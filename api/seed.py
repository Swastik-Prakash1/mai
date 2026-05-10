"""Database seeding script — seeds SystemPrompts and knowledge_base on startup."""

from __future__ import annotations

import sqlite3
import os

from agents.decomposition import DecompositionAgent
from agents.retrieval import RetrievalAgent
from agents.critique import CritiqueAgent
from agents.synthesis import SynthesisAgent
from agents.compression import CompressionAgent
from agents.orchestrator import OrchestratorAgent
from agents.meta import MetaAgent
from tools.db_lookup import seed_knowledge_base
from logging_.structured import get_logger

logger = get_logger(__name__)

# Map of agent_id → default system prompt
AGENT_PROMPTS = {
    "orchestrator": OrchestratorAgent.system_prompt,
    "decomposition": DecompositionAgent.system_prompt,
    "retrieval": RetrievalAgent.system_prompt,
    "critique": CritiqueAgent.system_prompt,
    "synthesis": SynthesisAgent.system_prompt,
    "compression": CompressionAgent.system_prompt,
    "meta": MetaAgent.system_prompt,
}


def seed_database(db_path: str = "/data/neuromesh.db") -> None:
    """Seed the database with initial system prompts and knowledge base data."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        # Check if system_prompts table exists and has data
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM system_prompts")
            count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            count = 0

        if count == 0:
            # Seed system prompts
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            for agent_id, prompt_text in AGENT_PROMPTS.items():
                conn.execute(
                    "INSERT INTO system_prompts (agent_id, prompt_text, version, is_active, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (agent_id, prompt_text, 1, True, now),
                )
            conn.commit()
            logger.info(f"Seeded {len(AGENT_PROMPTS)} system prompts")
        else:
            logger.info(f"System prompts already seeded ({count} rows)")
    finally:
        conn.close()

    # Seed knowledge base
    seed_knowledge_base(db_path)


if __name__ == "__main__":
    # Determine DB path from environment or default
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/neuromesh.db")
    # Extract file path from SQLAlchemy URL
    db_path = db_url.split("///")[-1] if "///" in db_url else "/data/neuromesh.db"
    seed_database(db_path)
