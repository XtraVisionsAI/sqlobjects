# Custom Field Types

## Overview

Extend SQLObjects with custom database-specific field types for specialized use cases like full-text search, vector similarity, or other database-specific features.

## Registering Custom Types

### Basic Registration

```python
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.registry import register_field_type
from sqlobjects.fields.types.comparators import DefaultComparator

# Define SQLAlchemy type
class TSVECTOR(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "TSVECTOR"

# Register to global registry
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=DefaultComparator)
```

### With Custom Operations

```python
from sqlobjects.fields.types.comparators import DefaultComparator

# Define custom comparator for type-specific operations
class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        """Full-text search match operator."""
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

# Register with custom comparator
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
```

### With Constructor Parameters

```python
class PGVECTOR(UserDefinedType):
    cache_ok = True
    
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

register_field_type(
    PGVECTOR, 
    "pgvector", 
    PGVectorComparator,
    default_params={"dimensions": 1536}
)
```

## PostgreSQL Examples

### Full-Text Search (tsvector)

**Type Definition:**
```python
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.comparators import DefaultComparator
from sqlobjects.fields.types.registry import register_field_type

class TSVECTOR(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "TSVECTOR"

class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        """Full-text search using @@ operator."""
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

# Register
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
```

**Model Usage:**
```python
from sqlalchemy import Index
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    
    class Config:
        table_name = "documents"
        indexes = [
            # GIN index for full-text search (recommended)
            Index("idx_content_vector", "content_vector", postgresql_using="gin"),
        ]
```

**Index Options:**
```python
class Config:
    indexes = [
        # GIN index (faster queries, slower updates, more space)
        Index("idx_content_gin", "content_vector", postgresql_using="gin"),
        
        # GiST index (faster updates, slower queries, less space)
        Index("idx_content_gist", "content_vector", postgresql_using="gist"),
    ]
```

**Query Examples:**
```python
# Simple full-text search
docs = await Document.objects.filter(
    Document.content_vector.match("python")
).all()

# Complex query with AND/OR
docs = await Document.objects.filter(
    Document.content_vector.match("python & programming")
).all()

# With ordering and pagination
docs = await Document.objects.filter(
    Document.content_vector.match("database | sql")
).order_by("-created_at").limit(10).all()
```

### Vector Similarity Search (pgvector)

**Type Definition:**
```python
class PGVECTOR(UserDefinedType):
    cache_ok = True
    
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):
        """L2 (Euclidean) distance: <-> operator."""
        return self.op('<->')(other)
    
    def cosine_distance(self, other):
        """Cosine distance: <=> operator."""
        return self.op('<=>')(other)
    
    def inner_product(self, other):
        """Inner product: <#> operator."""
        return self.op('<#>')(other)

# Register
register_field_type(PGVECTOR, "pgvector", comparator=PGVectorComparator)
```

**Model Usage:**
```python
from sqlalchemy import Index

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    embedding: Column = column(type="pgvector", dimensions=1536)
    
    class Config:
        table_name = "documents"
        indexes = [
            # IVFFlat index for approximate nearest neighbor search
            Index("idx_embedding", "embedding",
                  postgresql_using="ivfflat",
                  postgresql_ops={"embedding": "vector_l2_ops"}),
        ]
```

**Index Options:**
```python
class Config:
    indexes = [
        # IVFFlat with L2 distance (Euclidean)
        Index("idx_embedding_l2", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_l2_ops"}),
        
        # IVFFlat with cosine distance
        Index("idx_embedding_cosine", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        
        # IVFFlat with inner product
        Index("idx_embedding_ip", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_ip_ops"}),
        
        # HNSW index (faster queries, more memory)
        Index("idx_embedding_hnsw", "embedding",
              postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_l2_ops"}),
    ]
```

**Index Configuration:**
```python
# IVFFlat requires training - set lists parameter
# Rule of thumb: lists = rows / 1000 (for datasets > 1M rows)
async def create_ivfflat_index():
    from sqlobjects.session import get_session
    
    session = get_session(readonly=False)
    await session.execute(
        "CREATE INDEX idx_embedding ON documents "
        "USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)"
    )
    await session.commit()
```

**Query Examples:**
```python
# Find similar documents using L2 distance
query_vector = [0.1, 0.2, 0.3, ...]  # 1536 dimensions

similar_docs = await Document.objects.annotate(
    distance=Document.embedding.l2_distance(query_vector)
).order_by("distance").limit(5).all()

# Using cosine distance
similar_docs = await Document.objects.annotate(
    distance=Document.embedding.cosine_distance(query_vector)
).order_by("distance").limit(5).all()

# Filter by distance threshold
nearby_docs = await Document.objects.filter(
    Document.embedding.l2_distance(query_vector) < 0.5
).all()
```

## Complete Example

```python
# custom_types.py
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.registry import register_field_type
from sqlobjects.fields.types.comparators import DefaultComparator

# Type definitions
class TSVECTOR(UserDefinedType):
    cache_ok = True
    def get_col_spec(self, **kw):
        return "TSVECTOR"

class PGVECTOR(UserDefinedType):
    cache_ok = True
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

# Comparators
class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):
        return self.op('<->')(other)
    def cosine_distance(self, other):
        return self.op('<=>')(other)

# Register types
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
register_field_type(PGVECTOR, "pgvector", comparator=PGVectorComparator)
```

```python
# models.py
from sqlalchemy import Index
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from .custom_types import TSVECTOR, PGVECTOR  # Trigger registration

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    embedding: Column = column(type="pgvector", dimensions=1536)
    
    class Config:
        table_name = "documents"
        indexes = [
            Index("idx_content_vector", "content_vector", postgresql_using="gin"),
            Index("idx_embedding", "embedding",
                  postgresql_using="ivfflat",
                  postgresql_ops={"embedding": "vector_l2_ops"}),
        ]
```

```python
# usage.py
from sqlobjects.database import init_db, create_tables

async def main():
    # Initialize database
    await init_db("postgresql+asyncpg://user:pass@localhost/db")
    await create_tables(ObjectModel)
    
    # Full-text search
    docs = await Document.objects.filter(
        Document.content_vector.match("python & programming")
    ).all()
    
    # Vector similarity search
    query_vector = [0.1] * 1536
    similar = await Document.objects.annotate(
        distance=Document.embedding.l2_distance(query_vector)
    ).order_by("distance").limit(5).all()
    
    for doc in similar:
        print(f"{doc.title}: distance={doc.distance}")
```

## Best Practices

### 1. Type Registration Location

Register custom types before defining models:

```python
# ✅ Good: Register in separate module
# custom_types.py
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)

# models.py
from .custom_types import TSVECTOR  # Triggers registration
```

### 2. Comparator Design

Provide intuitive method names for database operations:

```python
class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):  # Clear, descriptive name
        return self.op('<->')(other)
    
    def cosine_similarity(self, other):  # User-friendly
        return 1 - self.op('<=>')(other)
```

### 3. Type Parameters

Use default parameters for common configurations:

```python
register_field_type(
    PGVECTOR,
    "pgvector",
    PGVectorComparator,
    default_params={"dimensions": 1536}  # Common OpenAI embedding size
)
```

### 4. Database Extensions

Ensure required extensions are enabled:

```python
# For PostgreSQL
async def setup_database():
    from sqlobjects.session import get_session
    
    session = get_session(readonly=False)
    await session.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    await session.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await session.commit()
```

### 5. Index Creation

Create indexes for optimal query performance:

```python
from sqlalchemy import Index

class Config:
    indexes = [
        # tsvector: Use GIN for full-text search
        Index("idx_content_vector", "content_vector", postgresql_using="gin"),
        
        # pgvector: Use IVFFlat or HNSW for similarity search
        Index("idx_embedding", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_l2_ops"}),
    ]
```

**Index Selection Guide:**

| Type | Method | Use Case | Speed | Memory |
|------|--------|----------|-------|--------|
| tsvector | GIN | Full-text search (recommended) | Fast query | High |
| tsvector | GiST | Full-text with frequent updates | Medium | Low |
| pgvector | IVFFlat | Large datasets (>100K vectors) | Fast | Medium |
| pgvector | HNSW | Highest query speed | Fastest | Highest |
| pgvector | None | Small datasets (<10K vectors) | Slow | None |

## Type Registry API

### register_field_type()

Register a custom type with the global registry:

```python
from sqlobjects.fields.types.registry import register_field_type

register_field_type(
    field_type: type,                    # SQLAlchemy type class
    type_name: str,                      # Type name for column(type="name")
    *,                                   # Keyword-only arguments below
    comparator: type | None = None,      # Comparator class (optional)
    aliases: list[str] | None = None,    # Alternative names
    default_params: dict | None = None   # Default constructor parameters
)
```

### Example with All Parameters

```python
register_field_type(
    PGVECTOR,
    "pgvector",
    comparator=PGVectorComparator,
    aliases=["vector", "embedding"],  # Can use any of these names
    default_params={"dimensions": 1536}
)

# All equivalent:
embedding1: Column = column(type="pgvector", dimensions=768)
embedding2: Column = column(type="vector", dimensions=768)
embedding3: Column = column(type="embedding", dimensions=768)
```

## Performance Considerations

### tsvector Indexes

**GIN vs GiST:**
```python
# GIN: Better for read-heavy workloads
Index("idx_gin", "content_vector", postgresql_using="gin")
# - 3x faster queries
# - 3x slower updates
# - 2-3x more disk space

# GiST: Better for write-heavy workloads  
Index("idx_gist", "content_vector", postgresql_using="gist")
# - Faster updates
# - Slower queries
# - Less disk space
```

### pgvector Indexes

**IVFFlat Configuration:**
```python
# Lists parameter affects speed/accuracy tradeoff
# More lists = faster queries, less accurate
# Fewer lists = slower queries, more accurate

# Small dataset (<100K): lists = 100
# Medium dataset (100K-1M): lists = rows / 1000  
# Large dataset (>1M): lists = sqrt(rows)

Index("idx_embedding", "embedding",
      postgresql_using="ivfflat",
      postgresql_ops={"embedding": "vector_l2_ops"})
```

**HNSW Configuration:**
```python
# HNSW provides better query performance than IVFFlat
# But requires more memory and build time

Index("idx_embedding_hnsw", "embedding",
      postgresql_using="hnsw",
      postgresql_ops={"embedding": "vector_l2_ops"},
      postgresql_with={"m": 16, "ef_construction": 64})
# m: max connections per layer (higher = better recall, more memory)
# ef_construction: build time quality (higher = better index, slower build)
```

**Distance Operator Selection:**
```python
# Choose operator based on your similarity metric
operators = {
    "vector_l2_ops": "L2 distance (Euclidean)",      # Most common
    "vector_cosine_ops": "Cosine distance",          # Normalized vectors
    "vector_ip_ops": "Inner product (negative)",     # Dot product
}
```

## See Also

- [Model Definition](02-model-definition.md) - Basic field types
- [Querying Data](03-querying-data.md) - Query building and filtering
- [Performance Optimization](07-performance-optimization.md) - Index strategies