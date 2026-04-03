"""Human step implementation for waiting for human input."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import TYPE_CHECKING, Any

from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class HumanInputTimeoutError(Exception):
    """Raised when human input times out."""


class HumanInputError(Exception):
    """Raised when human input is invalid or cannot be read."""


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
        timeout_seconds: int | None = None,
        **kwargs: Any,
    ):
        """Initialize a human step.

        Args:
            id: Unique step identifier
            message: Message to display to human
            input_schema: Optional JSON Schema for input validation
            timeout_seconds: Timeout in seconds (default: 300 = 5 minutes)
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="human", timeout_seconds=timeout_seconds, **kwargs)
        self.message = message
        self.input_schema = input_schema
        self.timeout = timeout_seconds or 300  # Default 5 minutes

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Wait for human input via stdin.

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with human input
        """
        start_time = time.time()

        # Render message
        rendered_message = render_template(self.message, state.snapshot())

        # Display the message
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"HUMAN INPUT REQUIRED: {self.id}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        print(rendered_message, file=sys.stderr)
        print(f"\n{'=' * 60}", file=sys.stderr)
        if self.input_schema:
            print(
                f"Expected input format (JSON): {json.dumps(self.input_schema, indent=2)}",
                file=sys.stderr,
            )
            print(file=sys.stderr)

        # Check if stdin is a TTY
        if not sys.stdin.isatty():
            # Non-interactive mode - try to read from stdin anyway (for piped input)
            context.logger.info(
                "HumanStep '%s': stdin is not a TTY. Reading piped input.",
                self.id,
            )

        print("Please enter your response as JSON, then press Enter:", file=sys.stderr)
        print("> ", end="", file=sys.stderr)
        sys.stderr.flush()

        try:
            # Read input with timeout
            input_task = asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            user_input = await asyncio.wait_for(input_task, timeout=self.timeout)
        except TimeoutError as e:
            raise HumanInputTimeoutError(
                f"Timeout waiting for human input after {self.timeout} seconds"
            ) from e

        user_input = user_input.strip()

        if not user_input:
            return StepResult(
                step_id=self.id,
                status="failed",
                outputs={"message": rendered_message},
                raw_output="",
                duration_seconds=time.time() - start_time,
                error="Empty input received",
            )

        # Parse JSON input
        try:
            parsed_input = json.loads(user_input)
        except json.JSONDecodeError as e:
            return StepResult(
                step_id=self.id,
                status="failed",
                outputs={"message": rendered_message, "raw_input": user_input},
                raw_output=user_input,
                duration_seconds=time.time() - start_time,
                error=f"Invalid JSON: {e}",
            )

        # Validate against schema if provided
        if self.input_schema:
            try:
                from jsonschema import ValidationError, validate  # pylint: disable=C0415

                validate(instance=parsed_input, schema=self.input_schema)
            except ImportError:
                context.logger.warning("jsonschema not installed, skipping validation")
            except ValidationError as e:
                return StepResult(
                    step_id=self.id,
                    status="failed",
                    outputs={
                        "message": rendered_message,
                        "raw_input": user_input,
                        "parsed_input": parsed_input,
                    },
                    raw_output=user_input,
                    duration_seconds=time.time() - start_time,
                    error=f"Schema validation failed: {e.message}",
                )

        print("✓ Input received and accepted", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

        return StepResult(
            step_id=self.id,
            status="success",
            outputs={"message": rendered_message, "input": parsed_input},
            raw_output=user_input,
            duration_seconds=time.time() - start_time,
        )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "message": self.message,
                "input_schema": self.input_schema,
                "timeout": self.timeout,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> HumanStep:
        """Deserialize step from dictionary."""
        return cls(
            id=data["id"],
            message=data.get("message", "Please provide input"),
            input_schema=data.get("input_schema"),
            timeout_seconds=data.get("timeout_seconds") or data.get("timeout"),
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            retry_delay_seconds=data.get("retry_delay_seconds", 5.0),
            retry_backoff=data.get("retry_backoff", "fixed"),
            retry_on=data.get("retry_on", ["error", "timeout"]),
        )
