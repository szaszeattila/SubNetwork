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

**Level 4 is the useful one.** Everything in `N06AA` is a tricyclic
antidepressant. Everything in `N05BA` is a benzodiazepine. It is not, as this
section first said, where the WHO groups drugs by how they work: the WHO
defines levels 3 and 4 as "chemical, pharmacological or therapeutic"
subgroups, and 42 of the 64 classes here are chemical-structure groups
([SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md) §3.5; corrected
2026-10-13, see §13). These groupings were made by pharmacologists who had never
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

## 11. A judge that cannot see the newcomers (D21, 2026-10-12)

D21 admitted 1,119 molecules through a Phase 1 or Phase 2 brain indication
(see [COHORT-2.md](COHORT-2.md)). None of them carries an ATC N code, so none
is in the ATC answer key, but every one of them can stand in a labelled drug's
list. One that ranks above the drug's class-mate is graded a miss, however
apt it is. That is section 4's walk-down, unchanged. Before D21 the 786
members admitted by indication alone could already intrude the same way. D21
more than doubled them.

| the same D21 build | scoreable | top-1 | top-10 | MRR |
|---|---|---|---|---|
| as graded | 284 | 32.7% | 74.3% | 0.4607 |
| with the 1,119 skipped in each list | 284 | 38.7% | 77.1% | 0.5121 |
| the build before D21 | 284 | 38.7% | 77.8% | 0.5119 |

So the whole fall is the judge's. Skipped, the newcomers leave the ranking
among the old catalogue where it was: their extra weight on each target's
prevalence moves MRR by +0.0002. The ones ranked first over a class-mate are
mostly right: adipiplon (a GABA-A partial agonist) for 13 drugs, carfentanil
for 6, GSK1360707 (a triple reuptake inhibitor), ladostigil, vanoxerine,
SB-649868 (an orexin antagonist), huperzine A and edrophonium. Busulfan is
the exception.

The floors in `tests/similarity_harness.test.mjs` were re-set under the new
figures. The instrument was not changed: grading only among labelled molecules
would also raise every earlier figure, and it should be decided as a change of
instrument, not slipped in beside a catalogue change.

The MeSH judge does not escape this. It labels about 280 of the 1,117
newcomers (1,028 labelled molecules against 745), and graded the same way it
tells the same story:

| the D21 build, MeSH key | scoreable | top-1 | MRR |
|---|---|---|---|
| as graded | 865 | 45.0% | 0.5945 |
| only the old catalogue's molecules asked | 641 | 44.6% | 0.5961 |
| ...and the newcomers skipped in each list | 621 | 50.2% | 0.6341 |
| the 1,335 build, same key | 621 | 50.4% | 0.6335 |

## 12. The MeSH key changed with its source (2026-10-13)

The MeSH actions stopped coming through PubChem on 2026-10-13. They are read
from each molecule's own MeSH record now ([MESH-ACTIONS-ROUTE-B.md](MESH-ACTIONS-ROUTE-B.md)).
Since section 10's answer key is built from them, the judge changed, not the
ranking. On the one 1,335-entry build:

| key | labelled | scoreable | top-1 | top-10 | MRR |
|---|---|---|---|---|---|
| PubChem's actions | 699 | 588 | 47.4% | 85.5% | 0.6060 |
| MeSH's own records | 745 | 621 | 50.4% | 86.8% | 0.6335 |

The ATC grade of that build is 38.7% and 0.5119 under both. A MeSH grade
taken before 2026-10-13 is therefore not comparable with one taken after,
including every MeSH figure in section 10.

## 13. The judge repaired, beside the headline (2026-10-13)

[SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md) §4.3 proposed repairing
the two keys already in use before adding any. Section 11 had said the
filtered reading "should be decided as a change of instrument, not slipped in
beside a catalogue change"; this is that change, made with no catalogue
change and no constant moved. **The headline is untouched**: `--key atc` is
read as before and still the figure in Status. Everything below is printed
beside it.

**Two readings for every key.** `grade` now returns, over the same scoreable
molecules:

- *filtered*: the same walk past only the molecules the key judges (`judged`:
  it places them in some class, a class of one included). Seltorexant above
  suvorexant's classmates is neither right nor wrong under ATC, which has no
  code for it, so it no longer stands in the way.
- *nDCG@10*, with the key's graded `gain` where it has one. The ideal
  ordering is built from what the list holds, not from every classmate in the
  catalogue, so coverage stays out of the ordering grade as `unanswerable`
  already keeps it out.

**A repaired ATC key**, `--key atc-repaired`, versioned in
`analysis/similarity_harness/atc_repaired.json`:

- the questions are still the molecules with an N code, but peers come from
  every ATC code the catalogue holds, read from `molecule_classes` in the
  database. The payload stopped carrying them in 2026-09-26, and the page
  should not carry them for a grader's sake, so the harness opens
  `db/cohort1.db` read-only and refuses one whose `built_at` is not the
  payload's;
- 41 level-4 classes and 7 level-3 groups are set aside beside the X rule,
  each with its reason: residual classes filed under another letter (N02BG,
  N05CM), classes by use (the four N07B/N07C classes, antidotes, erectile
  dysfunction), and classes that are not pharmacology (electrolytes,
  contrast media). N07BA is excluded although its three members are all
  nicotinic agonists, because a key that keeps a use class wherever it
  happens to agree with mechanism is being chosen by its answers;
- a shared level-3 group earns half in nDCG: thioridazine for chlorpromazine
  (N05AC against N05AA) is no longer worth what an unrelated drug is worth.
  Top-1 and MRR still count classmates only.

| the D21 build, 2,452 entries | questions | scoreable | top-1 | top-10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|
| ATC, as graded (the headline) | 395 | 284 | 32.7% | 74.3% | 0.4607 | 0.3388 |
| ATC, filtered | | | 48.6% | 85.2% | 0.6097 | 0.4709 |
| repaired ATC | 353 | 259 | 36.3% | 77.2% | 0.4958 | 0.3850 |
| repaired ATC, filtered | | | 45.6% | 81.9% | 0.5727 | 0.4671 |
| MeSH | 1,028 | 865 | 45.0% | 86.1% | 0.5945 | 0.4215 |
| MeSH, filtered | | | 60.1% | 88.9% | 0.7029 | 0.5216 |

Read with three cautions. **The repaired key asks fewer questions**: 25
molecules filed only under excluded classes (naltrexone, nicotine,
buprenorphine, dexmedetomidine, ...) are no longer asked, and most of them
were misses, so part of its rise is questions it should not have been asking,
not answers it now accepts. The answers it accepts are five, and none lost:
codeine to hydrocodone (R05DA, cough suppressants), lidocaine to mexiletine
(C01BB), bromocriptine to lisuride (G02CB), procaine to proparacaine and
carbachol to acetylcholine. **The two filtered figures are not comparable
with each other**: the repaired key judges more molecules (any ATC code at
any level), so more of them stand in the walk, and its filtered grade is the
lower of the two for that reason. **And no filtered figure is a bound**:
SIMILARITY-LITERATURE §3.4 lists wrong answers the filter lets through.

`node analysis/answer_keys/agreement.mjs` measures what §5 of that document
asked step 1 to measure, how far the keys agree with each other, over the
molecules both judge:

| A, B | both judge | B accepts A's pairs | A accepts B's |
|---|---|---|---|
| ATC, MeSH | 290 | 79.2% | 18.8% |
| ATC, EPC | 165 | 62.0% | 52.5% |
| repaired ATC, EPC | 626 | 59.2% | 35.3% |
| MeSH, EPC | 603 | 17.4% | 80.4% |
| EPC, PE | 681 | 79.9% | 16.7% |

MeSH accepts four in five of ATC's classmate pairs, and ATC one in five of
MeSH's, because MeSH's classes are broad. ATC and EPC, the two narrowest,
agree on little more than half of each other's pairs. A constant that moves
one of them and not the other has not yet been shown to move the ranking.

## 14. A third judge: FDA's classes (2026-10-13)

Step 2 of the same proposal. `scripts/resolve_cohort_fda_classes.py` backfills
FDA's Established Pharmacologic Class (EPC), mechanism of action (MoA) and
physiologic effect (PE) through NLM RxNav, by identifier alone (FDA UNII to
RxNorm ingredient to RxClass); what it reads and the theophylline case that
shaped its matching rule are in
[DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), 2026-10-13. The classes stay in
the database: they are an answer key, not something the page shows.

- `--key epc`: a classmate shares an EPC; sharing only a MoA earns half in
  nDCG, except through the MoA classes `fda_keys.json` lists as
  pharmacokinetic (CYP450, P-gp, transporters) or empty ("Unknown Cellular or
  Molecular Interaction", "Enzyme Inhibitors").
- `--key pe`: a classmate shares a physiologic effect. The nearest thing here
  to an effect axis, and coarse: "Central Nervous System Stimulation" holds
  caffeine and naltrexone.

| the same build | questions | scoreable | top-1 | top-10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|
| EPC | 487 | 455 | 45.7% | 84.0% | 0.5946 | 0.5046 |
| EPC, filtered | | | 64.0% | 88.4% | 0.7319 | 0.6589 |
| PE | 701 | 598 | 37.6% | 78.8% | 0.5154 | 0.3640 |
| PE, filtered | | | 53.8% | 85.1% | 0.6498 | 0.4897 |

EPC is a separate curator from WHO and ChEMBL but **not independent of the
score's inputs**: an EPC such as *Serotonin Reuptake Inhibitor* restates a
mechanism ChEMBL also curates. Only US-labelled drugs are judged (627 of the
2,452 entries have an EPC). The first key that shares nothing with the score
is still step 3, adverse-effect profiles from labels; until it exists, no
constant should be adopted on the strength of these keys agreeing, since ATC,
MeSH and EPC can all be reading the same curation.


## 15. A judge that shares nothing with the score: label effects (2026-10-14)

Step 3 of [SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md) §4.3. Every
judge so far can read the curation the score reads: ATC and EPC restate
mechanisms, and MeSH's actions are often mechanisms. This one reads what
happened to patients. `scripts/resolve_cohort_label_effects.py` backfills the
adverse effects drug labels list, from OnSIDES v3.1.1, and `--key onsides`
makes each molecule's **five nearest label neighbours** its classmates:

- an effect is a molecule's when two of its single-ingredient labels list it,
  or its only label does;
- profiles are restricted to MedDRA's nervous-system and psychiatric SOCs,
  placed through ADReCS since OnSIDES carries no hierarchy
  ([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md), 2026-10-14); `--key onsides-all`
  reads every effect, and stands if ADReCS is ruled out;
- a molecule needs five effects in scope to be asked or judged;
- similarity is the cosine of IDF-weighted profiles, so an effect on every
  label (class boilerplate, and OnSIDES's reading of the heading "Nervous
  system disorders" as an effect) weighs nothing;
- neighbours six to ten earn half in nDCG;
- a molecule's own ingredient-mate (haloperidol decanoate for haloperidol) is
  neither its neighbour nor judged in its list. `grade` now passes the
  question to `judged` for this; the other keys ignore it.

**It was fixed before it graded anything**, in `onsides_key.json`, and
committed and pushed as such (9d47202). One rule changed between writing and
that commit, on the key's coverage alone: "listed on half of a molecule's
labels" became "on two", because OnSIDES reads a hundredfold more from some
labels of a drug than from others, and the half rule left diazepam with no
effect at all. The config says so.

**Read before it graded, the key looks like pharmacology where labels are
rich.** `analysis/answer_keys/neighbours.mjs` shows morphine's classmates as
methadone, oxymorphone, meperidine, oxycodone and hydromorphone; diazepam's
as clonazepam, lorazepam, estazolam and triazolam; sertraline's as the SSRIs;
sumatriptan's as every other triptan. It is confounded where the doc said it
would be: memantine is donepezil's label neighbour, by indication.

| the D21 build | asked | scoreable | top-1 | top-10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|
| label, nervous system | 409 | 346 | 14.5% | 49.1% | 0.2620 | 0.1976 |
| label, nervous system, filtered | | | 28.0% | 61.8% | 0.3989 | 0.3158 |
| label, every effect | 609 | 507 | 19.3% | 54.4% | 0.3180 | 0.2448 |
| label, every effect, filtered | | | 31.0% | 62.5% | 0.4234 | 0.3322 |

**The grade is low, and the key is why.** The worst "misses" are mostly the
key's: ciprofloxacin's ranking puts moxifloxacin first, which is right, while
its label neighbours are azithromycin and bexarotene; a non-nervous-system
drug's handful of nervous-system effects is generic. Two measurements say
how much of the low figure is noise in the key rather than in the ranking.

*Against a shuffle* (`analysis/answer_keys/chance.mjs`, the same lists in
random order, in closed form):

| key | top-1 | shuffled | ratio | MRR | shuffled | ratio |
|---|---|---|---|---|---|---|
| ATC | 32.7% | 4.8% | 6.8 | 0.4607 | 0.1103 | 4.2 |
| MeSH | 45.0% | 9.4% | 4.8 | 0.5945 | 0.2078 | 2.9 |
| EPC | 45.7% | 5.1% | 9.0 | 0.5946 | 0.1227 | 4.8 |
| PE | 37.6% | 6.8% | 5.5 | 0.5154 | 0.1593 | 3.2 |
| label, nervous system | 14.5% | 1.8% | 8.1 | 0.2620 | 0.0629 | 4.2 |
| label, every effect | 19.3% | 2.8% | 6.9 | 0.3180 | 0.0768 | 4.1 |

Measured against what a shuffle would score, the ranking does as well under
the judge that shares nothing with it as under the judges that share its
curation. The absolute figure is low because the label key gives each
question five classmates out of hundreds, where a class key gives dozens.

*By profile size*, in tertiles of nervous-system effects: filtered top-1
19.2% (5–8 effects), 25.0% (9–16), 37.0% (17 or more), with the shuffle flat
at about 2% throughout. The richer a label, the more the ranking agrees with
it.

**Agreement with the other keys** (`agreement.mjs`), over the molecules both
judge: ATC accepts 47% of the label key's neighbour pairs and the label key
43% of ATC's classmate pairs, about as well as ATC and EPC agree (53% and
62%). EPC accepts 22%, MeSH 35% (MeSH's classes are broad). The two label
readings accept 37% and 44% of each other's.

### The constants under five judges

The sweep, one constant at a time, on the same build. MRR change from the
current setting:

| constant | ATC | MeSH | EPC | label, nervous | label, every |
|---|---|---|---|---|---|
| `OPPOSED_PAIR_FACTOR` 1.0 (D15 off) | −0.0287 | −0.0146 | −0.0316 | −0.0260 | −0.0193 |
| curated-only weight 0.75 → 1.0 | +0.0042 | +0.0086 | +0.0021 | +0.0058 | +0.0035 |
| replicated-only weight 0.9 → 0.75 | +0.0078 | +0.0079 | +0.0003 | −0.0044 | −0.0039 |
| family weight 0.5 → 1.0 | +0.0088 | +0.0180 | +0.0169 | +0.0039 | +0.0095 |
| Preliminary weight 0.5 → 0.25 | −0.0097 | +0.0110 | −0.0106 | +0.0044 | +0.0104 |
| `SPECIES_EXPONENT` 0.5 → 0.75 | +0.0063 | +0.0042 | +0.0079 | +0.0053 | +0.0003 |

Read row by row, the five judges sort the constants into three kinds:

- **Agreed by every judge.** Switching D15 off is the worst setting on its
  row under all five, which is the strongest confirmation D15 has had.
  Raising the curated-only weight to 1.0, the family weight to 1.0 and the
  species exponent to 0.75 each help under all five, by small amounts. The
  curated-only weight is section 6's live finding, whose caveat was that its
  judge flattered curation; a judge that reads no curation agrees, so the
  caveat no longer covers it, though the gain stays under 0.01 everywhere.
- **Agreed only by the judges that read curation.** Lowering the
  replicated-only weight to 0.75 helps under ATC (+0.0078) and MeSH
  (+0.0079), is flat under EPC, and hurts under both label readings. This is
  the pattern the label key was built to catch (SIMILARITY-LITERATURE §4.3):
  a gain the curated judges see and the independent one does not.
- **Split.** The Preliminary weight at 0.25 helps under MeSH and both label
  readings and hurts under ATC and EPC, as section 10 found for ATC and MeSH.

The figures for ATC and MeSH are this build's, not section 10's; the
curated-only gain under ATC is +0.0042 here against +0.0050 there.

**Nothing was changed.** SIMILARITY-LITERATURE §4.1 asks that a constant be
adopted only when judges of different provenance agree, and that is now
possible to ask; asking it is a decision about the score, not about the keys,
and it is not made in the change that built the judge.

## 16. A pre-registered pairwise key (2026-10-14)

Step 4. Section 3 refuses a hand-written key because it can be bent to say
anything. `analysis/answer_keys/pairs.json` is hand-written, and answers the
objection by how it was made rather than by what it says:

- **243 pairs**: 116 positives (one mechanism at one target, one direction),
  80 known-unlike negatives (one indication, different primary mechanisms)
  and 47 opposites (one target, opposite directions);
- **each cites its sources**, 207 in all: a DOI whose title was checked
  against Crossref, or a US label on DailyMed whose setid resolves, with what
  the source says. ChEMBL and GtoPdb, the score's inputs, were not allowed;
- **drafted blind**: three subagents, one per area, given only the
  catalogue's ids and names and forbidden the repository and the ranking,
  then reviewed here. The edits the review made are listed in the file;
- **frozen before use**: the pairs and the rules that grade them were
  committed and pushed (3ed013f) before either graded the ranking;
- **held out**: `KEYS` does not carry it, so no sweep can tune to it.

It is not independent of the score as the label key is: labels and reviews
state the mechanisms ChEMBL's curators also read. What it adds is negatives,
opposites and a fixed set of questions. 44 pairs repeat a relationship the
probe set had already asked about (`seen`), and 34 whose sourcing or claim is
weaker carry a `doubt` with the reason (a class-level source, a mechanism a
label calls unknown, an indication that overlaps rather than matches).

The rules, in the file: each pair is read both ways; a positive is a hit
within the top 10, and a partner absent from the list is coverage, not a
miss; a negative or an opposite is clean below the top 10 or absent;
ordering is the share of (positive, other) pairs within one list in which
the positive ranks higher, an absent partner last and a tie half.

| first grade, the D21 build | positives within top 10 | median rank | negatives clean | opposites clean | positive above other |
|---|---|---|---|---|---|
| every pair | 75.4% of 232 | 4 | 98.1% of 160 | 90.4% of 94 | 96.0% of 93 lists |
| without `seen` | 77.6% of 156 | 5 | 98.1% of 160 | 92.7% of 82 | 95.8% of 72 |
| without `doubt` | 77.6% of 210 | 4 | 97.7% of 130 | 91.0% of 78 | 96.8% of 82 |

Every positive direction is reachable: each pair shares at least one target.
The pairs the probe set had seen grade no better than the rest, so having
asked about them before did not flatter the key.

**What it found.**

- **D15 misses one opposition.** 7 of the 9 failed opposite directions are
  flumazenil against the benzodiazepines and zolpidem, at ranks 2 to 8.
  ChEMBL curates flumazenil as an ALLOSTERIC ANTAGONIST at GABA-A and them as
  POSITIVE ALLOSTERIC MODULATOR, and `OPPOSED_ACTIONS` names no such pair.
  The other two are pilocarpine to atropine (rank 9) and morphine to
  naltrexone (10). Not changed here: it is an entry in a list chosen by
  argument, and CLAUDE.md's open items say so.
- **Negatives are kept apart.** 3 of 160 directions fail: lacosamide and
  levetiracetam rank each other 2nd and 6th, and xanomeline ranks olanzapine
  10th, which is a real shared target, since olanzapine blocks the muscarinic
  receptors xanomeline activates.
- **The worst positives** are tranylcypromine to isocarboxazid (rank 183),
  lacosamide to oxcarbazepine (108), cabergoline to bromocriptine (102) and
  propranolol to nadolol (101). `node analysis/answer_keys/pairs.mjs --list`
  prints them all.
