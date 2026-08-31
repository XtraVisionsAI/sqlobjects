"""Unit tests for index deduplication in _post_process_table_indexes."""

from sqlobjects.fields import Column, StringColumn
from sqlobjects.metadata import index
from sqlobjects.model import ObjectModel


def test_same_columns_different_partial_predicates_are_kept():
    """Partial unique indexes on the same columns with different predicates are distinct."""

    class DedupTask(ObjectModel):
        kind: Column[str] = StringColumn(length=16)
        status: Column[str] = StringColumn(length=16)
        document_id: Column[str] = StringColumn(length=36)

        class Config:
            indexes = [
                index(
                    "ux_task_sync_active",
                    "document_id",
                    unique=True,
                    postgresql_where="kind = 'sync' AND status = 'pending'",
                ),
                index(
                    "ux_task_purge_active",
                    "document_id",
                    unique=True,
                    postgresql_where="kind = 'purge' AND status = 'pending'",
                ),
            ]

    names = {i.name for i in DedupTask.__table__.indexes}
    assert {"ux_task_sync_active", "ux_task_purge_active"} <= names


def test_same_columns_different_using_are_kept():
    """Indexes on the same columns with different access methods are distinct."""

    class DedupUsing(ObjectModel):
        tags: Column[str] = StringColumn(length=64)

        class Config:
            indexes = [
                index("ix_du_tags_btree", "tags"),
                index("ix_du_tags_gin", "tags", postgresql_using="gin"),
            ]

    names = {i.name for i in DedupUsing.__table__.indexes}
    assert {"ix_du_tags_btree", "ix_du_tags_gin"} <= names


def test_exact_duplicates_still_deduped_deterministically():
    """Only full-signature duplicates dedupe; the kept index is name-deterministic."""

    class DedupM(ObjectModel):
        a: Column[str] = StringColumn(length=8)

        class Config:
            indexes = [
                index("ux_m_a_1", "a", unique=True),
                index("ux_m_a_2", "a", unique=True),
            ]

    names = [i.name for i in DedupM.__table__.indexes if {c.name for c in i.columns} == {"a"}]
    assert names == ["ux_m_a_1"]


def test_partial_unique_does_not_remove_full_plain_index():
    """A partial unique index must not suppress a full-table plain index on the same columns."""

    class DedupN(ObjectModel):
        doc_id: Column[str] = StringColumn(length=36)
        state: Column[str] = StringColumn(length=8)

        class Config:
            indexes = [
                index("ix_n_doc", "doc_id"),
                index("ux_n_doc_active", "doc_id", unique=True, postgresql_where="state = 'active'"),
            ]

    names = {i.name for i in DedupN.__table__.indexes}
    assert {"ix_n_doc", "ux_n_doc_active"} <= names


def test_full_unique_still_removes_full_plain_index():
    """Existing optimization holds: a full-table unique index removes the plain one."""

    class DedupP(ObjectModel):
        email: Column[str] = StringColumn(length=64)

        class Config:
            indexes = [
                index("ix_p_email", "email"),
                index("ux_p_email", "email", unique=True),
            ]

    names = {i.name for i in DedupP.__table__.indexes}
    assert "ux_p_email" in names
    assert "ix_p_email" not in names
