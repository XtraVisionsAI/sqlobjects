# CRUD Operations

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/04-crud-operations.md](../../docs-zh/features/04-crud-operations.md)

SQLObjects provides comprehensive Create, Read, Update, Delete (CRUD) operations with smart operation detection, bulk processing, and high-performance optimizations.

## Create Operations

### Basic Creation

```python
# Create single record
user = await User.objects.create(
    username="alice",
    email="alice@example.com",
    age=25
)

# Create with validation
try:
    user = await User.objects.create(
        username="bob",
        email="invalid-email"  # Will trigger validation error
    )
except ValidationError as e:
    print(f"Validation failed: {e}")
```

### get_or_create

```python
# Get existing or create new
user, created = await User.objects.get_or_create(
    username="charlie",
    defaults={"email": "charlie@example.com", "age": 30}
)

if created:
    print("New user created")
else:
    print("Existing user found")
```

### update_or_create

```python
# Update existing or create new
user, created = await User.objects.update_or_create(
    username="david",
    defaults={"email": "david@example.com", "last_login": datetime.now()}
)
```

## Read Operations

### Basic Queries

```python
# Get single record
user = await User.objects.get(User.id == 1)

# Get with error handling
try:
    user = await User.objects.get(User.username == "alice")
except DoesNotExist:
    print("User not found")
except MultipleObjectsReturned:
    print("Multiple users found")

# Get first or None
user = await User.objects.filter(User.age >= 18).first()

# Check existence
exists = await User.objects.filter(User.email == "test@example.com").exists()
```

### List Operations

```python
# Get all records
users = await User.objects.all()

# Filtered results
active_users = await User.objects.filter(User.is_active == True).all()

# Ordered results
users = await User.objects.order_by("-created_at").all()

# Limited results
recent_users = await User.objects.order_by("-created_at").limit(10).all()
```

## Update Operations

### Single Record Updates

```python
# Update using save()
user = await User.objects.get(User.id == 1)
user.email = "newemail@example.com"
await user.save()  # Smart detection: UPDATE operation

# Update with validation
user.age = -5  # Invalid age
try:
    await user.save()
except ValidationError as e:
    print(f"Update failed: {e}")
```

### Bulk Updates

```python
# Update multiple records
await User.objects.filter(User.age < 18).update(is_minor=True)

# Update with expressions
from sqlobjects.expressions import func
await User.objects.filter(User.is_active == True).update(
    last_seen=func.now()
)

# Conditional updates
await User.objects.filter(
    User.created_at < datetime.now() - timedelta(days=30)
).update(is_verified=True)
```

## Delete Operations

### Single Record Deletion

```python
# Delete using instance
user = await User.objects.get(User.id == 1)
await user.delete()

# Delete with confirmation
user = await User.objects.get(User.username == "alice")
if user.posts_count == 0:  # Check before deletion
    await user.delete()
```

### Bulk Deletion

```python
# Delete multiple records
await User.objects.filter(User.is_active == False).delete()

# Delete with conditions
await User.objects.filter(
    User.last_login < datetime.now() - timedelta(days=365)
).delete()

# Delete all (use with caution)
await User.objects.all().delete()
```

## Bulk Operations

### Bulk Create

```python
# High-performance bulk creation
users_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"}
    for i in range(1000)
]

# Bulk create with batch processing
created_users = await User.objects.bulk_create(
    users_data,
    batch_size=500,  # Process in batches
    return_objects=True  # Return created objects
)

# Bulk create with conflict handling
await User.objects.bulk_create(
    users_data,
    on_conflict="ignore"  # Ignore duplicate key errors
)
```

### Bulk Update

```python
# True bulk update (much faster than individual updates)
mappings = [
    {"id": 1, "status": "active", "last_seen": datetime.now()},
    {"id": 2, "status": "inactive", "last_seen": datetime.now()},
    {"id": 3, "status": "pending", "last_seen": datetime.now()},
]

await User.objects.bulk_update(
    mappings,
    match_fields=["id"],  # Fields to match records
    batch_size=1000
)

# Bulk update specific fields only
await User.objects.bulk_update(
    mappings,
    match_fields=["id"],
    update_fields=["status", "last_seen"]  # Only update these fields
)
```

### Bulk Delete

```python
# Bulk delete by IDs
user_ids = [1, 2, 3, 4, 5]
await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000
)

# Bulk delete with custom field
usernames = ["user1", "user2", "user3"]
await User.objects.bulk_delete(
    usernames,
    id_field="username",
    batch_size=500
)
```

## Smart Operation Detection

### Automatic CREATE vs UPDATE

```python
# CREATE operation (no primary key value)
user = User(username="new_user", email="new@example.com")
await user.save()  # Triggers INSERT

# UPDATE operation (has primary key value)
user.email = "updated@example.com"
await user.save()  # Triggers UPDATE

# Detached instance UPDATE
detached_user = User(id=1, username="detached", email="detached@example.com")
await detached_user.save()  # Uses merge() strategy for UPDATE
```

### Operation Context in Signals

```python
from sqlobjects.signals import SignalContext, Operation

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        print(f"Operation: {context.operation}")  # SAVE
        print(f"Actual operation: {context.actual_operation}")  # CREATE or UPDATE
        
        if context.actual_operation == Operation.CREATE:
            self.created_at = datetime.now()
        else:
            self.updated_at = datetime.now()
```

## Transaction Management

### Single Operations

```python
from sqlobjects.session import ctx_session

# Automatic transaction management
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    posts = await Post.objects.using(session).bulk_create([
        {"title": "Post 1", "author_id": user.id},
        {"title": "Post 2", "author_id": user.id}
    ])
    # Automatic commit on success, rollback on exception
```

### Complex Transactions

```python
# Multi-step operations in single transaction
async with ctx_session() as session:
    try:
        # Create user
        user = await User.objects.using(session).create(
            username="complex_user",
            email="complex@example.com"
        )
        
        # Create related data
        profile = await Profile.objects.using(session).create(
            user_id=user.id,
            bio="User biography"
        )
        
        # Update statistics
        await Stats.objects.using(session).filter(
            Stats.type == "user_count"
        ).update(value=Stats.value + 1)
        
        # All operations committed together
    except Exception as e:
        # All operations rolled back automatically
        print(f"Transaction failed: {e}")
```

## Performance Optimization

### Batch Size Optimization

```python
# Optimize batch sizes for different operations
await User.objects.bulk_create(data, batch_size=1000)  # Large batches for inserts
await User.objects.bulk_update(mappings, batch_size=500)  # Smaller batches for updates
await User.objects.bulk_delete(ids, batch_size=2000)  # Large batches for deletes
```

### Memory-Efficient Operations

```python
# Process large datasets efficiently
async def process_large_dataset():
    async for user in User.objects.iterator(chunk_size=1000):
        # Process each user
        user.last_processed = datetime.now()
        await user.save()
        
        # Memory is automatically managed in chunks
```

### Query Optimization

```python
# Skip default ordering for better performance
count = await User.objects.skip_default_ordering().count()

# Use select_related to avoid N+1 queries
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(post.author.username)  # No additional query

# Use only() to load specific fields
users = await User.objects.only("id", "username", "email").all()
```

## Error Handling

### Validation Errors

```python
from sqlobjects.exceptions import ValidationError

try:
    user = await User.objects.create(
        username="",  # Empty username
        email="invalid-email"  # Invalid email
    )
except ValidationError as e:
    print(f"Validation failed: {e}")
    # Handle validation errors appropriately
```

### Database Errors

```python
from sqlobjects.exceptions import DatabaseError, IntegrityError

try:
    # Attempt to create user with duplicate email
    user = await User.objects.create(
        username="duplicate",
        email="existing@example.com"  # Already exists
    )
except IntegrityError as e:
    print(f"Integrity constraint violated: {e}")
except DatabaseError as e:
    print(f"Database error: {e}")
```

### Bulk Operation Errors

```python
# Handle errors in bulk operations
try:
    await User.objects.bulk_create(invalid_data)
except ValidationError as e:
    print(f"Bulk validation failed: {e}")
    # Process valid records separately
    
# Use on_conflict for graceful error handling
await User.objects.bulk_create(
    data_with_duplicates,
    on_conflict="ignore"  # Skip duplicates instead of failing
)
```

## Best Practices

### CRUD Operation Guidelines

1. **Use bulk operations for large datasets**: 10-100x performance improvement
2. **Validate data before bulk operations**: Catch errors early
3. **Use transactions for related operations**: Ensure data consistency
4. **Handle errors gracefully**: Provide meaningful error messages
5. **Monitor performance**: Use appropriate batch sizes

### Performance Best Practices

```python
# ✅ Good: Use bulk operations for multiple records
await User.objects.bulk_create(users_data, batch_size=1000)

# ❌ Bad: Individual creates in loop
for user_data in users_data:
    await User.objects.create(**user_data)  # Much slower

# ✅ Good: Use select_related for foreign keys
posts = await Post.objects.select_related("author").all()

# ❌ Bad: N+1 query problem
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # Additional query for each post
```

### Transaction Best Practices

```python
# ✅ Good: Use context managers for transactions
async with ctx_session() as session:
    # All operations in single transaction
    pass

# ✅ Good: Keep transactions short
async with ctx_session() as session:
    # Quick database operations only
    user = await User.objects.using(session).create(...)
    # Don't do long-running tasks here

# ❌ Bad: Long-running operations in transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(...)
    await send_email(user)  # This should be outside transaction
    await process_image(user.avatar)  # This too
```