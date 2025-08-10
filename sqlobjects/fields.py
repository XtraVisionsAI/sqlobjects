"""SQLObjects Fields Module - Enhanced field types with function chaining support"""

import inspect
from collections.abc import Callable
from enum import Enum as PyEnum
from functools import lru_cache
from typing import Any, NotRequired, TypedDict

from sqlalchemy.orm import Mapped, column_property, composite, mapped_column, synonym
from sqlalchemy.orm import relationship as sa_relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.schema import Computed, ForeignKey, Identity, Sequence
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
    Unicode,
    UnicodeText,
    Uuid,
)

from .expressions import DateTimeFunctionMixin, FunctionResult, NumericFunctionMixin, StringFunctionMixin


__all__ = [
    # Core
    "Column",
    "column",
    # Type shortcuts (recommended)
    "str_column",
    "int_column",
    "datetime_column",
    "bool_column",
    "json_column",
    "numeric_column",
    "array_column",
    "enum_column",
    "uuid_column",
    "binary_column",
    "pickle_column",
    # SQLAlchemy advanced features
    "composite",
    "column_property",
    "synonym",
    "relationship",
    "identity",
    "computed",
    "sequence",
    "foreign_key",
    "created_at",
    "updated_at",
    # Type system
    "register_field_type",
    "create_type_instance",
    "get_type_definition",
    # Type definitions
    "TypeDefinition",
    "TypeArgument",
]


# === Type System ===


class TypeArgument(TypedDict):
    name: str
    type: type
    required: bool
    default: Any
    transform: NotRequired[Callable[[Any], Any]]
    positional: NotRequired[bool]


class TypeDefinition(TypedDict):
    type: type
    arguments: list[TypeArgument]


def _transform_array_item_type(item_type: str | type) -> type:
    """Transform array item_type from string to SQLAlchemy type."""
    if isinstance(item_type, str):
        type_def = _registry.get_type(item_type)
        if type_def:
            return type_def["type"]()
        else:
            raise ValueError(f"Unknown array item type: {item_type}")

    return item_type


def _extract_constructor_params(type_class: type) -> list[TypeArgument]:
    """Extract constructor parameters using inspect."""
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


def _get_type_params(type_def: TypeDefinition, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 kwargs 中获取类型构建参数"""
    type_params = {}
    type_param_names = {arg["name"] for arg in type_def["arguments"]}

    for key, value in kwargs.items():
        if key in type_param_names:
            arg_def = next(arg for arg in type_def["arguments"] if arg["name"] == key)
            if "transform" in arg_def and arg_def["transform"]:
                value = arg_def["transform"](value)
            type_params[key] = value

    # 应用默认值
    for arg in type_def["arguments"]:
        if arg["name"] not in type_params and not arg["required"] and arg["default"] is not None:
            default_value = arg["default"]
            if "transform" in arg and arg["transform"]:
                default_value = arg["transform"](default_value)
            type_params[arg["name"]] = default_value

    return type_params


class TypeRegistry:
    """类型注册表，支持缓存和延迟加载"""

    def __init__(self):
        self._types: dict[str, TypeDefinition] = {}
        self._aliases: dict[str, str] = {
            "str": "string",
            "int": "integer",
            "bool": "boolean",
            "decimal": "numeric",
        }
        self._initialized = False

    @lru_cache(maxsize=128)  # noqa: B019
    def get_type(self, name: str) -> TypeDefinition:
        """缓存类型查找"""
        if not self._initialized:
            self._init_builtin_types()

        type_def = self._types.get(self._resolve_alias(name))
        if not type_def:
            available_types = list(_registry._types.keys())
            raise ValueError(f"Unknown type: '{name}'. Available types: {available_types}")

        return type_def

    def register(self, type_def: TypeDefinition | type, type_name: str | None, aliases: list[str] | None = None):
        """注册类型"""
        if isinstance(type_def, type):
            type_def = self._create_type_definition(type_def)

        name = type_name or type_def["type"].__name__.lower()

        self._types[name] = type_def

        if aliases:
            for alias in aliases:
                self._aliases[alias] = name

    def create_type_instance(self, type_name: str, type_params: dict[str, Any]):
        """创建类型实例"""
        type_def = self.get_type(type_name)

        positional_args = []
        keyword_args = {}

        for arg_def in type_def["arguments"]:
            param_name = arg_def["name"]
            if param_name not in type_params:
                continue

            value = type_params[param_name]

            # 检查是否为位置参数（默认为 False）
            if arg_def.get("positional", False):
                positional_args.append(value)
            else:
                keyword_args[param_name] = value

        return type_def["type"](*positional_args, **keyword_args)

    def _create_type_definition(self, type_class: type) -> TypeDefinition:  # noqa
        """从类型类创建类型定义"""
        try:
            arguments = _extract_constructor_params(type_class)
            return {"type": type_class, "arguments": arguments}
        except Exception:  # noqa
            return {"type": type_class, "arguments": []}

    def _resolve_alias(self, name: str) -> str:
        """解析类型别名"""
        return self._aliases.get(name, name)

    def _init_builtin_types(self):
        """初始化所有内置类型"""
        # 核心抽象类型（仅包含 SQLAlchemy 抽象类型）
        builtin_types = [
            # 字符串抽象类型
            (EnhancedString, "string", ["str"]),
            (EnhancedText, "text"),
            # 数值抽象类型
            (EnhancedInteger, "integer", ["int"]),
            (EnhancedBigInteger, "bigint"),
            (EnhancedSmallInteger, "smallint"),
            (EnhancedFloat, "float"),
            (EnhancedDouble, "double"),
            (EnhancedNumeric, "numeric", ["decimal"]),  # DECIMAL 继承自 Numeric
            # 布尔抽象类型
            (EnhancedBoolean, "boolean", ["bool"]),
            # 日期时间抽象类型
            (EnhancedDate, "date"),
            (EnhancedDateTime, "datetime"),
            (EnhancedTime, "time"),
            (EnhancedInterval, "interval"),
            # 二进制抽象类型
            (EnhancedLargeBinary, "binary"),
            # UUID 抽象类型
            (EnhancedUuid, "uuid"),
            # 特殊类型
            (EnhancedJSON, "json"),
            # Legacy Unicode types
            (EnhancedUnicode, "unicode"),
            (EnhancedUnicodeText, "unicodetext"),
        ]

        # 特殊类型
        special_types = [
            (
                {
                    "type": ARRAY,
                    "arguments": [
                        {
                            "name": "item_type",
                            "type": Any,
                            "required": True,
                            "default": None,
                            "transform": _transform_array_item_type,
                            "positional": True,
                        },
                        {"name": "dimensions", "type": int, "required": False, "default": 1},
                    ],
                },
                "array",
                None,
            ),
            (
                {
                    "type": Enum,
                    "arguments": [
                        {"name": "enum_class", "type": type, "required": True, "default": None, "positional": True}
                    ],
                },
                "enum",
                None,
            ),
        ]

        # 注册所有类型
        for type_info in builtin_types + special_types:
            field_type = type_info[0]
            type_name = type_info[1]
            aliases = type_info[2] if len(type_info) > 2 else []
            self.register(field_type, type_name, aliases=aliases)

        self._initialized = True


def register_field_type(
    type_def: TypeDefinition | type,
    type_name: str,
    *,
    aliases: list[str] | None = None,
) -> None:
    """注册字段类型"""
    _registry.register(type_def, type_name, aliases=aliases)


def create_type_instance(type_name: str, kwargs: dict[str, Any]) -> Any:
    """创建类型实例"""
    type_def = _registry.get_type(type_name)
    type_params = _get_type_params(type_def, kwargs)
    return _registry.create_type_instance(type_name, type_params)


def get_type_definition(type_name: str) -> TypeDefinition:
    return _registry.get_type(type_name)


# 全局注册表实例
_registry = TypeRegistry()


# === Enhanced Types ===


class EnhancedStringComparator(String.Comparator, StringFunctionMixin):  # pyright: ignore[reportIncompatibleMethodOverride]
    """增强的字符串 comparator，支持直接函数调用"""

    def matches(self, pattern: str) -> ColumnElement[bool]:
        return self.expr.op("~")(pattern)

    def length_between(self, min_len: int, max_len: int) -> ColumnElement[bool]:
        return func.length(self.expr).between(min_len, max_len)


class EnhancedIntegerComparator(Integer.Comparator, NumericFunctionMixin):
    """增强的整数 comparator"""

    pass


class EnhancedDateTimeComparator(DateTime.Comparator, DateTimeFunctionMixin):
    """增强的日期时间 comparator"""

    # === 原有语义化方法（返回查询条件）===
    def is_today(self) -> ColumnElement[bool]:
        return func.date(self.expr) == func.current_date()  # noqa

    def is_past(self) -> ColumnElement[bool]:
        return self.expr < func.now()

    def is_future(self) -> ColumnElement[bool]:
        return self.expr > func.now()

    def year_equals(self, year: int) -> ColumnElement[bool]:
        return func.extract("year", self.expr) == year  # noqa

    def month_equals(self, month: int) -> ColumnElement[bool]:
        return func.extract("month", self.expr) == month  # noqa


class EnhancedBooleanComparator(Boolean.Comparator):
    """增强的布尔 comparator"""

    def is_true(self) -> ColumnElement[bool]:
        return self.expr.is_(True)

    def is_false(self) -> ColumnElement[bool]:
        return self.expr.is_(False)


class EnhancedJSONComparator(JSON.Comparator):
    """增强的 JSON comparator"""

    def has_key(self, key: str) -> ColumnElement[bool]:
        return self.expr.op("?")(key)

    def has_keys(self, *keys) -> ColumnElement[bool]:
        return self.expr.op("?&")(list(keys))

    def has_any_key(self, *keys) -> ColumnElement[bool]:
        return self.expr.op("?|")(list(keys))

    def path_exists(self, path: str) -> ColumnElement[bool]:
        return func.json_extract_path(self.expr, path).is_not(None)

    def extract_text(self, path: str) -> FunctionResult:
        return FunctionResult(func.json_extract_path_text(self.expr, path))


# === 增强的 SQLAlchemy 类型，支持链式函数调用 ===
class EnhancedString(String):
    """Enhanced String type with function chaining support"""

    comparator_factory = EnhancedStringComparator


class EnhancedText(Text):
    """Enhanced Text type with function chaining support"""

    comparator_factory = EnhancedStringComparator


class EnhancedInteger(Integer):
    """Enhanced Integer type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator


class EnhancedBigInteger(BigInteger):
    """Enhanced BigInteger type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator


class EnhancedSmallInteger(SmallInteger):
    """Enhanced SmallInteger type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator


class EnhancedFloat(Float):
    """Enhanced Float type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator  # 使用数值 comparator


class EnhancedNumeric(Numeric):
    """Enhanced Numeric type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator  # 使用数值 comparator


class EnhancedDateTime(DateTime):
    """Enhanced DateTime type with function chaining support"""

    comparator_factory = EnhancedDateTimeComparator


class EnhancedBoolean(Boolean):
    """Enhanced Boolean type with function chaining support"""

    comparator_factory = EnhancedBooleanComparator


class EnhancedJSON(JSON):
    """Enhanced JSON type with function chaining support"""

    comparator_factory = EnhancedJSONComparator


class EnhancedDouble(Double):
    """Enhanced Double type with function chaining support"""

    comparator_factory = EnhancedIntegerComparator


class EnhancedDate(Date):
    """Enhanced Date type with function chaining support"""

    comparator_factory = EnhancedDateTimeComparator


class EnhancedTime(Time):
    """Enhanced Time type with function chaining support"""

    comparator_factory = EnhancedDateTimeComparator


class EnhancedUuid(Uuid):
    """Enhanced Uuid type with function chaining support"""

    comparator_factory = EnhancedStringComparator


class EnhancedLargeBinary(LargeBinary):
    """Enhanced LargeBinary type with function chaining support"""

    comparator_factory = LargeBinary.Comparator


class EnhancedInterval(Interval):
    """Enhanced Interval type with function chaining support"""

    comparator_factory = Interval.Comparator


class EnhancedUnicode(Unicode):
    """Enhanced Unicode type with function chaining support"""

    comparator_factory = EnhancedStringComparator


class EnhancedUnicodeText(UnicodeText):
    """Enhanced UnicodeText type with function chaining support"""

    comparator_factory = EnhancedStringComparator


# === Core Field Functions ===


def _get_column_params(type_def: TypeDefinition, kwargs: dict[str, Any]) -> dict[str, Any]:
    """从 kwargs 中获取列参数（排除类型参数）"""
    type_param_names = {arg["name"] for arg in type_def["arguments"]}
    return {key: value for key, value in kwargs.items() if key not in type_param_names}


# 核心类型别名
Column = Mapped


# 核心字段函数
def column(
    type: str,  # noqa
    *,
    # Core parameters
    primary_key: bool = False,
    unique: bool = False,
    # Index and constraints
    index: bool | None = None,
    comment: str | None = None,
    # Default values and updates
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    # Column name control
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    # Deferred loading support
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    # Validator system
    validators: list[Any] | None = None,
    # Metadata
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
    **kwargs: Any,
) -> Any:
    """创建列定义，支持增强类型和链式调用"""

    # Store validators in info metadata
    if validators is not None:
        if info is None:
            info = {}
        else:
            info = info.copy()
        info["_validators"] = validators

    # Get type definition first
    type_def = get_type_definition(type)

    # Build column kwargs
    column_params = _get_column_params(type_def, kwargs)
    column_kwargs: dict[str, Any] = {
        "primary_key": primary_key,
        "unique": unique,
        "deferred": deferred,
        "active_history": active_history,
        "system": system,
        **column_params,
    }

    # Add optional parameters
    if index is not None:
        column_kwargs["index"] = index
    if comment is not None:
        column_kwargs["comment"] = comment
    if default is not None:
        column_kwargs["default"] = default
    if server_default is not None:
        column_kwargs["server_default"] = server_default
    if server_onupdate is not None:
        column_kwargs["server_onupdate"] = server_onupdate
    if onupdate is not None:
        column_kwargs["onupdate"] = onupdate
    if insert_default is not None:
        column_kwargs["insert_default"] = insert_default
    if name is not None:
        column_kwargs["name"] = name
    if key is not None:
        column_kwargs["key"] = key
    if quote is not None:
        column_kwargs["quote"] = quote
    if deferred_group is not None:
        column_kwargs["deferred_group"] = deferred_group
    if deferred_raiseload is not None:
        column_kwargs["deferred_raiseload"] = deferred_raiseload
    if info is not None:
        column_kwargs["info"] = info
    if doc is not None:
        column_kwargs["doc"] = doc

    type_instance = create_type_instance(type, kwargs)
    return mapped_column(type_instance, **column_kwargs)


# === Shortcut Functions ===


def str_column(
    *,
    type: str = "string",  # noqa
    length: int | None = None,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        length=length,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def int_column(
    *,
    type: str = "integer",  # noqa
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def datetime_column(
    *,
    type: str = "datetime",  # noqa
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def bool_column(
    *,
    type: str = "boolean",  # noqa
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def json_column(
    *,
    type: str = "json",  # noqa
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def numeric_column(
    *,
    type: str = "numeric",  # noqa
    precision: int | None = None,
    scale: int | None = None,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        precision=precision,
        scale=scale,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def array_column(
    item_type: str,
    *,
    dimensions: int = 1,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type="array",
        item_type=item_type,
        dimensions=dimensions,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def enum_column(
    enum_class: type[PyEnum],
    *,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type="enum",
        enum_class=enum_class,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def uuid_column(
    *,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type="uuid",
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def binary_column(
    *,
    type: str = "binary",  # noqa
    length: int | None = None,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type=type,
        length=length,
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def pickle_column(
    *,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    server_default: Any = None,
    server_onupdate: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    """Pickle column for Python object serialization"""
    return binary_column(
        type="binary",
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        server_default=server_default,
        server_onupdate=server_onupdate,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


# === SQLAlchemy Advanced Features ===


def identity(
    start: int = 1,
    increment: int = 1,
    *,
    comment: str | None = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    identity_instance = Identity(start=start, increment=increment)
    column_kwargs: dict[str, Any] = {"primary_key": True, "system": system}

    if comment is not None:
        column_kwargs["comment"] = comment
    if name is not None:
        column_kwargs["name"] = name
    if key is not None:
        column_kwargs["key"] = key
    if quote is not None:
        column_kwargs["quote"] = quote
    if info is not None:
        column_kwargs["info"] = info
    if doc is not None:
        column_kwargs["doc"] = doc

    return mapped_column(Integer, identity_instance, **column_kwargs)


def computed(
    expression: str,
    *,
    type: str | None = None,  # noqa
    persisted: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    computed_instance = Computed(expression, persisted=persisted)
    column_kwargs: dict[str, Any] = {
        "unique": unique,
        "deferred": deferred,
        "active_history": active_history,
        "system": system,
    }

    if index is not None:
        column_kwargs["index"] = index
    if comment is not None:
        column_kwargs["comment"] = comment
    if name is not None:
        column_kwargs["name"] = name
    if key is not None:
        column_kwargs["key"] = key
    if quote is not None:
        column_kwargs["quote"] = quote
    if deferred_group is not None:
        column_kwargs["deferred_group"] = deferred_group
    if deferred_raiseload is not None:
        column_kwargs["deferred_raiseload"] = deferred_raiseload
    if info is not None:
        column_kwargs["info"] = info
    if doc is not None:
        column_kwargs["doc"] = doc

    if type is not None:
        type_instance = create_type_instance(type, {})
        return mapped_column(type_instance, computed_instance, **column_kwargs)

    return mapped_column(computed_instance, **column_kwargs)


def sequence(
    name: str,
    *,
    start: int = 1,
    increment: int = 1,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    column_name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    seq = Sequence(name, start=start, increment=increment)
    column_kwargs: dict[str, Any] = {
        "primary_key": primary_key,
        "unique": unique,
        "server_default": seq.next_value(),
        "system": system,
    }

    if index is not None:
        column_kwargs["index"] = index
    if comment is not None:
        column_kwargs["comment"] = comment
    if default is not None:
        column_kwargs["default"] = default
    if onupdate is not None:
        column_kwargs["onupdate"] = onupdate
    if insert_default is not None:
        column_kwargs["insert_default"] = insert_default
    if column_name is not None:
        column_kwargs["name"] = column_name
    if key is not None:
        column_kwargs["key"] = key
    if quote is not None:
        column_kwargs["quote"] = quote
    if info is not None:
        column_kwargs["info"] = info
    if doc is not None:
        column_kwargs["doc"] = doc

    return mapped_column(Integer, **column_kwargs)


def foreign_key(
    target: str,
    *,
    on_delete: str = "CASCADE",
    on_update: str = "CASCADE",
    unique: bool = False,
    index: bool = True,
    comment: str | None = None,
    name: str | None = None,
    **kwargs: Any,
) -> Any:
    fk = ForeignKey(target, ondelete=on_delete, onupdate=on_update)
    column_kwargs: dict[str, Any] = {"unique": unique, "index": index, **kwargs}

    if comment is not None:
        column_kwargs["comment"] = comment
    if name is not None:
        column_kwargs["name"] = name

    return mapped_column(fk, **column_kwargs)


def created_at(
    *,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type="datetime",
        server_default=func.now(),
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def updated_at(
    *,
    primary_key: bool = False,
    unique: bool = False,
    index: bool | None = None,
    comment: str | None = None,
    default: Any = None,
    onupdate: Any = None,
    insert_default: Any = None,
    name: str | None = None,
    key: str | None = None,
    quote: bool | None = None,
    deferred: bool = False,
    deferred_group: str | None = None,
    deferred_raiseload: bool | None = None,
    active_history: bool = False,
    validators: list[Any] | None = None,
    info: dict[str, Any] | None = None,
    doc: str | None = None,
    system: bool = False,
) -> Any:
    return column(
        type="datetime",
        server_default=func.now(),
        server_onupdate=func.now(),
        primary_key=primary_key,
        unique=unique,
        index=index,
        comment=comment,
        default=default,
        onupdate=onupdate,
        insert_default=insert_default,
        name=name,
        key=key,
        quote=quote,
        deferred=deferred,
        deferred_group=deferred_group,
        deferred_raiseload=deferred_raiseload,
        active_history=active_history,
        validators=validators,
        info=info,
        doc=doc,
        system=system,
    )


def relationship(
    to: str | Any,
    *,
    back_populates: str | None = None,
    lazy: str = "select",
    cascade: str | None = None,
    order_by: str | Any | None = None,
    foreign_keys: str | list[str] | None = None,
    secondary: str | Any | None = None,
    uselist: bool | None = None,
    primaryjoin: str | Any | None = None,
    secondaryjoin: str | Any | None = None,
    remote_side: str | Any | None = None,
    join_depth: int | None = None,
    innerjoin: bool | None = None,
    distinct_target_key: bool | None = None,
    collection_class: type | None = None,
    passive_deletes: bool | str | None = None,
    passive_updates: bool | None = None,
    post_update: bool | None = None,
    viewonly: bool | None = None,
    sync_backref: bool | None = None,
    doc: str | None = None,
    info: dict[str, Any] | None = None,
) -> Any:
    rel_kwargs: dict[str, Any] = {"lazy": lazy}

    if back_populates is not None:
        rel_kwargs["back_populates"] = back_populates
    if cascade is not None:
        rel_kwargs["cascade"] = cascade
    if order_by is not None:
        rel_kwargs["order_by"] = order_by
    if foreign_keys is not None:
        rel_kwargs["foreign_keys"] = foreign_keys
    if secondary is not None:
        rel_kwargs["secondary"] = secondary
    if uselist is not None:
        rel_kwargs["uselist"] = uselist
    if primaryjoin is not None:
        rel_kwargs["primaryjoin"] = primaryjoin
    if secondaryjoin is not None:
        rel_kwargs["secondaryjoin"] = secondaryjoin
    if remote_side is not None:
        rel_kwargs["remote_side"] = remote_side
    if join_depth is not None:
        rel_kwargs["join_depth"] = join_depth
    if innerjoin is not None:
        rel_kwargs["innerjoin"] = innerjoin
    if distinct_target_key is not None:
        rel_kwargs["distinct_target_key"] = distinct_target_key
    if collection_class is not None:
        rel_kwargs["collection_class"] = collection_class
    if passive_deletes is not None:
        rel_kwargs["passive_deletes"] = passive_deletes
    if passive_updates is not None:
        rel_kwargs["passive_updates"] = passive_updates
    if post_update is not None:
        rel_kwargs["post_update"] = post_update
    if viewonly is not None:
        rel_kwargs["viewonly"] = viewonly
    if sync_backref is not None:
        rel_kwargs["sync_backref"] = sync_backref
    if doc is not None:
        rel_kwargs["doc"] = doc
    if info is not None:
        rel_kwargs["info"] = info

    return sa_relationship(to, **rel_kwargs)
