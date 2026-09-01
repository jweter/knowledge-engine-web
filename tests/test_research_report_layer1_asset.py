from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "knowledge_engine_web" / "templates" / "base.html"
LAYER1_SCRIPT = ROOT / "knowledge_engine_web" / "static" / "research_report_layer1.js"


def test_base_template_loads_research_report_layer1_renderer() -> None:
    base = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert '<script src="/static/research_report_layer1.js" defer></script>' in base


def test_layer1_renderer_consumes_structured_report_fields_without_html_injection() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    for field in (
        "research_report",
        "bottom_line",
        "conclusion_rows",
        "certainty",
        "certainty_rationale",
        "missing_direct_evidence",
    ):
        assert field in script

    assert "innerHTML" not in script
    assert ".narrative" not in script
    assert "textContent" in script


def test_layer1_renderer_preserves_verified_base_result_when_report_is_unavailable() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    assert "The verified base answer remains available" in script
    assert "researchReport.available" in script
    assert "researchReport.report" in script
