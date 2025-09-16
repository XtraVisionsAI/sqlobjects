# Relationship and Performance Implementation Rules

## Relationship Loading Strategy Architecture

### select_related for Foreign Key Relationships
**Use JOIN operations for foreign key and one-to-one relationships**
```python
# Single relationship - both syntaxes supported
posts = await Post.objects.select_related("author").all()        # String syntax
posts = await Post.objects.select_related(Post.author).all()     # Expression syntax ✅

# Multiple relationships
posts = await Post.objects.select_related("author", "category").all()
posts = await Post.objects.select_related(Post.author, Post.category).all()  # Expression syntax ✅

# Nested relationships
comments = await Comment.objects.select_related("post__author").all()
```

### prefetch_related for Reverse Relationships
**Use separate queries for one-to-many and many-to-many relationships**
```python
# Reverse foreign key relationships - both syntaxes supported
users = await User.objects.prefetch_related("posts").all()       # String syntax
users = await User.objects.prefetch_related(User.posts).all()    # Expression syntax ✅

# Many-to-many relationships
posts = await Post.objects.prefetch_related("tags").all()
posts = await Post.objects.prefetch_related(Post.tags).all()     # Expression syntax ✅

# Multiple prefetch relationships
users = await User.objects.prefetch_related("posts", "comments", "groups").all()
users = await User.objects.prefetch_related(User.posts, User.comments, User.groups).all()  # Expression syntax ✅
```

### Combined Loading Strategies
**Optimize complex relationship queries by combining strategies**
```python
# Combine select_related and prefetch_related
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

# Access loaded relationships without additional queries
for post in posts:
    author = post.author           # From JOIN (select_related)
    tags = await post.tags.all()   # From prefetch (prefetch_related)
    comments = await post.comments.all()  # From prefetch
```

## Cache Control for Relationship Queries

### Cache Strategy for Relationship Data
**Balance between performance and data freshness**
```python
# Optimize relationship queries with field selection
users = await User.objects.select_related("department").all()

# Use field selection for dynamic relationship data
live_posts = await Post.objects.select_related("author").only("id", "title", "author__username").filter(
    Post.created_at > datetime.now() - timedelta(minutes=5)
).all()

# Cache prefetch operations for stable data
users = await User.objects.prefetch_related("roles").all()

# Optimize user-specific relationship data with field selection
user_posts = await Post.objects.defer("content").filter(
    Post.author_id == current_user.id
).prefetch_related("comments").all()
```

### Cache Performance Monitoring
**Basic cache statistics available**
```python
# Available: Field selection control
result = await queryset.only("id", "name").all()  # Load only needed fields

# Field cache information available
field_cache = Model._get_field_cache()  # Field metadata caching
```

## Performance Optimization Architecture

### skip_default_ordering() Usage Rules
**Critical performance optimization for count and aggregate operations**
```python
# Always skip default ordering for count operations
count = await User.objects.skip_default_ordering().count()

# Skip when applying custom ordering
users = await User.objects.skip_default_ordering().order_by("username").all()

# Use default ordering only when needed for display
recent_users = await User.objects.limit(10).all()  # Uses default ordering
```

### Batch Processing Strategy
**Optimize batch operations for performance and reliability**
- Configure appropriate batch sizes for different databases
- Balance memory usage with processing efficiency
- Provide configurable batch size parameters
- Plan for database-specific optimizations

```python
# Configurable batch processing
await User.objects.bulk_create(posts_data, batch_size=1000)
await User.objects.bulk_update(mappings, batch_size=1000)
await User.objects.bulk_delete(user_ids, batch_size=1000)
```

### Iterator Pattern for Large Datasets
**Memory-efficient processing of large result sets**
```python
# Basic iterator usage
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# Configure chunk size for optimal performance
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
    # Automatic memory cleanup every 10 chunks (fixed interval)

# Iterator with complex filtering and ordering
async for post in Post.objects.filter(
    Post.created_at >= datetime.now() - timedelta(days=30)
).order_by("-created_at").iterator(chunk_size=500):
    await process_post(post)

# Chunk size guidelines by database
# PostgreSQL: 1000-2000 records
# MySQL: 500-1000 records
# SQLite: 100-500 records
```

### Subquery Type Selection Strategy
**Choose appropriate subquery types for optimal performance**
```python
# Scalar subqueries - most efficient for single value comparisons
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# EXISTS subqueries - efficient for boolean conditions
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# Table subqueries - for complex JOINs and data manipulation
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()
```

## Memory Management Architecture

### Field Selection Optimization
**Minimize memory usage by loading only necessary fields**
```python
# Load only specific fields
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

### Pagination Strategy Selection
**Choose appropriate pagination method based on dataset size and usage pattern**
```python
# Offset-based pagination (simple but can be slow for large offsets)
def offset_pagination(page: int, page_size: int = 100):
    offset = (page - 1) * page_size
    return User.objects.offset(offset).limit(page_size)

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
```

### Connection Pool Configuration
**Optimize database connections for performance and resource usage**
```python
# Production-optimized connection pool settings
PRODUCTION_POOL_CONFIG = {
    "pool_size": 20,           # Base connection pool size
    "max_overflow": 30,        # Additional connections during peak load
    "pool_timeout": 30,        # Max wait time for connection (seconds)
    "pool_recycle": 3600,      # Recycle connections every hour
    "pool_pre_ping": True,     # Verify connections before use
    "echo": False              # Disable SQL logging in production
}

# Development-optimized settings
DEVELOPMENT_POOL_CONFIG = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 10,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
    "echo": True               # Enable SQL logging for debugging
}
```

## Relationship Performance Optimization Rules

### N+1 Query Prevention
**Strategies to avoid the N+1 query problem**
```python
# ❌ N+1 query problem
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N additional queries!

# ✅ Use select_related for foreign keys
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # No additional query

# ✅ Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.all()  # No additional queries
```

### Relationship Query Optimization
**Efficient querying through relationships**
```python
# Filter by related fields efficiently
posts = await Post.objects.filter(Post.author.username == "john").all()
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# Annotate with relationship data
users = await User.objects.annotate(
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at),
    avg_post_length=func.avg(func.length(User.posts.content))
).all()

# Filter by aggregated relationship data
active_authors = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

### Bulk Relationship Operations
**High-performance relationship management**
```python
# Bulk create with relationships
posts_data = [
    {"title": "Post 1", "author_id": 1, "category_id": 1},
    {"title": "Post 2", "author_id": 1, "category_id": 2},
    {"title": "Post 3", "author_id": 2, "category_id": 1},
]
posts = await Post.objects.bulk_create(posts_data, batch_size=1000)

# Bulk many-to-many associations
associations = [
    {"post_id": 1, "tag_id": 1},
    {"post_id": 1, "tag_id": 2},
    {"post_id": 2, "tag_id": 1},
]
await PostTag.objects.bulk_create(associations, batch_size=1000)
```

## Performance Optimization Guidelines

### Performance Optimization Tools
**Comprehensive performance optimization capabilities**
- Field selection and performance monitoring
- Memory-efficient data processing patterns
- Query optimization techniques
- Field selection and loading strategies

```python
# Performance optimization examples
field_cache = Model._get_field_cache()  # Performance monitoring
queryset.only("field1", "field2")      # Field selection
queryset.defer("heavy_field")          # Field deferring

# Memory-efficient processing
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# Query optimization
count = await User.objects.skip_default_ordering().count()
users = await User.objects.only("id", "username").all()
users = await User.objects.defer("bio", "image").all()
```

### Performance Best Practices
**Recommended patterns for optimal performance**
```python
# Use appropriate relationship loading
posts = await Post.objects.select_related("author").all()        # JOIN for FK
users = await User.objects.prefetch_related("posts").all()       # Separate query for reverse FK

# Optimize bulk operations
await User.objects.bulk_create(user_data, batch_size=1000)       # Bulk insert
await User.objects.bulk_update(mappings, match_fields=["id"])    # Bulk update

# Use efficient pagination
last_id = 0
while True:
    users = await User.objects.filter(User.id > last_id).order_by("id").limit(100).all()
    if not users: break
    # Process users
    last_id = users[-1].id
```

## Performance Optimization Guidelines

### Performance Issue Identification
1. **Monitoring Setup**: Implement query timing and memory monitoring
2. **Bottleneck Analysis**: Identify slow queries and memory-intensive operations
3. **Root Cause Analysis**: Determine why operations are slow or memory-intensive

### Optimization Strategy Selection
1. **Query Optimization**: Improve SQL generation and execution plans
2. **Relationship Loading**: Optimize select_related and prefetch_related usage
3. **Bulk Operations**: Replace individual operations with bulk alternatives
4. **Memory Management**: Implement iterator patterns and field selection