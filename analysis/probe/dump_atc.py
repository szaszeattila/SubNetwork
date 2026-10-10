#!/usr/bin/env python3
"""Dump every ATC code ChEMBL has for each cohort molecule, not only level N.

The cohort database stores `molecules.atc_level5` from a query written as the
route_atc_n admission test (`WHERE a.level1 = 'N'`), and the similarity harness
then reads that column as its answer key -- so the key inherits an admission
filter. This writes the unfiltered version beside it so the two can be graded
against each other without a rebuild.

Read-only on both databases. Writes one JSON file of identifiers and codes.
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

CHEMBL = "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db"
COHORT = "db/cohort1.db"
OUT = Path("analysis/probe/atc_full.json")


def main() -> int:
    coh = sqlite3.connect(f"file:{COHORT}?mode=ro", uri=True)
    parents = dict(coh.execute(
        "SELECT parent_molregno, chembl_id FROM molecules").fetchall())
    coh.close()

    ch = sqlite3.connect(f"file:{CHEMBL}?mode=ro", uri=True)
    # Rolled up to the parent through molecule_hierarchy exactly as
    # scripts/cohort/selection.py does, so a salt's ATC code reaches the parent
    # the catalogue actually holds.
    rows = ch.execute("""
        SELECT COALESCE(mh.parent_molregno, mac.molregno) AS parent, a.level5
          FROM molecule_atc_classification mac
          JOIN atc_classification a ON a.level5 = mac.level5
          LEFT JOIN molecule_hierarchy mh ON mh.molregno = mac.molregno
    """).fetchall()
    ch.close()

    by_chembl = defaultdict(set)
    for parent, level5 in rows:
        chembl_id = parents.get(parent)
        if chembl_id and level5:
            by_chembl[chembl_id].add(level5)

    payload = {k: sorted(v) for k, v in sorted(by_chembl.items())}
    OUT.write_text(json.dumps(payload, indent=0))
    print(f"{len(payload)} cohort molecules carry at least one ATC code")
    print(f"{sum(len(v) for v in payload.values())} codes written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
