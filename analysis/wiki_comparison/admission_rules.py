#!/usr/bin/env python3
"""What looser admission rules would do: how many of the wiki's ChEMBL-placed
compounds each would let in, and how many ChEMBL parents it would add to the
catalogue in all.

Read-only and adopts nothing. Reads comparison.csv (run compare.py first),
ChEMBL 37, the adopted indication scope and the GtoPdb ligand cache. A rule is
judged on a ChEMBL parent with its salts and forms folded on, as the build
does; the scoped-phase rules use the same scope and max_phase_for_ind as
route_indication, with only the floor moved.

    python3 analysis/wiki_comparison/admission_rules.py [--data-root DIR] [--csv FILE]
"""
import argparse
import collections
import csv
import json
import pathlib
import sqlite3
import sys

from placing import CHEMBL, HERE, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
from cohort import scope as scope_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--csv", type=pathlib.Path, default=HERE / "comparison.csv")
    args = ap.parse_args()

    policy = json.loads((ROOT / "config" / "cohort1_selection.json").read_text())
    in_scope = {k for k, d in scope_mod.load(policy).items() if d.in_scope}
    ch = sqlite3.connect(f"file:{CHEMBL}?mode=ro", uri=True)
    coh = sqlite3.connect(f"file:{args.data_root / 'db' / 'cohort1.db'}?mode=ro", uri=True)

    by_id = {c: m for m, c in ch.execute("SELECT molregno, chembl_id FROM molecule_dictionary")}
    parent = {m: p for m, p in ch.execute("SELECT molregno, parent_molregno FROM molecule_hierarchy") if p}
    P = lambda m: parent.get(m, m)  # noqa: E731
    parents = {P(m) for m in by_id.values()}
    catalogue = {P(by_id[c]) for (c,) in coh.execute("SELECT chembl_id FROM molecules") if c in by_id}

    # Furthest phase per parent, in scope and anywhere; a NULL phase reads -2.
    scoped, anywhere = {}, {}
    for m, phase, mesh in ch.execute("SELECT molregno, max_phase_for_ind, mesh_id FROM drug_indication"):
        v, p = (-2 if phase is None else float(phase)), P(m)
        anywhere[p] = max(anywhere.get(p, -9), v)
        if mesh in in_scope:
            scoped[p] = max(scoped.get(p, -9), v)
    atc = {P(m) for (m,) in ch.execute("SELECT molregno FROM molecule_atc_classification")}
    mech = {P(m) for (m,) in ch.execute("SELECT molregno FROM drug_mechanism")}
    gtopdb = set()
    for row in csv.reader(open(args.data_root / "db" / "cache" / "gtopdb" / "2026.3" / "ligands.csv", encoding="utf-8")):
        gtopdb.update(P(by_id[c]) for c in row if c in by_id)
    # compare.py's crude proxy, ChEMBL-wide: an exact pChEMBL value at a single
    # protein from a publication. Joined here rather than in SQL, which took hours.
    pub_docs = {d for (d,) in ch.execute("SELECT doc_id FROM docs WHERE doc_type = 'PUBLICATION'")}
    single = {t for (t,) in ch.execute("SELECT tid FROM target_dictionary WHERE target_type = 'SINGLE PROTEIN'")}
    single_assays = {a for a, t in ch.execute("SELECT assay_id, tid FROM assays") if t in single}
    published = {P(m) for m, a, d in ch.execute(
        "SELECT molregno, assay_id, doc_id FROM activities WHERE pchembl_value IS NOT NULL AND standard_relation = '='")
        if d in pub_docs and a in single_assays}

    rules = {
        "in-scope indication, phase >= 2": lambda p: scoped.get(p, -9) >= 2,
        "in-scope indication, phase >= 1": lambda p: scoped.get(p, -9) >= 1,
        "in-scope indication, any phase": lambda p: p in scoped,
        "any indication, phase >= 1": lambda p: anywhere.get(p, -9) >= 1,
        "any ATC code": lambda p: p in atc,
        "curated mechanism": lambda p: p in mech,
        "GtoPdb ligand": lambda p: p in gtopdb,
        "in-scope >= 1, or curated, or GtoPdb": lambda p: scoped.get(p, -9) >= 1 or p in mech or p in gtopdb,
        "publication data at any protein": lambda p: p in published,
    }

    wiki = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    members = sum(1 for r in wiki if r["in_catalogue"])
    outside = [r for r in wiki if r["chembl_parents"] and not r["in_catalogue"]]
    hits = lambda r, rule: any(rule(P(by_id[c])) for c in r["chembl_parents"].split("|") if c in by_id)  # noqa: E731

    print(f"{len(wiki)} wiki compounds; {members} in the catalogue; {len(outside)} in ChEMBL and outside it")
    print(f"| rule | wiki added | wiki covered | of {len(wiki)} | catalogue grows by |")
    print("|---|---:|---:|---:|---:|")
    for name, rule in rules.items():
        added = sum(1 for r in outside if hits(r, rule))
        grows = sum(1 for p in parents - catalogue if rule(p))
        print(f"| {name} | {added} | {members + added} | {(members + added) / len(wiki):.0%} | {grows:,} |")
    print(f"| every ChEMBL placement (ceiling) | {len(outside)} | {members + len(outside)} | "
          f"{(members + len(outside)) / len(wiki):.0%} | |")

    best = collections.Counter()
    for r in outside:
        ps = [scoped[P(by_id[c])] for c in r["chembl_parents"].split("|") if c in by_id and P(by_id[c]) in scoped]
        best[max(ps) if ps else "none"] += 1
    print("furthest in-scope phase of the wiki compounds outside:", dict(best))
    return 0


if __name__ == "__main__":
    sys.exit(main())
