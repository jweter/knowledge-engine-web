from __future__ import annotations

from knowledge_engine_web.evidence_intelligence import ClaimConfidence, EvidenceQuality
from knowledge_engine_web.evidence_reader import EvidenceRecordDetail
from knowledge_engine_web.synthesis import build_synthesis_prompt, synthesize_answer


class _FakeLLM:
    def __init__(self, response: str = "Synthesized answer.") -> None:
        self.response = response
        self.prompts: list[str] = []
        self.max_tokens_seen: list[int] = []

    def generate(self, prompt: str, *, max_tokens: int = 400) -> str:
        self.prompts.append(prompt)
        self.max_tokens_seen.append(max_tokens)
        return self.response


def _evidence(
    *, claim_text: str | None = "Semaglutide reduced body weight."
) -> EvidenceRecordDetail:
    return EvidenceRecordDetail(
        evidence_record_id="ev-1",
        research_question=None,
        claim_text=claim_text,
        evidence_direction="supports",
        study_type="randomized_controlled_trial",
        source_type=None,
        source_title=None,
        source_doi="10.1000/example",
        population=None,
        intervention=None,
        comparator=None,
        outcome=None,
        result_summary="Body weight reduced by 10.2% versus 1.5% with placebo.",
        short_source_excerpt=None,
        limitations=[],
        uncertainty_notes=None,
        confidence_note=None,
        extraction_method="manual_human_review",
        extraction_status="draft_manual_prototype",
        review_status="reviewed",
        review_checklist={"source_verified": True},
    )


def _intelligence() -> dict[str, object]:
    return {
        "quality": EvidenceQuality(
            evidence_record_id="ev-1",
            score=94,
            study_design_tier="randomized_controlled_trial",
            manually_reviewed=True,
            extraction_tier="manual",
        ),
        "confidence": ClaimConfidence(score=89, reliability="moderate", mean_evidence_quality=94.0),
    }


def _results(
    *, claim_text: str | None = "Semaglutide reduced body weight.", with_intelligence: bool = True
) -> list[dict[str, object]]:
    return [
        {
            "paper": None,
            "evidence_entries": [
                {
                    "evidence": _evidence(claim_text=claim_text),
                    "intelligence": _intelligence() if with_intelligence else None,
                }
            ],
        }
    ]


def test_build_synthesis_prompt_includes_evidence_record_id_and_claim_text() -> None:
    prompt = build_synthesis_prompt("does semaglutide reduce body weight", _results())

    assert "does semaglutide reduce body weight" in prompt
    assert "[ev-1]" in prompt
    assert "Semaglutide reduced body weight." in prompt
    assert "Body weight reduced by 10.2%" in prompt
    assert "Claim Confidence: 89/100" in prompt
    assert "cite" in prompt.lower()


def test_build_synthesis_prompt_skips_records_without_claim_text() -> None:
    prompt = build_synthesis_prompt("q", _results(claim_text=None))

    assert "ev-1" not in prompt
    assert "Answer:" in prompt  # still well-formed with an empty evidence section


def test_build_synthesis_prompt_omits_intelligence_when_none() -> None:
    prompt = build_synthesis_prompt("q", _results(with_intelligence=False))

    assert "[ev-1]" in prompt
    # The system instructions mention "Claim Confidence" in prose; only the
    # per-record "Claim Confidence: N/100" block should be absent.
    assert "Claim Confidence:" not in prompt


def test_synthesize_answer_calls_the_llm_with_the_grounded_prompt() -> None:
    llm = _FakeLLM(response="Semaglutide reduces body weight [ev-1].")

    answer = synthesize_answer("does semaglutide reduce body weight", _results(), llm)

    assert answer == "Semaglutide reduces body weight [ev-1]."
    assert len(llm.prompts) == 1
    assert "[ev-1]" in llm.prompts[0]


def test_synthesize_answer_returns_none_without_calling_the_llm_when_no_evidence() -> None:
    llm = _FakeLLM()

    answer = synthesize_answer("q", [], llm)

    assert answer is None
    assert llm.prompts == []


def test_synthesize_answer_returns_none_when_no_record_has_claim_text() -> None:
    llm = _FakeLLM()

    answer = synthesize_answer("q", _results(claim_text=None), llm)

    assert answer is None
    assert llm.prompts == []
