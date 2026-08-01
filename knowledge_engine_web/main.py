"""FastAPI application: renders `core`'s knowledge graph, read-only.

No synthesis, no confidence computation, no judgment about what a claim
or relationship means -- see `docs/web_design.md`'s Out of Scope
section. Every value shown traces back to an actual row `core` already
persisted.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine, create_engine

from knowledge_engine_web.config import Settings
from knowledge_engine_web.evidence_reader import read_evidence_record
from knowledge_engine_web.graph_reader import (
    list_claims,
    list_relationship_candidates,
    list_unconfirmed_claims,
    read_claim_detail,
    read_graph_summary,
    read_paper_detail,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Knowledge Engine Web")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _engine() -> Engine:
    """Return an engine bound to `core`'s configured database, read-only by convention."""

    return create_engine(Settings().database_url)


@app.get("/graph", response_class=HTMLResponse)
def graph_summary(request: Request) -> HTMLResponse:
    """Render the graph's current corpus-wide population counts."""

    summary = read_graph_summary(_engine())
    return templates.TemplateResponse(
        request=request, name="graph_summary.html", context={"summary": summary}
    )


@app.get("/claims", response_class=HTMLResponse)
def claims_list(request: Request) -> HTMLResponse:
    """Render every claim in the graph, linking to its own detail page."""

    claims = list_claims(_engine())
    return templates.TemplateResponse(
        request=request,
        name="claims_list.html",
        context={
            "claims": claims,
            "heading": "Claims",
            "description": None,
            "empty_message": "No claims in the graph yet.",
        },
    )


@app.get("/unconfirmed-claims", response_class=HTMLResponse)
def unconfirmed_claims(request: Request) -> HTMLResponse:
    """Render every claim with zero relationship edges of any type.

    Mirrors `ke graph-unconfirmed-claims` -- the only "gap" this project
    can honestly surface without guessing. A claim listed here has no
    `supports`/`contradicts`/`qualifies`/`contextualizes`/`supersedes`
    edge yet, meaning no second claim has been reviewed and explicitly
    related to it. Not a judgment about the underlying science.
    """

    claims = list_unconfirmed_claims(_engine())
    return templates.TemplateResponse(
        request=request,
        name="claims_list.html",
        context={
            "claims": claims,
            "heading": "Unconfirmed Claims",
            "description": (
                "A claim listed here has no relationship edge yet -- meaning no "
                "second claim has been reviewed and explicitly related to it, "
                "nothing more. Not a judgment about the underlying science."
            ),
            "empty_message": "Every claim in the graph has at least one relationship edge.",
        },
    )


@app.get("/relationship-candidates", response_class=HTMLResponse)
def relationship_candidates(request: Request) -> HTMLResponse:
    """Render claim pairs sharing a PICO-resolved concept, for a human to review.

    Mirrors `ke graph-relationship-candidates`. Structural overlap only:
    never infers, detects, or suggests a relationship type or rationale
    -- that judgment call stays entirely with the human.
    """

    candidates = list_relationship_candidates(_engine())
    return templates.TemplateResponse(
        request=request,
        name="relationship_candidates.html",
        context={"candidates": candidates},
    )


@app.get("/claims/{evidence_record_id}", response_class=HTMLResponse)
def claim_detail(request: Request, evidence_record_id: str) -> HTMLResponse:
    """Render one claim's concepts (by PICO role), relationship edges, and evidence-record content.

    Evidence-record content (`claim_text`, `research_question`, and so
    on) is only shown if `KE_WEB_EVIDENCE_RECORDS_PATH` is configured --
    it is optional, since not every deployment has that JSONL file
    available alongside `core`'s database.
    """

    detail = read_claim_detail(_engine(), evidence_record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No claim found for that evidence record ID.")

    settings = Settings()
    evidence = (
        read_evidence_record(Path(settings.evidence_records_path), evidence_record_id)
        if settings.evidence_records_path
        else None
    )
    return templates.TemplateResponse(
        request=request,
        name="claim_detail.html",
        context={"claim": detail, "evidence": evidence},
    )


@app.get("/papers/{paper_id}", response_class=HTMLResponse)
def paper_detail(request: Request, paper_id: int) -> HTMLResponse:
    """Render one paper's citation edges, as citer and as cited."""

    detail = read_paper_detail(_engine(), paper_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No paper found with that database ID.")
    return templates.TemplateResponse(
        request=request, name="paper_detail.html", context={"paper": detail}
    )


def run() -> None:
    """Entry point for `poetry run knowledge-engine-web` -- starts a local dev server.

    Binds to `127.0.0.1:8000` by default -- override via `KE_WEB_HOST`/
    `KE_WEB_PORT` to serve beyond localhost (e.g. on a local network),
    see `docs/deployment.md`.
    """

    import uvicorn

    settings = Settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
