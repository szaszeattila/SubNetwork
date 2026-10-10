"""Step 3 - assess ChEMBL 37 target evidence for the fixed cohort-1 candidate set.

The candidate set is already fixed by step 2. Nothing here can add or remove a
molecule: a candidate with no evidence stays in the catalogue and is written
out as a coverage gap.

Evidence is assessed uniformly across every candidate, at the molecule-target
claim level, against ``config/tier_rules.json``. Two claim families:

  curated     ChEMBL ``drug_mechanism`` records, at the target and action
              specificity ChEMBL itself asserts. A family-level or
              complex-level mechanism stays a family-level claim.
  experimental ``activities`` joined through ``assays`` to a target, split
              into binding (assay_type B) and functional (assay_type F)
              roles and never pooled across endpoint types.

Support is counted in distinct *studies*, not in activity rows and not in
database appearances. Deposited bulk datasets are one study however many
rows they carry, and never create multi-study support.

Writes: assessed_claims.csv, claim_studies.csv, claim_thresholds.csv,
evidence_exclusions.csv, coverage_gaps.csv, observed_targets.csv,
molecule_evidence.csv, measurements.csv.gz, step3_summary.json.
"""

import collections
import csv
import gzip
import math
import statistics
import sys

import common

ENDPOINT_TYPES = ("Ki", "Kd", "IC50", "EC50", "AC50", "Kb")
CENSORED_RELATIONS = (">", "<", ">=", "<=", "~", ">>", "<<")

POSITIVE = "POSITIVE MODULATOR"
NEGATIVE = "NEGATIVE MODULATOR"


def specificity(target_type, tax_id, conf, rel, variant_id) -> str:
    """Classify one activity's target assignment. See config/tier_rules.json.

    Order matters: the human direct single-protein test is the narrowest and
    is applied first, so nothing broader can be mistaken for it.
    """
    human = tax_id == 9606
    if (target_type == "SINGLE PROTEIN" and human and conf == 9 and rel == "D"):
        return ("human_direct_single_protein" if variant_id is None
                else "human_direct_single_protein_mutant")
    if target_type in ("PROTEIN COMPLEX", "PROTEIN COMPLEX GROUP") and human and conf == 7:
        return "human_direct_complex"
    if human and (target_type == "PROTEIN FAMILY" or conf == 5):
        return "human_family_or_multiple"
    if conf in (4, 6, 8) or rel == "H":
        return "homologous_or_unknown_species"
    if tax_id is not None and not human:
        return "nonhuman"
    if (conf is not None and conf <= 3) or rel in ("N", "S", "M", "U"):
        return "non_protein_or_unassigned"
    return "other"


def study_key(pmid, doi, patent_id, doc_chembl_id, doc_type):
    """Identify the original study behind a measurement, and how well it resolves."""
    if pmid:
        return f"pmid:{pmid}", ("publication" if doc_type == "PUBLICATION" else "deposited_dataset")
    if doi:
        return f"doi:{doi}", ("publication" if doc_type == "PUBLICATION" else
                              "deposited_dataset" if doc_type == "DATASET" else "unresolved")
    if patent_id:
        return f"patent:{patent_id}", "patent"
    if doc_chembl_id:
        return (f"doc:{doc_chembl_id}",
                "deposited_dataset" if doc_type == "DATASET" else "unresolved")
    return None, "unresolved"


def log_median(values):
    return 10 ** statistics.median([math.log10(v) for v in values])


def exclusion_retained_in_measurements(reason):
    """Whether rejected activity rows reach measurements.csv.gz, not the median.

    The first four gates continue before measurements.append; all later
    validation statuses remain in the row-level audit. Known-bad records were
    previously labelled retained even though only their aggregate count was.
    """
    return reason in {"censored_bound", "null_value", "units_not_nM",
                      "nonpositive_value", "other_relation"}


def main() -> int:
    rules = common.load_config("tier_rules.json")
    excluded_assays = set(
        rules["measurement_validity"]["documented_exclusions"]["CHEMBL_ASSAY_LINK_EXCLUSIONS"])

    with open(common.OUT / "family_members.csv", encoding="utf-8") as fh:
        fam_rows = list(csv.DictReader(fh))
    member_to_parent = {int(r["member_molregno"]): int(r["parent_molregno"]) for r in fam_rows}
    with open(common.OUT / "candidates.csv", encoding="utf-8") as fh:
        cand_rows = list(csv.DictReader(fh))
    parent_name = {int(r["parent_molregno"]): (r["parent_chembl_id"], r["pref_name"],
                                               r["molecule_type"])
                   for r in cand_rows}
    common.log(f"  {len(parent_name)} candidate parents, {len(member_to_parent)} family members")

    conn = common.chembl()
    conn.execute("CREATE TEMP TABLE cand(molregno INTEGER PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO cand VALUES(?)",
                     [(m,) for m in member_to_parent])
    conn.execute("CREATE TEMP TABLE parent_ids(molregno INTEGER PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO parent_ids VALUES(?)",
                     [(p,) for p in parent_name])

    # ---------------------------------------------------------------- targets
    targets = {}
    for row in conn.execute("""
        SELECT td.tid, td.chembl_id, td.pref_name, td.target_type, td.organism, td.tax_id,
               (SELECT GROUP_CONCAT(DISTINCT cs.accession) FROM target_components tc
                  JOIN component_sequences cs ON cs.component_id = tc.component_id
                 WHERE tc.tid = td.tid) AS accessions,
               (SELECT COUNT(*) FROM target_components tc WHERE tc.tid = td.tid) AS n_components
          FROM target_dictionary td"""):
        targets[row["tid"]] = dict(row)

    # ChEMBL's own protein-classification tree, used ONLY to summarise family
    # coverage. docs/DATA-QUALITY-LOG.md records that it must never be used to
    # infer physical assembly - it is a sequence/function taxonomy blind to that.
    fam_of_tid = {}
    try:
        pc = {r["protein_class_id"]: (r["parent_id"], r["pref_name"], r["class_level"])
              for r in conn.execute(
                  "SELECT protein_class_id, parent_id, pref_name, class_level "
                  "FROM protein_classification")}

        def ancestry(cid):
            """(level-1 name, level-2 name) for one protein class, walking to the root."""
            chain = []
            seen = set()
            while cid is not None and cid in pc and cid not in seen:
                seen.add(cid)
                parent, name, level = pc[cid]
                if level and level >= 1:
                    chain.append((level, name))
                cid = parent
            chain.sort()
            l1 = next((n for lv, n in chain if lv == 1), "")
            l2 = next((n for lv, n in chain if lv == 2), "")
            return l1, l2

        for row in conn.execute("""
            SELECT tc.tid, cc.protein_class_id
              FROM target_components tc
              JOIN component_class cc ON cc.component_id = tc.component_id"""):
            l1, l2 = ancestry(row["protein_class_id"])
            if l1 or l2:
                fam_of_tid.setdefault(row["tid"], set()).add((l1, l2, ""))
        family_source = ("ChEMBL protein_classification, walked to levels 1 and 2. "
                         "Used ONLY to summarise family coverage - never to infer "
                         "physical assembly (see docs/DATA-QUALITY-LOG.md).")
    except Exception as exc:                                   # pragma: no cover
        family_source = f"unavailable: {exc}"
        common.log(f"  protein_classification unavailable: {exc}")

    # ------------------------------------------------------- curated mechanisms
    mech_refs = collections.defaultdict(list)
    for row in conn.execute("""
        SELECT r.mec_id, r.ref_type, r.ref_id, r.ref_url
          FROM mechanism_refs r JOIN drug_mechanism d ON d.mec_id = r.mec_id
          JOIN cand c ON c.molregno = d.molregno ORDER BY r.mecref_id"""):
        mech_refs[row["mec_id"]].append(dict(row))

    curated = collections.defaultdict(list)      # (parent, target_chembl) -> [mech rows]
    curated_unassigned = []
    for row in conn.execute("""
        SELECT d.mec_id, d.molregno, d.tid, d.action_type, d.mechanism_of_action,
               d.direct_interaction, d.molecular_mechanism, d.disease_efficacy,
               d.mechanism_comment, d.selectivity_comment, d.variant_id, d.record_id,
               at.parent_type
          FROM drug_mechanism d JOIN cand c ON c.molregno = d.molregno
          LEFT JOIN action_type at ON at.action_type = d.action_type
         ORDER BY d.mec_id"""):
        parent = member_to_parent[row["molregno"]]
        if row["tid"] is None:
            curated_unassigned.append((parent, dict(row)))
            continue
        tgt = targets.get(row["tid"])
        curated[(parent, tgt["chembl_id"] if tgt else f"tid:{row['tid']}")].append(dict(row))
    common.log(f"  curated mechanisms: {sum(len(v) for v in curated.values())} assigned, "
               f"{len(curated_unassigned)} with no target")

    # ------------------------------------------------------------- activities
    common.log("  scanning activities (this is the long query)...")
    exclusion_counter = collections.Counter()
    measurements = []
    q = """
    SELECT act.activity_id, act.molregno, act.standard_type, act.standard_relation,
           act.standard_value, act.standard_units, act.data_validity_comment,
           act.potential_duplicate, act.activity_comment, act.pchembl_value, act.src_id,
           a.assay_id, a.chembl_id AS assay_chembl_id, a.description AS assay_description,
           a.assay_type, a.confidence_score, a.relationship_type, a.variant_id, a.tid,
           bao.label AS bao_label,
           d.chembl_id AS doc_chembl_id, d.pubmed_id, d.doi, d.patent_id, d.doc_type,
           d.year AS doc_year, d.journal AS doc_journal, d.title AS doc_title
      FROM activities act
      JOIN cand c ON c.molregno = act.molregno
      JOIN assays a ON a.assay_id = act.assay_id
      LEFT JOIN bioassay_ontology bao ON bao.bao_id = a.bao_format
      LEFT JOIN docs d ON d.doc_id = act.doc_id
    """
    n_scanned = 0
    for row in conn.execute(q):
        n_scanned += 1
        parent = member_to_parent[row["molregno"]]
        st, rel, val, units = (row["standard_type"], row["standard_relation"],
                               row["standard_value"], row["standard_units"])

        if row["assay_chembl_id"] in excluded_assays:
            exclusion_counter["documented_exclusion"] += 1
            continue
        if row["assay_type"] not in ("B", "F"):
            exclusion_counter["assay_type_not_B_or_F"] += 1
            continue
        if st not in ENDPOINT_TYPES:
            exclusion_counter["standard_type_out_of_scope"] += 1
            continue
        if row["assay_type"] == "F" and row["bao_label"] == "organism-based format":
            exclusion_counter["organism_based_format"] += 1
            continue

        role = "binding" if row["assay_type"] == "B" else "functional"
        if rel == "=" and units == "nM" and val is not None and val > 0:
            status = "included_exact"
        elif rel in CENSORED_RELATIONS:
            status = "retained_as_bound"
            exclusion_counter["censored_bound"] += 1
        elif val is None:
            status = "excluded_null_value"
            exclusion_counter["null_value"] += 1
        elif units != "nM":
            status = "excluded_units"
            exclusion_counter["units_not_nM"] += 1
        elif val <= 0:
            status = "excluded_nonpositive"
            exclusion_counter["nonpositive_value"] += 1
        else:
            status = "excluded_other_relation"
            exclusion_counter["other_relation"] += 1

        tgt = targets.get(row["tid"]) or {}
        spec = specificity(tgt.get("target_type"), tgt.get("tax_id"),
                           row["confidence_score"], row["relationship_type"],
                           row["variant_id"])
        skey, pclass = study_key(row["pubmed_id"], row["doi"], row["patent_id"],
                                 row["doc_chembl_id"], row["doc_type"])
        measurements.append({
            "activity_id": row["activity_id"],
            "parent_molregno": parent,
            "measured_molregno": row["molregno"],
            "target_chembl_id": tgt.get("chembl_id") or f"tid:{row['tid']}",
            "tid": row["tid"],
            "role": role,
            "endpoint_class": f"{role}:{st}",
            "standard_type": st,
            "standard_relation": rel,
            "standard_value_nM": val if units == "nM" else None,
            "standard_value_raw": val,
            "standard_units": units,
            "status": status,
            "specificity": spec,
            "confidence_score": row["confidence_score"],
            "relationship_type": row["relationship_type"],
            "target_type": tgt.get("target_type"),
            "target_organism": tgt.get("organism"),
            "target_tax_id": tgt.get("tax_id"),
            "variant_id": row["variant_id"],
            "assay_chembl_id": row["assay_chembl_id"],
            "assay_description": row["assay_description"],
            "data_validity_comment": row["data_validity_comment"],
            "potential_duplicate": row["potential_duplicate"],
            "activity_comment": row["activity_comment"],
            "src_id": row["src_id"],
            "study_key": skey,
            "provenance_class": pclass,
            "doc_chembl_id": row["doc_chembl_id"],
            "pubmed_id": row["pubmed_id"],
            "doi": row["doi"],
            "patent_id": row["patent_id"],
            "doc_type": row["doc_type"],
            "doc_year": row["doc_year"],
            "doc_journal": row["doc_journal"],
        })
    common.log(f"  scanned {n_scanned} activity rows, kept {len(measurements)} in-scope "
               f"({sum(1 for m in measurements if m['status'] == 'included_exact')} exact)")

    # --------------------------------------------------------------- claims
    exp = collections.defaultdict(list)          # (parent, target, role) -> measurements
    for m in measurements:
        exp[(m["parent_molregno"], m["target_chembl_id"], m["role"])].append(m)

    claim_rows, study_rows, thresh_rows = [], [], []
    THRESHOLDS = [(u, u * 1000.0) for u in rules["thresholds"]["micromolar"]]

    def target_fields(target_chembl_id, tid):
        tgt = targets.get(tid) or {}
        fams = sorted(fam_of_tid.get(tid, ()))
        return {
            "target_chembl_id": target_chembl_id,
            "target_pref_name": tgt.get("pref_name"),
            "target_type": tgt.get("target_type"),
            "target_organism": tgt.get("organism"),
            "target_tax_id": tgt.get("tax_id"),
            "target_accessions": tgt.get("accessions"),
            "target_family_l1": ";".join(sorted({f[0] for f in fams if f[0]})),
            "target_family_l2": ";".join(sorted({f[1] for f in fams if f[1]})),
        }

    # --- curated claims
    for (parent, target_chembl_id), mechs in sorted(curated.items()):
        tid = mechs[0]["tid"]
        actions = sorted({m["action_type"] for m in mechs if m["action_type"]})
        parents_types = {m["parent_type"] for m in mechs if m["parent_type"]}
        traceable = [m for m in mechs
                     if mech_refs.get(m["mec_id"]) or m["mechanism_comment"]]
        indirect = all(m["direct_interaction"] == 0 for m in mechs
                       if m["direct_interaction"] is not None) and any(
                           m["direct_interaction"] is not None for m in mechs)
        refs = [r for m in mechs for r in mech_refs.get(m["mec_id"], [])]

        curated_support = bool(traceable) and not indirect
        reasons = []
        if not traceable:
            reasons.append("curated_untraceable")
        if indirect:
            reasons.append("curated_indirect")

        tgt = targets.get(tid) or {}
        tt = tgt.get("target_type")
        claim_specificity = ("family_or_complex_level"
                             if tt in ("PROTEIN FAMILY", "PROTEIN COMPLEX",
                                       "PROTEIN COMPLEX GROUP", "SELECTIVITY GROUP")
                             else "single_protein" if tt == "SINGLE PROTEIN" else "other")

        conflict = int(POSITIVE in parents_types and NEGATIVE in parents_types)
        row = {
            "parent_molregno": parent,
            "parent_chembl_id": parent_name.get(parent, ("", "", ""))[0],
            "pref_name": parent_name.get(parent, ("", "", ""))[1],
            "claim_role": "curated",
            **target_fields(target_chembl_id, tid),
            "curated_actions": ";".join(actions),
            "curated_action_parent_types": ";".join(sorted(parents_types)),
            "n_mechanism_records": len(mechs),
            "n_mechanism_refs": len(refs),
            "mechanism_ref_types": ";".join(sorted({r["ref_type"] for r in refs})),
            "mechanism_of_action": mechs[0]["mechanism_of_action"],
            "direct_interaction": mechs[0]["direct_interaction"],
            "claim_target_specificity": claim_specificity,
            "assignment_specificity": ("human_curated"
                                       if tgt.get("tax_id") == 9606 else "nonhuman_or_unknown_curated"),
            "endpoint_classes": "",
            "n_exact_measurements": 0,
            "n_censored_measurements": 0,
            "n_studies_publication": 0,
            "n_studies_total": 0,
            "curated_support": int(curated_support),
            "multiple_study_support": 0,
            "tier": "supported" if curated_support else "limited_or_unresolved",
            "tier_reasons": ";".join(reasons) if reasons else "curated_traceable",
            "n_exact_human_direct": 0,
            "n_studies_publication_human_direct": 0,
            "multiple_study_support_human_direct": 0,
            "tier_human_direct": ("supported" if curated_support and tgt.get("tax_id") == 9606
                                  and tt == "SINGLE PROTEIN" else "not_applicable"),
            "tier_reasons_human_direct": (
                "curated_traceable_human_single_protein"
                if curated_support and tgt.get("tax_id") == 9606 and tt == "SINGLE PROTEIN"
                else "curated_claim_not_a_direct_human_single_protein_measurement"),
            "curated_mechanism_at_same_target": 1,
            "conflict_action": conflict,
            # Two curated actions at one target that do NOT disagree in
            # direction (AGONIST vs PARTIAL AGONIST, MODULATOR vs INHIBITOR).
            # Counted separately so a refinement is never reported as a
            # contradiction, and neither one raises the tier.
            "conflict_action_variant": int(len(actions) > 1 and not conflict),
            "conflict_dispersion": 0,
            "conflict_detail": ("curated actions disagree in direction: " + ";".join(actions)
                                if conflict else
                                "curated actions differ at one target: " + ";".join(actions)
                                if len(actions) > 1 else ""),
            "example_source_records": ";".join(
                sorted({f"mec_id:{m['mec_id']}" for m in mechs})[:5]),
        }
        claim_rows.append(row)
        for r in refs:
            study_rows.append({
                "parent_molregno": parent, "target_chembl_id": target_chembl_id,
                "claim_role": "curated", "endpoint_class": "",
                "study_key": f"{r['ref_type']}:{r['ref_id']}",
                "provenance_class": "curated_reference",
                "counts_toward_multi_study": 0,
                "n_measurements_in_study": 0,
                "doc_chembl_id": "", "pubmed_id": "", "doi": "",
                "ref_type": r["ref_type"], "ref_url": r["ref_url"],
            })

    for parent, m in curated_unassigned:
        claim_rows.append({
            "parent_molregno": parent,
            "parent_chembl_id": parent_name.get(parent, ("", "", ""))[0],
            "pref_name": parent_name.get(parent, ("", "", ""))[1],
            "claim_role": "curated",
            "target_chembl_id": "", "target_pref_name": "", "target_type": "",
            "target_organism": "", "target_tax_id": "", "target_accessions": "",
            "target_family_l1": "", "target_family_l2": "",
            "curated_actions": m["action_type"] or "",
            "curated_action_parent_types": "", "n_mechanism_records": 1,
            "n_mechanism_refs": len(mech_refs.get(m["mec_id"], [])),
            "mechanism_ref_types": "",
            "mechanism_of_action": m["mechanism_of_action"],
            "direct_interaction": m["direct_interaction"],
            "claim_target_specificity": "no_target_assigned",
            "assignment_specificity": "no_target_assigned",
            "endpoint_classes": "", "n_exact_measurements": 0,
            "n_censored_measurements": 0, "n_studies_publication": 0,
            "n_studies_total": 0, "curated_support": 0, "multiple_study_support": 0,
            "tier": "limited_or_unresolved",
            "tier_reasons": "curated_no_target_assigned",
            "conflict_action_variant": 0,
            "n_exact_human_direct": 0, "n_studies_publication_human_direct": 0,
            "multiple_study_support_human_direct": 0,
            "tier_human_direct": "not_applicable",
            "tier_reasons_human_direct": "curated_no_target_assigned",
            "curated_mechanism_at_same_target": 0,
            "conflict_action": 0, "conflict_dispersion": 0, "conflict_detail": "",
            "example_source_records": f"mec_id:{m['mec_id']}",
        })

    # --- experimental claims
    for (parent, target_chembl_id, role), rows in sorted(
            exp.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2])):
        tid = rows[0]["tid"]
        exact = [r for r in rows if r["status"] == "included_exact"]
        censored = [r for r in rows if r["status"] == "retained_as_bound"]

        by_class = collections.defaultdict(list)
        for r in exact:
            by_class[r["endpoint_class"]].append(r)

        pub_studies_per_class = {}
        all_studies = set()
        for cls, rs in by_class.items():
            pub = {r["study_key"] for r in rs
                   if r["provenance_class"] == "publication" and r["study_key"]}
            pub_studies_per_class[cls] = pub
            all_studies |= {r["study_key"] for r in rs if r["study_key"]}

        multi = any(len(p) >= 2 for p in pub_studies_per_class.values())
        n_pub = len({s for p in pub_studies_per_class.values() for s in p})

        specs = collections.Counter(r["specificity"] for r in exact)
        dominant = specs.most_common(1)[0][0] if specs else (
            collections.Counter(r["specificity"] for r in rows).most_common(1)[0][0])
        human_exact = [r for r in exact
                       if r["specificity"] == "human_direct_single_protein"]
        has_human_direct = bool(human_exact)

        def assess(ex, censored_rows, all_rows):
            """Tier one claim from a chosen measurement subset.

            Returns (tier, reasons, n_publication_studies, multi_flag). Called
            twice: once over every assessed measurement, and once over the
            direct-human-single-protein subset alone, which is what the report's
            main empirical comparison uses. A homologous or nonhuman study can
            therefore never contribute replication to the human comparison.
            """
            classes_ = collections.defaultdict(list)
            for r in ex:
                classes_[r["endpoint_class"]].append(r)
            pubs = {cls: {r["study_key"] for r in rs
                          if r["provenance_class"] == "publication" and r["study_key"]}
                    for cls, rs in classes_.items()}
            studies = {r["study_key"] for r in ex if r["study_key"]}
            n_pub_ = len({s for p in pubs.values() for s in p})
            multi_ = any(len(p) >= 2 for p in pubs.values())

            if not ex and censored_rows:
                return "limited_or_unresolved", ["censored_only"], n_pub_, multi_
            if not ex and all_rows:
                statuses = sorted({r["status"] for r in all_rows})
                if "excluded_units" in statuses:
                    why = "invalid_units_only"
                elif statuses == ["excluded_null_value"]:
                    why = "null_value_only"
                else:
                    why = "no_qualifying_exact_measurement"
                return "limited_or_unresolved", [why], n_pub_, multi_
            if not ex:
                return ("limited_or_unresolved", ["no_measurement_in_this_subset"],
                        n_pub_, multi_)
            if multi_:
                return "supported", ["multiple_study_support"], n_pub_, multi_
            if studies:
                if n_pub_ == 1:
                    why = ["one_publication"]
                elif n_pub_ >= 2:
                    why = ["multiple_publications_split_across_endpoint_classes"]
                else:
                    pc = {r["provenance_class"] for r in ex}
                    if pc == {"deposited_dataset"}:
                        why = ["deposited_datasets_only" if len(studies) > 1
                               else "one_deposit"]
                    elif pc == {"patent"}:
                        why = ["patents_only" if len(studies) > 1 else "one_patent"]
                    else:
                        why = ["mixed_non_publication_provenance"]
                return "preliminary", why, n_pub_, multi_
            return "limited_or_unresolved", ["unresolved_study_provenance"], n_pub_, multi_

        tier, reasons, n_pub, multi = assess(exact, censored, rows)
        h_tier, h_reasons, h_pub, h_multi = (
            assess(human_exact, [], []) if has_human_direct
            else ("not_applicable", ["no_direct_human_single_protein_measurement"], 0, False))

        if not has_human_direct and dominant in (
                "homologous_or_unknown_species", "non_protein_or_unassigned",
                "nonhuman") and tier in ("supported", "preliminary"):
            reasons.append("ambiguous_target_assignment")

        disp, disp_detail = 0, ""
        for cls, rs in by_class.items():
            vals = [r["standard_value_nM"] for r in rs]
            studies = {r["study_key"] for r in rs}
            if len(vals) >= 2 and len(studies) >= 2 and min(vals) > 0 and \
                    math.log10(max(vals) / min(vals)) > 2:
                disp = 1
                disp_detail = (f"{cls}: {min(vals):.4g}-{max(vals):.4g} nM across "
                               f"{len(studies)} studies")
                break

        claim_rows.append({
            "parent_molregno": parent,
            "parent_chembl_id": parent_name.get(parent, ("", "", ""))[0],
            "pref_name": parent_name.get(parent, ("", "", ""))[1],
            "claim_role": role,
            **target_fields(target_chembl_id, tid),
            "curated_actions": "", "curated_action_parent_types": "",
            "n_mechanism_records": 0, "n_mechanism_refs": 0, "mechanism_ref_types": "",
            "mechanism_of_action": "", "direct_interaction": "",
            "claim_target_specificity": dominant,
            "assignment_specificity": ("human_direct_single_protein" if has_human_direct
                                       else dominant),
            "endpoint_classes": ";".join(sorted(by_class)),
            "n_exact_measurements": len(exact),
            "n_censored_measurements": len(censored),
            "n_studies_publication": n_pub,
            "n_studies_total": len(all_studies),
            "curated_support": 0,
            "multiple_study_support": int(multi),
            "tier": tier,
            "tier_reasons": ";".join(reasons),
            "n_exact_human_direct": len(human_exact),
            "n_studies_publication_human_direct": h_pub,
            "multiple_study_support_human_direct": int(h_multi),
            "tier_human_direct": h_tier,
            "tier_reasons_human_direct": ";".join(h_reasons),
            "curated_mechanism_at_same_target": int(
                (parent, target_chembl_id) in curated),
            "conflict_action": 0,
            "conflict_action_variant": 0,
            "conflict_dispersion": disp,
            "conflict_detail": disp_detail,
            "example_source_records": ";".join(
                sorted({r["assay_chembl_id"] for r in exact or rows})[:5]),
        })

        per_study = collections.defaultdict(list)
        for r in exact:
            per_study[(r["study_key"], r["endpoint_class"])].append(r)
        for (skey, cls), rs in sorted(per_study.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
            study_rows.append({
                "parent_molregno": parent, "target_chembl_id": target_chembl_id,
                "claim_role": role, "endpoint_class": cls,
                "study_key": skey,
                "provenance_class": rs[0]["provenance_class"],
                "counts_toward_multi_study": int(rs[0]["provenance_class"] == "publication"),
                "n_measurements_in_study": len(rs),
                "doc_chembl_id": rs[0]["doc_chembl_id"],
                "pubmed_id": rs[0]["pubmed_id"], "doi": rs[0]["doi"],
                "ref_type": "", "ref_url": "",
            })

        for cls, rs in sorted(by_class.items()):
            vals = [r["standard_value_nM"] for r in rs]
            med = log_median(vals)
            trow = {
                "parent_molregno": parent,
                "parent_chembl_id": parent_name.get(parent, ("", "", ""))[0],
                "target_chembl_id": target_chembl_id,
                "claim_role": role, "endpoint_class": cls,
                "n_exact": len(vals), "n_studies": len({r["study_key"] for r in rs}),
                "median_nM_log_pooled": round(med, 4),
                "min_nM": min(vals), "max_nM": max(vals),
                "specificity": collections.Counter(
                    r["specificity"] for r in rs).most_common(1)[0][0],
                "human_direct_single_protein": int(any(
                    r["specificity"] == "human_direct_single_protein" for r in rs)),
            }
            for um, nm in THRESHOLDS:
                trow[f"median_pass_{um}uM"] = int(med <= nm)
                trow[f"any_pass_{um}uM"] = int(min(vals) <= nm)
            thresh_rows.append(trow)

    common.log(f"  {len(claim_rows)} claims, {len(study_rows)} claim-study links")

    # ---------------------------------------------------- molecule-target pairs
    # The two Supported routes land on different claim rows by construction:
    # curated support is a property of a curated claim, multi-study support of
    # an experimental one. Their intersection is therefore a molecule-target
    # fact, and is rolled up here rather than being silently reported as zero.
    pairs = collections.defaultdict(list)
    for c in claim_rows:
        if c["target_chembl_id"]:
            pairs[(c["parent_molregno"], c["target_chembl_id"])].append(c)

    pair_rows = []
    for (parent, tgt_id), cs in sorted(pairs.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        cur = any(c["curated_support"] for c in cs)
        ms = any(c["multiple_study_support"] for c in cs)
        ms_h = any(c["multiple_study_support_human_direct"] for c in cs)
        pair_rows.append({
            "parent_molregno": parent,
            "parent_chembl_id": cs[0]["parent_chembl_id"],
            "pref_name": cs[0]["pref_name"],
            "target_chembl_id": tgt_id,
            "target_pref_name": cs[0]["target_pref_name"],
            "target_type": cs[0]["target_type"],
            "target_organism": cs[0]["target_organism"],
            "target_family_l1": cs[0]["target_family_l1"],
            "target_family_l2": cs[0]["target_family_l2"],
            "n_claims": len(cs),
            "claim_roles": ";".join(sorted({c["claim_role"] for c in cs})),
            "curated_support": int(cur),
            "multiple_study_support": int(ms),
            "multiple_study_support_human_direct": int(ms_h),
            "support_routes": ("both" if cur and ms else "curated_only" if cur
                               else "multiple_study_only" if ms else "neither"),
            "best_tier": ("supported" if any(c["tier"] == "supported" for c in cs)
                          else "preliminary" if any(c["tier"] == "preliminary" for c in cs)
                          else "limited_or_unresolved"),
            "best_tier_human_direct": (
                "supported" if any(c["tier_human_direct"] == "supported" for c in cs)
                else "preliminary" if any(c["tier_human_direct"] == "preliminary" for c in cs)
                else "limited_or_unresolved" if any(
                    c["tier_human_direct"] == "limited_or_unresolved" for c in cs)
                else "not_applicable"),
            "curated_actions": ";".join(sorted({c["curated_actions"] for c in cs
                                                if c["curated_actions"]})),
            "n_exact_measurements": sum(c["n_exact_measurements"] for c in cs),
            "n_exact_human_direct": sum(c["n_exact_human_direct"] for c in cs),
            "conflict_action": max(c["conflict_action"] for c in cs),
            "conflict_action_variant": max(c["conflict_action_variant"] for c in cs),
            "conflict_dispersion": max(c["conflict_dispersion"] for c in cs),
        })
    common.write_csv("target_pairs.csv", list(pair_rows[0].keys()), pair_rows,
                     compress=True)

    pairs_by_parent = collections.defaultdict(list)
    for p in pair_rows:
        pairs_by_parent[p["parent_molregno"]].append(p)

    # ------------------------------------------------------------- molecules
    by_parent = collections.defaultdict(list)
    for c in claim_rows:
        by_parent[c["parent_molregno"]].append(c)

    mol_rows, gap_rows = [], []
    for r in cand_rows:
        p = int(r["parent_molregno"])
        claims = by_parent.get(p, [])
        counts = collections.Counter(c["tier"] for c in claims)
        human = [c for c in claims
                 if c["assignment_specificity"] in ("human_direct_single_protein",
                                                    "human_curated")]
        human_qual = [c for c in claims
                      if c["tier_human_direct"] in ("supported", "preliminary")]
        prs = pairs_by_parent.get(p, [])
        mol_rows.append({
            "parent_molregno": p,
            "parent_chembl_id": r["parent_chembl_id"],
            "pref_name": r["pref_name"],
            "molecule_type": r["molecule_type"],
            "route_combination": r["route_combination"],
            "cns_ind_max_phase_label": r["cns_ind_max_phase_label"],
            "family_max_phase_label": r["family_max_phase_label"],
            "n_claims": len(claims),
            "n_supported": counts["supported"],
            "n_preliminary": counts["preliminary"],
            "n_limited_or_unresolved": counts["limited_or_unresolved"],
            "n_curated_support": sum(c["curated_support"] for c in claims),
            "n_multiple_study_support": sum(c["multiple_study_support"] for c in claims),
            "n_pairs": len(prs),
            "n_pairs_curated_support": sum(p_["curated_support"] for p_ in prs),
            "n_pairs_multiple_study_support": sum(p_["multiple_study_support"] for p_ in prs),
            "n_pairs_both_routes": sum(1 for p_ in prs if p_["support_routes"] == "both"),
            "n_distinct_targets": len({c["target_chembl_id"] for c in claims
                                       if c["target_chembl_id"]}),
            "n_human_direct_claims": len(human),
            "n_supported_human_direct": sum(
                1 for c in claims if c["tier_human_direct"] == "supported"),
            "n_preliminary_human_direct": sum(
                1 for c in claims if c["tier_human_direct"] == "preliminary"),
            "any_qualifying_human_target_claim": int(bool(human_qual)),
            "n_conflict_action": sum(c["conflict_action"] for c in claims),
            "n_conflict_dispersion": sum(c["conflict_dispersion"] for c in claims),
            "evidence_status": ("assessed_with_evidence" if claims
                                else "no_eligible_evidence_found"),
        })
        if not claims:
            gap_rows.append({
                "parent_molregno": p,
                "parent_chembl_id": r["parent_chembl_id"],
                "pref_name": r["pref_name"],
                "molecule_type": r["molecule_type"],
                "structure_type": r["structure_type"],
                "route_combination": r["route_combination"],
                "cns_ind_max_phase_label": r["cns_ind_max_phase_label"],
                "gap_kind": "no_eligible_evidence_found_in_chembl_37",
                "detail": ("Retained in the catalogue. ChEMBL 37 holds no curated "
                           "mechanism and no assessable activity for any member of "
                           "this compound family. Not assessed against PDSP, "
                           "BindingDB, DGIdb, GtoPdb or the literature."),
            })

    # ---------------------------------------------------------------- outputs
    claim_fields = list(claim_rows[0].keys())
    common.write_csv("assessed_claims.csv", claim_fields, claim_rows, compress=True)
    common.write_csv("claim_studies.csv", list(study_rows[0].keys()), study_rows,
                     compress=True)
    common.write_csv("claim_thresholds.csv", list(thresh_rows[0].keys()), thresh_rows,
                     compress=True)
    common.write_csv("molecule_evidence.csv", list(mol_rows[0].keys()), mol_rows)
    common.write_csv("coverage_gaps.csv",
                     list(gap_rows[0].keys()) if gap_rows else ["parent_molregno"], gap_rows)

    excl_rows = [{"exclusion_reason": k, "n_activity_rows": v,
                  "retained_in_output": int(exclusion_retained_in_measurements(k))}
                 for k, v in sorted(exclusion_counter.items(), key=lambda kv: -kv[1])]
    common.write_csv("evidence_exclusions.csv", list(excl_rows[0].keys()), excl_rows)

    obs = {}
    for c in claim_rows:
        t = c["target_chembl_id"]
        if not t:
            continue
        o = obs.setdefault(t, {
            "target_chembl_id": t, "target_pref_name": c["target_pref_name"],
            "target_type": c["target_type"], "target_organism": c["target_organism"],
            "target_accessions": c["target_accessions"],
            "target_family_l1": c["target_family_l1"],
            "target_family_l2": c["target_family_l2"],
            "n_claims": 0, "n_molecules": set(), "n_supported": 0,
            "n_curated": 0, "n_human_direct": 0})
        o["n_claims"] += 1
        o["n_molecules"].add(c["parent_molregno"])
        o["n_supported"] += int(c["tier"] == "supported")
        o["n_curated"] += int(c["claim_role"] == "curated")
        o["n_human_direct"] += int(c["assignment_specificity"] == "human_direct_single_protein")
    obs_rows = []
    for o in obs.values():
        o["n_molecules"] = len(o["n_molecules"])
        obs_rows.append(o)
    obs_rows.sort(key=lambda r: (-r["n_molecules"], r["target_chembl_id"]))
    common.write_csv("observed_targets.csv", list(obs_rows[0].keys()), obs_rows)

    common.write_csv("measurements.csv", list(measurements[0].keys()), measurements,
                     compress=True)

    common.record_source("chembl_37", **{
        "name": "ChEMBL 37 bulk release (SQLite)",
        "publisher": "EMBL-EBI",
        "url": "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/",
        "local_path": str(common.CHEMBL_DB),
        "access_status": "ok",
        "access_mode": "read-only (SQLite URI mode=ro; no write can reach the release file)",
        "license": "CC BY-SA 3.0 (ChEMBL data); see https://chembl.gitbook.io/chembl-interface-documentation/about",
        "size_bytes": common.CHEMBL_DB.stat().st_size,
        "checksum_note": "Full-file sha256 not computed: the release is 30.5 GB. "
                         "Pinned by release name, path and byte size instead.",
        "tables_read": ["molecule_dictionary", "molecule_hierarchy",
                        "molecule_atc_classification", "atc_classification",
                        "drug_indication", "drug_mechanism", "mechanism_refs",
                        "activities", "assays", "target_dictionary",
                        "target_components", "component_sequences", "component_class",
                        "protein_classification", "docs", "bioassay_ontology",
                        "action_type"],
    })

    common.write_json("step3_summary.json", {
        "chembl_release": common.CHEMBL_RELEASE,
        "tier_rules_version": rules["version"],
        "candidate_parents": len(parent_name),
        "candidate_family_members": len(member_to_parent),
        "activity_rows_scanned": n_scanned,
        "measurement_rows_in_scope": len(measurements),
        "exact_measurements": sum(1 for m in measurements
                                  if m["status"] == "included_exact"),
        "censored_measurements": sum(1 for m in measurements
                                     if m["status"] == "retained_as_bound"),
        "claims": len(claim_rows),
        "claims_by_tier": dict(collections.Counter(c["tier"] for c in claim_rows)),
        "claims_by_role": dict(collections.Counter(c["claim_role"] for c in claim_rows)),
        "molecules_with_no_eligible_evidence": len(gap_rows),
        "distinct_targets_observed": len(obs_rows),
        "target_family_source": family_source,
        "exclusions": dict(exclusion_counter),
    })
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
