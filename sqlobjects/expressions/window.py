"""Window function support for SQLObjects.

This module provides window function capabilities including:
- ROW_NUMBER, RANK, DENSE_RANK
- LAG, LEAD, FIRST_VALUE, LAST_VALUE
- Windowed aggregations (SUM, AVG, COUNT, etc.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import asc, desc, over

from .base import QueryExpression


if TYPE_CHECKING:
    pass

__all__ = [
    "WindowSpec",
    "WindowFunction",
    "RowNumberFunction",
    "RankFunction",
    "DenseRankFunction",
    "PercentRankFunction",
    "NtileFunction",
    "LagFunction",
    "LeadFunction",
    "FirstValueFunction",
    "LastValueFunction",
    "NthValueFunction",
]


class WindowSpec:
    """Window specification for PARTITION BY, ORDER BY, and frame clauses."""

    def __init__(
        self,
        partition_by: list[Any] | None = None,
        order_by: list[Any] | None = None,
        rows: tuple[int | None, int | None] | None = None,
        range_: tuple[int | None, int | None] | None = None,
    ):
        self.partition_by = partition_by or []
        self.order_by = order_by or []
        self.rows = rows
        self.range_ = range_

    def to_sqlalchemy_args(self) -> dict[str, Any]:
        """Convert to SQLAlchemy over() arguments."""
        args: dict[str, Any] = {}

        if self.partition_by:
            args["partition_by"] = [self._convert_column(col) for col in self.partition_by]

        if self.order_by:
            args["order_by"] = [self._convert_order_by(item) for item in self.order_by]

        if self.rows:
            args["rows"] = self.rows

        if self.range_:
            args["range_"] = self.range_

        return args

    def _convert_column(self, col: Any) -> Any:
        """Convert field expression to SQLAlchemy column."""
        # ColumnAttribute has __clause_element__() method
        if hasattr(col, "__clause_element__"):
            return col.__clause_element__()
        return col

    def _convert_order_by(self, item: Any) -> Any:
        """Convert order by item to SQLAlchemy expression."""
        from .function import FunctionExpression

        # 1. FunctionExpression - extract underlying expression
        if isinstance(item, FunctionExpression):
            return item.expression

        # 2. SQLAlchemy expressions (including desc(), asc() results)
        if hasattr(item, "_element") or hasattr(item, "element"):
            return item

        # 3. Objects implementing __clause_element__ protocol (ColumnAttribute, etc.)
        if hasattr(item, "__clause_element__"):
            return item.__clause_element__()

        # 4. Tuple syntax (column, "desc") for backward compatibility
        if isinstance(item, tuple):
            col, direction = item
            col_expr = self._convert_column(col)
            return desc(col_expr) if direction == "desc" else asc(col_expr)

        # 5. Default ascending order
        col_expr = self._convert_column(item)
        return asc(col_expr)


class WindowFunction(QueryExpression):
    """Base class for window functions."""

    def __init__(self, func_name: str, *args: Any):
        super().__init__()
        self.func_name = func_name
        self.args = args
        self.window_spec = WindowSpec()
        self._sa_expr = None  # Will be set by over()

    def over(
        self,
        partition_by: list[Any] | None = None,
        order_by: list[Any] | None = None,
        rows: tuple[int | None, int | None] | None = None,
        range_: tuple[int | None, int | None] | None = None,
    ) -> WindowFunction:
        """Specify window specification.

        Args:
            partition_by: Columns to partition by
            order_by: Columns to order by (use tuple (col, 'desc') for DESC)
            rows: ROWS frame specification (start, end)
            range_: RANGE frame specification (start, end)

        Returns:
            Self for method chaining

        Examples:
            func.row_number().over(order_by=[User.created_at])
            func.rank().over(partition_by=[User.dept], order_by=[(User.salary, 'desc')])
        """
        self.window_spec = WindowSpec(partition_by=partition_by, order_by=order_by, rows=rows, range_=range_)
        # Build the SQLAlchemy expression immediately
        self._sa_expr = self._build_sa_expression()
        return self

    def _build_sa_expression(self) -> Any:
        """Build the actual SQLAlchemy Over expression."""
        # Convert args to SQLAlchemy columns
        converted_args = []
        for arg in self.args:
            if hasattr(arg, "__clause_element__"):
                converted_args.append(arg.__clause_element__())
            else:
                converted_args.append(arg)

        # Build function expression directly using SQLAlchemy's Function
        from sqlalchemy.sql.functions import Function

        # Create function instance with the function name
        func_expr = Function(self.func_name, *converted_args)

        # Apply window specification
        window_args = self.window_spec.to_sqlalchemy_args()
        return over(func_expr, **window_args)

    def get_query(self) -> Any:
        """Return the SQLAlchemy Over expression."""
        if hasattr(self, "_sa_expr"):
            return self._sa_expr
        # If over() wasn't called, build without window spec
        return self._build_sa_expression()

    def resolve(self, table_or_model=None):
        """Resolve to SQLAlchemy expression for use in queries."""
        return self.get_query()

    async def execute(self, session=None):
        """Window functions must be used in annotate(), not executed directly."""
        raise TypeError(
            f"Window function {self.func_name}() must be used in annotate(), "
            "not executed directly. Example: "
            "User.objects.annotate(rank=func.rank().over(order_by=[User.age])).all()"
        )


# Ranking functions
class RowNumberFunction(WindowFunction):
    """ROW_NUMBER() window function."""

    def __init__(self):
        super().__init__("row_number")


class RankFunction(WindowFunction):
    """RANK() window function."""

    def __init__(self):
        super().__init__("rank")


class DenseRankFunction(WindowFunction):
    """DENSE_RANK() window function."""

    def __init__(self):
        super().__init__("dense_rank")


class PercentRankFunction(WindowFunction):
    """PERCENT_RANK() window function."""

    def __init__(self):
        super().__init__("percent_rank")


class NtileFunction(WindowFunction):
    """NTILE(n) window function."""

    def __init__(self, n: int):
        super().__init__("ntile", n)


# Offset functions
class LagFunction(WindowFunction):
    """LAG(column, offset, default) window function."""

    def __init__(self, column: Any, offset: int = 1, default: Any = None):
        if default is None:
            super().__init__("lag", column, offset)
        else:
            super().__init__("lag", column, offset, default)


class LeadFunction(WindowFunction):
    """LEAD(column, offset, default) window function."""

    def __init__(self, column: Any, offset: int = 1, default: Any = None):
        if default is None:
            super().__init__("lead", column, offset)
        else:
            super().__init__("lead", column, offset, default)


class FirstValueFunction(WindowFunction):
    """FIRST_VALUE(column) window function."""

    def __init__(self, column: Any):
        super().__init__("first_value", column)


class LastValueFunction(WindowFunction):
    """LAST_VALUE(column) window function."""

    def __init__(self, column: Any):
        super().__init__("last_value", column)


class NthValueFunction(WindowFunction):
    """NTH_VALUE(column, n) window function."""

    def __init__(self, column: Any, n: int):
        super().__init__("nth_value", column, n)
