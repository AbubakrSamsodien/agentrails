"""Claude CLI subprocess manager for agent session lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentrails.storage import SessionInfo as StorageSessionInfo
from agentrails.storage import StateStore
from agentrails.utils import get_logger

logger = get_logger(__name__)

# Minimum supported Claude CLI version (semver)
MIN_CLAUDE_VERSION = (1, 0, 0)
# Version of record - when these features were added
VERSION_WITH_BARE_FLAG = (1, 0, 0)
VERSION_WITH_PERMISSION_MODE = (1, 0, 0)
VERSION_WITH_JSON_SCHEMA = (1, 0, 0)
VERSION_WITH_AGENT_FLAG = (1, 0, 0)


@dataclass
class SessionResult:
    """Result of a Claude CLI session execution."""

    session_id: str
    raw_output: str
    parsed_output: dict[str, Any]
    exit_code: int
    duration_seconds: float
    tokens_used: int | None = None
    claude_version: str | None = None


@dataclass
class SessionInfo:
    """Information about a Claude CLI session."""

    session_id: str
    name: str | None
    created_at: str
    last_used_at: str
    status: str  # active, completed, dead
    working_dir: str


class SessionManager:
    """Manages Claude CLI subprocess lifecycle.

    Handles starting, stopping, and resuming Claude Code CLI sessions
    with proper permission handling and structured output parsing.
    """

    def __init__(
        self,
        claude_path: str = "claude",
        max_concurrent_sessions: int = 5,
        state_store: StateStore | None = None,
    ):
        """Initialize session manager.

        Args:
            claude_path: Path to Claude CLI binary
            max_concurrent_sessions: Maximum concurrent sessions allowed
            state_store: Optional state store for session persistence
        """
        self.claude_path = claude_path
        self.max_concurrent_sessions = max_concurrent_sessions
        self._semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self._sessions: dict[str, asyncio.subprocess.Process] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._claude_version: str | None = None
        self._version_tuple: tuple[int, int, int] | None = None
        self._version_checked = False
        self._state_store = state_store
        self._workflow_id: str | None = None
        self._run_id: str | None = None

    def set_workflow_context(self, workflow_id: str, run_id: str) -> None:
        """Set workflow context for session persistence.

        Args:
            workflow_id: Current workflow ID
            run_id: Current run ID
        """
        self._workflow_id = workflow_id
        self._run_id = run_id

    async def _check_claude_version(self) -> None:
        """Check Claude CLI version and cache it.

        Raises:
            RuntimeError: If Claude CLI is not found or version is too old
        """
        if self._version_checked:
            return

        # Check if Claude CLI exists
        if not shutil.which(self.claude_path):
            raise RuntimeError(
                f"Claude CLI not found at '{self.claude_path}'. "
                "Install it from https://claude.ai/download"
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                self.claude_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            version_output = stdout.decode().strip() or stderr.decode().strip()

            # Parse semver from output (handles formats like "Claude Code 1.0.0", "v1.0.0", etc.)
            semver_match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_output)
            if semver_match:
                major, minor, patch = (
                    int(semver_match.group(1)),
                    int(semver_match.group(2)),
                    int(semver_match.group(3)),
                )
                self._claude_version = version_output
                self._version_tuple = (major, minor, patch)

                # Check minimum version
                if self._version_tuple < MIN_CLAUDE_VERSION:
                    min_ver_str = ".".join(map(str, MIN_CLAUDE_VERSION))
                    raise RuntimeError(
                        f"Claude CLI version {version_output} is too old. "
                        f"AgentRails requires >= {min_ver_str}. "
                        f"Upgrade: npm install -g @anthropic-ai/claude-cli"
                    )

                # Log warnings for missing features based on version
                if self._version_tuple < VERSION_WITH_BARE_FLAG:
                    logger.warning(
                        "Claude CLI %s may not support --bare flag. "
                        "Execution may be non-deterministic.",
                        version_output,
                    )
                if self._version_tuple < VERSION_WITH_PERMISSION_MODE:
                    logger.warning(
                        "Claude CLI %s may not support --permission-mode flag. "
                        "Falling back to --allowedTools or interactive prompts.",
                        version_output,
                    )
                if self._version_tuple < VERSION_WITH_JSON_SCHEMA:
                    logger.warning(
                        "Claude CLI %s may not support --json-schema flag. "
                        "Falling back to post-parse validation.",
                        version_output,
                    )
            else:
                # Could not parse version, but continue with warning
                self._claude_version = version_output
                self._version_tuple = None
                logger.warning(
                    "Could not parse Claude CLI version from '%s'. Proceeding with caution.",
                    version_output,
                )

            self._version_checked = True
            logger.info("Claude CLI version: %s", self._claude_version)

        except RuntimeError:
            # Re-raise RuntimeErrors (not found, too old)
            raise
        except Exception as e:
            logger.warning("Could not determine Claude CLI version: %s", e)
            self._version_checked = True
            self._claude_version = None
            self._version_tuple = None

    def has_flag(self, flag_name: str) -> bool:
        """Check if the detected Claude CLI version supports a specific flag.

        Args:
            flag_name: Name of the flag (e.g., 'bare', 'permission_mode', 'json_schema')

        Returns:
            True if the flag is supported, False otherwise
        """
        if self._version_tuple is None:
            return False

        # Map flag names to their minimum required versions
        flag_versions = {
            "bare": VERSION_WITH_BARE_FLAG,
            "permission_mode": VERSION_WITH_PERMISSION_MODE,
            "json_schema": VERSION_WITH_JSON_SCHEMA,
            "agent": VERSION_WITH_AGENT_FLAG,
        }

        min_version = flag_versions.get(flag_name)
        if min_version is None:
            return False

        return self._version_tuple >= min_version

    async def start_session(
        self,
        prompt: str,
        system_prompt: str | None = None,
        session_id: str | None = None,
        name: str | None = None,
        working_dir: Path | None = None,
        model: str | None = None,
        output_format: str = "json",
        max_turns: int | None = None,
        allowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        subagent: str | None = None,
    ) -> SessionResult:
        """Start a Claude CLI session.

        Args:
            prompt: User prompt to send to Claude
            system_prompt: Optional system prompt
            session_id: Session ID to resume (None = new session)
            name: Display name for the session (--name flag)
            working_dir: Working directory for Claude
            model: Model override
            output_format: Output format (json, text)
            max_turns: Maximum conversation turns
            allowed_tools: Pre-approved tools
            permission_mode: Permission mode (default, acceptEdits, plan, auto, bypassPermissions)
            timeout: Timeout in seconds
            env: Additional environment variables
            subagent: Subagent name to invoke (--agent flag)

        Returns:
            SessionResult with output and metadata
        """
        await self._check_claude_version()

        async with self._semaphore:
            # Build command
            cmd = [self.claude_path]

            # Omit --bare when using subagent to allow subagent config loading
            if not subagent:
                cmd.append("--bare")

            # Subagent (--agent flag)
            if subagent:
                cmd.extend(["--agent", subagent])

            # Session ID (new or resume)
            if session_id:
                cmd.extend(["--session-id", session_id])

            # Name (--name or -n flag)
            if name:
                cmd.extend(["--name", name])

            # Model
            if model:
                cmd.extend(["--model", model])

            # Output format
            if output_format == "json":
                cmd.extend(["--output-format", "json"])

            # Max turns
            if max_turns:
                cmd.extend(["--max-turns", str(max_turns)])

            # Permission mode (critical for non-interactive use)
            if permission_mode:
                cmd.extend(["--permission-mode", permission_mode])
            elif allowed_tools:
                # Note: camelCase flag
                cmd.extend(["--allowedTools", ",".join(allowed_tools)])
            else:
                # Default to bypassPermissions for non-interactive use
                logger.warning("Using bypassPermissions mode for non-interactive execution")
                cmd.extend(["--permission-mode", "bypassPermissions"])

            # System prompt
            temp_prompt_file = None
            if system_prompt:
                if len(system_prompt) <= 4096:
                    cmd.extend(["--system-prompt", system_prompt])
                else:
                    # Write to temp file for long prompts
                    with tempfile.NamedTemporaryFile(
                        mode="w", delete=False, suffix=".md"
                    ) as temp_file:
                        temp_file.write(system_prompt)
                        temp_prompt_file = temp_file.name
                    cmd.extend(["--system-prompt-file", temp_prompt_file])

            # Working directory
            cwd = working_dir or Path.cwd()

            # Environment
            full_env = {**os.environ, **(env or {})}

            # Add prompt as final argument
            cmd.extend(["-p", prompt])

            session_id = session_id or str(uuid4())
            start_time = asyncio.get_event_loop().time()

            # Track session metadata
            now = datetime.now()
            self._session_metadata[session_id] = {
                "name": name,
                "created_at": now.isoformat(),
                "last_used_at": now.isoformat(),
                "working_dir": str(cwd),
                "status": "active",
            }

            # Save to state store if available
            if self._state_store and self._workflow_id and self._run_id:
                session_info = StorageSessionInfo(
                    session_id=session_id,
                    workflow_id=self._workflow_id,
                    run_id=self._run_id,
                    name=name,
                    status="running",
                    working_dir=str(cwd),
                    created_at=now,
                    last_used_at=now,
                )
                await self._state_store.save_session(session_info)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=full_env,
                )

                self._sessions[session_id] = proc

                stdout, _stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )

                duration = asyncio.get_event_loop().time() - start_time
                exit_code = proc.returncode or 0
                raw_output = stdout.decode()

                # Parse JSON output if available
                parsed_output: dict[str, Any] = {}
                if output_format == "json" and raw_output:
                    try:
                        parsed_output = json.loads(raw_output)
                    except json.JSONDecodeError:
                        logger.warning("Could not parse JSON output: %s", raw_output[:200])

                return SessionResult(
                    session_id=session_id,
                    raw_output=raw_output,
                    parsed_output=parsed_output,
                    exit_code=exit_code,
                    duration_seconds=duration,
                    tokens_used=None,
                    claude_version=self._claude_version,
                )

            except TimeoutError:
                logger.error("Session %s timed out after %ss", session_id, timeout)
                if session_id in self._sessions:
                    proc.terminate()
                    await asyncio.sleep(1)
                    proc.kill()
                raise
            finally:
                if session_id in self._sessions:
                    del self._sessions[session_id]
                # Update metadata status
                if session_id in self._session_metadata:
                    self._session_metadata[session_id]["status"] = "completed"
                    self._session_metadata[session_id]["last_used_at"] = datetime.now().isoformat()
                # Update state store
                if self._state_store:
                    await self._state_store.update_session_status(session_id, "completed")
                if temp_prompt_file:
                    os.unlink(temp_prompt_file)

    async def resume_session(
        self,
        session_id: str,
        prompt: str,
        **kwargs: Any,
    ) -> SessionResult:
        """Resume an existing Claude CLI session.

        Args:
            session_id: ID of session to resume
            prompt: Prompt to send
            **kwargs: Additional arguments passed to start_session

        Returns:
            SessionResult with output and metadata
        """
        return await self.start_session(
            prompt=prompt,
            session_id=session_id,
            **kwargs,
        )

    async def list_sessions(
        self, workflow_id: str | None = None, run_id: str | None = None
    ) -> list[SessionInfo]:
        """List all sessions (in-memory and persisted).

        Args:
            workflow_id: Optional filter by workflow ID
            run_id: Optional filter by run ID

        Returns:
            List of SessionInfo objects
        """
        sessions = []

        # Add in-memory active sessions
        for session_id, proc in self._sessions.items():
            metadata = self._session_metadata.get(session_id, {})

            if proc.returncode is None:
                sessions.append(
                    SessionInfo(
                        session_id=session_id,
                        name=metadata.get("name"),
                        created_at=metadata.get("created_at", ""),
                        last_used_at=metadata.get("last_used_at", ""),
                        status="running",
                        working_dir=metadata.get("working_dir", str(Path.cwd())),
                    )
                )
            else:
                # Process has exited - mark as dead
                sessions.append(
                    SessionInfo(
                        session_id=session_id,
                        name=metadata.get("name"),
                        created_at=metadata.get("created_at", ""),
                        last_used_at=metadata.get("last_used_at", ""),
                        status="dead",
                        working_dir=metadata.get("working_dir", str(Path.cwd())),
                    )
                )
                # Clean up from active sessions
                del self._sessions[session_id]

        # Add persisted sessions from state store
        if self._state_store:
            persisted = await self._state_store.load_sessions(
                workflow_id=workflow_id, run_id=run_id
            )
            for ps in persisted:
                # Avoid duplicates
                if not any(s.session_id == ps.session_id for s in sessions):
                    sessions.append(
                        SessionInfo(
                            session_id=ps.session_id,
                            name=ps.name,
                            created_at=ps.created_at.isoformat(),
                            last_used_at=ps.last_used_at.isoformat(),
                            status=ps.status,
                            working_dir=ps.working_dir,
                        )
                    )

        return sessions

    async def kill_session(self, session_id: str) -> None:
        """Kill a running session.

        Args:
            session_id: ID of session to kill
        """
        if session_id in self._sessions:
            proc = self._sessions[session_id]
            if proc.returncode is None:
                proc.terminate()

            # Update metadata status
            if session_id in self._session_metadata:
                self._session_metadata[session_id]["status"] = "killed"
                self._session_metadata[session_id]["last_used_at"] = datetime.now().isoformat()

            # Persist status to state store
            if self._state_store:
                await self._state_store.update_session_status(session_id, "killed")

            del self._sessions[session_id]
