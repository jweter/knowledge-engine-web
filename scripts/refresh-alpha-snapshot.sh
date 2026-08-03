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
# Usage: scripts/refresh-alpha-snapshot.sh /path/to/knowledge-engine-core [corpus-name]
#   corpus-name defaults to glp1_weight_loss, core's real corpus today.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/knowledge-engine-core [corpus-name]" >&2
  exit 1
fi

core_path="$1"
corpus_name="${2:-glp1_weight_loss}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
web_root="$(dirname "$script_dir")"

database_source="$core_path/data/knowledge_engine.sqlite3"
evidence_source="$core_path/data/corpora/$corpus_name/evidence_records.jsonl"

for path in "$database_source" "$evidence_source"; do
  if [ ! -f "$path" ]; then
    echo "Not found: $path" >&2
    exit 1
  fi
done

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
cp "$evidence_source" "$web_root/data/evidence_records.jsonl"

echo "Snapshot refreshed in $web_root/data/ from $core_path (corpus: $corpus_name)."
echo "This is a point-in-time copy -- commit and push ./data/ to update the deployed alpha."
