# Clinical cohort follow-up: evidence recovery and import choices

Revised 2026-09-12. Read-only analysis of ChEMBL 37 and the original cohort
exports. No production database, graph export, seed list or viewer changed.
All numerical tables are generated from `analysis/cohort1/followup/out/`.

> **Status, added 2026-09-17: proposals, and measured against a baseline that
> was not adopted.** Its first heading reads "Decisions supported by the
> measurements", which means *supported*, not *taken* — the document's own
> summary says "These are recommendations, not adopted production rules."
> Two specifics worth knowing before quoting anything here:
>
> - The **995 small-molecule** policy proposed below is **not** what was
>   adopted. The adopted scope added the Pain tree and an explicit neuropathic
>   and fibromyalgia inclusion set, and the catalogue it built is larger; the
>   current figure is generated into `## Status` in [../CLAUDE.md](../CLAUDE.md).
>   Every count here that starts from 995 is therefore about a different
>   catalogue from the one that exists.
> - The **unit-recovery** and **organism-format** recommendations were never
>   triaged either way. Both are still open and are listed as such in
>   CLAUDE.md's "Not done — the cohort pipeline".

## Decisions supported by the measurements

Use **995 small-molecule candidates** as a concrete starting proposal if the
desired rule is whole ATC N plus Approved/Phase-3 CNS indications. That
proposal retains 22 of the original 28 seeds. Under direct human evidence
plus curated human targets at their native single-protein, complex or family
level, **666 molecules have a Supported claim, 738 have a Supported or
Preliminary claim, and 257 have neither**. Keep the catalogue distinct from
the displayed neighbourhood; the figures are not a rendering benchmark.

The unit question yields a small, tractable first improvement: 30 explicit
concentration conversions. The much larger mass-concentration opportunity
needs chemical-form checks. The organism question yields a context inventory
and 22 assay reviews; it does not justify mixing in-vivo exposure with
in-vitro potency. These are recommendations, not adopted production rules.

## 1. What was reproduced

The analysis reproduces the existing experimental evidence tiers and the
strict human-single-protein tier subset from their measurement rows, before
adding any proposed conversion. It also recovers the original 2,245-member
scope from the exported MeSH descriptor classification and ChEMBL indication
IDs. All source databases are opened with SQLite `mode=ro`.

Inputs are pinned by SHA-256 in `followup/out/summary.json`; the 30.5 GB
ChEMBL file is pinned by release and byte size as in the original manifest.
No other pharmacology database was assessed and no clinical membership is
decided by evidence availability. Publication counts remain a proxy for
independence, and baseline upstream validity/duplicate flags remain visible.

The original MeSH cache files are absent from this checkout. The follow-up
uses the saved `indication_scope.csv` rather than fetching a changing current
ontology. It therefore reproduces these scope comparisons offline without
claiming to restore the original cache byte-for-byte. Re-fetching MeSH for
the full original pipeline would be a new snapshot and requires comparison.

## 2. Unit recovery

The original table confused retention with numerical use. Every one of the
2,714 `excluded_units` records is already in the baseline measurement audit.
The corrected `evidence_exclusions.csv` now reports that accurately.

| Recovery scenario | Assignment basis | Added measurements | New Preliminary claims | New Supported claims |
|---|---|---|---|---|
| Concentration conversions | All assignments | 30 | 18 | 1 |
| Concentration conversions | Direct human single protein | 6 | 1 | 1 |
| Including conditional mass conversions | All assignments | 2,364 | 243 | 106 |
| Including conditional mass conversions | Direct human single protein | 35 | 7 | 1 |

The second scenario **includes** the first. New Preliminary and new Supported
claims are distinct transitions; a newly Supported claim may have been
Preliminary or Limited before. A claim includes its binding/functional role;
curation of that molecule-target pair never upgrades another role.

### Explicit concentration units: 30 records

The allowlist accepts dimensionally explicit concentration units and an
unambiguous `10^integer` prefix. Examples: 19.2 pmol/L becomes 0.0192 nM;
1.5 in `10^3nM` becomes 1,500 nM. Apostrophe exponent spellings, inverse
concentrations, rates, doses, percentages and missing units are not guessed.

The 30 records affect 29 claims and 16 molecules across all assignments.
Six records concern five claims in the strict human subset. Phenelzine at
MAO-A gains a second publication for binding IC50 and becomes Supported
under the report rule. Imipramine-BRD4 gains one Preliminary binding claim,
from two domains measured in one publication; its 647/1,020 micromolar
values are above all four thresholds considered.

These are conversions of source-reported numbers, not independent correction
of those numbers. For example, some assay descriptions say the target's
origin is unknown despite the direct-human metadata. Preserve that conflict
for review rather than pretending unit conversion resolves it.

### Conditional mass conversion: 2,334 additional records

The mass allowlist covers `ug.mL-1`, `ug ml-1` and `ng/ml`. A proposed
conversion requires a structured Small molecule, a canonical structure,
and positive `full_mwt` on the **measured** ChEMBL record. For micrograms/mL:

`nM = value_in_micrograms_per_mL * 1,000,000 / molecular_weight_g_per_mol`

Using a parent freebase weight for a measured salt can give a different
answer. Even the correct source-record weight does not prove whether the
paper expressed mass as freebase, salt, hydrate or formulation. Hence this
is a conditional sensitivity estimate, with every assumed weight exported
in `unit_audit.csv`; it is not an automatically eligible import list.

Of 2,437 records in these three mass units, 103 fail the identity/weight
conditions. Alongside 247 missing, incompatible or unreviewed unit cases,
that leaves **350** non-nM records unrecovered. The larger conditional
scenario helps mostly evidence outside the strict direct-human subset.

### Threshold consequences

For each affected claim and endpoint, recompute the log-space median with
the proposed values. Both directions are shown: adding an exact measurement
can move a median above a threshold as well as below it. These are changes
in **claim-endpoint combinations**, not unique claims or molecules.

| Scenario | Basis | Threshold (uM) | New passes | Lost passes |
|---|---|---|---|---|
| concentration_only | all_assignments | 1 | 14 | 0 |
| concentration_only | all_assignments | 10 | 14 | 0 |
| concentration_only | all_assignments | 100 | 14 | 0 |
| concentration_only | all_assignments | 300 | 16 | 0 |
| concentration_only | human_single | 1 | 0 | 0 |
| concentration_only | human_single | 10 | 0 | 0 |
| concentration_only | human_single | 100 | 0 | 0 |
| concentration_only | human_single | 300 | 0 | 0 |
| including_conditional_mass | all_assignments | 1 | 116 | 26 |
| including_conditional_mass | all_assignments | 10 | 196 | 18 |
| including_conditional_mass | all_assignments | 100 | 258 | 6 |
| including_conditional_mass | all_assignments | 300 | 278 | 3 |
| including_conditional_mass | human_single | 1 | 1 | 0 |
| including_conditional_mass | human_single | 10 | 2 | 1 |
| including_conditional_mass | human_single | 100 | 4 | 0 |
| including_conditional_mass | human_single | 300 | 5 | 0 |

No conversion changes membership or establishes brain exposure. No original
coverage-gap molecule gains its first assessed claim in either scenario.

## 3. Organism-format exclusions

All 21,999 excluded rows are now in `organism_context.csv.gz`, including
published and standard value/unit fields, study references, assay organism,
target organism, confidence and assignment. Of these, 21,937 have organism
targets, 36 have protein/family/complex targets, and 26 have other targets.

The 36 protein-assigned rows span 22 assays. Every assay description was read
and its interpretation recorded in `organism_review.json`; this is a review
of source descriptions, not a full re-extraction of 22 original methods.

| Context identified from the description | Records |
|---|---|
| cell_assay_format_conflict | 2 |
| in_vivo_binding_dose_context | 3 |
| in_vivo_metabolic_response | 1 |
| in_vivo_occupancy | 4 |
| in_vivo_phenotype_exposure | 2 |
| in_vivo_physiology | 5 |
| microorganism_phenotype | 14 |
| platelet_context_ambiguous | 2 |
| polymerization_context_ambiguous | 1 |
| uptake_context_ambiguous | 2 |

Four records describe receptor occupancy, separating brain and plasma
concentrations. That is useful exposure/target-engagement context, but is
not the same quantity as a biochemical binding constant. Two describe cell
systems despite the organism-format label. The H1 assay for latrepirdine
explicitly names SK-N-SH cells; the cited publication discusses H1 and
5-HT6 antagonism, but its accessible abstract alone does not verify every
assay method. [Publication record](https://pubmed.ncbi.nlm.nih.gov/19443217/)

The appropriate immediate outcome is **context retention, with zero changes
to the baseline biochemical tiers**. Candidate metadata corrections remain
pending methods-level confirmation. The complete records and reasons are
in `organism_reviewed.csv`.

As a diagnostic, lifting the gate for the 31 protein-assigned positive exact
nM values would affect 27 functional claims, create 18 Preliminary
claims and upgrade 2 to Supported under the old counting rule.
This deliberately unsafe comparison in `organism_unsafe_pooling_diagnostic.csv`
shows why numerical eligibility alone is insufficient: different organism,
exposure, preparation and endpoint contexts must not manufacture replication.

## 4. Concrete catalogue policies

All choices use S0 core indication scope and keep parent normalisation.
The indication phase is `max_phase_for_ind`, not overall molecule phase.
The whole-ATC route has no implied indication-phase requirement.

| Selection | All types | Small molecules | Seeds in small-molecule set |
|---|---|---|---|
| Whole clinical catalogue | 2,245 | 1,771 | 24 |
| CNS Approved/Phase 3 only | 997 | 791 | 22 |
| ATC N + CNS Approved | 761 | 677 | 18 |
| ATC N + CNS Approved/Phase 3 | 1,206 | 995 | 22 |
| ATC N + CNS Approved/Phase 2/3 | 1,912 | 1,540 | 24 |

Every policy has all-type and literal Small-molecule versions. Theophylline's
parent and hydrate are both typed Protein in this ChEMBL release, so the
small-molecule filter exposes an identity annotation problem. It is not
silently corrected to preserve an old seed. The chosen Phase-3 set also
excludes theophylline on its indication phase. Theobromine, loperamide and
mibefradil fail S0 clinical membership; rolipram and pentoxifylline fail the
Phase-3 cutoff. `policy_seed_membership.csv` shows all 28 under every choice.

## 5. Evidence available under each policy

The following figures use baseline measurements, with human-specific
experimental assignment and supported human curation. Curated action,
binding and functional claims stay separate. Families and complexes retain
their original target identifier and are not expanded into component claims.

| Small-molecule selection | Supported molecules | Supported pairs | Targets with support | Usable molecules | No qualifying edge |
|---|---|---|---|---|---|
| Whole clinical catalogue | 1,137 | 3,074 | 795 | 1,310 | 461 |
| CNS Approved/Phase 3 only | 607 | 1,528 | 426 | 665 | 126 |
| ATC N + CNS Approved | 448 | 1,145 | 264 | 481 | 196 |
| ATC N + CNS Approved/Phase 3 | 666 | 1,653 | 431 | 738 | 257 |
| ATC N + CNS Approved/Phase 2/3 | 1,013 | 2,738 | 749 | 1,152 | 388 |

For the proposed 995 candidates, the exact effect of widening target type is:

| Evidence basis for the same 995 candidates | Supported claims | Supported molecules | Usable molecules |
|---|---|---|---|
| Human single proteins | 1,719 | 532 | 641 |
| + precise protein complexes | 1,804 | 557 | 663 |
| + families and complex groups | 2,049 | 666 | 738 |

The recommended representation keeps all three levels available and labelled.
Adding families/groups to the single-plus-precise-complex basis brings another
109 molecules with Supported evidence in this catalogue. Removing those
claims altogether would lose substantial neuropharmacology; expanding them
to subtype claims would misrepresent their specificity.

The 995 candidates have 63 withdrawal annotations and 12 structure-NONE
identities. Clinical selection does not mean currently approved, available,
brain-penetrant or fully identified. Preserve those distinctions in the UI.

Phase 2 adds 545 small molecules, 347 supported molecules and
318 supported targets versus the Phase-3 proposal under the same broad
human basis. That is a meaningful coverage tradeoff; the original report's
unqualified assertion of thinner evidence is unsupported and removed.

Explicit concentration recovery adds one Supported claim to the proposed
catalogue (2,049 becomes 2,050), with no new supported/usable molecule.
`policy_comparison.csv` contains both baseline and recovered scenarios for
all target bases and catalogue choices. Conditional mass conversion is not
included in the proposed policy figures.

## 6. Scope arithmetic and interpretation corrections

Core plus oncology plus pain is **2,523 (+278)**; core plus pain alone is
2,445 (+200), and the widest scope is 2,611 (+366). The original recommendation
conflated those alternatives. Evidence for added molecules outside the
baseline candidate set is not assessed by this follow-up.

Other corrections are incorporated into the main report: `Preliminary`,
chemical parents, ATC branches, MeSH descriptors/tree numbers, scope versions,
mapping failures and target assignments are explained at first use. The
retention table now distinguishes missing numerical eligibility from missing
exported records. The four known-bad activity rows are retained in a separate
follow-up audit while remaining excluded from all proposed evidence.

The bounds inventory contains >, <, >=, <= and >> relations, plus 28 approximate
`~` results under the old status name. They do not all mean no activity.
Confidence 4/6/8 is a mixed category; a >=7 filter cannot admit every record
in it. A count of 1,676 human single-protein target records is not a count of
targets with direct human experimental support.

## 7. Reproduction and validation

Run from the repository root:

```bash
python3 analysis/cohort1/followup/analyze.py
python3 -m unittest tests.test_cohort_report tests.test_cohort_followup -v
python3 analysis/cohort1/followup/write_summary.py
```

The original 16 analysis tests and 13 follow-up tests pass. They exercise
unit dimensions, the measured salt weight, non-exact relations, incompatible
endpoints, duplicate studies, dataset provenance, species/variant separation,
target granularity and phase-versus-ATC admission. The data validations in
`followup/out/validation.csv` verify baseline tier reproduction, scope and
exclusion accounting, complete assay review, uniqueness of native target
claims, and unchanged production fingerprints.

Source limits: no new ligand catalogue, literature-wide search, supplementary
database integration, full mass-basis verification, or viewer performance
benchmark is implied by these results. The original annotation pages refer
to the archived edition; the revised PDF has different pagination.
