# Performance Optimization

> 📝 This document is based on the Chinese version. For the latest Chinese version,
> see [docs-zh/features/07-performance-optimization.md](../../docs-zh/features/07-performance-optimization.md)

SQLObjects provides comprehensive performance optimization features including query optimization, caching, bulk
operations, and memory management strategies.

## Query Optimization

### Relationship Loading Optimization

```python
# ✅ Use select_related for foreign key relationships (JOIN)
posts = await Post.objects.select_related("author", "category").all()

# ✅ Use prefetch_related for reverse relationships (separate queries)
users = await User.objects.prefetch_related("posts", "comments").all()

# ✅ Combine strategies for optimal loading
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

# ❌ Avoid N+1 query problems
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N additional queries!
```

### Field Selection Optimization

```python
# Load only necessary fields
users = await User.objects.only("id", "username", "email").all()

# Exclude heavy fields
users = await User.objects.defer("bio", "profile_image", "large_data").all()

# Selective loading with relationships
posts = await Post.objects.select_related("author").only(
    "title", "content", "created_at",
    "author__username", "author__email"
).all()

# Defer heavy fields from related objects
posts = await Post.objects.select_related("author").defer(
    "content",           # Heavy field from main model
    "author__bio"        # Heavy field from related model
).all()
```

### Query Performance Optimization

```python
# Skip default ordering when not needed (significant performance boost)
count = await User.objects.skip_default_ordering().count()

# Use exists() instead of count() for existence checks
has_users = await User.objects.filter(User.is_active == True).exists()
# Instead of: count = await User.objects.filter(User.is_active == True).count() > 0

# Use distinct() to remove duplicates efficiently
departments = await User.objects.values("department").distinct()

# Optimize aggregation queries
stats = await User.objects.skip_default_ordering().aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age)
)
```

## Bulk Operations

### High-Performance Bulk Processing

```python
# Bulk create (10-100x faster than individual creates)
users_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"} 
    for i in range(10000)
]
await User.objects.bulk_create(users_data, batch_size=1000)

# Bulk update (much faster than individual updates)
mappings = [
    {"id": 1, "status": "active", "last_seen": datetime.now()},
    {"id": 2, "status": "inactive", "last_seen": datetime.now()},
    # ... thousands of records
]
await User.objects.bulk_update(mappings, match_fields=["id"], batch_size=1000)

# Bulk delete with ID list
user_ids = [1, 2, 3, 4, 5]  # Thousands of IDs
await User.objects.bulk_delete(user_ids, id_field="id", batch_size=1000)
```

### Batch Size Optimization

```python
# Database-specific batch size recommendations
# PostgreSQL: 1000-2000 records per batch
await User.objects.bulk_create(data, batch_size=1500)

# MySQL: 500-1000 records per batch
await User.objects.bulk_create(data, batch_size=750)

# SQLite: 100-500 records per batch
await User.objects.bulk_create(data, batch_size=250)

# Adjust based on record size and complexity
large_records = [...]  # Records with many fields
await User.objects.bulk_create(large_records, batch_size=500)

small_records = [...]  # Records with few fields
await User.objects.bulk_create(small_records, batch_size=2000)
```

## Field and Relationship Caching

### Field Metadata Caching

```python
# Field information is automatically cached at the class level
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    bio: Column[str] = StringColumn(type="text", deferred=True)
    
    # Field cache is built automatically during model creation
    # and includes categorization of regular, deferred, and relationship fields

# Access cached field information
field_cache = User._get_field_cache()
deferred_fields = field_cache.get("deferred_fields", set())
relationship_fields = field_cache.get("relationship_fields", set())
```

### Relationship Object Caching

```python
# Related objects are cached after first access
user = await User.objects.get(User.id == 1)
posts = await user.posts  # Loads and caches related posts
posts_again = await user.posts  # Returns cached posts

# Single relationship caching
post = await Post.objects.get(Post.id == 1)
author = await post.author  # Loads and caches author
author_again = await post.author  # Returns cached author
```

## Memory Management

### Iterator Pattern for Large Datasets

```python
# Memory-efficient processing of large result sets
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# Configure chunk size for optimal performance
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
    # Automatic memory cleanup every 10 chunks

# Iterator with complex filtering and ordering
async for post in Post.objects.filter(
    Post.created_at >= datetime.now() - timedelta(days=30)
).order_by("-created_at").iterator(chunk_size=500):
    await process_post(post)
```

### Memory-Efficient Pagination

```python
# Cursor-based pagination (more efficient for large datasets)
async def cursor_pagination(last_id: int = 0, page_size: int = 100):
    return await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(page_size).all()

# Keyset pagination (most efficient for ordered datasets)
async def keyset_pagination(last_created_at: datetime = None, page_size: int = 100):
    query = User.objects.order_by("-created_at")
    if last_created_at:
        query = query.filter(User.created_at < last_created_at)
    return await query.limit(page_size).all()

# Avoid offset-based pagination for large datasets
# ❌ Slow for large offsets
users = await User.objects.offset(10000).limit(100).all()

# ✅ Use cursor-based instead
users = await cursor_pagination(last_id=10000, page_size=100)
```

### Deferred Loading

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    
    # Defer heavy fields until accessed
    bio: Column[str] = StringColumn(type="text", deferred=True)
    profile_image: Column[bytes] = column(type="binary", deferred=True)
    
    class Config:
        # Group deferred fields for batch loading
        deferred_groups = {
            "profile": ["bio", "profile_image"],
            "stats": ["login_count", "last_activity"]
        }

# Usage
users = await User.objects.all()  # bio and profile_image not loaded
for user in users:
    print(user.username)  # Fast access
    if need_bio:
        bio = await user.bio  # Loaded on demand
```

## Database Connection Optimization

### Connection Pool Configuration

```python
from sqlobjects.database import init_db

# Production-optimized connection pool
await init_db(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20,           # Base connection pool size
    max_overflow=30,        # Additional connections during peak load
    pool_timeout=30,        # Max wait time for connection (seconds)
    pool_recycle=3600,      # Recycle connections every hour
    pool_pre_ping=True,     # Verify connections before use
    echo=False              # Disable SQL logging in production
)

# Development configuration
await init_db(
    "sqlite+aiosqlite:///dev.db",
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
    echo=True  # Enable SQL logging for debugging
)
```

### Session Management Optimization

```python
# Efficient session usage
async with ctx_session() as session:
    # Group related operations in single session
    user = await User.objects.using(session).create(username="alice")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    posts = await Post.objects.using(session).bulk_create([
        {"title": "Post 1", "author_id": user.id},
        {"title": "Post 2", "author_id": user.id}
    ])
    # All operations in single transaction

# Avoid session per operation
# ❌ Inefficient - multiple sessions
user = await User.objects.create(username="alice")
profile = await Profile.objects.create(user_id=user.id)
posts = await Post.objects.bulk_create([...])
```

## Database-Specific Optimizations

### PostgreSQL Optimizations

```python
# Use PostgreSQL-specific features
from sqlobjects.expressions import func

# Array operations
users = await User.objects.filter(User.tags.contains(["python"])).all()

# JSON operations
posts = await Post.objects.filter(
    Post.metadata["category"].astext == "tutorial"
).all()

# Full-text search
posts = await Post.objects.filter(
    func.to_tsvector("english", Post.content).match("python programming")
).all()

# Window functions (planned in future versions)
# users = await User.objects.annotate(
#     rank=func.row_number().over(order_by=User.created_at.desc())
# ).all()
```

### MySQL Optimizations

```python
# MySQL-specific optimizations
# Use appropriate field lengths
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)  # Not 255 for short values
    status: Column[str] = StringColumn(length=20)    # Exact length needed
    
    class Config:
        # MySQL benefits from composite indexes
        indexes = [
            index("idx_user_status_created", "status", "created_at"),
            index("idx_user_email_active", "email", "is_active")
        ]
```

### SQLite Optimizations

```python
# SQLite-specific optimizations
await init_db(
    "sqlite+aiosqlite:///app.db",
    # SQLite-specific pragmas
    connect_args={
        "pragma": {
            "journal_mode": "WAL",      # Write-Ahead Logging
            "synchronous": "NORMAL",    # Balance safety and speed
            "temp_store": "MEMORY"      # Temporary tables in memory
            "temp_store": "MEMORY"      # Temporary tables in memory
        }
    }
)
```

## Performance Monitoring

### Query Performance Analysis

```python
import time
from contextlib import asynccontextmanager

@asynccontextmanager
async def query_timer():
    """Context manager to measure query execution time"""
    start_time = time.perf_counter()
    yield
    end_time = time.perf_counter()
    print(f"Query executed in {end_time - start_time:.3f} seconds")

# Usage
async with query_timer():
    users = await User.objects.filter(User.is_active == True).all()
```

### Memory Usage Monitoring

```python
import psutil
import os

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

# Monitor memory usage during bulk operations
memory_before = get_memory_usage()
await User.objects.bulk_create(large_dataset)
memory_after = get_memory_usage()
print(f"Memory usage increased by {memory_after - memory_before:.2f}MB")
```

### Performance Benchmarking

```python
import asyncio
import time

async def benchmark_bulk_vs_individual():
    """Compare bulk operations vs individual operations"""
    data = [{"username": f"user{i}", "email": f"user{i}@example.com"} for i in range(1000)]
    
    # Individual creates
    start = time.time()
    for item in data:
        await User.objects.create(**item)
    individual_time = time.time() - start
    
    # Bulk create
    start = time.time()
    await User.objects.bulk_create(data)
    bulk_time = time.time() - start
    
    print(f"Individual creates: {individual_time:.2f}s")
    print(f"Bulk create: {bulk_time:.2f}s")
    print(f"Bulk is {individual_time / bulk_time:.1f}x faster")
```

## Performance Best Practices

### Query Optimization Checklist

```python
# ✅ Good practices
class OptimizedQueries:
    async def get_posts_with_authors(self):
        # Use select_related for foreign keys
        return await Post.objects.select_related("author").all()
    
    async def get_users_with_posts(self):
        # Use prefetch_related for reverse relationships
        return await User.objects.prefetch_related("posts").all()
    
    async def count_active_users(self):
        # Skip ordering for count operations
        return await User.objects.skip_default_ordering().filter(
            User.is_active == True
        ).count()
    
    async def check_user_exists(self, email: str):
        # Use exists() instead of count()
        return await User.objects.filter(User.email == email).exists()
    
    async def get_user_summary(self):
        # Load only necessary fields
        return await User.objects.only("id", "username", "email").all()

# ❌ Bad practices to avoid
class SlowQueries:
    async def get_posts_with_authors(self):
        # N+1 query problem
        posts = await Post.objects.all()
        for post in posts:
            author = await post.author  # Additional query for each post
        return posts
    
    async def count_active_users(self):
        # Unnecessary ordering for count
        return await User.objects.filter(User.is_active == True).count()
    
    async def check_user_exists(self, email: str):
        # Using count() instead of exists()
        count = await User.objects.filter(User.email == email).count()
        return count > 0
```

### Bulk Operation Guidelines

```python
# ✅ Efficient bulk operations
async def efficient_bulk_processing():
    # Use appropriate batch sizes
    await User.objects.bulk_create(data, batch_size=1000)
    
    # Process in chunks for memory efficiency
    for chunk in chunks(large_dataset, 1000):
        await User.objects.bulk_create(chunk)
    
    # Use bulk operations for multiple records
    await User.objects.bulk_update(mappings, match_fields=["id"])

# ❌ Inefficient patterns
async def inefficient_processing():
    # Don't use individual operations for multiple records
    for item in data:
        await User.objects.create(**item)  # Much slower
    
    # Don't use huge batch sizes
    await User.objects.bulk_create(data, batch_size=50000)  # May cause memory issues
```

### Memory Management Guidelines

```python
# ✅ Memory-efficient patterns
async def process_large_dataset():
    # Use iterator for large datasets
    async for user in User.objects.iterator(chunk_size=1000):
        await process_user(user)
    
    # Defer heavy fields
    users = await User.objects.defer("bio", "profile_image").all()
    
    # Use cursor-based pagination
    last_id = 0
    while True:
        users = await User.objects.filter(User.id > last_id).limit(100).all()
        if not users:
            break
        for user in users:
            await process_user(user)
        last_id = users[-1].id

# ❌ Memory-intensive patterns
async def memory_intensive():
    # Don't load all records at once
    all_users = await User.objects.all()  # May cause memory issues
    
    # Don't use large offsets
    page_1000 = await User.objects.offset(100000).limit(100).all()  # Slow
```

This comprehensive performance optimization guide helps you build high-performance applications with SQLObjects by
leveraging its built-in optimization features and following proven best practices.