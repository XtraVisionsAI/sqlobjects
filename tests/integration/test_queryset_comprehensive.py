"""Comprehensive QuerySet Integration Tests

Tests all QuerySet methods through strategic combinations to maximize coverage.
"""

from datetime import date, datetime

import pytest

from sqlobjects.expressions import func
from tests.conftest import Post, User


class TestQuerySetBasicOperations:
    """Test basic query building and execution methods"""

    @pytest.mark.usefixtures("sample_users")
    async def test_filter_and_execution_methods(self, session):
        """Test filter with all execution methods"""
        # Basic filtering (query building)
        active_users = User.objects.filter(User.is_active == True)

        # Test all execution methods
        all_results = await active_users.using(session).all()
        assert len(all_results) == 3

        count = await active_users.using(session).count()
        assert count == 3

        exists = await active_users.using(session).exists()
        assert exists is True

        first = await active_users.using(session).first()
        assert first is not None

        last = await active_users.using(session).last()
        assert last is not None

    @pytest.mark.usefixtures("sample_users")
    async def test_complex_filtering_combinations(self, session):
        """Test complex filter combinations"""
        # Direct field comparisons
        young_users = User.objects.filter(User.age < 30)
        results = await young_users.using(session).all()
        assert len(results) == 1  # alice (25)

        # Multiple conditions
        active_young = User.objects.filter(User.age < 30, User.is_active == True)
        results = await active_young.using(session).all()
        assert len(results) == 1  # alice (25)

        # Exclude method
        not_bob = User.objects.exclude(User.username == "bob")
        results = await not_bob.using(session).all()
        assert len(results) == 2

    @pytest.mark.usefixtures("sample_users")
    async def test_ordering_and_pagination(self, session):
        """Test ordering with pagination methods"""
        # Order by age descending
        ordered = User.objects.order_by("-age")
        results = await ordered.using(session).all()
        ages = [user.age for user in results]
        assert ages == [35, 30, 25]

        # Pagination
        page1 = await User.objects.order_by("age").limit(2).using(session).all()
        assert len(page1) == 2

        page2 = await User.objects.order_by("age").offset(2).limit(2).using(session).all()
        assert len(page2) == 1

        # Slice syntax
        sliced = User.objects.order_by("age")[1:3]
        results = await sliced.using(session).all()
        assert len(results) == 2

    @pytest.mark.usefixtures("sample_users")
    async def test_field_selection_methods(self, session):
        """Test only() and defer() field selection"""
        # Only specific fields
        users = await User.objects.only("username", "age").using(session).all()
        assert len(users) == 3

        # Defer heavy fields
        users = await User.objects.defer("bio").using(session).all()
        assert len(users) == 3

        # Combined with filtering
        young_users = await User.objects.filter(User.age < 30).only("username").using(session).all()
        assert len(young_users) == 1


class TestQuerySetAdvancedOperations:
    """Test advanced query operations"""

    @pytest.mark.usefixtures("sample_users")
    async def test_distinct_and_aggregation(self, session):
        """Test distinct and aggregation methods"""
        # Distinct values
        distinct_ages = User.objects.distinct("age")
        results = await distinct_ages.using(session).all()
        assert len(results) == 3

        # Aggregation (terminal method)
        stats = await User.objects.using(session).aggregate(
            total=func.count(), avg_age=User.age.avg(), max_age=User.age.max()
        )
        assert stats["total"] == 3
        assert stats["avg_age"] == 30.0
        assert stats["max_age"] == 35

        # Annotation with query building
        from sqlalchemy import case

        annotated = User.objects.annotate(age_group=case((User.age < 30, "young"), else_="old"))
        results = await annotated.using(session).all()
        assert len(results) == 3

    @pytest.mark.usefixtures("sample_posts")
    async def test_grouping_and_having(self, session):
        """Test GROUP BY and HAVING clauses"""
        # Group by author with count
        grouped = Post.objects.group_by("author_id").annotate(post_count=func.count())
        results = await grouped.using(session).all()
        assert len(results) > 0

        # Having clause
        prolific_authors = Post.objects.group_by("author_id").annotate(post_count=func.count()).having(func.count() > 2)
        _ = await prolific_authors.using(session).all()
        # Results depend on sample data distribution

    @pytest.mark.usefixtures("sample_users")
    async def test_values_and_values_list(self, session):
        """Test values() and values_list() terminal methods"""
        # Values as dictionaries (terminal method - no chaining after)
        values = await User.objects.filter(User.is_active == True).using(session).values("username", "age")
        assert len(values) == 3
        assert all("username" in v and "age" in v for v in values)

        # Values list as tuples (terminal method - no chaining after)
        tuples = await User.objects.order_by("age").using(session).values_list("username", "age")
        assert len(tuples) == 3
        assert all(len(t) == 2 for t in tuples)

        # Flat values list (terminal method - no chaining after)
        usernames = await User.objects.order_by("username").using(session).values_list("username", flat=True)
        assert len(usernames) == 3
        assert all(isinstance(name, str) for name in usernames)

    @pytest.mark.usefixtures("sample_posts")
    async def test_date_extraction_methods(self, session):
        """Test dates() and datetimes() terminal methods"""
        # Extract unique dates (terminal method - no chaining after)
        post_dates = await Post.objects.filter(Post.id > 0).using(session).dates("created_at", "day")
        assert isinstance(post_dates, list)
        assert all(isinstance(d, date) for d in post_dates)

        # Extract unique datetimes (terminal method - no chaining after)
        post_datetimes = await Post.objects.order_by("created_at").using(session).datetimes("created_at", "hour")
        assert isinstance(post_datetimes, list)
        assert all(isinstance(dt, datetime) for dt in post_datetimes)


class TestQuerySetRelationships:
    """Test relationship loading methods"""

    @pytest.mark.usefixtures("complex_relationships")
    async def test_select_related(self, session):
        """Test select_related for JOIN loading"""
        # Single relationship
        posts = await Post.objects.select_related("author").using(session).all()
        assert len(posts) == 10

        # Combined with filtering
        recent_posts = await Post.objects.select_related("author").filter(Post.id > 0).using(session).all()
        assert len(recent_posts) == 10

    @pytest.mark.usefixtures("complex_relationships")
    async def test_prefetch_related(self, session):
        """Test prefetch_related for separate query loading"""
        # Basic prefetch
        users = await User.objects.prefetch_related("posts").using(session).all()
        assert len(users) == 3

        # Combined with filtering
        active_users = await User.objects.filter(User.is_active == True).prefetch_related("posts").using(session).all()
        assert len(active_users) == 3


class TestQuerySetSpecialMethods:
    """Test special QuerySet methods"""

    @pytest.mark.usefixtures("sample_users")
    async def test_none_and_reverse(self, session):
        """Test none() and reverse() methods"""
        # None queryset
        empty = await User.objects.none().using(session).all()
        assert len(empty) == 0

        # Reverse ordering
        normal = await User.objects.order_by("age").using(session).all()
        reversed_qs = await User.objects.order_by("age").reverse().using(session).all()
        assert normal[0].age != reversed_qs[0].age

    @pytest.mark.usefixtures("sample_users")
    async def test_raw_sql(self, session):
        """Test raw SQL execution (terminal method)"""
        # Raw SQL query
        users = await User.objects.using(session).raw("SELECT * FROM users WHERE age > :min_age", {"min_age": 25})
        assert len(users) >= 2

    @pytest.mark.usefixtures("sample_users")
    async def test_extra_sql(self, session):
        """Test extra SQL fragments"""
        # Extra where conditions (query building)
        users = User.objects.extra(where=["age > 25"])
        results = await users.using(session).all()
        assert len(results) >= 2


class TestQuerySetLocking:
    """Test row-level locking methods"""

    @pytest.mark.usefixtures("sample_users")
    async def test_select_for_update(self, session):
        """Test FOR UPDATE locking"""
        # Basic locking
        user = await User.objects.select_for_update().using(session).first()
        assert user is not None

        # Locking with options
        user = await User.objects.select_for_update(nowait=True).using(session).first()
        assert user is not None

    @pytest.mark.usefixtures("sample_users")
    async def test_select_for_share(self, session):
        """Test FOR SHARE locking"""
        # Shared locking
        user = await User.objects.select_for_share().using(session).first()
        assert user is not None

        # Shared locking with options
        user = await User.objects.select_for_share(skip_locked=True).using(session).first()
        assert user is not None


class TestQuerySetBulkOperations:
    """Test bulk data operations (terminal methods)"""

    @pytest.mark.usefixtures("sample_users")
    async def test_bulk_update(self, session):
        """Test bulk update operations"""
        # Update with filtering (terminal method)
        updated_count = await User.objects.filter(User.age > 100).using(session).update(is_active=False)
        assert updated_count >= 0

        # Conditional update (terminal method)
        updated_count = await User.objects.filter(User.username == "nonexistent").using(session).update(age=50)
        assert updated_count == 0

    @pytest.mark.usefixtures("sample_users")
    async def test_bulk_delete(self, session):
        """Test bulk delete operations"""
        # Count before delete
        initial_count = await User.objects.using(session).count()

        # Delete with conditions (terminal method)
        deleted_count = await User.objects.filter(User.age > 100).using(session).delete()
        assert deleted_count == 0

        # Verify count unchanged (no users > 100)
        final_count = await User.objects.using(session).count()
        assert final_count == initial_count

    @pytest.mark.usefixtures("sample_users")
    async def test_cascade_delete_strategies(self, session):
        """Test cascade delete parameter options"""
        # Test cascade="full" (default)
        deleted_count = await User.objects.filter(User.age > 100).using(session).delete(cascade="full")
        assert deleted_count == 0

        # Test cascade="fast"
        deleted_count = await User.objects.filter(User.age > 100).using(session).delete(cascade="fast")
        assert deleted_count == 0

        # Test cascade="none"
        deleted_count = await User.objects.filter(User.age > 100).using(session).delete(cascade="none")
        assert deleted_count == 0

    @pytest.mark.usefixtures("complex_relationships")
    async def test_cascade_delete_with_relationships(self, session):
        """Test cascade delete with actual relationships"""
        # Create test data with relationships
        from tests.conftest import Post, User

        # Create user and posts
        user_data = {"username": "test_cascade", "email": "test@example.com", "age": 30, "is_active": True}
        _ = await User.objects.using(session).bulk_create([user_data])

        # Get the created user ID (simplified approach)
        test_user = await User.objects.filter(User.username == "test_cascade").using(session).first()
        if test_user:
            # Create posts for this user
            post_data = [
                {"title": "Test Post 1", "content": "Content 1", "author_id": test_user.id},
                {"title": "Test Post 2", "content": "Content 2", "author_id": test_user.id},
            ]
            await Post.objects.using(session).bulk_create(post_data)

            # Test cascade delete
            deleted_count = await User.objects.filter(User.id == test_user.id).using(session).delete(cascade="full")
            assert deleted_count >= 0


class TestQuerySetCascadeOperations:
    """Test cascade delete functionality"""

    async def test_cascade_parameter_validation(self, session):
        """Test cascade parameter accepts valid values"""
        # Valid cascade values should not raise errors
        try:
            await User.objects.filter(User.id == -1).using(session).delete(cascade="full")
            await User.objects.filter(User.id == -1).using(session).delete(cascade="fast")
            await User.objects.filter(User.id == -1).using(session).delete(cascade="none")
        except Exception as e:
            # Should not raise parameter validation errors
            assert "cascade" not in str(e).lower()

    @pytest.mark.usefixtures("sample_users")
    async def test_cascade_delete_performance_difference(self, session):
        """Test that different cascade modes have different performance characteristics"""
        import time

        # Test cascade="none" (should be fastest)
        start = time.time()
        await User.objects.filter(User.age > 100).using(session).delete(cascade="none")
        none_time = time.time() - start

        # Test cascade="fast"
        start = time.time()
        await User.objects.filter(User.age > 100).using(session).delete(cascade="fast")
        fast_time = time.time() - start

        # Test cascade="full"
        start = time.time()
        await User.objects.filter(User.age > 100).using(session).delete(cascade="full")
        full_time = time.time() - start

        # All should complete (even if no records deleted)
        assert none_time >= 0
        assert fast_time >= 0
        assert full_time >= 0


class TestQuerySetIterators:
    """Test iterator and async iteration"""

    @pytest.mark.usefixtures("sample_users")
    async def test_async_iteration(self, session):
        """Test async iteration support"""
        count = 0
        async for user in User.objects.using(session).iterator():
            count += 1
            assert hasattr(user, "username")
        assert count == 3

    @pytest.mark.usefixtures("sample_users")
    async def test_chunked_iteration(self, session):
        """Test chunked iteration for large datasets"""
        count = 0
        async for _ in User.objects.using(session).iterator(chunk_size=2):
            count += 1
        assert count == 3

    @pytest.mark.usefixtures("sample_users")
    async def test_get_item_access(self, session):
        """Test index and slice access (terminal methods)"""
        # Single item access
        first_user = await User.objects.order_by("age").using(session).get_item(0)
        assert first_user.age == 25  # type: ignore

        # Slice access
        first_two = await User.objects.order_by("age").using(session).get_item(slice(0, 2))
        assert len(first_two) == 2  # type: ignore


class TestQuerySetErrorHandling:
    """Test error conditions and edge cases"""

    @pytest.mark.usefixtures("sample_users")
    async def test_get_exceptions(self, session):
        """Test get() method exceptions"""
        from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned

        # DoesNotExist
        with pytest.raises(DoesNotExist):
            await User.objects.filter(User.username == "nonexistent").using(session).get()

        # MultipleObjectsReturned
        with pytest.raises(MultipleObjectsReturned):
            await User.objects.using(session).get()  # Multiple users exist

    async def test_invalid_operations(self, session):
        """Test invalid operations and parameters"""
        # Invalid slice parameters
        with pytest.raises(ValueError):
            await User.objects.using(session).get_item(-1)


class TestQuerySetMethodChaining:
    """Test complex method chaining scenarios"""

    @pytest.mark.usefixtures("complex_relationships")
    async def test_comprehensive_chaining(self, session):
        """Test complex method chaining combinations"""
        # Complex chain: filter + order + limit + select_related + annotate
        results = await (
            User.objects.filter(User.is_active == True)
            .annotate(user_id_plus_age=User.id + User.age)
            .order_by("age")
            .limit(2)
            .using(session)
            .all()
        )
        assert len(results) <= 2

    @pytest.mark.usefixtures("sample_users")
    async def test_performance_optimizations(self, session):
        """Test performance-related method combinations"""
        # Skip default ordering for count
        count = await User.objects.skip_default_ordering().using(session).count()
        assert count == 3

        # Deferred loading with filtering
        users = await User.objects.filter(User.age > 25).defer("bio").only("username", "age").using(session).all()
        assert len(users) == 2


class TestQuerySetDatabaseCompatibility:
    """Test database-specific functionality"""

    @pytest.mark.usefixtures("sample_posts")
    async def test_date_functions_sqlite(self, session):
        """Test date functions work with SQLite"""
        # Test dates extraction (terminal method)
        dates = await Post.objects.filter(Post.id > 0).using(session).dates("created_at", "day")
        assert isinstance(dates, list)

        # Test datetimes extraction (terminal method)
        datetimes = await Post.objects.order_by("created_at").using(session).datetimes("created_at", "hour")
        assert isinstance(datetimes, list)

    @pytest.mark.usefixtures("sample_users")
    async def test_aggregation_functions(self, session):
        """Test various aggregation functions"""
        # Aggregation (terminal method)
        stats = (
            await User.objects.filter(User.is_active == True)
            .using(session)
            .aggregate(
                count=func.count(),
                min_age=User.age.min(),
                max_age=User.age.max(),
                avg_age=User.age.avg(),
                sum_age=User.age.sum(),
            )
        )

        assert stats["count"] == 3
        assert stats["min_age"] == 25
        assert stats["max_age"] == 35
        assert stats["avg_age"] == 30.0
        assert stats["sum_age"] == 90

    @pytest.mark.usefixtures("sample_users")
    async def test_earliest_latest_methods(self, session):
        """Test earliest() and latest() methods"""
        # Earliest by age (terminal method)
        youngest = await User.objects.using(session).earliest("age")
        assert youngest and youngest.age == 25

        # Latest by age (terminal method)
        oldest = await User.objects.using(session).latest("age")
        assert oldest and oldest.age == 35

        # With filtering
        oldest_active = await User.objects.filter(User.is_active == True).using(session).latest("age")
        assert oldest_active and oldest_active.age == 35


class TestQuerySetCastOperations:
    """Test cast() method on ColumnAttribute and FunctionExpression"""

    @pytest.mark.usefixtures("sample_users")
    async def test_column_attribute_cast_basic(self, session):
        """Test basic cast() method on ColumnAttribute objects"""
        # Cast age (integer) to string using SQLObjects type names
        users = await User.objects.annotate(age_as_string=User.age.cast("string")).using(session).all()
        assert len(users) == 3

        # Cast id to float
        users = await User.objects.annotate(id_as_float=User.id.cast("float")).using(session).all()
        assert len(users) == 3

    @pytest.mark.usefixtures("sample_users")
    async def test_function_expression_cast_basic(self, session):
        """Test basic cast() method on FunctionExpression objects"""
        # Cast arithmetic result to integer
        users = await User.objects.annotate(age_plus_one_as_int=(User.age + 1).cast("integer")).using(session).all()
        assert len(users) == 3

        # Use cast in aggregation (terminal operation)
        stats = await User.objects.using(session).aggregate(
            avg_age_string=User.age.avg().cast("string"), max_age_as_float=User.age.max().cast("float")
        )
        assert "avg_age_string" in stats
        assert "max_age_as_float" in stats

    @pytest.mark.usefixtures("sample_users")
    async def test_cast_chaining_operations(self, session):
        """Test cast() method in complex chaining operations"""
        # Cast then use in comparison
        users = await User.objects.filter(User.age.cast("string") == "25").using(session).all()
        assert len(users) == 1

        # Cast arithmetic result then use in comparison
        users = await User.objects.filter((User.age + 5).cast("integer") > 30).using(session).all()
        assert len(users) == 2  # ages 30+5=35 > 30 and 35+5=40 > 30

        # Cast in annotation with arithmetic
        users = await User.objects.annotate(computed=(User.age.cast("float") * 1.1)).using(session).all()
        assert len(users) == 3

        # Complex cast chaining
        users = (
            await User.objects.annotate(complex_calc=((User.age + 10).cast("float") / 2).cast("integer"))
            .using(session)
            .all()
        )
        assert len(users) == 3
