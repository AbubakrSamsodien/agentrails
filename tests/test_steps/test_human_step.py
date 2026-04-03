"""Tests for HumanStep class."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentrails.state import WorkflowState
from agentrails.steps.base import ExecutionContext
from agentrails.steps.human_step import HumanInputTimeoutError, HumanStep
from agentrails.storage_sqlite import SqliteStateStore


@pytest.fixture
def sample_context(tmp_path):  # pylint: disable=unused-argument
    """Create a sample execution context."""
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


def test_human_step_initialization():
    """Test HumanStep can be initialized."""
    step = HumanStep(
        id="approve",
        message="Please approve: {{state.plan}}",
        input_schema={"type": "object", "properties": {"approved": {"type": "boolean"}}},
        timeout_seconds=600,
    )

    assert step.id == "approve"
    assert step.type == "human"
    assert step.message == "Please approve: {{state.plan}}"
    assert step.timeout == 600
    assert step.input_schema is not None


@pytest.mark.asyncio
async def test_human_step_serialization_roundtrip():
    """Test HumanStep serialize/deserialize roundtrip."""
    original = HumanStep(
        id="deploy_approval",
        message="Approve deployment?",
        input_schema={"type": "object", "required": ["approved"]},
        timeout_seconds=3600,
        max_retries=1,
    )

    data = original.serialize()
    restored = HumanStep.deserialize(data)

    assert restored.id == original.id
    assert restored.message == original.message
    assert restored.input_schema == original.input_schema
    assert restored.timeout == original.timeout
    assert restored.max_retries == original.max_retries


@pytest.mark.asyncio
async def test_human_step_valid_input(sample_context, monkeypatch):
    """Test human step with valid JSON input."""
    step = HumanStep(id="test", message="Enter value", timeout_seconds=10)

    # Mock stdin to return valid JSON
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        sys.stdin, "readline", lambda: '{"approved": true, "comments": "looks good"}\n'
    )

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "success"
    assert result.error is None
    assert result.outputs["input"]["approved"] is True
    assert result.outputs["input"]["comments"] == "looks good"


@pytest.mark.asyncio
async def test_human_step_empty_input(sample_context, monkeypatch):
    """Test human step with empty input."""
    step = HumanStep(id="test", message="Enter value", timeout_seconds=10)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "readline", lambda: "\n")

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "failed"
    assert "Empty input" in result.error


@pytest.mark.asyncio
async def test_human_step_invalid_json(sample_context, monkeypatch):
    """Test human step with invalid JSON."""
    step = HumanStep(id="test", message="Enter value", timeout_seconds=10)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "readline", lambda: "not valid json\n")

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "failed"
    assert "Invalid JSON" in result.error


@pytest.mark.asyncio
async def test_human_step_schema_validation_failure(sample_context, monkeypatch):
    """Test human step with input that fails schema validation."""
    step = HumanStep(
        id="test",
        message="Enter value",
        input_schema={
            "type": "object",
            "properties": {"approved": {"type": "boolean"}},
            "required": ["approved"],
        },
        timeout_seconds=10,
    )

    # Input missing required "approved" field
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "readline", lambda: '{"comments": "no approval"}\n')

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    assert result.status == "failed"
    assert "Schema validation failed" in result.error


@pytest.mark.asyncio
async def test_human_step_non_interactive_mode(sample_context, monkeypatch):
    """Test human step in non-interactive (piped) mode reads input."""
    step = HumanStep(id="test", message="Enter value", timeout_seconds=10)

    # Mock stdin as not a TTY but with input available
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "readline", lambda: '{"approved": true}\n')

    state = WorkflowState({})
    result = await step.execute(state, sample_context)

    # In non-interactive mode, should still read piped input successfully
    assert result.status == "success"
    assert result.outputs["input"]["approved"] is True


@pytest.mark.asyncio
async def test_human_step_template_rendering(sample_context, monkeypatch):
    """Test that message template is rendered with state."""
    step = HumanStep(
        id="test",
        message="Review: {{state.plan.title}} by {{state.plan.author}}",
        timeout_seconds=10,
    )

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "readline", lambda: '{"approved": true}\n')

    state = WorkflowState({"plan": {"title": "My Plan", "author": "Alice"}})
    result = await step.execute(state, sample_context)

    assert result.status == "success"
    assert "My Plan" in result.outputs["message"]
    assert "Alice" in result.outputs["message"]


@pytest.mark.asyncio
async def test_human_step_timeout(sample_context, monkeypatch):
    """Test human step timeout handling."""

    step = HumanStep(id="test", message="Enter value", timeout_seconds=1)

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    # Mock wait_for to simulate timeout
    with (
        patch("asyncio.wait_for", side_effect=TimeoutError()),
        pytest.raises(HumanInputTimeoutError),
    ):
        await step.execute(WorkflowState({}), sample_context)
