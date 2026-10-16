"""Export the cohort database to the files the offline viewer loads.

    viz/graph.data.js       catalogue, targets and drawable claims (COHORT_DATA)
    viz/gtopdb.data.js      everything GtoPdb contributes (COHORT_GTOPDB): its
                            actions, its `gtopdb`-role claims, and the entry
                            statuses those claims change
    viz/evidence/<id>.js    one molecule's observation rows, studies, curated
                            mechanism detail and retained non-drawable claims,
                            loaded on demand

All are plain ``<script src>`` files, so the page still opens from ``file://``
with no server and no build step. A shard is fetched by injecting a script tag
when a reader first opens evidence for that molecule; classic script loads from
``file://`` are permitted, which was checked in Chrome before this format was
chosen because the whole offline workflow depends on it.

Four measured decisions shape the encoding, each made after writing the naive
version and looking at what it cost:

  * **Evidence is sharded per molecule.** Whole-catalogue evidence measured
    57 MB as one file. Nothing here needs all of it at once - a reader opens
    one molecule at a time - and the startup file drops to a few megabytes.
  * **A study is stored once per shard.** 210,157 observations resolve to
    14,548 distinct studies. Repeating a paper's title, DOI and journal on
    every measurement row was half the size, and it is the same conflation
    invariants 13 and 14 exist to prevent, arriving in the export.
  * **Only drawable claims ship at startup.** A limited_or_unresolved claim
    cannot be drawn in any filter state; it is a retained observation with a
    reason. Its count travels with the catalogue so a gap can state itself,
    and its rows travel in the molecule's shard.
  * **Each file interns its own strings.** The 42,323 distinct assay
    descriptions belong to observations, so they stay out of the startup file.

**GtoPdb travels in its own file** because it is licensed differently: its
database is ODbL and its contents CC BY-SA 4.0, while ChEMBL is CC BY-SA 3.0,
and no published compatibility joins the ODbL to CC BY-SA. Kept apart, each
file carries one set of terms and the page combines them only when it draws.
So graph.data.js holds nothing of GtoPdb's - not its claims, and not the
evidence_status or Supported counts those claims change, which it states from
ChEMBL's claims alone and the GtoPdb file corrects - and without that file the
page is the ChEMBL-only page, consistent with itself.

Row layouts are declared here and re-declared in each payload's ``fields``, so
the viewer reads columns by name and a field added on one side cannot silently
shift every column on the other.
"""

from __future__ import annotations

import collections
import datetime
import json
import shutil
import sqlite3

from . import build, common

MOLECULE_FIELDS = [
    "id", "chembl_id", "name", "molecule_type", "in_cohort", "is_seed",
    "route_atc_n", "route_indication", "admission_reason", "evidence_status",
    "scope_reasons", "n_claims_supported", "n_claims_preliminary", "n_claims_limited",
    "n_observations", "structure_type", "max_phase", "first_approval",
    "molecular_formula", "molecular_weight", "atc_level5", "atc_flags",
    "identity_flags", "seed_name", "gap_reason", "exclusion_reason", "smiles",
    "inchikey", "wikipedia_url", "n_indications_chembl", "synonyms", "aliases",
    "approved_elsewhere", "trial_sites", "trial_countries",
]

# Reviewed common names, keyed by ChEMBL ID, carried over from the legacy
# export's map and extended only where ChEMBL's own synonym list does not
# already answer the search.
#
# ChEMBL 37's synonyms are better than the legacy seed set suggested: Tylenol,
# Xanax, Viagra, Ambien, Marinol and Epidiolex all already find their molecule
# here. What they do not carry is the short form a non-expert actually types.
# "THC" appears only inside ".delta.1-thc" and "Delta-9-thc", so the query lands
# on whichever of three substring matches happens to sort first; "ASA" and
# "L-DOPA" appear nowhere at all.
#
# An entry here is a name a person would search for, checked against ChEMBL 37's
# own synonyms for that molecule. Combination products are excluded on purpose -
# Adderall is a mixed-salts formulation and not a name for amphetamine - and so
# are the names of other isomers. This changes search only: it renames no node,
# and it reaches neither source matching nor evidence. Add reviewed names here
# and re-export; no rebuild is needed.
MOLECULE_ALIASES = {
    "CHEMBL465": ["THC", "Tetrahydrocannabinol", "Delta-9-THC",
                  "Delta 9 THC", "Δ9-THC", "Delta-9-tetrahydrocannabinol",
                  "Marinol", "Syndros"],
    "CHEMBL190461": ["CBD", "Epidiolex", "Epidyolex"],
    "CHEMBL113": ["Guaranine", "NoDoz", "Vivarin"],
    "CHEMBL431770": ["Nourianz"],
    "CHEMBL799": ["Pletal"],
    "CHEMBL628": ["Oxpentifylline", "Trental"],
    "CHEMBL636": ["Exelon"],
    "CHEMBL972": ["Emsam"],
    "CHEMBL54": ["Haldol"],
    "CHEMBL42": ["Clozaril", "Fazaclo", "Versacloz"],
    "CHEMBL741": ["Lamictal"],
    "CHEMBL932": ["Persantine"],
    "CHEMBL1520": ["Levitra", "Vivanza"],
    "CHEMBL659": ["Galanthamine", "Reminyl"],
    # Short forms ChEMBL 37 has no searchable spelling of.
    "CHEMBL25": ["ASA"],
    "CHEMBL1009": ["L-DOPA", "L-dopa"],
}

# human_orthologue last: most targets are human or unmatched, and a trailing
# null costs nothing on the wire.
TARGET_FIELDS = [
    "chembl_id", "name", "target_type", "organism", "tax_id", "n_components",
    "wikipedia_url", "components", "human_orthologue",
]

# Sparse fields last: an experimental claim carries no action and no mechanism,
# and a limited claim carries no conflict either. The trailing run of nulls is
# dropped on write, so this order is part of the encoding.
CLAIM_FIELDS = [
    "id", "molecule", "target", "role", "basis", "tier", "tier_reason",
    "curated_support", "multiple_study_support", "n_measurements", "n_studies",
    "n_publications", "endpoints", "n_rows", "n_bounds", "n_conditional",
    "n_unresolved", "n_patents", "n_datasets", "assignment_classes",
    "supporting_endpoint_class", "action_type", "direct_interaction",
    "conflict_action", "conflict_dispersion", "mechanism_of_action", "conflict_detail",
    "action_exclusion",
]

ENDPOINT_FIELDS = [
    "endpoint_class", "n_measurements", "median_nm", "n_studies", "n_publications",
    "supported", "n_rows", "min_nm", "max_nm", "log_spread",
]

OBSERVATION_FIELDS = [
    "activity_id", "claim_id", "molecule", "target", "role", "endpoint_class",
    "standard_type", "standard_relation", "standard_value", "standard_units",
    "value_nm", "value_status", "counted", "study", "assay_chembl_id",
    "assay_description", "basis", "assignment_class", "confidence_score",
    "relationship_type", "conversion_kind", "conversion_note",
    "material_basis_verified", "measured_full_mwt", "measured_form",
    "data_validity_comment", "potential_duplicate", "activity_comment",
    "assignment_reason", "exclusion_reason", "measured_chembl_id", "variant_id",
    "assay_type",
]

STUDY_FIELDS = [
    "study_key", "provenance_class", "pubmed_id", "year", "journal", "title",
    "doi", "patent_id", "doc_chembl_id",
]

CLAIM_STUDY_FIELDS = ["claim_id", "endpoint_class", "study", "n_measurements", "n_rows"]

CURATED_FIELDS = [
    "claim_id", "mec_id", "action_type", "mechanism_of_action", "direct_interaction",
    "n_refs", "tier", "tier_reason", "refs", "mechanism_comment", "selectivity_comment",
    "excluded_action_type", "action_exclusion",
]

# GtoPdb's curated action at a pair the catalogue already has a claim for, from
# scripts/resolve_cohort_gtopdb_actions.py. A direction only: the viewer reads
# action_type (ChEMBL's vocabulary) wherever it reads a curated direction, and
# shows GtoPdb's own words beside it. Never an edge, never a tier.
GTOPDB_FIELDS = [
    "molecule", "target", "action_type", "gtp_type", "gtp_action", "primary_target",
    "endogenous", "gtp_ligand_id", "gtp_target_id", "selectivity", "pubmed_ids",
]

# What each file is, for anyone who finds one on its own, written as a header
# comment and as the payload's `licence`. Share-alike asks more than "stays
# under its terms": an adaptation is licensed by whoever made it, under the
# same licence, saying that it was changed and linking the licence text
# (docs/HOSTING-REVIEW.md, second pass). The evidence shards carry it too.
LOCAL_ONLY_MANIFEST_KEYS = frozenset({"chembl_path"})
GRAPH_NOTICE = (
    "SubNetwork, by Attila Szabo: adapted from ChEMBL 37 (EMBL-EBI),",
    "https://www.ebi.ac.uk/chembl/ - changes were made: records filtered, folded",
    "onto parent molecules, summarised into claims and scored. This adaptation is",
    "licensed under CC BY-SA 3.0, https://creativecommons.org/licenses/by-sa/3.0/",
    "Material from the other sources keeps their terms, listed in NOTICE.txt.",
    "It holds no GtoPdb data; that is in gtopdb.data.js.",
)
GRAPH_LICENCE = " ".join(GRAPH_NOTICE)
GTOPDB_NOTICE = (
    "Contains information from the IUPHAR/BPS Guide to PHARMACOLOGY (GtoPdb),",
    "https://www.guidetopharmacology.org/ - which is made available here under the",
    "Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/",
    "Its contents are under CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/",
    "SubNetwork, by Attila Szabo, adapted them: matched to ChEMBL's records and its",
    "action words. This adapted database is under the ODbL 1.0, its contents CC BY-SA 4.0.",
)
GTOPDB_LICENCE = " ".join(GTOPDB_NOTICE)
GTOPDB_ROLE = "gtopdb"

INTERNED = {
    "molecule_type", "structure_type", "admission_reason", "scope_reasons",
    "atc_flags", "identity_flags", "evidence_status", "gap_reason", "target_type",
    "organism", "role", "basis", "tier", "tier_reason", "supporting_endpoint_class",
    "action_type", "assignment_classes", "endpoint_class", "standard_type",
    "standard_relation", "standard_units", "value_status", "conversion_kind",
    "assignment_class", "assignment_reason", "relationship_type", "assay_type",
    "data_validity_comment", "provenance_class", "journal", "exclusion_reason",
    "measured_form", "name", "mechanism_of_action", "assay_description",
    "conversion_note", "activity_comment", "phase_label", "mesh_heading",
    "seed_name", "note", "description", "gene_symbol", "mechanism_comment",
    "selectivity_comment", "gtp_type", "gtp_action", "selectivity",
    "trial_sites", "trial_countries",
}

# The class sources the page offers: USAN/INN name stems, the MeSH
# pharmacological actions scripts/resolve_cohort_pharm_actions.py backfills, and
# the MeSH structure classes scripts/resolve_cohort_mesh_structure.py does.
# molecule_classes also holds every ATC code, which stays in the database for
# analysis (the similarity harness's answer key) and is not shipped to the page.
SURFACED_CLASS_SOURCES = ("usan", "mesh_pa", "mesh_struct")

# The two tiers any filter state can put on the canvas. limited_or_unresolved
# is never drawable by design: it is the tier for observations that exist and
# do not meet the rules, and drawing one would be the manufactured edge D13
# forbids.
DRAWABLE_TIERS = ("supported", "preliminary")

# A trial's start and end, from scripts/resolve_cohort_trials.py (schema
# version 3). The page shows years, so years travel - the full dates stay in
# the database - plus which of the two the registry gives only as a plan.
TRIAL_DATE_COLUMNS = ("start_date", "start_date_type",
                      "completion_date", "completion_date_type")
TRIAL_START_PLANNED = 1
TRIAL_END_PLANNED = 2


def _trial_years(r):
    """[start year, end year, planned] for one trial_status row, the trailing
    run of empties dropped. `planned` sets TRIAL_START_PLANNED or
    TRIAL_END_PLANNED where the registry types that date ESTIMATED; an untyped
    date is the one it reported (it typed none before 2017), not a plan. A
    planned end is often one long past, on a trial whose status is UNKNOWN,
    and without the flag it would read as the year the trial ended."""
    def year(d):
        return int(d[:4]) if d and d[:4].isdigit() else None
    start, end = year(r["start_date"]), year(r["completion_date"])
    planned = ((TRIAL_START_PLANNED if start and r["start_date_type"] == "ESTIMATED" else 0) |
               (TRIAL_END_PLANNED if end and r["completion_date_type"] == "ESTIMATED" else 0))
    out = [start, end, planned or None]
    while out and out[-1] is None:
        out.pop()
    return out


# Where one trial had sites (schema version 4), printed beside its NCT id
# (2026-10-15, at the user's request: trimipramine's indications said Germany
# and not which trial). It travels after the years, at a fixed index, so the
# fields before it are padded rather than dropped; a null there is the
# registry listing no site, and a row too short to reach it was never asked.
TRIAL_COUNTRIES_INDEX = 7


def _with_trial_countries(row, countries, strings):
    """row, padded to TRIAL_COUNTRIES_INDEX, with the trial's '|'-joined site
    countries appended interned, or None where the registry lists none."""
    return (row + [None] * (TRIAL_COUNTRIES_INDEX - len(row)) +
            [strings.intern(countries) if countries else None])


# Where a molecule's in-scope trials ran, for the page's trial-sites filter.
# A trial counts only where the registry's own phase for it is Phase 1 or
# later - the floor D21 sets for an indication, read here off the trial,
# because an indication's phase can come from a US Phase 3 while the trial
# abroad was Early Phase 1. Every in-scope indication's trials are read, not
# only the qualifying ones, so a member admitted by ATC N still says where its
# brain trials ran.
TRIAL_SITE_PHASES = frozenset({"PHASE1", "PHASE2", "PHASE3", "PHASE4"})
HOME_COUNTRY = "United States"


def trial_sites(trials) -> tuple[str | None, str | None]:
    """(sites, countries outside the US) for one molecule, from its in-scope
    trials as (phases, countries) pairs of trial_status's '|'-joined columns.

    sites is "us", "both" or "elsewhere" by where the Phase 1+ trials list a
    site; "unstated" where there are Phase 1+ trials and none lists one; None
    where there is no Phase 1+ in-scope trial at all - an ATC N member, an
    approval resting on a label, a trial not fetched. Nothing here is matched
    on a name: every trial is one ChEMBL cites, read by its NCT id."""
    us = False
    abroad: set[str] = set()
    counted = False
    for phases, countries in trials:
        if not phases or not TRIAL_SITE_PHASES & set(phases.split("|")):
            continue
        counted = True
        for c in (countries or "").split("|"):
            if c == HOME_COUNTRY:
                us = True
            elif c:
                abroad.add(c)
    if not counted:
        return None, None
    sites = ("both" if us and abroad else "us" if us
             else "elsewhere" if abroad else "unstated")
    return sites, "|".join(sorted(abroad)) or None


def _trial_sites_by_molecule(db) -> dict[int, tuple[str | None, str | None]]:
    """trial_sites() for every molecule, or {} where the trial backfill has
    not stored countries (it is a backfill; a build without it says nothing
    about where any trial ran, rather than calling them all unstated)."""
    has = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                     " AND name = 'trial_status'").fetchone()
    if not has or "countries" not in {c[1] for c in db.execute("PRAGMA table_info(trial_status)")}:
        return {}
    status = {r["nct_id"]: (r["phases"], r["countries"]) for r in db.execute(
        "SELECT nct_id, phases, countries FROM trial_status WHERE schema_version >= 4")}
    per_molecule = collections.defaultdict(dict)
    for r in db.execute("SELECT parent_molregno, trial_ids FROM molecule_indications"
                        " WHERE trial_ids IS NOT NULL"):
        for nct in r["trial_ids"].split("|"):
            if nct in status:
                per_molecule[r["parent_molregno"]][nct] = status[nct]
    return {m: trial_sites(t.values()) for m, t in per_molecule.items()}


class Strings:
    """One file's string dictionary, so repeated text is stored once."""

    def __init__(self):
        self.values: list[str] = []
        self.index: dict[str, int] = {}

    def intern(self, value):
        if value is None:
            return None
        value = str(value)
        i = self.index.get(value)
        if i is None:
            i = len(self.values)
            self.values.append(value)
            self.index[value] = i
        return i


def _row(record, fields, strings):
    """Encode one record positionally, dropping the trailing run of nulls.

    The viewer reads a short row as "everything after this is null", which is
    why the field order is declared and shipped rather than inferred.
    """
    out = []
    for f in fields:
        v = record.get(f)
        out.append(strings.intern(v) if (f in INTERNED and v is not None) else v)
    while out and out[-1] is None:
        out.pop()
    return out


def _dump(path, name, payload, notice=()) -> int:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("// Generated by scripts/export_cohort.py - do not edit.\n")
        for line in notice:
            fh.write(f"// {line}\n")
        fh.write(f"const {name} = ")
        json.dump(payload, fh, separators=(",", ":"), allow_nan=False)
        fh.write(";\n")
    return path.stat().st_size


def _dump_shard(shard_dir, molecule_id, payload) -> int:
    """Write one molecule's evidence shard.

    A shard calls ``registerEvidence`` rather than declaring a const, so the
    viewer can inject it with a script tag and know it arrived from the call
    itself instead of polling a global.
    """
    shard_dir.mkdir(parents=True, exist_ok=True)
    path = shard_dir / f"{molecule_id}.js"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("// Generated by scripts/export_cohort.py - do not edit.\n")
        for line in GRAPH_NOTICE:
            fh.write(f"// {line}\n")
        fh.write("registerEvidence(")
        json.dump(payload, fh, separators=(",", ":"), allow_nan=False)
        fh.write(");\n")
    return path.stat().st_size


def _clear_shards(shard_dir) -> int:
    """Remove shards from a previous build.

    A rerun removes stale derived claims rather than only adding new ones: a
    molecule that leaves the catalogue must not leave its old evidence behind
    for a later search hit to load.
    """
    if not shard_dir.exists():
        return 0
    n = 0
    for old in shard_dir.glob("*.js"):
        old.unlink()
        n += 1
    return n


def _backup(out_dir) -> list[str]:
    """Copy the existing startup export aside before replacing it."""
    made = []
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    for name in ("graph.data.js", "gtopdb.data.js"):
        src = out_dir / name
        if src.exists():
            common.VIZ_BACKUPS.mkdir(parents=True, exist_ok=True)
            dest = common.VIZ_BACKUPS / f"{name}.{stamp}"
            shutil.copy2(src, dest)
            made.append(str(dest.relative_to(common.ROOT)))
    return made


def export(db_path=None, out_dir=None, backup=True) -> dict:
    db_path = db_path or common.COHORT_DB
    out_dir = out_dir or common.VIZ
    if not db_path.exists():
        raise common.PolicyError(
            f"no cohort database at {db_path}. Run scripts/build_cohort.py first.")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    cat_s = Strings()
    # The manifest travels as the payload's `meta`, less what only this machine
    # needs: where ChEMBL lives on disk is a filesystem layout, not provenance,
    # and the payload is served publicly (docs/HOSTING-REVIEW.md).
    manifest = {r["key"]: r["value"]
                for r in db.execute("SELECT key, value FROM build_manifest")
                if r["key"] not in LOCAL_ONLY_MANIFEST_KEYS}

    # Counts and statuses are ChEMBL's alone; the GtoPdb file corrects them.
    claim_counts = collections.defaultdict(collections.Counter)
    chembl_tiers = collections.defaultdict(list)
    all_tiers = collections.defaultdict(list)
    for r in db.execute("SELECT parent_molregno, claim_role, basis, tier FROM claims"):
        all_tiers[r["parent_molregno"]].append((r["basis"], r["tier"]))
        if r["claim_role"] != GTOPDB_ROLE:
            chembl_tiers[r["parent_molregno"]].append((r["basis"], r["tier"]))
            claim_counts[r["parent_molregno"]][r["tier"]] += 1
    obs_counts = {r["parent_molregno"]: r["n"] for r in db.execute(
        "SELECT parent_molregno, COUNT(*) n FROM observations GROUP BY 1")}

    # ---- molecules -------------------------------------------------------
    synonyms = collections.defaultdict(list)
    for r in db.execute("SELECT parent_molregno, synonym FROM molecule_synonyms"
                        " ORDER BY parent_molregno, synonym"):
        synonyms[r["parent_molregno"]].append(r["synonym"])
    for r in db.execute("SELECT parent_molregno, chembl_id, seed_alias FROM molecule_forms"
                        " WHERE seed_alias IS NOT NULL ORDER BY parent_molregno"):
        # A seed stays findable by the id it was seeded under even though the
        # catalogue row is its parent: theophylline was seeded as
        # CHEMBL1355736 and lives here as CHEMBL190.
        synonyms[r["parent_molregno"]].append(r["chembl_id"])
        if r["seed_alias"]:
            synonyms[r["parent_molregno"]].append(r["seed_alias"])

    molecules, molecule_ids = [], []
    status_with_gtopdb = {}
    sites = _trial_sites_by_molecule(db)
    for r in db.execute("SELECT * FROM molecules ORDER BY parent_molregno"):
        rec = dict(r)
        mid = rec.pop("parent_molregno")
        rec["id"] = mid
        rec["name"] = rec.pop("pref_name") or rec["chembl_id"]
        stored = (rec["evidence_status"], rec["gap_reason"])
        if build.evidence_status_of(all_tiers.get(mid, [])) != stored:
            raise common.PolicyError(
                f"molecule {mid}: stored evidence_status {stored} is not what"
                " build.evidence_status_of gives its claims; the two rules have drifted")
        chembl_status = build.evidence_status_of(chembl_tiers.get(mid, []))
        if chembl_status != stored:
            status_with_gtopdb[str(mid)] = list(stored)
        rec["evidence_status"], rec["gap_reason"] = chembl_status
        counts = claim_counts.get(mid, {})
        rec["n_claims_supported"] = counts.get("supported", 0)
        rec["n_claims_preliminary"] = counts.get("preliminary", 0)
        rec["n_claims_limited"] = counts.get("limited_or_unresolved", 0)
        rec["n_observations"] = obs_counts.get(mid, 0)
        names = [n for n in dict.fromkeys(synonyms.get(mid, []))
                 if n and n != rec["chembl_id"]
                 and n.lower() != (rec["name"] or "").lower()]
        rec["synonyms"] = [cat_s.intern(n) for n in names]
        rec["aliases"] = [cat_s.intern(a)
                          for a in MOLECULE_ALIASES.get(rec["chembl_id"], [])]
        rec["trial_sites"], rec["trial_countries"] = sites.get(mid, (None, None))
        molecules.append(_row(rec, MOLECULE_FIELDS, cat_s))
        molecule_ids.append(mid)

    # ---- targets ---------------------------------------------------------
    # protein_class arrived after databases had been built without it, and is
    # filled into those by scripts/resolve_cohort_protein_class.py; a database
    # that has neither exports the three fields it always did.
    has_class = "protein_class" in {c[1] for c in db.execute(
        "PRAGMA table_info(target_components)")}
    components = collections.defaultdict(list)
    for r in db.execute("SELECT target_chembl_id, accession, gene_symbol, description" +
                        (", protein_class" if has_class else "") +
                        " FROM target_components ORDER BY target_chembl_id, accession"):
        row = [r["accession"], cat_s.intern(r["gene_symbol"]),
               cat_s.intern(r["description"])]
        if has_class and r["protein_class"]:
            row.append(cat_s.intern(r["protein_class"]))
        components[r["target_chembl_id"]].append(row)

    # The human protein a non-human record is, from
    # scripts/resolve_cohort_orthologues.py (D20); absent before that has run,
    # when every record is its own protein, as it was before D20.
    orthologues = {}
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                  " AND name = 'target_orthologues'").fetchone():
        orthologues = dict(db.execute(
            "SELECT target_chembl_id, human_accession FROM target_orthologues"
            " WHERE human_accession IS NOT NULL"))

    targets = []
    for r in db.execute("SELECT * FROM targets ORDER BY chembl_id"):
        rec = dict(r)
        rec["name"] = rec.pop("pref_name") or rec["chembl_id"]
        rec["components"] = components.get(rec["chembl_id"], [])
        rec["human_orthologue"] = orthologues.get(rec["chembl_id"])
        targets.append(_row(rec, TARGET_FIELDS, cat_s))

    # ---- claims ----------------------------------------------------------
    endpoints = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM claim_endpoints ORDER BY claim_id, endpoint_class"):
        endpoints[r["claim_id"]].append(dict(r))

    drawable = []
    gtopdb_claims = []
    gtp_s = Strings()
    retained_by_molecule = collections.defaultdict(list)
    claim_molecule = {}
    for r in db.execute("SELECT * FROM claims ORDER BY id"):
        rec = dict(r)
        mid = rec.pop("parent_molregno")
        rec["molecule"] = mid
        rec["target"] = rec.pop("target_chembl_id")
        rec["role"] = rec.pop("claim_role")
        claim_molecule[rec["id"]] = mid
        if rec["role"] == GTOPDB_ROLE:
            # D18 writes these Supported with no measurement behind them, so
            # none is ever retained in a shard: the GtoPdb file holds them all.
            if rec["tier"] not in DRAWABLE_TIERS or endpoints.get(rec["id"]):
                raise common.PolicyError(
                    f"claim {rec['id']}: a gtopdb claim that is not drawable, or"
                    " carries endpoints, would have to travel in a ChEMBL shard")
            rec["endpoints"] = []
            gtopdb_claims.append(_row(rec, CLAIM_FIELDS, gtp_s))
        elif rec["tier"] in DRAWABLE_TIERS:
            rec["endpoints"] = [_row(e, ENDPOINT_FIELDS, cat_s)
                                for e in endpoints.get(rec["id"], [])]
            drawable.append(_row(rec, CLAIM_FIELDS, cat_s))
        else:
            retained_by_molecule[mid].append(rec)

    # The trial ids travel joined rather than as an array: they are almost all
    # distinct, so interning buys nothing on the ids themselves, and one string
    # per row is shorter than the brackets and quotes an array would need. The
    # viewer splits them. Ordering is by descending phase so the panel's own
    # order is the export's, and a disease reached at two phases by two forms of
    # one molecule meets its highest first.
    indications = collections.defaultdict(list)
    for r in db.execute("SELECT parent_molregno, mesh_id, mesh_heading, phase_label,"
                        " scope_reasons, qualifies, max_phase_for_ind, trial_ids"
                        " FROM molecule_indications ORDER BY parent_molregno,"
                        " max_phase_for_ind DESC, mesh_heading, mesh_id"):
        indications[str(r["parent_molregno"])].append(
            [r["mesh_id"], cat_s.intern(r["mesh_heading"]),
             cat_s.intern(r["phase_label"]), cat_s.intern(r["scope_reasons"]),
             r["qualifies"], cat_s.intern(r["trial_ids"])])

    # Registry status per trial, from scripts/resolve_cohort_trials.py. That is
    # a backfill run after a build rather than part of one, so a database that
    # has not had it run (or predates the table) exports an empty map and the
    # viewer says the status was not fetched, rather than inventing one.
    trial_status = {}
    # When the registry was asked, as [earliest, latest] fetched_at, so the
    # page can date "as recorded when this page was built" (NLM's terms ask
    # for it too). None where the backfill has not run.
    trials_fetched = None
    has_trials = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                            " AND name = 'trial_status'").fetchone()
    if has_trials:
        first, last = db.execute(
            "SELECT MIN(fetched_at), MAX(fetched_at) FROM trial_status").fetchone()
        if first:
            trials_fetched = [first, last]
        # Rows fetched before phases and primary outcomes were recorded carry
        # two fields, and the viewer shows nothing for what was not fetched;
        # newer rows always carry four, so a null outcome there means the
        # registry has no results for that trial rather than "not asked".
        cols = {c[1] for c in db.execute("PRAGMA table_info(trial_status)")}
        detailed = {"phases", "primary_outcomes", "schema_version"} <= cols
        dated = detailed and set(TRIAL_DATE_COLUMNS) <= cols
        sited = dated and "countries" in cols
        select = ("SELECT nct_id, overall_status, why_stopped" +
                  (", phases, primary_outcomes, schema_version" if detailed else "") +
                  ("".join(", " + c for c in TRIAL_DATE_COLUMNS) if dated else "") +
                  (", countries" if sited else "") +
                  " FROM trial_status ORDER BY nct_id")
        for r in db.execute(select):
            row = [cat_s.intern(r["overall_status"]), cat_s.intern(r["why_stopped"])]
            if detailed and (r["schema_version"] or 0) >= 2:
                outcomes = None
                if r["primary_outcomes"] is not None:
                    # Only the outcomes with a reported p-value travel: they
                    # are all the page shows, and the titles of the untested
                    # ones were 610 KB of the startup file. An empty list still
                    # says "results posted, nothing tested". p-values verbatim.
                    outcomes = []
                    for o in json.loads(r["primary_outcomes"]):
                        ps = [a["p"] for a in o.get("analyses") or [] if a.get("p")]
                        if ps:
                            outcomes.append([cat_s.intern(o.get("title")), ps])
                row += [cat_s.intern(r["phases"]), outcomes]
                if dated and (r["schema_version"] or 0) >= 3:
                    row += _trial_years(r)
                if sited and (r["schema_version"] or 0) >= 4:
                    row = _with_trial_countries(row, r["countries"], cat_s)
            elif row[1] is None:
                row.pop()
            trial_status[r["nct_id"]] = row

    # Drug classes, from molecule_classes and class_labels, for search and
    # display only. Only the sources in SURFACED_CLASS_SOURCES travel: the
    # database also holds every ATC code, which was surfaced for a day and
    # taken back off the page (2026-09-26, at the user's request) because ATC
    # files a drug by its use and does not answer "which molecules are alike".
    # A database built before the tables existed (and not yet backfilled by
    # scripts/resolve_cohort_classes.py) exports an empty block.
    # mesh_record is each structure-classed molecule's own MeSH record
    # (D002110 for caffeine, C000591922 for brexpiprazole), read off the
    # carriers: the page links it, and tells a drug's own heading apart from
    # the classes it is filed in.
    classes = {"fields": ["source", "code", "subgroup", "label"],
               "labels": {}, "molecules": {}, "mesh_record": {}}
    has_classes = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                             " AND name IN ('molecule_classes', 'class_labels')"
                             ).fetchone()[0] == 2
    if has_classes:
        marks = ",".join("?" * len(SURFACED_CLASS_SOURCES))
        # parents arrived with the MeSH hierarchy; an older database has none.
        has_parents = "parents" in {c[1] for c in db.execute("PRAGMA table_info(class_labels)")}
        for r in db.execute("SELECT source, code, level, label" +
                            (", parents" if has_parents else "") + " FROM class_labels"
                            f" WHERE source IN ({marks}) ORDER BY source, code",
                            SURFACED_CLASS_SOURCES):
            row = [r["level"], cat_s.intern(r["label"])]
            if has_parents and r["parents"]:
                row.append(r["parents"].split("|"))
            classes["labels"].setdefault(r["source"], {})[r["code"]] = row
        for r in db.execute("SELECT parent_molregno, source, code, subgroup, label"
                            f" FROM molecule_classes WHERE source IN ({marks})"
                            " ORDER BY parent_molregno, source, code, subgroup",
                            SURFACED_CLASS_SOURCES):
            row = [r["source"], r["code"], r["subgroup"] or None, cat_s.intern(r["label"])]
            while row and row[-1] is None:
                row.pop()
            classes["molecules"].setdefault(str(r["parent_molregno"]), []).append(row)
        for r in db.execute("SELECT DISTINCT parent_molregno, carriers FROM molecule_classes"
                            " WHERE source = 'mesh_struct' ORDER BY parent_molregno"):
            own = [c[5:] for c in r["carriers"].split("|") if c.startswith("MeSH:")]
            if len(own) == 1:
                classes["mesh_record"][str(r["parent_molregno"])] = own[0]
        # A class's Wikipedia article, from scripts/resolve_cohort_wikipedia.py,
        # for the classes the page has a label for. A database that has not had
        # it run exports none and the page shows no link.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                      " AND name = 'class_wikipedia'").fetchone():
            classes["wikipedia"] = {}
            for r in db.execute("SELECT w.source, w.code, w.wikipedia_url"
                                " FROM class_wikipedia w JOIN class_labels l"
                                " USING (source, code)"
                                f" WHERE w.source IN ({marks}) ORDER BY w.source, w.code",
                                SURFACED_CLASS_SOURCES):
                classes["wikipedia"].setdefault(r["source"], {})[r["code"]] = r["wikipedia_url"]

    # GtoPdb actions, from a backfill run after a build. A database that has
    # not had it run exports an empty block, and the page shows ChEMBL's
    # directions alone, as it always did.
    gtopdb_release, gtopdb_actions = None, []
    has_gtopdb = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                            " AND name = 'gtopdb_interactions'").fetchone()
    if has_gtopdb:
        gtopdb_release = json.loads(manifest.get("gtopdb_actions") or "{}").get("release")
        for r in db.execute("SELECT * FROM gtopdb_interactions WHERE has_claim = 1"
                            " ORDER BY parent_molregno, target_chembl_id,"
                            " gtp_ligand_id, gtp_target_id, gtp_type, gtp_action"):
            rec = dict(r)
            rec["molecule"] = rec.pop("parent_molregno")
            rec["target"] = rec.pop("target_chembl_id")
            gtopdb_actions.append(_row(rec, GTOPDB_FIELDS, gtp_s))

    # ---- evidence shards -------------------------------------------------
    obs_by_molecule = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM observations ORDER BY activity_id"):
        obs_by_molecule[r["parent_molregno"]].append(dict(r))
    cs_by_molecule = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM claim_studies"
                        " ORDER BY claim_id, endpoint_class, study_key"):
        cs_by_molecule[claim_molecule.get(r["claim_id"])].append(dict(r))
    cur_by_molecule = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM curated_mechanisms ORDER BY mec_id"):
        cur_by_molecule[r["parent_molregno"]].append(dict(r))

    shard_dir = out_dir / "evidence"
    stale = _clear_shards(shard_dir)
    shard_bytes = shard_max = n_obs = n_studies = n_shards = 0

    for mol in molecule_ids:
        rows = obs_by_molecule.get(mol, [])
        retained = retained_by_molecule.get(mol, [])
        cstudies = cs_by_molecule.get(mol, [])
        curated_rows = cur_by_molecule.get(mol, [])
        if not (rows or retained or cstudies or curated_rows):
            continue

        s_local = Strings()
        study_index: dict[str, int] = {}
        studies: list = []

        def study_ref(rec):
            key = rec.get("study_key")
            if key is None:
                return None
            i = study_index.get(key)
            if i is None:
                i = len(studies)
                study_index[key] = i
                studies.append(_row({
                    "study_key": key,
                    "provenance_class": rec.get("provenance_class"),
                    "pubmed_id": rec.get("pubmed_id"),
                    "year": rec.get("year", rec.get("doc_year")),
                    "journal": rec.get("journal", rec.get("doc_journal")),
                    "title": rec.get("title", rec.get("doc_title")),
                    "doi": rec.get("doi"),
                    "patent_id": rec.get("patent_id"),
                    "doc_chembl_id": rec.get("doc_chembl_id"),
                }, STUDY_FIELDS, s_local))
            return i

        observations = []
        for rec in rows:
            rec = dict(rec)
            rec["molecule"] = rec.pop("parent_molregno")
            rec["target"] = rec.pop("target_chembl_id")
            rec["study"] = study_ref(rec)
            observations.append(_row(rec, OBSERVATION_FIELDS, s_local))

        claim_studies = []
        for rec in cstudies:
            rec = dict(rec)
            rec["study"] = study_ref(rec)
            claim_studies.append(_row(rec, CLAIM_STUDY_FIELDS, s_local))

        claims = []
        for rec in retained:
            rec = dict(rec)
            rec["endpoints"] = [_row(e, ENDPOINT_FIELDS, s_local)
                                for e in endpoints.get(rec["id"], [])]
            claims.append(_row(rec, CLAIM_FIELDS, s_local))

        curated = []
        for rec in curated_rows:
            rec = dict(rec)
            rec["refs"] = json.loads(rec.get("refs") or "[]")
            curated.append(_row(rec, CURATED_FIELDS, s_local))

        size = _dump_shard(shard_dir, mol, {
            "molecule": mol,
            "fields": {"observations": OBSERVATION_FIELDS, "studies": STUDY_FIELDS,
                       "claim_studies": CLAIM_STUDY_FIELDS, "curated": CURATED_FIELDS,
                       "claims": CLAIM_FIELDS, "endpoints": ENDPOINT_FIELDS},
            "observations": observations,
            "studies": studies,
            "claim_studies": claim_studies,
            "claims": claims,
            "curated": curated,
            "strings": s_local.values,
        })
        shard_bytes += size
        shard_max = max(shard_max, size)
        n_obs += len(observations)
        n_studies += len(studies)
        n_shards += 1

    # Both startup files carry this one stamp, and the page merges the GtoPdb
    # file only into the catalogue it was exported with: an older
    # graph.data.js still carries GtoPdb's claims itself, and a mismatched
    # pair (a partial republish, a cached file) would count them twice.
    generated = datetime.datetime.now().isoformat(timespec="seconds")
    catalogue = {
        "format": "cohort1/2",
        "licence": GRAPH_LICENCE,
        "generated": generated,
        "meta": manifest,
        "evidence_dir": "evidence",
        "fields": {"molecules": MOLECULE_FIELDS, "targets": TARGET_FIELDS,
                   "claims": CLAIM_FIELDS, "endpoints": ENDPOINT_FIELDS},
        "counts": {
            "molecules": len(molecules), "targets": len(targets),
            "claims_drawable": len(drawable),
            "claims_retained": sum(len(v) for v in retained_by_molecule.values()),
            "observations": n_obs, "evidence_shards": n_shards,
        },
        "molecules": molecules,
        "targets": targets,
        "claims": drawable,
        "indications": dict(indications),
        "classes": classes,
        "trial_status": trial_status,
        "trials_fetched": trials_fetched,
        "exclusions": [[r["reason"], r["n_rows"], r["retained"], cat_s.intern(r["note"])]
                       for r in db.execute("SELECT * FROM exclusion_summary"
                                           " ORDER BY reason")],
        "source_coverage": [[r["source"], r["status"], r["release"],
                             cat_s.intern(r["note"])]
                            for r in db.execute("SELECT * FROM source_coverage"
                                                " ORDER BY source")],
        "validation": [[r["check_name"], r["result"], r["detail"]]
                       for r in db.execute("SELECT * FROM validation"
                                           " ORDER BY check_name")],
        "strings": cat_s.values,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    backups = _backup(out_dir) if backup else []
    n1 = _dump(out_dir / "graph.data.js", "COHORT_DATA", catalogue, GRAPH_NOTICE)

    # Written even from a database the backfill has not reached, empty, so a
    # stale file from an earlier export is never paired with this one.
    gtopdb = {
        "format": "cohort1-gtopdb/1",
        "licence": GTOPDB_LICENCE,
        "generated": generated,
        "release": gtopdb_release,
        "fields": {"actions": GTOPDB_FIELDS, "claims": CLAIM_FIELDS},
        "actions": gtopdb_actions,
        "claims": gtopdb_claims,
        # molecule id -> [evidence_status, gap_reason], only where GtoPdb's
        # claims change what ChEMBL's alone give.
        "status": status_with_gtopdb,
        "strings": gtp_s.values,
    }
    n2 = _dump(out_dir / "gtopdb.data.js", "COHORT_GTOPDB", gtopdb, GTOPDB_NOTICE)

    # A single-file export from an earlier format would shadow the shards.
    legacy = out_dir / "evidence.data.js"
    if legacy.exists():
        legacy.unlink()

    return {
        "graph_bytes": n1,
        "gtopdb_bytes": n2,
        "gtopdb_actions": len(gtopdb_actions),
        "gtopdb_claims": len(gtopdb_claims),
        "gtopdb_status_changes": len(status_with_gtopdb),
        "evidence_bytes": shard_bytes,
        "evidence_shards": n_shards,
        "evidence_largest_shard": shard_max,
        "stale_shards_removed": stale,
        "molecules": len(molecules), "targets": len(targets),
        "claims_drawable": len(drawable),
        "claims_retained": catalogue["counts"]["claims_retained"],
        "observations": n_obs, "studies": n_studies,
        "catalogue_strings": len(cat_s.values),
        "backups": backups,
    }
