# Performance Optimization Guide

## Core Concepts

- **Bulk Operations**: 10-100x faster than individual operations
- **Field Selection**: Load only needed fields to reduce data transfer
- **Relationship Loading**: Prevent N+1 queries with select_related/prefetch_related
- **Connection Pooling**: Reuse database connections efficiently
- **Query Optimization**: Skip unnecessary operations and use indexes

## Common Optimizations

### Bulk Operations

```python
# Individual creates (slow - ~10 records/second)
for user_data in users_data:
    await User.objects.create(**user_data)

# Bulk create (fast - ~1000-10000 records/second)
await User.objects.bulk_create(users_data, batch_size=1000)

# Bulk update
mappings = [
    {"id": 1, "status": "active"},
    {"id": 2, "status": "inactive"},
]
await User.objects.bulk_update(mappings, match_fields=["id"], batch_size=1000)

# Bulk delete
user_ids = list(range(1, 1001))
await User.objects.bulk_delete(user_ids, id_field="id", batch_size=1000)
```

### Field Selection

```python
# Load all fields (slow, high memory)
users = await User.objects.all()

# Load only needed fields (fast, low memory)
users = await User.objects.only("id", "username", "email").all()

# Defer heavy fields
users = await User.objects.defer("bio", "profile_image").all()

# Field-level deferred loading
class User(ObjectModel):
    bio: Column[str] = column(type="text", deferred=True)  # Lazy load
    profile_image: Column[bytes] = column(type="binary", deferred=True)
```

### Relationship Loading

```python
# N+1 query problem (slow - 1 + N queries)
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # N additional queries!

# select_related for foreign keys (fast - 1 query with JOIN)
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # No additional query

# prefetch_related for reverse relationships (fast - 2 queries)
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.fetch()  # No N+1 queries
```

### Query Optimization

```python
# Skip default ordering for count/exists (significant speedup)
count = await User.objects.skip_default_ordering().count()
exists = await User.objects.skip_default_ordering().exists()

# Use exists() instead of count() for boolean checks
has_users = await User.objects.exists()  # Fast
# Not: count = await User.objects.count(); has_users = count > 0  # Slow

# Use indexes for frequently queried fields
class User(ObjectModel):
    email: Column[str] = StringColumn(length=100)
    
    class Config:
        indexes = [index("idx_email", "email")]
```

### Connection Pooling

```python
# Production configuration
await init_db(
    "postgresql://localhost/db",
    pool_size=20,           # Base connections
    max_overflow=30,        # Burst capacity
    pool_timeout=30,        # Wait time for connection
    pool_recycle=3600,      # Recycle connections hourly
    pool_pre_ping=True      # Verify connections
)

# Reuse sessions across operations
async with ctx_session() as session:
    # All operations share the same connection
    users = await User.objects.using(session).all()
    for user in users:
        await user.posts.using(session).all()
```

## Best Practices

### ✅ Do

- **Use bulk operations** for large datasets
- **Select only needed fields** to reduce data transfer
- **Use relationship loading** to prevent N+1 queries
- **Configure connection pools** appropriately
- **Add indexes** on frequently queried fields
- **Use iterator** for large result sets

```python
# Good: Bulk operations
await User.objects.bulk_create(users_data, batch_size=1000)

# Good: Field selection
users = await User.objects.only("id", "username").all()

# Good: Relationship loading
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# Good: Connection pooling
await init_db(url, pool_size=20, max_overflow=30)

# Good: Iterator for large datasets
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
```

### ❌ Don't

- **Don't use loops** for bulk operations
- **Don't load unnecessary fields**
- **Don't cause N+1 queries**
- **Don't use tiny connection pools** in production
- **Don't forget indexes** on foreign keys

```python
# Bad: Loop instead of bulk (100x slower!)
for user_data in users_data:
    await User.objects.create(**user_data)

# Bad: Loading all fields
users = await User.objects.all()  # Loads everything

# Bad: N+1 queries
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # N queries!

# Bad: Tiny connection pool
await init_db(url, pool_size=1)  # Will bottleneck!
```

## Performance Patterns

### Batch Processing

```python
# Process large datasets in batches
last_id = 0
while True:
    users = await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(100).all()
    
    if not users:
        break
    
    await process_batch(users)
    last_id = users[-1].id
```

### Memory-Efficient Iteration

```python
# Iterator with automatic memory cleanup
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
    # Memory automatically cleaned every 10 chunks

# Configure chunk size based on database
# PostgreSQL: 1000-2000 records
# MySQL: 500-1000 records
# SQLite: 100-500 records
```

### Efficient Pagination

```python
# Cursor-based pagination (efficient for large datasets)
async def get_users_page(last_id: int = 0, page_size: int = 100):
    return await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(page_size).all()

# Keyset pagination (most efficient for ordered datasets)
async def get_users_by_date(last_created_at: datetime = None, page_size: int = 100):
    query = User.objects.order_by("-created_at")
    if last_created_at:
        query = query.filter(User.created_at < last_created_at)
    return await query.limit(page_size).all()
```

### Transaction Optimization

```python
# Keep transactions short
async with ctx_session() as session:
    # Quick database operations only
    user = await User.objects.using(session).create(username="alice")
    await Post.objects.using(session).create(title="Post", author_id=user.id)
# Transaction commits here

# Don't hold transactions during I/O
async with ctx_session() as session:
    user = await User.objects.using(session).get(User.id == 1)
# Transaction ends
await send_email(user.email)  # External I/O outside transaction
```

## Database-Specific Optimizations

### PostgreSQL

```python
# Larger batch sizes
await User.objects.bulk_create(data, batch_size=2000)

# Use RETURNING for bulk operations
# (automatically handled by SQLObjects)

# Connection pool configuration
await init_db(
    "postgresql://localhost/db",
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True
)
```

### MySQL

```python
# Medium batch sizes
await User.objects.bulk_create(data, batch_size=1000)

# Connection pool configuration
await init_db(
    "mysql://localhost/db",
    pool_size=15,
    max_overflow=25,
    pool_recycle=3600  # Important for MySQL
)
```

### SQLite

```python
# Smaller batch sizes
await User.objects.bulk_create(data, batch_size=100)

# Single connection for SQLite
await init_db(
    "sqlite:///app.db",
    pool_size=1,  # SQLite doesn't support concurrent writes
    max_overflow=0
)
```

## Performance Monitoring

### Query Performance

```python
import time

# Measure query execution time
start = time.time()
users = await User.objects.filter(User.is_active == True).all()
duration = time.time() - start
print(f"Query took {duration:.3f} seconds")

# Compare strategies
# Without select_related
start = time.time()
posts = await Post.objects.all()
for post in posts[:10]:
    author = await post.author.fetch()
time_without = time.time() - start

# With select_related
start = time.time()
posts = await Post.objects.select_related("author").all()
for post in posts[:10]:
    author = post.author
time_with = time.time() - start

print(f"Without select_related: {time_without:.3f}s")
print(f"With select_related: {time_with:.3f}s")
print(f"Speedup: {time_without / time_with:.1f}x")
```

### Memory Monitoring

```python
import psutil
import os

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

# Monitor memory during processing
memory_before = get_memory_usage()

async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

memory_after = get_memory_usage()
print(f"Memory growth: {memory_after - memory_before:.2f} MB")
```

## Optimization Checklist

### Query Optimization
- [ ] Use bulk operations for large datasets
- [ ] Select only needed fields with only()/defer()
- [ ] Use select_related for foreign keys
- [ ] Use prefetch_related for reverse relationships
- [ ] Skip default ordering for count/exists
- [ ] Add indexes on frequently queried fields

### Connection Management
- [ ] Configure appropriate connection pool size
- [ ] Set pool_recycle for long-running applications
- [ ] Enable pool_pre_ping for connection health checks
- [ ] Reuse sessions across related operations
- [ ] Close connections properly on shutdown

### Memory Management
- [ ] Use iterator for large result sets
- [ ] Configure appropriate chunk sizes
- [ ] Use cursor-based pagination
- [ ] Defer heavy fields
- [ ] Clear caches periodically

### Transaction Management
- [ ] Keep transactions short
- [ ] Don't hold transactions during I/O
- [ ] Use appropriate isolation levels
- [ ] Handle deadlocks gracefully

## Troubleshooting

### Slow Queries

**Problem**: Queries taking too long

**Solution**:
```python
# Add indexes
class User(ObjectModel):
    email: Column[str] = StringColumn(length=100)
    
    class Config:
        indexes = [index("idx_email", "email")]

# Use field selection
users = await User.objects.only("id", "username").all()

# Skip default ordering
count = await User.objects.skip_default_ordering().count()
```

### High Memory Usage

**Problem**: Application using too much memory

**Solution**:
```python
# Use iterator instead of all()
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# Defer heavy fields
users = await User.objects.defer("bio", "profile_image").all()
```

### Connection Pool Exhausted

**Problem**: `TimeoutError: QueuePool limit exceeded`

**Solution**:
```python
# Increase pool size
await init_db(url, pool_size=30, max_overflow=50)

# Use context managers to release connections
async with ctx_session() as session:
    # Connection released after block
    pass
```

### N+1 Query Problem

**Problem**: Too many database queries

**Solution**:
```python
# Use select_related for foreign keys
posts = await Post.objects.select_related("author").all()

# Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, foreign_key, relationship, Related
from sqlobjects.session import ctx_session
from sqlobjects.database import init_db
import time

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    bio: Column[str] = column(type="text", deferred=True)  # Lazy load
    posts: Related[list["Post"]] = relationship("Post", back_populates="author")
    
    class Config:
        indexes = [
            index("idx_username", "username"),
            index("idx_email", "email")
        ]

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    author: Related["User"] = relationship("User", back_populates="posts")

async def main():
    # Configure connection pool
    await init_db(
        "postgresql://localhost/db",
        pool_size=20,
        max_overflow=30,
        pool_recycle=3600,
        pool_pre_ping=True
    )
    
    # Bulk create (fast)
    users_data = [
        {"username": f"user{i}", "email": f"user{i}@example.com"}
        for i in range(1000)
    ]
    await User.objects.bulk_create(users_data, batch_size=1000)
    
    # Field selection (efficient)
    users = await User.objects.only("id", "username", "email").all()
    
    # Relationship loading (prevent N+1)
    posts = await Post.objects.select_related("author").all()
    
    # Iterator for large datasets (memory efficient)
    async for user in User.objects.iterator(chunk_size=1000):
        await process_user(user)
    
    # Optimized count
    count = await User.objects.skip_default_ordering().count()

import asyncio
asyncio.run(main())
```
