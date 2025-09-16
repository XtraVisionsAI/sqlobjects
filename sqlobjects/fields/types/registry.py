import inspect
from typing import Any, Callable, NotRequired, TypedDict

from sqlalchemy.sql.sqltypes import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    Enum,
    Float,
    Integer,
    Interval,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    Uuid,
)
from sqlalchemy.types import TypeEngine

from .comparators import (
    BooleanComparator,
    DateTimeComparator,
    DefaultComparator,
    IntegerComparator,
    JSONComparator,
    NumericComparator,
    StringComparator,
)


class Auto(TypeEngine):
    """Automatic type inference placeholder for SQLAlchemy columns.

    Special type that indicates the actual type should be inferred from
    the Python type annotation or default value. Used as a placeholder
    during field definition and replaced with concrete type during
    model processing.

    Example:
        # Type inferred from annotation
        name: Column[str] = column()  # Uses Auto(), inferred as String
        age: Column[int] = column()   # Uses Auto(), inferred as Integer
    """

    def __init__(self):
        """Initialize Auto type instance.

        Creates a placeholder type that will be replaced during model processing
        with the appropriate concrete SQLAlchemy type.
        """
        super().__init__()


class TypeArgument(TypedDict):
    """Type argument definition for SQLAlchemy type constructor parameters.

    Defines metadata for a single constructor parameter of a SQLAlchemy type,
    including validation rules and transformation functions.

    Attributes:
        name: Parameter name in the constructor
        type: Expected Python type for the parameter
        required: Whether the parameter is required
        default: Default value if parameter is not provided
        transform: Optional function to transform parameter value
        positional: Whether parameter can be passed positionally
    """

    name: str
    type: type[Any]
    required: bool
    default: Any
    transform: NotRequired[Callable[[Any], Any]]
    positional: NotRequired[bool]


class TypeConfig(TypedDict):
    """Type configuration for registry storage and retrieval.

    Internal storage format for type definitions in the TypeRegistry.

    Attributes:
        sqlalchemy_type: SQLAlchemy type class
        comparator_class: Comparator class for database functions
        default_params: Default construction parameters
        arguments: Constructor parameter definitions
    """

    sqlalchemy_type: type[Any]
    comparator_class: type[Any]
    default_params: dict[str, Any]
    arguments: list[TypeArgument]


def _extract_constructor_params(type_class: type[Any]) -> list[TypeArgument]:
    """Extract constructor parameters from SQLAlchemy type class.

    Uses Python's inspect module to analyze the __init__ method signature
    and create TypeArgument definitions for each parameter.

    Args:
        type_class: SQLAlchemy type class to analyze

    Returns:
        List of TypeArgument definitions for constructor parameters

    Note:
        Returns empty list if inspection fails to ensure graceful degradation.
    """
    try:
        sig = inspect.signature(type_class.__init__)
        arguments = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            arguments.append(
                {
                    "name": param_name,
                    "type": Any,
                    "required": param.default == inspect.Parameter.empty,
                    "default": param.default if param.default != inspect.Parameter.empty else None,
                }
            )
        return arguments
    except Exception:  # noqa
        return []


def _get_type_params(type_config: TypeConfig, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract and validate type construction parameters from user input.

    Processes user-provided kwargs to extract parameters relevant to the
    SQLAlchemy type constructor, applies transformations, and sets defaults.

    Args:
        type_config: Type configuration from registry
        kwargs: User-provided parameters

    Returns:
        Dictionary of validated parameters for type construction

    Note:
        Only includes parameters defined in type_config.arguments.
        Applies transformation functions if specified in argument definitions.
    """
    type_params = {}
    type_param_names = {arg["name"] for arg in type_config["arguments"]}

    for key, value in kwargs.items():
        if key in type_param_names:
            arg_def = next(arg for arg in type_config["arguments"] if arg["name"] == key)
            if "transform" in arg_def and arg_def["transform"]:
                value = arg_def["transform"](value)
            type_params[key] = value

    # Apply default values
    for arg in type_config["arguments"]:
        if arg["name"] not in type_params and not arg["required"] and arg["default"] is not None:
            default_value = arg["default"]
            if "transform" in arg and arg["transform"]:
                default_value = arg["transform"](default_value)
            type_params[arg["name"]] = default_value

    return type_params


def _transform_array_item_type(item_type: str | type[Any]) -> type[Any]:
    """Transform array item_type from string name to SQLAlchemy type instance.

    Converts string type names (like 'string', 'integer') to actual SQLAlchemy
    type instances for use in ARRAY type construction.

    Args:
        item_type: String type name or SQLAlchemy type class

    Returns:
        SQLAlchemy type instance for array items

    Raises:
        ValueError: If string type name is not registered in type registry
    """
    if isinstance(item_type, str):
        type_config = _registry.get_type_config(item_type)
        if type_config:
            return type_config["sqlalchemy_type"]()
        else:
            raise ValueError(f"Unknown array item type: {item_type}")
    return item_type


class TypeRegistry:
    """Registry for SQLAlchemy types and comparator mappings.

    Central registry that manages the mapping between string type names
    and SQLAlchemy type classes, along with their associated comparator
    classes for database function support.

    Features:
    - Type registration with aliases
    - Automatic constructor parameter extraction
    - Enhanced type creation with comparators
    - Lazy initialization of built-in types

    Example:
        registry = TypeRegistry()
        registry.register_type(String, 'string', StringComparator)
        type_instance = registry.create_enhanced_type('string', length=100)
    """

    def __init__(self):
        """Initialize empty type registry.

        Creates an empty registry that will be populated with built-in types
        on first access. Uses lazy initialization for better startup performance.
        """
        self._type_configs: dict[str, TypeConfig] = {}
        self._aliases: dict[str, str] = {}
        self._initialized = False

    def register_type(
        self,
        field_type: type,
        name: str,
        comparator: type,
        aliases: list[str] | None = None,
        default_params: dict | None = None,
    ):
        """Register SQLAlchemy field type with associated comparator class and aliases.

        Args:
            field_type: SQLAlchemy type class to register
            name: Primary name for the type
            comparator: Comparator class providing database functions
            aliases: Alternative names for the type
            default_params: Default parameters for type construction

        Example:
            registry.register_type(
                String, 'string', StringComparator,
                aliases=['str'], default_params={'length': 255}
            )
        """
        # Extract constructor parameters
        arguments = _extract_constructor_params(field_type)

        config: TypeConfig = {
            "sqlalchemy_type": field_type,
            "comparator_class": comparator,
            "default_params": default_params or {},  # noqa
            "arguments": arguments,
        }

        self._type_configs[name] = config

        if aliases:
            for alias in aliases:
                self._aliases[alias] = name

    def get_type_config(self, name: str) -> TypeConfig:
        """Get complete type configuration by registered name or alias.

        Args:
            name: Type name or alias to look up

        Returns:
            Complete type configuration with SQLAlchemy type and comparator

        Raises:
            ValueError: If type name is not registered

        Example:
            config = registry.get_type_config('string')
            # Returns TypeConfig with String class and StringComparator
        """
        if not self._initialized:
            self._init_builtin_types()

        resolved_name = self._aliases.get(name, name)
        config = self._type_configs.get(resolved_name)
        if not config:
            available_types = list(self._type_configs.keys())
            raise ValueError(f"Unknown type: '{name}'. Available types: {available_types}")
        return config

    def create_enhanced_type(self, name: str, **params) -> Any:
        """Create SQLAlchemy type instance with enhanced comparator.

        Args:
            name: Type name to create
            **params: Parameters for type construction

        Returns:
            SQLAlchemy type instance with comparator_factory set

        Example:
            string_type = registry.create_enhanced_type('string', length=100)
            # Returns String(100) with StringComparator attached
        """
        config = self.get_type_config(name)

        # Extract valid type parameters using constructor analysis
        type_params = _get_type_params(config, params)
        final_params = {**config["default_params"], **type_params}

        # Special handling for ARRAY type
        if name == "array" and "item_type" in final_params:
            final_params["item_type"] = _transform_array_item_type(final_params["item_type"])

        type_instance = config["sqlalchemy_type"](**final_params)
        type_instance.comparator_factory = config["comparator_class"]

        return type_instance

    def _init_builtin_types(self):
        """Register all built-in SQLAlchemy types with their comparator mappings.

        Registers standard SQLAlchemy types (String, Integer, etc.) with
        their corresponding comparator classes and common aliases.
        Called automatically on first registry access.
        """
        builtin_types = [
            (String, "string", StringComparator, ["str"], {"length": 255}),
            (Text, "text", StringComparator, [], {}),
            (Integer, "integer", IntegerComparator, ["int"], {}),
            (BigInteger, "bigint", IntegerComparator, [], {}),
            (SmallInteger, "smallint", IntegerComparator, [], {}),
            (Float, "float", NumericComparator, [], {}),
            (Double, "double", NumericComparator, [], {}),
            (Numeric, "numeric", NumericComparator, ["decimal"], {}),
            (Boolean, "boolean", BooleanComparator, ["bool"], {}),
            (DateTime, "datetime", DateTimeComparator, [], {}),
            (Date, "date", DateTimeComparator, [], {}),
            (Time, "time", DateTimeComparator, [], {}),
            (Interval, "interval", DateTimeComparator, [], {}),
            (LargeBinary, "binary", DefaultComparator, ["bytes"], {}),
            (Uuid, "uuid", StringComparator, [], {}),
            (JSON, "json", JSONComparator, ["dict"], {}),
        ]

        # Special types
        special_types = [
            (ARRAY, "array", DefaultComparator, [], {}),
            (Enum, "enum", DefaultComparator, [], {}),
            (Auto, "auto", DefaultComparator, [], {}),
        ]

        for field_type, name, comparator, aliases, defaults in builtin_types + special_types:
            self.register_type(field_type, name, comparator, aliases, defaults)

        self._initialized = True


# Global registry instance
_registry = TypeRegistry()


def register_field_type(
    field_type: type[Any],
    type_name: str,
    *,
    comparator: type[Any] | None = None,
    aliases: list[str] | None = None,
    default_params: dict[str, Any] | None = None,
) -> None:
    """Register a custom field type in the global registry.

    Allows registration of custom SQLAlchemy types for use with the
    column() function and type system.

    Args:
        field_type: SQLAlchemy type class to register
        type_name: Name to register the type under
        comparator: Custom comparator class (defaults to ComparatorMixin)
        aliases: Alternative names for the type
        default_params: Default parameters for type construction

    Example:
        from sqlalchemy import INET

        register_field_type(
            INET, 'inet',
            aliases=['ip_address'],
            default_params={}
        )

        # Now can use: column(type='inet') or column(type='ip_address')
    """
    from .comparators import ComparatorMixin

    _registry.register_type(
        field_type=field_type,
        name=type_name,
        comparator=comparator or ComparatorMixin,
        aliases=aliases,
        default_params=default_params,
    )


def create_type_instance(type_name: str, kwargs: dict[str, Any]) -> Any:
    """Create SQLAlchemy type instance from registered type name and parameters.

    Args:
        type_name: Registered type name (e.g., 'string', 'integer')
        kwargs: Parameters for type construction

    Returns:
        SQLAlchemy type instance with enhanced comparator

    Example:
        string_type = create_type_instance('string', {'length': 100})
        # Returns String(100) with StringComparator
    """
    return _registry.create_enhanced_type(type_name, **kwargs)


def get_type_definition(type_name: str) -> TypeConfig:
    """Get complete type configuration definition by registered name.

    Args:
        type_name: Registered type name to look up

    Returns:
        Complete type configuration with all metadata

    Example:
        config = get_type_definition('string')
        # Returns TypeConfig with String class, StringComparator, etc.
    """
    return _registry.get_type_config(type_name)
