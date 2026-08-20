"""FastAPI application: renders `core`'s knowledge graph, read-only.

Every value shown traces back to an actual row `core` already persisted.
As of M1 (see `docs/web_design.md`'s Out of Scope section, "Revised for
Evidence Intelligence"), the one exception is a deterministic,
no-LLM confidence-scoring computation
(`knowledge_engine_web/evidence_intelligence.py`) -- still never an
invented number, still never a judgment call this project makes itself,
just arithmetic over already-stored, already-classified fields.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from knowledge_engine_ai.ke_client import FederatedProviderStatus
from sqlalchemy import Engine, create_engine

from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.ai_orchestration import (
    AIOrchestrationError,
    evaluate_ai_capability,
    result_reached_execution_limit,
    run_guarded_ai_orchestration,
)
from knowledge_engine_web.alpha_auth import AlphaBasicAuthMiddleware
from knowledge_engine_web.config import Settings
from knowledge_engine_web.dashboard import build_evidence_intelligence_dashboard
from knowledge_engine_web.discovery_freshness import (
    build_candidate_freshness,
    build_discovery_freshness,
)
from knowledge_engine_web.discovery_orchestration import (
    DiscoveryOrchestrationError,
    evaluate_discovery_capability,
    run_discovery_candidate_snapshot,
    run_discovery_history,
    run_guarded_discovery,
)
from knowledge_engine_web.discovery_presentation import build_discovery_presentation
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
    list_relationships,
    list_unconfirmed_claims,
    read_claim_detail,
    read_graph_summary,
    read_paper_detail,
)
from knowledge_engine_web.graph_visual import (
    build_relationship_network_svg,
    relationship_type_legend,
)
from knowledge_engine_web.relationship_reader import (
    list_relationship_records_for_evidence_record_id,
)
from knowledge_engine_web.report_renderer import (
    render_graph_summary_report,
    render_relationship_candidates_report,
    render_unconfirmed_claims_report,
    render_whats_changed_report,
)
from knowledge_engine_web.research_question import derive_research_question_id
from knowledge_engine_web.retrieval import SearchResult, answer_retrieval
from knowledge_engine_web.snapshot_metadata import read_snapshot_metadata
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the public landing page: mission, real corpus numbers, one CTA.

    Roadmap's "Current Project Path" item 1 ("One coherent public
    journey") calls for connecting the mission-first public showcase
    (https://knowledge-engine.steelzombie9999.chatgpt.site/) to this live
    laboratory. This page is that connection point -- it never invents
    copy or numbers the rest of the site doesn't already show: the corpus
    stats and network visual reuse the exact same `read_graph_summary`/
    `build_relationship_network_svg` path `/graph` uses.
    """

    engine = _engine()
    summary = read_graph_summary(engine)
    relationships = list_relationships(engine)
    evidence_path = _evidence_path()
    titles: dict[str, str] = {}
    if evidence_path is not None:
        node_ids = {relationship.source_evidence_record_id for relationship in relationships} | {
            relationship.target_evidence_record_id for relationship in relationships
        }
        for evidence_record_id in node_ids:
            record = read_evidence_record(evidence_path, evidence_record_id)
            if record is not None and record.source_title:
                titles[evidence_record_id] = record.source_title
    network_svg = build_relationship_network_svg(relationships, titles, width=620, height=560)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"summary": summary, "network_svg": network_svg},
    )


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
    """Render the graph's current corpus-wide population counts and a
    reviewed-relationship network visual.

    The visual is a deterministic SVG drawn from the exact rows
    `list_relationships` already returns -- no new query shape, no
    inferred structure, no client-side layout library. See
    `graph_visual.py`.
    """

    engine = _engine()
    summary = read_graph_summary(engine)
    relationships = list_relationships(engine)
    evidence_path = _evidence_path()
    titles: dict[str, str] = {}
    if evidence_path is not None:
        node_ids = {relationship.source_evidence_record_id for relationship in relationships} | {
            relationship.target_evidence_record_id for relationship in relationships
        }
        for evidence_record_id in node_ids:
            record = read_evidence_record(evidence_path, evidence_record_id)
            if record is not None and record.source_title:
                titles[evidence_record_id] = record.source_title
    network_svg = build_relationship_network_svg(relationships, titles)
    legend = relationship_type_legend(relationships)
    return templates.TemplateResponse(
        request=request,
        name="graph_summary.html",
        context={
            "summary": summary,
            "network_svg": network_svg,
            "network_legend": legend,
            "network_claim_count": len(
                {relationship.source_evidence_record_id for relationship in relationships}
                | {relationship.target_evidence_record_id for relationship in relationships}
            ),
            "network_relationship_count": len(relationships),
        },
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
    edge yet, meaning no second claim has been classified and explicitly
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
                "second claim has been classified and explicitly related to it, "
                "nothing more. Not a judgment about the underlying science."
            ),
            "empty_message": "Every claim in the graph has at least one relationship edge.",
        },
    )


_RELATIONSHIP_CANDIDATES_MINIMUM_SHARED_CONCEPTS = 2
_RELATIONSHIP_CANDIDATES_DISPLAY_LIMIT = 300


@app.get("/relationship-candidates", response_class=HTMLResponse)
def relationship_candidates(request: Request) -> HTMLResponse:
    """Render claim pairs sharing PICO-resolved concepts, before classification.

    Mirrors `ke graph-relationship-candidates`. Structural overlap only:
    this page itself never infers, detects, or suggests a relationship
    type or rationale -- `core`'s automated classifier (`ke
    relationship-classify-automate`) runs over pairs like these by
    default, proposing a type only when its quoted evidence passes
    deterministic grounding verification; a reviewer can also author one
    by hand via the linked compare page.

    Bounded for a browser, unlike the CLI's file output: a single
    generic concept shared across hundreds of claims (e.g. "Patients")
    otherwise produces a combinatorial explosion of near-meaningless
    single-concept pairs -- confirmed against the real corpus at 163,946
    candidates and a 50+ MB page when every claim's concepts are
    included. Requiring at least 2 shared concepts (not core's
    single-concept default) cuts that noise by 97% and is also a more
    meaningful signal that two claims are worth classifying next.
    `_RELATIONSHIP_CANDIDATES_DISPLAY_LIMIT` caps the page itself, since
    even the 2-concept floor is not guaranteed to stay bounded as the
    corpus keeps growing across more domains.
    """

    all_candidates = list_relationship_candidates(
        _engine(), minimum_shared_concepts=_RELATIONSHIP_CANDIDATES_MINIMUM_SHARED_CONCEPTS
    )
    total_count = len(all_candidates)
    candidates = all_candidates[:_RELATIONSHIP_CANDIDATES_DISPLAY_LIMIT]
    return templates.TemplateResponse(
        request=request,
        name="relationship_candidates.html",
        context={
            "candidates": candidates,
            "total_count": total_count,
            "shown_count": len(candidates),
            "truncated": total_count > len(candidates),
            "minimum_shared_concepts": _RELATIONSHIP_CANDIDATES_MINIMUM_SHARED_CONCEPTS,
        },
    )


@app.get(
    "/relationship-candidates/{evidence_record_id_a}/{evidence_record_id_b}",
    response_class=HTMLResponse,
)
def relationship_candidate_compare(
    request: Request, evidence_record_id_a: str, evidence_record_id_b: str
) -> HTMLResponse:
    """Render two claims' full evidence content side by side, for one candidate pair.

    The same fields `ke relationship-review-worksheet` assembles into a
    Markdown document, rendered as a browsable page instead -- reviewing
    from the browser rather than a generated CLI document, the last
    named item from `docs/future_ideas.md`'s Reviewer Tooling section.
    This page itself never infers, scores, or suggests a relationship:
    deciding whether one exists is, by default, `core`'s automated
    classifier's job (`ke relationship-classify-automate`), which
    proposes a type only when its quoted evidence passes deterministic
    grounding verification. A reviewer can still author one by hand
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


def _render_bounded_relationship_candidates_report(
    engine: Engine, evidence_path: Path | None
) -> str:
    """Bounded the same way the `/relationship-candidates` HTML page is -- see its docstring."""

    all_candidates = list_relationship_candidates(
        engine, minimum_shared_concepts=_RELATIONSHIP_CANDIDATES_MINIMUM_SHARED_CONCEPTS
    )
    return render_relationship_candidates_report(
        all_candidates[:_RELATIONSHIP_CANDIDATES_DISPLAY_LIMIT],
        total_count=len(all_candidates),
    )


_REPORTS: dict[str, tuple[str, str, Callable[[Engine, Path | None], str]]] = {
    "graph": (
        "Graph Report",
        "The corpus-wide population counts -- the same report `ke graph-report` prints.",
        lambda engine, evidence_path: render_graph_summary_report(read_graph_summary(engine)),
    ),
    "relationship-candidates": (
        "Relationship Candidates Report",
        "Claim pairs sharing at least 2 PICO-resolved concepts with no relationship edge yet.",
        _render_bounded_relationship_candidates_report,
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

    `synthesize=1` is the one opt-in exception: when the complete local
    Research Copilot runtime is available, `knowledge-engine-ai` runs its
    durable retrieval, narration, verification, and close-gate workflow.
    This page still shows its own deterministic retrieval independently,
    including whenever the optional AI runtime is unavailable.
    """

    settings = Settings()
    ai_capability = evaluate_ai_capability(settings)
    synthesis_available = ai_capability.available
    question = q.strip()
    if not question:
        return templates.TemplateResponse(
            request=request,
            name="ask.html",
            context={
                "question": "",
                "results": None,
                "synthesis_available": synthesis_available,
                "synthesize_requested": False,
                "synthesis_unavailable_notice": None,
                "copilot_result": None,
                "copilot_error": None,
            },
        )

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

    synthesize_requested = synthesize and synthesis_available
    synthesis_unavailable_notice = (
        "Research Copilot is unavailable on this deployment. Retrieval results are shown below."
        if synthesize and not synthesis_available
        else None
    )
    copilot_result = None
    copilot_error: str | None = None
    if synthesize_requested:
        try:
            client_key = request.client.host if request.client is not None else "unknown"
            copilot_result = run_guarded_ai_orchestration(
                settings,
                question,
                client_key=client_key,
            )
            if result_reached_execution_limit(copilot_result):
                copilot_error = (
                    "Research Copilot reached its execution time limit. The durable session "
                    "records the incomplete workflow; deterministic retrieval results are "
                    "still shown below."
                )
        except AIAdmissionError as exc:
            copilot_error = exc.visitor_message
        except AIOrchestrationError as exc:
            copilot_error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="ask.html",
        context={
            "question": question,
            "results": results,
            "synthesis_available": synthesis_available,
            "synthesize_requested": synthesize_requested,
            "synthesis_unavailable_notice": synthesis_unavailable_notice,
            "copilot_result": copilot_result,
            "copilot_error": copilot_error,
        },
    )


@app.get("/discover", response_class=HTMLResponse)
def discover(request: Request, q: str = "") -> HTMLResponse:
    """Search live scholarly providers via `core`'s federated discovery run.

    Separate and opt-in from Ask's own retrieval, which only ever searches
    the already-imported local corpus. This page instead calls out to
    real provider HTTPS APIs (PubMed, Crossref, OpenAlex, Semantic Scholar)
    through `core`'s `ke federated-discover` command, and shows exactly what
    was searched, what succeeded, and what degraded or failed -- never
    inferring provider status from result count (WEB-FRD-1).
    """

    settings = Settings()
    capability = evaluate_discovery_capability(settings)
    query = q.strip()
    if not query:
        return templates.TemplateResponse(
            request=request,
            name="discover.html",
            context={
                "query": "",
                "discovery_available": capability.available,
                "result": None,
                "error": None,
            },
        )

    result = None
    error: str | None = None
    research_question_id = derive_research_question_id(query)
    if not capability.available:
        error = capability.visitor_message
    else:
        try:
            client_key = request.client.host if request.client is not None else "unknown"
            result = run_guarded_discovery(
                settings,
                query,
                client_key=client_key,
                research_question_id=research_question_id,
            )
        except AIAdmissionError as exc:
            error = exc.visitor_message
        except DiscoveryOrchestrationError as exc:
            error = str(exc)

    presentation = build_discovery_presentation(result) if result is not None else None

    # WEB-FRD-5 (research freshness history): a history-lookup failure must
    # never take down an otherwise-successful discovery result. This is a
    # strictly additive, best-effort read layered on top of the result
    # above, not a required part of rendering it.
    freshness = None
    if result is not None:
        try:
            history = run_discovery_history(settings, research_question_id)
            freshness = build_discovery_freshness(result, history)
        except DiscoveryOrchestrationError:
            freshness = None

        # Candidate-level slice (WEB-FRD-5 item 7): only attempted once a
        # prior run for this tracked question is actually known to exist.
        # Equally best-effort -- a failed or empty snapshot leaves
        # `freshness` at its run-level-only state rather than failing the
        # page, matching the run-level lookup's own degrade-gracefully
        # contract above.
        if (
            freshness is not None
            and not freshness.is_first_recorded_search
            and freshness.previous_search_run_id is not None
            and presentation is not None
        ):
            try:
                previous_snapshot = run_discovery_candidate_snapshot(
                    settings, freshness.previous_search_run_id
                )
            except DiscoveryOrchestrationError:
                previous_snapshot = None
            if previous_snapshot is not None:
                candidate_level = build_candidate_freshness(
                    presentation.candidates, previous_snapshot.candidates
                )
                freshness = dataclasses.replace(
                    freshness,
                    per_candidate_history_available=True,
                    candidate_level=candidate_level,
                )

    return templates.TemplateResponse(
        request=request,
        name="discover.html",
        context={
            "query": query,
            "discovery_available": capability.available,
            "result": result,
            "provider_rows": [_provider_status_view(status) for status in result.provider_statuses]
            if result is not None
            else None,
            "candidate_cards": presentation.candidates if presentation is not None else None,
            "disagreement_data_available": presentation.disagreement_data_available
            if presentation is not None
            else False,
            "freshness": freshness,
            "error": error,
        },
    )


_PROVIDER_OUTCOME_LABELS: dict[str, tuple[str, str]] = {
    "success": ("searched", "is-ok"),
    "empty": ("searched, no matches", "is-ok"),
    "rate_limited": ("rate limited", "is-degraded"),
    "unavailable": ("unavailable", "is-degraded"),
    "failed": ("failed", "is-degraded"),
    "skipped": ("not searched", "is-skipped"),
    "disabled": ("disabled", "is-skipped"),
}


def _provider_status_view(status: FederatedProviderStatus) -> dict[str, object]:
    """Map one raw `FederatedProviderStatus` onto a fixed, deterministic label.

    Never infers status from `result_count` (WEB-FRD-1) -- the label comes
    only from Core's own recorded `outcome`, including the `success` case
    with zero results ("searched, no matches" is not the same claim as
    "unavailable").
    """

    label, css_class = _PROVIDER_OUTCOME_LABELS.get(
        status.outcome, (status.outcome or "unknown", "is-skipped")
    )
    return {
        "provider": status.provider,
        "label": label,
        "css_class": css_class,
        "reason": status.reason,
        "result_count": status.result_count,
    }


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
