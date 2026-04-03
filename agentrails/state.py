"""Workflow state management with immutable updates and merge strategies."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import jsonschema


class MergeStrategy(Enum):
    """Strategy for merging conflicting state values."""

    OVERWRITE = "overwrite"
    LIST_APPEND = "list_append"
    FAIL_ON_CONFLICT = "fail_on_conflict"


@dataclass
class WorkflowState:
    """Immutable workflow state with dot-path access.

    State is a nested dictionary that supports:
    - Dot-path get/set: state.get("a.b.c"), state.set("a.b.c", value)
    - Immutable updates: .update() returns a new copy
    - JSON serialization for checkpointing
    - Merge strategies for parallel branch reconciliation
    """

    _data: dict[str, Any]

    def __init__(self, data: dict[str, Any] | None = None):
        """Initialize workflow state.

        Args:
            data: Initial state dictionary (deep copied)
        """
        self._data = copy.deepcopy(data or {})

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value by dot-path.

        Args:
            path: Dot-separated path (e.g., "tests.unit.status")
            default: Value to return if path doesn't exist

        Returns:
            Value at path or default
        """
        keys = path.split(".")
        current = self._data
        for key in keys:
            if not isinstance(current, dict):
                return default
            if key not in current:
                return default
            current = current[key]
        return current

    def set(self, path: str, value: Any) -> WorkflowState:
        """Set a value by dot-path, returning a new state copy.

        Args:
            path: Dot-separated path (e.g., "tests.unit.status")
            value: Value to set

        Returns:
            New WorkflowState with the update applied
        """
        new_state = WorkflowState(self._data)
        keys = path.split(".")
        current = new_state._data  # pylint: disable=W0212

        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        return new_state

    def update(self, key: str, value: Any) -> WorkflowState:
        """Update state immutably, returning a new copy.

        This is an alias for set() for backwards compatibility.

        Args:
            key: Dot-separated path
            value: Value to set

        Returns:
            New WorkflowState with the update applied
        """
        return self.set(key, value)

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the entire state."""
        return copy.deepcopy(self._data)

    def merge(
        self, other: WorkflowState, strategy: MergeStrategy = MergeStrategy.OVERWRITE
    ) -> WorkflowState:
        """Merge another state into this one.

        Args:
            other: State to merge from
            strategy: How to handle conflicts

        Returns:
            New WorkflowState with merged values

        Raises:
            ValueError: If FAIL_ON_CONFLICT and conflicts detected
        """
        base = copy.deepcopy(self._data)
        other_data = other.snapshot()

        WorkflowState._merge_dicts(base, other_data, strategy)
        return WorkflowState(base)

    @staticmethod
    def _merge_dicts(base: dict, other: dict, strategy: MergeStrategy) -> None:
        """Recursively merge dictionaries in place."""
        for key, value in other.items():
            if key in base:
                if isinstance(base[key], dict) and isinstance(value, dict):
                    WorkflowState._merge_dicts(base[key], value, strategy)
                else:
                    if strategy == MergeStrategy.FAIL_ON_CONFLICT and base[key] != value:
                        raise ValueError(f"Conflict on key '{key}': {base[key]} vs {value}")
                    if strategy == MergeStrategy.LIST_APPEND:
                        if isinstance(base[key], list) and isinstance(value, list):
                            base[key].extend(value)
                        else:
                            base[key] = value
                    else:  # OVERWRITE
                        base[key] = value
            else:
                base[key] = value

    def to_json(self) -> str:
        """Serialize state to JSON string."""
        return json.dumps(self._data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> WorkflowState:
        """Deserialize state from JSON string."""
        return cls(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorkflowState):
            return NotImplemented
        return self._data == other._data

    def __repr__(self) -> str:
        return f"WorkflowState({self._data!r})"

    def validate(self, schema: dict[str, Any]) -> list[str]:
        """Validate state against a JSON Schema.

        Args:
            schema: JSON Schema to validate against

        Returns:
            List of validation error messages (empty if valid)
        """
        try:
            jsonschema.validate(self._data, schema)
            return []
        except jsonschema.ValidationError as e:
            # Return human-readable error message
            path = ".".join(str(p) for p in e.path) if e.path else "root"
            return [f"Field '{path}': {e.message}"]
        except jsonschema.SchemaError as e:
            return [f"Invalid schema: {e.message}"]
