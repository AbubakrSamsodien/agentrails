"""Output manager for compact and interactive display modes."""
# pylint: disable=C0301  # Display lines intentionally long for UI

from __future__ import annotations

import json
import sys
from dataclasses import dataclass


@dataclass
class StepProgress:
    """Progress information for a single step."""

    step_id: str
    status: str  # running, completed, failed, skipped, pending
    duration: float | None = None
    error: str | None = None
    branches: dict[str, StepProgress] | None = None
    step_type: str = ""


class DisplayManager:
    """Manages workflow output display in compact or interactive mode."""

    def __init__(
        self, workflow_name: str, run_id: str, interactive: bool = False, total_steps: int = 0
    ):
        """Initialize the display manager.

        Args:
            workflow_name: Name of the workflow being executed
            run_id: Unique identifier for this run
            interactive: If True, use rich/textual interactive display
            total_steps: Total number of steps in the workflow
        """
        self.workflow_name = workflow_name
        self.run_id = run_id
        self.interactive = interactive
        self._total_steps = total_steps
        self._steps: dict[str, StepProgress] = {}
        self._start_time: float | None = None
        self._display: InteractiveDisplay | None = None

        if interactive:
            self._setup_interactive()

    def _setup_interactive(self) -> None:
        """Set up interactive display with rich/textual."""
        try:
            from rich.console import Console
            from rich.live import Live
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text

            self._console = Console()
            self._live = Live(auto_refresh=True, refresh_per_second=4)
            self._panel_cls = Panel
            self._table_cls = Table
            self._text_cls = Text
            self._interactive_ready = True
        except ImportError:
            self._interactive_ready = False
            self.interactive = False
            print(
                "Warning: Interactive mode requires rich. Install with: uv pip install 'agentrails[interactive]'",  # noqa: C0301
                file=sys.stderr,
            )

    def workflow_header(self) -> None:
        """Print workflow header line at start of execution."""
        if self.interactive and self._interactive_ready:
            self._console.print(
                f"[bold]agentrails:[/bold] {self.workflow_name} (run: {self.run_id})"
            )
        else:
            print(f"agentrails: {self.workflow_name} (run: {self.run_id})")

    def step_started(self, step_id: str, step_num: int, total: int, step_type: str = "") -> None:
        """Called when a step starts executing."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="running", step_type=step_type)

        if self.interactive and self._interactive_ready:
            self._update_display()
        else:
            print(f"[{step_num}/{total}] {step_id}: running...")

    def step_completed(self, step_id: str, step_num: int, total: int, duration: float) -> None:
        """Called when a step completes successfully."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="completed", duration=duration)

        if self.interactive and self._interactive_ready:
            self._update_display()
        else:
            print(f"[{step_num}/{total}] {step_id}: completed ({duration:.1f}s)")

    def step_failed(
        self, step_id: str, step_num: int, total: int, duration: float, error: str
    ) -> None:
        """Called when a step fails."""
        self._steps[step_id] = StepProgress(
            step_id=step_id, status="failed", duration=duration, error=error
        )

        if self.interactive and self._interactive_ready:
            self._update_display()
        else:
            print(f"[{step_num}/{total}] {step_id}: failed -- {error} ({duration:.1f}s)")

    def step_skipped(self, step_id: str, step_num: int, total: int) -> None:
        """Called when a step is skipped (condition evaluated to false)."""
        self._steps[step_id] = StepProgress(step_id=step_id, status="skipped", duration=0.0)

        if self.interactive and self._interactive_ready:
            self._update_display()
        else:
            print(f"[{step_num}/{total}] {step_id}: skipped")

    def workflow_completed(self, steps_completed: int, steps_failed: int, duration: float) -> None:
        """Called when the workflow completes."""
        total = len(self._steps)
        status = "failed" if steps_failed > 0 else "completed"

        if self.interactive and self._interactive_ready:
            self._final_display(status, steps_completed, steps_failed, duration)
            self._live.stop()
        else:
            print(f"agentrails: {status} ({steps_completed}/{total} steps, {duration:.1f}s)")

    def _get_status_symbol(self, status: str) -> str:
        """Get Unicode symbol for step status."""
        symbols = {
            "completed": "✓",
            "failed": "✗",
            "running": "⟳",
            "pending": "○",
            "skipped": "⊘",
        }
        return symbols.get(status, "○")

    def _get_status_style(self, status: str) -> str:
        """Get rich style string for step status."""
        styles = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "dim",
            "skipped": "dim",
        }
        return styles.get(status, "default")

    def _update_display(self) -> None:
        """Update the live interactive display."""
        if not self._interactive_ready:
            return

        table = self._table_cls(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", style="bold", justify="center", width=3)
        table.add_column("Step", style="bold", width=30)
        table.add_column("Type", width=10)
        table.add_column("Duration", width=10)
        table.add_column("Details", width=40)

        for step_id, step in self._steps.items():
            symbol = self._get_status_symbol(step.status)
            style = self._get_status_style(step.status)

            duration_str = ""
            if step.duration is not None:
                duration_str = f"{step.duration:.1f}s"

            details = ""
            if step.error:
                details = step.error[:40]
            elif step.status == "completed":
                details = "ok"

            table.add_row(
                f"[{style}]{symbol}[/{style}]",
                f"[{style}]{step_id}[/{style}]" if step.status != "pending" else step_id,
                step.step_type or "",
                duration_str,
                details,
            )

        _elapsed = ""
        if self._start_time:
            import time

            _elapsed = f"Elapsed: {time.time() - self._start_time:.1f}s"  # noqa: F841

        panel = self._panel_cls(
            table,
            title=f"{self.workflow_name} (run: {self.run_id})",
            border_style="blue",
        )

        if not self._live.is_started:
            self._live.start()
        self._live.update(panel)

    def _final_display(
        self, status: str, steps_completed: int, steps_failed: int, duration: float
    ) -> None:
        """Show final summary in interactive mode."""
        if not self._interactive_ready:
            return

        total = len(self._steps)
        summary_text = self._text_cls()
        summary_text.append(f"\nWorkflow {status}\n", style="bold " + status)
        summary_text.append(f"Steps: {steps_completed}/{total} completed")
        if steps_failed > 0:
            summary_text.append(f", {steps_failed} failed", style="red")
        summary_text.append(f"\nTotal time: {duration:.1f}s\n")

        panel = self._panel_cls(
            summary_text, border_style="green" if status == "completed" else "red"
        )
        self._live.update(panel)

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

        if self.interactive and self._interactive_ready:
            self._console.print(json.dumps(summary, separators=(",", ":")))
        else:
            print(json.dumps(summary, separators=(",", ":")))


class InteractiveDisplay:
    """Rich-based interactive workflow display.

    Provides a live-updating dashboard showing all workflow steps
    with visual status indicators, colors, and real-time progress.
    """

    STATUS_SYMBOLS = {
        "completed": "✓",
        "failed": "✗",
        "running": "⟳",
        "pending": "○",
        "skipped": "⊘",
    }

    STATUS_STYLES = {
        "completed": "green",
        "failed": "red",
        "running": "yellow",
        "pending": "dim",
        "skipped": "dim",
    }

    def __init__(self, workflow_name: str, run_id: str, total_steps: int):
        """Initialize interactive display.

        Args:
            workflow_name: Name of the workflow
            run_id: Unique run identifier
            total_steps: Total number of steps in workflow
        """
        from rich.console import Console
        from rich.live import Live
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        self.workflow_name = workflow_name
        self.run_id = run_id
        self.total_steps = total_steps
        self.console = Console()
        self.live = Live(auto_refresh=True, refresh_per_second=4)
        self._panel_cls = Panel
        self._table_cls = Table
        self._text_cls = Text
        self.steps: dict[str, StepProgress] = {}
        self.start_time: float | None = None

    def start(self) -> None:
        """Start the live display."""
        self.start_time = __import__("time").time()
        self.live.start()

    def stop(self) -> None:
        """Stop the live display."""
        self.live.stop()

    def update_step(self, step: StepProgress) -> None:
        """Update a step's progress."""
        self.steps[step.step_id] = step
        self._refresh()

    def _refresh(self) -> None:
        """Refresh the display with current state."""
        table = self._table_cls(show_header=False, box=None, padding=(0, 1))
        table.add_column("Sym", width=3, justify="center")
        table.add_column("Step ID", width=25)
        table.add_column("Type", width=12)
        table.add_column("Time", width=8)
        table.add_column("Status", width=20)

        for step_id, step in sorted(
            self.steps.items(), key=lambda x: list(self.steps.keys()).index(x[0])
        ):
            symbol = self.STATUS_SYMBOLS.get(step.status, "○")
            style = self.STATUS_STYLES.get(step.status, "default")

            duration_str = f"{step.duration:.1f}s" if step.duration else ""

            status_detail = step.status
            if step.error:
                status_detail = f"failed: {step.error[:15]}"

            table.add_row(
                f"[{style}]{symbol}[/{style}]",
                f"[{style}]{step_id}[/{style}]",
                step.step_type or "",
                duration_str,
                status_detail,
            )

        elapsed = ""
        if self.start_time:
            elapsed = f"{__import__('time').time() - self.start_time:.1f}s"

        completed = sum(1 for s in self.steps.values() if s.status == "completed")
        footer = f"Elapsed: {elapsed} | Steps: {completed}/{self.total_steps}"

        panel = self._panel_cls(
            table,
            title=f"{self.workflow_name} (run: {self.run_id})",
            subtitle=footer,
            border_style="blue",
        )
        self.live.update(panel)

    def show_summary(
        self, status: str, duration: float, completed: int, failed: int, skipped: int
    ) -> None:
        """Show workflow completion summary."""
        text = self._text_cls()
        text.append(f"\nWorkflow {status.upper()}\n\n", style=f"bold {status}")
        text.append(f"Total steps: {completed + failed + skipped}\n")
        text.append(f"Completed: {completed}", style="green")
        text.append(f" | Failed: {failed}", style="red")
        text.append(f" | Skipped: {skipped}", style="dim")
        text.append(f"\nDuration: {duration:.1f}s\n")

        panel = self._panel_cls(
            text,
            title="Summary",
            border_style="green" if status == "completed" else "red",
        )
        self.live.update(panel)
