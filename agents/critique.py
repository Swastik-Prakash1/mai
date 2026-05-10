"""Critique agent — span-level confidence scoring and flagging.

Receives all prior agent outputs from SharedContext, assigns confidence
scores to specific text spans, and flags disagreements with suggested fixes.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import AgentMessage, Critique, SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)


class CritiqueAgent(BaseAgent):
    """Span-level critique agent.

    For each claim in prior outputs, assigns a confidence score (0.0-1.0)
    and flags specific text spans — never flags entire outputs.
    """

    agent_id: str = "critique"
    max_context_budget: int = 5000
    system_prompt: str = (
        "You are a critical analysis specialist. Review agent outputs for:\n"
        "1. Factual accuracy\n"
        "2. Internal contradictions between different agents' outputs\n"
        "3. Unsupported claims (not backed by retrieved data)\n"
        "4. Overstated certainty\n\n"
        "For EACH issue found, flag the SPECIFIC text span (not the entire output).\n"
        "Assign a confidence score (0.0 = certainly wrong, 1.0 = certainly correct).\n\n"
        "Return ONLY a JSON array of objects with keys:\n"
        "- source_agent_id: which agent produced the flagged text\n"
        "- flagged_span: the EXACT text span you are flagging (a few words to a sentence)\n"
        "- confidence: float 0.0-1.0\n"
        "- reason: why this span is flagged\n"
        "- suggested_fix: how to correct or improve it\n\n"
        "If no issues found, return an empty array: []"
    )

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        # Gather all prior agent outputs
        agent_outputs: list[str] = []
        for msg in context.messages:
            if msg.message_type == "output" and msg.agent_id != self.agent_id:
                agent_outputs.append(
                    f"[Agent: {msg.agent_id}]\n{msg.content}"
                )

        if not agent_outputs:
            logger.info("No prior outputs to critique")
            return context

        combined = "\n\n---\n\n".join(agent_outputs)

        # Also include retrieved chunks for cross-referencing
        chunks_text = ""
        if context.retrieved_chunks:
            chunks_text = "\n\nRetrieved evidence:\n" + "\n".join(
                f"[{c.chunk_id}]: {c.content}" for c in context.retrieved_chunks
            )

        response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Review these agent outputs for issues:\n\n"
                    f"{combined}\n{chunks_text}\n\n"
                    f"Flag specific spans with confidence scores. "
                    f"Return JSON array of critique objects."
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=800,
        )

        # Parse critiques
        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            critiques_data = json.loads(clean.strip())
            if not isinstance(critiques_data, list):
                critiques_data = [critiques_data]

            for cd in critiques_data:
                critique = Critique(
                    source_agent_id=cd.get("source_agent_id", "unknown"),
                    flagged_span=cd.get("flagged_span", ""),
                    confidence=float(cd.get("confidence", 0.5)),
                    reason=cd.get("reason", ""),
                    suggested_fix=cd.get("suggested_fix", ""),
                )
                context.critiques.append(critique)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(f"Failed to parse critique response: {exc}")

        logger.info(
            "Critique complete",
            extra={
                "extra_data": {
                    "critiques_found": len(context.critiques),
                    "agents_reviewed": len(agent_outputs),
                }
            },
        )

        return context
