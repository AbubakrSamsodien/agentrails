"""Integration tests for deterministic replay from event log."""

import pytest


@pytest.mark.asyncio
async def test_replay_produces_identical_state(tmp_path):
    """Test that replaying events produces identical final state."""
    from agentrails.engine import WorkflowRunner
    from agentrails.event_log import EventLog

    # Create a simple workflow
    workflow_file = tmp_path / "replay_test.yaml"
    workflow_file.write_text("""
name: replay_test
steps:
  - id: step1
    type: shell
    script: "echo hello"
  - id: step2
    type: shell
    depends_on: [step1]
    script: "echo world"
""")

    # Run workflow to completion
    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    original_state = result.final_state.snapshot()

    # Get events from the run
    store = await runner._get_state_store()
    events = await store.load_events("replay_test", result.run_id)

    # Create EventLog and replay events
    log = EventLog("replay_test", result.run_id)
    for event in events:
        log.append(event)
    replay_result = log.replay()

    # Compare states
    assert replay_result["state"].snapshot() == original_state


@pytest.mark.asyncio
async def test_replay_parallel_workflow(tmp_path):
    """Test replay of parallel workflow produces identical state."""
    from agentrails.engine import WorkflowRunner
    from agentrails.event_log import EventLog

    workflow_file = tmp_path / "parallel_replay.yaml"
    workflow_file.write_text("""
name: parallel_replay_test
steps:
  - id: parallel_step
    type: parallel_group
    branches:
      - id: branch1
        type: shell
        script: "echo first"
      - id: branch2
        type: shell
        script: "echo second"
""")

    # Run workflow
    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    original_state = result.final_state.snapshot()

    # Replay
    store = await runner._get_state_store()
    events = await store.load_events("parallel_replay_test", result.run_id)
    log = EventLog("parallel_replay_test", result.run_id)
    for event in events:
        log.append(event)
    replay_result = log.replay()

    # Compare states (order-independent merge should produce same result)
    assert replay_result["state"].snapshot() == original_state


@pytest.mark.asyncio
async def test_replay_conditional_workflow(tmp_path):
    """Test replay of conditional workflow takes same branch."""
    from agentrails.engine import WorkflowRunner
    from agentrails.event_log import EventLog

    workflow_file = tmp_path / "conditional_replay.yaml"
    workflow_file.write_text("""
name: conditional_replay_test
steps:
  - id: check
    type: shell
    script: "echo success"
  - id: branch
    type: conditional
    depends_on: [check]
    if: "{{'success' in state.stdout}}"
    then: [then_path]
    else: [else_path]
  - id: then_path
    type: shell
    depends_on: [branch]
    script: "echo then"
  - id: else_path
    type: shell
    depends_on: [branch]
    script: "echo else"
""")

    # Run workflow
    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    original_state = result.final_state.snapshot()

    # Replay
    store = await runner._get_state_store()
    events = await store.load_events("conditional_replay_test", result.run_id)
    log = EventLog("conditional_replay_test", result.run_id)
    for event in events:
        log.append(event)
    replay_result = log.replay()

    # Same condition should lead to same branch
    assert replay_result["state"].snapshot() == original_state
    # Verify the then branch was taken in replay
    assert "then_path" in replay_result["completed_steps"]
