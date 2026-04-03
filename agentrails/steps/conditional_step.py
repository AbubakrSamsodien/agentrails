"""Conditional step implementation for if/then/else branching."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class ConditionalStep(BaseStep):
    """Evaluate a condition and enable/disable downstream steps.

    YAML configuration:
        - id: check_tests
          type: conditional
          depends_on: [tests]
          if: "{{state.tests.unit_tests.return_code == 0}}"
          then: [deploy]
          else: [fix_code]
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        condition: str,
        then: list[str] | None = None,
        else_: list[str] | None = None,
        **kwargs: Any,
    ):
        """Initialize a conditional step.

        Args:
            id: Unique step identifier
            condition: Template expression to evaluate
            then: Step IDs to enable if condition is true
            else_: Step IDs to enable if condition is false
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="conditional", condition=condition, **kwargs)
        self.then = then or []
        self.else_ = else_ or []

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Evaluate the condition.

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with branch decision
        """
        start_time = time.time()

        try:
            # Render and evaluate condition
            if self.condition is None:
                raise ValueError(f"ConditionalStep '{self.id}' has no condition")
            rendered = render_template(self.condition, state.snapshot())

            # Evaluate as Python expression
            condition_value = eval(rendered, {"__builtins__": {}}, {})

            branch_taken = "then" if condition_value else "else"
            selected_steps = self.then if condition_value else self.else_

            outputs = {
                "branch_taken": branch_taken,
                "condition_value": condition_value,
                "selected_steps": selected_steps,
            }

            return StepResult(
                step_id=self.id,
                status="success",
                outputs=outputs,
                raw_output=rendered,
                duration_seconds=time.time() - start_time,
                error=None,
            )

        except Exception as e:
            return StepResult(
                step_id=self.id,
                status="failed",
                outputs={},
                raw_output="",
                duration_seconds=time.time() - start_time,
                error=str(e),
            )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "then": self.then,
                "else": self.else_,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> ConditionalStep:
        """Deserialize step from dictionary."""
        return cls(
            id=data["id"],
            condition=data["condition"],
            then=data.get("then"),
            else_=data.get("else"),
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
        )
