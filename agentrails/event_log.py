"""Event sourcing and replay for deterministic workflow execution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4


@dataclass
class Event:
    """An event in the workflow execution log."""

    event_id: str
    workflow_id: str
    run_id: str
    timestamp: datetime
    event_type: Literal[
        "workflow_started",
        "workflow_completed",
        "workflow_failed",
        "step_started",
        "step_completed",
        "step_failed",
        "step_skipped",
        "state_updated",
        "checkpoint_saved",
        "step_retried",
    ]
    step_id: str | None
    data: dict[str, Any]

    @classmethod
    def create(
        cls,
        workflow_id: str,
        run_id: str,
        event_type: str,
        step_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        """Create a new event with current timestamp and UUID."""
        return cls(
            event_id=str(uuid4()),
            workflow_id=workflow_id,
            run_id=run_id,
            timestamp=datetime.now(),
            event_type=event_type,  # type: ignore
            step_id=step_id,
            data=data or {},
        )


class EventLog:
    """Append-only event log for workflow execution."""

    def __init__(self, workflow_id: str, run_id: str):
        """Initialize the event log.

        Args:
            workflow_id: ID of the workflow
            run_id: ID of this specific run
        """
        self.workflow_id = workflow_id
        self.run_id = run_id
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        """Append an event to the log."""
        self._events.append(event)

    def get_events(self) -> list[Event]:
        """Get all events in the log."""
        return list(self._events)

    @staticmethod
    def create_event(
        workflow_id: str,
        run_id: str,
        event_type: str,
        step_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        """Static method to create an event.

        This is a convenience method for the engine to create events.
        """
        return Event.create(workflow_id, run_id, event_type, step_id, data)

    def replay(self) -> dict[str, Any]:
        """Replay events to reconstruct state and completed steps.

        Returns:
            Dictionary with:
                - state: WorkflowState reconstructed from events
                - completed_steps: set of step IDs that completed successfully
                - skipped_steps: set of step IDs that were skipped
        """
        from agentrails.state import WorkflowState  # pylint: disable=C0415

        state = WorkflowState({})
        completed_steps: set[str] = set()
        skipped_steps: set[str] = set()

        for event in self._events:
            if event.event_type == "state_updated":
                # Apply state updates
                data = event.data
                if "key" in data and "value" in data:
                    # FIX: WorkflowState is immutable - .set() returns a new copy
                    state = state.set(data["key"], data["value"])
                elif "state" in data:
                    # Full state snapshot - restore from it
                    snapshot = data["state"]
                    if isinstance(snapshot, dict):
                        state = WorkflowState(snapshot)

            elif event.event_type == "step_completed":
                # Mark step as completed
                if event.step_id:
                    completed_steps.add(event.step_id)

            elif event.event_type == "step_skipped":
                # Mark step as skipped
                if event.step_id:
                    skipped_steps.add(event.step_id)

        return {
            "state": state,
            "completed_steps": completed_steps,
            "skipped_steps": skipped_steps,
        }

    @staticmethod
    def hash_workflow(workflow_yaml: str) -> str:
        """Compute a hash of the workflow YAML for schema drift detection.

        Args:
            workflow_yaml: Raw YAML content of the workflow

        Returns:
            SHA256 hash hex string
        """
        return hashlib.sha256(workflow_yaml.encode()).hexdigest()

    def check_schema_drift(self, current_workflow_yaml: str) -> str | None:
        """Check if the workflow YAML has changed since execution started.

        Args:
            current_workflow_yaml: Current YAML content

        Returns:
            Warning message if drift detected, None if unchanged
        """
        # Find workflow_started event
        started_event = None
        for event in self._events:
            if event.event_type == "workflow_started":
                started_event = event
                break

        if started_event is None:
            return None

        stored_hash = started_event.data.get("workflow_hash")
        if stored_hash is None:
            return None  # No hash stored (old workflow)

        current_hash = self.hash_workflow(current_workflow_yaml)
        if current_hash != stored_hash:
            return (
                f"Workflow YAML has changed since this run started. "
                f"Original hash: {stored_hash[:16]}..., Current hash: {current_hash[:16]}..."
            )

        return None
