"""Base classes for query expressions."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generator, Generic, TypeVar


if TYPE_CHECKING:
    from ..queries import QueryExecutor

# Type variable for expression result type
T_Result = TypeVar("T_Result")


class QueryExpression(ABC, Generic[T_Result]):
    """Base class for all query expressions that can be executed or used in compositions.

    Query expressions represent SQL operations that can be executed independently
    or combined with other expressions to form complex queries. They support
    both direct execution via await and composition through comparison operators.
    """

    def __init__(self, executor: "QueryExecutor | None" = None):
        """Initialize query expression with optional executor.

        Args:
            executor: Query executor for SQL execution
        """
        self._executor = executor
        self._context: str | None = None

    def __await__(self) -> Generator[Any, None, T_Result]:
        """Enable direct awaiting of expressions with proper type inference."""
        return self.execute().__await__()

    @abstractmethod
    async def execute(self) -> T_Result:
        """Execute the expression and return results.

        Returns:
            Query results in appropriate format
        """
        pass

    @abstractmethod
    def get_sql(self) -> str:
        """Generate SQL string for this expression.

        Returns:
            SQL string representation
        """
        pass

    def explain(self, analyze: bool = False, verbose: bool = False) -> str:
        """Generate execution plan for this expression.

        Args:
            analyze: Include actual execution statistics
            verbose: Include detailed execution information

        Returns:
            Query execution plan
        """
        if not self._executor:
            raise RuntimeError("No executor available for explain operation")
        return self._executor.explain(self.get_sql(), analyze=analyze, verbose=verbose)

    def __gt__(self, other) -> "ComparisonExpression":
        """Create greater-than comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) > other

    def __lt__(self, other) -> "ComparisonExpression":
        """Create less-than comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) < other

    def __eq__(self, other) -> "ComparisonExpression":  # type: ignore[reportIncompatibleMethodOverride]
        """Create equality comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) == other

    def __ge__(self, other) -> "ComparisonExpression":
        """Create greater-than-or-equal comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) >= other

    def __le__(self, other) -> "ComparisonExpression":
        """Create less-than-or-equal comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) <= other

    def __ne__(self, other) -> "ComparisonExpression":  # type: ignore[reportIncompatibleMethodOverride]
        """Create not-equal comparison expression."""
        from .scalar import ScalarSubquery

        return ScalarSubquery(self) != other


class ComparisonExpression:
    """Represents a comparison operation between expressions."""

    def __init__(self, left, operator: str, right):
        """Initialize comparison expression.

        Args:
            left: Left side of comparison
            operator: Comparison operator (>, <, =, etc.)
            right: Right side of comparison
        """
        self.left = left
        self.operator = operator
        self.right = right

    def resolve(self, table):
        """Resolve comparison to SQLAlchemy expression.

        Args:
            table: Target table for resolution

        Returns:
            SQLAlchemy comparison expression
        """
        left_expr = self.left.resolve(table) if hasattr(self.left, "resolve") else self.left
        right_expr = self.right.resolve(table) if hasattr(self.right, "resolve") else self.right

        if self.operator == ">":
            return left_expr > right_expr
        elif self.operator == "<":
            return left_expr < right_expr
        elif self.operator == "=":
            return left_expr == right_expr
        elif self.operator == ">=":
            return left_expr >= right_expr
        elif self.operator == "<=":
            return left_expr <= right_expr
        elif self.operator == "!=":
            return left_expr != right_expr
        else:
            raise ValueError(f"Unsupported operator: {self.operator}")
