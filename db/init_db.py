"""Database initialization — creates tables and seeds data.

Called on API container startup before uvicorn starts.
"""

from __future__ import annotations

import os
import sqlite3

from logging_.structured import get_logger

logger = get_logger(__name__)


def init_database(db_path: str | None = None) -> None:
    """Initialize the database: create tables + seed data.

    Args:
        db_path: Path to SQLite file. Defaults to env var or /data/neuromesh.db.
    """
    if db_path is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/neuromesh.db")
        db_path = db_url.split("///")[-1] if "///" in db_url else "/data/neuromesh.db"

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    logger.info(f"Initializing database at {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        # Create tables (idempotent via IF NOT EXISTS)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            shared_context_json TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            input_hash TEXT NOT NULL DEFAULT '',
            output_hash TEXT NOT NULL DEFAULT '',
            latency_ms REAL NOT NULL DEFAULT 0,
            token_count INTEGER NOT NULL DEFAULT 0,
            policy_violation INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_agent_logs_job_id ON agent_logs(job_id);
        CREATE INDEX IF NOT EXISTS idx_agent_logs_agent_id ON agent_logs(agent_id);

        CREATE TABLE IF NOT EXISTS tool_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            input_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            latency_ms REAL NOT NULL DEFAULT 0,
            retry_number INTEGER NOT NULL DEFAULT 0,
            agent_accepted INTEGER NOT NULL DEFAULT 1,
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tool_logs_job_id ON tool_logs(job_id);

        CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            test_cases_json TEXT NOT NULL DEFAULT '[]',
            scores_json TEXT NOT NULL DEFAULT '{}',
            summary_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS prompt_rewrites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eval_run_id INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            original_prompt TEXT NOT NULL,
            proposed_prompt TEXT NOT NULL,
            diff_json TEXT NOT NULL DEFAULT '[]',
            justification TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reeval_delta_json TEXT
        );

        CREATE TABLE IF NOT EXISTS system_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_system_prompts_agent_id ON system_prompts(agent_id);
        """)
        conn.commit()
        logger.info("Database tables created/verified")
    except Exception as exc:
        logger.error(f"Failed to create tables: {exc}")
        raise
    finally:
        conn.close()

    # Seed data
    from api.seed import seed_database
    seed_database(db_path)
    logger.info("Database initialization complete")


if __name__ == "__main__":
    init_database()
