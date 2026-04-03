"""Output manager for compact and interactive display modes."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class StepProgress:
    """Progress information for a single step."""

    step_id: str
    status: str  # running, completed, failed, skipped, pending
    duration: float | None = None
    error: str | None = None
    branches: dict[str, StepProgress] | None = None


class DisplayManager:
    """Manages workflow output display in compact or interactive mode."""

    def __init__(self, workflow_name: str, run_id: str, interactive: bool = False):
        """Initialize the display manager.

        Args:
            workflow_name: Name of the workflow being executed
            run_id: Unique identifier for this run
            interactive: If True, use rich/textual interactive display
        """
        self.workflow_name = workflow_name
        self.run_id = run_id
        self.interactive = interactive
        self._steps: dict[str, StepProgress] = {}

    def workflow_header(self) -> None:
        """Print workflow header line at start of execution."""
        print(f"agentrails: {self.workflow_name} (run: {self.run_id})")

    def step_started(self, step_id: str, step_num: int, total: int) -> None:
        """Called when a step starts executing."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="running")
        print(f"[{step_num}/{total}] {step_id}: running...")

    def step_completed(self, step_id: str, step_num: int, total: int, duration: float) -> None:
        """Called when a step completes successfully."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="completed", duration=duration)
        print(f"[{step_num}/{total}] {step_id}: completed ({duration:.1f}s)")

    def step_failed(
        self, step_id: str, step_num: int, total: int, duration: float, error: str
    ) -> None:
        """Called when a step fails."""
        self._steps[step_id] = StepProgress(
            step_id=step_id, status="failed", duration=duration, error=error
        )
        print(f"[{step_num}/{total}] {step_id}: failed -- {error} ({duration:.1f}s)")

    def step_skipped(self, step_id: str, step_num: int, total: int) -> None:
        """Called when a step is skipped (condition evaluated to false)."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="skipped", duration=0.0)
        print(f"[{step_num}/{total}] {step_id}: skipped")

    def workflow_completed(self, steps_completed: int, steps_failed: int, duration: float) -> None:
        """Called when the workflow completes."""
        total = len(self._steps)
        status = "failed" if steps_failed > 0 else "completed"
        print(f"agentrails: {status} ({steps_completed}/{total} steps, {duration:.1f}s)")

    def workflow_summary(
        self,
        status: str,
        failed_step: str | None = None,
        error: str | None = None,
        duration: float = 0.0,
        steps_completed: int = 0,
        steps_failed: int = 0,
        steps_pending: int = 0,
    ) -> None:
        """Print final JSON summary line."""
        summary = {
            "run_id": self.run_id,
            "status": status,
            "duration": round(duration, 1),
        }
        if steps_completed:
            summary["steps_completed"] = steps_completed
        if steps_failed:
            summary["steps_failed"] = steps_failed
        if steps_pending:
            summary["steps_pending"] = steps_pending
        if failed_step:
            summary["failed_step"] = failed_step
        if error:
            summary["error"] = error

        print(json.dumps(summary, separators=(",", ":")))
