# Prompt for Opus: generate the clinical cohort and evidence-tier report

Work in the repository root.

Generate the actual, reproducible clinical-cohort report described
below, including the analysis scripts, source provenance, and supporting data.
Carry the work through to a completed report rather than stopping at a plan.
Make reasonable implementation decisions autonomously and document them.

## Context and boundaries

Read these first:

- `CLAUDE.md`
- `docs/DATA-QUALITY-LOG.md`
- `docs/MOLECULE-EXPANSION-BRAINSTORM.md`

Inspect the schema, pipeline, local source data, and working-tree status.
Preserve existing uncommitted work. The brainstorming document contains
proposals, not an adopted selection policy; this report should make the
consequences of those proposals concrete enough to choose a policy.

The goal is an independently defined catalogue of molecules whose target
relationships help explain brain pharmacology. Evaluate **cohort 1: clinical
catalogue only**, together with its molecule–target evidence tiers. This name
refers to option 1 in the brainstorming document, not the historical
cohorts used to build the existing 28-molecule seed. This narrower scope takes
precedence over the brainstorming document's combined-cohort recommendation.

**Cohorts 2 and 3 are both deferred.** Do not build a curated-ligand catalogue
or admit molecules solely because they have a curated target relationship or
qualifying assay hit. Retrieve and evaluate curated and experimental evidence
for molecules admitted through the clinical selection rules below. Evidence
availability must not determine clinical-catalogue membership: retain eligible
molecules with no target data as coverage gaps.

This task authorizes new report files, analysis code, configuration, and
source caches. Open the existing project and ChEMBL databases read-only.
Do not modify the production schema, seed list, database, graph export, or
viewer; do not run a production rebuild or publish anything. Keep report
calculations separate from the production pipeline's current trust rules.

## Cohort 1: clinical catalogue

Generate candidates from the union of:

- ChEMBL ATC N (nervous-system) classifications.
- ChEMBL indications within an explicitly defined CNS indication scope.

Define that scope using stable MeSH/EFO identifiers and documented ontology
descendants where appropriate. Record inclusion and exclusion reasons for
boundary areas such as peripheral nervous-system disease, general pain,
local anesthesia, and CNS oncology. Name searches can assist discovery but
must not be the final membership rule. Include psychiatric and neurological
conditions in the considered scope.

Keep ATC-derived membership separate from indication-derived membership.
ATC N alone does not verify central action or approval for a CNS condition.
Retain the relevant classification codes, indication identifiers, and source
records for every candidate.

Break down the catalogue by approved status and development stage. For an
indication-based selection, use `drug_indication.max_phase_for_ind` for the
qualifying CNS indication, not the molecule's maximum phase across unrelated
conditions. Report approved, Phase 3, Phase 2, Phase 1/early-phase, and
unknown/preclinical categories as the source supports, keeping missing and
unknown values distinct. Show cumulative choices such as approved only,
approved plus Phase 3, and approved plus Phase 2/3 without making a final
policy choice. Explain that ChEMBL's value 4 labels Approved; it is not proof
of current jurisdiction-specific approval or completion of a Phase IV trial.
Preserve withdrawal annotations where available.

Reproduce the brainstorming document's ChEMBL 37 baseline query: 521 ATC N
small-molecule parents, 361 with an approved record in their compound family,
and 15 of the current 28 within ATC N. Verify these numbers instead of using
them as required outputs; explain discrepancies against the exact same scope
before introducing different filters or releases.

Report small molecules as the main comparison, with clinically selected
peptides, biologics, mixtures, unknown types, and unresolved identities
separately accounted for. Preserve supported category annotations, but do
not add endogenous ligands, research tools, or active metabolites unless they
independently meet the clinical selection rules.

## Target evidence to assess

For the fixed clinical candidate set, retrieve ChEMBL curated mechanisms and
target-attributed binding/functional evidence. Assess identifiable human
protein targets and defined protein families/complexes; keep nonhuman,
ambiguous, indirect, and other target types separately accounted for. Use
available source family identifiers to summarize coverage, without merging
different proteins or expanding one family-level claim into subtype claims.

Do not restrict evidence retrieval to the existing graph's targets or require
an independently curated CNS target list. Clinical relevance is established
by the candidate-selection route; whether a particular target relationship
explains a CNS effect is a separate question. Retain potential peripheral
off-targets with their context, without labeling every target of a clinically
selected drug as a CNS mechanism. Existing brain-expression annotations can
provide context, but neither their presence nor their absence is a gate.

## Evidence tiers

Assign evidence at the **molecule–target claim level**, retaining action and
binding/functional role where known. A well-supported target does not upgrade
all other claims for that molecule. Molecule-level summaries should show
counts of claims in each tier and whether any assessed human-target claim
qualifies. Retain eligible molecules with zero such claims.

Implement the following as proposed report tiers, with machine-readable
reasons and examples. These are report definitions, not new production rules:

- **Supported:** a traceable curated pharmacological relationship at its
  explicitly asserted target/action specificity, or qualifying target-specific
  experimental support from at least two distinguishable studies/publications.
  Record `curated_support` and `multiple_study_support` separately so the
  report shows which route qualified and their intersection. Curated support
  does not imply independently replicated measurement. Multiple papers are
  a documented proxy, not proof of independent laboratories or experiments.
- **Preliminary:** qualifying target-specific experimental support from one
  identifiable study, without Supported-tier evidence for that claim.
- **Limited or unresolved:** evidence exists but is annotation-only,
  indirect, untraceable, ambiguously assigned, or otherwise insufficient for
  the claim being evaluated. Preserve the specific reason rather than
  discarding the record.

Separately report **no eligible evidence found in assessed sources** and
**not assessed/source unavailable**. Do not treat a failed fetch as a negative
finding or turn missing evidence into an interaction edge.

Track target-assignment specificity and species alongside the tier. A curated
family/complex claim may be supported at that level; it must not become
supported claims for every individual member. ChEMBL scores 9, 7, and 8
represent different assignment categories, so do not use a generic `>= 7`
filter as a proxy for direct human single-protein evidence. Distinguish human
direct assignments from homologous/unknown-species assignments, mutants,
and nonhuman evidence. Use direct human evidence for the main empirical
comparison and report other evidence separately. Document ambiguous cases.

Preserve these evidence rules:

- Separate Ki, Kd, binding IC50, functional endpoints, and curated actions.
  Two binding studies do not establish agonism or antagonism. Avoid pooling
  biologically incompatible assay contexts into apparent replication.
- Require valid, positive, unit-normalized exact measurements for numerical
  summaries. Retain censored observations as bounds, and retain upstream
  validity flags and exclusions with reasons.
- Count original evidence, not database appearances. Reuse the project's
  documented exclusions and republication rules where applicable. Preserve
  original record, assay, document, DOI/PMID, and deposit identifiers; document
  how study identities and duplicates are resolved. Keep unresolved study
  provenance from manufacturing multi-study support.
- Curated affinity ranges and source summaries are not individual raw
  measurements. Do not turn their endpoints or cited reviews into additional
  experimental replicates.
- Keep contradictory findings visible, including conflicts in action or
  compatible measurements. Explain how conflicts affect the assessed claim;
  do not award stronger support simply by accumulating incompatible reports.

Show sensitivity at 1, 10, 100, and 300 micromolar for experimental claims
within the fixed cohort-1 candidate set. Document the aggregation rule used
to decide whether a claim passes a threshold, with endpoint types separate.
Report both qualifying claims and molecules with qualifying human-target claims.
Retain curated weak relationships and catalogue membership throughout; these
thresholds must not recruit additional molecules or imply physiological exposure.

## Sources, identity, and reproducibility

Use the local ChEMBL 37 bulk release at
`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db` for candidate selection
and a uniform evidence assessment across the entire clinical candidate set.
This ChEMBL baseline is the required analysis. Label its source coverage
explicitly; it is not an assessment of all evidence in the literature or all
six production sources.

Existing cached PDSP data and other supplementary evidence are optional if
they can be assessed consistently without substantially expanding the task.
Show any supplementation separately from the uniform ChEMBL baseline. Do not
extrapolate PDSP, BindingDB, or DGIdb coverage from the existing 28 alone or
let their richer existing coverage masquerade as stronger biology. Record
which molecule/source combinations were assessed and which were not.

Defer new GtoPdb, HPA, Chemical Probes Portal, and B3DB integrations. They are
not requirements for this clinical-cohort report. Keep existing expression,
clinical status, and exposure annotations separate from interaction evidence;
do not require known BBB penetration, brain enrichment, caffeine similarity,
or graph connectivity for membership.

Normalize equivalent parent/salt forms while preserving source identities.
Keep meaningful stereoisomers, prodrugs, metabolites, and mixtures distinct.
Use exact identifiers/structure mappings, not fuzzy name matches. Report
ambiguous mappings and retain source-native identities where unresolved.

Pin source versions and record URLs, retrieval dates, checksums, access status,
and relevant license information. Cache downloads outside tracked bulk data;
avoid committing large releases. Paginate completely where APIs are used,
use bounded retries, and record failures. Make the analysis rerunnable from
the saved snapshots, with deterministic outputs and explicit rule files.

## Required deliverables

1. A readable report at `docs/COHORT-REPORT.md`, linked from the project guide.
   Lead with the measured catalogue size, evidence coverage, and decisions
   the results support. Include:
   - Counts for the ATC N and CNS-indication admission routes, their
     intersection, exclusive portions, and deduplicated clinical catalogue,
     before and after each relevant rule. No cohort-2 or cohort-3 comparison.
   - Clinical-stage breakdowns and target-family/molecule-category coverage,
     including new areas beyond the current graph.
   - Tier distributions at claim and molecule level, separate curated versus
     multi-study support, specificity, conflicts, and threshold sensitivity.
   - A row for each existing seed molecule showing membership, admission or
     exclusion reasons, and evidence status. No automatic grandfathering.
   - Coverage gaps, unresolved mappings, incomplete source access, and a
     precise distinction between measured counts and any estimates.
   - A recommendation for the next import policy, explaining tradeoffs with
     concrete examples. This task does not adopt or implement that policy.
2. Machine-readable supporting data for candidates, overlapping membership
   reasons, observed targets/families, indication scope, assessed claims, evidence
   provenance, exclusions, gaps, and the 28-molecule comparison. Use documented
   join keys so every report count and representative claim can be traced
   back to source records. Do not provide only a ranked shortlist.
3. Reusable scripts or queries, versioned selection/tier configuration, a
   source manifest, and exact commands to reproduce the report. Link the
   supporting files from the report and explain their schemas.

Validate meaningful failure cases: parent/salt deduplication, admission-route union
arithmetic, unrelated-indication approval, missing study provenance,
cross-source duplicates, one family claim versus many subtype claims, and
multiple measurements from one paper. Check totals against the exported
records. Confirm the production database and graph artifacts were not changed.
Use targeted tests for new substantive analysis logic; avoid unrelated
refactoring or new tests that only restate constants.

Finish by summarizing the actual results, validation, file locations, and any
remaining access blockers. Do not label the report complete if the clinical
selection or required ChEMBL evidence assessment is materially missing;
deliver useful partial results with explicit coverage limits in that case.
Unavailable optional supplementary sources do not block completion of the
required analysis, but their absence must remain explicit.
