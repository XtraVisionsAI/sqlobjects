"""Index deduplication must retain semantically different index definitions."""

import pytest
from sqlalchemy import Index, column, func, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateIndex
from sqlalchemy.sql.elements import ColumnElement, conv
from sqlalchemy.types import String

from sqlobjects.fields import Column, StringColumn, identity
from sqlobjects.metadata import ModelRegistry, index
from sqlobjects.model import ObjectModel


@pytest.fixture(autouse=True)
def clean_db():
    """No database is needed to compare isolated metadata."""


def make_table(indexes):
    class Base(ObjectModel):
        __abstract__ = True
        __registry__ = ModelRegistry()

    model_config = type("Config", (), {"table_name": "index_identity_records", "indexes": indexes})

    class Record(Base):
        id: Column[int] = identity()
        first: Column[str] = StringColumn(length=30)
        second: Column[str] = StringColumn(length=30)
        Config = model_config

    return Record.__table__


def names(table):
    return {str(idx.name) for idx in table.indexes}


def test_composite_column_order_is_part_of_index_identity():
    table = make_table([index("first_second", "first", "second"), index("second_first", "second", "first")])
    assert names(table) == {"first_second", "second_first"}


def test_repeated_columns_are_not_collapsed_to_a_set():
    table = make_table([index("one_column", "first"), index("repeated_column", "first", "first")])
    assert names(table) == {"one_column", "repeated_column"}


@pytest.mark.parametrize("unique", [False, True])
def test_functional_indexes_do_not_replace_raw_columns(unique):
    table = make_table(
        [
            Index("raw", column("first"), unique=unique),
            Index("lowercase", func.lower(column("first")), unique=unique),
            Index("uppercase", func.upper(column("first")), unique=unique),
        ]
    )
    assert names(table) == {"raw", "lowercase", "uppercase"}


def test_sort_direction_and_collation_are_part_of_identity():
    table = make_table(
        [
            Index("ascending", column("first").asc(), column("second")),
            Index("descending", column("first").desc(), column("second")),
            Index("collated", column("first").collate("NOCASE"), column("second")),
        ]
    )
    assert names(table) == {"ascending", "descending", "collated"}


def test_expression_literal_values_are_part_of_identity():
    table = make_table(
        [
            Index("prefix_one", func.substr(column("first"), 1, 1)),
            Index("prefix_two", func.substr(column("first"), 1, 2)),
        ]
    )
    assert names(table) == {"prefix_one", "prefix_two"}


@pytest.mark.parametrize(
    "dialect_options",
    [
        {"postgresql_using": "hash"},
        {"postgresql_include": ["second"]},
        {"postgresql_ops": {"first": "text_pattern_ops"}},
        {"mysql_length": {"first": 10}},
    ],
)
def test_unique_index_cannot_remove_differently_configured_plain_index(dialect_options):
    table = make_table(
        [
            Index("unique_first", "first", unique=True),
            Index("configured_first", "first", **dialect_options),
        ]
    )
    assert names(table) == {"unique_first", "configured_first"}


def test_unique_index_does_not_remove_reverse_order_or_expression_index():
    table = make_table(
        [
            Index("unique_ordered", "first", "second", unique=True),
            Index("reverse_ordered", "second", "first"),
            Index("expression", func.lower(column("first")), column("second")),
        ]
    )
    assert names(table) == {"unique_ordered", "reverse_ordered", "expression"}


def test_only_exact_functional_duplicates_are_removed_deterministically():
    table = make_table(
        [
            Index("z_lower", func.lower(column("first"))),
            Index("a_lower", func.lower(column("first"))),
            Index("other", func.upper(column("first"))),
        ]
    )
    assert names(table) == {"a_lower", "other"}


def test_identical_unique_index_can_still_replace_plain_index():
    table = make_table(
        [
            Index("plain_lower", func.lower(column("first"))),
            Index("unique_lower", func.lower(column("first")), unique=True),
        ]
    )
    assert names(table) == {"unique_lower"}


def test_partial_unique_does_not_replace_full_index_with_same_expression():
    table = make_table(
        [
            Index("full_lower", func.lower(column("first"))),
            Index("partial_lower", func.lower(column("first")), unique=True, sqlite_where=column("second") == "active"),
        ]
    )
    assert names(table) == {"full_lower", "partial_lower"}


def test_conditional_ddl_is_not_deduplicated_against_unconditional_indexes():
    table = make_table(
        [
            Index("unconditional", "first"),
            Index("conditional_unique", "first", unique=True).ddl_if(dialect="postgresql"),
            Index("conditional_plain", "first").ddl_if(dialect="mysql"),
        ]
    )
    assert names(table) == {"unconditional", "conditional_unique", "conditional_plain"}


class PostgreSQLOnlyExpression(ColumnElement):
    type = String()
    inherit_cache = False


@compiles(PostgreSQLOnlyExpression, "postgresql")
def compile_postgresql_only(expression, compiler, **kwargs):
    return "lower(first)"


def test_backend_only_expression_is_kept_without_generic_compiler():
    from sqlalchemy.dialects import postgresql

    table = make_table(
        [
            Index("custom_a", PostgreSQLOnlyExpression()),
            Index("custom_b", PostgreSQLOnlyExpression()),
            Index("normal", column("first")),
        ]
    )
    assert names(table) == {"custom_a", "custom_b", "normal"}
    for idx in table.indexes:
        str(CreateIndex(idx).compile(dialect=postgresql.dialect()))


def test_textual_indexes_are_compared_by_expression():
    table = make_table([Index("a_text", text("lower(first)")), Index("z_text", text("lower(first)"))])
    assert names(table) == {"a_text"}


def test_convention_name_has_no_effect_on_index_shape():
    table = make_table(
        [
            Index(conv("convention_lower"), func.lower(column("first"))),
            Index("explicit_raw", column("first")),
        ]
    )
    assert names(table) == {"convention_lower", "explicit_raw"}


def test_conditional_ddl_callback_is_not_evaluated_during_model_construction():
    def callback(*args, **kwargs):
        raise AssertionError("DDL callback ran without a DDL execution context")

    table = make_table(
        [
            Index("plain", "first"),
            Index("conditional", "first", unique=True).ddl_if(callable_=callback),
        ]
    )
    assert names(table) == {"plain", "conditional"}


def test_backend_only_predicate_is_retained_without_generic_compilation():
    table = make_table(
        [
            Index("custom_predicate_a", "first", postgresql_where=PostgreSQLOnlyExpression() == "a"),
            Index("custom_predicate_b", "first", postgresql_where=PostgreSQLOnlyExpression() == "b"),
        ]
    )
    assert names(table) == {"custom_predicate_a", "custom_predicate_b"}


def test_expression_labels_select_operator_classes_and_cannot_be_discarded():
    from sqlalchemy.dialects import postgresql

    table = make_table(
        [
            Index(
                "labelled",
                func.lower(column("first")).label("lower_first"),
                postgresql_ops={"lower_first": "text_pattern_ops"},
            ),
            Index("unlabelled", func.lower(column("first")), postgresql_ops={"lower_first": "text_pattern_ops"}),
        ]
    )
    assert names(table) == {"labelled", "unlabelled"}
    statements = {str(idx.name): str(CreateIndex(idx).compile(dialect=postgresql.dialect())) for idx in table.indexes}
    assert "text_pattern_ops" in statements["labelled"]
    assert "text_pattern_ops" not in statements["unlabelled"]
