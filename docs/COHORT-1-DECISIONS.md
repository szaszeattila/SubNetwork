# Cohort 1 implementation decisions

Created 2026-09-12. Updated 2026-09-13. Status: all policy decisions accepted; implementation details delegated.

This document records the user's choices before importing the first clinical
cohort. The original questions are retained below for context; the dated answer
and adopted-rule blocks govern where the user has decided. Recommendations
are not adopted merely by appearing here. No production import has been
performed in this decision-gathering step. The implementation prompt is linked
at the end of this document.

For each answer, preserve the user's intent, record the adopted rule and its
rationale, and identify any remaining ambiguity. Mark each item decided,
partially decided, or deferred. An unanswered item remains pending. If an
answer changes an earlier choice, retain a dated change note. Explicit deferral
must say what the first import will do in the meantime.

## Source documents and precedence

- [Revised cohort report](COHORT-REPORT.md), especially section 6.
- [Follow-up analysis](COHORT-FOLLOWUP.md).
- [Boundary review](COHORT-BOUNDARY-REVIEW.md) and its
  [audit package](../analysis/cohort1/boundaries/): source-backed boundary
  corrections and membership examples; its additional recommendations are not
  automatically adopted.
- [Expansion brainstorm](MOLECULE-EXPANSION-BRAINSTORM.md): proposals only.
- [Project guide](../CLAUDE.md) and [data-quality history](DATA-QUALITY-LOG.md):
  current production behavior and its rationale.
- [Original analysis package](../analysis/cohort1/README.md) and
  [follow-up package](../analysis/cohort1/followup/README.md), including their
  configurations and row-level outputs.

Use the revised September 12 report and follow-up when they correct the
archived report. This log will record explicit policy choices; it does not
silently rewrite the historical reports or supersede production invariants.
The implementation must reconcile any intentionally changed invariant with
the adopted policy and update the relevant documentation.

## Measured catalogue alternatives

These figures use S0 core indication scope, literal ChEMBL parent molecule
types, and the original baseline evidence. Supported counts use the follow-up's
broad human target basis, retaining single proteins, precise complexes,
families and complex groups at their native target identities. They are not
forecasts for different scope, source, potency, identity or evidence rules.

| Membership rule | Small molecules | With Supported evidence | With Supported or Preliminary evidence | Existing seeds admitted |
|---|---:|---:|---:|---:|
| CNS Approved/Phase 3 indications only | 791 | 607 | 665 | 22 |
| Whole ATC N + CNS Approved indications | 677 | 448 | 481 | 18 |
| Whole ATC N + CNS Approved/Phase 3 indications | 995 | 666 | 738 | 22 |
| Whole ATC N + CNS Approved/Phase 2/3 indications | 1,540 | 1,013 | 1,152 | 24 |
| Whole clinical catalogue, no minimum CNS phase | 1,771 | 1,137 | 1,310 | 24 |

## Decision register

### D01 — Admission routes and clinical stage

Choose whether whole ATC N remains an independent route, and the minimum
phase for the qualifying CNS indication: Approved, Phase 3, Phase 2, or no
minimum. The phase threshold applies to the qualifying indication, not the
molecule's highest phase in any disease. Whole ATC N has no implied CNS-phase
requirement. Specify treatment of missing/unknown phase if changing the saved
policies. The report proposes ATC N plus CNS Approved/Phase 3; Phase 2 offers
substantially wider measured coverage.

Status: decided (2026-09-12).

User answer: "Let's go with the proposal, Approved+Phase 3"

Adopted rule: whole ATC N remains an independent route. The indication route
requires Approved or Phase 3 for an indication in the scope adopted in D02.
Missing/unknown/lower indication phases cannot qualify through that route,
but do not disqualify an ATC-N match. Keep indication-specific phase separate
from the highest phase across unrelated indications. The old 995 count is
not the adopted catalogue size because D02 and D03 change its scope.

**The phase floor is superseded by D21** (2026-10-12, in
[COHORT-2.md](COHORT-2.md)): an in-scope indication now qualifies from Phase 1.
Early Phase 1, Unknown and missing phases still cannot, and everything else
above stands.

### D02 — Indication and ATC boundaries

Choose S0 core scope or explicit extensions for CNS oncology, peripheral/
cranial nerve disease, muscle/neuromuscular-junction disease, and general pain.
Separately decide whether to retain ATC N01B local anaesthetics and N02B general
analgesics, currently flagged but admitted through whole ATC N. Scope follows
the saved descriptor-placement rules; a descriptor with another valid core
placement can still qualify. Broader-scope membership counts are available,
but evidence for additions outside the original 2,245 candidates has not been
assessed. The starting proposal is S0 plus whole ATC N with visible flags.

Status: decided; identifier-level scope validation required during implementation (2026-09-12).

User answer: "Lets go with the core scope + include pain, explicitly preserve neuropathic pain and fibromyalgia"

Adopted rule: S0 core plus general pain, with explicit inclusion of neuropathic
pain and fibromyalgia, even where another boundary exclusion would otherwise
remove their descriptors. Retain whole ATC N, including its flagged local
anaesthetic and general-analgesic branches. No blanket oncology, peripheral
nerve or muscle/NMJ expansion is adopted. A separate qualifying pain/core
indication still admits a molecule. Apply D01's phase requirement to these
qualifying indications; inclusion of a disease does not waive clinical stage.

Local source discrepancy discovered while recording this answer:
`analysis/cohort1/out/indication_scope.csv` marks Fibromyalgia (D005356),
Neuralgia (D009437), Trigeminal Neuralgia (D014277), Facial Neuralgia (D005156),
Postherpetic Neuralgia (D051474), and Pudendal Neuralgia (D060545) outside core.
Fibromyalgia is classified under the excluded muscle/NMJ branch; trigeminal
and facial neuralgia are not in the saved general-pain class. This conflicts
with the report prose saying Neuralgia already has an included C10 placement.
Use source-native identifiers and the saved placements, verify the relevant
neuropathic-pain descriptor set, and implement explicit inclusions. Do not
assume S4 alone fulfills the user's requirement. The listed descriptors are
an audit starting point, not a claim that the full neuropathic scope is mapped.

Recompute membership and assess evidence for newly admitted candidates before
quoting final totals. Neither 995 nor the unfiltered 2,445 pain-scope count
answers the adopted phase/category/explicit-inclusion policy.

### D03 — Molecule categories and identity corrections

Choose small molecules first or include other molecule categories. Adopt
explicit chemical-parent normalization while preserving source salt/form
identities and distinct parents for stereoisomers, prodrugs and metabolites.
Decide whether to correct verified source-type anomalies through an audited
override mechanism. Both theophylline records are typed Protein in ChEMBL 37;
correcting its category alone would not resolve its Phase-1 CNS eligibility
under a Phase-3 policy.

Status: decided (2026-09-12).

User answer: "all molecule types, not just small molecules. this is about finding substances you can take that would elicit similar effects to other substances"

Adopted rule: no molecule-type eligibility filter. Retain the source category
for all qualifying substances, including biologics and unresolved categories.
Do not infer an oral-only requirement from "take" or add an unrequested route
of administration filter. Retain parent/form provenance and meaningful distinct
identities. Theophylline's source-type anomaly no longer excludes it by type;
flag it rather than silently rewriting ChEMBL's classification.

Product intent: support exploration of substances that may have related effects.
Current target overlap remains a mechanistic comparison; implementing all types
does not by itself add an effects predictor, exposure model, dosing model or
interchangeability claim.

### D04 — Withdrawn annotations and unresolved structures

Choose whether candidates with withdrawal annotations or no structure stay
searchable with explicit labels, enter a separate review inventory, or are
excluded. The 995-member proposal includes 63 family withdrawal flags and
12 structure-NONE records. Proposed default: retain and label them without
guessing structures or implying current approval/availability. Determine how
unresolved identity affects drawable claims, separately from membership.

Status: decided (2026-09-12).

User answer: "retain them with annotations"

Adopted rule: retain withdrawal-flagged and structurally unresolved candidates
with explicit source annotations. Do not invent a structure or equate a
ChEMBL Approved annotation with current availability. An absent structure
alone does not invalidate a traceable target claim for an identified source
entity; ambiguity in the claim's identity remains visible.

### D05 — Relationship to the existing 28 molecules

Choose whether the first cohort becomes the sole active catalogue or expands
the network alongside a separately labelled legacy seed cohort. No seed should
silently count as a clinical-policy match. The 995-member proposal admits 22
seeds; the omissions include theobromine, loperamide, mibefradil, theophylline,
rolipram and pentoxifylline. Phase 2 retains the last two. Decide whether any
exception requires a documented independent admission route. Historical seed
provenance can be retained regardless of active-view membership.

Status: decided (2026-09-12).

User answer: "lets supplement, because id like the seed molecules that didn't make it to become examples for cohort 2"

Adopted rule: supplement the existing 28-molecule catalogue; preserve all seed
identities and their labelled seed membership. Record clinical membership
independently, without grandfathering seeds into cohort 1. Reassess which seeds
fall outside the newly adopted scope, then retain those as examples to consider
when designing cohort 2. This does not pre-admit them to an undefined cohort 2.
Preserving a seed molecule does not preserve an edge that fails the final
uniform evidence rules or deferred-source policy.

### D06 — Target scope and target granularity

Choose all eligible protein targets of admitted molecules or a separately
defined CNS target subset. The report proposes human single proteins, precise
complexes, families and complex groups at their original target identity.
Decide whether these target levels all belong in the first release. Family
evidence must not become subtype evidence, and complex evidence must not
become separate component claims. Brain expression and BBB annotations are
proposed context/filters, not universal eligibility gates.

Status: decided (2026-09-12).

User answer: "keep all levels"

Adopted rule: include single proteins, precise complexes, families and complex
groups at their asserted target identity. Use the report's eligible-target
basis, without adding a new CNS-target whitelist. Keep family and complex
claims distinct from component/subtype claims; do not inflate overlap by
expansion. Brain expression and BBB status remain contextual, not membership
gates.

### D07 — Species, variants and indirect assignments

Choose the primary evidence basis and which additional evidence layers are
available in the first release. Proposed default: direct human experiments
without variants plus supported human curation at its asserted target level;
retain nonhuman, homologous, mutant and ambiguous assignments separately.
These must not contribute to human-specific support or overlap merely because
they reference a related target. Specify which layers are visible versus
audit-only initially.

Status: decided; filter implementation delegated (2026-09-12).

User answer: "yea i think we should make a filter that would optionally show the non-direct human evidence and members of the cohort that only have that as evidence"

Adopted rule: primary view uses the proposed human evidence basis. Provide an
explicit optional filter/layer for evidence outside that basis, including
nonhuman, homologous, variant and ambiguous assignments, and expose admitted
molecules whose only evidence is in that layer. Preserve assignment/species
labels and compute evidence strength within the selected basis, not by mixing
it into direct-human support. Species/assignment and evidence-tier filters are
separate controls. Enabling broader evidence cannot invent a named protein
edge for an unassigned observation. D11's organism-format exclusion still
applies; nonhuman biochemical evidence is not synonymous with organism-format
observations.

### D08 — Production evidence and conflict rules

Decide whether to adopt the report's Supported/Preliminary/Limited rules for
production, replacing the current measurement-count corroboration rule.
Experimental Supported requires at least two distinguishable publication-class
studies within the same role and endpoint class; multiple rows from one paper
do not establish replication. Curated support remains a separate claim route.
Binding, functional effects and curated actions remain distinct. Decide whether
upstream validity/duplicate flags and conflicting claims follow the report
(retained and visibly flagged) or receive a stricter eligibility policy.
Distinct publications remain a proxy for independence, not proof of it.

Status: decided (2026-09-13).

Initial user answer (2026-09-12): "not sure about this one, can you elaborate?"
Follow-up acceptance (2026-09-13): "yes go with your suggestions for all three remaining choices. lets build the prompt now for opus 5"

Adopted rule: use the explained study-based Supported/Preliminary/Limited
policy in production. Experimental Supported requires at least two distinct
publication-class studies with qualifying exact values within the same claim
role and endpoint class. Multiple rows from one paper remain one study;
patents and deposited datasets do not create multiple-publication support.
Preliminary requires at least one identifiable eligible study without meeting
Supported. Limited/unresolved observations retain explicit reasons.

Traceable curated mechanisms provide a separate Supported route at the actual
target/action specificity asserted. Curation does not upgrade binding or
functional evidence, and experimental binding does not establish action.
Apply species/assignment eligibility before assessing support for each basis.
Keep upstream flags and contradictions visible, exclude documented known-bad
records, and preserve the report's conflict flags without treating conflicting
results as agreement. Two publications remain a proxy for independence.

This intentionally replaces measurement-count corroboration as the trust rule.
Measurements must still be counted and traceable to their numeric summaries.

### D09 — Default graph, similarity and evidence layers

Choose Supported-only versus Supported plus Preliminary as the default view,
and specify which claims may count toward similarity. Proposed default:
Supported-only display and ranking, with optional Preliminary exploration;
curated and replicated support visibly distinguished. Exact target identity
must control overlap, with no automatic family-to-subtype equivalence or
multiple counting of one complex's components. Broader-target overlap should
remain distinguishable from exact single-protein overlap. Decide whether to
delegate detailed scoring weights to a documented implementation proposal.

Status: decided (default accepted 2026-09-12; D08 tier definition accepted 2026-09-13).

User answer: "yea go with the starting point here"

Adopted rule: Supported-only display and similarity by default, optional
Preliminary exploration, and visibly distinct curated/multiple-study support.
Match overlap at the actual target identity and avoid multiplying one family
or complex claim into component overlaps. Broader evidence from D07 must not
silently upgrade direct-human similarity. Detailed scoring implementation is
delegated under D14 and must be documented and consistent across views.

### D10 — Potency filtering

Choose whether potency restricts imported experimental edges, only their
display, or neither. If enabled, select the initial threshold (the report
compares 1, 10, 100 and 300 micromolar) and aggregation rule. Proposed default:
retain eligible evidence and offer an optional display filter using the
log-space median within each endpoint class. Preserve curated weak claims,
and never make a clinical catalogue member disappear because of potency.
Explicitly reconcile this choice with the current 300-micromolar experimental
auto-discovery cutoff. Potency is separate from evidence strength and exposure.

Status: decided; filter details delegated (2026-09-12).

User answer: "offer potency filters"

Adopted rule: potency is an optional display filter, not clinical membership
or evidence-import eligibility. Retain otherwise eligible weak experimental
evidence; reconcile the current 300-micromolar auto-discovery cutoff accordingly.
Implementation default: no potency filter initially, with 1/10/100/300 micromolar
presets, using within-endpoint log-space medians. Preserve curated claims and
make any missing quantitative value clear. Bounds do not masquerade as exact
values or enter these medians. Filter effects must be visible in graph and
similarity results.

### D11 — Unit recovery and contextual evidence

Decide whether to adopt the audited explicit concentration conversions now
and defer mass conversions until the publication's measured material basis
is verified. The concentration-only scenario adds one Supported claim in the
995-member proposal, without adding a molecule with qualifying evidence.
Choose whether bounds, approximate values and organism-format observations
are exposed in evidence panels or retained only in an audit/context inventory
for the first release. Preserve original values, units, relations and exclusion
reasons; none should be silently pooled into exact biochemical potency.

Status: decided (initial choices 2026-09-12; remaining choices accepted 2026-09-13).

Initial user answer: "adopt the audited concentration unit conversions. compute mass-based conversions. what do you mean by bounds/approximate results? keep organism observations out."
Follow-up: the user accepted the suggestions for all three remaining choices
on 2026-09-13 after the explanation recorded in the answer history.

Adopted rule: apply the audited dimensionally explicit concentration
conversions. Compute mass-based conversions wherever measured-form identity
and molecular weight permit, retaining original value/unit, source form,
weight, conversion formula and assumptions. Do not automatically use the
parent freebase weight. Keep unverified material-basis conversions conditional
and outside tier/potency calculations until that basis is verified. A source
record's molecular weight alone does not verify the publication's material.
Missing/ambiguous identity or weight produces an explicit unresolved result,
not a guessed conversion. Conditional computations fulfill this part of the
first implementation; literature-wide material verification is not required.

Show bounds and approximate values as labelled observations in evidence
details, preserving >, <, >=, <=, >> and ~ as reported. These are not exact
values and do not enter exact medians, exact-value potency threshold passes,
or the adopted exact-measurement replication rule. A bounds-only observation
must not become a default Supported edge. Details must be accessible from the
catalogue even when there is no default drawable edge.

Exclude organism-format observations from active imported evidence, graph,
viewer context and similarity, including the optional broader-assignment layer.
Preserve existing historical analysis/audit files; no deletion of earlier
source records or analysis was requested.

### D12 — Source integration in the first import

Choose a uniformly assessed ChEMBL-37 evidence baseline first, or extend PDSP,
BindingDB and DGIdb to the cohort immediately with source/study deduplication
and coverage tracking. Decide how existing supplementary seed evidence remains
available if new candidates initially have ChEMBL-only coverage. Identity and
link enrichment are separate from evidence-source scope. GtoPdb, HPA and BBB
datasets can be explicitly deferred; their cohort coverage was not measured.
Unassessed source coverage must not be labelled no evidence.

Status: source deferral decided; operational interpretation recorded (2026-09-12).

User answer: "lets deffer PDSP, bindingDB and DGIdb alltogether for now. we will come up with cohort 2 that may use these databases including the new sources mentioned. what is your opinion?"

Adopted rule: ChEMBL 37 is the pharmacology evidence source for this first
implementation. Defer PDSP, BindingDB and DGIdb altogether, along with new
pharmacology/context integrations such as GtoPdb, HPA and BBB datasets, for
later consideration in cohort 2. Identity/link enrichment is a separate role,
not an additional pharmacology evidence route.

Operational interpretation of "altogether": apply ChEMBL-only active evidence
uniformly to the retained seeds and new cohort; do not preserve supplementary
seed-only support in active tiers/ranking. Preserve historical data and its
provenance. Some old seed edges or strengths may therefore change even though
all seed molecules remain. Later supplementary coverage is not assessed now,
not a negative finding. Source deferral does not determine cohort-2 membership;
its selection policy will be designed separately.

### D13 — Catalogue access and browsing experience

Decide whether all admitted candidates remain searchable even with no drawable
edges. Proposed default: searchable full catalogue, explicit coverage gaps,
and selected molecule/target neighbourhoods, with visible filter effects.
The 995-member proposal has 257 candidates without Supported or Preliminary
claims under its broad human basis. Choose the initial landing experience:
search/start selection, a featured neighbourhood, or a catalogue overview.
Rendering the whole network is not required by catalogue membership.

Status: decided (opening view 2026-09-12; searchable gaps accepted 2026-09-13).

Initial user answer: "why would there be molecuels without drawable evidence? opening view should start with the caffeine neighborhood."
Follow-up: the user accepted retaining searchable catalogue entries with no
drawable edges on 2026-09-13.

Adopted rule: open on the caffeine neighbourhood under the active filters.
Its exact edges reflect the adopted source/evidence policy, not an attempt to
reproduce the previous graph unchanged. All admitted candidates and preserved
seed molecules remain searchable even if they have no drawable edge.

Distinguish no eligible evidence found in ChEMBL 37, unresolved target/evidence,
and evidence hidden by current filters. Expose source-qualified gap reasons
and allow inspection of retained observations without requiring an existing
graph edge. D07's broader-assignment filter must reveal molecules with eligible
evidence only in that layer. Clinical admission never manufactures an edge.
The old 257-gap count is not a count for the adopted catalogue.

### D14 — Reproducibility and completion criteria

Choose whether the first implementation pins ChEMBL 37 and the saved indication
scope, as proposed, or refreshes sources and remeasures the selected policy.
The original raw MeSH cache is absent; fetching MeSH now creates a new snapshot.
Proposed completion requirements: versioned membership/evidence policies,
auditable admission and exclusion reasons, reconciled seed identities,
consistent evidence in graph/panels/ranking, retained provenance, and measured
browsing performance at the chosen size. Delegate schema/build mechanics and
performance implementation to the implementation agent, with a reversible
staged build and review before replacing the active generated artifacts.

Status: decided; implementation details delegated (2026-09-12).

User answer: "yea pin, the rest is up to you."

Adopted rule: pin ChEMBL 37 and use the saved MeSH descriptor classification
as the starting ontology input. Version the changed scope and the explicit
pain inclusions. Do not substitute a current MeSH fetch for the missing old
raw cache. If missing mappings require another source, record that provenance
and any snapshot difference explicitly.

Delegated completion criteria: reproducible candidate/evidence builds, counted
admission/exclusion reasons, source-native identity and provenance, reconciliation
of seed and cohort membership, consistent panels/graph/ranking/filter behavior,
meaningful regression checks for changed data semantics, and measured browsing
performance. Stage replacement artifacts reversibly, preserve historical
outputs, and report material differences before replacing active generated
artifacts. The current task remains decision logging; implementation will
follow the later user-requested prompt.

### D15 — Curated direction in the similarity score

D09 fixed what counts as an overlap and delegated the scoring weights. It said
nothing about *direction*, and the score it produced therefore read a pair of
opposites as a pair of near-twins: caffeine and adenosine share ADORA1, A2A,
A2B and A3, and sat second in each other's ranking at 3.60 against
theophylline's 4.50, while ChEMBL curates one an ANTAGONIST and the other an
AGONIST at the family covering exactly those four receptors. For a page whose
stated purpose is finding molecules that may act alike, that is the one error
class that states the reverse of the truth rather than merely ranking noisily.

Decide whether a curated mechanism should affect the score, and if so how.

Status: decided (2026-09-16).

User answer: "im wondering if we could/should incorporate the mechanism on the
shared targets, for example if it also blocks the target it should get a higher
score than if it just has no curated mechanism?" — then, on the proposal below,
"yea go with the first and second moves."

Adopted rule, in three parts.

*Presence of a curated mechanism does not earn extra score.* It is already in
the evidence weight under D08 — curated-and-replicated 1.0, replicated 0.9,
curated-only 0.75 — where it answers how well evidenced a claim is. Direction
answers how informative it is. Folding the second into the first would label
two quantities so they invite comparison, which is invariant 13.

*Opposition is detected, conservatively, and stated.* `OPPOSED_ACTIONS` in
`viz/index.html` lists the pairs of ChEMBL actions that are each other's
opposite, and `directionAt` returns one of three answers: opposite, not
opposite, or — where either side has no curated action — **null**, because the
question cannot be asked. This is deliberately not a direction taxonomy and
does not fold the 23 actions into families, which is the merge the curated
mechanism control refuses under D06. It answers one narrower question and
declines most of the time.

The conservatism is measured, not assumed. Of 12,964 shared-target overlaps
under the default filters, 6,725 carry a curated action on both sides and
1,723 of those carry two different ones — but only **508 are opposites**. The
rest are the same direction said twice (320 POSITIVE ALLOSTERIC MODULATOR
against POSITIVE MODULATOR), a matter of degree (186 ANTAGONIST against PARTIAL
AGONIST, 120 AGONIST against PARTIAL AGONIST), or the same net effect by
another route (193 INHIBITOR against RELEASING AGENT, which at a transporter
both raise what is outside the cell). A rule reading "different action" as
"disagrees" would demote three pairs that agree for every one that does not.

*A pair whose every known direction is opposite is scored at a quarter.* The
factor only ever goes down. Rewarding agreement would demote the 6,239
overlaps where ChEMBL has curated no direction on one side or the other,
turning its silence into a negative result — the failure the mechanism
control's banner already counts two costs apart to avoid. Opposition is
something ChEMBL asserted; agreement is partly a fact about how much of the
catalogue its curators reached. A pair that opposes at one shared target and
agrees at another is **not** demoted; that target says so on its own row.

`OPPOSED_PAIR_FACTOR = 0.25` is the one judgement number in this scoring that
is not read off the data. It is a quarter rather than zero because the two
molecules do share the target, which is a fact, and caffeine against adenosine
at the adenosine receptors is one of the more illuminating things here. What it
must not do is read as "these two act alike", which is the only claim the score
makes.

Direction is read at **every** shared target including the subsumed ones, and
that is load-bearing rather than incidental. The only row that knows caffeine
and adenosine point opposite ways is their shared curated claim at the family,
which is precisely the row the D09 subsumption rule zeroes; the four protein
rows carrying the whole of that pair's 3.60 have no curated direction at all. A
direction factor applied per scored row would have found nothing on the one
pair that most needed it.

Measured against the 2026-09-13 build: 998 of the 19,362 ranked rows carry an
opposed shared target, 980 are demoted, over **499 distinct molecule pairs of
9,681**, and **35 of 769 molecules get a different top neighbour**. The
examples read correctly without being told to — propranolol drops albuterol (a
β-agonist) for esmolol, dronabinol drops cannabidiol (curated NEGATIVE
ALLOSTERIC MODULATOR at CNR1) for nabilone, pilocarpine and xanomeline drop
atropine for each other and for acetylcholine, and progesterone drops
mifepristone. Caffeine's list is unchanged at the top and adenosine moves from
2nd at 3.60 to 6th at 0.90.

*Stated limitation.* The rule reaches only as far as ChEMBL's curation does.
Adenosine and istradefylline are genuine opposites at ADORA2A and are **not**
demoted, because adenosine's only curated direction in this build is at the
family and istradefylline's is at the single protein, so the two never meet at
one target. This is the same conservatism working as designed — a missing
direction is not a disagreement — and it means the 499 pairs are a floor rather
than a count of the opposites in the catalogue.

#### Amended 2026-09-17 — direction is read at the protein

*User instruction: "go ahead and implement 1a in docs/NEXT-STEPS-PROPOSAL.md".*

The stated limitation above is lifted. A curated action is now attributed to
every protein the target it is filed against covers — a SINGLE PROTEIN
contributes its own accession, a PROTEIN FAMILY or PROTEIN COMPLEX GROUP all of
its components' — and two molecules are compared at each protein their shared
targets cover (`pooledDirection` in `viz/index.html`). Adenosine and
istradefylline are demoted. So is the case that prompted the change: morphine's
nearest neighbour of 380 was **naltrexone**, over twelve shared rows on which
`directionAt` returned null every one, because morphine's AGONIST is at human
mu-opioid and naltrexone's ANTAGONIST at the human mu/kappa/delta family. It now
ranks 17th.

**This is not the D06 merge.** Nothing about it changes what a shared target is,
what it weighs, which rows the D09 subsumption rule zeroes, or what the canvas
draws, and no claim is redistributed from a set onto its members. It changes
which two actions are compared and nothing else — the same argument the
paragraph above makes for reading direction at subsumed rows.

Matched on the **accession**, never on a gene symbol. The prototype in
`analysis/probe/direction_recovery.mjs` pooled on the symbol so that orthologue
records would meet; the two keys recover the same 535 entirely-opposed pairs
among ATC-labelled molecules, with the symbol reaching 56 more comparable pairs
and demoting none of them further. Invariant 6 decides a tie that costs nothing.

Measured against the 2026-09-16 build at the default filters: rows with a
comparable direction go from 12,328 to 15,416 of 227,298, and **490 demoted
pairs become 876** of 113,649 — 389 gained and 3 released. The three released
are part of the case: trimipramine and tolazoline are both ANTAGONIST at three
adrenoceptors and opposed at one, so a pair agreeing three times out of four was
being quartered by the one-record view. **7 of 988 molecules get a different top
neighbour** — morphine and oxycodone drop naltrexone for buprenorphine,
buprenorphine drops naloxone for oxymorphone, nalbuphine drops aticaprant for
samidorphan, remoxipride drops the D2 agonist pramipexole for tiapride. The ATC
grade moves from top-1 37.5% / MRR 0.5035 to 37.8% / 0.5083, which is not the
reason for the change and is reported so that it is not mistaken for one.

#### Amended 2026-09-20 — the demotion is proportional, over `comparable`

*User decision, on the measured options below: "Grade it over comparable".*

NEXT-STEPS-PROPOSAL.md §1 flagged one thing to settle alongside the pooling:
what an opposed pair is demoted *on*. Three rules were graded against the ATC
key before the choice was made.

| rule | top-1 | MRR |
| --- | --- | --- |
| no direction factor at all | 37.1% | 0.4975 |
| binary, over comparable (as adopted 2026-09-17) | 37.8% | 0.5083 |
| **graded over comparable (adopted)** | **38.2%** | **0.5105** |
| graded over shared | 37.8% | 0.5065 |

*The demotion is now proportional.* A pair opposed at `opposed` of `comparable`
proteins is multiplied by `1 - 0.75 × (opposed / comparable)`, so an
entirely-opposed pair is unchanged at a quarter and a pair opposed at one of two
lands on 0.625. The old rule fired only at full opposition, which scored a
half-opposed pair exactly as though nothing were known about direction — an
all-or-nothing cliff in the middle of the one signal the rule carries. It
reaches 42 pairs and 84 ranked rows here, and **4 of 988 molecules** get a
different top neighbour: nalbuphine drops the pure antagonist samidorphan for
butorphanol, its own mixed agonist–antagonist class, and nalmefene drops the
partial agonist buprenorphine for samidorphan.

*The denominator is `comparable`, never `n_shared`.* A shared target carrying no
curated direction is an **unknown**, not an agreement. Dividing by everything
shared would let ChEMBL's silence dilute a demotion — clozapine and apomorphine
share 34 targets and are comparable at one, so that rule would score them as
near-identical on the strength of 33 proteins nobody has said anything about.
That is the mirror image of the failure this decision already refuses in the
other direction, and it grades below the rule it would replace.

*The worry that prompted the question was measured, not argued.* The concern was
that quartering on one comparable protein out of 34 shared is too thin. Checked
against the answer key: of 876 entirely-opposed pairs, **exactly one** is a
same-ATC-class pair, and of the 167 demoted on a single comparable protein while
sharing ten or more targets, **none** are. The exception is betahistine and
cinnarizine — an H1 agonist against an H1 antagonist, same clinical class and
opposite mechanism, which is the key being a proxy rather than this rule
misfiring.

*Stated cost, and what it turned out to be.* Haloperidol and aripiprazole went
from rank 4 to rank 29, on haloperidol's curated INVERSE AGONIST at the D2-like
family against aripiprazole's PARTIAL AGONIST at D2. Chased down, that was a
fault in `OPPOSED_ACTIONS` rather than in the factor, and the entry was removed
the same week — see the amendment below. The pair is back at rank 4.

#### Amended 2026-09-20 — PARTIAL AGONIST vs INVERSE AGONIST is not an opposite

*User decision, on the measurement below: "Remove it".*

Efficacy is a signed continuum — full agonist, partial agonist, zero for a
neutral antagonist, negative for an inverse agonist — so a partial agonist and
an inverse agonist do sit either side of neutral. The pharmacology supports the
entry. It was removed anyway, because ChEMBL does not use the label
systematically enough for the rule to mean what it says.

The whole catalogue carries **four INVERSE AGONIST claims**: haloperidol and its
own decanoate at the D2-like dopamine receptor, pitolisant at H3, and
pimavanserin at 5-HT2A. Against them sit **260 ANTAGONIST** claims and 25
PARTIAL AGONIST. At DRD2, 41 molecules are curated ANTAGONIST and 2 INVERSE
AGONIST; at HTR2A, 41 against 1. Most antipsychotics have inverse agonist
activity at D2 and ChEMBL records it for one of them.

So the entry encoded a curator's vocabulary. Against aripiprazole, a D2 partial
agonist:

| pair | D2 label | opposed | rank |
| --- | --- | --- | --- |
| haloperidol / aripiprazole | INVERSE AGONIST | yes, ×0.625 | 29 |
| chlorpromazine / aripiprazole | ANTAGONIST | no | 13 |
| risperidone / aripiprazole | ANTAGONIST | no | 3 |
| fluphenazine / aripiprazole | ANTAGONIST | no | 40 |

Four D2 blockers in the same relationship to the same partial agonist, one of
them demoted.

*What settles it is the parallel case, already decided the other way.* PARTIAL
AGONIST against ANTAGONIST is a matter of degree and deliberately not opposed —
**242 pairs** in this build. PARTIAL AGONIST against INVERSE AGONIST is the same
axis one notch further, and was **10 pairs, every one involving haloperidol or
its decanoate**. Only two positions are self-consistent: treat the whole
efficacy-degree axis as opposition, which means demoting those 242 and is what
the 508-of-1,723 measurement in the original entry argues against, or treat none
of it as opposition. The list now does the latter.

*Cost.* None measurable: the grade is identical with the entry and without it
(top-1 38.2%, MRR 0.5105), and none of the 10 affected pairs was a
same-ATC-class pair either way.

*Revisit when the direction data improves.* This is a judgement about ChEMBL's
curation rather than about receptors. Pimavanserin is marketed as a 5-HT2A
inverse agonist; if a 5-HT2A partial agonist enters the catalogue the opposition
would be real and unlabelled. A source that curates efficacy systematically —
GtoPdb, proposed in NEXT-STEPS-PROPOSAL.md §1b — is the condition under which
this should be reopened.

### D16 — CNS conditions MeSH files outside C10 and F03

The indication route reads scope off MeSH tree position: C10 Nervous System
Diseases and F03 Mental Disorders, plus the Pain tree and D02's explicit
neuropathic set. MeSH files some conditions a reader would call psychiatric
somewhere else. **Anxiety** (D001007) is an emotion under F01 Behavior, beside
the F03 disorder Anxiety Disorders (D001008). ChEMBL uses the emotion heading
for 182 indication records against 46 for the disorder, so bromazepam's
approval was invisible: the panel said "approved" over three phase-3 diseases.
120 parents reach phase 3 or approval for Anxiety and 108 of those already
carry ATC N, so the gap was mostly in what the page listed and what a condition
search found, not in membership.

Status: decided (2026-09-27).

User answer, on the finding and a proposal to add the misfiled headings by id:
"Yea go with 1."

Adopted rule: four descriptors join D02's explicit inclusion set, each by
mesh_id and with its own scope reason, `explicit_cns_heading`, since calling
them neuropathic would be false. Anxiety (D001007) and Depression (D003863),
the F01 emotion headings beside their F03 disorders; Smoking Cessation
(D016540), the F01 behaviour heading beside Tobacco Use Disorder; and
Anesthesia (D000758), the E03 procedure heading ChEMBL uses for anaesthetic
agents. No branch is opened. F01 also holds behaviours and emotions that are
not conditions, and E03 holds procedures. The phase-3 floor is not waived.
Selection policy 2.1.0.

Measured effect: 4 new members, all through Anxiety (naluzotan, valerian,
hawthorn leaf with flower, and ChEMBL's generic "benzodiazepine" record). The
cohort goes from 1,326 to 1,330.

Not adopted, and left for the expansion beyond ATC N and qualifying
indications: drugs that act in the brain but are filed under a symptom or
another body system. That covers the NK3 antagonists for hot flashes
(fezolinetant, elinzanetant), the central anorectics under Obesity
(benzphetamine, diethylpropion), and the 5-HT3/NK1 antiemetics under Nausea
and Vomiting. Admitting those headings whole would bring in more drugs that do
not act on the brain than drugs that do.

## Answer history

### 2026-09-12 — First decision round

Recorded the user's answers to D01–D14 verbatim in the corresponding entries.
Membership is now whole ATC N or Approved/Phase-3 indications in core plus
pain, explicitly including neuropathic pain and fibromyalgia, across all
molecule types. This supplements the seed catalogue. Active pharmacology
sources are limited to ChEMBL 37 for now. The initial view is caffeine.

At the end of this first round, answers were still pending for: D08's production evidence tiers;
D11's display of bounds/approximations and numerical eligibility of conditional
mass conversions; D13's searchable entries with no drawable evidence.

The original decision questions and old comparison table remain for historical
context. Their 995-candidate proposal and associated seed/gap counts must not
be reused as the selected policy's totals.

### 2026-09-13 — Remaining decisions accepted; prompt requested

User: "yes go with your suggestions for all three remaining choices. lets build the prompt now for opus 5"

Accepted D08's study-based tiers and visible source flags/conflicts; D11's
labelled bounds/approximate observations and conditional treatment of
unverified mass conversions; and D13's searchable entries without drawable
edges. No policy questions remain open. D02 still requires an implementation
audit of descriptor coverage and recomputed counts, not a new policy approval.

The boundary review now present in the workspace corroborates the neuralgia
scope discrepancy. It also documents that the whole saved Pain tree includes
angina and that loperamide still fails a Phase-3 indication floor. Apply the
adopted whole-pain scope with explicit admission labels; do not invent narrower
exceptions or grandfather loperamide into cohort 1. It remains a seed regardless.

## Implementation handoff

Written 2026-09-13: [Opus 5 implementation prompt](prompts/COHORT-1-IMPLEMENTATION-PROMPT.md).
The prompt uses the adopted rules above, supporting reports, analysis packages,
and production documentation. It delegates implementation and validation while
explicitly identifying the intentional changes to existing production behavior.
No implementation agent has been launched and no production artifacts changed
as part of writing this handoff.
