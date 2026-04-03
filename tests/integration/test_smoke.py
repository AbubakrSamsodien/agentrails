"""Walking skeleton integration test - end-to-end smoke test."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_smoke_workflow(tmp_state_dir, fixtures_dir):
    """Test the walking skeleton: parse, execute single shell step, checkpoint state.

    This is the "it actually runs" test that verifies the entire pipeline works:
    1. Parse YAML workflow
    2. Execute a single shell step
    3. Checkpoint state to SQLite
    4. Complete successfully
    """
    from agentrails.config import Config
    from agentrails.engine import WorkflowRunner
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"

    # Create config with custom state_dir
    config = Config(
        state_dir=str(tmp_state_dir),
    )

    runner = WorkflowRunner(
        config=config,
        working_directory=fixtures_dir,
    )

    # Run the smoke test workflow
    result = await runner.run(str(fixtures_dir / "smoke.yaml"))

    # Close the runner's resources
    await runner.close()

    # Verify result
    assert result.status == "completed"
    assert result.step_results["hello"].status == "success"
    assert "hello" in result.step_results["hello"].raw_output

    # Verify SQLite state file was created
    assert db_path.exists()

    # Verify event log contains expected events
    store = SqliteStateStore(db_path)
    events = await store.load_events("smoke_test", result.run_id)
    event_types = [e.event_type for e in events]

    assert "workflow_started" in event_types
    assert "step_started" in event_types
    assert "step_completed" in event_types
    assert "workflow_completed" in event_types

    await store.close()
