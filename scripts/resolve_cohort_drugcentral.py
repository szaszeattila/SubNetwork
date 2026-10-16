#!/usr/bin/env python3
"""Backfill molecule_approvals in db/cohort1.db: which regulators approved a molecule, from DrugCentral.

ChEMBL's Approved for a disease often rests on nothing but a WHO ATC class
(293 in-scope records, D23): a classification by use, not a regulator. For 80
of those molecules nothing here traces an approval to anyone. DrugCentral
(drugcentral.org, CC BY-SA 4.0) keeps a molecule-level `approval` table - the
agency (FDA, EMA, PMDA and a few others) and the date it approved the active
ingredient - which turns "classified by WHO ATC" into "approved by EMA, 1998"
where it reaches (D24, docs/D23-GAPS.md gap 2.2). It is not about a disease:
the page says which regulator approved the drug, never that it approved it
for the disease on the row.

Identifiers only (invariant 15). A DrugCentral structure reaches a catalogue
entry through the ChEMBL IDs DrugCentral's `identifier` table files for it
(id_type 'ChEMBL_ID'), matched against the parent's ID and every form's in
molecule_forms. A structure whose IDs reach two entries, or an entry reached
by two structures, is refused and counted, never resolved to one of them: two
structures are two substances to DrugCentral (a racemate and its enantiomer),
and picking one is the guess invariant 6 forbids. DrugCentral's "YEAR
INTRODUCED" rows name no regulator and are left out.

Reads the pinned PostgreSQL dump, `db/cache/drugcentral/<DUMP_NAME>`, checked
against its sha256, with `pg_restore` (PostgreSQL's client, no server and no
RDKit: only two plain tables are read). `pg_restore` is found on PATH or at
$PG_RESTORE; docs/REPRODUCING.md says how to install it. Offline. It writes
only molecule_approvals and one build_manifest key, never which molecules,
targets or claims exist. Idempotent, with --dry-run.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common  # noqa: E402

DUMP_NAME = "Drugcentral_2026-09-25.pgdump"
DUMP_URL = "https://unmtid-dbs.net/download/Drugcentral_2026-09-25.pgdump"
DUMP_SHA256 = "5afea88f6a1916f250c28c10ab988e7464ca6fd5ccf2c42f080600473de732dc"
DUMP = common.ROOT / "db" / "cache" / "drugcentral" / DUMP_NAME
LICENCE = "CC BY-SA 4.0"

# Not a regulator: DrugCentral's year a substance came into use, where no
# agency's approval is recorded.
NOT_A_REGULATOR = {"YEAR INTRODUCED"}

DDL = """
CREATE TABLE IF NOT EXISTS molecule_approvals (
    parent_molregno INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    struct_id       INTEGER NOT NULL,
    agency          TEXT NOT NULL,
    approved        TEXT,
    year            INTEGER,
    applicant       TEXT,
    orphan          INTEGER,
    PRIMARY KEY (parent_molregno, agency)
)
"""


def _unescape(field: str):
    """One field of PostgreSQL's COPY text format: \\N is NULL, backslash escapes."""
    if field == r"\N":
        return None
    if "\\" not in field:
        return field
    out, i = [], 0
    esc = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\", "b": "\b", "f": "\f", "v": "\v"}
    while i < len(field):
        c = field[i]
        if c == "\\" and i + 1 < len(field):
            out.append(esc.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_copy(text: str) -> dict[str, list[dict]]:
    """Every COPY block in a plain-SQL dump, as {table: [row dicts]}."""
    tables: dict[str, list[dict]] = {}
    cols = rows = None
    for line in text.splitlines():
        if cols is None:
            if line.startswith("COPY ") and line.endswith("FROM stdin;"):
                head = line[5:-len("FROM stdin;")].strip()
                name, _, rest = head.partition(" ")
                name = name.split(".")[-1].strip('"')
                cols = [c.strip().strip('"') for c in rest.strip()[1:-1].split(",")]
                rows = tables.setdefault(name, [])
            continue
        if line == "\\.":
            cols = rows = None
            continue
        rows.append(dict(zip(cols, (_unescape(f) for f in line.split("\t")))))
    return tables


def read_dump(path=DUMP) -> dict[str, list[dict]]:
    if not path.exists():
        raise SystemExit(f"{path} is missing: download {DUMP_URL} there "
                         f"(docs/REPRODUCING.md)")
    got = common.sha256(path)
    if got != DUMP_SHA256:
        raise SystemExit(f"{path.name} has sha256 {got}, pinned {DUMP_SHA256}")
    exe = os.environ.get("PG_RESTORE") or shutil.which("pg_restore")
    if not exe:
        raise SystemExit("pg_restore not found: install PostgreSQL's client tools or set "
                         "PG_RESTORE (docs/REPRODUCING.md)")
    out = subprocess.run([exe, "-a", "-f", "-", "-t", "approval", "-t", "identifier",
                          "-t", "dbversion", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return parse_copy(out)


def match(conn, identifiers: list[dict]) -> tuple[dict[int, int], dict]:
    """{parent_molregno: struct_id} by ChEMBL ID, refusing every ambiguity."""
    parent_of = {}
    for p, cid in conn.execute("SELECT parent_molregno, chembl_id FROM molecules"):
        parent_of[cid] = p
    for p, cid in conn.execute("SELECT parent_molregno, chembl_id FROM molecule_forms"):
        if cid:
            parent_of.setdefault(cid, p)
    parents_of_struct = collections.defaultdict(set)
    for r in identifiers:
        if r["id_type"] == "ChEMBL_ID" and r["identifier"] in parent_of:
            parents_of_struct[int(r["struct_id"])].add(parent_of[r["identifier"]])
    structs_of_parent = collections.defaultdict(set)
    shared = set()
    for s, ps in parents_of_struct.items():
        if len(ps) > 1:
            shared.add(s)
            continue
        structs_of_parent[next(iter(ps))].add(s)
    matched, several = {}, {}
    for p, ss in structs_of_parent.items():
        if len(ss) == 1:
            matched[p] = next(iter(ss))
        else:
            several[p] = sorted(ss)
    refused_by_shared = {p for s in shared for p in parents_of_struct[s]} - set(matched)
    return matched, {
        "structures_reaching_two_entries": len(shared),
        "entries_refused_for_a_shared_structure": len(refused_by_shared),
        "entries_reached_by_two_structures": len(several),
    }


def backfill(conn, tables: dict[str, list[dict]]) -> dict:
    conn.execute(DDL)
    matched, refused = match(conn, tables.get("identifier", []))
    by_struct = collections.defaultdict(list)
    for r in tables.get("approval", []):
        by_struct[int(r["struct_id"])].append(r)
    rows, skipped = [], collections.Counter()
    for p, s in sorted(matched.items()):
        for r in by_struct.get(s, ()):
            if r["type"] in NOT_A_REGULATOR:
                skipped[r["type"]] += 1
                continue
            date = r["approval"]
            rows.append((p, s, r["type"], date, int(date[:4]) if date else None,
                         r["applicant"],
                         None if r["orphan"] is None else int(r["orphan"] == "t")))
    conn.execute("DELETE FROM molecule_approvals")
    conn.executemany("INSERT INTO molecule_approvals(parent_molregno, struct_id, agency,"
                     " approved, year, applicant, orphan) VALUES(?,?,?,?,?,?,?)", rows)
    version = (tables.get("dbversion") or [{}])[0]
    by_agency = collections.Counter(r[2] for r in rows)
    summary = {
        "source": "DrugCentral", "url": DUMP_URL, "file": DUMP_NAME, "sha256": DUMP_SHA256,
        "version": version.get("version"), "dated": version.get("dtime"),
        "licence": LICENCE,
        "entries_matched": len(matched),
        "entries_with_an_approval": len({r[0] for r in rows}),
        "approvals": len(rows), "by_agency": dict(sorted(by_agency.items())),
        "left_out": dict(skipped), **refused,
    }
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 ("drugcentral_approvals", json.dumps(summary)))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB,
                        help="path to the cohort database (default: db/cohort1.db)")
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")
    tables = read_dump()
    conn = sqlite3.connect(args.db, isolation_level=None)
    try:
        conn.execute("BEGIN")
        s = backfill(conn, tables)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
    print(f"DrugCentral v{s['version']}: {s['entries_matched']} entries matched by ChEMBL ID, "
          f"{s['entries_with_an_approval']} with a regulator's approval "
          f"({s['approvals']} rows: {s['by_agency']}); refused "
          f"{s['entries_refused_for_a_shared_structure']} entries sharing a structure, "
          f"{s['entries_reached_by_two_structures']} reached by two; left out {s['left_out']}"
          + (" - dry run, nothing written" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
