"""Tests for SQLite storage backend."""

import pytest

from agentrails.event_log import Event
from agentrails.steps.base import StepResult


@pytest.mark.asyncio
async def test_sqlite_save_load_state(tmp_state_dir):
    """Test saving and loading state from SQLite."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    state = {"key": "value", "nested": {"a": 1}}
    await store.save_state("wf1", "run1", state)

    loaded = await store.load_state("wf1", "run1")
    assert loaded == state

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_load_state_returns_none_for_missing_run(tmp_state_dir):
    """Test load_state returns None for non-existent run."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    loaded = await store.load_state("wf1", "nonexistent")
    assert loaded is None

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_save_state_updates_without_resetting_started_at(tmp_state_dir):
    """Test that save_state updates don't overwrite started_at."""

    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    # Initial save
    await store.save_state("wf1", "run1", {"count": 1})

    # Get the started_at timestamp
    conn = await store._get_connection()
    cursor = await conn.execute(
        "SELECT started_at FROM runs WHERE run_id = ?",
        ("run1",),
    )
    row = await cursor.fetchone()
    original_started_at = row[0]

    # Wait a tiny bit to ensure timestamp would be different if reset
    import asyncio

    await asyncio.sleep(0.01)

    # Update state
    await store.save_state("wf1", "run1", {"count": 2})

    # Verify started_at unchanged
    cursor = await conn.execute(
        "SELECT started_at FROM runs WHERE run_id = ?",
        ("run1",),
    )
    row = await cursor.fetchone()
    assert row[0] == original_started_at

    # Verify state was updated
    loaded = await store.load_state("wf1", "run1")
    assert loaded == {"count": 2}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_save_state_with_workflow_name(tmp_state_dir):
    """Test that workflow_name is stored on initial insert."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    await store.save_state("wf1", "run1", {"key": "value"}, workflow_name="Test Workflow")

    # Query directly to verify workflow_name
    conn = await store._get_connection()
    cursor = await conn.execute(
        "SELECT workflow_name FROM runs WHERE run_id = ?",
        ("run1",),
    )
    row = await cursor.fetchone()
    assert row[0] == "Test Workflow"

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_append_event(tmp_state_dir):
    """Test appending an event to the log."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    event = Event.create(
        workflow_id="wf1",
        run_id="run1",
        event_type="workflow_started",
        data={"source": "test"},
    )

    await store.append_event(event)

    # Verify by loading events
    events = await store.load_events("wf1", "run1")
    assert len(events) == 1
    assert events[0].event_type == "workflow_started"
    assert events[0].data == {"source": "test"}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_load_events_order(tmp_state_dir):
    """Test that events are returned in timestamp order."""
    from datetime import datetime, timedelta

    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    base_time = datetime.now()

    # Create events with specific timestamps (in reverse order)
    events_to_add = []
    for i, event_type in enumerate(["step_3", "step_1", "step_2"]):
        event = Event(
            event_id=f"event-{i}",
            workflow_id="wf1",
            run_id="run1",
            timestamp=base_time + timedelta(seconds=i),
            event_type=event_type,
            step_id=None,
            data={},
        )
        events_to_add.append(event)

    # Add in wrong order
    await store.append_event(events_to_add[0])  # step_3
    await store.append_event(events_to_add[1])  # step_1
    await store.append_event(events_to_add[2])  # step_2

    loaded = await store.load_events("wf1", "run1")
    assert len(loaded) == 3
    # Should be ordered by timestamp
    assert loaded[0].event_type == "step_3"
    assert loaded[1].event_type == "step_1"
    assert loaded[2].event_type == "step_2"

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_load_events_empty_for_missing_run(tmp_state_dir):
    """Test load_events returns empty list for non-existent run."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    events = await store.load_events("wf1", "nonexistent")
    assert events == []

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_load_events_timestamp_is_datetime(tmp_state_dir):
    """Test that loaded events have datetime objects, not strings."""
    from datetime import datetime

    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    event = Event.create(
        workflow_id="wf1",
        run_id="run1",
        event_type="workflow_started",
    )
    await store.append_event(event)

    loaded = await store.load_events("wf1", "run1")
    assert len(loaded) == 1
    assert isinstance(loaded[0].timestamp, datetime)

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_save_step_result(tmp_state_dir):
    """Test saving a step execution result."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    result = StepResult(
        step_id="step1",
        status="success",
        outputs={"key": "value"},
        raw_output="stdout text",
        duration_seconds=12.34,
        error=None,
    )

    await store.save_step_result("wf1", "run1", result)

    # Verify by loading
    loaded = await store.load_step_results("wf1", "run1")
    assert "step1" in loaded
    assert loaded["step1"].step_id == "step1"
    assert loaded["step1"].status == "success"
    assert loaded["step1"].outputs == {"key": "value"}
    assert loaded["step1"].raw_output == "stdout text"
    assert loaded["step1"].duration_seconds == 12.34
    assert loaded["step1"].error is None

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_update_step_result(tmp_state_dir):
    """Test that step results can be updated."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    # Save initial result
    result1 = StepResult(
        step_id="step1",
        status="running",
        outputs={},
        raw_output="",
        duration_seconds=0,
        error=None,
    )
    await store.save_step_result("wf1", "run1", result1)

    # Update with completed result
    result2 = StepResult(
        step_id="step1",
        status="success",
        outputs={"result": "done"},
        raw_output="output",
        duration_seconds=5.5,
        error=None,
    )
    await store.save_step_result("wf1", "run1", result2)

    loaded = await store.load_step_results("wf1", "run1")
    assert loaded["step1"].status == "success"
    assert loaded["step1"].outputs == {"result": "done"}
    assert loaded["step1"].duration_seconds == 5.5

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_load_step_results_empty(tmp_state_dir):
    """Test load_step_results returns empty dict for non-existent run."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    loaded = await store.load_step_results("wf1", "nonexistent")
    assert loaded == {}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_list_runs_all(tmp_state_dir):
    """Test listing all runs."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    await store.save_state("wf1", "run1", {})
    await store.save_state("wf2", "run2", {})
    await store.save_state("wf1", "run3", {})

    runs = await store.list_runs()
    assert len(runs) == 3
    run_ids = {r.run_id for r in runs}
    assert run_ids == {"run1", "run2", "run3"}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_list_runs_filtered_by_workflow(tmp_state_dir):
    """Test listing runs filtered by workflow_id."""
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    await store.save_state("wf1", "run1", {})
    await store.save_state("wf2", "run2", {})
    await store.save_state("wf1", "run3", {})

    runs = await store.list_runs(workflow_id="wf1")
    assert len(runs) == 2
    assert all(r.workflow_id == "wf1" for r in runs)
    run_ids = {r.run_id for r in runs}
    assert run_ids == {"run1", "run3"}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_schema_auto_creation(tmp_state_dir):
    """Test that schema is auto-created on first connection."""

    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"

    # Ensure file doesn't exist yet
    assert not db_path.exists()

    store = SqliteStateStore(db_path)
    await store._get_connection()

    # Verify tables exist
    conn = await store._get_connection()
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in await cursor.fetchall()}
    assert tables == {"runs", "events", "step_results", "sessions"}

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_session_persistence(tmp_state_dir):
    """Test session save/load/update operations."""
    from datetime import datetime

    from agentrails.storage import SessionInfo
    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    now = datetime.now()
    session = SessionInfo(
        session_id="test-session-123",
        workflow_id="test_wf",
        run_id="test_run",
        name="Test Session",
        status="running",
        working_dir="/tmp/test",
        created_at=now,
        last_used_at=now,
    )

    # Save session
    await store.save_session(session)

    # Load sessions
    sessions = await store.load_sessions()
    assert len(sessions) == 1
    assert sessions[0].session_id == "test-session-123"
    assert sessions[0].workflow_id == "test_wf"
    assert sessions[0].name == "Test Session"

    # Update status
    await store.update_session_status("test-session-123", "completed")
    updated = await store.load_sessions()
    assert updated[0].status == "completed"

    # Filter by workflow_id
    sessions = await store.load_sessions(workflow_id="test_wf")
    assert len(sessions) == 1

    # Filter by run_id
    sessions = await store.load_sessions(run_id="test_run")
    assert len(sessions) == 1

    # Filter by non-existent workflow
    sessions = await store.load_sessions(workflow_id="other_wf")
    assert len(sessions) == 0

    await store.close()


@pytest.mark.asyncio
async def test_sqlite_concurrent_saves_different_runs(tmp_state_dir):
    """Test concurrent saves to different runs."""
    import asyncio

    from agentrails.storage_sqlite import SqliteStateStore

    db_path = tmp_state_dir / "state.db"
    store = SqliteStateStore(db_path)

    async def save_run(run_id: str, data: dict):
        await store.save_state("wf1", run_id, data)

    # Save multiple runs concurrently
    await asyncio.gather(
        save_run("run1", {"id": 1}),
        save_run("run2", {"id": 2}),
        save_run("run3", {"id": 3}),
    )

    # Verify all saved
    for i in range(1, 4):
        loaded = await store.load_state("wf1", f"run{i}")
        assert loaded == {"id": i}

    await store.close()
