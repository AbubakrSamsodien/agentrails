"""Unified configuration management for AgentRails."""

import dataclasses
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:  # pylint: disable=too-many-instance-attributes
    """AgentRails configuration with resolution order: CLI > env > pyproject.toml > defaults.

    Resolution order (highest priority wins):
    1. CLI flags (passed via Click context)
    2. Environment variables (AGENTRAILS_* prefix)
    3. pyproject.toml [tool.agentrails] section (optional)
    4. Hardcoded defaults

    Config is frozen after initialization to prevent mutation during workflow execution.
    """

    log_level: str = "INFO"
    log_format: str = "json"
    storage_backend: str = "sqlite"
    db_url: str | None = None
    state_dir: str = ".agentrails"
    max_concurrent_sessions: int = 5
    default_permission_mode: str = "bypassPermissions"
    claude_cli_path: str = "claude"

    @classmethod
    def from_pyproject(cls, pyproject_path: Path | str | None = None) -> "Config":
        """Load configuration from pyproject.toml [tool.agentrails] section.

        Args:
            pyproject_path: Path to pyproject.toml. If None, searches from cwd upward.

        Returns:
            Config with values from pyproject.toml, or defaults if file not found.
        """

        if pyproject_path is None:
            pyproject_path = Path.cwd() / "pyproject.toml"
        else:
            pyproject_path = Path(pyproject_path)

        if not pyproject_path.exists():
            return cls()

        try:
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)

            tool_config = pyproject.get("tool", {}).get("agentrails", {})

            return cls(
                log_level=tool_config.get("log_level", "INFO"),
                log_format=tool_config.get("log_format", "json"),
                storage_backend=tool_config.get("storage_backend", "sqlite"),
                db_url=tool_config.get("db_url"),
                state_dir=tool_config.get("state_dir", ".agentrails"),
                max_concurrent_sessions=tool_config.get("max_concurrent_sessions", 5),
                default_permission_mode=tool_config.get(
                    "default_permission_mode", "bypassPermissions"
                ),
                claude_cli_path=tool_config.get("claude_cli_path", "claude"),
            )
        except (OSError, tomllib.TOMLDecodeError):
            return cls()

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            log_level=os.environ.get("AGENTRAILS_LOG_LEVEL", "INFO"),
            log_format=os.environ.get("AGENTRAILS_LOG_FORMAT", "json"),
            storage_backend=os.environ.get("AGENTRAILS_STORAGE", "sqlite"),
            db_url=os.environ.get("AGENTRAILS_DB_URL"),
            state_dir=os.environ.get("AGENTRAILS_STATE_DIR", ".agentrails"),
            max_concurrent_sessions=int(os.environ.get("AGENTRAILS_MAX_SESSIONS", "5")),
            default_permission_mode=os.environ.get(
                "AGENTRAILS_PERMISSION_MODE", "bypassPermissions"
            ),
            claude_cli_path=os.environ.get("AGENTRAILS_CLAUDE_PATH", "claude"),
        )

    @classmethod
    def from_cli(cls, base_config: "Config | None" = None, **kwargs) -> "Config":
        """Merge CLI overrides into configuration.

        Args:
            base_config: Base config to override. If None, loads from env + pyproject.
            **kwargs: CLI flag values (None values are ignored).

        Returns:
            Config with CLI overrides applied.
        """
        if base_config is None:
            base_config = cls.from_env()

        fields = {f.name for f in dataclasses.fields(cls)}
        overrides = {k: v for k, v in kwargs.items() if k in fields and v is not None}
        return dataclasses.replace(base_config, **overrides)
