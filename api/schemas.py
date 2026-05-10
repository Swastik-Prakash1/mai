"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Request schemas ---

class QueryRequest(BaseModel):
    """POST /query request body."""
    query: str
    job_id: str | None = None


class PromptReviewRequest(BaseModel):
    """POST /prompts/review request body."""
    rewrite_id: int
    decision: Literal["approved", "rejected"]
    reviewer_note: str = ""


class EvalRerunRequest(BaseModel):
    """POST /eval/rerun request body."""
    only_failed: bool = True


# --- Response schemas ---

class ErrorResponse(BaseModel):
    """Standard error response."""
    error_code: str
    message: str
    job_id: str | None = None


class QueryResponse(BaseModel):
    """POST /query initial response (before SSE stream)."""
    job_id: str
    status: str
    message: str


class TraceEvent(BaseModel):
    """A single event in the execution trace."""
    timestamp: str
    event_type: str
    agent_id: str | None = None
    tool_name: str | None = None
    details: dict = Field(default_factory=dict)


class TraceResponse(BaseModel):
    """GET /trace/{job_id} response."""
    job_id: str
    status: str
    query: str
    trace: list[TraceEvent] = Field(default_factory=list)
    total_duration_ms: float = 0.0


class DimensionScoreResponse(BaseModel):
    """A single dimension score."""
    dimension: str
    score: float
    justification: str


class TestCaseScoreResponse(BaseModel):
    """Scores for a single test case."""
    test_case_id: int
    category: str
    total: float
    dimensions: list[DimensionScoreResponse] = Field(default_factory=list)


class EvalSummaryResponse(BaseModel):
    """Summary statistics for an eval run."""
    overall_average: float
    by_category: dict[str, float] = Field(default_factory=dict)
    by_dimension: dict[str, float] = Field(default_factory=dict)
    total_cases: int


class PromptRewriteResponse(BaseModel):
    """A pending/completed prompt rewrite."""
    id: int
    agent_id: str
    dimension: str
    status: str
    justification: str
    created_at: str


class EvalLatestResponse(BaseModel):
    """GET /eval/latest response."""
    run_id: int
    run_timestamp: str
    scores: list[TestCaseScoreResponse] = Field(default_factory=list)
    summary: EvalSummaryResponse | None = None
    pending_rewrites: list[PromptRewriteResponse] = Field(default_factory=list)


class PromptReviewResponse(BaseModel):
    """POST /prompts/review response."""
    rewrite_id: int
    status: str
    message: str


class EvalRerunResponse(BaseModel):
    """POST /eval/rerun response."""
    new_run_id: int
    cases_rerun: int
    delta: dict = Field(default_factory=dict)
