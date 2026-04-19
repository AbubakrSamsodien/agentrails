"""Tests for prompt composition engine."""

from agentrails.prompt_composer import LAYER_SEPARATOR, compose_system_prompt


class TestComposeSystemPrompt:
    """Test the layered prompt composition function."""

    def test_no_prompts(self):
        """All None inputs return empty string."""
        result = compose_system_prompt(
            base_prompt=None,
            workflow_default_prompt=None,
            step_prompt=None,
            auto_context=None,
        )
        assert result == ""

    def test_base_prompt_only(self):
        """Only base prompt returns base prompt."""
        result = compose_system_prompt(base_prompt="Base prompt content")
        assert result == "Base prompt content"
        assert "# Workflow context" not in result
        assert "# Task instructions" not in result

    def test_workflow_default_only(self):
        """Only workflow default includes header."""
        result = compose_system_prompt(workflow_default_prompt="Default content")
        assert result == "# Workflow context\n\nDefault content"

    def test_step_override_only(self):
        """Only step prompt includes header."""
        result = compose_system_prompt(step_prompt="Step content")
        assert result == "# Task instructions\n\nStep content"

    def test_all_three_layers(self):
        """All three layers composed in order with separators."""
        result = compose_system_prompt(
            base_prompt="Layer 1",
            workflow_default_prompt="Layer 2",
            step_prompt="Layer 3",
        )
        assert (
            result
            == f"Layer 1{LAYER_SEPARATOR}# Workflow context\n\nLayer 2{LAYER_SEPARATOR}# Task instructions\n\nLayer 3"
        )

    def test_empty_string_treated_as_absent(self):
        """Empty strings are treated as absent (skipped)."""
        result = compose_system_prompt(
            base_prompt="",
            workflow_default_prompt="   ",  # whitespace only
            step_prompt="Step content",
        )
        # Base and default should be skipped
        assert result == "# Task instructions\n\nStep content"
        assert LAYER_SEPARATOR not in result  # No separator since only one layer

    def test_auto_context_appended(self):
        """Auto context is appended as Layer 4."""
        result = compose_system_prompt(
            base_prompt="Base",
            workflow_default_prompt=None,
            step_prompt=None,
            auto_context="Auto-injected context",
        )
        assert result == f"Base{LAYER_SEPARATOR}Auto-injected context"

    def test_all_four_layers(self):
        """All four layers composed correctly."""
        result = compose_system_prompt(
            base_prompt="Base",
            workflow_default_prompt="Default",
            step_prompt="Step",
            auto_context="Auto",
        )
        # Count separators - should have 3 separators for 4 layers
        separator_count = result.count(LAYER_SEPARATOR)
        assert separator_count == 3
        assert result.startswith("Base")
        assert result.endswith("Auto")

    def test_raw_mode_step_only(self):
        """Raw mode returns only step prompt."""
        result = compose_system_prompt(
            base_prompt="Base",
            workflow_default_prompt="Default",
            step_prompt="Step only",
            auto_context="Auto",
            raw_mode=True,
        )
        assert result == "Step only"
        assert "Base" not in result
        assert "Default" not in result
        assert "Auto" not in result

    def test_raw_mode_no_step_prompt(self):
        """Raw mode with no step prompt returns empty string."""
        result = compose_system_prompt(
            base_prompt="Base",
            workflow_default_prompt="Default",
            step_prompt=None,
            raw_mode=True,
        )
        assert result == ""

    def test_raw_mode_empty_step_prompt(self):
        """Raw mode with empty step prompt returns empty string."""
        result = compose_system_prompt(
            base_prompt="Base",
            step_prompt="  ",
            raw_mode=True,
        )
        assert result == ""

    def test_separator_format(self):
        """Layer separator is correct format."""
        assert LAYER_SEPARATOR == "\n\n---\n\n"

    def test_workflow_context_header_present(self):
        """Workflow default gets '# Workflow context' header."""
        result = compose_system_prompt(workflow_default_prompt="My workflow default")
        assert result == "# Workflow context\n\nMy workflow default"

    def test_task_instructions_header_present(self):
        """Step prompt gets '# Task instructions' header."""
        result = compose_system_prompt(step_prompt="Do the task")
        assert result == "# Task instructions\n\nDo the task"
