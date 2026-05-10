"""Context compression agent — triggered on budget overflow.

Lossless for: tool outputs, scores, citations, structured data.
Lossy only for: conversational filler, redundant explanations.
Uses Claude to summarize only the lossy parts.
"""

from __future__ import annotations

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import AgentMessage, SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)


class CompressionAgent(BaseAgent):
    """Compresses context when an agent would overflow its budget.

    Preserves structured data (tool outputs, scores, citations) verbatim.
    Summarizes only conversational filler and redundant explanations.
    """

    agent_id: str = "compression"
    max_context_budget: int = 3000
    system_prompt: str = (
        "You are a context compression specialist. Given a set of agent messages, "
        "compress them while preserving ALL of the following verbatim:\n"
        "- Tool call results and data\n"
        "- Numerical scores, metrics, and statistics\n"
        "- Citations and chunk_ids\n"
        "- Structured data (JSON, tables)\n\n"
        "You may summarize ONLY:\n"
        "- Conversational filler and pleasantries\n"
        "- Redundant explanations that repeat the same point\n"
        "- Verbose reasoning that can be condensed\n\n"
        "Return the compressed content as a single string."
    )

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        # Gather all output messages that could be compressed
        compressible_messages = [
            msg for msg in context.messages
            if msg.message_type == "output" and msg.agent_id != self.agent_id
        ]

        if not compressible_messages:
            return context

        combined = "\n\n".join(
            f"[{msg.agent_id}]: {msg.content}" for msg in compressible_messages
        )

        compressed = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Compress these agent outputs while preserving all structured data, "
                    f"citations, and tool results verbatim:\n\n{combined}"
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=800,
        )

        # Replace compressible messages with single compressed message
        context.messages = [
            msg for msg in context.messages
            if msg.message_type != "output" or msg.agent_id == self.agent_id
        ]
        context.messages.append(
            AgentMessage(
                agent_id=self.agent_id,
                content=compressed,
                token_count=0,
                message_type="output",
                metadata={"compressed": True, "original_count": len(compressible_messages)},
            )
        )

        logger.info(
            "Compression complete",
            extra={
                "extra_data": {
                    "original_messages": len(compressible_messages),
                    "compressed_length": len(compressed),
                }
            },
        )

        return context
