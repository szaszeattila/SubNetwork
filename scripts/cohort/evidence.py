"""Assess cohort-1 evidence against ChEMBL 37 alone (decisions D07-D12).

The unit of assessment is a **claim**: one parent molecule, one target at the
identity ChEMBL asserts it, one role (curated, binding or functional). A claim
is assessed separately in each assignment basis, so direct human evidence and
broader (nonhuman, homologous, variant, ambiguous) evidence never pool.

Support is counted in **studies**, not in rows. Twenty measurements from one
paper are one study; a bulk deposit is one study however many rows it carries.
That is the rule that replaced measurement-count corroboration (D08).

Nothing here converts an unassigned or non-molecular observation into a
protein edge, distributes a family's evidence over its members, or lets a
bound masquerade as an exact value.
"""

from __future__ import annotations

import collections
import re

from . import common

ROLE_BY_ASSAY_TYPE = {"B": "binding", "F": "functional"}

# An explicit 10^<int> prefix in front of a supported concentration unit. The
# apostrophe exponent spellings ChEMBL also carries stay unresolved: guessing
# what "10'-6M" means is exactly the kind of recovered value this policy will
# not accept.
SCALED_UNIT = re.compile(r"^10\^(-?\d+)\s*(\S+)$")


class Assessor:
    def __init__(self, policy: dict):
        self.policy = policy
        cg = policy["claim_granularity"]
        self.endpoint_types = set(cg["endpoint_types"])

        mv = policy["measurement_validity"]
        self.known_bad = set(mv["documented_exclusions"]["CHEMBL_ASSAY_LINK_EXCLUSIONS"])
        self.mechanism_action_exclusions = {
            e["mec_id"]: e for e in
            mv["documented_exclusions"].get("CHEMBL_MECHANISM_ACTION_EXCLUSIONS", [])}
        self.bound_relations = set(mv["retained_as_bound"]["standard_relation_in"])
        self.organism_label = "organism-based format"

        uc = policy["unit_conversion"]
        self.conc_factors = dict(uc["concentration_factors_to_nM"])
        self.mass_factors = dict(uc["mass_conversion"]["mass_factors_to_ug_per_mL"])

        ab = policy["assignment_bases"]
        self.primary_classes = ab["primary_classes"]
        self.claimable = set(policy["target_identity"]["claimable_target_types"])

    # ---------------------------------------------------------------- units
    def normalise(self, relation, value, units, measured):
        """Return (value_nM, status, conversion dict).

        status is one of: exact, bound, conditional, unresolved.
        Only an exact relation is converted: a censored bound is a statement
        about a concentration that was never measured, and rescaling it does
        not make it one.
        """
        conv = {"kind": None, "factor": None, "basis": None, "note": None,
                "verified": None, "mwt": None, "form": None}

        if relation in self.bound_relations:
            nm = value if (units == "nM" and value is not None and value > 0) else None
            conv["note"] = ("bound reported as %s; preserved with its relation and "
                            "excluded from exact medians, exact-value threshold passes "
                            "and the replication rule" % relation)
            return nm, "bound", conv

        if relation != "=":
            conv["note"] = f"relation {relation!r} is not an exact measurement"
            return None, "unresolved", conv
        if value is None:
            conv["note"] = "no standard_value recorded"
            return None, "unresolved", conv

        unit_key, scale = units, 1.0
        if units:
            m = SCALED_UNIT.match(units.strip())
            if m:
                scale = 10 ** int(m.group(1))
                unit_key = m.group(2)

        if unit_key in self.conc_factors:
            nm = value * scale * self.conc_factors[unit_key]
            if nm <= 0:
                conv["note"] = "non-positive value after conversion"
                return None, "unresolved", conv
            conv.update(kind=("native" if units == "nM" else "concentration"),
                        factor=scale * self.conc_factors[unit_key],
                        basis="dimensionally explicit concentration unit",
                        verified=1)
            if units != "nM":
                conv["note"] = f"{value} {units} converted to {nm:g} nM"
            return nm, "exact", conv

        if unit_key in self.mass_factors:
            if not measured:
                conv["note"] = "measured record not resolved; mass basis unknown"
                return None, "unresolved", conv
            mwt, mtype, has_struct = (measured.get("full_mwt"),
                                      measured.get("molecule_type"),
                                      measured.get("has_structure"))
            if mtype != "Small molecule":
                conv["note"] = (f"measured record is {mtype!r}; small-molecule mass "
                                f"rules are not applied to it")
                return None, "unresolved", conv
            if not has_struct:
                conv["note"] = "measured record has no canonical structure"
                return None, "unresolved", conv
            if not mwt or mwt <= 0:
                conv["note"] = "measured record has no usable molecular weight"
                return None, "unresolved", conv
            ug_per_ml = value * scale * self.mass_factors[unit_key]
            nm = ug_per_ml * 1e6 / mwt
            if nm <= 0:
                conv["note"] = "non-positive value after conversion"
                return None, "unresolved", conv
            conv.update(
                kind="mass", factor=None, verified=0,
                mwt=mwt, form=measured.get("chembl_id"),
                basis=(f"mass basis taken from the measured record "
                       f"{measured.get('chembl_id')} (full_mwt {mwt:g} g/mol), not the "
                       f"parent freebase"),
                note=(f"{value} {units} -> {nm:g} nM using nM = ug/mL * 1e6 / MW. "
                      f"Conditional: the source record's weight does not establish "
                      f"whether the publication expressed mass as salt, freebase, "
                      f"hydrate or formulation."))
            return nm, "conditional", conv

        conv["note"] = f"units {units!r} are not dimensionally resolvable to a concentration"
        return None, "unresolved", conv

    # ----------------------------------------------------------- assignment
    def assignment(self, target, conf, rel, variant_id):
        """Classify one experimental assignment.

        Returns (basis, class_id, reason). basis is 'human_direct', 'broader'
        or None; None means the observation backs no claim at all and must
        never reach a named-protein edge.
        """
        if target is None:
            return None, "unassigned_or_non_molecular", "no target record"
        ttype, tax = target["target_type"], target["tax_id"]

        if ttype not in self.claimable:
            return None, "unassigned_or_non_molecular", (
                f"target type {ttype!r} is not one of the four claimable identities")
        if conf is not None and conf <= 3:
            return None, "unassigned_or_non_molecular", (
                f"assay confidence_score {conf} is a non-molecular or unassigned target")
        if rel in ("N", "S", "M", "U"):
            return None, "unassigned_or_non_molecular", (
                f"relationship_type {rel!r} is not a direct or homologous assignment")

        human = tax == 9606
        direct = rel == "D"
        no_variant = variant_id is None

        if human and direct and no_variant:
            for cls in self.primary_classes:
                want = cls["target_type"]
                types = want if isinstance(want, list) else [want]
                if ttype in types and conf == cls["confidence_score"]:
                    return "human_direct", cls["id"], "direct human assignment"

        if rel == "H":
            return "broader", "homologous", "homologous target assignment"
        if human and not no_variant:
            return "broader", "human_variant", (
                f"human target with variant_id {variant_id}; a variant result is not a "
                f"wild-type direct-binding assertion")
        if tax is None:
            return "broader", "unknown_species", "target species not recorded"
        if not human:
            return "broader", "nonhuman", f"nonhuman target organism ({target['organism']})"
        return "broader", "ambiguous_assignment", (
            f"human {ttype} at confidence_score {conf}, relationship_type {rel!r}: not one "
            f"of the adopted direct-assignment combinations")

    # ---------------------------------------------------------------- study
    @staticmethod
    def study(pmid, doi, patent_id, doc_chembl_id, doc_type):
        """Identify the original study, and how well its provenance resolves.

        doc_type is classified first, so a patent that happens to carry a
        PubMed id stays a patent rather than being counted as a deposit.
        """
        if doc_type == "PATENT":
            key = (f"patent:{patent_id}" if patent_id else
                   f"doc:{doc_chembl_id}" if doc_chembl_id else None)
            return key, "patent"
        if doc_type == "DATASET":
            key = (f"pmid:{pmid}" if pmid else f"doi:{doi}" if doi else
                   f"doc:{doc_chembl_id}" if doc_chembl_id else None)
            return key, "deposited_dataset"
        if doc_type == "PUBLICATION" and (pmid or doi):
            return (f"pmid:{pmid}" if pmid else f"doi:{doi}"), "publication"
        if patent_id:
            return f"patent:{patent_id}", "patent"
        if doc_chembl_id:
            return f"doc:{doc_chembl_id}", "unresolved"
        return None, "unresolved"


# --------------------------------------------------------------------------
# Streaming scan
# --------------------------------------------------------------------------

ACTIVITY_SQL = """
SELECT act.activity_id, act.molregno, act.standard_type, act.standard_relation,
       act.standard_value, act.standard_units, act.data_validity_comment,
       act.potential_duplicate, act.activity_comment,
       a.assay_id, a.chembl_id AS assay_chembl_id, a.description AS assay_description,
       a.assay_type, a.confidence_score, a.relationship_type, a.variant_id, a.tid,
       bao.label AS bao_label,
       d.chembl_id AS doc_chembl_id, d.pubmed_id, d.doi, d.patent_id, d.doc_type,
       d.year AS doc_year, d.journal AS doc_journal, d.title AS doc_title
  FROM activities act
  JOIN cohort_members c ON c.molregno = act.molregno
  JOIN assays a ON a.assay_id = act.assay_id
  LEFT JOIN bioassay_ontology bao ON bao.bao_id = a.bao_format
  LEFT JOIN docs d ON d.doc_id = act.doc_id
"""


def measured_records(conn, molregnos) -> dict[int, dict]:
    """The identity facts a mass conversion needs about the MEASURED record."""
    out = {}
    for chunk in common.chunked(molregnos):
        marks = ",".join("?" * len(chunk))
        q = (f"SELECT md.molregno, md.chembl_id, md.molecule_type, cp.full_mwt, "
             f"       (SELECT 1 FROM compound_structures cs "
             f"         WHERE cs.molregno = md.molregno AND cs.canonical_smiles IS NOT NULL) "
             f"       AS has_structure "
             f"  FROM molecule_dictionary md "
             f"  LEFT JOIN compound_properties cp ON cp.molregno = md.molregno "
             f" WHERE md.molregno IN ({marks})")
        for row in conn.execute(q, chunk):
            out[row["molregno"]] = dict(row)
    return out


def scan_activities(conn, assessor, member_to_parent, target_index, measured, emit):
    """Stream every activity row for the catalogue's compound families.

    Rows are gated in a fixed order and every rejection is counted with its
    reason. ``emit`` receives one observation dict per row that survives to
    the audit; rows dropped before that point are counted only, except the
    documented known-bad records, which are emitted individually so the
    exclusion can be inspected rather than taken on trust.
    """
    counts = collections.Counter()
    known_bad_rows = []
    scanned = 0

    for row in conn.execute(ACTIVITY_SQL):
        scanned += 1
        parent = member_to_parent[row["molregno"]]
        target = target_index.get(row["tid"])

        if row["assay_chembl_id"] in assessor.known_bad:
            counts["documented_exclusion"] += 1
            known_bad_rows.append({
                "activity_id": row["activity_id"],
                "parent_molregno": parent,
                "assay_chembl_id": row["assay_chembl_id"],
                "target_chembl_id": target["chembl_id"] if target else None,
                "reason": "documented_exclusion",
                "detail": ("known-bad upstream record on CHEMBL_ASSAY_LINK_EXCLUSIONS; "
                           "excluded on every ingestion path, never silently dropped"),
            })
            continue

        if row["assay_type"] not in ROLE_BY_ASSAY_TYPE:
            counts["assay_type_not_B_or_F"] += 1
            continue
        if row["standard_type"] not in assessor.endpoint_types:
            counts["standard_type_out_of_scope"] += 1
            continue

        # D11: organism-format observations leave active evidence entirely.
        # Applied to every assay type, not only functional assays: the release
        # also carries organism-format assays typed 'B', which the report's
        # functional-only gate let through as binding evidence. Counted after
        # the scope gates so the figure stays comparable with the report's.
        if row["bao_label"] == assessor.organism_label:
            counts["organism_based_format"] += 1
            counts[f"organism_based_format_{row['assay_type']}"] += 1
            continue

        role = ROLE_BY_ASSAY_TYPE[row["assay_type"]]
        value_nm, status, conv = assessor.normalise(
            row["standard_relation"], row["standard_value"], row["standard_units"],
            measured.get(row["molregno"]))
        basis, aclass, areason = assessor.assignment(
            target, row["confidence_score"], row["relationship_type"], row["variant_id"])
        skey, pclass = assessor.study(row["pubmed_id"], row["doi"], row["patent_id"],
                                      row["doc_chembl_id"], row["doc_type"])

        counts[f"kept_{status}"] += 1
        if basis is None:
            counts["no_claimable_assignment"] += 1

        emit({
            "activity_id": row["activity_id"],
            "parent_molregno": parent,
            "measured_molregno": row["molregno"],
            "measured_chembl_id": (measured.get(row["molregno"]) or {}).get("chembl_id"),
            "target_chembl_id": target["chembl_id"] if target else None,
            "tid": row["tid"],
            "role": role,
            "endpoint_class": f"{role}:{row['standard_type']}",
            "standard_type": row["standard_type"],
            "standard_relation": row["standard_relation"],
            "standard_value": row["standard_value"],
            "standard_units": row["standard_units"],
            "value_nm": value_nm,
            "value_status": status,
            "conversion_kind": conv["kind"],
            "conversion_factor": conv["factor"],
            "conversion_basis": conv["basis"],
            "conversion_note": conv["note"],
            "material_basis_verified": conv["verified"],
            "measured_full_mwt": conv["mwt"],
            "measured_form": conv["form"],
            "counted": 0,
            "basis": basis,
            "assignment_class": aclass,
            "assignment_reason": areason,
            "confidence_score": row["confidence_score"],
            "relationship_type": row["relationship_type"],
            "variant_id": row["variant_id"],
            "assay_chembl_id": row["assay_chembl_id"],
            "assay_description": row["assay_description"],
            "assay_type": row["assay_type"],
            "bao_label": row["bao_label"],
            "data_validity_comment": row["data_validity_comment"],
            "potential_duplicate": row["potential_duplicate"],
            "activity_comment": row["activity_comment"],
            "study_key": skey,
            "provenance_class": pclass,
            "pubmed_id": row["pubmed_id"],
            "doi": row["doi"],
            "patent_id": row["patent_id"],
            "doc_chembl_id": row["doc_chembl_id"],
            "doc_year": row["doc_year"],
            "doc_journal": row["doc_journal"],
            "doc_title": row["doc_title"],
            "claim_id": None,
            "exclusion_reason": None if basis else areason,
        })

    counts["scanned"] = scanned
    return counts, known_bad_rows


# --------------------------------------------------------------------------
# Curated mechanisms
# --------------------------------------------------------------------------

CURATED_SQL = """
SELECT dm.mec_id, dm.molregno, dm.tid, dm.action_type, dm.mechanism_of_action,
       dm.direct_interaction, dm.molecular_mechanism, dm.mechanism_comment,
       dm.selectivity_comment, dm.variant_id, dm.record_id,
       at.parent_type
  FROM drug_mechanism dm
  JOIN cohort_members c ON c.molregno = dm.molregno
  LEFT JOIN action_type at ON at.action_type = dm.action_type
"""


def load_curated(conn, member_to_parent, target_index):
    """Curated mechanisms, at the target and action level ChEMBL asserts."""
    refs = collections.defaultdict(list)
    for row in conn.execute("""
        SELECT r.mec_id, r.ref_type, r.ref_id, r.ref_url
          FROM mechanism_refs r
          JOIN drug_mechanism dm ON dm.mec_id = r.mec_id
          JOIN cohort_members c ON c.molregno = dm.molregno
         ORDER BY r.mecref_id
    """):
        refs[row["mec_id"]].append({
            "ref_type": row["ref_type"], "ref_id": row["ref_id"], "ref_url": row["ref_url"],
        })

    out = []
    for row in conn.execute(CURATED_SQL):
        parent = member_to_parent[row["molregno"]]
        target = target_index.get(row["tid"]) if row["tid"] is not None else None
        mrefs = refs.get(row["mec_id"], [])
        traceable = bool(mrefs) or bool((row["mechanism_comment"] or "").strip())

        claimable = bool(target and target["claimable"])
        if row["tid"] is None:
            tier, reason = "limited_or_unresolved", "curated_no_target_assigned"
        elif not claimable:
            # A curated mechanism filed against a target type outside the four
            # claimable identities is kept as a record with its reason, but it
            # never becomes an edge: D07 forbids manufacturing a named-protein
            # claim for a non-molecular or unassigned observation, and that
            # applies to curation as much as to measurement.
            tier, reason = "limited_or_unresolved", "curated_target_not_claimable"
        elif row["direct_interaction"] == 0:
            tier, reason = "limited_or_unresolved", "curated_indirect"
        elif not traceable:
            tier, reason = "limited_or_unresolved", "curated_untraceable"
        else:
            tier, reason = "supported", "curated_support"

        out.append({
            "mec_id": row["mec_id"],
            "parent_molregno": parent,
            "measured_molregno": row["molregno"],
            "target_chembl_id": target["chembl_id"] if claimable else None,
            "source_target_chembl_id": target["chembl_id"] if target else None,
            "target_type": target["target_type"] if target else None,
            "target_tax_id": target["tax_id"] if target else None,
            "action_type": row["action_type"],
            "action_parent_type": row["parent_type"],
            "mechanism_of_action": row["mechanism_of_action"],
            "direct_interaction": row["direct_interaction"],
            "molecular_mechanism": row["molecular_mechanism"],
            "mechanism_comment": row["mechanism_comment"],
            "selectivity_comment": row["selectivity_comment"],
            "variant_id": row["variant_id"],
            "n_refs": len(mrefs),
            "refs": mrefs,
            "tier": tier,
            "tier_reason": reason,
        })
    return out


def withhold_excluded_actions(mechanisms, exclusions):
    """Withhold the action of each mechanism on CHEMBL_MECHANISM_ACTION_EXCLUSIONS.

    The record is kept and its tier is untouched - curated support is the
    curator's assertion that the molecule acts at the target, and nothing here
    disputes that. Only the direction goes, because its own reference
    contradicts it. ChEMBL's word moves to `excluded_action_type` with the
    reason beside it (invariant 9: never a silent drop), and nothing is written
    in its place.

    Each entry names the action it expects. If ChEMBL's record no longer says
    it - corrected upstream, or changed to something else - the build stops
    rather than withholding an action nobody has looked at. An entry that
    matches no mechanism in the catalogue stops it too: a stale exclusion is
    one nobody is checking.
    """
    seen = set()
    for m in mechanisms:
        entry = exclusions.get(m["mec_id"])
        if entry is None:
            continue
        seen.add(m["mec_id"])
        if m["action_type"] != entry["action_type"]:
            raise ValueError(
                f"CHEMBL_MECHANISM_ACTION_EXCLUSIONS: mec_id {m['mec_id']} now reads "
                f"{m['action_type']!r}, not {entry['action_type']!r}. ChEMBL has changed "
                "the record; review it and remove or update the entry.")
        m["excluded_action_type"] = m["action_type"]
        m["action_exclusion"] = entry["reason"]
        m["action_type"] = None
        m["action_parent_type"] = None
    missing = sorted(set(exclusions) - seen)
    if missing:
        raise ValueError(
            f"CHEMBL_MECHANISM_ACTION_EXCLUSIONS: mec_id {missing} matched no curated "
            "mechanism in the catalogue; remove the stale entry.")
    return mechanisms


def curated_basis(mech, primary_ids=("human_single_protein", "human_complex", "human_family")):
    """Which basis a curated claim belongs in.

    Curation is an assertion about a target, not an experiment, so there is no
    confidence score or relationship type to test. The species of the asserted
    target is what separates the bases; a variant-specific mechanism stays in
    the broader layer rather than becoming a wild-type claim.
    """
    if mech["target_chembl_id"] is None:
        # No claimable target: the mechanism is retained as a record with its
        # reason and produces no edge in any basis or filter state.
        return None
    if mech["target_tax_id"] == 9606 and mech["variant_id"] is None:
        return "human_direct"
    return "broader"


# --------------------------------------------------------------------------
# Claim aggregation
# --------------------------------------------------------------------------

def aggregate_claims(observations, curated, policy):
    """Build claims from observations and curated mechanisms.

    Keyed (parent, target, role, basis). Endpoint classes are summarised
    separately inside each claim and never pooled with one another; support is
    counted in distinct publication-class studies inside one endpoint class.
    """
    claims: dict[tuple, dict] = {}

    # ---- experimental roles ---------------------------------------------
    grouped = collections.defaultdict(list)
    for obs in observations:
        if obs["basis"] is None or obs["target_chembl_id"] is None:
            continue
        grouped[(obs["parent_molregno"], obs["target_chembl_id"],
                 obs["role"], obs["basis"])].append(obs)

    for key, rows in grouped.items():
        parent, target, role, basis = key
        endpoints = {}
        by_endpoint = collections.defaultdict(list)
        for r in rows:
            by_endpoint[r["endpoint_class"]].append(r)

        n_exact = n_bounds = n_conditional = n_unresolved = 0
        supported_endpoint = None
        multiple_study = False
        all_studies, all_pub_studies = set(), set()
        patents = datasets = 0
        # The studies that hold an exact value, by provenance class. A
        # Preliminary claim's reason names these and nothing else: a paper
        # that reported only a bound, or a deposit with no value, is listed
        # with the claim but is not where its values come from.
        exact_studies = collections.defaultdict(set)
        conflict_dispersion = False
        conflict_detail = []

        for ec, ers in sorted(by_endpoint.items()):
            exact = [r for r in ers if r["value_status"] == "exact"]
            for r in ers:
                if r["value_status"] == "exact":
                    n_exact += 1
                elif r["value_status"] == "bound":
                    n_bounds += 1
                elif r["value_status"] == "conditional":
                    n_conditional += 1
                else:
                    n_unresolved += 1

            # Only exact values are counted into a median, and `counted` is
            # written back onto the row so the stored count and the displayed
            # summary cannot disagree.
            for r in exact:
                r["counted"] = 1

            studies = collections.defaultdict(list)
            for r in ers:
                if r["study_key"]:
                    studies[(r["study_key"], r["provenance_class"])].append(r)
                    all_studies.add(r["study_key"])
                    if r["provenance_class"] == "publication":
                        all_pub_studies.add(r["study_key"])
                    elif r["provenance_class"] == "patent":
                        patents += 1
                    elif r["provenance_class"] == "deposited_dataset":
                        datasets += 1

            # Replication is counted only over exact values, only in publication
            # -class studies, and only inside this one endpoint class.
            pub_with_exact = {r["study_key"] for r in exact
                              if r["provenance_class"] == "publication" and r["study_key"]}
            for r in exact:
                if r["study_key"]:
                    exact_studies[r["provenance_class"]].add(r["study_key"])
            ec_supported = len(pub_with_exact) >= 2
            if ec_supported:
                multiple_study = True
                if supported_endpoint is None:
                    supported_endpoint = ec

            values = [r["value_nm"] for r in exact if r["value_nm"]]
            spread = common.log_spread(values) if len(values) > 1 else 0.0
            if ec_supported and spread > 2:
                conflict_dispersion = True
                conflict_detail.append(
                    f"{ec}: values span {10 ** spread:.0f}-fold across "
                    f"{len(pub_with_exact)} studies")

            endpoints[ec] = {
                "endpoint_class": ec,
                "n_measurements": len(exact),
                "n_rows": len(ers),
                "median_nm": common.log_median(values) if values else None,
                "min_nm": min(values) if values else None,
                "max_nm": max(values) if values else None,
                "n_studies": len(studies),
                "n_publications": len(pub_with_exact),
                "supported": 1 if ec_supported else 0,
                "log_spread": spread,
                "studies": [
                    {"study_key": sk, "provenance_class": pc,
                     "n_measurements": sum(1 for r in rs if r["value_status"] == "exact"),
                     "n_rows": len(rs),
                     "pubmed_id": rs[0]["pubmed_id"], "doi": rs[0]["doi"],
                     "patent_id": rs[0]["patent_id"], "doc_chembl_id": rs[0]["doc_chembl_id"],
                     "year": rs[0]["doc_year"], "journal": rs[0]["doc_journal"],
                     "title": rs[0]["doc_title"]}
                    for (sk, pc), rs in sorted(studies.items())
                ],
            }

        # A document with no PubMed id, DOI or patent number is not an
        # identifiable study, so it alone never makes a claim Preliminary.
        exact_pubs = exact_studies["publication"]
        exact_patents = exact_studies["patent"]
        exact_datasets = exact_studies["deposited_dataset"]
        if multiple_study:
            tier, reason = "supported", "multiple_study_support"
        elif exact_pubs or exact_patents or exact_datasets:
            tier = "preliminary"
            if exact_pubs:
                reason = ("multiple_publications_split_across_endpoint_classes"
                          if len(exact_pubs) >= 2 else "one_publication")
            elif exact_datasets and not exact_patents:
                reason = "deposited_datasets_only"
            elif exact_patents and not exact_datasets:
                reason = "patents_only"
            else:
                reason = "patents_and_deposits_only"
        else:
            tier = "limited_or_unresolved"
            if n_exact:
                reason = "unresolved_study_provenance"
            elif n_conditional and not n_exact:
                reason = "conditional_conversion_only"
            elif n_bounds and not n_exact:
                reason = "censored_only"
            elif n_unresolved and not n_exact:
                reason = "invalid_units_only"
            else:
                reason = "censored_only"

        claims[key] = {
            "parent_molregno": parent, "target_chembl_id": target,
            "claim_role": role, "basis": basis,
            "tier": tier, "tier_reason": reason,
            "curated_support": 0,
            "multiple_study_support": 1 if multiple_study else 0,
            "supporting_endpoint_class": supported_endpoint,
            "n_rows": len(rows),
            "n_measurements": n_exact, "n_bounds": n_bounds,
            "n_conditional": n_conditional, "n_unresolved": n_unresolved,
            "n_studies": len(all_studies), "n_publications": len(all_pub_studies),
            "n_patents": patents, "n_datasets": datasets,
            "action_type": None, "mechanism_of_action": None, "direct_interaction": None,
            "conflict_action": 0,
            "conflict_dispersion": 1 if conflict_dispersion else 0,
            "conflict_detail": "; ".join(conflict_detail) or None,
            "assignment_classes": sorted({r["assignment_class"] for r in rows}),
            "endpoints": endpoints,
            "rows": rows,
        }

    # ---- curated role ----------------------------------------------------
    cur_grouped = collections.defaultdict(list)
    for mech in curated:
        basis = curated_basis(mech)
        if basis is None:
            continue
        cur_grouped[(mech["parent_molregno"], mech["target_chembl_id"],
                     "curated", basis)].append(mech)

    for key, mechs in cur_grouped.items():
        parent, target, role, basis = key
        supported = [m for m in mechs if m["tier"] == "supported"]
        chosen = supported or mechs
        # Opposing curated directions are both preserved; neither is chosen by
        # row order, and their disagreement never reads as agreement.
        parents_types = {m["action_parent_type"] for m in mechs if m["action_parent_type"]}
        conflict = int({"POSITIVE MODULATOR", "NEGATIVE MODULATOR"} <= parents_types)
        actions = sorted({m["action_type"] for m in mechs if m["action_type"]})
        # A withheld action (CHEMBL_MECHANISM_ACTION_EXCLUSIONS) takes ChEMBL's
        # sentence with it, since the sentence names the same direction; both
        # stay on the mechanism record, and the claim says why.
        withheld = [m for m in mechs if m.get("excluded_action_type")]
        mechanism_text = next((m["mechanism_of_action"] for m in chosen
                               if not m.get("excluded_action_type")), None)

        claims[key] = {
            "parent_molregno": parent, "target_chembl_id": target,
            "claim_role": "curated", "basis": basis,
            "tier": "supported" if supported else "limited_or_unresolved",
            "tier_reason": ("curated_support" if supported else chosen[0]["tier_reason"]),
            "curated_support": 1 if supported else 0,
            "multiple_study_support": 0,
            "supporting_endpoint_class": None,
            "n_rows": len(mechs),
            "n_measurements": 0, "n_bounds": 0, "n_conditional": 0, "n_unresolved": 0,
            "n_studies": 0, "n_publications": 0, "n_patents": 0, "n_datasets": 0,
            "action_type": " / ".join(actions) if actions else None,
            "mechanism_of_action": mechanism_text,
            "direct_interaction": chosen[0]["direct_interaction"],
            "action_exclusion": "; ".join(
                f"ChEMBL files this as {m['excluded_action_type']} "
                f"(\"{m['mechanism_of_action']}\", mechanism {m['mec_id']}), "
                f"withheld as a known error: {m['action_exclusion']}"
                for m in withheld) or None,
            "conflict_action": conflict,
            "conflict_dispersion": 0,
            "conflict_detail": (
                "curated mechanisms assert opposing directions: "
                + "; ".join(f"{m['action_type']} ({m['mechanism_of_action']})"
                            for m in mechs if m["action_type"])
            ) if conflict else None,
            "assignment_classes": ["curated"],
            "endpoints": {},
            "rows": [],
            "mechanisms": mechs,
        }

    return claims


def similarity_weights(policy):
    return sim["target_weight"], sim["evidence_weight"]
