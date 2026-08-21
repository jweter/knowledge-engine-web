# WEB-FRD-5: Research Freshness History -- Design and Dependency Scoping

Status: complete. All seven items in section 5's dependency list have
merged (Core, then AI, then this repository twice -- once for the run-level
slice, once more for the candidate-level slice), and this repository has
implemented items 5-7 in full, including the candidate-level diff rendering
section 4 originally sketched. See "Section 9: 2026-08-20 implementation
update" at the end of this document for exactly what shipped and how it was
verified. The rest of this document is preserved as originally written for
its evidence trail.
Scope: `docs/federated_discovery_transparency_roadmap.md`'s WEB-FRD-5
("research freshness history").

## 1. What this milestone is actually asking for

The roadmap's own framing (its "Search freshness and 'what changed'"
section) is specific, not aspirational marketing copy. For a **previously
run question**, Web should be able to show a person, on a **return visit**:

- last literature search date;
- newly discovered works since the previous run;
- newly available full text;
- newly discovered citation/reference links;
- corrections/retractions since the previous run;
- whether the evidence-map conclusion changed;
- whether provider coverage changed because a provider was newly added or
  was unavailable in one run.

WEB-FRD-5's own exit criteria compress this to four checks:

1. newly discovered works are visible;
2. new corrections/retractions are highlighted;
3. provider-coverage changes are shown;
4. old synthesis is versioned rather than silently rewritten.

Concretely, for a user this means something like:

> A researcher asks "does semaglutide reduce cardiovascular events in
> non-diabetic patients?" via `/discover` on 2026-06-01. They come back on
> 2026-08-19 and ask the *same* question again. Web should be able to say:
> "Since your last search on 2026-06-01: 4 new candidate works found; 1
> provider (Semantic Scholar) that was rate-limited last time is now
> reachable; 1 previously-clear candidate now carries a retraction flag."

That requires the system to know, on the second visit, (a) that this is
"the same question" as before, and (b) what the first run actually found,
so the two runs can be diffed. Both of those are the crux of this design.

## 2. What already exists to build on

### 2.1 Core: a durable, single-run ledger -- point lookup only

`knowledge-engine-core`'s `ke federated-discover` already persists **every**
run immutably to a local JSON ledger before returning
(`knowledge_engine/federated_search_ledger.py`, `FederatedSearchLedger`).
Each `SearchRunRecord` already carries a `research_question_id: str | None`
field (`federated_search_ledger.py:58`) and `FederatedDiscoveryService.search()`
already accepts and threads a `research_question_id` parameter down to the
ledger (`knowledge_engine/federated_discovery_service.py:22`, `:56`, `:70`).
So the storage schema for "tag a run as belonging to a tracked question"
**already exists** at the Python-API layer.

But:

- `FederatedSearchLedger` exposes exactly two read operations: `load(id)`
  and `coverage_report(id)` -- both **point lookups by exact
  `search_run_id` UUID**. There is no method to list every run in a ledger
  root, and no method to filter runs by `research_question_id` or by query
  text (`federated_search_ledger.py:192-222`; verified no other public read
  method exists in that file).
- The `federated-discover` CLI command (`knowledge_engine/entrypoint.py:5359`)
  never exposes a `--research-question-id` flag and never passes one to
  `service.search(...)` -- confirmed by grep: `research_question_id` does
  not appear anywhere in `entrypoint.py`. The one field that would let two
  runs be correlated as "the same tracked question" is wired all the way
  down to the ledger and then left disconnected at the CLI boundary.
- There is a second read command, `federated-coverage-report
  <search_run_id>` (`entrypoint.py:5463`), but it also requires the caller
  to already know the exact UUID -- it cannot discover which UUIDs exist for
  a given question.
- No `ke` command anywhere in `entrypoint.py` lists or searches the ledger
  (`grep -n "@app.command" | grep -i "list\|history\|runs"` returns nothing).

This is not a deep architectural problem -- the storage and the
correlating ID already exist -- but it is a real, unbuilt Core capability,
not a documentation gap.

### 2.2 AI: no wrapper reaches a past run at all

`knowledge-engine-ai`'s `ke_client.py` wraps exactly one federated-discovery
CLI surface: `federated_discover()` (`ke_client.py:535`), which shells out to
`ke federated-discover` and parses its `--output` snapshot. It does not
forward `research_question_id` (Core's CLI doesn't accept it either, so
there is nothing to forward), and there is **no wrapper at all** for `ke
federated-coverage-report` -- confirmed by reading the full file: the only
federated-discovery-related public functions are `federated_discover`,
`parse_federated_discovery_result`, and the `citation_snowball` family, which
is an unrelated command.

Per this repository's own architecture rule
(`docs/agent-development-policy.md` section 1), Web must reach Core's CLI
exclusively through `ke_client` and must never shell out to `ke` on its own.
That means even Core's one existing point-lookup command
(`federated-coverage-report`) is **currently unreachable from Web** through
any sanctioned path, because `ke_client` has no wrapper for it.

This "durable ledger with point-lookup-by-ID-only, and no list/query
capability" shape is not unique to federated discovery. `knowledge-engine-ai`'s
own Research Copilot session store (`knowledge_engine_ai.sessions.repository.
SessionRepository`, already imported by this repository's `ai_orchestration.py`)
has the identical shape: `get_session(session_id)` is a point lookup by exact
ID; there is no `list_sessions()` or "find sessions asking a similar
question" method (`sessions/repository.py`, full method list checked: `create_
session`, `get_session`, `update_session_status`, `attach_research_isa`,
`get_research_isa`, `record_criterion_result`, `latest_criterion_results`,
`append_event`, `has_event`, `list_events` -- `list_events` lists **events
within** one already-known session, not sessions themselves). This confirms
the missing capability is systemic across the family's durable stores, not
an oversight specific to federated discovery.

### 2.3 Web: `/discover` is fully stateless, and there is no "tracked
question" identity to hang history on

`GET /discover?q=...` (`knowledge_engine_web/main.py:701-759`) calls
`run_guarded_discovery` -> `discovery_orchestration.run_discovery` ->
`ke_client.federated_discover()` fresh on every request and renders the
in-memory result. Nothing is written to any Web-owned store. The only
identifier for "this question" is the raw query string in the URL; there is
no user account, no saved/bookmarked question, no session concept for
`/discover` at all (confirmed: `discovery_orchestration.py` and `main.py`'s
`/discover` route contain no read or write of any local file or database).
`docs/project-status.yaml`'s own WEB-FRD-1 note says the same thing plainly:
"one Research Session type's coverage view, not yet wired into a saved/
durable Research Session record."

Even if Web decided to keep its own local copy of past runs (bypassing the
ledger/list gap by never needing to list Core's ledger), the default
`federated_discovery_ledger_root` (`data/federated_discovery_runs`,
`config.py:48`) is a relative path under Web's working directory. Per
`docs/deployment.md`'s "Alpha hosting (Render)" section, Render's filesystem
is ephemeral unless a paid persistent disk is attached at `/var/data`; today
only Research Copilot's session storage (`KE_WEB_SESSION_STORAGE_MODE=
persistent`) opts into that disk. A history feature would need the same
opt-in persistent-disk wiring before "return next month and see what
changed" could survive a redeploy -- solvable with the existing pattern, but
not yet done for discovery.

### 2.4 Precedent already in this repository: `whats_changed.py`

`knowledge_engine_web/whats_changed.py` is the closest existing analogue,
and it is instructive about what *not* to do. Its own docstring records
that its first version tried to reconstruct "before" from `created_at`
timestamps and had to be revised (Codex review, PR #23) because Core's
working database is rebuilt from scratch on every alpha refresh, so
`created_at` said nothing about true age. The fix was a **single** captured
baseline file, written once per deploy refresh by a deploy script
(`scripts/capture_whats_changed_baseline.py`), diffed against current live
state. That pattern proves two things relevant here:

- this project already has one working precedent for "diff current state
  against a captured past snapshot," so the general shape (baseline JSON +
  diff function) is not new engineering risk;
- but that pattern is single-baseline, whole-corpus, deploy-triggered --
  not per-question, not multi-run, and not request-time. WEB-FRD-5 needs
  multi-run history *per tracked question*, captured at *request* time, not
  a single global baseline captured at *deploy* time. The existing pattern
  does not transfer directly; it is a precedent for "this is buildable in
  principle," not a shortcut that already solves this milestone.

## 3. Data model this milestone actually needs

Three distinct pieces of state, and where each belongs:

| What | Owner | Why |
|---|---|---|
| The immutable fact of one search run (query, timestamp, provider outcomes, candidates, disagreements, publication-status flags) | **Core** (already exists: `FederatedSearchLedger`) | Core is the source of truth for what a provider search actually found and when. Web must never invent or locally re-derive this. |
| The correlation between multiple runs and "the same tracked question" | **Core**, via the already-defined but CLI-unexposed `research_question_id` | This is run metadata, not run content -- it belongs next to the run record it tags, so any consumer (Web, or a future non-Web client) gets the same answer. Web assigning its own ad hoc correlation ID that Core never sees would let Web's idea of "the same question" and Core's ledger silently diverge. |
| The list/index of "which runs belong to this tracked question, newest first" | **Core**, as a new read capability over the ledger it already owns | Same reasoning: an index over Core's own immutable records should be computed by Core (or, at minimum, exposed by Core's CLI/`ke_client` deterministically), not reconstructed by Web scanning files it does not own. |
| The concept of "a tracked question a person returns to" (as opposed to a one-shot free-text search) | **Web** | This is presentation/product surface, not corpus fact. Web already owns `/discover`'s query-string-driven, account-free UX; a "tracked question" is a Web-level product decision (e.g., a stable slug/URL a person bookmarks) that then supplies `research_question_id` on each run it initiates. |
| The diff/"what changed" computation between two runs | **Web** (rendering) over **Core-supplied** facts for both runs | Same division of labor as every other WEB-FRD milestone in this roadmap: Core supplies deterministic facts, Web never infers or fabricates a comparison Core did not state. Diffing two already-fetched immutable run records (new candidate IDs, provider outcome deltas, retraction-flag deltas) is a pure, side-effect-free function over data Core already recorded -- this part is genuinely Web's to build, once it can reach two runs' data at all. |

None of this needs a new database *engine* -- Core's existing per-run JSON
ledger is a perfectly reasonable durable store for this. What it needs is
new **read surface** over that store (list-by-question) and new **write
surface** to actually tag runs when they're created (the CLI flag), plus,
separately, Web-side product identity for "a tracked question" and
persistent-disk wiring for the ledger to survive redeploys.

## 4. UI surface (once the dependency is resolved)

Sketch, following this roadmap's existing progressive-disclosure convention
(default view stays simple; detail is opt-in):

```text
Discovery coverage
PubMed              searched
Crossref            searched
OpenAlex            searched
Semantic Scholar    searched            <- was "rate limited" last time
arXiv               not relevant to this query
Last search          2026-08-19 09:14 UTC

  [ Since your last search on 2026-06-01 v ]
    + 4 new works found
    + Semantic Scholar is now reachable (was rate-limited)
    ! 1 candidate now flagged as retracted (was clear)
    Provider coverage: complete (was: degraded / partial)
```

- Default answer view is unchanged from today's WEB-FRD-1/2/3/4 `/discover`
  page.
- A closed-by-default `<details>` section (matching the pattern already
  used for "Search method and provenance" and `/ask`'s "Research path"
  section) shows the diff only when a previous run for the same tracked
  question exists; otherwise it states plainly "This is the first recorded
  search for this question" rather than omitting the section or implying
  history that does not exist.
- New candidates get the same card treatment `/discover` already renders,
  not a separate mini-format.
- Retraction/preprint deltas reuse WEB-FRD-4's existing
  `PublicationStatusView` states, framed as "was X, now Y," never a bare
  color change.
- Provider-coverage deltas reuse WEB-FRD-1's existing per-provider outcome
  labels the same way.

## 5. Blocking dependencies (exact, not hand-waved)

WEB-FRD-5 cannot be honestly implemented in `knowledge-engine-web` alone.
Specifically:

**Core (`knowledge-engine-core`) must add:**

1. A `--research-question-id` (and, for parity, `--project-id`) option on
   the `federated-discover` CLI command, threaded to
   `service.search(research_question_id=...)` -- the underlying parameter
   already exists at every layer beneath the CLI; only the CLI flag is
   missing.
2. A new read capability over `FederatedSearchLedger`: at minimum, "list
   every `SearchRunRecord` in `--ledger-root` whose `research_question_id`
   equals X, newest first." This needs a ledger-root directory scan (or a
   small side index written alongside each record) plus, most likely, a new
   `ke federated-discover-history <research-question-id> --ledger-root ...`
   CLI command mirroring `federated-coverage-report`'s existing shape.

**AI (`knowledge-engine-ai`) must add:**

3. A `ke_client` wrapper for whatever new Core history command #2 produces
   (parse its JSON the same way `parse_federated_discovery_result` does
   today), plus, at minimum, a wrapper for the already-existing `ke
   federated-coverage-report` so a single past run becomes reachable through
   the sanctioned boundary at all.
4. `federated_discover()`'s signature extended to accept and forward
   `research_question_id`, once Core's CLI accepts it (item 1).

**Web (`knowledge-engine-web`) must add, only after 1-4 land:**

5. A product concept of "a tracked research question" for `/discover` --
   at minimum a stable, bookmarkable identifier a person's browser can
   return to (this does not require user accounts; a URL-embedded slug/UUID
   is sufficient, consistent with this repository's account-free design so
   far), which becomes the `research_question_id` passed on every run.
6. Persistent-disk wiring for `federated_discovery_ledger_root`, following
   the exact pattern `docs/deployment.md` already documents for
   `KE_WEB_SESSION_STORAGE_MODE=persistent` -- otherwise history is silently
   wiped on every Render redeploy, which would be worse than not offering
   the feature (it would imply durability that does not exist).
7. The diff-rendering route/template work sketched in section 4, once (1)-(6)
   supply real data to diff.

Per `docs/agent-development-policy.md` section 1a, a Core change expected to
affect Web should identify Web as a consumer before merging; the reverse
coordination applies here -- Web should not start (5)-(7) until (1)-(4) are
merged and this repository's pinned `knowledge-engine-ai` revision is
bumped past them, the same two-step procedure already used for WEB-FRD-2/
WEB-FRD-3/WEB-FRD-4 (see `docs/web_launch_gate_security.md`'s dated
entries).

## 6. Alternative considered and rejected: client-held "compare to your last
view" token

One tempting way to avoid waiting on Core/AI: have `/discover` return the
current run's essential facts (candidate IDs/titles, provider outcomes,
publication-status flags) embedded in a hidden form field or query
parameter; a "compare to a new search" action resubmits both the old
(browser-held) payload and a fresh query; Web runs a brand-new
`federated_discover()` call and diffs the two **without any server-side
storage at all**. This is technically buildable today with zero Core/AI
changes.

It was rejected for this milestone:

- It only ever compares "the run you happened to still have open in this
  browser" to a brand-new run in the same sitting. It cannot satisfy the
  roadmap's actual scenario -- a person returning *after leaving and coming
  back*, on a different device or browser session, or after Core/Web have
  been redeployed. That is precisely the "what changed since I last looked"
  value this milestone exists to deliver; a same-tab-only compare would not
  deliver it, only resemble it.
  Exit criterion 4 ("old synthesis is versioned rather than silently
  rewritten") is not satisfiable by this approach at all -- there is nothing
  to version if nothing is durably stored.
- It risks presenting something that *looks* like durable freshness history
  to a user while actually being an ephemeral browser-tab artifact -- a
  transparency/trust regression in a product whose explicit product
  principle (this roadmap's own opening section) is not to visually imply
  more than the system actually knows.
- This project has an established, explicit precedent for declining exactly
  this kind of look-alike shortcut: WEB-FRD-4's status paragraph
  (`docs/federated_discovery_transparency_roadmap.md`) states plainly that
  correction/expression-of-concern/withdrawal rendering "remain[s] out of
  scope: Core's `ProviderObservation` does not yet carry those fields, so
  rendering them would require a Core (and then AI) change first, not a
  Web-only slice" -- rather than approximating those states from data that
  does not actually carry them. This design follows the same discipline.

## 7. Exit-criteria mapping (today vs. once unblocked)

| Exit criterion | Blocked today because | Unblocked once |
|---|---|---|
| Newly discovered works are visible | No way to fetch a *previous* run's candidate list at all (no `ke_client` wrapper reaches any past run) | Dependencies 1-4 (Core history read + AI wrapper) |
| New corrections/retractions are highlighted | Same -- there is no previous run's `observation_flags` to diff against | Same |
| Provider-coverage changes are shown | Same -- there is no previous run's `provider_statuses` to diff against | Same |
| Old synthesis is versioned rather than silently rewritten | `/discover` has no synthesis at all (it is discovery, not Research Copilot synthesis); versioning synthesis specifically is a separate, larger question about `/ask`'s `SessionRepository`, which has the identical "point lookup only, no list" gap (section 2.2) | A separate design pass once/if this exit criterion is scoped against `/ask` rather than `/discover` -- out of scope for this document, which follows the roadmap section's own framing under federated discovery |

## 8. Recommendation

1. Keep WEB-FRD-5 `not started` in `docs/project-status.yaml`, but replace
   the vague "likely needs a durable multi-run history/versioning design"
   continuation note with the concrete dependency list in section 5 of this
   document, so a future session does not have to re-derive it.
2. File (or ask Jeremy to file) the two concrete Core asks (section 5,
   items 1-2) and the two concrete AI asks (items 3-4) as their own
   roadmap/issue entries in `knowledge-engine-core` and `knowledge-engine-ai`
   respectively, cross-referenced from this document -- the same
   "Core/AI merges first, then Web consumes it" sequencing already used
   successfully for WEB-FRD-2/3/4.
3. Do not build any Web-only approximation in the meantime (section 6). If
   an interim signal is wanted, the honest option is a plain, explicit
   disclosure -- e.g. `/discover` stating "This deployment does not yet
   retain past searches for comparison" -- not a feature that resembles
   history without being durable. This document does not implement even
   that disclosure as a "slice," because WEB-FRD-2 already states the
   run's own timestamp/ID explicitly and adding a second, adjacent "no
   history yet" sentence next to it is not meaningful forward progress on
   this milestone -- it would be documentation dressed as a feature
   commit.

## 9. 2026-08-20 implementation update

Dependencies 1-4 (section 5) have all merged:

1. Core's `federated-discover --research-question-id`/`--project-id` flags: merged.
2. Core's `ke federated-discover-history <id>` command: merged.
3. `knowledge-engine-ai`'s `ke_client.federated_discover_history()` wrapper: merged.
4. `federated_discover()` forwarding `project_id`/`research_question_id`: merged.

This repository bumped its pinned `knowledge-engine-ai` revision to consume
them and implemented items 5-6 in full, plus a deliberately partial slice
of item 7:

- **Item 5 (tracked-question identity):** implemented as a pure,
  deterministic function of normalized query text
  (`knowledge_engine_web/research_question.py`), not a client-held random
  token requiring a bookmark. This is a stronger version of what item 5
  asked for: two people (or the same person on two different devices)
  asking the same question in the same words are automatically recognized
  as the same tracked question, with no account or saved state.
- **Item 6 (persistent-disk ledger wiring):** implemented, mirroring
  AI-O15's `session_storage_mode`/`session_persistent_root` split exactly
  (`config.py`'s `discovery_ledger_storage_mode`/
  `discovery_ledger_persistent_root`, `discovery_orchestration.py`'s
  `_evaluate_ledger_storage`). `render.yaml` declares the persistent
  contract at `/var/data`, matching AI-O15's own "declares the contract,
  does not purchase the disk" posture -- an operator must still attach a
  real Render disk before this survives a redeploy in production.
- **Item 7 (diff rendering): implemented only at the run level, not the
  candidate level.** This is the one place this implementation diverges
  from the original sketch in section 4, and deliberately so. Section 4's
  UI sketch shows *specific* new works and a *specific* candidate's
  retraction flag flipping. That requires knowing what candidates a past
  run actually returned. `ke_client.federated_discover_history()` -- the
  wrapper that closed dependency 3 above -- was deliberately built to
  return only each past run's `SearchCoverageReport` (candidate count,
  provider outcomes, completeness, its own timestamp), not that run's
  candidate list, because the underlying Core command
  (`federated-coverage-report`) that could supply a single past run's full
  candidates has no `--output` JSON option, and `knowledge-engine-ai`
  explicitly declined to wrap console-text scraping. Confirmed by reading
  that project's own `ke_client.py` and its introducing commit's message.

  So what shipped (`discovery_freshness.py`, a "Since your last search"
  section in `discover.html`) answers three of section 1's seven bullet
  points honestly -- last search date, whether provider coverage changed,
  whether the aggregate candidate count changed -- and explicitly declines
  to answer the other four (specific newly discovered works, specific newly
  available full text, specific newly discovered citation links, specific
  corrections/retractions) rather than approximating them from data this
  project does not have. The rendered section states this limitation to
  the visitor in plain language.

**What would unblock the remaining, candidate-level slice:** a Core
capability that returns a specific past run's full candidate list (not just
its aggregate coverage), reachable through `ke_client` without console-text
scraping -- e.g. a `--output` JSON option on `federated-coverage-report`, or
a Core-side persisted-snapshot read command mirroring how
`federated-discover --output` already writes one at request time. This is a
Core-repository ask; recorded here rather than filed as a separate Core
roadmap document because it is a small, single addition to an existing
command's contract, not a new milestone family of its own.

## 10. 2026-08-20 follow-up: candidate-level slice unblocked and shipped

The exact Core capability section 9 asked for landed later the same day:

1. Core PR #394 ("Persist federated-discover candidate snapshots; add
   coverage-report --output", commit `96d30ac`) added `--output` to
   `federated-coverage-report` and started persisting each run's full
   deduplicated candidate list on `SearchRunRecord.candidates`. Purely
   additive: a run persisted before this change loads with an honest empty
   candidate list, never a fabrication.
2. `knowledge-engine-ai` PR #55 (commit `2cab16b`) added
   `ke_client.federated_coverage_report()`, the point-lookup wrapper for
   that new command, typed as `FederatedCoverageReportResult` pairing the
   run's `SearchCoverageReport` with its `FederatedCandidateRecord` /
   `FederatedCandidateObservation` snapshot.

This repository bumped its pinned `knowledge-engine-ai` revision from
`f65e340d4d280840a49f3c10a8693dd5aadcc340` to
`2cab16b47bb9d3f42d777e989bf2637e8310fb4d` to consume it, and implemented
the candidate-level slice of item 7 that section 9 explicitly deferred:

- `discovery_orchestration.py` gained `run_discovery_candidate_snapshot()`,
  wrapping `ke_client.federated_coverage_report()` with the same
  capability-gating and error-sanitizing pattern as the existing
  `run_discovery_history()`.
- `discovery_presentation.py`'s per-provider retraction/preprint rollup
  (`_build_publication_status`) was made public
  (`build_publication_status()`) so `discovery_freshness.py` could reuse it
  verbatim against a past run's `FederatedCandidateObservation` records --
  the same duck-typed shape as the current run's `ObservationFlagSource`,
  so no adapter layer was needed.
- `discovery_freshness.py` gained `build_candidate_freshness()`: given the
  current run's already-computed candidate cards and one past run's full
  candidate snapshot, it reports candidates present now and absent from the
  snapshot (`newly_discovered`) and candidates present in both whose
  `retraction_state` flipped to `"retracted"` (`newly_retracted`, carrying
  the previous state for a "was clear/not checked, now retracted" framing).
  A brand-new candidate that happens to already be retracted is reported
  only in `newly_discovered` -- there is no prior "was" state to compare it
  against.
- `main.py`'s `/discover` route composes this as a second, additive,
  best-effort lookup on top of the existing run-level freshness view (only
  attempted once a previous run is known to exist), using
  `dataclasses.replace` to attach the result without touching
  `build_discovery_freshness()`'s existing, already-tested run-level logic.
  A failed or empty lookup leaves the view at its run-level-only state.
- `discover.html` renders "Newly discovered works" and "Newly flagged as
  retracted" sections, reusing the exact candidate-card markup
  `/discover`'s main results list already uses (extracted into a local
  Jinja macro, `candidate_card`, so both call sites stay byte-identical)
  and WEB-FRD-4's existing retraction banner -- per section 4's original
  instruction, no separate mini-format was invented.

**Verification:** `poetry run python scripts/quality_preflight.py` passed
in full (format, lint, mypy, 332 tests -- 318 pre-existing plus 14 new,
pip-audit, diff hygiene). Per this repository's own development-policy
discipline against fake-transport-only verification, the new capability was
also live-verified against the real `ke` binary end to end: a
`knowledge-engine-core` checkout at the commit containing PR #394 was
installed, a `FederatedSearchLedger` was seeded directly via Core's own
`ledger.record()` (no network provider call needed -- this command is a
pure ledger read, the same justification AI PR #55's own commit message
gives for its live verification) with two runs for one tracked question: an
older run with one candidate reported clear of retraction, and a newer run
with that same candidate now retracted plus one brand-new candidate. A
local `knowledge-engine-web` server was then started with `KE_WEB_KE_EXECUTABLE`
and `KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT` pointed at that real binary and
ledger (only the top-level `run_guarded_discovery` -- the one call that
would otherwise require real external provider API access -- was stubbed to
return the "current run" fixture matching the seeded newer run), and
`curl`'d. The response HTML showed "Newly discovered works" naming the
brand-new candidate and "Newly flagged as retracted" naming the flipped one
with "Was reported clear of retraction ... now reported retracted," proving
the real `ke federated-discover-history` and
`ke federated-coverage-report --output` subprocess calls, Core's real JSON
contract, `knowledge-engine-ai`'s real parsing, and this repository's diff
and rendering logic all compose correctly end to end -- not just against
fixtures.

Docker's `docker` CI job (image build + container smoke test) was not run
locally for this change -- no Docker daemon was available in this session's
environment. `pyproject.toml`/`poetry.lock` changed (the pin bump), so this
is exactly the case `docs/quality_preflight.md` recommends a local Docker
build for; it was not possible here, so CI's `docker` job is the first
actual verification of the built image for this change, consistent with
this repository's "GitHub Actions remains the authoritative merge gate"
policy.

All four exit criteria are now resolved (three met, one not applicable --
see `docs/federated_discovery_transparency_roadmap.md`'s WEB-FRD-5 section
for the current per-criterion accounting). Correction/expression-of-concern/
withdrawal states remain out of scope, unrelated to this slice: Core's
`ProviderObservation` still does not carry those fields (a separate,
still-blocked Core schema change, the same one WEB-FRD-4 already named).

## 11. PR #75 review follow-up: an unusable snapshot could masquerade as a valid empty baseline

A P1 review comment on PR #75 (this section's own PR) identified a real gap
in section 10's "a run persisted before this change loads with an honest
empty candidate list, never a fabrication" framing: that honest empty
`candidates` tuple is indistinguishable, on its own, from a run that
genuinely had zero candidates. `main.py`'s composition step only checked
`previous_snapshot is not None` before trusting it as a complete baseline --
so a run recorded before Core PR #394's candidate-snapshot persistence
existed (nonzero aggregate `candidate_count`, empty `candidates` tuple) was
wrongly treated as a valid zero-candidate baseline, making every current
candidate render as newly discovered.

Fixed by adding `discovery_freshness.candidate_snapshot_is_usable()`, which
checks the snapshot's own internal consistency (`len(candidates) > 0` or
`coverage.candidate_count == 0`) before `main.py` trusts it. An inconsistent
snapshot now falls back to the run-level-only comparison exactly as a failed
or missing lookup already did -- no new fallback mechanism, reusing the one
this section already documents. Regression test:
`tests/test_discover_route.py::test_discover_degrades_to_run_level_freshness_when_prior_snapshot_predates_persistence`,
confirmed to fail against the pre-fix code and pass after. Full
`quality_preflight.py` passed (333 tests -- 332 from section 10 plus this
one).

## 12. 2026-08-21: candidate-level diff extended to all four publication-status flags

Section 10 shipped `build_candidate_freshness()`'s "newly retracted" diff
alone, deliberately deferring correction/expression-of-concern/withdrawal
because -- at the time -- Core's `ProviderObservation` did not carry those
fields for `federated-coverage-report --output` to persist, and even where
Core did have them, `/discover`'s own per-candidate rendering
(`discovery_presentation.PublicationStatusView`) had not yet been extended
to roll them up (that was WEB-FRD-4's own remaining slice, tracked
separately in `docs/federated_discovery_transparency_roadmap.md`).

Both blockers cleared the same day this section was written: Core PR #396
wired Crossref's `update-to` relation into the three fields, AI PR #57
parsed them, and this repository's WEB-FRD-4 slice (completed 2026-08-21)
rolled them into `PublicationStatusView` as three additional independent
states (`correction_state`, `expression_of_concern_state`,
`withdrawal_state`). `ke_client.federated_coverage_report()`'s
`FederatedCandidateObservation` -- the same past-run snapshot type
`build_candidate_freshness()` already consumed for retraction -- already
carried `corrected`/`expression_of_concern`/`withdrawn` per provider
(confirmed by reading `knowledge-engine-ai`'s `ke_client.py`, which this
repository was already pinned to at commit `58c21b1`), so closing this gap
required no further Core or AI change -- it was a Web-only extension of
already-available data, exactly as this document's own item 7 always
anticipated once WEB-FRD-4 unblocked.

What changed:

- `RetractedCandidateFreshnessView` was generalized to
  `FlaggedCandidateFreshnessView` (`candidate` plus `previous_state`), one
  view type shared by all four flags rather than one class per flag, since
  the "was clear/not_checked, now flagged" shape is identical across them.
- `CandidateLevelFreshnessView` gained `newly_corrected`,
  `newly_expression_of_concern`, and `newly_withdrawn` alongside the
  existing `newly_retracted`, computed by `build_candidate_freshness()` in
  a single pass over the current run's candidates (one
  `build_publication_status()` call per matching candidate, reused across
  all four flag checks rather than recomputed per flag).
- The four flags are diffed independently and are non-exclusive, matching
  `PublicationStatusView`'s own discipline against collapsing them into one
  status: a candidate simultaneously newly retracted and newly corrected
  appears in both `newly_retracted` and `newly_corrected`.
- `discover.html` gained a `newly_flagged_section()` macro (parameterized by
  heading, banner severity class, and the "was X" / "now Y" copy) so the
  four sections ("Newly flagged as retracted/corrected", "Newly flagged with
  an expression of concern", "Newly flagged as withdrawn") share one
  rendering path instead of four near-duplicate template blocks; the
  correction banner uses WEB-FRD-4's `is-degraded` severity (matching its
  per-candidate card treatment) while retraction/expression-of-concern/
  withdrawal use `is-critical`.
- The "nothing changed" and "candidate-level history unavailable"
  disclosures were reworded from retraction-specific language to name all
  four flags generically, so they stay honest about what this comparison
  now actually covers.

Verification: `poetry run python scripts/quality_preflight.py` passed in
full (format, lint, mypy across 55 source files, 359 tests -- 333
pre-existing plus 26 new/changed covering each flag's flip independently,
the four-flags-at-once non-exclusivity case, and the route-level rendering
of all three newly-covered flags together -- pip-audit, diff hygiene).
