"""Shortcut field classes for common types"""

from typing import Any, Callable, Literal

from sqlalchemy import Computed, ForeignKey, Identity
from sqlalchemy.sql.elements import ColumnElement

from .core import Column


class StringColumn(Column[Any]):
    """String column type (type='string' or 'str')"""

    def __init__(
        self,
        *,
        length: int | None = None,
        type: Literal["string", "text"] = "string",  # noqa
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params: dict = {"type": type, **locals()}
        params.pop("self")
        if length is not None:
            params["length"] = length
        super().__init__(**params)


class TextColumn(Column[Any]):
    """Text column type (type='text')"""

    def __init__(
        self,
        *,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "text", **locals()}
        params.pop("self")
        super().__init__(**params)


class IntegerColumn(Column[Any]):
    """Integer column type (type='integer'/'bigint'/'smallint' or 'int')"""

    def __init__(
        self,
        *,
        type: Literal["integer", "bigint", "smallint", "int"] = "integer",  # noqa
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": type, **locals()}
        params.pop("self")
        super().__init__(**params)


class FloatColumn(Column[Any]):
    """Float column type (type='float'/'double')"""

    def __init__(
        self,
        *,
        type: Literal["float", "double"] = "float",  # noqa
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": type, **locals()}
        params.pop("self")
        super().__init__(**params)


class NumericColumn(Column[Any]):
    """Numeric column type (type='numeric' or 'decimal')"""

    def __init__(
        self,
        *,
        precision: int | None = None,
        scale: int | None = None,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params: dict = {"type": "numeric", **locals()}
        params.pop("self")
        if precision is not None:
            params["precision"] = precision
        if scale is not None:
            params["scale"] = scale
        super().__init__(**params)


class BooleanColumn(Column[Any]):
    """Boolean column type (type='boolean' or 'bool')"""

    def __init__(
        self,
        *,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "boolean", **locals()}
        params.pop("self")
        super().__init__(**params)


class DateTimeColumn(Column[Any]):
    """DateTime column type (type='datetime'/'date'/'time'/'interval')"""

    def __init__(
        self,
        *,
        type: Literal["datetime", "date", "time", "interval"] = "datetime",  # noqa
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": type, **locals()}
        params.pop("self")
        super().__init__(**params)


class BinaryColumn(Column[Any]):
    """Binary column type (type='binary' or 'bytes')"""

    def __init__(
        self,
        *,
        length: int | None = None,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params: dict = {"type": "binary", **locals()}
        params.pop("self")
        if length is not None:
            params["length"] = length
        super().__init__(**params)


class UuidColumn(Column[Any]):
    """UUID column type (type='uuid')"""

    def __init__(
        self,
        *,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "uuid", **locals()}
        params.pop("self")
        super().__init__(**params)


class JsonColumn(Column[Any]):
    """JSON column type (type='json' or 'dict')"""

    def __init__(
        self,
        *,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "json", **locals()}
        params.pop("self")
        super().__init__(**params)


class ArrayColumn(Column[Any]):
    """Array column type (type='array')"""

    def __init__(
        self,
        item_type: str | type[Any],
        *,
        dimensions: int = 1,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "array", "item_type": item_type, "dimensions": dimensions, **locals()}
        params.pop("self")
        params.pop("item_type")  # Already included above
        params.pop("dimensions")  # Already included above
        super().__init__(**params)


class EnumColumn(Column[Any]):
    """Enum column type (type='enum')"""

    def __init__(
        self,
        enum_class: type[Any],
        *,
        # SQLAlchemy Column parameters
        name: str | None = None,
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
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        params = {"type": "enum", "enum_class": enum_class, **locals()}
        params.pop("self")
        params.pop("enum_class")  # Already included above
        super().__init__(**params)


class IdentityColumn(Column[Any]):
    """Identity column type with database-native auto-increment support"""

    def __init__(
        self,
        *,
        start: int = 1,
        increment: int = 1,
        minvalue: int | None = None,
        maxvalue: int | None = None,
        cycle: bool = False,
        cache: int | None = None,
        # SQLAlchemy Column parameters
        name: str | None = None,
        primary_key: bool = True,  # Identity columns are typically primary keys
        nullable: bool = False,  # Identity columns are typically non-nullable
        default: Any = None,
        index: bool = False,
        unique: bool = False,
        autoincrement: str | bool = True,
        doc: str | None = None,
        key: str | None = None,
        onupdate: Any = None,
        comment: str | None = None,
        system: bool = False,
        server_onupdate: Any = None,
        quote: bool | None = None,
        info: dict[str, Any] | None = None,
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        # Validate parameters
        if start < 1:
            raise ValueError("Identity start value must be >= 1")
        if increment == 0:
            raise ValueError("Identity increment cannot be 0")

        # Create SQLAlchemy Identity object
        identity_col = Identity(
            start=start, increment=increment, minvalue=minvalue, maxvalue=maxvalue, cycle=cycle, cache=cache
        )

        # Prepare parameters
        params: dict = {"type": "integer", **locals()}
        params.pop("self")
        params.pop("start")
        params.pop("increment")
        params.pop("minvalue")
        params.pop("maxvalue")
        params.pop("cycle")
        params.pop("cache")
        params.pop("identity_col")
        params["server_default"] = identity_col
        params["autoincrement"] = True  # Identity columns should have autoincrement=True

        super().__init__(**params)


class ComputedColumn(Column[Any]):
    """Computed column type with expression-based values"""

    def __init__(
        self,
        sqltext: str | ColumnElement,
        *,
        persisted: bool | None = None,
        column_type: str = "auto",
        # SQLAlchemy Column parameters
        name: str | None = None,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,  # Will be validated and rejected
        index: bool = False,
        unique: bool = False,
        autoincrement: str | bool = "auto",
        doc: str | None = None,
        key: str | None = None,
        onupdate: Any = None,
        comment: str | None = None,
        system: bool = False,
        server_onupdate: Any = None,
        quote: bool | None = None,
        info: dict[str, Any] | None = None,
        # Enhanced functionality parameters
        default_factory: Callable[[], Any] | None = None,
        validators: list[Any] | None = None,
        deferred: bool = False,
        deferred_group: str | None = None,
        insert_default: Any = None,
        init: bool | None = None,
        repr: bool | None = None,  # noqa
        compare: bool | None = None,
        active_history: bool = False,
        deferred_raiseload: bool | None = None,
        hash: bool | None = None,  # noqa
        kw_only: bool | None = None,
        foreign_key: ForeignKey | None = None,
    ):
        # Validate parameters
        if default is not None:
            raise ValueError("Computed columns cannot have default values")

        # Create SQLAlchemy Computed object
        computed_col = Computed(sqltext, persisted=persisted)

        # Prepare parameters
        params: dict = {"type": column_type, **locals()}
        params.pop("self")
        params.pop("sqltext")
        params.pop("persisted")
        params.pop("column_type")
        params.pop("computed_col")
        params["server_default"] = computed_col
        params.pop("default")  # Remove default since it's not allowed

        super().__init__(**params)
