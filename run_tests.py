#!/usr/bin/env python3
"""
SQLObjects Unified Test Runner

Comprehensive test runner for SQLObjects with different test categories and reporting.
Consolidates functionality from run_tests.py and run_deferred_tests.py.
"""

import argparse
import subprocess
import sys
import time


def run_command(cmd: list[str], description: str = "") -> bool:
    """Run a command and return success status"""
    print(f"\n{'=' * 60}")
    print(f"Running: {description or ' '.join(cmd)}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")

    start_time = time.time()
    try:
        _ = subprocess.run(cmd, check=True, capture_output=False)
        end_time = time.time()
        duration = end_time - start_time
        print(f"\n✅ SUCCESS: {description} (completed in {duration:.2f}s)")
        return True
    except subprocess.CalledProcessError as e:
        end_time = time.time()
        duration = end_time - start_time
        print(f"\n❌ FAILED: {description} (failed after {duration:.2f}s, exit code: {e.returncode})")
        return False


def main():
    parser = argparse.ArgumentParser(description="SQLObjects Unified Test Runner")

    # Test categories
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")

    # Specific test types
    parser.add_argument("--deferred", action="store_true", help="Run deferred field tests only")
    parser.add_argument("--bulk", action="store_true", help="Run bulk operation tests only")
    parser.add_argument("--relationships", action="store_true", help="Run relationship tests only")
    parser.add_argument("--signals", action="store_true", help="Run signal tests only")

    # Test execution options
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", "-n", type=int, help="Number of parallel workers")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark tests")
    parser.add_argument("--memory", action="store_true", help="Run memory tests")

    # Special modes
    parser.add_argument("--ci", action="store_true", help="Run in CI mode")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests")

    args = parser.parse_args()

    # Default to all tests if no specific category selected
    if not any(
        [
            args.unit,
            args.integration,
            args.performance,
            args.deferred,
            args.bulk,
            args.relationships,
            args.signals,
            args.benchmark,
            args.memory,
        ]
    ):
        args.all = True

    # Base pytest command
    base_cmd = ["uv", "run", "pytest"]

    # Add verbosity
    if args.verbose:
        base_cmd.append("-v")
    else:
        base_cmd.append("-q")

    # Add parallel execution
    if args.parallel:
        base_cmd.extend(["-n", str(args.parallel)])

    # Add coverage if requested
    if args.coverage:
        base_cmd.extend(["--cov=sqlobjects", "--cov-report=html", "--cov-report=term"])

    # Skip slow tests if requested
    if args.fast:
        base_cmd.extend(["-m", "not slow"])

    success_count = 0
    total_count = 0

    # Handle special modes first
    if args.ci:
        return run_ci_tests()
    elif args.quick:
        return run_quick_tests()

    # Run specific test categories
    if args.unit or args.all:
        total_count += 1
        cmd = base_cmd + ["tests/unit/"]
        if run_command(cmd, "Unit Tests"):
            success_count += 1

    if args.integration or args.all:
        total_count += 1
        cmd = base_cmd + ["tests/integration/"]
        if run_command(cmd, "Integration Tests"):
            success_count += 1

    if args.performance or args.all:
        total_count += 1
        cmd = base_cmd + ["tests/performance/"]
        if run_command(cmd, "Performance Tests"):
            success_count += 1

    # Run specific feature tests
    if args.deferred:
        total_count += 1
        cmd = base_cmd + [
            "tests/unit/test_deferred_proxies.py",
            "tests/integration/test_deferred_loading.py",
            "tests/performance/test_deferred_performance.py",
        ]
        if run_command(cmd, "Deferred Field Tests"):
            success_count += 1

    if args.bulk:
        total_count += 1
        cmd = base_cmd + [
            "tests/integration/test_bulk_operations.py",
            "tests/integration/test_bulk_return_values.py",
            "tests/integration/test_bulk_transaction_control.py",
            "tests/performance/test_bulk_perf.py",
        ]
        if run_command(cmd, "Bulk Operation Tests"):
            success_count += 1

    if args.relationships:
        total_count += 1
        cmd = base_cmd + ["tests/unit/test_relationship_validation.py", "tests/integration/test_relationships.py"]
        if run_command(cmd, "Relationship Tests"):
            success_count += 1

    if args.signals:
        total_count += 1
        cmd = base_cmd + ["tests/integration/test_signals.py"]
        if run_command(cmd, "Signal Tests"):
            success_count += 1

    if args.benchmark:
        total_count += 1
        cmd = base_cmd + ["tests/performance/", "--benchmark-only"]
        if run_command(cmd, "Benchmark Tests"):
            success_count += 1

    if args.memory:
        total_count += 1
        cmd = base_cmd + ["tests/performance/test_memory_usage.py"]
        if run_command(cmd, "Memory Tests"):
            success_count += 1

    # Summary
    print(f"\n{'=' * 60}")
    print("TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"Passed: {success_count}/{total_count}")

    if success_count == total_count:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"💥 {total_count - success_count} test suite(s) failed")
        return 1


def run_quick_tests() -> int:
    """Run quick smoke tests"""
    print("SQLObjects Quick Test Suite")
    print("=" * 50)

    tests = [
        (["uv", "run", "pytest", "tests/unit/test_model_basic.py", "-v"], "Model Basic Tests"),
        (["uv", "run", "pytest", "tests/unit/test_fields.py", "-v"], "Field System Tests"),
        (["uv", "run", "pytest", "tests/unit/test_queries.py", "-v"], "Query Building Tests"),
    ]

    success_count = 0
    for cmd, description in tests:
        if run_command(cmd, description):
            success_count += 1

    print(f"\nQuick Tests: {success_count}/{len(tests)} passed")
    return 0 if success_count == len(tests) else 1


def run_ci_tests() -> int:
    """Run tests suitable for CI environment"""
    print("SQLObjects CI Test Suite")
    print("=" * 50)

    cmd = [
        "uv",
        "run",
        "pytest",
        "tests/",
        "--cov=sqlobjects",
        "--cov-report=xml",
        "--cov-report=term",
        "--tb=short",
        "-v",
    ]

    return 0 if run_command(cmd, "CI Test Suite") else 1


if __name__ == "__main__":
    sys.exit(main())
