"""Tests for AgentRails base prompt loading and validation."""

from agentrails.prompts import load_base_prompt


class TestBasePromptLoading:
    """Test that the base prompt file exists and is loadable."""

    def test_base_prompt_file_exists(self):
        """Base prompt file can be loaded."""
        prompt = load_base_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_base_prompt_not_empty(self):
        """Base prompt has content."""
        prompt = load_base_prompt()
        assert prompt.strip() != ""

    def test_base_prompt_cached(self):
        """Base prompt is cached after first load."""
        prompt1 = load_base_prompt()
        prompt2 = load_base_prompt()
        assert prompt1 is prompt2  # Same object due to lru_cache


class TestBasePromptValidation:
    """Test that the base prompt meets design requirements."""

    def test_base_prompt_under_600_words(self):
        """Base prompt is under 600 words."""
        prompt = load_base_prompt()
        word_count = len(prompt.split())
        assert word_count < 600, f"Base prompt has {word_count} words, expected < 600"

    def test_base_prompt_no_provider_specific_terms(self):
        """Base prompt contains no AI provider or CLI tool specific references."""
        prompt = load_base_prompt().lower()

        # Terms that would indicate provider/tool coupling
        forbidden_terms = [
            "claude",
            "anthropic",
            "openai",
            "gpt",
            "gemini",
            "google",
            "cohere",
            "mistral",
            "llama",
            "meta ai",
            "grok",
            "xai",
            "@anthropic-ai/claude-cli",
            "claude cli",
            "agentrails cli",
        ]

        found_terms = []
        for term in forbidden_terms:
            if term in prompt:
                found_terms.append(term)

        assert len(found_terms) == 0, f"Base prompt contains provider-specific terms: {found_terms}"

    def test_base_prompt_has_required_sections(self):
        """Base prompt contains all required section headers."""
        prompt = load_base_prompt()

        required_sections = [
            "# Tools and file operations",
            "# Working with code",
            "# Scope and safety",
            "# Output discipline",
            "# Work style",
        ]

        missing_sections = []
        for section in required_sections:
            if section not in prompt:
                missing_sections.append(section)

        assert len(missing_sections) == 0, f"Base prompt missing sections: {missing_sections}"

    def test_base_prompt_starts_with_headless_statement(self):
        """Base prompt opens with headless pipeline context."""
        prompt = load_base_prompt()
        assert "headlessly" in prompt.lower() or "automated workflow" in prompt.lower()

    def test_base_prompt_mentions_structured_output(self):
        """Base prompt mentions JSON/TOML output format requirements."""
        prompt = load_base_prompt()
        assert "json" in prompt.lower() or "toml" in prompt.lower()


class TestBasePromptContent:
    """Test specific content requirements in the base prompt."""

    def test_tools_section_mentions_dedicated_tools(self):
        """Tools section mentions using dedicated tools over shell."""
        prompt = load_base_prompt()
        assert "Read" in prompt
        assert "Edit" in prompt
        assert "Write" in prompt
        assert "Glob" in prompt
        assert "Grep" in prompt

    def test_code_section_mentions_security(self):
        """Working with code section mentions security vulnerabilities."""
        prompt = load_base_prompt()
        assert "security" in prompt.lower()

    def test_scope_section_mentions_reversibility(self):
        """Scope and safety section mentions reversibility."""
        prompt = load_base_prompt()
        assert "reversible" in prompt.lower() or "reversibility" in prompt.lower()

    def test_output_section_mentions_markdown_fences(self):
        """Output discipline section mentions markdown code fences."""
        prompt = load_base_prompt()
        assert "code fences" in prompt.lower() or "markdown" in prompt.lower()
