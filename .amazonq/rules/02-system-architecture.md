# SQLObjects System Architecture

## Database Configuration Rules

### 1. Database Initialization

```python
from sqlobjects.database import init_db, init_dbs, create_tables, DatabaseConfig
from sqlobjects.base import ObjectModel
from dataclasses import dataclass
from typing import Any

# DatabaseConfig with @dataclass(init=False) design
@dataclass(init=False)
class DatabaseConfig:
    url: str
    echo: bool
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    engine_kwargs: dict[str, Any]
    
    def __init__(self, url: str, echo: bool = False, pool_size: int = 5, 
                 max_overflow: int = 10, pool_timeout: int = 30, 
                 pool_recycle: int = 3600, **kwargs: Any) -> None:
        self.url = url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.engine_kwargs = kwargs  # Collect extra engine parameters

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

### 3. Session Management and Transaction Modes

```python
from sqlobjects.session import ctx_session, ctx_sessions, SessionContextManager
import asyncio
import contextvars

# Set session factory for databases
SessionContextManager.set_session_factory(main_factory, "main", is_default=True)
SessionContextManager.set_session_factory(analytics_factory, "analytics")

# Switch default database
SessionContextManager.set_default("analytics")

# Single database context manager
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="test")

# Multiple databases context manager
async with ctx_sessions("main", "logs") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="test")
    await Log.objects.using(sessions["logs"]).create(message="User created")

# Or use default session
user = await User.objects.create(username="test")

# Three Transaction Modes

# Mode 1: ContextVar Inheritance - Unified Transaction
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    await asyncio.gather(*tasks)  # All tasks share same session via ContextVar

# Mode 2: Independent Context - Isolated Transactions
tasks = [
    asyncio.create_task(process_batch_isolated(batch), context=contextvars.copy_context())
    for batch in batches
]
await asyncio.gather(*tasks, return_exceptions=True)  # Each task has independent session

# Mode 3: Explicit Session Passing - Full Control
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch_explicit(batch, session)) for batch in batches]
    await asyncio.gather(*tasks)  # Explicitly share same session
```

#### Transaction Mode Comparison

| Mode | Advantages | Use Cases | Considerations |
|------|------------|-----------|----------------|
| **ContextVar Inheritance** | Clean code, automatic propagation | Unified transactions, code simplification | Depends on ContextVar mechanism |
| **Independent Context** | Complete isolation, failure doesn't affect others | Independent transactions, fault tolerance | Manual context management required |
| **Explicit Passing** | Clear control, no implicit mechanisms | Complex transaction logic, debugging friendly | Slightly more verbose code |

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

**Selection Logic:**

```python
# Internal behavior when auto_default=True and closing default database
if auto_default and self._default_db == db_name:
    self._default_db = next(iter(self._databases), None)
    if self._default_db:
        default_db = self._databases[self._default_db]
        SessionContextManager.set_session_factory(default_db.session_factory, self._default_db, is_default=True)
```

## Signal and Event System Rules

### 1. Enhanced Signal System with Smart SAVE Operation

```python
# SQLObjects provides enhanced signal system with intelligent operation detection
from sqlobjects.signals import SignalMixin, SignalContext, Operation, emit_signals

class User(ObjectModel, SignalMixin):
    # Instance-level signals (single record operations)
    async def before_save(self, context: SignalContext):
        print("Universal save logic")  # Always triggered for SAVE operations
    
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()  # Only triggered for CREATE
    
    async def before_update(self, context: SignalContext):
        self.updated_at = datetime.now()  # Only triggered for UPDATE
    
    # Bulk operation signals (multiple records)
    @classmethod
    async def before_bulk_save(cls, context: SignalContext):
        print(f"Bulk save operation affecting {context.affected_count} records")
    
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        print(f"Bulk update operation affecting {context.affected_count} records")

# Smart SAVE operation with dual signal emission
@emit_signals(Operation.SAVE)  # Automatically detects CREATE vs UPDATE
async def save(self):
    # New instance: triggers before_save → before_create → DB operation → after_save → after_create
    # Existing instance: triggers before_save → before_update → DB operation → after_save → after_update
    pass
```

### 2. Operation Types and Signal Naming Conventions

```python
# Operation enumeration
class Operation(Enum):
    CREATE = "create"  # Explicit create operations
    UPDATE = "update"  # Explicit update operations
    DELETE = "delete"  # Delete operations
    SAVE = "save"      # Smart save operations (auto-detects CREATE/UPDATE)

# Signal handler naming conventions:
# Instance-level signals (single record operations):
# - before_create, after_create
# - before_update, after_update
# - before_delete, after_delete
# - before_save, after_save

# Bulk operation signals (multiple records):
# - before_bulk_create, after_bulk_create
# - before_bulk_update, after_bulk_update
# - before_bulk_delete, after_bulk_delete
# - before_bulk_save, after_bulk_save
```

### 3. SQLAlchemy Event Integration

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

### 6. Database Event Convenience Methods

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

### 4. Signal Decorator Usage Patterns

```python
# Explicit operation type specification
@emit_signals(Operation.CREATE)
async def create_user(cls, **kwargs):
    # Only triggers CREATE-specific signals
    pass

@emit_signals(Operation.UPDATE)
async def update_user(self, **kwargs):
    # Only triggers UPDATE-specific signals
    pass

# Smart SAVE operation with dual signal emission
@emit_signals(Operation.SAVE)
async def save_user(self):
    # Automatically detects CREATE vs UPDATE and triggers both generic and specific signals
    pass

# Bulk operations with explicit bulk signal naming
@emit_signals(Operation.UPDATE, is_bulk=True)
async def bulk_update_users(cls, mappings):
    # Triggers before_bulk_update and after_bulk_update signals
    pass

@emit_signals(Operation.SAVE, is_bulk=True)
async def bulk_save_users(cls, data):
    # Triggers before_bulk_save and after_bulk_save signals
    pass
```

### 5. Signal Context and Operation Detection

```python
# SignalContext provides comprehensive operation information
@dataclass
class SignalContext:
    operation: Operation                    # Original operation type
    session: AsyncSession                   # Database session
    model_class: Any                        # Target model class
    instance: Any | None = None             # Instance for single operations
    affected_count: int | None = None       # Row count for bulk operations
    update_data: dict[str, Any] | None = None  # Update data for bulk operations
    actual_operation: Operation | None = None  # Detected operation for SAVE

# Automatic operation detection for SAVE operations
def _determine_save_operation(self_or_cls) -> Operation:
    if hasattr(self_or_cls, "__table__"):  # Instance method
        # Check if instance has primary key set (indicates UPDATE)
        primary_keys = [col.name for col in self_or_cls.__table__.primary_key.columns]
        if any(getattr(self_or_cls, pk, None) is not None for pk in primary_keys):
            return Operation.UPDATE
        else:
            return Operation.CREATE
    else:
        return Operation.CREATE  # Class methods default to CREATE
```

## Exception Handling Rules

### 1. Use Project-Specific Exceptions with English Messages

```python
from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned, ValidationError, create_validation_error

# Use descriptive English error messages
try:
    user = await User.objects.get(User.email == email)
except DoesNotExist:
    raise DoesNotExist(f"User with email '{email}' does not exist")
except MultipleObjectsReturned:
    raise MultipleObjectsReturned(f"Multiple User objects found with email '{email}'")

# Using specific session for exception handling
try:
    user = await User.objects.using(analytics_session).get(User.email == email)
except DoesNotExist:
    raise DoesNotExist(f"User with email '{email}' does not exist")
```

### 2. Validation Error Handling with English Messages

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector, create_validation_error

# Complete English error message mapping
_ERROR_MESSAGES = {
    "required": "This field is required",
    "invalid": "Invalid value",
    "min_length": "Ensure this value has at least {min_length} characters",
    "max_length": "Ensure this value has at most {max_length} characters",
    "min_value": "Ensure this value is greater than or equal to {min_value}",
    "max_value": "Ensure this value is less than or equal to {max_value}",
    "invalid_email": "Enter a valid email address",
    "invalid_url": "Enter a valid URL",
    "invalid_choice": "'{value}' is not a valid choice",
    "invalid_date": "Enter a valid date",
    "invalid_time": "Enter a valid time",
    "invalid_decimal": "Enter a valid decimal number",
    "invalid_json": "Enter valid JSON",
    "file_not_found": "File not found: {path}",
    "file_too_large": "File size {size} exceeds maximum allowed size {max_size}",
    "invalid_file_extension": "File extension '{extension}' not allowed. Allowed: {allowed}",
    "invalid_image_format": "Invalid image format '{extension}'. Allowed: {allowed}"
}

# Use create_validation_error for consistent error messages
if not email:
    raise create_validation_error("required", field="email")

# Parameterized error messages
if len(password) < 8:
    raise create_validation_error("min_length", field="password", params={"min_length": 8})

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
        user = await User.objects.using(session).create(
            username="testuser",
            email="test@example.com"
        )
        assert user.id is not None
        assert user.username == "testuser"
```

### 2. ModelProxy Session Management

```python
from sqlobjects.base import ModelProxy, ModelMixin
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session

class ModelProxy(ModelMixin):
    def __init__(self, instance, db_or_session: str | AsyncSession):
        self._instance = instance
        self._db_or_session = db_or_session
        self._session_attached = False
    
    def _ensure_session_attachment(self, session: AsyncSession) -> None:
        """Ensure instance is properly attached to the specified session"""
        if self._session_attached:
            return
        
        current_session = async_object_session(self._instance)
        if current_session is None:
            session.add(self._instance)
        elif current_session is not session:
            self._handle_session_migration(current_session, session)
        
        self._session_attached = True
    
    def _handle_session_migration(self, old_session: AsyncSession, new_session: AsyncSession) -> None:
        """Handle instance migration between different sessions"""
        try:
            old_session.expunge(self._instance)
        except Exception:
            pass
        new_session.add(self._instance)
    
    def __getattr__(self, name):
        """Proxy attribute access to the wrapped instance"""
        return getattr(self._instance, name)
```

### 2. Test Execution

Always use `uv run pytest` for running tests.

### 3. Test Database Management with ConfigManager

```python
# ConfigManager and _ConfigParser separation
class ConfigManager:
    """Global configuration manager with caching and lifecycle management"""
    
    def __init__(self):
        self.parser = _ConfigParser()
        self._config_cache: dict[type, ModelConfig] = {}
    
    def process_model_config(self, model_class: type) -> tuple[ModelConfig, bool]:
        """Process model configuration and cache results"""
        config = self.parser.process_complete_config(model_class)
        is_abstract = self._is_abstract_model(model_class, config)
        if not is_abstract:
            self._apply_config_to_model(model_class, config)
        self._config_cache[model_class] = config
        return config, is_abstract

class _ConfigParser:
    """Internal configuration parser for parsing and merging logic"""
    
    def process_complete_config(self, model_class: type) -> ModelConfig:
        """Process complete model configuration"""
        configs = []
        
        # Parse class attributes
        class_config = self.parse_class_attributes(model_class)
        if class_config:
            configs.append(class_config)
        
        # Parse Config inner class
        config_class = getattr(model_class, "Config", None)
        if config_class:
            inner_config = self.parse_config_class(config_class)
            if inner_config:
                configs.append(inner_config)
        
        return self.merge_configs(*configs) if configs else ModelConfig()

# In test fixtures, recommend using is_default=False to avoid global state pollution
@pytest.fixture
async def test_db():
    db = await init_db("sqlite+aiosqlite:///:memory:", name="test_db", is_default=False)
    await create_tables(ObjectModel, "test_db")
    yield db
    await close_db("test_db")

# Test-specific database operations
async def test_user_creation(test_db):
    async with ctx_session("test_db") as session:
        user = await User.objects.using(session).create(username="test")
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
    json_column, array_column, enum_column, uuid_column, binary_column
)

# Type system and registration
from sqlobjects.fields import register_field_type

# SQLAlchemy advanced features
from sqlobjects.fields import composite, column_property, synonym

# Query operations
from sqlobjects.queries import Q, QuerySet

# Expressions and functions
from sqlobjects.expressions import func, SubqueryExpression

# Database operations
from sqlobjects.database import (
    init_db, init_dbs, create_tables, drop_tables, 
    close_db, Database, DatabaseManager, DatabaseConfig
)

# Session management
from sqlobjects.session import ctx_session, ctx_sessions, SessionContextManager

# Exception handling
from sqlobjects.exceptions import (
    DoesNotExist, 
    MultipleObjectsReturned, 
    ValidationError,
    ValidationErrorCollector,
    create_validation_error
)

# Signal system
from sqlobjects.signals import (
    Operation,
    SignalContext,
    SignalMixin,
    emit_signals
)

# Common validators
from sqlobjects.validators import (
    validate_email,
    validate_length,
    validate_range,
    validate_choices,
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

    
    # SQLAlchemy advanced features
    composite,     # Composite types
    column_property, # Computed properties
    synonym,       # Column synonyms
)
```

### 3. Expression System Imports

```python
# Primary expression system
from sqlobjects.expressions import func, SubqueryExpression

# For raw SQLAlchemy integration when needed
from sqlalchemy import text, literal, and_, or_, not_
from sqlalchemy import func as sa_func  # Only when func object is insufficient
from sqlalchemy import event  # For SQLAlchemy event system integration

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
class User(ObjectModel, SignalMixin):
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
    
    # 4. Signal handlers
    async def before_save(self, context: SignalContext):
        # Universal save logic
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        # Create-specific logic
        self.created_at = datetime.now()
    
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        # Bulk operation logic
        print(f"Updating {context.affected_count} users")
    
    # 5. Instance methods with signal decorators
    @emit_signals(Operation.SAVE)
    async def save(self):
        # Smart save with dual signal emission
        pass
    
    async def custom_method(self):
        # Custom business logic
        pass
    
    # 6. Class methods and properties
    @classmethod
    def custom_class_method(cls):
        # Custom class-level logic
        pass
    
    # 7. Query methods using expressions
    @classmethod
    async def get_active_users_with_stats(cls):
        return await cls.objects.filter(User.is_active == True).annotate(
            post_count=func.count(cls.posts),
            latest_post=func.max(cls.posts.created_at)
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
from sqlobjects.signals import SignalMixin, SignalContext, Operation, emit_signals
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