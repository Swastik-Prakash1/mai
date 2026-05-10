"""Decomposition agent — breaks queries into typed sub-tasks with dependency graph.

Uses Claude to decompose a query, then performs topological sort on the
resulting dependency graph to determine execution order.
"""

from __future__ import annotations

import json
from collections import deque

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import AgentMessage, SharedContext, SubTask
from logging_.structured import get_logger

logger = get_logger(__name__)


def topological_sort(sub_tasks: list[SubTask]) -> list[SubTask]:
    """Topological sort of sub-tasks respecting dependency edges.

    Uses Kahn's algorithm (BFS-based). If the graph has a cycle,
    returns tasks in best-effort order with remaining tasks appended.

    Args:
        sub_tasks: List of SubTask with id and dependencies fields.

    Returns:
        Sub-tasks in valid execution order.
    """
    task_map = {t.id: t for t in sub_tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in sub_tasks}
    adjacency: dict[str, list[str]] = {t.id: [] for t in sub_tasks}

    for task in sub_tasks:
        for dep_id in task.dependencies:
            if dep_id in adjacency:
                adjacency[dep_id].append(task.id)
                in_degree[task.id] += 1

    queue: deque[str] = deque()
    for task_id, degree in in_degree.items():
        if degree == 0:
            queue.append(task_id)

    sorted_ids: list[str] = []
    while queue:
        current = queue.popleft()
        sorted_ids.append(current)
        for neighbor in adjacency.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Append any remaining tasks (cycle detected) in original order
    remaining = [t.id for t in sub_tasks if t.id not in sorted_ids]
    if remaining:
        logger.warning(
            f"Dependency cycle detected, appending {len(remaining)} tasks at end"
        )
    sorted_ids.extend(remaining)

    return [task_map[tid] for tid in sorted_ids]


class DecompositionAgent(BaseAgent):
    """Breaks a query into typed sub-tasks with a dependency graph.

    Sub-task types: FACTUAL_LOOKUP, CODE_TASK, ANALYSIS, COMPARISON, SYNTHESIS
    Each sub-task has dependencies forming a DAG, sorted via topological sort.
    """

    agent_id: str = "decomposition"
    max_context_budget: int = 4000
    system_prompt: str = (
        "You are a query decomposition specialist. Break complex queries into "
        "atomic sub-tasks that can be executed by specialized agents.\n\n"
        "For each sub-task, determine:\n"
        "1. A unique ID (e.g., 'st_1', 'st_2')\n"
        "2. Type: FACTUAL_LOOKUP | CODE_TASK | ANALYSIS | COMPARISON | SYNTHESIS\n"
        "3. A clear description of what needs to be done\n"
        "4. Dependencies: list of sub-task IDs that must complete first\n\n"
        "Return ONLY valid JSON array of objects with keys: "
        "id, type, description, dependencies.\n"
        "Example: [{\"id\": \"st_1\", \"type\": \"FACTUAL_LOOKUP\", "
        "\"description\": \"Look up the capital of France\", \"dependencies\": []}]"
    )

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        # Record input
        context.messages.append(
            AgentMessage(
                agent_id=self.agent_id,
                content=context.query,
                token_count=0,
                message_type="input",
            )
        )

        # Call LLM to decompose
        response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Decompose this query into sub-tasks:\n\n"
                    f"Query: {context.query}\n\n"
                    f"Return a JSON array of sub-tasks."
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=800,
        )

        # Parse response
        try:
            # Strip markdown fences
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            clean = clean.strip()

            tasks_data = json.loads(clean)
            if not isinstance(tasks_data, list):
                tasks_data = [tasks_data]

            sub_tasks = []
            for td in tasks_data:
                sub_tasks.append(SubTask(
                    id=td.get("id", f"st_{len(sub_tasks)+1}"),
                    type=td.get("type", "ANALYSIS"),
                    description=td.get("description", ""),
                    dependencies=td.get("dependencies", []),
                ))
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Failed to parse decomposition response: {exc}")
            # Fallback: create a single task
            sub_tasks = [
                SubTask(
                    id="st_1",
                    type="ANALYSIS",
                    description=context.query,
                    dependencies=[],
                )
            ]

        # Topological sort
        sorted_tasks = topological_sort(sub_tasks)
        context.sub_tasks = sorted_tasks

        logger.info(
            "Decomposition complete",
            extra={
                "extra_data": {
                    "num_subtasks": len(sorted_tasks),
                    "task_types": [t.type for t in sorted_tasks],
                }
            },
        )

        return context
