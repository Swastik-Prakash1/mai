"""SharedContext schema and all supporting Pydantic models.

SharedContext is the ONLY communication channel between agents. The orchestrator
passes it to each agent, which reads from and appends to it. No agent-to-agent
direct calls are allowed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """A single message produced by or consumed by an agent."""

    agent_id: str
    content: str
    token_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message_type: Literal[
        "input", "output", "tool_call", "tool_result", "critique", "synthesis"
    ]
    metadata: dict = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    """Record of a single tool invocation with full audit trail."""

    tool_name: str
    input: dict
    output: dict | None = None
    latency_ms: float
    success: bool
    failure_reason: str | None = None
    retry_number: int = 0  # 0 = first call, 1 = first retry, etc.
    agent_accepted: bool = True  # did the agent accept the tool output?


class SubTask(BaseModel):
    """A decomposed sub-task from the decomposition agent."""

    id: str
    type: Literal[
        "FACTUAL_LOOKUP", "CODE_TASK", "ANALYSIS", "COMPARISON", "SYNTHESIS"
    ]
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["pending", "completed", "failed"] = "pending"
    result: str | None = None


class Chunk(BaseModel):
    """A retrieved knowledge chunk from the retrieval agent."""

    chunk_id: str
    source_url: str
    content: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    hop_number: int = 1


class Critique(BaseModel):
    """A span-level critique from the critique agent."""

    source_agent_id: str
    flagged_span: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    suggested_fix: str


class ProvenanceEntry(BaseModel):
    """Maps a sentence in the final answer to its source."""

    sentence_id: int
    sentence_text: str
    source_agent_id: str
    source_chunk_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PolicyViolation(BaseModel):
    """Record of an agent exceeding its context budget."""

    agent_id: str
    violation_type: str  # e.g., "budget_overflow"
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_used: int = 0
    tokens_allowed: int = 0


class OrchestratorDecision(BaseModel):
    """A decision logged by the orchestrator agent."""

    step: int
    agent: str
    action: str
    rationale: str
    budget_allocated: int = 0
    context_keys: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SharedContext(BaseModel):
    """The central context object passed between all agents.

    This is the ONLY way agents communicate. The orchestrator creates it,
    passes it to each agent in sequence, and each agent reads from / appends to it.
    """

    job_id: str
    query: str
    messages: list[AgentMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    sub_tasks: list[SubTask] = Field(default_factory=list)
    retrieved_chunks: list[Chunk] = Field(default_factory=list)
    critiques: list[Critique] = Field(default_factory=list)
    final_answer: str | None = None
    provenance_map: list[ProvenanceEntry] = Field(default_factory=list)
    policy_violations: list[PolicyViolation] = Field(default_factory=list)
    orchestrator_log: list[OrchestratorDecision] = Field(default_factory=list)
