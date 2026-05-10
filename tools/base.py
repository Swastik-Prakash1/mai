"""BaseTool ABC with ToolResult schema and failure contract.

Every tool must:
1. Return a ToolResult, never raise exceptions to the caller
2. Declare failure modes in its class docstring (the "failure contract")
3. Record all calls in SharedContext.tool_calls via the wrapper
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from pydantic import BaseModel

from context.shared_context import SharedContext, ToolCallRecord
from logging_.structured import get_logger

logger = get_logger(__name__)


class ToolResult(BaseModel):
    """Standardized result from any tool invocation.

    Every tool returns this — success or failure. Callers never see raw exceptions.
    """

    success: bool
    data: dict | None = None
    error_code: str | None = None  # TIMEOUT | EMPTY | MALFORMED | EXEC_ERROR
    error_message: str | None = None
    latency_ms: float = 0.0


class BaseTool(ABC):
    """Abstract base for all tools.

    Subclasses must implement `call()` and declare their failure contract
    as the class docstring. The `execute()` wrapper handles timing, logging,
    and recording to SharedContext.
    """

    name: str = "base_tool"

    @abstractmethod
    async def call(self, input: dict) -> ToolResult:
        """Execute the tool logic. Must return ToolResult, never raise."""
        ...

    async def execute(
        self,
        input: dict,
        context: SharedContext,
        agent_id: str,
        retry_number: int = 0,
    ) -> ToolResult:
        """Wrapper that times the call, logs it, and records to SharedContext.

        Args:
            input: Tool-specific input dict.
            context: SharedContext to record the call in.
            agent_id: ID of the agent making this tool call.
            retry_number: 0 for first attempt, 1+ for retries.

        Returns:
            ToolResult from the underlying call().
        """
        start = time.perf_counter()
        try:
            result = await self.call(input)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            result = ToolResult(
                success=False,
                error_code="EXEC_ERROR",
                error_message=str(exc),
                latency_ms=elapsed,
            )

        elapsed = (time.perf_counter() - start) * 1000
        result.latency_ms = elapsed

        record = ToolCallRecord(
            tool_name=self.name,
            input=input,
            output=result.model_dump() if result else None,
            latency_ms=elapsed,
            success=result.success,
            failure_reason=result.error_code if not result.success else None,
            retry_number=retry_number,
            agent_accepted=True,
        )
        context.tool_calls.append(record)

        logger.info(
            "Tool call completed",
            extra={
                "extra_data": {
                    "tool_name": self.name,
                    "agent_id": agent_id,
                    "success": result.success,
                    "latency_ms": round(elapsed, 2),
                    "retry": retry_number,
                    "error_code": result.error_code,
                }
            },
        )

        return result
