#!/usr/bin/env python3
"""Export the cohort database to viz/graph.data.js, viz/gtopdb.data.js and viz/evidence/."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common, export


def main() -> int:
    try:
        r = export.export()
    except common.PolicyError as exc:
        print(f"export failed: {exc}")
        return 2
    for path in r["backups"]:
        print(f"  previous export backed up to {path}")
    if r["stale_shards_removed"]:
        print(f"  removed {r['stale_shards_removed']} shards from the previous build")
    print("  viz/graph.data.js   %6.2f MB  %d molecules, %d targets, %d drawable claims"
          % (r["graph_bytes"] / 1e6, r["molecules"], r["targets"], r["claims_drawable"]))
    print("  viz/gtopdb.data.js  %6.2f MB  %d actions, %d claims, %d entry statuses changed"
          % (r["gtopdb_bytes"] / 1e6, r["gtopdb_actions"], r["gtopdb_claims"],
             r["gtopdb_status_changes"]))
    print("  viz/evidence/      %6.2f MB across %d shards (largest %.0f KB, mean %.0f KB)"
          % (r["evidence_bytes"] / 1e6, r["evidence_shards"],
             r["evidence_largest_shard"] / 1e3,
             r["evidence_bytes"] / max(r["evidence_shards"], 1) / 1e3))
    print("  %d observations, %d retained non-drawable claims" % (
        r["observations"], r["claims_retained"]))
    print("  open viz/index.html in a browser - no server needed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
