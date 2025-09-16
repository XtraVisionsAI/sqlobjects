from typing import Any

from sqlalchemy.exc import DataError as SQLADataError
from sqlalchemy.exc import DisconnectionError as SQLADisconnectionError
from sqlalchemy.exc import IntegrityError as SQLAIntegrityError
from sqlalchemy.exc import OperationalError as SQLAOperationalError
from sqlalchemy.exc import ProgrammingError as SQLAProgrammingError
from sqlalchemy.exc import SQLAlchemyError


__all__ = [
    "SQLObjectsError",
    "DoesNotExist",
    "MultipleObjectsReturned",
    "ValidationError",
    "ValidationErrorCollector",
    "DatabaseError",
    "IntegrityError",
    "TransactionError",
    "ConfigurationError",
    "DeferredFieldError",
    "PrimaryKeyError",
    "SQLError",
    "OperationalError",
    "DataError",
    "ProgrammingError",
    "convert_sqlalchemy_error",
]


class SQLObjectsError(Exception):
    """Base exception class for all SQLObjects-related errors.

    This is the root exception class that all other SQLObjects exceptions
    inherit from. It can be used to catch any SQLObjects-specific error.

    Examples:
        >>> try:
        ...     # SQLObjects operations
        ...     pass
        ... except SQLObjectsError as e:
        ...     # Handle any SQLObjects error
        ...     print(f"SQLObjects error: {e}")
    """

    pass


class DoesNotExist(SQLObjectsError):
    """Raised when a database query returns no results when one was expected.

    This exception is typically raised by get() methods when no object
    matches the specified criteria.

    Examples:
        >>> try:
        ...     user = await User.objects.get(id=999)
        ... except DoesNotExist:
        ...     print("User not found")
    """

    pass


class MultipleObjectsReturned(SQLObjectsError):
    """Raised when a query returns multiple objects when only one was expected.

    This exception is typically raised by get() methods when multiple objects
    match the specified criteria.

    Examples:
        >>> try:
        ...     user = await User.objects.get(name="John")
        ... except MultipleObjectsReturned:
        ...     print("Multiple users found with name 'John'")
    """

    pass


class ValidationError(SQLObjectsError):
    """Raised when data validation fails during model operations.

    This exception supports both single field validation errors and multiple
    field validation errors. It provides detailed information about what
    validation failed and why.

    Attributes:
        field: Name of the field that failed validation (for single errors)
        message: Human-readable error message
        code: Error code for programmatic handling
        params: Parameters used in the error message
        field_errors: Dictionary of field names to error lists (for multiple errors)
        model_class: Name of the model class where validation failed
        operation: Operation that triggered the validation (e.g., 'create', 'update')
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        """Initialize a validation error.

        Args:
            message: Human-readable error message
            field: Name of the field that failed validation (for single errors)
            code: Error code for programmatic handling
            params: Parameters used in the error message
            field_errors: Dictionary of field names to error lists (for multiple errors)

        Examples:
            >>> # Single field error
            >>> raise ValidationError("Email is required", field="email", code="required")
            >>> # Multiple field errors
            >>> errors = {"email": ["Email is required"], "age": ["Age must be positive"]}
            >>> raise ValidationError("Validation failed", field_errors=errors)
        """
        super().__init__(message)
        self.field = field
        self.message = message
        self.code = code or "invalid"
        self.params = params or {}
        self.field_errors = field_errors or {}
        self.model_class: str | None = None
        self.operation: str | None = None

    @property
    def is_multiple(self) -> bool:
        """Check if this validation error contains multiple field errors.

        Returns:
            True if this error contains multiple field errors, False otherwise

        Examples:
            >>> error = ValidationError("Email is required", field="email")
            >>> error.is_multiple  # False
            >>> errors = {"email": ["Required"], "age": ["Invalid"]}
            >>> error = ValidationError("Multiple errors", field_errors=errors)
            >>> error.is_multiple  # True
        """
        return bool(self.field_errors)

    def add_field_error(self, field: str, message: str) -> None:
        """Add a validation error for a specific field.

        Args:
            field: Name of the field
            message: Error message for the field

        Examples:
            >>> error = ValidationError("Validation failed")
            >>> error.add_field_error("email", "Email is required")
            >>> error.add_field_error("email", "Email format is invalid")
        """
        if field not in self.field_errors:
            self.field_errors[field] = []
        self.field_errors[field].append(message)

    def get_field_errors(self, field: str) -> list[str]:
        """Get all validation errors for a specific field.

        Args:
            field: Name of the field

        Returns:
            List of error messages for the specified field

        Examples:
            >>> errors = {"email": ["Required", "Invalid format"]}
            >>> error = ValidationError("Multiple errors", field_errors=errors)
            >>> error.get_field_errors("email")  # ["Required", "Invalid format"]
            >>> error.get_field_errors("name")  # []
        """
        return self.field_errors.get(field, [])

    def to_dict(self) -> dict[str, Any]:
        """Convert the validation error to a dictionary format suitable for APIs.

        Returns:
            Dictionary representation of the validation error

        Examples:
            >>> # Single field error
            >>> error = ValidationError("Email is required", field="email", code="required")
            >>> error.to_dict()
            {'message': 'Email is required', 'code': 'required', 'field': 'email'}

            >>> # Multiple field errors
            >>> errors = {"email": ["Required"], "age": ["Invalid"]}
            >>> error = ValidationError("Validation failed", field_errors=errors)
            >>> error.to_dict()
            {'message': 'Validation failed', 'field_errors': {...}, 'error_count': 2}
        """
        if self.is_multiple:
            # Multiple field errors format
            return {
                "message": self.message,
                "field_errors": self.field_errors,
                "error_count": sum(len(errors) for errors in self.field_errors.values()),
            }
        else:
            # Single field error format
            result: dict = {"message": self.message, "code": self.code}
            if self.field:
                result["field"] = self.field
            if self.params:
                result["params"] = self.params
            return result


class ValidationErrorCollector:
    """Helper class for collecting multiple validation errors before raising.

    This class provides a convenient way to collect validation errors from
    multiple fields and then raise a single ValidationError with all the
    collected errors.

    Examples:
        >>> collector = ValidationErrorCollector()
        >>> if not user.email:
        ...     collector.add_error("email", "Email is required")
        >>> if user.age < 0:
        ...     collector.add_error("age", "Age must be positive")
        >>> collector.raise_if_errors()  # Raises ValidationError if any errors
    """

    def __init__(self) -> None:
        """Initialize an empty error collector."""
        self._errors: dict[str, list[str]] = {}

    def add_error(self, field: str, message: str) -> None:
        """Add a validation error for a specific field.

        Args:
            field: Name of the field that has the error
            message: Error message describing the validation failure

        Examples:
            >>> collector = ValidationErrorCollector()
            >>> collector.add_error("email", "Email is required")
            >>> collector.add_error("email", "Email format is invalid")
        """
        if field not in self._errors:
            self._errors[field] = []
        self._errors[field].append(message)

    def has_errors(self) -> bool:
        """Check if any validation errors have been collected.

        Returns:
            True if there are any errors, False otherwise

        Examples:
            >>> collector = ValidationErrorCollector()
            >>> collector.has_errors()  # False
            >>> collector.add_error("email", "Required")
            >>> collector.has_errors()  # True
        """
        return bool(self._errors)

    def raise_if_errors(self) -> None:
        """Raise a ValidationError if any errors have been collected.

        Raises:
            ValidationError: If there are any collected errors

        Examples:
            >>> collector = ValidationErrorCollector()
            >>> collector.add_error("email", "Required")
            >>> collector.raise_if_errors()  # Raises ValidationError
        """
        if self.has_errors():
            field_count = len(self._errors)
            total_errors = sum(len(errors) for errors in self._errors.values())
            message = f"Validation failed for {field_count} field(s) with {total_errors} error(s)"
            raise ValidationError(message, field_errors=self._errors)

    @property
    def errors(self) -> dict[str, list[str]]:
        """Get a copy of all collected errors.

        Returns:
            Dictionary mapping field names to lists of error messages

        Examples:
            >>> collector = ValidationErrorCollector()
            >>> collector.add_error("email", "Required")
            >>> collector.errors  # {"email": ["Required"]}
        """
        return self._errors.copy()


class DatabaseError(SQLObjectsError):
    """Raised when a database operation fails.

    This is a general exception for database-related errors that don't
    fall into more specific categories like IntegrityError or TransactionError.

    Examples:
        >>> try:
        ...     await db.execute("INVALID SQL")
        ... except DatabaseError as e:
        ...     print(f"Database error: {e}")
    """

    pass


class IntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated.

    This exception is typically raised when operations violate database
    constraints such as unique constraints, foreign key constraints, or
    check constraints.

    Examples:
        >>> try:
        ...     await User.objects.create(email="existing@example.com")
        ... except IntegrityError:
        ...     print("Email already exists")
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


class TransactionError(DatabaseError):
    """Raised when a database transaction operation fails.

    This exception is raised for transaction-specific errors such as
    deadlocks, transaction rollbacks, or commit failures.

    Examples:
        >>> try:
        ...     async with session.begin():
        ...         # Database operations that might cause deadlock
        ...         pass
        ... except TransactionError as e:
        ...     print(f"Transaction failed: {e}")
    """

    pass


class ConfigurationError(SQLObjectsError):
    """Raised when there is an error in SQLObjects configuration.

    This exception is raised when invalid configuration is detected,
    such as invalid database URLs, missing required settings, or
    conflicting configuration options.

    Examples:
        >>> try:
        ...     init_db("invalid://database/url")
        ... except ConfigurationError as e:
        ...     print(f"Configuration error: {e}")
    """

    pass


class DeferredFieldError(SQLObjectsError):
    """Raised when accessing a deferred field that hasn't been loaded.

    This exception is raised when trying to access a field that was
    deferred during the query and hasn't been explicitly loaded.

    Examples:
        >>> try:
        ...     content = article.content  # deferred field
        ... except DeferredFieldError:
        ...     await article.load_deferred_field("content")
    """

    def __init__(self, field_name: str):
        self.field_name = field_name
        super().__init__(f"Deferred field '{field_name}' not loaded")


class PrimaryKeyError(SQLObjectsError):
    """Raised when there's an issue with primary key operations.

    This exception is raised for primary key related errors such as
    missing primary key values for update/delete operations.

    Examples:
        >>> try:
        ...     await user.delete()  # user has no primary key
        ... except PrimaryKeyError:
        ...     print("Cannot delete without primary key")
    """

    def __init__(self, message: str, operation: str | None = None):
        self.operation = operation
        super().__init__(message)


class SQLError(SQLObjectsError):
    """Base class for SQLAlchemy operation errors.

    This exception wraps SQLAlchemy errors to provide a consistent
    exception interface for SQLObjects users.
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


class OperationalError(SQLError):
    """Database operational errors (connection, timeout, etc.).

    This exception is raised for operational database errors such as
    connection failures, timeouts, or server unavailability.
    """

    pass


class DataError(SQLError):
    """Data-related errors (invalid values, type conversion).

    This exception is raised for data-related errors such as invalid
    data types, constraint violations, or conversion failures.
    """

    pass


class ProgrammingError(SQLError):
    """SQL programming errors (syntax, missing tables).

    This exception is raised for programming errors such as SQL syntax
    errors, missing tables, or invalid column references.
    """

    pass


def convert_sqlalchemy_error(error: Exception) -> SQLObjectsError:
    """Convert SQLAlchemy exceptions to SQLObjects exceptions.

    Args:
        error: SQLAlchemy exception to convert

    Returns:
        Corresponding SQLObjects exception

    Examples:
        >>> try:
        ...     # SQLAlchemy operation
        ...     pass
        ... except SQLAlchemyError as e:
        ...     raise convert_sqlalchemy_error(e)
    """
    error_msg = str(error)

    if isinstance(error, SQLAIntegrityError):
        return IntegrityError(error_msg, original_error=error)
    elif isinstance(error, SQLAOperationalError):
        return OperationalError(error_msg, original_error=error)
    elif isinstance(error, SQLADataError):
        return DataError(error_msg, original_error=error)
    elif isinstance(error, SQLAProgrammingError):
        return ProgrammingError(error_msg, original_error=error)
    elif isinstance(error, SQLADisconnectionError):
        return OperationalError(error_msg, original_error=error)
    elif isinstance(error, SQLAlchemyError):
        return SQLError(error_msg, original_error=error)
    else:
        # Not a SQLAlchemy error, return as-is or wrap in generic SQLError
        return SQLError(error_msg, original_error=error)
