"""Step 4 - roll the per-row outputs up into the tables the report quotes.

Everything here is arithmetic over the CSVs written by steps 2 and 3. No
database is read except the project's own ``db/subnetwork.db``, opened
read-only and only to answer "which of these targets are already in the
graph" - the report's new-coverage question. If that database is absent the
comparison is reported as not assessed rather than as zero.

Writes: report_tables.json (every number the report quotes, with the key it
is quoted under), plus stage_breakdown.csv, tier_distribution.csv,
threshold_sensitivity.csv, family_coverage.csv, seed_report.csv.
"""

import collections
import csv
import sys

import common


def read(name):
    return common.read_csv(name)


def i(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


STAGE_ORDER = ["Approved", "Phase 3", "Phase 2", "Phase 1", "Early Phase 1",
               "Unknown (ChEMBL -1)", "Missing (no phase recorded)",
               "Missing (no phase on the qualifying indication)",
               "Not applicable (ATC route only)"]


def ordered(counter):
    out = {k: counter[k] for k in STAGE_ORDER if k in counter}
    for k in sorted(counter):
        out.setdefault(k, counter[k])
    return out


def main() -> int:
    scope = common.load_config("cns_indication_scope.json")
    rules = common.load_config("tier_rules.json")

    cands = read("candidates.csv")
    claims = read("assessed_claims.csv")
    mols = read("molecule_evidence.csv")
    pairs = read("target_pairs.csv")
    thresholds = read("claim_thresholds.csv")
    seeds = read("seed_membership.csv")
    gaps = read("coverage_gaps.csv")
    arith = read("route_arithmetic.csv")
    inds = read("candidate_indications.csv")
    atcs = read("candidate_atc_codes.csv")
    scope_tbl = read("indication_scope.csv")

    T = {}
    T["catalogue"] = {
        "parents_total": len(cands),
        "by_molecule_type": dict(collections.Counter(
            c["molecule_type"] for c in cands).most_common()),
        "by_structure_type": dict(collections.Counter(
            c["structure_type"] for c in cands).most_common()),
        "by_route": dict(collections.Counter(c["route_combination"] for c in cands)),
        "small_molecule_parents": sum(1 for c in cands
                                      if c["molecule_type"] == "Small molecule"),
        "unresolved_identity_structure_none": sum(
            1 for c in cands if c["structure_type"] == "NONE"),
        "withdrawn_any_family": sum(1 for c in cands if c["withdrawn_any_family"] == "1"),
    }
    T["route_arithmetic"] = arith

    # ------------------------------------------------------------ stages
    sm = [c for c in cands if c["molecule_type"] == "Small molecule"]
    stage_rows = []
    for label, subset in [("all_candidates", cands), ("small_molecules", sm),
                          ("atc_n_route", [c for c in cands if c["route_atc_n"] == "1"]),
                          ("cns_indication_route",
                           [c for c in cands if c["route_cns_indication"] == "1"]),
                          ("both_routes",
                           [c for c in cands if c["route_combination"] == "both"])]:
        fam = ordered(collections.Counter(c["family_max_phase_label"] for c in subset))
        ind = ordered(collections.Counter(c["cns_ind_max_phase_label"] for c in subset))
        for k, v in fam.items():
            stage_rows.append({"subset": label, "phase_basis": "family_max_phase",
                               "stage": k, "n_molecules": v})
        for k, v in ind.items():
            stage_rows.append({"subset": label,
                               "phase_basis": "cns_indication_max_phase_for_ind",
                               "stage": k, "n_molecules": v})
    common.write_csv("stage_breakdown.csv",
                     ["subset", "phase_basis", "stage", "n_molecules"], stage_rows)
    T["stage_breakdown"] = stage_rows

    T["cumulative_stage_choices"] = {
        r["stage"]: {"union": i(r["union"]), "note": r["note"]}
        for r in arith if r["stage"].startswith("cns_indication_stage_")
    }

    # ---------------------------------------------------------- boundaries
    flag_counts = collections.Counter()
    for a in atcs:
        if a["boundary_flag"]:
            flag_counts[(a["boundary_flag"], a["atc_level3"])] += 1
    T["atc_boundary_flags"] = {
        f"{flag} ({lvl2})": len({a["parent_chembl_id"] for a in atcs
                                 if a["boundary_flag"] == flag and a["atc_level3"] == lvl2})
        for (flag, lvl2) in flag_counts}
    T["scope_variants"] = {
        r["stage"].replace("scope_variant_", ""): {
            "union": i(r["union"]), "cns_indication_total": i(r["cns_indication_total"]),
            "delta_vs_core": i(r["union"]) - next(
                i(x["union"]) for x in arith if x["stage"] == "scope_variant_S0_core"),
            "label": r["note"]}
        for r in arith if r["stage"].startswith("scope_variant_")}
    T["indication_scope"] = {
        "descriptors_in_core": sum(1 for r in scope_tbl if r["in_core_scope"] == "1"),
        "descriptors_in_core_used_by_chembl": sum(
            1 for r in scope_tbl if r["in_core_scope"] == "1"
            and i(r["drug_indication_rows"]) > 0),
        "descriptors_unresolved": sum(
            1 for _ in open(common.CACHE / "mesh_unresolved.tsv", encoding="utf-8")) - 1,
        "top_core_descriptors": [
            {"mesh_id": r["mesh_id"], "label": r["mesh_label"],
             "molecules": i(r["distinct_parent_molecules"]),
             "rows": i(r["drug_indication_rows"])}
            for r in sorted((r for r in scope_tbl if r["in_core_scope"] == "1"),
                            key=lambda r: -i(r["distinct_parent_molecules"]))[:15]],
    }

    # --------------------------------------------------------------- tiers
    tier_rows = []
    for role in ("curated", "binding", "functional"):
        for basis, field in (("all_assessed_evidence", "tier"),
                             ("direct_human_single_protein_only", "tier_human_direct")):
            cnt = collections.Counter(c[field] for c in claims if c["claim_role"] == role)
            for tier, n in sorted(cnt.items()):
                tier_rows.append({"claim_role": role, "basis": basis,
                                  "tier": tier, "n_claims": n})
    common.write_csv("tier_distribution.csv",
                     ["claim_role", "basis", "tier", "n_claims"], tier_rows)
    T["tier_distribution"] = tier_rows
    T["claims_total"] = len(claims)
    T["claims_by_tier"] = dict(collections.Counter(c["tier"] for c in claims))
    T["claims_by_tier_human_direct"] = dict(
        collections.Counter(c["tier_human_direct"] for c in claims))
    T["claim_tier_reasons"] = dict(collections.Counter(
        c["tier_reasons"] for c in claims).most_common(20))
    T["limited_reasons"] = dict(collections.Counter(
        c["tier_reasons"] for c in claims
        if c["tier"] == "limited_or_unresolved").most_common(15))

    T["support_routes"] = {
        "claims_curated_support": sum(1 for c in claims if c["curated_support"] == "1"),
        "claims_multiple_study_support": sum(
            1 for c in claims if c["multiple_study_support"] == "1"),
        "claims_multiple_study_support_human_direct": sum(
            1 for c in claims if c["multiple_study_support_human_direct"] == "1"),
        "pairs_total": len(pairs),
        "pairs_curated_only": sum(1 for p in pairs if p["support_routes"] == "curated_only"),
        "pairs_multiple_study_only": sum(
            1 for p in pairs if p["support_routes"] == "multiple_study_only"),
        "pairs_both_routes": sum(1 for p in pairs if p["support_routes"] == "both"),
        "pairs_neither": sum(1 for p in pairs if p["support_routes"] == "neither"),
    }

    T["specificity"] = dict(collections.Counter(
        c["assignment_specificity"] for c in claims).most_common())
    T["curated_claim_specificity"] = dict(collections.Counter(
        c["claim_target_specificity"] for c in claims if c["claim_role"] == "curated"))
    T["curated_family_level_examples"] = [
        {"molecule": c["pref_name"], "molecule_chembl_id": c["parent_chembl_id"],
         "target": c["target_pref_name"], "target_chembl_id": c["target_chembl_id"],
         "target_type": c["target_type"], "action": c["curated_actions"],
         "mechanism": c["mechanism_of_action"]}
        for c in claims
        if c["claim_target_specificity"] == "family_or_complex_level"][:12]

    T["conflicts"] = {
        "claims_with_action_conflict": sum(1 for c in claims if c["conflict_action"] == "1"),
        "claims_with_action_variant_only": sum(
            1 for c in claims if c["conflict_action_variant"] == "1"),
        "claims_with_dispersion_conflict": sum(
            1 for c in claims if c["conflict_dispersion"] == "1"),
        "action_variant_examples": [
            {"molecule": c["pref_name"], "target": c["target_pref_name"],
             "actions": c["curated_actions"], "detail": c["conflict_detail"]}
            for c in claims if c["conflict_action_variant"] == "1"][:10],
        "pairs_with_action_conflict": sum(1 for p in pairs if p["conflict_action"] == "1"),
        "dispersion_examples": [
            {"molecule": c["pref_name"], "target": c["target_pref_name"],
             "role": c["claim_role"], "detail": c["conflict_detail"],
             "tier": c["tier"], "n_studies": c["n_studies_publication"]}
            for c in claims if c["conflict_dispersion"] == "1"][:10],
        "action_conflict_examples": [
            {"molecule": c["pref_name"], "target": c["target_pref_name"],
             "actions": c["curated_actions"], "detail": c["conflict_detail"]}
            for c in claims if c["conflict_action"] == "1"][:10],
    }

    # --------------------------------------------------------- molecules
    T["molecule_level"] = {
        "molecules_assessed": len(mols),
        "with_any_evidence": sum(1 for m in mols
                                 if m["evidence_status"] == "assessed_with_evidence"),
        "no_eligible_evidence_found": len(gaps),
        "with_any_supported_claim": sum(1 for m in mols if i(m["n_supported"]) > 0),
        "with_any_curated_support": sum(1 for m in mols if i(m["n_curated_support"]) > 0),
        "with_any_multiple_study_support": sum(
            1 for m in mols if i(m["n_multiple_study_support"]) > 0),
        "with_pair_supported_by_both_routes": sum(
            1 for m in mols if i(m["n_pairs_both_routes"]) > 0),
        "with_any_qualifying_human_target_claim": sum(
            1 for m in mols if m["any_qualifying_human_target_claim"] == "1"),
        "with_supported_human_direct_claim": sum(
            1 for m in mols if i(m["n_supported_human_direct"]) > 0),
        "with_only_limited_or_unresolved": sum(
            1 for m in mols if i(m["n_claims"]) > 0 and i(m["n_supported"]) == 0
            and i(m["n_preliminary"]) == 0),
    }
    T["coverage_gaps"] = {
        "molecules": len(gaps),
        "by_molecule_type": dict(collections.Counter(g["molecule_type"] for g in gaps)),
        "by_route": dict(collections.Counter(g["route_combination"] for g in gaps)),
        "approved_cns_indication": sum(
            1 for g in gaps if g["cns_ind_max_phase_label"] == "Approved"),
        "examples": [{"chembl_id": g["parent_chembl_id"], "name": g["pref_name"],
                      "type": g["molecule_type"], "route": g["route_combination"],
                      "cns_phase": g["cns_ind_max_phase_label"]} for g in gaps[:15]],
    }

    # -------------------------------------------------------- thresholds
    th_rows = []
    for um in rules["thresholds"]["micromolar"]:
        for basis, subset in (("all_assessed_evidence", thresholds),
                              ("direct_human_single_protein_only",
                               [t for t in thresholds
                                if t["human_direct_single_protein"] == "1"])):
            by_class = collections.defaultdict(lambda: [0, 0, set(), set()])
            for t in subset:
                k = t["endpoint_class"]
                by_class[k][0] += i(t[f"median_pass_{um}uM"])
                by_class[k][1] += i(t[f"any_pass_{um}uM"])
                if t[f"median_pass_{um}uM"] == "1":
                    by_class[k][2].add(t["parent_molregno"])
                if t[f"any_pass_{um}uM"] == "1":
                    by_class[k][3].add(t["parent_molregno"])
            for cls, (nm, na, mm, ma) in sorted(by_class.items()):
                th_rows.append({
                    "threshold_uM": um, "basis": basis, "endpoint_class": cls,
                    "claims_pass_median_rule": nm, "claims_pass_any_rule": na,
                    "molecules_pass_median_rule": len(mm),
                    "molecules_pass_any_rule": len(ma),
                })
            tot_m = {t["parent_molregno"] for t in subset if t[f"median_pass_{um}uM"] == "1"}
            tot_a = {t["parent_molregno"] for t in subset if t[f"any_pass_{um}uM"] == "1"}
            th_rows.append({
                "threshold_uM": um, "basis": basis, "endpoint_class": "ALL_CLASSES_UNION",
                "claims_pass_median_rule": sum(
                    i(t[f"median_pass_{um}uM"]) for t in subset),
                "claims_pass_any_rule": sum(i(t[f"any_pass_{um}uM"]) for t in subset),
                "molecules_pass_median_rule": len(tot_m),
                "molecules_pass_any_rule": len(tot_a),
            })
    common.write_csv("threshold_sensitivity.csv", list(th_rows[0].keys()), th_rows)
    T["threshold_sensitivity"] = [r for r in th_rows
                                  if r["endpoint_class"] == "ALL_CLASSES_UNION"]
    T["threshold_note"] = rules["thresholds"]["scope"]

    # ---------------------------------------------------- family coverage
    graph_targets, graph_status = set(), "not assessed"
    pdb = common.project_db()
    if pdb is not None:
        try:
            graph_targets = {r[0] for r in pdb.execute(
                "SELECT uniprot_accession FROM targets WHERE uniprot_accession IS NOT NULL")}
            graph_status = f"read from {common.PROJECT_DB.name} ({len(graph_targets)} targets)"
        except Exception as exc:                                # pragma: no cover
            graph_status = f"present but unreadable: {exc}"
        pdb.close()
    else:
        graph_status = ("db/subnetwork.db absent - new-vs-existing coverage "
                        "not assessed (reported as unknown, not as zero)")

    obs = read("observed_targets.csv")
    fam = collections.defaultdict(lambda: {"targets": set(), "molecules": 0,
                                           "claims": 0, "supported": 0,
                                           "new_targets": set()})
    for o in obs:
        key = o["target_family_l1"] or "(unclassified)"
        f = fam[key]
        f["targets"].add(o["target_chembl_id"])
        f["molecules"] += i(o["n_molecules"])
        f["claims"] += i(o["n_claims"])
        f["supported"] += i(o["n_supported"])
        accs = {a for a in (o["target_accessions"] or "").split(",") if a}
        if graph_targets and not (accs & graph_targets):
            f["new_targets"].add(o["target_chembl_id"])
    fam_rows = sorted(({"target_family_l1": k, "n_targets": len(v["targets"]),
                        "n_claims": v["claims"], "n_supported_claims": v["supported"],
                        "n_targets_not_in_current_graph": len(v["new_targets"])}
                       for k, v in fam.items()),
                      key=lambda r: -r["n_targets"])
    common.write_csv("family_coverage.csv", list(fam_rows[0].keys()), fam_rows)

    all_acc = set()
    for o in obs:
        all_acc |= {a for a in (o["target_accessions"] or "").split(",") if a}
    T["target_coverage"] = {
        "distinct_targets_observed": len(obs),
        "distinct_uniprot_accessions": len(all_acc),
        "current_graph_status": graph_status,
        "current_graph_targets": len(graph_targets),
        "graph_targets_also_observed": len(graph_targets & all_acc) if graph_targets else None,
        "graph_targets_not_observed": len(graph_targets - all_acc) if graph_targets else None,
        "accessions_new_vs_graph": len(all_acc - graph_targets) if graph_targets else None,
        "by_family": fam_rows,
        "top_targets": [{"target": o["target_pref_name"],
                         "chembl_id": o["target_chembl_id"],
                         "type": o["target_type"], "organism": o["target_organism"],
                         "molecules": i(o["n_molecules"]),
                         "supported_claims": i(o["n_supported"])} for o in obs[:20]],
    }

    # -------------------------------------------------------------- seeds
    ev = {m["parent_chembl_id"]: m for m in mols}
    seed_rows = []
    for s in seeds:
        e = ev.get(s["parent_chembl_id"], {})
        seed_rows.append({
            "seed_name": s["seed_name"],
            "seed_chembl_id": s["seed_chembl_id"],
            "parent_chembl_id": s["parent_chembl_id"],
            "seed_is_parent": s["seed_is_parent"],
            "in_catalogue": s["in_catalogue"],
            "route_atc_n": s["route_atc_n"],
            "route_cns_indication": s["route_cns_indication"],
            "admission_or_exclusion_reason": s["admission_or_exclusion_reason"],
            "cns_ind_max_phase": s["cns_ind_max_phase"],
            "n_claims": e.get("n_claims", "not assessed - not in catalogue"),
            "n_supported": e.get("n_supported", ""),
            "n_preliminary": e.get("n_preliminary", ""),
            "n_limited_or_unresolved": e.get("n_limited_or_unresolved", ""),
            "n_curated_support": e.get("n_curated_support", ""),
            "n_multiple_study_support": e.get("n_multiple_study_support", ""),
            "n_supported_human_direct": e.get("n_supported_human_direct", ""),
            "any_qualifying_human_target_claim":
                e.get("any_qualifying_human_target_claim", ""),
            "evidence_status": e.get("evidence_status",
                                     "not assessed - outside the catalogue"),
        })
    common.write_csv("seed_report.csv", list(seed_rows[0].keys()), seed_rows)
    T["seeds"] = {
        "total": len(seed_rows),
        "in_catalogue": sum(1 for s in seed_rows if s["in_catalogue"] == "1"),
        "excluded": [{"name": s["seed_name"], "chembl_id": s["seed_chembl_id"],
                      "reason": s["admission_or_exclusion_reason"]}
                     for s in seed_rows if s["in_catalogue"] != "1"],
        "by_route": dict(collections.Counter(
            ("both" if s["route_atc_n"] == "1" and s["route_cns_indication"] == "1"
             else "atc_only" if s["route_atc_n"] == "1"
             else "indication_only" if s["route_cns_indication"] == "1" else "not_admitted")
            for s in seed_rows)),
        "with_supported_human_direct": sum(
            1 for s in seed_rows if i(s["n_supported_human_direct"]) > 0),
        "rows": seed_rows,
    }

    # ------------------------------------------------- identity / mappings
    fams = read("family_members.csv")
    per_parent = collections.Counter(f["parent_molregno"] for f in fams)
    T["identity"] = {
        "parents": len(cands),
        "family_members_total": len(fams),
        "parents_with_salts_or_forms": sum(1 for n in per_parent.values() if n > 1),
        "largest_family": max(per_parent.values()),
        "members_carrying_atc_but_not_parent": sum(
            1 for f in fams if f["member_carries_atc_n"] == "1" and f["is_parent"] == "0"),
        "members_carrying_indication_but_not_parent": sum(
            1 for f in fams
            if f["member_carries_scoped_indication"] == "1" and f["is_parent"] == "0"),
        "seeds_not_their_own_parent": [
            {"seed": s["seed_name"], "seed_chembl_id": s["seed_chembl_id"],
             "parent_chembl_id": s["parent_chembl_id"]}
            for s in seeds if s["seed_is_parent"] == "0"],
    }

    T["indication_records"] = {
        "candidate_indication_rows": len(inds),
        "in_core_scope": sum(1 for r in inds if r["in_core_scope"] == "1"),
        "boundary_only": sum(1 for r in inds if r["in_core_scope"] != "1"),
        "phase_on_qualifying_indication": dict(collections.Counter(
            r["max_phase_for_ind_label"] for r in inds if r["in_core_scope"] == "1")),
    }

    T["provenance"] = {
        "scope_version": scope["version"],
        "tier_rules_version": rules["version"],
        "chembl_release": common.CHEMBL_RELEASE,
        "source_coverage_note": rules["source_coverage"],
    }

    common.write_json("report_tables.json", T)
    return 0


if __name__ == "__main__":
    sys.exit(main())
