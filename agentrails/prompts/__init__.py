"""AgentRails prompt resources."""

from functools import lru_cache
from pathlib import Path

__all__ = ["load_base_prompt"]


@lru_cache(maxsize=1)
def load_base_prompt() -> str:
    """Load the AgentRails base prompt (Layer 1).

    Returns:
        The base prompt content as a string.

    The base prompt is cached after first load for performance.
    """
    prompt_path = Path(__file__).parent / "base.md"
    return prompt_path.read_text(encoding="utf-8")
