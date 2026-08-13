# AI-O15 Deployed Research Session Persistence

## Status

Implemented as an explicit storage policy and deployment gate. No persistent
disk has been purchased or provisioned by this change.

## Decision

Research Copilot may use ordinary local SQLite storage for development and a
trusted single-machine deployment. A persistent/public deployment must declare
`persistent` session storage and keep the session database canonically inside a
configured persistent mount.

Ephemeral sessions are not acceptable for the public alpha. A displayed
session ID is a promise that the research history can be inspected later;
silently losing it on a restart or deploy would violate that promise.

SQLite remains the correct smallest durable store for the current
single-instance alpha. Moving the session schema to PostgreSQL would duplicate
the AI repository's tested persistence layer before multi-instance or remote
database requirements exist.

## Configuration Contract

Local development defaults:

```text
KE_WEB_SESSION_STORAGE_MODE=local
KE_WEB_SESSION_DB_PATH=data/research_sessions.db
```

Persistent deployment:

```text
KE_WEB_SESSION_STORAGE_MODE=persistent
KE_WEB_SESSION_PERSISTENT_ROOT=/var/data
KE_WEB_SESSION_DB_PATH=/var/data/research_sessions.sqlite3
```

`persistent` mode is available only when:

1. the root and database paths are absolute;
2. the configured root exists and is a writable directory;
3. the session database is a writable file or has a writable existing parent;
4. canonical path resolution places the database below the persistent root;
5. the database path is not the root directory itself; and
6. symlink resolution does not escape the persistent root.

Failure produces a stable capability reason and keeps `/ask` retrieval-only.
No private path or operator configuration detail is rendered to visitors.

## Render Operator Procedure

Render filesystems are ephemeral by default. Render's official persistent-disk
documentation states that only files under the configured mount survive
deploys and restarts, and that disks are available to paid services:
https://render.com/docs/disks

The committed blueprint declares persistent mode with `/var/data`, but does not
include a `disk` resource. This is intentional: merging code must not purchase
infrastructure or alter billing without an operator decision.

Before enabling Research Copilot on Render, an operator must:

1. attach a Render persistent disk to `knowledge-engine-web-alpha`;
2. mount it at `/var/data`;
3. choose and approve its size and recurring cost;
4. confirm the three committed session settings above are active;
5. verify the mount is writable in the running service;
6. create a real Research Copilot session;
7. restart or redeploy the service; and
8. reopen the same SQLite store and verify the session and events remain.

Render documents that a disk is attached to one service instance, prevents
horizontal scaling, and removes zero-downtime deploys. Those constraints are
acceptable for a single-instance alpha and must be revisited before scaling.

## Resume Integrity

`knowledge-engine-ai.SessionRepository` already supports reopening the SQLite
database and reading or continuing existing session/event state. AI-O15 tests
the web-selected path and its persistence policy; it does not add a web resume
route because the composed `/ask` workflow does not yet define continuation of
an existing `run_research_question` session.

The operator verification above proves storage survival. A user-facing resume
workflow requires its own contract for authorization, terminal-session
behavior, and idempotent continuation; it must not be implied by merely showing
a session ID.

## Security And Failure Behavior

- Canonical containment is used instead of string-prefix comparison.
- Symlink escapes fail closed.
- Capability checks do not create directories, databases, or disks.
- A missing mount cannot silently fall back to the container filesystem.
- Research Copilot remains unavailable when durable mode is misconfigured.
- Deterministic retrieval remains available.
- Session data stays on the one configured service volume.

The persistent SQLite file may contain research questions, model/tool events,
source identifiers, and verification outcomes. Access therefore remains within
the password-gated service and Render operator boundary. Backup and retention
policy must be decided before broader or sensitive use.

## Tests

The test suite covers:

- unchanged local-mode behavior;
- a persistent database inside its mount;
- missing persistent-root configuration;
- a database outside the mount;
- symlink escape where the test platform permits symlink creation;
- non-mutating capability evaluation;
- environment-variable parsing; and
- the Render blueprint's fail-closed persistent declaration.

## Non-Goals

AI-O15 does not:

- provision or purchase a Render disk;
- enable public Research Copilot;
- expose a session-history or resume route;
- migrate Research Sessions to PostgreSQL;
- add multi-instance database coordination;
- add retention, deletion, export, or backup UI;
- add rate limiting, timeouts, or job cancellation; or
- change evidence, retrieval, verification, or synthesis behavior.

## Next Handoff

AI-O16: guard the real compute-bearing endpoint with bounded execution,
concurrency/rate controls, and an honest in-progress/failure experience. The
hosted-inference decision remains a separate prerequisite before AI-O17 can
claim a public end-to-end Research Copilot run.
