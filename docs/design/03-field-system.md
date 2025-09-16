# Field System

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/design/03-field-system.md](../../docs-zh/design/03-field-system.md)

This document describes the internal architecture and implementation details of SQLObjects' field system, including type registry, field processing, and validation integration.

## Field System Architecture

### Core Components

```python
# Field system structure
fields/
├── core.py          # Core field classes and type registry
├── shortcuts.py     # StringColumn, IntegerColumn, etc.
├── functions.py     # column(), foreign_key(), etc.
├── types/           # Specialized field types
│   ├── base.py      # Base type classes
│   ├── registry.py  # Type registry and mapping
│   └── comparators.py # Field comparison operations
├── relations/       # Relationship field definitions
└── utils.py         # Field utilities and helpers
```

### Type Registry System

```python
from functools import lru_cache
import sqlalchemy as sa

class TypeRegistry:
    """Centralized type mapping with LRU caching"""
    
    # Core type mapping
    TYPE_MAP = {
        # Basic types
        "string": (sa.String, {"length": 255}),
        "text": (sa.Text, {}),
        "integer": (sa.Integer, {}),
        "bigint": (sa.BigInteger, {}),
        "float": (sa.Float, {}),
        "decimal": (sa.Numeric, {"precision": 10, "scale": 2}),
        "boolean": (sa.Boolean, {}),
        
        # Date and time types
        "date": (sa.Date, {}),
        "time": (sa.Time, {}),
        "datetime": (sa.DateTime, {}),
        "timestamp": (sa.TIMESTAMP, {}),
        
        # Binary and JSON types
        "binary": (sa.LargeBinary, {}),
        "json": (sa.JSON, {}),
        
        # Database-specific types
        "uuid": (sa.String, {"length": 36}),  # Generic UUID as string
        "array": (sa.ARRAY, {}),  # PostgreSQL arrays
        "enum": (sa.Enum, {}),    # Enum types
    }
    
    @classmethod
    @lru_cache(maxsize=1000)
    def get_sqlalchemy_type(cls, type_name: str, **kwargs):
        """Get SQLAlchemy type with caching"""
        if type_name not in cls.TYPE_MAP:
            raise ValueError(f"Unknown field type: {type_name}")
        
        sa_type, default_params = cls.TYPE_MAP[type_name]
        
        # Merge default parameters with provided kwargs
        params = {**default_params, **kwargs}
        
        # Create and return SQLAlchemy type instance
        return sa_type(**params)
    
    @classmethod
    def register_type(cls, type_name: str, sa_type, default_params=None):
        """Register new field type"""
        cls.TYPE_MAP[type_name] = (sa_type, default_params or {})
        
        # Clear cache to include new type
        cls.get_sqlalchemy_type.cache_clear()
    
    @classmethod
    def get_python_type_mapping(cls, python_type: type) -> str:
        """Map Python type to field type string"""
        type_mapping = {
            str: "string",
            int: "integer",
            float: "float",
            bool: "boolean",
            bytes: "binary",
            dict: "json",
            list: "json",
        }
        
        # Handle datetime types
        from datetime import datetime, date, time
        type_mapping.update({
            datetime: "datetime",
            date: "date",
            time: "time",
        })
        
        return type_mapping.get(python_type, "string")
```

### Field Base Classes

```python
from typing import TypeVar, Generic, Any, Optional, List, Callable
import sqlalchemy as sa

T = TypeVar('T')

class FieldType(Generic[T]):
    """Base class for all field types"""
    
    def __init__(
        self,
        type: str,
        nullable: bool = True,
        default: Any = None,
        default_factory: Optional[Callable] = None,
        server_default: Any = None,
        primary_key: bool = False,
        unique: bool = False,
        index: bool = False,
        validators: Optional[List[Callable]] = None,
        init: bool = True,
        repr: bool = True,
        compare: bool = True,
        hash: bool = False,
        kw_only: bool = False,
        deferred: bool = False,
        **kwargs
    ):
        self.type = type
        self.nullable = nullable
        self.default = default
        self.default_factory = default_factory
        self.server_default = server_default
        self.primary_key = primary_key
        self.unique = unique
        self.index = index
        self.validators = validators or []
        
        # Code generation parameters
        self.init = init
        self.repr = repr
        self.compare = compare
        self.hash = hash
        self.kw_only = kw_only
        
        # Performance parameters
        self.deferred = deferred
        
        # Additional SQLAlchemy parameters
        self.sa_kwargs = kwargs
        
        # Create SQLAlchemy column
        self.column = self._create_column()
    
    def _create_column(self) -> sa.Column:
        """Create SQLAlchemy column from field parameters"""
        # Get SQLAlchemy type
        sa_type = TypeRegistry.get_sqlalchemy_type(self.type, **self.sa_kwargs)
        
        # Build column parameters
        column_kwargs = {
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "unique": self.unique,
            "index": self.index,
        }
        
        # Add default values
        if self.default is not None:
            column_kwargs["default"] = self.default
        elif self.default_factory is not None:
            column_kwargs["default"] = self.default_factory
        
        if self.server_default is not None:
            column_kwargs["server_default"] = self.server_default
        
        # Store field metadata for code generation
        column_kwargs["info"] = {
            "_sqlobjects_field": self,
            "_codegen": {
                "init": self.init,
                "repr": self.repr,
                "compare": self.compare,
                "hash": self.hash,
                "kw_only": self.kw_only,
            },
            "_performance": {
                "deferred": self.deferred,
            }
        }
        
        return sa.Column(sa_type, **column_kwargs)
    
    def validate(self, value: T) -> T:
        """Validate field value using registered validators"""
        for validator in self.validators:
            value = validator(value)
        return value
    
    def __set_name__(self, owner, name):
        """Called when field is assigned to model class"""
        self.name = name
        self.column.name = name
```

### Parameter Processing Pipeline

```python
class ParameterProcessor:
    """Process and validate field parameters"""
    
    @staticmethod
    def extract_sqlalchemy_params(kwargs: dict) -> tuple[dict, dict]:
        """Separate SQLAlchemy parameters from field parameters"""
        
        # SQLAlchemy-specific parameters
        sa_params = {}
        field_params = {}
        
        # Known SQLAlchemy parameters
        sa_param_names = {
            "length", "precision", "scale", "collation", "charset",
            "autoincrement", "doc", "comment", "system", "onupdate",
            "quote", "key", "redefined", "info"
        }
        
        for key, value in kwargs.items():
            if key in sa_param_names:
                sa_params[key] = value
            else:
                field_params[key] = value
        
        return sa_params, field_params
    
    @staticmethod
    def process_init_parameter(field_type: str, **kwargs) -> bool:
        """Determine if field should participate in __init__"""
        
        # Explicit init parameter takes precedence
        if "init" in kwargs:
            return kwargs["init"]
        
        # Auto-generated fields should not be in __init__
        if kwargs.get("primary_key") and kwargs.get("autoincrement", True):
            return False
        
        # Server-generated fields should not be in __init__
        if kwargs.get("server_default") is not None:
            return False
        
        # Fields with automatic defaults might not need init
        if kwargs.get("default_factory") is not None:
            return True  # User might want to override
        
        # Default: include in __init__
        return True
    
    @staticmethod
    def validate_parameter_combinations(field_type: str, **kwargs):
        """Validate parameter combinations make sense"""
        
        # Cannot have both default and default_factory
        if kwargs.get("default") is not None and kwargs.get("default_factory") is not None:
            raise ValueError("Cannot specify both 'default' and 'default_factory'")
        
        # Primary key fields should not be nullable
        if kwargs.get("primary_key") and kwargs.get("nullable", True):
            raise ValueError("Primary key fields cannot be nullable")
        
        # Unique fields with default values might cause issues
        if kwargs.get("unique") and kwargs.get("default") is not None:
            import warnings
            warnings.warn("Unique fields with default values may cause constraint violations")
        
        # Type-specific validations
        if field_type == "string":
            if "length" not in kwargs:
                kwargs["length"] = 255  # Default string length
        
        elif field_type == "decimal":
            if "precision" not in kwargs:
                kwargs["precision"] = 10
            if "scale" not in kwargs:
                kwargs["scale"] = 2
```

### Field Shortcut Functions

```python
# Shortcut field creation functions
def StringColumn(length: int = 255, **kwargs) -> FieldType[str]:
    """Create string field with specified length"""
    return FieldType(type="string", length=length, **kwargs)

def IntegerColumn(**kwargs) -> FieldType[int]:
    """Create integer field"""
    return FieldType(type="integer", **kwargs)

def BooleanColumn(default: bool = None, **kwargs) -> FieldType[bool]:
    """Create boolean field"""
    return FieldType(type="boolean", default=default, **kwargs)

def DateTimeColumn(**kwargs) -> FieldType[datetime]:
    """Create datetime field"""
    return FieldType(type="datetime", **kwargs)

def JsonColumn(default=None, **kwargs) -> FieldType[dict]:
    """Create JSON field"""
    if default is None:
        default = dict
    return FieldType(type="json", default_factory=default, **kwargs)

# Generic column function
def column(type: str, **kwargs) -> FieldType:
    """Generic field creation function"""
    return FieldType(type=type, **kwargs)
```

### Advanced Field Types

```python
class ArrayColumn(FieldType[List[T]]):
    """PostgreSQL array field"""
    
    def __init__(self, item_type: str, dimensions: int = 1, **kwargs):
        self.item_type = item_type
        self.dimensions = dimensions
        
        # Get item SQLAlchemy type
        item_sa_type = TypeRegistry.get_sqlalchemy_type(item_type)
        
        super().__init__(
            type="array",
            item_type=item_sa_type,
            dimensions=dimensions,
            **kwargs
        )

class EnumColumn(FieldType[T]):
    """Enum field with Python enum integration"""
    
    def __init__(self, enum_class, **kwargs):
        self.enum_class = enum_class
        
        # Extract enum values
        enum_values = [item.value for item in enum_class]
        
        super().__init__(
            type="enum",
            enum_class=enum_class,
            values=enum_values,
            **kwargs
        )
    
    def validate(self, value):
        """Validate enum value"""
        if value is not None and not isinstance(value, self.enum_class):
            # Try to convert string to enum
            if isinstance(value, str):
                try:
                    value = self.enum_class(value)
                except ValueError:
                    raise ValueError(f"Invalid enum value: {value}")
            else:
                raise ValueError(f"Expected {self.enum_class.__name__}, got {type(value)}")
        
        return super().validate(value)

class UuidColumn(FieldType[str]):
    """UUID field with automatic generation"""
    
    def __init__(self, **kwargs):
        import uuid
        
        # Default to UUID4 generation
        if "default_factory" not in kwargs and "default" not in kwargs:
            kwargs["default_factory"] = lambda: str(uuid.uuid4())
        
        super().__init__(type="uuid", **kwargs)
```

### Field Comparison System

```python
class FieldComparator:
    """Provides comparison operations for fields"""
    
    def __init__(self, field: FieldType, column: sa.Column):
        self.field = field
        self.column = column
    
    def __eq__(self, other):
        """Equality comparison"""
        return self.column == other
    
    def __ne__(self, other):
        """Inequality comparison"""
        return self.column != other
    
    def __lt__(self, other):
        """Less than comparison"""
        return self.column < other
    
    def __le__(self, other):
        """Less than or equal comparison"""
        return self.column <= other
    
    def __gt__(self, other):
        """Greater than comparison"""
        return self.column > other
    
    def __ge__(self, other):
        """Greater than or equal comparison"""
        return self.column >= other
    
    def like(self, pattern: str):
        """SQL LIKE operation"""
        return self.column.like(pattern)
    
    def ilike(self, pattern: str):
        """Case-insensitive LIKE operation"""
        return self.column.ilike(pattern)
    
    def in_(self, values):
        """SQL IN operation"""
        return self.column.in_(values)
    
    def between(self, low, high):
        """SQL BETWEEN operation"""
        return self.column.between(low, high)
    
    def contains(self, value):
        """Array/JSON contains operation (PostgreSQL)"""
        if hasattr(self.column.type, 'contains'):
            return self.column.contains(value)
        else:
            raise NotImplementedError("Contains operation not supported for this field type")
    
    def startswith(self, prefix: str):
        """String starts with operation"""
        return self.column.like(f"{prefix}%")
    
    def endswith(self, suffix: str):
        """String ends with operation"""
        return self.column.like(f"%{suffix}")
```

### Field Processing in Models

```python
class FieldProcessor:
    """Process fields during model class creation"""
    
    @staticmethod
    def process_model_fields(model_class, namespace: dict):
        """Process all fields in model class"""
        fields = {}
        columns = {}
        
        # Find all field definitions
        for name, value in namespace.items():
            if isinstance(value, FieldType):
                # Process field
                field = value
                field.__set_name__(model_class, name)
                
                fields[name] = field
                columns[name] = field.column
                
                # Create field comparator for queries
                comparator = FieldComparator(field, field.column)
                setattr(model_class, name, comparator)
        
        # Store field metadata
        model_class.__fields__ = fields
        model_class.__columns__ = columns
        
        # Create SQLAlchemy table
        table_name = getattr(model_class.Config, "table_name", None)
        if not table_name:
            table_name = FieldProcessor._generate_table_name(model_class.__name__)
        
        model_class.__table__ = sa.Table(
            table_name,
            model_class.metadata,
            *columns.values(),
            **FieldProcessor._get_table_kwargs(model_class)
        )
    
    @staticmethod
    def _generate_table_name(class_name: str) -> str:
        """Generate table name from class name"""
        # Convert CamelCase to snake_case and pluralize
        import re
        
        # Insert underscores before uppercase letters
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', class_name)
        snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        
        # Simple pluralization
        if snake_case.endswith('y'):
            return snake_case[:-1] + 'ies'
        elif snake_case.endswith(('s', 'sh', 'ch', 'x', 'z')):
            return snake_case + 'es'
        else:
            return snake_case + 's'
    
    @staticmethod
    def _get_table_kwargs(model_class) -> dict:
        """Get additional table creation arguments"""
        kwargs = {}
        
        if hasattr(model_class, 'Config'):
            config = model_class.Config
            
            # Schema
            if hasattr(config, 'schema'):
                kwargs['schema'] = config.schema
            
            # Indexes
            if hasattr(config, 'indexes'):
                # Process indexes
                pass
            
            # Constraints
            if hasattr(config, 'constraints'):
                # Process constraints
                pass
        
        return kwargs
```

### Validation Integration

```python
class FieldValidator:
    """Field-level validation system"""
    
    def __init__(self, field: FieldType):
        self.field = field
    
    def validate_value(self, value, instance=None):
        """Validate single field value"""
        # Skip validation for None values if field is nullable
        if value is None and self.field.nullable:
            return value
        
        # Required field validation
        if value is None and not self.field.nullable:
            raise ValidationError(f"Field '{self.field.name}' is required")
        
        # Type validation
        value = self._validate_type(value)
        
        # Custom validators
        for validator in self.field.validators:
            value = validator(value)
        
        return value
    
    def _validate_type(self, value):
        """Validate value type matches field type"""
        if value is None:
            return value
        
        # Type-specific validation
        if self.field.type == "string":
            if not isinstance(value, str):
                value = str(value)
            
            # Length validation
            max_length = self.field.sa_kwargs.get("length")
            if max_length and len(value) > max_length:
                raise ValidationError(
                    f"String too long: {len(value)} > {max_length}"
                )
        
        elif self.field.type == "integer":
            if not isinstance(value, int):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise ValidationError(f"Invalid integer: {value}")
        
        elif self.field.type == "boolean":
            if not isinstance(value, bool):
                # Convert common boolean representations
                if isinstance(value, str):
                    if value.lower() in ("true", "1", "yes", "on"):
                        value = True
                    elif value.lower() in ("false", "0", "no", "off"):
                        value = False
                    else:
                        raise ValidationError(f"Invalid boolean: {value}")
                elif isinstance(value, int):
                    value = bool(value)
                else:
                    raise ValidationError(f"Invalid boolean: {value}")
        
        return value
```

### Field Caching and Performance

```python
class FieldCache:
    """Cache field metadata for performance"""
    
    def __init__(self):
        self._field_cache = {}
        self._type_cache = {}
    
    @lru_cache(maxsize=500)
    def get_field_info(self, model_class, field_name):
        """Get cached field information"""
        if model_class not in self._field_cache:
            self._build_field_cache(model_class)
        
        return self._field_cache[model_class].get(field_name)
    
    def _build_field_cache(self, model_class):
        """Build field cache for model class"""
        field_info = {}
        
        for name, field in model_class.__fields__.items():
            field_info[name] = {
                "type": field.type,
                "nullable": field.nullable,
                "primary_key": field.primary_key,
                "deferred": field.deferred,
                "validators": field.validators,
                "init": field.init,
                "repr": field.repr,
            }
        
        self._field_cache[model_class] = field_info
    
    def clear_cache(self):
        """Clear all cached field information"""
        self._field_cache.clear()
        self._type_cache.clear()
        TypeRegistry.get_sqlalchemy_type.cache_clear()

# Field cache is managed at the class level through FieldCacheMixin
```

This field system architecture provides the foundation for SQLObjects' type-safe, high-performance field processing with comprehensive validation and cross-database compatibility.