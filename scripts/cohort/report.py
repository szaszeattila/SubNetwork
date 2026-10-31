"""Print the measured results of a cohort build.

Used to write docs/COHORT-1-IMPLEMENTATION.md and to re-check it after a
rebuild. Every number the implementation summary quotes comes from here, so a
figure in the prose can always be reproduced by running this.

    python3 scripts/cohort_report.py
"""

from __future__ import annotations

import collections
import json
import sqlite3

from . import common


def rows(db, sql, *params):
    return db.execute(sql, params).fetchall()


def one(db, sql, *params):
    r = db.execute(sql, params).fetchone()
    return r[0] if r else 0


def section(title):
    print("\n" + title)
    print("-" * len(title))


def table(db, sql, *params):
    got = rows(db, sql, *params)
    if not got:
        print("  (none)")
        return
    keys = got[0].keys()
    width = [max(len(k), max(len(str(r[k] if r[k] is not None else "")) for r in got))
             for k in keys]
    print("  " + "  ".join(k.ljust(w) for k, w in zip(keys, width)))
    for r in got:
        print("  " + "  ".join(str(r[k] if r[k] is not None else "").ljust(w)
                               for k, w in zip(keys, width)))


def run(db_path=None) -> int:
    db_path = db_path or common.COHORT_DB
    if not db_path.exists():
        print(f"no cohort database at {db_path}")
        return 1
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    manifest = {r["key"]: r["value"] for r in rows(db, "SELECT key, value FROM build_manifest")}
    section("Build")
    print("  built            ", manifest.get("built_at"))
    print("  ChEMBL release   ", manifest.get("chembl_release"))
    for key in ("selection_policy", "evidence_policy"):
        p = json.loads(manifest.get(key, "{}"))
        print("  %-17s %s v%s  sha256 %s" % (
            key.replace("_", " "), p.get("policy_id"), p.get("version"),
            (p.get("sha256") or "")[:12]))
    print("  deferred sources ", ", ".join(json.loads(manifest.get("deferred_sources", "[]"))))

    section("Catalogue")
    print("  catalogue rows (unique chemical parents): ",
          one(db, "SELECT COUNT(*) FROM molecules"))
    print("  in cohort 1:                              ",
          one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1"))
    print("  retained seeds outside cohort 1:          ",
          one(db, "SELECT COUNT(*) FROM molecules WHERE admission_reason='seed_only'"))
    print("  listed molecules outside cohort 1 (D25):  ",
          one(db, "SELECT COUNT(*) FROM molecules WHERE admission_reason='listed_only'"))
    print("  source forms folded onto those parents:   ",
          one(db, "SELECT COUNT(*) FROM molecule_forms"))
    print("  of which are not the parent themselves:   ",
          one(db, "SELECT COUNT(*) FROM molecule_forms WHERE is_parent=0"))
    print("  admission-route arithmetic:               ",
          manifest.get("route_arithmetic"))

    section("Admission routes")
    table(db, "SELECT admission_reason, COUNT(*) n FROM molecules GROUP BY 1 ORDER BY n DESC")

    section("Indication scope reasons (cohort members; a member can have several)")
    counter = collections.Counter()
    for r in rows(db, "SELECT scope_reasons FROM molecules WHERE in_cohort=1"
                      " AND scope_reasons IS NOT NULL"):
        for reason in r["scope_reasons"].split("|"):
            counter[reason] += 1
    for k, n in counter.most_common():
        print("  %-24s %d" % (k, n))
    print("  members admitted ONLY through a non-core scope reason: %d" % one(
        db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND route_atc_n=0"
            " AND scope_reasons IS NOT NULL AND scope_reasons NOT LIKE '%core%'"))

    section("Adopted scope")
    print("  descriptors classified: ", one(db, "SELECT COUNT(*) FROM indication_scope"))
    print("  in scope:               ", one(db, "SELECT COUNT(*) FROM indication_scope"
                                                " WHERE in_scope=1"))
    print("  in core:                ", one(db, "SELECT COUNT(*) FROM indication_scope"
                                                " WHERE in_core=1"))
    print("  recovered outside core: ", one(db, "SELECT COUNT(*) FROM indication_scope"
                                                " WHERE in_scope=1 AND in_core=0"))
    table(db, "SELECT mesh_id, label, scope_reasons FROM indication_scope"
              " WHERE mesh_id IN ('D005356','D009437','D051474','D014277','D005156',"
              " 'D060545','D003929','D000071075') ORDER BY mesh_id")

    section("Molecule categories (cohort members)")
    table(db, "SELECT molecule_type, COUNT(*) n FROM molecules WHERE in_cohort=1"
              " GROUP BY 1 ORDER BY n DESC")
    print("  unresolved structures retained: %d" % one(
        db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND structure_type='NONE'"))
    print("  withdrawal flags retained:      %d" % one(
        db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND withdrawn_any_family=1"))

    section("Targets (source target records, not component proteins)")
    table(db, "SELECT t.target_type, COUNT(DISTINCT t.chembl_id) target_records,"
              " COUNT(c.id) claims FROM targets t LEFT JOIN claims c"
              " ON c.target_chembl_id=t.chembl_id GROUP BY 1 ORDER BY claims DESC")
    print("  distinct target records:      ", one(db, "SELECT COUNT(*) FROM targets"))
    print("  distinct component accessions:",
          one(db, "SELECT COUNT(DISTINCT accession) FROM target_components"))
    print("  (a component is context; it is never itself a claim)")

    section("Claims by basis, role and tier")
    table(db, "SELECT basis, claim_role, tier, COUNT(*) n FROM claims"
              " GROUP BY 1,2,3 ORDER BY 1,2,3")
    print("  total claims:", one(db, "SELECT COUNT(*) FROM claims"))
    print("  distinct molecule-target pairs (any role or basis):",
          one(db, "SELECT COUNT(*) FROM (SELECT DISTINCT parent_molregno,"
                  " target_chembl_id FROM claims)"))
    print("  distinct pairs with a Supported claim in the direct human basis:",
          one(db, "SELECT COUNT(*) FROM (SELECT DISTINCT parent_molregno,"
                  " target_chembl_id FROM claims WHERE basis='human_direct'"
                  " AND tier='supported')"))

    section("Supported routes (direct human basis)")
    table(db, "SELECT curated_support, multiple_study_support, COUNT(*) n FROM claims"
              " WHERE basis='human_direct' AND tier='supported' GROUP BY 1,2")

    section("Assignment classes in the broader layer (observations)")
    table(db, "SELECT assignment_class, COUNT(*) n FROM observations"
              " WHERE basis='broader' GROUP BY 1 ORDER BY n DESC")

    section("Catalogue coverage")
    table(db, "SELECT evidence_status, COUNT(*) n FROM molecules GROUP BY 1 ORDER BY n DESC")

    section("Observations and their value status")
    table(db, "SELECT value_status, conversion_kind, COUNT(*) n FROM observations"
              " GROUP BY 1,2 ORDER BY n DESC")
    print("  counted into a median:", one(db, "SELECT COUNT(*) FROM observations"
                                              " WHERE counted=1"))
    print("  distinct studies:     ", one(db, "SELECT COUNT(DISTINCT study_key)"
                                              " FROM observations WHERE study_key IS NOT NULL"))

    section("Bounds retained, by relation")
    table(db, "SELECT standard_relation, COUNT(*) n FROM observations"
              " WHERE value_status='bound' GROUP BY 1 ORDER BY n DESC")

    section("Unit conversions")
    table(db, "SELECT conversion_kind, material_basis_verified, COUNT(*) n"
              " FROM observations WHERE conversion_kind IN ('concentration','mass')"
              " GROUP BY 1,2")
    print("  conditional rows excluded from every tier and median: %d" % one(
        db, "SELECT COUNT(*) FROM observations WHERE value_status='conditional'"
            " AND counted=1"))
    print("  (that count must be 0)")

    section("Exclusions accounted for in the activity scan")
    table(db, "SELECT reason, n_rows, retained FROM exclusion_summary ORDER BY n_rows DESC")

    section("Conflicts")
    table(db, "SELECT conflict_action, conflict_dispersion, COUNT(*) n FROM claims"
              " GROUP BY 1,2 ORDER BY n DESC")

    section("Source coverage")
    table(db, "SELECT source, status, release FROM source_coverage ORDER BY status, source")

    section("Seed outcomes")
    table(db, "SELECT seed_name, chembl_id, in_cohort, admission_reason,"
              " evidence_status FROM molecules WHERE is_seed=1 ORDER BY seed_name")
    print("  seeds admitted to cohort 1: %d of %d" % (
        one(db, "SELECT COUNT(*) FROM molecules WHERE is_seed=1 AND in_cohort=1"),
        one(db, "SELECT COUNT(*) FROM molecules WHERE is_seed=1")))

    section("Listed molecules (D25-D27)")
    table(db, "SELECT l.source, m.admission_reason, m.evidence_status, COUNT(*) n"
              " FROM molecule_listings l JOIN molecules m USING (parent_molregno)"
              " GROUP BY 1, 2, 3 ORDER BY 1, 2, n DESC")

    section("Validation")
    table(db, "SELECT check_name, result FROM validation ORDER BY check_name")
    return 0
