"""Scalar expression implementations."""

from typing import TYPE_CHECKING

from sqlalchemy import and_, exists, func, select

from .base import ComparisonExpression, QueryExpression


if TYPE_CHECKING:
    from ..queries import QueryBuilder


class CountExpression(QueryExpression[int]):
    """Represents a COUNT operation that can be executed or used as scalar subquery."""

    def __init__(self, builder: "QueryBuilder", executor=None):
        """Initialize count expression.

        Args:
            builder: Query builder containing base query conditions
            executor: Optional query executor
        """
        super().__init__(executor)
        self._builder = builder

    async def execute(self) -> int:
        """Execute count query and return integer result.

        Returns:
            Number of matching records
        """
        if not self._executor:
            raise RuntimeError("No executor available for count execution")

        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "count")
        return result if isinstance(result, int) else 0

    def get_sql(self) -> str:
        """Generate SQL string for count query.

        Returns:
            SQL string for the count operation
        """
        base_query = self._builder.build(self._builder.model_class.get_table())
        return str(base_query.compile(compile_kwargs={"literal_binds": True}))

    def scalar_subquery(self):
        """Convert to scalar subquery for use in comparisons.

        Returns:
            SQLAlchemy scalar subquery expression
        """
        query = select(func.count()).select_from(self._builder.model_class.get_table())

        if hasattr(self._builder, "conditions") and self._builder.conditions:
            query = query.where(and_(*self._builder.conditions))

        return query.scalar_subquery()


class ExistsExpression(QueryExpression[bool]):
    """Represents an EXISTS operation that can be executed or used in filters."""

    def __init__(self, builder: "QueryBuilder", executor=None):
        """Initialize exists expression.

        Args:
            builder: Query builder containing base query conditions
            executor: Optional query executor
        """
        super().__init__(executor)
        self._builder = builder

    async def execute(self) -> bool:
        """Execute exists query and return boolean result.

        Returns:
            True if matching records exist, False otherwise
        """
        if not self._executor:
            raise RuntimeError("No executor available for exists execution")

        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "exists")
        return bool(result)

    def get_sql(self) -> str:
        """Generate SQL string for exists query.

        Returns:
            SQL string for the exists operation
        """
        base_query = self._builder.build(self._builder.model_class.get_table())
        query = select(exists(base_query))
        return str(query.compile(compile_kwargs={"literal_binds": True}))

    def exists_subquery(self):
        """Convert to EXISTS subquery for use in filters.

        Returns:
            SQLAlchemy EXISTS expression
        """
        subquery = select(1).select_from(self._builder.model_class.get_table())

        if hasattr(self._builder, "conditions") and self._builder.conditions:
            subquery = subquery.where(and_(*self._builder.conditions))

        return exists(subquery)

    def resolve(self, table):
        """Resolve EXISTS expression for use in WHERE clauses.

        Args:
            table: Target table (unused for EXISTS)

        Returns:
            SQLAlchemy EXISTS expression
        """
        return self.exists_subquery()


class ScalarSubquery:
    """Wrapper for converting expressions to scalar subqueries in comparisons."""

    def __init__(self, expression: QueryExpression):
        """Initialize scalar subquery wrapper.

        Args:
            expression: Expression to convert to scalar subquery
        """
        self.expression = expression

    def __gt__(self, other) -> ComparisonExpression:
        """Create greater-than comparison."""
        return ComparisonExpression(self, ">", other)

    def __lt__(self, other) -> ComparisonExpression:
        """Create less-than comparison."""
        return ComparisonExpression(self, "<", other)

    def __eq__(self, other) -> ComparisonExpression:  # type: ignore[reportIncompatibleMethodOverride]
        """Create equality comparison."""
        return ComparisonExpression(self, "=", other)

    def __ge__(self, other) -> ComparisonExpression:
        """Create greater-than-or-equal comparison."""
        return ComparisonExpression(self, ">=", other)

    def __le__(self, other) -> ComparisonExpression:
        """Create less-than-or-equal comparison."""
        return ComparisonExpression(self, "<=", other)

    def __ne__(self, other) -> ComparisonExpression:  # type: ignore[reportIncompatibleMethodOverride]
        """Create not-equal comparison."""
        return ComparisonExpression(self, "!=", other)

    def resolve(self, table):
        """Resolve to SQLAlchemy scalar subquery.

        Args:
            table: Target table for resolution

        Returns:
            SQLAlchemy scalar subquery expression
        """
        if hasattr(self.expression, "scalar_subquery"):
            return self.expression.scalar_subquery()  # type: ignore[reportAttributeAccessIssue]
        else:
            raise ValueError(f"Expression {type(self.expression)} does not support scalar subquery conversion")
