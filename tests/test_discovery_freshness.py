from __future__ import annotations

from types import SimpleNamespace

from knowledge_engine_web.discovery_freshness import build_discovery_freshness


def _status(provider: str, outcome: str) -> SimpleNamespace:
    return SimpleNamespace(provider=provider, outcome=outcome)


def _current(
    *,
    search_run_id: str = "run-new",
    completeness: str = "complete",
    provider_statuses: tuple[SimpleNamespace, ...] = (),
    candidate_count: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        search_run_id=search_run_id,
        completeness=completeness,
        provider_statuses=provider_statuses,
        candidates=tuple(range(candidate_count)),
    )


def _run_record(
    *,
    search_run_id: str,
    created_at: str = "2026-06-01T09:00:00+00:00",
    completeness: str = "partial",
    candidate_count: int = 2,
    providers_completed: tuple[str, ...] = ("pubmed",),
) -> SimpleNamespace:
    return SimpleNamespace(
        search_run_id=search_run_id,
        created_at=created_at,
        completeness=completeness,
        candidate_count=candidate_count,
        providers_completed=providers_completed,
    )


def test_first_recorded_search_when_history_only_contains_the_current_run() -> None:
    current = _current()
    history = SimpleNamespace(
        run_count=1,
        runs=(_run_record(search_run_id="run-new"),),
    )

    freshness = build_discovery_freshness(current, history)

    assert freshness.is_first_recorded_search
    assert freshness.prior_run_count == 0
    assert freshness.previous_search_run_id is None
    assert freshness.candidate_count_delta is None


def test_first_recorded_search_when_history_is_empty() -> None:
    current = _current()
    history = SimpleNamespace(run_count=0, runs=())

    freshness = build_discovery_freshness(current, history)

    assert freshness.is_first_recorded_search


def test_computes_candidate_count_delta_against_the_most_recent_prior_run() -> None:
    current = _current(candidate_count=5)
    history = SimpleNamespace(
        run_count=2,
        runs=(
            _run_record(search_run_id="run-new", candidate_count=5),
            _run_record(search_run_id="run-old", candidate_count=2),
        ),
    )

    freshness = build_discovery_freshness(current, history)

    assert not freshness.is_first_recorded_search
    assert freshness.prior_run_count == 1
    assert freshness.previous_search_run_id == "run-old"
    assert freshness.candidate_count_delta == 3


def test_uses_the_first_non_current_run_as_previous_when_newest_first() -> None:
    current = _current(candidate_count=5)
    history = SimpleNamespace(
        run_count=3,
        runs=(
            _run_record(search_run_id="run-new", candidate_count=5),
            _run_record(
                search_run_id="run-middle", created_at="2026-07-01T00:00:00Z", candidate_count=4
            ),
            _run_record(
                search_run_id="run-oldest", created_at="2026-06-01T00:00:00Z", candidate_count=1
            ),
        ),
    )

    freshness = build_discovery_freshness(current, history)

    assert freshness.previous_search_run_id == "run-middle"
    assert freshness.prior_run_count == 2


def test_reports_newly_completed_and_newly_failed_providers() -> None:
    current = _current(
        provider_statuses=(
            _status("pubmed", "success"),
            _status("crossref", "empty"),
            _status("openalex", "rate_limited"),
        )
    )
    history = SimpleNamespace(
        run_count=2,
        runs=(
            _run_record(search_run_id="run-new"),
            _run_record(
                search_run_id="run-old",
                providers_completed=("openalex", "semantic_scholar"),
            ),
        ),
    )

    freshness = build_discovery_freshness(current, history)

    # pubmed/crossref completed now but hadn't before; openalex/semantic_scholar
    # had completed before but did not this time.
    assert freshness.newly_completed_providers == ("crossref", "pubmed")
    assert freshness.newly_failed_providers == ("openalex", "semantic_scholar")


def test_unchanged_provider_coverage_reports_no_deltas_either_direction() -> None:
    current = _current(provider_statuses=(_status("pubmed", "success"),))
    history = SimpleNamespace(
        run_count=2,
        runs=(
            _run_record(search_run_id="run-new"),
            _run_record(search_run_id="run-old", providers_completed=("pubmed",)),
        ),
    )

    freshness = build_discovery_freshness(current, history)

    assert freshness.newly_completed_providers == ()
    assert freshness.newly_failed_providers == ()


def test_per_candidate_history_is_always_reported_unavailable() -> None:
    """This module deliberately never claims candidate-level freshness.

    `ke federated-discover-history` only returns aggregate coverage facts
    per run, not the candidate list -- see this module's own docstring.
    """

    current = _current()
    history = SimpleNamespace(run_count=1, runs=(_run_record(search_run_id="run-new"),))

    freshness = build_discovery_freshness(current, history)

    assert freshness.per_candidate_history_available is False
