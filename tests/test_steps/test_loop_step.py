"""Tests for LoopStep class."""



def test_loop_step_initialization():
    """Test LoopStep can be initialized."""
    from agentrails.steps.loop_step import LoopStep
    from agentrails.steps.shell_step import ShellStep

    body = [ShellStep(id="attempt", script="echo attempt")]
    step = LoopStep(id="test", body=body, until="{{state.test.latest.attempt.return_code == 0}}")

    assert step.id == "test"
    assert step.type == "loop"
    assert len(step.body) == 1
