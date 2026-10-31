"""Write a cohort build into a staging SQLite database.

The build is deterministic and restartable: it always writes to a fresh
staging file, so a rerun cannot leave a stale claim behind by appending to
what a previous run produced. Activation is a separate, reversible step that
copies the validated staging file over the active one after backing it up.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import shutil
import sqlite3

from . import common


def create(path: pathlib.Path) -> sqlite3.Connection:
    """Open a brand-new staging database with the cohort schema applied."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    for suffix in ("-journal", "-wal", "-shm"):
        stale = path.with_name(path.name + suffix)
        if stale.exists():
            stale.unlink()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript((common.DB / "schema_cohort.sql").read_text())
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    return conn


def _join(values) -> str | None:
    return "|".join(str(v) for v in values) if values else None


def write_manifest(conn, entries: dict) -> None:
    conn.executemany("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                     [(k, json.dumps(v) if not isinstance(v, str) else v)
                      for k, v in entries.items()])


def write_scope(conn, descriptors, indication_rows) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO indication_scope(mesh_id, label, tree_numbers, in_core,"
        " boundary_classes, in_scope, scope_reasons, drug_indication_rows)"
        " VALUES(?,?,?,?,?,?,?,?)",
        [(d.mesh_id, d.label, ";".join(d.tree_numbers), int(d.in_core),
          _join(d.boundary_classes), int(d.in_scope), _join(d.scope_reasons),
          indication_rows.get(d.mesh_id, 0))
         for d in descriptors.values()])


def write_molecules(conn, members, properties) -> None:
    rows, forms, syns, inds, withdrawn, listings = [], [], [], [], [], []
    for m in members.values():
        chembl_of = {f["molregno"]: f["chembl_id"] for f in m.family}
        for w in m.withdrawals:
            withdrawn.append((m.parent_molregno, w["warning_id"], w["molregno"],
                              chembl_of.get(w["molregno"]), w["countries"], w["year"],
                              w["warning_class"], w["description"]))
        p = properties.get(m.parent_molregno, {})
        for e in m.listings:
            listings.append((m.parent_molregno, e["source"], e["chembl_id"], e["name"],
                             e["slug"], e.get("section"), e.get("placed_by")))
        rows.append((
            m.parent_molregno, m.parent_chembl_id, m.pref_name, m.molecule_type,
            m.structure_type, m.max_phase, m.first_approval, int(m.withdrawn_any_family),
            int(m.in_cohort), int(m.is_seed), m.seed_name,
            int(m.route_atc_n), int(m.route_indication), m.admission_reason,
            m.exclusion_reason, _join(m.scope_reasons), _join(m.atc_level5),
            _join(m.atc_flags), _join(m.identity_flags),
            p.get("full_molformula"), p.get("full_mwt"),
            p.get("canonical_smiles"), p.get("standard_inchi_key"), None,
            m.n_indications_chembl, _join(m.approved_elsewhere),
            m.approval_status, m.max_phase_checked,
        ))
        for f in m.family:
            forms.append((m.parent_molregno, f["molregno"], f["chembl_id"], f["pref_name"],
                          f["molecule_type"], f["structure_type"], f["max_phase"],
                          f["withdrawn_flag"], int(f["is_parent"]),
                          int(f["carries_atc_n"]), int(f["carries_qualifying_indication"]),
                          f["seed_alias"]))
            for s in f["synonyms"]:
                syns.append((m.parent_molregno, f["molregno"], s))
        for qualifies, entries in ((1, m.qualifying_indications),
                                   (0, m.near_miss_indications)):
            for e in entries:
                labels = e.get("unapproved_labels") or []
                inds.append((m.parent_molregno, e["drugind_id"], e["member_molregno"],
                             e["member_chembl_id"], e["mesh_id"], e["mesh_heading"],
                             e["efo_id"], e["efo_term"], e["max_phase_for_ind"],
                             e["phase_label"], _join(e["scope_reasons"]), qualifies,
                             _join(e.get("trial_ids", ())), e.get("chembl_max_phase"),
                             e.get("approval_basis"),
                             json.dumps(labels, ensure_ascii=False) if labels else None,
                             _join(e.get("atc_classes") or ()) or None,
                             e.get("unread_reason")))

    conn.executemany(
        "INSERT INTO molecules(parent_molregno, chembl_id, pref_name, molecule_type,"
        " structure_type, max_phase, first_approval, withdrawn_any_family, in_cohort,"
        " is_seed, seed_name, route_atc_n, route_indication, admission_reason,"
        " exclusion_reason, scope_reasons, atc_level5, atc_flags, identity_flags,"
        " molecular_formula, molecular_weight, smiles, inchikey, wikipedia_url,"
        " n_indications_chembl, approved_elsewhere, approval_status, max_phase_checked)"
        " VALUES(" + ",".join("?" * 28) + ")", rows)
    conn.executemany(
        "INSERT OR REPLACE INTO molecule_forms(parent_molregno, molregno, chembl_id,"
        " pref_name, molecule_type, structure_type, max_phase, withdrawn_flag, is_parent,"
        " carries_atc_n, carries_qualifying_indication, seed_alias)"
        " VALUES(" + ",".join("?" * 12) + ")", forms)
    conn.executemany(
        "INSERT OR IGNORE INTO molecule_synonyms(parent_molregno, molregno, synonym)"
        " VALUES(?,?,?)", syns)
    conn.executemany(
        "INSERT INTO molecule_withdrawals(parent_molregno, warning_id, molregno,"
        " chembl_id, countries, year, warning_class, description)"
        " VALUES(?,?,?,?,?,?,?,?)", withdrawn)
    conn.executemany(
        "INSERT INTO molecule_listings(parent_molregno, source, chembl_id, name, slug,"
        " section, placed_by) VALUES(?,?,?,?,?,?,?)", listings)
    conn.executemany(
        "INSERT OR REPLACE INTO molecule_indications(parent_molregno, drugind_id,"
        " member_molregno, member_chembl_id, mesh_id, mesh_heading, efo_id, efo_term,"
        " max_phase_for_ind, phase_label, scope_reasons, qualifies, trial_ids,"
        " chembl_max_phase, approval_basis, unapproved_labels, atc_classes, unread_reason)"
        " VALUES(" + ",".join("?" * 18) + ")", inds)


def write_atc(conn, members, atc_by_mol, records) -> None:
    rows = []
    for m in members.values():
        for f in m.family:
            for r in atc_by_mol.get(f["molregno"], []):
                rows.append((m.parent_molregno, f["molregno"], f["chembl_id"],
                             r["level5"], r["level4"], r["level3"], r["level2"],
                             r["who_name"], r["level3_description"],
                             _atc_flag(r["level3"])))
    conn.executemany(
        "INSERT OR REPLACE INTO molecule_atc(parent_molregno, carrier_molregno,"
        " carrier_chembl_id, level5, level4, level3, level2, who_name,"
        " level3_description, boundary_flag) VALUES(" + ",".join("?" * 10) + ")", rows)


_ATC_FLAGS = {"N01B": "peripheral_site_of_action", "N02B": "general_analgesic"}


def _atc_flag(level3):
    return _ATC_FLAGS.get(level3)


def write_targets(conn, target_index, used_chembl_ids, gene_symbols,
                  protein_classes=None) -> None:
    protein_classes = protein_classes or {}
    rows, comps = [], []
    for t in target_index.values():
        if t["chembl_id"] not in used_chembl_ids:
            continue
        rows.append((t["chembl_id"], t["tid"], t["pref_name"], t["target_type"],
                     t["organism"], t["tax_id"], t["n_components"], None))
        for c in t["components"]:
            comps.append((t["chembl_id"], c["accession"], c["description"],
                          gene_symbols.get(c["accession"]),
                          protein_classes.get(c["accession"])))
    conn.executemany(
        "INSERT OR REPLACE INTO targets(chembl_id, tid, pref_name, target_type, organism,"
        " tax_id, n_components, wikipedia_url) VALUES(?,?,?,?,?,?,?,?)", rows)
    conn.executemany(
        "INSERT OR REPLACE INTO target_components(target_chembl_id, accession, description,"
        " gene_symbol, protein_class) VALUES(?,?,?,?,?)", comps)


OBS_COLUMNS = [
    "activity_id", "parent_molregno", "measured_molregno", "measured_chembl_id",
    "target_chembl_id", "tid", "claim_id", "role", "endpoint_class", "standard_type",
    "standard_relation", "standard_value", "standard_units", "value_nm", "value_status",
    "conversion_kind", "conversion_factor", "conversion_basis", "conversion_note",
    "material_basis_verified", "measured_full_mwt", "measured_form", "counted", "basis",
    "assignment_class", "assignment_reason", "confidence_score", "relationship_type",
    "variant_id", "assay_chembl_id", "assay_description", "assay_type", "bao_label",
    "data_validity_comment", "potential_duplicate", "activity_comment", "study_key",
    "provenance_class", "pubmed_id", "doi", "patent_id", "doc_chembl_id", "doc_year",
    "doc_journal", "doc_title", "exclusion_reason",
]

OBS_SQL = ("INSERT OR REPLACE INTO observations(" + ",".join(OBS_COLUMNS) + ") VALUES("
           + ",".join("?" * len(OBS_COLUMNS)) + ")")


def write_observations(conn, rows) -> None:
    conn.executemany(OBS_SQL, [tuple(r.get(c) for c in OBS_COLUMNS) for r in rows])


CLAIM_COLUMNS = [
    "parent_molregno", "target_chembl_id", "claim_role", "basis", "tier", "tier_reason",
    "curated_support", "multiple_study_support", "supporting_endpoint_class", "n_rows",
    "n_measurements", "n_bounds", "n_conditional", "n_unresolved", "n_studies",
    "n_publications", "n_patents", "n_datasets", "action_type", "mechanism_of_action",
    "direct_interaction", "conflict_action", "conflict_dispersion", "conflict_detail",
    "assignment_classes", "action_exclusion",
]

CLAIM_SQL = ("INSERT INTO claims(" + ",".join(CLAIM_COLUMNS) + ") VALUES("
             + ",".join("?" * len(CLAIM_COLUMNS)) + ")")


def write_claim(conn, claim) -> int:
    values = []
    for c in CLAIM_COLUMNS:
        v = claim.get(c)
        values.append("|".join(v) if isinstance(v, list) else v)
    cur = conn.execute(CLAIM_SQL, values)
    claim_id = cur.lastrowid

    conn.executemany(
        "INSERT OR REPLACE INTO claim_endpoints(claim_id, endpoint_class, n_measurements,"
        " n_rows, median_nm, min_nm, max_nm, n_studies, n_publications, supported,"
        " log_spread) VALUES(" + ",".join("?" * 11) + ")",
        [(claim_id, e["endpoint_class"], e["n_measurements"], e["n_rows"], e["median_nm"],
          e["min_nm"], e["max_nm"], e["n_studies"], e["n_publications"], e["supported"],
          e["log_spread"]) for e in claim["endpoints"].values()])

    conn.executemany(
        "INSERT OR REPLACE INTO claim_studies(claim_id, endpoint_class, study_key,"
        " provenance_class, n_measurements, n_rows, pubmed_id, doi, patent_id,"
        " doc_chembl_id, year, journal, title) VALUES(" + ",".join("?" * 13) + ")",
        [(claim_id, e["endpoint_class"], s["study_key"], s["provenance_class"],
          s["n_measurements"], s["n_rows"], s["pubmed_id"], s["doi"], s["patent_id"],
          s["doc_chembl_id"], s["year"], s["journal"], s["title"])
         for e in claim["endpoints"].values() for s in e["studies"]])
    return claim_id


def write_curated(conn, mechanisms) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO curated_mechanisms(mec_id, parent_molregno,"
        " measured_molregno, target_chembl_id, claim_id, action_type, action_parent_type,"
        " mechanism_of_action, direct_interaction, molecular_mechanism, mechanism_comment,"
        " selectivity_comment, variant_id, n_refs, refs, tier, tier_reason,"
        " excluded_action_type, action_exclusion)"
        " VALUES(" + ",".join("?" * 19) + ")",
        [(m["mec_id"], m["parent_molregno"], m["measured_molregno"],
          m.get("source_target_chembl_id") or m["target_chembl_id"],
          m.get("claim_id"), m["action_type"], m["action_parent_type"],
          m["mechanism_of_action"], m["direct_interaction"], m["molecular_mechanism"],
          m["mechanism_comment"], m["selectivity_comment"], m["variant_id"],
          m["n_refs"], json.dumps(m["refs"]), m["tier"], m["tier_reason"],
          m.get("excluded_action_type"), m.get("action_exclusion"))
         for m in mechanisms])


def write_exclusions(conn, counts, known_bad_rows, notes) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO exclusion_summary(reason, n_rows, retained, note)"
        " VALUES(?,?,?,?)",
        [(reason, n, 1 if reason.startswith("kept_") else 0, notes.get(reason))
         for reason, n in sorted(counts.items())])
    conn.executemany(
        "INSERT OR REPLACE INTO excluded_records(activity_id, parent_molregno,"
        " assay_chembl_id, target_chembl_id, reason, detail) VALUES(?,?,?,?,?,?)",
        [(r["activity_id"], r["parent_molregno"], r["assay_chembl_id"],
          r["target_chembl_id"], r["reason"], r["detail"]) for r in known_bad_rows])


def write_source_coverage(conn, policy) -> None:
    rows = [("ChEMBL", "assessed", common.CHEMBL_RELEASE,
             "The only active pharmacology source in this release (D12).")]
    for src in policy["source_scope"]["deferred"]["sources"]:
        rows.append((src, "not_assessed", None,
                     "Deferred to cohort 2. Not assessed is not a negative finding and "
                     "is never shown as absence of pharmacology."))
    conn.executemany(
        "INSERT OR REPLACE INTO source_coverage(source, status, release, note)"
        " VALUES(?,?,?,?)", rows)


def write_validation(conn, results) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO validation(check_name, result, detail) VALUES(?,?,?)",
        [(r["check"], r["result"], r["detail"]) for r in results])


def activate(staging: pathlib.Path, active: pathlib.Path) -> pathlib.Path | None:
    """Copy a validated staging database over the active one, backing it up.

    Returns the backup path, or None when there was nothing to back up. The
    active file is never edited in place: a build either produces a complete
    new file or leaves the previous one untouched.
    """
    backup = None
    if active.exists():
        common.BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        backup = common.BACKUPS / f"{active.name}.{stamp}"
        shutil.copy2(active, backup)
    active.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staging, active)
    return backup
