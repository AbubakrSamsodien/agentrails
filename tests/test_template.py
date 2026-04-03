"""Tests for template rendering."""

import pytest

from agentrails.template import (
    TemplateRenderError,
    evaluate_condition,
    render_template,
)


def test_render_simple():
    """Test simple variable substitution."""
    state = {"name": "Alice"}
    result = render_template("Hello {{state.name}}!", state)
    assert result == "Hello Alice!"


def test_render_nested():
    """Test nested dot-path access."""
    state = {"user": {"name": "Bob", "age": 30}}
    result = render_template("User: {{state.user.name}}, Age: {{state.user.age}}", state)
    assert result == "User: Bob, Age: 30"


def test_render_comparison():
    """Test comparison expressions."""
    state = {"count": 5}
    result = render_template("{{state.count > 0}}", state)
    assert result == "True"


def test_render_boolean_operators():
    """Test boolean operators."""
    state = {"a": True, "b": False}
    result1 = render_template("{{state.a and state.b}}", state)
    result2 = render_template("{{state.a or state.b}}", state)
    result3 = render_template("{{not state.b}}", state)

    assert result1 == "False"
    assert result2 == "True"
    assert result3 == "True"


def test_render_undefined_variable():
    """Test that undefined variables raise TemplateRenderError."""
    state = {"key": "value"}
    with pytest.raises(TemplateRenderError):
        render_template("{{state.undefined}}", state)


def test_render_filter_count():
    """Test count filter (Jinja2 built-in)."""
    state = {"my_list": [1, 2, 3]}
    result = render_template("{{state.my_list | length}}", state)
    assert result == "3"


def test_render_filter_join():
    """Test join filter (Jinja2 built-in)."""
    state = {"my_list": ["a", "b", "c"]}
    result = render_template("{{state.my_list | join(', ')}}", state)
    assert result == "a, b, c"


def test_render_no_variables():
    """Test template with no variables."""
    result = render_template("Plain text", {})
    assert result == "Plain text"


class TestEvaluateCondition:
    """Tests for evaluate_condition()."""

    def test_condition_with_wrapper(self):
        """Test condition with {{...}} wrapper."""
        state = {"count": 5}
        assert evaluate_condition("{{state.count > 0}}", state) is True
        assert evaluate_condition("{{state.count < 0}}", state) is False

    def test_condition_without_wrapper(self):
        """Test condition without {{...}} wrapper."""
        state = {"status": "ready"}
        assert evaluate_condition("state.status == 'ready'", state) is True
        assert evaluate_condition("state.status != 'ready'", state) is False

    def test_condition_boolean_operators(self):
        """Test boolean operators in conditions."""
        state = {"a": True, "b": False, "c": True}
        assert evaluate_condition("{{state.a and state.c}}", state) is True
        assert evaluate_condition("{{state.a and state.b}}", state) is False
        assert evaluate_condition("{{state.a or state.b}}", state) is True
        assert evaluate_condition("{{not state.b}}", state) is True

    def test_condition_nested_access(self):
        """Test nested dot-path access in conditions."""
        state = {"tests": {"unit": {"passed": True}}}
        assert evaluate_condition("{{state.tests.unit.passed == True}}", state) is True
        assert evaluate_condition("{{state.tests.unit.passed == False}}", state) is False

    def test_condition_undefined_variable(self):
        """Test that undefined variables raise TemplateRenderError."""
        state = {"key": "value"}
        with pytest.raises(TemplateRenderError):
            evaluate_condition("{{state.undefined == True}}", state)

    def test_condition_whitespace_handling(self):
        """Test whitespace handling in condition wrapper."""
        state = {"x": 1}
        # Various whitespace patterns
        assert evaluate_condition("  {{state.x == 1}}  ", state) is True
        assert evaluate_condition("{{  state.x == 1  }}", state) is True
        assert evaluate_condition("{{ state.x == 1 }}", state) is True

    def test_condition_invalid_expression(self):
        """Test that invalid expressions raise TemplateRenderError."""
        state = {"x": 1}
        with pytest.raises(TemplateRenderError):
            evaluate_condition("{{state.x === 1}}", state)  # Invalid Python syntax
