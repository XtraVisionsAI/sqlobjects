# SQLObjects Performance Optimization Rules

## Query Performance Guidelines

### 1. Default Sorting Performance Optimization

Use `skip_default_ordering()` method to improve performance when sorting is not needed:

```python
# Skip default sorting for count operations (significant performance improvement)
count = await User.objects.skip_default_ordering().count()

# Skip default sorting when applying custom sorting
users = await User.objects.skip_default_ordering().order_by("id").all()

# Use default sorting only when needed
recent_users = await User.objects.limit(10).all()  # Uses default sorting efficiently
```

### 2. Bulk Operations Performance

Choose appropriate bulk operation methods based on data size:

```python
# Standard operations for moderate data
affected = await User.objects.filter(User.is_active == False).update(values={"status": "inactive"})
deleted = await User.objects.filter(User.is_deleted == True).delete()

# Bulk operations for large datasets (10-100x faster)
mappings = [{"id": 1, "status": "active"}, {"id": 2, "status": "inactive"}]
affected = await User.objects.bulk_update(mappings, match_fields=["id"], batch_size=1000)

user_ids = [1, 2, 3, 4, 5]  # Thousands of IDs
deleted = await User.objects.bulk_delete(user_ids, id_field="id", batch_size=1000)
```

### 3. Subquery Performance

Use appropriate subquery types for optimal performance:

```python
# Scalar subqueries for single value comparisons (most efficient)
avg_salary = Employee.objects.aggregate(avg_sal=func.avg(Employee.salary)).subquery(query_type="scalar")
high_earners = await Employee.objects.filter(Employee.salary > avg_salary).all()

# EXISTS subqueries for boolean conditions (often more efficient than IN)
has_orders = Order.objects.filter(Order.customer_id == Customer.id).subquery(query_type="exists")
active_customers = await Customer.objects.filter(has_orders).all()

# Table subqueries for complex JOINs
active_users = User.objects.filter(User.is_active == True).subquery("active")
results = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()
```

## Memory Management

### 1. Iterator for Large Datasets

Use async iterator to avoid loading large datasets into memory:

```python
# Process large datasets without memory issues
async for user in User.objects.filter(User.is_active == True).iterator():
    process_user(user)

# Custom memory cleanup interval
async for user in User.objects.iterator(memory_cleanup_interval=1000):
    process_user(user)
```

### 2. Field Selection Optimization

Load only necessary fields to reduce memory usage:

```python
# Load specific fields only
users = await User.objects.only('id', 'username', 'email').all()

# Defer heavy fields
users = await User.objects.defer('large_text_field', 'binary_data').all()
```

## Database Connection Optimization

### 1. Session Management Performance

Choose appropriate session management pattern based on use case:

```python
# Mode 1: ContextVar Inheritance - Best for unified transactions
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    await asyncio.gather(*tasks)  # Shared session, minimal overhead

# Mode 2: Independent Context - Best for fault tolerance
tasks = [
    asyncio.create_task(process_batch_isolated(batch), context=contextvars.copy_context())
    for batch in batches
]
await asyncio.gather(*tasks, return_exceptions=True)  # Isolated sessions

# Mode 3: Explicit Passing - Best for complex logic
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch_explicit(batch, session)) for batch in batches]
    await asyncio.gather(*tasks)  # Explicit control
```

### 2. Connection Pool Optimization

Configure database connections for optimal performance:

```python
from sqlobjects.database import DatabaseConfig

# Optimized database configuration
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=20,  # Adjust based on concurrent load
    max_overflow=30,  # Allow burst capacity
    pool_timeout=30,  # Connection timeout
    pool_recycle=3600,  # Recycle connections hourly
    pool_pre_ping=True,  # Verify connections
    echo=False  # Disable SQL logging in production
)
```

## Type System Performance

### 1. LRU Cache Optimization

The type system uses LRU cache for optimal lookup performance:

```python
# Type lookups are cached automatically
@lru_cache(maxsize=128)  # Configured for optimal performance
def get_type(self, name: str) -> TypeDefinition:
    # Fast cached lookup after first access
    pass

# Lazy initialization reduces startup time
if not self._initialized:
    self._init_builtin_types()  # Initialize only when needed
```

### 2. Parameter Processing Efficiency

Transform functions are applied only when needed:

```python
# Efficient parameter processing
if "transform" in arg_def and arg_def["transform"]:
    value = arg_def["transform"](value)  # Applied only when defined

# Minimal overhead for standard types
type_params = {key: value for key, value in kwargs.items() if key in type_param_names}
```

## Validation Performance

### 1. Validation Optimization

Control validation execution for performance-critical operations:

```python
# Skip validation for trusted data
user = await User.objects.create(username="john", validate=False)

# Validate specific fields only
user.validate_fields(["email", "username"])  # Partial validation

# Batch validation with error collection
collector = ValidationErrorCollector()
# ... collect errors efficiently
collector.raise_if_errors()  # Single exception for all errors
```

### 2. File Validation Performance

Optimize file validation for large files:

```python
# Efficient file validation
file_validator = FileValidator(
    allowed_extensions=["pdf", "doc"],
    max_size=10 * 1024 * 1024,  # Check size first (fastest)
    min_size=1024
)

# Image validation with size limits
image_validator = ImageValidator(
    max_size=5 * 1024 * 1024,  # Size check before image processing
    max_width=1920,
    max_height=1080
)
```

## Monitoring and Profiling

### 1. Query Analysis

Use explain functionality to analyze query performance:

```python
# Analyze query execution plan
explain_result = await User.objects.filter(User.age >= 18).explain(analyze=True)
print(explain_result)

# JSON format for programmatic analysis
explain_json = await User.objects.filter(User.age >= 18).explain(output="json")
```

### 2. Performance Metrics

Monitor key performance indicators:

```python
import time

# Measure query execution time
start_time = time.time()
users = await User.objects.filter(User.is_active == True).all()
execution_time = time.time() - start_time

# Monitor bulk operation performance
start_time = time.time()
affected = await User.objects.bulk_update(mappings, match_fields=["id"])
bulk_time = time.time() - start_time

print(f"Bulk update: {affected} rows in {bulk_time:.2f}s")
```

## Best Practices Summary

### 1. Query Optimization Checklist

- [ ] Use `skip_default_ordering()` for count operations
- [ ] Choose appropriate bulk operations for large datasets
- [ ] Select optimal subquery types (scalar/exists/table)
- [ ] Use field selection (`only()`, `defer()`) to reduce memory
- [ ] Apply async iterator for large result sets

### 2. Session Management Checklist

- [ ] Choose appropriate transaction mode for use case
- [ ] Configure connection pool based on load requirements
- [ ] Use `auto_default=True` for fault tolerance
- [ ] Avoid session leaks in long-running processes

### 3. Validation Performance Checklist

- [ ] Skip validation for trusted data when appropriate
- [ ] Use partial validation for specific fields
- [ ] Implement efficient file validation with size checks
- [ ] Collect multiple validation errors in single operation