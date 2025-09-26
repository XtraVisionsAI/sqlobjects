"""Integration tests for deferred field and relationship loading behavior"""

import pytest

from sqlobjects.exceptions import DeferredFieldError, PrimaryKeyError
from sqlobjects.fields import Column, StringColumn, column, foreign_key, identity
from sqlobjects.fields.proxies import DeferredFieldProxy, RelationFieldProxy
from tests.conftest import TestModel


# Test Models for Integration Testing
class DeferredUser(TestModel):
    """User model with various deferred field configurations"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100)
    first_name: Column[str] = StringColumn(length=50)
    last_name: Column[str] = StringColumn(length=50)

    # Different types of deferred fields
    bio: Column[str] = column(type="text", deferred=True)  # Field-level deferred
    profile_data: Column[str] = column(
        type="text", deferred=True, deferred_group="details"
    )  # Field-level deferred with group
    large_content: Column[str] = column(
        type="text", deferred=True, deferred_raiseload=True
    )  # Field-level deferred with raiseload
    settings: Column[str] = column(type="json", deferred=True)  # Field-level deferred JSON

    class Config:
        table_name = "deferred_users"


class DeferredPost(TestModel):
    """Post model for relationship testing"""

    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text")
    summary: Column[str] = column(type="text", deferred=True)
    author_id: Column[int] = foreign_key("deferred_users.id")

    class Config:
        table_name = "deferred_posts"


class DeferredComment(TestModel):
    """Comment model for nested relationship testing"""

    id: Column[int] = identity()
    content: Column[str] = column(type="text")
    metadata: Column[str] = column(type="json", deferred=True)
    post_id: Column[int] = foreign_key("deferred_posts.id")
    author_id: Column[int] = foreign_key("deferred_users.id")

    class Config:
        table_name = "deferred_comments"


class TestDeferredFieldDatabaseOperations:
    """Test deferred field behavior with actual database operations"""

    async def test_create_with_deferred_fields(self, session):
        """Test creating objects with deferred fields"""
        user = await DeferredUser.objects.using(session).create(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            bio="This is a test bio",
            profile_data='{"theme": "dark", "notifications": true}',
            large_content="Very large content data",
            settings='{"language": "en", "timezone": "UTC"}',
        )

        assert user.id is not None
        assert user.username == "testuser"
        assert user.bio == "This is a test bio"
        assert user.profile_data == '{"theme": "dark", "notifications": true}'

    async def test_defer_single_field(self, session):
        """Test deferring a single field during query"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="defer_single_user",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            bio="This is a test bio",
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Check deferred status
        assert loaded_user.is_field_deferred("bio")
        assert not loaded_user.is_field_loaded("bio")
        assert not loaded_user.is_field_deferred("username")

        # Non-deferred fields should be accessible
        assert loaded_user.username == "defer_single_user"
        assert loaded_user.email == "test@example.com"

    async def test_defer_multiple_fields(self, session):
        """Test deferring multiple fields during query"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="defer_multiple_user",
            email="test@example.com",
            bio="Test bio",
            profile_data="Profile data",
            large_content="Large content",
        )

        # Load with multiple deferred fields
        loaded_user = (
            await DeferredUser.objects.using(session)
            .defer("bio", "profile_data", "large_content")
            .get(DeferredUser.id == user.id)
        )

        # Check all deferred fields
        assert loaded_user.is_field_deferred("bio")
        assert loaded_user.is_field_deferred("profile_data")
        assert loaded_user.is_field_deferred("large_content")

        # Non-deferred fields should still be accessible
        assert loaded_user.username == "defer_multiple_user"
        assert loaded_user.email == "test@example.com"

    async def test_load_single_deferred_field(self, session):
        """Test loading a single deferred field"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="load_single_user", email="test@example.com", bio="This is a test bio"
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Initially deferred
        assert not loaded_user.is_field_loaded("bio")

        # Load the deferred field
        await loaded_user.load_deferred_field("bio")

        # Now should be loaded
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.bio == "This is a test bio"

    async def test_load_multiple_deferred_fields(self, session):
        """Test loading multiple deferred fields efficiently"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="load_multiple_user",
            email="test@example.com",
            bio="Test bio content",
            profile_data="Profile data content",
            large_content="Large content data",
        )

        # Load with multiple deferred fields
        loaded_user = (
            await DeferredUser.objects.using(session)
            .defer("bio", "profile_data", "large_content")
            .get(DeferredUser.id == user.id)
        )

        # Load specific fields
        await loaded_user.load_deferred_fields(["bio", "profile_data"])

        # Check loaded status
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("profile_data")
        assert not loaded_user.is_field_loaded("large_content")

        # Verify values
        assert loaded_user.bio == "Test bio content"
        assert loaded_user.profile_data == "Profile data content"

    async def test_load_all_deferred_fields(self, session):
        """Test loading all deferred fields at once"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="load_all_user",
            email="test@example.com",
            bio="Test bio",
            profile_data="Profile data",
            large_content="Large content",
        )

        # Load with all fields deferred
        loaded_user = (
            await DeferredUser.objects.using(session)
            .defer("bio", "profile_data", "large_content")
            .get(DeferredUser.id == user.id)
        )

        # Load all deferred fields
        await loaded_user.load_deferred_fields()

        # All should be loaded now
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("profile_data")
        assert loaded_user.is_field_loaded("large_content")

    async def test_deferred_field_proxy_integration(self, session):
        """Test deferred field proxy integration with database loading"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="proxy_integration_user", email="test@example.com", bio="Test bio content"
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Mark as from database to enable proxy behavior
        loaded_user._state_manager.mark_from_database(True)

        # Accessing deferred field should return proxy
        bio_proxy = loaded_user.bio
        assert isinstance(bio_proxy, DeferredFieldProxy)

        # Fetch through proxy should load the field
        bio_content = await bio_proxy.fetch()
        assert bio_content == "Test bio content"

        # Subsequent access should return loaded value
        assert loaded_user.is_field_loaded("bio")

    async def test_deferred_field_error_without_primary_key(self):
        """Test that loading deferred fields requires primary key"""
        # Create user without saving (no primary key)
        user = DeferredUser(username="no_pk_user", email="test@example.com")

        # Mark field as deferred
        deferred_fields = user._state_manager.get_deferred_fields()
        deferred_fields.add("bio")
        user._state_manager.set_deferred_fields(deferred_fields)

        # Should raise error when trying to load without primary key
        with pytest.raises(PrimaryKeyError):
            await user.load_deferred_field("bio")

    async def test_deferred_field_with_json_type(self, session):
        """Test deferred fields with JSON data type"""
        # Create user with JSON deferred field
        settings_data = '{"theme": "dark", "language": "en", "notifications": {"email": true, "push": false}}'
        user = await DeferredUser.objects.using(session).create(
            username="json_user", email="test@example.com", settings=settings_data
        )

        # Load with deferred JSON field
        loaded_user = await DeferredUser.objects.using(session).defer("settings").get(DeferredUser.id == user.id)

        # Load the JSON field
        await loaded_user.load_deferred_field("settings")
        assert loaded_user.settings == settings_data

    async def test_deferred_field_groups_behavior(self, session):
        """Test deferred field groups functionality"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="groups_user",
            email="test@example.com",
            bio="Regular deferred field",
            profile_data="Grouped deferred field",
        )

        # Load with specific deferred field (profile_data is in "details" group)
        loaded_user = await DeferredUser.objects.using(session).defer("profile_data").get(DeferredUser.id == user.id)

        # Check deferred status
        assert loaded_user.is_field_deferred("profile_data")  # Query-level deferred
        assert loaded_user.is_field_deferred("bio")  # Field-level deferred (deferred=True in model)

        # Load the grouped field
        await loaded_user.load_deferred_field("profile_data")
        assert loaded_user.is_field_loaded("profile_data")
        assert loaded_user.profile_data == "Grouped deferred field"


class TestDeferredFieldQueryOperations:
    """Test deferred field behavior with various query operations"""

    async def test_defer_with_filter_operations(self, session):
        """Test deferred fields work with filtering"""
        # Create multiple users
        users_data = [
            {"username": f"filter_user{i}", "email": f"user{i}@example.com", "bio": f"Bio for user {i}"}
            for i in range(5)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)

        # Query with filter and defer
        users = (
            await DeferredUser.objects.using(session)
            .defer("bio")
            .filter(DeferredUser.username.like("filter_user%"))
            .all()
        )

        assert len(users) == 5
        for user in users:
            assert user.is_field_deferred("bio")
            assert not user.is_field_loaded("bio")

    async def test_defer_with_ordering(self, session):
        """Test deferred fields work with ordering"""
        # Create test data
        users_data = [
            {"username": f"order_user{i}", "email": f"user{i}@example.com", "bio": f"Bio {i}"} for i in range(3)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)

        # Query with ordering and defer - filter only our test data
        users = (
            await DeferredUser.objects.using(session)
            .defer("bio")
            .filter(DeferredUser.username.like("order_user%"))
            .order_by("-username")
            .all()
        )

        assert len(users) == 3
        assert users[0].username == "order_user2"
        assert users[1].username == "order_user1"
        assert users[2].username == "order_user0"

        # All should have deferred bio
        for user in users:
            assert user.is_field_deferred("bio")

    async def test_defer_with_limit_offset(self, session):
        """Test deferred fields work with pagination"""
        # Create test data
        users_data = [
            {"username": f"page_user{i:02d}", "email": f"user{i}@example.com", "bio": f"Bio {i}"} for i in range(10)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)

        # Query with pagination and defer - filter only our test data
        users = (
            await DeferredUser.objects.using(session)
            .defer("bio")
            .filter(DeferredUser.username.like("page_user%"))
            .order_by("username")
            .limit(3)
            .offset(2)
            .all()
        )

        assert len(users) == 3
        assert users[0].username == "page_user02"
        assert users[1].username == "page_user03"
        assert users[2].username == "page_user04"

        # All should have deferred bio
        for user in users:
            assert user.is_field_deferred("bio")

    async def test_defer_with_only_fields(self, session):
        """Test combining defer with only field selection"""
        # Create test data
        user = await DeferredUser.objects.using(session).create(
            username="only_fields_user", email="test@example.com", first_name="Test", last_name="User", bio="Test bio"
        )

        # Query with only specific fields and defer
        loaded_user = (
            await DeferredUser.objects.using(session)
            .only("id", "username", "email", "bio")
            .defer("bio")
            .get(DeferredUser.id == user.id)
        )

        # Should have only selected fields, with bio deferred
        assert loaded_user.username == "only_fields_user"
        assert loaded_user.email == "test@example.com"
        assert loaded_user.is_field_deferred("bio")


class TestRelationshipFieldProxyIntegration:
    """Test relationship field proxy integration (basic functionality)"""

    async def test_relationship_proxy_creation(self, session):
        """Test relationship proxy objects are created correctly"""
        # Create test user
        user = await DeferredUser.objects.using(session).create(username="author", email="author@example.com")

        # Simulate relationship field in cache (since we don't have actual relationships set up)
        field_cache = user._get_field_cache()
        field_cache["relationship_fields"].add("posts")

        # Accessing relationship should create proxy
        posts_proxy = user.posts
        assert isinstance(posts_proxy, RelationFieldProxy)
        assert posts_proxy.field_name == "posts"
        assert posts_proxy.instance == user

    def test_relationship_proxy_caching(self):
        """Test relationship proxy objects are cached properly"""
        # Create test user
        user = DeferredUser(username="author", email="author@example.com")

        # Create and cache proxy
        proxy1 = RelationFieldProxy(user, "posts")
        user._state_manager.update_object_cache("posts", proxy1)

        # Accessing again should return cached proxy
        cached_proxy = user._state_manager.get_object_cache().get("posts")
        assert cached_proxy is proxy1

    def test_relationship_proxy_error_handling(self):
        """Test relationship proxy error handling"""
        user = DeferredUser(username="author", email="author@example.com")
        proxy = RelationFieldProxy(user, "posts")

        # Should raise appropriate errors for unloaded relationships
        with pytest.raises(DeferredFieldError):
            iter(proxy)

        with pytest.raises(DeferredFieldError):
            len(proxy)

        with pytest.raises(DeferredFieldError):
            bool(proxy)


class TestDeferredFieldPerformance:
    """Test deferred field performance characteristics"""

    async def test_deferred_field_memory_efficiency(self, session):
        """Test that deferred fields save memory by not loading large content"""
        # Create user with large deferred content
        large_content = "x" * 10000  # 10KB of data
        user = await DeferredUser.objects.using(session).create(
            username="memory_user", email="test@example.com", bio="Small bio", large_content=large_content
        )

        # Load without deferred field (should include large content)
        full_user = await DeferredUser.objects.using(session).get(DeferredUser.id == user.id)
        # Load the deferred field first
        await full_user.load_deferred_field("large_content")
        assert len(full_user.large_content) == 10000

        # Load with deferred field (should not include large content)
        deferred_user = await DeferredUser.objects.using(session).defer("large_content").get(DeferredUser.id == user.id)
        assert deferred_user.is_field_deferred("large_content")
        assert not deferred_user.is_field_loaded("large_content")

    async def test_selective_deferred_field_loading(self, session):
        """Test loading only needed deferred fields"""
        # Create user with multiple deferred fields
        user = await DeferredUser.objects.using(session).create(
            username="selective_user",
            email="test@example.com",
            bio="Bio content",
            profile_data="Profile data",
            large_content="Large content",
            settings='{"key": "value"}',
        )

        # Load with all deferred
        loaded_user = (
            await DeferredUser.objects.using(session)
            .defer("bio", "profile_data", "large_content", "settings")
            .get(DeferredUser.id == user.id)
        )

        # Load only needed fields
        await loaded_user.load_deferred_fields(["bio", "settings"])

        # Only requested fields should be loaded
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.is_field_loaded("settings")
        assert not loaded_user.is_field_loaded("profile_data")
        assert not loaded_user.is_field_loaded("large_content")

    async def test_deferred_field_batch_loading(self, session):
        """Test efficient batch loading of deferred fields"""
        # Create multiple users with deferred content
        users_data = [
            {
                "username": f"batch_user{i}",
                "email": f"user{i}@example.com",
                "bio": f"Bio for user {i}",
                "profile_data": f"Profile data for user {i}",
            }
            for i in range(5)
        ]
        await DeferredUser.objects.using(session).bulk_create(users_data)

        # Load all users with deferred fields
        users = await DeferredUser.objects.using(session).defer("bio", "profile_data").all()

        # Load deferred fields for each user
        for user in users:
            await user.load_deferred_fields(["bio"])
            assert user.is_field_loaded("bio")
            assert not user.is_field_loaded("profile_data")


class TestDeferredFieldEdgeCases:
    """Test edge cases and error conditions for deferred fields"""

    async def test_deferred_field_with_null_values(self, session):
        """Test deferred fields with NULL values"""
        # Create user with NULL deferred field
        user = await DeferredUser.objects.using(session).create(
            username="null_user",
            email="test@example.com",
            bio=None,  # NULL value
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Load the NULL field
        await loaded_user.load_deferred_field("bio")
        assert loaded_user.is_field_loaded("bio")
        assert loaded_user.bio is None

    async def test_deferred_field_nonexistent_field(self, session):
        """Test loading nonexistent deferred field"""
        # Create user
        user = await DeferredUser.objects.using(session).create(username="nonexistent_user", email="test@example.com")

        # Try to load nonexistent field (should not raise error, just do nothing)
        await user.load_deferred_field("nonexistent_field")
        # Should complete without error

    async def test_deferred_field_already_loaded(self, session):
        """Test loading already loaded deferred field"""
        # Create user
        user = await DeferredUser.objects.using(session).create(
            username="already_loaded_user", email="test@example.com", bio="Test bio"
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Load field once
        await loaded_user.load_deferred_field("bio")
        assert loaded_user.is_field_loaded("bio")

        # Load again (should be no-op)
        await loaded_user.load_deferred_field("bio")
        assert loaded_user.is_field_loaded("bio")

    async def test_deferred_field_empty_list(self, session):
        """Test loading empty list of deferred fields"""
        # Create user
        user = await DeferredUser.objects.using(session).create(
            username="empty_list_user", email="test@example.com", bio="Test bio"
        )

        # Load with deferred field
        loaded_user = await DeferredUser.objects.using(session).defer("bio").get(DeferredUser.id == user.id)

        # Load empty list (should be no-op)
        await loaded_user.load_deferred_fields([])
        assert not loaded_user.is_field_loaded("bio")
