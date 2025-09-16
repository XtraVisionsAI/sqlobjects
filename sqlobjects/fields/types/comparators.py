from sqlalchemy import func
from sqlalchemy.sql.sqltypes import JSON, Boolean, DateTime, Integer, Numeric, String, TypeEngine

from ...expressions import FunctionExpression


class ComparatorMixin:
    """Base mixin class providing common database function methods."""

    def cast(self, type_, **kwargs) -> FunctionExpression:
        return FunctionExpression(self).cast(type_, **kwargs)

    def coalesce(self, *values) -> FunctionExpression:
        return FunctionExpression(func.coalesce(self, *values))

    def nullif(self, value) -> FunctionExpression:
        return FunctionExpression(func.nullif(self, value))

    def case(self, *conditions, else_=None) -> FunctionExpression:  # noqa
        if len(conditions) == 1 and isinstance(conditions[0], dict):
            cases = list(conditions[0].items())
        else:
            cases = conditions
        return FunctionExpression(func.case(*cases, else_=else_))

    def greatest(self, *args) -> FunctionExpression:
        return FunctionExpression(func.greatest(self, *args))

    def least(self, *args) -> FunctionExpression:
        return FunctionExpression(func.least(self, *args))

    # === Universal Aggregate Functions ===
    def sum(self) -> FunctionExpression:
        return FunctionExpression(func.sum(self))

    def avg(self) -> FunctionExpression:
        return FunctionExpression(func.avg(self))

    def max(self) -> FunctionExpression:
        return FunctionExpression(func.max(self))

    def min(self) -> FunctionExpression:
        return FunctionExpression(func.min(self))

    def count(self) -> FunctionExpression:
        return FunctionExpression(func.count(self))  # type: ignore[reportArgumentType]

    def count_distinct(self) -> FunctionExpression:
        return FunctionExpression(func.count(func.distinct(self)))

    def raw(self, sql: str, *args, **kwargs) -> FunctionExpression:
        from sqlalchemy import literal

        if ... in args:
            all_args = []
            for arg in args:
                if arg is ...:
                    all_args.append(self)
                else:
                    all_args.append(literal(arg))
        else:
            all_args = [self] + [literal(arg) for arg in args]
        raw_func = getattr(func, sql)
        return FunctionExpression(raw_func(*all_args, **kwargs))

    # Override comparison operators to return FunctionExpression
    def is_(self, other) -> FunctionExpression:
        return FunctionExpression(super().is_(other))  # type: ignore[reportAttributeAccessIssue]

    def is_not(self, other) -> FunctionExpression:
        return FunctionExpression(super().is_not(other))  # type: ignore[reportAttributeAccessIssue]

    def in_(self, other) -> FunctionExpression:
        return FunctionExpression(super().in_(other))  # type: ignore[reportAttributeAccessIssue]

    def between(self, cleft, cright, symmetric: bool = False) -> FunctionExpression:
        return FunctionExpression(super().between(cleft, cright, symmetric=symmetric))  # type: ignore[reportAttributeAccessIssue]

    def not_in(self, other) -> FunctionExpression:
        return FunctionExpression(super().not_in(other))  # type: ignore[reportAttributeAccessIssue]

    def notin_(self, other) -> FunctionExpression:
        return FunctionExpression(super().notin_(other))  # type: ignore[reportAttributeAccessIssue]

    def is_distinct_from(self, other) -> FunctionExpression:
        return FunctionExpression(super().is_distinct_from(other))  # type: ignore[reportAttributeAccessIssue]

    def is_not_distinct_from(self, other) -> FunctionExpression:
        return FunctionExpression(super().is_not_distinct_from(other))  # type: ignore[reportAttributeAccessIssue]

    def isnot(self, other) -> FunctionExpression:
        return FunctionExpression(super().isnot(other))  # type: ignore[reportAttributeAccessIssue]

    def isnot_distinct_from(self, other) -> FunctionExpression:
        return FunctionExpression(super().isnot_distinct_from(other))  # type: ignore[reportAttributeAccessIssue]

    # Ordering methods
    def asc(self) -> FunctionExpression:
        return FunctionExpression(super().asc())  # type: ignore[reportAttributeAccessIssue]

    def desc(self) -> FunctionExpression:
        return FunctionExpression(super().desc())  # type: ignore[reportAttributeAccessIssue]

    def nulls_first(self) -> FunctionExpression:
        return FunctionExpression(super().nulls_first())  # type: ignore[reportAttributeAccessIssue]

    def nulls_last(self) -> FunctionExpression:
        return FunctionExpression(super().nulls_last())  # type: ignore[reportAttributeAccessIssue]

    def nullsfirst(self) -> FunctionExpression:
        return FunctionExpression(super().nullsfirst())  # type: ignore[reportAttributeAccessIssue]

    def nullslast(self) -> FunctionExpression:
        return FunctionExpression(super().nullslast())  # type: ignore[reportAttributeAccessIssue]

    def distinct(self) -> FunctionExpression:
        return FunctionExpression(super().distinct())  # type: ignore[reportAttributeAccessIssue]


class StringComparator(ComparatorMixin, String.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """String type comparator with comprehensive string function methods."""

    def upper(self) -> FunctionExpression:
        return FunctionExpression(func.upper(self))

    def lower(self) -> FunctionExpression:
        return FunctionExpression(func.lower(self))

    def trim(self) -> FunctionExpression:
        return FunctionExpression(func.trim(self))

    def length(self) -> FunctionExpression:
        return FunctionExpression(func.length(self))

    def substring(self, start, length=None) -> FunctionExpression:
        if length is not None:
            return FunctionExpression(func.substring(self, start, length))
        return FunctionExpression(func.substring(self, start))

    def concat(self, *args) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(func.concat(self, *args))

    def replace(self, old: str, new: str) -> FunctionExpression:
        return FunctionExpression(func.replace(self, old, new))

    def reverse(self) -> FunctionExpression:
        return FunctionExpression(func.reverse(self))

    def md5(self) -> FunctionExpression:
        return FunctionExpression(func.md5(self))

    def left(self, length: int) -> FunctionExpression:
        return FunctionExpression(func.left(self, length))

    def right(self, length: int) -> FunctionExpression:
        return FunctionExpression(func.right(self, length))

    def lpad(self, length: int, fill_char: str = " ") -> FunctionExpression:
        return FunctionExpression(func.lpad(self, length, fill_char))

    def rpad(self, length: int, fill_char: str = " ") -> FunctionExpression:
        return FunctionExpression(func.rpad(self, length, fill_char))

    def ltrim(self, chars: str | None = None) -> FunctionExpression:
        if chars is not None:
            return FunctionExpression(func.ltrim(self, chars))
        return FunctionExpression(func.ltrim(self))

    def rtrim(self, chars: str | None = None) -> FunctionExpression:
        if chars is not None:
            return FunctionExpression(func.rtrim(self, chars))
        return FunctionExpression(func.rtrim(self))

    # Override inherited methods to return FunctionExpression
    def like(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        if escape is not None:
            return FunctionExpression(super().like(other, escape=escape))
        return FunctionExpression(super().like(other))

    def ilike(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        if escape is not None:
            return FunctionExpression(super().ilike(other, escape=escape))
        return FunctionExpression(super().ilike(other))

    def contains(self, other, **kw) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().contains(other, **kw))

    def startswith(self, other, escape: str | None = None, autoescape: bool = False) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().startswith(other, escape=escape, autoescape=autoescape))

    def endswith(self, other, escape: str | None = None, autoescape: bool = False) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().endswith(other, escape=escape, autoescape=autoescape))

    # Additional comparison methods for chaining support
    def icontains(self, other, **kw) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().icontains(other, **kw))

    def istartswith(self, other, escape: str | None = None, autoescape: bool = False) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().istartswith(other, escape=escape, autoescape=autoescape))

    def iendswith(self, other, escape: str | None = None, autoescape: bool = False) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().iendswith(other, escape=escape, autoescape=autoescape))

    def match(self, other, **kwargs) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().match(other, **kwargs))

    def regexp_match(self, pattern, flags: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().regexp_match(pattern, flags=flags))

    def regexp_replace(self, pattern, replacement, flags: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().regexp_replace(pattern, replacement, flags=flags))

    def not_like(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().not_like(other, escape=escape))

    def not_ilike(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().not_ilike(other, escape=escape))

    def notlike(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().notlike(other, escape=escape))

    def notilike(self, other: str, escape: str | None = None) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().notilike(other, escape=escape))

    def collate(self, collation: str) -> FunctionExpression:  # type: ignore[reportIncompatibleMethodOverride]
        return FunctionExpression(super().collate(collation))


class IntegerComparator(ComparatorMixin, Integer.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """Integer type comparator with comprehensive mathematical functions"""

    def abs(self) -> FunctionExpression:
        return FunctionExpression(func.abs(self))

    def sqrt(self) -> FunctionExpression:
        return FunctionExpression(func.sqrt(self))

    def power(self, exponent) -> FunctionExpression:
        return FunctionExpression(func.power(self, exponent))

    def mod(self, divisor) -> FunctionExpression:
        return FunctionExpression(func.mod(self, divisor))

    def sign(self) -> FunctionExpression:
        return FunctionExpression(func.sign(self))

    def trunc(self, precision: int = 0) -> FunctionExpression:
        return FunctionExpression(func.trunc(self, precision))

    def exp(self) -> FunctionExpression:
        return FunctionExpression(func.exp(self))

    def ln(self) -> FunctionExpression:
        return FunctionExpression(func.ln(self))

    def log(self, base: int = 10) -> FunctionExpression:
        return FunctionExpression(func.log(self, base))


class NumericComparator(ComparatorMixin, Numeric.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """Numeric type comparator for Float and Decimal types"""

    def abs(self) -> FunctionExpression:
        return FunctionExpression(func.abs(self))

    def round(self, precision=0) -> FunctionExpression:
        return FunctionExpression(func.round(self, precision))

    def ceil(self) -> FunctionExpression:
        return FunctionExpression(func.ceil(self))

    def floor(self) -> FunctionExpression:
        return FunctionExpression(func.floor(self))

    def sqrt(self) -> FunctionExpression:
        return FunctionExpression(func.sqrt(self))

    def power(self, exponent) -> FunctionExpression:
        return FunctionExpression(func.power(self, exponent))

    def mod(self, divisor) -> FunctionExpression:
        return FunctionExpression(func.mod(self, divisor))

    def sign(self) -> FunctionExpression:
        return FunctionExpression(func.sign(self))

    def trunc(self, precision: int = 0) -> FunctionExpression:
        return FunctionExpression(func.trunc(self, precision))

    def exp(self) -> FunctionExpression:
        return FunctionExpression(func.exp(self))

    def ln(self) -> FunctionExpression:
        return FunctionExpression(func.ln(self))

    def log(self, base: int = 10) -> FunctionExpression:
        return FunctionExpression(func.log(self, base))


class DateTimeComparator(ComparatorMixin, DateTime.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """DateTime type comparator with comprehensive date/time functions."""

    def extract(self, field) -> FunctionExpression:
        return FunctionExpression(func.extract(field, self))

    def year(self) -> FunctionExpression:
        return FunctionExpression(func.extract("year", self))

    def month(self) -> FunctionExpression:
        return FunctionExpression(func.extract("month", self))

    def day(self) -> FunctionExpression:
        return FunctionExpression(func.extract("day", self))

    def hour(self) -> FunctionExpression:
        return FunctionExpression(func.extract("hour", self))

    def minute(self) -> FunctionExpression:
        return FunctionExpression(func.extract("minute", self))

    def date_trunc(self, precision) -> FunctionExpression:
        return FunctionExpression(func.date_trunc(precision, self))


class JSONComparator(ComparatorMixin, JSON.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """JSON type comparator with JSON extraction and manipulation methods."""

    def extract_path(self, path) -> FunctionExpression:
        return FunctionExpression(func.json_extract_path(self, path))

    def extract_text(self, path) -> FunctionExpression:
        return FunctionExpression(func.json_extract_path_text(self, path))


class BooleanComparator(ComparatorMixin, Boolean.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """Boolean type comparator with boolean check methods"""

    def is_true(self) -> FunctionExpression:
        return FunctionExpression(self.is_(True))

    def is_false(self) -> FunctionExpression:
        return FunctionExpression(self.is_(False))


class DefaultComparator(ComparatorMixin, TypeEngine.Comparator):  # type: ignore[reportIncompatibleMethodOverride]
    """Default comparator for custom types."""

    pass
