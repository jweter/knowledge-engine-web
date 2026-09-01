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


def test_layer2_renderer_exposes_structured_evidence_and_methodology_without_reinterpreting_it() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    for field in (
        "supporting_evidence_ids",
        "contradicting_or_null_evidence_ids",
        "directness",
        "direct_evidence_summary",
        "indirect_evidence_summary",
        "indexed_before_run_evidence_ids",
        "acquired_during_run_evidence_ids",
        "provider_coverage_completeness",
        "degraded_providers",
        "provider_statuses",
        "missing_evidence",
        "limitations",
        "session_id",
        "research_state",
    ):
        assert field in script

    for label in (
        "Evidence and methodology",
        "Supporting evidence IDs",
        "Null / contradictory evidence IDs",
        "Evidence provenance",
        "Provider coverage and degradation",
        "Limitations and missing evidence",
        "Research session identity",
    ):
        assert label in script

    assert 'details.id = "research-report-layer2"' in script
    assert "renderLayer2(block, report)" in script
    assert "innerHTML" not in script


def test_layer2_provider_rows_use_only_contract_fields() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    for field in ("provider", "attempted", "outcome", "reason"):
        assert f"status.{field}" in script

    assert "JSON.stringify(status" not in script


def test_layer1_renderer_preserves_verified_base_result_when_report_is_unavailable() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    assert "The verified base answer remains available" in script
    assert "researchReport.available" in script
    assert "researchReport.report" in script


def test_completed_report_hides_stale_pipeline_metadata_before_answer() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    assert "hideCompletedPipelineMetadata(resultNode)" in script
    assert "previousElementSibling" in script
    assert "sibling.hidden = true" in script


def test_layer1_hydration_retries_transient_or_stale_fetches() -> None:
    script = LAYER1_SCRIPT.read_text(encoding="utf-8")

    assert "MAX_HYDRATE_ATTEMPTS" in script
    assert "shouldRetry = true" in script
    assert "window.setTimeout" in script
    assert "attempt + 1" in script
