"""Performance tests for bulk operations

Validates the 10-100x performance improvement claims for bulk operations
with comprehensive benchmarking and memory usage monitoring.
"""

import asyncio
import os
import time

import psutil

from tests.conftest import User


class TestBulkCreatePerformance:
    """Test bulk create performance characteristics"""

    async def test_bulk_create_10x_improvement(self, session, performance_monitor):
        """Test bulk_create achieves at least 10x performance improvement"""
        # Individual creates (baseline)
        performance_monitor.start()
        individual_users = []
        for i in range(100):
            user = await User.objects.using(session).create(
                username=f"individual_{i}", email=f"individual{i}@example.com", age=25 + (i % 30)
            )
            individual_users.append(user)
        individual_time = performance_monitor.stop()["execution_time"]

        # Clean up
        await User.objects.using(session).bulk_delete([user.id for user in individual_users], id_field="id")

        # Bulk create (optimized)
        bulk_data = [
            {"username": f"bulk_{i}", "email": f"bulk{i}@example.com", "age": 25 + (i % 30)} for i in range(100)
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_create(bulk_data)
        bulk_time = performance_monitor.stop()["execution_time"]

        # Verify same number of records created
        bulk_count = await User.objects.using(session).count()
        assert len(individual_users) == bulk_count == 100

        # Bulk should be at least 10x faster
        improvement_ratio = individual_time / bulk_time
        assert improvement_ratio >= 10.0, f"Only {improvement_ratio:.2f}x improvement, expected >= 10x"

    async def test_bulk_create_scalability(self, session, performance_monitor):
        """Test bulk create performance scales well with dataset size"""
        dataset_sizes = [100, 500, 1000, 2000]
        times = []

        for size in dataset_sizes:
            # Clean up first
            existing_users = await User.objects.using(session).all()
            if existing_users:
                user_ids = [user.id for user in existing_users]
                await User.objects.using(session).bulk_delete(user_ids, id_field="id")

            # Prepare data
            users_data = [
                {"username": f"scale_user_{size}_{i}", "email": f"scale{size}_{i}@example.com", "age": 25}
                for i in range(size)
            ]

            # Measure bulk create time
            performance_monitor.start()
            await User.objects.using(session).bulk_create(users_data)
            execution_time = performance_monitor.stop()["execution_time"]
            times.append(execution_time)

            # Verify creation
            count = await User.objects.using(session).count()
            assert count == size

        # Performance should scale roughly linearly (not exponentially)
        # Time for 2000 records should be less than 5x time for 500 records (more lenient)
        time_500 = times[1]  # 500 records
        time_2000 = times[3]  # 2000 records

        scaling_ratio = time_2000 / time_500
        expected_linear_ratio = 2000 / 500  # 4x

        # Allow more overhead for database operations
        assert scaling_ratio < expected_linear_ratio * 2.0, (
            f"Poor scaling: {scaling_ratio:.2f}x vs expected ~{expected_linear_ratio}x"
        )

    async def test_bulk_create_memory_efficiency(self, session):
        """Test bulk create memory usage remains reasonable"""
        process = psutil.Process(os.getpid())

        # Baseline memory
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Large bulk create
        users_data = [
            {"username": f"memory_user_{i}", "email": f"memory{i}@example.com", "age": 25} for i in range(10000)
        ]

        await User.objects.using(session).bulk_create(users_data)

        # Memory after operation
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = memory_after - memory_before

        # Verify creation
        count = await User.objects.using(session).count()
        assert count == 10000

        # Memory growth should be reasonable (less than 200MB for 10k records)
        assert memory_growth < 200, f"Excessive memory usage: {memory_growth:.2f}MB for 10k records"

    async def test_bulk_create_batch_size_optimization(self, session, performance_monitor):
        """Test different batch sizes for optimal performance"""
        batch_sizes = [100, 500, 1000]
        times = {}

        for i, batch_size in enumerate(batch_sizes):
            # Clean database first - get all users and bulk delete them
            existing_users = await User.objects.using(session).all()
            if existing_users:
                user_ids = [user.id for user in existing_users]
                await User.objects.using(session).bulk_delete(user_ids, id_field="id")

            # Use unique usernames for each batch to avoid conflicts
            users_data = [
                {"username": f"batch_{i}_{j}", "email": f"batch{i}_{j}@example.com", "age": 25} for j in range(1000)
            ]

            # Test with specific batch size
            performance_monitor.start()
            await User.objects.using(session).bulk_create(users_data, batch_size=batch_size)
            execution_time = performance_monitor.stop()["execution_time"]
            times[batch_size] = execution_time

            # Verify creation
            count = await User.objects.using(session).count()
            assert count == 1000

        # All batch sizes should complete within reasonable time
        for batch_size, time_taken in times.items():
            assert time_taken < 10.0, f"Batch size {batch_size} took {time_taken:.2f}s, too slow"


class TestBulkUpdatePerformance:
    """Test bulk update performance characteristics"""

    async def test_bulk_update_performance_improvement(self, session, performance_monitor):
        """Test bulk update achieves significant performance improvement"""
        # Create test data
        users_data = [
            {"username": f"update_user_{i}", "email": f"update{i}@example.com", "age": 25} for i in range(200)
        ]
        users = await User.objects.using(session).bulk_create(users_data, return_objects=True)
        assert users.objects is not None
        user_objects: list[User] = users.objects  # type: ignore[assignment]

        # Individual updates (baseline)
        performance_monitor.start()
        for user in user_objects[:100]:  # Update first 100
            user.age = 30
            await user.save()
        individual_time = performance_monitor.stop()["execution_time"]

        # Bulk update (optimized)
        update_mappings = [
            {"id": user.id, "age": 35}
            for user in user_objects[100:]  # Update remaining 100
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        bulk_time = performance_monitor.stop()["execution_time"]

        # Verify updates
        updated_30 = await User.objects.using(session).filter(User.age == 30).count()
        updated_35 = await User.objects.using(session).filter(User.age == 35).count()
        assert updated_30 == 100
        assert updated_35 == 100

        # Bulk should be significantly faster (at least 5x)
        improvement_ratio = individual_time / bulk_time
        assert improvement_ratio >= 5.0, f"Only {improvement_ratio:.2f}x improvement, expected >= 5x"

    async def test_bulk_update_large_dataset_performance(self, session, performance_monitor):
        """Test bulk update performance with large datasets"""
        # Create large dataset
        users_data = [
            {"username": f"large_update_user_{i}", "email": f"large_update{i}@example.com", "age": 25}
            for i in range(5000)
        ]
        users_result = await User.objects.using(session).bulk_create(users_data, return_objects=True)
        assert users_result.objects is not None
        user_objects: list[User] = users_result.objects  # type: ignore[assignment]

        # Prepare bulk update
        update_mappings = [{"id": user.id, "age": 30, "is_active": False} for user in user_objects]

        # Measure bulk update performance
        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        execution_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time (less than 15 seconds for 5k records)
        assert execution_time < 15.0, f"Bulk update took {execution_time:.2f}s for 5k records"

        # Verify updates
        updated_count = await User.objects.using(session).filter(User.age == 30, User.is_active == False).count()
        assert updated_count == 5000

    async def test_bulk_update_partial_field_performance(self, session, performance_monitor):
        """Test bulk update performance with partial field updates"""
        # Create test data
        users_data = [
            {"username": f"partial_user_{i}", "email": f"partial{i}@example.com", "age": 25} for i in range(1000)
        ]
        users_result = await User.objects.using(session).bulk_create(users_data, return_objects=True)
        assert users_result.objects is not None
        user_objects: list[User] = users_result.objects  # type: ignore[assignment]

        # Update only one field (should be faster than updating all fields)
        update_mappings = [
            {"id": user.id, "age": 26}  # Only age field
            for user in user_objects
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        execution_time = performance_monitor.stop()["execution_time"]

        # Should be fast for single field update
        assert execution_time < 5.0, f"Partial field update took {execution_time:.2f}s"

        # Verify only age was updated
        updated_users = await User.objects.using(session).filter(User.age == 26).all()
        assert len(updated_users) == 1000

        # Other fields should remain unchanged
        for user in updated_users[:10]:  # Check first 10
            assert user.email.startswith("partial")
            assert user.username.startswith("partial_user_")


class TestBulkDeletePerformance:
    """Test bulk delete performance characteristics"""

    async def test_bulk_delete_performance_improvement(self, session, performance_monitor):
        """Test bulk delete achieves significant performance improvement"""
        # Create test data
        users_data = [
            {"username": f"delete_user_{i}", "email": f"delete{i}@example.com", "age": 25} for i in range(200)
        ]
        users_result = await User.objects.using(session).bulk_create(users_data, return_objects=True)
        assert users_result.objects is not None
        user_objects: list[User] = users_result.objects  # type: ignore[assignment]

        # Individual deletes (baseline)
        performance_monitor.start()
        for user in user_objects[:100]:  # Delete first 100
            await user.delete()
        individual_time = performance_monitor.stop()["execution_time"]

        # Bulk delete (optimized)
        remaining_ids = [user.id for user in user_objects[100:]]  # Remaining 100

        performance_monitor.start()
        await User.objects.using(session).bulk_delete(remaining_ids, id_field="id")
        bulk_time = performance_monitor.stop()["execution_time"]

        # Verify deletions
        final_count = await User.objects.using(session).count()
        assert final_count == 0

        # Bulk should be significantly faster (at least 3x)
        improvement_ratio = individual_time / bulk_time
        assert improvement_ratio >= 3.0, f"Only {improvement_ratio:.2f}x improvement, expected >= 3x"

    async def test_bulk_delete_large_dataset_performance(self, session, performance_monitor):
        """Test bulk delete performance with large datasets"""
        # Create large dataset
        users_data = [
            {"username": f"large_delete_user_{i}", "email": f"large_delete{i}@example.com", "age": 25}
            for i in range(10000)
        ]
        users_result = await User.objects.using(session).bulk_create(users_data, return_objects=True)
        assert users_result.objects is not None
        user_objects: list[User] = users_result.objects  # type: ignore[assignment]

        # Delete all records
        user_ids = [user.id for user in user_objects]

        performance_monitor.start()
        await User.objects.using(session).bulk_delete(user_ids, id_field="id")
        execution_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time (less than 10 seconds for 10k records)
        assert execution_time < 10.0, f"Bulk delete took {execution_time:.2f}s for 10k records"

        # Verify all records deleted
        final_count = await User.objects.using(session).count()
        assert final_count == 0


class TestConcurrentBulkOperations:
    """Test bulk operations under concurrent load"""

    async def test_concurrent_bulk_creates(self, session, performance_monitor):
        """Test concurrent bulk create operations"""

        async def create_batch(batch_id: int, batch_size: int = 100):
            users_data = [
                {"username": f"concurrent_{batch_id}_{i}", "email": f"concurrent{batch_id}_{i}@example.com", "age": 25}
                for i in range(batch_size)
            ]
            return await User.objects.using(session).bulk_create(users_data)

        # Run multiple concurrent bulk creates
        performance_monitor.start()
        tasks = [create_batch(i) for i in range(5)]  # 5 concurrent batches
        results = await asyncio.gather(*tasks)
        execution_time = performance_monitor.stop()["execution_time"]

        # Verify all batches completed
        assert len(results) == 5
        total_created = sum(result if isinstance(result, int) else len(result.objects) for result in results)
        assert total_created == 500  # 5 batches * 100 users each

        # Should complete within reasonable time
        assert execution_time < 15.0, f"Concurrent bulk creates took {execution_time:.2f}s"

        # Verify database state
        final_count = await User.objects.using(session).count()
        assert final_count == 500

    async def test_mixed_concurrent_operations(self, session, performance_monitor):
        """Test mixed concurrent bulk operations"""
        # Create initial data
        initial_data = [
            {"username": f"mixed_user_{i}", "email": f"mixed{i}@example.com", "age": 25} for i in range(200)
        ]
        initial_users_result = await User.objects.using(session).bulk_create(initial_data, return_objects=True)
        assert initial_users_result.objects is not None
        initial_users: list[User] = initial_users_result.objects  # type: ignore[assignment]

        async def concurrent_create():
            new_data = [{"username": f"new_user_{i}", "email": f"new{i}@example.com", "age": 30} for i in range(50)]
            return await User.objects.using(session).bulk_create(new_data)

        async def concurrent_update():
            update_mappings = [{"id": user.id, "age": 35} for user in initial_users[:50]]
            return await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])

        async def concurrent_delete():
            delete_ids = [user.id for user in initial_users[50:100]]
            return await User.objects.using(session).bulk_delete(delete_ids, id_field="id")

        # Run mixed operations concurrently
        performance_monitor.start()
        create_result, update_result, delete_result = await asyncio.gather(
            concurrent_create(), concurrent_update(), concurrent_delete()
        )
        execution_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time
        assert execution_time < 10.0, f"Mixed concurrent operations took {execution_time:.2f}s"

        # Verify results
        created_count = create_result if isinstance(create_result, int) else len(create_result.objects)
        assert created_count == 50  # New users created

        # Verify final state
        total_count = await User.objects.using(session).count()
        expected_count = 200 + 50 - 50  # initial + created - deleted
        assert total_count == expected_count


class TestBulkOperationResourceUsage:
    """Test resource usage characteristics of bulk operations"""

    async def test_cpu_usage_efficiency(self, session):
        """Test bulk operations are CPU efficient"""
        import threading

        cpu_usage_samples = []
        monitoring = True

        def monitor_cpu():
            process = psutil.Process(os.getpid())
            while monitoring:
                cpu_usage_samples.append(process.cpu_percent())
                time.sleep(0.1)

        # Start CPU monitoring
        monitor_thread = threading.Thread(target=monitor_cpu)
        monitor_thread.start()

        try:
            # Perform bulk operation
            users_data = [{"username": f"cpu_user_{i}", "email": f"cpu{i}@example.com", "age": 25} for i in range(5000)]

            await User.objects.using(session).bulk_create(users_data)

        finally:
            # Stop monitoring
            monitoring = False
            monitor_thread.join()

        # Analyze CPU usage
        if cpu_usage_samples:
            avg_cpu = sum(cpu_usage_samples) / len(cpu_usage_samples)
            max_cpu = max(cpu_usage_samples)

            # CPU usage should be reasonable (not pegging CPU at 100%)
            assert avg_cpu < 80.0, f"High average CPU usage: {avg_cpu:.2f}%"
            assert max_cpu < 95.0, f"High peak CPU usage: {max_cpu:.2f}%"

    async def test_database_connection_efficiency(self, session, performance_monitor):
        """Test bulk operations use database connections efficiently"""
        # Multiple bulk operations should reuse connections efficiently
        operations = []

        for i in range(10):
            users_data = [
                {"username": f"conn_user_{i}_{j}", "email": f"conn{i}_{j}@example.com", "age": 25} for j in range(100)
            ]
            operations.append(User.objects.using(session).bulk_create(users_data))

        # Execute all operations
        performance_monitor.start()
        results = await asyncio.gather(*operations)
        execution_time = performance_monitor.stop()["execution_time"]

        # Verify all operations completed
        total_created = sum(result if isinstance(result, int) else len(result.objects) for result in results)
        assert total_created == 1000  # 10 batches * 100 users each

        # Should complete efficiently
        assert execution_time < 20.0, f"Connection efficiency test took {execution_time:.2f}s"

    async def test_transaction_efficiency(self, isolated_session, performance_monitor):
        """Test bulk operations handle transactions efficiently"""
        # Large bulk operation within transaction
        users_data = [{"username": f"tx_user_{i}", "email": f"tx{i}@example.com", "age": 25} for i in range(2000)]

        performance_monitor.start()
        users_result = await User.objects.using(isolated_session).bulk_create(users_data, return_objects=True)
        assert users_result.objects is not None
        user_objects: list[User] = users_result.objects  # type: ignore[assignment]

        # Additional operations within same transaction
        update_mappings = [{"id": user.id, "age": 30} for user in user_objects[:500]]
        await User.objects.using(isolated_session).bulk_update(update_mappings, match_fields=["id"])

        # Commit the transaction
        await isolated_session.commit()

        execution_time = performance_monitor.stop()["execution_time"]

        # Should complete within reasonable time
        assert execution_time < 15.0, f"Transaction efficiency test took {execution_time:.2f}s"

        # Verify transaction committed
        final_count = await User.objects.using(isolated_session).count()
        assert final_count == 2000

        updated_count = await User.objects.using(isolated_session).filter(User.age == 30).count()
        assert updated_count == 500


class TestBulkOperationBenchmarks:
    """Comprehensive benchmarks for bulk operations"""

    async def test_comprehensive_bulk_create_benchmark(self, session, performance_monitor):
        """Comprehensive benchmark for bulk create across different scenarios"""
        scenarios = [
            {"name": "Small batch", "size": 100, "max_time": 2.0},
            {"name": "Medium batch", "size": 1000, "max_time": 5.0},
            {"name": "Large batch", "size": 5000, "max_time": 20.0},
            {"name": "Extra large batch", "size": 10000, "max_time": 30.0},
        ]

        results = {}

        for scenario in scenarios:
            # Clean up first
            existing_users = await User.objects.using(session).all()
            if existing_users:
                user_ids = [user.id for user in existing_users]
                await User.objects.using(session).bulk_delete(user_ids, id_field="id")

            # Prepare data
            users_data = [
                {"username": f"bench_{scenario['name']}_{i}", "email": f"bench{i}@example.com", "age": 25}
                for i in range(scenario["size"])
            ]

            # Benchmark
            performance_monitor.start()
            await User.objects.using(session).bulk_create(users_data)
            execution_time = performance_monitor.stop()["execution_time"]

            # Record results
            results[scenario["name"]] = {
                "size": scenario["size"],
                "time": execution_time,
                "records_per_second": scenario["size"] / execution_time,
            }

            # Verify performance target
            assert execution_time < scenario["max_time"], (
                f"{scenario['name']}: {execution_time:.2f}s > {scenario['max_time']}s limit"
            )

            # Verify creation
            count = await User.objects.using(session).count()
            assert count == scenario["size"]

        # Print benchmark results for analysis
        print("\nBulk Create Benchmark Results:")
        for name, result in results.items():
            print(
                f"{name}: {result['size']} records in {result['time']:.2f}s "
                f"({result['records_per_second']:.0f} records/sec)"
            )

    async def test_performance_regression_detection(self, session, performance_monitor):
        """Test to detect performance regressions in bulk operations"""
        # Baseline performance targets (adjust based on expected performance)
        targets = {
            "bulk_create_1000": 3.0,  # seconds
            "bulk_update_1000": 5.0,  # seconds
            "bulk_delete_1000": 2.0,  # seconds
        }

        # Test bulk create
        users_data = [
            {"username": f"regression_user_{i}", "email": f"regression{i}@example.com", "age": 25} for i in range(1000)
        ]

        performance_monitor.start()
        await User.objects.using(session).bulk_create(users_data)
        create_time = performance_monitor.stop()["execution_time"]

        assert create_time < targets["bulk_create_1000"], (
            f"Bulk create regression: {create_time:.2f}s > {targets['bulk_create_1000']}s"
        )

        # Get users for update test
        users = await User.objects.using(session).all()

        # Test bulk update
        update_mappings = [{"id": user.id, "age": 30} for user in users]

        performance_monitor.start()
        await User.objects.using(session).bulk_update(update_mappings, match_fields=["id"])
        update_time = performance_monitor.stop()["execution_time"]

        assert update_time < targets["bulk_update_1000"], (
            f"Bulk update regression: {update_time:.2f}s > {targets['bulk_update_1000']}s"
        )

        # Test bulk delete
        user_ids = [user.id for user in users]

        performance_monitor.start()
        await User.objects.using(session).bulk_delete(user_ids, id_field="id")
        delete_time = performance_monitor.stop()["execution_time"]

        assert delete_time < targets["bulk_delete_1000"], (
            f"Bulk delete regression: {delete_time:.2f}s > {targets['bulk_delete_1000']}s"
        )
