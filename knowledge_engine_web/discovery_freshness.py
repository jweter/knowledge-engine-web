"""WEB-FRD-5 (research freshness history): honest, presentation-only diffing.

This module computes exactly what Core+AI's current contract can support --
no more. `docs/roadmap/web_frd5_freshness_history_design.md` section 4
sketches two layers: run-level facts (last search date, aggregate candidate
count, provider coverage) and candidate-level facts (specific newly
discovered works, a specific candidate's retraction flag flipping). Both are
now honest to render:

- Run-level: `build_discovery_freshness` compares the current run against
  `ke federated-discover-history`'s aggregate `SearchCoverageReport` per past
  run (candidate count, provider outcomes, completeness, timestamp) -- this
  has been available since this module's introduction.
- Candidate-level: `build_candidate_freshness` additionally compares the
  current run's full candidate list against one specific past run's full
  candidate snapshot, now reachable via `ke_client.federated_coverage_report()`
  (knowledge-engine-ai PR #55, wrapping Core PR #394's
  `federated-coverage-report --output`). This closes WEB-FRD-5's remaining
  two exit criteria: "newly discovered works are visible" and "new
  corrections/retractions are highlighted" (the retraction half only --
  correction/expression-of-concern/withdrawal states remain out of scope for
  the same reason WEB-FRD-4 left them out: Core's `ProviderObservation` does
  not carry those fields yet, a separate and still-blocked Core change).

Candidate-level diffing is best-effort and additive: a run persisted before
Core's candidate-snapshot follow-up existed reports an honest empty
candidate list (Core/AI's own contract, not this module's approximation),
and a failure fetching the previous run's snapshot degrades to the run-level
view alone (`DiscoveryFreshnessView.candidate_level` stays `None`) rather
than failing the whole "Since your last search" section. This is the same
discipline this project has already applied elsewhere: render exactly what
is durably known, and say plainly what is not yet available, rather than
approximating it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from knowledge_engine_web.discovery_presentation import (
    ObservationFlagSource,
    PublicationStatusView,
    build_publication_status,
)

_COMPLETED_OUTCOMES = frozenset({"success", "empty"})


class ProviderStatusSource(Protocol):
    @property
    def provider(self) -> str: ...
    @property
    def outcome(self) -> str: ...


class CandidateCountSource(Protocol):
    def __len__(self) -> int: ...


class CurrentDiscoveryResultSource(Protocol):
    @property
    def search_run_id(self) -> str: ...
    @property
    def completeness(self) -> str: ...
    @property
    def provider_statuses(self) -> tuple[ProviderStatusSource, ...]: ...
    @property
    def candidates(self) -> CandidateCountSource: ...


class SearchCoverageReportSource(Protocol):
    @property
    def search_run_id(self) -> str: ...
    @property
    def created_at(self) -> str: ...
    @property
    def completeness(self) -> str: ...
    @property
    def candidate_count(self) -> int: ...
    @property
    def providers_completed(self) -> tuple[str, ...]: ...


class DiscoveryHistorySource(Protocol):
    @property
    def run_count(self) -> int: ...
    @property
    def runs(self) -> tuple[SearchCoverageReportSource, ...]: ...


class CurrentCandidateSource(Protocol):
    """One current-run candidate card, as `discovery_presentation.DiscoveryCandidateView`."""

    @property
    def canonical_id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def doi(self) -> str | None: ...
    @property
    def publication_year(self) -> int | None: ...
    @property
    def providers(self) -> tuple[str, ...]: ...
    @property
    def publication_status(self) -> PublicationStatusView: ...


class PastCandidateSource(Protocol):
    """One past-run candidate, as `ke_client.FederatedCandidateRecord`.

    ``observations`` (not ``observation_flags``) is Core/AI's own field name
    for this type -- deliberately not renamed here so this protocol matches
    the real dependency shape without an adapter layer.
    """

    @property
    def canonical_id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def doi(self) -> str | None: ...
    @property
    def publication_year(self) -> int | None: ...
    @property
    def observations(self) -> tuple[ObservationFlagSource, ...]: ...


@dataclass(frozen=True)
class RetractedCandidateFreshnessView:
    """One candidate whose retraction status newly flipped to "retracted".

    ``previous_retraction_state`` is always ``"clear"`` or ``"not_checked"``
    (never ``"retracted"`` -- that candidate would not be in this list) so a
    template can render the "was X, now Y" framing
    `docs/roadmap/web_frd5_freshness_history_design.md` section 4 calls for,
    never a bare color change.
    """

    candidate: CurrentCandidateSource
    previous_retraction_state: str


@dataclass(frozen=True)
class CandidateLevelFreshnessView:
    """WEB-FRD-5 item 7's candidate-level slice: specific works, not just counts.

    Built only when both the current run's candidates and one specific past
    run's full candidate snapshot are available (see
    `build_candidate_freshness` below). Candidates absent from the previous
    run's snapshot are reported only in ``newly_discovered`` -- a candidate
    with no prior record has no "was" retraction state to report, so it is
    never double-counted in ``newly_retracted`` even if it happens to already
    carry a retraction flag on first sight.
    """

    newly_discovered: tuple[CurrentCandidateSource, ...]
    newly_retracted: tuple[RetractedCandidateFreshnessView, ...]


@dataclass(frozen=True)
class DiscoveryFreshnessView:
    """ "Since your last search" facts, run-level plus an optional candidate-level layer.

    ``is_first_recorded_search=True`` means exactly what it says: Core has
    no earlier run tagged with this tracked question, not "no changes were
    found." ``per_candidate_history_available`` and ``candidate_level`` stay
    unset (``False``/``None``) whenever the candidate-level lookup was not
    attempted or did not succeed -- kept explicit, not omitted, so a template
    can render an honest disclosure rather than silently under-delivering the
    design doc's fuller sketch.
    """

    is_first_recorded_search: bool
    prior_run_count: int
    previous_search_run_id: str | None
    previous_created_at: str | None
    previous_completeness: str | None
    candidate_count_delta: int | None
    newly_completed_providers: tuple[str, ...]
    newly_failed_providers: tuple[str, ...]
    per_candidate_history_available: bool = False
    candidate_level: CandidateLevelFreshnessView | None = None


def build_discovery_freshness(
    current: CurrentDiscoveryResultSource,
    history: DiscoveryHistorySource,
) -> DiscoveryFreshnessView:
    """Compare `current`'s just-persisted run against its own prior history.

    `history` is expected to already include `current`'s own run (Core
    persists a run before ever returning it, per the project's
    reproducibility principle) -- it is excluded here by `search_run_id` so
    "prior runs" never double-counts the run that triggered this comparison.
    """

    previous_runs = [run for run in history.runs if run.search_run_id != current.search_run_id]

    if not previous_runs:
        return DiscoveryFreshnessView(
            is_first_recorded_search=True,
            prior_run_count=0,
            previous_search_run_id=None,
            previous_created_at=None,
            previous_completeness=None,
            candidate_count_delta=None,
            newly_completed_providers=(),
            newly_failed_providers=(),
        )

    # `runs` is documented newest-first; the first remaining entry is the
    # most recent prior run once `current` itself is excluded.
    previous = previous_runs[0]

    current_completed = {
        status.provider
        for status in current.provider_statuses
        if status.outcome in _COMPLETED_OUTCOMES
    }
    previous_completed = set(previous.providers_completed)

    return DiscoveryFreshnessView(
        is_first_recorded_search=False,
        prior_run_count=len(previous_runs),
        previous_search_run_id=previous.search_run_id,
        previous_created_at=previous.created_at,
        previous_completeness=previous.completeness,
        candidate_count_delta=len(current.candidates) - previous.candidate_count,
        newly_completed_providers=tuple(sorted(current_completed - previous_completed)),
        newly_failed_providers=tuple(sorted(previous_completed - current_completed)),
    )


def build_candidate_freshness(
    current_candidates: tuple[CurrentCandidateSource, ...],
    previous_candidates: tuple[PastCandidateSource, ...],
) -> CandidateLevelFreshnessView:
    """Diff two runs' full candidate lists -- specific works, not just counts.

    ``current_candidates`` is the just-run search's own
    `discovery_presentation.DiscoveryCandidateView` cards (already computed
    for the main results list -- reused here rather than re-derived).
    ``previous_candidates`` is one specific prior run's full snapshot from
    `ke_client.federated_coverage_report()`. Matching is by Core's own
    `canonical_id` -- Web never re-derives work identity.

    A candidate present now but absent from the previous snapshot is
    "newly discovered." A candidate present in both, not retracted in the
    previous snapshot but retracted now, is "newly retracted" -- computed
    from the same `build_publication_status` rollup WEB-FRD-4 already uses,
    so a candidate the previous run's providers were simply silent about
    (``"not_checked"``) counts as newly retracted exactly like one they
    reported ``False`` for (``"clear"``); either way, the honest fact is
    "we did not know about this retraction before, and we do now."
    """

    previous_by_id: dict[str, PastCandidateSource] = {
        candidate.canonical_id: candidate for candidate in previous_candidates
    }

    newly_discovered = tuple(
        candidate
        for candidate in current_candidates
        if candidate.canonical_id not in previous_by_id
    )

    newly_retracted: list[RetractedCandidateFreshnessView] = []
    for candidate in current_candidates:
        if candidate.publication_status.retraction_state != "retracted":
            continue
        previous_candidate = previous_by_id.get(candidate.canonical_id)
        if previous_candidate is None:
            # Already reported in `newly_discovered` -- no prior "was" state
            # exists to frame a "was X, now retracted" comparison against.
            continue
        previous_status = build_publication_status(previous_candidate.observations)
        if previous_status.retraction_state == "retracted":
            continue
        newly_retracted.append(
            RetractedCandidateFreshnessView(
                candidate=candidate,
                previous_retraction_state=previous_status.retraction_state,
            )
        )

    return CandidateLevelFreshnessView(
        newly_discovered=newly_discovered,
        newly_retracted=tuple(newly_retracted),
    )


__all__ = [
    "CandidateLevelFreshnessView",
    "DiscoveryFreshnessView",
    "RetractedCandidateFreshnessView",
    "build_candidate_freshness",
    "build_discovery_freshness",
]
