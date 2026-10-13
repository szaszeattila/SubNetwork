#!/usr/bin/env python3
"""What a target-defined route would admit: every compound linked to a brain
target, with no clinical phase, from ChEMBL and from the two sources that
reach compounds ChEMBL lacks (GtoPdb, PDSP Ki).

Read-only and adopts nothing. "Brain target" here is a stand-in, not a
decision: by default every human protein at which a nervous-system drug (an ATC
N code outside the local-anaesthetic and simple-analgesic branches) has a
curated claim, ChEMBL's mechanism or GtoPdb's primary target. A non-human
record counts as its human orthologue (D20), and a complex or family as its
components. That last step reads target_components as a list of proteins,
never as a binding claim about them: it decides which proteins are in the set,
and no molecule's claim is moved.

    python3 analysis/wiki_comparison/brain_targets.py [--data-root DIR] [--csv FILE] [--pdsp CSV]
        [--brain-set atc-n|catalogue]
"""
import argparse
import collections
import csv
import gzip
import pathlib
import re
import sqlite3
import sys

from placing import CHEMBL, HERE, ROOT, Placer, norm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=pathlib.Path, default=ROOT)
    ap.add_argument("--csv", type=pathlib.Path, default=HERE / "comparison.csv")
    ap.add_argument("--brain-set", choices=("atc-n", "catalogue"), default="atc-n")
    ap.add_argument("--pdsp", type=pathlib.Path, help="the PDSP Ki CSV; default <data-root>/db/pdsp_ki_database.csv")
    args = ap.parse_args()
    data = args.data_root
    pl = Placer(data)
    ch, coh = pl.ch, pl.coh
    ch.row_factory = None

    # ---- the brain-target set, as human accessions -------------------------
    human_of = {t: h for t, h in coh.execute(
        "SELECT target_chembl_id, human_accession FROM target_orthologues WHERE human_accession IS NOT NULL")}
    # --brain-set catalogue: every member's curated targets. It is not a brain
    # set - members admitted by a pain, angina or MS indication bring COX,
    # PDE5, the glucocorticoid receptor and tubulin - and is kept to show that.
    # --brain-set atc-n: only members with an ATC N code outside N01B and N02B.
    only_atc_n = "" if args.brain_set == "catalogue" else """
               AND c.parent_molregno IN (SELECT parent_molregno FROM molecule_atc
                                          WHERE boundary_flag IS NULL)"""
    brain = set()
    for t, ttype, tax, acc in coh.execute(f"""
            SELECT DISTINCT c.target_chembl_id, t.target_type, t.tax_id, tc.accession
              FROM claims c JOIN targets t ON t.chembl_id = c.target_chembl_id
              JOIN target_components tc ON tc.target_chembl_id = c.target_chembl_id
             WHERE c.claim_role IN ('curated', 'gtopdb'){only_atc_n}"""):
        if tax == 9606:
            brain.add(acc)
        elif t in human_of:
            brain.add(human_of[t])
    print(f"brain-target set: {len(brain)} human proteins")

    # ChEMBL target records reaching the set: a human record by its own
    # accessions, any other by the orthologue the cohort matched it to.
    tid_acc = collections.defaultdict(set)
    for tid, acc, tax in ch.execute("""
            SELECT tc.tid, cs.accession, td.tax_id FROM target_components tc
              JOIN component_sequences cs ON cs.component_id = tc.component_id
              JOIN target_dictionary td ON td.tid = tc.tid"""):
        if tax == 9606 and acc:
            tid_acc[tid].add(acc)
    for tid, cid in ch.execute("SELECT tid, chembl_id FROM target_dictionary"):
        if cid in human_of:
            tid_acc[tid].add(human_of[cid])
    brain_tids = {t for t, a in tid_acc.items() if a & brain}
    single = {t for (t,) in ch.execute("SELECT tid FROM target_dictionary WHERE target_type = 'SINGLE PROTEIN'")}

    parent = {m: p for m, p in ch.execute("SELECT molregno, parent_molregno FROM molecule_hierarchy") if p}
    P = lambda m: parent.get(m, m)  # noqa: E731
    by_id = {c: m for m, c in pl.chembl_id.items()}
    catalogue = {P(by_id[c]) for c in pl.catalogue if c in by_id}

    # ---- ChEMBL routes ------------------------------------------------------
    curated = {P(m) for m, t in ch.execute("SELECT molregno, tid FROM drug_mechanism") if t in brain_tids}
    pub_docs = {d for (d,) in ch.execute("SELECT doc_id FROM docs WHERE doc_type = 'PUBLICATION'")}
    assay_tid = {a: t for a, t in ch.execute("SELECT assay_id, tid FROM assays") if t in brain_tids and t in single}
    any_value, docs_at = set(), collections.defaultdict(set)
    for m, a, d, v in ch.execute("SELECT molregno, assay_id, doc_id, pchembl_value FROM activities "
                                 "WHERE pchembl_value IS NOT NULL AND standard_relation = '='"):
        if d in pub_docs and a in assay_tid:
            p = P(m)
            any_value.add(p)
            if v >= 6:
                docs_at[(p, assay_tid[a])].add(d)
    replicated = {p for (p, _), ds in docs_at.items() if len(ds) >= 2}

    # ---- GtoPdb: interactions at a human brain protein ----------------------
    gt_lig = {}
    for row in csv.DictReader(_skip_comment(data / "db" / "cache" / "gtopdb" / "2026.3" / "ligands.csv")):
        gt_lig[row["Ligand ID"]] = row
    gt_any, gt_primary = set(), set()
    for row in csv.DictReader(_skip_comment(data / "db" / "cache" / "gtopdb" / "2026.3" / "interactions.csv")):
        if row["Target Species"] != "Human":
            continue
        if set(row["Target UniProt ID"].split("|")) & brain:
            gt_any.add(row["Ligand ID"])
            if row["Primary Target"] == "true":
                gt_primary.add(row["Ligand ID"])

    def gt_parents(ids):
        out, outside = set(), set()
        for i in ids:
            lig = gt_lig.get(i, {})
            ps = {P(by_id[c]) for c in re.split(r"[|;, ]+", lig.get("ChEMBL ID", "")) if c in by_id}
            k = lig.get("InChIKey", "")
            if not ps and k:
                ps = {P(m) for m in pl.from_key(k)[0]}
            out |= ps
            if not ps:
                outside.add(i)
        return out, outside
    gt_any_p, gt_any_out = gt_parents(gt_any)
    gt_pri_p, gt_pri_out = gt_parents(gt_primary)

    # ---- PDSP Ki: a gene symbol is placed on UniProt's primary gene name ----
    gene_acc = collections.defaultdict(set)
    with gzip.open(data / "db" / "cache" / "uniprot" / "human_reviewed.fasta.gz", "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                m = re.search(r" GN=(\S+)", line)
                if m:
                    gene_acc[m.group(1)].add(line.split("|")[1])
    pdsp_names = set()
    for row in csv.DictReader(open(args.pdsp or data / "db" / "pdsp_ki_database.csv", encoding="utf-8", errors="replace")):
        accs = gene_acc.get(row["Unigene"].strip(), set())
        if len(accs) == 1 and accs & brain and not row["ki Note"].strip() and row["ki Val"].strip():
            pdsp_names.add(row[" Ligand Name"].strip())
    pdsp_p, pdsp_out = set(), set()
    for n in pdsp_names:
        got = pl.place(n, use_pubchem=False)[0]
        if got:
            pdsp_p |= {P(m) for m in got}
        else:
            pdsp_out.add(norm(n))

    routes = {
        "ChEMBL curated mechanism at a brain target": curated,
        "GtoPdb primary target is a brain target": gt_pri_p,
        "GtoPdb any interaction at a brain target": gt_any_p,
        "ChEMBL: <= 1 uM at a brain target, 2+ papers": replicated,
        "PDSP Ki: an exact Ki at a brain target": pdsp_p,
        "ChEMBL: any exact published value at a brain target": any_value,
    }
    routes["curated or GtoPdb (any)"] = curated | gt_any_p

    wiki = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    members = sum(1 for r in wiki if r["in_catalogue"])
    outside = [r for r in wiki if r["chembl_parents"] and not r["in_catalogue"]]
    ps_of = lambda r: {P(by_id[c]) for c in r["chembl_parents"].split("|") if c in by_id}  # noqa: E731
    print(f"\n| route (ChEMBL compounds) | wiki added | wiki covered | of {len(wiki)} | catalogue grows by |")
    print("|---|---:|---:|---:|---:|")
    for name, s in routes.items():
        added = sum(1 for r in outside if ps_of(r) & s)
        print(f"| {name} | {added} | {members + added} | {(members + added) / len(wiki):.0%} | {len(s - catalogue):,} |")

    # ---- what reaches compounds ChEMBL does not have -------------------------
    absent = [r for r in wiki if not r["chembl_parents"] and r["match_tier"] != "rejected_on_review"]
    gt_out_keys = {gt_lig[i]["InChIKey"][:14] for i in gt_any_out if gt_lig[i].get("InChIKey")}
    gt_out_names = {norm(gt_lig[i]["Name"]) for i in gt_any_out} | {
        norm(s) for i in gt_any_out for s in gt_lig[i].get("Synonyms", "").split("|") if s.strip()}
    hit_gt, hit_pdsp = [], []
    for r in absent:
        keys = {k[:14] for _, k in pl.unii.get(norm(r["name"]), ()) if k} | {
            k[:14] for k in pl.pubchem.get(r["name"], []) or []}
        if keys & gt_out_keys or norm(r["name"]) in gt_out_names:
            hit_gt.append(r["name"])
        if norm(r["name"]) in pdsp_out:
            hit_pdsp.append(r["name"])
    print(f"\nnot in ChEMBL: GtoPdb has {len(gt_any_out)} ligands at a brain target with no ChEMBL record; "
          f"PDSP {len(pdsp_out)} ligand names ChEMBL's names do not place")
    print(f"of the wiki's {len(absent)} compounds not in ChEMBL: GtoPdb reaches {len(hit_gt)} {sorted(hit_gt)}")
    print(f"  PDSP, by name only: {len(hit_pdsp)} {sorted(hit_pdsp)}")
    both = {r["name"] for r in outside if ps_of(r) & routes['curated or GtoPdb (any)']}
    print(f"\nwiki covered by curated | GtoPdb, both sources: {members + len(both) + len(set(hit_gt))}"
          f" ({(members + len(both) + len(set(hit_gt))) / len(wiki):.0%})")
    by_sec = collections.Counter(r["section"] for r in outside if ps_of(r) & routes['curated or GtoPdb (any)'])
    print("curated|GtoPdb additions by section:", dict(by_sec))
    return 0


def _skip_comment(path):
    fh = open(path, encoding="utf-8")
    fh.readline()  # "# GtoPdb Version: ..."
    return fh


if __name__ == "__main__":
    sys.exit(main())
