"""Build the cohort-1 database from ChEMBL 37 and the versioned policies.

    python3 scripts/build_cohort.py            # stage, validate, activate
    python3 scripts/build_cohort.py --stage-only
    python3 scripts/build_cohort.py --activate  # activate an existing staged build

The build always writes a fresh staging file and only then replaces the
active one, backing it up first. A rerun therefore removes stale derived
claims rather than appending to them, and a failed run leaves the active
database exactly as it was.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import sys

from . import classes as classes_mod
from . import common, evidence, labels as labels_mod, scope as scope_mod, selection, store
from . import targets as targets_mod
from . import validate as validate_mod

EXCLUSION_NOTES = {
    "documented_exclusion": (
        "Known-bad upstream records (CHEMBL_ASSAY_LINK_EXCLUSIONS). Excluded on every "
        "ingestion path with the reason preserved; the individual rows are in "
        "excluded_records."),
    "organism_based_format": (
        "Whole-organism readouts. Excluded from active evidence, viewer context, graph, "
        "similarity and the broader-assignment layer (D11). Applied to every assay type, "
        "not only functional assays."),
    "assay_type_not_B_or_F": "Not a binding or functional assay.",
    "standard_type_out_of_scope": "Endpoint type outside Ki, Kd, IC50, EC50, AC50, Kb.",
    "kept_exact": "Exact measurements retained and eligible for medians and tiers.",
    "kept_bound": "Bounds and approximations retained with their relation, outside medians.",
    "kept_conditional": (
        "Conditional mass-basis conversions retained, excluded from tiers and potency "
        "until the measured material basis is verified (D11)."),
    "kept_unresolved": "Retained with an explicit reason for not resolving to a value.",
    "no_claimable_assignment": (
        "Retained observations that back no edge: unassigned, non-molecular, or a target "
        "type outside the four claimable identities."),
    "scanned": "Activity rows scanned for the catalogue's compound families.",
}


def _properties(conn, molregnos):
    out = {}
    for chunk in common.chunked(molregnos):
        marks = ",".join("?" * len(chunk))
        for row in conn.execute(
            f"SELECT cp.molregno, cp.full_mwt, cp.full_molformula, cs.canonical_smiles,"
            f"       cs.standard_inchi_key"
            f"  FROM compound_properties cp"
            f"  LEFT JOIN compound_structures cs ON cs.molregno = cp.molregno"
            f" WHERE cp.molregno IN ({marks})", chunk):
            out[row["molregno"]] = dict(row)
    return out


def build(stage_only: bool = False) -> int:
    started = datetime.datetime.now()
    sel_policy = common.load_policy("cohort1_selection.json")
    ev_policy = common.load_policy("cohort1_evidence.json")

    common.log(f"SubNetwork cohort-1 build  ({common.CHEMBL_RELEASE}, read-only)")
    common.log("  selection policy %s v%s / evidence policy %s v%s" % (
        sel_policy["policy_id"], sel_policy["version"],
        ev_policy["policy_id"], ev_policy["version"]))

    # ---- pinned inputs ---------------------------------------------------
    mesh_sha = common.sha256(common.MESH_SCOPE_CSV)
    pinned_sha = sel_policy["pinned_inputs"]["mesh_classification"]["sha256"]
    if mesh_sha != pinned_sha:
        raise common.PolicyError(
            f"{common.MESH_SCOPE_CSV} has changed: policy pins {pinned_sha}, file is "
            f"{mesh_sha}. The ontology input is pinned by D14; raise the policy version "
            f"deliberately rather than letting it drift.")

    common.log("  resolving the adopted indication scope...")
    descriptors = scope_mod.load(sel_policy)
    problems = scope_mod.fixtures_check(descriptors, sel_policy)
    if problems:
        raise common.PolicyError("adopted scope does not deliver its own fixtures: "
                                 + "; ".join(problems))
    scope_summary = scope_mod.summarise(descriptors)
    common.log("    %d descriptors in scope (%d core, %d recovered outside core)" % (
        scope_summary["descriptors_in_scope"], scope_summary["descriptors_in_core"],
        scope_summary["recovered_outside_core"]))

    conn = common.chembl()

    # ---- what stands behind each Approved (D23) --------------------------
    label_pin = sel_policy["pinned_inputs"]["label_status"]["sha256"]
    label_sha = common.sha256(labels_mod.STATUS_FILE)
    if label_sha != label_pin:
        raise common.PolicyError(
            f"{labels_mod.STATUS_FILE.name} has changed: policy pins {label_pin}, file is "
            f"{label_sha}. It moves membership (D23); raise the policy version "
            f"deliberately rather than letting it drift.")
    label_status = labels_mod.LabelStatus(conn)
    label_summary = label_status.summary()
    common.log(f"  label status {label_summary['file']} v{label_summary['version']}: "
               f"phase-4 records by basis {label_summary['bases']}")

    # ---- selection -------------------------------------------------------
    common.log("  selecting the catalogue...")
    sel = selection.run(conn, sel_policy, descriptors, label_status)
    members = sel["members"]
    member_to_parent = {f["molregno"]: p
                        for p, m in members.items() for f in m.family}

    conn.execute("CREATE TEMP TABLE cohort_members(molregno INTEGER PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO cohort_members VALUES(?)",
                     [(m,) for m in member_to_parent])

    # ---- staging database ------------------------------------------------
    db = store.create(common.STAGING_DB)
    common.log(f"  staging at {common.STAGING_DB.relative_to(common.ROOT)}")

    indication_rows = collections.Counter()
    for row in conn.execute("SELECT mesh_id, COUNT(*) n FROM drug_indication GROUP BY mesh_id"):
        indication_rows[row["mesh_id"]] = row["n"]
    store.write_scope(db, descriptors, indication_rows)

    props = _properties(conn, set(members))
    store.write_molecules(db, members, props)

    atc_by_mol = collections.defaultdict(list)
    for row in conn.execute("""
        SELECT mac.molregno, a.level5, a.level4, a.level3, a.level2, a.who_name,
               a.level3_description
          FROM molecule_atc_classification mac
          JOIN atc_classification a ON a.level5 = mac.level5
         WHERE a.level1 = 'N' ORDER BY mac.molregno, a.level5
    """):
        atc_by_mol[row["molregno"]].append(row)
    store.write_atc(db, members, atc_by_mol, sel["records"])
    # Every ATC code and USAN stem, for search and display; molecule_atc above
    # stays the admission route's N-only record.
    classes_mod.write(db, *classes_mod.collect(conn, member_to_parent))
    db.commit()

    # ---- evidence --------------------------------------------------------
    common.log("  loading targets...")
    target_index = targets_mod.load(conn)
    assessor = evidence.Assessor(ev_policy)
    measured = evidence.measured_records(conn, set(member_to_parent))

    common.log("  scanning activities (the long query)...")
    batch, used_targets = [], set()

    def emit(obs):
        batch.append(obs)
        # Only the four claimable identities become target records. An
        # observation filed against a cell line, an organism or a tissue keeps
        # that id for provenance and its reason for backing no claim, but it
        # must not enter the target index: a search that offered 1,144 cell
        # lines as targets would be answering a different question.
        tgt = target_index.get(obs["tid"])
        if tgt and tgt["claimable"]:
            used_targets.add(tgt["chembl_id"])
        if len(batch) >= 20000:
            store.write_observations(db, batch)
            batch.clear()

    counts, known_bad = evidence.scan_activities(
        conn, assessor, member_to_parent, target_index, measured, emit)
    if batch:
        store.write_observations(db, batch)
        batch.clear()
    db.commit()
    common.log("    scanned %d rows; kept %d observations (%d exact, %d bounds, "
               "%d conditional, %d unresolved)" % (
                   counts["scanned"],
                   counts["kept_exact"] + counts["kept_bound"] + counts["kept_conditional"]
                   + counts["kept_unresolved"],
                   counts["kept_exact"], counts["kept_bound"],
                   counts["kept_conditional"], counts["kept_unresolved"]))
    common.log("    excluded: %d organism-format, %d non-B/F assays, %d out-of-scope "
               "endpoints, %d known-bad" % (
                   counts["organism_based_format"], counts["assay_type_not_B_or_F"],
                   counts["standard_type_out_of_scope"], counts["documented_exclusion"]))

    common.log("  loading curated mechanisms...")
    curated = evidence.load_curated(conn, member_to_parent, target_index)
    evidence.withhold_excluded_actions(curated, assessor.mechanism_action_exclusions)
    for m in curated:
        # Only claimable targets enter the target table: a mechanism filed
        # against another target type is kept as a record, not as an identity
        # the graph can draw.
        if m["target_chembl_id"]:
            used_targets.add(m["target_chembl_id"])
    common.log(f"    {len(curated)} curated mechanism records")

    accessions = {c["accession"] for t in target_index.values()
                  if t["chembl_id"] in used_targets for c in t["components"]}
    store.write_targets(db, target_index, used_targets,
                        targets_mod.gene_symbols(conn, accessions),
                        targets_mod.protein_classes(conn, accessions))
    db.commit()

    # ---- claims, one parent at a time -----------------------------------
    common.log("  aggregating claims...")
    curated_by_parent = collections.defaultdict(list)
    for m in curated:
        curated_by_parent[m["parent_molregno"]].append(m)

    n_claims = 0
    for parent in sorted(members):
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM observations WHERE parent_molregno = ?", (parent,))]
        claims = evidence.aggregate_claims(rows, curated_by_parent.get(parent, []), ev_policy)
        if not claims:
            continue
        obs_updates, mech_updates = [], []
        for claim in claims.values():
            claim_id = store.write_claim(db, claim)
            n_claims += 1
            for r in claim.get("rows", []):
                obs_updates.append((claim_id, r["counted"], r["activity_id"]))
            for m in claim.get("mechanisms", []):
                mech_updates.append((claim_id, m["mec_id"]))
                m["claim_id"] = claim_id
        db.executemany("UPDATE observations SET claim_id = ?, counted = ? "
                       "WHERE activity_id = ?", obs_updates)
        db.commit()
    common.log(f"    {n_claims} claims")

    store.write_curated(db, curated)
    store.write_exclusions(db, counts, known_bad, EXCLUSION_NOTES)
    store.write_source_coverage(db, ev_policy)

    # ---- derived catalogue status ---------------------------------------
    _write_evidence_status(db)
    db.commit()

    # ---- manifest and validation ----------------------------------------
    store.write_manifest(db, {
        "built_at": started.isoformat(timespec="seconds"),
        "chembl_release": common.CHEMBL_RELEASE,
        "chembl_path": str(common.CHEMBL_DB),
        "selection_policy": json.dumps(common.policy_fingerprint("cohort1_selection.json")),
        "evidence_policy": json.dumps(common.policy_fingerprint("cohort1_evidence.json")),
        "label_status": json.dumps(label_summary),
        "mesh_classification": json.dumps({
            "file": str(common.MESH_SCOPE_CSV.relative_to(common.ROOT)),
            "sha256": mesh_sha, "descriptors": len(descriptors)}),
        "scope_summary": json.dumps(scope_summary),
        "route_arithmetic": json.dumps(sel["arithmetic"]),
        "activity_scan": json.dumps(dict(counts)),
        "active_pharmacology_sources": "chembl_37",
        "deferred_sources": json.dumps(ev_policy["source_scope"]["deferred"]["sources"]),
    })
    db.commit()

    common.log("  validating...")
    results = validate_mod.run(db)
    store.write_validation(db, results)
    db.commit()
    failed = [r for r in results if r["result"] != "PASS"]
    for r in results:
        mark = "ok " if r["result"] == "PASS" else "FAIL"
        common.log(f"    [{mark}] {r['check']}: {r['detail']}")
    db.close()

    if failed:
        common.log(f"  {len(failed)} validation checks failed; not activating.")
        return 1

    if stage_only:
        common.log(f"  staged only. Activate with: python3 scripts/build_cohort.py --activate")
        return 0
    return activate()


def activate() -> int:
    if not common.STAGING_DB.exists():
        common.log(f"no staged build at {common.STAGING_DB}")
        return 1
    backup = store.activate(common.STAGING_DB, common.COHORT_DB)
    common.log(f"  activated {common.COHORT_DB.relative_to(common.ROOT)}")
    if backup:
        common.log(f"  previous database backed up to {backup.relative_to(common.ROOT)}")
    common.log("  next: python3 scripts/export_cohort.py")
    return 0


# Each evidence_status and the gap_reason it carries, first match wins.
GAP_REASONS = {
    "has_supported": None,
    "has_supported_broader_only": "Supported evidence only in the broader assignment layer",
    "has_preliminary": "No Supported claim; Preliminary evidence only",
    "limited_only": "Observations retained, none meeting Preliminary or above",
    "no_eligible_evidence": "No qualifying evidence found in ChEMBL 37",
}


def evidence_status_of(claims) -> tuple[str, str | None]:
    """The (evidence_status, gap_reason) one entry's claims give it.

    `claims` is that entry's (basis, tier) pairs. The same rule as
    _write_evidence_status, for the export, which states a status from a
    subset of the claims (ChEMBL's alone, without GtoPdb's) and checks this
    against the stored status over all of them, so the two cannot drift.
    """
    claims = list(claims)
    if ("human_direct", "supported") in claims:
        status = "has_supported"
    elif any(t == "supported" for _, t in claims):
        status = "has_supported_broader_only"
    elif any(t == "preliminary" for _, t in claims):
        status = "has_preliminary"
    elif claims:
        status = "limited_only"
    else:
        status = "no_eligible_evidence"
    return status, GAP_REASONS[status]


def _write_evidence_status(db) -> None:
    """Say what each catalogue entry has, so a gap can name itself.

    Four different statements, never collapsed into one: it has Supported
    evidence, it has Preliminary evidence, everything it has is limited or
    unresolved, or ChEMBL 37 holds nothing assessable for it at all. The last
    is a coverage gap in one source, not an absence of pharmacology.
    """
    db.execute("""
        UPDATE molecules SET evidence_status = 'has_supported', gap_reason = NULL
         WHERE parent_molregno IN (
            SELECT parent_molregno FROM claims
             WHERE basis = 'human_direct' AND tier = 'supported')
    """)
    db.execute("""
        UPDATE molecules SET evidence_status = 'has_supported_broader_only',
               gap_reason = ?
         WHERE evidence_status IS NULL AND parent_molregno IN (
            SELECT parent_molregno FROM claims WHERE tier = 'supported')
    """, (GAP_REASONS["has_supported_broader_only"],))
    db.execute("""
        UPDATE molecules SET evidence_status = 'has_preliminary',
               gap_reason = ?
         WHERE evidence_status IS NULL AND parent_molregno IN (
            SELECT parent_molregno FROM claims WHERE tier = 'preliminary')
    """, (GAP_REASONS["has_preliminary"],))
    db.execute("""
        UPDATE molecules SET evidence_status = 'limited_only',
               gap_reason = ?
         WHERE evidence_status IS NULL AND parent_molregno IN (
            SELECT parent_molregno FROM claims)
    """, (GAP_REASONS["limited_only"],))
    db.execute("""
        UPDATE molecules SET evidence_status = 'no_eligible_evidence',
               gap_reason = ?
         WHERE evidence_status IS NULL
    """, (GAP_REASONS["no_eligible_evidence"],))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage-only", action="store_true",
                    help="build and validate, but do not replace the active database")
    ap.add_argument("--activate", action="store_true",
                    help="activate the existing staged build without rebuilding")
    args = ap.parse_args(argv)
    try:
        if args.activate:
            return activate()
        return build(stage_only=args.stage_only)
    except common.PolicyError as exc:
        common.log(f"build failed: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
