# Web Design: Phase 5, First Slice

Status: this is the design sketch for `knowledge-engine-web`'s first
milestone (a single `GET /graph` page), written before any application
code, the same role `knowledge-engine-core`'s own
`docs/phase1_design.md`/`docs/phase4_design.md` played for their
phases. Much more has shipped since -- claims, unconfirmed claims,
relationship candidates, paper detail, Evidence Record rendering,
Markdown reports, a Roadmap page, and a password-gated alpha
deployment. **For current scope, see this repo's own `README.md`
Roadmap section**, kept up to date as features ship. What follows
below is the original first-slice scope and the architectural
decisions made reaching it -- most still hold true (the SQLAlchemy
reflection decision, the JSONL-not-shell-out decision for Evidence
Records) even though the page inventory it describes is now smaller
than what actually exists.

## Mission

Render what `knowledge-engine-core` has already validated -- for a
person, in a browser, instead of a terminal. Nothing here decides what
evidence *means*; that seam belongs to the future `knowledge-engine-ai`
layer (see `core_interface_contract.md`'s "The seam" section, quoted
below). This project's only job is trustworthy, legible display.

## Principle

Same principle every `core` milestone held to, restated for a renderer:
never guess, never infer, never compute a judgment `core` itself does
not already store. Every number and label this project shows must trace
back to an actual row in `core`'s database or an actual field in an
`EvidenceRecord`/`RelationshipRecord` -- never a value this project
invents to make a page look more complete.

## Prerequisite: what `core` actually documents as consumable

`knowledge-engine-core/docs/core_interface_contract.md` is the concrete
answer to "what can a layer like this one actually read from `core`,"
written specifically so a consumer does not have to reverse-engineer
`core`'s source. Two facts from it shape every decision below:

1. **"There is no HTTP API, no RPC layer, no Python package published
   for import today -- `ke <command>` is the interface."** Confirmed by
   direct testing while bootstrapping this project: adding
   `knowledge-engine-core` as a Poetry dependency (even a git dependency
   pinned to a specific commit) pulls in its *entire* declared
   dependency set -- including `torch`, `sentence-transformers`, and
   `faiss-cpu` for Phase 3's embedding/vector-search features -- since
   Poetry has no way to install a subset of a package's declared
   dependencies without the source package defining optional extras,
   which `core` does not. Importing `knowledge_engine` as a library
   would drag a multi-gigabyte ML dependency tree into a page that only
   needs to run three `SELECT` statements. Not attempted.
2. **"Data access: two supported paths"** -- reading `core`'s SQLite
   database directly (read-only, via SQLAlchemy or any SQLite client),
   or the portable corpus-library snapshot. `EvidenceRecord`s and
   `RelationshipRecord`s are a third, related fact: they are plain JSONL
   files on disk (e.g. `data/corpora/glp1_weight_loss/evidence_records.jsonl`),
   never SQL rows -- confirmed by reading `knowledge-engine-core/knowledge_engine/models.py`,
   which has no `EvidenceRecord`/`RelationshipRecord` table at all (see
   `docs/phase4_design.md`'s own Open Questions on why
   `GraphClaim.evidence_record_id` is a plain string, not a foreign key).

## Goals (this milestone)

- A single page, `GET /graph`, rendering the graph's corpus-wide summary
  -- concepts by source, claims, claim-concept edges, relationship
  edges, citation edges -- the same numbers `ke graph-report`'s no-filter
  mode already prints, reached by reading `core`'s SQLite database
  directly instead of shelling out to the CLI.
- Every value on the page traced to a real row count; an empty or sparse
  graph (true of the real corpus today -- 2 claims, per
  `knowledge-engine-core`'s own M46-M51 live verifications) renders
  correctly as a small, honest number, not an error or a placeholder.

## Out of Scope (original first milestone)

What this section originally excluded, and what's true of each today:

- **Claim detail, paper/citation detail, relationship-candidate, and
  unconfirmed-claims pages.** All since built: `GET /claims`,
  `GET /claims/{evidence_record_id}`, `GET /papers/{paper_id}`,
  `GET /relationship-candidates`, `GET /unconfirmed-claims` -- all
  reusing `_reflect_graph_tables` and the same "missing table means
  empty, not an error" posture this milestone established.
- **`EvidenceRecord` rendering.** Since built: `GET /claims/{evidence_record_id}`
  shows `claim_text`, `research_question`, `evidence_direction`, PICO
  fields, `result_summary`, `limitations`, `uncertainty_notes`, and
  `confidence_note` when `KE_WEB_EVIDENCE_RECORDS_PATH` is configured
  -- see `knowledge_engine_web/evidence_reader.py`.
- **`RelationshipRecord` rendering.** Still not built -- no page reads
  relationship-record JSONL content (as opposed to the
  `graph_claim_relationships` SQL edges the claim-detail page already
  renders). Still needs its own design pass; see this repo's
  `README.md` Roadmap.
- **Any confidence rating, synthesis, or judgment about what a claim or
  relationship means.** Revised for Evidence Intelligence (M1):
  `GET /claims/{evidence_record_id}` now shows a deterministic,
  no-LLM confidence-scoring computation (`knowledge_engine_web/evidence_intelligence.py`,
  independently rebuilding `knowledge-engine-core`'s
  `docs/evidence_intelligence_design.md` formula against this project's
  own dataclasses, the same "read `core`'s data, never its code"
  posture as `graph_reader.py`). This is not a loosening of the seam's
  actual substance: the computation is fully deterministic (no LLM, no
  statistical model), reads only already-stored, already-human-reviewed
  fields, and this project still never sets or infers
  `research_question`, `evidence_direction`, or authors a
  `RelationshipRecord` -- `core_interface_contract.md`'s own "Revised
  in M58" note documents the same location change on `core`'s side.
  What remains out of scope, unchanged: any *narrated* synthesis (an
  LLM explaining what a number means), cross-domain confidence
  profiles, and the Statistics Auditor -- see
  `docs/evidence_intelligence_design.md`'s own "Explicitly out of
  scope" section in `knowledge-engine-core`.
- **Write access of any kind.** Still true. This project never
  modifies `core`'s database. Read-only, always.
- **Authentication, multi-user support, deployment.** Since built: a
  password-gated Render deployment (`knowledge_engine_web/alpha_auth.py`,
  `Dockerfile`, `render.yaml`) -- see `docs/deployment.md`'s "Alpha
  hosting (Render)" section. Still explicitly not built: real
  multi-user accounts, rate limiting, horizontal scaling -- see that
  same section's "What this does not cover".

## Decision: read `core`'s SQLite database via SQLAlchemy reflection, not by redeclaring its schema

Two ways to read `core`'s database exist: reimplement `core`'s own
`GraphClaim`/`GraphConcept`/etc. SQLAlchemy model classes in this
project (duplicating `knowledge_engine/models.py` by hand), or use
SQLAlchemy's table reflection (`MetaData().reflect(engine)`) to
introspect whatever tables actually exist at query time, with no
duplicated schema definitions.

**Decision: reflection.** Rationale:

- `core_interface_contract.md` itself warns that "the table layout
  itself is not yet a versioned, published contract... a consumer
  reading the database directly should expect to track `core` schema
  changes by watching `CHANGELOG.md`, not assume long-term column
  stability before v1.0." Hand-copied model classes would silently drift
  out of sync with `core`'s real schema (e.g. M50's `relationship_type`
  CHECK-constraint widening, or a future column addition) with no
  mechanism to notice; reflection reads whatever is actually there,
  every time.
- This project performs read-only `SELECT`s over a handful of columns
  (row counts grouped by `source`, a handful of foreign-key joins) --
  exactly the case reflection is built for. It does not need `core`'s
  own validation logic, relationships, or ORM behavior (e.g.
  `get_or_create_*` methods), only the column names and types.
- Keeps this project's only dependency on `core` being the documented
  interface contract itself (a database file path and a schema this
  project reads defensively), not a build-time coupling to `core`'s
  internal Python structure.

## Architecture

As originally scoped for the first slice (`config.py`, `graph_reader.py`,
`main.py`'s one route, one template) -- all still accurate as far as
they go. What's been added since, following the same patterns:

- `knowledge_engine_web/config.py` -- a `pydantic-settings` `Settings`
  class reading `KE_WEB_DATABASE_URL` (falls back to
  `sqlite:///data/knowledge_engine.sqlite3`, mirroring `core`'s own
  `KE_DATABASE_URL` default shape but under this project's own prefix,
  since this is a distinct consuming process, not `core` itself). Since
  extended with `evidence_records_path`, `host`/`port`, and the alpha
  auth username/password settings.
- `knowledge_engine_web/graph_reader.py` -- a small, read-only set of
  dataclasses and reader functions: reflects `graph_concepts`/`graph_claims`/
  `graph_claim_concepts`/`graph_claim_relationships`/`graph_citations`/`papers`
  (skipping any table reflection finds missing, e.g. a `core` database
  older than a given graph milestone), and computes the same counts and
  detail views `GraphRepository`'s own methods compute in `core` --
  independently, since this project does not import `core`'s
  repository, but checked against `core`'s own documented numbers in
  testing (see Testing Strategy).
- `knowledge_engine_web/evidence_reader.py` -- reads one `EvidenceRecord`
  by ID directly from `evidence_records.jsonl`, when
  `KE_WEB_EVIDENCE_RECORDS_PATH` is configured.
- `knowledge_engine_web/report_renderer.py` -- rebuilds the same
  Markdown reports `ke graph-report`/`ke graph-relationship-candidates`/
  `ke graph-unconfirmed-claims` print, from this project's own data,
  for the `/reports` pages -- see `docs/deployment.md` for why (never
  shells out to `ke`, which the alpha deployment doesn't have).
- `knowledge_engine_web/alpha_auth.py` -- HTTP Basic Auth middleware
  gating the whole app when `KE_WEB_ALPHA_USERNAME`/`KE_WEB_ALPHA_PASSWORD`
  are configured; see `docs/deployment.md`'s "Alpha hosting (Render)"
  section.
- `knowledge_engine_web/main.py` -- the FastAPI app: one route per page
  (`/graph`, `/claims`, `/claims/{id}`, `/papers/{id}`,
  `/unconfirmed-claims`, `/relationship-candidates`, `/reports` and its
  sub-pages, `/roadmap`, `/about`), each rendering a Jinja2 template
  (autoescaping on by default -- every concept-source label and count
  is escaped automatically, the same non-negotiable discipline `core`'s
  own `_report_text`/`_graph_report_text` helpers hand-implement for
  Markdown, done here by the standard tool for HTML instead).
- `templates/base.html` -- the shared layout (header, nav, footer,
  favicon) every page now extends, added once a second page existed, as
  originally planned below. `static/style.css` is the hand-written,
  no-framework, no-build-step stylesheet.

## Testing Strategy

- `graph_reader.read_graph_summary` tested against small, self-contained
  SQLite fixture databases built with plain SQLAlchemy `Table`/`insert`
  calls matching `core`'s real, documented column names (from
  `knowledge_engine/models.py`, read directly rather than imported) --
  covering an empty graph, a populated one, and a database predating a
  given graph table (M47's `graph_citations`), confirming reflection's
  `skip if missing` behavior degrades to zero rather than erroring.
  Deliberately not built by installing `core`'s own Poetry environment
  and shelling out to `ke graph-build` in CI -- real, but disproportionate
  complexity (a second project's full dependency install) for testing
  three `SELECT` statements over a handful of columns this project
  already reads defensively via reflection.
- `GET /graph` tested via FastAPI's `TestClient` against the same
  fixture databases, asserting the rendered counts and that a
  deliberately malicious concept-source string cannot inject HTML (a
  regression test mirroring `core`'s own Codex-caught Markdown-injection
  finding on `relationship-report`, redone for this project's actual
  output format).
- **Live verification against a real `core` corpus, separately, is still
  required before every milestone ships** -- the same "verify against
  real data" discipline every `core` milestone in this ecosystem follows.
  Small fixture tests prove the code's logic; a real corpus copy (built
  with `core`'s own `ke graph-build`, pointed at by
  `KE_WEB_DATABASE_URL`) proves this project reads `core`'s *actual*
  schema correctly. Not automated in CI for this milestone; done by hand
  before merge and recorded in the PR description, mirroring `core`'s
  own PR precedent.

## Open Questions (owner decisions, not resolved here)

- **How this project locates a specific `core` database file in a
  multi-corpus or multi-operator future.** Today: one env var, one
  database. Real enough for a first slice; revisit once a second real
  deployment scenario exists.
- **Resolved: `EvidenceRecord` rendering reads its JSONL file directly**,
  via a new optional `KE_WEB_EVIDENCE_RECORDS_PATH` setting
  (`knowledge_engine_web/evidence_reader.py`), not by shelling out to
  `ke evidence-report --output`. This keeps the whole read path
  process-free and consistent with `graph_reader.py`'s direct-SQLite
  approach -- no subprocess, no dependency on `ke` being installed or on
  its stdout format staying stable. The setting is optional and a
  missing file/unset path renders as "not configured" rather than an
  error, matching `graph_reader`'s "missing table means empty" posture.
  `RelationshipRecord` rendering is unresolved and remains open -- no
  page reads relationship-record JSONL content yet.
- **HTML template structure once a second page exists** (shared layout,
  navigation). Not designed against one page; revisit at the second
  page, the same "don't design for a hypothetical" discipline `core`
  itself follows throughout.
