"""Tests for ConditionalStep class."""

import pytest

from agentrails.state import WorkflowState


def test_conditional_step_initialization():
    """Test ConditionalStep can be initialized."""
    from agentrails.steps.conditional_step import ConditionalStep

    step = ConditionalStep(id="test", condition="{{state.value > 0}}", then=["a"], else_=["b"])
    assert step.id == "test"
    assert step.type == "conditional"
    assert step.then == ["a"]
    assert step.else_ == ["b"]


@pytest.mark.asyncio
async def test_conditional_step_execute_true(tmp_path):
    """Test ConditionalStep evaluates true condition."""
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.conditional_step import ConditionalStep

    state = WorkflowState({"value": 5})
    step = ConditionalStep(
        id="check", condition="{{state.value > 0}}", then=["deploy"], else_=["rollback"]
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=None,
        state_store=None,
    )

    result = await step.execute(state, context)

    assert result.status == "success"
    assert result.outputs["branch_taken"] == "then"
    assert result.outputs["condition_value"] is True
    assert result.outputs["selected_steps"] == ["deploy"]


@pytest.mark.asyncio
async def test_conditional_step_execute_false(tmp_path):
    """Test ConditionalStep evaluates false condition."""
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.conditional_step import ConditionalStep

    state = WorkflowState({"value": -1})
    step = ConditionalStep(
        id="check", condition="{{state.value > 0}}", then=["deploy"], else_=["rollback"]
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=None,
        state_store=None,
    )

    result = await step.execute(state, context)

    assert result.status == "success"
    assert result.outputs["branch_taken"] == "else"
    assert result.outputs["condition_value"] is False
    assert result.outputs["selected_steps"] == ["rollback"]


@pytest.mark.asyncio
async def test_conditional_step_execute_error(tmp_path):
    """Test ConditionalStep handles evaluation errors."""
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.conditional_step import ConditionalStep

    state = WorkflowState({})
    # Invalid condition (missing variable)
    step = ConditionalStep(
        id="check", condition="{{state.nonexistent > 0}}", then=["a"], else_=["b"]
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=None,
        state_store=None,
    )

    result = await step.execute(state, context)

    assert result.status == "failed"
    assert result.error is not None


def test_conditional_step_serialize_deserialize():
    """Test ConditionalStep serialize/deserialize roundtrip."""
    from agentrails.steps.conditional_step import ConditionalStep

    original = ConditionalStep(
        id="check",
        condition="{{state.value > 0}}",
        then=["deploy"],
        else_=["rollback"],
        depends_on=["test"],
        max_retries=2,
    )

    data = original.serialize()
    restored = ConditionalStep.deserialize(data)

    assert restored.id == original.id
    assert restored.condition == original.condition
    assert restored.then == original.then
    assert restored.else_ == original.else_
    assert restored.depends_on == original.depends_on
    assert restored.max_retries == original.max_retries
