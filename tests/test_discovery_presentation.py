from __future__ import annotations

from dataclasses import dataclass

from knowledge_engine_web.discovery_presentation import build_discovery_presentation


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
    candidates: tuple[_Candidate, ...]
    provider_disagreements: tuple[_CandidateDisagreements, ...] | None


def test_build_presentation_keeps_one_card_for_one_canonical_candidate() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="doi:10.1000/example",
                title="A trial",
                doi="10.1000/example",
                publication_year=2026,
                providers=("pubmed", "crossref", "pubmed"),
            ),
        ),
        provider_disagreements=(),
    )

    presentation = build_discovery_presentation(result)

    assert len(presentation.candidates) == 1
    card = presentation.candidates[0]
    assert card.canonical_id == "doi:10.1000/example"
    assert card.providers == ("crossref", "pubmed")
    assert card.disagreement_state == "none_reported"
    assert card.disagreements == ()


def test_build_presentation_preserves_all_reported_provider_assertions() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="doi:10.1000/example",
                title="A trial",
                doi="10.1000/example",
                publication_year=2026,
                providers=("crossref", "openalex"),
            ),
        ),
        provider_disagreements=(
            _CandidateDisagreements(
                canonical_id="doi:10.1000/example",
                disagreements=(
                    _Disagreement(
                        field="publication_year",
                        assertions=(
                            _Assertion("crossref", "cr-1", 2025),
                            _Assertion("openalex", "oa-1", 2026),
                        ),
                    ),
                ),
            ),
        ),
    )

    presentation = build_discovery_presentation(result)

    card = presentation.candidates[0]
    assert card.disagreement_state == "reported"
    assert card.disagreements[0].field == "publication_year"
    assert [(item.provider, item.value) for item in card.disagreements[0].assertions] == [
        ("crossref", 2025),
        ("openalex", 2026),
    ]


def test_build_presentation_keeps_unavailable_distinct_from_no_disagreement() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="pmid:123",
                title="A paper",
                doi=None,
                publication_year=None,
                providers=("pubmed",),
            ),
        ),
        provider_disagreements=None,
    )

    presentation = build_discovery_presentation(result)

    assert presentation.disagreement_data_available is False
    assert presentation.candidates[0].disagreement_state == "unavailable"
    assert presentation.candidates[0].disagreements == ()


def test_build_presentation_does_not_treat_unreported_candidate_as_verified() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="arxiv:2608.00001",
                title="Preprint",
                doi=None,
                publication_year=2026,
                providers=("arxiv", "semantic_scholar"),
            ),
        ),
        provider_disagreements=(),
    )

    presentation = build_discovery_presentation(result)

    card = presentation.candidates[0]
    assert card.disagreement_state == "none_reported"
    assert "verified" not in card.disagreement_state
    assert "agree" not in card.disagreement_state


def test_publication_status_flags_retraction_when_any_provider_reports_it() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="doi:10.1000/example",
                title="A trial",
                doi="10.1000/example",
                publication_year=2026,
                providers=("pubmed", "crossref"),
                observation_flags=(
                    _ObservationFlags(
                        "pubmed", retracted=False, preprint=None, preprint_version=None
                    ),
                    _ObservationFlags(
                        "crossref", retracted=True, preprint=None, preprint_version=None
                    ),
                ),
            ),
        ),
        provider_disagreements=(),
    )

    presentation = build_discovery_presentation(result)

    status = presentation.candidates[0].publication_status
    assert status.retraction_state == "retracted"
    assert [(o.provider, o.retracted) for o in status.observations] == [
        ("pubmed", False),
        ("crossref", True),
    ]


def test_publication_status_distinguishes_clear_from_not_checked() -> None:
    checked = _Result(
        candidates=(
            _Candidate(
                canonical_id="pmid:1",
                title="Checked, not retracted",
                doi=None,
                publication_year=None,
                providers=("pubmed",),
                observation_flags=(
                    _ObservationFlags(
                        "pubmed", retracted=False, preprint=None, preprint_version=None
                    ),
                ),
            ),
        ),
        provider_disagreements=(),
    )
    unchecked = _Result(
        candidates=(
            _Candidate(
                canonical_id="pmid:2",
                title="Never reported",
                doi=None,
                publication_year=None,
                providers=("arxiv",),
                observation_flags=(
                    _ObservationFlags(
                        "arxiv", retracted=None, preprint=None, preprint_version=None
                    ),
                ),
            ),
        ),
        provider_disagreements=(),
    )
    no_observations = _Result(
        candidates=(
            _Candidate(
                canonical_id="pmid:3",
                title="No observation flags at all",
                doi=None,
                publication_year=None,
                providers=("openalex",),
                observation_flags=(),
            ),
        ),
        provider_disagreements=(),
    )

    checked_status = build_discovery_presentation(checked).candidates[0].publication_status
    unchecked_status = build_discovery_presentation(unchecked).candidates[0].publication_status
    no_observations_status = (
        build_discovery_presentation(no_observations).candidates[0].publication_status
    )

    assert checked_status.retraction_state == "clear"
    assert unchecked_status.retraction_state == "not_checked"
    assert no_observations_status.retraction_state == "not_checked"
    assert checked_status.retraction_state != unchecked_status.retraction_state


def test_publication_status_flags_preprint_and_preserves_version() -> None:
    result = _Result(
        candidates=(
            _Candidate(
                canonical_id="arxiv:2608.00001",
                title="A preprint",
                doi=None,
                publication_year=2026,
                providers=("arxiv", "semantic_scholar"),
                observation_flags=(
                    _ObservationFlags("arxiv", retracted=None, preprint=True, preprint_version=2),
                    _ObservationFlags(
                        "semantic_scholar", retracted=None, preprint=None, preprint_version=None
                    ),
                ),
            ),
        ),
        provider_disagreements=(),
    )

    presentation = build_discovery_presentation(result)

    status = presentation.candidates[0].publication_status
    assert status.preprint_state == "preprint"
    assert status.preprint_versions == (2,)
    # Retraction was never reported by either provider for this candidate.
    assert status.retraction_state == "not_checked"
