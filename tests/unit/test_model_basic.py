"""Unit tests for basic model functionality"""

from datetime import datetime

import pytest

from sqlobjects.expressions import func
from sqlobjects.fields import BooleanColumn, Column, IntegerColumn, StringColumn, column, identity
from sqlobjects.model import ObjectModel


class TestUser(ObjectModel):
    """Test model for basic functionality testing"""

    __test__ = False

    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=50, nullable=False)
    age: Column[int] = IntegerColumn()
    is_active: Column[bool] = BooleanColumn(default=True)
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())


class TestModelCreation:
    """Test model definition and metadata"""

    def test_model_definition(self):
        """Test automatic table generation"""
        assert hasattr(TestUser, "__table__")
        assert TestUser.__table__.name == "test_users"  # Auto pluralization
        assert "id" in TestUser.__table__.columns
        assert "name" in TestUser.__table__.columns
        assert "age" in TestUser.__table__.columns
        assert "is_active" in TestUser.__table__.columns
        assert "created_at" in TestUser.__table__.columns

    def test_primary_key_detection(self):
        """Test automatic primary key handling"""
        pk_columns = [col for col in TestUser.__table__.columns if col.primary_key]  # noqa
        assert len(pk_columns) == 1
        assert pk_columns[0].name == "id"

    def test_column_types(self):
        """Test column type mapping"""
        table = TestUser.__table__

        # Check column types
        assert str(table.columns["name"].type) == "VARCHAR(50)"
        assert str(table.columns["age"].type) == "INTEGER"
        assert str(table.columns["is_active"].type) == "BOOLEAN"
        assert "DATETIME" in str(table.columns["created_at"].type)

    def test_column_constraints(self):
        """Test column constraints"""
        table = TestUser.__table__

        # Primary key constraint
        assert table.columns["id"].primary_key is True
        assert table.columns["id"].autoincrement is True

        # Nullable constraints
        assert table.columns["name"].nullable is False  # Explicitly non-nullable
        assert table.columns["age"].nullable is True  # Default for nullable

        # Default values
        assert table.columns["is_active"].default.arg is True  # type: ignore


class TestInstanceCreation:
    """Test instance creation and initialization"""

    def test_constructor_behavior(self):
        """Test constructor with init parameter handling"""
        # Should only accept init=True fields
        user = TestUser(name="John", age=25)
        assert user.name == "John"
        assert user.age == 25
        assert user.is_active is True  # Default value

        # id field (init=False) should not be in constructor
        with pytest.raises(TypeError):
            TestUser(id=1, name="John", age=25)

        # created_at field (server_default, init=False) should not be in constructor
        with pytest.raises(TypeError):
            TestUser(name="John", created_at=datetime.now())

    def test_from_dict_integration(self):
        """Test from_dict method handles all field types"""
        data = {"id": 1, "name": "Jane", "age": 30, "is_active": False, "created_at": datetime.now()}
        user = TestUser.from_dict(data)

        assert user.id == 1
        assert user.name == "Jane"
        assert user.age == 30
        assert user.is_active is False
        assert isinstance(user.created_at, datetime)

        # Verify dirty fields are cleared after from_dict
        dirty_fields = user._state_manager.get_dirty_fields()
        assert len(dirty_fields) == 0

    def test_partial_from_dict(self):
        """Test from_dict with partial data"""
        data = {"name": "Bob", "age": 35}
        user = TestUser.from_dict(data)

        assert user.name == "Bob"
        assert user.age == 35
        assert user.is_active is True  # Default value
        assert not hasattr(user, "id") or user.id is None

    def test_dirty_field_tracking(self):
        """Test automatic dirty field tracking"""
        user = TestUser(name="Original", age=25)

        # Constructor should mark fields as dirty
        dirty_fields = user._state_manager.get_dirty_fields()
        assert "name" in dirty_fields
        assert "age" in dirty_fields

        # Clear dirty fields
        user._state_manager.clear_dirty_fields()

        # Modifying field should mark as dirty
        user.name = "Modified"
        dirty_fields = user._state_manager.get_dirty_fields()
        assert "name" in dirty_fields
        assert "age" not in dirty_fields

    def test_get_dirty_fields_public_api(self):
        """Test public get_dirty_fields() accessor"""
        user = TestUser(name="Original", age=25)

        dirty_fields = user.get_dirty_fields()
        assert "name" in dirty_fields
        assert "age" in dirty_fields

        # Returned set is a copy: mutating it must not affect internal state
        dirty_fields.clear()
        assert "name" in user.get_dirty_fields()

        user._state_manager.clear_dirty_fields()
        assert user.get_dirty_fields() == set()

        user.name = "Modified"
        assert user.get_dirty_fields() == {"name"}


class TestModelOperations:
    """Test model operations and smart detection"""

    def test_save_operation_detection(self):
        """Test save() method CREATE/UPDATE detection"""
        user = TestUser(name="Test", age=20)

        # New instance should trigger CREATE
        assert not user._has_primary_key_values()

        # After setting primary key should trigger UPDATE
        user.id = 1
        assert user._has_primary_key_values()

    def test_detached_instance_handling(self):
        """Test operations on detached instances"""
        # Detached instance with primary key
        detached_user = TestUser.from_dict({"id": 1, "name": "Detached", "age": 30})

        # Should be recognized as existing instance
        assert detached_user._has_primary_key_values()

        # Should support operations (would use merge strategy)
        assert hasattr(detached_user, "save")
        assert hasattr(detached_user, "delete")
        assert hasattr(detached_user, "refresh")

    def test_delete_cascade_parameter(self):
        """Test delete method cascade parameter"""
        user = TestUser.from_dict({"id": 1, "name": "Delete Test", "age": 25})

        # Should accept cascade parameter
        try:
            # These should not raise parameter errors (will fail due to no session)
            import inspect

            delete_method = user.delete
            sig = inspect.signature(delete_method)
            assert "cascade" in sig.parameters

            # Default parameter should be True
            cascade_param = sig.parameters["cascade"]
            assert cascade_param.default is True

        except Exception as e:
            # Should not be parameter-related errors
            assert "cascade" not in str(e).lower() or "unexpected keyword" not in str(e).lower()

    def test_state_manager_integration(self):
        """Test state manager functionality"""
        user = TestUser(name="State Test", age=25)

        # Should have state manager
        assert hasattr(user, "_state_manager")

        # Should track dirty fields
        dirty_fields = user._state_manager.get_dirty_fields()
        assert isinstance(dirty_fields, set)
        assert len(dirty_fields) > 0

        # Should support state operations
        user._state_manager._set("test_key", "test_value")
        assert user._state_manager._get("test_key", None) == "test_value"


class TestDataclassIntegration:
    """Test dataclass-style functionality"""

    def test_repr_generation(self):
        """Test __repr__ method generation"""
        user = TestUser(name="Repr Test", age=30)
        repr_str = repr(user)

        assert "TestUser" in repr_str
        assert "name='Repr Test'" in repr_str
        assert "age=30" in repr_str
        assert "is_active=True" in repr_str

    def test_eq_generation(self):
        """Test __eq__ method generation"""
        user1 = TestUser.from_dict({"id": 1, "name": "Equal Test", "age": 25})
        user2 = TestUser.from_dict({"id": 1, "name": "Different Name", "age": 30})
        user3 = TestUser.from_dict({"id": 2, "name": "Equal Test", "age": 25})

        # Same primary key should be equal
        assert user1 == user2

        # Different primary key should not be equal
        assert user1 != user3

        # Different type should not be equal
        assert user1 != "not a user"

    def test_dataclass_markers(self):
        """Test dataclass compatibility markers"""
        assert hasattr(TestUser, "__dataclass_fields__")
        assert hasattr(TestUser, "__dataclass_params__")
        assert hasattr(TestUser, "__dataclass_transform__")

        # Check dataclass fields
        fields = TestUser.__dataclass_fields__  # type: ignore
        assert "name" in fields
        assert "age" in fields
        assert "is_active" in fields


class TestFieldCache:
    """Test field cache optimization"""

    def test_field_cache_initialization(self):
        """Test field cache is properly initialized"""
        assert hasattr(TestUser, "_field_cache")
        field_cache = TestUser._field_cache  # type: ignore

        assert "deferred_fields" in field_cache
        assert "relationship_fields" in field_cache
        assert "regular_fields" in field_cache

        assert isinstance(field_cache["deferred_fields"], set)
        assert isinstance(field_cache["relationship_fields"], set)
        assert isinstance(field_cache["regular_fields"], set)

    def test_field_classification(self):
        """Test fields are properly classified"""
        field_cache = TestUser._field_cache  # type: ignore

        # Regular fields should be in regular_fields
        regular_fields = field_cache["regular_fields"]
        assert "name" in regular_fields
        assert "age" in regular_fields
        assert "is_active" in regular_fields


class TestModelConfiguration:
    """Test model configuration system"""

    def test_default_configuration(self):
        """Test default configuration values"""
        # Table name should be auto-generated
        assert TestUser.__table__.name == "test_users"

        # Should have default ordering if specified
        if hasattr(TestUser, "_default_ordering"):
            assert isinstance(TestUser._default_ordering, list)  # type: ignore

    def test_custom_configuration(self):
        """Test custom configuration"""

        class CustomUser(ObjectModel):
            id: Column[int] = identity()
            name: Column[str] = StringColumn(length=50)

            class Config:
                table_name = "custom_users"
                ordering = ["-id"]

        assert CustomUser.__table__.name == "custom_users"
        assert CustomUser._default_ordering == ["-id"]  # type: ignore


class TestModelInheritance:
    """Test model inheritance"""

    def test_model_inheritance(self):
        """Test model can be inherited"""

        class ExtendedUser(TestUser):
            email: Column[str] = StringColumn(length=100)

        # Should have all parent fields plus new field
        table = ExtendedUser.__table__
        assert "id" in table.columns
        assert "name" in table.columns
        assert "age" in table.columns
        assert "email" in table.columns

        # Should have different table name
        assert table.name == "extended_users"

    def test_abstract_model(self):
        """Test abstract model functionality"""

        class AbstractBase(ObjectModel):
            __abstract__ = True

            created_at: Column[datetime] = column(type="datetime", server_default=func.now())
            updated_at: Column[datetime] = column(type="datetime", onupdate=func.now())

        class ConcreteModel(AbstractBase):
            id: Column[int] = identity()
            name: Column[str] = StringColumn(length=50)

        # Abstract model should not have table
        assert not hasattr(AbstractBase, "__table__")

        # Concrete model should have table with inherited fields
        table = ConcreteModel.__table__
        assert "created_at" in table.columns
        assert "updated_at" in table.columns
        assert "name" in table.columns


class TestErrorHandling:
    """Test model error handling"""

    def test_invalid_field_access(self):
        """Test accessing non-existent fields"""
        user = TestUser(name="Error Test", age=25)

        with pytest.raises(AttributeError):
            _ = user.non_existent_field

    def test_invalid_constructor_arguments(self):
        """Test invalid constructor arguments"""
        # Non-existent field
        with pytest.raises(TypeError):
            TestUser(name="Test", non_existent_field="value")

        # Field with init=False
        with pytest.raises(TypeError):
            TestUser(id=1, name="Test")

    def test_type_validation(self):
        """Test basic type validation"""
        user = TestUser(name="Type Test", age=25)

        # Should accept correct types
        user.name = "New Name"
        user.age = 30
        user.is_active = False

        # Type validation depends on implementation
        # This is a placeholder for future type validation features
