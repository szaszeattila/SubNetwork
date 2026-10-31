#!/usr/bin/env python3
"""Do the listed entries (D25-D27) act on a protein the brain expresses?

The user's test, 2026-10-16: "anything that acts on a brain protein I think is
fair game" - a SERM acts on oestrogen receptors in the brain. A brain protein
here is one the Human Protein Atlas detects in at least one brain region
(proteinatlas.tsv, "RNA brain regional distribution" anything but "Not
detected"), matched by UniProt accession, never by gene symbol. That is where a
protein is made, not proof that a drug acting on it acts in the brain.

A claim's protein is its target's: a human SINGLE PROTEIN's accession, a
non-human one's human orthologue (D20, target_orthologues), and a complex or
family's human components. The last reads target_components as a list of
proteins to test, never as a binding claim about them (D06).

Read-only. Prints the counts by evidence tier and list, and writes one row per
listed entry to OUT (default db/cache/hpa/listed_brain_proteins.csv, out of the
repository like every list it names).

    python3 analysis/wiki_comparison/listed_brain_proteins.py [HPA_ZIP] [--out FILE]
"""
import argparse
import collections
import csv
import io
import pathlib
import sqlite3
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TIERS = ("supported", "preliminary", "limited_or_unresolved")


def brain_accessions(hpa_zip: pathlib.Path) -> tuple[set, set]:
    """(detected in a brain region, measured at all) as UniProt accessions."""
    detected, measured = set(), set()
    with zipfile.ZipFile(hpa_zip) as z, z.open(z.namelist()[0]) as fh:
        for row in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"), delimiter="\t"):
            dist = (row.get("RNA brain regional distribution") or "").strip()
            accs = [a.strip() for a in (row.get("Uniprot") or "").split(",") if a.strip()]
            if not dist:
                continue
            measured.update(accs)
            if dist != "Not detected":
                detected.update(accs)
    return detected, measured


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("hpa", nargs="?", type=pathlib.Path,
                    default=ROOT / "db" / "cache" / "hpa" / "proteinatlas.tsv.zip")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "db" / "cache" / "hpa" / "listed_brain_proteins.csv")
    args = ap.parse_args()
    brain, measured = brain_accessions(args.hpa)
    db = sqlite3.connect(f"file:{ROOT / 'db' / 'cohort1.db'}?mode=ro", uri=True)

    human_of = dict(db.execute("SELECT target_chembl_id, human_accession FROM target_orthologues"
                               " WHERE human_accession IS NOT NULL"))
    proteins = collections.defaultdict(set)   # target -> human accessions
    for t, ttype, tax, acc in db.execute(
            "SELECT t.chembl_id, t.target_type, t.tax_id, tc.accession FROM targets t"
            " JOIN target_components tc ON tc.target_chembl_id = t.chembl_id"):
        if tax == 9606 and acc:
            proteins[t].add(acc)
        elif t in human_of:
            proteins[t].add(human_of[t])

    listed = {}
    for p, cid, name, status in db.execute(
            "SELECT parent_molregno, chembl_id, pref_name, evidence_status FROM molecules"
            " WHERE admission_reason = 'listed_only'"):
        listed[p] = {"chembl_id": cid, "name": name, "evidence_status": status,
                     "sources": set(), "best": None, "brain_genes": set(), "other_genes": set()}
    for p, src, lname in db.execute("SELECT parent_molregno, source, name FROM molecule_listings"):
        if p in listed:
            listed[p]["sources"].add(src)
            listed[p]["name"] = listed[p]["name"] or lname
    gene = dict(db.execute("SELECT accession, gene_symbol FROM target_components"
                           " WHERE gene_symbol IS NOT NULL"))

    for p, t, tier in db.execute("SELECT parent_molregno, target_chembl_id, tier FROM claims"):
        e = listed.get(p)
        if e is None:
            continue
        accs = proteins.get(t, set())
        hit = accs & brain
        if hit:
            e["brain_genes"].update(gene.get(a, a) for a in hit)
            if e["best"] is None or TIERS.index(tier) < TIERS.index(e["best"]):
                e["best"] = tier
        else:
            e["other_genes"].update(gene.get(a, a) for a in accs)
        e.setdefault("any_claim", True)

    def verdict(e):
        if e["best"]:
            return "brain_" + e["best"]
        return "claims_none_on_a_brain_protein" if e.get("any_claim") else "no_claim"

    for e in listed.values():
        e["verdict"] = verdict(e)
    order = [f"brain_{t}" for t in TIERS] + ["claims_none_on_a_brain_protein", "no_claim"]
    print(f"HPA brain regions: {len(brain)} accessions detected, of {len(measured)} measured")
    by_src = collections.defaultdict(collections.Counter)
    for e in listed.values():
        by_src["all listed"][e["verdict"]] += 1
        for s in e["sources"]:
            by_src[s][e["verdict"]] += 1
    cols = ["all listed", "wikipedia", "wikidata", "tripsit", "psychonautwiki", "sciwiki"]
    print("| | " + " | ".join(cols) + " |")
    print("|---|" + "---:|" * len(cols))
    for v in order:
        print(f"| {v} | " + " | ".join(str(by_src[c][v]) for c in cols) + " |")

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["chembl_id", "name", "sources", "evidence_status", "verdict",
                    "brain_proteins", "other_proteins"])
        for e in sorted(listed.values(), key=lambda e: (order.index(e["verdict"]), str(e["name"]))):
            w.writerow([e["chembl_id"], e["name"], "|".join(sorted(e["sources"])), e["evidence_status"],
                        e["verdict"], " ".join(sorted(e["brain_genes"])),
                        " ".join(sorted(e["other_genes"] - e["brain_genes"]))])
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
