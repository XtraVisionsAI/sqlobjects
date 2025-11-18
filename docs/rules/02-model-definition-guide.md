# Model Definition Guide

## Core Concepts

- **ObjectModel**: Base class for all models with automatic table generation
- **Fields**: Type-safe column definitions using `Column[T]` annotations
- **Config Class**: Model configuration (table name, ordering, indexes, constraints)
- **Field Parameters**: Control initialization, validation, performance, and code generation
- **Auto Type Inference**: Automatic type detection from `Column[T]` annotations

## Common Usage

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

### Field Types

```python
from sqlobjects.fields import (
    Column, column,
    StringColumn, IntegerColumn, BooleanColumn,
    DateTimeColumn, NumericColumn, JsonColumn
)
from datetime import datetime
from decimal import Decimal

class Product(ObjectModel):
    # String fields
    name: Column[str] = StringColumn(length=100)
    description: Column[str] = column(type="text")
    
    # Numeric fields
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)
    stock: Column[int] = IntegerColumn(default=0)
    
    # Boolean fields
    is_available: Column[bool] = BooleanColumn(default=True)
    
    # DateTime fields
    created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
    
    # JSON fields
    metadata: Column[dict] = JsonColumn(default=dict)
```

### Auto Type Inference

```python
from sqlobjects.fields import Column, column

class User(ObjectModel):
    # Auto-infer type from Column[T] annotation
    username: Column[str] = column(type="auto", length=50)  # Infers "string"
    age: Column[int] = column(type="auto")  # Infers "integer"
    data: Column[dict] = column(type="auto")  # Infers "json"
```

### Model Configuration

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, index, constraint

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn()
    
    class Config:
        table_name = "app_users"  # Custom table name
        ordering = ["-created_at"]  # Default ordering
        indexes = [
            index("idx_username", "username", unique=True),
            index("idx_email", "email")
        ]
        constraints = [
            constraint("age >= 0", "chk_positive_age")
        ]
```

### Field Parameters

```python
from sqlobjects.fields import Column, column
from datetime import datetime

class User(ObjectModel):
    # Primary key (excluded from __init__)
    id: Column[int] = column(type="integer", primary_key=True, init=False)
    
    # Required fields (included in __init__)
    username: Column[str] = column(type="string", length=50, init=True)
    
    # Server-generated fields (excluded from __init__)
    created_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        init=False
    )
    
    # Optional fields with defaults
    is_active: Column[bool] = column(type="boolean", default=True, init=True)
    
    # Deferred loading for heavy fields
    bio: Column[str] = column(type="text", deferred=True)
```

## Best Practices

### ✅ Do

- **Use type annotations** with `Column[T]` for type safety
- **Set appropriate field lengths** for string fields
- **Use deferred loading** for heavy fields
- **Configure indexes** for frequently queried fields
- **Use server defaults** for timestamps
- **Control init parameter** based on field characteristics

```python
# Good: Type-safe with proper configuration
class User(ObjectModel):
    id: Column[int] = column(type="integer", primary_key=True, init=False)
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    bio: Column[str] = column(type="text", deferred=True)  # Heavy field
    created_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        init=False
    )
    
    class Config:
        indexes = [index("idx_username", "username")]
```

### ❌ Don't

- **Don't omit field lengths** for string columns
- **Don't load heavy fields** by default
- **Don't forget indexes** on foreign keys
- **Don't use init=True** for auto-generated fields
- **Don't mix init=True and init=False** inconsistently

```python
# Bad: No length limit, no indexes
class User(ObjectModel):
    username: Column[str] = StringColumn()  # No length!
    bio: Column[str] = column(type="text")  # Heavy field not deferred
    
    # Bad: Auto-generated field with init=True
    id: Column[int] = column(type="integer", primary_key=True, init=True)
    
    # Bad: Server-generated field with init=True
    created_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        init=True  # Should be False
    )
```

## Field Parameter Guidelines

### init Parameter Rules

```python
class User(ObjectModel):
    # init=False: Auto-generated or server-managed fields
    id: Column[int] = column(type="integer", primary_key=True, init=False)
    created_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        init=False
    )
    
    # init=True: User-provided fields
    username: Column[str] = StringColumn(length=50, init=True)
    email: Column[str] = StringColumn(length=100, init=True)
    
    # init=True with default: Optional user-provided fields
    is_active: Column[bool] = BooleanColumn(default=True, init=True)
```

### Performance Parameters

```python
class User(ObjectModel):
    # Deferred loading for heavy fields
    bio: Column[str] = column(type="text", deferred=True)
    profile_image: Column[bytes] = column(type="binary", deferred=True)
    
    # Active history tracking for important fields
    balance: Column[Decimal] = NumericColumn(
        precision=10,
        scale=2,
        active_history=True  # Track changes
    )
```

### Code Generation Parameters

```python
class User(ObjectModel):
    # Control __repr__ output
    password: Column[str] = StringColumn(length=100, repr=False)  # Hide in repr
    
    # Control comparison operations
    id: Column[int] = column(type="integer", primary_key=True, compare=True)
    created_at: Column[datetime] = DateTimeColumn(compare=False)  # Exclude from ==
    
    # Keyword-only parameters
    optional_field: Column[str] = StringColumn(length=50, kw_only=True)
```

## Performance Tips

### Deferred Loading

```python
class Article(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text", deferred=True)  # Load on access
    
# Query without loading content
articles = await Article.objects.only("id", "title").all()

# Load content when needed
article = await Article.objects.get(Article.id == 1)
content = article.content  # Triggers deferred load
```

### Field Selection

```python
# Load only needed fields
users = await User.objects.only("id", "username", "email").all()

# Defer heavy fields
users = await User.objects.defer("bio", "profile_image").all()
```

### Indexes

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    department: Column[str] = StringColumn(length=50)
    
    class Config:
        indexes = [
            index("idx_username", "username", unique=True),
            index("idx_email", "email", unique=True),
            index("idx_dept", "department"),  # For filtering
        ]
```

## Troubleshooting

### Field Not in Constructor

**Problem**: `TypeError: __init__() got an unexpected keyword argument`

**Solution**:
```python
# Check init parameter
class User(ObjectModel):
    id: Column[int] = column(type="integer", primary_key=True, init=False)  # Excluded
    username: Column[str] = StringColumn(length=50, init=True)  # Included

# Correct usage
user = User(username="alice")  # Don't pass id
```

### Type Inference Failed

**Problem**: `ValueError: Cannot infer type from annotation`

**Solution**:
```python
# Use explicit type instead of "auto"
class User(ObjectModel):
    # Bad: Complex type annotation
    data: Column[dict[str, Any]] = column(type="auto")  # May fail
    
    # Good: Explicit type
    data: Column[dict] = column(type="json")  # Clear
```

### Table Name Conflicts

**Problem**: `Table 'users' already exists`

**Solution**:
```python
# Use custom table name
class User(ObjectModel):
    class Config:
        table_name = "app_users"  # Avoid conflicts
```

### Missing Indexes

**Problem**: Slow queries on filtered fields

**Solution**:
```python
# Add indexes for frequently queried fields
class User(ObjectModel):
    email: Column[str] = StringColumn(length=100)
    department: Column[str] = StringColumn(length=50)
    
    class Config:
        indexes = [
            index("idx_email", "email"),
            index("idx_dept", "department"),
        ]
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import (
    Column, column, StringColumn, IntegerColumn,
    BooleanColumn, DateTimeColumn, JsonColumn,
    index, constraint
)
from datetime import datetime

class User(ObjectModel):
    # Primary key (auto-generated)
    id: Column[int] = column(type="integer", primary_key=True, init=False)
    
    # Required fields
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    
    # Optional fields with defaults
    is_active: Column[bool] = BooleanColumn(default=True)
    is_admin: Column[bool] = BooleanColumn(default=False)
    
    # Heavy fields (deferred loading)
    bio: Column[str] = column(type="text", deferred=True)
    
    # JSON field
    preferences: Column[dict] = JsonColumn(default=dict)
    
    # Timestamps (server-generated)
    created_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        init=False
    )
    updated_at: Column[datetime] = column(
        type="datetime",
        server_default="func.now()",
        onupdate=datetime.now,
        init=False
    )
    
    class Config:
        table_name = "users"
        ordering = ["-created_at"]
        indexes = [
            index("idx_username", "username", unique=True),
            index("idx_email", "email", unique=True),
        ]
        constraints = [
            constraint("length(username) >= 3", "chk_username_length")
        ]

# Usage
user = User(
    username="alice",
    email="alice@example.com",
    is_admin=True
)
await user.save()
```
