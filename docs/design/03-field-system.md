# SQLObjects Field System Design Document

## Overview

The SQLObjects field system adopts a unified Column descriptor architecture that supports unified definition of database
fields and relationship fields. Through the TypeRegistry type registration system, ColumnAttribute enhanced attributes,
and comprehensive parameter system, it provides type safety, performance optimization, and code generation control
features.

## Core Features

### 1. Unified Column Descriptor Architecture

Column descriptors support unified definition of database fields and relationship fields, with automatic setup via
`__set_name__`:

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn, JsonColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey

class User(ObjectModel):
    # Database fields - using Column descriptor
    name: Column[str] = StringColumn(length=50)
    age: Column[int] = IntegerColumn()
    email: Column[str] = StringColumn(length=100, unique=True)
    is_active: Column[bool] = BooleanColumn(default=True)
    metadata: Column[dict] = JsonColumn(default=dict)
  
    # Relationship fields - using Related container
    posts: Related[list["Post"]] = relationship("Post", foreign_keys="author_id")

# Column descriptor dual access mode:
# - Class access: User.name returns ColumnAttribute for queries
# - Instance access: user.name returns field value with type conversion support

# Automatic type inference - using type="auto" parameter
id: Column[int] = column(type="auto", primary_key=True)  # Infers from Column[int]
name: Column[str] = column(type="auto")  # Infers from Column[str]

# Comprehensive parameter system
username: Column[str] = column(
    type="string", length=50, unique=True,
    # Enhanced functionality parameters
    validators=[validate_length(3, 50)],
    default_factory=None, insert_default=None,
    # Performance optimization parameters
    deferred=False, deferred_group=None, active_history=False,
    # Code generation parameters
    init=True, repr=True, compare=False, hash=None, kw_only=False
)

# Foreign key fields
author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
```

### 2. Function Expression Chaining

Supports chained function calls on fields, providing type-specific operation methods:

```python
# String function chaining
User.name.upper().trim()
User.email.lower().substring(1, 10)

# Numeric function chaining
User.age.abs().round(2)
User.salary.sum().avg()

# DateTime function chaining
User.birth_date.year().month()
User.created_at.age_in_years()
```

### 3. Data Validation System

Complete field-level and model-level validation with built-in and custom validators:

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50,
        validators=[
            LengthValidator(min_length=3, max_length=50),
            RegexValidator(r"^[a-zA-Z0-9_]+$")
        ]
    )
  
    email: Column[str] = StringColumn(
        length=100,
        validators=[EmailValidator()]
    )
  
    def validate(self):
        if self.age < 0:
            raise ValidationError("Age cannot be negative")
```

### 4. Performance Optimization Features

Field-level performance optimization with support for lazy loading and memory management:

```python
class User(ObjectModel):
    # Deferred loading for large fields
    bio: Column[str] = TextColumn(deferred=True)
    profile_image: Column[bytes] = BinaryColumn(deferred=True, deferred_group="media")
  
    # Active history tracking
    important_field: Column[str] = StringColumn(active_history=True)
  
    # Code generation control
    internal_id: Column[str] = StringColumn(init=False, repr=False)
    api_key: Column[str] = StringColumn(repr=False, compare=False)
```

## Module Architecture

### Core Components

**Descriptor Layer**

- **Column**: Unified field descriptor supporting unified definition of database and relationship fields
- **ColumnAttribute**: Enhanced SQLAlchemy Column with integrated validation, performance optimization, and code
  generation control
- **RelationshipDescriptor**: Relationship field descriptor handling relationship definition and access

**Type System Layer**

- **TypeRegistry**: Global type registration system supporting lazy initialization and automatic parameter extraction
- **create_type_instance()**: Function that creates SQLAlchemy type instances from type names and parameters
- **_infer_type_from_annotation()**: Function that infers type from Column[T] annotations when type="auto"
- **Enhanced Types**: SQLAlchemy types + Comparator supporting database function chaining

**Function Expression Layer**

- **ColumnFunctionMixin**: Field function mixin providing function calls for Column descriptors
- **ColumnAttributeFunctionMixin**: ColumnAttribute function mixin supporting database functions
- **Comparator Classes**: Type-specific comparators providing rich database functions

### Design Philosophy

**Unified Descriptor**: Column descriptor uniformly handles database and relationship fields, simplifying API
**Parameter Classification**: Categorizes parameters into SQLAlchemy, enhanced functionality, performance optimization,
and code generation
**Smart Defaults**: Automatically infers init/repr/compare parameters based on field characteristics
**Type Registration**: Global TypeRegistry supports type aliases and automatic constructor parameter extraction
**Function Integration**: Provides database function calls for fields through Mixin and Comparator
**Performance First**: Built-in lazy loading, history tracking, and field caching capabilities

### Integration with Other Modules

**Core Architecture Module**: Processes field definitions through ModelProcessor
**Data Operation Module**: Provides field expressions and query conditions
**Extension Module**: Integrates validator and exception handling systems

## API Reference

### Field Definition Classes

```python
# Core field function
column(
    type="auto", name=None,
    # SQLAlchemy parameters
    primary_key=False, nullable=True, default=None, index=False, unique=False,
    autoincrement="auto", doc=None, key=None, onupdate=None, comment=None,
    system=False, server_default=None, server_onupdate=None, quote=None, info=None,
    # Enhanced functionality parameters
    default_factory=None, validators=None, insert_default=None,
    # Performance optimization parameters
    deferred=False, deferred_group=None, active_history=False, deferred_raiseload=None,
    # Code generation parameters
    init=None, repr=None, compare=None, hash=None, kw_only=None,
    # Foreign key constraint
    foreign_key=None, on_delete=OnDelete.NO_ACTION,
    **kwargs  # Type-specific parameters
)

# Column type classes
StringColumn(length=None, **kwargs)
TextColumn(**kwargs)
IntegerColumn(type="integer", **kwargs)  # type: "integer"|"bigint"|"smallint"|"int"
FloatColumn(type="float", **kwargs)     # type: "float"|"double"
NumericColumn(precision=None, scale=None, **kwargs)
BooleanColumn(**kwargs)
DateTimeColumn(type="datetime", **kwargs)  # type: "datetime"|"date"|"time"|"interval"
BinaryColumn(length=None, **kwargs)
UuidColumn(**kwargs)
JsonColumn(**kwargs)
ArrayColumn(item_type, dimensions=1, **kwargs)
EnumColumn(enum_class, **kwargs)
IdentityColumn(start=1, increment=1, minvalue=None, maxvalue=None, cycle=False, cache=None, **kwargs)
ComputedColumn(sqltext, persisted=None, column_type="auto", **kwargs)
```

### Function Expressions

```python
# String functions
field.upper() / field.lower() / field.trim()
field.substring(start, length) / field.length()
field.concat(*args) / field.replace(old, new)
field.left(length) / field.right(length)
field.lpad(length, fill_char) / field.rpad(length, fill_char)
field.ltrim(chars) / field.rtrim(chars)
field.split_part(delimiter, field) / field.position(substring)
field.reverse() / field.md5()
field.regexp_replace(pattern, replacement, flags)

# Numeric functions
field.abs() / field.round(precision) / field.ceil() / field.floor()
field.sqrt() / field.power(exponent) / field.mod(divisor)
field.sign() / field.trunc(precision) / field.exp() / field.ln() / field.log(base)
field.sum() / field.avg() / field.count_distinct()

# DateTime functions
field.extract(field) / field.year() / field.month() / field.day()
field.hour() / field.minute()
field.date_trunc(precision) / field.age_in_years() / field.age_in_months()
field.days_between(end_date) / field.to_char(format_str) / field.add_days(days)

# JSON functions
field.extract_path(path) / field.extract_text(path)

# Generic functions
field.cast(type_, **kwargs) / field.coalesce(*values) / field.nullif(value)
field.case(*conditions, else_=None) / field.greatest(*args) / field.least(*args)
```

### Utility Functions

```python
# Identity and computed columns
identity(start=1, increment=1, minvalue=None, maxvalue=None, cycle=False, cache=None, **kwargs)
computed(sqltext, persisted=None, column_type="auto", **kwargs)

# Foreign key fields (use SQLAlchemy ForeignKey)
from sqlalchemy import ForeignKey
author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))

# Type system
register_field_type(field_type, type_name, comparator=None, aliases=None, default_params=None)
create_type_instance(type_name, type_params)  # Creates SQLAlchemy type from name and params
get_type_definition(type_name)

# SQLAlchemy integration
ForeignKey(reference, **kwargs)  # Direct use of SQLAlchemy ForeignKey

# Field compatibility
is_field_definition(attr)
get_column_from_field(field_def)

# Validation and metadata
get_field_validators(model_class, field_name)
get_model_metadata(model_class)
```

### Type Registration System

```python
# TypeRegistry core methods
registry = TypeRegistry()
register_field_type(field_type, name, comparator, aliases, default_params)
registry.get_type_config(name)
registry.create_enhanced_type(name, **params)

# Auto type inference
column(type="auto")  # Infers type from Column[T] annotation using _infer_type_from_annotation()

# ColumnAttribute enhanced features
attr.validate_value(value, field_name)
attr.get_effective_default()
attr.get_field_metadata()
attr.get_codegen_params()
```

## Usage Guide

### Basic Usage

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn

# Basic field definition
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    age: Column[int] = IntegerColumn()
    email: Column[str] = StringColumn(length=100, unique=True)
    is_active: Column[bool] = BooleanColumn(default=True)

# Field function calls
users = await User.objects.filter(
    User.name.upper() == "JOHN",
    User.age >= 18
).all()

# Basic validation
class Product(ObjectModel):
    name: Column[str] = StringColumn(
        length=100,
        validators=[LengthValidator(min_length=1)]
    )
    price: Column[Decimal] = NumericColumn(
        precision=10, scale=2,
        validators=[RangeValidator(min_value=0)]
    )
```

### Advanced Usage

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column, IdentityColumn, ComputedColumn
from sqlalchemy import ForeignKey
from datetime import datetime

# Complex field configuration
class User(ObjectModel):
    username: Column[str] = column(
        type="string", length=50,
        nullable=False, unique=True,
        validators=[validate_length(3, 50), validate_regex(r"^[a-zA-Z0-9_]+$")],
        init=True, repr=True, compare=True
    )
  
    password_hash: Column[str] = column(
        type="string", length=255,
        nullable=False,
        repr=False  # Don't show in __repr__
    )
  
    created_at: Column[datetime] = column(
        type="datetime",
        default_factory=datetime.now,
        init=False  # Don't include in __init__
    )
  
    # Performance optimization fields
    bio: Column[str] = column(
        type="text",
        deferred=True,  # Lazy loading
        deferred_group="details"
    )
  
    # Identity and computed columns
    id: Column[int] = IdentityColumn()
    full_name: Column[str] = ComputedColumn(
        "first_name || ' ' || last_name",
        column_type="string"
    )
  
    # Foreign key fields
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    category_id: Column[int] = column(type="integer", foreign_key=ForeignKey("categories.id"), nullable=False, index=True)

# Chained function calls
users = await User.objects.annotate(
    display_name=User.first_name.concat(" ", User.last_name).upper(),
    email_domain=User.email.split_part("@", 2),
    age_years=User.birth_date.age_in_years(),
    salary_rounded=User.salary.round(2)
).filter(
    User.name.upper().like("ADMIN%"),
    User.birth_date.age_in_years() >= 18,
    User.salary.abs() > 5000
).all()

# Subquery usage
avg_salary = User.objects.aggregate(
    avg_salary=func.avg(User.salary)
).subquery()

high_earners = await User.objects.filter(
    User.salary > avg_salary
).annotate(
    salary_ratio=User.salary / avg_salary
).all()

# Custom validators
def validate_password_strength(value):
    if len(value) < 8:
        raise ValidationError("Password too short")
    if not any(c.isupper() for c in value):
        raise ValidationError("Password must contain uppercase")

class User(ObjectModel):
    password: Column[str] = column(
        type="string", length=255,
        validators=[validate_password_strength]
    )
  
    def validate(self):
        if self.username.lower() in self.email.lower():
            raise ValidationError("Username cannot be part of email")

# Type registration and custom types
from sqlalchemy import INET
from sqlobjects.fields.types import register_field_type

register_field_type(
    INET, 'inet',
    aliases=['ip_address'],
    default_params={}
)

class Server(ObjectModel):
    ip_address: Column[str] = column(type="inet")
  
# Field metadata access
metadata = User.username.get_field_metadata()
validators = get_field_validators(User, 'username')
model_info = get_model_metadata(User)
```