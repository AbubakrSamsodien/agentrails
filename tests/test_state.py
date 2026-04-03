"""Tests for WorkflowState class."""

import pytest

from agentrails.state import MergeStrategy, WorkflowState


def test_dot_path_access():
    """Test getting values via dot-path."""
    state = WorkflowState({"tests": {"unit": {"status": "pass"}}})
    assert state.get("tests.unit.status") == "pass"
    assert state.get("tests.unit") == {"status": "pass"}
    assert state.get("tests") == {"unit": {"status": "pass"}}


def test_dot_path_access_missing():
    """Test getting non-existent paths returns default."""
    state = WorkflowState({"key": "value"})
    assert state.get("nonexistent") is None
    assert state.get("nonexistent", "default") == "default"
    assert state.get("key.nested") is None


def test_dot_path_set():
    """Test setting values via dot-path."""
    state = WorkflowState({})
    new_state = state.set("a.b.c", "value")

    assert state.get("a.b.c") is None  # Original unchanged
    assert new_state.get("a.b.c") == "value"
    assert new_state.get("a.b") == {"c": "value"}


def test_immutable_update():
    """Test that update returns a new copy."""
    s1 = WorkflowState({})
    s2 = s1.update("plan", "do things")

    assert s1.get("plan") is None
    assert s2.get("plan") == "do things"
    assert s1 is not s2


def test_json_roundtrip():
    """Test JSON serialization and deserialization."""
    original = WorkflowState({"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}})
    json_str = original.to_json()
    restored = WorkflowState.from_json(json_str)

    assert original == restored


def test_snapshot():
    """Test that snapshot returns a deep copy."""
    state = WorkflowState({"key": "value"})
    snapshot = state.snapshot()

    snapshot["key"] = "modified"
    assert state.get("key") == "value"  # Original unchanged


def test_merge_overwrite():
    """Test merge with OVERWRITE strategy."""
    s1 = WorkflowState({"a": 1, "b": 2})
    s2 = WorkflowState({"b": 3, "c": 4})

    merged = s1.merge(s2, MergeStrategy.OVERWRITE)

    assert merged.get("a") == 1
    assert merged.get("b") == 3  # Overwritten
    assert merged.get("c") == 4


def test_merge_list_append():
    """Test merge with LIST_APPEND strategy."""
    s1 = WorkflowState({"items": [1, 2]})
    s2 = WorkflowState({"items": [3, 4]})

    merged = s1.merge(s2, MergeStrategy.LIST_APPEND)

    assert merged.get("items") == [1, 2, 3, 4]


def test_merge_fail_on_conflict():
    """Test merge with FAIL_ON_CONFLICT strategy."""
    s1 = WorkflowState({"key": "value1"})
    s2 = WorkflowState({"key": "value2"})

    with pytest.raises(ValueError, match="Conflict"):
        s1.merge(s2, MergeStrategy.FAIL_ON_CONFLICT)


def test_merge_nested():
    """Test merge with nested dictionaries."""
    s1 = WorkflowState({"a": {"b": 1, "c": 2}})
    s2 = WorkflowState({"a": {"c": 3, "d": 4}})

    merged = s1.merge(s2, MergeStrategy.OVERWRITE)

    assert merged.get("a.b") == 1
    assert merged.get("a.c") == 3
    assert merged.get("a.d") == 4


def test_eq():
    """Test equality comparison."""
    s1 = WorkflowState({"key": "value"})
    s2 = WorkflowState({"key": "value"})
    s3 = WorkflowState({"key": "other"})

    assert s1 == s2
    assert s1 != s3


def test_repr():
    """Test string representation."""
    state = WorkflowState({"key": "value"})
    repr_str = repr(state)
    assert "WorkflowState" in repr_str
    assert "key" in repr_str


def test_validate_success():
    """Test validation passes when state matches schema."""
    state = WorkflowState({"name": "test", "count": 5})
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
        "required": ["name"],
    }

    errors = state.validate(schema)
    assert errors == []


def test_validate_missing_required_field():
    """Test validation fails when required field is missing."""
    state = WorkflowState({"name": "test"})
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
        "required": ["name", "count"],
    }

    errors = state.validate(schema)
    assert len(errors) == 1
    assert "count" in errors[0]


def test_validate_wrong_type():
    """Test validation fails when field has wrong type."""
    state = WorkflowState({"name": "test", "count": "not-a-number"})
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
    }

    errors = state.validate(schema)
    assert len(errors) == 1
    assert "count" in errors[0]


def test_validate_nested():
    """Test validation with nested schema."""
    state = WorkflowState(
        {
            "user": {"name": "test", "age": 25},
            "active": True,
        }
    )
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name"],
            },
            "active": {"type": "boolean"},
        },
    }

    errors = state.validate(schema)
    assert errors == []


def test_validate_no_schema():
    """Test that validate can be called with empty schema (always passes)."""
    state = WorkflowState({"anything": "goes"})
    schema = {}

    errors = state.validate(schema)
    assert errors == []
