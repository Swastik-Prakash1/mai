"""FastAPI application entry point.

Registers all route modules and provides the health check endpoint.
"""

from fastapi import FastAPI

from api.routes import query, trace, eval, prompts

app = FastAPI(
    title="NeuroMesh",
    description=(
        "Multi-Agent Orchestration System with self-improving capabilities. "
        "Processes queries through decomposition, retrieval, critique, and synthesis agents "
        "with full provenance tracking and evaluation."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register route modules
app.include_router(query.router, tags=["Query"])
app.include_router(trace.router, tags=["Trace"])
app.include_router(eval.router, tags=["Evaluation"])
app.include_router(prompts.router, tags=["Prompts"])


@app.get("/health", tags=["Health"])
async def health():
    """Health check endpoint for Docker and load balancers."""
    return {"status": "ok", "service": "neuromesh-api"}
