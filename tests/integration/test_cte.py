"""Tests for CTE (Common Table Expression) functionality."""

import pytest

from sqlobjects.expressions import func
from sqlobjects.session import ctx_session
from tests.conftest import User


class TestBasicCTE:
    """Test basic CTE functionality."""

    async def test_simple_cte(self, sample_users):
        """Test simple CTE creation and usage."""
        async with ctx_session() as session:
            # Create CTE for users over 30
            adults = User.objects.filter(User.age >= 30).cte("adults")

            # Use CTE in query
            result = await User.objects.using(session).with_cte(adults).filter(User.age >= 30).all()

            assert len(result) >= 2  # Bob (30) and Charlie (35)
            assert all(user.age >= 30 for user in result)

    async def test_cte_with_filtering(self, sample_users):
        """Test CTE with additional filtering."""
        async with ctx_session() as session:
            # Create CTE for active users
            active = User.objects.filter(User.is_active == True).cte("active")

            # Use CTE and add more filters
            result = (
                await User.objects.using(session).with_cte(active).filter(User.is_active == True, User.age >= 30).all()
            )

            assert len(result) >= 2  # Bob and Charlie
            assert all(user.is_active and user.age >= 30 for user in result)

    async def test_cte_with_ordering(self, sample_users):
        """Test CTE with ordering."""
        async with ctx_session() as session:
            # Create CTE
            users_cte = User.objects.filter(User.age >= 25).cte("users_cte")

            # Use CTE with ordering
            result = (
                await User.objects.using(session)
                .with_cte(users_cte)
                .filter(User.age >= 25)
                .order_by("-age")
                .limit(2)
                .all()
            )

            assert len(result) == 2
            # Should be ordered by age descending
            assert result[0].age >= result[1].age


class TestMultipleCTEs:
    """Test multiple CTEs in a single query."""

    async def test_two_ctes(self, sample_users):
        """Test using two CTEs together."""
        async with ctx_session() as session:
            # Create two CTEs
            adults = User.objects.filter(User.age >= 30).cte("adults")
            active = User.objects.filter(User.is_active == True).cte("active")

            # Use both CTEs
            result = (
                await User.objects.using(session)
                .with_cte(adults, active)
                .filter(User.age >= 30, User.is_active == True)
                .all()
            )

            assert len(result) >= 2  # Bob and Charlie
            assert all(user.age >= 30 and user.is_active for user in result)

    async def test_multiple_ctes_different_filters(self, sample_users):
        """Test multiple CTEs with different filters."""
        async with ctx_session() as session:
            # Create CTEs with different criteria
            young = User.objects.filter(User.age < 30).cte("young")
            active = User.objects.filter(User.is_active == True).cte("active")

            # Query using both CTEs
            result = (
                await User.objects.using(session)
                .with_cte(young, active)
                .filter(User.age < 30, User.is_active == True)
                .all()
            )

            # Should find Alice (25)
            assert len(result) >= 1
            assert all(user.age < 30 and user.is_active for user in result)


class TestCTEWithRelationships:
    """Test CTE with relationship queries."""

    async def test_cte_with_posts(self, sample_users, sample_posts):
        """Test CTE with post relationships."""
        async with ctx_session() as session:
            # Create CTE for users with posts
            users_with_posts = User.objects.filter(User.id.in_([post.author_id for post in sample_posts])).cte(
                "users_with_posts"
            )

            # Use CTE
            result = (
                await User.objects.using(session)
                .with_cte(users_with_posts)
                .filter(User.id.in_([post.author_id for post in sample_posts]))
                .all()
            )

            assert len(result) >= 1


class TestCTEProperties:
    """Test CTE object properties and methods."""

    def test_cte_name_property(self):
        """Test CTE name property."""
        cte = User.objects.filter(User.age >= 30).cte("test_cte")
        assert cte.name == "test_cte"

    def test_cte_is_recursive_property(self):
        """Test CTE is_recursive property."""
        regular_cte = User.objects.filter(User.age >= 30).cte("regular")
        recursive_cte = User.objects.filter(User.age >= 30).cte("recursive", recursive=True)

        assert not regular_cte.is_recursive
        assert recursive_cte.is_recursive

    def test_cte_repr(self):
        """Test CTE string representation."""
        regular_cte = User.objects.filter(User.age >= 30).cte("test")
        recursive_cte = User.objects.filter(User.age >= 30).cte("test_rec", recursive=True)

        assert "test" in repr(regular_cte)
        assert "test_rec" in repr(recursive_cte)
        assert "recursive=True" in repr(recursive_cte)
        assert "recursive=True" not in repr(regular_cte)


class TestCTEErrors:
    """Test CTE error handling."""

    def test_union_all_on_non_recursive_cte(self):
        """Test that union_all raises error on non-recursive CTE."""
        cte = User.objects.filter(User.age >= 30).cte("non_recursive")
        recursive_part = User.objects.filter(User.age < 30)

        with pytest.raises(ValueError, match="recursive"):
            cte.union_all(recursive_part)

    def test_cte_column_access_before_build(self):
        """Test that accessing CTE columns before building raises error."""
        cte = User.objects.filter(User.age >= 30).cte("test")

        with pytest.raises(RuntimeError, match="not been built"):
            _ = cte.c.username


class TestCTEIntegration:
    """Test CTE integration with other QuerySet features."""

    async def test_cte_with_aggregation(self, sample_users):
        """Test CTE with aggregation."""
        async with ctx_session() as session:
            # Create CTE
            users_cte = User.objects.filter(User.age >= 25).cte("users")

            # Use CTE with aggregation
            result = (
                await User.objects.using(session)
                .with_cte(users_cte)
                .filter(User.age >= 25)
                .aggregate(avg_age=func.avg(User.age), count=func.count())
            )

            assert "avg_age" in result
            assert "count" in result
            assert result["count"] >= 3  # Alice, Bob, Charlie

    async def test_cte_with_limit_offset(self, sample_users):
        """Test CTE with limit and offset."""
        async with ctx_session() as session:
            # Create CTE
            users_cte = User.objects.filter(User.age >= 25).cte("users")

            # Use CTE with limit and offset
            result = (
                await User.objects.using(session)
                .with_cte(users_cte)
                .filter(User.age >= 25)
                .order_by("age")
                .limit(2)
                .offset(1)
                .all()
            )

            assert len(result) <= 2
