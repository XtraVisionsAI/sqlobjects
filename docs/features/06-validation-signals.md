# Validation & Signals

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/06-validation-signals.md](../../docs-zh/features/06-validation-signals.md)

SQLObjects provides comprehensive data validation and lifecycle hooks through a powerful signal system that integrates seamlessly with database operations.

## Data Validation

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
        """Model-level validation for business rules"""
        if not self.email:
            raise ValidationError("Email is required")
        
        # Cross-field validation
        if self.is_admin and self.age and self.age < 18:
            raise ValidationError("Admin users must be at least 18 years old")
        
        # Complex business logic
        if self.username and self.email and self.username in self.email:
            raise ValidationError("Username cannot be part of email address")
```

### Custom Validators

```python
def validate_username_format(value: str) -> str:
    """Custom validator for username format"""
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', value):
        raise ValidationError(
            "Username can only contain letters, numbers, and underscores",
            code="invalid_format"
        )
    return value

def validate_unique_email(value: str) -> str:
    """Custom validator for email uniqueness"""
    async def check_uniqueness():
        exists = await User.objects.filter(User.email == value).exists()
        if exists:
            raise ValidationError("Email already exists", code="unique")
    
    # Note: Async validators need special handling
    return value

class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50,
        validators=[validate_username_format]
    )
    email: Column[str] = StringColumn(
        length=100,
        validators=[validate_email(), validate_unique_email]
    )
```

### Validation Execution

```python
# Automatic validation on save
user = User(username="test", email="invalid-email")
try:
    await user.save()  # Validation executed automatically
except ValidationError as e:
    print(f"Validation failed: {e}")

# Manual validation
user = User(username="test", email="test@example.com")
try:
    user.validate()  # Manual validation
    print("Validation passed")
except ValidationError as e:
    print(f"Validation failed: {e}")

# Skip validation
user = User(username="test", email="invalid-email")
await user.save(validate=False)  # Skip validation
```

## Signal System

### Instance-Level Signals

```python
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    created_at: Column[datetime] = DateTimeColumn(nullable=True)
    updated_at: Column[datetime] = DateTimeColumn(nullable=True)
    
    # Universal save signals (always triggered)
    async def before_save(self, context: SignalContext):
        """Called before any save operation (CREATE or UPDATE)"""
        self.updated_at = datetime.now()
    
    async def after_save(self, context: SignalContext):
        """Called after any save operation (CREATE or UPDATE)"""
        await self.invalidate_cache()
    
    # Operation-specific signals (triggered based on detected operation)
    async def before_create(self, context: SignalContext):
        """Only triggered for CREATE operations"""
        self.created_at = datetime.now()
        await self.generate_uuid()
    
    async def before_update(self, context: SignalContext):
        """Only triggered for UPDATE operations"""
        self.version += 1
    
    async def after_create(self, context: SignalContext):
        """After creation only"""
        await self.send_welcome_email()
        await self.create_default_profile()
    
    async def after_update(self, context: SignalContext):
        """After update only"""
        await self.notify_profile_changes()
    
    # Deletion signals
    async def before_delete(self, context: SignalContext):
        """Before deletion"""
        await self.log_deletion()
        await self.cleanup_related_data()
    
    async def after_delete(self, context: SignalContext):
        """After deletion"""
        await self.send_deletion_notification()
```

### Bulk Operation Signals

```python
class User(ObjectModel):
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        """Before bulk creation of multiple records"""
        logger.info(f"Creating {context.affected_count} users")
        await cls.prepare_bulk_resources()
    
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        """Before bulk update of multiple records"""
        logger.info(f"Updating {context.affected_count} users")
        if context.update_data:
            logger.info(f"Update fields: {list(context.update_data.keys())}")
    
    @classmethod
    async def before_bulk_delete(cls, context: SignalContext):
        """Before bulk deletion of multiple records"""
        logger.info(f"Deleting {context.affected_count} users")
        await cls.backup_deleted_data(context)
    
    @classmethod
    async def after_bulk_create(cls, context: SignalContext):
        """After bulk creation"""
        await cls.send_bulk_welcome_emails(context.affected_count)
        await cls.update_statistics("user_created", context.affected_count)
    
    @classmethod
    async def after_bulk_update(cls, context: SignalContext):
        """After bulk update"""
        await cls.invalidate_bulk_caches(context.affected_count)
    
    @classmethod
    async def after_bulk_delete(cls, context: SignalContext):
        """After bulk deletion"""
        await cls.cleanup_bulk_related_data()
```

### Signal Context Information

```python
from sqlobjects.signals import SignalContext, Operation

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        # Operation information
        print(f"Operation: {context.operation}")           # SAVE, CREATE, UPDATE, DELETE
        print(f"Actual operation: {context.actual_operation}")  # Detected operation for SAVE
        
        # Session and model information
        print(f"Session: {context.session}")               # Database session
        print(f"Model class: {context.model_class}")       # Model class
        print(f"Instance: {context.instance}")             # Model instance
        
        # Bulk operation information (for bulk signals)
        print(f"Affected count: {context.affected_count}") # For bulk operations
        print(f"Update data: {context.update_data}")       # For bulk updates
        
        # Additional metadata
        print(f"Timestamp: {context.timestamp}")           # Operation timestamp
        print(f"User context: {context.user_context}")     # Optional user context
```

### Smart SAVE Operation Detection

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    async def before_save(self, context: SignalContext):
        if context.actual_operation == Operation.CREATE:
            print("This is a CREATE operation")
            self.created_at = datetime.now()
        elif context.actual_operation == Operation.UPDATE:
            print("This is an UPDATE operation")
            self.updated_at = datetime.now()

# Usage examples
user = User(username="new_user")
await user.save()  # Triggers: before_save → before_create → after_save → after_create

user.username = "updated_user"
await user.save()  # Triggers: before_save → before_update → after_save → after_update
```

## Advanced Validation

### Async Validation

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    
    async def validate(self):
        """Async model validation"""
        # Check username uniqueness
        if self.username:
            exists = await User.objects.filter(
                User.username == self.username,
                User.id != self.id  # Exclude self for updates
            ).exists()
            if exists:
                raise ValidationError("Username already exists")
        
        # External API validation
        if self.email:
            is_valid = await validate_email_with_external_service(self.email)
            if not is_valid:
                raise ValidationError("Email validation failed")
```

### Conditional Validation

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    is_premium: Column[bool] = BooleanColumn(default=False)
    subscription_expires: Column[datetime] = DateTimeColumn(nullable=True)
    
    def validate(self):
        # Conditional validation based on user type
        if self.is_premium:
            if not self.subscription_expires:
                raise ValidationError("Premium users must have subscription expiry date")
            
            if self.subscription_expires < datetime.now():
                raise ValidationError("Subscription has expired")
        
        # Cross-field validation
        if self.is_premium and not self.email:
            raise ValidationError("Premium users must have email address")
```

### Validation Groups

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    phone: Column[str] = StringColumn(length=20, nullable=True)
    
    def validate(self, validation_group=None):
        """Validation with groups"""
        if validation_group == "registration":
            # Only validate required fields for registration
            if not self.username:
                raise ValidationError("Username is required")
            if not self.email:
                raise ValidationError("Email is required")
        
        elif validation_group == "profile_update":
            # Validate all fields for profile updates
            if self.phone and not self.phone.startswith('+'):
                raise ValidationError("Phone number must include country code")
        
        else:
            # Default validation
            super().validate()

# Usage
user = User(username="test")
user.validate(validation_group="registration")  # Only check required fields
```

## Signal Integration with Operations

### CRUD Operation Signals

```python
# Create operations
user = await User.objects.create(username="alice")
# Triggers: before_save → before_create → after_save → after_create

# Update operations
user.email = "alice@example.com"
await user.save()
# Triggers: before_save → before_update → after_save → after_update

# Delete operations
await user.delete()
# Triggers: before_delete → after_delete

# Bulk operations
await User.objects.bulk_create(users_data)
# Triggers: before_bulk_create → after_bulk_create
```

### get_or_create Signal Integration

```python
user, created = await User.objects.get_or_create(
    username="signal_user",
    defaults={"email": "signal@example.com"}
)

# If created: before_save → before_create → after_save → after_create
# If found: no signals triggered
```

## Error Handling in Signals

### Signal Error Handling

```python
import logging

logger = logging.getLogger(__name__)

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
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
        
        # Business rule validation
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21 years old")
```

### Validation Error Handling

```python
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    def validate(self):
        errors = []
        
        # Collect all validation errors
        if not self.username:
            errors.append("Username is required")
        
        if not self.email:
            errors.append("Email is required")
        elif not "@" in self.email:
            errors.append("Invalid email format")
        
        if self.age and self.age < 0:
            errors.append("Age cannot be negative")
        
        # Raise all errors together
        if errors:
            raise ValidationError("; ".join(errors))

# Usage with error handling
try:
    user = User(username="", email="invalid", age=-5)
    user.validate()
except ValidationError as e:
    print(f"Multiple validation errors: {e}")
```

## Testing Validation and Signals

### Validation Testing

```python
import pytest
from sqlobjects.exceptions import ValidationError

class TestUserValidation:
    def test_username_validation(self):
        """Test username validation rules"""
        # Valid username
        user = User(username="validuser", email="test@example.com")
        user.validate()  # Should not raise
        
        # Invalid username (too short)
        user = User(username="ab", email="test@example.com")
        with pytest.raises(ValidationError) as exc_info:
            user.validate()
        assert "username" in str(exc_info.value).lower()
    
    def test_email_validation(self):
        """Test email validation"""
        # Valid email
        user = User(username="test", email="test@example.com")
        user.validate()
        
        # Invalid email
        user = User(username="test", email="invalid-email")
        with pytest.raises(ValidationError):
            user.validate()
    
    async def test_async_validation(self):
        """Test async validation"""
        user = User(username="test", email="test@example.com")
        await user.validate()  # Should not raise
```

### Signal Testing

```python
class TestUserSignals:
    async def test_before_save_signal(self):
        """Test before_save signal is triggered"""
        user = User(username="test", email="test@example.com")
        
        # Mock signal handler
        with patch.object(user, 'before_save') as mock_signal:
            await user.save()
            mock_signal.assert_called_once()
    
    async def test_signal_context_information(self):
        """Test signal context contains correct information"""
        user = User(username="test", email="test@example.com")
        
        async def check_context(context):
            assert context.operation == Operation.SAVE
            assert context.actual_operation == Operation.CREATE
            assert context.instance == user
            assert context.model_class == User
        
        user.before_save = check_context
        await user.save()
    
    async def test_bulk_signals(self):
        """Test bulk operation signals"""
        signals_called = []
        
        @classmethod
        async def mock_before_bulk_create(cls, context):
            signals_called.append("before_bulk_create")
            assert context.affected_count == 3
        
        User.before_bulk_create = mock_before_bulk_create
        
        await User.objects.bulk_create([
            {"username": "user1", "email": "user1@example.com"},
            {"username": "user2", "email": "user2@example.com"},
            {"username": "user3", "email": "user3@example.com"},
        ])
        
        assert "before_bulk_create" in signals_called
```

## Best Practices

### Validation Best Practices

1. **Use field-level validation for simple rules**: Format, length, range validation
2. **Use model-level validation for business logic**: Cross-field validation, complex rules
3. **Keep validation fast**: Avoid expensive operations in validation
4. **Provide clear error messages**: Help users understand what went wrong
5. **Use async validation sparingly**: Only when necessary for database checks

### Signal Best Practices

```python
class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        # ✅ Good: Fast, critical operations only
        self.updated_at = datetime.now()
        
        # ✅ Good: Validation that must succeed
        if not self.email:
            raise ValidationError("Email is required")
    
    async def after_create(self, context: SignalContext):
        # ✅ Good: Non-critical operations with error handling
        try:
            await self.send_welcome_email()
        except Exception as e:
            logger.error(f"Failed to send welcome email: {e}")
        
        # ❌ Bad: Don't do expensive operations that can fail the transaction
        # await self.process_large_image()  # This should be done asynchronously
    
    async def before_delete(self, context: SignalContext):
        # ✅ Good: Cleanup and validation
        await self.cleanup_related_data()
        
        # ✅ Good: Prevent deletion if needed
        if await self.has_active_subscriptions():
            raise ValidationError("Cannot delete user with active subscriptions")
```

### Performance Considerations

```python
# ✅ Good: Efficient signal handling
class User(ObjectModel):
    async def after_create(self, context: SignalContext):
        # Group related operations
        await asyncio.gather(
            self.send_welcome_email(),
            self.create_default_preferences(),
            self.log_user_creation()
        )
    
    async def before_save(self, context: SignalContext):
        # Critical operations only - keep fast
        self.updated_at = datetime.now()
        
        # Non-critical operations in background
        if not context.is_bulk_operation:
            asyncio.create_task(self.update_search_index())

# ❌ Bad: Slow operations in signals
class User(ObjectModel):
    async def after_create(self, context: SignalContext):
        # Don't do this - blocks the transaction
        await self.resize_profile_image()  # Expensive operation
        await self.send_email_to_all_admins()  # Network operation
```