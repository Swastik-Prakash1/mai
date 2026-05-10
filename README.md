# 🧠 NeuroMesh — Multi-Agent Orchestration System

> A production-grade, containerized multi-agent AI system with self-improving capabilities, full provenance tracking, and automated evaluation.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        FastAPI (SSE)                         │
│  POST /query  │ GET /trace/{id} │ GET /eval │ POST /prompts │
└──────────┬───────────────────────────────────────────────────┘
           │ Redis Queue (BLPOP)
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Background Worker                         │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Orchestrator Agent (LLM-planned)           │ │
│  │  ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌───────────┐ │ │
│  │  │Decompose │→│ Retrieval │→│Critique │→│ Synthesis │ │ │
│  │  │(DAG sort)│ │(2-hop RAG)│ │(span)   │ │(provenance│ │ │
│  │  └──────────┘ └───────────┘ └────┬────┘ └───────────┘ │ │
│  │                                  │ flags?              │ │
│  │                            ┌─────▼─────┐              │ │
│  │                            │  Retry +   │              │ │
│  │                            │Re-synthesis│              │ │
│  │                            └────────────┘              │ │
│  │  ┌────────────┐  ┌──────────────┐                      │ │
│  │  │Compression │  │  Meta Agent   │                      │ │
│  │  │(on overflow)│  │(prompt rewrite)│                     │ │
│  │  └────────────┘  └──────────────┘                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                        SharedContext                         │
│              (sole inter-agent communication)                │
└──────────────────────────────────────────────────────────────┘
           │                              │
     ┌─────▼─────┐                 ┌──────▼──────┐
     │  SQLite   │                 │  ChromaDB   │
     │ (6 tables)│                 │ (vectors)   │
     └───────────┘                 └─────────────┘
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Agents never call each other** | Only the Orchestrator holds routing logic — prevents circular dependencies and enables full trace reconstruction |
| **SharedContext is the sole communication bus** | Every agent reads from and writes to the same Pydantic schema — enables deterministic replay and budget tracking |
| **Span-level critique, not output-level** | Critique agent flags specific text spans with confidence scores, not entire outputs — enables surgical fixes |
| **2-hop minimum retrieval** | Forces the system to identify information gaps and fill them, producing more comprehensive answers |
| **Human-in-the-loop prompt rewrites** | Meta-agent proposes prompt changes but never auto-applies — `/prompts/review` endpoint for approval/rejection |
| **Budget overflow → compression, not truncation** | When an agent exceeds its token budget, the compression agent summarizes filler while preserving all structured data verbatim |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API key

### Launch (zero extra steps)

```bash
# 1. Clone the repo
git clone <repo-url> && cd neuromesh

# 2. Set your API key
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY=sk-ant-...

# 3. Launch all 4 services
docker compose up --build
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| **API** | `8000` | FastAPI with SSE streaming, Swagger at `/docs` |
| **Worker** | — | Background job processor (Redis BLPOP) |
| **Redis** | `6379` | Job queue + SSE event pub/sub |
| **Log UI** | `8080` | Internal trace viewer, violation inspector, SQL query |

---

## API Endpoints

### 1. `POST /query` — Submit a query
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the time complexity of merge sort?"}'
```
Returns `job_id`. Connect to SSE stream for real-time events:
```bash
curl -N http://localhost:8000/query/stream/{job_id}
```

**SSE Event Types:**
- `agent_start` — Agent begins processing
- `agent_complete` — Agent finished with token count
- `final_answer` — Complete answer with provenance map
- `error` — Processing failure

### 2. `GET /trace/{job_id}` — Full execution trace
```bash
curl http://localhost:8000/trace/{job_id}
```
Returns ordered list of all agent decisions, tool calls, latencies, and handoffs.

### 3. `GET /eval/latest` — Latest evaluation scores
```bash
curl http://localhost:8000/eval/latest
```
Returns scores broken down by:
- **Category**: A (straightforward), B (ambiguous), C (adversarial)
- **Dimension**: answer_correctness, citation_accuracy, contradiction_resolution, tool_efficiency, budget_compliance, critique_agreement

### 4. `POST /prompts/review` — Approve/reject prompt rewrites
```bash
curl -X POST http://localhost:8000/prompts/review \
  -H "Content-Type: application/json" \
  -d '{"rewrite_id": 1, "decision": "approved"}'
```

### 5. `POST /eval/rerun` — Re-run evaluation
```bash
curl -X POST http://localhost:8000/eval/rerun \
  -H "Content-Type: application/json" \
  -d '{"only_failed": true}'
```
Re-runs only test cases where any dimension scored < 6. Returns delta against previous run.

---

## Agent Pipeline

### 7 Specialized Agents

| Agent | Role | Budget | Key Feature |
|-------|------|--------|-------------|
| **Orchestrator** | Plans and coordinates agent execution | 8000 | LLM-driven execution planning with fallback |
| **Decomposition** | Breaks queries into typed sub-tasks | 4000 | Kahn's algorithm topological sort on dependency DAG |
| **Retrieval** | Multi-hop search with citation tracking | 6000 | Minimum 2 hops, each chunk tagged with `hop_number` |
| **Critique** | Span-level confidence scoring | 5000 | Flags specific text spans, never entire outputs |
| **Synthesis** | Contradiction resolution + provenance | 6000 | Sentence-level provenance map with `[chunk_id]` citations |
| **Compression** | Context compression on budget overflow | 3000 | Preserves structured data verbatim, summarizes only filler |
| **Meta** | Self-improving prompt rewrite proposals | 4000 | Analyzes worst agent×dimension, proposes diffs for human review |

### Execution Flow
1. **Orchestrator** asks Claude for an execution plan (with fallback default)
2. **Decomposition** breaks query into sub-tasks with dependency graph
3. **Retrieval** performs 2-hop search, produces cited chunks
4. **Critique** reviews all outputs for contradictions and unsupported claims
5. **Synthesis** resolves contradictions, produces final answer with provenance
6. If critique flagged issues → retry the flagged agent → re-synthesize
7. If budget overflow → **Compression** agent triggered

---

## Tools Layer

| Tool | Type | Failure Modes |
|------|------|---------------|
| **Web Search** | Deterministic stub (20-doc corpus) | TIMEOUT, EMPTY, MALFORMED |
| **Code Execution** | Subprocess sandbox (10s timeout) | BLOCKED_IMPORT, TIMEOUT, SYNTAX_ERROR |
| **DB Lookup** | NL→SQL via Claude (30-row seed) | DESTRUCTIVE_QUERY_BLOCKED, PARSE_ERROR |
| **Self-Reflection** | Agent history analysis | INSUFFICIENT_HISTORY |

All tools implement `BaseTool` ABC with:
- Standardized `ToolResult` interface
- Automatic execution timing
- SharedContext recording (every tool call logged)
- Explicit failure contracts (no silent failures)

---

## Evaluation Harness

### 15 Test Cases (3 Categories)

| Category | Cases | Description |
|----------|-------|-------------|
| **A** (1-5) | Straightforward | Known correct answers (merge sort complexity, capital of France, etc.) |
| **B** (6-10) | Ambiguous | Underspecified queries ("Tell me about the model", "Is it fast?") |
| **C** (11-15) | Adversarial | Prompt injection, wrong premises, data contradictions, overconfidence |

### 6 Scoring Dimensions (0-10 each)

1. **Answer Correctness** — Category-aware: keyword match (A), ambiguity detection (B), injection refusal (C)
2. **Citation Accuracy** — Do `[chunk_id]` references trace to real retrieved chunks?
3. **Contradiction Resolution** — Were critique-flagged spans addressed in final answer?
4. **Tool Selection Efficiency** — Penalizes unnecessary tool calls beyond expected count
5. **Context Budget Compliance** — Deducts 3 points per policy violation
6. **Critique Agent Agreement** — What % of flagged spans were addressed?

### Self-Improving Loop
1. After each eval run, Meta Agent identifies the worst-performing agent×dimension
2. Meta Agent proposes a rewritten system prompt with line-level diff
3. Human reviews via `POST /prompts/review` (approve/reject)
4. On approval, new prompt version is activated; old version preserved
5. `POST /eval/rerun` re-evaluates with the new prompt, returns delta

---

## Database Schema

6 tables in SQLite:

| Table | Purpose |
|-------|---------|
| `jobs` | Query processing jobs with status tracking |
| `agent_logs` | Full audit trail of agent events (indexed by job_id, agent_id) |
| `tool_logs` | Tool invocation records with retry counts |
| `eval_runs` | Evaluation run results with scores and summaries |
| `prompt_rewrites` | Meta-agent proposed prompt changes (pending/approved/rejected) |
| `system_prompts` | Versioned system prompts for each agent |

---

## Project Structure

```
neuromesh/
├── api/
│   ├── main.py              # FastAPI app entry point
│   ├── dependencies.py       # DB sessions, Redis client, settings
│   ├── schemas.py            # Pydantic request/response models
│   ├── seed.py               # Database seeding script
│   └── routes/
│       ├── query.py          # POST /query + SSE stream
│       ├── trace.py          # GET /trace/{job_id}
│       ├── eval.py           # GET /eval/latest + POST /eval/rerun
│       └── prompts.py        # POST /prompts/review
├── agents/
│   ├── base.py               # BaseAgent ABC with call_llm() wrapper
│   ├── orchestrator.py       # Master orchestrator (LLM-planned routing)
│   ├── decomposition.py      # Query → sub-task DAG with topological sort
│   ├── retrieval.py          # 2-hop RAG with citation tracking
│   ├── critique.py           # Span-level confidence scoring
│   ├── synthesis.py          # Contradiction resolution + provenance map
│   ├── compression.py        # Budget overflow handler
│   └── meta.py               # Self-improving prompt rewrite proposals
├── context/
│   ├── shared_context.py     # 10+ Pydantic models (sole comms bus)
│   └── budget_manager.py     # tiktoken-based token budget tracking
├── tools/
│   ├── base.py               # BaseTool ABC + ToolResult
│   ├── web_search.py         # Deterministic 20-doc search stub
│   ├── code_exec.py          # Sandboxed Python execution
│   ├── db_lookup.py          # NL→SQL with destructive query blocking
│   └── self_reflection.py    # Agent history contradiction analysis
├── eval/
│   ├── test_cases.py         # 15 test cases (A/B/C categories)
│   ├── scorer.py             # 6-dimension scoring engine
│   ├── harness.py            # Eval runner + summary builder
│   └── diff.py               # Structured diff between eval runs
├── db/
│   ├── models.py             # 6 SQLAlchemy ORM models
│   ├── init_db.py            # Table creation + seeding on startup
│   └── migrations/
│       └── versions/
│           └── 001_initial_schema.py
├── worker/
│   └── processor.py          # Redis BLPOP → orchestrator → SSE publish
├── log_ui/
│   └── app.py                # Internal log viewer (dark theme)
├── logging_/
│   └── structured.py         # JSON structured logging
├── tests/
│   ├── test_context.py       # 14 tests: SharedContext + BudgetManager
│   ├── test_tools.py         # 7 tests: WebSearch + CodeExec
│   ├── test_agents.py        # 6 tests: topological sort
│   └── test_eval.py          # 16 tests: test cases + scorer + diff
├── docker-compose.yml        # 4-service stack
├── Dockerfile.api
├── Dockerfile.worker
├── Dockerfile.log_ui
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Running Tests

```bash
# All 36 tests (no API key needed)
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_eval.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Claude API key |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/neuromesh.db` | SQLite database path |
| `CHROMA_PERSIST_DIR` | `/data/chroma` | ChromaDB persistence directory |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## License

MIT
