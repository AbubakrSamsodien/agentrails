"""Loop step implementation for repeat-until-conditional execution."""
# pylint: disable=C0301  # Error messages exceed line length

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import TemplateRenderError, evaluate_condition

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class LoopStep(BaseStep):
    """Repeat sub-steps until a condition is met or max iterations reached.

    YAML configuration:
        - id: retry_loop
          type: loop
          depends_on: [initial_attempt]
          max_iterations: 5
          until: "{{state.retry_loop.latest.return_code == 0}}"
          body:
            - id: fix
              type: agent
              prompt: "Fix the failing tests"
            - id: retest
              type: shell
              script: "pytest -q"
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        body: list[BaseStep],
        until: str,
        max_iterations: int = 5,
        **kwargs: Any,
    ):
        """Initialize a loop step.

        Args:
            id: Unique step identifier
            body: Steps to execute in each iteration
            until: Condition template expression to check after each iteration
            max_iterations: Maximum number of iterations
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="loop", **kwargs)
        self.body = body
        self.until = until
        self.max_iterations = max_iterations

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute the loop.

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with iteration outputs
        """
        start_time = time.time()
        iterations: list[dict[str, Any]] = []
        error: str | None = None
        latest_outputs: dict[str, Any] = {}

        for iteration_num in range(self.max_iterations):
            iteration_outputs: dict[str, Any] = {}
            iteration_error: str | None = None

            # Execute body steps
            for step in self.body:
                result = await step.execute(state, context)
                iteration_outputs[step.id] = result.outputs

                if result.status == "failed":
                    iteration_error = f"{step.id}: {result.error}"
                    break

            # Store iteration results
            iterations.append(iteration_outputs)
            latest_outputs = iteration_outputs

            # Update state with current iteration results so condition can access them
            # This makes state.{loop_id}.latest, state.{loop_id}.iterations, and state.{loop_id}.iteration_count available
            state = state.set(f"{self.id}.latest", latest_outputs)
            state = state.set(f"{self.id}.iterations", iterations)
            state = state.set(f"{self.id}.iteration_count", len(iterations))

            # Check exit condition against full workflow state
            try:
                if evaluate_condition(self.until, state.snapshot()):
                    # Condition satisfied - clear any iteration errors and exit successfully
                    error = None
                    break
            except TemplateRenderError as e:
                context.logger.warning(
                    "Iteration %d: condition evaluation failed: %s. Continuing.",
                    iteration_num + 1,
                    e,
                )

            # If body step failed, record error for potential retry
            # This error will be cleared if a later iteration succeeds
            if iteration_error:
                error = iteration_error

        duration = time.time() - start_time

        # Return outputs - engine will wrap under step ID
        outputs = {
            "latest": latest_outputs,
            "iterations": iterations,
            "iteration_count": len(iterations),
        }

        # Check if we exhausted max iterations without satisfying condition
        if len(iterations) >= self.max_iterations and error is None:
            try:
                if not evaluate_condition(self.until, state.snapshot()):
                    error = f"Max iterations ({self.max_iterations}) reached without satisfying condition"
            except TemplateRenderError as e:
                error = f"Could not evaluate until condition: {e}"

        return StepResult(
            step_id=self.id,
            status="failed" if error else "success",
            outputs=outputs,
            raw_output="",
            duration_seconds=duration,
            error=error,
        )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "body": [step.serialize() for step in self.body],
                "until": self.until,
                "max_iterations": self.max_iterations,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> LoopStep:
        """Deserialize step from dictionary."""
        # Lazy import to avoid circular dependency with dsl_parser
        from pathlib import Path  # pylint: disable=C0415

        from agentrails.dsl_parser import (  # pylint: disable=C0415
            WorkflowDefaults,
            _create_step,
        )

        defaults = WorkflowDefaults()
        yaml_dir = Path.cwd()  # Default for deserialization
        body = [
            _create_step(step_data, defaults, set(), yaml_dir) for step_data in data.get("body", [])
        ]

        return cls(
            id=data["id"],
            body=body,
            until=data.get("until", ""),
            max_iterations=data.get("max_iterations", 5),
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
            retry_delay_seconds=data.get("retry_delay_seconds", 5.0),
            retry_backoff=data.get("retry_backoff", "fixed"),
            retry_on=data.get("retry_on", ["error", "timeout"]),
        )
