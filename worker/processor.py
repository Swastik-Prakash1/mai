"""Background job processor — polls Redis queue and runs orchestrator pipeline.

Publishes SSE events to Redis pub/sub for real-time streaming to API clients.
Handles graceful shutdown on SIGTERM and 5-minute job timeout.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis

from agents.orchestrator import OrchestratorAgent
from context.budget_manager import BudgetManager
from context.shared_context import SharedContext
from logging_.structured import get_logger

logger = get_logger(__name__)

# Graceful shutdown flag
_shutdown = False


def _handle_sigterm(signum, frame):
    """Signal handler for graceful shutdown."""
    global _shutdown
    logger.info("SIGTERM received — finishing current job then exiting")
    _shutdown = True


class EventPublisher:
    """Publishes SSE events to Redis pub/sub for a specific job."""

    def __init__(self, redis_client: aioredis.Redis, job_id: str):
        self._redis = redis_client
        self._channel = f"neuromesh:events:{job_id}"

    async def publish(self, event_type: str, data: dict) -> None:
        """Publish an event to the job's channel."""
        payload = {"event_type": event_type, **data}
        try:
            await self._redis.publish(self._channel, json.dumps(payload, default=str))
        except Exception as exc:
            logger.error(f"Failed to publish event: {exc}")


async def process_job(
    job_data: dict, redis_client: aioredis.Redis
) -> None:
    """Process a single job through the full orchestrator pipeline.

    Args:
        job_data: Dict with job_id and query.
        redis_client: Redis client for publishing events and updating status.
    """
    job_id = job_data["job_id"]
    query = job_data["query"]
    publisher = EventPublisher(redis_client, job_id)

    # Update job status to running
    await _update_job_status(job_id, "running")

    await publisher.publish("agent_start", {
        "agent_id": "orchestrator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "budget_remaining": 8000,
    })

    start_time = time.perf_counter()
    context = SharedContext(job_id=job_id, query=query)
    budget = BudgetManager()

    try:
        orchestrator = OrchestratorAgent()

        # Run with timeout
        context = await asyncio.wait_for(
            orchestrator.execute(context, budget),
            timeout=300,  # 5 minute timeout
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Publish completion events
        await publisher.publish("agent_complete", {
            "agent_id": "orchestrator",
            "total_tokens": budget.get_consumed("orchestrator"),
            "duration_ms": round(elapsed_ms, 2),
        })

        await publisher.publish("final_answer", {
            "answer": context.final_answer or "",
            "provenance_map": [p.model_dump() for p in context.provenance_map],
        })

        # Save to DB
        await _save_job_result(job_id, context)
        logger.info(
            f"Job {job_id} completed in {elapsed_ms:.0f}ms",
            extra={"extra_data": {"job_id": job_id}},
        )

    except asyncio.TimeoutError:
        await publisher.publish("error", {
            "error": "Job exceeded 5 minute timeout",
            "job_id": job_id,
        })
        await _update_job_status(job_id, "failed")
        logger.error(f"Job {job_id} timed out")

    except Exception as exc:
        await publisher.publish("error", {
            "error": str(exc),
            "job_id": job_id,
        })
        await _update_job_status(job_id, "failed")
        logger.error(f"Job {job_id} failed: {exc}", exc_info=True)


async def _update_job_status(job_id: str, status: str) -> None:
    """Update job status in SQLite."""
    import sqlite3
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/neuromesh.db")
    db_path = db_url.split("///")[-1] if "///" in db_url else "/data/neuromesh.db"

    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        if status in ("completed", "failed"):
            conn.execute(
                "UPDATE jobs SET status=?, completed_at=? WHERE id=?",
                (status, now, job_id),
            )
        else:
            conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Failed to update job status: {exc}")


async def _save_job_result(job_id: str, context: SharedContext) -> None:
    """Save final SharedContext to job record."""
    import sqlite3
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/neuromesh.db")
    db_path = db_url.split("///")[-1] if "///" in db_url else "/data/neuromesh.db"

    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        ctx_json = context.model_dump_json()
        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=?, shared_context_json=? WHERE id=?",
            (now, ctx_json, job_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Failed to save job result: {exc}")


async def worker_loop() -> None:
    """Main worker loop — polls Redis queue for jobs."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    # Verify Redis connectivity
    try:
        await redis_client.ping()
        logger.info("Worker connected to Redis")
    except Exception as exc:
        logger.error(f"Cannot connect to Redis: {exc}")
        return

    logger.info("Worker started — polling for jobs")

    while not _shutdown:
        try:
            # BLPOP with 1 second timeout
            result = await redis_client.blpop("neuromesh:jobs", timeout=1)
            if result:
                _, job_json = result
                job_data = json.loads(job_json)
                logger.info(f"Processing job: {job_data.get('job_id', 'unknown')}")
                await process_job(job_data, redis_client)
        except Exception as exc:
            logger.error(f"Worker error: {exc}", exc_info=True)
            await asyncio.sleep(1)

    logger.info("Worker shutting down gracefully")
    await redis_client.close()


def main():
    """Entry point for the worker process."""
    signal.signal(signal.SIGTERM, _handle_sigterm)
    logger.info("Starting NeuroMesh worker")

    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker interrupted")


if __name__ == "__main__":
    main()
