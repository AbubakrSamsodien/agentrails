"""Jinja2-based template engine for {{state.xxx}} expressions."""

from __future__ import annotations

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
