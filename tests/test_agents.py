"""Unit tests for the decomposition agent (no LLM calls)."""

import pytest

from agents.decomposition import topological_sort
from context.shared_context import SubTask


class TestTopologicalSort:
    """Test Kahn's algorithm topological sort."""

    def test_linear_chain(self):
        tasks = [
            SubTask(id="st_1", type="ANALYSIS", description="first", dependencies=[]),
            SubTask(id="st_2", type="ANALYSIS", description="second", dependencies=["st_1"]),
            SubTask(id="st_3", type="ANALYSIS", description="third", dependencies=["st_2"]),
        ]
        sorted_tasks = topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids == ["st_1", "st_2", "st_3"]

    def test_diamond_dag(self):
        tasks = [
            SubTask(id="st_1", type="ANALYSIS", description="root", dependencies=[]),
            SubTask(id="st_2", type="ANALYSIS", description="left", dependencies=["st_1"]),
            SubTask(id="st_3", type="ANALYSIS", description="right", dependencies=["st_1"]),
            SubTask(id="st_4", type="ANALYSIS", description="merge", dependencies=["st_2", "st_3"]),
        ]
        sorted_tasks = topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids[0] == "st_1"
        assert ids[-1] == "st_4"
        assert ids.index("st_2") < ids.index("st_4")
        assert ids.index("st_3") < ids.index("st_4")

    def test_no_dependencies(self):
        tasks = [
            SubTask(id="st_1", type="ANALYSIS", description="a", dependencies=[]),
            SubTask(id="st_2", type="ANALYSIS", description="b", dependencies=[]),
        ]
        sorted_tasks = topological_sort(tasks)
        assert len(sorted_tasks) == 2

    def test_single_task(self):
        tasks = [SubTask(id="st_1", type="ANALYSIS", description="only", dependencies=[])]
        sorted_tasks = topological_sort(tasks)
        assert len(sorted_tasks) == 1
        assert sorted_tasks[0].id == "st_1"

    def test_empty_list(self):
        sorted_tasks = topological_sort([])
        assert sorted_tasks == []

    def test_cycle_handling(self):
        """Cycle should not crash — remaining tasks appended."""
        tasks = [
            SubTask(id="st_1", type="ANALYSIS", description="a", dependencies=["st_2"]),
            SubTask(id="st_2", type="ANALYSIS", description="b", dependencies=["st_1"]),
        ]
        sorted_tasks = topological_sort(tasks)
        assert len(sorted_tasks) == 2  # Both present, no crash
