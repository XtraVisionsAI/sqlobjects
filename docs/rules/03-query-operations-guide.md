# Query Operations Guide

## Core Concepts

- **QuerySet**: Chainable query interface for building and executing queries
- **Q Objects**: Logical combinations for complex filtering
- **Field Expressions**: Type-safe field access using `Model.field` syntax
- **Aggregation**: Statistical operations using `func` expressions
- **Subqueries**: Composable query expressions for complex conditions

## Common Usage

### Basic Filtering

```python
# Simple equality
users = await User.objects.filter(User.is_active == True).all()

# Multiple conditions (AND)
users = await User.objects.filter(
    User.is_active == True,
    User.age >= 18
).all()

# Comparison operators
adults = await User.objects.filter(User.age >= 18).all()
recent = await User.objects.filter(User.created_at > datetime.now() - timedelta(days=7)).all()
```

### String Operations

```python
# Pattern matching
admins = await User.objects.filter(User.username.like("%admin%")).all()
gmail_users = await User.objects.filter(User.email.ilike("%@gmail.com")).all()  # Case-insensitive

# Starts with / ends with
users = await User.objects.filter(User.username.like("admin%")).all()
```

### Complex Filtering with Q Objects

```python
from sqlobjects.queries import Q

# OR conditions
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Complex combinations
users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.role == "admin") | Q(User.is_staff == True))
).all()

# Negation
active_users = await User.objects.filter(~Q(User.is_deleted == True)).all()
```

### Sorting and Pagination

```python
# Order by single field
users = await User.objects.order_by("username").all()
users = await User.objects.order_by("-created_at").all()  # Descending

# Order by multiple fields
users = await User.objects.order_by("department", "-created_at").all()

# Pagination
users = await User.objects.limit(10).offset(20).all()

# Skip default ordering (performance optimization)
count = await User.objects.skip_default_ordering().count()
```

### Field Selection

```python
# Load only specific fields
users = await User.objects.only("id", "username", "email").all()

# Defer heavy fields
users = await User.objects.defer("bio", "profile_image").all()

# Undefer previously deferred fields
users = await User.objects.defer("bio").undefer("bio").all()
```

### Aggregation

```python
from sqlobjects.expressions import func

# Count
total = await User.objects.count()
active_count = await User.objects.filter(User.is_active == True).count()

# Aggregate functions
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)

# Annotation (add calculated fields)
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts)
).all()
```

### Grouping

```python
# Group by with aggregation
dept_stats = await User.objects.annotate(
    user_count=func.count()
).group_by("department").all()

# Having clause (filter groups)
large_depts = await User.objects.annotate(
    user_count=func.count()
).group_by("department").having(func.count() > 10).all()
```

### Distinct

```python
# Remove duplicates
departments = await User.objects.distinct("department").all()

# Distinct on all columns
unique_users = await User.objects.distinct().all()
```

## Best Practices

### ✅ Do

- **Use field expressions** (`User.field`) for type safety
- **Chain query methods** for readability
- **Use Q objects** for complex logic
- **Skip default ordering** for count/exists operations
- **Use field selection** to reduce data transfer

```python
# Good: Type-safe and readable
users = await User.objects.filter(
    User.is_active == True,
    User.age >= 18
).order_by("-created_at").limit(10).all()

# Good: Complex logic with Q objects
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Good: Performance optimization
count = await User.objects.skip_default_ordering().count()
```

### ❌ Don't

- **Don't use string field names** in filters (use field expressions)
- **Don't forget to await** query execution
- **Don't load unnecessary fields**
- **Don't use ordering** for count operations

```python
# Bad: String field names (no type safety)
users = await User.objects.filter(is_active=True).all()  # Wrong!

# Bad: Not awaiting
users = User.objects.filter(User.is_active == True).all()  # Missing await!

# Bad: Loading all fields when only need few
users = await User.objects.all()  # Loads everything
# Good: Select only needed fields
users = await User.objects.only("id", "username").all()

# Bad: Unnecessary ordering for count
count = await User.objects.order_by("-created_at").count()  # Slow!
# Good: Skip ordering
count = await User.objects.skip_default_ordering().count()
```

## Advanced Patterns

### Subqueries

```python
# Scalar subquery (single value)
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# EXISTS subquery (boolean condition)
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# Table subquery (for JOINs)
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()
```

### Manual Joins

```python
# Inner join using Model class (recommended)
posts = await Post.objects.join(
    User,
    Post.author_id == User.id
).all()

# Left join
posts = await Post.objects.leftjoin(
    Comment,
    Post.id == Comment.post_id
).all()

# Outer join
posts = await Post.objects.outerjoin(
    Tag,
    Post.id == Tag.post_id
).all()
```

### Row Locking

```python
# Pessimistic locking (FOR UPDATE)
user = await User.objects.filter(
    User.id == 1
).select_for_update(nowait=True).first()

# Shared locking (FOR SHARE)
users = await User.objects.filter(
    User.department == "sales"
).select_for_share(skip_locked=True).all()
```

### Date/Time Extraction

```python
# Extract dates (multi-database compatible)
signup_dates = await User.objects.dates("created_at", "year")  # Returns list[date]
signup_dates = await User.objects.dates("created_at", "month")
signup_dates = await User.objects.dates("created_at", "day")

# Extract datetimes
login_times = await User.objects.datetimes("last_login", "hour")  # Returns list[datetime]
```

### Raw SQL

```python
# Execute raw SQL when needed
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age",
    {"age": 18}
)
```

## Performance Tips

### Query Optimization

```python
# Use exists() instead of count() for boolean checks
has_users = await User.objects.filter(User.is_active == True).exists()  # Fast
# Don't: count = await User.objects.filter(User.is_active == True).count(); has_users = count > 0

# Skip default ordering when not needed
count = await User.objects.skip_default_ordering().count()

# Use field selection
users = await User.objects.only("id", "username").all()  # Load only needed fields
```

### Efficient Pagination

```python
# Cursor-based pagination (efficient for large datasets)
last_id = 0
while True:
    users = await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(100).all()
    
    if not users:
        break
    
    for user in users:
        await process_user(user)
    
    last_id = users[-1].id
```

### Memory Management

```python
# Use iterator for large result sets
async for user in User.objects.filter(User.is_active == True).iterator(chunk_size=1000):
    await process_user(user)
```

## Troubleshooting

### No Results Returned

**Problem**: Query returns empty list unexpectedly

**Solution**:
```python
# Check if using correct field expressions
users = await User.objects.filter(User.is_active == True).all()  # Correct
# Not: users = await User.objects.filter(is_active=True).all()  # Wrong!

# Check if awaiting the query
users = await User.objects.all()  # Correct
# Not: users = User.objects.all()  # Returns QuerySet, not results!
```

### Type Errors in Filters

**Problem**: `TypeError: unsupported operand type(s)`

**Solution**:
```python
# Use field expressions, not strings
users = await User.objects.filter(User.age >= 18).all()  # Correct
# Not: users = await User.objects.filter("age >= 18").all()  # Wrong!
```

### Slow Count Queries

**Problem**: `count()` is slow

**Solution**:
```python
# Skip default ordering
count = await User.objects.skip_default_ordering().count()

# Use exists() for boolean checks
has_users = await User.objects.exists()  # Faster than count() > 0
```

### Q Object Errors

**Problem**: `TypeError: unsupported operand type(s) for |`

**Solution**:
```python
# Q object must be on the left side
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)  # Correct
).all()

# Not: User.role == "admin" | User.is_staff == True  # Wrong!
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.queries import Q
from sqlobjects.expressions import func
from datetime import datetime, timedelta

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn()
    department: Column[str] = StringColumn(length=50)
    is_active: Column[bool] = BooleanColumn(default=True)
    created_at: Column[datetime] = DateTimeColumn()

# Basic filtering
active_users = await User.objects.filter(User.is_active == True).all()

# Complex filtering with Q objects
admins_or_staff = await User.objects.filter(
    Q(User.department == "admin") | Q(User.department == "staff")
).all()

# Aggregation
dept_stats = await User.objects.annotate(
    user_count=func.count()
).group_by("department").all()

# Pagination with field selection
users = await User.objects.only(
    "id", "username", "email"
).order_by("-created_at").limit(10).offset(20).all()

# Subquery
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# Performance optimization
count = await User.objects.skip_default_ordering().count()
has_users = await User.objects.exists()
```
