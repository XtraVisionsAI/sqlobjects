# Persistence and query contracts

The ORM uses SQLAlchemy Core for SQL and connection management. These contracts
define the behavior of its model and QuerySet APIs. Regression coverage lives in
`tests/integration/test_orm_contracts.py` and
`tests/integration/test_commit_callbacks.py`, with execution logging covered by
`tests/integration/test_query_logging_contracts.py`. All three run against SQLite,
PostgreSQL and MySQL in CI.

## Persisted and partial objects

Objects loaded from a database retain their database alias. Subsequent `save()`,
`delete()`, `refresh()` and deferred-field reads use that alias unless `using()`
overrides it. An explicitly bound session retains its existing lifetime rules.

Database hydration does not apply Python construction defaults to missing columns.
`only()` retains the primary key; unselected fields remain deferred. Assigning a
deferred field loads it locally and marks it dirty. Saving a persisted object
updates only assigned columns, so a stale object does not overwrite unrelated
changes. Saving an unchanged object performs no UPDATE. In-place mutation of a
mutable value still requires assigning the field to mark it dirty.

A new object uses INSERT and reads generated primary keys. Saving a newly
constructed object with an existing primary key retains the detached-object
update behavior. Concurrent updates to the same field remain last-writer-wins;
this change does not add optimistic version checks. Transaction rollback does not
rewind Python object state; discard or refresh affected instances.

## Writes and transaction boundaries

QuerySet `update()` and `delete()` reject LIMIT, OFFSET, grouping, HAVING, DISTINCT
and joins before issuing SQL. These clauses must never be silently discarded
when deriving a write from a read query.

Instance writes request writable sessions. Compound cascade operations and
implicit bulk writes own a transaction; operations inside an explicit writable
session participate in its transaction.

| Bulk mode | Boundary |
| --- | --- |
| `INHERIT` | Use the caller's transaction, or own one for the entire implicit call. |
| `INDEPENDENT` | Own one separate transaction across all batches on the same database. |
| `BATCH` | Own a separate transaction per batch; earlier committed batches survive later failures. |
| `SAVEPOINT` | Isolate each batch with a savepoint inside the caller's transaction, or inside one owned transaction. |

An SQL error outside a savepoint makes an explicit transaction unusable until
rollback. Catching the exception alone does not restore it. For recoverable errors:

```python
async with ctx_session() as session:
    try:
        async with await session.begin_nested():
            await User.objects.create(username="duplicate")
    except IntegrityError:
        pass
    await User.objects.create(username="next")
```

`COLLECT` and `IGNORE` isolate each attempted record with a savepoint. `COLLECT`
reports input indexes across batches. Independent connections can block on locks
held by an outer transaction; avoid writing those rows in an independent batch.
SQLite also limits concurrent writers at database level.

### Async task ownership and cleanup

An open session belongs to its owning asyncio task. Copying a ContextVar into a
child task does not clone its connection or transaction. ORM operations through
an inherited or explicitly passed parent session raise `TransactionError` before
touching the database. Each concurrent worker must open its own `ctx_session()`;
`join_ambient=True` cannot join another live task's transaction. These independent
transactions are not rolled back with the parent.

`has_session()` reports only a usable session for the current task. Sequential
handoff is supported after the previous owner task has finished, but a session
closed by its context manager remains closed. Implicit per-statement connection
release keeps the session object reusable for sequential operations.

Cancellation rolls back active context/request transactions. Session context
tokens are restored even when cleanup raises, and multi-database cleanup attempts
to close every session. Timeouts inside a transaction should use
`asyncio.timeout()`, since `wait_for()` creates a different task for a coroutine.
Low-level SQLAlchemy connections, result cursors and transaction handles exposed
by the API must also stay in their owning task.

This follows the [SQLAlchemy guidance on one session per concurrent task](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks).

`get_or_create()` isolates creation with a savepoint and retries the lookup after
an integrity conflict. Database uniqueness on the lookup fields is required for
concurrent uniqueness. Unrelated integrity errors propagate. `update_or_create()`
locks an existing row within its write transaction where the database supports it.
Outside SQLite, explicit `select_for_update()` / `select_for_share()` reads require
an explicit transaction. Isolation-level serialization failures and deadlocks
still need application-level retries.

### Commit callbacks

`await session.on_commit(callback)` queues a callable on an explicit writable
session, even before its first statement. `await on_commit(callback)` selects the
ambient session and executes immediately when no explicit transaction exists.
`SignalContext.on_commit()` uses the operation's session, including an instance
binding or a session passed to `save()`. Sync callbacks and awaitable return
values run in registration order after successful root commit.

Each callback retains its savepoint ancestry. Savepoint rollback removes its
callbacks and those from released descendants; release alone never runs them.
Root rollback, close or failed commit discards the entire queue. The savepoint
wrapper starts exactly one physical SAVEPOINT for
`async with await session.begin_nested()`, enforces task ownership and reverse
completion order, and treats cleanup of an already released savepoint as a no-op.

The committing connection is returned to the pool before dispatch. The committed
database alias is temporarily removed from ambient sessions so callback queries
use a fresh session, even with a one-connection pool. Explicit reuse of the
committing session is rejected during dispatch. Callbacks cannot undo committed
data: errors propagate and stop later callbacks unless `robust=True`, which logs
ordinary exceptions and continues. Cancellation always propagates.

Callbacks run inline and are not durable delivery. Use a transactional outbox for
crash-safe effects. Multi-database contexts commit each database sequentially;
callbacks do not provide a distributed commit boundary. These semantics follow
[Django's commit callback contracts](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit),
with async callback support and explicit session ownership.

## Bulk results

UPSERT processes every input row. When RETURNING can be matched by unique conflict
keys, results are restored to input order. Other cases execute per row. Returned
objects contain stored database values; missing UPDATE targets do not produce
fabricated objects. Backends without RETURNING fetch inserted or updated records
using their keys. This costs additional queries.

Accurate UPDATE counts can require individual execution on drivers that do not
report executemany row counts. `accurate_count=False` permits an approximate count
for those drivers. PostgreSQL and SQLite conflict handling and MySQL's
`INSERT IGNORE` / `ON DUPLICATE KEY UPDATE` keep their native dialect semantics.

## Query evaluation and relationships

`count()` counts the result of the composed query, including grouping, distinctness
and slicing. Scalar count subqueries use the same query shape.

`iterator()` streams the original query in bounded partitions and yields models,
preserving ordering, LIMIT, OFFSET and deferred fields. If iteration can stop
early, close it explicitly so the cursor and owned connection are released:

```python
from contextlib import aclosing

async with aclosing(User.objects.order_by("id").iterator(chunk_size=500)) as users:
    async for user in users:
        if should_stop(user):
            break
```

An iterator borrows an explicit session and leaves its lifetime to the caller.
MySQL streaming with prefetch is rejected because a live streaming cursor cannot
safely share its connection with prefetch queries; use explicit pagination.

`select_related()` selects and hydrates single-valued relationships, with an alias
per path. Collection relationships use `prefetch_related()`. Both resolve actual
relationship and foreign-key metadata, including non-primary referenced columns.
The conventional `author_id` to `author` shorthand uses that column's actual FK.
Invalid paths raise errors. Custom prefetch querysets must target the declared
related model. Sliced prefetch querysets are rejected until per-parent limits are
implemented; a global limit would truncate collections incorrectly.

## Query execution logging

The `sqlobjects.sql` logger observes each configured engine, covering model
writes, bulk operations, raw SQL and streaming alongside QuerySet reads. Records
describe physical driver calls, including failures and cancellation; they do not
duplicate records at the QueryExecutor layer. Batched RETURNING records use each
batch's actual SQL and parameters rather than the original unbatched values.

Structured records include database alias, dialect, duration, driver row count,
executemany status and success/error type. `hide_parameters=True` suppresses bind
values on success and failure. Handler exceptions do not change the database
outcome. Caller lookup walks frames across SQLAlchemy's async greenlet bridge.
Disabled logging skips timing and stack inspection, and logging never recompiles
SQL. Timing measures cursor execution, excluding pool wait, compilation, later
fetching, hydration and commit. See the
[logging field contract](../features/01-database-setup.md#sql-logging) for format
changes from the old QueryExecutor logger.

Central execution instrumentation follows the purpose of
[Django's query instrumentation](https://docs.djangoproject.com/en/5.2/topics/db/instrumentation/),
implemented using the underlying
[SQLAlchemy dialect and connection events](https://docs.sqlalchemy.org/en/20/core/events.html)
so every ORM entry point shares the same recording path.

## Schema migrations

An explicit `__registry__ = ModelRegistry(...)` on a model or abstract base is
honored and inherited. Previously the metaclass silently replaced it with the
shared registry, leaking application tables into the wrong migration metadata.
The default shared registry remains available when no explicit one is supplied.

The optional `migrations` extra installs Alembic. The
[runnable example](../../examples/migrations/README.md) uses an async environment,
an isolated registry, an ownership filter and a dedicated version table. Two
historical revisions demonstrate schema creation and a required field backfill,
including SQLite batch operations with offline SQL support. It supports the CLI
and a caller-supplied connection through `run_sync()`.

`tests/integration/test_migrations.py` checks populated upgrades, downgrades,
generated revisions, ownership filtering, real default changes, ORM writes and
offline SQL. SQLite/MySQL Identity differences are filtered without suppressing
actual server-default changes. Alembic 1.16.5 and the lockfile version are both
tested locally on SQLite; the lockfile version is also exercised on PostgreSQL
and MySQL in CI.

## Verification and remaining work

CI runs the SQLite unit/integration suite, the cross-database contract suite and
additional PostgreSQL integration tests. Tagged publication depends on these
checks. Some older tests are not portable: index-only test models include invalid
PostgreSQL DDL, and performance tests use fixed timing ratios. They are not part
of the cross-database contract job.

Local verification on 2026-10-08 used Python 3.12, SQLAlchemy 2.0.44 and Alembic 1.20.0:

| Database | Scope | Result |
| --- | --- | --- |
| SQLite | Unit and integration suite | 608 passed; one row-lock test skipped because SQLite has no SELECT FOR UPDATE. |
| PostgreSQL 16 | Contracts, commit callbacks, query logging, migrations, CRUD, relationships, deferred fields, bulk results, cascades and signals | 251 passed. |
| MySQL 8.4 | Contracts, commit callbacks, query logging and migrations with aiomysql and its RSA authentication extra | 110 passed; one executemany RETURNING test skipped because this backend does not support it. |

The 10 migration integration tests also pass with Alembic 1.16.5 on SQLite.

Ruff lint and formatting passed. Pyright reported zero errors and three existing
unnecessary-ignore warnings. SQLite retains two existing DISTINCT ON dialect
warnings. The workflow definitions were checked locally; hosted CI results will
be available after the changes are pushed.

Further work from the ORM review includes realistic performance benchmarks,
batched data-migration tooling and broader driver/version coverage. These are separate
from the persistence and query corrections described here.
