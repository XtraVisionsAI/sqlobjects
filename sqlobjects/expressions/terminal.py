"""Terminal expression implementations for query execution and data extraction."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import and_, select

from .base import QueryExpression


if TYPE_CHECKING:
    from ..queries import QueryBuilder

T = TypeVar("T")


class AllExpression(QueryExpression[list[T]]):
    """Represents a query that returns all matching objects."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class

    async def execute(self) -> list[T]:
        if not self._executor:
            raise RuntimeError("No executor available for all execution")
        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "all", builder=self._builder, model_class=self._model_class)
        return result if isinstance(result, list) else []

    def get_sql(self) -> str:
        query = self._builder.build(self._builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class FirstExpression(QueryExpression[T | None]):
    """Represents a query that returns the first matching object."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class

    async def execute(self) -> T | None:
        if not self._executor:
            raise RuntimeError("No executor available for first execution")
        limited_builder = self._builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)
        return result[0] if isinstance(result, list) and result else None

    def get_sql(self) -> str:
        limited_builder = self._builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class LastExpression(QueryExpression[T | None]):
    """Represents a query that returns the last matching object."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class

    async def execute(self) -> T | None:
        if not self._executor:
            raise RuntimeError("No executor available for last execution")
        reversed_builder = self._builder.set_reversed()
        limited_builder = reversed_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)
        return result[0] if isinstance(result, list) and result else None

    def get_sql(self) -> str:
        reversed_builder = self._builder.set_reversed()
        limited_builder = reversed_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class EarliestExpression(QueryExpression[T | None]):
    """Represents a query that returns the earliest object by specified fields."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], fields: tuple[str, ...], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class
        self._fields = fields

    async def execute(self) -> T | None:
        if not self._executor:
            raise RuntimeError("No executor available for earliest execution")
        order_fields = [field.lstrip("-") for field in self._fields]
        ordered_builder = self._builder.add_ordering(*order_fields)
        limited_builder = ordered_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)
        return result[0] if isinstance(result, list) and result else None

    def get_sql(self) -> str:
        order_fields = [field.lstrip("-") for field in self._fields]
        ordered_builder = self._builder.add_ordering(*order_fields)
        limited_builder = ordered_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class LatestExpression(QueryExpression[T | None]):
    """Represents a query that returns the latest object by specified fields."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], fields: tuple[str, ...], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class
        self._fields = fields

    async def execute(self) -> T | None:
        if not self._executor:
            raise RuntimeError("No executor available for latest execution")
        order_fields = [f"-{field.lstrip('-')}" for field in self._fields]
        ordered_builder = self._builder.add_ordering(*order_fields)
        limited_builder = ordered_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)
        return result[0] if isinstance(result, list) and result else None

    def get_sql(self) -> str:
        order_fields = [f"-{field.lstrip('-')}" for field in self._fields]
        ordered_builder = self._builder.add_ordering(*order_fields)
        limited_builder = ordered_builder.add_limit(1)
        query = limited_builder.build(limited_builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class ValuesExpression(QueryExpression[list[dict[str, Any]]]):
    """Represents a query that returns field values as dictionaries."""

    def __init__(self, builder: "QueryBuilder", fields: tuple[str, ...], executor=None):
        super().__init__(executor)
        self._builder = builder
        self._fields = fields

    async def execute(self) -> list[dict[str, Any]]:
        if not self._executor:
            raise RuntimeError("No executor available for values execution")
        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "values", fields=self._fields)
        if isinstance(result, list):
            return [dict(zip(self._fields, row, strict=False)) for row in result]
        return []

    def get_sql(self) -> str:
        table = self._builder.model_class.get_table()
        columns = [table.c[field] for field in self._fields if field in table.c]
        query = select(*columns).select_from(table)
        if hasattr(self._builder, "conditions") and self._builder.conditions:
            query = query.where(and_(*self._builder.conditions))
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class ValuesListExpression(QueryExpression[list[Any] | list[tuple[Any, ...]]]):
    """Represents a query that returns field values as tuples or flat list."""

    def __init__(self, builder: "QueryBuilder", fields: tuple[str, ...], flat: bool = False, executor=None):
        super().__init__(executor)
        self._builder = builder
        self._fields = fields
        self._flat = flat

    async def execute(self) -> list[Any] | list[tuple[Any, ...]]:
        if not self._executor:
            raise RuntimeError("No executor available for values_list execution")
        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "values_list", fields=list(self._fields))
        if isinstance(result, list):
            if self._flat and len(self._fields) == 1:
                return [row[0] for row in result]
            return [tuple(row) for row in result]
        return []

    def get_sql(self) -> str:
        query = self._builder.build(self._builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))


class DatesExpression(QueryExpression[list[date]]):
    """Represents a query that returns unique dates for a field."""

    def __init__(self, builder: "QueryBuilder", field: str, kind: str, order: str = "ASC", executor=None):
        super().__init__(executor)
        self._builder = builder
        self._field = field
        self._kind = kind
        self._order = order

    async def execute(self) -> list[date]:
        if not self._executor:
            raise RuntimeError("No executor available for dates execution")
        # Implementation would be similar to current dates method
        return []

    def get_sql(self) -> str:
        return f"-- Dates query for {self._field} with {self._kind} precision"


class DatetimesExpression(QueryExpression[list[datetime]]):
    """Represents a query that returns unique datetimes for a field."""

    def __init__(self, builder: "QueryBuilder", field: str, kind: str, order: str = "ASC", executor=None):
        super().__init__(executor)
        self._builder = builder
        self._field = field
        self._kind = kind
        self._order = order

    async def execute(self) -> list[datetime]:
        if not self._executor:
            raise RuntimeError("No executor available for datetimes execution")
        # Implementation would be similar to current datetimes method
        return []

    def get_sql(self) -> str:
        return f"-- Datetimes query for {self._field} with {self._kind} precision"


class GetItemExpression(QueryExpression[T | list[T]]):
    """Represents a query that returns item by index or slice."""

    def __init__(self, builder: "QueryBuilder", model_class: type[T], key: Any, executor=None):
        super().__init__(executor)
        self._builder = builder
        self._model_class = model_class
        self._key = key

    async def execute(self) -> T | list[T]:
        if not self._executor:
            raise RuntimeError("No executor available for get_item execution")

        if isinstance(self._key, slice):
            start = self._key.start or 0
            stop = self._key.stop
            if stop is not None:
                limited_builder = self._builder.add_offset(start).add_limit(stop - start)
            else:
                limited_builder = self._builder.add_offset(start)

            query = limited_builder.build(limited_builder.model_class.get_table())
            result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)
            return result if isinstance(result, list) else []
        elif isinstance(self._key, int):
            if self._key < 0:
                raise ValueError("Negative indexing is not supported")

            limited_builder = self._builder.add_offset(self._key).add_limit(1)
            query = limited_builder.build(limited_builder.model_class.get_table())
            result = await self._executor.execute(query, "all", builder=limited_builder, model_class=self._model_class)

            if isinstance(result, list) and result:
                return result[0]
            raise IndexError("Index out of range")
        else:
            raise TypeError("Invalid key type for indexing")

    def get_sql(self) -> str:
        if isinstance(self._key, slice):
            start = self._key.start or 0
            stop = self._key.stop
            if stop is not None:
                limited_builder = self._builder.add_offset(start).add_limit(stop - start)
            else:
                limited_builder = self._builder.add_offset(start)
        elif isinstance(self._key, int):
            limited_builder = self._builder.add_offset(self._key).add_limit(1)
        else:
            return "-- Invalid key type for indexing"

        query = limited_builder.build(limited_builder.model_class.get_table())
        return str(query.compile(compile_kwargs={"literal_binds": True}))
