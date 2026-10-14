-- SubNetwork cohort-1 schema
--
-- The clinical cohort's database. Built by scripts/build_cohort.py from
-- ChEMBL 37 alone, against the two versioned policies in config/. It is a
-- separate file from db/subnetwork.db, which stays as the legacy six-source
-- build and the rollback path.
--
-- Three things about this schema differ from the legacy one, and each is a
-- decision rather than a refactor:
--
--   * A target is a ChEMBL target record, not a gene. The legacy `targets`
--     table keyed on a UNIQUE gene_symbol and uniprot_accession, which cannot
--     represent a PROTEIN FAMILY or PROTEIN COMPLEX GROUP at all. D06 keeps
--     all four native target identities, so the key is the target's own
--     ChEMBL id and components are context hanging off it.
--   * An edge is a claim at (parent, target, role), assessed separately in
--     each assignment basis. The legacy UNIQUE (molecule, target, action_type)
--     could not hold the same molecule-target relationship at two different
--     evidence bases, and had no room for a tier at all.
--   * Trust is a tier computed from distinct studies, not from a measurement
--     count. `n_measurements` still exists and must still reconcile to what
--     is stored (invariant 7 survives as an accounting rule), but it is no
--     longer the trust signal. D08 replaced it.

PRAGMA foreign_keys = ON;

-- Which pinned sources, policy versions and code produced this file. Written
-- once per build; a database that cannot say which rules made it is not
-- auditable.
CREATE TABLE IF NOT EXISTS build_manifest (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

-- ---------------------------------------------------------------- catalogue

-- One row per chemical parent. `in_cohort` and `is_seed` are separate columns
-- on purpose (D05): a seed is never grandfathered into the clinical cohort,
-- and a clinical member is not a seed. Five seeds are retained here with
-- in_cohort = 0 and an exclusion_reason, as examples for designing cohort 2.
CREATE TABLE IF NOT EXISTS molecules (
    parent_molregno      INTEGER PRIMARY KEY,
    chembl_id            TEXT NOT NULL UNIQUE,
    pref_name            TEXT,
    molecule_type        TEXT,          -- source category, never used as a filter (D03)
    structure_type       TEXT,          -- 'NONE' is retained and flagged, never invented (D04)
    max_phase            REAL,          -- molecule-level, across ALL diseases; not the admission test
    first_approval       INTEGER,
    withdrawn_any_family INTEGER NOT NULL DEFAULT 0,
    in_cohort            INTEGER NOT NULL,
    is_seed              INTEGER NOT NULL,
    seed_name            TEXT,
    route_atc_n          INTEGER NOT NULL,
    route_indication     INTEGER NOT NULL,
    admission_reason     TEXT NOT NULL,  -- both_routes / route_atc_n / route_indication / seed_only
    exclusion_reason     TEXT,           -- why a retained seed is not in the cohort
    scope_reasons        TEXT,           -- '|' joined: core / general_pain / explicit_neuropathic / explicit_fibromyalgia / explicit_cns_heading
    atc_level5           TEXT,
    atc_flags            TEXT,           -- peripheral_site_of_action / general_analgesic
    identity_flags       TEXT,           -- structure_unresolved / withdrawn_in_family / a named anomaly
    molecular_formula    TEXT,
    molecular_weight     REAL,
    smiles               TEXT,
    inchikey             TEXT,
    wikipedia_url        TEXT,           -- resolved by identifier only, NULL when unresolved
    -- Distinct diseases ChEMBL records for this family across every therapeutic
    -- area. molecule_indications holds only the ones inside the adopted scope,
    -- so this is what lets a list of them say how much of the record it is
    -- showing rather than reading as the whole label.
    n_indications_chembl INTEGER NOT NULL DEFAULT 0,
    -- '|' joined MeSH headings of the diseases the family is approved for
    -- outside the adopted scope, NULL where there are none. Lets an approved
    -- drug whose listed diseases carry no approval say what it is approved for.
    approved_elsewhere   TEXT,
    -- Derived from claims at the end of a build, so a catalogue entry can say
    -- what it has without the viewer recomputing it: has_supported /
    -- has_preliminary / limited_only / no_eligible_evidence.
    evidence_status      TEXT,
    gap_reason           TEXT
);

-- Every ChEMBL record that folded onto this parent: salts, hydrates and
-- formulations. Retained so identity stays traceable and a seed's own record
-- id survives the rollup (D03, D05).
CREATE TABLE IF NOT EXISTS molecule_forms (
    parent_molregno  INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    molregno         INTEGER NOT NULL,
    chembl_id        TEXT,
    pref_name        TEXT,
    molecule_type    TEXT,
    structure_type   TEXT,
    max_phase        REAL,
    withdrawn_flag   INTEGER,
    is_parent        INTEGER NOT NULL,
    carries_atc_n    INTEGER NOT NULL DEFAULT 0,
    carries_qualifying_indication INTEGER NOT NULL DEFAULT 0,
    -- The seed list's own ChEMBL id where this form is one, e.g. theophylline
    -- was seeded as CHEMBL1355736 and rolls up to parent CHEMBL190. Both
    -- identities survive here.
    seed_alias       TEXT,
    PRIMARY KEY (parent_molregno, molregno)
);

CREATE TABLE IF NOT EXISTS molecule_synonyms (
    parent_molregno  INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    molregno         INTEGER NOT NULL,
    synonym          TEXT NOT NULL,
    PRIMARY KEY (parent_molregno, molregno, synonym)
);

CREATE TABLE IF NOT EXISTS molecule_atc (
    parent_molregno  INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    carrier_molregno INTEGER NOT NULL,
    carrier_chembl_id TEXT,
    level5           TEXT NOT NULL,
    level4           TEXT,
    level3           TEXT,
    level2           TEXT,
    who_name         TEXT,
    level3_description TEXT,
    boundary_flag    TEXT,             -- set for N01B and N02B; annotated, never removed
    PRIMARY KEY (parent_molregno, carrier_molregno, level5)
);

-- The drug classes recorded for each entry, for search and display only.
-- Four sources, kept apart and never merged. From ChEMBL: the WHO ATC code of
-- every form of the molecule, in every anatomical group (molecule_atc above
-- keeps only the N codes, because it is the admission route's record), and the
-- USAN/INN name stem, which files a drug by the family its name was assigned
-- from - written by the build and, for a database built before it, by
-- scripts/resolve_cohort_classes.py. From MeSH: the pharmacological actions
-- NLM's indexers record for the drug ('mesh_pa'), written only by the network
-- backfill scripts/resolve_cohort_pharm_actions.py; and the chemical-structure
-- classes MeSH files the drug under ('mesh_struct', "Xanthines"), written only
-- by scripts/resolve_cohort_mesh_structure.py through FDA's UNII. Each writer
-- replaces only its own sources. A class is not evidence about a target and never enters the
-- similarity score.
CREATE TABLE IF NOT EXISTS molecule_classes (
    parent_molregno  INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    source           TEXT NOT NULL,     -- 'atc' | 'usan' | 'mesh_pa' | 'mesh_struct' | 'fda_epc' | 'fda_moa' | 'fda_pe'
    code             TEXT NOT NULL,     -- ATC level-5 code, the stem as ChEMBL writes it ('-pramine'),
                                        -- a MeSH descriptor UI ('D000929'), or an FDA
                                        -- class id from RxClass ('N0000175696')
    subgroup         TEXT NOT NULL DEFAULT '',  -- USAN sub-stem ('-tioxetine'), '' for none; '' for ATC
    label            TEXT,              -- ATC: WHO substance name; USAN: the stem's own annotation
    carriers         TEXT NOT NULL,     -- '|' joined ChEMBL ids of the forms that carry it;
                                        -- for mesh_pa the identifiers that reached the molecule's
                                        -- MeSH record ('UNII:3G6A5W338E|MeSH:D002110', a CAS after
                                        -- the UNII, or 'Wikidata:Q60235|MeSH:D002110'); for
                                        -- mesh_struct the form matched, its UNII and the molecule's
                                        -- own MeSH record ('CHEMBL113|UNII:3G6A5W338E|MeSH:D002110');
                                        -- for fda_epc / fda_moa / fda_pe the UNIIs that reached the
                                        -- RxNorm ingredient, the ingredient and the sources that
                                        -- asserted the class ('UNII:QUC7NX6WMB|RxCUI:36437|FDASPL+MEDRT')
    PRIMARY KEY (parent_molregno, source, code, subgroup)
);

-- The name of each class a molecule_classes row falls in: ATC levels 1-4 as
-- WHO describes them, each USAN stem's annotation, and each MeSH action with
-- the MeSH actions above it. NULL where ChEMBL gives a stem no annotation of
-- its own, rather than one borrowed from a member.
CREATE TABLE IF NOT EXISTS class_labels (
    source           TEXT NOT NULL,     -- 'atc' | 'usan' | 'mesh_pa' | 'mesh_struct' | 'fda_epc' | 'fda_moa' | 'fda_pe'
    code             TEXT NOT NULL,     -- 'N', 'N06', 'N06A', 'N06AA'; '-pramine'; 'D000929'; 'N0000175696'
    level            INTEGER,           -- ATC level 1-4; MeSH tree depth; NULL for a stem
    label            TEXT,
    parents          TEXT,              -- '|' joined codes of the classes directly above (mesh_pa, mesh_struct)
    PRIMARY KEY (source, code)
);

-- An English Wikipedia article for a MeSH structure class, written only by
-- scripts/resolve_cohort_wikipedia.py and only where an identifier reaches it:
-- the one Wikidata item carrying the class's MeSH descriptor (P486) has an
-- article of its own ('item'), or, where it has none, the English category
-- Wikidata names for that item (P910) declares its main article ('category' -
-- "Xanthines" has an item and no article; Category:Xanthines names Xanthine).
-- Its own table rather than a class_labels column, because the class backfills
-- delete and rewrite their class_labels rows and would wipe it. Only resolved
-- classes have a row; a class with none is shown without a link.
CREATE TABLE IF NOT EXISTS class_wikipedia (
    source           TEXT NOT NULL,     -- 'mesh_struct'
    code             TEXT NOT NULL,     -- the MeSH descriptor UI, as in class_labels
    wikidata_item    TEXT NOT NULL,     -- 'Q49922434': the one item carrying the descriptor
    route            TEXT NOT NULL,     -- 'item' | 'category'
    category         TEXT,              -- 'Category:Xanthines', on the category route
    wikipedia_url    TEXT NOT NULL,
    PRIMARY KEY (source, code)
);

-- Every in-scope indication, qualifying or not. The near misses are kept
-- because "loperamide's pain indication is Early Phase 1" is the answer to
-- why it is not a member, and deleting it would leave only the absence.
CREATE TABLE IF NOT EXISTS molecule_indications (
    parent_molregno   INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    drugind_id        INTEGER NOT NULL,
    member_molregno   INTEGER,
    member_chembl_id  TEXT,
    mesh_id           TEXT NOT NULL,
    mesh_heading      TEXT,
    efo_id            TEXT,
    efo_term          TEXT,
    max_phase_for_ind REAL,
    phase_label       TEXT,
    scope_reasons     TEXT,
    qualifies         INTEGER NOT NULL,   -- 1 when it satisfies the indication route
    -- ClinicalTrials.gov NCT ids from ChEMBL's indication_refs, '|' joined, NULL
    -- where ChEMBL registers none. The registry entry is what stands behind a
    -- phase annotation, and without it "Phase 3" is an assertion this page could
    -- not show the reader. Identifiers only, never a title search (invariant 15):
    -- the link is built from the NCT id at display time.
    trial_ids         TEXT,
    PRIMARY KEY (parent_molregno, drugind_id)
);

-- The adopted scope, descriptor by descriptor, so a membership decision can
-- be traced to the classification that produced it without re-reading the
-- pinned CSV.
CREATE TABLE IF NOT EXISTS indication_scope (
    mesh_id           TEXT PRIMARY KEY,
    label             TEXT,
    tree_numbers      TEXT,
    in_core           INTEGER NOT NULL,
    boundary_classes  TEXT,
    in_scope          INTEGER NOT NULL,
    scope_reasons     TEXT,
    drug_indication_rows INTEGER
);

-- ------------------------------------------------------------------ targets

-- One row per ChEMBL target record, at the identity ChEMBL asserts (D06).
-- There is deliberately no UNIQUE on an accession: a single protein, a
-- complex containing it and a family containing it are three different
-- targets making three different claims.
CREATE TABLE IF NOT EXISTS targets (
    chembl_id     TEXT PRIMARY KEY,
    tid           INTEGER,
    pref_name     TEXT,
    target_type   TEXT NOT NULL,   -- SINGLE PROTEIN / PROTEIN COMPLEX / PROTEIN COMPLEX GROUP / PROTEIN FAMILY
    organism      TEXT,
    tax_id        INTEGER,
    n_components  INTEGER,
    wikipedia_url TEXT
);

-- What a target contains, as context. These rows are never read as binding
-- claims: a complex's evidence is not evidence about its subunits, and a
-- family's is not evidence about its members (D06).
CREATE TABLE IF NOT EXISTS target_components (
    target_chembl_id TEXT NOT NULL REFERENCES targets(chembl_id),
    accession        TEXT NOT NULL,
    description      TEXT,
    gene_symbol      TEXT,          -- label only; never a matching or merging key
    -- ChEMBL protein_classification at levels 1-2, "L1 > L2", '|'-joined when a
    -- component is filed under several. A drawing hint for the viewer (which
    -- complexes are ion-channel assemblies); never a matching key or evidence.
    protein_class    TEXT,
    PRIMARY KEY (target_chembl_id, accession)
);

-- ------------------------------------------------------------------- claims

-- One row per (parent, target, role, assignment basis). The same molecule and
-- target can carry a curated claim, a binding claim and a functional claim,
-- and each of those separately in the direct-human and broader bases. None of
-- them upgrades another.
CREATE TABLE IF NOT EXISTS claims (
    id                      INTEGER PRIMARY KEY,
    parent_molregno         INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    target_chembl_id        TEXT NOT NULL REFERENCES targets(chembl_id),
    claim_role              TEXT NOT NULL,   -- curated / binding / functional
    basis                   TEXT NOT NULL,   -- human_direct / broader
    tier                    TEXT NOT NULL,   -- supported / preliminary / limited_or_unresolved
    tier_reason             TEXT NOT NULL,
    -- The two Supported routes are separate flags, never one score. Curated
    -- support is one curator's assertion; multiple-study support is
    -- replication across publications. The viewer shows which.
    curated_support         INTEGER NOT NULL DEFAULT 0,
    multiple_study_support  INTEGER NOT NULL DEFAULT 0,
    -- Which endpoint class earned Supported, kept visible so a tier won at Ki
    -- cannot appear to certify the claim's functional IC50.
    supporting_endpoint_class TEXT,
    n_rows                  INTEGER NOT NULL DEFAULT 0,
    n_measurements          INTEGER NOT NULL DEFAULT 0,  -- exact values only
    n_bounds                INTEGER NOT NULL DEFAULT 0,
    n_conditional           INTEGER NOT NULL DEFAULT 0,
    n_unresolved            INTEGER NOT NULL DEFAULT 0,
    n_studies               INTEGER NOT NULL DEFAULT 0,
    n_publications          INTEGER NOT NULL DEFAULT 0,
    n_patents               INTEGER NOT NULL DEFAULT 0,
    n_datasets              INTEGER NOT NULL DEFAULT 0,
    action_type             TEXT,              -- curated action; where one pair's curated rows name
                                               -- several, all of them, sorted and joined with ' / '
                                               -- ('AGONIST / PARTIAL AGONIST') - a list, never one word
    mechanism_of_action     TEXT,
    direct_interaction      INTEGER,
    conflict_action         INTEGER NOT NULL DEFAULT 0,
    conflict_dispersion     INTEGER NOT NULL DEFAULT 0,
    conflict_detail         TEXT,
    assignment_classes      TEXT,
    -- Set only where a curated action was withheld as a known ChEMBL error
    -- (CHEMBL_MECHANISM_ACTION_EXCLUSIONS): ChEMBL's word, its sentence and the
    -- reason, in one line the viewer shows. action_type and
    -- mechanism_of_action above are then NULL for that record.
    action_exclusion        TEXT,
    UNIQUE (parent_molregno, target_chembl_id, claim_role, basis)
);

CREATE INDEX IF NOT EXISTS idx_claims_molecule ON claims(parent_molregno);
CREATE INDEX IF NOT EXISTS idx_claims_target ON claims(target_chembl_id);
CREATE INDEX IF NOT EXISTS idx_claims_tier ON claims(basis, tier);

-- Per-endpoint summaries. Ki, Kd, binding IC50, functional IC50, EC50, AC50
-- and Kb are never pooled with one another, so the median lives here rather
-- than on the claim.
CREATE TABLE IF NOT EXISTS claim_endpoints (
    claim_id       INTEGER NOT NULL REFERENCES claims(id),
    endpoint_class TEXT NOT NULL,
    n_measurements INTEGER NOT NULL,   -- rows with counted = 1; must reconcile exactly
    n_rows         INTEGER NOT NULL,
    median_nm      REAL,
    min_nm         REAL,
    max_nm         REAL,
    n_studies      INTEGER NOT NULL,
    n_publications INTEGER NOT NULL,
    supported      INTEGER NOT NULL DEFAULT 0,
    log_spread     REAL,
    PRIMARY KEY (claim_id, endpoint_class)
);

-- One row per distinct study behind a claim's endpoint. Twenty measurement
-- rows from one paper collapse to one row here; that collapse is what the
-- Supported tier counts.
CREATE TABLE IF NOT EXISTS claim_studies (
    claim_id         INTEGER NOT NULL REFERENCES claims(id),
    endpoint_class   TEXT NOT NULL,
    study_key        TEXT NOT NULL,     -- pmid:… / doi:… / patent:… / doc:…
    provenance_class TEXT NOT NULL,     -- publication / patent / deposited_dataset / unresolved
    n_measurements   INTEGER NOT NULL,
    n_rows           INTEGER NOT NULL,
    pubmed_id        INTEGER,
    doi              TEXT,
    patent_id        TEXT,
    doc_chembl_id    TEXT,
    year             INTEGER,
    journal          TEXT,
    title            TEXT,
    PRIMARY KEY (claim_id, endpoint_class, study_key)
);

-- One row per retained ChEMBL activity record. Deliberately not
-- deduplicated: two identical values from two assays are two observations.
--
-- A row with claim_id NULL is a retained observation that backs no edge - an
-- unassigned target, a non-molecular assignment, a target type outside the
-- four claimable identities. It stays here with its reason so a catalogue
-- entry can show what exists without a graph edge being manufactured for it.
CREATE TABLE IF NOT EXISTS observations (
    activity_id       INTEGER PRIMARY KEY,
    parent_molregno   INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    measured_molregno INTEGER NOT NULL,
    measured_chembl_id TEXT,
    target_chembl_id  TEXT,
    tid               INTEGER,
    claim_id          INTEGER REFERENCES claims(id),
    role              TEXT,
    endpoint_class    TEXT,
    standard_type     TEXT,
    standard_relation TEXT,            -- '=' , '>', '<', '>=', '<=', '>>', '~' kept as reported
    standard_value    REAL,            -- the source's own value, never overwritten
    standard_units    TEXT,            -- the source's own units, never overwritten
    value_nm          REAL,            -- normalised; NULL when not resolvable
    value_status      TEXT NOT NULL,   -- exact / bound / conditional / unresolved
    -- Where value_nm came from. 'native' is already nM; 'concentration' is an
    -- audited dimensionally explicit conversion and counts normally; 'mass' is
    -- a conditional mass-to-molar result that is excluded from tiers, medians
    -- and threshold passes until its material basis is verified (D11).
    conversion_kind   TEXT,
    conversion_factor REAL,
    conversion_basis  TEXT,
    conversion_note   TEXT,
    material_basis_verified INTEGER,   -- NULL n/a, 0 conditional, 1 verified
    measured_full_mwt REAL,            -- the MEASURED record's weight, never the parent freebase
    measured_form     TEXT,
    counted           INTEGER NOT NULL DEFAULT 0,  -- entered a median and n_measurements
    basis             TEXT,
    assignment_class  TEXT,
    assignment_reason TEXT,
    confidence_score  INTEGER,
    relationship_type TEXT,
    variant_id        INTEGER,
    assay_chembl_id   TEXT,
    assay_description TEXT,            -- what the assay measured, in the source's words
    assay_type        TEXT,
    bao_label         TEXT,
    data_validity_comment TEXT,        -- recorded and shown, never used to drop a row
    potential_duplicate INTEGER,
    activity_comment  TEXT,
    study_key         TEXT,
    provenance_class  TEXT,
    pubmed_id         INTEGER,
    doi               TEXT,
    patent_id         TEXT,
    doc_chembl_id     TEXT,
    doc_year          INTEGER,
    doc_journal       TEXT,
    doc_title         TEXT,
    exclusion_reason  TEXT              -- why this observation backs no claim
);

CREATE INDEX IF NOT EXISTS idx_observations_claim ON observations(claim_id);
CREATE INDEX IF NOT EXISTS idx_observations_molecule ON observations(parent_molregno);

-- Curated ChEMBL mechanisms, at the target and action level asserted. A
-- family-level or complex-level mechanism stays one record here and is never
-- expanded into records for the members.
CREATE TABLE IF NOT EXISTS curated_mechanisms (
    mec_id             INTEGER PRIMARY KEY,
    parent_molregno    INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    measured_molregno  INTEGER,
    target_chembl_id   TEXT,
    claim_id           INTEGER REFERENCES claims(id),
    action_type        TEXT,
    action_parent_type TEXT,
    mechanism_of_action TEXT,
    direct_interaction INTEGER,
    molecular_mechanism INTEGER,
    mechanism_comment  TEXT,
    selectivity_comment TEXT,
    variant_id         INTEGER,
    n_refs             INTEGER NOT NULL DEFAULT 0,
    refs               TEXT,            -- JSON array of {ref_type, ref_id, ref_url}
    tier               TEXT NOT NULL,
    tier_reason        TEXT NOT NULL,
    -- ChEMBL's action_type, verbatim, where it was withheld as a known error
    -- (CHEMBL_MECHANISM_ACTION_EXCLUSIONS); action_type is then NULL and
    -- mechanism_of_action keeps ChEMBL's sentence as filed.
    excluded_action_type TEXT,
    action_exclusion   TEXT
);

-- Records excluded before they reached `observations`, counted by reason.
-- Nothing is dropped silently; an exclusion with no accounting is the failure
-- this table exists to prevent.
CREATE TABLE IF NOT EXISTS exclusion_summary (
    reason    TEXT PRIMARY KEY,
    n_rows    INTEGER NOT NULL,
    retained  INTEGER NOT NULL,        -- 1 when the rows survive in `observations`
    note      TEXT
);

-- The documented known-bad records, individually, so the exclusion can be
-- inspected instead of taken on trust (CLAUDE.md invariant 9).
CREATE TABLE IF NOT EXISTS excluded_records (
    activity_id      INTEGER PRIMARY KEY,
    parent_molregno  INTEGER,
    assay_chembl_id  TEXT,
    target_chembl_id TEXT,
    reason           TEXT NOT NULL,
    detail           TEXT
);

-- What each deferred source's status is, so "not assessed" can be shown as
-- itself rather than as an absence of pharmacology (D12).
CREATE TABLE IF NOT EXISTS source_coverage (
    source   TEXT PRIMARY KEY,
    status   TEXT NOT NULL,            -- assessed / not_assessed
    release  TEXT,
    note     TEXT
);

-- Build-time validation results, stored so a database carries the evidence
-- that it passed its own checks.
CREATE TABLE IF NOT EXISTS validation (
    check_name TEXT PRIMARY KEY,
    result     TEXT NOT NULL,
    detail     TEXT
);

-- ClinicalTrials.gov registry status for every NCT id molecule_indications
-- cites in trial_ids, backfilled by scripts/resolve_cohort_trials.py after a
-- build - the same shape as wikipedia_url on molecules and targets: a
-- separate run against an identifier this database already holds, never part
-- of a build, and the build itself opens ChEMBL alone. A phase annotation on
-- an indication says how far a trial got; this says what became of it, which
-- is the other half of "is this settled" a bare NCT id could not answer.
-- Matched on nctId exactly (invariant 15 again - identifier, never a title or
-- condition search); an id CT.gov does not return is never inserted, so a
-- missing row here means "not yet fetched or not found", not "no status".
--
-- phases and primary_outcomes were added after the first backfill shipped
-- (schema_version 2). schema_version is NULL or 1 on a row fetched under the
-- first shape and 2 on a row that carries these columns - not a heuristic
-- on the columns themselves, because a study can legitimately have no phase
-- or no primary outcome and NULL must not be read as "not fetched yet". A
-- default run re-fetches any row with schema_version < 2 alongside any id
-- with no row at all; see resolve_cohort_trials.py.
CREATE TABLE IF NOT EXISTS trial_status (
    nct_id            TEXT PRIMARY KEY,
    overall_status    TEXT,      -- CT.gov overallStatus verbatim: COMPLETED, TERMINATED, RECRUITING, UNKNOWN, ...
    why_stopped       TEXT,      -- statusModule.whyStopped verbatim, NULL if none given
    has_results       INTEGER,   -- 1/0 from hasResults
    last_update       TEXT,      -- statusModule.lastUpdatePostDateStruct.date
    phases            TEXT,      -- designModule.phases, '|'-joined verbatim ('PHASE2|PHASE3'), NULL if absent
    primary_outcomes  TEXT,      -- JSON array of {"title","analyses":[{"p","design"}]} for type=='PRIMARY'
                                  -- outcomes only, in registry order; NULL when the study has no results section
    start_date        TEXT,      -- statusModule.startDateStruct.date verbatim ('2005-06' or '2005-06-15')
    start_date_type   TEXT,      -- its type: ACTUAL, ESTIMATED, or NULL (the registry typed none before 2017)
    completion_date   TEXT,      -- statusModule.completionDateStruct.date verbatim: the whole study's end
    completion_date_type TEXT,   -- ACTUAL / ESTIMATED / NULL; ESTIMATED is a plan, often one long past
    schema_version    INTEGER,   -- 3 for a row carrying the dates; 2 for one with phases/primary_outcomes
                                  -- and no dates; NULL/1 for one fetched before any of them existed
    fetched_at        TEXT NOT NULL   -- ISO UTC timestamp of this fetch, for --refresh staleness
);

-- GtoPdb (IUPHAR/BPS Guide to Pharmacology) curated ligand-target interactions,
-- read for one field: the *action*, which ChEMBL gives on 1.5% of this
-- catalogue's molecule-target pairs. Backfilled by
-- scripts/resolve_cohort_gtopdb_actions.py from a pinned release, like the
-- other network backfills: a rebuild wipes it and it is rerun after.
--
-- A row never creates a claim, never raises a tier and is never evidence of
-- affinity. It supplies a direction to a pair the catalogue already draws
-- (has_claim = 1); rows at a pair with no claim are kept with has_claim = 0 so
-- what GtoPdb knows beyond ChEMBL stays countable, and nothing exports them.
--
-- Matched by identifier only (invariants 6 and 15). The ligand by exact
-- InChIKey to molecules.inchikey, else by its ChEMBL id to exactly one parent
-- through molecule_forms; the two routes disagreeing drops the ligand. The
-- target by UniProt accession: a one-accession GtoPdb target to the one SINGLE
-- PROTEIN record carrying it, a multi-subunit one only to a PROTEIN COMPLEX
-- whose accessions are exactly the same set - never fanned out onto subunits,
-- which would manufacture shared targets.
--
-- gtp_type and gtp_action are GtoPdb's words verbatim; action_type is the
-- ChEMBL action_type word they map to (ACTION_MAP in the script), NULL where
-- they name no direction ("Neutral", "Binding", "Mixed").
CREATE TABLE IF NOT EXISTS gtopdb_interactions (
    parent_molregno   INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    target_chembl_id  TEXT NOT NULL REFERENCES targets(chembl_id),
    gtp_ligand_id     INTEGER NOT NULL,
    gtp_target_id     INTEGER NOT NULL,
    gtp_type          TEXT NOT NULL,
    gtp_action        TEXT NOT NULL,
    action_type       TEXT,             -- ChEMBL vocabulary, NULL for no direction
    ligand_match      TEXT NOT NULL,    -- 'inchikey' | 'chembl_id'
    accessions        TEXT NOT NULL,    -- GtoPdb's target UniProt id(s), '|' joined
    target_species    TEXT,
    primary_target    INTEGER NOT NULL, -- 1 if GtoPdb marks this its primary target on any row
    endogenous        INTEGER NOT NULL, -- 1 if GtoPdb marks the ligand endogenous here
    selectivity       TEXT,             -- '|' joined distinct values
    action_comment    TEXT,             -- '|' joined distinct values
    receptor_site     TEXT,
    ligand_context    TEXT,
    pubmed_ids        TEXT,             -- '|' joined, as GtoPdb cites them
    n_rows            INTEGER NOT NULL, -- GtoPdb rows folded into this one
    has_claim         INTEGER NOT NULL, -- 1 if claims has this molecule at this target
    PRIMARY KEY (parent_molregno, target_chembl_id, gtp_ligand_id, gtp_target_id, gtp_type, gtp_action)
);
CREATE INDEX IF NOT EXISTS idx_gtopdb_pair ON gtopdb_interactions(parent_molregno, target_chembl_id);

-- Which human protein each non-human SINGLE PROTEIN record is the same protein
-- as, found by sequence (D20). Backfilled by scripts/resolve_cohort_orthologues.py
-- after a build, like the other backfills: a rebuild wipes it and it is rerun.
--
-- The similarity score counts a protein once however many species ChEMBL
-- records it in (naloxone and naltrexone's "12 shared targets" were three
-- opioid receptors in up to four species, and CYP2D6), and that needs to know
-- which records are one protein. No identifier says so: ChEMBL records no
-- orthology, NCBI's orthologue list misses the guinea-pig mu receptor, OrthoDB
-- puts mu and kappa in one group, and a gene symbol is never a matching key
-- (invariant 6). So it is read off the sequences: each mammalian record is
-- aligned to UniProt's reviewed human proteome (pinned, sha256 in
-- build_manifest), and matched only when its best human protein is clearly
-- ahead of the runner-up and, from the other side, that human protein's best
-- match in the record's species is this record. Anything short of that is
-- stored with its reason and human_accession NULL, which the viewer reads as
-- "its own protein" - so the failure mode is counting a protein twice, as
-- before, never merging two.
--
-- One row per non-human, mammalian, single-component SINGLE PROTEIN target in
-- the catalogue. A human record needs no row: it is its own protein.
CREATE TABLE IF NOT EXISTS target_orthologues (
    target_chembl_id   TEXT PRIMARY KEY REFERENCES targets(chembl_id),
    accession          TEXT NOT NULL,    -- the record's own UniProt accession
    tax_id             INTEGER NOT NULL,
    human_accession    TEXT,             -- NULL unless status = 'matched'
    best_accession     TEXT,             -- the best human hit, matched or not
    identity           REAL,             -- to best_accession, over the shorter sequence
    runner_up          TEXT,             -- the next-best human protein
    runner_up_identity REAL,
    coverage           REAL,             -- shorter length / longer length
    status             TEXT NOT NULL     -- 'matched', or the rule that refused it
);

-- The adverse effects drug labels list, from OnSIDES (v3.1.1, pinned; a model's
-- reading of US, UK, EU and Japanese labels into MedDRA terms), written only by
-- scripts/resolve_cohort_label_effects.py. An answer key for the similarity
-- harness and nothing else: never on the page, never evidence about a target,
-- never part of the score (docs/SIMILARITY-LITERATURE.md, step 3).
--
-- A molecule reaches its RxNorm ingredient by the FDA classes' route (InChIKey
-- -> UNII -> ingredient), and only labels whose products are that one
-- ingredient are read: a combination's effects are its partner's too. Two
-- molecules can share an ingredient (haloperidol and haloperidol decanoate),
-- and then share every row here.
CREATE TABLE IF NOT EXISTS label_effect_molecules (
    parent_molregno  INTEGER PRIMARY KEY REFERENCES molecules(parent_molregno),
    rxcui            TEXT NOT NULL,     -- the RxNorm ingredient
    n_labels         INTEGER NOT NULL,  -- its single-ingredient labels in OnSIDES
    labels_by_source TEXT NOT NULL      -- the same, by country ('JP:2|UK:4|US:120')
);

-- One row per molecule and effect: on how many of the molecule's labels it
-- appears, and in which sections (OnSIDES's AR adverse reactions, BW boxed
-- warning, WP warnings and precautions, NA a label not split into sections).
CREATE TABLE IF NOT EXISTS label_effects (
    parent_molregno  INTEGER NOT NULL REFERENCES molecules(parent_molregno),
    effect           TEXT NOT NULL,     -- a MedDRA code: the PT where the term reaches one,
                                        -- else the OnSIDES term's own (label_effect_terms)
    n_labels         INTEGER NOT NULL,
    sections         TEXT NOT NULL,     -- '|' joined, 'AR|WP'
    PRIMARY KEY (parent_molregno, effect)
);

-- How each OnSIDES term the catalogue's labels use was placed in MedDRA's
-- hierarchy, which OnSIDES does not carry: through ADReCS v3.3 (pinned), by PT
-- code, or for an LLT by its exact name among one PT's synonyms. An LLT naming
-- several PTs is never resolved to one of them.
CREATE TABLE IF NOT EXISTS label_effect_terms (
    term             TEXT PRIMARY KEY,  -- the MedDRA code OnSIDES gives
    term_type        TEXT NOT NULL,     -- 'PT' | 'LLT'
    name             TEXT NOT NULL,
    effect           TEXT NOT NULL,     -- what label_effects counts it as
    placement        TEXT NOT NULL,     -- 'pt' | 'llt_one' | 'llt_several' | 'unplaced'
    socs             TEXT               -- '|' joined MedDRA SOC codes; for llt_several those
                                        -- every candidate PT shares; NULL when unplaced
);
