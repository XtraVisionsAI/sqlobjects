# Persistence and query contracts

The ORM uses SQLAlchemy Core for SQL and connection management. These contracts
define the behavior of its model and QuerySet APIs. Regression coverage lives in
`tests/integration/test_orm_contracts.py` and runs against SQLite, PostgreSQL and
MySQL in CI.

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

`get_or_create()` isolates creation with a savepoint and retries the lookup after
an integrity conflict. Database uniqueness on the lookup fields is required for
concurrent uniqueness. Unrelated integrity errors propagate. `update_or_create()`
locks an existing row within its write transaction where the database supports it.
Outside SQLite, explicit `select_for_update()` / `select_for_share()` reads require
an explicit transaction. Isolation-level serialization failures and deadlocks
still need application-level retries.

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

## Verification and remaining work

CI runs the SQLite unit/integration suite, the cross-database contract suite and
additional PostgreSQL integration tests. Tagged publication depends on these
checks. Some older tests are not portable: index-only test models include invalid
PostgreSQL DDL, and performance tests use fixed timing ratios. They are not part
of the cross-database contract job.

Local verification on 2026-10-08 used Python 3.12 and SQLAlchemy 2.0.44:

| Database | Scope | Result |
| --- | --- | --- |
| SQLite | Unit and integration suite | 524 passed; one row-lock test skipped because SQLite has no SELECT FOR UPDATE. |
| PostgreSQL 16 | Contracts, CRUD, relationships, deferred fields, bulk results and cascades | 160 passed. |
| MySQL 8.4 | Contract suite with aiomysql and its RSA authentication extra | 33 passed. |

Ruff lint and formatting passed. Pyright reported zero errors and three existing
unnecessary-ignore warnings. SQLite retains two existing DISTINCT ON dialect
warnings. The workflow definitions were checked locally; hosted CI results will
be available after the changes are pushed.

Further work from the ORM review includes task-safe session ownership,
commit callbacks, Alembic examples, unified query instrumentation, realistic
performance benchmarks and broader driver/version coverage. These are separate
from the persistence and query corrections described here.
