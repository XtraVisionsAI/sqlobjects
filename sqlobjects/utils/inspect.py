from typing import Any


def get_field_validators(model_class: type, field_name: str) -> list[Any]:
    """Get validator list for specified field.

    Args:
        model_class: Model class to inspect
        field_name: Name of field to get validators for

    Returns:
        List of validator functions for the field

    Example:
        validators = get_field_validators(User, 'email')
        # Returns list of validation functions
    """
    if hasattr(model_class, "_field_validators"):
        return model_class._field_validators.get(field_name, [])  # noqa
    return []


def get_model_metadata(model_class: type) -> dict[str, Any]:
    """Get complete metadata information for model.

    Extracts comprehensive metadata about a model class including
    field definitions, validators, and configuration.

    Args:
        model_class: Model class to inspect

    Returns:
        Dictionary containing complete model metadata

    Example:
        metadata = get_model_metadata(User)
        # {
        #     'model_name': 'User',
        #     'table_name': 'users',
        #     'fields': {...},
        #     'validators': {...},
        #     'config': {...}
        # }
    """
    metadata = {
        "model_name": model_class.__name__,
        "table_name": getattr(model_class.__table__, "name", None) if hasattr(model_class, "__table__") else None,
        "fields": {},
        "validators": getattr(model_class, "_field_validators", {}),
    }

    # Collect field metadata
    for name in dir(model_class):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(model_class, name)
            if hasattr(attr, "get_field_metadata"):
                metadata["fields"][name] = attr.get_field_metadata()
        except Exception:  # noqa
            continue

    # Add model configuration information
    if hasattr(model_class, "Config"):
        config_attrs = {}
        config_class = model_class.Config
        for attr_name in dir(config_class):
            if not attr_name.startswith("_") and not callable(getattr(config_class, attr_name, None)):
                try:
                    value = getattr(config_class, attr_name)
                    if not callable(value):
                        config_attrs[attr_name] = (
                            str(value) if hasattr(value, "__iter__") and not isinstance(value, str | bytes) else value
                        )
                except Exception:  # noqa
                    continue
        if config_attrs:
            metadata["config"] = config_attrs

    return metadata
