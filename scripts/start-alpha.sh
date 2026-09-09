#!/bin/sh
# Start the hosted alpha without pretending ephemeral storage is durable.
#
# When an operator-provided persistent mount already exists, bootstrap Core's
# complete writable Research workspace from the committed corpus seed and point
# Web/AI at that durable state. If the mount is absent or preparation fails,
# leave the image's committed retrieval snapshot configured; capability checks
# keep Research Copilot disabled while normal Ask retrieval stays available.

set -u

snapshot_root="/app/data"
persistent_root="${KE_WEB_SESSION_PERSISTENT_ROOT:-}"
core_workspace_snapshot="${KE_WEB_CORE_WORKSPACE_SNAPSHOT:-/opt/knowledge-engine-core/data/corpus_library/obesity_metabolic_disease_library.sqlite3.gz}"

if [ "${KE_WEB_SESSION_STORAGE_MODE:-local}" = "persistent" ] \
  && [ -n "$persistent_root" ] \
  && [ -d "$persistent_root" ] \
  && [ -w "$persistent_root" ]; then
  core_workspace="$persistent_root/core"
  if /opt/ke-research/bin/ke-research-workspace \
      --workspace "$core_workspace" \
      --snapshot "$core_workspace_snapshot"; then
    export KE_WEB_DATABASE_URL="sqlite:///$core_workspace/knowledge_engine.sqlite3"
    export KE_WEB_EVIDENCE_RECORDS_PATH="$core_workspace/evidence_records.jsonl"
    export KE_WEB_SESSION_DB_PATH="$persistent_root/research_sessions.db"
    export KE_WEB_RESEARCH_PAPERS_DIR="$persistent_root/research-papers"
    export KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT="$persistent_root/discovery-ledger"
    mkdir -p "$KE_WEB_RESEARCH_PAPERS_DIR" "$KE_WEB_FEDERATED_DISCOVERY_LEDGER_ROOT"

    # sources.csv remains Web's metadata overlay. Seed it idempotently from the
    # image snapshot while Core owns the writable research database/evidence.
    if poetry run python -m knowledge_engine_web.alpha_workspace seed \
        --snapshot-root "$snapshot_root" \
        --persistent-root "$persistent_root"; then
      export KE_WEB_SOURCES_PATH="$persistent_root/sources.csv"
    else
      echo "Persistent Web metadata preparation failed; continuing retrieval-only." >&2
    fi
  else
    echo "Persistent Core research workspace preparation failed; continuing retrieval-only." >&2
  fi
else
  echo "Persistent research mount not available; continuing retrieval-only." >&2
fi

# Render's Blueprint service references expose a private service as host:port,
# while OllamaLLM expects an absolute HTTP URL. Keep the public application
# configuration provider-neutral and perform the one required interpolation at
# process start. A directly configured KE_WEB_OLLAMA_HOST still takes priority.
if [ -z "${KE_WEB_OLLAMA_HOST:-}" ] && [ -n "${KE_WEB_OLLAMA_HOSTPORT:-}" ]; then
  case "$KE_WEB_OLLAMA_HOSTPORT" in
    http://*|https://*)
      export KE_WEB_OLLAMA_HOST="$KE_WEB_OLLAMA_HOSTPORT"
      ;;
    *)
      export KE_WEB_OLLAMA_HOST="http://$KE_WEB_OLLAMA_HOSTPORT"
      ;;
  esac
fi

export KE_WEB_PORT="${PORT:-${KE_WEB_PORT:-8000}}"
exec poetry run knowledge-engine-web
