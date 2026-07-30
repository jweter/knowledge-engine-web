# Web Design: Phase 5, First Slice

Status: this is the design sketch for `knowledge-engine-web`'s first
milestone, written before any application code, the same role
`knowledge-engine-core`'s own `docs/phase1_design.md`/`docs/phase4_design.md`
played for their phases. `docs/roadmap.md`'s Phase 5 bullet says this
project's job is where the future `knowledge-engine-ai`/`-web`/`-agents`
layers' work "actually reaches a person" -- this document scopes the
smallest honest version of that: a read-only page showing what `core`'s
graph already contains, with zero synthesis or judgment added.

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

## Out of Scope (this milestone)

- **Claim detail, paper/citation detail, relationship-candidate, or
  unconfirmed-claims pages.** Real, valuable next slices (`ke
  graph-report --evidence-record-id`/`--paper-id`, `ke
  graph-relationship-candidates`, `ke graph-unconfirmed-claims` all have
  page-shaped equivalents worth building) -- not attempted in this first
  milestone, which exists to prove the read-only database-access pattern
  end to end on the simplest possible page first. **Claim listing and
  detail were built next**, immediately after this milestone proved the
  pattern: `GET /claims` and `GET /claims/{evidence_record_id}`, reusing
  `_reflect_graph_tables` and the same "missing table means empty, not
  an error" posture. Paper/citation detail, relationship-candidate, and
  unconfirmed-claims pages remain real next slices.
- **`EvidenceRecord`/`RelationshipRecord` rendering.** These are JSONL
  files, not SQL rows, and `core` does not publish a single canonical
  path to one -- a real, separate design question (does this project
  read a path from its own config, shell out to `ke evidence-report
  --output`, or something else?) deliberately deferred rather than
  guessed here.
- **Any confidence rating, synthesis, or judgment about what a claim or
  relationship means.** `core_interface_contract.md`'s "the seam"
  applies here exactly as it applies to `core` itself: this project
  never sets or infers `research_question`, `evidence_direction`, or any
  rating beyond `core`'s own stored `confidence_note` text. That is the
  future `knowledge-engine-ai` layer's job, not this one's, regardless
  of how tempting a "graph with typed edges" is to summarize into a
  score.
- **Write access of any kind.** This project never modifies `core`'s
  database. Read-only, always.
- **Authentication, multi-user support, deployment.** A real future
  need once this runs anywhere but a trusted local machine; not
  attempted here (see `SECURITY.md`'s Current Limitations).

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

- `knowledge_engine_web/config.py` -- a `pydantic-settings` `Settings`
  class reading `KE_WEB_DATABASE_URL` (falls back to
  `sqlite:///data/knowledge_engine.sqlite3`, mirroring `core`'s own
  `KE_DATABASE_URL` default shape but under this project's own prefix,
  since this is a distinct consuming process, not `core` itself).
- `knowledge_engine_web/graph_reader.py` -- a small, read-only
  `GraphSummary` dataclass and a `read_graph_summary(engine)` function:
  reflects `graph_concepts`/`graph_claims`/`graph_claim_concepts`/
  `graph_claim_relationships`/`graph_citations` (skipping any table
  reflection finds missing, e.g. a `core` database older than M47),
  and computes the same counts `GraphRepository.population_counts()`
  computes in `core` -- independently, since this project does not
  import `core`'s repository, but checked against `core`'s own
  documented numbers in testing (see Testing Strategy).
- `knowledge_engine_web/main.py` -- the FastAPI app: one route,
  `GET /graph`, rendering `templates/graph_summary.html` via Jinja2
  (autoescaping on by default -- every concept-source label and count is
  escaped automatically, the same non-negotiable discipline `core`'s own
  `_report_text`/`_graph_report_text` helpers hand-implement for
  Markdown, done here by the standard tool for HTML instead).
- `templates/graph_summary.html` -- minimal, no client-side JavaScript,
  no build step. A future page can extend a shared base template once a
  second page exists; not built prematurely for one page.

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
- **Whether `EvidenceRecord`/`RelationshipRecord` rendering shells out
  to `ke` or reads JSONL directly.** Named in Out of Scope above;
  belongs to whichever milestone actually builds an evidence-record
  page, not this one.
- **HTML template structure once a second page exists** (shared layout,
  navigation). Not designed against one page; revisit at the second
  page, the same "don't design for a hypothetical" discipline `core`
  itself follows throughout.
