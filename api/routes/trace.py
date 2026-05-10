"""GET /trace/{job_id} — Full execution trace endpoint."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from api.schemas import TraceEvent, TraceResponse, ErrorResponse
from db.models import AgentLog, Job, ToolLog
from logging_.structured import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/trace/{job_id}",
    response_model=TraceResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get full execution trace for a job",
    description="Returns ordered list of all agent decisions, tool calls, and handoffs.",
)
async def get_trace(
    job_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Reconstruct full execution trace from logs."""
    # Get job
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Get agent logs
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.job_id == job_id)
        .order_by(AgentLog.timestamp)
    )
    agent_logs = result.scalars().all()

    # Get tool logs
    result = await db.execute(
        select(ToolLog)
        .where(ToolLog.job_id == job_id)
        .order_by(ToolLog.timestamp)
    )
    tool_logs = result.scalars().all()

    # Merge and sort by timestamp
    trace_events: list[TraceEvent] = []

    for log in agent_logs:
        trace_events.append(TraceEvent(
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            event_type=log.event_type,
            agent_id=log.agent_id,
            details={
                "latency_ms": log.latency_ms,
                "token_count": log.token_count,
                "policy_violation": log.policy_violation,
                "input_hash": log.input_hash,
                "output_hash": log.output_hash,
            },
        ))

    for log in tool_logs:
        trace_events.append(TraceEvent(
            timestamp=log.timestamp.isoformat() if log.timestamp else "",
            event_type="tool_call",
            agent_id=log.agent_id,
            tool_name=log.tool_name,
            details={
                "latency_ms": log.latency_ms,
                "retry_number": log.retry_number,
                "agent_accepted": log.agent_accepted,
            },
        ))

    # Sort by timestamp
    trace_events.sort(key=lambda e: e.timestamp)

    # Calculate duration
    duration = 0.0
    if job.created_at and job.completed_at:
        duration = (job.completed_at - job.created_at).total_seconds() * 1000

    return TraceResponse(
        job_id=job_id,
        status=job.status,
        query=job.query,
        trace=trace_events,
        total_duration_ms=round(duration, 2),
    )
