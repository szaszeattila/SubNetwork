#!/usr/bin/env python3
"""Backfill molecule_classes and class_labels in db/cohort1.db from ChEMBL 37.

The classes are every WHO ATC code and every USAN/INN name stem ChEMBL records
for any form of each catalogue entry - "Non-selective monoamine reuptake
inhibitors", "-pramine: antidepressants (imipramine type)" - which the viewer
makes searchable and lists a class's molecules from. They are for search and
display only: never evidence about a target, never part of the similarity score.

The build writes these tables (scripts/cohort/classes.py); this script exists
because they arrived after db/cohort1.db was built, and a rebuild would also
wipe the Wikipedia and trial-status backfills, which need the network to redo.
It is the same derivation over the same forms (molecule_forms is the family the
build folded onto each parent), from the same pinned release, so a backfilled
database and a freshly built one carry the same rows.

Offline and read-only against ChEMBL (mode=ro). It creates the two tables if
they are missing and rewrites their contents; it changes no other table and
never changes which molecules exist. Idempotent.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import classes as classes_mod
from cohort import common


def backfill(conn, chembl):
    """Fill both tables on an open cohort connection. Returns a summary."""
    made = classes_mod.ensure_tables(conn)
    before = {tuple(r) for r in conn.execute("SELECT * FROM molecule_classes")}
    form_to_parent = dict(conn.execute("SELECT molregno, parent_molregno FROM molecule_forms"))
    rows, label_rows = classes_mod.collect(chembl, form_to_parent)
    classes_mod.write(conn, rows, label_rows)
    after = {tuple(r) for r in conn.execute("SELECT * FROM molecule_classes")}
    by_source = collections.Counter(r[1] for r in rows)
    with_any = collections.defaultdict(set)
    for r in rows:
        with_any[r[1]].add(r[0])
    n_mol = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
    return {
        "tables_created": made,
        "molecules": n_mol,
        "rows": len(rows),
        "rows_changed": len(before ^ after),
        "by_source": by_source,
        "molecules_by_source": {s: len(v) for s, v in with_any.items()},
        "molecules_with_any": len(set().union(*with_any.values())) if with_any else 0,
        "labels": len(label_rows),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB,
                        help="path to the cohort database (default: db/cohort1.db)")
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    # One explicit transaction, because Python's sqlite3 commits a CREATE TABLE
    # on its own otherwise, and a dry run must leave the schema as it found it.
    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        conn.execute("BEGIN")
        s = backfill(conn, chembl)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
        chembl.close()

    print(f"{s['molecules_with_any']} of {s['molecules']} molecules carry a class; "
          f"{s['rows']} rows ({s['rows_changed']} changed), {s['labels']} class labels"
          + (f" (created {', '.join(s['tables_created'])})" if s["tables_created"] else "")
          + (" - dry run, nothing written" if args.dry_run else ""))
    for source, n in sorted(s["by_source"].items()):
        print(f"  {source:5s} {n:5d} rows over {s['molecules_by_source'][source]} molecules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
