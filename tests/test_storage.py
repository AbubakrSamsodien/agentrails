"""Tests for storage interface (ABC and dataclasses)."""

import pytest


def test_runinfo_dataclass():
    """Test RunInfo dataclass fields and initialization."""
    from agentrails.storage import RunInfo

    run = RunInfo(
        run_id="run-123",
        workflow_id="wf-456",
        status="completed",
        started_at="2026-04-01T10:00:00",
        completed_at="2026-04-01T10:05:00",
    )

    assert run.run_id == "run-123"
    assert run.workflow_id == "wf-456"
    assert run.status == "completed"
    assert run.started_at == "2026-04-01T10:00:00"
    assert run.completed_at == "2026-04-01T10:05:00"


def test_runinfo_with_null_completed_at():
    """Test RunInfo for running workflow (no completion time)."""
    from agentrails.storage import RunInfo

    run = RunInfo(
        run_id="run-789",
        workflow_id="wf-012",
        status="running",
        started_at="2026-04-01T11:00:00",
        completed_at=None,
    )

    assert run.status == "running"
    assert run.completed_at is None


def test_statestore_is_abstract():
    """Test that StateStore cannot be instantiated directly."""
    from agentrails.storage import StateStore

    with pytest.raises(TypeError, match="abstract method"):
        StateStore()


def test_statestore_requires_implementation():
    """Test that StateStore requires all abstract methods."""
    from agentrails.storage import StateStore

    class IncompleteStore(StateStore):
        pass

    with pytest.raises(TypeError, match="abstract method"):
        IncompleteStore()
