"""15-case evaluation runner.

Runs all test cases through the orchestrator, scores them, and persists
EvalRun records to the database.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from agents.orchestrator import OrchestratorAgent
from context.budget_manager import BudgetManager
from context.shared_context import SharedContext
from eval.scorer import TestCaseScore, score_test_case
from eval.test_cases import ALL_TEST_CASES, TestCase
from logging_.structured import get_logger

logger = get_logger(__name__)


async def run_single_case(test_case: TestCase) -> tuple[SharedContext, TestCaseScore]:
    """Run a single test case through the full pipeline and score it.

    Returns:
        Tuple of (final SharedContext, TestCaseScore).
    """
    job_id = f"eval_{test_case.id}_{uuid.uuid4().hex[:8]}"
    context = SharedContext(job_id=job_id, query=test_case.query)
    budget = BudgetManager()
    orchestrator = OrchestratorAgent()

    try:
        context = await orchestrator.execute(context, budget)
    except Exception as exc:
        logger.error(
            f"Test case {test_case.id} failed: {exc}",
            exc_info=True,
        )
        context.final_answer = f"[ERROR] {exc}"

    score = score_test_case(test_case, context)
    return context, score


async def run_eval(
    test_cases: list[TestCase] | None = None,
) -> dict:
    """Run evaluation on specified test cases (or all 15).

    Returns:
        Dict with test_cases, scores, and summary for DB storage.
    """
    cases = test_cases or ALL_TEST_CASES
    all_scores: list[TestCaseScore] = []
    contexts: list[SharedContext] = []

    logger.info(f"Starting eval run with {len(cases)} test cases")

    for tc in cases:
        logger.info(f"Running test case {tc.id}: {tc.query[:50]}...")
        ctx, score = await run_single_case(tc)
        all_scores.append(score)
        contexts.append(ctx)

    # Build summary
    summary = _build_summary(all_scores)

    # Serialize for DB
    scores_json = [
        {
            "test_case_id": s.test_case_id,
            "category": s.category,
            "total": round(s.total, 2),
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "score": d.score,
                    "justification": d.justification,
                }
                for d in s.dimensions
            ],
        }
        for s in all_scores
    ]

    test_cases_json = [
        {
            "id": tc.id,
            "category": tc.category,
            "query": tc.query,
            "expected_answer": tc.expected_answer,
            "expected_behavior": tc.expected_behavior,
        }
        for tc in cases
    ]

    result = {
        "test_cases": test_cases_json,
        "scores": scores_json,
        "summary": summary,
    }

    logger.info(
        "Eval run complete",
        extra={
            "extra_data": {
                "total_cases": len(cases),
                "overall_score": summary.get("overall_average", 0),
            }
        },
    )

    return result


def _build_summary(scores: list[TestCaseScore]) -> dict:
    """Build aggregated summary by category and dimension."""
    category_scores: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    dimension_scores: dict[str, list[float]] = {}

    for s in scores:
        category_scores[s.category].append(s.total)
        for d in s.dimensions:
            dimension_scores.setdefault(d.dimension, []).append(d.score)

    summary = {
        "overall_average": round(
            sum(s.total for s in scores) / len(scores) if scores else 0, 2
        ),
        "by_category": {
            cat: round(sum(vals) / len(vals), 2) if vals else 0.0
            for cat, vals in category_scores.items()
        },
        "by_dimension": {
            dim: round(sum(vals) / len(vals), 2) if vals else 0.0
            for dim, vals in dimension_scores.items()
        },
        "total_cases": len(scores),
    }

    return summary
