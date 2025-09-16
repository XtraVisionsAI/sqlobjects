# Performance Optimization

## Overview

SQLObjects provides comprehensive performance optimization features including bulk operations, query optimization, memory management, and connection pooling for high-performance database applications.

## Quick Start

### Basic Optimizations

```python
# Use bulk operations for large datasets
users_data = [{"username": f"user{i}", "email": f"user{i}@example.com"} for i in range(1000)]
await User.objects.bulk_create(users_data, batch_size=500)

# Skip default ordering when not needed
count = await User.objects.skip_default_ordering().count()

# Use select_related for foreign key relationships
posts = await Post.objects.select_related("author").all()

# Use iterator for large result sets
async for user in User.objects.iterator():
    await process_user(user)

# Control cache usage
users = await User.objects.filter(User.is_active == True).all()  # Uses cache
live_data = await User.objects.no_cache().filter(User.status == "online").all()  # Skips cache
```

## Bulk Operations

### Bulk Creation

```python
# Standard bulk create
users_data = [
    {"username": "user1", "email": "user1@example.com"},
    {"username": "user2", "email": "user2@example.com"},
    # ... thousands of records
]

# Batch processing for memory efficiency
users = await User.objects.bulk_create(users_data, batch_size=1000)

# Database-specific batch sizes
postgresql_batch = 1000  # PostgreSQL handles larger batches well
mysql_batch = 500        # MySQL prefers smaller batches
sqlite_batch = 100       # SQLite has lower limits

await User.objects.bulk_create(
    users_data, 
    batch_size=postgresql_batch if db_type == "postgresql" else mysql_batch
)
```

### Bulk Updates

```python
# Standard update (moderate performance)
affected = await User.objects.filter(
    User.is_active == False
).update(values={"status": "inactive"})

# True bulk update (10-100x faster for large datasets)
mappings = [
    {"id": 1, "status": "active", "last_seen": datetime.now()},
    {"id": 2, "status": "inactive", "last_seen": datetime.now()},
    # ... thousands of records
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["id"],
    batch_size=1000
)

# Multi-field matching
mappings = [
    {"username": "alice", "email": "alice@old.com", "new_email": "alice@new.com"},
    {"username": "bob", "email": "bob@old.com", "new_email": "bob@new.com"}
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["username", "email"]
)
```

### Bulk Deletion

```python
# Standard deletion with conditions
deleted = await User.objects.filter(
    User.is_active == False,
    User.last_login < datetime.now() - timedelta(days=365)
).delete()

# True bulk delete (10-100x faster for large ID lists)
user_ids = [1, 2, 3, 4, 5]  # Thousands of IDs
deleted = await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000
)

# Bulk delete with custom field
usernames = ["inactive_user1", "inactive_user2", "inactive_user3"]
deleted = await User.objects.bulk_delete(
    usernames,
    id_field="username",
    batch_size=500
)
```

## Cache Control

### Query Cache Management

```python
# Default behavior uses cache for read operations
users = await User.objects.filter(User.is_active == True).all()

# Force skip cache for real-time data
live_users = await User.objects.no_cache().filter(
    User.last_login > datetime.now() - timedelta(minutes=1)
).all()

# Query cache statistics
stats = User.objects.get_cache_stats()
print(f"Query cache hit rate: {stats['hit_rate']:.2%}")
print(f"Cache hits: {stats['hits']}, misses: {stats['misses']}")

# Clear query cache
User.objects.clear_cache()  # Clear query cache

# Cache performance optimization
if stats["hit_rate"] < 0.5:
    # Low hit rate - consider query optimization
    # or cache size adjustment
    pass
```

### Cache Strategy Guidelines

```python
# Use cache for:
# - Frequently accessed reference data
active_users = await User.objects.filter(User.is_active == True).all()

# - Expensive aggregation queries
user_stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age)
)

# Skip cache for:
# - Real-time data requirements
current_sessions = await Session.objects.no_cache().filter(
    Session.expires_at > datetime.now()
).all()

# - One-time queries
report_data = await User.objects.no_cache().filter(
    User.created_at >= report_start_date
).all()
```

## Query Optimization

### Default Ordering Control

```python
# Skip default ordering for count operations (significant performance boost)
count = await User.objects.skip_default_ordering().count()

# Skip when applying custom ordering
users = await User.objects.skip_default_ordering().order_by("username").all()

# Use default ordering only when needed
recent_users = await User.objects.limit(10).all()  # Uses default ordering
```

### Relationship Loading

```python
# Efficient relationship loading
# Use select_related for foreign keys (JOIN)
posts = await Post.objects.select_related("author", "category").all()

# Use prefetch_related for reverse relationships (separate queries)
users = await User.objects.prefetch_related("posts", "comments").all()

# Advanced prefetch with custom QuerySets (concurrent execution)
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at').limit(10),
    popular_posts=Post.objects.filter(Post.view_count > 1000)
                             .order_by('-view_count')
                             .limit(5)
).all()  # All prefetch queries execute concurrently

# Combine both strategies
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# Expression syntax (recommended)
posts = await Post.objects.select_related(Post.author).prefetch_related(Post.tags).all()
```

### Field Selection

```python
# Load only necessary fields
users = await User.objects.only("id", "username", "email").all()

# Exclude heavy fields
users = await User.objects.defer("bio", "profile_image").all()

# Selective loading with relationships
posts = await Post.objects.select_related("author").only(
    "title", "content", "author__username"
).all()
```

### Subquery Optimization

```python
# Use appropriate subquery types
# Scalar subqueries for single value comparisons (most efficient)
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# EXISTS subqueries for boolean conditions (often more efficient than IN)
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# Table subqueries for complex JOINs
active_users = User.objects.filter(User.is_active == True).subquery("active")
posts = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()
```

## Memory Management

### Iterator for Large Datasets

```python
# Process large datasets without loading everything into memory
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# Custom chunk size and memory cleanup
async for user in User.objects.iterator(
    chunk_size=1000,
    memory_cleanup_interval=10  # Cleanup every 10 chunks
):
    await process_user(user)

# Iterator with filtering and ordering
async for post in Post.objects.filter(
    Post.created_at >= datetime.now() - timedelta(days=30)
).order_by("-created_at").iterator():
    await process_post(post)

# Memory-efficient batch processing
async def process_large_dataset():
    processed_count = 0
    
    async for record in LargeTable.objects.iterator(chunk_size=1000):
        await process_record(record)
        processed_count += 1
        
        # Progress reporting
        if processed_count % 10000 == 0:
            print(f"Processed {processed_count} records")
```

### Pagination Strategies

```python
# Offset-based pagination (simple but can be slow for large offsets)
page_size = 100
offset = 0

while True:
    users = await User.objects.offset(offset).limit(page_size).all()
    if not users:
        break
    
    for user in users:
        await process_user(user)
    
    offset += page_size

# Cursor-based pagination (more efficient for large datasets)
last_id = 0
page_size = 100

while True:
    users = await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(page_size).all()
    
    if not users:
        break
    
    for user in users:
        await process_user(user)
    
    last_id = users[-1].id
```

### Slice Access

```python
# Efficient slice access
first_10 = await User.objects.get_item(slice(0, 10))
next_10 = await User.objects.get_item(slice(10, 20))

# Single item access
first_user = await User.objects.get_item(0)
fifth_user = await User.objects.get_item(4)
```

## Database Connection Optimization

### Connection Pool Configuration

```python
from sqlobjects.database import DatabaseConfig

# Optimized connection pool settings
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=20,           # Base connection pool size
    max_overflow=30,        # Additional connections during peak load
    pool_timeout=30,        # Max wait time for connection
    pool_recycle=3600,      # Recycle connections every hour
    pool_pre_ping=True,     # Verify connections before use
    echo=False              # Disable SQL logging in production
)

db = await init_db(config.url, **config.engine_kwargs)
```

### Session Management Patterns

```python
# Choose appropriate session pattern for your use case

# Pattern 1: ContextVar Inheritance (best for unified transactions)
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    await asyncio.gather(*tasks)  # All tasks share same session

# Pattern 2: Independent Context (best for fault tolerance)
tasks = [
    asyncio.create_task(process_batch(batch), context=contextvars.copy_context())
    for batch in batches
]
await asyncio.gather(*tasks, return_exceptions=True)

# Pattern 3: Explicit Passing (best for complex logic)
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch, session)) for batch in batches]
    await asyncio.gather(*tasks)
```

### Connection Lifecycle Management

```python
# Graceful shutdown with automatic failover
await close_db("primary", auto_default=True)  # Automatically switch to backup

# Health checks
async def check_database_health():
    try:
        count = await User.objects.count()
        return {"status": "healthy", "user_count": count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## Advanced Optimization Techniques

### Query Analysis

```python
# Analyze query performance
explain_result = await User.objects.filter(User.age >= 18).explain(analyze=True)
print(explain_result)

# JSON format for programmatic analysis
explain_json = await User.objects.filter(User.age >= 18).explain(output="json")

# Identify slow queries
import time

start_time = time.time()
users = await User.objects.filter(User.is_active == True).all()
execution_time = time.time() - start_time

if execution_time > 1.0:  # Log slow queries
    logger.warning(f"Slow query detected: {execution_time:.2f}s")
```

### Database Function Usage

```python
from sqlobjects.expressions import func

# Use database functions for calculations (more efficient than Python)
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    age_years=func.extract("year", func.age(User.birth_date))
).all()

# Aggregations in database
stats = await Order.objects.aggregate(
    total_amount=func.sum(Order.amount),
    avg_amount=func.avg(Order.amount),
    order_count=func.count(),
    max_order_date=func.max(Order.created_at)
)
```

### Batch Processing Patterns

```python
# Efficient batch processing
async def process_users_in_batches(batch_size=1000):
    offset = 0
    
    while True:
        # Process batch
        users = await User.objects.offset(offset).limit(batch_size).all()
        if not users:
            break
        
        # Batch operations
        updates = []
        for user in users:
            # Process user
            processed_data = await process_user_data(user)
            updates.append({"id": user.id, **processed_data})
        
        # Bulk update results
        if updates:
            await User.objects.bulk_update(updates, match_fields=["id"])
        
        offset += batch_size

# Parallel batch processing
async def parallel_batch_processing(user_ids: list[int], batch_size=100):
    batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]
    
    async def process_batch(batch_ids):
        users = await User.objects.filter(User.id.in_(batch_ids)).all()
        # Process users in batch
        return await process_user_batch(users)
    
    # Process batches in parallel
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results
```

## Performance Monitoring

### Metrics Collection

```python
import time
from collections import defaultdict

class QueryMetrics:
    def __init__(self):
        self.query_times = defaultdict(list)
        self.query_counts = defaultdict(int)
    
    async def time_query(self, query_name, query_func):
        start_time = time.time()
        try:
            result = await query_func()
            execution_time = time.time() - start_time
            
            self.query_times[query_name].append(execution_time)
            self.query_counts[query_name] += 1
            
            if execution_time > 1.0:
                logger.warning(f"Slow query {query_name}: {execution_time:.2f}s")
            
            return result
        except Exception as e:
            logger.error(f"Query {query_name} failed: {e}")
            raise

# Usage
metrics = QueryMetrics()

users = await metrics.time_query(
    "get_active_users",
    lambda: User.objects.filter(User.is_active == True).all()
)
```

### Performance Benchmarking

```python
async def benchmark_bulk_operations():
    # Test data
    test_data = [
        {"username": f"user{i}", "email": f"user{i}@test.com"}
        for i in range(10000)
    ]
    
    # Benchmark bulk create
    start_time = time.time()
    await User.objects.bulk_create(test_data, batch_size=1000)
    bulk_create_time = time.time() - start_time
    
    # Benchmark individual creates
    start_time = time.time()
    for data in test_data[:100]:  # Test smaller sample
        await User.objects.create(**data)
    individual_create_time = (time.time() - start_time) * 100  # Scale up
    
    print(f"Bulk create: {bulk_create_time:.2f}s")
    print(f"Individual create (estimated): {individual_create_time:.2f}s")
    print(f"Performance improvement: {individual_create_time / bulk_create_time:.1f}x")
```

## Best Practices

### Query Optimization Checklist

```python
# ✅ Use appropriate loading strategies
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# ✅ Use advanced prefetch for filtered relationships
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at')
).all()

# ✅ Skip default ordering when not needed
count = await User.objects.skip_default_ordering().count()

# ✅ Use bulk operations for large datasets
await User.objects.bulk_update(mappings, match_fields=["id"])

# ✅ Use iterator for large result sets
async for user in User.objects.iterator():
    process_user(user)

# ✅ Select only needed fields
users = await User.objects.only("id", "username").all()

# ❌ Avoid N+1 queries
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N additional queries!
```

### Memory Management Checklist

```python
# ✅ Use iterator for large datasets
async for record in Model.objects.iterator():
    process_record(record)

# ✅ Use pagination for large result sets
users = await User.objects.offset(0).limit(100).all()

# ✅ Define deferred fields at field level
class User(ObjectModel):
    username: Column[str] = column(type="string", length=50)
    bio: Column[str] = column(type="text", deferred=True)  # Deferred by default
    profile_image: Column[bytes] = column(
        type="binary", 
        deferred=True, 
        deferred_group="media"  # Group related deferred fields
    )
    
    # Active history tracking for important fields
    important_field: Column[str] = column(
        type="string",
        active_history=True  # Track field value changes
    )

# ✅ Use defer() for additional fields not marked as deferred
users = await User.objects.defer("additional_field").all()

# ❌ Avoid loading everything into memory
all_users = await User.objects.all()  # Could be millions of records!

# ✅ Use deferred fields for large data
class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(
        type="text", 
        deferred=True  # Don't load by default
    )
    
# ✅ Use active history for change tracking
class AuditableModel(ObjectModel):
    sensitive_field: Column[str] = column(
        type="string",
        active_history=True  # Track all changes to this field
    )
```

### Connection Pool Optimization

```python
# ✅ Configure appropriate pool sizes
config = DatabaseConfig(
    database_url,
    pool_size=10,      # Base connections
    max_overflow=20,   # Burst capacity
    pool_recycle=3600  # Refresh connections
)

# ✅ Use session context managers
async with ctx_session() as session:
    # Operations within transaction
    pass

# ✅ Handle connection errors gracefully
try:
    result = await User.objects.count()
except DatabaseError:
    # Fallback or retry logic
    pass
```

### Performance Testing

```python
# Load testing example
async def load_test_queries(concurrent_users=10, queries_per_user=100):
    async def user_simulation():
        for _ in range(queries_per_user):
            # Simulate user queries
            users = await User.objects.filter(User.is_active == True).limit(10).all()
            await asyncio.sleep(0.1)  # Simulate processing time
    
    # Run concurrent simulations
    tasks = [asyncio.create_task(user_simulation()) for _ in range(concurrent_users)]
    
    start_time = time.time()
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    total_queries = concurrent_users * queries_per_user
    qps = total_queries / total_time
    
    print(f"Processed {total_queries} queries in {total_time:.2f}s")
    print(f"Queries per second: {qps:.1f}")
```