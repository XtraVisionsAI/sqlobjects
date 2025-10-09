#!/usr/bin/env python3
"""
SQLObjects Test Runner

Unified test runner for SQLObjects with multi-database support and various test modes.

Usage Examples:
    python run_tests.py --all                              # Run all tests (SQLite)
    python run_tests.py --all --db=postgresql              # Run all tests (PostgreSQL)
    python run_tests.py --unit --db=postgresql             # Run unit tests (PostgreSQL)
    python run_tests.py --performance                      # Run performance tests
    python run_tests.py --test tests/unit/test_model.py    # Run specific test file
    python run_tests.py --test tests/unit/test_model.py::TestUser  # Run specific test class
    python run_tests.py --test tests/unit/test_model.py::TestUser::test_create  # Run specific test method
    python run_tests.py --keyword "create and user"        # Run tests matching keywords
    python run_tests.py --marker "slow"                    # Run tests with specific marker
    python run_tests.py --lf                               # Run only last failed tests
    python run_tests.py --pdb                              # Drop into debugger on failures
"""

import argparse
import asyncio
import subprocess
import sys

from tests.test_config import check_database_connection


def run_command(cmd, description=""):
    """Run a command and handle errors"""
    print(f"\n🚀 {description}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Failed: {description}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        return False
    else:
        print(f"✅ Success: {description}")
        if result.stdout:
            print(result.stdout)
        return True


def main():
    parser = argparse.ArgumentParser(description="SQLObjects Test Runner")

    # Test categories
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")

    # Specific test selection
    parser.add_argument("--test", "-t", help="Run specific test (file, class, or method)")
    parser.add_argument("--keyword", "-k", help="Run tests matching keyword expression")
    parser.add_argument("--marker", "-m", help="Run tests with specific marker")

    # Database selection
    parser.add_argument(
        "--db", choices=["sqlite", "postgresql", "mysql"], default="sqlite", help="Database type (default: sqlite)"
    )

    # Test options
    parser.add_argument("--coverage", action="store_true", help="Run with coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", type=int, help="Number of parallel workers")
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--ci", action="store_true", help="CI mode with coverage and strict settings")
    parser.add_argument("--pdb", action="store_true", help="Drop into debugger on failures")
    parser.add_argument("--lf", "--last-failed", action="store_true", help="Run only tests that failed last time")
    parser.add_argument("--ff", "--failed-first", action="store_true", help="Run failed tests first")

    args = parser.parse_args()

    # Default to --all if no specific test category or test is selected
    if not any([args.all, args.unit, args.integration, args.performance, args.test]):
        args.all = True

    # Check database availability
    print(f"🔍 Checking {args.db.upper()} database availability...")
    if not asyncio.run(check_database_connection(args.db)):
        print(f"❌ {args.db.upper()} database not available")
        if args.db != "sqlite":
            print("💡 Falling back to SQLite for testing")
            args.db = "sqlite"
        else:
            print("❌ No database available for testing")
            sys.exit(1)
    else:
        print(f"✅ {args.db.upper()} database is available")

    # Build pytest command
    cmd = ["uv", "run", "pytest"]

    # Add database selection
    cmd.extend(["--db", args.db])

    # Add test paths based on categories or specific test
    test_paths = []

    if args.test:
        # Specific test file, class, or method
        test_paths.append(args.test)
    elif args.all:
        test_paths.append("tests/")
    else:
        if args.unit:
            test_paths.append("tests/unit/")
        if args.integration:
            test_paths.append("tests/integration/")
        if args.performance:
            test_paths.append("tests/performance/")

    cmd.extend(test_paths)

    # Add options
    if args.coverage or args.ci:
        cmd.extend(["--cov=sqlobjects", "--cov-report=term-missing"])
        if args.ci:
            cmd.extend(["--cov-report=xml", "--cov-fail-under=80"])

    if args.verbose:
        cmd.append("-v")

    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])

    if args.keyword:
        cmd.extend(["-k", args.keyword])

    if args.marker:
        cmd.extend(["-m", args.marker])

    if args.fast:
        cmd.extend(["-m", "not slow"])

    if args.pdb:
        cmd.append("--pdb")

    if args.lf:
        cmd.append("--lf")

    if args.ff:
        cmd.append("--ff")

    if args.ci:
        cmd.extend(["--strict-markers", "--tb=short"])

    # Run the tests
    success = run_command(cmd, f"Running SQLObjects tests with {args.db.upper()}")

    if success:
        print(f"\n🎉 All tests passed with {args.db.upper()} database!")

        # Show database-specific tips
        if args.db == "postgresql":
            print("\n💡 PostgreSQL Testing Tips:")
            print("   - Ensure PostgreSQL server is running")
            print("   - Database 'tests' should exist")
            print("   - User 'test' should have CREATE/DROP privileges")
        elif args.db == "mysql":
            print("\n💡 MySQL Testing Tips:")
            print("   - Ensure MySQL server is running")
            print("   - Database 'tests' should exist")
            print("   - User 'test' should have CREATE/DROP privileges")
    else:
        print(f"\n❌ Tests failed with {args.db.upper()} database")
        sys.exit(1)


if __name__ == "__main__":
    main()
