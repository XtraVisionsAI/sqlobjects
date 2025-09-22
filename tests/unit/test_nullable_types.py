"""Test nullable column type annotations"""

from sqlobjects.fields import Column, IntegerColumn, StringColumn
from sqlobjects.model import ObjectModel


def validate_positive(value):
    if value is not None and value < 0:
        raise ValueError("Value must be positive")
    return value


class TestNullableTypeAnnotations:
    """Test that nullable columns work with union type annotations"""

    def test_nullable_integer_column_type_annotation(self):
        """Test that nullable integer columns work with int | None annotation"""

        class TestModel(ObjectModel):
            # This should not cause type checking issues
            age: Column[int | None] = IntegerColumn(nullable=True, validators=[validate_positive])

        # Test functionality
        model = TestModel(age=25)
        assert model.age == 25

        model_none = TestModel(age=None)
        assert model_none.age is None

    def test_nullable_string_column_type_annotation(self):
        """Test that nullable string columns work with str | None annotation"""

        class TestModel2(ObjectModel):
            name: Column[str | None] = StringColumn(nullable=True)

            class Config:
                table_name = "test_nullable_string_models"

        # Test functionality
        model = TestModel2(name="test")
        assert model.name == "test"

        model_none = TestModel2(name=None)
        assert model_none.name is None

    def test_non_nullable_column_type_annotation(self):
        """Test that non-nullable columns work with regular type annotation"""

        class TestModel3(ObjectModel):
            # Non-nullable should work with regular type
            id: Column[int] = IntegerColumn(nullable=False, primary_key=True)
            name: Column[str] = StringColumn(nullable=False)

            class Config:
                table_name = "test_non_nullable_models"

        # Test functionality
        model = TestModel3(name="test")
        assert model.name == "test"

    def test_mixed_nullable_and_non_nullable(self):
        """Test mixing nullable and non-nullable columns"""

        class TestModel4(ObjectModel):
            id: Column[int] = IntegerColumn(primary_key=True, nullable=False)
            name: Column[str] = StringColumn(nullable=False)
            age: Column[int | None] = IntegerColumn(nullable=True)
            bio: Column[str | None] = StringColumn(nullable=True)

            class Config:
                table_name = "test_mixed_nullable_models"

        # Test functionality
        model = TestModel4(name="test", age=25, bio="test bio")
        assert model.name == "test"
        assert model.age == 25
        assert model.bio == "test bio"

        model_partial = TestModel4(name="test", age=None, bio=None)
        assert model_partial.name == "test"
        assert model_partial.age is None
        assert model_partial.bio is None
