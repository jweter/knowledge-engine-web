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
  corrections/retractions are highlighted" -- for all four independent
  publication-status flags WEB-FRD-4 now renders (retraction, correction,
  expression of concern, withdrawal), not retraction alone. Core's
  `ProviderObservation.corrected`/`.expression_of_concern`/`.withdrawn` and
  `knowledge-engine-ai`'s matching parsing (both landed 2026-08-20/21, the
  same dependency this module already pins) made this the last honest gap
  in item 7; closing it here requires no further Core or AI change.

Candidate-level diffing is best-effort and additive: a run persisted before
Core's candidate-snapshot follow-up existed reports an honest empty
candidate list (Core/AI's own contract, not this module's approximation),
and a failure fetching the previous run's snapshot degrades to the run-level
view alone (`DiscoveryFreshnessView.candidate_level` stays `None`) rather
than failing the whole "Since your last search" section. This is the same
discipline this project has already applied elsewhere: render exactly what
is durably known, and say plainly what is not yet available, rather than
approximating it.

That same honest-empty-list contract means a point lookup cannot be trusted
purely because it returned successfully: a run that predates candidate-
snapshot persistence still reports its real, nonzero aggregate
`candidate_count` alongside an empty `candidates` tuple, which is
indistinguishable from a genuinely candidate-free run unless the two are
cross-checked. `candidate_snapshot_is_usable` below performs that check;
callers (`main.py`'s `/discover` route) must use it to decide whether the
candidate-level layer is actually available, the same way they already
treat a failed lookup as "stay at the run-level-only state".
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


class PastRunCandidateSnapshotSource(Protocol):
    """One past run's point-lookup result, as `ke_client.FederatedCoverageReportResult`."""

    @property
    def coverage(self) -> SearchCoverageReportSource: ...
    @property
    def candidates(self) -> tuple[PastCandidateSource, ...]: ...


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
class FlaggedCandidateFreshnessView:
    """One candidate whose publication-status flag newly flipped to its affirmative state.

    Shared by all four independent, non-exclusive flags WEB-FRD-4 renders
    (retraction, correction, expression of concern, withdrawal) -- the "was
    clear/not_checked, now flagged" shape is identical for each, so one view
    type serves all four; which flag is meant is determined by which
    `CandidateLevelFreshnessView` tuple an instance lives in, exactly as
    `PublicationStatusView` already tracks the four states as four
    independent fields rather than one collapsed status.

    ``previous_state`` is always ``"clear"`` or ``"not_checked"`` (never the
    flag's own affirmative value -- that candidate would not be in this
    list) so a template can render the "was X, now Y" framing
    `docs/roadmap/web_frd5_freshness_history_design.md` section 4 calls for,
    never a bare color change.
    """

    candidate: CurrentCandidateSource
    previous_state: str


@dataclass(frozen=True)
class CandidateLevelFreshnessView:
    """WEB-FRD-5 item 7's candidate-level slice: specific works, not just counts.

    Built only when both the current run's candidates and one specific past
    run's full candidate snapshot are available (see
    `build_candidate_freshness` below). Candidates absent from the previous
    run's snapshot are reported only in ``newly_discovered`` -- a candidate
    with no prior record has no "was" state to report, so it is never
    double-counted in one of the ``newly_*`` flag tuples even if it happens
    to already carry that flag on first sight.
    """

    newly_discovered: tuple[CurrentCandidateSource, ...]
    newly_retracted: tuple[FlaggedCandidateFreshnessView, ...]
    newly_corrected: tuple[FlaggedCandidateFreshnessView, ...]
    newly_expression_of_concern: tuple[FlaggedCandidateFreshnessView, ...]
    newly_withdrawn: tuple[FlaggedCandidateFreshnessView, ...]


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


def candidate_snapshot_is_usable(snapshot: PastRunCandidateSnapshotSource) -> bool:
    """True when `snapshot`'s candidate list can be trusted as a complete baseline.

    A point lookup that predates Core's candidate-snapshot persistence (Core
    PR #394) still reports its run's real, historical aggregate
    `coverage.candidate_count`, but an honest empty `candidates` tuple --
    there is no per-candidate data to return, not "this run found zero
    candidates". Without this check, that empty tuple is indistinguishable
    from a genuinely candidate-free prior run: every current candidate would
    be misreported as newly discovered against a baseline that was never
    actually observed.

    A snapshot is only usable when its own `candidates` tuple is consistent
    with its own `coverage.candidate_count` -- either some candidates were
    actually returned, or the run legitimately had none. Any other
    combination (nonzero `candidate_count`, empty `candidates`) means the
    snapshot could not be trusted, and the caller must fall back to the
    run-level-only comparison `docs/roadmap/web_frd5_freshness_history_design.md`
    already documents for a failed or unavailable candidate-level lookup.
    """

    return len(snapshot.candidates) > 0 or snapshot.coverage.candidate_count == 0


#: The four independent, non-exclusive `PublicationStatusView` flags this
#: diff covers, each as (state field name, that field's affirmative value).
#: Matches `discovery_presentation.build_publication_status`'s own four
#: rollups exactly -- preprint is deliberately excluded: it is a version
#: relationship, not a publication-integrity warning, and this project has
#: no "newly became a preprint" product need the way it does for these four.
_FLAG_SPECS: tuple[tuple[str, str], ...] = (
    ("retraction_state", "retracted"),
    ("correction_state", "corrected"),
    ("expression_of_concern_state", "expression_of_concern"),
    ("withdrawal_state", "withdrawn"),
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
    "newly discovered." A candidate present in both runs whose retraction,
    correction, expression-of-concern, or withdrawal state newly flipped to
    its affirmative value is reported in the matching ``newly_*`` tuple --
    computed from the same `build_publication_status` rollup WEB-FRD-4
    already uses, so a candidate the previous run's providers were simply
    silent about (``"not_checked"``) counts as newly flagged exactly like
    one they explicitly reported ``False`` for (``"clear"``); either way,
    the honest fact is "we did not know about this before, and we do now."
    The four flags are independent and non-exclusive (a candidate can land
    in more than one ``newly_*`` tuple at once), matching
    `PublicationStatusView`'s own refusal to collapse them into one status.
    """

    previous_by_id: dict[str, PastCandidateSource] = {
        candidate.canonical_id: candidate for candidate in previous_candidates
    }

    newly_discovered = tuple(
        candidate
        for candidate in current_candidates
        if candidate.canonical_id not in previous_by_id
    )

    newly_flagged: dict[str, list[FlaggedCandidateFreshnessView]] = {
        state_attr: [] for state_attr, _ in _FLAG_SPECS
    }
    for candidate in current_candidates:
        previous_candidate = previous_by_id.get(candidate.canonical_id)
        if previous_candidate is None:
            # Already reported in `newly_discovered` -- no prior "was" state
            # exists to frame a "was X, now flagged" comparison against.
            continue
        previous_status = build_publication_status(previous_candidate.observations)
        for state_attr, affirmative_value in _FLAG_SPECS:
            if getattr(candidate.publication_status, state_attr) != affirmative_value:
                continue
            previous_state = getattr(previous_status, state_attr)
            if previous_state == affirmative_value:
                continue
            newly_flagged[state_attr].append(
                FlaggedCandidateFreshnessView(candidate=candidate, previous_state=previous_state)
            )

    return CandidateLevelFreshnessView(
        newly_discovered=newly_discovered,
        newly_retracted=tuple(newly_flagged["retraction_state"]),
        newly_corrected=tuple(newly_flagged["correction_state"]),
        newly_expression_of_concern=tuple(newly_flagged["expression_of_concern_state"]),
        newly_withdrawn=tuple(newly_flagged["withdrawal_state"]),
    )


__all__ = [
    "CandidateLevelFreshnessView",
    "DiscoveryFreshnessView",
    "FlaggedCandidateFreshnessView",
    "build_candidate_freshness",
    "build_discovery_freshness",
    "candidate_snapshot_is_usable",
]
