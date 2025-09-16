from typing import Any

from sqlalchemy import Column as CoreColumn


def extract_field_metadata(field_info: dict[str, Any]) -> dict[str, Any]:
    """Extract field metadata from field info"""
    metadata = {}

    # Extract codegen parameters
    codegen = field_info.get("_codegen", {})
    if codegen:
        metadata["codegen"] = codegen

    # Extract performance parameters
    performance = field_info.get("_performance", {})
    if performance:
        metadata["performance"] = performance

    # Extract enhanced parameters
    enhanced = field_info.get("_enhanced", {})
    if enhanced:
        metadata["enhanced"] = enhanced

    return metadata


def get_deferred_fields(model_class) -> set[str]:
    """Get set of deferred field names from model class"""
    deferred_fields = set()

    for field_name, field in getattr(model_class, "__fields__", {}).items():
        if hasattr(field, "_column_attribute"):
            column_attr = field._column_attribute  # noqa
            if column_attr and column_attr.is_deferred:
                deferred_fields.add(field_name)

    return deferred_fields


def get_relation_fields(model_class) -> set[str]:
    """Get set of relation field names from model class"""
    relation_fields = set()

    for field_name, field in getattr(model_class, "__fields__", {}).items():
        if getattr(field, "_is_relationship", False):
            relation_fields.add(field_name)

    return relation_fields


def is_field_definition(attr) -> bool:
    """Check if attribute is a field definition.

    Determines whether an attribute represents a database field by checking
    for Column descriptor or ColumnAttribute characteristics.

    Args:
        attr: Attribute to check for field definition

    Returns:
        True if attribute is a field definition (Column descriptor or ColumnAttribute)

    Example:
        class User(ObjectModel):
            name = StringColumn()

        is_field_definition(User.name)  # True
        is_field_definition(User.__init__)  # False
    """
    return (
        hasattr(attr, "_column_attribute")  # Column descriptor
        or hasattr(attr, "__column__")  # ColumnAttribute instance (refactored)
        or hasattr(attr, "_is_relationship")  # Relationship fields
        or isinstance(attr, CoreColumn)  # Direct SQLAlchemy Column
    )


def get_column_from_field(field_def):
    """Get SQLAlchemy Column object from field definition.

    Extracts the underlying SQLAlchemy Column from various field definition
    formats used in SQLObjects.

    Args:
        field_def: Field definition (Column descriptor or ColumnAttribute)

    Returns:
        SQLAlchemy Column object or None if not a field definition or is a relationship field

    Example:
        user_name_field = User.name  # Column descriptor
        column = get_column_from_field(user_name_field)
        # Returns underlying SQLAlchemy Column
    """
    # Check if it's a relationship field first
    if hasattr(field_def, "_is_relationship") and field_def._is_relationship:  # noqa
        return None
    # New architecture - Column descriptor with _column_attribute
    if hasattr(field_def, "_column_attribute"):
        return field_def._column_attribute  # noqa
    # ColumnAttribute instance (refactored architecture)
    elif hasattr(field_def, "__column__"):
        return field_def  # Return ColumnAttribute itself for create_table_column method
    # Direct SQLAlchemy Column
    elif isinstance(field_def, CoreColumn):
        return field_def
    return None
