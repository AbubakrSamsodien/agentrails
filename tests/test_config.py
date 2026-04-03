"""Tests for Config class and configuration resolution."""

import dataclasses

import pytest

from agentrails.config import Config


class TestConfigDefaults:
    """Test default configuration values."""

    def test_config_defaults(self):
        """Test all default values are set correctly."""
        config = Config()

        assert config.log_level == "INFO"
        assert config.log_format == "json"
        assert config.storage_backend == "sqlite"
        assert config.db_url is None
        assert config.state_dir == ".agentrails"
        assert config.max_concurrent_sessions == 5
        assert config.default_permission_mode == "bypassPermissions"
        assert config.claude_cli_path == "claude"

    def test_config_is_frozen(self):
        """Test that config cannot be modified after creation."""
        config = Config()

        with pytest.raises(dataclasses.FrozenInstanceError):
            config.log_level = "DEBUG"


class TestConfigFromEnv:
    """Test loading configuration from environment variables."""

    def test_config_from_env_all_defaults(self, monkeypatch):
        """Test from_env with no env vars set."""
        for key in [
            "AGENTRAILS_LOG_LEVEL",
            "AGENTRAILS_LOG_FORMAT",
            "AGENTRAILS_STORAGE",
            "AGENTRAILS_DB_URL",
            "AGENTRAILS_STATE_DIR",
            "AGENTRAILS_MAX_SESSIONS",
            "AGENTRAILS_PERMISSION_MODE",
            "AGENTRAILS_CLAUDE_PATH",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = Config.from_env()

        assert config.log_level == "INFO"
        assert config.log_format == "json"
        assert config.storage_backend == "sqlite"
        assert config.db_url is None
        assert config.state_dir == ".agentrails"
        assert config.max_concurrent_sessions == 5
        assert config.default_permission_mode == "bypassPermissions"
        assert config.claude_cli_path == "claude"

    def test_config_from_env_all_set(self, monkeypatch):
        """Test from_env with all env vars set."""
        monkeypatch.setenv("AGENTRAILS_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("AGENTRAILS_LOG_FORMAT", "text")
        monkeypatch.setenv("AGENTRAILS_STORAGE", "postgres")
        monkeypatch.setenv("AGENTRAILS_DB_URL", "postgresql://localhost/test")
        monkeypatch.setenv("AGENTRAILS_STATE_DIR", "/tmp/state")
        monkeypatch.setenv("AGENTRAILS_MAX_SESSIONS", "10")
        monkeypatch.setenv("AGENTRAILS_PERMISSION_MODE", "acceptEdits")
        monkeypatch.setenv("AGENTRAILS_CLAUDE_PATH", "/usr/local/bin/claude")

        config = Config.from_env()

        assert config.log_level == "DEBUG"
        assert config.log_format == "text"
        assert config.storage_backend == "postgres"
        assert config.db_url == "postgresql://localhost/test"
        assert config.state_dir == "/tmp/state"
        assert config.max_concurrent_sessions == 10
        assert config.default_permission_mode == "acceptEdits"
        assert config.claude_cli_path == "/usr/local/bin/claude"

    def test_config_from_env_partial(self, monkeypatch):
        """Test from_env with only some env vars set."""
        monkeypatch.setenv("AGENTRAILS_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("AGENTRAILS_STORAGE", "postgres")

        config = Config.from_env()

        assert config.log_level == "WARNING"
        assert config.log_format == "json"  # default
        assert config.storage_backend == "postgres"
        assert config.max_concurrent_sessions == 5  # default


class TestConfigFromPyproject:
    """Test loading configuration from pyproject.toml."""

    def test_config_from_pyproject_not_found(self):
        """Test from_pyproject when file doesn't exist."""
        config = Config.from_pyproject("/nonexistent/pyproject.toml")

        assert config.log_level == "INFO"
        assert config.storage_backend == "sqlite"

    def test_config_from_pyproject_empty_section(self, tmp_path):
        """Test from_pyproject with file but no [tool.agentrails] section."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')

        config = Config.from_pyproject(pyproject)

        assert config.log_level == "INFO"
        assert config.storage_backend == "sqlite"

    def test_config_from_pyproject_full_config(self, tmp_path):
        """Test from_pyproject with full configuration."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.agentrails]
log_level = "DEBUG"
log_format = "text"
storage_backend = "postgres"
db_url = "postgresql://localhost/test"
state_dir = "/tmp/state"
max_concurrent_sessions = 10
default_permission_mode = "acceptEdits"
claude_cli_path = "/usr/local/bin/claude"
""")

        config = Config.from_pyproject(pyproject)

        assert config.log_level == "DEBUG"
        assert config.log_format == "text"
        assert config.storage_backend == "postgres"
        assert config.db_url == "postgresql://localhost/test"
        assert config.state_dir == "/tmp/state"
        assert config.max_concurrent_sessions == 10
        assert config.default_permission_mode == "acceptEdits"
        assert config.claude_cli_path == "/usr/local/bin/claude"

    def test_config_from_pyproject_partial_config(self, tmp_path):
        """Test from_pyproject with partial configuration."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.agentrails]
log_level = "WARNING"
storage_backend = "postgres"
""")

        config = Config.from_pyproject(pyproject)

        assert config.log_level == "WARNING"
        assert config.log_format == "json"  # default
        assert config.storage_backend == "postgres"
        assert config.max_concurrent_sessions == 5  # default


class TestConfigFromCli:
    """Test CLI override resolution."""

    def test_config_from_cli_no_overrides(self):
        """Test from_cli with no overrides."""
        base = Config()
        config = Config.from_cli(base)

        assert config == base

    def test_config_from_cli_single_override(self):
        """Test from_cli with single override."""
        base = Config()
        config = Config.from_cli(base, log_level="DEBUG")

        assert config.log_level == "DEBUG"
        assert config.log_format == "json"  # unchanged

    def test_config_from_cli_multiple_overrides(self):
        """Test from_cli with multiple overrides."""
        base = Config()
        config = Config.from_cli(
            base,
            log_level="DEBUG",
            storage_backend="postgres",
            max_concurrent_sessions=10,
        )

        assert config.log_level == "DEBUG"
        assert config.storage_backend == "postgres"
        assert config.max_concurrent_sessions == 10

    def test_config_from_cli_none_values_ignored(self):
        """Test that None values in kwargs don't override."""
        base = Config(log_level="DEBUG")
        config = Config.from_cli(base, log_level=None, log_format="text")

        assert config.log_level == "DEBUG"  # unchanged (None ignored)
        assert config.log_format == "text"

    def test_config_from_cli_loads_base_from_env(self, monkeypatch):
        """Test from_cli without base_config loads from env."""
        monkeypatch.setenv("AGENTRAILS_LOG_LEVEL", "WARNING")

        config = Config.from_cli(log_format="text")

        assert config.log_level == "WARNING"  # from env
        assert config.log_format == "text"  # from cli


class TestConfigResolutionOrder:
    """Test full resolution order: CLI > env > pyproject > defaults."""

    def test_resolution_order_full_chain(self, monkeypatch, tmp_path):
        """Test complete resolution chain."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.agentrails]
log_level = "WARNING"
storage_backend = "postgres"
max_concurrent_sessions = 3
""")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("AGENTRAILS_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("AGENTRAILS_STORAGE", "postgres")
        monkeypatch.setenv("AGENTRAILS_MAX_SESSIONS", "3")

        env_config = Config.from_env()
        cli_config = Config.from_cli(env_config, storage_backend="sqlite")

        assert cli_config.log_level == "ERROR"  # from env (CLI didn't override)
        assert cli_config.storage_backend == "sqlite"  # from CLI (overrode env)
        assert (
            cli_config.max_concurrent_sessions == 3
        )  # from env (originally from pyproject concept)

    def test_cli_beats_env_beats_pyproject_beats_defaults(self, monkeypatch, tmp_path):
        """Test priority: CLI > env > pyproject > defaults."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.agentrails]
log_level = "WARNING"
""")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("AGENTRAILS_LOG_LEVEL", "ERROR")

        config = Config.from_cli(Config.from_env(), log_level="DEBUG")

        assert config.log_level == "DEBUG"  # CLI wins
