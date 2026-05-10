"""Structured data lookup — NL→SQL against local SQLite.

Uses Claude API to convert natural language questions to SQL queries,
then executes against a knowledge_base table with 30 rows of structured data.

Failure contract:
- MALFORMED: if NL→SQL produces invalid SQL (sqlite3.OperationalError)
- EMPTY: if query returns 0 rows
- MALFORMED: INSERT/UPDATE/DELETE detected → reject
"""

from __future__ import annotations

import os
import re
import sqlite3

import anthropic

from tools.base import BaseTool, ToolResult
from logging_.structured import get_logger

logger = get_logger(__name__)

# Schema for the knowledge_base table
KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    value_numeric REAL,
    unit TEXT,
    description TEXT,
    region TEXT,
    year INTEGER
);
"""

# 30 rows of seed data covering countries with economic/demographic data
SEED_DATA: list[tuple] = [
    (1, "United States", "gdp", 28800.0, "billion_usd", "Nominal GDP of the United States", "North America", 2024),
    (2, "China", "gdp", 18500.0, "billion_usd", "Nominal GDP of China", "Asia", 2024),
    (3, "India", "gdp", 3900.0, "billion_usd", "Nominal GDP of India", "Asia", 2024),
    (4, "Germany", "gdp", 4500.0, "billion_usd", "Nominal GDP of Germany", "Europe", 2024),
    (5, "Japan", "gdp", 4200.0, "billion_usd", "Nominal GDP of Japan", "Asia", 2024),
    (6, "United Kingdom", "gdp", 3500.0, "billion_usd", "Nominal GDP of the UK", "Europe", 2024),
    (7, "France", "gdp", 3100.0, "billion_usd", "Nominal GDP of France", "Europe", 2024),
    (8, "Brazil", "gdp", 2200.0, "billion_usd", "Nominal GDP of Brazil", "South America", 2024),
    (9, "Canada", "gdp", 2100.0, "billion_usd", "Nominal GDP of Canada", "North America", 2024),
    (10, "Italy", "gdp", 2300.0, "billion_usd", "Nominal GDP of Italy", "Europe", 2024),
    (11, "India", "population", 1440.0, "million", "Population of India", "Asia", 2024),
    (12, "China", "population", 1425.0, "million", "Population of China", "Asia", 2024),
    (13, "United States", "population", 335.0, "million", "Population of the US", "North America", 2024),
    (14, "Germany", "population", 84.0, "million", "Population of Germany", "Europe", 2024),
    (15, "France", "population", 68.0, "million", "Population of France", "Europe", 2024),
    (16, "India", "gdp_growth", 6.8, "percent", "GDP growth rate of India", "Asia", 2024),
    (17, "China", "gdp_growth", 5.2, "percent", "GDP growth rate of China", "Asia", 2024),
    (18, "United States", "gdp_growth", 2.5, "percent", "GDP growth rate of the US", "North America", 2024),
    (19, "Germany", "gdp_growth", 0.3, "percent", "GDP growth rate of Germany", "Europe", 2024),
    (20, "India", "population_growth", 0.7, "percent", "Population growth rate of India", "Asia", 2024),
    (21, "Germany", "population_growth", -0.1, "percent", "Population growth rate of Germany (declining)", "Europe", 2024),
    (22, "GPT-4", "ml_benchmark", 86.4, "score", "MMLU benchmark score for GPT-4", "Global", 2024),
    (23, "Claude-3", "ml_benchmark", 86.8, "score", "MMLU benchmark score for Claude-3 Opus", "Global", 2024),
    (24, "Gemini-Ultra", "ml_benchmark", 90.0, "score", "MMLU benchmark score for Gemini Ultra", "Global", 2024),
    (25, "Llama-3", "ml_benchmark", 79.5, "score", "MMLU benchmark score for Llama-3 70B", "Global", 2024),
    (26, "Merge Sort", "algorithm_complexity", 0.0, "nlogn", "Time complexity of merge sort: O(n log n)", "Global", 2024),
    (27, "Quick Sort", "algorithm_complexity", 0.0, "nlogn_avg", "Average time complexity of quicksort: O(n log n)", "Global", 2024),
    (28, "Binary Search", "algorithm_complexity", 0.0, "logn", "Time complexity of binary search: O(log n)", "Global", 2024),
    (29, "France", "capital", 0.0, "city", "Paris is the capital of France", "Europe", 2024),
    (30, "Germany", "capital", 0.0, "city", "Berlin is the capital of Germany", "Europe", 2024),
]


def seed_knowledge_base(db_path: str) -> None:
    """Create and seed the knowledge_base table if empty."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(KNOWLEDGE_SCHEMA)
        cursor = conn.execute("SELECT COUNT(*) FROM knowledge_base")
        count = cursor.fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO knowledge_base VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                SEED_DATA,
            )
            conn.commit()
            logger.info(f"Seeded knowledge_base with {len(SEED_DATA)} rows")
    finally:
        conn.close()


class DbLookupTool(BaseTool):
    """Natural language to SQL lookup against local knowledge_base.

    Uses Claude API to convert NL question to SELECT query, executes against
    SQLite, returns rows as list of dicts.

    Failure contract:
    - MALFORMED: invalid SQL generated, or INSERT/UPDATE/DELETE attempted
    - EMPTY: query returns 0 rows
    """

    name: str = "db_lookup"

    def __init__(self, db_path: str = "/data/neuromesh.db") -> None:
        self.db_path = db_path

    async def call(self, input: dict) -> ToolResult:
        if "question" not in input:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Input dict must contain 'question' key",
            )

        question = str(input["question"]).strip()
        if not question:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Question is empty",
            )

        # Convert NL to SQL using Claude
        try:
            sql_query = await self._nl_to_sql(question)
        except Exception as exc:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message=f"NL→SQL conversion failed: {exc}",
            )

        # Reject destructive queries
        sql_upper = sql_query.upper().strip()
        if any(kw in sql_upper for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]):
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message=f"Destructive SQL rejected: {sql_query[:100]}",
            )

        # Execute query
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(sql_query)
                rows = [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message=f"SQL execution error: {exc}",
            )

        if not rows:
            return ToolResult(
                success=False,
                error_code="EMPTY",
                error_message=f"Query returned 0 rows: {sql_query[:100]}",
            )

        return ToolResult(
            success=True,
            data={"sql_query": sql_query, "rows": rows, "row_count": len(rows)},
        )

    async def _nl_to_sql(self, question: str) -> str:
        """Convert a natural language question to a SELECT SQL query via Claude."""
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        schema_desc = (
            "Table: knowledge_base\n"
            "Columns: id (int), name (text), category (text), value_numeric (real), "
            "unit (text), description (text), region (text), year (int)\n"
            "Categories include: gdp, population, gdp_growth, population_growth, "
            "ml_benchmark, algorithm_complexity, capital\n"
            "Example rows: ('India', 'gdp', 3900.0, 'billion_usd', ...), "
            "('GPT-4', 'ml_benchmark', 86.4, 'score', ...)"
        )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"Convert this question to a SQLite SELECT query. Return ONLY the SQL, "
                    f"no explanation.\n\nSchema:\n{schema_desc}\n\nQuestion: {question}"
                ),
            }],
        )

        sql = response.content[0].text.strip()
        # Strip markdown code fences if present
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        return sql.strip()
