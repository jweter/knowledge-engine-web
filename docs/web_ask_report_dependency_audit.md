# Web Ask / Research Report dependency audit

Status: characterization of `main` at `9b5a61e539d4d482de3b3f4822c277abfa9e3cf3` (2026-11-02). This is **not** an online-only implementation or a claim of Product Reality acceptance. Authority: `docs/OWNER_APPROVED_ROADMAP_2026-10-25.md`, first slice.

## Mandatory local inputs in the current path

| Current entry point | Dependency today | Source / regression evidence |
| --- | --- | --- |
| `GET /ask?q=...` with a nonblank question, including `quick=1` | Calls `_engine()` and `answer_retrieval()` against Core's indexed SQLite database **before** deciding whether Research runs. No corpus-free fallback exists in this route. | `knowledge_engine_web/main.py::ask`, `_engine`, `knowledge_engine_web/retrieval.py`; `tests/test_web_ask_report_dependency_audit.py` |
| Default `/ask` Research capability | Requires a nonblank `KE_WEB_LLM_MODEL`; without it, capability is `model_not_configured`. The page honestly falls back to indexed retrieval rather than starting online research. | `knowledge_engine_web/ai_orchestration.py::evaluate_ai_capability`; `tests/test_ai_orchestration.py`, new audit regression |
| Default `/ask` Research capability | Requires an existing `KE_WEB_SOURCES_PATH` (pre-existing local corpus metadata); without it, `sources_unavailable`. | `ai_orchestration.py::evaluate_ai_capability`; `tests/test_ai_orchestration.py`, new audit regression |
| Default `/ask` Research capability | Requires a writable `KE_WEB_EVIDENCE_RECORDS_PATH`; without it, `evidence_unavailable`. Research may promote acquired evidence to this durable file. | `ai_orchestration.py::evaluate_ai_capability`; `tests/test_ai_orchestration.py`, new audit regression |
| Research execution once admitted | Passes both local paths into `run_research_question` and constructs `OllamaLLM` for synthesis. Structured report projection also constructs `OllamaLLM`. | `ai_orchestration.py::run_ai_orchestration`, `_build_research_report_projection`; `knowledge_engine_ai/copilot/run_research_question.py` |
| Research capability, beyond corpus/model | Also requires a resolvable Core `ke` executable, usable acquired-paper destination, session storage, and discovery capability; optional command-surface preflight can be enabled. These are **separate** prerequisites, not evidence that the default flow is corpus-free. | `ai_orchestration.py::evaluate_ai_capability`, `tests/test_ai_orchestration.py` |

`Settings` declares `sources_path`, `evidence_records_path`, and `llm_model` optional at configuration parsing time, but the **Research capability gate** makes all three mandatory. Do not confuse configuration optionality with working Research availability. `quick=1` bypasses synthesis, **not** the indexed database. `/discover` is a separate opt-in provider workflow, not a replacement for `/ask`'s Research prerequisites.

## Migration boundary

The next `web-one-request-report-orchestration` slice must consume the versioned online-evidence contract from Core and the AI online-evidence adapter through supported boundaries. It should expose a separately guarded, bounded, one-question route or equivalent explicitly approved migration; preserve current `/ask` compatibility until end-to-end evidence proves the new default. It must not require a pre-ingested corpus or Ollama for the new default, must avoid persistent bulk storage, and must preserve provenance, uncertainty, unavailable-source disclosure, error states, and cleanup.

Update the characterization tests **deliberately** when each old prerequisite is removed; a passing fake transport is not evidence of a working online report. Full native preflight, fresh CI/review, and real online-source Product Reality remain separate gates.
