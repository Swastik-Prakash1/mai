"""POST /prompts/review — Prompt review endpoint."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from api.schemas import PromptReviewRequest, PromptReviewResponse, ErrorResponse
from db.models import PromptRewrite, SystemPrompt
from logging_.structured import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/prompts/review",
    response_model=PromptReviewResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Review a proposed prompt rewrite",
    description="Approve or reject a meta-agent proposed prompt rewrite. If approved, updates the active system prompt.",
)
async def review_prompt(
    request: PromptReviewRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a prompt rewrite proposal."""
    # Get the rewrite
    result = await db.execute(
        select(PromptRewrite).where(PromptRewrite.id == request.rewrite_id)
    )
    rewrite = result.scalar_one_or_none()

    if not rewrite:
        raise HTTPException(
            status_code=404, detail=f"Rewrite {request.rewrite_id} not found"
        )

    if rewrite.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Rewrite {request.rewrite_id} already {rewrite.status}",
        )

    try:
        rewrite.status = request.decision
        rewrite.reviewed_at = datetime.now(timezone.utc)

        if request.decision == "approved":
            # Deactivate current prompt for this agent
            result = await db.execute(
                select(SystemPrompt).where(
                    SystemPrompt.agent_id == rewrite.agent_id,
                    SystemPrompt.is_active == True,
                )
            )
            current = result.scalar_one_or_none()
            if current:
                current.is_active = False
                current_version = current.version
            else:
                current_version = 0

            # Create new active prompt
            new_prompt = SystemPrompt(
                agent_id=rewrite.agent_id,
                prompt_text=rewrite.proposed_prompt,
                version=current_version + 1,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_prompt)

            message = f"Prompt for '{rewrite.agent_id}' updated to v{current_version + 1}"
            logger.info(message)
        else:
            message = f"Prompt rewrite for '{rewrite.agent_id}' rejected"
            logger.info(message)

        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to review prompt: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    return PromptReviewResponse(
        rewrite_id=request.rewrite_id,
        status=request.decision,
        message=message,
    )
