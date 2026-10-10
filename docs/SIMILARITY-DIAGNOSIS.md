# What the ranking gets right, what it gets wrong, and why

Recorded 2026-09-17. **Nothing here is adopted.** Every number is measured
against the active `db/cohort1.db` and the exported `viz/graph.data.js`; the
scripts are in [analysis/probe/](../analysis/probe/README.md) and are read-only.

The question this answers: the similarity ranking is graded against ATC level-4
classes, and that grade is a proxy nobody chose for the purpose. So the grade
was put beside a second thing — a set of drug relationships that are settled
pharmacology — to find out where the ranking is actually good, where it is bad,
and whether the grade is telling us about the ranking or about itself.

The short version:

- **The published grade understates the ranking.** The same `sharedTargets`,
  graded against every ATC level rather than N alone, goes from top-1 37.5% to
  **44.5%**. The N-only key is the hardest slice, and the build fills it that
  way for a reason that has nothing to do with grading.
- **The ranking is right about most textbook pairs** — 29 of 35 canonical
  mechanism relationships land in the top 5, 16 of them at rank 1.
- **Four defects account for most of what is left**, and three of them are one
  underlying problem: a protein's identity is split across several ChEMBL target
  records, and neither the score nor D15 puts it back together.
- **The worst single error in the catalogue is morphine's nearest neighbour
  being naltrexone** — the drug given to reverse it.

---

## 1. The answer key is a slice, and it is the hard slice

`molecules.atc_level5` is filled by `scripts/cohort/selection.py`, whose query
ends `WHERE a.level1 = 'N'`. That clause is the **route_atc_n admission test**:
it decides who gets into the cohort. The similarity harness then reads the same
column as its answer key, so the key silently inherits an admission filter that
was never written to define one.

Removing it costs nothing — no rebuild, no new source, the codes are already in
ChEMBL for molecules the catalogue already holds:

| | molecules | classes | scoreable | unanswerable | top-1 | top-5 | MRR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ATC N only *(graded today)* | 395 | 64 | 283 | 112 | 37.5% | 66.1% | 0.5035 |
| every ATC level | 759 | 212 | 544 | 215 | **44.5%** | 71.3% | 0.5630 |
| non-N classes only | 386 | 148 | 278 | 108 | **49.6%** | 74.5% | 0.6043 |

1,055 of the 1,331 catalogue entries carry at least one ATC code; only 544 carry
an **N** one. The rest are there through the indication route and their
classifications — C 89, A 110, M 63, L 87 — are simply not stored.

**The gap is a real finding about the pharmacology, not just about the key.**
Non-N classes are easier because they are mostly single-mechanism: statins,
sartans, PPIs and ACE inhibitors are 100% top-1, and each is a class where one
shared target settles the question. ATC N is harder because CNS drugs are
polypharmacological — a typical antipsychotic carries thirty targets, and
telling two antipsychotics apart from an antipsychotic and an antidepressant
means weighing thirty overlaps rather than finding one. So the ranking is worst
in exactly the domain this project is for, and the headline grade has been
reporting that honestly while looking like a worse instrument than it is.

**Two cautions before adopting the wider key.** Some non-N classes are grouped
by *use or route* rather than mechanism, which is the same defect the `X`
exclusion already handles: `V03AB` (antidotes) puts naloxone, physostigmine,
alcohol and acetylcysteine in one class, and `B05XA` (electrolytes) and `A11HA`
(vitamins) are not mechanism claims at all. And several classes are 100% for an
uninteresting reason — `L04AG`, `L03AB` and `H01AC` are monoclonals and
interferons whose target lists are so short that a classmate is most of the
list. A wider key wants a documented exclusion list in the spirit of the `X`
rule, and the biologics counted apart.

---

## 2. What the probe set is, and why it is allowed to exist

[`analysis/probe/probes.mjs`](../analysis/probe/probes.mjs) is 50 drug
relationships written down by hand: the SSRIs, the tricyclics, the triptans, the
benzodiazepines, the opioids, the cholinesterase inhibitors, and so on. Each
names a query molecule, the partners that would be a right answer, and why.

Hand-writing an answer key is exactly what
[docs/SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §3 refuses to do, so the
distinction matters. That objection is about **optimising**: hand-picking the
key that judges six hand-picked constants lets the grade be made to say
anything. It does not apply to asking *"is the ranking right about morphine and
oxycodone, and if not, why not"* — a question the aggregate cannot answer at
all, because a rate over 283 molecules never says which 283 or what went wrong.

So the probe set is a diagnostic and never a tuning target. Nothing in it is
summed into a number that a constant is then swept against, and the runner says
so where it prints its counts.

### What it found

**29 of 35 mechanism probes land in the top 5; 16 are rank 1.** Every one of
these is the ranking's own answer, unprompted:

| | | |
| --- | --- | --- |
| caffeine → theophylline | 1 | the methylxanthines |
| fluoxetine → citalopram | 1 | SSRIs |
| citalopram → fluoxetine | 1 | SSRIs |
| amitriptyline → clomipramine | 1 | tricyclics |
| donepezil → rivastigmine | 1 | cholinesterase inhibitors |
| sumatriptan → rizatriptan | 1 | triptans |
| ketamine → memantine | 1 | NMDA channel blockers |
| gabapentin → pregabalin | 1 | α2δ ligands |
| pramipexole → ropinirole | 1 | D2/D3 agonists |
| ondansetron → granisetron | 1 | 5-HT3 antagonists |
| thioridazine → chlorpromazine | 1 | phenothiazines |
| propranolol → metoprolol | 1 | beta blockers *(non-N)* |
| atorvastatin → rosuvastatin | 1 | statins *(non-N)* |
| omeprazole → rabeprazole | 1 | PPIs *(non-N)* |

Seven of the eight non-N probes are rank 1, which is the probe-level version of
the table in §1.

The six that miss are where the rest of this document comes from.

---

## 3. One protein, several target records — three defects from one cause

### 3.1 The same receptor counted several times

`OPRK1` and `Oprk1` are the human and rat records of one receptor. D06 keeps
them as separate target identities deliberately, and the viewer's own
`singleProteinByAccession` already returns **null** when two targets hold one
accession, calling them "two species' records of the same protein". But
`sharedTargets` scores them as two shared targets.

**336 gene symbols are carried by more than one target record, over 859 of the
2,577 target rows.** Across every ranked pair involving an ATC-labelled
molecule: **2,426 of 49,134 pairs (4.9%) count at least one receptor twice**,
covering 4,178 rows — 2.0% of all scored rows. It concentrates in exactly the
well-studied aminergic drugs the ATC key is mostly made of: imipramine and
clomipramine read as 43 shared targets, 8 of which are a second species record
of a receptor already counted.

This is the same double-count the family subsumption rule exists to stop, one
axis over.

### 3.2 D15 is blind wherever the two directions are filed apart

> **Fixed on 2026-09-17.** This section measured a prototype and the prototype
> was adopted: the viewer now reads a curated direction at the protein
> (`pooledDirection`), keyed on the accession rather than on the gene symbol.
> Morphine ranks naltrexone 17th of 380 and opens on buprenorphine. What the
> section below describes is the state it was written against, and it is kept
> because the measurement is the argument. The adopted rule and its numbers are
> in [COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) D15. **The decision at the
> end of this section was taken on 2026-09-20**: the demotion is proportional
> and divides by *comparable*. Dividing by *shared* was graded and came out
> below the rule it would replace, because a shared target carrying no curated
> direction is an unknown rather than an agreement, and letting it dilute a
> demotion turns ChEMBL's silence into a defence. The clozapine/apomorphine
> worry below was checked against the answer key and does not hold: none of the
> 167 thinnest demotions is a same-class pair.

**Morphine's nearest neighbour is naltrexone**, at rank 1 of 380. Here is the
whole pair:

```
MORPHINE -> NALTREXONE: rank 1 of 380, score 0.2724
shared 12  comparable 0  opposed 0  all_opposed false

  Opioid receptor                  PROTEIN FAMILY   Rattus       A:-         B:-           subsumed
  Oprm1                            SINGLE PROTEIN   Rattus       A:-         B:-
  OPRM1                            SINGLE PROTEIN   Homo sapiens A:AGONIST   B:-
  OPRD1, OPRK1                     SINGLE PROTEIN   Homo sapiens A:-         B:-
  OPRK1, OPRM1                     SINGLE PROTEIN   Cavia        A:-         B:-
  Opioid receptors; mu/kappa/delta PROTEIN FAMILY   Homo sapiens A:-         B:ANTAGONIST  subsumed
  Oprd1, Oprk1, Oprm1              SINGLE PROTEIN   Mus/Rattus   A:-         B:-
  SLC22A1                          SINGLE PROTEIN   Homo sapiens A:-         B:-
```

Three receptors, filed as twelve shared targets across five species. ChEMBL
curates both directions and they are one row apart: morphine's **AGONIST** on
human mu-opioid (`CHEMBL233`), naltrexone's **ANTAGONIST** on the human
mu/kappa/delta family (`CHEMBL2095181`). They never land on one record, so
`directionAt` returns null on all twelve rows, `comparable` is 0, and the pair
is scored as though nothing were known about direction.

Worse: the family row that carries naltrexone's direction is **subsumed** —
the pair shares every protein in it individually — so it contributes 0 to the
score while being the only row that knows these two are opposites.

CLAUDE.md already records this shape for adenosine and istradefylline and calls
499 "a floor, not a census". This measures the distance to the census.
[`direction_recovery.mjs`](../analysis/probe/direction_recovery.mjs) prototypes
reading a curated action at **the protein** — a SINGLE PROTEIN contributes its
gene symbol, a FAMILY or COMPLEX GROUP contributes all of its components',
species dropped — and comparing molecules there:

| | today | pooled |
| --- | --- | --- |
| pairs D15 can compare at all | 3,637 (7.4%) | 4,664 (9.5%) |
| pairs demoted as entirely opposed | 247 | **535** |

290 pairs are recovered and **two are released** — trimipramine and tolazoline
are both ANTAGONIST at three adrenoceptors and opposed at one, so the one-record
view was quartering a pair that agrees three times out of four. The recovered
ones are led by precisely the errors that matter, highest score first:

```
0.272  MORPHINE / NALTREXONE          0.113  CLOZAPINE / APOMORPHINE
0.268  NALTREXONE / BUPRENORPHINE     0.110  CHLORPROMAZINE / PERGOLIDE
0.257  MORPHINE / NALOXONE            0.109  PERGOLIDE / OLANZAPINE
0.246  NALTREXONE / OXYCODONE         0.107  APOMORPHINE / RISPERIDONE
0.201  FENTANYL / NALTREXONE          0.103  HALOPERIDOL / PERGOLIDE
```

The top block is opioid agonists against their antagonists. The second is
antipsychotics against dopamine agonists — drugs that cause each other's
adverse effect, which is as clean an opposite as pharmacology offers.

This is **not** the D06 merge. Nothing in it changes what a shared target is,
what it weighs, or what the canvas draws; it changes only which two actions get
compared. That is the same argument the viewer already makes for reading
direction at subsumed rows.

**The thing to decide before adopting it.** `all_opposed` divides by
*comparable*, not by *shared*, so clozapine/apomorphine is demoted fourfold on
one comparable protein out of 34 shared. That is already true today; pooling
makes it bite more often. A rule that demoted in proportion to how much of the
shared pharmacology is opposed would be a different, and possibly better,
answer — and it is a decision about what the score claims, not a constant.

### 3.3 Where it also shows: 92.6% of pairs have no direction anywhere

Of the 49,134 pairs, **45,497 (92.6%) share targets on which ChEMBL gives
neither side a curated direction.** D15 is not a weak rule; it is a rule with
almost nothing to read. That is the strongest single argument in this document
for a source that curates *action* rather than affinity — see §5.

---

## 4. Screening panels, which the prevalence discount only half solves

### 4.1 Whole-panel fan-out has no equivalent in the cohort pipeline

**Amlodipine ranks nicardipine 94th of 561.** Its top three neighbours are
terfenadine, pimozide and amitriptyline, sharing 29–30 targets each — ADRB3,
MC4R, HTR3A, KCNK2, a long tail of GPCRs — every one of them Preliminary and
mid-prevalence. None of those molecules resemble amlodipine. They were all run
through **one broad off-target screening campaign**, and sharing thirty results
from one panel is one fact, not thirty.

`prevalenceWeight` cannot catch this. It discounts a target *everything* hits;
it cannot see that a *set* of targets is one experiment run on a subset of the
catalogue. The legacy pipeline solved exactly this with `fanoutRef` — "133 of
the 654 edges fall into 29 such groups" — and **the cohort pipeline has no
equivalent at any layer.** It is not in the Not-done list either.
`observations` carries the assay id, so the signal is available.

### 4.2 The discount cannot tell a safety screen from a mechanism

The prevalence discount treats every much-measured target alike. It should not:

| target | molecules | curated mechanisms |
| --- | --- | --- |
| KCNH2 (hERG) | 666 | **0** |
| Alpha-2A adrenergic | 666 | **0** |
| Adenosine A3 | 650 | **0** |
| Alpha-1A adrenergic | 637 | **0** |
| Mu-opioid receptor | 687 | 27 |
| Noradrenaline transporter | 678 | 34 |
| Serotonin transporter | 675 | 25 |

SERT is measured as often as hERG and is discounted as hard — but SERT is the
actual mechanism of a large class and hERG is a liability assay. The
curated-mechanism ratio separates them completely at the top of the prevalence
distribution: exactly 0 against 25–34.

This is the **conditioning half** of the prevalence proposal that CLAUDE.md
records as not done, on the grounds that "the ratio is a claim about why, and it
needs the argument this item never made for it". The table above is the
beginning of that argument. The caveat in CLAUDE.md stands and gets sharper: a
term rewarding curation is graded by an ATC key that is partly *defined* by
mechanism, so this one in particular should not be adopted on the ATC grade
alone.

### 4.3 A pair scored only on a safety panel is graded as a ranking failure

**Phenobarbital ranks pentobarbital 50th, and its top answer is dolasetron.**
The reason is not the ranking. Phenobarbital carries about 110 claims in this
build, nearly all `limited_or_unresolved`, and they are a standard broad panel —
every GPCR, every CYP, a row of kinases. **Not one of them is at GABA-A**, which
is its entire mechanism. After the tier filter, phenobarbital's whole visible
pharmacology is the brain sodium-channel family and KCNH2: two safety-screen
targets. Its only shared target with pentobarbital is hERG.

The harness already separates "ranked badly" from "unanswerable". This is a
third case it has no name for: **answerable only through a screening panel.**
The pair shares something, so it is scored, so it counts as a ranking failure —
when there was never a right answer available to find. Under a prevalence
threshold of 0.35 (a target on roughly a tenth of the visible catalogue),
**26,934 of 49,134 pairs (54.8%) share nothing else**, 9,789 of them between two
ATC-labelled molecules.

Reporting that third category would make the grade mean what it says. It would
also, honestly, lower the apparent size of the problem the constants are being
blamed for.

---

## 5. What this says about cohort 2

The evidence points somewhere specific, and it is **not** "add more molecules by
the same rule".

Every failure above is a failure of the *target* side, not the molecule side.
Barbiturates fail because GABA-A claims are missing, not because barbiturates
are missing. Amlodipine fails because a screening panel is undifferentiated from
mechanism. D15 fails because 92.6% of pairs carry no curated action. Admitting
another few hundred clinical molecules under the existing selection policy adds
more rows of the same broad panels — more of what already dominates the picture
— without adding one curated direction.

So the priority order the measurements support:

**First, the things that need no new source at all.** Extending the answer key
past ATC N, reading direction at the protein, collapsing orthologue duplicates,
and reporting screening-only pairs as their own category are all computable from
`db/cohort1.db` as it stands. Three of the four are scoring changes and want the
harness run before and after; the first is a change to the instrument.

**Then GtoPdb, and for the reason the measurements give rather than the reason
the brainstorm gave.**
[docs/MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md) already
ranks IUPHAR/BPS first among new pharmacology sources. What this diagnosis adds
is *which* of its fields is the one worth having: **the curated action**. GtoPdb
curates ligand→target with a direction and a primary-target flag, on the target
families this project is about, and the single largest measured hole here is
that ChEMBL leaves direction null on 92.6% of pairs. It would also give
barbiturates and the general anaesthetics a mechanism, which ChEMBL's
binding-assay record structurally cannot. Its access route changed in
September 2026 and needs checking before any import — the brainstorm records
this.

**And a molecule-side gap worth naming, because it is small and sharp.**
Flumazenil is an approved drug, is in ChEMBL as `CHEMBL407` at phase 4, and is
**not in the catalogue at all** — it is an antidote, ATC `V03AB`, and its
indication is benzodiazepine overdose. The molecules that best *define*
direction at CNS targets are disproportionately antagonists, antidotes and
reversal agents, and the clinical selection rule filters on therapeutic use,
which is precisely the axis on which those differ from the drugs they reverse.
That is a much narrower and better-evidenced boundary argument than the ones in
[docs/COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md), and it is testable:
the probe set already contains the pairs it would fix.

**A second answer key remains the open methodological item.** FDA Established
Pharmacologic Class via DailyMed is still the right candidate, for the reason
CLAUDE.md gives — an explicit mechanism label not derived from ChEMBL. Extending
ATC past N is cheaper and is not a substitute: it is the same authority, with
the same bias toward classes ChEMBL curates well.

---

## 6. Recommendations, ordered by evidence behind them

Nothing below is adopted. Each is stated with what would confirm it.

1. **Extend the answer key past ATC N**, with a documented exclusion for
   use-and-route classes in the spirit of the `X` rule, and biologics counted
   apart. It is the instrument, not the ranking, so it changes no output; it
   takes the graded set from 283 molecules to 544. *Measured in §1.*
2. **Read curated direction at the protein rather than the target record.**
   Doubles D15's demotions, and the pairs it catches are led by
   morphine/naltrexone. Decide the `all_opposed` denominator question in §3.2
   at the same time. *Measured in §3.2; re-grade before adopting.*
3. **Report "scored only through screening targets" as a third category** beside
   scoreable and unanswerable. It is a change to what the grade reports, not to
   what the page does, and it stops 54.8% of pairs being counted as ranking
   failures they never had a chance at. *Measured in §4.3.*
4. **Collapse orthologue duplicates into one shared target.** Smallest measured
   effect of the four (2.0% of scored rows) and the clearest in principle: the
   viewer already refuses to treat two species' records as one protein
   elsewhere. *Measured in §3.1.*
5. **Investigate assay fan-out in the cohort pipeline.** Nothing is measured
   here beyond the amlodipine case and the fact that the legacy pipeline needed
   it; the first step is to count how many shared-target rows come from a single
   assay, which `observations` can answer. *Not measured — this is the one item
   here that is still a hypothesis.*
6. **Condition the prevalence discount on the curated-mechanism ratio**, last of
   the six and deliberately so. The separation is clean (§4.2) and the judge is
   biased in its favour, which is the one combination this project has already
   decided not to trust. It needs the second answer key first.

None of the six original scoring constants is on this list. The sweep's finding
about the curated/replicated gap is unchanged and unaddressed by any of them.

---

## 7. Running it

```bash
node analysis/probe/run.mjs                    # every probe, one line each
node analysis/probe/run.mjs --detail 10        # the ten worst, with diagnosis
node analysis/probe/run.mjs --only MORPHINE    # one probe, with diagnosis
node analysis/probe/pair.mjs MORPHINE NALTREXONE   # one pair, every shared row
node analysis/probe/structure.mjs              # the three counts in §3.1, §4.3, §3.3
node analysis/probe/direction_recovery.mjs     # the prototype in §3.2

python3 analysis/probe/dump_atc.py             # ATC codes at every level -> JSON
node analysis/probe/regrade.mjs                # the three-key table in §1
node analysis/probe/keystats.mjs               # what the current key is made of
```

All of them read `viz/graph.data.js` and report a missing payload rather than a
bad grade when there is no build. `dump_atc.py` and `atc_coverage.py` open
ChEMBL `mode=ro` and the cohort database read-only. Nothing here writes to
either database or to the viewer.
