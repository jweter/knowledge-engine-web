"""Deterministic presentation model for WEB-FRD-3 federated discovery results.

This module is intentionally presentation-only. Core remains authoritative for
canonical work identity and provider-disagreement facts; Web only reshapes the
typed cross-repository contract for rendering. No provider is selected as
preferred and metadata disagreement is never reinterpreted as scientific
contradiction or evidence strength.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

type ObservedValue = str | int | bool


class ProviderAssertionSource(Protocol):
    @property
    def provider(self) -> str: ...
    @property
    def provider_id(self) -> str: ...
    @property
    def value(self) -> ObservedValue: ...


class ProviderDisagreementSource(Protocol):
    @property
    def field(self) -> str: ...
    @property
    def assertions(self) -> tuple[ProviderAssertionSource, ...]: ...


class CandidateDisagreementsSource(Protocol):
    @property
    def canonical_id(self) -> str: ...
    @property
    def disagreements(self) -> tuple[ProviderDisagreementSource, ...]: ...


class ObservationFlagSource(Protocol):
    @property
    def provider(self) -> str: ...
    @property
    def retracted(self) -> bool | None: ...
    @property
    def preprint(self) -> bool | None: ...
    @property
    def preprint_version(self) -> int | None: ...


class CandidateSource(Protocol):
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
    def observation_flags(self) -> tuple[ObservationFlagSource, ...]: ...


class DiscoveryResultSource(Protocol):
    @property
    def candidates(self) -> tuple[CandidateSource, ...]: ...
    @property
    def provider_disagreements(self) -> tuple[CandidateDisagreementsSource, ...] | None: ...


@dataclass(frozen=True)
class ProviderAssertionView:
    """One provider-native metadata value preserved exactly for display."""

    provider: str
    provider_id: str
    value: ObservedValue


@dataclass(frozen=True)
class ProviderDisagreementView:
    """One Core-reported bibliographic/provider metadata conflict."""

    field: str
    assertions: tuple[ProviderAssertionView, ...]


@dataclass(frozen=True)
class ProviderObservationFlagView:
    """One provider's retraction/preprint observation, preserved exactly.

    ``None`` means the provider did not report the flag -- distinct from the
    provider explicitly reporting ``False``. AI does not merge, vote on, or
    pick an authoritative provider observation, and neither does this view.
    """

    provider: str
    retracted: bool | None
    preprint: bool | None
    preprint_version: int | None


@dataclass(frozen=True)
class PublicationStatusView:
    """WEB-FRD-4 rollup: a candidate's retraction/preprint status.

    ``retraction_state`` and ``preprint_state`` are each one of:

    - ``"retracted"`` / ``"preprint"`` -- at least one provider explicitly
      reported the flag as ``True``.
    - ``"clear"`` -- at least one provider explicitly reported the flag as
      ``False`` and none reported ``True``. This is a provider self-report,
      not an independent editorial check.
    - ``"not_checked"`` -- no provider reported this flag at all. Distinct
      from ``"clear"``: absence of a report is not evidence of absence of a
      retraction or preprint relationship.

    ``observations`` preserves every provider's raw flags, unmerged, for
    inspection -- the rollup drives visual treatment, it does not replace the
    underlying per-provider facts.
    """

    retraction_state: str
    preprint_state: str
    preprint_versions: tuple[int, ...]
    observations: tuple[ProviderObservationFlagView, ...]


@dataclass(frozen=True)
class DiscoveryCandidateView:
    """One Core-deduplicated work card ready for deterministic rendering."""

    canonical_id: str
    title: str
    doi: str | None
    publication_year: int | None
    providers: tuple[str, ...]
    disagreement_state: str
    disagreements: tuple[ProviderDisagreementView, ...]
    publication_status: PublicationStatusView


@dataclass(frozen=True)
class DiscoveryPresentation:
    """WEB-FRD-3 card model plus run-level disagreement availability state."""

    candidates: tuple[DiscoveryCandidateView, ...]
    disagreement_data_available: bool


def _build_publication_status(
    flags: tuple[ObservationFlagSource, ...],
) -> PublicationStatusView:
    """Roll up per-provider retraction/preprint flags without voting on them.

    ``None`` values (provider did not report the flag) are excluded from the
    "did anyone report True/False" scan so a candidate with zero reporting
    providers correctly lands on ``"not_checked"`` rather than being
    miscounted as ``"clear"``.
    """

    retracted_reports = [flag.retracted for flag in flags if flag.retracted is not None]
    if any(retracted_reports):
        retraction_state = "retracted"
    elif retracted_reports:
        retraction_state = "clear"
    else:
        retraction_state = "not_checked"

    preprint_reports = [flag.preprint for flag in flags if flag.preprint is not None]
    if any(preprint_reports):
        preprint_state = "preprint"
    elif preprint_reports:
        preprint_state = "clear"
    else:
        preprint_state = "not_checked"

    preprint_versions = tuple(
        flag.preprint_version for flag in flags if flag.preprint_version is not None
    )

    observations = tuple(
        ProviderObservationFlagView(
            provider=flag.provider,
            retracted=flag.retracted,
            preprint=flag.preprint,
            preprint_version=flag.preprint_version,
        )
        for flag in flags
    )

    return PublicationStatusView(
        retraction_state=retraction_state,
        preprint_state=preprint_state,
        preprint_versions=preprint_versions,
        observations=observations,
    )


def build_discovery_presentation(result: DiscoveryResultSource) -> DiscoveryPresentation:
    """Map typed AI discovery state to Web cards without adding interpretation.

    ``provider_disagreements is None`` means the upstream snapshot predates or
    omitted the public disagreement contract. That state remains distinguishable
    from an available report containing zero conflicts. Provider order is
    normalized for stable presentation only; it carries no ranking semantics.
    """

    disagreement_index: dict[str, tuple[ProviderDisagreementView, ...]] = {}
    disagreement_data_available = result.provider_disagreements is not None

    if result.provider_disagreements is not None:
        for candidate_report in result.provider_disagreements:
            disagreement_index[candidate_report.canonical_id] = tuple(
                ProviderDisagreementView(
                    field=disagreement.field,
                    assertions=tuple(
                        ProviderAssertionView(
                            provider=assertion.provider,
                            provider_id=assertion.provider_id,
                            value=assertion.value,
                        )
                        for assertion in disagreement.assertions
                    ),
                )
                for disagreement in candidate_report.disagreements
            )

    cards: list[DiscoveryCandidateView] = []
    for candidate in result.candidates:
        disagreements = disagreement_index.get(candidate.canonical_id, ())
        if not disagreement_data_available:
            state = "unavailable"
        elif disagreements:
            state = "reported"
        else:
            state = "none_reported"

        cards.append(
            DiscoveryCandidateView(
                canonical_id=candidate.canonical_id,
                title=candidate.title,
                doi=candidate.doi,
                publication_year=candidate.publication_year,
                providers=tuple(sorted(set(candidate.providers))),
                disagreement_state=state,
                disagreements=disagreements,
                publication_status=_build_publication_status(candidate.observation_flags),
            )
        )

    return DiscoveryPresentation(
        candidates=tuple(cards),
        disagreement_data_available=disagreement_data_available,
    )


__all__ = [
    "DiscoveryCandidateView",
    "DiscoveryPresentation",
    "ProviderAssertionView",
    "ProviderDisagreementView",
    "ProviderObservationFlagView",
    "PublicationStatusView",
    "build_discovery_presentation",
]
