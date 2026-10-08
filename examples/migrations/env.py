"""Alembic environment for an async SQLObjects application."""

import asyncio
import os

from alembic import context
from alembic.autogenerate import rewriter
from alembic.operations import ops
from sqlalchemy import Connection, Identity, pool
from sqlalchemy.ext.asyncio import create_async_engine

from examples.migrations.models import MigrationBase


config = context.config
# Import every model module before selecting its registry.
target_metadata = MigrationBase.__registry__
rewrites = rewriter.Rewriter()


@rewrites.rewrites(ops.AlterColumnOp)
def omit_unsupported_identity(migration_context, revision, operation):
    # SQLite/MySQL ignore SQL standard Identity in DDL and cannot reflect it.
    # Remove only that impossible alteration, retaining real default/type changes.
    if not migration_context.dialect.supports_identity_columns and isinstance(
        operation.modify_server_default, Identity
    ):
        operation.modify_server_default = False
    return operation if operation.has_changes() else []


def database_url() -> str:
    # Read the environment directly so percent-encoded credentials are not
    # interpreted by ConfigParser. Never print this URL.
    url = os.environ.get("SQLOBJECTS_MIGRATION_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise ValueError("Set SQLOBJECTS_MIGRATION_URL or sqlalchemy.url")
    return url


def include_name(name, type_, parent_names):
    # An ownership prefix also includes tables removed from current models,
    # allowing autogenerate to detect their removal without touching other apps.
    return type_ != "table" or (name is not None and name.startswith("migration_"))


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="migration_example_version",
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=rewrites,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        version_table="migration_example_version",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        run_migrations(supplied_connection)
    else:
        asyncio.run(run_async_migrations())
