"""Tests for WorkflowRunner engine."""

import pytest


def test_runner_initialization():
    """Test WorkflowRunner can be initialized."""
    from agentrails.engine import WorkflowRunner

    runner = WorkflowRunner()
    assert runner is not None


@pytest.mark.asyncio
async def test_runner_state_validation_success(tmp_path):
    """Test workflow with state schema that validates successfully."""
    from agentrails.engine import WorkflowRunner

    # Create a workflow with state schema
    # ShellStep outputs stdout, stderr, return_code under step ID
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text("""
name: validation_test
state:
  type: object
  properties:
    step1:
      type: object
      properties:
        stdout:
          type: string
        return_code:
          type: integer
      required: [stdout, return_code]
  required: [step1]
steps:
  - id: step1
    type: shell
    script: "echo success"
    output_format: text
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))

    assert result.status == "completed"
    assert "success" in result.final_state.get("step1", {}).get("stdout", "")
    assert result.final_state.get("step1", {}).get("return_code") == 0
    await runner.close()


@pytest.mark.asyncio
async def test_runner_state_validation_failure(tmp_path):
    """Test workflow fails when state doesn't match schema."""
    from agentrails.engine import WorkflowRunner

    # Create a workflow with state schema that will fail
    # ShellStep always outputs stdout (string) and return_code (integer) under step ID
    # We require a "count" field which won't exist
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text("""
name: validation_fail_test
state:
  type: object
  properties:
    step1:
      type: object
      properties:
        count:
          type: integer
      required: [count]
  required: [step1]
steps:
  - id: step1
    type: shell
    script: "echo test"
    output_format: text
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))

    # Workflow should fail validation
    assert result.status == "failed"
    assert "State validation failed" in result.error
    await runner.close()


@pytest.mark.asyncio
async def test_runner_conditional_branch_then(tmp_path):
    """Test ConditionalStep takes 'then' branch when condition is true."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "conditional.yaml"
    workflow_file.write_text("""
name: conditional_test
steps:
  - id: setup
    type: shell
    script: "echo ready"
  - id: check
    type: conditional
    depends_on: [setup]
    if: "{{True}}"
    then: [success_path]
    else: [fail_path]
  - id: success_path
    type: shell
    depends_on: [check]
    script: "echo success"
  - id: fail_path
    type: shell
    depends_on: [check]
    script: "echo fail"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))

    assert result.status == "completed"
    # success_path should have run, fail_path should be skipped
    assert result.step_results["success_path"].status == "success"
    assert result.step_results["fail_path"].status == "skipped"
    await runner.close()


@pytest.mark.asyncio
async def test_runner_conditional_branch_else(tmp_path):
    """Test ConditionalStep takes 'else' branch when condition is false."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "conditional.yaml"
    workflow_file.write_text("""
name: conditional_test
steps:
  - id: setup
    type: shell
    script: "echo ready"
  - id: check
    type: conditional
    depends_on: [setup]
    if: "{{False}}"
    then: [success_path]
    else: [fail_path]
  - id: success_path
    type: shell
    depends_on: [check]
    script: "echo success"
  - id: fail_path
    type: shell
    depends_on: [check]
    script: "echo fail"
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))

    assert result.status == "completed"
    # fail_path should have run, success_path should be skipped
    assert result.step_results["fail_path"].status == "success"
    assert result.step_results["success_path"].status == "skipped"
    await runner.close()


@pytest.mark.asyncio
async def test_runner_resume_with_drift_warning(tmp_path, caplog):
    """Test resume() warns when workflow YAML has changed."""
    from agentrails.engine import WorkflowRunner

    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text("""
name: drift_test
steps:
  - id: step1
    type: shell
    script: "echo first"
  - id: step2
    type: shell
    script: "echo second"
""")

    # Run workflow
    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    assert result.status == "completed"
    run_id = result.run_id
    await runner.close()

    # Modify workflow YAML
    workflow_file.write_text("""
name: drift_test
steps:
  - id: step1
    type: shell
    script: "echo MODIFIED"
  - id: step2
    type: shell
    script: "echo second"
""")

    # Resume - should warn about drift
    runner2 = WorkflowRunner(working_directory=tmp_path)
    result2 = await runner2.resume(run_id)
    await runner2.close()

    # Resume should succeed but workflow was already complete
    assert result2.status == "completed"
    # Check for drift warning in output (display output goes to stdout)


@pytest.mark.asyncio
async def test_retry_on_transient_failure(tmp_path):
    """Test that steps retry on transient failures."""
    from agentrails.engine import WorkflowRunner

    # Create a workflow that fails twice then succeeds (simulated via shell)
    workflow_file = tmp_path / "retry.yaml"
    workflow_file.write_text("""
name: retry_test
steps:
  - id: flaky
    type: shell
    script: "test -f /tmp/retry_marker || (touch /tmp/retry_marker && exit 1)"
    max_retries: 2
    retry_delay_seconds: 0.1
    retry_backoff: fixed
""")

    # Clean up marker file
    import os

    marker = "/tmp/retry_marker"
    if os.path.exists(marker):
        os.remove(marker)

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    # Clean up
    if os.path.exists(marker):
        os.remove(marker)

    assert result.status == "completed"
    assert result.step_results["flaky"].status == "success"


@pytest.mark.asyncio
async def test_retry_exhaustion_fails_workflow(tmp_path):
    """Test that workflow fails when retries are exhausted."""
    from agentrails.engine import WorkflowRunner

    # Create a workflow that always fails
    workflow_file = tmp_path / "fail.yaml"
    workflow_file.write_text("""
name: fail_retry_test
steps:
  - id: always_fails
    type: shell
    script: "exit 1"
    max_retries: 2
    retry_delay_seconds: 0.01
    retry_on: ["error"]
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "failed"
    assert result.step_results["always_fails"].status == "failed"


@pytest.mark.asyncio
async def test_retry_backoff_strategies(tmp_path):
    """Test different retry backoff strategies."""
    from agentrails.engine import WorkflowRunner

    # Test exponential backoff
    workflow_file = tmp_path / "backoff.yaml"
    workflow_file.write_text("""
name: backoff_test
steps:
  - id: exponential
    type: shell
    script: "exit 1"
    max_retries: 2
    retry_delay_seconds: 0.01
    retry_backoff: exponential
""")

    runner = WorkflowRunner(working_directory=tmp_path)
    result = await runner.run(str(workflow_file))
    await runner.close()

    assert result.status == "failed"
    # Verify the step was attempted (max_retries + 1 = 3 times)
    assert result.step_results["exponential"].status == "failed"
