"""Prompt composition engine for AgentRails layered system prompts."""

__all__ = ["compose_system_prompt"]

LAYER_SEPARATOR = "\n\n---\n\n"


def compose_system_prompt(
    base_prompt: str | None = None,
    workflow_default_prompt: str | None = None,
    step_prompt: str | None = None,
    auto_context: str | None = None,
    raw_mode: bool = False,
) -> str:
    """Compose system prompt from layers.

    Layer model:
        Layer 1: base_prompt — AgentRails base prompt (always unless raw_mode)
        Layer 2: workflow_default_prompt — defaults.system_prompt from YAML
        Layer 3: step_prompt — step-level system_prompt override
        Layer 4: auto_context — auto-injected schema and pipeline context

    Args:
        base_prompt: Layer 1 — framework base prompt
        workflow_default_prompt: Layer 2 — workflow-level default
        step_prompt: Layer 3 — step-specific override
        auto_context: Layer 4 — auto-injected context (schema + pipeline)
        raw_mode: If True, only step_prompt is used (escape hatch)

    Returns:
        Composed system prompt string, or empty string if all layers are empty.
    """
    if raw_mode:
        return step_prompt.strip() if step_prompt else ""

    layers = []

    if base_prompt and base_prompt.strip():
        layers.append(base_prompt)

    if workflow_default_prompt and workflow_default_prompt.strip():
        layers.append(f"# Workflow context\n\n{workflow_default_prompt}")

    if step_prompt and step_prompt.strip():
        layers.append(f"# Task instructions\n\n{step_prompt}")

    if auto_context and auto_context.strip():
        layers.append(auto_context)

    if not layers:
        return ""

    return LAYER_SEPARATOR.join(layers)
