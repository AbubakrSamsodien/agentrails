"""Base abstract class for all step types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


@dataclass
class ExecutionContext:
    """Context passed to steps during execution."""

    workflow_id: str
    run_id: str
    working_directory: Any  # pathlib.Path
    logger: Any  # logging.Logger
    session_manager: Any  # SessionManager
    state_store: Any  # StateStore


@dataclass
class StepResult:
    """Result of a step execution."""

    step_id: str
    status: Literal["success", "failed", "skipped", "timeout"]
    outputs: dict[str, Any]
    raw_output: str
    duration_seconds: float
    error: str | None = None


class BaseStep(ABC):
    """Abstract base class for all step types.

    Each step type must implement the execute() method and may
    override serialize()/deserialize() for custom serialization.
    """

    id: str
    type: str
    depends_on: list[str]
    outputs: dict[str, str]
    condition: str | None
    output_format: str
    output_schema: dict[str, Any] | None
    max_retries: int
    timeout_seconds: int | None
    retry_delay_seconds: float
    retry_backoff: str
    retry_on: list[str]

    def __init__(
        self,
        id: str,  # noqa: A002
        type: str,  # noqa: A002
        depends_on: list[str] | None = None,
        outputs: dict[str, str] | None = None,
        condition: str | None = None,
        output_format: str = "text",
        output_schema: dict[str, Any] | None = None,
        max_retries: int = 0,
        timeout_seconds: int | None = None,
        retry_delay_seconds: float = 5.0,
        retry_backoff: str = "fixed",
        retry_on: list[str] | None = None,
    ):
        """Initialize a step.

        Args:
            step_id: Unique step identifier
            step_type: Step type name
            depends_on: List of step IDs this step depends on
            outputs: Expected output fields (field_name -> type_name)
            condition: Optional condition template expression
            output_format: Output format (json, toml, text)
            output_schema: Optional JSON Schema for output validation
            max_retries: Number of retry attempts on failure
            timeout_seconds: Optional timeout in seconds
            retry_delay_seconds: Initial delay between retries (seconds)
            retry_backoff: Backoff strategy: fixed, linear, exponential
            retry_on: Which failure types trigger retry: error, timeout
        """
        self.id = id
        self.type = type
        self.depends_on = depends_on or []
        self.outputs = outputs or {}
        self.condition = condition
        self.output_format = output_format
        self.output_schema = output_schema
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.retry_backoff = retry_backoff
        self.retry_on = retry_on or ["error", "timeout"]

    @abstractmethod
    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute the step.

        Args:
            state: Current workflow state
            context: Execution context with services

        Returns:
            StepResult with status and outputs
        """

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary.

        Returns:
            Dictionary representation of step
        """
        return {
            "id": self.id,
            "type": self.type,
            "depends_on": self.depends_on,
            "outputs": self.outputs,
            "condition": self.condition,
            "output_format": self.output_format,
            "output_schema": self.output_schema,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "retry_delay_seconds": self.retry_delay_seconds,
            "retry_backoff": self.retry_backoff,
            "retry_on": self.retry_on,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> BaseStep:
        """Deserialize step from dictionary.

        Args:
            data: Dictionary representation of step

        Returns:
            Step instance
        """
        return cls(
            id=data["id"],
            type=data["type"],
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            condition=data.get("condition"),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
            retry_delay_seconds=data.get("retry_delay_seconds", 5.0),
            retry_backoff=data.get("retry_backoff", "fixed"),
            retry_on=data.get("retry_on", ["error", "timeout"]),
        )
