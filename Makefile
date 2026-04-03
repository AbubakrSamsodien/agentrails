.PHONY: install install-dev lint format test test-all test-cov build clean

# Install the package in the current environment
install:
	uv pip install .

# Install with all dev dependencies (editable)
install-dev:
	uv pip install -e ".[dev]"

# Run all linters: ruff, pylint, vulture
lint:
	uv run ruff check agentrails/ tests/
	uv run pylint agentrails/
	@echo "Running vulture (unused Click params expected)..."
	-uv run vulture agentrails/ 2>&1 | grep -v "unused variable 'storage'\|unused variable 'db_url'\|unused variable 'interactive'" || true

# Auto-format code with ruff
format:
	uv run ruff format agentrails/ tests/
	uv run ruff check --fix agentrails/ tests/

# Run tests (unit only, excludes integration)
test:
	uv run pytest -m "not integration"

# Run all tests including integration
test-all:
	uv run pytest

# Run tests with coverage report
test-cov:
	uv run pytest --cov=agentrails --cov-report=term-missing --cov-report=html

# Build distributable package (wheel + sdist)
build:
	uv build

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
