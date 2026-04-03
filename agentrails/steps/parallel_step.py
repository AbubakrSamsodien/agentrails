"""Parallel group step implementation for concurrent branch execution."""
# pylint: disable=cyclic-import

from __future__ import annotations

import asyncio
import time
from typing import Any

from agentrails.state import MergeStrategy, WorkflowState
from agentrails.steps.base import BaseStep, ExecutionContext, StepResult


class ParallelGroupStep(BaseStep):
    """Execute multiple sub-steps concurrently.

    YAML configuration:
        - id: tests
          type: parallel_group
          depends_on: [implement]
          max_concurrency: 4
          fail_fast: false
          merge_strategy: list_append
          branches:
            - id: unit_tests
              type: shell
              script: "pytest -q tests/unit"
            - id: integration_tests
              type: shell
              script: "pytest -q tests/integration"
    """

    def __init__(
        self,
        id: str,  # noqa: A002
        branches: list[BaseStep],
        max_concurrency: int = 4,
        fail_fast: bool = False,
        merge_strategy: str = "overwrite",
        **kwargs: Any,
    ):
        """Initialize a parallel group step.

        Args:
            id: Unique step identifier
            branches: List of step instances to execute in parallel
            max_concurrency: Maximum concurrent branches
            fail_fast: If True, cancel remaining branches on first failure
            merge_strategy: How to merge branch outputs
            **kwargs: Additional arguments for BaseStep
        """
        super().__init__(id=id, type="parallel_group", **kwargs)
        self.branches = branches
        self.max_concurrency = max_concurrency
        self.fail_fast = fail_fast
        self.merge_strategy = MergeStrategy(merge_strategy)

    async def execute(self, state: WorkflowState, context: ExecutionContext) -> StepResult:
        """Execute all branches concurrently.

        Args:
            state: Current workflow state
            context: Execution context

        Returns:
            StepResult with merged branch outputs
        """
        start_time = time.time()
        semaphore = asyncio.Semaphore(self.max_concurrency)
        branch_results: dict[str, StepResult] = {}
        errors: list[str] = []

        async def run_branch(branch: BaseStep) -> tuple[str, StepResult]:
            async with semaphore:
                if self.fail_fast and errors:
                    # Skip if fail_fast and another branch already failed
                    return branch.id, StepResult(
                        step_id=branch.id,
                        status="skipped",
                        outputs={},
                        raw_output="",
                        duration_seconds=0,
                        error="Cancelled due to fail_fast",
                    )

                result = await branch.execute(state, context)
                return branch.id, result

        # Run all branches concurrently
        tasks = [run_branch(branch) for branch in self.branches]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for item in completed:
            if isinstance(item, Exception):
                errors.append(str(item))
            else:
                branch_id: str
                result: Any
                branch_id, result = item
                branch_results[branch_id] = result
                if result.status == "failed":
                    errors.append(f"{branch_id}: {result.error}")
                    if self.fail_fast:
                        break

        duration = time.time() - start_time

        # Merge outputs
        outputs = {"branches": {}}
        merged_state = WorkflowState({})

        for branch_id, result in branch_results.items():
            outputs["branches"][branch_id] = result.outputs
            if result.status == "success":
                try:
                    merged_state = merged_state.merge(
                        WorkflowState(result.outputs),
                        self.merge_strategy,
                    )
                except ValueError as e:
                    errors.append(str(e))

        overall_status = "success" if not errors else "failed"

        return StepResult(
            step_id=self.id,
            status=overall_status,
            outputs=outputs,
            raw_output="",
            duration_seconds=duration,
            error="\n".join(errors) if errors else None,
        )

    def serialize(self) -> dict[str, Any]:
        """Serialize step to dictionary."""
        data = super().serialize()
        data.update(
            {
                "branches": [b.serialize() for b in self.branches],
                "max_concurrency": self.max_concurrency,
                "fail_fast": self.fail_fast,
                "merge_strategy": self.merge_strategy.value,
            }
        )
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> ParallelGroupStep:
        """Deserialize step from dictionary."""
        # Lazy import to avoid circular dependency with dsl_parser
        from pathlib import Path  # pylint: disable=C0415

        from agentrails.dsl_parser import (  # pylint: disable=C0415
            WorkflowDefaults,
            _create_step,
        )

        defaults = WorkflowDefaults()
        yaml_dir = Path.cwd()  # Default for deserialization (not from YAML file)
        branches = [
            _create_step(branch_data, defaults, set(), yaml_dir)
            for branch_data in data.get("branches", [])
        ]

        return cls(
            id=data["id"],
            branches=branches,
            max_concurrency=data.get("max_concurrency", 4),
            fail_fast=data.get("fail_fast", False),
            merge_strategy=data.get("merge_strategy", "overwrite"),
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
