# SQLObjects Core Architecture Design Document

## Overview

SQLObjects core architecture is built on SQLAlchemy Core using a composition pattern design, providing global database
management, ContextVar-based session context, and complete model base classes.
It implements decoupling between database manager and session manager through an event system, supporting multi-database
environments and asynchronous operations.

## Core Features

### 1. Global Database Management

An internal database manager (`_DatabaseManager`) serves as a global singleton managing multi-database connections, while the Database class provides event
handling capabilities:

```python
# Database initialization - returns Database instance
db = await init_db("postgresql://user:pass@localhost/db", name="main")
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql://...", "pool_size": 20},
    "analytics": {"url": "sqlite:///analytics.db"}
}, default="main")

# Event registration - through Database instance
@db.on("connect")
def on_connect(conn, record):
    print("Database connected")

# The internal _DatabaseManager manages all database instances
# Supports default database and named database access
```

### 2. ContextVar-Based Session Context

AsyncSession class provides intelligent connection management, and an internal session context manager (`_SessionContextManager`) provides context-level session
management based on `contextvars.ContextVar`:

```python
# Automatic session management - using default database
user = await User.objects.get(User.id == 1)

# Explicit transaction control - using context managers (recommended)
from sqlobjects.session import ctx_session, ctx_sessions

# Single database session
async with ctx_session() as session:
    user = await User.objects.using(session).create(name="John")

# Specified database session
async with ctx_session("analytics") as session:
    data = await Log.objects.using(session).all()

# Multi-database sessions
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(name="Alice")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
```

### 3. Composition Pattern Model Base Class

ObjectModel is implemented through composition of ModelProcessor metaclass and ModelMixin, integrating all functional
components:

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):  # Inherits ModelMixin + ModelProcessor metaclass
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100, unique=True)
  
    class Config:
        table_name = "users"
        ordering = ["-created_at"]

# ObjectModel built-in features:
# - SignalMixin: Signal system
# - FieldCacheMixin: Field caching and proxy
# - ValidationMixin: Validation system
# - DeferredLoadingMixin: Deferred loading
# - SessionMixin: Session management
# - _StateManager: Dirty-field tracking and instance state (history of changes)

# Instance operations - intelligent detection and signal emission
user = User(name="John", email="john@example.com")
await user.save()  # Auto-detects CREATE, emits before_save/before_create/after_save/after_create

user.email = "john.new@example.com"
await user.save()  # Auto-detects UPDATE, only updates dirty fields
```

### 4. ModelProcessor Metaclass System

ModelProcessor metaclass automatically handles model definitions, generating SQLAlchemy tables and setting up objects
manager:

```python
# Automatic table name generation and objects manager setup
class UserProfile(ObjectModel):  # → table: "user_profiles"
    pass
# Automatically sets: UserProfile.objects = ObjectsDescriptor(UserProfile)

# Configuration processing and field caching
class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)
  
    class Config:
        indexes = [index("idx_name", "name")]
        constraints = [constraint("price > 0")]

# ModelProcessor automatically handles:
# - Field definition conversion to SQLAlchemy Column
# - Generation of __table__ attribute
# - Setup of objects manager
# - Initialization of field cache
# - Processing of relationship definitions
```

## Module Architecture

### Core Components

**Global Management Layer**

- **_DatabaseManager**: Internal global database manager (`database/manager.py`), manages multiple database instances. Not accessed directly; the public entry points are the module-level functions `init_db`/`init_dbs`/`close_db`/`close_dbs`.
- **Database**: Database instance, provides event handling and connection management
- **AsyncSession**: Intelligent session class, provides connection management and transaction control
- **_SessionContextManager**: Internal global session context manager (`session.py`), ContextVar-based context-level session management. Not accessed directly; the public entry points are the module-level functions `ctx_session`/`get_session`/`has_session`.

**Model Layer**

- **ObjectModel**: Composition pattern model base class, integrates ModelMixin + ModelProcessor metaclass
- **ModelProcessor**: Metaclass processor, automatically generates SQLAlchemy tables and objects manager
- **ModelMixin**: Defined as `class ModelMixin(DataConversionMixin, SignalMixin)` (`model.py`). Its
  functionality comes from a single linear inheritance chain rooted at `DataConversionMixin`, plus
  `SignalMixin` as a direct base:
  - DataConversionMixin (data conversion functionality) — the direct base
  - FieldCacheMixin (field caching and attribute access optimization)
  - DeferredLoadingMixin (deferred loading functionality)
  - ValidationMixin (validation logic)
  - PrimaryKeyMixin (primary key operations)
  - SessionMixin (session management)
  - BaseMixin (basic functionality and state management)

**Functional Mixin Layer**

- **FieldCacheMixin**: Field caching and intelligent attribute access, integrated proxy system
- **SignalMixin**: Signal system, a direct base class of ModelMixin (composed alongside the DataConversionMixin chain)
- **ValidationMixin**: Validation system integration
- **DeferredLoadingMixin**: Deferred loading functionality
- **SessionMixin**: Session management and using() method

**State Management Layer**

- **_StateManager**: Internal unified instance state management (`mixins.py`), supports dirty-field
  tracking (the basis for change history), deferred fields, and proxy/object cache
- **DeferredObject**: Deferred field proxy, supports lazy loading and caching
- **RelatedObject** / **RelatedCollection**: Relationship field proxies, support relationship lazy loading
  (single object vs. collection; see `fields/proxies.py`)

**Web Framework Integration Layer (`contrib/`)**

- **SessionMiddleware** (`contrib/asgi.py`): ASGI middleware providing request-scoped session management with auto commit/rollback
- **get_db_session** (`contrib/fastapi.py`): FastAPI dependency that yields a transactional session via `ctx_session()`

**Cross-cutting Subsystems**

- **SQL Logging** (`sql_logging.py`): `ObjectLogger` rewrites log-record caller fields to the real user-code call site; installed as the `sqlobjects.sql` logger and used by the query executor. See document 05.
- **Cascade** (`cascade.py`): unified cascade strategy coordinating database-level `ondelete`/`onupdate` and ORM-level `cascade`, with dependency resolution and cascade execution. See document 04.

### Design Philosophy

**Composition Pattern**: Uses Mixin composition rather than complex inheritance for better maintainability
**Global Management**: Global internal _DatabaseManager and _SessionContextManager instances (fronted by module-level functions) for simplified usage
**Event-Driven**: Database class provides extension points through event system
**Intelligent Detection**: Automatic detection of CREATE/UPDATE operations, dirty field tracking, deferred loading
**Metaclass-Driven**: ModelProcessor metaclass automatically handles model definition and table generation
**Unified State**: _StateManager unifies instance state management, supporting multiple state types

### Integration with Other Modules

**Data Operation Module**: Obtains sessions through the module-level session context (`ctx_session`/`get_session`, backed by the internal `_SessionContextManager`)
**Field System Module**: Processes field definitions through ModelProcessor
**Relationship Processing Module**: Provides relationship support through ObjectModel

## API Reference

### Database Management

```python
# Database initialization
await init_db(url, name=None, **kwargs)
await init_dbs(databases, default=None)

# Table operations
await create_tables(base_class, db_name=None)
await drop_tables(base_class, db_name=None)

# Connection management
await close_db(db_name=None)
await close_dbs(db_names=None)
```

### Session Management

```python
# Context managers
async with ctx_session(db_name=None) as session:
    pass

# Reuse the ambient session when one exists (avoids a second physical
# connection inside an active transaction); lifecycle stays with the owner
async with ctx_session(join_ambient=True) as session:
    pass

async with ctx_sessions(*db_names) as sessions:
    pass

# Recommended to use context managers rather than directly getting sessions
# The module-level get_session() (backed by the internal _SessionContextManager) is mainly for internal implementation
```

### Model Definition

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class Model(ObjectModel):
    # Field definitions
    field: Column[str] = StringColumn(...)
  
    # Configuration class
    class Config:
        table_name = "custom_name"
        ordering = ["-created_at"]
        indexes = [...]
        constraints = [...]
```

## Usage Guide

### Basic Usage

```python
# 1. Database initialization
await init_db("sqlite+aiosqlite:///app.db")

# 2. Model definition
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100, unique=True)

# 3. Create tables
await create_tables(ObjectModel)

# 4. Basic operations
user = User(name="John", email="john@example.com")
await user.save()
```

### Advanced Usage

```python
# Multi-database configuration
await init_dbs({
    "main": {
        "url": "postgresql://localhost/main",
        "pool_size": 20
    },
    "analytics": {
        "url": "sqlite:///analytics.db"
    }
}, default="main")

# Complex model configuration
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, NumericColumn
from decimal import Decimal

class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)
  
    class Config:
        table_name = "products"
        ordering = ["name"]
        indexes = [
            index("idx_name", "name"),
            index("idx_price", "price", unique=True)
        ]
        constraints = [
            constraint("price > 0", "ck_positive_price")
        ]

# Transaction management
async with ctx_session() as session:
    # All operations within the same transaction
    user = await User.objects.using(session).create(name="Alice")
    product = await Product.objects.using(session).create(
        name="Widget", price=Decimal("19.99")
    )
```