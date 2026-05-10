"""Synthesis agent — contradiction resolution and provenance mapping.

Receives full SharedContext including critiques. Resolves contradictions
explicitly, produces final_answer with sentence-level provenance map.
"""

from __future__ import annotations

import json

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import (
    AgentMessage,
    ProvenanceEntry,
    SharedContext,
)
from logging_.structured import get_logger

logger = get_logger(__name__)


class SynthesisAgent(BaseAgent):
    """Synthesis agent that resolves contradictions and maps provenance.

    For each contradiction flagged by critique agent, explicitly resolves it.
    Produces a final_answer with sentence-level provenance tracking.
    """

    agent_id: str = "synthesis"
    max_context_budget: int = 6000
    system_prompt: str = (
        "You are a synthesis specialist. Produce a coherent final answer by:\n"
        "1. Resolving ALL contradictions flagged by the critique agent\n"
        "2. For each contradiction: choose one side OR merge both with justification\n"
        "3. NEVER surface raw contradictions — the user should see a resolved answer\n"
        "4. Cite sources using [chunk_id] notation for every factual claim\n\n"
        "Return JSON with keys:\n"
        "- final_answer: string (the complete, resolved answer)\n"
        "- provenance: array of objects with keys:\n"
        "  - sentence_id: int (0-indexed)\n"
        "  - sentence_text: string\n"
        "  - source_agent_id: string\n"
        "  - source_chunk_id: string or null\n"
        "  - confidence: float 0.0-1.0"
    )

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        # Gather all agent outputs
        agent_outputs = "\n\n".join(
            f"[{msg.agent_id}]: {msg.content}"
            for msg in context.messages
            if msg.message_type == "output"
        )

        # Gather critiques
        critiques_text = ""
        if context.critiques:
            critiques_text = "\n\nCritiques to resolve:\n" + "\n".join(
                f"- [{c.source_agent_id}] flagged '{c.flagged_span}' "
                f"(confidence: {c.confidence}): {c.reason}. Fix: {c.suggested_fix}"
                for c in context.critiques
            )

        # Gather chunks for citation
        chunks_text = ""
        if context.retrieved_chunks:
            chunks_text = "\n\nAvailable chunks for citation:\n" + "\n".join(
                f"[{c.chunk_id}]: {c.content}" for c in context.retrieved_chunks
            )

        response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Original query: {context.query}\n\n"
                    f"Agent outputs:\n{agent_outputs}\n"
                    f"{critiques_text}\n"
                    f"{chunks_text}\n\n"
                    f"Produce the final synthesized answer with provenance map. "
                    f"Return JSON with 'final_answer' and 'provenance' keys."
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=1000,
        )

        # Parse response
        try:
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            parsed = json.loads(clean.strip())

            final_answer = parsed.get("final_answer", response)
            provenance_data = parsed.get("provenance", [])

            context.final_answer = final_answer

            for p in provenance_data:
                entry = ProvenanceEntry(
                    sentence_id=p.get("sentence_id", 0),
                    sentence_text=p.get("sentence_text", ""),
                    source_agent_id=p.get("source_agent_id", "synthesis"),
                    source_chunk_id=p.get("source_chunk_id"),
                    confidence=float(p.get("confidence", 0.5)),
                )
                context.provenance_map.append(entry)

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(f"Failed to parse synthesis JSON: {exc}")
            # Use raw response as final answer
            context.final_answer = response
            context.provenance_map.append(
                ProvenanceEntry(
                    sentence_id=0,
                    sentence_text=response[:200],
                    source_agent_id=self.agent_id,
                    confidence=0.5,
                )
            )

        logger.info(
            "Synthesis complete",
            extra={
                "extra_data": {
                    "answer_length": len(context.final_answer or ""),
                    "provenance_entries": len(context.provenance_map),
                    "contradictions_resolved": len(context.critiques),
                }
            },
        )

        return context
