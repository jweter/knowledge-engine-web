"""Tests for report_renderer's Markdown generation, especially its escaping.

Mirrors core's own hardening (`_graph_report_text`, hardened against a
real Codex-caught injection finding on `relationship-report`) -- a
concept label or evidence record ID must never be able to forge a
report heading or alter formatting in a downloaded `.md` file.
"""

from __future__ import annotations

from knowledge_engine_web.graph_reader import (
    ClaimListItem,
    GraphSummary,
    RelationshipCandidate,
)
from knowledge_engine_web.report_renderer import (
    render_graph_summary_report,
    render_relationship_candidates_report,
    render_unconfirmed_claims_report,
)


def test_graph_summary_report_has_the_expected_shape() -> None:
    summary = GraphSummary(
        concepts_total=2,
        concepts_by_source={"rxnorm": 1, "mesh": 1},
        claims_total=3,
        claim_concept_edges_total=4,
        relationship_edges_total=0,
        citation_edges_total=1,
    )

    report = render_graph_summary_report(summary)

    assert report.startswith("# Knowledge Engine Graph Report")
    assert "- Concepts: 2 (mesh: 1, rxnorm: 1)" in report
    assert "- Claims: 3" in report
    assert "## Scope" in report


def test_graph_summary_report_escapes_a_markdown_special_character_in_source() -> None:
    summary = GraphSummary(
        concepts_total=1,
        concepts_by_source={"*evil*": 1},
        claims_total=0,
        claim_concept_edges_total=0,
        relationship_edges_total=0,
        citation_edges_total=0,
    )

    report = render_graph_summary_report(summary)

    assert "\\*evil\\*" in report
    assert "*evil*: 1" not in report


def test_relationship_candidates_report_escapes_a_forged_heading() -> None:
    candidate = RelationshipCandidate(
        claim_a_evidence_record_id="ev-a",
        claim_b_evidence_record_id="ev-b\n# Forged Heading",
        shared_concept_labels=["[link](javascript:alert(1))"],
    )

    report = render_relationship_candidates_report([candidate])

    assert "ev-b # Forged Heading" in report
    assert "\n# Forged Heading" not in report
    assert "\\[link\\]" in report


def test_unconfirmed_claims_report_escapes_backticks_in_evidence_record_id() -> None:
    claim = ClaimListItem(
        id=1, evidence_record_id="ev-`injected`", created_at="2026-01-01T00:00:00Z"
    )

    report = render_unconfirmed_claims_report([claim])

    assert "ev-\\`injected\\`" in report


def test_unconfirmed_claims_report_renders_empty_state() -> None:
    report = render_unconfirmed_claims_report([])

    assert "Every claim in the graph has at least one relationship edge." in report


def test_relationship_candidates_report_renders_empty_state() -> None:
    report = render_relationship_candidates_report([])

    assert "No claim pairs share a concept without an existing relationship yet." in report


def test_relationship_candidates_report_notes_truncation_when_total_exceeds_shown() -> None:
    candidate = RelationshipCandidate(
        claim_a_evidence_record_id="ev-a",
        claim_b_evidence_record_id="ev-b",
        shared_concept_labels=["Semaglutide"],
    )

    report = render_relationship_candidates_report([candidate], total_count=163946)

    assert "Candidate pairs found: 163946" in report
    assert "Showing the top 1, ranked by number of shared concepts." in report
