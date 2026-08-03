# Service Boundary Design: Beyond the Point-in-Time Snapshot

Status: design doc for the project owner's priority-list item 4 --
"a real service boundary for `knowledge-engine-web`, replacing the
point-in-time Render snapshot deployment with a live connection to
`core`." Written the same way `docs/phase4_design.md` preceded Phase 4's
code: a decision made before implementation, not after.

## The problem, stated honestly

The alpha deployment (`docs/deployment.md`'s "Alpha hosting (Render)"
section) bakes a trimmed copy of `core`'s database into the Docker image
at build time. A weekly Routine narrows the staleness window by
re-running the same refresh and pushing a new snapshot, but it is still
a snapshot on a schedule, not a request-time connection to `core`'s own
data.

## What `core` actually offers today (the real constraint)

`core_interface_contract.md`'s "Data access: two supported paths"
section is the ground truth: direct SQLite read access to a running
database, or the portable `corpus-library` snapshot export/import. There
is no HTTP API, no RPC layer, no published Python package -- "the CLI is
the primary API." Just as importantly: **`core` has no persistent
server today.** It runs inside ephemeral Claude Code sessions and,
per `core`'s own `docs/deployment.md` ("Local Server to Start"), is
only *documented*, not yet *running*, as a persistent systemd service
anywhere. Any design here that assumes a long-lived, network-reachable
`core` process is assuming infrastructure that does not exist yet.

## Options considered

**A. A thin read-only HTTP API in front of `core`'s database**, hosted
alongside a persistent `core` instance, that `web` calls per request
instead of reading a local snapshot file. The architecturally "right"
end state, but it requires `core` to actually run as a persistent,
publicly-reachable service first -- new infrastructure this project
does not have today, and building the API before that host exists means
building and testing it against nothing real.

**B. A shared managed database** (e.g. both `core`'s batch jobs and
`web`'s Render deployment read/write the same hosted Postgres or
managed SQLite-compatible service) instead of `core`'s local SQLite
file. Solves the "no persistent core host" problem by moving the data
instead of the compute, but is a real hosting-cost and migration
decision (`core`'s schema is SQLite-specific today per
`core_interface_contract.md`'s "table layout is not yet a versioned,
published contract" caveat) -- too large a commitment to make as a side
effect of this item.

**C. Shrink the snapshot's staleness window by triggering a refresh on
every relevant merge, not just weekly.** Keeps today's proven
architecture (Docker-baked snapshot, Render redeploys on push) and adds
no new infrastructure -- just changes *when* the existing refresh
Routine fires. Staleness drops from "up to ~7 days" to "typically same
day as the corpus/evidence change that caused it."

**D. A continuously-synced remote SQLite replica** (e.g. Litestream/
LiteFS streaming `core`'s database to object storage `web` reads
directly). An interesting middle ground between A and C, but it is
still new infrastructure (a replication layer) layered on top of a
`core` process that, per the constraint above, does not run
persistently yet -- premature for the same reason as A.

## Decision

**C now; A once `core` has a real persistent host.** This is not a
compromise so much as the only option that doesn't assume
infrastructure this project hasn't built. `core`'s own roadmap already
names "local server to start" as its next deployment step
(`docs/deployment.md`'s status line); once that exists, Option A becomes
a comparatively small addition on top of it (a FastAPI wrapper around
the same `GraphRepository`/reader modules `web` already has, exposed
over the network instead of read from a local file) -- revisit this
doc then, don't build it speculatively now.

## Scope for this milestone (C)

- Wire the corpus-growth-cycle and evidence-extraction-backlog Routines
  (both in `knowledge-engine-core`, both already merge PRs that change
  `sources.csv`/`evidence_records.jsonl`) to trigger the existing
  Web Alpha Snapshot Refresh Routine immediately after a successful
  merge, instead of waiting for its own independent Wednesday schedule.
- No new code in `knowledge_engine_web` itself -- `scripts/
  refresh-alpha-snapshot.sh` and the Refresh Routine's own pipeline are
  unchanged; only the trigger cadence changes.
- Document the new trigger relationship in `docs/deployment.md`'s
  "automated (weekly)" note, since it is no longer purely weekly once
  this ships.

## Explicitly out of scope

- Any new HTTP API, RPC layer, or shared database (Options A/B/D above).
- Real-time, sub-minute freshness -- "same day as the triggering merge"
  is the honest target, not "instant."
- Full-text `/ask` search staying limited to title/abstract in the
  trimmed snapshot (a separate, already-documented recall gap in
  `docs/deployment.md`) -- unaffected by refresh cadence.
- Anything for `core` itself running as a persistent host -- that is
  `core`'s own roadmap item, not `web`'s to build.
