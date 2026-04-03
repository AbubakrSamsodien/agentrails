"""Tests for CLI commands."""

import os

from click.testing import CliRunner

from agentrails.cli import main


def test_cli_help():
    """Test CLI --help works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "AgentRails" in result.output


def test_cli_version():
    """Test CLI --version works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0


def test_cli_all_commands_present():
    """Test all expected commands are in help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    expected_commands = [
        "run",
        "resume",
        "status",
        "list",
        "validate",
        "visualize",
        "logs",
        "export",
    ]
    for cmd in expected_commands:
        assert cmd in result.output


def test_validate_valid_workflow(fixtures_dir):
    """Test validate command with valid workflow."""
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(fixtures_dir / "smoke.yaml")])
    assert result.exit_code == 0
    assert "Workflow valid" in result.output
    assert "smoke_test" in result.output


def test_validate_invalid_workflow(tmp_path):
    """Test validate command with invalid workflow (missing name)."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("steps:\n  - id: test\n    type: shell\n    script: echo\n")

    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(invalid_yaml)])
    assert result.exit_code == 3
    assert "error" in result.output.lower() or "Validation" in result.output


def test_validate_missing_file():
    """Test validate command with missing file."""
    runner = CliRunner()
    result = runner.invoke(main, ["validate", "/nonexistent/file.yaml"])
    # Click returns 2 for usage errors
    assert result.exit_code in (2, 3)


def test_visualize_mermaid(fixtures_dir):
    """Test visualize command with mermaid format."""
    runner = CliRunner()
    result = runner.invoke(main, ["visualize", str(fixtures_dir / "smoke.yaml")])
    assert result.exit_code == 0
    assert "graph" in result.output


def test_visualize_ascii(fixtures_dir):
    """Test visualize command with ascii format."""
    runner = CliRunner()
    result = runner.invoke(
        main, ["visualize", str(fixtures_dir / "smoke.yaml"), "--format", "ascii"]
    )
    assert result.exit_code == 0
    assert "Workflow:" in result.output
    assert "hello" in result.output


def test_run_workflow_success(fixtures_dir, tmp_path):
    """Test run command with successful workflow."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", str(fixtures_dir / "smoke.yaml")],
        env={"AGENTRAILS_STATE_DIR": str(state_dir)},
    )
    assert result.exit_code == 0
    assert "completed" in result.output
    assert "hello" in result.output


def test_run_workflow_with_initial_state(fixtures_dir, tmp_path):
    """Test run command with initial state JSON."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            str(fixtures_dir / "smoke.yaml"),
            "--state",
            '{"test_key": "test_value"}',
        ],
        env={"AGENTRAILS_STATE_DIR": str(state_dir)},
    )
    assert result.exit_code == 0
    assert "completed" in result.output


def test_run_workflow_invalid_state_json(fixtures_dir, tmp_path):
    """Test run command with invalid JSON state."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            str(fixtures_dir / "smoke.yaml"),
            "--state",
            "invalid json",
        ],
        env={"AGENTRAILS_STATE_DIR": str(state_dir)},
    )
    assert result.exit_code == 2
    assert "Invalid JSON" in result.output


def test_list_no_runs(tmp_path):
    """Test list command with no runs."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["list"], env={"AGENTRAILS_STATE_DIR": str(state_dir)})
    # Should not error, just show empty or header
    assert result.exit_code == 0


def test_status_nonexistent_run(tmp_path):
    """Test status command with nonexistent run ID."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main, ["status", "nonexistent-run-id"], env={"AGENTRAILS_STATE_DIR": str(state_dir)}
    )
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_logs_nonexistent_run(tmp_path):
    """Test logs command with nonexistent run ID."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main, ["logs", "nonexistent-run-id"], env={"AGENTRAILS_STATE_DIR": str(state_dir)}
    )
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_export_nonexistent_run(tmp_path):
    """Test export command with nonexistent run ID."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main, ["export", "nonexistent-run-id"], env={"AGENTRAILS_STATE_DIR": str(state_dir)}
    )
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_resume_nonexistent_run(tmp_path):
    """Test resume command with nonexistent run ID."""
    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main, ["resume", "nonexistent-run-id"], env={"AGENTRAILS_STATE_DIR": str(state_dir)}
    )
    # Resume should error gracefully
    assert result.exit_code in (2, 5)


def test_cli_run_subprocess(tmp_path):
    """Test running agentrails run in a subprocess."""
    import subprocess
    import sys

    # Create a workflow file
    workflow_file = tmp_path / "cli_test.yaml"
    workflow_file.write_text("""
name: cli_subprocess_test
steps:
  - id: hello
    type: shell
    script: "echo hello_from_cli"
""")

    state_dir = tmp_path / ".agentrails"
    state_dir.mkdir()

    # Get the venv bin directory
    venv_bin = os.path.dirname(sys.executable)

    # Run via subprocess using the installed entry point
    result = subprocess.run(
        [os.path.join(venv_bin, "agentrails"), "run", str(workflow_file)],
        capture_output=True,
        text=True,
        env={**os.environ, "AGENTRAILS_STATE_DIR": str(state_dir)},
        cwd=tmp_path,
    )

    # Should complete successfully
    assert result.returncode == 0
    assert "completed" in result.stdout.lower()
    assert '"status":"completed"' in result.stdout
