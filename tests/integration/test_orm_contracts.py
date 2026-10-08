"""Regression tests for persistence, transaction and query contracts."""

import asyncio
from contextlib import aclosing
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from sqlobjects import ConflictResolution, ErrorHandling, TransactionMode
from sqlobjects.database import close_db, create_tables, drop_tables, init_db
from sqlobjects.exceptions import DoesNotExist, IntegrityError, QueryError, TransactionError
from sqlobjects.fields import Column, IntegerColumn, StringColumn, foreign_key, identity, relationship
from sqlobjects.model import ObjectModel
from sqlobjects.queryset import QuerySet
from sqlobjects.session import ctx_session
from tests.test_config import TestDatabaseConfig


class ContractRecord(ObjectModel):
    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=64, unique=True, nullable=False)
    value: Column[int] = IntegerColumn(default=0)


class ContractParent(ObjectModel):
    id: Column[int] = identity()
    code: Column[str] = StringColumn(length=64, unique=True)
    children = relationship("ContractChild", remote_fields="author_code")


class ContractChild(ObjectModel):
    id: Column[int] = identity()
    reviewer_code: Column[str] = foreign_key("contract_parents.code")
    author_code: Column[str] = foreign_key("contract_parents.code")
    author = relationship("ContractParent", foreign_keys="author_code")
    reviewer = relationship("ContractParent", foreign_keys="reviewer_code")


MODELS = [ContractRecord, ContractParent, ContractChild]


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own their database lifecycle, including commits and rollbacks."""


@pytest.fixture
async def contract_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'contracts.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    await create_tables(ObjectModel, tables=MODELS)
    try:
        yield db
    finally:
        await drop_tables(ObjectModel, tables=MODELS)
        await close_db()


async def seed(count=3):
    await ContractRecord.objects.bulk_create([{"name": f"r{i}", "value": i % 2} for i in range(count)])


@pytest.mark.usefixtures("contract_db")
class TestPersistenceContracts:
    @pytest.mark.parametrize("operation", ["update", "delete"])
    @pytest.mark.parametrize("kind", ["limit", "offset"])
    async def test_sliced_writes_are_rejected(self, operation, kind):
        await seed()
        query = getattr(ContractRecord.objects.order_by("id"), kind)(1)
        with pytest.raises(QueryError):
            if operation == "update":
                await query.update(value=99)
            else:
                await query.delete(cascade="none")
        assert await ContractRecord.objects.count() == 3
        assert await ContractRecord.objects.filter(value=99).count() == 0

    @pytest.mark.parametrize("resolution", [ConflictResolution.UPDATE, ConflictResolution.IGNORE])
    async def test_upsert_processes_every_input(self, resolution):
        await ContractRecord.objects.create(name="existing", value=1)
        result = await ContractRecord.objects.bulk_create(
            [{"name": "first", "value": 2}, {"name": "existing", "value": 3}, {"name": "last", "value": 4}],
            on_conflict=resolution,
            conflict_fields=["name"],
            return_objects=True,
        )
        assert await ContractRecord.objects.count() == 3
        assert (await ContractRecord.objects.get(name="last")).value == 4
        assert (await ContractRecord.objects.get(name="existing")).value == (
            3 if resolution == ConflictResolution.UPDATE else 1
        )
        assert result.success_count == (3 if resolution == ConflictResolution.UPDATE else 2)

    async def test_instance_writes_without_ambient_session(self):
        obj = ContractRecord(name="new", value=1)
        await obj.save(cascade=False)
        loaded = await ContractRecord.objects.get(id=obj.id)
        loaded.value = 7
        await loaded.save(cascade=False)
        assert (await ContractRecord.objects.get(id=obj.id)).value == 7
        await loaded.delete(cascade=False)
        assert await ContractRecord.objects.count() == 0

    async def test_dirty_save_preserves_other_changes(self):
        await seed(1)
        first = await ContractRecord.objects.get(name="r0")
        stale = await ContractRecord.objects.get(name="r0")
        first.value = 7
        await first.save(cascade=False)
        stale.name = "renamed"
        await stale.save(cascade=False)
        assert (await ContractRecord.objects.get(name="renamed")).value == 7

    async def test_bulk_update_returns_only_matched_stored_rows(self):
        obj = await ContractRecord.objects.create(name="keep", value=1)
        result = await ContractRecord.objects.bulk_update(
            [{"id": obj.id + 1000, "value": 9}, {"id": obj.id, "value": 7}],
            return_objects=True,
        )
        assert result.success_count == 1
        assert len(result.objects) == 1
        stored = result.objects[0]
        assert isinstance(stored, ContractRecord)
        assert stored.id == obj.id
        assert stored.name == "keep"
        assert stored.value == 7

    async def test_bulk_update_count_excludes_missing_rows(self):
        obj = await ContractRecord.objects.create(name="keep", value=1)
        count = await ContractRecord.objects.bulk_update(
            [{"id": obj.id + 1000, "value": 9}, {"id": obj.id, "value": 7}],
        )
        assert count == 1

    async def test_partial_save_and_deferred_fetch(self):
        await ContractRecord.objects.create(name="partial", value=42)
        obj = await ContractRecord.objects.only("name").get(name="partial")
        assert obj.id is not None
        assert obj.is_field_deferred("value")
        obj.name = "renamed"
        await obj.save(cascade=False)
        assert (await ContractRecord.objects.get(name="renamed")).value == 42
        await obj.load_deferred_field("value")
        assert obj.value == 42

    async def test_defer_retains_primary_key(self):
        stored = await ContractRecord.objects.create(name="partial", value=42)
        obj = await ContractRecord.objects.defer("id", "value").get(name="partial")
        assert obj.id == stored.id
        assert not obj.is_field_deferred("id")
        obj.name = "renamed"
        await obj.save(cascade=False)
        assert (await ContractRecord.objects.get(id=stored.id)).value == 42

    async def test_multi_database_origin(self, tmp_path):
        await ContractRecord.objects.create(id=1, name="default", value=1)
        await init_db(f"sqlite+aiosqlite:///{tmp_path / 'other.db'}", name="other", is_default=False)
        try:
            await create_tables(ObjectModel, db_name="other", tables=MODELS)
            await ContractRecord.objects.using("other").create(id=1, name="other", value=2)
            raw = await ContractRecord.objects.using("other").raw("SELECT id, name FROM contract_records")
            assert raw[0].is_from_database()
            assert raw[0].is_field_deferred("value")
            await raw[0].load_deferred_field("value")
            assert raw[0].value == 2
            obj = await ContractRecord.objects.using("other").only("id", "name").get(id=1)
            await obj.load_deferred_field("value")
            assert obj.value == 2
            await obj.refresh()
            assert obj.name == "other"
            obj.value = 9
            await obj.save(cascade=False)
            assert (await ContractRecord.objects.using("other").get(id=1)).value == 9
            await obj.delete(cascade=False)
            assert await ContractRecord.objects.using("other").count() == 0
            assert (await ContractRecord.objects.get(id=1)).value == 1
        finally:
            await close_db("other")

    async def test_full_delete_does_not_skip_batches(self):
        await seed(150)
        assert await ContractRecord.objects.filter().delete(cascade="full") == 150
        assert await ContractRecord.objects.count() == 0

    async def test_integrity_errors_keep_their_type(self):
        await seed(1)
        with pytest.raises(IntegrityError):
            await ContractRecord.objects.create(name="r0")
        with pytest.raises(IntegrityError):
            await ContractRecord(name="r0").save(cascade=False)


@pytest.mark.usefixtures("contract_db")
class TestTransactionContracts:
    async def test_failed_transaction_requires_rollback(self):
        async with ctx_session() as session:
            await ContractRecord.objects.create(name="duplicate")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.create(name="duplicate")
            with pytest.raises(TransactionError):
                await session.execute(select(ContractRecord.get_table()))
            with pytest.raises(TransactionError):
                await session.stream(select(ContractRecord.get_table()))
            with pytest.raises(TransactionError):
                await session.commit()
            await session.rollback()
            await ContractRecord.objects.create(name="after")
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"after"}

    @pytest.mark.parametrize("on_error", [ErrorHandling.COLLECT, ErrorHandling.IGNORE])
    async def test_upsert_error_recovery_preserves_valid_rows(self, on_error):
        async with ctx_session():
            await ContractRecord.objects.create(name="outer")
            result = await ContractRecord.objects.bulk_create(
                [{"name": "first", "value": 1}, {"name": None, "value": 2}, {"name": "last", "value": 3}],
                on_conflict=ConflictResolution.UPDATE,
                conflict_fields=["name"],
                on_error=on_error,
                return_objects=True,
            )
            assert result.success_count == 2
            if on_error == ErrorHandling.COLLECT:
                assert [failure.index for failure in result.failed_records] == [1]
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"outer", "first", "last"}

    async def test_savepoint_failure_preserves_outer_write(self):
        await seed(1)
        async with ctx_session():
            await ContractRecord.objects.create(name="outer")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.bulk_create(
                    [{"name": "r0"}],
                    transaction_mode=TransactionMode.SAVEPOINT,
                )
            await ContractRecord.objects.create(name="after")
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"r0", "outer", "after"}

    async def test_independent_survives_outer_rollback(self):
        with pytest.raises(ValueError, match="outer rollback"):
            async with ctx_session():
                await ContractRecord.objects.bulk_create(
                    [{"name": "independent"}],
                    transaction_mode=TransactionMode.INDEPENDENT,
                )
                raise ValueError("outer rollback")
        assert await ContractRecord.objects.filter(name="independent").count() == 1

    async def test_independent_is_atomic_across_batches(self):
        await seed(1)
        with pytest.raises(IntegrityError):
            await ContractRecord.objects.bulk_create(
                [{"name": "first"}, {"name": "r0"}],
                batch_size=1,
                transaction_mode=TransactionMode.INDEPENDENT,
            )
        assert await ContractRecord.objects.count() == 1

    async def test_batch_mode_commits_each_batch(self):
        await seed(1)
        with pytest.raises(IntegrityError):
            async with ctx_session():
                await ContractRecord.objects.bulk_create(
                    [{"name": "first"}, {"name": "r0"}],
                    batch_size=1,
                    transaction_mode=TransactionMode.BATCH,
                )
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"r0", "first"}

    async def test_collect_preserves_successful_rows(self):
        await seed(1)
        async with ctx_session():
            result = await ContractRecord.objects.bulk_create(
                [{"name": "first"}, {"name": "r0"}, {"name": "last"}],
                on_error=ErrorHandling.COLLECT,
                return_objects=True,
            )
            assert result.success_count == 2
            assert result.error_count == 1
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"r0", "first", "last"}

    async def test_get_or_create_race(self):
        original = QuerySet.get
        barrier = asyncio.Event()
        misses = 0

        async def synchronized_get(queryset, *args, **kwargs):
            nonlocal misses
            try:
                return await original(queryset, *args, **kwargs)
            except DoesNotExist:
                misses += 1
                if misses == 2:
                    barrier.set()
                await barrier.wait()
                raise

        with patch.object(QuerySet, "get", synchronized_get):
            results = await asyncio.wait_for(
                asyncio.gather(
                    ContractRecord.objects.get_or_create(name="same"),
                    ContractRecord.objects.get_or_create(name="same"),
                ),
                timeout=10,
            )
        assert sorted(created for _, created in results) == [False, True]
        assert results[0][0].id == results[1][0].id
        assert await ContractRecord.objects.count() == 1


@pytest.mark.usefixtures("contract_db")
class TestQueryContracts:
    async def test_locking_queries_require_transaction(self, db_type):
        if db_type == "sqlite":
            pytest.skip("SQLite does not implement SELECT FOR UPDATE")
        query = ContractRecord.objects.select_for_update()
        with pytest.raises(TransactionError):
            await query.all()
        with pytest.raises(TransactionError):
            async with aclosing(query.iterator()) as stream:
                await anext(stream)

    async def test_iterator_preserves_query_and_models(self):
        await seed()
        query = ContractRecord.objects.order_by("id").offset(1).limit(1)
        expected = await query.all()
        actual = [obj async for obj in query.iterator(chunk_size=2)]
        assert all(isinstance(obj, ContractRecord) for obj in actual)
        assert [obj.id for obj in actual] == [obj.id for obj in expected]

    async def test_iterator_early_close_returns_connection(self, contract_db):
        await seed()
        async with aclosing(ContractRecord.objects.iterator(chunk_size=1)) as stream:
            await anext(stream)
        assert contract_db.engine.pool.checkedout() == 0

    async def test_count_preserves_limits_and_groups(self):
        await seed()
        assert await ContractRecord.objects.limit(1).count() == 1
        assert await ContractRecord.objects.only("value").group_by("value").count() == 2

    async def test_count_subquery_matches_executed_count(self):
        await seed()
        for query in [
            ContractRecord.objects.limit(1),
            ContractRecord.objects.only("value").group_by("value"),
        ]:
            count = query.count()
            async with ctx_session() as session:
                result = await session.execute(select(count.scalar_subquery()))
                assert result.scalar_one() == await count

    async def test_correlated_count_subquery(self):
        await ContractParent.objects.create(code="author")
        await ContractParent.objects.create(code="empty")
        await ContractChild.objects.create(author_code="author", reviewer_code="author")
        count = ContractChild.objects.filter(ContractChild.author_code == ContractParent.code).count()
        async with ctx_session() as session:
            result = await session.execute(select(ContractParent.code, count.scalar_subquery().label("total")))
            assert {row["code"]: row["total"] for row in result.mappings()} == {"author": 1, "empty": 0}

    async def test_select_related_uses_columns_and_aliases(self, contract_db):
        await ContractParent.objects.create(code="author")
        await ContractParent.objects.create(code="reviewer")
        await ContractChild.objects.create(author_code="author", reviewer_code="reviewer")
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(contract_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            child = await ContractChild.objects.select_related("author", "reviewer").get()
            author = await child.load_relation("author")
            reviewer = await child.load_relation("reviewer")
            assert author.code == "author"
            assert reviewer.code == "reviewer"
            assert len(statements) == 1
        finally:
            event.remove(contract_db.engine.sync_engine, "before_cursor_execute", record)

    async def test_custom_prefetch_uses_declared_foreign_key(self):
        await ContractParent.objects.create(code="author")
        await ContractParent.objects.create(code="reviewer")
        await ContractChild.objects.create(author_code="author", reviewer_code="reviewer")
        parent = (
            await ContractParent.objects.filter(code="author")
            .prefetch_related(
                children=ContractChild.objects.filter(),
            )
            .get()
        )
        children = await parent.load_relation("children")
        assert len(children) == 1
        assert children[0].author_code == "author"

    async def test_invalid_relationship_is_an_error(self):
        with pytest.raises((ValueError, QueryError)):
            await ContractParent.objects.prefetch_related("typo").all()
