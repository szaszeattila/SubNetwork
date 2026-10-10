# Cohort 1 — the clinical catalogue, measured

What a clinical-only selection rule actually produces against ChEMBL 37, and
how well evidenced the molecule–target claims inside it are.

**This report chooses nothing.** It measures the consequences of the clinical
option in
[docs/MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md) so a
selection policy can be chosen with numbers in hand. Nothing here changes the
seed list, the schema, the database, the graph export or the viewer, and the
tiers below are **report definitions, not production trust rules** — the
invariants in [the project guide](../CLAUDE.md) are untouched.

Cohorts 2 (curated ligands) and 3 (broad experimental) are deferred and not
compared here.

Everything is reproducible from
[`analysis/cohort1/`](../analysis/cohort1/README.md):
`bash analysis/cohort1/scripts/run_all.sh`.

---

## The headline

A clinical-only rule — ATC N **or** an in-scope CNS indication, deduplicated to
chemical parents — admits **2,245 molecules** from ChEMBL 37, of which
**1,771 are small molecules**. That is **80× the current 28-molecule seed set**,
and it reaches **4,885 distinct targets** (3,750 UniProt accessions) against
the graph's present 207.

The evidence behind it is thinner than the size suggests, and thins further
the more carefully the target assignment is read:

| | Claims | Molecules |
|---|---:|---:|
| Molecule–target claims assessed | 138,509 | 2,245 |
| **Supported** | 9,014 (6.5%) | 1,555 |
| **Preliminary** | 38,506 (27.8%) | — |
| **Limited or unresolved** | 90,989 (65.7%) | — |
| Supported on **direct human single-protein** evidence only | 3,442 (2.5%) | 1,125 |
| No eligible evidence found in ChEMBL 37 at all | — | 361 |

Three findings drive every recommendation at the end:

1. **Two thirds of all claims are Limited or unresolved, and 59,327 of them —
   43% of every claim in the report — exist only as censored bounds.** These are
   "no activity detected up to this concentration" records. Counting them as
   evidence would have been the single largest error available here, and it is
   the same failure [invariant 1](../CLAUDE.md#invariants) already exists to
   prevent, at 100× the scale the production pipeline has ever faced.
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

ATC N is taken **whole**, so the baseline reproduces exactly. Two subtrees the
prompt names as boundaries are *flagged in the output rather than removed*:

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
member, names a MeSH descriptor inside a versioned scope.

The scope is defined on **MeSH tree numbers**, resolved by exact descriptor id
against the NLM MeSH SPARQL endpoint — never by heading text. This is
[invariant 15](../CLAUDE.md#invariants) applied to an ontology: a name search
answers confidently and wrongly. All **2,178** distinct `mesh_id` values in
ChEMBL 37's `drug_indication` resolved; **zero** were unresolvable.

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

### Baseline reproduction (ChEMBL 37)

The brainstorming document's query reproduces **exactly**, inside this
pipeline, before any new filter is introduced:

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

Identity is normalised to the ChEMBL parent `molregno`, collapsing salts and
hydrates onto one chemical identity while every contributing family member is
kept in `out/family_members.csv`. Nothing is matched on a name.

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

| Excluded / retained | Activity rows | Kept in output? |
|---|---:|---|
| Assay type not B or F | 483,915 | no |
| Standard type out of scope | 321,727 | no |
| **Censored bound** (`>`, `<`, …) | **81,867** | **yes, as a bound** |
| Null value | 102,708 | no |
| Organism-based format (whole-organism readout) | 21,999 | no |
| Other relation | 5,903 | no |
| Units not nM | 2,714 | no |
| Non-positive value | 8 | no |
| **Documented known-bad records** | **4** | **yes, flagged** |

The last row is the project's own `CHEMBL_ASSAY_LINK_EXCLUSIONS`
(`CHEMBL5133661`, `CHEMBL1074487`), reused verbatim and applied on this path
too — never a silent drop. ChEMBL's `data_validity_comment` and
`potential_duplicate` flags are **recorded per measurement and reported, not
used to drop rows**, matching how the production pipeline stores them.

### Claim granularity

A claim is `(molecule parent, target, role)` where role is `curated`,
`binding` or `functional`. Endpoint types (Ki, Kd, binding IC50, functional
IC50, EC50, AC50, Kb) are separate classes and are **never pooled**;
replication is only ever counted inside one class. Two binding studies do not
establish agonism. A well-evidenced target does not upgrade any other claim
for the same molecule.

### Tier distribution

| Role | Supported | Preliminary | Limited/unresolved |
|---|---:|---:|---:|
| curated | 1,859 | — | 140 |
| binding | 4,441 | 11,753 | 70,804 |
| functional | 2,714 | 26,753 | 20,045 |
| **All** | **9,014** | **38,506** | **90,989** |

Restricted to **direct human single-protein** evidence — the main empirical
comparison, and the only basis on which a claim about a named human protein is
really being made:

| Role | Supported | Preliminary | Not applicable |
|---|---:|---:|---:|
| curated | 1,195 | — | 804 |
| binding | 1,980 | 4,116 | 80,902 |
| functional | 267 | 683 | 48,562 |
| **All** | **3,442** | **4,799** | **130,268** |

Supported drops from 9,014 to 3,442 — **62% of Supported claims lose that
status once homologous, nonhuman and unassigned evidence is set aside.** Both
columns are reported; neither replaces the other.

### Why so much is Limited or unresolved

| Reason | Claims |
|---|---:|
| `censored_only` — every measurement is a bound | **59,327** |
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
not a quality ranking. **A generic `>= 7` filter would have merged all three
and swept 78,928 homologous claims into the human comparison.** This report
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

**4,885 distinct targets**, 3,750 UniProt accessions, 1,676 of them human
single proteins. Against the current graph: **206 of the present 207 targets
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

**Seven are approved for a CNS indication and have no target evidence at all**:
`MEPHOBARBITAL`, `MEDIFOXAMINE`, `FONAZINE`, `THIOPROPAZATE`, `PHENETURIDE`,
`ACEGLUMATE`, and `GINKGO` (a botanical with no structure). Older drugs and
botanicals are systematically under-represented in a modern screening database
— the absence is about ChEMBL, not about the pharmacology.

A further **116 molecules have claims but none above Limited or unresolved.**

### What this report did not assess

| Not assessed | Consequence |
|---|---|
| PDSP, BindingDB, DGIdb | The project's supplementary sources. Their richer coverage of the existing 28 is **not** extrapolated to the other 2,217 — doing so would let familiarity masquerade as biology. |
| GtoPdb, HPA, Chemical Probes Portal, B3DB | Deferred by the prompt. GtoPdb additionally introduced registration in August 2026 and announced API keys for ~15–17 September 2026; check access terms before implementing. |
| Brain expression, BBB penetration, exposure | Kept as context, never a gate. Absence of annotation remains unknown, per invariant 10. |
| Literature beyond ChEMBL | Out of scope entirely. |

**Every "no evidence" statement in this report means "none in ChEMBL 37".**
The recorded molecule/source combinations are exactly: all 2,245 candidates ×
ChEMBL 37, assessed; all 2,245 × every other source, **not assessed**.

### Measured versus estimated

**Every number in this report is measured** — counted from ChEMBL 37 and the
cached MeSH snapshot, and traceable to a row in `analysis/cohort1/out/`. There
are no estimates, no extrapolations and no projections. Where something could
not be determined it is reported as unknown or not assessed, never as zero.
`out/report_tables.json` holds every quoted number under the key it is quoted
by.

### Unresolved mappings

- MeSH: **0 of 2,178** ChEMBL descriptor ids failed to resolve.
- Identity: 222 candidates have no structure (`structure_type = NONE`) and are
  marked unresolved rather than guessed at.
- Targets: 139 curated mechanism records have no target assigned; they are kept
  as Limited/unresolved with that reason, not dropped.
- 1,495 observed targets carry no ChEMBL protein-class assignment and are
  reported as `(unclassified)` rather than being forced into a family.

---

## 6. Recommendation for the next import policy

**This task does not adopt or implement a policy.** What the measurements
support:

### 1. Do not adopt cohort 1 alone

Theobromine settles it. A molecule with real, measured ADORA pharmacology,
already in the graph and load-bearing for its central cluster, is invisible to
every clinical rule tested — it has no ATC N code and no CNS indication in
ChEMBL. Rolipram survives only because someone registered a CNS indication for
a compound that is, in practice, a research tool. A clinical catalogue is a
good *spine*; it is not a sufficient definition of brain pharmacology. The
brainstorming document's combined recommendation is supported by this
measurement, with cohort 1 as the spine and a curated-ligand cohort filling
exactly this gap.

### 2. Take both admission routes, and keep them labelled

An ATC-only rule loses 1,701 of 2,245 molecules; an indication-only rule loses
136. Neither is close to sufficient. Keep `route_atc_n` and
`route_cns_indication` as separate stored columns and never collapse them,
because they support different claims: ATC says "classified as a nervous-system
drug", the indication route says "developed to phase *n* for this specific CNS
condition". The 591 molecules approved elsewhere but sub-phase-4 for CNS are
the concrete reason.

### 3. Start at approved-plus-Phase-3 on the indication-specific phase

997 molecules — a ~36× expansion on today's 28, large enough to change the
graph and small enough to inspect. Approved-plus-Phase-2 (1,766) roughly
doubles the set for molecules whose evidence is measurably thinner. Use
`max_phase_for_ind` on the qualifying CNS indication, **never** the molecule's
max phase.

Concretely, the cost of the stricter setting is measurable on molecules
already in the graph. Approved-only (506) would drop **five of the current 28
seeds** — cilostazol, dextromethorphan, dronabinol, quinidine and verapamil
all sit at Phase 3 for their qualifying CNS indication while being Approved at
molecule level. Approved-plus-Phase-3 keeps all five, retaining 22 of the 25
qualifying seeds; the three it still drops are theophylline (Phase 1 for its
CNS indication), rolipram and pentoxifylline (Phase 2). That is the clearest
available demonstration that molecule-level phase and indication-level phase
must not be conflated: read off the wrong column, all five of those Phase 3
molecules look approved.

### 4. Keep the core scope; revisit CNS oncology and general pain by hand

The three excluded classes cost 2 of 28 existing seeds, and both losses trace
to a single boundary decision. Two options, and the report supports either:

- Keep S0 core and add back specific molecules by an explicit, recorded
  exception — the mechanism the data-quality log already uses for
  `CHEMBL190`-style cases, and the reason `dipyridamole`'s earlier exclusion
  could be reversed cleanly.
- Adopt S1+S4 (core + oncology + pain, 2,445 molecules, +200) and accept
  NSAIDs and alkylating agents in the catalogue, filtered at display time.

The first is preferable. It costs 366 molecules of breadth and buys a
catalogue whose membership claim stays true, and the current viewer has no
filter UI to hide the difference.

### 5. Store the tier, the route, and the specificity — not a single badge

The 538-of-7,997 overlap between curated and replicated support is the finding
with the most direct consequence for the viewer. A single "corroborated" flag
would merge one curator's assertion with two independent papers, and merge a
human single-protein measurement with a rat homologue. Persist three
orthogonal fields: `tier`, `support_route` (curated / multi-study / both), and
`assignment_specificity`. The edge panel already distinguishes curated from
corroborated; this extends the same honesty to species and assignment.

### 6. Do not import censored measurements, and expect to say so loudly

59,327 of 138,509 claims exist only as bounds. At the current scale the
production pipeline drops these silently and correctly. At 2,245 molecules,
"this molecule was tested at this target and nothing was detected" is a large
and genuinely informative body of data — and rendering it as an absent edge
loses it entirely. Recommendation: keep excluding bounds from values and
`n_measurements`, but consider storing them as an explicit "tested, no
activity detected" annotation. That is a design question this report does not
answer.

### 7. Budget for the graph, not just the catalogue

2,245 molecules × 4,885 targets is not renderable. The catalogue and the
display must be separated before any import — as the brainstorming document
proposes, and as the missing filter UI makes urgent. A 997-molecule
approved-plus-Phase-3 import against the ~2,090 targets carrying any supported
pair is the smallest version of this that is still worth building.

---

## 7. Validation

All ten checks pass (`analysis/cohort1/out/validation.csv`), plus 16 unit tests
for the analysis logic (`tests/test_cohort_report.py`).

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
| Every quoted number | `out/report_tables.json` |
| Validation | `out/validation.csv`, `tests/test_cohort_report.py` |

**Sources.** ChEMBL 37 bulk release
(`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db`, 30,480,314,368
bytes, CC BY-SA 3.0, read-only) and MeSH tree numbers from the NLM MeSH SPARQL
endpoint (current-year graph, retrieved 2026-09-07, public domain,
`cache/mesh_tree.tsv` sha256 `dc8f2681…`). No fetch failed; nothing is missing
for a reason this report could not record.
