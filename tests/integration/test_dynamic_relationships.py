"""Dynamic collections preserve relationship scope through QuerySet composition."""

import pytest
from sqlalchemy import ForeignKeyConstraint, event

from sqlobjects.database import close_db, init_db
from sqlobjects.exceptions import DeferredFieldError, PrimaryKeyError, QueryError, TransactionError
from sqlobjects.fields import (
    Column,
    IntegerColumn,
    M2MTable,
    RelatedQuerySet,
    StringColumn,
    foreign_key,
    identity,
    relationship,
)
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel
from sqlobjects.session import ctx_session
from tests.test_config import TestDatabaseConfig


class DynamicBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class DynamicParent(DynamicBase):
    id: Column[int] = identity()
    code: Column[str | None] = StringColumn(length=40, unique=True, nullable=True)
    children: RelatedQuerySet["DynamicChild"] = relationship(
        "DynamicChild", remote_fields="owner_code", lazy="dynamic", order_by="-score"
    )
    reviews = relationship("DynamicChild", remote_fields="reviewer_code", lazy="dynamic")
    tags = relationship("DynamicTag", secondary="dynamic_links", lazy="dynamic", order_by=["code"])
    mapped_tags = relationship(
        "DynamicTag",
        secondary=M2MTable("dynamic_links", "DynamicParent", "DynamicTag", "parent_code", "tag_code", "code", "code"),
        lazy="dynamic",
    )


class DynamicChild(DynamicBase):
    id: Column[int] = identity()
    owner_code: Column[str | None] = foreign_key("dynamic_parents.code", nullable=True)
    reviewer_code: Column[str | None] = foreign_key("dynamic_parents.code", nullable=True)
    score: Column[int] = IntegerColumn(default=0)
    owner = relationship("DynamicParent", foreign_keys="owner_code")


class DynamicTag(DynamicBase):
    id: Column[int] = identity()
    code: Column[str] = StringColumn(length=40, unique=True)
    parents = relationship("DynamicParent", secondary="dynamic_links", lazy="dynamic")


class DynamicLink(DynamicBase):
    id: Column[int] = identity()
    parent_code: Column[str] = foreign_key("dynamic_parents.code")
    tag_code: Column[str] = foreign_key("dynamic_tags.code")


class DynamicCompositeParent(DynamicBase):
    tenant: Column[int] = IntegerColumn(primary_key=True)
    number: Column[int] = IntegerColumn(primary_key=True)
    children = relationship(
        "DynamicCompositeChild", remote_fields=["tenant", "parent_number"], lazy="dynamic", uselist=True
    )


class DynamicCompositeChild(DynamicBase):
    id: Column[int] = identity()
    tenant: Column[int] = IntegerColumn()
    parent_number: Column[int] = IntegerColumn()

    class Config:
        constraints = [
            ForeignKeyConstraint(
                ["tenant", "parent_number"],
                ["dynamic_composite_parents.tenant", "dynamic_composite_parents.number"],
                name="fk_dynamic_composite_parent",
            )
        ]


class DynamicNode(DynamicBase):
    id: Column[int] = identity()
    parent_id: Column[int | None] = foreign_key("dynamic_nodes.id", nullable=True)
    children = relationship("DynamicNode", remote_fields="parent_id", uselist=True, lazy="dynamic")


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own their registry and transaction boundaries."""


@pytest.fixture
async def dynamic_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'dynamic.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    await db.create_tables(DynamicBase)
    try:
        yield db
    finally:
        await db.drop_tables(DynamicBase)
        await close_db()


@pytest.fixture
async def parent(dynamic_db):
    first = await DynamicParent.objects.create(code="first")
    await DynamicParent.objects.create(code="second")
    await DynamicChild.objects.bulk_create(
        [
            {"owner_code": "first", "reviewer_code": "second", "score": 1},
            {"owner_code": "first", "reviewer_code": "second", "score": 3},
            {"owner_code": "second", "reviewer_code": "first", "score": 9},
            {"owner_code": None, "reviewer_code": None, "score": 99},
        ]
    )
    return first


async def test_dynamic_queries_compose_without_loading_unrelated_rows(parent, dynamic_db):
    statements = []

    @dynamic_db.on("before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    relation = parent.children
    query = relation.filter(DynamicChild.score > 1).order_by("score").limit(1)
    assert statements == []
    assert isinstance(relation, RelatedQuerySet)
    assert [child.score for child in await query.all()] == [3]
    assert await relation.count() == 2
    assert await relation.exists() is True
    assert await parent.reviews.values_list("score", flat=True) == [9]
    assert await relation.values_list("score", flat=True) == [3, 1]
    assert await relation.order_by("score").values("score") == [{"score": 1}, {"score": 3}]
    event.remove(dynamic_db.engine.sync_engine, "before_cursor_execute", record)


async def test_fetch_and_stream_are_fresh_and_return_persisted_objects(parent):
    relation = parent.children
    rows = await relation.fetch()
    assert [row.score for row in rows] == [3, 1]
    assert all(row.is_from_database() for row in rows)
    await DynamicChild.objects.create(owner_code="first", score=5)
    assert [row.score for row in await relation.fetch()] == [5, 3, 1]
    assert [row.score async for row in relation] == [5, 3, 1]
    assert [row.score for row in await parent.load_relation("children")] == [5, 3, 1]
    assert [row.score for row in await relation[1:2].all()] == [3]


async def test_existing_query_keeps_scope_while_proxy_uses_current_key(parent):
    relation = parent.children
    first_query = relation.filter(DynamicChild.score > 0)
    parent.code = "second"
    assert await relation.values_list("score", flat=True) == [9]
    assert await first_query.values_list("score", flat=True) == [3, 1]


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_query_writes_retain_parent_scope_and_transaction(parent, operation):
    with pytest.raises(RuntimeError, match="rollback"):
        async with ctx_session() as session:
            query = parent.children.using(session).filter(score=1)
            if operation == "update":
                assert await query.update(score=7) == 1
            else:
                assert await query.delete(cascade="none") == 1
            raise RuntimeError("rollback")
    assert await parent.children.count() == 2
    assert await DynamicChild.objects.order_by("score").values_list("score", flat=True) == [1, 3, 9, 99]


@pytest.mark.parametrize("relation_name", ["tags", "mapped_tags"])
async def test_many_to_many_uses_real_keys_and_deduplicates_links(parent, relation_name):
    await DynamicTag.objects.bulk_create([{"code": "blue"}, {"code": "red"}, {"code": "green"}])
    await DynamicLink.objects.bulk_create(
        [
            {"parent_code": "first", "tag_code": "blue"},
            {"parent_code": "first", "tag_code": "blue"},
            {"parent_code": "first", "tag_code": "red"},
            {"parent_code": "second", "tag_code": "green"},
        ]
    )
    relation = getattr(parent, relation_name)
    assert await relation.order_by("code").values_list("code", flat=True) == ["blue", "red"]
    assert await relation.count() == 2
    assert await relation.filter(code="green").exists() is False
    blue = await DynamicTag.objects.get(code="blue")
    assert await blue.parents.values_list("code", flat=True) == ["first"]


async def test_composite_foreign_key_keeps_every_parent_component(dynamic_db):
    await DynamicCompositeParent.objects.bulk_create(
        [{"tenant": 1, "number": 1}, {"tenant": 2, "number": 1}, {"tenant": 1, "number": 2}]
    )
    await DynamicCompositeChild.objects.bulk_create(
        [{"tenant": 1, "parent_number": 1}, {"tenant": 2, "parent_number": 1}, {"tenant": 1, "parent_number": 2}]
    )
    parent = await DynamicCompositeParent.objects.get(tenant=1, number=1)
    assert await parent.children.values("tenant", "parent_number") == [{"tenant": 1, "parent_number": 1}]


async def test_self_relationship_uses_child_foreign_key(dynamic_db):
    root = await DynamicNode.objects.create(parent_id=None)
    branch = await DynamicNode.objects.create(parent_id=root.id)
    await DynamicNode.objects.create(parent_id=branch.id)
    await DynamicNode.objects.create(parent_id=None)
    assert await root.children.values_list("id", flat=True) == [branch.id]
    assert await branch.children.count() == 1


@pytest.mark.parametrize("relation_name", ["children", "tags"])
async def test_missing_parent_primary_key_never_queries_orphans(parent, dynamic_db, relation_name):
    statements = []

    @dynamic_db.on("before_cursor_execute")
    def record(*args):
        statements.append(args)

    with pytest.raises(PrimaryKeyError, match="primary key"):
        await getattr(DynamicParent(code="first"), relation_name).count()
    assert statements == []


@pytest.mark.parametrize("relation_name", ["children", "tags"])
async def test_null_reference_key_is_empty(parent, relation_name):
    empty = await DynamicParent.objects.create(code=None)
    assert await getattr(empty, relation_name).count() == 0
    assert await getattr(empty, relation_name).fetch() == []


async def test_deferred_reference_key_requires_explicit_loading(parent):
    partial_parent = await DynamicParent.objects.only("id").get(id=parent.id)
    with pytest.raises(DeferredFieldError, match="code"):
        await partial_parent.children.count()
    await partial_parent.load_deferred_field("code")
    assert await partial_parent.children.count() == 2


async def test_binding_and_hydration_follow_parent_database(parent, dynamic_db):
    await init_db(dynamic_db.engine.url.render_as_string(hide_password=False), name="other", is_default=False)
    try:
        parent.using("other")
        relation = parent.children
        child = await relation.first()
        assert child is not None
        assert child._state_manager.get_bound_session() == "other"
        child.score = 4
        await child.save(cascade=False)
        assert (await DynamicChild.objects.get(id=child.id)).score == 4
        async with ctx_session("other") as session:
            parent.using(session)
            query = relation.filter(score=4)
            assert await query.count() == 1
        with pytest.raises(TransactionError, match="closed"):
            await query.count()
        parent.using("default")
        assert await relation.count() == 2
    finally:
        await close_db("other")


@pytest.mark.parametrize("mode", ["prefetch", "custom", "nested", "select"])
async def test_eager_loading_dynamic_relationships_is_rejected(parent, mode):
    with pytest.raises(ValueError, match="dynamic"):
        if mode == "prefetch":
            DynamicParent.objects.prefetch_related("children")
        elif mode == "custom":
            DynamicParent.objects.prefetch_related(children=DynamicChild.objects.filter(score=1))
        elif mode == "nested":
            DynamicChild.objects.prefetch_related("owner__children")
        else:
            DynamicParent.objects.select_related("children")


@pytest.mark.parametrize("operation", [bool, len, iter])
async def test_synchronous_collection_protocols_require_explicit_async_queries(parent, operation):
    with pytest.raises(TypeError, match="await|async"):
        operation(parent.children)


async def test_unsupported_scalar_and_custom_join_relationships_fail_clearly(parent, monkeypatch):
    descriptor = DynamicParent.children
    monkeypatch.setattr(descriptor.property, "primaryjoin", "custom condition")
    with pytest.raises(QueryError, match="custom join"):
        await parent.children.count()
    monkeypatch.setattr(descriptor.property, "primaryjoin", None)
    owner = DynamicChild.owner
    monkeypatch.setattr(owner.property, "lazy", "dynamic")
    child = await DynamicChild.objects.filter(owner_code="first").first()
    assert child is not None
    with pytest.raises(QueryError, match="collection"):
        await child.owner.count()


def test_same_named_models_resolve_within_the_owning_registry():
    def models():
        class LocalBase(ObjectModel):
            __abstract__ = True
            __registry__ = ModelRegistry()

        class LocalOwner(LocalBase):
            id: Column[int] = identity()
            entries = relationship("LocalEntry", remote_fields="owner_id", lazy="dynamic")

        class LocalEntry(LocalBase):
            id: Column[int] = identity()
            owner_id: Column[int] = foreign_key("local_owners.id")

        return LocalOwner, LocalEntry

    first_owner, first_entry = models()
    second_owner, second_entry = models()
    assert first_owner(id=1).entries.filter()._model_class is first_entry
    assert second_owner(id=1).entries.filter()._model_class is second_entry
