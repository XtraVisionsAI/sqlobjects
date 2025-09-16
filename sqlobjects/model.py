from typing import TypeVar

from sqlalchemy import and_, delete, insert, select, update

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
        self._state_manager.set("dirty_fields", set())

        # Set history initialization flag before setting values
        if hasattr(self, "_history_initialized"):
            self._history_initialized = False

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
        """Get all field data.

        Returns:
            Dictionary mapping field names to their current values
        """
        return {name: getattr(self, name, None) for name in self._get_field_names()}

    def _get_dirty_data(self) -> dict:
        """Get modified field data.

        Returns:
            Dictionary mapping dirty field names to their current values,
            or all field data if no dirty fields are tracked
        """
        dirty_fields = self._state_manager.get("dirty_fields", set())
        if not dirty_fields:
            return self._get_all_data()
        return {name: getattr(self, name, None) for name in dirty_fields}

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

    @emit_signals(Operation.SAVE)
    async def save(self, validate: bool = True):
        """Optimized save operation with better error handling.

        Automatically determines whether to INSERT or UPDATE based on
        primary key presence. Uses dirty field tracking for efficient
        updates that only modify changed fields.

        Args:
            validate: Whether to run validation before saving

        Returns:
            Self for method chaining

        Raises:
            PrimaryKeyError: If save operation fails
            ValidationError: If validation fails and validate=True
        """
        session = self.get_session()
        table = self.get_table()

        if validate:
            self.validate_all_fields()

        try:
            if self._has_primary_key_values():
                # UPDATE operation
                pk_conditions = self._build_pk_conditions()
                update_data = self._get_dirty_data()
                if update_data:
                    stmt = update(table).where(and_(*pk_conditions)).values(**update_data)
                    await session.execute(stmt)
            else:
                # INSERT operation
                stmt = insert(table).values(**self._get_all_data())
                result = await session.execute(stmt)
                if result.inserted_primary_key:
                    self._set_primary_key_values(result.inserted_primary_key)
        except Exception as e:
            raise PrimaryKeyError(f"Save operation failed: {e}") from e

        # Clear dirty fields after successful save
        dirty_fields = self._state_manager.get("dirty_fields", set())
        if isinstance(dirty_fields, set):
            dirty_fields.clear()
        return self

    @emit_signals(Operation.DELETE)
    async def delete(self):
        """Delete this model instance from the database.

        Raises:
            PrimaryKeyError: If instance has no primary key values or delete fails
        """
        session = self.get_session()
        table = self.get_table()

        if not self._has_primary_key_values():
            raise PrimaryKeyError("Cannot delete instance without primary key values")

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
            loaded_deferred_fields = self._state_manager.get("loaded_deferred_fields", set())
            if isinstance(loaded_deferred_fields, set):
                if fields:
                    for i, field in enumerate(fields):
                        setattr(self, field, fresh_data[i])
                        if field in self._deferred_fields:
                            loaded_deferred_fields.add(field)
                else:
                    for col_name, value in fresh_data._mapping.items():  # noqa
                        setattr(self, col_name, value)
                        if col_name in self._deferred_fields:
                            loaded_deferred_fields.add(col_name)

        return self

    def __setattr__(self, name, value):
        """Track dirty fields when setting attributes.

        Automatically tracks field modifications for optimized UPDATE
        operations. Skips tracking for private attributes and during
        initialization.

        Args:
            name: Attribute name
            value: Attribute value
        """
        if not name.startswith("_") and hasattr(self, "_state_manager"):
            dirty_fields = self._state_manager.get("dirty_fields", set())
            if isinstance(dirty_fields, set):
                dirty_fields.add(name)
        super().__setattr__(name, value)


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
