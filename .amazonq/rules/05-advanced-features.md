# SQLObjects Advanced Features

## Subquery System Rules

### 1. Intelligent Subquery Creation with Type Inference

SQLObjects provides an intelligent subquery system with automatic type inference:

```python
from sqlobjects.expressions import SubqueryExpression

# Automatic type inference (recommended)
subq = User.objects.filter(User.is_active == True).subquery()  # Auto-inferred type

# Explicit type specification
table_subq = User.objects.filter(User.age >= 18).subquery(query_type="table")
scalar_subq = User.objects.aggregate(count=func.count()).subquery(query_type="scalar")
exists_subq = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")

# Named subqueries for complex queries
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
```

### 2. Subquery Type Inference Rules

The system automatically infers subquery types based on query structure:

```python
# Scalar subquery inference rules
# Rule 1: Single column + aggregates + LIMIT 1 or count query → scalar
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # → scalar

# Rule 2: Single column aggregate queries (common for comparisons) → scalar
max_salary = Employee.objects.aggregate(max_sal=func.max(Employee.salary)).subquery()  # → scalar

# Table subquery inference rules
# Rule 3: Multi-column queries → table
user_profiles = User.objects.values("id", "username", "email").subquery()  # → table

# Rule 4: Single column non-aggregate (for IN conditions) → table
user_ids = User.objects.filter(User.is_active == True).values_list("id").subquery()  # → table

# Default: Table subquery when inference is uncertain
general_query = User.objects.filter(User.created_at >= date.today()).subquery()  # → table
```

### 3. Subquery Type Conversion

```python
# Convert between subquery types
base_query = User.objects.filter(User.is_active == True)

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



### 4. Subquery Usage Patterns

```python
# Table subqueries for JOIN operations
active_users_subq = User.objects.filter(User.is_active == True).subquery("active_users")
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
    department_id=Employee.department_id
).aggregate(
    dept_avg=func.avg(Employee.salary)
).subquery(query_type="scalar")

high_performers = await Employee.objects.filter(
    Employee.salary > department_avg_subq * 1.1
).annotate(
    performance_ratio=Employee.salary / department_avg_subq
).all()
```

### 4. Subquery Type Conversion

```python
# Convert between subquery types
base_query = User.objects.filter(User.is_active == True)

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
    author_id=User.id
).order_by("-created_at").limit(1).subquery(query_type="scalar")

users_with_latest_post = await User.objects.annotate(
    latest_post_date=latest_post_subq
).filter(
    User.latest_post_date >= date.today() - timedelta(days=30)
).all()

# Multiple subqueries in single query
avg_age_subq = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
max_posts_subq = Post.objects.aggregate(max_posts=func.count()).group_by("author_id").subquery(query_type="scalar")

complex_users = await User.objects.filter(
    User.age > avg_age_subq,
    User.posts_count >= max_posts_subq * 0.8
).all()

# Subqueries in aggregations
dept_employee_count_subq = Employee.objects.filter(
    department_id=Employee.department_id
).aggregate(
    emp_count=func.count()
).subquery(query_type="scalar")

department_stats = await Department.objects.annotate(
    employee_count=dept_employee_count_subq,
    avg_salary_per_employee=Department.total_salary / dept_employee_count_subq
).all()
```

### 6. Subquery Error Handling

```python
from sqlobjects.exceptions import ValidationError

# Subquery validation errors use English messages
try:
    invalid_subq = User.objects.filter(User.invalid_field == True).subquery(query_type="invalid")
except ValidationError as e:
    print(e.message)  # English error message

# Handle subquery conversion failures
try:
    problematic_subq = ComplexQuery.objects.complex_filter().subquery()
except ValidationError as e:
    # Log error and fallback to simpler query
    fallback_query = User.objects.filter(User.is_active == True)
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
# Use select_related for one-to-one and many-to-one - string syntax
users = await User.objects.select_related('profile').all()
# SQLAlchemy expression syntax (recommended)
users = await User.objects.select_related(User.profile).all()

# Use prefetch_related for one-to-many and many-to-many - string syntax
users = await User.objects.prefetch_related('posts').all()
# SQLAlchemy expression syntax (recommended)
users = await User.objects.prefetch_related(User.posts).all()

# Combine both for complex relationships - string syntax
users = await User.objects.select_related('profile').prefetch_related('posts.tags').all()
# SQLAlchemy expression syntax (recommended)
users = await User.objects.select_related(User.profile).prefetch_related(User.posts).all()

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
user = await User.objects.select_for_update().get(User.id == 1)
user = await User.objects.select_for_update(nowait=True).get(User.id == 1)
user = await User.objects.select_for_update(skip_locked=True).get(User.id == 1)

# Query optimization with options
# Using SQLObjects relationship loading (recommended)
users = await User.objects.select_related(User.profile).prefetch_related(User.posts).all()

# Or using SQLAlchemy options directly
from sqlalchemy.orm import joinedload, selectinload
users = await User.objects.options(
    joinedload(User.profile),
    selectinload(User.posts)
).all()

# Query explanation for debugging
explain_result = await User.objects.filter(User.age >= 18).explain(
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

#### Session Management with using() Method

Methods use the `using()` method pattern to specify which database session to use:

```python
# Basic usage with default session
user = await User.objects.get(User.username == "john")

# Using specific database session
user = await User.objects.using(analytics_session).get(User.username == "john")

# Complex query with session
user = await User.objects.using(main_session).get(
    Q(username="john") | Q(email="john@example.com"),
    is_active=True
)

# Chain methods with session
users = await User.objects.using(db_session).filter(User.is_active == True).all()
```

#### Create Operations

- `create()` - Single object creation with validation
- `bulk_create()` - Batch creation for performance

#### Update & Delete Operations

- `update(values, *, filter=None, **conditions)` - Update with complex conditions and explicit values parameter
- `bulk_update(mappings, match_fields)` - True bulk update using executemany for performance
- `delete(*, filter=None, **conditions)` - Delete with complex conditions (Q objects, SQLAlchemy expressions)
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
    .filter(User.is_active == True)
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

### 1. Model Configuration Processing

```python
# Configuration is processed through ConfigParser
from sqlobjects.config import ConfigParser, ModelConfig

class ObjectModel:
    @classmethod
    def _process_config(cls):
        """Process and apply model configuration"""
        parser = ConfigParser()
        configs = [parser.parse_class_attributes(cls)]
        
        # Parse Config inner class if present
        config_class = getattr(cls, "Config", None)
        if config_class:
            configs.append(parser.parse_config_class(config_class))
        
        # Merge configurations and apply
        merged_config = parser.merge_configs(*configs)
        cls._apply_config(merged_config)
```

### 2. Database-Specific Configuration

```python
from sqlobjects.base import ObjectModel
from sqlobjects.config import mysql_config, postgresql_config, multi_db_config

class User(ObjectModel):
    # ... fields ...

    class Config:
        # Multi-database configuration
        db_options = multi_db_config(
            mysql={"engine": "InnoDB", "charset": "utf8mb4"},
            postgresql={"tablespace": "fast_storage"},
            generic={"comment": "User data table"}
        )
```

### 3. Index and Constraint Creation

```python
from sqlobjects.base import ObjectModel
from sqlobjects.config import index, constraint, unique

class Product(ObjectModel):
    # ... fields ...

    class Config:
        indexes = [
            index("idx_sku", "sku", unique=True),
            index("idx_name_category", "name", "category_id")
        ]
        constraints = [
            constraint("price > 0", "chk_price_positive"),
            unique("name", "category", name="uq_name_category")
        ]
```

## Function Categories and Usage Patterns

```python
# === Field Methods (Enhanced Comparators) ===

# String functions on field instances
User.name.upper()               # Convert to uppercase
User.description.trim()         # Remove whitespace
User.text.length()              # String length
User.content.substring(1, 10)   # Extract substring

# Math functions on field instances
User.value.abs()                # Absolute value
User.price.round(2)             # Round to 2 decimals
User.area.sqrt()                # Square root

# Date/time extraction on field instances
User.created_at.year()          # Extract year
User.created_at.month()         # Extract month
User.created_at.day()           # Extract day
User.timestamp.hour()           # Extract hour

# === func Object Methods (Multi-Field Operations) ===

# String functions with multiple arguments
func.concat(User.first_name, " ", User.last_name)  # Concatenate strings
func.upper(User.name)                               # Also available on func
func.substr(User.text, 1, 10)                       # Also available on func
func.length(User.description)                       # Also available on func

# Math functions with multiple arguments
func.power(User.base, User.exponent)                # Power function
func.round(User.value, User.precision)              # Dynamic precision
func.abs(User.difference)                           # Also available on func

# Date/time functions
func.now()                                          # Current timestamp
func.current_date()                                 # Current date
func.extract('year', User.date)                     # Extract date part

# Aggregate functions
func.count()                                        # Count all rows (COUNT(*))
func.sum(User.amount)                               # Sum values
func.avg(User.score)                                # Average
func.max(User.price)                                # Maximum
func.min(User.age)                                  # Minimum

# Conditional functions
func.coalesce(User.nickname, User.name, "Anonymous")  # First non-null
func.nullif(User.value, 0)                           # Return null if equal

# Case expressions (func only)
func.case(
    (User.score >= 90, "A"),
    (User.score >= 80, "B"),
    else_="F"
)

# Window functions (func only)
func.row_number()                                   # Row number
func.rank()                                         # Rank with gaps
func.dense_rank()                                   # Rank without gaps
func.lag(User.value, 1)                             # Previous row value
func.lead(User.value, 1)                            # Next row value

# Database-specific functions (automatic fallback)
func.json_extract(User.data, "$.key")               # JSON extraction
func.array_length(User.tags)                        # Array length (PostgreSQL)
func.group_concat(User.names)                       # Group concatenation (MySQL)

# === Usage Guidelines ===

# Use field methods for single-field operations
User.name.upper().trim()                            # Chainable

# Use func for multi-field operations
func.concat(User.first_name, " ", User.last_name)   # Multiple fields
func.coalesce(User.mobile, User.phone, "N/A")       # Multiple fallbacks

# Complex expressions combining both
total_with_tax = func.round(User.subtotal * User.tax_rate, 2)
full_address = func.concat(
    User.street.trim(),
    ", ",
    User.city.upper(),
    " ",
    User.postal_code
)

# Subquery expressions in complex queries
avg_salary_subq = Employee.objects.aggregate(avg_salary=func.avg(Employee.salary)).subquery(query_type="scalar")
high_earners = await Employee.objects.filter(
    Employee.salary > avg_salary_subq * 1.2  # 20% above average
).annotate(
    salary_ratio=Employee.salary / avg_salary_subq
).all()
```

## Performance Considerations

### 1. Subquery Performance

```python
# Prefer scalar subqueries for single value comparisons
avg_salary = Employee.objects.aggregate(avg_sal=func.avg(Employee.salary)).subquery(query_type="scalar")
high_earners = await Employee.objects.filter(Employee.salary > avg_salary).all()

# Use table subqueries for complex JOINs
active_users = User.objects.filter(User.is_active == True).select_related("profile").subquery("active")
results = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()

# Use EXISTS for boolean conditions (often more efficient than IN)
has_orders = Order.objects.filter(Order.customer_id == Customer.id).subquery(query_type="exists")
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
async for user in User.objects.filter(User.is_active == True).iterator():
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