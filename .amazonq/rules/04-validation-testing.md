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

### 4. Built-in Validators

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column, int_column, column
from sqlobjects.validators import (
    validate_email, validate_url, validate_length, validate_range,
    validate_regex, validate_choices, validate_date, validate_time,
    validate_decimal, validate_json, validate_file, validate_image,
    combine_validators
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

## Instance Operations Rules

### 1. Model Instance Lifecycle

```python
# Create instances using ObjectsManager
user = await User.objects.create(username="john", email="john@example.com")

# Instance-level operations
user = User(username="john", email="john@example.com")

# Save instance to database
await user.save()  # With validation
await user.save(validate=False)  # Skip validation
# Save operations now handle transactions through session context

# Delete instance from database
await user.delete()  # Delete this instance
await user.using(session).delete()  # With specific session

# Refresh instance from database
await user.refresh()  # Refresh all fields
await user.refresh_from_db(["username", "email"])  # Refresh specific fields

# Data conversion
user_dict = user.to_dict()  # Convert to dictionary
user_dict = user.to_dict(include=["id", "username"])  # Include specific fields
user_dict = user.to_dict(exclude=["password"])  # Exclude specific fields

# Create from dictionary
user_data = {"username": "john", "email": "john@example.com"}
user = User.from_dict(user_data, validate=True)
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
        
        user = await User.objects.using(test_session).get(username="alice")
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
        retrieved = await User.objects.using(test_session).get(id=user.id)
        assert retrieved.username == "testuser"
        
        # Update
        retrieved.email = "updated@example.com"
        await retrieved.using(test_session).save()
        
        # Delete
        await retrieved.using(test_session).delete()
        
        with pytest.raises(DoesNotExist):
            await User.objects.using(test_session).get(id=user.id)
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
            await User.objects.using(test_session).get(username="nonexistent")
        
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
```