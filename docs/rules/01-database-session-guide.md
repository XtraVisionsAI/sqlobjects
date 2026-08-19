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

### Session Availability Check

```python
from sqlobjects.session import has_session

# Check if an explicit session is active
if has_session():
    # Inside a ctx_session() block — use the existing session
    pass

# Check for a specific database
if has_session("analytics"):
    pass
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
    "postgresql+asyncpg://localhost/db",
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
# DANGER: Nested ctx_session opens a SECOND physical connection
async with ctx_session() as session1:
    user = await User.objects.using(session1).create(username="alice")
    async with ctx_session() as session2:
        # ContextVar restore is safe, but session2 is a separate physical
        # connection with its own transaction:
        # - session1 won't see session2's uncommitted changes and vice versa
        # - if session2 writes a row that session1 holds a lock on, session2
        #   blocks forever while session1 sits idle-in-transaction waiting for
        #   this coroutine to return. The database deadlock detector CANNOT
        #   see this cycle — it manifests as request timeouts, and session1's
        #   locks block unrelated requests until then.
        await Post.objects.using(session2).create(author_id=user.id)

# Good: join the ambient session when running inside a possibly-active transaction
async with ctx_session(join_ambient=True) as session:
    # Reuses the outer session if one exists (no second connection);
    # creates a new one only at the top level. Lifecycle (commit/rollback/close)
    # belongs to the outermost owner.
    await Post.objects.using(session).create(author_id=user.id)

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
    "postgresql+asyncpg://localhost/db",
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
from sqlobjects.database import init_dbs, create_tables, close_dbs
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
        "main": {"url": "postgresql+asyncpg://localhost/main", "pool_size": 20},
        "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
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
    await close_dbs()

# Run
import asyncio
asyncio.run(main())
```

## Web Framework Integration

### ASGI Middleware

Use `SessionMiddleware` for automatic request-scoped session management in any ASGI framework (FastAPI, Starlette, etc.):

```python
from fastapi import FastAPI
from sqlobjects.contrib.asgi import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware)
# Each request gets an auto-managed session: commit on success, rollback on error

# Optional: target a specific database or use readonly mode
app.add_middleware(SessionMiddleware, db_name="analytics", readonly=True)
```

### FastAPI Dependency Injection

Use `get_db_session` for explicit session access in route handlers:

```python
from fastapi import Depends
from sqlobjects.contrib.fastapi import get_db_session
from sqlobjects.session import AsyncSession

@app.post("/users")
async def create_user(session: AsyncSession = Depends(get_db_session)):
    user = await User.objects.using(session).create(username="alice")
    return {"id": user.id}

@app.get("/users/{user_id}")
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)):
    user = await User.objects.using(session).get(User.id == user_id)
    return {"username": user.username}
```

## SQL Logging

SQLObjects ships zero-config SQL logging through the standard library `logging`
module. Every executed statement is logged at `DEBUG` level to the logger named
**`sqlobjects.sql`**. This logger is an `ObjectLogger` (installed automatically
on import) that rewrites each record's caller fields — `pathname`, `filename`,
`funcName`, `lineno` — to the first user-code frame, skipping internal
`sqlobjects.*` and `sqlalchemy.*` frames. Your log output therefore points at
the line in your application that issued the query, not at ORM internals.

### Enabling

```python
import logging

# Show SQL (and everything else) at DEBUG
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)

# Now queries emit DEBUG log records
users = await User.objects.filter(User.is_active == True).all()
```

To capture SQL only, without lowering the level of the rest of your app, attach
a dedicated handler to the `sqlobjects.sql` logger:

```python
import logging

sql_logger = logging.getLogger("sqlobjects.sql")
sql_logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(pathname)s:%(lineno)d - %(message)s"))
sql_logger.addHandler(handler)
```

Statement compilation only happens when the logger is actually enabled for
`DEBUG`, so leaving logging off has no runtime cost. Each record carries the
compiled SQL as the message plus an `extra` dict with `sql`, `params`, and
`duration_ms`.

### Public API

```python
from sqlobjects import ObjectLogger, get_caller_frame
```

- **`ObjectLogger`** — the `logging.Logger` subclass used for `sqlobjects.sql`.
  It accepts an `extra_skip_packages` list to skip additional module prefixes
  (e.g. your own middleware) when resolving the user-code frame.
- **`get_caller_frame(extra_skip_packages=None, max_frames=1)`** — returns the
  first user-code frame as a `"path:lineno in func"` string (or a list when
  `max_frames > 1`), applying the same skip rules. Useful for custom logging.
