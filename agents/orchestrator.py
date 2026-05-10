"""Master orchestrator agent — dynamic routing and agent coordination.

Decides which agents to invoke, in what order, with what budget allocation.
Agents NEVER call each other — only the orchestrator calls agents.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent
from agents.compression import CompressionAgent
from agents.critique import CritiqueAgent
from agents.decomposition import DecompositionAgent
from agents.retrieval import RetrievalAgent
from agents.synthesis import SynthesisAgent
from context.budget_manager import BudgetManager
from context.shared_context import (
    AgentMessage,
    OrchestratorDecision,
    SharedContext,
)
from logging_.structured import get_logger

logger = get_logger(__name__)

# Registry of available agents (exclude orchestrator itself)
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "decomposition": DecompositionAgent,
    "retrieval": RetrievalAgent,
    "critique": CritiqueAgent,
    "synthesis": SynthesisAgent,
}


class OrchestratorAgent(BaseAgent):
    """Master orchestrator that plans and executes multi-agent pipelines.

    Uses Claude to create an execution plan, then runs agents in sequence.
    If critique flags contradictions, re-invokes the relevant agent (1 retry).
    """

    agent_id: str = "orchestrator"
    max_context_budget: int = 8000
    system_prompt: str = (
        "You are the master orchestrator for a multi-agent system. "
        "Given a user query, decide which agents to invoke and in what order.\n\n"
        "Available agents:\n"
        "- decomposition: breaks queries into typed sub-tasks\n"
        "- retrieval: multi-hop search and knowledge retrieval\n"
        "- critique: reviews outputs for contradictions and errors\n"
        "- synthesis: produces final answer with provenance\n\n"
        "Return a JSON execution plan:\n"
        "{\"plan\": [\n"
        "  {\"agent\": \"decomposition\", \"budget\": 4000, "
        "\"rationale\": \"...\", \"context_keys\": [\"query\"]},\n"
        "  ...\n"
        "]}"
    )

    def __init__(self) -> None:
        self._agents = {name: cls() for name, cls in AGENT_REGISTRY.items()}
        self._compression = CompressionAgent()

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        # Step 1: Create execution plan via LLM
        plan = await self._create_plan(context, budget)

        # Step 2: Execute agents in planned order
        step_num = 0
        for step in plan:
            agent_name = step.get("agent", "")
            agent = self._agents.get(agent_name)
            if not agent:
                logger.warning(f"Unknown agent in plan: {agent_name}")
                continue

            step_num += 1
            step_budget = step.get("budget", agent.max_context_budget)

            # Log decision
            decision = OrchestratorDecision(
                step=step_num,
                agent=agent_name,
                action="invoke",
                rationale=step.get("rationale", ""),
                budget_allocated=step_budget,
                context_keys=step.get("context_keys", []),
            )
            context.orchestrator_log.append(decision)

            logger.info(
                f"Orchestrator invoking {agent_name}",
                extra={
                    "extra_data": {
                        "step": step_num,
                        "agent": agent_name,
                        "budget": step_budget,
                    }
                },
            )

            # Execute agent
            context = await agent.execute(context, budget)

            # Check for budget overflow → trigger compression
            if budget.is_overflow(agent_name):
                budget.record_violation(agent_name, context)
                logger.info(f"Triggering compression for {agent_name}")
                context = await self._compression.execute(context, budget)

        # Step 3: If critique flagged contradictions, re-invoke relevant agent
        if context.critiques:
            flagged_agents = set(c.source_agent_id for c in context.critiques)
            for agent_name in flagged_agents:
                if agent_name in self._agents and agent_name != "critique":
                    step_num += 1
                    decision = OrchestratorDecision(
                        step=step_num,
                        agent=agent_name,
                        action="retry_after_critique",
                        rationale=f"Critique flagged {len([c for c in context.critiques if c.source_agent_id == agent_name])} spans",
                    )
                    context.orchestrator_log.append(decision)

                    logger.info(f"Re-invoking {agent_name} after critique")
                    context = await self._agents[agent_name].execute(context, budget)
                    break  # One retry max

            # Re-run synthesis after retry
            if "synthesis" in self._agents:
                step_num += 1
                decision = OrchestratorDecision(
                    step=step_num,
                    agent="synthesis",
                    action="re-synthesis_after_critique",
                    rationale="Re-synthesizing after critique-driven retry",
                )
                context.orchestrator_log.append(decision)
                context = await self._agents["synthesis"].execute(context, budget)

        return context

    async def _create_plan(
        self, context: SharedContext, budget: BudgetManager
    ) -> list[dict]:
        """Use Claude to create an execution plan for the query."""
        response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Create an execution plan for this query:\n\n"
                    f"Query: {context.query}\n\n"
                    f"Which agents should I invoke, in what order, "
                    f"and with what budget allocation?"
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=500,
        )

        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            parsed = json.loads(clean.strip())
            plan = parsed.get("plan", [])
            if isinstance(plan, list) and plan:
                return plan
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Failed to parse orchestrator plan: {exc}")

        # Default plan if LLM fails
        return [
            {"agent": "decomposition", "budget": 4000, "rationale": "Default: decompose first", "context_keys": ["query"]},
            {"agent": "retrieval", "budget": 6000, "rationale": "Default: retrieve information", "context_keys": ["query", "sub_tasks"]},
            {"agent": "critique", "budget": 5000, "rationale": "Default: critique outputs", "context_keys": ["messages"]},
            {"agent": "synthesis", "budget": 6000, "rationale": "Default: synthesize final answer", "context_keys": ["messages", "critiques", "retrieved_chunks"]},
        ]
