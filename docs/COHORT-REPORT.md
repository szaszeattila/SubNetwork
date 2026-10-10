# Cohort 1 — the clinical catalogue, measured

> **Status, added 2026-09-17: historical. Read this for what the alternatives
> would have cost, never for current figures.** This report measured candidate
> policies and **adopted none of them**. The policy that was adopted is in
> [COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) and what it built is in
> [COHORT-1-IMPLEMENTATION.md](COHORT-1-IMPLEMENTATION.md); the current totals
> are generated into `## Status` in [../CLAUDE.md](../CLAUDE.md). In particular
> the **2,245 molecules** and **138,509 claims** below, and the **995
> small-molecule** policy this report proposes, are none of them the catalogue.
> One factual error in the prose — about Neuralgia — is corrected inline under
> §1, "Route B — CNS indication scope".
> See [INDEX.md](INDEX.md) for which documents here are in force.

What a clinical-only selection rule actually produces against ChEMBL 37, and
how well evidenced the molecule–target claims inside it are.

**Revised 2026-09-12 after review of 11 Zotero questions.** Definitions are
expanded in place; exclusion retention and policy counts are corrected.
The original annotated edition is preserved in Zotero, with an unchanged
PDF, Markdown, and annotation export in `docs/archive/cohort-report-2026-09-12/`.
The headline below remains the original ChEMBL 37 baseline. New recovery and
policy comparisons are reported separately in section 6 and
[the follow-up analysis](COHORT-FOLLOWUP.md); they do not silently replace it.

**This report chooses nothing.** It measures the consequences of the clinical
option in
[docs/MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md) so a
selection policy can be chosen with numbers in hand. Nothing here changes the
seed list, the schema, the database, the graph export or the viewer, and the
tiers below are **report definitions, not production trust rules** — the
invariants in [the project guide](../CLAUDE.md) are untouched.

Cohorts 2 (curated ligands) and 3 (broad experimental) are deferred and not
compared here.

The original scripts and saved outputs are in
[`analysis/cohort1/`](../analysis/cohort1/README.md). The original MeSH cache
files are absent from this checkout, so `run_all.sh` would fetch a new MeSH
snapshot rather than reproduce its bytes. The follow-up reruns offline from
the saved descriptor classification and the pinned ChEMBL release:
`python3 analysis/cohort1/followup/analyze.py`.

---

## The headline

A clinical-only rule — ATC N **or** an in-scope CNS indication, deduplicated to
chemical parents — admits **2,245 molecules** from ChEMBL 37, of which
**1,771 are small molecules**. That is **80× the current 28-molecule seed set**,
and it reaches **4,885 distinct targets** (3,750 UniProt accessions) against
the graph's present 207.

Here **chemical-parent deduplication** counts related salt/hydrate records
once while retaining their original identities; see the worked theophylline
example in section 2. It does not merge distinct prodrugs or stereoisomers
where ChEMBL gives them separate parents.

The evidence behind it is thinner than the size suggests, and thins further
the more carefully the target assignment is read:

| | Claims | Molecules |
|---|---:|---:|
| Molecule–target claims assessed | 138,509 | 2,245 |
| **Supported** | 9,014 (6.5%) | 1,555 |
| **Preliminary** | 38,506 (27.8%) | — |
| **Limited or unresolved** | 90,989 (65.7%) | — |
| Supported on **direct human single-protein** evidence only | 3,442 (2.5%) | 1,125 |
| No eligible evidence under the report rules (ChEMBL 37) | — | 361 |

**Preliminary** means experimental evidence is available for that particular
molecule-target-role claim but does not meet the report's replication rule.
It is not a clinical phase or a rating of the whole molecule; section 3 gives
the study and target-assignment qualifications.

Three findings drive every recommendation at the end:

1. **Two thirds of all claims are Limited or unresolved. 59,327 claims
   (43% of the total) have no qualifying exact value and at least one bound
   or approximate result.** These are informative observations, but cannot be
   pooled as exact measurements. Their direction matters: `Ki > 10,000 nM`
   and `Ki < 1 nM` imply different things, and `~` means approximate rather
   than censored. Preserving that distinction extends
   [invariant 1](../CLAUDE.md#invariants) to a much larger dataset.
2. **The two Supported routes barely overlap.** 1,321 molecule–target pairs are
   supported by curation alone, 6,138 by replicated measurement alone, and only
   **538 by both**. Curation and measurement are answering different questions,
   and a single "supported" badge would hide that.
3. **The catalogue is defined independently of the graph and it shows.** 206 of
   the current 207 targets reappear, and 3,544 accessions are new. The clinical
   rule does not merely extend the caffeine neighbourhood; it replaces its
   centre of gravity with the aminergic receptors and transporters.

---

## 1. How membership is defined

Two admission routes, kept separate throughout. **Neither is evidence of
anything.** ATC N is a classification, not a verified claim of central action;
an indication record is a development or approval annotation, not a target
relationship. Membership is settled first, and evidence is assessed afterwards
on the fixed candidate set — so evidence availability never decides who is in
the catalogue.

### Route A — ATC N

A molecule is admitted when it, or any member of its ChEMBL compound family,
carries an ATC level-5 code whose level 1 is `N` (nervous system).

ATC is a hierarchy of drug categories. A **subtree** means a branch plus its
more specific categories: for example `N` (nervous system) contains `N01`
(anaesthetics), which contains `N01B` (local anaesthetics).

ATC N is taken **whole** in this baseline. The
[report-generation instructions](prompts/COHORT-REPORT-PROMPT.md) asked for explicit
decisions about local anaesthesia and general pain, among other boundaries.
The analysis author translated those concerns into two ATC branch flags:
they are *flagged in the output rather than removed*. This was a report design
choice, not a requirement to exclude them and not a production selection rule.

| Flag | ATC level 3 | Molecules | Why flagged |
|---|---|---:|---|
| `peripheral_site_of_action` | N01B — anaesthetics, local | 20 | Local anaesthetics block peripheral nerve conduction at the site of application. ATC files them under N because they act on nervous tissue, not because they act centrally. |
| `general_analgesic` | N02B — other analgesics and antipyretics | 37 | Paracetamol and kin. Same argument as the pain indication class, arriving by the ATC route. |

They are flagged, not dropped, precisely because the ATC route's whole point is
that it is a classification and not a verified claim — hiding its weakest cases
would make it look stronger than it is. Several (lidocaine, mexiletine) have
real central and cardiac target pharmacology anyway.

### Route B — CNS indication scope

A molecule is admitted when a `drug_indication` record for it, or for a family
member, names a MeSH descriptor inside the report's saved indication scope.

**MeSH** means *Medical Subject Headings*, the US National Library of Medicine's
controlled vocabulary for organising biomedical information. A **descriptor**
is a defined concept with an identifier, such as `D010146` for Pain. A
**versioned scope** is our documented rule for which concepts qualify: this
report uses version **1.0.0** in `config/cns_indication_scope.json`. MeSH supplies
the vocabulary; the project chooses the inclusion rule. The rule version and
the dated MeSH snapshot are separate parts of reproducibility.
[NLM MeSH](https://www.nlm.nih.gov/databases/download/mesh.html)

**MeSH tree numbers are addresses within that hierarchy.** `C10` identifies
the nervous-system disease branch; `C10.597.617.470` is one placement of
Neuralgia. One descriptor may have several placements. Its descriptor ID
identifies the concept, while its tree numbers locate it within categories.
[NLM tree structures](https://www.nlm.nih.gov/mesh/intro_trees.html)

> **Correction, added 2026-09-17.** This report's prose goes on to argue that
> the peripheral-nerve exclusion is safe because Neuralgia (`D009437`) keeps an
> in-core placement at `C10.597.617.470`. **The classification this report
> itself saved says otherwise**: its C10 placement is `C10.668.829.600`, inside
> the excluded branch, with `in_core_scope = 0`.
> [COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md) caught this and is
> correct; the adjudication is in
> [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) under "The report's own prose was
> wrong about Neuralgia". The adopted scope resolves it with an explicit
> inclusion set that overrides the boundary exclusions, because adding the Pain
> tree recovers neuralgia and postherpetic neuralgia but **not** trigeminal
> neuralgia, facial neuralgia or fibromyalgia. The saved data was right
> throughout; only the sentence about it was wrong.

The analysis obtains those placements by exact descriptor ID from the NLM
MeSH SPARQL endpoint, a service for structured queries. Heading text is not
the final matching rule. A name search can return a related concept, synonym,
or broader term; it does not always fail. The project's actual ADRA1A-to-ADRA1D
search error occurred in UniProt, not MeSH, and motivates
[invariant 15](../CLAUDE.md#invariants).

All **2,178** distinct `mesh_id` values in ChEMBL 37's `drug_indication`
resolved in the original run. **Unresolvable** would mean an ID could not be
matched to its MeSH record and tree information. Zero failed mappings checks
that lookup, not the biological validity of the chosen scope.

**Descendant rule.** A descriptor is in a class when any of its tree numbers
equals the class tree number or begins with it followed by a period.

**Core scope** = `C10` (Nervous System Diseases) ∪ `F03` (Mental Disorders),
minus the excluded boundary classes below. 974 descriptors, 359 of them
actually used by ChEMBL indications.

**Exclusion rule.** A descriptor leaves the core only when *every* one of its
in-scope tree placements sits inside an excluded class. Anything with a
remaining in-core placement stays. This is what keeps myasthenia gravis
(autoimmune `C10.114` **and** neuromuscular-junction `C10.668.758`) inside the
core while genuinely muscle-only disease falls out.

### Boundary decisions, with the argument against each

| Class | MeSH | In core? | Reason | Counter-argument |
|---|---|---|---|---|
| **CNS oncology** | `C10.551`, `C04.588.614` | **No** | Sits inside C10 but admits drugs selected by oncology pharmacology. The relationship explaining a temozolomide glioma record is DNA alkylation, not neurotransmission. | Agents used for tumour-associated seizures or oedema are genuinely central — and they re-enter the core through their own non-oncology indications. |
| **Peripheral / cranial nerve** | `C10.668.829`, `C10.292` | **No** | A peripheral neuropathy indication does not establish central action, which is the property the catalogue is about. | Pregabalin, duloxetine and carbamazepine act centrally — and nearly all re-enter through epilepsy, mood or neuropathic-pain descriptors carrying a `C10.597` placement. |
| **Muscle and NMJ** | `C10.668.491`, `C10.668.758` | **No** | Muscular dystrophies are diseases of muscle, filed under C10 only because MeSH groups neuromuscular disease there. | Cholinesterase inhibitors for myasthenia gravis share targets with the Alzheimer's drugs central to this project — and they are admitted through the autoimmune placement anyway. |
| **General pain** | `C23.888.592.612` | **No — by construction** | *Measured, not assumed*: MeSH `Pain` (D010146) carries `C23.888.592.612`, `F02.830.816.444` and `G11.561.790.444`, and **none under C10 or F03**. General pain never enters the core; no rule is needed to keep it out. | `Neuralgia` (D009437) carries **both** `C10.597.617.470` and `C23.888.592.612.547`, so nervous-system pain is already in core while non-neurological pain is not. This is the split worth keeping. |
| **Local anaesthesia** | — | n/a | Not a disease; it reaches the catalogue only through ATC N01B, and is flagged there. | — |

Each class is reported as its own additive delta, so none of these is a final
decision. Full per-descriptor detail: `out/indication_scope.csv`.

---

## 2. What the routes produce

### Admission-route arithmetic

Deduplicated to chemical parents. `arithmetic_holds` is verified for every row
(`|A ∪ B| = |A| + |B| − |A ∩ B|`) — check 3 in `out/validation.csv`.

| Stage | ATC N only | Indication only | Both | **Union** |
|---|---:|---:|---:|---:|
| All molecule types | 136 | 1,701 | 408 | **2,245** |
| Small molecules only | 132 | 1,250 | 389 | **1,771** |
| Small molecules with an Approved record in the family | 65 | 591 | 296 | **952** |

The routes are **not** substitutes. Only 408 molecules arrive by both; 1,701
arrive by indication alone and would be invisible to an ATC-only rule, and 136
arrive by ATC alone with no in-scope indication record at all.

### Checking the earlier ATC-N counts (ChEMBL 37)

The **baseline** is the earlier ATC-N-only calculation in the brainstorming
document. **Reproduction** means rerunning that same query, with the same
parent normalisation, small-molecule filter and ChEMBL release, and checking
that the counts agree. It does not mean independently repeating experiments
or validating every conclusion in this report. The counts agree **exactly**:

| Quantity | Document | Measured |
|---|---:|---:|
| ATC N small-molecule parents | 521 | **521** |
| …with an approved record in the compound family | 361 | **361** |
| Current seed molecules inside ATC N | 15 of 28 | **15 of 28** |

No discrepancy to explain. The differences that appear elsewhere in this
report come from deliberately different scope — 544 rather than 521 because
the catalogue does not pre-filter to small molecules, and 373 rather than 361
for the same reason.

### Scope sensitivity

| Variant | Union | Δ vs core |
|---|---:|---:|
| **S0 core** (C10 + F03 − excluded classes) | **2,245** | — |
| S1 + CNS oncology | 2,323 | +78 |
| S2 + peripheral / cranial nerve | 2,330 | +85 |
| S3 + muscle and NMJ | 2,338 | +93 |
| S4 + general pain | 2,445 | +200 |
| S5 widest (all of C10 + F03 + Pain) | 2,611 | +366 |

The boundary decisions move the catalogue by at most 16%. General pain is the
largest single one at +200 — and it is also the one whose molecules are least
likely to be explained by a central target relationship.

### Clinical stage

Two different quantities, reported in two columns and never merged.

**Indication-specific** (`drug_indication.max_phase_for_ind` for the qualifying
CNS indication) — the honest one for an indication-based selection:

| Stage for the qualifying CNS indication | Molecules | Cumulative |
|---|---:|---:|
| Approved (ChEMBL 4) | 506 | 506 |
| Phase 3 | 491 | 997 |
| Phase 2 | 769 | 1,766 |
| Phase 1 | 311 | 2,077 |
| Early Phase 1 (0.5) | 25 | 2,102 |
| Unknown (ChEMBL −1) | 7 | — |
| Not applicable (ATC route only, no in-scope indication) | 136 | — |

**Molecule-level** (`molecule_dictionary.max_phase` across the compound family,
any condition): 1,147 Approved, 386 Phase 3, 591 Phase 2, 101 Phase 1, 19
Unknown.

The gap between them is the point. **1,147 candidates have an Approved record
somewhere in the family, but only 506 are approved *for a CNS indication*.**
591 are approved elsewhere while their qualifying CNS indication sits below
phase 4 — prazosin (`CHEMBL2`) is approved, and Phase 3 for its CNS
indication. Collapsing those columns would have inflated "approved CNS drugs"
by more than twofold.

ChEMBL's `max_phase = 4` labels **Approved**. It is not proof of current
approval in any particular jurisdiction, and it is not a completed Phase IV
trial. Missing and Unknown (−1) are kept as distinct categories throughout,
never folded into zero. Withdrawal annotations are preserved: **78** candidates
carry `withdrawn_flag` somewhere in the compound family.

### Molecule categories

Small molecules are the main comparison; everything else is accounted for
separately rather than filtered away.

| `molecule_type` | Molecules | | `structure_type` | Molecules |
|---|---:|---|---|---:|
| Small molecule | 1,771 | | MOL (a structure) | 1,761 |
| Protein | 127 | | SEQ (sequence only) | 232 |
| Unknown | 117 | | BOTH | 30 |
| Antibody | 115 | | **NONE (unresolved identity)** | **222** |
| Enzyme | 32 | | | |
| Oligonucleotide | 31 | | | |
| Gene | 19 | | | |
| Vaccine component | 16 | | | |
| Oligosaccharide | 11 | | | |
| Cell | 5 | | | |
| Antibody drug conjugate | 1 | | | |

**222 candidates have no chemical structure in ChEMBL at all** (`structure_type
= NONE`) — mixtures, botanicals such as `GINKGO`, and formulation records.
They are retained with their identity marked unresolved. No endogenous ligand,
research tool or active metabolite was added; every row here met a clinical
selection rule on its own.

### Identity: parent/salt normalisation

**Deduplicated to chemical parents** means counting related salt or hydrate
forms once, using ChEMBL's explicit parent links. A parent is the reference
compound in this database hierarchy, not a biological precursor. The analysis
uses the parent's `molregno` identifier while every contributing source form
is kept in `out/family_members.csv`. Nothing is matched on a name.

This prevents several forms of one compound appearing as several catalogue
molecules. It does not assert identical absorption or exposure across
formulations, and mass-to-molar conversions must still use the chemical form
actually measured rather than automatically using the parent freebase weight.

- 2,245 parents span 3,668 family members — **1,423 salt, hydrate and
  formulation records folded in**.
- 883 parents have more than one form; the largest family has 16.
- **11** family members carry the ATC N code while the parent does not, and
  **448** carry the qualifying indication while the parent does not. Ignoring
  the hierarchy would have lost those molecules entirely.
- Meaningful distinctions are preserved: stereoisomers, prodrugs, metabolites
  and mixtures stay separate parents where ChEMBL treats them so.

The known hard case behaves correctly. The seeded theophylline record
`CHEMBL1355736` (the monohydrate — and typed `Protein` in ChEMBL 37, a source
oddity worth noting) rolls up to parent `CHEMBL190`, "theophylline anhydrous".
It is **one** catalogue row, not two. This is the same record the data-quality
log records as a false positive in an earlier sweep, and it is the only seed
that is not its own parent.

---

## 3. Target evidence

### What was assessed, and what it excludes

Uniformly across all 2,245 candidates and their 3,668 family members: every
`drug_mechanism` record and every `activities` row in ChEMBL 37.

**1,138,364 activity rows scanned.** 310,719 fell in scope (assay type B or F,
an endpoint type the report recognises); **117,519 were valid exact
measurements**.

| Excluded / retained | Activity rows | In baseline measurement audit? |
|---|---:|---|
| Assay type not B or F | 483,915 | no |
| Standard type out of scope | 321,727 | no |
| **Bound or approximate result** (`>`, `<`, `~`, …) | **81,867** | **yes, relation preserved** |
| Null value | 102,708 | yes, excluded from numerical use |
| Organism-based format (whole-organism readout) | 21,999 | no |
| Other relation | 5,903 | yes, excluded from numerical use |
| Units not nM | 2,714 | yes, original value and units |
| Non-positive value | 8 | yes, excluded from numerical use |
| **Documented known-bad records** | **4** | **no; aggregate exclusion count only** |

The last row is the project's own `CHEMBL_ASSAY_LINK_EXCLUSIONS`
(`CHEMBL5133661`, `CHEMBL1074487`), reused verbatim and applied on this path
too. Their aggregate counts were retained, but the original report incorrectly
claimed their individual rows were exported. The follow-up now supplies all
four in `followup/out/known_bad_excluded_records.csv`.
ChEMBL's `data_validity_comment` and
`potential_duplicate` flags are **recorded per measurement and reported, not
used to drop rows**, matching how the production pipeline stores them. Here
"valid exact" means eligible under these analysis rules; it is not an
independent certification of experimental quality.

**Why exclude organism-format observations?** A whole-organism response may
combine several targets, metabolism and exposure, so it cannot automatically
support a direct protein-binding edge. The original gate is nevertheless too
broad to justify discarding the context: 21,937 of its 21,999 excluded rows
have organism targets, but **36 have protein, family or complex targets** and
26 have other assignments. The 36 include receptor occupancy in rat brain
and descriptions that conflict with the organism-format label. They are now
preserved and individually reviewed in `followup/out/organism_reviewed.csv`.
Section 6 distinguishes contextual retention from numerical pooling.

**Why require nM?** nM means nanomolar, a concentration unit. The original
analysis trusts ChEMBL's standardisation and accepts only literal nM for
numerical summaries. It nevertheless exports all **2,714** non-nM records
with status `excluded_units`. The earlier "not kept" label was wrong.
Some concentrations are convertible; dose, percentage, rate and missing units
need different treatment. The follow-up finds **30** explicit concentration
conversions and **2,334** conditional mass-based conversions. The latter
depend on the material and molecular-weight basis, so remain a separate
sensitivity scenario. No conversion changes catalogue membership.

The retained relation counts are **80,812 `>`**, 902 `<`, 87 `>=`, 33 `<=`,
28 `~`, and 5 `>>`. The legacy status name `retained_as_bound` includes the
28 approximate results; none enters an exact median. A bound can constrain
potency without identifying its exact value and cannot universally be labelled
"tested, no activity detected".

### Claim granularity

A claim is `(molecule parent, target, role)` where role is `curated`,
`binding` or `functional`. Endpoint types (Ki, Kd, binding IC50, functional
IC50, EC50, AC50, Kb) are separate classes and are **never pooled**;
replication is only ever counted inside one class. Two binding studies do not
establish agonism. A well-evidenced target does not upgrade any other claim
for the same molecule.

### Tier distribution

**Preliminary** means a claim has a qualifying exact measurement linked to a
study, but lacks the report's required replication within the same endpoint
class. Usually it is one paper; it can also be a patent, a deposited dataset,
or several papers split across endpoints. Twenty measurements from one paper
remain one study. This is an evidence category for one molecule-target-role
claim, not a clinical development phase or a verdict on the whole molecule.
Species and target-assignment specificity remain separate: a Preliminary
claim is not automatically a direct human-protein claim.

| Role | Supported | Preliminary | Limited/unresolved |
|---|---:|---:|---:|
| curated | 1,859 | — | 140 |
| binding | 4,441 | 11,753 | 70,804 |
| functional | 2,714 | 26,753 | 20,045 |
| **All** | **9,014** | **38,506** | **90,989** |

Restricted to **direct human single-protein** evidence - the report's strict
comparison for a named human protein. Human family and complex claims remain
valid at their asserted level and are compared separately in the follow-up:

| Role | Supported | Preliminary | Not applicable |
|---|---:|---:|---:|
| curated | 1,195 | — | 804 |
| binding | 1,980 | 4,116 | 80,902 |
| functional | 267 | 683 | 48,562 |
| **All** | **3,442** | **4,799** | **130,268** |

Supported drops from 9,014 to 3,442 — **62% of Supported claims lose that
status when evidence outside this strict basis, including family and complex
claims, is set aside.** Both
columns are reported; neither replaces the other.

### Why so much is Limited or unresolved

| Reason | Claims |
|---|---:|
| `censored_only` - no qualifying exact value and at least one bound/approximate result | **59,327** |
| `null_value_only` | 30,735 |
| `no_qualifying_exact_measurement` | 494 |
| `invalid_units_only` | 293 |
| `curated_no_target_assigned` — `drug_mechanism.tid` is null | 139 |
| `curated_untraceable` — no reference and no comment | 1 |

The reason is preserved on every claim rather than discarded. 63,545 claims
carry at least one censored measurement. A failed fetch is never recorded as a
negative finding, and missing evidence never becomes an interaction edge.

### The two Supported routes, and their intersection

The routes land on different claim rows by construction — curated support is a
property of a curated claim, replication of an experimental one — so the
intersection is a **molecule–target** fact and is rolled up as one
(`out/target_pairs.csv.gz`):

| Support route | Pairs |
|---|---:|
| Curated only | 1,321 |
| Replicated measurement only | 6,138 |
| **Both** | **538** |
| Neither | 118,199 |

7,997 pairs carry any support at all, covering 1,555 molecules and 2,090
targets. Only **6.7% of supported pairs are supported both ways.**

Two caveats the numbers cannot carry on their own:

- **Curated support does not imply an independently replicated measurement.**
  It is one curator's assertion with a traceable reference. 2,263 of the 2,267
  mechanism records carry at least one; ChEMBL's references include DailyMed,
  FDA labels and Wikipedia as well as PubMed.
- **Multiple papers are a documented proxy for independence, not proof of it.**
  Two publications may share a laboratory, a compound batch or an assay
  protocol. What is measured is "two distinguishable publications", and that is
  what the column is named.

Deposited bulk datasets never create multi-study support, and the scale of
what that prevents is worth stating plainly. The 117,519 valid exact
measurements resolve to **19,321 distinct studies**, of which 18,855 are
publications:

| Provenance | Exact measurements | Distinct studies |
|---|---:|---:|
| Publication (PubMed id or journal DOI) | 89,829 | 18,855 |
| Deposited dataset | 26,095 | **45** |
| Patent | 1,592 | — |
| Unresolved | 3 | — |

**26,095 measurements collapse to 45 studies**, and 19,041 of them — the
Sanger Genomics of Drug Sensitivity in Cancer deposit — collapse to exactly
**one**. Counting activity rows, or dataset DOIs, as studies would have
manufactured replication on that scale. Validation check 5 asserts zero claims
reached Supported that way.

### Target-assignment specificity

**Assignment** describes what the experiment can be attributed to.
**Homologous** means a related protein is assigned in place of a confidently
identified exact target, often across species. When the original species is
unknown, even a human-labelled target record may carry a homologous assignment.
Scores 4, 6 and 8 distinguish multiple homologous proteins, homologous complex
subunits and a homologous single protein; relationship `H` also marks homology.

**Non-protein or unassigned** groups several different cases: confidence 0 / U
means not yet assigned or curated; 1 / N means a non-molecular target such as
a cell line or organism; 2 / S means a subcellular fraction; and 3 / M means
a molecular target other than a protein. Such observations can be useful
without identifying which named protein caused a response.
[ChEMBL assay definitions](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/chembl-data-questions)

| Assignment | Claims |
|---|---:|
| Homologous or unknown species (confidence 4/6/8, or relationship H) | 78,928 |
| Non-protein or unassigned (confidence ≤ 3, relationship N/S/M/U) | 25,499 |
| **Human direct single protein** (type SINGLE PROTEIN, tax 9606, confidence 9, relationship D, no variant) | **22,003** |
| Nonhuman | 9,001 |
| Human curated | 1,738 |
| Human family or multiple (confidence 5, or PROTEIN FAMILY) | 571 |
| Human direct complex (confidence 7) | 430 |
| No target assigned | 139 |
| Human direct single protein, **mutant** (variant present) | 49 |

ChEMBL confidence 9, 7 and 8 are three *different assignment categories* —
direct single protein, direct complex subunits, homologous single protein —
not a general experimental-quality score. **A generic `>= 7` filter mixes all
three, including homologous score-8 assignments.** The earlier claim that it
would admit all 78,928 rows of the combined 4/6/8 category was incorrect.
This report
never uses `>= 7` as a proxy; it tests for 9 + D + SINGLE PROTEIN + tax 9606 +
no variant explicitly, and reports the rest separately.

### Family and complex claims are not fanned out

477 curated claims are asserted at family or complex level and stay there:

| Molecule | Target | ChEMBL type | Action |
|---|---|---|---|
| PRAZOSIN | Adrenergic receptor alpha-1 | PROTEIN FAMILY | ANTAGONIST |
| NICOTINE | Neuronal acetylcholine receptor α4/β2 | PROTEIN COMPLEX | AGONIST |
| DIAZEPAM | GABA-A receptor; anion channel | PROTEIN COMPLEX GROUP | POSITIVE ALLOSTERIC MODULATOR |
| FLUMAZENIL | GABA-A receptor; anion channel | PROTEIN COMPLEX GROUP | ALLOSTERIC ANTAGONIST |
| INDOMETHACIN | Cyclooxygenase | PROTEIN FAMILY | INHIBITOR |

Expanding these to their member components would have produced **3,146 claims
instead of 477 — 2,669 additional "supported" claims carrying no additional
assertion.** That is exactly the mechanism-fan-out failure the data-quality log
records as detected by nothing in the production pipeline, quantified here.
Validation check 8 asserts it did not happen.

### Conflicts

- **Directional action conflicts: 0.** No molecule–target pair carries curated
  actions that disagree in direction (POSITIVE vs NEGATIVE modulator).
  Independently confirmed against ChEMBL directly, so this is a real zero, not
  a broken check.
- **Action refinements: 5.** Different action strings that do not contradict —
  varenicline `AGONIST` / `PARTIAL AGONIST` at the α4β2 nicotinic receptor,
  fingolimod `AGONIST` / `BINDING AGENT`, chloroquine `BINDING AGENT` /
  `INHIBITOR`. Counted separately so a refinement is never reported as a
  contradiction.
- **Measurement dispersion: 1,832 claims** where values within one endpoint
  class, from two or more distinct studies, span more than 100×. Prazosin at
  the α1 adrenergic receptor spans 0.01 nM to 1,148 nM in binding Kd across
  three studies — a 100,000-fold disagreement inside one supported claim.

**A conflict never raises a tier.** A claim with a conflict keeps its tier and
carries the flag and detail, so accumulating incompatible reports cannot look
like stronger support.

### Threshold sensitivity

Applied **only inside the fixed candidate set**. Thresholds admit no molecule
and remove none, and say nothing about physiological exposure. Curated weak
relationships keep their membership and their tier at every threshold —
caffeine's curated ADORA3 mechanism at Ki = 100 µM is unaffected.

Aggregation rule: a `(claim, endpoint class)` passes at T when the **log-space
median** of its qualifying exact nM values is ≤ T. The looser "any measurement
≤ T" rule is reported alongside.

| Threshold | All evidence: claims (median / any) | All: molecules | Human-direct: claims | Human-direct: molecules |
|---|---:|---:|---:|---:|
| 1 µM | 20,828 / 22,075 | 1,164 / 1,183 | 4,864 / 5,158 | 799 / 825 |
| 10 µM | 33,885 / 34,671 | 1,296 / 1,301 | 6,974 / 7,118 | 917 / 928 |
| 100 µM | 44,843 / 44,996 | 1,355 / 1,359 | 7,972 / 8,003 | 991 / 992 |
| 300 µM | 48,321 / 48,425 | 1,362 / 1,365 | 8,161 / 8,183 | 1,007 / 1,010 |

The choice of threshold matters far less than the choice of evidence basis.
Moving from 1 µM to 300 µM changes the molecule count by 17% (1,164 → 1,362);
moving from all evidence to direct human single-protein evidence changes it by
31% at 1 µM and, more importantly, cuts qualifying claims by 77%. The median
and "any" rules barely differ — this data is not threshold-sensitive in the
way the brainstorming document anticipated.

### Target and family coverage

**4,885 distinct ChEMBL target records**, representing 3,750 UniProt accessions;
**1,676 target records are typed as human single proteins**. A human single
protein means one specified protein type, such as human ADORA1, rather than a
family, multi-protein complex, cell line or organism. It does not mean one
physical protein molecule or an experiment in human participants: a human
receptor expressed in a laboratory cell system can qualify.

Target identity alone is weaker than **direct human single-protein evidence**,
which additionally requires confidence 9, relationship D and no recorded
variant. The 1,676 count does not mean that every target has direct experimental
support or is relevant to the brain. Against the current graph:
**206 of the present 207 targets
reappear, and 3,544 accessions are new.**

| ChEMBL protein class | Targets | Claims | Supported | Not in current graph |
|---|---:|---:|---:|---:|
| Enzyme | 1,737 | 42,956 | 2,586 | 1,662 |
| (unclassified) | 1,495 | 26,749 | 2,568 | 1,495 |
| Membrane receptor | 524 | 47,974 | 2,051 | 445 |
| Ion channel | 306 | 7,434 | 692 | 237 |
| Transporter | 159 | 4,850 | 372 | 146 |
| Transcription factor | 125 | 5,877 | 251 | 119 |
| Epigenetic regulator | 86 | 355 | 119 | 84 |

Family labels come from ChEMBL's `protein_classification`, used **only** to
summarise coverage. The data-quality log records that it must never be used to
infer physical assembly — it is a sequence and function taxonomy blind to
that, filing CACNA1C and CACNA1D on one leaf.

Best-evidenced human single-protein targets:

| Target | ChEMBL | Molecules | Supported claims |
|---|---|---:|---:|
| D(2) dopamine receptor | CHEMBL217 | 745 | 99 |
| 5-HT2A receptor | CHEMBL224 | 735 | 83 |
| hERG (KCNH2) | CHEMBL240 | 859 | 75 |
| μ-opioid receptor | CHEMBL233 | 858 | 59 |
| Noradrenaline transporter | CHEMBL222 | 847 | 59 |
| Serotonin transporter | CHEMBL228 | 846 | 58 |
| 5-HT1A receptor | CHEMBL214 | 826 | 53 |

This is a genuinely different centre of gravity from the present graph, whose
best-connected nodes are the adenosine receptors, the phosphodiesterases and
the cholinesterases. hERG's position is a caution, not a discovery: it is a
safety-screening target, and its 859 molecules reflect regulatory panels, not
brain pharmacology. **Retaining peripheral off-targets with their context —
rather than labelling every target of a clinically selected drug a CNS
mechanism — is why hERG appears here honestly instead of being quietly
promoted.**

---

## 4. The existing 28

No grandfathering. Each seed was tested against the same rules.

**25 of 28 qualify.** 15 by both routes, 10 by indication only, 3 not admitted.
24 of the 25 have at least one Supported direct-human claim.

| Seed | In? | ATC N | CNS ind. | Admission / exclusion reason | Claims | Sup. | Prelim. | Cur. | Multi | HD sup. |
|---|:-:|:-:|:-:|---|---:|---:|---:|---:|---:|---:|
| caffeine | ✓ | ✓ | ✓ | ATC N (N06BC01); 18 core MeSH terms | 207 | 21 | 34 | 1 | 20 | 10 |
| theophylline | ✓ | — | ✓ | core CNS indication (2 terms); parent `CHEMBL190` | 212 | 27 | 22 | 3 | 24 | 6 |
| **theobromine** | ✗ | — | — | **no ATC N, and no indication record inside the considered CNS scope** | — | — | — | — | — | — |
| istradefylline | ✓ | ✓ | ✓ | ATC N (N04CX01); 3 terms | 50 | 8 | 5 | 1 | 7 | 6 |
| rolipram | ✓ | — | ✓ | core CNS indication (5 terms) | 58 | 17 | 12 | 1 | 16 | 5 |
| cilostazol | ✓ | — | ✓ | core CNS indication (7 terms) | 163 | 5 | 13 | 1 | 4 | 2 |
| donepezil | ✓ | ✓ | ✓ | ATC N (N06DA02); 24 terms | 141 | 21 | 31 | 1 | 20 | 8 |
| pentoxifylline | ✓ | — | ✓ | core CNS indication (8 terms) | 157 | 2 | 10 | 2 | 0 | 0 |
| sildenafil | ✓ | — | ✓ | core CNS indication (13 terms) | 202 | 23 | 30 | 1 | 22 | 8 |
| verapamil | ✓ | — | ✓ | core CNS indication (3 terms) | 244 | 33 | 61 | 1 | 32 | 5 |
| rivastigmine | ✓ | ✓ | ✓ | ATC N (N06DA03); 17 terms | 24 | 11 | 6 | 1 | 10 | 2 |
| tacrine | ✓ | ✓ | ✓ | ATC N (N06DA01); 2 terms | 192 | 19 | 42 | 1 | 18 | 2 |
| selegiline | ✓ | ✓ | ✓ | ATC N (N04BD01); 10 terms | 170 | 9 | 7 | 1 | 8 | 3 |
| cannabidiol | ✓ | ✓ | ✓ | ATC N (N03AX24); 43 terms | 123 | 16 | 73 | 1 | 15 | 6 |
| haloperidol | ✓ | ✓ | ✓ | ATC N (N05AD01); 16 terms | 269 | 50 | 79 | 2 | 48 | 21 |
| clozapine | ✓ | ✓ | ✓ | ATC N (N05AH02); 7 terms | 256 | 53 | 80 | 2 | 51 | 24 |
| amitriptyline | ✓ | ✓ | ✓ | ATC N (N06AA09); 6 terms | 195 | 8 | 71 | 2 | 6 | 7 |
| **loperamide** | ✗ | — | — | **indications fall only in the `general_pain` class (D010146)** | — | — | — | — | — | — |
| dextromethorphan | ✓ | ✓ | ✓ | ATC N (N07XX59); 19 terms | 170 | 5 | 25 | 2 | 3 | 3 |
| memantine | ✓ | ✓ | ✓ | ATC N (N06DX01); 32 terms | 104 | 11 | 15 | 1 | 10 | 1 |
| lamotrigine | ✓ | ✓ | ✓ | ATC N (N03AX09); 21 terms | 174 | 6 | 18 | 1 | 5 | 2 |
| dipyridamole | ✓ | — | ✓ | core CNS indication (2 terms) | 169 | 8 | 33 | 2 | 6 | 2 |
| vardenafil | ✓ | — | ✓ | core CNS indication (2 terms) | 51 | 9 | 19 | 1 | 8 | 5 |
| dronabinol | ✓ | — | ✓ | core CNS indication (20 terms) | 30 | 12 | 16 | 1 | 11 | 6 |
| phenelzine | ✓ | ✓ | ✓ | ATC N (N06AF03); 1 term | 140 | 3 | 22 | 1 | 2 | 2 |
| quinidine | ✓ | — | ✓ | core CNS indication (6 terms) | 108 | 8 | 43 | 1 | 7 | 2 |
| galantamine | ✓ | ✓ | ✓ | ATC N (N06DA04); 16 terms | 150 | 10 | 7 | 1 | 9 | 3 |
| **mibefradil** | ✗ | — | — | **indications fall only in the `cns_oncology` class (D016543)** | — | — | — | — | — | — |

Each exclusion fails for a *different, documented* reason, and each is a fair
test of a boundary decision:

- **theobromine** has neither an ATC N code nor any CNS indication in ChEMBL —
  a genuine miss. It is a methylxanthine with real ADORA pharmacology, and the
  clinical rule cannot see it. This is the clearest evidence that a
  clinical-only policy is insufficient on its own.
- **loperamide** is excluded only because general pain is outside the core
  scope. Under variant S4 it would be admitted. It has a curated μ-opioid
  agonist mechanism, and it is the only route in the current graph to
  OPRD1/OPRK1/OPRM1 — an expensive exclusion made by a boundary decision, not
  by evidence.
- **mibefradil** is excluded only by the CNS-oncology decision; under S1 it
  would be admitted. It is also the only molecule in the graph measuring
  CACNA1G/1H/1I individually.

Two of three exclusions are reversible by a single documented boundary choice.
That is worth weighing against the fact that both boundaries are defensible on
their own terms.

Note also **pentoxifylline**: in the catalogue, 157 claims, but **0**
multi-study support and **0** supported direct-human claims — its two curated
mechanisms are family-level PDE assertions. It is in the graph today drawing
13 solid edges from one curator's family-level claim.

---

## 5. Coverage gaps and limits

### Molecules retained with no evidence

**361 catalogue molecules have no assessable ChEMBL 37 evidence at any target.**
They stay in the catalogue as coverage gaps; no edge was manufactured for them.

By type: 204 small molecules, 65 Unknown, 28 Protein, 19 oligonucleotide, 17
antibody, 16 gene, plus 12 others. By route: 272 indication-only, 47 ATC-only,
42 both.

**Seven carry an Approved CNS indication but have no assessable target evidence
under these ChEMBL 37 report rules**:
`MEPHOBARBITAL`, `MEDIFOXAMINE`, `FONAZINE`, `THIOPROPAZATE`, `PHENETURIDE`,
`ACEGLUMATE`, and `GINKGO` (a botanical with no structure). Older drugs and
botanicals are systematically under-represented in a modern screening database
— the absence is about ChEMBL, not about the pharmacology.

A further **116 molecules have claims but none above Limited or unresolved.**

### What this report did not assess

| Not assessed | Consequence |
|---|---|
| PDSP, BindingDB, DGIdb | The project's supplementary sources. Their richer coverage of the existing 28 is **not** extrapolated to the other 2,217 — doing so would let familiarity masquerade as biology. |
| GtoPdb, HPA, Chemical Probes Portal, B3DB | Outside the original report and this follow-up. Check current access terms and source coverage before any integration. |
| Brain expression, BBB penetration, exposure | Kept as context, never a gate. Absence of annotation remains unknown, per invariant 10. |
| Literature beyond ChEMBL | Out of scope entirely. |

**Every "no evidence" statement means no eligible evidence under the stated
rules and source coverage.** It does not mean no published pharmacology, and
a gap under the direct-human comparison may still have other ChEMBL evidence.
The recorded molecule/source combinations are exactly: all 2,245 candidates ×
ChEMBL 37, assessed; all 2,245 × every other source, **not assessed**.

### Measured versus estimated

Baseline counts come from ChEMBL 37 and the original MeSH snapshot, with
supporting rows in `analysis/cohort1/out/` and aggregate tables in
`out/report_tables.json`. Follow-up counts and policy comparisons come from
`followup/out/`. Proposed mass conversions are conditional calculations using
an explicitly stated material assumption; they are not newly measured values.
Where a source or additional cohort was not assessed it remains unknown or
not assessed, never zero. The graph has not been benchmarked at the proposed
catalogue sizes.

### Unresolved mappings

- MeSH: **0 of 2,178** ChEMBL descriptor ids failed to resolve.
- Identity: 222 candidates have no structure (`structure_type = NONE`) and are
  marked unresolved rather than guessed at.
- Targets: 139 curated mechanism records have no target assigned; they are kept
  as Limited/unresolved with that reason, not dropped.
- 1,495 observed targets carry no ChEMBL protein-class assignment and are
  reported as `(unclassified)` rather than being forced into a family.

---

## 6. Follow-up findings and proposed import policy

**No policy is adopted or implemented by this report.** The September 12
follow-up answers the Zotero questions and measures concrete choices using
the original candidate and evidence exports. Full methods, conversion audit,
all 28 seeds under every policy, and limitations are in
[COHORT-FOLLOWUP.md](COHORT-FOLLOWUP.md) and
[`analysis/cohort1/followup/`](../analysis/cohort1/followup/README.md).

### 1. Count both admission routes explicitly

The earlier recommendation quoted **997** while also recommending retention
of both routes. That is the indication-only Approved/Phase-3 count. Keeping
whole ATC N alongside it gives **1,206** candidates, or **995 small molecules**.
An ATC-only candidate remains eligible even when its CNS phase is missing;
this does not label it CNS-approved.

| Selection | All types | Small molecules | Seeds in small-molecule set |
|---|---|---|---|
| Whole clinical catalogue | 2,245 | 1,771 | 24 |
| CNS Approved/Phase 3 only | 997 | 791 | 22 |
| ATC N + CNS Approved | 761 | 677 | 18 |
| ATC N + CNS Approved/Phase 3 | 1,206 | 995 | 22 |
| ATC N + CNS Approved/Phase 2/3 | 1,912 | 1,540 | 24 |

These use S0 core indications. All 28 seeds are tested without grandfathering.
The small-molecule definition follows the parent's source type literally.
Both theophylline records, including parent `CHEMBL190`, are typed `Protein`
in ChEMBL 37. That source anomaly costs theophylline under a literal
small-molecule filter even before considering its Phase-1 CNS indication.
It needs an explicit identity correction, not a silent exception.

### 2. Separate catalogue membership from drawable evidence

The following uses the **original baseline evidence**, keeping supported
human single proteins, precise complexes, families and complex groups at
their native ChEMBL target level. Experimental support is recalculated only
from direct human assignments within each accepted type; mutants and
homologous assignments do not contribute. Curated support retains its own
route and is not experimental replication.

"Usable" means at least one Supported or Preliminary claim. A pair is a
molecule-target pair, which may have several role-specific claims. Targets
are ChEMBL target records, not counts of expanded component proteins.

| Small-molecule selection | Supported molecules | Supported pairs | Targets with support | Usable molecules | No qualifying edge |
|---|---|---|---|---|---|
| Whole clinical catalogue | 1,137 | 3,074 | 795 | 1,310 | 461 |
| CNS Approved/Phase 3 only | 607 | 1,528 | 426 | 665 | 126 |
| ATC N + CNS Approved | 448 | 1,145 | 264 | 481 | 196 |
| ATC N + CNS Approved/Phase 3 | 666 | 1,653 | 431 | 738 | 257 |
| ATC N + CNS Approved/Phase 2/3 | 1,013 | 2,738 | 749 | 1,152 | 388 |

For the same 995 candidates, target granularity changes what can be shown:

| Evidence basis for the same 995 candidates | Supported claims | Supported molecules | Usable molecules |
|---|---|---|---|
| Human single proteins | 1,719 | 532 | 641 |
| + precise protein complexes | 1,804 | 557 | 663 |
| + families and complex groups | 2,049 | 666 | 738 |

My proposed starting catalogue is **ATC N plus CNS Approved/Phase 3, small
molecules first**. Keep all 995 catalogue entries. Its broad human-specific
evidence view reaches **666 molecules with Supported evidence**
and **738 with Supported or Preliminary evidence**;
the other **257 remain visible as coverage gaps** for this basis.
Those are not necessarily gaps in all ChEMBL evidence.

Families and complexes need their own target nodes or rows. Their evidence
must not be distributed to subunits or counted as several independent shared
targets. Show Supported claims initially, offer Preliminary and other-species
evidence as explicit layers, and keep curated versus multi-study support
visible. Clinical membership does not certify a CNS mechanism for every edge.

This candidate set carries **63 family withdrawal flags** and
**12 records without a structure**. Preserve those annotations;
"clinical catalogue" does not mean currently available or uniformly resolved.

### 3. Treat the Phase-2 expansion as a real tradeoff

Moving from Approved/Phase 3 to Approved/Phase 2/3 while keeping ATC N adds
**545 small molecules**, **347 molecules with Supported
evidence**, and **318 targets with support** under the broad human-specific
basis above. It also retains rolipram and pentoxifylline, which the Phase-3
choice loses. The original claim that this necessarily adds thinner evidence
was not established by its stage counts and is withdrawn. The choice is
between a tighter clinical-stage scope and substantially wider target coverage.

### 4. Preserve excluded evidence before broadening numerical rules

The unit audit compares explicit concentration conversions with a conditional
scenario that also uses the measured compound record's full molecular weight.
The scenarios are alternatives; their counts must not be added together.

| Recovery scenario | Assignment basis | Added measurements | New Preliminary claims | New Supported claims |
|---|---|---|---|---|
| Concentration conversions | All assignments | 30 | 18 | 1 |
| Concentration conversions | Direct human single protein | 6 | 1 | 1 |
| Including conditional mass conversions | All assignments | 2,364 | 243 | 106 |
| Including conditional mass conversions | Direct human single protein | 35 | 7 | 1 |

The direct-human upgrade from explicit concentration conversion is
**phenelzine-MAO-A binding**; imipramine-BRD4 binding gains a Preliminary claim.
The latter's converted values are 647 and 1,020 micromolar, demonstrating why
an exact value and evidence tier do not imply useful potency or exposure.
Conversion does not independently validate upstream units or target species.

The 2,334 mass-concentration proposals remain conditional until the original
material basis is checked. Another 350 non-nM rows remain unrecovered.
No existing coverage-gap molecule gains its first assessed claim through
either conversion scenario. In the proposed 995-molecule catalogue, explicit
concentration recovery adds one Supported claim without adding another
molecule with qualifying evidence.

All **21,999 organism-format exclusions** are now available in a context
inventory. All **36 protein-assigned records**, spanning 22 assays, have been
reviewed from their descriptions. **31** have positive exact nM values, but
their contexts include occupancy, downstream physiology, cell assays with
conflicting format metadata, and microorganism screens. Keeping this context
causes **zero changes to the baseline biochemical tiers**. Blindly pooling
the 31 values would produce 18 new Preliminary and
2 new Supported claims under the old counting rule; that is a diagnostic
of the risk, not a recommended evidence upgrade.

### 5. Keep scope extensions separate from evidence claims

Core plus CNS oncology plus general pain gives **2,523 molecules (+278)**,
not the earlier 2,445 figure, which counted core plus pain alone. The widest
variant is 2,611 (+366). Neither delta is a count of useful new graph edges:
evidence for molecules added outside the original 2,245 was not assessed.
The corrected scope counts alone do not justify adopting either extension.

A clinical-only catalogue still misses theobromine and other nonclinical
ligands. A future curated-ligand route remains a separate candidate analysis,
with explicit eligibility and identity rules; its coverage is not measured
or assumed here. Loperamide and mibefradil should be judged by those explicit
routes or a documented scope choice, not simply because they are old seeds.

### 6. Build the viewer around selected neighbourhoods

The table measures candidates, claims, pairs and targets; it does not benchmark
rendering performance. A graph need not draw every catalogue item at once.
Searchable membership, target-level identity, selectable neighbourhoods and
clear evidence filters should precede a production import. The original
2,245-by-4,885 product was not an observed edge count and did not establish
that a particular graph implementation was impossible to render.

---

## 7. Validation

The ten original baseline checks pass (`analysis/cohort1/out/validation.csv`).
The follow-up adds eight data validations, including reproduction of baseline
tiers and unchanged production fingerprints. The combined unit suite passes
**29 tests**: 16 original and 13 follow-up tests. These checks validate the
implemented rules and accounting; they do not certify every upstream assay
assignment or the biological interpretation of a threshold.

| # | Check | Result |
|---|---|---|
| 1 | Baseline reproduction — 521 / 361 / 15 | **PASS**, exactly |
| 2 | Parent/salt deduplication — 2,245 distinct parents, 1,423 forms folded in, `CHEMBL1355736` → `CHEMBL190` as one row | **PASS** |
| 3 | Admission-route union arithmetic across 13 stages | **PASS**, 0 violations |
| 4 | Unrelated-indication approval — 1,147 family-Approved vs 506 CNS-Approved, 591 divergent, never merged | **PASS** |
| 5 | Missing study provenance — 0 claims reached Supported without ≥ 2 publication-class studies | **PASS** |
| 6 | Multiple measurements from one paper — `CHEMBL14` vs `CHEMBL320`, 20 Ki measurements across 20 assays in one document, recorded as **1** study | **PASS** |
| 7 | Cross-source duplicates — 10 PubMed ids carried by more than one ChEMBL doc record collapse to one study; 74,691 of 106,380 links are PubMed-keyed | **PASS** |
| 8 | One family claim vs many subtype claims — 477 stay 477, not 3,146 | **PASS** |
| 9 | Report totals match the exported records — 7 cross-totals | **PASS**, 0 mismatches |
| 10 | Production artifacts unchanged | **PASS** |

On check 10: `git status` reports no modification to `db/schema.sql`,
`scripts/build_db.py`, `scripts/chembl_local.py`, `scripts/export_graph.py` or
`viz/index.html`. `db/subnetwork.db` (1,437,696 bytes) and `viz/graph.data.js`
(2,330,003 bytes) both retain their pre-existing mtimes; no rebuild was run and
both were opened read-only, as was the 30.5 GB ChEMBL release.

---

## 8. Files

Schemas, join keys and per-file row counts:
[`analysis/cohort1/README.md`](../analysis/cohort1/README.md).

| | |
|---|---|
| Rules (versioned) | `analysis/cohort1/config/cns_indication_scope.json`, `config/tier_rules.json` |
| Scripts | `analysis/cohort1/scripts/step1…step5`, `run_all.sh` |
| Source manifest | `analysis/cohort1/MANIFEST.json` — URLs, retrieval dates, checksums, access status, licences |
| Catalogue | `out/candidates.csv`, `candidate_atc_codes.csv`, `candidate_indications.csv`, `family_members.csv`, `indication_scope.csv`, `route_arithmetic.csv`, `stage_breakdown.csv` |
| Evidence | `out/assessed_claims.csv.gz`, `target_pairs.csv.gz`, `claim_studies.csv.gz`, `claim_thresholds.csv.gz`, `measurements.csv.gz`, `molecule_evidence.csv`, `observed_targets.csv`, `family_coverage.csv`, `tier_distribution.csv`, `threshold_sensitivity.csv` |
| Gaps and exclusions | `out/coverage_gaps.csv`, `evidence_exclusions.csv` |
| The 28 | `out/seed_membership.csv`, `seed_report.csv` |
| Baseline aggregates | `out/report_tables.json` |
| Follow-up | `followup/out/summary.json`, `followup/out/policy_comparison.csv`, `followup/out/unit_recovery_summary.csv`, `followup/out/organism_reviewed.csv` |
| Validation | `out/validation.csv`, `followup/out/validation.csv`, `tests/test_cohort_report.py`, `tests/test_cohort_followup.py` |

**Sources.** ChEMBL 37 bulk release
(`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db`, 30,480,314,368
bytes, CC BY-SA 3.0, read-only) and MeSH tree numbers from the NLM MeSH SPARQL
endpoint (current-year graph, retrieved 2026-09-07, public domain,
original `cache/mesh_tree.tsv` sha256 `dc8f2681…`). The original run recorded
no fetch failures. Those raw MeSH cache files are now absent; their exported
descriptor classification remains available and is the follow-up's scope
input. Follow-up input hashes, rules and validations are recorded separately
in `analysis/cohort1/followup/out/summary.json`.
