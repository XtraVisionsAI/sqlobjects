"""Regression tests for the ORM review follow-up fixes.

Covers session cleanup from generator finalizers, implicit-session savepoints,
readonly session resilience, UPSERT RETURNING attribution, instance-save commit
callbacks, dynamic relationship attribute protocol and index signature rendering.
"""

import asyncio
import copy
import gc
from typing import Any, cast

import pytest
from sqlalchemy import JSON, column, text
from sqlalchemy.pool import QueuePool

from sqlobjects import ConflictResolution
from sqlobjects.database import close_db, create_tables, drop_tables, get_database, init_db
from sqlobjects.exceptions import IntegrityError, SQLObjectsError, TransactionError
from sqlobjects.fields import Column, IntegerColumn, RelatedQuerySet, StringColumn, foreign_key, identity, relationship
from sqlobjects.metadata import ModelRegistry, index
from sqlobjects.model import ObjectModel
from sqlobjects.session import AsyncSession, ctx_session
from tests.test_config import TestDatabaseConfig


class FollowupBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class FollowupItem(FollowupBase):
    id: Column[int] = identity()
    code: Column[int] = IntegerColumn(unique=True)
    name: Column[str] = StringColumn(length=32, default="")

    events: list = []

    async def before_save(self, ctx):
        async def check():
            seen = await FollowupItem.objects.filter(code=self.code).count()
            FollowupItem.events.append(("on_commit", seen))

        await ctx.on_commit(check)

    async def after_save(self, ctx):
        FollowupItem.events.append(("after_save",))


class FollowupAuthor(FollowupBase):
    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=32)
    posts = relationship("FollowupPost", back_populates="author", lazy="dynamic")


class FollowupPost(FollowupBase):
    id: Column[int] = identity()
    author_id: Column[int] = foreign_key("followup_authors.id")
    title: Column[str] = StringColumn(length=32)
    author = relationship("FollowupAuthor", back_populates="posts")


MODELS = [FollowupItem, FollowupAuthor, FollowupPost]


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own their database lifecycle."""


@pytest.fixture
async def followup_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'followups.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    await create_tables(FollowupBase, tables=MODELS)
    FollowupItem.events.clear()
    try:
        yield db
    finally:
        await drop_tables(FollowupBase, tables=MODELS)
        await close_db()


class TestSessionCleanup:
    async def test_abandoned_iterator_releases_connection(self, followup_db):
        for code in range(5):
            await FollowupItem.objects.create(code=code)
        pool = cast(QueuePool, get_database("default").engine.pool)
        assert pool.checkedout() == 0

        async for _ in FollowupItem.objects.order_by("id").iterator(chunk_size=2):
            break
        # asyncio finalizes the abandoned generator from another task.
        for _ in range(3):
            gc.collect()
            await asyncio.sleep(0.05)

        assert pool.checkedout() == 0
        assert (await FollowupItem.objects.create(code=99)).id is not None

    async def test_caller_owned_session_still_rejects_close_from_another_task(self, followup_db):
        session = AsyncSession("default", readonly=False, auto_commit=False)
        await session.execute(text("SELECT 1"))
        with pytest.raises(TransactionError, match="another asyncio task"):
            await asyncio.create_task(session.close())
        await session.close()

    async def test_readonly_session_survives_failed_query(self, followup_db):
        session = AsyncSession("default", readonly=True)
        with pytest.raises(SQLObjectsError):
            await session.execute(text("SELECT * FROM followup_missing_table"))
        assert (await session.execute(text("SELECT 1"))).scalar() == 1
        await session.close()

    async def test_explicit_session_still_requires_rollback_after_failure(self, followup_db):
        async with ctx_session() as session:
            with pytest.raises(SQLObjectsError):
                await session.execute(text("SELECT * FROM followup_missing_table"))
            with pytest.raises(TransactionError):
                await session.execute(text("SELECT 1"))
            await session.rollback()
            assert (await session.execute(text("SELECT 1"))).scalar() == 1


class TestImplicitSavepoint:
    async def test_released_savepoint_on_implicit_session_commits(self, followup_db):
        session = AsyncSession("default", readonly=False, auto_commit=True)
        async with await session.begin_nested():
            await session.execute(FollowupItem.get_table().insert().values(code=1))
        assert not session.in_transaction
        await session.close()
        assert await FollowupItem.objects.filter(code=1).count() == 1

    async def test_rolled_back_savepoint_on_implicit_session_persists_nothing(self, followup_db):
        session = AsyncSession("default", readonly=False, auto_commit=True)
        with pytest.raises(RuntimeError):
            async with await session.begin_nested():
                await session.execute(FollowupItem.get_table().insert().values(code=2))
                raise RuntimeError("abort")
        assert not session.in_transaction
        await session.close()
        assert await FollowupItem.objects.filter(code=2).count() == 0

    async def test_nested_savepoints_commit_once_outermost_ends(self, followup_db):
        session = AsyncSession("default", readonly=False, auto_commit=True)
        async with await session.begin_nested():
            await session.execute(FollowupItem.get_table().insert().values(code=3))
            async with await session.begin_nested():
                await session.execute(FollowupItem.get_table().insert().values(code=4))
            assert session.in_transaction
        assert not session.in_transaction
        await session.close()
        assert await FollowupItem.objects.filter(FollowupItem.code.in_([3, 4])).count() == 2


class TestUpsertAttribution:
    async def test_returning_rows_matched_after_database_normalization(self, followup_db, db_type):
        if db_type != "sqlite":
            pytest.skip("Only SQLite coerces a string key to INTEGER; attribution logic is covered below")
        result = await FollowupItem.objects.bulk_create(
            [{"code": "21", "name": "a"}, {"code": "22", "name": "b"}],
            on_conflict=ConflictResolution.UPDATE,
            conflict_fields=["code"],
            return_objects=True,
        )
        assert result.success_count == 2
        objects = cast(list[FollowupItem], result.objects)
        assert [(obj.code, obj.name) for obj in objects] == [(21, "a"), (22, "b")]
        assert await FollowupItem.objects.count() == 2

    async def test_normalized_returning_rows_are_attributed_through_lookup(self, followup_db):
        """Attribution must not trust raw input keys: the database may normalize them."""
        from sqlobjects.objects.upsert import UpsertHandler

        table = FollowupItem.get_table()
        stored = [
            {"id": 1, "code": 21, "name": "a"},
            {"id": 2, "code": 22, "name": "b"},
            {"id": 3, "code": 23, "name": "stale-row-not-returned"},
        ]

        class StubResult:
            def __init__(self, row):
                self._row = row

            def one_or_none(self):
                if self._row is None:
                    return None
                return type("Row", (), {"_mapping": self._row})()

        class StubSession:
            lookups = 0

            async def execute(self, statement):
                StubSession.lookups += 1
                wanted = statement.whereclause.right.value
                return StubResult(next((r for r in stored if str(r["code"]) == str(wanted)), None))

        handler = UpsertHandler.__new__(UpsertHandler)
        handler.session = StubSession()  # type: ignore[assignment]
        rows = await handler._match_returned_rows(
            table,
            [{"code": "22"}, {"code": "21"}, {"code": "23"}],
            ["code"],
            [stored[0], stored[1]],
        )
        # Input order is restored, and the row the statement never returned is not fabricated.
        assert [row["name"] for row in rows] == ["b", "a"]
        assert StubSession.lookups == 2

    async def test_returning_rows_keep_input_order(self, followup_db):
        await FollowupItem.objects.create(code=31, name="old")
        result = await FollowupItem.objects.bulk_create(
            [{"code": 32, "name": "new"}, {"code": 31, "name": "updated"}],
            on_conflict=ConflictResolution.UPDATE,
            conflict_fields=["code"],
            return_objects=True,
        )
        objects = cast(list[FollowupItem], result.objects)
        assert [(obj.code, obj.name) for obj in objects] == [(32, "new"), (31, "updated")]


class TestInstanceSaveCommitCallbacks:
    async def test_implicit_save_runs_on_commit_after_write(self, followup_db):
        await FollowupItem(code=41).save()
        assert FollowupItem.events == [("after_save",), ("on_commit", 1)]

    async def test_explicit_save_defers_on_commit_until_commit(self, followup_db):
        async with ctx_session():
            await FollowupItem(code=42).save()
            assert FollowupItem.events == [("after_save",)]
        assert FollowupItem.events == [("after_save",), ("on_commit", 1)]

    async def test_failed_implicit_save_discards_on_commit(self, followup_db):
        await FollowupItem.objects.create(code=43)
        FollowupItem.events.clear()
        with pytest.raises(IntegrityError):
            await FollowupItem(code=43).save()
        assert FollowupItem.events == []


class TestDynamicRelationshipProtocol:
    async def test_unsaved_parent_supports_hasattr_and_to_dict(self, followup_db):
        author = FollowupAuthor(name="x")
        assert isinstance(author.posts, RelatedQuerySet)
        assert hasattr(author.posts, "not_a_queryset_method") is False
        assert getattr(author.posts, "missing", None) is None
        assert author.to_dict(include_relations=True) == {"id": None, "name": "x"}

    async def test_saved_parent_to_dict_skips_dynamic_collection(self, followup_db):
        author = await FollowupAuthor.objects.create(name="x")
        await FollowupPost.objects.create(author_id=author.id, title="p")
        assert author.to_dict(include_relations=True) == {"id": author.id, "name": "x"}
        assert await author.posts.count() == 1

    async def test_instances_with_dynamic_relationships_support_copy(self, followup_db):
        author = await FollowupAuthor.objects.create(name="x")
        clone = copy.deepcopy(author)
        assert clone.name == "x"
        assert copy.copy(author).id == author.id


class TestIndexSignatures:
    def test_unrenderable_partial_index_predicate_does_not_break_model_definition(self):
        class SignatureBase(ObjectModel):
            __abstract__ = True
            __registry__ = ModelRegistry()

        class SignatureModel(SignatureBase):
            id: Column[int] = identity()
            x: Column[int] = IntegerColumn()

            class Config:
                indexes = [index(None, "x", postgresql_where=cast(Any, column("payload", JSON) == {"a": 1}))]

        assert [idx.name for idx in SignatureModel.get_table().indexes] == ["idx_signature_models_x"]
