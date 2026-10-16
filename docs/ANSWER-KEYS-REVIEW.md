# The answer keys against the literature, and what they can decide

Written 2026-10-16 against the active build of 2026-10-13 (2,452 entries).
**A review and a proposal; nothing in it is adopted, and no key, constant or
page behaviour was changed.** Every measurement is reproduced by a read-only
script under `analysis/answer_keys/`, named where it is used.

[SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md) (2026-10-13) asked what
the literature says about the *score*, and proposed four better keys. All
four were built by 2026-10-14 ([SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md)
§13–16; explained in [ANSWER-KEYS-PRIMER.md](ANSWER-KEYS-PRIMER.md)). This
document turns the same question on the *keys*. They are about to be used to
decide changes to the score, so it asks: what does the literature on reference
standards say about keys of each kind, and can these keys actually decide the
changes they will be asked to decide?

In short:

- **The keys cannot see the changes the sweep reports.** Compared paired,
  question by question, the smallest change a key can detect is 0.011 MRR
  (MeSH) to 0.021 (repaired ATC). The changes §15 of the harness sorts into
  "agreed by every judge", "agreed only by the curated judges" and "split"
  are mostly +0.002 to +0.009. Under a paired test with Holm's correction
  across the 42 key-by-setting cells, **only switching D15 off is detected
  under every key.** Raising the family weight to 1.0 is detected under MeSH
  alone. The other four settings are within every key's noise, including the
  curated-only gain and the replicated-only split that §15 reads as a finding.
  To detect a +0.004 change at 80% power would need 4,500 to 7,000
  questions depending on the key; the catalogue has 2,452 molecules (§2).
- **The label key is noisier than the ranking it grades.** Build it twice,
  once from US labels and once from UK, EU and Japanese labels, and the two
  share 14% of their five nearest neighbours. The target ranking predicts each
  half's neighbours *better* than the other half does (§3.4). This fits the
  literature: a US and an EU label for the same CNS drug share 29% of their
  adverse-reaction terms (Cornelius 2016).
- **The label key's agreement with the ranking runs through shared
  indication.** Label neighbours share an approved indication 42% of the time,
  random pairs 8%. Rebuilt so that a neighbour must be approved for a
  different disease, the key agrees with the ranking at top-1 1.6% against a
  shuffle's 0.8% (§3.4). It is independent of the score's inputs, but not of
  what the drugs are for.
- **Most of the pairwise key's negatives cannot fail.** 96 of the 160
  negative directions share no target, so they are absent from both lists and
  clean by construction. 110 of the 116 positives are already classmates under
  the repaired ATC, EPC or MeSH key (§3.5). Its value is the opposites (all 94
  directions reachable) and the 64 negative directions that could fail.
- **The class keys are incomplete by construction, which the literature
  measures.** FDA's asserted class memberships match those inferable from its
  own drug descriptions about half the time (Winnenburg 2015), and ATC is
  extended only on request (Liu 2015). A miss under a class key is often a
  missing label, which supports reading the filtered grade first (§3.1–3.3).
- **Proposed order (§6):** fix the decision rule before the next constant is
  moved (no new data); a pairwise key v2 with negatives that can fail and a
  second, independent drafter; a label key v2 that requires agreement across
  regulators and removes a drug's own indication symptoms; then pilots of
  brain-specific keys. None of the brain-specific keys the literature offers is
  ready to build at catalogue scale (§5).

---

## 1. What a key has to do now

SIMILARITY-LITERATURE §4.1 listed six properties for a key: it asks the page's
question, states its provenance, judges only what it can judge, grades with
negatives, comes as several judges with one held out, and is fixed before use.
The keys as built meet most of them. Using them to decide changes to the
score adds four more, each from a literature that has faced the same problem:

| property | why | from |
| --- | --- | --- |
| **It resolves the effect sizes at issue.** A grade's sampling noise must be smaller than the change being judged, tested on paired per-question differences, with the number of settings tried counted. | Information retrieval compares two systems over one question set the same way, and found that many reported gains do not survive a paired test. | Smucker, Allan & Carterette 2007; Sakai 2016; Carterette 2012 |
| **Its own reliability is known.** A key that disagrees with a second measurement of itself caps the grade any ranking can reach. | The "noise ceiling" of representational similarity analysis. | Nili et al. 2014 |
| **Its negatives can fail.** A negative control the method cannot get wrong adds nothing to a rate but its denominator, and negatives are where reference sets are most often misclassified. | Drug-safety reference sets with positive and negative controls. | Ryan et al. 2013; Coloma et al. 2013; Hauben et al. 2016 |
| **What it shares with the predictor is measured, not only stated.** | Circularity inflated the evaluation of variant-effect predictors, and redundancy between benchmark and training data explained most of the performance of ligand-based classifiers. | Grimm et al. 2015; Wallach & Heifets 2018 |

The rest of this document checks each key against these properties.

---

## 2. Can the keys see the changes? (`power.mjs`)

`node analysis/answer_keys/power.mjs` takes the six settings in
SIMILARITY-HARNESS §15 and, for each key, compares every question's
reciprocal rank before and after. It reports a paired bootstrap interval on
the MRR change. For the class keys it adds a second bootstrap that resamples
whole classes, since one constant moves a class's members together. Then come
a sign-flip randomisation test, and Holm's correction across all 42 cells. A
cell counts below as **detected** when it survives Holm.

**How precisely each grade is known.** These are baseline MRRs with a 95%
bootstrap interval over questions:

| key | questions | MRR | 95% interval |
| --- | --- | --- | --- |
| ATC (headline) | 284 | 0.4607 | 0.414 – 0.508 |
| ATC repaired | 259 | 0.4958 | 0.447 – 0.546 |
| MeSH | 865 | 0.5945 | 0.569 – 0.620 |
| EPC | 455 | 0.5946 | 0.559 – 0.631 |
| PE | 598 | 0.5154 | 0.483 – 0.548 |
| label, nervous system | 346 | 0.2620 | 0.227 – 0.298 |
| label, every effect | 507 | 0.3180 | 0.287 – 0.351 |

**What each setting does, under seven keys.** The full table, with intervals
and the count of questions moved each way, is the script's output.

| setting | MRR change across the seven keys | keys whose interval excludes zero | detected (Holm) |
| --- | --- | --- | --- |
| D15 off (`OPPOSED_PAIR_FACTOR` 1.0) | −0.015 to −0.034 | 7 | **7** |
| family weight 0.5 → 1.0 | +0.002 to +0.018 | 4 (MeSH, EPC, PE, label every effect) | 1 (MeSH) |
| curated-only 0.75 → 1.0 | +0.002 to +0.009 | 1 (MeSH) | 0 |
| replicated-only 0.9 → 0.75 | −0.004 to +0.008 | 1 (MeSH) | 0 |
| Preliminary 0.5 → 0.25 | −0.013 to +0.011 | 0 | 0 |
| `SPECIES_EXPONENT` 0.5 → 0.75 | +0.000 to +0.008 | 0 | 0 |

Resampling whole classes widens most class-key intervals, by up to 80% for
D15 under ATC, since one change moves a class together. Of the 30 class-key
cells, 10 still exclude zero under it, against 13 of all 42 cells at the
question level.

**What this changes in §15's reading.** §15 sorted the constants into three
kinds by the sign of their change under five judges:

- **"Agreed by every judge."** D15 holds: it is the one finding every key
  resolves. The other three are not shown by these keys to do anything, though
  §15 reads them as small agreed gains. The curated-only gain is the case that
  matters, because §15 and CLAUDE.md read it as answering the old caveat that
  the judge flattered curation. Under the label key it is +0.0058, interval
  −0.004 to +0.017.
- **"Agreed only by the curated judges."** The replicated-only change helps
  under ATC and MeSH and "hurts" under both label readings, and §15 calls
  this "the pattern the label key was built to catch". The label key's
  intervals are −0.012 to +0.003 and −0.010 to +0.002. It has not caught
  anything yet: it cannot tell −0.004 from zero.
- **"Split."** The Preliminary weight is as noisy as the sweep has: 37 to 140
  questions move each way under every key.

**How large a change can be seen.** The baseline intervals above say how
well a grade is known in absolute terms, which matters when comparing builds.
Two settings on one build are compared paired, which is tighter. Under the
five small settings, a question's reciprocal rank changes with a standard
deviation of about 0.10 to 0.12. A paired test at 5% with 80% power then
detects a change of 2.8 × sd / √n, and needs 7.84 × (sd / δ)² questions to
detect a change of δ (Sakai's topic-set-size design, with this project's
measured spread; `power.mjs` prints both):

| key | questions | smallest detectable change | questions needed for 0.004 |
| --- | --- | --- | --- |
| ATC (headline) | 284 | 0.019 | 6,374 |
| ATC repaired | 259 | 0.021 | 6,987 |
| MeSH | 865 | 0.011 | 6,682 |
| EPC | 455 | 0.015 | 6,638 |
| PE | 598 | 0.013 | 6,483 |
| label, nervous system | 346 | 0.014 | 4,512 |
| label, every effect | 507 | 0.013 | 5,123 |

A change of 0.004 cannot be resolved by any per-question key on a
2,452-molecule catalogue, however well built. **The keys can arbitrate changes
of roughly 0.01 to 0.02 MRR and above, depending on the key. Below that the
sweep reports signs, not findings.**

Voorhees 2000 is the reassurance: different assessors' relevance judgements
vary widely, yet rank retrieval systems alike. A noisy key still orders
formulas whose difference is large. What it cannot do is order formulas whose
difference is small, which is where every constant except D15 sits.

---

## 3. Each key against the literature

Every reference below resolves on Crossref with its title and first author
matching (checked 2026-10-16). "Abstract" marks a paper read through its
abstract only. "Summary" marks one whose figure comes from a subagent's
reading of the full text, which was not checked here.

### 3.1 ATC, as the headline and repaired

| paper | finding | bearing |
| --- | --- | --- |
| Winnenburg & Bodenreider 2014, [*A framework for assessing the consistency of drug classes across sources*](https://doi.org/10.1186/2041-1480-5-30), J Biomed Semantics | Aligning MeSH 2013 with ATC levels 2–4 over 1,685 shared drugs: lexical alignment found 226 equivalent classes and drug-set alignment 223, with only 36 in common; 313 inconsistencies. Same-named classes are often inclusions, not equivalents (summary). | Explains the asymmetric agreement `agreement.mjs` measures (MeSH accepts 79% of ATC's pairs, ATC 19% of MeSH's). Never merge keys by class name. |
| Liu et al. 2015, [*Similarity-based prediction for ATC classification of drugs by integrating multiple data sources*](https://doi.org/10.1093/bioinformatics/btv055), Bioinformatics | New drugs enter ATC only when someone asks WHO, so coverage is "seriously incomplete" (abstract). | An unclassed molecule is unknown, not unlike: for the filtered reading. |
| Yıldırım et al. 2007, [*Drug–target network*](https://doi.org/10.1038/nbt1338), Nat Biotechnol | Drugs of one ATC type cluster in the drug–target network; follow-on drugs pile onto proteins already targeted (abstract). | For ATC as a target-sharing benchmark, and a reason target sharing partly measures the market. |
| Mougin, Burgun & Bodenreider 2012, [*Comparing drug-class membership in ATC and NDF-RT*](https://doi.org/10.1145/2110363.2110413) | Lexical mapping aligned about half of ATC's terms; mapping cardiovascular classes by hand raised common pairs from 39 to 128 (abstract). | Agreement between ATC and FDA's classes depends on how they are mapped; `agreement.mjs` compares classmate pairs over shared molecules, the safe way. |

**Measured here.** In this catalogue, **95.1% of repaired-ATC classmate pairs
share an approved indication** (`confounding.mjs`; random pairs 7.7%).
SIMILARITY-LITERATURE §3.5 classed 4 of the 64 level-4 classes as use
classes. By what its members are approved for, nearly all of them behave like
use classes. The repaired key is therefore as much a "same indication" key as
the label key is, and more so. And one class can decide the grade: the five
largest classes hold a quarter of the questions. Averaged over classes rather
than questions, MRR falls from 0.4607 to 0.4148 (`difficulty.mjs`).

**What the literature does not give.** No paper tests information-content
similarity over the ATC tree (Resnik, Lin; reviewed by
[Pesquita et al. 2009](https://doi.org/10.1371/journal.pcbi.1000443)) as
graded relevance against any standard. Replacing the repaired key's flat half
credit with such a weight is plausible, untested anywhere, and would change
the instrument.

### 3.2 MeSH pharmacological actions

No published audit of MeSH pharmacological-action indexing was found, for
completeness or for errors. Winnenburg & Bodenreider 2014 cite missing action
links as one cause of MeSH–ATC misalignment. This project's own audit is the
D22 work in [MESH-ACTIONS-ROUTE-B.md](MESH-ACTIONS-ROUTE-B.md), and
the *Gestormone* error in CLAUDE.md is an NLM indexing error it found.

**Measured here.** MeSH is the most powerful key: 865 questions, the
narrowest interval, and the only key under which the family weight is
detected. It is powerful because its classes are broad: it accepts 79% of
ATC's classmate pairs, and 157 classes hold its 865 questions. Breadth buys
power and costs fidelity, so the one change only MeSH detects is the one to
distrust most. Its MRR falls from 0.5945 to 0.5214 when averaged over
classes, the largest drop of any key.

### 3.3 FDA's classes (EPC, MoA, PE)

| paper | finding | bearing |
| --- | --- | --- |
| Winnenburg, Mortensen & Bodenreider 2015, [*Using description logics to evaluate the consistency of drug-class membership relations in NDF-RT*](https://doi.org/10.1186/s13326-015-0007-3), J Biomed Semantics | The drug-class relations FDA's labels assert and those a reasoner infers from NDF-RT's own drug descriptions "only match in about 50% of the cases" (abstract); 660 of 1,308 drugs have identical class sets (summary). | A true classmate under EPC is often unlabelled as one. Read EPC's filtered grade first. |
| Pathak & Chute 2010, [*Analyzing categorical information in two publicly available drug terminologies: RxNorm and NDF-RT*](https://doi.org/10.1136/jamia.2009.001289), JAMIA | About 54% of RxNorm clinical drugs have no NDF-RT counterpart; 42% of MoA classes and 75% of PE classes have no RxNorm drug under them (abstract, as relayed). | Fits the coverage the primer reports (909 molecules whose UNII RxNorm does not know). MoA and PE are sparse by construction. |
| Nelson et al. 2017, [*Interoperability of medication classification systems: lessons learned mapping EPCs to SNOMED CT*](https://doi.org/10.3233/978-1-61499-830-3-920) | Of 543 EPCs, 284 map to an equivalent SNOMED CT class, 205 are more specific and 54 do not map (abstract, as relayed). | EPC's granularity is its own; no other vocabulary stands in for it. |

**Measured here.** 75.3% of EPC classmate pairs share an approved indication.
EPC detects a paired change of about 0.015 (§2).

### 3.4 The label key (OnSIDES)

| paper | finding | bearing |
| --- | --- | --- |
| Cornelius et al. 2016, [*Variation in adverse drug reactions listed in product information for antidepressants and anticonvulsants, between the USA and Europe*](https://doi.org/10.1136/bmjopen-2015-010599), BMJ Open | Twelve CNS brand drugs, each with a US and an EU document from the same company: median 201 against 114 adverse reactions, and "only 29% of ADR terms were reported in both paired documents" (abstract). | The key pools labels across regulators; the regulators largely disagree. |
| Duke, Friedlin & Ryan 2011, [*A quantitative analysis of adverse events and "overwarning" in drug labeling*](https://doi.org/10.1001/archinternmed.2011.182), Arch Intern Med | 5,602 US labels list a median of 49 and a mean of about 70 distinct adverse events, up to 525 (as relayed; no abstract on PubMed). | Label length is a property of the label as much as of the drug, so profile richness is partly noise. The key's agreement rising with richness (19% to 37%) is what this predicts. |
| Brouwers et al. 2011, [*Network neighbors of drug targets contribute to drug side-effect similarity*](https://doi.org/10.1371/journal.pone.0022187), PLoS ONE | Of 1,534 significantly side-effect-similar drug pairs, at least 64% share a target; 5.8% have neighbouring but distinct targets (summary). | For the key: shared targets are the main explanation of shared effects. |
| Kuhn et al. 2013, [*Systematic identification of proteins that elicit drug side effects*](https://doi.org/10.1038/msb.2013.10), Mol Syst Biol | 732 of 1,428 side effects are predicted to be caused chiefly by individual proteins (abstract); indication is not modelled. | For, with the confounder unaddressed. |
| Duran-Frigola & Aloy 2013, [*Analysis of chemical and biological features yields mechanistic insights into drug side effects*](https://doi.org/10.1016/j.chembiol.2013.03.017), Chem Biol | Most side effects need biological and chemical features together; roughly 38% are explained by biology alone (summary). | A label key will be wrong about many pairs even where it is right in aggregate. |
| Jamal et al. 2017, [*Predicting neurological adverse drug reactions based on biological, chemical and phenotypic properties of drugs*](https://doi.org/10.1038/s41598-017-00908-z), Sci Rep | Target features predicted neurological adverse reactions least well; phenotypic features, which include indications, best (as relayed). | Indication carries much of the signal in neurological side effects. |
| Tatonetti et al. 2012, [*Data-driven prediction of drug effects and interactions*](https://doi.org/10.1126/scitranslmed.3003377), Sci Transl Med | Corrects spontaneous reports for covariates including the reason for prescribing, producing OFFSIDES. | The published route to an indication-adjusted effect profile. |

OnSIDES's own extraction quality is published for the adverse-reactions
section of US labels (F1 0.90; [Tanaka et al. 2025](https://doi.org/10.1016/j.medj.2025.100642)).
None is published for the UK, EU or Japanese labels, which supply most
of the effects for many molecules.

**Measured here: the key's reliability** (`label_reliability.mjs`, with
`label_halves.py`). Each profile is rebuilt under the key's own rules from two
disjoint sets of labels: the US labels, and the UK, EU and Japanese ones.
Only ingredients with five or more effects in both halves are compared, and
neighbours are drawn from that common set.

| scope | ingredients | five nearest neighbours shared by the halves | chance |
| --- | --- | --- | --- |
| nervous system | 152 | 14.1% | 3.3% |
| every effect | 376 | 17.1% | 1.3% |

Graded the way the harness grades, on questions both can answer, over the same
candidates:

| judged by | predicted by | top-1 | MRR |
| --- | --- | --- | --- |
| non-US half, nervous system (126 questions) | the US half's own similarity list | 18.3% | 0.3459 |
| | the target ranking | 31.0% | 0.4786 |
| US half, nervous system (126) | the non-US half's own list | 24.6% | 0.3981 |
| | the target ranking | 34.1% | 0.4495 |
| non-US half, every effect (317) | the US half's own list | 25.9% | 0.3977 |
| | the target ranking | 28.7% | 0.4203 |
| US half, every effect (317) | the non-US half's own list | 31.9% | 0.4431 |
| | the target ranking | 38.8% | 0.4856 |

In all four cases the target ranking predicts a half of the label key better
than the other half of the label data does. Two cautions. First, each half is
thinner than the pooled key, so the pooled key's reliability is higher than a
half's. Second, the halves differ in how much OnSIDES reads from them, so
their disagreement mixes the key's noise with a real difference between
regulators. The conclusion survives both. The ranking already sits at or
above what a second measurement of the key achieves, so the key can rank
large changes but has no headroom to rank small ones. Its low absolute grade
is the key's ceiling, not the ranking's failure.

**Measured here: confounding by indication** (`confounding.mjs`). Approved
indications are read from ChEMBL's `drug_indication` at phase 4, by exact MeSH
id, with forms folded onto parents.

| pairs, both with an approved indication | pairs | share one |
| --- | --- | --- |
| label neighbours, nervous system | 2,023 | 41.9% |
| label neighbours, every effect | 2,936 | 46.2% |
| repaired-ATC classmates | 1,281 | 95.1% |
| EPC classmates | 2,934 | 75.3% |
| the ranking's first answer (label-key questions) | 273 | 63.7% |
| random pairs of labelled molecules | 18,372 | 7.7% |

The label key is less a use key than the class keys are. To test whether its
agreement with the ranking survives without shared use, the key was rebuilt
with every candidate sharing an approved indication with the question set
aside. A neighbour must then come from a drug for another disease. The
recomputed neighbours match the key's exactly for all 409 questions before
anything is set aside.

| on the 393 questions with an approved indication | scoreable | top-1 | shuffled | MRR |
| --- | --- | --- | --- | --- |
| label key as built | 336 | 14.3% | 1.8% | 0.2608 |
| neighbours from other diseases only | 306 | 1.6% | 0.8% | 0.0682 |

**Read this carefully, because it does not mean what it first seems to.**
Drugs with one mechanism are mostly approved for one disease, so setting
aside every same-indication candidate also sets aside most same-mechanism
ones. The test cannot separate "similar labels because similar mechanism"
from "similar labels because similar patients". What it does show is that
outside the pairs where use and mechanism coincide, the key and the ranking
barely agree. The label key's independence from the score's *inputs* is
real. Its independence from *what the drugs are for* is not, and it cannot
yet tell mechanism from use any better than ATC can. The literature's remedy
is to remove the effects that are the indication's own symptoms (SIDER's
approach, [Kuhn et al. 2016](https://doi.org/10.1093/nar/gkv1075)), not to
remove candidates. That keeps the same-mechanism neighbours and takes out the
disease.

### 3.5 The pre-registered pairwise key

| paper | finding | bearing |
| --- | --- | --- |
| Ryan et al. 2013, [*Defining a reference set to support methodological research in drug safety*](https://doi.org/10.1007/s40264-013-0097-8), Drug Saf | OMOP's 399 test cases, 165 positive and 234 negative controls, each with its level of evidence recorded (abstract, as relayed). | A per-pair evidence level, reported by level. |
| Coloma et al. 2013, [*A reference standard for evaluation of methods for drug safety signal detection using electronic healthcare record databases*](https://doi.org/10.1007/s40264-012-0002-x), Drug Saf | 44 positive and 50 negative controls; two experts verified each independently and a third settled disagreements; only drugs with enough exposure for a method to see were eligible (abstract, as relayed). | Two drafters and an adjudicator; and an eligibility rule like "the pair shares a target", so that a negative can fail. |
| Hauben et al. 2016, [*Evidence of misclassification of drug–event associations classified as gold standard 'negative controls' by OMOP*](https://doi.org/10.1007/s40264-016-0392-2), Drug Saf | OMOP's rules were asymmetric (a case report made a positive if one textbook cited it, a negative otherwise). Of 233 negatives, 40 (17%) were or may have been misclassified (abstract). | Audit the negatives with a symmetric rule, and budget for errors. |
| Harpaz et al. 2014, [*A time-indexed reference standard of adverse drug reactions*](https://doi.org/10.1038/sdata.2014.43), Sci Data | A reference set dated by label revision, so methods can be tested prospectively. | The same idea as freezing pairs.json before use. |
| Schuemie et al. 2013, [*Interpreting observational studies: why empirical calibration is needed to correct p-values*](https://doi.org/10.1002/sim.5925), Stat Med | Negative controls used as an empirical null: most observational p < 0.05 findings on true nulls disappeared once calibrated (abstract, as relayed). | A change's movement on negatives and opposites is its null: a gain on positives that moves negatives as much is not a gain. |
| Hripcsak & Wilcox 2002, [*Reference standards, judges, and comparison subjects*](https://doi.org/10.1136/jamia.2002.0090001), JAMIA | Experts serve three roles (making the standard, judging output, being compared), each with its own reliability. | Three drafters can be compared with each other, not only pooled. |
| Pakhomov et al. 2011, [*Towards a framework for developing semantic relatedness reference standards*](https://doi.org/10.1016/j.jbi.2010.10.004), J Biomed Inform | 13 raters on 101 term pairs; agreement moderate, with systematic rater differences (abstract, as relayed). Their earlier UMNSRS set (AMIA 2010, no DOI) reports drug–drug agreement among four raters of ICC 0.47 (relatedness) and 0.63 (similarity) (summary). | Human agreement on "are these drugs similar" is moderate; no key built by hand should be read as near-perfect. |
| Walters & Wilder 2023, [*Fabrication and errors in the bibliographic citations generated by ChatGPT*](https://doi.org/10.1038/s41598-023-41032-5), Sci Rep | 55% of GPT-3.5's and 18% of GPT-4's citations were fabricated, and many real ones misstated (abstract, as relayed). | The pairs' DOIs were all checked against Crossref by title; whether each cited source *says* what the pair quotes was not checked independently. |

**Measured here** (`difficulty.mjs`):

| | directions | clean by construction (no shared target) | of those that could fail, kept below rank 10 |
| --- | --- | --- | --- |
| negatives | 160 | 96 (60.0%) | 61 of 64 (95.3%) |
| opposites | 94 | 0 | 85 of 94 (90.4%) |

The headline "98.1% of negatives clean" is therefore 64 informative
directions in a denominator of 160. They are good news, but over a quarter of
the size the figure suggests. The opposites are the key's hardest and most
informative part: every one can fail, and they found the flumazenil gap
(SIMILARITY-HARNESS §16).

Of the 116 positives, 64 are repaired-ATC classmates, 81 EPC classmates and 91
MeSH classmates, and **110 are a classmate under at least one**. The
positives mostly re-ask questions the class keys already ask; six do not.

### 3.6 Across keys

- **Circularity, measured.** Grimm et al. 2015
  ([Hum Mutat](https://doi.org/10.1002/humu.22768)) distinguish circularity
  from shared data and from shared groups (variants of one gene on both
  sides). Both have analogues here. The first is the class keys restating
  ChEMBL's curated mechanisms, measured in SIMILARITY-LITERATURE §3.4: 39 of
  110 top-1 hits rest on a curated mechanism on both sides. The second is
  classmates sharing target records. Wallach & Heifets 2018
  ([J Chem Inf Model](https://doi.org/10.1021/acs.jcim.7b00403)) found that a
  benchmark's redundancy predicted most of the performance reported on it.
  The redundancy measure worth adding is the share of each key's classmate
  pairs where both molecules have a curated mechanism at a shared protein,
  reported per key beside its grade.
- **No latent-class combination.** Dawid & Skene 1979
  ([Appl Stat](https://doi.org/10.2307/2346806)) and Hui & Walter 1980
  ([Biometrics](https://doi.org/10.2307/2530508)) estimate each judge's error
  rates without a gold standard. Both assume judges err independently given
  the truth. ATC, MeSH and EPC share curation, and every key shares indication
  (§3.4), so the assumption fails here, and a pooled "consensus key" would
  count one curator's error several times.
- **Hubness is not a current problem.** Radovanović et al. 2010
  ([JMLR](https://jmlr.org/papers/v11/radovanovic10a.html)) describe
  nearest-neighbour lists dominated by a few points, and CLAUDE.md records
  that before normalisation aripiprazole was the top answer for 14 molecules.
  Now the skewness of top-10 appearances is 1.45, the top 1% of molecules
  fill 5.4% of top-10 places, and the most frequent appears in 49 lists
  (`difficulty.mjs`). The tested remedies, mutual proximity
  ([Schnitzer et al. 2012](https://jmlr.org/papers/v13/schnitzer12a.html))
  and CSLS ([Conneau et al. 2018](https://arxiv.org/abs/1710.04087)), would
  change the score and are not indicated. The figure is worth keeping as a
  diagnostic after any change to the normalisation.

---

## 4. What the measurements say about the keys together

| key | smallest detectable change (MRR) | shares with the score | share of classmate pairs with a shared approved indication | own reliability | note |
| --- | --- | --- | --- | --- | --- |
| ATC headline | 0.019 | curated mechanisms, partly | (headline not measured; repaired 95%) | not measurable | mostly structure and use classes |
| ATC repaired | 0.021 | curated mechanisms, partly | 95.1% | not measurable | |
| MeSH | 0.011 | mechanisms, often | not measured | not measurable | most power, broadest classes |
| EPC | 0.015 | restates mechanism | 75.3% | not measurable | about half of memberships unasserted (Winnenburg 2015) |
| PE | 0.013 | little | not measured | not measurable | coarse |
| label | 0.013–0.014 | nothing | 41.9% | 14% neighbour agreement between regulators | below the ranking's own agreement with it |
| pairwise | not a rate over questions | mechanisms labels state | — | one drafter per area | 64 informative negatives, 94 opposites |

The detectable change is for two settings compared paired on one build, at 5%
with 80% power (§2).

Three conclusions follow.

1. **D15 is the only constant every key has tested.** The family weight at 1.0
   is detected under MeSH alone, the broadest key. Every other change in the
   sweep sits below what any key resolves, so the sweep can neither confirm
   nor reject it. SIMILARITY-LITERATURE §4.1's rule, "adopt a
   constant only when judges of different provenance agree", needs a
   companion: *and only when the change is larger than those judges can
   resolve*. Without it, the rule would adopt noise whenever two noisy keys
   happen to agree in sign.
2. **The label key is a check, not an arbiter.** It is the only judge that
   reads no curation, which makes it the right one to veto a change that only
   curated judges like. But it is noisier than the ranking, and it rides on
   indication. Its veto should be read only for changes above its resolution.
3. **The pairwise key's opposites are its most valuable part.** They are
   reachable, hard, sourced and held out, and they test the direction terms
   (D15, D19, `OPPOSED_ACTIONS`), which are the part of the score the keys
   have most firmly shown to matter.

---

## 5. Brain-specific keys: what the literature offers

The page's question is "may act in similar ways in the brain". None of the
keys above measures the brain directly. The literature has five candidates;
none is ready at catalogue scale.

| candidate | evidence that target profiles predict it | data | verdict |
| --- | --- | --- | --- |
| Subjective-effect reports of psychedelics | [Zamberlan et al. 2018](https://doi.org/10.3389/fnint.2018.00054): the similarity of binding-affinity profiles of substituted phenethylamines and tryptamines correlates with the semantic similarity of their Erowid reports (abstract; R = 0.60 on one affinity set and 0.48 on another, summary). [Ballentine et al. 2022](https://doi.org/10.1126/sciadv.abl6989) map words in 6,850 reports on 27 drugs to receptor expression. | Erowid reports (terms of use unchecked); 18–27 drugs | the only direct test of target profile against brain effect in this survey; a pilot for one class, not a key |
| Receptor affinity against clinical effects within a class | [Kroeze et al. 2003](https://doi.org/10.1038/sj.npp.1300027): H1 affinity predicts short-term weight gain across 17 antipsychotics (as relayed). | trial and review tables | within-class checks, a few dozen drugs |
| Pharmaco-EEG fingerprints | Dimpfel 2003 (Eur J Med Res, PMID 12844474): rat EEG classifies drugs into eight CNS categories (abstract, as relayed). | no open per-drug table found | not buildable until a dataset is found |
| Zebrafish behavioural profiles | Rihel 2010, Kokel 2010, Bruni 2016 (in SIMILARITY-LITERATURE §4.2) | supplementary tables, joined by name | buildable with care; name joins break invariant 15 unless each compound is mapped by identifier |
| Drug discrimination | the classic "feels alike" measure | no machine-readable database of generalisation results found; review literature only | a hand-curated, sourced pilot in the pairwise key's style |
| Mouse behavioural screening (SmartCube) | Roberds et al. 2011, Alexandrov et al. 2015 | proprietary reference database | not obtainable |

---

## 6. Proposed order

Each step is its own change and adopts nothing about the score.

**Step 1: fix the decision rule before the next constant moves (no new
data).**

- Report every sweep cell with its paired interval, question-level and
  class-resampled, and the Holm-adjusted test across the cells actually run.
  `power.mjs` does this for six settings. Folded into `sweep.mjs`, it would do
  it for every grid point.
- State each key's resolution beside its grade, as Status states coverage.
- Write the adoption rule down, versioned like a key. A suggested form:
  a change must be detected (Holm) under at least two keys of different
  provenance, one of them reading no curation; must not worsen the pairwise
  key's negatives or opposites; and is confirmed once on the held-out pairwise
  key after it is chosen, never before. Under that rule, of the six settings
  in §2 only D15 would qualify, and it is already adopted.
- Report MRR averaged over classes beside MRR averaged over questions.

**Step 2: pairwise key v2.** Keep v1 frozen; add, never edit.

- Draw new negatives from pairs that **share at least one target** but differ
  in primary mechanism (an antipsychotic and an antihistamine at H1; a tricyclic
  and an anticholinergic at muscarinic receptors). These can fail, and they
  are what the score most needs to get right. Report negative rates over
  reachable directions beside the current figure.
- Have a second drafter, blind to the first and from a different model family,
  label every pair, with an adjudicator. Report agreement by kind (Coloma 2013;
  Pakhomov 2011).
- Check that each cited source says what the pair quotes, not only that the
  DOI resolves. Record each pair's evidence level (label, trial, review, case
  report), and grade by level (Ryan 2013).
- Audit v1's negatives with one symmetric rule for what disqualifies a
  negative, and budget for Hauben's 17%.
- Grow the opposites, the part that has found a real gap.

**Step 3: label key v2.** Under SIMILARITY-LITERATURE §4.1 a new key needs a
new version and a changelog entry; v1 stays.

- Require an effect to appear in labels from **two regulators**, or report a
  US-only and a non-US reading beside the pooled one (Cornelius 2016).
  `label_reliability.mjs` measures each version's reliability, and a v2 that
  does not raise it is not better.
- Remove from each profile the effects that are its approved indications' own
  symptoms, through an identifier mapping from the indication's MeSH heading to
  MedDRA terms, never by name. Then rerun `confounding.mjs`: the test is
  whether the "other diseases only" row rises above its shuffle.
- Consider OFFSIDES (Tatonetti 2012) as an indication-adjusted second source.

**Step 4: graded relevance by information content**, as one alternative
reading of the repaired ATC key and the MeSH key, labelled untested
(Pesquita 2009).

**Step 5: a brain-specific pilot.** Two candidates: a sourced
drug-discrimination subset added to the pairwise key's opposites and
positives, or the psychedelic subjective-effect set as a within-class check.
Neither will be large enough to arbitrate a constant. Both would test the
page's own question.

**What not to do.** Do not add more class keys to raise power: they share
curation and indication, and agreement among them is not independent
evidence. Do not pool the keys into a consensus by latent-class methods: their
errors are correlated. And do not keep sweeping for changes under about 0.01 MRR:
on this catalogue no key can see them, and a constant chosen there is chosen
by noise.

---

## 7. How much to trust this

- **Citations.** Three literature sweeps were run by subagents in parallel
  (class keys, phenotype keys, evaluation method). Every DOI cited here was
  resolved on Crossref on 2026-10-16, and its title and first author matched.
  The abstracts behind three load-bearing figures, Cornelius 2016's 29%,
  Hauben 2016's 17% and Winnenburg 2015's 50%, were read here. Rows marked
  *summary* rest on a subagent's reading of a full text, and rows marked
  *as relayed* on a subagent's reading of an abstract, neither checked here.
  Those figures should be checked before anything depends on them. Pakhomov
  et al. 2010 (UMNSRS) and Dimpfel 2003 have no DOI.
- **Measurements.** Every figure in §2–§4 comes from `power.mjs`,
  `label_reliability.mjs` (with `label_halves.py`), `confounding.mjs` and
  `difficulty.mjs`, against the 2026-10-13 build. They read the payload,
  `db/cohort1.db`, the cached OnSIDES zip and, for indications, ChEMBL 37 at
  `$CHEMBL_SQLITE_PATH`. They write nothing. The bootstraps are seeded, so a
  rerun prints the same intervals.
- **The detectable changes and sample sizes** (§2) use each key's median
  standard deviation of per-question changes over the five small settings, and
  the normal approximation. They are orders of magnitude, not a design; a
  larger change moves more questions further, so its spread is larger too.
- **The indication test** compares exact MeSH ids. "Depressive Disorder" and
  "Depressive Disorder, Major" count as different, which undercounts
  sharing, so the true share for every row in §3.4 is somewhat higher.
- **Not measured.** The MeSH key's share of same-indication pairs; the
  redundancy measure proposed in §3.6; the agreement between the three
  pairwise drafters, which cannot be measured since each drafted a different
  area; and OnSIDES's extraction quality outside the US.
