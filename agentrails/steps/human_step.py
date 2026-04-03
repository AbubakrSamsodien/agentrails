"""Human step implementation for waiting for human input."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class HumanStep(BaseStep):
    """Pause workflow and wait for human input.

    YAML configuration:
        - id: approve_deploy
          type: human
          depends_on: [review]
          message: "Review the changes. Test results: {{state.tests}}"
          input_schema:
            type: object
            properties:
              approved: { type: boolean }
              comments: { type: string }
            required: [approved]
          timeout: 86400
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        message: str,
        input_schema: dict[str, Any] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ):
        """Initialize a human step.

        Args:
            id: Unique step identifier
            message: Message to display to human
            input_schema: Optional JSON Schema for input validation
            timeout: Timeout in seconds
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="human", timeout_seconds=timeout, **kwargs)
        self.message = message
        self.input_schema = input_schema
        self.timeout = timeout

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Wait for human input.

        This is a stub implementation. In a real implementation, this would:
        1. Persist the workflow state
        2. Send a notification to the human
        3. Wait for input (via CLI, API, or file)
        4. Validate input against schema
        5. Return the input as outputs

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with human input
        """
        start_time = time.time()

        # Render message
        rendered_message = render_template(self.message, state.snapshot())

        # Stub: In a real implementation, this would wait for actual human input
        # For now, we'll just return a placeholder
        context.logger.info(f"Human step '{self.id}' waiting for input: {rendered_message}")

        # TODO: Implement actual human input mechanism
        # Options:
        # 1. Read from stdin (for CLI interactive mode)
        # 2. Poll a file for input
        # 3. Wait for API callback
        # 4. Use a message queue

        return StepResult(
            step_id=self.id,
            status="success",
            outputs={"message": rendered_message, "input": None},
            raw_output=rendered_message,
            duration_seconds=time.time() - start_time,
            error="Human input not implemented - stub implementation",
        )
