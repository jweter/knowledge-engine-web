"""WEB-FRD-5 (research freshness history): honest, presentation-only diffing.

This module deliberately computes only what Core+AI's current contract can
actually support. `docs/roadmap/web_frd5_freshness_history_design.md`
sketches a richer comparison -- specific newly discovered works, specific
newly retracted candidates -- but that requires a *per-candidate* historical
record for each past run. `ke federated-discover-history` (and this
project's `ke_client.federated_discover_history()`) deliberately returns
only each past run's aggregate `SearchCoverageReport` (candidate count,
provider outcomes, completeness, timestamp) -- not the candidate list
itself, and no wrapper exists for a `--output`-less
`federated-coverage-report` point lookup either (see that AI commit's own
rationale: adding one would mean scraping console text). So a work-level or
retraction-level diff is not yet an honest thing to render; only
run-level facts are.

This is the same discipline this project has already applied elsewhere
(WEB-FRD-4 leaving correction/withdrawal states out of scope until Core
carries them): render exactly what is durably known, and say plainly what
is not yet available, rather than approximating it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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


@dataclass(frozen=True)
class DiscoveryFreshnessView:
    """Run-level (never candidate-level) "since your last search" facts.

    ``is_first_recorded_search=True`` means exactly what it says: Core has
    no earlier run tagged with this tracked question, not "no changes were
    found." ``per_candidate_history_available`` is always ``False`` today --
    kept explicit, not omitted, so a template can render an honest disclosure
    rather than silently under-delivering the design doc's fuller sketch.
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


__all__ = ["DiscoveryFreshnessView", "build_discovery_freshness"]
