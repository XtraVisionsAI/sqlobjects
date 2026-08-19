# CRUD Operations

## Overview

SQLObjects provides comprehensive Create, Read, Update, Delete operation support, including single and bulk processing
capabilities, intelligent operation detection, and transaction support.

## Quick Start

### Basic CRUD Operations

```python
# Create
user = await User.objects.create(username="john", email="john@example.com")

# Read
user = await User.objects.get(User.id == 1)
users = await User.objects.filter(User.is_active == True).all()

# Update
user.email = "john.new@example.com"
await user.save()

# Delete
await user.delete()
```

## Create Operations

### Single Object Creation

```python
# Method 1: Using object manager
user = await User.objects.create(
    username="alice",
    email="alice@example.com",
    age=25
)

# ObjectsManager's create method internally uses from_dict
user = await User.objects.create(
    username="alice",
    email="alice@example.com",
    id=1  # init=False fields are handled automatically
)

# Method 2: Instance creation and save
user = User(username="bob", email="bob@example.com")
await user.save()

# With validation control
user = await User.objects.create(
    username="charlie",
    email="invalid-email",  # Will raise ValidationError
    validate=True  # Default behavior
)
```

### Bulk Creation

```python
# Bulk create for performance
users_data = [
    {"username": "user1", "email": "user1@example.com"},
    {"username": "user2", "email": "user2@example.com"},
    {"username": "user3", "email": "user3@example.com"},
]

# Returns count of created records
created_count = await User.objects.bulk_create(users_data, batch_size=1000)
```

### Get or Create Pattern

```python
# Get existing or create new
user, created = await User.objects.get_or_create(
    username="david",  # Lookup field
    defaults={"email": "david@example.com", "age": 30}  # Values for creation
)

# get_or_create and update_or_create also use from_dict
user, created = await User.objects.get_or_create(
    username="david",
    defaults={"email": "david@example.com", "id": 100}  # Handles all field types
)

if created:
    print("Created new user")
else:
    print("Found existing user")

# Multiple lookup fields
user, created = await User.objects.get_or_create(
    username="eve",
    email="eve@example.com",
    defaults={"age": 25, "is_active": True}
)
```

## Read Operations

### Single Object Retrieval

```python
# Get by primary key
user = await User.objects.get(User.id == 1)

# Get by unique field
user = await User.objects.get(User.username == "john")

# Multi-condition get
user = await User.objects.get(
    User.username == "john",
    User.is_active == True
)

# First/last with ordering
first_user = await User.objects.order_by("created_at").first()
latest_user = await User.objects.order_by("-created_at").first()
```

### Multiple Object Retrieval

```python
# All objects
users = await User.objects.all()

# Filtered results
active_users = await User.objects.filter(User.is_active == True).all()

# Pagination
users_page = await User.objects.offset(20).limit(10).all()
```

### Bulk Retrieval

```python
# Bulk get by field values
user_dict = await User.objects.in_bulk([1, 2, 3], field_name="id")
# Result: {1: User(id=1), 2: User(id=2), 3: User(id=3)}

user_dict = await User.objects.in_bulk(
    ["john", "alice", "bob"], 
    field_name="username"
)
# Result: {"john": User(username="john"), "alice": User(username="alice")}

# Using primary key (default)
user_dict = await User.objects.in_bulk([1, 2, 3])  # field_name="pk" is default
```

## Update Operations

### Single Object Update

```python
# Method 1: Load, modify, save
user = await User.objects.get(User.id == 1)
user.email = "new.email@example.com"
user.last_login = datetime.now(timezone.utc)
await user.save()

# Method 2: Detached instance smart save
user = User(id=1, email="updated@example.com", username="updated_user")
await user.save()  # Automatically detects UPDATE operation
```

### Bulk Updates

```python
# Update multiple records with same values
affected = await User.objects.filter(
    User.is_active == False
).update(
    status="inactive",
    updated_at=func.now()  # database clock, not app clock (avoids timezone mismatch)
)

# Conditional update using Q objects
affected = await User.objects.filter(
    Q(User.last_login < datetime.now(timezone.utc) - timedelta(days=30)) |
    Q(User.login_count == 0)
).update(is_active=False)

# Bulk update with conflict resolution
mappings = [
    {"id": 1, "email": "user1@new.com", "status": "active"},
    {"id": 2, "email": "user2@new.com", "status": "inactive"},
    # ... thousands of records
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["id"],
    batch_size=1000
)

# With conflict handling
from sqlobjects import ConflictResolution

affected = await User.objects.bulk_create(
    users_data,
    on_conflict=ConflictResolution.IGNORE,  # Skip duplicates
    batch_size=1000
)
```

### Update or Create Pattern

```python
# Update existing or create new
user, created = await User.objects.update_or_create(
    username="frank",  # Lookup field
    defaults={
        "email": "frank@example.com",
        "last_login": datetime.now(timezone.utc),
        "login_count": 1
    }
)

if created:
    print("Created new user")
else:
    print("Updated existing user")
```

## Delete Operations

### Single Object Deletion

```python
# Method 1: Load and delete
user = await User.objects.get(User.id == 1)
await user.delete()

# Method 2: Delete detached instance
user = User(id=1)
await user.delete()  # Automatically attaches to session
```

`Model.delete(cascade=None)` auto-detects whether cascade handling is needed
based on the model's relationships. Pass `cascade=True` to force cascade
handling or `cascade=False` for a direct delete without cascade. Database-level
foreign key actions (`OnDelete.CASCADE`, etc.) and ORM-level `relationship(cascade=...)`
are configured on the model itself; see the
[Cascade Operations](05-relationships.md#cascade-operations) section for details.

### Bulk Deletion

```python
# Conditional delete
deleted = await User.objects.filter(
    User.is_active == False,
    User.last_login < datetime.now(timezone.utc) - timedelta(days=365)
).delete()

# Delete using Q objects
deleted = await User.objects.filter(
    Q(User.is_deleted == True) | Q(User.status == "banned")
).delete()

# True bulk delete for large ID lists (10-100x faster)
user_ids = [1, 2, 3, 4, 5]  # Thousands of IDs
deleted = await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000
)

# Bulk delete using custom field
usernames = ["user1", "user2", "user3"]
deleted = await User.objects.bulk_delete(
    usernames,
    id_field="username"
)

### Update All Records

```python
# Update all records with same values
affected = await User.objects.update_all(
    status="migrated",
    updated_at=func.now()
)
```

### Delete All Records

```python
# Delete all records
deleted = await User.objects.delete_all()

# Fast delete using TRUNCATE (use with caution)
deleted = await User.objects.delete_all(fast=True)  # Returns -1, no transaction safety
```

## Advanced Instance Operations

### Smart Save Detection

```python
# Automatic CREATE vs UPDATE detection
# New instance (no primary key) → CREATE
user = User(username="new_user", email="new@example.com")
await user.save()  # INSERT operation

# Existing instance (has primary key) → UPDATE
user.email = "updated@example.com"
await user.save()  # UPDATE operation

# Detached instance (has primary key) → UPDATE via merge()
detached_user = User(id=1, username="detached", email="detached@example.com")
await user.save()  # UPDATE operation via merge() strategy

# from_dict creates instance with proper dirty field tracking
user_data = {"username": "new_user", "email": "new@example.com"}
user = User.from_dict(user_data)  # No dirty fields marked
await user.save()  # Clean INSERT operation

# Manual construction marks all fields as dirty
user = User(username="manual", email="manual@example.com")  # All fields marked dirty
await user.save()  # UPDATE operation with all fields
```

### Refresh Operations

```python
# Full refresh from database
user = await User.objects.get(User.id == 1)
user.username = "modified_locally"
await user.refresh()  # Reset all fields to database state

# Selective field refresh
await user.refresh(fields=["username", "updated_at"])

# Refresh detached instance
detached_user = User(id=1)
await detached_user.refresh()  # Load current data from database
```

### Session Management

```python
# Using specific database session
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="session_user")
    user.email = "updated@example.com"
    await user.using(session).save()

# Cross-database operations
user = User(username="multi_db_user")
await user.using("main_db").save()
await user.using("analytics_db").save()  # Same data to different databases
```

## Transaction Management

### Automatic Transactions

```python
# Single operations (auto-commit)
user = await User.objects.create(username="auto_commit")

# Multiple operations in transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="tx_user")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    # Auto-commit on success, rollback on error
```

### Manual Transaction Control

```python
from sqlobjects.session import ctx_session

async with ctx_session() as session:
    try:
        # Multiple operations
        user = await User.objects.using(session).create(username="manual_tx")
        await User.objects.using(session).filter(
            User.is_active == False
        ).update(status="archived")
    
        # Manual commit
        await session.commit()
    except Exception as e:
        # Manual rollback
        await session.rollback()
        raise
```

## Performance Optimization

### Batch Size Guidelines

```python
# Recommended batch sizes by database type
postgresql_batch = 1000  # PostgreSQL handles larger batches well
mysql_batch = 500        # MySQL prefers smaller batches
sqlite_batch = 100       # SQLite has lower limits

# Adjust by record complexity
simple_records_batch = 2000    # Simple fields (id, name, status)
complex_records_batch = 200    # Complex fields (JSON, text, binary)

# Usage example
await User.objects.bulk_create(
    large_dataset,
    batch_size=postgresql_batch if db_type == "postgresql" else mysql_batch
)
```

### Memory Management

```python
# Process large updates in batches
async def process_large_update(user_ids: list[int]):
    batch_size = 1000
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i + batch_size]
        await User.objects.bulk_update(
            [{"id": uid, "processed": True} for uid in batch],
            match_fields=["id"]
        )
```

## Error Handling

### Common Exceptions

```python
from sqlobjects.exceptions import (
    DoesNotExist, 
    MultipleObjectsReturned, 
    ValidationError,
    IntegrityError
)

# Handle not found
try:
    user = await User.objects.get(User.username == "nonexistent")
except DoesNotExist:
    print("User not found")

# Handle multiple results
try:
    user = await User.objects.get(User.email.like("%@gmail.com"))
except MultipleObjectsReturned:
    user = await User.objects.filter(User.email.like("%@gmail.com")).first()

# Handle validation errors
try:
    user = await User.objects.create(username="ab", email="invalid")
except ValidationError as e:
    print(f"Validation failed: {e.message}")

# Handle database constraints
try:
    user = await User.objects.create(username="existing_user")
except IntegrityError as e:
    print(f"Database constraint violation: {e}")
```

### Bulk Operation Error Handling

```python
# Bulk operations with error handling
try:
    affected = await User.objects.bulk_update(mappings, match_fields=["id"])
    print(f"Updated {affected} records")
except Exception as e:
    # Handle bulk failure
    logger.error(f"Bulk update failed: {e}")

    # Fallback to individual updates
    for mapping in mappings:
        try:
            await User.objects.filter(User.id == mapping["id"]).update(
                **{k: v for k, v in mapping.items() if k != "id"}
            )
        except Exception as individual_error:
            logger.error(f"Individual update failed for ID {mapping['id']}: {individual_error}")
```

## Best Practices

### Validation Strategy

```python
# Enable validation for user input
user_data = request.json  # From API request
user = await User.objects.create(**user_data, validate=True)

# Skip validation for trusted data
system_user = await User.objects.create(
    username="system",
    email="system@internal.com",
    validate=False  # Skip validation for performance
)
```

### Bulk vs Individual Operations

```python
# Use bulk operations for large datasets
if len(user_updates) > 100:
    # Bulk update (10-100x faster)
    await User.objects.bulk_update(user_updates, match_fields=["id"])
else:
    # Individual updates (better error handling)
    for update in user_updates:
        await User.objects.filter(User.id == update["id"]).update(**update)
```

### Session Usage

```python
# Use sessions for related operations
async with ctx_session() as session:
    # All operations in same transaction
    user = await User.objects.using(session).create(username="related_ops")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    settings = await Settings.objects.using(session).create(user_id=user.id)
```