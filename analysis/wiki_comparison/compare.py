#!/usr/bin/env python3
"""Place every compound in wiki_compounds.csv against ChEMBL 37 and the active
catalogue, and say what ChEMBL holds for the ones outside it.

Read-only and adopts nothing: ChEMBL and db/cohort1.db are opened mode=ro, and
the output is comparison.csv plus a summary on stdout.

A wiki name is placed by the first of these that answers, and the tier is kept
on the row:

  chembl_name      exact ChEMBL pref_name                          high
  unii_inchikey    FDA UNII preferred name -> InChIKey -> ChEMBL   high
  chembl_synonym   exact ChEMBL synonym                            medium; low
                   if the name is four characters or fewer (AMT, MDA)
  *_squashed / *_connectivity / pubchem_*                          low

"_connectivity" means the InChIKey's first block matched and the full key did
not: another stereoisomer or isotope form of the same skeleton. A name reaching
several ChEMBL parents keeps all of them. REJECTED lists the matches found wrong
on review; the reason stays on the row.

    python3 analysis/wiki_comparison/compare.py [--data-root DIR]

--data-root is the checkout holding db/cohort1.db and db/cache/ (both
gitignored), for running from a worktree that has no build of its own.
"""
import argparse
import collections
import csv
import io
import json
import os
import pathlib
import re
import sqlite3
import sys
import unicodedata
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CHEMBL = os.environ.get("CHEMBL_SQLITE_PATH", "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db")

REJECTED = {
    "Irisin": "PubChem name reached iridin, an isoflavone; irisin is a myokine protein",
    "Cardiogen": "PubChem name reached levocarnitine; Cardiogen is a Khavinson tetrapeptide",
    "Thymalin": "PubChem name reached nonathymulin; thymalin is a thymus extract",
    "HCG": "PubChem name reached a small molecule; hCG is a glycoprotein hormone",
    "MKP": "PubChem name reached potassium phosphate",
    "AMT": "ChEMBL synonym of 3-amino-3-deoxythymidine; the wiki means alpha-methyltryptamine",
    "NPAP": "ChEMBL synonym of prajmalium, an unrelated substance",
    "HU-210": "squashed name reached dexanabinol (HU-211), its enantiomer",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=pathlib.Path, default=ROOT)
    args = ap.parse_args()
    data = args.data_root.resolve()

    wiki = list(csv.DictReader(open(HERE / "wiki_compounds.csv", encoding="utf-8")))
    ch = sqlite3.connect(f"file:{CHEMBL}?mode=ro", uri=True)
    coh = sqlite3.connect(f"file:{data / 'db' / 'cohort1.db'}?mode=ro", uri=True)

    parent = dict(ch.execute("SELECT molregno, parent_molregno FROM molecule_hierarchy"))
    chembl_id = dict(ch.execute("SELECT molregno, chembl_id FROM molecule_dictionary"))
    pref_name = dict(ch.execute("SELECT molregno, pref_name FROM molecule_dictionary"))
    P = lambda m: parent.get(m, m)

    by_pref, by_syn, by_squash = (collections.defaultdict(set) for _ in range(3))
    for m, n in ch.execute("SELECT molregno, pref_name FROM molecule_dictionary WHERE pref_name IS NOT NULL"):
        by_pref[norm(n)].add(P(m))
        by_squash[squash(n)].add(P(m))
    for m, n in ch.execute("SELECT molregno, synonyms FROM molecule_synonyms WHERE synonyms IS NOT NULL"):
        by_syn[norm(n)].add(P(m))
        by_squash[squash(n)].add(P(m))
    by_key, by_block = collections.defaultdict(set), collections.defaultdict(set)
    for m, k in ch.execute("SELECT molregno, standard_inchi_key FROM compound_structures "
                           "WHERE standard_inchi_key IS NOT NULL"):
        by_key[k].add(P(m))
        by_block[k[:14]].add(P(m))

    # The FDA UNII file the MeSH structure backfill already pins.
    unii = collections.defaultdict(set)
    with zipfile.ZipFile(data / "db" / "cache" / "fda" / "UNII_Data.zip") as z:
        member = next(n for n in z.namelist() if n.startswith("UNII_Records"))
        with z.open(member) as fh:
            reader = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
            head = reader.readline().rstrip("\n").split("\t")
            i_name, i_key = head.index("DISPLAY_NAME"), head.index("INCHIKEY")
            for line in reader:
                c = line.rstrip("\n").split("\t")
                if len(c) > i_key:
                    unii[norm(c[i_name])].add((c[0], c[i_key]))

    cache_f = HERE / "pubchem_cache.json"
    pubchem = json.loads(cache_f.read_text()) if cache_f.exists() else {}

    gtopdb = set()
    for row in csv.reader(open(data / "db" / "cache" / "gtopdb" / "2026.3" / "ligands.csv", encoding="utf-8")):
        gtopdb.update(c for c in row if c.startswith("CHEMBL"))

    catalogue = {r[0]: r[1:] for r in coh.execute(
        "SELECT chembl_id, admission_reason, evidence_status FROM molecules")}

    def from_key(k):
        if k in by_key:
            return by_key[k], "inchikey"
        if k[:14] in by_block:
            return by_block[k[:14]], "connectivity"
        return set(), None

    need_pubchem, out = [], []
    for w in wiki:
        name, got, tier, note = w["name"], set(), None, ""
        if norm(name) in by_pref:
            got, tier = by_pref[norm(name)], "chembl_name"
        elif norm(name) in by_syn:
            got, tier = by_syn[norm(name)], "chembl_synonym"
        elif squash(name) and squash(name) in by_squash:
            got, tier = by_squash[squash(name)], "chembl_squashed"
        elif norm(name) in unii and any(k for _, k in unii[norm(name)]):
            for _, k in unii[norm(name)]:
                s, how = from_key(k) if k else (set(), None)
                if s:
                    got |= s
                    tier = f"unii_{how}"
            if not got:
                tier = "unii_not_in_chembl"
                note = "UNII " + ";".join(sorted(u for u, k in unii[norm(name)] if k))
        elif norm(name) in unii:
            tier, note = "unii_no_structure", "UNII " + ";".join(sorted(u for u, _ in unii[norm(name)]))
        if tier is None:
            if name not in pubchem:
                need_pubchem.append(name)
                tier = "not_looked_up"
            elif pubchem[name]:
                for k in pubchem[name]:
                    s, how = from_key(k)
                    if s:
                        got |= s
                        tier = f"pubchem_{how}"
                tier = tier or "pubchem_not_in_chembl"
            else:
                tier = "no_match"
        if name in REJECTED and got:
            got, tier, note = set(), "rejected_on_review", REJECTED[name]

        if tier in ("chembl_name", "unii_inchikey"):
            confidence = "high"
        elif tier == "chembl_synonym" and len(squash(name)) > 4:
            confidence = "medium"
        else:
            confidence = "low" if got else ""

        ids = sorted(chembl_id[p] for p in got)
        row = dict(w, match_tier=tier, confidence=confidence, note=note,
                   chembl_parents="|".join(ids),
                   chembl_names="|".join(sorted({pref_name[p] for p in got if pref_name.get(p)})),
                   in_catalogue="|".join(c for c in ids if c in catalogue),
                   catalogue_status="|".join(f"{catalogue[c][0]}/{catalogue[c][1]}"
                                             for c in ids if c in catalogue),
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
                gtopdb=int(any(c in gtopdb for c in ids)))
        out.append(row)

    (HERE / "need_pubchem.json").write_text(json.dumps(need_pubchem, indent=0))
    with open(HERE / "comparison.csv", "w", newline="", encoding="utf-8") as fh:
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
