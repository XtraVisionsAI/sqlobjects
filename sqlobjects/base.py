from typing import Any, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session
from sqlalchemy.orm import DeclarativeBase

from .config import ModelConfig, get_model_config, process_model_config
from .exceptions import ValidationError, ValidationErrorCollector
from .objects import ObjectsDescriptor
from .session import SessionContextManager
from .signals import Operation, SignalContext, SignalMixin, emit_signals


__all__ = [
    "ObjectModel",
    "ModelProxy",
]


# Type variable for ModelMixin
M = TypeVar("M", bound="ModelMixin")


class ModelMixin(SignalMixin):
    """Mixin class that adds instance methods and validation capabilities to models."""

    # ========== Private Interface Methods ==========

    def _get_session(self) -> AsyncSession:
        """Get the effective session for database operations."""
        raise NotImplementedError("Subclasses must implement _get_session()")

    def _get_model_class(self) -> type:
        """Get the model class for this instance."""
        raise NotImplementedError("Subclasses must implement _get_model_class()")

    def _get_instance(self):
        """Get the actual model instance."""
        raise NotImplementedError("Subclasses must implement _get_instance()")

    # ========== Unified Signal and Validation Methods ==========

    async def _emit_signal(self, timing: str, context: SignalContext):
        """Emit signal using the actual instance."""
        instance = self._get_instance()
        if hasattr(instance, "_emit_signal") and hasattr(SignalMixin, "_emit_signal"):
            await SignalMixin._emit_signal(instance, timing, context)

    def _get_field_names(self) -> list[str]:
        """Get field names from the actual instance."""
        instance = self._get_instance()
        if hasattr(instance, "__table__"):
            return [col.name for col in instance.__table__.columns]
        return []

    def _get_column_validators(self, field_name: str) -> list:
        """Get column validators from the actual instance."""
        model_class = self._get_model_class()
        column_validators = []

        if hasattr(model_class, field_name):
            field_attr = getattr(model_class, field_name)

            if hasattr(field_attr, "_sqlobjects_validators"):
                column_validators = field_attr._sqlobjects_validators or []  # noqa
            elif hasattr(field_attr, "column") and hasattr(field_attr.column, "info"):
                if "_validators" in field_attr.column.info:
                    column_validators = field_attr.column.info["_validators"]
            elif hasattr(field_attr, "property"):
                if hasattr(field_attr.property, "columns"):
                    for col in field_attr.property.columns:
                        if hasattr(col, "info") and "_validators" in col.info:
                            column_validators = col.info["_validators"]
                            break
                elif hasattr(field_attr.property, "info") and "_validators" in field_attr.property.info:
                    column_validators = field_attr.property.info["_validators"]

        return column_validators

    def _temporarily_disable_sqlalchemy_validators(self) -> dict[str, Any]:
        """Temporarily disable SQLAlchemy validators on the model class."""
        model_class = self._get_model_class()
        original_validators = {}

        for attr_name in dir(model_class):
            attr = getattr(model_class, attr_name)
            if hasattr(attr, "__validates__"):
                original_validators[attr_name] = attr
                setattr(model_class, attr_name, lambda _, key, value: value)

        return original_validators

    def _restore_sqlalchemy_validators(self, original_validators: dict[str, Any]) -> None:
        """Restore SQLAlchemy validators on the model class."""
        model_class = self._get_model_class()
        for attr_name, original_method in original_validators.items():
            setattr(model_class, attr_name, original_method)

    # ========== Using Method ==========

    def using(self, db_or_session: str | AsyncSession) -> "ModelProxy":
        """Return a proxy bound to specific database/session."""
        return ModelProxy(self._get_instance(), db_or_session)

    # ========== Validation Methods ==========

    def validate_fields(self, fields: list[str] | None = None) -> None:
        """Validate field-level data using registered validators.

        Args:
            fields: List of specific fields to validate, if None validates all fields

        Raises:
            ValidationError: If any field validation fails
        """
        error_collector = ValidationErrorCollector()
        instance = self._get_instance()
        model_class = self._get_model_class()

        # Determine which fields to validate
        field_names = fields if fields is not None else self._get_field_names()

        # Validate each field using its registered validators
        for field_name in field_names:
            # Skip fields that don't exist on the model
            if not hasattr(instance, field_name):
                continue

            # Get validators added through add_field_validator class method
            class_validators = getattr(model_class, f"_validators_{field_name}", [])

            # Get validators passed through column() function
            column_validators = self._get_column_validators(field_name)

            # Combine all validators for this field
            all_validators = class_validators + column_validators

            if all_validators:
                value = getattr(instance, field_name, None)
                for validator in all_validators:
                    try:
                        validator(value)
                    except ValidationError as e:
                        # Add the error message directly without extra formatting
                        error_collector.add_error(field_name, e.message)
                    except Exception as e:
                        # Handle other types of exceptions
                        error_collector.add_error(field_name, f"Validation error: {e}")

        error_collector.raise_if_errors()

    def validate(self) -> None:
        """Model-level validation hook that subclasses can override.

        This method is called during full validation to perform custom
        business logic validation that spans multiple fields or requires
        complex validation rules.

        Raises:
            ValidationError: If model-level validation fails
        """
        # Default implementation - subclasses can override
        # This method should be overridden by subclasses to provide custom validation
        pass

    def validate_all(self, fields: list[str] | None = None) -> None:
        """Execute complete validation including both field-level and model-level checks.

        Args:
            fields: List of specific fields to validate, if None validates all fields

        Raises:
            ValidationError: If any validation fails
        """
        # 1. Execute field-level validation
        self.validate_fields(fields)

        # 2. Execute model-level validation (only when validating all fields)
        if fields is None:
            try:
                self.validate()
            except ValidationError:
                raise
            except Exception as e:
                # Convert other exceptions to ValidationError for consistency
                raise ValidationError(f"Model validation failed: {e}") from e

    @classmethod
    def add_field_validator(cls, field_name: str, validator) -> None:
        """Add a validator function for the specified field.

        Args:
            field_name: Name of the field to add validator for
            validator: Validator function that takes a value and raises ValidationError if invalid
        """
        validator_attr = f"_validators_{field_name}"
        if not hasattr(cls, validator_attr):
            setattr(cls, validator_attr, [])
        getattr(cls, validator_attr).append(validator)

    @classmethod
    def setup_validators(cls) -> None:
        """Setup field validators for the model.

        This method should be overridden by subclasses to register field validators
        using the add_field_validator method. It's automatically called during
        class initialization.

        Examples:
            >>> class User(ObjectModel):
            ...     username: Column[str] = column(type="string", length=50)
            ...     email: Column[str] = column(type="string", length=100)
            ...
            ...     @classmethod
            ...     def setup_validators(cls):
            ...         cls.add_field_validator("username", cls.validate_username)
            ...         cls.add_field_validator("email", cls.validate_email)
            ...
            ...     @staticmethod
            ...     def validate_username(value):
            ...         if not value or len(value) < 3:
            ...             raise ValidationError("Username must be at least 3 characters")
            ...
            ...     @staticmethod
            ...     def validate_email(value):
            ...         if not value or "@" not in value:
            ...             raise ValidationError("Invalid email format")
        """
        pass

    @classmethod
    def _setup_validators(cls) -> None:
        """Internal method to call setup_validators if it's overridden.

        This method is called automatically during class initialization to
        ensure that field validators are properly registered.
        """
        # Only call setup_validators if it's been overridden by the subclass
        if hasattr(cls, "setup_validators") and cls.setup_validators is not ModelMixin.setup_validators:
            cls.setup_validators()

    # ========== Instance Operations ==========
    @emit_signals(Operation.SAVE)
    async def save(self, validate: bool = True):
        """Validate and save the model instance to the database.

        Args:
            validate: Whether to execute all validation (both SQLObjects and SQLAlchemy validators)

        Returns:
            The saved model instance

        Raises:
            ValidationError: If validation fails (when validate=True)
            IntegrityError: If database constraints are violated
            DatabaseError: If database connection or transaction fails
            AttributeError: If model fields are not properly defined
        """
        session = self._get_session()
        instance = self._get_instance()

        if validate:
            self.validate_all()

        original_validators: dict[str, Any] = {}
        if not validate:
            original_validators = self._temporarily_disable_sqlalchemy_validators()

        try:
            session.add(instance)
            await session.flush()
        finally:
            if not validate and original_validators:
                self._restore_sqlalchemy_validators(original_validators)

        return self

    @emit_signals(Operation.DELETE)
    async def delete(self):
        """Delete this model instance from the database.

        Raises:
            IntegrityError: If foreign key constraints prevent deletion
            DatabaseError: If database connection or transaction fails
            AttributeError: If the instance is not properly initialized
        """
        session = self._get_session()
        instance = self._get_instance()

        await session.delete(instance)
        await session.flush()

    async def refresh(self):
        """Refresh this instance with the latest data from the database.

        Returns:
            The refreshed model instance
        """
        session = self._get_session()
        instance = self._get_instance()

        await session.flush()
        await session.refresh(instance)
        return self

    async def refresh_from_db(self, fields: list[str] | None = None):
        """Refresh specific fields from the database without affecting other fields.

        Args:
            fields: List of specific fields to refresh, if None refreshes all fields

        Returns:
            The refreshed model instance
        """
        session = self._get_session()
        instance = self._get_instance()
        model_class = self._get_model_class()

        pk_columns = list(model_class.__table__.primary_key)  # noqa
        pk_conditions = {col.name: getattr(instance, col.name) for col in pk_columns}

        # Always select specific columns to avoid identity map issues
        if fields:
            # Select only the specified fields
            columns_to_select = [getattr(model_class, field) for field in fields]
        else:
            # Select all columns
            columns_to_select = [getattr(model_class, col.name) for col in model_class.__table__.columns]  # noqa

        query = select(*columns_to_select)
        conditions = [getattr(model_class, k) == v for k, v in pk_conditions.items()]
        query = query.where(and_(*conditions))

        # Execute query and get fresh data
        result = await session.execute(query)
        fresh_data = result.first()

        if fresh_data:
            if fields:
                # Update only requested fields
                for i, field in enumerate(fields):
                    setattr(instance, field, fresh_data[i])
            else:
                # Update all fields
                all_columns = [col.name for col in model_class.__table__.columns]  # noqa
                for i, col_name in enumerate(all_columns):
                    setattr(instance, col_name, fresh_data[i])

        return self

    # ========== Data Conversion ==========

    def to_dict(self, include: list[str] | None = None, exclude: list[str] | None = None) -> dict[str, Any]:
        """Convert the model instance to a dictionary, similar to pydantic's model_dump method.

        Args:
            include: List of fields to include, if None includes all fields
            exclude: List of fields to exclude

        Returns:
            Dictionary containing the model data
        """
        instance = self._get_instance()
        model_class = self._get_model_class()

        if not hasattr(model_class, "__table__"):
            return {}

        all_fields = {col.name for col in model_class.__table__.columns}  # noqa

        if include is not None:
            fields = set(include) & all_fields
        else:
            fields = all_fields

        if exclude is not None:
            fields = fields - set(exclude)

        result = {}
        for field in fields:
            value = getattr(instance, field, None)
            result[field] = value

        return result


class ModelProxy(ModelMixin):
    """Proxy class that wraps a model instance with specific session binding."""

    def __init__(self, instance, db_or_session: str | AsyncSession):
        self._instance = instance
        self._db_or_session = db_or_session
        self._session_attached = False

    # ========== Private Interface Implementation ==========

    def _get_session(self) -> AsyncSession:
        if isinstance(self._db_or_session, str):
            session = SessionContextManager.get_session(self._db_or_session)
        else:
            session = self._db_or_session

        self._ensure_session_attachment(session)
        return session

    def _get_model_class(self) -> type:
        return self._instance.__class__

    def _get_instance(self):
        return self._instance

    # ========== Session Management ==========

    def _ensure_session_attachment(self, session: AsyncSession) -> None:
        """Ensure instance is properly attached to the specified session."""
        if self._session_attached:
            return

        current_session = async_object_session(self._instance)

        if current_session is None:
            session.add(self._instance)
        elif current_session is not session:
            self._handle_session_migration(current_session, session)

        self._session_attached = True

    def _handle_session_migration(self, old_session: AsyncSession, new_session: AsyncSession) -> None:
        """Handle instance migration between different sessions."""
        try:
            old_session.expunge(self._instance)
        except Exception:  # noqa
            pass

        new_session.add(self._instance)

    # ========== Attribute Proxy ==========

    def __getattr__(self, name):
        """Proxy attribute access to the wrapped instance."""
        return getattr(self._instance, name)

    def __setattr__(self, name, value):
        """Proxy attribute setting to the wrapped instance."""
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._instance, name, value)


class ObjectModel(DeclarativeBase, ModelMixin):
    """Base model class with configuration support and common functionality."""

    __abstract__ = True

    # ========== Private Interface Implementation ==========

    def _get_session(self) -> AsyncSession:
        return SessionContextManager.get_session()

    def _get_model_class(self) -> type:
        return self.__class__

    def _get_instance(self):
        return self

    def __init_subclass__(cls, **kwargs):
        """Process subclass initialization with configuration parsing and setup.

        This method is called when a new model class is defined and handles:
        - Configuration parsing from class attributes and Config inner class
        - Table name and metadata setup
        - Objects manager initialization
        - Validator setup

        Args:
            **kwargs: Additional keyword arguments passed to parent classes
        """
        cls._process_config()
        cls._setup_validators()
        super().__init_subclass__(**kwargs)

    # ========== Configuration Processing ==========

    @classmethod
    def _process_config(cls):
        """Process and apply model configuration using the global configuration manager."""
        _, is_abstract = process_model_config(cls)

        # Setup objects manager for non-abstract models
        if not is_abstract and not hasattr(cls, "objects"):
            cls.objects = ObjectsDescriptor(cls)

    # ========== Metadata Access ==========

    @classmethod
    def get_config(cls) -> ModelConfig:
        """Get the cached configuration for this model class.

        Returns:
            ModelConfig object containing all configuration settings
        """
        return get_model_config(cls)

    @classmethod
    def get_table_name(cls) -> str:
        """Get the database table name for this model.

        Returns:
            Table name from configuration
        """
        config = cls.get_config()
        return config.table_name

    @classmethod
    def get_verbose_name(cls) -> str:
        """Get the human-readable name for this model.

        Returns:
            Verbose name from configuration
        """
        config = cls.get_config()
        return config.verbose_name

    @classmethod
    def get_verbose_name_plural(cls) -> str:
        """Get the human-readable plural name for this model.

        Returns:
            Plural verbose name from configuration
        """
        config = cls.get_config()
        return config.verbose_name_plural

    @classmethod
    def get_description(cls) -> str | None:
        """Get the description for this model.

        Returns:
            Model description from configuration or None
        """
        config = cls.get_config()
        return config.description

    @classmethod
    def get_metadata(cls) -> dict[str, str | None]:
        """Get all model metadata as a dictionary.

        Returns:
            Dictionary containing verbose_name, verbose_name_plural, and description
        """
        config = cls.get_config()
        return {
            "verbose_name": config.verbose_name,
            "verbose_name_plural": config.verbose_name_plural,
            "description": config.description,
        }

    # ========== Data Conversion ==========

    @classmethod
    def from_dict(cls: type[M], data: dict[str, Any], validate: bool = True) -> M:
        """Create a model instance from a dictionary, similar to pydantic's model_validate method.

        Args:
            data: Dictionary containing model data
            validate: Whether to execute validation

        Returns:
            Created model instance

        Raises:
            ValidationError: If validation fails and validate=True
        """
        if not hasattr(cls, "__table__"):
            return cls()

        all_fields = {col.name for col in cls.__table__.columns}  # type: ignore
        filtered_data = {k: v for k, v in data.items() if k in all_fields}

        for col in cls.__table__.columns:  # type: ignore
            if col.name not in filtered_data and col.default is not None:
                if col.default.is_scalar:
                    filtered_data[col.name] = col.default.arg

        instance = cls(**filtered_data)

        if validate:
            instance.validate_all()

        return instance
