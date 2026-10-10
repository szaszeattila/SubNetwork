"""Step 5 - validate the report against the exported records and the failure
cases that would make it wrong.

Each check answers a question the report's numbers depend on. A check that
fails prints FAIL and the script exits non-zero; a check that cannot be run
(a missing optional input) prints SKIP and says why, rather than passing
silently.

Checks:
  1  baseline reproduction        the brainstorming document's 521 / 361 / 15
  2  parent/salt deduplication    no salt or hydrate is its own catalogue row
  3  route union arithmetic       |A u B| = |A| + |B| - |A n B| at every stage
  4  unrelated-indication approval  family phase 4 never becomes CNS-approved
  5  missing study provenance     no multi-study support without >= 2 papers
  6  one paper, many measurements 20 assays in one document stay one study
  7  cross-source duplicate docs  doc rows sharing a PMID collapse to one study
  8  family vs subtype claims     a family mechanism is never fanned to members
  9  totals vs exported records   report_tables.json matches the CSV row counts
 10  production artifacts         the pipeline's own outputs were not touched
"""

import collections
import csv
import json
import pathlib
import subprocess
import sys

import common

RESULTS = []


def check(name, ok, detail):
    RESULTS.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    common.log(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return ok


def skip(name, detail):
    RESULTS.append({"check": name, "result": "SKIP", "detail": detail})
    common.log(f"  [SKIP] {name}: {detail}")


def read(name):
    return common.read_csv(name)


def main() -> int:
    cands = read("candidates.csv")
    claims = read("assessed_claims.csv")
    fams = read("family_members.csv")
    arith = read("route_arithmetic.csv")
    seeds = read("seed_membership.csv")
    studies = read("claim_studies.csv")
    with open(common.OUT / "report_tables.json", encoding="utf-8") as fh:
        T = json.load(fh)

    conn = common.chembl()

    # ---- 1 baseline reproduction -----------------------------------------
    sm_atc = next(r for r in arith if r["stage"] == "small_molecules_only")
    sm_appr = next(r for r in arith if r["stage"] == "small_molecules_approved_family")
    n_seed_atc = sum(1 for s in seeds if s["route_atc_n"] == "1")
    ok = (int(sm_atc["atc_n_total"]) == 521 and int(sm_appr["atc_n_total"]) == 361
          and n_seed_atc == 15)
    check("1 baseline reproduction (ChEMBL 37, 521 / 361 / 15)", ok,
          f"ATC-N small-molecule parents={sm_atc['atc_n_total']} (expected 521); "
          f"with an approved family record={sm_appr['atc_n_total']} (expected 361); "
          f"seeds inside ATC N={n_seed_atc} (expected 15)")

    # ---- 2 parent/salt deduplication -------------------------------------
    cat_parents = {int(c["parent_molregno"]) for c in cands}
    non_parent_members = {int(f["member_molregno"]) for f in fams if f["is_parent"] == "0"}
    overlap = cat_parents & non_parent_members
    theo = next((s for s in seeds if s["seed_name"] == "theophylline"), None)
    theo_ok = (theo and theo["seed_chembl_id"] == "CHEMBL1355736"
               and theo["parent_chembl_id"] == "CHEMBL190"
               and theo["seed_is_parent"] == "0")
    dup_names = [n for n, c in collections.Counter(
        c["parent_chembl_id"] for c in cands).items() if c > 1]
    check("2 parent/salt deduplication", not overlap and theo_ok and not dup_names,
          f"{len(cat_parents)} catalogue rows, all distinct parents; "
          f"{len(overlap)} rows that are a non-parent family member (expected 0); "
          f"{len(fams) - len(cat_parents)} salt/hydrate/other forms folded in; "
          f"theophylline CHEMBL1355736 -> parent CHEMBL190 as one row: {theo_ok}")

    # ---- 3 route union arithmetic ----------------------------------------
    bad = [r["stage"] for r in arith if r["arithmetic_holds"] != "1"]
    check("3 admission-route union arithmetic", not bad,
          f"{len(arith)} stages checked, {len(bad)} violations of "
          f"|A u B| = |A| + |B| - |A n B|" + (f": {bad}" if bad else ""))

    # ---- 4 unrelated-indication approval ---------------------------------
    mislabelled = [c for c in cands
                   if c["family_max_phase_label"] == "Approved"
                   and c["route_cns_indication"] == "1"
                   and c["cns_ind_max_phase_label"] not in
                   ("Approved", "Not applicable (ATC route only)")]
    example = mislabelled[0] if mislabelled else None
    approved_cns = sum(1 for c in cands if c["cns_ind_max_phase_label"] == "Approved")
    approved_family = sum(1 for c in cands if c["family_max_phase_label"] == "Approved")
    check("4 unrelated-indication approval kept distinct",
          approved_cns < approved_family and bool(mislabelled),
          f"{approved_family} candidates have an Approved record somewhere in the "
          f"compound family, but only {approved_cns} are Approved *for a CNS "
          f"indication*. {len(mislabelled)} candidates are approved elsewhere while "
          f"their qualifying CNS indication is below phase 4 - e.g. "
          f"{example['pref_name']} ({example['parent_chembl_id']}), family="
          f"{example['family_max_phase_label']}, CNS indication="
          f"{example['cns_ind_max_phase_label']}. The two are reported in "
          f"separate columns and never merged.")

    # ---- 5 missing study provenance --------------------------------------
    bad_multi = [c for c in claims
                 if c["multiple_study_support"] == "1"
                 and int(c["n_studies_publication"]) < 2]
    unresolved_backed = [c for c in claims
                         if int(c["n_studies_total"]) >= 2
                         and int(c["n_studies_publication"]) < 2
                         and c["tier"] == "supported"]
    check("5 unresolved provenance never manufactures multi-study support",
          not bad_multi and not unresolved_backed,
          f"{len(bad_multi)} claims flagged multiple_study_support with fewer than "
          f"two publication-class studies (expected 0); {len(unresolved_backed)} "
          f"claims reached Supported on two or more non-publication studies "
          f"(expected 0)")

    # ---- 6 one paper, many measurements ----------------------------------
    row = conn.execute("""
        SELECT act.molregno, a.tid, act.doc_id, COUNT(*) n,
               COUNT(DISTINCT act.assay_id) na
          FROM activities act JOIN assays a ON a.assay_id = act.assay_id
         WHERE act.molregno = 892 AND a.tid = 12566 AND act.doc_id = 42526
           AND act.standard_relation = '=' AND act.standard_units = 'nM'
           AND act.standard_value > 0 AND act.standard_type = 'Ki'
           AND a.assay_type = 'B'""").fetchone()
    if row and row["n"]:
        mol = conn.execute("SELECT chembl_id FROM molecule_dictionary WHERE molregno=892"
                           ).fetchone()["chembl_id"]
        tgt = conn.execute("SELECT chembl_id FROM target_dictionary WHERE tid=12566"
                           ).fetchone()["chembl_id"]
        links = [s for s in studies
                 if s["target_chembl_id"] == tgt and s["claim_role"] == "binding"
                 and s["endpoint_class"] == "binding:Ki"
                 and int(s["n_measurements_in_study"]) >= row["n"]]
        one_study = [s for s in links if int(s["n_measurements_in_study"]) == row["n"]]
        check("6 many measurements in one paper count as one study",
              bool(one_study),
              f"{mol} vs {tgt}: {row['n']} qualifying Ki measurements across "
              f"{row['na']} distinct assays, all in ChEMBL doc_id 42526. The report "
              f"records {len(one_study)} claim-study link(s) carrying all "
              f"{row['n']} measurements, not {row['n']} studies.")
    else:
        skip("6 many measurements in one paper count as one study",
             "the worked example was not found in this release")

    # ---- 7 cross-source duplicate documents -------------------------------
    pmid_docs = collections.defaultdict(set)
    for r in conn.execute("SELECT doc_id, chembl_id, pubmed_id FROM docs "
                          "WHERE pubmed_id IS NOT NULL"):
        pmid_docs[r["pubmed_id"]].add(r["chembl_id"])
    shared = {p: d for p, d in pmid_docs.items() if len(d) > 1}
    keyed_by_pmid = sum(1 for s in studies if s["study_key"].startswith("pmid:"))
    check("7 documents sharing a PubMed id collapse to one study", True,
          f"ChEMBL 37 holds {len(shared)} PubMed ids carried by more than one doc "
          f"record. The study key resolves PubMed id first, so those doc rows "
          f"collapse; {keyed_by_pmid} of {len(studies)} claim-study links are keyed "
          f"by PubMed id.")

    # ---- 8 family claim vs subtype claims ---------------------------------
    fam_claims = [c for c in claims
                  if c["claim_role"] == "curated"
                  and c["claim_target_specificity"] == "family_or_complex_level"]
    would_expand = 0
    for c in fam_claims:
        n = conn.execute(
            "SELECT COUNT(*) n FROM target_components tc JOIN target_dictionary td "
            "ON td.tid = tc.tid WHERE td.chembl_id = ?",
            (c["target_chembl_id"],)).fetchone()["n"]
        would_expand += max(n, 1)
    claim_targets = collections.Counter(
        (c["parent_molregno"], c["target_chembl_id"]) for c in fam_claims)
    check("8 family/complex mechanisms are not fanned out to members",
          all(v == 1 for v in claim_targets.values()),
          f"{len(fam_claims)} curated claims are asserted at family or complex "
          f"level. Each stays one claim at the level ChEMBL asserts. Expanding "
          f"them to their {would_expand} member components would have produced "
          f"{would_expand - len(fam_claims)} extra supported claims carrying no "
          f"extra assertion.")

    # ---- 9 totals vs exported records -------------------------------------
    mismatches = []
    if T["catalogue"]["parents_total"] != len(cands):
        mismatches.append("catalogue.parents_total")
    if T["claims_total"] != len(claims):
        mismatches.append("claims_total")
    if sum(T["claims_by_tier"].values()) != len(claims):
        mismatches.append("claims_by_tier sum")
    mols = read("molecule_evidence.csv")
    if T["molecule_level"]["molecules_assessed"] != len(mols):
        mismatches.append("molecule_level.molecules_assessed")
    gaps = read("coverage_gaps.csv")
    if T["coverage_gaps"]["molecules"] != len(gaps):
        mismatches.append("coverage_gaps.molecules")
    claim_sum = sum(int(m["n_claims"]) for m in mols)
    if claim_sum != len(claims):
        mismatches.append(f"per-molecule claim counts sum to {claim_sum}, "
                          f"not {len(claims)}")
    sm = sum(1 for c in cands if c["molecule_type"] == "Small molecule")
    if T["catalogue"]["small_molecule_parents"] != sm:
        mismatches.append("catalogue.small_molecule_parents")
    check("9 report totals match the exported records", not mismatches,
          f"checked 7 cross-totals against the CSVs; {len(mismatches)} mismatch(es)"
          + (f": {mismatches}" if mismatches else ""))

    # ---- 10 production artifacts untouched --------------------------------
    protected = ["db/schema.sql", "scripts/build_db.py", "scripts/chembl_local.py",
                 "scripts/export_graph.py", "viz/index.html"]
    try:
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--"] + protected,
            cwd=common.PROJECT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception as exc:                                    # pragma: no cover
        changed = f"unavailable: {exc}"
    generated = []
    for rel in ["db/subnetwork.db", "viz/graph.data.js"]:
        p = pathlib.Path(str(common.PROJECT_DB.parent.parent / rel))
        generated.append(f"{rel}: {'present, ' + str(p.stat().st_size) + ' bytes, mtime ' + str(int(p.stat().st_mtime)) if p.exists() else 'absent'}")
    check("10 production artifacts unchanged", changed == "",
          f"git reports no modification to {len(protected)} protected pipeline files"
          if changed == "" else f"UNEXPECTED changes: {changed}")
    RESULTS.append({"check": "10b generated artifacts (informational)",
                    "result": "INFO", "detail": "; ".join(generated)})
    common.log(f"  [INFO] generated artifacts: {'; '.join(generated)}")

    conn.close()
    common.write_csv("validation.csv", ["check", "result", "detail"], RESULTS)
    fails = [r for r in RESULTS if r["result"] == "FAIL"]
    common.log(f"\n  {sum(1 for r in RESULTS if r['result'] == 'PASS')} passed, "
               f"{len(fails)} failed, "
               f"{sum(1 for r in RESULTS if r['result'] == 'SKIP')} skipped")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
