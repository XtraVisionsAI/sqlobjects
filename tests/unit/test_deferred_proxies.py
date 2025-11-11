"""Unit tests for deferred field and relationship field proxy system"""

import pytest

from sqlobjects.exceptions import DeferredFieldError
from sqlobjects.fields import Column, StringColumn, column, foreign_key, identity
from sqlobjects.fields.proxies import DeferredFieldProxy
from tests.conftest import TestModel


# Test Models for Deferred and Relationship Testing
class DeferredTestUser(TestModel):
    """User model with deferred fields for testing"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    bio: Column[str] = column(type="text", deferred=True)
    profile_data: Column[str] = column(type="text", deferred=True, deferred_group="details")
    large_content: Column[str] = column(type="text", deferred=True, deferred_raiseload=True)


class DeferredTestPost(TestModel):
    """Post model for relationship testing"""

    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text")
    author_id: Column[int] = foreign_key("deferred_test_users.id")


class TestDeferredFieldProxy:
    """Test DeferredFieldProxy behavior and error handling"""

    def test_deferred_field_proxy_creation(self):
        """Test DeferredFieldProxy can be created with proper parameters"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        assert proxy.instance == user
        assert proxy.field_name == "bio"
        assert proxy._cached_value is None
        assert proxy._is_loaded is False

    def test_deferred_field_proxy_string_representation(self):
        """Test DeferredFieldProxy string representations"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        assert str(proxy) == "<DeferredField: bio>"
        assert repr(proxy) == "DeferredFieldProxy(field_name='bio')"

    def test_deferred_field_proxy_error_on_iteration(self):
        """Test DeferredFieldProxy raises error when trying to iterate"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            iter(proxy)

        assert "Cannot iterate over deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    def test_deferred_field_proxy_error_on_length(self):
        """Test DeferredFieldProxy raises error when trying to get length"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            len(proxy)

        assert "Cannot get length of deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    def test_deferred_field_proxy_error_on_boolean(self):
        """Test DeferredFieldProxy raises error when checking boolean value"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            bool(proxy)

        assert "Cannot check boolean value of deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    def test_deferred_field_proxy_error_on_getitem(self):
        """Test DeferredFieldProxy raises error when accessing items"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            proxy[0]  # noqa

        assert "Cannot access items of deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    def test_deferred_field_proxy_error_on_contains(self):
        """Test DeferredFieldProxy raises error when checking containment"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            "test" in proxy  # noqa  # type: ignore

        assert "Cannot check containment in deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    def test_deferred_field_proxy_error_on_arithmetic(self):
        """Test DeferredFieldProxy raises error on arithmetic operations"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        with pytest.raises(DeferredFieldError) as exc_info:
            proxy + "test"  # noqa  # type: ignore

        assert "Cannot perform arithmetic on deferred field 'bio'" in str(exc_info.value)
        assert "DeferredTestUser" in str(exc_info.value)

    async def test_deferred_field_proxy_is_loaded_status(self, session):
        """Test DeferredFieldProxy correctly reports loaded status"""
        # Create user with deferred field
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio"
        )

        # Load user with deferred field
        loaded_user = await DeferredTestUser.objects.using(session).defer("bio").get(DeferredTestUser.id == user.id)

        proxy = DeferredFieldProxy(loaded_user, "bio")

        # Initially not loaded
        assert not proxy.is_loaded()
        assert proxy.is_deferred()

        # After loading
        await loaded_user.load_deferred_field("bio")
        assert proxy.is_loaded()
        assert proxy.is_deferred()  # Still deferred, but loaded

    async def test_deferred_field_proxy_fetch_caching(self, session):
        """Test DeferredFieldProxy caches fetched values"""
        # Create user with deferred field
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio content"
        )

        # Load user with deferred field
        loaded_user = await DeferredTestUser.objects.using(session).defer("bio").get(DeferredTestUser.id == user.id)

        proxy = DeferredFieldProxy(loaded_user, "bio")

        # First fetch should load and cache
        result1 = await proxy.fetch()
        assert result1 == "Test bio content"
        assert proxy._is_loaded is True
        assert proxy._cached_value == "Test bio content"

        # Second fetch should return cached value
        result2 = await proxy.fetch()
        assert result2 == "Test bio content"
        assert result2 is proxy._cached_value


class TestDeferredFieldIntegration:
    """Test deferred field integration with model system"""

    async def test_deferred_field_automatic_proxy_creation(self, session):
        """Test that deferred fields automatically create proxy objects"""
        # Create user with deferred field
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio"
        )

        # Load user with deferred field
        loaded_user = await DeferredTestUser.objects.using(session).defer("bio").get(DeferredTestUser.id == user.id)

        # Mark as from database to trigger proxy creation
        loaded_user._state_manager.mark_from_database(True)

        # Accessing deferred field should return proxy
        bio_proxy = loaded_user.bio
        assert isinstance(bio_proxy, DeferredFieldProxy)
        assert bio_proxy.field_name == "bio"

    async def test_deferred_field_loading_behavior(self, session):
        """Test deferred field loading through model methods"""
        # Create user with deferred fields
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio content", profile_data="Profile data content"
        )

        # Load user with deferred fields
        loaded_user = (
            await DeferredTestUser.objects.using(session)
            .defer("bio", "profile_data")
            .get(DeferredTestUser.id == user.id)
        )

        # Check deferred status
        assert loaded_user.is_field_deferred("bio")
        assert loaded_user.is_field_deferred("profile_data")
        assert not loaded_user.is_field_loaded("bio")
        assert not loaded_user.is_field_loaded("profile_data")

        # Load single deferred field
        await loaded_user.load_deferred_field("bio")
        assert loaded_user.is_field_loaded("bio")
        assert not loaded_user.is_field_loaded("profile_data")

        # Load all remaining deferred fields
        await loaded_user.load_deferred_fields()
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("profile_data")

    async def test_deferred_field_groups(self, session):
        """Test deferred field groups functionality"""
        # Create user with grouped deferred field
        user = await DeferredTestUser.objects.using(session).create(
            username="test", email="test@example.com", bio="Test bio", profile_data="Profile data"
        )

        # Load user with deferred field groups
        loaded_user = (
            await DeferredTestUser.objects.using(session).defer("profile_data").get(DeferredTestUser.id == user.id)
        )

        # Check that both fields are deferred:
        # - profile_data: deferred by query (.defer() call)
        # - bio: deferred by field definition (deferred=True)
        assert loaded_user.is_field_deferred("profile_data")
        assert loaded_user.is_field_deferred("bio")  # Always deferred due to deferred=True

        # Load the grouped field
        await loaded_user.load_deferred_field("profile_data")
        assert loaded_user.is_field_loaded("profile_data")

    async def test_multiple_deferred_fields_loading(self, session):
        """Test loading multiple deferred fields efficiently"""
        # Create user with multiple deferred fields
        user = await DeferredTestUser.objects.using(session).create(
            username="test",
            email="test@example.com",
            bio="Test bio content",
            profile_data="Profile data content",
            large_content="Large content data",
        )

        # Load user with multiple deferred fields
        loaded_user = (
            await DeferredTestUser.objects.using(session)
            .defer("bio", "profile_data", "large_content")
            .get(DeferredTestUser.id == user.id)
        )

        # Load specific fields
        await loaded_user.load_deferred_fields(["bio", "profile_data"])

        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("profile_data")
        assert not loaded_user.is_field_loaded("large_content")

        # Verify loaded values
        assert loaded_user.bio == "Test bio content"
        assert loaded_user.profile_data == "Profile data content"


class TestProxyErrorMessages:
    """Test proxy error messages are clear and helpful"""

    def test_deferred_field_error_messages_are_descriptive(self):
        """Test that deferred field error messages provide clear guidance"""
        user = DeferredTestUser(username="test", email="test@example.com")
        proxy = DeferredFieldProxy(user, "bio")

        # Test iteration error message
        with pytest.raises(DeferredFieldError) as exc_info:
            iter(proxy)
        error_msg = str(exc_info.value)
        assert "Cannot iterate" in error_msg
        assert "deferred field" in error_msg
        assert "'bio'" in error_msg
        assert "DeferredTestUser" in error_msg

    def test_error_messages_include_model_class_name(self):
        """Test that error messages include the model class name for context"""
        user = DeferredTestUser(username="test", email="test@example.com")

        deferred_proxy = DeferredFieldProxy(user, "bio")

        # Should include model class name
        with pytest.raises(DeferredFieldError) as exc_info:
            len(deferred_proxy)
        assert "DeferredTestUser" in str(exc_info.value)
