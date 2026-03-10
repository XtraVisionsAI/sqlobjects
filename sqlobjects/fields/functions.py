from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.sql.elements import ColumnElement

from ..cascade import OnDeleteType, OnUpdateType, normalize_ondelete, normalize_onupdate
from .core import Column, column
from .shortcuts import ComputedColumn, IdentityColumn


def _extract_table_or_class_name(reference: str) -> str | None:
    """从 'X.col' 或 'schema.X.col' 中提取 X（可能是表名或类名）。

    Returns:
        X 部分，用于后续延迟匹配；格式不合法时返回 None
    """
    parts = reference.split(".")
    if len(parts) == 2:
        # "X.col"
        return parts[0]
    if len(parts) == 3:
        # "schema.X.col"
        return parts[1]
    return None


def identity(
    *,
    start: int = 1,
    increment: int = 1,
    minvalue: int | None = None,
    maxvalue: int | None = None,
    cycle: bool = False,
    cache: int | None = None,
    **kwargs,
) -> IdentityColumn:
    """Create identity column with auto-increment functionality

    Args:
        start: Starting value for identity sequence
        increment: Increment value for identity sequence
        minvalue: Minimum value for identity sequence
        maxvalue: Maximum value for identity sequence
        cycle: Whether to cycle when reaching max/min value
        cache: Number of values to cache for performance
        **kwargs: Additional column parameters

    Returns:
        IdentityColumn with auto-increment functionality

    Example:
        id: Column[int] = identity()
        order_id: Column[int] = identity(start=1000, increment=1)
    """
    return IdentityColumn(
        start=start, increment=increment, minvalue=minvalue, maxvalue=maxvalue, cycle=cycle, cache=cache, **kwargs
    )


def computed(
    sqltext: str | ColumnElement, *, persisted: bool | None = None, column_type: str = "auto", **kwargs
) -> ComputedColumn:
    """Create computed column with expression-based values

    Args:
        sqltext: SQL expression for computed value
        persisted: Whether to store computed value in database
        column_type: Type of the computed column
        **kwargs: Additional column parameters

    Returns:
        ComputedColumn with expression-based values

    Example:
        full_name: Column[str] = computed("first_name || ' ' || last_name")
        total: Column[float] = computed("price * quantity", persisted=True)
    """
    return ComputedColumn(sqltext=sqltext, persisted=persisted, column_type=column_type, **kwargs)


def foreign_key(
    reference: str,
    *,
    type: str = "auto",  # noqa
    nullable: bool = True,
    ondelete: OnDeleteType = None,
    onupdate: OnUpdateType = None,
    deferrable: bool = False,
    initially: str = "IMMEDIATE",
    **kwargs: Any,
) -> Column[Any]:
    """Create foreign key column with database constraint behavior.

    Args:
        reference: Foreign key reference in format "X.column" where X can be either
            a model class name (e.g. "User.id", "UserProfile.id") or a database table
            name (e.g. "users.id"). Class names are automatically resolved to table
            names via delayed matching. Schema is also supported: "schema.X.column".
        type: Column type, "auto" for automatic type inference
        nullable: Whether column can be null
        ondelete: Database constraint behavior when referenced object is deleted
        onupdate: Database constraint behavior when referenced object is updated
        deferrable: Whether constraint checking can be deferred
        initially: Initial constraint state ("IMMEDIATE" or "DEFERRED")
        **kwargs: Additional column parameters

    Returns:
        Column descriptor with foreign key constraint

    Examples:
        # Using class name (resolved automatically)
        author_id: Column[int] = foreign_key("User.id")

        # Using table name directly (also works)
        author_id: Column[int] = foreign_key("users.id")

        # Complete constraint configuration
        author_id: Column[int] = foreign_key(
            "User.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
            nullable=False
        )

        # Deferred constraint for circular references
        parent_id: Column[int] = foreign_key(
            "Category.id",
            deferrable=True,
            initially="DEFERRED"
        )
    """

    # Normalize constraint parameters
    ondelete_str = normalize_ondelete(ondelete)
    onupdate_str = normalize_onupdate(onupdate) if onupdate else None

    # Build foreign key constraint parameters
    fk_kwargs = {}
    if ondelete_str:
        fk_kwargs["ondelete"] = ondelete_str
    if onupdate_str:
        fk_kwargs["onupdate"] = onupdate_str
    if deferrable:
        fk_kwargs["deferrable"] = True
        fk_kwargs["initially"] = initially

    # Reference is passed directly to SQLAlchemy; delayed matching in
    # ModelProcessor._resolve_class_foreign_keys will correct the table
    # name if the first segment turns out to be a class name.
    fk_constraint = ForeignKey(reference, **fk_kwargs)

    # Store the table-or-class segment for delayed resolution
    table_or_class = _extract_table_or_class_name(reference)
    if table_or_class:
        fk_constraint.info["_fk_ref"] = table_or_class

    # Use existing column() function with foreign key
    return column(
        type=type,
        nullable=nullable,
        foreign_key=fk_constraint,
        **kwargs,
    )
