"""Tests for ShellStep execution."""

import asyncio

import pytest

from agentrails.state import WorkflowState
from agentrails.steps.base import ExecutionContext
from agentrails.steps.shell_step import ShellStep


@pytest.fixture
def mock_context(tmp_path, caplog):
    """Create a mock ExecutionContext for testing."""
    import logging

    logger = logging.getLogger("test")
    logger.addHandler(caplog.handler) if hasattr(caplog, "handler") else None

    return ExecutionContext(
        workflow_id="test-wf",
        run_id="test-run",
        working_directory=tmp_path,
        logger=logger,
        session_manager=None,
        state_store=None,
    )


class TestShellStepExecution:
    """Tests for ShellStep execute method."""

    def test_shell_step_execute_success(self, mock_context):
        """Test successful shell command execution."""
        step = ShellStep(id="test", script="echo hello")

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.step_id == "test"
        assert result.status == "success"
        assert result.outputs["return_code"] == 0
        assert result.outputs["stdout"].strip() == "hello"
        assert result.error is None

    def test_shell_step_execute_failure(self, mock_context):
        """Test failed shell command execution."""
        step = ShellStep(id="test", script="exit 1")

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.step_id == "test"
        assert result.status == "failed"
        assert result.outputs["return_code"] == 1
        assert "Exit code 1" in result.error

    def test_shell_step_timeout(self, mock_context):
        """Test shell command timeout."""
        step = ShellStep(id="test", script="sleep 10", timeout=1)

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.step_id == "test"
        assert result.status == "timeout"
        assert "Timeout after 1s" in result.error

    def test_shell_step_template_rendering(self, mock_context):
        """Test that template expressions in script are rendered."""
        step = ShellStep(id="test", script="echo {{state.greeting}}")
        state = WorkflowState({"greeting": "world"})

        async def run():
            result = await step.execute(state, mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert result.outputs["stdout"].strip() == "world"

    def test_shell_step_working_dir(self, mock_context, tmp_path):
        """Test that shell command runs in correct working directory."""
        # Create a file in a subdirectory
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        test_file = work_dir / "test.txt"
        test_file.write_text("test content")

        step = ShellStep(id="test", script="cat test.txt", working_dir=str(work_dir))

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert result.outputs["stdout"].strip() == "test content"

    def test_shell_step_env_vars(self, mock_context):
        """Test that custom environment variables are passed."""
        step = ShellStep(id="test", script="echo $TEST_VAR", env={"TEST_VAR": "custom_value"})

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert result.outputs["stdout"].strip() == "custom_value"

    def test_shell_step_template_in_working_dir(self, mock_context, tmp_path):
        """Test template rendering in working_dir field."""
        # Create a directory with a dynamic name
        work_dir = tmp_path / "dynamic_work"
        work_dir.mkdir()
        test_file = work_dir / "file.txt"
        test_file.write_text("dynamic content")

        step = ShellStep(id="test", script="cat file.txt", working_dir="{{state.work_dir}}")
        state = WorkflowState({"work_dir": str(work_dir)})

        async def run():
            result = await step.execute(state, mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert result.outputs["stdout"].strip() == "dynamic content"

    def test_shell_step_captures_stderr(self, mock_context):
        """Test that stderr is captured separately."""
        step = ShellStep(id="test", script="echo error >&2 && echo ok")

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert "error" in result.outputs["stderr"]
        assert "ok" in result.outputs["stdout"]

    def test_shell_step_output_format_json(self, mock_context):
        """Test that JSON output is preserved in raw_output."""
        step = ShellStep(id="test", script='echo \'{"key": "value"}\'', output_format="json")

        async def run():
            result = await step.execute(WorkflowState({}), mock_context)
            return result

        result = asyncio.run(run())

        assert result.status == "success"
        assert result.raw_output.strip() == '{"key": "value"}'
        # Note: actual JSON parsing would happen in the engine, not the step
