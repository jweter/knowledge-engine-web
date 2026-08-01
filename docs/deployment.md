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

## Alpha hosting (Render)

The step beyond a local/LAN server: a small, password-gated public
deployment for testing hosting, browsers, mobile, and real-world
latency -- not "launching" the project. This is explicitly an alpha,
not the eventual public architecture (see "What this does not cover"
below for what real public hosting still needs).

**This deployment serves a point-in-time snapshot, not live data.**
`core`'s SQLite database and `evidence_records.jsonl` are baked into the
Docker image at build time -- there is no live connection back to a
`core` checkout. Refreshing the alpha means re-running the snapshot
script and rebuilding/redeploying the image. This is a deliberate,
documented limitation, not an oversight: a real API/shared-database
boundary between `web` and `core` (rather than `web` reading `core`'s
SQLite file directly) is real, separate infrastructure work for the
eventual public platform, out of scope for a first alpha test.

### 1. Refresh the data snapshot

```bash
scripts/refresh-alpha-snapshot.sh /path/to/knowledge-engine-core
```

Copies `core`'s current database and evidence file into `./data/`
(gitignored -- never committed, but present in the Docker build
context; see `.dockerignore`).

### 2. Set alpha credentials

Required -- the alpha must never be reachable without a password. Pick
any username/password; Render stores these as encrypted environment
variables, never committed:

- `KE_WEB_ALPHA_USERNAME`
- `KE_WEB_ALPHA_PASSWORD`

Both must be set together (`knowledge_engine_web/alpha_auth.py` fails
closed -- every request denied -- if only one is configured, rather
than silently leaving the alpha unprotected).

### 3. Build and test the image locally

```bash
docker build -t knowledge-engine-web-alpha .
docker run -p 8000:8000 \
  -e KE_WEB_ALPHA_USERNAME=tester \
  -e KE_WEB_ALPHA_PASSWORD=<pick-a-password> \
  knowledge-engine-web-alpha
```

Visit `http://127.0.0.1:8000/graph` -- the browser should prompt for
the username/password before showing anything.

### 4. Deploy to Render

`render.yaml` declares a Docker web service. In the Render dashboard:
New -> Blueprint -> point at this repository -> Render reads
`render.yaml` and provisions the service. Set
`KE_WEB_ALPHA_USERNAME`/`KE_WEB_ALPHA_PASSWORD` in the service's
Environment tab (the blueprint marks them `sync: false`, meaning Render
prompts for them rather than storing them in the repo). Render builds
the `Dockerfile` on every push to the connected branch and provides
HTTPS automatically -- no reverse proxy setup needed for this step,
unlike the local-network deployment above.

## What this does not cover

- **A live connection to `core`.** The Render alpha bakes in a
  snapshot; see above. A real API boundary (`web` talking to a service
  over HTTP/gRPC rather than reading SQLite directly) is real,
  unbuilt infrastructure work for beyond the alpha stage.
- **Real multi-user authentication.** The alpha's shared
  username/password is a stopgap for a small testing group, not a
  user-account system -- see `docs/web_design.md`'s Out of Scope.
- **Rate limiting, abuse protection, horizontal scaling.** None of
  this exists yet; not needed for a small, password-gated alpha, but
  real prerequisites before an open public launch.
- **Keeping the underlying `core` database and evidence file up to
  date** for local/LAN deployments. That is `knowledge-engine-core`'s
  own concern (`ke discovery-cycle-run`, `ke graph-build`, etc. -- see
  `docs/m55_discovery_cycle.md`), not something this project manages.
