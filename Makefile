# SQLObjects Development Makefile

.PHONY: help test test-unit test-integration test-performance test-ci test-coverage clean lint format type-check

help:  ## Show this help message
	@echo "SQLObjects Development Commands:"
	@echo ""
	@echo "Basic Test Commands:"
	@grep -E '^test[^-]*:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Specific Test Commands:"
	@grep -E '^test-[^:]*:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Code Quality Commands:"
	@grep -E '^(lint|format|type-check|check|clean|install|pre-commit):.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make test-file FILE=tests/unit/test_model.py"
	@echo "  make test-class CLASS=tests/unit/test_model.py::TestUser"
	@echo "  make test-method METHOD=tests/unit/test_model.py::TestUser::test_create"
	@echo "  make test-keyword KEYWORD='create and user'"
	@echo "  python run_tests.py --test tests/unit/test_model.py::TestUser::test_create"

# Test commands
test:  ## Run all tests
	uv run python run_tests.py --all

test-unit:  ## Run unit tests only
	uv run python run_tests.py --unit

test-integration:  ## Run integration tests only
	uv run python run_tests.py --integration

test-performance:  ## Run performance tests only
	uv run python run_tests.py --performance

test-ci:  ## Run tests in CI mode with coverage
	uv run python run_tests.py --ci

test-coverage:  ## Run tests with coverage report
	uv run python run_tests.py --all --coverage

# Specific test commands
test-file:  ## Run specific test file (usage: make test-file FILE=tests/unit/test_model.py)
	@if [ -z "$(FILE)" ]; then echo "Usage: make test-file FILE=tests/unit/test_model.py"; exit 1; fi
	uv run python run_tests.py --test $(FILE)

test-class:  ## Run specific test class (usage: make test-class CLASS=tests/unit/test_model.py::TestUser)
	@if [ -z "$(CLASS)" ]; then echo "Usage: make test-class CLASS=tests/unit/test_model.py::TestUser"; exit 1; fi
	uv run python run_tests.py --test $(CLASS)

test-method:  ## Run specific test method (usage: make test-method METHOD=tests/unit/test_model.py::TestUser::test_create)
	@if [ -z "$(METHOD)" ]; then echo "Usage: make test-method METHOD=tests/unit/test_model.py::TestUser::test_create"; exit 1; fi
	uv run python run_tests.py --test $(METHOD)

test-keyword:  ## Run tests matching keyword (usage: make test-keyword KEYWORD="create and user")
	@if [ -z "$(KEYWORD)" ]; then echo "Usage: make test-keyword KEYWORD=\"create and user\""; exit 1; fi
	uv run python run_tests.py --keyword "$(KEYWORD)"

test-marker:  ## Run tests with specific marker (usage: make test-marker MARKER=slow)
	@if [ -z "$(MARKER)" ]; then echo "Usage: make test-marker MARKER=slow"; exit 1; fi
	uv run python run_tests.py --marker $(MARKER)

test-failed:  ## Run only tests that failed last time
	uv run python run_tests.py --lf

test-debug:  ## Run tests with debugger on failures
	uv run python run_tests.py --all --pdb

# Code quality commands
lint:  ## Run linting with ruff
	uv run ruff check sqlobjects tests

format:  ## Format code with ruff
	uv run ruff format sqlobjects tests

type-check:  ## Run type checking with pyright
	uv run pyright sqlobjects tests

# Development commands
clean:  ## Clean up build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

install:  ## Install development dependencies
	uv sync --group dev --group test

pre-commit:  ## Run pre-commit checks
	uv run pre-commit run --all-files

# Combined commands
check: lint type-check test-unit  ## Run all code quality checks and unit tests

# Quick test shortcuts
test-quick:  ## Run tests quickly (skip slow tests)
	uv run python run_tests.py --all --fast

test-pg:  ## Run all tests with PostgreSQL
	uv run python run_tests.py --all --db=postgresql

test-mysql:  ## Run all tests with MySQL
	uv run python run_tests.py --all --db=mysql
