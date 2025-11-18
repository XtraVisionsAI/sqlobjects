# Validation & Signals Guide

## Core Concepts

- **Field-level Validation**: Validators parameter for field-specific validation
- **Model-level Validation**: validate() method for cross-field validation
- **Signal System**: Lifecycle hooks for database operations
- **Smart Operation Detection**: Automatic CREATE/UPDATE detection for signals
- **Bulk Signals**: Class-level signals for bulk operations

## Common Usage

### Field-level Validation

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column, StringColumn, IntegerColumn
from sqlobjects.exceptions import ValidationError

# Built-in validators
def validate_email(value: str) -> str:
    if "@" not in value:
        raise ValidationError("Invalid email address", field="email")
    return value

def validate_age(value: int) -> int:
    if value < 0 or value > 150:
        raise ValidationError("Age must be between 0 and 150", field="age")
    return value

class User(ObjectModel):
    email: Column[str] = column(type="string", length=100, validators=[validate_email])
    age: Column[int] = column(type="integer", validators=[validate_age])
```

### Model-level Validation

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn()
    is_admin: Column[bool] = BooleanColumn(default=False)
    
    def validate(self):
        """Model-level validation for cross-field rules"""
        # Business rule validation
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21 years old")
        
        # Cross-field validation
        if self.username and self.username == self.email.split("@")[0]:
            raise ValidationError("Username cannot be same as email prefix")
```

### Instance-level Signals

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    created_at: Column[datetime] = DateTimeColumn()
    updated_at: Column[datetime] = DateTimeColumn()
    
    # Universal save signals (always triggered)
    async def before_save(self, context: SignalContext):
        """Called before any save operation"""
        self.updated_at = datetime.now()
    
    async def after_save(self, context: SignalContext):
        """Called after any save operation"""
        print(f"User {self.username} saved")
    
    # Operation-specific signals (triggered based on detected operation)
    async def before_create(self, context: SignalContext):
        """Only triggered for CREATE operations"""
        self.created_at = datetime.now()
    
    async def before_update(self, context: SignalContext):
        """Only triggered for UPDATE operations"""
        print(f"Updating user {self.username}")
    
    async def after_create(self, context: SignalContext):
        """After creation only"""
        await self.send_welcome_email()
    
    async def after_update(self, context: SignalContext):
        """After update only"""
        await self.notify_profile_changes()
    
    # Deletion signals
    async def before_delete(self, context: SignalContext):
        """Before deletion"""
        await self.log_deletion()
    
    async def after_delete(self, context: SignalContext):
        """After deletion"""
        await self.cleanup_related_data()
```

### Bulk Operation Signals

```python
class User(ObjectModel):
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        """Before bulk creation of multiple records"""
        print(f"Creating {context.affected_count} users")
    
    @classmethod
    async def after_bulk_create(cls, context: SignalContext):
        """After bulk creation"""
        await cls.send_bulk_welcome_emails(context.affected_count)
    
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        """Before bulk update"""
        print(f"Updating {context.affected_count} users")
        if context.update_data:
            print(f"Update fields: {list(context.update_data.keys())}")
    
    @classmethod
    async def after_bulk_update(cls, context: SignalContext):
        """After bulk update"""
        print(f"Updated {context.affected_count} users")
    
    @classmethod
    async def before_bulk_delete(cls, context: SignalContext):
        """Before bulk deletion"""
        print(f"Deleting {context.affected_count} users")
    
    @classmethod
    async def after_bulk_delete(cls, context: SignalContext):
        """After bulk deletion"""
        await cls.cleanup_bulk_related_data()
```

## Best Practices

### ✅ Do

- **Use field validators** for field-specific rules
- **Use model validate()** for cross-field rules
- **Keep signals fast** - avoid heavy operations
- **Use async signals** for I/O operations
- **Handle signal errors** gracefully

```python
# Good: Field-level validation
class User(ObjectModel):
    email: Column[str] = column(type="string", validators=[validate_email])
    age: Column[int] = column(type="integer", validators=[validate_age])
    
    # Good: Cross-field validation
    def validate(self):
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21 years old")
    
    # Good: Fast signal operations
    async def before_save(self, context: SignalContext):
        self.updated_at = datetime.now()  # Fast
    
    # Good: Non-critical operations with error handling
    async def after_create(self, context: SignalContext):
        try:
            await self.send_welcome_email()
        except Exception as e:
            logger.error(f"Failed to send welcome email: {e}")
            # Don't fail the transaction
```

### ❌ Don't

- **Don't put business logic** in field validators (use model validate())
- **Don't do heavy operations** in before_save signals
- **Don't fail transactions** in after_* signals for non-critical operations
- **Don't forget to await** async signal handlers

```python
# Bad: Business logic in field validator
def validate_username(value: str) -> str:
    if User.objects.filter(User.username == value).exists():  # Database query!
        raise ValidationError("Username already exists")
    return value

# Good: Use model validate() or database constraints
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)  # Database constraint

# Bad: Heavy operation in before_save
async def before_save(self, context: SignalContext):
    await self.process_large_file()  # Slow!
    await self.send_notifications()  # Slow!

# Good: Keep before_save fast, use after_save for heavy operations
async def before_save(self, context: SignalContext):
    self.updated_at = datetime.now()  # Fast

async def after_save(self, context: SignalContext):
    asyncio.create_task(self.process_large_file())  # Background task
```

## Signal Execution Flow

### save() Operation Signals

```python
# For new instances (no primary key)
user = User(username="alice", email="alice@example.com")
await user.save()
# Triggers: before_save → before_create → after_save → after_create

# For existing instances (has primary key)
user.email = "newemail@example.com"
await user.save()
# Triggers: before_save → before_update → after_save → after_update
```

### Signal Context Information

```python
async def before_save(self, context: SignalContext):
    # Operation information
    print(f"Operation: {context.operation}")  # SAVE, CREATE, UPDATE, DELETE
    print(f"Actual operation: {context.actual_operation}")  # CREATE or UPDATE for SAVE
    
    # Session and model information
    print(f"Session: {context.session}")
    print(f"Model class: {context.model_class}")
    print(f"Instance: {context.instance}")
    
    # Bulk operation information
    print(f"Is bulk: {context.is_bulk}")
    print(f"Affected count: {context.affected_count}")
    print(f"Update data: {context.update_data}")
```

## Validation Patterns

### Custom Validators

```python
# Pattern validator
def validate_pattern(pattern: str, message: str = None):
    import re
    def validator(value: str) -> str:
        if not re.match(pattern, value):
            raise ValidationError(message or f"Value must match pattern: {pattern}")
        return value
    return validator

# Range validator
def validate_range(min_value, max_value):
    def validator(value) -> int:
        if value < min_value or value > max_value:
            raise ValidationError(f"Value must be between {min_value} and {max_value}")
        return value
    return validator

# Usage
class User(ObjectModel):
    username: Column[str] = column(
        type="string",
        validators=[validate_pattern(r'^[a-zA-Z0-9_]+$', "Username must be alphanumeric")]
    )
    age: Column[int] = column(type="integer", validators=[validate_range(0, 150)])
```

### Conditional Validation

```python
class User(ObjectModel):
    role: Column[str] = StringColumn(length=20)
    admin_code: Column[str] = StringColumn(length=50, nullable=True)
    
    def validate(self):
        # Conditional validation based on role
        if self.role == "admin" and not self.admin_code:
            raise ValidationError("Admin users must have an admin code")
        
        if self.role != "admin" and self.admin_code:
            raise ValidationError("Only admin users can have admin codes")
```

## Performance Tips

### Signal Performance

```python
# Group related operations
async def after_create(self, context: SignalContext):
    await asyncio.gather(
        self.send_welcome_email(),
        self.create_default_preferences(),
        self.log_user_creation()
    )

# Background tasks for non-critical operations
async def after_save(self, context: SignalContext):
    # Critical operations (blocking)
    self.updated_at = datetime.now()
    
    # Non-critical operations (background)
    if not context.is_bulk:
        asyncio.create_task(self.update_search_index())
```

### Validation Performance

```python
# Cache expensive validations
class User(ObjectModel):
    email: Column[str] = column(type="string", validators=[validate_email])
    
    def validate(self):
        # Expensive validation - cache result
        if not hasattr(self, '_validation_cache'):
            self._validation_cache = {}
        
        if 'email_domain' not in self._validation_cache:
            self._validation_cache['email_domain'] = self._check_email_domain()
        
        if not self._validation_cache['email_domain']:
            raise ValidationError("Email domain not allowed")
```

## Troubleshooting

### Validation Not Triggered

**Problem**: Validation not running on save

**Solution**:
```python
# Ensure validate=True (default)
await user.save(validate=True)

# Or call validation manually
user.validate_all_fields()
await user.save()
```

### Signal Not Triggered

**Problem**: Signal handler not called

**Solution**:
```python
# Check method name matches signal convention
async def before_save(self, context: SignalContext):  # Correct
    pass

# Not: async def beforesave(self, context):  # Wrong name!

# Check it's an instance method (not class method) for instance signals
async def before_save(self, context: SignalContext):  # Correct
    pass

# Not: @classmethod async def before_save(cls, context):  # Wrong for instance signals!
```

### Signal Errors Break Transaction

**Problem**: Exception in signal rolls back transaction

**Solution**:
```python
# Handle non-critical errors in after_* signals
async def after_create(self, context: SignalContext):
    try:
        await self.send_welcome_email()
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        # Don't re-raise - transaction continues

# Let critical errors propagate in before_* signals
async def before_save(self, context: SignalContext):
    if not self.is_valid():
        raise ValidationError("Invalid data")  # Should fail transaction
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.signals import SignalContext
from sqlobjects.exceptions import ValidationError
from datetime import datetime
import asyncio

# Custom validators
def validate_email(value: str) -> str:
    if "@" not in value or "." not in value.split("@")[1]:
        raise ValidationError("Invalid email address", field="email")
    return value

def validate_age(value: int) -> int:
    if value < 0 or value > 150:
        raise ValidationError("Age must be between 0 and 150", field="age")
    return value

class User(ObjectModel):
    # Fields with validators
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = column(type="string", length=100, validators=[validate_email])
    age: Column[int] = column(type="integer", validators=[validate_age])
    is_admin: Column[bool] = BooleanColumn(default=False)
    created_at: Column[datetime] = DateTimeColumn()
    updated_at: Column[datetime] = DateTimeColumn()
    
    # Model-level validation
    def validate(self):
        if self.is_admin and self.age < 21:
            raise ValidationError("Admin users must be at least 21 years old")
    
    # Instance signals
    async def before_save(self, context: SignalContext):
        self.updated_at = datetime.now()
    
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()
    
    async def after_create(self, context: SignalContext):
        try:
            await self.send_welcome_email()
        except Exception as e:
            print(f"Failed to send email: {e}")
    
    async def before_delete(self, context: SignalContext):
        await self.log_deletion()
    
    # Bulk signals
    @classmethod
    async def after_bulk_create(cls, context: SignalContext):
        print(f"Created {context.affected_count} users")

# Usage
user = User(username="alice", email="alice@example.com", age=25)
await user.save()  # Triggers validation and signals
```
