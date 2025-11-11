from .core import Column, ColumnAttribute, Related, column
from .functions import computed, foreign_key, identity
from .proxies import (
    # Backward compatibility aliases
    DeferredObject,
    ManyToManyRelation,
    OneToManyRelation,
    RelatedObject,
)
from .relations import M2MTable, relationship
from .shortcuts import (
    ArrayColumn,
    BinaryColumn,
    BooleanColumn,
    ComputedColumn,
    DateTimeColumn,
    EnumColumn,
    FloatColumn,
    IdentityColumn,
    IntegerColumn,
    JsonColumn,
    NumericColumn,
    StringColumn,
    TextColumn,
    UuidColumn,
)
from .utils import extract_field_metadata, get_deferred_fields, get_relation_fields


__all__ = [
    # Core field system
    "Column",
    "ColumnAttribute",
    "Related",
    "column",
    # Shortcut field classes
    "StringColumn",
    "TextColumn",
    "IntegerColumn",
    "FloatColumn",
    "NumericColumn",
    "BooleanColumn",
    "DateTimeColumn",
    "BinaryColumn",
    "UuidColumn",
    "JsonColumn",
    "ArrayColumn",
    "EnumColumn",
    "IdentityColumn",
    "ComputedColumn",
    # Special field functions
    "identity",
    "computed",
    "foreign_key",
    # Relationship system
    "M2MTable",
    "relationship",
    # Public proxy interfaces
    "DeferredObject",
    "RelatedObject",
    "OneToManyRelation",
    "ManyToManyRelation",
    # Utility functions
    "extract_field_metadata",
    "get_deferred_fields",
    "get_relation_fields",
]
