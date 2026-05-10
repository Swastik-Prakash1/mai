"""SQLAlchemy ORM models for NeuroMesh.

All persistent state is stored here: jobs, agent logs, tool logs,
eval runs, prompt rewrites, and system prompts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class Job(Base):
    """A query processing job."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # queued | running | completed | failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shared_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentLog(Base):
    """Log entry for agent events — full audit trail."""

    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # start | llm_call | tool_call | complete | policy_violation
    input_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_violation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class ToolLog(Base):
    """Log entry for tool invocations."""

    __tablename__ = "tool_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(50), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retry_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    agent_accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class EvalRun(Base):
    """A single evaluation run with all test case scores."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    test_cases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    scores_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class PromptRewrite(Base):
    """A proposed prompt rewrite from the meta-agent."""

    __tablename__ = "prompt_rewrites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    diff_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    justification: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reeval_delta_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SystemPrompt(Base):
    """Versioned system prompts for each agent."""

    __tablename__ = "system_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
