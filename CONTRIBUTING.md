# Contributing to AgentRails

Thank you for contributing to AgentRails! This document covers development setup, code style, and the contribution process.

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/agentrails.git
cd agentrails

# Create virtual environment and install with dev dependencies
uv venv
source .venv/bin/activate
make install-dev

# Verify setup
make test
make lint
```

## Code Style

AgentRails uses the following tools for code quality:

| Tool | Purpose | Config |
|------|---------|--------|
| **ruff** | Linting and formatting | `pyproject.toml` |
| **pylint** | Additional linting | `pyproject.toml` |
| **vulture** | Dead code detection | `pyproject.toml` |

### Style Guidelines

- **Line length**: 100 characters
- **Quotes**: Double quotes
- **Indentation**: 4 spaces
- **Type hints**: Required for all function signatures
- **Docstrings**: Required for all public classes and functions

### Running Linters

```bash
# Format code
make format

# Run all linters
make lint
```

## Testing

### Running Tests

```bash
# Unit tests only (excludes integration tests)
make test

# All tests including integration
make test-all

# With coverage report
make test-cov

# Run tests that require real Claude CLI (requires ANTHROPIC_API_KEY)
pytest -m realcli --run-real-cli
# Or set env var: RUN_REAL_CLI=1 pytest -m realcli
```

### Writing Tests

- Place tests in `tests/` directory mirroring the `agentrails/` structure
- Use pytest fixtures from `tests/conftest.py`
- Mark integration tests with `@pytest.mark.integration`
- Mark tests requiring real Claude CLI with `@pytest.mark.realcli` (skipped by default)
- Include test cases in task acceptance criteria

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_state.py         # Unit tests for state.py
├── test_dag.py           # Unit tests for dag.py
├── test_steps/           # Step type tests
│   ├── test_shell_step.py
│   └── ...
└── integration/          # End-to-end tests
    ├── test_smoke.py
    └── ...
```

## Commit Messages

Use the following format:

```
RAIL-XXX: Brief description

Optional longer description explaining the change.
```

Examples:
- `RAIL-001: Create package scaffold`
- `RAIL-010: Implement WorkflowState with immutable updates`

## Pull Request Process

1. **Branch from `main`**: Create a feature branch for your work
   ```bash
   git checkout main
   git pull
   git checkout -b feature/your-feature
   ```

2. **Make changes**: Implement your feature or fix

3. **Ensure CI passes**:
   ```bash
   make lint
   make test
   ```

4. **Commit**: Use the commit message format above

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature
   ```

6. **Review**: Wait for CI to pass and at least one approval

### PR Requirements

- [ ] All tests pass
- [ ] Linters pass (`make lint`)
- [ ] Commit messages follow the `RAIL-XXX` format
- [ ] Code follows existing style conventions
- [ ] New code includes tests

## Adding a New Step Type

To add a new step type:

1. **Create the step class** in `agentrails/steps/`:
   ```python
   from agentrails.steps.base import BaseStep, StepResult

   class MyStep(BaseStep):
       async def execute(self, state, context) -> StepResult:
           # Implementation
           pass
   ```

2. **Export from `agentrails/steps/__init__.py`**

3. **Add parser support** in `agentrails/dsl_parser.py`

4. **Write tests** in `tests/test_steps/test_my_step.py`

5. **Update documentation** with YAML examples

## Architecture Overview

Key components:

| Component | File | Purpose |
|-----------|------|---------|
| **BaseStep** | `steps/base.py` | Abstract base for all step types |
| **WorkflowState** | `state.py` | Immutable state passed between steps |
| **WorkflowRunner** | `engine.py` | DAG execution engine |
| **SessionManager** | `session_manager.py` | Claude CLI subprocess management |
| **StateStore** | `storage.py` | Abstract storage interface |
| **OutputParser** | `output.py` | JSON/TOML output parsing |

## Questions?

- Open a GitHub issue for bugs or feature requests
- Check existing issues before creating new ones
- Refer to the docs in `docs/` for project guidance
