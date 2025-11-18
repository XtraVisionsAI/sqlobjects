# Database & Session Management Guide

## Core Concepts

- **DatabaseManager**: Global singleton managing multiple database connections
- **Session**: Task-level database session with automatic transaction management
- **Context Managers**: `ctx_session()` and `ctx_sessions()` for transaction control
- **using() Pattern**: Bind operations to specific sessions or databases

## Common Usage

### Single Database Setup

```python
from sqlobjects.database import init_db, create_tables
from sqlobjects.model import ObjectModel

# Initialize database
await init_db("sqlite+aiosqlite:///app.db")

# Create tables
await create_tables(ObjectModel)

# Use default session (automatic)
user = await User.objects.create(username="alice")
```

### Multi-Database Setup

```python
from sqlobjects.database import init_dbs

# Configure multiple databases
await init_dbs({
    "main": {"url": "postgresql+asyncpg://localhost/main", "pool_size": 20},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
}, default="main")

# Use specific database
user = await User.objects.using("analytics").create(username="analyst")
```

### Transaction Management

```python
from sqlobjects.session import ctx_session, ctx_sessions

# Single database transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="bob")
    posts = await user.posts.using(session).all()
    # Auto-commit on success, rollback on exception

# Multi-database transaction
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="alice")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
```

### Session Binding

```python
# Bind to session
async with ctx_session() as session:
    # All operations use the same session
    user = await User.objects.using(session).get(User.id == 1)
    user.email = "new@example.com"
    await user.using(session).save()

# Bind to named database
user = await User.objects.using("analytics").create(username="test")
```

## Best Practices

### ✅ Do

- **Use context managers** for explicit transaction control
- **Bind operations to sessions** in complex transactions
- **Configure connection pools** based on your workload
- **Use read-only sessions** for query-only operations
- **Close databases** properly on application shutdown

```python
# Good: Explicit transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    await Post.objects.using(session).create(title="First Post", author_id=user.id)

# Good: Connection pool configuration
await init_db(
    "postgresql://localhost/db",
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600
)
```

### ❌ Don't

- **Don't mix sessions** in related operations
- **Don't forget to close** database connections
- **Don't use tiny connection pools** in production
- **Don't create sessions manually** (use context managers)

```python
# Bad: Mixing sessions
async with ctx_session() as session1:
    user = await User.objects.using(session1).create(username="alice")
    async with ctx_session() as session2:
        # Different session - may cause issues
        await Post.objects.using(session2).create(author_id=user.id)

# Bad: No transaction control
user = await User.objects.create(username="alice")
# If next operation fails, user is already created
await Post.objects.create(title="Post", author_id=user.id)
```

## Performance Tips

### Connection Pooling

```python
# Production configuration
await init_db(
    "postgresql://localhost/db",
    pool_size=20,           # Base connections
    max_overflow=30,        # Burst capacity
    pool_timeout=30,        # Wait time for connection
    pool_recycle=3600,      # Recycle connections hourly
    pool_pre_ping=True      # Verify connections
)
```

### Session Reuse

```python
# Reuse session across operations
async with ctx_session() as session:
    # All operations share the same connection
    users = await User.objects.using(session).all()
    for user in users:
        await user.posts.using(session).all()
```

### Read/Write Separation

```python
# Use readonly parameter for read operations
from sqlobjects.session import get_session

# Read operations
session = get_session(readonly=True)
users = await User.objects.using(session).all()

# Write operations
session = get_session(readonly=False)
await User.objects.using(session).create(username="alice")
```

## Troubleshooting

### Connection Pool Exhausted

**Problem**: `TimeoutError: QueuePool limit exceeded`

**Solution**:
```python
# Increase pool size
await init_db(url, pool_size=30, max_overflow=50)

# Or use context managers to release connections
async with ctx_session() as session:
    # Connection released after block
    pass
```

### Transaction Deadlock

**Problem**: Operations hang or timeout

**Solution**:
```python
# Use shorter transactions
async with ctx_session() as session:
    # Keep transaction scope small
    user = await User.objects.using(session).get(User.id == 1)
    user.email = "new@example.com"
    await user.using(session).save()
# Transaction commits here

# Don't hold transactions during I/O
async with ctx_session() as session:
    user = await User.objects.using(session).get(User.id == 1)
# Transaction ends before external I/O
await send_email(user.email)  # Outside transaction
```

### Session Not Found

**Problem**: `RuntimeError: No session available`

**Solution**:
```python
# Always use context managers or explicit binding
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")

# Or bind to database name
user = await User.objects.using("main").create(username="alice")
```

### Database Connection Lost

**Problem**: `OperationalError: connection closed`

**Solution**:
```python
# Enable connection health checks
await init_db(url, pool_pre_ping=True, pool_recycle=3600)

# Handle connection errors gracefully
try:
    user = await User.objects.get(User.id == 1)
except OperationalError:
    # Reconnect or retry
    await init_db(url)
    user = await User.objects.get(User.id == 1)
```

## Complete Example

```python
from sqlobjects.database import init_dbs, create_tables, close_all_dbs
from sqlobjects.session import ctx_session, ctx_sessions
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)

class Log(ObjectModel):
    message: Column[str] = StringColumn(length=500)

async def main():
    # Setup
    await init_dbs({
        "main": {"url": "postgresql://localhost/main", "pool_size": 20},
        "analytics": {"url": "sqlite:///analytics.db"}
    }, default="main")
    
    await create_tables(ObjectModel, "main")
    await create_tables(ObjectModel, "analytics")
    
    # Single database transaction
    async with ctx_session() as session:
        user = await User.objects.using(session).create(
            username="alice",
            email="alice@example.com"
        )
    
    # Multi-database transaction
    async with ctx_sessions("main", "analytics") as sessions:
        user = await User.objects.using(sessions["main"]).get(User.username == "alice")
        await Log.objects.using(sessions["analytics"]).create(
            message=f"User {user.username} logged in"
        )
    
    # Cleanup
    await close_all_dbs()

# Run
import asyncio
asyncio.run(main())
```
