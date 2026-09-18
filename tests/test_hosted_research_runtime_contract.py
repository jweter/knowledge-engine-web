from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DOC = ROOT / "docs" / "hosted_research_runtime.md"


def test_monster_runtime_acceptance_contract_captures_exact_component_identity_and_evidence() -> None:
    text = RUNTIME_DOC.read_text(encoding="utf-8")
    required = [
        "Core commit SHA",
        "Web commit SHA",
        "AI commit SHA",
        "session ID",
        "time to first grounded information",
        "time to final report",
        "acquisition/extraction funnel",
        "provider coverage/degradation",
        "promoted Evidence Record IDs",
        "final ResearchState",
        "every structured conclusion row and certainty",
        "explicit missing approximately-one-year direct evidence",
        "counter/null evidence",
        "resolved citations and evidence-detail navigation",
    ]
    for item in required:
        assert item in text
