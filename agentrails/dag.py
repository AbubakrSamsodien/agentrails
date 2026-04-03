"""DAG data structure and algorithms for workflow execution."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


class CycleError(Exception):
    """Raised when a cycle is detected in the DAG."""


@dataclass
class DAG:
    """Directed Acyclic Graph for workflow step dependencies."""

    _adjacency: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _predecessors: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add_node(self, node_id: str) -> None:
        """Add a node to the DAG."""
        if node_id not in self._adjacency:
            self._adjacency[node_id] = []

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add a directed edge from from_id to to_id."""
        self.add_node(from_id)
        self.add_node(to_id)
        self._adjacency[from_id].append(to_id)
        self._predecessors[to_id].append(from_id)

    def topological_order(self) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm.

        Raises:
            CycleError: If the graph contains a cycle.
        """
        in_degree = defaultdict(int)
        for node in self._adjacency:
            in_degree[node] = len(self._predecessors[node])

        queue = deque([node for node in self._adjacency if in_degree[node] == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for successor in self._adjacency[node]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(result) != len(self._adjacency):
            raise CycleError("Graph contains a cycle")

        return result

    def ready_steps(self, completed: set[str]) -> list[str]:
        """Return steps whose dependencies are all in the completed set."""
        ready = []
        for node in self._adjacency:
            if node not in completed:
                preds = self._predecessors[node]
                if all(p in completed for p in preds):
                    ready.append(node)
        return ready

    def predecessors(self, node_id: str) -> list[str]:
        """Return all predecessors of a node."""
        return list(self._predecessors[node_id])

    def successors(self, node_id: str) -> list[str]:
        """Return all successors of a node."""
        return list(self._adjacency[node_id])

    def validate(self) -> list[str]:
        """Validate the DAG and return a list of errors.

        Checks for:
        - Orphan nodes (no path from any root)
        - Unreachable nodes
        """
        errors = []
        if not self._adjacency:
            return errors

        # Find roots (nodes with no predecessors)
        roots = [node for node in self._adjacency if not self._predecessors[node]]

        if not roots:
            errors.append("DAG has no root nodes (all nodes have predecessors)")
            return errors

        # BFS from roots to find all reachable nodes
        reachable = set()
        queue = deque(roots)
        while queue:
            node = queue.popleft()
            if node not in reachable:
                reachable.add(node)
                queue.extend(self._adjacency[node])

        # Find orphan nodes
        orphans = set(self._adjacency.keys()) - reachable
        if orphans:
            errors.append(f"Orphan nodes (unreachable from roots): {sorted(orphans)}")

        return errors

    def to_mermaid(self) -> str:
        """Export the DAG as a Mermaid diagram string."""
        lines = ["graph TD"]
        for node in self._adjacency:
            for successor in self._adjacency[node]:
                lines.append(f"    {node} --> {successor}")
        return "\n".join(lines)
