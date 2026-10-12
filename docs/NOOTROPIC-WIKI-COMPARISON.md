# A nootropics wiki, placed against the catalogue

2026-10-11. **Measurement; adopts nothing.** No membership policy was changed.
The figures are from `analysis/wiki_comparison/comparison.csv` against the
active build of 2026-10-11 and ChEMBL 37; where they disagree with
[../CLAUDE.md](../CLAUDE.md)'s Status, Status is right.

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
not retrieved.

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
