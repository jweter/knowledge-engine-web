"""Markdown/JSON export of one `/discover` federated discovery run.

Closes the roadmap item `docs/federated_discovery_transparency_roadmap.md`
records under "Improvements beyond the external reference": "Coverage
limitations should travel with exports" -- downloaded reports must carry the
same provider/search coverage limitations the `/discover` page already shows,
and exporting a run must not strip away the fact that the underlying search
was degraded.

Both `render_discovery_export_markdown` and `build_discovery_export_json`
are built from one shared `DiscoveryExportView`, itself built directly from
the exact same `FederatedDiscoveryResult` (`knowledge_engine_ai.ke_client`)
and `DiscoveryPresentation` (`discovery_presentation.py`) the `/discover`
route already computes and renders in `discover.html`. This module never
recomputes, infers, merges, or fabricates a fact Core/AI did not already
report -- it only reshapes already-computed data into two downloadable
shapes, using `discovery_presentation.provider_outcome_label` for the same
provider-status vocabulary `main.py`'s HTML rendering uses, so the two
surfaces cannot silently drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from knowledge_engine_web.discovery_presentation import (
    DiscoveryCandidateView,
    DiscoveryPresentation,
    provider_outcome_label,
)


class ProviderStatusSource(Protocol):
    """Duck-typed provider coverage fact, matching `ke_client.FederatedProviderStatus`.

    A `Protocol` rather than the concrete `knowledge_engine_ai` dataclass --
    same convention `discovery_freshness.py` already uses -- so tests can
    build lightweight fixtures without depending on that package's exact
    type.
    """

    @property
    def provider(self) -> str: ...
    @property
    def outcome(self) -> str: ...
    @property
    def attempted(self) -> bool: ...
    @property
    def result_count(self) -> int: ...
    @property
    def reason(self) -> str | None: ...


class DiscoveryResultSource(Protocol):
    """Duck-typed discovery run, matching `ke_client.FederatedDiscoveryResult`."""

    @property
    def search_run_id(self) -> str: ...
    @property
    def completeness(self) -> str: ...
    @property
    def search_run_created_at(self) -> str | None: ...
    @property
    def provider_statuses(self) -> tuple[ProviderStatusSource, ...]: ...


_MARKDOWN_SPECIAL_CHARS = re.compile(r"([\\`*_\[\]<~|])")

_COMPLETENESS_LABELS: dict[str, str] = {
    "complete": "complete",
    "partial": "degraded / partial",
}


def _export_text(value: object) -> str:
    """Collapse whitespace and escape Markdown-structural characters (mirrors `report_renderer`).

    A candidate title, provider reason string, or disagreement value could
    otherwise forge a heading, break a table row, or alter formatting in a
    downloaded report opened elsewhere -- the same concern `report_renderer.
    _report_text`'s docstring names for the existing graph-report exports.
    ``|`` is additionally escaped here because this module's Markdown uses
    pipe-delimited tables, which `report_renderer`'s reports do not.
    """

    collapsed = " ".join(str(value).split())
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", collapsed)


def _generated_at() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ProviderCoverageExportView:
    """One provider's coverage row, in the export's own stable shape."""

    provider: str
    outcome: str
    label: str
    attempted: bool
    result_count: int
    reason: str | None


@dataclass(frozen=True)
class DiscoveryExportView:
    """Everything both export formats render, built once and shared by both.

    Deliberately holds the same facts `discover.html`'s "Discovery coverage"
    section and candidate cards show on screen: overall run completeness,
    per-provider coverage (including the reason a provider degraded or was
    skipped), whether provider-disagreement data is available for this run,
    and each candidate's publication-status/disagreement state.
    """

    generated_at: str
    query: str
    search_run_id: str
    search_run_created_at: str | None
    completeness: str
    provider_coverage: tuple[ProviderCoverageExportView, ...]
    disagreement_data_available: bool
    candidates: tuple[DiscoveryCandidateView, ...]


def build_discovery_export_view(
    query: str,
    result: DiscoveryResultSource,
    presentation: DiscoveryPresentation,
) -> DiscoveryExportView:
    """Build one export view from the same result/presentation `/discover` already rendered."""

    provider_coverage = tuple(
        ProviderCoverageExportView(
            provider=status.provider,
            outcome=status.outcome,
            label=provider_outcome_label(status.outcome),
            attempted=status.attempted,
            result_count=status.result_count,
            reason=status.reason,
        )
        for status in result.provider_statuses
    )
    return DiscoveryExportView(
        generated_at=_generated_at(),
        query=query,
        search_run_id=result.search_run_id,
        search_run_created_at=result.search_run_created_at,
        completeness=result.completeness,
        provider_coverage=provider_coverage,
        disagreement_data_available=presentation.disagreement_data_available,
        candidates=presentation.candidates,
    )


def render_discovery_export_markdown(view: DiscoveryExportView) -> str:
    """Render one discovery run's coverage and candidates as a downloadable `.md` file."""

    lines = [
        "# Knowledge Engine Discovery Export",
        "",
        f"Generated: {view.generated_at}",
        f"Query: {_export_text(view.query)}",
        f"Search run ID: `{view.search_run_id}`",
    ]
    if view.search_run_created_at:
        lines.append(f"Search run timestamp: `{view.search_run_created_at}`")
    else:
        lines.append(
            "Search run timestamp: not recorded for this search run (an "
            "older cached result, or a snapshot from before Core began "
            "recording this timestamp)."
        )
    lines.extend(
        [
            "",
            f"Overall run: {_COMPLETENESS_LABELS.get(view.completeness, 'failed')}",
            "",
        ]
    )
    if view.completeness != "complete":
        lines.extend(
            [
                "This is a degraded search run. One or more providers did not "
                "complete, so absence of a candidate below does not mean the "
                "literature does not contain it.",
                "",
            ]
        )

    lines.extend(
        [
            "## Provider coverage",
            "",
            "| Provider | Status | Results | Reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    for provider in view.provider_coverage:
        reason = _export_text(provider.reason) if provider.reason else "--"
        lines.append(
            f"| {_export_text(provider.provider)} | {_export_text(provider.label)} "
            f"| {provider.result_count} | {reason} |"
        )
    lines.append("")

    if not view.disagreement_data_available:
        lines.extend(
            [
                "This search run predates provider-disagreement reporting, so "
                "per-candidate metadata-agreement status below is not "
                "available for it.",
                "",
            ]
        )

    lines.extend([f"## Candidates ({len(view.candidates)})", ""])
    if not view.candidates:
        lines.extend(["No candidates found by any searched provider.", ""])
    for candidate in view.candidates:
        lines.extend(_render_candidate_markdown(candidate))

    lines.extend(
        [
            "## Scope",
            "",
            "Provider availability, result count, or provider rank does not "
            "make a scientific claim stronger or weaker; these are search- "
            "provenance facts, not evidence-quality scores. This export "
            "carries the same coverage and provider-limitation facts the "
            "`/discover` page showed for this search run -- nothing here is "
            "inferred beyond what Core/AI already reported.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_candidate_markdown(candidate: DiscoveryCandidateView) -> list[str]:
    status = candidate.publication_status
    lines = [f"### {_export_text(candidate.title)}", ""]

    meta_bits = []
    if candidate.doi:
        meta_bits.append(f"DOI: {_export_text(candidate.doi)}")
    if candidate.publication_year is not None:
        meta_bits.append(str(candidate.publication_year))
    if candidate.providers:
        meta_bits.append(f"observed by {_export_text(', '.join(candidate.providers))}")
    if meta_bits:
        lines.append(" &middot; ".join(meta_bits))
        lines.append("")

    preprint_version = f" (v{status.preprint_versions[0]})" if status.preprint_versions else ""
    lines.extend(
        [
            f"- Retraction status: {status.retraction_state}",
            f"- Preprint status: {status.preprint_state}{preprint_version}",
            f"- Correction status: {status.correction_state}",
            f"- Expression-of-concern status: {status.expression_of_concern_state}",
            f"- Withdrawal status: {status.withdrawal_state}",
            f"- Provider metadata disagreement: {candidate.disagreement_state}",
            "",
        ]
    )
    return lines


def build_discovery_export_json(view: DiscoveryExportView) -> dict[str, Any]:
    """Build the same facts as `render_discovery_export_markdown`, as a JSON-serializable dict."""

    return {
        "generated_at": view.generated_at,
        "query": view.query,
        "search_run_id": view.search_run_id,
        "search_run_created_at": view.search_run_created_at,
        "completeness": view.completeness,
        "provider_coverage": [
            {
                "provider": provider.provider,
                "outcome": provider.outcome,
                "label": provider.label,
                "attempted": provider.attempted,
                "result_count": provider.result_count,
                "reason": provider.reason,
            }
            for provider in view.provider_coverage
        ],
        "disagreement_data_available": view.disagreement_data_available,
        "candidates": [_candidate_to_json(candidate) for candidate in view.candidates],
    }


def _candidate_to_json(candidate: DiscoveryCandidateView) -> dict[str, Any]:
    status = candidate.publication_status
    return {
        "canonical_id": candidate.canonical_id,
        "title": candidate.title,
        "doi": candidate.doi,
        "publication_year": candidate.publication_year,
        "providers": list(candidate.providers),
        "disagreement_state": candidate.disagreement_state,
        "disagreements": [
            {
                "field": disagreement.field,
                "assertions": [
                    {
                        "provider": assertion.provider,
                        "provider_id": assertion.provider_id,
                        "value": assertion.value,
                    }
                    for assertion in disagreement.assertions
                ],
            }
            for disagreement in candidate.disagreements
        ],
        "publication_status": {
            "retraction_state": status.retraction_state,
            "preprint_state": status.preprint_state,
            "correction_state": status.correction_state,
            "expression_of_concern_state": status.expression_of_concern_state,
            "withdrawal_state": status.withdrawal_state,
            "preprint_versions": list(status.preprint_versions),
            "observations": [
                {
                    "provider": observation.provider,
                    "retracted": observation.retracted,
                    "preprint": observation.preprint,
                    "preprint_version": observation.preprint_version,
                    "corrected": observation.corrected,
                    "expression_of_concern": observation.expression_of_concern,
                    "withdrawn": observation.withdrawn,
                }
                for observation in status.observations
            ],
        },
    }


__all__ = [
    "DiscoveryExportView",
    "ProviderCoverageExportView",
    "build_discovery_export_json",
    "build_discovery_export_view",
    "render_discovery_export_markdown",
]
