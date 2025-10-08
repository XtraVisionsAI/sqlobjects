# SQLObjects Development Makefile

.PHONY: help test test-unit test-integration test-performance test-quick test-ci test-coverage clean lint format type-check

help:  ## Show this help message
	@echo "SQLObjects Development Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Test commands
test:  ## Run all tests
	uv run python run_tests.py --all

test-unit:  ## Run unit tests only
	uv run python run_tests.py --unit

test-integration:  ## Run integration tests only
	uv run python run_tests.py --integration

test-performance:  ## Run performance tests only
	uv run python run_tests.py --performance

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
check: lint type-check test-quick  ## Run all code quality checks and quick tests
