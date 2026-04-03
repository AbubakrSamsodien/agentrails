"""Shell step implementation for executing shell commands."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentrails.output import OutputParseError, OutputParser
from agentrails.steps.base import BaseStep, ExecutionContext, StepResult
from agentrails.template import render_template

if TYPE_CHECKING:
    from agentrails.state import WorkflowState


class ShellStep(BaseStep):
    """Execute a shell command and capture output.

    YAML configuration:
        - id: run_tests
          type: shell
          script: "pytest -q"
          working_dir: "{{state.project_dir}}"
          env:
            PYTHONPATH: "./src"
          timeout: 300
          output_format: json
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        script: str,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ):
        """Initialize a shell step.

        Args:
            id: Unique step identifier
            script: Shell command to execute
            working_dir: Working directory (supports templates)
            env: Additional environment variables
            timeout: Timeout in seconds
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="shell", **kwargs)
        self.script = script
        self.working_dir = working_dir
        self.env = env or {}
        self.timeout = timeout

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute the shell command.

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with command output
        """
        start_time = time.time()

        # Render templates in script and working_dir
        rendered_script = render_template(self.script, state.snapshot())
        rendered_wd = None
        if self.working_dir:
            rendered_wd = render_template(self.working_dir, state.snapshot())

        working_directory = Path(rendered_wd) if rendered_wd else context.working_directory

        # Build environment
        env = {**os.environ, **self.env}

        try:
            proc = await asyncio.create_subprocess_shell(
                rendered_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )

            duration = time.time() - start_time
            return_code = proc.returncode or 0
            stdout_str = stdout.decode()
            stderr_str = stderr.decode()
            error: str | None = None

            outputs = {
                "return_code": return_code,
                "stdout": stdout_str,
                "stderr": stderr_str,
            }

            # Parse output for structured formats
            if self.output_format in ("json", "toml") and stdout_str.strip():
                try:
                    parsed = OutputParser.parse(stdout_str, self.output_format, self.output_schema)
                    outputs["parsed"] = parsed
                except OutputParseError as e:
                    error = f"Output parse error: {e}"
                    return_code = 1

            status = "success" if return_code == 0 else "failed"
            error = error or (None if return_code == 0 else f"Exit code {return_code}")

            return StepResult(
                step_id=self.id,
                status=status,
                outputs=outputs,
                raw_output=stdout.decode(),
                duration_seconds=duration,
                error=error,
            )

        except TimeoutError:
            duration = time.time() - start_time
            return StepResult(
                step_id=self.id,
                status="timeout",
                outputs={},
                raw_output="",
                duration_seconds=duration,
                error=f"Timeout after {self.timeout}s",
            )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "script": self.script,
                "working_dir": self.working_dir,
                "env": self.env,
                "timeout": self.timeout,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> ShellStep:
        """Deserialize step from dictionary."""
        return cls(
            id=data["id"],
            script=data["script"],
            working_dir=data.get("working_dir"),
            env=data.get("env"),
            timeout=data.get("timeout"),
            depends_on=data.get("depends_on", []),
            outputs=data.get("outputs", {}),
            condition=data.get("condition"),
            output_format=data.get("output_format", "text"),
            output_schema=data.get("output_schema"),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
        )
