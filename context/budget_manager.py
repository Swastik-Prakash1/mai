"""Token budget tracker using tiktoken.

Each agent declares a token budget before execution. The BudgetManager tracks
consumption and flags violations — it never silently truncates. Overflow triggers
the compression agent.
"""

from __future__ import annotations

import tiktoken

from logging_ .structured import get_logger
from context.shared_context import PolicyViolation, SharedContext

logger = get_logger(__name__)

# cl100k_base is the encoding used by Claude-family models for counting purposes.
# While not an exact match, it provides a reasonable proxy for budget enforcement.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using cl100k_base encoding."""
    return len(_ENCODING.encode(text))


class BudgetManager:
    """Tracks per-agent token budgets and flags violations.

    Usage:
        bm = BudgetManager()
        bm.declare_budget("retrieval", 6000)
        remaining = bm.consume("retrieval", some_text)
        if bm.is_overflow("retrieval"):
            bm.record_violation("retrieval", shared_context)
    """

    def __init__(self) -> None:
        self._budgets: dict[str, int] = {}  # agent_id → max tokens
        self._consumed: dict[str, int] = {}  # agent_id → tokens used so far

    def declare_budget(self, agent_id: str, max_tokens: int) -> None:
        """Register an agent's token budget.

        Args:
            agent_id: Unique identifier for the agent.
            max_tokens: Maximum tokens this agent may consume.
        """
        self._budgets[agent_id] = max_tokens
        self._consumed.setdefault(agent_id, 0)
        logger.info(
            "Budget declared",
            extra={"extra_data": {"agent_id": agent_id, "max_tokens": max_tokens}},
        )

    def consume(self, agent_id: str, text: str) -> int:
        """Count tokens in text, deduct from budget, return remaining.

        Args:
            agent_id: The agent consuming tokens.
            text: The text whose tokens to count.

        Returns:
            Number of tokens remaining in the agent's budget (may be negative).
        """
        tokens = count_tokens(text)
        self._consumed[agent_id] = self._consumed.get(agent_id, 0) + tokens
        remaining = self.check_remaining(agent_id)
        logger.info(
            "Tokens consumed",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "tokens_consumed": tokens,
                    "remaining": remaining,
                }
            },
        )
        return remaining

    def check_remaining(self, agent_id: str) -> int:
        """Return how many tokens the agent has left. Negative means overflow."""
        max_tokens = self._budgets.get(agent_id, 0)
        used = self._consumed.get(agent_id, 0)
        return max_tokens - used

    def is_overflow(self, agent_id: str) -> bool:
        """Check whether the agent has exceeded its token budget."""
        return self.check_remaining(agent_id) < 0

    def get_consumed(self, agent_id: str) -> int:
        """Return total tokens consumed by an agent so far."""
        return self._consumed.get(agent_id, 0)

    def record_violation(self, agent_id: str, context: SharedContext) -> None:
        """Append a PolicyViolation to the SharedContext.

        Called when an agent overflows — this is NOT silent truncation.
        The orchestrator must then invoke the compression agent.
        """
        used = self._consumed.get(agent_id, 0)
        allowed = self._budgets.get(agent_id, 0)
        violation = PolicyViolation(
            agent_id=agent_id,
            violation_type="budget_overflow",
            details=(
                f"Agent '{agent_id}' consumed {used} tokens "
                f"but budget is {allowed} tokens (overflow by {used - allowed})"
            ),
            tokens_used=used,
            tokens_allowed=allowed,
        )
        context.policy_violations.append(violation)
        logger.warning(
            "Policy violation recorded",
            extra={
                "extra_data": {
                    "agent_id": agent_id,
                    "tokens_used": used,
                    "tokens_allowed": allowed,
                }
            },
        )
