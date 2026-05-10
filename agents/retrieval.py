"""Retrieval agent — multi-hop RAG with citation tracking.

Performs at minimum 2 tool calls to web_search:
1. Initial query → get chunks
2. Follow-up query based on gaps → get more chunks
Each chunk is tracked with hop_number for provenance.
"""

from __future__ import annotations

import json
import uuid

from agents.base import BaseAgent
from context.budget_manager import BudgetManager
from context.shared_context import AgentMessage, Chunk, SharedContext
from tools.web_search import WebSearchTool
from logging_.structured import get_logger

logger = get_logger(__name__)


class RetrievalAgent(BaseAgent):
    """Multi-hop retrieval agent with citation tracking.

    Always performs at least 2 search hops:
    - Hop 1: Initial query search
    - Hop 2: Gap-filling follow-up search based on first results
    """

    agent_id: str = "retrieval"
    max_context_budget: int = 6000
    system_prompt: str = (
        "You are a retrieval specialist. Given search results, identify information "
        "gaps and formulate follow-up queries to fill them. When synthesizing answers, "
        "cite specific chunk_ids for every claim.\n\n"
        "Return your analysis as JSON with keys:\n"
        "- follow_up_query: string (query for second hop search)\n"
        "- reasoning: string (why this follow-up is needed)"
    )

    def __init__(self) -> None:
        self._search_tool = WebSearchTool()

    async def execute(
        self, context: SharedContext, budget: BudgetManager
    ) -> SharedContext:
        budget.declare_budget(self.agent_id, self.max_context_budget)

        context.messages.append(
            AgentMessage(
                agent_id=self.agent_id,
                content=context.query,
                token_count=0,
                message_type="input",
            )
        )

        # HOP 1: Initial search
        hop1_result = await self._search_tool.execute(
            input={"query": context.query},
            context=context,
            agent_id=self.agent_id,
        )

        hop1_chunks: list[Chunk] = []
        if hop1_result.success and hop1_result.data:
            for r in hop1_result.data.get("results", []):
                chunk = Chunk(
                    chunk_id=f"chunk_{uuid.uuid4().hex[:8]}",
                    source_url=r.get("url", ""),
                    content=r.get("snippet", ""),
                    relevance_score=r.get("relevance_score", 0.0),
                    hop_number=1,
                )
                hop1_chunks.append(chunk)

        context.retrieved_chunks.extend(hop1_chunks)

        # Determine follow-up query using LLM
        hop1_summary = "\n".join(
            f"[{c.chunk_id}] {c.content}" for c in hop1_chunks
        ) or "No results found in first hop."

        follow_up_response = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Original query: {context.query}\n\n"
                    f"First hop results:\n{hop1_summary}\n\n"
                    f"What information gaps remain? Formulate a follow-up search query.\n"
                    f"Return JSON: {{\"follow_up_query\": \"...\", \"reasoning\": \"...\"}}"
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=300,
        )

        # Parse follow-up query
        follow_up_query = context.query  # fallback
        try:
            clean = follow_up_response.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
            parsed = json.loads(clean.strip())
            follow_up_query = parsed.get("follow_up_query", context.query)
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse follow-up query, using original")

        # HOP 2: Follow-up search
        hop2_result = await self._search_tool.execute(
            input={"query": follow_up_query},
            context=context,
            agent_id=self.agent_id,
        )

        if hop2_result.success and hop2_result.data:
            for r in hop2_result.data.get("results", []):
                chunk = Chunk(
                    chunk_id=f"chunk_{uuid.uuid4().hex[:8]}",
                    source_url=r.get("url", ""),
                    content=r.get("snippet", ""),
                    relevance_score=r.get("relevance_score", 0.0),
                    hop_number=2,
                )
                context.retrieved_chunks.append(chunk)

        # Generate cited answer
        all_chunks_text = "\n".join(
            f"[{c.chunk_id}] (hop {c.hop_number}, relevance {c.relevance_score}): {c.content}"
            for c in context.retrieved_chunks
        )

        answer = await self.call_llm(
            messages=[{
                "role": "user",
                "content": (
                    f"Query: {context.query}\n\n"
                    f"Retrieved chunks:\n{all_chunks_text}\n\n"
                    f"Synthesize an answer citing chunk_ids in [brackets] for every claim. "
                    f"Example: 'The capital is Paris [chunk_abc123].' "
                    f"If information is insufficient, say so explicitly."
                ),
            }],
            context=context,
            budget=budget,
            max_tokens=600,
            system="You are a research synthesizer. Cite every claim with [chunk_id].",
        )

        context.messages.append(
            AgentMessage(
                agent_id=self.agent_id,
                content=answer,
                token_count=0,
                message_type="output",
                metadata={"type": "cited_answer"},
            )
        )

        logger.info(
            "Retrieval complete",
            extra={
                "extra_data": {
                    "hop1_chunks": len(hop1_chunks),
                    "total_chunks": len(context.retrieved_chunks),
                    "hops": 2,
                }
            },
        )

        return context
