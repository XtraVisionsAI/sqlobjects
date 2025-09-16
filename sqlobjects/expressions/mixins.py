from typing import TYPE_CHECKING

from sqlalchemy.sql import func
from sqlalchemy.sql.elements import ColumnElement

from .function import FunctionExpression


class FunctionMixin:
    """Base mixin providing common method handling for database functions

    Provides shared functionality for method resolution, result wrapping,
    and error handling across different function mixin implementations.
    """

    def _get_method_source(self):
        """Get the object that provides callable methods

        Returns:
            Object containing the methods to be called

        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError("Subclasses must implement _get_method_source()")

    def _wrap_method_result(self, method, *args, **kwargs):
        """Execute method and wrap result in FunctionExpression if needed

        Args:
            method: Callable method to execute
            *args: Arguments to pass to method
            **kwargs: Keyword arguments to pass to method

        Returns:
            FunctionExpression wrapping the method result
        """
        result = method(*args, **kwargs)
        return result if isinstance(result, FunctionExpression) else FunctionExpression(result)

    def _handle_missing_method(self, name):
        """Handle cases where requested method is not available

        Args:
            name: Name of the requested method

        Raises:
            AttributeError: With information about available methods
        """
        source = self._get_method_source()
        available = [m for m in dir(source) if not m.startswith("_") and callable(getattr(source, m, None))]
        raise AttributeError(f"Method '{name}' not available. Available methods: {available}")

    def _get_expression(self):
        """Get expression object for legacy compatibility

        Returns:
            The expression object to apply functions to

        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError("Subclasses must implement _get_expression()")

    def _create_result(self, func_call):  # noqa
        """Create FunctionExpression object for legacy compatibility

        Args:
            func_call: SQLAlchemy function call result

        Returns:
            FunctionExpression wrapping the function call
        """
        return FunctionExpression(func_call)

    # === General functions ===
    def cast(self, type_: str, **kwargs) -> "FunctionExpression":
        """Cast expression to specified type

        Args:
            type_: Target type name
            **kwargs: Additional type parameters

        Returns:
            FunctionExpression with cast operation
        """
        return FunctionExpression(self._get_expression()).cast(type_, **kwargs)

    def is_null(self) -> ColumnElement[bool]:
        """Check if expression is NULL

        Returns:
            Boolean expression for NULL check
        """
        return self._get_expression().is_(None)

    def is_not_null(self) -> ColumnElement[bool]:
        """Check if expression is NOT NULL

        Returns:
            Boolean expression for NOT NULL check
        """
        return self._get_expression().is_not(None)

    def case(self, *conditions, else_=None) -> "FunctionExpression":
        """Create CASE expression

        Args:
            *conditions: Condition tuples or dictionary
            else_: Default value for ELSE clause

        Returns:
            FunctionExpression with CASE operation
        """
        if len(conditions) == 1 and isinstance(conditions[0], dict):
            cases = list(conditions[0].items())
        else:
            cases = conditions
        return self._create_result(func.case(*cases, else_=else_))

    def coalesce(self, *values) -> "FunctionExpression":
        """Return first non-NULL value

        Args:
            *values: Values to check for non-NULL

        Returns:
            FunctionExpression with COALESCE operation
        """
        return self._create_result(func.coalesce(self._get_expression(), *values))

    def nullif(self, value) -> "FunctionExpression":
        """Return NULL if expression equals value

        Args:
            value: Value to compare against

        Returns:
            FunctionExpression with NULLIF operation
        """
        return self._create_result(func.nullif(self._get_expression(), value))

    # === Ordering methods ===
    def asc(self):
        """Create ascending order expression

        Returns:
            SQLAlchemy ascending order expression
        """
        return self._get_expression().asc()

    def desc(self):
        """Create descending order expression

        Returns:
            SQLAlchemy descending order expression
        """
        return self._get_expression().desc()


class ColumnAttributeFunctionMixin(FunctionMixin):
    """Type-safe method resolver for ColumnAttribute fields

    Provides type-safe method resolution by delegating to the appropriate
    Comparator based on the field's data type. Ensures only valid methods
    for each type are accessible at runtime.
    """

    def _get_method_source(self):
        """Get the comparator that provides type-specific methods

        Returns:
            The comparator instance for this field's type
        """
        return self.__column__.comparator  # type: ignore[reportAttributeAccessIssue]

    def _get_expression(self):
        """Get expression from ColumnAttribute for legacy compatibility

        Returns:
            The underlying SQLAlchemy column
        """
        return self.__column__

    def __getattr__(self, name):
        """Type-safe method resolution through comparator

        Only allows methods that are available on the field's type-specific
        comparator, ensuring type safety at runtime.

        Args:
            name: Name of the method to resolve

        Returns:
            Callable method that returns FunctionExpression

        Raises:
            AttributeError: If method is not available for this field type
        """
        method_source = self._get_method_source()

        if hasattr(method_source, name):
            method = getattr(method_source, name)
            if callable(method):
                return lambda *args, **kwargs: self._wrap_method_result(method, *args, **kwargs)

        self._handle_missing_method(name)

    if TYPE_CHECKING:
        # String methods
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

        # Numeric methods
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

        # DateTime methods
        def year(self) -> "FunctionExpression": ...
        def month(self) -> "FunctionExpression": ...
        def day(self) -> "FunctionExpression": ...
        def hour(self) -> "FunctionExpression": ...
        def minute(self) -> "FunctionExpression": ...
        def extract(self, field: str) -> "FunctionExpression": ...
        def date_trunc(self, precision: str) -> "FunctionExpression": ...

        # JSON methods
        def extract_path(self, path) -> "FunctionExpression": ...
        def extract_text(self, path) -> "FunctionExpression": ...

        # Common methods (all types)
        def sum(self) -> "FunctionExpression": ...
        def avg(self) -> "FunctionExpression": ...
        def max(self) -> "FunctionExpression": ...
        def min(self) -> "FunctionExpression": ...
        def count(self) -> "FunctionExpression": ...
        def count_distinct(self) -> "FunctionExpression": ...
        def distinct(self) -> "FunctionExpression": ...
        def cast(self, type_: str, **kwargs) -> "FunctionExpression": ...
        def coalesce(self, *values) -> "FunctionExpression": ...
        def nullif(self, value) -> "FunctionExpression": ...
        def case(self, *conditions, else_=None) -> "FunctionExpression": ...
        def greatest(self, *args) -> "FunctionExpression": ...
        def least(self, *args) -> "FunctionExpression": ...
        def raw(self, sql: str, *args, **kwargs) -> "FunctionExpression": ...

        # Ordering methods
        def asc(self): ...
        def desc(self): ...

        # Comparison methods
        def like(self, pattern: str) -> "FunctionExpression": ...
        def ilike(self, pattern: str) -> "FunctionExpression": ...
        def in_(self, values) -> "FunctionExpression": ...
        def between(self, low, high) -> "FunctionExpression": ...
        def contains(self, other) -> "FunctionExpression": ...
        def startswith(self, other) -> "FunctionExpression": ...
        def endswith(self, other) -> "FunctionExpression": ...
        def is_(self, other) -> "FunctionExpression": ...
        def is_not(self, other) -> "FunctionExpression": ...
