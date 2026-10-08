"""Deferred loading benchmarks with verified projections and query counts."""

import asyncio

import pytest
from sqlalchemy import Text
from sqlalchemy.ext.compiler import compiles

from sqlobjects.fields import Column, StringColumn, column, identity
from sqlobjects.fields.proxies import DeferredObject
from sqlobjects.fields.types import StringComparator, register_field_type
from sqlobjects.session import ctx_session
from tests.conftest import TestModel


CONTENT_FIELDS = ("small_bio", "medium_content", "large_content", "huge_content")
CONTENT_SIZES = (100, 1024, 10240, 102400)


class PerformanceLargeText(Text):
    # The 100 KiB fixture exceeds MySQL's ordinary TEXT capacity.
    pass


@compiles(PerformanceLargeText, "mysql")
def compile_large_text(type_, compiler, **kwargs):
    return "LONGTEXT"


register_field_type(PerformanceLargeText, "performance_large_text", comparator=StringComparator)


class PerformanceTestUser(TestModel):
    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100)
    small_bio: Column[str] = column(type="text", deferred=True)
    medium_content: Column[str] = column(type="text", deferred=True)
    large_content: Column[str] = column(type="text", deferred=True)
    huge_content: Column[str] = column(type="performance_large_text", deferred=True)


@pytest.fixture
async def performance_dataset(session):
    content = {name: "x" * size for name, size in zip(CONTENT_FIELDS, CONTENT_SIZES, strict=True)}
    assert (
        await PerformanceTestUser.objects.using(session).bulk_create(
            [{"username": f"perf{i}", "email": f"perf{i}@example.com", **content} for i in range(100)]
        )
        == 100
    )


@pytest.mark.usefixtures("performance_dataset")
@pytest.mark.parametrize("deferred", [("huge_content",), CONTENT_FIELDS])
async def test_full_and_deferred_loading(session, benchmark, deferred):
    query = PerformanceTestUser.objects.using(session).order_by("id")
    with benchmark.measure("full") as full_sample:
        full = await query.only(*PerformanceTestUser.__table__.columns.keys()).all()
    assert len(full) == 100
    assert all(user.is_field_loaded(name) for user in full for name in CONTENT_FIELDS)
    assert [len(getattr(full[0], name)) for name in CONTENT_FIELDS] == list(CONTENT_SIZES)
    full_ids = [user.id for user in full]
    del full

    # An explicit projection overrides model defaults, which defer all four.
    with benchmark.measure(f"defer_{len(deferred)}") as deferred_sample:
        partial = await query.only(*PerformanceTestUser.__table__.columns.keys()).defer(*deferred).all()
    assert [user.id for user in partial] == full_ids
    for user in partial:
        for name in CONTENT_FIELDS:
            assert user.is_field_deferred(name) == (name in deferred)
    assert full_sample.statements == deferred_sample.statements == 1
    full_sql, partial_sql = benchmark.statements[-2:]
    for name in deferred:
        assert name in full_sql
        assert name not in partial_sql


@pytest.mark.usefixtures("performance_dataset")
@pytest.mark.parametrize("field", ["small_bio", "huge_content"])
async def test_selective_loading(session, benchmark, field):
    users = await PerformanceTestUser.objects.using(session).order_by("id").limit(10).all()
    assert all(user.is_field_deferred(field) for user in users)
    with benchmark.measure(field) as sample:
        for user in users:
            await user.load_deferred_field(field)
    assert sample.statements == 10
    assert all(user.is_field_loaded(field) for user in users)
    assert all(len(getattr(user, field)) == CONTENT_SIZES[CONTENT_FIELDS.index(field)] for user in users)


@pytest.mark.usefixtures("performance_dataset")
async def test_batch_deferred_loading_efficiency(session, benchmark):
    users = await PerformanceTestUser.objects.using(session).order_by("id").limit(20).all()
    with benchmark.measure("individual_fields") as individual:
        for user in users[:10]:
            await user.load_deferred_field("small_bio")
            await user.load_deferred_field("medium_content")
    with benchmark.measure("combined_fields") as combined:
        for user in users[10:]:
            await user.load_deferred_fields(["small_bio", "medium_content"])
    assert individual.statements == 20
    assert combined.statements == 10
    assert all(user.small_bio == "x" * 100 and user.medium_content == "x" * 1024 for user in users)


async def make_deferred_user(session):
    user = await PerformanceTestUser.objects.using(session).create(
        username="proxy", email="proxy@example.com", small_bio="content"
    )
    return await PerformanceTestUser.objects.using(session).get(id=user.id)


async def test_proxy_object_creation_overhead(session, benchmark):
    user = await make_deferred_user(session)
    with benchmark.measure("create_1000_proxies") as sample:
        proxies = [DeferredObject(user, "small_bio") for _ in range(1000)]
    assert all(proxy.field_name == "small_bio" for proxy in proxies)
    assert sample.statements == 0
    assert user.is_field_deferred("small_bio")


async def test_deferred_field_cache_efficiency(session, benchmark):
    user = await make_deferred_user(session)
    proxy = DeferredObject(user, "small_bio")
    with benchmark.measure("first_fetch") as first:
        result1 = await proxy.fetch()
    with benchmark.measure("cached_fetch") as cached:
        result2 = await proxy.fetch()
    assert result1 == result2 == "content"
    assert first.statements == 1
    assert cached.statements == 0


async def test_concurrent_deferred_loading(session, benchmark):
    await PerformanceTestUser.objects.using(session).bulk_create(
        [{"username": f"concurrent{i}", "email": f"{i}@example.com", "medium_content": "x" * 1024} for i in range(25)]
    )
    ids = await PerformanceTestUser.objects.using(session).order_by("id").values_list("id", flat=True)
    await session.commit()

    async def load(pk):
        async with ctx_session() as worker:
            user = await PerformanceTestUser.objects.using(worker).get(id=pk)
            assert user.is_field_deferred("medium_content")
            await user.load_deferred_field("medium_content")
            return user.id, user.medium_content

    with benchmark.measure("sequential_load") as sequential_sample:
        sequential = [await load(pk) for pk in ids]
    semaphore = asyncio.Semaphore(5)

    async def limited_load(pk):
        async with semaphore:
            return await load(pk)

    with benchmark.measure("concurrent_load_5_workers") as concurrent_sample:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(limited_load(pk)) for pk in ids]
    assert sequential == [task.result() for task in tasks] == [(pk, "x" * 1024) for pk in ids]
    assert sequential_sample.statements == concurrent_sample.statements == 50


async def test_deferred_field_status_checks(session, benchmark):
    user = await make_deferred_user(session)
    with benchmark.measure("8000_status_checks") as sample:
        for _ in range(1000):
            for name in CONTENT_FIELDS:
                assert user.is_field_deferred(name)
                assert not user.is_field_loaded(name)
    assert sample.statements == 0


async def test_proxy_cache_performance(session, benchmark):
    user = await make_deferred_user(session)
    with benchmark.measure("first_proxy") as first:
        proxy1 = user.small_bio
    with benchmark.measure("cached_proxy") as cached:
        proxy2 = user.small_bio
    assert proxy1 is proxy2
    assert isinstance(proxy1, DeferredObject)
    assert first.statements == cached.statements == 0


async def test_deferred_vs_regular_field_access(session, benchmark):
    user = await make_deferred_user(session)
    normal = await PerformanceTestUser.objects.using(session).only("id", "small_bio").get(id=user.id)
    await user.load_deferred_field("small_bio")
    assert normal.is_field_loaded("small_bio") and user.is_field_loaded("small_bio")
    for label, instance in (("eager_access", normal), ("loaded_deferred_access", user)):
        with benchmark.measure(label) as sample:
            for _ in range(10000):
                assert instance.small_bio == "content"
        assert sample.statements == 0


async def test_bulk_deferred_loading(session, benchmark):
    await PerformanceTestUser.objects.using(session).bulk_create(
        [{"username": f"bulk{i}", "email": f"{i}@example.com", "medium_content": "x" * 1024} for i in range(200)]
    )
    users = await PerformanceTestUser.objects.using(session).all()
    with benchmark.measure("load_200_fields") as sample:
        for user in users:
            await user.load_deferred_field("medium_content")
    assert len(users) == sample.statements == 200
    assert all(user.medium_content == "x" * 1024 for user in users)
