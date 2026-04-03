"""Storage backend interface (abstract base class)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class RunInfo:
    """Information about a workflow run."""

    run_id: str
    workflow_id: str
    status: Literal["completed", "failed", "running"]
    started_at: str
    completed_at: str | None


@dataclass
class SessionInfo:
    """Information about a Claude CLI session."""

    session_id: str
    workflow_id: str
    run_id: str
    name: str | None
    status: Literal["running", "completed", "dead", "killed"]
    working_dir: str
    created_at: datetime
    last_used_at: datetime


class StateStore(ABC):
    """Abstract storage backend for workflow state and events."""

    @abstractmethod
    async def save_state(
        self,
        workflow_id: str,
        run_id: str,
        state: dict[str, Any],
    ) -> None:
        """Save workflow state checkpoint."""

    @abstractmethod
    async def load_state(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Load workflow state checkpoint."""

    @abstractmethod
    async def append_event(self, event: Any) -> None:
        """Append an event to the log.

        Args:
            event: Event object from event_log module
        """

    @abstractmethod
    async def load_events(
        self,
        workflow_id: str,
        run_id: str,
    ) -> list[Any]:
        """Load all events for a run."""

    @abstractmethod
    async def save_step_result(
        self,
        workflow_id: str,
        run_id: str,
        result: Any,
    ) -> None:
        """Save a step execution result.

        Args:
            result: StepResult from steps.base module
        """

    @abstractmethod
    async def load_step_results(
        self,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Load all step results for a run."""

    @abstractmethod
    async def list_runs(
        self,
        workflow_id: str | None = None,
    ) -> list[RunInfo]:
        """List workflow runs, optionally filtered by workflow."""

    @abstractmethod
    async def save_session(self, session: SessionInfo) -> None:
        """Save session metadata.

        Args:
            session: SessionInfo object
        """

    @abstractmethod
    async def load_sessions(
        self,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> list[SessionInfo]:
        """Load sessions, optionally filtered.

        Args:
            workflow_id: Filter by workflow ID
            run_id: Filter by run ID

        Returns:
            List of SessionInfo objects
        """

    @abstractmethod
    async def update_session_status(
        self,
        session_id: str,
        status: Literal["running", "completed", "dead", "killed"],
    ) -> None:
        """Update session status.

        Args:
            session_id: Session ID
            status: New status
        """
