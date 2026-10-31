# Cohort 1 — implementation summary

> **Status, added 2026-09-17: in force.** This is what the adopted policy
> produced, and it is the document to read for how the current pipeline
> behaves. Its figures track the active database and agree with the generated
> `## Status` block in [../CLAUDE.md](../CLAUDE.md), which is the authority if
> the two ever differ. Written for the first cohort-1 build of 2026-09-13 and
> updated through 2026-09-16; **the active database is the 2026-09-16 rebuild**
> that added `molecule_indications.trial_ids`, which is why sections below carry
> later dates than the line under this one. See [INDEX.md](INDEX.md) for which
> documents here are in force and which are not.

Built 2026-09-13 against `chembl_37`, under selection policy
`cohort1-selection v2.0.0` and evidence policy `cohort1-evidence v1.0.0`
(`config/`). Every number here comes from `python3 scripts/cohort_report.py`
run against the active database, so any figure can be reproduced rather than
taken on trust.

These are **not** the report's totals. [COHORT-REPORT.md](COHORT-REPORT.md),
[COHORT-FOLLOWUP.md](COHORT-FOLLOWUP.md) and
[COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md) measured *alternatives*
under S0 core scope and the baseline evidence rules. The adopted policy changes
the scope, the evidence tiers, the source set and the target granularity, so
its counts are different by construction. The report's 995 / 1,206 proposal,
its 257-gap count and its tier tables describe a policy that was not adopted.

## What was adopted

[COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) records the choices. In short:

- **Membership**: whole ATC N as an independent route with no phase floor, or
  an indication inside the adopted scope at Approved or Phase 3, measured on
  `drug_indication.max_phase_for_ind`.
- **Scope**: S0 core (C10 + F03 minus the three boundary classes), plus the
  whole saved Pain tree, plus an explicit inclusion set for neuropathic pain
  and fibromyalgia that overrides the boundary exclusions.
- **Categories**: all molecule types, all structure types, withdrawal
  annotations retained and flagged.
- **Seeds**: supplement, never grandfather. All 28 retained; clinical
  membership recorded separately.
- **Evidence**: study-based Supported / Preliminary / Limited, replacing
  measurement-count corroboration.
- **Sources**: ChEMBL 37 only for active pharmacology. Everything else
  deferred and marked *not assessed*.
- **Targets**: single proteins, precise complexes, protein families and
  complex groups, each at its own identity.
- **Potency**: a display filter, never an import or membership rule.

## Measured results

### Catalogue

| | |
|---|---:|
| Catalogue rows (unique chemical parents) | **1,331** |
| In cohort 1 | **1,326** |
| Retained seeds outside cohort 1 | 5 |
| Source forms folded onto those parents | 2,315 |
| …of which are salts, hydrates or other non-parent forms | 984 |

Admission routes, which partition the cohort exactly
(171 + 782 + 373 = 1,326):

| Route | Molecules |
|---|---:|
| Indication only | 782 |
| Both routes | 373 |
| ATC N only | 171 |

Scope reasons on cohort members (a member can carry several):

| Reason | Members |
|---|---:|
| core | 997 |
| general_pain | 305 |
| explicit_neuropathic | 51 |
| explicit_fibromyalgia | 21 |

**120 members are admitted only through a non-core scope reason** — they are in
the catalogue because the Pain tree or the explicit neuropathic/fibromyalgia
inclusions were adopted, and the viewer says so on each one.

Molecule categories, with no type filter applied (D03):

Small molecule 1,102 · Protein 62 · Antibody 53 · Unknown 45 · Enzyme 24 ·
Vaccine component 13 · Oligonucleotide 13 · Oligosaccharide 10 · Gene 4.
**105** carry `structure_type = NONE` and **78** carry a withdrawal flag in
their family; all are retained and labelled.

### The scope audit

2,869 descriptors were classified; **1,029 are in scope**, of which 974 are the
report's S0 core and **55 are recovered outside it**. Every `mesh_id` in
`chembl_37.drug_indication` (2,178 distinct, 0 null) is classified, and the
build fails rather than treating an unmapped descriptor as out of scope.

The audit D02 asked for found a real error in the report's prose. The report
says Neuralgia (D009437) keeps an in-core placement at `C10.597.617.470`. **It
does not.** Its C10 placement is `C10.668.829.600`, inside the excluded
peripheral-nerve class, and the saved classification marks it out of core. The
boundary review's correction is the accurate one.

That matters because **adding the Pain tree alone does not deliver what D02
asked for**:

| Descriptor | Recovered by the Pain tree? | Admitted by |
|---|---|---|
| D009437 Neuralgia | yes | `general_pain`, `explicit_neuropathic` |
| D051474 Postherpetic Neuralgia | yes | `general_pain`, `explicit_neuropathic` |
| D060545 Pudendal Neuralgia | yes | `general_pain`, `explicit_neuropathic` |
| D014277 Trigeminal Neuralgia | **no** | `explicit_neuropathic` |
| D005156 Facial Neuralgia | **no** | `explicit_neuropathic` |
| D005356 Fibromyalgia | **no** | `explicit_fibromyalgia` |

The explicit inclusion set is four tree roots (`C10.668.829.600` Neuralgia,
`C10.292.319.625` Facial Neuralgia, `C07.465.299.625.500.700` trigeminal
neuralgia's second placement, `C10.668.491.425` Fibromyalgia) plus two
descriptors named individually (`D003929` Diabetic Neuropathies, the largest
neuropathic-pain indication in the release at 100 rows, and `D000071075` Small
Fiber Neuropathy). Five descriptors that were *considered and not included* —
Radiculopathy, Polyneuropathies, Carpal Tunnel Syndrome, Peripheral Nervous
System Diseases and Mononeuropathies — are recorded in the policy with the
reason, so the line is visible rather than implied. A test asserts all six
descriptors D02 names land in scope.

The Pain tree is accepted at its measured breadth, as D02 requires. It reaches
angina (`D000787` and its variants), so adenosine, isosorbide and similar
cardiovascular drugs are admitted with `general_pain` as their stated reason.
That is the adopted policy, not an oversight, and the admission reason is on
every entry.

### Targets

**2,577 target records** carry claims, at the four adopted identities:

| Identity | Target records | Claims |
|---|---:|---:|
| SINGLE PROTEIN | 2,268 | 78,139 |
| PROTEIN FAMILY | 136 | 968 |
| PROTEIN COMPLEX | 144 | 798 |
| PROTEIN COMPLEX GROUP | 29 | 554 |

Those records resolve to **2,845 distinct component accessions**. A component
is context: it is never itself a claim, a complex is never split into its
subunits, and a family is never redistributed to its members. Target records
and component proteins are separate counts and are never added.

### Claims and evidence

**80,459 claims** at (parent, target, role, basis), over **69,107 distinct
molecule–target pairs**.

| Basis | Role | Supported | Preliminary | Limited / unresolved |
|---|---|---:|---:|---:|
| human_direct | curated | 1,045 | — | — |
| human_direct | binding | 1,156 | 2,398 | 5,729 |
| human_direct | functional | 210 | 517 | 188 |
| broader | curated | 38 | — | — |
| broader | binding | 1,218 | 6,191 | 44,710 |
| broader | functional | 204 | 3,229 | 13,626 |

The two Supported routes, in the direct human basis: **1,366** claims by
multiple-study replication and **1,045** by curated mechanism. **No claim
carries both**, which is worth stating plainly — the report measured the same
split and found only 6.7% of pairs supported both ways. **1,962 distinct
molecule–target pairs** have a Supported claim in the direct human basis.

Broader-layer observations by assignment class: homologous 111,318, nonhuman
15,278, human variant 530, ambiguous 64. None of these contributes to a
direct-human tier, score or shared-target count.

### Catalogue coverage

| Status | Entries |
|---|---:|
| Has a Supported claim (direct human) | 845 |
| No eligible evidence in ChEMBL 37 | 260 |
| Preliminary only | 151 |
| Supported **only** in the broader layer | 38 |
| Retained observations only, none reaching Preliminary | 37 |

Those 38 are exactly the group D07's filter exists for: they are invisible
under the default basis, and the banner says so and names the control that
reveals them. All 1,331 entries stay searchable regardless.

### Observations, bounds and conversions

**210,157 observations** retained from 803,018 activity rows scanned, resolving
to **14,548 distinct studies**. **41,682** rows are counted into a median.

| Value status | Rows |
|---|---:|
| exact (native nM) | 69,394 |
| exact (audited concentration conversion) | 10 |
| bound | 51,036 |
| conditional (mass basis) | 1,727 |
| unresolved | 87,990 |

Bounds by relation, each preserved as reported: `>` 50,391, `<` 546, `>=` 57,
`<=` 20, `~` 19, `>>` 3. None enters a median, a threshold pass or the
replication rule, and none is labelled "no activity".

The 1,727 conditional mass conversions use the **measured** record's own
molecular weight, never the parent freebase. **Zero** of them are counted into
any median or tier — a build check asserts that number is 0. They stay visible
and labelled conditional, with the weight, source form, original units and
formula on the row.

Exclusion accounting, which reconciles exactly to what was scanned:

| Reason | Rows | Retained |
|---|---:|---|
| scanned | 803,018 | — |
| assay type not B or F | 376,461 | no |
| endpoint type out of scope | 203,213 | no |
| kept: unresolved | 87,990 | yes |
| kept: exact | 69,404 | yes |
| kept: bound | 51,036 | yes |
| organism-based format | 13,184 | no |
| kept: conditional | 1,727 | yes |
| documented known-bad | 3 | individually, in `excluded_records` |

`no_claimable_assignment` (54,325) is a breakdown of the kept rows, not a
separate bucket: those observations are retained with their reason and back no
edge.

Conflicts: **517 claims** carry a measurement-dispersion flag (values
disagreeing by more than a hundredfold within one endpoint class across two or
more studies). **0** curated directional conflicts, which matches the report.
A conflict never raises a tier.

### Seed outcomes

**23 of 28 seeds are admitted to cohort 1.** The five that are not are retained
with an exclusion reason, as examples for designing cohort 2:

| Seed | Why not admitted |
|---|---|
| loperamide | No ATC N in family; best scoped indication is Pain at Early Phase 1 |
| mibefradil | No ATC N in family and no indication inside the adopted scope |
| pentoxifylline | No ATC N in family; best scoped indication is Brain Diseases at Phase 2 |
| rolipram | No ATC N in family; best scoped indication is Multiple Sclerosis below the floor |
| theobromine | No ATC N in family and no indication inside the adopted scope |

Two results are worth calling out.

**Theophylline is admitted**, where the report had it failing on indication
phase. It enters at its parent `CHEMBL190` through Headache (`D006261`) at
Phase 3 — a Pain-tree descriptor, so the adopted scope is exactly what admits
it. Its seeded record `CHEMBL1355736` is preserved as a form and stays
searchable by that id. Both records are typed `Protein` in `chembl_37`; under
the all-types rule that annotation excludes nothing, and it is flagged for
review rather than rewritten.

**Loperamide is not admitted**, which the implementation prompt predicted: its
saved Pain phase is 0.5, so adopting the Pain tree admits the descriptor and
not the molecule. It remains a seed, and its near-miss indication is stored so
the panel can say why.

Every seed still has a Supported claim somewhere except theobromine, whose only
Supported evidence is in the broader assignment layer.

### Validation

All 15 build checks pass, and a build that fails one does not replace the
active database. They cover referential integrity of claims and observations,
source-record uniqueness, admission-route arithmetic, every entry carrying a
reason, parent identity, per-summary measurement counts reconciling to the rows
counted into them, only exact values being counted, multiple-study support
needing two publications inside one endpoint class, no claim on a non-claimable
target and no edge from an unassigned observation, organism-format rows being
absent, curated and measured support staying separate, bases not pooling,
exclusion accounting, and every entry stating its evidence status.

### Browsing performance

Measured in headless Chrome on this machine, over the real 4.03 MB payload and
the real shards (not the unit harness):

| | |
|---|---:|
| Parse and index the catalogue | **216 ms** |
| Select a molecule (neighbourhood + similarity) | **0.10 ms** |
| Select the densest molecule (clozapine, 61 Supported claims) | **0.49 ms** |
| Toggle a filter, including recounting every banner | **0.39 ms** |
| One search keystroke over the whole catalogue | **1.3 ms** |
| Load one evidence shard on demand | **10 ms** |

Artifact sizes: `viz/graph.data.js` **4.03 MB** (the previous export was
2.33 MB), and `viz/evidence/` 71.7 MB across 1,176 shards, mean 61 KB, largest
2.2 MB. Only the startup file and one shard are ever loaded.

The startup file is **4.39 MB** as of 2026-09-16, up from 4.13 MB, the whole
increase being `molecule_indications.trial_ids` and `molecules.n_indications_chembl`
— +257 KB for 12,845 reachable ClinicalTrials.gov studies. The table above was
measured in headless Chrome against the smaller payload and has not been
re-measured there; in the vm harness parse-and-index is 156-164 ms at the new
size against 159 ms at the old, so the growth costs nothing detectable, but that
is not the browser number and is not a replacement for it. Rendering the
indication section itself is 1 ms for caffeine's 26 diseases and 3 ms for
risperidone's 28, whose Schizophrenia row alone carries 200 registrations.

Checked by hand in the browser: the caffeine default view, a dense
neighbourhood (clozapine), a family claim (caffeine's curated `Adenosine
receptor` PROTEIN FAMILY antagonist mechanism, retained at the family level), an
entry whose only evidence is in the broader layer (sulfadiazine), and an entry
with no drawable evidence at all (fencamfamin, searchable and stating its gap).

### Wikipedia links

`molecules.wikipedia_url` and `targets.wikipedia_url` exist in
`db/schema_cohort.sql` but the build never fills them — the cohort pipeline
reads ChEMBL 37 and nothing else, so both columns were NULL for all 1,331
molecules and all 2,577 targets. `scripts/resolve_cohort_wikipedia.py` is a
standalone backfill, run once after the build and after every rebuild that
adds molecules or targets, following the same rule the legacy pipeline
established (invariant 15, docs/DATA-QUALITY-LOG.md 2026-08-29): every match
is on an identifier already in the database, through Wikidata, and an item
resolving to more than one English article is dropped rather than guessed.

Molecules match on InChIKey (P235) and ChEMBL ID (P592) — there is no
PubChem CID column in the cohort schema, so unlike the legacy build that
third identifier is never tried. Targets match on UniProt accession (P352),
then Wikidata's "encoded by" (P702) hop to the gene item, and only where a
target has **exactly one** component accession.

Run against the build described above:

| | resolved | no article | ambiguous (dropped) | failed |
|---|---:|---:|---:|---:|
| Molecules (1,331 total, all queried) | **1,051** | 278 | 2 | 0 |
| Targets (2,265 single-component, of 2,577 total) | **1,280** | 972 | 13 | 0 |

Re-run on 2026-09-16 after the rebuild that added `molecule_indications.trial_ids`,
against the same 1,331 molecules and 2,265 eligible targets. One further target
resolves than the first run: Wikidata gained an English article, not this
pipeline changing what it accepts.

**310 of the 2,577 targets are multi-component** (144 PROTEIN COMPLEX, 29
PROTEIN COMPLEX GROUP, 136 PROTEIN FAMILY, plus one target ChEMBL itself
files as SINGLE PROTEIN with two component accessions) **and are left NULL
by design, not by omission.** `build_db.py`'s history for the legacy
pipeline's seven protein assemblies is exactly the warning: walking
Wikidata's "has part"/"part of" links outward from a complex's members, or
even requiring unanimity across every member, both produced *confident wrong
answers* (5-HT3 to "Cys-loop receptor", the 7-member NMDA group to
"Ionotropic glutamate receptor") more often than no answer at all. That
pipeline's fallback was a seven-entry hand-written ChEMBL-id-to-Wikidata-item
map; hand-curating an equivalent for 310 targets is future work the cohort
pipeline has not undertaken, so a PROTEIN COMPLEX, PROTEIN COMPLEX GROUP or
PROTEIN FAMILY row here carries no Wikipedia link regardless of how well
resolved its members individually are. 2 further targets carry zero
component accessions at all (ChEMBL toxoid antigens with no UniProt record)
and are skipped for the same reason: there is no identifier to match on.

*Superseded 2026-10-18:* the review was done. Every multi-component target
now has a reviewed entry in `config/cohort1_target_wikidata.json` naming its
Wikidata item, or null with the reason it has no article of its own, and is
linked through that item ([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md),
2026-10-18).

The two remaining failure-free "0" columns are worth being explicit about:
every one of 1,331+2,265 = 3,596 lookups attempted completed without a
Wikidata request exhausting its retries. A run that did hit a failure would
report it separately from "no article exists" and leave the affected rows
unchanged rather than guess — rerunning the script is always safe and only
re-queries what is still NULL.

### Indications, phases and clinical trials

Added 2026-09-16, and the reason for the rebuild that produced the current
database. The catalogue totals are unchanged by it — 1,331 entries, 2,577
targets, 80,459 claims, 210,157 observations, all 15 checks passing — because
nothing here changes which rows exist.

`molecule_indications` holds **6,776 rows** for 1,242 of the 1,331 entries. Those
resolve to **5,939 distinct diseases**, because ChEMBL files a `drug_indication`
per *form* of the molecule and the forms fold onto one parent here:

| | |
|---|---:|
| Diseases assembled from more than one ChEMBL record | **682** |
| …of which the records disagree about the phase | **227** |
| …of which the records straddle the qualifying floor | **115** |

Caffeine is the readable case: Pain is Approved against `CHEMBL113` and Phase 2
against `CHEMBL1200569`, one disease and not two. The viewer folds them to one
row at the furthest phase any record reached, pools their trials, and states the
record count — the same de-duplication, for the same reason, as a curated
claim's repeated references.

`trial_ids` carries the ClinicalTrials.gov registrations from ChEMBL's
`indication_refs`, split from its comma-joined `ref_id` and stored '|' joined.
**5,864 of the 6,776 rows carry at least one; 12,845 distinct studies are
reachable.** Coverage is far better where the claim is a development stage than
where it is an approval:

| | diseases | with a registered study | without |
|---|---:|---:|---:|
| Approved | 1,078 | 563 | **515** |
| Phase 3 | 2,093 | **2,078** | 15 |

That asymmetry is not a gap in the pipeline: what ChEMBL cites for an approved
indication is usually the product label. 286 of those 515 carry a **DailyMed**
reference, which is the obvious next thing to read and is deliberately not read
yet — the ask was for the studies, a label is not a study, and its set-ids would
cost more payload than the trials did. The viewer states the shortfall in the
section rather than letting a missing link read as no trial having been run.

One disease carries **258** registrations, so a row links a single study inline
and folds above one with the count on the disclosure. Only the NCT identifiers
are stored: ChEMBL's own `ref_url` is a clinicaltrials.gov *search* over the same
ids, and invariant 15 wants the identifier, not somebody else's frozen query.

`molecules.n_indications_chembl` counts the distinct diseases ChEMBL records for
the family across **every** therapeutic area, in scope or not — 418 at the most
(sodium chloride). It exists only so the viewer's list can say how much of the
drug's record it is showing: `molecule_indications` is a neuro-and-pain slice,
and **959 of the 1,331 entries have a disease that is not listed there**
(fenretinide shows 4 of 27). Without the count that sentence would have to be
hedged instead of measured.

`molecules.max_phase` was in the export from the start and drawn nowhere. The
panel now states it in words. **296 entries stop at phase 3** — trialled that far
and approved for nothing — against 900 approved, 114 at phase 2, 2 at phase 1 and
19 recorded as unknown. It remains *not* the admission test, which reads the
phase of the qualifying indication.

## What changed in production behaviour

Each of these was explicitly adopted, and each replaces something that was
load-bearing before.

1. **Study-based support replaces measurement-count corroboration.** Invariant
   7's `n_measurements` is no longer the trust signal. It survives as an
   accounting rule — every displayed summary's count must equal the rows stored
   against it with `counted = 1`, and a build check asserts it.
2. **Active pharmacology is ChEMBL-only.** PDSP, BindingDB and DGIdb are not
   read. Some seed edges that existed before are gone or weaker; that is the
   adopted uniform treatment, not data loss. The previous six-source database
   is untouched at `db/subnetwork.db`.
3. **Targets keep their native identity.** The legacy `targets` table keyed on
   a unique gene symbol and UniProt accession, which cannot represent a protein
   family or complex group at all. The new schema keys on the target's own
   ChEMBL id.
4. **Clinical selection supplements the seeds.** `SEED_MOLECULES` is no longer
   how membership is decided; `config/cohort1_selection.json` is.
5. **Potency is a display filter.** Invariant 8's 300 µM auto-discovery cutoff
   decided what reached the database, and a display control cannot undo an
   import cutoff, so the cutoff moved. Every eligible measurement is stored and
   the filter operates over complete data.
6. **The viewer renders the whole eligible network, and a selection lights a
   neighbourhood inside it.** Under the default filters that is 1,034 molecules,
   2,063 targets and 12,835 edges (845 / 528 / 1,962 when the tier and basis
   controls are narrowed to Supported and direct-human, which was the default
   until the similarity work of 2026-09-17 measured that the strict setting left
   the median entry with a single target and the ranking with nothing to rank
   on) — not the whole catalogue, because the
   eligibility rule decides the canvas, but not one neighbourhood either. The
   first implementation drew one neighbourhood at a time and rebuilt on every
   click; it answered what a molecule acts on and lost where that sits among
   the others. A selection now writes opacity only.

Unaffected invariants are unchanged and still enforced: exact identity matching
(6, 15), source provenance, role and endpoint separation (3, 4), explicit
known-bad exclusions (9), escaped viewer text (11), and never labelling two
different quantities so they invite comparison (13, 14).

## Two analysis defects corrected rather than copied

The production code is derived from `analysis/cohort1/`, and two of its rules
did not survive review. Both are recorded in the policy files where the change
is made.

**The organism-format gate ran only on functional assays.** `chembl_37` also
holds 1,632 organism-format assays typed `B`, carrying 34,791 activity rows,
which that gate let through as binding evidence. D11 excludes organism-format
observations from active evidence without qualification, so production applies
the gate to every assay type. In this catalogue that is 13,144 functional rows
and **40 binding rows** the analysis would have kept.

**The direct-assignment test skipped two of its own conditions.** The report's
`specificity()` applied `relationship_type = 'D'` and `variant_id IS NULL` only
to the single-protein branch. Its complex branch would have accepted the 109
human confidence-7 PROTEIN COMPLEX assays that carry a variant, and its family
branch the 11 variant-carrying PROTEIN FAMILY assays, as direct no-variant
human evidence. Its `confidence_score = 5` branch also admitted
PROTEIN-PROTEIN INTERACTION (9,740 assays), SELECTIVITY GROUP (1,129) and
confidence-5 PROTEIN COMPLEX GROUP (2,827) into the broad human basis, none of
which is one of the four target identities D06 names. Production applies the
full combination to all three classes.

A third, smaller one: the report's `study_key()` labelled a patent document
carrying a PubMed id as a deposited dataset. Production classifies `doc_type`
first.

## Limitations

- **"No evidence" means no eligible evidence in ChEMBL 37 under these rules.**
  It is not a finding about the literature, and it is not a finding about the
  seven deferred sources, which are recorded as *not assessed*.
- **Multiple publications are a proxy for independence**, not proof of
  independent laboratories, experiments or material.
- **Curated support is one curator's assertion** with a traceable reference. It
  is not a replicated measurement, and it never upgrades a measured claim.
- **Mass conversions are conditional.** A source record's molecular weight does
  not establish whether a publication expressed mass as salt, freebase, hydrate
  or formulation. 1,727 rows wait on that verification; none is counted.
- **Shared targets are not "acts alike".** The comparison knows nothing about
  dose, exposure, brain penetration or subjective effect. It is a place to
  start looking.
- **The similarity weights are a documented judgement**, not a measurement. A
  family or complex-group overlap counts at half an exact protein overlap
  because it is a claim about a set whose members may be different proteins.
  The rationale is in `config/cohort1_evidence.json`.
- **The MeSH classification is pinned, not current.** It is the September 2026
  report's saved output; the raw cache that produced it is gone, and D14
  forbids substituting a fresh fetch. Descriptors added or reclassified in MeSH
  since are not covered until the policy version is raised.
- **The explicit neuropathic set is an audited starting point**, not a proof
  that the complete neuropathic scope is mapped. D02 says so, and the policy
  repeats it.
- **The 2.2 MB largest shard** is a heavily measured molecule. It loads on
  demand in well under a second locally, but it is the one figure worth
  re-measuring if the catalogue grows again.
- **Brain expression and BBB status are absent from this build entirely.** They
  were context in the legacy viewer and are deferred with the other sources;
  missing remains unknown, and nothing here treats it as a gate.
- **310 of 2,577 targets carry no Wikipedia link, and cannot by the rule
  adopted.** Every PROTEIN COMPLEX, PROTEIN COMPLEX GROUP and PROTEIN FAMILY
  record is multi-component, and every derivation tried against the legacy
  pipeline's seven assemblies resolved confidently to the wrong article or to
  one too broad. There is no per-target fallback here the way there was for
  those seven; a molecule that acts only on a family or complex target links
  out to nothing, correctly rather than by oversight. *(Superseded
  2026-10-18 by a reviewed item per target; see above.)*

## Building, opening and rolling back

```bash
python3 scripts/build_cohort.py --stage-only   # build + validate, change nothing
python3 scripts/build_cohort.py                # stage, validate, then activate
python3 scripts/build_cohort.py --activate     # activate an existing staged build
python3 scripts/export_cohort.py               # db/cohort1.db -> viz/
python3 scripts/cohort_report.py               # the numbers above
```

Then open `viz/index.html` in a browser — no server, no network, no build step.
A full build takes about 20 seconds and the export about 6.

The build is restartable and idempotent: it always writes a fresh
`db/staging/cohort1.db` and only replaces the active file after every check
passes, so a rerun removes stale claims rather than appending to them, and a
failed run leaves the active database exactly as it was. The export clears
`viz/evidence/` before writing, for the same reason. ChEMBL is opened
`mode=ro` throughout.

### Rolling back

The legacy pipeline's *source* was not modified and its database was not
touched. `viz/graph.data.js` is the one generated file the two pipelines share
a name for, and it now holds the cohort export; the previous bytes are kept
beside it.

```bash
# Still here, unmodified:
ls db/subnetwork.db                     # the six-source seed database
ls viz/legacy/index.html                # the previous viewer
node --test "tests/legacy_*.test.mjs"   # its 222 tests, still passing

# Go back to the seed viewer and its data:
cp viz/backups/graph.data.js.legacy-seed-2026-09-05 viz/graph.data.js
git checkout HEAD -- viz/index.html     # or just open viz/legacy/index.html
rm -rf viz/evidence

# The seed export is also reproducible rather than only restorable:
python3 scripts/export_graph.py         # db/subnetwork.db -> viz/graph.data.js

# Roll back one cohort build:
cp db/backups/cohort1.db.<timestamp> db/cohort1.db
python3 scripts/export_cohort.py
```

`db/backups/` and `viz/backups/` hold the timestamped copy each build and
export makes, plus `graph.data.js.legacy-seed-2026-09-05`, the seed export as
it stood before this work. Both directories are gitignored, like everything
else generated here; the durable guarantee is that `db/subnetwork.db` and
`scripts/export_graph.py` can reproduce the seed export from scratch.
