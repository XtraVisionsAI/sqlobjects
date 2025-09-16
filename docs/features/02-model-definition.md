# Model Definition

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/02-model-definition.md](../../docs-zh/features/02-model-definition.md)

SQLObjects uses Django-style model definitions with automatic table generation, type safety, and comprehensive field system.

## Basic Model Definition

### Simple Model

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)
```

### Model with Configuration

```python
from datetime import datetime
from sqlobjects.fields import DateTimeColumn, foreign_key

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = StringColumn(type="text")
    author_id: Column[int] = foreign_key("users.id")
    created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
    
    class Config:
        table_name = "blog_posts"        # Custom table name
        ordering = ["-created_at"]       # Default ordering
        indexes = [                      # Additional indexes
            index("idx_title", "title"),
            index("idx_author_created", "author_id", "created_at")
        ]
```

## Field Types

### Basic Field Types

```python
from sqlobjects.fields import *

class Product(ObjectModel):
    # String fields
    name: Column[str] = StringColumn(length=100)
    description: Column[str] = StringColumn(type="text")
    
    # Numeric fields
    price: Column[Decimal] = DecimalColumn(precision=10, scale=2)
    quantity: Column[int] = IntegerColumn(default=0)
    weight: Column[float] = FloatColumn(nullable=True)
    
    # Boolean and date fields
    is_available: Column[bool] = BooleanColumn(default=True)
    created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
    updated_at: Column[datetime] = DateTimeColumn(onupdate=datetime.now)
    
    # JSON field
    metadata: Column[dict] = JsonColumn(default=dict)
```

### Advanced Field Types

```python
from sqlobjects.fields import ArrayColumn, EnumColumn, UuidColumn
import uuid
from enum import Enum

class UserStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class User(ObjectModel):
    # UUID field with automatic generation
    uuid: Column[str] = UuidColumn(default_factory=uuid.uuid4)
    
    # Enum field
    status: Column[UserStatus] = EnumColumn(UserStatus, default=UserStatus.ACTIVE)
    
    # Array field (PostgreSQL)
    tags: Column[list[str]] = ArrayColumn("string")
    permissions: Column[list[int]] = ArrayColumn("integer")
```

### Field Parameters

```python
class User(ObjectModel):
    # Basic parameters
    username: Column[str] = StringColumn(
        length=50,
        nullable=False,
        unique=True,
        index=True
    )
    
    # Default values
    created_at: Column[datetime] = DateTimeColumn(
        default_factory=datetime.now,    # Dynamic default
        nullable=False
    )
    
    # Server defaults
    id: Column[int] = IntegerColumn(
        primary_key=True,
        server_default=text("nextval('user_id_seq')")
    )
    
    # Validation
    email: Column[str] = StringColumn(
        length=100,
        validators=[validate_email()]
    )
```

## Primary Keys and Identity

### Automatic Primary Key

```python
# SQLObjects automatically creates 'id' field if no primary key is defined
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    # 'id' field automatically created as primary key
```

### Custom Primary Key

```python
class User(ObjectModel):
    user_id: Column[int] = IntegerColumn(primary_key=True)
    username: Column[str] = StringColumn(length=50)

# Or using identity column
class User(ObjectModel):
    id: Column[int] = identity(start=1000, increment=1)
    username: Column[str] = StringColumn(length=50)
```

### Composite Primary Key

```python
class UserRole(ObjectModel):
    user_id: Column[int] = foreign_key("users.id", primary_key=True)
    role_id: Column[int] = foreign_key("roles.id", primary_key=True)
    assigned_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
```

## Relationships

### Foreign Key Relationships

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    category_id: Column[int] = foreign_key("categories.id", nullable=True)

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # Reverse relationship (one-to-many)
    posts = relationship("Post", back_populates="author")

class Category(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    posts = relationship("Post", back_populates="category")
```

### Many-to-Many Relationships

```python
# Association table
class PostTag(ObjectModel):
    post_id: Column[int] = foreign_key("posts.id", primary_key=True)
    tag_id: Column[int] = foreign_key("tags.id", primary_key=True)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    tags = relationship("Tag", secondary="post_tags", back_populates="posts")

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50, unique=True)
    posts = relationship("Post", secondary="post_tags", back_populates="tags")
```

## Model Configuration

### Table Configuration

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    class Config:
        table_name = "app_users"         # Custom table name
        schema = "public"                # Database schema
        ordering = ["username"]          # Default ordering
        
        # Table constraints
        constraints = [
            constraint("age >= 0", "chk_positive_age"),
            unique("username", "email", name="uq_user_identity")
        ]
        
        # Additional indexes
        indexes = [
            index("idx_username", "username", unique=True),
            index("idx_email_domain", func.split_part("email", "@", 2))
        ]
```

### Performance Configuration

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    bio: Column[str] = StringColumn(type="text", deferred=True)  # Lazy loading
    
    class Config:
        # Performance optimizations
        select_related_default = ["profile"]     # Default relationship loading
        prefetch_related_default = ["posts"]     # Default prefetch relationships
        indexes = ["username", "email"]          # Database indexes for performance
```

## Validation

### Field-Level Validation

```python
from sqlobjects.validators import validate_email, validate_length, validate_range

class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50,
        validators=[validate_length(3, 50)]
    )
    email: Column[str] = StringColumn(
        length=100,
        validators=[validate_email()]
    )
    age: Column[int] = IntegerColumn(
        validators=[validate_range(0, 150)]
    )
```

### Model-Level Validation

```python
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_admin: Column[bool] = BooleanColumn(default=False)
    
    def validate(self):
        """Model-level validation"""
        if not self.email:
            raise ValidationError("Email is required")
        
        if self.is_admin and self.age and self.age < 18:
            raise ValidationError("Admin users must be at least 18 years old")
        
        # Cross-field validation
        if self.username and self.email and self.username in self.email:
            raise ValidationError("Username cannot be part of email address")
```

## Lifecycle Hooks

### Signal Handlers

```python
from sqlobjects.signals import SignalContext

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    created_at: Column[datetime] = DateTimeColumn(nullable=True)
    updated_at: Column[datetime] = DateTimeColumn(nullable=True)
    
    async def before_save(self, context: SignalContext):
        """Called before any save operation"""
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        """Called only before creation"""
        self.created_at = datetime.now()
    
    async def after_create(self, context: SignalContext):
        """Called after creation"""
        await self.send_welcome_email()
    
    async def before_delete(self, context: SignalContext):
        """Called before deletion"""
        await self.cleanup_related_data()
```

## Advanced Features

### Computed Fields

```python
class User(ObjectModel):
    first_name: Column[str] = StringColumn(length=50)
    last_name: Column[str] = StringColumn(length=50)
    
    # Computed field stored in database
    full_name: Column[str] = computed(
        "first_name || ' ' || last_name",
        column_type="string",
        persisted=True
    )
```

### Deferred Loading

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # Large fields loaded only when accessed
    bio: Column[str] = StringColumn(type="text", deferred=True)
    profile_image: Column[bytes] = column(type="binary", deferred=True)
    
    class Config:
        # Group deferred fields
        deferred_groups = {
            "profile": ["bio", "profile_image"],
            "stats": ["login_count", "last_activity"]
        }
```

### Custom Field Types

```python
from sqlobjects.fields.core import FieldType

class EmailField(FieldType):
    """Custom email field with built-in validation"""
    
    def __init__(self, **kwargs):
        kwargs.setdefault("validators", []).append(validate_email())
        super().__init__(type="string", length=254, **kwargs)

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = EmailField()  # Custom field type
```

## Best Practices

### Model Organization

1. **Keep models focused**: Each model should represent a single entity
2. **Use meaningful names**: Choose clear, descriptive field and model names
3. **Group related fields**: Organize fields logically within the model
4. **Document complex logic**: Add docstrings for complex validation or business logic

### Performance Considerations

```python
class User(ObjectModel):
    # Index frequently queried fields
    username: Column[str] = StringColumn(length=50, index=True)
    email: Column[str] = StringColumn(length=100, unique=True)  # Unique creates index
    
    # Defer large fields
    bio: Column[str] = StringColumn(type="text", deferred=True)
    
    # Use appropriate field lengths
    status: Column[str] = StringColumn(length=20)  # Not 255 for short values
    
    class Config:
        # Add composite indexes for common query patterns
        indexes = [
            index("idx_user_status_created", "status", "created_at"),
            index("idx_user_email_active", "email", "is_active")
        ]
```

### Validation Strategy

```python
class User(ObjectModel):
    # Field-level validation for simple rules
    username: Column[str] = StringColumn(
        length=50,
        validators=[validate_length(3, 50)]
    )
    
    # Model-level validation for complex business rules
    def validate(self):
        # Cross-field validation
        if self.is_premium and not self.email_verified:
            raise ValidationError("Premium users must verify their email")
        
        # Business logic validation
        if self.subscription_expires and self.subscription_expires < datetime.now():
            raise ValidationError("Subscription has expired")
```