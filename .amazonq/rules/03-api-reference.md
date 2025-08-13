# SQLObjects API Reference

## API Design Rules

### 1. Session Management Pattern

SQLObjects uses the `using()` method pattern for session specification:

```python
# Default session usage
user = await User.objects.create(username="john")

# Specific session usage
user = await User.objects.using(session).create(username="john")
user = await User.objects.using("database_name").create(username="john")
```

**Key Principles:**

- **using() Method**: Returns ObjectsManager or ModelProxy bound to specific session
- **Flexible Session Types**: Accepts AsyncSession instances or database names
- **Multi-database Support**: Easy to specify which database to use
- **Clean API**: No session parameters cluttering method signatures
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
query = User.objects.filter(User.is_active == True).order_by("-created_at").limit(10)

# Query execution
users = await query.all()
user = await User.objects.get(User.username == "john")
count = await User.objects.filter(User.is_active == True).count()

# With specific session
users = await User.objects.using(analytics_session).filter(User.is_active == True).all()
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

## Model Instance Operation API

### 1. Smart save() Method API

```python
# Smart save() method with automatic CREATE/UPDATE detection
async def save(self, validate: bool = True) -> None:
    """Save instance with intelligent operation detection.
    
    Automatically detects whether to perform CREATE or UPDATE based on
    primary key values. Supports detached instances through merge() strategy.
    
    Args:
        validate: Whether to execute validation before saving
    
    Raises:
        ValidationError: If validation fails
        IntegrityError: If database constraints are violated
    """

# Usage examples
# New instance - automatically detected as CREATE
user = User(name="John", email="john@example.com")
await user.save()  # Executes INSERT operation

# Existing instance - automatically detected as UPDATE  
user.name = "Jane"
await user.save()  # Executes UPDATE operation

# Detached instance with primary key - intelligently handled as UPDATE
detached_user = User(id=1, name="Alice", email="alice@example.com")
await detached_user.save()  # Uses merge() for UPDATE semantics

# With specific session using ModelProxy
await user.using(session).save()
await detached_user.using("analytics").save()
```

### 2. Detached Instance Operations API

```python
# delete() method supports detached instances
async def delete(self) -> None:
    """Delete instance, supporting both attached and detached instances.
    
    For detached instances, automatically attaches to session using merge()
    before deletion.
    
    Raises:
        DoesNotExist: If instance doesn't exist in database
    """

# Usage examples
# Delete attached instance
user = await User.objects.get(User.id == 1)
await user.delete()

# Delete detached instance
detached_user = User(id=1)
await detached_user.delete()  # Automatically attaches to session

# With specific session
await detached_user.using(session).delete()
```

### 3. Unified refresh() Method API

```python
# Unified refresh() method replacing both refresh() and refresh_from_db()
async def refresh(self, fields: list[str] = None) -> None:
    """Refresh instance data from database.
    
    Supports both full refresh and selective field refresh.
    Handles both attached and detached instances.
    
    Args:
        fields: List of field names to refresh. If None, refreshes all fields.
    
    Raises:
        DoesNotExist: If instance doesn't exist in database
        ValueError: If instance has no primary key values
    """

# Usage examples
# Full refresh (replaces original refresh_from_db())
user = await User.objects.get(User.id == 1)
user.name = "Modified"
await user.refresh()  # Resets all fields to database state

# Selective field refresh
await user.refresh(fields=["name", "updated_at"])  # Only refresh specified fields

# Detached instance refresh
detached_user = User(id=1)
await detached_user.refresh()  # Loads data via direct query

# With specific session
await user.using(session).refresh()
await detached_user.using("analytics").refresh(fields=["name"])
```

### 4. ModelProxy Session Binding API

```python
# using() method returns ModelProxy for session binding
def using(self, db_or_session: str | AsyncSession) -> "ModelProxy":
    """Return a proxy bound to specific database/session.
    
    Args:
        db_or_session: Database name string or AsyncSession instance
    
    Returns:
        ModelProxy instance bound to the specified session
    """

# Usage examples
# Bind to specific session
user = User(name="John")
proxy = user.using(session)
await proxy.save()

# Bind to database by name
proxy = user.using("analytics")
await proxy.save()

# Chain operations with session binding
user = User(name="Alice")
await user.using(session).save()
user.name = "Alice Updated"
await user.using(session).save()
await user.using(session).delete()

# ModelProxy preserves all model functionality
proxy = user.using(session)
proxy.name = "New Name"  # Attribute access
user_dict = proxy.to_dict()  # Method access
await proxy.refresh(fields=["name"])  # Enhanced methods
```

### 5. Primary Key Detection API

```python
# Internal method for primary key detection (used by smart save())
def _has_primary_key_values(self) -> bool:
    """Check if instance has primary key values.
    
    Supports both single and composite primary keys.
    
    Returns:
        True if all primary key fields have non-None values
    """

# Usage in smart save() logic
if self._has_primary_key_values():
    # Has primary key: use merge() for UPDATE semantics
    merged_instance = await session.merge(instance)
    self._update_instance(merged_instance)
else:
    # No primary key: use add() for CREATE semantics
    session.add(instance)
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

- `column(type="binary", length=255)` for variable-length binary data
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
- `binary_column("rbinary")` for binary data with type variants

#### Type System Features

- **Automatic Type Handling**: The system automatically handles SQLAlchemy type creation
- **Type Aliases**: Common aliases are supported (`str` → `string`, `int` → `integer`, etc.)
- **Special Types**: Array and enum types have enhanced syntax for easier usage
- **Custom Types**: Support for registering custom field types when needed

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
image_data: Column[bytes] = binary_column(type="binary", length=2048)


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

# Relationship loading - string syntax (supported)
users_with_profile = User.objects.select_related('profile')  # Returns QuerySet
users_with_posts = User.objects.prefetch_related('posts')  # Returns QuerySet

# Relationship loading - SQLAlchemy expression syntax (recommended)
users_with_profile = User.objects.select_related(User.profile)  # Returns QuerySet
users_with_posts = User.objects.prefetch_related(User.posts)  # Returns QuerySet

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
# Using SQLObjects relationship loading (recommended)
optimized_users = User.objects.select_related(User.profile)  # Returns QuerySet

# Or using SQLAlchemy options directly
from sqlalchemy.orm import joinedload
optimized_users = User.objects.options(joinedload(User.profile))  # Returns QuerySet

# Set operations (return QuerySet for chaining)
active_users = User.objects.filter(User.is_active == True)
inactive_users = User.objects.filter(User.is_active == False)
reversed_users = User.objects.reverse()  # Returns QuerySet
empty_users = User.objects.none()  # Returns QuerySet
```

### Terminal Query Methods (Execute Query)

```python
# Basic execution methods
users = await User.objects.filter(User.age >= 18).all()  # Returns list[User]
user = await User.objects.get(User.id == 1)  # Returns User or raises exception
first_user = await User.objects.first()  # Returns User | None
last_user = await User.objects.last()  # Returns User | None

# Using specific database session
user = await User.objects.using(analytics_session).get(User.username == "john")
users = await User.objects.using(main_session).filter(User.is_active == True).all()

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

# Update and delete operations (use QuerySet methods)
affected_rows = await User.objects.filter(User.age >= 18).update(
    last_seen=datetime.now()
)  # Returns int
deleted_rows = await User.objects.filter(
    User.created_at < cutoff_date
).delete()  # Returns int

# Exists method
exists = await User.objects.using(analytics_session).filter(
    User.username.like("%admin%")
).exists()  # Returns bool

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
explain_result = await User.objects.filter(User.age >= 18).explain(analyze=True)  # Returns dict
raw_users = await User.objects.raw("SELECT * FROM users WHERE age > :age", {"age": 18})  # Returns list[User]

# Iterator for large datasets
async for user in User.objects.filter(User.is_active == True).iterator():
    print(user.username)  # Async generator

# Index/slice access
first_10_users = await User.objects.get_item(slice(0, 10))  # Returns list[User]
fifth_user = await User.objects.get_item(4)  # Returns User
```

### Subquery Operations

```python
from sqlobjects.expressions import SubqueryExpression

# Subquery creation (returns SubqueryExpression, not QuerySet)
active_users_subq = User.objects.filter(User.is_active == True).subquery("active_users")
avg_age_subq = User.objects.aggregate(avg_age=func.avg("age")).subquery(query_type="scalar")
exists_subq = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")

# Using subqueries in queries
results = await Post.objects.join(active_users_subq, Post.author_id == active_users_subq.c.id).all()
older_users = await User.objects.filter(User.age > avg_age_subq).all()
users_with_posts = await User.objects.filter(exists_subq).all()

# Automatic type inference (recommended)
user_count_subq = User.objects.annotate(count=func.count()).subquery()  # Auto-inferred as scalar
user_list_subq = User.objects.only("id", "username").subquery()  # Auto-inferred as table
```

## Expression System Rules

### 1. func Object - Database Functions

```python
from sqlobjects.expressions import func

# Multi-field operations
full_name = func.concat(User.first_name, " ", User.last_name)
total_amount = func.sum(User.price * User.quantity)

# Database functions
current_time = func.now()
current_date = func.current_date()

# Aggregations with multiple expressions
avg_total = func.avg(User.price * User.quantity)
max_date = func.max(User.created_at)

# Conditional functions
first_non_null = func.coalesce(User.nickname, User.username, "Anonymous")
null_if_zero = func.nullif(User.value, 0)

# Case expressions with enhanced syntax
status = func.case(
    (User.score >= 90, "A"),
    (User.score >= 80, "B"),
    (User.score >= 70, "C"),
    else_="F"
)

# Dictionary syntax for case expressions
grade = func.case({
    User.score >= 90: "Excellent",
    User.score >= 80: "Good",
    User.score >= 70: "Average"
}, else_="Poor")

# Window functions
row_num = func.row_number()
rank_val = func.rank()
lag_value = func.lag(User.salary, 1)

# SQLAlchemy compatibility - automatic fallback
any_sqlalchemy_func = func.custom_db_function(User.field, param=value)
```

### 2. Window Functions

```python
# Window functions
row_number = func.row_number().over(order_by=User.salary.desc())
rank_in_dept = func.rank().over(partition_by=User.department_id, order_by=User.salary.desc())

# Use in queries
employees = await Employee.objects.annotate(
    row_number=func.row_number().over(order_by=Employee.salary.desc()),
    department_rank=func.rank().over(partition_by=Employee.department_id, order_by=Employee.salary.desc())
).all()
```

### 3. Raw SQLAlchemy Integration

```python
from sqlalchemy import text, func as sa_func

# Use raw SQLAlchemy expressions directly
users = await User.objects.annotate(
    current_time=text("NOW()"),
    json_value=sa_func.json_extract(User.metadata, "$.name")
).all()

# For complex database-specific functions
postgres_array = sa_func.array_agg(User.tags)
mysql_group_concat = sa_func.group_concat(User.names)
```

## Advanced Instance Operations

### 1. Composite Primary Key Support

```python
# Smart save() works with composite primary keys
class OrderItem(ObjectModel):
    order_id: Column[int] = int_column(primary_key=True)
    product_id: Column[int] = int_column(primary_key=True)
    quantity: Column[int] = int_column()
    
# Detached instance with composite primary key
order_item = OrderItem(order_id=1, product_id=2, quantity=5)
await order_item.save()  # Intelligently detects composite primary key

# Primary key detection logic handles composite keys
def _has_primary_key_values(self) -> bool:
    """Supports both single and composite primary keys"""
    for pk_col in self.__table__.primary_key.columns:
        if getattr(self, pk_col.name, None) is None:
            return False
    return len(self.__table__.primary_key.columns) > 0
```

### 2. Error Handling for Instance Operations

```python
# Proper error handling for enhanced instance operations

try:
    # Smart save with validation
    detached_user = User(id=1, email="invalid-email")
    await detached_user.save(validate=True)
except ValidationError as e:
    print(f"Validation failed: {e.message}")
except IntegrityError as e:
    print(f"Database constraint violation: {e}")

try:
    # Delete detached instance
    user_to_delete = User(id=999)  # Non-existent ID
    await user_to_delete.delete()
except DoesNotExist as e:
    print(f"User not found: {e}")

try:
    # Refresh detached instance without primary key
    invalid_user = User(name="No ID")
    await invalid_user.refresh()
except ValueError as e:
    print(f"Cannot refresh without primary key: {e}")

# Graceful handling of detached instance operations
async def safe_detached_operation(user_id: int, user_data: dict):
    try:
        detached_user = User(id=user_id, **user_data)
        await detached_user.save()
        return detached_user
    except DoesNotExist:
        # Handle case where user doesn't exist for UPDATE
        new_user = User(**user_data)
        await new_user.save()  # CREATE instead
        return new_user
    except ValidationError as e:
        # Handle validation errors
        logger.error(f"Validation failed for user {user_id}: {e.message}")
        raise
```

## get_or_create 和 update_or_create 信号集成

从 v1.1 开始，`get_or_create` 和 `update_or_create` 方法已集成信号机制，通过调用模型实例的 `save()` 方法来触发相应信号：

### 1. get_or_create 信号集成

```python
# get_or_create 现在会触发信号
user, created = await User.objects.get_or_create(
    username="john",  # 查找条件
    defaults={"email": "john@example.com"}  # 创建时的默认值
)
# 如果创建新用户，会触发：
# before_save → before_create → 数据库操作 → after_save → after_create

# 使用特定会话
user, created = await User.objects.using(session).get_or_create(
    username="john",
    defaults={"email": "john@example.com"}
)
```

### 2. update_or_create 信号集成

```python
# update_or_create 现在会触发信号
user, created = await User.objects.update_or_create(
    username="john",  # 查找条件
    defaults={"last_login": datetime.now()}  # 更新/创建时的值
)
# 如果更新现有用户，会触发：
# before_save → before_update → 数据库操作 → after_save → after_update
# 如果创建新用户，会触发：
# before_save → before_create → 数据库操作 → after_save → after_create

# 复杂条件查找
user, created = await User.objects.update_or_create(
    username="john",
    is_active=True,  # 多个查找条件
    defaults={"last_login": datetime.now()}
)
```

### 3. 实现原理

**修改前的实现：**
```python
# get_or_create 直接调用 create() 方法
obj = await self.create(validate=validate, **create_data)

# update_or_create 手动处理信号
context = SignalContext(...)
await obj._emit_signal("before", context)
# ... 手动设置属性和验证
await self._session.flush()
await obj._emit_signal("after", context)
```

**修改后的实现：**
```python
# 两个方法都使用实例的 save() 方法
obj = self._model(**create_data)
await obj.using(self._session).save(validate=validate)
```

### 4. 信号触发优势

- **一致性**：与直接调用 `save()` 方法具有相同的信号行为
- **智能检测**：`save()` 方法自动检测创建或更新操作
- **完整验证**：执行完整的验证流程（字段级和模型级）
- **代码复用**：消除重复的信号处理代码
- **向后兼容**：API 接口保持不变，现有代码无需修改

## Batch Operations Best Practices

### 1. Update Operations

```python
# Conditional updates with values parameter
await User.objects.filter(
    is_active=True,
    department="IT"
).update(values={"status": "active", "last_seen": datetime.now()})

# Complex conditions with Q objects and SQLAlchemy expressions
await User.objects.update(
    values={"status": "premium"},
    Q(subscription_type="paid") | Q(is_vip=True),
    User.account_balance > 1000
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
# Conditional deletes with complex conditions using Q objects and SQLAlchemy expressions
await User.objects.filter(
    Q(is_active=False) & Q(last_login < datetime.now() - timedelta(days=365)),
    User.account_type == "trial"
).delete()

# Using SQLAlchemy expressions for dynamic conditions
await User.objects.filter(
    User.created_at < datetime.now() - timedelta(days=30),
    User.login_count == 0
).delete()

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
        await User.objects.using(session).bulk_update(mappings)
        await User.objects.using(session).bulk_delete(old_ids)
        await session.commit()
except Exception as e:
    # Transaction automatically rolled back
    logger.error(f"Bulk operation failed: {e}")

# Manual commit control with using() method
async with ctx_session() as session:
    affected = await User.objects.using(session).bulk_update(mappings)
    if affected > 0:
        await session.commit()
    else:
        await session.rollback()
```

## Instance Operation Best Practices

### 1. Smart save() Usage Patterns

```python
# Recommended patterns for different scenarios

# API update endpoints - detached instances
@app.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate):
    # Create detached instance with primary key
    user = User(id=user_id, **user_data.dict())
    # save() automatically detects as UPDATE
    await user.save()
    return user

# Data synchronization - batch detached instances
async def sync_users_from_external_api():
    external_users = await fetch_users_from_external_api()
    
    async with ctx_session() as session:
        for user_data in external_users:
            # Create detached instance with primary key
            user = User(id=user_data['id'], **user_data)
            # Uses merge() strategy for upsert behavior
            await user.using(session).save()

# New record creation - standard pattern
async def create_new_user(user_data: dict):
    user = User(**user_data)  # No primary key
    await user.save()  # Automatically detected as CREATE
    return user
```

### 2. Detached Instance Best Practices

```python
# Working with detached instances effectively

# Partial updates with selective refresh
detached_user = User(id=1, name="Updated Name")
await detached_user.save()  # Update only changed fields
# Refresh only specific fields to get latest data
await detached_user.refresh(fields=["updated_at", "version"])

# Cross-database operations
user_data = {"id": 1, "name": "John", "email": "john@example.com"}
async with ctx_sessions("main", "analytics") as sessions:
    # Same data to multiple databases
    main_user = User(**user_data)
    analytics_user = User(**user_data)
    
    await main_user.using(sessions["main"]).save()
    await analytics_user.using(sessions["analytics"]).save()

# Batch operations with detached instances
async def batch_update_detached():
    updates = [
        {"id": 1, "name": "Alice Updated"},
        {"id": 2, "name": "Bob Updated"},
        {"id": 3, "name": "Charlie Updated"},
    ]
    
    async with ctx_session() as session:
        tasks = []
        for update_data in updates:
            user = User(**update_data)
            task = asyncio.create_task(user.using(session).save())
            tasks.append(task)
        
        await asyncio.gather(*tasks)
```

### 3. Session Management Best Practices

```python
# Effective session management with instance operations

# Long-running operations with session control
async def process_user_batch(user_ids: list[int]):
    async with ctx_session() as session:
        for user_id in user_ids:
            # Load user
            user = await User.objects.using(session).get(User.id == user_id)
            
            # Process user
            await process_user_logic(user)
            
            # Save changes
            await user.using(session).save()
            
            # Refresh to get latest state
            await user.using(session).refresh(fields=["status", "updated_at"])

# Mixed attached/detached operations
async def mixed_operations_example():
    async with ctx_session() as session:
        # Work with attached instance
        user = await User.objects.using(session).get(User.id == 1)
        user.name = "Updated via attached"
        await user.save()  # Uses existing session
        
        # Work with detached instance
        detached_user = User(id=2, name="Updated via detached")
        await detached_user.using(session).save()  # Explicit session binding
        
        # Both operations in same transaction
        await session.commit()
```