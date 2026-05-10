"""Lightweight log query interface — internal tool for inspecting execution traces.

Provides:
- Search logs by job_id, agent_id, event_type, date range
- Full execution trace view
- Policy violation viewer
- Eval run history
- Raw SQL query (SELECT only)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse

from logging_.structured import get_logger

logger = get_logger(__name__)

app = FastAPI(title="NeuroMesh Log UI", version="0.1.0")

DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/neuromesh.db")
DB_PATH = DB_PATH.split("///")[-1] if "///" in DB_PATH else "/data/neuromesh.db"

HTML_HEAD = """
<!DOCTYPE html>
<html>
<head>
<title>NeuroMesh Log UI</title>
<style>
body { font-family: 'Courier New', monospace; background: #1a1a2e; color: #e0e0e0; margin: 20px; }
h1 { color: #00d4ff; }
h2 { color: #7b68ee; border-bottom: 1px solid #333; padding-bottom: 5px; }
a { color: #00d4ff; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; }
th, td { border: 1px solid #333; padding: 6px 10px; text-align: left; font-size: 13px; }
th { background: #16213e; color: #00d4ff; }
tr:nth-child(even) { background: #0f3460; }
tr:hover { background: #1a4080; }
input, textarea, select { background: #16213e; color: #e0e0e0; border: 1px solid #333; padding: 6px; margin: 4px; font-family: monospace; }
button { background: #00d4ff; color: #1a1a2e; border: none; padding: 8px 16px; cursor: pointer; font-weight: bold; }
button:hover { background: #7b68ee; }
.nav { margin-bottom: 20px; }
.nav a { margin-right: 15px; padding: 5px 10px; background: #16213e; text-decoration: none; }
.card { background: #16213e; padding: 15px; margin: 10px 0; border-radius: 5px; }
.violation { color: #ff6b6b; }
.success { color: #51cf66; }
pre { background: #0f3460; padding: 10px; overflow-x: auto; font-size: 12px; }
</style>
</head>
<body>
<h1>🧠 NeuroMesh Log UI</h1>
<div class="nav">
<a href="/">Home</a>
<a href="/jobs">Jobs</a>
<a href="/violations">Violations</a>
<a href="/evals">Evals</a>
<a href="/sql">SQL Query</a>
</div>
"""

HTML_FOOT = "</body></html>"


def _get_db():
    """Get a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_table(rows, columns=None):
    """Convert rows to HTML table."""
    if not rows:
        return "<p>No results found.</p>"
    if columns is None:
        columns = rows[0].keys() if hasattr(rows[0], "keys") else range(len(rows[0]))
    html = "<table><tr>"
    for col in columns:
        html += f"<th>{col}</th>"
    html += "</tr>"
    for row in rows:
        html += "<tr>"
        for col in columns:
            val = row[col] if hasattr(row, "__getitem__") else str(row)
            val_str = str(val)[:200]
            html += f"<td>{val_str}</td>"
        html += "</tr>"
    html += "</table>"
    return html


@app.get("/", response_class=HTMLResponse)
async def home():
    """Dashboard home page."""
    conn = _get_db()
    try:
        jobs_count = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()["c"]
        agent_logs_count = conn.execute("SELECT COUNT(*) as c FROM agent_logs").fetchone()["c"]
        tool_logs_count = conn.execute("SELECT COUNT(*) as c FROM tool_logs").fetchone()["c"]
        violations = conn.execute(
            "SELECT COUNT(*) as c FROM agent_logs WHERE policy_violation = 1"
        ).fetchone()["c"]
        eval_count = conn.execute("SELECT COUNT(*) as c FROM eval_runs").fetchone()["c"]
    except sqlite3.OperationalError:
        return HTMLResponse(HTML_HEAD + "<p>Database not yet initialized. Run migrations first.</p>" + HTML_FOOT)
    finally:
        conn.close()

    return HTMLResponse(HTML_HEAD + f"""
    <div class="card">
        <h2>📊 Dashboard</h2>
        <p>Total Jobs: <strong>{jobs_count}</strong></p>
        <p>Agent Log Entries: <strong>{agent_logs_count}</strong></p>
        <p>Tool Log Entries: <strong>{tool_logs_count}</strong></p>
        <p>Policy Violations: <strong class="{'violation' if violations else 'success'}">{violations}</strong></p>
        <p>Eval Runs: <strong>{eval_count}</strong></p>
    </div>
    <h2>🔍 Search Logs</h2>
    <form action="/search" method="get">
        <input type="text" name="job_id" placeholder="Job ID">
        <input type="text" name="agent_id" placeholder="Agent ID">
        <select name="event_type">
            <option value="">All Events</option>
            <option value="start">start</option>
            <option value="llm_call">llm_call</option>
            <option value="tool_call">tool_call</option>
            <option value="complete">complete</option>
            <option value="policy_violation">policy_violation</option>
        </select>
        <button type="submit">Search</button>
    </form>
    """ + HTML_FOOT)


@app.get("/search", response_class=HTMLResponse)
async def search(
    job_id: str = "",
    agent_id: str = "",
    event_type: str = "",
):
    """Search logs with filters."""
    conn = _get_db()
    try:
        query = "SELECT * FROM agent_logs WHERE 1=1"
        params = []
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY timestamp DESC LIMIT 100"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return HTMLResponse(HTML_HEAD + f"""
    <h2>Search Results ({len(rows)} rows)</h2>
    {_rows_to_table(rows)}
    """ + HTML_FOOT)


@app.get("/jobs", response_class=HTMLResponse)
async def list_jobs():
    """List all jobs."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, query, status, created_at, completed_at FROM jobs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    return HTMLResponse(HTML_HEAD + f"""
    <h2>📋 Jobs</h2>
    {_rows_to_table(rows)}
    """ + HTML_FOOT)


@app.get("/trace/{job_id}", response_class=HTMLResponse)
async def view_trace(job_id: str):
    """View full trace for a job."""
    conn = _get_db()
    try:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        agent_logs = conn.execute(
            "SELECT * FROM agent_logs WHERE job_id = ? ORDER BY timestamp", (job_id,)
        ).fetchall()
        tool_logs = conn.execute(
            "SELECT * FROM tool_logs WHERE job_id = ? ORDER BY timestamp", (job_id,)
        ).fetchall()
    finally:
        conn.close()

    html = f"<h2>Trace: {job_id}</h2>"
    if job:
        html += f"<div class='card'><strong>Query:</strong> {job['query']}<br><strong>Status:</strong> {job['status']}</div>"
    html += "<h3>Agent Logs</h3>" + _rows_to_table(agent_logs)
    html += "<h3>Tool Logs</h3>" + _rows_to_table(tool_logs)

    return HTMLResponse(HTML_HEAD + html + HTML_FOOT)


@app.get("/violations", response_class=HTMLResponse)
async def violations():
    """View all policy violations."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_logs WHERE policy_violation = 1 ORDER BY timestamp DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    return HTMLResponse(HTML_HEAD + f"""
    <h2 class="violation">⚠️ Policy Violations ({len(rows)})</h2>
    {_rows_to_table(rows)}
    """ + HTML_FOOT)


@app.get("/evals", response_class=HTMLResponse)
async def eval_history():
    """View eval run history."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, run_timestamp, summary_json FROM eval_runs ORDER BY run_timestamp DESC LIMIT 20"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    html = "<h2>📈 Eval History</h2>"
    for row in rows:
        summary = json.loads(row["summary_json"]) if row["summary_json"] else {}
        html += f"""
        <div class='card'>
            <strong>Run #{row['id']}</strong> — {row['run_timestamp']}<br>
            Overall: <strong>{summary.get('overall_average', 'N/A')}</strong> |
            Cat A: {summary.get('by_category', {}).get('A', 'N/A')} |
            Cat B: {summary.get('by_category', {}).get('B', 'N/A')} |
            Cat C: {summary.get('by_category', {}).get('C', 'N/A')}
        </div>
        """

    return HTMLResponse(HTML_HEAD + html + HTML_FOOT)


@app.get("/sql", response_class=HTMLResponse)
async def sql_form():
    """SQL query form."""
    return HTMLResponse(HTML_HEAD + """
    <h2>🗃️ Raw SQL Query</h2>
    <form action="/sql" method="post">
        <textarea name="query" rows="4" cols="80" placeholder="SELECT * FROM jobs LIMIT 10"></textarea><br>
        <button type="submit">Execute</button>
    </form>
    <p><em>SELECT queries only. Tables: jobs, agent_logs, tool_logs, eval_runs, prompt_rewrites, system_prompts</em></p>
    """ + HTML_FOOT)


@app.post("/sql", response_class=HTMLResponse)
async def sql_execute(query: str = Form("")):
    """Execute a SELECT-only SQL query."""
    if not query.strip():
        return HTMLResponse(HTML_HEAD + "<p>Empty query.</p>" + HTML_FOOT)

    # Reject non-SELECT queries
    if not query.strip().upper().startswith("SELECT"):
        return HTMLResponse(
            HTML_HEAD + "<p class='violation'>Only SELECT queries are allowed.</p>" + HTML_FOOT
        )

    conn = _get_db()
    try:
        rows = conn.execute(query).fetchall()
        table = _rows_to_table(rows)
    except Exception as exc:
        table = f"<p class='violation'>Error: {exc}</p>"
    finally:
        conn.close()

    return HTMLResponse(HTML_HEAD + f"""
    <h2>Query Results</h2>
    <pre>{query}</pre>
    {table}
    <a href="/sql">← New Query</a>
    """ + HTML_FOOT)
