"""Tests for ParallelGroupStep class."""

import pytest


def test_parallel_step_initialization():
    """Test ParallelGroupStep can be initialized."""
    from agentrails.steps.parallel_step import ParallelGroupStep
    from agentrails.steps.shell_step import ShellStep

    branches = [ShellStep(id="a", script="echo a")]
    step = ParallelGroupStep(id="test", branches=branches)

    assert step.id == "test"
    assert step.type == "parallel_group"
    assert len(step.branches) == 1


def test_parallel_step_serialize_deserialize():
    """Test ParallelGroupStep serialize/deserialize roundtrip."""
    from agentrails.steps.parallel_step import ParallelGroupStep
    from agentrails.steps.shell_step import ShellStep

    original = ParallelGroupStep(
        id="parallel",
        branches=[
            ShellStep(id="branch1", script="echo 1"),
            ShellStep(id="branch2", script="echo 2"),
        ],
        max_concurrency=2,
        fail_fast=True,
        merge_strategy="list_append",
        depends_on=["setup"],
    )

    data = original.serialize()
    restored = ParallelGroupStep.deserialize(data)

    assert restored.id == original.id
    assert restored.max_concurrency == original.max_concurrency
    assert restored.fail_fast == original.fail_fast
    assert restored.merge_strategy == original.merge_strategy
    assert len(restored.branches) == len(original.branches)
    assert restored.branches[0].id == "branch1"
    assert restored.branches[1].id == "branch2"


@pytest.mark.asyncio
async def test_parallel_step_execute_concurrent(tmp_path):
    """Test ParallelGroupStep executes branches concurrently."""
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.parallel_step import ParallelGroupStep
    from agentrails.steps.shell_step import ShellStep

    branches = [ShellStep(id=f"branch{i}", script=f"echo {i}") for i in range(3)]
    step = ParallelGroupStep(id="parallel", branches=branches, max_concurrency=3)

    from agentrails.state import WorkflowState

    state = WorkflowState({})
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
    assert "branches" in result.outputs
    assert len(result.outputs["branches"]) == 3


@pytest.mark.asyncio
async def test_parallel_step_fail_fast(tmp_path):
    """Test ParallelGroupStep fail_fast cancels remaining branches."""
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.parallel_step import ParallelGroupStep
    from agentrails.steps.shell_step import ShellStep

    # One branch will fail
    branches = [
        ShellStep(id="good", script="echo ok"),
        ShellStep(id="bad", script="exit 1"),
        ShellStep(id="another", script="echo ok"),
    ]
    step = ParallelGroupStep(id="parallel", branches=branches, fail_fast=True)

    from agentrails.state import WorkflowState

    state = WorkflowState({})
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
    # At least one branch should have failed
    assert result.error is not None


@pytest.mark.asyncio
async def test_parallel_step_merge_strategy(tmp_path):
    """Test ParallelGroupStep merge strategies."""
    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext
    from agentrails.steps.parallel_step import ParallelGroupStep
    from agentrails.steps.shell_step import ShellStep

    # Branches that produce outputs
    branches = [
        ShellStep(id="b1", script="echo val1"),
        ShellStep(id="b2", script="echo val2"),
    ]
    step = ParallelGroupStep(
        id="parallel",
        branches=branches,
        merge_strategy="list_append",
    )

    state = WorkflowState({})
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
    assert "branches" in result.outputs
