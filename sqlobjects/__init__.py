"""SQLObjects - Django-style async ORM library built on SQLAlchemy

A modern, type-safe ORM that combines the best of Django's ORM with SQLAlchemy's power,
featuring chainable queries, Q objects, relationship loading, and comprehensive validation.
"""

from .expressions import (
    SubqueryExpression,
    and_,
    asc,
    defer,
    desc,
    exists,
    func,
    joinedload,
    literal,
    load_only,
    not_,
    nullsfirst,
    nullslast,
    or_,
    selectinload,
    subqueryload,
    text,
    undefer,
)
from .fields import (
    Column,
    array_column,
    binary_column,
    bool_column,
    column,
    column_property,
    composite,
    computed,
    created_at,
    datetime_column,
    enum_column,
    foreign_key,
    identity,
    int_column,
    json_column,
    numeric_column,
    pickle_column,
    register_field_type,
    relationship,
    sequence,
    str_column,
    synonym,
    updated_at,
    uuid_column,
)
from .queries import Q, QuerySet


__version__ = "0.1.0"

__all__ = [
    # Core query system
    "Q",
    "QuerySet",
    # Field system
    "Column",
    "column",
    # Type shortcuts
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
    # Expression system
    "func",
    "and_",
    "or_",
    "not_",
    "exists",
    "text",
    "literal",
    "asc",
    "desc",
    "nullsfirst",
    "nullslast",
    "joinedload",
    "selectinload",
    "subqueryload",
    "defer",
    "undefer",
    "load_only",
    "SubqueryExpression",
]
