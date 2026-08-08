from knowledge_engine_web.graph_reader import RelationshipListItem
from knowledge_engine_web.graph_visual import (
    build_relationship_network_svg,
    relationship_type_legend,
)


def _relationship(
    relationship_id: str,
    relationship_type: str,
    source: str,
    target: str,
) -> RelationshipListItem:
    return RelationshipListItem(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        source_evidence_record_id=source,
        target_evidence_record_id=target,
        created_at="2026-01-01T00:00:00Z",
    )


def test_build_relationship_network_svg_returns_none_for_no_relationships() -> None:
    assert build_relationship_network_svg([], {}) is None


def test_build_relationship_network_svg_draws_one_node_per_distinct_claim() -> None:
    relationships = [
        _relationship("rel-1", "supports", "ev-a", "ev-b"),
        _relationship("rel-2", "qualifies", "ev-b", "ev-c"),
    ]

    svg = build_relationship_network_svg(relationships, {})

    assert svg is not None
    assert svg.startswith("<svg")
    assert svg.count("<circle") == 3
    assert svg.count("<line") == 2


def test_build_relationship_network_svg_uses_titles_when_available() -> None:
    relationships = [_relationship("rel-1", "supports", "ev-a", "ev-b")]
    titles = {"ev-a": "A Randomized Trial of Something", "ev-b": "A Cohort Study"}

    svg = build_relationship_network_svg(relationships, titles)

    assert svg is not None
    assert "A Randomized Trial of Something" in svg
    assert "A Cohort Study" in svg


def test_build_relationship_network_svg_falls_back_to_evidence_record_id_without_a_title() -> None:
    relationships = [_relationship("rel-1", "supports", "ev-a", "ev-b")]

    svg = build_relationship_network_svg(relationships, {})

    assert svg is not None
    assert "ev-a" in svg
    assert "ev-b" in svg


def test_build_relationship_network_svg_is_deterministic() -> None:
    relationships = [
        _relationship("rel-1", "supports", "ev-a", "ev-b"),
        _relationship("rel-2", "qualifies", "ev-b", "ev-c"),
        _relationship("rel-3", "contextualizes", "ev-a", "ev-c"),
    ]

    first = build_relationship_network_svg(relationships, {})
    second = build_relationship_network_svg(relationships, {})

    assert first == second


def test_build_relationship_network_svg_escapes_a_malicious_title() -> None:
    relationships = [_relationship("rel-1", "supports", "ev-a", "ev-b")]
    titles = {"ev-a": "<script>alert(1)</script>", "ev-b": "Safe title"}

    svg = build_relationship_network_svg(relationships, titles)

    assert svg is not None
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_build_relationship_network_svg_truncates_long_titles_but_keeps_full_text() -> None:
    long_title = "A " + "very " * 20 + "long title"
    relationships = [_relationship("rel-1", "supports", "ev-a", "ev-b")]

    svg = build_relationship_network_svg(relationships, {"ev-a": long_title})

    assert svg is not None
    assert long_title in svg  # full text survives in the <title> tooltip
    assert "…" in svg  # visible <text> label is truncated


def test_relationship_type_legend_returns_distinct_sorted_types_with_colors() -> None:
    relationships = [
        _relationship("rel-1", "supports", "ev-a", "ev-b"),
        _relationship("rel-2", "qualifies", "ev-b", "ev-c"),
        _relationship("rel-3", "supports", "ev-c", "ev-a"),
    ]

    legend = relationship_type_legend(relationships)

    assert legend == [
        ("qualifies", "#d69e2e"),
        ("supports", "#2f9e6f"),
    ]


def test_relationship_type_legend_returns_empty_list_for_no_relationships() -> None:
    assert relationship_type_legend([]) == []


def test_relationship_type_legend_falls_back_to_default_color_for_unknown_type() -> None:
    relationships = [_relationship("rel-1", "supersedes", "ev-a", "ev-b")]

    legend = relationship_type_legend(relationships)

    assert legend == [("supersedes", "#9b6bd1")]
