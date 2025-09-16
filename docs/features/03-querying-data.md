# Querying Data

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/03-querying-data.md](../../docs-zh/features/03-querying-data.md)

SQLObjects provides a powerful and intuitive query system with Django-style API, chainable methods, and comprehensive filtering capabilities.

## Basic Queries

### Simple Filtering

```python
# Get all active users
active_users = await User.objects.filter(User.is_active == True).all()

# Get users by username
user = await User.objects.filter(User.username == "alice").first()

# Multiple conditions (AND)
adult_users = await User.objects.filter(
    User.age >= 18,
    User.is_active == True
).all()
```

### Field Lookups

```python
# String operations
users = await User.objects.filter(User.username.like("%admin%")).all()
users = await User.objects.filter(User.email.ilike("%GMAIL%")).all()  # Case insensitive

# Numeric comparisons
adults = await User.objects.filter(User.age >= 18).all()
seniors = await User.objects.filter(User.age.between(65, 120)).all()

# Date operations
from datetime import datetime, timedelta
recent_users = await User.objects.filter(
    User.created_at > datetime.now() - timedelta(days=7)
).all()

# List operations
user_ids = [1, 2, 3, 4, 5]
users = await User.objects.filter(User.id.in_(user_ids)).all()
```

### Q Objects for Complex Logic

```python
from sqlobjects.queries import Q

# OR conditions
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Complex combinations with proper precedence
users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.role == "admin") | Q(User.is_staff == True))
).all()

# Negation
active_users = await User.objects.filter(~Q(User.is_deleted == True)).all()

# Nested Q objects
complex_filter = Q(
    Q(User.age >= 18) & Q(User.is_verified == True)
) | Q(User.role == "admin")
users = await User.objects.filter(complex_filter).all()
```

## Query Methods

### Execution Methods

```python
# Get all results
users = await User.objects.filter(User.is_active == True).all()

# Get single result
user = await User.objects.filter(User.username == "alice").get()

# Get first result or None
user = await User.objects.filter(User.age >= 18).first()

# Get last result
user = await User.objects.filter(User.is_active == True).last()

# Check existence
exists = await User.objects.filter(User.email == "test@example.com").exists()

# Count results
count = await User.objects.filter(User.is_active == True).count()
```

### Ordering and Limiting

```python
# Order by single field
users = await User.objects.order_by("username").all()
users = await User.objects.order_by("-created_at").all()  # Descending

# Order by multiple fields
users = await User.objects.order_by("age", "-created_at").all()

# Limit and offset
users = await User.objects.limit(10).all()
users = await User.objects.offset(20).limit(10).all()

# Pagination helper
page_2_users = await User.objects.offset(10).limit(10).all()
```

### Field Selection

```python
# Select specific fields only
users = await User.objects.only("id", "username", "email").all()

# Exclude heavy fields
users = await User.objects.defer("bio", "profile_image").all()

# Values as dictionaries
user_data = await User.objects.values("id", "username", "email")

# Values as flat list
usernames = await User.objects.values_list("username", flat=True)
```

## Advanced Querying

### Aggregation

```python
from sqlobjects.expressions import func

# Simple aggregations
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)

# Aggregation with filtering
adult_stats = await User.objects.filter(
    User.age >= 18
).aggregate(
    adult_count=func.count(),
    avg_adult_age=func.avg(User.age)
)
```

### Annotation

```python
# Add calculated fields
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at)
).all()

# Use annotations in filtering
active_authors = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(User.post_count > 5).all()
```

### Grouping

```python
# Group by field
department_stats = await User.objects.values("department").annotate(
    employee_count=func.count(),
    avg_salary=func.avg(User.salary)
).all()

# Group by multiple fields
stats = await User.objects.values("department", "role").annotate(
    count=func.count(),
    avg_age=func.avg(User.age)
).all()

# Having clause for group filtering
large_departments = await User.objects.values("department").annotate(
    employee_count=func.count()
).having(func.count() > 10).all()
```

### Distinct

```python
# Remove duplicates
departments = await User.objects.values("department").distinct()

# Distinct on specific fields (PostgreSQL)
users = await User.objects.distinct("department").all()
```

## Subqueries

### Scalar Subqueries

```python
# Use subquery result in comparison
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# Subquery in annotation
users = await User.objects.annotate(
    age_vs_avg=User.age - avg_age
).all()
```

### EXISTS Subqueries

```python
# Filter by related record existence
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# Complex EXISTS conditions
has_recent_posts = Post.objects.filter(
    Post.author_id == User.id,
    Post.created_at > datetime.now() - timedelta(days=30)
).subquery(query_type="exists")
active_authors = await User.objects.filter(has_recent_posts).all()
```

### Table Subqueries

```python
# Use subquery as table
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()
```

## Relationship Queries

### Filtering by Related Fields

```python
# Filter by foreign key relationship
posts = await Post.objects.filter(Post.author.username == "alice").all()

# Filter by reverse relationship
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# Multiple relationship levels
comments = await Comment.objects.filter(
    Comment.post.author.username == "alice"
).all()
```

### Relationship Loading

```python
# Select related (JOIN for foreign keys)
posts = await Post.objects.select_related("author", "category").all()

# Prefetch related (separate queries for reverse relationships)
users = await User.objects.prefetch_related("posts", "comments").all()

# Combined loading strategies
posts = await Post.objects.select_related("author").prefetch_related(
    "comments", "tags"
).all()

# Access loaded relationships without additional queries
for post in posts:
    author = post.author           # From JOIN (select_related)
    comments = await post.comments.all()  # From prefetch (prefetch_related)
```

## Raw SQL

### Raw Queries

```python
# Execute raw SQL
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age AND created_at > :date",
    {"age": 18, "date": datetime.now() - timedelta(days=30)}
)

# Raw SQL with model instantiation
users = await User.objects.raw(
    "SELECT id, username, email FROM users WHERE is_active = true"
)
```

### Extra Clauses

```python
# Add custom SELECT clauses
users = await User.objects.extra(
    select={"age_group": "CASE WHEN age < 18 THEN 'minor' ELSE 'adult' END"}
).all()

# Custom WHERE clauses
users = await User.objects.extra(
    where=["age > %s", "created_at > %s"],
    params=[18, datetime.now() - timedelta(days=30)]
).all()
```

## Performance Optimization

### Query Optimization

```python
# Skip default ordering when not needed
count = await User.objects.skip_default_ordering().count()

# Use select_related for foreign key relationships
posts = await Post.objects.select_related("author").all()

# Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()

# Combine for optimal loading
posts = await Post.objects.select_related("author").prefetch_related("tags").all()
```

### Field Selection Control

```python
# Load only specific fields
users = await User.objects.only("id", "username", "email").all()

# Defer heavy fields until accessed
users = await User.objects.defer("bio", "profile_image").all()

# Combine with filtering
live_users = await User.objects.filter(
    User.status == "online"
).only("id", "username").all()
```

### Iterator for Large Datasets

```python
# Memory-efficient processing
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# Configure chunk size
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
```

## Date and Time Queries

### Date Extraction

```python
# Extract date parts (cross-database compatible)
years = await User.objects.dates("created_at", "year")
months = await User.objects.dates("created_at", "month")

# DateTime extraction
hours = await User.objects.datetimes("last_login", "hour")
```

### Date Filtering

```python
from datetime import date, datetime

# Date comparisons
today_users = await User.objects.filter(
    User.created_at >= datetime.combine(date.today(), datetime.min.time())
).all()

# Date ranges
this_month_users = await User.objects.filter(
    User.created_at__year=2024,
    User.created_at__month=1
).all()
```

## Query Chaining

### Method Chaining

```python
# Build complex queries step by step
query = User.objects.filter(User.is_active == True)
query = query.filter(User.age >= 18)
query = query.order_by("-created_at")
query = query.limit(10)

users = await query.all()

# Or chain directly
users = await User.objects.filter(
    User.is_active == True
).filter(
    User.age >= 18
).order_by("-created_at").limit(10).all()
```

### Conditional Chaining

```python
def build_user_query(is_admin=False, min_age=None, search_term=None):
    query = User.objects.filter(User.is_active == True)
    
    if is_admin:
        query = query.filter(User.role == "admin")
    
    if min_age:
        query = query.filter(User.age >= min_age)
    
    if search_term:
        query = query.filter(
            Q(User.username.like(f"%{search_term}%")) |
            Q(User.email.like(f"%{search_term}%"))
        )
    
    return query

# Usage
admin_users = await build_user_query(is_admin=True, min_age=21).all()
```

## Best Practices

### Query Performance

1. **Use select_related for foreign keys**: Avoid N+1 queries
2. **Use prefetch_related for reverse relationships**: Optimize related data loading
3. **Skip default ordering for counts**: Use `skip_default_ordering()` for better performance
4. **Use only() and defer()**: Load only necessary fields
5. **Use iterator for large datasets**: Avoid memory issues with large result sets

### Query Organization

```python
# Create reusable query methods
class UserQuerySet:
    def active(self):
        return self.filter(User.is_active == True)
    
    def adults(self):
        return self.filter(User.age >= 18)
    
    def by_role(self, role):
        return self.filter(User.role == role)

# Usage
active_adult_admins = await User.objects.active().adults().by_role("admin").all()
```

### Error Handling

```python
from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned

try:
    user = await User.objects.filter(User.username == "alice").get()
except DoesNotExist:
    print("User not found")
except MultipleObjectsReturned:
    print("Multiple users found")

# Safe get with default
user = await User.objects.filter(User.username == "alice").first()
if user is None:
    print("User not found")
```