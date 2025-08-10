# SQLObjects Advanced Features

## Subquery System Rules

### 1. Intelligent Subquery Creation

SQLObjects provides an intelligent subquery system with automatic type inference:

```python
from sqlobjects.expressions import SubqueryExpression

# Automatic type inference (recommended)
subq = User.objects.filter(is_active=True).subquery()  # Auto-inferred type

# Explicit type specification
table_subq = User.objects.filter(age__gte=18).subquery(query_type="table")
scalar_subq = User.objects.aggregate(count=func.count()).subquery(query_type="scalar")
exists_subq = Post.objects.filter(author_id=F("id")).subquery(query_type="exists")

# Named subqueries for complex queries
active_users = User.objects.filter(is_active=True).subquery("active_users")
```

### 2. Subquery Type Inference Rules

The system automatically infers subquery types based on query structure:

```python
# Scalar subquery inference
# Rule 1: Single column + aggregates + LIMIT 1 or count query
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # → scalar

# Rule 2: Single column aggregate queries (common for comparisons)
max_salary = Employee.objects.aggregate(max_sal=func.max(Employee.salary)).subquery()  # → scalar

# Table subquery inference
# Rule 3: Multi-column queries
user_profiles = User.objects.values("id", "username", "email").subquery()  # → table

# Rule 4: Single column non-aggregate (for IN conditions)
user_ids = User.objects.filter(is_active=True).values_list("id").subquery()  # → table

# Default: Table subquery when inference is uncertain
general_query = User.objects.filter(created_at__gte=date.today()).subquery()  # → table
```

### 3. Subquery Usage Patterns

```python
# Table subqueries for JOIN operations
active_users_subq = User.objects.filter(is_active=True).subquery("active_users")
posts_with_active_authors = await Post.objects.join(
    active_users_subq, 
    Post.author_id == active_users_subq.c.id
).all()

# Scalar subqueries for comparisons
avg_age_subq = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age_subq).all()

# Existence subqueries for boolean conditions
has_posts_subq = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
users_with_posts = await User.objects.filter(has_posts_subq).all()

# Complex nested subqueries
department_avg_subq = Employee.objects.filter(
    department_id=F("department_id")
).aggregate(
    dept_avg=F("salary").avg()
).subquery(query_type="scalar")

high_performers = await Employee.objects.filter(
    F("salary") > department_avg_subq * 1.1
).annotate(
    performance_ratio=F("salary") / department_avg_subq
).all()
```

### 4. Subquery Type Conversion

```python
# Convert between subquery types
base_query = User.objects.filter(is_active=True)

# Create different subquery types from same base
table_subq = base_query.subquery().as_table()  # For JOINs
scalar_subq = base_query.subquery().as_scalar()  # For comparisons
exists_subq = base_query.subquery().as_exists()  # For boolean conditions

# Alias subqueries
aliased_subq = base_query.subquery().alias("active_users")

# Access subquery columns (table subqueries only)
user_subq = User.objects.only("id", "username").subquery("users")
user_id_col = user_subq.c.id  # Access specific column
username_col = user_subq.c.username
```

### 5. Advanced Subquery Patterns

```python
# Correlated subqueries
latest_post_subq = Post.objects.filter(
    author_id=F("id")
).order_by("-created_at").limit(1).subquery(query_type="scalar")

users_with_latest_post = await User.objects.annotate(
    latest_post_date=latest_post_subq
).filter(
    latest_post_date__gte=date.today() - timedelta(days=30)
).all()

# Multiple subqueries in single query
avg_age_subq = User.objects.aggregate(avg_age=F("age").avg()).subquery(query_type="scalar")
max_posts_subq = Post.objects.aggregate(max_posts=func.count()).group_by("author_id").subquery(query_type="scalar")

complex_users = await User.objects.filter(
    F("age") > avg_age_subq,
    F("posts_count") >= max_posts_subq * 0.8
).all()

# Subqueries in aggregations
dept_employee_count_subq = Employee.objects.filter(
    department_id=F("department_id")
).aggregate(
    emp_count=func.count()
).subquery(query_type="scalar")

department_stats = await Department.objects.annotate(
    employee_count=dept_employee_count_subq,
    avg_salary_per_employee=F("total_salary") / dept_employee_count_subq
).all()
```

### 6. Subquery Error Handling

```python
from sqlobjects.exceptions import ValidationError
from sqlobjects.locales import t

# Subquery validation errors are localized
try:
    invalid_subq = User.objects.filter(invalid_field=True).subquery(query_type="invalid")
except ValidationError as e:
    print(e.message)  # Localized error message

# Handle subquery conversion failures
try:
    problematic_subq = ComplexQuery.objects.complex_filter().subquery()
except ValidationError as e:
    # Log error and fallback to simpler query
    fallback_query = User.objects.filter(is_active=True)
```

## Type System Architecture

### 1. TypeArgument and TypeDefinition

```python
from typing import Any, Callable, NotRequired, TypedDict

class TypeArgument(TypedDict):
    name: str
    type: type
    required: bool
    default: Any
    transform: NotRequired[Callable[[Any], Any]]  # Optional value transformation
    positional: NotRequired[bool]  # Optional positional parameter flag

class TypeDefinition(TypedDict):
    type: type
    arguments: list[TypeArgument]
```

### 2. Unified Type Registration

All types are registered through a single `_init_type_registry()` function:

```python
def _init_type_registry():
    """Initialize all builtin and special types."""
    builtin_types = [
        # Standard types (auto-extracted parameters)
        (String, "string", ["str"]),
        (Integer, "integer", ["int"]),
        
        # Special types (manual TypeDefinition)
        ({
            "type": ARRAY,
            "arguments": [
                {"name": "item_type", "type": Any, "required": True, "default": None,
                 "transform": _transform_array_item_type, "positional": True},
                {"name": "dimensions", "type": int, "required": False, "default": 1}
            ]
        }, "array", None),
    ]
    
    for field_type, type_name, aliases in builtin_types:
        register_field_type(field_type, type_name, aliases=aliases)
```

### 3. Parameter Processing Pipeline

1. **Parameter Extraction**: `_extract_type_params()` separates type parameters from column parameters
2. **Value Transformation**: Apply `transform` functions if defined
3. **Type Instantiation**: `_create_type_instance()` handles positional and keyword arguments
4. **Column Creation**: `mapped_column()` with the instantiated type

### 4. Custom Type Registration Examples

```python
# Simple type with automatic parameter extraction
register_field_type(MyCustomType, "custom", aliases=["my_type"])

# Complex type with transform function
def transform_my_param(value):
    return process_value(value)

register_field_type({
    "type": ComplexType,
    "arguments": [
        {"name": "param1", "type": str, "required": True, "default": None,
         "transform": transform_my_param, "positional": True},
        {"name": "param2", "type": int, "required": False, "default": 100}
    ]
}, "complex")
```

## Performance Guidelines

### 1. Type System Performance

- **Unified Processing**: All types use the same processing pipeline, eliminating special-case overhead
- **Parameter Caching**: Type definitions are cached in `_FIELD_TYPE_REGISTRY` for fast lookup
- **Transform Functions**: Applied only when needed, with minimal overhead
- **Automatic Extraction**: Constructor parameters extracted once during registration

### 2. Query Optimization

```python
# Use select_related for one-to-one and many-to-one
users = await User.objects.select_related('profile').all()

# Use prefetch_related for one-to-many and many-to-many
users = await User.objects.prefetch_related('posts').all()

# Combine both for complex relationships
users = await User.objects.select_related('profile').prefetch_related('posts__tags').all()

# Use only() to load specific fields
users = await User.objects.only('id', 'username', 'email').all()

# Use defer() to exclude heavy fields
users = await User.objects.defer('large_text_field').all()
```

### 3. Expression Performance

```python
# Prefer database-level operations over Python processing
# Good: Use expressions for calculations
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    age_years=func.extract('year', User.birth_date)
).all()

# Good: Use aggregations in database
stats = await Order.objects.aggregate(
    total_amount=func.sum(Order.amount),
    avg_amount=func.avg(Order.amount),
    order_count=func.count()
)

# Avoid: Loading all data then processing in Python
# orders = await Order.objects.all()
# total = sum(order.amount for order in orders)  # Inefficient
```

### 4. Advanced Query Techniques

```python
# Query slicing (using get_item method)
users_page = await User.objects.get_item(slice(0, 10))  # First 10 users
users_offset = await User.objects.get_item(slice(20, 30))  # Users 20-30

# Row-level locking
user = await User.objects.select_for_update().get(id=1)
user = await User.objects.select_for_update(nowait=True).get(id=1)
user = await User.objects.select_for_update(skip_locked=True).get(id=1)

# Query optimization with options
from sqlalchemy.orm import joinedload, selectinload

users = await User.objects.options(
    joinedload(User.profile),
    selectinload(User.posts)
).all()

# Query explanation for debugging
explain_result = await User.objects.filter(age__gte=18).explain(
    analyze=True,
    output="json"
)

# Date/datetime queries
dates = await User.objects.dates('created_at', 'month', order='DESC')
datetimes = await User.objects.datetimes('created_at', 'day', order='ASC')
```

## ORM Method Organization

### 1. Method Categories

SQLObjects organizes database operations through two main interfaces:

- **ObjectsManager** (`User.objects`): Direct database operations and shortcuts
- **QuerySet** (`User.objects.filter()`): Chainable query building and execution

Methods are organized into functional groups:

#### Basic Query Methods

- `filter()`, `all()`, `get()`, `first()`, `last()`
- `earliest()`, `latest()` - Ordering-based retrieval
- `get_or_create(*filters, *, defaults, **conditions)` - Get/create patterns with complex filter support
- `update_or_create(*filters, *, defaults, **conditions)` - Update/create patterns with complex filter support
- `in_bulk()` - Efficient bulk retrieval by field values

#### Session Parameter Support

Most methods accept an optional `session` parameter in `**kwargs` to specify which database session to use:

```python
# Basic usage with default session
user = await User.objects.get(username="john")

# Using specific database session
user = await User.objects.get(username="john", session=analytics_session)

# Complex query with session
user = await User.objects.get(
    Q(username="john") | Q(email="john@example.com"),
    is_active=True,
    session=main_session
)

# Chain methods with session
users = await User.objects.filter(is_active=True).all(session=db_session)
```

#### Create Operations

- `create()` - Single object creation with validation
- `bulk_create()` - Batch creation for performance

#### Update & Delete Operations

- `update(values, *, filter=None, **conditions)` - Update with complex conditions and explicit values parameter
- `bulk_update(mappings, match_fields)` - True bulk update using executemany for performance
- `delete(*, filter=None, **conditions)` - Delete with complex conditions (Q objects, F expressions)
- `bulk_delete(ids, id_field)` - True bulk delete using IN clauses for performance
- `delete_all()` - Delete all records (with fast TRUNCATE option)

#### Aggregation & Statistics

- `count()`, `exists()`, `aggregate()`
- `values()`, `values_list()` - Data extraction

#### Utility Methods

- `random()`, `sample()` - Random sampling
- `dates()`, `datetimes()` - Date/time queries (via QuerySet)
- `explain()` - Query analysis (via QuerySet)
- `raw()` - Raw SQL execution (via QuerySet)
- `iterator()` - Async iteration for large datasets (via QuerySet)
- `get_item()` - Index/slice access (via QuerySet)

#### QuerySet Shortcuts

- `distinct()`, `exclude()`, `order_by()`
- `limit()`, `offset()`, `only()`, `defer()`
- `none()`, `reverse()`, `select_for_update()`, `slice()`

#### Relationships & Joins

- `select_related()`, `prefetch_related()`
- `join()`, `leftjoin()`, `outerjoin()`

#### Advanced Query Methods

- `annotate()`, `group_by()`, `having()`, `options()`
- `subquery()` - Intelligent subquery creation with automatic type inference

### 2. Method Chaining Patterns

```python
# Chain methods for complex queries
users = await (User.objects
    .filter(is_active=True)
    .select_related('profile')
    .prefetch_related('posts')
    .order_by('-created_at')
    .limit(10)
    .all())

# Use shortcuts for common operations
active_users = User.objects.filter(is_active=True)
recent_users = active_users.order_by('-created_at').limit(5)
user_names = await active_users.values_list('username', flat=True)
```

## Database Connection Lifecycle Rules

### 1. Connection Cleanup with auto_default

```python
# Graceful shutdown with automatic failover
async def shutdown_primary_db():
    # Close primary database, automatically switch to secondary
    await close_db("primary", auto_default=True)
    
    # System continues to work with secondary database
    remaining_users = await User.objects.count()  # Uses secondary DB

# Test cleanup with automatic default management
@pytest.fixture
async def test_with_multiple_dbs():
    # Setup multiple test databases
    main_db = await init_db("sqlite:///:memory:", name="test_main", is_default=True)
    backup_db = await init_db("sqlite:///:memory:", name="test_backup", is_default=False)
    
    yield main_db, backup_db
    
    # Cleanup: close main, backup becomes default automatically
    await close_db("test_main", auto_default=True)
    await close_db("test_backup")  # Close remaining database

# Batch database cleanup
async def cleanup_old_databases(db_names: list[str]):
    # Close multiple databases, maintain default if possible
    await close_dbs(db_names, auto_default=True)
```

### 2. Default Database Selection Logic

When `auto_default=True` and the current default database is being closed:

1. **Selection Method**: Uses `next(iter(remaining_databases), None)` to select the first available database
2. **Session Factory Update**: Automatically updates `SessionContextManager` with the new default
3. **No Available Databases**: Sets `_default_db` to `None` if no databases remain

```python
# Internal behavior (for understanding)
if auto_default and self._default_db == db_name:
    self._default_db = next(iter(self._databases), None)
    if self._default_db:
        default_db = self._databases[self._default_db]
        SessionContextManager.set_session_factory(default_db.session_factory, self._default_db, is_default=True)
```

## Configuration System Rules

### 1. Database-Specific Configuration

```python
from sqlobjects.config import mysql_config, postgresql_config

class User(ObjectModel):
    # ... fields ...

    class Config:
        db_options = mysql_config(
            engine="InnoDB",
            charset="utf8mb4",
            row_format="DYNAMIC"
        )
```

### 2. Index and Constraint Creation

```python
from sqlobjects.config import create_index, create_check_constraint

class Product(ObjectModel):
    # ... fields ...

    class Config:
        indexes = [
            index("idx_sku", "sku", unique=True),
            index("idx_name_category", "name", "category_id")
        ]
        constraints = [
            constraint("price > 0", "chk_price_positive")
        ]
```

## Function Categories and Usage Patterns

```python
# === F Class Instance Methods (Single Field Operations) ===

# String functions on F instances
F("name").upper()               # Convert to uppercase
F("description").trim()         # Remove whitespace
F("text").length()              # String length
F("content").substr(1, 10)      # Extract substring
F("text").replace("old", "new") # Replace substring

# Math functions on F instances
F("value").abs()                # Absolute value
F("price").round(2)             # Round to 2 decimals
F("area").sqrt()                # Square root
F("base") ** 2                  # Power using operator

# Date/time extraction on F instances
F("created_at").year()          # Extract year
F("created_at").month()         # Extract month
F("created_at").day()           # Extract day
F("timestamp").hour()           # Extract hour

# Aggregates on F instances
F("amount").sum()               # Sum values
F("score").avg()                # Average
F("price").max()                # Maximum
F("age").min()                  # Minimum
F("id").count()                 # Count non-null

# Type conversion on F instances
F("id").to_string()             # Convert to string
F("code").to_integer()          # Convert to integer
F("price").to_decimal(10, 2)    # Convert to decimal
F("flag").to_boolean()          # Convert to boolean

# === func Object Methods (Multi-Field Operations) ===

# String functions with multiple arguments
func.concat(F("first"), " ", F("last"))    # Concatenate strings
func.upper(F("name"))                       # Also available on func
func.substr(F("text"), 1, 10)               # Also available on func
func.length(F("description"))               # Also available on func

# Math functions with multiple arguments
func.power(F("base"), F("exponent"))        # Power function
func.round(F("value"), F("precision"))      # Dynamic precision
func.abs(F("difference"))                   # Also available on func

# Date/time functions
func.now()                                  # Current timestamp
func.current_date()                         # Current date
func.extract('year', from_=F("date"))       # Extract date part

# Aggregate functions
func.count()                                # Count all rows (COUNT(*))
func.sum(F("amount"))                       # Sum values
func.avg(F("score"))                        # Average
func.max(F("price"))                        # Maximum
func.min(F("age"))                          # Minimum

# Conditional functions
func.coalesce(F("nickname"), F("name"), "Anonymous")  # First non-null
func.nullif(F("value"), 0)                            # Return null if equal

# Case expressions (func only)
func.case(
    (F("score") >= 90, "A"),
    (F("score") >= 80, "B"),
    else_="F"
)

# Window functions (func only)
func.row_number()                           # Row number
func.rank()                                 # Rank with gaps
func.dense_rank()                           # Rank without gaps
func.lag(F("value"), 1)                     # Previous row value
func.lead(F("value"), 1)                    # Next row value

# Database-specific functions (automatic fallback)
func.json_extract(F("data"), "$.key")       # JSON extraction
func.array_length(F("tags"))                # Array length (PostgreSQL)
func.group_concat(F("names"))               # Group concatenation (MySQL)

# === Usage Guidelines ===

# Prefer F instance methods for single-field operations
F("name").upper().trim()                    # Chainable
F("price").round(2).to_string()             # Multiple transformations

# Use func for multi-field operations
func.concat(F("first_name"), " ", F("last_name"))  # Multiple fields
func.coalesce(F("mobile"), F("phone"), "N/A")      # Multiple fallbacks

# Complex expressions combining both
total_with_tax = func.round(F("subtotal") * F("tax_rate"), 2)
full_address = func.concat(
    F("street").trim(),
    ", ",
    F("city").upper(),
    " ",
    F("postal_code")
)

# Subquery expressions in complex queries
avg_salary_subq = Employee.objects.aggregate(avg_salary=F("salary").avg()).subquery(query_type="scalar")
high_earners = await Employee.objects.filter(
    F("salary") > avg_salary_subq * 1.2  # 20% above average
).annotate(
    salary_ratio=F("salary") / avg_salary_subq
).all()
```

## Performance Considerations

### 1. Subquery Performance

```python
# Prefer scalar subqueries for single value comparisons
avg_salary = Employee.objects.aggregate(avg_sal=F("salary").avg()).subquery(query_type="scalar")
high_earners = await Employee.objects.filter(F("salary") > avg_salary).all()

# Use table subqueries for complex JOINs
active_users = User.objects.filter(is_active=True).select_related("profile").subquery("active")
results = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()

# Use EXISTS for boolean conditions (often more efficient than IN)
has_orders = Order.objects.filter(customer_id=F("id")).subquery(query_type="exists")
active_customers = await Customer.objects.filter(has_orders).all()

# Avoid deeply nested subqueries when possible
# Good: Use JOINs or separate queries for complex relationships
# Avoid: Multiple levels of nested subqueries that are hard to optimize
```

### 2. Bulk Operations Performance

```python
# Bulk create
users_data = [{"username": f"user{i}", "email": f"user{i}@example.com"} for i in range(100)]
await User.objects.bulk_create(users_data)

# Bulk retrieval
user_dict = await User.objects.in_bulk([1, 2, 3], field_name="id")

# Random sampling
random_users = await User.objects.random(5)
sample_users = await User.objects.sample(10)
```

### 3. Memory Management

```python
# Use iterator for large datasets to avoid loading everything into memory
async for user in User.objects.filter(is_active=True).iterator():
    process_user(user)

# Custom memory cleanup interval
async for user in User.objects.iterator(memory_cleanup_interval=1000):
    process_user(user)

# Use pagination for large result sets
page_size = 100
offset = 0
while True:
    users = await User.objects.slice(offset, offset + page_size).all()
    if not users:
        break
    
    for user in users:
        process_user(user)
    
    offset += page_size
```