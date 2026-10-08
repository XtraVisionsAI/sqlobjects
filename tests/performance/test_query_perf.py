"""Query workloads with deterministic result and SQL-count assertions."""

import asyncio

import pytest

from sqlobjects.expressions import func
from sqlobjects.session import ctx_session
from tests.conftest import Post, PostTag, Tag, User


@pytest.mark.usefixtures("large_dataset")
async def test_simple_query_performance(session, benchmark):
    with benchmark.measure("filter_age_lt_30") as filtered:
        users = await User.objects.using(session).filter(User.age < 30).all()
    with benchmark.measure("count_age_lt_30") as counted:
        count = await User.objects.using(session).filter(User.age < 30).count()
    assert count == len(users) == 2000
    assert all(user.age < 30 for user in users)
    assert filtered.statements == counted.statements == 1


@pytest.mark.usefixtures("large_dataset")
async def test_complex_query_performance(session, benchmark):
    with benchmark.measure("filter_order_limit"):
        users = (
            await User.objects.using(session)
            .filter(User.age >= 25, User.age <= 45, User.is_active == True, User.username.like("%user%"))
            .order_by("-age", "id")
            .limit(100)
            .all()
        )
    assert len(users) == 100
    assert all(user.age == 45 and user.is_active for user in users)
    assert [user.id for user in users] == sorted(user.id for user in users)


@pytest.mark.usefixtures("large_dataset")
async def test_aggregation_query_performance(session, benchmark):
    with benchmark.measure("aggregate") as sample:
        stats = await User.objects.using(session).aggregate(
            total=func.count(), average=User.age.avg(), minimum=User.age.min(), maximum=User.age.max()
        )
    assert stats == {"total": 10000, "average": 44.5, "minimum": 20, "maximum": 69}
    assert sample.statements == 1


@pytest.mark.usefixtures("large_dataset")
async def test_count_ordering(session, benchmark):
    for label, query in (
        ("ordered", User.objects.using(session).order_by("age")),
        ("skip_ordering", User.objects.using(session).skip_default_ordering()),
    ):
        with benchmark.measure(label) as sample:
            assert await query.count() == 10000
        assert sample.statements == 1
        assert "ORDER BY" not in benchmark.statements[-1].upper()


@pytest.mark.usefixtures("complex_relationships")
async def test_select_related_performance(session, benchmark):
    with benchmark.measure("lazy_authors") as lazy:
        posts = await Post.objects.using(session).order_by("id").all()
        authors = [(await post.load_relation("author")).id for post in posts]
    with benchmark.measure("joined_authors") as joined:
        eager = await Post.objects.using(session).select_related("author").order_by("id").all()
        eager_authors = [(await post.load_relation("author")).id for post in eager]
    assert len(posts) == len(eager) == 10
    assert authors == eager_authors == [post.author_id for post in posts]
    assert lazy.statements == 11
    assert joined.statements == 1


@pytest.mark.usefixtures("complex_relationships")
async def test_prefetch_related_performance(session, benchmark):
    with benchmark.measure("lazy_posts") as lazy:
        users = await User.objects.using(session).order_by("id").all()
        posts = [sorted(post.id for post in await user.load_relation("posts")) for user in users]
    with benchmark.measure("prefetched_posts") as prefetched:
        eager = await User.objects.using(session).prefetch_related("posts").order_by("id").all()
        eager_posts = [sorted(post.id for post in await user.load_relation("posts")) for user in eager]
    assert len(users) == len(eager) == 3
    assert posts == eager_posts
    assert sum(map(len, posts)) == 10
    assert lazy.statements == 4
    assert prefetched.statements == 2


async def test_complex_join_performance(session, benchmark, complex_relationships):
    data = complex_relationships
    python_tag = next(tag.id for tag in data["tags"] if tag.name == "python")
    tagged_posts = {item["post_id"] for item in data["associations"] if item["tag_id"] == python_tag}
    expected = {post.author_id for post in data["posts"] if post.id in tagged_posts}
    with benchmark.measure("join_many_to_many"):
        users = (
            await User.objects.using(session)
            .join(Post.__table__, User.id == Post.author_id)
            .join(PostTag.__table__, Post.id == PostTag.post_id)
            .join(Tag.__table__, PostTag.tag_id == Tag.id)
            .filter(Tag.name == "python")
            .distinct()
            .all()
        )
    assert expected
    assert {user.id for user in users} == expected
    assert len(users) == len(expected)


@pytest.mark.usefixtures("large_dataset")
@pytest.mark.parametrize("chunk_size", [100, 500, 1000, 2000])
async def test_iterator_performance(session, benchmark, chunk_size):
    with benchmark.measure(f"iterator_{chunk_size}") as sample:
        names = set()
        count = 0
        async for user in User.objects.using(session).order_by("id").iterator(chunk_size=chunk_size):
            names.add(user.username)
            count += 1
    assert names == {f"user{i}" for i in range(10000)}
    assert count == 10000
    assert sample.statements == 1


@pytest.mark.usefixtures("large_dataset")
@pytest.mark.parametrize("selection", ["only", "defer"])
async def test_field_selection(session, benchmark, selection):
    query = User.objects.using(session).order_by("id")
    with benchmark.measure("full"):
        full = await query.only(*User.__table__.columns.keys()).all()
    partial_query = query.only("id", "username") if selection == "only" else query.defer("bio")
    with benchmark.measure(selection):
        partial = await partial_query.all()
    assert len(full) == len(partial) == 10000
    assert [user.id for user in full] == [user.id for user in partial]
    assert all(user.is_field_loaded("bio") and user.bio == "x" * 256 for user in full)
    assert all(user.is_field_deferred("bio") for user in partial)
    assert "bio" in benchmark.statements[-2] and "bio" not in benchmark.statements[-1]
    if selection == "only":
        assert all(user.is_field_deferred("email") for user in partial)


@pytest.mark.usefixtures("large_dataset")
async def test_concurrent_read_queries(benchmark):
    async def read(batch):
        async with ctx_session() as worker:
            return await User.objects.using(worker).filter(User.age >= 20 + batch * 5, User.age <= 30 + batch * 5).all()

    with benchmark.measure("concurrent_reads_5_workers") as sample:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(read(i)) for i in range(5)]
    for i, task in enumerate(tasks):
        users = task.result()
        assert len(users) == 2200
        assert all(20 + i * 5 <= user.age <= 30 + i * 5 for user in users)
    assert sample.statements == 5


@pytest.mark.usefixtures("large_dataset")
async def test_concurrent_mixed_operations(session, benchmark):
    async def read():
        async with ctx_session() as worker:
            return await User.objects.using(worker).filter(User.age > 30).count()

    async def write(i):
        async with ctx_session() as worker:
            return await User.objects.using(worker).create(username=f"concurrent_{i}", email=f"{i}@example.com", age=25)

    with benchmark.measure("mixed_reads_writes"):
        async with asyncio.TaskGroup() as group:
            readers = [group.create_task(read()) for _ in range(5)]
            writers = [group.create_task(write(i)) for i in range(5)]
    assert [task.result() for task in readers] == [7800] * 5
    assert len({task.result().id for task in writers}) == 5
    assert await User.objects.using(session).count() == 10005


@pytest.mark.usefixtures("large_dataset")
async def test_distinct_query_performance(session, benchmark):
    query = User.objects.using(session).filter(User.age > 20).order_by("id")
    with benchmark.measure("regular"):
        regular = await query.all()
    with benchmark.measure("distinct"):
        distinct = await query.distinct().all()
    assert len(regular) == len(distinct) == 9800
    assert [user.id for user in regular] == [user.id for user in distinct]


@pytest.mark.usefixtures("large_dataset")
@pytest.mark.parametrize("offset", [100, 5000])
async def test_limit_offset_performance(session, benchmark, offset):
    with benchmark.measure(f"offset_{offset}"):
        users = await User.objects.using(session).order_by("username").limit(100).offset(offset).all()
    expected = sorted(f"user{i}" for i in range(10000))[offset : offset + 100]
    assert [user.username for user in users] == expected


@pytest.mark.usefixtures("large_dataset")
async def test_expression_system_performance(session, benchmark):
    with benchmark.measure("two_queries") as multiple:
        stats = await User.objects.using(session).aggregate(avg_age=User.age.avg())
        old = await User.objects.using(session).filter(User.age > stats["avg_age"]).order_by("id").all()
    with benchmark.measure("scalar_subquery") as single:
        average = User.objects.using(session).aggregate(avg_age=User.age.avg()).scalar_subquery()
        new = await User.objects.using(session).filter(User.age > average).order_by("id").all()
    assert len(old) == len(new) == 5000
    assert [user.id for user in old] == [user.id for user in new]
    assert multiple.statements == 2
    assert single.statements == 1


@pytest.mark.usefixtures("large_dataset")
async def test_query_terminals_benchmark(session, benchmark):
    with benchmark.measure("exists") as exists:
        assert await User.objects.using(session).filter(User.age > 50).exists()
    with benchmark.measure("first") as first:
        user = await User.objects.using(session).order_by("age", "username").first()
    assert user is not None and user.age == 20 and user.username == "user0"
    assert exists.statements == first.statements == 1
