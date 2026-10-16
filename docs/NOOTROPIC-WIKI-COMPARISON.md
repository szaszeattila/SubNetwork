# A nootropics wiki, placed against the catalogue

2026-10-11. **Measurement; adopts nothing.** No membership policy was changed.
The figures are from `analysis/wiki_comparison/comparison.csv` against the
active build of 2026-10-11 and ChEMBL 37; where they disagree with
[../CLAUDE.md](../CLAUDE.md)'s Status, Status is right. The sections from
*Against the Phase 1 floor (D21)* on, added 2026-10-13, are measured against
the `phase1-admission` branch's build instead, and say so.

**Since 2026-10-14 two of its sections are policy.** The user adopted the
compounds the *Cognition & nootropic* and *Psychiatric & neuro-clinical*
sections place in ChEMBL outside the catalogue, and asked for the wiki to be
cited as their source of entry: D25 in [COHORT-2.md](COHORT-2.md). That did not
make this document's name matches policy. Each was reviewed against ChEMBL's
structure and written into `config/cohort1_selection.json` as an id; 221 were
kept, one corrected and 11 refused, and D25 says which and why. On 2026-10-15
a third section, *Psychedelics & entactogens*, followed the same way (D26: 75
kept, two corrected, six refused). Everything up to *The listed entries
against other public lists* is still the measurement it was; that last
section, added 2026-10-15, is measured against the D26 build of 2,748
entries.

The first question was the user's: of the compounds
[scientificsean.wiki](https://www.scientificsean.wiki/) lists — a community wiki
of nootropics, peptides, psychiatric drugs, psychedelics, supplements and
blends — which are in this catalogue, which could be, and what stands in the
way of the rest. It follows the discussion of semax, bromantane and flmodafinil,
none of which is a member: semax is not in ChEMBL at all, and bromantane's
ChEMBL record is two repurposing screens with nothing at a brain target.

The wiki is not a source here and nothing it says is read as pharmacology. Its
list is used as a list of names somebody wants to look up, and its section and
class labels are carried along only so the results can be read by them.

## How names were placed

2,184 compounds, from the wiki's class table. Each name was placed by the first
of: an exact ChEMBL preferred name; an exact ChEMBL synonym; the name with
punctuation and spaces dropped; the FDA UNII preferred name, through its
InChIKey to ChEMBL's structure; and last, PubChem's name service, through its
InChIKey. A match on the InChIKey's first block alone — the same skeleton in
another stereo or isotope form — is kept and labelled as such.

**This is matching by name, which invariant 15 forbids for anything entering
the database, and it was wrong where expected.** PubChem took Irisin (a protein)
to iridin, Cardiogen (a Khavinson tetrapeptide) to levocarnitine, and hCG to a
small molecule; ChEMBL's synonym list took AMT to 3-amino-3-deoxythymidine; a
squashed name took HU-210 to its enantiomer, dexanabinol; PubChem took MET
(methylethyltryptamine) to methionine and DGL (deglycyrrhizinated licorice) to
D-glutamate. The eleven found are rejected with their reasons, and every row
carries a confidence: of the 1,490 placed in ChEMBL, 1,140 are `high`, 146
`medium` and 204 `low`. Name variants
the four routes do not know are missed outright — *Alpha-GPC*, *Levoamphetamine*
and *9-Me-BC* are among the unidentified, though the first two are in ChEMBL
as choline alfoscerate and levamfetamine.

PubChem throttled the first run (HTTP 429 on every request for over half an
hour) with 363 names to go; `pubchem_lookup.py` was rerun once the block
lifted, and every name has now been asked. 128 of those 363 resolved.

## What it found

| section | in catalogue | in ChEMBL, has target data | in ChEMBL, no target data | identified, not in ChEMBL | unidentified | total |
|---|---:|---:|---:|---:|---:|---:|
| Cognition & nootropic | 104 | 135 | 82 | 48 | 43 | 412 |
| Peptides & bioregulators | 9 | 37 | 22 | 49 | 103 | 220 |
| Metabolic & performance | 20 | 66 | 29 | 20 | 43 | 178 |
| Cardiovascular & metabolic | 47 | 42 | 10 | 4 | 6 | 109 |
| Anti-infective & immune | 33 | 67 | 7 | 1 | 11 | 119 |
| Psychiatric & neuro-clinical | 213 | 68 | 40 | 18 | 13 | 352 |
| Psychedelics & entactogens | 18 | 47 | 41 | 49 | 20 | 175 |
| Hormones, GI & derm | 36 | 74 | 13 | 4 | 7 | 134 |
| Other clinical | 9 | 39 | 7 | 5 | 5 | 65 |
| Nutrients & botanicals | 3 | 6 | 4 | 6 | 10 | 29 |
| formats & blends | 32 | 77 | 53 | 37 | 192 | 391 |
| **all** | **524** | **658** | **308** | **241** | **453** | **2,184** |

Every compound behind these counts is listed by `sections.py`, one CSV per
section, with the column it is counted under, its placement and what ChEMBL
holds for it, and whether it is a member under D21 (below). Since 2026-10-15
those files, the wiki's list and the full comparison files are kept in
`db/cache/sciwiki/`, out of the repository, because together they copy the
wiki's arrangement, which its terms refuse
([COMPOUND-LIST-TERMS.md](COMPOUND-LIST-TERMS.md)); the repository's
`comparison.csv` and `comparison_d21.csv` leave out its section and class.

"Has target data" is a crude proxy for whether an entry would draw anything: a
ChEMBL curated mechanism, or an exact pChEMBL value at a single protein from a
publication. It does not ask whether that protein has anything to do with the
brain.

### 1. A quarter is already here, and mostly well evidenced

524 of the 2,184 are catalogue entries; 391 of those have a Supported claim and
38 have no eligible evidence. Of the wiki's 412 cognition and nootropic
compounds, 104 are members — every one of its 12 ADHD drugs, the clinical
eugeroics (modafinil, armodafinil, adrafinil, pitolisant, solriamfetol), the
cholinesterase inhibitors and nicotinic agonists, the orexin antagonists, and
the racetams and Russian drugs that reached an admission route — piracetam,
aniracetam, oxiracetam, pramiracetam, phenibut and mebicar by an ATC N code,
emoxypine by a Phase 3 stroke indication. Several of those are members with
little to draw: the four racetams have no exact pChEMBL value at any single
protein, and emoxypine has no eligible evidence.

### 2. Most of what is missing is in ChEMBL and fails the clinical rule

966 wiki compounds are in ChEMBL and not in the catalogue. Nearly all stopped
at Phase 2 or earlier with no ATC N code, or are approved for something outside
the scope; that is the admission test working as written (D01) rather than a
gap in the data. **314 of them have a ChEMBL curated mechanism, and 386 are
GtoPdb ligands** — the population
[COHORT-2.md](COHORT-2.md)'s open item 5 and the curated-route proposal in
[COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md) are about.

In the nootropic section, 48 have a curated mechanism: the ampakines
(CX-1739, farampator, mibampator, TAK-653, pesampator), the nicotinic and
muscarinic agonists that stopped in Phase 2 (GTS-21, TC-5619, ABT-089,
talsaclidine, MK-7622, TAK-071), huperzine A, the H3 antagonist irdabisant,
the 5-HT6 antagonist masupirdine. A curated-mechanism route with no phase floor
would admit these with a direction attached, which is what
[NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) §3 says the catalogue is short
of.

The same 48 also include the five HDAC inhibitors the wiki files as
nootropics (vorinostat, panobinostat, belinostat, entinostat, romidepsin),
sibutramine and clenbuterol. Admitted, they would be drawn by their oncology,
appetite and β2 targets, because that is what they are curated at. A route
defined by *which list a compound is on* imports the list's idea of what
belongs; a route defined by targets does not.

### 3. Admitting the racetam-like compounds would add entries and no edges

308 are in ChEMBL with no target data. The nootropic section's include 12
of the wiki's 20 racetams (phenylpiracetam, aloracetam, coluracetam,
nefiracetam, fasoracetam, dimiracetam and others), noopept, picamilon, unifiram
and sunifiram. Most are ChEMBL records with no name
and two repurposing screens. In the catalogue they would join the 263 entries
already saying ChEMBL 37 has no eligible evidence: searchable, honest, and
similar to nothing, because similarity here is shared targets.

### 4. A further 241 are real substances ChEMBL does not have

Identified by FDA UNII or PubChem and absent from ChEMBL 37: semax and selank
and their N-acetyl forms, dihexa, epithalon, pinealon, the other Khavinson
peptides with a defined sequence, TB-500, MOTS-c, KPV, fladrafinil, bemethyl,
hemantane, PRL-8-53, the NBOH/NBOMe and designer-benzodiazepine analogues.
Every molecule here is keyed on a ChEMBL parent, so none of them can be an
entry without a non-ChEMBL identity — and none would have evidence from any
source the pipeline reads.

### 5. 453 could not be identified at all

192 of them are the wiki's formats and blends. Mostly what is not one
substance: herbal extracts (kava, valerian,
passionflower), the Khavinson "bioregulator" products named by organ
(*Cerebramin*, *Ventfort*), protein hydrolysates (cerebrolysin, cortexin) and
brand names. A few are misses of this matcher, not of the sources (above).

## Against other public lists

The user's second question: how the wiki's list compares with others like it.
Six were retrieved on 2026-10-11 and run through the same matcher (without
PubChem); `prepare_lists.py` records each retrieval and cleaning rule, and the
lists themselves are not kept here, being other sites' content.

| list | what it is |
| --- | --- |
| Nootropics Expert | one author's "most comprehensive nootropics list", mostly supplements; an affiliate site |
| PsychonautWiki | a harm-reduction community wiki of psychoactive substances, from its API; also its *Nootropic* category |
| TripSit | harm-reduction factsheets, mostly recreational drugs and research chemicals; also its *nootropic* tag |
| Wikipedia | the English *Category:Nootropics*, less the articles about the idea (Neuroenhancement, Eugeroic, lists) |
| Wikidata | items whose *subject has role* or *has use* is nootropic (Q742487). The instance and subclass routes were dropped: coffee carries the role, so they return coffee brands |

Examine.com (behind a bot checkpoint), Erowid (its robots.txt requires written
permission to scrape), DrugBank (licensed) and the r/Nootropics wiki (403) were
not retrieved. What each list's terms allow, and lists not compared here, are
in [COMPOUND-LIST-TERMS.md](COMPOUND-LIST-TERMS.md).

| list | compounds | placed in ChEMBL | also on the wiki | in the catalogue | on neither | wiki entries it has |
|---|---:|---:|---:|---:|---:|---:|
| Nootropics Expert | 110 | 68 (62%) | 103 (94%) | 33 (30%) | 6 (5%) | 108 |
| PsychonautWiki, all | 373 | 160 (43%) | 262 (70%) | 86 (23%) | 102 (27%) | 264 |
| PsychonautWiki, *Nootropic* | 25 | 20 (80%) | 24 (96%) | 15 (60%) | 1 (4%) | 24 |
| TripSit, all | 548 | 293 (53%) | 270 (49%) | 146 (27%) | 231 (42%) | 274 |
| TripSit, *nootropic* | 28 | 20 (71%) | 27 (96%) | 11 (39%) | 1 (4%) | 27 |
| Wikidata, nootropic role | 162 | 140 (86%) | 102 (63%) | 42 (26%) | 57 (35%) | 104 |
| Wikipedia, *Category:Nootropics* | 149 | 113 (76%) | 87 (58%) | 31 (21%) | 59 (40%) | 88 |

"Also on the wiki" counts a ChEMBL parent in common, an equal name, or one of
20 reviewed equivalences in `compare_lists.py` (`SAME_AS_WIKI`: Centrophenoxine
is meclofenoxate, Tropoflavin is 7,8-DHF, Kava Kava is Kava). Before them,
Nootropics Expert read 79% rather than 94%. A name neither matcher nor review
caught still reads as "not on the wiki".

**The wiki is the widest of them by a distance, and contains the nootropic
lists almost whole.** At 2,184 it is four times TripSit and twenty times
Nootropics Expert, and it has 94–96% of every list that means *nootropic* in
the supplement-user's sense. What those lists have and it lacks is a handful of
herbs (holy basil, oat straw, polygala).

**Most of it is on no other list.** 472 of its 2,184 entries are on at least one
of the six; 256 of its 412 nootropics, 213 of its 220 peptides and 352 of its
391 formats and blends are on none. Its distinctive part is the long tail:
research compounds sold as nootropics, peptides, and products.

**Wikipedia and Wikidata mean something else by the word.** About 60 entries
each are not on the wiki, and they are mostly drug-development compounds tried
for cognition — A-349821, ABT-418, basmisanil, iclepertin, PF-03654746,
radequinil — 43 and 51 of them in ChEMBL, 8 each with a curated mechanism. The
encyclopaedia's nootropic is a research category; the wiki's is a shopping one.

**Its clinical coverage is chosen, not systematic.** TripSit and PsychonautWiki
have 278 and 111 entries the wiki lacks, mostly designer drugs and research
chemicals, but also ordinary medicines: diazepam, flurazepam, the barbiturates,
dihydrocodeine. 47 of TripSit's are catalogue members. The wiki lists
alprazolam, clonazepam and lorazepam, and not diazepam.

**The catalogue covers about a quarter of every list** — 21% of Wikipedia's,
26% of Wikidata's, 30% of Nootropics Expert's, 60% of PsychonautWiki's small
*Nootropic* category, whose members are mostly approved drugs. That is the
wiki's own result again: whatever a list means by nootropic, most of it has not
reached Phase 3 for a nervous-system indication or an ATC N code.

PsychonautWiki's API includes class pages (*Benzodiazepines*, *2C-x*) as
substances, and they are counted as entries; TripSit's aliases are used for
matching.

## Where the wiki's list probably comes from

2026-10-12, the user's question. **The wiki does not say**, so this is an
inference from what the list contains, and it is unconfirmed. Its home and
*About* pages say it is run by Scientific Sean LLC, that "nothing here is written by a
doctor, medical professional, or scientist in any capacity", "Powered by Claude", and grows
"continuously"; neither describes how a compound gets on the list. Its
*Suppliers* page lists 14 partner outlets, some through affiliate links:
research-peptide and research-chemical shops (RUO, Kimera Chems, Moglabs,
WorldwideBioResearch, Limitless Biochem, Peptira, AllAmericanAmino), RUPharma
for Russian medicines and Khavinson bioregulators, PCT.Zone for prescription
drugs, Nootropics Depot, iHerb and Amazon for supplements.

That catalogue fits the parts of the list no other public list has. The
Khavinson products named by organ, cerebrolysin and cortexin, semax, selank,
bemethyl and bromantane are RUPharma's and Limitless's lines. Dihexa, 9-Me-BC,
TAK-653, J-147, BPC-157, KPV and BAM15 are the research shops' named examples.
The peptide and blend sections, 213 of 220 and 352 of 391 on no other list,
read like product listings rather than substances. The rest fits public lists
taken whole: the wiki holds 94–96% of each list that means *nootropic* in the
supplement-user's sense. And the clinical sections fit what a prescription
outlet stocks, which would explain why they are selective rather than
systematic (alprazolam and not diazepam). If that is right, the list is a
catalogue of **what can be bought**, with pages written about each item. That
is why the share of it that ChEMBL knows about falls off with each section.
The operator's listed contact could confirm it; nothing here depends on it.

## What it would take to admit most of it

The user's follow-up: what sources or rules would bring most of these
compounds into the network, for instance a Phase 1 floor in place of Phase 3.
`admission_rules.py` applies each rule to the wiki's ChEMBL placements and to
ChEMBL as a whole, so the cost is stated beside the gain.

| rule | wiki added | wiki covered | of 2,184 | catalogue grows by |
|---|---:|---:|---:|---:|
| *today* (ATC N, or in-scope indication at Phase 3) | — | 524 | 24% | — |
| in-scope indication, phase ≥ 2 | 183 | 707 | 32% | 787 |
| **in-scope indication, phase ≥ 1** | 234 | 758 | 35% | 1,117 |
| in-scope indication, any phase | 240 | 764 | 35% | 1,146 |
| any indication, phase ≥ 1 | 482 | 1,006 | 46% | 7,526 |
| any ATC code | 245 | 769 | 35% | 2,556 |
| curated mechanism (any target) | 314 | 838 | 38% | 4,617 |
| GtoPdb ligand | 387 | 911 | 42% | 6,229 |
| in-scope phase ≥ 1, or curated, or GtoPdb | 568 | 1,092 | 50% | 9,632 |
| publication data at any protein | 568 | 1,092 | 50% | 618,102 |
| every ChEMBL placement (ceiling) | 966 | 1,490 | 68% | |

**A Phase 1 floor is a small lever.** It roughly doubles the indication route
(1,117 more entries, most of them Phase 2) and takes the wiki from 24% to 35%.
That is because 726 of the 966 wiki compounds ChEMBL has but the catalogue does
not have no in-scope indication at any phase: 183 stop at Phase 2, 51 at Phase 1 and 6 at
Early Phase 1. Its 67 nootropic additions are the clinical failures —
nefiracetam, fasoracetam, the ampakines (CX-516, CX-717, farampator, TAK-653),
GTS-21, ABT-089, huperzine A, masupirdine — plus choline, uridine and
phosphatidylserine, which have in-scope trials.

**Dropping the scope buys more than dropping the phase, at seven times the
size**: any indication at Phase 1 reaches 46% and adds 7,526 entries, nearly
all of them developed for something other than the brain. A curated-mechanism or GtoPdb route reaches 38–42%,
and the three together reach exactly half the wiki for about 9,600 entries.
Only a rule with no curation in it at all, publication data at any protein,
reaches the same half, by adding six hundred thousand screening compounds.

**No ChEMBL rule reaches more than 68%.** 694 entries are not in ChEMBL: 241 are
real substances absent from it, and 453 are blends, extracts and products. The
other sources that could hold them:

- **The identified 241** (semax, dihexa, the NBOMes, designer benzodiazepines):
  PubChem and FDA UNII give them an identity, but neither carries a curated
  target claim. Where binding data exists, it is in **BindingDB** and the
  **PDSP Ki database**, the two sources D12 deferred. For the psychedelics in
  particular, PDSP is the one with the most data. Admitting them needs a molecule
  identity not keyed on a ChEMBL parent, which is a schema change.
- **Peptides** (the Khavinson set, BPC-157, TB-500): there are sequences in
  UniProt and peptide databases, and almost no receptor-level data anywhere.
  They would be entries that draw nothing.
- **Blends, extracts and products**: not one substance, so not a node. A
  product could at most point to its ingredients, which is a different
  feature.

So most of the wiki can be brought in only by a rule that is not about the
brain. The rules that are — a lower phase floor inside the scope, a curated
mechanism at a brain target (NEXT-STEPS §3) — add the wiki's clinical-failure
compounds and leave its distinctive long tail out. That tail is what the shops
sell, and nobody has measured what it does.

## A route defined by brain targets

The user's next question: admit anything linked to a brain target, with no
clinical phase, and from outside ChEMBL where possible. `brain_targets.py`
measures it.

**What a brain target is has to be decided first, and the catalogue cannot
supply it.** The curated targets of every member are 516 human proteins, and
they are not a brain set: members admitted by a pain, angina or MS indication
bring COX-1 and -2, PDE5, the glucocorticoid and oestrogen receptors, H2, the
proton pump and tubulin. With that set, 44 of the additions were the wiki's
hormones and GI drugs. The stand-in used below is narrower: 184 proteins at
which a drug with an ATC N code, outside the local-anaesthetic and
simple-analgesic branches, has a curated claim. It still includes some
peripheral proteins. An expression signal (HPA, the unbuilt backfill under
*Not done*) would be the principled set, but expression says where a protein
is, not that a drug acting on it acts in the brain.

| route (ChEMBL compounds), at the 184 | wiki added | wiki covered | of 2,184 | catalogue grows by |
|---|---:|---:|---:|---:|
| GtoPdb: the primary target is one | 24 | 548 | 25% | 155 |
| ChEMBL curated mechanism at one | 82 | 606 | 28% | 445 |
| PDSP Ki: an exact Ki at one | 72 | 596 | 27% | 538 |
| GtoPdb: any interaction at one | 121 | 645 | 30% | 1,247 |
| **ChEMBL curated, or any GtoPdb interaction** | 163 | 687 | 31% | 1,541 |
| ChEMBL: ≤ 1 µM at one, in 2+ publications | 116 | 640 | 29% | 7,740 |
| ChEMBL: any exact published value at one | 333 | 857 | 39% | 132,906 |

With the 516-protein set the same routes read 33–45% of the wiki and grow the
catalogue by 612 to 277,640.

**The evidence bar decides the size, not the phase.** A curated bar, ChEMBL's
mechanism or a GtoPdb interaction, adds about 1,500 entries. Every one of them
would draw at least one line, many with a curated direction. That is the
coherent version of the idea and doubles the catalogue. A measured bar is
another kind of catalogue. Replication at 1 µM adds 7,740, mostly
medicinal-chemistry series measured at one receptor. Any published value adds
132,906. The 72-entry PDSP figure is a floor: its ligands are placed by name,
because without RDKit its SMILES cannot be turned into InChIKeys.

**It reaches the wiki's research compounds and not its distinctive tail.** Of
the 163 wiki additions, 70 are nootropics, 34 psychiatric drugs and 13
psychedelics: ampakines, nicotinic and muscarinic agonists, H3 and 5-HT6
antagonists, tool compounds. The tail stays out. ChEMBL's records for the
racetams, noopept, bromantane and phenylpiracetam hold no value at any of these
proteins. And the sources that go beyond ChEMBL hardly reach the 683 wiki
entries ChEMBL lacks: GtoPdb has 239 ligands at the 184 proteins with no
ChEMBL record, and 6 of them are wiki entries (AC-90179, LY503430, T-495,
muscarinic toxins 3 and 7, T440). PDSP's names match 9 (5-APB, 6-APB,
desoxypipradrol, ethylone, methiopropamine and others). One of those, DMT, is
in ChEMBL as CHEMBL12420 and was missed by the wiki matcher, so "not in
ChEMBL" includes some misses. Semax, selank, dihexa, the Khavinson peptides and
the designer benzodiazepines have no receptor-level data in any of the three.

**What adopting it would take.** A new route in
`config/cohort1_selection.json` with the target set versioned beside it. GtoPdb
read at build time rather than as a backfill, since membership would depend on
it. A molecule identity not keyed on a ChEMBL parent for GtoPdb's and PDSP's
own compounds, which is a schema change. PDSP resolved by structure, which
needs RDKit, and D12 reopened. And the similarity harness regraded, because a
catalogue twice the size changes every target's prevalence.

## Against the Phase 1 floor (D21)

2026-10-13, the user's question: compare the `phase1-admission` branch, whose
D21 ([COHORT-2.md](COHORT-2.md) on that branch) lowers the indication route's
floor from Phase 3 to Phase 1, against the wiki. The same placement was run
against that branch's build (selection policy 3.0.0, 2,452 entries) into
`comparison_d21.csv`; the placement itself does not depend on the build, so
every difference below is membership.

| section | before | with D21 | of |
|---|---:|---:|---:|
| Cognition & nootropic | 104 | 171 | 412 |
| Peptides & bioregulators | 9 | 21 | 220 |
| Metabolic & performance | 20 | 39 | 178 |
| Cardiovascular & metabolic | 47 | 68 | 109 |
| Anti-infective & immune | 33 | 52 | 119 |
| Psychiatric & neuro-clinical | 213 | 239 | 352 |
| Psychedelics & entactogens | 18 | 25 | 175 |
| Hormones, GI & derm | 36 | 56 | 134 |
| Other clinical | 9 | 24 | 65 |
| Nutrients & botanicals | 3 | 7 | 29 |
| formats & blends | 32 | 56 | 391 |
| **all** | **524 (24%)** | **758 (35%)** | **2,184** |

**The branch does exactly what `admission_rules.py` predicted.** 758 wiki
compounds and a catalogue grown by 1,117, against a prediction of 758 and
1,117. 234 came in, all by the indication route, and none left. 36 members
already in by ATC N alone (aniracetam, oxiracetam, pramiracetam, adrafinil,
ipidacrine, meclofenoxate, tofisopam among them) now also qualify by
indication, and pentoxifylline and rolipram are members rather than retained
seeds. No existing member's evidence status changed.

**Most of the newcomers draw something.** Of the 234, 152 have a Supported
claim, 34 only Preliminary, 12 only the broader layer or limited evidence, and
36 have no eligible evidence. The nootropic section's 67 are the
clinical-failure compounds the earlier section named: the ampakines
(farampator, mibampator, TAK-653, CX-516), the nicotinic and muscarinic
agonists (GTS-21, ABT-089, ABT-126, TC-5619, ispronicline, talsaclidine,
MK-7622, TAK-071), huperzine A, irdabisant, masupirdine, tesofensine — mostly
Supported. The ones with nothing to draw are the ones whose ChEMBL record is
the trial and not the pharmacology: nefiracetam, fasoracetam, CX-717, NSI-189,
phosphatidylserine. Seven psychedelics came in (LSD, 5-MeO-DMT, ibogaine,
mephedrone, methylone), and so did the HDAC inhibitors and clenbuterol,
which the earlier section warned would be drawn by their oncology and β2
targets.

### What is left, and why

| ChEMBL has it, outside the catalogue | no target data | measured only | curated mechanism | all |
|---|---:|---:|---:|---:|
| no indication in ChEMBL at all | 220 | 242 | 18 | 480 |
| indications, none in scope, none approved | 38 | 44 | 50 | 132 |
| approved, for something outside the scope | 6 | 5 | 103 | 114 |
| an in-scope indication below Phase 1 | 0 | 2 | 4 | 6 |
| **all** | **264** | **293** | **175** | **732** |

Beside these, 241 are identified and absent from ChEMBL and 453 are not
identified, unchanged, since D21 reads ChEMBL alone.

**D21 has spent the clinical lever.** 726 of the 732 have no in-scope
indication in ChEMBL at any phase, so no phase floor reaches them: dropping it
altogether adds 6 wiki compounds for 29 entries. Two thirds of what is left
has no ChEMBL indication of any kind. That is the racetams (phenylpiracetam,
coluracetam, aloracetam), unifiram and sunifiram, the stimulant analogues
(flmodafinil, ethylphenidate, 4F-MPH, 3,4-CTMP), and most of the psychedelics.
A further 246 are drugs developed or approved for something else, including
sibutramine, vincamine, metrifonate and the GLP-1 agonists.

Each route measured above, applied to the D21 build:

| route, on top of D21 | wiki added | wiki covered | catalogue grows by |
|---|---:|---:|---:|
| GtoPdb: the primary target is a brain target | 12 | 770 (35%) | 123 |
| **ChEMBL curated mechanism at a brain target** | 34 | 792 (36%) | 289 |
| PDSP Ki: an exact Ki at a brain target | 55 | 813 (37%) | 494 |
| GtoPdb: any interaction at a brain target | 81 | 839 (38%) | 1,144 |
| ChEMBL curated, or any GtoPdb interaction, at one | 96 | 854 (39%) | 1,342 |
| ChEMBL: ≤ 1 µM at a brain target, in 2+ publications | 86 | 844 (39%) | 7,653 |
| any ATC code | 161 | 919 (42%) | 2,227 |
| curated mechanism, any target | 175 | 933 (43%) | 3,956 |
| any indication, phase ≥ 1 | 248 | 1,006 (46%) | 6,409 |
| GtoPdb ligand, any target | 262 | 1,020 (47%) | 5,825 |
| every ChEMBL placement (ceiling) | 732 | 1,490 (68%) | |

"Brain target" is the 184-protein stand-in defined above. D21 took most of
what the target routes used to add: the curated-or-GtoPdb route added 163
before it and adds 96 now, for 1,342 entries. The cheapest remaining step is
ChEMBL's own curated mechanism at a brain target, which adds 34 for 289 entries,
every one with a curated direction.

## Sources that could close the rest

The user's follow-up question: which public sources could narrow the gap?
Measured where it was cheap, and otherwise checked for licence and access. The
gap has four parts, and each needs a different kind of source:

1. **A clinical record ChEMBL lacks**, for the 480 ChEMBL compounds with no
   indication at all.
2. **Target data**, for the 264 with none in ChEMBL.
3. **An identity outside ChEMBL**, for the 241 it does not have, with target
   data as well.
4. **Not one substance** — 453 blends, extracts and products. No source turns
   these into nodes.

### Clinical records

**ClinicalTrials.gov, read directly, finds trials ChEMBL has not made into
indications, but most of them would admit drugs the scope was not written to
admit.** Each passes the scope's test on paper, being filed under an in-scope
condition. What is trialled is mostly not a drug for a brain disorder: a statin
in stroke, a kinase inhibitor in glioma, an anti-androgen in Kennedy's disease,
a supplement with a mood endpoint, or a compound listed as an intervention
beside the drug actually under test. ChEMBL's
indications come from the registry, but only where a curator has taken a
trial's condition as the drug's indication. `ctgov_route.py` asks the
registry instead, for every wiki compound outside the catalogue, by name.
It keeps a study only when an intervention name contains the compound's name
as whole words. It reads the condition's MeSH ids against the adopted scope,
applying the scope's rules to all 31,110 MeSH 2026 descriptors; on the 2,869
the saved scope holds, the two agree on all of them.

| wiki compounds outside the catalogue, names over four characters | in ChEMBL | not in ChEMBL |
|---|---:|---:|
| an in-scope trial at Phase 1 or later | 126 | 19 |
| an in-scope trial at Early Phase 1 | 1 | 1 |
| an in-scope trial, phase "not applicable" only | 21 | 7 |
| trials, none in scope | 146 | 29 |
| no trial naming it | 373 | 151 |
| all | 667 | 207 |

Taken as a rule, that would add 145 of the wiki's compounds, from 758 (35%)
to 903 (41%); what it would add to the catalogue outside the wiki was not
measured. **Read compound by compound, it is mostly the scope's soft edges
and co-medication.** Tallied across those compounds' trials, the in-scope
conditions are led by stroke (43), Brain Neoplasms (35), Pain (26),
Hereditary Sensory and Autonomic Neuropathies (21, not reviewed, and an odd
heading to lead with) and X-linked bulbo-spinal atrophy (15: Kennedy's
disease, trialled with the anti-androgens). What they admit is anti-androgens, aromatase inhibitors,
statins, insulins, enoxaparin, antibiotics trialled in meningitis, kinase
inhibitors in glioma, and supplements (lysine, gelatin, iodine, beta-carotene)
with depression or cognition endpoints. A trial's condition is not a drug's
indication; ChEMBL's curation is what makes the difference, and this reads
around it. The 65 names of four characters or fewer were set apart, since
ALA, MDA and NAD+ match far too much.

**The wiki's distinctive tail is not in the registry either.** Semax,
noopept, bromantane, dihexa, sunifiram, coluracetam, flmodafinil, bemethyl and
picamilon have no registered trial; selank has two that do not name it as an
intervention. The registry's useful finds are few: **cerebrolysin** (40
trials, mostly stroke, Phase 2–4, which needs an identity ChEMBL does not
give it and is a hydrolysate, not one substance), **psilocin** (four,
alongside psilocybin), phenylpiracetam's single Phase 1 sleep-deprivation
trial, metadoxine, SAGE-324 and GB-115. As an admission source it would need
a curator's judgement per trial, which is what ChEMBL already supplies.

**Wikidata's ATC codes add almost nothing.** Wikidata carries 4,454 ATC
statements, 558 of them N codes. Only 18 sit on a ChEMBL parent ChEMBL gives
no N code, mostly a stereoisomer or a form ((R,R)-tramadol, cidoxepin,
Z-flupentixol). Three are wiki gap compounds: DMAE, pipotiazine (the earlier
finding again), and JWH-018, a synthetic cannabinoid with no WHO ATC code,
which looks like a Wikidata mistake and was not traced.

**National approvals are the real gap for the Russian drugs, and no open
source for them was found.** Phenotropil (phenylpiracetam), bemitil, ladasten
(bromantane), noopept, semax, selank, cortexin and cerebrolysin are or have
been registered medicines in Russia, and ChEMBL records no indication for
any of the ones it has. The Russian State Register (GRLS) is a public website, but
no bulk export or licence for one was found, and a 2022 tender set out to move
it onto another government platform. DrugCentral publishes approval lists for FDA, EMA and PMDA
(Japan) as CSV, but not for Russia, and its download page names no licence.
Admitting by a foreign approval would also be a new admission route, D01's
to change.

### Target data

**PubChem BioAssay adds nothing for the tail.** It was sampled with twenty
of the wiki's distinctive compounds. Semax, selank, dihexa, BPC-157, bemethyl,
fladrafinil and the designer benzodiazepines have no results at all.
Phenylpiracetam, fasoracetam and sunifiram have 700–900 each, and they are
the NIH screening library's inactive HTS results. The only target-level
actives are 25I-NBOMe's three 5-HT2 Ki values, from a 2022 paper ChEMBL
already holds (CHEMBL5108009, the same three activities). Licence aside (public, but set by
each depositor), PubChem is ChEMBL plus screening negatives here.

**PDSP Ki is the one measured source that reaches new compounds.** At a
brain target it covers 55 of the wiki's gap compounds that ChEMBL has, and 9
the wiki matcher did not place in ChEMBL, by name (5-APB, 6-APB,
desoxypipradrol, ethylone, methiopropamine, MT-2; DMT among the 9 is in
ChEMBL and a matcher miss). It is free to download and has no formal licence
text. Its compounds carry names, CAS numbers and SMILES, so placing them by
identifier needs RDKit to turn SMILES into InChIKeys. D12 deferred it.

**BindingDB is the largest source not yet measured.** Data its own staff
curate is CC BY 3.0; what it imports from ChEMBL is CC BY-SA 3.0 and is
ChEMBL again (invariant 5: 97% republished in the legacy pipeline). It is
keyed on InChIKey, and comes as a TSV or SDF dump. Its curated part is
patents and articles ChEMBL has not taken, which is where NPS and
medicinal-chemistry series would be, if anywhere. Measuring it is a download and
the same script as PDSP.

**GtoPdb reaches 6 compounds outside ChEMBL** (AC-90179, LY503430, T-495,
muscarinic toxins 3 and 7, T440). It is already pinned.

**The aggregators repackage what is here.** Papyrus (CC BY-SA 4.0), ExCAPE-DB,
Probes & Drugs (CC BY-SA 4.0), Pharos and the Broad Repurposing Hub assemble
ChEMBL, GtoPdb, BindingDB, PubChem and DrugCentral. Probes & Drugs' compound
sets are the one useful part: reviewed probe and drug lists with InChIKeys,
which could serve as an admission list for tool compounds. Text-mined
resources (STITCH) and those with non-commercial or unstated terms (TTD, CTD,
DrugBank) do not fit an open CC BY-SA project.

### What no source reaches

**Semax, selank, the Khavinson peptides, BPC-157, TB-500, dihexa, the
racetams' mechanism and the designer benzodiazepines** have no receptor-level
data in any open, identifier-keyed source checked: not ChEMBL, GtoPdb, PDSP,
or PubChem BioAssay. Their literature exists, much of it in Russian journals
ChEMBL does not abstract. The only way in is curation by hand: a claim this
project writes, citing the paper, under a provenance of its own. That is a
policy question, not a source, and it collides with "prefer data that can be
refreshed rather than hand-curated".

### Ranked, by what each would add per unit of work

1. **ChEMBL's curated mechanism at a brain target** — no new source, a route.
   34 wiki compounds, 289 entries, all drawing a directed line. Needs the
   brain-target set decided and versioned.
2. **PDSP Ki, resolved by structure** — about 55 + 9 wiki compounds, about 500
   entries; needs RDKit, an identity not keyed on a ChEMBL parent for the 9,
   and D12 reopened. The psychedelic and NPS section is where it reaches.
3. **BindingDB's curated part** — unmeasured; the one plausible source of new
   measurements for NPS and research compounds. Measure before deciding.
4. **ClinicalTrials.gov read directly** — 145 wiki compounds by the numbers,
   but mostly off-scope drugs carried in by a trial's secondary condition;
   useful only as a list of candidates for review (cerebrolysin, psilocin),
   not as a rule.
5. **A foreign-approval route** (GRLS, PMDA via DrugCentral) — the right
   answer for the Russian drugs, but no open bulk source was found and it is a
   new admission rule.

Every source here gives the 241 compounds outside ChEMBL either no data or a
name match. Admitting them is the schema change named above, a molecule
identity not keyed on a ChEMBL parent, before it is a source question.

## A catalogue finding on the way

**Pipotiazine is not a member; its palmitate ester is, with no evidence.**
ChEMBL files ATC N05AC04 on pipotiazine palmitate (`CHEMBL2106439`), which is
its own parent, and not on pipotiazine (`CHEMBL398880`), which carries the
measurements — 12 single proteins. So the depot ester is an entry with
`no_eligible_evidence` and the antipsychotic it releases is outside. Whether
other long-acting esters do the same was not measured here; it would be a
sweep of ATC N codes held only by an ester whose parent compound has no code.

## What this does not answer

- It does not say any of these compounds act in the brain, or alike. The wiki's
  sections are its own and are not evidence; ChEMBL's records are evidence only
  as far as the cohort pipeline already treats them.
- It does not say what a new route would cost in screening noise. The 314
  curated-mechanism compounds are counted across every therapeutic area and
  were not filtered to a target scope; NEXT-STEPS §3's target scope is the
  thing that would.
- Its matching misses some names and was wrong on eleven it found; the
  comparison file says which route placed each row.

## The listed entries against other public lists

2026-10-15, the user's question: how Wikidata, Wikipedia, TripSit and
PsychonautWiki compare with the catalogue now that it holds the wiki's three
sections (D25, D26), and which of the compounds the wiki brought in those
lists also have. Measured against the D26 build: 2,748 entries, 296 of them
`listed_only`. `compare_lists.py` places every list entry as before and now
also says whether its ChEMBL parent is one the wiki brought in
(`molecule_listings`); its per-molecule output, `listed_on_lists.csv`, stays
beside the lists, out of the repository.

**What was compared.** PsychonautWiki and TripSit are the 2026-10-11 downloads,
both already whole lists of psychoactive substances. Wikipedia and Wikidata
were refreshed and widened by `fetch_lists.py`, since their nootropic lists
alone say nothing about the psychedelics section:

| list | what it is |
| --- | --- |
| Wikipedia, nootropics | *Category:Nootropics*, its pages only — the 2026-10-11 rule, refreshed |
| Wikipedia, psychoactive | *Category:Psychedelic drugs* and every category below it (phenethylamines, tryptamines, lysergamides, arylpiperazines), with *Entactogens*, *Dissociative drugs*, *Deliriants* and *Cathinones* |
| Wikipedia, designer drugs | *Category:Designer drugs* and its four subcategories |
| Wikidata, nootropic | items whose *subject has role* or *has use* is nootropic — the 2026-10-11 rule, refreshed |
| Wikidata, psychoactive | the same for psychedelic drug, hallucinogen, empathogen-entactogen, dissociative (two items) and stimulant |

A Wikipedia article is placed through its Wikidata item's InChIKey where the
item has one (761 of the psychoactive category's articles, 807 of the
designer-drug one's), and by its title otherwise. Topic articles, templates,
books, combinations and products were dropped by a reviewed list in
`prepare_lists.py` (*Arylcyclohexylamine*, *PiHKAL*, *Borax combo*, *Gray
death*, one person's biography); plants and fungi were kept, as the wiki lists
them too (*Atropa belladonna*). Wikidata files few compounds under a
psychoactive role: 119 items for the six, against Wikipedia's 1,042 articles.

### The lists against the catalogue now

| list | compounds | in ChEMBL | also on the wiki | in the catalogue | by a clinical route | entered from the wiki | in ChEMBL, outside |
|---|---:|---:|---:|---:|---:|---:|---:|
| PsychonautWiki, all | 373 | 160 | 262 | 141 (38%) | 97 | 44 | 19 |
| PsychonautWiki, *Nootropic* | 25 | 20 | 24 | 18 (72%) | 16 | 2 | 2 |
| TripSit, all | 548 | 293 | 270 | 207 (38%) | 161 | 46 | 86 |
| TripSit, *nootropic* | 28 | 20 | 27 | 19 (68%) | 14 | 5 | 1 |
| Wikidata, nootropic role | 161 | 140 | 102 | 93 (58%) | 65 | 28 | 47 |
| Wikidata, psychoactive roles | 115 | 90 | 48 | 46 (40%) | 24 | 22 | 44 |
| Wikipedia, *Nootropics* | 149 | 124 | 87 | 79 (53%) | 55 | 24 | 45 |
| Wikipedia, psychoactive | 1,042 | 376 | 134 | 88 (8%) | 29 | 59 | 288 |
| Wikipedia, *Designer drugs* | 967 | 387 | 157 | 90 (9%) | 26 | 64 | 297 |

"By a clinical route" counts members of the cohort and one seed, theobromine,
on TripSit and Wikidata; "entered from the wiki" is D25 and D26.

**The catalogue's share of every list has about doubled since 2026-10-11.**
Against the 1,335-entry build it held 86 of PsychonautWiki's entries, 146 of
TripSit's, 42 of Wikidata's nootropics and 31 of Wikipedia's; now 141, 207, 93
and 79. On the harm-reduction lists most of the gain is the wiki's listing (44
of PsychonautWiki's 55, 46 of TripSit's 61); on the nootropic lists about half
is (28 of Wikidata's 51, 24 of Wikipedia's 48), and the rest D21's Phase 1
floor.
Wikipedia's nootropic list also places better than before (124 in ChEMBL, from
113), because its articles now come with their items' InChIKeys.

**The psychoactive lists are reached mostly through the wiki.** Of the 88
Wikipedia psychoactive articles and 90 designer drugs the catalogue holds, 59
and 64 are listed entries; without D25 and D26 it would hold 29 and 26 — for
the first MDMA, LSD, psilocybin, DMT, ketamine and the NMDA-antagonist and
anticholinergic drugs, for the second modafinil and its analogues, six
benzodiazepine-type drugs, mephedrone and methylone. Both categories are still mostly
outside: 288 and 297 of their compounds are in ChEMBL and not in the
catalogue, and 666 and 580 were not placed in ChEMBL at all.

### Which listed entries the lists also have

| | Cognition & nootropic | Psychedelics & entactogens | Psychiatric & neuro-clinical | all |
|---|---:|---:|---:|---:|
| listed entries | 144 | 75 | 77 | 296 |
| on Wikipedia | 31 | 59 | 11 | 101 |
| on Wikidata | 28 | 18 | 4 | 50 |
| on TripSit | 11 | 31 | 4 | 46 |
| on PsychonautWiki | 7 | 33 | 4 | 44 |
| **on at least one of the four** | **43** | **62** | **15** | **120** |
| on all four | 0 | 14 | 0 | 14 |
| on none | 101 | 13 | 62 | 176 |

Nootropics Expert adds two the four lack, paraxanthine and phenylalanine.

**The psychedelics section is the part of the wiki the other lists share.** 62
of its 75 listed entries are on at least one of the four, and 14 are on all
four: 2C-B, 2C-C, 2C-E, 2C-I, 2C-P, 2C-T, 2C-T-2, 2C-T-7, 2C-T-21, 3C-E, DOI,
MDA, mescaline and psilocin. Another 13 are on three, among them 25I-NBOMe,
DOM, DOC, escaline, proscaline, MDAI, deschloroketamine and cathinone. 24 are
on Wikipedia or Wikidata and neither harm-reduction list — the tryptamines
4-HO-DET, 4-HO-MiPT, 5-MeO-DiPT and DiPT, 3-HO-PCP and 4-MeO-PCP, AL-LAD and
ETH-LAD, DOB, ergine, GBL — and three are on a harm-reduction list only
(Bromo-DragonFLY, 1,3-butanediol, salvinorin B methoxymethyl ether). The 13
on none are the section's terpenes and plant constituents (α-pinene,
β-caryophyllene, limonene, linalool, nootkatone, parthenolide, ursolic acid,
bilobalide, carvacrol, cycloastragenol) and three it files as psychoactive
that no list does: brompheniramine, alfetamine and N,N-dimethylphenethylamine.

**A third of the cognition section is on another list, and mostly on the
encyclopaedia's.** 43 of 144. Four are on three lists: 4-FA, coluracetam,
noopept and theacrine. 26 are on two, mostly the racetams, ampakines and
research stimulants the nootropic categories carry (aloracetam, cebaracetam,
phenylpiracetam, IDRA-21, sunifiram, unifiram, tulrampator, ethylphenidate,
4F-MPH, 3,4-CTMP, flmodafinil, P7C3, 7,8-DHF). 28 of the 43 are on Wikipedia
or Wikidata only. The 101 on none are drug-development compounds the wiki
files as nootropic — CX-546, CX-614, LY404187, SB-271046, PNU-120596, the
orexin antagonists vornorexant and nivasorexant, the muscarinic agonists
sabcomeline, milameline and alvameline — with HDAC inhibitors (belinostat,
entinostat, trichostatin A) and flavonoids and plant extracts (apigenin,
baicalein, honokiol, hypericin, rosemary extract).

**The psychiatric section is almost entirely the wiki's own.** 15 of 77: the
designer benzodiazepines (flubromazepam and pyrazolam on three lists,
phenazepam on two, diclazepam and gidazepam on one), the opioids desomorphine,
ethylmorphine and 7-hydroxymitragynine, harmine and harmaline, arketamine, and
three development compounds Wikipedia covers (aptiganel, indeloxazine,
suritozole). The 62 on none are neurosteroids and pheromone steroids
(pregnanolone, THDOC, androstenol, estratetraenol), second-generation
antihistamines (bilastine, ebastine, levocetirizine), antipsychotics and
antidepressants approved in Japan or Russia (perospirone, timiperone,
tandospirone, pipofezine, pirlindole) and research ligands (WAY-100635,
norbinaltorphimine, siramesine).

**Where the lists agree with the wiki, ChEMBL has least.** Of the 120 listed
entries on another list, 17 have a Supported claim and 55 no eligible evidence;
of the 176 on none, 65 and 54. The lists share the wiki's recreational and
research chemicals, which ChEMBL holds a structure for and seldom measures; what
only the wiki lists is mostly development compounds, which ChEMBL has assayed.
Agreement between lists says a compound is used, not that it is understood.

**What the harm-reduction lists have that neither the wiki nor the catalogue
does.** 77 of TripSit's entries are in ChEMBL, outside the catalogue and not on
the wiki: phenethylamines the wiki skips (2C-G, 2C-T-4, DOET, DOPR, Aleph,
4-MTA), aminorex, synthetic cannabinoids (AB-FUBINACA, AB-CHMINACA, AM-2201),
fentanyl analogues and nitazenes, and designer benzodiazepines (bromazolam,
delorazepam). PsychonautWiki has 12, among them **PCP and salvinorin A**: the
wiki lists four PCP analogues and salvinorin B's methoxymethyl ether but
neither parent drug, and no clinical route admits them, so the catalogue holds
the analogues and not the compounds they are analogues of. Ibotenic acid,
rolicyclidine and diphenidine are the others of the 12 a reader would look
for.

**Limits.** PsychonautWiki's and TripSit's entries are placed by name (TripSit's
aliases help), so a name neither matcher knows reads as "not in ChEMBL".
PsychonautWiki counts class pages (*2C-x*) as entries. Wikipedia's categories
take an article wherever an editor filed it, so *Doxylamine* is a deliriant
there, as it is on the wiki. A connectivity match on a list's InChIKey counts
as the same compound, which can join enantiomers the wiki keeps apart.

The lists, as downloaded and as name files, and both outputs are in
`db/cache/lists/` (`raw/` from 2026-10-11, `raw/2026-10-15/`, and
`names/2026-10-15/`):

```bash
python3 analysis/wiki_comparison/fetch_lists.py db/cache/lists/raw/2026-10-15
python3 analysis/wiki_comparison/prepare_lists.py db/cache/lists/raw db/cache/lists/raw/2026-10-15 db/cache/lists/names/2026-10-15
python3 analysis/wiki_comparison/compare_lists.py db/cache/lists/names/2026-10-15
```

## The lists brought in (D27)

2026-10-16, the user's two comments on the table above: bring in every
compound in its "in ChEMBL, outside" column and say where each came from,
citing each list by its terms; and cite the open list, not the sci-wiki, for
the compounds in its "entered from the wiki" column. Adopted as D27 in
[COHORT-2.md](COHORT-2.md), with the review in
[DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) (2026-10-16) and the citations in
[COMPOUND-LIST-TERMS.md](COMPOUND-LIST-TERMS.md). `open_listings.py` wrote the
four lists' entries into the selection policy from `lists_overlap.csv`.
Measured against the D27 build, 3,293 entries:

| list | compounds | in ChEMBL | in the catalogue | by a clinical route | entered from a list | entered from the wiki | in ChEMBL, outside |
|---|---:|---:|---:|---:|---:|---:|---:|
| PsychonautWiki, all | 373 | 160 | 159 (43%) | 97 | 62 | 0 | 1 |
| PsychonautWiki, *Nootropic* | 25 | 20 | 20 (80%) | 16 | 4 | 0 | 0 |
| TripSit, all | 548 | 293 | 287 (52%) | 161 | 126 | 0 | 6 |
| TripSit, *nootropic* | 28 | 20 | 20 (71%) | 14 | 6 | 0 | 0 |
| Wikidata, nootropic role | 161 | 140 | 139 (86%) | 65 | 74 | 0 | 1 |
| Wikidata, psychoactive roles | 115 | 90 | 87 (76%) | 24 | 63 | 0 | 3 |
| Wikipedia, *Nootropics* | 149 | 124 | 123 (83%) | 55 | 68 | 0 | 1 |
| Wikipedia, psychoactive | 1,042 | 376 | 358 (34%) | 29 | 329 | 0 | 18 |
| Wikipedia, *Designer drugs* | 967 | 387 | 371 (38%) | 26 | 345 | 0 | 16 |

"Entered from a list" counts entries in the catalogue because some list names
them, this one or another; "entered from the wiki" is now 0 on every one of
the four, as the second comment asked, since an entry any of them carries is
cited by them and not by the sci-wiki. **What is still in ChEMBL and outside
is what the review refused**, 46 entries naming 30 compounds across the lists:
racemates ChEMBL holds only as single enantiomers (MT-45, 6-MAPB, MDPV,
4-methylaminorex), names reaching several stereoisomers (dichloropane, LSZ,
CP 47,497), and the synonyms ChEMBL gives the wrong compound (2C-B-AN, G-4).
PCP and salvinorin A, which the section above found outside, are in.

The sci-wiki now cites 176 entries, those no open list carries: 101 of the
cognition section's, 62 of the psychiatric section's and 13 of the
psychedelics section's, by the section counts above.
