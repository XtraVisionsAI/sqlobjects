"""Create the account schema before display names were introduced."""

import sqlalchemy as sa
from alembic import op


revision = "0001_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_accounts",
        sa.Column("id", sa.Integer(), sa.Identity(start=1, increment=1, cycle=False), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_migration_accounts"),
        sa.UniqueConstraint("email", name="uq_migration_accounts_email"),
    )


def downgrade() -> None:
    op.drop_table("migration_accounts")
