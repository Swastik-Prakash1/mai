"""BaseAgent abstract base class.

All agents inherit from this. They:
1. Declare agent_id, max_context_budget, and system_prompt
2. Implement execute() which receives and returns SharedContext
3. Use call_llm() for all Anthropic API interactions (with structured logging)
"""

from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import anthropic

from context.budget_manager import BudgetManager, count_tokens
from context.shared_context import AgentMessage, SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for all NeuroMesh agents."""

    agent_id: str = "base"
    max_context_budget: int = 4000
    system_prompt: str = "You are a helpful AI assistant."

    @abstractmethod
    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        """Execute agent logic. Must return the (possibly modified) SharedContext."""
        ...

    async def call_llm(
        self,
        messages: list[dict],
        context: SharedContext,
        budget: BudgetManager,
        max_tokens: int = 1000,
        system: str | None = None,
    ) -> str:
        """Wrap Anthropic API call with structured logging and budget tracking.

        Args:
            messages: List of {role, content} dicts for the API.
            context: SharedContext to log to.
            budget: BudgetManager to track token consumption.
            max_tokens: Maximum output tokens.
            system: Optional system prompt override.

        Returns:
            The text response from the LLM.
        """
        sys_prompt = system or self.system_prompt
        start = time.perf_counter()

        # Track input tokens
        input_text = sys_prompt + " ".join(m.get("content", "") for m in messages)
        budget.consume(self.agent_id, input_text)

        try:
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
            )
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=sys_prompt,
                messages=messages,
            )
            output_text = response.content[0].text
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "LLM call failed",
                extra={
                    "extra_data": {
                        "agent_id": self.agent_id,
                        "error": str(exc),
                        "latency_ms": round(elapsed, 2),
                    }
                },
            )
            raise

        elapsed = (time.perf_counter() - start) * 1000

        # Track output tokens
        output_tokens = count_tokens(output_text)
        budget.consume(self.agent_id, output_text)

        # Log the call
        input_hash = hashlib.sha256(input_text.encode()).hexdigest()[:16]
        output_hash = hashlib.sha256(output_text.encode()).hexdigest()[:16]

        # Record as AgentMessage
        context.messages.append(
            AgentMessage(
                agent_id=self.agent_id,
                content=output_text,
                token_count=output_tokens,
                message_type="output",
                metadata={
                    "input_hash": input_hash,
                    "output_hash": output_hash,
                    "latency_ms": round(elapsed, 2),
                    "model": "claude-sonnet-4-20250514",
                },
            )
        )

        logger.info(
            "LLM call completed",
            extra={
                "extra_data": {
                    "agent_id": self.agent_id,
                    "input_hash": input_hash,
                    "output_hash": output_hash,
                    "latency_ms": round(elapsed, 2),
                    "output_tokens": output_tokens,
                }
            },
        )

        return output_text
