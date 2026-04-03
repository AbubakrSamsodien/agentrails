"""Tests for HumanStep class."""



def test_human_step_initialization():
    """Test HumanStep can be initialized."""
    from agentrails.steps.human_step import HumanStep

    step = HumanStep(id="test", message="Please review")
    assert step.id == "test"
    assert step.type == "human"
    assert step.message == "Please review"
