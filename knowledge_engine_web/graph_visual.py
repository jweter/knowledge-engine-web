"""Deterministic SVG rendering of the reviewed relationship network.

Turns `graph_reader.list_relationships` output into a self-contained inline
SVG: a circular layout of claim nodes connected by relationship-typed edges.
No JavaScript, no external assets, no randomness -- the same edges always
produce the same picture, so this stays trivially testable. Node size reflects
edge count (degree) purely as a display cue; it is not a recomputed score and
feeds no confidence number.
"""

from __future__ import annotations

import math
from collections import Counter
from xml.sax.saxutils import escape, quoteattr

from knowledge_engine_web.graph_reader import RelationshipListItem

RELATIONSHIP_TYPE_COLORS: dict[str, str] = {
    "supports": "#2f9e6f",
    "qualifies": "#d69e2e",
    "contextualizes": "#3b82c4",
    "contradicts": "#e0575a",
    "supersedes": "#9b6bd1",
}
_DEFAULT_EDGE_COLOR = "#8a97a1"
_LABEL_MAX_CHARS = 22


def _truncate(label: str, *, max_chars: int = _LABEL_MAX_CHARS) -> str:
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1] + "…"


def _text_anchor(cos_angle: float) -> str:
    if cos_angle > 0.3:
        return "start"
    if cos_angle < -0.3:
        return "end"
    return "middle"


def _label_dy(sin_angle: float) -> str:
    if sin_angle < -0.6:
        return "-6"
    if sin_angle > 0.6:
        return "13"
    return "4"


def build_relationship_network_svg(
    relationships: list[RelationshipListItem],
    titles: dict[str, str],
    *,
    width: int = 760,
    height: int = 760,
) -> str | None:
    """Return a self-contained `<svg>` string, or `None` if there is nothing to draw.

    `titles` maps `evidence_record_id` to a human-readable label (typically
    the source paper's title). A node with no entry falls back to its own
    `evidence_record_id`. Node labels are truncated for legibility; the full
    label and degree remain available via `<title>` tooltip text.
    """

    if not relationships:
        return None

    node_ids = sorted(
        {relationship.source_evidence_record_id for relationship in relationships}
        | {relationship.target_evidence_record_id for relationship in relationships}
    )
    degree: Counter[str] = Counter()
    for relationship in relationships:
        degree[relationship.source_evidence_record_id] += 1
        degree[relationship.target_evidence_record_id] += 1

    center_x = width / 2
    center_y = height / 2
    radius = min(width, height) / 2 - 150
    node_count = len(node_ids)

    positions: dict[str, tuple[float, float, float, float]] = {}
    for index, node_id in enumerate(node_ids):
        angle = 2 * math.pi * index / node_count - math.pi / 2
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        positions[node_id] = (x, y, math.cos(angle), math.sin(angle))

    aria_label = quoteattr(
        f"Reviewed relationship network: {node_count} claims, {len(relationships)} relationships"
    )
    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label={aria_label} xmlns="http://www.w3.org/2000/svg">',
        "<style>"
        "text { font: 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
        "fill: var(--text); }"
        "circle.graph-node { fill: var(--bg-alt); stroke: var(--accent); stroke-width: 2; }"
        "</style>",
    ]

    for relationship in relationships:
        x1, y1, _, _ = positions[relationship.source_evidence_record_id]
        x2, y2, _, _ = positions[relationship.target_evidence_record_id]
        color = RELATIONSHIP_TYPE_COLORS.get(relationship.relationship_type, _DEFAULT_EDGE_COLOR)
        tooltip = escape(
            f"{relationship.relationship_type}: "
            f"{relationship.source_evidence_record_id} -> {relationship.target_evidence_record_id}"
        )
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="1.75" stroke-opacity="0.75">'
            f"<title>{tooltip}</title></line>"
        )

    for node_id in node_ids:
        x, y, cos_angle, sin_angle = positions[node_id]
        node_radius = 7 + min(degree[node_id], 6) * 1.6
        full_label = titles.get(node_id, node_id)
        tooltip = escape(
            f"{full_label} ({node_id}) -- "
            f"{degree[node_id]} relationship{'s' if degree[node_id] != 1 else ''}"
        )
        parts.append(
            f'<circle class="graph-node" cx="{x:.1f}" cy="{y:.1f}" r="{node_radius:.1f}">'
            f"<title>{tooltip}</title></circle>"
        )
        label_radius = radius + node_radius + 10
        lx = center_x + label_radius * cos_angle
        ly = center_y + label_radius * sin_angle
        anchor = _text_anchor(cos_angle)
        dy = _label_dy(sin_angle)
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" dy="{dy}">'
            f"{escape(_truncate(full_label))}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def relationship_type_legend(relationships: list[RelationshipListItem]) -> list[tuple[str, str]]:
    """Return the distinct `(relationship_type, color)` pairs actually present, sorted by type."""

    types = sorted({relationship.relationship_type for relationship in relationships})
    return [
        (rel_type, RELATIONSHIP_TYPE_COLORS.get(rel_type, _DEFAULT_EDGE_COLOR))
        for rel_type in types
    ]
