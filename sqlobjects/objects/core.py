"""SQLObjects Objects Manager - Core Operations

This module provides the core ObjectsManager functionality including
session management, query building, and single record operations.
"""

from typing import Any, Generic, Literal, overload

from sqlalchemy import insert, text

from ..exceptions import DoesNotExist, MultipleObjectsReturned
from ..queryset import QuerySet, T
from ..session import AsyncSession, get_session
from ..signals import Operation, emit_signals
from .bulk import BulkResult, ConflictResolution, ErrorHandling, TransactionMode


__all__ = ["ObjectsDescriptor", "ObjectsManager"]


class ObjectsDescriptor(Generic[T]):
    """Descriptor that provides Django-style objects attribute for model classes.

    This descriptor is automatically attached to model classes to provide the
    'objects' attribute that returns an ObjectsManager instance for database operations.
    It implements the descriptor protocol to ensure each model class gets its own
    manager instance.
    """

    def __init__(self, model_class: type[T]) -> None:
        """Initialize the descriptor with the model class.

        Args:
            model_class: The model class this descriptor is attached to
        """
        self._model_class = model_class

    def __get__(self, obj: Any, owner: type[T]) -> "ObjectsManager[T]":
        """Return an ObjectsManager instance for the model class.

        This method is called when accessing the 'objects' attribute on a model class.

        Args:
            obj: The instance accessing the attribute (None for class access)
            owner: The class that owns this descriptor

        Returns:
            ObjectsManager instance configured for the model class
        """
        return ObjectsManager(self._model_class)


class ObjectsManager(Generic[T]):
    """Object manager providing Django ORM-like interface using SQLAlchemy Core.

    This manager provides a familiar Django-style API for database operations
    while leveraging SQLAlchemy Core for optimal performance. It supports
    session management, query building, and bulk operations.
    """

    def __init__(self, model_class: type[T], db_or_session: str | AsyncSession | None = None):
        """Initialize the objects manager.

        Args:
            model_class: The model class this manager operates on
            db_or_session: Optional database name or session to use
        """
        self._model_class = model_class
        self._table = model_class.get_table()  # type: ignore[reportAttributeAccessIssue]
        self._db_or_session = db_or_session

    # ========================================
    # 1. Internal Helper Methods
    # ========================================

    def _get_session(self, readonly: bool = True) -> AsyncSession:
        """Get database session with explicit readonly parameter.

        Args:
            readonly: Whether the session is for read-only operations

        Returns:
            AsyncSession instance
        """
        if self._db_or_session is None:
            return get_session(readonly=readonly)
        elif isinstance(self._db_or_session, str):
            return get_session(self._db_or_session, readonly=readonly)
        else:
            return self._db_or_session

    def _validate_field_names(self, **kwargs) -> None:
        """Validate that all field names exist on the model.

        Args:
            **kwargs: Field names to validate

        Raises:
            AttributeError: If any field name doesn't exist on the model
        """
        table_fields = set(self._table.columns.keys())
        for field_name in kwargs.keys():
            if field_name not in table_fields:
                raise AttributeError(f"'{self._model_class.__name__}' has no field '{field_name}'")

    # ========================================
    # 2. Session Management Methods
    # ========================================

    def using(self, db_or_session: str | AsyncSession) -> "ObjectsManager[T]":
        """Create a new manager instance using the specified database or session.

        Args:
            db_or_session: Database name or AsyncSession instance

        Returns:
            New ObjectsManager instance bound to the specified database/session
        """
        return ObjectsManager(self._model_class, db_or_session)

    # ========================================
    # 3. Query Building Methods - Return QuerySet
    # ========================================

    def filter(self, *args) -> QuerySet[T]:
        """Filter objects using Q objects SQLAlchemy expressions and keyword arguments.

        Args:
            *args: Q objects or SQLAlchemy expressions for complex conditions

        Returns:
            QuerySet with filter conditions applied
        """
        return QuerySet(self._table, self._model_class, db_or_session=self._db_or_session).filter(*args)

    def defer(self, *fields) -> QuerySet[T]:
        """Defer loading of specified fields until accessed.

        Args:
            *fields: Field names to defer (supports strings and field expressions)

        Returns:
            QuerySet with deferred fields
        """
        return QuerySet(self._table, self._model_class, db_or_session=self._db_or_session).defer(*fields)

    def undefer(self, *fields) -> QuerySet[T]:
        """Remove specified fields from deferred loading.

        Args:
            *fields: Field names to remove from deferred set

        Returns:
            QuerySet with specified fields no longer deferred
        """
        return QuerySet(self._table, self._model_class, db_or_session=self._db_or_session).undefer(*fields)

    def annotate(self, *args, **kwargs) -> QuerySet[T]:
        """Add annotation fields to the query.

        Args:
            *args: Positional annotation expressions with auto-generated aliases
            **kwargs: Named annotation expressions with custom aliases

        Returns:
            QuerySet with annotation fields added
        """
        return self.filter().annotate(*args, **kwargs)

    def group_by(self, *fields) -> QuerySet[T]:
        """Add GROUP BY clause to the query.

        Args:
            *fields: Field names, field expressions, or SQLAlchemy expressions for grouping

        Returns:
            QuerySet with GROUP BY clause applied
        """
        return self.filter().group_by(*fields)

    def having(self, *conditions) -> QuerySet[T]:
        """Add HAVING clause for grouped queries.

        Args:
            *conditions: SQLAlchemy expressions for HAVING conditions

        Returns:
            QuerySet with HAVING conditions applied
        """
        return self.filter().having(*conditions)

    def join(self, target_table, on_condition, join_type: str = "inner") -> QuerySet[T]:
        """Perform manual JOIN with another table.

        Args:
            target_table: Table to join with
            on_condition: JOIN condition expression
            join_type: Type of join ('inner', 'left', 'outer')

        Returns:
            QuerySet with JOIN applied
        """
        return self.filter().join(target_table, on_condition, join_type)

    def leftjoin(self, target_table, on_condition) -> QuerySet[T]:
        """Perform LEFT JOIN with another table.

        Args:
            target_table: Table to join with
            on_condition: JOIN condition expression

        Returns:
            QuerySet with LEFT JOIN applied
        """
        return self.filter().leftjoin(target_table, on_condition)

    def outerjoin(self, target_table, on_condition) -> QuerySet[T]:
        """Perform OUTER JOIN with another table.

        Args:
            target_table: Table to join with
            on_condition: JOIN condition expression

        Returns:
            QuerySet with OUTER JOIN applied
        """
        return self.filter().outerjoin(target_table, on_condition)

    def select_for_update(self, nowait: bool = False, skip_locked: bool = False) -> QuerySet[T]:
        """Apply row-level locking using FOR UPDATE.

        Args:
            nowait: Don't wait if rows are locked by another transaction
            skip_locked: Skip locked rows instead of waiting

        Returns:
            QuerySet with FOR UPDATE locking applied
        """
        return self.filter().select_for_update(nowait, skip_locked)

    def select_for_share(self, nowait: bool = False, skip_locked: bool = False) -> QuerySet[T]:
        """Apply shared row-level locking using FOR SHARE.

        Args:
            nowait: Don't wait if rows are locked by another transaction
            skip_locked: Skip locked rows instead of waiting

        Returns:
            QuerySet with FOR SHARE locking applied
        """
        return self.filter().select_for_share(nowait, skip_locked)

    def extra(self, columns=None, where=None, params=None) -> QuerySet[T]:
        """Add extra SQL fragments to the query.

        Args:
            columns: Extra columns to add to SELECT clause
            where: Extra WHERE conditions as raw SQL strings
            params: Parameters for extra SQL fragments

        Returns:
            QuerySet with extra SQL fragments added
        """
        return self.filter().extra(columns, where, params)

    def skip_default_ordering(self) -> QuerySet[T]:
        """Return QuerySet that skips applying default ordering.

        Returns:
            QuerySet without default ordering applied
        """
        return self.filter().skip_default_ordering()

    def subquery(self, name: str | None = None, query_type: str = "auto"):
        """Convert current QuerySet to subquery expression.

        Args:
            name: Optional name for the subquery
            query_type: Type of subquery ('auto', 'table', 'scalar', 'exists')

        Returns:
            SubqueryExpression that can be used in other queries
        """
        return self.filter().subquery(name, query_type)  # type: ignore[reportArgumentType]

    # ========================================
    # 4. Query Execution Methods - Execute queries and return results
    # ========================================

    # Basic execution methods

    def all(self):
        """Create all expression that can be executed or used as subquery.

        Returns:
            AllExpression that can be awaited or used in comparisons
        """
        return self.filter().all()

    async def get(self, *args) -> T:
        """Get a single object matching the given conditions.

        Args:
            *args: Q objects or SQLAlchemy expressions for complex conditions

        Returns:
            Single model instance

        Raises:
            DoesNotExist: If no object matches the conditions
            MultipleObjectsReturned: If multiple objects match the conditions
        """
        results = await self.filter(*args).limit(2).all()
        if not results:
            raise DoesNotExist(f"{self._model_class.__name__} matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model_class.__name__} objects returned")
        return results[0]

    def exists(self):
        """Create exists expression that can be executed or used in filters.

        Returns:
            ExistsExpression that can be awaited or used in WHERE clauses
        """
        return self.filter().exists()

    async def raw(self, sql: str, params: dict | None = None) -> list[T]:
        """Execute raw SQL query and return model instances.

        Args:
            sql: Raw SQL query string
            params: Optional parameters for the SQL query

        Returns:
            List of model instances created from query results
        """
        return await self.filter().raw(sql, params)

    def first(self):
        """Create first expression that can be executed or used as subquery.

        Returns:
            FirstExpression that can be awaited or used in comparisons
        """
        return self.filter().first()

    def last(self):
        """Create last expression that can be executed or used as subquery.

        Returns:
            LastExpression that can be awaited or used in comparisons
        """
        return self.filter().last()

    # Ordering-related execution methods

    def earliest(self, *fields):
        """Create earliest expression that can be executed or used as subquery.

        Returns:
            EarliestExpression that can be awaited or used in comparisons
        """
        if not fields:
            fields = ["id"]
        return self.filter().earliest(*fields)

    def latest(self, *fields):
        """Create latest expression that can be executed or used as subquery.

        Returns:
            LatestExpression that can be awaited or used in comparisons
        """
        if not fields:
            fields = ["id"]
        return self.filter().latest(*fields)

    # Data extraction methods

    def values(self, *fields):
        """Create values expression that can be executed or used as subquery.

        Returns:
            ValuesExpression that can be awaited or used in comparisons
        """
        return self.filter().values(*fields)

    def values_list(self, *fields, flat: bool = False):
        """Create values_list expression that can be executed or used as subquery.

        Returns:
            ValuesListExpression that can be awaited or used in comparisons
        """
        return self.filter().values_list(*fields, flat=flat)

    def dates(self, field, kind: str, order: str = "ASC"):
        """Create dates expression that can be executed or used as subquery.

        Returns:
            DatesExpression that can be awaited or used in comparisons
        """
        return self.filter().dates(field, kind, order)

    def datetimes(self, field, kind: str, order: str = "ASC"):
        """Create datetimes expression that can be executed or used as subquery.

        Returns:
            DatetimesExpression that can be awaited or used in comparisons
        """
        return self.filter().datetimes(field, kind, order)

    # Advanced execution methods

    async def iterator(self, chunk_size: int = 1000):
        """Async iterator for large datasets.

        Args:
            chunk_size: Number of objects to fetch per chunk

        Yields:
            Model instances one by one
        """
        async for obj in self.filter().iterator(chunk_size):
            yield obj

    def get_item(self, key):
        """Create get_item expression that can be executed or used as subquery.

        Returns:
            GetItemExpression that can be awaited or used in comparisons
        """
        return self.filter().get_item(key)

    # ========================================
    # 5. Data Operations Methods - Create and modify data
    # ========================================

    # Creation operations

    async def get_or_create(
        self, defaults: dict[str, Any] | None = None, validate: bool = True, **lookup
    ) -> tuple[T, bool]:
        """Get an existing object or create a new one if it doesn't exist.

        Args:
            defaults: Additional values to use when creating a new object
            validate: Whether to validate when creating
            **lookup: Field lookup conditions (only equality supported)

        Returns:
            Tuple of (object, created) where created is True if object was created
        """
        if not lookup:
            raise ValueError("get_or_create requires at least one lookup field")

        # Validate field names
        self._validate_field_names(**lookup)
        if defaults:
            self._validate_field_names(**defaults)

        try:
            # Try to get existing object
            conditions = [self._table.c[field] == value for field, value in lookup.items()]
            obj = await self.filter(*conditions).get()
            return obj, False
        except DoesNotExist:
            # Create new object with lookup fields + defaults
            create_data = lookup.copy()
            if defaults:
                # defaults override lookup values if there's conflict
                create_data.update(defaults)

            # Create instance and use save() method to trigger signals
            obj = self._model_class.from_dict(create_data, validate=False)  # type: ignore[reportAttributeAccessIssue]
            await obj.using(self._get_session(readonly=False)).save(validate=validate)
            return obj, True

    async def update_or_create(
        self, defaults: dict[str, Any] | None = None, validate: bool = True, **lookup
    ) -> tuple[T, bool]:
        """Update an existing object or create a new one if it doesn't exist.

        Args:
            defaults: Values to update/set when object exists or is created
            validate: Whether to validate when updating/creating
            **lookup: Field lookup conditions (only equality supported)

        Returns:
            Tuple of (object, created) where created is True if object was created
        """
        if not lookup:
            raise ValueError("update_or_create requires at least one lookup field")

        # Validate field names
        self._validate_field_names(**lookup)
        if defaults:
            self._validate_field_names(**defaults)

        try:
            # Try to get existing object
            conditions = [self._table.c[field] == value for field, value in lookup.items()]
            obj = await self.filter(*conditions).get()

            # Update existing object with defaults using save() method
            if defaults:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                await obj.using(self._get_session(readonly=False)).save(validate=validate)  # type: ignore[reportAttributeAccessIssue]

            return obj, False
        except DoesNotExist:
            # Create new object with lookup fields + defaults
            create_data = lookup.copy()
            if defaults:
                # defaults override lookup values if there's conflict
                create_data.update(defaults)

            # Create instance and use save() method to trigger signals
            obj = self._model_class.from_dict(create_data, validate=False)  # type: ignore[reportAttributeAccessIssue]
            await obj.using(self._get_session(readonly=False)).save(validate=validate)
            return obj, True

    async def in_bulk(self, id_list: list[Any] | None = None, field_name: str = "pk") -> dict[Any, T]:
        """Get multiple objects as a dictionary mapping field values to objects.

        Args:
            id_list: List of values to match against the specified field
            field_name: Name of the field to use as dictionary keys ('pk' for primary key)

        Returns:
            Dictionary mapping field values to model instances
        """
        if field_name == "pk":
            pk_columns = list(self._table.primary_key.columns)
            actual_field = pk_columns[0].name if pk_columns else "id"
        else:
            actual_field = field_name

        queryset = self.filter()
        if id_list is not None:
            field_column = self._table.c[actual_field]
            queryset = queryset.filter(field_column.in_(id_list))

        objects = await queryset.all()
        return {getattr(obj, actual_field): obj for obj in objects}

    @emit_signals(Operation.SAVE)
    async def create(self, validate: bool = True, **kwargs) -> T:
        """Create a new object with the given field values.

        Args:
            validate: Whether to execute all validation
            **kwargs: Field values for the new object

        Returns:
            Created model instance
        """
        try:
            obj = self._model_class.from_dict(kwargs, validate=False)  # type: ignore[reportAttributeAccessIssue]
            # Execute database operation directly, don't call obj.save() to avoid duplicate signals
            if validate:
                obj.validate_all_fields()

            stmt = insert(self._table).values(**obj._get_all_data())  # noqa
            session = self._get_session(readonly=False)
            result = await session.execute(stmt)

            # Set primary key values from result
            if result.inserted_primary_key:
                obj._set_primary_key_values(result.inserted_primary_key)  # noqa

            return obj
        except Exception as e:
            raise RuntimeError(f"Failed to create {self._model_class.__name__}: {e}") from e

    # QuerySet shortcut methods

    def count(self):
        """Create count expression that can be executed or used as subquery.

        Returns:
            CountExpression that can be awaited or used in comparisons
        """
        return self.filter().count()

    def aggregate(self, **kwargs):
        """Create aggregation expression that can be executed or used as subquery.

        Args:
            **kwargs: Aggregation expressions with their aliases

        Returns:
            AggregateExpression that can be awaited or used in comparisons
        """
        return self.filter().aggregate(**kwargs)

    def distinct(self, *fields) -> QuerySet[T]:
        """Apply DISTINCT clause to eliminate duplicate rows.

        Args:
            *fields: Field names, field expressions to apply DISTINCT on, if empty applies to all

        Returns:
            QuerySet with DISTINCT applied
        """
        return self.filter().distinct(*fields)

    def exclude(self, *args) -> QuerySet[T]:
        """Exclude objects matching the given conditions.

        Args:
            *args: Q objects or SQLAlchemy expressions for complex conditions

        Returns:
            QuerySet with exclusion conditions applied
        """
        return self.filter().exclude(*args)

    def order_by(self, *fields) -> QuerySet[T]:
        """Order results by the specified fields.

        Args:
            *fields: Field names, field expressions, or SQLAlchemy expressions
                    (prefix string fields with '-' for descending order)

        Returns:
            QuerySet with ordering applied
        """
        return self.filter().order_by(*fields)

    def limit(self, count: int) -> QuerySet[T]:
        """Limit the number of results.

        Args:
            count: Maximum number of results to return

        Returns:
            QuerySet with limit applied
        """
        return self.filter().limit(count)

    def offset(self, count: int) -> QuerySet[T]:
        """Skip the specified number of results.

        Args:
            count: Number of results to skip

        Returns:
            QuerySet with offset applied
        """
        return self.filter().offset(count)

    def only(self, *fields) -> QuerySet[T]:
        """Load only the specified fields from the database.

        Args:
            *fields: Field names to load (supports strings and field expressions)

        Returns:
            QuerySet that loads only the specified fields
        """
        return self.filter().only(*fields)

    def none(self) -> QuerySet[T]:
        """Return an empty queryset that will never match any objects.

        Returns:
            QuerySet that returns no results
        """
        return self.filter().none()

    def reverse(self) -> QuerySet[T]:
        """Reverse the ordering of the queryset.

        Returns:
            QuerySet with reversed ordering
        """
        return self.filter().reverse()

    def select_related(self, *fields) -> QuerySet[T]:
        """JOIN preload related objects.

        Args:
            *fields: Related field names to preload (supports strings, field expressions, and nested paths)

        Returns:
            QuerySet with related objects preloaded
        """
        return self.filter().select_related(*fields)

    def prefetch_related(self, *fields, **queryset_configs: "QuerySet[Any]") -> QuerySet[T]:
        """Separate query preload related objects with advanced configuration support.

        Args:
            *fields: Simple prefetch field names (supports strings, field expressions, and nested paths)
            **queryset_configs: Advanced prefetch with custom QuerySets for filtering/ordering

        Returns:
            QuerySet with related objects prefetched
        """
        return self.filter().prefetch_related(*fields, **queryset_configs)

    # ========================================
    # 6. Bulk Operations - Delegate to bulk module
    # ========================================

    # Overloads for bulk_create to provide precise type hints
    @overload
    async def bulk_create(
        self,
        objects: list[dict[str, Any]],
        batch_size: int = 1000,
        return_objects: Literal[False] = False,
        return_fields: list[str] | None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> int: ...

    @overload
    async def bulk_create(
        self,
        objects: list[dict[str, Any]],
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> BulkResult[T]: ...

    @overload
    async def bulk_create(
        self,
        objects: list[dict[str, Any]],
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: list[str] = ...,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> BulkResult[dict[str, Any]]: ...

    @emit_signals(Operation.SAVE, is_bulk=True)
    async def bulk_create(
        self,
        objects: list[dict[str, Any]],
        batch_size: int = 1000,
        return_objects: bool = False,
        return_fields: list[str] | None = None,
        # Transaction control parameters
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> int | BulkResult[T] | BulkResult[dict[str, Any]]:
        """Create multiple objects for better performance.

        Args:
            objects: List of dictionaries containing object data
            batch_size: Number of records to process in each batch
            return_objects: Whether to return created objects with detailed statistics
            return_fields: Specific fields to return in objects (for memory optimization)
                          If None, returns full objects. If specified, only loads these fields.
            transaction_mode: Transaction control mode
            on_error: Error handling strategy
            on_conflict: Conflict resolution strategy
            conflict_fields: Fields to check for conflicts

        Returns:
            - int: Number of created records (when return_objects=False)
            - BulkResult[T]: Detailed result with objects and statistics (when return_objects=True)
        """
        from .bulk import bulk_create

        return await bulk_create(  # type: ignore[reportReturnType]
            self,
            objects,
            batch_size,
            return_objects,
            return_fields,
            transaction_mode,
            on_error,
            on_conflict,
            conflict_fields,
        )

    # Overloads for bulk_update to provide precise type hints
    @overload
    async def bulk_update(
        self,
        mappings: list[dict[str, Any]],
        match_fields: list[str] | None = None,
        batch_size: int = 1000,
        return_objects: Literal[False] = False,
        return_fields: list[str] | None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> int: ...

    @overload
    async def bulk_update(
        self,
        mappings: list[dict[str, Any]],
        match_fields: list[str] | None = None,
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> BulkResult[T]: ...

    @overload
    async def bulk_update(
        self,
        mappings: list[dict[str, Any]],
        match_fields: list[str] | None = None,
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: list[str] = ...,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> BulkResult[dict[str, Any]]: ...

    @emit_signals(Operation.SAVE, is_bulk=True)
    async def bulk_update(
        self,
        mappings: list[dict[str, Any]],
        match_fields: list[str] | None = None,
        batch_size: int = 1000,
        return_objects: bool = False,
        return_fields: list[str] | None = None,
        # Transaction control parameters
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
        on_conflict: "ConflictResolution" = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
    ) -> int | BulkResult[T] | BulkResult[dict[str, Any]]:
        """Perform true bulk update operations for better performance.

        Args:
            mappings: List of dictionaries containing match fields and update values
            match_fields: Fields to use for matching records (defaults to ["id"])
            batch_size: Number of records to process in each batch
            return_objects: Whether to return updated objects
            return_fields: Specific fields to return (requires return_objects=True)
            transaction_mode: Transaction control mode
            on_error: Error handling strategy
            on_conflict: Conflict resolution strategy
            conflict_fields: Fields to check for conflicts

        Returns:
            - int: Number of updated records (when return_objects=False)
            - BulkResult[T]: Detailed result with objects and statistics (when return_objects=True)
        """
        from .bulk import bulk_update

        return await bulk_update(  # type: ignore[reportReturnType]
            self,
            mappings,
            match_fields,
            batch_size,
            return_objects,
            return_fields,
            transaction_mode,
            on_error,
            on_conflict,
            conflict_fields,
        )

    # Overloads for bulk_delete to provide precise type hints
    @overload
    async def bulk_delete(
        self,
        ids: list[Any],
        id_field: str = "id",
        batch_size: int = 1000,
        return_objects: Literal[False] = False,
        return_fields: list[str] | None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    ) -> int: ...

    @overload
    async def bulk_delete(
        self,
        ids: list[Any],
        id_field: str = "id",
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: None = None,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    ) -> BulkResult[T]: ...

    @overload
    async def bulk_delete(
        self,
        ids: list[Any],
        id_field: str = "id",
        batch_size: int = 1000,
        return_objects: Literal[True] = ...,
        return_fields: list[str] = ...,
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    ) -> BulkResult[dict[str, Any]]: ...

    @emit_signals(Operation.DELETE, is_bulk=True)
    async def bulk_delete(
        self,
        ids: list[Any],
        id_field: str = "id",
        batch_size: int = 1000,
        return_objects: bool = False,
        return_fields: list[str] | None = None,
        # Transaction control parameters
        transaction_mode: TransactionMode = TransactionMode.INHERIT,
        on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    ) -> int | BulkResult[T] | BulkResult[dict[str, Any]]:
        """Perform true bulk delete operations for better performance.

        Args:
            ids: List of IDs to delete
            id_field: Field name to use for matching (defaults to "id")
            batch_size: Number of records to process in each batch
            return_objects: Whether to return deleted objects (for audit logging)
            return_fields: Specific fields to return (requires return_objects=True)
            transaction_mode: Transaction control mode
            on_error: Error handling strategy

        Returns:
            - int: Number of deleted records (when return_objects=False)
            - BulkResult[T]: Detailed result with objects and statistics (when return_objects=True)
        """
        from .bulk import bulk_delete

        return await bulk_delete(  # type: ignore[reportReturnType]
            self, ids, id_field, batch_size, return_objects, return_fields, transaction_mode, on_error
        )

    async def delete_all(self, fast: bool = False) -> int:
        """Delete all records from the table.

        Args:
            fast: Whether to use TRUNCATE for fast deletion

        Returns:
            Number of deleted rows (-1 for TRUNCATE as it cannot return accurate count)
        """
        if fast:
            # Use TRUNCATE for maximum performance on large tables
            table_name = self._table.name
            session = self._get_session(readonly=False)
            await session.execute(text(f"TRUNCATE TABLE {table_name}"))
            return -1  # TRUNCATE cannot return accurate row count
        else:
            # Use QuerySet.delete() for transaction safety and signal support
            return await self.filter().delete()

    async def update_all(self, **values) -> int:
        """Update all records in the table with the given values.

        Args:
            **values: Field values to update

        Returns:
            Number of updated rows
        """
        return await self.filter().update(**values)
