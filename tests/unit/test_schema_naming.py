"""Generated schema names stay stable, bounded and separate from user names."""

import pytest
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, column
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.exc import IdentifierError
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.elements import conv

from sqlobjects.fields import Column, IntegerColumn, StringColumn, identity
from sqlobjects.metadata import ModelRegistry, constraint, index, unique
from sqlobjects.model import ObjectModel


@pytest.fixture(autouse=True)
def clean_db():
    """These tests only construct isolated metadata."""


def make_model(table_name, constraints=None, indexes=None, naming_convention=None):
    class Base(ObjectModel):
        __abstract__ = True
        __registry__ = ModelRegistry(naming_convention=naming_convention)

    model_config = type(
        "Config", (), {"table_name": table_name, "constraints": constraints or [], "indexes": indexes or []}
    )

    class Record(Base):
        id: Column[int] = identity()
        external_customer_identifier: Column[str] = StringColumn(length=30, unique=True)
        external_transaction_identifier: Column[str] = StringColumn(length=30, index=True)
        amount: Column[int] = IntegerColumn()
        Config = model_config

    return Record


def names(table):
    return {str(item.name) for item in [*table.constraints, *table.indexes] if item.name is not None}


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
@pytest.mark.parametrize("table_name", ["external_transaction_processing_records", "业务数据" * 5])
def test_generated_names_fit_all_backends_and_keep_utf8_boundaries(dialect, table_name):
    table = make_model(
        table_name,
        constraints=[unique("external_customer_identifier", "external_transaction_identifier")],
        indexes=[index(None, "amount", "external_customer_identifier")],
    ).__table__
    assert all(len(name.encode("utf-8")) <= 63 for name in names(table))
    ddl = str(CreateTable(table).compile(dialect=dialect))
    ddl += "\n".join(str(CreateIndex(idx).compile(dialect=dialect)) for idx in table.indexes)
    for name in names(table):
        assert name in ddl


def test_short_names_are_unchanged():
    table = make_model("records", constraints=[constraint("amount > 0")], indexes=[index(None, "amount")]).__table__
    assert names(table) == {
        "uq_records_external_customer_identifier",
        "idx_records_external_transaction_identifier",
        "idx_records_external_customer_identifier",
        "idx_records_amount",
        "ck_records_amount",
    }


def test_long_names_with_common_prefix_do_not_collide_and_rebuild_stably():
    def build():
        return make_model(
            "external_transaction_processing_records",
            constraints=[
                unique("external_customer_identifier", "external_transaction_identifier"),
                unique("external_customer_identifier", "amount"),
            ],
        ).__table__

    first, second = build(), build()
    uniques = [str(item.name) for item in first.constraints if isinstance(item, UniqueConstraint)]
    assert len(uniques) == len(set(uniques)) == 3
    assert all(len(name.encode()) <= 63 for name in uniques)
    assert names(first) == names(second)


def test_check_name_collisions_are_resolved_independently_of_declaration_order():
    def build(conditions):
        table = make_model("records", constraints=[constraint(sql) for sql in conditions]).__table__
        return {str(item.sqltext): str(item.name) for item in table.constraints if isinstance(item, CheckConstraint)}

    conditions = ["amount > 0", "amount < 100"]
    first, second = build(conditions), build(reversed(conditions))
    assert len(set(first.values())) == 2
    assert first == second
    assert all(name.startswith("ck_records_amount_") for name in first.values())


def test_automatic_name_does_not_collide_with_explicit_name():
    table = make_model(
        "records", constraints=[constraint("amount > 0"), constraint("amount < 100", "ck_records_amount")]
    ).__table__
    checks = {str(item.sqltext): str(item.name) for item in table.constraints if isinstance(item, CheckConstraint)}
    assert checks["amount < 100"] == "ck_records_amount"
    assert checks["amount > 0"] != "ck_records_amount"


def test_explicit_names_including_converted_names_are_not_rewritten():
    explicit = "user_selected_long_constraint_or_index_name_" + "x" * 40
    table = make_model(
        "records",
        constraints=[constraint("amount > 0", explicit)],
        indexes=[Index(conv(explicit), "amount")],
    ).__table__
    assert next(item for item in table.constraints if isinstance(item, CheckConstraint)).name == explicit
    assert next(item for item in table.indexes if "amount" in item.columns).name == explicit
    # Explicit names remain the caller's responsibility, including length errors.
    with pytest.raises(IdentifierError, match="exceeds maximum length"):
        str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_custom_naming_convention_keeps_sqlalchemy_truncation():
    convention = {
        "uq": "custom_uq_%(table_name)s_%(column_0_N_name)s",
        "ix": "custom_ix_%(table_name)s_%(column_0_name)s",
        "ck": "custom_ck_%(table_name)s_%(constraint_name)s",
    }
    table = make_model(
        "external_transaction_processing_records",
        constraints=[constraint("amount > 0", "positive")],
        naming_convention=convention,
    ).__table__
    assert all(isinstance(item.name, conv) for item in [*table.indexes, *table.constraints] if item.name)
    assert any(len(name) > 63 for name in names(table))
    str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for idx in table.indexes:
        str(CreateIndex(idx).compile(dialect=postgresql.dialect()))


def test_partial_index_names_include_the_predicate_when_names_collide():
    def build(predicates):
        table = make_model(
            "records", indexes=[index(None, "amount", postgresql_where=predicate) for predicate in predicates]
        ).__table__
        return {
            str(idx.dialect_options["postgresql"].get("where")): str(idx.name)
            for idx in table.indexes
            if "amount" in idx.columns
        }

    predicates = ["amount > 0", "amount < 100"]
    first, second = build(predicates), build(reversed(predicates))
    assert len(set(first.values())) == 2
    assert first == second


def test_explicit_index_name_wins_over_automatic_field_index():
    table = make_model(
        "records", indexes=[index("ix_explicit_transaction", "external_transaction_identifier")]
    ).__table__
    assert "ix_explicit_transaction" in names(table)
    assert "idx_records_external_transaction_identifier" not in names(table)


def test_check_name_signatures_include_bound_values():
    def build(values):
        table = make_model(
            "records", constraints=[CheckConstraint(column("amount") > value) for value in values]
        ).__table__
        return {
            str(item.sqltext.compile(compile_kwargs={"literal_binds": True})): str(item.name)
            for item in table.constraints
            if isinstance(item, CheckConstraint)
        }

    assert build([0, 1]) == build([1, 0])
    assert len(set(build([0, 1]).values())) == 2


def test_index_predicates_with_different_bound_values_are_not_deduplicated():
    table = make_model(
        "records",
        indexes=[Index(f"amount_gt_{value}", "amount", postgresql_where=column("amount") > value) for value in [0, 1]],
    ).__table__
    assert {"amount_gt_0", "amount_gt_1"} <= names(table)


def test_unique_constraint_name_avoids_an_explicit_index_name():
    explicit = "uq_records_external_customer_identifier"
    table = make_model("records", indexes=[index(explicit, "amount")]).__table__
    assert next(idx for idx in table.indexes if "amount" in idx.columns).name == explicit
    assert all(item.name != explicit for item in table.constraints if isinstance(item, UniqueConstraint))
