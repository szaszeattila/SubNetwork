# Next steps, ranked against the mission

Recorded 2026-09-17. **These are proposals. Nothing here is adopted**, no
membership policy is changed, and no scoring constant is altered by this
document. It is the argument for what to do next; the measurements behind it are
in [docs/SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md), and the read-only
scripts that produced them are in
[analysis/probe/](../analysis/probe/README.md).

The ordering principle is the one CLAUDE.md's own backlog uses: how directly
each item damages the thing this project is for.

---

## The frame

The mission is one sentence:

> Make it possible to **see which molecules may act in similar ways in the
> brain**, by drawing what they act on and how well each of those claims is
> evidenced.

It has three clauses, and the work so far has gone almost entirely into the
arithmetic of the first.

| clause | what carries it today |
| --- | --- |
| *act in similar ways* | six hand-chosen constants, a prevalence discount, a cosine normalisation, and D15 |
| *in the brain* | the molecule selection policy, and **nothing else** |
| *see* | the canvas, six controls, and a picture that is 84% assay history |

The diagnosis found the second and third clauses to be where the larger losses
are. Two measurements say so plainly:

- **1,736 of the 2,063 targets on the default canvas have no curated mechanism
  for any molecule in the catalogue.** Only 327 are places where ChEMBL says
  anything acts at all. Those 327 carry 5,346 molecule–target pairs against
  7,489 at the other 1,736, so most of the picture's mass is measurement history
  rather than pharmacology.
- **There is no brain signal in `db/cohort1.db` at all**, and 3,303 of the
  16,206 eligible claims are at non-human targets.

None of that makes the score wrong. It means the score has been asked to carry a
claim about the brain that nothing in the data supports, inside a picture that
mostly is not about pharmacology.

---

## 1. Make direction first-class

> **Step one (1a) was implemented on 2026-09-17** on the user's instruction, and
> is no longer a proposal. Direction is read at the protein in
> `pooledDirection`, keyed on the **accession** rather than on the gene symbol
> the prototype used — the two recover the same pairs, so invariant 6 decides
> it. 490 demoted pairs became 876; morphine ranks naltrexone 17th of 380.
> Recorded in [COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) D15. **The decision
> flagged below — what the demotion divides by — was taken on 2026-09-20**: the
> demotion is now proportional and the denominator is `comparable`, never
> `shared`, because a shared target with no curated direction is an unknown and
> not an agreement. Graded over shared was measured and is *worse* than the rule
> it would replace. Step two (GtoPdb) is untouched and still a proposal, as is
> everything in §2 onward.

**Why first.** Every other item makes the ranking noisier or cleaner. An
opposite makes it *wrong in the one way this page cannot afford*: it states the
reverse of the truth. Morphine's nearest neighbour is naltrexone — the drug
given to reverse it — and caffeine's list had adenosine at rank 2 before D15.
D15 is the right rule reaching almost nothing: it can compare directions on
**7.4% of pairs**, because ChEMBL leaves `action_type` null on 92.6% of them.

**Step one, free and measured.** Read a curated direction at the **protein**
rather than at the ChEMBL target record it happens to be filed against. Morphine
is curated AGONIST at human mu-opioid and naltrexone ANTAGONIST at the human
mu/kappa/delta family — one row apart, never compared. Pooling takes
entirely-opposed demotions from **247 to 535**, led by morphine/naltrexone,
naltrexone/buprenorphine, fentanyl/naltrexone, then the antipsychotics against
the dopamine agonists. (Written here as 537, which was 247 + the 290 recovered.
That sum assumed pooling only ever adds: it also *releases* two pairs, by
finding an agreeing protein the one-record view could not see.)

This is not the D06 merge and must not be described as one: it changes only
which two actions get compared, never what a shared target is, what it weighs,
or what the canvas draws. The viewer already makes exactly this argument when it
reads direction at subsumed rows.

**Decide at the same time:** `all_opposed` divides by *comparable*, not by
*shared*, so clozapine/apomorphine is demoted fourfold on one comparable protein
out of 34 shared. That is already true today and pooling makes it bite more
often. A factor proportional to how much of the shared pharmacology is opposed
is a different answer and possibly a better one. It is a decision about what the
score claims, not a constant to sweep.

**Step two: GtoPdb, for the field rather than the volume.** *Adopted
2026-09-27 as D17, in [COHORT-2.md](COHORT-2.md), with what it measured.*
[docs/MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md)
already ranks IUPHAR/BPS first among new pharmacology sources. What the
diagnosis adds is *which of its columns justifies the import*: the **curated
action**. Not more interactions — ChEMBL has plenty — but a direction on the
interactions already drawn. GtoPdb's access route changed in September 2026 and
must be checked before any import; the brainstorm records this.

---

## 2. Separate pharmacology from screening history, in the picture

**Why here.** This serves *see* rather than the ranking, and it is the clause
with the least work behind it. 84% of drawn targets are places nothing is known
to act. That is not a data error — it is what a binding database looks like —
but it means a reader looking for molecules that act alike is looking at a
canvas whose mass is assay history. Amlodipine's nearest neighbours are
terfenadine and pimozide over thirty shared results from one off-target panel.

**What to add.** A channel that distinguishes *a target where something is
curated to act* (327) from *a target that has only ever been measured* (1,736).
The machinery exists and the idiom is settled: **Canvas** already hides
single-molecule targets and states its cost, **Line colour** already reads the
legend off the canvas rather than off the palette. This is the same shape,
sharper — and it must state its cost the way the other five do.

**It is also the honest home for the curated-mechanism ratio.** CLAUDE.md keeps
that term out of the *score* because an ATC-shaped key is the friendliest
possible judge of anything rewarding curation. That objection is exact, and it
is an objection to scoring on it. It is no objection at all to *showing* it.

**Related, and still only a hypothesis.** The legacy pipeline collapsed assay
fan-out with `fanoutRef` — one experiment attributed to many proteins, 133 of
its 654 edges in 29 groups. **The cohort pipeline has no equivalent at any
layer**, and it is not in CLAUDE.md's Not-done list either. `observations`
carries the assay id, so the first step is to count how many shared-target rows
come from a single assay. Nothing here is measured yet beyond the amlodipine
case.

---

## 3. Define cohort 2 as a target scope, not a longer molecule list

**This is the decision that is not an agent's to make.** It is a change to
`config/cohort1_selection.json` and a rebuild, and it is the largest item here.

The brainstorm's three options are still open. The measurements point at its
**option 2** (a neuropharmacology catalogue: define the relevant human target
families, then admit their curated ligands) over its **option 1** (more clinical
molecules by the existing rule).

The argument, from the diagnosis rather than from taste: every failure found was
a failure of the *target* side. Barbiturates rank badly because no barbiturate
here has a GABA-A claim — phenobarbital carries about 110 claims, nearly all
`limited_or_unresolved`, and not one at its own mechanism. Amlodipine ranks
badly because a screening panel is undifferentiated from pharmacology. D15
barely fires because direction is unannotated. **Admitting another few hundred
molecules under the existing clinical rule adds more rows of the same broad
panels and not one curated direction.**

A target-defined scope does three things at once:

- makes *in the brain* a constraint the data enforces rather than an assertion
  inherited from ATC codes,
- admits the molecules that **define** direction — antagonists, reversal agents
  and tool compounds. **Flumazenil is approved, is in ChEMBL as `CHEMBL407` at
  phase 4, and is absent from this catalogue**, because an antidote is filed by
  therapeutic use and that is precisely the axis on which a reversal agent
  differs from the drug it reverses. That is a narrower and better-evidenced
  boundary case than the ones in
  [docs/COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md), and the probe set
  already contains the pairs it would fix.
- bounds the screening noise at its source, because the scope is a set of
  targets rather than whatever each molecule happened to be screened against.

The costs are real and are the brainstorm's own: it requires an explicit,
versioned target scope, and biochemical activity at an in-scope target does not
establish brain exposure. Neither is an argument for the clinical rule, which
does not establish it either.

---

## 4. Put a brain signal on the target side

`grep -i brain` over `scripts/cohort/` and `db/schema_cohort.sql` still returns
nothing. Until that changes, the mission's third clause is carried by molecule
selection alone — and the diagnosis shows that selection is simultaneously too
loose on the target side (CYPs, hERG, whole off-target panels) and too tight on
the molecule side (flumazenil).

The review's proposal stands: a `resolve_cohort_brain_expression.py` backfill on
the pattern of the Wikipedia one — a separate run, never part of a build — drawn
as a **marker rather than a filter**, because invariant 10 holds and absence of
a tissue annotation is not a negative result. HPA is the source the brainstorm
prefers, with RNA and protein evidence kept distinct.

---

## 5. Weigh affinity, last

Two molecules sharing a target at 7 nM and at 200 µM still score identically,
and "act alike" plainly means something about potency. It is last because it is
the only item here with a **failed prototype already on record**: weighting each
overlap by the weaker of the pair's two median affinities graded *below* the
un-weighted score. `median_nm` is already in the startup payload, so what is
missing is the formulation and not the data. Invariant 7 keeps potency out of
the *trust* signal and that is unchanged; this would be a separate term, and it
needs the second answer key before it could be believed.

---

## What is deliberately not on this list

**None of the six scoring constants.** The sweep's one live finding — the gap
between a curated claim at 0.75 and a replicated one at 0.9 — is unchanged,
unaddressed by everything above, and still the setting the ranking feels most.
It stays where CLAUDE.md left it: not changed on the strength of a proxy that
flatters curation, with 24 of 217 molecules getting worse under the best-scoring
value.

**Extending the answer key past ATC N** is in the diagnosis rather than here,
because it changes the instrument and not the project. It is cheap, it is
measured (top-1 37.5% → 44.5%), and it should probably be done first of
everything — but it improves no answer the page gives anybody.

---

## A wording proposal for CLAUDE.md's Goal

The Goal section is admirably exact about what similarity here excludes: "It
knows nothing about dose, exposure, or whether a molecule reaches the brain at
all." Two further limitations are currently true and unstated, and both are
measured above:

1. **Direction is known for a small minority of pairs.** The Goal describes D15
   at length without saying that ChEMBL gives both sides a direction on 7.4% of
   overlaps. A reader can currently infer that opposites are handled; they are
   handled *where they are annotated*.
2. **Nothing about the targets is brain-specific.** The focus on brain-expressed
   targets is stated in the Shows list and carried entirely by which molecules
   were admitted.

Proposed as an addition to the existing limitations sentence, not a rewrite:
the paragraph is load-bearing and its honesty is the reason it is quotable.

---

## Summary

| | item | new source? | measured? | whose call |
| --- | --- | --- | --- | --- |
| 1a | direction at the protein | no | yes, 247 → 535 | **done 2026-09-17**, re-graded |
| 1b | GtoPdb for curated action | yes | the hole is: 92.6% | needs the import decision |
| 2a | show curated-vs-measured targets | no | 327 / 1,736 | implementable |
| 2b | assay fan-out in the cohort pipeline | no | **no** — hypothesis | measure first |
| 3 | cohort 2 as a target scope | maybe | the failures are target-side | **yours** |
| 4 | brain marker on targets | yes (HPA) | absence confirmed | yours |
| 5 | affinity weighting | no | prototype failed | after a second key |
