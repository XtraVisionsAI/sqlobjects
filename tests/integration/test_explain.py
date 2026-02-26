"""Integration tests for EXPLAIN functionality."""

import pytest


@pytest.mark.asyncio
class TestExplain:
    """Test EXPLAIN query analysis functionality."""

    async def test_explain_all(self, session, sample_users):
        """Test EXPLAIN on all() expression."""
        from tests.conftest import User

        # Get EXPLAIN plan
        plan = await User.objects.using(session).all().explain()

        assert isinstance(plan, str)
        assert len(plan) > 0
        plan_upper = plan.upper()
        assert "SCAN" in plan_upper or "SEARCH" in plan_upper or "EXPLAIN" in plan_upper

    async def test_explain_filter(self, session, sample_users):
        """Test EXPLAIN on filtered query."""
        from tests.conftest import User

        plan = await User.objects.using(session).filter(User.age > 25).all().explain()

        assert isinstance(plan, str)
        assert len(plan) > 0

    async def test_explain_count(self, session):
        """Test EXPLAIN on count() expression."""
        from tests.conftest import User

        plan = await User.objects.using(session).count().explain()

        assert isinstance(plan, str)
        assert len(plan) > 0

    async def test_explain_first(self, session, sample_users):
        """Test EXPLAIN on first() expression."""
        from tests.conftest import User

        plan = await User.objects.using(session).first().explain()

        assert isinstance(plan, str)
        assert len(plan) > 0

    async def test_explain_with_analyze(self, session, sample_users):
        """Test EXPLAIN with analyze parameter."""
        from tests.conftest import User

        # Note: SQLite doesn't support ANALYZE in EXPLAIN
        # This test verifies the parameter is accepted
        plan = await User.objects.using(session).all().explain(analyze=True)

        assert isinstance(plan, str)
        assert len(plan) > 0

    async def test_explain_aggregate(self, session, sample_users):
        """Test EXPLAIN on aggregate expression."""
        from sqlobjects.expressions import func
        from tests.conftest import User

        # Use table column instead of ColumnAttribute
        plan = await User.objects.using(session).aggregate(avg_age=func.avg(User.__table__.c.age)).explain()

        assert isinstance(plan, str)
        assert len(plan) > 0
