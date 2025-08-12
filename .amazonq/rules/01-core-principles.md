# SQLObjects Core Development Principles

## Project Context

SQLObjects is a Django-style async ORM library built on SQLAlchemy with chainable queries, Q objects, relationship
loading, and comprehensive validation system.

## Core Development Principles

### 1. Python Environment Standards

- **Python Version**: Use Python 3.12+ exclusively
- **Package Manager**: Always use `uv` for all operations
- **Command Execution**: Prefix all commands with `uv run`
- **Type Checker**: Use `pyright` as the primary type checker

### 2. Code Style and Formatting

- **Line Length**: Maximum 120 characters
- **Formatter**: Use Ruff for code formatting
- **Import Order**: Standard library → Third-party → Local imports
- **Code Quality**: MUST run `uv run ruff format` and `uv run ruff check` before committing

```bash
# Format code
uv run ruff format sqlobjects/ tests/

# Check for linting issues
uv run ruff check sqlobjects/ tests/

# Fix auto-fixable issues
uv run ruff check --fix sqlobjects/ tests/
```

### 3. Module Standards

- **__all__ Definition**: Every module MUST define `__all__` to explicitly control public API
- **Import Preferences**: Always import from `sqlobjects` and its subpackages
- **Documentation Language**: All comments, docstrings, and exception messages MUST be in English
- **Method Organization**: Group methods by functionality with clear section headers

### 4. SQLAlchemy Integration Standards

- **Latest Version Compliance**: Always follow SQLAlchemy latest version best practices, no backward compatibility
  considerations
- **Standard Feature Priority**: Prioritize using or extending SQLAlchemy's standard functionality over custom
  implementations
- **Modern SQLAlchemy 2.0+ Patterns**: Use `mapped_column`, `Mapped` annotations, and modern declarative syntax
- **Async-First Design**: All database operations must be async-compatible using SQLAlchemy's async engine

### 5. Operator Implementation Principles

- **Avoid Reverse Operators**: Do not implement `__rand__`, `__ror__` etc. unless there are clear, tested use cases
- **Type Compatibility**: Ensure custom types have well-defined interaction patterns with SQLAlchemy expressions
- **Simplicity First**: Prioritize simple, explicit API design over complex syntax sugar that adds maintenance burden

## Async Programming Rules

### 1. Database Operations

- **All database operations MUST be async**
- Always use `await` for database calls
- Use `async def` for any function performing I/O

```python
# Correct
async def get_user_posts(user_id: int) -> list[Post]:
    user = await User.objects.get(User.id == user_id)
    return await user.posts.all()
```

### 2. Session Management with using() Method

SQLObjects uses the `using()` method pattern for session specification:

#### Method Pattern

```python
# Default session usage
user = await User.objects.create(username="john")

# Specific session usage
user = await User.objects.using(session).create(username="john")
user = await User.objects.using("database_name").create(username="john")

# Model instance with specific session
user = User(username="john")
await user.using(session).save()
```

#### Benefits of This Pattern

1. **Clean API**: No session parameters cluttering method signatures
2. **Multi-database Support**: Easy to specify which database to use
3. **Flexible Session Types**: Accepts AsyncSession instances or database names
4. **Consistent**: Same pattern across ObjectsManager, QuerySet, and model instances

## Naming Conventions

### Table Name Generation

SQLObjects automatically generates table names using Rails conventions:

```python
from sqlobjects.utils.naming import to_snake_case, to_camel_case
from sqlobjects.utils.pattern import pluralize, singularize

# Naming conversion examples
to_snake_case("UserProfile")    # → "user_profile"
to_snake_case("XMLParser")      # → "xml_parser"
to_camel_case("user_profile")   # → "UserProfile"
pluralize("user_profile")       # → "user_profiles"

# Model to table name conversion
from sqlobjects.base import ObjectModel

class UserProfile(ObjectModel):  # → table: "user_profiles"
class XMLParser(ObjectModel):    # → table: "xml_parsers"
class HTTPRequest(ObjectModel):  # → table: "http_requests"
```

### Naming Utility Functions

```python
# Convert between naming styles
from sqlobjects.utils.naming import to_snake_case, to_camel_case

# CamelCase to snake_case
snake_name = to_snake_case("UserProfile")  # "user_profile"

# snake_case to CamelCase
camel_name = to_camel_case("user_profile")          # "UserProfile" (PascalCase)
camel_name = to_camel_case("user_profile", False)   # "userProfile" (camelCase)

# Pluralization utilities
from sqlobjects.utils.pattern import pluralize, singularize, is_plural

plural = pluralize("user")        # "users"
singular = singularize("users")   # "user"
check = is_plural("users")        # True
```

## Error Messages

### 1. English-Only Messages

All error messages and user-facing text are in English. The system provides clear, descriptive error messages for
validation failures and other exceptions.

```python
from sqlobjects.exceptions import create_validation_error

# Create validation errors with English messages
error = create_validation_error("required", field="email")
print(error.message)  # "This field is required"

error = create_validation_error("min_length", params={"min_length": 3})
print(error.message)  # "Ensure this value has at least 3 characters"
```

### 2. Built-in Error Messages

The system includes comprehensive English error messages for:

- Field validation (required, length, format)
- Type validation (email, URL, numeric)
- File validation (size, type, existence)
- Database operations (not found, multiple results)
- Model operations (creation, update failures)

## Model Definition Standards

### 1. ObjectModel Base Class

All models inherit from `ObjectModel` which provides:

- Automatic table name generation (Rails-style pluralization)
- Configuration support through `Config` inner class
- Validation system integration
- Signal system integration
- Objects manager (`objects` attribute)

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column, int_column

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    age: Column[int] = int_column()
    
    class Config:
        table_name = "users"  # Optional: overrides auto-generated name
        ordering = ["-created_at"]
```

### 2. Unified Type System Architecture

SQLObjects features a unified type system with automatic parameter extraction and transformation support:

```python
from typing import Any, Callable, NotRequired, TypedDict

class TypeArgument(TypedDict):
    name: str
    type: type
    required: bool
    default: Any
    transform: NotRequired[Callable[[Any], Any]]  # Optional value transformation
    positional: NotRequired[bool]  # Optional positional parameter flag

class TypeDefinition(TypedDict):
    type: type
    arguments: list[TypeArgument]

# Type registration with LRU cache and lazy initialization
from functools import lru_cache

class TypeRegistry:
    def __init__(self):
        self._types: dict[str, TypeDefinition] = {}
        self._aliases: dict[str, str] = {}  # Type alias mapping
        self._initialized = False  # Lazy initialization flag
    
    @lru_cache(maxsize=128)  # LRU cache for lookup performance
    def get_type(self, name: str) -> TypeDefinition:
        if not self._initialized:
            self._init_builtin_types()  # Initialize on first access
        return self._types.get(self._resolve_alias(name))

# Field definition with type-safe annotations
name: Column[str] = str_column(length=50, nullable=False)
age: Column[int] = int_column(nullable=False)
is_active: Column[bool] = bool_column(default=True, nullable=False)

# Advanced parameters for dataclass behavior
internal_id: Column[str] = str_column(init=False, repr=False)  # Internal field
api_key: Column[str] = str_column(default_factory=generate_key, repr=False)

# Array types with transform function
tags: Column[list[str]] = array_column("string")  # item_type transformed via _transform_array_item_type
matrix: Column[list[list[int]]] = array_column("integer", dimensions=2)

# Enum types with positional parameter
status: Column[UserStatus] = enum_column(UserStatus, default=UserStatus.ACTIVE)  # enum_class as positional
```