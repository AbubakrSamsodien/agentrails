"""Shared pytest fixtures and configuration for AgentRails tests."""

import os
from pathlib import Path

import pytest

from agentrails.state import WorkflowState


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for SQLite state files.

    Auto-cleanup is handled by pytest's tmp_path fixture.

    Returns:
        Path to temporary directory
    """
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def sample_state() -> WorkflowState:
    """Create a pre-populated WorkflowState instance.

    Returns:
        WorkflowState with sample data
    """
    return WorkflowState(
        {
            "plan": {
                "title": "Sample Plan",
                "steps": ["step1", "step2"],
            },
            "tests": {
                "unit": {
                    "status": "pass",
                    "count": 42,
                },
                "integration": {
                    "status": "pending",
                },
            },
            "count": 5,
            "status": "running",
        }
    )


@pytest.fixture
def mock_claude_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a mock Claude CLI script for testing.

    The mock script accepts the same flags as the real Claude CLI
    and returns canned JSON responses.

    Environment variables:
        MOCK_CLAUDE_RESPONSE: JSON string to return (default: {"result": "mocked"})
        MOCK_CLAUDE_EXIT_CODE: Exit code (default: 0)
        MOCK_CLAUDE_ARGS_FILE: If set, write received args to this file for assertion
        MOCK_CLAUDE_VERSION: Version string to return for --version (default: "Claude Code 1.0.0")

    Args:
        tmp_path: Pytest temporary directory
        monkeypatch: Pytest monkeypatch fixture

    Returns:
        Path to mock Claude CLI script
    """
    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
import os
import json

args = sys.argv[1:]

# Handle --version flag
if "--version" in args:
    version = os.environ.get("MOCK_CLAUDE_VERSION", "Claude Code 1.0.0")
    print(version)
    sys.exit(0)

# Capture args if requested
args_file = os.environ.get("MOCK_CLAUDE_ARGS_FILE")
if args_file:
    with open(args_file, "w") as f:
        json.dump(args, f)

# Get response from env or use default
response = os.environ.get("MOCK_CLAUDE_RESPONSE", '{"result": "mocked"}')
exit_code = int(os.environ.get("MOCK_CLAUDE_EXIT_CODE", "0"))

print(response)
sys.exit(exit_code)
""")
    mock_script.chmod(0o755)

    # Add to PATH
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    return mock_script


@pytest.fixture
def fixtures_dir() -> Path:
    """Get the path to test fixtures directory.

    Returns:
        Path to tests/fixtures/
    """
    return Path(__file__).parent / "fixtures"
