from typing import Any, TypeVar

from sqlalchemy import (
    and_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from .config import ConfigParser, ModelConfig
from .exceptions import ValidationError, ValidationErrorCollector
from .objects import ObjectsDescriptor
from .session import SessionContextManager
from .signals import Operation, SignalContext, SignalMixin
from .utils.naming import to_snake_case
from .utils.pattern import pluralize


__all__ = [
    "ObjectModel",
]


# Type variable for ModelMixin
M = TypeVar("M", bound="ModelMixin")


class ModelMixin(SignalMixin):
    """Mixin class that adds instance methods and validation capabilities to models."""

    # ========== Validation Methods ==========

    def validate_fields(self, fields: list[str] | None = None) -> None:
        """Validate field-level data using registered validators.

        Args:
            fields: List of specific fields to validate, if None validates all fields

        Raises:
            ValidationError: If any field validation fails
        """
        error_collector = ValidationErrorCollector()

        # Determine which fields to validate
        field_names = fields if fields is not None else self._get_field_names()

        # Validate each field using its registered validators
        for field_name in field_names:
            # Skip fields that don't exist on the model
            if not hasattr(self, field_name):
                continue

            # Get validators added through add_field_validator class method
            class_validators = getattr(self.__class__, f"_validators_{field_name}", [])

            # Get validators passed through column() function
            column_validators = self._get_column_validators(field_name)

            # Combine all validators for this field
            all_validators = class_validators + column_validators

            if all_validators:
                value = getattr(self, field_name, None)
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

    def _get_field_names(self) -> list[str]:
        """Get all field names defined on the model.

        This method extracts field names from the SQLAlchemy table metadata,
        providing a list of all columns that can be validated. It's used
        internally by the validation system to determine which fields to
        validate when no specific field list is provided.

        The method handles:
        - Models with __table__ attribute (normal case)
        - Models without __table__ (abstract models, edge cases)
        - Empty field lists for models without columns

        Returns:
            List of field names from the model's table columns, or empty list
            if the model has no table (e.g., abstract models)

        Examples:
            >>> class User(ObjectModel):
            ...     id: Column[int] = int_column(primary_key=True)
            ...     name: Column[str] = str_column()
            >>> user = User()
            >>> user._get_field_names()  # ['id', 'name']
        """
        if hasattr(self, "__table__"):
            return [col.name for col in self.__table__.columns]  # type: ignore
        return []

    def _get_column_validators(self, field_name: str) -> list:
        """Get validators that were registered for a field through the column() function.

        This method retrieves validators that were attached to a field during
        field definition using the validators parameter in column() or shortcut
        functions like str_column(validators=[...]).

        The method checks multiple locations where validators might be stored:
        1. Direct attribute storage (_sqlobjects_validators)
        2. SQLAlchemy column info metadata (_validators key)
        3. Handles cases where validators are not found

        Args:
            field_name: Name of the field to get validators for

        Returns:
            List of validator functions for the field, or empty list if no
            validators are found for the specified field

        Examples:
            >>> class User(ObjectModel):
            ...     email: Column[str] = str_column(validators=[validate_email()])
            >>> user = User()
            >>> validators = user._get_column_validators("email")
            >>> len(validators)  # 1 (the email validator)
        """
        column_validators = []

        if hasattr(self.__class__, field_name):
            field_attr = getattr(self.__class__, field_name)

            # Method 1: Validators stored directly on the field attribute
            if hasattr(field_attr, "_sqlobjects_validators"):
                column_validators = field_attr._sqlobjects_validators or []  # noqa

            # Method 2: Validators stored in SQLAlchemy MappedColumn info
            elif hasattr(field_attr, "column") and hasattr(field_attr.column, "info"):
                if "_validators" in field_attr.column.info:
                    column_validators = field_attr.column.info["_validators"]

            # Method 3: Validators stored in SQLAlchemy column info (legacy support)
            elif hasattr(field_attr, "property"):
                # For MappedColumn, check the column info directly
                if hasattr(field_attr.property, "columns"):
                    for col in field_attr.property.columns:
                        if hasattr(col, "info") and "_validators" in col.info:
                            column_validators = col.info["_validators"]
                            break
                # For direct column access
                elif hasattr(field_attr.property, "info") and "_validators" in field_attr.property.info:
                    column_validators = field_attr.property.info["_validators"]

        return column_validators

    def validate(self) -> None:
        """Model-level validation hook that subclasses can override.

        This method is called during full validation to perform custom
        business logic validation that spans multiple fields or requires
        complex validation rules.

        Raises:
            ValidationError: If model-level validation fails
        """
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
        if cls.setup_validators is not ObjectModel.setup_validators:
            cls.setup_validators()

    # ========== Instance Operations ==========
    async def save(
        self,
        session: AsyncSession | None = None,
        commit: bool = False,
        validate: bool = True,
    ):
        """Validate and save the model instance to the database.

        Args:
            session: Database session to use
            commit: Whether to commit the transaction
            validate: Whether to execute all validation (both SQLObjects and SQLAlchemy validators)

        Returns:
            The saved model instance

        Raises:
            ValidationError: If validation fails (when validate=True)
            IntegrityError: If database constraints are violated
            DatabaseError: If database connection or transaction fails
            AttributeError: If model fields are not properly defined
        """
        session = session or SessionContextManager.get_session()

        if validate:
            self.validate_all()

        context = SignalContext(operation=Operation.SAVE, session=session, model_class=self.__class__, instance=self)
        await self._emit_signal("before", context)

        original_validators: dict[str, Any] = {}
        if not validate:
            original_validators = self._temporarily_disable_sqlalchemy_validators()

        try:
            session.add(self)
            if commit:
                await session.commit()
                await session.refresh(self)
            else:
                await session.flush()
        finally:
            if not validate and original_validators:
                self._restore_sqlalchemy_validators(original_validators)
            await self._emit_signal("after", context)

        return self  # noqa

    async def delete(self, session: AsyncSession | None = None, commit: bool = False):
        """Delete this model instance from the database.

        Args:
            session: Database session to use
            commit: Whether to commit the transaction

        Raises:
            IntegrityError: If foreign key constraints prevent deletion
            DatabaseError: If database connection or transaction fails
            AttributeError: If the instance is not properly initialized
        """
        session = session or SessionContextManager.get_session()

        context = SignalContext(operation=Operation.DELETE, session=session, model_class=self.__class__, instance=self)
        await self._emit_signal("before", context)

        await session.delete(self)
        if commit:
            await session.commit()
        else:
            await session.flush()

        await self._emit_signal("after", context)

    async def refresh(self, session: AsyncSession | None = None):
        """Refresh this instance with the latest data from the database.

        Args:
            session: Database session to use

        Returns:
            The refreshed model instance
        """
        session = session or SessionContextManager.get_session()
        await session.flush()
        await session.refresh(self)
        return self

    async def refresh_from_db(self, fields: list[str] | None = None, session: AsyncSession | None = None):
        """Refresh specific fields from the database without affecting other fields.

        Args:
            fields: List of specific fields to refresh, if None refreshes all fields
            session: Database session to use

        Returns:
            The refreshed model instance
        """
        session = session or SessionContextManager.get_session()

        pk_columns = list(self.__table__.primary_key)  # type: ignore
        pk_conditions = {col.name: getattr(self, col.name) for col in pk_columns}

        # Always select specific columns to avoid identity map issues
        if fields:
            # Select only the specified fields
            columns_to_select = [getattr(self.__class__, field) for field in fields]
        else:
            # Select all columns
            columns_to_select = [getattr(self.__class__, col.name) for col in self.__table__.columns]  # type: ignore

        query = select(*columns_to_select)
        conditions = [getattr(self.__class__, k) == v for k, v in pk_conditions.items()]
        query = query.where(and_(*conditions))

        # Execute query and get fresh data
        result = await session.execute(query)
        fresh_data = result.first()

        if fresh_data:
            if fields:
                # Update only requested fields
                for i, field in enumerate(fields):
                    setattr(self, field, fresh_data[i])
            else:
                # Update all fields
                all_columns = [col.name for col in self.__table__.columns]  # type: ignore
                for i, col_name in enumerate(all_columns):
                    setattr(self, col_name, fresh_data[i])

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
        if not hasattr(self, "__table__"):
            return {}

        all_fields = {col.name for col in self.__table__.columns}  # type: ignore

        if include is not None:
            fields = set(include) & all_fields
        else:
            fields = all_fields

        if exclude is not None:
            fields = fields - set(exclude)

        result = {}
        for field in fields:
            value = getattr(self, field, None)
            result[field] = value

        return result

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

    # ========== Private Helper Methods ==========
    def _temporarily_disable_sqlalchemy_validators(self) -> dict[str, Any]:
        """Temporarily disable SQLAlchemy validators when validation is disabled.

        This method finds all @validates decorated methods on the model class
        and temporarily replaces them with no-op functions. This is used when
        save(validate=False) is called to bypass all validation including
        SQLAlchemy's built-in validators.

        The method works by:
        1. Scanning the class for methods with __validates__ attribute
        2. Storing references to original validator methods
        3. Replacing them with lambda functions that return values unchanged
        4. Returning the original methods for later restoration

        Returns:
            Dictionary mapping validator method names to their original implementations
            for later restoration via _restore_sqlalchemy_validators()

        Note:
            This is an internal method used by the save() operation and should not
            be called directly. Always use save(validate=False) instead.

        Examples:
            >>> # Internal usage during save(validate=False)
            >>> original_validators = instance._temporarily_disable_sqlalchemy_validators()
            >>> # ... perform database operation ...
            >>> instance._restore_sqlalchemy_validators(original_validators)
        """
        original_validators = {}

        # Scan all class attributes for SQLAlchemy validators
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name)
            # Check if attribute has __validates__ (SQLAlchemy validator marker)
            if hasattr(attr, "__validates__"):
                # Store original validator for later restoration
                original_validators[attr_name] = attr
                # Replace with no-op function that just returns the value unchanged
                setattr(self.__class__, attr_name, lambda _, key, value: value)

        return original_validators

    def _restore_sqlalchemy_validators(self, original_validators: dict[str, Any]) -> None:
        """Restore SQLAlchemy validators to their original implementations.

        This method restores SQLAlchemy validator methods that were temporarily
        disabled by _temporarily_disable_sqlalchemy_validators(). It ensures
        that the model class returns to its normal validation state after
        a save(validate=False) operation.

        The restoration process:
        1. Iterates through the provided original validators dictionary
        2. Restores each validator method to its original implementation
        3. Ensures the class validation behavior returns to normal

        Args:
            original_validators: Dictionary mapping validator method names to their
                               original implementations, as returned by
                               _temporarily_disable_sqlalchemy_validators()

        Note:
            This is an internal method used by the save() operation and should not
            be called directly. It's automatically called in the finally block
            of save() operations to ensure validators are always restored.

        Examples:
            >>> # Internal usage during save(validate=False)
            >>> original_validators = instance._temporarily_disable_sqlalchemy_validators()
            >>> try:
            ...     # ... perform database operation ...
            ... finally:
            ...     instance._restore_sqlalchemy_validators(original_validators)
        """
        # Restore each validator method to its original implementation
        for attr_name, original_method in original_validators.items():
            setattr(self.__class__, attr_name, original_method)


class ObjectModel(DeclarativeBase, ModelMixin):
    """Base model class with configuration support and common functionality."""

    __abstract__ = True
    _config_cache: dict[type, ModelConfig] = {}

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
        """Process and apply model configuration from class attributes and Config inner class.

        This method:
        1. Parses configuration from class attributes
        2. Parses configuration from Config inner class (higher priority)
        3. Merges configurations with proper precedence
        4. Applies configuration to the model class
        5. Sets up objects manager for non-abstract models
        """
        parser = ConfigParser()
        configs = [parser.parse_class_attributes(cls)]

        config_class = getattr(cls, "Config", None)
        if config_class:
            configs.append(parser.parse_config_class(config_class))

        merged_config = parser.merge_configs(*configs) if configs else ModelConfig()
        is_abstract = ("__abstract__" in cls.__dict__ and cls.__dict__["__abstract__"]) or merged_config.abstract

        if is_abstract:
            cls._config_cache[cls] = merged_config
            return

        cls._config_cache[cls] = merged_config
        cls._apply_config(merged_config)

        if not is_abstract and not hasattr(cls, "objects"):
            cls.objects = ObjectsDescriptor(cls)

    @classmethod
    def _apply_config(cls, config: ModelConfig):
        """Apply parsed configuration to the model class.

        This method takes a ModelConfig object and applies its settings to the class:
        - Sets table name if specified
        - Configures abstract flag
        - Sets default ordering
        - Builds __table_args__ with indexes, constraints, and database options

        Args:
            config: Parsed model configuration to apply
        """
        # Set table name - use config, existing __tablename__, or Rails-style pluralized class name
        if config.table_name:
            cls.__tablename__ = config.table_name
        elif not hasattr(cls, "__tablename__"):
            snake_case = to_snake_case(cls.__name__)
            cls.__tablename__ = pluralize(snake_case)

        if config.abstract:
            cls.__abstract__ = True

        if config.ordering:
            cls._default_ordering = config.ordering

        table_args = []
        existing_args = getattr(cls, "__table_args__", ())
        if existing_args:
            for arg in existing_args:
                if not isinstance(arg, dict):
                    table_args.append(arg)

        table_args.extend(config.indexes)
        table_args.extend(config.constraints)

        if config.db_options:
            db_dict = {}
            for db_name, options in config.db_options.items():
                if db_name == "generic":
                    db_dict.update(options)
                else:
                    for key, value in options.items():
                        db_dict[f"{db_name}_{key}"] = value
            if db_dict:
                table_args.append(db_dict)

        if table_args:
            cls.__table_args__ = tuple(table_args)

    # ========== Metadata Access ==========
    @classmethod
    def get_config(cls) -> ModelConfig:
        """Get the cached configuration for this model class.

        Returns:
            ModelConfig object containing all configuration settings
        """
        return cls._config_cache.get(cls, ModelConfig())

    @classmethod
    def get_table_name(cls) -> str:
        """Get the database table name for this model.

        Returns:
            Table name from configuration, __tablename__ attribute, or Rails-style pluralized class name
        """
        config = cls.get_config()

        # 1. 优先使用配置中的 table_name
        if config.table_name:
            return config.table_name

        # 2. 其次使用 __tablename__ 属性
        if hasattr(cls, "__tablename__"):
            return cls.__tablename__

        # 3. 使用Rails风格的复数化类名作为默认值
        snake_case = to_snake_case(cls.__name__)
        return pluralize(snake_case)

    @classmethod
    def get_verbose_name(cls) -> str:
        """Get the human-readable name for this model.

        Returns:
            Verbose name from configuration or class name
        """
        config = cls.get_config()
        return config.verbose_name or cls.__name__

    @classmethod
    def get_verbose_name_plural(cls) -> str:
        """Get the human-readable plural name for this model.

        Returns:
            Plural verbose name from configuration or verbose name with 's' suffix
        """
        config = cls.get_config()
        return config.verbose_name_plural or f"{cls.get_verbose_name()}s"

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
        return {
            "verbose_name": cls.get_verbose_name(),
            "verbose_name_plural": cls.get_verbose_name_plural(),
            "description": cls.get_description(),
        }
