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
export KE_WEB_RELATIONSHIP_RECORDS_PATH="/path/to/relationship_records.jsonl"
export KE_WEB_LLM_MODEL="qwen2.5:1.5b"  # optional -- enables /ask's synthesis checkbox
poetry run knowledge-engine-web
```

`KE_WEB_LLM_MODEL` is genuinely optional and specific to this kind of
deployment: it requires `ollama serve` already running on the same host
(`ollama pull qwen2.5:1.5b` once) -- see `docs/web_design.md`'s
"Decision: local LLM". This works for local-network serving, but not
for the Render alpha hosting below: a laptop or self-hosted machine
cannot durably run Ollama *for* Render's separate hosted environment,
so `/ask` renders a disabled synthesis control and remains retrieval-only
there until that gets its own architecture. A stale or forged synthesis
request safely degrades to retrieval without exposing environment-variable
details.

The Ollama desktop application running on an operator's laptop is appropriate
for this local or trusted-LAN mode. Enabling Ollama's network exposure is not a
supported way to provide inference to Render: it would couple a public service
to laptop uptime, router and firewall configuration, and an unauthenticated
local model endpoint.

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
Environment=KE_WEB_RELATIONSHIP_RECORDS_PATH=/path/to/data/corpora/glp1_weight_loss/relationship_records.jsonl
Environment=KE_WEB_LLM_MODEL=qwen2.5:1.5b
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
A trimmed copy of `core`'s database and evidence file live in this
repo's `data/` directory and are baked into the Docker image at build
time -- there is no live connection back to a `core` checkout. This is
a deliberate, documented limitation, not an oversight: a real
API/shared-database boundary between `web` and `core` (rather than
`web` reading `core`'s SQLite file directly) is real, separate
infrastructure work for the eventual public platform, out of scope for
a first alpha test.

**The refresh runs on a weekly schedule, plus event-triggered same-day
refreshes.** A scheduled Routine re-runs the exact steps below --
restore `core`'s local working database, rebuild the graph from
whatever `evidence_records.jsonl` currently has on `main`, refresh this
repo's snapshot, commit, push -- every Wednesday as a floor. On top of
that, `core`'s own corpus-growth and evidence-extraction Routines each
fire this refresh Routine directly the same day their own PR merges
real new data (see `docs/service_boundary_design.md`'s "Option C"),
skipping it entirely on a cycle that changed nothing. So the alpha
typically reflects a change same-day, with the weekly schedule as a
backstop rather than the only trigger -- this narrows the gap between
"point-in-time snapshot" and "live connection" without building the
real API boundary yet (`docs/service_boundary_design.md` is the full
decision on why, and what would come next). See "What this does not
cover" below for what's still separate work. A human can still run the
refresh manually at any time with the exact commands in step 1 below.

Relationship-only graph changes are a known exception to the event-triggered
path: unless they accompany corpus growth or evidence extraction, they may wait
for the weekly run or a manual refresh. The current project path calls for this
gap to become visible through a published snapshot revision and for those
changes to trigger or explicitly queue a refresh. Until that work ships, the
alpha must not be described as live or guaranteed same-day for every graph
update.

**The snapshot is committed to the repo, not gitignored.** Render's
Docker build clones this repo directly from GitHub with no way to run
a pre-build script -- a gitignored local `data/` directory (the
original approach) can never reach it, which broke the alpha's first
real deploy (`COPY data ./data` failing with `"/data": not found`).
`scripts/build_alpha_snapshot.py` keeps this safe to commit: it copies
only the tables `knowledge_engine_web` actually reads (graph tables,
`papers`, `journals` for a foreign-key reference, and `paper_search` --
the FTS5 index `/ask` queries) out of `core`'s full database, which is
hundreds of megabytes of raw paper text and embeddings this app mostly
never touches. The trimmed result is a few megabytes -- small enough
to commit directly. **These graph tables are corpus-agnostic** -- every
corpus `core` has (GLP-1, oncology, mental health, ...) writes into the
same tables via `ke graph-build`, so `scripts/refresh-alpha-snapshot.sh`
merges `evidence_records.jsonl` from every corpus directory under
`core`'s `data/corpora/`, not just one. Otherwise a claim from a corpus
other than GLP-1 would show up on `/graph` with no evidence available
on its detail page. **`paper_search` is indexed on title/abstract only,
not full body text**, which is what makes up most of `core`'s database
size (~120 MB across today's corpus); a snapshot with full-text search
included would be far too large to commit. This means the alpha's
`/ask` page only matches title/abstract content, not full paper text --
a real, documented recall gap for this deployment, not a bug.

### 1. Refresh the data snapshot

Automated weekly (see above) -- this is the manual/ad-hoc equivalent,
for refreshing sooner than the schedule or debugging the automation
itself:

```bash
scripts/refresh-alpha-snapshot.sh /path/to/knowledge-engine-core
git add data/ && git commit -m "Refresh alpha snapshot" && git push
```

Rebuilds `./data/knowledge_engine.sqlite3` (trimmed, via
`scripts/build_alpha_snapshot.py`) and copies `evidence_records.jsonl`
verbatim. Before doing so, it also captures a `GET /reports/what-changed`
baseline (`scripts/capture_whats_changed_baseline.py`) from the
currently-deployed snapshot into `./data/whats_changed_baseline.json` --
the only reliable "before" state that report can diff against, since
`core`'s own working database has no persistent host and graph
`created_at` timestamps do not survive a rebuild (see
`knowledge_engine_web/whats_changed.py`'s module docstring). Commit and
push all three files -- Render redeploys automatically on a push to the
connected branch. The automated Routine follows a PR (draft -> CI ->
ready -> squash-merge), same as every other change in this project's
history; a manual refresh may push directly if you prefer, since it's a
generated data artifact, not source code.

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
  snapshot; see above. The weekly automated refresh narrows how stale
  that snapshot gets, but it is still a snapshot, refreshed on a
  schedule -- not a request-time connection back to `core`. A real API
  boundary (`web` talking to a service over HTTP/gRPC rather than
  reading SQLite directly) is real, unbuilt infrastructure work for
  beyond the alpha stage.
- **Full-text `/ask` search.** The committed snapshot's `paper_search`
  index covers title/abstract only, not full body text (see above) --
  a real recall gap versus a local/LAN deployment reading `core`'s
  full database directly.
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
