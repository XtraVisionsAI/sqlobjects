"""SQLObjects Queries Module - Query Building System

This module provides the core query building system for SQLObjects, focusing on
Q objects for logical combination of SQLAlchemy expressions and QuerySet for
chainable query operations.
"""

from collections.abc import AsyncGenerator, Sequence
from typing import Any, Generic, TypeVar, Union

from session import SessionContextManager
from sqlalchemy import and_, asc, delete, desc, func, literal, not_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, defer, joinedload, selectinload
from sqlalchemy.sql import ColumnElement, Select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement

from .exceptions import DoesNotExist, MultipleObjectsReturned
from .expressions import SubqueryExpression
from .signals import Operation, SignalContext, emit_signals


# Export classes for use in other modules
__all__ = ["Q", "QuerySet", "QueryType", "T"]

# Type variables for generic support
T = TypeVar("T", bound=DeclarativeBase)

# Supported expression types for Q object combinations
QueryType = Union[
    "Q",
    ColumnElement,
    BinaryExpression,
    ClauseElement,
    Any,  # For FunctionResult and other SQLObjects expressions
]


class Q:
    """Q object for logical combination of SQLAlchemy expressions.

    Focuses on combining SQLAlchemy expressions using logical operators (AND, OR, NOT).
    Supports both single and multiple expressions with automatic AND combination.

    Examples:
        # Single expression
        Q(User.age >= 18)

        # Multiple expressions (AND combination)
        Q(User.age >= 18, User.is_active == True)

        # Logical combinations
        Q(User.name == "John") | Q(User.name == "Jane")
        Q(User.age >= 18) & Q(User.is_active == True)
        ~Q(User.is_deleted == True)

        # Mixed with SQLAlchemy expressions
        Q(User.name == "John") & (User.age > 25)
    """

    def __init__(self, *expressions: Any):
        """Initialize Q object with SQLAlchemy expressions.

        Args:
            *expressions: SQLAlchemy expressions to combine with AND logic
        """
        self.expressions = list(expressions)
        self.connector = "AND"
        self.negated = False
        self.children: list[Q] = []

    def __and__(self, other: QueryType) -> "Q":
        """Combine with another expression using AND logic.

        Args:
            other: Another Q object or SQLAlchemy expression

        Returns:
            New Q object representing the AND combination

        Raises:
            ArgumentError: If SQLAlchemy expression is on left side with Q object
        """
        new_q = Q()
        new_q.connector = "AND"

        if isinstance(other, Q):
            new_q.children = [self, other]
        else:
            # Q object must be on left side for SQLAlchemy expression combinations
            new_q.children = [self]
            new_q.expressions = [other]

        return new_q

    def __or__(self, other: QueryType) -> "Q":
        """Combine with another expression using OR logic.

        Args:
            other: Another Q object or SQLAlchemy expression

        Returns:
            New Q object representing the OR combination
        """
        new_q = Q()
        new_q.connector = "OR"

        if isinstance(other, Q):
            new_q.children = [self, other]
        else:
            new_q.children = [self]
            new_q.expressions = [other]

        return new_q

    def __invert__(self) -> "Q":
        """Negate this Q object using NOT logic.

        Returns:
            New Q object representing the negated condition
        """
        new_q = Q(*self.expressions)
        new_q.connector = self.connector
        new_q.negated = not self.negated
        new_q.children = self.children.copy()
        return new_q

    def _to_sqlalchemy(self, model_class: type) -> Any:
        """Convert Q object to SQLAlchemy condition expression.

        Args:
            model_class: The model class for expression resolution

        Returns:
            SQLAlchemy condition expression
        """
        conditions = []

        # Handle child Q objects
        if self.children:
            child_conditions = [child._to_sqlalchemy(model_class) for child in self.children]
            conditions.extend(child_conditions)

        # Handle direct expressions
        if self.expressions:
            for expr in self.expressions:
                if hasattr(expr, "resolve"):
                    # Resolve SQLObjects expressions
                    conditions.append(expr.resolve(model_class))
                else:
                    # Direct SQLAlchemy expressions
                    conditions.append(expr)

        # Combine conditions based on connector
        if len(conditions) == 0:
            # No conditions, return a true condition
            condition = literal(True)
        elif len(conditions) == 1:
            condition = conditions[0]
        else:
            if self.connector == "AND":
                condition = and_(*conditions)
            else:  # OR
                condition = or_(*conditions)

        return not_(condition) if self.negated else condition


class QuerySet(Generic[T]):
    """Query set class providing chainable query interface.

    Implements a Django-style ORM interface with method chaining for
    complex query construction and execution. All methods support
    unified session parameter handling for multi-database environments.
    """

    def __init__(
        self, model: type[T], query: Select | None = None, db_or_session: str | AsyncSession | None = None
    ) -> None:
        """Initialize a new QuerySet instance.

        Args:
            model: Model class this QuerySet operates on
            query: Optional existing SQLAlchemy Select query to build upon
            db_or_session: Database name or session for executing queries
        """
        self._db_or_session = db_or_session
        self._model = model
        self._query = query if query is not None else select(model)

    @property
    def _session(self) -> AsyncSession:
        """获取有效的会话对象"""
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session

    # ========================================
    # 查询构建方法 (Query Building Methods)
    # ========================================

    def _process_conditions(self, conditions) -> list[Any]:
        """Process conditions into SQLAlchemy expressions.

        Unified condition processing logic to reduce code duplication between
        filter and exclude methods.

        Args:
            conditions: Sequence of Q objects, SQLObjects expressions, or SQLAlchemy expressions

        Returns:
            List of processed SQLAlchemy condition expressions
        """
        condition_list = []
        for condition in conditions:
            if isinstance(condition, Q):
                # Convert Q object to SQLAlchemy expression
                condition_list.append(condition._to_sqlalchemy(self._model))  # noqa
            elif hasattr(condition, "resolve"):
                # Handle SubqueryExpression and other SQLObjects expressions
                condition_list.append(condition.resolve(self._model))
            else:
                # Direct SQLAlchemy expressions
                condition_list.append(condition)
        return condition_list

    def _clone(self, query=None) -> "QuerySet[T]":
        """Create a QuerySet copy with optional parameter overrides.

        Helper method to improve code reusability across QuerySet methods.

        Args:
           query:  Optional SQLAlchemy Select query to build upon

        Returns:
            New QuerySet instance
        """
        return QuerySet(self._model, query, self._session)

    def filter(self, *conditions) -> "QuerySet[T]":
        """Filter the QuerySet to include only objects matching the given conditions.

        Args:
            *conditions: Q objects or SQLAlchemy expressions

        Returns:
            New QuerySet instance with the filter conditions applied
        """

        condition_list = self._process_conditions(conditions)

        if condition_list:
            new_query = self._query.where(and_(*condition_list))
            return self._clone(query=new_query)
        return self._clone()

    def exclude(self, *conditions) -> "QuerySet[T]":
        """Exclude objects matching the given conditions from the QuerySet.

        Args:
            *conditions: Q objects or SQLAlchemy expressions

        Returns:
            New QuerySet instance with the exclusion conditions applied
        """

        condition_list = [not_(cond) for cond in self._process_conditions(conditions)]

        if condition_list:
            new_query = self._query.where(and_(*condition_list))
            return self._clone(query=new_query)
        return self._clone()

    def order_by(self, *fields) -> "QuerySet[T]":
        """Order the QuerySet results by the specified fields.

        Args:
            *fields: Field names (strings) or SQLAlchemy expressions
                    Use '-' prefix for descending order with string fields

        Returns:
            New QuerySet instance with the ordering applied
        """
        order_clauses = []
        for field in fields:
            if isinstance(field, str):
                # Django-style string field
                if field.startswith("-"):
                    order_clauses.append(desc(getattr(self._model, field[1:])))
                else:
                    order_clauses.append(asc(getattr(self._model, field)))
            elif hasattr(field, "resolve"):
                # SQLObjects expressions
                order_clauses.append(field.resolve(self._model))
            else:
                # SQLAlchemy expressions
                order_clauses.append(field)

        new_query = self._query.order_by(*order_clauses)
        return self._clone(query=new_query)

    def limit(self, count: int) -> "QuerySet[T]":
        """Limit the number of results returned by the QuerySet.

        Args:
            count: Maximum number of results to return

        Returns:
            New QuerySet instance with the limit applied
        """
        new_query = self._query.limit(count)
        return self._clone(query=new_query)

    def offset(self, count: int) -> "QuerySet[T]":
        """Skip the specified number of results from the beginning.

        Args:
            count: Number of results to skip

        Returns:
            New QuerySet instance with the offset applied
        """
        new_query = self._query.offset(count)
        return self._clone(query=new_query)

    def select_related(self, *relations) -> "QuerySet[T]":
        """Preload related objects using JOIN operations.

        Args:
            *relations: Relationship names to preload

        Returns:
            New QuerySet instance with the related objects preloaded
        """
        options = []
        for relation in relations:
            if relation:
                options.append(joinedload(getattr(self._model, relation)))

        new_query = self._query.options(*options)
        return self._clone(query=new_query)

    def prefetch_related(self, *relations) -> "QuerySet[T]":
        """Prefetch related objects using separate queries.

        Args:
            *relations: Relationship names to prefetch

        Returns:
            New QuerySet instance with the related objects prefetched
        """
        options = [selectinload(relation) for relation in relations]
        new_query = self._query.options(*options)
        return self._clone(query=new_query)

    def distinct(self, *fields) -> "QuerySet[T]":
        """Apply DISTINCT clause to eliminate duplicate rows.

        Args:
            *fields: Field names to apply DISTINCT on, if empty applies to all

        Returns:
            New QuerySet with DISTINCT applied
        """
        if fields:
            columns = [getattr(self._model, field) for field in fields]
            new_query = self._query.distinct(*columns)
        else:
            new_query = self._query.distinct()
        return self._clone(query=new_query)

    def only(self, *fields) -> "QuerySet[T]":
        """Load only the specified fields from the database.

        Args:
            *fields: Field names to load

        Returns:
            New QuerySet that loads only the specified fields
        """
        columns = [getattr(self._model, field) for field in fields]
        new_query = select(*columns)
        if self._query.whereclause is not None:
            new_query = new_query.where(self._query.whereclause)

        return self._clone(query=new_query)

    def defer(self, *fields) -> "QuerySet[T]":
        """Defer loading of the specified fields until they are accessed.

        Args:
            *fields: Field names to defer loading

        Returns:
            New QuerySet with deferred field loading
        """
        options = [defer(getattr(self._model, field)) for field in fields]
        new_query = self._query.options(*options)
        return self._clone(query=new_query)

    def annotate(self, **kwargs) -> "QuerySet[T]":
        """Add annotation fields to the queryset.

        Args:
            **kwargs: Annotation expressions with their aliases

        Returns:
            New QuerySet with annotation fields added
        """
        annotations = []
        for alias, expr in kwargs.items():
            if hasattr(expr, "resolve"):
                # SubqueryExpression, or aggregate function
                annotations.append(expr.resolve(self._model).label(alias))
            else:
                annotations.append(expr.label(alias))

        new_query = self._query.add_columns(*annotations)
        return self._clone(query=new_query)

    def group_by(self, *fields) -> "QuerySet[T]":
        """Add GROUP BY clause.

        Args:
            *fields: Field names or SQLAlchemy expressions to group by

        Returns:
            QuerySet with group by applied
        """
        group_columns = []
        for field in fields:
            if isinstance(field, str):
                group_columns.append(getattr(self._model, field))
            elif hasattr(field, "resolve"):
                group_columns.append(field.resolve(self._model))
            else:
                group_columns.append(field)

        new_query = self._query.group_by(*group_columns)
        return self._clone(query=new_query)

    def having(self, *conditions) -> "QuerySet[T]":
        """Add HAVING clause for aggregated queries.

        Args:
            *conditions: SQLAlchemy expressions for having clause

        Returns:
            QuerySet with having conditions applied
        """
        having_conditions = []
        for condition in conditions:
            if hasattr(condition, "resolve"):
                having_conditions.append(condition.resolve(self._model))
            else:
                having_conditions.append(condition)

        new_query = self._query.having(and_(*having_conditions))
        return self._clone(query=new_query)

    def options(self, *options) -> "QuerySet[T]":
        """Add SQLAlchemy query options.

        Args:
            *options: SQLAlchemy query options

        Returns:
            QuerySet with options applied
        """
        new_query = self._query.options(*options)
        return self._clone(query=new_query)

    def join(
        self,
        target_model: type[DeclarativeBase],
        on_condition: Any | None = None,
        join_type: str = "inner",
        isouter: bool = False,
    ) -> "QuerySet[T]":
        """Perform manual JOIN with another model.

        Args:
            target_model: Model class to join with
            on_condition: Join condition, if None uses foreign key relationship
            join_type: Type of join ('inner' or 'left')
            isouter: Whether to use outer join

        Returns:
            New QuerySet with the join applied
        """
        if isouter or join_type == "left":
            if on_condition is None:
                new_query = self._query.outerjoin(target_model)
            else:
                new_query = self._query.outerjoin(target_model, on_condition)
        else:  # inner join
            if on_condition is None:
                new_query = self._query.join(target_model)
            else:
                new_query = self._query.join(target_model, on_condition)

        return self._clone(query=new_query)

    def select_for_update(self, nowait: bool = False, skip_locked: bool = False) -> "QuerySet[T]":
        """Apply row-level locking to the query using FOR UPDATE.

        Args:
            nowait: If True, don't wait for locks and return error immediately
            skip_locked: If True, skip rows that are already locked

        Returns:
            New QuerySet instance with FOR UPDATE locking applied
        """
        if nowait:
            new_query = self._query.with_for_update(nowait=True)
        elif skip_locked:
            new_query = self._query.with_for_update(skip_locked=True)
        else:
            new_query = self._query.with_for_update()

        return self._clone(query=new_query)

    def none(self) -> "QuerySet[T]":
        """Return an empty queryset that will never match any objects.

        Returns:
            New QuerySet that returns no results
        """
        new_query = self._query.where(literal(False))
        return self._clone(query=new_query)

    def reverse(self) -> "QuerySet[T]":
        """Reverse the ordering of the queryset.

        Returns:
            New QuerySet with reversed ordering
        """
        # Simple implementation: reverse by id field
        new_query = self._query.order_by(desc(getattr(self._model, "id", literal(1))))
        return self._clone(query=new_query)

    # ========================================
    # 查询执行方法 (Query Execution Methods)
    # ========================================

    async def all(self) -> list[T]:
        """Execute the query and return all matching objects as a list.

        Returns:
            List of all model instances matching the QuerySet conditions
        """

        result = await self._session.execute(self._query)
        return list(result.scalars())

    async def get(self, *conditions) -> T:
        """Get a single object matching the given conditions.

        Args:
            *conditions: Q objects or SQLAlchemy expressions

        Returns:
            Single model instance

        Raises:
            DoesNotExist: If no object matches the conditions
            MultipleObjectsReturned: If multiple objects match the conditions
        """

        results = await self.filter(*conditions).limit(2).all()
        if not results:
            raise DoesNotExist(f"{self._model.__name__} matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model.__name__} objects returned")
        return results[0]

    async def first(self) -> T | None:
        """Get the first object matching the QuerySet conditions.

        Returns:
            First model instance matching the conditions, or None if no matches found
        """

        result = await self._session.execute(self._query)
        return result.scalars().first()

    async def last(self) -> T | None:
        """Get the last object matching the QuerySet conditions.

        Returns:
            Last model instance matching the conditions, or None if no matches found
        """

        # Reverse the query to get the last item
        reversed_query = self._query.order_by(desc(getattr(self._model, "id", literal(1)))).limit(1)
        result = await self._session.execute(reversed_query)
        return result.scalars().first()

    async def earliest(self, *fields) -> T | None:
        """Get the earliest object based on the specified fields.

        Args:
            *fields: Field names to order by for finding the earliest object

        Returns:
            Earliest model instance, or None if no objects exist
        """
        if not fields:
            fields = ["id"]
        order_clauses = [asc(getattr(self._model, field.lstrip("-"))) for field in fields]
        query = self._query.order_by(*order_clauses).limit(1)

        result = await self._session.execute(query)
        return result.scalars().first()

    async def latest(self, *fields) -> T | None:
        """Get the latest object based on the specified fields.

        Args:
            *fields: Field names to order by for finding the latest object

        Returns:
            Latest model instance, or None if no objects exist
        """
        if not fields:
            fields = ["id"]
        order_clauses = [desc(getattr(self._model, field.lstrip("-"))) for field in fields]
        query = self._query.order_by(*order_clauses).limit(1)

        result = await self._session.execute(query)
        return result.scalars().first()

    async def count(self) -> int:
        """Count the number of objects matching the query conditions.

        Returns:
            Number of matching objects
        """

        count_query = select(func.count()).select_from(self._model)
        if self._query.whereclause is not None:
            count_query = count_query.where(self._query.whereclause)
        result = await self._session.execute(count_query)
        return result.scalar_one()

    async def exists(self) -> bool:
        """Check if any objects match the query conditions.

        Returns:
            True if at least one object matches, False otherwise
        """
        return await self.count() > 0

    async def values(self, *fields) -> list[dict[str, Any]]:
        """Get dictionaries containing only the specified field values.

        Args:
            *fields: Field names to include in the result, will returne all fields if not specified.

        Returns:
            List of dictionaries with field names as keys
        """

        if not fields:
            # Return all fields if none specified
            fields = tuple(col.name for col in self._model.__table__.columns)  # noqa

        columns = [getattr(self._model, field) for field in fields]
        query = select(*columns)
        if self._query.whereclause is not None:
            query = query.where(self._query.whereclause)

        result = await self._session.execute(query)
        results = result.all()
        return [dict(zip(fields, row, strict=False)) for row in results]

    async def values_list(self, *fields, flat: bool = False) -> list[Any] | list[tuple[Any, ...]]:
        """Get list of tuples or single values for the specified fields.

        Args:
            *fields: Field names to include
            flat: If True and only one field specified, return flat list of values

        Returns:
            List of tuples (or flat list if flat=True and single field)
        """
        if not fields:
            raise ValueError("values_list() requires at least one field name")

        columns = [getattr(self._model, field) for field in fields]
        query = select(*columns)
        if self._query.whereclause is not None:
            query = query.where(self._query.whereclause)

        result = await self._session.execute(query)
        results = result.all()

        if flat and len(fields) == 1:
            return [row[0] for row in results]
        return [tuple(row) for row in results]

    async def aggregate(self, **kwargs) -> dict[str, Any]:
        """Perform aggregation operations on the QuerySet.

        Args:
            **kwargs: Aggregation expressions with their result aliases

        Returns:
            Dictionary mapping aggregation aliases to their computed values
        """

        aggregations = []
        labels = []

        for alias, expr in kwargs.items():
            if hasattr(expr, "resolve"):
                # SQLObjects function
                aggregations.append(expr.resolve(self._model).label(alias))
            else:
                aggregations.append(expr.label(alias))
            labels.append(alias)

        query = select(*aggregations).select_from(self._model)
        if self._query.whereclause is not None:
            query = query.where(self._query.whereclause)

        result = await self._session.execute(query)
        first_result = result.first()
        return dict(zip(labels, first_result, strict=False)) if first_result else {}

    async def iterator(self, memory_cleanup_interval: int = 1000) -> AsyncGenerator[T, None]:
        """Async iterator for processing large datasets.

        Args:
            memory_cleanup_interval: Clear session cache every N items

        Yields:
            Model instances one by one
        """

        count = 0

        stream = await self._session.stream_scalars(self._query)
        async for item in stream:
            yield item
            count += 1

            # Periodic memory cleanup
            if count % memory_cleanup_interval == 0:
                self._session.expunge_all()

    async def get_item(self, key) -> T | list[T]:
        """Get items by index or slice.

        Args:
            key: Integer index or slice object

        Returns:
            Single object (for integer key) or list of objects (for slice key)
        """

        if isinstance(key, slice):
            start = key.start or 0
            stop = key.stop
            if stop is not None:
                new_query = self._query.offset(start).limit(stop - start)
                result = await self._session.execute(new_query)
                return list(result.scalars().all())
            else:
                new_query = self._query.offset(start)
                result = await self._session.execute(new_query)
                return list(result.scalars().all())
        elif isinstance(key, int):
            if key < 0:
                raise ValueError("Negative indexing is not supported")
            new_query = self._query.offset(key).limit(1)
            result = await self._session.execute(new_query)
            item = result.scalars().first()
            if item is None:
                raise IndexError("Index out of range")
            return item
        else:
            raise TypeError("Invalid key type for indexing")

    async def dates(self, field: str, kind: str, order: str = "ASC") -> list[Any]:
        """Get unique date list for the specified date field.

        Args:
            field: Date field name
            kind: Date precision ('year', 'month', 'day')
            order: Sort order ('ASC' or 'DESC')

        Returns:
            List of unique dates

        Raises:
            ValueError: If unsupported date kind is specified
        """

        field_obj = getattr(self._model, field)

        # Use SQLAlchemy's dialect-aware date truncation
        try:
            if kind == "year":
                date_expr = func.date_trunc("year", field_obj)
            elif kind == "month":
                date_expr = func.date_trunc("month", field_obj)
            elif kind == "day":
                date_expr = func.date_trunc("day", field_obj)
            else:
                raise ValueError(f"Unsupported date kind: {kind}")
        except Exception:  # noqa
            # Fallback for databases that don't support date_trunc (like SQLite)
            if kind == "year":
                date_expr = func.strftime("%Y-01-01", field_obj)
            elif kind == "month":
                date_expr = func.strftime("%Y-%m-01", field_obj)
            elif kind == "day":
                date_expr = func.date(field_obj)
            else:
                raise ValueError(f"Unsupported date kind: {kind}") from None

        # Build query
        query = select(date_expr.distinct().label("date_value"))
        if self._query.whereclause is not None:
            query = query.where(self._query.whereclause)

        # Add ordering
        if order.upper() == "DESC":
            query = query.order_by(desc("date_value"))
        else:
            query = query.order_by(asc("date_value"))

        result = await self._session.execute(query)
        return [row[0] for row in result]

    async def datetimes(self, field: str, kind: str, order: str = "ASC") -> list[Any]:
        """Get unique datetime list for the specified datetime field.

        Args:
            field: Datetime field name
            kind: Time precision ('year', 'month', 'day', 'hour', 'minute', 'second')
            order: Sort order ('ASC' or 'DESC')

        Returns:
            List of unique datetimes

        Raises:
            ValueError: If unsupported datetime kind is specified
        """

        field_obj = getattr(self._model, field)

        # Use SQLAlchemy's dialect-aware datetime truncation
        try:
            if kind == "year":
                datetime_expr = func.date_trunc("year", field_obj)
            elif kind == "month":
                datetime_expr = func.date_trunc("month", field_obj)
            elif kind == "day":
                datetime_expr = func.date_trunc("day", field_obj)
            elif kind == "hour":
                datetime_expr = func.date_trunc("hour", field_obj)
            elif kind == "minute":
                datetime_expr = func.date_trunc("minute", field_obj)
            elif kind == "second":
                datetime_expr = func.date_trunc("second", field_obj)
            else:
                raise ValueError(f"Unsupported datetime kind: {kind}")
        except Exception:  # noqa
            # Fallback for databases that don't support date_trunc (like SQLite)
            if kind == "year":
                datetime_expr = func.strftime("%Y-01-01 00:00:00", field_obj)
            elif kind == "month":
                datetime_expr = func.strftime("%Y-%m-01 00:00:00", field_obj)
            elif kind == "day":
                datetime_expr = func.strftime("%Y-%m-%d 00:00:00", field_obj)
            elif kind == "hour":
                datetime_expr = func.strftime("%Y-%m-%d %H:00:00", field_obj)
            elif kind == "minute":
                datetime_expr = func.strftime("%Y-%m-%d %H:%M:00", field_obj)
            elif kind == "second":
                datetime_expr = func.strftime("%Y-%m-%d %H:%M:%S", field_obj)
            else:
                raise ValueError(f"Unsupported datetime kind: {kind}") from None

        # Build query
        query = select(datetime_expr.distinct().label("datetime_value"))
        if self._query.whereclause is not None:
            query = query.where(self._query.whereclause)

        # Add ordering
        if order.upper() == "DESC":
            query = query.order_by(desc("datetime_value"))
        else:
            query = query.order_by(asc("datetime_value"))

        result = await self._session.execute(query)
        return [row[0] for row in result]

    async def explain(self, output: str | None = None, analyze: bool = False, **options) -> dict[str, Any]:
        """Get query execution plan using EXPLAIN.

        Args:
            output: Output format ('json' or 'text', defaults to 'text')
            analyze: Whether to actually execute the query for analysis
            **options: Other database-specific options

        Returns:
            Dictionary containing the query execution plan
        """

        # Detect database dialect
        dialect_name = self._session.bind.dialect.name if self._session.bind else "sqlite"

        # Build EXPLAIN query
        explain_prefix = self._build_explain_prefix(output, analyze, dialect_name, **options)

        # Get raw SQL query
        compiled_query = self._query.compile(compile_kwargs={"literal_binds": True})
        sql_query = str(compiled_query)

        # Build complete EXPLAIN query
        explain_query = text(f"{explain_prefix}{sql_query}")

        # Execute EXPLAIN query
        result = await self._session.execute(explain_query)
        raw_result = result.fetchall()

        # Normalize return result
        return self._normalize_explain_result(raw_result, dialect_name, output)

    @staticmethod
    def _build_explain_prefix(output: str | None, analyze: bool, dialect: str, **options) -> str:
        """Build EXPLAIN prefix based on database dialect.

        Args:
            output: Output format preference
            analyze: Whether to include ANALYZE
            dialect: Database dialect name
            **options: Additional database-specific options

        Returns:
            EXPLAIN prefix string for the SQL query
        """
        if dialect == "postgresql":
            explain_options = []
            if analyze:
                explain_options.append("ANALYZE")
            if output and output.upper() == "JSON":
                explain_options.append("FORMAT JSON")
            # Handle additional PostgreSQL options
            if options.get("verbose"):
                explain_options.append("VERBOSE")
            if options.get("costs") is False:
                explain_options.append("COSTS FALSE")
            if options.get("buffers"):
                explain_options.append("BUFFERS")
            return f"EXPLAIN ({', '.join(explain_options)}) " if explain_options else "EXPLAIN "

        elif dialect == "mysql":
            if output and output.upper() == "JSON":
                return "EXPLAIN FORMAT=JSON "
            return "EXPLAIN "

        elif dialect == "sqlite":
            return "EXPLAIN QUERY PLAN "

        else:
            return "EXPLAIN "

    @staticmethod
    def _normalize_explain_result(raw_result: Sequence[Any], dialect: str, output: str | None) -> dict[str, Any]:
        """Normalize EXPLAIN results from different databases into a standard format.

        Args:
            raw_result: Raw result from database EXPLAIN query
            dialect: Database dialect name
            output: Output format used

        Returns:
            Normalized dictionary with query plan information
        """
        # Convert to dictionary list
        if raw_result:
            if hasattr(raw_result[0], "_mapping"):
                query_plan = [dict(row._mapping) for row in raw_result]  # noqa
            else:
                # Handle tuple results
                query_plan = [dict(enumerate(row)) if isinstance(row, tuple) else row for row in raw_result]
        else:
            query_plan = []

        return {
            "dialect": dialect,
            "format": output or "text",
            "query_plan": query_plan,
            "analyze": "ANALYZE" in str(raw_result) if raw_result else False,
        }

    async def raw(self, sql: str, params: dict | None = None) -> list[T]:
        """Execute raw SQL query and return model instances.

        Args:
            sql: Raw SQL query string
            params: Query parameters dictionary

        Returns:
            List of model instances created from query results
        """

        query = text(sql)
        result = await self._session.execute(query, params or {})
        return [self._model(**dict(row._mapping)) for row in result]  # noqa

    # ========================================
    # 集合操作方法 (Set Operations Methods)
    # ========================================

    async def union(self, *other_qs: "QuerySet[T]", all_: bool = False) -> list[T]:
        """Perform union operation on QuerySets.

        Args:
            *other_qs: Other QuerySet instances to union with
            all_: If True, use UNION ALL instead of UNION

        Returns:
            List of unique model instances from all QuerySets
        """
        if not other_qs:
            return await self.all()

        # Simple implementation: get all results and combine in memory
        all_results = []
        seen_ids = set()

        # Process current QuerySet
        for item in await self.all():
            item_id = getattr(item, "id", id(item))
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                all_results.append(item)

        # Process other QuerySets
        for qs in other_qs:
            for item in await qs.all():
                item_id = getattr(item, "id", id(item))
                if all_ or item_id not in seen_ids:
                    if not all_:
                        seen_ids.add(item_id)
                    all_results.append(item)

        return all_results

    async def intersection(self, *other_qs: "QuerySet[T]") -> list[T]:
        """Perform intersection operation on QuerySets.

        Args:
            *other_qs: Other QuerySet instances to intersect with

        Returns:
            List of model instances present in all QuerySets
        """
        if not other_qs:
            return await self.all()

        # Get all objects and IDs from current QuerySet
        self_results = await self.all()
        self_ids = {getattr(item, "id", id(item)) for item in self_results}

        # Progressively intersect with each additional QuerySet
        for qs in other_qs:
            other_results = await qs.all()
            other_ids = {getattr(item, "id", id(item)) for item in other_results}
            self_ids &= other_ids

        # Return objects whose IDs are in the final intersection
        return [item for item in self_results if getattr(item, "id", id(item)) in self_ids]

    async def difference(self, *other_qs: "QuerySet[T]") -> list[T]:
        """Perform difference operation on QuerySets.

        Args:
            *other_qs: Other QuerySet instances to subtract from this QuerySet

        Returns:
            List of model instances in this QuerySet but not in others
        """
        self_results = await self.all()
        if not other_qs:
            return self_results

        # Collect all IDs to exclude from other QuerySets
        exclude_ids = set()
        for qs in other_qs:
            other_results = await qs.all()
            exclude_ids.update(getattr(item, "id", id(item)) for item in other_results)

        # Return objects whose IDs are not in the exclusion set
        return [item for item in self_results if getattr(item, "id", id(item)) not in exclude_ids]

    # ========================================
    # 数据操作方法 (Data Operations Methods)
    # ========================================

    @emit_signals(Operation.UPDATE)
    async def update(self, **values) -> int:
        """Perform bulk update on objects matching the query conditions.

        Args:
            **values: Field values to update

        Returns:
            Number of affected rows
        """
        # Resolve expressions in update values
        resolved_values = {}
        for key, value in values.items():
            if hasattr(value, "resolve"):
                resolved_values[key] = value.resolve(self._model)
            else:
                resolved_values[key] = value

        stmt = update(self._model).values(**resolved_values)
        if self._query.whereclause is not None:
            stmt = stmt.where(self._query.whereclause)

        result = await self._session.execute(stmt)
        affected_count = result.rowcount if result.rowcount is not None else 0

        await self._session.flush()
        return affected_count

    @emit_signals(Operation.DELETE)
    async def delete(self) -> int:
        """Perform bulk delete on objects matching the query conditions.

        Returns:
            Number of deleted rows
        """
        stmt = delete(self._model)
        if self._query.whereclause is not None:
            stmt = stmt.where(self._query.whereclause)

        result = await self._session.execute(stmt)
        affected_count = result.rowcount if result.rowcount is not None else 0

        await self._session.flush()
        return affected_count

    # ========================================
    # 子查询方法 (Subquery Methods)
    # ========================================

    def subquery(self, name: str | None = None, query_type: str = "auto") -> SubqueryExpression:
        """Convert the current QuerySet to a subquery expression with intelligent type inference.

        Args:
            name: Optional alias name for the subquery
            query_type: Type of subquery to create ('auto', 'table', 'scalar', 'exists')
                       'auto' enables intelligent type inference based on query structure

        Returns:
            SubqueryExpression object with automatic type inference and conversion capabilities

        Examples:
            # Automatic inference - scalar subquery for aggregates
            avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()
            older_users = User.objects.filter(User.age > avg_age)

            # Automatic inference - table subquery for multi-column
            active_users = User.objects.filter(is_active=True).subquery("active_users")
            posts = Post.objects.join(active_users, Post.author_id == active_users.c.id)

            # Manual type specification
            exists_subq = Post.objects.filter(author_id=User.id).subquery(query_type="exists")
            users_with_posts = User.objects.filter(exists_subq)
        """
        return SubqueryExpression(self._query, name, query_type)
