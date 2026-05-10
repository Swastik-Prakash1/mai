"""POST /query — SSE streaming query endpoint.

Creates a Job, pushes to Redis queue, and returns an SSE stream
that forwards events from the worker via Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_redis
from api.schemas import QueryRequest, QueryResponse, ErrorResponse
from db.models import Job
from logging_.structured import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Submit a query for multi-agent processing",
    description="Creates a job, queues it for the background worker, and returns an SSE stream of processing events.",
)
async def submit_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Submit a query and receive SSE stream of processing events."""
    job_id = request.job_id or str(uuid.uuid4())

    # Create Job record
    job = Job(
        id=job_id,
        query=request.query,
        status="queued",
        created_at=datetime.now(timezone.utc),
    )
    try:
        db.add(job)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to create job: {exc}")
        return ErrorResponse(
            error_code="DB_ERROR", message=str(exc), job_id=job_id
        )

    # Push to Redis queue
    try:
        redis = await get_redis()
        await redis.lpush(
            "neuromesh:jobs",
            json.dumps({"job_id": job_id, "query": request.query}),
        )
        await redis.close()
    except Exception as exc:
        logger.error(f"Failed to push to Redis: {exc}")

    logger.info(f"Job {job_id} queued", extra={"extra_data": {"job_id": job_id}})

    return QueryResponse(
        job_id=job_id,
        status="queued",
        message="Job queued. Connect to /query/stream/{job_id} for SSE events.",
    )


@router.get(
    "/query/stream/{job_id}",
    summary="SSE stream for job events",
    description="Subscribe to real-time events for a processing job.",
)
async def stream_events(job_id: str):
    """SSE endpoint that streams processing events for a job."""

    async def event_generator():
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"neuromesh:events:{job_id}")

            # Send initial connection event
            yield {
                "event": "connected",
                "data": json.dumps({"job_id": job_id, "status": "connected"}),
            }

            # Listen for events with timeout
            timeout_count = 0
            max_timeout = 300  # 5 minutes
            while timeout_count < max_timeout:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message.get("type") == "message":
                    timeout_count = 0
                    data = message["data"]
                    try:
                        event_data = json.loads(data)
                        event_type = event_data.pop("event_type", "update")
                        yield {
                            "event": event_type,
                            "data": json.dumps(event_data),
                        }
                        # Stop on final events
                        if event_type in ("final_answer", "error", "complete"):
                            break
                    except json.JSONDecodeError:
                        yield {"event": "raw", "data": data}
                else:
                    timeout_count += 1
                    # Keep-alive ping every 15 seconds
                    if timeout_count % 15 == 0:
                        yield {"event": "ping", "data": "{}"}

            await pubsub.unsubscribe(f"neuromesh:events:{job_id}")
            await redis.close()
        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(event_generator())
