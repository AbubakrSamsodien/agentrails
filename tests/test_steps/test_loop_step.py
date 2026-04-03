"""Tests for LoopStep class."""
# pylint: disable=unused-argument

import pytest

from agentrails.state import WorkflowState
from agentrails.steps.base import ExecutionContext
from agentrails.steps.loop_step import LoopStep
from agentrails.steps.shell_step import ShellStep


@pytest.fixture
def sample_context(tmp_path):  # pylint: disable=unused-argument
    """Create a sample execution context."""
    from unittest.mock import AsyncMock, MagicMock

    from agentrails.storage_sqlite import SqliteStateStore

    store = SqliteStateStore(tmp_path / "state.db")
    session_manager = AsyncMock()
    logger = MagicMock()

    return ExecutionContext(
        workflow_id="wf_test",
        run_id="run_test",
        working_directory=tmp_path,
        logger=logger,
        session_manager=session_manager,
        state_store=store,
    )


async def test_loop_step_initialization():
    """Test LoopStep can be initialized."""
    body = [ShellStep(id="attempt", script="echo attempt")]
    step = LoopStep(id="test", body=body, until="{{state.test.latest.attempt.return_code == 0}}")

    assert step.id == "test"
    assert step.type == "loop"
    assert len(step.body) == 1
    assert step.max_iterations == 5
    assert step.until == "{{state.test.latest.attempt.return_code == 0}}"


async def test_loop_step_single_iteration_success(sample_context, tmp_path):
    """Test loop that succeeds on first iteration."""
    body = [ShellStep(id="check", script="echo success")]
    step = LoopStep(
        id="loop",
        body=body,
        until="{{state.loop.latest.check.return_code == 0}}",
        max_iterations=3,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "success"
    assert result.error is None
    assert result.outputs["iteration_count"] == 1
    assert result.outputs["latest"]["check"]["return_code"] == 0


async def test_loop_step_condition_based_on_iteration_count(sample_context):
    """Test loop that exits after N iterations based on count."""
    body = [ShellStep(id="count", script="echo iteration")]
    step = LoopStep(
        id="counter",
        body=body,
        until="{{state.counter.iteration_count >= 3}}",
        max_iterations=5,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "success"
    assert result.outputs["iteration_count"] == 3


async def test_loop_step_max_iterations_exceeded(sample_context):
    """Test loop that fails when max iterations reached without condition met."""
    body = [ShellStep(id="always_fail", script="exit 1")]
    step = LoopStep(
        id="failing_loop",
        body=body,
        until="{{state.failing_loop.latest.always_fail.return_code == 0}}",
        max_iterations=2,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "failed"
    # Error contains both the body step failure and max iterations info
    assert result.error is not None
    assert result.outputs["iteration_count"] == 2


async def test_loop_step_state_updated_between_iterations(sample_context):
    """Test that state is properly updated with iteration results."""
    body = [ShellStep(id="step", script="echo data")]
    step = LoopStep(
        id="myloop",
        body=body,
        until="{{state.myloop.iteration_count >= 2}}",
        max_iterations=3,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    # Outputs should contain the loop results
    assert result.outputs["latest"] is not None
    assert result.outputs["iterations"] is not None
    assert len(result.outputs["iterations"]) == 2
    assert result.outputs["iteration_count"] == 2


async def test_loop_step_retries_on_body_failure(sample_context):
    """Test that loop retries when body step fails."""
    # Always failing step - tests that loop retries up to max
    body = [ShellStep(id="flaky", script="exit 1")]
    step = LoopStep(
        id="retry",
        body=body,
        until="{{state.retry.latest.flaky.return_code == 0}}",
        max_iterations=3,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    # Should have tried all 3 iterations
    assert result.outputs["iteration_count"] == 3
    # Status is failed because condition never met
    assert result.status == "failed"


async def test_loop_step_serialization_roundtrip():
    """Test LoopStep serialize/deserialize roundtrip."""
    body = [ShellStep(id="inner", script="echo test")]
    original = LoopStep(
        id="loop",
        body=body,
        until="{{state.loop.latest.inner.return_code == 0}}",
        max_iterations=10,
        max_retries=2,
        output_format="json",
    )

    data = original.serialize()
    restored = LoopStep.deserialize(data)

    assert restored.id == original.id
    assert restored.until == original.until
    assert restored.max_iterations == original.max_iterations
    assert len(restored.body) == 1
    assert restored.body[0].id == "inner"
    assert restored.max_retries == 2
    assert restored.output_format == original.output_format


async def test_loop_step_condition_undefined_variable(sample_context):
    """Test loop handles undefined variables in condition gracefully."""
    body = [ShellStep(id="step", script="echo test")]
    # Condition references a non-existent path
    step = LoopStep(
        id="loop",
        body=body,
        until="{{state.loop.nonexistent.path == True}}",
        max_iterations=2,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    # Should handle the error and continue, eventually hitting max iterations
    assert result.status == "failed"
    assert "Could not evaluate" in result.error or "Max iterations" in result.error


async def test_loop_step_multiple_body_steps(sample_context):
    """Test loop with multiple body steps per iteration."""
    body = [
        ShellStep(id="setup", script="echo setup"),
        ShellStep(id="run", script="echo running"),
        ShellStep(id="cleanup", script="echo done"),
    ]
    step = LoopStep(
        id="pipeline",
        body=body,
        until="{{state.pipeline.iteration_count >= 2}}",
        max_iterations=3,
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "success"
    assert result.outputs["iteration_count"] == 2
    # Each iteration should have all 3 steps
    assert "setup" in result.outputs["latest"]
    assert "run" in result.outputs["latest"]
    assert "cleanup" in result.outputs["latest"]
