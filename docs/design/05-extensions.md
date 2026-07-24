# SQLObjects Extensions Design Document

## Overview

SQLObjects extensions provide enhanced functionality through built-in integration with ObjectModel, including signal
system, intelligent operation detection, performance optimization, and proxy system. Through Mixin composition patterns
and unified state management, it offers seamless integration capabilities for core functionality.

## Core Features

### 1. Built-in Signal System

ObjectModel includes SignalMixin by default, providing complete model lifecycle signals with method name convention discovery:

```python
from sqlobjects.model import ObjectModel  # SignalMixin already built-in
from sqlobjects.fields import Column, StringColumn
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime

class User(ObjectModel):  # Automatically has signal functionality
    name: Column[str] = StringColumn(length=50)
  
    # Instance-level signals - discovered by method name convention
    async def before_save(self, context: SignalContext):
        # context.actual_operation shows detected operation (CREATE or UPDATE)
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        await self.send_welcome_email()
  
    # Class-level batch signals
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        print(f"Creating {context.affected_count} users")

# Signal handler discovery mechanism:
# - Uses getattr() to find methods by name (before_save, after_create, etc.)
# - @emit_signals decorator calls _determine_save_operation() to detect CREATE/UPDATE
# - Emits dual signals for SAVE operations (both SAVE and CREATE/UPDATE)

user = User(name="John")  # No primary key value
await user.save()  # _determine_save_operation() returns CREATE
# Emits: before_save → before_create → after_save → after_create

user.name = "John Updated"
await user.save()  # _determine_save_operation() returns UPDATE
# Emits: before_save → before_update → after_save → after_update
```

### 2. Exception Handling

Hierarchical exception system providing detailed error information and unified error handling:

```python
# Exception hierarchy
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    print("User does not exist")
except ValidationError as e:
    if e.is_multiple:
        for field, errors in e.field_errors.items():
            print(f"{field}: {', '.join(errors)}")
except SQLObjectsError:
    print("SQLObjects operation error")

# Validation error collection
collector = ValidationErrorCollector()
collector.add_error("email", "Invalid email format")
collector.add_error("age", "Age must be positive")
collector.raise_if_errors()
```

### 3. Integrated Performance Optimization

Performance enhancement through batch operation optimization and FieldCacheMixin proxy system:

```python
# Batch operation optimization - uses bindparam and batch processing
await User.objects.bulk_create(users_data)  # automatic batching
affected = await User.objects.bulk_update(update_data, batch_size=500)

# FieldCacheMixin proxy system - automatically handles deferred fields
user = await User.objects.only("name").first()  # bio field deferred
# user.bio returns DeferredObject
# await user.bio.fetch() actually loads the data

# Relationship proxy - RelatedObject / RelatedCollection
# user.posts returns RelatedCollection
# await user.posts.fetch() loads relationship data
```

### 4. Utility Functions

Practical utility functions and helper classes that simplify common operations:

```python
# Naming conversion tools
from sqlobjects.utils.naming import to_snake_case, to_camel_case
from sqlobjects.utils.pattern import pluralize, singularize

snake_name = to_snake_case("UserProfile")  # "user_profile"
camel_name = to_camel_case("user_profile")  # "UserProfile"
plural = pluralize("user")                  # "users"

# Debugging tools
field_stats = User._get_field_cache()
print(f"Field categories: {list(field_stats.keys())}")
```

### 5. SQL Logging

SQLObjects ships a zero-configuration SQL logger (`sqlobjects/sql_logging.py`) that attributes each logged
statement to the user's own code rather than to a frame inside the library:

```python
import logging

# Enabling DEBUG on the "sqlobjects.sql" logger turns on SQL logging.
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)
logging.basicConfig()

users = await User.objects.filter(User.is_active == True).all()
# The emitted record's filename/lineno/funcName point at the caller in user code,
# not at executor.py or a SQLAlchemy internal frame.
```

- **ObjectLogger** (a `logging.Logger` subclass): overrides `makeRecord()` to rewrite the standard caller
  fields (`pathname`, `filename`, `module`, `funcName`, `lineno`) to the first user-code frame. Because the
  rewrite happens on the record, any attached handler — including loguru `InterceptHandler` — shows the real
  call site with no extra `Filter` configuration.
- **Frame-skipping** (`_find_user_frame` / `_should_skip_frame`): walks `inspect.stack()` and skips frames
  from `site-packages`, synthetic `<...>` filenames, modules named exactly `sqlobjects`/`sqlalchemy`/`logging`
  or prefixed with `sqlobjects.`/`sqlalchemy.` (covers editable installs), the `sql_logging.py` file itself,
  and any `extra_skip_packages` prefixes supplied by the caller.
- **Installation**: the module installs itself as the logger named `sqlobjects.sql` via
  `_install_object_logger()`, which writes the `ObjectLogger` directly into `logging.root.manager.loggerDict`
  (under the logging lock), migrating any pre-existing handlers/level/propagate. The `QueryExecutor` emits SQL
  through this logger, compiling SQL for logging only when the logger is enabled for `DEBUG` (avoiding overhead
  when logging is off).
- **Public API**: `ObjectLogger` and `get_caller_frame(extra_skip_packages=None, max_frames=1) -> str | list[str]`,
  which returns the first user-code frame(s) as `"path:lineno in func"` strings for custom scenarios.

## Module Architecture

### Core Components

**Model Integration Layer**

- **ObjectModel**: Complete model base class combining all Mixins with built-in extension functionality
- **ModelMixin**: Defined as `ModelMixin(DataConversionMixin, SignalMixin)` — the DataConversionMixin chain (which includes FieldCacheMixin) plus SignalMixin

**Signal System Layer**

- **SignalMixin**: Signal mixin class, built into ObjectModel
- **@emit_signals**: Signal decorator that automatically handles signal emission and operation detection
- **_determine_save_operation()**: Function that checks _has_primary_key_values() to detect CREATE vs UPDATE
- **_emit_signal()**: Function that discovers handlers by method name using getattr()
- **Operation**: Operation type enumeration supporting SAVE/CREATE/UPDATE/DELETE
- **SignalContext**: Dataclass containing operation, session, instance, and actual_operation

**Proxy System Layer**

- **DeferredObject**: Deferred field proxy supporting lazy loading and caching
- **RelatedObject**: Single relationship proxy (ForeignKey, OneToOne)
- **RelatedCollection**: Collection relationship proxy (OneToMany, ManyToMany)
- **FieldCacheMixin**: Integrates field cache and proxy system into __getattribute__

**State Management Layer**

- **_StateManager**: Internal unified instance state management supporting multiple state types
- **Dirty-field tracking**: Change detection is handled by `_StateManager` (tracked dirty fields), which is the basis for change history — there is no separate history mixin

**Performance Tools Layer**

- **FieldCache**: Field metadata caching mechanism integrated into model classes
- **ValidationError**: Layered exception system supporting single-field and multi-field errors

**SQL Logging Layer (`sql_logging.py`)**

- **ObjectLogger**: `logging.Logger` subclass that rewrites LogRecord caller fields to the user-code call site; installed as the `sqlobjects.sql` logger and used by `QueryExecutor`
- **get_caller_frame() / _find_user_frame() / _should_skip_frame()**: user-frame discovery skipping library and internal frames

### Design Philosophy

**Built-in Integration**: All extension functionality is built into ObjectModel without explicit configuration
**Mixin Composition**: Avoids complex inheritance through Mixin composition, improving maintainability
**Unified State**: _StateManager unifies instance state management supporting multiple state types
**Intelligent Proxy**: Integrates proxy system through __getattribute__ providing transparent lazy loading
**Method Name Discovery**: Signal handlers discovered by method name convention using getattr()
**Operation Detection**: _determine_save_operation() checks _has_primary_key_values() to detect CREATE/UPDATE
**Dual Signal Emission**: SAVE operations emit both SAVE and specific CREATE/UPDATE signals
**Built-in Performance**: Field caching, batch operations, and proxy system built into core components

### Integration with Other Modules

**Core Architecture Module**: Integrates signal system into model lifecycle
**Data Operations Module**: Provides batch operation optimization and field caching
**Field System Module**: Integrates validation error handling and exception system

## API Reference

### Signal System

```python
# Signal functionality (built into ObjectModel)
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation, emit_signals

class Model(ObjectModel):
    # Instance-level signals - discovered by method name
    async def before_save(self, context: SignalContext): pass
    async def after_save(self, context: SignalContext): pass
    async def before_create(self, context: SignalContext): pass
    async def after_create(self, context: SignalContext): pass
    async def before_update(self, context: SignalContext): pass
    async def after_update(self, context: SignalContext): pass
    async def before_delete(self, context: SignalContext): pass
    async def after_delete(self, context: SignalContext): pass
  
    # Batch operation signals
    @classmethod
    async def before_bulk_create(cls, context: SignalContext): pass
    @classmethod
    async def after_bulk_create(cls, context: SignalContext): pass

# Signal decorator with operation detection
@emit_signals(Operation.SAVE)  # Calls _determine_save_operation() for actual operation
async def save(self): pass
```

### Exception Handling

```python
# Exception classes
SQLObjectsError           # Root exception
├── DoesNotExist         # Query returns no results
├── MultipleObjectsReturned  # Multiple results
├── ValidationError      # Validation error
├── DatabaseError        # Database error
│   ├── IntegrityError   # Integrity constraint
│   └── TransactionError # Transaction error
└── ConfigurationError   # Configuration error

# Error creation
create_validation_error(code, field=None, params=None)

# Error collection
collector = ValidationErrorCollector()
collector.add_error(field, message)
collector.raise_if_errors()
```

### Performance Tools

```python
# Field cache
field_cache = Model._get_field_cache()
deferred_fields = field_cache.get("deferred_fields", set())

# Batch operations
.bulk_create(objects, batch_size=1000)
.bulk_update(mappings, batch_size=500)
.bulk_delete(ids, batch_size=1000)

# Performance analysis
# QueryExecutor.explain(query, analyze=False, verbose=False) -> str
# Returns the query plan as a string (ExplainResult); there is no output= parameter.
await queryset.explain(analyze=True)
```

### SQL Logging

```python
from sqlobjects.sql_logging import ObjectLogger, get_caller_frame

# ObjectLogger is installed as the "sqlobjects.sql" logger; enable it with:
import logging
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)

# get_caller_frame returns the first user-code frame(s), skipping library frames.
get_caller_frame(extra_skip_packages=None, max_frames=1)  # -> str | list[str]
```

### Utility Functions

```python
# Naming conversion
to_snake_case(name)
to_camel_case(name, pascal=True)
pluralize(word)
singularize(word)

# Debugging tools
get_field_validators(model_class, field_name)
get_model_metadata(model_class)
```

## Usage Guide

### Basic Usage

```python
# Basic signal usage
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):  # Signal functionality already built-in
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
  
    async def before_save(self, context: SignalContext):
        # Pre-save processing
        self.updated_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        # Post-create processing
        await self.send_welcome_email()

# Exception handling
try:
    user = await User.objects.get(User.email == "test@example.com")
except DoesNotExist:
    user = await User.objects.create(
        name="Test User",
        email="test@example.com"
    )
except ValidationError as e:
    print(f"Validation failed: {e.message}")

# Utility function usage
table_name = to_snake_case("UserProfile")  # "user_profile"
model_name = to_camel_case(table_name)     # "UserProfile"
```

### Advanced Usage

```python
# Complex signal handling
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        # Common save logic
        # context.actual_operation set by _determine_save_operation()
        if context.actual_operation == Operation.CREATE:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        # Post-create async tasks
        await self.create_user_profile()
        await self.send_welcome_email()
        await self.log_user_creation(context.session)
  
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        # Pre-bulk-create processing
        print(f"Creating {context.affected_count} users")

# Advanced exception handling
class UserValidator:
    def __init__(self):
        self.collector = ValidationErrorCollector()
  
    def validate_user_data(self, data):
        if not data.get("name"):
            self.collector.add_error("name", "Name is required")
      
        if not data.get("email"):
            self.collector.add_error("email", "Email is required")
        elif "@" not in data["email"]:
            self.collector.add_error("email", "Invalid email format")
      
        self.collector.raise_if_errors()

# Performance optimization usage
# Field cache statistics
field_cache = User._get_field_cache()
print(f"Deferred fields: {len(field_cache.get('deferred_fields', set()))}")
print(f"Relationship fields: {len(field_cache.get('relationship_fields', set()))}")

# Batch operation optimization
users_data = [{"name": f"User{i}", "email": f"user{i}@example.com"} 
              for i in range(1000)]
await User.objects.bulk_create(users_data, batch_size=100)

# Intelligent prefetch optimization
users = await User.objects.prefetch_related(
    active_posts=Post.objects.filter(Post.is_active == True)
                             .order_by("-created_at")
                             .limit(5)
).all()

# Query performance analysis
# explain() returns the plan as a string (accepts analyze and verbose flags only).
plan = await User.objects.filter(User.is_active == True).explain(
    analyze=True,
    verbose=True,
)
print(plan)

# Custom utility functions
def format_model_name(name: str) -> str:
    """Format model name"""
    return to_camel_case(to_snake_case(name))

def get_table_name(model_class) -> str:
    """Get model table name"""
    if hasattr(model_class, '__table__'):
        return model_class.__table__.name
    return pluralize(to_snake_case(model_class.__name__))

# Debugging and monitoring
metadata = get_model_metadata(User)
print(f"Model: {metadata['model_name']}")
print(f"Table: {metadata['table_name']}")
print(f"Fields: {list(metadata['fields'].keys())}")
```