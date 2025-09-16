"""Unit tests for relationship validation in select_related and prefetch_related"""

import pytest

from sqlobjects.fields import Column, StringColumn, foreign_key, identity
from tests.conftest import TestModel


class RelationTestUser(TestModel):
    """User model for relationship validation testing"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)


class RelationTestPost(TestModel):
    """Post model with foreign key for relationship validation testing"""

    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = StringColumn(length=1000)
    author_id: Column[int] = foreign_key("relation_test_users.id")


class TestRelationshipValidation:
    """Test relationship validation in select_related and prefetch_related"""

    async def test_valid_relationship_select_related(self, session):
        """Test that valid relationships work correctly"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Valid relationship should work
        posts = await RelationTestPost.objects.using(session).select_related("author").all()
        assert len(posts) == 1
        assert posts[0].title == "Test Post"

    async def test_invalid_relationship_select_related(self, session):
        """Test that invalid relationships raise ValueError with helpful message"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Invalid relationship should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await RelationTestPost.objects.using(session).select_related("nonexistent_relation").all()

        error_message = str(exc_info.value)
        assert "Invalid relationship 'nonexistent_relation'" in error_message
        assert "Available relationships: ['author']" in error_message

    async def test_nested_invalid_relationship_select_related(self, session):
        """Test that nested invalid relationships raise ValueError"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Nested invalid relationship should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await RelationTestPost.objects.using(session).select_related("author__nonexistent").all()

        error_message = str(exc_info.value)
        assert "Invalid relationship 'nonexistent'" in error_message
        assert "author__nonexistent" in error_message

    async def test_non_foreign_key_field_error(self, session):
        """Test error when trying to use non-foreign key field as relationship"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Using regular field as relationship should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await RelationTestPost.objects.using(session).select_related("title").all()

        error_message = str(exc_info.value)
        assert "Invalid relationship 'title'" in error_message

    async def test_valid_relationship_prefetch_related(self, session):
        """Test that valid relationships work with prefetch_related"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Valid relationship should work with prefetch_related
        # Note: This tests the path validation, actual prefetch logic may vary
        posts = await RelationTestPost.objects.using(session).prefetch_related("author").all()
        assert len(posts) == 1
        assert posts[0].title == "Test Post"

    async def test_invalid_relationship_prefetch_related(self, session):
        """Test that invalid relationships raise ValueError in prefetch_related"""
        # Create test data
        user = await RelationTestUser.objects.using(session).create(username="testuser", email="test@example.com")

        _ = await RelationTestPost.objects.using(session).create(
            title="Test Post", content="Test content", author_id=user.id
        )

        # Invalid relationship should raise ValueError in prefetch_related too
        with pytest.raises(ValueError) as exc_info:
            await RelationTestPost.objects.using(session).prefetch_related("nonexistent_relation").all()

        error_message = str(exc_info.value)
        assert "Invalid relationship 'nonexistent_relation'" in error_message

    def test_relationship_path_format_validation(self):
        """Test that _get_relationship_path validates string format"""
        from sqlobjects.queryset import QuerySet

        # Valid paths should work
        assert QuerySet._get_relationship_path("author") == "author"
        assert QuerySet._get_relationship_path("author__profile") == "author__profile"
        assert QuerySet._get_relationship_path("user__posts__tags") == "user__posts__tags"

        # Invalid paths should raise ValueError
        with pytest.raises(ValueError):
            QuerySet._get_relationship_path("")  # Empty string

        with pytest.raises(ValueError):
            QuerySet._get_relationship_path("123invalid")  # Starts with number

        with pytest.raises(ValueError):
            QuerySet._get_relationship_path("invalid-name")  # Contains hyphen

        with pytest.raises(ValueError):
            QuerySet._get_relationship_path("invalid.name")  # Contains dot

    def test_error_message_quality(self):
        """Test that error messages are helpful and informative"""
        # This is tested indirectly through the other tests, but we can verify
        # the error message format here

        # The error messages should:
        # 1. Clearly state what relationship is invalid
        # 2. Show the full path being processed
        # 3. List available relationships when possible
        # 4. Be in English and user-friendly

        # These are verified in the integration tests above
        pass
