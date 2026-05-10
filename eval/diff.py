"""Eval run diff tool — structured comparison between two eval runs."""

from __future__ import annotations

import json


def diff_eval_runs(run1_scores: dict, run2_scores: dict) -> dict:
    """Produce a structured diff of scores between two eval runs.

    Args:
        run1_scores: Scores dict from first run (with "scores" and "summary" keys).
        run2_scores: Scores dict from second run.

    Returns:
        Dict with per-test-case and per-dimension deltas.
    """
    scores1 = {s["test_case_id"]: s for s in run1_scores.get("scores", [])}
    scores2 = {s["test_case_id"]: s for s in run2_scores.get("scores", [])}

    # Per test-case diff
    case_diffs = []
    all_ids = sorted(set(list(scores1.keys()) + list(scores2.keys())))

    for tc_id in all_ids:
        s1 = scores1.get(tc_id)
        s2 = scores2.get(tc_id)

        if s1 and s2:
            total_delta = round(s2["total"] - s1["total"], 2)
            dim_deltas = {}
            dims1 = {d["dimension"]: d["score"] for d in s1.get("dimensions", [])}
            dims2 = {d["dimension"]: d["score"] for d in s2.get("dimensions", [])}

            for dim in set(list(dims1.keys()) + list(dims2.keys())):
                old = dims1.get(dim, 0.0)
                new = dims2.get(dim, 0.0)
                dim_deltas[dim] = {"old": old, "new": new, "delta": round(new - old, 2)}

            case_diffs.append({
                "test_case_id": tc_id,
                "old_total": s1["total"],
                "new_total": s2["total"],
                "total_delta": total_delta,
                "dimension_deltas": dim_deltas,
                "improved": total_delta > 0,
                "regressed": total_delta < 0,
            })
        elif s2:
            case_diffs.append({
                "test_case_id": tc_id,
                "old_total": None,
                "new_total": s2["total"],
                "total_delta": None,
                "note": "New test case in run 2",
            })

    # Summary diff
    sum1 = run1_scores.get("summary", {})
    sum2 = run2_scores.get("summary", {})

    summary_diff = {
        "overall_delta": round(
            sum2.get("overall_average", 0) - sum1.get("overall_average", 0), 2
        ),
        "by_category": {},
        "by_dimension": {},
    }

    for cat in ["A", "B", "C"]:
        old = sum1.get("by_category", {}).get(cat, 0.0)
        new = sum2.get("by_category", {}).get(cat, 0.0)
        summary_diff["by_category"][cat] = {
            "old": old, "new": new, "delta": round(new - old, 2)
        }

    dims1 = sum1.get("by_dimension", {})
    dims2 = sum2.get("by_dimension", {})
    for dim in set(list(dims1.keys()) + list(dims2.keys())):
        old = dims1.get(dim, 0.0)
        new = dims2.get(dim, 0.0)
        summary_diff["by_dimension"][dim] = {
            "old": old, "new": new, "delta": round(new - old, 2)
        }

    return {
        "case_diffs": case_diffs,
        "summary_diff": summary_diff,
        "improved_count": sum(1 for d in case_diffs if d.get("improved")),
        "regressed_count": sum(1 for d in case_diffs if d.get("regressed")),
        "unchanged_count": sum(1 for d in case_diffs if d.get("total_delta") == 0),
    }
