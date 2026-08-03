"""LLM-grounded synthesis for `/ask`: one narrative paragraph, strictly grounded in retrieval.

Mirrors `knowledge-engine-ai`'s own `knowledge_engine_ai.synthesis` module
(same system instructions, same "narrate already-computed signals, never
invent one" discipline -- see that module's docstring and
`docs/ai_design.md`'s "Decision: local LLM" section) rather than importing
it, for the same reason `knowledge_engine_web.llm` gives. The prompt this
module builds contains nothing but fields `/ask`'s own retrieval and
`evidence_intelligence.py` already computed (`claim_text`,
`result_summary`, Evidence Quality/Claim Confidence) -- the model is told,
explicitly, to use only that content and to cite each claim's
`evidence_record_id`, never to introduce a fact, a number, or a confidence
rating this project has not already computed. This is narration of
existing signals, not a new judgment.
"""

from __future__ import annotations

from knowledge_engine_web.evidence_intelligence import ClaimConfidence, EvidenceQuality
from knowledge_engine_web.evidence_reader import EvidenceRecordDetail
from knowledge_engine_web.llm import LocalLLM

_SYSTEM_INSTRUCTIONS = (
    "You are a careful research assistant summarizing evidence for a clinician or researcher. "
    "Answer the question using ONLY the evidence listed below -- never add a fact, statistic, or "
    "claim that is not present in it. Cite the evidence_record_id in square brackets after every "
    "claim you state, e.g. [ev-example-001]. If the evidence is insufficient, contradictory, or "
    "absent, say so plainly instead of guessing. Do not invent a confidence score of your own; "
    "if a Claim Confidence number is given, you may mention it, but never compute a new one."
)


def build_synthesis_prompt(question: str, results: list[dict[str, object]]) -> str:
    """Assemble the strict, evidence-only prompt for a local LLM.

    Only evidence entries that actually have `claim_text` are included --
    a matched paper with zero evidence records, or one whose records
    never got a claim extracted, contributes nothing to ground on, so it
    is left out rather than padding the prompt with retrieval metadata
    the model has no evidence-based use for.
    """

    evidence_blocks = _evidence_blocks(results)

    lines = [_SYSTEM_INSTRUCTIONS, "", f"Question: {question}", "", "Evidence:"]
    lines.extend(evidence_blocks)
    lines.append("")
    lines.append("Answer:")
    return "\n".join(lines)


def synthesize_answer(
    question: str, results: list[dict[str, object]], llm: LocalLLM, *, max_tokens: int = 400
) -> str | None:
    """Return a grounded narrative answer, or `None` if there is no evidence to ground on.

    Deliberately skips calling the model at all when zero evidence
    entries have `claim_text` -- nothing to narrate, and asking a model
    to answer from an empty evidence list only invites it to guess.
    """

    if not _evidence_blocks(results):
        return None

    prompt = build_synthesis_prompt(question, results)
    return llm.generate(prompt, max_tokens=max_tokens)


def _evidence_blocks(results: list[dict[str, object]]) -> list[str]:
    blocks = []
    for item in results:
        entries = item["evidence_entries"]
        assert isinstance(entries, list)
        for entry in entries:
            evidence = entry["evidence"]
            assert isinstance(evidence, EvidenceRecordDetail)
            if not evidence.claim_text or not evidence.evidence_record_id:
                continue
            block = f"[{evidence.evidence_record_id}] {evidence.claim_text}"
            if evidence.result_summary:
                block += f" Result: {evidence.result_summary}"
            intelligence = entry["intelligence"]
            if intelligence is not None:
                assert isinstance(intelligence, dict)
                quality = intelligence["quality"]
                confidence = intelligence["confidence"]
                assert isinstance(quality, EvidenceQuality)
                assert isinstance(confidence, ClaimConfidence)
                confidence_text = (
                    f"{confidence.score}/100"
                    if confidence.score is not None
                    else "not yet assessable"
                )
                block += (
                    f" Evidence Quality: {quality.score}/100. "
                    f"Claim Confidence: {confidence_text} ({confidence.reliability})."
                )
            blocks.append(block)
    return blocks
