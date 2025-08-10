import re


__all__ = ["to_snake_case", "to_camel_case"]


def to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case (Rails style).

    Args:
        name: CamelCase string to convert

    Returns:
        snake_case string

    Examples:
        >>> to_snake_case("UserProfile")
        'user_profile'
        >>> to_snake_case("XMLParser")
        'xml_parser'
        >>> to_snake_case("HTTPRequest")
        'http_request'
    """
    # Handle sequences of uppercase letters followed by lowercase
    s1 = re.sub("([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Handle lowercase followed by uppercase
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


def to_camel_case(name: str, pascal_case: bool = True) -> str:
    """Convert snake_case to CamelCase.

    Args:
        name: snake_case string to convert
        pascal_case: If True, return PascalCase; if False, return camelCase

    Returns:
        CamelCase string

    Examples:
        >>> to_camel_case("user_profile")
        'UserProfile'
        >>> to_camel_case("user_profile", pascal_case=False)
        'userProfile'
        >>> to_camel_case("xml_parser")
        'XmlParser'
    """
    components = name.split("_")
    if pascal_case:
        return "".join(word.capitalize() for word in components)
    else:
        return components[0] + "".join(word.capitalize() for word in components[1:])
