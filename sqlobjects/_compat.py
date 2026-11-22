"""SQLAlchemy version compatibility helpers.

Everything that depends on SQLAlchemy internals differing between supported
release series lives here, so that an upgrade breaks in one tested place
instead of at import time in user code.

Supported series: 2.0 (>= 2.0.44) and 2.1.
"""

from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import ext as _postgresql_ext


# Added in 2.1 as the replacement for ``select.distinct(*columns)``; absent on 2.0.
_distinct_on: Any = getattr(_postgresql_ext, "distinct_on", None)
_DistinctOnClause: Any = getattr(_postgresql_ext, "DistinctOnClause", None)


__all__ = [
    "apply_distinct_on",
    "foreign_key_copy_target",
    "foreign_key_target_tokens",
    "has_distinct_on",
    "index_has_ddl_if",
    "retarget_foreign_key",
    "select_has_for_update",
]

# SQLAlchemy 2.1 stores a name-based foreign key target as a
# ``ForeignKeyTarget(schema, table_name, column_name)`` tuple exposed through
# the public ``ForeignKey.target_tokens``; ``_colspec`` became a read-only
# legacy accessor. 2.0 stores the dotted string in a writable ``_colspec``.
_HAS_TARGET_TOKENS = hasattr(ForeignKey, "target_tokens")


def foreign_key_target_tokens(fk: ForeignKey) -> tuple[str | None, str, str | None]:
    """Return the ``(schema, table_name, column_name)`` target of a foreign key."""
    raw: Any = fk  # version-specific attributes; see _HAS_TARGET_TOKENS
    schema, table_name, column_name = raw.target_tokens if _HAS_TARGET_TOKENS else raw._column_tokens  # noqa: SLF001
    return schema, table_name, column_name


def foreign_key_copy_target(fk: ForeignKey) -> Any:
    """Return a value that builds an equivalent ``ForeignKey`` when passed to its constructor.

    A target given as a ``Column`` is returned as that column; a target given
    by name is returned in the form the running SQLAlchemy version stores it,
    so names containing dots survive the copy on 2.1.
    """
    raw: Any = fk
    if _HAS_TARGET_TOKENS:
        column = raw.target_column
        return raw.target_tokens if column is None else column
    return raw._colspec  # noqa: SLF001


def retarget_foreign_key(fk: ForeignKey, table_name: str) -> None:
    """Point a name-based foreign key at another table, keeping schema and column.

    Used to replace a model class name with the model's actual table name once
    the referenced model is registered. SQLAlchemy has no public API for
    changing the target of an existing ``ForeignKey``, so this is the single
    place allowed to rewrite its private state.
    """
    raw: Any = fk
    if _HAS_TARGET_TOKENS:
        raw._given_tokens = raw.target_tokens._replace(table_name=table_name)  # noqa: SLF001
    else:
        schema, _, column_name = raw._column_tokens  # noqa: SLF001
        prefix = f"{schema}." if schema else ""
        raw._colspec = f"{prefix}{table_name}.{column_name}"  # noqa: SLF001
        # Memoized on 2.0; drop it so the new target is parsed again.
        raw.__dict__.pop("_column_tokens", None)


def apply_distinct_on(query: Any, columns: list[Any]) -> Any:
    """Apply PostgreSQL ``DISTINCT ON (columns)`` to a SELECT.

    2.1 deprecates ``select.distinct(*columns)`` in favour of the
    ``postgresql.distinct_on`` extension; 2.0 only has the former.
    """
    if _distinct_on is not None:
        return query.ext(_distinct_on(*columns))
    return query.distinct(*columns)


def has_distinct_on(element: Any) -> bool:
    """Whether a statement element is, or directly carries, a ``DISTINCT ON`` clause.

    Covers both spellings: ``select.distinct(*columns)`` stores the columns on
    the SELECT, the 2.1 extension is a separate element inside the statement.
    Call it for every element of ``visitors.iterate(statement)``.
    """
    if _DistinctOnClause is not None and isinstance(element, _DistinctOnClause):
        return True
    return bool(getattr(element, "_distinct_on", ()))


def select_has_for_update(query: Any) -> bool:
    """Whether a SELECT was built with ``with_for_update()``; there is no public accessor."""
    return getattr(query, "_for_update_arg", None) is not None


def index_has_ddl_if(index: Index) -> bool:
    """Whether an index has conditional DDL set through ``Index.ddl_if()``; there is no public accessor."""
    return getattr(index, "_ddl_if", None) is not None
