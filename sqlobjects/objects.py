from typing import Any, Generic

from sqlalchemy import (
    bindparam,
    delete,
    func,
    insert,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import DoesNotExist, MultipleObjectsReturned, ValidationError
from .queries import QuerySet, T
from .session import SessionContextManager
from .signals import Operation, SignalContext, emit_signals


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
    """Object manager providing Django ORM-like interface."""

    def __init__(self, model_class: type[T], db_or_session: str | AsyncSession | None = None):
        self._model = model_class
        self._db_or_session = db_or_session

    @property
    def _session(self) -> AsyncSession:
        """获取有效的会话对象"""
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session

    # ========== Session Methods ==========

    def using(self, db_or_session: str | AsyncSession) -> "ObjectsManager[T]":
        """指定数据库名或会话对象"""
        return ObjectsManager(self._model, db_or_session)

    # ========== Basic Query Methods ==========

    def filter(self, *args) -> QuerySet[T]:
        """Filter objects using Q objects SQLAlchemy expressions and keyword arguments.

        Args:
            *args: Q objects or SQLAlchemy expressions for complex conditions

        Returns:
            QuerySet with filter conditions applied
        """
        return QuerySet(self._model, None, self._session).filter(*args)

    async def all(self) -> list[T]:
        """Get all objects of this model.

        Returns:
            List of all model instances
        """
        return await self.filter().all()

    async def get(self, *args) -> T:
        """Get a single object matching the given conditions.

        Args:
            *args: Q objects or SQLAlchemy expressions for complex conditions

        Returns:
            Single model instance

        Raises:
            DoesNotExist: If no object matches the conditions
            MultipleObjectsReturned: If multiple objects match the conditions
            ValidationError: If field lookup conditions are invalid
            DatabaseError: If database connection or query execution fails
            AttributeError: If specified field names don't exist on the model

        Examples:
            # Basic usage with default session
            user = await User.objects.get(User.username="john")

            # Using specific database session
            user = await User.objects.use(analytics_session).get(User.username="john")

            # Complex query with session
            user = await User.objects.use(analytics_session).get(
                Q(User.username="john", User.email="john@example.com")
            )
        """

        results = await self.filter(*args).limit(2).all()
        if not results:
            raise DoesNotExist(f"{self._model.__name__} matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model.__name__} objects returned")
        return results[0]

    async def first(self) -> T | None:
        """Get the first object according to the default ordering.

        Returns:
            First model instance or None if no objects exist
        """
        return await self.filter().first()

    async def last(self) -> T | None:
        """Get the last object according to the default ordering.

        Returns:
            Last model instance or None if no objects exist
        """
        return await self.filter().last()

    async def earliest(self, *fields) -> T | None:
        """Get the earliest object based on the specified fields.

        Args:
            *fields: Field names to order by for finding earliest object (string field names only)

        Returns:
            Earliest model instance or None if no objects exist
        """
        return await self.filter().earliest(*fields)

    async def latest(self, *fields) -> T | None:
        """Get the latest object based on the specified fields.

        Args:
            *fields: Field names to order by for finding latest object (string field names only)

        Returns:
            Latest model instance or None if no objects exist
        """
        return await self.filter().latest(*fields)

    def iterator(self, memory_cleanup_interval: int = 1000):
        """Return an async iterator for processing large datasets efficiently.

        Args:
            memory_cleanup_interval: Clear session cache every N items to prevent memory buildup

        Returns:
            Async iterator that yields model instances one by one
        """
        return self.filter().iterator(memory_cleanup_interval=memory_cleanup_interval)

    async def get_item(self, key) -> T | list[T]:
        """Get items by index or slice, supporting both integer and slice access.

        Args:
            key: Integer index or slice object

        Returns:
            Single object (for integer key) or list of objects (for slice key)

        Raises:
            ValueError: If negative index is used
            IndexError: If index is out of range
            TypeError: If key type is invalid
        """
        return await self.filter().get_item(key)

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
        return await self.filter().dates(field, kind, order=order)

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
        return await self.filter().datetimes(field, kind, order=order)

    async def get_or_create(
        self, *filters, defaults: dict[str, Any] | None = None, validate: bool = True
    ) -> tuple[T, bool]:
        """Get an existing object or create a new one if it doesn't exist.

        Args:
            *filters: Q objects or SQLAlchemy expressions for lookup conditions
            defaults: Default values to use when creating a new object
            validate: Whether to validate when creating

        Returns:
            Tuple of (object, created) where created is True if object was created

        Examples:
            # Simple field lookup
            user, created = await User.objects.get_or_create(
                User.username == "john",
                defaults={"email": "john@example.com"}
            )

            # Multiple conditions
            user, created = await User.objects.get_or_create(
                User.username == "john",
                User.is_active == True,
                defaults={"email": "john@example.com"}
            )

            # Complex conditions with Q objects
            user, created = await User.objects.get_or_create(
                Q(User.username == "john") | Q(User.email == "john@example.com"),
                defaults={"is_active": True}
            )
        """
        try:
            # Build queryset with conditions
            queryset = self.filter()

            # Apply filter conditions
            if filters:
                queryset = queryset.filter(*filters)

            obj = await queryset.get()
            return obj, False
        except DoesNotExist:
            pass

        create_kwargs = {}
        if defaults:
            create_kwargs.update(defaults)
        return await self.create(validate=validate, **create_kwargs), True

    async def update_or_create(
        self, *filters, defaults: dict[str, Any] | None = None, validate: bool = True
    ) -> tuple[T, bool]:
        """Update an existing object or create a new one if it doesn't exist.

        Args:
            *filters: Q objects or SQLAlchemy expressions for lookup conditions
            defaults: Values to update/set when object exists or is created
            validate: Whether to validate when updating/creating

        Returns:
            Tuple of (object, created) where created is True if object was created

        Examples:
            # Simple field lookup
            user, created = await User.objects.update_or_create(
                User.username == "john",
                defaults={"last_login": datetime.now()}
            )

            # Multiple conditions
            user, created = await User.objects.update_or_create(
                User.username == "john",
                User.is_active == True,
                defaults={"last_login": datetime.now()}
            )

            # Complex conditions with Q objects
            user, created = await User.objects.update_or_create(
                Q(User.username == "john") | Q(User.email == "john@example.com"),
                defaults={"last_login": datetime.now()}
            )
        """
        try:
            # Build queryset with conditions
            queryset = self.filter()

            # Apply filter conditions
            if filters:
                queryset = queryset.filter(*filters)

            obj = await queryset.get()
            if defaults:
                context = SignalContext(
                    operation=Operation.SAVE, session=self._session, model_class=obj.__class__, instance=obj
                )
                await obj._emit_signal("before", context)  # type: ignore[attr-defined] # noqa

                for key, value in defaults.items():
                    setattr(obj, key, value)
                if validate:
                    obj.validate_all()  # type: ignore[attr-defined]

                await self._session.flush()

                await obj._emit_signal("after", context)  # type: ignore[attr-defined] # noqa
            return obj, False
        except DoesNotExist:
            pass

        create_kwargs = {}
        if defaults:
            create_kwargs.update(defaults)
        return await self.create(validate=validate, **create_kwargs), True

    async def in_bulk(self, id_list: list[Any] | None = None, field_name: str = "pk") -> dict[Any, T]:
        """Get multiple objects as a dictionary mapping field values to objects.

        This method is useful for efficiently retrieving multiple objects when you
        have a list of identifiers and want to access them by their field values.

        Args:
            id_list: List of values to match against the specified field
            field_name: Name of the field to use as dictionary keys ('pk' for primary key)

        Returns:
            Dictionary mapping field values to model instances
        """

        if field_name == "pk":
            pk_columns = list(self._model.__table__.primary_key)  # noqa
            actual_field = pk_columns[0].name if pk_columns else "id"
        else:
            actual_field = field_name

        queryset = self.filter()
        if id_list is not None:
            field_attr = getattr(self._model, actual_field)
            queryset = queryset.filter(field_attr.in_(id_list))

        objects = await queryset.all()
        return {getattr(obj, actual_field): obj for obj in objects}

    # ========== Create Operations ==========

    @emit_signals(Operation.SAVE)
    async def create(self, validate: bool = True, **kwargs) -> T:
        """Create a new object with the given field values.

        Args:
            validate: Whether to execute all validation (both SQLObjects and SQLAlchemy validators)
            **kwargs: Field values for the new object

        Returns:
            Created model instance

        Raises:
            ValidationError: If validation fails during creation
            IntegrityError: If database constraints are violated (unique, foreign key, etc.)
            DatabaseError: If database connection or transaction fails
            TypeError: If invalid field names or values are provided
            AttributeError: If specified field names don't exist on the model
        """
        try:
            obj = self._model(**kwargs)
            # 直接执行数据库操作，不调用 obj.save() 避免重复触发信号
            if validate:
                obj.validate_all()  # type: ignore[attr-defined]

            self._session.add(obj)
            await self._session.flush()
            return obj
        except ValidationError as e:
            if not e.is_multiple:
                enhanced_error = ValidationError(
                    f"Failed to create {self._model.__name__}: {e.message}",
                    field=e.field,
                    code=e.code,
                    params=e.params,
                )
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e
            else:
                enhanced_message = f"Failed to create {self._model.__name__}: {e.message}"
                enhanced_error = ValidationError(enhanced_message, field_errors=e.field_errors)
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e

    @emit_signals(Operation.SAVE, is_bulk=True)
    async def bulk_create(self, objects: list[dict[str, Any]]) -> None:
        """Create multiple objects for better performance.

        Args:
            objects: List of dictionaries containing object data
        """
        if not objects:
            return

        stmt = insert(self._model).values(objects)
        await self._session.execute(stmt)
        await self._session.flush()

    # ========== Update & Delete Operations ==========

    @emit_signals(Operation.UPDATE, is_bulk=True)
    async def bulk_update(
        self, mappings: list[dict[str, Any]], match_fields: list[str] | None = None, batch_size: int = 1000
    ) -> int:
        """Perform true bulk update operations for better performance.

        Args:
            mappings: List of dictionaries containing match fields and update values
            match_fields: Fields to use for matching records (defaults to ["id"])
            batch_size: Number of records to process in each batch

        Returns:
            Total number of affected rows

        Raises:
            ValidationError: If mappings is empty or invalid
            IntegrityError: If database constraints are violated during update
            DatabaseError: If database connection or transaction fails
        """
        if not mappings:
            raise ValidationError("Bulk update requires non-empty mappings list")

        if match_fields is None:
            match_fields = ["id"]

        total_affected = 0

        # Process in batches using Core-level update
        for i in range(0, len(mappings), batch_size):
            batch = mappings[i : i + batch_size]

            # Build WHERE conditions using match_fields
            where_conditions = []
            for field in match_fields:
                where_conditions.append(getattr(self._model, field) == bindparam(f"match_{field}"))

            # Create Core-level update statement
            stmt = update(self._model).where(*where_conditions)

            # Add update values (exclude match fields from values)
            update_values = {}
            for key in batch[0].keys():
                if key not in match_fields:
                    update_values[key] = bindparam(f"update_{key}")

            if update_values:
                stmt = stmt.values(**update_values)

                # Prepare parameter mappings
                param_mappings = []
                for mapping in batch:
                    param_dict = {}
                    # Add match field parameters
                    for field in match_fields:
                        param_dict[f"match_{field}"] = mapping[field]
                    # Add update value parameters
                    for key, value in mapping.items():
                        if key not in match_fields:
                            param_dict[f"update_{key}"] = value
                    param_mappings.append(param_dict)

                # Use connection().execute() to bypass ORM layer completely
                conn = await self._session.connection()
                result = await conn.execute(stmt, param_mappings)
                total_affected += result.rowcount if result.rowcount is not None else 0

        await self._session.flush()
        # Expire all ORM objects to ensure fresh data is loaded from database as we use core method for bulk update
        # Note: This may cause issues in async mode if objects are accessed immediately
        self._session.expire_all()

        return total_affected

    @emit_signals(Operation.DELETE, is_bulk=True)
    async def bulk_delete(self, ids: list[Any], id_field: str = "id", batch_size: int = 1000) -> int:
        """Perform true bulk delete operations for better performance.

        Args:
            ids: List of IDs to delete
            id_field: Field name to use for matching (defaults to "id")
            batch_size: Number of records to process in each batch

        Returns:
            Total number of deleted rows

        Raises:
            ValidationError: If ids list is empty
            IntegrityError: If foreign key constraints prevent deletion
            DatabaseError: If database connection or transaction fails
        """
        if not ids:
            raise ValidationError("Bulk delete requires non-empty ids list")

        total_affected = 0

        # Process in batches using IN clause
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]

            # Create delete statement with IN clause
            stmt = delete(self._model).where(getattr(self._model, id_field).in_(batch_ids))
            result = await self._session.execute(stmt)
            total_affected += result.rowcount if result.rowcount is not None else 0

        await self._session.flush()
        return total_affected

    async def delete_all(self, fast: bool = False) -> int:
        """Delete all records from the table.

        Args:
            fast: Whether to use TRUNCATE for fast deletion
                 Note: TRUNCATE doesn't support transaction rollback and doesn't trigger signals
                 Use with caution in production environments

        Returns:
            Number of deleted rows (-1 for TRUNCATE as it cannot return accurate count)
        """

        if fast:
            # Use TRUNCATE for maximum performance on large tables
            # Warning: This bypasses transaction safety and signal triggering
            table_name = self._model.__tablename__
            await self._session.execute(text(f"TRUNCATE TABLE {table_name}"))
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

        Examples:
            # Update all users' status
            affected = await User.objects.update_all(status="migrated")
        """
        return await self.filter().update(**values)

    # ========== Aggregation & Statistics ==========

    async def count(self) -> int:
        """Count the total number of objects.

        Returns:
            Total number of objects
        """
        return await self.filter().count()

    async def aggregate(self, **kwargs) -> dict[str, Any]:
        """Perform aggregation operations on the queryset.

        Args:
            **kwargs: Aggregation expressions with their aliases

        Returns:
            Dictionary with aggregation results
        """
        return await self.filter().aggregate(**kwargs)

    async def values(self, *fields) -> list[dict[str, Any]]:
        """Get dictionaries containing only the specified field values.

        Args:
            *fields: Field names to include in the result (string field names only)

        Returns:
            List of dictionaries with field names as keys
        """
        return await self.filter().values(*fields)

    async def values_list(self, *fields, flat: bool = False) -> list:
        """Get list of tuples or single values for the specified fields.

        Args:
            *fields: Field names to include (string field names only)
            flat: If True and only one field specified, return flat list of values

        Returns:
            List of tuples (or flat list if flat=True and single field)
        """
        return await self.filter().values_list(*fields, flat=flat)

    # ========== Utility Methods ==========

    async def random(self, count: int = 1) -> list[T]:
        """Get random objects from the table.

        Args:
            count: Number of random objects to return

        Returns:
            List of randomly selected model instances
        """
        return await self.filter().order_by(func.random()).limit(count).all()

    # ========== QuerySet Shortcuts ==========

    def distinct(self, *fields) -> QuerySet[T]:
        """Apply DISTINCT clause to eliminate duplicate rows.

        Args:
            *fields: Field names or SQLAlchemy expressions to apply DISTINCT on, if empty applies to all

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
            *fields: Field names or SQLAlchemy expressions
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
            *fields: Field names to load (string field names only)

        Returns:
            QuerySet that loads only the specified fields
        """
        return self.filter().only(*fields)

    def defer(self, *fields) -> QuerySet[T]:
        """Defer loading of the specified fields until they are accessed.

        Args:
            *fields: Field names to defer loading (string field names only)

        Returns:
            QuerySet with deferred field loading
        """
        return self.filter().defer(*fields)

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

    def select_for_update(self, nowait: bool = False, skip_locked: bool = False) -> QuerySet[T]:
        """Apply row-level locking to the query using FOR UPDATE.

        Args:
            nowait: If True, don't wait for locks and return error immediately
            skip_locked: If True, skip rows that are already locked

        Returns:
            QuerySet with FOR UPDATE locking applied
        """
        return self.filter().select_for_update(nowait=nowait, skip_locked=skip_locked)

    def slice(self, start: int, stop: int | None = None) -> QuerySet[T]:
        """Slice query results with offset and limit.

        Args:
            start: Starting offset
            stop: Ending position (exclusive)

        Returns:
            QuerySet with slice applied
        """
        queryset = self.filter().offset(start)
        if stop is not None:
            queryset = queryset.limit(stop - start)
        return queryset

    # ========== Relationships & Joins ==========

    def select_related(self, *relations) -> QuerySet[T]:
        """Preload related objects using JOIN operations.

        Args:
            *relations: Relationship names to preload (string relationship names only)

        Returns:
            QuerySet with related objects preloaded
        """
        return self.filter().select_related(*relations)

    def prefetch_related(self, *relations) -> QuerySet[T]:
        """Prefetch related objects using separate queries.

        Args:
            *relations: Relationship names to prefetch (string relationship names only)

        Returns:
            QuerySet with related objects prefetched
        """
        return self.filter().prefetch_related(*relations)

    def join(self, target_model, on_condition=None, join_type="inner") -> QuerySet[T]:
        """Perform manual JOIN with another model.

        Args:
            target_model: Model class to join with
            on_condition: Join condition, if None uses foreign key relationship
            join_type: Type of join ('inner' or 'left')

        Returns:
            QuerySet with the join applied
        """
        return self.filter().join(target_model, on_condition, join_type)

    def leftjoin(self, target, onclause=None) -> QuerySet[T]:
        """Perform LEFT JOIN with another model.

        Args:
            target: Target model or table to join
            onclause: Join condition

        Returns:
            QuerySet with left join applied
        """
        return self.filter().join(target, onclause, join_type="left")

    def outerjoin(self, target, onclause=None) -> QuerySet[T]:
        """Perform OUTER JOIN with another model.

        Args:
            target: Target model or table to join
            onclause: Join condition

        Returns:
            QuerySet with outer join applied
        """
        return self.filter().join(target, onclause, isouter=True)

    # ========== Advanced Query Methods ==========

    def annotate(self, **kwargs) -> QuerySet[T]:
        """Add annotation fields to the queryset.

        Args:
            **kwargs: Annotation expressions with their aliases

        Returns:
            QuerySet with annotation fields added
        """
        return self.filter().annotate(**kwargs)

    def group_by(self, *fields) -> QuerySet[T]:
        """Group query results by the specified fields.

        Args:
            *fields: Field names or SQLAlchemy expressions to group by

        Returns:
            QuerySet with group by applied
        """
        return self.filter().group_by(*fields)

    def having(self, *conditions) -> QuerySet[T]:
        """Apply HAVING clause for aggregated queries.

        Args:
            *conditions: SQLAlchemy expressions for having clause

        Returns:
            QuerySet with having conditions applied
        """
        return self.filter().having(*conditions)

    def options(self, *options) -> QuerySet[T]:
        """Apply query options for performance optimization.

        Args:
            *options: SQLAlchemy query options like joinedload, selectinload

        Returns:
            QuerySet with options applied
        """
        return self.filter().options(*options)
