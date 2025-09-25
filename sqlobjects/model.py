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
        self._state_manager.set("dirty_fields", set())

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
                dirty_fields = self._state_manager.get("dirty_fields", set())
                if isinstance(dirty_fields, set):
                    dirty_fields.clear()
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
        dirty_fields = self._state_manager.get("dirty_fields", set())
        if isinstance(dirty_fields, set):
            dirty_fields.clear()
        return self

    @emit_signals(Operation.SAVE)
    async def save(self, validate: bool = True, cascade: bool | None = None, session=None):
        """Optimized save operation with cascade support and better error handling.

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

        # Check if we need to process cascade relationships
        needs_cascade = (
            self._state_manager.get("needs_cascade_save", False) if hasattr(self, "_state_manager") else False
        )

        if needs_cascade and cascade is not False:
            await self._process_cascade_relationships(session)

        # Determine if cascade should be used - only auto-detect if None
        if cascade is None:
            cascade = self._has_cascade_relations()

        # Use cascade executor only if explicitly requested or auto-detected
        if cascade:
            executor = CascadeExecutor()
            await executor.execute_cascade_operation(self, "save", session)  # type: ignore[reportArgumentType]
            return self

        # Standard save operation using internal method
        return await self._save_internal(validate=validate, session=session)

    async def _process_cascade_relationships(self, session):
        """Process cascade relationships for this instance."""
        if not hasattr(self, "_state_manager"):
            return

        cascade_relationships = self._state_manager.get("cascade_relationships", {})
        if not cascade_relationships:
            return

        # Save self first to get primary key
        await self._save_internal(session=session)

        # Process each relationship with full update logic
        for rel_name, new_related_objects in cascade_relationships.items():
            await self._process_relationship_update(rel_name, new_related_objects, session)

        # keep cascade_relationships
        # self._state_manager.set("cascade_relationships", {})
        self._state_manager.set("needs_cascade_save", False)

    async def _process_relationship_update(self, rel_name: str, new_related_objects, session):
        """Process complete relationship update: add, remove, modify."""
        from .cascade import ForeignKeyInferrer

        # Get relationship configuration
        relationships = getattr(self.__class__, "_relationships", {})
        if rel_name not in relationships:
            return

        rel_descriptor = relationships[rel_name]
        if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
            return

        cascade_str = rel_descriptor.property.cascade or ""
        has_delete_orphan = "delete-orphan" in cascade_str

        # Get current related objects from database
        current_objects = await self._fetch_current_related_objects(rel_name, session)

        # Convert to lists for processing
        if new_related_objects is None:
            new_objects = []
        elif isinstance(new_related_objects, list):
            new_objects = new_related_objects
        else:
            new_objects = [new_related_objects]

        # Process updates
        await self._update_relationship_objects(current_objects, new_objects, has_delete_orphan, session)

        # Set foreign keys for new/updated objects
        for obj in new_objects:
            if hasattr(obj, "save"):
                ForeignKeyInferrer.set_foreign_key(self, obj)
                await obj.using(session).save(cascade=False)

    async def _fetch_current_related_objects(self, rel_name: str, session) -> list:
        """Fetch current related objects from database."""
        relationships = getattr(self.__class__, "_relationships", {})
        if rel_name not in relationships:
            return []

        rel_descriptor = relationships[rel_name]
        if not hasattr(rel_descriptor.property, "resolved_model") or not rel_descriptor.property.resolved_model:
            return []

        related_model = rel_descriptor.property.resolved_model
        foreign_keys = rel_descriptor.property.foreign_keys

        if not foreign_keys:
            return []

        # fetch foreign keys
        fk_field = foreign_keys if isinstance(foreign_keys, str) else foreign_keys[0]

        # get pk
        pk_value = getattr(self, self._get_primary_key_field())
        if pk_value is None:
            return []

        current_objects = (
            await related_model.objects.using(session).filter(getattr(related_model, fk_field) == pk_value).all()
        )

        return current_objects

    async def _update_relationship_objects(
        self, current_objects: list, new_objects: list, has_delete_orphan: bool, session
    ):
        """Update relationship objects: handle add, remove, modify."""
        # Create ID mappings
        current_by_id = {getattr(obj, "id", None): obj for obj in current_objects if getattr(obj, "id", None)}
        new_by_id = {getattr(obj, "id", None): obj for obj in new_objects if getattr(obj, "id", None)}

        # Find objects to remove (orphans)
        if has_delete_orphan:
            for obj_id, obj in current_by_id.items():
                if obj_id and obj_id not in new_by_id:
                    # This object is no longer in the relationship - delete it
                    await obj.using(session).delete(cascade=False)

        # Process existing objects for updates
        for obj in new_objects:
            obj_id = getattr(obj, "id", None)
            if obj_id and obj_id in current_by_id:
                # This is an existing object - check if it needs updating
                current_obj = current_by_id[obj_id]
                if self._object_has_changes(obj, current_obj):
                    # Object has changes - it will be saved in the main loop
                    pass

    @staticmethod
    def _object_has_changes(new_obj, current_obj) -> bool:
        """Check if object has changes by comparing field values."""
        # Simple implementation - compare key fields
        field_names = getattr(new_obj, "_get_field_names", lambda: [])() or []
        for field_name in field_names:
            if field_name.startswith("_"):
                continue
            new_value = getattr(new_obj, field_name, None)
            current_value = getattr(current_obj, field_name, None)
            if new_value != current_value:
                return True
        return False

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

        # Use cascade executor if cascade is enabled
        if cascade:
            executor = CascadeExecutor()
            await executor.execute_cascade_operation(self, "delete")  # type: ignore[reportArgumentType]
            return

        # Standard delete operation without cascade
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

    def _has_cascade_relations(self) -> bool:
        """Check if this model has any relationships configured for cascade operations.

        Returns:
            True if any relationship has cascade=True, False otherwise
        """
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
            dirty_fields = self._state_manager.get("dirty_fields", set())
            if isinstance(dirty_fields, set):
                dirty_fields.add(name)
        super().__setattr__(name, value)

    def _handle_relationship_assignment(self, field_name: str, value):
        """Handle assignment of relationship objects for cascade save."""
        if not hasattr(self, "_state_manager"):
            return

        # Store relationship objects
        cascade_relationships = self._state_manager.get("cascade_relationships", {})
        cascade_relationships[field_name] = value if isinstance(value, list) else [value]  # type: ignore[reportOptionalSubscript]
        self._state_manager.set("cascade_relationships", cascade_relationships)

        # Mark for cascade save
        self._state_manager.set("needs_cascade_save", True)

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
