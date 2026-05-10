"""GET /eval/latest, POST /eval/rerun — Evaluation endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from api.schemas import (
    DimensionScoreResponse,
    ErrorResponse,
    EvalLatestResponse,
    EvalRerunRequest,
    EvalRerunResponse,
    EvalSummaryResponse,
    PromptRewriteResponse,
    TestCaseScoreResponse,
)
from db.models import EvalRun, PromptRewrite
from eval.diff import diff_eval_runs
from eval.harness import run_eval
from eval.test_cases import ALL_TEST_CASES
from logging_.structured import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/eval/latest",
    response_model=EvalLatestResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get the latest evaluation run",
    description="Returns scores broken down by category and dimension, plus pending prompt rewrites.",
)
async def get_latest_eval(
    db: AsyncSession = Depends(get_db_session),
):
    """Return the most recent EvalRun with scores and pending rewrites."""
    result = await db.execute(
        select(EvalRun).order_by(EvalRun.run_timestamp.desc()).limit(1)
    )
    eval_run = result.scalar_one_or_none()

    if not eval_run:
        raise HTTPException(status_code=404, detail="No eval runs found")

    scores_data = json.loads(eval_run.scores_json)
    summary_data = json.loads(eval_run.summary_json)

    # Build response scores
    scores = []
    for s in scores_data:
        scores.append(TestCaseScoreResponse(
            test_case_id=s["test_case_id"],
            category=s["category"],
            total=s["total"],
            dimensions=[
                DimensionScoreResponse(**d) for d in s.get("dimensions", [])
            ],
        ))

    summary = EvalSummaryResponse(**summary_data) if summary_data else None

    # Get pending rewrites
    result = await db.execute(
        select(PromptRewrite).where(PromptRewrite.status == "pending")
    )
    rewrites = result.scalars().all()
    pending = [
        PromptRewriteResponse(
            id=r.id,
            agent_id=r.agent_id,
            dimension=r.dimension,
            status=r.status,
            justification=r.justification,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rewrites
    ]

    return EvalLatestResponse(
        run_id=eval_run.id,
        run_timestamp=eval_run.run_timestamp.isoformat(),
        scores=scores,
        summary=summary,
        pending_rewrites=pending,
    )


@router.post(
    "/eval/rerun",
    response_model=EvalRerunResponse,
    summary="Re-run evaluation",
    description="Re-runs eval on failed test cases (any dimension < 6) or all cases.",
)
async def rerun_eval(
    request: EvalRerunRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Re-run eval, optionally only on previously failed cases."""
    # Get latest run to determine which cases failed
    previous_scores = None
    if request.only_failed:
        result = await db.execute(
            select(EvalRun).order_by(EvalRun.run_timestamp.desc()).limit(1)
        )
        prev_run = result.scalar_one_or_none()
        if prev_run:
            previous_scores = json.loads(prev_run.scores_json)

    # Determine which cases to re-run
    cases_to_run = ALL_TEST_CASES
    if request.only_failed and previous_scores:
        failed_ids = set()
        for s in previous_scores:
            for d in s.get("dimensions", []):
                if d["score"] < 6:
                    failed_ids.add(s["test_case_id"])
                    break
        cases_to_run = [tc for tc in ALL_TEST_CASES if tc.id in failed_ids]
        if not cases_to_run:
            cases_to_run = ALL_TEST_CASES  # All passed — re-run all

    # Run eval
    eval_result = await run_eval(cases_to_run)

    # Store new EvalRun
    new_run = EvalRun(
        run_timestamp=datetime.now(timezone.utc),
        test_cases_json=json.dumps(eval_result["test_cases"], default=str),
        scores_json=json.dumps(eval_result["scores"], default=str),
        summary_json=json.dumps(eval_result["summary"], default=str),
    )
    try:
        db.add(new_run)
        await db.commit()
        await db.refresh(new_run)
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to save eval run: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    # Compute diff
    delta = {}
    if previous_scores:
        prev_data = {"scores": previous_scores, "summary": json.loads(prev_run.summary_json)}
        delta = diff_eval_runs(prev_data, eval_result)

    return EvalRerunResponse(
        new_run_id=new_run.id,
        cases_rerun=len(cases_to_run),
        delta=delta,
    )
