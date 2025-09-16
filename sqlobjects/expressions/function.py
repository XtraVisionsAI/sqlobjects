from typing import TYPE_CHECKING

from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import func

from .subquery import SubqueryExpression


if TYPE_CHECKING:
    # Provide IDE hints for common database functions
    class _FunctionMethods:
        # String functions
        def upper(self) -> "FunctionExpression": ...
        def lower(self) -> "FunctionExpression": ...
        def trim(self) -> "FunctionExpression": ...
        def length(self) -> "FunctionExpression": ...
        def substring(self, start: int, length: int | None = None) -> "FunctionExpression": ...
        def concat(self, *args) -> "FunctionExpression": ...
        def replace(self, old: str, new: str) -> "FunctionExpression": ...
        def reverse(self) -> "FunctionExpression": ...
        def md5(self) -> "FunctionExpression": ...
        def left(self, length: int) -> "FunctionExpression": ...
        def right(self, length: int) -> "FunctionExpression": ...
        def lpad(self, length: int, fill_char: str = " ") -> "FunctionExpression": ...
        def rpad(self, length: int, fill_char: str = " ") -> "FunctionExpression": ...
        def ltrim(self, chars: str | None = None) -> "FunctionExpression": ...
        def rtrim(self, chars: str | None = None) -> "FunctionExpression": ...

        # Numeric functions
        def abs(self) -> "FunctionExpression": ...
        def round(self, precision: int = 0) -> "FunctionExpression": ...
        def ceil(self) -> "FunctionExpression": ...
        def floor(self) -> "FunctionExpression": ...
        def sqrt(self) -> "FunctionExpression": ...
        def power(self, exponent) -> "FunctionExpression": ...
        def mod(self, divisor) -> "FunctionExpression": ...
        def sign(self) -> "FunctionExpression": ...
        def trunc(self, precision: int = 0) -> "FunctionExpression": ...
        def exp(self) -> "FunctionExpression": ...
        def ln(self) -> "FunctionExpression": ...
        def log(self, base: int = 10) -> "FunctionExpression": ...

        # Aggregate functions
        def sum(self) -> "FunctionExpression": ...
        def avg(self) -> "FunctionExpression": ...
        def max(self) -> "FunctionExpression": ...
        def min(self) -> "FunctionExpression": ...
        def count(self) -> "FunctionExpression": ...
        def count_distinct(self) -> "FunctionExpression": ...
        def distinct(self) -> "FunctionExpression": ...

        # Date/Time functions
        def year(self) -> "FunctionExpression": ...
        def month(self) -> "FunctionExpression": ...
        def day(self) -> "FunctionExpression": ...
        def hour(self) -> "FunctionExpression": ...
        def minute(self) -> "FunctionExpression": ...
        def extract(self, field: str) -> "FunctionExpression": ...
        def date_trunc(self, precision: str) -> "FunctionExpression": ...

        # General functions
        def cast(self, type_: str, **kwargs) -> "FunctionExpression": ...
        def coalesce(self, *values) -> "FunctionExpression": ...
        def nullif(self, value) -> "FunctionExpression": ...
        def case(self, *conditions, else_=None) -> "FunctionExpression": ...
        def greatest(self, *args) -> "FunctionExpression": ...
        def least(self, *args) -> "FunctionExpression": ...

        # Comparison functions (chainable)
        def like(self, pattern: str) -> "FunctionExpression": ...
        def ilike(self, pattern: str) -> "FunctionExpression": ...
        def not_like(self, pattern: str) -> "FunctionExpression": ...
        def not_ilike(self, pattern: str) -> "FunctionExpression": ...
        def between(self, min_val, max_val) -> "FunctionExpression": ...
        def in_(self, values) -> "FunctionExpression": ...
        def not_in(self, values) -> "FunctionExpression": ...
        def is_(self, other) -> "FunctionExpression": ...
        def is_not(self, other) -> "FunctionExpression": ...


class FunctionExpression:
    """Function call result supporting continued method chaining

    Wraps SQLAlchemy function expressions and provides chainable methods
    for building complex database expressions.
    """

    if TYPE_CHECKING:
        # Inherit all method hints for IDE support
        def __new__(cls, *args, **kwargs) -> "FunctionExpression & _FunctionMethods": ...  # type: ignore

    def __init__(self, expression):
        """Initialize function expression

        Args:
            expression: SQLAlchemy expression object to wrap
        """
        self.expression = expression

    def __getattr__(self, name):
        """Smart proxy for continued method chaining

        Args:
            name: Attribute name to access

        Returns:
            Method or attribute from underlying expression or new FunctionExpression
        """
        # First try the underlying SQLAlchemy expression
        if hasattr(self.expression, name):
            return getattr(self.expression, name)

        # Then delegate to SQLAlchemy func - let database decide if function exists
        db_func = getattr(func, name)
        return lambda *args, **kwargs: FunctionExpression(db_func(self.expression, *args, **kwargs))

    def raw(self, sql: str, *args, **kwargs) -> "FunctionExpression":
        """Execute raw SQL function with flexible argument positioning

        Args:
            sql: Raw SQL function name or expression
            *args: Arguments to pass to the function. Use ... (Ellipsis) as placeholder for current expression
            **kwargs: Additional keyword arguments passed to the function

        Returns:
            New FunctionExpression with the raw SQL function applied

        Examples:
            # Current expression as first argument (default)
            User.age.avg().raw('CUSTOM_FUNCTION', 'param1')
            # Generates: CUSTOM_FUNCTION(avg(age), 'param1')

            # Current expression at specific position
            User.age.avg().raw('CUSTOM_FUNCTION', 'param1', ..., 'param2')
            # Generates: CUSTOM_FUNCTION('param1', avg(age), 'param2')

            # Only current expression
            User.age.raw('CUSTOM_FUNCTION')
            # Generates: CUSTOM_FUNCTION(age)
        """
        from sqlalchemy import literal

        # Check if ... (Ellipsis) is used as placeholder
        if ... in args:
            # Replace ... with current expression
            all_args = []
            for arg in args:
                if arg is ...:
                    all_args.append(self.expression)
                else:
                    all_args.append(literal(arg))
        else:
            # Default behavior: current expression as first argument
            all_args = [self.expression]
            for arg in args:
                all_args.append(literal(arg))

        # Use func to create the raw function call
        raw_func = getattr(func, sql)
        return FunctionExpression(raw_func(*all_args, **kwargs))

    def resolve(self, table_or_model=None):
        """Resolve to underlying SQLAlchemy expression.

        Args:
            table_or_model: Table object or model class (unused for function expressions)

        Returns:
            The underlying SQLAlchemy expression
        """
        return self.expression

    def cast(self, type_: str, **kwargs) -> "FunctionExpression":
        """Cast expression to specified type

        Args:
            type_: Target type name
            **kwargs: Additional type parameters

        Returns:
            FunctionExpression with cast operation
        """
        from sqlalchemy.sql import cast

        from ..fields.types import create_type_instance, get_type_definition

        # use type class directly when no parameters provided
        if not kwargs:
            type_config = get_type_definition(type_)
            sqlalchemy_type = type_config["sqlalchemy_type"]
        else:
            sqlalchemy_type = create_type_instance(type_, kwargs)

        return FunctionExpression(cast(self.expression, sqlalchemy_type))

    # === Special Methods ===

    def label(self, name: str):
        """Create labeled expression for SELECT clauses"""
        return self.expression.label(name)

    def asc(self):
        """Create ascending order expression"""
        return self.expression.asc()

    def desc(self):
        """Create descending order expression"""
        return self.expression.desc()

    # === Comparison Operators ===

    def __eq__(self, other) -> ColumnElement[bool]:  # type: ignore[reportIncompatibleMethodOverride]
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression == other  # noqa

    def __ne__(self, other) -> ColumnElement[bool]:  # type: ignore[reportIncompatibleMethodOverride]
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression != other  # noqa

    def __lt__(self, other) -> ColumnElement[bool]:
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression < other  # noqa

    def __le__(self, other) -> ColumnElement[bool]:
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression <= other  # noqa

    def __gt__(self, other) -> ColumnElement[bool]:
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression > other  # noqa

    def __ge__(self, other) -> ColumnElement[bool]:
        if isinstance(other, FunctionExpression):
            other = other.expression
        return self.expression >= other  # noqa

    def like(self, pattern: str) -> "FunctionExpression":
        return FunctionExpression(self.expression.like(pattern))

    def ilike(self, pattern: str) -> "FunctionExpression":
        return FunctionExpression(self.expression.ilike(pattern))

    def not_like(self, pattern: str) -> "FunctionExpression":
        return FunctionExpression(~self.expression.like(pattern))

    def not_ilike(self, pattern: str) -> "FunctionExpression":
        return FunctionExpression(~self.expression.ilike(pattern))

    def between(self, min_val, max_val) -> "FunctionExpression":
        return FunctionExpression(self.expression.between(min_val, max_val))

    def in_(self, values) -> "FunctionExpression":
        # Auto-wrap SubqueryExpression in list
        if isinstance(values, SubqueryExpression):
            values = [values]
        return FunctionExpression(self.expression.in_(values))

    def not_in(self, values) -> "FunctionExpression":
        # Auto-wrap SubqueryExpression in list
        if isinstance(values, SubqueryExpression):
            values = [values]
        return FunctionExpression(~self.expression.in_(values))

    def is_(self, other) -> "FunctionExpression":
        return FunctionExpression(self.expression.is_(other))

    def is_not(self, other) -> "FunctionExpression":
        return FunctionExpression(self.expression.is_not(other))

    # === Arithmetic Operators ===

    def __add__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(self.expression + other)

    def __radd__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(other + self.expression)

    def __sub__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(self.expression - other)

    def __rsub__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(other - self.expression)

    def __mul__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(self.expression * other)

    def __rmul__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(other * self.expression)

    def __truediv__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(self.expression / other)

    def __rtruediv__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(other / self.expression)

    def __mod__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(self.expression % other)

    def __rmod__(self, other):
        if isinstance(other, FunctionExpression):
            other = other.expression
        return FunctionExpression(other % self.expression)
