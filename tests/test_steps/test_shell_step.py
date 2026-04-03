"""Tests for ShellStep class."""



def test_shell_step_initialization():
    """Test ShellStep can be initialized."""
    from agentrails.steps.shell_step import ShellStep

    step = ShellStep(id="test", script="echo hello")
    assert step.id == "test"
    assert step.script == "echo hello"
    assert step.type == "shell"
