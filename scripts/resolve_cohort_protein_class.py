#!/usr/bin/env python3
"""Backfill target_components.protein_class in db/cohort1.db from ChEMBL 37.

protein_class is ChEMBL's protein classification of each component at levels
1 and 2 ("Ion channel > Ligand-gated ion channel"). The viewer reads it for one
thing: which PROTEIN COMPLEX and PROTEIN COMPLEX GROUP targets are ion-channel
assemblies - GABA-A, nicotinic, NMDA, AMPA, kainate, 5-HT3, glycine, Cav, KCNQ
- whose subunits it lays out as one unit, because they never work apart.
Kinase pairs, receptor heteromers and nuclear-receptor dimers are complexes in
ChEMBL too, and their parts do work alone, so a complex type on its own could
not draw that line.

The build writes this column (scripts/cohort/targets.py protein_classes); this
script exists because the column arrived after db/cohort1.db was built, and a
rebuild would also wipe the Wikipedia and trial-status backfills, which need
the network to redo. It is the same derivation, from the same pinned release,
so a backfilled database and a freshly built one carry the same values.

Offline and read-only against ChEMBL (mode=ro). It changes no table but
target_components and no column but protein_class: it never changes which
rows exist. Idempotent: it adds the column if missing and rewrites every
row's value, so rerunning it is a no-op on an up-to-date database.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common
from cohort import targets as targets_mod


def _ensure_column(conn):
    cols = {c[1] for c in conn.execute("PRAGMA table_info(target_components)")}
    if "protein_class" not in cols:
        conn.execute("ALTER TABLE target_components ADD COLUMN protein_class TEXT")
        return True
    return False


def backfill(conn, chembl):
    """Fill protein_class on an open cohort connection. Returns a summary."""
    added = _ensure_column(conn)
    accessions = {r[0] for r in conn.execute(
        "SELECT DISTINCT accession FROM target_components")}
    classes = targets_mod.protein_classes(chembl, accessions)
    before = dict(conn.execute("SELECT target_chembl_id || '|' || accession,"
                               " protein_class FROM target_components"))
    conn.executemany("UPDATE target_components SET protein_class = ? WHERE accession = ?",
                     [(classes.get(a), a) for a in sorted(accessions)])
    after = dict(conn.execute("SELECT target_chembl_id || '|' || accession,"
                              " protein_class FROM target_components"))
    by_l1 = collections.Counter()
    for value in classes.values():
        for path in value.split("|"):
            by_l1[path.split(" > ")[0]] += 1
    return {
        "column_added": added,
        "accessions": len(accessions),
        "classified": len(classes),
        "rows_changed": sum(1 for k in after if after[k] != before.get(k)),
        "by_level1": by_l1,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB,
                        help="path to the cohort database (default: db/cohort1.db)")
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    # One explicit transaction, because Python's sqlite3 commits an ALTER TABLE
    # on its own otherwise, and a dry run must leave the schema as it found it.
    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        conn.execute("BEGIN")
        summary = backfill(conn, chembl)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
        chembl.close()

    print(f"{summary['classified']} of {summary['accessions']} component accessions "
          f"classified; {summary['rows_changed']} rows changed"
          + (" (column added)" if summary["column_added"] else "")
          + (" - dry run, nothing written" if args.dry_run else ""))
    for name, n in summary["by_level1"].most_common():
        print(f"  {n:5d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
