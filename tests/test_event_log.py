"""Tests for EventLog class."""

from agentrails.event_log import Event, EventLog


def test_event_creation():
    """Test Event creation."""
    event = Event.create(
        workflow_id="wf1",
        run_id="run1",
        event_type="workflow_started",
    )

    assert event.event_id is not None
    assert event.workflow_id == "wf1"
    assert event.run_id == "run1"
    assert event.event_type == "workflow_started"


def test_event_log_replay_basic():
    """Test replay reconstructs state from events."""
    log = EventLog("wf1", "run1")

    # Add events
    log.append(Event.create("wf1", "run1", "state_updated", data={"key": "a", "value": 1}))
    log.append(Event.create("wf1", "run1", "state_updated", data={"key": "b", "value": 2}))
    log.append(Event.create("wf1", "run1", "step_completed", step_id="step1"))

    result = log.replay()

    assert result["state"].get("a") == 1
    assert result["state"].get("b") == 2
    assert "step1" in result["completed_steps"]


def test_event_log_replay_skipped_steps():
    """Test replay tracks skipped steps."""
    log = EventLog("wf1", "run1")

    log.append(Event.create("wf1", "run1", "step_completed", step_id="step1"))
    log.append(Event.create("wf1", "run1", "step_skipped", step_id="step2"))
    log.append(Event.create("wf1", "run1", "step_skipped", step_id="step3"))

    result = log.replay()

    assert "step1" in result["completed_steps"]
    assert "step2" in result["skipped_steps"]
    assert "step3" in result["skipped_steps"]


def test_event_log_replay_state_snapshot():
    """Test replay restores from state snapshot."""
    log = EventLog("wf1", "run1")

    # Start with some state
    log.append(Event.create("wf1", "run1", "state_updated", data={"key": "a", "value": 1}))
    # Then a full snapshot
    log.append(Event.create("wf1", "run1", "state_updated", data={"state": {"b": 2, "c": 3}}))

    result = log.replay()

    # Snapshot should replace previous state
    assert result["state"].get("a") is None
    assert result["state"].get("b") == 2
    assert result["state"].get("c") == 3


def test_event_log_hash_workflow():
    """Test workflow hashing for drift detection."""
    yaml1 = "name: test\nsteps: []"
    yaml2 = "name: test\nsteps: []\n"  # Different

    hash1 = EventLog.hash_workflow(yaml1)
    hash2 = EventLog.hash_workflow(yaml2)

    assert hash1 != hash2
    assert len(hash1) == 64  # SHA256 hex


def test_event_log_schema_drift():
    """Test schema drift detection."""
    log = EventLog("wf1", "run1")

    original_yaml = "name: test\nsteps: []"
    original_hash = EventLog.hash_workflow(original_yaml)

    # Simulate workflow_started event with hash
    log.append(
        Event.create("wf1", "run1", "workflow_started", data={"workflow_hash": original_hash})
    )

    # Same YAML - no drift
    assert log.check_schema_drift(original_yaml) is None

    # Different YAML - drift detected
    modified_yaml = "name: test\nsteps:\n  - id: a"
    warning = log.check_schema_drift(modified_yaml)
    assert warning is not None
    assert "changed" in warning.lower()


def test_event_log_schema_drift_no_hash():
    """Test drift detection handles missing hash gracefully."""
    log = EventLog("wf1", "run1")

    # workflow_started without hash (old workflow)
    log.append(Event.create("wf1", "run1", "workflow_started", data={}))

    # Should return None (no drift detection possible)
    assert log.check_schema_drift("any yaml") is None


def test_event_log_schema_drift_no_started_event():
    """Test drift detection handles missing workflow_started event."""
    log = EventLog("wf1", "run1")

    # No workflow_started event
    assert log.check_schema_drift("any yaml") is None
