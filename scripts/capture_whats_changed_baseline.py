#!/usr/bin/env python3
"""Capture a "what changed" baseline from the currently-deployed alpha snapshot.

Run as part of `scripts/refresh-alpha-snapshot.sh`, BEFORE the new DB
snapshot overwrites the old one -- see `docs/deployment.md`'s "Alpha
hosting (Render)" section and `knowledge_engine_web/whats_changed.py`'s
own module docstring for why a saved baseline, not graph `created_at`
timestamps, is the only reliable way to compute a real before/after
delta: `core`'s own working database is gitignored and rebuilt from
scratch every session, so `graph_claims.created_at` reflects "when this
graph row was rebuilt this session," not "when the underlying claim was
actually first established."

Run via `poetry run` (unlike `build_alpha_snapshot.py`, which is
deliberately stdlib-only) -- this script reuses
`knowledge_engine_web.whats_changed`'s own aggregation logic rather than
reimplementing Evidence Quality/Coverage a second time in raw SQL.

Usage: poetry run python3 scripts/capture_whats_changed_baseline.py \\
         <db-path> <evidence-path> <baseline-output-path>
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine

from knowledge_engine_web.whats_changed import build_whats_changed_baseline, write_baseline_json


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)

    db_path = Path(sys.argv[1])
    evidence_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])
    if not db_path.is_file():
        raise SystemExit(f"Not found: {db_path}")
    if not evidence_path.is_file():
        raise SystemExit(f"Not found: {evidence_path}")

    engine = create_engine(f"sqlite:///{db_path}")
    baseline = build_whats_changed_baseline(engine, evidence_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_baseline_json(baseline, output_path)
    print(
        f"Captured what-changed baseline to {output_path} "
        f"({len(baseline.claim_evidence_record_ids)} claims, "
        f"{len(baseline.relationship_ids)} relationship edges)."
    )


if __name__ == "__main__":
    main()
