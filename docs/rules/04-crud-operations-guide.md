# CRUD Operations Guide

## Core Concepts

- **Smart save()**: Automatic CREATE/UPDATE detection based on primary key
- **Bulk Operations**: High-performance operations for large datasets (10-100x faster)
- **Detached Instances**: Operations on instances not attached to a session
- **Dirty Field Tracking**: Automatic tracking of modified fields for optimized UPDATEs
- **Transaction Safety**: All operations support transaction management

## Common Usage

### Create Operations

```python
# Single create
user = await User.objects.create(username="alice", email="alice@example.com")

# Create with validation
user = await User.objects.create(username="bob", email="bob@example.com", validate=True)

# Get or create
user, created = await User.objects.get_or_create(
    username="charlie",
    defaults={"email": "charlie@example.com"}
)

# Update or create
user, created = await User.objects.update_or_create(
    username="david",
    defaults={"email": "david@example.com", "is_active": True}
)
```

### Read Operations

```python
# Get single object
user = await User.objects.get(User.id == 1)
user = await User.objects.get(User.username == "alice")

# Get or None
user = await User.objects.filter(User.id == 999).first()  # Returns None if not found

# Get multiple objects
users = await User.objects.filter(User.is_active == True).all()

# Check existence
exists = await User.objects.filter(User.username == "alice").exists()

# Count
count = await User.objects.filter(User.is_active == True).count()
```

### Update Operations

```python
# Update single instance (smart save)
user = await User.objects.get(User.id == 1)
user.email = "newemail@example.com"
await user.save()  # Only updates modified fields

# Bulk update (high performance)
mappings = [
    {"id": 1, "is_active": False},
    {"id": 2, "is_active": True},
    {"id": 3, "email": "updated@example.com"}
]
await User.objects.bulk_update(mappings, match_fields=["id"], batch_size=1000)

# Update all matching records
await User.objects.filter(User.department == "sales").update_all(is_active=False)
```

### Delete Operations

```python
# Delete single instance
user = await User.objects.get(User.id == 1)
await user.delete()

# Bulk delete (high performance)
user_ids = [1, 2, 3, 4, 5]
await User.objects.bulk_delete(user_ids, id_field="id", batch_size=1000)

# Delete all matching records
await User.objects.filter(User.is_active == False).delete_all()
```

### Bulk Operations

```python
# Bulk create (10-100x faster than individual creates)
users_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"}
    for i in range(1000)
]
await User.objects.bulk_create(users_data, batch_size=500)

# Bulk update with match fields
mappings = [
    {"id": 1, "status": "active", "last_seen": datetime.now()},
    {"id": 2, "status": "inactive", "last_seen": datetime.now()},
]
await User.objects.bulk_update(mappings, match_fields=["id"])

# Bulk delete with ID list
user_ids = list(range(1, 1001))
await User.objects.bulk_delete(user_ids, id_field="id", batch_size=1000)
```

## Best Practices

### ✅ Do

- **Use bulk operations** for large datasets
- **Use transactions** for related operations
- **Let save() detect** CREATE vs UPDATE automatically
- **Use batch_size** parameter for very large datasets
- **Check return values** from get_or_create/update_or_create

```python
# Good: Bulk operations for performance
await User.objects.bulk_create(users_data, batch_size=1000)

# Good: Transaction for related operations
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    await Post.objects.using(session).create(title="First Post", author_id=user.id)

# Good: Smart save() with automatic detection
user = User(username="bob", email="bob@example.com")
await user.save()  # Automatically detects CREATE

user.email = "newemail@example.com"
await user.save()  # Automatically detects UPDATE, only updates email
```

### ❌ Don't

- **Don't use loops** for bulk operations
- **Don't forget transactions** for related operations
- **Don't manually check** if object exists before save()
- **Don't use huge batch sizes** (memory issues)

```python
# Bad: Loop instead of bulk operation (100x slower!)
for user_data in users_data:
    await User.objects.create(**user_data)

# Good: Bulk operation
await User.objects.bulk_create(users_data, batch_size=1000)

# Bad: No transaction for related operations
user = await User.objects.create(username="alice")
# If next line fails, user is already created!
await Post.objects.create(title="Post", author_id=user.id)

# Good: Use transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    await Post.objects.using(session).create(title="Post", author_id=user.id)
```

## Smart save() Behavior

### Automatic Operation Detection

```python
# CREATE: No primary key value
user = User(username="alice", email="alice@example.com")
await user.save()  # Triggers CREATE operation
# Signals: before_save → before_create → after_save → after_create

# UPDATE: Has primary key value
user.email = "newemail@example.com"
await user.save()  # Triggers UPDATE operation, only updates email
# Signals: before_save → before_update → after_save → after_update

# Detached instance UPDATE
detached_user = User(id=1, username="bob", email="bob@example.com")
await detached_user.save()  # Triggers UPDATE operation
```

### Dirty Field Tracking

```python
# Only modified fields are updated
user = await User.objects.get(User.id == 1)
user.email = "newemail@example.com"
user.is_active = False
await user.save()  # Only updates email and is_active fields

# Check dirty fields
if user._has_changes():
    changed_fields = user._get_changed_fields()
    print(f"Modified fields: {changed_fields}")
```

## Performance Tips

### Bulk Operations Performance

```python
# Use appropriate batch sizes
await User.objects.bulk_create(data, batch_size=1000)  # PostgreSQL
await User.objects.bulk_create(data, batch_size=500)   # MySQL
await User.objects.bulk_create(data, batch_size=100)   # SQLite

# Bulk operations are 10-100x faster
# Individual creates: ~10 records/second
# Bulk create: ~1000-10000 records/second
```

### Transaction Management

```python
# Keep transactions short
async with ctx_session() as session:
    # Quick database operations only
    user = await User.objects.using(session).create(username="alice")
    await user.posts.using(session).create(title="Post")
# Transaction commits here

# Don't hold transactions during I/O
async with ctx_session() as session:
    user = await User.objects.using(session).get(User.id == 1)
# Transaction ends
await send_email(user.email)  # External I/O outside transaction
```

### Memory Management

```python
# Process large datasets with iterator
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
    # Memory automatically cleaned every 10 chunks

# Batch processing with pagination
last_id = 0
while True:
    users = await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(100).all()
    
    if not users:
        break
    
    await process_batch(users)
    last_id = users[-1].id
```

## Troubleshooting

### Object Not Found

**Problem**: `DoesNotExist: User matching query does not exist`

**Solution**:
```python
# Use first() instead of get() if object might not exist
user = await User.objects.filter(User.id == 999).first()
if user is None:
    # Handle not found case
    pass

# Or handle exception
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    # Handle not found
    pass
```

### Dirty Fields Not Cleared

**Problem**: New objects have dirty field markers

**Solution**:
```python
# Use from_dict() for clean state
user = User.from_dict({"username": "alice", "email": "alice@example.com"})
# Dirty fields automatically cleared after creation

# Or use objects.create()
user = await User.objects.create(username="alice", email="alice@example.com")
# No dirty fields after creation
```

### Bulk Operation Failures

**Problem**: Bulk operation fails partway through

**Solution**:
```python
# Use transactions for atomicity
async with ctx_session() as session:
    await User.objects.using(session).bulk_create(users_data)
    # All or nothing - rolls back on error

# Use smaller batch sizes
await User.objects.bulk_create(users_data, batch_size=100)  # More reliable
```

### Performance Issues

**Problem**: Individual operations are slow

**Solution**:
```python
# Use bulk operations
# Bad: Loop (slow)
for user_data in users_data:
    await User.objects.create(**user_data)

# Good: Bulk operation (fast)
await User.objects.bulk_create(users_data, batch_size=1000)
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, BooleanColumn
from sqlobjects.session import ctx_session
from datetime import datetime

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    is_active: Column[bool] = BooleanColumn(default=True)

async def main():
    # CREATE
    user = await User.objects.create(username="alice", email="alice@example.com")
    
    # READ
    user = await User.objects.get(User.username == "alice")
    users = await User.objects.filter(User.is_active == True).all()
    
    # UPDATE (smart save)
    user.email = "newemail@example.com"
    await user.save()  # Only updates email field
    
    # DELETE
    await user.delete()
    
    # BULK OPERATIONS
    users_data = [
        {"username": f"user{i}", "email": f"user{i}@example.com"}
        for i in range(1000)
    ]
    await User.objects.bulk_create(users_data, batch_size=500)
    
    # TRANSACTION
    async with ctx_session() as session:
        user = await User.objects.using(session).create(username="bob")
        # Related operations in same transaction
        await process_user(user, session)

import asyncio
asyncio.run(main())
```
