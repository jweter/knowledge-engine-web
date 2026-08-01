#!/usr/bin/env bash
# Copy a point-in-time snapshot of core's database and evidence file into
# ./data/, ready for `docker build` (see ../Dockerfile and
# ../docs/deployment.md's "Alpha hosting (Render)" section).
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
cp "$database_source" "$web_root/data/knowledge_engine.sqlite3"
cp "$evidence_source" "$web_root/data/evidence_records.jsonl"

echo "Snapshot refreshed in $web_root/data/ from $core_path (corpus: $corpus_name)."
echo "This is a point-in-time copy -- rerun this script and rebuild the image to update it."
