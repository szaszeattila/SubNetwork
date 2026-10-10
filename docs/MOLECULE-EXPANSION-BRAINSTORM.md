# Molecule expansion: options and selection criteria

Recorded 2026-09-06 from the September 5–6 discussion.

**Status: brainstorming, not an adopted selection policy.** The working
recommendation is to combine a clinical catalogue with a curated
neuropharmacology catalogue, and offer broader experimental compounds as an
optional layer. Dataset priorities and thresholds below are proposals. The
running pipeline still uses the 28-molecule seed list.

> **Superseded in part, noted 2026-09-17.** That last sentence was true when
> this was written and is not now: cohort 1 was built and the page opens on it.
> Only the **legacy** pipeline still uses the 28-molecule seed list. Everything
> below that describes "the current 28 molecules" or "the running pipeline"
> should be read as of 2026-09-06.
>
> The *reasoning* here was not superseded and is still the live argument — its
> three options, its dataset priorities and its rule that a filter like brain
> expression must not be a blanket admission gate. Which of the three options to
> take next is argued from measurements in
> [NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md), which recommends this
> document's **option 2** over its option 1, and the evidence for that is in
> [SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md).

The project goal remains to show which molecules share targets relevant to
the brain and how well each relationship is evidenced. See
[the project guide](../CLAUDE.md) and the existing
[data-quality history](DATA-QUALITY-LOG.md).

## Why change the selection method?

The current cohorts were chosen to connect to targets already present and
corroborate sparsely connected parts of the graph. That produced useful
structure, but keeps carrying the caffeine starting point forward. It also
favors heavily screened compounds and can mistake family-level assertions
for broad target coverage.

A systematic catalogue should admit a relevant molecule even when it opens
an entirely new component. Define membership independently of the current
graph, then decide which evidence and neighborhoods to display. A large
catalogue need not mean rendering every molecule and edge simultaneously.

## Three options

| Option | Inclusion rule | Benefit | Limitation |
|---|---|---|---|
| Clinical catalogue | Start with nervous-system drug classifications and CNS indications; optionally extend to clinical candidates. | Familiar molecules, reproducible candidate selection. | Misses endogenous ligands, research tools, and substances without clinical classifications. Classification alone does not establish central action. |
| Neuropharmacology catalogue | Define relevant human target families independently, then include their curated ligands: medicines, endogenous substances, natural compounds, and experimental tools. | Strong fit for comparing mechanisms across the brain. | Requires an explicit target scope; biochemical activity does not establish brain exposure. |
| Broad experimental catalogue | Include every identifiable compound with qualifying experimental activity at an in-scope target. | Broad discovery coverage, including obscure compounds and chemical series. | Much larger, unevenly studied, and harder for a non-expert to explore. |

Working recommendation: combine the first two for the main catalogue, with
the third as an expandable research layer. These cohorts may overlap; retain
all reasons a molecule qualified.

## A concrete clinical candidate count

A read-only query of the local **ChEMBL 37** release on 2026-09-05 found:

- 521 distinct small-molecule parents with an ATC **N (nervous system)**
  classification on a member of their compound family.
- 361 of those parents had at least one family record with `max_phase = 4`.
- 15 of the current 28 molecules fell within the ATC N candidate set.
  Theobromine and rolipram were among those outside it.

These are candidate counts before target/evidence filtering, not a count of
currently approved CNS treatments. ATC N is a useful starting screen, not a
complete definition of central nervous system pharmacology.

The query used `molecule_atc_classification` joined to `atc_classification`
where `level1 = 'N'`, normalized identifiers through
`molecule_hierarchy.parent_molregno` (falling back to the original molecule),
and required the parent's `molecule_type = 'Small molecule'`. The second
count checked both the parent and all family members for `max_phase = 4`.
The source file was
`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db`.

### What the phase terminology means

“Approved-phase record” was shorthand for a ChEMBL record labeled
`max_phase = 4` (Approved). It was not a claim about current approval in a
particular jurisdiction or completion of a Phase IV trial.

`molecule_dictionary.max_phase` summarizes development across indications;
`drug_indication.max_phase_for_ind` describes a particular indication.
For example, hypothetically, a drug approved for a skin disease but only in
Phase 2 for Parkinson's could have overall phase 4 and Parkinson's phase 2.
It would qualify as a CNS candidate, not as approved for Parkinson's.
[ChEMBL field definitions](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/drug-and-compound-questions)

For an indication-based cohort, first select the relevant disease identifiers,
then apply the desired phase threshold to those indication records. Keep
missing indication data as unknown. An ATC-derived cohort should retain its
classification-based membership reason rather than imply a verified CNS
approval. Clinical status is a scope annotation, not target-binding evidence.

## Dataset priorities

| Dataset | Proposed use | Priority |
|---|---|---|
| ChEMBL, already present | Main measurement and mechanism source; also use its classification and indication tables to generate candidates. | Retain as the backbone. |
| IUPHAR/BPS Guide to Pharmacology (GtoPdb) | Curated ligand–target interactions, actions, target families, endogenous ligands, and identifier mappings. | First new pharmacology source. |
| Human Protein Atlas (HPA) | Structured human brain-region and cell-type expression, keeping RNA and protein evidence distinct. | First new tissue-context source. |
| Chemical Probes Portal | Expert-assessed experimental probes, target assignments, ratings, and limitations. | Optional research cohort. |
| B3DB | BBB classifications, brain/blood ratios where available, references, and uncertainty. | Later exposure-context enrichment. |

GtoPdb supplies downloadable target, ligand, interaction, and endogenous-ligand
files, plus identifier mappings. Its target-family information can help
organize the catalogue without treating all members of a family as one
physical receptor. [GtoPdb downloads](https://www.guidetopharmacology.org/download.jsp)

Access detail checked September 2026: GtoPdb introduced website registration
on August 18 and announced API-key requirements for approximately September
15–17, 2026. The announcement distinguishes free access for non-commercial
organizations from commercial access fees. Check the access route and dataset
terms when implementing the import.
[GtoPdb access announcement](https://blog.guidetopharmacology.org/2026/07/29/user-registration-is-coming-to-gtopdb/)

HPA offers bulk human brain and cell-type expression data, including
GTEx-derived datasets. Start with those structured data instead of relying
only on UniProt tissue-specificity prose; preserve dataset provenance rather
than treating HPA and its imported GTEx data as independent confirmations.
[HPA downloads](https://www.proteinatlas.org/about/download)

The Chemical Probes Portal supports downloads and filtering by protein
family and expert rating. Probe quality would help choose useful experimental
comparators, but does not itself demonstrate human CNS activity.
[Portal FAQ](https://www.chemicalprobes.org/faq)

B3DB contains categorical BBB labels and a smaller subset with numerical
`logBB` data. Preserve references, uncertainty, species and experimental
context where available. Brain/blood distribution is not a measurement of
free concentration at a particular target or proof of target engagement.
[B3DB repository](https://github.com/theochem/B3DB)

Keep the other existing sources in their established roles: PDSP and
BindingDB for supplementary evidence, PubChem for identity, UniProt for
protein identity and context, DGIdb for annotations, and Wikidata for links.
The existing data-quality log documents their limitations and overlap.
More databases do not automatically mean more independent evidence.

## Proposed selection and evidence rules

1. **Define target scope independently.** Specify relevant target families
   using stable identifiers, derive their members, and version the scope.
   Candidate groups include neurotransmitter receptors, relevant channels,
   transporters, synthesis/degradation enzymes, and additional established
   molecular targets of CNS medicines. The current 207 targets must not be
   the eligibility boundary. Neuronal and glial relevance both matter.

2. **Record explicit admission routes.** A qualifying clinical annotation,
   curated relationship with an in-scope target, or sufficient experimental
   evidence can admit a molecule. Record all qualifying reasons and source
   releases. Keep relevant candidates with no usable target evidence in a
   coverage-gap inventory; do not manufacture graph edges for them.

3. **Normalize identity without erasing meaningful distinctions.**
   Consolidate equivalent salt/hydrate forms while retaining original source
   identities. Preserve distinct stereoisomers, active metabolites and
   prodrugs as appropriate, with explicit relationships. Do not turn mixture
   or formulation records into a single inferred chemical structure.
   Small molecules first is a scope choice; peptides and biologics can form
   additional cohorts rather than fail an arbitrary molecular-weight rule.

4. **Match evidence to the target claim.** Prefer direct human target
   assignments. Keep animal, homologous, mutant, family-level and complex-level
   evidence distinguishable. Do not fan one family assertion into independent
   subtype claims or interpret an indirect mechanism as measured binding.
   ChEMBL confidence 9 identifies a direct single-protein assignment, 7 a
   direct complex assignment, and 8 a homologous single-protein assignment.
   A blanket `>= 7` filter mixes these categories; confidence is about target
   assignment, not a general experiment-quality score.
   [ChEMBL assay definitions](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/chembl-data-questions)

5. **Separate evidence tiers.** A proposed core view could show curated
   relationships or support from multiple distinct studies. Single-study
   experimental hits remain an exploratory layer. Account for republication
   across sources; measurement rows, papers and databases are different
   counts, and distinct papers do not necessarily mean independent work.
   Preserve binding, functional effects and curated actions separately.

6. **Compare potency settings before choosing one.** For admitting compounds
   through experimental activity alone, compare candidate pools at 1, 10,
   100 and 300 micromolar. Ten micromolar is a suggested starting setting,
   not an accepted threshold or a boundary of physiological relevance.
   Preserve curated weak relationships, including the methylxanthine cases
   that motivated the existing cutoff rules. Binding and functional endpoints
   remain separate. Preserve censored results as bounds in any future raw
   evidence store; never pool them as exact measurements.

7. **Keep catalogue membership and display separate.** Optional display
   filters can select cohorts, evidence tiers, target context, or potency.
   A molecule need not connect to the present graph to qualify, and the
   viewer should make clear when a filter hides evidence or molecules.

## Filters that should not be universal admission gates

**Brain expression alone is too broad.** HPA reports brain RNA expression
for about 76% of human protein-coding genes. Conversely, demanding brain
enrichment would discard targets shared with other tissues. Use expression
as context and an optional filter; absence of annotation remains unknown.
[HPA human brain resource](https://www.proteinatlas.org/humanproteome/brain/human%2Bbrain)

Also avoid universal requirements for known BBB penetration, structural
similarity to caffeine, minimum graph degree, or drug-likeness scores.
Missing BBB data should not mean exclusion; endogenous CNS ligands also need
not enter the brain from blood to be relevant. A positive BBB label does not
establish an effect at the concentrations a target requires.

## Decisions to resolve with a candidate report

Before changing the seed list or doing a full import, compare cohorts against
the same pinned releases. Report:

- Candidate counts before and after each rule, deduplicated by chemical
  identity, with overlapping admission reasons retained.
- Coverage by target family and molecule category, including newly reached
  areas rather than only connections to the existing graph.
- Evidence tiers, target-assignment specificity, study support, and missing
  brain-expression or exposure annotations.
- Which of the existing 28 molecules qualify or fall outside each policy,
  and why; avoid automatic grandfathering based on existing membership.
- Sensitivity to the proposed potency settings and clinical-phase choices.
- Relevant molecules with no usable target edges, identity-mapping failures,
  and other coverage gaps.

The open choices are the CNS target/indication scope, clinical-stage cutoff,
molecular categories, and experimental admission thresholds. The next
implementation step should be this read-only comparison, followed by an
explicit selection policy. None of these proposed rules supersedes the
current pipeline invariants merely by appearing in this document.
