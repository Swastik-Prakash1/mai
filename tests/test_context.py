"""Unit tests for SharedContext and BudgetManager."""

import pytest

from context.budget_manager import BudgetManager, count_tokens
from context.shared_context import (
    AgentMessage,
    Chunk,
    Critique,
    OrchestratorDecision,
    PolicyViolation,
    ProvenanceEntry,
    SharedContext,
    SubTask,
    ToolCallRecord,
)


class TestSharedContext:
    """Tests for SharedContext schema."""

    def test_create_minimal(self):
        ctx = SharedContext(job_id="test-1", query="What is 2+2?")
        assert ctx.job_id == "test-1"
        assert ctx.query == "What is 2+2?"
        assert ctx.messages == []
        assert ctx.sub_tasks == []

    def test_add_message(self):
        ctx = SharedContext(job_id="test-2", query="Test")
        msg = AgentMessage(
            agent_id="test_agent",
            content="Hello",
            token_count=5,
            message_type="output",
        )
        ctx.messages.append(msg)
        assert len(ctx.messages) == 1
        assert ctx.messages[0].agent_id == "test_agent"

    def test_add_subtask(self):
        ctx = SharedContext(job_id="test-3", query="Test")
        task = SubTask(
            id="st_1",
            type="ANALYSIS",
            description="Analyze data",
            dependencies=[],
        )
        ctx.sub_tasks.append(task)
        assert len(ctx.sub_tasks) == 1
        assert ctx.sub_tasks[0].type == "ANALYSIS"

    def test_add_chunk(self):
        ctx = SharedContext(job_id="test-4", query="Test")
        chunk = Chunk(
            chunk_id="chunk_abc",
            source_url="https://example.com",
            content="Test content",
            relevance_score=0.9,
            hop_number=1,
        )
        ctx.retrieved_chunks.append(chunk)
        assert ctx.retrieved_chunks[0].hop_number == 1

    def test_add_critique(self):
        ctx = SharedContext(job_id="test-5", query="Test")
        critique = Critique(
            source_agent_id="retrieval",
            flagged_span="incorrect claim",
            confidence=0.3,
            reason="Contradicts source",
            suggested_fix="Replace with correct data",
        )
        ctx.critiques.append(critique)
        assert ctx.critiques[0].confidence == 0.3

    def test_add_policy_violation(self):
        ctx = SharedContext(job_id="test-6", query="Test")
        violation = PolicyViolation(
            agent_id="test_agent",
            violation_type="budget_overflow",
            details="Exceeded 4000 token budget",
        )
        ctx.policy_violations.append(violation)
        assert len(ctx.policy_violations) == 1

    def test_provenance_entry(self):
        entry = ProvenanceEntry(
            sentence_id=0,
            sentence_text="Paris is the capital of France.",
            source_agent_id="retrieval",
            source_chunk_id="chunk_abc",
            confidence=0.95,
        )
        assert entry.confidence == 0.95

    def test_serialization(self):
        ctx = SharedContext(job_id="test-7", query="Test query")
        ctx.messages.append(
            AgentMessage(
                agent_id="test", content="Hello", token_count=1, message_type="output"
            )
        )
        json_str = ctx.model_dump_json()
        assert "test-7" in json_str
        assert "Hello" in json_str


class TestBudgetManager:
    """Tests for BudgetManager."""

    def test_count_tokens(self):
        count = count_tokens("Hello world")
        assert isinstance(count, int)
        assert count > 0

    def test_declare_and_consume(self):
        bm = BudgetManager()
        bm.declare_budget("agent_a", 1000)
        bm.consume("agent_a", "Hello world")
        consumed = bm.get_consumed("agent_a")
        assert consumed > 0
        assert consumed < 1000

    def test_overflow_detection(self):
        bm = BudgetManager()
        bm.declare_budget("agent_b", 10)  # Very small budget
        bm.consume("agent_b", "This is a long text that will exceed the tiny budget")
        assert bm.is_overflow("agent_b") is True

    def test_no_overflow(self):
        bm = BudgetManager()
        bm.declare_budget("agent_c", 100000)
        bm.consume("agent_c", "Short text")
        assert bm.is_overflow("agent_c") is False

    def test_undeclared_agent(self):
        bm = BudgetManager()
        bm.consume("unknown", "Some text")
        assert bm.get_consumed("unknown") > 0

    def test_record_violation(self):
        bm = BudgetManager()
        bm.declare_budget("agent_d", 5)
        bm.consume("agent_d", "This text will overflow the 5-token budget")
        ctx = SharedContext(job_id="test", query="test")
        bm.record_violation("agent_d", ctx)
        assert len(ctx.policy_violations) == 1
        assert ctx.policy_violations[0].agent_id == "agent_d"
