"""Structured output parsing for step results (JSON/TOML/text)."""

from __future__ import annotations

import json
import re
import tomllib
from typing import Any

import jsonschema


class OutputParseError(Exception):
    """Raised when output parsing fails."""

    def __init__(self, message: str, raw_text: str, expected_format: str):
        super().__init__(message)
        self.raw_text = raw_text
        self.expected_format = expected_format


class OutputParser:
    """Parse and validate step outputs in various formats."""

    @staticmethod
    def parse(
        raw_text: str,
        output_format: str,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        """Parse raw output text into structured data.

        Args:
            raw_text: Raw output from step execution
            output_format: Output format ("json", "toml", or "text")
            schema: Optional JSON Schema for validation

        Returns:
            Parsed output (dict for json/toml, str for text)

        Raises:
            OutputParseError: If parsing or validation fails
        """
        if output_format == "text":
            return raw_text

        if output_format == "json":
            return OutputParser._parse_json(raw_text, schema)

        if output_format == "toml":
            return OutputParser._parse_toml(raw_text, schema)

        raise OutputParseError(f"Unknown format: {output_format}", raw_text, output_format)

    @staticmethod
    def _parse_json(raw_text: str, schema: dict[str, Any] | None) -> Any:
        """Parse JSON output, handling markdown code fences."""
        content = OutputParser._extract_code_block(raw_text, "json")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise OutputParseError(f"Invalid JSON: {e}", raw_text, "json") from e

        if schema:
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as e:
                raise OutputParseError(
                    f"Schema validation failed: {e.message}", raw_text, "json"
                ) from e

        return data

    @staticmethod
    def _parse_toml(raw_text: str, schema: dict[str, Any] | None) -> Any:
        """Parse TOML output, handling markdown code fences."""
        content = OutputParser._extract_code_block(raw_text, "toml")
        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError as e:
            raise OutputParseError(f"Invalid TOML: {e}", raw_text, "toml") from e

        if schema:
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as e:
                raise OutputParseError(
                    f"Schema validation failed: {e.message}", raw_text, "toml"
                ) from e

        return data

    @staticmethod
    def _extract_code_block(text: str, language: str | None = None) -> str:
        """Extract code block from markdown-fenced text.

        If a language is specified, only extract blocks matching that language.
        If no matching block found, returns the entire text.
        """
        # Pattern for fenced code blocks
        pattern = r"```(?:\w+)?\n(.*?)```" if not language else rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)

        if matches:
            # Return the last matching block (most likely the final answer)
            return matches[-1].strip()

        # No fenced block found, return the entire text
        return text.strip()
