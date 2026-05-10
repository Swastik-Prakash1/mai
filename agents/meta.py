"""Meta-agent — self-improving prompt loop.

Reads the latest eval run, identifies the worst-performing agent×dimension,
and proposes a rewritten system prompt for human review.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import AgentMessage, SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)


class MetaAgent(BaseAgent):
    """Self-improving meta-agent.

    Analyzes eval results to propose prompt rewrites for underperforming agents.
    Does NOT auto-apply — creates PromptRewrite records for human review.
    """

    agent_id: str = "meta"
    max_context_budget: int = 4000
    system_prompt: str = (
        "You are a prompt engineering specialist. Given an agent's current system "
        "prompt and its failed test cases with scores, propose an improved prompt.\n\n"
        "Return JSON with keys:\n"
        "- proposed_prompt: string (the full rewritten prompt)\n"
        "- diff: array of {line: int, old: string, new: string}\n"
        "- justification: string (why these changes will help)\n"
        "- expected_improvement: string (which test cases should improve)"
    )

    async def propose_rewrite(
        self,
        agent_id: str,
        current_prompt: str,
        failed_cases: list[dict],
        worst_dimension: str,
    ) -> dict:
        """Propose a rewritten prompt for an underperforming agent.

        Args:
            agent_id: The agent to improve.
            current_prompt: Current system prompt text.
            failed_cases: List of failed test case dicts with scores.
            worst_dimension: The scoring dimension with lowest score.

        Returns:
            Dict with proposed_prompt, diff, justification, expected_improvement.
        """
        budget = BudgetManager()
        budget.declare_budget(self.agent_id, self.max_context_budget)
        context = SharedContext(job_id="meta_rewrite", query="prompt_improvement")

        failed_text = json.dumps(failed_cases, indent=2, default=str)

        response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Agent: {agent_id}\n"
                    f"Worst dimension: {worst_dimension}\n\n"
                    f"Current prompt:\n{current_prompt}\n\n"
                    f"Failed test cases:\n{failed_text}\n\n"
                    f"Propose a rewritten system prompt to improve performance on "
                    f"the '{worst_dimension}' dimension. Return JSON."
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=1000,
        )

        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            return json.loads(clean.strip())
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Failed to parse meta-agent response: {exc}")
            return {
                "proposed_prompt": current_prompt,
                "diff": [],
                "justification": f"Parse error: {exc}",
                "expected_improvement": "None — parse failed",
            }

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        """Not used directly — use propose_rewrite() instead."""
        return context
