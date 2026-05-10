"""Self-reflection tool — checks agent outputs for contradictions.

Takes an agent_id and a check_for description, reads that agent's prior
outputs from SharedContext, and uses Claude to identify inconsistencies.

Failure contract:
- EMPTY: agent has no prior outputs in SharedContext
- MALFORMED: check_for is empty string
"""

from __future__ import annotations

import os

import anthropic

from tools.base import BaseTool, ToolResult
from context.shared_context import SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)


class SelfReflectionTool(BaseTool):
    """Analyzes an agent's prior outputs for contradictions and inconsistencies.

    Uses Claude to perform the analysis, providing structured results about
    any contradictions found.

    Failure contract:
    - EMPTY: if agent has no prior outputs
    - MALFORMED: if check_for is empty string
    """

    name: str = "self_reflection"

    def __init__(self, context: SharedContext | None = None) -> None:
        self._context = context

    def set_context(self, context: SharedContext) -> None:
        """Set the SharedContext to read agent outputs from."""
        self._context = context

    async def call(self, input: dict) -> ToolResult:
        if "agent_id" not in input:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Input must contain 'agent_id' key",
            )
        if "check_for" not in input or not str(input["check_for"]).strip():
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Input must contain non-empty 'check_for' key",
            )

        agent_id = input["agent_id"]
        check_for = input["check_for"]

        if self._context is None:
            return ToolResult(
                success=False,
                error_code="EMPTY",
                error_message="No SharedContext available",
            )

        # Gather prior outputs from the specified agent
        prior_outputs = [
            msg.content
            for msg in self._context.messages
            if msg.agent_id == agent_id and msg.message_type == "output"
        ]

        if not prior_outputs:
            return ToolResult(
                success=False,
                error_code="EMPTY",
                error_message=f"Agent '{agent_id}' has no prior outputs in context",
            )

        # Use Claude to analyze for contradictions
        try:
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
            )
            combined_outputs = "\n---\n".join(prior_outputs)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Analyze these outputs from agent '{agent_id}' for "
                        f"contradictions or inconsistencies related to: {check_for}\n\n"
                        f"Outputs:\n{combined_outputs}\n\n"
                        f"Return JSON: {{\"contradictions_found\": bool, "
                        f"\"details\": [str], \"flagged_spans\": [str]}}\n"
                        f"Return ONLY the JSON, no explanation."
                    ),
                }],
            )

            import json
            result_text = response.content[0].text.strip()
            # Strip markdown fences
            result_text = result_text.strip("`")
            if result_text.startswith("json"):
                result_text = result_text[4:].strip()
            parsed = json.loads(result_text)

            return ToolResult(
                success=True,
                data=parsed,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error_code="EXEC_ERROR",
                error_message=f"Self-reflection analysis failed: {exc}",
            )
