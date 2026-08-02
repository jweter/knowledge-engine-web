# Knowledge Engine Web

Read-only web interface for the [Knowledge Engine](https://github.com/jweter/knowledge-engine-core)
project. Renders what `knowledge-engine-core` ("`core`") has already
validated -- for a person, in a browser, instead of a terminal. As of M1,
claim detail pages also show a deterministic, no-LLM Evidence
Intelligence confidence score (see "The Seam" below); nothing else here
adds synthesis, narration, or judgment about what a claim or
relationship means.

## Status

Early, but every page in this roadmap's original list is built: graph
summary, claims list/detail (now including evidence-record content),
unconfirmed claims, relationship candidates, and paper detail. `GET /ask`
now turns the `/roadmap` page's old non-functional concept-preview mockup
into a real, working question-first page -- retrieval over `core`'s own
FTS5 index, each matched paper's evidence records showing their own
Evidence Intelligence numbers where a graph claim exists. See
`docs/web_design.md` for the design this project follows, and `core`'s
own `docs/roadmap.md` for where this project fits in the larger
Knowledge Engine roadmap (Phase 5).

## The Seam

`core` locates, validates, and persists evidence. It never decides what
that evidence means for a person's actual question -- see
`knowledge-engine-core/docs/core_interface_contract.md`'s "The seam"
section. This project holds the exact same boundary: it never sets or
infers a `research_question`, an `evidence_direction`, or authors a
`RelationshipRecord`.

**Revised for Evidence Intelligence (M1):** claim detail pages now show
a deterministic, no-LLM confidence score (Evidence Quality, Evidence
Consensus, Claim Confidence, Evidence Coverage --
`knowledge_engine_web/evidence_intelligence.py`, independently
rebuilding `core`'s own `docs/evidence_intelligence_design.md` formula).
This is a location change, not a loosening of the seam: the computation
is fully deterministic, reads only already-stored, already-human-reviewed
fields, and never involves an LLM or a judgment call this project makes
itself. See `docs/web_design.md`'s Out of Scope section for the full
rationale, and `core_interface_contract.md`'s own "Revised in M58" note
for the matching change on `core`'s side. What's still the future
`knowledge-engine-ai` layer's job: narrating what a number means, and
anything beyond the Clinical Medicine confidence profile. See
`CONTRIBUTING.md` before adding anything that might blur this line.

## Requirements

- Python 3.12+
- [Poetry](https://python-poetry.org/)
- A `knowledge-engine-core` SQLite database to point at (see `core`'s
  own README for how to build one)

## Installation

```bash
poetry install
```

## Quick Start

Point this project at an existing `core` database and run the dev
server:

```bash
export KE_WEB_DATABASE_URL="sqlite:///path/to/knowledge_engine.sqlite3"
poetry run knowledge-engine-web
```

Then open `http://127.0.0.1:8000/graph` for the graph summary page.

To also show evidence-record content (the actual `claim_text`,
`research_question`, `evidence_direction`, and so on) on claim detail
pages, point this project at `core`'s `evidence_records.jsonl` too:

```bash
export KE_WEB_EVIDENCE_RECORDS_PATH="/path/to/data/corpora/glp1_weight_loss/evidence_records.jsonl"
```

This is optional -- without it, claim detail pages still render graph
structure (concepts, relationships) exactly as before.

By default this binds to `127.0.0.1:8000` (local machine only). To
serve on a local network, or run as a persistent systemd service, see
`docs/deployment.md`.

## Architecture

This project reads `core`'s SQLite database directly, read-only, via
SQLAlchemy table reflection -- it does not import `knowledge_engine` as
a Python package (that would pull in `core`'s full dependency set,
including Phase 3's embedding/vector-search stack, for a page that only
needs a few `SELECT` statements) and it does not redeclare `core`'s
schema by hand (`core_interface_contract.md` explicitly does not
guarantee long-term column stability before v1.0 -- reflection reads
whatever is actually there). See `docs/web_design.md` for the full
design and its Decision, Out of Scope, and Open Questions sections.

## Data Model

This project reads, but never writes, three kinds of `core` data:

- **The knowledge graph** (`graph_concepts`/`graph_claims`/
  `graph_claim_concepts`/`graph_claim_relationships`/`graph_citations`)
  -- SQL tables in `core`'s SQLite database, read via reflection.
- **The FTS5 lexical index** (`paper_search`) -- `core`'s own SQLite
  full-text index over paper title/abstract/body text. `GET /ask`'s
  retrieval query is ported from `core`'s `knowledge_engine.search`
  module rather than imported, same reasoning as the graph reflection
  above (`knowledge_engine_web/retrieval.py`).
- **Evidence Records** -- plain JSONL files `core` produces (e.g.
  `evidence_records.jsonl`), read directly via a configured path
  (`KE_WEB_EVIDENCE_RECORDS_PATH`), never imported from `core`. Rendered
  on claim detail pages when configured (`knowledge_engine_web/evidence_reader.py`).
- **Relationship Records** -- plain JSONL files `core` produces, not yet
  rendered by any page here (see `docs/web_design.md`'s Out of Scope).

## Roadmap

- `GET /graph` -- corpus-wide graph summary (done).
- `GET /claims` / `GET /claims/{evidence_record_id}` -- claim listing and
  detail: concepts by PICO role, relationship edges (done).
- `GET /unconfirmed-claims` -- claims with zero relationship edges of
  any type (done).
- `GET /relationship-candidates` -- claim pairs sharing a PICO-resolved
  concept, for a human to review (done).
- `GET /papers/{paper_id}` -- one paper's citation edges, as citer and
  as cited (done). This completes every page named in this roadmap's
  original list.
- Evidence Record rendering on claim detail pages -- `claim_text`,
  `research_question`, `evidence_direction`, PICO fields,
  `result_summary`, `limitations`, and more, read directly from
  `evidence_records.jsonl` (done; optional via `KE_WEB_EVIDENCE_RECORDS_PATH`).
- Relationship Record rendering -- still needs its own design pass (see
  `docs/web_design.md`'s Out of Scope).
- `KE_WEB_HOST`/`KE_WEB_PORT` and a systemd service example for running
  as a persistent local server (done; see `docs/deployment.md`).
- A password-gated alpha deployment on Render (`Dockerfile`,
  `render.yaml`, `KE_WEB_ALPHA_USERNAME`/`KE_WEB_ALPHA_PASSWORD`) for
  testing hosting, browsers, and real-world latency outside a local
  network -- done; see `docs/deployment.md`'s "Alpha hosting (Render)"
  section. Serves a snapshot, refreshed automatically on a weekly
  schedule (done -- see deployment.md's automation note), not a
  request-time live connection to `core` -- a real API boundary
  remains future work.
- `GET /reports` and `GET /reports/{graph,relationship-candidates,unconfirmed-claims}`
  -- the same Markdown reports `ke graph-report`/`ke graph-relationship-candidates`/
  `ke graph-unconfirmed-claims` print, rebuilt from this site's own data
  and viewable or downloadable as `.md` (done).
- `GET /roadmap` -- what's shipped, what's next, and a clearly-labeled,
  non-functional concept preview of a possible future answer view (done).
- Evidence Intelligence rendering on claim detail pages -- deterministic,
  no-LLM Evidence Quality/Consensus/Claim Confidence/Coverage scores,
  computed from the same stored fields as the Evidence Record section
  above it (done; see "The Seam" above and
  `knowledge_engine_web/evidence_intelligence.py`).
- `GET /ask` -- a question-first page: retrieval over `core`'s FTS5
  index (`knowledge_engine_web/retrieval.py`, ported from `core`'s
  `knowledge_engine.search`, not shelled out to and not imported), each
  matched paper's evidence records (matched by DOI) shown with their own
  Evidence Intelligence numbers where a graph claim exists for them
  (done). Retrieval plus already-computed signals only -- no cross-paper
  synthesis, no single "the answer" verdict; the project owner's first
  piece of a larger question-first "Ask" experience connecting this
  project, `knowledge-engine-ai`, and `core`.

## Repository Family

- [`knowledge-engine-core`](https://github.com/jweter/knowledge-engine-core)
  -- offline scientific document ingestion, evidence validation, and the
  knowledge graph this project renders.
- `knowledge-engine-web` (this repository) -- read-only presentation.
- [`knowledge-engine-ai`](https://github.com/jweter/knowledge-engine-ai)
  -- the judgment layer: Retrieval/Evidence/Analytical/Discovery
  intelligences, research-question crafting, evidence synthesis,
  confidence rating.

## License

MIT. See `LICENSE`.
