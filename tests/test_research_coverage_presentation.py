from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine_web.research_coverage_presentation import build_research_coverage_panel


@dataclass(frozen=True)
class _ProviderStatus:
    provider: str
    outcome: str
    result_count: int
    reason: str | None


@dataclass(frozen=True)
class _FederatedDiscovery:
    search_run_id: str
    completeness: str
    provider_statuses: tuple[_ProviderStatus, ...]
    candidates: tuple[object, ...]
    search_run_created_at: str | None


@dataclass(frozen=True)
class _Discovery:
    triggered: bool
    trigger_reason: str
    evidence_record_coverage: int
    federated_discovery: _FederatedDiscovery | None
    federated_discovery_attempted: bool
    federated_discovery_error: str | None
    acquisition_plan_attempted: bool
    acquisition_plan_skipped_reason: str | None
    acquisition_plan_error: str | None


@dataclass(frozen=True)
class _AcquisitionRoute:
    route: str
    attempted: bool
    candidate_ids: tuple[str, ...]
    persisted_count: int
    reused_count: int
    error: str | None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class _GroundedCompletion:
    attempted: bool
    already_indexed_paper_ids: tuple[int, ...]
    acquisition_routes: tuple[_AcquisitionRoute, ...]
    draft_item_count: int
    classified_item_count: int
    staged_record_ids: tuple[str, ...]
    grounded_record_ids: tuple[str, ...]
    promoted_record_ids: tuple[str, ...]
    grounding_failures: tuple[str, ...]
    extraction_error: str | None
    reretrieval_error: str | None
    skipped_reason: str | None


def _not_triggered_discovery() -> _Discovery:
    return _Discovery(
        triggered=False,
        trigger_reason="Evidence-record coverage (2) met the configured threshold (1).",
        evidence_record_coverage=2,
        federated_discovery=None,
        federated_discovery_attempted=False,
        federated_discovery_error=None,
        acquisition_plan_attempted=False,
        acquisition_plan_skipped_reason=None,
        acquisition_plan_error=None,
    )


def test_returns_none_when_discovery_was_never_evaluated() -> None:
    assert build_research_coverage_panel(None, None) is None


def test_not_triggered_discovery_still_returns_a_panel_explaining_why() -> None:
    panel = build_research_coverage_panel(_not_triggered_discovery(), None)

    assert panel is not None
    assert panel.discovery_triggered is False
    assert panel.federated_discovery_attempted is False
    assert panel.candidate_count == 0
    assert panel.provider_rows == ()
    assert panel.grounded_completion_attempted is False
    assert panel.promoted_record_count == 0


def test_provider_rows_reuse_the_shared_outcome_label_and_css_class() -> None:
    discovery = _Discovery(
        triggered=True,
        trigger_reason="Evidence-record coverage (0) fell below the configured threshold (1).",
        evidence_record_coverage=0,
        federated_discovery=_FederatedDiscovery(
            search_run_id="run-1",
            completeness="partial",
            provider_statuses=(
                _ProviderStatus(provider="pubmed", outcome="success", result_count=4, reason=None),
                _ProviderStatus(
                    provider="crossref",
                    outcome="unavailable",
                    result_count=0,
                    reason="timeout",
                ),
            ),
            candidates=(object(), object()),
            search_run_created_at="2026-08-29T00:00:00Z",
        ),
        federated_discovery_attempted=True,
        federated_discovery_error=None,
        acquisition_plan_attempted=True,
        acquisition_plan_skipped_reason=None,
        acquisition_plan_error=None,
    )

    panel = build_research_coverage_panel(discovery, None)

    assert panel is not None
    assert panel.search_run_id == "run-1"
    assert panel.completeness == "partial"
    assert panel.candidate_count == 2
    assert panel.provider_rows[0].provider == "pubmed"
    assert panel.provider_rows[0].label == "searched"
    assert panel.provider_rows[0].css_class == "is-ok"
    assert panel.provider_rows[1].label == "unavailable"
    assert panel.provider_rows[1].css_class == "is-degraded"
    assert panel.provider_rows[1].reason == "timeout"


def test_acquisition_and_extraction_funnel_counts_stay_independent_of_evidence_count() -> None:
    """BT-2: candidate/acquisition totals must remain distinct from Evidence Record totals."""

    grounded_completion = _GroundedCompletion(
        attempted=True,
        already_indexed_paper_ids=(101,),
        acquisition_routes=(
            _AcquisitionRoute(
                route="pmc_oa",
                attempted=True,
                candidate_ids=("c1", "c2", "c3"),
                persisted_count=2,
                reused_count=1,
                error=None,
            ),
            _AcquisitionRoute(
                route="core",
                attempted=False,
                candidate_ids=("c4",),
                persisted_count=0,
                reused_count=0,
                error=None,
                skipped_reason="max_acquisition_routes budget reached",
            ),
        ),
        draft_item_count=5,
        classified_item_count=4,
        staged_record_ids=("s1", "s2", "s3"),
        grounded_record_ids=("s1", "s2"),
        promoted_record_ids=("s1",),
        grounding_failures=("s3",),
        extraction_error=None,
        reretrieval_error=None,
        skipped_reason=None,
    )

    panel = build_research_coverage_panel(_not_triggered_discovery(), grounded_completion)

    assert panel is not None
    assert panel.already_indexed_paper_count == 1
    assert len(panel.acquisition_routes) == 2
    assert panel.acquisition_routes[0].candidate_count == 3
    assert panel.acquisition_routes[0].persisted_count == 2
    assert panel.acquisition_routes[1].attempted is False
    assert panel.acquisition_routes[1].skipped_reason == "max_acquisition_routes budget reached"
    assert panel.acquisition_routes[0].skipped_reason is None
    # The funnel is deliberately reported at every stage, not collapsed to one number.
    assert panel.draft_item_count == 5
    assert panel.classified_item_count == 4
    assert panel.staged_record_count == 3
    assert panel.grounded_record_count == 2
    assert panel.promoted_record_count == 1
    assert panel.grounding_failure_count == 1


def test_already_indexed_reuse_is_visible_even_when_no_route_was_attempted() -> None:
    """Already-indexed reuse (no network acquisition needed) still reports a real count."""

    grounded_completion = _GroundedCompletion(
        attempted=True,
        already_indexed_paper_ids=(1, 2, 3),
        acquisition_routes=(),
        draft_item_count=0,
        classified_item_count=0,
        staged_record_ids=(),
        grounded_record_ids=(),
        promoted_record_ids=("existing-1",),
        grounding_failures=(),
        extraction_error=None,
        reretrieval_error=None,
        skipped_reason=None,
    )

    panel = build_research_coverage_panel(_not_triggered_discovery(), grounded_completion)

    assert panel is not None
    assert panel.already_indexed_paper_count == 3
    assert panel.acquisition_routes == ()
