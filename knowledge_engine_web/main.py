"""FastAPI application: renders `core`'s knowledge graph, read-only.

No synthesis, no confidence computation, no judgment about what a claim
or relationship means -- see `docs/web_design.md`'s Out of Scope
section. Every value shown traces back to an actual row `core` already
persisted.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine

from knowledge_engine_web.config import Settings
from knowledge_engine_web.graph_reader import read_graph_summary

_TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Knowledge Engine Web")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@app.get("/graph", response_class=HTMLResponse)
def graph_summary(request: Request) -> HTMLResponse:
    """Render the graph's current corpus-wide population counts."""

    settings = Settings()
    engine = create_engine(settings.database_url)
    summary = read_graph_summary(engine)
    return templates.TemplateResponse(
        request=request, name="graph_summary.html", context={"summary": summary}
    )


def run() -> None:
    """Entry point for `poetry run knowledge-engine-web` -- starts a local dev server."""

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
