"""FastAPI application: renders `core`'s knowledge graph, read-only.

Every value shown traces back to an actual row `core` already persisted.
As of M1 (see `docs/web_design.md`'s Out of Scope section, "Revised for
Evidence Intelligence"), the one exception is a deterministic,
no-LLM confidence-scoring computation
(`knowledge_engine_web/evidence_intelligence.py`) -- still never an
invented number, still never a judgment call this project makes itself,
just arithmetic over already-stored, already-human-reviewed fields.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine, create_engine

from knowledge_engine_web.alpha_auth import AlphaBasicAuthMiddleware
from knowledge_engine_web.config import Settings
from knowledge_engine_web.dashboard import build_evidence_intelligence_dashboard
from knowledge_engine_web.evidence_intelligence import (
    compute_claim_confidence,
    compute_evidence_consensus,
    compute_evidence_coverage,
    compute_evidence_quality,
    render_synthesis,
)
from knowledge_engine_web.evidence_reader import (
    EvidenceRecordDetail,
    count_evidence_records,
    list_evidence_records_for_doi,
    read_evidence_record,
)
from knowledge_engine_web.graph_reader import (
    RelationshipEdge,
    list_claims,
    list_relationship_candidates,
    list_unconfirmed_claims,
    read_claim_detail,
    read_graph_summary,
    read_paper_detail,
)
from knowledge_engine_web.llm import LocalLLMError, OllamaLLM
from knowledge_engine_web.relationship_reader import (
    list_relationship_records_for_evidence_record_id,
)
from knowledge_engine_web.report_renderer import (
    render_graph_summary_report,
    render_relationship_candidates_report,
    render_unconfirmed_claims_report,
    render_whats_changed_report,
)
from knowledge_engine_web.retrieval import SearchResult, answer_retrieval
from knowledge_engine_web.snapshot_metadata import read_snapshot_metadata
from knowledge_engine_web.synthesis import synthesize_answer
from knowledge_engine_web.whats_changed import build_whats_changed_summary

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Knowledge Engine Web")
app.add_middleware(AlphaBasicAuthMiddleware)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _snapshot_context(_: Request) -> dict[str, object]:
    return {"snapshot": read_snapshot_metadata(Path(Settings().snapshot_metadata_path))}


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR), context_processors=[_snapshot_context])

_DEMO_EVIDENCE_RECORD_ID = "ev-glp1-select-trial-weight-loss-208wk-001"


def _engine() -> Engine:
    """Return an engine bound to `core`'s configured database, read-only by convention."""

    return create_engine(Settings().database_url)


def _evidence_path() -> Path | None:
    """Return `core`'s configured evidence-records path, or `None` if not set."""

    settings = Settings()
    return Path(settings.evidence_records_path) if settings.evidence_records_path else None


def _whats_changed_baseline_path() -> Path:
    """Return the configured "what changed" baseline path.

    Always a real path (default `data/whats_changed_baseline.json`,
    alongside the DB's own default location) -- a missing file at that
    path is a normal, expected state (`whats_changed.read_baseline_json`
    returns `None`), not a configuration error.
    """

    return Path(Settings().whats_changed_baseline_path)


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """Redirect the bare domain to /graph -- the site's actual home page.

    Without this, a first-time visitor hitting the root URL (the normal
    thing to do) got FastAPI's default {"detail": "Not Found"} JSON,
    since no route was ever defined for "/" itself.
    """

    return RedirectResponse(url="/demo")


@app.get("/demo", response_class=HTMLResponse)
def demo(request: Request) -> HTMLResponse:
    """Render one stable, source-linked example of the implemented public workflow."""

    claim = read_claim_detail(_engine(), _DEMO_EVIDENCE_RECORD_ID)
    evidence_path = _evidence_path()
    evidence = (
        read_evidence_record(evidence_path, _DEMO_EVIDENCE_RECORD_ID) if evidence_path else None
    )
    intelligence = None
    if claim is not None and evidence is not None and evidence_path is not None:
        intelligence = _compute_evidence_intelligence(evidence_path, evidence, claim.relationships)
    return templates.TemplateResponse(
        request=request,
        name="demo.html",
        context={"claim": claim, "evidence": evidence, "intelligence": intelligence},
    )


@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> HTMLResponse:
    """Explain what this site is, the seam it holds, and what "alpha" means here."""

    return templates.TemplateResponse(request=request, name="about.html", context={})


@app.get("/roadmap", response_class=HTMLResponse)
def roadmap(request: Request) -> HTMLResponse:
    """Show what's shipped, what's next, and a clearly-labeled preview of a future feature.

    The embedded concept preview (static/concept-preview.html) shows a
    synthesized answer to a research question -- a deliberate departure
    from this site's "nothing inferred or synthesized" rule everywhere
    else, so it's isolated in its own iframe and banner-labeled as a
    non-functional mockup, never presented as a working feature.
    """

    return templates.TemplateResponse(request=request, name="roadmap.html", context={})


@app.get("/graph", response_class=HTMLResponse)
def graph_summary(request: Request) -> HTMLResponse:
    """Render the graph's current corpus-wide population counts."""

    summary = read_graph_summary(_engine())
    return templates.TemplateResponse(
        request=request, name="graph_summary.html", context={"summary": summary}
    )


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Render the corpus-wide Evidence Intelligence dashboard.

    Extends M58/M1's per-claim Evidence Quality/Claim Confidence
    computation to a corpus-wide distribution -- see
    `knowledge_engine_web/dashboard.py`. Only shown for claims with
    `KE_WEB_EVIDENCE_RECORDS_PATH` configured and a record on file, the
    same "not configured" posture every other Evidence Intelligence
    surface in this project already follows.
    """

    settings = Settings()
    if not settings.evidence_records_path:
        return templates.TemplateResponse(
            request=request, name="dashboard.html", context={"summary": None}
        )
    summary = build_evidence_intelligence_dashboard(_engine(), Path(settings.evidence_records_path))
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context={"summary": summary}
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


@app.get(
    "/relationship-candidates/{evidence_record_id_a}/{evidence_record_id_b}",
    response_class=HTMLResponse,
)
def relationship_candidate_compare(
    request: Request, evidence_record_id_a: str, evidence_record_id_b: str
) -> HTMLResponse:
    """Render two claims' full evidence content side by side, for reviewing one candidate pair.

    The same fields `ke relationship-review-worksheet` assembles into a
    Markdown document, rendered as a browsable page instead -- reviewing
    from the browser rather than a generated CLI document, the last
    named item from `docs/future_ideas.md`'s Reviewer Tooling section.
    Never infers, scores, or suggests a relationship; deciding whether
    one exists remains entirely a human judgment call, authored
    directly in `core`'s `relationship_records.jsonl`.
    """

    engine = _engine()
    detail_a = read_claim_detail(engine, evidence_record_id_a)
    detail_b = read_claim_detail(engine, evidence_record_id_b)
    if detail_a is None or detail_b is None:
        raise HTTPException(status_code=404, detail="No claim found for that evidence record ID.")

    shared_concept_labels = sorted(
        {concept.label for concept in detail_a.concepts}
        & {concept.label for concept in detail_b.concepts}
    )

    evidence_path = _evidence_path()
    evidence_a = None
    evidence_b = None
    if evidence_path is not None:
        evidence_a = read_evidence_record(evidence_path, evidence_record_id_a)
        evidence_b = read_evidence_record(evidence_path, evidence_record_id_b)

    return templates.TemplateResponse(
        request=request,
        name="relationship_compare.html",
        context={
            "columns": [
                (detail_a, evidence_a),
                (detail_b, evidence_b),
            ],
            "shared_concept_labels": shared_concept_labels,
        },
    )


_REPORTS: dict[str, tuple[str, str, Callable[[Engine, Path | None], str]]] = {
    "graph": (
        "Graph Report",
        "The corpus-wide population counts -- the same report `ke graph-report` prints.",
        lambda engine, evidence_path: render_graph_summary_report(read_graph_summary(engine)),
    ),
    "relationship-candidates": (
        "Relationship Candidates Report",
        "Claim pairs sharing a PICO-resolved concept with no relationship edge yet.",
        lambda engine, evidence_path: render_relationship_candidates_report(
            list_relationship_candidates(engine)
        ),
    ),
    "unconfirmed-claims": (
        "Unconfirmed Claims Report",
        "Claims with no relationship edge of any type yet.",
        lambda engine, evidence_path: render_unconfirmed_claims_report(
            list_unconfirmed_claims(engine)
        ),
    ),
    "what-changed": (
        "What Changed Report",
        "New claims, new relationship edges, and aggregate deltas since the "
        "last captured baseline.",
        lambda engine, evidence_path: render_whats_changed_report(
            build_whats_changed_summary(engine, evidence_path, _whats_changed_baseline_path())
        ),
    ),
}


@app.get("/reports", response_class=HTMLResponse)
def reports_index(request: Request) -> HTMLResponse:
    """List the available Markdown reports, each viewable and downloadable.

    These mirror `core`'s `ke graph-report`/`ke graph-relationship-candidates`/
    `ke graph-unconfirmed-claims` Markdown output exactly, rebuilt here
    from the same data the rest of this site already reads -- not by
    shelling out to `ke`, which the alpha deployment doesn't have.
    """

    reports = [
        {"slug": slug, "title": title, "description": description}
        for slug, (title, description, _) in _REPORTS.items()
    ]
    return templates.TemplateResponse(
        request=request, name="reports_index.html", context={"reports": reports}
    )


@app.get("/reports/{report_slug}.md")
def report_download(report_slug: str) -> Response:
    """Download one report as a raw `.md` file.

    Registered before the bare `/reports/{report_slug}` route below --
    Starlette matches path routes in registration order, and its simple
    string path converter would otherwise let that route's `report_slug`
    swallow the literal `.md` suffix too.
    """

    entry = _REPORTS.get(report_slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="No report with that name.")
    _, _, render = entry
    report_text = render(_engine(), _evidence_path())
    return Response(
        content=report_text,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{report_slug}-report.md"'},
    )


@app.get("/reports/{report_slug}", response_class=HTMLResponse)
def report_view(request: Request, report_slug: str) -> HTMLResponse:
    """Render one report as a page, with a link to download it as Markdown."""

    entry = _REPORTS.get(report_slug)
    if entry is None:
        raise HTTPException(status_code=404, detail="No report with that name.")
    title, _, render = entry
    report_text = render(_engine(), _evidence_path())
    return templates.TemplateResponse(
        request=request,
        name="report_view.html",
        context={"title": title, "report_slug": report_slug, "report_text": report_text},
    )


@app.get("/claims/{evidence_record_id}", response_class=HTMLResponse)
def claim_detail(request: Request, evidence_record_id: str) -> HTMLResponse:
    """Render one claim's concepts (by PICO role), relationship edges, and evidence-record content.

    Evidence-record content (`claim_text`, `research_question`, and so
    on) is only shown if `KE_WEB_EVIDENCE_RECORDS_PATH` is configured --
    it is optional, since not every deployment has that JSONL file
    available alongside `core`'s database.

    Each relationship edge's `provenance` (who determined it, and how --
    manual review or automated) comes from the `RelationshipRecord`
    JSONL directly, keyed by the same `relationship_id` `core`'s SQL
    mirror (`graph_claim_relationships`, what `detail.relationships`
    already reads) carries -- shown only if
    `KE_WEB_RELATIONSHIP_RECORDS_PATH` is configured, since the SQL edge
    itself has `relationship_type`/`rationale` but not a record's own
    authorship. See `relationship_reader.py`.
    """

    detail = read_claim_detail(_engine(), evidence_record_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No claim found for that evidence record ID.")

    settings = Settings()
    evidence = None
    intelligence = None
    if settings.evidence_records_path:
        evidence_path = Path(settings.evidence_records_path)
        evidence = read_evidence_record(evidence_path, evidence_record_id)
        if evidence is not None:
            intelligence = _compute_evidence_intelligence(
                evidence_path, evidence, detail.relationships
            )

    relationship_provenance = {}
    if settings.relationship_records_path:
        relationship_path = Path(settings.relationship_records_path)
        for record in list_relationship_records_for_evidence_record_id(
            relationship_path, evidence_record_id
        ):
            relationship_provenance[record.relationship_id] = record

    return templates.TemplateResponse(
        request=request,
        name="claim_detail.html",
        context={
            "claim": detail,
            "evidence": evidence,
            "intelligence": intelligence,
            "relationship_provenance": relationship_provenance,
        },
    )


def _compute_evidence_intelligence(
    evidence_path: Path, evidence: EvidenceRecordDetail, relationships: list[RelationshipEdge]
) -> dict[str, object]:
    """Compute Evidence Quality, Consensus, Claim Confidence, and Coverage for one claim.

    See `knowledge_engine_web/evidence_intelligence.py`. Reads each
    `supports`/`contradicts` partner's own evidence record (a handful of
    extra JSONL scans at the corpus's current ~150-record scale) so Claim
    Confidence's "mean quality of participating records" reflects every
    claim actually in agreement, not just this one.
    """

    quality = compute_evidence_quality(evidence)
    consensus = compute_evidence_consensus(relationships)

    participating_qualities = [quality]
    seen_other_ids: set[str] = set()
    for relationship in relationships:
        if relationship.relationship_type not in ("supports", "contradicts"):
            continue
        other_id = relationship.other_evidence_record_id
        if other_id in seen_other_ids or other_id == evidence.evidence_record_id:
            continue
        seen_other_ids.add(other_id)
        other_evidence = read_evidence_record(evidence_path, other_id)
        if other_evidence is not None:
            participating_qualities.append(compute_evidence_quality(other_evidence))

    confidence = compute_claim_confidence(participating_qualities, consensus)

    summary = read_graph_summary(_engine())
    records_in_relationship = summary.claims_total - len(list_unconfirmed_claims(_engine()))
    coverage = compute_evidence_coverage(
        total_records=count_evidence_records(evidence_path),
        records_in_relationship=records_in_relationship,
    )

    synthesis = render_synthesis(
        consensus=consensus, quality=quality, confidence=confidence, coverage=coverage
    )

    return {
        "quality": quality,
        "consensus": consensus,
        "confidence": confidence,
        "coverage": coverage,
        "synthesis": synthesis,
    }


@app.get("/ask", response_class=HTMLResponse)
def ask(request: Request, q: str = "", synthesize: bool = False) -> HTMLResponse:
    """Answer a natural-language research question: ranked papers, plus per-claim confidence.

    Retrieval, via `core`'s own FTS5 index (`retrieval.py`), is always
    the primary result -- no single "the answer" verdict. Each matched
    paper's evidence records (matched by DOI, `KE_WEB_EVIDENCE_RECORDS_PATH`
    permitting) show their own already-computed Evidence Intelligence
    numbers exactly as `/claims/{evidence_record_id}` does, when a graph
    claim exists for them -- never a new number, never a judgment this
    project invents for the occasion.

    `synthesize=1` is the one opt-in exception: a local, offline LLM
    (served by Ollama, `KE_WEB_LLM_MODEL` required) narrates that same
    already-computed evidence into one grounded paragraph -- see
    `knowledge_engine_web/synthesis.py` and `docs/web_design.md`'s
    "Decision: local LLM" section. Off by default: real inference, not
    free, and a person should ask for it explicitly.
    """

    question = q.strip()
    if not question:
        return templates.TemplateResponse(
            request=request, name="ask.html", context={"question": "", "results": None}
        )

    settings = Settings()
    evidence_path = Path(settings.evidence_records_path) if settings.evidence_records_path else None
    engine = _engine()
    papers = answer_retrieval(engine, question, limit=5, evidence_path=evidence_path)

    results = [
        {
            "paper": paper,
            "evidence_entries": _evidence_entries_for_paper(engine, evidence_path, paper),
        }
        for paper in papers
    ]

    synthesis: str | None = None
    synthesis_error: str | None = None
    if synthesize:
        if not settings.llm_model:
            synthesis_error = (
                "Synthesis is not configured on this server -- KE_WEB_LLM_MODEL must be set."
            )
        else:
            try:
                llm = OllamaLLM(model=settings.llm_model, host=settings.ollama_host)
                synthesis = synthesize_answer(question, results, llm)
            except LocalLLMError as exc:
                synthesis_error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="ask.html",
        context={
            "question": question,
            "results": results,
            "synthesize_requested": synthesize,
            "synthesis": synthesis,
            "synthesis_error": synthesis_error,
        },
    )


def _evidence_entries_for_paper(
    engine: Engine, evidence_path: Path | None, paper: SearchResult
) -> list[dict[str, object]]:
    """Return one paper's evidence records, each paired with its Evidence Intelligence if any."""

    if evidence_path is None or not paper.doi:
        return []

    entries: list[dict[str, object]] = []
    for evidence in list_evidence_records_for_doi(evidence_path, paper.doi):
        intelligence = None
        detail = read_claim_detail(engine, evidence.evidence_record_id)
        if detail is not None:
            intelligence = _compute_evidence_intelligence(
                evidence_path, evidence, detail.relationships
            )
        entries.append({"evidence": evidence, "intelligence": intelligence})
    return entries


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
