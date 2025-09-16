"""Validation system for SQLObjects"""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Pattern

from .exceptions import ValidationError


__all__ = [
    "FieldValidator",
    "LengthValidator",
    "RangeValidator",
    "EmailValidator",
    "RegexValidator",
    "ChoiceValidator",
    "validate_field_value",
    # Built-in validators
    "validate_length",
    "validate_range",
    "validate_email",
    "validate_url",
    "validate_regex",
    "validate_choice",
    "validate_not_empty",
    "validate_positive",
    "validate_datetime_range",
]


class FieldValidator(ABC):
    """Base class for field validators.

    This abstract base class defines the interface for all field validators
    in the SQLObjects system. Validators are used to ensure data integrity
    and enforce business rules on model fields.

    Examples:
        >>> class CustomValidator(FieldValidator):
        ...     def validate(self, value: Any, field_name: str) -> Any:
        ...         if value and len(str(value)) < 3:
        ...             raise ValidationError(self.get_error_message(field_name, value))
        ...         return value
        ...
        ...     def get_error_message(self, field_name: str, value: Any) -> str:
        ...         return f"Field '{field_name}' must be at least 3 characters long"
    """

    def __init__(self, message: str | None = None):
        self.message = message

    @abstractmethod
    def validate(self, value: Any, field_name: str | None = None) -> Any:
        """Validate and return the processed value.

        Args:
            value: The value to validate
            field_name: Name of the field being validated

        Returns:
            The validated (and potentially transformed) value

        Raises:
            ValidationError: If validation fails
        """
        pass

    def __call__(self, value: Any, field_name: str | None = None) -> Any:
        """Make validator callable"""
        return self.validate(value, field_name)


class LengthValidator(FieldValidator):
    """Validate string length"""

    def __init__(self, min_length: int | None = None, max_length: int | None = None, message: str | None = None):
        super().__init__(message)
        self.min_length = min_length
        self.max_length = max_length

    def validate(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        str_value = str(value)
        length = len(str_value)

        if self.min_length is not None and length < self.min_length:
            raise ValidationError(
                self.message or f"Value must be at least {self.min_length} characters long",
                field=field_name,
                code="min_length",
            )

        if self.max_length is not None and length > self.max_length:
            raise ValidationError(
                self.message or f"Value must be at most {self.max_length} characters long",
                field=field_name,
                code="max_length",
            )

        return value


class RangeValidator(FieldValidator):
    """Validate numeric range"""

    def __init__(self, min_value: float | None = None, max_value: float | None = None, message: str | None = None):
        super().__init__(message)
        self.min_value = min_value
        self.max_value = max_value

    def validate(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        try:
            num_value = float(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                self.message or "Value must be a number",
                field=field_name,
                code="invalid_number",
            ) from e

        if self.min_value is not None and num_value < self.min_value:
            raise ValidationError(
                self.message or f"Value must be at least {self.min_value}", field=field_name, code="min_value"
            )

        if self.max_value is not None and num_value > self.max_value:
            raise ValidationError(
                self.message or f"Value must be at most {self.max_value}", field=field_name, code="max_value"
            )

        return value


class EmailValidator(FieldValidator):
    """Validate email address"""

    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def validate(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        str_value = str(value)
        if not self.EMAIL_PATTERN.match(str_value):
            raise ValidationError(self.message or "Invalid email address", field=field_name, code="invalid_email")

        return value


class RegexValidator(FieldValidator):
    """Validate against regex pattern"""

    def __init__(self, pattern: str | Pattern, message: str | None = None):
        super().__init__(message)
        if isinstance(pattern, str):
            self.pattern = re.compile(pattern)
        else:
            self.pattern = pattern

    def validate(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        str_value = str(value)
        if not self.pattern.match(str_value):
            raise ValidationError(
                self.message or "Value does not match required pattern", field=field_name, code="invalid_pattern"
            )

        return value


class ChoiceValidator(FieldValidator):
    """Validate value is in allowed choices"""

    def __init__(self, choices: list[Any], message: str | None = None):
        super().__init__(message)
        self.choices = choices

    def validate(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        if value not in self.choices:
            raise ValidationError(
                self.message or f"Value must be one of: {', '.join(map(str, self.choices))}",
                field=field_name,
                code="invalid_choice",
            )

        return value


def validate_field_value(value: Any, validators: list[Any], field_name: str | None = None) -> Any:
    """Validate a field value using a list of validators.

    This function applies multiple validators to a field value in sequence.
    It supports both FieldValidator instances and simple callable functions.

    Args:
        value: The value to validate
        validators: List of validators to apply
        field_name: Name of the field being validated

    Returns:
        The validated (and potentially transformed) value

    Raises:
        ValidationError: If any validator fails

    Examples:
        >>> validators = [LengthValidator(min_length=3, max_length=50), EmailValidator()]
        >>> validate_field_value("user@example.com", validators, "email")
        'user@example.com'

        >>> # Using simple function validator
        >>> def no_spaces(value):
        ...     if " " in str(value):
        ...         raise ValueError("No spaces allowed")
        ...     return value
        >>> validate_field_value("username", [no_spaces], "username")
        'username'
    """

    if not validators:
        return value

    validated_value = value
    for validator in validators:
        if callable(validator):
            validated_value = validator(validated_value, field_name)
        else:
            raise ValueError(f"Invalid validator: {validator}")

    return validated_value


# Convenience functions for creating validators


def validate_length(min_length: int | None = None, max_length: int | None = None, message: str | None = None):
    """Create length validator"""
    return LengthValidator(min_length, max_length, message)


def validate_range(min_value: float | None = None, max_value: float | None = None, message: str | None = None):
    """Create range validator"""
    return RangeValidator(min_value, max_value, message)


def validate_email(message: str | None = None):
    """Create email validator"""
    return EmailValidator(message)


def validate_url(message: str | None = None):
    """Create URL validator"""
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return RegexValidator(url_pattern, message or "Invalid URL")


def validate_regex(pattern: str | Pattern, message: str | None = None):
    """Create regex validator"""
    return RegexValidator(pattern, message)


def validate_choice(choices: list[Any], message: str | None = None):
    """Create choice validator"""
    return ChoiceValidator(choices, message)


def validate_not_empty(message: str | None = None):
    """Create not empty validator"""

    def validator(value: Any, field_name: str | None = None) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError(message or "Value cannot be empty", field=field_name, code="required")
        return value

    return validator


def validate_positive(message: str | None = None):
    """Create positive number validator"""
    return validate_range(min_value=0, message=message or "Value must be positive")


def validate_datetime_range(
    min_date: datetime | None = None, max_date: datetime | None = None, message: str | None = None
):
    """Create datetime range validator"""

    def validator(value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return value

        if not isinstance(value, datetime):
            raise ValidationError(message or "Value must be a datetime", field=field_name, code="invalid_datetime")

        if min_date and value < min_date:
            raise ValidationError(message or f"Date must be after {min_date}", field=field_name, code="min_date")

        if max_date and value > max_date:
            raise ValidationError(message or f"Date must be before {max_date}", field=field_name, code="max_date")

        return value

    return validator
