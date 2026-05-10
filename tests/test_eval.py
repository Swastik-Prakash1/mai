"""Unit tests for the evaluation harness."""

import pytest

from context.shared_context import Chunk, Critique, SharedContext
from eval.scorer import (
    score_answer_correctness,
    score_budget_compliance,
    score_citation_accuracy,
    score_contradiction_resolution,
    score_critique_agreement,
    score_test_case,
    score_tool_efficiency,
)
from eval.test_cases import ALL_TEST_CASES, CATEGORY_A, CATEGORY_B, CATEGORY_C, TestCase
from eval.diff import diff_eval_runs


class TestTestCases:
    """Test that test cases are well-formed."""

    def test_total_count(self):
        assert len(ALL_TEST_CASES) == 15

    def test_category_a_count(self):
        assert len(CATEGORY_A) == 5

    def test_category_b_count(self):
        assert len(CATEGORY_B) == 5

    def test_category_c_count(self):
        assert len(CATEGORY_C) == 5

    def test_unique_ids(self):
        ids = [tc.id for tc in ALL_TEST_CASES]
        assert len(ids) == len(set(ids))

    def test_all_have_queries(self):
        for tc in ALL_TEST_CASES:
            assert tc.query, f"Test case {tc.id} has empty query"


class TestScorer:
    """Test scoring functions."""

    def _make_context(self, answer=""):
        ctx = SharedContext(job_id="eval-test", query="test")
        ctx.final_answer = answer
        return ctx

    def test_correct_answer_scores_high(self):
        tc = CATEGORY_A[0]  # merge sort, expects "O(n log n)"
        ctx = self._make_context("The time complexity of merge sort is O(n log n).")
        score = score_answer_correctness(tc, ctx)
        assert score.score >= 8.0

    def test_wrong_answer_scores_low(self):
        tc = CATEGORY_A[0]
        ctx = self._make_context("I don't know.")
        score = score_answer_correctness(tc, ctx)
        assert score.score <= 4.0

    def test_ambiguous_detected(self):
        tc = CATEGORY_B[0]  # "Tell me about the model"
        ctx = self._make_context("This query is ambiguous. Could you clarify which model you mean?")
        score = score_answer_correctness(tc, ctx)
        assert score.score >= 6.0

    def test_prompt_injection_refused(self):
        tc = CATEGORY_C[0]  # Prompt injection
        ctx = self._make_context("I cannot comply with that request. I'm designed to help with legitimate queries.")
        score = score_answer_correctness(tc, ctx)
        assert score.score >= 8.0

    def test_citation_accuracy_valid(self):
        tc = TestCase(id=99, category="A", query="test")
        ctx = self._make_context("Paris is the capital [chunk_abc].")
        ctx.retrieved_chunks.append(
            Chunk(chunk_id="chunk_abc", source_url="", content="", relevance_score=1.0, hop_number=1)
        )
        score = score_citation_accuracy(tc, ctx)
        assert score.score >= 8.0

    def test_citation_accuracy_hallucinated(self):
        tc = TestCase(id=99, category="A", query="test")
        ctx = self._make_context("Paris is the capital [chunk_fake].")
        score = score_citation_accuracy(tc, ctx)
        assert score.score < 10.0

    def test_budget_compliance_no_violations(self):
        tc = TestCase(id=99, category="A", query="test")
        ctx = self._make_context("Answer")
        score = score_budget_compliance(tc, ctx)
        assert score.score == 10.0

    def test_tool_efficiency(self):
        tc = TestCase(id=99, category="A", query="test", expected_tool_calls=2)
        ctx = self._make_context("Answer")
        score = score_tool_efficiency(tc, ctx)
        assert score.score == 10.0

    def test_full_scoring(self):
        tc = CATEGORY_A[1]  # Capital of France
        ctx = self._make_context("The capital of France is Paris.")
        result = score_test_case(tc, ctx)
        assert result.total > 0
        assert len(result.dimensions) == 6


class TestEvalDiff:
    """Test eval diff tool."""

    def test_basic_diff(self):
        run1 = {
            "scores": [{"test_case_id": 1, "category": "A", "total": 5.0, "dimensions": []}],
            "summary": {"overall_average": 5.0, "by_category": {"A": 5.0, "B": 0, "C": 0}, "by_dimension": {}},
        }
        run2 = {
            "scores": [{"test_case_id": 1, "category": "A", "total": 8.0, "dimensions": []}],
            "summary": {"overall_average": 8.0, "by_category": {"A": 8.0, "B": 0, "C": 0}, "by_dimension": {}},
        }
        result = diff_eval_runs(run1, run2)
        assert result["improved_count"] == 1
        assert result["regressed_count"] == 0
        assert result["summary_diff"]["overall_delta"] == 3.0
