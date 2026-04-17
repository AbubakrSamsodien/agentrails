# AgentRails

Deterministic AI workflow runtime for orchestrating agent and shell pipelines.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![CI](https://github.com/agentrails/agentrails/actions/workflows/ci.yml/badge.svg)](https://github.com/agentrails/agentrails/actions)

## What is AgentRails?

AgentRails is a workflow engine that orchestrates AI agents and shell commands in deterministic, reproducible pipelines. It provides:

- **YAML workflow definitions** with support for parallel execution, conditionals, and loops
- **Structured output parsing** (JSON/TOML) for reliable agent communication
- **System prompt control** at workflow and step level
- **Checkpointing and replay** for crash recovery and determinism
- **SQLite/PostgreSQL backends** for state persistence

## Why AgentRails?

Other AI orchestration tools exist, but AgentRails was built with a different philosophy: **determinism first**. Every workflow execution is checkpointed, every step output is structured, and every failure is recoverable. This means you can:

- **Resume after crashes** — pick up exactly where you left off, no re-work
- **Replay for debugging** — reproduce the exact same execution for troubleshooting
- **Chain agents reliably** — structured JSON/TOML output means downstream steps can depend on upstream results
- **Control agent behavior** — system prompts at workflow and step level, with file-based templates for complex prompts

AgentRails treats AI agents like any other component in a pipeline: testable, debuggable, and reproducible.

AgentRails is an independent open source project. It is not affiliated with, endorsed by, or sponsored by any model provider or coding-agent vendor. Users are responsible for complying with the terms of any tools and services they connect.

## Quick Start

### Installation

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install
uv venv
source .venv/bin/activate
make install-dev
```

### Run a Workflow

```bash
# Create a simple workflow
cat > workflow.yaml << 'EOF'
name: hello_world
steps:
  - id: greet
    type: shell
    script: "echo 'Hello from AgentRails!'"
EOF

# Run it
agentrails run workflow.yaml
```

## Development Setup

```bash
# Clone and setup
git clone https://github.com/agentrails/agentrails.git
cd agentrails
uv venv
source .venv/bin/activate
make install-dev

# Run tests
make test

# Run linters
make lint
```

## Project Structure

```
agentrails/
├── agentrails/          # Python package
│   ├── cli.py           # CLI entry point
│   ├── engine.py        # Workflow execution engine
│   ├── state.py         # Workflow state management
│   ├── dag.py           # DAG data structure
│   ├── dsl_parser.py    # YAML parser
│   ├── steps/           # Step type implementations
│   └── storage*.py      # Storage backends
├── tests/               # Test suite
├── examples/            # Example workflows
├── pyproject.toml       # Project configuration
├── Makefile             # Build/test commands
└── TASKPLAN.md          # Project roadmap
```

## Key Commands

| Command | Description |
|---------|-------------|
| `make install` | Install package |
| `make install-dev` | Install with dev dependencies |
| `make test` | Run unit tests |
| `make test-all` | Run all tests |
| `make lint` | Run linters |
| `make format` | Auto-format code |
| `make build` | Build wheel |

## CLI Reference

```bash
agentrails run <workflow.yaml>      # Run a workflow
agentrails resume <run_id>          # Resume from checkpoint
agentrails status <run_id>          # Show run status
agentrails list                     # List all runs
agentrails validate <workflow.yaml> # Validate YAML
agentrails visualize <workflow.yaml># Show DAG
agentrails logs <run_id>            # Show event log
```

## Example Workflow

```yaml
name: code_review
defaults:
  output_format: json
steps:
  - id: analyze
    type: agent
    prompt: "Analyze the codebase in {{state.project_dir}}"
    output_schema:
      type: object
      properties:
        issues: { type: array }
        suggestions: { type: array }

  - id: tests
    type: parallel_group
    depends_on: [analyze]
    branches:
      - id: unit
        type: shell
        script: "pytest tests/unit -q"
      - id: lint
        type: shell
        script: "ruff check ."

  - id: report
    type: agent
    depends_on: [analyze, tests]
    prompt: |
      Create a report based on:
      - Analysis: {{state.analyze.result}}
      - Test results: {{state.tests}}
```

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.
