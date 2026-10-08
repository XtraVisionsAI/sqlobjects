"""Memory observations backed by object-lifetime and persisted-data checks.

RSS deltas depend on allocator reuse and may be negative. They are reported, not
used as universal limits or as proof that an object was released.
"""

import asyncio
import gc
import weakref
from contextlib import aclosing

import pytest

from sqlobjects.session import ctx_session
from tests.conftest import User
from tests.performance.test_bulk_perf import rows


async def test_model_instance_memory(benchmark):
    with benchmark.measure("construct_1000_models"):
        users = [User(**data) for data in rows("memory", 1000)]
    references = [weakref.ref(user) for user in users]
    assert len(users) == 1000
    del users
    gc.collect()
    assert all(reference() is None for reference in references)


@pytest.mark.usefixtures("large_dataset")
async def test_query_result_memory(session, benchmark):
    with benchmark.measure("hydrate_10000"):
        users = await User.objects.using(session).all()
    assert len(users) == 10000
    references = [weakref.ref(user) for user in users]
    del users
    gc.collect()
    assert all(reference() is None for reference in references)


@pytest.mark.usefixtures("large_dataset")
@pytest.mark.parametrize("chunk_size", [100, 500, 1000])
async def test_iterator_releases_previous_chunks(session, benchmark, chunk_size):
    """Guard bounded hydration without comparing RSS in a warmed-up process."""
    references = []
    count = 0
    with benchmark.measure(f"stream_{chunk_size}") as sample:
        async with aclosing(User.objects.using(session).order_by("id").iterator(chunk_size=chunk_size)) as stream:
            async for user in stream:
                count += 1
                if count <= chunk_size:
                    references.append(weakref.ref(user))
                elif count == chunk_size + 1:
                    gc.collect()
                    assert all(reference() is None for reference in references)
                assert user.username.startswith("user")
    assert count == 10000
    assert sample.statements == 1


@pytest.mark.usefixtures("large_dataset")
async def test_iterator_close_releases_objects(session, benchmark):
    with benchmark.measure("stream_early_close"):
        async with aclosing(User.objects.using(session).iterator(chunk_size=100)) as stream:
            user = await anext(stream)
            reference = weakref.ref(user)
        del user
        gc.collect()
        assert reference() is None
    assert await User.objects.using(session).count() == 10000


@pytest.mark.parametrize("size", [1000, 5000, 10000])
async def test_bulk_create_memory(session, benchmark, size):
    with benchmark.measure(f"create_{size}_including_input"):
        data = rows("bulk_memory", size)
        assert await User.objects.using(session).bulk_create(data) == size
    assert await User.objects.using(session).count() == size


async def test_bulk_update_and_delete_memory(session, benchmark):
    await User.objects.using(session).bulk_create(rows("update_memory", 5000))
    ids = await User.objects.using(session).values_list("id", flat=True)
    with benchmark.measure("update_5000"):
        assert (
            await User.objects.using(session).bulk_update([{"id": pk, "age": 30, "is_active": False} for pk in ids])
            == 5000
        )
    assert await User.objects.using(session).filter(age=30, is_active=False).count() == 5000
    with benchmark.measure("delete_5000"):
        assert await User.objects.using(session).bulk_delete(ids, id_field="id") == 5000
    assert await User.objects.using(session).count() == 0


@pytest.mark.usefixtures("large_dataset")
async def test_repeated_queryset_does_not_retain_results(session, benchmark):
    query = User.objects.using(session).filter(User.age >= 18)
    for iteration in range(5):
        with benchmark.measure(f"query_{iteration}"):
            users = await query.all()
        assert len(users) == 10000
        reference = weakref.ref(users[0])
        del users
        gc.collect()
        assert reference() is None


async def test_concurrent_bulk_operations_memory(session, benchmark):
    async def create(batch):
        async with ctx_session() as worker:
            return await User.objects.using(worker).bulk_create(rows(f"concurrent_memory_{batch}", 500))

    with benchmark.measure("concurrent_create_5x500"):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(create(i)) for i in range(5)]
    assert [task.result() for task in tasks] == [500] * 5
    assert await User.objects.using(session).count() == 2500


async def test_repeated_crud_releases_models(session, benchmark):
    for iteration in range(10):
        with benchmark.measure(f"crud_cycle_{iteration}"):
            assert await User.objects.using(session).bulk_create(rows(f"cycle_{iteration}", 100)) == 100
            users = await User.objects.using(session).all()
            assert len(users) == 100
            references = [weakref.ref(user) for user in users]
            assert await User.objects.using(session).bulk_delete([user.id for user in users], id_field="id") == 100
            del users
            gc.collect()
            assert all(reference() is None for reference in references)
        assert await User.objects.using(session).count() == 0


@pytest.mark.usefixtures("large_dataset")
async def test_batch_processing_memory(session, benchmark):
    count = 0
    previous_id = None
    with benchmark.measure("page_500"):
        for offset in range(0, 10000, 500):
            users = await User.objects.using(session).order_by("id").limit(500).offset(offset).all()
            assert len(users) == 500
            if previous_id is not None:
                assert users[0].id > previous_id
            previous_id = users[-1].id
            references = [weakref.ref(user) for user in users]
            count += len(users)
            del users
            gc.collect()
            assert all(reference() is None for reference in references)
    assert count == 10000
