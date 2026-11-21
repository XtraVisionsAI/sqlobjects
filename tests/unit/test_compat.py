"""Contracts for the SQLAlchemy version compatibility layer.

These run against every supported SQLAlchemy series in CI; a failure here
means an upgrade changed the internals that ``sqlobjects._compat`` wraps.
"""

import warnings

import pytest
from sqlalchemy import Column, ForeignKey, Index, Integer, MetaData, Table, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SADeprecationWarning
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql import visitors

from sqlobjects._compat import (
    apply_distinct_on,
    foreign_key_copy_target,
    foreign_key_target_tokens,
    has_distinct_on,
    index_has_ddl_if,
    retarget_foreign_key,
    select_has_for_update,
)


def _child(metadata: MetaData, target, *, name: str = "children") -> ForeignKey:
    table = Table(name, metadata, Column("parent_id", Integer, ForeignKey(target, name="fk_parent")))
    return next(iter(table.c.parent_id.foreign_keys))


class TestForeignKeyTargetTokens:
    def test_table_and_column(self):
        assert foreign_key_target_tokens(_child(MetaData(), "Parent.id")) == (None, "Parent", "id")

    def test_schema_qualified(self):
        assert foreign_key_target_tokens(_child(MetaData(), "app.Parent.id")) == ("app", "Parent", "id")


class TestRetargetForeignKey:
    def test_retargeted_key_resolves_to_the_new_table(self):
        metadata = MetaData()
        parents = Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, "Parent.id")

        retarget_foreign_key(fk, "parents")

        assert foreign_key_target_tokens(fk) == (None, "parents", "id")
        assert fk.target_fullname == "parents.id"
        assert fk.column is parents.c.id
        assert fk.constraint is not None
        assert fk.constraint.referred_table is parents

    def test_retargeted_key_renders_in_ddl(self):
        metadata = MetaData()
        Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, "Parent.id")

        retarget_foreign_key(fk, "parents")

        ddl = str(CreateTable(fk.parent.table))
        assert "REFERENCES parents (id)" in ddl

    def test_schema_is_preserved(self):
        metadata = MetaData()
        parents = Table("parents", metadata, Column("id", Integer, primary_key=True), schema="app")
        fk = _child(metadata, "app.Parent.id")

        retarget_foreign_key(fk, "parents")

        assert foreign_key_target_tokens(fk) == ("app", "parents", "id")
        assert fk.column is parents.c.id

    def test_retarget_after_tokens_were_read(self):
        """Reading the target first must not pin the stale value (memoized on 2.0)."""
        metadata = MetaData()
        parents = Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, "Parent.id")
        assert foreign_key_target_tokens(fk)[1] == "Parent"

        retarget_foreign_key(fk, "parents")

        assert fk.column is parents.c.id


class TestForeignKeyCopyTarget:
    def test_name_target_copies_to_an_equivalent_key(self):
        metadata = MetaData()
        parents = Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, "parents.id")

        copy = ForeignKey(foreign_key_copy_target(fk))
        Table("copies", metadata, Column("parent_id", Integer, copy))

        assert foreign_key_target_tokens(copy) == (None, "parents", "id")
        assert copy.column is parents.c.id

    def test_schema_qualified_name_target(self):
        fk = _child(MetaData(), "app.parents.id")

        copy = ForeignKey(foreign_key_copy_target(fk))

        assert foreign_key_target_tokens(copy) == ("app", "parents", "id")

    def test_column_target_stays_a_column(self):
        metadata = MetaData()
        parents = Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, parents.c.id)

        assert foreign_key_copy_target(fk) is parents.c.id

    def test_retargeted_key_copies_with_the_new_target(self):
        metadata = MetaData()
        Table("parents", metadata, Column("id", Integer, primary_key=True))
        fk = _child(metadata, "Parent.id")
        retarget_foreign_key(fk, "parents")

        copy = ForeignKey(foreign_key_copy_target(fk))

        assert foreign_key_target_tokens(copy) == (None, "parents", "id")


def _items() -> Table:
    return Table("items", MetaData(), Column("id", Integer, primary_key=True), Column("kind", Integer))


def _carries_distinct_on(statement) -> bool:
    return any(has_distinct_on(part) for part in visitors.iterate(statement))


class TestDistinctOn:
    def test_renders_distinct_on_for_postgresql_without_deprecation(self):
        items = _items()
        with warnings.catch_warnings():
            warnings.simplefilter("error", SADeprecationWarning)
            statement = apply_distinct_on(select(items), [items.c.kind])
            sql = str(statement.compile(dialect=postgresql.dialect()))

        assert "SELECT DISTINCT ON (items.kind)" in sql

    def test_is_detected_on_the_statement(self):
        items = _items()

        assert _carries_distinct_on(apply_distinct_on(select(items), [items.c.kind]))

    @pytest.mark.parametrize("nest", ["subquery", "cte", "scalar_subquery"])
    def test_is_detected_when_nested(self, nest):
        items = _items()
        inner = apply_distinct_on(select(items.c.id), [items.c.kind])
        if nest == "scalar_subquery":
            statement = select(inner.scalar_subquery())
        else:
            statement = select(func.count()).select_from(getattr(inner, nest)())

        assert _carries_distinct_on(statement)

    def test_legacy_spelling_is_detected(self):
        """Statements written by callers may still use select.distinct(*columns)."""
        items = _items()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SADeprecationWarning)
            statement = select(items).distinct(items.c.kind)

        assert _carries_distinct_on(statement)

    def test_plain_distinct_is_not_distinct_on(self):
        items = _items()

        assert not _carries_distinct_on(select(items).distinct())
        assert not _carries_distinct_on(select(items))


class TestSelectHasForUpdate:
    def test_detects_for_update_and_for_share(self):
        items = _items()

        assert select_has_for_update(select(items).with_for_update())
        assert select_has_for_update(select(items).with_for_update(read=True))

    def test_plain_select_and_non_select(self):
        items = _items()

        assert not select_has_for_update(select(items))
        assert not select_has_for_update(items.update())


class TestIndexHasDdlIf:
    def test_detects_conditional_ddl(self):
        items = _items()

        assert index_has_ddl_if(Index("ix_kind", items.c.kind).ddl_if(dialect="postgresql"))

    def test_plain_index(self):
        items = _items()

        assert not index_has_ddl_if(Index("ix_kind", items.c.kind))
