"""Decide cohort-1 membership from ChEMBL 37 and the adopted selection policy.

Two admission routes, kept separate throughout and both recorded on every
member (decision D01):

  route_atc_n        the parent, or any member of its ChEMBL compound family,
                     carries an ATC level-5 code whose level1 is 'N'. No
                     indication-phase requirement.
  route_indication   the parent, or a family member, has a drug_indication row
                     inside the adopted scope with max_phase_for_ind >= 3.

Neither route is evidence of anything, and neither looks at evidence: the
candidate set is fixed here and assessed afterwards, so evidence availability
can never decide who is in the catalogue.

Identity normalises to the ChEMBL parent molregno. Nothing is matched on a
name. All molecule types qualify (D03); withdrawal annotations and unresolved
structures are retained and flagged (D04); the 28 seed molecules are retained
and labelled separately from clinical membership (D05).
"""

from __future__ import annotations

import collections
import dataclasses

from . import common, scope as scope_mod


@dataclasses.dataclass
class Member:
    parent_molregno: int
    parent_chembl_id: str
    pref_name: str | None
    molecule_type: str | None
    structure_type: str | None
    max_phase: float | None
    first_approval: int | None
    withdrawn_any_family: bool
    # admission
    route_atc_n: bool
    route_indication: bool
    is_seed: bool
    seed_name: str | None
    admission_reason: str
    exclusion_reason: str | None
    # annotations
    atc_level5: tuple[str, ...]
    atc_level3: tuple[str, ...]
    atc_flags: tuple[str, ...]
    scope_reasons: tuple[str, ...]
    qualifying_indications: tuple[dict, ...]
    near_miss_indications: tuple[dict, ...]
    # Distinct diseases ChEMBL records for this family across *every*
    # therapeutic area, in scope or not. Stored so the viewer's indication list
    # can say how much of the drug's record it is showing: the two tables above
    # hold only what the adopted scope covers, and a list that cannot say so
    # reads as the whole label.
    n_indications_chembl: int
    # The MeSH headings of the diseases this family is approved for (phase 4)
    # outside the adopted scope, sorted. The viewer lists only in-scope
    # diseases, so an approved drug whose approvals all fall outside it -
    # bromazepam for Anxiety - read as "approved" over a list with no approval
    # in it. Names only, for that one sentence; never a membership input.
    approved_elsewhere: tuple[str, ...]
    family: tuple[dict, ...]
    identity_flags: tuple[str, ...]

    @property
    def in_cohort(self) -> bool:
        return self.route_atc_n or self.route_indication


def approved_out_of_scope(ind_rows, in_scope) -> dict[int, dict[str, str]]:
    """molregno -> {mesh_id: heading} for its approved indications outside scope.

    Shared by the build and scripts/resolve_cohort_approved_elsewhere.py, so a
    backfilled database and a freshly built one carry the same values.
    """
    out = collections.defaultdict(dict)
    for r in ind_rows:
        mesh = r["mesh_id"]
        phase = r["max_phase_for_ind"]
        if not mesh or mesh in in_scope or phase is None or float(phase) < 4:
            continue
        out[r["molregno"]].setdefault(mesh, r["mesh_heading"] or mesh)
    return out


def approved_for_family(by_mol, fam) -> tuple[str, ...]:
    """The distinct headings across a family, one per disease, sorted."""
    merged = {}
    for m in fam:
        for mesh, heading in by_mol.get(m, {}).items():
            merged.setdefault(mesh, heading)
    return tuple(sorted(merged.values(), key=str.lower))


def _parents_for(conn, molregnos) -> dict[int, int]:
    out = {m: m for m in molregnos}
    for chunk in common.chunked(molregnos):
        q = ("SELECT molregno, parent_molregno FROM molecule_hierarchy "
             f"WHERE molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            if row["parent_molregno"] is not None:
                out[row["molregno"]] = row["parent_molregno"]
    return out


def _families_for(conn, parents) -> dict[int, set[int]]:
    fam = {p: {p} for p in parents}
    for chunk in common.chunked(parents):
        q = ("SELECT molregno, parent_molregno FROM molecule_hierarchy "
             f"WHERE parent_molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            fam[row["parent_molregno"]].add(row["molregno"])
    return fam


MOL_COLS = ("molregno, chembl_id, pref_name, molecule_type, structure_type, max_phase, "
            "first_approval, withdrawn_flag, therapeutic_flag, natural_product, prodrug, "
            "polymer_flag, inorganic_flag, black_box_warning, chirality, chemical_probe, "
            "orphan, usan_stem")


def _records(conn, molregnos) -> dict[int, dict]:
    out = {}
    for chunk in common.chunked(molregnos):
        q = (f"SELECT {MOL_COLS} FROM molecule_dictionary "
             f"WHERE molregno IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            out[row["molregno"]] = dict(row)
    return out


def _synonyms(conn, molregnos) -> dict[int, list[str]]:
    """Source synonyms, kept so a catalogue entry stays findable by its own names."""
    out = collections.defaultdict(list)
    for chunk in common.chunked(molregnos):
        q = ("SELECT molregno, synonyms, syn_type FROM molecule_synonyms "
             f"WHERE molregno IN ({','.join('?' * len(chunk))}) "
             "ORDER BY molregno, syn_type, synonyms")
        for row in conn.execute(q, chunk):
            if row["synonyms"]:
                out[row["molregno"]].append(row["synonyms"])
    return {k: sorted(set(v)) for k, v in out.items()}


def run(conn, policy: dict, descriptors: dict) -> dict:
    """Compute the cohort. Returns members plus the audit tables."""
    routes = policy["admission_routes"]
    min_phase = routes["indication"]["min_phase"]
    flagged = {f["code"]: f["flag"] for f in routes["atc_n"]["flagged_subtrees"]}
    seed_pairs = [(name, cid) for name, cid in policy["seeds"]["molecules"]]

    # ---- route A: ATC N ---------------------------------------------------
    atc_rows = conn.execute("""
        SELECT mac.molregno, a.level5, a.level4, a.level3, a.level2, a.level1,
               a.who_name, a.level2_description, a.level3_description, a.level4_description
          FROM molecule_atc_classification mac
          JOIN atc_classification a ON a.level5 = mac.level5
         WHERE a.level1 = 'N'
         ORDER BY mac.molregno, a.level5
    """).fetchall()
    atc_molregnos = {r["molregno"] for r in atc_rows}
    common.log(f"  ATC N: {len(atc_rows)} rows on {len(atc_molregnos)} molecules")

    # ---- route B: scoped indications -------------------------------------
    ind_rows = conn.execute("""
        SELECT drugind_id, record_id, molregno, max_phase_for_ind,
               mesh_id, mesh_heading, efo_id, efo_term
          FROM drug_indication ORDER BY drugind_id
    """).fetchall()
    scope_mod.assert_covers(descriptors, {r["mesh_id"] for r in ind_rows if r["mesh_id"]})

    # The registry entries behind those phase annotations. ChEMBL files one
    # `ClinicalTrials` reference per drug_indication whose ref_id is a
    # comma-joined list of NCT ids, so this is a lookup and never a second
    # source of rows: an indication with no registered trial keeps its phase and
    # simply gets no link. Only the identifiers are read - ChEMBL's own ref_url
    # is a clinicaltrials.gov *search* over those same ids, and a link is built
    # from an identifier at display time rather than stored as somebody else's
    # query (invariant 15).
    trials = {}
    for r in conn.execute("SELECT drugind_id, ref_id FROM indication_refs"
                          " WHERE ref_type = 'ClinicalTrials' ORDER BY drugind_id"):
        ids = sorted({t.strip() for t in (r["ref_id"] or "").split(",") if t.strip()})
        if ids:
            trials[r["drugind_id"]] = tuple(ids)
    common.log(f"  indication_refs: {len(trials)} indications carry "
               f"{len({t for v in trials.values() for t in v})} distinct "
               f"ClinicalTrials ids")

    scoped, qualifying = [], []
    for r in ind_rows:
        d = descriptors.get(r["mesh_id"])
        if not d or not d.in_scope:
            continue
        scoped.append(r)
        phase = r["max_phase_for_ind"]
        if phase is not None and float(phase) >= min_phase:
            qualifying.append(r)
    ind_molregnos = {r["molregno"] for r in qualifying}
    common.log(f"  drug_indication: {len(ind_rows)} rows; {len(scoped)} in the adopted "
               f"scope; {len(qualifying)} at phase >= {min_phase} on "
               f"{len(ind_molregnos)} molecules")

    # ---- normalise identity to parents -----------------------------------
    seen = atc_molregnos | {r["molregno"] for r in scoped}
    seed_molregnos = {}
    for name, chembl_id in seed_pairs:
        row = conn.execute("SELECT molregno FROM molecule_dictionary WHERE chembl_id = ?",
                           (chembl_id,)).fetchone()
        if row is None:
            raise common.PolicyError(f"seed {name} ({chembl_id}) is not in {common.CHEMBL_RELEASE}")
        seed_molregnos[chembl_id] = row["molregno"]
    seen |= set(seed_molregnos.values())

    parent_of = _parents_for(conn, seen)
    atc_parents = {parent_of[m] for m in atc_molregnos}
    ind_parents = {parent_of[m] for m in ind_molregnos}
    seed_parents = {cid: parent_of[m] for cid, m in seed_molregnos.items()}

    # Seeds are retained whether or not they qualify clinically (D05), so the
    # catalogue is the clinical union plus every seed's parent.
    cohort = atc_parents | ind_parents
    catalogue = sorted(cohort | set(seed_parents.values()))
    common.log(f"  ATC-N parents {len(atc_parents)}, indication parents {len(ind_parents)}, "
               f"cohort union {len(cohort)}, catalogue with seeds {len(catalogue)}")

    families = _families_for(conn, set(catalogue))
    every = set(catalogue) | {m for f in families.values() for m in f}
    records = _records(conn, every)
    synonyms = _synonyms(conn, every)

    atc_by_mol = collections.defaultdict(list)
    for r in atc_rows:
        atc_by_mol[r["molregno"]].append(r)
    ind_by_mol = collections.defaultdict(list)
    for r in scoped:
        ind_by_mol[r["molregno"]].append(r)
    # Every disease, scoped or not, for the "N of M" the viewer states.
    all_ind_by_mol = collections.defaultdict(set)
    for r in ind_rows:
        if r["mesh_id"]:
            all_ind_by_mol[r["molregno"]].add(r["mesh_id"])

    approved_out = approved_out_of_scope(
        ind_rows, {k for k, d in descriptors.items() if d.in_scope})

    seed_by_parent = collections.defaultdict(list)
    for name, chembl_id in seed_pairs:
        seed_by_parent[seed_parents[chembl_id]].append((name, chembl_id))

    anomalies = {}
    for entry in policy["identity"]["anomaly_flags"]:
        for cid in entry["molecules"]:
            anomalies.setdefault(cid, []).append(entry["id"])

    members: dict[int, Member] = {}
    for p in catalogue:
        fam = sorted(families[p])
        rec = records.get(p, {})

        fam_atc = [(m, r) for m in fam for r in atc_by_mol.get(m, [])]
        fam_ind = [(m, r) for m in fam for r in ind_by_mol.get(m, [])]

        atc_l5 = tuple(sorted({r["level5"] for _, r in fam_atc}))
        atc_l3 = tuple(sorted({r["level3"] for _, r in fam_atc}))
        atc_flags = tuple(sorted({flagged[c] for c in atc_l3 if c in flagged}))

        qual, near = [], []
        reasons: list[str] = []
        for m, r in fam_ind:
            d = descriptors[r["mesh_id"]]
            phase = r["max_phase_for_ind"]
            entry = {
                "drugind_id": r["drugind_id"],
                "member_molregno": m,
                "member_chembl_id": records.get(m, {}).get("chembl_id"),
                "mesh_id": r["mesh_id"],
                "mesh_heading": r["mesh_heading"],
                "efo_id": r["efo_id"],
                "efo_term": r["efo_term"],
                "max_phase_for_ind": phase,
                "phase_label": common.phase_label(phase),
                "scope_reasons": list(d.scope_reasons),
                "trial_ids": trials.get(r["drugind_id"], ()),
            }
            if phase is not None and float(phase) >= min_phase:
                qual.append(entry)
                for sr in d.scope_reasons:
                    if sr not in reasons:
                        reasons.append(sr)
            else:
                near.append(entry)

        in_atc = p in atc_parents
        in_ind = p in ind_parents
        seeds_here = seed_by_parent.get(p, [])

        if in_atc and in_ind:
            admission = "both_routes"
        elif in_atc:
            admission = "route_atc_n"
        elif in_ind:
            admission = "route_indication"
        else:
            admission = "seed_only"

        exclusion = None
        if admission == "seed_only":
            if near:
                best = max(near, key=lambda e: (e["max_phase_for_ind"] is not None,
                                                e["max_phase_for_ind"] or -99))
                exclusion = (f"no ATC N code in family; best scoped indication is "
                             f"{best['mesh_heading']} at {best['phase_label']}, below "
                             f"the Approved/Phase 3 floor")
            elif fam_ind:
                exclusion = "no ATC N code in family; no scoped indication at any phase"
            else:
                exclusion = ("no ATC N code in family and no indication inside the "
                             "adopted scope")

        flags = []
        if rec.get("structure_type") == "NONE":
            flags.append("structure_unresolved")
        if any(records.get(m, {}).get("withdrawn_flag") for m in fam):
            flags.append("withdrawn_in_family")
        for cid in [rec.get("chembl_id")] + [records.get(m, {}).get("chembl_id") for m in fam]:
            for a in anomalies.get(cid, []):
                if a not in flags:
                    flags.append(a)

        members[p] = Member(
            parent_molregno=p,
            parent_chembl_id=rec.get("chembl_id"),
            pref_name=rec.get("pref_name"),
            molecule_type=rec.get("molecule_type"),
            structure_type=rec.get("structure_type"),
            max_phase=rec.get("max_phase"),
            first_approval=rec.get("first_approval"),
            withdrawn_any_family="withdrawn_in_family" in flags,
            route_atc_n=in_atc,
            route_indication=in_ind,
            is_seed=bool(seeds_here),
            seed_name=seeds_here[0][0] if seeds_here else None,
            admission_reason=admission,
            exclusion_reason=exclusion,
            atc_level5=atc_l5,
            atc_level3=atc_l3,
            atc_flags=atc_flags,
            scope_reasons=tuple(reasons),
            qualifying_indications=tuple(qual),
            near_miss_indications=tuple(near),
            n_indications_chembl=len(set().union(
                *(all_ind_by_mol.get(m, set()) for m in fam)) if fam else set()),
            approved_elsewhere=approved_for_family(approved_out, fam),
            family=tuple({
                "molregno": m,
                "chembl_id": records.get(m, {}).get("chembl_id"),
                "pref_name": records.get(m, {}).get("pref_name"),
                "molecule_type": records.get(m, {}).get("molecule_type"),
                "structure_type": records.get(m, {}).get("structure_type"),
                "max_phase": records.get(m, {}).get("max_phase"),
                "withdrawn_flag": records.get(m, {}).get("withdrawn_flag"),
                "is_parent": m == p,
                "carries_atc_n": bool(atc_by_mol.get(m)),
                "carries_qualifying_indication": any(
                    e["member_molregno"] == m for e in qual),
                "synonyms": synonyms.get(m, []),
                "seed_alias": next((n for n, c in seed_pairs
                                    if records.get(m, {}).get("chembl_id") == c), None),
            } for m in fam),
            identity_flags=tuple(flags),
        )

    arithmetic = {
        "atc_n_only": len(atc_parents - ind_parents),
        "indication_only": len(ind_parents - atc_parents),
        "both_routes": len(atc_parents & ind_parents),
        "cohort_union": len(cohort),
        "atc_n_total": len(atc_parents),
        "indication_total": len(ind_parents),
        "seeds_retained_outside_cohort": len(set(seed_parents.values()) - cohort),
        "catalogue_total": len(catalogue),
    }
    arithmetic["union_check"] = (arithmetic["atc_n_total"] + arithmetic["indication_total"]
                                 - arithmetic["both_routes"])
    arithmetic["arithmetic_holds"] = arithmetic["union_check"] == arithmetic["cohort_union"]
    if not arithmetic["arithmetic_holds"]:
        raise common.PolicyError(f"admission-route arithmetic does not hold: {arithmetic}")

    return {
        "members": members,
        "arithmetic": arithmetic,
        "seed_parents": seed_parents,
        "parent_of": parent_of,
        "families": families,
        "records": records,
        "scoped_indication_rows": len(scoped),
        "qualifying_indication_rows": len(qualifying),
    }
