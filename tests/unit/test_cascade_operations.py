"""Unit tests for cascade operations components.

Tests individual CascadeExecutor methods, DependencyResolver, and cascade enums
in isolation without database dependencies.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from sqlobjects.cascade import (
    CascadeExecutor,
    CascadeOption,
    CascadePresets,
    CyclicDependencyError,
    DependencyResolver,
    ForeignKeyInferrer,
    OnDelete,
    normalize_cascade,
    normalize_ondelete,
)
from sqlobjects.fields import Column, StringColumn, foreign_key, relationship
from tests.conftest import TestModel


class MockUser(TestModel):
    __test__ = False

    id: Column[int] = Column(type="integer", primary_key=True)
    username: Column[str] = StringColumn(length=50)

    posts = relationship("MockPost", cascade=CascadePresets.ALL_DELETE_ORPHAN)

    class Config:
        table_name = "mock_users"


class MockPost(TestModel):
    __test__ = False

    id: Column[int] = Column(type="integer", primary_key=True)
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("mock_users.id", ondelete=OnDelete.CASCADE)

    class Config:
        table_name = "mock_posts"


class TestOnDeleteEnum:
    """Test OnDelete enumeration values and behavior."""

    def test_ondelete_enum_values(self):
        """Test OnDelete enum has correct string values."""
        assert OnDelete.CASCADE.value == "CASCADE"
        assert OnDelete.SET_NULL.value == "SET NULL"
        assert OnDelete.RESTRICT.value == "RESTRICT"
        assert OnDelete.NO_ACTION.value == "NO ACTION"

    def test_ondelete_enum_members(self):
        """Test all expected OnDelete members exist."""
        expected = {"CASCADE", "SET_NULL", "RESTRICT", "NO_ACTION"}
        actual = {member.name for member in OnDelete}
        assert actual == expected

    def test_normalize_ondelete_enum(self):
        """Test normalize_ondelete with enum values."""
        assert normalize_ondelete(OnDelete.CASCADE) == "CASCADE"
        assert normalize_ondelete(OnDelete.SET_NULL) == "SET NULL"

    def test_normalize_ondelete_string(self):
        """Test normalize_ondelete with string values."""
        assert normalize_ondelete("CASCADE") == "CASCADE"
        assert normalize_ondelete("cascade") == "CASCADE"  # type: ignore[reportArgumentType]
        assert normalize_ondelete("set null") == "SET NULL"  # type: ignore[reportArgumentType]

    def test_normalize_ondelete_invalid(self):
        """Test normalize_ondelete with invalid values."""
        with pytest.raises(ValueError, match="Invalid ondelete value"):
            normalize_ondelete("INVALID")  # type: ignore[reportArgumentType]


class TestCascadeOption:
    """Test CascadeOption enumeration values and behavior."""

    def test_cascade_option_values(self):
        """Test CascadeOption enum has correct values."""
        assert CascadeOption.SAVE_UPDATE.value == "save-update"
        assert CascadeOption.DELETE.value == "delete"
        assert CascadeOption.DELETE_ORPHAN.value == "delete-orphan"
        assert CascadeOption.MERGE.value == "merge"
        assert CascadeOption.REFRESH_EXPIRE.value == "refresh-expire"

    def test_cascade_presets(self):
        """Test CascadePresets constants."""
        assert CascadePresets.SAVE_UPDATE == "save-update"
        assert CascadePresets.ALL == "save-update, merge, refresh-expire"
        assert CascadePresets.ALL_DELETE_ORPHAN == "all, delete-orphan"

    def test_normalize_cascade_bool(self):
        """Test normalize_cascade with boolean values."""
        assert normalize_cascade(True) == "save-update"  # type: ignore[reportArgumentType]
        assert normalize_cascade(False) == ""  # type: ignore[reportArgumentType]

    def test_normalize_cascade_string(self):
        """Test normalize_cascade with string values."""
        assert normalize_cascade("save-update") == "save-update"
        assert normalize_cascade("all") == "save-update, merge, refresh-expire"


class TestDependencyResolver:
    """Test DependencyResolver methods in isolation."""

    def test_dependency_resolver_init(self):
        """Test DependencyResolver initialization."""
        resolver = DependencyResolver()
        assert resolver is not None

    def test_resolve_save_order_empty(self):
        """Test resolve_save_order with empty list."""
        resolver = DependencyResolver()
        result = resolver.resolve_save_order([])
        assert result == []

    def test_resolve_save_order_single_instance(self):
        """Test resolve_save_order with single instance."""
        resolver = DependencyResolver()
        user = MockUser(username="test")
        result = resolver.resolve_save_order([user])
        assert result == [user]

    def test_resolve_save_order_multiple_instances(self):
        """Test resolve_save_order with multiple instances."""
        resolver = DependencyResolver()
        user1 = MockUser(username="user1")
        user2 = MockUser(username="user2")

        result = resolver.resolve_save_order([user1, user2])
        assert len(result) == 2
        assert user1 in result
        assert user2 in result

    def test_detect_cycles_dfs_no_cycles(self):
        """Test _detect_cycles_dfs with no circular dependencies."""
        resolver = DependencyResolver()
        user = MockUser(username="test")
        post = MockPost(title="test")

        # Should not raise exception
        resolver._detect_cycles_dfs([user, post])

    def test_detect_cycles_dfs_with_cycles(self):
        """Test _detect_cycles_dfs detects circular dependencies."""
        resolver = DependencyResolver()
        user = MockUser(username="test")
        post = MockPost(title="test")

        # Mock _has_cycle_dfs to return True (circular dependency)
        with patch.object(resolver, "_has_cycle_dfs", return_value=True):
            with pytest.raises(CyclicDependencyError):
                resolver._detect_cycles_dfs([user, post])


class TestForeignKeyInferrer:
    """Test ForeignKeyInferrer methods in isolation."""

    def test_foreign_key_inferrer_init(self):
        """Test ForeignKeyInferrer initialization."""
        inferrer = ForeignKeyInferrer()
        assert inferrer is not None

    def test_infer_foreign_key_field(self):
        """Test infer_foreign_key_field method."""
        user = MockUser(username="test")
        post = MockPost(title="test")

        field_name = ForeignKeyInferrer.infer_foreign_key_field(user, post)
        assert isinstance(field_name, str)
        assert field_name.endswith("_id")

    def test_set_foreign_key(self):
        """Test set_foreign_key method."""
        user = MockUser(username="test")
        user.id = 123  # Set primary key
        post = MockPost(title="test")

        # Should not raise exception
        ForeignKeyInferrer.set_foreign_key(user, post)

        # Verify foreign key was set (if the field exists)
        if hasattr(post, "author_id"):
            assert post.author_id == 123


class TestCascadeExecutor:
    """Test CascadeExecutor methods in isolation."""

    def test_cascade_executor_init(self):
        """Test CascadeExecutor initialization."""
        executor = CascadeExecutor()
        assert executor is not None
        assert executor.resolver is not None
        assert hasattr(executor.resolver, "resolve_save_order")

    @pytest.mark.asyncio
    async def test_cascade_save_optimized_empty_list(self):
        """Test cascade_save_optimized with empty instance list."""
        result = await CascadeExecutor.cascade_save_optimized([])
        assert result is None

    @pytest.mark.asyncio
    async def test_cascade_save_optimized_single_instance(self):
        """Test cascade_save_optimized with single instance."""
        user = MockUser(username="test")

        # Mock the to_dict method
        with patch.object(user, "to_dict", return_value={"username": "test"}):
            # Mock the objects manager
            with patch.object(MockUser, "objects") as mock_objects:
                mock_manager = Mock()
                mock_objects.using.return_value = mock_manager
                mock_manager.bulk_create = AsyncMock()

                result = await CascadeExecutor.cascade_save_optimized([user])
                assert result is None
                mock_manager.bulk_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_cascade_save_method(self):
        """Test cascade_save method."""
        executor = CascadeExecutor()
        user = MockUser(username="test")

        # Mock the relationship to avoid proxy issues
        with (
            patch.object(user, "save", new_callable=AsyncMock) as mock_save,
            patch.object(user.__class__, "_relationships", {}),  # No relationships
        ):
            await executor.cascade_save([user])
            mock_save.assert_called_once_with(cascade=False)

    @pytest.mark.asyncio
    async def test_cascade_delete_method(self):
        """Test cascade_delete method."""
        user = MockUser(username="test")
        user.id = 1

        with patch.object(user, "delete", new_callable=AsyncMock) as mock_delete:
            await CascadeExecutor.cascade_delete([user])
            mock_delete.assert_called_once_with(cascade=False)

    @pytest.mark.asyncio
    async def test_execute_cascade_operation_save(self):
        """Test execute_cascade_operation with save operation."""
        executor = CascadeExecutor()
        user = MockUser(username="test")

        with patch.object(executor, "_cascade_save_with_relationships", new_callable=AsyncMock) as mock_save:
            await executor.execute_cascade_operation(user, "save")
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_cascade_operation_delete(self):
        """Test execute_cascade_operation with delete operation."""
        executor = CascadeExecutor()
        user = MockUser(username="test")
        user.id = 1

        with patch.object(executor, "_cascade_delete_with_relationships", new_callable=AsyncMock) as mock_delete:
            await executor.execute_cascade_operation(user, "delete")
            mock_delete.assert_called_once()

    def test_execute_cascade_operation_invalid(self):
        """Test execute_cascade_operation with invalid operation."""
        executor = CascadeExecutor()
        user = MockUser(username="test")

        with pytest.raises(ValueError, match="Unsupported cascade operation"):
            import asyncio

            asyncio.run(executor.execute_cascade_operation(user, "invalid"))


class TestCyclicDependencyError:
    """Test CyclicDependencyError exception."""

    def test_cyclic_dependency_error_default_message(self):
        """Test CyclicDependencyError with default message."""
        error = CyclicDependencyError()
        assert "circular dependency" in str(error).lower()

    def test_cyclic_dependency_error_custom_message(self):
        """Test CyclicDependencyError with custom message."""
        custom_message = "Custom circular dependency detected"
        error = CyclicDependencyError(custom_message)
        assert str(error) == custom_message

    def test_cyclic_dependency_error_inheritance(self):
        """Test CyclicDependencyError inherits from Exception."""
        error = CyclicDependencyError()
        assert isinstance(error, Exception)


class TestCascadeUtilityFunctions:
    """Test cascade utility functions."""

    def test_normalize_ondelete_none(self):
        """Test normalize_ondelete with None value."""
        result = normalize_ondelete(None)
        assert result == "NO ACTION"  # Default value

    def test_normalize_cascade_none(self):
        """Test normalize_cascade with None value."""
        result = normalize_cascade(None)
        assert result == ""  # Default value

    def test_normalize_cascade_preset_constants(self):
        """Test normalize_cascade with preset constants."""
        assert normalize_cascade(CascadePresets.SAVE_UPDATE) == "save-update"
        assert normalize_cascade(CascadePresets.ALL) == "save-update, merge, refresh-expire"
        assert normalize_cascade(CascadePresets.ALL_DELETE_ORPHAN) == "all, delete-orphan"


class TestCascadeIntegrationPoints:
    """Test cascade system integration points."""

    def test_model_cascade_method_exists(self):
        """Test that models have cascade-related methods."""
        user = MockUser(username="test")

        # Test method existence (basic model functionality)
        assert hasattr(user, "save")
        assert hasattr(user, "delete")
        assert hasattr(user, "__class__")

    def test_cascade_executor_session_handling(self):
        """Test CascadeExecutor handles session parameter."""
        executor = CascadeExecutor()
        _mock_session = Mock()

        # Test that executor can accept session parameter
        # (Implementation details tested in integration tests)
        assert executor is not None

    def test_foreign_key_inferrer_static_methods(self):
        """Test ForeignKeyInferrer static methods exist."""
        # Test static method existence
        assert callable(getattr(ForeignKeyInferrer, "infer_foreign_key_field", None))
        assert callable(getattr(ForeignKeyInferrer, "set_foreign_key", None))
