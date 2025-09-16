# Data Operations

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/design/02-data-operations.md](../../docs-zh/design/02-data-operations.md)

This document describes the internal architecture and implementation details of SQLObjects' data operations system, including query execution, result processing, and performance optimizations.

## Query Execution Architecture

### QuerySet to SQL Pipeline

```python
# Query execution flow
QuerySet → QueryBuilder → SQLAlchemy Query → Database → Results → Objects

# Example flow
User.objects.filter(User.age >= 18).order_by("-created_at").limit(10).all()
    ↓
QueryBuilder.add_filter(User.age >= 18)
    ↓
QueryBuilder.add_ordering("-created_at")
    ↓
QueryBuilder.add_limit(10)
    ↓
SQLAlchemy select() statement
    ↓
Database execution
    ↓
Raw result rows
    ↓
Object instantiation
    ↓
List[User] objects
```

### QueryBuilder Implementation

```python
class QueryBuilder:
    """Immutable query builder for SQL construction"""
    
    def __init__(self, model_class):
        self.model_class = model_class
        self.table = model_class.__table__
        self.conditions = []
        self.orderings = []
        self.limit_value = None
        self.offset_value = None
        self.select_related_fields = []
        self.prefetch_related_fields = []
    
    def add_filter(self, condition):
        """Add WHERE condition (returns new QueryBuilder)"""
        new_builder = self._copy()
        new_builder.conditions.append(condition)
        return new_builder
    
    def add_ordering(self, field):
        """Add ORDER BY clause (returns new QueryBuilder)"""
        new_builder = self._copy()
        new_builder.orderings.append(field)
        return new_builder
    
    def build(self):
        """Build SQLAlchemy query from accumulated conditions"""
        query = select(self.table)
        
        # Apply WHERE conditions
        if self.conditions:
            query = query.where(and_(*self.conditions))
        
        # Apply ORDER BY
        if self.orderings:
            order_clauses = []
            for ordering in self.orderings:
                if ordering.startswith('-'):
                    field = getattr(self.table.c, ordering[1:])
                    order_clauses.append(field.desc())
                else:
                    field = getattr(self.table.c, ordering)
                    order_clauses.append(field.asc())
            query = query.order_by(*order_clauses)
        
        # Apply LIMIT and OFFSET
        if self.limit_value:
            query = query.limit(self.limit_value)
        if self.offset_value:
            query = query.offset(self.offset_value)
        
        return query
```

### Query Execution Engine

```python
class QueryExecutor:
    """Unified query execution interface"""
    
    def __init__(self, session, cache=None):
        self.session = session
        self.cache = cache
    
    async def execute(self, query, query_type="all", use_cache=True):
        """Execute query with caching and result processing"""
        
        # Generate cache key
        cache_key = None
        if use_cache and self.cache:
            cache_key = self._generate_cache_key(query, query_type)
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                return cached_result
        
        # Execute query
        if query_type == "all":
            result = await self._execute_all(query)
        elif query_type == "count":
            result = await self._execute_count(query)
        elif query_type == "exists":
            result = await self._execute_exists(query)
        else:
            raise ValueError(f"Unknown query type: {query_type}")
        
        # Cache result
        if use_cache and self.cache and cache_key:
            self.cache.set(cache_key, result)
        
        return result
    
    async def _execute_all(self, query):
        """Execute SELECT query and return objects"""
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [self._row_to_object(row) for row in rows]
    
    async def _execute_count(self, query):
        """Execute COUNT query"""
        count_query = select(func.count()).select_from(query.alias())
        result = await self.session.execute(count_query)
        return result.scalar()
    
    async def _execute_exists(self, query):
        """Execute EXISTS query"""
        exists_query = select(exists(query))
        result = await self.session.execute(exists_query)
        return result.scalar()
```

## Result Processing System

### Object Instantiation

```python
class ObjectInstantiator:
    """Converts database rows to model objects"""
    
    def __init__(self, model_class):
        self.model_class = model_class
        self.field_map = self._build_field_map()
    
    def _build_field_map(self):
        """Build mapping from column names to field names"""
        field_map = {}
        for field_name, field in self.model_class.__fields__.items():
            column_name = field.column.name
            field_map[column_name] = field_name
        return field_map
    
    def row_to_object(self, row):
        """Convert database row to model object"""
        # Extract field values from row
        field_values = {}
        for column_name, value in row._mapping.items():
            field_name = self.field_map.get(column_name)
            if field_name:
                field_values[field_name] = value
        
        # Create object using from_dict for proper initialization
        obj = self.model_class.from_dict(field_values)
        
        # Mark as loaded from database (not dirty)
        obj._state_manager.set("loaded_from_db", True)
        obj._state_manager.set("dirty_fields", set())
        
        return obj
```

### Relationship Loading

```python
class RelationshipLoader:
    """Handles select_related and prefetch_related loading"""
    
    def __init__(self, session):
        self.session = session
    
    async def load_select_related(self, objects, related_fields):
        """Load foreign key relationships using JOINs"""
        if not objects or not related_fields:
            return objects
        
        # Build JOIN query
        model_class = objects[0].__class__
        query = select(model_class.__table__)
        
        for field_name in related_fields:
            related_model = self._get_related_model(model_class, field_name)
            query = query.join(related_model.__table__)
        
        # Execute and populate relationships
        result = await self.session.execute(query)
        # ... populate relationship data on objects
        
        return objects
    
    async def load_prefetch_related(self, objects, related_fields):
        """Load reverse relationships using separate queries"""
        if not objects or not related_fields:
            return objects
        
        for field_name in related_fields:
            await self._prefetch_field(objects, field_name)
        
        return objects
    
    async def _prefetch_field(self, objects, field_name):
        """Prefetch single relationship field"""
        # Get primary keys of main objects
        object_ids = [obj.id for obj in objects]
        
        # Query related objects
        related_model = self._get_related_model(objects[0].__class__, field_name)
        foreign_key_field = self._get_foreign_key_field(related_model, objects[0].__class__)
        
        related_objects = await related_model.objects.filter(
            getattr(related_model, foreign_key_field).in_(object_ids)
        ).all()
        
        # Group related objects by foreign key
        related_by_id = {}
        for related_obj in related_objects:
            fk_value = getattr(related_obj, foreign_key_field)
            if fk_value not in related_by_id:
                related_by_id[fk_value] = []
            related_by_id[fk_value].append(related_obj)
        
        # Attach to main objects
        for obj in objects:
            related_list = related_by_id.get(obj.id, [])
            setattr(obj, f"_prefetched_{field_name}", related_list)
```

## Bulk Operations Implementation

### Bulk Create Architecture

```python
class BulkCreateOperation:
    """High-performance bulk insert implementation"""
    
    def __init__(self, model_class, session):
        self.model_class = model_class
        self.session = session
        self.table = model_class.__table__
    
    async def execute(self, data, batch_size=1000, return_objects=False):
        """Execute bulk create with batching"""
        if not data:
            return []
        
        created_objects = []
        
        # Process in batches
        for batch in self._batch_data(data, batch_size):
            batch_objects = await self._create_batch(batch, return_objects)
            created_objects.extend(batch_objects)
        
        return created_objects
    
    async def _create_batch(self, batch_data, return_objects):
        """Create single batch of records"""
        # Validate data
        validated_data = []
        for item in batch_data:
            if isinstance(item, dict):
                # Create object for validation
                obj = self.model_class.from_dict(item)
                obj.validate()
                validated_data.append(item)
            else:
                # Assume it's already a model instance
                item.validate()
                validated_data.append(item.to_dict())
        
        # Execute bulk insert
        if return_objects:
            # Use RETURNING clause (PostgreSQL) or fetch inserted records
            result = await self.session.execute(
                self.table.insert().returning(*self.table.c),
                validated_data
            )
            rows = result.fetchall()
            return [self._row_to_object(row) for row in rows]
        else:
            # Simple insert without returning objects
            await self.session.execute(
                self.table.insert(),
                validated_data
            )
            return []
    
    def _batch_data(self, data, batch_size):
        """Split data into batches"""
        for i in range(0, len(data), batch_size):
            yield data[i:i + batch_size]
```

### Bulk Update Architecture

```python
class BulkUpdateOperation:
    """High-performance bulk update implementation"""
    
    def __init__(self, model_class, session):
        self.model_class = model_class
        self.session = session
        self.table = model_class.__table__
    
    async def execute(self, mappings, match_fields, update_fields=None, batch_size=1000):
        """Execute bulk update with field matching"""
        if not mappings:
            return 0
        
        total_updated = 0
        
        # Process in batches
        for batch in self._batch_data(mappings, batch_size):
            updated_count = await self._update_batch(batch, match_fields, update_fields)
            total_updated += updated_count
        
        return total_updated
    
    async def _update_batch(self, batch_mappings, match_fields, update_fields):
        """Update single batch of records"""
        # Build update statement with CASE expressions
        update_stmt = self.table.update()
        
        # Build WHERE clause for matching
        match_conditions = []
        for field in match_fields:
            column = getattr(self.table.c, field)
            values = [mapping[field] for mapping in batch_mappings]
            match_conditions.append(column.in_(values))
        
        if match_conditions:
            update_stmt = update_stmt.where(and_(*match_conditions))
        
        # Build SET clause with CASE expressions
        set_values = {}
        fields_to_update = update_fields or self._get_update_fields(batch_mappings, match_fields)
        
        for field in fields_to_update:
            column = getattr(self.table.c, field)
            
            # Build CASE expression
            case_conditions = []
            for mapping in batch_mappings:
                match_condition = and_(*[
                    getattr(self.table.c, match_field) == mapping[match_field]
                    for match_field in match_fields
                ])
                case_conditions.append((match_condition, mapping[field]))
            
            set_values[column] = case(case_conditions)
        
        update_stmt = update_stmt.values(**set_values)
        
        # Execute update
        result = await self.session.execute(update_stmt)
        return result.rowcount
```

## Caching System

### Query Cache Implementation

```python
class QueryCache:
    """FIFO query result cache with performance monitoring"""
    
    def __init__(self, maxsize=1000):
        self.maxsize = maxsize
        self.cache = {}
        self.access_order = []
        self.stats = {"hits": 0, "misses": 0}
    
    def get(self, key):
        """Get cached result"""
        if key in self.cache:
            self.stats["hits"] += 1
            return self.cache[key]
        else:
            self.stats["misses"] += 1
            return None
    
    def set(self, key, value):
        """Cache query result"""
        if len(self.cache) >= self.maxsize:
            # FIFO eviction
            oldest_key = self.access_order.pop(0)
            del self.cache[oldest_key]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def get_stats(self):
        """Get cache performance statistics"""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0
        
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": hit_rate,
            "cache_size": len(self.cache)
        }
    
    def clear(self):
        """Clear all cached results"""
        self.cache.clear()
        self.access_order.clear()
        self.stats = {"hits": 0, "misses": 0}
```

### Cache Key Generation

```python
class CacheKeyGenerator:
    """Generate consistent cache keys for queries"""
    
    @staticmethod
    def generate_key(query, query_type, params=None):
        """Generate cache key from query components"""
        import hashlib
        
        # Build key components
        key_parts = [
            str(query),  # SQL query string
            query_type,  # Query type (all, count, exists)
        ]
        
        if params:
            key_parts.append(str(sorted(params.items())))
        
        # Generate hash
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
```

## Performance Optimizations

### Query Optimization Strategies

```python
class QueryOptimizer:
    """Query optimization and analysis"""
    
    @staticmethod
    def optimize_count_query(query_builder):
        """Optimize COUNT queries by removing unnecessary clauses"""
        # Remove ORDER BY for count queries (significant performance boost)
        optimized_builder = query_builder._copy()
        optimized_builder.orderings = []
        
        # Remove SELECT fields, only need COUNT
        optimized_builder.select_fields = []
        
        return optimized_builder
    
    @staticmethod
    def optimize_exists_query(query_builder):
        """Optimize EXISTS queries"""
        optimized_builder = query_builder._copy()
        
        # Remove ORDER BY and LIMIT for exists queries
        optimized_builder.orderings = []
        optimized_builder.limit_value = None
        optimized_builder.offset_value = None
        
        # Add LIMIT 1 for early termination
        optimized_builder.limit_value = 1
        
        return optimized_builder
    
    @staticmethod
    def analyze_query_performance(query, execution_time):
        """Analyze query performance and suggest optimizations"""
        suggestions = []
        
        query_str = str(query).lower()
        
        # Check for potential N+1 queries
        if "select" in query_str and "where" in query_str and "in" in query_str:
            suggestions.append("Consider using select_related or prefetch_related")
        
        # Check for missing indexes
        if execution_time > 1.0 and "where" in query_str:
            suggestions.append("Consider adding database indexes for WHERE conditions")
        
        # Check for unnecessary ordering
        if "order by" in query_str and "count" in query_str:
            suggestions.append("Remove ORDER BY from COUNT queries")
        
        return suggestions
```

### Memory Management

```python
class MemoryManager:
    """Memory-efficient result processing"""
    
    @staticmethod
    async def process_large_resultset(query_executor, query, chunk_size=1000):
        """Process large result sets in chunks"""
        offset = 0
        
        while True:
            # Build chunked query
            chunked_query = query.offset(offset).limit(chunk_size)
            
            # Execute chunk
            chunk_results = await query_executor.execute(chunked_query, "all")
            
            if not chunk_results:
                break
            
            # Yield results for processing
            for result in chunk_results:
                yield result
            
            # Cleanup chunk from memory
            del chunk_results
            
            # Move to next chunk
            offset += chunk_size
            
            # Trigger garbage collection every 10 chunks
            if offset % (chunk_size * 10) == 0:
                import gc
                gc.collect()
```

## Database Dialect Handling

### Cross-Database Compatibility

```python
class DialectHandler:
    """Handle database-specific operations"""
    
    def __init__(self, session):
        self.session = session
        self.dialect = session.bind.dialect.name
    
    def get_limit_offset_clause(self, limit, offset):
        """Generate database-specific LIMIT/OFFSET"""
        if self.dialect == "postgresql":
            return f"LIMIT {limit} OFFSET {offset}"
        elif self.dialect == "mysql":
            return f"LIMIT {offset}, {limit}"
        elif self.dialect == "sqlite":
            return f"LIMIT {limit} OFFSET {offset}"
        else:
            return f"LIMIT {limit} OFFSET {offset}"  # Standard SQL
    
    def get_date_trunc_function(self, precision, field):
        """Get database-specific date truncation function"""
        if self.dialect == "postgresql":
            return func.date_trunc(precision, field)
        elif self.dialect == "mysql":
            if precision == "day":
                return func.date(field)
            elif precision == "month":
                return func.date_format(field, "%Y-%m-01")
            elif precision == "year":
                return func.date_format(field, "%Y-01-01")
        elif self.dialect == "sqlite":
            if precision == "day":
                return func.date(field)
            elif precision == "month":
                return func.strftime("%Y-%m-01", field)
            elif precision == "year":
                return func.strftime("%Y-01-01", field)
        
        # Fallback to extract function
        return func.extract(precision, field)
    
    def supports_returning(self):
        """Check if database supports RETURNING clause"""
        return self.dialect in ["postgresql", "sqlite"]
    
    def get_bulk_insert_strategy(self):
        """Get optimal bulk insert strategy for database"""
        if self.dialect == "postgresql":
            return "copy"  # Use COPY for best performance
        elif self.dialect == "mysql":
            return "multi_insert"  # Use multi-row INSERT
        elif self.dialect == "sqlite":
            return "transaction"  # Use single transaction
        else:
            return "batch"  # Generic batching
```

This data operations architecture provides the foundation for SQLObjects' high-performance query execution, result processing, and optimization capabilities while maintaining cross-database compatibility and type safety.