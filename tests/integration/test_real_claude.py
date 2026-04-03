"""Real Claude CLI integration tests (skip by default).

These tests require a real Claude CLI installation and valid credentials.
Run with: pytest -m realcli --run-real-cli
"""

import os

import pytest


@pytest.mark.realcli
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("RUN_REAL_CLI"),
    reason="Requires --run-real-cli flag or RUN_REAL_CLI=1 env var",
)
async def test_real_claude_cli_structured_output(tmp_state_dir):
    """Test actual Claude CLI invocation with structured JSON output.

    This test requires:
    - Claude CLI installed and on PATH
    - Valid Anthropic API key (ANTHROPIC_API_KEY env var)

    Run with: pytest -m realcli --run-real-cli
    """
    import tempfile
    from pathlib import Path

    from agentrails.config import Config
    from agentrails.engine import WorkflowRunner

    config = Config(state_dir=str(tmp_state_dir))

    # Create a simple workflow with an agent step
    workflow_content = """
name: real_claude_test
steps:
  - id: simple_question
    type: agent
    prompt: "What is 2+2? Respond with ONLY a JSON object: {\\\"answer\\\": <number>}"
    output_format: json
    output_schema:
      type: object
      properties:
        answer:
          type: number
      required: [answer]
    permission_mode: bypassPermissions
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(workflow_content)
        workflow_path = Path(f.name)

    try:
        runner = WorkflowRunner(config=config, working_directory=workflow_path.parent)
        result = await runner.run(str(workflow_path))
        await runner.close()

        assert result.status == "completed"
        assert result.step_results["simple_question"].status == "success"

        outputs = result.step_results["simple_question"].outputs
        assert "outputs" in outputs
        assert outputs["outputs"]["answer"] == 4
    finally:
        workflow_path.unlink()
