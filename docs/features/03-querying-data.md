# Querying and Filtering Data

## Overview

SQLObjects provides a Django-style query API with support for method chaining, Q objects for complex conditions, and
powerful database operation expression support.

## Quick Start

### Basic Queries

```python
# Get all users
users = await User.objects.all()

# Filter by condition
active_users = await User.objects.filter(User.is_active == True).all()

# Get single object
user = await User.objects.get(User.username == "john")

# Check existence
exists = await User.objects.filter(User.email == "john@example.com").exists()
```

### Query Chaining

```python
# Chain multiple conditions
users = await (User.objects
    .filter(User.is_active == True)
    .filter(User.age >= 18)
    .order_by("-created_at")
    .limit(10)
    .all())
```

## Filtering

### Basic Conditions

```python
# Equality condition
users = await User.objects.filter(User.username == "john").all()

# Comparison operators
adults = await User.objects.filter(User.age >= 18).all()
recent = await User.objects.filter(User.created_at > datetime.now(timezone.utc) - timedelta(days=7)).all()

# String operations
users = await User.objects.filter(User.username.like("%admin%")).all()
users = await User.objects.filter(User.email.ilike("%GMAIL%")).all()  # Case insensitive
```

### Multi-condition Queries

```python
# AND conditions (default)
users = await User.objects.filter(
    User.is_active == True,
    User.age >= 18,
    User.email.like("%@company.com")
).all()

# Exclude conditions
users = await User.objects.exclude(User.is_deleted == True).all()
```

### Complex Logic Queries with Q Objects

```python
from sqlobjects import Q

# OR conditions
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Complex combinations
users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.role == "admin") | Q(User.is_staff == True))
).all()

# Negation conditions
users = await User.objects.filter(~Q(User.is_deleted == True)).all()
```

## Ordering and Limiting

### Ordering

```python
# Single field ordering
users = await User.objects.order_by("username").all()
users = await User.objects.order_by("-created_at").all()  # Descending

# Multi-field ordering
users = await User.objects.order_by("department", "-salary").all()

# Skip default ordering for performance
count = await User.objects.skip_default_ordering().count()
```

### Pagination

```python
# Limit and offset
users = await User.objects.limit(10).all()
users = await User.objects.offset(20).limit(10).all()

# Index and slice access
first_user = await User.objects.get_item(0)  # First user
last_user = await User.objects.get_item(-1)  # Last user
users = await User.objects.get_item(slice(0, 10))  # First 10
users = await User.objects.get_item(slice(20, 30))  # 20th-30th
```

## Field Selection

### Specify Fields

```python
# Load only specified fields
users = await User.objects.only("id", "username", "email").all()

# Exclude heavy fields
users = await User.objects.defer("large_text_field", "binary_data").all()

# Return values as dictionaries
user_data = await User.objects.values("id", "username", "email").all()
# Result: [{"id": 1, "username": "john", "email": "john@example.com"}, ...]

# Return values as tuples
usernames = await User.objects.values_list("username", flat=True).all()
# Result: ["john", "alice", "bob", ...]
```

## Aggregation

### Basic Aggregation

```python
from sqlobjects.expressions import func

# Count
user_count = await User.objects.count()
active_count = await User.objects.filter(User.is_active == True).count()

# Other aggregation functions
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)
# Result: {"total_users": 100, "avg_age": 32.5, "max_age": 65, "min_age": 18}
```

### Annotations

```python
# Add calculated fields
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at)
).all()

# Use annotations in filtering
active_posters = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

## Field Selection Control

### Field Loading Management

```python
# Load only specified fields
users = await User.objects.only("id", "username", "email").all()

# Defer loading heavy fields
live_users = await User.objects.defer("bio", "profile_image").all()

# Combine filtering and field selection
active_users = await User.objects.filter(
    User.is_active == True
).only("id", "username").all()
```

## Advanced Query Methods

### Query Building Methods

```python
# Annotate with calculated fields
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts)
).all()

# Group aggregation — per-group rows come from values mode, not aggregate()
dept_stats = await User.objects.annotate(
    dept_count=func.count(),
    avg_salary=func.avg(User.salary)
).group_by("department").having(
    func.count() > 5
).values("department", "dept_count", "avg_salary")

# Manual joins for complex queries (using Model class - recommended)
posts = await Post.objects.join(
    User, 
    Post.author_id == User.id,
    join_type="inner"
).all()

# Left joins and outer joins
posts = await Post.objects.leftjoin(
    Comment,
    Comment.post_id == Post.id
).all()

posts = await Post.objects.outerjoin(
    Tag,
    Tag.post_id == Post.id
).all()

# Row-level locking
users = await User.objects.select_for_update(
    nowait=True, 
    skip_locked=False
).filter(User.balance > 0).all()

users = await User.objects.select_for_share(
    nowait=False, 
    skip_locked=True
).filter(User.is_active == True).all()

# Extra SQL fragments
users = await User.objects.extra(
    columns={"full_name": "first_name || ' ' || last_name"},
    where=["age > %s"],
    params=[18]
).all()

# Skip default ordering for performance
count = await User.objects.skip_default_ordering().count()

# Subquery creation
avg_age = User.objects.aggregate(
    avg_age=func.avg(User.age)
).subquery(query_type="scalar")

active_users = User.objects.filter(
    User.is_active == True
).subquery("active_users")
```

### Grouping and Aggregation

Per-group aggregation uses **values mode**: declare the aggregates with
`annotate()`, group with `group_by()`, then list the grouping columns and
aggregate aliases in `values()` — each group becomes one dict. `aggregate()`
is single-row only and raises `QueryError` when combined with `group_by()`.

```python
# Grouping with having clause
dept_stats = await User.objects.annotate(
    dept_count=func.count(),
    avg_salary=func.avg(User.salary)
).group_by("department").having(
    func.count() > 5
).values("department", "dept_count", "avg_salary")
# [{"department": "sales", "dept_count": 12, "avg_salary": 52000.0}, ...]

# Complex grouping by expressions: annotate the expression with an alias so
# values() can select it alongside the aggregates
monthly_stats = await Sale.objects.annotate(
    year=func.extract("year", Sale.created_at),
    month=func.extract("month", Sale.created_at),
    total_sales=func.sum(Sale.amount),
    avg_sale=func.avg(Sale.amount)
).group_by(
    func.extract("year", Sale.created_at),
    func.extract("month", Sale.created_at)
).values("year", "month", "total_sales", "avg_sale")
```

### Manual Joins and Locking

```python
# Join types (using Model class - recommended)
# Inner join (default)
posts = await Post.objects.join(
    User,
    Post.author_id == User.id
).all()

# Left join
posts = await Post.objects.leftjoin(
    Comment,
    Comment.post_id == Post.id
).all()

# Outer join
posts = await Post.objects.outerjoin(
    Tag,
    Tag.post_id == Post.id
).all()

# Multi-table joins
posts = await Post.objects.join(
    User, Post.author_id == User.id
).leftjoin(
    Comment, Comment.post_id == Post.id
).all()

# Complex join conditions
posts = await Post.objects.join(
    User,
    and_(
        Post.author_id == User.id,
        User.is_active == True,
        User.created_at < Post.created_at
    )
).all()

# Pessimistic locking
# FOR UPDATE locking
users = await User.objects.select_for_update().filter(
    User.balance > 0
).all()

# FOR UPDATE with NOWAIT
users = await User.objects.select_for_update(nowait=True).filter(
    User.account_status == "active"
).all()

# FOR UPDATE with SKIP LOCKED
users = await User.objects.select_for_update(skip_locked=True).filter(
    User.processing_status == "pending"
).all()

# Shared locks
# FOR SHARE locking
users = await User.objects.select_for_share().filter(
    User.is_active == True
).all()

# FOR SHARE with options
users = await User.objects.select_for_share(
    nowait=True,
    skip_locked=True
).filter(User.role == "admin").all()
```

## Query Execution Methods

### Other Execution Methods

```python
# Check existence
exists = await User.objects.filter(User.email == "test@example.com").exists()

# Bulk delete matching rows. The cascade strategy controls how related rows
# are handled: "auto" (default) picks a strategy from the model's relationships
# and delete signals, "full" runs per-instance ORM cascade, "fast" does a
# minimal foreign-key cascade, and "none" issues a direct SQL delete.
deleted = await User.objects.filter(User.is_active == False).delete()
deleted = await User.objects.filter(User.is_active == False).delete(cascade="none")

# Raw SQL execution
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age",
    {"age": 18}
)

# First and last with ordering
first_user = await User.objects.order_by("created_at").first()
last_user = await User.objects.order_by("created_at").last()

# Earliest and latest by specified field
earliest = await User.objects.earliest("created_at")
latest = await User.objects.latest("updated_at")

# Earliest/latest with multiple fields
earliest = await User.objects.earliest("created_at", "id")
latest = await User.objects.latest("updated_at", "username")

# Return values as dictionaries
user_data = await User.objects.values("id", "username", "email")
# Result: [{"id": 1, "username": "john", "email": "john@example.com"}]

# Return values as tuples or flat lists
user_tuples = await User.objects.values_list("username", "email")
# Result: [("john", "john@example.com"), ("alice", "alice@example.com")]

usernames = await User.objects.values_list("username", flat=True)
# Result: ["john", "alice", "bob"]

# Date and datetime extraction
signup_years = await User.objects.dates("created_at", "year", order="DESC")
# Result: [date(2023, 1, 1), date(2022, 1, 1)]

login_hours = await User.objects.datetimes("last_login", "hour", order="ASC")
# Result: [datetime(2023, 12, 1, 10, 0), datetime(2023, 12, 1, 11, 0)]

# Index and slice access
first_user = await User.objects.get_item(0)
last_user = await User.objects.get_item(-1)
users_slice = await User.objects.get_item(slice(10, 20))

# Iterator for memory-efficient processing
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
```

### Raw SQL Queries

```python
# Execute raw SQL with parameters
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age AND department = :dept",
    {"age": 18, "dept": "engineering"}
)

# Complex raw queries
results = await User.objects.raw(
    """
    SELECT u.*, COUNT(p.id) as post_count
    FROM users u
    LEFT JOIN posts p ON u.id = p.author_id
    WHERE u.is_active = true
    GROUP BY u.id
    HAVING COUNT(p.id) > :min_posts
    """,
    {"min_posts": 5}
)
```

## Advanced Queries

### Subqueries

```python
# Scalar subqueries for single value comparisons
avg_salary = User.objects.aggregate(
    avg_salary=func.avg(User.salary)
).subquery(query_type="scalar")

high_earners = await User.objects.filter(
    User.salary > avg_salary
).all()

# Multiple scalar subqueries
max_age = User.objects.aggregate(max_age=func.max(User.age)).subquery(query_type="scalar")
min_age = User.objects.aggregate(min_age=func.min(User.age)).subquery(query_type="scalar")

users = await User.objects.filter(
    (User.age == max_age) | (User.age == min_age)
).all()

# EXISTS subqueries for boolean conditions
has_posts = Post.objects.filter(
    Post.author_id == User.id
).subquery(query_type="exists")

authors = await User.objects.filter(has_posts).all()

# Complex EXISTS conditions
has_recent_posts = Post.objects.filter(
    Post.author_id == User.id,
    Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
).subquery(query_type="exists")

active_authors = await User.objects.filter(has_recent_posts).all()

# Table subqueries for complex joins
active_users = User.objects.filter(
    User.is_active == True
).subquery("active_users")

posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()

# Complex table subqueries
top_users = User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 10
).subquery("top_users")

popular_posts = await Post.objects.join(
    top_users,
    Post.author_id == top_users.c.id
).all()
```

### Complex Aggregations

```python
# Department statistics (per-group rows → values mode)
dept_stats = await User.objects.annotate(
    user_count=func.count(),
    avg_salary=func.avg(User.salary),
    max_salary=func.max(User.salary)
).group_by("department").values("department", "user_count", "avg_salary", "max_salary")

# Conditional aggregations
stats = await User.objects.aggregate(
    total_users=func.count(),
    active_users=func.sum(func.case([(User.is_active == True, 1)], else_=0)),
    avg_age=func.avg(User.age)
)
```

### Raw SQL

```python
# Raw SQL queries - raw() is an async method that returns a list of instances
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :min_age AND created_at > :date",
    {"min_age": 18, "date": datetime.now(timezone.utc) - timedelta(days=30)}
)

# Raw expressions
users = await User.objects.annotate(
    custom_field=text("CASE WHEN age >= 18 THEN 'adult' ELSE 'minor' END")
).all()

# func.raw() calls an arbitrary SQL function by name and accepts both plain
# values and SQLAlchemy expressions (columns/other function expressions) as
# arguments, passing expressions through as SQL fragments rather than binds.
from sqlobjects.expressions import func

docs = await Document.objects.annotate(
    rank=func.raw("ts_rank", Document.content_vector, func.raw("to_tsvector", Document.body))
).order_by("-rank").all()
```

## Related Queries

### Loading Related Data

```python
# select_related (JOIN) - using string field names
users = await User.objects.select_related("profile").all()

# prefetch_related (separate queries) - using string field names
users = await User.objects.prefetch_related("posts").all()

# Multiple relationships
users = await User.objects.select_related("profile").prefetch_related("posts", "groups").all()
```

### Filter by Related Fields

```python
# Filter by related fields
users = await User.objects.filter(User.profile.bio.like("%developer%")).all()
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# Count related objects
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

## Performance Optimization

### Efficient Queries

```python
# Use exists() instead of count() for boolean checks
has_users = await User.objects.filter(User.is_active == True).exists()

# Use iterator for large datasets
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# Batch processing with a custom chunk size
async for user in User.objects.iterator(
    chunk_size=1000
):
    await process_user(user)

# Skip default ordering for count operations
count = await User.objects.skip_default_ordering().count()
```

### Window Functions

```python
from sqlobjects.expressions import func

# Row numbering
users = await User.objects.annotate(
    row_num=func.row_number().over(order_by=[User.created_at])
).all()

# Ranking within partitions
users = await User.objects.annotate(
    dept_rank=func.rank().over(
        partition_by=[User.department],
        order_by=[(User.salary, 'desc')]
    )
).all()

# Dense rank (no gaps in ranking)
users = await User.objects.annotate(
    dense_rank=func.dense_rank().over(order_by=[(User.score, 'desc')])
).all()

# LAG/LEAD for accessing adjacent rows
users = await User.objects.annotate(
    prev_salary=func.lag(User.salary, 1).over(order_by=[User.created_at]),
    next_salary=func.lead(User.salary, 1).over(order_by=[User.created_at])
).all()

# FIRST_VALUE / LAST_VALUE
users = await User.objects.annotate(
    highest_salary=func.first_value(User.salary).over(
        partition_by=[User.department],
        order_by=[(User.salary, 'desc')]
    )
).all()

# NTILE - divide rows into N buckets
users = await User.objects.annotate(
    quartile=func.ntile(4).over(order_by=[User.salary])
).all()
```

Available window functions: `row_number()`, `rank()`, `dense_rank()`, `percent_rank()`, `ntile(n)`, `lag(col, offset, default)`, `lead(col, offset, default)`, `first_value(col)`, `last_value(col)`, `nth_value(col, n)`.

### CTE (Common Table Expressions)

```python
# Basic CTE
adults = User.objects.filter(User.age >= 18).cte("adults")
result = await User.objects.with_cte(adults).filter(
    adults.c.age < 30
).all()

# Multiple CTEs
active = User.objects.filter(User.is_active == True).cte("active")
recent = User.objects.filter(
    User.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
).cte("recent")
result = await User.objects.with_cte(active, recent).all()

# Recursive CTE (e.g., organizational hierarchy)
base = Employee.objects.filter(
    Employee.manager_id.is_(None)
).cte("hierarchy", recursive=True)
recursive_part = Employee.objects.join(
    base, Employee.manager_id == base.c.id
)
hierarchy = base.union_all(recursive_part)
all_employees = await Employee.objects.with_cte(hierarchy).all()
```

### Query Analysis

Terminal query expressions (for example the one returned by `.all()`) expose an
awaitable `explain()` that returns the execution plan as a string. It accepts
`analyze` and `verbose` flags; there is no JSON/`output=` option.

```python
# Explain query execution (returns the plan as a string)
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True)
print(plan)

# Verbose plan with more detail
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True, verbose=True)
print(plan)
```

### QuerySet Shortcut Methods

ObjectsManager provides direct access to all QuerySet methods:

```python
# Distinct operations
unique_departments = await User.objects.distinct("department").all()
all_distinct = await User.objects.distinct().all()

# Exclude filtering
non_deleted = await User.objects.exclude(User.is_deleted == True).all()

# Ordering
users = await User.objects.order_by("username", "-created_at").all()

# Pagination
page_users = await User.objects.limit(10).offset(20).all()

# Field selection
users = await User.objects.only("id", "username").all()
users = await User.objects.defer("large_field").all()

# Empty queryset
empty = await User.objects.none().all()  # Always returns []

# Reverse ordering
users = await User.objects.order_by("created_at").reverse().all()

# Related loading
users = await User.objects.select_related("profile").all()
users = await User.objects.prefetch_related("posts").all()

# Advanced prefetch with custom queryset
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
    ).order_by("-created_at").limit(5)
).all()
```

## Date and Time Queries

### Date Extraction

```python
# Cross-database compatible date part extraction
users_by_year = await User.objects.dates("created_at", "year", order="DESC")
users_by_month = await User.objects.dates("created_at", "month", order="ASC")
users_by_day = await User.objects.dates("created_at", "day")

# Datetime extraction with precision levels
login_times = await User.objects.datetimes("last_login", "hour", order="ASC")
minute_logins = await User.objects.datetimes("last_login", "minute")
second_logins = await User.objects.datetimes("last_login", "second")

# Supported precision levels:
# dates(): "year", "month", "day"
# datetimes(): "year", "month", "day", "hour", "minute", "second"
```

### Date Filtering

```python
from datetime import datetime, timedelta, timezone

# Recent records
recent_users = await User.objects.filter(
    User.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
).all()

# Date ranges
this_month_users = await User.objects.filter(
    User.created_at >= datetime.now(timezone.utc).replace(day=1),
    User.created_at < datetime.now(timezone.utc).replace(day=1) + timedelta(days=32)
).all()

# Extract date parts in filtering
users_2023 = await User.objects.filter(
    func.extract("year", User.created_at) == 2023
).all()
```

## Best Practices

### Query Optimization

```python
# Use select_related for foreign keys
users = await User.objects.select_related("department").all()

# Use prefetch_related for reverse foreign keys and many-to-many relationships
users = await User.objects.prefetch_related("posts", "groups").all()

# Combine both for complex relationships
users = await User.objects.select_related("department").prefetch_related("posts").all()
```

### Error Handling

```python
from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned

try:
    user = await User.objects.get(User.username == "john")
except DoesNotExist:
    # Handle user not found
    user = None
except MultipleObjectsReturned:
    # Handle multiple users found
    user = await User.objects.filter(User.username == "john").first()
```

### Memory Management

```python
# For large result sets, use iterator
async for user in User.objects.filter(User.is_active == True).iterator():
    # Process one user at a time
    await process_user(user)

# Or use pagination
page_size = 100
offset = 0
while True:
    users = await User.objects.offset(offset).limit(page_size).all()
    if not users:
        break

    for user in users:
        await process_user(user)

    offset += page_size
```