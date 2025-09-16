# Database Setup and Configuration

## Overview

SQLObjects provides flexible database configuration supporting single and multiple databases with automatic connection management, session handling, and transaction control.

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

# Initialize multiple databases - returns Database instance tuple
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
    echo=False  # Set True for SQL logging
)

db = await init_db(config.url, **config.engine_kwargs)
```

### Environment-Based Configuration

```python
import os

# Development
if os.getenv("ENV") == "development":
    db_url = "sqlite+aiosqlite:///dev.db"
    echo = True
# Production
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
    # Automatic commit on success, rollback on error

# Specific database session
async with ctx_session("analytics") as session:
    logs = await Log.objects.using(session).all()

# Multiple database sessions
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    await Log.objects.using(sessions["analytics"]).create(message="User created")

# Session with specific database
async with ctx_session("analytics") as session:
    users = await User.objects.using(session).all()
```

### Default Session Usage

```python
# Uses default database automatically
user = await User.objects.create(username="charlie")
users = await User.objects.filter(User.is_active == True).all()
```

## Transaction Patterns

### Unified Transactions

```python
# All operations in single transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="david")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    # Automatic commit on success, rollback on error
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

# Direct SQLAlchemy event registration
@event.listens_for(db.engine.sync_engine, "connect")
def setup_connection(dbapi_connection, connection_record):
    # Configure connection settings
    pass
```

## Connection Lifecycle

### Graceful Shutdown

```python
from sqlobjects.database import close_db, close_dbs, close_all_dbs

# Close specific database by name
await close_db("analytics")

# Close with automatic default reassignment
await close_db("main", auto_default=True)

# Close multiple specific databases
await close_dbs(["analytics", "backup"])

# Close all databases
await close_all_dbs()

# Close Database instance directly
await analytics_db.close()
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

## Best Practices

### Connection Pooling

```python
# Optimize for your workload
config = DatabaseConfig(
    database_url,
    pool_size=10,      # Base connections
    max_overflow=20,   # Burst capacity
    pool_timeout=30,   # Connection wait time
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