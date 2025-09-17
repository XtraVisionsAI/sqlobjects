# SQLObjects Extensions Design Document

## Overview

SQLObjects extensions provide enhanced functionality through built-in integration with ObjectModel, including signal
system, intelligent operation detection, performance optimization, and proxy system. Through Mixin composition patterns
and unified state management, it offers seamless integration capabilities for core functionality.

## Core Features

### 1. Built-in Signal System

ObjectModel includes SignalMixin by default, providing complete model lifecycle signals and intelligent operation
detection:

```python
from sqlobjects.model import ObjectModel  # SignalMixin already built-in
from sqlobjects.fields import Column, StringColumn
from datetime import datetime

class User(ObjectModel):  # Automatically has signal functionality
    name: Column[str] = StringColumn(length=50)
  
    # Instance-level signals - automatically integrated
    async def before_save(self, context):
        # context.actual_operation shows actual operation type
        self.updated_at = datetime.now()
  
    async def before_create(self, context):
        self.created_at = datetime.now()
  
    async def after_create(self, context):
        await self.send_welcome_email()
  
    # Class-level batch signals
    @classmethod
    async def before_bulk_create(cls, context):
        print(f"Creating {context.affected_count} users")

# @emit_signals decorator automatically handles signal emission
user = User(name="John")  # No primary key value
await user.save()  # Auto-detects CREATE, emits dual signals

user.name = "John Updated"
await user.save()  # Auto-detects UPDATE, only updates dirty fields
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
# QueryCache FIFO cache - automatically manages cache size
users = await User.objects.filter(User.is_active == True).all()  # cache miss
users = await User.objects.filter(User.is_active == True).all()  # cache hit

# Cache statistics and control
stats = QuerySet.get_cache_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
QuerySet.clear_query_cache()

# Batch operation optimization - uses bindparam and batch processing
await User.objects.bulk_create(users_data)  # automatic batching
affected = await User.objects.bulk_update(update_data, batch_size=500)

# FieldCacheMixin proxy system - automatically handles deferred fields
user = await User.objects.only("name").first()  # bio field deferred
# user.bio returns DeferredFieldProxy
# await user.bio.fetch() actually loads the data

# Relationship proxy - RelationFieldProxy
# user.posts returns RelationFieldProxy
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

## Module Architecture

### Core Components

**Model Integration Layer**

- **ObjectModel**: Complete model base class combining all Mixins with built-in extension functionality
- **ModelMixin**: Combines FieldCacheMixin + SignalMixin

**Signal System Layer**

- **SignalMixin**: Signal mixin class, built into ObjectModel
- **@emit_signals**: Signal decorator that automatically handles signal emission and operation detection
- **Operation**: Operation type enumeration supporting SAVE/DELETE etc.

**Proxy System Layer**

- **DeferredFieldProxy**: Deferred field proxy supporting lazy loading and caching
- **RelationFieldProxy**: Relationship field proxy supporting relationship lazy loading
- **FieldCacheMixin**: Integrates field cache and proxy system into __getattribute__

**State Management Layer**

- **StateManager**: Unified instance state management supporting multiple state types
- **HistoryTrackingMixin**: History tracking and dirty field detection

**Performance Tools Layer**

- **FieldCache**: Field metadata caching mechanism integrated into model classes
- **ValidationError**: Layered exception system supporting single-field and multi-field errors

### Design Philosophy

**Built-in Integration**: All extension functionality is built into ObjectModel without explicit configuration
**Mixin Composition**: Avoids complex inheritance through Mixin composition, improving maintainability
**Unified State**: StateManager unifies instance state management supporting multiple state types
**Intelligent Proxy**: Integrates proxy system through __getattribute__ providing transparent lazy loading
**Decorator-Driven**: @emit_signals decorator automatically handles signal emission and operation detection
**Built-in Performance**: Field caching, batch operations, and proxy system built into core components

### Integration with Other Modules

**Core Architecture Module**: Integrates signal system into model lifecycle
**Data Operations Module**: Provides batch operation optimization and field caching
**Field System Module**: Integrates validation error handling and exception system

## API Reference

### Signal System

```python
# Signal functionality (built into ObjectModel)
class Model(ObjectModel):
    # Instance-level signals
    async def before_save(self, context): pass
    async def after_save(self, context): pass
    async def before_create(self, context): pass
    async def after_create(self, context): pass
    async def before_update(self, context): pass
    async def after_update(self, context): pass
    async def before_delete(self, context): pass
    async def after_delete(self, context): pass
  
    # Batch operation signals
    @classmethod
    async def before_bulk_create(cls, context): pass
    @classmethod
    async def after_bulk_create(cls, context): pass

# Signal decorator
@emit_signals(Operation.SAVE)
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
await queryset.explain(analyze=True)
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

class User(ObjectModel):  # Signal functionality already built-in
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
  
    async def before_save(self, context):
        # Pre-save processing
        self.updated_at = datetime.now()
  
    async def after_create(self, context):
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
from sqlobjects.signals import Operation
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context):
        # Common save logic
        if context.actual_operation == Operation.CREATE:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
  
    async def after_create(self, context):
        # Post-create async tasks
        await self.create_user_profile()
        await self.send_welcome_email()
        await self.log_user_creation(context.session)
  
    @classmethod
    async def before_bulk_create(cls, context):
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
plan = await User.objects.filter(User.is_active == True).explain(
    analyze=True, 
    output="json"
)
print(f"Query cost: {plan['query_plan'][0].get('Total Cost', 'N/A')}")

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