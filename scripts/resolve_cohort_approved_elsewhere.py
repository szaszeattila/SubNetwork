#!/usr/bin/env python3
"""Backfill molecules.approved_elsewhere in db/cohort1.db from ChEMBL 37.

approved_elsewhere names the diseases a molecule's family is approved for
(phase 4) outside the adopted scope. The viewer's indication list holds only
in-scope diseases, so 327 of the 900 approved entries showed "approved" over a
list with no approval in it - bromazepam is approved for Anxiety and listed
only at phase 3 for dementia, depression and schizophrenia. The column lets
that line say what the approval was for.

The build writes this column (scripts/cohort/selection.py
approved_out_of_scope); this script exists because the column arrived after
db/cohort1.db was built, and a rebuild would also wipe the network backfills.
It is the same derivation from the same pinned release: scope is read from the
database's own indication_scope table and families from molecule_forms, which
are what the build wrote from that release.

Offline and read-only against ChEMBL (mode=ro). It changes no column but
molecules.approved_elsewhere and never changes which rows exist. Idempotent:
it adds the column if missing and rewrites every row's value.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common
from cohort import selection


def _ensure_column(conn):
    cols = {c[1] for c in conn.execute("PRAGMA table_info(molecules)")}
    if "approved_elsewhere" not in cols:
        conn.execute("ALTER TABLE molecules ADD COLUMN approved_elsewhere TEXT")
        return True
    return False


def backfill(conn, chembl):
    """Fill approved_elsewhere on an open cohort connection. Returns a summary."""
    added = _ensure_column(conn)
    in_scope = {r[0] for r in conn.execute(
        "SELECT mesh_id FROM indication_scope WHERE in_scope = 1")}
    families = collections.defaultdict(set)
    for parent, member in conn.execute("SELECT parent_molregno, molregno FROM molecule_forms"):
        families[parent].add(member)
    parents = [r[0] for r in conn.execute("SELECT parent_molregno FROM molecules")]
    for p in parents:
        families[p].add(p)
    chembl.row_factory = sqlite3.Row
    ind_rows = chembl.execute(
        "SELECT molregno, max_phase_for_ind, mesh_id, mesh_heading"
        " FROM drug_indication ORDER BY drugind_id").fetchall()
    by_mol = selection.approved_out_of_scope(ind_rows, in_scope)
    values = {p: selection.approved_for_family(by_mol, sorted(families[p])) for p in parents}
    before = dict(conn.execute("SELECT parent_molregno, approved_elsewhere FROM molecules"))
    conn.executemany("UPDATE molecules SET approved_elsewhere = ? WHERE parent_molregno = ?",
                     [("|".join(v) if v else None, p) for p, v in values.items()])
    after = dict(conn.execute("SELECT parent_molregno, approved_elsewhere FROM molecules"))
    return {
        "column_added": added,
        "molecules": len(parents),
        "with_value": sum(1 for v in values.values() if v),
        "rows_changed": sum(1 for k in after if after[k] != before.get(k)),
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

    print(f"{summary['with_value']} of {summary['molecules']} molecules are approved for a "
          f"disease outside the adopted scope; {summary['rows_changed']} rows changed"
          + (" (column added)" if summary["column_added"] else "")
          + (" - dry run, nothing written" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
