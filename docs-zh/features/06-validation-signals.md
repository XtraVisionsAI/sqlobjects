# Validation and Signals

## Overview

SQLObjects provides comprehensive validation at field and model levels, plus a powerful signal system for hooking into database operations with automatic lifecycle management.

## Quick Start

### Basic Validation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn
from sqlobjects.validators import validate_email, validate_length
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50, 
        validators=[validate_length(3, 50)]
    )
    email: Column[str] = StringColumn(
        length=100, 
        validators=[validate_email()]
    )
    age: Column[int] = IntegerColumn(nullable=True)
    
    def validate(self):
        """Model-level validation"""
        if self.age and self.age < 13:
            raise ValidationError("Users must be at least 13 years old")
```

### Basic Signals

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):  # Built-in signal support
    # ... fields ...
    
    async def before_save(self, context: SignalContext):
        """Called before any save operation"""
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        """Called only before creating new records"""
        self.created_at = datetime.now()
```

## Field Validation

### Built-in Validators

```python
from sqlobjects.validators import (
    validate_email, validate_url, validate_length, validate_range,
    validate_regex, validate_choices, validate_date, validate_time,
    validate_decimal, validate_json
)

class User(ObjectModel):
    # Email validation
    email: Column[str] = StringColumn(validators=[validate_email()])
    
    # Length validation
    username: Column[str] = StringColumn(validators=[validate_length(3, 50)])
    
    # Range validation
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])
    
    # Regex validation
    phone: Column[str] = StringColumn(validators=[validate_regex(r"^\d{3}-\d{3}-\d{4}$")])
    
    # Choices validation
    status: Column[str] = StringColumn(validators=[validate_choices(["active", "inactive", "pending"])])
    
    # URL validation
    website: Column[str] = StringColumn(validators=[validate_url()])
    
    # Date/time validation
    birth_date: Column[str] = StringColumn(validators=[validate_date("%Y-%m-%d")])
    work_time: Column[str] = StringColumn(validators=[validate_time("%H:%M")])
    
    # Decimal validation
    price: Column[str] = StringColumn(validators=[validate_decimal(10, 2)])
    
    # JSON validation
    metadata: Column[str] = StringColumn(validators=[validate_json()])
```

### Advanced Validators

```python
from sqlobjects.validators import validate_regex, validate_choices

class Document(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    
    # File extension validation using regex
    filename: Column[str] = StringColumn(validators=[
        validate_regex(
            r'\.(pdf|doc|docx|txt)$',
            "File must be PDF, DOC, DOCX, or TXT format"
        )
    ])
    
    # Document type validation
    doc_type: Column[str] = StringColumn(validators=[
        validate_choices(["report", "manual", "specification", "other"])
    ])
    
    # Size validation (as string representation)
    file_size: Column[str] = StringColumn(validators=[
        validate_regex(r'^\d+[KMGT]?B$', "Size format: 100B, 1KB, 1MB, etc.")
    ])
```

### Custom Validators

```python
from sqlobjects.exceptions import ValidationError

def validate_username(value):
    """Custom username validator"""
    if not value:
        raise ValidationError("Username is required")
    
    if len(value) < 3:
        raise ValidationError("Username must be at least 3 characters")
    
    if not value.isalnum():
        raise ValidationError("Username must contain only letters and numbers")
    
    # Check for reserved names
    reserved = ["admin", "root", "system", "api"]
    if value.lower() in reserved:
        raise ValidationError("Username is reserved")

def validate_strong_password(value):
    """Strong password validator"""
    if not value:
        raise ValidationError("Password is required")
    
    if len(value) < 8:
        raise ValidationError("Password must be at least 8 characters")
    
    if not any(c.isupper() for c in value):
        raise ValidationError("Password must contain at least one uppercase letter")
    
    if not any(c.islower() for c in value):
        raise ValidationError("Password must contain at least one lowercase letter")
    
    if not any(c.isdigit() for c in value):
        raise ValidationError("Password must contain at least one digit")

class User(ObjectModel):
    username: Column[str] = StringColumn(validators=[validate_username])
    password: Column[str] = StringColumn(validators=[validate_strong_password])
```

### Combining Validators

```python
from sqlobjects.validators import combine_validators

class User(ObjectModel):
    # Combine multiple validators
    username: Column[str] = StringColumn(validators=[
        combine_validators(
            validate_length(3, 50),
            validate_regex(r"^[a-zA-Z0-9_]+$"),
            validate_username  # Custom validator
        )
    ])
    
    # Multiple individual validators
    email: Column[str] = StringColumn(validators=[
        validate_email(),
        validate_length(5, 100)
    ])
```

## Model Validation

### Model-Level Validation

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_admin: Column[bool] = BooleanColumn(default=False)
    
    def validate(self):
        """Cross-field validation"""
        # Age restrictions for admin users
        if self.is_admin and self.age and self.age < 18:
            raise ValidationError("Admin users must be at least 18 years old")
        
        # Email domain restrictions
        if self.email and self.is_admin:
            if not self.email.endswith("@company.com"):
                raise ValidationError("Admin users must use company email")
        
        # Username uniqueness (example - usually handled by database constraints)
        if self.username:
            existing = User.objects.filter(
                User.username == self.username,
                User.id != self.id  # Exclude self for updates
            ).exists()
            if existing:
                raise ValidationError("Username already exists")
```

### Validation Control

```python
# Automatic validation (default)
user = await User.objects.create(
    username="john",
    email="john@example.com"
)  # Validates automatically

# Skip validation for trusted data
system_user = await User.objects.create(
    username="system",
    email="system@internal.com",
    validate=False  # Skip validation
)

# Manual validation
user = User(username="alice", email="alice@example.com")
user.validate_all()  # Validate all fields and model
user.validate_fields(["username", "email"])  # Validate specific fields
user.validate()  # Model-level validation only

# Validation during save
user = User(username="bob", email="bob@example.com")
await user.save(validate=True)  # Default behavior
await user.save(validate=False)  # Skip validation
```

### Validation Error Handling

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector

# Single validation error
try:
    user = User(username="ab", email="invalid-email")
    user.validate_all()
except ValidationError as e:
    print(f"Validation failed: {e.message}")
    print(f"Field: {e.field}")
    print(f"Code: {e.code}")

# Multiple validation errors
try:
    user = User(username="a", email="bad", age=-5)
    user.validate_all()
except ValidationError as e:
    if hasattr(e, 'errors') and e.errors:
        for field, errors in e.errors.items():
            print(f"{field}: {', '.join(errors)}")

# Manual error collection
collector = ValidationErrorCollector()
if not username:
    collector.add_error("username", "Username is required")
if not email:
    collector.add_error("email", "Email is required")
collector.raise_if_errors()  # Raises ValidationError if any errors
```

## Signal System

### Signal Types

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime
import uuid

class User(ObjectModel):  # 已内置信号功能
    # Instance-level signals (single record operations)
    async def before_save(self, context: SignalContext):
        """Universal save logic - always triggered"""
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        """Only triggered for CREATE operations"""
        self.created_at = datetime.now()
        self.uuid = str(uuid.uuid4())
    
    async def before_update(self, context: SignalContext):
        """Only triggered for UPDATE operations"""
        self.version += 1
    
    async def before_delete(self, context: SignalContext):
        """Triggered before deletion"""
        # Log deletion or cleanup
        await AuditLog.objects.create(
            action="delete",
            model="User",
            object_id=self.id
        )
    
    async def after_save(self, context: SignalContext):
        """After save operations"""
        # Send notifications, update caches, etc.
        pass
    
    async def after_create(self, context: SignalContext):
        """After creation only"""
        # Send welcome email, create related objects
        await self.send_welcome_email()
    
    async def after_update(self, context: SignalContext):
        """After update only"""
        # Invalidate caches, send update notifications
        cache.delete(f"user:{self.id}")
    
    async def after_delete(self, context: SignalContext):
        """After deletion"""
        # Cleanup related data
        await self.cleanup_user_data()
```

### Bulk Operation Signals

```python
class User(ObjectModel):
    # Bulk operation signals (multiple records)
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        """Before bulk creation"""
        print(f"Creating {context.affected_count} users")
    
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        """Before bulk update"""
        print(f"Updating {context.affected_count} users")
        # Access update data
        if context.update_data:
            print(f"Update data: {context.update_data}")
    
    @classmethod
    async def before_bulk_delete(cls, context: SignalContext):
        """Before bulk deletion"""
        print(f"Deleting {context.affected_count} users")
    
    @classmethod
    async def after_bulk_create(cls, context: SignalContext):
        """After bulk creation"""
        # Send batch notifications
        pass
    
    @classmethod
    async def after_bulk_update(cls, context: SignalContext):
        """After bulk update"""
        # Invalidate caches for affected records
        pass
    
    @classmethod
    async def after_bulk_delete(cls, context: SignalContext):
        """After bulk deletion"""
        # Cleanup related data
        pass
```

### Signal Context

```python
from sqlobjects.signals import SignalContext, Operation

# SignalContext provides operation information
async def before_save(self, context: SignalContext):
    print(f"Operation: {context.operation}")  # SAVE, CREATE, UPDATE, DELETE
    print(f"Session: {context.session}")  # Database session
    print(f"Model: {context.model_class}")  # Model class
    print(f"Instance: {context.instance}")  # Model instance (for single operations)
    print(f"Affected count: {context.affected_count}")  # For bulk operations
    print(f"Update data: {context.update_data}")  # For bulk updates
    print(f"Actual operation: {context.actual_operation}")  # Detected operation for SAVE
```

### Smart SAVE Operation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        """Always called for save() operations"""
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        """Called for new instances"""
        self.created_at = datetime.now()
    
    async def before_update(self, context: SignalContext):
        """Called for existing instances"""
        self.version += 1

# Smart save automatically detects CREATE vs UPDATE
user = User(username="new_user")  # No primary key
await user.save()  # Triggers: before_save → before_create → after_save → after_create

user.username = "updated_user"
await user.save()  # Triggers: before_save → before_update → after_save → after_update

# Detached instance with primary key
detached_user = User(id=1, username="detached")
await detached_user.save()  # Triggers: before_save → before_update → after_save → after_update
```

### Signal Integration with Operations

```python
# get_or_create and update_or_create trigger signals
user, created = await User.objects.get_or_create(
    username="signal_user",
    defaults={"email": "signal@example.com"}
)
# If created: before_save → before_create → after_save → after_create
# If found: no signals triggered

user, created = await User.objects.update_or_create(
    username="signal_user",
    defaults={"last_login": datetime.now()}
)
# If updated: before_save → before_update → after_save → after_update
# If created: before_save → before_create → after_save → after_create
```

## Advanced Validation Patterns

### Conditional Validation

```python
class User(ObjectModel):
    user_type: Column[str] = StringColumn(length=20)
    company_email: Column[str] = StringColumn(length=100, nullable=True)
    personal_email: Column[str] = StringColumn(length=100, nullable=True)
    
    def validate(self):
        if self.user_type == "employee":
            if not self.company_email:
                raise ValidationError("Employee users must have company email")
            if not self.company_email.endswith("@company.com"):
                raise ValidationError("Company email must be from company domain")
        
        elif self.user_type == "customer":
            if not self.personal_email:
                raise ValidationError("Customer users must have personal email")
```

### Async Validation

```python
class User(ObjectModel):
    email: Column[str] = StringColumn(length=100)
    
    async def validate(self):
        """Async model validation"""
        # Check email uniqueness in database
        if self.email:
            existing = await User.objects.filter(
                User.email == self.email,
                User.id != self.id
            ).exists()
            if existing:
                raise ValidationError("Email already exists")
        
        # External API validation
        if self.email:
            is_valid = await validate_email_with_external_service(self.email)
            if not is_valid:
                raise ValidationError("Email failed external validation")
```

### Validation with Signals

```python
class User(ObjectModel, SignalMixin):
    async def before_save(self, context: SignalContext):
        """Validation in signals"""
        # Perform validation before save
        if not self.email:
            raise ValidationError("Email is required")
        
        # Business rule validation
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21")
    
    async def before_create(self, context: SignalContext):
        """Create-specific validation"""
        # Check for duplicate usernames
        existing = await User.objects.filter(User.username == self.username).exists()
        if existing:
            raise ValidationError("Username already exists")
```

## Best Practices

### Validation Strategy

```python
# Layer validation appropriately
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.validators import validate_email, validate_range
from sqlobjects.exceptions import ValidationError
from sqlobjects.signals import SignalContext

class User(ObjectModel):
    # Field-level: Basic format validation
    email: Column[str] = StringColumn(validators=[validate_email()])
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])
    is_admin: Column[bool] = BooleanColumn(default=False)
    
    # Model-level: Cross-field and business rules
    def validate(self):
        if self.is_admin and self.age < 18:
            raise ValidationError("Admin users must be adults")
    
    # Signal-level: Database-dependent validation
    async def before_save(self, context: SignalContext):
        if await self.has_pending_violations():
            raise ValidationError("Cannot save user with pending violations")
```

### Signal Organization

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    # Group related signal handlers
    
    # === Timestamp Management ===
    async def before_save(self, context: SignalContext):
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()
    
    # === Audit Logging ===
    async def after_save(self, context: SignalContext):
        await self.log_change(context.operation)
    
    async def after_delete(self, context: SignalContext):
        await self.log_deletion()
    
    # === Cache Management ===
    async def after_update(self, context: SignalContext):
        cache.delete(f"user:{self.id}")
    
    # === Notifications ===
    async def after_create(self, context: SignalContext):
        await self.send_welcome_email()
```

### Error Handling

```python
# Graceful error handling in signals
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
import logging

logger = logging.getLogger(__name__)

class User(ObjectModel):
    async def after_create(self, context: SignalContext):
        try:
            # Non-critical operations
            await self.send_welcome_email()
            await self.create_default_preferences()
        except Exception as e:
            # Log but don't fail the transaction
            logger.error(f"Post-creation tasks failed for user {self.id}: {e}")
    
    async def before_save(self, context: SignalContext):
        # Critical validation - let exceptions bubble up
        if not self.email:
            raise ValidationError("Email is required")
```