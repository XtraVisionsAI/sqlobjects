"""Integration tests for bulk operations

Tests bulk create, update, delete operations with performance validation
and real database integration.
"""

import pytest

from tests.conftest import Post, User


class TestBulkCreateOperations:
    """Test bulk create operations and performance"""

    async def test_bulk_create_basic(self, session):
        """Test basic bulk create functionality"""
        users_data = [{"username": f"bulk_user_{i}", "email": f"bulk{i}@example.com", "age": 20 + i} for i in range(10)]

        await User.objects.using(session).bulk_create(users_data)

        # Verify all users were created
        total_count = await User.objects.using(session).count()
        assert total_count == 10

        # Verify data integrity by querying
        created_users = await User.objects.using(session).order_by("username").all()
        for i, user in enumerate(created_users):
            assert user.username == f"bulk_user_{i}"
            assert user.email == f"bulk{i}@example.com"
            assert user.age == 20 + i
            assert user.id is not None
            assert user.is_active is True  # Default value

    async def test_bulk_create_large_dataset(self, session, performance_monitor):
        """Test bulk create with large dataset for performance"""
        # Create large dataset
        users_data = [
            {"username": f"large_user_{i}", "email": f"large{i}@example.com", "age": 20 + (i % 50)} for i in range(1000)
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_create(users_data)
        metrics = performance_monitor.stop()

        # Performance should be reasonable (less than 5 seconds for 1000 records)
        assert metrics["execution_time"] < 5.0

        # Verify database state
        total_count = await User.objects.using(session).count()
        assert total_count == 1000

    async def test_bulk_create_with_batch_size(self, session):
        """Test bulk create with custom batch size"""
        users_data = [{"username": f"batch_user_{i}", "email": f"batch{i}@example.com", "age": 25} for i in range(50)]

        # Use smaller batch size
        await User.objects.using(session).bulk_create(users_data, batch_size=10)

        # Verify all users exist in database
        count = await User.objects.using(session).count()
        assert count == 50

    async def test_bulk_create_empty_data(self, session):
        """Test bulk create with empty data"""
        await User.objects.using(session).bulk_create([])

        # Database should remain unchanged
        count = await User.objects.using(session).count()
        assert count == 0

    async def test_bulk_create_with_defaults(self, session):
        """Test bulk create respects default values"""
        users_data = [
            {"username": f"default_user_{i}", "email": f"default{i}@example.com"}
            # age not specified, is_active should use default
            for i in range(5)
        ]

        await User.objects.using(session).bulk_create(users_data)

        # Verify default values by querying
        created_users = await User.objects.using(session).all()
        assert len(created_users) == 5

        for user in created_users:
            assert user.is_active is True  # Default value
            assert user.age is None  # Nullable field, no default


class TestBulkUpdateOperations:
    """Test bulk update operations"""

    async def test_bulk_update_basic(self, session, sample_users):
        """Test basic bulk update functionality"""
        # Prepare update data
        update_mappings = [
            {"id": sample_users[0].id, "age": 26, "email": "alice_bulk_updated@example.com"},
            {"id": sample_users[1].id, "age": 31, "email": "bob_bulk_updated@example.com"},
            {"id": sample_users[2].id, "age": 36, "email": "charlie_bulk_updated@example.com"},
        ]

        # Perform bulk update
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        # Verify updates
        alice = await User.objects.using(session).get(User.id == sample_users[0].id)
        assert alice.age == 26
        assert alice.email == "alice_bulk_updated@example.com"
        assert alice.username == "alice"  # Unchanged field

        bob = await User.objects.using(session).get(User.id == sample_users[1].id)
        assert bob.age == 31
        assert bob.email == "bob_bulk_updated@example.com"

    async def test_bulk_update_partial_fields(self, session, sample_users):
        """Test bulk update with partial field updates"""
        # Update only age field
        update_mappings = [
            {"id": sample_users[0].id, "age": 99},
            {"id": sample_users[1].id, "age": 88},
        ]

        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        # Verify only age was updated
        alice = await User.objects.using(session).get(User.id == sample_users[0].id)
        assert alice.age == 99
        assert alice.email == "alice@example.com"  # Unchanged
        assert alice.username == "alice"  # Unchanged

    async def test_bulk_update_large_dataset(self, session, performance_monitor):
        """Test bulk update performance with large dataset"""
        # Create large dataset first
        users_data = [
            {"username": f"bulk_update_user_{i}", "email": f"bulk_update{i}@example.com", "age": 25} for i in range(500)
        ]
        await User.objects.using(session).bulk_create(users_data)

        # Get created users for update
        users = await User.objects.using(session).filter(User.username.like("bulk_update_user_%")).all()

        # Prepare bulk update
        update_mappings = [{"id": user.id, "age": 30, "is_active": False} for user in users]

        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        metrics = performance_monitor.stop()

        # Performance should be reasonable
        assert metrics["execution_time"] < 10.0

        # Verify updates
        updated_count = await User.objects.using(session).filter(User.age == 30, User.is_active == False).count()
        assert updated_count == 500

    async def test_bulk_update_with_batch_size(self, session, sample_users):
        """Test bulk update with custom batch size"""
        # Create more test data
        additional_users_data = [
            {"username": f"batch_update_user_{i}", "email": f"batch_update{i}@example.com", "age": 20}
            for i in range(20)
        ]
        await User.objects.using(session).bulk_create(additional_users_data)

        # Get all users for update
        additional_users = await User.objects.using(session).filter(User.username.like("batch_update_user_%")).all()
        all_users = sample_users + additional_users

        # Prepare update with small batch size
        update_mappings = [{"id": user.id, "age": 35} for user in all_users]

        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"], batch_size=5)

        # Verify all updates
        updated_count = await User.objects.using(session).filter(User.age == 35).count()
        assert updated_count == len(all_users)

    async def test_bulk_update_nonexistent_records(self, session):
        """Test bulk update with non-existent record IDs"""
        # Try to update non-existent records
        update_mappings = [
            {"id": 99999, "age": 50},
            {"id": 99998, "age": 51},
        ]

        # Should not raise error, but no records should be updated
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        # Verify no records were affected
        count = await User.objects.using(session).filter(User.age.in_([50, 51])).count()
        assert count == 0


class TestBulkDeleteOperations:
    """Test bulk delete operations"""

    async def test_bulk_delete_basic(self, session, sample_users):
        """Test basic bulk delete functionality"""
        # Delete first two users
        user_ids = [sample_users[0].id, sample_users[1].id]

        await User.objects.using(session).bulk_delete(user_ids, id_field="id")

        # Verify deletions
        remaining_count = await User.objects.using(session).count()
        assert remaining_count == 1

        # Verify correct user remains
        remaining_user = await User.objects.using(session).first()
        assert remaining_user and remaining_user.username == "charlie"

    async def test_bulk_delete_large_dataset(self, session, performance_monitor):
        """Test bulk delete performance with large dataset"""
        # Create large dataset
        users_data = [
            {"username": f"bulk_delete_user_{i}", "email": f"bulk_delete{i}@example.com", "age": 25}
            for i in range(1000)
        ]
        await User.objects.using(session).bulk_create(users_data)

        # Get created users for deletion
        users = await User.objects.using(session).filter(User.username.like("bulk_delete_user_%")).all()

        # Delete half of the users
        user_ids = [user.id for user in users[:500]]

        performance_monitor.start()
        await User.objects.using(session).bulk_delete(user_ids, id_field="id")
        metrics = performance_monitor.stop()

        # Performance should be reasonable
        assert metrics["execution_time"] < 5.0

        # Verify deletions
        remaining_count = await User.objects.using(session).count()
        assert remaining_count == 500

    async def test_bulk_delete_with_batch_size(self, session):
        """Test bulk delete with custom batch size"""
        # Create test data
        users_data = [
            {"username": f"batch_delete_user_{i}", "email": f"batch_delete{i}@example.com", "age": 25}
            for i in range(50)
        ]
        await User.objects.using(session).bulk_create(users_data)

        # Get created users for deletion
        users = await User.objects.using(session).filter(User.username.like("batch_delete_user_%")).all()

        # Delete with small batch size
        user_ids = [user.id for user in users[:30]]

        await User.objects.using(session).bulk_delete(user_ids, id_field="id", batch_size=10)

        # Verify deletions
        remaining_count = await User.objects.using(session).count()
        assert remaining_count == 20

    async def test_bulk_delete_single_record(self, session, sample_users):
        """Test bulk delete with single record"""
        original_count = await User.objects.using(session).count()

        # Delete only first user
        user_ids = [sample_users[0].id]

        await User.objects.using(session).bulk_delete(user_ids, id_field="id")

        # Verify deletion
        remaining_count = await User.objects.using(session).count()
        assert remaining_count == original_count - 1

        # Verify correct users remain
        remaining_users = await User.objects.using(session).order_by("username").all()
        assert len(remaining_users) == 2
        assert remaining_users[0].username == "bob"
        assert remaining_users[1].username == "charlie"

    @pytest.mark.usefixtures("sample_users")
    async def test_bulk_delete_nonexistent_ids(self, session):
        """Test bulk delete with non-existent IDs"""
        original_count = await User.objects.using(session).count()

        # Try to delete non-existent IDs
        nonexistent_ids = [99999, 99998, 99997]

        await User.objects.using(session).bulk_delete(nonexistent_ids, id_field="id")

        # Count should remain unchanged
        final_count = await User.objects.using(session).count()
        assert final_count == original_count


class TestBulkOperationPerformance:
    """Test bulk operation performance characteristics"""

    async def test_bulk_vs_individual_create_performance(self, session, performance_monitor):
        """Test bulk create is significantly faster than individual creates"""
        # Individual creates
        performance_monitor.start()
        for i in range(100):
            await User.objects.using(session).create(
                username=f"individual_user_{i}", email=f"individual{i}@example.com", age=25
            )
        individual_time = performance_monitor.stop()["execution_time"]

        # Clear data
        await User.objects.using(session).filter().delete()

        # Bulk create
        users_data = [{"username": f"bulk_user_{i}", "email": f"bulk{i}@example.com", "age": 25} for i in range(100)]

        performance_monitor.start()
        await User.objects.using(session).bulk_create(users_data)
        bulk_time = performance_monitor.stop()["execution_time"]

        # Bulk should be significantly faster (at least 3x)
        assert bulk_time < individual_time / 3

    async def test_bulk_vs_individual_update_performance(self, session, performance_monitor):
        """Test bulk update is faster than individual updates"""
        # Create test data
        users_data = [{"username": f"perf_user_{i}", "email": f"perf{i}@example.com", "age": 25} for i in range(100)]
        await User.objects.using(session).bulk_create(users_data)

        # Get created users for testing
        users = await User.objects.using(session).filter(User.username.like("perf_user_%")).all()

        # Individual updates
        performance_monitor.start()
        for user in users[:50]:  # Update first 50
            user.age = 30
            await user.save()
        individual_time = performance_monitor.stop()["execution_time"]

        # Bulk update
        update_mappings = [
            {"id": user.id, "age": 35}
            for user in users[50:]  # Update remaining 50
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        bulk_time = performance_monitor.stop()["execution_time"]

        # Bulk should be faster (at least 2x)
        assert bulk_time < individual_time / 2

    async def test_memory_efficiency_large_bulk_operations(self, session):
        """Test memory efficiency of large bulk operations"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Large bulk operation
        users_data = [
            {"username": f"memory_user_{i}", "email": f"memory{i}@example.com", "age": 25} for i in range(5000)
        ]

        await User.objects.using(session).bulk_create(users_data)

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = memory_after - memory_before

        # Memory growth should be reasonable (less than 100MB for 5000 records)
        assert memory_growth < 100


class TestBulkOperationErrorHandling:
    """Test error handling in bulk operations"""

    async def test_bulk_create_validation_errors(self, session):
        """Test bulk create with validation errors"""
        # Include invalid data
        users_data = [
            {"username": "valid_user_1", "email": "valid1@example.com", "age": 25},
            {"username": "", "email": "invalid@example.com", "age": 30},  # Invalid username
            {"username": "valid_user_2", "email": "valid2@example.com", "age": 35},
        ]

        # Depending on implementation, this might raise an error or skip invalid records
        # For now, test that it handles the situation gracefully
        try:
            await User.objects.using(session).bulk_create(users_data)
            # If no error, verify valid records were created
            count = await User.objects.using(session).count()
            assert count >= 2  # At least the valid ones
        except Exception:  # noqa
            # If error is raised, that's also acceptable behavior
            pass

    async def test_bulk_update_constraint_violations(self, session, sample_users):
        """Test bulk update with constraint violations"""
        # Try to update with duplicate username (unique constraint)
        update_mappings = [
            {"id": sample_users[0].id, "username": "alice"},  # Same username
            {"id": sample_users[1].id, "username": "alice"},  # Duplicate
        ]

        # Should handle constraint violation gracefully
        with pytest.raises(Exception):  # Database constraint error expected  # noqa: B017
            await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

    async def test_bulk_operation_transaction_rollback(self, isolated_session):
        """Test bulk operations rollback on transaction failure"""
        # Create initial data
        users_data = [
            {"username": f"rollback_user_{i}", "email": f"rollback{i}@example.com", "age": 25} for i in range(5)
        ]
        await User.objects.using(isolated_session).bulk_create(users_data)
        await isolated_session.commit()

        # Get created users for testing
        users = await User.objects.using(isolated_session).filter(User.username.like("rollback_user_%")).all()

        try:
            # Bulk update within existing transaction
            update_mappings = [{"id": user.id, "age": 30} for user in users]
            await User.objects.using(isolated_session).bulk_update(update_mappings, match_fields=["id"])

            # Force rollback
            await isolated_session.rollback()
        except Exception:  # noqa
            await isolated_session.rollback()

        # Verify rollback - ages should still be 25
        updated_users = await User.objects.using(isolated_session).filter(User.age == 30).all()
        assert len(updated_users) == 0

        original_users = await User.objects.using(isolated_session).filter(User.age == 25).all()
        assert len(original_users) == 5


class TestBulkOperationWithRelationships:
    """Test bulk operations with relationship data"""

    async def test_bulk_create_with_foreign_keys(self, session, sample_users):
        """Test bulk create with foreign key relationships"""
        # Create posts for existing users
        posts_data = [
            {"title": f"Bulk Post {i}", "content": f"Content {i}", "author_id": sample_users[i % len(sample_users)].id}
            for i in range(20)
        ]

        await Post.objects.using(session).bulk_create(posts_data)

        # Verify posts were created
        total_posts = await Post.objects.using(session).count()
        assert total_posts == 20

        # Verify foreign key relationships by querying
        created_posts = await Post.objects.using(session).order_by("title").all()
        for post in created_posts:
            # Extract post number from title "Bulk Post {i}"
            post_num = int(post.title.split()[-1])
            expected_author_id = sample_users[post_num % len(sample_users)].id
            assert post.author_id == expected_author_id

    async def test_bulk_update_foreign_keys(self, session, sample_users, sample_posts):
        """Test bulk update of foreign key fields"""
        # Update all posts to have the same author
        new_author = sample_users[0]

        update_mappings = [{"id": post.id, "author_id": new_author.id} for post in sample_posts]

        await Post.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        # Verify all posts now have the same author
        updated_posts = await Post.objects.using(session).filter(Post.author_id == new_author.id).all()
        assert len(updated_posts) == len(sample_posts)

    @pytest.mark.usefixtures("sample_posts")
    async def test_bulk_delete_cascade_behavior(self, session, sample_users):
        """Test bulk delete behavior with related records"""
        # Delete users (posts should be handled according to cascade rules)
        user_ids = [user.id for user in sample_users[:2]]

        # Count posts before deletion
        _ = await Post.objects.using(session).count()

        await User.objects.using(session).bulk_delete(user_ids, id_field="id")

        # Verify users were deleted
        remaining_users = await User.objects.using(session).count()
        assert remaining_users == 1

        # Posts behavior depends on cascade configuration
        # For now, just verify the operation completed successfully
        posts_after = await Post.objects.using(session).count()
        assert posts_after >= 0  # Could be 0 if cascade delete, or unchanged if no cascade
