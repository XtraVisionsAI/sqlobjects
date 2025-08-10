import json
import re
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .exceptions import create_validation_error


__all__ = [
    "BaseValidator",
    "LengthValidator",
    "EmailValidator",
    "URLValidator",
    "RangeValidator",
    "RegexValidator",
    "ChoicesValidator",
    "DateValidator",
    "TimeValidator",
    "DecimalValidator",
    "JSONValidator",
    "FileValidator",
    "ImageValidator",
    "combine_validators",
]


class BaseValidator:
    """Abstract base class for all field validators.

    This class defines the interface that all validators must implement.
    Validators are callable objects that take a value and raise a
    ValidationError if the value is invalid.

    Examples:
        >>> class CustomValidator(BaseValidator):
        ...     def __call__(self, value: Any) -> None:
        ...         if value is not None and value < 0:
        ...             raise create_validation_error("invalid")
        >>> validator = CustomValidator()
        >>> validator(10)  # OK
        >>> validator(-5)  # Raises ValidationError
    """

    def __call__(self, value: Any) -> None:
        """Validate the given value.

        Args:
            value: The value to validate

        Raises:
            ValidationError: If the value is invalid
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("This method must be implemented by subclasses")


class LengthValidator(BaseValidator):
    """Validator for string length constraints.

    Validates that the string representation of a value falls within
    specified minimum and maximum length bounds.

    Examples:
        >>> # Validate minimum length
        >>> validator = LengthValidator(min_length=3)
        >>> validator("hello")  # OK
        >>> validator("hi")  # Raises ValidationError
        >>> # Validate maximum length
        >>> validator = LengthValidator(max_length=10)
        >>> validator("short")  # OK
        >>> validator("very long string")  # Raises ValidationError
        >>> # Validate both min and max
        >>> validator = LengthValidator(min_length=3, max_length=10)
        >>> validator("hello")  # OK
    """

    def __init__(self, min_length: int | None = None, max_length: int | None = None) -> None:
        """Initialize the length validator.

        Args:
            min_length: Minimum allowed length (inclusive)
            max_length: Maximum allowed length (inclusive)
        """
        self.min_length = min_length
        self.max_length = max_length

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        length = len(str(value))

        if self.min_length is not None and length < self.min_length:
            raise create_validation_error("min_length", params={"min_length": self.min_length})

        if self.max_length is not None and length > self.max_length:
            raise create_validation_error("max_length", params={"max_length": self.max_length})


class EmailValidator(BaseValidator):
    """Validator for email address format.

    Validates that a string matches a basic email address pattern.
    Uses a regex pattern to check for valid email structure.

    Examples:
        >>> validator = EmailValidator()
        >>> validator("user@example.com")  # OK
        >>> validator("test.email@domain.co.uk")  # OK
        >>> validator("invalid-email")  # Raises ValidationError
        >>> validator("@domain.com")  # Raises ValidationError
    """

    pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid")

        if not self.pattern.match(value):
            raise create_validation_error("invalid_email")


class URLValidator(BaseValidator):
    """Validator for URL format.

    Validates that a string matches a valid HTTP or HTTPS URL pattern.
    Supports domain names, localhost, and IP addresses with optional ports.

    Examples:
        >>> validator = URLValidator()
        >>> validator("https://example.com")  # OK
        >>> validator("http://localhost:8000")  # OK
        >>> validator("https://192.168.1.1:3000/path")  # OK
        >>> validator("ftp://example.com")  # Raises ValidationError
        >>> validator("not-a-url")  # Raises ValidationError
    """

    pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid")

        if not self.pattern.match(value):
            raise create_validation_error("invalid_url")


class RangeValidator(BaseValidator):
    """Validator for numeric range constraints.

    Validates that a numeric value falls within specified minimum
    and maximum bounds. Converts values to float for comparison.

    Examples:
        >>> # Validate minimum value
        >>> validator = RangeValidator(min_value=0)
        >>> validator(5)  # OK
        >>> validator(-1)  # Raises ValidationError
        >>> # Validate maximum value
        >>> validator = RangeValidator(max_value=100)
        >>> validator(50)  # OK
        >>> validator(150)  # Raises ValidationError
        >>> # Validate range
        >>> validator = RangeValidator(min_value=0, max_value=100)
        >>> validator(50)  # OK
    """

    def __init__(self, min_value: float | None = None, max_value: float | None = None) -> None:
        """Initialize the range validator.

        Args:
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
        """
        self.min_value = min_value
        self.max_value = max_value

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        try:
            num_value = float(value)
        except (ValueError, TypeError) as e:
            raise create_validation_error("invalid") from e

        if self.min_value is not None and num_value < self.min_value:
            raise create_validation_error("min_value", params={"min_value": self.min_value})

        if self.max_value is not None and num_value > self.max_value:
            raise create_validation_error("max_value", params={"max_value": self.max_value})


class RegexValidator(BaseValidator):
    r"""Validator for regular expression pattern matching.

    Validates that a string value matches a specified regular expression pattern.

    Examples:
        >>> # Validate alphanumeric strings
        >>> validator = RegexValidator(r"^[a-zA-Z0-9]+$")
        >>> validator("abc123")  # OK
        >>> validator("abc-123")  # Raises ValidationError
        >>> # Case-insensitive validation
        >>> validator = RegexValidator(r"^[a-z]+$", re.IGNORECASE)
        >>> validator("ABC")  # OK
        >>> # Phone number validation
        >>> validator = RegexValidator(r"^\d{3}-\d{3}-\d{4}$")
        >>> validator("123-456-7890")  # OK
    """

    def __init__(self, pattern: str, flags: int = 0) -> None:
        """Initialize the regex validator.

        Args:
            pattern: Regular expression pattern string
            flags: Regex flags (e.g., re.IGNORECASE, re.MULTILINE)
        """
        self.regex = re.compile(pattern, flags)

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid")

        if not self.regex.match(value):
            raise create_validation_error("invalid")


class ChoicesValidator(BaseValidator):
    """Validator for allowed choice values.

    Validates that a value is one of a predefined set of allowed choices.

    Examples:
        >>> # String choices
        >>> validator = ChoicesValidator(["red", "green", "blue"])
        >>> validator("red")  # OK
        >>> validator("yellow")  # Raises ValidationError
        >>> # Numeric choices
        >>> validator = ChoicesValidator([1, 2, 3, 5, 8])
        >>> validator(3)  # OK
        >>> validator(4)  # Raises ValidationError
        >>> # Mixed type choices
        >>> validator = ChoicesValidator(["active", "inactive", 1, 0])
        >>> validator("active")  # OK
        >>> validator(1)  # OK
    """

    def __init__(self, choices: list[Any]) -> None:
        """Initialize the choices validator.

        Args:
            choices: List of allowed values
        """
        self.choices = choices

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        if value not in self.choices:
            raise create_validation_error("invalid_choice", params={"value": value})


class DateValidator(BaseValidator):
    """Validator for date format and values.

    Validates that a value is a valid date, either as a date object
    or as a string that can be parsed according to a specified format.

    Examples:
        >>> # Default ISO format validation
        >>> validator = DateValidator()
        >>> validator("2023-12-25")  # OK
        >>> validator("12/25/2023")  # Raises ValidationError
        >>> # Custom format validation
        >>> validator = DateValidator("%m/%d/%Y")
        >>> validator("12/25/2023")  # OK
        >>> validator("2023-12-25")  # Raises ValidationError
        >>> # Date object validation
        >>> from datetime import date
        >>> validator(date(2023, 12, 25))  # OK
    """

    def __init__(self, date_format: str = "%Y-%m-%d") -> None:
        """Initialize the date validator.

        Args:
            date_format: Expected date format string using Python strftime format codes.
                        Default is "%Y-%m-%d" for ISO format (YYYY-MM-DD)
        """
        self.date_format = date_format

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        # If already a date object, it's valid
        if isinstance(value, date):
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid_date")

        try:
            datetime.strptime(value, self.date_format)
        except ValueError as e:
            raise create_validation_error("invalid_date", params={"format": self.date_format}) from e


class TimeValidator(BaseValidator):
    """Validator for time format and values.

    Validates that a value is a valid time, either as a time object
    or as a string that can be parsed according to a specified format.

    Examples:
        >>> # Default 24-hour format validation
        >>> validator = TimeValidator()
        >>> validator("14:30:00")  # OK
        >>> validator("2:30 PM")  # Raises ValidationError
        >>> # Custom format validation
        >>> validator = TimeValidator("%I:%M %p")
        >>> validator("2:30 PM")  # OK
        >>> validator("14:30:00")  # Raises ValidationError
        >>> # Time object validation
        >>> from datetime import time
        >>> validator(time(14, 30, 0))  # OK
    """

    def __init__(self, time_format: str = "%H:%M:%S") -> None:
        """Initialize the time validator.

        Args:
            time_format: Expected time format string using Python strftime format codes.
                        Default is "%H:%M:%S" for 24-hour format (HH:MM:SS)
        """
        self.time_format = time_format

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        # If already a time object, it's valid
        if isinstance(value, time):
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid_time")

        try:
            datetime.strptime(value, self.time_format)
        except ValueError as e:
            raise create_validation_error("invalid_time", params={"format": self.time_format}) from e


class DecimalValidator(BaseValidator):
    """Validator for decimal precision and scale constraints.

    Validates that a numeric value meets specified precision (total digits)
    and scale (decimal places) requirements. Accepts int, float, string,
    and Decimal values.

    Examples:
        >>> # Validate maximum total digits
        >>> validator = DecimalValidator(max_digits=5)
        >>> validator("123.45")  # OK (5 digits total)
        >>> validator("123456")  # Raises ValidationError (6 digits)
        >>> # Validate decimal places
        >>> validator = DecimalValidator(decimal_places=2)
        >>> validator("123.45")  # OK (2 decimal places)
        >>> validator("123.456")  # Raises ValidationError (3 decimal places)
        >>> # Validate both precision and scale
        >>> validator = DecimalValidator(max_digits=5, decimal_places=2)
        >>> validator("123.45")  # OK
        >>> validator("1234.567")  # Raises ValidationError
    """

    def __init__(self, max_digits: int | None = None, decimal_places: int | None = None) -> None:
        """Initialize the decimal validator.

        Args:
            max_digits: Maximum total number of digits allowed
            decimal_places: Maximum number of decimal places allowed
        """
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        try:
            if isinstance(value, int | float):
                decimal_value = Decimal(str(value))
            elif isinstance(value, str):
                decimal_value = Decimal(value)
            elif isinstance(value, Decimal):
                decimal_value = value
            else:
                raise create_validation_error("invalid_decimal")
        except (InvalidOperation, ValueError) as e:
            raise create_validation_error("invalid_decimal") from e

        # Validate digits and decimal places
        if self.max_digits is not None or self.decimal_places is not None:
            _, digits, exponent = decimal_value.as_tuple()

            # Check total digits
            if self.max_digits is not None:
                total_digits = len(digits)
                if total_digits > self.max_digits:
                    raise create_validation_error(
                        "max_digits", params={"max_digits": self.max_digits, "digits": total_digits}
                    )

            # Check decimal places
            if self.decimal_places is not None and isinstance(exponent, int) and exponent < 0:
                decimal_places = -exponent
                if decimal_places > self.decimal_places:
                    raise create_validation_error(
                        "max_decimal_places",
                        params={"max_decimal_places": self.decimal_places, "decimal_places": decimal_places},
                    )


class JSONValidator(BaseValidator):
    """Validator for JSON format.

    Validates that a string value contains valid JSON that can be parsed
    without errors.

    Examples:
        >>> validator = JSONValidator()
        >>> validator('{"name": "John", "age": 30}')  # OK
        >>> validator("[1, 2, 3]")  # OK
        >>> validator('"simple string"')  # OK
        >>> validator("{invalid json}")  # Raises ValidationError
        >>> validator("undefined")  # Raises ValidationError
    """

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        if not isinstance(value, str):
            raise create_validation_error("invalid_json")

        try:
            json.loads(value)
        except json.JSONDecodeError as e:
            raise create_validation_error("invalid_json", params={"error": str(e)}) from e


class FileValidator(BaseValidator):
    """Validator for file type and size constraints.

    Validates file paths or file-like objects against extension whitelist
    and size constraints. Supports both file path strings and file objects.

    Examples:
        >>> # Validate file extensions
        >>> validator = FileValidator(allowed_extensions=["txt", "pdf"])
        >>> validator("/path/to/document.pdf")  # OK
        >>> validator("/path/to/image.jpg")  # Raises ValidationError
        >>> # Validate file size (in bytes)
        >>> validator = FileValidator(max_size=1024 * 1024)  # 1MB limit
        >>> validator("/path/to/small_file.txt")  # OK if < 1MB
        >>> # Combined validation
        >>> validator = FileValidator(
        ...     allowed_extensions=["jpg", "png"],
        ...     max_size=5 * 1024 * 1024,  # 5MB
        ...     min_size=1024,  # 1KB
        ... )
    """

    def __init__(
        self,
        allowed_extensions: list[str] | None = None,
        max_size: int | None = None,
        min_size: int | None = None,
    ) -> None:
        """Initialize the file validator.

        Args:
            allowed_extensions: List of allowed file extensions (without dots)
            max_size: Maximum file size in bytes
            min_size: Minimum file size in bytes
        """
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or [])]
        self.max_size = max_size  # in bytes
        self.min_size = min_size  # in bytes

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        # Handle file path string
        if isinstance(value, str):
            file_path = Path(value)
            if not file_path.exists():
                raise create_validation_error("file_not_found", params={"path": value})

            # Check extension
            if self.allowed_extensions:
                extension = file_path.suffix.lower().lstrip(".")
                if extension not in self.allowed_extensions:
                    raise create_validation_error(
                        "invalid_file_extension",
                        params={"extension": extension, "allowed": self.allowed_extensions},
                    )

            # Check file size
            try:
                file_size = file_path.stat().st_size
                if self.min_size is not None and file_size < self.min_size:
                    raise create_validation_error(
                        "file_too_small", params={"size": file_size, "min_size": self.min_size}
                    )
                if self.max_size is not None and file_size > self.max_size:
                    raise create_validation_error(
                        "file_too_large", params={"size": file_size, "max_size": self.max_size}
                    )
            except OSError as e:
                raise create_validation_error("file_access_error", params={"error": str(e)}) from e

        # Handle file-like objects (basic validation)
        elif hasattr(value, "read") and hasattr(value, "name"):
            if self.allowed_extensions and hasattr(value, "name"):
                file_path = Path(value.name)
                extension = file_path.suffix.lower().lstrip(".")
                if extension not in self.allowed_extensions:
                    raise create_validation_error(
                        "invalid_file_extension",
                        params={"extension": extension, "allowed": self.allowed_extensions},
                    )
        else:
            raise create_validation_error("invalid_file")


class ImageValidator(BaseValidator):
    """Validator for image file type and dimensions.

    Validates image files against extension whitelist, file size, and
    dimension constraints. Currently validates extensions and file size;
    dimension validation requires PIL/Pillow library.

    Examples:
        >>> # Basic image validation
        >>> validator = ImageValidator()
        >>> validator("/path/to/image.jpg")  # OK
        >>> validator("/path/to/document.txt")  # Raises ValidationError
        >>> # Custom extensions and size limit
        >>> validator = ImageValidator(
        ...     allowed_extensions=["jpg", "png"],
        ...     max_size=2 * 1024 * 1024,  # 2MB
        ... )
        >>> # With dimension constraints (requires PIL)
        >>> validator = ImageValidator(max_width=1920, max_height=1080, min_width=100, min_height=100)
    """

    # Common image extensions
    DEFAULT_EXTENSIONS = ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg"]

    def __init__(
        self,
        allowed_extensions: list[str] | None = None,
        max_width: int | None = None,
        max_height: int | None = None,
        min_width: int | None = None,
        min_height: int | None = None,
        max_size: int | None = None,
    ) -> None:
        """Initialize the image validator.

        Args:
            allowed_extensions: List of allowed image extensions (default: common formats)
            max_width: Maximum image width in pixels
            max_height: Maximum image height in pixels
            min_width: Minimum image width in pixels
            min_height: Minimum image height in pixels
            max_size: Maximum file size in bytes
        """
        self.allowed_extensions = [ext.lower().lstrip(".") for ext in (allowed_extensions or self.DEFAULT_EXTENSIONS)]
        self.max_width = max_width
        self.max_height = max_height
        self.min_width = min_width
        self.min_height = min_height
        self.max_size = max_size

    def __call__(self, value: Any) -> None:
        if value is None:
            return

        # First validate as a file
        file_validator = FileValidator(allowed_extensions=self.allowed_extensions, max_size=self.max_size)
        file_validator(value)

        # Additional image-specific validation would require PIL/Pillow
        # For now, we just validate the extension
        if isinstance(value, str):
            file_path = Path(value)
            extension = file_path.suffix.lower().lstrip(".")
            if extension not in self.allowed_extensions:
                raise create_validation_error(
                    "invalid_image_format",
                    params={"extension": extension, "allowed": self.allowed_extensions},
                )


def combine_validators(*validators: Callable) -> Callable:
    """Combine multiple validators into a single validator.

    The combined validator runs all provided validators in sequence. If any
    validator raises a ValidationError, the validation stops and the error
    is propagated. All validators must pass for the value to be considered valid.

    Args:
        *validators: Variable number of validator functions that take a value
                    and raise ValidationError if invalid

    Returns:
        A combined validator function that runs all validators in sequence
        and raises ValidationError if any individual validator fails

    Examples:
        >>> # Combine length and pattern validation for usernames
        >>> username_validator = combine_validators(
        ...     validate_length(min_length=3, max_length=50), validate_regex(r"^[a-zA-Z0-9_]+$")
        ... )
        >>> username_validator("test123")  # OK (passes both length and regex)
        >>> username_validator("ab")  # Raises ValidationError (too short)
        >>> username_validator("test-123")  # Raises ValidationError (invalid character)
        >>> # Combine multiple constraints for email
        >>> email_validator = combine_validators(
        ...     validate_length(max_length=254),  # RFC 5321 limit
        ...     validate_email(),
        ... )
        >>> # Combine range and decimal validation for prices
        >>> price_validator = combine_validators(
        ...     validate_range(min_value=0), validate_decimal(max_digits=10, decimal_places=2)
        ... )
    """

    def combined_validator(value: Any) -> None:
        for validator in validators:
            validator(value)

    return combined_validator
