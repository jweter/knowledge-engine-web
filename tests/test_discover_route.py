from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from knowledge_engine_web import main
from knowledge_engine_web.ai_guardrails import AIAdmissionError
from knowledge_engine_web.discovery_orchestration import (
    DiscoveryCapability,
    DiscoveryOrchestrationError,
)
from knowledge_engine_web.main import app


def _available_capability() -> DiscoveryCapability:
    return DiscoveryCapability(available=True)


def _unavailable_capability() -> DiscoveryCapability:
    return DiscoveryCapability(
        available=False,
        reason_code="core_cli_unavailable",
        visitor_message="Discovery is unavailable on this deployment.",
    )


def _discovery_result(
    *,
    completeness: str = "partial",
    provider_disagreements: tuple[SimpleNamespace, ...] | None = (),
    observation_flags: tuple[SimpleNamespace, ...] = (),
    search_run_created_at: str | None = "2026-08-15T11:22:00+00:00",
) -> SimpleNamespace:
    """One fixture covering every provider outcome WEB-FRD-1 must render.

    success with zero results, rate_limited, unavailable, disabled, and
    skipped ("not relevant" in the roadmap doc's language) all appear, so a
    single test proves the UI's status label never depends on `result_count`.
    `provider_disagreements` defaults to an empty (available, no conflicts)
    report; pass `None` to simulate a snapshot that predates WEB-FRD-3.
    `observation_flags` defaults to empty (no provider reported a
    retraction/preprint flag for this candidate). `search_run_created_at`
    defaults to a recorded timestamp (WEB-FRD-2); pass `None` to simulate an
    older cached result or a snapshot predating Core's `coverage.created_at`.
    """

    return SimpleNamespace(
        search_run_id="run-abc-123",
        query_text="GLP-1 receptor agonist weight loss",
        completeness=completeness,
        search_run_created_at=search_run_created_at,
        provider_statuses=(
            SimpleNamespace(
                provider="pubmed", outcome="success", attempted=True, result_count=5, reason=None
            ),
            SimpleNamespace(
                provider="crossref", outcome="empty", attempted=True, result_count=0, reason=None
            ),
            SimpleNamespace(
                provider="openalex",
                outcome="rate_limited",
                attempted=True,
                result_count=0,
                reason="provider_rate_limited",
            ),
            SimpleNamespace(
                provider="semantic_scholar",
                outcome="unavailable",
                attempted=True,
                result_count=0,
                reason="provider_unavailable",
            ),
            SimpleNamespace(
                provider="arxiv",
                outcome="disabled",
                attempted=False,
                result_count=0,
                reason="no_api_key_configured",
            ),
        ),
        candidates=(
            SimpleNamespace(
                canonical_id="pubmed:12345",
                title="A Trial of Semaglutide for Body Weight Reduction",
                doi="10.1000/example",
                publication_year=2026,
                providers=("pubmed",),
                observation_flags=observation_flags,
            ),
        ),
        provider_disagreements=provider_disagreements,
    )


def test_discover_page_renders_the_empty_state_with_no_query() -> None:
    response = TestClient(app).get("/discover")

    assert response.status_code == 200
    assert "Live discovery" in response.text
    assert "Results for" not in response.text


def test_discover_form_shows_unavailable_notice_when_runtime_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _unavailable_capability()
    )

    response = TestClient(app).get("/discover")

    assert response.status_code == 200
    assert "Discovery is unavailable on this deployment." in response.text


def test_discover_query_shows_unavailable_error_without_invoking_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _unavailable_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: pytest.fail("unavailable runtime must not be invoked"),
    )

    response = TestClient(app).get("/discover", params={"q": "semaglutide"})

    assert response.status_code == 200
    assert "Discovery is unavailable on this deployment." in response.text


def test_discover_renders_every_provider_outcome_without_inferring_from_result_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    # success, including the empty-but-searched Crossref case -- never
    # relabeled as unavailable merely because it returned zero results.
    assert "searched, no matches" in body
    assert "rate limited" in body
    assert body.count("unavailable") >= 1
    assert "disabled" in body
    assert "provider_rate_limited" in body
    assert "A Trial of Semaglutide for Body Weight Reduction" in body


def test_discover_exposes_search_method_provenance_without_claiming_unrun_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Search method and provenance" in body
    assert "GLP-1 receptor agonist weight loss" in body
    assert "run-abc-123" in body
    assert "pubmed, crossref, openalex, semantic_scholar, arxiv" in body
    assert "This Web discovery entry point does not currently request a year bound." in body
    assert body.count("Not run by this discovery entry point.") == 2
    assert "2026-08-15T11:22:00+00:00" in body
    assert "search-provenance facts, not evidence-quality scores" in body


def test_discover_shows_not_recorded_when_run_timestamp_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older cached result or a pre-coverage-block snapshot must not crash.

    `knowledge_engine_ai.ke_client.parse_federated_discovery_result` parses a
    missing `coverage.created_at` to `None` rather than fabricating a value
    (WEB-FRD-2); the Web-facing row must say so plainly instead of omitting
    the row or inventing a timestamp.
    """

    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(search_run_created_at=None),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Not recorded for this search run" in body
    assert "2026-08-15T11:22:00+00:00" not in body


def test_discover_shows_degraded_state_in_text_and_visual_treatment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="partial"),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert "degraded / partial" in response.text
    assert "is-degraded" in response.text
    assert "This is a degraded search run." in response.text


def test_discover_shows_complete_state_without_a_degraded_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert "This is a degraded search run." not in response.text


def test_discover_shows_admission_error_when_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )

    def fail(settings: object, query: str, **kwargs: object) -> None:
        raise AIAdmissionError("rate_limit_reached", "Discovery has received too many requests.")

    monkeypatch.setattr(main, "run_guarded_discovery", fail)

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert "Discovery has received too many requests." in response.text


def test_discover_shows_no_disagreement_badge_when_report_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(provider_disagreements=()),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "no provider metadata disagreement reported" in body
    assert "What providers disagree about" not in body


def test_discover_shows_disagreement_details_without_calling_it_a_contradiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    disagreement_report = (
        SimpleNamespace(
            canonical_id="pubmed:12345",
            disagreements=(
                SimpleNamespace(
                    field="publication_year",
                    assertions=(
                        SimpleNamespace(provider="pubmed", provider_id="12345", value=2025),
                        SimpleNamespace(
                            provider="crossref", provider_id="10.1000/example", value=2026
                        ),
                    ),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            provider_disagreements=disagreement_report
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "provider metadata disagreement" in body
    assert "What providers disagree about" in body
    assert "publication_year" in body
    assert "pubmed: 2025" in body
    assert "crossref: 2026" in body
    assert "not a scientific contradiction between" in body


def test_discover_notes_when_disagreement_data_predates_this_search_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(provider_disagreements=None),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "predates provider-disagreement reporting" in body
    assert "no provider metadata disagreement reported" not in body
    assert "provider metadata disagreement" not in body


def test_discover_shows_not_checked_retraction_status_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Retraction status: not checked by any searched provider." in body
    assert "publication-status-banner" not in body


def test_discover_shows_a_prominent_retraction_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            observation_flags=(
                SimpleNamespace(
                    provider="pubmed", retracted=False, preprint=None, preprint_version=None
                ),
                SimpleNamespace(
                    provider="crossref", retracted=True, preprint=None, preprint_version=None
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "publication-status-banner is-critical" in body
    assert "Retracted:" in body
    # The per-provider breakdown remains inspectable and unmerged: pubmed's
    # explicit "not retracted" is preserved alongside crossref's "retracted".
    assert "Publication-status observations by provider" in body
    assert "pubmed" in body and "crossref" in body


def test_discover_shows_preprint_badge_with_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            observation_flags=(
                SimpleNamespace(
                    provider="arxiv", retracted=None, preprint=True, preprint_version=2
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "preprint (v2)" in body
    assert "publication-status-banner" not in body


def test_discover_shows_independent_correction_concern_and_withdrawal_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            observation_flags=(
                SimpleNamespace(
                    provider="crossref",
                    retracted=False,
                    preprint=None,
                    preprint_version=None,
                    corrected=True,
                    expression_of_concern=True,
                    withdrawn=True,
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Corrected:" in body
    assert "Expression of concern:" in body
    assert "Withdrawn:" in body
    assert "corrected:" in body and "yes" in body


def test_discover_shows_orchestration_error_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )

    def fail(settings: object, query: str, **kwargs: object) -> None:
        raise DiscoveryOrchestrationError("Discovery could not complete this request.")

    monkeypatch.setattr(main, "run_guarded_discovery", fail)

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert "Discovery could not complete this request." in response.text


def test_discover_shows_first_recorded_search_when_no_prior_history_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(),
    )
    monkeypatch.setattr(
        main,
        "run_discovery_history",
        lambda settings, research_question_id: SimpleNamespace(
            research_question_id=research_question_id,
            run_count=1,
            runs=(SimpleNamespace(search_run_id="run-abc-123"),),
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Since your last search" in body
    assert "This is the first recorded search for this question." in body


def test_discover_shows_freshness_deltas_against_a_prior_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )
    monkeypatch.setattr(
        main,
        "run_discovery_history",
        lambda settings, research_question_id: SimpleNamespace(
            research_question_id=research_question_id,
            run_count=2,
            runs=(
                SimpleNamespace(search_run_id="run-abc-123"),
                SimpleNamespace(
                    search_run_id="run-prior",
                    created_at="2026-06-01T09:00:00+00:00",
                    completeness="partial",
                    candidate_count=0,
                    providers_completed=("crossref",),
                ),
            ),
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "2026-06-01T09:00:00+00:00" in body
    assert "+1 since last time" in body
    assert "now reachable: pubmed" in body
    assert "no longer reachable" not in body
    assert "was partial, now complete" in body
    assert "cannot yet show which specific works are newly" in body


def _prior_run_history(*, candidate_count: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        research_question_id="rq-web-abc",
        run_count=2,
        runs=(
            SimpleNamespace(search_run_id="run-abc-123"),
            SimpleNamespace(
                search_run_id="run-prior",
                created_at="2026-06-01T09:00:00+00:00",
                completeness="partial",
                candidate_count=candidate_count,
                providers_completed=("pubmed",),
            ),
        ),
    )


def _candidate_snapshot(
    *, candidates: tuple[SimpleNamespace, ...], candidate_count: int | None = None
) -> SimpleNamespace:
    """A `FederatedCoverageReportResult`-shaped fixture.

    ``candidate_count`` defaults to matching ``len(candidates)`` -- a
    self-consistent snapshot, as Core reports for any run persisted after
    candidate-snapshot persistence (Core PR #394) landed. Pass an explicit,
    higher value to simulate a run that predates that change: the point
    lookup still reports its real historical aggregate count on ``coverage``
    but an honest empty ``candidates`` tuple.
    """

    resolved_count = len(candidates) if candidate_count is None else candidate_count
    return SimpleNamespace(
        search_run_id="run-prior",
        coverage=SimpleNamespace(candidate_count=resolved_count),
        candidates=candidates,
    )


def test_discover_shows_newly_discovered_candidates_when_snapshot_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WEB-FRD-5 item 7: a specific new work, not just an aggregate count delta."""

    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )
    monkeypatch.setattr(
        main, "run_discovery_history", lambda settings, research_question_id: _prior_run_history()
    )
    monkeypatch.setattr(
        main,
        "run_discovery_candidate_snapshot",
        lambda settings, search_run_id: _candidate_snapshot(candidates=()),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Newly discovered works" in body
    assert "A Trial of Semaglutide for Body Weight Reduction" in body
    assert "cannot yet show which specific works are newly" not in body


def test_discover_degrades_to_run_level_freshness_when_prior_snapshot_predates_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prior run recorded before Core PR #394 must not fake a zero-candidate baseline.

    Regression test for the PR #75 review finding: such a run's point lookup
    succeeds and returns an empty ``candidates`` tuple, but that run's own
    aggregate ``candidate_count`` was nonzero -- the snapshot has no real
    per-candidate data, not "this run found zero candidates". Treating the
    empty tuple as a valid baseline would misreport the current run's only
    candidate as newly discovered; the correct behavior is to fall back to
    the run-level-only comparison instead.
    """

    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )
    monkeypatch.setattr(
        main,
        "run_discovery_history",
        lambda settings, research_question_id: _prior_run_history(candidate_count=3),
    )
    monkeypatch.setattr(
        main,
        "run_discovery_candidate_snapshot",
        # Predates candidate-snapshot persistence: an honest empty
        # `candidates` tuple alongside the run's real, nonzero
        # `candidate_count`.
        lambda settings, search_run_id: _candidate_snapshot(candidates=(), candidate_count=3),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Since your last search" in body
    assert "cannot yet show which specific works are newly" in body
    assert "Newly discovered works" not in body
    assert "A Trial of Semaglutide for Body Weight Reduction" in body


def test_discover_shows_newly_retracted_candidates_with_was_now_framing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            completeness="complete",
            observation_flags=(
                SimpleNamespace(
                    provider="pubmed", retracted=True, preprint=None, preprint_version=None
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        main, "run_discovery_history", lambda settings, research_question_id: _prior_run_history()
    )
    monkeypatch.setattr(
        main,
        "run_discovery_candidate_snapshot",
        lambda settings, search_run_id: _candidate_snapshot(
            candidates=(
                SimpleNamespace(
                    canonical_id="pubmed:12345",
                    title="A Trial of Semaglutide for Body Weight Reduction",
                    doi="10.1000/example",
                    publication_year=2026,
                    observations=(
                        SimpleNamespace(
                            provider="pubmed",
                            retracted=False,
                            preprint=None,
                            preprint_version=None,
                        ),
                    ),
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Newly flagged as retracted" in body
    assert "reported clear of retraction" in body
    assert "now reported retracted" in body
    assert "Newly discovered works" not in body


def test_discover_shows_newly_corrected_expression_of_concern_and_withdrawn_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WEB-FRD-5 item 7's remaining slice: all four flags, not retraction alone."""

    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(
            completeness="complete",
            observation_flags=(
                SimpleNamespace(
                    provider="pubmed",
                    retracted=None,
                    preprint=None,
                    preprint_version=None,
                    corrected=True,
                    expression_of_concern=True,
                    withdrawn=True,
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        main, "run_discovery_history", lambda settings, research_question_id: _prior_run_history()
    )
    monkeypatch.setattr(
        main,
        "run_discovery_candidate_snapshot",
        lambda settings, search_run_id: _candidate_snapshot(
            candidates=(
                SimpleNamespace(
                    canonical_id="pubmed:12345",
                    title="A Trial of Semaglutide for Body Weight Reduction",
                    doi="10.1000/example",
                    publication_year=2026,
                    observations=(
                        SimpleNamespace(
                            provider="pubmed",
                            retracted=None,
                            preprint=None,
                            preprint_version=None,
                            corrected=False,
                            expression_of_concern=False,
                            withdrawn=False,
                        ),
                    ),
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Newly flagged as corrected" in body
    assert "Newly flagged with an expression of concern" in body
    assert "Newly flagged as withdrawn" in body
    assert "now reported corrected" in body
    assert "now reported under an expression of concern" in body
    assert "now reported withdrawn" in body
    assert "Newly flagged as retracted" not in body


def test_discover_shows_an_honest_no_changes_message_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )
    monkeypatch.setattr(
        main, "run_discovery_history", lambda settings, research_question_id: _prior_run_history()
    )
    monkeypatch.setattr(
        main,
        "run_discovery_candidate_snapshot",
        lambda settings, search_run_id: _candidate_snapshot(
            candidates=(
                SimpleNamespace(
                    canonical_id="pubmed:12345",
                    title="A Trial of Semaglutide for Body Weight Reduction",
                    doi="10.1000/example",
                    publication_year=2026,
                    observations=(),
                ),
            )
        ),
    )

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "No newly discovered works and no newly flagged publication-status changes" in body
    assert "Newly discovered works" not in body
    assert "Newly flagged as retracted" not in body


def test_discover_degrades_to_run_level_freshness_when_candidate_snapshot_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(completeness="complete"),
    )
    monkeypatch.setattr(
        main, "run_discovery_history", lambda settings, research_question_id: _prior_run_history()
    )

    def fail_snapshot(settings: object, search_run_id: str) -> None:
        raise DiscoveryOrchestrationError("Search history could not be read for this deployment.")

    monkeypatch.setattr(main, "run_discovery_candidate_snapshot", fail_snapshot)

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    body = response.text
    assert "Since your last search" in body
    assert "cannot yet show which specific works are newly" in body
    assert "A Trial of Semaglutide for Body Weight Reduction" in body


def test_discover_omits_freshness_section_when_history_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "evaluate_discovery_capability", lambda settings: _available_capability()
    )
    monkeypatch.setattr(
        main,
        "run_guarded_discovery",
        lambda settings, query, **kwargs: _discovery_result(),
    )

    def fail_history(settings: object, research_question_id: str) -> None:
        raise DiscoveryOrchestrationError("Search history could not be read for this deployment.")

    monkeypatch.setattr(main, "run_discovery_history", fail_history)

    response = TestClient(app).get("/discover", params={"q": "GLP-1 weight loss"})

    assert response.status_code == 200
    assert "Since your last search" not in response.text
    assert "A Trial of Semaglutide for Body Weight Reduction" in response.text
