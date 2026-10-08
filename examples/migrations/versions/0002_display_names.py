"""Add a display name, backfill existing rows, then enforce NOT NULL."""

import sqlalchemy as sa
from alembic import op


revision = "0002_display_names"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None


def account_table(*, nullable: bool) -> sa.Table:
    # Historical schema makes SQLite batch mode work with --sql, without
    # reflection or imports from the application's changing model definitions.
    return sa.Table(
        "migration_accounts",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), sa.Identity(start=1, increment=1, cycle=False), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=nullable),
        sa.PrimaryKeyConstraint("id", name="pk_migration_accounts"),
        sa.UniqueConstraint("email", name="uq_migration_accounts_email"),
    )


def upgrade() -> None:
    op.add_column("migration_accounts", sa.Column("display_name", sa.String(255), nullable=True))
    accounts = account_table(nullable=True)
    op.execute(accounts.update().where(accounts.c.display_name.is_(None)).values(display_name=accounts.c.email))
    with op.batch_alter_table("migration_accounts", copy_from=accounts) as batch:
        batch.alter_column("display_name", existing_type=sa.String(255), existing_nullable=True, nullable=False)
    op.create_index("ix_migration_accounts_display_name", "migration_accounts", ["display_name"])


def downgrade() -> None:
    op.drop_index("ix_migration_accounts_display_name", table_name="migration_accounts")
    with op.batch_alter_table("migration_accounts", copy_from=account_table(nullable=False)) as batch:
        batch.drop_column("display_name")
