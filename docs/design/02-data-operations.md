# SQLObjects Data Operations Design Documentation

## Overview

The SQLObjects data operations module adopts a composite pattern architecture, providing Django-style database operation
interfaces. It implements high-performance database access through ObjectsDescriptor descriptors, composite QuerySet,
and unified QueryExecutor.

## Core Features

### 1. Descriptor Pattern Objects Manager

Automatically provides independent ObjectsManager instances for each model class through ObjectsDescriptor descriptors:

```python
# ObjectsDescriptor automatic setup
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
# Auto-setup: User.objects = ObjectsDescriptor(User)

# ObjectsDescriptor returns new ObjectsManager instance on each User.objects access
# Query operations return ObjectModel instance or instance lists
users = await User.objects.all()  # Returns list[User]
user = await User.objects.get(User.name == "John")  # Returns User instance
first_user = await User.objects.first()  # Returns User instance or None

# Chained queries - ObjectsManager methods return QuerySet
active_users = await User.objects.filter(
    User.age >= 18
).order_by("name").limit(10).all()

# Session binding - returns new ObjectsManager instance
bound_manager = User.objects.using("analytics")
analytics_users = await bound_manager.all()
```

### 2. Composite Pattern QuerySet Architecture

QuerySet uses composite pattern, implemented through QueryBuilder and QueryExecutor components:

```python
# QuerySet composite components
class QuerySet:
    def __init__(self, table, model_class, db_or_session=None):
        self._builder = QueryBuilder(model_class)      # Query building
        self._executor = QueryExecutor(db_or_session)   # Unified execution

# Chained building - each method returns new QuerySet instance
query = User.objects.filter(User.is_active == True)  # New QuerySet
query = query.filter(User.age >= 18)                 # New QuerySet
query = query.order_by(User.name)                    # New QuerySet
users = await query.all()  # Execute query

# Q object logical composition - supports SQLAlchemy expressions
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# Component sharing - new QuerySet shares executor
new_qs = query.filter(User.department == "IT")
# new_qs._executor and query._executor are the same instance
```

### 3. CRUD Operations

Complete Create, Read, Update, Delete operations support:

```python
# Create
user = await User.objects.create(name="Alice", age=25)

# Read
user = await User.objects.get(User.id == 1)
users = await User.objects.filter(User.age >= 18).all()

# Update
await User.objects.filter(User.id == 1).update(age=26)

# Delete
await User.objects.filter(User.id == 1).delete()
```

### 4. Signal Integration with Batch Processing

Batch operations use @emit_signals decorator to integrate signal system, supporting bulk signal emission:

```python
# Bulk create - automatically emits before_bulk_create/after_bulk_create signals
@emit_signals(Operation.SAVE, is_bulk=True)
async def bulk_create(self, objects):
    # Actual implementation uses SQLAlchemy Core insert
    stmt = insert(self._table).values(objects)
    await session.execute(stmt)

users_data = [
    {"name": "Alice", "age": 25},
    {"name": "Bob", "age": 30}
]
await User.objects.bulk_create(users_data)

# Bulk update - uses bindparam and batch processing
@emit_signals(Operation.SAVE, is_bulk=True)
async def bulk_update(self, mappings, match_fields=["id"], batch_size=1000):
    # Uses SQLAlchemy Core update + bindparam
    # Supports batch processing and parameter binding
    pass

update_data = [
    {"id": 1, "age": 26},
    {"id": 2, "age": 31}
]
affected_rows = await User.objects.bulk_update(update_data, match_fields=["id"])

# Bulk delete - uses IN clause and batch processing
deleted_rows = await User.objects.bulk_delete([1, 2, 3], batch_size=1000)
```

## Module Architecture

### Core Components

**Manager Layer**

- **ObjectsDescriptor**: Descriptor pattern, provides independent ObjectsManager instances for each model class
- **ObjectsManager**: Django-style database operations manager, supports session binding and bulk operations

**Query Building Layer**

- **QuerySet**: Composite pattern query builder, integrates QueryBuilder and QueryExecutor
- **QueryBuilder**: Immutable query builder, handles SQL construction and query optimization
- **Q**: SQLAlchemy expression logical combiner, supports AND/OR/NOT complex conditions

**Execution Layer**

- **QueryExecutor**: Unified query execution engine, supports multiple query types, iterators and lazy loading

**Expressions Subsystem (`expressions/`)**

The `expressions/` package supplies the composable SQL expression objects that the query pipeline builds on. Each module contributes one family of expressions:

- **window.py**: Window functions (`WindowFunction` base with `RowNumberFunction`, `RankFunction`, `DenseRankFunction`, `PercentRankFunction`, `NtileFunction`, `LagFunction`, `LeadFunction`, `FirstValueFunction`, `LastValueFunction`, `NthValueFunction`) plus `WindowSpec`. A window function is created via `func.row_number()`, `func.rank()`, etc., configured with `.over(partition_by=..., order_by=..., rows=..., range_=...)`, and used as an annotation: `User.objects.annotate(rank=func.rank().over(order_by=[User.age])).all()`. Window functions cannot be executed directly.
- **cte.py**: `CTEExpression` for Common Table Expressions. The entry points are `QuerySet.cte(name, recursive=False)` (turns the current QuerySet into a CTE) and `QuerySet.with_cte(*ctes)` (uses one or more CTEs in a query); recursive CTEs are supported via `recursive=True` and `union_all`.
- **subquery.py**: `SubqueryExpression` for correlated and standalone subqueries.
- **scalar.py**: Scalar-returning expressions (`ScalarSubquery`, `CountExpression`, `ExistsExpression`).
- **aggregate.py**: `AggregateExpression` for aggregate functions used in `annotate()`/`aggregate()`.
- **function.py**: The `func` factory (`FunctionExpression`), a type-safe wrapper over SQLAlchemy functions that also exposes the window-function constructors; `func.raw(name, *args)` builds arbitrary SQL functions.
- **explain.py**: `ExplainResult`, the string-valued result of query plan inspection (see document 05).
- **terminal.py**: Terminal expression helpers backing execution methods such as `all`, `first`, `last`, `earliest`, `latest`, `values`, `values_list`, `dates`, `datetimes`, and `get_item`.

### Design Philosophy

**Descriptor Pattern**: Provides independent manager instances for each model class through ObjectsDescriptor
**Composite Architecture**: QuerySet avoids MRO issues through component composition, improving maintainability
**Immutable Building**: QueryBuilder immutable design, each method returns new instance
**Component Sharing**: New QuerySet instances share executor, improving performance
**Unified Execution**: QueryExecutor single execution method handles all query types
**Signal Integration**: Bulk operations use @emit_signals decorator to integrate signal system
**Session Management**: Supports using() method for session binding and readonly parameter control

### Integration with Other Modules

**Core Architecture Module**: Obtains database sessions through the module-level session context (`ctx_session`/`get_session`)
**Field System Module**: Supports field expressions and function calls
**Relationship Processing Module**: Integrates select_related and prefetch_related

## API Reference

### Objects Manager

```python
# Basic queries
await User.objects.all()
await User.objects.get(*conditions)
await User.objects.first()
await User.objects.count()

# Create operations
await User.objects.create(**kwargs)
await User.objects.get_or_create(defaults=None, **lookup)
await User.objects.update_or_create(defaults=None, **lookup)

# Bulk operations
await User.objects.bulk_create(objects)
await User.objects.bulk_update(mappings, match_fields)
await User.objects.bulk_delete(ids, id_field)
```

### QuerySet Methods

```python
# Query building methods (return QuerySet)
.filter(*conditions) / .exclude(*conditions)
.order_by(*fields)  # replaces any existing ordering (not appended); see QueryBuilder.add_ordering
.limit(count) / .offset(count)
.only(*fields) / .defer(*fields)
.select_related(*fields) / .prefetch_related(*fields)
.distinct(*fields) / .annotate(**kwargs)
.group_by(*fields) / .having(*conditions)
.join(table, condition) / .select_for_update()
.skip_default_ordering() / .reverse() / .none()

# Query execution methods (execute query)
await .all() / await .get() / await .first()
await .count() / await .exists()
await .last() / await .earliest() / await .latest()
await .values(*fields) / await .values_list(*fields)
await .aggregate(**kwargs) / await .raw(sql)
await .iterator() / await .update() / await .delete()

# Date/time query methods
await .dates(field, precision, order) / await .datetimes(field, precision, order)

# Index access methods
await .get_item(index_or_slice)

# Field selection methods
.only(*fields) / .defer(*fields)

# Subquery methods
.subquery(name, query_type)
```

### Q Object Operations

```python
# Basic usage
Q(User.name == "John")
Q(User.age >= 18, User.is_active == True)

# Logical combination
Q(User.name == "John") & Q(User.age >= 18)
Q(User.role == "admin") | Q(User.is_staff == True)
~Q(User.is_deleted == True)
```

## Usage Guide

### Basic Usage

```python
# Simple queries
users = await User.objects.all()
user = await User.objects.get(User.name == "John")

# Filtering and ordering
active_users = await User.objects.filter(
    User.is_active == True
).order_by("name").all()

# Create and update
user = await User.objects.create(name="Alice", age=25)
await User.objects.filter(User.id == user.id).update(age=26)
```

### Advanced Usage

```python
# Complex query combination
admin_or_staff = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True),
    User.is_active == True
).select_related("profile").all()

# Advanced query methods: per-row computed columns (no grouping)
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name)
).all()

# Grouped aggregation returns one row per group via values mode
dept_stats = await User.objects.annotate(
    user_count=func.count()
).group_by("department").having(
    func.count() > 5
).values("department", "user_count")

# Aggregate queries
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age)
)

# Field selection control
selected_users = await User.objects.only("id", "username").all()
deferred_users = await User.objects.defer("bio", "profile_image").all()

# Query execution methods
last_user = await User.objects.last()
earliest = await User.objects.earliest("created_at")
user_data = await User.objects.values("id", "username", "email")
usernames = await User.objects.values_list("username", flat=True)

# Bulk operations
users_data = [
    {"name": f"User{i}", "age": 20 + i}
    for i in range(100)
]
await User.objects.bulk_create(users_data)

# Large dataset processing
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# Date/time queries
signup_years = await User.objects.dates("created_at", "year", order="DESC")
login_hours = await User.objects.datetimes("last_login", "hour")

# Index access
first_user = await User.objects.order_by("created_at").get_item(0)
recent_users = await User.objects.order_by("-created_at").get_item(slice(0, 5))

# Session management
async with ctx_session() as session:
    users = await User.objects.using(session).filter(
        User.is_active == True
    ).all()
  
    for user in users:
        await User.objects.using(session).filter(
            User.id == user.id
        ).update(last_seen=func.now())
```