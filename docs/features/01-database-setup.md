# Database Setup and Configuration

## Overview

SQLObjects provides flexible database configuration that supports single and multiple databases with automatic
connection management, session handling, and transaction control.

## Quick Start

### Single Database Setup

```python
from sqlobjects.database import init_db, create_tables
from sqlobjects.model import ObjectModel

# Initialize database
db = await init_db("sqlite+aiosqlite:///app.db")

# Create tables
await create_tables(ObjectModel)

# Ready to use
user = await User.objects.create(username="john")
```

### Multiple Database Setup

```python
from sqlobjects.database import init_dbs

# Initialize multiple databases - returns tuple of Database instances
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://user:pass@localhost/main"},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
}, default="main")

# Use specific database by name
user = await User.objects.using("analytics").create(username="john")

# Or use Database instance directly
user = await User.objects.using(analytics_db).create(username="jane")
```

## Database Configuration

### Connection Parameters

```python
from sqlobjects.database import DatabaseConfig

# Advanced configuration
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    echo=False  # Set to True to enable SQL logging
)

db = await init_db(config.url, **config.engine_kwargs)
```

### Environment-based Configuration

```python
import os

# Development environment
if os.getenv("ENV") == "development":
    db_url = "sqlite+aiosqlite:///dev.db"
    echo = True
# Production environment
else:
    db_url = os.getenv("DATABASE_URL")
    echo = False

db = await init_db(db_url, echo=echo)
```

## Session Management

### Context Managers

```python
from sqlobjects.session import ctx_session, ctx_sessions

# Single database session (recommended)
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    posts = await user.posts.all()
    # Auto-commit on success, rollback on error

# Specific database session
async with ctx_session("analytics") as session:
    logs = await Log.objects.using(session).all()

# Multi-database sessions
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    await Log.objects.using(sessions["analytics"]).create(message="User created")

# Session with specific database
async with ctx_session("analytics") as session:
    users = await User.objects.using(session).all()

# Inside a possibly-active transaction: join the ambient session instead of
# opening a second physical connection (whose writes could block forever on
# rows locked by the outer transaction, invisible to deadlock detection)
async with ctx_session(join_ambient=True) as session:
    # Reuses the outer session if one exists; creates one only at top level.
    # Commit/rollback/close belong to the outermost owner.
    await User.objects.using(session).create(username="carol")
```

### Checking Session Availability

```python
from sqlobjects.session import has_session

# Check if an explicit session exists in current context
if has_session():
    # Inside a ctx_session() block
    pass

# Check for a specific database
if has_session("analytics"):
    # Inside a ctx_session("analytics") block
    pass
```

### Default Session Usage

```python
# Automatically uses default database
user = await User.objects.create(username="charlie")
users = await User.objects.filter(User.is_active == True).all()
```

## Transaction Modes

### Unified Transaction

```python
# All operations in single transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="david")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    # Auto-commit on success, rollback on error
```

### Independent Transactions

```python
import asyncio
import contextvars

# Each task has independent transaction
tasks = [
    asyncio.create_task(process_user(user_id), context=contextvars.copy_context())
    for user_id in user_ids
]
await asyncio.gather(*tasks, return_exceptions=True)
```

## Database Events

### Connection Events

```python
# Register database events
@db.on("connect")
def on_connect(conn, record):
    print("Database connected")

@db.on("before_commit")
def before_commit(session):
    print("About to commit transaction")

@db.on("after_commit")
def after_commit(session):
    print("Transaction committed")
```

### SQLAlchemy Events

```python
from sqlalchemy import event

# Register SQLAlchemy events directly
@event.listens_for(db.engine.sync_engine, "connect")
def setup_connection(dbapi_connection, connection_record):
    # Configure connection settings
    pass
```

## Connection Lifecycle

### Graceful Shutdown

```python
from sqlobjects.database import close_db, close_dbs

# Close specific database by name
await close_db("analytics")

# Close and auto-reassign default database
await close_db("main", auto_default=True)

# Close multiple specific databases
await close_dbs(["analytics", "backup"])

# Close all databases (call with no arguments)
await close_dbs()

# Close a Database instance directly
await analytics_db.disconnect()
```

### Health Checks

```python
# Check database connectivity
try:
    count = await User.objects.count()
    print(f"Database healthy: {count} users")
except Exception as e:
    print(f"Database error: {e}")
```

## SQL Logging

SQLObjects emits executed statements through the standard `logging` module under
the logger name `sqlobjects.sql`. Logging is zero-configuration: the query
executor only compiles SQL for logging when the logger is actually enabled for
`DEBUG`, so there is no overhead when logging is off.

### Enabling SQL Logging

```python
import logging

# Emit SQL to the console at DEBUG level
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)

# Any query now logs its SQL
users = await User.objects.filter(User.is_active == True).all()
```

Each SQL log record carries structured data in `record.__dict__` that you can
consume from a custom handler:

- `sql` - the compiled SQL string (bind parameters not inlined)
- `params` - a dict of the bind parameters
- `duration_ms` - execution time in milliseconds

```python
class SQLHandler(logging.Handler):
    def emit(self, record):
        print(f"[{record.duration_ms:.1f}ms] {record.sql}")
        print(f"    params: {record.params}")

sql_logger = logging.getLogger("sqlobjects.sql")
sql_logger.setLevel(logging.DEBUG)
sql_logger.addHandler(SQLHandler())
```

### Caller Location Rewriting

`sqlobjects.sql` is an `ObjectLogger` instance (`sqlobjects/sql_logging.py`).
It overrides `makeRecord()` to rewrite each record's caller fields
(`pathname`, `filename`, `module`, `funcName`, `lineno`) to the first
**user-code** frame, skipping frames from `sqlobjects.*`, `sqlalchemy.*`, the
standard `logging` package, and any `site-packages`. This means log output
points at the line in your application that issued the query rather than at
internal library code, and it works with any handler (including loguru's
`InterceptHandler`) without extra filter configuration.

For custom scenarios you can also resolve the caller frame directly:

```python
from sqlobjects import get_caller_frame

frame = get_caller_frame()                       # "app/service.py:42 in list_users"
frames = get_caller_frame(max_frames=3)          # list of frame strings
frame = get_caller_frame(extra_skip_packages=["myapp.middleware"])
```

## Best Practices

### Connection Pooling

```python
# Optimize for your workload
config = DatabaseConfig(
    database_url,
    pool_size=10,      # Base connections
    max_overflow=20,   # Burst capacity
    pool_timeout=30,   # Wait time for connections
    pool_recycle=3600  # Refresh connections hourly
)
```

### Error Handling

```python
from sqlobjects.exceptions import DatabaseError

try:
    async with ctx_session() as session:
        # Database operations
        pass
except DatabaseError as e:
    # Handle database-specific errors
    logger.error(f"Database error: {e}")
except Exception as e:
    # Handle general errors
    logger.error(f"Unexpected error: {e}")
```

### Testing Setup

```python
import pytest

@pytest.fixture
async def test_db():
    # Isolated test database
    db = await init_db(
        "sqlite+aiosqlite:///:memory:",
        name="test",
        is_default=False
    )
    await create_tables(ObjectModel, "test")
    yield db
    await close_db("test")
```

## Web Framework Integration

### ASGI Middleware (Starlette / FastAPI)

`SessionMiddleware` provides automatic request-scoped session management for any ASGI framework:

```python
from fastapi import FastAPI
from sqlobjects.contrib.asgi import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware)
# Each request now gets an auto-managed session (commit on success, rollback on error)

# Optional: specify database name and readonly mode
app.add_middleware(SessionMiddleware, db_name="analytics", readonly=True)
```

### FastAPI Dependency Injection

`get_db_session` is a FastAPI dependency that yields a transactional session:

```python
from fastapi import Depends
from sqlobjects.contrib.fastapi import get_db_session
from sqlobjects.session import AsyncSession

@app.post("/users")
async def create_user(session: AsyncSession = Depends(get_db_session)):
    user = await User.objects.using(session).create(name="Alice")
    return {"id": user.id}
```