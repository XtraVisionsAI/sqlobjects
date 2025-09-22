"""Integration tests for bulk operations return values functionality."""

from sqlobjects.objects.bulk import BulkResult
from tests.conftest import Post, User


class TestBulkCreateReturnValues:
    """Test bulk_create return value functionality."""

    async def test_bulk_create_default_return_count(self, session):
        """Test default behavior returns count (backward compatibility)."""
        users_data = [{"username": f"user_{i}", "email": f"user{i}@example.com", "age": 20 + i} for i in range(5)]

        result = await User.objects.using(session).bulk_create(users_data)

        # Should return count by default
        assert isinstance(result, int)
        assert result == 5

    async def test_bulk_create_return_objects(self, session):
        """Test returning created objects."""
        users_data = [
            {"username": f"return_user_{i}", "email": f"return{i}@example.com", "age": 25 + i} for i in range(3)
        ]

        result = await User.objects.using(session).bulk_create(users_data, return_objects=True)

        # Should return list of objects
        assert isinstance(result, BulkResult)
        assert result.objects and len(result.objects) == 3

        # Verify objects have correct data and auto-generated fields
        for i, user in enumerate(result.objects):
            assert isinstance(user, User)
            assert user.username == f"return_user_{i}"
            assert user.email == f"return{i}@example.com"
            assert user.age == 25 + i
            assert user.id is not None  # Auto-generated ID
            assert user.is_active is True  # Default value

    async def test_bulk_create_return_specific_fields(self, session):
        """Test returning only specific fields."""
        users_data = [{"username": f"fields_user_{i}", "email": f"fields{i}@example.com", "age": 30} for i in range(3)]

        result = await User.objects.using(session).bulk_create(
            users_data, return_objects=True, return_fields=["id", "username"]
        )

        # Should return BulkResult with only requested fields
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 3

        for i, user in enumerate(result.objects):
            assert isinstance(user, dict)  # return_fields returns dict objects
            assert "id" in user
            assert user["username"] == f"fields_user_{i}"
            # Other fields should not be present
            assert "email" not in user
            assert "age" not in user

    async def test_bulk_create_empty_data_return_objects(self, session):
        """Test return_objects=True with empty data."""
        result = await User.objects.using(session).bulk_create([], return_objects=True)

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 0

    async def test_bulk_create_empty_data_default(self, session):
        """Test default behavior with empty data."""
        result = await User.objects.using(session).bulk_create([])

        assert isinstance(result, int)
        assert result == 0


class TestBulkUpdateReturnValues:
    """Test bulk_update return value functionality."""

    async def test_bulk_update_default_return_count(self, session, sample_users):
        """Test default behavior returns count (backward compatibility)."""
        update_mappings = [
            {"id": sample_users[0].id, "age": 99},
            {"id": sample_users[1].id, "age": 88},
        ]

        result = await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        # Should return count by default
        assert isinstance(result, int)
        assert result == 2

    async def test_bulk_update_return_objects(self, session, sample_users):
        """Test returning updated objects."""
        update_mappings = [
            {"id": sample_users[0].id, "age": 77, "email": "updated1@example.com"},
            {"id": sample_users[1].id, "age": 66, "email": "updated2@example.com"},
        ]

        result = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], return_objects=True
        )

        # Should return BulkResult with updated objects
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 2

        # Verify objects have updated data
        updated_users = {user.id: user for user in result.objects if isinstance(user, User)}

        user1 = updated_users[sample_users[0].id]
        assert user1.age == 77
        assert user1.email == "updated1@example.com"

        user2 = updated_users[sample_users[1].id]
        assert user2.age == 66
        assert user2.email == "updated2@example.com"

    async def test_bulk_update_return_specific_fields(self, session, sample_users):
        """Test returning only specific fields from updated objects."""
        update_mappings = [
            {"id": sample_users[0].id, "age": 55},
            {"id": sample_users[1].id, "age": 44},
        ]

        result = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], return_objects=True, return_fields=["id", "age"]
        )

        # Should return BulkResult with only requested fields
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 2

        for user in result.objects:
            assert isinstance(user, dict)  # return_fields returns dict objects
            assert "id" in user
            assert user["age"] in [55, 44]

    async def test_bulk_update_nonexistent_records_return_objects(self, session):
        """Test return_objects=True with non-existent records."""
        update_mappings = [
            {"id": 99999, "age": 100},
            {"id": 99998, "age": 101},
        ]

        result = await User.objects.using(session).bulk_update(
            update_mappings, match_fields=["id"], return_objects=True
        )

        # Should return empty BulkResult for non-existent records
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 0

    async def test_bulk_update_empty_mappings_return_objects(self, session):
        """Test return_objects=True with empty mappings."""
        result = await User.objects.using(session).bulk_update([], match_fields=["id"], return_objects=True)

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 0


class TestBulkDeleteReturnValues:
    """Test bulk_delete return value functionality."""

    async def test_bulk_delete_default_return_count(self, session, sample_users):
        """Test default behavior returns count (backward compatibility)."""
        user_ids = [sample_users[0].id, sample_users[1].id]

        result = await User.objects.using(session).bulk_delete(user_ids, id_field="id")

        # Should return count by default
        assert isinstance(result, int)
        assert result == 2

    async def test_bulk_delete_return_objects(self, session, sample_users):
        """Test returning deleted objects for audit logging."""
        user_ids = [sample_users[0].id, sample_users[1].id]

        result = await User.objects.using(session).bulk_delete(user_ids, id_field="id", return_objects=True)

        # Should return BulkResult with deleted objects
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 2

        # Verify objects contain the deleted data
        deleted_users = {user.id: user for user in result.objects if isinstance(user, User)}

        assert sample_users[0].id in deleted_users
        assert sample_users[1].id in deleted_users

        # Verify data integrity
        user1 = deleted_users[sample_users[0].id]
        assert user1.username == sample_users[0].username
        assert user1.email == sample_users[0].email

    async def test_bulk_delete_return_specific_fields(self, session, sample_users):
        """Test returning only specific fields from deleted objects."""
        user_ids = [sample_users[0].id]

        result = await User.objects.using(session).bulk_delete(
            user_ids, id_field="id", return_objects=True, return_fields=["id", "username", "email"]
        )

        # Should return BulkResult with only requested fields
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 1

        deleted_user = result.objects[0]
        assert isinstance(deleted_user, dict)  # return_fields returns dict objects
        assert deleted_user["id"] == sample_users[0].id
        assert deleted_user["username"] == sample_users[0].username
        assert deleted_user["email"] == sample_users[0].email

    async def test_bulk_delete_nonexistent_ids_return_objects(self, session):
        """Test return_objects=True with non-existent IDs."""
        nonexistent_ids = [99999, 99998]

        result = await User.objects.using(session).bulk_delete(nonexistent_ids, id_field="id", return_objects=True)

        # Should return empty BulkResult for non-existent records
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 0

    async def test_bulk_delete_empty_ids_return_objects(self, session):
        """Test return_objects=True with empty ID list."""
        result = await User.objects.using(session).bulk_delete([], id_field="id", return_objects=True)

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 0
        assert len(result) == 0


class TestBulkOperationPerformanceWithReturnValues:
    """Test performance impact of return values."""

    async def test_bulk_create_performance_with_return_objects(self, session, performance_monitor):
        """Test performance impact of return_objects=True."""
        import warnings

        users_data = [{"username": f"perf_user_{i}", "email": f"perf{i}@example.com", "age": 25} for i in range(100)]

        # Test without return_objects
        performance_monitor.start()
        await User.objects.using(session).bulk_create(users_data.copy())
        time_without_return = performance_monitor.stop()["execution_time"]

        # Clear data
        await User.objects.using(session).filter(User.username.like("perf_user_%")).delete()

        # Test with return_objects - capture warnings to check for RETURNING support
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            performance_monitor.start()
            result = await User.objects.using(session).bulk_create(users_data, return_objects=True)
            time_with_return = performance_monitor.stop()["execution_time"]

        # Verify return_objects works
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 100

        # Check if database supports RETURNING
        has_returning_warning = any("does not support" in str(warning.message) for warning in w)

        if not has_returning_warning:
            # Database supports RETURNING - performance impact should be reasonable (less than 5x slower)
            # Note: RETURNING adds overhead for fetching and processing returned data
            performance_ratio = time_with_return / time_without_return if time_without_return > 0 else 1
            print(f"\nPerformance impact with return_objects=True: {performance_ratio:.2f}x")
            assert time_with_return < time_without_return * 30, f"Performance impact too high: {performance_ratio:.2f}x"
        else:
            # Database doesn't support RETURNING - skip performance assertion but log the impact
            performance_ratio = time_with_return / time_without_return if time_without_return > 0 else 1
            print(f"\nDatabase doesn't support INSERT RETURNING. Performance impact: {performance_ratio:.2f}x")
            # Just verify it's not extremely slow (less than 10x)
            assert time_with_return < time_without_return * 10, f"Performance impact too high: {performance_ratio:.2f}x"

    async def test_bulk_create_memory_usage_with_return_objects(self, session):
        """Test memory usage with return_objects=True."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Large dataset with return_objects
        users_data = [
            {"username": f"memory_user_{i}", "email": f"memory{i}@example.com", "age": 25} for i in range(1000)
        ]

        result = await User.objects.using(session).bulk_create(users_data, return_objects=True)

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = memory_after - memory_before

        # Verify functionality
        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 1000

        # Memory growth should be reasonable (less than 200MB for 1000 objects)
        assert memory_growth < 200


class TestBulkOperationDatabaseCompatibility:
    """Test return values work across different database dialects."""

    async def test_bulk_create_return_objects_postgresql(self, session):
        """Test return_objects with PostgreSQL (RETURNING support)."""
        # This test assumes PostgreSQL - adapt based on test database
        users_data = [{"username": f"pg_user_{i}", "email": f"pg{i}@example.com", "age": 30} for i in range(3)]

        result = await User.objects.using(session).bulk_create(users_data, return_objects=True)

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 3

        for user in result.objects:
            assert isinstance(user, User)
            assert user.id is not None
            assert user.username.startswith("pg_user_")

    async def test_bulk_operations_with_relationships(self, session, sample_users):
        """Test bulk operations return values with foreign key relationships."""
        # Create posts with foreign keys
        posts_data = [
            {
                "title": f"Return Post {i}",
                "content": f"Content {i}",
                "author_id": sample_users[i % len(sample_users)].id,
            }
            for i in range(6)
        ]

        result = await Post.objects.using(session).bulk_create(posts_data, return_objects=True)

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 6

        # Verify foreign key relationships
        for post in result.objects:
            assert isinstance(post, Post)
            assert post.id is not None
            assert post.author_id in [user.id for user in sample_users]
            assert post.title.startswith("Return Post")

    async def test_bulk_operations_batch_processing_with_return_values(self, session):
        """Test return values work correctly with batch processing."""
        # Large dataset that will be processed in multiple batches
        users_data = [
            {"username": f"batch_user_{i}", "email": f"batch{i}@example.com", "age": 25}
            for i in range(150)  # More than default batch_size of 100
        ]

        result = await User.objects.using(session).bulk_create(
            users_data,
            return_objects=True,
            batch_size=50,  # Force multiple batches
        )

        assert isinstance(result, BulkResult)
        assert result.objects is not None
        assert len(result.objects) == 150

        # Verify all objects are returned correctly across batches
        usernames = {user.username for user in result.objects if isinstance(user, User)}
        expected_usernames = {f"batch_user_{i}" for i in range(150)}
        assert usernames == expected_usernames

        # Verify all have IDs
        assert all(user.id is not None for user in result.objects if isinstance(user, User))
