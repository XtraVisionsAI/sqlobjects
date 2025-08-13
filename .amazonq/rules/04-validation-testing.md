# SQLObjects Validation and Testing

## Model Validation Rules

### 1. Field-Level Validation

```python
from sqlobjects.exceptions import ValidationError

from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column, int_column

class User(ObjectModel):
    # Add field validators using shortcut functions or column() function
    username: Column[str] = str_column(length=50, validators=[validate_username])
    email: Column[str] = str_column(length=100, validators=[validate_email])
    age: Column[int] = int_column(validators=[validate_age])
    
    # Or setup validators using class method
    @classmethod
    def setup_validators(cls):
        cls.add_field_validator('username', cls.validate_username)
        cls.add_field_validator('email', cls.validate_email)
        cls.add_field_validator('age', cls.validate_age)
    
    @staticmethod
    def validate_username(value):
        if not value or len(value) < 3:
            raise ValidationError("Username must be at least 3 characters")
    
    @staticmethod
    def validate_email(value):
        if not value or '@' not in value:
            raise ValidationError("Invalid email format")
    
    @staticmethod
    def validate_age(value):
        if value is not None and (value < 0 or value > 150):
            raise ValidationError("Age must be between 0 and 150")
```

### 2. Model-Level Validation

```python
from sqlobjects.base import ObjectModel
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    # ... fields ...
    
    def validate(self):
        """Custom model-level validation"""
        # Cross-field validation
        if self.age and self.age < 18 and self.is_admin:
            raise ValidationError("Users under 18 cannot be administrators")
        
        # Business logic validation
        if self.username and self.username.lower() in ['admin', 'root', 'system']:
            raise ValidationError("Reserved username not allowed")
```

### 3. Validation Control

```python
# Create with validation via ObjectsManager
user = await User.objects.create(
    username="john",
    email="john@example.com"
)

# Create with specific session
user = await User.objects.using(analytics_session).create(
    username="john",
    email="john@example.com"
)

# Instance-level validation methods
user = User(username="john", email="john@example.com")
user.validate_all()  # Execute complete validation
user.validate_fields(["username", "email"])  # Validate specific fields
user.validate()  # Model-level validation hook

# Save with validation control
await user.save()  # Full validation (default)
await user.using(session).save()  # With specific session

# Create from dictionary with validation
user_data = {"username": "john", "email": "john@example.com"}
user = User.from_dict(user_data, validate=True)

# Get or create patterns
user, created = await User.objects.get_or_create(
    User.username == "john",
    defaults={"email": "john@example.com"}
)

# Update or create patterns
user, created = await User.objects.update_or_create(
    User.username == "john",
    defaults={"last_login": datetime.now()}
)
```

### 4. Built-in Validators with File Support

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column, int_column, column
from sqlobjects.validators import (
    validate_email, validate_url, validate_length, validate_range,
    validate_regex, validate_choices, validate_date, validate_time,
    validate_decimal, validate_json, validate_file, validate_image,
    combine_validators, FileValidator, ImageValidator
)

class User(ObjectModel):
    # Email validation
    email: Column[str] = str_column(validators=[validate_email()])
    
    # Length validation
    username: Column[str] = str_column(validators=[validate_length(3, 50)])
    
    # Range validation
    age: Column[int] = int_column(validators=[validate_range(0, 150)])
    
    # Regex validation
    phone: Column[str] = str_column(validators=[validate_regex(r"^\d{3}-\d{3}-\d{4}$")])
    
    # Choices validation
    status: Column[str] = str_column(validators=[validate_choices(["active", "inactive"])])
    
    # Combined validators
    code: Column[str] = str_column(validators=[
        combine_validators(
            validate_length(6, 6),
            validate_regex(r"^[A-Z0-9]+$")
        )
    ])
    
    # JSON validation
    metadata: Column[str] = column(type="text", validators=[validate_json()])
    
    # Date/time validation
    birth_date: Column[str] = str_column(validators=[validate_date("%Y-%m-%d")])
    work_time: Column[str] = str_column(validators=[validate_time("%H:%M")])
    
    # Decimal validation
    price: Column[str] = str_column(validators=[validate_decimal(10, 2)])
    
    # File validation
    document: Column[str] = str_column(validators=[
        FileValidator(
            allowed_extensions=["pdf", "doc", "docx"],
            max_size=10 * 1024 * 1024,  # 10MB
            min_size=1024  # 1KB
        )
    ])
    
    # Image validation
    avatar: Column[str] = str_column(validators=[
        ImageValidator(
            allowed_extensions=["jpg", "png", "webp"],
            max_width=1920,
            max_height=1080,
            max_size=5 * 1024 * 1024  # 5MB
        )
    ])
```

### 5. Data Conversion

```python
# Convert model to dictionary
user_dict = user.to_dict()
user_dict_partial = user.to_dict(include=['id', 'username'])
user_dict_filtered = user.to_dict(exclude=['password_hash'])

# Create model from dictionary
user_data = {"username": "john", "email": "john@example.com"}
user = User.from_dict(user_data, validate=True)
```

## Enhanced Instance Operations Rules

### 1. Smart save() Method Operations

```python
# Smart save() with automatic CREATE/UPDATE detection

# New instance - automatically detected as CREATE
user = User(username="john", email="john@example.com")
await user.save()  # Executes INSERT operation

# Existing instance - automatically detected as UPDATE
user.username = "jane"
await user.save()  # Executes UPDATE operation

# Detached instance with primary key - intelligently handled as UPDATE
detached_user = User(id=1, username="alice", email="alice@example.com")
await detached_user.save()  # Uses merge() for UPDATE semantics

# Validation control with smart save
await user.save(validate=True)   # Full validation (default)
await user.save(validate=False)  # Skip validation

# Session binding with smart save
await user.using(session).save()  # With specific session
await detached_user.using("analytics").save()  # With database name
```

### 2. Detached Instance Operations

```python
# Detached instance creation and operations
detached_user = User(id=1, username="alice", email="alice@example.com")

# save() method intelligently handles detached instances
await detached_user.save()  # Automatically uses merge() for UPDATE

# delete() method supports detached instances
detached_user = User(id=1)
await detached_user.delete()  # Automatically attaches to session then deletes

# refresh() method handles detached instances via direct query
detached_user = User(id=1, username="Old Data")
await detached_user.refresh()  # Reloads data from database
print(detached_user.username)  # Shows latest data

# Selective field refresh for detached instances
await detached_user.refresh(fields=["username", "email"])

# Session binding with detached instances
await detached_user.using(session).save()
await detached_user.using(session).delete()
await detached_user.using(session).refresh()
```

### 3. Unified refresh() Method

```python
# Unified refresh() method replacing both refresh() and refresh_from_db()

# Full refresh (replaces original refresh_from_db())
user = await User.objects.get(User.id == 1)
user.username = "Modified"
await user.refresh()  # Resets all fields to database state

# Selective field refresh
await user.refresh(fields=["username", "updated_at"])  # Only refresh specified fields

# Detached instance refresh
detached_user = User(id=1)
await detached_user.refresh()  # Loads data via direct query

# Session binding with refresh
await user.using(session).refresh()
await detached_user.using("analytics").refresh(fields=["username"])
```

### 4. ModelProxy Session Management

```python
# ModelProxy provides transparent session binding

# Create proxy with session binding
user = User(username="john", email="john@example.com")
proxy = user.using(session)

# All operations work through proxy
await proxy.save()  # Uses bound session
proxy.username = "jane"  # Attribute access
user_dict = proxy.to_dict()  # Method access
await proxy.refresh(fields=["username"])  # Enhanced methods

# Detached instance with proxy
detached_user = User(id=1, username="alice")
proxy = detached_user.using(session)
await proxy.save()  # Automatic session attachment and reference update

# Cross-session operations
user = User(username="bob")
await user.using(session1).save()
await user.using(session2).save()  # Automatic session migration
```

### 2. Model Configuration Access

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    # ... fields ...
    
    class Config:
        table_name = "users"
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"
        description = "System user accounts"
        ordering = ["-created_at"]

# Access model metadata
table_name = User.get_table_name()  # "users"
verbose_name = User.get_verbose_name()  # "User Account"
verbose_plural = User.get_verbose_name_plural()  # "User Accounts"
description = User.get_description()  # "System user accounts"
config = User.get_config()  # Full ModelConfig object
metadata = User.get_metadata()  # All metadata as dict
```

### 3. Signal Integration

```python
# Signals are automatically triggered for:
# - save() operations (before_save, after_save)
# - delete() operations (before_delete, after_delete)
# - bulk update() operations (before_update, after_update)
# - bulk delete() operations (before_delete, after_delete)

from sqlobjects.base import ObjectModel
from datetime import datetime

# Custom signal handling in models
class User(ObjectModel):
    # ... fields ...
    
    async def before_save_handler(self, context):
        """Custom logic before save"""
        self.updated_at = datetime.now()
    
    async def after_save_handler(self, context):
        """Custom logic after save"""
        # Log user creation/update
        pass
```

## Testing Structure and Best Practices

### 1. Test Organization

```python
import pytest
from sqlobjects.base import ObjectModel
from sqlobjects.database import init_db, create_tables, close_db
from sqlobjects.session import ctx_session

class TestUserModel:
    @pytest.mark.asyncio
    async def test_create_user(self, test_session):
        user = await User.objects.using(test_session).create(
            username="testuser",
            email="test@example.com"
        )
        assert user.id is not None
        assert user.username == "testuser"
    
    @pytest.mark.asyncio
    async def test_user_validation(self):
        # Test field validation
        with pytest.raises(ValidationError):
            user = User(username="ab")  # Too short
            user.validate_all()
        
        # Test model validation
        with pytest.raises(ValidationError):
            user = User(username="admin", age=17, is_admin=True)
            user.validate()
    
    @pytest.mark.asyncio
    async def test_user_queries(self, test_session):
        # Create test data
        await User.objects.using(test_session).create(username="alice", age=25)
        await User.objects.using(test_session).create(username="bob", age=30)
        
        # Test queries
        users = await User.objects.using(test_session).filter(User.age >= 25).all()
        assert len(users) == 2
        
        user = await User.objects.using(test_session).get(User.username == "alice")
        assert user.age == 25
```

### 2. Test Fixtures

```python
@pytest.fixture
async def test_db():
    """Create test database with isolated state"""
    db = await init_db(
        "sqlite+aiosqlite:///:memory:", 
        name="test_db", 
        is_default=False  # Recommended to avoid global state pollution
    )
    await create_tables(ObjectModel, "test_db")
    yield db
    await close_db("test_db")

@pytest.fixture
async def test_session(test_db):
    """Provide test session for database operations"""
    async with ctx_session("test_db") as session:
        yield session

@pytest.fixture
async def sample_users(test_session):
    """Create sample test data"""
    users = []
    for i in range(5):
        user = await User.objects.using(test_session).create(
            username=f"user{i}",
            email=f"user{i}@test.com",
            age=20 + i
        )
        users.append(user)
    return users
```

### 3. Test Categories

#### Unit Tests

```python
class TestUserValidation:
    def test_username_validation(self):
        """Test username field validation"""
        user = User(username="ab")
        with pytest.raises(ValidationError, match="at least 3 characters"):
            user.validate_fields(["username"])
    
    def test_email_validation(self):
        """Test email field validation"""
        user = User(email="invalid-email")
        with pytest.raises(ValidationError, match="Invalid email format"):
            user.validate_fields(["email"])
    
    def test_model_validation(self):
        """Test cross-field validation"""
        user = User(username="admin", age=17, is_admin=True)
        with pytest.raises(ValidationError, match="under 18 cannot be administrators"):
            user.validate()
```

#### Integration Tests

```python
class TestUserDatabase:
    @pytest.mark.asyncio
    async def test_crud_operations(self, test_session):
        """Test complete CRUD cycle"""
        # Create
        user = await User.objects.using(test_session).create(
            username="testuser",
            email="test@example.com"
        )
        assert user.id is not None
        
        # Read
        retrieved = await User.objects.using(test_session).get(User.id == user.id)
        assert retrieved.username == "testuser"
        
        # Update
        retrieved.email = "updated@example.com"
        await retrieved.using(test_session).save()
        
        # Delete
        await retrieved.using(test_session).delete()
        
        with pytest.raises(DoesNotExist):
            await User.objects.using(test_session).get(User.id == user.id)
```

#### Smart Instance Operation Tests

```python
class TestSmartInstanceOperations:
    @pytest.mark.asyncio
    async def test_smart_save_create_vs_update(self, test_session):
        """Test smart save() CREATE vs UPDATE detection"""
        # Test CREATE detection
        new_user = User(username="newuser", email="new@example.com")
        await new_user.using(test_session).save()
        assert new_user.id is not None  # Should have ID after CREATE
        
        # Test UPDATE detection
        original_id = new_user.id
        new_user.email = "updated@example.com"
        await new_user.using(test_session).save()
        assert new_user.id == original_id  # ID should remain same after UPDATE
        
        # Verify update in database
        retrieved = await User.objects.using(test_session).get(User.id == original_id)
        assert retrieved.email == "updated@example.com"
    
    @pytest.mark.asyncio
    async def test_detached_instance_save(self, test_session):
        """Test detached instance save() with merge() strategy"""
        # Create initial user
        user = await User.objects.using(test_session).create(
            username="original", email="original@example.com"
        )
        user_id = user.id
        
        # Create detached instance with same ID
        detached_user = User(id=user_id, username="updated", email="updated@example.com")
        await detached_user.using(test_session).save()
        
        # Verify update worked
        retrieved = await User.objects.using(test_session).get(User.id == user_id)
        assert retrieved.username == "updated"
        assert retrieved.email == "updated@example.com"
    
    @pytest.mark.asyncio
    async def test_detached_instance_delete(self, test_session):
        """Test detached instance delete() operation"""
        # Create user
        user = await User.objects.using(test_session).create(
            username="todelete", email="delete@example.com"
        )
        user_id = user.id
        
        # Create detached instance and delete
        detached_user = User(id=user_id)
        await detached_user.using(test_session).delete()
        
        # Verify deletion
        with pytest.raises(DoesNotExist):
            await User.objects.using(test_session).get(User.id == user_id)
    
    @pytest.mark.asyncio
    async def test_unified_refresh_method(self, test_session):
        """Test unified refresh() method functionality"""
        # Create user
        user = await User.objects.using(test_session).create(
            username="refresh_test", email="refresh@example.com"
        )
        user_id = user.id
        
        # Modify locally
        user.username = "modified_locally"
        user.email = "modified@local.com"
        
        # Full refresh
        await user.using(test_session).refresh()
        assert user.username == "refresh_test"  # Should be reset
        assert user.email == "refresh@example.com"  # Should be reset
        
        # Modify again for selective refresh test
        user.username = "modified_again"
        user.email = "modified_again@local.com"
        
        # Selective refresh
        await user.using(test_session).refresh(fields=["username"])
        assert user.username == "refresh_test"  # Should be reset
        assert user.email == "modified_again@local.com"  # Should remain modified
    
    @pytest.mark.asyncio
    async def test_detached_instance_refresh(self, test_session):
        """Test refresh() with detached instances"""
        # Create user
        user = await User.objects.using(test_session).create(
            username="detached_refresh", email="detached@example.com"
        )
        user_id = user.id
        
        # Create detached instance with old data
        detached_user = User(id=user_id, username="old_data", email="old@example.com")
        
        # Refresh should load current data
        await detached_user.using(test_session).refresh()
        assert detached_user.username == "detached_refresh"
        assert detached_user.email == "detached@example.com"
    
    @pytest.mark.asyncio
    async def test_composite_primary_key_detection(self, test_session):
        """Test smart save() with composite primary keys"""
        # Assuming OrderItem has composite primary key (order_id, product_id)
        class OrderItem(ObjectModel):
            order_id: Column[int] = int_column(primary_key=True)
            product_id: Column[int] = int_column(primary_key=True)
            quantity: Column[int] = int_column()
        
        # Test CREATE detection (no primary key values)
        new_item = OrderItem(quantity=5)
        # This would be CREATE if we had proper setup
        
        # Test UPDATE detection (has primary key values)
        detached_item = OrderItem(order_id=1, product_id=2, quantity=10)
        # This would be UPDATE if we had proper setup
        
        # Note: Actual test would require proper table setup
    
    @pytest.mark.asyncio
    async def test_model_proxy_session_binding(self, test_session):
        """Test ModelProxy session binding functionality"""
        user = User(username="proxy_test", email="proxy@example.com")
        
        # Create proxy with session binding
        proxy = user.using(test_session)
        
        # Test attribute access through proxy
        assert proxy.username == "proxy_test"
        proxy.email = "updated_proxy@example.com"
        assert user.email == "updated_proxy@example.com"  # Should update original
        
        # Test method access through proxy
        await proxy.save()
        assert user.id is not None  # Should have ID after save
        
        # Test proxy with detached instance
        detached_user = User(id=user.id, username="detached_proxy")
        detached_proxy = detached_user.using(test_session)
        await detached_proxy.save()  # Should handle merge() correctly
        
        # Verify update
        retrieved = await User.objects.using(test_session).get(User.id == user.id)
        assert retrieved.username == "detached_proxy"
```

#### Performance Tests

```python
class TestUserPerformance:
    @pytest.mark.asyncio
    async def test_bulk_operations(self, test_session):
        """Test bulk operation performance"""
        import time
        
        # Bulk create test data
        users_data = [
            {"username": f"user{i}", "email": f"user{i}@test.com"}
            for i in range(1000)
        ]
        
        start_time = time.time()
        await User.objects.using(test_session).bulk_create(users_data)
        create_time = time.time() - start_time
        
        # Bulk update test
        mappings = [
            {"id": i, "status": "active"} 
            for i in range(1, 1001)
        ]
        
        start_time = time.time()
        await User.objects.using(test_session).bulk_update(mappings, match_fields=["id"])
        update_time = time.time() - start_time
        
        # Assert reasonable performance
        assert create_time < 5.0  # Should complete within 5 seconds
        assert update_time < 3.0  # Should complete within 3 seconds
```

### 4. Test Data Management

```python
class TestDataFactory:
    """Factory for creating test data"""
    
    @staticmethod
    async def create_user(session, **kwargs):
        """Create a test user with default values"""
        defaults = {
            "username": "testuser",
            "email": "test@example.com",
            "age": 25,
            "is_active": True
        }
        defaults.update(kwargs)
        return await User.objects.using(session).create(**defaults)
    
    @staticmethod
    async def create_users(session, count=5, **kwargs):
        """Create multiple test users"""
        users = []
        for i in range(count):
            user_data = {
                "username": f"user{i}",
                "email": f"user{i}@test.com",
                "age": 20 + i
            }
            user_data.update(kwargs)
            user = await TestDataFactory.create_user(session, **user_data)
            users.append(user)
        return users

# Usage in tests
class TestUserQueries:
    @pytest.mark.asyncio
    async def test_filter_by_age(self, test_session):
        await TestDataFactory.create_users(test_session, count=10)
        
        young_users = await User.objects.using(test_session).filter(
            User.age < 25
        ).all()
        assert len(young_users) == 5
```

### 5. Test Configuration

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--disable-warnings",
    "-v"
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests"
]

# Run specific test categories
# uv run pytest -m unit          # Run only unit tests
# uv run pytest -m integration   # Run only integration tests
# uv run pytest -m "not slow"    # Skip slow tests
```

### 6. Error Handling in Tests

```python
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_does_not_exist_exception(self, test_session):
        """Test DoesNotExist exception handling"""
        with pytest.raises(DoesNotExist) as exc_info:
            await User.objects.using(test_session).get(User.username == "nonexistent")
        
        # Verify localized error message
        assert "does not exist" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_validation_error_collection(self):
        """Test multiple validation errors"""
        user = User(username="ab", email="invalid", age=-5)
        
        with pytest.raises(ValidationError) as exc_info:
            user.validate_all()
        
        # Check that multiple errors are collected
        error = exc_info.value
        assert len(error.errors) >= 3  # username, email, age errors
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, test_session):
        """Test transaction rollback on error"""
        try:
            async with ctx_session("test_db") as session:
                await User.objects.using(session).create(username="user1")
                # Simulate error
                raise Exception("Simulated error")
        except Exception:
            pass
        
        # Verify rollback occurred
        count = await User.objects.using(test_session).count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_detached_instance_error_handling(self, test_session):
        """Test error handling for detached instance operations"""
        # Test delete non-existent detached instance
        with pytest.raises(DoesNotExist):
            detached_user = User(id=999)  # Non-existent ID
            await detached_user.using(test_session).delete()
        
        # Test refresh detached instance without primary key
        with pytest.raises(ValueError, match="Cannot refresh instance without primary key"):
            invalid_user = User(username="no_id")
            await invalid_user.using(test_session).refresh()
        
        # Test validation with detached instance
        with pytest.raises(ValidationError):
            detached_user = User(id=1, email="invalid-email")
            await detached_user.using(test_session).save(validate=True)
    
    @pytest.mark.asyncio
    async def test_smart_save_error_scenarios(self, test_session):
        """Test error scenarios in smart save() operations"""
        # Test validation failure in CREATE
        with pytest.raises(ValidationError):
            user = User(username="ab")  # Too short
            await user.using(test_session).save(validate=True)
        
        # Test validation failure in UPDATE
        user = await User.objects.using(test_session).create(
            username="valid", email="valid@example.com"
        )
        user.email = "invalid-email"
        with pytest.raises(ValidationError):
            await user.using(test_session).save(validate=True)
        
        # Test integrity constraint violation
        user1 = await User.objects.using(test_session).create(
            username="unique1", email="unique1@example.com"
        )
        
        # Try to create another user with same username (assuming unique constraint)
        with pytest.raises(IntegrityError):
            user2 = User(username="unique1", email="different@example.com")
            await user2.using(test_session).save()
```

### 7. Performance Testing for Enhanced Operations

```python
class TestEnhancedOperationPerformance:
    @pytest.mark.asyncio
    async def test_detached_instance_batch_performance(self, test_session):
        """Test performance of batch operations with detached instances"""
        import time
        
        # Create initial users
        initial_users = [
            {"username": f"user{i}", "email": f"user{i}@example.com"}
            for i in range(100)
        ]
        created_users = []
        for user_data in initial_users:
            user = await User.objects.using(test_session).create(**user_data)
            created_users.append(user)
        
        # Test batch update with detached instances
        detached_updates = [
            User(id=user.id, username=f"updated_{user.username}", email=user.email)
            for user in created_users
        ]
        
        start_time = time.time()
        tasks = []
        for detached_user in detached_updates:
            task = asyncio.create_task(detached_user.using(test_session).save())
            tasks.append(task)
        await asyncio.gather(*tasks)
        update_time = time.time() - start_time
        
        # Should complete within reasonable time
        assert update_time < 10.0  # 100 updates should complete within 10 seconds
        
        # Verify updates
        updated_users = await User.objects.using(test_session).all()
        for user in updated_users:
            assert user.username.startswith("updated_")
    
    @pytest.mark.asyncio
    async def test_refresh_performance(self, test_session):
        """Test performance of refresh operations"""
        import time
        
        # Create test users
        users = []
        for i in range(50):
            user = await User.objects.using(test_session).create(
                username=f"refresh_user{i}", email=f"refresh{i}@example.com"
            )
            users.append(user)
        
        # Test full refresh performance
        start_time = time.time()
        tasks = []
        for user in users:
            task = asyncio.create_task(user.using(test_session).refresh())
            tasks.append(task)
        await asyncio.gather(*tasks)
        full_refresh_time = time.time() - start_time
        
        # Test selective refresh performance
        start_time = time.time()
        tasks = []
        for user in users:
            task = asyncio.create_task(user.using(test_session).refresh(fields=["username"]))
            tasks.append(task)
        await asyncio.gather(*tasks)
        selective_refresh_time = time.time() - start_time
        
        # Selective refresh should be faster or similar
        assert selective_refresh_time <= full_refresh_time * 1.2  # Allow 20% margin
        
        # Both should complete within reasonable time
        assert full_refresh_time < 5.0
        assert selective_refresh_time < 5.0
```