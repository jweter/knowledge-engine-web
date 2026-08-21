"""Unit tests for `discovery_export.py`.

Covers the roadmap item `docs/federated_discovery_transparency_roadmap.md`
records under "Improvements beyond the external reference": "Coverage
limitations should travel with exports" -- both the Markdown and JSON export
must carry the same provider/search coverage limitations (degraded run
state, per-provider reason, retraction/preprint/correction status, provider
metadata disagreement) that `discover.html` already shows on screen for the
same result.
"""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine_web.discovery_export import (
    DiscoveryExportView,
    build_discovery_export_json,
    build_discovery_export_view,
    render_discovery_export_markdown,
)
from knowledge_engine_web.discovery_presentation import build_discovery_presentation


@dataclass(frozen=True)
class _ProviderStatus:
    provider: str
    outcome: str
    attempted: bool
    result_count: int
    reason: str | None


@dataclass(frozen=True)
class _Assertion:
    provider: str
    provider_id: str
    value: str | int | bool


@dataclass(frozen=True)
class _Disagreement:
    field: str
    assertions: tuple[_Assertion, ...]


@dataclass(frozen=True)
class _CandidateDisagreements:
    canonical_id: str
    disagreements: tuple[_Disagreement, ...]


@dataclass(frozen=True)
class _ObservationFlags:
    provider: str
    retracted: bool | None
    preprint: bool | None
    preprint_version: int | None
    corrected: bool | None = None
    expression_of_concern: bool | None = None
    withdrawn: bool | None = None


@dataclass(frozen=True)
class _Candidate:
    canonical_id: str
    title: str
    doi: str | None
    publication_year: int | None
    providers: tuple[str, ...]
    observation_flags: tuple[_ObservationFlags, ...] = ()


@dataclass(frozen=True)
class _Result:
    search_run_id: str
    query_text: str
    completeness: str
    search_run_created_at: str | None
    provider_statuses: tuple[_ProviderStatus, ...]
    candidates: tuple[_Candidate, ...]
    provider_disagreements: tuple[_CandidateDisagreements, ...] | None


def _degraded_result() -> _Result:
    """One partial run: a rate-limited provider and a retracted candidate.

    Mirrors `test_discover_route.py`'s fixture shape (same field names,
    same fixture style) so the export and the page are demonstrably built
    from the same kind of data.
    """

    return _Result(
        search_run_id="run-abc-123",
        query_text="GLP-1 receptor agonist weight loss",
        completeness="partial",
        search_run_created_at="2026-08-15T11:22:00+00:00",
        provider_statuses=(
            _ProviderStatus(
                provider="pubmed", outcome="success", attempted=True, result_count=5, reason=None
            ),
            _ProviderStatus(
                provider="openalex",
                outcome="rate_limited",
                attempted=True,
                result_count=0,
                reason="provider_rate_limited",
            ),
        ),
        candidates=(
            _Candidate(
                canonical_id="pubmed:12345",
                title="A Trial of Semaglutide for Body Weight Reduction",
                doi="10.1000/example",
                publication_year=2026,
                providers=("pubmed",),
                observation_flags=(
                    _ObservationFlags(
                        provider="pubmed", retracted=True, preprint=None, preprint_version=None
                    ),
                ),
            ),
        ),
        provider_disagreements=(
            _CandidateDisagreements(
                canonical_id="pubmed:12345",
                disagreements=(
                    _Disagreement(
                        field="publication_year",
                        assertions=(_Assertion("pubmed", "12345", 2025),),
                    ),
                ),
            ),
        ),
    )


def _build_view(
    result: _Result, query: str = "GLP-1 receptor agonist weight loss"
) -> DiscoveryExportView:
    presentation = build_discovery_presentation(result)
    return build_discovery_export_view(query, result, presentation)


def test_markdown_export_carries_degraded_run_and_provider_limitation() -> None:
    view = _build_view(_degraded_result())

    markdown_text = render_discovery_export_markdown(view)

    assert "run-abc-123" in markdown_text
    assert "degraded / partial" in markdown_text
    assert "This is a degraded search run." in markdown_text
    assert "rate limited" in markdown_text
    # The reason string is data (Core-supplied), so its underscores are
    # Markdown-escaped the same way `report_renderer._report_text` escapes
    # every data value -- see the injection-hardening this mirrors.
    assert "provider\\_rate\\_limited" in markdown_text


def test_markdown_export_carries_retraction_and_disagreement_state() -> None:
    view = _build_view(_degraded_result())

    markdown_text = render_discovery_export_markdown(view)

    assert "A Trial of Semaglutide for Body Weight Reduction" in markdown_text
    assert "Retraction status: retracted" in markdown_text
    assert "Provider metadata disagreement: reported" in markdown_text


def test_markdown_export_discloses_missing_disagreement_data_like_the_page_does() -> None:
    result = _degraded_result()
    result_without_disagreements = type(result)(
        **{**result.__dict__, "provider_disagreements": None}
    )

    view = _build_view(result_without_disagreements)
    markdown_text = render_discovery_export_markdown(view)

    assert "predates provider-disagreement reporting" in markdown_text


def test_markdown_export_discloses_missing_run_timestamp() -> None:
    result = _degraded_result()
    result_without_timestamp = type(result)(**{**result.__dict__, "search_run_created_at": None})

    markdown_text = render_discovery_export_markdown(_build_view(result_without_timestamp))

    assert "not recorded for this search run" in markdown_text


def test_markdown_export_escapes_markdown_structural_characters() -> None:
    result = _degraded_result()
    hostile_candidate = type(result.candidates[0])(
        **{**result.candidates[0].__dict__, "title": "# Fake Heading | *bold* [link](evil)"}
    )
    hostile_result = type(result)(**{**result.__dict__, "candidates": (hostile_candidate,)})

    markdown_text = render_discovery_export_markdown(_build_view(hostile_result))

    assert "\n# Fake Heading" not in markdown_text
    assert "\\*bold\\*" in markdown_text
    assert "\\|" in markdown_text


def test_json_export_carries_the_same_coverage_limitations_as_markdown() -> None:
    view = _build_view(_degraded_result())

    payload = build_discovery_export_json(view)

    assert payload["search_run_id"] == "run-abc-123"
    assert payload["completeness"] == "partial"
    rate_limited = next(p for p in payload["provider_coverage"] if p["provider"] == "openalex")
    assert rate_limited["label"] == "rate limited"
    assert rate_limited["reason"] == "provider_rate_limited"

    candidate = payload["candidates"][0]
    assert candidate["title"] == "A Trial of Semaglutide for Body Weight Reduction"
    assert candidate["publication_status"]["retraction_state"] == "retracted"
    assert candidate["disagreement_state"] == "reported"
    assert candidate["disagreements"][0]["field"] == "publication_year"


def test_json_export_preserves_not_reported_as_null_not_false() -> None:
    """A provider that never reported a flag must not be conflated with an explicit `False`."""

    result = _degraded_result()
    payload = build_discovery_export_json(_build_view(result))

    observation = payload["candidates"][0]["publication_status"]["observations"][0]
    assert observation["preprint"] is None
    assert observation["retracted"] is True


def test_export_view_is_built_from_the_same_presentation_the_page_uses() -> None:
    """No separate recomputation: the export candidate list *is*
    `build_discovery_presentation`'s own candidate views, unchanged."""

    result = _degraded_result()
    presentation = build_discovery_presentation(result)

    view = build_discovery_export_view("q", result, presentation)

    assert view.candidates is presentation.candidates
    assert view.disagreement_data_available is presentation.disagreement_data_available
