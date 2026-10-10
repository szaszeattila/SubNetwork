"""Step 2 - build the cohort-1 clinical catalogue from ChEMBL 37.

Two admission routes, kept separate throughout:

  ATC-N route         a molecule (or any member of its ChEMBL compound
                      family) carries an ATC level-5 code whose level1 is 'N'.
  CNS-indication route a ``drug_indication`` record for the molecule (or a
                      family member) names a MeSH descriptor inside the
                      versioned CNS scope from ``config/cns_indication_scope.json``.

Neither route is evidence of anything. ATC N is a classification, not a
verified claim of central action; an indication record is a development or
approval annotation, not a target relationship. Membership is decided here
and evidence is assessed afterwards, on the fixed candidate set, so evidence
availability never decides who is in the catalogue.

Identity is normalised to the ChEMBL *parent* molregno
(``molecule_hierarchy.parent_molregno``, falling back to the molecule itself),
which collapses salts and hydrates onto one chemical identity while every
contributing family member is retained in ``family_members.csv``. Nothing is
matched on a name.

Writes: candidates.csv, candidate_atc_codes.csv, candidate_indications.csv,
family_members.csv, indication_scope.csv, route_arithmetic.csv,
seed_membership.csv.
"""

import collections
import sys

import common

# ---------------------------------------------------------------------------
# MeSH scope
# ---------------------------------------------------------------------------

def load_mesh_tree() -> tuple[dict[str, set[str]], dict[str, str]]:
    path = common.CACHE / "mesh_tree.tsv"
    if not path.exists():
        raise SystemExit(f"{path} missing - run step1_fetch_mesh.py first")
    tree: dict[str, set[str]] = collections.defaultdict(set)
    label: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            d, tn, lb = line.rstrip("\n").split("\t")
            tree[d].add(tn)
            label.setdefault(d, lb)
    return tree, label


def in_class(tree_numbers: set[str], class_trees: list[str]) -> set[str]:
    """Tree numbers of this descriptor that fall inside the given class."""
    hits = set()
    for tn in tree_numbers:
        for ct in class_trees:
            if tn == ct or tn.startswith(ct + "."):
                hits.add(tn)
    return hits


def classify_scope(scope: dict, tree: dict[str, set[str]]) -> dict[str, dict]:
    """Classify every MeSH descriptor against the core scope and each boundary class.

    Returns descriptor_id -> {"core": bool, "classes": [...], "core_trees": [...],
    "boundary_trees": {...}}. The exclusion rule is the one written down in the
    config: a descriptor leaves core only when *every* one of its tree numbers
    under a core root also sits in an excluded boundary class.
    """
    core_roots = [r["tree"] for r in scope["core_roots"]]
    excluded = [b for b in scope["boundary_classes"]
                if not b.get("in_core") and not b.get("outside_core_roots")]
    additive = [b for b in scope["boundary_classes"] if b.get("outside_core_roots")]

    out = {}
    for d, tns in tree.items():
        under_core_roots = in_class(tns, core_roots)
        boundary_hits = {}
        for b in scope["boundary_classes"]:
            hit = in_class(tns, b["trees"])
            if hit:
                boundary_hits[b["id"]] = sorted(hit)

        if under_core_roots:
            excluded_trees = set()
            for b in excluded:
                excluded_trees |= in_class(under_core_roots, b["trees"])
            core = bool(under_core_roots - excluded_trees)
            core_trees = sorted(under_core_roots - excluded_trees)
        else:
            core = False
            core_trees = []

        classes = []
        if core:
            classes.append("core")
        for b in scope["boundary_classes"]:
            if b["id"] in boundary_hits:
                classes.append(b["id"])
        if not classes:
            continue
        out[d] = {
            "core": core,
            "classes": classes,
            "core_trees": core_trees,
            "boundary_trees": boundary_hits,
            "additive_only": bool(boundary_hits) and not core
                             and all(b["id"] in boundary_hits for b in additive
                                     if b["id"] in boundary_hits),
        }
    return out


def variant_members(scope: dict, classified: dict) -> dict[str, set[str]]:
    """Descriptor sets for each cumulative scope variant."""
    variants = {}
    for v in scope["cumulative_variants"]:
        wanted = set(v["adds"])
        members = {d for d, info in classified.items()
                   if info["core"] or (wanted & set(info["classes"]))}
        variants[v["id"]] = members
    return variants


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def parents_for(conn, molregnos: set[int]) -> dict[int, int]:
    """molregno -> parent molregno, falling back to the molecule itself."""
    out = {m: m for m in molregnos}
    if not molregnos:
        return out
    ids = list(molregnos)
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = ("SELECT molregno, parent_molregno FROM molecule_hierarchy "
             f"WHERE molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            if row["parent_molregno"] is not None:
                out[row["molregno"]] = row["parent_molregno"]
    return out


def families_for(conn, parents: set[int]) -> dict[int, set[int]]:
    """parent molregno -> every molregno in its compound family (parent included)."""
    fam = {p: {p} for p in parents}
    ids = list(parents)
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = ("SELECT molregno, parent_molregno FROM molecule_hierarchy "
             f"WHERE parent_molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            fam[row["parent_molregno"]].add(row["molregno"])
    return fam


def molecule_records(conn, molregnos: set[int]) -> dict[int, dict]:
    cols = ("molregno, chembl_id, pref_name, molecule_type, structure_type, max_phase, "
            "first_approval, withdrawn_flag, therapeutic_flag, natural_product, prodrug, "
            "polymer_flag, inorganic_flag, oral, parenteral, topical, black_box_warning, "
            "chirality, chemical_probe, orphan, usan_stem, usan_stem_definition")
    out = {}
    ids = list(molregnos)
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = (f"SELECT {cols} FROM molecule_dictionary "
             f"WHERE molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            out[row["molregno"]] = dict(row)
    return out


PHASE_LABEL = {
    4.0: "Approved",
    3.0: "Phase 3",
    2.0: "Phase 2",
    1.0: "Phase 1",
    0.5: "Early Phase 1",
    -1.0: "Unknown (ChEMBL -1)",
}


def phase_label(v) -> str:
    if v is None:
        return "Missing (no phase recorded)"
    return PHASE_LABEL.get(float(v), f"Other ({v})")


def main() -> int:
    scope = common.load_config("cns_indication_scope.json")
    tree, mesh_label = load_mesh_tree()
    classified = classify_scope(scope, tree)
    variants = variant_members(scope, classified)
    core_set = variants["S0_core"]
    widest = variants["S5_widest"]

    conn = common.chembl()

    # -- route A: ATC N ----------------------------------------------------
    atc_rows = conn.execute("""
        SELECT mac.molregno, a.level5, a.level1, a.level2, a.level3, a.level4,
               a.who_name, a.level2_description, a.level3_description, a.level4_description
        FROM molecule_atc_classification mac
        JOIN atc_classification a ON a.level5 = mac.level5
        WHERE a.level1 = 'N'
        ORDER BY mac.molregno, a.level5
    """).fetchall()
    atc_molregnos = {r["molregno"] for r in atc_rows}
    common.log(f"  ATC N: {len(atc_rows)} classification rows on {len(atc_molregnos)} molecules")

    # -- route B: CNS indications -----------------------------------------
    ind_rows = conn.execute("""
        SELECT drugind_id, record_id, molregno, max_phase_for_ind,
               mesh_id, mesh_heading, efo_id, efo_term
        FROM drug_indication ORDER BY drugind_id
    """).fetchall()
    scoped_ind = [r for r in ind_rows if r["mesh_id"] in widest]
    core_ind = [r for r in ind_rows if r["mesh_id"] in core_set]
    ind_molregnos = {r["molregno"] for r in core_ind}
    common.log(f"  drug_indication: {len(ind_rows)} rows; {len(scoped_ind)} in the widest "
               f"considered scope; {len(core_ind)} in core, on {len(ind_molregnos)} molecules")

    # -- normalise identity to parents ------------------------------------
    all_mol = atc_molregnos | {r["molregno"] for r in scoped_ind}
    parent_of = parents_for(conn, all_mol)
    atc_parents = {parent_of[m] for m in atc_molregnos}
    ind_parents_core = {parent_of[r["molregno"]] for r in core_ind}

    variant_parents = {}
    for vid, members in variants.items():
        variant_parents[vid] = {parent_of[r["molregno"]] for r in scoped_ind
                                if r["mesh_id"] in members}

    catalogue = sorted(atc_parents | ind_parents_core)
    common.log(f"  ATC-N parents {len(atc_parents)}, core-indication parents "
               f"{len(ind_parents_core)}, union {len(catalogue)}")

    families = families_for(conn, set(catalogue))
    every_mol = set(catalogue) | {m for f in families.values() for m in f}
    records = molecule_records(conn, every_mol)

    # ATC codes reachable through the family, not only the molecule itself
    atc_by_mol = collections.defaultdict(list)
    for r in atc_rows:
        atc_by_mol[r["molregno"]].append(r)
    ind_by_mol = collections.defaultdict(list)
    for r in scoped_ind:
        ind_by_mol[r["molregno"]].append(r)

    # -- per-candidate rows ------------------------------------------------
    cand_rows, atc_out, ind_out, fam_out = [], [], [], []
    for p in catalogue:
        fam = sorted(families[p])
        prec = records.get(p, {})

        fam_atc = [(m, r) for m in fam for r in atc_by_mol.get(m, [])]
        fam_ind = [(m, r) for m in fam for r in ind_by_mol.get(m, [])]

        atc_l5 = sorted({r["level5"] for _, r in fam_atc})
        atc_l2 = sorted({r["level2"] for _, r in fam_atc})
        # The flagged boundary subtrees (N01B local anaesthetics, N02B other
        # analgesics) are ATC *level 3* codes: level2 is N01, level3 N01B,
        # level4 N01AB, level5 N01AB01.
        atc_l3 = sorted({r["level3"] for _, r in fam_atc})
        flagged = {f["code"]: f["flag"] for f in scope["atc"]["flagged_subtrees"]}
        atc_flags = sorted({flagged[c] for c in atc_l3 if c in flagged})

        core_hits = [(m, r) for m, r in fam_ind if r["mesh_id"] in core_set]
        core_phases = [r["max_phase_for_ind"] for _, r in core_hits
                       if r["max_phase_for_ind"] is not None]
        fam_phases = [records[m]["max_phase"] for m in fam
                      if records.get(m, {}).get("max_phase") is not None]

        in_atc = p in atc_parents
        in_ind = p in ind_parents_core

        cand_rows.append({
            "parent_molregno": p,
            "parent_chembl_id": prec.get("chembl_id"),
            "pref_name": prec.get("pref_name"),
            "molecule_type": prec.get("molecule_type") or "Missing",
            "structure_type": prec.get("structure_type") or "Missing",
            "route_atc_n": int(in_atc),
            "route_cns_indication": int(in_ind),
            "route_combination": ("both" if in_atc and in_ind
                                  else "atc_only" if in_atc else "indication_only"),
            "atc_level5_codes": ";".join(atc_l5),
            "atc_level2_codes": ";".join(atc_l2),
            "atc_level3_codes": ";".join(atc_l3),
            "atc_boundary_flags": ";".join(atc_flags),
            "n_family_members": len(fam),
            "family_chembl_ids": ";".join(
                records[m]["chembl_id"] for m in fam if m in records),
            "parent_max_phase": prec.get("max_phase"),
            "parent_max_phase_label": phase_label(prec.get("max_phase")),
            "family_max_phase": max(fam_phases) if fam_phases else None,
            "family_max_phase_label": phase_label(max(fam_phases) if fam_phases else None),
            "cns_ind_max_phase": max(core_phases) if core_phases else None,
            "cns_ind_max_phase_label": (phase_label(max(core_phases)) if core_phases
                                        else ("Missing (no phase on the qualifying indication)"
                                              if in_ind else "Not applicable (ATC route only)")),
            "n_core_cns_indications": len({r["drugind_id"] for _, r in core_hits}),
            "core_cns_mesh_ids": ";".join(sorted({r["mesh_id"] for _, r in core_hits})),
            "withdrawn_any_family": int(any(records[m].get("withdrawn_flag")
                                            for m in fam if m in records)),
            "first_approval": prec.get("first_approval"),
            "therapeutic_flag": prec.get("therapeutic_flag"),
            "natural_product": prec.get("natural_product"),
            "prodrug": prec.get("prodrug"),
            "polymer_flag": prec.get("polymer_flag"),
            "inorganic_flag": prec.get("inorganic_flag"),
            "black_box_warning": prec.get("black_box_warning"),
            "chirality": prec.get("chirality"),
            "orphan": prec.get("orphan"),
            "chemical_probe": prec.get("chemical_probe"),
            "usan_stem": prec.get("usan_stem"),
        })

        for m, r in fam_atc:
            atc_out.append({
                "parent_molregno": p,
                "parent_chembl_id": prec.get("chembl_id"),
                "carrier_molregno": m,
                "carrier_chembl_id": records.get(m, {}).get("chembl_id"),
                "carrier_is_parent": int(m == p),
                "atc_level5": r["level5"], "atc_level4": r["level4"],
                "atc_level3": r["level3"], "atc_level2": r["level2"],
                "atc_level1": r["level1"], "who_name": r["who_name"],
                "level2_description": r["level2_description"],
                "level3_description": r["level3_description"],
                "level4_description": r["level4_description"],
                "boundary_flag": flagged.get(r["level3"], ""),
            })

        for m, r in fam_ind:
            info = classified.get(r["mesh_id"], {})
            ind_out.append({
                "parent_molregno": p,
                "parent_chembl_id": prec.get("chembl_id"),
                "carrier_molregno": m,
                "carrier_chembl_id": records.get(m, {}).get("chembl_id"),
                "carrier_is_parent": int(m == p),
                "drugind_id": r["drugind_id"], "record_id": r["record_id"],
                "mesh_id": r["mesh_id"], "mesh_heading": r["mesh_heading"],
                "efo_id": r["efo_id"], "efo_term": r["efo_term"],
                "max_phase_for_ind": r["max_phase_for_ind"],
                "max_phase_for_ind_label": phase_label(r["max_phase_for_ind"]),
                "in_core_scope": int(bool(info.get("core"))),
                "scope_classes": ";".join(info.get("classes", [])),
                "core_tree_numbers": ";".join(info.get("core_trees", [])),
            })

        for m in fam:
            rec = records.get(m, {})
            fam_out.append({
                "parent_molregno": p,
                "parent_chembl_id": prec.get("chembl_id"),
                "member_molregno": m,
                "member_chembl_id": rec.get("chembl_id"),
                "member_pref_name": rec.get("pref_name"),
                "is_parent": int(m == p),
                "member_molecule_type": rec.get("molecule_type"),
                "member_structure_type": rec.get("structure_type"),
                "member_max_phase": rec.get("max_phase"),
                "member_withdrawn_flag": rec.get("withdrawn_flag"),
                "member_carries_atc_n": int(bool(atc_by_mol.get(m))),
                "member_carries_scoped_indication": int(bool(ind_by_mol.get(m))),
            })

    common.write_csv("candidates.csv", list(cand_rows[0].keys()), cand_rows)
    common.write_csv("candidate_atc_codes.csv", list(atc_out[0].keys()), atc_out)
    common.write_csv("candidate_indications.csv", list(ind_out[0].keys()), ind_out)
    common.write_csv("family_members.csv", list(fam_out[0].keys()), fam_out)

    # -- the indication scope itself, as a table ---------------------------
    ind_counts = collections.Counter(r["mesh_id"] for r in ind_rows)
    ind_mols = collections.defaultdict(set)
    for r in ind_rows:
        ind_mols[r["mesh_id"]].add(parent_of.get(r["molregno"], r["molregno"]))
    scope_rows = []
    for d in sorted(set(classified) | set(ind_counts)):
        info = classified.get(d)
        if not info and d not in ind_counts:
            continue
        used = ind_counts.get(d, 0)
        if not info and not used:
            continue
        scope_rows.append({
            "mesh_id": d,
            "mesh_label": mesh_label.get(d, ""),
            "tree_numbers": ";".join(sorted(tree.get(d, []))),
            "in_core_scope": int(bool(info and info["core"])),
            "scope_classes": ";".join(info["classes"]) if info else "",
            "core_tree_numbers": ";".join(info["core_trees"]) if info else "",
            "drug_indication_rows": used,
            "distinct_parent_molecules": len(ind_mols.get(d, ())),
        })
    common.write_csv("indication_scope.csv", list(scope_rows[0].keys()), scope_rows)

    # -- union arithmetic, before and after each rule ----------------------
    def sm(parents):
        return {p for p in parents
                if (records.get(p) or {}).get("molecule_type") == "Small molecule"}

    arith = []

    def add(stage, a, b, note):
        arith.append({
            "stage": stage,
            "atc_n_only": len(a - b), "cns_indication_only": len(b - a),
            "both_routes": len(a & b), "union": len(a | b),
            "atc_n_total": len(a), "cns_indication_total": len(b),
            "union_check_sum_minus_intersection": len(a) + len(b) - len(a & b),
            "arithmetic_holds": int(len(a | b) == len(a) + len(b) - len(a & b)),
            "note": note,
        })

    add("all_molecule_types", atc_parents, ind_parents_core,
        "Every candidate parent, any molecule_type. The catalogue as defined.")
    add("small_molecules_only", sm(atc_parents), sm(ind_parents_core),
        "Restricted to parents whose molecule_type is 'Small molecule' - the "
        "main comparison, and the same filter the 521 baseline used.")

    approved_fam = {p for p in catalogue
                    if any((records.get(m) or {}).get("max_phase") == 4
                           for m in families[p])}
    add("small_molecules_approved_family",
        sm(atc_parents) & approved_fam, sm(ind_parents_core) & approved_fam,
        "Small-molecule parents with any max_phase=4 record in the compound "
        "family. ChEMBL's 4 labels Approved; it is not proof of current "
        "jurisdiction-specific approval or of a completed Phase IV trial.")

    ind_by_phase = collections.defaultdict(set)
    for _, r in [(None, r) for r in core_ind]:
        if r["max_phase_for_ind"] is not None:
            ind_by_phase[float(r["max_phase_for_ind"])].add(parent_of[r["molregno"]])
    cum = set()
    for thr, name in [(4.0, "approved_only"), (3.0, "approved_plus_phase3"),
                      (2.0, "approved_plus_phase2_3"), (1.0, "approved_plus_phase1_2_3")]:
        cum |= ind_by_phase.get(thr, set())
        add(f"cns_indication_stage_{name}", set(), cum,
            f"Indication route only, cumulative on max_phase_for_ind >= {thr} "
            "for the qualifying CNS indication (not the molecule's max phase "
            "across unrelated conditions).")

    for v in scope["cumulative_variants"]:
        vp = variant_parents[v["id"]]
        add(f"scope_variant_{v['id']}", atc_parents, vp, v["label"])

    common.write_csv("route_arithmetic.csv", list(arith[0].keys()), arith)

    # -- the existing 28 ----------------------------------------------------
    seed_rows = []
    seed_ids = [cid for _, cid in common.SEED_MOLECULES]
    seed_recs = {}
    for i in range(0, len(seed_ids), 900):
        chunk = seed_ids[i:i + 900]
        q = ("SELECT molregno, chembl_id, pref_name, molecule_type, structure_type, "
             "max_phase FROM molecule_dictionary WHERE chembl_id IN "
             f"({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            seed_recs[row["chembl_id"]] = dict(row)

    seed_parents = parents_for(conn, {r["molregno"] for r in seed_recs.values()})
    seed_parent_ids = set(seed_parents.values())
    seed_parent_recs = molecule_records(conn, seed_parent_ids)
    seed_fams = families_for(conn, seed_parent_ids)
    seed_all = seed_parent_ids | {m for f in seed_fams.values() for m in f}
    seed_all_recs = molecule_records(conn, seed_all)

    seed_atc = collections.defaultdict(list)
    for r in atc_rows:
        seed_atc[r["molregno"]].append(r)
    seed_ind = collections.defaultdict(list)
    for r in ind_rows:
        seed_ind[r["molregno"]].append(r)

    catalogue_set = set(catalogue)
    for name, cid in common.SEED_MOLECULES:
        rec = seed_recs.get(cid, {})
        mol = rec.get("molregno")
        par = seed_parents.get(mol, mol)
        prec = seed_parent_recs.get(par, {})
        fam = sorted(seed_fams.get(par, {par}))
        fam_atc = sorted({r["level5"] for m in fam for r in seed_atc.get(m, [])})
        fam_scoped = [r for m in fam for r in seed_ind.get(m, [])
                      if r["mesh_id"] in widest]
        fam_core = [r for r in fam_scoped if r["mesh_id"] in core_set]
        in_cat = par in catalogue_set

        if in_cat:
            reason = []
            if par in atc_parents:
                reason.append(f"ATC N ({','.join(fam_atc)})")
            if par in ind_parents_core:
                reason.append(f"core CNS indication ({len({r['mesh_id'] for r in fam_core})} MeSH terms)")
            admission = "; ".join(reason)
        elif fam_scoped:
            classes = sorted({c for r in fam_scoped
                              for c in classified.get(r["mesh_id"], {}).get("classes", [])})
            admission = ("excluded: indications fall only in boundary classes "
                         + ",".join(classes))
        elif seed_ind.get(mol) or any(seed_ind.get(m) for m in fam):
            admission = ("excluded: has indication records, none inside the "
                         "considered CNS scope")
        else:
            admission = ("excluded: no ATC N classification and no "
                         "drug_indication record at all")

        seed_rows.append({
            "seed_name": name,
            "seed_chembl_id": cid,
            "seed_molregno": mol,
            "seed_molecule_type": rec.get("molecule_type"),
            "seed_structure_type": rec.get("structure_type"),
            "parent_molregno": par,
            "parent_chembl_id": prec.get("chembl_id"),
            "parent_pref_name": prec.get("pref_name"),
            "parent_molecule_type": prec.get("molecule_type"),
            "seed_is_parent": int(mol == par),
            "in_catalogue": int(in_cat),
            "route_atc_n": int(par in atc_parents),
            "route_cns_indication": int(par in ind_parents_core),
            "admission_or_exclusion_reason": admission,
            "atc_level5_codes": ";".join(fam_atc),
            "n_scoped_indication_rows": len(fam_scoped),
            "n_core_indication_rows": len(fam_core),
            "core_mesh_ids": ";".join(sorted({r["mesh_id"] for r in fam_core})),
            "boundary_mesh_ids": ";".join(sorted(
                {r["mesh_id"] for r in fam_scoped if r["mesh_id"] not in core_set})),
            "cns_ind_max_phase": max(
                [r["max_phase_for_ind"] for r in fam_core
                 if r["max_phase_for_ind"] is not None], default=None),
            "family_max_phase": max(
                [(seed_all_recs.get(m) or {}).get("max_phase") for m in fam
                 if (seed_all_recs.get(m) or {}).get("max_phase") is not None],
                default=None),
        })
    common.write_csv("seed_membership.csv", list(seed_rows[0].keys()), seed_rows)

    common.write_json("step2_summary.json", {
        "scope_version": scope["version"],
        "chembl_release": common.CHEMBL_RELEASE,
        "core_scope_descriptors": len(core_set),
        "core_scope_descriptors_used_in_chembl": len(
            {r["mesh_id"] for r in core_ind}),
        "atc_n_parents": len(atc_parents),
        "core_indication_parents": len(ind_parents_core),
        "catalogue_parents": len(catalogue),
        "catalogue_small_molecule_parents": len(sm(set(catalogue))),
        "seeds_in_catalogue": sum(r["in_catalogue"] for r in seed_rows),
    })

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
