#!/usr/bin/env python3
"""How much of the ATC answer key the build's `level1 = 'N'` filter discards.

`molecules.atc_level5` is populated by a query written as the *admission* test
for route_atc_n (scripts/cohort/selection.py, `WHERE a.level1 = 'N'`). The
similarity harness then reads that column as its answer key, so the key inherits
a filter that was never meant to define one. This measures what a key over every
ATC level would hold instead.

Read-only. It opens ChEMBL mode=ro and the cohort database read-only, and
adopts nothing.
"""
import sqlite3
import sys
from collections import defaultdict

CHEMBL = "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db"
COHORT = "db/cohort1.db"


def main() -> int:
    coh = sqlite3.connect(f"file:{COHORT}?mode=ro", uri=True)
    rows = coh.execute(
        "SELECT parent_molregno, chembl_id, pref_name, atc_level5 FROM molecules"
    ).fetchall()
    coh.close()
    parents = {r[0]: r for r in rows}
    print(f"cohort molecules: {len(parents)}")
    have_n = sum(1 for r in rows if r[3])
    print(f"carrying an ATC N code today: {have_n}")

    ch = sqlite3.connect(f"file:{CHEMBL}?mode=ro", uri=True)
    # Same shape as selection.py's query, minus the level1 filter: a molecule's
    # ATC codes are taken across its whole compound family, rolled up to the
    # parent through molecule_hierarchy exactly as the build does.
    q = """
        SELECT COALESCE(mh.parent_molregno, mac.molregno) AS parent,
               a.level5, a.level4, a.level1
          FROM molecule_atc_classification mac
          JOIN atc_classification a ON a.level5 = mac.level5
          LEFT JOIN molecule_hierarchy mh ON mh.molregno = mac.molregno
    """
    by_parent = defaultdict(set)
    for parent, l5, l4, l1 in ch.execute(q):
        if parent in parents:
            by_parent[parent].add((l5, l4, l1))
    ch.close()

    lvl1 = defaultdict(set)
    for parent, codes in by_parent.items():
        for _l5, _l4, l1 in codes:
            lvl1[l1].add(parent)
    print("\nATC level-1 spread over the SAME cohort, filter removed:")
    for l1, mols in sorted(lvl1.items(), key=lambda kv: -len(kv[1])):
        print(f"  {l1}  molecules {len(mols)}")

    # The key as the harness builds it: level-4 classes, X dropped, size >= 2.
    def build_key(keep):
        members = defaultdict(set)
        for parent, codes in by_parent.items():
            for _l5, l4, l1 in codes:
                if not keep(l1):
                    continue
                if len(l4) != 5 or l4[4] == "X":
                    continue
                members[l4].add(parent)
        members = {c: s for c, s in members.items() if len(s) >= 2}
        mols = set()
        for s in members.values():
            mols |= s
        return members, mols

    n_cls, n_mols = build_key(lambda l1: l1 == "N")
    a_cls, a_mols = build_key(lambda l1: True)
    print(f"\nkey, N only        : {len(n_mols)} molecules in {len(n_cls)} classes")
    print(f"key, every level-1 : {len(a_mols)} molecules in {len(a_cls)} classes")
    print(f"  added molecules  : {len(a_mols - n_mols)}")
    print(f"  added classes    : {len(set(a_cls) - set(n_cls))}")

    non_n = {c: s for c, s in a_cls.items() if c[0] != "N"}
    print(f"\nnon-N classes of 3 or more ({sum(1 for s in non_n.values() if len(s) >= 3)}):")
    for code, s in sorted(non_n.items(), key=lambda kv: -len(kv[1])):
        if len(s) < 3:
            continue
        names = sorted(parents[p][2] or parents[p][1] for p in s)
        print(f"  {code}  n={len(s):<3} {', '.join(names[:6])}"
              + (" ..." if len(names) > 6 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
