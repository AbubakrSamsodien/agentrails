"""Loop step implementation for repeat-until-conditional execution."""
# pylint: disable=C0301  # Error messages exceed line length

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

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

        for _iteration_num in range(self.max_iterations):
            iteration_outputs: dict[str, Any] = {}

            # Execute body steps
            for step in self.body:
                result = await step.execute(state, context)
                iteration_outputs[step.id] = result.outputs

                if result.status == "failed":
                    error = f"{step.id}: {result.error}"
                    break

            # Store iteration results
            iterations.append(iteration_outputs)

            # Check exit condition
            latest_state = {"latest": iteration_outputs, "iterations": iterations}
            try:
                rendered = render_template(self.until, latest_state)
                condition_value = eval(rendered, {"__builtins__": {}}, {})
                if condition_value:
                    break
            except Exception:
                pass  # Continue to next iteration

        duration = time.time() - start_time

        outputs = {
            "iterations": iterations,
            "iteration_count": len(iterations),
        }

        # Check if we exhausted max iterations without satisfying condition
        if len(iterations) >= self.max_iterations and error is None:
            # Check if condition is satisfied
            latest_state = {
                "latest": iterations[-1] if iterations else {},
                "iterations": iterations,
            }
            try:
                rendered = render_template(self.until, latest_state)
                condition_value = eval(rendered, {"__builtins__": {}}, {})
                if not condition_value:
                    error = f"Max iterations ({self.max_iterations}) reached without satisfying condition"
            except Exception:
                error = "Could not evaluate until condition"

        return StepResult(
            step_id=self.id,
            status="failed" if error else "success",
            outputs=outputs,
            raw_output="",
            duration_seconds=duration,
            error=error,
        )
