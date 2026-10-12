# A nootropics wiki, placed against the catalogue

2026-10-11. **Measurement; adopts nothing.** No membership policy was changed.
The figures are from `analysis/wiki_comparison/comparison.csv` against the
active build of 2026-10-11 and ChEMBL 37; where they disagree with
[../CLAUDE.md](../CLAUDE.md)'s Status, Status is right.

The question was the user's: of the compounds
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
squashed name took HU-210 to its enantiomer, dexanabinol. The eight found are
rejected with their reasons, and every row carries a confidence: of the 1,417
placed in ChEMBL, 1,140 are `high`, 146 `medium` and 131 `low`. Name variants
the four routes do not know are missed outright — *Alpha-GPC*, *Levoamphetamine*
and *9-Me-BC* are among the unidentified, though the first two are in ChEMBL
as choline alfoscerate and levamfetamine.

**363 names were never looked up in PubChem**, because PubChem throttled the
run (HTTP 429 on every request for over half an hour). They are 225 of the
wiki's formats and blends, 72 psychedelics and a scatter elsewhere; the
nootropic and peptide sections were looked up in full. `pubchem_lookup.py`
resumes them.

## What it found

| section | in catalogue | in ChEMBL, has target data | in ChEMBL, no target data | identified, not in ChEMBL | unidentified | not looked up | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cognition & nootropic | 104 | 135 | 82 | 48 | 43 | 0 | 412 |
| Peptides & bioregulators | 9 | 37 | 22 | 49 | 103 | 0 | 220 |
| Metabolic & performance | 20 | 66 | 29 | 20 | 43 | 0 | 178 |
| Cardiovascular & metabolic | 47 | 42 | 10 | 4 | 6 | 0 | 109 |
| Anti-infective & immune | 33 | 67 | 7 | 1 | 11 | 0 | 119 |
| Psychiatric & neuro-clinical | 212 | 64 | 32 | 15 | 8 | 21 | 352 |
| Psychedelics & entactogens | 17 | 34 | 25 | 26 | 1 | 72 | 175 |
| Hormones, GI & derm | 36 | 71 | 11 | 1 | 0 | 15 | 134 |
| Other clinical | 9 | 32 | 6 | 2 | 0 | 16 | 65 |
| Nutrients & botanicals | 3 | 6 | 4 | 2 | 0 | 14 | 29 |
| formats & blends | 29 | 68 | 48 | 21 | 0 | 225 | 391 |
| **all** | **519** | **622** | **276** | **189** | **215** | **363** | **2,184** |

"Has target data" is a crude proxy for whether an entry would draw anything: a
ChEMBL curated mechanism, or an exact pChEMBL value at a single protein from a
publication. It does not ask whether that protein has anything to do with the
brain.

### 1. A quarter is already here, and mostly well evidenced

519 of the 2,184 are catalogue entries; 388 of those have a Supported claim and
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

898 wiki compounds are in ChEMBL and not in the catalogue. They stopped at
Phase 2 or earlier and carry no ATC N code, which is the admission test
working as written (D01) rather than a gap in the data. **310 of them have a
ChEMBL curated mechanism, and 367 are GtoPdb ligands** — the population
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

276 are in ChEMBL with no target data. The nootropic section's include 12
of the wiki's 20 racetams (phenylpiracetam, aloracetam, coluracetam,
nefiracetam, fasoracetam, dimiracetam and others), noopept, picamilon, unifiram
and sunifiram. Most are ChEMBL records with no name
and two repurposing screens. In the catalogue they would join the 263 entries
already saying ChEMBL 37 has no eligible evidence: searchable, honest, and
similar to nothing, because similarity here is shared targets.

### 4. A further 189 are real substances ChEMBL does not have

Identified by FDA UNII or PubChem and absent from ChEMBL 37: semax and selank
and their N-acetyl forms, dihexa, epithalon, pinealon, the other Khavinson
peptides with a defined sequence, TB-500, MOTS-c, KPV, fladrafinil, bemethyl,
hemantane, PRL-8-53, the NBOH/NBOMe and designer-benzodiazepine analogues.
Every molecule here is keyed on a ChEMBL parent, so none of them can be an
entry without a non-ChEMBL identity — and none would have evidence from any
source the pipeline reads.

### 5. 215 could not be identified at all

Mostly what is not one substance: herbal extracts (kava, valerian,
passionflower), the Khavinson "bioregulator" products named by organ
(*Cerebramin*, *Ventfort*), protein hydrolysates (cerebrolysin, cortexin) and
brand names. A few are misses of this matcher, not of the sources (above).

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
- It does not say what a new route would cost in screening noise. The 310
  curated-mechanism compounds are counted across every therapeutic area and
  were not filtered to a target scope; NEXT-STEPS §3's target scope is the
  thing that would.
- Its matching misses some names and was wrong on eight it found; the
  comparison file says which route placed each row.
