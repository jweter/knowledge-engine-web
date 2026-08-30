"""Deterministic presentation model for WEB-GQR-2's Research Copilot coverage panel.

`/ask`'s Research mode already renders AI's deterministic `research_state`
(WEB-GQR-1) and a promoted-Evidence-Record count. What that view does not yet
show is *why* -- which providers were attempted and how they degraded, how
many discovery candidates existed versus how many were ever acquired versus
how many actually became Evidence Records, and whether a budget/adequacy
short-circuit stopped further breadth. Those facts already exist on AI's
`DiscoveryAugmentationResult`/`GroundedCompletionResult` (see
`ai_orchestration.WebResearchResult.discovery`/`.grounded_completion`); this
module only reshapes them for rendering, the same presentation-only contract
`discovery_presentation.py` documents for `/discover`.

This module is intentionally presentation-only: it invents no quality signal
from these counts (a low acquisition count is not "bad evidence", it may be
a scientifically thin literature or a deliberate adequacy stop) and it never
claims a step ran when the underlying result says it was skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from knowledge_engine_web.discovery_presentation import (
    provider_outcome_label,
    provider_status_css_class,
)


class ProviderStatusSource(Protocol):
    @property
    def provider(self) -> str: ...
    @property
    def outcome(self) -> str: ...
    @property
    def result_count(self) -> int: ...
    @property
    def reason(self) -> str | None: ...


class FederatedDiscoverySource(Protocol):
    @property
    def search_run_id(self) -> str: ...
    @property
    def completeness(self) -> str: ...
    @property
    def provider_statuses(self) -> tuple[ProviderStatusSource, ...]: ...
    @property
    def candidates(self) -> tuple[object, ...]: ...
    @property
    def search_run_created_at(self) -> str | None: ...


class DiscoveryAugmentationSource(Protocol):
    @property
    def triggered(self) -> bool: ...
    @property
    def trigger_reason(self) -> str: ...
    @property
    def evidence_record_coverage(self) -> int: ...
    @property
    def federated_discovery(self) -> FederatedDiscoverySource | None: ...
    @property
    def federated_discovery_attempted(self) -> bool: ...
    @property
    def federated_discovery_error(self) -> str | None: ...
    @property
    def acquisition_plan_attempted(self) -> bool: ...
    @property
    def acquisition_plan_skipped_reason(self) -> str | None: ...
    @property
    def acquisition_plan_error(self) -> str | None: ...


class AcquisitionRouteSource(Protocol):
    @property
    def route(self) -> str: ...
    @property
    def attempted(self) -> bool: ...
    @property
    def candidate_ids(self) -> tuple[str, ...]: ...
    @property
    def persisted_count(self) -> int: ...
    @property
    def reused_count(self) -> int: ...
    @property
    def error(self) -> str | None: ...
    @property
    def skipped_reason(self) -> str | None: ...


class GroundedCompletionSource(Protocol):
    @property
    def attempted(self) -> bool: ...
    @property
    def already_indexed_paper_ids(self) -> tuple[int, ...]: ...
    @property
    def acquisition_routes(self) -> tuple[AcquisitionRouteSource, ...]: ...
    @property
    def draft_item_count(self) -> int: ...
    @property
    def classified_item_count(self) -> int: ...
    @property
    def staged_record_ids(self) -> tuple[str, ...]: ...
    @property
    def grounded_record_ids(self) -> tuple[str, ...]: ...
    @property
    def promoted_record_ids(self) -> tuple[str, ...]: ...
    @property
    def grounding_failures(self) -> tuple[str, ...]: ...
    @property
    def extraction_error(self) -> str | None: ...
    @property
    def reretrieval_error(self) -> str | None: ...
    @property
    def skipped_reason(self) -> str | None: ...


@dataclass(frozen=True)
class ProviderCoverageRow:
    """One provider's federated-discovery outcome, same labels `/discover` uses."""

    provider: str
    label: str
    css_class: str
    reason: str | None
    result_count: int


@dataclass(frozen=True)
class AcquisitionRouteRow:
    """One GQR-4 acquisition route's durable outcome.

    `route` is one of `pmc_oa`/`europe_pmc_oa`/`core`/`unpaywall`.
    """

    route: str
    attempted: bool
    candidate_count: int
    persisted_count: int
    reused_count: int
    error: str | None
    skipped_reason: str | None


@dataclass(frozen=True)
class ResearchCoveragePanel:
    """WEB-GQR-2: provider/acquisition/promotion totals, distinct from citation-level evidence.

    Deliberately keeps three counts separate rather than collapsing them into
    one number: `candidate_count` (federated-discovery leads -- never
    evidence), the acquisition-route persisted/reused counts (papers Core
    actually holds), and `promoted_record_count` (the only count that ever
    reaches synthesis). Collapsing these would hide exactly the funnel loss
    BT-2 exists to make visible.
    """

    # Federated discovery
    discovery_triggered: bool
    trigger_reason: str
    indexed_evidence_record_coverage: int
    federated_discovery_attempted: bool
    federated_discovery_error: str | None
    search_run_id: str | None
    search_run_created_at: str | None
    completeness: str | None
    candidate_count: int
    provider_rows: tuple[ProviderCoverageRow, ...]

    # Acquisition planning
    acquisition_plan_attempted: bool
    acquisition_plan_skipped_reason: str | None
    acquisition_plan_error: str | None

    # GQR-4/GQR-5 grounded completion
    grounded_completion_attempted: bool
    grounded_completion_skipped_reason: str | None
    already_indexed_paper_count: int
    acquisition_routes: tuple[AcquisitionRouteRow, ...]
    draft_item_count: int
    classified_item_count: int
    staged_record_count: int
    grounded_record_count: int
    promoted_record_count: int
    grounding_failure_count: int
    extraction_error: str | None
    reretrieval_error: str | None


def _provider_row(status: ProviderStatusSource) -> ProviderCoverageRow:
    return ProviderCoverageRow(
        provider=status.provider,
        label=provider_outcome_label(status.outcome),
        css_class=provider_status_css_class(status.outcome),
        reason=status.reason,
        result_count=status.result_count,
    )


def _acquisition_route_row(route: AcquisitionRouteSource) -> AcquisitionRouteRow:
    return AcquisitionRouteRow(
        route=route.route,
        attempted=route.attempted,
        candidate_count=len(route.candidate_ids),
        persisted_count=route.persisted_count,
        reused_count=route.reused_count,
        error=route.error,
        skipped_reason=route.skipped_reason,
    )


def build_research_coverage_panel(
    discovery: DiscoveryAugmentationSource | None,
    grounded_completion: GroundedCompletionSource | None,
) -> ResearchCoveragePanel | None:
    """Build the coverage panel from one Research Copilot run's already-recorded facts.

    Returns `None` only when discovery was never evaluated for this run (a
    caller that omitted `discovery_policy` entirely -- not Web's own
    production configuration, but preserved here so a bare `run_research_question`
    result never renders a fabricated panel). A `discovery` that was
    evaluated but not triggered (indexed coverage was already adequate)
    still returns a panel explaining that.
    """

    if discovery is None:
        return None

    federated = discovery.federated_discovery
    provider_rows = (
        tuple(_provider_row(status) for status in federated.provider_statuses)
        if federated is not None
        else ()
    )

    acquisition_routes = (
        tuple(_acquisition_route_row(route) for route in grounded_completion.acquisition_routes)
        if grounded_completion is not None
        else ()
    )

    return ResearchCoveragePanel(
        discovery_triggered=discovery.triggered,
        trigger_reason=discovery.trigger_reason,
        indexed_evidence_record_coverage=discovery.evidence_record_coverage,
        federated_discovery_attempted=discovery.federated_discovery_attempted,
        federated_discovery_error=discovery.federated_discovery_error,
        search_run_id=federated.search_run_id if federated is not None else None,
        search_run_created_at=federated.search_run_created_at if federated is not None else None,
        completeness=federated.completeness if federated is not None else None,
        candidate_count=len(federated.candidates) if federated is not None else 0,
        provider_rows=provider_rows,
        acquisition_plan_attempted=discovery.acquisition_plan_attempted,
        acquisition_plan_skipped_reason=discovery.acquisition_plan_skipped_reason,
        acquisition_plan_error=discovery.acquisition_plan_error,
        grounded_completion_attempted=(
            grounded_completion.attempted if grounded_completion is not None else False
        ),
        grounded_completion_skipped_reason=(
            grounded_completion.skipped_reason if grounded_completion is not None else None
        ),
        already_indexed_paper_count=(
            len(grounded_completion.already_indexed_paper_ids)
            if grounded_completion is not None
            else 0
        ),
        acquisition_routes=acquisition_routes,
        draft_item_count=(
            grounded_completion.draft_item_count if grounded_completion is not None else 0
        ),
        classified_item_count=(
            grounded_completion.classified_item_count if grounded_completion is not None else 0
        ),
        staged_record_count=(
            len(grounded_completion.staged_record_ids) if grounded_completion is not None else 0
        ),
        grounded_record_count=(
            len(grounded_completion.grounded_record_ids) if grounded_completion is not None else 0
        ),
        promoted_record_count=(
            len(grounded_completion.promoted_record_ids) if grounded_completion is not None else 0
        ),
        grounding_failure_count=(
            len(grounded_completion.grounding_failures) if grounded_completion is not None else 0
        ),
        extraction_error=(
            grounded_completion.extraction_error if grounded_completion is not None else None
        ),
        reretrieval_error=(
            grounded_completion.reretrieval_error if grounded_completion is not None else None
        ),
    )


__all__ = [
    "AcquisitionRouteRow",
    "ProviderCoverageRow",
    "ResearchCoveragePanel",
    "build_research_coverage_panel",
]
