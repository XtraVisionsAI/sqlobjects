# Extensions

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/design/05-extensions.md](../../docs-zh/design/05-extensions.md)

This document describes the internal architecture and implementation details of SQLObjects' extension system, including signals, validation, custom field types, and plugin architecture.

## Extension Architecture

### Core Extension Points

```python
# Extension system structure
sqlobjects/
├── signals.py       # Signal system and lifecycle hooks
├── validators.py    # Validation framework and built-in validators
├── exceptions.py    # Exception hierarchy and error handling
├── mixins.py        # Reusable functionality mixins
└── extensions/      # Extension framework (future)
    ├── __init__.py
    ├── base.py      # Base extension classes
    ├── registry.py  # Extension registry
    └── loader.py    # Extension loading system
```

### Signal System Architecture

```python
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING
from datetime import datetime
import asyncio

if TYPE_CHECKING:
    from sqlobjects.model import ObjectModel
    from sqlobjects.session import AsyncSession

class Operation(Enum):
    """Database operation types"""
    SAVE = "save"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_CREATE = "bulk_create"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"

class SignalContext:
    """Context information for signal handlers"""
    
    def __init__(
        self,
        operation: Operation,
        instance: Optional["ObjectModel"] = None,
        model_class: Optional[type] = None,
        session: Optional["AsyncSession"] = None,
        actual_operation: Optional[Operation] = None,
        affected_count: int = 0,
        update_data: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None
    ):
        self.operation = operation
        self.instance = instance
        self.model_class = model_class
        self.session = session
        self.actual_operation = actual_operation or operation
        self.affected_count = affected_count
        self.update_data = update_data
        self.user_context = user_context or {}
        self.timestamp = datetime.now()
    
    @property
    def is_bulk_operation(self) -> bool:
        """Check if this is a bulk operation"""
        return self.operation.value.startswith("bulk_")

class SignalRegistry:
    """Registry for signal handlers"""
    
    def __init__(self):
        self._handlers = {}
    
    def register_handler(self, model_class: type, signal_name: str, handler):
        """Register signal handler for model"""
        if model_class not in self._handlers:
            self._handlers[model_class] = {}
        
        if signal_name not in self._handlers[model_class]:
            self._handlers[model_class][signal_name] = []
        
        self._handlers[model_class][signal_name].append(handler)
    
    def get_handlers(self, model_class: type, signal_name: str):
        """Get handlers for model and signal"""
        handlers = []
        
        # Get handlers from model class and all parent classes
        for cls in model_class.__mro__:
            if cls in self._handlers and signal_name in self._handlers[cls]:
                handlers.extend(self._handlers[cls][signal_name])
        
        return handlers
    
    async def emit_signal(self, model_class: type, signal_name: str, context: SignalContext):
        """Emit signal to all registered handlers"""
        handlers = self.get_handlers(model_class, signal_name)
        
        if handlers:
            # Execute all handlers concurrently
            tasks = []
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(context))
                else:
                    # Wrap sync handlers in async
                    tasks.append(asyncio.create_task(asyncio.to_thread(handler, context)))
            
            if tasks:
                await asyncio.gather(*tasks)

# Global signal registry
signal_registry = SignalRegistry()
```

### Signal Mixin Implementation

```python
class SignalMixin:
    """Mixin providing signal functionality to models"""
    
    def __init_subclass__(cls, **kwargs):
        """Auto-register signal handlers when class is created"""
        super().__init_subclass__(**kwargs)
        cls._register_signal_handlers()
    
    @classmethod
    def _register_signal_handlers(cls):
        """Automatically register signal handlers from method names"""
        signal_methods = [
            # Instance signals
            "before_save", "after_save",
            "before_create", "after_create",
            "before_update", "after_update",
            "before_delete", "after_delete",
            
            # Bulk signals
            "before_bulk_create", "after_bulk_create",
            "before_bulk_update", "after_bulk_update",
            "before_bulk_delete", "after_bulk_delete",
        ]
        
        for method_name in signal_methods:
            if hasattr(cls, method_name):
                handler = getattr(cls, method_name)
                if callable(handler):
                    signal_registry.register_handler(cls, method_name, handler)
    
    async def _emit_signal(self, signal_name: str, context: SignalContext):
        """Emit signal for this instance"""
        await signal_registry.emit_signal(self.__class__, signal_name, context)
    
    @classmethod
    async def _emit_class_signal(cls, signal_name: str, context: SignalContext):
        """Emit class-level signal"""
        await signal_registry.emit_signal(cls, signal_name, context)
```

### Validation System Architecture

```python
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional

class ValidationError(Exception):
    """Raised when validation fails"""
    
    def __init__(self, message: str, field: str = None, code: str = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code
    
    def __str__(self):
        if self.field:
            return f"{self.field}: {self.message}"
        return self.message

class BaseValidator(ABC):
    """Base class for all validators"""
    
    def __init__(self, message: str = None, code: str = None):
        self.message = message
        self.code = code
    
    @abstractmethod
    def __call__(self, value: Any) -> Any:
        """Validate value and return cleaned value"""
        pass
    
    def _get_error_message(self, default_message: str) -> str:
        """Get error message with fallback to default"""
        return self.message or default_message

class LengthValidator(BaseValidator):
    """Validate string length"""
    
    def __init__(self, min_length: int = None, max_length: int = None, **kwargs):
        self.min_length = min_length
        self.max_length = max_length
        super().__init__(**kwargs)
    
    def __call__(self, value: Any) -> Any:
        if value is None:
            return value
        
        if not isinstance(value, str):
            value = str(value)
        
        length = len(value)
        
        if self.min_length is not None and length < self.min_length:
            raise ValidationError(
                self._get_error_message(f"Value must be at least {self.min_length} characters long"),
                code=self.code or "min_length"
            )
        
        if self.max_length is not None and length > self.max_length:
            raise ValidationError(
                self._get_error_message(f"Value must be at most {self.max_length} characters long"),
                code=self.code or "max_length"
            )
        
        return value

class RangeValidator(BaseValidator):
    """Validate numeric range"""
    
    def __init__(self, min_value: float = None, max_value: float = None, **kwargs):
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(**kwargs)
    
    def __call__(self, value: Any) -> Any:
        if value is None:
            return value
        
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (ValueError, TypeError):
                raise ValidationError(
                    self._get_error_message("Value must be a number"),
                    code=self.code or "invalid_number"
                )
        
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(
                self._get_error_message(f"Value must be at least {self.min_value}"),
                code=self.code or "min_value"
            )
        
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(
                self._get_error_message(f"Value must be at most {self.max_value}"),
                code=self.code or "max_value"
            )
        
        return value

class EmailValidator(BaseValidator):
    """Validate email address format"""
    
    def __call__(self, value: Any) -> Any:
        if value is None:
            return value
        
        if not isinstance(value, str):
            value = str(value)
        
        # Simple email validation (can be enhanced)
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_pattern, value):
            raise ValidationError(
                self._get_error_message("Invalid email address format"),
                code=self.code or "invalid_email"
            )
        
        return value

# Validator factory functions
def validate_length(min_length: int = None, max_length: int = None, **kwargs) -> LengthValidator:
    """Create length validator"""
    return LengthValidator(min_length=min_length, max_length=max_length, **kwargs)

def validate_range(min_value: float = None, max_value: float = None, **kwargs) -> RangeValidator:
    """Create range validator"""
    return RangeValidator(min_value=min_value, max_value=max_value, **kwargs)

def validate_email(**kwargs) -> EmailValidator:
    """Create email validator"""
    return EmailValidator(**kwargs)
```

### Validation Mixin Implementation

```python
class ValidationMixin:
    """Mixin providing validation functionality to models"""
    
    def validate(self):
        """Override this method to add model-level validation"""
        pass
    
    def validate_field(self, field_name: str, value: Any) -> Any:
        """Validate single field value"""
        if not hasattr(self.__class__, '__fields__'):
            return value
        
        field = self.__class__.__fields__.get(field_name)
        if field and field.validators:
            for validator in field.validators:
                value = validator(value)
        
        return value
    
    def validate_all_fields(self):
        """Validate all field values"""
        if not hasattr(self.__class__, '__fields__'):
            return
        
        for field_name, field in self.__class__.__fields__.items():
            if field.validators:
                current_value = getattr(self, field_name, None)
                validated_value = self.validate_field(field_name, current_value)
                setattr(self, field_name, validated_value)
    
    def full_clean(self):
        """Perform complete validation (fields + model)"""
        # Validate all fields
        self.validate_all_fields()
        
        # Validate model
        self.validate()
```

### Custom Field Type Extension

```python
class FieldTypeRegistry:
    """Registry for custom field types"""
    
    def __init__(self):
        self._custom_types = {}
    
    def register_field_type(self, type_name: str, field_class: type):
        """Register custom field type"""
        self._custom_types[type_name] = field_class
    
    def get_field_type(self, type_name: str):
        """Get field type class"""
        return self._custom_types.get(type_name)
    
    def create_field(self, type_name: str, **kwargs):
        """Create field instance of custom type"""
        field_class = self.get_field_type(type_name)
        if field_class:
            return field_class(**kwargs)
        
        # Fall back to standard field creation
        from sqlobjects.fields import FieldType
        return FieldType(type=type_name, **kwargs)

# Global field type registry
field_type_registry = FieldTypeRegistry()

# Example custom field type
class PhoneNumberField(FieldType[str]):
    """Custom phone number field with validation"""
    
    def __init__(self, **kwargs):
        # Add phone number validator
        validators = kwargs.get('validators', [])
        validators.append(self._validate_phone_number)
        kwargs['validators'] = validators
        
        super().__init__(type="string", length=20, **kwargs)
    
    def _validate_phone_number(self, value: str) -> str:
        """Validate phone number format"""
        if value is None:
            return value
        
        import re
        # Simple phone number validation
        phone_pattern = r'^\+?1?\d{9,15}$'
        
        if not re.match(phone_pattern, value.replace(' ', '').replace('-', '')):
            raise ValidationError("Invalid phone number format")
        
        return value

# Register custom field type
field_type_registry.register_field_type("phone", PhoneNumberField)
```

### Exception Hierarchy

```python
class SQLObjectsError(Exception):
    """Base exception for all SQLObjects errors"""
    pass

class ValidationError(SQLObjectsError):
    """Raised when data validation fails"""
    
    def __init__(self, message: str, field: str = None, code: str = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code

class DatabaseError(SQLObjectsError):
    """Raised when database operations fail"""
    pass

class ConfigurationError(SQLObjectsError):
    """Raised when configuration is invalid"""
    pass

class QueryError(SQLObjectsError):
    """Raised when query building or execution fails"""
    pass

class SessionError(SQLObjectsError):
    """Raised when session management fails"""
    pass

class IntegrityError(DatabaseError):
    """Raised when database integrity constraints are violated"""
    pass

class DoesNotExist(QueryError):
    """Raised when a query returns no results when one was expected"""
    pass

class MultipleObjectsReturned(QueryError):
    """Raised when a query returns multiple results when one was expected"""
    pass

class FieldError(SQLObjectsError):
    """Raised when field operations fail"""
    pass

class RelationshipError(SQLObjectsError):
    """Raised when relationship operations fail"""
    pass
```

### Mixin System Architecture

```python
class BaseMixin:
    """Base mixin with common functionality"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialize_mixin()
    
    def _initialize_mixin(self):
        """Initialize mixin-specific state"""
        pass

class TimestampMixin(BaseMixin):
    """Mixin adding created_at and updated_at fields"""
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Add timestamp fields to the class
        from sqlobjects.fields import DateTimeColumn
        from datetime import datetime
        
        if not hasattr(cls, 'created_at'):
            cls.created_at = DateTimeColumn(default_factory=datetime.now, nullable=False)
        
        if not hasattr(cls, 'updated_at'):
            cls.updated_at = DateTimeColumn(default_factory=datetime.now, onupdate=datetime.now, nullable=False)
    
    async def before_save(self, context: SignalContext):
        """Update timestamp before save"""
        from datetime import datetime
        
        if context.actual_operation == Operation.UPDATE:
            self.updated_at = datetime.now()
        
        # Call parent signal handler if exists
        if hasattr(super(), 'before_save'):
            await super().before_save(context)

class SoftDeleteMixin(BaseMixin):
    """Mixin adding soft delete functionality"""
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Add deleted_at field
        from sqlobjects.fields import DateTimeColumn
        
        if not hasattr(cls, 'deleted_at'):
            cls.deleted_at = DateTimeColumn(nullable=True, default=None)
    
    async def delete(self, hard_delete: bool = False):
        """Soft delete by default, hard delete if requested"""
        if hard_delete:
            # Call original delete method
            await super().delete()
        else:
            # Soft delete
            from datetime import datetime
            self.deleted_at = datetime.now()
            await self.save()
    
    @classmethod
    def get_queryset(cls):
        """Override queryset to exclude soft-deleted records"""
        queryset = super().get_queryset()
        return queryset.filter(cls.deleted_at.is_(None))
    
    @classmethod
    def all_with_deleted(cls):
        """Get all records including soft-deleted ones"""
        return super().get_queryset()
    
    @classmethod
    def only_deleted(cls):
        """Get only soft-deleted records"""
        return super().get_queryset().filter(cls.deleted_at.is_not(None))

class VersionMixin(BaseMixin):
    """Mixin adding version control functionality"""
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Add version field
        from sqlobjects.fields import IntegerColumn
        
        if not hasattr(cls, 'version'):
            cls.version = IntegerColumn(default=1, nullable=False)
    
    async def before_update(self, context: SignalContext):
        """Increment version before update"""
        self.version += 1
        
        # Call parent signal handler if exists
        if hasattr(super(), 'before_update'):
            await super().before_update(context)
```

### Plugin Architecture (Future Extension)

```python
class BasePlugin:
    """Base class for SQLObjects plugins"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.name = self.__class__.__name__
    
    def initialize(self):
        """Initialize plugin"""
        pass
    
    def register_signals(self, signal_registry: SignalRegistry):
        """Register plugin signal handlers"""
        pass
    
    def register_field_types(self, field_registry: FieldTypeRegistry):
        """Register plugin field types"""
        pass
    
    def register_validators(self, validator_registry):
        """Register plugin validators"""
        pass

class PluginRegistry:
    """Registry for managing plugins"""
    
    def __init__(self):
        self._plugins = {}
        self._initialized = False
    
    def register_plugin(self, plugin: BasePlugin):
        """Register a plugin"""
        self._plugins[plugin.name] = plugin
    
    def get_plugin(self, name: str) -> BasePlugin:
        """Get plugin by name"""
        return self._plugins.get(name)
    
    def initialize_plugins(self):
        """Initialize all registered plugins"""
        if self._initialized:
            return
        
        for plugin in self._plugins.values():
            plugin.initialize()
            plugin.register_signals(signal_registry)
            plugin.register_field_types(field_type_registry)
        
        self._initialized = True
    
    def list_plugins(self):
        """List all registered plugins"""
        return list(self._plugins.keys())

# Global plugin registry
plugin_registry = PluginRegistry()

# Example plugin
class AuditLogPlugin(BasePlugin):
    """Plugin for automatic audit logging"""
    
    def register_signals(self, signal_registry: SignalRegistry):
        """Register audit logging signals"""
        
        async def log_create(context: SignalContext):
            # Log creation
            print(f"Created {context.model_class.__name__}: {context.instance.id}")
        
        async def log_update(context: SignalContext):
            # Log update
            print(f"Updated {context.model_class.__name__}: {context.instance.id}")
        
        async def log_delete(context: SignalContext):
            # Log deletion
            print(f"Deleted {context.model_class.__name__}: {context.instance.id}")
        
        # Register for all models (would need more sophisticated registration)
        # This is a simplified example
        signal_registry.register_handler(None, "after_create", log_create)
        signal_registry.register_handler(None, "after_update", log_update)
        signal_registry.register_handler(None, "after_delete", log_delete)
```

### Extension Integration

```python
class ExtensionIntegrator:
    """Integrate extensions into the main system"""
    
    @staticmethod
    def apply_mixins(model_class, mixins: List[type]):
        """Apply mixins to model class"""
        # Create new class with mixins
        bases = tuple(mixins) + (model_class,)
        new_class = type(model_class.__name__, bases, dict(model_class.__dict__))
        
        # Copy metadata
        new_class.__module__ = model_class.__module__
        new_class.__qualname__ = model_class.__qualname__
        
        return new_class
    
    @staticmethod
    def register_global_validators(validators: Dict[str, Callable]):
        """Register global validators"""
        for name, validator in validators.items():
            # Add to global validator registry
            pass
    
    @staticmethod
    def setup_extension_hooks():
        """Setup hooks for extension points"""
        # Model creation hooks
        # Field processing hooks
        # Query building hooks
        # Result processing hooks
        pass

# Usage example
class User(ObjectModel, TimestampMixin, SoftDeleteMixin):
    """User model with timestamp and soft delete functionality"""
    
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, validators=[validate_email()])
    
    # Mixins automatically add:
    # - created_at, updated_at (TimestampMixin)
    # - deleted_at (SoftDeleteMixin)
    # - Signal handlers for timestamp updates and soft delete
```

This extension architecture provides a flexible and powerful system for extending SQLObjects with custom functionality, validation, field types, and plugins while maintaining clean separation of concerns and backward compatibility.