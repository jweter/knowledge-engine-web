#!/bin/sh
# Start the hosted alpha without pretending ephemeral storage is durable.
#
# When an operator-provided persistent mount already exists, seed the mutable
# Research Copilot inputs from the image snapshot and point Web at those
# durable copies. If the mount is absent or preparation fails, leave the
# image's committed retrieval snapshot configured; capability checks will keep
# Research Copilot disabled while normal Ask retrieval stays available.

set -u

snapshot_root="/app/data"
persistent_root="${KE_WEB_SESSION_PERSISTENT_ROOT:-}"

if [ "${KE_WEB_SESSION_STORAGE_MODE:-local}" = "persistent" ] \
  && [ -n "$persistent_root" ] \
  && [ -d "$persistent_root" ] \
  && [ -w "$persistent_root" ]; then
  if poetry run python -m knowledge_engine_web.alpha_workspace seed \
      --snapshot-root "$snapshot_root" \
      --persistent-root "$persistent_root"; then
    export KE_WEB_EVIDENCE_RECORDS_PATH="$persistent_root/evidence_records.jsonl"
    export KE_WEB_SOURCES_PATH="$persistent_root/sources.csv"
  else
    echo "Persistent research workspace preparation failed; continuing retrieval-only." >&2
  fi
else
  echo "Persistent research mount not available; continuing retrieval-only." >&2
fi

export KE_WEB_PORT="${PORT:-${KE_WEB_PORT:-8000}}"
exec poetry run knowledge-engine-web
