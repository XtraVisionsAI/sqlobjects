"""Unit tests for prefetch_related implementation

Tests the RelationshipAnalyzer and PrefetchHandler classes to ensure
proper relationship analysis and prefetch operations.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from sqlobjects.fields import Column, StringColumn, foreign_key, identity
from sqlobjects.fields.relations.prefetch import PrefetchHandler
from sqlobjects.fields.relations.utils import M2MTable, RelationshipAnalyzer
from tests.conftest import TestModel


class PrefetchTestUser(TestModel):
    """User model for prefetch testing"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)


class PrefetchTestPost(TestModel):
    """Post model for prefetch testing"""

    id: Column[int] = identity()
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("prefetch_test_users.id")


class TestRelationshipAnalyzer:
    """Test RelationshipAnalyzer functionality"""

    def test_analyze_many_to_one_relationship(self):
        """Test analyzing many-to-one (forward FK) relationships"""
        prop = Mock()
        prop.argument = "PrefetchTestUser"
        prop.secondary = None
        prop.foreign_keys = "author_id"

        original_resolve = RelationshipAnalyzer._resolve_model_class
        RelationshipAnalyzer._resolve_model_class = Mock(return_value=PrefetchTestUser)

        try:
            result = RelationshipAnalyzer._extract_relationship_info(PrefetchTestPost, prop)

            assert result is not None
            assert result["type"] == "many_to_one"
            assert result["related_model"] == PrefetchTestUser
            assert result["foreign_key_fields"][0] == "author_id"
            # _scan_ref_fields resolves the actual referenced column on the related model
            assert result["ref_fields"][0] == "id"
        finally:
            RelationshipAnalyzer._resolve_model_class = original_resolve

    def test_analyze_reverse_fk_relationship(self):
        """Test analyzing reverse FK relationships"""
        prop = Mock()
        prop.argument = "PrefetchTestPost"
        prop.secondary = None
        prop.foreign_keys = None
        prop.remote_fields = None
        prop.back_populates = None
        prop.uselist = True

        original_resolve = RelationshipAnalyzer._resolve_model_class
        RelationshipAnalyzer._resolve_model_class = Mock(return_value=PrefetchTestPost)

        try:
            result = RelationshipAnalyzer._extract_relationship_info(PrefetchTestUser, prop)

            assert result is not None
            assert result["type"] == "reverse_fk"
            assert result["related_model"] == PrefetchTestPost
            # Scan finds the actual FK column on PrefetchTestPost pointing to prefetch_test_users
            assert result["foreign_key_fields"][0] == "author_id"
            assert result["ref_fields"][0] == "id"
        finally:
            RelationshipAnalyzer._resolve_model_class = original_resolve

    def test_analyze_many_to_many_with_m2m_definition(self):
        """Test analyzing M2M relationships with M2MTable definition"""
        m2m_def = M2MTable(
            table_name="user_tags", left_model="User", right_model="Tag", left_field="user_id", right_field="tag_id"
        )

        prop = Mock()
        prop.argument = "Tag"
        prop.secondary = "user_tags"
        prop.m2m_definition = m2m_def

        original_resolve = RelationshipAnalyzer._resolve_model_class
        RelationshipAnalyzer._resolve_model_class = Mock(return_value=Mock(__name__="Tag"))

        try:
            result = RelationshipAnalyzer._extract_relationship_info(PrefetchTestUser, prop)

            assert result is not None
            assert result["type"] == "many_to_many"
            assert result["through_table"] == "user_tags"
            assert result["left_field"] == "user_id"
            assert result["right_field"] == "tag_id"
            assert result["left_ref_field"] == "id"
            assert result["right_ref_field"] == "id"
        finally:
            RelationshipAnalyzer._resolve_model_class = original_resolve

    def test_infer_reverse_relationship(self):
        """Test that _infer_reverse_relationship returns None (guessing removed)"""
        result = RelationshipAnalyzer._infer_reverse_relationship(PrefetchTestUser, "posts")
        assert result is None

    def test_extract_ref_field(self):
        """Test extracting reference field from foreign key specification"""
        assert RelationshipAnalyzer._extract_ref_field("users.username") == "username"
        assert RelationshipAnalyzer._extract_ref_field("posts.id") == "id"
        # plain column name returned as-is (not guessed as "id")
        assert RelationshipAnalyzer._extract_ref_field("author_id") == "author_id"
        assert RelationshipAnalyzer._extract_ref_field("user_id") == "user_id"


class TestPrefetchHandler:
    """Test PrefetchHandler functionality"""

    @pytest.fixture
    def mock_session(self):
        """Create mock session for testing"""
        session = Mock()
        session.execute = AsyncMock()
        session.scalars = AsyncMock()
        return session

    async def test_prefetch_reverse_fk_relationship(self, mock_session):
        """Test prefetching reverse FK relationships"""
        # Create mock instances with _update_cache method
        user1 = Mock()
        user1.id = 1
        user1._update_cache = Mock()

        user2 = Mock()
        user2.id = 2
        user2._update_cache = Mock()

        instances = [user1, user2]

        mock_post1 = Mock()
        mock_post1.author_id = 1
        mock_post2 = Mock()
        mock_post2.author_id = 1
        mock_post3 = Mock()
        mock_post3.author_id = 2

        mock_objects = Mock()
        mock_objects.using.return_value.filter.return_value.all = AsyncMock(
            return_value=[mock_post1, mock_post2, mock_post3]
        )
        PrefetchTestPost.objects = mock_objects

        handler = PrefetchHandler(mock_session)
        await handler._prefetch_by_fields(instances, "posts", PrefetchTestPost, ["id"], ["author_id"], [])

        # Verify _update_cache was called with correct data
        user1._update_cache.assert_called_once_with("posts", [mock_post1, mock_post2])
        user2._update_cache.assert_called_once_with("posts", [mock_post3])

    async def test_prefetch_many_to_one_relationship(self, mock_session):
        """Test prefetching many-to-one (forward FK) relationships"""
        # Create mock instances with _update_cache method
        post1 = Mock()
        post1.author_id = 1
        post1._update_cache = Mock()

        post2 = Mock()
        post2.author_id = 2
        post2._update_cache = Mock()

        instances = [post1, post2]

        mock_user1 = Mock()
        mock_user1.id = 1
        mock_user2 = Mock()
        mock_user2.id = 2

        mock_objects = Mock()
        mock_objects.using.return_value.filter.return_value.all = AsyncMock(return_value=[mock_user1, mock_user2])
        PrefetchTestUser.objects = mock_objects

        handler = PrefetchHandler(mock_session)
        await handler._prefetch_by_fields(instances, "author", PrefetchTestUser, ["author_id"], ["id"], None)

        # Verify _update_cache was called with correct data
        post1._update_cache.assert_called_once_with("author", mock_user1)
        post2._update_cache.assert_called_once_with("author", mock_user2)

    async def test_handle_prefetch_relationships_integration(self, mock_session):
        """Test the main handle_prefetch_relationships method"""
        # Create mock instance with _update_cache method
        user1 = Mock()
        user1.id = 1
        user1.__class__ = PrefetchTestUser  # type: ignore[reportAttributeAccessIssue]
        user1._update_cache = Mock()

        instances = [user1]

        prefetch_relationships = ["posts"]

        mock_relationship_info = {
            "type": "reverse_fk",
            "related_model": PrefetchTestPost,
            "foreign_key_fields": ["author_id"],
            "ref_fields": ["id"],
        }

        original_analyze = RelationshipAnalyzer.analyze_relationship
        RelationshipAnalyzer.analyze_relationship = Mock(return_value=mock_relationship_info)

        mock_post = Mock()
        mock_post.author_id = 1

        mock_objects = Mock()
        mock_objects.using.return_value.filter.return_value.all = AsyncMock(return_value=[mock_post])
        PrefetchTestPost.objects = mock_objects

        try:
            handler = PrefetchHandler(mock_session)
            result = await handler.handle_prefetch_relationships(instances, prefetch_relationships)

            assert result == instances
            # Verify _update_cache was called with correct data
            user1._update_cache.assert_called_once_with("posts", [mock_post])

            RelationshipAnalyzer.analyze_relationship.assert_called_once_with(PrefetchTestUser, "posts")
        finally:
            RelationshipAnalyzer.analyze_relationship = original_analyze

    async def test_handle_none_relationship_info(self, mock_session):
        """Test handling None relationship info"""
        instances = [Mock()]
        prefetch_relationships = ["nonexistent"]

        original_analyze = RelationshipAnalyzer.analyze_relationship
        RelationshipAnalyzer.analyze_relationship = Mock(return_value=None)

        try:
            handler = PrefetchHandler(mock_session)
            result = await handler.handle_prefetch_relationships(instances, prefetch_relationships)

            assert result == instances
        finally:
            RelationshipAnalyzer.analyze_relationship = original_analyze


class TestM2MTableDefaults:
    """Test M2MTable default field name generation"""

    def test_m2m_table_default_field_names(self):
        """Test that M2MTable generates correct default field names"""
        m2m_def = M2MTable(table_name="user_tags", left_model="User", right_model="Tag")

        assert m2m_def.left_field == "user_id"
        assert m2m_def.right_field == "tag_id"
        assert m2m_def.left_ref_field == "id"
        assert m2m_def.right_ref_field == "id"

    def test_m2m_table_custom_field_names(self):
        """Test that M2MTable preserves custom field names"""
        m2m_def = M2MTable(
            table_name="user_tags",
            left_model="User",
            right_model="Tag",
            left_field="custom_user_id",
            right_field="custom_tag_id",
            left_ref_field="username",
            right_ref_field="name",
        )

        assert m2m_def.left_field == "custom_user_id"
        assert m2m_def.right_field == "custom_tag_id"
        assert m2m_def.left_ref_field == "username"
        assert m2m_def.right_ref_field == "name"

    def test_m2m_table_partial_custom_names(self):
        """Test M2MTable with some custom and some default names"""
        m2m_def = M2MTable(
            table_name="user_tags",
            left_model="User",
            right_model="Tag",
            left_field="custom_user_id",
            left_ref_field="username",
        )

        assert m2m_def.left_field == "custom_user_id"
        assert m2m_def.right_field == "tag_id"  # default
        assert m2m_def.left_ref_field == "username"
        assert m2m_def.right_ref_field == "id"  # default
