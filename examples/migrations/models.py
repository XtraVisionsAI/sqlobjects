"""Current application schema; migration revisions keep their own historical schema."""

from sqlobjects.fields import Column, StringColumn, identity
from sqlobjects.metadata import ModelRegistry, index, unique
from sqlobjects.model import ObjectModel


class MigrationBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
    )


class MigrationAccount(MigrationBase):
    id: Column[int] = identity()
    email: Column[str] = StringColumn(length=255, nullable=False)
    display_name: Column[str] = StringColumn(length=255, nullable=False)

    class Config:
        table_name = "migration_accounts"
        constraints = [unique("email", name="uq_migration_accounts_email")]
        indexes = [index("ix_migration_accounts_display_name", "display_name")]
