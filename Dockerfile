# Alpha deployment image. Bundles a point-in-time snapshot of core's
# database and evidence file at build time -- this is a read-only alpha
# for testing hosting/browsers/latency, not a live-updating service.
# See docs/deployment.md's "Alpha hosting (Render)" section: refresh the
# snapshot with scripts/refresh-alpha-snapshot.sh before each rebuild.
FROM python:3.14-slim AS base

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    PIP_NO_CACHE_DIR=1

# AI-O13: knowledge-engine-ai is a git dependency now, so `poetry install`
# needs `git` on PATH to clone it -- python:3.12-slim doesn't ship it.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==2.4.1

WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root

COPY knowledge_engine_web ./knowledge_engine_web
RUN poetry install --only main

# Snapshot data, refreshed with scripts/refresh-alpha-snapshot.sh and
# committed to the repo -- Render's Docker build clones straight from
# GitHub, so this must already be in the repo, not populated locally
# before `docker build` (that gitignored-local approach broke the first
# real deploy; see docs/deployment.md).
COPY data ./data

ENV KE_WEB_DATABASE_URL=sqlite:////app/data/knowledge_engine.sqlite3 \
    KE_WEB_EVIDENCE_RECORDS_PATH=/app/data/evidence_records.jsonl \
    KE_WEB_SNAPSHOT_METADATA_PATH=/app/data/snapshot_metadata.json \
    KE_WEB_WHATS_CHANGED_BASELINE_PATH=/app/data/whats_changed_baseline.json \
    KE_WEB_HOST=0.0.0.0

EXPOSE 8000

# Render (and most PaaS hosts) inject $PORT at runtime; fall back to
# 8000 for `docker run` without one set.
CMD ["sh", "-c", "KE_WEB_PORT=${PORT:-8000} poetry run knowledge-engine-web"]
