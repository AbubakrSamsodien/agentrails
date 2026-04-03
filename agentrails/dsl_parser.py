"""YAML DSL parser for workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agentrails.dag import DAG
from agentrails.steps.agent_step import AgentStep
from agentrails.steps.conditional_step import ConditionalStep
from agentrails.steps.human_step import HumanStep
from agentrails.steps.loop_step import LoopStep
from agentrails.steps.parallel_step import ParallelGroupStep
from agentrails.steps.shell_step import ShellStep

if TYPE_CHECKING:
    from agentrails.steps.base import BaseStep


@dataclass
class WorkflowDefaults:
    """Default settings for workflow steps."""

    system_prompt: str | None = None
    model: str | None = None
    output_format: str = "text"
    max_retries: int = 0
    timeout: int | None = None
    permission_mode: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    retry_delay_seconds: float = 5.0
    retry_backoff: str = "fixed"
    retry_on: list[str] = field(default_factory=lambda: ["error", "timeout"])


@dataclass
class Workflow:
    """Parsed workflow definition."""

    name: str
    steps: list[BaseStep]
    state_schema: dict[str, Any] | None
    dag: DAG
    defaults: WorkflowDefaults


class ValidationError(Exception):
    """Raised when workflow validation fails."""


def parse_workflow(yaml_path: str | Path) -> Workflow:
    """Parse a YAML workflow file into a Workflow object.

    Args:
        yaml_path: Path to the YAML workflow file

    Returns:
        Parsed and validated Workflow object

    Raises:
        ValidationError: If the workflow definition is invalid
    """
    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        raise ValidationError(f"Workflow file not found: {yaml_path}")

    with open(yaml_path, encoding="utf-8") as f:
        workflow_data = yaml.safe_load(f)

    if not workflow_data:
        raise ValidationError(f"Empty workflow file: {yaml_path}")

    # Validate required top-level fields
    if "name" not in workflow_data:
        raise ValidationError("Workflow must have a 'name' field")

    if "steps" not in workflow_data:
        raise ValidationError("Workflow must have a 'steps' field")

    # Parse defaults
    defaults = _parse_defaults(workflow_data.get("defaults", {}))

    # Parse state schema (optional)
    state_schema = workflow_data.get("state")

    # Parse steps (pass yaml_dir for resolving relative file paths)
    yaml_dir = yaml_path.parent
    steps = _parse_steps(workflow_data["steps"], defaults, yaml_dir)

    # Build and validate DAG
    dag = _build_dag(steps)

    return Workflow(
        name=workflow_data["name"],
        steps=steps,
        state_schema=state_schema,
        dag=dag,
        defaults=defaults,
    )


def _parse_defaults(defaults_data: dict[str, Any]) -> WorkflowDefaults:
    """Parse workflow defaults."""
    return WorkflowDefaults(
        system_prompt=defaults_data.get("system_prompt"),
        model=defaults_data.get("model"),
        output_format=defaults_data.get("output_format", "text"),
        max_retries=defaults_data.get("max_retries", 0),
        timeout=defaults_data.get("timeout"),
        permission_mode=defaults_data.get("permission_mode"),
        allowed_tools=defaults_data.get("allowed_tools", []),
        retry_delay_seconds=defaults_data.get("retry_delay_seconds", 5.0),
        retry_backoff=defaults_data.get("retry_backoff", "fixed"),
        retry_on=defaults_data.get("retry_on", ["error", "timeout"]),
    )


def _parse_steps(
    steps_data: list[dict[str, Any]], defaults: WorkflowDefaults, yaml_dir: Path
) -> list[BaseStep]:
    """Parse step definitions into step objects.

    Args:
        steps_data: List of step YAML data
        defaults: Workflow defaults
        yaml_dir: Directory containing the YAML file (for resolving relative paths)
    """
    # Track all step IDs for validation
    step_ids = set()

    # First pass: collect all step IDs
    _collect_step_ids(steps_data, step_ids)

    # Second pass: create step objects
    steps = []
    for step_data in steps_data:
        step = _create_step(step_data, defaults, step_ids, yaml_dir)
        steps.append(step)

    return steps


def _collect_step_ids(steps_data: list[dict[str, Any]], step_ids: set[str]) -> None:
    """Recursively collect all step IDs including nested steps."""
    for step_data in steps_data:
        if "id" not in step_data:
            raise ValidationError(f"Step missing 'id' field: {step_data}")

        step_id = step_data["id"]
        if step_id in step_ids:
            raise ValidationError(f"Duplicate step ID: '{step_id}'")
        step_ids.add(step_id)

        # Collect nested step IDs (parallel_group branches, loop body)
        if step_data.get("type") == "parallel_group":
            _collect_step_ids(step_data.get("branches", []), step_ids)
        elif step_data.get("type") == "loop":
            _collect_step_ids(step_data.get("body", []), step_ids)


def _create_step(
    step_data: dict[str, Any],
    defaults: WorkflowDefaults,
    step_ids: set[str],
    yaml_dir: Path,
) -> BaseStep:
    """Create a step object from YAML data.

    Args:
        step_data: Step YAML data
        defaults: Workflow defaults
        step_ids: Set of all step IDs for validation
        yaml_dir: Directory containing the YAML file (for resolving relative paths)
    """
    step_type = step_data.get("type", "shell")

    # Base step arguments
    base_kwargs = {
        "depends_on": step_data.get("depends_on", []),
        "outputs": step_data.get("outputs", {}),
        "output_format": step_data.get("output_format", defaults.output_format),
        "output_schema": step_data.get("output_schema"),
        "max_retries": step_data.get("max_retries", defaults.max_retries),
        "timeout_seconds": step_data.get("timeout", defaults.timeout),
        "retry_delay_seconds": step_data.get("retry_delay_seconds", defaults.retry_delay_seconds),
        "retry_backoff": step_data.get("retry_backoff", defaults.retry_backoff),
        "retry_on": step_data.get("retry_on", list(defaults.retry_on)),
    }

    # Handle conditional step's special fields
    if step_type == "conditional":
        condition = step_data.get("if")
        if not condition:
            raise ValidationError(f"Conditional step '{step_data.get('id')}' missing 'if' field")

        return ConditionalStep(
            id=step_data["id"],
            condition=condition,
            then=step_data.get("then", []),
            else_=step_data.get("else", []),
            **base_kwargs,
        )

    # Handle parallel group
    if step_type == "parallel_group":
        branches_data = step_data.get("branches", [])
        if not branches_data:
            raise ValidationError(f"Parallel group '{step_data['id']}' has no branches")

        # Recursively parse branches
        branches = [
            _create_step(branch_data, defaults, step_ids, yaml_dir) for branch_data in branches_data
        ]

        return ParallelGroupStep(
            id=step_data["id"],
            branches=branches,
            max_concurrency=step_data.get("max_concurrency", 4),
            fail_fast=step_data.get("fail_fast", False),
            merge_strategy=step_data.get("merge_strategy", "overwrite"),
            **base_kwargs,
        )

    # Handle loop
    if step_type == "loop":
        body_data = step_data.get("body", [])
        if not body_data:
            raise ValidationError(f"Loop step '{step_data['id']}' has no body")

        until = step_data.get("until")
        if not until:
            raise ValidationError(f"Loop step '{step_data['id']}' missing 'until' field")

        # Recursively parse body
        body = [
            _create_step(body_step_data, defaults, step_ids, yaml_dir)
            for body_step_data in body_data
        ]

        return LoopStep(
            id=step_data["id"],
            body=body,
            until=until,
            max_iterations=step_data.get("max_iterations", 5),
            **base_kwargs,
        )

    # Handle shell step
    if step_type == "shell":
        if "script" not in step_data:
            raise ValidationError(f"Shell step '{step_data['id']}' missing 'script' field")

        return ShellStep(
            id=step_data["id"],
            script=step_data["script"],
            working_dir=step_data.get("working_dir"),
            env=step_data.get("env", {}),
            timeout=step_data.get("timeout"),
            **base_kwargs,
        )

    # Handle agent step
    if step_type == "agent":
        if "prompt" not in step_data:
            raise ValidationError(f"Agent step '{step_data['id']}' missing 'prompt' field")

        # Handle system_prompt and system_prompt_file (mutually exclusive)
        system_prompt = step_data.get("system_prompt")
        system_prompt_file = step_data.get("system_prompt_file")

        if system_prompt and system_prompt_file:
            raise ValidationError(
                f"Agent step '{step_data['id']}' cannot have both 'system_prompt' "
                f"and 'system_prompt_file'"
            )

        # Load system_prompt_file if specified
        if system_prompt_file:
            prompt_file_path = yaml_dir / system_prompt_file
            if not prompt_file_path.exists():
                raise ValidationError(
                    f"System prompt file '{system_prompt_file}' not found for step "
                    f"'{step_data['id']}'"
                )
            with open(prompt_file_path, encoding="utf-8") as f:
                system_prompt = f.read()
        elif system_prompt is None:
            # Fall back to defaults.system_prompt
            system_prompt = defaults.system_prompt

        # Merge defaults for agent-specific fields
        permission_mode = step_data.get("permission_mode", defaults.permission_mode)
        allowed_tools = step_data.get("allowed_tools", defaults.allowed_tools)

        return AgentStep(
            id=step_data["id"],
            prompt=step_data["prompt"],
            system_prompt=system_prompt,
            session_id=step_data.get("session_id"),
            name=step_data.get("name"),
            model=step_data.get("model", defaults.model),
            max_turns=step_data.get("max_turns"),
            allowed_tools=allowed_tools,
            permission_mode=permission_mode,
            working_dir=step_data.get("working_dir", "."),
            **base_kwargs,
        )

    # Handle human step
    if step_type == "human":
        return HumanStep(
            id=step_data["id"],
            message=step_data.get("message", "Please provide input"),
            input_schema=step_data.get("input_schema"),
            **base_kwargs,
        )

    raise ValidationError(f"Unknown step type: '{step_type}'")


def _build_dag(steps: list[BaseStep]) -> DAG:
    """Build DAG from steps and validate dependencies."""
    dag = DAG()
    step_ids = {step.id for step in steps}

    # Add all step IDs as nodes
    for step in steps:
        dag.add_node(step.id)

    # Add edges for dependencies
    for step in steps:
        for dep_id in step.depends_on:
            if dep_id not in step_ids:
                raise ValidationError(
                    f"Step '{step.id}' depends on '{dep_id}', which does not exist"
                )
            dag.add_edge(dep_id, step.id)

    # Validate DAG (checks for cycles via topological sort)
    try:
        dag.topological_order()
    except Exception as e:
        raise ValidationError(f"Workflow contains a cycle: {e}") from e

    return dag
