# SQLObjects Testing Guide

This guide explains how to run tests in the SQLObjects project with the enhanced test runner.

## Quick Start

```bash
# Run all tests
make test

# Run specific test categories
make test-unit
make test-integration
make test-performance

# Run specific test file
make test-file FILE=tests/unit/test_model.py

# Run specific test class
make test-class CLASS=tests/unit/test_model.py::TestUser

# Run specific test method
make test-method METHOD=tests/unit/test_model.py::TestUser::test_create
```

## Test Runner Options

### Basic Categories

```bash
python run_tests.py --all              # Run all tests
python run_tests.py --unit             # Unit tests only
python run_tests.py --integration      # Integration tests only
python run_tests.py --performance      # Performance tests only
```

### Specific Test Selection

```bash
# Run specific test file
python run_tests.py --test tests/unit/test_model.py

# Run specific test class
python run_tests.py --test tests/unit/test_model.py::TestUser

# Run specific test method
python run_tests.py --test tests/unit/test_model.py::TestUser::test_create
```

### Keyword and Marker Selection

```bash
# Run tests matching keywords
python run_tests.py --keyword "create and user"
python run_tests.py -k "model"

# Run tests with specific markers
python run_tests.py --marker slow
python run_tests.py -m "not slow"

# Skip slow tests
python run_tests.py --all --fast
```

### Database Selection

```bash
# Default SQLite
python run_tests.py --all

# PostgreSQL (requires setup)
python run_tests.py --all --db=postgresql

# MySQL (requires setup)
python run_tests.py --all --db=mysql
```

### Debug and Development

```bash
# Drop into debugger on failures
python run_tests.py --test tests/unit/test_model.py --pdb

# Run only tests that failed last time
python run_tests.py --lf

# Run failed tests first, then others
python run_tests.py --ff

# Verbose output
python run_tests.py --all --verbose
```

### Coverage and CI

```bash
# Run with coverage report
python run_tests.py --all --coverage

# CI mode (coverage + strict settings)
python run_tests.py --ci
```

## Makefile Shortcuts

### Basic Commands

```bash
make test                    # Run all tests
make test-unit              # Unit tests only
make test-integration       # Integration tests only
make test-performance       # Performance tests only
make test-coverage          # All tests with coverage
make test-ci               # CI mode
```

### Specific Test Commands

```bash
# Run specific test file
make test-file FILE=tests/unit/test_model.py

# Run specific test class
make test-class CLASS=tests/unit/test_model.py::TestUser

# Run specific test method
make test-method METHOD=tests/unit/test_model.py::TestUser::test_create

# Run tests matching keyword
make test-keyword KEYWORD="create and user"

# Run tests with marker
make test-marker MARKER=slow

# Run only failed tests
make test-failed

# Run with debugger
make test-debug
```

### Quick Shortcuts

```bash
make test-quick             # Skip slow tests
make test-pg               # Run with PostgreSQL
make test-mysql            # Run with MySQL
```

## Database Setup for Testing

### SQLite (Default)
No setup required - uses in-memory database.

### PostgreSQL
```bash
# Install dependencies
pip install asyncpg

# Set environment variable (optional)
export POSTGRESQL_TEST_URL="postgresql+asyncpg://test:test@localhost/tests"

# Create test database and user
createdb tests
createuser test --password  # password: test
```

### MySQL
```bash
# Install dependencies
pip install asyncmy

# Set environment variable (optional)
export MYSQL_TEST_URL="mysql+asyncmy://test:test@localhost/tests"

# Create test database and user
mysql -u root -p
CREATE DATABASE tests;
CREATE USER 'test'@'localhost' IDENTIFIED BY 'test';
GRANT ALL PRIVILEGES ON tests.* TO 'test'@'localhost';
```

## Test Structure

```
tests/
├── unit/                   # Fast, isolated unit tests
├── integration/            # Component interaction tests
├── performance/            # Performance and benchmark tests
├── conftest.py            # Shared fixtures and configuration
└── README.md              # Testing documentation
```

## Common Test Patterns

### Run Tests for Specific Feature

```bash
# All model-related tests
python run_tests.py -k "model"

# All query-related tests
python run_tests.py -k "query"

# All relationship tests
python run_tests.py -k "relationship"
```

### Debug Failing Tests

```bash
# Run only failed tests with debugger
python run_tests.py --lf --pdb

# Run specific failing test with verbose output
python run_tests.py --test tests/unit/test_model.py::TestUser::test_create -v --pdb
```

### Performance Testing

```bash
# Run performance tests only
make test-performance

# Run performance tests with specific database
python run_tests.py --performance --db=postgresql

# Skip slow tests for quick feedback
make test-quick
```

## Examples

### Development Workflow

```bash
# 1. Run quick tests during development
make test-quick

# 2. Run specific test you're working on
make test-method METHOD=tests/unit/test_model.py::TestUser::test_create

# 3. Run all related tests
python run_tests.py -k "user and create"

# 4. Run full test suite before commit
make test

# 5. Run with different databases
make test-pg
```

### Debugging Issues

```bash
# 1. Run failing test with debugger
python run_tests.py --test tests/unit/test_model.py::TestUser::test_create --pdb

# 2. Run with verbose output
python run_tests.py --test tests/unit/test_model.py::TestUser::test_create -v

# 3. Run only failed tests
make test-failed
```

### CI/CD Integration

```bash
# Local CI simulation
make test-ci

# Test with all databases
python run_tests.py --ci --db=sqlite
python run_tests.py --ci --db=postgresql
python run_tests.py --ci --db=mysql
```

## Help and Documentation

```bash
# Show all available make commands
make help

# Show test runner options
python run_tests.py --help

# Show pytest options
uv run pytest --help
```