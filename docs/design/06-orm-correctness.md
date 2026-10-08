# Persistence and query contracts

The ORM uses SQLAlchemy Core for SQL and connection management. These contracts
define the behavior of its model and QuerySet APIs. Regression coverage lives in
`tests/integration/test_orm_contracts.py`, `test_commit_callbacks.py`,
`test_query_logging_contracts.py`, `test_distinct_contracts.py`,
`test_signal_contracts.py`, `test_database_events.py`,
`test_dynamic_relationships.py`, `test_aggregate_contracts.py`,
`test_grouped_aggregation.py` and `test_schema_naming.py`. These run against SQLite, PostgreSQL and MySQL in CI.

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

### Signal execution

Manager `create()` emits instance save/create hooks around an INSERT even when
the caller supplies a primary key. Before hooks can change values before
validation; after hooks see the persisted object. It joins an explicit writable
transaction or owns one spanning hooks and SQL. QuerySet update/delete hooks use
the same transaction and database binding as the write; unsupported write clauses
are rejected before any hook runs.

Manager bulk hooks run once per batch inside its actual transaction or savepoint.
Create/update emit generic bulk-save hooks followed by operation-specific hooks;
bulk methods do not emit instance hooks. Before counts describe batch input;
after counts match that batch's successful result. Empty input emits no hooks.
QuerySet before counts remain unknown, and its after count is the returned count.

Hook errors propagate under every error policy and roll back owned transactions
or savepoints. Callers control rollback when joining an explicit transaction.
Commit-callback errors also propagate, without reclassifying committed records
as failed input. These boundaries let `context.on_commit()` track all four bulk
transaction modes correctly. See the [signal guide](../features/06-validation-signals.md)
for context fields and direct instance-save behavior.

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

`distinct()` applies ordinary SQL DISTINCT to the selected columns, including
projected values and rows duplicated by joins. Its enabled state survives cloning
even with no field arguments. `distinct(*fields)` requires known model columns
and PostgreSQL's DISTINCT ON. SQLite/MySQL reject it before execution, including
inside counts, existence checks, streaming, subqueries, CTEs and EXPLAIN. This follows
[Django's distinction between ordinary DISTINCT and PostgreSQL DISTINCT ON](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#distinct).
`aggregate()` uses the same statement for execution, SQL rendering, scalar
subqueries and EXPLAIN. Filters (including Q objects, keyword filters and bound
extra WHERE clauses), joins and CTEs survive composition. DISTINCT, annotations
and slices aggregate through a derived table; ordinary unsliced aggregation uses
a direct SELECT. Ordering is retained when slicing or DISTINCT ON needs it.

Aggregate inputs are remapped to the derived table, including deferred model
fields and annotation aliases. Joined/scalar inputs after ordinary DISTINCT must
already be projected; adding them implicitly would change the deduplication key.
Scalar inputs keep their local query scope, and correlated aggregate subqueries
work across the supported backends. Projection of only a scalar expression now
retains the model's FROM clause. Empty inputs preserve SQL aggregate defaults.
Explicit GROUP BY queries can now be summarized by `aggregate()`. A derived table
selects only grouping keys and annotations, preserving HAVING, DISTINCT, slices
and CTEs. Outer aggregates reference grouping keys or annotation aliases; direct
model fields outside the grouping keys are rejected. Empty inputs keep SQL
aggregate defaults. The grouped values API still returns individual group rows.
HAVING without explicit grouping and row locking remain unsupported.

Native SQLAlchemy grouping expressions now retain their expression and source
table instead of being reduced to a field name. Ordering by annotation aliases
also works, so slices select the intended groups. Constant groups use projected
aliases to avoid MySQL treating numeric literals as select-list ordinals.
Annotations cannot shadow model columns in grouped terminal aggregation.
This extends the [Django-style aggregation of annotations](https://docs.djangoproject.com/en/5.2/topics/db/aggregation/#aggregating-annotations)
while keeping SQLObjects' explicit `group_by()` API.

This follows [Django's filtered aggregation and annotation composition](https://docs.djangoproject.com/en/5.2/topics/db/aggregation/)
and uses [SQLAlchemy's derived-table and scalar-subquery APIs](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#subqueries-and-ctes).
The [query guide](../features/03-querying-data.md#aggregating-composed-queries)
documents the supported combinations and boundaries.

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

### Dynamic collections

`lazy="dynamic"` now returns a working `RelatedQuerySet` proxy instead of a
placeholder. Building a query does not execute SQL. Each new query captures the
parent's current reference values and database/session binding, then delegates
to the ordinary QuerySet for filtering, ordering, projection, counting, streaming
and writes. QuerySets already built retain their original scope. Hydration uses
normal persisted state and database alias retention.

Reverse relationships use real FK mappings, including non-primary and composite
references. Many-to-many relationships use a membership subquery over the existing
association table, so repeated links do not duplicate target rows. Explicit
`M2MTable` mappings support custom columns. Model names resolve in the owning
registry; unrelated registries can safely contain models with the same names.

Dynamic `fetch()` and `load_relation()` issue new queries without replacing the
proxy with cached rows. Synchronous iteration, truthiness and length are rejected
in favor of async iteration, `exists()` and `count()`. The parent must have complete
primary key values, and deferred reference fields must be loaded explicitly.
Null reference values yield an empty query. Eager-loading paths through dynamic
relationships, scalar dynamic relationships and custom join conditions are
rejected. This proxy does not add relationship add/remove/set or creation methods.

Cross-database coverage also exposed a nullable type inference bug:
`Column[int | None]` with `column()` or `foreign_key()` was inferred as a string.
The mapper now recognizes PEP 604 unions alongside `Optional[T]`, retaining the
integer SQL type; the self-referencing dynamic-collection test creates and queries
this FK on all three databases.

This adopts the queryable-collection pattern described by
[Django's related manager](https://docs.djangoproject.com/en/5.2/ref/models/relations/)
using SQLObjects' async Core QuerySet. SQLAlchemy documents its legacy dynamic
loader's [async and implicit-iteration limitations](https://docs.sqlalchemy.org/en/20/orm/large_collections.html#dynamic-relationship);
SQLObjects keeps evaluation explicit and uses its existing async streaming path.
See the [dynamic collection guide](../features/05-relationships.md#dynamic-collections).

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

## Database event registration

`db.on(name, **options)` registers native SQLAlchemy Engine, Pool and Dialect
listeners on the selected database's `engine.sync_engine`. The decorator retains
the listener's identity and signature, forwards options such as `named` and
`retval`, and supports removal with `sqlalchemy.event.remove`. Unknown names and
invalid options retain SQLAlchemy's validation. Listeners are scoped to one
engine; register before opening connections that should observe them.

SQLAlchemy events run synchronously even with async drivers. Coroutine functions,
async callable objects and async-generator functions are rejected at registration;
ordinary synchronous listeners must not return awaitables. Native connection and
pool callback arguments are passed through, including SQLAlchemy 2.x's third
`reset_state` argument for pool reset. Listener exceptions follow SQLAlchemy's
event rules, independently of the SQL logger's handler-error isolation.

The previously advertised `before_commit`, `after_commit`, `before_rollback` and
`after_rollback` names do not belong to Engine events and now produce actionable
errors. `commit` and `rollback` intercept attempts before the driver completes
them; they cannot confirm success. For effects after a successful transaction,
use `await session.on_commit(callback)`. Tests verify event/driver/callback order
and callback suppression when either an event listener or the driver commit fails.

See the [event usage guide](../features/01-database-setup.md#database-events) and
[SQLAlchemy's async event contracts](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension).

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

## Portable generated schema names

SQLObjects bounds its generated CHECK, UNIQUE, foreign key and index names to
63 UTF-8 bytes, retaining short names and adding a readable prefix plus a stable
SHA-256 suffix for long names. This handles both composite keys and multibyte
identifiers without relying on server truncation. Generated-name collisions use
the constraint/index definition to select distinct names. Explicit names and
names already assigned by SQLAlchemy naming conventions keep their existing rules.
Field/helper indexes share the same naming path; explicit index names take
precedence during deduplication. Partial-index comparisons include bound values.

[SQLAlchemy's deterministic truncation](https://docs.sqlalchemy.org/en/20/core/constraints.html#truncation-of-long-names)
informed this approach. SQLObjects bounds the metadata name itself using
[PostgreSQL's byte limit](https://www.postgresql.org/docs/current/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS),
so the resulting physical name is shared across the supported backends.
The tests exercise real DDL, reflection, constraint enforcement, drop/recreate and
Alembic comparison, including Unicode names and long composite foreign keys.

Existing long/colliding names need a reviewed migration or explicit names that
pin the current database identifiers. CHECK changes are not fully covered by
Alembic autogenerate. See the [migration guide](../features/09-migrations.md#changes-to-generated-schema-names).
Table/column names and database-wide collisions between explicitly named objects
remain the application's responsibility.

## Verification and remaining work

CI runs the SQLite unit/integration suite, the cross-database contract suite and
additional PostgreSQL integration tests. Tagged publication depends on these
checks. Some older tests are not portable: index-only test models include invalid
PostgreSQL DDL, and performance tests use fixed timing ratios. They are not part
of the cross-database contract job.

Local verification on 2026-10-08 used Python 3.12, SQLAlchemy 2.0.44 and Alembic 1.20.0:

| Database | Scope | Result |
| --- | --- | --- |
| SQLite | Unit and integration suite | 765 passed; one row-lock test skipped because SQLite has no SELECT FOR UPDATE. |
| PostgreSQL 16 | Contracts, commit callbacks, query logging, migrations, DISTINCT, signal contracts, database events, dynamic relationships, aggregation including grouped inputs, schema naming, CRUD, relationships, deferred fields, bulk results, cascades and signals | 385 passed. |
| MySQL 8.4 | Contracts, commit callbacks, query logging, migrations, DISTINCT, signal contracts, database events and dynamic relationships, aggregation including grouped inputs and schema naming with aiomysql and its RSA authentication extra | 249 passed; one executemany RETURNING test skipped because this backend does not support it. |

The 10 migration integration tests also pass with Alembic 1.16.5 on SQLite.

Ruff lint and formatting passed. Pyright reported zero errors and three existing
unnecessary-ignore warnings. SQLite no longer emits DISTINCT ON dialect warnings.
The workflow definitions were checked locally; hosted CI results will
be available after the changes are pushed.

Further work from the ORM review includes realistic performance benchmarks,
batched data-migration tooling and broader driver/version coverage. These are separate from the persistence and query
corrections described here.
