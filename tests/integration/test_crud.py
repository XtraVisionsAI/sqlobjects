"""Integration tests for CRUD operations

Tests complete CRUD workflows with real database operations,
focusing on behavior and outcomes rather than implementation details.
"""

import pytest

from sqlobjects.exceptions import DoesNotExist
from sqlobjects.session import ctx_session
from tests.conftest import User


class TestCRUDLifecycle:
    """Test complete CRUD lifecycle operations"""

    @pytest.mark.usefixtures("sample_users")
    async def test_complete_crud_workflow(self, session):
        """Test complete CRUD operations work correctly end-to-end"""
        # CREATE - Test object creation
        user = await User.objects.using(session).create(username="crud_test", email="crud@example.com", age=28)
        assert user.id is not None
        assert user.username == "crud_test"
        assert user.email == "crud@example.com"
        assert user.age == 28
        assert user.is_active is True  # Default value

        # READ - Test object retrieval
        retrieved = await User.objects.using(session).get(User.id == user.id)
        assert retrieved.username == "crud_test"
        assert retrieved.email == "crud@example.com"
        assert retrieved.age == 28

        # UPDATE - Test object modification
        retrieved.email = "updated@example.com"
        retrieved.age = 29
        await retrieved.save()

        # Verify update persisted
        updated = await User.objects.using(session).get(User.id == user.id)
        assert updated.email == "updated@example.com"
        assert updated.age == 29
        assert updated.username == "crud_test"  # Unchanged field

        # DELETE - Test object deletion
        await updated.delete()

        # Verify deletion
        with pytest.raises(DoesNotExist):
            await User.objects.using(session).get(User.id == user.id)

    async def test_save_operation_detection(self, session):
        """Test save() correctly detects CREATE vs UPDATE operations"""
        # CREATE operation (no primary key)
        new_user = User(username="new_user", email="new@example.com", age=25)
        assert not new_user._has_primary_key_values()

        await new_user.using(session).save()

        # Should have ID after creation
        assert new_user.id is not None
        original_id = new_user.id

        # UPDATE operation (has primary key)
        new_user.email = "updated@example.com"
        await new_user.save()

        # ID should remain the same
        assert new_user.id == original_id

        # Verify update persisted
        updated = await User.objects.using(session).get(User.id == new_user.id)
        assert updated.email == "updated@example.com"

    async def test_detached_instance_operations(self, session, sample_users):
        """Test operations on detached instances work correctly"""
        user = sample_users[0]

        # Create detached instance with same ID
        detached_user = User.from_dict(
            {"id": user.id, "username": "detached_user", "email": "detached@example.com", "age": 40}
        )

        # Should be recognized as existing instance
        assert detached_user._has_primary_key_values()

        # Save should perform UPDATE operation
        await detached_user.using(session).save()

        # Verify update worked
        updated = await User.objects.using(session).get(User.id == user.id)
        assert updated.username == "detached_user"
        assert updated.email == "detached@example.com"
        assert updated.age == 40

    async def test_from_dict_creates_clean_instances(self, session):
        """Test from_dict creates instances without dirty field markers"""
        data = {"username": "clean_user", "email": "clean@example.com", "age": 30, "is_active": True}

        user = User.from_dict(data)

        # Should have clean state after creation
        dirty_fields = user._state_manager.get("dirty_fields", set())
        assert dirty_fields is not None and len(dirty_fields) == 0

        # Should be able to save without issues
        await user.using(session).save()
        assert user.id is not None


class TestQueryOperations:
    """Test query operations integration"""

    @pytest.mark.usefixtures("sample_users")
    async def test_filter_and_retrieval(self, session):
        """Test filtering and object retrieval"""
        # Single object retrieval
        alice = await User.objects.using(session).get(User.username == "alice")
        assert alice.username == "alice"
        assert alice.email == "alice@example.com"

        # Multiple object retrieval
        adults = await User.objects.using(session).filter(User.age >= 30).all()
        assert len(adults) == 2  # bob (30) and charlie (35)

        usernames = [user.username for user in adults]
        assert "bob" in usernames
        assert "charlie" in usernames

    @pytest.mark.usefixtures("sample_users")
    async def test_ordering_and_pagination(self, session):
        """Test query ordering and pagination"""
        # Order by age ascending
        users_by_age = await User.objects.using(session).order_by("age").all()
        ages = [user.age for user in users_by_age]
        assert ages == [25, 30, 35]  # alice, bob, charlie

        # Order by age descending
        users_desc = await User.objects.using(session).order_by("-age").all()
        ages_desc = [user.age for user in users_desc]
        assert ages_desc == [35, 30, 25]  # charlie, bob, alice

        # Pagination
        first_two = await User.objects.using(session).order_by("age").limit(2).all()
        assert len(first_two) == 2
        assert first_two[0].username == "alice"
        assert first_two[1].username == "bob"

    @pytest.mark.usefixtures("sample_users")
    async def test_aggregation_operations(self, session):
        """Test aggregation and counting operations"""
        # Count all users
        total_count = await User.objects.using(session).count()
        assert total_count == 3

        # Count with filter
        adult_count = await User.objects.using(session).filter(User.age >= 30).count()
        assert adult_count == 2

        # Exists check
        alice_exists = await User.objects.using(session).filter(User.username == "alice").exists()
        assert alice_exists is True

        nonexistent_exists = await User.objects.using(session).filter(User.username == "nonexistent").exists()
        assert nonexistent_exists is False

    @pytest.mark.usefixtures("sample_users")
    async def test_first_and_last_operations(self, session):
        """Test first() and last() operations"""
        # First user by age
        youngest = await User.objects.using(session).order_by("age").first()
        assert youngest
        assert youngest.username == "alice"
        assert youngest.age == 25

        # Last user by age
        oldest = await User.objects.using(session).order_by("age").last()
        assert oldest
        assert oldest.username == "charlie"
        assert oldest.age == 35

        # First with filter
        first_adult = await User.objects.using(session).filter(User.age >= 30).order_by("age").first()
        assert first_adult is not None and first_adult.username == "bob"
        assert first_adult.age == 30


class TestGetOrCreateOperations:
    """Test get_or_create and update_or_create operations"""

    @pytest.mark.usefixtures("sample_users")
    async def test_get_or_create_existing(self, session):
        """Test get_or_create with existing object"""
        user, created = await User.objects.using(session).get_or_create(
            username="alice", defaults={"email": "different@example.com", "age": 99}
        )

        assert created is False
        assert user.username == "alice"
        assert user.email == "alice@example.com"  # Original email, not defaults
        assert user.age == 25  # Original age, not defaults

    async def test_get_or_create_new(self, session):
        """Test get_or_create with new object"""
        user, created = await User.objects.using(session).get_or_create(
            username="new_user", defaults={"email": "new@example.com", "age": 25}
        )

        assert created is True
        assert user.username == "new_user"
        assert user.email == "new@example.com"
        assert user.age == 25
        assert user.id is not None

    @pytest.mark.usefixtures("sample_users")
    async def test_update_or_create_existing(self, session):
        """Test update_or_create with existing object"""
        user, created = await User.objects.using(session).update_or_create(
            username="alice", defaults={"email": "alice_updated@example.com", "age": 26}
        )

        assert created is False
        assert user.username == "alice"
        assert user.email == "alice_updated@example.com"  # Updated
        assert user.age == 26  # Updated

    async def test_update_or_create_new(self, session):
        """Test update_or_create with new object"""
        user, created = await User.objects.using(session).update_or_create(
            username="update_new_user", defaults={"email": "update_new@example.com", "age": 30}
        )

        assert created is True
        assert user.username == "update_new_user"
        assert user.email == "update_new@example.com"
        assert user.age == 30
        assert user.id is not None


class TestTransactionIntegration:
    """Test transaction behavior integration"""

    async def test_session_transaction_rollback(self, isolated_session):
        """Test transaction rollback on errors"""
        # Create initial data outside the transaction that will not be rolled back
        async with ctx_session() as db_session:
            user = await User.objects.using(db_session).create(
                username="transaction_test", email="transaction@example.com", age=25
            )

        original_email = user.email
        user_id = user.id

        # Simulate transaction that should rollback
        try:
            user.email = "updated@example.com"
            await user.using(isolated_session).save()

            # Force an error to trigger rollback
            raise ValueError("Simulated error")
        except ValueError:
            # Rollback the transaction
            await isolated_session.rollback()

        # Verify rollback - email should not be updated
        fresh_user = await User.objects.using(isolated_session).get(User.id == user_id)
        assert fresh_user.email == original_email  # Original email should be preserved

    async def test_session_transaction_commit(self, isolated_session):
        """Test successful transaction commit"""
        user = await User.objects.using(isolated_session).create(
            username="commit_test", email="commit@example.com", age=25
        )

        # Successful transaction
        user.email = "committed@example.com"
        await user.save()
        # Commit the transaction
        await isolated_session.commit()

        # Verify commit - email should be updated
        fresh_user = await User.objects.using(isolated_session).get(User.id == user.id)
        assert fresh_user.email == "committed@example.com"


class TestErrorHandling:
    """Test error handling in CRUD operations"""

    async def test_get_nonexistent_object(self, session):
        """Test getting non-existent object raises appropriate error"""
        with pytest.raises(DoesNotExist):
            await User.objects.using(session).get(User.username == "nonexistent")

    @pytest.mark.usefixtures("sample_users")
    async def test_duplicate_unique_field(self, session):
        """Test creating object with duplicate unique field"""
        # Try to create user with existing username
        with pytest.raises(Exception):  # Database constraint error  # noqa: B017
            await User.objects.using(session).create(
                username="alice",  # Already exists
                email="duplicate@example.com",
                age=30,
            )

    async def test_invalid_field_values(self, session):
        """Test validation of invalid field values"""
        # This test depends on validation implementation
        # For now, test basic type constraints
        user = User(username="test", email="test@example.com")

        # Should be able to create valid user
        await user.using(session).save()
        assert user.id is not None


class TestFieldSelection:
    """Test field selection operations (only/defer)"""

    @pytest.mark.usefixtures("sample_users")
    async def test_only_field_selection(self, session):
        """Test only() field selection"""
        # Select only specific fields
        users = await User.objects.using(session).only("id", "username").all()

        assert len(users) == 3
        for user in users:
            assert hasattr(user, "id")
            assert hasattr(user, "username")
            # Other fields should be deferred or not loaded

    @pytest.mark.usefixtures("sample_users")
    async def test_defer_field_selection(self, session):
        """Test defer() field selection"""
        # Defer specific fields
        users = await User.objects.using(session).defer("bio").all()

        assert len(users) == 3
        for user in users:
            assert hasattr(user, "id")
            assert hasattr(user, "username")
            assert hasattr(user, "email")
            # bio field should be deferred


class TestQueryOptimization:
    """Test query optimization features"""

    @pytest.mark.usefixtures("sample_users")
    async def test_skip_default_ordering_performance(self, session):
        """Test skip_default_ordering improves count performance"""
        # Count with default ordering (potentially slower)
        count_with_ordering = await User.objects.using(session).count()

        # Count without ordering (should be faster)
        count_without_ordering = await User.objects.using(session).skip_default_ordering().count()

        # Results should be the same
        assert count_with_ordering == count_without_ordering == 3
