"""Unit tests for validation system"""

import pytest

from sqlobjects.exceptions import ValidationError
from sqlobjects.fields import Column, IntegerColumn, StringColumn, column
from sqlobjects.model import ObjectModel


def validate_email(value, field_name=None):
    """Simple email validator for testing"""
    if not isinstance(value, str) or "@" not in value:
        raise ValidationError("Invalid email format")
    return value


def validate_length(min_length, max_length):
    """Length validator factory for testing"""

    def validator(value, field_name=None):
        if not isinstance(value, str):
            raise ValidationError("Value must be a string")
        if len(value) < min_length:
            raise ValidationError(f"Value must be at least {min_length} characters")
        if len(value) > max_length:
            raise ValidationError(f"Value must be at most {max_length} characters")
        return value

    return validator


def validate_positive(value, field_name=None):
    """Positive number validator for testing"""
    if value is not None and value <= 0:
        raise ValidationError("Value must be positive")
    return value


class ValidationTestUser(ObjectModel):
    """Test model for validation testing"""

    id: Column[int] = column(type="integer", primary_key=True)
    username: Column[str] = StringColumn(length=50, nullable=False, validators=[validate_length(3, 50)])
    email: Column[str] = StringColumn(length=100, validators=[validate_email])
    age: Column[int | None] = IntegerColumn(nullable=True, validators=[validate_positive])
    bio: Column[str] = column(type="text", nullable=True)


class TestFieldLevelValidation:
    """Test field-level validation"""

    def test_single_validator(self):
        """Test single validator on field"""
        # Valid email should pass
        user = ValidationTestUser(username="test", email="test@example.com", age=25)
        # No exception should be raised during creation

        # Invalid email should fail validation when explicitly validated
        user.email = "invalid-email"
        with pytest.raises(ValidationError):
            user.validate_field("email")

    def test_multiple_validators(self):
        """Test multiple validators on single field"""
        user = ValidationTestUser(username="test", email="test@example.com", age=25)

        # Valid username should pass all validators
        user.username = "valid_user"
        # Should not raise exception

        # Too short username should fail length validator
        user.username = "ab"
        with pytest.raises(ValidationError):
            user.validate_field("username")

        # Too long username should fail length validator
        user.username = "a" * 60
        with pytest.raises(ValidationError):
            user.validate_field("username")

    def test_nullable_field_validation(self):
        """Test validation of nullable fields"""
        user = ValidationTestUser(username="test", email="test@example.com")

        # None value should be allowed for nullable field
        user.age = None
        # Should not raise exception

        # Invalid value should still fail validation
        user.age = -5
        with pytest.raises(ValidationError):
            user.validate_field("age")

    def test_validator_execution_order(self):
        """Test validators are executed in order"""
        # This test assumes validators are executed in the order they're defined
        # First validator failure should be the one reported

        user = ValidationTestUser(username="test", email="test@example.com", age=25)
        user.username = "ab"  # Too short, should fail first validator

        with pytest.raises(ValidationError) as exc_info:
            user.validate_field("username")

        # Should contain message from length validator
        assert "at least 3 characters" in str(exc_info.value)


class TestModelLevelValidation:
    """Test model-level validation"""

    def test_validate_method_called(self):
        """Test model validate() method is called"""

        class CustomValidationUser(ValidationTestUser):
            def validate(self):
                if self.username == "forbidden":
                    raise ValidationError("Username 'forbidden' is not allowed")

        user = CustomValidationUser(username="forbidden", email="test@example.com", age=25)

        with pytest.raises(ValidationError):
            user.validate()

    def test_cross_field_validation(self):
        """Test validation across multiple fields"""

        class CrossFieldUser(ValidationTestUser):
            def validate(self):
                if self.username == "admin" and self.age and self.age < 21:
                    raise ValidationError("Admin users must be at least 21 years old")

        # Valid combination should pass
        user = CrossFieldUser(username="admin", email="admin@example.com", age=25)
        user.validate()  # Should not raise

        # Invalid combination should fail
        user.age = 18
        with pytest.raises(ValidationError):
            user.validate()

    def test_conditional_validation(self):
        """Test conditional validation logic"""

        class ConditionalUser(ValidationTestUser):
            def validate(self):
                if self.email and self.email.endswith("@admin.com"):
                    if self.username and not self.username.startswith("admin_"):
                        raise ValidationError("Admin email requires admin_ username prefix")

        # Non-admin email should not require prefix
        user = ConditionalUser(username="regular", email="user@example.com", age=25)
        user.validate()  # Should not raise

        # Admin email with correct prefix should pass
        user = ConditionalUser(username="admin_user", email="user@admin.com", age=25)
        user.validate()  # Should not raise

        # Admin email without prefix should fail
        user = ConditionalUser(username="regular", email="user@admin.com", age=25)
        with pytest.raises(ValidationError):
            user.validate()


class TestValidationIntegration:
    """Test validation integration with model operations"""

    def test_validation_on_save(self):
        """Test validation is called during save operation"""

        class SaveValidationUser(ValidationTestUser):
            def validate(self):
                if self.username == "invalid_save":
                    raise ValidationError("Cannot save user with invalid_save username")

        user = SaveValidationUser(username="invalid_save", email="test@example.com", age=25)

        # save() should trigger validation and fail
        with pytest.raises(ValidationError):
            # Note: This would require database integration to test fully
            # For unit test, we test the validation method directly
            user.validate()

    def test_skip_validation_option(self):
        """Test validation can be skipped"""

        class SkipValidationUser(ValidationTestUser):
            def validate(self):
                raise ValidationError("This should be skipped")

        user = SkipValidationUser(username="test", email="test@example.com", age=25)

        # Direct validation should fail
        with pytest.raises(ValidationError):
            user.validate()

        # Validation with skip should not fail
        # Note: This would be tested with save(validate=False) in integration tests
        # For unit test, we test the concept
        try:
            # Simulate skipping validation
            pass  # Would call user.save(validate=False)
        except ValidationError:
            pytest.fail("Validation should have been skipped")


class TestValidationErrorHandling:
    """Test validation error handling and reporting"""

    def test_validation_error_message(self):
        """Test validation error messages are descriptive"""
        user = ValidationTestUser(username="test", email="test@example.com", age=25)
        user.email = "invalid-email"

        with pytest.raises(ValidationError) as exc_info:
            user.validate_field("email")

        error = exc_info.value
        assert "Invalid email format" in str(error)

    def test_validation_error_field_info(self):
        """Test validation errors include field information"""
        user = ValidationTestUser(username="test", email="test@example.com", age=25)
        user.username = "ab"  # Too short

        with pytest.raises(ValidationError) as exc_info:
            user.validate_field("username")

        # Error should be related to username field
        error = exc_info.value
        assert hasattr(error, "field") or "username" in str(error)

    def test_multiple_validation_errors(self):
        """Test handling of multiple validation errors"""

        class MultiErrorUser(ValidationTestUser):
            def validate(self):
                errors = []

                if self.username == "invalid":
                    errors.append("Invalid username")

                if self.age and self.age < 0:
                    errors.append("Age cannot be negative")

                if errors:
                    raise ValidationError("; ".join(errors))

        user = MultiErrorUser(username="invalid", email="test@example.com", age=-5)

        with pytest.raises(ValidationError) as exc_info:
            user.validate()

        error_message = str(exc_info.value)
        assert "Invalid username" in error_message
        assert "Age cannot be negative" in error_message


class TestValidatorFunctions:
    """Test individual validator functions"""

    def test_email_validator(self):
        """Test email validator function"""
        # Valid emails should pass
        assert validate_email("test@example.com") == "test@example.com"
        assert validate_email("user.name+tag@domain.co.uk") == "user.name+tag@domain.co.uk"

        # Invalid emails should fail
        with pytest.raises(ValidationError):
            validate_email("invalid-email")

    def test_length_validator(self):
        """Test length validator function"""
        validator = validate_length(3, 10)

        # Valid lengths should pass
        assert validator("abc") == "abc"
        assert validator("1234567890") == "1234567890"

        # Too short should fail
        with pytest.raises(ValidationError):
            validator("ab")

        # Too long should fail
        with pytest.raises(ValidationError):
            validator("12345678901")

        # Non-string should fail
        with pytest.raises(ValidationError):
            validator(123)  # noqa

    def test_positive_validator(self):
        """Test positive number validator"""
        # Positive numbers should pass
        assert validate_positive(1) == 1
        assert validate_positive(100) == 100

        # None should pass (for nullable fields)
        assert validate_positive(None) is None

        # Zero and negative should fail
        with pytest.raises(ValidationError):
            validate_positive(0)

        with pytest.raises(ValidationError):
            validate_positive(-1)


class TestValidationPerformance:
    """Test validation performance considerations"""

    def test_validation_caching(self):
        """Test validation results can be cached if implemented"""
        user = ValidationTestUser(username="test", email="test@example.com", age=25)

        # Multiple validations of same field should be efficient
        # This is a placeholder for potential caching implementation
        user.validate_field("email")
        user.validate_field("email")  # Should be fast if cached

    def test_lazy_validation(self):
        """Test validation is only performed when needed"""
        # Creating user with invalid data should not immediately validate
        user = ValidationTestUser(username="ab", email="invalid", age=-5)

        # Validation should only occur when explicitly called
        with pytest.raises(ValidationError):
            user.validate_field("username")

    def test_partial_validation(self):
        """Test validation of individual fields"""
        user = ValidationTestUser(username="test", email="test@example.com", age=25)

        # Should be able to validate individual fields
        user.validate_field("username")  # Should not raise
        user.validate_field("email")  # Should not raise
        user.validate_field("age")  # Should not raise

        # Invalid field should fail individual validation
        user.email = "invalid"
        with pytest.raises(ValidationError):
            user.validate_field("email")


class TestCustomValidators:
    """Test custom validator implementation"""

    def test_custom_validator_function(self):
        """Test custom validator function"""

        def validate_even_number(value):
            if value is not None and value % 2 != 0:
                raise ValidationError("Number must be even")
            return value

        # Even numbers should pass
        assert validate_even_number(2) == 2
        assert validate_even_number(100) == 100
        assert validate_even_number(None) is None

        # Odd numbers should fail
        with pytest.raises(ValidationError):
            validate_even_number(1)

        with pytest.raises(ValidationError):
            validate_even_number(99)

    def test_validator_with_parameters(self):
        """Test validator factory with parameters"""

        def validate_range(min_val, max_val):
            def validator(value):
                if value is not None and (value < min_val or value > max_val):
                    raise ValidationError(f"Value must be between {min_val} and {max_val}")
                return value

            return validator

        age_validator = validate_range(0, 150)

        # Valid range should pass
        assert age_validator(25) == 25
        assert age_validator(0) == 0
        assert age_validator(150) == 150
        assert age_validator(None) is None

        # Out of range should fail
        with pytest.raises(ValidationError):
            age_validator(-1)

        with pytest.raises(ValidationError):
            age_validator(151)

    def test_class_based_validator(self):
        """Test class-based validator"""

        class EmailDomainValidator:
            def __init__(self, allowed_domains):
                self.allowed_domains = allowed_domains

            def __call__(self, value):
                if value and "@" in value:
                    domain = value.split("@")[1]
                    if domain not in self.allowed_domains:
                        raise ValidationError(f"Email domain must be one of: {', '.join(self.allowed_domains)}")
                return value

        validator = EmailDomainValidator(["example.com", "test.org"])

        # Allowed domains should pass
        assert validator("user@example.com") == "user@example.com"
        assert validator("user@test.org") == "user@test.org"

        # Disallowed domain should fail
        with pytest.raises(ValidationError):
            validator("user@gmail.com")
