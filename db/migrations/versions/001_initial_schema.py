"""initial schema

Revision ID: 001
Revises: None
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("shared_context_json", sa.Text, nullable=True),
    )

    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(36), nullable=False, index=True),
        sa.Column("agent_id", sa.String(50), nullable=False, index=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("output_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("latency_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("policy_violation", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
    )

    op.create_table(
        "tool_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(36), nullable=False, index=True),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("tool_name", sa.String(50), nullable=False),
        sa.Column("input_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("latency_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("retry_number", sa.Integer, nullable=False, server_default="0"),
        sa.Column("agent_accepted", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("timestamp", sa.DateTime, nullable=False),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_timestamp", sa.DateTime, nullable=False),
        sa.Column("test_cases_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("scores_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("summary_json", sa.Text, nullable=False, server_default="{}"),
    )

    op.create_table(
        "prompt_rewrites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("eval_run_id", sa.Integer, nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("original_prompt", sa.Text, nullable=False),
        sa.Column("proposed_prompt", sa.Text, nullable=False),
        sa.Column("diff_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("justification", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("reeval_delta_json", sa.Text, nullable=True),
    )

    op.create_table(
        "system_prompts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.String(50), nullable=False, index=True),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_prompts")
    op.drop_table("prompt_rewrites")
    op.drop_table("eval_runs")
    op.drop_table("tool_logs")
    op.drop_table("agent_logs")
    op.drop_table("jobs")
