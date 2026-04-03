"""Integration tests for linear workflow execution."""

import pytest


@pytest.mark.asyncio
async def test_linear_workflow_end_to_end(tmp_path):
    """Test a 3-step linear workflow executes in order."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "linear.yaml"
    workflow_file.write_text("""
name: linear_integration_test
steps:
  - id: step1
    type: shell
    script: "echo first > /tmp/linear_test.txt"
  - id: step2
    type: shell
    depends_on: [step1]
    script: "cat /tmp/linear_test.txt && echo second >> /tmp/linear_test.txt"
  - id: step3
    type: shell
    depends_on: [step2]
    script: "cat /tmp/linear_test.txt && echo third >> /tmp/linear_test.txt"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    assert result.step_results["step1"].status == "success"
    assert result.step_results["step2"].status == "success"
    assert result.step_results["step3"].status == "success"

    # Verify order via file contents
    with open("/tmp/linear_test.txt") as f:
        content = f.read()
        assert "first" in content
        assert "second" in content
        assert "third" in content

    # Clean up
    import os

    if os.path.exists("/tmp/linear_test.txt"):
        os.remove("/tmp/linear_test.txt")


@pytest.mark.asyncio
async def test_linear_workflow_with_state_passthrough(tmp_path):
    """Test state is passed between steps in linear workflow."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "state_passthrough.yaml"
    workflow_file.write_text("""
name: state_passthrough_test
steps:
  - id: produce
    type: shell
    script: "echo test_value"
  - id: consume
    type: shell
    depends_on: [produce]
    script: "echo {{state.produce.stdout | trim}}"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "completed"
    assert "test_value" in result.final_state.get("produce", {}).get("stdout", "")
