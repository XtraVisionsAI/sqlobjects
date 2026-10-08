# Performance workloads

These tests exercise bulk CRUD, query projections, joins, relationship loading,
streaming, deferred fields, concurrent tasks and object lifetimes. They report
measurements while asserting results, persisted data, SQL counts and object
release. No test requires a universal speedup, elapsed-time limit, CPU percentage
or RSS ratio. A passing run confirms those contracts, not the absence of every
performance regression.

```bash
uv run --no-sync pytest tests/performance --db=sqlite -s
uv run --no-sync pytest tests/performance --db=sqlite \
  --junitxml=performance-sqlite.xml -o junit_family=legacy
```

PostgreSQL and MySQL use `POSTGRESQL_TEST_URL` and `MYSQL_TEST_URL`, with
`--db=postgresql` or `--db=mysql`. Use a disposable test database: each test creates
and drops the shared test tables. SQLite uses a temporary file, giving concurrent
workers distinct physical connections. Every worker opens its own session, and
seed data is committed before concurrent reads. Task groups finish or cancel all
workers before database teardown.

Each measurement appears as JSON in captured stdout and a `measurement` property
in JUnit XML. Units are explicit: wall-clock `seconds`, process `cpu_seconds`,
`rss_delta_mib`, and executed `statements`. Environment properties identify Python,
SQLAlchemy, operating system, database version and driver. CPU and RSS describe
the client process, not a separate database server. RSS is an end-minus-start
snapshot, not peak memory or retained object size; allocator reuse can make it
zero or negative. Garbage collection checks use weak references to establish
object release directly.

The large dataset fixture inserts 10,000 rows without hydrating and retaining a
duplicate object list. Full/deferred comparisons verify the actual selected
columns and loaded state. Relationship comparisons access the same related data:
`select_related()` uses one query instead of eleven; reverse prefetch uses two
instead of four for the fixed fixture. Deferred caching must issue no second SQL
query, and loading two deferred fields together halves the queries in that case.
Bulk comparisons measure the public APIs, including their different return-value
and signal behavior; they do not isolate driver execution time.

For timing comparisons, use the same machine, database settings, dependency
versions, selected test and dataset. Run once to warm up, then run the same command
at least three times in separate processes and compare the per-measurement median
and spread. Keep individual reports. CI uploads measurements from all three
databases for inspection; timings are observations rather than release gates.
The deterministic assertions remain CI gates.
