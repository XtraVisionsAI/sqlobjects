"""SQLObjects Expression System - Type-Safe and Performance-Optimized

This module provides a simplified expression system that directly uses SQLAlchemy
native expressions, offering type safety, high performance, and modern database
expression support without unnecessary abstraction layers.

Key Design Principles:
- Direct SQLAlchemy integration for zero-overhead abstraction
- Type safety through native SQLAlchemy field references
- Intelligent subquery support with automatic type inference
- Full compatibility with SQLAlchemy ecosystem

Usage Examples:
    # Direct field references with type safety
    User.name.upper()                    # Chain methods on fields
    User.age >= 18                       # Direct comparisons

    # Database functions
    func.concat(User.first_name, ' ', User.last_name)
    func.extract('year', User.created_at)

    # Complex expressions
    condition = and_(
        User.age >= 18,
        or_(User.role == 'admin', User.is_staff == True)
    )

    # Subqueries with intelligent type inference
    avg_salary = User.objects.aggregate(
        avg_sal=func.avg(User.salary)
    ).subquery(query_type="scalar")
"""

from typing import Any

# SQLAlchemy core expressions - direct imports for zero overhead
from sqlalchemy import func
from sqlalchemy.orm import defer, joinedload, load_only, selectinload, subqueryload, undefer
from sqlalchemy.sql import Select, and_, asc, desc, exists, literal, not_, nullsfirst, nullslast, or_, text
from sqlalchemy.sql.expression import BinaryExpression

from .exceptions import ValidationError


__all__ = [
    # Core expression building
    "func",
    "and_",
    "or_",
    "not_",
    "exists",
    "text",
    "literal",
    # Query ordering
    "asc",
    "desc",
    "nullsfirst",
    "nullslast",
    # Relationship loading optimization
    "joinedload",
    "selectinload",
    "subqueryload",
    "defer",
    "undefer",
    "load_only",
    # Subquery support
    "SubqueryExpression",
    # Function mixins and results
    "FunctionMixin",
    "StringFunctionMixin",
    "NumericFunctionMixin",
    "DateTimeFunctionMixin",
    "FunctionResult",
]


class SubqueryExpression:
    """Intelligent subquery expression supporting multiple SQLAlchemy subquery types.

    This class provides a unified interface for creating and managing different types
    of subqueries including table subqueries, scalar subqueries, and existence subqueries.
    It automatically handles type conversion and provides operator overloading for
    seamless integration with other expressions.

    Examples:
        >>> # Table subquery for JOIN operations
        >>> subq = User.objects.filter(age__gte=18).subquery()
        >>> # Scalar subquery for comparisons
        >>> avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery("scalar")
        >>> # Existence subquery for boolean conditions
        >>> has_posts = Post.objects.filter(author_id=User.id).subquery("exists")
    """

    def __init__(self, query: Select, name: str | None = None, query_type: str = "auto"):
        """Initialize subquery expression with intelligent type inference.

        Args:
            query: SQLAlchemy Select query to convert to subquery
            name: Optional alias name for the subquery
            query_type: Type of subquery ('auto', 'table', 'scalar', 'exists')

        Raises:
            ValidationError: If query_type is invalid
        """
        valid_types = {"auto", "table", "scalar", "exists"}
        if query_type not in valid_types:
            raise ValidationError(f"Unknown query type: {query_type}. Available types: {', '.join(valid_types)}")

        self.query = query
        self.name = name
        self.query_type = self._infer_type() if query_type == "auto" else query_type
        self._subquery = None
        self._scalar_subquery = None
        self._exists_subquery = None

    def _infer_type(self) -> str:
        """Automatically infer the appropriate subquery type based on query structure.

        Analyzes query characteristics including column count, aggregate functions,
        and LIMIT clauses to determine the most suitable subquery type.

        Returns:
            Inferred subquery type ('scalar', 'table', or 'exists')
        """
        try:
            structure = self._analyze_query_structure()

            # Rule 1: Clear scalar query characteristics
            if (
                structure["has_single_column"]
                and structure["has_aggregates"]
                and (structure["has_limit_one"] or structure["is_count_query"])
            ):
                return "scalar"

            # Rule 2: Single column aggregate query (commonly used for comparisons)
            if structure["has_single_column"] and structure["has_aggregates"]:
                return "scalar"

            # Rule 3: Multi-column queries default to table subquery
            if structure["column_count"] > 1:
                return "table"

            # Rule 4: Single column non-aggregate query (e.g., ID lists)
            if structure["has_single_column"] and not structure["has_aggregates"]:
                return "table"  # For IN conditions

            # Default: table subquery
            return "table"

        except Exception:  # noqa
            # Default to table subquery when inference fails
            return "table"

    def _analyze_query_structure(self) -> dict:
        """Analyze query structure to extract inference criteria.

        Examines various aspects of the query including SELECT columns,
        aggregate functions, LIMIT clauses, and annotations to provide
        data for intelligent type inference.

        Returns:
            Dictionary containing query structure analysis results
        """
        analysis = {
            "select_columns": [],
            "has_aggregates": False,
            "has_single_column": False,
            "has_limit_one": False,
            "has_annotations": False,
            "column_count": 0,
            "is_count_query": False,
        }

        try:
            # Analyze SELECT columns
            if hasattr(self.query, "selected_columns"):
                analysis["select_columns"] = list(self.query.selected_columns)  # noqa
                analysis["column_count"] = len(analysis["select_columns"])
                analysis["has_single_column"] = analysis["column_count"] == 1

            # Analyze aggregate functions (simplified detection)
            query_str = str(self.query).lower()
            aggregate_keywords = ["count(", "sum(", "avg(", "max(", "min("]
            analysis["has_aggregates"] = any(keyword in query_str for keyword in aggregate_keywords)

            # Analyze LIMIT clause
            analysis["has_limit_one"] = (
                hasattr(self.query, "_limit") and self.query._limit is not None and self.query._limit == 1  # noqa
            )

            # Detect count queries
            analysis["is_count_query"] = "count(" in query_str

        except Exception:  # noqa
            # Return safe defaults when analysis fails
            pass

        return analysis

    def resolve(self, model_class=None) -> Any:
        """Resolve to appropriate SQLAlchemy object based on subquery type.

        Args:
            model_class: Model class for field resolution (unused for subqueries)

        Returns:
            SQLAlchemy subquery object (Subquery, ScalarSelect, or Exists)

        Raises:
            ValidationError: If subquery conversion fails
        """
        try:
            if self.query_type == "scalar":
                return self._get_scalar_subquery()
            elif self.query_type == "exists":
                return self._get_exists_subquery()
            else:  # 'table'
                return self._get_table_subquery()
        except Exception as e:
            raise ValidationError(f"Subquery conversion failed: {e}") from e

    def _get_table_subquery(self):
        """Get table subquery (equivalent to SQLAlchemy subquery()).

        Creates a table subquery that can be used in JOIN operations
        and other table-level operations.

        Returns:
            SQLAlchemy Subquery object

        Raises:
            ValidationError: If subquery creation fails
        """
        if self._subquery is None:
            try:
                self._subquery = self.query.subquery(name=self.name)
            except Exception as e:
                raise ValidationError(f"Subquery build failed: {e}") from e
        return self._subquery

    def _get_scalar_subquery(self):
        """Get scalar subquery (equivalent to SQLAlchemy scalar_subquery()).

        Creates a scalar subquery that returns a single value and can be used
        in comparisons and arithmetic operations.

        Returns:
            SQLAlchemy ScalarSelect object

        Raises:
            ValidationError: If scalar subquery creation fails
        """
        if self._scalar_subquery is None:
            try:
                self._scalar_subquery = self.query.scalar_subquery()
            except Exception as e:
                raise ValidationError(f"Scalar subquery build failed: {e}") from e
        return self._scalar_subquery

    def _get_exists_subquery(self):
        """Get existence subquery (equivalent to SQLAlchemy exists()).

        Creates an existence subquery that returns a boolean value indicating
        whether any rows match the subquery conditions.

        Returns:
            SQLAlchemy Exists object

        Raises:
            ValidationError: If existence subquery creation fails
        """
        if self._exists_subquery is None:
            try:
                self._exists_subquery = exists(self.query)
            except Exception as e:
                raise ValidationError(f"Exists subquery build failed: {e}") from e
        return self._exists_subquery

    @property
    def c(self):
        """Access subquery columns (only applicable to table subqueries).

        Provides access to the columns of a table subquery, similar to
        SQLAlchemy's subquery.c attribute.

        Returns:
            Column collection for the table subquery

        Raises:
            ValidationError: If called on non-table subquery types
        """
        if self.query_type != "table":
            raise ValidationError(f"Column access not supported on {self.query_type} subquery")
        return self._get_table_subquery().c

    def alias(self, name: str) -> "SubqueryExpression":
        """Create an alias for the subquery.

        Args:
            name: Alias name for the subquery

        Returns:
            New SubqueryExpression with the specified alias
        """
        return SubqueryExpression(self.query, name, self.query_type)

    def as_scalar(self) -> "SubqueryExpression":
        """Convert to scalar subquery type.

        Returns:
            New SubqueryExpression configured as scalar subquery
        """
        return SubqueryExpression(self.query, self.name, "scalar")

    def as_exists(self) -> "SubqueryExpression":
        """Convert to existence subquery type.

        Returns:
            New SubqueryExpression configured as existence subquery
        """
        return SubqueryExpression(self.query, self.name, "exists")

    def as_table(self) -> "SubqueryExpression":
        """Convert to table subquery type.

        Returns:
            New SubqueryExpression configured as table subquery
        """
        return SubqueryExpression(self.query, self.name, "table")

    # Operator overloading with automatic type adaptation
    def __eq__(self, other):
        """Equality comparison with automatic type handling."""
        if self.query_type == "table":
            return self.as_scalar().resolve() == other
        return self.resolve() == other

    def __gt__(self, other):
        """Greater than comparison with automatic scalar conversion."""
        if self.query_type == "table":
            return self.as_scalar().resolve() > other
        return self.resolve() > other

    def __lt__(self, other):
        """Less than comparison with automatic scalar conversion."""
        if self.query_type == "table":
            return self.as_scalar().resolve() < other
        return self.resolve() < other

    def __ge__(self, other):
        """Greater than or equal comparison with automatic scalar conversion."""
        if self.query_type == "table":
            return self.as_scalar().resolve() >= other
        return self.resolve() >= other

    def __le__(self, other):
        """Less than or equal comparison with automatic scalar conversion."""
        if self.query_type == "table":
            return self.as_scalar().resolve() <= other
        return self.resolve() <= other


class FunctionMixin:
    """函数方法混入类，减少代码重复"""

    def _get_expression(self):
        """子类需要实现这个方法来返回当前的表达式"""
        return self.expr  # type: ignore[attr-defined]

    def _create_result(self, func_call):  # noqa
        """创建 FunctionResult 对象"""
        return FunctionResult(func_call)

    # === 通用函数 ===
    def cast(self, type_: str, **kwargs) -> "FunctionResult":
        from .fields import create_type_instance

        sqlalchemy_type = create_type_instance(type_, **kwargs)
        return self._create_result(func.cast(self._get_expression(), sqlalchemy_type))

    def is_null(self) -> BinaryExpression:
        return self._get_expression().is_(None)

    def is_not_null(self) -> BinaryExpression:
        return self._get_expression().is_not(None)

    def case(self, *conditions, else_=None) -> "FunctionResult":
        if len(conditions) == 1 and isinstance(conditions[0], dict):
            cases = list(conditions[0].items())
        else:
            cases = conditions
        return self._create_result(func.case(*cases, else_=else_))

    def coalesce(self, *values) -> "FunctionResult":
        return self._create_result(func.coalesce(self._get_expression(), *values))

    def nullif(self, value) -> "FunctionResult":
        return self._create_result(func.nullif(self._get_expression(), value))


class StringFunctionMixin(FunctionMixin):
    """字符串函数混入"""

    def upper(self) -> "FunctionResult":
        return self._create_result(func.upper(self._get_expression()))

    def lower(self) -> "FunctionResult":
        return self._create_result(func.lower(self._get_expression()))

    def trim(self) -> "FunctionResult":
        return self._create_result(func.trim(self._get_expression()))

    def length(self) -> "FunctionResult":
        return self._create_result(func.length(self._get_expression()))

    def substring(self, start: int, length: int | None = None) -> "FunctionResult":
        expr = self._get_expression()
        if length is not None:
            return self._create_result(func.substring(expr, start, length))
        return self._create_result(func.substring(expr, start))

    def regexp_replace(self, pattern: str, replacement: str) -> "FunctionResult":
        return self._create_result(func.regexp_replace(self._get_expression(), pattern, replacement))

    def split_part(self, delimiter: str, field: int) -> "FunctionResult":
        return self._create_result(func.split_part(self._get_expression(), delimiter, field))

    def position(self, substring: str) -> "FunctionResult":
        return self._create_result(func.position(substring, self._get_expression()))

    def reverse(self) -> "FunctionResult":
        return self._create_result(func.reverse(self._get_expression()))

    def md5(self) -> "FunctionResult":
        return self._create_result(func.md5(self._get_expression()))


class NumericFunctionMixin(FunctionMixin):
    """数值函数混入"""

    def abs(self) -> "FunctionResult":
        return self._create_result(func.abs(self._get_expression()))

    def round(self, precision: int = 0) -> "FunctionResult":
        return self._create_result(func.round(self._get_expression(), precision))

    def ceil(self) -> "FunctionResult":
        return self._create_result(func.ceil(self._get_expression()))

    def floor(self) -> "FunctionResult":
        return self._create_result(func.floor(self._get_expression()))

    def sqrt(self) -> "FunctionResult":
        return self._create_result(func.sqrt(self._get_expression()))

    def power(self, exponent) -> "FunctionResult":
        return self._create_result(func.power(self._get_expression(), exponent))

    def mod(self, divisor) -> "FunctionResult":
        return self._create_result(func.mod(self._get_expression(), divisor))

    def sign(self) -> "FunctionResult":
        return self._create_result(func.sign(self._get_expression()))

    # 聚合函数
    def sum(self) -> "FunctionResult":
        return self._create_result(func.sum(self._get_expression()))

    def avg(self) -> "FunctionResult":
        return self._create_result(func.avg(self._get_expression()))

    def max(self) -> "FunctionResult":
        return self._create_result(func.max(self._get_expression()))

    def min(self) -> "FunctionResult":
        return self._create_result(func.min(self._get_expression()))

    def count(self) -> "FunctionResult":
        return self._create_result(func.count(self._get_expression()))


class DateTimeFunctionMixin(FunctionMixin):
    """日期时间函数混入"""

    def extract(self, field: str) -> "FunctionResult":
        return self._create_result(func.extract(field, self._get_expression()))

    def year(self) -> "FunctionResult":
        return self._create_result(func.extract("year", self._get_expression()))

    def month(self) -> "FunctionResult":
        return self._create_result(func.extract("month", self._get_expression()))

    def day(self) -> "FunctionResult":
        return self._create_result(func.extract("day", self._get_expression()))

    def hour(self) -> "FunctionResult":
        return self._create_result(func.extract("hour", self._get_expression()))

    def minute(self) -> "FunctionResult":
        return self._create_result(func.extract("minute", self._get_expression()))

    def age_in_years(self) -> "FunctionResult":
        expr = self._get_expression()
        return self._create_result(func.extract("year", func.age(func.now(), expr)))

    def age_in_months(self) -> "FunctionResult":
        expr = self._get_expression()
        return self._create_result(func.extract("month", func.age(func.now(), expr)))

    def days_between(self, end_date) -> "FunctionResult":
        expr = self._get_expression()
        return self._create_result(func.extract("day", func.age(end_date, expr)))

    def date_trunc(self, precision: str) -> "FunctionResult":
        return self._create_result(func.date_trunc(precision, self._get_expression()))

    def to_char(self, format_str: str) -> "FunctionResult":
        return self._create_result(func.to_char(self._get_expression(), format_str))

    def add_days(self, days: int) -> "FunctionResult":
        expr = self._get_expression()
        return self._create_result(expr + func.interval(f"{days} days"))


class FunctionResult:
    """函数调用结果，支持继续链式调用"""

    def __init__(self, expression):
        self.expression = expression

    # === 字符串函数 ===
    def upper(self) -> "FunctionResult":
        return FunctionResult(func.upper(self.expression))

    def lower(self) -> "FunctionResult":
        return FunctionResult(func.lower(self.expression))

    def substring(self, start: int, length: int | None = None) -> "FunctionResult":
        if length is not None:
            return FunctionResult(func.substring(self.expression, start, length))
        return FunctionResult(func.substring(self.expression, start))

    def trim(self) -> "FunctionResult":
        return FunctionResult(func.trim(self.expression))

    def length(self) -> "FunctionResult":
        return FunctionResult(func.length(self.expression))

    def regexp_replace(self, pattern: str, replacement: str) -> "FunctionResult":
        return FunctionResult(func.regexp_replace(self.expression, pattern, replacement))

    def split_part(self, delimiter: str, field: int) -> "FunctionResult":
        return FunctionResult(func.split_part(self.expression, delimiter, field))

    def position(self, substring: str) -> "FunctionResult":
        return FunctionResult(func.position(substring, self.expression))

    def reverse(self) -> "FunctionResult":
        return FunctionResult(func.reverse(self.expression))

    def md5(self) -> "FunctionResult":
        return FunctionResult(func.md5(self.expression))

    # === 数值函数 ===
    def abs(self) -> "FunctionResult":
        return FunctionResult(func.abs(self.expression))

    def round(self, precision: int = 0) -> "FunctionResult":
        return FunctionResult(func.round(self.expression, precision))

    def ceil(self) -> "FunctionResult":
        return FunctionResult(func.ceil(self.expression))

    def floor(self) -> "FunctionResult":
        return FunctionResult(func.floor(self.expression))

    def sqrt(self) -> "FunctionResult":
        return FunctionResult(func.sqrt(self.expression))

    def power(self, exponent) -> "FunctionResult":
        return FunctionResult(func.power(self.expression, exponent))

    def mod(self, divisor) -> "FunctionResult":
        return FunctionResult(func.mod(self.expression, divisor))

    def sign(self) -> "FunctionResult":
        return FunctionResult(func.sign(self.expression))

    # === 聚合函数 ===
    def sum(self) -> "FunctionResult":
        return FunctionResult(func.sum(self.expression))

    def avg(self) -> "FunctionResult":
        return FunctionResult(func.avg(self.expression))

    def max(self) -> "FunctionResult":
        return FunctionResult(func.max(self.expression))

    def min(self) -> "FunctionResult":
        return FunctionResult(func.min(self.expression))

    def count(self) -> "FunctionResult":
        return FunctionResult(func.count(self.expression))

    # === 日期函数 ===
    def year(self) -> "FunctionResult":
        return FunctionResult(func.extract("year", self.expression))

    def month(self) -> "FunctionResult":
        return FunctionResult(func.extract("month", self.expression))

    def day(self) -> "FunctionResult":
        return FunctionResult(func.extract("day", self.expression))

    def hour(self) -> "FunctionResult":
        return FunctionResult(func.extract("hour", self.expression))

    def minute(self) -> "FunctionResult":
        return FunctionResult(func.extract("minute", self.expression))

    def extract(self, field: str) -> "FunctionResult":
        return FunctionResult(func.extract(field, self.expression))

    def age_in_years(self) -> "FunctionResult":
        return FunctionResult(func.extract("year", func.age(func.now(), self.expression)))

    def age_in_months(self) -> "FunctionResult":
        return FunctionResult(func.extract("month", func.age(func.now(), self.expression)))

    def days_between(self, end_date) -> "FunctionResult":
        return FunctionResult(func.extract("day", func.age(end_date, self.expression)))

    def date_trunc(self, precision: str) -> "FunctionResult":
        return FunctionResult(func.date_trunc(precision, self.expression))

    def to_char(self, format_str: str) -> "FunctionResult":
        return FunctionResult(func.to_char(self.expression, format_str))

    def add_days(self, days: int) -> "FunctionResult":
        return FunctionResult(self.expression + func.interval(f"{days} days"))

    # === 通用函数 ===
    def cast(self, type_: str, **kwargs) -> "FunctionResult":
        from .fields import create_type_instance

        sqlalchemy_type = create_type_instance(type_, **kwargs)
        return FunctionResult(func.cast(self.expression, sqlalchemy_type))

    def coalesce(self, *values) -> "FunctionResult":
        return FunctionResult(func.coalesce(self.expression, *values))

    def nullif(self, value) -> "FunctionResult":
        return FunctionResult(func.nullif(self.expression, value))

    def case(self, *conditions, else_=None) -> "FunctionResult":  # noqa
        if len(conditions) == 1 and isinstance(conditions[0], dict):
            cases = list(conditions[0].items())
        else:
            cases = conditions
        return FunctionResult(func.case(*cases, else_=else_))

    def distinct(self) -> "FunctionResult":
        return FunctionResult(func.distinct(self.expression))

    # === SQLAlchemy 方法代理 ===
    def label(self, name: str):
        return self.expression.label(name)

    def asc(self):
        return self.expression.asc()

    def desc(self):
        return self.expression.desc()

    # === 操作符重载 ===
    def __eq__(self, other) -> BinaryExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return self.expression == other  # noqa

    def __ne__(self, other) -> BinaryExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return self.expression != other  # noqa

    def __lt__(self, other) -> BinaryExpression:
        return self.expression < other  # noqa

    def __le__(self, other) -> BinaryExpression:
        return self.expression <= other  # noqa

    def __gt__(self, other) -> BinaryExpression:
        return self.expression > other  # noqa

    def __ge__(self, other) -> BinaryExpression:
        return self.expression >= other  # noqa

    def like(self, pattern: str) -> BinaryExpression:
        return self.expression.like(pattern)

    def ilike(self, pattern: str) -> BinaryExpression:
        return self.expression.ilike(pattern)

    def between(self, min_val, max_val) -> BinaryExpression:
        return self.expression.between(min_val, max_val)

    def in_(self, values) -> BinaryExpression:
        return self.expression.in_(values)

    # === 代理其他方法 ===
    def __getattr__(self, name):
        return getattr(self.expression, name)
