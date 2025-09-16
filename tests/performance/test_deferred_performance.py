"""Performance tests for deferred field loading and proxy system"""

import asyncio
import gc
import os
import time

import psutil
import pytest

from sqlobjects.fields import Column, StringColumn, column, identity
from sqlobjects.fields.proxies import DeferredFieldProxy
from tests.conftest import TestModel


class PerformanceTestUser(TestModel):
    """User model optimized for performance testing"""

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100)

    # Various sizes of deferred content for performance testing
    small_bio: Column[str] = column(type="text", deferred=True)  # ~100 bytes
    medium_content: Column[str] = column(type="text", deferred=True)  # ~1KB
    large_content: Column[str] = column(type="text", deferred=True)  # ~10KB
    huge_content: Column[str] = column(type="text", deferred=True)  # ~100KB


@pytest.fixture
async def performance_dataset(session):
    """Create dataset for performance testing"""
    # Generate content of different sizes
    small_content = "x" * 100  # 100 bytes
    medium_content = "x" * 1024  # 1KB
    large_content = "x" * 10240  # 10KB
    huge_content = "x" * 102400  # 100KB

    # Create test users with varying content sizes
    users_data = []
    for i in range(100):  # 100 users for meaningful performance testing
        users_data.append(
            {
                "username": f"perfuser{i:03d}",
                "email": f"perfuser{i:03d}@example.com",
                "small_bio": f"Bio {i}: {small_content}",
                "medium_content": f"Content {i}: {medium_content}",
                "large_content": f"Large {i}: {large_content}",
                "huge_content": f"Huge {i}: {huge_content}",
            }
        )

    await PerformanceTestUser.objects.using(session).bulk_create(users_data)
    return await PerformanceTestUser.objects.using(session).all()


@pytest.mark.usefixtures("performance_dataset")
class TestDeferredFieldPerformance:
    """Test performance characteristics of deferred field system"""

    async def test_memory_usage_with_deferred_fields(self, session):
        """Benchmark: Memory usage patterns for deferred vs full loading"""
        process = psutil.Process(os.getpid())

        # Baseline measurement
        gc.collect()
        memory_baseline = process.memory_info().rss / 1024 / 1024

        # Benchmark full loading
        start_time = time.perf_counter()
        full_users = await PerformanceTestUser.objects.using(session).all()
        full_load_time = time.perf_counter() - start_time
        gc.collect()
        memory_full = process.memory_info().rss / 1024 / 1024

        # Benchmark deferred loading
        del full_users
        gc.collect()
        start_time = time.perf_counter()
        deferred_users = (
            await PerformanceTestUser.objects.using(session)
            .defer("small_bio", "medium_content", "large_content", "huge_content")
            .all()
        )
        deferred_load_time = time.perf_counter() - start_time
        gc.collect()
        memory_deferred = process.memory_info().rss / 1024 / 1024

        full_usage = memory_full - memory_baseline
        deferred_usage = memory_deferred - memory_baseline

        # Performance benchmarks: measure actual performance characteristics
        print(f"\nMemory benchmark: Full={full_usage:.2f}MB, Deferred={deferred_usage:.2f}MB")
        print(f"Load time benchmark: Full={full_load_time * 1000:.1f}ms, Deferred={deferred_load_time * 1000:.1f}ms")

        # Realistic performance targets
        assert full_load_time < 1.0, f"Full loading too slow: {full_load_time:.2f}s"
        assert deferred_load_time < 1.0, f"Deferred loading too slow: {deferred_load_time:.2f}s"
        assert len(deferred_users) == 100, "Record count mismatch"

    async def test_query_performance_with_deferred_fields(self, session):
        """Test query performance difference with deferred fields"""

        # Measure time for full query
        start_time = time.perf_counter()
        full_users = await PerformanceTestUser.objects.using(session).all()
        full_query_time = time.perf_counter() - start_time

        # Measure time for deferred query
        start_time = time.perf_counter()
        deferred_users = (
            await PerformanceTestUser.objects.using(session)
            .defer("small_bio", "medium_content", "large_content", "huge_content")
            .all()
        )
        deferred_query_time = time.perf_counter() - start_time

        # Performance benchmarks: measure query performance characteristics
        print(f"\nQuery performance: Full={full_query_time * 1000:.1f}ms, Deferred={deferred_query_time * 1000:.1f}ms")

        # Realistic performance targets
        assert full_query_time < 1.0, f"Full query too slow: {full_query_time:.2f}s"
        assert deferred_query_time < 1.0, f"Deferred query too slow: {deferred_query_time:.2f}s"
        assert len(full_users) == len(deferred_users) == 100, "Record count mismatch"

    async def test_selective_loading_performance(self, session):
        """Benchmark: Individual field loading performance"""

        # Load users with deferred fields
        users = await PerformanceTestUser.objects.using(session).defer("small_bio", "huge_content").limit(10).all()

        # Benchmark small field loading
        start_time = time.perf_counter()
        for user in users[:5]:
            await user.load_deferred_fields(["small_bio"])
        small_time = time.perf_counter() - start_time

        # Benchmark large field loading
        start_time = time.perf_counter()
        for user in users[5:]:
            await user.load_deferred_fields(["huge_content"])
        large_time = time.perf_counter() - start_time

        # Performance benchmarks: measure actual loading performance
        small_per_field = small_time / 5 * 1000  # ms per field
        large_per_field = large_time / 5 * 1000  # ms per field

        print(f"\nField loading benchmark: Small={small_per_field:.1f}ms/field, Large={large_per_field:.1f}ms/field")

        # Reasonable performance targets for any field size
        assert small_per_field < 200, f"Small field loading too slow: {small_per_field:.1f}ms/field"
        assert large_per_field < 1000, f"Large field loading too slow: {large_per_field:.1f}ms/field"

    async def test_batch_deferred_loading_efficiency(self, session):
        """Benchmark: Field loading method performance comparison"""

        users = await PerformanceTestUser.objects.using(session).defer("small_bio", "medium_content").limit(20).all()

        # Benchmark individual field loading
        start_time = time.perf_counter()
        for user in users[:10]:
            await user.load_deferred_field("small_bio")
            await user.load_deferred_field("medium_content")
        individual_time = time.perf_counter() - start_time

        # Benchmark batch field loading
        start_time = time.perf_counter()
        for user in users[10:]:
            await user.load_deferred_fields(["small_bio", "medium_content"])
        batch_time = time.perf_counter() - start_time

        # Performance benchmarks: measure loading method performance
        individual_per_user = individual_time / 10 * 1000  # ms per user
        batch_per_user = batch_time / 10 * 1000  # ms per user

        print(
            f"\nField loading methods: Individual={individual_per_user:.1f}ms/user, Batch={batch_per_user:.1f}ms/user"
        )

        # Reasonable performance targets for both methods
        assert individual_per_user < 500, f"Individual loading too slow: {individual_per_user:.1f}ms/user"
        assert batch_per_user < 500, f"Batch loading too slow: {batch_per_user:.1f}ms/user"

    async def test_proxy_object_creation_overhead(self, session):
        """Test overhead of proxy object creation"""

        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="proxytest", email="proxy@example.com", small_bio="Test bio"
        )

        # Load with deferred field
        loaded_user = (
            await PerformanceTestUser.objects.using(session).defer("small_bio").get(PerformanceTestUser.id == user.id)
        )
        loaded_user._state_manager.set("is_from_db", True)

        # Measure proxy creation time
        start_time = time.perf_counter()
        for _ in range(1000):
            proxy = DeferredFieldProxy(loaded_user, "small_bio")
            _ = proxy.field_name  # Access to ensure object is created
        proxy_creation_time = time.perf_counter() - start_time

        # Proxy creation should be very fast (< 1ms per proxy)
        avg_time_per_proxy = proxy_creation_time / 1000
        assert avg_time_per_proxy < 0.001, f"Proxy creation should be fast: {avg_time_per_proxy:.6f}s per proxy"

    async def test_deferred_field_cache_efficiency(self, session):
        """Test caching efficiency of deferred field proxies"""

        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="cachetest", email="cache@example.com", small_bio="Cached bio content"
        )

        # Load with deferred field
        loaded_user = (
            await PerformanceTestUser.objects.using(session).defer("small_bio").get(PerformanceTestUser.id == user.id)
        )

        proxy = DeferredFieldProxy(loaded_user, "small_bio")

        # First fetch (should load from database)
        start_time = time.perf_counter()
        result1 = await proxy.fetch()
        first_fetch_time = time.perf_counter() - start_time

        # Second fetch (should use cache)
        start_time = time.perf_counter()
        result2 = await proxy.fetch()
        second_fetch_time = time.perf_counter() - start_time

        # Cached access should be much faster
        assert second_fetch_time < first_fetch_time / 10, (
            f"Cached access should be much faster: {second_fetch_time:.6f}s vs {first_fetch_time:.6f}s"
        )

        # Results should be identical
        assert result1 == result2 == "Cached bio content"

    async def test_large_dataset_deferred_loading(self, session):
        """Benchmark: Dataset query throughput"""

        # Benchmark full query
        start_time = time.perf_counter()
        full_users = await PerformanceTestUser.objects.using(session).all()
        full_time = time.perf_counter() - start_time

        # Benchmark deferred query
        start_time = time.perf_counter()
        deferred_users = (
            await PerformanceTestUser.objects.using(session)
            .defer("small_bio", "medium_content", "large_content", "huge_content")
            .all()
        )
        deferred_time = time.perf_counter() - start_time

        # Performance benchmarks: measure query throughput
        records_per_sec_full = len(full_users) / full_time if full_time > 0 else 0
        records_per_sec_deferred = len(deferred_users) / deferred_time if deferred_time > 0 else 0

        print(
            f"\nQuery throughput: Full={records_per_sec_full:.0f} rec/s, Deferred={records_per_sec_deferred:.0f} rec/s"
        )
        print(f"Query time: Full={full_time * 1000:.1f}ms, Deferred={deferred_time * 1000:.1f}ms")

        # Reasonable performance targets
        assert full_time < 5.0, f"Full query too slow: {full_time:.2f}s for {len(full_users)} records"
        assert deferred_time < 5.0, f"Deferred query too slow: {deferred_time:.2f}s for {len(deferred_users)} records"
        assert records_per_sec_full >= 20, f"Full query throughput too low: {records_per_sec_full:.0f} rec/s"
        assert records_per_sec_deferred >= 20, (
            f"Deferred query throughput too low: {records_per_sec_deferred:.0f} rec/s"
        )

    async def test_concurrent_deferred_loading(self, session):
        """Test performance of concurrent deferred field loading"""

        # Create test users
        users_data = []
        for i in range(50):
            users_data.append(
                {
                    "username": f"concurrent{i:02d}",
                    "email": f"concurrent{i:02d}@example.com",
                    "medium_content": f"Content for concurrent test {i}: " + "x" * 1000,
                }
            )

        await PerformanceTestUser.objects.using(session).bulk_create(users_data)

        # Load users with deferred fields
        users = (
            await PerformanceTestUser.objects.using(session)
            .defer("medium_content")
            .filter(PerformanceTestUser.username.like("concurrent%"))
            .all()
        )

        # Measure sequential loading
        start_time = time.perf_counter()
        for user in users[:25]:
            await user.load_deferred_field("medium_content")
        sequential_time = time.perf_counter() - start_time

        # Measure concurrent loading
        start_time = time.perf_counter()
        tasks = [user.load_deferred_field("medium_content") for user in users[25:]]
        await asyncio.gather(*tasks)
        concurrent_time = time.perf_counter() - start_time

        # Concurrent loading should be faster (due to async I/O)
        assert concurrent_time < sequential_time, (
            f"Concurrent loading should be faster: {concurrent_time:.3f}s vs {sequential_time:.3f}s"
        )


class TestDeferredFieldScalability:
    """Benchmark scalability characteristics of deferred field system"""

    async def test_deferred_field_count_scalability(self, session):
        """Benchmark: Field status check performance"""

        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="manyfields",
            email="many@example.com",
            small_bio="Bio",
            medium_content="Content",
            large_content="Large",
            huge_content="Huge",
        )

        # Load with all fields deferred
        loaded_user = (
            await PerformanceTestUser.objects.using(session)
            .defer("small_bio", "medium_content", "large_content", "huge_content")
            .get(PerformanceTestUser.id == user.id)
        )

        # Benchmark field status checks
        field_names = ["small_bio", "medium_content", "large_content", "huge_content"]

        start_time = time.perf_counter()
        for _ in range(1000):  # Repeat for meaningful measurement
            for field_name in field_names:
                _ = loaded_user.is_field_deferred(field_name)
                _ = loaded_user.is_field_loaded(field_name)
        status_check_time = time.perf_counter() - start_time

        # Performance benchmark: status checks should be fast
        total_checks = 1000 * len(field_names) * 2
        avg_time_per_check = status_check_time / total_checks * 1000000  # microseconds

        print(
            f"\nField status benchmark: "
            f"{avg_time_per_check:.1f}μs per check ({total_checks} checks in {status_check_time * 1000:.1f}ms)"
        )

        assert avg_time_per_check < 100, f"Status checks too slow: {avg_time_per_check:.1f}μs per check"

    async def test_deferred_field_memory_scalability(self, session):
        """Benchmark: Memory usage patterns with varying deferred field counts"""
        process = psutil.Process(os.getpid())

        # Baseline
        gc.collect()
        base_memory = process.memory_info().rss / 1024 / 1024

        # Benchmark with 1 deferred field
        start_time = time.perf_counter()
        users_1 = await PerformanceTestUser.objects.using(session).defer("huge_content").all()
        time_1 = time.perf_counter() - start_time
        gc.collect()
        memory_1 = process.memory_info().rss / 1024 / 1024
        users_1_count = len(users_1)

        # Benchmark with 4 deferred fields
        del users_1
        gc.collect()
        start_time = time.perf_counter()
        users_4 = (
            await PerformanceTestUser.objects.using(session)
            .defer("small_bio", "medium_content", "large_content", "huge_content")
            .all()
        )
        time_4 = time.perf_counter() - start_time
        gc.collect()
        memory_4 = process.memory_info().rss / 1024 / 1024

        usage_1 = memory_1 - base_memory
        usage_4 = memory_4 - base_memory

        # Performance benchmarks: measure scaling characteristics
        print(
            f"\nDeferred field scaling: "
            f"1 field={usage_1:.2f}MB/{time_1 * 1000:.1f}ms, 4 fields={usage_4:.2f}MB/{time_4 * 1000:.1f}ms"
        )

        # Reasonable performance targets
        assert time_1 < 2.0, f"1-field query too slow: {time_1:.2f}s"
        assert time_4 < 2.0, f"4-field query too slow: {time_4:.2f}s"
        assert users_1_count == len(users_4), "Record count mismatch"

    async def test_proxy_cache_performance(self, session):
        """Benchmark: Proxy object caching performance"""

        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="proxycache", email="proxycache@example.com", small_bio="Bio for proxy cache test"
        )

        # Load with deferred field
        loaded_user = (
            await PerformanceTestUser.objects.using(session).defer("small_bio").get(PerformanceTestUser.id == user.id)
        )
        loaded_user._state_manager.set("is_from_db", True)

        # Benchmark first proxy access (creation)
        start_time = time.perf_counter()
        proxy1 = loaded_user.small_bio
        first_access_time = time.perf_counter() - start_time

        # Benchmark subsequent proxy access (cached)
        start_time = time.perf_counter()
        proxy2 = loaded_user.small_bio
        second_access_time = time.perf_counter() - start_time

        # Performance benchmarks: measure proxy access performance
        first_access_us = first_access_time * 1000000  # microseconds
        second_access_us = second_access_time * 1000000  # microseconds

        print(f"\nProxy access benchmark: First={first_access_us:.1f}μs, Cached={second_access_us:.1f}μs")

        # Reasonable performance targets
        assert first_access_us < 1000, f"First proxy access too slow: {first_access_us:.1f}μs"
        assert second_access_us < 100, f"Cached proxy access too slow: {second_access_us:.1f}μs"
        assert proxy1 is proxy2, "Proxy objects should be cached and reused"


class TestDeferredFieldBenchmarks:
    """Benchmark tests for deferred field system"""

    async def test_deferred_vs_regular_field_access_benchmark(self, session):
        """Benchmark deferred vs regular field access performance"""

        # Create test user
        user = await PerformanceTestUser.objects.using(session).create(
            username="benchmark", email="benchmark@example.com", small_bio="Benchmark bio content"
        )

        # Load user normally (no deferred fields)
        normal_user = await PerformanceTestUser.objects.using(session).get(PerformanceTestUser.id == user.id)

        # Load user with deferred field
        deferred_user = (
            await PerformanceTestUser.objects.using(session).defer("small_bio").get(PerformanceTestUser.id == user.id)
        )

        # Load the deferred field
        await deferred_user.load_deferred_field("small_bio")

        # Benchmark regular field access
        start_time = time.perf_counter()
        for _ in range(10000):
            _ = normal_user.small_bio
        normal_access_time = time.perf_counter() - start_time

        # Benchmark loaded deferred field access
        start_time = time.perf_counter()
        for _ in range(10000):
            _ = deferred_user.small_bio
        deferred_access_time = time.perf_counter() - start_time

        # Loaded deferred field access should be comparable to normal access
        # Allow up to 2x slower due to additional checks
        assert deferred_access_time < normal_access_time * 2, (
            f"Loaded deferred field access should be reasonable: "
            f"{deferred_access_time:.3f}s vs {normal_access_time:.3f}s"
        )

    async def test_bulk_deferred_loading_benchmark(self, session):
        """Benchmark bulk deferred field loading performance"""

        # Create many users with deferred content
        content = "x" * 1000  # 1KB per field
        users_data = []
        for i in range(200):
            users_data.append(
                {
                    "username": f"bulkuser{i:03d}",
                    "email": f"bulkuser{i:03d}@example.com",
                    "medium_content": f"Content {i}: {content}",
                }
            )

        await PerformanceTestUser.objects.using(session).bulk_create(users_data)

        # Load users with deferred fields
        users = (
            await PerformanceTestUser.objects.using(session)
            .defer("medium_content")
            .filter(PerformanceTestUser.username.like("bulkuser%"))
            .all()
        )

        # Benchmark bulk loading
        start_time = time.perf_counter()
        for user in users:
            await user.load_deferred_field("medium_content")
        bulk_load_time = time.perf_counter() - start_time

        # Should complete within reasonable time (< 5 seconds for 200 users)
        assert bulk_load_time < 5.0, (
            f"Bulk deferred loading should complete quickly: {bulk_load_time:.3f}s for 200 users"
        )

        # Calculate throughput
        throughput = len(users) / bulk_load_time
        assert throughput > 40, f"Should achieve reasonable throughput: {throughput:.1f} loads/second"
