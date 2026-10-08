# Schema migrations with Alembic

SQLObjects registries inherit SQLAlchemy `MetaData`, so Alembic can compare them
with a database directly. Use migrations to evolve an existing schema;
`create_tables()` only creates missing tables and does not upgrade existing ones.

## Installation and runnable example

For an application, install the optional migration dependency and its async driver:

```bash
pip install 'sqlobjects[migrations]' asyncpg
```

Use `aiosqlite` for SQLite or `aiomysql[rsa]` for MySQL instead. The core ORM does
not require Alembic. The repository test dependency group includes all three
drivers and Alembic.

The complete [example](../../examples/migrations/README.md) contains `alembic.ini`,
an async `env.py`, a revision template, models and two historical revisions.
From the repository root:

```bash
uv sync --group test
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
```

This uses a local SQLite file in the example directory. Set
`SQLOBJECTS_MIGRATION_URL` to select a different async database URL. The environment
reads this value directly, preserving percent-encoded credentials without routing
them through INI interpolation. Configuration and model imports work when the
CLI is invoked from another directory using an absolute `-c` path.
When copying the example into an application, update the model import,
`prepend_sys_path`, table ownership filter and version-table name for that project.

## Isolate the application's metadata

Declare an explicit registry before creating concrete models:

```python
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel

class AppModel(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
    )

# All concrete application models inherit AppModel.
target_metadata = AppModel.__registry__
```

Explicit `__registry__` must be a `ModelRegistry`. Subclasses inherit that exact
registry unless they explicitly override it. Models without an explicit registry
keep the shared default behavior. Import every model module before assigning
Alembic's `target_metadata`; the registry contains only models already imported.

Metadata isolation alone does not restrict which existing database tables Alembic
reflects. The example's `include_name` filter owns the `migration_` table prefix.
This excludes other applications' tables while still detecting removal of a
previously managed table. Choose a stable ownership rule for your application;
filtering only by the current model names would hide table removals. Separate
migration histories also need distinct version tables or separate databases.

## Generate and apply schema changes

First bring the development database to the current revision. Edit models, then:

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini revision --autogenerate -m "add account field"
# Inspect and edit the generated revision.
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
```

`check` exits nonzero when schema differences would produce migration operations.
It requires the database to be at the current revision head. Autogenerate compares
schema, not ORM validation, signals or Python defaults. Column/table renames may
appear as drop/add operations and need manual correction. Custom database types,
views, triggers and data transformations may also require handwritten operations.
See [Alembic's autogenerate limitations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect).

The example compares types and server defaults. Its revision rewriter removes
only Identity alterations on dialects without SQL standard Identity support:
SQLite and MySQL use their own integer autoincrement behavior. PostgreSQL Identity
changes and ordinary server-default changes still participate in comparison.
Generate and review revisions against your deployment dialect.

## Changes to generated schema names

SQLObjects now bounds its automatic constraint and index names to 63 UTF-8 bytes.
Long names and generated-name collisions receive a stable hash suffix; explicit
names and names already assigned by SQLAlchemy conventions remain unchanged.
See [automatic schema names](02-model-definition.md#automatic-schema-names).

Existing databases may have older full names, server-truncated names or indexes
shortened by SQLAlchemy. Inspect the deployment database before generating a
revision. To retain an existing object, explicitly name it with its physical name
in the model configuration. To adopt the new name, write a rename or drop/create
operation appropriate for the deployment dialect; SQLite constraint changes may
need batch mode. Alembic can report index/unique-name changes as drop/create, and
CHECK-name changes may not appear in autogenerate at all. Review the revision
rather than treating an empty `check` result as proof that every name agrees.

## Migrate existing data with historical definitions

The second revision demonstrates adding a required field to populated tables:

1. Add `display_name` as nullable.
2. Backfill it from the existing email column using a Core UPDATE.
3. Change it to NOT NULL and create its index.

Revision files use local SQLAlchemy table/column definitions. They do not import
current application models, call `save()`, or trigger current validation/signals.
That keeps old revisions runnable after the model API changes. Python defaults
do not backfill stored rows; write explicit data operations or server defaults.

The example uses one UPDATE for a small table. Large deployments should separate
schema expansion, batched backfill and constraint enforcement, and coordinate
concurrent application writes. SQLite batch alterations may rebuild a table;
MySQL DDL can commit implicitly, so a failed migration is not guaranteed to undo
earlier steps. Downgrade to `0001_accounts` preserves email/id but loses display
names; downgrade to `base` removes the account table.

## Reuse an existing async connection

For application-controlled migration execution, pass the synchronous connection
provided by `AsyncConnection.run_sync()` through Alembic's configuration:

```python
from alembic import command
from alembic.config import Config
from sqlobjects.database import get_database

def upgrade(connection):
    config = Config("examples/migrations/alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")

async with get_database().engine.begin() as connection:
    await connection.run_sync(upgrade)
```

The example environment borrows this connection without closing or disposing it.
Without one, the CLI creates an async engine with `NullPool`, runs migrations via
`run_sync()`, and disposes the engine in `finally`. Avoid calling the synchronous
Alembic command directly inside a running event loop without supplying a
connection; the CLI path uses `asyncio.run()`. Run a coordinated migration job
before application workers start. For multiple databases, migrate each alias
separately; this is not a distributed transaction.

This follows Alembic's documented
[asyncio and connection-sharing recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).

## Offline SQL

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head --sql
uv run --no-sync alembic -c examples/migrations/alembic.ini downgrade 0002_display_names:base --sql
```

Offline mode compiles existing revisions without connecting. It cannot discover
model/database differences. SQLite batch mode normally needs reflection; this
example supplies each revision's historical `copy_from` table to support offline
SQL as well. Keep those definitions aligned with the schema at that revision.
Generated SQL targets the configured database dialect and revision range; it is
not an idempotent script to replay on an already upgraded database.
