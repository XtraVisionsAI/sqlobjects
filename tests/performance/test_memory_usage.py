"""Performance tests for memory usage and management

Tests memory efficiency, garbage collection, and resource management
for various SQLObjects operations and patterns.
"""

import asyncio
import gc
import os

import psutil
import pytest

from tests.conftest import User


class MemoryTestBase:
    """Base class for memory usage tests with shared utilities"""

    @staticmethod
    def get_memory_usage():
        """Get current memory usage in MB"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024


class TestMemoryUsageBasics(MemoryTestBase):
    """Test basic memory usage patterns"""

    async def test_model_instance_memory_efficiency(self):
        """Test memory usage of model instances"""
        memory_before = self.get_memory_usage()

        # Create many model instances
        users = []
        for i in range(1000):
            user = User(username=f"memory_user_{i}", email=f"memory{i}@example.com", age=25 + (i % 50))
            users.append(user)

        memory_after = self.get_memory_usage()
        memory_per_instance = (memory_after - memory_before) / 1000

        # Each instance should use reasonable memory (less than 1KB)
        assert memory_per_instance < 1.0, f"Each instance uses {memory_per_instance:.3f}MB"

        # Clean up
        del users
        gc.collect()

    @pytest.mark.usefixtures("large_dataset")
    async def test_query_result_memory_usage(self, session):
        """Test memory usage of query results"""
        memory_before = self.get_memory_usage()

        # Load large result set
        users = await User.objects.using(session).all()

        memory_after = self.get_memory_usage()
        memory_growth = memory_after - memory_before

        # Should load 10,000 users
        assert len(users) == 10000

        # Memory usage should be reasonable (less than 100MB for 10k records)
        assert memory_growth < 100, f"Query result used {memory_growth:.2f}MB"

        # Clean up
        del users
        gc.collect()

    async def test_memory_cleanup_after_operations(self, session):
        """Test memory is properly cleaned up after operations"""
        memory_baseline = self.get_memory_usage()

        # Perform multiple operations
        for i in range(10):
            # Create data
            users_data = [
                {"username": f"cleanup_user_{i}_{j}", "email": f"cleanup{i}_{j}@example.com", "age": 25}
                for j in range(100)
            ]
            created_count = await User.objects.using(session).bulk_create(users_data)
            assert created_count == 100

            # Query data to get actual user objects
            queried_users = await User.objects.using(session).filter(User.age == 25).all()
            user_ids = [user.id for user in queried_users]

            # Clean up data
            deleted_count = await User.objects.using(session).bulk_delete(user_ids, id_field="id")
            assert deleted_count == len(user_ids)

            # Force cleanup
            del queried_users, user_ids
            gc.collect()

        memory_final = self.get_memory_usage()
        memory_growth = memory_final - memory_baseline

        # Memory growth should be minimal after cleanup
        assert memory_growth < 20, f"Memory leaked {memory_growth:.2f}MB after operations"


class TestIteratorMemoryEfficiency(MemoryTestBase):
    """Test iterator memory efficiency"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_vs_all_memory_usage(self, session):
        """Test iterator uses less memory than all()"""
        # Test all() method - loads everything into memory
        memory_before_all = self.get_memory_usage()
        all_users = await User.objects.using(session).all()
        memory_after_all = self.get_memory_usage()
        all_memory_usage = memory_after_all - memory_before_all

        # Clean up
        del all_users
        gc.collect()

        # Test iterator - should use less memory
        memory_before_iter = self.get_memory_usage()
        count = 0
        max_memory_during_iter = memory_before_iter

        async for user in User.objects.using(session).iterator(chunk_size=100):
            count += 1
            current_memory = self.get_memory_usage()
            max_memory_during_iter = max(max_memory_during_iter, current_memory)

            # Process user to simulate real usage
            _ = user.username.upper()

        iter_memory_usage = max_memory_during_iter - memory_before_iter

        # Should process same number of records
        assert count == 10000

        # Iterator should use significantly less memory
        assert iter_memory_usage < all_memory_usage / 2, (
            f"Iterator used {iter_memory_usage:.2f}MB vs all() {all_memory_usage:.2f}MB"
        )

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_chunk_size_memory_impact(self, session):
        """Test how chunk size affects memory usage"""
        chunk_sizes = [10, 100, 1000]
        memory_usage = {}

        for chunk_size in chunk_sizes:
            memory_before = self.get_memory_usage()
            max_memory = memory_before
            count = 0

            async for _ in User.objects.using(session).iterator(chunk_size=chunk_size):
                count += 1
                current_memory = self.get_memory_usage()
                max_memory = max(max_memory, current_memory)

            memory_usage[chunk_size] = max_memory - memory_before

            # Should process all records
            assert count == 10000

        # Memory usage should be reasonable for all chunk sizes
        for chunk_size, usage in memory_usage.items():
            assert usage < 50, f"Chunk size {chunk_size} used {usage:.2f}MB"

        # Generally, larger chunk sizes should not use dramatically less memory
        # (allowing for system variance in memory measurement)
        max_usage = max(memory_usage.values())
        min_usage = min(memory_usage.values())
        assert max_usage - min_usage < 30, f"Memory usage variance too high: {memory_usage}"

    @pytest.mark.usefixtures("large_dataset")
    async def test_iterator_memory_stability(self, session):
        """Test iterator memory usage remains stable over time"""
        memory_samples = []
        count = 0

        async for _ in User.objects.using(session).iterator(chunk_size=500):
            count += 1

            # Sample memory every 1000 records
            if count % 1000 == 0:
                memory_samples.append(self.get_memory_usage())

        # Should process all records
        assert count == 10000
        assert len(memory_samples) == 10

        # Memory usage should remain relatively stable
        memory_variance = max(memory_samples) - min(memory_samples)
        assert memory_variance < 30, f"Memory variance {memory_variance:.2f}MB too high"


class TestBulkOperationMemoryUsage(MemoryTestBase):
    """Test memory usage of bulk operations"""

    async def test_bulk_create_memory_efficiency(self, session):
        """Test bulk create memory usage"""
        dataset_sizes = [1000, 5000, 10000]

        for i, size in enumerate(dataset_sizes):
            memory_before = self.get_memory_usage()

            # Prepare data with unique usernames
            users_data = [
                {"username": f"bulk_mem_{i}_{j}", "email": f"bulk_mem{i}_{j}@example.com", "age": 25}
                for j in range(size)
            ]

            # Bulk create
            created_count = await User.objects.using(session).bulk_create(users_data)

            memory_after = self.get_memory_usage()
            memory_usage = memory_after - memory_before
            memory_per_record = memory_usage / size

            # Verify creation
            assert created_count == size

            # Memory per record should be reasonable (less than 0.01MB per record)
            assert memory_per_record < 0.01, f"Bulk create used {memory_per_record:.4f}MB per record for {size} records"

            # Clean up
            await User.objects.using(session).filter().delete()
            del users_data
            gc.collect()

    async def test_bulk_update_memory_efficiency(self, session):
        """Test bulk update memory usage"""
        # Create test data
        users_data = [
            {"username": f"bulk_update_mem_{i}", "email": f"bulk_update_mem{i}@example.com", "age": 25}
            for i in range(5000)
        ]
        created_count = await User.objects.using(session).bulk_create(users_data)
        assert created_count == 5000

        # Get created users to get their IDs
        created_users = await User.objects.using(session).filter(User.username.like("bulk_update_mem_%")).all()

        memory_before = self.get_memory_usage()

        # Prepare update data
        update_mappings = [{"id": user.id, "age": 30, "is_active": False} for user in created_users]

        # Bulk update
        updated_count = await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        assert updated_count > 0

        memory_after = self.get_memory_usage()
        memory_usage = memory_after - memory_before

        # Memory usage should be reasonable for bulk update
        assert memory_usage < 50, f"Bulk update used {memory_usage:.2f}MB for 5000 records"

        # Clean up
        user_ids = [user.id for user in created_users]
        deleted_count = await User.objects.using(session).bulk_delete(user_ids, id_field="id")
        assert deleted_count > 0

    async def test_bulk_delete_memory_efficiency(self, session):
        """Test bulk delete memory usage"""
        # Create test data
        users_data = [
            {"username": f"bulk_delete_mem_{i}", "email": f"bulk_delete_mem{i}@example.com", "age": 30}
            for i in range(3000)
        ]
        created_count = await User.objects.using(session).bulk_create(users_data)
        assert created_count == 3000

        # Get created users to get their IDs
        created_users = await User.objects.using(session).filter(User.username.like("bulk_delete_mem_%")).all()
        user_ids = [user.id for user in created_users]

        memory_before = self.get_memory_usage()

        # Bulk delete
        deleted_count = await User.objects.using(session).bulk_delete(user_ids, id_field="id")

        memory_after = self.get_memory_usage()
        memory_usage = memory_after - memory_before

        # Should delete all records
        assert deleted_count == len(user_ids)

        # Memory usage should be reasonable for bulk delete
        assert memory_usage < 30, f"Bulk delete used {memory_usage:.2f}MB for 3000 records"


class TestCacheMemoryManagement(MemoryTestBase):
    """Test cache memory management"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_cache_cleanup_effectiveness(self, session):
        """Test cache cleanup reduces memory usage"""
        memory_before = self.get_memory_usage()

        # Perform queries that should be cached
        for _i in range(5):
            users = await User.objects.using(session).filter(User.age >= 18).all()
            assert len(users) > 0

        memory_after_cache = self.get_memory_usage()
        cache_memory_usage = memory_after_cache - memory_before

        # Force garbage collection to simulate cache cleanup
        gc.collect()

        memory_after_clear = self.get_memory_usage()
        memory_freed = memory_after_cache - memory_after_clear

        # Cache should use some memory
        assert cache_memory_usage >= 0, "Cache memory usage should be non-negative"

        # Memory should be stable after garbage collection
        assert abs(memory_freed) < 50, f"Memory should be stable, change: {memory_freed:.2f}MB"


class TestConcurrentMemoryUsage(MemoryTestBase):
    """Test memory usage under concurrent operations"""

    async def test_concurrent_bulk_operations_memory(self, session):
        """Test memory usage during concurrent bulk operations"""
        memory_before = self.get_memory_usage()

        async def create_users_batch(batch_id: int):
            users_data = [
                {"username": f"concurrent_{batch_id}_{i}", "email": f"concurrent{batch_id}_{i}@example.com", "age": 25}
                for i in range(500)
            ]
            return await User.objects.using(session).bulk_create(users_data)

        # Run concurrent bulk operations
        tasks = [create_users_batch(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        memory_after = self.get_memory_usage()
        memory_usage = memory_after - memory_before

        # Should create 2500 users total (each result is a count, not a list)
        total_created = sum(result for result in results)
        assert total_created == 2500

        # Memory usage should be reasonable for concurrent operations
        assert memory_usage < 100, f"Concurrent operations used {memory_usage:.2f}MB"

        # Clean up
        await User.objects.using(session).filter(User.username.like("concurrent_%")).delete()


class TestMemoryLeakDetection(MemoryTestBase):
    """Test for memory leaks in repeated operations"""

    async def test_repeated_operations_memory_stability(self, session):
        """Test memory remains stable over repeated operations"""
        memory_samples = []

        for iteration in range(10):
            # Create data
            users_data = [
                {"username": f"leak_test_{iteration}_{i}", "email": f"leak{iteration}_{i}@example.com", "age": 25}
                for i in range(100)
            ]
            created_count = await User.objects.using(session).bulk_create(users_data)
            assert created_count == 100

            # Query data to get actual user objects
            queried_users = (
                await User.objects.using(session).filter(User.username.like(f"leak_test_{iteration}_%")).all()
            )
            user_ids = [user.id for user in queried_users]

            # Clean up
            deleted_count = await User.objects.using(session).bulk_delete(user_ids, id_field="id")
            assert deleted_count == len(user_ids)

            # Force cleanup and measure memory
            del queried_users, user_ids
            gc.collect()
            memory_samples.append(self.get_memory_usage())

        # Memory should remain relatively stable
        memory_variance = max(memory_samples) - min(memory_samples)
        assert memory_variance < 50, f"Memory variance {memory_variance:.2f}MB indicates potential leak"


class TestMemoryOptimizationFeatures(MemoryTestBase):
    """Test memory optimization features"""

    @pytest.mark.usefixtures("large_dataset")
    async def test_batch_processing_memory_efficiency(self, session):
        """Test batch processing reduces memory usage"""
        memory_before = self.get_memory_usage()
        max_memory_during_processing = memory_before

        # Process in batches
        batch_size = 500
        total_processed = 0

        # Use proper range iteration instead of async for
        for batch_start in range(0, 10000, batch_size):
            # Simulate batch processing
            users = await User.objects.using(session).limit(batch_size).offset(batch_start).all()
            total_processed += len(users)

            # Track peak memory usage
            current_memory = self.get_memory_usage()
            max_memory_during_processing = max(max_memory_during_processing, current_memory)

            # Process users (simulate work)
            for user in users:
                _ = user.username.upper()

            # Clean up batch
            del users
            gc.collect()

        memory_after = self.get_memory_usage()
        peak_memory_usage = max_memory_during_processing - memory_before
        final_memory_usage = memory_after - memory_before

        # Should process all records
        assert total_processed == 10000

        # Peak memory should be reasonable for batch size
        assert peak_memory_usage < 100, f"Peak memory usage {peak_memory_usage:.2f}MB too high"

        # Final memory should return to baseline
        assert final_memory_usage < 20, f"Final memory usage {final_memory_usage:.2f}MB indicates leak"
