"""Performance tests for query operations

Tests query performance and memory usage for various query patterns
and optimization techniques.
"""

import asyncio
import os
import time

import psutil
import pytest

from sqlobjects.expressions import func
from tests.conftest import Post, PostTag, Tag, User


class TestQueryPerformance:
    """Test basic query performance characteristics"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_simple_query_performance(self, session, performance_monitor):
        """Test performance of simple queries on large dataset"""
        # Simple filter query
        performance_monitor.start()
        young_users = await User.objects.using(session).filter(User.age < 30).all()
        filter_time = performance_monitor.stop()["execution_time"]

        # Should complete quickly even with large dataset
        assert filter_time < 2.0, f"Simple filter took {filter_time:.2f}s"
        assert len(young_users) > 0

        # Count query (should be faster)
        performance_monitor.start()
        count = await User.objects.using(session).filter(User.age < 30).count()
        count_time = performance_monitor.stop()["execution_time"]

        assert count_time < 1.0, f"Count query took {count_time:.2f}s"
        assert count == len(young_users)

    @pytest.mark.usefixtures("large_dataset")
    async def test_complex_query_performance(self, session, performance_monitor):
        """Test performance of complex queries"""
        # Complex query with multiple conditions
        performance_monitor.start()
        complex_users = (
            await User.objects.using(session)
            .filter(User.age >= 25, User.age <= 45, User.is_active == True, User.username.like("%user%"))
            .order_by("-age")
            .limit(100)
            .all()
        )
        complex_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time
        assert complex_time < 3.0, f"Complex query took {complex_time:.2f}s"
        assert len(complex_users) <= 100

        # Verify ordering
        if len(complex_users) > 1:
            for i in range(len(complex_users) - 1):
                assert complex_users[i].age >= complex_users[i + 1].age

    @pytest.mark.usefixtures("large_dataset")
    async def test_aggregation_query_performance(self, session, performance_monitor):
        """Test performance of aggregation queries"""
        # Aggregation query using field methods
        performance_monitor.start()
        stats = await User.objects.using(session).aggregate(
            total_users=func.count(), avg_age=User.age.avg(), min_age=User.age.min(), max_age=User.age.max()
        )
        agg_time = performance_monitor.stop()["execution_time"]

        # Should complete quickly
        assert agg_time < 2.0, f"Aggregation query took {agg_time:.2f}s"

        # Verify results
        assert stats["total_users"] == 10000  # From large_dataset fixture
        assert stats["avg_age"] is not None
        assert stats["min_age"] <= stats["max_age"]

    @pytest.mark.usefixtures("large_dataset")
    async def test_skip_default_ordering_performance(self, session, performance_monitor):
        """Test skip_default_ordering performance improvement"""
        # Count with default ordering
        performance_monitor.start()
        count_with_ordering = await User.objects.using(session).count()
        time_with_ordering = performance_monitor.stop()["execution_time"]

        # Count without ordering (should be faster)
        performance_monitor.start()
        count_without_ordering = await User.objects.using(session).skip_default_ordering().count()
        time_without_ordering = performance_monitor.stop()["execution_time"]

        # Results should be the same
        assert count_with_ordering == count_without_ordering == 10000

        # Without ordering should be faster (or at least not slower)
        assert time_without_ordering <= time_with_ordering * 1.1  # Allow 10% margin


class TestRelationshipQueryPerformance:
    """Test relationship query performance"""

    @pytest.mark.usefixtures("complex_relationships")
    async def test_select_related_performance(self, session, performance_monitor):
        """Test select_related performance improvement"""
        # Query without select_related
        performance_monitor.start()
        posts_without = await Post.objects.using(session).all()
        time_without = performance_monitor.stop()["execution_time"]

        # Query with select_related
        performance_monitor.start()
        posts_with = await Post.objects.using(session).select_related("author").all()
        time_with = performance_monitor.stop()["execution_time"]

        # Both should return same number of posts
        assert len(posts_without) == len(posts_with) == 10

        # Both should complete within reasonable time
        assert time_without < 2.0
        assert time_with < 2.0

    @pytest.mark.usefixtures("complex_relationships")
    async def test_prefetch_related_performance(self, session, performance_monitor):
        """Test prefetch_related performance"""
        # Query without prefetch_related
        performance_monitor.start()
        users_without = await User.objects.using(session).all()
        time_without = performance_monitor.stop()["execution_time"]

        # Query with prefetch_related
        performance_monitor.start()
        users_with = await User.objects.using(session).prefetch_related("posts").all()
        time_with = performance_monitor.stop()["execution_time"]

        # Both should return same number of users
        assert len(users_without) == len(users_with) == 3

        # Both should complete within reasonable time
        assert time_without < 2.0
        assert time_with < 2.0

    @pytest.mark.usefixtures("complex_relationships")
    async def test_complex_join_performance(self, session, performance_monitor):
        """Test complex join query performance"""
        # Complex join query
        performance_monitor.start()
        results = (
            await User.objects.using(session)
            .join(Post.__table__, User.id == Post.author_id)
            .join(PostTag.__table__, Post.id == PostTag.post_id)
            .join(Tag.__table__, PostTag.tag_id == Tag.id)
            .filter(Tag.name == "python")
            .distinct()
            .all()
        )

        join_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time
        assert join_time < 3.0, f"Complex join took {join_time:.2f}s"
        assert len(results) >= 0  # May be 0 depending on test data


class TestIteratorPerformance:
    """Test iterator performance and memory efficiency"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_memory_efficiency(self, session):
        """Test iterator doesn't load all data into memory"""
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Process large dataset with iterator
        count = 0
        async for user in User.objects.using(session).iterator(chunk_size=100):
            count += 1
            # Simulate processing
            _ = user.username.upper()

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = memory_after - memory_before

        # Should process all records
        assert count == 10000

        # Memory growth should be minimal (less than 50MB)
        assert memory_growth < 50, f"Iterator used {memory_growth:.2f}MB memory"

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_vs_all_performance(self, session, performance_monitor):
        """Test iterator vs all() for large datasets"""
        # Using all() - loads everything into memory
        performance_monitor.start()
        all_users = await User.objects.using(session).all()
        all_count = len(all_users)
        all_time = performance_monitor.stop()["execution_time"]

        # Using iterator - memory efficient
        performance_monitor.start()
        iterator_count = 0
        async for _user in User.objects.using(session).iterator(chunk_size=1000):
            iterator_count += 1
        iterator_time = performance_monitor.stop()["execution_time"]

        # Should process same number of records
        assert all_count == iterator_count == 10000

        # Iterator may be slower but should be reasonable
        assert iterator_time < all_time * 2  # Allow 2x slower for memory efficiency

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_chunk_size_optimization(self, session, performance_monitor):
        """Test optimal chunk size for iterator performance"""
        chunk_sizes = [100, 500, 1000, 2000]
        times = {}

        for chunk_size in chunk_sizes:
            performance_monitor.start()
            count = 0
            async for _user in User.objects.using(session).iterator(chunk_size=chunk_size):
                count += 1
            execution_time = performance_monitor.stop()["execution_time"]
            times[chunk_size] = execution_time

            # Should process all records
            assert count == 10000

        # All chunk sizes should complete within reasonable time
        for chunk_size, time_taken in times.items():
            assert time_taken < 10.0, f"Chunk size {chunk_size} took {time_taken:.2f}s"


class TestFieldSelectionPerformance:
    """Test field selection performance (only/defer)"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_only_field_performance(self, session, performance_monitor):
        """Test only() field selection performance"""
        # Query all fields
        performance_monitor.start()
        all_fields = await User.objects.using(session).all()
        all_fields_time = performance_monitor.stop()["execution_time"]

        # Query only specific fields
        performance_monitor.start()
        selected_fields = await User.objects.using(session).only("id", "username").all()
        selected_time = performance_monitor.stop()["execution_time"]

        # Should return same number of records
        assert len(all_fields) == len(selected_fields) == 10000

        # Selected fields should be faster (or at least not slower)
        assert selected_time <= all_fields_time * 1.2  # Allow 20% margin

    @pytest.mark.usefixtures("large_dataset")
    async def test_defer_field_performance(self, session, performance_monitor):
        """Test defer() field selection performance"""
        # Query all fields
        performance_monitor.start()
        all_fields = await User.objects.using(session).all()
        all_fields_time = performance_monitor.stop()["execution_time"]

        # Query with deferred fields
        performance_monitor.start()
        deferred_fields = await User.objects.using(session).defer("bio").all()
        deferred_time = performance_monitor.stop()["execution_time"]

        # Should return same number of records
        assert len(all_fields) == len(deferred_fields) == 10000

        # Deferred fields should be faster (or at least not slower)
        assert deferred_time <= all_fields_time * 1.2  # Allow 20% margin


class TestConcurrentQueryPerformance:
    """Test query performance under concurrent load"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_concurrent_read_queries(self, session, performance_monitor):
        """Test concurrent read query performance"""

        async def query_batch(batch_id: int):
            return (
                await User.objects.using(session)
                .filter(User.age >= 20 + (batch_id * 5), User.age <= 30 + (batch_id * 5))
                .all()
            )

        # Run concurrent queries
        performance_monitor.start()
        tasks = [query_batch(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        execution_time = performance_monitor.stop()["execution_time"]

        # All queries should complete
        assert len(results) == 5
        for result in results:
            assert len(result) >= 0  # May vary based on age distribution

        # Should complete within reasonable time
        assert execution_time < 5.0, f"Concurrent queries took {execution_time:.2f}s"

    @pytest.mark.usefixtures("large_dataset")
    async def test_concurrent_mixed_operations(self, session, performance_monitor):
        """Test mixed read/write operations performance"""

        async def read_operation():
            return await User.objects.using(session).filter(User.age > 30).count()

        async def write_operation():
            return await User.objects.using(session).create(
                username=f"concurrent_user_{int(time.time() * 1000000)}",
                email=f"concurrent{int(time.time() * 1000000)}@example.com",
                age=25,
            )

        # Mix of read and write operations
        performance_monitor.start()
        tasks = []
        for i in range(10):
            if i % 2 == 0:
                tasks.append(read_operation())
            else:
                tasks.append(write_operation())

        results = await asyncio.gather(*tasks)
        execution_time = performance_monitor.stop()["execution_time"]

        # All operations should complete
        assert len(results) == 10

        # Should complete within reasonable time
        assert execution_time < 8.0, f"Mixed operations took {execution_time:.2f}s"


class TestQueryOptimizationFeatures:
    """Test query optimization features"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_distinct_query_performance(self, session, performance_monitor):
        """Test DISTINCT query performance"""
        # Regular query
        performance_monitor.start()
        regular_users = await User.objects.using(session).filter(User.age > 20).all()
        regular_time = performance_monitor.stop()["execution_time"]

        # DISTINCT query
        performance_monitor.start()
        distinct_users = await User.objects.using(session).filter(User.age > 20).distinct().all()
        distinct_time = performance_monitor.stop()["execution_time"]

        # DISTINCT may return fewer records but should complete reasonably
        assert len(distinct_users) <= len(regular_users)
        assert distinct_time < regular_time * 2  # Allow 2x slower for DISTINCT

    @pytest.mark.usefixtures("large_dataset")
    async def test_limit_offset_performance(self, session, performance_monitor):
        """Test LIMIT/OFFSET query performance"""
        # Small offset
        performance_monitor.start()
        small_offset = await User.objects.using(session).order_by("id").limit(100).offset(100).all()
        small_offset_time = performance_monitor.stop()["execution_time"]

        # Large offset
        performance_monitor.start()
        large_offset = await User.objects.using(session).order_by("id").limit(100).offset(5000).all()
        large_offset_time = performance_monitor.stop()["execution_time"]

        # Both should return 100 records
        assert len(small_offset) == len(large_offset) == 100

        # Both should complete within reasonable time
        assert small_offset_time < 2.0
        assert large_offset_time < 3.0  # Large offset may be slower

    @pytest.mark.usefixtures("large_dataset")
    async def test_expression_system_performance(self, session, performance_monitor):
        """Test new expression system performance vs traditional approach"""
        # Test old approach (multiple queries)
        performance_monitor.start()
        avg_result = await User.objects.using(session).aggregate(avg_age=User.age.avg())
        avg_age = avg_result["avg_age"]
        older_users_old = await User.objects.using(session).filter(User.age > avg_age).all()
        multi_query_time = performance_monitor.stop()["execution_time"]

        # Test new expression approach (single query with subquery)
        performance_monitor.start()
        avg_age_expr = User.objects.using(session).aggregate(avg_age=User.age.avg()).scalar_subquery()
        older_users_new = await User.objects.using(session).filter(User.age > avg_age_expr).all()
        expression_time = performance_monitor.stop()["execution_time"]

        # Both approaches should return similar results
        assert len(older_users_old) == len(older_users_new)

        # Both approaches should complete within reasonable time
        assert multi_query_time < 3.0, f"Multi-query approach took {multi_query_time:.2f}s"
        assert expression_time < 3.0, f"Expression approach took {expression_time:.2f}s"

        # Expression approach should be faster (single query vs multiple queries)
        assert expression_time <= multi_query_time * 1.2, "Expression approach should be competitive"

        print(f"Multi-query time: {multi_query_time:.3f}s, Expression time: {expression_time:.3f}s")
        print(f"Performance improvement: {((multi_query_time - expression_time) / multi_query_time * 100):.1f}%")


class TestQueryPerformanceBenchmarks:
    """Comprehensive query performance benchmarks"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_query_performance_regression(self, session, performance_monitor):
        """Test for query performance regressions"""
        # Performance targets (adjust based on expected performance)
        targets = {
            "simple_filter": 1.0,  # seconds
            "complex_filter": 2.0,  # seconds
            "aggregation": 1.5,  # seconds
            "count_query": 0.5,  # seconds
        }

        # Simple filter
        performance_monitor.start()
        await User.objects.using(session).filter(User.age > 25).all()
        simple_time = performance_monitor.stop()["execution_time"]

        # Complex filter
        performance_monitor.start()
        await (
            User.objects.using(session)
            .filter(User.age >= 25, User.age <= 45, User.is_active == True)
            .order_by("-age")
            .limit(1000)
            .all()
        )
        complex_time = performance_monitor.stop()["execution_time"]

        # Aggregation
        performance_monitor.start()
        await User.objects.using(session).aggregate(count=func.count(), avg_age=User.age.avg())
        agg_time = performance_monitor.stop()["execution_time"]

        # Count query
        performance_monitor.start()
        await User.objects.using(session).skip_default_ordering().count()
        count_time = performance_monitor.stop()["execution_time"]

        # Check against targets
        assert simple_time < targets["simple_filter"], (
            f"Simple filter regression: {simple_time:.2f}s > {targets['simple_filter']}s"
        )

        assert complex_time < targets["complex_filter"], (
            f"Complex filter regression: {complex_time:.2f}s > {targets['complex_filter']}s"
        )

        assert agg_time < targets["aggregation"], f"Aggregation regression: {agg_time:.2f}s > {targets['aggregation']}s"

        assert count_time < targets["count_query"], (
            f"Count query regression: {count_time:.2f}s > {targets['count_query']}s"
        )

    @pytest.mark.usefixtures("large_dataset")
    async def test_comprehensive_query_benchmark(self, session, performance_monitor):
        """Comprehensive query benchmark across different patterns"""
        benchmarks = {
            "Filter by single field": lambda: User.objects.using(session).filter(User.age == 25).all(),
            "Filter by multiple fields": lambda: (
                User.objects.using(session).filter(User.age > 25, User.is_active == True).all()
            ),
            "String pattern matching": lambda: User.objects.using(session).filter(User.username.like("%user_1%")).all(),
            "Ordering": lambda: User.objects.using(session).order_by("-age").limit(1000).all(),
            "Count query": lambda: User.objects.using(session).count(),
            "Exists query": lambda: User.objects.using(session).filter(User.age > 50).exists(),
            "Aggregation": lambda: User.objects.using(session).aggregate(avg_age=User.age.avg()),
            "First/Last": lambda: User.objects.using(session).order_by("age").first(),
        }

        results = {}

        for name, query_func in benchmarks.items():
            performance_monitor.start()
            _result = await query_func()
            execution_time = performance_monitor.stop()["execution_time"]

            results[name] = execution_time

            # All queries should complete within reasonable time
            assert execution_time < 5.0, f"{name} took {execution_time:.2f}s"

        # Print benchmark results
        print("\nQuery Performance Benchmark Results:")
        for name, time_taken in results.items():
            print(f"{name}: {time_taken:.3f}s")
