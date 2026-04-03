"""Workflow execution engine."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from agentrails.event_log import EventLog
from agentrails.steps.conditional_step import ConditionalStep

if TYPE_CHECKING:
    from agentrails.config import Config
    from agentrails.state import WorkflowState
    from agentrails.steps.base import BaseStep, StepResult


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""

    workflow_id: str
    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    final_state: WorkflowState
    step_results: dict[str, StepResult]
    duration_seconds: float
    error: str | None = None


class WorkflowRunner:
    """Executes workflows by walking the DAG and invoking steps."""

    def __init__(self, config: Config | None = None, working_directory: Path | None = None):
        """Initialize the workflow runner.

        Args:
            config: Configuration object. Defaults to Config.from_env()
            working_directory: Directory to execute the workflow in
        """
        from agentrails.config import Config  # pylint: disable=C0415

        self.config = config or Config.from_env()
        self.working_directory = working_directory or Path.cwd()
        self._state_store = None
        self._session_manager = None

    async def _get_state_store(self, db_path: Path | None = None):
        """Get or create the state store."""
        if self._state_store is None:
            from agentrails.storage_sqlite import (  # pylint: disable=C0415
                SqliteStateStore,
            )

            if db_path is None:
                db_path = Path(self.config.state_dir) / "state.db"
            self._state_store = SqliteStateStore(db_path)
        return self._state_store

    async def _get_session_manager(self):
        """Get or create the session manager."""
        if self._session_manager is None:
            from agentrails.session_manager import (  # pylint: disable=C0415
                SessionManager,
            )

            store = await self._get_state_store()
            self._session_manager = SessionManager(
                max_concurrent_sessions=self.config.max_concurrent_sessions,
                state_store=store,
            )
        return self._session_manager

    @staticmethod
    def _compute_retry_delay(base_delay: float, backoff: str, attempt: int) -> float:
        """Compute retry delay based on backoff strategy.

        Args:
            base_delay: Base delay in seconds
            backoff: Strategy: fixed, linear, exponential
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        if backoff == "linear":
            return base_delay * (attempt + 1)
        if backoff == "exponential":
            return base_delay * (2**attempt)
        # fixed
        return base_delay

    async def run(
        self,
        workflow_path: str,
        initial_state: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Execute a workflow from a YAML file.

        Args:
            workflow_path: Path to the YAML workflow file
            initial_state: Optional initial state dictionary

        Returns:
            WorkflowResult with final state and step results
        """
        from agentrails.display import DisplayManager
        from agentrails.dsl_parser import parse_workflow
        from agentrails.state import WorkflowState
        from agentrails.utils import get_logger

        start_time = time.time()

        # Parse workflow
        workflow = parse_workflow(workflow_path)
        workflow_id = workflow.name
        run_id = str(uuid.uuid4())

        # Initialize state
        state = WorkflowState(initial_state or {})

        # Create display manager
        display = DisplayManager(workflow_id, run_id)
        display.workflow_header()

        # Get services
        store = await self._get_state_store()
        session_manager = await self._get_session_manager()
        session_manager.set_workflow_context(workflow_id, run_id)
        logger = get_logger("agentrails.engine")

        # Create event log
        event_log = EventLog(workflow_id, run_id)

        # Emit workflow_started event
        # Include workflow hash for schema drift detection
        workflow_hash = EventLog.hash_workflow(workflow_path)
        event = EventLog.create_event(
            workflow_id,
            run_id,
            "workflow_started",
            data={"workflow_name": workflow_id, "workflow_hash": workflow_hash},
        )
        event_log.append(event)
        await store.append_event(event)

        # Save initial state
        await store.save_state(workflow_id, run_id, state.snapshot(), workflow_name=workflow_id)

        # Initialize execution tracking
        completed: set[str] = set()
        step_results: dict[str, StepResult] = {}
        total_steps = len(workflow.steps)

        # Execute steps
        result = await self._execute_steps(
            workflow=workflow,
            workflow_id=workflow_id,
            run_id=run_id,
            state=state,
            completed=completed,
            step_results=step_results,
            event_log=event_log,
            store=store,
            session_manager=session_manager,
            logger=logger,
            display=display,
            total_steps=total_steps,
        )

        workflow_status = result["status"]
        workflow_error = result["error"]
        state = result["state"]
        completed = result["completed"]
        step_results = result["step_results"]

        # Emit workflow completion event
        duration = time.time() - start_time
        event_type = "workflow_completed" if workflow_status == "completed" else "workflow_failed"
        event = EventLog.create_event(
            workflow_id,
            run_id,
            event_type,
            data={
                "status": workflow_status,
                "error": workflow_error,
                "duration": duration,
                "steps_completed": len(completed),
                "steps_total": total_steps,
            },
        )
        event_log.append(event)
        await store.append_event(event)

        # Update run status
        await store.save_state(
            workflow_id, run_id, state.snapshot(), workflow_name=workflow_id, status=workflow_status
        )

        # Display summary
        display.workflow_completed(len(completed), len(step_results) - len(completed), duration)
        display.workflow_summary(
            status=workflow_status,
            failed_step=None
            if workflow_status == "completed"
            else self._find_failed_step(step_results),
            error=workflow_error,
            duration=duration,
            steps_completed=len(completed),
            steps_failed=len(
                [r for r in step_results.values() if r.status in ("failed", "timeout")]
            ),
            steps_pending=total_steps - len(completed),
        )

        return WorkflowResult(
            workflow_id=workflow_id,
            run_id=run_id,
            status=workflow_status,
            final_state=state,
            step_results=step_results,
            duration_seconds=duration,
            error=workflow_error,
        )

    async def resume(
        self,
        run_id: str,
    ) -> WorkflowResult:
        """Resume a workflow from a checkpoint.

        Args:
            run_id: ID of the run to resume

        Returns:
            WorkflowResult with final state and step results
        """
        from agentrails.display import DisplayManager
        from agentrails.utils import get_logger

        start_time = time.time()

        # Get store
        store = await self._get_state_store()

        # Find the workflow by looking up the run
        runs = await store.list_runs()
        run_info = None
        for run in runs:
            if run.run_id == run_id:
                run_info = run
                break

        if run_info is None:
            raise ValueError(f"Run not found: {run_id}")

        workflow_id = run_info.workflow_id

        # We need to find the workflow YAML - for now, assume it's in the working directory
        # or use the workflow_id as the filename
        workflow_path = None
        for ext in [".yaml", ".yml"]:
            candidate = self.working_directory / f"{workflow_id}{ext}"
            if candidate.exists():
                workflow_path = candidate
                break

        if workflow_path is None:
            # Try to find any workflow file with matching name
            for yaml_file in self.working_directory.glob("*.yaml"):
                try:
                    from agentrails.dsl_parser import (  # pylint: disable=C0415
                        parse_workflow,
                    )

                    wf = parse_workflow(yaml_file)
                    if wf.name == workflow_id:
                        workflow_path = yaml_file
                        break
                except Exception:  # pylint: disable=W0718
                    continue

        if workflow_path is None:
            raise ValueError(
                f"Cannot find workflow YAML for '{workflow_id}' in {self.working_directory}"
            )

        # Parse workflow
        workflow = parse_workflow(workflow_path)

        # Create display manager and logger early for drift warning
        display = DisplayManager(workflow_id, run_id)
        display.workflow_header()
        logger = get_logger("agentrails.engine")

        # Load events and reconstruct state
        events = await store.load_events(workflow_id, run_id)
        event_log = EventLog(workflow_id, run_id)
        for event in events:
            event_log.append(event)

        # Check for schema drift
        workflow_yaml = workflow_path.read_text()
        drift_warning = event_log.check_schema_drift(workflow_yaml)
        if drift_warning:
            logger.warning(drift_warning)
            print(f"  ⚠️  {drift_warning}")

        # Replay to get state and completed steps
        replay_result = event_log.replay()
        state = replay_result["state"]
        completed = replay_result["completed_steps"]
        skipped = replay_result.get("skipped_steps", set())

        # Load step results
        step_results = await store.load_step_results(workflow_id, run_id)

        # Get services
        session_manager = await self._get_session_manager()
        session_manager.set_workflow_context(workflow_id, run_id)

        # Build step map
        total_steps = len(workflow.steps)

        logger.info(
            "Resuming workflow %s (run %s): %d/%d steps completed",
            workflow_id,
            run_id,
            len(completed),
            total_steps,
        )

        # Add skipped steps to completed set so they're not re-executed
        completed.update(skipped)

        # Execute remaining steps
        result = await self._execute_steps(
            workflow=workflow,
            workflow_id=workflow_id,
            run_id=run_id,
            state=state,
            completed=completed,
            step_results=step_results,
            event_log=event_log,
            store=store,
            session_manager=session_manager,
            logger=logger,
            display=display,
            total_steps=total_steps,
        )

        workflow_status = result["status"]
        workflow_error = result["error"]
        state = result["state"]
        completed = result["completed"]
        step_results = result["step_results"]

        # Emit workflow completion event
        duration = time.time() - start_time
        event_type = "workflow_completed" if workflow_status == "completed" else "workflow_failed"
        event = EventLog.create_event(
            workflow_id,
            run_id,
            event_type,
            data={
                "status": workflow_status,
                "error": workflow_error,
                "duration": duration,
                "steps_completed": len(completed),
                "steps_total": total_steps,
            },
        )
        event_log.append(event)
        await store.append_event(event)

        # Update run status
        await store.save_state(
            workflow_id, run_id, state.snapshot(), workflow_name=workflow_id, status=workflow_status
        )

        display.workflow_completed(
            len(completed),
            len([r for r in step_results.values() if r.status in ("failed", "timeout")]),
            duration,
        )
        display.workflow_summary(
            status=workflow_status,
            failed_step=None
            if workflow_status == "completed"
            else self._find_failed_step(step_results),
            error=workflow_error,
            duration=duration,
            steps_completed=len(completed),
            steps_failed=len(
                [r for r in step_results.values() if r.status in ("failed", "timeout")]
            ),
            steps_pending=total_steps - len(completed),
        )

        return WorkflowResult(
            workflow_id=workflow_id,
            run_id=run_id,
            status=workflow_status,
            final_state=state,
            step_results=step_results,
            duration_seconds=duration,
            error=workflow_error,
        )

    async def _execute_steps(
        self,
        workflow: Any,
        workflow_id: str,
        run_id: str,
        state: WorkflowState,
        completed: set[str],
        step_results: dict[str, StepResult],
        event_log: EventLog,
        store: Any,
        session_manager: Any,
        logger: Any,
        display: Any,
        total_steps: int,
    ) -> dict[str, Any]:
        """Execute workflow steps in DAG order.

        Args:
            workflow: Parsed workflow object with steps and DAG
            workflow_id: ID of the workflow
            run_id: ID of this run
            state: Current workflow state (mutated in place)
            completed: Set of completed step IDs (mutated in place)
            step_results: Dict of step results (mutated in place)
            event_log: Event log for recording events
            store: State store for persistence
            session_manager: Session manager for agent steps
            logger: Logger instance
            display: Display manager for progress output
            total_steps: Total number of steps in workflow

        Returns:
            Dict with keys: status, error, state, completed, step_results
        """
        from agentrails.steps.base import ExecutionContext, StepResult
        from agentrails.template import TemplateRenderError, evaluate_condition

        step_map: dict[str, BaseStep] = {step.id: step for step in workflow.steps}
        workflow_status: Literal["completed", "failed", "cancelled"] = "completed"
        workflow_error: str | None = None

        # Track steps that should be skipped due to conditional branching
        skipped_by_conditional: set[str] = set()

        try:
            while len(completed) < total_steps:
                # Get ready steps (returns step IDs)
                ready_ids = workflow.dag.ready_steps(completed)
                ready_ids = [s for s in ready_ids if s not in completed]

                if not ready_ids and len(completed) < total_steps:
                    # Deadlock - no ready steps but not all completed
                    pending = set(step_map.keys()) - completed
                    workflow_error = f"Deadlock: no ready steps, pending: {pending}"
                    workflow_status = "failed"
                    logger.error(workflow_error)
                    break

                # Execute ready steps sequentially (Sprint 4 - no concurrency)
                for step_id in ready_ids:
                    step = step_map[step_id]

                    # Skip if this step was excluded by a ConditionalStep
                    if step_id in skipped_by_conditional:
                        completed.add(step.id)
                        display.step_skipped(step.id, len(completed), total_steps)
                        event = EventLog.create_event(
                            workflow_id,
                            run_id,
                            "step_skipped",
                            step_id=step.id,
                            data={"reason": "Excluded by ConditionalStep"},
                        )
                        event_log.append(event)
                        await store.append_event(event)
                        step_results[step.id] = StepResult(
                            step_id=step.id,
                            status="skipped",
                            outputs={},
                            raw_output="",
                            duration_seconds=0.0,
                        )
                        await store.save_step_result(workflow_id, run_id, step_results[step.id])
                        continue

                    # Evaluate condition (but NOT for ConditionalStep).
                    # ConditionalStep uses 'if' field internally, not 'condition'.
                    if step.condition and not isinstance(step, ConditionalStep):
                        try:
                            condition_result = evaluate_condition(step.condition, state.snapshot())
                        except TemplateRenderError as e:
                            condition_result = False
                            logger.warning("Condition evaluation failed for %s: %s", step.id, e)

                        if not condition_result:
                            # Skip this step
                            completed.add(step.id)
                            display.step_skipped(step.id, len(completed), total_steps)
                            event = EventLog.create_event(
                                workflow_id,
                                run_id,
                                "step_skipped",
                                step_id=step.id,
                                data={"condition": step.condition},
                            )
                            event_log.append(event)
                            await store.append_event(event)
                            step_results[step.id] = StepResult(
                                step_id=step.id,
                                status="skipped",
                                outputs={},
                                raw_output="",
                                duration_seconds=0.0,
                            )
                            await store.save_step_result(workflow_id, run_id, step_results[step.id])
                            continue

                    # Execute step with retry logic
                    step_start = time.time()
                    display.step_started(step.id, len(completed) + 1, total_steps)

                    event = EventLog.create_event(
                        workflow_id, run_id, "step_started", step_id=step.id
                    )
                    event_log.append(event)
                    await store.append_event(event)

                    result = None
                    step_duration = 0.0
                    last_error = None

                    # Retry loop
                    for attempt in range(step.max_retries + 1):
                        try:
                            # Create execution context
                            context = ExecutionContext(
                                workflow_id=workflow_id,
                                run_id=run_id,
                                working_directory=self.working_directory,
                                logger=logger,
                                session_manager=session_manager,
                                state_store=store,
                            )

                            # Execute step
                            result = await step.execute(state, context)
                            step_duration = time.time() - step_start

                            if result.status == "success":
                                break  # Success - exit retry loop

                            # Check if this failure type should be retried
                            # Map: "failed" -> "error", "timeout" -> "timeout"
                            failure_type = "error" if result.status == "failed" else result.status
                            if failure_type not in step.retry_on:
                                break  # Don't retry this failure type

                            # Retry if attempts remain
                            if attempt < step.max_retries:
                                delay = self._compute_retry_delay(
                                    step.retry_delay_seconds,
                                    step.retry_backoff,
                                    attempt,
                                )
                                await asyncio.sleep(delay)

                                # Log retry event
                                event = EventLog.create_event(
                                    workflow_id,
                                    run_id,
                                    "step_retried",
                                    step_id=step.id,
                                    data={
                                        "attempt": attempt + 1,
                                        "max_retries": step.max_retries,
                                        "delay": delay,
                                        "backoff": step.retry_backoff,
                                        "previous_error": result.error,
                                    },
                                )
                                event_log.append(event)
                                await store.append_event(event)

                        except Exception as e:  # pylint: disable=W0718
                            last_error = str(e)
                            # Check if exception-type failures should be retried
                            if "timeout" not in step.retry_on and "error" not in step.retry_on:
                                break
                            if attempt < step.max_retries:
                                delay = self._compute_retry_delay(
                                    step.retry_delay_seconds,
                                    step.retry_backoff,
                                    attempt,
                                )
                                await asyncio.sleep(delay)
                                event = EventLog.create_event(
                                    workflow_id,
                                    run_id,
                                    "step_retried",
                                    step_id=step.id,
                                    data={
                                        "attempt": attempt + 1,
                                        "max_retries": step.max_retries,
                                        "delay": delay,
                                        "backoff": step.retry_backoff,
                                        "previous_error": last_error,
                                    },
                                )
                                event_log.append(event)
                                await store.append_event(event)

                    # Handle final result after retries exhausted
                    if result is None:
                        # All retries raised exceptions
                        result = StepResult(
                            step_id=step.id,
                            status="failed",
                            outputs={},
                            raw_output="",
                            duration_seconds=step_duration or (time.time() - step_start),
                            error=last_error or "Unknown error",
                        )

                    if result.status == "success":
                        # Merge outputs into state under step ID
                        # This makes outputs accessible as {{state.step_id.key}}
                        state = state.set(step.id, result.outputs)
                        # Emit state_updated event
                        event = EventLog.create_event(
                            workflow_id,
                            run_id,
                            "state_updated",
                            step_id=step.id,
                            data={
                                "key": step.id,
                                "value": result.outputs,
                                "state": state.snapshot(),
                            },
                        )
                        event_log.append(event)
                        await store.append_event(event)

                        # Validate state against schema (if defined)
                        if workflow.state_schema:
                            validation_errors = state.validate(workflow.state_schema)
                            if validation_errors:
                                workflow_status = "failed"
                                workflow_error = (
                                    f"State validation failed: {'; '.join(validation_errors)}"
                                )
                                logger.error(workflow_error)
                                step_results[step.id] = result
                                display.step_failed(
                                    step.id,
                                    len(completed) + 1,
                                    total_steps,
                                    step_duration,
                                    workflow_error,
                                )
                                event = EventLog.create_event(
                                    workflow_id,
                                    run_id,
                                    "step_failed",
                                    step_id=step.id,
                                    data={
                                        "error": workflow_error,
                                        "validation_errors": validation_errors,
                                    },
                                )
                                event_log.append(event)
                                await store.append_event(event)
                                await store.save_step_result(workflow_id, run_id, result)
                                break

                        completed.add(step.id)
                        step_results[step.id] = result
                        display.step_completed(step.id, len(completed), total_steps, step_duration)

                        event = EventLog.create_event(
                            workflow_id,
                            run_id,
                            "step_completed",
                            step_id=step.id,
                            data={"duration": step_duration, "outputs": result.outputs},
                        )
                        event_log.append(event)
                        await store.append_event(event)
                        await store.save_step_result(workflow_id, run_id, result)

                        # Checkpoint state
                        await store.save_state(
                            workflow_id, run_id, state.snapshot(), workflow_name=workflow_id
                        )

                        # Handle ConditionalStep - mark non-selected steps as skipped
                        if isinstance(step, ConditionalStep):
                            selected_steps = result.outputs.get("selected_steps", [])
                            # Find all steps that depend on this ConditionalStep
                            for other_id, other_step in step_map.items():
                                if (
                                    step.id in other_step.depends_on
                                    and other_id not in selected_steps
                                ):
                                    # Step depends on conditional and was not selected
                                    skipped_by_conditional.add(other_id)
                                    logger.info(
                                        "Step '%s' skipped by ConditionalStep '%s'",
                                        other_id,
                                        step.id,
                                    )

                    elif result.status in ("failed", "timeout"):
                        # Retries exhausted or failure type not retryable
                        workflow_status = "failed"
                        workflow_error = result.error or f"Step {step.id} {result.status}"
                        step_results[step.id] = result
                        display.step_failed(
                            step.id,
                            len(completed) + 1,
                            total_steps,
                            step_duration,
                            workflow_error,
                        )

                        event = EventLog.create_event(
                            workflow_id,
                            run_id,
                            "step_failed",
                            step_id=step.id,
                            data={
                                "error": workflow_error,
                                "status": result.status,
                                "attempts": step.max_retries + 1,
                            },
                        )
                        event_log.append(event)
                        await store.append_event(event)
                        await store.save_step_result(workflow_id, run_id, result)
                        break

                if workflow_status == "failed":
                    break

        except Exception as e:  # pylint: disable=W0718
            workflow_status = "failed"
            workflow_error = f"Engine error: {e}"
            logger.exception(workflow_error)

        return {
            "status": workflow_status,
            "error": workflow_error,
            "state": state,
            "completed": completed,
            "step_results": step_results,
        }

    def _find_failed_step(self, step_results: dict[str, StepResult]) -> str | None:
        """Find the first failed step."""
        for step_id, result in step_results.items():
            if result.status in ("failed", "timeout"):
                return step_id
        return None

    async def close(self):
        """Clean up resources."""
        if self._state_store:
            await self._state_store.close()
        if self._session_manager:
            # SessionManager doesn't have a close method in Sprint 3
            pass
