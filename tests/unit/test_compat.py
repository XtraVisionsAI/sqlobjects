"""Contracts for the SQLAlchemy version compatibility layer.

These run against every supported SQLAlchemy series in CI; a failure here
means an upgrade changed the internals that ``sqlobjects._compat`` wraps.
"""

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table
from sqlalchemy.schema import CreateTable

from sqlobjects._compat import foreign_key_copy_target, foreign_key_target_tokens, retarget_foreign_key


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
