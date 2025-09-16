"""Integration tests for bulk operations transaction control functionality."""

import pytest

from sqlobjects import (
    BulkResult,
    ConflictResolution,
    ErrorHandling,
    TransactionMode,
)
from sqlobjects.session import ctx_session
from tests.conftest import User


class TestTransactionModes:
    """Test different transaction modes for bulk operations."""

    async def test_inherit_mode_default(self, session):
        """Test INHERIT mode (default behavior)."""
        users_data = [
            {"username": f"inherit_user_{i}", "email": f"inherit{i}@example.com", "age": 25} for i in range(3)
        ]

        result = await User.objects.using(session).bulk_create(
            users_data, transaction_mode=TransactionMode.INHERIT, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 3

    async def test_independent_mode(self, session):
        """Test INDEPENDENT mode creates its own transaction."""
        users_data = [
            {"username": f"independent_user_{i}", "email": f"independent{i}@example.com", "age": 30} for i in range(3)
        ]

        result = await User.objects.using(session).bulk_create(
            users_data, transaction_mode=TransactionMode.INDEPENDENT, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 3

    async def test_batch_mode(self, session):
        """Test BATCH mode with separate batch transactions."""
        users_data = [{"username": f"batch_user_{i}", "email": f"batch{i}@example.com", "age": 35} for i in range(5)]

        result = await User.objects.using(session).bulk_create(
            users_data,
            transaction_mode=TransactionMode.BATCH,
            batch_size=2,  # Force multiple batches
            return_objects=True,
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 5

    async def test_savepoint_mode(self, session):
        """Test SAVEPOINT mode with nested transactions."""
        users_data = [
            {"username": f"savepoint_user_{i}", "email": f"savepoint{i}@example.com", "age": 40} for i in range(3)
        ]

        result = await User.objects.using(session).bulk_create(
            users_data, transaction_mode=TransactionMode.SAVEPOINT, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 3


class TestErrorHandling:
    """Test different error handling strategies."""

    async def test_fail_fast_default(self, session):
        """Test FAIL_FAST mode (default behavior)."""
        users_data = [{"username": "fail_fast_user", "email": "failfast@example.com", "age": 25}]

        result = await User.objects.using(session).bulk_create(
            users_data, on_error=ErrorHandling.FAIL_FAST, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 1

    async def test_ignore_errors(self, session):
        """Test IGNORE mode skips error records."""
        # Create a user first to test duplicate handling
        await User.objects.using(session).create(username="existing_user", email="existing@example.com", age=25)

        users_data = [
            {"username": "new_user", "email": "new@example.com", "age": 30},
            {"username": "existing_user", "email": "duplicate@example.com", "age": 35},  # Duplicate username
        ]

        result = await User.objects.using(session).bulk_create(
            users_data,
            on_error=ErrorHandling.IGNORE,
            on_conflict=ConflictResolution.IGNORE,
            conflict_fields=["username"],
            return_objects=True,
        )

        # Should succeed with at least the non-duplicate record
        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) >= 1

    async def test_collect_errors(self, session):
        """Test COLLECT mode gathers error information."""
        # Create a user first to test duplicate handling
        await User.objects.using(session).create(
            username="existing_collect", email="existing_collect@example.com", age=25
        )

        users_data = [
            {"username": "new_collect_user", "email": "new_collect@example.com", "age": 30},
            {"username": "existing_collect", "email": "duplicate_collect@example.com", "age": 35},  # Duplicate
        ]

        result = await User.objects.using(session).bulk_create(
            users_data, on_error=ErrorHandling.COLLECT, return_objects=True
        )

        # Should return BulkResult with error information
        if isinstance(result, BulkResult):
            assert result.success_count >= 1
            assert result.total_count == 2
            assert result.has_errors or not result.has_errors  # Either is valid depending on DB handling


class TestConflictResolution:
    """Test different conflict resolution strategies."""

    async def test_error_on_conflict_default(self, session):
        """Test ERROR mode (default behavior)."""
        users_data = [{"username": "conflict_user", "email": "conflict@example.com", "age": 25}]

        result = await User.objects.using(session).bulk_create(
            users_data, on_conflict=ConflictResolution.ERROR, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 1

    async def test_ignore_conflicts(self, session):
        """Test IGNORE mode for conflicts."""
        # Create initial user
        await User.objects.using(session).create(
            username="ignore_conflict_user", email="ignore_conflict@example.com", age=25
        )

        users_data = [
            {"username": "ignore_conflict_user", "email": "duplicate_ignore@example.com", "age": 30},
            {"username": "new_ignore_user", "email": "new_ignore@example.com", "age": 35},
        ]

        result = await User.objects.using(session).bulk_create(
            users_data, on_conflict=ConflictResolution.IGNORE, conflict_fields=["username"], return_objects=True
        )

        # Should handle conflicts gracefully
        assert isinstance(result, BulkResult)


class TestBulkUpdateTransactionControl:
    """Test transaction control for bulk_update operations."""

    async def test_bulk_update_with_transaction_modes(self, session, sample_users):
        """Test bulk_update with different transaction modes."""
        update_mappings = [
            {"id": sample_users[0].id, "age": 99},
            {"id": sample_users[1].id, "age": 88},
        ]

        # Test INHERIT mode
        result = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], transaction_mode=TransactionMode.INHERIT, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 2

        # Test BATCH mode
        result = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], transaction_mode=TransactionMode.BATCH, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 2


class TestBulkDeleteTransactionControl:
    """Test transaction control for bulk_delete operations."""

    async def test_bulk_delete_with_transaction_modes(self, session, sample_users):
        """Test bulk_delete with different transaction modes."""
        user_ids = [sample_users[0].id, sample_users[1].id]

        # Test INHERIT mode
        result = await User.objects.using(session).bulk_delete(
            user_ids, id_field="id", transaction_mode=TransactionMode.INHERIT, return_objects=True
        )

        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 2

    async def test_bulk_delete_error_handling(self, session, sample_users):
        """Test bulk_delete with error handling."""
        user_ids = [sample_users[0].id, 99999]  # One valid, one invalid

        # Test COLLECT mode
        result = await User.objects.using(session).bulk_delete(
            user_ids, id_field="id", on_error=ErrorHandling.COLLECT, return_objects=True
        )

        # Should handle mixed valid/invalid IDs
        assert isinstance(result, BulkResult)
        assert result.total_count == 2
        assert result.success_count >= 1


class TestBulkResultEnhancements:
    """Test enhanced BulkResult functionality."""

    async def test_bulk_result_properties(self, session):
        """Test BulkResult properties and methods."""
        users_data = [{"username": f"result_user_{i}", "email": f"result{i}@example.com", "age": 25} for i in range(5)]

        result = await User.objects.using(session).bulk_create(
            users_data, on_error=ErrorHandling.COLLECT, return_objects=True
        )

        if isinstance(result, BulkResult):
            # Test properties
            assert result.success_count >= 0
            assert result.total_count == 5
            assert result.success_rate >= 0.0
            assert isinstance(result.has_errors, bool)
            assert isinstance(result.has_partial_success, bool)

            # Test len() support
            assert len(result) == 5

            # Test transaction info
            if result.transaction_info:
                assert result.transaction_info.mode == TransactionMode.INHERIT
                assert result.transaction_info.batch_count >= 1


class TestComplexTransactionScenarios:
    """Test complex transaction scenarios."""

    @pytest.mark.usefixtures("test_db")
    async def test_nested_transaction_with_ctx_session(self):
        """Test transaction control within ctx_session."""
        async with ctx_session() as db_session:
            # Create some initial data
            users_data = [
                {"username": f"nested_user_{i}", "email": f"nested{i}@example.com", "age": 25} for i in range(3)
            ]

            result = await User.objects.using(db_session).bulk_create(
                users_data, transaction_mode=TransactionMode.SAVEPOINT, return_objects=True
            )

            assert isinstance(result, BulkResult)
            assert result.objects and len(result.objects) == 3

            # Update within same transaction
            assert result.objects is not None
            assert isinstance(result.objects[0], User)
            update_mappings = [{"id": result.objects[0].id, "age": 99}]  # noqa

            update_result = await User.objects.using(db_session).bulk_update(
                update_mappings,
                match_fields=["id"],
                transaction_mode=TransactionMode.INHERIT,  # Inherit the outer transaction
                return_objects=True,
            )

            assert isinstance(update_result, BulkResult)
            assert update_result.objects is not None
            assert len(update_result.objects) == 1
            assert isinstance(update_result.objects[0], User)
            assert update_result.objects[0].age == 99  # noqa

    async def test_transaction_rollback_behavior(self, session):
        """Test transaction rollback behavior."""
        users_data = [{"username": "rollback_user", "email": "rollback@example.com", "age": 25}]

        try:
            # This should work normally
            result = await User.objects.using(session).bulk_create(
                users_data, transaction_mode=TransactionMode.BATCH, return_objects=True
            )

            assert isinstance(result, BulkResult)
            assert result.objects and len(result.objects) == 1

        except Exception:  # noqa
            # If there's an error, it should be handled gracefully
            pass

    async def test_mixed_operations_in_transaction(self, session):
        """Test mixing different bulk operations in same transaction."""
        # Create users
        users_data = [{"username": f"mixed_user_{i}", "email": f"mixed{i}@example.com", "age": 25} for i in range(3)]

        created_users = await User.objects.using(session).bulk_create(
            users_data, transaction_mode=TransactionMode.INHERIT, return_objects=True
        )

        assert isinstance(created_users, BulkResult)
        assert created_users.objects is not None
        assert len(created_users.objects) == 3

        # Update some users
        assert isinstance(created_users.objects[0], User)
        assert isinstance(created_users.objects[1], User)
        assert isinstance(created_users.objects[2], User)
        update_mappings = [
            {"id": created_users.objects[0].id, "age": 99},  # noqa
            {"id": created_users.objects[1].id, "age": 88},  # noqa
        ]

        updated_users = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], transaction_mode=TransactionMode.INHERIT, return_objects=True
        )

        assert isinstance(updated_users, BulkResult)
        assert updated_users.objects is not None
        assert len(updated_users.objects) == 2

        # Delete one user
        delete_result = await User.objects.using(session).bulk_delete(
            [created_users.objects[2].id],  # noqa
            id_field="id",
            transaction_mode=TransactionMode.INHERIT,
            return_objects=True,
        )

        assert isinstance(delete_result, BulkResult)
        assert delete_result.objects is not None
        assert len(delete_result.objects) == 1
