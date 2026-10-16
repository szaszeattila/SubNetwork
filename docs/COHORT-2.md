# Cohort 2

Cohort 1 was built from ChEMBL 37 alone and deferred every other source (D12 in
[COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md)): "we will come up with cohort 2
that may use these databases". This is that cohort's decision record, numbered
on from cohort 1's.

**Scope, as the user set it on 2026-09-27:** cohort 2 imports from GtoPdb, the
IUPHAR/BPS Guide to Pharmacology, in two steps. First the **mechanism** — a
direction on the molecule–target pairs cohort 1 already has. **New molecules
come later**, as a separate step. Worked in the `cohort-2` worktree.

Why GtoPdb first, and why its action rather than its interactions, is argued in
[NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) §1b and
[SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md) §5: D15 can only compare two
molecules where both have a curated direction, and ChEMBL gives one on 1.5% of
this catalogue's molecule–target pairs.

---

### D17 — GtoPdb's curated action, as a direction only

**Decision.** Import GtoPdb's `Type` and `Action` for every ligand–target
interaction that lands on a pair the catalogue already has a claim for, and
read it as a direction beside ChEMBL's. It adds no molecule, target, claim,
tier or affinity. This revisits D12's deferral for GtoPdb alone.

Whether a GtoPdb action may count as curated support was left open here and
answered by D18, for primary targets only.

**What was built.**

- `scripts/resolve_cohort_gtopdb_actions.py`, a backfill run after a build like
  the MeSH and trial ones, writing `gtopdb_interactions` and the
  `gtopdb_actions` key of `build_manifest`. Release **2026.3** (published
  2026-09-16), pinned by the files' own version line, cached under
  `db/cache/gtopdb/2026.3/`, sha256 in the manifest. Bumped on 2026-10-14 to
  **2026.3.1** (published 2026-10-12), which changes nothing in this
  catalogue: its 25 new interaction rows and 40 new ligands are all outside
  it, and the 2,749 stored rows and 739 claims are identical column for
  column. Its one new (Type, Action) pair is mapped below.
- Matched by identifier only. The ligand by exact InChIKey, else by a ChEMBL id
  naming exactly one parent; two routes disagreeing drops the ligand. The target
  by UniProt accession, to one SINGLE PROTEIN record, or — for a multi-subunit
  GtoPdb target — only to a PROTEIN COMPLEX with exactly the same accessions,
  never fanned out onto the subunits (fan-out manufactures shared targets).
- `ACTION_MAP`, every (Type, Action) pair in 2026.3 mapped by hand to ChEMBL's
  `action_type` vocabulary so the viewer's `OPPOSED_ACTIONS` reads both
  sources; "Neutral", "Binding", "Mixed" and the like map to no direction. A
  pair a future release adds is stored undirected and listed in the manifest.
  2026.3.1 added one, ('Antibody', 'Activation'), on denecimig at coagulation
  factor IX, mapped to ACTIVATOR as ('Activator', 'Activation') is.
- The export carries a `gtopdb` block; the viewer folds its directions into
  `directionIndex` only where the pair has a claim the filters show, names the
  curator in every sentence about an opposition, and shows GtoPdb's own words
  and a ligand link in the edge and pair panels. Credited on the page under CC
  BY-SA 4.0.

**Measured, against the 2026-09-27 build.**

| | ChEMBL only | with GtoPdb |
|---|---:|---:|
| molecule–target pairs with a direction | 1,034 | 1,930 (+896, on 308 molecules) |
| molecule pairs D15 can compare | 7,721 | 10,550 of 113,972 |
| molecule pairs sharing targets with no direction | 93.2% | 90.7% |
| pairs entirely opposed (quartered) | 872 | 1,302 (592 added, 162 released) |
| harness top-1 / top-5 / top-10 | 38.2 / 66.8 / 76.3% | 38.2 / 67.5 / 77.0% |
| harness MRR | 0.5105 | 0.5114 |

No newly quartered pair is a same-ATC-class pair. Where both curators direct a
pair they agree 286 times in 289 at GtoPdb primary targets and 96 in 100
elsewhere; the one error shape found is in
[DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) (2026-09-27).

**Licence and access.** The GtoPdb database is ODbL and its contents CC BY-SA
4.0. Commercial organisations pay access fees; this project is not one.
Registration arrived in August 2026 and the site says anonymous access will
end; the bulk CSVs still downloaded without a login on 2026-09-27. The cache
is what keeps a rerun possible after that.

**Rejected alternatives,** with their numbers in the data-quality log:
ChEMBL's per-activity `action_type` (+1,800 pairs, but it names the assay's
readout — every triptan an "antagonist"), and MeSH pharmacological actions
(filed per molecule, never per target).

---

### D18 — GtoPdb primary targets are curated support

**Decision (user, 2026-09-27).** Where GtoPdb marks a target as a ligand's
*primary* target, that is curated support, as a ChEMBL curated mechanism is.
The backfill writes one Supported claim per molecule, target and basis in its
own role, `gtopdb` (tier reason `gtopdb_primary_target`), so the two curators
never overwrite or impersonate each other. Non-primary rows stay directions
only (D17).

**Why primary only.** A primary-target flag is an expert saying "this is how the
drug works" — the same statement ChEMBL's `drug_mechanism` makes. The other rows
are mostly affinities from the papers ChEMBL already abstracts, which is not
independent evidence, and they hold GtoPdb's one known error shape (vilazodone
"agonist" at D2, D3 and H1). Where both curators direct a pair GtoPdb agrees with
ChEMBL 286 times in 289 at primary targets and 96 in 100 elsewhere.

**What it did.** 528 claims on 333 molecules: 419 at pairs already Supported, 75
Preliminary pairs now Supported, and 34 new lines where ChEMBL had no claim — a
curator's assertion at an unmeasured target, which is what a ChEMBL curated
claim there already is, not an edge manufactured from a measurement. Three
molecules moved to `has_supported`; `evidence_status` is re-derived from the
claims exactly as the build derives it, and nothing else moved. With D19, the
grade is ATC top-1 38.7%, top-10 77.8%, MRR 0.5159 and MeSH top-1 46.8%, MRR
0.6068 (from 0.5114 and 0.6005 under D17 alone); D18's own share is ATC −0.0007
and MeSH +0.0073.

### D19 — a partial agonist against an antagonist is half an opposite

**Decision (user, 2026-09-27).** PARTIAL AGONIST against ANTAGONIST or INVERSE
AGONIST counts as half an opposed protein in D15's proportional demotion — a pair
opposed only that way at its one comparable protein scores ×0.625, not ×0.25 and
not ×1. Partial against full agonist is never opposed. `HALF_OPPOSED_ACTIONS` in
the viewer; every sentence names it as a partial agonist against an antagonist.
D15's revisit condition — "a source that curates efficacy systematically" — was
GtoPdb, and it is what put the question.

*Literature (2026-09-27).* Efficacy is one continuum — Stephenson 1956;
Black & Leff 1983 (doi:10.1098/rspb.1983.0093); the IUPHAR nomenclature,
Neubig et al. 2003, PMID 14657418 — with a partial agonist between a neutral
antagonist (≈0) and a full agonist, and an inverse agonist below zero. A
partial agonist acts as an antagonist where tone or a full agonist is high
and as an agonist where it is low (Berg & Clarke 2018, PMID 30085126;
aripiprazole, Lieberman 2004, PMID 15015905; buprenorphine precipitating
withdrawal). And database "antagonists" often hide inverse agonism — most
D2 antipsychotics are inverse agonists (Hall & Strange 1997, PMID 9208141) —
so ANTAGONIST and INVERSE AGONIST should get one rule against a partial
agonist. Partial against full agonist is the same sign: not opposed.

*Measured,* on the GtoPdb build (ATC MRR / MeSH MRR; aripiprazole's rank
for haloperidol and risperidone; morphine's for naltrexone):

| partial vs antagonist or inverse agonist | ATC | MeSH | ARI→HAL | ARI→RIS | MOR→NTX |
|---|---:|---:|---:|---:|---:|
| not opposed (D15 as it was) | 0.5114 | 0.6005 | #6 | #4 | #6 |
| fully opposed | 0.5156 | 0.5982 | #90 | #62 | #17 |
| half an opposed protein | **0.5166** | 0.5995 | #10 | #8 | #6 |

Fully opposed is what the ATC judge likes and the MeSH judge does not, and
it throws aripiprazole out of its own class. Half is the best ATC grade,
costs MeSH 0.001, and says in the score what the literature says in words:
sometimes opposite, depending on the system.

### D20 — one protein is one shared target, whatever species recorded it

**Decision (user, 2026-09-27).** A protein ChEMBL records in several species
counts as one shared target, worth n^0.5 of one for n species' records
(`SPECIES_EXPONENT`), and each molecule's target count in the normalisation is
a count of proteins. Which records are one protein is found by sequence
(`scripts/resolve_cohort_orthologues.py`, table `target_orthologues`), since no
identifier says so. The user's words: "if two molecules share two different
targets they should be considered more similar than two molecules that simply
share the same target across two species". The user chose the sequence route
and accepted the new dependency (parasail) for it.

*What was wrong.* The score counted every species' record as a separate full
target. Naloxone and naltrexone's "12 shared targets" were the mu, kappa and
delta opioid receptors in up to four species (human, rat, mouse, guinea pig)
and CYP2D6. Rarity is read per record and fewer molecules are measured on a rat
receptor than a human one, so the non-human records also weighed *more*: the
human records carried 18% of that pair's score.

*Which records are one protein.* No identifier source is clean. ChEMBL records
no orthology (its `EQUIVALENT TO` relations join a species record to a broader
taxon). NCBI's orthologue list reaches a UniProt accession only through a
GeneID, which the guinea-pig mu receptor lacks. OrthoDB puts mu and kappa in one
group, and OMA has no rat or guinea-pig entry for them. A gene symbol is never a
matching key (invariant 6). So each non-human, mammalian (ChEMBL
`organism_class`), single-component SINGLE PROTEIN record is aligned to
UniProt's reviewed human proteome (release 2026_03, 20,431 proteins, pinned by
sha256). It is matched to a human protein only when all of these hold:

- the identity (over the record's own length) reaches 70%, or 90% for a
  fragment;
- it leads the runner-up by 10 points, or the runner-up has three times the
  differences;
- in the record's species, no other protein whose own best human match is the
  same protein comes close. A protein near-identical to the record (≥90%) is
  the record filed twice;
- the match is one to one within a species.

The script's docstring carries the case behind each rule: the 98-residue
guinea-pig mu fragment, rat Scn3a, the rodent Cyp2d cluster, rat's three
noradrenaline-transporter entries.

| of 578 records | |
|---|---:|
| matched | 524 |
| no clear lead over the runner-up (DHFR/DHFR2, tubulins, HCAR2/3, CALCA/B, …) | 23 |
| below 70% identity | 19 |
| fragment below 90% | 6 |
| a rival in the same species (Ccr5/Ccr2, …) | 3 |
| not reciprocal | 2 |
| no sequence in ChEMBL | 1 |

Checked against the gene symbols, which are read here and never matched on: 509
matches carry the record's own symbol case-folded. The other 15 were read one by
one and are right: old names (GPM2 for CHRM2, Sis for SI, Ren1 for REN),
records with no symbol, and rat Agtr1a and Agtr1b both reaching AGTR1, which
they both are. A refusal never merges anything, so it leaves that record
counted as its own protein, as before.

*The rule, measured* (ATC top-1 / MRR, MeSH top-1 / MRR; the gene symbol stood
in as the key for the prototype rows, never in the shipped page):

| | ATC top-1 | ATC MRR | MeSH top-1 | MeSH MRR |
|---|---:|---:|---:|---:|
| every record a full target (before) | 38.7% | 0.5159 | 46.8% | 0.6068 |
| each protein strictly once | 34.2% | 0.4887 | 42.9% | 0.5822 |
| once, rarity counted per protein too | 34.5% | 0.4875 | 43.7% | 0.5840 |
| once × n^0.5, target count in proteins (prototype) | 38.4% | 0.5109 | 47.4% | 0.6068 |
| once × n^0.75, target count in proteins (prototype) | 39.1% | 0.5139 | 47.6% | 0.6097 |
| **shipped: once × n^0.5, sequence-matched** | **38.7%** | **0.5119** | **47.4%** | **0.6060** |

And the exponent swept on the shipped implementation
(`node analysis/similarity_harness/sweep.mjs species_exponent`), where the
target count is already in proteins:

| `SPECIES_EXPONENT` | ATC top-1 | ATC MRR | MeSH top-1 | MeSH MRR |
|---|---:|---:|---:|---:|
| 0 (strictly once) | 37.7% | 0.5075 | 45.2% | 0.5932 |
| 0.25 | 38.0% | 0.5069 | 46.4% | 0.6009 |
| **0.5** | **38.7%** | **0.5119** | **47.4%** | **0.6060** |
| 0.75 | 39.4% | 0.5152 | 47.8% | 0.6095 |
| 1 | 39.1% | 0.5141 | 47.6% | 0.6096 |

With the target count in proteins, counting strictly once costs 1 point under
ATC and 2.2 under MeSH, much less than the prototype's 4.5, which still counted
each molecule's targets per record. 1 breaks the ordering the rule exists for
(two species would equal two proteins). 0.75 grades a little higher on top-1
and MRR and lower on top-5 under both judges. That is within what the caveat
calls fitting the proxy, so the round value was kept.

Strictly once is worse because a drug class's defining target is the one
assayed across species, and a side-target is mostly assayed in human alone.
Counted strictly once in the prototype, citalopram's nearest neighbour became benztropine
rather than fluoxetine, and donepezil's became neostigmine. The repeat
across species is a crude signal of a well-replicated central overlap, so it is
kept as a diminishing one: a second species adds 0.41 of a target and a second
protein adds 1. That keeps the ordering the user asked for at no cost to either
judge. Naloxone/naltrexone now read 4 shared targets and are still each other's
nearest neighbour.

Direction and family subsumption follow the same key (`proteinOf`). A curated
agonist at the rat record and an antagonist at the human one are opposed at one
protein. Previously they were compared at no protein. A human family is
subsumed by the pair's shared proteins even where some are rat records.

*What it deliberately does not do.* The record that counts is the group's
strongest by contribution, which is often a rodent record because per-record
rarity reads it as rarer. Letting the human record stand for the group cost
1.4 points under both judges, and rarity counted per protein cost 2.8 (ATC)
and 1.5 (MeSH), so neither was adopted. The panel names which species' record
counted, and that it counts once. Complexes and families are never matched
across species (each is a record, not one sequence), and nothing outside
mammals is matched.

*Drawn as well as counted* (2026-10-10, at the user's request). The canvas
drew one node per record until then, so a protein the score counted once was
two to four diamonds with one symbol. It is now one node per `proteinKey`, and
the target and edge panels are the protein's, with a section per species'
record ([VIEWER.md](VIEWER.md), *One protein, one node*). Still a grouping and
never a move: each record keeps its own claims, rarity and links, and the
score is untouched.

### D21 — an in-scope indication qualifies from Phase 1

**Decision (user, 2026-10-12).** "Lets expand the molecule set by letting in
all molecules with a brain indication that have reached phase 1 or above."
The indication route's floor drops from Phase 3 (D01) to Phase 1:
`admission_routes.indication.min_phase` is 1, selection policy 3.0.0. Nothing
else moves. The scope is D02's and D16's, read off the same pinned MeSH
classification; the phase is still the qualifying *indication's*, never the
molecule's highest across unrelated diseases; Early Phase 1 (0.5), Unknown (−1)
and a missing phase still cannot qualify, and still never disqualify an ATC N
match. Worked in the `phase1-admission` worktree.

**What "brain indication" was read as.** The adopted scope, unchanged, so one
floor applies to every in-scope descriptor. Two edges of that scope, accepted
at Phase 3 in D02, carry further at Phase 1, and are measured here rather than
narrowed without asking:

- **69 new members qualify only through the Pain tree** — Pain itself, myalgia,
  arthralgia, low back pain, stable angina, abdominal pain. D02 accepted that
  breadth with visible admission reasons.
- **72 qualify only through a tumour heading**: Brain Neoplasms alone (54),
  Diffuse Intrinsic Pontine Glioma alone (13), the two together (3) and
  Pituitary Neoplasms (2). Counting neurofibromatosis 1 and 2, the
  tumour-predisposition syndromes, makes 80. These are mostly cancer drugs
  trialled in glioma (ipilimumab, pazopanib, cabazitaxel), plus imaging
  agents. The headings are in scope because D02's core rule removes a
  descriptor only when *every* C10 placement is in an excluded class, and
  Brain Neoplasms also sits at C10.228.140.211 under Brain Diseases, outside
  the excluded C10.551 Nervous System Neoplasms. DIPG, Pituitary Neoplasms,
  Brain Stem Neoplasms and Pinealoma inherit the same placement. At Phase 3
  this admitted 12 members by tumour alone (lomustine, procarbazine,
  nivolumab, pembrolizumab among them).
  *Counted* by the qualifying headings with any C04 placement, each judged
  by name: Myasthenia Gravis carries C04 only as a paraneoplastic syndrome,
  and Sturge-Weber Syndrome and Tuberous Sclerosis are neurocutaneous
  syndromes, so none of those three counts as a tumour heading.

Seven more qualify only through Erectile Dysfunction, which MeSH also files
under F03.

**What it did.** The cohort goes from 1,330 to 2,449 members and the catalogue
from 1,335 to 2,452: 1,119 new members, all by the indication route, none
lost. Pentoxifylline and rolipram, seeds outside the cohort until now, are
members; loperamide (Pain at Early Phase 1), mibefradil and theobromine
remain seeds only. Of the new members 110 stopped at Phase 1, 557 at Phase 2
and 132 at Phase 3 across every disease, and 318 are approved — for something
outside the scope and trialled at Phase 1 or 2 within it (an antidiabetic in
Alzheimer's, an anticancer drug in glioma). They are 838 small molecules, 87
of unknown type, 71 proteins, 67 antibodies and 56 others (D03 filters none).
The most common qualifying headings among them are Alzheimer Disease (131),
Parkinson Disease (87), Brain Neoplasms (84), Schizophrenia (70) and Major
Depressive Disorder (68).

The ATC grade fell with D21 (38.7% to 32.7% top-1), and so did the MeSH
grade. Neither is the ranking getting worse: the newcomers mostly carry no
label either judge can credit, so one ranked above a class-mate counts as a
miss however apt. Skipped in each list, the ranking among the old catalogue
grades as it did before ([SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §11).

### D22 — MeSH actions read from MeSH, not through PubChem

**Decision (user, 2026-10-13).** "adopt B2 and complete the open items". The
MeSH pharmacological actions are read from each molecule's own MeSH record,
reached by identifier and never through PubChem. The steps, each tried only
where the one before placed nothing:

1. FDA UNII;
2. the CAS number FDA lists for it;
3. a stereoisomer mixture, for a structure ChEMBL draws flat;
4. the MeSH ID on the Wikidata item carrying the ChEMBL ID.

**Why.** PubChem blocked the D21 backfill after about 400 requests, twice. Its
compound-to-MeSH links are made by name, which is how tafamidis carried
triamcinolone's actions. The new route uses identifiers at every step and runs
offline from pinned files and one cached Wikidata pass.

**What it did.** On the 1,335-entry build, 848 molecules carry actions against
PubChem's 787, 760 identical. On D21's catalogue, 1,194 of 2,452 do. Tarenflurbil
lost flurbiprofen's COX actions, the 11 links PubChem's name-matching made in
error are gone, and 20 molecules PubChem reached are left without actions. The MeSH
answer key moved with it, so MeSH grades before and after are not comparable.
The measurements and the refused alternative (matching a skeleton while
ignoring stereochemistry, which put esmethadone on methadone's record) are in
[MESH-ACTIONS-ROUTE-B.md](MESH-ACTIONS-ROUTE-B.md) and DATA-QUALITY-LOG,
2026-10-13.

### D23 — a molecule the sci-wiki lists is entered, and cites it

**Decision (user, 2026-10-14).** "lets implement the compounds in these lists
that are in CHEMBL with or without target data … lets cite the wiki as a
source of entry", of two of the section lists in
[analysis/wiki_comparison/sections/](../analysis/wiki_comparison/sections/):
*Cognition & nootropic* and *Psychiatric & neuro-clinical*, from the sci-wiki
(scientificsean.wiki, read 2026-10-11). Selection policy 3.1.0. Worked in the
`wiki-comparison` worktree.

**What it is.** A third reason for being in the catalogue, beside the clinical
routes (D01, D21) and the seeds (D05), and shaped like the seeds:
`listings.sciwiki` in `config/cohort1_selection.json` names ChEMBL ids, the
build normalises each to its parent and keeps it whatever the clinical routes
say, and `in_cohort` stays the clinical routes alone. Such an entry reads
`admission_reason = 'listed_only'`, carries the exclusion reason a seed would,
and has a row in the new `molecule_listings` table: the wiki's name for the
compound, the slug its page is linked by, the section, and how the name was
placed. A listing is no evidence of anything and never enters the score.

**"With or without target data"** is taken literally: an entry ChEMBL holds no
eligible evidence for is entered like any other and says so, as 263 clinical
members already did.

**Only entries outside D21's catalogue are named.** Of the two sections' 764
rows, 317 already place at a catalogue entry; the clinical route is their
reason for being here, so they need no listing, and not naming them keeps
what is copied from the wiki to what the entries need. Another 93 were
outside the 1,335-entry build the sections were counted against and are D21
members (`with_d21`); 66 are identified but not in ChEMBL, and 56 not
identified at all. That leaves 232 in ChEMBL and outside the catalogue.

**Identity is an identifier, written down after review** (invariant 15). The
names were placed by `analysis/wiki_comparison/placing.py`, by name, which the
database refuses. So each of the 232 candidate rows was checked against what
ChEMBL draws at the id, and what is written into the policy is the id; the
build never reads a name. The 157 placed by an exact ChEMBL preferred name or
an FDA UNII InChIKey were read over and kept. The 75 placed through a synonym, PubChem or a
skeleton-only match were each compared with ChEMBL's structure by hand:

- **kept**, 63 of them, among them three skeleton matches whose ChEMBL record
  is drawn with no stereochemistry and is its only record of the compound
  (MAP4343, nooglutyl, androstadienone), each with a `review` note;
- **corrected**, one: *Deoxycorticosterone* had landed on
  DESOXYCORTICOSTERONE ACETATE through the acetate's synonym list; the free
  steroid is its own parent, CHEMBL1498;
- **refused**, 11, each in `considered_and_not_listed` with its reason:
  *BPAP*, which PubChem's name took to bisphenol AP; five names reaching two or
  three parents (Dichloropane, Methylnaphthidate, Hydroxydione, U-47700,
  4-Methylpregabalin), where choosing one would be a guess at a stereoisomer;
  and five skeleton matches to a record drawn as a different stereoisomer
  (LY451646 and MRZ-9547, whose racemates are listed under LY404187 and
  Phenylpiracetam; α-conotoxin PIA; allotetrahydrocorticosterone; Org 20599).

**What the wiki allows, and so what is kept.** Its terms (/about/legal, §13 and
§18) allow "reading, linking to a page, and quoting a short passage with
attribution", and refuse "republishing entries, copying the reference in
bulk" and building "a competing dataset"; they also forbid suggesting an
endorsement. So an entry keeps what a citation needs: the compound's name, a
chemical name, and the slug. The URL is built from the slug on the page, the
wiki's own classes are not copied into the policy, the database or the page,
and the credit says SubNetwork is not affiliated with it.

**On the page.** A listed entry's identity table has an *Entered from* row:
"the sci-wiki, as Noopept", the name linking to that compound's page, with a
hover saying a listing is not evidence and not an affiliation. A listed
molecule the clinical routes also admit would read *Also listed by*; none does
yet. About credits the sci-wiki, with the count, only when the payload holds an
entry from it. Where ChEMBL gives the parent no preferred name (83 of the 221),
the wiki's name is the label, so a reader sees *Noopept* and not
CHEMBL4303687; it is attached through the reviewed id and is never a match. The
wiki's name is searchable on every listed entry.

**What it did.** The catalogue goes from 2,452 to 2,673 entries: 221 listed
molecules, 144 from the cognition section and 77 from the psychiatric one, and
none lost; the cohort stays 2,449. Of the 221, 68 have a Supported claim, 61
only Preliminary ones, 13 only the broader layer, 3 only retained observations,
and 76 no eligible evidence in ChEMBL 37. The ATC grade goes from 32.7% to
31.7% top-1 and MRR 0.4607 to 0.4467; with the 221 skipped in each list it is
32.4% and 0.4589, so most of the fall is a judge that cannot label them
([SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §13).

**Left open.** The 410 rows of the two sections already in the catalogue carry
no listing, so their pages do not cite the wiki. And
`analysis/wiki_comparison/` published the wiki's whole compound list with its
sections and classes (`wiki_compounds.csv`, `comparison.csv`, `sections/`),
committed before its terms were read. [COMPOUND-LIST-TERMS.md](COMPOUND-LIST-TERMS.md)
weighed it and recommended removing the list and its classes before `main`;
**the user agreed on 2026-10-15**, and asked that the copy be kept on disk as
the widest list to measure the catalogue against. The list, the sections and
the full comparison files now live in `db/cache/sciwiki/`, which is
gitignored, and the scripts read them there; the repository keeps the
comparison files without the wiki's `section` and `wiki_class` columns. The
commits that carried them stay reachable by hash on the published branch.

### D24 — the sci-wiki's psychedelics section is listed too

**Decision (user, 2026-10-15).** "also implement the scientific sean compounds
in psychedelics-entactogens that are in CHEMBL": D23's rule, applied to a third
section, *Psychedelics & entactogens*. Selection policy 3.2.0. Worked in the
`wiki-comparison` worktree.

**What it is.** Nothing new in kind: 75 more entries in `listings.sciwiki`,
each a ChEMBL id written down after review, `admission_reason = 'listed_only'`,
a `molecule_listings` row and the *Entered from* row on the page. The policy's
rule names the third section.

**Which.** Of the section's 175 rows, 106 place at a ChEMBL parent; 25 of those
are already catalogue members by a clinical route and need no listing (MDMA,
LSD, psilocybin, 5-MeO-DMT, esketamine and the anticholinergic deliriants
among them); 49 are identified but not in
ChEMBL, and 20 not identified at all. That leaves 81 candidates, and the same
review as D23's:

- the 47 placed by an exact ChEMBL preferred name or an FDA UNII InChIKey were
  read over and kept;
- the 34 placed through a synonym, PubChem or a skeleton match were each
  compared with ChEMBL's structure: 26 **kept** (MDA through the four-letter
  synonym, ChEMBL's TENAMFETAMINE; *Atropa belladonna* at ChEMBL's
  structureless BELLADONNA record, with a `review` note);
- 2 **corrected**: *MDEA*, which PubChem's name took to N-methyldiethanolamine,
  an abbreviation clash, is CHEMBL126279; *Limonene*, which ChEMBL's synonym
  put on D-limonene, is CHEMBL15799, ChEMBL's record drawn with no
  stereochemistry, since the name gives none;
- 6 **refused**, in `considered_and_not_listed`: 5-MAPB and MDPV, racemates
  ChEMBL holds only as single enantiomers; Ginkgolide B (eight parents), LSZ
  (three) and Ariadne (two), skeleton matches where choosing one stereoisomer
  would be a guess; and *Grayanotoxin*, a family of diterpenes that PubChem's
  name took to one flat record.

**What it did.** The catalogue goes from 2,673 to 2,748 entries, 296 of them
listed; the cohort stays 2,449. Of the 75, 9 have a Supported claim, 23 only
Preliminary ones, 9 only the broader layer, 1 only retained observations, and
33 no eligible evidence in ChEMBL 37 — the section is mostly research
chemicals ChEMBL holds a structure for and little else. 49 of the 75 have no
ChEMBL preferred name, so the wiki's name is their label. The ATC grade goes
from 31.7% to 32.0% top-1 and MRR 0.4467 to 0.4477; with all 296 skipped in
each list it is 32.7% and 0.4601, the D21 build's own grade, so what the
listing costs the ranking is again the judge's
([SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §13).

How the 296 sit against Wikipedia, Wikidata, TripSit and PsychonautWiki is in
[NOOTROPIC-WIKI-COMPARISON.md](NOOTROPIC-WIKI-COMPARISON.md), *The listed
entries against other public lists*: 62 of these 75 are on at least one of
them, against 43 of the cognition section's 144 and 15 of the psychiatric
section's 77.

### D25 — what Wikipedia, Wikidata, TripSit and PsychonautWiki list is entered, and cites them

**Decision (user, 2026-10-16),** two comments on the table *The lists against
the catalogue now* in [NOOTROPIC-WIKI-COMPARISON.md](NOOTROPIC-WIKI-COMPARISON.md):
of its "in ChEMBL, outside" column, "lets bring in all these compounds, and
state where they came in from. make sure to cite them correctly according to
their terms"; and of its "entered from the wiki" column, "for these compounds,
state the non-scientific sean wiki as the sources instead of how its currently
cited". Selection policy 3.3.0. Worked in the `wiki-comparison` worktree.

**What it is.** D23's rule, applied to four open lists as four more
`listings` blocks: `wikipedia` (the *Nootropics*, psychoactive and *Designer
drugs* categories), `wikidata` (nootropic and psychoactive roles), `tripsit`
(its factsheets) and `psychonautwiki` (its substance index). Each entry is a
ChEMBL id with the list's name for the compound and the key its page is linked
by; `admission_reason = 'listed_only'`, never in the cohort, never evidence.
A parent no clinical route or seed holds is listed under every one of the four
that carries it. **A compound one of them carries is no longer cited from the
sci-wiki:** of the 296 entries D23 and D24 listed, the 120 also on an open list
now cite that list instead, and the sci-wiki block keeps the 176 none of them
names. Read as "the non-sci-wiki list" in the second comment; the comment's
column is exactly those 120.

**Identity.** The four lists were placed by
`analysis/wiki_comparison/compare_lists.py`: Wikipedia's articles and Wikidata's
items by the InChIKey on the item where there is one (715 of their 733
entries), the rest and TripSit's and PsychonautWiki's names by exact ChEMBL
name, FDA UNII InChIKey or weaker tiers. `open_listings.py` writes the policy
blocks and stops on any placement its `REVIEW` table does not decide; the 72
not made by an identifier, and two identifier placements a read-over caught,
were compared with ChEMBL's structure: 19 kept, 5 corrected, 50 refused
([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md), 2026-10-16). Among the refusals,
ChEMBL synonyms that name another compound (*2C-B-AN* on isoaminile, *G-4* on
dichlorophen), deupsilocin folded onto psilocin, and racemates ChEMBL holds
only as single enantiomers, as D24 refused 5-MAPB.

**Citing them by their terms**, reread at the source for TripSit and
PsychonautWiki ([COMPOUND-LIST-TERMS.md](COMPOUND-LIST-TERMS.md), *Used as
reasons for entry since D25*). Only a name and a page key are kept from any of
them. The panel's *Entered from* row names each list and links the compound's
page there — Wikipedia's article, Wikidata's item, TripSit's factsheet,
PsychonautWiki's page — open lists first. That row is the note "citing TripSit
as the source … on every page which uses/displays the information" TripSit's
terms ask for, beside the link back; its non-commercial condition holds while
SubNetwork is free. About credits each list with its count and its licence:
Wikipedia's article text CC BY-SA 4.0, Wikidata CC0, PsychonautWiki's semantic
data CC BY 4.0, TripSit's terms linked; and it says SubNetwork is affiliated
with none of them. Where ChEMBL gives a parent no preferred name (552 of the
841 listed), the label is a substance index's name, then a Wikipedia title
without its disambiguator, then the sci-wiki's, then Wikidata's label, which
can be a salt's.

**What it did.** The catalogue goes from 2,748 to 3,293 entries, 841 of them
listed (665 by an open list, 176 by the sci-wiki alone); the cohort stays
2,449, and no entry is lost. Of the 545 new entries, 64 have a Supported
claim, 220 only Preliminary ones, 53 only the broader layer, 12 only retained
observations, and 196 no eligible evidence in ChEMBL 37; 420 have no ChEMBL
preferred name, so a list's name is their label. The ATC grade goes from 32.0%
to 30.3% top-1 and MRR 0.4477 to 0.4343, under both floors in
`tests/similarity_harness.test.mjs`; with all 841 listed entries skipped in
each list it is 33.5% and 0.4646, above the D24 build's 32.7% and 0.4601 the
same way. So the floors now grade with listed entries skipped
(`skippingListed`, `evaluate.mjs --skip-listed`), and were not lowered
([SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §13).

**Left open.** The catalogue now holds Wikipedia's psychoactive and
designer-drug categories wholesale where ChEMBL has a structure, which includes
designer steroids and SARMs (bolandiol, LGD-4033) filed there as designer
drugs, and a few drugs PsychonautWiki indexes for their effects (efavirenz,
serotonin, tyrosine). They were entered as asked, and each says why. The
sections of NOOTROPIC-WIKI-COMPARISON.md that count the catalogue against the
lists were measured before D25, and its last section says what changed. The
myristicin record ChEMBL names ELEMICIN is unreported.

---

## Open

In the order they bear on the picture.

1. **The eight remaining `OPPOSED_ACTIONS` entries** were never examined the way
   the partial-agonist ones now have been.
2. **356 non-primary GtoPdb rows, at 346 pairs, have no claim**
   (`has_claim = 0`): directions nobody draws. By D18 they stay that way.
3. **Controls done 2026-09-27:** the mechanism filter and line colour read
   GtoPdb's action on a measured claim's pair, a curated claim keeps its own.
   Lines with an action colour went from 1,084 to 1,944 of 12,841, 56 of them
   mixed where the curators' words differ.
4. **Primary-only for evidence, all rows for direction** (the user's call on
   2026-09-27). Worth revisiting if a second error like vilazodone's appears.
5. **New molecules** — the second step. D21 added 1,119 by lowering the
   indication route's phase floor, D23 221 by the sci-wiki's two
   sections and D24 75 by its psychedelics section, and D25 545 more from
Wikipedia, Wikidata, TripSit and PsychonautWiki; the sci-wiki's other eight sections
   (peptides, botanicals, formats and the rest) are not listed, and the 17
   refused names would need a ChEMBL record drawn as the compound they mean. GtoPdb's ligands outside the cohort are
   still unadmitted, by a rule still to be written; see
   [COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md) for the curated-route
   proposal it should start from.
6. **Report the alfuzosin mechanism to ChEMBL.** Drafted 2026-10-10 in
   [CHEMBL-ERROR-REPORT-ALFUZOSIN.md](CHEMBL-ERROR-REPORT-ALFUZOSIN.md) and not
   sent. The action is withheld locally in the meantime
   (`CHEMBL_MECHANISM_ACTION_EXCLUSIONS`, DATA-QUALITY-LOG 2026-10-10); the
   entry stops the build when ChEMBL corrects the row, which is when to remove
   it.
7. **D20's per-record rarity.** A rodent record often stands for its protein
   because fewer molecules are measured on it, not because the protein is rarer.
   Both obvious fixes grade worse (see D20); a rarity read from the human
   record's count, or from the protein's, weighted by how many species assay it,
   has not been tried.
8. **Complexes and families across species** (a rat GABA-A assembly against
   the human one) are still separate targets under D20, and so still separate
   nodes on the canvas, where single proteins are now one.
9. **D21's scope edges.** At Phase 1 the Pain tree admits 69 members by pain
   alone (angina and myalgia among them), and the tumour headings 72 (80 with
   neurofibromatosis), mostly cancer drugs trialled in glioma. Both edges
   were accepted at Phase 3 in D02. Whether "brain indication" should exclude
   them at the lower floor is the user's call.
