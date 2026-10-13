#!/usr/bin/env python3
"""Place every compound in wiki_compounds.csv against ChEMBL 37 and the active
catalogue, and say what ChEMBL holds for the ones outside it.

Read-only and adopts nothing: ChEMBL and db/cohort1.db are opened mode=ro, and
the output is comparison.csv plus a summary on stdout. How a name is placed,
and what each tier's confidence means, is in placing.py. A name reaching
several ChEMBL parents keeps all of them; REJECTED there lists the matches
found wrong on review, and the reason stays on the row.

    python3 analysis/wiki_comparison/compare.py [--data-root DIR] [--csv OUT]

--data-root is the checkout holding db/cohort1.db and db/cache/ (both
gitignored), for running from a worktree that has no build of its own.
"""
import argparse
import collections
import csv
import json
import pathlib
import sys

from placing import HERE, ROOT, Placer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--csv", type=pathlib.Path, default=HERE / "comparison.csv")
    args = ap.parse_args()

    wiki = list(csv.DictReader(open(HERE / "wiki_compounds.csv", encoding="utf-8")))
    pl = Placer(args.data_root)
    ch = pl.ch

    need_pubchem, out = [], []
    for w in wiki:
        got, tier, note, confidence = pl.place(w["name"])
        if tier == "not_looked_up":
            need_pubchem.append(w["name"])
        ids = pl.ids(got)
        row = dict(w, match_tier=tier, confidence=confidence, note=note,
                   chembl_parents="|".join(ids),
                   chembl_names="|".join(sorted({pl.pref_name[p] for p in got if pl.pref_name.get(p)})),
                   in_catalogue="|".join(c for c in ids if c in pl.catalogue),
                   catalogue_status="|".join(f"{pl.catalogue[c][0]}/{pl.catalogue[c][1]}"
                                             for c in ids if c in pl.catalogue),
                   max_phase="", atc_level1="", curated_mechanisms="", publication_targets="", gtopdb="")
        if got:
            fam = [m for (m,) in ch.execute(
                f"SELECT molregno FROM molecule_hierarchy WHERE parent_molregno IN ({','.join('?' * len(got))})",
                sorted(got))] or sorted(got)
            q = ",".join("?" * len(fam))
            phases = [x for (x,) in ch.execute(f"SELECT max_phase FROM molecule_dictionary WHERE molregno IN ({q})", fam)
                      if x is not None]
            # A crude proxy for "would an edge be drawn": distinct single
            # proteins with an exact pChEMBL value from a publication.
            targets = ch.execute(f"""
                SELECT COUNT(DISTINCT s.tid) FROM activities a
                JOIN assays s ON s.assay_id = a.assay_id
                JOIN target_dictionary t ON t.tid = s.tid
                JOIN docs d ON d.doc_id = a.doc_id
                WHERE a.molregno IN ({q}) AND a.pchembl_value IS NOT NULL AND a.standard_relation = '='
                  AND t.target_type = 'SINGLE PROTEIN' AND d.doc_type = 'PUBLICATION'""", fam).fetchone()[0]
            row.update(
                max_phase=max(phases) if phases else "",
                atc_level1="".join(sorted({x for (x,) in ch.execute(
                    f"SELECT DISTINCT substr(level5, 1, 1) FROM molecule_atc_classification WHERE molregno IN ({q})", fam)})),
                curated_mechanisms=ch.execute(f"SELECT COUNT(*) FROM drug_mechanism WHERE molregno IN ({q})", fam).fetchone()[0],
                publication_targets=targets,
                gtopdb=int(any(c in pl.gtopdb for c in ids)))
        out.append(row)

    (HERE / "need_pubchem.json").write_text(json.dumps(need_pubchem, indent=0))
    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        wr.writeheader()
        wr.writerows(out)

    def bucket(r):
        if r["in_catalogue"]:
            return "in catalogue"
        if r["chembl_parents"]:
            has = r["curated_mechanisms"] or r["publication_targets"]
            return "ChEMBL, has target data" if has else "ChEMBL, no target data"
        if r["match_tier"] in ("unii_not_in_chembl", "unii_no_structure", "pubchem_not_in_chembl"):
            return "identified, not in ChEMBL"
        if r["match_tier"] == "not_looked_up":
            return "not looked up"
        return "unidentified"

    order = ["in catalogue", "ChEMBL, has target data", "ChEMBL, no target data",
             "identified, not in ChEMBL", "unidentified", "not looked up"]
    table = collections.OrderedDict()
    for r in out:
        table.setdefault(r["section"], collections.Counter())[bucket(r)] += 1
    total = collections.Counter()
    print("| section | " + " | ".join(order) + " | total |")
    print("|---|" + "---:|" * (len(order) + 1))
    for sec, c in table.items():
        total.update(c)
        print(f"| {sec} | " + " | ".join(str(c[b]) for b in order) + f" | {sum(c.values())} |")
    print("| **all** | " + " | ".join(f"**{total[b]}**" for b in order) + f" | **{sum(total.values())}** |")
    print(f"\nmatch tiers: {dict(collections.Counter(r['match_tier'] for r in out))}")
    print(f"{len(need_pubchem)} names not looked up in PubChem (need_pubchem.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
