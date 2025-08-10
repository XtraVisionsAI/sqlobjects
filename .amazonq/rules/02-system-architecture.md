# SQLObjects System Architecture

## Database Configuration Rules

### 1. Database Initialization

```python
from sqlobjects.database import init_db, init_dbs, create_tables, DatabaseConfig
from sqlobjects.base import ObjectModel

# Single database - returns Database instance (default database)
db = await init_db("sqlite+aiosqlite:///test.db")
await create_tables(ObjectModel)

# Using DatabaseConfig with **kwargs support
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=10,
    echo=True,
    isolation_level="READ_COMMITTED",  # Extra engine parameter
    connect_args={"sslmode": "require"}
)
db = await init_db(config.url, **config.engine_kwargs)

# Single database with a name (default database)
db = await init_db("sqlite+aiosqlite:///test.db", name="main")

# Named database that is not the default
db = await init_db("sqlite+aiosqlite:///test.db", name="secondary", is_default=False)

# Control default database setting explicitly
db = await init_db("sqlite+aiosqlite:///test.db", name="main", is_default=True)  # Set as default
db = await init_db("sqlite+aiosqlite:///test.db", name="logs", is_default=False)  # Not default

# Test databases should not be default to avoid state pollution
test_db = await init_db("sqlite+aiosqlite:///:memory:", name="test_db", is_default=False)

# Multiple databases - returns tuple of Database instances in order
main_db, logs_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://..."},
    "logs": {"url": "sqlite+aiosqlite://logs.db"}
}, default="main")

# Multiple databases without default database
db1, db2 = await init_dbs({
    "db1": {"url": "postgresql+asyncpg://..."},
    "db2": {"url": "sqlite+aiosqlite://logs.db"}
})  # No default database set

# Direct access to each database instance
print(main_db.name)   # "main"
print(logs_db.name)   # "logs"
```

### 2. Database Event Handling

```python
# Single database event registration using Database.on() method
db = await init_db("sqlite+aiosqlite:///test.db")

@db.on("connect")
def on_connect(conn, record):
    print("Connected to database")

@db.on("before_commit")
def before_commit(session):
    print("About to commit")

@db.on("after_commit")
def after_commit(session):
    print("Committed successfully")

# Multiple databases event registration
main_db, logs_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://..."},
    "logs": {"url": "sqlite+aiosqlite:///logs.db"}
}, default="main")

@main_db.on("connect")
def main_db_connect(conn, record):
    print("Main DB connected")

@logs_db.on("connect")
def logs_db_connect(conn, record):
    print("Logs DB connected")

# Or use SQLAlchemy events directly
from sqlalchemy import event
event.listens_for(main_db.engine.sync_engine, "connect")(my_handler)
```

### 3. Session Management

```python
from sqlobjects.session import ctx_session, ctx_sessions, SessionContextManager

# Set session factory for databases
SessionContextManager.set_session_factory(main_factory, "main", is_default=True)
SessionContextManager.set_session_factory(analytics_factory, "analytics")

# Switch default database
SessionContextManager.set_default("analytics")

# Single database context manager
async with ctx_session() as session:
    user = await User.objects.create(username="test", session=session)

# Multiple databases context manager
async with ctx_sessions("main", "logs") as sessions:
    user = await User.objects.create(username="test", session=sessions["main"])
    await Log.objects.create(message="User created", session=sessions["logs"])

# Or use default session
user = await User.objects.create(username="test")
```

### 4. Database Connection Management

```python
from sqlobjects.database import close_db, close_dbs, set_default_db

# Close specific database with auto_default parameter
await close_db("main", auto_default=True)  # Automatically select new default if closing default DB
await close_db("logs", auto_default=False)  # Don't change default (default behavior)

# Close multiple databases with auto_default parameter
await close_dbs(["main", "logs"], auto_default=True)  # Auto-select new default if needed

# Close all databases
await close_db()  # Closes all databases
await close_dbs()  # Same as close_db()

# Manual default database selection
SessionContextManager.set_default("secondary")  # Set secondary database as default
```

#### auto_default Parameter Behavior

The `auto_default` parameter controls automatic default database selection when closing databases:

- **`auto_default=True`**: When closing the current default database, automatically select another available database as
  the new default
- **`auto_default=False`** (default): Don't change the default database setting when closing databases

**Use Cases:**

- **Dynamic Database Management**: Close databases at runtime while maintaining system functionality
- **Testing Environments**: Clean up test databases and automatically switch to remaining databases
- **Fault Recovery**: Close problematic databases and automatically failover to backup databases

## Signal and Event System Rules

### 1. SQLAlchemy Event Integration

```python
# Import SQLAlchemy event system
from sqlalchemy import event
from sqlalchemy.orm import Session

# Register engine events
@event.listens_for(engine, "connect")
def on_connect(dbapi_connection, connection_record):
    print("Database connected")

# Register session events
@event.listens_for(Session, "before_commit")
def before_commit(session):
    print("About to commit transaction")

# Register model events
@event.listens_for(User, "before_insert")
def before_insert_user(mapper, connection, target):
    target.created_at = datetime.now()
```

### 2. Database Event Convenience Methods

```python
# Use Database instance on() method for event registration
db = await init_db("sqlite+aiosqlite:///test.db")

# Register events using on() method
@db.on("connect")
def on_connect(conn, record):
    print("Connected!")

@db.on("before_commit")
def before_commit(session):
    print("Committing...")

@db.on("after_commit")
def after_commit(session):
    print("Committed!")

@db.on("before_rollback")
def before_rollback(session):
    print("Rolling back...")

@db.on("after_rollback")
def after_rollback(session):
    print("Rolled back!")
```

### 3. Model-Level Signal Handling

```python
# Model signals are handled through SQLAlchemy events
class User(ObjectModel):
    # ... fields ...
    
    @classmethod
    def setup_events(cls):
        """Setup model-level events"""
        event.listens_for(cls, "before_insert")(cls.before_insert_handler)
        event.listens_for(cls, "after_update")(cls.after_update_handler)
    
    @staticmethod
    def before_insert_handler(mapper, connection, target):
        target.created_at = datetime.now()
    
    @staticmethod
    def after_update_handler(mapper, connection, target):
        target.updated_at = datetime.now()

# Setup events after model definition
User.setup_events()
```

## Exception Handling Rules

### 1. Use Project-Specific Exceptions with English Messages

```python
from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned, ValidationError, create_validation_error

# Use descriptive English error messages
try:
    user = await User.objects.get(email=email)
except DoesNotExist:
    raise DoesNotExist(f"User with email '{email}' does not exist")
except MultipleObjectsReturned:
    raise MultipleObjectsReturned(f"Multiple User objects found with email '{email}'")

# Using specific session for exception handling
try:
    user = await User.objects.get(email=email, session=analytics_session)
except DoesNotExist:
    raise DoesNotExist(f"User with email '{email}' does not exist")
```

### 2. Validation Error Handling with English Messages

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector, create_validation_error

# Use create_validation_error for consistent error messages
if not email:
    raise create_validation_error("required", field="email")

# Or create ValidationError directly
if not email:
    raise ValidationError("This field is required", field="email", code="required")

# Multiple field validation with English messages
collector = ValidationErrorCollector()
if not username:
    collector.add_error("username", "This field is required")
if not email:
    collector.add_error("email", "This field is required")
collector.raise_if_errors()
```

### 3. Exception Message Guidelines

- **CLEAR AND DESCRIPTIVE**: Use clear, descriptive English error messages
- **CONSISTENT FORMATTING**: Use consistent message formatting across the codebase
- **PARAMETER SUPPORT**: Use parameter substitution for dynamic content
- **ERROR CODES**: Include error codes for programmatic handling

```python
# GOOD - Clear, descriptive messages
raise ValueError(f"Unknown type '{type_name}'. Available types: {', '.join(available_types)}")
raise ValidationError("Username must be at least 3 characters", code="min_length")

# GOOD - Using create_validation_error for consistency
raise create_validation_error("min_length", params={"min_length": 3})
```

## Testing Rules

### 1. Test Structure

- Use `pytest` with `pytest-asyncio`
- Place tests in `tests/` directory
- Use `@pytest.mark.asyncio` for async tests

```python
import pytest
from sqlobjects import ObjectModel

class TestUserModel:
    @pytest.mark.asyncio
    async def test_create_user(self, session):
        user = await User.objects.create(
            username="testuser",
            email="test@example.com",
            session=session
        )
        assert user.id is not None
        assert user.username == "testuser"
```

### 2. Test Execution

Always use `uv run pytest` for running tests.

### 3. Test Database Management

```python
# In test fixtures, use is_default=False to avoid global state pollution
@pytest.fixture
async def test_db():
    db = await init_db("sqlite+aiosqlite:///:memory:", name="test_db", is_default=False)
    await create_tables(ObjectModel, "test_db")
    yield db
    await close_db("test_db")

# Test-specific database operations
async def test_user_creation(test_db):
    async with ctx_session("test_db") as session:
        user = await User.objects.create(username="test", session=session)
        assert user.id is not None
```

## Import Standards

### 1. Core Imports

```python
# Base model and field definitions
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, column, relationship

# Type shortcut functions (recommended)
from sqlobjects.fields import (
    str_column, int_column, bool_column, numeric_column, datetime_column,
    json_column, array_column, enum_column, uuid_column, binary_column, pickle_column
)

# Type system and registration
from sqlobjects.fields import register_field_type

# SQLAlchemy advanced features
from sqlobjects.fields import composite, column_property, synonym

# Query operations
from sqlobjects.queries import Q, QuerySet

# Expressions and functions (unified system)
from sqlobjects.expressions import F, func, SubqueryExpression

# Database operations
from sqlobjects.database import (
    init_db, init_dbs, create_tables, drop_tables, 
    close_db, Database, DatabaseManager, DatabaseConfig
)

# Session management
from sqlobjects.session import ctx_session, ctx_sessions, SessionContextManager

# Signal and event handling
from sqlobjects.signals import event

# Exception handling
from sqlobjects.exceptions import (
    DoesNotExist, 
    MultipleObjectsReturned, 
    ValidationError,
    ValidationErrorCollector,
    create_validation_error
)

# Validators
from sqlobjects.validators import (
    validate_email,
    validate_url,
    validate_length,
    validate_range,
    validate_regex,
    validate_choices,
    validate_date,
    validate_time,
    validate_decimal,
    validate_json,
    validate_file,
    validate_image,
    combine_validators
)

# Configuration
from sqlobjects.config import (
    index, 
    constraint,
    unique,
    mysql_config,
    postgresql_config
)

# Naming utilities
from sqlobjects.utils.naming import (
    to_snake_case,
    to_camel_case
)

# Pattern utilities  
from sqlobjects.utils.pattern import (
    pluralize,
    singularize,
    is_plural
)
```

### 2. Field Shortcuts

```python
from sqlobjects.fields import (
    # Core shortcuts
    identity,      # Auto-increment primary key
    computed,      # Computed columns (now supports type parameter)
    sequence,      # Sequence-based columns
    foreign_key,   # Foreign key columns
    created_at,    # Creation timestamp
    updated_at,    # Update timestamp
    
    # Type shortcuts (recommended)
    str_column,    # String columns with type variants
    int_column,    # Integer columns with size variants
    bool_column,   # Boolean columns
    numeric_column, # Numeric columns with precision control
    datetime_column, # DateTime columns with type variants
    json_column,   # JSON columns
    array_column,  # Array columns
    enum_column,   # Enum columns
    uuid_column,   # UUID columns
    binary_column, # Binary columns with type variants
    pickle_column, # Pickle columns for Python objects
    
    # SQLAlchemy advanced features
    composite,     # Composite types
    column_property, # Computed properties
    synonym,       # Column synonyms
)
```

### 3. Expression System Imports

```python
# Primary expression system (recommended)
from sqlobjects.expressions import func, SubqueryExpression

# For raw SQLAlchemy integration when needed
from sqlalchemy import text, literal, and_, or_, not_
from sqlalchemy import func as sa_func  # Only when func object is insufficient

# Usage patterns
# Use: User.name.upper() for field-level operations (enhanced comparators)
# Use: func.concat(User.first_name, User.last_name) for multi-field operations
# Use: QuerySet.subquery() for intelligent subquery creation with automatic type inference
# Use: Q objects for complex logical combinations
```

## Code Organization Best Practices

### 1. Class Method Organization

When implementing model classes, organize methods in this order:

```python
class User(ObjectModel):
    # 1. Field definitions
    id: Column[int] = int_column(primary_key=True)
    username: Column[str] = str_column(length=50)
    
    # 2. Configuration
    class Config:
        table_name = "users"
        ordering = ["-created_at"]
    
    # 3. Validation methods
    def validate(self):
        # Model-level validation
        pass
    
    @classmethod
    def setup_validators(cls):
        # Field validator setup
        pass
    
    # 4. Instance methods
    async def custom_method(self):
        # Custom business logic
        pass
    
    # 5. Class methods and properties
    @classmethod
    def custom_class_method(cls):
        # Custom class-level logic
        pass
    
    # 6. Query methods using expressions
    @classmethod
    async def get_active_users_with_stats(cls):
        return await cls.objects.filter(is_active=True).annotate(
            post_count=F.count(F("posts")),
            latest_post=F.max(F("posts__created_at"))
        ).all()
```

### 2. Import Organization

```python
# Standard library imports
from datetime import datetime
from typing import Any

# Third-party imports
from sqlalchemy import text

# SQLObjects core imports
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, column, relationship, str_column, int_column
from sqlobjects.queries import Q, QuerySet
from sqlobjects.expressions import func, SubqueryExpression
from sqlobjects.exceptions import ValidationError, DoesNotExist
from sqlobjects.session import ctx_session
from sqlobjects.config import index, constraint
```

### 3. Documentation Standards

- All public methods MUST have comprehensive docstrings
- Include Args, Returns, and Raises sections
- Group related methods with section headers
- Use type hints consistently
- Document validation behavior and signal triggering

```python
async def create(
    self,
    validate: bool = True,
    session: AsyncSession | None = None,
    commit: bool = False,
    **kwargs,
) -> T:
    """Create a new object with the given field values.

    Args:
        validate: Whether to execute all validation (both SQLObjects and SQLAlchemy validators)
        session: Database session to use
        commit: Whether to commit the transaction
        **kwargs: Field values for the new object

    Returns:
        Created model instance

    Raises:
        ValidationError: If validation fails during creation
    """
```