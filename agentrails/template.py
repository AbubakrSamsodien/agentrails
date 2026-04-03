"""Jinja2-based template engine for {{state.xxx}} expressions."""

from __future__ import annotations

import re

from jinja2 import Environment, StrictUndefined, TemplateError


class TemplateRenderError(Exception):
    """Raised when template rendering fails."""

    def __init__(self, message: str, template: str, variable: str | None = None):
        super().__init__(message)
        self.template = template
        self.variable = variable


def render_template(template: str, state: dict) -> str:
    """Render a Jinja2 template with state variables.

    Args:
        template: Template string with {{state.xxx}} expressions
        state: State dictionary (will be accessible as 'state' in template)

    Returns:
        Rendered template string

    Raises:
        TemplateRenderError: If an undefined variable is accessed
    """
    env = Environment(
        undefined=StrictUndefined,
        autoescape=False,
        extensions=[],
    )

    # Jinja2 already provides 'length' (via |count or |length) and 'join' filters
    # We just need to expose state safely

    try:
        tmpl = env.from_string(template)
        return tmpl.render(state=state)
    except TemplateError as e:
        raise TemplateRenderError(str(e), template) from e


# Regex to match {{...}} wrapper
_CONDITION_PATTERN = re.compile(r"^\s*\{\{\s*(.+?)\s*\}\}\s*$")


def evaluate_condition(condition: str, state: dict) -> bool:
    """Evaluate a condition expression as a boolean.

    Uses Jinja2's compile_expression for safe evaluation instead of eval().

    Args:
        condition: Condition string, either a raw expression or {{expression}} wrapper
        state: State dictionary (accessible as 'state' in expression)

    Returns:
        Boolean result of the condition

    Raises:
        TemplateRenderError: If the condition cannot be evaluated

    Examples:
        >>> evaluate_condition("{{state.count > 0}}", {"count": 5})
        True
        >>> evaluate_condition("state.status == 'ready'", {"status": "ready"})
        True
    """
    # Strip {{...}} wrapper if present
    match = _CONDITION_PATTERN.match(condition)
    expression = match.group(1) if match else condition

    env = Environment(
        undefined=StrictUndefined,
        autoescape=False,
    )

    try:
        # Compile the expression (not a full template)
        expr = env.compile_expression(expression)
        result = expr(state=state)
        return bool(result)
    except TemplateError as e:
        raise TemplateRenderError(str(e), condition) from e
    except Exception as e:
        raise TemplateRenderError(f"Failed to evaluate condition: {e}", condition) from e
