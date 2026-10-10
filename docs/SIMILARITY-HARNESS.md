# The similarity harness, explained from scratch

A proposal for finding 2 of the 2026-09-17 review: *the deliverable rests on six
unvalidated constants*. Written plainly, because the method is simple and the
first explanation of it was not.

**Sections 1-7 describe a measuring instrument and what a prototype of it
measured; nothing in them was adopted.** Sections 8 and 9 are what happened
next: the instrument found something the sweep was not built to look for, and
three changes were adopted on the strength of it. **None of the six constants
was one of them** — they are still chosen by argument and still unvalidated.

---

## 1. The problem, in one paragraph

The page's whole job is to answer one question: *which molecules act alike?*
It answers by scoring every pair of molecules and sorting the list. That score
is computed from six numbers someone picked by hand — 1.0, 0.9, 0.75, 0.5, 0.5,
0.25 — each defended in prose and none of them measured.

So the honest state of things is: **we do not know if the ranking is good.** Not
"we think it's good" or "it looks right on caffeine" — we have no way to tell.
And worse, we have no way to tell whether a *change* to it helps or hurts. Every
future argument about these numbers is unwinnable, because both sides only have
arguments.

A harness is the thing that ends that. It is not a feature. Nobody using the
page ever sees it. It exists so that the next sentence can be "we changed 0.75
to 1.0 and the ranking got better by this much" instead of "we changed 0.75 to
1.0 because it felt more principled".

---

## 2. The idea, explained simply

Imagine the page is a machine with one button. You feed it a drug and it prints
a list: *here are the other drugs most like this one, best first.*

You want to know if the machine is any good. You can't check every answer by
hand — there are 1,331 drugs and nearly a million pairs.

But here is the trick: **for some drugs, we already know the right answer.**

Everybody knows amitriptyline and imipramine are the same kind of drug. They're
both tricyclic antidepressants. If you feed the machine amitriptyline and
imipramine is nowhere near the top of the list, the machine is wrong — and you
didn't need to understand the score to know that.

So: collect a pile of drugs whose "right answer" we already know. Feed each one
to the machine. Count how often the machine puts a known-correct drug near the
top. **That count is the grade.**

Once you have a grade, everything else follows. Change a constant, re-grade. Did
the number go up or down? That is the entire method.

---

## 3. Where the answer key comes from

The obvious move is to write the answer key by hand: "the four cholinesterase
inhibitors go together, haloperidol and clozapine go together, the
methylxanthines go together." The docs already say all of those things.

**That would be a mistake**, and it's worth being clear why. The complaint is
that six numbers were chosen by hand. Fixing it by hand-choosing the answer key
that judges those six numbers is the same problem wearing a hat. You would be
able to make the grade say anything by picking which classes to include.

So the answer key should be *generated*, from something already in the database
that was written down by somebody else for another purpose.

**That thing is the ATC code.** ATC is the WHO's filing system for drugs. Every
drug gets a code like `N06AA09` (amitriptyline), and the code is a nested
address:

```
N  06  A  A  09
│  │   │  │  └── the specific drug
│  │   │  └───── "non-selective monoamine reuptake inhibitors"  ← level 4
│  │   └──────── antidepressants
│  └──────────── psychoanaleptics
└─────────────── nervous system
```

**Level 4 is the useful one.** It is where the WHO groups drugs by how they
work. Everything in `N06AA` is a tricyclic antidepressant. Everything in `N05BA`
is a benzodiazepine. These groupings were made by pharmacologists who had never
heard of this project, which is exactly what makes them a fair test.

The database already stores this, in `molecules.atc_level5`. Chop the code to
five characters and you have the class. No new data, no lookups, no curation.

That gives **395 molecules across 64 classes**, which is the answer key.

### One exclusion that matters

ATC has junk-drawer classes. The fourth letter `X` means "other" — `N06AX` is
literally *"other antidepressants"*, and at 29 members it is the biggest class
there is.

But "other antidepressants" is a group **defined by not sharing a mechanism**.
Mirtazapine and bupropion are both in it and they work completely differently.
If the machine ranked them as similar, that would be a *mistake* — and grading
against `N06AX` would award points for it.

So all `X` classes are dropped. (My first prototype checked the wrong character
and let them through; fixing it moved the set from 514 molecules to 395. Worth
mentioning because it's the kind of error that quietly inflates a grade.)

---

## 4. How the grading works

For each drug in the answer key:

1. Ask the page for its similarity list.
2. Walk down the list until you hit a drug from the same ATC class.
3. Write down **how far down you had to go.** That's the rank.

Rank 1 means the machine's top answer was a classmate — perfect. Rank 50 means
you had to scroll past 49 wrong answers first.

Then summarise across all of them:

- **top-1** — how often was the very first answer a classmate?
- **top-5** — how often was a classmate in the first five?
- **MRR** — "mean reciprocal rank". Score each drug as `1 ÷ rank`, then average.
  Rank 1 scores 1.0, rank 2 scores 0.5, rank 10 scores 0.1. It's just a way of
  saying "close counts for something, and closer counts for more."

**Why MRR and not just top-1?** Because top-1 is blind to most improvement. If a
change moves a drug from rank 50 to rank 8, top-1 doesn't budge — but the
ranking genuinely got better, and you want the instrument to notice. MRR notices.

### The one subtle bit: "wrong" is not the same as "unanswerable"

Sometimes a drug's classmates aren't in its similarity list **at all** — not low
down, just absent. This happens when ChEMBL has no shared target between them.
The page isn't ranking them badly; it has nothing to rank.

Those get excluded from the grade and counted separately. **This is the most
important design decision in the whole harness**, and here is why:

Several of the constants affect *which claims are eligible* at all. If you let
unanswerable drugs into the denominator, a constant that quietly makes more
things eligible will improve the grade — not by ranking better, but by making
more questions answerable. You would then "tune" the score toward whatever
maximises coverage, and never notice.

So the report gives two numbers side by side: **217 scoreable, 178
unanswerable.** The second one is a fact about ChEMBL's coverage. Only the first
one is a fact about the ranking.

---

## 5. How the prototype is wired

One rule above all: **the harness calls the page's own code.** It does not
reimplement the scoring. A reimplementation starts identical and drifts, and
then you're measuring a copy while shipping an original.

`tests/cohort_harness.mjs` already does exactly the right thing — it pulls the
inline `<script>` out of `viz/index.html` and runs it in a Node sandbox. It
turns out `loadViewer(data)` will happily take the *real* `viz/graph.data.js`
instead of a test fixture. So:

```
viz/graph.data.js  ──►  loadViewer()  ──►  sharedTargets(drug)  ──►  grade
   (real payload)       (existing harness)   (the page's own function)
```

Loading the real 4.39 MB payload takes 103 ms. Grading all 217 drugs takes
54 ms. The whole thing runs offline with no dependencies.

### Turning the knobs

To test a constant you need to change it and re-grade. Two of the six are easy
and four are not, for a boring JavaScript reason worth writing down:

- `evidenceWeight` is a `function` declaration, so it lands on the sandbox's
  global object and can simply be replaced from outside.
- `TARGET_WEIGHT` and `OPPOSED_PAIR_FACTOR` are `const`. A top-level `const`
  lives in the script's *lexical* scope, which is not reachable from outside the
  sandbox at all.

So the sweep patches the source text before running it — find
`const OPPOSED_PAIR_FACTOR = 0.25;`, swap the number, run that version in a
fresh sandbox. This needs `makeSandbox` exported from `tests/cohort_harness.mjs`
(currently it is module-private). **That one-line export is the only change the
harness needs to existing code.**

---

## 6. What the prototype actually found

Baseline, current constants:

```
scoreable 217   unanswerable 178
top-1  35.9%    top-5  64.1%    top-10  75.6%    MRR  0.4985
```

Then each constant swept one at a time.

### Five of the six barely matter

`TARGET_WEIGHT` for families and complex groups, currently 0.5:

| value | MRR | change |
| --- | --- | --- |
| 0.00 | 0.4985 | ±0.0000 |
| 0.25 | 0.4984 | −0.0001 |
| **0.50 (current)** | **0.4985** | — |
| 0.75 | 0.4985 | +0.0000 |
| 1.00 | 0.5016 | +0.0031 |

Flat from 0 to 0.75. Setting it to **zero** — ignoring family overlaps entirely —
grades the same as the current 0.5. The only value that changes anything is 1.0,
where a family stops being worth less than a single protein. So the question is
categorical ("is a family worth less, yes or no?") and the specific magnitude is
not a question at all.

`OPPOSED_PAIR_FACTOR`, currently 0.25:

| value | MRR | change |
| --- | --- | --- |
| 0.00 | 0.4985 | ±0.0000 |
| **0.25 (current)** | **0.4985** | — |
| 0.50 | 0.4982 | −0.0003 |
| 1.00 (disabled) | 0.4925 | −0.0060 |

Good news: **D15 earns its place.** Turning the opposed-pair demotion off is the
worst setting tested. And anything from 0 to 0.25 grades identically, so the
argument for "0.25 rather than 0, because the two molecules do genuinely share
the target" is a free choice — it costs nothing measurable, so keep it.

### One of the six matters, and is set to the wrong value

`evidenceWeight`'s curated-only step, currently 0.75:

| value | top-1 | MRR | change |
| --- | --- | --- | --- |
| 0.50 | 35.9% | 0.4981 | −0.0004 |
| **0.75 (current)** | **35.9%** | **0.4985** | — |
| 0.90 | 35.9% | 0.5010 | +0.0026 |
| 0.95 | 36.4% | 0.5021 | +0.0036 |
| 1.00 | **38.2%** | 0.5134 | **+0.0149** |

Monotonic, and by far the biggest effect measured anywhere.

### The example that explains why

Here is meperidine's (pethidine's) similarity list as the page ranks it today:

| | rank | score | what they share |
| --- | --- | --- | --- |
| **AMITRIPTYLINE** | **1** | 0.90 | KCNH2 — the hERG cardiac safety channel |
| FENTANYL | 50 | 0.75 | the mu-opioid receptor |

Meperidine is an opioid. Its top-ranked "most similar drug" is an
antidepressant, and the only thing they have in common is a **cardiac safety
screen that every drug candidate gets put through.** Its actual opioid
classmate sits at rank 50.

The cause is exactly the constant above. hERG scores 0.90 because the finding is
replicated across publications. Mu-opioid scores 0.75 because it is curated but
not replicated. **The current weights rank "lots of people measured it" above
"ChEMBL says this is the mechanism"** — and screening panels are, by
construction, the most-measured things in the database.

Raise curated to 1.0 and meperidine goes 50 → 8, fentanyl goes 13 → 1,
levobupivacaine 19 → 1.

This is also the cleanest argument for doing finding 2 before finding 1. That
example is a finding-1 problem — a screening panel masquerading as shared
pharmacology — and it was found by the finding-2 harness, in a form no amount of
arguing would have produced.

### Why this is not yet a recommendation

Two reasons to sweep the full grid before changing anything.

**It isn't a clean win.** 42 drugs improve, **24 get worse** — levosulpiride
falls from rank 3 to 28, triflupromazine from 15 to 43. 151 don't move.

**The test is biased toward the answer it gave.** ATC level-4 classes are partly
*defined* by mechanism, and ChEMBL curates mechanisms most thoroughly for
well-known drugs. So a metric built on ATC will always somewhat flatter a
constant that rewards curation. That bias has to be reported next to the number,
not discovered later — and it matters even more for finding 1, whose proposed
curated-mechanism-ratio term would be graded by the same friendly judge.

---

## 7. What was built

All four, on `worktree-cohort1-impl`.

| | |
| --- | --- |
| `analysis/similarity_harness/harness.mjs` | answer key, grading, constant patching |
| `analysis/similarity_harness/evaluate.mjs` | the grade, worst-ranked, per-class breakdown, `--json` |
| `analysis/similarity_harness/sweep.mjs` | every constant over a grid, `--movers` |
| `tests/similarity_harness.test.mjs` | 7 tests holding the grade to a floor |
| `tests/cohort_harness.mjs` | `makeSandbox` exported — the one change to existing code |
| `scripts/cohort/status.py` | the grade generated into `## Status` |

```bash
node analysis/similarity_harness/evaluate.mjs
node analysis/similarity_harness/sweep.mjs evidence_curated --movers
```

Both read `viz/graph.data.js`, which is generated and gitignored; without it
they report a missing payload rather than grading nothing.

### What the tests actually hold

Pinning MRR to a floor is the obvious half and the less important one. The
floors are deliberately slack (MRR 0.47 against a measured 0.4985) because they
exist to catch a regression, not to pin a number that moves whenever the
catalogue is rebuilt.

The half that matters is that **the instrument cannot fail silently.** A sweep
whose regex has stopped matching would print the baseline under every label — a
table of numbers that agree because nothing was ever varied, which reads exactly
like a constant that does not matter. So one test asserts every constant's patch
still matches `viz/index.html` *and* writes a different value, and another
asserts end-to-end that disabling `OPPOSED_PAIR_FACTOR` moves the grade. That
test needs no build, because `viz/index.html` is checked in.

The same reasoning put the guard in `patchConstant` itself. It fired on the
first run — correctly, on the wrong condition: patching a constant to the value
it already holds is a legitimate no-op and is the first row of every grid. The
test is whether the pattern *matched*, not whether the text changed.

### Two more findings from the full sweep

Running all six rather than the three I had prototyped turned up two things.

**The Preliminary weight is unreachable.** `evidenceWeight`'s 0.5 branch grades
identically at 0.25, 0.5 and 0.75 — because the default tier filter admits only
Supported claims, so the branch is never taken. The viewer's own comment says
exactly this (`// Preliminary, only reachable when that filter is on`). The
harness independently confirmed a code comment, which is a reassuring thing for
a new instrument to do. *(This stopped being true in section 9: the default tier
filter now admits Preliminary claims, so the branch is live. It was re-swept the
moment it became reachable — see below.)*

**The real finding is a gap, not a value.** I had reported this as "the curated
step is set too low". The full sweep says it more precisely: what the ranking can
feel is the *distance between* curated (0.75) and replicated (0.9), and closing
it from either side helps. Raising curated to 1.0 gains +0.0149. *Lowering*
replicated to 0.5 gains +0.0036. Raising replicated to 1.0 — widening the gap —
costs −0.0289, the largest single loss measured anywhere.

So the thing to decide is not "what should 0.75 be" but "should a replicated
measurement outrank a curated mechanism at all, and by how much" — which is a
question about what the page is claiming, and a much better question to be
arguing about.

## 8. What the sweep could not see

The six-constant sweep reported five constants as inert. That reading was
correct and the explanation for it was missing, and the explanation turns out to
matter more than the sweep did.

**The score only takes 73 distinct values across the whole catalogue.** It is a
sum of a handful of discrete weights over a small number of shared targets, so
it lands on the same value again and again:

```
lists with a tied top score      84%   (median tie 7 molecules, largest 58)
top-1 if every top tie broke our way   78.3%   against an actual 35.9%
```

Inside a tie the sort falls through to `localeCompare` on the name. Nine of the
twelve commonest "most similar drug" answers in the whole catalogue began with
the letter **A**; acamprosate alone won 30 of 395 queries. Roughly half the
achievable accuracy was sitting in tie-breaking rather than in weighting.

That is also why five constants graded inert: **moving a weight cannot break a
tie when both sides of the comparison move with it.** The sweep was measuring
the wrong dimension — not because it was built wrong, but because the thing it
was built to vary was not the thing in the way.

The cause upstream is sparsity. Under the default tier and basis filters, **the
median labelled molecule reached exactly one target.** One target is a set, not
a ranking; nothing can order the 58 molecules that all touch it.

## 9. What was adopted, and what it measured

Three changes, landed together because none of them is worth much alone.

**A prevalence discount** (`prevalenceWeight`). Each shared target is weighted by
`log(1 + n/df) / log(1 + n)`, where `df` is how many molecules in the current
picture reach it. A target nearly everything is measured at contributes nearly
nothing; a target unique to one pair contributes 1. The smoothing is load-bearing
and the tests found it: unsmoothed, a target every visible molecule reaches
scores exactly 0 and takes the whole pair to 0, which says two molecules share
nothing when they demonstrably share a protein.

**Cosine normalisation.** The pair's total is divided by `sqrt(deg(a) · deg(b))`,
so the score is the fraction of what the two molecules do that is shared rather
than a count of overlaps.

**The tier and basis defaults opened** to Supported-and-Preliminary and to both
assignment layers, which takes the median entry from one target to five.

### The numbers

On the 217 molecules answerable under the *old* defaults — a fixed question set,
so coverage cannot flatter the result:

| | top-1 | MRR |
| --- | --- | --- |
| before | 35.9% | 0.4985 |
| filters opened, old score | 30.4% | 0.4421 |
| **all three** | **42.4%** | **0.5625** |

The middle row is the reason the three shipped together: **more evidence, scored
flat, makes the ranking worse.** The added claims are weaker and more
promiscuous, and a score that cannot tell a rare target from a screening panel
spends them badly.

Across the whole labelled set the change buys coverage as well as ordering —
**283 scoreable molecules against 217**, at 37.5% top-1 and MRR 0.5035. Tied top
scores fall from 84% to 20% and the largest tie from 58 molecules to 14.

For scale: the best single-constant change the sweep found was +0.0149 MRR. This
is +0.064 on the same question set.

### The two filters do not decompose

Holding the new scoring constant and moving only the filter defaults, on the same
fixed question set:

| tier | basis | top-1 | MRR |
| --- | --- | --- | --- |
| Supported | direct human | 38.2% | 0.5114 |
| + Preliminary | direct human | 33.2% | 0.4772 |
| Supported | both layers | 35.5% | 0.4958 |
| **+ Preliminary** | **both layers** | **42.4%** | **0.5625** |

**Opening either one alone is worse than opening neither.** Only the pair wins,
and it wins by more than the two apparent losses combined. The likely reason is
that a partial opening adds claims asymmetrically — a molecule gains targets
while the molecules it would be compared against do not, so the prevalence and
degree statistics that the two new terms read are computed over a picture that
is inconsistent with itself.

Whatever the mechanism, the practical consequence is the one that matters here:
there is no conservative middle setting to retreat to. "Open the tier but keep
assignments strict" is the worst of the four, not a compromise. That is worth
knowing before anyone proposes it as one.

### It reads correctly without being told to

| | before | after |
| --- | --- | --- |
| fluoxetine | cocaine, desipramine, duloxetine | **citalopram, sertraline, imipramine** |
| haloperidol | aripiprazole, clozapine, olanzapine | **clozapine**, olanzapine, risperidone |
| donepezil | curcumin, galantamine, neostigmine | **rivastigmine, galantamine, physostigmine** |
| tacrine | memantine, donepezil, ethopropazine | **physostigmine, galantamine, rivastigmine** |
| caffeine | theophylline, istradefylline, tozadenant | *unchanged* |

Fluoxetine finding the other SSRIs, and the cholinesterase inhibitors finding
each other, are the answers a pharmacologist would give. Caffeine being
unchanged is the check that matters most: the correction is aimed at promiscuous
targets and over-studied molecules, and it leaves the case this project has
always got right alone.

### What was tried and not adopted

**Affinity weighting.** Each overlap weighted by the weaker of the pair's two
median affinities, `median_nm` being already in the startup payload. It graded
*below* the unweighted score when measured alongside it in the same prototype
run (MRR 0.5175 against 0.5618) and was dropped. The data is there; the formulation is wrong. A curated claim carries no
measurement at all, so it has to be held neutral rather than penalised, and that
asymmetry is probably where the term goes wrong.

**None of the six original constants was changed.** The +0.0149 available from
raising the curated weight is still on the table and still unclaimed, for the
reason section 6 gives: 24 of 217 molecules get worse, and ATC flatters
curation.

### The constants were inert because the score was coarse

Re-sweeping all six under the new defaults is the cleanest confirmation that the
diagnosis in section 8 was right. **Four of the six now move where five of six
were flat.**

| constant | current | best on grid | Δ MRR |
| --- | --- | --- | --- |
| `TARGET_WEIGHT`, family / complex group | 0.5 | 0.75 | +0.0078 |
| `OPPOSED_PAIR_FACTOR` | 0.25 | 0 | +0.0009 |
| `evidenceWeight`, curated + replicated | 1.0 | 1.0 | — |
| `evidenceWeight`, replicated only | 0.9 | 0.5 | **+0.0202** |
| `evidenceWeight`, curated only | 0.75 | 1.0 | +0.0068 |
| `evidenceWeight`, Preliminary | 0.5 | 0.5 | — |

The family weight was flat from 0.0 to 0.75 before and is not flat now. A
constant cannot be measured through a score with 73 values and 84% ties; giving
the score resolution is what made the instrument able to see them at all.

Two things worth noting. **The Preliminary weight became load-bearing the moment
the tier default opened**, having been unreachable and therefore unvalidated
when it was chosen — and 0.5 turns out to be the best of its grid, with 0.25
costing −0.0158 and 0.75 costing −0.0072. A number chosen by argument survived
its first real test. And **`OPPOSED_PAIR_FACTOR` still earns its place**:
disabling D15 entirely is still the worst setting on that row at −0.0059.

The shape of the one live finding is unchanged from section 6. It is still the
*gap* between a curated claim and a replicated one, it is still the largest
effect on the board, and closing it from the replication side is now worth
+0.0202. **It is still not adopted**, for the reason it was not adopted before:
ATC flatters curation, and this is precisely a term that rewards curation.

### The caveat, sharpened

An ATC-shaped answer key structurally flatters any term that rewards curation.
**Neither of the two adopted terms rewards curation** — prevalence is a fact
about how much a target has been measured and normalisation is a fact about how
much a molecule has been measured — which is the one reason to trust this result
more than the constant sweep's.

What it still cannot answer is whether ATC is the right judge at all. That needs
a second, independent answer key. The best candidate is the FDA's Established
Pharmacologic Class via DailyMed: an explicit mechanism label, freely available,
and not derived from ChEMBL. Until there is one, every number in this document
is one proxy's opinion.

## 10. A second judge: MeSH pharmacological actions (2026-09-26)

Section 9 ends by saying every number here is one proxy's opinion. There is now
a second proxy. `scripts/resolve_cohort_pharm_actions.py` backfills the MeSH
pharmacological actions NLM's indexers record for each drug. They come from the
literature and not from ChEMBL, and they are linked to our molecules through
PubChem by InChIKey. `meshActionSet` in `harness.mjs` turns them into an answer
key, and `--key mesh` on `evaluate.mjs` and `sweep.mjs` grades against it.

Two molecules are classmates when they share an action they are *directly*
indexed with. Actions shallower than depth 5 in the MeSH tree are dropped
("Central Nervous System Agents", "Enzyme Inhibitors"), for the reason the ATC
key drops its `X` classes: those are headings, not shared mechanisms. It is
not the FDA's Established Pharmacologic Class this section used to name as the
candidate. It has the property that mattered, independence from ChEMBL, and it
was the one to hand.

### The grade

| judge | graded | top-1 | top-5 | top-10 | MRR |
|---|---|---|---|---|---|
| ATC level 4 | 283 molecules, 64 classes | 38.2% | 66.8% | 76.3% | 0.5105 |
| MeSH actions | 586 molecules, 175 classes | 46.1% | 76.5% | 85.2% | 0.5987 |

The MeSH row was re-measured the same day, after the action backfill began
setting aside actions PubChem had attached from a different substance. The
cases were a brand name or code shared by two drugs, and a combination
product's actions reaching one ingredient. That removed 11 action links on 6
molecules, and tafamidis stopped being classmates with the glucocorticoids.
Before, the row read 588 molecules, 176 classes, 45.9% / 76.2% / 85.0% / 0.5970.
The key got slightly smaller and slightly easier, which is what removing wrong
classmates should do.

The two rows are **not** a like-for-like comparison, and the higher number is
not "the ranking is better than we thought". MeSH classes are broader
(Anticonvulsants has 57 members), and a molecule indexed with several actions
has several sets of classmates, so a hit is easier to score. What the row does
show is that a judge not built from ChEMBL finds the ranking far better than
chance, over twice as many molecules as ATC can grade.

### What the two judges agree on

The sweep was run against both keys, one constant at a time, on the same build.
The MeSH column was re-run after the correction above, and one figure moved,
by 0.0001:

| constant | ATC judge | MeSH judge |
|---|---|---|
| `OPPOSED_PAIR_FACTOR` 1.0 (D15 off) | −0.0130 | −0.0156 |
| curated-only weight 0.75 → 1.0 | +0.0050 | +0.0123 |
| replicated-only weight 0.9 → 0.75 | +0.0080 | +0.0042 |
| family weight 0.5 → 1.0 | +0.0035 | +0.0172 |
| Preliminary weight 0.5 → 0.25 | −0.0176 | +0.0082 |

**D15 is confirmed by a second judge.** Switching off the opposite-direction
demotion is the worst setting on its row under both.

**The one live finding survives.** Section 6's finding was that the ranking
wants the gap between a curated claim (0.75) and a replicated one (0.9) closed.
The caveat against acting on it was that ATC flatters curation. A judge from
outside ChEMBL agrees on the direction: raising the curated weight helps under
both, and more under MeSH. That weakens the caveat without removing it. Many
MeSH actions are themselves mechanisms ("Serotonin Uptake Inhibitors"), so this
judge also rewards what curation records. **Nothing was changed.** The numbers
are recorded so the decision can be made against two judges rather than one.

**The Preliminary weight is judge-dependent**, helping under one and hurting
under the other, and should not be moved on either's say-so. The family weight
points the same way under both but by amounts four times apart.
