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
