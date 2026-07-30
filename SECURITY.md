# Security Policy

## Supported Versions

Knowledge Engine Web is pre-release software. Security fixes will target the
latest version on `main` until the first stable release policy is defined.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public issues.

Until a private security contact is published, prepare a concise report with:

- Affected version or commit.
- Steps to reproduce.
- Impact.
- Any known workaround.
- Whether the issue involves private data, unsafe file handling, or command
  execution.

Once the repository is published on GitHub, enable private vulnerability
reporting and update this file with the official reporting path.

## Scope

Security-sensitive areas include:

- Rendering `knowledge-engine-core` data (evidence records, graph content)
  into HTML -- every free-text field must be escaped, the same discipline
  `core`'s own `_report_text`/`_graph_report_text` helpers established.
- Read-only database access to `core`'s SQLite file -- this project must
  never write to `core`'s database.
- Future authentication, session handling, and any endpoint accepting
  user input.

## Current Limitations

This is a read-only web interface over a local `knowledge-engine-core`
database. It runs a local network service (unlike `core` itself, which is
offline-only) but performs no writes and has no authentication yet -- do
not expose it beyond a trusted local network until that is addressed.
