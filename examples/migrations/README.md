# Async Alembic example

Run these commands from the repository root:

```bash
uv sync --group test
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
uv run --no-sync alembic -c examples/migrations/alembic.ini current
```

The default SQLite database is `examples/migrations/example.db` (Git-ignored).
To use a different database, set `SQLOBJECTS_MIGRATION_URL` to an async SQLAlchemy
URL, such as `postgresql+asyncpg://...` or `mysql+aiomysql://...`.

`0001_accounts` creates accounts with an email address. `0002_display_names` adds
a nullable display name, copies existing email addresses into it, then enforces
NOT NULL and adds an index. The current model describes the schema at head.

Generate a migration after editing the model:

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini revision --autogenerate -m "change accounts"
# Review the generated upgrade and downgrade, then apply it.
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
```

For a disposable example database, exercise downgrade and offline SQL:

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini downgrade 0001_accounts
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head --sql
```

Downgrading to `0001_accounts` discards display names; downgrading to `base`
drops the account table. The example owns tables prefixed `migration_` and uses
`migration_example_version` for revision tracking. Adapt both when copying it.

See [the migration guide](../../docs/features/09-migrations.md) for application
setup, connection sharing, historical schemas and cross-database details.
