"""Tests for BaseStep and related classes."""

from agentrails.steps.base import ExecutionContext, StepResult


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_step_result_creation(self):
        """Test StepResult can be created."""
        result = StepResult(
            step_id="test",
            status="success",
            outputs={"key": "value"},
            raw_output="raw text",
            duration_seconds=1.5,
        )

        assert result.step_id == "test"
        assert result.status == "success"
        assert result.outputs == {"key": "value"}
        assert result.raw_output == "raw text"
        assert result.duration_seconds == 1.5
        assert result.error is None

    def test_step_result_with_error(self):
        """Test StepResult with error field."""
        result = StepResult(
            step_id="test",
            status="failed",
            outputs={},
            raw_output="",
            duration_seconds=0,
            error="Something went wrong",
        )

        assert result.status == "failed"
        assert result.error == "Something went wrong"


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_execution_context_creation(self, tmp_path):
        """Test ExecutionContext can be created."""
        import logging

        logger = logging.getLogger("test")
        context = ExecutionContext(
            workflow_id="wf-123",
            run_id="run-456",
            working_directory=tmp_path,
            logger=logger,
            session_manager=None,
            state_store=None,
        )

        assert context.workflow_id == "wf-123"
        assert context.run_id == "run-456"
        assert context.working_directory == tmp_path
        assert context.logger == logger


class TestBaseStep:
    """Tests for BaseStep abstract class."""

    def test_base_step_defaults(self):
        """Test BaseStep default values."""
        from agentrails.steps.shell_step import ShellStep

        step = ShellStep(id="test", script="echo hello")

        assert step.id == "test"
        assert step.type == "shell"
        assert step.depends_on == []
        assert step.outputs == {}
        assert step.condition is None
        assert step.output_format == "text"
        assert step.output_schema is None
        assert step.max_retries == 0
        assert step.timeout_seconds is None

    def test_base_step_custom_values(self):
        """Test BaseStep with custom values."""
        from agentrails.steps.shell_step import ShellStep

        schema = {"type": "object"}
        step = ShellStep(
            id="test",
            script="echo hello",
            depends_on=["prev"],
            outputs={"stdout": "string"},
            condition="{{state.x > 0}}",
            output_format="json",
            output_schema=schema,
            max_retries=3,
            timeout_seconds=60,
        )

        assert step.depends_on == ["prev"]
        assert step.outputs == {"stdout": "string"}
        assert step.condition == "{{state.x > 0}}"
        assert step.output_format == "json"
        assert step.output_schema == schema
        assert step.max_retries == 3
        assert step.timeout_seconds == 60


class TestStepSerializeRoundtrip:
    """Tests for step serialize/deserialize roundtrip.

    Note: Only ShellStep has a complete deserialize implementation.
    Other step types will need deserialize implementations as needed.
    """

    def test_shell_step_serialize_roundtrip(self):
        """Test ShellStep serialize and deserialize preserves all fields."""
        from agentrails.steps.shell_step import ShellStep

        original = ShellStep(
            id="test",
            script="pytest -q",
            working_dir="{{state.project_dir}}",
            env={"PYTHONPATH": "./src"},
            timeout=300,
            depends_on=["setup"],
            output_format="json",
            max_retries=2,
            timeout_seconds=60,
        )

        data = original.serialize()
        restored = ShellStep.deserialize(data)

        assert restored.id == original.id
        assert restored.script == original.script
        assert restored.working_dir == original.working_dir
        assert restored.env == original.env
        assert restored.timeout == original.timeout
        assert restored.depends_on == original.depends_on
        assert restored.output_format == original.output_format
        assert restored.max_retries == original.max_retries
        assert restored.timeout_seconds == original.timeout_seconds

    def test_shell_step_serialize_base_fields(self):
        """Test that BaseStep fields are included in ShellStep serialization."""
        from agentrails.steps.shell_step import ShellStep

        step = ShellStep(
            id="test",
            script="echo hello",
            depends_on=["prev"],
            output_format="json",
            max_retries=3,
        )

        data = step.serialize()

        assert data["id"] == "test"
        assert data["type"] == "shell"
        assert data["depends_on"] == ["prev"]
        assert data["output_format"] == "json"
        assert data["max_retries"] == 3
        assert data["script"] == "echo hello"
