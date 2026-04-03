"""Integration tests for conditional workflow execution."""

import pytest


@pytest.mark.asyncio
async def test_conditional_workflow_then_branch(tmp_path):
    """Test conditional workflow takes 'then' branch when condition is true."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "conditional_then.yaml"
    workflow_file.write_text("""
name: conditional_then_test
steps:
  - id: check
    type: shell
    script: "echo success=true"
  - id: branch
    type: conditional
    depends_on: [check]
    if: "{{'success' in state.stdout}}"
    then: [success_path]
    else: [failure_path]
  - id: success_path
    type: shell
    depends_on: [branch]
    script: "echo took_then_branch"
  - id: failure_path
    type: shell
    depends_on: [branch]
    script: "echo took_else_branch"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    # then branch should run
    assert result.step_results["success_path"].status == "success"
    # else branch should be skipped
    assert result.step_results["failure_path"].status == "skipped"


@pytest.mark.asyncio
async def test_conditional_workflow_else_branch(tmp_path):
    """Test conditional workflow takes 'else' branch when condition is false."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "conditional_else.yaml"
    workflow_file.write_text("""
name: conditional_else_test
steps:
  - id: check
    type: shell
    script: "echo failure=true"
  - id: branch
    type: conditional
    depends_on: [check]
    if: "{{'success' in state.stdout}}"
    then: [success_path]
    else: [failure_path]
  - id: success_path
    type: shell
    depends_on: [branch]
    script: "echo took_then_branch"
  - id: failure_path
    type: shell
    depends_on: [branch]
    script: "echo took_else_branch"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    # then branch should be skipped
    assert result.step_results["success_path"].status == "skipped"
    # else branch should run
    assert result.step_results["failure_path"].status == "success"
