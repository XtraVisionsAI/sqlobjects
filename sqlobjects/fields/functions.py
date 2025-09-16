from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.sql.elements import ColumnElement

from .core import Column, column
from .shortcuts import ComputedColumn, IdentityColumn


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
    type: str = "integer",  # noqa
    nullable: bool = True,
    **kwargs: Any,
) -> Column[Any]:
    """Create foreign key column with reference constraint.

    Args:
        reference: Foreign key reference in format "table.column"
        type: Column type (default: "integer")
        nullable: Whether column can be null
        **kwargs: Additional column parameters

    Returns:
        Column descriptor with foreign key constraint

    Example:
        author_id: Column[int] = foreign_key("users.id")
        user_uuid: Column[str] = foreign_key("users.uuid", type="uuid")
        category_id: Column[int] = foreign_key("categories.id", nullable=False)
    """
    # Create ForeignKey constraint
    fk_constraint = ForeignKey(reference)

    # Use existing column() function with foreign key
    return column(
        type=type,
        nullable=nullable,
        foreign_key=fk_constraint,
        **kwargs,
    )
