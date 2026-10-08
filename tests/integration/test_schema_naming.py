"""Generated names survive real DDL, reflection and migration comparison."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, event, inspect
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.schema import AddConstraint, CreateIndex, DropConstraint, DropIndex

from sqlobjects.database import close_db, init_db
from sqlobjects.fields import Column, IntegerColumn, StringColumn, identity
from sqlobjects.metadata import ModelRegistry, constraint, foreignkey, index, unique
from sqlobjects.model import ObjectModel
from tests.test_config import TestDatabaseConfig


class NamingBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class NamingParent(NamingBase):
    first_component_identifier: Column[int] = IntegerColumn(primary_key=True, nullable=False)
    second_component_identifier: Column[int] = IntegerColumn(primary_key=True, nullable=False)
    external_account_identifier: Column[str] = StringColumn(length=40)
    external_sequence_identifier: Column[int] = IntegerColumn()

    class Config:
        table_name = "external_transaction_processing_records"
        indexes = [index(None, "first_component_identifier", "external_sequence_identifier")]
        constraints = [
            unique("external_account_identifier", "external_sequence_identifier"),
            constraint("first_component_identifier >= 0"),
            constraint("first_component_identifier < 100"),
        ]


class NamingChild(NamingBase):
    id: Column[int] = identity()
    first_component_identifier: Column[int] = IntegerColumn()
    second_component_identifier: Column[int] = IntegerColumn()

    class Config:
        table_name = "external_transaction_relationship_entries"
        constraints = [
            foreignkey(
                ["first_component_identifier", "second_component_identifier"],
                [
                    "external_transaction_processing_records.first_component_identifier",
                    "external_transaction_processing_records.second_component_identifier",
                ],
            )
        ]


class NamingUnicode(NamingBase):
    id: Column[int] = identity()
    customer: Column[str] = StringColumn(length=30, unique=True)
    sequence: Column[int] = IntegerColumn(index=True)

    class Config:
        table_name = "业务数据" * 5


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own isolated metadata and transaction boundaries."""


@pytest.fixture
async def naming_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'naming.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    if db_type == "sqlite":
        # These DDL tests use Core connections, bypassing AsyncSession's PRAGMA.
        @event.listens_for(db.engine.sync_engine, "connect")
        def foreign_keys_on(connection, record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    try:
        await db.create_tables(NamingBase)
        yield db
    finally:
        await db.drop_tables(NamingBase)
        await close_db()


async def test_physical_names_match_metadata_and_migrations(naming_db):
    def verify(connection):
        inspector = inspect(connection)
        for table in NamingBase.__registry__.tables.values():
            reflected = {
                item["name"]
                for method in [
                    inspector.get_indexes,
                    inspector.get_unique_constraints,
                    inspector.get_foreign_keys,
                    inspector.get_check_constraints,
                ]
                for item in method(table.name)
            }
            for item in [*table.constraints, *table.indexes]:
                if item.name is not None:
                    assert len(str(item.name).encode("utf-8")) <= 63
                    assert item.name in reflected
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, NamingBase.__registry__) == []

    async with naming_db.engine.connect() as connection:
        await connection.run_sync(verify)


@pytest.mark.parametrize("failure", ["check_lower", "check_upper", "unique", "foreign_key"])
async def test_named_constraints_are_enforced(naming_db, failure):
    parent, child = NamingParent.__table__, NamingChild.__table__
    values = {
        "first_component_identifier": 1,
        "second_component_identifier": 2,
        "external_account_identifier": "account",
        "external_sequence_identifier": 3,
    }
    async with naming_db.engine.begin() as connection:
        await connection.execute(parent.insert().values(values))
        await connection.execute(child.insert().values(first_component_identifier=1, second_component_identifier=2))
    statement = parent.insert().values(values | {"second_component_identifier": 4})
    if failure == "check_lower":
        statement = parent.insert().values(
            values | {"first_component_identifier": -1, "external_sequence_identifier": 5}
        )
    elif failure == "check_upper":
        statement = parent.insert().values(
            values | {"first_component_identifier": 100, "external_sequence_identifier": 5}
        )
    elif failure == "foreign_key":
        statement = child.insert().values(first_component_identifier=1, second_component_identifier=9)
    with pytest.raises(DBAPIError) as error:
        async with naming_db.engine.begin() as connection:
            await connection.execute(statement)
    if failure.startswith("check") and naming_db.engine.dialect.name == "mysql":
        assert error.value.orig is not None
        assert error.value.orig.args[0] == 3819  # MySQL reports CHECK violations as OperationalError.
    else:
        assert isinstance(error.value, IntegrityError)


async def test_generated_names_can_be_used_to_drop_and_recreate_schema_objects(naming_db):
    async with naming_db.engine.begin() as connection:
        for table in NamingBase.__registry__.tables.values():
            for idx in table.indexes:
                await connection.execute(DropIndex(idx))
                await connection.execute(CreateIndex(idx))
            if connection.dialect.name != "sqlite":
                for item in table.constraints:
                    if isinstance(item, (CheckConstraint, UniqueConstraint, ForeignKeyConstraint)):
                        await connection.execute(DropConstraint(item))
                        await connection.execute(AddConstraint(item))
