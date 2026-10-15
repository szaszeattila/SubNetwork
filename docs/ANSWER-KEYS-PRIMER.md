# The answer keys, explained: ATC, FDA's classes through RxNav, OnSIDES and the pre-registered pairs

Written 2026-10-15 against the active build of 2026-10-13 (2,452 entries).
**An explainer: it adopts nothing and changes nothing.** It says what each
outside source is, how this project turns it into an answer key, and what
each key can and cannot tell you. The measurements, and the arguments for
each key, are in [SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §3–4 and
§13–16 and in [SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md) Parts 3–4.
Where a figure here disagrees with CLAUDE.md's **Status**, Status is right.

---

## 0. What an answer key is for

The page ranks every molecule against every other by shared targets and
shows the closest. Nobody can check that ranking pair by pair: there are
2,452 entries and about three million pairs. So the ranking is graded
against **answer keys**: lists, written by someone else for another purpose,
that say which drugs belong together.

Every key here is used the same way. For each molecule the key can ask about
(a **question**), the harness asks the page for its similarity list and
walks down it to the first molecule the key calls a **classmate**. How far
down that is is the molecule's **rank**. The grade summarises the ranks
across all the questions (§6 defines each figure).

A key is worth more the less it shares with the score. If the score reads
ChEMBL's curated mechanisms and the key restates the same mechanisms, a
good grade partly measures the score agreeing with itself. That is why
there are several keys from different curators, and why the table in §5
says what each one shares with the score.

| key | what it says belongs together | curator | section |
| --- | --- | --- | --- |
| ATC level 4 (the headline) and its repair | drugs WHO files in one subgroup | WHO | §1 |
| FDA EPC and PE | drugs FDA gives one pharmacologic class or physiologic effect | FDA, reached through NLM's RxNav | §2–3 |
| label effects | drugs whose labels list similar nervous-system side effects | drug labels, read by OnSIDES | §4 |
| pre-registered pairs | 243 named drug pairs: alike, unlike, or opposite | written here, each with a cited source | §5 |

RxNav is not a key. It is the identifier service the FDA and OnSIDES keys
both go through, so it gets its own section (§2).

---

## 1. ATC: the WHO's drug classification, and its levels

### What it is

The **Anatomical Therapeutic Chemical (ATC) classification** is the WHO's
filing system for drug substances. The WHO Collaborating Centre for Drug
Statistics Methodology in Oslo maintains it and revises it every year. It
was built for counting drug use across countries, not for describing
pharmacology, and that purpose shows in how it groups drugs.

Each code is a nested address with five levels. Amitriptyline is `N06AA09`:

| level | code | name | what WHO groups by at this level |
| --- | --- | --- | --- |
| 1 | `N` | Nervous system | the anatomical main group: the organ or system the drug acts on (14 groups, A to V) |
| 2 | `N06` | Psychoanaleptics | a therapeutic or pharmacological subgroup |
| 3 | `N06A` | Antidepressants | a chemical, pharmacological or therapeutic subgroup |
| 4 | `N06AA` | Non-selective monoamine reuptake inhibitors | a chemical, pharmacological or therapeutic subgroup |
| 5 | `N06AA09` | amitriptyline | the chemical substance |

Three properties matter for using it as a key.

- **A drug can have several codes**, one for each use WHO recognises.
  Caffeine is `N06BC01` (a psychostimulant, *xanthine derivatives*) and
  `D11AX26` (a dermatological). Morphine carries `N02AA01` and two codes
  for combination products.
- **Levels 3 and 4 group by whatever WHO found most useful for that
  subgroup**: chemical structure, mechanism or use. WHO's own definition
  says "chemical, pharmacological or therapeutic". The same
  benzodiazepines are filed twice, as anxiolytics (`N05BA`) and as
  hypnotics (`N05CD`). Every opioid agonist sits in one of five
  structure classes (`N02AA` to `N02AF`), and every D2-blocking
  antipsychotic in one of nine. Of the 64 level-4 classes the key uses, 42
  group by chemical structure, 16 by mechanism and 4 by use, read by class
  name (SIMILARITY-LITERATURE §3.5).
- **A fourth-level letter `X` means "other"**: `N06AX` is *Other
  antidepressants*, a group defined by its members **not** sharing a
  mechanism (mirtazapine and bupropion are both in it).

### How it becomes the headline key (`--key atc`)

1. ChEMBL's `molecule_atc_classification` is read at build time, keeping
   **only N codes**. That filter is the cohort's ATC admission route; it was
   never designed to define a key. The codes are stored in
   `molecules.atc_level5` and exported in `viz/graph.data.js`.
2. The harness truncates each code to five characters, its level-4 class
   (`N06AA09` → `N06AA`), drops every `X` class, and drops classes with only
   one member.
3. Two molecules are classmates when they share a level-4 class. That gives
   **395 questions in 64 classes**.

On the current build, 284 of the 395 have a classmate somewhere in their
list and are graded: **top-1 32.7%, MRR 0.4607**. The other 111 have no
classmate anywhere in their list, which says something about ChEMBL's
coverage rather than about the ranking, so they are left out of the rates.

**What it gets wrong.** Because it reads only N codes, a right answer filed
elsewhere counts as a miss. Naloxone is `V03AB` (*antidotes*), so it is wrong
as naltrexone's nearest neighbour; seltorexant has no ATC code, so it is
wrong as suvorexant's. Because it is binary, thioridazine → chlorpromazine (two
phenothiazine subgroups, `N05AC` and `N05AA`) scores the same as an unrelated
drug. And it has no negatives: nothing in it says two drugs must *not* be near
each other.

### The repaired key (`--key atc-repaired`, v1.0.0)

Built 2026-10-13 and reported beside the headline, never in place of it.
Its rules are in `analysis/similarity_harness/atc_repaired.json`:

- the questions are still the molecules with an N code, but **classmates
  can come from any ATC code** the catalogue holds (read from
  `molecule_classes`, source `atc`, in the database);
- residual classes filed under a letter other than X (`N02BG`, `N05CM`),
  classes defined by use (drugs for nicotine, alcohol or opioid dependence,
  antivertigo preparations, antidotes) and non-pharmacological classes are
  set aside, each with its reason written next to it;
- a molecule in a **sibling class** (same level 3) earns half credit in
  nDCG@10. Top-1 and MRR still count only exact classmates.

It asks 353 questions, grades 259, and scores top-1 36.3%, MRR 0.4958 and
nDCG@10 0.3850.

**What it shares with the score:** partly the curated mechanisms. Where
an ATC class follows mechanism (SSRIs, MAO inhibitors), it encodes the same
knowledge ChEMBL's curators write into `drug_mechanism`, and 39 of the 110
top-1 hits on the 1,335-entry build were won mainly at a target where both
molecules have a curated mechanism (SIMILARITY-LITERATURE §3.4).

---

## 2. RxNav, RxNorm and RxClass: how a molecule reaches FDA's labels

### What they are

**RxNav** is the U.S. National Library of Medicine's browser and free
public web API for its drug terminologies. Two of them are used here:

- **RxNorm** gives every clinical drug sold in the US a normalised name
  and an identifier, the **RxCUI**. Its concepts come in term types. The
  ones that matter here:
  - **IN**, an *ingredient* (sertraline);
  - **PIN**, a *precise ingredient*, a salt or ester (sertraline
    hydrochloride);
  - brand names and clinical drugs (a strength and dose form), which
    this pipeline never uses.
- **RxClass** links RxNorm ingredients to drug classes from several class
  systems: ATC, MeSH, the VA's classes and, the ones used here, FDA's
  pharmacologic classes (§3).

A molecule in this catalogue is a ChEMBL structure, not an RxNorm drug, so
something has to connect the two. That something is the **FDA UNII**
(Unique Ingredient Identifier). FDA's Global Substance Registration System
assigns it to a substance from its structure, and both FDA and RxNorm index
by it.

### The route, an identifier at every step

`scripts/resolve_cohort_fda_classes.py` goes from structure to class without
ever searching by name (invariant 15):

```
molecules.inchikey ──► FDA UNII ──► RxCUI ──► RxNorm ingredient (IN) ──► FDA classes
  (the structure)      (FDA's UNII     (RxNav,     (a PIN is followed to      (RxClass, asserted
                       records file,    by UNII)    its one IN; any other      for the ingredient
                       exact InChIKey)              term type is unused)       itself)
```

Three rules keep it from guessing:

- **Exactly one ingredient, or nothing.** A molecule whose identifiers reach
  two ingredients is dropped as ambiguous and listed, never resolved to
  either. A wrong drug is worse than a missing one (invariant 6).
- **The parent's own structure decides.** ChEMBL folds salts and
  formulations onto a parent; RxNorm sometimes keeps such a form as a drug
  of its own. ChEMBL folds aminophylline onto theophylline, but RxNorm files
  aminophylline as a separate ingredient (RxCUI 689 against 10438). Reading
  every form at once dropped theophylline as ambiguous, so a folded form is
  now read only where the parent reaches nothing (DATA-QUALITY-LOG,
  2026-10-13).
- **Not pinned, but cached.** RxNav is a live service with no downloadable
  release this pipeline can pin. Every answer is cached as JSON under
  `db/cache/rxnav/`, a rerun is offline, and RxNav's version and the run
  date are recorded in `build_manifest`. A cold run takes about 50 minutes.

**Coverage.** 930 molecules reach exactly one ingredient: 911 through the
parent and 19 through a form. 909 molecules have a UNII that RxNorm does not
know, most presumably because they were never sold in the US. Nobody has
checked.

The OnSIDES key (§4) reuses this route from the same cache, because OnSIDES
is keyed by the same RxNorm ingredient ids.

---

## 3. FDA's pharmacologic classes: EPC, MoA and PE

### What they are

When FDA approves a drug label, it indexes the active ingredient with
pharmacologic classes on four axes, three of which are read here. The terms
come from **MED-RT** (Medication Reference Terminology), the Department of
Veterans Affairs' drug-class terminology that replaced NDF-RT and that FDA
draws its class terms from. That is why every class code here looks like
`N0000175696`.

- **Established Pharmacologic Class (EPC).** The class FDA judges
  scientifically valid and clinically meaningful for the drug's approved
  indication. It is the phrase in the indications line of a label's
  *Highlights*: "Zoloft is a *selective serotonin reuptake inhibitor (SSRI)*
  indicated for …".
- **Mechanism of action (MoA).** What the drug does at the molecular level.
  It mixes pharmacology with pharmacokinetics: sertraline is a *Serotonin
  Uptake Inhibitor* and also a *Cytochrome P450 2D6 Inhibitor*.
- **Physiologic effect (PE).** What happens in the body. This is the
  nearest thing among the class keys to an effect axis, and it is coarse.
- The fourth axis, *chemical structure*, is not read.

From this database (the labels are as RxClass serves them):

| molecule | EPC | MoA | PE |
| --- | --- | --- | --- |
| sertraline | Serotonin Reuptake Inhibitor | Serotonin Uptake Inhibitors; Cytochrome P450 2D6 Inhibitors | Increased CNS Serotonin Activity |
| amitriptyline | Tricyclic Antidepressant | Norepinephrine Uptake Inhibitors; Serotonin Uptake Inhibitors | Increased CNS Norepinephrine Activity; Decreased Serotonin Degradation |
| morphine | Opioid Agonist | Full Opioid Agonists; Opioid mu-Receptor Agonists | Analgesia; Decreased GI Motility; and four more |
| caffeine | Central Nervous System Stimulant; Methylxanthine | Enzyme Inhibitors | Central Nervous System Stimulation; Bronchodilation; and three more |

The table shows the axes' character. An EPC is narrow and mostly names a
mechanism. A MoA can name one precisely (*Opioid mu-Receptor Agonists*) or
say nothing (caffeine's *Enzyme Inhibitors*). A PE can be generic:
*Central Nervous System Stimulation* holds both caffeine and naltrexone.

RxClass serves each class with the source that asserted it. Only rows from
**FDASPL** (FDA's structured product labels) and **MEDRT** are kept, and only
those asserted for the ingredient itself; DAILYMED's rows repeat FDASPL's and
are ignored. The backfill stores everything else it reads too, CYP450
classes included, as the `fda_epc`, `fda_moa` and `fda_pe` sources of
`molecule_classes`. **The page never shows them.** Their only use is grading.

**Coverage.** 627 molecules have an EPC, 787 a MoA and 733 a PE. Only drugs
with a US label are covered.

### How they become keys (`analysis/similarity_harness/fda_keys.json`, v1.0.0)

- **`--key epc`.** Molecules sharing an EPC are classmates. Molecules
  sharing only a MoA earn half credit in nDCG, except through MoA classes
  that describe how a drug is handled (CYP450 enzymes, P-glycoprotein and
  other transporters, glucuronidation) or that say nothing (*Enzyme
  Inhibitors*, *Receptor Interactions*, *Unknown Cellular or Molecular
  Interaction*). Each exclusion is listed with its reason.
- **`--key pe`.** Molecules sharing any physiologic effect are classmates,
  unfiltered.

| key | questions | graded | top-1 | MRR | filtered top-1 | filtered MRR |
| --- | --- | --- | --- | --- | --- | --- |
| EPC | 487 | 455 | 45.7% | 0.5946 | 64.0% | 0.7319 |
| PE | 701 | 598 | 37.6% | 0.5154 | 53.8% | 0.6498 |

**What they share with the score.** FDA is a different curator from WHO
and ChEMBL, but an EPC such as *Serotonin Reuptake Inhibitor* states the
same mechanism ChEMBL curates. EPC is the narrowest key here and agrees with
ATC on little more than half of each other's classmate pairs (SIMILARITY-HARNESS
§13).

---

## 4. OnSIDES: side effects from drug labels

### What it is

**OnSIDES** is a database of the adverse effects listed in drug labels, made
by the Tatonetti lab ([Tanaka et al. 2025, *Med*](https://doi.org/10.1016/j.medj.2025.100642);
[GitHub](https://github.com/tatonetti-lab/onsides)). A fine-tuned language
model reads label text from the US (DailyMed), the UK, the EU and Japan and
turns each adverse effect it finds into a **MedDRA** term. The result is
keyed by RxNorm ingredient. Release v3.1.1 is pinned by sha256 and licensed
CC BY 4.0.

It matters here because **it is the only key that shares no input with the
score.** Every other key reads targets or a curator's word about a mechanism.
A label's adverse-reactions section records what happened to patients. If
two drugs' labels list the same unusual nervous-system effects, they may act
alike in the brain whatever ChEMBL has measured.

### MedDRA, and the hierarchy OnSIDES leaves out

**MedDRA** (Medical Dictionary for Regulatory Activities) is the standard
vocabulary for adverse events. It is a five-level tree:

| level | example |
| --- | --- |
| System Organ Class (SOC) | Nervous system disorders |
| High Level Group Term (HLGT) | Movement disorders (incl parkinsonism) |
| High Level Term (HLT) | Tremor (excl congenital) |
| Preferred Term (PT) | Tremor |
| Lowest Level Term (LLT) | Shakiness, Tremulousness, Tremor limb: the wordings a label may use |

The key needs only the effects under two SOCs: *Nervous system disorders*
and *Psychiatric disorders*. MedDRA's hierarchy is licensed, so OnSIDES
ships the terms without it. This project places each term through
**ADReCS** v3.3 (Adverse Drug Reaction Classification System,
[Cai et al. 2015](https://doi.org/10.1093/nar/gku1066)), which publishes
MedDRA's tree with its codes. ADReCS is pinned and read locally, but it states
no open licence. That is why a second reading that needs no hierarchy,
`onsides-all`, sits beside the nervous-system key.

Each term is placed by code where it is a PT. Where it is an LLT, it is
placed by its exact name among one PT's synonyms. An LLT that names several
PTs ("Convulsion") is never resolved to one of them and stays its own
effect. A Wikidata route was tried first and reached only 95 of the
nervous-system terms the catalogue's labels use, missing *Depression* and
*Hallucination* (DATA-QUALITY-LOG, 2026-10-14).

### How it becomes a key (`analysis/similarity_harness/onsides_key.json`, v1.0.0)

These rules were fixed before the key graded anything, and committed as
such (9d47202):

1. **A label is read only if all its products are one ingredient.**
   Combination products are skipped, because their effects belong to the
   partner drug as much as to this one. 691 molecules have at least one
   single-ingredient label.
2. **An effect belongs to a molecule if two of its labels list it**, or its
   only label does. A share of labels was the first rule written, but labels
   of one drug differ a hundredfold in what OnSIDES reads from them:
   diazepam's 34 US labels yield a median of 4 effects each, its 13 Japanese
   labels 49. Under that rule, no effect reached half of diazepam's labels.
3. **Only nervous-system and psychiatric effects count**, and a molecule
   needs at least five of them to be asked or judged. That leaves 409
   questions.
4. **Rare effects weigh more.** Each effect is weighted by its *inverse
   document frequency*, ln(N / df), where N is the number of ingredients
   with a profile and df the number listing that effect. An effect on
   nearly every label weighs nearly nothing. That covers class boilerplate,
   and also OnSIDES's habit of reading the table heading "Nervous system
   disorders" as the effect "Nervous".
5. **Similarity is the cosine** of two weighted profiles: the overlap
   measured as an angle, so a long label does not beat a short one by length.
6. **A molecule's five nearest label neighbours are its classmates**;
   neighbours six to ten earn half credit in nDCG. Two molecules that are one
   RxNorm ingredient (haloperidol and its decanoate) share every label, so
   neither is the other's neighbour.

### What it says, and where it is noisy

Read before it graded anything (`node analysis/answer_keys/neighbours.mjs`):

- sertraline's classmates are vilazodone, fluoxetine, escitalopram,
  citalopram and fluvoxamine;
- morphine's are methadone, oxymorphone, meperidine, oxycodone and
  hydromorphone;
- diazepam's are clonazepam, lorazepam, estazolam, triazolam and
  *methadone*, which is noise;
- donepezil's include memantine, by shared indication rather than by
  mechanism;
- ciprofloxacin's are azithromycin and bexarotene, because a
  non-nervous-system drug's few nervous-system effects are generic.

| key | questions | graded | top-1 | MRR | top-1 if the list were shuffled |
| --- | --- | --- | --- | --- | --- |
| label, nervous system | 409 | 346 | 14.5% | 0.2620 | 1.8% |
| label, every effect | 609 | 507 | 19.3% | 0.3180 | 2.8% |

**The absolute grade is low, and the key is why.** Each question has five
classmates out of hundreds, where a class key gives dozens, so a shuffled
list almost never hits. Measured as a ratio over the shuffle, the ranking
does as well against this key (8.1×) as against the keys that share its
curation (ATC 6.8×, EPC 9.0×). The richer a label, the more the ranking
agrees with it: filtered top-1 rises from 19% for molecules with 5–8
effects to 37% for those with 17 or more.

**Three cautions.** Labels carry class boilerplate: every antidepressant
label has the suicidality warning. Effects are confounded by indication:
drugs for one disease list that disease's symptoms. And the ADReCS licence
is unresolved.

---

## 5. The pre-registered pairwise key

### What "pre-registered" means

In clinical trials and experimental psychology, a study is
**pre-registered** when its hypotheses and its analysis plan are written
down and time-stamped before any data are seen. Results cannot then be
dredged for whatever looks good afterwards. The same idea applies here: a
hand-written answer key could be bent to say anything if it were written
after looking at the ranking.

SIMILARITY-HARNESS §3 refused a hand-written key for exactly that reason.
`analysis/answer_keys/pairs.json` is hand-written anyway. It answers the
objection by how it was made, not by what it says:

- **drafted blind.** Three subagents wrote it, one per area (psychiatry;
  neurology and pain; autonomic and other receptor systems). Each was given
  only the catalogue's ChEMBL ids and names and was forbidden to open the
  repository or run the ranking. The session that commissioned them
  reviewed the drafts, and every edit it made is listed in the file;
- **sourced.** Every pair cites what it rests on: 207 sources, each a DOI
  whose title was checked against Crossref or a US label on DailyMed whose
  setid resolves, quoted with what it says. ChEMBL and GtoPdb (the score's
  own inputs), DrugBank and Wikipedia were not allowed;
- **frozen.** The pairs and the rules that grade them were committed and
  pushed (3ed013f) before either was run against the ranking;
- **held out.** No `--key` loads it, so no sweep over the scoring constants
  can be tuned to it. Changing a pair or a rule makes a new version, logged
  in SIMILARITY-HARNESS.md, and never in the same change as a constant it
  judges.

### What it holds

243 pairs of three kinds:

| kind | count | meaning | example |
| --- | --- | --- | --- |
| **positive** | 116 | the same primary mechanism at the same target, in the same direction | fluoxetine and sertraline: both inhibit the serotonin transporter |
| **negative** (known-unlike) | 80 | the same indication reached by different primary mechanisms, with no shared primary target | sertraline and bupropion: both for depression; one blocks serotonin reuptake, the other noradrenaline and dopamine uptake and "not serotonin" (its label) |
| **opposite** | 47 | one target, opposite directions | flumazenil and alprazolam: alprazolam enhances GABA-A through the benzodiazepine site; flumazenil competitively blocks that site |

Two flags mark pairs to read with care. **`seen`** (44 pairs) marks a
relationship the older 50-probe diagnostic had already put to the ranking,
so its answer was known in advance. **`doubt`** (34 pairs) marks weaker
sourcing or a weaker claim: a class-level source, a mechanism a label calls
unknown, or an indication that overlaps rather than matches.

### The rules

- Each pair is read **both ways**: b in a's list, and a in b's.
- A **positive** is a hit when the partner ranks within the **top 10**. A
  partner absent from the list shares no target and cannot be reached; it is
  counted as coverage, never as a miss.
- A **negative** or an **opposite** is **clean** when the partner ranks
  below 10 or is absent.
- **Ordering:** in each list asked about at least one positive and at least
  one negative or opposite, the share of (positive, other) pairs in which the
  positive ranks higher. An absent partner ranks last, and a tie counts half.
- Three readings are always reported: every pair, without `seen`, and
  without `doubt`. None replaces another.

### First grade, and what it found

`node analysis/answer_keys/pairs.mjs`, on the current build:

| reading | positives within top 10 | negatives clean | opposites clean | positive above other |
| --- | --- | --- | --- | --- |
| every pair | 75.4% of 232 | 98.1% of 160 | 90.4% of 94 | 96.0% of 93 lists |
| without `seen` | 77.6% of 156 | 98.1% of 160 | 92.7% of 82 | 95.8% of 72 |
| without `doubt` | 77.6% of 210 | 97.7% of 130 | 91.0% of 78 | 96.8% of 82 |

The `seen` pairs grade no better than the rest, so having been asked before
did not flatter the key. Three findings:

- **The opposition rule misses one pair of actions.** 7 of the 9 failed
  opposite directions are flumazenil against the benzodiazepines and
  zolpidem, at ranks 2 to 8. ChEMBL curates flumazenil as an ALLOSTERIC
  ANTAGONIST and them as POSITIVE ALLOSTERIC MODULATOR, and
  `OPPOSED_ACTIONS` names no such pair. It has not been changed: that list
  is chosen by argument, and the item is open in CLAUDE.md.
- **Negatives stay apart.** 3 of 160 fail: lacosamide and levetiracetam rank
  each other 2nd and 6th. Xanomeline ranks olanzapine 10th, and that one
  reflects a real shared target: olanzapine blocks the muscarinic receptors
  xanomeline activates.
- **The worst positives** are tranylcypromine to isocarboxazid (rank 183),
  lacosamide to oxcarbazepine (108), cabergoline to bromocriptine (102) and
  propranolol to nadolol (101).

**What it shares with the score.** Labels and reviews state the mechanisms
ChEMBL's curators also read, so this key is not independent the way the label
key is. What it adds that no other key has is **negatives, opposites and a
fixed set of questions**.

---

## 6. The keys side by side

| key | judges | shares with the score | questions | graded | top-1 | MRR | where |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ATC level 4 (headline) | WHO subgroup, N codes only | partly the curated mechanisms | 395 | 284 | 32.7% | 0.4607 | `molecules.atc_level5`; `harness.mjs` |
| ATC repaired | any ATC code, exclusions, sibling half credit | partly the curated mechanisms | 353 | 259 | 36.3% | 0.4958 | `atc_repaired.json` |
| FDA EPC | FDA's established class; MoA for half credit | restates the mechanism | 487 | 455 | 45.7% | 0.5946 | `fda_epc`/`fda_moa`; `fda_keys.json` |
| FDA PE | FDA's physiologic effect | little; a coarse effect axis | 701 | 598 | 37.6% | 0.5154 | `fda_pe` |
| MeSH actions | NLM's indexed pharmacological actions | many actions name a mechanism | 1,028 | 865 | 45.0% | 0.5945 | `mesh_pa` (SIMILARITY-HARNESS §10, §12) |
| label effects | five nearest label neighbours | **nothing** | 409 | 346 | 14.5% | 0.2620 | `label_effects`; `onsides_key.json` |
| pairs | 243 sourced pairs | the mechanisms labels and reviews state | 243 pairs | — | — | — | `pairs.json`; **held out** |

The grades are not comparable across rows as absolute numbers. A key with
broad classes or many classmates per question is easier to hit, which is why
`chance.mjs` sets each grade beside a shuffle of the same lists. Against the
shuffle, every key puts the ranking's top-1 at about five to nine times
chance.

**How the keys are used together.** SIMILARITY-LITERATURE §4.1 asks that a
scoring constant be changed only when judges of different provenance agree,
with one key held out. In the sweep across five judges (SIMILARITY-HARNESS
§15), every judge rates switching off the opposite-direction demotion (D15)
as the worst single setting. Lowering the weight of replicated-only claims
helps only under the judges that read curation (ATC, MeSH) and hurts under
the label key. That is the pattern the label key was built to catch.

---

## 7. Reading a grade

- **Question.** A molecule the key can ask about.
- **Scoreable / unanswerable.** A question is unanswerable when none of its
  classmates appears anywhere in its similarity list, because they share no
  target in ChEMBL. Unanswerable questions are counted apart and left out of
  every rate. Otherwise, a change that made more claims eligible would raise
  the grade by adding answerable questions, not by ranking better.
- **Top-1.** The share of graded questions whose first answer is a
  classmate.
- **MRR** (mean reciprocal rank). Each question scores 1 ÷ the rank of its
  first classmate, and the scores are averaged. Rank 1 scores 1.0, rank 2
  scores 0.5 and rank 10 scores 0.1. It notices a move from rank 50 to rank
  8, which top-1 does not.
- **Filtered.** The same list, walked past only the molecules the key can
  judge. Seltorexant above suvorexant's classmates is neither right nor
  wrong under ATC, which has no code for it, so the filtered reading steps
  over it. This is the "filtered" setting of link-prediction evaluation.
  It changes the judge, not the ranking, and it is not an upper bound.
- **nDCG@10** (normalised discounted cumulative gain over the top ten). It
  credits every relevant molecule in the first ten, not just the first,
  discounts lower ranks, and allows half credit (a sibling class, a MoA
  match, a label neighbour sixth to tenth).
- **Against a shuffle.** The grade the same list would get in random
  order, computed in closed form (`chance.mjs`). A grade means something
  only as its distance from that figure.
- **Held out.** A key no sweep may tune to. Only the pairwise key is held
  out.
- **Fixed / frozen, versioned.** Each key's rules sit in a JSON file with a
  version and a date. Changing it is a change of instrument, recorded in
  SIMILARITY-HARNESS.md and never made in the same change as a constant it
  judges.

---

## 8. Commands and files

```bash
node analysis/similarity_harness/evaluate.mjs                     # ATC, the headline
node analysis/similarity_harness/evaluate.mjs --key atc-repaired
node analysis/similarity_harness/evaluate.mjs --key epc           # also --key pe
node analysis/similarity_harness/evaluate.mjs --key onsides       # also onsides-all
node analysis/answer_keys/pairs.mjs                               # the pairwise key
node analysis/answer_keys/neighbours.mjs SERTRALINE               # what the label key says
node analysis/answer_keys/agreement.mjs                           # how far the keys agree
node analysis/answer_keys/chance.mjs                              # each grade beside a shuffle

python3 scripts/resolve_cohort_fda_classes.py     # FDA classes via RxNav (~50 min cold, cached)
python3 scripts/resolve_cohort_label_effects.py   # OnSIDES label effects; after the FDA classes
```

| file | what it holds |
| --- | --- |
| `analysis/similarity_harness/harness.mjs` | every key's construction and the grading walk |
| `analysis/similarity_harness/atc_repaired.json` | the repaired ATC key's exclusions, each with its reason |
| `analysis/similarity_harness/fda_keys.json` | which MoA classes earn no credit, and why |
| `analysis/similarity_harness/onsides_key.json` | the label key's rules, each with its reason |
| `analysis/answer_keys/pairs.json` | the 243 pairs, their sources, rules and provenance |
| `scripts/resolve_cohort_fda_classes.py` | the RxNav route, in its docstring |
| `scripts/resolve_cohort_label_effects.py` | OnSIDES and ADReCS, in its docstring |

Further reading: [SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) for the
harness and every measurement; [SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md)
for why these keys were chosen, the literature behind them and what ATC gets
wrong; [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), 2026-10-13 and 2026-10-14,
for what went wrong building the FDA and OnSIDES backfills.
