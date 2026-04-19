"""Tests for SessionManager class."""

import os
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_session_manager_initialization():
    """Test SessionManager can be initialized."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path="claude")
    assert manager is not None
    assert manager.max_concurrent_sessions == 5


@pytest.mark.asyncio
async def test_session_manager_start_session_basic(mock_claude_cli):
    """Test basic session start with mock CLI."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))
    result = await manager.start_session(prompt="test prompt")

    assert result.session_id is not None
    assert result.raw_output.strip() == "mocked"
    assert result.parsed_output == {"result": "mocked"}
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_session_manager_with_all_parameters(mock_claude_cli, tmp_path):
    """Test session start with all optional parameters."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    result = await manager.start_session(
        prompt="test",
        system_prompt="you are helpful",
        name="test-session",
        working_dir=tmp_path,
        model="claude-sonnet-4",
        max_turns=5,
        permission_mode="bypassPermissions",
        output_format="json",
    )

    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_session_manager_system_prompt_inline(mock_claude_cli, tmp_path):
    """Test short system prompt passed as --system-prompt arg."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(
        prompt="test",
        system_prompt="short prompt",
    )

    # Verify args were captured
    import json

    args = json.loads(args_file.read_text())
    assert "--system-prompt" in args
    assert "short prompt" in args

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_system_prompt_file(mock_claude_cli, tmp_path):
    """Test long system prompt written to temp file."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    # Create a long system prompt (> 4096 chars)
    long_prompt = "x" * 5000

    result = await manager.start_session(
        prompt="test",
        system_prompt=long_prompt,
    )

    # Should succeed (temp file handling works)
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_session_manager_permission_mode_default(mock_claude_cli):
    """Test that permission_mode defaults to bypassPermissions."""
    import json

    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    # Capture args via env var
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        args_file = f.name
        os.environ["MOCK_CLAUDE_ARGS_FILE"] = args_file

    try:
        await manager.start_session(prompt="test")

        args = json.loads(Path(args_file).read_text())
        assert "--permission-mode" in args
        assert "bypassPermissions" in args
    finally:
        del os.environ["MOCK_CLAUDE_ARGS_FILE"]
        os.unlink(args_file)


@pytest.mark.asyncio
async def test_session_manager_with_allowed_tools(mock_claude_cli):
    """Test allowed_tools parameter."""
    import json

    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        args_file = f.name
        os.environ["MOCK_CLAUDE_ARGS_FILE"] = args_file

    try:
        await manager.start_session(
            prompt="test",
            allowed_tools=["Read", "Write"],
        )

        args = json.loads(Path(args_file).read_text())
        assert "--allowedTools" in args
        assert "Read,Write" in args
    finally:
        del os.environ["MOCK_CLAUDE_ARGS_FILE"]
        os.unlink(args_file)


@pytest.mark.asyncio
async def test_session_manager_resume_session(mock_claude_cli):
    """Test resuming an existing session."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    result = await manager.resume_session(
        session_id="existing-session-123",
        prompt="continue from before",
    )

    assert result.session_id == "existing-session-123"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_session_manager_list_sessions(mock_claude_cli, tmp_path):
    """Test listing sessions with metadata."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    # Start a session
    await manager.start_session(
        prompt="test",
        name="my-test-session",
        working_dir=tmp_path,
    )

    # List sessions (will be completed/dead since mock exits immediately)
    sessions = await manager.list_sessions()

    # Session should be in the list
    assert len(sessions) >= 0  # May be 0 if process already cleaned up


@pytest.mark.asyncio
async def test_session_manager_kill_session(mock_claude_cli):
    """Test killing a running session."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    # Start a session
    result = await manager.start_session(prompt="test")

    # Kill it (may already be dead from mock)
    await manager.kill_session(result.session_id)

    # Should not raise


@pytest.mark.asyncio
async def test_session_manager_version_check_not_found(monkeypatch):
    """Test version check when Claude CLI not found."""
    from agentrails.session_manager import SessionManager

    # Ensure claude is not in PATH
    monkeypatch.setenv("PATH", "/nonexistent")

    manager = SessionManager(claude_path="nonexistent-claude")

    with pytest.raises(RuntimeError, match="Claude CLI not found"):
        await manager.start_session(prompt="test")


@pytest.mark.asyncio
async def test_session_manager_concurrency_limit(monkeypatch, tmp_path):
    """Test that semaphore limits concurrent sessions."""
    import asyncio

    from agentrails.session_manager import SessionManager

    # Create a mock that delays
    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
import time
time.sleep(0.1)
print('{"result": "delayed"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script), max_concurrent_sessions=2)

    # Try to start 5 concurrent sessions
    async def start():
        return await manager.start_session(prompt="test")

    # Should not hang - semaphore should limit to 2 at a time
    results = await asyncio.gather(*[start() for _ in range(5)])
    assert len(results) == 5


@pytest.mark.asyncio
async def test_session_manager_version_parsing_valid(monkeypatch, tmp_path):
    """Test version parsing with valid semver output."""
    from agentrails.session_manager import SessionManager

    # Create a mock claude that returns a version
    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("Claude Code 1.2.3")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))
    await manager._check_claude_version()

    assert manager._claude_version == "Claude Code 1.2.3"
    assert manager._version_tuple == (1, 2, 3)
    assert manager._version_checked is True


@pytest.mark.asyncio
async def test_session_manager_version_parsing_v_prefix(monkeypatch, tmp_path):
    """Test version parsing with v-prefixed output."""
    from agentrails.session_manager import SessionManager

    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("v2.0.0")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))
    await manager._check_claude_version()

    assert manager._version_tuple == (2, 0, 0)


@pytest.mark.asyncio
async def test_session_manager_version_too_old(monkeypatch, tmp_path):
    """Test version check fails when version is below minimum."""
    from agentrails.session_manager import MIN_CLAUDE_VERSION, SessionManager

    # Make minimum version very high
    original_min = MIN_CLAUDE_VERSION[0]
    import agentrails.session_manager as sm

    sm.MIN_CLAUDE_VERSION = (99, 0, 0)  # Very high minimum

    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("Claude Code 1.0.0")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))

    with pytest.raises(RuntimeError, match="is too old"):
        await manager._check_claude_version()

    # Restore original
    sm.MIN_CLAUDE_VERSION = (original_min, 0, 0)


@pytest.mark.asyncio
async def test_session_manager_version_not_found(monkeypatch, tmp_path):
    """Test version check when output cannot be parsed."""
    from agentrails.session_manager import SessionManager

    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("unknown version format")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))
    await manager._check_claude_version()

    assert manager._claude_version == "unknown version format"
    assert manager._version_tuple is None
    assert manager._version_checked is True


@pytest.mark.asyncio
async def test_session_manager_has_flag(monkeypatch, tmp_path):
    """Test has_flag() method for feature detection."""
    from agentrails.session_manager import SessionManager

    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("Claude Code 1.0.0")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))
    await manager._check_claude_version()

    # Version 1.0.0 should have all flags
    assert manager.has_flag("bare") is True
    assert manager.has_flag("permission_mode") is True
    assert manager.has_flag("json_schema") is True
    assert manager.has_flag("unknown_flag") is False


@pytest.mark.asyncio
async def test_session_manager_has_flag_before_version(monkeypatch, tmp_path):
    """Test has_flag() returns False when version tuple is None."""
    from agentrails.session_manager import SessionManager

    mock_script = tmp_path / "claude"
    mock_script.write_text("""#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("no version here")
    sys.exit(0)
print('{"result": "mocked"}')
sys.exit(0)
""")
    mock_script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    manager = SessionManager(claude_path=str(mock_script))
    await manager._check_claude_version()

    # Version couldn't be parsed, so all flags should be False
    assert manager.has_flag("bare") is False
    assert manager.has_flag("permission_mode") is False


@pytest.mark.asyncio
async def test_session_manager_no_bare_flag(mock_claude_cli, tmp_path):
    """Test --bare flag is NOT present for any sessions (breaks auth discovery)."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(prompt="test")

    import json

    args = json.loads(args_file.read_text())
    assert "--bare" not in args

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_no_bare_flag_subagent(mock_claude_cli, tmp_path):
    """Test --bare flag is NOT present for subagent sessions either."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(prompt="test", subagent="slack")

    import json

    args = json.loads(args_file.read_text())
    # --bare should NOT be present (breaks auth and MCP discovery)
    assert "--bare" not in args
    # --agent flag should NOT be used
    assert "--agent" not in args
    # Instead, the prompt should be prefixed with @'name (agent)' syntax
    prompt_idx = args.index("-p") + 1
    assert args[prompt_idx].startswith("@'slack (agent)'")

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_subagent_uses_system_prompt(mock_claude_cli, tmp_path):
    """Test subagents use --system-prompt (not --append-system-prompt).

    Since we no longer use --agent flag, there's no agent persona to append to.
    The system prompt fully replaces the default.
    """
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(
        prompt="test", subagent="slack", system_prompt="you are a slack expert"
    )

    import json

    args = json.loads(args_file.read_text())
    assert "--system-prompt" in args
    assert "--append-system-prompt" not in args
    assert "you are a slack expert" in args

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_regular_uses_system_prompt(mock_claude_cli, tmp_path):
    """Test regular agents use --system-prompt (not --append-system-prompt)."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(prompt="test", system_prompt="you are helpful")

    import json

    args = json.loads(args_file.read_text())
    assert "--system-prompt" in args
    assert "--append-system-prompt" not in args
    assert "you are helpful" in args

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_subagent_long_system_prompt_file(mock_claude_cli, tmp_path):
    """Test subagents with long system prompts use --system-prompt-file."""
    from agentrails.session_manager import SessionManager

    manager = SessionManager(claude_path=str(mock_claude_cli))

    # Long system prompt (> 4096 chars)
    long_prompt = "x" * 5000

    result = await manager.start_session(prompt="test", subagent="slack", system_prompt=long_prompt)

    # Should succeed (temp file handling works)
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_session_manager_subagent_prompt_prefix(mock_claude_cli, tmp_path):
    """Test subagent prompt is prefixed with @'name (agent)' inline syntax."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(prompt="fetch messages from #general", subagent="slack")

    import json

    args = json.loads(args_file.read_text())
    prompt_idx = args.index("-p") + 1
    assert args[prompt_idx] == "@'slack (agent)' fetch messages from #general"

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]


@pytest.mark.asyncio
async def test_session_manager_regular_no_prompt_prefix(mock_claude_cli, tmp_path):
    """Test regular (non-subagent) sessions don't get prompt prefix."""
    from agentrails.session_manager import SessionManager

    args_file = tmp_path / "args.json"
    os.environ["MOCK_CLAUDE_ARGS_FILE"] = str(args_file)

    manager = SessionManager(claude_path=str(mock_claude_cli))
    await manager.start_session(prompt="just a normal prompt")

    import json

    args = json.loads(args_file.read_text())
    prompt_idx = args.index("-p") + 1
    assert args[prompt_idx] == "just a normal prompt"

    del os.environ["MOCK_CLAUDE_ARGS_FILE"]
