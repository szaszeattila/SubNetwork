"""Reproduce the annotation follow-up without writing to source or production DBs.

Baseline candidate/evidence exports stay fixed. Writes only followup/out/.
Run from any directory: python3 analysis/cohort1/followup/analyze.py
"""
import collections
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import common
import step2_candidates as step2
import step3_evidence as step3

OUT = HERE / "out"
RULES = json.loads((HERE / "rules.json").read_text())


def write(name, rows):
    rows = list(rows)
    path = OUT / name
    fields = list(rows[0]) if rows else ["no_rows"]
    opener = (lambda: io.TextIOWrapper(gzip.GzipFile(filename=str(path), mode="wb", mtime=0), encoding="utf-8", newline="")) if name.endswith(".gz") else (lambda: path.open("w",newline="",encoding="utf-8"))
    with opener() as f:
        w = csv.DictWriter(f, fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows", flush=True)
    return rows


def claim_key(r):
    return (str(r["parent_molregno"]), r["target_chembl_id"], r.get("role", r.get("claim_role")))


def number(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def convert_unit(value, unit, relation="=", identity=None):
    """Return proposal class, nM value, reason. Never infer missing dimensions."""
    value = number(value)
    if relation != "=" or value is None or not math.isfinite(value) or value <= 0:
        return "not_recovered", None, "requires_positive_finite_exact_value"
    cfg = RULES["unit_recovery"]
    factors = cfg["concentration_factors_to_nM"]
    unit = (unit or "").strip()
    if unit in factors:
        return "concentration", value * factors[unit], "explicit_concentration_unit"
    m = re.fullmatch(r"10\^([+-]?\d+)\s*(.+)", unit)
    if m and m[2] in factors:
        result = value * 10 ** int(m[1]) * factors[m[2]]
        if math.isfinite(result) and result > 0:
            return "concentration", result, "explicit_power_of_ten_concentration"
    if unit in cfg["mass_factors_to_g_per_L"]:
        i = identity or {}
        mw = number(i.get("full_mwt"))
        if (i.get("molecule_type") == "Small molecule" and i.get("structure_type") in ("MOL", "BOTH")
                and i.get("canonical_smiles") and mw is not None and math.isfinite(mw) and mw > 0):
            return "conditional_mass", value * cfg["mass_factors_to_g_per_L"][unit] / mw * 1e9, "measured_record_full_mwt_material_basis_unverified"
        return "not_recovered", None, "mass_concentration_identity_or_molecular_weight_unresolved"
    return "not_recovered", None, "missing_incompatible_or_unreviewed_unit"


def assignment_matches(r, basis):
    """Keep exact assignment, species, role and variant distinct from study support."""
    if str(r.get("target_tax_id")) != "9606" or r.get("relationship_type") != "D" or r.get("variant_id") not in (None, ""):
        return False
    tt, conf = r.get("target_type"), str(r.get("confidence_score"))
    if tt == "SINGLE PROTEIN" and conf == "9":
        return True
    if basis != "human_single" and tt == "PROTEIN COMPLEX" and conf == "7":
        return True
    return basis == "human_with_families" and ((tt == "PROTEIN COMPLEX GROUP" and conf == "7") or (tt == "PROTEIN FAMILY" and conf == "5"))


def assess(rows):
    """Same experimental support rule as baseline; preserve endpoint classes."""
    pubs = collections.defaultdict(set)
    studies = set()
    for r in rows:
        if r.get("study_key"):
            studies.add(r["study_key"])
            if r.get("provenance_class") == "publication":
                pubs[r["endpoint_class"]].add(r["study_key"])
    return "supported" if any(len(p) >= 2 for p in pubs.values()) else "preliminary" if studies else "limited_or_unresolved"


def membership(candidate, policy, category):
    if category == "small_molecules" and candidate["molecule_type"] != "Small molecule":
        return False
    phase = number(candidate["cns_ind_max_phase"])
    indication = candidate["route_cns_indication"] == "1" and (policy["min_cns_phase"] is None or (phase is not None and phase >= policy["min_cns_phase"]))
    return indication or (policy["keep_atc"] and candidate["route_atc_n"] == "1")


def main():
    OUT.mkdir(exist_ok=True)
    cands = common.read_csv("candidates.csv")
    candidates = {r["parent_molregno"]: r for r in cands}
    claims = common.read_csv("assessed_claims.csv")
    existing = {claim_key(r): r for r in claims}
    measurements = common.read_csv("measurements.csv")
    families = common.read_csv("family_members.csv")
    member_parent = {str(r["member_molregno"]): r["parent_molregno"] for r in families}
    conn = common.chembl()
    conn.execute("CREATE TEMP TABLE followup_members(molregno INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO followup_members VALUES(?)", [(int(m),) for m in member_parent])
    identities = {str(r["molregno"]): dict(r) for r in conn.execute("""
        SELECT md.molregno,md.chembl_id,md.molecule_type,md.structure_type,cp.full_mwt,
               cp.mw_freebase,cp.full_molformula,cs.canonical_smiles
        FROM molecule_dictionary md JOIN followup_members fm USING(molregno)
        LEFT JOIN compound_properties cp USING(molregno)
        LEFT JOIN compound_structures cs USING(molregno)""")}
    unit_rows, recovered = [], collections.defaultdict(list)
    for r in measurements:
        if r["status"] != "excluded_units":
            continue
        identity = identities[r["measured_molregno"]]
        kind, val, reason = convert_unit(r["standard_value_raw"], r["standard_units"], r["standard_relation"], identity)
        row = dict(r, recovery_class=kind, proposed_value_nM=val, recovery_reason=reason,
                   measured_chembl_id=identity["chembl_id"], measured_full_mwt=identity["full_mwt"],
                   measured_freebase_mwt=identity["mw_freebase"], measured_formula=identity["full_molformula"])
        unit_rows.append(row)
        if val is not None:
            recovered[kind].append(dict(r, standard_value_nM=val))
    write("unit_audit.csv", unit_rows)
    grouped = collections.Counter((r["standard_units"], r["recovery_class"], r["recovery_reason"]) for r in unit_rows)
    write("unit_summary.csv", [dict(unit=u, recovery_class=k, reason=why, records=n) for (u,k,why),n in sorted(grouped.items())])

    exact = [r for r in measurements if r["status"] == "included_exact"]
    by_key = collections.defaultdict(list)
    for r in exact:
        by_key[claim_key(r)].append(r)
    scenarios = {"baseline": [], "concentration_only": recovered["concentration"],
                 "including_conditional_mass": recovered["concentration"] + recovered["conditional_mass"]}
    changes, recovery_summary, thresholds = [], [], []
    for scenario, additions in list(scenarios.items())[1:]:
        add_by_key = collections.defaultdict(list)
        for r in additions:
            add_by_key[claim_key(r)].append(r)
        for basis in ["all_assignments", "human_single"]:
            transformed = []
            for key, extra in sorted(add_by_key.items()):
                old = by_key.get(key, [])
                keep = lambda r: basis == "all_assignments" or assignment_matches(r, basis)
                extra = [r for r in extra if keep(r)]
                if not extra:
                    continue
                old = [r for r in old if keep(r)]
                before, after = assess(old), assess(old + extra)
                row = dict(scenario=scenario, basis=basis, parent_molregno=key[0], parent_chembl_id=candidates[key[0]]["parent_chembl_id"],
                           molecule=candidates[key[0]]["pref_name"], target_chembl_id=key[1], role=key[2],
                           old_tier=before, new_tier=after, old_exact=len(old), added_exact=len(extra), tier_changed=int(before != after))
                transformed.append(row)
                classes = {r["endpoint_class"] for r in extra}
                for cls in sorted(classes):
                    a = [float(r["standard_value_nM"]) for r in old if r["endpoint_class"] == cls]
                    b = a + [float(r["standard_value_nM"]) for r in extra if r["endpoint_class"] == cls]
                    oldmed = 10 ** statistics.median([math.log10(v) for v in a]) if a else None
                    newmed = 10 ** statistics.median([math.log10(v) for v in b])
                    for um in [1,10,100,300]:
                        thresholds.append(dict(scenario=scenario,basis=basis,parent_molregno=key[0],target_chembl_id=key[1],role=key[2],endpoint_class=cls,
                                               threshold_uM=um,old_median_nM=oldmed,new_median_nM=newmed,
                                               old_pass=int(oldmed is not None and oldmed <= um*1000),new_pass=int(newmed <= um*1000)))
            changes.extend(transformed)
            recovery_summary.append(dict(scenario=scenario,basis=basis,added_measurements=sum(r["added_exact"] for r in transformed),
                 affected_claims=len(transformed),affected_molecules=len({r["parent_molregno"] for r in transformed}),
                 newly_measured_claims=sum(r["old_exact"] == 0 for r in transformed),
                 newly_preliminary=sum(r["old_tier"] == "limited_or_unresolved" and r["new_tier"] == "preliminary" for r in transformed),
                 newly_supported=sum(r["old_tier"] != "supported" and r["new_tier"] == "supported" for r in transformed),
                 previously_gap_molecules=sum(not any(c["parent_molregno"] == p for c in claims) for p in {r["parent_molregno"] for r in transformed})))
    write("unit_claim_changes.csv", changes)
    write("unit_recovery_summary.csv", recovery_summary)
    write("unit_threshold_changes.csv", thresholds)

    # Export rows dropped at the organism-format gate, with their source context.
    organism = []
    for r in conn.execute("""
      SELECT act.activity_id,act.molregno measured_molregno,act.standard_type,act.standard_relation,
             act.standard_value,act.standard_units,act.data_validity_comment,act.potential_duplicate,
             act.value published_value,act.units published_units,act.type published_type,
             a.chembl_id assay_chembl_id,a.description assay_description,a.confidence_score,
             a.relationship_type,a.variant_id,a.assay_organism,a.assay_tax_id,
             td.chembl_id target_chembl_id,td.pref_name target_name,td.target_type,td.tax_id target_tax_id,
             td.organism target_organism,d.chembl_id doc_chembl_id,d.pubmed_id,d.doi,d.doc_type,d.patent_id
      FROM activities act JOIN followup_members fm USING(molregno) JOIN assays a USING(assay_id)
      JOIN bioassay_ontology bao ON bao.bao_id=a.bao_format
      LEFT JOIN target_dictionary td ON td.tid=a.tid LEFT JOIN docs d ON d.doc_id=act.doc_id
      WHERE a.assay_type='F' AND bao.label='organism-based format'
        AND act.standard_type IN ('Ki','Kd','IC50','EC50','AC50','Kb')
        AND a.chembl_id NOT IN ('CHEMBL5133661','CHEMBL1074487') ORDER BY act.activity_id"""):
        r = dict(r)
        p = member_parent[str(r["measured_molregno"])]
        r.update(parent_molregno=p,parent_chembl_id=candidates[p]["parent_chembl_id"],molecule=candidates[p]["pref_name"])
        r["specificity"] = step3.specificity(r["target_type"],r["target_tax_id"],r["confidence_score"],r["relationship_type"],r["variant_id"])
        r["study_key"],r["provenance_class"] = step3.study_key(r["pubmed_id"],r["doi"],r["patent_id"],r["doc_chembl_id"],r["doc_type"])
        r["role"] = "functional"
        r["endpoint_class"] = "functional:"+r["standard_type"]
        r["standard_value_nM"] = r["standard_value"] if r["standard_units"] == "nM" else None
        r["has_existing_functional_claim"] = int(claim_key(r) in existing)
        r["protein_assigned"] = int(r["target_type"] in ("SINGLE PROTEIN","PROTEIN FAMILY","PROTEIN COMPLEX","PROTEIN COMPLEX GROUP"))
        r["numerically_exact_nM"] = int(r["standard_relation"] == "=" and r["standard_units"] == "nM" and r["standard_value"] is not None and r["standard_value"] > 0)
        organism.append(r)
    write("organism_context.csv.gz", organism)
    protein_rows = write("organism_protein_assigned.csv", [r for r in organism if r["protein_assigned"]])
    review = json.loads((HERE / "organism_review.json").read_text())
    reviewed_rows = []
    for r in protein_rows:
        decision = review["reviews"][r["assay_chembl_id"]]
        reviewed_rows.append(dict(r,context_class=decision["class"],review_reason=decision["reason"],
                                 recommended_tier_change="none_pending_context_validation"))
    write("organism_reviewed.csv",reviewed_rows)
    write("organism_review_summary.csv",[dict(context_class=k,records=v) for k,v in sorted(collections.Counter(r["context_class"] for r in reviewed_rows).items())])
    org_summary = collections.Counter((r["target_type"],r["specificity"]) for r in organism)
    write("organism_summary.csv", [dict(target_type=t,specificity=s,records=n) for (t,s),n in sorted(org_summary.items(),key=lambda x:str(x[0]))])
    # Diagnostic only: quantify the consequences of removing the gate. Do not recommend pooling.
    unsafe_changes = []
    org_by_claim = collections.defaultdict(list)
    for r in protein_rows:
        if r["numerically_exact_nM"]:
            org_by_claim[claim_key(r)].append(r)
    for key, rows in sorted(org_by_claim.items()):
        old=by_key.get(key, [])
        unsafe_changes.append(dict(parent_molregno=key[0],target_chembl_id=key[1],role=key[2],
            added_exact=len(rows),old_tier=assess(old),unsafe_pooled_tier=assess(old+rows),
            would_change_tier=int(assess(old)!=assess(old+rows)),
            caveat="Diagnostic of blanket gate removal only; mixes assay contexts and is not adopted"))
    write("organism_unsafe_pooling_diagnostic.csv",unsafe_changes)

    # Build support separately within each permitted target-assignment basis.
    evidence = {}
    allowed_types = {"human_single":{"SINGLE PROTEIN"},"human_single_and_complex":{"SINGLE PROTEIN","PROTEIN COMPLEX"},
                     "human_with_families":{"SINGLE PROTEIN","PROTEIN COMPLEX","PROTEIN COMPLEX GROUP","PROTEIN FAMILY"}}
    for scenario in ["baseline", "concentration_only"]:
        for basis, types in allowed_types.items():
            ex = collections.defaultdict(list)
            for r in exact + scenarios[scenario]:
                if assignment_matches(r,basis):
                    ex[claim_key(r)].append(r)
            entries = []
            for key, rows in ex.items():
                entries.append((key,assess(rows)))
            for c in claims:
                if c["claim_role"] == "curated" and c["curated_support"] == "1" and c["target_tax_id"] == "9606" and c["target_type"] in types:
                    entries.append((claim_key(c),"supported"))
            evidence[(scenario,basis)] = entries
    summaries, memberships, seed_rows = [], [], []
    seeds = common.read_csv("seed_membership.csv")
    for policy in RULES["policies"]:
        for category in RULES["policy_categories"]:
            pid = policy["id"]+"__"+category
            selected = {p for p,c in candidates.items() if membership(c,policy,category)}
            for p in sorted(selected,key=int):
                memberships.append(dict(policy=pid,parent_molregno=p,parent_chembl_id=candidates[p]["parent_chembl_id"],molecule=candidates[p]["pref_name"],
                    admitted_via_atc=int(policy["keep_atc"] and candidates[p]["route_atc_n"]=="1"),
                    cns_ind_max_phase=candidates[p]["cns_ind_max_phase"]))
            for s in seeds:
                p = next((p for p,c in candidates.items() if c["parent_chembl_id"]==s["parent_chembl_id"]),None)
                seed_rows.append(dict(policy=pid,seed=s["seed_name"],parent_chembl_id=s["parent_chembl_id"],included=int(p in selected),
                    reason="qualifies" if p in selected else s["admission_or_exclusion_reason"] if p is None else "fails_phase_route_or_category"))
            for (scenario,basis), entries in evidence.items():
                filtered = [(k,tier) for k,tier in entries if k[0] in selected]
                supported = [k for k,t in filtered if t=="supported"]
                preliminary = [k for k,t in filtered if t=="preliminary"]
                measurable = supported + preliminary
                summaries.append(dict(policy=pid,label=policy["label"],category=category,scenario=scenario,evidence_basis=basis,
                    catalogue_molecules=len(selected),withdrawn_flagged=sum(candidates[p]["withdrawn_any_family"]=="1" for p in selected),
                    identity_none=sum(candidates[p]["structure_type"]=="NONE" for p in selected),
                    supported_claims=len(supported),supported_pairs=len({k[:2] for k in supported}),supported_targets=len({k[1] for k in supported}),
                    molecules_with_supported=len({k[0] for k in supported}),preliminary_claims=len(preliminary),
                    molecules_with_supported_or_preliminary=len({k[0] for k in measurable}),
                    molecules_without_qualifying_edges=len(selected-{k[0] for k in measurable}),
                    seeds_retained=sum(r["included"] for r in seed_rows if r["policy"]==pid)))
    write("policy_membership.csv",memberships)
    write("policy_seed_membership.csv",seed_rows)
    write("policy_comparison.csv",summaries)
    # Evidence selection is fully auditable without duplicating it for every membership policy.
    write("evidence_by_basis.csv.gz",[dict(scenario=s,basis=b,parent_molregno=k[0],target_chembl_id=k[1],role=k[2],tier=t)
          for (s,b),entries in evidence.items() for k,t in sorted(entries)])

    # Reconstruct scope union from exported descriptor classification, not current MeSH.
    scope={r["mesh_id"]:r for r in common.read_csv("indication_scope.csv")}
    ind=conn.execute("SELECT molregno,mesh_id FROM drug_indication").fetchall()
    atc_rows=conn.execute("SELECT DISTINCT mac.molregno FROM molecule_atc_classification mac JOIN atc_classification a USING(level5) WHERE a.level1='N'").fetchall()
    parent=step2.parents_for(conn,{r["molregno"] for r in ind}|{r["molregno"] for r in atc_rows})
    atc={parent[r["molregno"]] for r in atc_rows}
    def scope_set(adds):
        return atc|{parent[r["molregno"]] for r in ind if r["mesh_id"] in scope and
                   (scope[r["mesh_id"]]["in_core_scope"]=="1" or set(adds)&set(scope[r["mesh_id"]]["scope_classes"].split(";")))}
    scope_variants={"core":[],"core_plus_oncology":["cns_oncology"],"core_plus_pain":["general_pain"],
                    "core_plus_oncology_and_pain":["cns_oncology","general_pain"],
                    "widest":["cns_oncology","general_pain","peripheral_nervous_system","muscle_and_neuromuscular_junction"]}
    scope_counts={k:len(scope_set(v)) for k,v in scope_variants.items()}
    write("scope_comparison.csv",[dict(scope=k,molecules=v,extra_vs_core=v-scope_counts["core"],evidence_for_added_molecules="not assessed") for k,v in scope_counts.items()])

    # A measurement can be retained in the baseline audit yet excluded from numerical use.
    statuses=collections.Counter(r["status"] for r in measurements)
    relations=collections.Counter(r["standard_relation"] for r in measurements if r["status"]=="retained_as_bound")
    exceptions=[]
    for r in conn.execute("""SELECT act.activity_id,a.chembl_id assay_chembl_id,act.molregno,a.description,
          act.standard_type,act.standard_relation,act.standard_value,act.standard_units
          FROM activities act JOIN followup_members fm USING(molregno) JOIN assays a USING(assay_id)
          WHERE a.chembl_id IN ('CHEMBL5133661','CHEMBL1074487') ORDER BY act.activity_id"""):
        exceptions.append(dict(r))
    write("known_bad_excluded_records.csv",exceptions)
    baseline_mismatches=[k for k,rs in by_key.items() if assess(rs)!=existing[k]["tier"]]
    expected_human={(claim_key(c),c["tier_human_direct"]) for c in claims if c["tier_human_direct"] in ("supported","preliminary")}
    actual_human=set(evidence[("baseline","human_single")])
    protected=json.loads((HERE/"protected-before.json").read_text())
    protected_ok=all(common.sha256(common.PROJECT/p)==s["sha256"] for p,s in protected.items())
    checks={"baseline_experimental_tiers_reproduced":not baseline_mismatches,
            "baseline_human_tiers_reproduced":expected_human==actual_human,
            "all_non_nM_records_accounted_for":len(unit_rows)==statuses["excluded_units"],
            "scope_core_reproduced":scope_counts["core"]==len(candidates),
            "organism_rows_reproduced":len(organism)==21999,
            "organism_assay_review_complete":{r["assay_chembl_id"] for r in protein_rows}==set(review["reviews"]),
            "no_family_fanout":all(len(entries)==len({k for k,t in entries}) for entries in evidence.values()),
            "production_fingerprints_unchanged":protected_ok}
    write("validation.csv",[dict(check=k,result="PASS" if v else "FAIL") for k,v in checks.items()])
    meta={"rules_version":RULES["version"],"chembl_release":common.CHEMBL_RELEASE,
          "chembl_path":str(common.CHEMBL_DB),"chembl_bytes":common.CHEMBL_DB.stat().st_size,
          "source_coverage":"ChEMBL 37 and baseline exported MeSH classification only; no current MeSH fetch or new pharmacology source",
          "input_sha256":{str(p.relative_to(common.PROJECT)):common.sha256(p) for p in [HERE/"rules.json",HERE/"organism_review.json",HERE/"analyze.py",HERE.parent/"scripts/common.py",HERE.parent/"scripts/step2_candidates.py",HERE.parent/"scripts/step3_evidence.py",common.OUT/"candidates.csv",common.OUT/"family_members.csv",common.OUT/"seed_membership.csv",common.OUT/"assessed_claims.csv.gz",common.OUT/"measurements.csv.gz",common.OUT/"indication_scope.csv"]},
          "measurement_status_counts":dict(statuses),"retained_relation_counts":dict(relations),
          "unit_recovery_classes":dict(collections.Counter(r["recovery_class"] for r in unit_rows)),
          "scope_counts":scope_counts,"organism_protein_assigned":len(protein_rows),
          "organism_exact_protein_assigned":sum(r["numerically_exact_nM"] for r in protein_rows),
          "baseline_tier_mismatches":len(baseline_mismatches),"human_tier_symmetric_difference":len(expected_human^actual_human),
          "checks":checks}
    (OUT/"summary.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
    if not all(checks.values()):
        raise SystemExit("Follow-up validation failed; inspect out/summary.json")


if __name__ == "__main__":
    main()
