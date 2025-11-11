"""SQLObjects Test Configuration and Universal Fixtures

This module provides universal fixtures for the SQLObjects test suite:
- Universal Model Definitions: Standard test models covering all field types and relationship patterns
- Universal Database Configuration: Multi-database support with standardized configuration
- Universal Data Preparation: Standard test datasets and large datasets for performance testing
- Universal Data Cleanup: Automated cleanup and isolation mechanisms
"""

from datetime import datetime

import pytest

from sqlobjects.database import close_db, create_tables, init_db
from sqlobjects.expressions import func
from sqlobjects.fields import (
    BooleanColumn,
    Column,
    IntegerColumn,
    Related,
    StringColumn,
    column,
    foreign_key,
    identity,
    relationship,
)
from sqlobjects.model import ObjectModel
from sqlobjects.session import ctx_session
from tests.test_config import TestDatabaseConfig


# ============================================================================
# Universal Model Definitions - All field types and relationship patterns
# ============================================================================


class TestModel(ObjectModel):
    """Common test base class - all test models share the same registry"""

    __abstract__ = True
    __test__ = False


class User(TestModel):
    """Standard user model covering basic field types"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())
    bio: Column[str] = column(type="text", deferred=True)

    # Relationships
    posts: Related[list["Post"]] = relationship("Post", back_populates="author")
    profile: Related["Profile"] = relationship("Profile", back_populates="user", uselist=False)


user = User()
print(type(user.posts))
print(type(user.profile))


class Post(TestModel):
    """Post model for testing foreign key relationships"""

    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text")
    author_id: Column[int] = foreign_key("users.id", ondelete="CASCADE")
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())

    # Relationships
    author = relationship("User", back_populates="posts")
    tags = relationship("Tag", secondary="post_tags", back_populates="posts")


class Tag(TestModel):
    """Tag model for testing many-to-many relationships"""

    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=50, unique=True)

    # Relationships
    posts = relationship("Post", secondary="post_tags", back_populates="tags")


class Profile(TestModel):
    """User profile model for testing nested relationships"""

    id: Column[int] = identity()
    user_id: Column[int] = foreign_key("users.id", unique=True, ondelete="CASCADE")
    full_name: Column[str] = StringColumn(length=100)
    location: Column[str] = StringColumn(length=100, nullable=True)
    website: Column[str] = StringColumn(length=200, nullable=True)

    # Relationships
    user = relationship("User", back_populates="profile")


class PostTag(TestModel):
    """Post-tag association for testing composite primary keys"""

    post_id: Column[int] = foreign_key("posts.id", primary_key=True, ondelete="CASCADE")
    tag_id: Column[int] = foreign_key("tags.id", primary_key=True, ondelete="CASCADE")

    class Config:
        table_name = "post_tags"


# ============================================================================
# Universal Database Configuration - Multi-database support
# ============================================================================


# Database configuration - can be overridden via pytest command line
def pytest_addoption(parser):
    """Add command line options for database selection"""
    parser.addoption(
        "--db",
        action="store",
        default="sqlite",
        choices=["sqlite", "postgresql", "mysql"],
        help="Database type to use for testing (default: sqlite)",
    )


@pytest.fixture(scope="session")
def db_type(request):
    """Get database type from command line or default to sqlite"""
    return request.config.getoption("--db")


@pytest.fixture
async def test_db(db_type):
    """Universal database fixture supporting multiple databases

    Usage:
    - Default SQLite: pytest
    - PostgreSQL: pytest --db=postgresql
    - MySQL: pytest --db=mysql

    Environment variables for database URLs:
    - POSTGRESQL_TEST_URL (default: postgresql+asyncpg://test:test@localhost/tests)
    - MYSQL_TEST_URL (default: mysql+asyncmy://test:test@localhost/tests)
    """
    config = TestDatabaseConfig.get_config(db_type)

    print(f"\n🗄️  Testing with {db_type.upper()} database: {config['url']}")

    # 使用统一的池配置
    await init_db(config["url"], **config["pool_config"])
    await create_tables(TestModel)

    try:
        yield db_type
    finally:
        await close_db()


@pytest.fixture
async def session(test_db):
    """Universal session fixture providing database session"""
    # Tables already created at session level, just provide session
    async with ctx_session() as session:
        yield session


# ============================================================================
# Universal Data Preparation - Standard test datasets
# ============================================================================


@pytest.fixture
async def sample_users(session):
    """Standard user dataset - 3 users covering basic test scenarios"""
    users_data = [
        {"username": "alice", "email": "alice@example.com", "age": 25},
        {"username": "bob", "email": "bob@example.com", "age": 30},
        {"username": "charlie", "email": "charlie@example.com", "age": 35},
    ]
    await User.objects.using(session).bulk_create(users_data)

    # Get created users
    users = (
        await User.objects.using(session)
        .filter(User.username.in_(["alice", "bob", "charlie"]))
        .order_by("username")
        .all()
    )

    # Create profiles for nested relationship testing
    profiles_data = [
        {"user_id": users[0].id, "full_name": "Alice Smith", "location": "New York"},
        {"user_id": users[1].id, "full_name": "Bob Johnson", "location": "California"},
        {"user_id": users[2].id, "full_name": "Charlie Brown", "location": "Texas"},
    ]
    await Profile.objects.using(session).bulk_create(profiles_data)

    return (
        await User.objects.using(session)
        .filter(User.username.in_(["alice", "bob", "charlie"]))
        .order_by("username")
        .all()
    )


@pytest.fixture
async def sample_posts(session, sample_users):
    """Standard post dataset - 10 posts for relationship query testing"""
    posts_data = [
        {"title": f"Post {i}", "content": f"Content for post {i}", "author_id": sample_users[i % len(sample_users)].id}
        for i in range(10)
    ]

    await Post.objects.using(session).bulk_create(posts_data)
    return await Post.objects.using(session).filter(Post.title.like("Post %")).order_by("title").all()


@pytest.fixture
async def sample_tags(session):
    """Standard tag dataset - 5 tags for many-to-many relationship testing"""
    tags_data = [
        {"name": "python"},
        {"name": "database"},
        {"name": "async"},
        {"name": "performance"},
        {"name": "testing"},
    ]
    await Tag.objects.using(session).bulk_create(tags_data)
    return (
        await Tag.objects.using(session)
        .filter(Tag.name.in_(["python", "database", "async", "performance", "testing"]))
        .order_by("name")
        .all()
    )


@pytest.fixture
async def large_dataset(session):
    """Large dataset for performance testing (10,000 records)"""
    users_data = [{"username": f"user{i}", "email": f"user{i}@example.com", "age": 20 + (i % 50)} for i in range(10000)]
    await User.objects.using(session).bulk_create(users_data)
    return await User.objects.using(session).filter(User.username.like("user%")).all()


@pytest.fixture
async def complex_relationships(session, sample_users, sample_posts, sample_tags):
    """Complex relationship dataset for relationship query and prefetch testing"""
    # Create post-tag associations
    associations = []
    for i, post in enumerate(sample_posts):
        # Each post has 2-3 tags
        tag_count = 2 + (i % 2)
        for j in range(tag_count):
            tag_index = (i + j) % len(sample_tags)
            associations.append({"post_id": post.id, "tag_id": sample_tags[tag_index].id})

    await PostTag.objects.using(session).bulk_create(associations)
    return {"users": sample_users, "posts": sample_posts, "tags": sample_tags, "associations": associations}


# ============================================================================
# Universal Data Cleanup - Automated cleanup mechanisms
# ============================================================================


@pytest.fixture(autouse=True)
async def clean_db(test_db):
    """Automatic data cleanup after each test

    Uses autouse=True to ensure automatic cleanup after each test
    Deletes data from tables (not table structure) in dependency order
    Table structures remain intact throughout the test session
    """
    yield

    async with ctx_session() as db_session:
        # Delete data from tables in dependency order (child tables first)
        tables_to_clean = [PostTag.__table__, Profile.__table__, Post.__table__, Tag.__table__, User.__table__]

        for table in tables_to_clean:
            try:
                await db_session.execute(table.delete())
            except Exception:  # noqa
                # Ignore errors for tables that don't exist yet
                pass

        try:
            await db_session.commit()
        except Exception:  # noqa
            await db_session.rollback()

        # Get all tables from metadata
        metadata = User.__table__.metadata
        all_tables = list(metadata.tables.values())

        # Sort tables by foreign key dependencies (child tables first)
        tables_with_fks = []
        tables_without_fks = []

        for table in all_tables:
            has_fk = any(col.foreign_keys for col in table.columns)
            if has_fk:
                tables_with_fks.append(table)
            else:
                tables_without_fks.append(table)

        # Clean child tables first, then parent tables
        tables_to_clean = tables_with_fks + tables_without_fks

        for table in tables_to_clean:
            try:
                await db_session.execute(table.delete())  # Deletes data, not table structure
            except Exception:
                # Skip tables that don't exist
                pass
        await db_session.commit()


@pytest.fixture
async def isolated_session():
    """Isolated session for tests requiring complete isolation

    Creates independent session unaffected by other tests
    Suitable for transaction testing, concurrency testing, etc.
    """
    async with ctx_session() as db_session:
        yield db_session


# ============================================================================
# Testing Tool Fixtures - Test assistance utilities
# ============================================================================


@pytest.fixture
def performance_monitor():
    """Performance monitoring tool for measuring execution time"""
    import time

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None

        def start(self):
            self.start_time = time.perf_counter()

        def stop(self):
            if self.start_time is None:
                return {"execution_time": 0.0}
            end_time = time.perf_counter()
            return {"execution_time": end_time - self.start_time}

    return PerformanceMonitor()


@pytest.fixture
def query_counter():
    """Query counter for monitoring SQL query count"""

    class QueryCounter:
        def __init__(self):
            self.count = 0

        def __enter__(self):
            self.count = 0
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def increment(self):
            self.count += 1

    return QueryCounter()
