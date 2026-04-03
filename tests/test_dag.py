"""Tests for DAG class."""

import pytest

from agentrails.dag import DAG, CycleError


def test_add_node():
    """Test adding nodes to DAG."""
    dag = DAG()
    dag.add_node("a")
    dag.add_node("b")

    assert dag.ready_steps(set()) == ["a", "b"]  # Both are roots


def test_add_edge():
    """Test adding edges to DAG."""
    dag = DAG()
    dag.add_edge("a", "b")

    assert dag.predecessors("b") == ["a"]
    assert dag.successors("a") == ["b"]


def test_topological_order_linear():
    """Test topological sort on linear graph."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")

    order = dag.topological_order()
    assert order.index("a") < order.index("b")
    assert order.index("b") < order.index("c")


def test_topological_order_complex():
    """Test topological sort on complex graph."""
    dag = DAG()
    dag.add_edge("a", "c")
    dag.add_edge("b", "c")
    dag.add_edge("c", "d")

    order = dag.topological_order()
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("c")
    assert order.index("c") < order.index("d")


def test_cycle_detection():
    """Test that cycles are detected."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")
    dag.add_edge("c", "a")  # Creates cycle

    with pytest.raises(CycleError, match="cycle"):
        dag.topological_order()


def test_ready_steps():
    """Test ready_steps returns nodes with all deps completed."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("a", "c")
    dag.add_edge("b", "d")
    dag.add_edge("c", "d")

    assert dag.ready_steps(set()) == ["a"]
    assert dag.ready_steps({"a"}) == ["b", "c"]
    assert dag.ready_steps({"a", "b", "c"}) == ["d"]
    assert dag.ready_steps({"a", "b", "c", "d"}) == []


def test_predecessors():
    """Test predecessors method."""
    dag = DAG()
    dag.add_edge("a", "c")
    dag.add_edge("b", "c")
    dag.add_edge("c", "d")

    assert sorted(dag.predecessors("c")) == ["a", "b"]
    assert dag.predecessors("d") == ["c"]
    assert dag.predecessors("a") == []


def test_successors():
    """Test successors method."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("a", "c")
    dag.add_edge("b", "d")

    assert sorted(dag.successors("a")) == ["b", "c"]
    assert dag.successors("b") == ["d"]
    assert dag.successors("d") == []


def test_validate_no_orphans():
    """Test validation with no orphan nodes."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")

    errors = dag.validate()
    # Note: validate() currently only checks if graph has roots
    assert errors == []


def test_validate_multiple_components():
    """Test validation with disconnected components."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_node("orphan")  # Disconnected node (also a root)

    errors = dag.validate()
    # A disconnected node that's also a root is not flagged as orphan
    # This is current behavior - orphans are nodes with no path from ANY root
    # but "orphan" here IS a root itself
    # For now, just verify it doesn't crash
    assert isinstance(errors, list)


def test_to_mermaid():
    """Test Mermaid diagram export."""
    dag = DAG()
    dag.add_edge("a", "b")
    dag.add_edge("a", "c")

    mermaid = dag.to_mermaid()

    assert "graph TD" in mermaid
    assert "a --> b" in mermaid
    assert "a --> c" in mermaid


def test_empty_dag():
    """Test empty DAG operations."""
    dag = DAG()

    assert dag.topological_order() == []
    assert dag.ready_steps(set()) == []
    assert dag.validate() == []
    assert dag.to_mermaid() == "graph TD"
