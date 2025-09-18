# SQLObjects Test Suite Design

## Overview

Comprehensive test design for SQLObjects, focusing on practical performance testing and multi-database compatibility.

## Running Tests

### Unified Test Runner

Use the unified test runner `run_tests.py` for all testing needs:

```bash
# Run all tests
python run_tests.py --all

# Run specific test categories
python run_tests.py --unit
python run_tests.py --integration
python run_tests.py --performance

# Run specific feature tests
python run_tests.py --deferred      # Deferred field tests
python run_tests.py --bulk          # Bulk operation tests
python run_tests.py --relationships # Relationship tests
python run_tests.py --signals       # Signal tests

# Special modes
python run_tests.py --quick         # Quick smoke tests
python run_tests.py --ci            # CI mode with coverage

# Test execution options
python run_tests.py --all --coverage    # With coverage report
python run_tests.py --all --verbose     # Verbose output
python run_tests.py --all --parallel 4  # Parallel execution
python run_tests.py --all --fast        # Skip slow tests
```

### Using Makefile

Convenient shortcuts via Makefile:

```bash
make test              # Run all tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-performance  # Performance tests only
make test-quick        # Quick smoke tests
make test-ci           # CI mode with coverage
make test-coverage     # Tests with coverage report

# Specific feature tests
make test-deferred     # Deferred field tests
make test-bulk         # Bulk operation tests
make test-relationships # Relationship tests
make test-signals      # Signal tests

# Code quality
make lint              # Run linting
make format            # Format code
make type-check        # Type checking
make check             # All quality checks + quick tests
```

### Direct pytest Usage

```bash
# Run all tests with pytest directly
uv run pytest tests/

# Run specific test files
uv run pytest tests/unit/test_model_basic.py
uv run pytest tests/integration/test_crud.py

# Run with markers
uv run pytest -m "unit"
uv run pytest -m "integration"
uv run pytest -m "performance"

# Run with coverage
uv run pytest --cov=sqlobjects --cov-report=html
```

## Design Principles

1. **Comprehensive Coverage** - Test all documented features and edge cases
2. **Performance Focus** - Validate performance claims (10-100x improvements)
3. **Multi-Database Support** - Test PostgreSQL, MySQL, and SQLite compatibility
4. **Real-World Scenarios** - Test practical usage patterns
5. **Unified Test Runner** - Single entry point for all test execution needs

## Test Architecture

### Directory Structure

```
tests/
├── conftest.py                 # Universal fixtures and test models
├── unit/                       # Fast, isolated component tests
│   ├── test_fields.py          # Field system and validation
│   ├── test_model_basic.py     # Basic model functionality
│   ├── test_queries.py         # Query building and execution
│   ├── test_validation.py      # Validation system
│   └── test_deferred_proxies.py # Deferred field and relationship proxy tests
├── integration/                # Component interaction tests
│   ├── test_crud.py            # CRUD operations integration
│   ├── test_relationships.py   # Relationship queries and loading
│   ├── test_signals.py         # Signal system integration
│   ├── test_bulk_operations.py # Bulk operations integration
│   └── test_deferred_loading.py # Deferred field loading integration tests
└── performance/                # Performance benchmarks
    ├── test_bulk_perf.py       # Bulk operations performance
    ├── test_query_perf.py      # Query performance and caching
    ├── test_memory_usage.py    # Memory management and iterators
    └── test_deferred_performance.py # Deferred field performance and scalability
```

## Universal Fixtures (conftest.py)

### Design Philosophy

The `conftest.py` module provides **universal fixtures** with high reusability across all test modules:

- **Universal Model Definitions**: Standard test models covering all field types and relationship patterns
- **Universal Database Configuration**: Multi-database support with standardized configuration
- **Universal Data Preparation**: Standard test datasets and large datasets for performance testing
- **Universal Data Cleanup**: Automated cleanup and isolation mechanisms

### Core Responsibilities

#### 1. Test Model Definitions

```python
# Standard models covering all field types and relationships
class User(ObjectModel):
    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())
    bio: Column[str] = column(type="text", deferred=True)

class Post(ObjectModel):
    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text")
    author_id: Column[int] = foreign_key("users.id")

class Tag(ObjectModel):
    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=50, unique=True)

class PostTag(ObjectModel):  # Many-to-many relationship
    post_id: Column[int] = foreign_key("posts.id", primary_key=True)
    tag_id: Column[int] = foreign_key("tags.id", primary_key=True)
```

#### 2. Database Configuration

```python
@pytest.fixture(scope="session", params=["sqlite"])
async def test_db(request):
    """Universal database fixture supporting multiple databases"""
    db_type = request.param
    
    if db_type == "sqlite":
        db_url = "sqlite:///:memory:"  # Fast in-memory database
    elif db_type == "postgresql":
        db_url = os.getenv("POSTGRESQL_TEST_URL", "postgresql://test:test@localhost/test_db")
    elif db_type == "mysql":
        db_url = os.getenv("MYSQL_TEST_URL", "mysql://test:test@localhost/test_db")
    
    await init_db(db_url)
    yield db_type
    await close_db()

@pytest.fixture
async def session(test_db):
    """Universal session fixture"""
    async with ctx_session() as session:
        yield session
```

#### 3. Data Preparation Fixtures

```python
@pytest.fixture
async def sample_users(session):
    """Standard user dataset - 3 users for basic test scenarios"""
    users_data = [
        {"username": "alice", "email": "alice@example.com", "age": 25},
        {"username": "bob", "email": "bob@example.com", "age": 30},
        {"username": "charlie", "email": "charlie@example.com", "age": 35},
    ]
    return await User.objects.using(session).bulk_create(users_data)

@pytest.fixture
async def large_dataset(session):
    """Large dataset for performance testing (10,000 records)"""
    users_data = [
        {"username": f"user{i}", "email": f"user{i}@example.com", "age": 20 + (i % 50)}
        for i in range(10000)
    ]
    return await User.objects.using(session).bulk_create(users_data)

@pytest.fixture
async def complex_relationships(session, sample_users, sample_posts, sample_tags):
    """Complex relationship dataset for relationship query testing"""
    # Create post-tag associations
    associations = []
    for i, post in enumerate(sample_posts):
        tag_count = 2 + (i % 2)  # 2-3 tags per post
        for j in range(tag_count):
            tag_index = (i + j) % len(sample_tags)
            associations.append({"post_id": post.id, "tag_id": sample_tags[tag_index].id})
    
    await PostTag.objects.using(session).bulk_create(associations)
    return {"users": sample_users, "posts": sample_posts, "tags": sample_tags}
```

#### 4. Automated Cleanup

```python
@pytest.fixture(autouse=True)
async def clean_db(test_db):
    """Automatic data cleanup after each test"""
    yield
    
    async with ctx_session() as db_session:
        # Clean tables in dependency order (child tables first)
        tables_to_clean = [PostTag.__table__, Post.__table__, Tag.__table__, User.__table__]
        
        for table in tables_to_clean:
            await db_session.execute(table.delete())
        await db_session.commit()
```

#### 5. Testing Tools

```python
@pytest.fixture
def performance_monitor():
    """Performance monitoring tool"""
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
```

### Fixture Usage Examples

#### Basic Testing

```python
async def test_user_crud_operations(session, sample_users):
    """Test basic CRUD operations using standard fixtures"""
    user = sample_users[0]
    assert user.username == "alice"
    
    # Update operation
    user.age = 26
    await user.save()
    
    # Verify update
    updated_user = await User.objects.using(session).get(User.id == user.id)
    assert updated_user.age == 26
```

#### Performance Testing

```python
async def test_bulk_operations_performance(session, large_dataset, performance_monitor):
    """Test bulk operations performance using large dataset"""
    performance_monitor.start()
    
    await User.objects.using(session).filter(User.age > 30).update({"is_active": False})
    
    metrics = performance_monitor.stop()
    assert metrics["execution_time"] < 5.0  # Complete within 5 seconds
```

#### Multi-Database Testing

```python
async def test_cross_database_compatibility(test_db, session, sample_users):
    """Test cross-database compatibility"""
    count = await User.objects.using(session).count()
    assert count == 3
    
    # Database-specific functionality
    if test_db == "postgresql":
        # PostgreSQL-specific tests
        pass
    elif test_db == "mysql":
        # MySQL-specific tests
        pass
```

### Configuration

#### pytest Configuration

```toml
# pyproject.toml configuration
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = [
    "--strict-markers",
    "-v"
]
markers = [
    "unit: Unit tests for individual components",
    "integration: Integration tests with real database", 
    "performance: Performance and benchmarking tests",
    "slow: Tests that take longer than 5 seconds",
    "postgresql: PostgreSQL-specific tests",
    "mysql: MySQL-specific tests",
    "sqlite: SQLite-specific tests"
]
```

## Core Test Implementation

### 1. Field System Tests (`test_fields.py`)

```python
import pytest
from sqlobjects.fields import column, StringColumn, IntegerColumn, identity, computed
from sqlobjects.model import ObjectModel
from sqlobjects.validators import validate_email, validate_length

class TestFieldDefinition:
    """Test field definition and type system"""
    
    def test_column_function_basic(self):
        """Test column() function with type parameter"""
        field = column(type="string", length=100)
        assert field.column.type.length == 100
    
    def test_shortcut_classes(self):
        """Test field shortcut classes"""
        name_field = StringColumn(length=50)
        age_field = IntegerColumn()
        
        assert name_field.column.type.length == 50
        assert isinstance(age_field.column.type, sa.Integer)
    
    def test_init_parameter_intelligence(self):
        """Test automatic init parameter handling"""
        # Primary key fields should have init=False automatically
        id_field = column(type="integer", primary_key=True)
        assert id_field.column.info["_codegen"]["init"] is False
        
        # Server default fields should have init=False automatically
        created_field = column(type="datetime", server_default=func.now())
        assert created_field.column.info["_codegen"]["init"] is False
        
        # Regular fields should have init=True by default
        name_field = column(type="string")
        assert name_field.column.info["_codegen"]["init"] is True

class TestFieldValidation:
    """Test field-level validation"""
    
    def test_field_validators(self):
        """Test field validators parameter"""
        field = column(type="string", validators=[validate_email()])
        validators = field.column.info["_enhanced"]["validators"]
        assert len(validators) == 1
    
    def test_multiple_validators(self):
        """Test combining multiple validators"""
        field = column(type="string", validators=[
            validate_length(3, 50),
            validate_email()
        ])
        validators = field.column.info["_enhanced"]["validators"]
        assert len(validators) == 2

class TestAdvancedFields:
    """Test advanced field types"""
    
    def test_identity_fields(self):
        """Test identity() shortcut"""
        id_field = identity()
        assert id_field.column.autoincrement is True
        assert id_field.column.primary_key is True
        assert id_field.column.info["_codegen"]["init"] is False
    
    def test_computed_fields(self):
        """Test computed() shortcut"""
        computed_field = computed("first_name || ' ' || last_name", column_type="string")
        assert computed_field.column.computed is not None
        assert computed_field.column.info["_codegen"]["init"] is False
    
    def test_deferred_fields(self):
        """Test deferred loading configuration"""
        field = column(type="text", deferred=True, deferred_group="details")
        assert field.column.info["_enhanced"]["deferred"] is True
        assert field.column.info["_enhanced"]["deferred_group"] == "details"
```

### 2. Model System Tests (`test_model_basic.py`)

```python
import pytest
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, identity

class User(ObjectModel):
    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=50)
    age: Column[int] = IntegerColumn(nullable=True)

class TestModelCreation:
    """Test model definition and metadata"""
    
    def test_model_definition(self):
        """Test automatic table generation"""
        assert hasattr(User, '__table__')
        assert User.__table__.name == 'users'  # Auto pluralization
        assert 'id' in User.__table__.columns
        assert 'name' in User.__table__.columns
        assert 'age' in User.__table__.columns
    
    def test_primary_key_detection(self):
        """Test automatic primary key handling"""
        pk_columns = [col for col in User.__table__.columns if col.primary_key]
        assert len(pk_columns) == 1
        assert pk_columns[0].name == 'id'

class TestInstanceCreation:
    """Test instance creation and from_dict integration"""
    
    def test_constructor_behavior(self):
        """Test constructor with init parameter handling"""
        # Should only accept init=True fields
        user = User(name="John", age=25)
        assert user.name == "John"
        assert user.age == 25
        
        # id field (init=False) should not be in constructor
        with pytest.raises(TypeError):
            User(id=1, name="John", age=25)
    
    def test_from_dict_integration(self):
        """Test from_dict method handles all field types"""
        data = {"id": 1, "name": "Jane", "age": 30}
        user = User.from_dict(data)
        
        assert user.id == 1
        assert user.name == "Jane"
        assert user.age == 30
        
        # Verify dirty fields are cleared after from_dict
        dirty_fields = user._state_manager.get("dirty_fields", set())
        assert len(dirty_fields) == 0
    
    def test_dirty_field_tracking(self):
        """Test automatic dirty field tracking"""
        user = User(name="Original", age=25)
        
        # Constructor should mark fields as dirty
        dirty_fields = user._state_manager.get("dirty_fields", set())
        assert "name" in dirty_fields
        assert "age" in dirty_fields
        
        # Clear dirty fields
        user._state_manager.get("dirty_fields").clear()
        
        # Modifying field should mark as dirty
        user.name = "Modified"
        dirty_fields = user._state_manager.get("dirty_fields", set())
        assert "name" in dirty_fields
        assert "age" not in dirty_fields

class TestModelOperations:
    """Test model operations and smart detection"""
    
    def test_save_operation_detection(self):
        """Test save() method CREATE/UPDATE detection"""
        user = User(name="Test", age=20)
        
        # New instance should trigger CREATE
        assert not user._has_primary_key_values()
        
        # After setting primary key should trigger UPDATE
        user.id = 1
        assert user._has_primary_key_values()
    
    def test_detached_instance_handling(self):
        """Test operations on detached instances"""
        # Detached instance with primary key
        detached_user = User.from_dict({"id": 1, "name": "Detached", "age": 30})
        
        # Should be recognized as existing instance
        assert detached_user._has_primary_key_values()
        
        # Should support operations (would use merge strategy)
        assert hasattr(detached_user, 'save')
        assert hasattr(detached_user, 'delete')
```

### 3. Query System Tests (`test_queries.py`)

```python
import pytest
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, identity
from sqlobjects.queries import Q
from sqlobjects.expressions import func

class TestQueryBuilding:
    """Test query building and chaining"""
    
    async def test_basic_filtering(self, session, sample_users):
        """Test basic filter operations"""
        # Simple equality filter
        alice = await User.objects.using(session).filter(User.username == "alice").first()
        assert alice.username == "alice"
        
        # Multiple filters
        young_users = await User.objects.using(session).filter(
            User.age < 30, User.is_active == True
        ).all()
        assert len(young_users) == 1
        assert young_users[0].username == "alice"
    
    async def test_q_object_combinations(self, session, sample_users):
        """Test Q object logical combinations"""
        # OR combination
        users = await User.objects.using(session).filter(
            Q(User.username == "alice") | Q(User.username == "bob")
        ).all()
        assert len(users) == 2
        
        # AND combination with OR
        users = await User.objects.using(session).filter(
            Q(User.age >= 25) & (Q(User.username == "alice") | Q(User.username == "charlie"))
        ).all()
        assert len(users) == 2
    
    async def test_ordering_and_pagination(self, session, sample_users):
        """Test ordering and pagination"""
        # Order by age descending
        users = await User.objects.using(session).order_by("-age").all()
        assert users[0].age == 35  # charlie
        assert users[1].age == 30  # bob
        assert users[2].age == 25  # alice
        
        # Pagination
        first_page = await User.objects.using(session).order_by("age").limit(2).all()
        assert len(first_page) == 2
        assert first_page[0].age == 25
        
        second_page = await User.objects.using(session).order_by("age").offset(2).limit(2).all()
        assert len(second_page) == 1
        assert second_page[0].age == 35

class TestQueryExecution:
    """Test query execution methods"""
    
    async def test_execution_methods(self, session, sample_users):
        """Test various query execution methods"""
        # Count
        count = await User.objects.using(session).count()
        assert count == 3
        
        # Exists
        exists = await User.objects.using(session).filter(User.username == "alice").exists()
        assert exists is True
        
        # First/Last
        first = await User.objects.using(session).order_by("age").first()
        assert first.age == 25
        
        last = await User.objects.using(session).order_by("age").last()
        assert last.age == 35
    
    async def test_aggregation(self, session, sample_users):
        """Test aggregation functions"""
        # Basic aggregation
        stats = await User.objects.using(session).aggregate(
            avg_age=func.avg(User.age),
            max_age=func.max(User.age),
            min_age=func.min(User.age),
            total_users=func.count()
        )
        
        assert stats["avg_age"] == 30.0
        assert stats["max_age"] == 35
        assert stats["min_age"] == 25
        assert stats["total_users"] == 3

class TestBulkOperations:
    """Test bulk operations performance"""
    
    async def test_bulk_create_performance(self, session, performance_monitor):
        """Test bulk create performance"""
        data = [{"name": f"User{i}", "age": 20 + (i % 50)} for i in range(1000)]
        
        performance_monitor.start()
        users = await User.objects.using(session).bulk_create(data)
        metrics = performance_monitor.stop()
        
        assert len(users) == 1000
        assert metrics["execution_time"] < 2.0  # Should complete within 2 seconds
    
    async def test_bulk_update_performance(self, session, large_dataset, performance_monitor):
        """Test bulk update performance"""
        performance_monitor.start()
        
        updated_count = await User.objects.using(session).filter(
            User.age > 40
        ).update({"is_active": False})
        
        metrics = performance_monitor.stop()
        
        assert updated_count > 0
        assert metrics["execution_time"] < 1.0  # Should complete within 1 second
```

### 4. Performance Tests (`test_performance.py`)

```python
import pytest
import asyncio
from sqlobjects.model import ObjectModel

class TestPerformanceBenchmarks:
    """Performance benchmark tests"""
    
    async def test_bulk_vs_individual_creates(self, session, performance_monitor):
        """Compare bulk create vs individual creates"""
        data = [{"name": f"User{i}", "age": 25} for i in range(100)]
        
        # Individual creates
        performance_monitor.start()
        for item in data:
            await User.objects.using(session).create(**item)
        individual_time = performance_monitor.stop()["execution_time"]
        
        # Clear data
        await User.objects.using(session).delete()
        
        # Bulk create
        performance_monitor.start()
        await User.objects.using(session).bulk_create(data)
        bulk_time = performance_monitor.stop()["execution_time"]
        
        # Bulk should be at least 5x faster
        assert bulk_time < individual_time / 5
    
    async def test_memory_efficiency_iterator(self, session, large_dataset):
        """Test memory efficiency of iterator pattern"""
        processed_count = 0
        
        # Process large dataset with iterator (should not load all into memory)
        async for user in User.objects.using(session).iterator(chunk_size=100):
            processed_count += 1
            # Simulate processing
            _ = user.username.upper()
        
        assert processed_count == 10000
    
    async def test_relationship_loading_performance(self, session, complex_relationships, performance_monitor):
        """Test relationship loading performance"""
        # Test N+1 query problem prevention
        performance_monitor.start()
        
        # With select_related (should use JOIN)
        posts = await Post.objects.using(session).select_related("author").all()
        for post in posts:
            _ = post.author.username  # Should not trigger additional queries
        
        select_related_time = performance_monitor.stop()["execution_time"]
        
        # Without select_related (N+1 queries)
        performance_monitor.start()
        
        posts = await Post.objects.using(session).all()
        for post in posts:
            author = await User.objects.using(session).get(User.id == post.author_id)
            _ = author.username
        
        n_plus_one_time = performance_monitor.stop()["execution_time"]
        
        # select_related should be significantly faster
        assert select_related_time < n_plus_one_time / 2

## Deferred Field and Proxy System Tests

### Unit Tests (`test_deferred_proxies.py`)

Tests for the deferred field and relationship field proxy system:

```python
class TestDeferredFieldProxy:
    """Test DeferredFieldProxy behavior and error handling"""
    
    def test_deferred_field_proxy_creation(self):
        """Test DeferredFieldProxy can be created with proper parameters"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")
        
        assert proxy.instance == user
        assert proxy.field_name == "bio"
        assert proxy._cached_value is None
        assert proxy._is_loaded is False
    
    def test_deferred_field_proxy_error_handling(self):
        """Test DeferredFieldProxy raises appropriate errors"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")
        
        # Should raise DeferredFieldError for various operations
        with pytest.raises(DeferredFieldError):
            iter(proxy)
        
        with pytest.raises(DeferredFieldError):
            len(proxy)
        
        with pytest.raises(DeferredFieldError):
            bool(proxy)
    
    async def test_deferred_field_proxy_fetch_caching(self, session):
        """Test DeferredFieldProxy caches fetched values"""
        # Create and load user with deferred field
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio content"
        )
        
        loaded_user = await DeferredTestUser.objects.using(session).defer("bio").get(
            DeferredTestUser.id == user.id
        )
        
        proxy = DeferredFieldProxy(loaded_user, "bio")
        
        # First fetch should load and cache
        result1 = await proxy.fetch()
        assert result1 == "Test bio content"
        assert proxy._is_loaded is True
        
        # Second fetch should return cached value
        result2 = await proxy.fetch()
        assert result2 is proxy._cached_value

class TestRelationFieldProxy:
    """Test RelationFieldProxy behavior and error handling"""
    
    def test_relation_field_proxy_creation(self):
        """Test RelationFieldProxy can be created with proper parameters"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = RelationFieldProxy(user, "posts")
        
        assert proxy.instance == user
        assert proxy.field_name == "posts"
        assert proxy._cached_objects is None
        assert proxy._is_loaded is False
    
    def test_relation_field_proxy_error_handling(self):
        """Test RelationFieldProxy raises appropriate errors"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = RelationFieldProxy(user, "posts")
        
        # Should raise DeferredFieldError for various operations
        with pytest.raises(DeferredFieldError):
            iter(proxy)
        
        with pytest.raises(DeferredFieldError):
            len(proxy)
        
        with pytest.raises(DeferredFieldError):
            bool(proxy)
```

### Integration Tests (`test_deferred_loading.py`)

Comprehensive integration tests for deferred field loading with actual database operations:

```python
class TestDeferredFieldDatabaseOperations:
    """Test deferred field behavior with actual database operations"""
    
    async def test_defer_single_field(self, session):
        """Test deferring a single field during query"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="testuser",
            email="test@example.com",
            bio="This is a test bio"
        )
        
        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(
            DeferredUser.id == user.id
        )
        
        # Check deferred status
        assert loaded_user.is_field_deferred("bio")
        assert not loaded_user.is_field_loaded("bio")
        assert not loaded_user.is_field_deferred("username")
    
    async def test_load_deferred_fields(self, session):
        """Test loading deferred fields efficiently"""
        # Create user with multiple deferred fields
        user = await DeferredUser.objects.using(session).create(
            username="testuser",
            bio="Test bio content",
            profile_data="Profile data content",
            large_content="Large content data"
        )
        
        # Load with multiple deferred fields
        loaded_user = await DeferredUser.objects.using(session).defer(
            "bio", "profile_data", "large_content"
        ).get(DeferredUser.id == user.id)
        
        # Load specific fields
        await loaded_user.load_deferred_fields(["bio", "profile_data"])
        
        # Check loaded status
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("profile_data")
        assert not loaded_user.is_field_loaded("large_content")
    
    async def test_deferred_field_proxy_integration(self, session):
        """Test deferred field proxy integration with database loading"""
        # Create and load user with deferred field
        user = await DeferredUser.objects.using(session).create(
            username="testuser",
            bio="Test bio content"
        )
        
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(
            DeferredUser.id == user.id
        )
        
        # Mark as from database to enable proxy behavior
        loaded_user._state_manager.set("is_from_db", True)
        
        # Accessing deferred field should return proxy
        bio_proxy = loaded_user.bio
        assert isinstance(bio_proxy, DeferredFieldProxy)
        
        # Fetch through proxy should load the field
        bio_content = await bio_proxy.fetch()
        assert bio_content == "Test bio content"

class TestDeferredFieldQueryOperations:
    """Test deferred field behavior with various query operations"""
    
    async def test_defer_with_filter_operations(self, session):
        """Test deferred fields work with filtering"""
        # Create multiple users
        users_data = [
            {"username": f"user{i}", "email": f"user{i}@example.com", "bio": f"Bio for user {i}"}
            for i in range(5)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)
        
        # Query with filter and defer
        users = await DeferredUser.objects.using(session).defer("bio").filter(
            DeferredUser.username.like("user%")
        ).all()
        
        assert len(users) == 5
        for user in users:
            assert user.is_field_deferred("bio")
    
    async def test_defer_with_ordering_and_pagination(self, session):
        """Test deferred fields work with ordering and pagination"""
        # Create test data
        users_data = [
            {"username": f"user{i:02d}", "email": f"user{i}@example.com", "bio": f"Bio {i}"}
            for i in range(10)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)
        
        # Query with pagination and defer
        users = await DeferredUser.objects.using(session).defer("bio").order_by(
            "username"
        ).limit(3).offset(2).all()
        
        assert len(users) == 3
        assert users[0].username == "user02"
        
        # All should have deferred bio
        for user in users:
            assert user.is_field_deferred("bio")
```

### Performance Tests (`test_deferred_performance.py`)

Performance and scalability tests for the deferred field system:

```python
class TestDeferredFieldPerformance:
    """Test performance characteristics of deferred field system"""
    
    async def test_memory_usage_with_deferred_fields(self, session, performance_dataset):
        """Test memory usage difference between deferred and non-deferred loading"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Measure memory before loading
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Load all users WITHOUT deferred fields (full content)
        full_users = await PerformanceTestUser.objects.using(session).all()
        memory_full = process.memory_info().rss / 1024 / 1024  # MB
        
        # Load WITH deferred fields
        deferred_users = await PerformanceTestUser.objects.using(session).defer(
            "small_bio", "medium_content", "large_content", "huge_content"
        ).all()
        memory_deferred = process.memory_info().rss / 1024 / 1024  # MB
        
        # Deferred loading should use significantly less memory
        full_memory_usage = memory_full - memory_before
        deferred_memory_usage = memory_deferred - memory_before
        
        # Deferred should use at least 50% less memory
        assert deferred_memory_usage < full_memory_usage * 0.5
    
    async def test_query_performance_with_deferred_fields(self, session, performance_dataset):
        """Test query performance difference with deferred fields"""
        
        # Measure time for full query
        start_time = time.perf_counter()
        full_users = await PerformanceTestUser.objects.using(session).all()
        full_query_time = time.perf_counter() - start_time
        
        # Measure time for deferred query
        start_time = time.perf_counter()
        deferred_users = await PerformanceTestUser.objects.using(session).defer(
            "small_bio", "medium_content", "large_content", "huge_content"
        ).all()
        deferred_query_time = time.perf_counter() - start_time
        
        # Deferred queries should be faster (less data transfer)
        assert deferred_query_time < full_query_time
    
    async def test_deferred_field_cache_efficiency(self, session):
        """Test caching efficiency of deferred field proxies"""
        
        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="cachetest",
            small_bio="Cached bio content"
        )
        
        # Load with deferred field
        loaded_user = await PerformanceTestUser.objects.using(session).defer("small_bio").get(
            PerformanceTestUser.id == user.id
        )
        
        proxy = DeferredFieldProxy(loaded_user, "small_bio")
        
        # First fetch (should load from database)
        start_time = time.perf_counter()
        result1 = await proxy.fetch()
        first_fetch_time = time.perf_counter() - start_time
        
        # Second fetch (should use cache)
        start_time = time.perf_counter()
        result2 = await proxy.fetch()
        second_fetch_time = time.perf_counter() - start_time
        
        # Cached access should be much faster
        assert second_fetch_time < first_fetch_time / 10
        assert result1 == result2

class TestDeferredFieldScalability:
    """Test scalability characteristics of deferred field system"""
    
    async def test_large_dataset_deferred_loading(self, session):
        """Test deferred loading performance with large datasets"""
        
        # Create larger dataset for stress testing
        large_content = "x" * 5000  # 5KB per record
        users_data = []
        for i in range(500):  # 500 users
            users_data.append({
                "username": f"largeuser{i:03d}",
                "email": f"largeuser{i:03d}@example.com",
                "large_content": f"Large content {i}: {large_content}"
            })
        
        await PerformanceTestUser.objects.using(session).bulk_create(users_data)
        
        # Measure full loading time
        start_time = time.perf_counter()
        full_users = await PerformanceTestUser.objects.using(session).filter(
            PerformanceTestUser.username.like("largeuser%")
        ).all()
        full_load_time = time.perf_counter() - start_time
        
        # Measure deferred loading time
        start_time = time.perf_counter()
        deferred_users = await PerformanceTestUser.objects.using(session).defer(
            "large_content"
        ).filter(PerformanceTestUser.username.like("largeuser%")).all()
        deferred_load_time = time.perf_counter() - start_time
        
        # Deferred loading should be significantly faster
        assert deferred_load_time < full_load_time / 2
        assert len(full_users) == len(deferred_users) == 500
```

## Key Testing Features

### Deferred Field Testing Coverage

1. **Proxy Object Behavior**: Test DeferredFieldProxy and RelationFieldProxy creation, caching, and error handling
2. **Database Integration**: Test deferred field loading with actual database operations
3. **Query Operations**: Test deferred fields work correctly with filtering, ordering, and pagination
4. **Performance Characteristics**: Test memory usage, query performance, and caching efficiency
5. **Error Handling**: Test appropriate error messages and edge cases
6. **Scalability**: Test performance with large datasets and many deferred fields

### Performance Benchmarks

- **Memory Efficiency**: Deferred fields should use 50%+ less memory
- **Query Performance**: Deferred queries should be faster due to less data transfer
- **Cache Efficiency**: Cached proxy access should be 10x+ faster than initial load
- **Scalability**: System should handle 500+ records with large deferred content efficiently

### Error Testing

- **Clear Error Messages**: All proxy errors include field name and model class
- **Appropriate Exceptions**: Use DeferredFieldError for proxy operation attempts
- **Edge Cases**: Handle NULL values, nonexistent fields, and already loaded fields
- **Primary Key Requirements**: Proper error handling when primary key is missing

class TestCachePerformance:
"""Test caching performance"""

    async def test_query_cache_effectiveness(self, session, sample_users, performance_monitor):
        """Test query caching improves performance"""
        query = User.objects.using(session).filter(User.is_active == True)
        
        # First query (cache miss)
        performance_monitor.start()
        result1 = await query.all()
        first_time = performance_monitor.stop()["execution_time"]
        
        # Second query (cache hit)
        performance_monitor.start()
        result2 = await query.all()
        second_time = performance_monitor.stop()["execution_time"]
        
        assert len(result1) == len(result2) == 3
        # Second query should be faster due to caching
        assert second_time < first_time / 2
    
    async def test_cache_bypass(self, session, sample_users):
        """Test cache bypass functionality"""
        # Cached query
        cached_users = await User.objects.using(session).filter(User.is_active == True).all()
        
        # Bypass cache
        fresh_users = await User.objects.using(session).no_cache().filter(User.is_active == True).all()
        
        assert len(cached_users) == len(fresh_users) == 3
        # Results should be equivalent but fetched differently

```

## Testing Guidelines

### Test Organization Principles

1. **Unit Tests**: Fast, isolated tests for individual components
2. **Integration Tests**: Test component interactions with real database
3. **Performance Tests**: Validate performance claims and benchmarks
4. **Behavior Focus**: Test observable outcomes, not implementation details

### Naming Conventions

- Test files: `test_*.py`
- Test classes: `Test*` (descriptive of component being tested)
- Test methods: `test_*` (descriptive of behavior being tested)
- Fixtures: Descriptive names indicating purpose and scope

### Performance Testing Standards

- **Bulk Operations**: Must be 5-10x faster than individual operations
- **Memory Usage**: Iterator patterns should handle large datasets without memory growth
- **Query Caching**: Cache hits should be 2x+ faster than cache misses
- **Relationship Loading**: select_related should prevent N+1 query problems

### Multi-Database Testing

- Default to SQLite in-memory for speed
- Use environment variables for PostgreSQL/MySQL testing
- Test database-specific features separately
- Ensure consistent behavior across databases

