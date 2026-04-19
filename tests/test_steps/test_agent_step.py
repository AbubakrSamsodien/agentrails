"""Tests for AgentStep class."""

from unittest.mock import AsyncMock

import pytest

from agentrails.state import WorkflowState
from agentrails.steps.agent_step import AgentStep
from agentrails.steps.base import ExecutionContext


def test_agent_step_initialization():
    """Test AgentStep can be initialized."""
    step = AgentStep(id="test", prompt="Hello")
    assert step.id == "test"
    assert step.prompt == "Hello"
    assert step.type == "agent"


def test_agent_step_with_all_fields():
    """Test AgentStep with all optional fields."""
    step = AgentStep(
        id="plan",
        prompt="Create a plan",
        system_prompt="You are helpful",
        subagent="code-reviewer",
        session_id="session-123",
        name="planning",
        model="claude-sonnet-4",
        max_turns=10,
        allowed_tools=["Read", "Write"],
        permission_mode="bypassPermissions",
        working_dir="./subdir",
        output_format="json",
        output_schema={"type": "object"},
        max_retries=2,
    )

    assert step.id == "plan"
    assert step.system_prompt == "You are helpful"
    assert step.subagent == "code-reviewer"
    assert step.session_id == "session-123"
    assert step.name == "planning"
    assert step.allowed_tools == ["Read", "Write"]


@pytest.mark.asyncio
async def test_agent_step_execute_success(tmp_path):
    """Test successful agent step execution with mocked SessionManager."""
    from agentrails.session_manager import SessionResult

    # Mock session manager
    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test-session",
        raw_output='{"result": {"plan": "do things"}}',
        parsed_output={"result": {"plan": "do things"}},
        exit_code=0,
        duration_seconds=5.0,
    )

    # Create context
    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(id="plan", prompt="Create a plan")
    result = await step.execute(WorkflowState({}), context)

    assert result.status == "success"
    assert result.step_id == "plan"
    assert "_session_id" in result.outputs
    assert result.outputs["_session_id"] == "test-session"


@pytest.mark.asyncio
async def test_agent_step_execute_with_template(tmp_path):
    """Test agent step with template rendering in prompt."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='{"result": "done"}',
        parsed_output={"result": "done"},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    # Prompt with template expression
    step = AgentStep(
        id="plan",
        prompt="Plan for {{state.feature_name}}",
    )

    state = WorkflowState({"feature_name": "authentication"})
    await step.execute(state, context)

    # Verify session manager was called with rendered prompt
    mock_session_manager.start_session.assert_called_once()
    call_args = mock_session_manager.start_session.call_args
    assert "authentication" in call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_agent_step_execute_with_system_prompt_template(tmp_path):
    """Test agent step with template rendering in system prompt."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='{"result": "done"}',
        parsed_output={"result": "done"},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(
        id="plan",
        prompt="Plan",
        system_prompt="You know about {{state.topic}}",
    )

    state = WorkflowState({"topic": "Python"})
    await step.execute(state, context)

    call_args = mock_session_manager.start_session.call_args
    assert "Python" in call_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_agent_step_execute_with_subagent_template(tmp_path):
    """Test agent step with template rendering in subagent field."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='{"result": "done"}',
        parsed_output={"result": "done"},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(
        id="notify",
        prompt="Send notification",
        subagent="{{state.target_agent}}",
    )

    state = WorkflowState({"target_agent": "slack"})
    await step.execute(state, context)

    call_args = mock_session_manager.start_session.call_args
    assert call_args.kwargs["subagent"] == "slack"


@pytest.mark.asyncio
async def test_agent_step_execute_passes_subagent_to_session_manager(tmp_path):
    """Test that subagent field is passed to session_manager.start_session()."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='{"result": "done"}',
        parsed_output={"result": "done"},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(
        id="notify",
        prompt="Send notification",
        subagent="jira",
    )

    state = WorkflowState({})
    await step.execute(state, context)

    call_args = mock_session_manager.start_session.call_args
    assert call_args.kwargs["subagent"] == "jira"


@pytest.mark.asyncio
async def test_agent_step_execute_json_output(tmp_path):
    """Test agent step with JSON output parsing."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='Here is the plan:\n```json\n{"title": "Plan A", "steps": ["a", "b"]}\n```',
        parsed_output={},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(
        id="plan",
        prompt="Plan",
        output_format="json",
    )

    result = await step.execute(WorkflowState({}), context)

    assert result.status == "success"
    assert "result" in result.outputs
    assert result.outputs["result"] == {"title": "Plan A", "steps": ["a", "b"]}


@pytest.mark.asyncio
async def test_agent_step_execute_json_with_schema(tmp_path):
    """Test agent step with JSON schema validation."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output='{"title": "Plan", "steps": ["a"]}',
        parsed_output={},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    }

    step = AgentStep(
        id="plan",
        prompt="Plan",
        output_format="json",
        output_schema=schema,
    )

    result = await step.execute(WorkflowState({}), context)

    assert result.status == "success"
    assert "result" in result.outputs


@pytest.mark.asyncio
async def test_agent_step_execute_parse_error(tmp_path):
    """Test agent step with JSON parse error."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output="This is not valid JSON at all",
        parsed_output={},
        exit_code=0,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(
        id="plan",
        prompt="Plan",
        output_format="json",
    )

    result = await step.execute(WorkflowState({}), context)

    # Should still succeed but include parse error in outputs
    assert result.status == "success"
    assert "parse_error" in result.outputs


@pytest.mark.asyncio
async def test_agent_step_execute_failure(tmp_path):
    """Test agent step with non-zero exit code."""
    from agentrails.session_manager import SessionResult

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.return_value = SessionResult(
        session_id="test",
        raw_output="Error occurred",
        parsed_output={},
        exit_code=1,
        duration_seconds=1.0,
    )

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(id="plan", prompt="Plan")
    result = await step.execute(WorkflowState({}), context)

    assert result.status == "failed"
    assert "Exit code 1" in result.error


@pytest.mark.asyncio
async def test_agent_step_execute_exception(tmp_path):
    """Test agent step with SessionManager exception."""
    mock_session_manager = AsyncMock()
    mock_session_manager.start_session.side_effect = RuntimeError("Connection failed")

    context = ExecutionContext(
        workflow_id="wf1",
        run_id="run1",
        working_directory=tmp_path,
        logger=None,
        session_manager=mock_session_manager,
        state_store=None,
    )

    step = AgentStep(id="plan", prompt="Plan")
    result = await step.execute(WorkflowState({}), context)

    assert result.status == "failed"
    assert "Connection failed" in result.error


def test_agent_step_serialize(tmp_path):
    """Test AgentStep serialization."""
    step = AgentStep(
        id="plan",
        prompt="Create a plan",
        system_prompt="Be helpful",
        subagent="slack",
        name="planning",
    )

    data = step.serialize()

    assert data["id"] == "plan"
    assert data["type"] == "agent"
    assert data["prompt"] == "Create a plan"
    assert data["system_prompt"] == "Be helpful"
    assert data["subagent"] == "slack"
    assert data["name"] == "planning"


def test_agent_step_deserialize():
    """Test AgentStep deserialization."""
    data = {
        "id": "plan",
        "type": "agent",
        "prompt": "Create a plan",
        "system_prompt": "Be helpful",
        "subagent": "jira",
        "name": "planning",
        "model": "claude-sonnet-4",
        "max_turns": 10,
        "allowed_tools": ["Read"],
        "permission_mode": "bypassPermissions",
        "working_dir": ".",
        "depends_on": [],
        "output_format": "json",
        "max_retries": 2,
    }

    step = AgentStep.deserialize(data)

    assert step.id == "plan"
    assert step.prompt == "Create a plan"
    assert step.system_prompt == "Be helpful"
    assert step.subagent == "jira"
    assert step.name == "planning"
    assert step.model == "claude-sonnet-4"
    assert step.max_turns == 10
    assert step.allowed_tools == ["Read"]


def test_agent_step_serialize_deserialize_roundtrip():
    """Test AgentStep serialize/deserialize roundtrip."""
    original = AgentStep(
        id="plan",
        prompt="Plan",
        system_prompt="Helpful",
        subagent="gitlab",
        name="planning",
        model="claude-sonnet-4",
        max_turns=5,
    )

    data = original.serialize()
    restored = AgentStep.deserialize(data)

    assert restored.id == original.id
    assert restored.prompt == original.prompt
    assert restored.system_prompt == original.system_prompt
    assert restored.subagent == original.subagent
    assert restored.name == original.name
    assert restored.model == original.model


@pytest.mark.asyncio
async def test_agent_step_schema_injection_json(tmp_path, mock_claude_cli):
    """Test that JSON schema is auto-injected into system prompt."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="plan",
        prompt="Create a plan",
        output_format="json",
        output_schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_default_system_prompt=None,
        workflow_name="test_workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    assert "--system-prompt" in args
    system_prompt = args[args.index("--system-prompt") + 1]

    # Check schema injection
    assert "# Required output format" in system_prompt
    assert "valid JSON conforming to this schema" in system_prompt
    assert '"title"' in system_prompt
    assert '"type": "string"' in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_schema_injection_toml(tmp_path, mock_claude_cli):
    """Test that TOML schema is auto-injected into system prompt."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="config",
        prompt="Create config",
        output_format="toml",
        output_schema={"type": "object"},
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_default_system_prompt=None,
        workflow_name="test_workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    assert "# Required output format" in system_prompt
    assert "valid TOML conforming to this schema" in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_no_schema_format_only(tmp_path, mock_claude_cli):
    """Test format-only instruction when no schema defined."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="simple",
        prompt="Do something",
        output_format="json",
        output_schema=None,
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_name="test_workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    assert "# Required output format" in system_prompt
    assert "valid JSON" in system_prompt
    assert "conforming to this schema" not in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_text_format_no_injection(tmp_path, mock_claude_cli):
    """Test no schema injection for text output format."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="text_step",
        prompt="Write text",
        output_format="text",
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_name="test_workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    assert "# Required output format" not in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_pipeline_context_first_step(tmp_path, mock_claude_cli):
    """Test pipeline context for first step (no dependencies)."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="first",
        prompt="Start",
        depends_on=[],
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_name="my_workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    assert "# Pipeline context" in system_prompt
    assert "- Workflow: my_workflow" in system_prompt
    assert "- Current step: first" in system_prompt
    assert "- Steps completed: none" in system_prompt
    assert "- This step depends on: nothing (first step)" in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_pipeline_context_with_deps(tmp_path, mock_claude_cli):
    """Test pipeline context with completed steps and dependencies."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="deploy",
        prompt="Deploy",
        depends_on=["build", "test"],
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_name="ci_cd",
        completed_steps={"build", "test", "lint"},
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    assert "- Workflow: ci_cd" in system_prompt
    assert "- Current step: deploy" in system_prompt
    assert "- Steps completed: build, lint, test" in system_prompt  # sorted
    assert "- This step depends on: build, test" in system_prompt

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_raw_system_prompt_only(tmp_path, mock_claude_cli):
    """Test raw_system_prompt bypasses all framework layers."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="custom",
        prompt="Custom task",
        system_prompt="You are a custom agent.",
        raw_system_prompt=True,
        output_format="json",
        output_schema={"type": "object"},
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
        workflow_default_system_prompt="Default",
        workflow_name="workflow",
        completed_steps=set(),
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    system_prompt = args[args.index("--system-prompt") + 1]

    # Only the step's system prompt should be present
    assert system_prompt == "You are a custom agent."
    assert "Tools and file operations" not in system_prompt  # No base prompt
    assert "Default" not in system_prompt  # No workflow default
    assert "# Required output format" not in system_prompt  # No schema injection
    assert "# Pipeline context" not in system_prompt  # No pipeline context

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_agent_step_raw_system_prompt_no_prompt(tmp_path, mock_claude_cli):
    """Test raw_system_prompt with no system_prompt results in empty prompt."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    import os

    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    step = AgentStep(
        id="bare",
        prompt="Task",
        raw_system_prompt=True,
        system_prompt=None,
    )

    from agentrails.state import WorkflowState
    from agentrails.steps.base import ExecutionContext

    state = WorkflowState({})
    context = ExecutionContext(
        workflow_id="wf123",
        run_id="run456",
        working_directory=tmp_path,
        logger=None,
        session_manager=SessionManager(claude_path=str(mock_claude_cli)),
        state_store=None,
    )

    await step.execute(state, context)

    import json

    args = json.loads(args_file.read_text())
    # --system-prompt should not be present if prompt is empty
    assert "--system-prompt" not in args

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]
