from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.sql.elements import ColumnElement

from ..cascade import OnDeleteType, OnUpdateType, normalize_ondelete, normalize_onupdate  # pyright: ignore
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
        reference: Foreign key reference in format "table.column"
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
        # Basic usage with auto type inference
        author_id: Column[int] = foreign_key("users.id")

        # Complete constraint configuration
        author_id: Column[int] = foreign_key(
            "users.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
            nullable=False
        )

        # Deferred constraint for circular references
        parent_id: Column[int] = foreign_key(
            "categories.id",
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

    # Create ForeignKey constraint
    fk_constraint = ForeignKey(reference, **fk_kwargs)

    # Use existing column() function with foreign key
    return column(
        type=type,
        nullable=nullable,
        foreign_key=fk_constraint,
        **kwargs,
    )
