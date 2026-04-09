"""Unit tests for query building and execution"""

import pytest

from sqlobjects.expressions import func
from sqlobjects.fields import BooleanColumn, Column, IntegerColumn, StringColumn, identity
from sqlobjects.model import ObjectModel
from sqlobjects.queryset import Q, QuerySet


class QueryTestUser(ObjectModel):
    """Test model for query testing"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)


class TestQueryBuilding:
    """Test query building without database execution"""

    def test_basic_filter_building(self):
        """Test basic filter query building"""
        # Simple equality filter
        qs = QueryTestUser.objects.filter(QueryTestUser.username == "alice")
        assert isinstance(qs, QuerySet)

        # Multiple filters
        qs = QueryTestUser.objects.filter(QueryTestUser.age > 18, QueryTestUser.is_active == True)
        assert isinstance(qs, QuerySet)

    def test_q_object_building(self):
        """Test Q object query building"""
        # OR combination
        q = Q(QueryTestUser.username == "alice") | Q(QueryTestUser.username == "bob")
        qs = QueryTestUser.objects.filter(q)
        assert isinstance(qs, QuerySet)

        # AND combination
        q = Q(QueryTestUser.age >= 18) & Q(QueryTestUser.is_active == True)
        qs = QueryTestUser.objects.filter(q)
        assert isinstance(qs, QuerySet)

        # Negation
        q = ~Q(QueryTestUser.is_active == False)
        qs = QueryTestUser.objects.filter(q)
        assert isinstance(qs, QuerySet)

    def test_ordering_building(self):
        """Test ordering query building"""
        # Single field ascending
        qs = QueryTestUser.objects.order_by("username")
        assert isinstance(qs, QuerySet)

        # Single field descending
        qs = QueryTestUser.objects.order_by("-age")
        assert isinstance(qs, QuerySet)

        # Multiple fields
        qs = QueryTestUser.objects.order_by("age", "-username")
        assert isinstance(qs, QuerySet)

    def test_order_by_replaces_previous_ordering(self):
        """Test that chained order_by replaces previous ordering instead of appending."""
        qs1 = QueryTestUser.objects.order_by("username")
        assert qs1._builder.ordering == ["username"]

        # Second order_by should replace, not append
        qs2 = qs1.order_by("-age")
        assert qs2._builder.ordering == ["-age"]

        # Original should be unchanged (immutability)
        assert qs1._builder.ordering == ["username"]

    def test_order_by_replaces_same_field_different_direction(self):
        """Test order_by('sent_at').order_by('-sent_at') produces only one ordering."""
        qs = QueryTestUser.objects.order_by("age").order_by("-age")
        assert qs._builder.ordering == ["-age"]

    def test_order_by_replaces_default_ordering(self):
        """Test that explicit order_by replaces default ordering from ModelConfig."""

        class OrderedUser(ObjectModel):
            id: Column[int] = identity()
            username: Column[str] = StringColumn(length=50)
            age: Column[int] = IntegerColumn(nullable=True)

        # Simulate default ordering set by ModelConfig
        OrderedUser._default_ordering = ["username"]  # type: ignore

        qs = OrderedUser.objects.filter()  # default ordering applied
        assert qs._builder.ordering == ["username"]

        # Explicit order_by should replace default ordering
        qs2 = qs.order_by("-age")
        assert qs2._builder.ordering == ["-age"]

    def test_pagination_building(self):
        """Test pagination query building"""
        # Limit only
        qs = QueryTestUser.objects.limit(10)
        assert isinstance(qs, QuerySet)

        # Offset only
        qs = QueryTestUser.objects.offset(5)
        assert isinstance(qs, QuerySet)

        # Limit and offset
        qs = QueryTestUser.objects.limit(10).offset(20)
        assert isinstance(qs, QuerySet)

    def test_query_chaining(self):
        """Test query method chaining"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True).order_by("-age").limit(10).offset(5)

        assert isinstance(qs, QuerySet)

    def test_distinct_building(self):
        """Test distinct query building"""
        # Basic distinct
        qs = QueryTestUser.objects.distinct()
        assert isinstance(qs, QuerySet)

        # Distinct on specific fields
        qs = QueryTestUser.objects.distinct("username")
        assert isinstance(qs, QuerySet)


class TestQuerySetMethods:
    """Test QuerySet method availability and behavior"""

    def test_execution_methods_available(self):
        """Test execution methods are available"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        # Check methods exist
        assert hasattr(qs, "all")
        assert hasattr(qs, "first")
        assert hasattr(qs, "last")
        assert hasattr(qs, "get")
        assert hasattr(qs, "count")
        assert hasattr(qs, "exists")
        assert hasattr(qs, "iterator")

    def test_aggregation_methods_available(self):
        """Test aggregation methods are available"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        assert hasattr(qs, "aggregate")
        assert hasattr(qs, "annotate")
        assert hasattr(qs, "values")
        assert hasattr(qs, "values_list")

    def test_modification_methods_available(self):
        """Test modification methods are available"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        assert hasattr(qs, "update")
        assert hasattr(qs, "delete")
        # Note: bulk_create and bulk_update are ObjectsManager methods, not QuerySet methods

    def test_relationship_methods_available(self):
        """Test relationship loading methods are available"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        assert hasattr(qs, "select_related")
        assert hasattr(qs, "prefetch_related")
        assert hasattr(qs, "only")
        assert hasattr(qs, "defer")

    def test_performance_methods_available(self):
        """Test performance optimization methods are available"""
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        assert hasattr(qs, "skip_default_ordering")
        assert hasattr(qs, "select_for_update")


class TestObjectsManager:
    """Test ObjectsManager functionality"""

    def test_objects_manager_exists(self):
        """Test objects manager is available"""
        assert hasattr(QueryTestUser, "objects")
        assert QueryTestUser.objects is not None

    def test_objects_manager_methods(self):
        """Test ObjectsManager provides QuerySet methods"""
        objects = QueryTestUser.objects

        # Query building methods
        assert hasattr(objects, "filter")
        assert hasattr(objects, "order_by")
        assert hasattr(objects, "limit")
        assert hasattr(objects, "offset")

        # Execution methods
        assert hasattr(objects, "all")
        assert hasattr(objects, "get")
        assert hasattr(objects, "first")
        assert hasattr(objects, "count")
        assert hasattr(objects, "exists")

        # Creation methods
        assert hasattr(objects, "create")
        assert hasattr(objects, "get_or_create")
        assert hasattr(objects, "update_or_create")
        assert hasattr(objects, "bulk_create")

    def test_objects_manager_returns_queryset(self):
        """Test ObjectsManager methods return QuerySet"""
        # Filter should return QuerySet
        qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)
        assert isinstance(qs, QuerySet)

        # Order by should return QuerySet
        qs = QueryTestUser.objects.order_by("username")
        assert isinstance(qs, QuerySet)

        # Filter should return QuerySet (all() is a terminal method)
        qs = QueryTestUser.objects.filter()
        assert isinstance(qs, QuerySet)


class TestQueryExpressions:
    """Test query expression building"""

    def test_field_expressions(self):
        """Test field-based expressions"""
        # Equality
        expr = QueryTestUser.username == "alice"
        assert expr is not None

        # Inequality
        expr = QueryTestUser.age > 18
        assert expr is not None

        # String operations
        expr = QueryTestUser.username.like("%alice%")
        assert expr is not None

        expr = QueryTestUser.email.ilike("%GMAIL%")
        assert expr is not None

    def test_func_expressions(self):
        """Test func object expressions"""
        # Count function
        count_expr = func.count()
        assert count_expr is not None

        # String functions
        concat_expr = func.concat(QueryTestUser.username.__column__, "@example.com")
        assert concat_expr is not None

        # Date functions
        year_expr = func.extract("year", QueryTestUser.id.__column__)  # Using id as placeholder
        assert year_expr is not None

    def test_complex_expressions(self):
        """Test complex expression combinations"""
        # Multiple conditions
        expr = (QueryTestUser.age >= 18) & (QueryTestUser.is_active == True)
        assert expr is not None

        # OR conditions
        expr = (QueryTestUser.username == "alice") | (QueryTestUser.username == "bob")
        assert expr is not None


class TestQueryOptimization:
    """Test query optimization features"""

    def test_skip_default_ordering(self):
        """Test skip_default_ordering method"""
        qs = QueryTestUser.objects.skip_default_ordering()
        assert isinstance(qs, QuerySet)

        # Should be chainable
        qs = QueryTestUser.objects.skip_default_ordering().filter(QueryTestUser.is_active == True)
        assert isinstance(qs, QuerySet)

    def test_select_for_update(self):
        """Test select_for_update method"""
        qs = QueryTestUser.objects.select_for_update()
        assert isinstance(qs, QuerySet)

        # With parameters
        qs = QueryTestUser.objects.select_for_update(nowait=True, skip_locked=True)
        assert isinstance(qs, QuerySet)


class TestQueryValidation:
    """Test query validation and error handling"""

    def test_invalid_field_reference(self):
        """Test invalid field reference handling"""
        with pytest.raises(AttributeError):
            QueryTestUser.objects.filter(QueryTestUser.non_existent_field == "value")  # type: ignore

    def test_invalid_q_object_combination(self):
        """Test invalid Q object combinations"""
        # Q objects should be on the left side
        q = Q(QueryTestUser.username == "alice")

        # This should work
        combined = q | Q(QueryTestUser.username == "bob")
        assert combined is not None

        # Invalid combinations should raise appropriate errors
        with pytest.raises((TypeError, AttributeError)):  # noqa
            # String on left side of Q object operation
            invalid = "string" | q  # noqa # type: ignore

    def test_empty_filter(self):
        """Test empty filter handling"""
        # Empty filter should return all records
        qs = QueryTestUser.objects.filter()
        assert isinstance(qs, QuerySet)

    def test_none_values_in_filter(self):
        """Test None values in filter"""
        # None equality
        qs = QueryTestUser.objects.filter(QueryTestUser.age == None)  # noqa: E711
        assert isinstance(qs, QuerySet)

        # IS NULL / IS NOT NULL
        qs = QueryTestUser.objects.filter(QueryTestUser.age.is_(None))
        assert isinstance(qs, QuerySet)

        qs = QueryTestUser.objects.filter(QueryTestUser.age.isnot(None))
        assert isinstance(qs, QuerySet)


class TestQuerySetImmutability:
    """Test QuerySet immutability"""

    def test_queryset_immutability(self):
        """Test QuerySet methods return new instances"""
        original_qs = QueryTestUser.objects

        # Filter should return new QuerySet
        filtered_qs = original_qs.filter(QueryTestUser.is_active == True)
        assert filtered_qs is not original_qs

        # Order by should return new QuerySet
        ordered_qs = original_qs.order_by("username")
        assert ordered_qs is not original_qs

        # Limit should return new QuerySet
        limited_qs = original_qs.limit(10)
        assert limited_qs is not original_qs

    def test_chaining_creates_new_instances(self):
        """Test method chaining creates new instances"""
        qs1 = QueryTestUser.objects.filter()
        qs2 = qs1.filter(QueryTestUser.is_active == True)
        qs3 = qs2.order_by("username")
        qs4 = qs3.limit(10)

        # All should be different instances
        assert qs1 is not qs2
        assert qs2 is not qs3
        assert qs3 is not qs4

        # But all should be QuerySet instances
        assert isinstance(qs1, QuerySet)
        assert isinstance(qs2, QuerySet)
        assert isinstance(qs3, QuerySet)
        assert isinstance(qs4, QuerySet)


class TestQuerySetCopy:
    """Test QuerySet copying and cloning"""

    def test_queryset_copy(self):
        """Test QuerySet can be copied"""
        original_qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        # Should be able to copy
        copied_qs = original_qs._create_new_queryset()
        assert copied_qs is not original_qs
        assert isinstance(copied_qs, QuerySet)

    def test_independent_modifications(self):
        """Test copied QuerySets can be modified independently"""
        base_qs = QueryTestUser.objects.filter(QueryTestUser.is_active == True)

        qs1 = base_qs.order_by("username")
        qs2 = base_qs.order_by("-age")

        # Should be different instances
        assert qs1 is not qs2
        assert qs1 is not base_qs
        assert qs2 is not base_qs
