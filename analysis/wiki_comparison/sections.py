#!/usr/bin/env python3
"""Split comparison.csv into one file per wiki section, each compound labelled
with the column of the *What it found* table it is counted under.

Read-only and offline: it reads comparison.csv and comparison_d21.csv and
writes sections/<section>.csv, sorted by column in the table's order and then
by name. `column` is compare.bucket(), the same rule the table is printed by,
so the counts it prints are the table's rows.
`with_d21` says whether the compound is a member of the phase1-admission build
(D21) too, so the files answer both of the document's membership tables.

    python3 analysis/wiki_comparison/sections.py
"""
import collections
import csv
import re
import sys

from compare import ORDER, bucket
from placing import HERE

FIELDS = ["name", "wiki_class", "column", "with_d21", "match_tier", "confidence",
          "chembl_parents", "chembl_names", "catalogue_status", "max_phase", "atc_level1",
          "curated_mechanisms", "publication_targets", "gtopdb", "note", "slug"]


def slug(section: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")


def main() -> int:
    rows = list(csv.DictReader(open(HERE / "comparison.csv", encoding="utf-8")))
    d21 = {r["slug"]: r for r in csv.DictReader(open(HERE / "comparison_d21.csv", encoding="utf-8"))}
    if set(d21) != {r["slug"] for r in rows}:
        sys.exit("comparison.csv and comparison_d21.csv do not hold the same compounds")

    by_section = collections.OrderedDict()
    for r in rows:
        out = {k: r[k] for k in FIELDS if k in r}
        out["column"] = bucket(r)
        out["with_d21"] = "member" if d21[r["slug"]]["in_catalogue"] else ""
        by_section.setdefault(r["section"], []).append(out)

    outdir = HERE / "sections"
    outdir.mkdir(exist_ok=True)
    for old in outdir.glob("*.csv"):
        old.unlink()
    for section, members in by_section.items():
        members.sort(key=lambda m: (ORDER.index(m["column"]), m["name"].casefold()))
        with open(outdir / f"{slug(section)}.csv", "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=FIELDS)
            wr.writeheader()
            wr.writerows(members)
        counts = collections.Counter(m["column"] for m in members)
        print(f"{slug(section)}.csv  {len(members):4d}  "
              + "  ".join(f"{c}: {counts[c]}" for c in ORDER if counts[c]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
