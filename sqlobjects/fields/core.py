"""Core field classes for SQLObjects"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from sqlalchemy import Column as CoreColumn
from sqlalchemy import ForeignKey
from sqlalchemy.sql.elements import ColumnElement

from ..expressions.mixins import ColumnAttributeFunctionMixin
from .types import create_type_instance


if TYPE_CHECKING:
    pass


T = TypeVar("T")
NullableT = TypeVar("NullableT")


class Column(Generic[T]):
    """Field descriptor for parameter collection and ColumnAttribute creation."""

    def __init__(self, **params):
        self._params = params
        self._column_attribute = None
        self._relationship_descriptor = None
        self._is_relationship = params.get("is_relationship", False)
        self._nullable = params.get("nullable", True)  # Store nullable info for type inference
        self.name = None
        self._private_name = None

    def __set_name__(self, owner, name):
        self.name = name
        self._private_name = f"_{name}"

        if self._is_relationship:
            self._setup_relationship(owner, name)
        else:
            self._setup_column(owner, name)

    def _setup_relationship(self, owner, name):
        """Set relationship field"""
        from .relations.descriptors import RelationshipDescriptor

        relationship_property = self._params.get("relationship_property")
        if relationship_property:
            self._relationship_descriptor = RelationshipDescriptor(relationship_property)
            self._relationship_descriptor.__set_name__(owner, name)

    def _setup_column(self, owner, name):
        """Set database field"""
        params = self._params.copy()
        foreign_key = params.pop("foreign_key", None)
        type_name = params.pop("type", "auto")

        # Process extended parameters
        info = params.pop("info", None) or {}

        # Collect code generation parameters
        codegen_params = {}
        for key in ["init", "repr", "compare", "hash", "kw_only"]:
            if key in params:
                codegen_params[key] = params.pop(key)

        # Collect performance parameters
        performance_params = {}
        for key in ["deferred", "deferred_group", "deferred_raiseload", "active_history"]:
            if key in params:
                performance_params[key] = params.pop(key)

        # Collect enhanced parameters
        enhanced_params = {}
        for key in ["default_factory", "insert_default", "validators"]:
            if key in params:
                enhanced_params[key] = params.pop(key)

        # Apply intelligent defaults
        column_kwargs = {
            "primary_key": params.get("primary_key", False),
            "autoincrement": params.get("autoincrement", "auto"),
            "server_default": params.get("server_default"),
        }
        codegen_params = _apply_codegen_defaults(codegen_params, column_kwargs)

        # Store parameters to info
        info["_codegen"] = codegen_params
        info["_performance"] = performance_params
        info["_enhanced"] = enhanced_params

        # Handle default value logic
        default = params.get("default")
        default_factory = enhanced_params.get("default_factory")
        insert_default = enhanced_params.get("insert_default")
        final_default = _resolve_default_value(default, default_factory, insert_default)
        if final_default is not None:
            params["default"] = final_default

        # Separate type parameters and column parameters
        type_params = _extract_type_params(params)
        column_params = _extract_column_params(params)
        column_params["info"] = info

        # Remove potentially conflicting parameters
        params.pop("name", None)
        type_params.pop("name", None)

        # Create enhanced type
        enhanced_type = create_type_instance(type_name, type_params)

        # Create ColumnAttribute
        self._column_attribute = ColumnAttribute(
            name, enhanced_type, foreign_key=foreign_key, model_class=owner, **column_params
        )

    @overload
    def __get__(self, instance: None, owner: type) -> "ColumnAttribute[T]": ...

    @overload
    def __get__(self, instance: Any, owner: type) -> T: ...

    def __get__(self, instance, owner):
        if self._is_relationship and self._relationship_descriptor:
            return self._relationship_descriptor.__get__(instance, owner)

        if instance is None:
            return self._column_attribute
        else:
            # Instance access returns stored value
            private_name = self._private_name or f"_{self.name}"
            value = getattr(instance, private_name, None)
            if self._nullable:
                return cast(T | None, value)
            else:
                return cast(T, value)

    def __set__(self, instance, value):
        if self._is_relationship:
            # Relationship fields may not support direct setting
            pass
        else:
            if instance is None:
                raise AttributeError("Cannot set attribute on class")
            private_name = self._private_name or f"_{self.name}"
            setattr(instance, private_name, value)


class ColumnAttribute(ColumnAttributeFunctionMixin, Generic[T]):
    def __getattr__(self, name):
        """Handle attribute access with proper priority

        First check for SQLAlchemy column attributes, then delegate to function mixin.
        """
        # First try the underlying SQLAlchemy column for its own attributes
        if hasattr(self.__column__, name):
            return getattr(self.__column__, name)

        # Then delegate to the function mixin for database functions
        return super().__getattr__(name)

    """Enhanced column attribute with SQLAlchemy CoreColumn compatibility.

    Extends SQLAlchemy's Column with additional functionality for validation,
    performance optimization, and code generation control. Used when accessing
    fields on model classes for query building.

    Features:
    - Validation system integration
    - Deferred loading support
    - Code generation parameter control
    - Enhanced default value handling
    - Performance optimization settings

    Example:
        # Accessed when building queries
        User.name  # Returns ColumnAttribute instance
        User.objects.filter(User.name == 'John')  # Uses ColumnAttribute
    """

    inherit_cache = True  # make use of the cache key generated by the superclass from SQLAlchemy

    def __init__(self, name, type_, foreign_key=None, *, model_class, **kwargs):  # noqa
        # Extract enhanced parameters from info dict
        info = kwargs.get("info", {})
        enhanced_params = info.get("_enhanced", {})
        performance_params = info.get("_performance", {})
        codegen_params = info.get("_codegen", {})

        # Filter out invalid SQLAlchemy Column parameters
        valid_kwargs = _extract_column_params(kwargs)

        # Create internal Column instance for table creation
        if foreign_key is not None:
            self.__column__ = CoreColumn(name, type_, foreign_key, **valid_kwargs)
        else:
            self.__column__ = CoreColumn(name, type_, **valid_kwargs)

        # Save enhanced functionality parameters
        self.model_class = model_class
        self._enhanced_params = enhanced_params
        self._performance_params = performance_params
        self._codegen_params = codegen_params

        # Store field name for type annotation lookup
        self._field_name = name

    # === Core functionality interfaces ===

    # Validation related
    @property
    def validators(self) -> list[Any]:
        return self._enhanced_params.get("validators", [])

    def validate_value(self, value: Any, field_name: str) -> Any:
        """Validate field value using registered validators"""
        validators = self.validators
        if validators:
            from ..validators import validate_field_value

            return validate_field_value(value, validators, field_name)
        return value

    # Default value related
    def get_default_factory(self) -> Callable[[], Any] | None:
        return self._enhanced_params.get("default_factory")

    def get_insert_default(self) -> Any:
        return self._enhanced_params.get("insert_default")

    def has_insert_default(self) -> bool:
        return "insert_default" in self._enhanced_params

    def get_effective_default(self) -> Any:
        """Get effective default value by priority order"""
        if self.default is not None:
            return self.default

        default_factory = self.get_default_factory()
        if default_factory is not None:
            return default_factory

        insert_default = self.get_insert_default()
        if insert_default is not None:
            return insert_default

        return None

    # Performance optimization related
    @property
    def is_deferred(self) -> bool:
        return self._performance_params.get("deferred", False)

    @property
    def deferred_group(self) -> str | None:
        return self._performance_params.get("deferred_group")

    @property
    def has_active_history(self) -> bool:
        return self._performance_params.get("active_history", False)

    @property
    def deferred_raiseload(self) -> bool | None:
        return self._performance_params.get("deferred_raiseload")

    # Code generation related
    @property
    def include_in_init(self) -> bool | None:
        return self._codegen_params.get("init")

    def create_table_column(self, name: str) -> CoreColumn:
        """Create independent Column instance for Table to avoid binding conflicts"""
        # Create new ForeignKey instance instead of reusing existing one
        foreign_keys = []
        if self.__column__.foreign_keys:
            for fk in self.__column__.foreign_keys:
                # Use original string reference instead of column attribute
                new_fk = ForeignKey(
                    fk._colspec,  # noqa # Use original string reference
                    name=fk.name,
                    onupdate=fk.onupdate,
                    ondelete=fk.ondelete,
                    deferrable=fk.deferrable,
                    initially=fk.initially,
                    use_alter=fk.use_alter,
                    link_to_name=fk.link_to_name,
                    match=fk.match,
                    info=fk.info.copy() if fk.info else None,
                )
                foreign_keys.append(new_fk)

        return CoreColumn(
            name,
            self.__column__.type,
            *foreign_keys,
            nullable=self.__column__.nullable,
            default=self.__column__.default,
            server_default=self.__column__.server_default,
            primary_key=self.__column__.primary_key,
            autoincrement=self.__column__.autoincrement,
            unique=self.__column__.unique,
            index=self.__column__.index,
            doc=getattr(self.__column__, "doc", None),
            key=getattr(self.__column__, "key", None),
            onupdate=getattr(self.__column__, "onupdate", None),
            server_onupdate=getattr(self.__column__, "server_onupdate", None),
            quote=getattr(self.__column__, "quote", None),
            system=getattr(self.__column__, "system", False),
            comment=getattr(self.__column__, "comment", None),
            info=self.__column__.info.copy() if self.__column__.info else None,
        )

    # Explicit core attribute delegation (performance optimization)
    @property
    def name(self):
        return self.__column__.name

    @property
    def type(self):
        return self.__column__.type

    @property
    def nullable(self):
        return self.__column__.nullable

    @property
    def default(self):
        return self.__column__.default

    @property
    def primary_key(self):
        return self.__column__.primary_key

    @property
    def foreign_keys(self):
        return self.__column__.foreign_keys

    @property
    def comparator(self):
        return self.__column__.comparator

    # Explicitly declare core SQLAlchemy methods (IDE support)
    def __eq__(self, other) -> ColumnElement[bool]:  # type: ignore[reportIncompatibleMethodOverride]
        # Convert other ColumnAttribute to its underlying column
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ == other

    def __ne__(self, other) -> ColumnElement[bool]:  # type: ignore[reportIncompatibleMethodOverride]
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ != other

    def __lt__(self, other) -> ColumnElement[bool]:
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ < other

    def __le__(self, other) -> ColumnElement[bool]:
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ <= other

    def __gt__(self, other) -> ColumnElement[bool]:
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ > other

    def __ge__(self, other) -> ColumnElement[bool]:
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return self.__column__ >= other

    # Arithmetic operators
    def __add__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        # Convert other ColumnAttribute to its underlying column
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(self.__column__ + other)

    def __radd__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        # Convert other ColumnAttribute to its underlying column
        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(other + self.__column__)

    def __sub__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(self.__column__ - other)

    def __rsub__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(other - self.__column__)

    def __mul__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(self.__column__ * other)

    def __rmul__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(other * self.__column__)

    def __truediv__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(self.__column__ / other)

    def __rtruediv__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(other / self.__column__)

    def __mod__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(self.__column__ % other)

    def __rmod__(self, other):
        from sqlobjects.expressions.function import FunctionExpression

        if isinstance(other, ColumnAttribute):
            other = other.__column__
        return FunctionExpression(other % self.__column__)

    def __hash__(self):
        """Delegate hash to underlying column for SQLAlchemy compatibility"""
        return self.__column__.__hash__()

    @property
    def include_in_repr(self) -> bool | None:
        return self._codegen_params.get("repr")

    @property
    def include_in_compare(self) -> bool | None:
        return self._codegen_params.get("compare")

    @property
    def include_in_hash(self) -> bool | None:
        return self._codegen_params.get("hash")

    @property
    def is_kw_only(self) -> bool | None:
        return self._codegen_params.get("kw_only")

    # === General parameter access methods ===

    def get_param(self, category: str, name: str, default: Any = None) -> Any:
        """Get parameter from specified category"""
        param_dict = getattr(self, f"_{category}_params", {})
        return param_dict.get(name, default)

    def get_codegen_params(self) -> dict[str, Any]:
        """Get code generation parameters"""
        return self._codegen_params

    def get_python_type(self):
        """Get Python type from class annotations, similar to SQLAlchemy's approach"""
        if not self.model_class or not self._field_name:
            return None

        # Get type annotation from model class
        annotations = getattr(self.model_class, "__annotations__", {})
        if self._field_name not in annotations:
            return None

        annotation = annotations[self._field_name]

        # Extract type parameter from Column[T] annotation
        try:
            from typing import get_args, get_origin

            # Check if it's a generic type like Column[int]
            origin = get_origin(annotation)
            args = get_args(annotation)

            # If it's Column[T], extract T
            if origin is not None and args:
                return args[0]  # Return the first type argument (T)

        except (ImportError, AttributeError):
            pass

        return None

    def get_field_metadata(self) -> dict[str, Any]:
        """Get complete field metadata information"""
        metadata = {
            "name": self.name,
            "type": str(self.type),
            "python_type": self.get_python_type(),
            "nullable": getattr(self, "nullable", True),
            "primary_key": getattr(self, "primary_key", False),
            "unique": getattr(self, "unique", False),
            "index": getattr(self, "index", False),
        }

        # Add comments and documentation
        if hasattr(self, "comment") and self.comment:
            metadata["comment"] = self.comment
        if hasattr(self, "doc") and self.doc:
            metadata["doc"] = self.doc

        # Add extended parameters
        if self._enhanced_params:
            metadata["enhanced"] = self._enhanced_params
        if self._performance_params:
            metadata["performance"] = self._performance_params
        if self._codegen_params:
            metadata["codegen"] = self._codegen_params

        return metadata


def column(
    *,
    type: str = "auto",  # noqa
    name: str | None = None,
    # SQLAlchemy Column parameters
    primary_key: bool = False,
    nullable: bool = True,
    default: Any = None,
    index: bool = False,
    unique: bool = False,
    autoincrement: str | bool = "auto",
    doc: str | None = None,
    key: str | None = None,
    onupdate: Any = None,
    comment: str | None = None,
    system: bool = False,
    server_default: Any = None,
    server_onupdate: Any = None,
    quote: bool | None = None,
    info: dict[str, Any] | None = None,
    # Essential functionality parameters
    default_factory: Callable[[], Any] | None = None,
    validators: list[Any] | None = None,
    deferred: bool = False,
    # Experience enhancement parameters
    deferred_group: str | None = None,
    insert_default: Any = None,
    init: bool | None = None,
    repr: bool | None = None,  # noqa
    compare: bool | None = None,
    # Advanced functionality parameters
    active_history: bool = False,
    deferred_raiseload: bool | None = None,
    hash: bool | None = None,  # noqa
    kw_only: bool | None = None,
    # Foreign key constraint
    foreign_key: ForeignKey | None = None,
    # Type parameters (passed through **kwargs)
    **kwargs: Any,
) -> "Column[Any]":
    """Create field descriptor with new unified architecture"""
    # Collect all parameters
    all_params = {
        "type": type,
        "name": name,
        "primary_key": primary_key,
        "nullable": nullable,
        "default": default,
        "index": index,
        "unique": unique,
        "autoincrement": autoincrement,
        "doc": doc,
        "key": key,
        "onupdate": onupdate,
        "comment": comment,
        "system": system,
        "server_default": server_default,
        "server_onupdate": server_onupdate,
        "quote": quote,
        "info": info,
        "default_factory": default_factory,
        "validators": validators,
        "deferred": deferred,
        "deferred_group": deferred_group,
        "insert_default": insert_default,
        "init": init,
        "repr": repr,
        "compare": compare,
        "active_history": active_history,
        "deferred_raiseload": deferred_raiseload,
        "hash": hash,
        "kw_only": kw_only,
        "foreign_key": foreign_key,
        **kwargs,
    }

    # Pass parameters directly to new Column class
    return Column(**all_params)


# Helper functions


def _extract_column_params(kwargs: dict) -> dict:
    """Extract SQLAlchemy Column parameters"""
    column_param_names = {
        "primary_key",
        "nullable",
        "default",
        "index",
        "unique",
        "autoincrement",
        "doc",
        "key",
        "onupdate",
        "comment",
        "system",
        "server_default",
        "server_onupdate",
        "quote",
        "info",
    }
    return {k: v for k, v in kwargs.items() if k in column_param_names}


def _extract_type_params(kwargs: dict) -> dict:
    """Extract type-specific parameters"""
    column_param_names = {
        "primary_key",
        "nullable",
        "default",
        "index",
        "unique",
        "autoincrement",
        "doc",
        "key",
        "onupdate",
        "comment",
        "system",
        "server_default",
        "server_onupdate",
        "quote",
        "info",
    }
    return {k: v for k, v in kwargs.items() if k not in column_param_names}


def _apply_codegen_defaults(codegen_params: dict, column_kwargs: dict) -> dict:
    """Apply default values for code generation parameters"""
    defaults = {"init": True, "repr": True, "compare": False, "hash": None, "kw_only": False}

    # Primary key fields: don't participate in initialization, but participate in comparison and display
    if column_kwargs.get("primary_key"):
        defaults.update({"init": False, "repr": True, "compare": True})

    # Auto-increment fields: only when it is True, don't participate in initialization
    if column_kwargs.get("autoincrement") is True:  # noqa
        defaults["init"] = False

    # Server default value fields: don't participate in initialization
    if column_kwargs.get("server_default") is not None:
        defaults["init"] = False

    # Apply defaults only for parameters not explicitly set or set to None
    for key, default_value in defaults.items():
        if key not in codegen_params or codegen_params[key] is None:
            codegen_params[key] = default_value

    return codegen_params


def _resolve_default_value(
    default: Any,
    default_factory: Callable[[], Any] | None,
    insert_default: Any,
) -> Any:
    """Resolve default value priority: default > default_factory > insert_default"""
    if default is not None:
        return default

    if default_factory is not None:
        # Wrap as SQLAlchemy compatible callable
        return lambda: default_factory()

    if insert_default is not None:
        # Support SQLAlchemy function expressions
        return insert_default

    return None
