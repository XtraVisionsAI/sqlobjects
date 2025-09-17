# Model Definition and Fields

## Overview

SQLObjects provides a Django-style model definition system with automatic table generation, type-safe fields, and
comprehensive validation support.

## Quick Start

### Basic Model

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)
```

### Automatic Generation Features

```python
# ModelProcessor metaclass automatically handles:
# - Table name: "users" (pluralized snake_case)
# - Object manager: User.objects = ObjectsDescriptor(User)
# - Field caching: _cached_field_info for performance optimization
# - Primary key: automatically generates id field if not specified

user = await User.objects.create(username="john", email="john@example.com")
print(user.id)  # Auto-generated when using identity() or primary_key=True

# ObjectsDescriptor provides new ObjectsManager instance on each access
manager1 = User.objects  # New ObjectsManager instance
manager2 = User.objects  # Another new ObjectsManager instance
```

## Field Types

### String Fields

```python
# Basic string field
name: Column[str] = StringColumn(length=100)

# Text field (no length limitation)
description: Column[str] = TextColumn()

# Fixed length
code: Column[str] = StringColumn(type="char", length=10)

# With validation
email: Column[str] = StringColumn(length=100, validators=[validate_email()])
```

### Numeric Fields

```python
# Integer type variants
id: Column[int] = IntegerColumn(primary_key=True)
count: Column[int] = IntegerColumn(type="bigint")
rating: Column[int] = IntegerColumn(type="smallint")

# Decimal precision
price: Column[Decimal] = NumericColumn(precision=10, scale=2)
percentage: Column[float] = FloatColumn()
```

### Date and Time

```python
from datetime import datetime, date, time

# DateTime with automatic timestamps
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
updated_at: Column[datetime] = DateTimeColumn(onupdate=datetime.now)

# Date and time variants
birth_date: Column[date] = DateTimeColumn(type="date")
start_time: Column[time] = DateTimeColumn(type="time")
```

### Advanced Types

```python
# JSON data
preferences: Column[dict] = JsonColumn(default=dict)
metadata: Column[list] = JsonColumn(default=list)

# Arrays (PostgreSQL)
tags: Column[list[str]] = ArrayColumn("string")
matrix: Column[list[list[int]]] = ArrayColumn("integer", dimensions=2)

# Enums
from enum import Enum

class UserStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

status: Column[UserStatus] = EnumColumn(UserStatus, default=UserStatus.ACTIVE)

# UUID
import uuid
external_id: Column[str] = UuidColumn(default_factory=uuid.uuid4)

# Binary data
file_data: Column[bytes] = BinaryColumn(length=1024)

# Foreign key relationships
author_id: Column[int] = foreign_key("users.id")
category_id: Column[int] = foreign_key("categories.id", nullable=False, index=True)
```

## Field Parameters

### Common Parameters

```python
# Nullability and defaults
username: Column[str] = StringColumn(nullable=False)  # Required
nickname: Column[str] = StringColumn(nullable=True)   # Optional
is_active: Column[bool] = BooleanColumn(default=True) # Default value

# Constraints
email: Column[str] = StringColumn(unique=True)        # Unique constraint
code: Column[str] = StringColumn(index=True)          # Database index
```

### Smart Code Generation Parameters

```python
# _apply_codegen_defaults function automatically infers parameters
class User(ObjectModel):
    # Regular fields get defaults: init=True, repr=True, compare=False
    username: Column[str] = column(type="string")  # Auto-apply defaults

    # Primary key fields auto-set: init=False, repr=True, compare=True
    id: Column[int] = identity()  # Auto-detected as primary key

    # Auto-increment fields auto-set: init=False
    sequence_id: Column[int] = column(type="integer", autoincrement=True)

    # Server default fields auto-set: init=False
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())

    # Manual override of defaults
    internal_field: Column[str] = column(type="string", init=False, repr=False)
    password: Column[str] = column(type="string", repr=False)  # Hide sensitive info
    version: Column[int] = column(type="integer", compare=True)  # Include in comparison

# from_dict method automatically handles init parameters
user_data = {"id": 1, "username": "alice", "created_at": datetime.now()}
user = User.from_dict(user_data)  # Auto-separate init=True/False fields

# ObjectsManager creation methods use from_dict for consistency
user = await User.objects.create(
    id=1,  # init=False fields handled via setattr
    username="bob",  # init=True fields handled via constructor
    created_at=datetime.now()  # init=False fields handled via setattr
)
```

### Performance Optimization Parameters

```python
# Deferred loading parameters
bio: Column[str] = column(
    type="text",
    deferred=True,  # Lazy load until accessed
    deferred_group="details",  # Group deferred fields
    deferred_raiseload=True  # Raise error if accessed while deferred
)

# History tracking
important_field: Column[str] = column(
    type="string",
    active_history=True  # Track field value changes
)

# Memory optimization
profile_image: Column[bytes] = column(
    type="binary",
    deferred=True,
    init=False,      # Exclude from constructor
    repr=False       # Hide in string representation
)
```

### Automatic Default Rules

```python
# Primary key fields automatically get: init=False, repr=True, compare=True
id: Column[int] = identity()

# Auto-increment fields automatically get: init=False
sequence_id: Column[int] = column(type="integer", autoincrement=True)

# Server default fields automatically get: init=False
created_at: Column[datetime] = column(type="datetime", server_default=func.now())

# Regular fields get: init=True, repr=True, compare=False, hash=None, kw_only=False
username: Column[str] = column(type="string")
```

### Enhanced Feature Parameters

```python
# Dynamic defaults and validation
created_at: Column[datetime] = column(
    type="datetime",
    default_factory=datetime.now,  # Dynamic default
    validators=[validate_datetime()]  # Field-level validation
)

# Insert-only defaults
status: Column[str] = column(
    type="string",
    insert_default="pending"  # Default only on INSERT operations
)

# Keyword arguments
optional_param: Column[str] = column(type="string", kw_only=True)
```

## Foreign Key Fields

```python
from sqlobjects.fields import foreign_key, ForeignKey, column

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)

    # Method 1: Using foreign_key() convenience function (recommended)
    author_id: Column[int] = foreign_key("users.id")
    category_id: Column[int] = foreign_key("categories.id", nullable=False, index=True)

    # Method 2: Using column() with ForeignKey parameter
    tag_id: Column[int] = column(
        type="integer",
        foreign_key=ForeignKey("tags.id"),
        nullable=True
    )

    # Foreign key with custom type
    uuid_ref: Column[str] = foreign_key("external_table.uuid", type="string")
```

## Field Shortcuts

### Identity and Timestamps

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, identity, column
from datetime import datetime

class Post(ObjectModel):
    id: Column[int] = identity()  # Auto-increment primary key
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = column(type="integer", nullable=False)
    created_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)
    updated_at: Column[datetime] = column(type="datetime", onupdate=datetime.now)
```

### Identity and Computed Fields

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, NumericColumn, computed, identity
from decimal import Decimal

class Order(ObjectModel):
    # Identity column with custom configuration
    id: Column[int] = identity(start=1000, increment=1)
    order_number: Column[int] = identity(start=1000, increment=1, cache=10)

    subtotal: Column[Decimal] = NumericColumn(precision=10, scale=2)
    tax_rate: Column[Decimal] = NumericColumn(precision=5, scale=4)

    # Computed column
    total: Column[Decimal] = computed(
        "subtotal * (1 + tax_rate)", 
        column_type="numeric", 
        precision=10, 
        scale=2
    )

    # Persisted computed column (stored in database)
    total_cached: Column[Decimal] = computed(
        "subtotal * (1 + tax_rate)",
        persisted=True,
        column_type="numeric"
    )
```

## Model Configuration

### Table Settings

```python
class User(ObjectModel):
    # ... fields ...

    class Config:
        table_name = "app_users"  # Override default table name
        ordering = ["-created_at"]  # Default ordering
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"
```

### Indexes and Constraints

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, NumericColumn
from sqlobjects.config import index, constraint, unique
from decimal import Decimal

class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    sku: Column[str] = StringColumn(length=50)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)

    class Config:
        indexes = [
            index("idx_sku", "sku", unique=True),
            index("idx_name_price", "name", "price")
        ]
        constraints = [
            constraint("price > 0", "chk_positive_price"),
            unique("name", "sku", name="uq_name_sku")
        ]
```

## Validation

### Field Validation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from sqlobjects.validators import validate_email, validate_length, validate_range

class User(ObjectModel):
    username: Column[str] = column(
        type="string", length=50,
        validators=[validate_length(3, 50)]
    )
    email: Column[str] = column(
        type="string", length=100,
        validators=[validate_email()]
    )
    age: Column[int] = column(
        type="integer",
        validators=[validate_range(0, 150)]
    )
```

### Model Validation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    # ... fields ...

    def validate(self):
        """Custom model-level validation"""
        if self.age and self.age < 18 and self.is_admin:
            raise ValidationError("Users under 18 cannot be administrators")
    
        if self.username and self.username.lower() in ['admin', 'root']:
            raise ValidationError("Reserved usernames are not allowed")
```

### Custom Validation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from sqlobjects.validators import validate_regex, validate_length
from sqlobjects.exceptions import ValidationError

def validate_file_extension(value):
    """Custom file extension validator"""
    if not value.lower().endswith(('.pdf', '.doc', '.docx')):
        raise ValidationError("Only PDF and Word documents are allowed")

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)

    # Custom validation
    filename: Column[str] = column(
        type="string",
        validators=[
            validate_length(1, 255),
            validate_file_extension
        ]
    )

    # Pattern validation
    document_code: Column[str] = column(
        type="string",
        validators=[
            validate_regex(r'^DOC-\d{4}-\d{2}$', "Format: DOC-YYYY-MM")
        ]
    )
```

## Model Methods

### Instance Operations

```python
# Create and save
user = User(username="alice", email="alice@example.com")
await user.save()

# Update
user.email = "alice.new@example.com"
await user.save()

# Delete
await user.delete()

# Refresh from database
await user.refresh()
await user.refresh(fields=["username", "email"])  # Selective refresh
```

### Smart Data Conversion

```python
# to_dict method - supports deferred fields and safe access
user_dict = user.to_dict()  # All loaded fields
user_dict = user.to_dict(include=["id", "username"])  # Specific fields
user_dict = user.to_dict(exclude=["password_hash"])  # Exclude sensitive fields
user_dict = user.to_dict(include_deferred=True)  # Include deferred fields
user_dict = user.to_dict(safe_access=False)  # Unsafe access may raise exceptions

# from_dict method - intelligently handles init parameters and defaults
user_data = {"username": "bob", "email": "bob@example.com", "id": 1}
user = User.from_dict(user_data, validate=True)

# from_dict internal process:
# 1. Filter invalid fields (not in table.columns)
# 2. Apply default_factory and column.default
# 3. Separate init=True/False fields based on field.get_codegen_params()
# 4. Create instance with init=True fields
# 5. Set init=False fields via setattr
# 6. Clear dirty field tracking
# 7. Execute validation (if validate=True)

# ObjectsManager integration - all creation methods use from_dict
user = await User.objects.create(
    id=1,  # init=False fields automatically handled
    username="alice",  # init=True fields
    created_at=datetime.now()  # init=False fields automatically handled
)

user, created = await User.objects.get_or_create(
    username="bob",
    defaults={"id": 2, "created_at": datetime.now()}  # Mixed field types automatically handled
)

user, created = await User.objects.update_or_create(
    username="charlie",
    defaults={"email": "charlie@example.com"}  # Updates also use from_dict logic
)
```

## Best Practices

### Field Naming

```python
# Use descriptive names
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
is_active: Column[bool] = BooleanColumn(default=True)
user_count: Column[int] = IntegerColumn(default=0)

# Avoid abbreviations
# Good: description, category_id, is_published
# Avoid: desc, cat_id, pub
```

### Default Values

```python
# Static defaults
is_active: Column[bool] = BooleanColumn(default=True)
status: Column[str] = StringColumn(default="pending")

# Dynamic defaults
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
uuid: Column[str] = UuidColumn(default_factory=uuid.uuid4)
```

### Validation Strategy

```python
# Combine field and model validation
class User(ObjectModel):
    email: Column[str] = column(type="string", validators=[validate_email()])  # Field-level
    age: Column[int] = column(type="integer", validators=[validate_range(0, 150)])

    def validate(self):  # Model-level
        if self.email and User.objects.filter(User.email == self.email).exists():
            raise ValidationError("Email already exists")
```