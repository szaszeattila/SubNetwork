# Cohort boundary review

September 12, 2026. Follow-up to the question about retaining opioids and
recovering useful molecules excluded by core scope. Recommendations below
are proposals; no membership policy or production data was changed.

> **Status, added 2026-09-17: still proposals, and counted against a baseline
> that has since moved.** Every extension delta below (+200, +99, +85 and the
> rest) is measured against the pre-adoption 2,245 / 995-candidate world of
> [COHORT-REPORT.md](COHORT-REPORT.md), not against the catalogue that was
> actually built. Nothing in the file said so.
>
> One finding here **was** acted on: this review is what caught the report's
> wrong claim that Neuralgia keeps an in-core placement, and it is correct —
> see [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), "The report's own prose was
> wrong about Neuralgia". The adopted scope carries the explicit inclusion set
> that follows from it.
>
> The larger recommendation — an independently defined **curated
> neuropharmacology route** — was not adopted and is still open. It is argued
> for on different and newer evidence in
> [NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) §3.

The audit uses ChEMBL 37 opened read-only and the original exported descriptor
classification. It reproduces the exact 2,245 baseline parent identities,
the 995-member small-molecule Phase 3/approved policy, and the 2,611 widest
union. It does not re-evaluate evidence tiers for additions. Mechanisms in
the examples are ChEMBL source annotations unless an external source is linked.

The reproducible script and row-level outputs are in
[`analysis/cohort1/boundaries/`](../analysis/cohort1/boundaries/).
Run `python3 analysis/cohort1/boundaries/audit.py` from the repository root.
`provenance.json` records input hashes and the pinned database identity.

Morphine is already admitted by core plus whole ATC N. Its family carries
N02AA01 and N02AA51. Fentanyl, oxycodone, codeine, tramadol, methadone and
buprenorphine also remain in both the unrestricted baseline and the 995-member
policy. Naloxone qualifies through indications, and naltrexone through ATC N
and indications. Thus the pain boundary does not exclude all opioid medicines.
Morphine is indeed used for acute and chronic pain, as its
[label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=300b6afd-bac8-32ca-e063-6294a90a12a7)
states. ATC N02A is the
[opioid subgroup](https://atcddd.fhi.no/atc_ddd_index/?code=N02A&showdescription=no).

However, whole ATC N does not guarantee complete opioid coverage in ChEMBL.
Levorphanol (CHEMBL592) has no ATC mapping on any of its five saved family
members and its only qualifying boundary indication is Pain, recorded at
phase 0.5. It therefore fails core, and still fails a Phase 3 pain extension.
This is an annotation coverage problem: its
[prescribing information](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=b2ab70e4-ca0c-4a73-9c98-974bf94e890c)
explicitly identifies it as an opioid analgesic for pain. Do not interpret
the database's indication phase as its complete real-world clinical status.

Loperamide has the same saved Pain phase 0.5 limitation. Its mu-receptor
pharmacology makes it a useful comparator, with its peripheral context
visible; the [label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=74b9893a-18c3-4117-85c2-edab8e7b3b3b)
describes binding in the gut wall. Retaining it does not imply morphine-like
brain exposure or clinical effects.

The general-pain extension recovers nine parents outside the unrestricted
core with curated opioid-target mechanisms: levorphanol, loperamide,
ADL-5859, ADL-5747 free base, faxeladol, benzhydrocodone, axomadol,
difelikefalin and oxycodegol. These are source parents across molecule
categories and phases, not nine approved small molecules.

A separate query of curated mechanisms at mu, delta, kappa, nociceptin and
the mu/kappa/delta family finds 65 parents: 41 in core, nine recovered by the
widest scope, and 15 still outside even the widest scope. The latter include
diphenoxylate, difenoxin, alvimopan, naldemedine, eluxadoline, nalfurafine and
asimadoline. This is a targeted curated-mechanism query, not a census of all
opioids or experimental opioid binders. Its source mechanism IDs are retained
in `curated_opioid_membership.csv`.

The main report's explanation also contains a factual inconsistency. It says
Neuralgia D009437 stays core via C10.597.617.470. The actual saved row instead
has C10.668.829.600 and C23.888.592.612.664, plus F02/G11 placements, and
`in_core_scope=0`. Postherpetic neuralgia D051474 is also excluded. The current
[NLM descriptor](https://meshb.nlm.nih.gov/record/ui?dcmsLinks=true&ui=D009437)
agrees with the relevant saved placements; current web data were not used to
recompute membership. Fibromyalgia D005356 is excluded under muscle/NMJ,
and generic Headache D006261 under general pain. Other descriptors, such as
migraine disorders, can still qualify separately. The report's claim that
the boundary preserves nervous-system pain should not guide the decision.

These are concrete omissions I would prioritize for a neuropharmacology
catalogue:

| Boundary | Excluded examples and why they matter | Effect of retaining Phase 3/approved small-molecule rules |
|---|---|---|
| General pain | Levorphanol and loperamide; benzhydrocodone (opioid-family agonist); granisetron (5-HT3A antagonist); ralfinamide (sodium/calcium-channel, NMDA and MAO-B annotations) | Pain expansion admits benzhydrocodone, granisetron and ralfinamide; levorphanol/loperamide still need another admission route |
| General pain / peripheral disease | T-62 (adenosine A1 modulator), Z160 (N-type calcium-channel blocker), ADL-5747 (delta-opioid agonist) | Their listed boundary indications are Phase 2, so changing scope alone at Phase 3 does not rescue them |
| Peripheral disease | Pirenzepine (M1 muscarinic antagonist) | Listed peripheral indications are Phase 2 |
| Muscle/NMJ | Esreboxetine (norepinephrine transporter inhibitor), dolasetron (5-HT3A antagonist), dichlorphenamide (carbonic anhydrase inhibitor) | Each has qualifying Phase 3 muscle-branch indications; esreboxetine and dolasetron enter through fibromyalgia |
| CNS oncology | Mibefradil (T-type calcium-channel blocker) | Its qualifying oncology indication is Phase 1; a pharmacology route is preferable to admitting all oncology solely to recover it |

Suzetrigine is another pain/PNS omission worth including in a broader nervous
system and pain comparison. Its saved Pain indication is Phase 3, so the pain
extension admits it under the tighter policy. It is a peripheral NaV1.8
analgesic, with [FDA approval in January 2025](https://www.fda.gov/news-events/press-announcements/fda-approves-novel-non-opioid-treatment-moderate-severe-acute-pain).
This example supports a broader nervous-system catalogue; it does not establish
central action.

Pregabalin, duloxetine, carbamazepine, baclofen, dantrolene, neostigmine,
pyridostigmine and amifampridine already qualify in the tighter core policy.
Ziconotide's CHEMBL4594214 parent qualifies by ATC N in the unrestricted core
but is typed Protein and excluded by small-molecules-only. A separate
ziconotide-acetate parent is outside core; this is also an identity review
issue, not evidence for two distinct active pharmacologies.

The measured membership changes are:

| Extension, separately versus core | All categories, no phase floor: additions to 2,245 | Small molecules, ATC N or qualifying Phase 3/approved indication: additions to 995 |
|---|---:|---:|
| General pain | 200 | 99 |
| Peripheral/cranial nerve | 85 | 20 |
| Muscle/NMJ | 93 | 38 |
| CNS oncology | 78 | 7 |
| All four together, deduplicated | 366 | 134 |

Individual deltas overlap and must not be summed. These are membership counts,
not counts with Supported evidence. In the tighter policy, an addition may
already be in the unrestricted baseline through an earlier-phase core
indication; `boundary_additions.csv` exposes that distinction. Cebranopadol,
for example, is in unrestricted core but needs the pain extension at Phase 3.

My recommendation is to retain whole ATC N, include clinically relevant pain
indications, explicitly restore neuralgia/postherpetic neuralgia and
fibromyalgia, and add an independently defined curated neuropharmacology
route. Start that route with opioid receptor ligands, including antagonists
and peripheral comparators, and assess other relevant target families in the
same way. A clinical phase floor should apply to the clinical route, not
silently discard curated pharmacology-route members. Peptides/endogenous
ligands need a deliberate category choice as well.

The entire Pain tree is broader than the phrase "pain medicines": the saved
descendants include angina, admitting isosorbide dinitrate and
hydrochlorothiazide, among other cardiovascular drugs. For reproducibility,
either accept that breadth with visible admission labels or define and measure
explicit descriptor exceptions. Do not claim a narrower pain scope while
quoting the +200/+99 whole-tree counts. I would avoid using oncology or the
whole muscle branch as blanket routes merely to recover particular useful
ligands; the curated route addresses those omissions more directly.

This also answers the broader three-cohort question: the clinical catalogue
cannot guarantee coverage of mechanistically relevant medicines, endogenous
ligands or research tools. The brainstorm's clinical plus curated
neuropharmacology union remains the stronger design. A broad experimental
cohort can extend that later, with its evidence thresholds measured separately.
