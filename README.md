# Knowledge Engine Web

Read-only web interface for the [Knowledge Engine](https://github.com/jweter/knowledge-engine-core)
project. Renders what `knowledge-engine-core` ("`core`") has already
validated -- for a person, in a browser, instead of a terminal. Adds no
synthesis, no confidence rating, no judgment about what a claim or
relationship means.

## Status

Early. One page exists: a read-only summary of `core`'s Phase 4
knowledge graph. See `docs/web_design.md` for the design this project
follows, and `core`'s own `docs/roadmap.md` for where this project fits
in the larger Knowledge Engine roadmap (Phase 5).

## The Seam

`core` locates, validates, and persists evidence. It never decides what
that evidence means for a person's actual question -- see
`knowledge-engine-core/docs/core_interface_contract.md`'s "The seam"
section. This project holds the exact same boundary: it never sets or
infers a `research_question`, an `evidence_direction`, or any confidence
rating beyond what `core` already stores as a free-text
`confidence_note`. That judgment belongs to the future
`knowledge-engine-ai` layer, not this one. See `CONTRIBUTING.md` before
adding anything that might blur this line.

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

This project reads, but never writes, two kinds of `core` data:

- **The knowledge graph** (`graph_concepts`/`graph_claims`/
  `graph_claim_concepts`/`graph_claim_relationships`/`graph_citations`)
  -- SQL tables in `core`'s SQLite database, read via reflection.
- **Evidence Records / Relationship Records** -- plain JSONL files `core`
  produces, not yet rendered by any page here (see `docs/web_design.md`'s
  Out of Scope).

## Roadmap

- `GET /graph` -- corpus-wide graph summary (done).
- `GET /claims` / `GET /claims/{evidence_record_id}` -- claim listing and
  detail: concepts by PICO role, relationship edges (done).
- Paper/citation detail, relationship-candidate, and unconfirmed-claims
  pages -- real next slices, each with a `core` CLI equivalent already
  built (`ke graph-report --paper-id`, `ke graph-relationship-candidates`,
  `ke graph-unconfirmed-claims`).
- Evidence Record rendering -- needs its own design pass first (see
  `docs/web_design.md`'s Out of Scope).

## Repository Family

- [`knowledge-engine-core`](https://github.com/jweter/knowledge-engine-core)
  -- offline scientific document ingestion, evidence validation, and the
  knowledge graph this project renders.
- `knowledge-engine-web` (this repository) -- read-only presentation.
- `knowledge-engine-ai` (future) -- the judgment layer: research-question
  crafting, evidence synthesis, confidence rating.

## License

MIT. See `LICENSE`.
