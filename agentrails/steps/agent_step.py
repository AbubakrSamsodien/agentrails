"""Agent step implementation for Claude CLI invocations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentrails.output import OutputParseError, OutputParser
from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class AgentStep(BaseStep):
    """Execute a Claude Code CLI agent with a prompt.

    YAML configuration:
        - id: plan
          type: agent
          description: "Generate implementation plan"
          prompt: |
            Analyze the codebase and create a plan for {{state.feature}}.
          system_prompt: |
            You are a senior software architect. Always respond with JSON.
          output_format: json
          output_schema:
            type: object
            properties:
              title: { type: string }
              steps: { type: array }
          session_id: null
          name: "planning"
          model: null
          max_turns: 10
          allowed_tools: []
          permission_mode: null
          working_dir: "."
          timeout: 600
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        prompt: str,
        system_prompt: str | None = None,
        session_id: str | None = None,
        name: str | None = None,
        model: str | None = None,
        max_turns: int | None = None,
        allowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        working_dir: str | None = None,
        **kwargs: Any,
    ):
        """Initialize an agent step.

        Args:
            id: Unique step identifier
            prompt: User prompt (supports templates)
            system_prompt: System prompt (supports templates)
            session_id: Session ID to resume (None = new session)
            name: Display name for session
            model: Model override
            max_turns: Maximum conversation turns
            allowed_tools: Pre-approved tools
            permission_mode: Permission mode
            working_dir: Working directory
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="agent", **kwargs)
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.name = name
        self.model = model
        self.max_turns = max_turns
        self.allowed_tools = allowed_tools or []
        self.permission_mode = permission_mode
        self.working_dir = working_dir

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute the agent step.

        Args:
            state: Current workflow state
            context: Execution context with SessionManager

        Returns:
            StepResult with agent output
        """
        # Render templates
        rendered_prompt = render_template(self.prompt, state.snapshot())
        rendered_system_prompt = None
        if self.system_prompt:
            rendered_system_prompt = render_template(self.system_prompt, state.snapshot())

        # Get session manager from context
        session_manager = context.session_manager

        try:
            result = await session_manager.start_session(
                prompt=rendered_prompt,
                system_prompt=rendered_system_prompt,
                session_id=self.session_id,
                name=self.name,
                model=self.model,
                max_turns=self.max_turns,
                allowed_tools=self.allowed_tools if self.allowed_tools else None,
                permission_mode=self.permission_mode,
                working_dir=context.working_directory / self.working_dir
                if self.working_dir
                else None,
                output_format=self.output_format,
                timeout=self.timeout_seconds,
            )

            # Extract structured output
            outputs = {
                "_session_id": result.session_id,
            }

            # Parse output using OutputParser for structured formats
            if self.output_format in ("json", "toml") and result.raw_output:
                try:
                    parsed = OutputParser.parse(
                        result.raw_output,
                        self.output_format,
                        self.output_schema,
                    )
                    outputs["result"] = parsed
                except OutputParseError as e:
                    # Parse failure - include error in result
                    outputs["parse_error"] = str(e)
                    outputs["raw_result"] = result.raw_output

            status = "success" if result.exit_code == 0 else "failed"

            return StepResult(
                step_id=self.id,
                status=status,
                outputs=outputs,
                raw_output=result.raw_output,
                duration_seconds=result.duration_seconds,
                error=None if status == "success" else f"Exit code {result.exit_code}",
            )

        except Exception as e:
            return StepResult(
                step_id=self.id,
                status="failed",
                outputs={},
                raw_output="",
                duration_seconds=0,
                error=str(e),
            )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "prompt": self.prompt,
                "system_prompt": self.system_prompt,
                "session_id": self.session_id,
                "name": self.name,
                "model": self.model,
                "max_turns": self.max_turns,
                "allowed_tools": self.allowed_tools,
                "permission_mode": self.permission_mode,
                "working_dir": self.working_dir,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> AgentStep:
        """Deserialize step from dictionary.

        Args:
            data: Dictionary representation of step

        Returns:
            AgentStep instance
        """
        return cls(
            id=data["id"],
            prompt=data["prompt"],
            system_prompt=data.get("system_prompt"),
            session_id=data.get("session_id"),
            name=data.get("name"),
            model=data.get("model"),
            max_turns=data.get("max_turns"),
            allowed_tools=data.get("allowed_tools", []),
            permission_mode=data.get("permission_mode"),
            working_dir=data.get("working_dir"),
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            condition=data.get("condition"),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
        )
