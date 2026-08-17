#!/usr/bin/env bash
# Refresh the committed alpha-deployment snapshot in ./data/ from a real
# core checkout, ready to commit and push (see ../Dockerfile and
# ../docs/deployment.md's "Alpha hosting (Render)" section).
#
# The database snapshot is trimmed to only the tables the web app reads
# (scripts/build_alpha_snapshot.py) -- small enough to commit directly,
# since Render's Docker build clones this repo from GitHub with no way
# to run a pre-build script against a gitignored local file.
#
# The graph tables copied from core's database are corpus-agnostic --
# core's own `ke graph-build` writes claims from every corpus into the
# same graph_claims/graph_claim_relationships/etc tables, keyed by
# claim id, not corpus. So evidence_records.jsonl and relationship_records.jsonl
# are merged from every corpus under data/corpora/ too (sorted by corpus
# directory name for a deterministic merge order). The merged relationship
# bytes are also hashed into snapshot_metadata.json so relationship-only
# changes become visible in snapshot provenance even before a live service
# boundary exists.
#
# Usage: scripts/refresh-alpha-snapshot.sh /path/to/knowledge-engine-core

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/knowledge-engine-core" >&2
  exit 1
fi

core_path="$1"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
web_root="$(dirname "$script_dir")"

database_source="$core_path/data/knowledge_engine.sqlite3"
corpora_root="$core_path/data/corpora"

if [ ! -f "$database_source" ]; then
  echo "Not found: $database_source" >&2
  exit 1
fi
if [ ! -d "$corpora_root" ]; then
  echo "Not found: $corpora_root" >&2
  exit 1
fi

corpus_names=()
evidence_sources=()
relationship_sources=()
for corpus_dir in "$corpora_root"/*/; do
  corpus_name="$(basename "$corpus_dir")"
  evidence_path="$corpus_dir/evidence_records.jsonl"
  relationship_path="$corpus_dir/relationship_records.jsonl"
  if [ -f "$evidence_path" ]; then
    corpus_names+=("$corpus_name")
    evidence_sources+=("$evidence_path")
  fi
  if [ -f "$relationship_path" ]; then
    relationship_sources+=("$relationship_path")
  fi
done

if [ "${#evidence_sources[@]}" -eq 0 ]; then
  echo "No evidence_records.jsonl found under $corpora_root" >&2
  exit 1
fi

mkdir -p "$web_root/data"

# Capture a "what changed" baseline from the currently-deployed snapshot
# BEFORE it's replaced below -- the only reliable "before" state the
# report can diff against, since core's own working database has no
# persistent host and graph created_at timestamps do not survive a
# rebuild (see knowledge_engine_web/whats_changed.py's module docstring).
old_database="$web_root/data/knowledge_engine.sqlite3"
old_evidence="$web_root/data/evidence_records.jsonl"
if [ -f "$old_database" ] && [ -f "$old_evidence" ]; then
  (cd "$web_root" && poetry run python3 "$script_dir/capture_whats_changed_baseline.py" \
    "$old_database" "$old_evidence" "$web_root/data/whats_changed_baseline.json")
else
  echo "No existing snapshot to capture a what-changed baseline from -- skipping (first deploy)."
fi

python3 "$script_dir/build_alpha_snapshot.py" "$database_source" "$web_root/data/knowledge_engine.sqlite3"
cat "${evidence_sources[@]}" > "$web_root/data/evidence_records.jsonl"

relationship_output="$web_root/data/relationship_records.jsonl"
if [ "${#relationship_sources[@]}" -gt 0 ]; then
  cat "${relationship_sources[@]}" > "$relationship_output"
else
  rm -f "$relationship_output"
fi

corpus_id="$(IFS=,; echo "${corpus_names[*]}")"
metadata_args=(
  "$core_path"
  "$corpus_id"
  "$web_root/data/knowledge_engine.sqlite3"
  "$web_root/data/evidence_records.jsonl"
  "$web_root/data/snapshot_metadata.json"
)
if [ -f "$relationship_output" ]; then
  metadata_args+=("--relationships" "$relationship_output")
fi
python3 "$script_dir/build_snapshot_metadata.py" "${metadata_args[@]}"

echo "Snapshot refreshed in $web_root/data/ from $core_path (corpora: $corpus_id)."
if [ -f "$relationship_output" ]; then
  echo "Relationship provenance included from ${#relationship_sources[@]} corpus file(s)."
else
  echo "No relationship_records.jsonl inputs were present; metadata records that explicitly."
fi
echo "This is a point-in-time copy -- commit and push ./data/ to update the deployed alpha."
