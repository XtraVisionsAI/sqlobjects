"""Declared index expressions and order survive table creation on real backends."""

import pytest
from sqlalchemy import Index, column, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, DropIndex

from sqlobjects.database import close_db, init_db
from sqlobjects.fields import Column, IntegerColumn, StringColumn, identity
from sqlobjects.metadata import ModelRegistry, index
from sqlobjects.model import ObjectModel
from tests.test_config import TestDatabaseConfig


class IndexBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class IndexRecord(IndexBase):
    id: Column[int] = identity()
    tenant: Column[int] = IntegerColumn()
    code: Column[str] = StringColumn(length=30)
    amount: Column[int] = IntegerColumn()

    class Config:
        table_name = "index_contract_records"
        indexes = [
            index("ix_tenant_code", "tenant", "code"),
            index("ix_code_tenant", "code", "tenant"),
            Index("ix_ascending", column("tenant").asc(), column("amount").asc()),
            Index("ix_mixed", column("tenant").asc(), column("amount").desc()),
            Index("a_raw_amount", "amount", unique=True),
            Index("z_absolute_amount", func.abs(column("amount")), unique=True),
            Index("a_unique_code", "code", unique=True),
            Index("ix_lower_code", func.lower(column("code"))),
            Index("ix_cover_code", "code", postgresql_include=["tenant"]),
            Index("ix_postgresql_only", "code").ddl_if(dialect="postgresql"),
            Index("ix_always_tenant", "tenant"),
            Index("ix_conditional_unique_tenant", "tenant", unique=True).ddl_if(dialect="postgresql"),
        ]


@pytest.fixture(autouse=True)
def clean_db():
    """The schema and transaction boundaries belong to these tests."""


@pytest.fixture
async def index_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'indexes.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    try:
        await db.create_tables(IndexBase)
        yield db
    finally:
        await db.drop_tables(IndexBase)
        await close_db()


async def index_definitions(connection):
    """Read expression indexes even on dialects whose inspector omits them."""
    queries = {
        "sqlite": "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :table",
        "postgresql": """SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = current_schema() AND tablename = :table""",
        "mysql": """SELECT index_name, GROUP_CONCAT(
            CONCAT(COALESCE(column_name, expression), ' ', COALESCE(collation, '')) ORDER BY seq_in_index SEPARATOR ', '
        ) FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name = :table GROUP BY index_name""",
    }
    result = await connection.execute(text(queries[connection.dialect.name]), {"table": IndexRecord.__table__.name})
    return {row[0]: row[1] for row in result.all()}


async def test_index_definitions_survive_real_ddl(index_db):
    async with index_db.engine.connect() as connection:
        definitions = await index_definitions(connection)
        expected = {
            "ix_tenant_code",
            "ix_code_tenant",
            "ix_ascending",
            "ix_mixed",
            "a_raw_amount",
            "z_absolute_amount",
            "a_unique_code",
            "ix_lower_code",
            "ix_cover_code",
            "ix_always_tenant",
        }
        conditional = {"ix_postgresql_only", "ix_conditional_unique_tenant"}
        assert expected <= definitions.keys()
        if connection.dialect.name == "postgresql":
            assert conditional <= definitions.keys()
            assert "INCLUDE (tenant)" in definitions["ix_cover_code"]
        else:
            assert not conditional & definitions.keys()
        assert "abs(" in definitions["z_absolute_amount"].lower()
        assert "lower(" in definitions["ix_lower_code"].lower()
        if connection.dialect.name == "mysql":
            assert definitions["ix_tenant_code"].startswith("tenant")
            assert "amount D" in definitions["ix_mixed"]
            assert definitions["ix_code_tenant"].startswith("code")
        else:
            assert "(tenant, code)" in definitions["ix_tenant_code"]
            assert "amount DESC" in definitions["ix_mixed"]
            assert "(code, tenant)" in definitions["ix_code_tenant"]


async def test_functional_unique_index_enforces_its_expression(index_db):
    table = IndexRecord.__table__
    async with index_db.engine.begin() as connection:
        await connection.execute(table.insert().values(tenant=1, code="first", amount=7))
    with pytest.raises(IntegrityError):
        async with index_db.engine.begin() as connection:
            await connection.execute(table.insert().values(tenant=2, code="second", amount=-7))
    async with index_db.engine.connect() as connection:
        assert (await connection.execute(select(func.count()).select_from(table))).scalar_one() == 1


async def test_non_conflicting_rows_and_queries_work_with_all_indexes(index_db):
    await IndexRecord.objects.bulk_create(
        [
            {"tenant": 1, "code": "bravo", "amount": 5},
            {"tenant": 2, "code": "alpha", "amount": -9},
        ]
    )
    assert await IndexRecord.objects.order_by("code", "tenant").values_list("amount", flat=True) == [-9, 5]
    assert await IndexRecord.objects.filter(func.abs(IndexRecord.amount) == 9).count() == 1


async def test_preserved_indexes_can_be_dropped_and_recreated(index_db):
    async with index_db.engine.begin() as connection:
        before = await index_definitions(connection)
        for idx in IndexRecord.__table__.indexes:
            if idx.name in before:
                await connection.execute(DropIndex(idx))
                await connection.execute(CreateIndex(idx))
        assert await index_definitions(connection) == before
