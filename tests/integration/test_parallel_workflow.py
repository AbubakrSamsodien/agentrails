"""Integration tests for parallel workflow execution."""

import pytest


@pytest.mark.asyncio
async def test_parallel_workflow_end_to_end(tmp_path):
    """Test parallel branches execute concurrently and merge."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "parallel.yaml"
    workflow_file.write_text("""
name: parallel_integration_test
steps:
  - id: setup
    type: shell
    script: "echo setup_done > /tmp/parallel_setup.txt"
  - id: tests
    type: parallel_group
    depends_on: [setup]
    branches:
      - id: unit
        type: shell
        script: "echo unit_passed"
      - id: lint
        type: shell
        script: "echo lint_passed"
  - id: deploy
    type: shell
    depends_on: [tests]
    script: "cat /tmp/parallel_setup.txt && echo deploy_ready"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    assert result.step_results["setup"].status == "success"
    assert result.step_results["tests"].status == "success"
    assert result.step_results["deploy"].status == "success"

    # Verify parallel branch results are accessible
    tests_outputs = result.step_results["tests"].outputs
    assert "branches" in tests_outputs
    assert "unit" in tests_outputs["branches"]
    assert "lint" in tests_outputs["branches"]

    # Clean up
    import os

    if os.path.exists("/tmp/parallel_setup.txt"):
        os.remove("/tmp/parallel_setup.txt")


@pytest.mark.asyncio
async def test_parallel_workflow_merge_strategy(tmp_path):
    """Test parallel group with list_append merge strategy."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "parallel_merge.yaml"
    workflow_file.write_text("""
name: parallel_merge_test
steps:
  - id: collect
    type: parallel_group
    merge_strategy: list_append
    branches:
      - id: branch1
        type: shell
        script: "echo item1"
      - id: branch2
        type: shell
        script: "echo item2"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    assert result.step_results["collect"].status == "success"
