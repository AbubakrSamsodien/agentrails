"""Tests for OutputParser class."""

import pytest

from agentrails.output import OutputParseError, OutputParser


def test_parse_text():
    """Test text format returns raw string."""
    result = OutputParser.parse("hello world", "text")
    assert result == "hello world"


def test_parse_json_simple():
    """Test parsing simple JSON."""
    raw = '{"key": "value", "num": 42}'
    result = OutputParser.parse(raw, "json")
    assert result == {"key": "value", "num": 42}


def test_parse_json_from_fenced_block():
    """Test extracting JSON from markdown code fence."""
    raw = 'Here is the plan:\n```json\n{"title": "Plan A", "steps": ["a", "b"]}\n```\nDone.'
    result = OutputParser.parse(raw, "json")
    assert result == {"title": "Plan A", "steps": ["a", "b"]}


def test_parse_json_with_prose():
    """Test extracting JSON from text with surrounding prose."""
    raw = """Sure, I can help with that.

Based on my analysis, here's the plan:

```json
{
  "title": "Implementation Plan",
  "steps": ["step1", "step2"]
}
```

Let me know if you need any changes!"""
    result = OutputParser.parse(raw, "json")
    assert result["title"] == "Implementation Plan"
    assert result["steps"] == ["step1", "step2"]


def test_parse_toml_simple():
    """Test parsing simple TOML."""
    raw = 'title = "Test"\nvalue = 42'
    result = OutputParser.parse(raw, "toml")
    assert result == {"title": "Test", "value": 42}


def test_parse_toml_from_fenced_block():
    """Test extracting TOML from markdown code fence."""
    raw = '```toml\ntitle = "Plan A"\nsteps = ["a", "b"]\n```'
    result = OutputParser.parse(raw, "toml")
    assert result == {"title": "Plan A", "steps": ["a", "b"]}


def test_parse_json_invalid():
    """Test that invalid JSON raises OutputParseError."""
    raw = '{"invalid": json}'
    with pytest.raises(OutputParseError) as exc_info:
        OutputParser.parse(raw, "json")

    assert exc_info.value.raw_text == raw
    assert exc_info.value.expected_format == "json"


def test_parse_json_schema_validation_success():
    """Test JSON schema validation passes for valid data."""
    raw = '{"title": "Plan", "steps": ["a"]}'
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
    }

    result = OutputParser.parse(raw, "json", schema)
    assert result["title"] == "Plan"


def test_parse_json_schema_validation_failure():
    """Test JSON schema validation fails for invalid data."""
    raw = '{"title": "Plan"}'  # missing required "steps"
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array"},
        },
        "required": ["title", "steps"],
    }

    with pytest.raises(OutputParseError, match="Schema validation failed"):
        OutputParser.parse(raw, "json", schema)


def test_parse_unknown_format():
    """Test that unknown format raises OutputParseError."""
    with pytest.raises(OutputParseError, match="Unknown format"):
        OutputParser.parse("data", "xml")
