-- SubNetwork database schema
-- A drug-target interaction network: molecules <-> targets, with mechanism-of-action
-- edges, and per-interaction source provenance so every edge is traceable back to
-- the public dataset it came from.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS molecules (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    chembl_id           TEXT UNIQUE,
    pubchem_cid         INTEGER UNIQUE,
    iupac_name          TEXT,
    molecular_formula   TEXT,
    molecular_weight    REAL,
    smiles              TEXT,
    inchikey            TEXT,
    -- English Wikipedia article, resolved through Wikidata from an exact
    -- identifier match (never a name search - see resolve_wikipedia_urls).
    -- NULL when no article is linked to the matching Wikidata item, which is
    -- a real answer: this project would rather show no link than a plausible
    -- wrong one.
    wikipedia_url       TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    id                  INTEGER PRIMARY KEY,
    gene_symbol         TEXT NOT NULL UNIQUE,
    protein_name        TEXT,
    uniprot_accession   TEXT UNIQUE,
    chembl_target_id    TEXT,
    organism            TEXT DEFAULT 'Homo sapiens',
    function_summary    TEXT,
    -- Brain/CNS expression is curated (not all source APIs expose clean
    -- structured tissue data), so it carries its own note + citation.
    expressed_in_brain  INTEGER,   -- 1 = yes, 0 = no, NULL = unknown/unverified
    expression_note     TEXT,
    -- English Wikipedia article, resolved through Wikidata from an exact
    -- identifier match (never a name search - see resolve_wikipedia_urls).
    -- NULL when no article is linked to the matching Wikidata item, which is
    -- a real answer: this project would rather show no link than a plausible
    -- wrong one.
    wikipedia_url       TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

-- One row per (molecule, target, action_type) edge in the network.
CREATE TABLE IF NOT EXISTS interactions (
    id                   INTEGER PRIMARY KEY,
    molecule_id          INTEGER NOT NULL REFERENCES molecules(id),
    target_id            INTEGER NOT NULL REFERENCES targets(id),
    action_type          TEXT,      -- e.g. ANTAGONIST, AGONIST, INHIBITOR, ACTIVATOR
    mechanism_of_action  TEXT,      -- human-readable description
    is_primary_mechanism INTEGER DEFAULT 0,  -- 1 for the curated top-line MOA (e.g. ChEMBL "mechanism" record)
    binding_value        REAL,      -- e.g. Ki, median across replicate assays
    binding_type         TEXT,      -- e.g. 'Ki'
    binding_units        TEXT,      -- e.g. 'nM'
    n_measurements        INTEGER,  -- number of assay measurements the median is based on
    -- Cell-based functional-assay corroboration (e.g. cAMP/Ca2+ response,
    -- Kb from Schild analysis) of the same molecule/target/action_type,
    -- pooled and reduced the same way as binding_value but kept in
    -- separate columns rather than merged into one median - a functional
    -- potency is not the same physical quantity as a binding affinity
    -- (receptor reserve and signal amplification can shift it), so mixing
    -- the two into a single number would misrepresent both. Deliberately
    -- excludes whole-organism (in-vivo) functional data: those assays
    -- report a phenotypic/physiological outcome (e.g. urine output in a
    -- dosed rat) without attributing it to a specific molecular target, so
    -- they can't be mapped onto this schema at all (see CLAUDE.md).
    functional_value            REAL,
    functional_type             TEXT,      -- e.g. 'EC50', 'Kb'
    functional_units            TEXT,      -- e.g. 'nM'
    functional_n_measurements   INTEGER,
    created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (molecule_id, target_id, action_type)
);

-- Public datasets this project draws from.
CREATE TABLE IF NOT EXISTS sources (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,  -- 'PubChem', 'ChEMBL', 'DGIdb', 'UniProt'
    base_url       TEXT,
    accessed_date  TEXT,
    -- Which snapshot of the source backed this build, when the source is
    -- versioned and was read offline (e.g. 'chembl_37'). NULL means the
    -- source was queried live, in which case accessed_date is the only
    -- version information there is. Without this a database built from the
    -- local ChEMBL dump could not state which release its numbers came from.
    source_release TEXT
);

-- Which source(s) support which interaction edge, with the external record id
-- so a claim can be traced back to the exact upstream record.
CREATE TABLE IF NOT EXISTS interaction_sources (
    interaction_id      INTEGER NOT NULL REFERENCES interactions(id),
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    external_ref        TEXT,   -- e.g. ChEMBL assay id, DGIdb gene name
    -- A reference that is NOT one of this edge's measurements, and therefore
    -- cannot appear in `measurements`. Only two things qualify (see
    -- citation_kind), so on most rows these are NULL by design.
    --
    -- They used to hold a *sampled* citation instead: reduce_measurements
    -- collapsed every row from a source into one dict entry, last-write-wins,
    -- so the citation shown here was whichever measurement ChEMBL happened to
    -- deposit last. 84 of 133 links carried such a sample. It read as an
    -- independent reference for the edge and was nothing of the kind - the
    -- same paper was already listed, with the number it actually supports,
    -- under `measurements`. Nobody chose it and reversing the loop would have
    -- shown a different one, so it is no longer written at all.
    citation_url         TEXT,
    -- Short human-readable citation (paper title, or "<journal> (<year>)",
    -- or PDSP's own free-text Reference field) to show next to the link.
    citation_text        TEXT,
    -- What kind of claim the citation above supports. NULL whenever there is
    -- no citation, which is the common case.
    --   'mechanism'  - ChEMBL's drug-level reference for a curated MOA (FDA
    --                  label or review). Explains why the edge has an
    --                  action_type at all; is not evidence for any single
    --                  pooled value, and is typically a review rather than a
    --                  primary study.
    --   'annotation' - the reference a source cites for asserting the edge
    --                  exists when it contributes no measurement (DGIdb).
    -- Stored rather than inferred from `role`: "this citation is a
    -- drug-level MOA review, not a measurement" is a claim about the data,
    -- and the viewer labels the two differently. Leaving it to be guessed
    -- downstream is how the sampled citation went unnoticed for so long.
    citation_kind        TEXT,
    -- No data_validity_note here. A source's quality flag (e.g. ChEMBL's
    -- "Outside typical range" comment) is always about one measurement, and
    -- this table has one row per (source, role), so storing it here meant
    -- sampling it the same way the citation was: 13 links carried a flag
    -- where the underlying measurements carried 20, and which 13 depended on
    -- iteration order. Flags live on `measurements`, next to the value they
    -- actually apply to.
    -- What this source contributed to the edge. One source can back the same
    -- edge in more than one capacity - ChEMBL routinely supplies both a
    -- binding assay and a separate functional assay for the same
    -- molecule/target - and those are different records with different
    -- citations, so they get their own rows rather than one overwriting the
    -- other (which silently discarded the functional assay ID on every edge
    -- carrying both).
    --   'binding'    - contributed to binding_value's pooled median
    --   'functional' - contributed to functional_value's pooled median
    --   'annotation' - corroborates that the edge exists, with no
    --                  measurement of its own (e.g. a DGIdb gene claim)
    role                 TEXT NOT NULL DEFAULT 'binding',
    PRIMARY KEY (interaction_id, source_id, role)
);

-- One row per individual measurement pooled into an interaction's binding or
-- functional value.
--
-- This answers a different question from interaction_sources, and conflating
-- the two is what made the viewer's edge panel misleading. interaction_sources
-- answers "which databases back this edge" - one row per (source, role), so
-- thirteen ChEMBL binding measurements collapse into a single row carrying no
-- citation at all. n_measurements, meanwhile, counts measurements.
-- Showing "n=13" beside "Sources (3)" invited a comparison that neither number
-- supported, and ~230 of the ~290 citations behind this database's pooled
-- values had no representation in the viewer at all.
--
-- Deliberately NOT deduplicated and with no UNIQUE constraint: two identical
-- values from two different assays are two measurements. The invariant is
-- COUNT(*) WHERE counted = 1 AND role = 'binding' == interactions.n_measurements
-- (and likewise for functional), which is asserted in the test suite.
CREATE TABLE IF NOT EXISTS measurements (
    id                  INTEGER PRIMARY KEY,
    interaction_id      INTEGER NOT NULL REFERENCES interactions(id),
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    -- 'binding' or 'functional'. No 'annotation': an annotation is by
    -- definition not a measurement, which is exactly why DGIdb appearing in
    -- the source list never corroborated n.
    role                TEXT NOT NULL,
    affinity_type       TEXT NOT NULL,   -- Ki / Kd / IC50 / EC50 / AC50 / Kb
    value               REAL NOT NULL,
    units               TEXT NOT NULL DEFAULT 'nM',
    -- 1 if this row entered the pooled median and n_measurements; 0 if it is
    -- recorded for its citation but excluded from both. Currently only
    -- BindingDB rows superseded by a non-BindingDB source for the same
    -- affinity type (see reduce_measurements' docstring on republication).
    -- Stored rather than recomputed so the viewer can show what was excluded
    -- and say why, instead of silently omitting it.
    counted             INTEGER NOT NULL DEFAULT 1,
    -- The specific upstream record: a ChEMBL assay id, a BindingDB monomerid,
    -- a PDSP row number. Unlike interaction_sources.external_ref, this one is
    -- never overwritten by a later measurement from the same source.
    external_ref        TEXT,
    -- This measurement's own paper - not the edge's drug-level mechanism
    -- reference. On a curated-mechanism edge those differ: the mechanism
    -- citation is a review, while each measurement has its own primary study.
    citation_url        TEXT,
    citation_text       TEXT,
    data_validity_note  TEXT,
    -- What this assay actually measured, in the source's own words (ChEMBL's
    -- assay description; NULL for PDSP and BindingDB, which expose no
    -- equivalent). Already fetched on both ChEMBL backends and previously
    -- only printed to the console.
    --
    -- Without it, several rows from one paper look like replicates of one
    -- experiment. Rolipram/PDE4D is the clearest case in this database: five
    -- functional IC50s spanning 41-17000 nM, all from PMID 16263279, are not
    -- repeats but five different readouts - one whole-blood LTE4 release
    -- assay plus four eosinophil-chemotaxis assays driven by different
    -- chemoattractants. The pooled median is a median over unlike
    -- quantities, and nothing in the panel said so. ChEMBL's unit of record
    -- is the assay, not the paper, so this is the field that distinguishes
    -- "measured five times" from "measured five different things".
    assay_description   TEXT
);

CREATE INDEX IF NOT EXISTS idx_interactions_molecule ON interactions(molecule_id);
CREATE INDEX IF NOT EXISTS idx_interactions_target ON interactions(target_id);
CREATE INDEX IF NOT EXISTS idx_measurements_interaction ON measurements(interaction_id);

-- Which of this database's `targets` rows are subunits of one physical
-- protein assembly, so the graph can draw one hull around them instead of
-- letting a similarity claim ("shares a target") multiply by the number of
-- subunits one experiment happened to be attributed to. Derived once,
-- offline, from the local ChEMBL bulk release, keyed on identifiers only -
-- never a gene symbol or name (invariants 6 and 15) - by
-- load_target_complexes in build_db.py.
--
-- ChEMBL's protein_classification tree must NOT be used for this: it is a
-- sequence/function taxonomy, blind to assembly. Checked directly against
-- the release - CACNA1C and CACNA1D land on the identical leaf "Voltage-
-- gated calcium channel" despite being two different channels (Cav1.2,
-- Cav1.3), while CACNB2, which physically co-assembles with CACNA1C into
-- one channel, sits under "Auxiliary transport protein" and shares nothing
-- with it below the root. It merges what should stay apart and splits what
-- should join.
--
-- target_dictionary.target_type is the field that actually answers the
-- assembly question:
--   'PROTEIN COMPLEX'       - ChEMBL asserts the exact subunit composition
--                              (e.g. GABA-A alpha1/alpha2/beta2/gamma2).
--   'PROTEIN COMPLEX GROUP' - ChEMBL's own definition: "a poorly defined
--                              protein complex, where subunit composition
--                              is unclear" (e.g. its 26-member "Voltage-
--                              gated calcium channel" group, which lumps L-,
--                              N-, P/Q-, R- and T-type channels together).
-- Both kinds are recorded here; export_graph.py's resolve_groups decides how
-- to reconcile one against the other where their membership overlaps.
CREATE TABLE IF NOT EXISTS target_complexes (
    chembl_id       TEXT PRIMARY KEY,   -- target_dictionary.chembl_id of the assembly
    name            TEXT NOT NULL,      -- target_dictionary.pref_name
    target_type     TEXT NOT NULL,      -- 'PROTEIN COMPLEX' or 'PROTEIN COMPLEX GROUP'
    n_components    INTEGER NOT NULL,   -- components ChEMBL lists, including ones absent here
    source_release  TEXT,               -- which snapshot this was derived from
    -- English Wikipedia article for the assembly as a whole, resolved
    -- through Wikidata - but, unlike molecules.wikipedia_url and
    -- targets.wikipedia_url above, not from an identifier ChEMBL supplies.
    -- There is no member-accession walk on Wikidata that reaches the right
    -- concept (see COMPLEX_WIKIDATA_ITEMS in build_db.py for what was tried
    -- and why it was confidently wrong or silent); the ChEMBL-id-to-
    -- Wikidata-item identity is hand-curated there instead, and only that -
    -- the article itself is still resolved from that item at build time,
    -- through the same apply_articles ambiguity check as the other two
    -- columns, so a page move or rename is picked up automatically. NULL
    -- both where an assembly has no entry in that map yet and where it does
    -- and the entry is deliberately None (e.g. the IKs channel, which has
    -- no English article of its own) - either way, a real answer this
    -- project would rather show than a plausible wrong one.
    wikipedia_url   TEXT
);

-- Which of this database's own targets sit inside which assembly, matched to
-- ChEMBL's target_components by UniProt accession *exactly* - never a gene
-- symbol or name. A complex with fewer than two members present in this
-- database is not stored at all (see load_target_complexes): a "complex" of
-- one target isn't a grouping of anything this graph can draw.
CREATE TABLE IF NOT EXISTS target_complex_members (
    complex_chembl_id  TEXT NOT NULL REFERENCES target_complexes(chembl_id),
    target_id          INTEGER NOT NULL REFERENCES targets(id),
    PRIMARY KEY (complex_chembl_id, target_id)
);

CREATE INDEX IF NOT EXISTS idx_target_complex_members_target
    ON target_complex_members(target_id);
