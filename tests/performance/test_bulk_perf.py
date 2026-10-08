"""Bulk workloads: report resource use and verify persisted results."""

import asyncio
from typing import cast

import pytest
from sqlalchemy import event

from sqlobjects.database import get_database
from sqlobjects.session import ctx_session
from tests.conftest import User


def rows(prefix, count, age=25):
    return [{"username": f"{prefix}_{i}", "email": f"{prefix}{i}@example.com", "age": age} for i in range(count)]


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_individual_and_bulk_operations(session, benchmark, operation):
    """Compare public APIs without assuming a speedup on every driver."""
    if operation == "create":
        with benchmark.measure("individual_create"):
            for data in rows("individual", 100):
                await User.objects.using(session).create(**data)
        with benchmark.measure("bulk_create"):
            count = await User.objects.using(session).bulk_create(rows("bulk", 100))
        assert count == 100
        assert await User.objects.using(session).count() == 200
        return

    result = await User.objects.using(session).bulk_create(rows("existing", 200), return_objects=True)
    assert result.success_count == 200
    users = cast(list[User], result.objects)
    with benchmark.measure(f"individual_{operation}"):
        for user in users[:100]:
            if operation == "update":
                user.age = 30
                await user.save()
            else:
                await user.delete()
    with benchmark.measure(f"bulk_{operation}"):
        if operation == "update":
            count = await User.objects.using(session).bulk_update(
                [{"id": user.id, "age": 30} for user in users[100:]], match_fields=["id"]
            )
        else:
            count = await User.objects.using(session).bulk_delete([user.id for user in users[100:]], id_field="id")
    assert count == 100
    assert await User.objects.using(session).count() == (200 if operation == "update" else 0)
    if operation == "update":
        assert await User.objects.using(session).filter(age=30).count() == 200


@pytest.mark.parametrize("size", [100, 500, 1000, 2000, 5000, 10000])
async def test_bulk_create_scalability(session, benchmark, size):
    data = rows("scale", size)
    with benchmark.measure(f"create_{size}"):
        count = await User.objects.using(session).bulk_create(data)
    assert count == size
    assert await User.objects.using(session).count() == size


@pytest.mark.parametrize("batch_size", [100, 500, 1000])
async def test_bulk_create_batch_size(session, benchmark, batch_size):
    data = rows("batch", 1000)
    with benchmark.measure(f"batch_size_{batch_size}"):
        count = await User.objects.using(session).bulk_create(data, batch_size=batch_size)
    assert count == 1000
    assert set(await User.objects.using(session).values_list("username", flat=True)) == {
        item["username"] for item in data
    }


@pytest.mark.parametrize("size,fields", [(1000, ["age"]), (5000, ["age", "is_active"])])
async def test_bulk_update_large_dataset(session, benchmark, size, fields):
    await User.objects.using(session).bulk_create(rows("update", size))
    ids = await User.objects.using(session).order_by("id").values_list("id", flat=True)
    values = {"age": 30, "is_active": False}
    updates = [{"id": pk, **{name: values[name] for name in fields}} for pk in ids]
    with benchmark.measure(f"update_{size}_{len(fields)}_fields"):
        count = await User.objects.using(session).bulk_update(updates, match_fields=["id"])
    assert count == size
    assert await User.objects.using(session).filter(age=30, is_active=("is_active" not in fields)).count() == size
    assert set(await User.objects.using(session).values_list("email", flat=True)) == {
        item["email"] for item in rows("update", size)
    }


async def test_bulk_delete_large_dataset(session, benchmark):
    await User.objects.using(session).bulk_create(rows("delete", 10000))
    ids = await User.objects.using(session).values_list("id", flat=True)
    with benchmark.measure("delete_10000"):
        count = await User.objects.using(session).bulk_delete(ids, id_field="id")
    assert count == 10000
    assert await User.objects.using(session).count() == 0


async def test_concurrent_bulk_creates(session, benchmark):
    async def create_batch(batch_id):
        async with ctx_session() as worker:
            return await User.objects.using(worker).bulk_create(rows(f"concurrent_{batch_id}", 100))

    with benchmark.measure("concurrent_create_5x100"):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(create_batch(i)) for i in range(5)]
    assert [task.result() for task in tasks] == [100] * 5
    assert await User.objects.using(session).count() == 500


async def test_mixed_concurrent_operations(session, benchmark):
    await User.objects.using(session).bulk_create(rows("mixed", 200))
    ids = await User.objects.using(session).order_by("id").values_list("id", flat=True)
    await session.commit()

    async def create():
        async with ctx_session() as worker:
            return await User.objects.using(worker).bulk_create(rows("new", 50, age=30))

    async def update():
        async with ctx_session() as worker:
            return await User.objects.using(worker).bulk_update([{"id": pk, "age": 35} for pk in ids[:50]])

    async def delete():
        async with ctx_session() as worker:
            return await User.objects.using(worker).bulk_delete(ids[50:100], id_field="id")

    with benchmark.measure("concurrent_create_update_delete"):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(operation()) for operation in (create, update, delete)]
    assert [task.result() for task in tasks] == [50, 50, 50]
    assert await User.objects.using(session).count() == 200
    assert await User.objects.using(session).filter(age=35).count() == 50
    assert await User.objects.using(session).filter(User.id.in_(ids[50:100])).count() == 0


async def test_database_connection_reuse(session, benchmark):
    """Sequential batches in one transaction use one checked-out connection."""
    engine = get_database().engine.sync_engine
    checkouts = []

    def checkout(connection, record, proxy):
        checkouts.append(id(connection))

    event.listen(engine, "checkout", checkout)
    try:
        with benchmark.measure("sequential_create_10x100"):
            for i in range(10):
                assert await User.objects.using(session).bulk_create(rows(f"connection_{i}", 100)) == 100
        assert len(checkouts) == 1
    finally:
        event.remove(engine, "checkout", checkout)
    assert await User.objects.using(session).count() == 1000


async def test_transaction_efficiency(session, benchmark):
    with benchmark.measure("create_update_commit"):
        assert await User.objects.using(session).bulk_create(rows("transaction", 2000)) == 2000
        ids = await User.objects.using(session).order_by("id").limit(500).values_list("id", flat=True)
        assert await User.objects.using(session).bulk_update([{"id": pk, "age": 30} for pk in ids]) == 500
        await session.commit()
    async with ctx_session() as reader:
        assert await User.objects.using(reader).count() == 2000
        assert await User.objects.using(reader).filter(age=30).count() == 500


async def test_bulk_crud_benchmark(session, benchmark):
    """Report each phase separately for repeatable comparisons across revisions."""
    with benchmark.measure("create_1000"):
        assert await User.objects.using(session).bulk_create(rows("phases", 1000)) == 1000
    ids = await User.objects.using(session).values_list("id", flat=True)
    with benchmark.measure("update_1000"):
        assert await User.objects.using(session).bulk_update([{"id": pk, "age": 30} for pk in ids]) == 1000
    assert await User.objects.using(session).filter(age=30).count() == 1000
    with benchmark.measure("delete_1000"):
        assert await User.objects.using(session).bulk_delete(ids, id_field="id") == 1000
    assert await User.objects.using(session).count() == 0
