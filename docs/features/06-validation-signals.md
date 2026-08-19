# Validation and Signals

## Overview

SQLObjects provides comprehensive field-level and model-level validation capabilities, along with a powerful signal
system for hooking into database operations and providing automated lifecycle management.

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
            raise ValidationError("User must be at least 13 years old")
```

### Basic Signals

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime, timezone

class User(ObjectModel):  # Built-in signal support
    # ... field definitions ...

    async def before_save(self, context: SignalContext):
        """Called before any save operation"""
        self.updated_at = datetime.now(timezone.utc)

    async def before_create(self, context: SignalContext):
        """Called only before creating new records"""
        self.created_at = datetime.now(timezone.utc)
```

## Field Validation

### Built-in Validators

```python
from sqlobjects.validators import (
    validate_email, validate_url, validate_length, validate_range,
    validate_regex, validate_choice, validate_not_empty, validate_positive,
    validate_datetime_range
)
from datetime import datetime, timezone

class User(ObjectModel):
    # Email validation
    email: Column[str] = StringColumn(validators=[validate_email()])

    # Length validation
    username: Column[str] = StringColumn(validators=[validate_length(3, 50)])

    # Range validation
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])

    # Regular expression validation
    phone: Column[str] = StringColumn(validators=[validate_regex(r"^\d{3}-\d{3}-\d{4}$")])

    # Choice validation (value must be one of the allowed choices)
    status: Column[str] = StringColumn(validators=[validate_choice(["active", "inactive", "pending"])])

    # URL validation
    website: Column[str] = StringColumn(validators=[validate_url()])

    # Not-empty validation
    display_name: Column[str] = StringColumn(validators=[validate_not_empty()])

    # Positive-number validation
    credits: Column[int] = IntegerColumn(validators=[validate_positive()])

    # Datetime range validation
    signup_at: Column[datetime] = DateTimeColumn(
        validators=[validate_datetime_range(min_date=datetime(2020, 1, 1))]
    )
```

### Advanced Validators

```python
from sqlobjects.validators import validate_regex, validate_choice

class Document(ObjectModel):
    title: Column[str] = StringColumn(length=200)

    # Validate file extensions with regex
    filename: Column[str] = StringColumn(validators=[
        validate_regex(
            r'\.(pdf|doc|docx|txt)$',
            "File must be PDF, DOC, DOCX, or TXT format"
        )
    ])

    # Document type validation
    doc_type: Column[str] = StringColumn(validators=[
        validate_choice(["report", "manual", "specification", "other"])
    ])

    # File size validation (string representation)
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
        raise ValidationError("Username can only contain letters and numbers")

    # Check reserved names
    reserved = ["admin", "root", "system", "api"]
    if value.lower() in reserved:
        raise ValidationError("This username is reserved")

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

The `validators` parameter is a list, and every validator in it is applied in
sequence to the field value (see `validate_field_value` in
`sqlobjects/validators.py`). To combine multiple validators, just list them —
there is no separate combinator helper:

```python
from sqlobjects.validators import validate_length, validate_regex, validate_email

class User(ObjectModel):
    # Multiple validators run in order: length first, then pattern, then custom
    username: Column[str] = StringColumn(validators=[
        validate_length(3, 50),
        validate_regex(r"^[a-zA-Z0-9_]+$"),
        validate_username,  # Custom validator function
    ])

    # Built-in and length validators together
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
        # Admin user age restriction
        if self.is_admin and self.age and self.age < 18:
            raise ValidationError("Admin users must be at least 18 years old")
    
        # Email domain restriction
        if self.email and self.is_admin:
            if not self.email.endswith("@company.com"):
                raise ValidationError("Admin users must use company email")
    
        # Username uniqueness (example - typically handled by database constraints)
        if self.username:
            existing = User.objects.filter(
                User.username == self.username,
                User.id != self.id  # Exclude self when updating
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
)  # Automatically validated

# Skip validation for trusted data
system_user = await User.objects.create(
    username="system",
    email="system@internal.com",
    validate=False  # Skip validation
)

# Manual validation
user = User(username="alice", email="alice@example.com")
user.validate_all_fields()  # Validate all fields
user.validate_all_fields(["username", "email"])  # Validate specific fields
user.validate_field("username")  # Validate a single field
user.validate()  # Model-level validation only (if defined on the model)

# Validation on save
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
    user.validate_all_fields()
except ValidationError as e:
    print(f"Validation failed: {e.message}")
    print(f"Field: {e.field}")
    print(f"Code: {e.code}")

# Multiple validation errors
try:
    user = User(username="a", email="bad", age=-5)
    user.validate_all_fields()
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
collector.raise_if_errors()  # Raise ValidationError if any errors exist
```

## Signal System

### Signal Types

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime, timezone
import uuid

class User(ObjectModel):  # Built-in signal functionality
    # Instance-level signals (single record operations)
    async def before_save(self, context: SignalContext):
        """Generic save logic - always fired"""
        self.updated_at = datetime.now(timezone.utc)

    async def before_create(self, context: SignalContext):
        """Only fired on CREATE operations"""
        self.created_at = datetime.now(timezone.utc)
        self.uuid = str(uuid.uuid4())

    async def before_update(self, context: SignalContext):
        """Only fired on UPDATE operations"""
        self.version += 1

    async def before_delete(self, context: SignalContext):
        """Fired before deletion"""
        # Log deletion or cleanup operations
        await AuditLog.objects.create(
            action="delete",
            model="User",
            object_id=self.id
        )

    async def after_save(self, context: SignalContext):
        """After save operations"""
        # Send notifications, update cache, etc.
        pass

    async def after_create(self, context: SignalContext):
        """Only after creation"""
        # Send welcome email, create related objects
        await self.send_welcome_email()

    async def after_update(self, context: SignalContext):
        """Only after updates"""
        # Invalidate cache, send update notifications
        cache.delete(f"user:{self.id}")

    async def after_delete(self, context: SignalContext):
        """After deletion"""
        # Clean up related data
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
        """Before bulk updates"""
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
        # Send bulk notifications
        pass

    @classmethod
    async def after_bulk_update(cls, context: SignalContext):
        """After bulk updates"""
        # Invalidate cache for affected records
        pass

    @classmethod
    async def after_bulk_delete(cls, context: SignalContext):
        """After bulk deletion"""
        # Clean up related data
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
    print(f"Instance: {context.instance}")  # Model instance (single operations)
    print(f"Affected count: {context.affected_count}")  # Bulk operations
    print(f"Update data: {context.update_data}")  # Bulk updates
    print(f"Actual operation: {context.actual_operation}")  # Detected operation for SAVE
```

### Smart SAVE Operations

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime, timezone

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        """Always called for save() operations"""
        self.updated_at = datetime.now(timezone.utc)

    async def before_create(self, context: SignalContext):
        """Called for new instances"""
        self.created_at = datetime.now(timezone.utc)

    async def before_update(self, context: SignalContext):
        """Called for existing instances"""
        self.version += 1

# Smart save automatically detects CREATE vs UPDATE
user = User(username="new_user")  # No primary key
await user.save()  # Fires: before_save → before_create → after_save → after_create

user.username = "updated_user"
await user.save()  # Fires: before_save → before_update → after_save → after_update

# Detached instance with primary key
detached_user = User(id=1, username="detached")
await detached_user.save()  # Fires: before_save → before_update → after_save → after_update
```

### Signal Integration with Operations

```python
# get_or_create and update_or_create trigger signals
user, created = await User.objects.get_or_create(
    username="signal_user",
    defaults={"email": "signal@example.com"}
)
# If created: before_save → before_create → after_save → after_create
# If found: no signals fired

user, created = await User.objects.update_or_create(
    username="signal_user",
    defaults={"last_login": datetime.now(timezone.utc)}
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
        # Perform validation before saving
        if not self.email:
            raise ValidationError("Email is required")
    
        # Business rule validation
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21 years old")

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
# Layered validation
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.validators import validate_email, validate_range
from sqlobjects.exceptions import ValidationError
from sqlobjects.signals import SignalContext

class User(ObjectModel):
    # Field-level: basic format validation
    email: Column[str] = StringColumn(validators=[validate_email()])
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])
    is_admin: Column[bool] = BooleanColumn(default=False)

    # Model-level: cross-field and business rules
    def validate(self):
        if self.is_admin and self.age < 18:
            raise ValidationError("Admin users must be adults")

    # Signal-level: database-dependent validation
    async def before_save(self, context: SignalContext):
        if await self.has_pending_violations():
            raise ValidationError("Cannot save user with pending violations")
```

### Signal Organization

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime, timezone

class User(ObjectModel):
    # Group related signal handlers

    # === Timestamp management ===
    async def before_save(self, context: SignalContext):
        self.updated_at = datetime.now(timezone.utc)

    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now(timezone.utc)

    # === Audit logging ===
    async def after_save(self, context: SignalContext):
        await self.log_change(context.operation)

    async def after_delete(self, context: SignalContext):
        await self.log_deletion()

    # === Cache management ===
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