"""CTE (Common Table Expression) support for SQLObjects.

This module provides CTE functionality for building complex queries with
reusable subqueries and recursive queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import CTE as SACTE


if TYPE_CHECKING:
    from sqlobjects.queryset import QuerySet

__all__ = ["CTEExpression"]


class CTEExpression:
    """CTE expression wrapper for query reuse.

    A CTE (Common Table Expression) allows you to define a temporary named
    result set that can be referenced within a SELECT, INSERT, UPDATE, or
    DELETE statement.

    Examples:
        Basic CTE:
            >>> adults = User.objects.filter(User.age >= 18).cte("adults")
            >>> result = await User.objects.with_cte(adults).filter(adults.c.age < 30).all()

        Recursive CTE:
            >>> base = Employee.objects.filter(Employee.manager_id.is_(None)).cte("hierarchy", recursive=True)
            >>> recursive = Employee.objects.join(base, Employee.manager_id == base.c.id)
            >>> hierarchy = base.union_all(recursive)
            >>> all_employees = await Employee.objects.with_cte(hierarchy).select_from(hierarchy).all()
    """

    def __init__(self, queryset: QuerySet, name: str, recursive: bool = False):
        """Initialize CTE expression.

        Args:
            queryset: The QuerySet to convert to CTE
            name: Name of the CTE
            recursive: Whether this is a recursive CTE
        """
        self._queryset = queryset
        self._name = name
        self._recursive = recursive
        self._cte_obj: SACTE | None = None
        self._union_query: QuerySet | None = None

    def _build_cte(self, session) -> SACTE:
        """Build SQLAlchemy CTE object.

        Args:
            session: Database session for building the query

        Returns:
            SQLAlchemy CTE object
        """
        if self._cte_obj is not None:
            return self._cte_obj

        # Build base query
        stmt = self._queryset._builder.build(session)

        # Handle recursive CTE with UNION ALL
        if self._recursive and self._union_query is not None:
            # Build recursive part
            recursive_stmt = self._union_query._builder.build(session)

            # Combine with UNION ALL
            combined = stmt.union_all(recursive_stmt)
            cte_obj = combined.cte(self._name, recursive=True)
        else:
            # Non-recursive CTE
            cte_obj = stmt.cte(self._name, recursive=self._recursive)

        self._cte_obj = cte_obj
        return cte_obj

    @property
    def c(self) -> Any:
        """Access CTE columns (similar to Table.c).

        Returns:
            Column collection for the CTE

        Note:
            The CTE must be built before accessing columns.
            This is typically done automatically when used in a query.
        """
        if self._cte_obj is None:
            raise RuntimeError(f"CTE '{self._name}' has not been built yet. Use it in a query with .with_cte() first.")
        return self._cte_obj.c

    def union_all(self, recursive_queryset: QuerySet) -> CTEExpression:
        """Add UNION ALL clause for recursive CTE.

        This method is used to define the recursive part of a recursive CTE.

        Args:
            recursive_queryset: QuerySet for the recursive part

        Returns:
            Self for method chaining

        Example:
            >>> base = Employee.objects.filter(Employee.manager_id.is_(None)).cte("tree", recursive=True)
            >>> recursive = Employee.objects.join(base, Employee.manager_id == base.c.id)
            >>> tree = base.union_all(recursive)
        """
        if not self._recursive:
            raise ValueError(
                f"union_all() can only be used with recursive CTEs. "
                f"Set recursive=True when creating CTE '{self._name}'."
            )

        self._union_query = recursive_queryset
        return self

    @property
    def name(self) -> str:
        """Get CTE name."""
        return self._name

    @property
    def is_recursive(self) -> bool:
        """Check if this is a recursive CTE."""
        return self._recursive

    def __repr__(self) -> str:
        """String representation."""
        recursive_str = ", recursive=True" if self._recursive else ""
        return f"CTEExpression(name='{self._name}'{recursive_str})"
