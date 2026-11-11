#!/usr/bin/env python3
"""Backfill observations.assay_action_type in db/cohort1.db from ChEMBL 37.

ChEMBL attaches an action word to some single activity records
(activities.action_type: AGONIST, ANTAGONIST, INHIBITOR, ...), and its
action_type table files each word under a parent (POSITIVE MODULATOR,
NEGATIVE MODULATOR, OTHER). This copies both onto the observation the
activity became, verbatim (D28).

The word describes one assay's readout. From a binding assay it is not a
direction - every triptan is ANTAGONIST at 5-HT1B/1D on a Ki from one review,
cabergoline INHIBITOR at D2 - and nothing reads it. From a functional assay
the export ships it, and the page shows it as a direction at the pair, named
as ChEMBL's assay label. It never changes a tier, a claim, a line's colour, the
mechanism filter or D15's oppositions (docs/COHORT-2.md, D28).

The build writes these columns (scripts/cohort/evidence.py ACTIVITY_SQL); this
script exists because they arrived after db/cohort1.db was built, and a
rebuild would also wipe the backfills that need the network to redo. It is the
same derivation, from the same pinned release, so a backfilled database and a
freshly built one carry the same values.

Offline and read-only against ChEMBL (mode=ro). It changes no table but
observations and no columns but these two: it never changes which rows exist.
Idempotent: it adds the columns if missing and rewrites every row's value, so
rerunning it is a no-op on an up-to-date database.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common

COLUMNS = ("assay_action_type", "assay_action_parent_type")


def _ensure_columns(conn):
    have = {c[1] for c in conn.execute("PRAGMA table_info(observations)")}
    added = []
    for col in COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE observations ADD COLUMN {col} TEXT")
            added.append(col)
    return added


def labels(chembl, activity_ids):
    """{activity_id: (action_type, parent_type)} for the ids ChEMBL labels."""
    out = {}
    for chunk in common.chunked(sorted(activity_ids)):
        marks = ",".join("?" * len(chunk))
        for row in chembl.execute(
                f"SELECT act.activity_id, act.action_type, aat.parent_type"
                f"  FROM activities act"
                f"  LEFT JOIN action_type aat ON aat.action_type = act.action_type"
                f" WHERE act.activity_id IN ({marks}) AND act.action_type IS NOT NULL",
                chunk):
            out[row[0]] = (row[1], row[2])
    return out


def backfill(conn, chembl):
    """Fill both columns on an open cohort connection. Returns a summary."""
    added = _ensure_columns(conn)
    before = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT activity_id, assay_action_type, assay_action_parent_type FROM observations")}
    found = labels(chembl, before)
    conn.executemany(
        "UPDATE observations SET assay_action_type = ?, assay_action_parent_type = ?"
        " WHERE activity_id = ?",
        [(found.get(a, (None, None))[0], found.get(a, (None, None))[1], a)
         for a in sorted(before)])
    by_kind = collections.Counter()
    for assay_type, parent in conn.execute(
            "SELECT assay_type, assay_action_parent_type FROM observations"
            " WHERE assay_action_type IS NOT NULL"):
        by_kind[(assay_type or "?", parent or "unfiled")] += 1
    return {
        "columns_added": added,
        "observations": len(before),
        "labelled": len(found),
        "rows_changed": sum(1 for a, v in before.items()
                            if v != found.get(a, (None, None))),
        "by_kind": by_kind,
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

    print(f"{summary['labelled']} of {summary['observations']} observations carry "
          f"ChEMBL's assay label; {summary['rows_changed']} rows changed"
          + (f" (added {', '.join(summary['columns_added'])})"
             if summary["columns_added"] else "")
          + (" - dry run, nothing written" if args.dry_run else ""))
    for (assay_type, parent), n in sorted(summary["by_kind"].items()):
        print(f"  {n:6d}  assay type {assay_type}, {parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
