from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import Table, and_, select

from .exceptions import PrimaryKeyError, ValidationError
from .fields.proxies import DeferredFieldProxy, RelationFieldProxy
from .fields.utils import get_column_from_field, is_field_definition
from .session import AsyncSession, get_session


if TYPE_CHECKING:
    from .metadata import ModelRegistry


class _StateManager:
    """Unified state management for model instances."""

    def __init__(self):
        """Initialize empty state dictionary."""
        self._state: dict[str, Any] = {
            "dirty_fields": set(),
            "cascade_relationships": {},  # Store relationship objects for cascade save
            "needs_cascade_save": False,  # Flag for cascade save requirement
        }

    def get(self, key: str, default=None):
        """Get state value by key.

        Args:
            key: State key to retrieve
            default: Default value if key not found

        Returns:
            State value or default
        """
        return self._state.get(key, default)

    def set(self, key: str, value):
        """Set state value by key.

        Args:
            key: State key to set
            value: Value to store
        """
        self._state[key] = value


class BaseMixin:
    """Base mixin with common functionality and state management."""

    if TYPE_CHECKING:
        __table__: ClassVar[Table]
        __registry__: ClassVar["ModelRegistry"]

    def __init__(self):
        """Initialize state manager if not already present."""
        if not hasattr(self, "_state_manager"):
            self._state_manager = _StateManager()

    @classmethod
    def get_table(cls) -> Table:
        """Get SQLAlchemy Core Table definition.

        Returns:
            SQLAlchemy Table instance for this model
        """
        ...

    @classmethod
    @lru_cache(maxsize=1)
    def _get_field_names(cls) -> list[str]:
        """Get field names from the table definition (cached).

        Returns:
            List of field names from the table columns
        """
        return list(cls.get_table().columns.keys())


class SessionMixin(BaseMixin):
    """Session management - Layer 1."""

    def get_session(self) -> AsyncSession:
        """Get the effective session for database operations.

        Returns:
            AsyncSession instance for database operations
        """
        bound_session = self._state_manager.get("bound_session")
        if isinstance(bound_session, str):
            return get_session(bound_session)
        return bound_session or get_session()

    def using(self, db_or_session: str | AsyncSession):
        """Return self bound to specific database/connection.

        Args:
            db_or_session: Database name or AsyncSession instance

        Returns:
            Self with bound session for method chaining
        """
        self._state_manager.set("bound_session", db_or_session)
        return self


class PrimaryKeyMixin(SessionMixin):
    """Primary key operations - Layer 2."""

    @classmethod
    @lru_cache(maxsize=1)
    def _get_primary_key_info(cls) -> dict[str, Any]:
        """Cache primary key information at class level.

        Returns:
            Dictionary with 'columns' and 'names' keys containing
            primary key column objects and names respectively
        """
        table = cls.get_table()
        pk_columns = list(table.primary_key.columns)
        return {"columns": pk_columns, "names": [col.name for col in pk_columns]}

    def _get_primary_key_values(self) -> dict[str, Any]:
        """Get primary key values as dict.

        Returns:
            Dictionary mapping primary key field names to their values
        """
        pk_info = self._get_primary_key_info()
        return {name: getattr(self, name, None) for name in pk_info["names"]}

    def _has_primary_key_values(self) -> bool:
        """Check if instance has primary key values set.

        Returns:
            True if all primary key fields have non-None values
        """
        pk_values = self._get_primary_key_values()
        # Handle case where model has no primary key fields
        if not pk_values:
            return False
        return all(value is not None for value in pk_values.values())

    def _build_pk_conditions(self) -> list:
        """Build primary key conditions for queries.

        Returns:
            List of SQLAlchemy condition expressions for primary key matching

        Raises:
            PrimaryKeyError: If primary key values are not set
        """
        if not self._has_primary_key_values():
            raise PrimaryKeyError("Cannot build conditions without primary key values")

        table = self.get_table()
        pk_values = self._get_primary_key_values()
        return [table.c[name] == value for name, value in pk_values.items()]


class ValidationMixin(PrimaryKeyMixin):
    """Validation logic - Layer 3."""

    def validate_field(self, field_name: str) -> None:
        """Validate a single field.

        Args:
            field_name: Name of the field to validate

        Raises:
            ValueError: If field does not exist
            ValidationError: If validation fails
        """
        if field_name not in self._get_field_names():
            raise ValueError(f"Field '{field_name}' does not exist")

        field_attr = getattr(self.__class__, field_name, None)
        if field_attr is not None and is_field_definition(field_attr):
            column = get_column_from_field(field_attr)
            validators = (
                column.info.get("_enhanced", {}).get("validators", []) if column is not None and column.info else []
            )
            if validators:
                value = getattr(self, field_name, None)
                try:
                    from .validators import validate_field_value

                    validated_value = validate_field_value(value, validators, field_name)
                    setattr(self, field_name, validated_value)
                except Exception as e:
                    raise ValidationError(str(e), field=field_name) from e

    def validate_all_fields(self, fields: list[str] | None = None) -> None:
        """Validate multiple fields efficiently.

        Args:
            fields: List of field names to validate, or None for all fields

        Raises:
            ValidationError: If any validation fails, with combined error messages
        """
        field_names = fields if fields is not None else self._get_field_names()
        errors = []
        for field_name in field_names:
            try:
                self.validate_field(field_name)
            except ValidationError as e:
                errors.append(e)
        if errors:
            error_messages = [str(e) for e in errors]
            raise ValidationError("; ".join(error_messages))


class DeferredLoadingMixin(ValidationMixin):
    """Deferred loading functionality - Layer 4."""

    def __init__(self):
        """Initialize deferred loading state."""
        super().__init__()
        self._state_manager.set("deferred_fields", set())
        self._state_manager.set("loaded_deferred_fields", set())
        self._state_manager.set("is_from_db", False)

    @property
    def _deferred_fields(self) -> set[str]:
        result = self._state_manager.get("deferred_fields", set())
        return result if isinstance(result, set) else set()

    @property
    def _loaded_deferred_fields(self) -> set[str]:
        result = self._state_manager.get("loaded_deferred_fields", set())
        return result if isinstance(result, set) else set()

    def get_deferred_fields(self) -> set[str]:
        """Get all deferred fields.

        Returns:
            Set of field names that are deferred
        """
        return self._deferred_fields.copy()

    def get_loaded_deferred_fields(self) -> set[str]:
        """Get loaded deferred fields.

        Returns:
            Set of deferred field names that have been loaded
        """
        return self._loaded_deferred_fields.copy()

    def is_field_deferred(self, field_name: str) -> bool:
        """Check if field is deferred.

        Args:
            field_name: Name of the field to check

        Returns:
            True if field is deferred
        """
        return field_name in self._deferred_fields

    def is_field_loaded(self, field_name: str) -> bool:
        """Check if deferred field is loaded.

        Args:
            field_name: Name of the field to check

        Returns:
            True if field is not deferred or has been loaded
        """
        if field_name not in self._deferred_fields:
            return True
        return field_name in self._loaded_deferred_fields

    def is_from_database(self) -> bool:
        """Check if instance was loaded from database.

        Returns:
            True if instance was loaded from database
        """
        result = self._state_manager.get("is_from_db", False)
        return bool(result)

    async def load_deferred_field(self, field_name: str) -> None:
        """Load a single deferred field.

        Args:
            field_name: Name of the field to load
        """
        await self.load_deferred_fields([field_name])

    async def load_deferred_fields(self, fields: list[str] | None = None) -> None:
        """Load multiple deferred fields efficiently.

        Args:
            fields: List of field names to load, or None for all deferred fields

        Raises:
            PrimaryKeyError: If primary key values are not set
        """
        table = self.get_table()

        pk_conditions = self._build_pk_conditions()
        if not all(value is not None for value in pk_conditions):
            raise PrimaryKeyError("Cannot load deferred fields without primary key")

        if fields is None:
            fields_to_load = self._deferred_fields - self._loaded_deferred_fields
        else:
            fields_to_load = set(fields) & self._deferred_fields - self._loaded_deferred_fields

        if not fields_to_load:
            return

        valid_fields = [f for f in fields_to_load if f in table.columns]
        if not valid_fields:
            return

        columns = [table.c[field] for field in valid_fields]
        stmt = select(*columns).where(and_(*pk_conditions))

        session = self.get_session()
        result = await session.execute(stmt)
        row = result.first()

        if row:
            loaded_fields = self._state_manager.get("loaded_deferred_fields", set())
            if isinstance(loaded_fields, set):
                for i, field in enumerate(valid_fields):
                    setattr(self, field, row[i])
                    loaded_fields.add(field)


class DataConversionMixin(DeferredLoadingMixin):
    """Data conversion functionality - Layer 5."""

    def to_dict(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        include_deferred: bool = False,
        safe_access: bool = True,
    ) -> dict[str, Any]:
        """Convert model instance to dictionary.

        Args:
            include: List of fields to include, or None for all fields
            exclude: List of fields to exclude
            include_deferred: Whether to include deferred fields
            safe_access: Whether to skip unloaded deferred fields safely

        Returns:
            Dictionary representation of the model instance
        """
        all_fields = set(self._get_field_names())

        if include is not None:
            fields = set(include) & all_fields
        else:
            fields = all_fields

        if exclude is not None:
            fields = fields - set(exclude)

        if not include_deferred:
            fields = fields - self._deferred_fields

        result = {}
        for field in fields:
            if safe_access and field in self._deferred_fields and field not in self._loaded_deferred_fields:
                continue
            try:
                result[field] = getattr(self, field)
            except AttributeError:
                if not safe_access:
                    raise
                continue

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any], validate: bool = True):
        """Create model instance from dictionary with validation.

        Args:
            data: Dictionary of field values
            validate: Whether to validate fields after creation

        Returns:
            New model instance created from dictionary data
        """
        all_fields = set(cls._get_field_names())
        filtered_data = {k: v for k, v in data.items() if k in all_fields}

        # Default values will be handled by __init__ method

        init_data = {}
        non_init_data = {}

        for field_name, value in filtered_data.items():
            field_attr = getattr(cls, field_name, None)
            if field_attr is not None and hasattr(field_attr, "get_codegen_params"):
                codegen_params = field_attr.get_codegen_params()
                if codegen_params.get("init", True):
                    init_data[field_name] = value
                else:
                    non_init_data[field_name] = value
            else:
                # For fields without codegen_params, check if it's an identity field
                if field_name == "id" and hasattr(field_attr, "column") and hasattr(field_attr.column, "autoincrement"):  # type: ignore[reportOptionalSubscript]
                    non_init_data[field_name] = value
                else:
                    init_data[field_name] = value

        instance = cls(**init_data)  # noqa

        for field_name, value in non_init_data.items():
            # Apply default value if value is None
            if value is None:
                default_value = instance._get_field_default_value(field_name)  # noqa
                if default_value is not None:
                    value = default_value
            setattr(instance, field_name, value)

        # Clear dirty fields since this is initial creation from dict
        dirty_fields = instance._state_manager.get("dirty_fields", set())
        if isinstance(dirty_fields, set):
            dirty_fields.clear()

        if validate:
            instance.validate_all_fields()

        return instance

    def _apply_default_values(self, kwargs: dict):
        """Apply default values for fields not provided in kwargs.

        Args:
            kwargs: Dictionary of provided field values (will be modified)
        """
        for field_name in self._get_field_names():
            if field_name not in kwargs or kwargs[field_name] is None:
                default_value = self._get_field_default_value(field_name)
                if default_value is not None:
                    kwargs[field_name] = default_value

    def _get_field_default_value(self, field_name: str):
        """Get default value for a field.

        Args:
            field_name: Name of the field

        Returns:
            Default value or None if no default
        """
        field_attr = getattr(self.__class__, field_name, None)
        if field_attr is None:
            return None

        # Priority: default_factory > SQLAlchemy default
        if hasattr(field_attr, "get_default_factory"):
            factory = field_attr.get_default_factory()
            if factory and callable(factory):
                return factory()

        if hasattr(field_attr, "default") and field_attr.default is not None:
            default_value = field_attr.default
            if callable(default_value):
                return default_value()
            else:
                return default_value

        return None


class FieldCacheMixin(DataConversionMixin):
    """Field caching and attribute access optimization - Layer 6."""

    @classmethod
    def _get_field_cache(cls):
        """Auto-initialize and cache field information.

        Returns:
            Dictionary containing categorized field information
        """
        cache_attr = "_cached_field_info"
        if not hasattr(cls, cache_attr):
            setattr(cls, cache_attr, cls._build_field_cache())
        return getattr(cls, cache_attr)

    @classmethod
    def _build_field_cache(cls):
        """Build field cache with error handling.

        Returns:
            Dictionary with field categories: deferred_fields, relationship_fields, regular_fields
        """
        cache = {"deferred_fields": set(), "relationship_fields": set(), "regular_fields": set()}

        try:
            if hasattr(cls, "__table__"):
                table = getattr(cls, "__table__", None)
                if table is not None:
                    for col_name in table.columns.keys():
                        cls._categorize_field(col_name, cache)

            if hasattr(cls, "_relationships"):
                relationships = getattr(cls, "_relationships", {})
                cache["relationship_fields"].update(relationships.keys())
        except Exception:  # noqa
            pass

        return cache

    @classmethod
    def _categorize_field(cls, field_name, cache):
        """Categorize a single field into cache.

        Args:
            field_name: Name of the field to categorize
            cache: Cache dictionary to update
        """
        try:
            attr = getattr(cls, field_name, None)
            if attr is not None and is_field_definition(attr):
                # Check if this is a relationship field
                if hasattr(attr, "_is_relationship") and attr._is_relationship:  # noqa
                    cache["relationship_fields"].add(field_name)
                    return

                # Handle database field
                column = get_column_from_field(attr)
                if column is not None and hasattr(column, "info") and column.info is not None:
                    performance_params = column.info.get("_performance", {})
                    if performance_params.get("deferred", False):
                        cache["deferred_fields"].add(field_name)
                    else:
                        cache["regular_fields"].add(field_name)
                else:
                    cache["regular_fields"].add(field_name)
        except (AttributeError, TypeError):
            cache["regular_fields"].add(field_name)

    @classmethod
    def _invalidate_field_cache(cls):
        """Manually invalidate field cache.

        Use this when field definitions change at runtime.
        """
        cache_attr = "_cached_field_info"
        if hasattr(cls, cache_attr):
            delattr(cls, cache_attr)

    def __setattr__(self, name: str, value):
        """Override setattr to handle relationship field assignments."""
        if hasattr(self, "_get_relationship_fields") and name in self._get_relationship_fields():
            self._handle_relationship_assignment(name, value)
        else:
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

    def __getattribute__(self, name: str):
        """Optimized attribute access using automatic field cache.

        Provides intelligent attribute access with proxy objects for
        deferred and relationship fields. Skips optimization for
        special attributes and methods to avoid recursion.

        Args:
            name: Attribute name to access

        Returns:
            Attribute value or proxy object
        """
        if name.startswith("_") or name in (
            "get_table",
            "load_deferred_fields",
            "validate_all_fields",
            "save",
            "delete",
            "refresh",
            "to_dict",
            "from_dict",
            "using",
            "is_field_deferred",
            "is_field_loaded",
            "get_deferred_fields",
            "_get_field_cache",
            "get_session",
            "validate_field",
            "load_deferred_field",
            "is_from_database",
            "_handle_relationship_assignment",
            "_get_relationship_fields",
        ):
            return super().__getattribute__(name)

        model_class = super().__getattribute__("__class__")
        field_cache = model_class._get_field_cache()  # noqa

        deferred_fields = field_cache.get("deferred_fields", set())
        if isinstance(deferred_fields, set) and name in deferred_fields:
            if (
                hasattr(self, "_state_manager")
                and self._state_manager.get("is_from_db", False)
                and name in self._deferred_fields
                and not self.is_field_loaded(name)
            ):
                proxy_cache = self._state_manager.get("proxy_cache", {})
                if isinstance(proxy_cache, dict) and name not in proxy_cache:
                    proxy_cache[name] = DeferredFieldProxy(self, name)
                    self._state_manager.set("proxy_cache", proxy_cache)
                if isinstance(proxy_cache, dict):
                    return proxy_cache[name]

        relationship_fields = field_cache.get("relationship_fields", set())
        if isinstance(relationship_fields, set) and name in relationship_fields:
            # Check cascade_relationships first (manually assigned values)
            if hasattr(self, "_state_manager"):
                cascade_relationships: dict = self._state_manager.get("cascade_relationships", {})  # type: ignore[reportAssignmentType]
                if name in cascade_relationships:
                    return cascade_relationships[name]

            # Check preloaded cache
            cache_name = f"_{name}_cache"
            try:
                if hasattr(self, cache_name):
                    cached_value = super().__getattribute__(cache_name)
                    if cached_value is not None:
                        return cached_value
            except AttributeError:
                pass

            # Only create proxy if relationship is not loaded
            proxy_cache = self._state_manager.get("proxy_cache", {})
            if isinstance(proxy_cache, dict) and name not in proxy_cache:
                proxy_cache[name] = RelationFieldProxy(self, name)
                self._state_manager.set("proxy_cache", proxy_cache)
            if isinstance(proxy_cache, dict):
                return proxy_cache[name]

        return super().__getattribute__(name)
