# SubNetwork

An explorable network map of drug–target interactions, built from public
bioinformatics databases. Click caffeine, see its receptors, and see which
other molecules act on them.

This file is the rules and the current state; the reasoning lives in `docs/`,
indexed by **[docs/INDEX.md](docs/INDEX.md)**, which says which documents are
in force and which are proposals or history. Four of them to read before the
change they govern:

- **[docs/DATA-QUALITY-LOG.md](docs/DATA-QUALITY-LOG.md)** — before changing how
  any value gets into the database. Every invariant below is an incident there.
- **[docs/VIEWER.md](docs/VIEWER.md)** — before changing what the page draws,
  scores or says. **The viewer** below lists its rules; that file is why.
- **[docs/COHORT-1-DECISIONS.md](docs/COHORT-1-DECISIONS.md)** and
  **[docs/COHORT-2.md](docs/COHORT-2.md)** — the adopted policy, decision by
  decision (D01–D16, then D17 on).
- **[docs/PUBLISHING.md](docs/PUBLISHING.md)** — before republishing the page.

**A document goes into `docs/` as a markdown file, never into a claude.ai
artifact or Claude Doc** (the user's rule, 2026-10-10): a write-up, a draft
email, a review or a proposal lives in the repository, is listed in
[docs/INDEX.md](docs/INDEX.md), and is committed with the work it records. The
viewer is hosted on Cloudflare; its claude.ai artifact was deleted 2026-10-10.

The catalogue is built from ChEMBL 37, with GtoPdb laid on it as
directions (D17) and, at primary targets, curated claims (D18); its size is stated once, in **Status**, generated from the
database rather than typed.
[docs/COHORT-REPORT.md](docs/COHORT-REPORT.md) measured selection policies that
were **not** adopted, and its totals are historical.

## Two pipelines

There are two, and only one produces the artifacts the page opens.

**The cohort pipeline is current.** `scripts/build_cohort.py` builds
`db/cohort1.db` from ChEMBL 37 against two versioned policies in `config/`, a
handful of backfills add what ChEMBL does not have, and
`scripts/export_cohort.py` writes `viz/graph.data.js`, `viz/gtopdb.data.js`
and `viz/evidence/`. `viz/index.html` reads those.

**The seed pipeline is legacy, and is the rollback path — do not modify it.**
`scripts/build_db.py` builds `db/subnetwork.db` from six live sources for the 28
seed molecules and `viz/legacy/index.html` displays it. Nothing in the cohort
pipeline reads any of it. Its schema, how to run it, its history and its
backlog are in [docs/LEGACY-PIPELINE.md](docs/LEGACY-PIPELINE.md); the rules it
taught are the **Invariants** below.

## Goal

Make it possible to **see which molecules may act in similar ways in the
brain**, by drawing what they act on and how well each of those claims is
evidenced.

Two molecules are related here when they act on the same targets. That makes
the *graph* the deliverable rather than a readout of the database: what a
selection lights up, what collapses into a single row, and what is allowed to
count as an overlap are all part of the claim being made. A change that leaves
the data correct and the picture misleading has not worked.

Shows, for a non-expert:

- **Molecules** — drugs, compounds, natural substances
- **Targets** — the proteins they act on (initial focus: brain-expressed)
- **Mechanisms** — how the molecule acts on each target (agonist, antagonist,
  inhibitor, …)
- **Evidence** — how much of it stands behind each claim, and how much of that
  is independent

Exploratory and educational. Mechanistic, not dosing or safety guidance.

Similarity here means **shared targets, weighted by evidence, discounted by how
common the target is, and divided by how much each molecule does** — a much
weaker claim than "these two drugs act alike". A protein is one target whatever
species ChEMBL recorded it in (D20): naloxone and naltrexone's "12 shared
targets" were three opioid receptors in up to four species and CYP2D6, and now
read 4, with a repeat across species worth a diminishing √n rather than nothing. It knows nothing about dose,
exposure, or whether a molecule reaches the brain at all.

The last two of those four were added after the harness measured what the first
two were doing on their own, and they answer failures the arguments had missed.
*Prevalence*: a target almost everything is measured at says almost nothing
about the pair that shares it, and scored flat, the hERG cardiac screen made
meperidine's nearest neighbour an antidepressant while its opioid classmate sat
at rank 50. *Normalisation*: an unnormalised sum rewards breadth, so the
best-studied molecules came out as everything's nearest neighbour — aripiprazole
was the top answer for 14 of the 395 ATC-labelled molecules, and haloperidol's
nearest neighbour was aripiprazole rather than clozapine. Both are recorded
with their measurements in
[docs/SIMILARITY-HARNESS.md](docs/SIMILARITY-HARNESS.md).

Cohort 1 does now carry ChEMBL's
family and complex-group targets as first-class identities, so two molecules
that both have a claim at the *Adenosine receptor* family do share that target;
but two molecules measured separately at ADORA1 and ADORA2A still score zero
against each other, because those are two proteins and nothing here says
otherwise. A family or complex-group overlap is counted at half the weight of
an exact single-protein overlap and shown as a different thing, since it is a
claim about a set rather than a hit on a subtype — except where the pair already
shares every protein in that set individually, which is a repeat of what has
been counted rather than a second overlap, and is kept, listed and counted once.

Direction enters in one direction only (D15). Where ChEMBL or GtoPdb (D17)
curates both molecules at a shared protein and the two actions are opposite, the
row says so, and a pair whose every known direction is opposite scores at a
quarter — caffeine and adenosine share four adenosine receptors and are an
antagonist and an agonist at them. Agreement is never a bonus, because most
claims here carry no curated direction at all and rewarding the ones that do
would make ChEMBL's silence look like a disagreement. It is a place to start
looking, not a verdict.

## Running it

```bash
python3 scripts/build_cohort.py            # stage, validate, activate db/cohort1.db
python3 scripts/build_cohort.py --stage-only   # build and validate, change nothing
python3 scripts/build_cohort.py --activate     # activate an existing staged build

# backfills: run after a build (a rebuild wipes them), before the export
python3 scripts/resolve_cohort_trials.py       # trial_status from ClinicalTrials.gov (~20 s)
python3 scripts/resolve_cohort_protein_class.py  # target_components.protein_class (offline)
python3 scripts/resolve_cohort_approved_elsewhere.py  # molecules.approved_elsewhere (offline)
python3 scripts/resolve_cohort_classes.py       # ATC codes and USAN stems (offline)
python3 scripts/resolve_cohort_pharm_actions.py # MeSH pharmacological actions via FDA UNII and Wikidata (minutes)
python3 scripts/resolve_cohort_mesh_structure.py # MeSH structure classes via FDA UNII (~35 s)
python3 scripts/resolve_cohort_wikipedia.py    # Wikipedia links via Wikidata and infoboxes; after the MeSH classes
python3 scripts/resolve_cohort_gtopdb_actions.py # GtoPdb curated actions (pinned 2026.3.1, cached)
python3 scripts/resolve_cohort_orthologues.py   # target_orthologues by sequence (~2 min cold, needs parasail)

python3 scripts/export_cohort.py           # db/cohort1.db -> viz/*.data.js + viz/evidence/
python3 scripts/cohort_report.py           # the measured results of the active build
python3 scripts/cohort_report.py --write-status  # refresh the generated block in ## Status
python3 scripts/cohort_report.py --check-status  # exit 1 if that block is stale

node analysis/similarity_harness/evaluate.mjs   # grade the similarity ranking
node analysis/similarity_harness/evaluate.mjs --key mesh   # ...against MeSH actions instead of ATC
node analysis/similarity_harness/sweep.mjs      # what each scoring constant is worth

python3 -m unittest discover -s tests      # pipeline
node --test "tests/*.test.mjs"             # viewer + harness
```

Then open `viz/index.html` directly in a browser — no server, no network, no
build step. Suite sizes are in **Status**, generated from the runners, because
a count written beside a command is the first thing to go stale. The harness
commands are read-only measurement, not part of a build; they read
`viz/graph.data.js` and `viz/gtopdb.data.js` and report a missing payload
rather than a bad grade when there is none
([docs/SIMILARITY-HARNESS.md](docs/SIMILARITY-HARNESS.md)).

ChEMBL is read from `$CHEMBL_SQLITE_PATH`, defaulting to the path under
`/mnt/data/chembl/` named in **Sources**. Starting from a fresh clone (where to
download ChEMBL 37, its checksum, and which backfills will not reproduce
exactly) is [docs/REPRODUCING.md](docs/REPRODUCING.md).

The build takes about 20 seconds and the export about 6. It is restartable and
idempotent: it always writes a fresh `db/staging/cohort1.db` and replaces the
active database only after all 15 validation checks pass, so a rerun removes
stale derived claims and a failed run changes nothing; the export clears
`viz/evidence/` first for the same reason. ChEMBL is opened `mode=ro`
throughout. Backups land in `db/backups/` and `viz/backups/`; rollback commands
are in [docs/COHORT-1-IMPLEMENTATION.md](docs/COHORT-1-IMPLEMENTATION.md).

**The build reads ChEMBL alone; every network source is a backfill.** Each one
changes only its own table or columns, never which molecules, targets or claims
exist, and each is idempotent with `--dry-run`. Each is identifier-only
(invariant 15). A target gets a Wikipedia link only when it has exactly one
component accession: every complex, complex group and family stays NULL on
purpose — the legacy pipeline derived one from members' accessions twice and
was confidently wrong both times — and so do the one SINGLE PROTEIN ChEMBL files
against three accessions (`CHEMBL3390824`, lanosterol 14-alpha demethylase) and
the two targets it gives no accession at all. Where a protein's item and its
gene's item carry different articles, the protein's own is taken (Albumin:
*Human serum albumin*, not *Serum albumin*), unless the protein item names two
genes (HSPA1A's carries the *HSPA1B* article). A molecule Wikidata finds no
article for is linked by the article whose drug or chemical infobox names its
own parent ChEMBL ID, found through Wikipedia's index of ChEMBL links — never
through a salt form's ID (ChEMBL files a deuterated drug as a form), and
refused where that infobox's InChIKey has a different skeleton or two
articles qualify (PBF-509 to *Taminadenant*, whose Wikidata item is empty;
[DATA-QUALITY-LOG](docs/DATA-QUALITY-LOG.md), 2026-10-13). A MeSH structure class is linked
through the one Wikidata item carrying its descriptor, or, where that item has
no English article (Xanthines), through the main article its English category
declares — never by its name, and never for a MeSH action, where that route
reaches topics rather than classes. The counts are in **Status**.
Pinned upstream files (MeSH, FDA UNII, GtoPdb, UniProt's human proteome) are
cached under `db/cache/` and recorded by sha256 in `build_manifest`.

**To change what is in the catalogue, edit `config/cohort1_selection.json` and
rebuild.** `SEED_MOLECULES` decides which molecules are labelled seeds and kept
regardless of the clinical policy, not membership; a seed is never
grandfathered into the cohort, and both facts are on every entry.

Both suites run offline and need nothing installed beyond `requirements.txt`;
the one test that runs parasail skips itself without it. The viewer tests load the
page's inline `<script>` into a `vm` sandbox (`tests/cohort_harness.mjs`) rather
than importing it, so the page stays one self-contained file with no build step.

## Layout

```
config/cohort1_selection.json  versioned membership policy: scope, routes, phase, seeds
config/cohort1_evidence.json   versioned trust policy: bases, endpoints, tiers, conversions
db/schema_cohort.sql      every table of the cohort database (see Data model)
db/cache/                 pinned upstream files for the backfills (gitignored)
scripts/build_cohort.py   CLI: stage, validate, activate db/cohort1.db
scripts/resolve_cohort_*.py  the backfills listed under Running it
scripts/export_cohort.py  CLI: db/cohort1.db -> viz/*.data.js + viz/evidence/
scripts/cohort_report.py  CLI: the active build's results; --write/--check-status
scripts/deploy_cloudflare.sh  deploy the page (docs/PUBLISHING.md)
scripts/privacy_check.py, .githooks/  keep a home path, a personal address or a
                          session link out of this public repository, on
                          every branch pushed
scripts/cohort/           the pipeline - scope, selection, targets, evidence,
                          classes, store, build, validate, export, report, status
viz/index.html            the page: self-contained, vendored vis-network
viz/graph.data.js         startup payload: catalogue, targets, ChEMBL's claims
viz/gtopdb.data.js        GtoPdb's part, apart for its licence (ODbL / CC BY-SA 4.0)
viz/evidence/             per-molecule evidence shards, loaded on demand
tests/test_cohort_*.py    offline pipeline and backfill tests; test_cohort_status
                          fails when the generated Status block is stale
tests/cohort_viewer*.test.mjs  what the page claims; cohort_harness.mjs loads it
tests/similarity_harness.test.mjs  holds the similarity grade to a floor
analysis/similarity_harness/  grades the ranking against ATC level-4 classes
                          (harness, evaluate, sweep). Read-only; adopts nothing.
analysis/probe/           50 settled drug relationships put to the ranking, and
                          what went wrong where it misses. A diagnostic, never a
                          tuning target; read-only.
analysis/wiki_comparison/ a nootropics wiki's compound list placed against
                          ChEMBL and the catalogue, by name. Read-only.
analysis/answer_keys/     what the ATC answer key calls a miss, and whether it
                          is one (docs/SIMILARITY-LITERATURE.md). Read-only.
analysis/cohort1/         the read-only analysis behind COHORT-REPORT.md
analysis/mesh_route_b/    MeSH actions through the FDA UNII against the PubChem
                          route (docs/MESH-ACTIONS-ROUTE-B.md); read-only
docs/                     the reasoning; docs/INDEX.md is the index
README.md, CONTRIBUTING.md, SECURITY.md, CITATION.cff  for people arriving at
                          the repository; this file stays the rulebook

legacy - the rollback path, not to be modified (docs/LEGACY-PIPELINE.md):
db/schema.sql, scripts/build_db.py, scripts/chembl_local.py,
scripts/export_graph.py, viz/legacy/, tests/test_build_db.py, tests/legacy_*
```

## Data model

### The cohort database (`db/schema_cohort.sql`)

The schema file's comments are the column-level reference; this is what each
table is for and the rule that is easy to break.

**`molecules`** holds one row per **chemical parent**, with `in_cohort` and
`is_seed` as separate columns — a seed is never grandfathered into the clinical
cohort and a clinical member is not a seed. Every entry carries its admission
route or exclusion reason, its indication-scope reasons, its ATC and identity
flags, and an `evidence_status`. **`molecule_forms`** keeps every salt, hydrate
and formulation folded onto the parent, including the id a seed was seeded
under (theophylline was seeded as `CHEMBL1355736` and lives as `CHEMBL190`), and
both identities stay searchable.

**`molecule_indications`** holds every in-scope disease, qualifying or not, with
the phase it reached and the ClinicalTrials.gov NCT ids ChEMBL cites
(`trial_ids`); near misses are kept because "loperamide's pain indication is
Early Phase 1" is the answer to why it is not a member. `max_phase` is the
furthest stage across every disease and is not the admission test.
`n_indications_chembl` counts every disease ChEMBL has, so the in-scope list can
say how much of the record it shows. `approved_elsewhere` names phase-4
diseases outside the scope — display text only, never a membership input.
**`trial_status`** is each NCT id's registry status, backfilled.

**`targets`** holds one row per **ChEMBL target record** at the identity ChEMBL
asserts — `SINGLE PROTEIN`, `PROTEIN COMPLEX`, `PROTEIN COMPLEX GROUP` or
`PROTEIN FAMILY` — with deliberately no unique constraint on an accession: a
protein, a complex containing it and a family containing it are three targets
making three claims. **`target_components`** is context that lets a complex name
what it contains, and is **never read as a binding claim** about those proteins.
`protein_class` (ChEMBL levels 1–2) is a drawing hint for one viewer rule, never
a matching key or evidence.

**`claims`** holds one row per (parent, target, role, assignment basis); the
roles are `curated`, `binding` and `functional` from the build, and `gtopdb`
from the GtoPdb backfill (D18). A
claim's `tier` is computed from **distinct studies**, not measurements;
`curated_support` and `multiple_study_support` are separate flags because they
are different kinds of evidence; `supporting_endpoint_class` records which
endpoint earned the tier so a result replicated at Ki cannot certify an IC50.
**`claim_endpoints`** holds per-endpoint medians — Ki, Kd, binding IC50,
functional IC50, EC50, AC50 and Kb are never pooled — and **`claim_studies`**
one row per distinct study, which is what Supported counts.
**`curated_mechanisms`** holds ChEMBL's `drug_mechanism` rows at the target and
action level asserted; a family-level mechanism stays one record and is never
expanded onto the members. Where an action is withheld as a known error
(invariant 9), `action_type` is NULL and ChEMBL's word sits in
`excluded_action_type`, with the reason in `action_exclusion` there and on the
claim.

**`observations`** holds one row per retained ChEMBL activity. **A row with
`claim_id` NULL backs no edge** — an unassigned target, a non-molecular
assignment, a target type outside the four — and keeps its reason, so an entry
can show what exists without an edge being manufactured. `value_status`
separates an exact value from a bound, a conditional mass-basis conversion and
an unresolved one; only exact rows are `counted`.

**`exclusion_summary`, `excluded_records`, `source_coverage`, `validation`** and
**`build_manifest`** exist so a build can be audited without rerunning it: what
was dropped and why, which sources were read, which checks passed, and which
pinned inputs, policies and backfills produced the file.

**Classes — `molecule_classes` and `class_labels` — are for search and display
only.** They are never evidence about a target and never enter the similarity
score. Four sources, each writer replacing only its own rows:

- `atc` — every WHO ATC code of any form. Kept in the database, **not on the
  page** (taken off 2026-09-26: ATC files a drug by use). `molecule_atc` and
  `molecules.atc_level5` still hold only the N codes, because they are the
  admission route's record and the harness's answer key.
- `usan` — USAN/INN name stems (`-pramine`). Stems and sub-stems are paired
  positionally because a definition can contain the `"; "` that joins them
  (`-triptan`); ChEMBL's bare `-` means no stem.
- `mesh_pa` — MeSH **pharmacological actions**: each molecule is placed on
  **one** MeSH record (pinned `desc2026`/`supp2026`) and takes that record's
  own action list, with the D27 hierarchy in `class_labels.parents`. Each step
  is tried only where the one before placed nothing:
  1. the FDA UNII of its exact structure;
  2. the CAS number FDA lists for that UNII;
  3. for a structure ChEMBL draws without stereochemistry, an FDA substance
     registered as a mixture of that skeleton's stereoisomers;
  4. the MeSH ID on the Wikidata item carrying its ChEMBL ID.

  Two records at any step is a refusal. A stereo-defined molecule never
  matches by skeleton: that put esmethadone on methadone's record. It went
  through PubChem until 2026-10-13, which links compounds to MeSH by name
  (tafamidis carried triamcinolone's actions through "FX006")
  ([DATA-QUALITY-LOG](docs/DATA-QUALITY-LOG.md), 2026-10-13).
- `mesh_struct` — MeSH **chemical-structure** classes, by identifiers alone:
  InChIKey → FDA UNII (FDA registers it from the structure) → the one MeSH
  record carrying that UNII. PubChem's route was measured and rejected for
  this; a molecule reaching two records is dropped (invariant 6). Only the
  structural branches count, and a drug whose own heading is a class for
  another entry is a member of it (ketorolac under *Indomethacin*).

**`gtopdb_interactions`** holds GtoPdb's curated **action** (D17): its `Type` and
`Action` verbatim, and `action_type`, the ChEMBL word they map to through
`ACTION_MAP` in `scripts/resolve_cohort_gtopdb_actions.py` (NULL where they name
no direction). Every row is a direction on its pair; **only a primary-target
row is also evidence** (D18): the backfill writes it as a Supported claim in the
`gtopdb` role, beside ChEMBL's `curated`, and re-derives `evidence_status`. A
non-primary row creates no claim and carries no affinity; one at a pair with
no claim keeps `has_claim = 0` and is never exported. Ligands match by InChIKey or a ChEMBL id
naming one parent; targets by UniProt accession to one SINGLE PROTEIN, or a
multi-subunit GtoPdb target only to a PROTEIN COMPLEX with exactly those
accessions — never fanned out onto the subunits.

**`target_orthologues`** says which human protein each non-human, mammalian
SINGLE PROTEIN record is (D20), found by sequence because no identifier says
so: aligned to UniProt's reviewed human proteome with parasail, matched only on
a clear, reciprocal, one-to-one best match, and otherwise stored with the rule
that refused it. The viewer reads the match as `human_orthologue` and counts a
protein once in the score; **it is never a claim moved between records** — the
rat record stays the rat record, with its own claims and its own rarity.

**`wikipedia_url`** on molecules and targets is a backfill through Wikidata, on
an exact identifier, and for a molecule Wikidata cannot place, through the
ChEMBL ID its article's own infobox declares (see **Running it**). **`class_wikipedia`** holds the same
for MeSH structure classes, in a table of its own because the class backfills
rewrite their `class_labels` rows; each row records the item, and whether the
article was the item's own or its category's declared main article
([DATA-QUALITY-LOG](docs/DATA-QUALITY-LOG.md), 2026-10-09).

## Sources

What each is actually good for, and its caveat, is tabled in
[docs/DATA-QUALITY-LOG.md](docs/DATA-QUALITY-LOG.md).

**The cohort pipeline.** **ChEMBL 37** is primary, read from the bulk release at
`/mnt/data/chembl/`: curated mechanisms, binding and functional assays, and the
clinical side — `drug_indication` for what a molecule is developed for and how
far it got, `indication_refs` for the **ClinicalTrials.gov** NCT ids that phase
is read off. `indication_refs` also carries DailyMed, EMA, FDA, ATC, USAN and
INN references, none read here; DailyMed is the one worth revisiting, being the
label behind 286 of the 515 approved indications with no registered trial.
**GtoPdb** (IUPHAR/BPS Guide to Pharmacology, release 2026.3.1) supplies a curated
action on pairs ChEMBL already has (D17); its database is ODbL and its contents
CC BY-SA 4.0, credited on the page. Everything it contributes is exported to
its own `viz/gtopdb.data.js` under those terms, never into `graph.data.js`
(ChEMBL, CC BY-SA 3.0): no published compatibility joins the ODbL to CC BY-SA,
so the two stay separate files the page combines when it draws.
**MeSH** (via **FDA UNII**, and **Wikidata** where FDA files no structure)
supplies classes, **UniProt**'s reviewed human proteome (release 2026_03) the
sequences D20's orthologue matching aligns against, **ClinicalTrials.gov**
trial status, and **Wikidata** a Wikipedia link per node and a molecule's MeSH
record where FDA's route does not reach it. Both are matched on an identifier
this database already holds — never a title search: "ATM", "APP" and "TNF" are
English words. The cohort pipeline no longer reads **PubChem** (2026-10-13).

**The legacy pipeline** also reads PubChem for identity and the CAS numbers
that join into PDSP, UniProt for protein identity and tissue specificity, the
**PDSP Ki Database** (bulk CSV; no query API) and **BindingDB** for
supplementary measurements, and **DGIdb** to cross-validate that an edge
exists. Cohort 1 deferred those three (D12), and they still are.

Prefer open licences and programmatic access, so data can be refreshed rather
than hand-curated.

## Invariants

These are load-bearing. Each one exists because it was violated and the
database carried wrong data as a result.

1. **A value is only a measurement if the source says it is.** ChEMBL
   `standard_relation` must be `"="`; `">"` means "nothing detected up to this
   concentration". Same check for BindingDB (`>` prefix) and PDSP (`ki Note`).
2. **Paginate every ChEMBL list fetch.** `page_meta.next`, not the first page.
   Default ordering is by internal id, so a prefix is an arbitrary sample.
3. **Never mix affinity types in one median.** Ki > Kd > IC50, first available
   wins. Pool in log space (`pooled_affinity`), because affinities are
   log-normal.
4. **Never blend functional potency into `binding_value`.** Different physical
   quantity; separate columns, separate medians.
5. **BindingDB doesn't count toward `n_measurements`** when any other source
   reports the same affinity type — ~97% of what it returns here is
   republished ChEMBL/PDSP, not independent corroboration.
6. **Refuse to guess a gene.** `resolve_uniprot_accession` accepts only an
   exact match — on UniProt's recommended protein name for a name lookup, and
   on the entry's *primary* gene name for a gene lookup. Both of UniProt's
   searches are relevance-ranked and match synonyms, and both have returned
   the wrong protein first: `protein_name:"Tumor necrosis factor"` ranks LTBR
   above TNF, and `gene_exact:ADRA1A` ranks ADRA1D above ADRA1A, because the
   receptor cloned as "alpha-1a" was reclassified and the old name survives as
   a synonym. An ambiguous answer is refused rather than resolved. A wrong
   gene is worse than a missing one.
7. **Trust is counted in distinct studies, not in measurements.** *Changed for
   cohort 1 (decision D08).* It used to be `n_measurements`, and twenty rows
   from one paper looked like twenty opinions. Supported now means a traceable
   curated mechanism, or the same claim measured in two or more distinct
   publication-class studies **within one endpoint class**; patents and bulk
   deposits are counted and never create replication. The counting half of the
   old invariant survives intact and is still the thing that must be auditable:
   every displayed summary's measurement count must equal the rows stored
   against it with `counted = 1`, which a build check asserts across the whole
   database. What changed is that the number is an accounting fact rather than
   the trust signal. The legacy pipeline still uses the old rule.
8. **Potency is a display filter, not an import gate.** *Changed for cohort 1
   (decision D10).* `MAX_SUPPLEMENTARY_AFFINITY_NM` (300 µM) used to decide
   what reached the database, and a display control cannot undo an import
   cutoff — so the cutoff moved rather than being duplicated. Every eligible
   measurement is now stored and the filter operates over complete data, with
   presets at 1/10/100/300 µM and no cutoff by default. The reason the cutoff
   existed is unchanged and still load-bearing: weak ≠ unreal, and caffeine's
   curated ADORA3 mechanism at Ki = 100 µM is still in the catalogue at every
   threshold. A curated claim with no quantitative value is reported as hidden
   *for want of a comparable value*, never as having failed the threshold.
9. **Known-bad upstream records get an explicit, documented exclusion**
   (`CHEMBL_ASSAY_LINK_EXCLUSIONS`, `BINDINGDB_TARGET_LINK_EXCLUSIONS`) — never
   a silent drop. Exclude on *every* path the record can arrive by; the same
   bad assay reaches this pipeline from both ChEMBL and BindingDB. A curated
   action its own reference contradicts is *withheld*, never rewritten
   (`CHEMBL_MECHANISM_ACTION_EXCLUSIONS`, alfuzosin's alpha-1 AGONIST): the
   record and its curated support stay, ChEMBL's word is kept beside the
   reason, and each entry names the action it expects so the build stops if
   ChEMBL changes the row.
10. **`expressed_in_brain` is 1 or NULL, never 0 from absence.** UniProt's
    tissue comments are incomplete (ADORA1 has none at all).
11. **Escape everything in the viewer.** Paper titles and protein names reach
    `innerHTML`, and the page gets published as a shared artifact.
12. **The two ChEMBL backends must stay interchangeable.** `chembl_local`
    returns the REST API's exact dict shapes and record ordering, so
    `load_molecule` can't tell them apart and an API-vs-local rebuild diff is
    a real regression test. Ordering is load-bearing, not cosmetic: several
    reducers here take the last or first row of a tie.
13. **Never label two different quantities so they invite comparison.** The
    edge panel showed "n=13" beside "Sources (3)"; one counts measurements,
    the other counts databases, and nothing said so. Measurements are now
    listed under the value they produced, summarised where the number is
    ("median of 13 measurements" / "13 measurements from 12 papers"), and the
    heading reads "Databases" with one row per database.
14. **A per-measurement fact may not be stored per-source.** `interaction_sources`
    has one row per (source, role), so a citation or a validity flag put there
    is *sampled* — whichever row was written last. It read as independent
    corroboration and was a copy of a row already on the edge. Both fields are
    now on `measurements`; a citation still allowed on a source link must
    declare a `citation_kind` (`mechanism` or `annotation`), which `link_source`
    enforces, because the only citations that belong there are the ones that
    are not measurements.
15. **Resolve external links by identifier, never by name.** Wikipedia links
    go through Wikidata on an exact identifier match — or, where Wikidata
    reaches no article, through the identifier an article's own infobox
    declares — and an ambiguous match is dropped. This is invariant 6 applied to links: a title search answers
    confidently and wrongly, and a wrong link on a page explaining what a
    protein *is* misinforms more directly than a missing one. Where no
    identifier reaches the right item — the seven protein assemblies, where
    every derivation tried was wrong or silent — what is written down by hand
    is the Wikidata *item*, never the article title, and the article is still
    resolved from that item at build time.

## Status

Every figure between the markers below is measured from the active database,
the exported payload and the test suites, by
`python3 scripts/cohort_report.py --write-status`. They used to be transcribed
here by hand, and four of them had gone stale by 2026-09-17 while the figures
the pipeline itself computes were all still exact — so the transcription step
is gone rather than proofread. `--check-status` fails when the block and the
build disagree, and a test runs it. Everything outside the markers is
hand-written and is never rewritten.

<!-- BEGIN GENERATED: cohort-status -->
<!-- Written by `python3 scripts/cohort_report.py --write-status`. Do not edit by hand: `--check-status` fails when this block and the active build disagree, and a rewrite discards whatever was typed here. The prose outside the markers is hand-written and is never touched. -->

Pipeline and viewer both working. Current database, `db/cohort1.db`, built
2026-10-13 against the `chembl_37` bulk release under selection policy
`cohort1-selection v3.0.0` and evidence policy `cohort1-evidence v1.1.1`:

**2,452 catalogue entries · 3,359 targets · 127,741 claims · 327,957 observations**

2,449 are cohort-1 members (72 by ATC N alone, 1,905 by a qualifying
indication alone, 472 by both) and 3 are seed molecules retained outside the
cohort with their exclusion reason. 25 of the 28 seeds are admitted. 5,057
claims are Supported in the direct human basis — 2,563 by replication across
publications and 2,494 by curated mechanism, with no claim carrying both —
over 3,773 distinct molecule–target pairs. 1,497 entries have a Supported
claim, 262 only Preliminary, 75 only in the broader assignment layer, 56 only
retained observations, and 562 have no eligible evidence in ChEMBL 37 at all.
All of them stay searchable.

Behind those claims sit 327,957 retained observations resolving to 20,916
distinct studies, of which 67,035 rows are counted into a median. 86,596
bounds are kept with their relations and out of every median; 2,331
conditional mass-basis conversions are kept and counted into nothing. 22,698
organism-format rows and 4 documented known-bad records are excluded with
their reasons, and the exclusion accounting reconciles exactly to the
1,200,625 activity rows scanned. All 15 build checks pass.

What the page loads is 8.42 MB of startup payload in `viz/graph.data.js` and
0.20 MB in `viz/gtopdb.data.js`, GtoPdb's part, kept apart for its licence;
and 112.2 MB of per-molecule evidence shards across 2,046 files under
`viz/evidence/`, fetched one at a time on demand.

`molecules.wikipedia_url` and `targets.wikipedia_url` are backfilled by
`scripts/resolve_cohort_wikipedia.py` after a build: **1,746 of 2,452
molecules** and **1,599 of 2,922 single-component targets** link to an English
Wikipedia article. The other 435 multi-component targets — every PROTEIN
COMPLEX, PROTEIN COMPLEX GROUP and PROTEIN FAMILY, plus one ChEMBL-labelled
SINGLE PROTEIN carrying 3 accessions — are left NULL rather than resolved to a
guess. The 2 targets ChEMBL lists with no accession at all are left NULL for
the same reason. Of the 889 MeSH structure classes, **610** link one too, in
the `class_wikipedia` table: 523 through the Wikidata item carrying the
descriptor, and 87 whose item has no article through the main article its
English category declares (Xanthines to *Xanthine*).

The pipeline suite is 515 tests and the node suites are 701 (472 cohort
viewer, 222 legacy viewer, 7 similarity harness).

The similarity ranking is graded by `analysis/similarity_harness/evaluate.mjs`
against ATC level-4 classes, which are the WHO's own grouping of drugs by how
they work and are read from `molecules.atc_level5` rather than written here:
**top-1 32.7% and MRR 0.4607** over 284 of 395 labelled molecules in 64
classes. The other 111 have no same-class peer anywhere in their list, which
is a fact about ChEMBL's coverage rather than about the ranking, and is kept
out of the rates for that reason. It is a proxy and not ground truth — ATC
groups partly by mechanism, so the measure flatters any weighting term that
rewards curation.
<!-- END GENERATED: cohort-status -->

Three browser measurements sit outside the block because they were taken once,
in Chrome, against a 4.03 MB payload: parse and index in 216 ms, selecting a
molecule in 0.1 ms, loading an evidence shard in 10 ms. Parse and index were
unchanged at the later 4.4 MB (159 ms in the vm harness, which is not the
browser and is quoted only as a before-and-after). D21 nearly doubled the
payload to 8.4 MB, and the browser has not been timed against it. The last
Wikipedia backfill (2026-10-13) had 0 failed lookups and 10 dropped as
ambiguous (3 molecules, 6 targets, 1 class; invariant 15), and refused 3
infobox matches whose structure differs — facts about that run, not the
database, so not generated. The ATC grade above fell with D21 because the
1,119 molecules it admitted carry no ATC N code: one ranked above a class-mate
is a miss however apt. Skipped in each list, the same build grades 38.7% and
MRR 0.5121, as before them
([docs/SIMILARITY-HARNESS.md](docs/SIMILARITY-HARNESS.md) §11). Full build numbers, the two
analysis defects the build corrects, the limitations and the rollback commands
are in [docs/COHORT-1-IMPLEMENTATION.md](docs/COHORT-1-IMPLEMENTATION.md).

## The viewer

The viewer is `viz/index.html`: a single self-contained page that opens
from `file://`, draws `viz/graph.data.js` with `viz/gtopdb.data.js`
merged in at load, and loads per-molecule
evidence from `viz/evidence/` shards on demand. Full reasoning —
measurements, false starts, exact examples — lives in
[docs/VIEWER.md](docs/VIEWER.md) and must be read before changing any
behaviour a rule here describes.

**What's drawn vs. what's in the catalogue**

- **`claimVisible` decides what's in the picture; only the four claim
  filters (tier, basis, potency, curated mechanism) may change that.**
  Canvas control, viewport culling, line colour and protein-group
  linking answer "drawn/on screen/what colour" instead, invisible to
  panels, ranking, gaps and search.
- **"Hide single-molecule targets" is a drawing rule, not
  eligibility.** It removes 810 fringe proteins from the canvas, but
  caffeine's 59 claims and 265 shared-target rows are unchanged either
  way.
- **Edge culling is an exact viewport clip, not a bounding-box test,
  and never drops haze edges mid-gesture.** A box test kept 9,876 of
  12,835 edges at zoom 2.0 where the clip keeps 60; dropping haze on
  drag (tried, reverted) hid a selection's own lines to its targets.
- **A click asks the lit picture first (`pickLit`): the selection's
  nodes and lines, then the second hop, a line caught within 8 screen
  pixels at any zoom; only with nothing lit near does vis's own pick
  stand.** vis takes any node first, then the nearest of all 12,835
  lines within 10 canvas units — 0 of 12 clicks beside preladenant's
  lines opened them.
- **A protein's label is its gene symbol, never ChEMBL's full name; a
  group keeps its own shortened name; the lit selection's label is
  never hidden.** One symbol standing for a group asserts the merge
  D06 refuses; vis dims a node's shape by opacity but not its label,
  so the label dims by colour instead.

**Similarity scoring**

- **Tier and basis default open, with the prevalence discount and
  normalisation shipped in the same change, and opening only one of
  the two is worse than opening neither.** Strict, the median entry
  reaches one target and 84% of lists tie for top score; opened
  against the old unnormalised sum the ranking got *worse*. One
  filter open alone grades 33.2%/35.5%, both strict 38.2%, both open
  42.4% — no safe middle setting.
- **One protein is one shared target across species (D20): its strongest
  record counts, × n^0.5 for n species' records (`SPECIES_EXPONENT`), and
  each molecule's target count is in proteins.** Counted strictly once the
  grade falls 1 point (ATC) and 2.2 (MeSH), because a class's defining target
  is the one assayed across species; 1.0 would let two species equal two
  proteins, the ordering the rule exists to prevent.
  `proteinKey`/`proteinOf` are the only matching key — never a gene symbol —
  and direction and subsumption use them too.
- **A family/complex overlap that only repeats proteins already shared
  is not a second shared target, unless the repeat is partial.**
  Caffeine/theophylline's shared family read "6 shared targets" for
  five proteins before this; lidocaine's ten-protein family keeps half
  weight since 8 of 10 are shared nowhere else. A `PROTEIN COMPLEX` is
  never subsumed — one assembly, not a set.

**Direction and opposition (decision D15)**

- **An opposite is not a likeness.** Adenosine ranked 2nd for caffeine
  at 3.60 though ChEMBL curates caffeine ANTAGONIST and adenosine
  AGONIST at the same family — the one error stating the reverse of
  the truth.
- **`OPPOSED_ACTIONS` never folds ChEMBL's 23 actions into
  direction families; `OPPOSED_PAIR_FACTOR` is 0.25, never 0, only
  ever down.** Of 1,723 overlaps with two curated actions, only 508
  are true opposites. Partial-vs-inverse-agonist came off the list for
  the same reason: ChEMBL uses INVERSE AGONIST on 4 claims total, so
  it penalised only haloperidol (rank 4→29) for a curator's word.
- **Demotion is proportional over `comparable` shared targets, and the
  denominator is `comparable`, never `n_shared`.** One-of-two-opposed
  multiplies by 0.625, not left untouched. Clozapine/apomorphine share
  34 targets, comparable at one; dividing by 34 would score them
  near-identical on 33 untested targets.
- **`pooledDirection` reads direction at every protein a target
  *covers* (accession, never gene symbol), including subsumed rows.**
  This catches morphine/naltrexone: naltrexone topped morphine's list
  on 12 null-direction rows because the family row carrying its true
  direction is subsumed and scored 0. Morphine now ranks it 17th.
- **GtoPdb's actions are a second curator, read beside ChEMBL's and only
  where the pair has a visible claim** (D17). They land in the same
  per-protein set in `directionIndex`, so a molecule whose two curators
  disagree is not opposed to anything (bromocriptine at D4: ChEMBL AGONIST,
  GtoPdb antagonist) — which is also why a known-wrong action has to be
  withheld rather than outvoted (invariant 9); every sentence about an
  opposition names its curator. A
  `gtopdb`-role claim (D18) is curated like a `curated` one — ask
  `isCuratedRole`, name the curator with `curatorOf`, never test the role
  string. The mechanism filter and line colour read `claimActions`: a curated
  claim's own action, a measured claim the GtoPdb action at its pair — never
  relabelling ChEMBL. A claim's `action_type` is a ` / `-joined list where
  one curator names several at a pair (varenicline AGONIST / PARTIAL
  AGONIST); read it through `curatedActions`, never whole — whole, it was a
  word no filter, colour or opposite knew.
- **A partial agonist against an antagonist or inverse agonist is half an
  opposite** (D19, `HALF_OPPOSED_ACTIONS`); partial against full agonist is
  never one. Counting it fully threw aripiprazole from #6 to #90 for
  haloperidol; not at all left morphine/naltrexone understated; half is the
  best ATC grade and near-neutral under MeSH. `opposedShare` is the one place
  the fraction is computed, for the score and the sentence alike.
- **The pair panel names every opposition it demotes for, even where
  no block shows both halves** — the two curated actions are often on
  two different, non-shared records.

**Families, complexes and subsumption (invariant 6, decision D06)**

- **`gene_symbol` stays a label and is never a matching key;
  `singleProteinByAccession` returns null rather than picking one
  where two targets share an accession.**
- **A curated family/complex claim is never redistributed onto its
  members, and its membership lines are springs and ink, never
  edges.** Caffeine's family claim plus four ADORA1–3 claims read as
  "five findings" and was reported as a bug; each family row now names
  the proteins it covers, and the lines joining them are invisible to
  `edges`, hops, similarity and the second hop.
- **`channelAssembly` groups ion-channel units by `protein_class`,
  never PROTEIN COMPLEX alone** (that also covers the JAK pairs and
  mu-opioid/α2A heteromer, whose parts work apart); the legacy
  collapse/hull control and a band round a selection's groups (v12,
  removed) do not carry over — 105 drawn proteins sit inside two or
  more drawn groups, so "keep the largest" would fold α1β2γ2 and
  α5β3γ2 together.

**Filters and display controls**

- **Curated-mechanism actions compose, are never folded into direction
  families, and an emptied action stays visible as "(0)."** A cost and
  an inclusion are counted apart (invariant 13): a different action vs.
  no action are two banners, never one number.
- **Line colour and protein-group linking move no claim or score, but
  only protein-group linking is in the graph signature** (its lines
  are springs; a repaint must never cost a rebuild), and the legend
  reads its swatches off the canvas drawn, never the palette. A
  selection's highlight never repaints that colour/fill channel — the
  element keeps its own colour and gains width/rim instead
  (`selectionWidth` 2, rim held at or above its own).
- **Every coloured action has a hover explanation (`ACTION_HELP`), worded
  from ChEMBL's own `action_type` definitions, shown in a box beside the
  legend and never inside it** — the legend scrolls and would clip it. A
  test reads the palette and fails for a colour added without one.
- **The canvas's count box states what the claim filters keep against the
  whole catalogue, in canvas nodes (a protein once across species, D20),
  and what is drawn only on a second line** — the canvas control never
  moves the first. ChEMBL's record count is named "target records"
  wherever it appears, never "targets" (invariant 13).
- **A filter change paints its busy line before the rebuild starts**
  (`refreshAfterFilters`: a timeout queued in a frame callback), in the
  count box and not `#load-status`, which the open Display options covers.
  The re-solve's batch size stays at 100: lowered, the `SETTLE_MS`
  backstop ended the solve early (docs/VIEWER.md).

**Panels and wording**

- **One protein in several species is one heading, never one record**
  (D20) — the pair panel folds each species' record under a protein
  header, and the score row reads *ADORA1 · 4 species*, not the counted
  record's species. Every table name links to its block, and every block
  leads with the same symbol.
- **A protein is one node in every species; its records are sections,
  never merged** (2026-10-10). The node is keyed by its first
  `proteinRecords` record (`targetNodeKey`: human, else lowest id) so
  layout survives filters; the target and edge panels are headed by the
  protein with no species, and list one section per record, the record
  they were opened at first — a claim row opens its own record, a line
  its strongest. Complexes and families stay one node per species, and
  `proteinKey` is the only grouping key.
- **A claim has no panel of its own** — an edge opens the whole pair,
  grouped into drawn / held-back / retained, none summed; 2,601 of
  11,599 edges carry more than one claim.
- **A curated claim offers ChEMBL's references, never a "Measurements"
  disclosure, and those references are de-duplicated (invariant 14).**
  No curated claim here rests on a measurement; ChEMBL files one
  mechanism per salt/form with identical references each time.
- **A `tier_reason` token is named, not spelled, falls back to the
  token if unrecognised, and a row states one fact once (invariant
  13)** — a pill names the route, so the line below it says what the
  pill cannot, and a heading saying "molecules" counts molecules, not
  claims.
- **A claim's sibling-claim count is read off the pair, never as
  `edge.claims.length - 1`; no panel is a dead end; and a late shard
  is attributed from the selection's identity read into primitives
  before it is requested, never `getSelection()` at callback time**
  (same mutable object, so a stale check is true by construction). A
  retained claim lives only in the molecule's shard, never on an edge.
- **The page says when it is loading and when it cannot draw**
  (`setLoadStatus`, `loadProblem`): a missing `graph.data.js` is a failed
  download, never an empty catalogue, and progress never overwrites a stated
  failure. The disclaimer and About carry the data's build date, read from
  the payload and never typed.
- **The disclaimer is permanent and outside every panel; About is the one
  place the page credits its sources, and credits GtoPdb only when its file
  was merged.** "Closest target profiles" reads as "this drug can replace
  that one" on a public page; a credit in two places drifts, and one written
  into the markup would attribute data a ChEMBL-only page is not showing.
  Both the strip and About link the public repository's issues as the place
  an error goes; About says what a useful report names.

**Search**

- **Search ranks match quality before field, the reviewed alias map
  (THC, CBD, ASA, L-DOPA, …) is search-only and excludes combination
  products, and a target tie-break of component count opens a subtype
  (ADORA1) before a family listing the same gene.** An entry carries
  up to 146 synonyms, so a reviewed common name must outrank a buried
  substring hit; Adderall is not a name for amphetamine; the family
  standing in front of its subtype is the merge D06 refuses.

**Links**

- **The URL fragment names the selection and the sender's filters
  (`#m=CHEMBL113&tier=supported`) and is only ever a lookup key** — ChEMBL
  ids, never the page's molecule numbers; a filter only where it is off its
  default, and only a value its control offers; anything naming nothing is
  dropped and the address put back. Written with `replaceState`, never
  `location.hash`, so it adds no browser history beside the page's own Back.
- **The CSP names the one inline script by hash, computed at deploy by
  `scripts/csp.py`.** The page must keep exactly one inline `<script>` and no
  inline event handlers; the script refuses to deploy one that has either.

**Indications and trials**

- **One `drug_indication` record per form folds onto one disease row at
  its furthest phase, and the panel states what slice of the record it
  shows.** 682 of 5,939 diseases here span more than one record; 959 of
  1,331 entries have a disease outside the adopted scope.
- **A trial states status, phase and p-values verbatim, never failure
  or rejection, and "Approved" names the condition it is for or says
  ChEMBL records none** — no identifier-keyed source holds the former,
  and 327 of 900 approved entries needed the latter.
- **A trial's years are the registry's, and an ESTIMATED date is always
  worded as planned** — 890 status-UNKNOWN trials carry a planned end
  already past, which printed bare reads as the year they ended.

**Rendering correctness (not just performance)**

- **A filter change calls `network.stabilize(n)` explicitly** — vis
  answers a DataSet change with `startSimulation()`, which never emits
  `stabilizationIterationsDone`, so physics never turns itself off.
- **A selection or glide repaints via `setOptions`/`edge.options`, and
  never rewrites the DataSet**, which vis rebuilds wholesale on any
  write (37 ms for one edge). Writing a font straight onto
  `node.options` shipped once and broke every label — vis's
  `labelModule.fontOptions` is a private copy only `setOptions` syncs.
- **`ctx.lineCap` is stated once per edge pass; edges draw
  faintest-bucket-first, one path per style, none dropped; the width
  floor `Math.max(width, 0.3/scale)` is copied from vis.** Skipping
  any leaked cap state, let alpha reach 0.78 at 100 overlaps and bury
  the nodes, or thinned every line (78,683 differing pixels).
- **A dash invisible at the current zoom draws solid at its averaged
  alpha (`dashIsVisible`), never left dashed, and a hairline
  (`lineIsFaint`) is sized in device pixels, not CSS pixels.** GPUs
  cannot dash, so only what a reader actually reads stays dashed; at
  DPR 2 a "0.9-pixel" CSS hairline misses the fast path, costing
  427 ms for one stroke bucket.
- **The gesture-scene cache invalidates via `sceneChanged()` on every
  DataSet event and non-gesture-end redraw** — disabled, a stale
  selection differs from live by a mean of 15.6/255.

## Not done — the cohort pipeline

An index of what is open, ordered by how directly each item damages the thing
this project is for — seeing which molecules may act in similar ways. **Nothing
here is a decision**; the linked documents hold the argument. Cohort 2's own
open items (D15's partial-agonist rule now that GtoPdb curates efficacy,
primary-only GtoPdb rows, whether GtoPdb counts as curated support, new
molecules) are in [docs/COHORT-2.md](docs/COHORT-2.md) and come first.

- **Which curated actions count as opposites is chosen by argument.**
  `OPPOSED_ACTIONS` is nine hand-written pairs, eight of them never examined the
  way PARTIAL AGONIST/INVERSE AGONIST was (removed on a measurement). Each entry
  is a pharmacological claim, not a number to sweep.
- **The six scoring constants are unvalidated; the two newer terms were
  measured first.** The one live finding, under both the ATC and the MeSH
  judge: the gap between a curated claim (0.75) and a replicated one (0.9) is
  the setting the ranking feels most — it is why meperidine's nearest neighbour
  is amitriptyline over a hERG screen. Nothing was changed on the strength of
  it: 24 of 217 molecules get worse, and the judge flatters curation.
  [docs/SIMILARITY-HARNESS.md](docs/SIMILARITY-HARNESS.md); FDA Established
  Pharmacologic Class is the candidate third judge.
- **D20 keeps rarity per record,** so a rodent record, measured on by fewer
  molecules, often stands for its protein in a pair's score. Both obvious fixes
  graded worse ([docs/COHORT-2.md](docs/COHORT-2.md), D20).
- **The prevalence discount is not conditioned on curation.** KCNH2 (hERG)
  carries 41 Supported molecules and no curated mechanism; prevalence now
  discounts it, but conditioning on the curated-mechanism ratio is a claim
  about *why* a target is common and was never argued. GtoPdb's primary-target
  flag is new input for exactly this.
- **Affinity is not weighed.** 7 nM and 200 µM score alike; a first prototype
  graded worse. Invariant 7 keeps potency out of the trust signal; the ranking
  is a separate question.
- **No brain-expression signal.** The cohort build reads ChEMBL alone, so the
  brain focus is carried by molecule selection only. Proposed: a
  `resolve_cohort_brain_expression.py` backfill (HPA), drawn as a marker, never
  a filter (invariant 10).
- **One MeSH finding is unreported.** *Gestormone* sits in MeSH's dacuronium
  record though NIST, NCI and ChemIDplus give progesterone — an NLM error. It
  no longer reaches this catalogue: the actions stopped going through PubChem's
  name links on 2026-10-13, and tarenflurbil lost flurbiprofen's
  *Cyclooxygenase Inhibitors* the same way.
- **20 molecules lost their MeSH actions in that change** — 9 carry a UNII no
  MeSH record holds (semagacestat), 4 are flat structures whose stereoisomer
  mixtures reach no single record (doxepin), 4 are in neither FDA's file nor
  Wikidata (liraglutide), and 2 are drawn with different defined stereochemistry
  by ChEMBL and FDA (dextrose). Nothing that matches by identifier reaches them
  ([docs/MESH-ACTIONS-ROUTE-B.md](docs/MESH-ACTIONS-ROUTE-B.md)).
- **A ChEMBL curation error to report:** alfuzosin filed as an alpha-1
  AGONIST against its own cited label. Withheld here since 2026-10-10; the
  report is drafted in
  [docs/CHEMBL-ERROR-REPORT-ALFUZOSIN.md](docs/CHEMBL-ERROR-REPORT-ALFUZOSIN.md)
  and not sent. How many more there are is unmeasured: three
  sweeps found no other, and none of them can see an error of its shape
  ([DATA-QUALITY-LOG](docs/DATA-QUALITY-LOG.md), 2026-10-10). Of the 176
  activities ChEMBL itself flags "Potential transcription error", 156 are
  counted, in 43 Supported claims - unexamined.
- **Untriaged proposals.** Unit recovery (30 explicit conversions, and a
  conditional mass-basis rule touching 2,364 records that changes what
  "conditional" means) and the organism-format review, in
  [docs/COHORT-FOLLOWUP.md](docs/COHORT-FOLLOWUP.md); an alternative selection
  policy (ATC N plus CNS Phase 3, 995 molecules) there too, neither adopted nor
  declined; and the scope boundary's soft edge (neuralgia, fibromyalgia) with a
  curated neuropharmacology route, in
  [docs/COHORT-BOUNDARY-REVIEW.md](docs/COHORT-BOUNDARY-REVIEW.md) — a
  membership change and the user's call.
- **Nothing enforces the suites.** No CI, and the git hooks check privacy, not
  the suites; both run offline in seconds.
- **The legacy pipeline's fate is undecided** — a maintained rollback path
  (which needs a test that builds it) or history (a tag, and delete the code).
- **Public since 2026-10-10, with the hosting review's items open.** The
  page is at `subnetwork.dev` and this repository is public. Open: phones
  (responsive, or stated desktop-only — the user's call), and a meta
  description and link-preview tags; and from its second pass, a privacy
  note, Firefox/Safari, keyboard access, external monitoring, whether
  search engines should index it (`robots.txt`), and a favicon. Done
  2026-10-10: shareable links, a `script-src` CSP, licence links, a visible
  data date, how to cite, the load and failure states, the "no interactions"
  line, two more headers, a staging copy, a deploy record naming the data,
  the address, and a way to report an error (GitHub issues, linked from the
  strip and About). The table is in
  [docs/HOSTING-REVIEW.md](docs/HOSTING-REVIEW.md), and
  the answers to the user's questions on it in
  [docs/HOSTING-REVIEW-ANSWERS.md](docs/HOSTING-REVIEW-ANSWERS.md).

## Repository and pushing

**This repository is public: everything pushed to it is public and
permanent.** It is `szaszeattila/SubNetwork`, public on GitHub since
2026-10-10 ([docs/PUBLISHING.md](docs/PUBLISHING.md), *Going public*). It
began on 2026-10-10 as one snapshot of a private working copy,
`szaszeattila/SubNetwork-private`, now archived. That copy holds the history
from before the snapshot, which carries a personal address and session links,
and is never pushed here.

**Worktree branches are published** (the user's decision, 2026-10-12,
replacing "unfinished work stays local" of 2026-10-10):

- **A session commits to its worktree's branch and pushes that branch** to
  GitHub, where it is public like everything else. Merging into `main` and
  pushing `main` still happen only when the user asks. A deleted branch's
  commits stay reachable by their hashes, so a push cannot be taken back.
- **Before a worktree is removed, its branch is merged or pushed**, never
  deleted while it exists nowhere else.
- **Never write a home path, a personal address, a claude.ai session link or
  a job directory into the repository**, in a file or a commit message, and
  commit as the GitHub no-reply address. The hooks in `.githooks/` refuse all
  of these, and pre-push searches every commit a push of any branch would
  publish (`scripts/privacy_check.py`). Each clone enables them once with
  `git config core.hooksPath .githooks`. Never `--no-verify`.
- **A contributor's pull request is merged here like any other change**,
  keeping its commits and author ([CONTRIBUTING.md](CONTRIBUTING.md)).

## Hosting

The cohort viewer runs on Cloudflare Workers, **with** the evidence shards,
and is the one hosted copy: **public at <https://subnetwork.dev>** since
2026-10-10 and nowhere else. The Worker's `workers.dev` addresses show the
account name and stay out of the repository: production's is switched off,
and the preview URLs, staging included, stay behind Cloudflare Access. The claude.ai artifact it was also published as (versions
1–28) was **deleted on 2026-10-10** at the user's request, so that two
shareable copies could not drift; [docs/PUBLISHING.md](docs/PUBLISHING.md) keeps its procedure and
version history as a record. The legacy viewer's separate artifact snapshot
is in [docs/LEGACY-PIPELINE.md](docs/LEGACY-PIPELINE.md).

`scripts/deploy_cloudflare.sh` deploys after both suites and
`--check-status` pass, attaches `subnetwork.dev`, and fails unless that
address serves the deploy and every `workers.dev` address wrangler reports
answers with the Access login; `--preview` uploads to the private **staging** alias
instead, leaving production alone. Each upload names the data build in its
message and is kept under `deploys/`. The `workers.dev` addresses stay out
of the repository ([docs/PUBLISHING.md](docs/PUBLISHING.md), *The Cloudflare copy*).
