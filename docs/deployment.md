# Deployment: Local Server to Start

Status: documents this project's current, real deployment surface --
running as a systemd service on a self-hosted machine, matching the
project owner's stated end state ("local server to start"). Written
the same way `knowledge-engine-core`'s `docs/m55_discovery_cycle.md`
documents its own crontab/systemd examples: concrete and copy-pasteable,
but not auto-installed, since the actual host, paths, and TLS/reverse-
proxy setup are operator decisions this project does not make for you.

## What changed to make this possible

`run()` (the `poetry run knowledge-engine-web` entry point) used to
hardcode `host="127.0.0.1", port=8000` -- correct for local development,
but unusable for anything beyond the machine it runs on. It now reads
`KE_WEB_HOST`/`KE_WEB_PORT` from `Settings` (same `KE_WEB_` prefix as
`KE_WEB_DATABASE_URL`), defaulting to the exact same `127.0.0.1:8000` as
before -- **binding beyond localhost is opt-in, never automatic.**

## Serving on a local network

```bash
export KE_WEB_HOST="0.0.0.0"
export KE_WEB_PORT="8000"
export KE_WEB_DATABASE_URL="sqlite:///path/to/knowledge_engine.sqlite3"
export KE_WEB_EVIDENCE_RECORDS_PATH="/path/to/evidence_records.jsonl"
poetry run knowledge-engine-web
```

`0.0.0.0` binds every network interface on the host -- reachable from
other machines on the same local network at `http://<host-ip>:8000`.
This project has no authentication, rate-limiting, or write access of
any kind (see `docs/web_design.md`'s Out of Scope), so treat this as
trusted-network-only. It is explicitly **not** a hardening story for
public internet exposure -- that remains deliberately out of scope
until there is real concurrent read+write traffic to design against
(the same "verify against real data before designing" discipline this
project follows everywhere else), not something to scaffold
speculatively now.

## Running it as a systemd service

For a machine that should keep `knowledge-engine-web` running across
reboots -- the concrete "local server" this project's owner is building
toward:

```ini
# /etc/systemd/system/knowledge-engine-web.service
[Unit]
Description=Knowledge Engine Web
After=network.target

[Service]
Type=simple
User=knowledge-engine
WorkingDirectory=/path/to/knowledge-engine-web
Environment=KE_WEB_HOST=0.0.0.0
Environment=KE_WEB_PORT=8000
Environment=KE_WEB_DATABASE_URL=sqlite:////path/to/data/knowledge_engine.sqlite3
Environment=KE_WEB_EVIDENCE_RECORDS_PATH=/path/to/data/corpora/glp1_weight_loss/evidence_records.jsonl
ExecStart=/path/to/poetry run knowledge-engine-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now knowledge-engine-web
sudo systemctl status knowledge-engine-web
```

Use an absolute `sqlite:////...` URL (four slashes) here, not a
relative one -- systemd's `WorkingDirectory` is not always what an
operator expects, and a relative path silently pointing at an empty
database is a worse failure mode than an explicit absolute one.

## What this does not cover

- **TLS/HTTPS.** Put a reverse proxy (nginx, Caddy) in front if serving
  beyond a trusted local network; this project speaks plain HTTP only.
- **Authentication, multi-user support.** Explicitly out of scope --
  see `docs/web_design.md`.
- **Public internet exposure.** Deliberately deferred; see above.
- **Keeping the underlying `core` database and evidence file up to
  date.** That is `knowledge-engine-core`'s own concern (`ke
  discovery-cycle-run`, `ke graph-build`, etc. -- see
  `docs/m55_discovery_cycle.md`), not something this project manages.
