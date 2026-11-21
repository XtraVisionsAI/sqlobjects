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
    posts = await user.load_relation("posts")
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

### Recovering From Errors

An SQL error inside an explicit transaction leaves it unusable: the next
statement raises `TransactionError` until you call `rollback()`. Catching the
exception alone does not restore the transaction. To continue after a statement
that may fail, isolate it with a savepoint:

```python
async with ctx_session() as session:
    try:
        async with await session.begin_nested():
            await User.objects.create(username="duplicate")
    except IntegrityError:
        pass  # savepoint rolled back; the transaction stays usable
    await User.objects.create(username="next")
```

Readonly sessions hold no transaction and release their connection after each
statement, so a failed query there does not affect later queries. On an implicit
(auto-commit) session, `begin_nested()` opens a transaction only for its
savepoints; when the outermost savepoint ends, that transaction commits and the
connection is released. See
[Writes and transaction boundaries](../design/06-orm-correctness.md#writes-and-transaction-boundaries).

### Independent Transactions

Each worker must open its own session. Copying a context does not copy the session
or connection it contains. Inherited parent sessions cannot be used or joined from
another live asyncio task; SQLObjects raises `TransactionError` before issuing SQL.

```python
import asyncio

async def process_user(user_id):
    async with ctx_session():
        user = await User.objects.get(id=user_id)
        user.is_active = True
        await user.save()

await asyncio.gather(*(process_user(user_id) for user_id in user_ids))
```

Workers commit independently. To keep operations in one transaction, await them
sequentially in its owning task. For a timeout in that transaction, use
`asyncio.timeout()`; `asyncio.wait_for()` schedules a coroutine in another task.

After `close()` or context-manager exit, a session cannot be reopened. Background
work must create a fresh `ctx_session()` even if it inherited a request's context.
An implicit session's automatic connection release does not close the session
object, so sequential calls on it remain supported. An explicitly managed session
may be handed off only after its previous owning task has finished.

### Actions After Commit

Use `await session.on_commit(callback)` or the `on_commit()` helper for effects
that should run only after a successful transaction. Pass a callable; both sync
functions and functions returning awaitables are supported.

```python
from functools import partial
from sqlobjects.session import ctx_session, on_commit

async with ctx_session() as session:
    user = await User.objects.create(username="alice")
    await session.on_commit(partial(invalidate_user_cache, user.id))
    await on_commit(partial(notify_user_created, user.id), robust=True)
    # Both callbacks wait until this context successfully commits.
```

Callbacks run in registration order and are awaited inline. Root rollback,
cancellation before commit and session close discard pending callbacks. Savepoint
rollback discards callbacks registered in that savepoint and its descendants;
releasing a savepoint leaves them waiting for root commit. Use
`async with await session.begin_nested()` or the returned savepoint's
`commit()` / `rollback()` methods, completing nested savepoints in reverse order.

An explicit writable session queues callbacks even before its first SQL statement.
Outside a transaction the helper executes immediately. A named database or an
explicit session can be selected with `on_commit(callback, db_or_session)`.
Readonly, failed, closed and foreign-task sessions reject registration.

A callback failure cannot undo a completed commit. By default it propagates and
stops later callbacks; `robust=True` logs ordinary exceptions and continues.
Cancellation still propagates. The connection is released before dispatch, and
callback ORM calls use fresh sessions for the committed database. Explicitly
reusing the committing session from a callback raises `TransactionError`; open a
new `ctx_session()` if the callback needs a transaction.

Callbacks belong to an individual database transaction. `ctx_sessions()` commits
databases sequentially; it is not a distributed transaction, and one database's
callback may run before another database commits. These in-process callbacks are
not a durable delivery queue. Use a transactional outbox when delivery must
survive a process crash after commit.

## Database Events

`db.on(name, **options)` registers a synchronous listener on that database's
`engine.sync_engine`. Names, callback arguments and options follow SQLAlchemy's
[Engine, Pool and Dialect events](https://docs.sqlalchemy.org/en/20/core/events.html).
Register listeners before opening the connections they should observe.

### Connection and Transaction Events

```python
@db.on("connect")
def on_connect(dbapi_connection, connection_record):
    print("Database connected")

@db.on("commit")
def committing(connection):
    print("About to commit transaction")

@db.on("rollback")
def rolling_back(connection):
    print("About to roll back transaction")

@db.on("reset")
def resetting(dbapi_connection, connection_record, reset_state):
    # SQLAlchemy 2.x pool-reset signature includes reset_state.
    pass
```

Connection events such as `commit` receive a SQLAlchemy synchronous `Connection`;
pool events such as `connect` receive an adapted DBAPI connection. Neither is a
SQLObjects session. These handlers run synchronously inside SQLAlchemy's async
adaptation layer. Coroutine functions, async callable objects and async-generator
functions are rejected at registration. A synchronous handler must not return an
awaitable. See [SQLAlchemy's async event guidance](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension)
for driver-specific async setup via an adapted connection's `run_async()`.

`commit` and `rollback` intercept attempts, before the driver completes the
operation. A `commit` event can fire even if the commit subsequently fails.
`before_commit`, `after_commit`, `before_rollback` and `after_rollback` are not
Engine events; `db.on()` rejects them with guidance. The old examples using these
names were invalid. For effects after a successful commit, use:

```python
from sqlobjects.session import ctx_session

async with ctx_session() as session:
    await User.objects.using(session).create(username="alice")
    await session.on_commit(lambda: print("Transaction committed"))
```

### Listener Options and Removal

```python
from sqlalchemy import event

@db.on("before_cursor_execute", named=True, retval=True)
def annotate_statement(statement, parameters, **kwargs):
    return statement + " /* application */", parameters

# The decorator preserves the callable, so native removal works.
event.remove(db.engine.sync_engine, "before_cursor_execute", annotate_statement)
```

Options are forwarded to `sqlalchemy.event.listen`; their availability and return
contracts depend on the event. Unknown names and invalid options use SQLAlchemy's
validation. Listener exceptions propagate according to SQLAlchemy's event rules;
they are not handled by the SQL logger's error-isolation policy. Listeners belong
to one engine and do not observe other database aliases. Direct
`event.listens_for(db.engine.sync_engine, name)` registration remains available.

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
the logger name `sqlobjects.sql`. Each configured engine records driver cursor
executions at `DEBUG`, including QuerySets, instance writes, bulk operations,
raw SQL, streaming, and direct use of `db.engine`. Failed and cancelled driver
executions use the same logger. Logging never recompiles SQL; with `DEBUG`
disabled, event handlers skip timing and caller inspection.

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

| Field | Meaning |
| --- | --- |
| `sql` | SQL string passed to the driver, with expanded placeholders. |
| `params` | Driver parameters: dictionary, tuple, or a sequence of parameter sets; `None` when absent or hidden. |
| `duration_ms` | Driver execution time in milliseconds. |
| `db_name`, `dialect` | Configured database alias and SQL dialect. |
| `executemany` | Whether this driver call uses `executemany()`. |
| `rowcount` | Driver row count, often `-1` when unknown; `None` on failure. |
| `success`, `error_type` | Cursor execution outcome and exception class name, without exception messages or tracebacks. For database errors `error_type` is the SQLAlchemy exception class (for example `IntegrityError`), stable across drivers and SQLAlchemy versions. |
| `driver_error_type` | Class name of the exception raised by the driver; `None` on success. Driver- and version-specific, for example `UniqueViolationError` with asyncpg on SQLAlchemy 2.1. |

One record describes one driver call. A batched INSERT with RETURNING can produce
multiple records; a driver `executemany()` call produces one record for all its
parameter sets. Timing excludes pool checkout, SQL compilation, later result
fetching, model hydration and transaction commit. In particular, a successful
streaming execution does not imply that later fetching succeeded. Connection,
compilation and commit errors are outside this cursor-execution log.

Set `hide_parameters=True` when initializing a database to omit bind values from
both successful and failed records:

```python
await init_db(database_url, hide_parameters=True)
```

This does not redact literals already embedded in raw SQL; use bound parameters.
Ordinary exceptions from a custom logging handler are suppressed so they cannot
roll back a successful write or replace the original database exception.

Compared with the previous QueryExecutor-only logger, `params` now uses the
driver's format rather than always a dictionary, and `duration_ms` measures
cursor execution rather than the surrounding session operation.

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
points at the line in your application that issued the query, including across
SQLAlchemy's async greenlet bridge. It works with any handler (including loguru's
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
