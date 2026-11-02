# `/ask` research report: mandatory dependency audit

Status: audit of **current** behaviour at `6042774`, written as the first spec task for the
`web-one-request-research-report` capability. It describes what is true today; it does not change behaviour and does
not claim that model-free research works. Every dependency below is pinned by a test in
`tests/test_report_dependency_characterization.py` (or by the existing `tests/test_ai_orchestration.py`).
When a later slice removes a dependency it must change the matching test deliberately.

## How a report is gated

`evaluate_ai_capability(settings)` (`knowledge_engine_web/ai_orchestration.py:191`) checks prerequisites **in this order**
and returns the first failure as a stable `reason_code`. The order matters: an earlier failure hides every later one.

| # | Check | `reason_code` | Source |
|---|-------|---------------|--------|
| 1 | `settings.llm_model` is non-blank (a configured local Ollama model) | `model_not_configured` | `ai_orchestration.py:203` |
| 2 | `settings.sources_path` is an existing file | `sources_unavailable` | `ai_orchestration.py:205` |
| 3 | `settings.evidence_records_path` is a writable file | `evidence_unavailable` | `ai_orchestration.py:207` |
| 4 | `settings.ke_executable` resolves (the Core CLI) | `core_cli_unavailable` | `ai_orchestration.py:209` |
| 5 | When `core_cli_command_preflight`: required Core commands answer `--help` | `core_cli_incomplete` | `ai_orchestration.py:212` |
| 6 | `research_papers_dir` exists-and-writable, or its parent is | `research_papers_unavailable` | `ai_orchestration.py:214` |
| 7 | Session store usable (local), or inside the persistent mount | `session_store_unavailable`, `persistent_session_root_unavailable`, `persistent_session_path_invalid` | `ai_orchestration.py:216`, `:472` |
| 8 | Discovery capability (below); its code is passed through | `core_cli_unavailable`, `ledger_root_unavailable`, `persistent_ledger_root_unavailable`, `persistent_ledger_path_invalid` | `ai_orchestration.py:219`, `discovery_orchestration.py:50` |

The capability check is filesystem-only: it creates no storage and contacts no model or provider.

## Where the local model is hard-wired

- `run_ai_orchestration` re-checks capability and raises `AIOrchestrationError` when unavailable (`ai_orchestration.py:278`),
  so without a model no report can start.
- It then asserts `settings.llm_model is not None` (`:284`) and constructs `OllamaLLM(model=..., host=settings.ollama_host)` (`:300`).
- `_build_grounded_completion_policy` asserts a model and passes it as `grounding_model` (`:247`).

So **a one-request report cannot run without a configured model today**, and the model must be reachable at `ollama_host` when the report runs.

## Other mandatory inputs

- **Indexed corpus inputs:** `sources_path` and `evidence_records_path` must exist (checks 2-3). The report path first searches the indexed evidence.
- **Core CLI:** required both by the report path (check 4) and by discovery (`discovery_orchestration.py:59`).
- **Durable storage:** a session database and a discovery ledger directory, each with a `local` or `persistent` mode.
  Persistent mode requires an absolute path inside a writable mount and rejects paths outside it (including symlink escapes).
- **External providers:** discovery and acquisition are attempted only when evidence coverage is thin; they are not part of the
  static capability check and are exercised only after a visitor submits a question.

## What this audit does not establish

- Provider outcome strings and DOI formats are not pinned here (open validations for the later citation-link slice).
- The progress and certainty vocabulary live in `knowledge-engine-ai`/Core, not in this repository.
- No claim is made that progress is live or that a model-free report is possible.

## Suggested next slices (unchanged from the decomposition proposal)

Removing the model dependency requires a design for synthesis without an LLM (`web-orchestration-without-llm`) before
`evaluate_ai_capability` may advertise availability without one; otherwise `/ask` would start research that cannot finish.
