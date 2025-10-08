from typing import TypeVar

from sqlalchemy import and_, delete, insert, select, update

from .cascade import CascadeExecutor
from .exceptions import PrimaryKeyError
from .metadata import ModelProcessor
from .mixins import FieldCacheMixin
from .signals import Operation, SignalMixin, emit_signals


# Type variable for ModelMixin
M = TypeVar("M", bound="ModelMixin")


class ModelMixin(FieldCacheMixin, SignalMixin):
    """Optimized mixin class with linear inheritance and performance improvements.

    Combines field caching, signal handling, and history tracking into a single
    optimized mixin. Provides core CRUD operations with intelligent dirty field
    tracking and efficient database operations.

    Features:
    - Automatic dirty field tracking for optimized updates
    - Signal emission for lifecycle events
    - History tracking for audit trails
    - Deferred loading support
    - Validation integration
    """

    @classmethod
    def get_table(cls):
        """Get SQLAlchemy Core Table definition.

        Returns:
            SQLAlchemy Table instance for this model

        Raises:
            AttributeError: If model has no __table__ attribute
        """
        table = getattr(cls, "__table__", None)
        if table is None:
            raise AttributeError(f"Model {cls.__name__} has no __table__ attribute")
        return table

    def __init__(self, **kwargs):
        """Initialize optimized model instance.

        Args:
            **kwargs: Field values to set on the instance
        """
        super().__init__()
        self._state_manager.clear_dirty_fields()

        # Set history initialization flag before setting values
        if hasattr(self, "_history_initialized"):
            self._history_initialized = False

        # Generate default values for fields not provided in kwargs
        self._apply_default_values(kwargs)

        # Set field values
        for key, value in kwargs.items():
            setattr(self, key, value)

        # Enable history tracking after initialization
        if hasattr(self, "_history_initialized"):
            self._history_initialized = True

    def validate(self) -> None:
        """Model-level validation hook that subclasses can override.

        Override this method to implement custom model-level validation
        logic that goes beyond field-level validation.

        Raises:
            ValidationError: If validation fails
        """
        pass

    def _get_all_data(self) -> dict:
        """Get all field data, excluding deferred field proxies.

        Returns:
            Dictionary mapping field names to their current values
        """
        from .fields.proxies import DeferredFieldProxy, RelationFieldProxy

        data = {}
        for name in self._get_field_names():
            value = getattr(self, name, None)
            # Skip proxy objects to avoid serialization issues
            if not isinstance(value, (DeferredFieldProxy, RelationFieldProxy)):
                data[name] = value
        return data

    def _get_dirty_data(self) -> dict:
        """Get modified field data, excluding deferred field proxies.

        Returns:
            Dictionary mapping dirty field names to their current values,
            or all field data if no dirty fields are tracked
        """
        from .fields.proxies import DeferredFieldProxy, RelationFieldProxy

        dirty_fields = self._state_manager.get_dirty_fields()
        if not dirty_fields:
            return self._get_all_data()

        data = {}
        for name in dirty_fields:
            value = getattr(self, name, None)
            # Skip proxy objects to avoid serialization issues
            if not isinstance(value, (DeferredFieldProxy, RelationFieldProxy)):
                data[name] = value
        return data

    def _set_primary_key_values(self, pk_values):
        """Set primary key values.

        Args:
            pk_values: Sequence of primary key values to set
        """
        table = self.get_table()
        pk_columns = list(table.primary_key.columns)
        for i, col in enumerate(pk_columns):
            if i < len(pk_values):
                setattr(self, col.name, pk_values[i])

    def _get_upsert_statement(self, table, data):
        """Construct UPSERT statement based on database dialect."""
        dialect = self.get_session().bind.dialect.name

        pk_columns = list(table.primary_key.columns)

        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert

            stmt = insert(table).values(**data)
            return stmt.on_conflict_do_update(index_elements=pk_columns, set_=data)

        elif dialect == "mysql":
            from sqlalchemy.dialects.mysql import insert

            stmt = insert(table).values(**data)
            return stmt.on_duplicate_key_update(**data)

        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert

            stmt = insert(table).values(**data)
            return stmt.on_conflict_do_update(index_elements=pk_columns, set_=data)

        else:
            # Return None for unsupported dialects to trigger fallback
            return None

    async def _save_internal(self, validate: bool = True, session=None):
        """Internal save operation using UPSERT with fallback to query-then-save.

        This method contains the core save logic that can be reused by both
        the public save() method and the cascade executor without triggering
        additional cascades or signals.

        Args:
            validate: Whether to run validation before saving
            session: Database session to use (gets current session if None)

        Returns:
            Self for method chaining

        Raises:
            PrimaryKeyError: If save operation fails
            ValidationError: If validation fails and validate=True
        """
        if session is None:
            session = self.get_session()
        table = self.get_table()

        if validate:
            self.validate_all_fields()

        data = self._get_all_data()

        # Try UPSERT for supported databases
        upsert_stmt = self._get_upsert_statement(table, data)
        if upsert_stmt is not None:
            try:
                result = await session.execute(upsert_stmt)
                if result.inserted_primary_key:
                    self._set_primary_key_values(result.inserted_primary_key)
                # Clear dirty fields after successful save
                self._state_manager.clear_dirty_fields()
                return self
            except Exception as e:
                raise PrimaryKeyError(f"Upsert operation failed: {e}") from e

        # Fallback: query database to determine INSERT or UPDATE
        try:
            pk_conditions = self._build_pk_conditions()
            existing = await session.execute(select(table).where(and_(*pk_conditions)))

            if existing.first():
                # Record exists, perform UPDATE
                update_data = self._get_dirty_data()
                if update_data:
                    stmt = update(table).where(and_(*pk_conditions)).values(**update_data)
                    await session.execute(stmt)
            else:
                # Record does not exist, perform INSERT
                stmt = insert(table).values(**data)
                result = await session.execute(stmt)
                if result.inserted_primary_key:
                    self._set_primary_key_values(result.inserted_primary_key)
        except Exception as e:
            raise PrimaryKeyError(f"Save operation failed: {e}") from e

        # Clear dirty fields after successful save
        self._state_manager.clear_dirty_fields()
        return self

    @emit_signals(Operation.SAVE)
    async def save(self, validate: bool = True, cascade: bool | None = None, session=None):
        """Save operation with cascade support and automatic operation detection.

        Automatically determines whether to INSERT or UPDATE based on
        primary key presence. Uses dirty field tracking for efficient
        updates that only modify changed fields. Supports cascade save
        operations for related objects.

        Args:
            validate: Whether to run validation before saving
            cascade: Whether to cascade save to related objects (auto-detected if None)
            session: Database session to use

        Returns:
            Self for method chaining

        Raises:
            PrimaryKeyError: If save operation fails
            ValidationError: If validation fails and validate=True
        """
        if session is None:
            session = self.get_session()

        # Determine if cascade should be used
        if cascade is None:
            cascade = self._has_cascade_relations()

        # Use cascade executor for cascade operations
        if cascade:
            executor = CascadeExecutor()
            return await executor.execute_save_operation(self, validate=validate, session=session)  # type: ignore[reportArgumentType]

        # Direct save operation without cascade
        return await self._save_internal(validate=validate, session=session)

    @emit_signals(Operation.DELETE)
    async def delete(self, cascade: bool = True):
        """Delete this model instance from the database with cascade support.

        Args:
            cascade: Whether to handle cascade deletion (default: True)

        Raises:
            PrimaryKeyError: If instance has no primary key values or delete fails
        """
        if not self._has_primary_key_values():
            raise PrimaryKeyError("Cannot delete instance without primary key values")

        session = self.get_session()

        # Use cascade executor for cascade operations
        if cascade:
            executor = CascadeExecutor()
            await executor.execute_delete_operation(self, session=session)
            return

        # Direct delete operation without cascade
        await self._delete_internal(session=session)

    async def _delete_internal(self, session=None):
        """Internal delete operation without cascade handling."""
        if session is None:
            session = self.get_session()

        table = self.get_table()
        try:
            pk_conditions = self._build_pk_conditions()
            stmt = delete(table).where(and_(*pk_conditions))
            await session.execute(stmt)
        except Exception as e:
            raise PrimaryKeyError(f"Delete operation failed: {e}") from e

    async def refresh(self, fields: list[str] | None = None, include_deferred: bool = True):
        """Refresh this instance with the latest data from the database.

        Args:
            fields: Specific fields to refresh, or None for all fields
            include_deferred: Whether to include deferred fields in refresh

        Returns:
            Self for method chaining

        Raises:
            ValueError: If instance has no primary key values
        """
        session = self.get_session()
        table = self.get_table()

        if not self._has_primary_key_values():
            raise ValueError("Cannot refresh instance without primary key values")

        pk_conditions = self._build_pk_conditions()

        if fields:
            columns_to_select = [table.c[field] for field in fields]
        else:
            if not include_deferred:
                field_names = [f for f in self._get_field_names() if f not in self._deferred_fields]
                columns_to_select = [table.c[field] for field in field_names]
            else:
                columns_to_select = [table]

        stmt = select(*columns_to_select).where(and_(*pk_conditions))
        result = await session.execute(stmt)
        fresh_data = result.first()

        if fresh_data:
            if fields:
                for i, field in enumerate(fields):
                    setattr(self, field, fresh_data[i])
                    if field in self._deferred_fields:
                        self._state_manager.add_loaded_deferred_field(field)
            else:
                for col_name, value in fresh_data._mapping.items():  # noqa
                    setattr(self, col_name, value)
                    if col_name in self._deferred_fields:
                        self._state_manager.add_loaded_deferred_field(col_name)

        return self

    def _has_cascade_relations(self) -> bool:
        """Check if this model has any relationships configured for cascade operations.

        Returns:
            True if any relationship has cascade operations, False otherwise
        """
        # Check for cascade relationships in state manager
        if hasattr(self, "_state_manager"):
            cascade_relationships = self._state_manager.get_cascade_relationships()
            if cascade_relationships:
                return True

        # Check for configured cascade relationships
        relationships = getattr(self.__class__, "_relationships", {})
        for rel_descriptor in relationships.values():
            if hasattr(rel_descriptor, "property") and rel_descriptor.property.cascade:
                return True
        return False

    def _has_on_delete_relations(self) -> bool:
        """Check if this model has any relationships with on_delete configuration.

        Returns:
            True if any relationship has on_delete behavior, False otherwise
        """
        from .cascade import OnDelete

        relationships = getattr(self.__class__, "_relationships", {})

        for _, rel_descriptor in relationships.items():
            if hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade"):
                cascade_str = rel_descriptor.property.cascade
                if cascade_str and ("delete" in cascade_str or "all" in cascade_str):
                    return True
            if (
                hasattr(rel_descriptor, "property")
                and hasattr(rel_descriptor.property, "on_delete")
                and rel_descriptor.property.on_delete != OnDelete.NO_ACTION
            ):
                return True
        return False

    def _get_primary_key_field(self) -> str:
        """Get the primary key field name.

        Returns:
            Name of the primary key field

        Raises:
            PrimaryKeyError: If no primary key is found
        """
        table = self.get_table()
        pk_columns = list(table.primary_key.columns)
        if not pk_columns:
            raise PrimaryKeyError(f"Model {self.__class__.__name__} has no primary key")
        return pk_columns[0].name

    def __setattr__(self, name, value):
        """Track dirty fields when setting attributes.

        Automatically tracks field modifications for optimized UPDATE
        operations. Skips tracking for private attributes and during
        initialization.

        Args:
            name: Attribute name
            value: Attribute value
        """
        # Handle relationship field assignments
        if hasattr(self, "_get_relationship_fields") and name in self._get_relationship_fields():
            self._handle_relationship_assignment(name, value)
        elif not name.startswith("_") and hasattr(self, "_state_manager"):
            self._state_manager.add_dirty_field(name)
        super().__setattr__(name, value)

    def _handle_relationship_assignment(self, field_name: str, value):
        """Handle assignment of relationship objects for cascade save."""
        if not hasattr(self, "_state_manager"):
            return

        # Store relationship objects and mark for cascade save
        relationship_value = value if isinstance(value, list) else [value] if value is not None else []
        self._state_manager.set_cascade_relationship(field_name, relationship_value)

    def _get_relationship_fields(self) -> set[str]:
        """Get relationship field names from model metadata."""
        relationships = getattr(self.__class__, "_relationships", {})
        return set(relationships.keys())


class ObjectModel(ModelMixin, metaclass=ModelProcessor):
    """Base model class with configuration support and common functionality.

    This is the main base class for all SQLObjects models. It combines
    the ModelProcessor metaclass for automatic table generation with
    the ModelMixin for runtime functionality.

    Features:
    - Automatic table generation from field definitions
    - Built-in CRUD operations with signal support
    - Query manager (objects) for database operations
    - Validation and history tracking
    - Deferred loading and field caching

    Usage:
        class User(ObjectModel):
            name: Column[str] = str_column(length=100)
            email: Column[str] = str_column(length=255, unique=True)
    """

    __abstract__ = True

    def __init_subclass__(cls, **kwargs):
        """Process subclass initialization and setup objects manager.

        Automatically sets up the objects manager for database operations
        and initializes validators for non-abstract model classes.

        Args:
            **kwargs: Additional keyword arguments passed to parent
        """
        super().__init_subclass__(**kwargs)

        # Check if this class explicitly defines __abstract__ in its own __dict__
        # If not, it's a concrete model (not abstract)
        is_abstract = cls.__dict__.get("__abstract__", False)

        # For concrete models, explicitly set __abstract__ = False to avoid inheritance confusion
        if not is_abstract:
            cls.__abstract__ = False

        # Setup objects manager for non-abstract models
        if not is_abstract and not hasattr(cls, "objects"):
            from .objects import ObjectsDescriptor

            cls.objects = ObjectsDescriptor(cls)

        # Setup validators if method exists
        setup_validators = getattr(cls, "_setup_validators", None)
        if setup_validators and callable(setup_validators):
            setup_validators()
