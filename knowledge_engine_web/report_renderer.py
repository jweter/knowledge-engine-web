"""Markdown report rendering, mirroring `core`'s `ke graph-report` family exactly.

`core`'s CLI (`ke graph-report`, `ke graph-relationship-candidates`, `ke
graph-unconfirmed-claims`) already builds these reports as Markdown text
over the same graph data this project reads. This module rebuilds that
same Markdown shape independently, using `graph_reader`'s own already-
fetched data -- never by importing `knowledge_engine` (see
`docs/web_design.md`'s Decision section) and never by shelling out to
`ke`, which the alpha deployment doesn't have available anyway.

Reports are offered both as a rendered page and as a downloadable `.md`
file, so the same Markdown-structural-character escaping `core`'s own
`_graph_report_text` applies (hardened against a real Codex-caught
injection finding on the original `relationship-report`) is reproduced
here -- a concept label or evidence record ID could otherwise forge a
heading or alter formatting in a downloaded report opened elsewhere.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from knowledge_engine_web.graph_reader import (
    ClaimListItem,
    GraphSummary,
    RelationshipCandidate,
)
from knowledge_engine_web.whats_changed import WhatsChangedSummary

_MARKDOWN_SPECIAL_CHARS = re.compile(r"([\\`*_\[\]<~])")


def _report_text(value: object) -> str:
    """Collapse whitespace and escape Markdown-structural characters in a data value."""

    collapsed = " ".join(str(value).split())
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", collapsed)


def _generated_at() -> str:
    return datetime.now(UTC).isoformat()


def render_graph_summary_report(summary: GraphSummary) -> str:
    """Build the same report `ke graph-report`'s no-filter mode prints."""

    by_source = (
        ", ".join(
            f"{_report_text(source)}: {count}"
            for source, count in sorted(summary.concepts_by_source.items())
        )
        or "none"
    )
    return "\n".join(
        [
            "# Knowledge Engine Graph Report",
            "",
            f"Generated: {_generated_at()}",
            "",
            "## Corpus Totals",
            "",
            f"- Concepts: {summary.concepts_total} ({by_source})",
            f"- Claims: {summary.claims_total}",
            f"- Claim-concept edges: {summary.claim_concept_edges_total}",
            f"- Relationship edges: {summary.relationship_edges_total}",
            f"- Citation edges: {summary.citation_edges_total}",
            "",
            "## Scope",
            "",
            "This report displays the graph's current, actual row counts "
            "only -- nothing here is inferred or synthesized.",
            "",
        ]
    )


def render_relationship_candidates_report(candidates: list[RelationshipCandidate]) -> str:
    """Build the same report `ke graph-relationship-candidates` prints."""

    lines = [
        "# Knowledge Engine Graph Relationship Candidates",
        "",
        f"Generated: {_generated_at()}",
        "",
        f"Candidate pairs found: {len(candidates)}",
        "",
    ]
    if not candidates:
        lines.extend(["No claim pairs share a concept without an existing relationship yet.", ""])
    for candidate in candidates:
        concept_labels = ", ".join(_report_text(label) for label in candidate.shared_concept_labels)
        lines.extend(
            [
                f"## {_report_text(candidate.claim_a_evidence_record_id)} <-> "
                f"{_report_text(candidate.claim_b_evidence_record_id)}",
                "",
                f"- Shared concepts ({len(candidate.shared_concept_labels)}): {concept_labels}",
                "",
            ]
        )

    lines.extend(
        [
            "## Scope",
            "",
            "This report surfaces structural overlap only -- which claims "
            "share a PICO-resolved concept. It never infers, detects, or "
            "suggests a relationship type or rationale; that remains a "
            "human judgment call.",
            "",
        ]
    )
    return "\n".join(lines)


def render_unconfirmed_claims_report(claims: list[ClaimListItem]) -> str:
    """Build the same report `ke graph-unconfirmed-claims` prints."""

    lines = [
        "# Knowledge Engine Graph Unconfirmed Claims",
        "",
        f"Generated: {_generated_at()}",
        "",
        f"Unconfirmed claims found: {len(claims)}",
        "",
    ]
    if not claims:
        lines.extend(["Every claim in the graph has at least one relationship edge.", ""])
    for claim in claims:
        lines.extend(
            [
                f"## {_report_text(claim.evidence_record_id)}",
                "",
                f"- Graph claim ID: {claim.id}",
                f"- Created: {_report_text(claim.created_at)}",
                "",
            ]
        )

    lines.extend(
        [
            "## Scope",
            "",
            "A claim listed here has no `supports`/`contradicts`/`qualifies`/"
            "`contextualizes`/`supersedes` edge yet -- meaning no second "
            "claim has been reviewed and explicitly related to it, nothing "
            "more. This is a fact about review coverage, not a judgment "
            "about the underlying science.",
            "",
        ]
    )
    return "\n".join(lines)


def _quality_delta_line(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "not yet assessable"
    return f"{before:.1f}/100 -> {after:.1f}/100 ({after - before:+.1f})"


def render_whats_changed_report(summary: WhatsChangedSummary) -> str:
    """Build the "what changed" report: new activity and aggregate deltas over one window.

    `docs/roadmap.md`'s "Planned: Reviewer & Evidence Intelligence
    Tooling" third item. "Before" is reconstructed from `created_at`
    timestamps already stored on graph rows, not a stored historical
    snapshot -- see `whats_changed.py`'s own module docstring.
    """

    lines = [
        "# Knowledge Engine What Changed Report",
        "",
        f"Generated: {summary.generated_at}",
        f"Window: last {summary.window_days} day(s), since {summary.since}",
        "",
        "## New Claims",
        "",
        f"New claims: {len(summary.new_claims)}",
        "",
    ]
    if not summary.new_claims:
        lines.extend(["No new claims in this window.", ""])
    for claim in summary.new_claims:
        lines.append(
            f"- {_report_text(claim.evidence_record_id)} ({_report_text(claim.created_at)})"
        )
    if summary.new_claims:
        lines.append("")

    lines.extend(
        [
            "## New Relationship Edges",
            "",
            f"New relationship edges: {len(summary.new_relationships)}",
            "",
        ]
    )
    if not summary.new_relationships:
        lines.extend(["No new relationship edges in this window.", ""])
    for edge in summary.new_relationships:
        lines.append(
            f"- {_report_text(edge.source_evidence_record_id)} "
            f"**{_report_text(edge.relationship_type)}** "
            f"{_report_text(edge.target_evidence_record_id)} ({_report_text(edge.created_at)})"
        )
    if summary.new_relationships:
        lines.append("")

    lines.extend(
        [
            "## Aggregate Deltas",
            "",
            f"- Claims in the graph: {summary.claims_total_before} -> {summary.claims_total_after}",
        ]
    )
    if summary.evidence_configured:
        lines.extend(
            [
                f"- Mean Evidence Quality: "
                f"{_quality_delta_line(summary.mean_quality_before, summary.mean_quality_after)}",
                f"- Evidence Coverage: {summary.coverage_before.percentage}% -> "
                f"{summary.coverage_after.percentage}% "
                f"({summary.coverage_before.records_in_relationship} of "
                f"{summary.coverage_before.total_records} -> "
                f"{summary.coverage_after.records_in_relationship} of "
                f"{summary.coverage_after.total_records})",
            ]
        )
    else:
        lines.append(
            "- Mean Evidence Quality / Evidence Coverage: not shown -- "
            "`KE_WEB_EVIDENCE_RECORDS_PATH` is not configured on this deployment."
        )
    lines.extend(
        [
            "",
            "## Scope",
            "",
            '"Before" is reconstructed from each graph row\'s own `created_at` '
            "timestamp as of the window's start, not a stored historical "
            "snapshot -- this project has no persistent host to keep one on "
            "(see `docs/service_boundary_design.md`). Both ends are real, "
            "already-stored values; nothing here is estimated.",
            "",
        ]
    )
    return "\n".join(lines)
