"""Read-only membership audit using ChEMBL 37 and the saved MeSH scope.

Run from the repository root: python3 analysis/cohort1/boundaries/audit.py
Curated mechanisms below are source annotations, not a new evidence-tier audit.
"""
import collections
import csv
import hashlib
import json
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import common
import step2_candidates as step2


def write(name, rows):
    with (HERE / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    conn = sqlite3.connect(f"file:{common.CHEMBL_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    scope_path = common.OUT / "indication_scope.csv"
    scope = {r["mesh_id"]: r for r in common.read_csv("indication_scope.csv")}
    indications = conn.execute("SELECT * FROM drug_indication").fetchall()
    atc_rows = conn.execute("""SELECT mac.molregno, a.level5 FROM
        molecule_atc_classification mac JOIN atc_classification a USING(level5)
        WHERE a.level1='N'""").fetchall()
    parent = step2.parents_for(conn, {r["molregno"] for r in indications} |
                               {r["molregno"] for r in atc_rows})
    atc = collections.defaultdict(set)
    inds = collections.defaultdict(list)
    for r in atc_rows:
        atc[parent[r["molregno"]]].add(r["level5"])
    for r in indications:
        inds[parent[r["molregno"]]].append(dict(r))
    records = step2.molecule_records(conn, set(parent.values()))
    boundaries = [b["id"] for b in json.loads(
        (common.CONFIG / "cns_indication_scope.json").read_text())["boundary_classes"]]

    def qualifying(p, adds, phase):
        return [r for r in inds[p] if r["mesh_id"] in scope and
                (scope[r["mesh_id"]]["in_core_scope"] == "1" or
                 set(adds) & set(scope[r["mesh_id"]]["scope_classes"].split(";"))) and
                (phase is None or (r["max_phase_for_ind"] is not None and
                                  float(r["max_phase_for_ind"]) >= phase))]

    def members(adds=(), phase=None, small=False):
        return {p for p in records if (not small or records[p]["molecule_type"] == "Small molecule")
                and (p in atc or qualifying(p, adds, phase))}

    baseline = members()
    saved = {int(r["parent_molregno"]) for r in common.read_csv("candidates.csv")}
    assert baseline == saved, "Baseline identity mismatch"
    assert len(members(phase=3, small=True)) == 995
    assert len(members(boundaries)) == 2611
    summary, additions = [], []
    for policy, phase, small in [("all_categories_no_phase_floor", None, False),
                                  ("small_molecules_phase3_or_approved", 3, True)]:
        base = members(phase=phase, small=small)
        for boundary in boundaries + ["all_boundaries"]:
            adds = boundaries if boundary == "all_boundaries" else [boundary]
            expanded = members(adds, phase, small)
            summary.append(dict(policy=policy, boundary=boundary, core=len(base),
                                expanded=len(expanded), added=len(expanded-base)))
            for p in sorted(expanded-base):
                r = records[p]
                q = qualifying(p, adds, phase)
                additions.append(dict(policy=policy, boundary=boundary,
                    parent_molregno=p, chembl_id=r["chembl_id"], name=r["pref_name"],
                    molecule_type=r["molecule_type"],
                    qualifying_indications="; ".join(sorted({
                        f'{i["mesh_id"]} {i["mesh_heading"]} (phase {i["max_phase_for_ind"]})' for i in q})),
                    in_unrestricted_core=int(p in baseline)))

    # All scoped parents, including those already rescued by another route.
    widest = members(boundaries)
    families = step2.families_for(conn, widest)
    reverse = {m: p for p, family in families.items() for m in family}
    mechanisms = collections.defaultdict(set)
    for r in conn.execute("""SELECT dm.*, td.chembl_id AS target_id,
            td.pref_name AS target_name, td.organism, td.target_type
            FROM drug_mechanism dm LEFT JOIN target_dictionary td ON dm.tid=td.tid"""):
        if r["molregno"] in reverse:
            mechanisms[reverse[r["molregno"]]].add(
                f'{r["mechanism_of_action"]} [{r["target_id"]}; {r["organism"]}; {r["target_type"]}]')
    inventory = []
    phase3core = members(phase=3, small=True)
    for p in sorted(widest):
        r = records[p]
        inventory.append(dict(parent_molregno=p, chembl_id=r["chembl_id"], name=r["pref_name"],
            molecule_type=r["molecule_type"], in_core=int(p in baseline),
            in_small_phase3_core=int(p in phase3core), atc_n=";".join(sorted(atc.get(p, set()))),
            qualifying_core_indications="; ".join(sorted({
                f'{i["mesh_heading"]} (phase {i["max_phase_for_ind"]})' for i in qualifying(p, [], None)})),
            boundary_classes=";".join(b for b in boundaries if any(
                b in scope.get(i["mesh_id"], {}).get("scope_classes", "").split(";") for i in inds[p])),
            curated_mechanisms="; ".join(sorted(mechanisms[p]))))
    write("scope_summary.csv", summary)
    write("boundary_additions.csv", additions)
    write("membership_inventory.csv", inventory)
    opioid_targets = ("CHEMBL233", "CHEMBL236", "CHEMBL237", "CHEMBL2014", "CHEMBL2095181")
    opioid_rows = conn.execute("""SELECT dm.molregno, dm.mec_id, dm.mechanism_of_action,
        td.chembl_id AS target_id, td.pref_name AS target_name
        FROM drug_mechanism dm JOIN target_dictionary td USING(tid)
        WHERE td.chembl_id IN (?,?,?,?,?) ORDER BY dm.mec_id""", opioid_targets).fetchall()
    opioid_parents = step2.parents_for(conn, {r["molregno"] for r in opioid_rows})
    opioid_records = step2.molecule_records(conn, set(opioid_parents.values()))
    write("curated_opioid_membership.csv", [dict(
        parent_molregno=opioid_parents[r["molregno"]],
        chembl_id=opioid_records[opioid_parents[r["molregno"]]]["chembl_id"],
        name=opioid_records[opioid_parents[r["molregno"]]]["pref_name"],
        source_molregno=r["molregno"], source_mec_id=r["mec_id"],
        target_id=r["target_id"], target_name=r["target_name"],
        mechanism=r["mechanism_of_action"],
        in_core=int(opioid_parents[r["molregno"]] in baseline),
        in_small_phase3_core=int(opioid_parents[r["molregno"]] in phase3core),
        in_widest=int(opioid_parents[r["molregno"]] in widest)
    ) for r in opioid_rows])
    (HERE / "provenance.json").write_text(json.dumps(dict(
        chembl_release=common.CHEMBL_RELEASE, chembl_path=str(common.CHEMBL_DB),
        chembl_bytes=common.CHEMBL_DB.stat().st_size,
        input_sha256={str(p.relative_to(common.PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [scope_path, common.OUT / "candidates.csv", pathlib.Path(__file__)]},
        checks=["Exact baseline parent set reproduced", "995 small-molecule phase-3 core reproduced",
                "2611 widest unrestricted union reproduced"],
        limitations="Membership and source-curated mechanism annotations only; no new evidence tiers or current regulatory verification. Phase is indication-specific; whole ATC N is independent of phase."
    ), indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
