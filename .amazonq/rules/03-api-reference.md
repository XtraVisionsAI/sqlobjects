# SQLObjects API Reference

## API Design Rules

### 1. Session Parameter Pattern

All ObjectsManager and QuerySet methods follow a consistent session parameter pattern:

```python
async def method_name(
    self,
    *args,
    session: AsyncSession | None = None,
    **kwargs
) -> ReturnType:
    session = session or self._session
    # ... method implementation
```

**Key Principles:**

- **Explicit Session Parameter**: Session is always a named parameter for clarity
- **Optional with Fallback**: Falls back to `self._session` from SessionContextManager
- **Multi-database Support**: Easy to specify which database to use
- **Type Safety**: Session parameter is properly typed
- **Consistent**: Same pattern across all database operation methods

### 2. Query Method Categories

Methods are organized into clear functional categories:

**Query Building Methods (Return QuerySet):**

- `filter(*conditions)` - Add WHERE conditions
- `exclude(*conditions)` - Add NOT WHERE conditions
- `order_by(*fields)` - Add ORDER BY clause
- `limit(count)`, `offset(count)` - Add LIMIT/OFFSET
- `select_related(*relations)` - JOIN preloading
- `prefetch_related(*relations)` - Separate query preloading
- `annotate(**kwargs)` - Add calculated fields
- `distinct(*fields)` - Add DISTINCT clause

**Query Execution Methods (Execute Query):**

- `all()` - Get all results as list
- `get(*conditions)` - Get single object
- `first()`, `last()` - Get first/last object
- `count()` - Count matching objects
- `exists()` - Check if any objects exist
- `values(*fields)` - Get dictionaries
- `values_list(*fields)` - Get tuples/flat list

**Usage Examples:**

```python
# Query building (chainable)
query = User.objects.filter(is_active=True).order_by("-created_at").limit(10)

# Query execution
users = await query.all()
user = await User.objects.get(username="john")
count = await User.objects.filter(is_active=True).count()

# With specific session
users = await User.objects.filter(is_active=True).all(session=analytics_session)
```

## Field Parameter Guidelines

### Parameter Priority Guide

#### High Priority Parameters (Database Constraints)

```python
# Database constraint scenarios
username: Column[str] = str_column(length=50, nullable=False, unique=True)  # Required unique
id: Column[int] = int_column(primary_key=True, autoincrement=True)  # Auto-increment PK
email: Column[str] = str_column(length=100, nullable=False, unique=True)  # Required unique email
price: Column[Decimal] = numeric_column(precision=10, scale=2, nullable=False)  # Required price
```

#### Medium Priority Parameters (Dynamic Defaults and Dataclass Behavior)

```python
from datetime import datetime
from uuid import uuid4

# Dynamic default value scenarios
created_at: Column[datetime] = datetime_column(default_factory=datetime.now)
api_key: Column[str] = str_column(default_factory=lambda: str(uuid4()))
random_code: Column[str] = str_column(default_factory=generate_random_code)

# Dataclass control scenarios
internal_id: Column[str] = str_column(init=False, repr=False)  # Internal field
password_hash: Column[str] = str_column(repr=False)  # Hidden in __repr__
sort_key: Column[int] = int_column(compare=True, hash=True)  # Participates in comparison
```

#### Low Priority Parameters (Advanced Usage)

```python
# Advanced parameter scenarios
ordered_field: Column[str] = str_column(sort_order=1)  # Field ordering control
keyword_only: Column[str] = str_column(kw_only=True)  # Keyword-only parameter
existing_col: Column[str] = str_column(use_existing_column=True)  # Reuse column definition
```

## Model Definition Standards

### 1. Basic Model Structure

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, column, relationship, str_column, bool_column, datetime_column
from sqlalchemy import func
from datetime import datetime

class User(ObjectModel):
    id: Column[int] = column(type="integer", primary_key=True, autoincrement=True)
    username: Column[str] = str_column(length=50, unique=True, nullable=False)
    email: Column[str] = str_column(length=100, unique=True, nullable=False)
    is_active: Column[bool] = bool_column(default=True, nullable=False)
    created_at: Column[datetime] = datetime_column(default_factory=datetime.now, nullable=False)
    
    # Advanced parameter examples
    internal_id: Column[str] = str_column(init=False, repr=False)  # Internal field
    api_key: Column[str] = str_column(default_factory=generate_api_key, repr=False)
    sort_order: Column[int] = column(type="integer", sort_order=1, compare=True)
```

### 2. Field Type System

SQLObjects features a unified type system with automatic parameter extraction and transformation support:

#### Type Registration System

- All types are registered through `register_field_type()` with automatic parameter extraction
- Special types (array, enum) use `TypeDefinition` with transform functions and positional parameters
- Type aliases supported: `str` → `string`, `int` → `integer`, `bool` → `boolean`, `decimal` → `numeric`

#### Direct Column Definition

- `column(type="string", length=255)` for text fields (default length: 255)
- `column(type="text")` for long text without length limit
- `column(type="integer")`, `column(type="bigint")`, `column(type="smallint")` for integers
- `column(type="boolean")` for booleans
- `column(type="datetime")`, `column(type="date")`, `column(type="time")` for temporal types
- `column(type="numeric", precision=10, scale=2)` for decimal numbers
- `column(type="json")` for JSON fields
- `column(type="uuid")` for UUID fields
- `column(type="array", item_type="string", dimensions=1)` for arrays (with automatic type conversion)
- `column(type="enum", enum_class=MyEnum)` for enums (positional parameter)

- `column(type="varbinary", length=255)` for variable-length binary data
- `column(type="unicode", length=100)` for Unicode strings (legacy)
- `column(type="unicodetext")` for Unicode text (legacy)

#### Shortcut Functions (Recommended)

- `str_column(length=255)` for string fields with type variants
- `int_column()` for integer fields with size variants
- `bool_column()` for boolean fields
- `numeric_column(precision=10, scale=2)` for decimal fields
- `datetime_column()` for datetime fields with type variants
- `json_column()` for JSON fields
- `array_column("string")` for array fields
- `enum_column(MyEnum)` for enum fields
- `uuid_column()` for UUID fields
- `binary_column("varbinary")` for binary data with type variants


#### Advanced Type System Features

1. **Automatic Parameter Extraction**: The system uses `inspect` to automatically extract SQLAlchemy type constructor
   parameters:
   ```python
   # Standard types use automatic extraction
   column(type="string", length=255)  # → String(length=255)
   numeric_column(precision=10, scale=2)  # → Numeric(precision=10, scale=2)
   ```

2. **Transform Functions**: Special types can define transform functions for parameter conversion:
   ```python
   # Array item_type is automatically converted from string to SQLAlchemy type
   array_column("string")  # "string" → String() instance
   column(type="array", item_type="integer", dimensions=2)
   ```

3. **Positional Parameters**: Some types use positional parameters for cleaner syntax:
   ```python
   # Enum class is passed as positional parameter
   enum_column(MyEnum)  # → Enum(MyEnum)
   column(type="enum", enum_class=MyEnum)
   ```

4. **Custom Type Registration**: Register custom types with full feature support:
   ```python
   from sqlobjects.fields import register_field_type
   
   # Automatic parameter extraction
   register_field_type(MyCustomType, "custom", aliases=["my_type"])
   
   # Manual definition with transform functions
   register_field_type({
       "type": MySpecialType,
       "arguments": [
           {"name": "param", "type": str, "required": True, "default": None,
            "transform": my_transform_func, "positional": True}
       ]
   }, "special")
   ```

5. **Type Aliases**: Common aliases are supported:
    - `"str"` → `"string"`
    - `"int"` → `"integer"`
    - `"bool"` → `"boolean"`
    - `"decimal"` → `"numeric"`

#### Common Type Examples

```python
# String types - using shortcut functions (recommended)
username: Column[str] = str_column(length=50, nullable=False, unique=True)  # Required unique field
code: Column[str] = str_column(type="char", length=10)  # Fixed length
description: Column[str] = str_column(type="varchar", length=500)
long_text: Column[str] = str_column(type="text")  # No length limit

# String types with advanced parameters
api_key: Column[str] = str_column(default_factory=generate_api_key, repr=False)  # Hidden in repr
internal_field: Column[str] = str_column(init=False, repr=False)  # Internal use only

# String types - using column() function
username: Column[str] = column(type="string", length=50, nullable=False)
code: Column[str] = column(type="char", length=10)

# Numeric types - using shortcut functions (recommended)
price: Column[Decimal] = numeric_column(precision=10, scale=2, nullable=False)  # Required price
percentage: Column[Decimal] = numeric_column(type="decimal", precision=5, scale=4)
weight: Column[float] = numeric_column(type="float")

# Integer types with size variants
id: Column[int] = int_column(primary_key=True, autoincrement=True)  # Auto-increment PK
big_number: Column[int] = int_column(type="bigint")
small_number: Column[int] = int_column(type="smallint")

# Integer with advanced parameters
counter: Column[int] = int_column(default=0, init=False)  # Internal counter
sort_order: Column[int] = int_column(compare=True, sort_order=1)  # Sortable field

# Boolean types
is_active: Column[bool] = bool_column(default=True, nullable=False)  # Required boolean
is_verified: Column[bool] = bool_column(default=False)

# DateTime types with variants
created_at: Column[datetime] = datetime_column(default_factory=datetime.now, nullable=False)
birth_date: Column[date] = datetime_column(type="date")
start_time: Column[time] = datetime_column(type="time")

# Array types (PostgreSQL)
tags: Column[list[str]] = array_column("string")
matrix: Column[list[list[int]]] = array_column("integer", dimensions=2)

# Enum types
status: Column[UserStatus] = enum_column(UserStatus, default=UserStatus.ACTIVE)

# JSON and UUID types
preferences: Column[dict] = json_column(default=dict)
external_id: Column[str] = uuid_column(unique=True)

# Binary and Pickle types
file_data: Column[bytes] = binary_column(length=1024)
image_data: Column[bytes] = binary_column(type="varbinary", length=2048)


# Unicode types (for legacy databases)
name_unicode: Column[str] = column(type="unicode", length=100)
description_unicode: Column[str] = column(type="unicodetext")
```

### 3. Field Shortcuts and Advanced Features

```python
from uuid import uuid4
from sqlobjects.fields import (
    identity, computed, sequence, foreign_key, created_at, updated_at,
    str_column, int_column, bool_column, numeric_column, datetime_column,
    json_column, array_column, enum_column, uuid_column,
    composite, column_property, synonym
)

class User(ObjectModel):
    # Auto-increment primary key
    id: Column[int] = identity()
    
    # String fields with shortcuts
    username: Column[str] = str_column(length=50, unique=True)
    first_name: Column[str] = str_column(length=30)
    last_name: Column[str] = str_column(length=30)
    
    # Foreign key
    department_id: Column[int] = foreign_key("departments.id")
    
    # Timestamps
    created_at: Column[datetime] = created_at()
    updated_at: Column[datetime] = updated_at()
    
    # Boolean field
    is_active: Column[bool] = bool_column(default=True)
    
    # Numeric field
    salary: Column[Decimal] = numeric_column(precision=10, scale=2)
    
    # JSON column
    preferences: Column[dict] = json_column(default=dict)
    
    # Array column (PostgreSQL)
    tags: Column[list[str]] = array_column("string", default=list)
    
    # Enum column
    status: Column[UserStatus] = enum_column(UserStatus, default=UserStatus.ACTIVE)
    
    # UUID column
    uuid: Column[str] = uuid_column(unique=True)
    
    # Computed column with type specification
    full_name: Column[str] = computed("first_name || ' ' || last_name", type="string")
    
    # Sequence column
    order_number: Column[int] = sequence("order_seq", start=1000)
    
    # SQLAlchemy advanced features
    address: composite = composite(Address, street, city, state)
    display_name: column_property = column_property(first_name + " " + last_name)
    name: synonym = synonym("username")
```

### 4. Relationship Definitions

```python
# One-to-Many
posts: Column[list["Post"]] = relationship("Post", back_populates="author")

# Many-to-One
author: Column["User"] = relationship("User", back_populates="posts")

# Many-to-Many
tags: Column[list["Tag"]] = relationship("Tag", secondary="post_tags", back_populates="posts")

# Foreign Key
author_id: Column[int] = foreign_key("users.id")
```

### 5. Model Configuration and Table Naming

```python
class User(ObjectModel):
    # ... fields ...

    class Config:
        table_name = "users"  # Optional: defaults to Rails-style pluralized class name
        ordering = ["-created_at"]
        indexes = [
            index("idx_username", "username"),
            index("idx_email", "email", unique=True)
        ]
```

#### Table Name Convention

SQLObjects follows Rails-style table naming conventions:

- **Default behavior**: Converts CamelCase model names to snake_case plural table names
- **Priority**: `Config.table_name` > `__tablename__` > auto-generated name

```python
# Automatic table name generation
class User(ObjectModel):          # → table: "users"
class UserProfile(ObjectModel):   # → table: "user_profiles"
class XMLParser(ObjectModel):     # → table: "xml_parsers"
class HTTPRequest(ObjectModel):   # → table: "http_requests"

# Explicit table name (overrides default)
class CustomModel(ObjectModel):
    class Config:
        table_name = "my_custom_table"
```

## Q Object Usage Rules

Q objects provide logical combination of SQLAlchemy expressions with clear syntax requirements:

### Supported Combination Patterns

```python
# Q objects with SQLAlchemy expressions
Q(User.username == "john")
Q(User.age >= 18, User.is_active == True)  # Multiple expressions (AND)

# Q objects with other Q objects
Q(User.username == "john") & Q(User.age >= 18)
Q(User.is_active == True) | Q(User.is_staff == True)
~Q(User.is_deleted == True)

# Q objects with SQLAlchemy expressions (Q object must be on left side)
Q(User.username == "john") & (User.age > 25)
Q(User.is_active == True) | (User.created_at > datetime.now())
```

### Usage in Queries

```python
# In filter methods
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Mixed with direct SQLAlchemy expressions
users = await User.objects.filter(
    Q(User.department == "IT"),
    User.salary >= 50000  # Direct SQLAlchemy expression
).all()
```

### Design Rationale

- Q objects focus on logical combination of SQLAlchemy expressions
- No reverse operators to maintain API simplicity
- Clear precedence rules: Q object must be on left side when combining with SQLAlchemy expressions
- Supports both single and multiple expressions with automatic AND combination

## Query Patterns

### Chainable Query Methods (Return QuerySet)

```python
# Filtering and exclusion using Q objects and SQLAlchemy expressions
users = User.objects.filter(User.age >= 18)  # Returns QuerySet
active_users = User.objects.exclude(User.is_active == False)  # Returns QuerySet

# Complex queries with Q objects and SQLAlchemy expressions
from sqlobjects.queries import Q

query = Q(User.age >= 18) & (Q(User.username == "john") | Q(User.username == "jane"))
users = User.objects.filter(query)  # Returns QuerySet
users = User.objects.filter(User.age >= 18)  # Returns QuerySet

# Ordering and limiting
ordered_users = User.objects.order_by('-created_at')  # Returns QuerySet
limited_users = User.objects.limit(10)  # Returns QuerySet
offset_users = User.objects.offset(20)  # Returns QuerySet

# Relationship loading
users_with_profile = User.objects.select_related('profile')  # Returns QuerySet
users_with_posts = User.objects.prefetch_related('posts')  # Returns QuerySet

# Field selection and annotations
user_subset = User.objects.only('id', 'username')  # Returns QuerySet
deferred_users = User.objects.defer('password_hash')  # Returns QuerySet
annotated_users = User.objects.annotate(post_count=func.count(User.posts))  # Returns QuerySet

# Joins and advanced operations
joined_query = User.objects.join(Profile, User.id == Profile.user_id)  # Returns QuerySet
distinct_users = User.objects.distinct('department')  # Returns QuerySet
grouped_users = User.objects.group_by('department')  # Returns QuerySet
filtered_groups = User.objects.having(func.count() > 5)  # Returns QuerySet

# Locking and options
locked_users = User.objects.select_for_update()  # Returns QuerySet
from sqlalchemy.orm import joinedload
optimized_users = User.objects.options(joinedload(User.profile))  # Returns QuerySet

# Set operations (return QuerySet for chaining)
active_users = User.objects.filter(is_active=True)
inactive_users = User.objects.filter(is_active=False)
reversed_users = User.objects.reverse()  # Returns QuerySet
empty_users = User.objects.none()  # Returns QuerySet
```

### Terminal Query Methods (Execute Query)

```python
# Basic execution methods
users = await User.objects.filter(age__gte=18).all()  # Returns list[User]
user = await User.objects.get(id=1)  # Returns User or raises exception
first_user = await User.objects.first()  # Returns User | None
last_user = await User.objects.last()  # Returns User | None

# Using specific database session
user = await User.objects.get(username="john", session=analytics_session)
users = await User.objects.filter(is_active=True).all(session=main_session)

# Ordering-based retrieval
earliest = await User.objects.earliest('created_at')  # Returns User | None
latest = await User.objects.latest('created_at')  # Returns User | None

# Iterator for large datasets
async for user in User.objects.iterator():  # Async generator
    print(user.username)
# Or with custom memory cleanup interval
async for user in User.objects.iterator(memory_cleanup_interval=500):
    print(user.username)

# Index/slice access
first_user = await User.objects.get_item(0)  # Returns User
first_10_users = await User.objects.get_item(slice(0, 10))  # Returns list[User]
fifth_user = await User.objects.get_item(4)  # Returns User

# Date/datetime extraction
date_list = await User.objects.dates('created_at', 'month', order='DESC')  # Returns list[date]
datetime_list = await User.objects.datetimes('created_at', 'day', order='ASC')  # Returns list[datetime]

# Counting and existence
user_count = await User.objects.count()  # Returns int
has_users = await User.objects.exists()  # Returns bool

# Value extraction
user_data = await User.objects.values('id', 'username', 'email')  # Returns list[dict]
user_names = await User.objects.values_list('username', flat=True)  # Returns list[str]

# Aggregation
results = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg('age')
)  # Returns dict[str, Any]

# Update and delete operations with unified parameter structure
affected_rows = await User.objects.update(
    values={"last_seen": datetime.now()},
    filter=Q(age__gte=18),
    is_active=True  # Simple condition combined with filter using AND
)  # Returns int
deleted_rows = await User.objects.delete(
    filter=Q(created_at__lt=cutoff_date),
    is_active=False  # Simple condition
)  # Returns int

# Exists method with unified parameter structure
exists = await User.objects.exists(
    filter=Q(username__icontains="admin"),
    is_active=True,
    session=analytics_session
)  # Returns bool

# Bulk operations for performance
mappings = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
affected_rows = await User.objects.bulk_update(mappings, match_fields=["id"])  # Returns int
deleted_rows = await User.objects.bulk_delete([1, 2, 3], id_field="id")  # Returns int

# Set operations (execute immediately)
all_users = await active_users.union(inactive_users)  # Returns list[User]
common_users = await active_users.intersection(inactive_users)  # Returns list[User]
diff_users = await active_users.difference(inactive_users)  # Returns list[User]

# Advanced query methods
date_list = await User.objects.dates('created_at', 'month', order='DESC')  # Returns list[date]
datetime_list = await User.objects.datetimes('created_at', 'day', order='ASC')  # Returns list[datetime]
explain_result = await User.objects.filter(age__gte=18).explain(analyze=True)  # Returns dict
raw_users = await User.objects.raw("SELECT * FROM users WHERE age > :age", {"age": 18})  # Returns list[User]

# Iterator for large datasets
async for user in User.objects.filter(is_active=True).iterator():
    print(user.username)  # Async generator

# Index/slice access
first_10_users = await User.objects.get_item(slice(0, 10))  # Returns list[User]
fifth_user = await User.objects.get_item(4)  # Returns User
```

### Subquery Operations

```python
from sqlobjects.expressions import SubqueryExpression

# Subquery creation (returns SubqueryExpression, not QuerySet)
active_users_subq = User.objects.filter(is_active=True).subquery("active_users")
avg_age_subq = User.objects.aggregate(avg_age=func.avg("age")).subquery(query_type="scalar")
exists_subq = Post.objects.filter(author_id=F("id")).subquery(query_type="exists")

# Using subqueries in queries
results = await Post.objects.join(active_users_subq, Post.author_id == active_users_subq.c.id).all()
older_users = await User.objects.filter(F("age") > avg_age_subq).all()
users_with_posts = await User.objects.filter(exists_subq).all()

# Automatic type inference (recommended)
user_count_subq = User.objects.annotate(count=func.count()).subquery()  # Auto-inferred as scalar
user_list_subq = User.objects.only("id", "username").subquery()  # Auto-inferred as table
```

## Expression System Rules

### 1. F Class - Field References with Instance Methods

```python
from sqlobjects.expressions import F, func

# Field references
price_field = F("price")
total_expr = F("price") * F("quantity")

# Chainable instance methods for single-field operations
upper_name = F("name").upper()
trimmed_name = F("name").trim()
rounded_price = F("price").round(2)

# Aggregate methods on F instances
total_sales = F("amount").sum()
avg_rating = F("rating").avg()
max_score = F("score").max()

# String operations
substring = F("description").substr(1, 10)
replaced = F("text").replace("old", "new")
concatenated = F("first_name").concat_with(" ", F("last_name"))

# Math operations
absolute = F("value").abs()
square_root = F("area").sqrt()
power = F("base") ** 2  # Uses __pow__ operator

# Date/time extraction
year_part = F("created_at").year()
month_part = F("created_at").month()

# Type conversion
string_id = F("id").to_string()
integer_code = F("code").to_integer()
decimal_price = F("price").to_decimal(10, 2)
```

### 2. func Object - Multi-Field and Database Functions

```python
from sqlobjects.expressions import func

# Multi-field operations
full_name = func.concat(F("first_name"), " ", F("last_name"))
total_amount = func.sum(F("price") * F("quantity"))

# Database functions
current_time = func.now()
current_date = func.current_date()

# Aggregations with multiple expressions
avg_total = func.avg(F("price") * F("quantity"))
max_date = func.max(F("created_at"))

# Conditional functions
first_non_null = func.coalesce(F("nickname"), F("username"), "Anonymous")
null_if_zero = func.nullif(F("value"), 0)

# Case expressions with enhanced syntax
status = func.case(
    (F("score") >= 90, "A"),
    (F("score") >= 80, "B"),
    (F("score") >= 70, "C"),
    else_="F"
)

# Dictionary syntax for case expressions
grade = func.case({
    F("score") >= 90: "Excellent",
    F("score") >= 80: "Good",
    F("score") >= 70: "Average"
}, else_="Poor")

# Window functions
row_num = func.row_number()
rank_val = func.rank()
lag_value = func.lag(F("salary"), 1)

# SQLAlchemy compatibility - automatic fallback
any_sqlalchemy_func = func.custom_db_function(F("field"), param=value)
```

### 3. Window Functions

```python
# Window functions with F class
window_sum = F("amount").sum().window().partition_by("department").order_by("-created_at")
row_number = func.row_number().window().order_by("-salary")

# Complex window expressions
running_total = F("amount").sum().window().partition_by("category").order_by("date")
rank_in_dept = func.rank().window().partition_by("department_id").order_by("-salary")

# Use in queries
employees = await Employee.objects.annotate(
    row_number=func.row_number().window().order_by("-salary"),
    department_rank=func.rank().window().partition_by("department_id").order_by("-salary"),
    running_total=F("salary").sum().window().partition_by("department_id").order_by("hire_date")
).all()
```

### 4. Mixed Usage Support

```python
# F expressions and Model.field can be mixed
from myapp.models import User

# Both patterns work seamlessly
full_name1 = func.concat(F("first_name"), " ", User.last_name)
full_name2 = func.concat(User.first_name, " ", F("last_name"))

# In aggregations
total_with_bonus = func.sum(F("salary") + User.bonus)
avg_age = func.avg(User.age)

# In case expressions
status = func.case(
    (F("is_active") == True, "Active"),
    (User.is_suspended == True, "Suspended"),
    else_="Inactive"
)
```

### 5. Raw SQLAlchemy Integration

```python
from sqlobjects.expressions import RawExpression
from sqlalchemy import text, func as sa_func

# Wrap raw SQLAlchemy expressions
raw_timestamp = RawExpression(text("CURRENT_TIMESTAMP"))
complex_json = RawExpression(sa_func.json_extract(F("data"), "$.key"))

# Use in queries
users = await User.objects.annotate(
    current_time=RawExpression(text("NOW()")),
    json_value=RawExpression(sa_func.json_extract(F("metadata"), "$.name"))
).all()

# For complex database-specific functions
postgres_array = RawExpression(sa_func.array_agg(F("tags")))
mysql_group_concat = RawExpression(sa_func.group_concat(F("names")))
```

## Batch Operations Best Practices

### 1. Update Operations

```python
# Conditional updates with explicit values parameter
await User.objects.update(
    values={"status": "active", "last_seen": datetime.now()},
    is_active=True,
    department="IT"
)

# Complex conditions with Q objects and F expressions
await User.objects.update(
    values={"status": "premium"},
    Q(subscription_type="paid") | Q(is_vip=True),
    F("account_balance") > 1000
)

# True bulk update for large datasets (10-100x faster)
mappings = [
    {"id": 1, "name": "Alice", "email": "alice@new.com"},
    {"id": 2, "name": "Bob", "email": "bob@new.com"},
    # ... thousands of records
]
await User.objects.bulk_update(
    mappings, 
    match_fields=["id"],
    batch_size=1000  # Process in batches
)

# Multi-field matching
mappings = [
    {"username": "alice", "email": "alice@old.com", "new_email": "alice@new.com"},
    {"username": "bob", "email": "bob@old.com", "new_email": "bob@new.com"}
]
await User.objects.bulk_update(
    mappings,
    match_fields=["username", "email"]  # Match on multiple fields
)
```

### 2. Delete Operations

```python
# Conditional deletes with complex conditions using Q objects, F expressions, and SQLAlchemy expressions
await User.objects.delete(
    Q(is_active=False) & Q(last_login__lt=datetime.now() - timedelta(days=365)),
    User.account_type == "trial"
)

# Using F expressions and SQLAlchemy expressions for dynamic conditions
await User.objects.delete(
    F("created_at") < datetime.now() - timedelta(days=30),
    F("login_count") == 0
)

# True bulk delete for large ID lists (10-100x faster)
user_ids = [1, 2, 3, 4, 5, ...]  # Thousands of IDs
await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000  # Process in batches to avoid query size limits
)

# Bulk delete with custom field
inactive_usernames = ["user1", "user2", "user3", ...]
await User.objects.bulk_delete(
    inactive_usernames,
    id_field="username"
)
```

### 3. Performance Comparison

| Operation | Method          | Performance    | Use Case                          |
|-----------|-----------------|----------------|-----------------------------------|
| Update    | `update()`      | Standard       | Complex conditions, moderate data |
| Update    | `bulk_update()` | 10-100x faster | Large datasets, simple matching   |
| Delete    | `delete()`      | Standard       | Complex conditions, moderate data |
| Delete    | `bulk_delete()` | 10-100x faster | Large ID lists, simple matching   |

### 4. Batch Size Guidelines

```python
# Recommended batch sizes by database
postgresql_batch_size = 1000  # PostgreSQL handles larger batches well
mysql_batch_size = 500        # MySQL prefers smaller batches
sqlite_batch_size = 100       # SQLite has lower limits

# Adjust based on record size
small_records_batch = 2000    # Simple fields (id, name, status)
large_records_batch = 200     # Complex fields (JSON, text, binary)

# Example usage
await User.objects.bulk_update(
    large_mappings,
    match_fields=["id"],
    batch_size=postgresql_batch_size if db_type == "postgresql" else mysql_batch_size
)
```

### 5. Error Handling and Transactions

```python
# Bulk operations with transaction control
try:
    async with ctx_session() as session:
        # All operations in single transaction
        await User.objects.bulk_update(mappings, session=session)
        await User.objects.bulk_delete(old_ids, session=session)
        await session.commit()
except Exception as e:
    # Transaction automatically rolled back
    logger.error(f"Bulk operation failed: {e}")

# Manual commit control
affected = await User.objects.bulk_update(
    mappings,
    commit=False  # Don't auto-commit
)
if affected > 0:
    await session.commit()
else:
    await session.rollback()
```