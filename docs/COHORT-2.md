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
  `db/cache/gtopdb/2026.3/`, sha256 in the manifest.
- Matched by identifier only. The ligand by exact InChIKey, else by a ChEMBL id
  naming exactly one parent; two routes disagreeing drops the ligand. The target
  by UniProt accession, to one SINGLE PROTEIN record, or — for a multi-subunit
  GtoPdb target — only to a PROTEIN COMPLEX with exactly the same accessions,
  never fanned out onto the subunits (fan-out manufactures shared targets).
- `ACTION_MAP`, every (Type, Action) pair in 2026.3 mapped by hand to ChEMBL's
  `action_type` vocabulary so the viewer's `OPPOSED_ACTIONS` reads both
  sources; "Neutral", "Binding", "Mixed" and the like map to no direction. A
  pair a future release adds is stored undirected and listed in the manifest.
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
5. **New molecules** — the second step. GtoPdb's ligands outside the cohort,
   admitted by a rule still to be written; see
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
