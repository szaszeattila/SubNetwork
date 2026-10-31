"""Checks a cohort build must pass before it may replace the active database.

These are structural: referential integrity, uniqueness of source records,
admission-route arithmetic, and the accounting rules that let a displayed
number be checked against the rows behind it. A check that fails stops
activation rather than printing a warning.
"""

from __future__ import annotations


def _one(db, sql, *params):
    row = db.execute(sql, params).fetchone()
    return row[0] if row else 0


def run(db) -> list[dict]:
    out = []

    def check(name, ok, detail):
        out.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    # 1. Every claim points at a molecule and a target that exist.
    orphan_m = _one(db, "SELECT COUNT(*) FROM claims c LEFT JOIN molecules m"
                        " ON m.parent_molregno = c.parent_molregno"
                        " WHERE m.parent_molregno IS NULL")
    orphan_t = _one(db, "SELECT COUNT(*) FROM claims c LEFT JOIN targets t"
                        " ON t.chembl_id = c.target_chembl_id WHERE t.chembl_id IS NULL")
    check("referential integrity of claims", orphan_m == 0 and orphan_t == 0,
          f"{orphan_m} claims with no molecule, {orphan_t} with no target")

    # 2. Every observation belongs to a catalogue molecule, and every claim_id
    #    it carries exists.
    orphan_o = _one(db, "SELECT COUNT(*) FROM observations o LEFT JOIN molecules m"
                        " ON m.parent_molregno = o.parent_molregno"
                        " WHERE m.parent_molregno IS NULL")
    orphan_c = _one(db, "SELECT COUNT(*) FROM observations o LEFT JOIN claims c"
                        " ON c.id = o.claim_id"
                        " WHERE o.claim_id IS NOT NULL AND c.id IS NULL")
    check("referential integrity of observations", orphan_o == 0 and orphan_c == 0,
          f"{orphan_o} observations with no molecule, {orphan_c} with a dangling claim")

    # 3. Source-record uniqueness: one row per ChEMBL activity_id.
    dupes = _one(db, "SELECT COUNT(*) FROM (SELECT activity_id FROM observations"
                     " GROUP BY activity_id HAVING COUNT(*) > 1)")
    check("source record uniqueness", dupes == 0,
          f"{dupes} activity_id values stored more than once")

    # 4. Admission-route arithmetic: the routes partition the cohort exactly.
    atc_only = _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND route_atc_n=1"
                        " AND route_indication=0")
    ind_only = _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND route_atc_n=0"
                        " AND route_indication=1")
    both = _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND route_atc_n=1"
                    " AND route_indication=1")
    cohort = _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1")
    check("admission route arithmetic", atc_only + ind_only + both == cohort,
          f"{atc_only} ATC-only + {ind_only} indication-only + {both} both = "
          f"{atc_only + ind_only + both}, cohort is {cohort}")

    # 5. No cohort member without a reason, no retained seed or listed molecule
    #    (D25) without one either, and a listed_only entry has its listing.
    unreasoned = _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1 AND"
                          " admission_reason IN ('seed_only', 'listed_only')")
    seedless = _one(db, "SELECT COUNT(*) FROM molecules m WHERE in_cohort=0 AND"
                        " (exclusion_reason IS NULL OR NOT (is_seed=1 OR EXISTS"
                        " (SELECT 1 FROM molecule_listings l"
                        "   WHERE l.parent_molregno = m.parent_molregno)))")
    unlisted = _one(db, "SELECT COUNT(*) FROM molecules m WHERE admission_reason ="
                        " 'listed_only' AND NOT EXISTS (SELECT 1 FROM molecule_listings l"
                        " WHERE l.parent_molregno = m.parent_molregno)")
    check("every entry carries its admission or exclusion reason",
          unreasoned == 0 and seedless == 0 and unlisted == 0,
          f"{unreasoned} members admitted with no route, {seedless} non-members that are "
          f"not retained seeds or listed molecules with a reason, {unlisted} listed_only "
          f"entries with no listing")

    # 6. Parent identity: one row per parent, and every form rolls up to one.
    dup_parent = _one(db, "SELECT COUNT(*) FROM (SELECT chembl_id FROM molecules"
                          " GROUP BY chembl_id HAVING COUNT(*) > 1)")
    split_form = _one(db, "SELECT COUNT(*) FROM (SELECT molregno FROM molecule_forms"
                          " GROUP BY molregno HAVING COUNT(DISTINCT parent_molregno) > 1)")
    check("parent identity", dup_parent == 0 and split_form == 0,
          f"{dup_parent} duplicated parents, {split_form} forms rolling up to two parents")

    # 7. Invariant 7 as an accounting rule: each endpoint summary's measurement
    #    count equals the rows stored against it with counted = 1.
    mismatch = _one(db, """
        SELECT COUNT(*) FROM claim_endpoints e
         WHERE e.n_measurements <> (
            SELECT COUNT(*) FROM observations o
             WHERE o.claim_id = e.claim_id AND o.endpoint_class = e.endpoint_class
               AND o.counted = 1)
    """)
    check("per-summary measurement counts reconcile", mismatch == 0,
          f"{mismatch} endpoint summaries whose n_measurements does not equal the rows "
          f"counted into it")

    # 8. Only exact values are counted. A bound, a conditional mass conversion
    #    or an unresolved unit must never enter a median.
    bad_counted = _one(db, "SELECT COUNT(*) FROM observations WHERE counted = 1"
                           " AND value_status <> 'exact'")
    check("only exact values are counted", bad_counted == 0,
          f"{bad_counted} non-exact observations marked as counted")

    # 9. Study support is counted in studies, not rows, and only publications
    #    can create multiple-study support.
    bad_support = _one(db, """
        SELECT COUNT(*) FROM claims c
         WHERE c.multiple_study_support = 1
           AND NOT EXISTS (SELECT 1 FROM claim_endpoints e
                            WHERE e.claim_id = c.id AND e.supported = 1
                              AND e.n_publications >= 2)
    """)
    check("multiple-study support needs two publications in one endpoint class",
          bad_support == 0,
          f"{bad_support} claims flagged as replicated without two publication-class "
          f"studies in a single endpoint class")

    # 10. No claim on a target type outside the four claimable identities, and
    #     no observation without an assignment carrying a claim.
    bad_target = _one(db, "SELECT COUNT(*) FROM claims c JOIN targets t"
                          " ON t.chembl_id = c.target_chembl_id"
                          " WHERE t.target_type NOT IN ('SINGLE PROTEIN','PROTEIN COMPLEX',"
                          " 'PROTEIN COMPLEX GROUP','PROTEIN FAMILY')")
    manufactured = _one(db, "SELECT COUNT(*) FROM observations"
                            " WHERE claim_id IS NOT NULL AND basis IS NULL")
    check("no claim on a non-claimable target, no edge from an unassigned observation",
          bad_target == 0 and manufactured == 0,
          f"{bad_target} claims on other target types, {manufactured} unassigned "
          f"observations attached to a claim")

    # 11. Organism-format observations are absent from every active layer.
    organism = _one(db, "SELECT COUNT(*) FROM observations WHERE bao_label ="
                        " 'organism-based format'")
    check("organism-format observations excluded", organism == 0,
          f"{organism} organism-format rows present in observations")

    # 12. Curated support never appears on an experimental claim, and a curated
    #     claim never carries measurements.
    leak = _one(db, "SELECT COUNT(*) FROM claims WHERE claim_role <> 'curated'"
                    " AND curated_support = 1")
    leak2 = _one(db, "SELECT COUNT(*) FROM claims WHERE claim_role = 'curated'"
                     " AND n_measurements > 0")
    check("curated and measured support stay separate", leak == 0 and leak2 == 0,
          f"{leak} experimental claims carrying curated support, {leak2} curated claims "
          f"carrying measurements")

    # 13. Bases never mix: a claim's observations all sit in its own basis.
    mixed = _one(db, """
        SELECT COUNT(*) FROM observations o JOIN claims c ON c.id = o.claim_id
         WHERE c.claim_role <> 'curated' AND o.basis <> c.basis
    """)
    check("assignment bases do not pool", mixed == 0,
          f"{mixed} observations attached to a claim in a different basis")

    # 14. Exclusion accounting: the scan's reasons add up to what it scanned.
    scanned = _one(db, "SELECT n_rows FROM exclusion_summary WHERE reason = 'scanned'")
    # 'scanned' is the total; 'no_claimable_assignment' and the per-assay-type
    # organism-format rows are breakdowns of buckets already counted, not
    # buckets of their own.
    parts = _one(db, "SELECT COALESCE(SUM(n_rows),0) FROM exclusion_summary"
                     " WHERE reason NOT IN ('scanned', 'no_claimable_assignment')"
                     "   AND reason NOT LIKE 'organism_based_format\\_%' ESCAPE '\\'")
    check("exclusion accounting", scanned == parts,
          f"scanned {scanned}, reasons account for {parts}")

    # 15. Every catalogue entry has an evidence status, so no entry is silent.
    silent = _one(db, "SELECT COUNT(*) FROM molecules WHERE evidence_status IS NULL")
    check("every catalogue entry states its evidence status", silent == 0,
          f"{silent} entries with no evidence status")

    return out
