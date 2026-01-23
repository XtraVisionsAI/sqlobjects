# Custom Types Examples

Examples demonstrating how to extend SQLObjects with custom database-specific field types.

## PostgreSQL Types

### [postgresql_types.py](postgresql_types.py)

Complete example showing:
- **tsvector** - Full-text search
- **pgvector** - Vector similarity search

**Features:**
- Type registration with custom comparators
- Full-text search queries
- Vector similarity operations (L2, cosine, inner product)
- Combined text + semantic search

**Requirements:**
```sql
CREATE EXTENSION pg_trgm;
CREATE EXTENSION vector;
```

**Run:**
```bash
uv run python examples/custom_types/postgresql_types.py
```

## Creating Custom Types

### 1. Define SQLAlchemy Type

```python
from sqlalchemy.types import UserDefinedType

class MyCustomType(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "CUSTOM_TYPE_NAME"
```

### 2. Create Comparator (Optional)

```python
from sqlobjects.fields.types.comparators import DefaultComparator

class MyCustomComparator(DefaultComparator):
    def custom_operation(self, value):
        return self.op('CUSTOM_OP')(value)
```

### 3. Register Type

```python
from sqlobjects.fields.types.registry import register_field_type

# Use register_field_type() to register custom types
register_field_type(MyCustomType, "mytype", comparator=MyCustomComparator)
```

### 4. Use in Models

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column

class MyModel(ObjectModel):
    custom_field: Column = column(type="mytype")
```

## See Also

- [Custom Field Types Documentation](../../docs/features/08-custom-field-types.md)
- [Model Definition](../../docs/features/02-model-definition.md)
- [Querying Data](../../docs/features/03-querying-data.md)
