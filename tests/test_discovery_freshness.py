from __future__ import annotations

from types import SimpleNamespace

from knowledge_engine_web.discovery_freshness import (
    build_candidate_freshness,
    build_discovery_freshness,
)
from knowledge_engine_web.discovery_presentation import PublicationStatusView


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
    """`build_discovery_freshness` alone never claims candidate-level freshness.

    That layer is a strictly additive composition the caller (`main.py`)
    performs with `build_candidate_freshness` below, once a specific past
    run's full candidate snapshot is actually available -- see this
    module's own docstring.
    """

    current = _current()
    history = SimpleNamespace(run_count=1, runs=(_run_record(search_run_id="run-new"),))

    freshness = build_discovery_freshness(current, history)

    assert freshness.per_candidate_history_available is False
    assert freshness.candidate_level is None


def _observation(
    provider: str,
    *,
    retracted: bool | None = None,
    preprint: bool | None = None,
    preprint_version: int | None = None,
    corrected: bool | None = None,
    expression_of_concern: bool | None = None,
    withdrawn: bool | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        retracted=retracted,
        preprint=preprint,
        preprint_version=preprint_version,
        corrected=corrected,
        expression_of_concern=expression_of_concern,
        withdrawn=withdrawn,
    )


def _current_candidate(
    *,
    canonical_id: str,
    title: str = "A trial",
    doi: str | None = "10.1000/example",
    publication_year: int | None = 2026,
    providers: tuple[str, ...] = ("pubmed",),
    retraction_state: str = "not_checked",
    correction_state: str = "not_checked",
    expression_of_concern_state: str = "not_checked",
    withdrawal_state: str = "not_checked",
) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_id=canonical_id,
        title=title,
        doi=doi,
        publication_year=publication_year,
        providers=providers,
        publication_status=PublicationStatusView(
            retraction_state=retraction_state,
            preprint_state="not_checked",
            correction_state=correction_state,
            expression_of_concern_state=expression_of_concern_state,
            withdrawal_state=withdrawal_state,
            preprint_versions=(),
            observations=(),
        ),
    )


def _previous_candidate(
    *, canonical_id: str, observations: tuple[SimpleNamespace, ...] = ()
) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_id=canonical_id,
        title="A trial",
        doi="10.1000/example",
        publication_year=2026,
        observations=observations,
    )


def test_candidate_freshness_reports_a_candidate_absent_from_the_previous_run() -> None:
    current = (_current_candidate(canonical_id="doi:new"),)
    previous: tuple[SimpleNamespace, ...] = ()

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_discovered) == 1
    assert freshness.newly_discovered[0].canonical_id == "doi:new"
    assert freshness.newly_retracted == ()
    assert freshness.newly_corrected == ()
    assert freshness.newly_expression_of_concern == ()
    assert freshness.newly_withdrawn == ()


def test_candidate_freshness_does_not_report_a_candidate_seen_in_both_runs_as_new() -> None:
    current = (_current_candidate(canonical_id="doi:seen"),)
    previous = (_previous_candidate(canonical_id="doi:seen"),)

    freshness = build_candidate_freshness(current, previous)

    assert freshness.newly_discovered == ()


def test_candidate_freshness_reports_a_retraction_flip_from_clear() -> None:
    current = (_current_candidate(canonical_id="doi:flip", retraction_state="retracted"),)
    previous = (
        _previous_candidate(
            canonical_id="doi:flip",
            observations=(_observation("pubmed", retracted=False),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_retracted) == 1
    assert freshness.newly_retracted[0].candidate.canonical_id == "doi:flip"
    assert freshness.newly_retracted[0].previous_state == "clear"
    assert freshness.newly_discovered == ()


def test_candidate_freshness_reports_a_retraction_flip_from_not_checked() -> None:
    current = (_current_candidate(canonical_id="doi:flip", retraction_state="retracted"),)
    previous = (_previous_candidate(canonical_id="doi:flip", observations=()),)

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_retracted) == 1
    assert freshness.newly_retracted[0].previous_state == "not_checked"


def test_candidate_freshness_reports_a_correction_flip() -> None:
    current = (_current_candidate(canonical_id="doi:flip", correction_state="corrected"),)
    previous = (
        _previous_candidate(
            canonical_id="doi:flip",
            observations=(_observation("pubmed", corrected=False),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_corrected) == 1
    assert freshness.newly_corrected[0].candidate.canonical_id == "doi:flip"
    assert freshness.newly_corrected[0].previous_state == "clear"
    assert freshness.newly_retracted == ()


def test_candidate_freshness_reports_an_expression_of_concern_flip() -> None:
    current = (
        _current_candidate(
            canonical_id="doi:flip", expression_of_concern_state="expression_of_concern"
        ),
    )
    previous = (_previous_candidate(canonical_id="doi:flip", observations=()),)

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_expression_of_concern) == 1
    assert freshness.newly_expression_of_concern[0].previous_state == "not_checked"


def test_candidate_freshness_reports_a_withdrawal_flip() -> None:
    current = (_current_candidate(canonical_id="doi:flip", withdrawal_state="withdrawn"),)
    previous = (
        _previous_candidate(
            canonical_id="doi:flip",
            observations=(_observation("pubmed", withdrawn=False),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_withdrawn) == 1
    assert freshness.newly_withdrawn[0].previous_state == "clear"


def test_candidate_freshness_flags_are_independent_and_non_exclusive() -> None:
    """A candidate newly retracted and newly corrected in the same run lands in both lists."""

    current = (
        _current_candidate(
            canonical_id="doi:both",
            retraction_state="retracted",
            correction_state="corrected",
        ),
    )
    previous = (
        _previous_candidate(
            canonical_id="doi:both",
            observations=(_observation("pubmed", retracted=False, corrected=False),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_retracted) == 1
    assert len(freshness.newly_corrected) == 1
    assert freshness.newly_retracted[0].candidate.canonical_id == "doi:both"
    assert freshness.newly_corrected[0].candidate.canonical_id == "doi:both"


def test_candidate_freshness_does_not_repeat_an_already_corrected_or_withdrawn_candidate() -> None:
    current = (
        _current_candidate(
            canonical_id="doi:still",
            correction_state="corrected",
            withdrawal_state="withdrawn",
        ),
    )
    previous = (
        _previous_candidate(
            canonical_id="doi:still",
            observations=(_observation("pubmed", corrected=True, withdrawn=True),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert freshness.newly_corrected == ()
    assert freshness.newly_withdrawn == ()


def test_candidate_freshness_does_not_repeat_an_already_retracted_candidate() -> None:
    current = (_current_candidate(canonical_id="doi:still", retraction_state="retracted"),)
    previous = (
        _previous_candidate(
            canonical_id="doi:still",
            observations=(_observation("pubmed", retracted=True),),
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert freshness.newly_retracted == ()


def test_candidate_freshness_does_not_double_count_a_newly_discovered_retracted_candidate() -> None:
    """A brand-new candidate that happens to already be retracted has no

    prior "was X" state to compare against, so it belongs only in
    `newly_discovered`, not `newly_retracted`.
    """

    current = (
        _current_candidate(canonical_id="doi:new-and-retracted", retraction_state="retracted"),
    )
    previous: tuple[SimpleNamespace, ...] = ()

    freshness = build_candidate_freshness(current, previous)

    assert len(freshness.newly_discovered) == 1
    assert freshness.newly_retracted == ()


def test_candidate_freshness_is_empty_when_nothing_changed() -> None:
    current = (_current_candidate(canonical_id="doi:seen", retraction_state="clear"),)
    previous = (
        _previous_candidate(
            canonical_id="doi:seen", observations=(_observation("pubmed", retracted=False),)
        ),
    )

    freshness = build_candidate_freshness(current, previous)

    assert freshness.newly_discovered == ()
    assert freshness.newly_retracted == ()
