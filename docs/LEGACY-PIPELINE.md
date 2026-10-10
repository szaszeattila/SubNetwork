# The legacy seed pipeline

Moved out of `CLAUDE.md` verbatim on 2026-09-27, when that file had grown to
3,375 lines (option A of [CLAUDE-MD-SPLIT-PROPOSAL.md](CLAUDE-MD-SPLIT-PROPOSAL.md)).
Nothing in the cohort pipeline reads any of this, and the code it describes
is the rollback path and is **not to be modified**. The rules it produced have
already been promoted into `CLAUDE.md`'s **Invariants**, which stay there.

Kept because the second and third seed cohorts' selection reasoning is the
best material here on how to expand a graph without manufacturing
similarity, and the cohort pipeline faces that question again in cohort 2.

## Running it

The legacy six-source pipeline is still here and still runs:

```bash
pip install -r requirements.txt
python3 scripts/build_db.py           # incremental: reloads each seed molecule
python3 scripts/build_db.py --rebuild # discard the DB and start clean
python3 scripts/build_db.py --complexes-only  # re-derive assembly membership
python3 scripts/export_graph.py       # regenerate the legacy export
```

It writes `db/subnetwork.db`, and its output is displayed by
`viz/legacy/index.html` rather than by the current page. The export goes to
`viz/legacy/graph.data.js`, beside the page that reads it, and the page takes
the shared `viz/vendor/` library by `../`. Both used to point at `viz/` itself,
so a legacy export overwrote the cohort payload and the moved page loaded
neither file; the page is byte-for-byte the viewer `master` served before the
cohort merge apart from that one path, and tag `legacy-seed-graph` marks that
commit.

The legacy pipeline's ChEMBL access, below, applies only to it. ChEMBL is read from a local bulk release when one is present (~10 min for a
full rebuild of all 28 molecules) and from the REST API otherwise (~45 min for
the original seven, and twice aborted on EBI outages). `--chembl-source {auto,local,api}` overrides; `--chembl-db PATH` or
`CHEMBL_SQLITE_PATH` points at a specific file. See `scripts/chembl_local.py`
for how to fetch a release. Only ChEMBL is affected — the other five sources
are still queried live, so a rebuild still needs a connection.

`--rebuild` is required after a schema change (`check_schema` will tell you),
and is the honest way to re-baseline the counts quoted below. The one
legitimate alternative is a new column or table whose value is *derivable from
a snapshot already on disk*: `assay_description` was added by `ALTER TABLE`
plus a backfill joined to the `chembl_37` release on assay id, and
`target_complexes` the same way through `--complexes-only`, precisely so the
counts below would not be re-rolled against five live sources for a change
that adds no rows. Anything that could change which rows exist still needs
`--rebuild`. Reruns without it
are still idempotent: each molecule's edges are dropped and rebuilt from what
the sources report *now*, so a correction that removes a measurement actually
removes it.

First run caches `db/pdsp_ki_database.csv` (~20MB, gitignored, re-fetched after
30 days; `--refresh-pdsp` forces it). `db/subnetwork.db`, `db/cohort1.db`,
`viz/graph.data.js` and `viz/evidence/` are gitignored — all are generated.

## The legacy database (`db/schema.sql`)

`interactions` holds one row per (molecule, target, action_type) edge, with the
pooled binding value, the separately-pooled functional value, and
`is_primary_mechanism` for curated top-line MOAs. `interaction_sources` records
which source backed the edge and in which `role` (`binding` / `functional` /
`annotation`) — a database-level pointer, not evidence. It carries a citation
only when that citation is *not* one of the edge's measurements, and then says
which kind it is in `citation_kind`: `mechanism` (ChEMBL's drug-level MOA
reference, 64 links) or `annotation` (the reference a source cites for
asserting the edge exists without measuring it, 154 DGIdb links). The other 795
links carry none. `sources.source_release` names the snapshot a build read
(`chembl_37`), or is NULL when the source was queried live. `molecules`,
`targets` and `target_complexes` each carry a `wikipedia_url`, resolved through
Wikidata at the end of a build and NULL where no English article is linked (13
of 207 targets: 10 with no article, 3 ambiguous). The assembly column is the
one that is not derived — see below.

`measurements` holds one row per *individual* measurement pooled into a value,
with its own assay id, its own paper, the source's own data-validity flag on
that specific number, and `assay_description` — what that assay actually
measured, in the source's words (ChEMBL only; NULL for PDSP and BindingDB,
which expose no equivalent). This is a different question from `interaction_sources`,
which answers "which databases back this edge" and keeps only one row per
(source, role). Both are needed: without `measurements`, `n_measurements` was
an assertion the viewer could not show the evidence for — an edge reading
"n=13" listed a single citation, and ~230 of the ~290 citations behind the
database were unreachable.

Anything that is per-measurement belongs on `measurements` and nowhere else.
A one-row-per-source table cannot hold a per-measurement fact without sampling
one arbitrarily, and it did so twice: the citation (84 of 133 links carried a
copy of one of the edge's own measurement papers, chosen by dict last-write-
wins) and the data-validity flag (13 links carried one where the underlying
measurements carried 20). Both are gone from `interaction_sources`;
`link_source` now raises rather than store a citation with no `citation_kind`.

`target_complexes` and `target_complex_members` record which `targets` rows are
subunits of one physical assembly. Derived offline from the `chembl_37` release
by `--complexes-only`, and reachable by identifier at every step: an assay id
this database already stores resolves to a ChEMBL target, whose
`target_dictionary.target_type` distinguishes `PROTEIN COMPLEX` (ChEMBL asserts
the subunit composition) from `PROTEIN COMPLEX GROUP` ("a poorly defined protein
complex, where subunit composition is unclear") and `PROTEIN FAMILY`
(paralogues, deliberately not recorded — merging them would destroy the
DRD2-vs-DRD3 distinction the seed set exists to show). Members are matched on
UniProt accession exactly, never on a gene symbol. What must **not** be used is
ChEMBL's `protein_classification` tree: it is a sequence and function taxonomy
blind to assembly, putting CACNA1C and CACNA1D on one leaf while they are two
different channels and filing CACNB2, which co-assembles with CACNA1C, under
"Auxiliary transport protein". `export_graph.py`'s `resolve_groups` reconciles
overlapping complexes into the disjoint assemblies the viewer draws.

`target_complexes.wikipedia_url` is the one link on this page whose *identity*
is hand-written, and the reason is worth keeping. There is no walk from an
identifier this database already holds to the right Wikidata concept. Following
`P527` / `P361` out from the members' UniProt accessions returns a pile of
Reactome complex items plus a few broad concepts, and the ones with an English
article are confidently wrong — 5-HT3 lands on "Cys-loop receptor", KCNQ1/KCNE1
on "KCNQ channels". Requiring unanimity across *every* member does not fix it:
the 7-member NMDA group resolves 7/7 to "Ionotropic glutamate receptor", too
broad, while the correct "NMDA receptor" is reachable from only 4 of the 7;
GABA-A resolves 4/4 correctly; the other five assemblies resolve to nothing. A
rule that is sometimes wrong with full confidence is worse than one that is
sometimes silent, so `COMPLEX_WIKIDATA_ITEMS` maps each ChEMBL complex id to a
Wikidata item by hand — and *only* that. The article is still resolved from the
item at build time, through the same ambiguity check as molecules and targets,
so a page move is picked up. What is curated is which identifier, not which
title, which is what keeps it inside invariant 15. Six of the seven records
resolve; `CHEMBL2221347` (the IKs channel) maps to `None` deliberately, because
English Wikipedia has no article for that assembly — an explicit "there is not
one", in the spirit of `CHEMBL_ASSAY_LINK_EXCLUSIONS`, rather than a gap.

`action_type` is `ANTAGONIST` / `INHIBITOR` / … when ChEMBL has a curated
mechanism, `BINDER` when there's raw affinity but no curated mechanism, and
`FUNCTIONAL` when there's functional activity but no binding measurement at
all.

## The legacy seed database — history

Everything from here to the end of this section describes the six-source seed
pipeline, which still builds `db/subnetwork.db` and is displayed by
`viz/legacy/index.html`. It is kept because it is why most of the rules above
exist. Its counts are not the current ones.

Built 2026-09-03 against the `chembl_37` bulk release:

**28 molecules · 207 targets · 654 interactions · 1013 source links**
(up from 14/141/244/342, and from 7/51/84/133 before that). 64 edges carry a
curated ChEMBL mechanism; 288 of 654 are corroborated — curated, or backed by
more than one measurement — and the rest are single-measurement leads. Edge
types: 411 BINDER, 171 FUNCTIONAL, 40 INHIBITOR, 21 ANTAGONIST, 6 BLOCKER,
3 INVERSE AGONIST, 1 AGONIST, 1 NEGATIVE ALLOSTERIC MODULATOR. Source links by
database: 718 ChEMBL, 154 DGIdb, 122 PDSP, 19 BindingDB; by role: 569 binding,
290 functional, 154 annotation. 218 of them carry a citation — 64 `mechanism`,
154 `annotation` — and the other 795 carry none, because every citation they
used to hold was a sampled copy of one of the edge's own measurements. 86
targets are marked brain-expressed.

Behind those 654 edges sit **2,858 individual measurements** (2,842 counted, 16
BindingDB rows recorded but excluded as republication), citing **740 distinct
papers** and carrying 49 of ChEMBL's own data-validity flags. All 28 molecules
and 194 of 207 targets link out to Wikipedia (10 have no English article linked
from their Wikidata item; CALM1, DRD3 and PDE9A resolve to several articles
each and are skipped rather than guessed at), as do 6 of the 7 protein
assemblies — the seventh, the IKs channel, has no article of its own and is
recorded as having none. Invariant 7 holds exactly:
`COUNT(*) FROM measurements WHERE counted = 1` equals `n_measurements` for
every edge, in both roles.

Build takes 9m59s for all 28 molecules: ChEMBL comes off the local bulk
release, and the remaining time is BindingDB, DGIdb, PubChem, UniProt, PDSP
and Wikidata, which are still queried live. That live dependency remains the
standing weakness — what the database contains depends partly on which
sources happen to be up at build time. See
[docs/DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md).

Seeded in three cohorts, each chosen against the targets the previous ones
produced, so the graph has real structure rather than twenty-eight
disconnected stars.

The **first seven** established the core: the three methylxanthines (caffeine,
theophylline, theobromine) across the ADORA family; istradefylline (selective
ADORA2A antagonist, ~1000× more selective than the methylxanthines) as a
counterpoint; rolipram (PDE4) and cilostazol (PDE3) against theophylline's
curated PDE targets; donepezil (ACHE), which corroborates caffeine's own ACHE
lead.

The **second seven** were picked to densify that core rather than extend it,
selected by sweeping `chembl_37` for every molecule with a curated mechanism
or a qualifying binding measurement against the 51 targets the first cohort
produced: pentoxifylline (curated mechanism at 13 of the 51 — a fourth
methylxanthine that welds the xanthine and PDE clusters through one node),
sildenafil (binding at 10, and the only route found from the PDE cluster back
to ADORA1/ADORA2A), verapamil (CACNA1C, KCNH2 and ABCB1 — three families that
each hung off a single edge), rivastigmine (curated dual ACHE/BCHE, the
contrast to ACHE-selective donepezil, plus FAAH), tacrine (the most heavily
measured candidate found, 340 qualifying rows across ACHE, BCHE, APP and
KCNH2), selegiline (MAOB, playing the selective-single-target role
istradefylline plays at ADORA2A), and cannabidiol (CNR1, HRH3 and ADRA2C —
three brain-expressed targets that were each at one edge). All 51 original
targets survived the rebuild; ACHE went 2 edges → 6, KCNH2 and ADRA2C 1 → 4,
BCHE and CYP1A2 1 → 3, MAOB 2 → 3.

That cohort left 93 of 141 targets sitting at a single edge, mostly its own
off-targets. The **third fourteen** were chosen to pay that down: corroborate
targets already in the graph, and drag in as few new ones as possible. Two
things about the previous sweep had to change first, and both only became
visible by running it again (see the log for the full account).

*Rank on distinct single-protein ChEMBL targets, not on accessions.* Counting
accessions put gabapentin, pregabalin and suloctidil at the top with 26 hits
each — one curated mechanism against the voltage-gated calcium channel
*complex*, fanned out over 26 subunits that are in this database only because
tacrine's own fan-out put them there. Seeding gabapentin would have added 26
edges carrying one assertion and scored as the best pick available.

*Score each candidate by what it adds to the ones already chosen.* Five
antipsychotics covering DRD1/2/3 look like five wins and are close to one, and
the second one's off-targets are mostly the first one's — so selection ran as
a greedy set-cover, orphans newly covered minus 0.35 per new node newly
dragged in. Run unrestricted it returns research compounds nobody would
recognise, so the pool was restricted to approved drugs and the final set
chosen by hand from what the scoring surfaced.

What that produced: haloperidol (the anchor of the aminergic block — 343
qualifying rows, curated D2/5-HT2A, 11 single-edge targets in one molecule),
clozapine (the atypical against haloperidol's typical: same two curated
targets, opposite balance across them), amitriptyline (curated SERT/NET, and
the only bridge found between the aminergic and sodium-channel blocks),
loperamide (curated mu-opioid agonist, the only route to OPRD1/OPRK1/OPRM1),
dextromethorphan (curated GRIN2A antagonist and sigma-1 agonist, reaching six
single-edge targets while adding no new ones at all), memantine (the second
NMDA opinion, and the fifth approved Alzheimer's drug here), lamotrigine (the
sodium channels), dipyridamole (curated SLC29A1 — it raises adenosine by
blocking reuptake where every xanthine here blocks the receptor — plus the
PDE6/7/8/10/11 isoforms sildenafil left at one edge each), vardenafil (the
direct PDE5A comparison to sildenafil), dronabinol (curated CB1 *agonist*
against cannabidiol's curated negative allosteric modulator at that same
receptor), phenelzine (curated MAO-A *and* MAO-B, against MAO-B-selective
selegiline), quinidine (the CYP2D6/SCN5A/KCNH2 cardiac trio), galantamine (90
ACHE and 55 BCHE rows and nothing else at all — pure corroboration, completing
the four approved cholinesterase inhibitors), and mibefradil (the only
molecule found that measures CACNA1G/1H/1I *individually* rather than as a
27th fan-out).

It worked, on the measure it was chosen for. All 141 previous targets survived
the rebuild, and **50 of the 93 single-edge targets got a second opinion** —
CYP2D6 1 → 11, SCN5A 1 → 9, DRD3 and SCN2A/3A and SLC6A4 1 → 7, DRD2 and HRH2
and SIGMAR1 and SCN1A 1 → 6. The count of single-edge targets fell from 93 to
**81 while the target set grew from 141 to 207**, which is the first time an
expansion here has left the periphery smaller in proportion than it found it.

Dipyridamole was excluded from the second cohort and is in this one. That
reversal is deliberate: its 11 hits were then a subset of pentoxifylline's 13,
and the target set it would join has since grown to include the PDE isoforms
sildenafil brought in as off-targets. An exclusion recorded against a snapshot
of the graph is not a permanent one. `CHEMBL190` — "theophylline anhydrous",
the *parent* of the seeded theophylline record — was excluded by hand for the
opposite reason: the parent-molecule rollup that suppresses salts attributes
every child's data to the parent, including the seeded molecule's own, so it
scored as a strong candidate while being theophylline wearing its parent's
name.

The cost, stated plainly: **81 of the 207 targets still sit at a single edge**,
and 38 of those are newly added — the new molecules' own off-targets, reached
by one edge each. 66 targets are new overall. The proportion improved and the
absolute problem did not go away, and with no filter UI there is still no way
to hide the periphery. That makes the missing filter (below) the most pressing
thing on the list.

The viewer draws molecules as blue circles and targets as orange diamonds; edge
colour encodes `action_type` and edge style encodes confidence (solid =
curated or multi-source-corroborated, dashed = single-measurement lead).
Clicking a node highlights its neighbourhood and opens a details panel. The
panel's edge list — a molecule's targets, a target's molecules — is grouped
into three evidence tiers (curated mechanism, corroborated, single-source
leads) and ranked within each by distinct papers, then measurements, then
databases. Papers lead because n counts assays and several assays routinely
share one paper. What counts as a distinct paper is `paperKeys`, shared with
the edge panel's "from N papers" so the two cannot disagree (invariant 13): a
citation is identified by its URL, falling back to its free text and only then
to the assay id. The fallback matters because PDSP measurements carry no
`citation_url` at all — filtering on it dropped the one source here whose
corroboration is independent out of the primary ranking key, and rendered "0
papers" beside "1 measurement". The ranking never reads `binding_value`:
invariant 7 makes n the trust signal and the affinity value explicitly not
one, and sorting
tacrine's targets by affinity puts a single unreplicated IC50 on APP above the
13-paper ACHE result. `evidenceTier` is built on `isCorroborated` rather than
beside it, so the grouping and the graph's solid-vs-dashed styling cannot
disagree. The leads tier starts collapsed, with its count on the summary —
tacrine is 6 corroborated against 40 leads, and expanded they pushed the
evidenced rows off-screen.

**Grouping happens before the tiers see the list, not inside each one.** Built
the other way round, an assembly whose subunit edges are not all equally
evidenced was cut along the tier boundary: verapamil's four calcium-channel
edges rendered as a "Voltage-gated calcium channel" row under Corroborated that
opened onto CACNA1C alone, plus a second row of the same name under Leads
holding the other three. 4 of the 23 molecule-and-assembly rows in this database
were split that way; 0 are now. `displayUnits` groups once, and `unitTier` puts
a grouped row in the tier of its **best-evidenced** member — the same rule the
canvas already uses to draw a collapsed edge solid when any subunit edge is
corroborated, so the panel and the picture cannot disagree about how well
evidenced one receptor is. The promotion is stated rather than assumed: a row
that spans tiers prints what it holds ("4 subunits of 26 measured here · 1
corroborated edge, 3 leads"), because three leads inside a heading reading
"Corroborated" is the right place for them and exactly the thing that must not
be silent. The "of 26" is the other half — a row naming a whole channel and
showing four proteins should say it is showing four.

A molecule's target list also collapses **assay fan-out**: ChEMBL's
unit of record is the assay, and an assay run against a protein complex or
family is attributed to every member, so one experiment arrives as many edges
that each honestly say "1 measurement" while the page says something false.
133 of the 654 edges fall into 29 such groups, the largest still being
tacrine's `CHEMBL4613617` ("Inhibition of VGCC (unknown origin)", IC50 17 µM,
one paper), which alone accounts for 26 of its 46 targets; the third cohort
added eight more of them, the largest being mibefradil's own 8-subunit calcium
screen and haloperidol's 7-target aminergic panel. They now render as one
row naming the assay and saying so, expandable to the members. `fanoutRef`
returns null the moment an edge has a second assay of its own, which keeps
rolipram's PDE4B edge (18 assays) out of it entirely; grouping is applied only
to the targets-of-a-molecule direction, because an assay id is also shared by
the several compounds screened in one run and grouping on it in a target's
molecule list would merge separate findings about different drugs.

The molecule panel ends with **Shares targets with** — the other molecules
acting on the same targets, which is the closest this database comes to "these
two may work alike". Ranked by shared targets where *both* edges are
corroborated: with 81 targets sitting at a single edge, an uncritical overlap
count mostly finds off-target noise. A fan-out group counts once per side —
donepezil and verapamil each have one Cav1.2 QPatch assay attributed to four
subunits, and counting it four times ranked the pair above
caffeine/theophylline at the adenosine receptors. Caffeine's list still opens
on theophylline (6 shared, 4 corroborated on both sides, 6 brain-expressed)
then istradefylline.

**A row opens the pair, not the other molecule.** Clicking one used to select
the molecule named on it, which answers a different question: it replaced one
molecule's whole neighbourhood with another's, and the overlap — the thing the
row is a count of — still had to be found by eye across two target lists that
run to 46 rows on tacrine. A row now opens both molecules and nothing but what
they share: the shared targets, and at each of them the two edges one above the
other, so the mechanisms and the evidence can be compared without opening
either. The graph lights the same set and nothing else — no second hop, unlike
a molecule's own selection, because the overlap is already the answer and
echoing one step out from it puts back the graph the pair was selected to
isolate. Caffeine and theophylline is 8 nodes and 12 edges of 235 and 654.

The panel lists the row's *own* units rather than walking the edges again, so
the number on the row and the list it opens cannot disagree about which things
they are. That means the two de-duplications are visible where they happen: a
shared assembly is one block naming the receptor and holding every subunit's
edges — dextromethorphan and memantine is one NMDA block of 7 proteins plus
SLC22A1, which is the 8 → 2 correction shown rather than asserted — and a
shared fan-out assay is one block naming the proteins it was filed against.
Each says what it compressed on the block itself. Both molecules can still be
opened on their own, from a row at the bottom of the pair.

It still dims rather than removes. Only the brain filter takes anything out of
the picture; a second thing that removed would be a second answer to "what is
on screen", which is the disagreement the one-rule-read-four-ways arrangement
exists to prevent.

The third cohort is what this section was built for, and it reads correctly
without being told to. Haloperidol and clozapine are each other's top row by a
wide margin — 41 shared targets over 44 proteins, 28 corroborated on both
sides, 17 brain-expressed — which is the typical/atypical antipsychotic pair,
found by overlap alone. (Recorded here as "44 shared targets, 28, 18" before
the assembly grouping landed; 44 is the protein count, 41 the number of things
those group into, and the brain count is 17. Measured against the current
database, and the old and new code agree on every one of the 476 pair rows in
it, in all three grouping modes.) Tacrine's list now opens on **memantine** (5 shared, 4
corroborated) rather than rivastigmine, because the two share the NMDA
receptor subunits and the cholinesterase overlap is only 2 targets deep;
that is the right answer and not the one the cholinesterase framing predicts.
Galantamine, which contributes nothing but corroboration, lands on
rivastigmine, tacrine and donepezil at 2 shared and 2 corroborated each — the
four approved cholinesterase inhibitors finding each other. Dronabinol's opens
on cannabidiol, the only other cannabinoid here, at 5 shared.

Selecting a molecule also lights a **second hop** on the graph — the molecules
on its targets, at an intermediate opacity — so a shared-target relationship
is visible rather than something you had to find one click at a time.
Selecting a *target* does not: a target's second hop is every other target of
every molecule that binds it, which for ACHE is most of the graph.

**Protein assemblies are grouped, and how they are grouped is a control.** Five
assemblies cover 44 of the 207 targets: the 26-member voltage-gated calcium
channel, the 7-subunit NMDA receptor, 5-HT3 (5), GABA-A α1/α2/β2/γ2 (4) and the
KCNQ1/KCNE1 IKs channel (2). Each is drawn one of three ways — **collapse** into
a single hexagonal node, **hull** (a dashed enclosure, every subunit still on the
canvas and clickable), or **separate**. The defaults are graded by what ChEMBL is
willing to claim: `PROTEIN COMPLEX` collapses, `PROTEIN COMPLEX GROUP` gets a
hull, and `PROTEIN FAMILY` is not grouped at all. The tier default is one
control, a per-assembly override on the assembly's own panel is another, and
"Show every subunit individually" turns the lot off — including the panel's
assay-level fan-out rows and both de-duplications in the ranking. Each control's
reasoning is on hover rather than printed beneath it, still counted from the
loaded data rather than hardcoded; it was eight lines of prose sitting above
every panel, read once and scrolled past forever.

Collapse and hull both count the assembly **once** in `sharedTargets`; only
"separate" counts subunits individually. That is the load-bearing decision: the
hull is a claim that these proteins are one receptor, and a picture saying "one
receptor" beside a number saying "eight shared targets" is the disagreement this
project keeps trying not to have. The row prints both — "2 shared targets (8
proteins, grouped)" — so the compression is never silent.

It fixes what it was built to fix. **Dextromethorphan / memantine goes 8 → 2**,
**mibefradil / tacrine 13 → 6**, and **tacrine / memantine — the pairing this
section is proudest of — 5 → 3**, all three measured against the current
database. Caffeine/theophylline stays at 6, which is the check that matters:
the correction is aimed at assemblies and leaves everything else alone. **30 of
the 238 pairs change** under the defaults. Two de-duplications now run side by
side and they catch different failures: `fanoutRef` catches one experiment
attributed to many proteins, and assembly identity catches many experiments
against one receptor. Memantine measures the NMDA subunits one at a time, so it
shares no assay id with dextromethorphan's single seven-subunit screen — which
is exactly why de-duplicating by assay alone reported eight.

**A hull contains its members and nothing else.** The enclosure says "these
proteins are one receptor", and vis's physics knows nothing about assemblies, so
for a while it said that about whatever the layout happened to scatter inside
it. Two halves fix that, a cause and a guarantee. `glueEdges` are invisible
physics-only springs holding an assembly's subunits together — 39 of them over
the 5 assemblies, a star per assembly rather than a clique, because the
26-member calcium channel as a clique would be 325 springs and would overwhelm
every other force on the canvas — so one receptor is laid out in one place and
the hull is tight around it. `hullExclusions` is the guarantee: any node that is
not a member and lands in or against the outline is carved out of the drawn
region, even-odd filled and the dashed outline traced around the gap, so it is
visibly not enclosed. Nodes are deliberately never *moved* to achieve this —
`moveNode` restarts vis's simulation, so pushing an intruder out fights the
physics that placed it, and it would make the layout a function of the grouping
mode. The picture stays the force layout; only what the enclosure claims is
corrected.

Collapsing is deliberately **not** folded into the filter's "one rule read four
ways". `nodeVisible` / `edgeVisible` answer "is this in the picture" and only
the brain filter may change that answer; `nodeOnCanvas` / `edgeOnCanvas` answer
"is this drawn". A subunit inside a collapsed assembly is off the canvas and
still in the panel, still in the ranking, still findable — one hexagon on
screen, seven rows inside one collapsed row in the list.

Brain expression is **marked by default and filtered only on request**.
Confirmed targets get a thicker node rim — 4px against 1px, both in the
target's own dark orange — and the shared-target rows carry a brain count.
The rim is the honest default, because `expressed_in_brain` is 1 or NULL and
never 0 (invariant 10): 121 of the 207 targets are NULL, and a thin rim
asserts nothing at all.

**The sidebar holds the selection and nothing else.** The title, the search
box and the display options used to stack on top of it, so clicking a molecule
put its name a screenful below the click that opened it. Folding the controls
to one line helped and was not enough: folded or not, they still sat between
the reader and the thing they had just selected. All three are about the
picture rather than about what is selected, so the page is now three bands —
a top bar carrying the title, the search box, the display options and the reset
button; a strip under it for what a control is doing; and below that the graph
beside a sidebar that starts with the selection. The panel's `border-top` went
with them: it was there to stop a selection reading as a continuation of the
controls stacked above it, and there is nothing above it now.

The controls still **fold to one line**, and that line names every setting it
is hiding ("Display options — brain filter on · protein complexes collapse,
protein complex groups hull"), so folding them can never hide a changed one.
Opened, they are a popover hanging off their own button rather than a block
that pushes the page down; so are the search results. Both scroll if they must,
which clips nothing that matters, because `.help-text` is anchored `left:0;
right:0` to the row it belongs to and so lengthens the scroll rather than being
cut off sideways — the arrangement `#sidebar` has always had. What a control is
*doing* still does not fold, and is now not even in the bar: the banners get a
strip of their own across the window, because the whole argument for allowing a
filter that removes things is that it states its cost, and a cost behind a
disclosure is not being stated.

Moving them broke one thing that a test now holds: the delegated click handler
that opens every row on this page — panel rows, shared-target rows, search
results, a citation's edges — was bound to `#sidebar`, and the search results
are no longer in it. It is bound to `#app` now. A row somewhere nothing is
listening to is silent, not broken, which is the kind of regression that
survives a manual look at the page.

**"Confirmed brain-expressed targets only"** is the first
control here that *removes* things rather than marking them. Everything else
dims — a selection, a paper, a live search — and dimming is the wrong verb for
a reader who wants the periphery gone. The filter is deliberately the one that
has to argue for itself, because hiding on a field that has no negative is
exactly how "UniProt has no tissue comment" becomes a claim of absence. So it
states its cost, counted from the loaded data rather than asserted: it keeps
86 targets and hides 121 *unverified, not known to be absent*; it names the
best-connected ones it removes; and it names any molecule it deletes outright.
On this database that is **galantamine**, whose only two targets are ACHE and
BCHE — the entire reason it is an approved Alzheimer's drug, and neither
carries a UniProt tissue comment. A banner reporting 86/207 targets,
27/28 molecules and 277/654 edges stays on screen for as long as the filter is
on.

Visibility is **one rule read four ways**, so the canvas, the panel's lists,
the similarity ranking and the search cannot disagree about what is on screen:
a target survives on a positive tissue comment, an edge survives with its
target, and a molecule survives while it still has one edge left. A panel row
shows exactly when the node at its other end is on the canvas. Nothing shrinks
silently — a heading reads "Targets (26 of 63)", a shortened list says how
many rows the filter took, and the search stops offering results it would have
to scroll to a hidden node to open. Four views that can disagree about what
exists is how a picture goes wrong while every number in it stays correct.

The legend groups its rows under headings naming the channel each one encodes
— node shape, protein assemblies, node rim, line colour, line style — because
unlabelled they read as one flat list of fourteen unrelated things. Assemblies
get **one** heading covering both ways they are drawn: the hexagon was filed
under "Node shape" and the enclosure under a heading of its own, which named the
same feature twice and read as two unrelated things. Each block's explanation is
on hover rather than printed under its rows, which is where the rest of this
page's vocabulary already lives and which stops the legend growing tall enough
to cover the graph it explains; a test asserts every `.help` in it has a
`.help-text` to open. They open **upward**, because the legend is pinned to the
bottom-left corner and the panel's downward box would open off the bottom of the
window — the same failure that made the tier explanations unreachable. Its swatches are held to the
canvas by test: the brain-expressed swatch drew a white rim, which is the
*selected*-node border colour, so on screen it looked like no rim at all while
the note beneath it explained a distinction the reader could not see.
`tests/viewer.test.mjs` now reads the border colours and widths out of the
node-styling code and asserts the legend uses those, so the two cannot drift
apart again.

The same test file now also holds `ACTION_COLORS` to the legend, because a new
`action_type` in the data is otherwise silent: `actionColor` falls back, the
edge draws, and nothing says a mechanism is on the canvas that the legend does
not name. That has happened twice. `NEGATIVE ALLOSTERIC MODULATOR` arrived with
cannabidiol and fell through to `FUNCTIONAL`'s exact colour; `INVERSE AGONIST`
arrived with haloperidol's curated D2-family mechanism and fell through to a
grey one shade off `BINDER`'s — and `BINDER` means the opposite thing, raw
affinity with no curated mechanism at all. Inverse agonists now have their own
colour, the fallback is well clear of `BINDER`'s grey rather than a shade from
it, and two tests assert that every colour an edge can be drawn in has a
legend row and that the fallback is not also some named mechanism's colour.

Clicking an edge shows mechanism, binding and functional values, each with a
one-line summary of the measurements behind it ("13 measurements from 12
papers" — the paper count is always shown, including "from 1 paper", because
that is the case n most overstates) that expands to the individual rows — value, assay id, paper, what the assay
measured, the source's flag on that number, and any excluded rows with the
reason. Below
them, one row per database saying what it contributed, and, only where such a
thing exists, a reference that is not a measurement, labelled as a mechanism or
annotation reference so it cannot be mistaken for one.

Every field label carries a hover explanation (`HELP` in `viz/index.html`),
including the database names, which is where the difference between ChEMBL,
DGIdb and BindingDB — and so how much a number is worth — actually gets
explained. They are kept in one map rather than inline so the panel's
vocabulary can be read as a whole; several of its words (source, measurement,
database, n) mean specific and easily-confused things here. Molecule and
target panels link to Wikipedia first, ahead of the source records.

That covers the headings *inside* the target list too — the three tier names
and the fan-out row's "26 targets, one assay". Those had explanations that
could not be opened: `.help-text` is absolutely positioned against its nearest
positioned ancestor, and the tier and fan-out summaries were not one, so the
box anchored to the viewport and opened a screen-width panel below the fold.
An explanation nobody can reach is the same as no explanation, and this was
reported as the explanations being missing. Any new heading that calls
`helpLabel` needs `position: relative` on the element it sits in; a test
asserts it for all five.

**Shares targets with** is a `<details>`, open by default. It is the section
closest to the question the graph exists to answer, so it is not hidden — but
it sits under a target list that runs to 46 rows on tacrine, and a reader who
has read it once should be able to fold it away rather than scroll past it on
every selection. `.section-toggle` styles the summary as the `h2` it replaces,
so this is an affordance added to the existing heading rather than a second
kind of heading. Its rows open the two-molecule view described above rather
than the other molecule.

A **search box** at the top of the panel covers four kinds of thing, kept as
four separate result groups rather than one ranked list: molecules (name, common and brand names,
systematic name, formula, ChEMBL and PubChem ids), targets (gene symbol,
protein name, UniProt accession), interactions (either end's name, the
mechanism text, the action type — so "antagonist" finds all 18 and
"caffeine adora1" finds one), and **papers**.

Common names come from the reviewed `MOLECULE_ALIASES` map in
`scripts/export_graph.py`, keyed by ChEMBL ID and included in every export.
THC finds Dronabinol, CBD finds Cannabidiol, and alias matches show the matched
name beside the canonical result. Aliases also work in interaction searches
such as `THC CNR1`. Names were checked against ChEMBL 37's molecule synonyms;
the map excludes combination products and other isomers. It changes search
only, without renaming nodes or changing source matching or evidence. Add
reviewed names there and re-export; no database rebuild is needed.

Ranking is by *which field* the hit came from, not just whether it matched.
A field's position costs the full width of the match scale, so any match on
the name beats every match on a later field: searching `P30542` finds ADORA1,
but a partial match on a gene symbol still outranks an exact hit on some other
protein's accession. Words found scattered across several fields rank below
every whole-string match. A group heading counts *every* match and the list
draws at most eight, so a capped list never reads as the whole answer.

Searching a **paper** answers "does this study appear here, and what does it
hold up". The index is every citation in the database, keyed on its URL where
there is one — so ChEMBL citing PubMed 111 on three activity records and again
on the mechanism link is *one* paper, not four. Its panel splits what it
contributes in two, and never adds them: **measurements**, each stated against
the edge's own total ("2 of 13 binding measurements pooled into this edge" —
the paper's actual weight in the median, not a bare count of its rows), and
**references**, the mechanism or annotation citations that assert something
without measuring it. Binding and functional stay on separate lines
(invariant 4), and a BindingDB row says "none counted toward the value" rather
than "0 of n".

Not every citation is a paper, and the ones that are not say so on their own
panel rather than being filtered out of the index — someone who searches
"BindingDB" should find the record and be told it is a compound page, not a
study. Same for FDA labels, Wikipedia pages, and DGIdb's `PharmGKB, TTD`
fallback where a claim carries no publication. A PDSP reference (free text, no
link) and a ChEMBL PubMed link to the same study stay two entries: merging
them would mean matching a citation by its name, which is invariant 15 applied
to references, and would claim cross-database corroboration that might be two
different papers.

Typing **dims the graph to the matches** — matched nodes, the endpoints of
matched edges, every edge running between two matched nodes (without which
"PDE" reads as a scatter of unconnected dots rather than a region), and every
edge a matched paper touches. Clearing the box restores whatever was selected
rather than resetting the view out from under the reader. All the opacity
writing now goes through one `applyHighlight`, so the several things that dim
the canvas — a selection, a paper, a live search — cannot disagree about what
dimmed means.

`highlightMatch` slices the text *before* escaping each piece, because
escaping first shifts every offset (`&` becomes `&amp;`) and escaping after
inserting the marker escapes the marker. Paper titles are upstream free text
reaching `innerHTML`, so this is invariant 11 and not a formatting detail.

## Not done — the legacy seed pipeline

Everything in this list is backlog for the **legacy** six-source seed pipeline
and its viewer, and it is written in that pipeline's vocabulary (`fanoutRef`,
assembly hulls, the brain filter, BindingDB and DGIdb). It is kept for the same
reason the rest of this section is kept: it is why the rules above exist. None
of it is work queued against the pipeline that produces the page you open —
that list is **Not done — the cohort pipeline**, above, next to the work it
describes.

Two of these carry over in substance rather than in code. *Similarity is
shared-target overlap, nothing more* is half-answered in the cohort pipeline,
which does know about families; its other half, that affinity is not weighed at
all, is still true there and is listed above. *Brain expression is thin* is
worse in the cohort pipeline than here, where it is merely incomplete: there is
no brain signal in `db/cohort1.db` at all. The remaining six are specific to
this pipeline's data model and do not transfer.

- **Family fan-out is collapsed in the panel but still not on the canvas.** The
  assembly grouping above covers the 6 complex fan-out groups (45 edges); the
  other 23 groups and 88 edges are *paralogue* fan-out — one assay across the
  sodium-channel alpha subunits, or the PDE isoforms — and they are one row in
  the target list and still that many nodes in the graph. Most of that is
  deliberate and not pending work: merging paralogues would destroy the
  DRD2-vs-DRD3 and PDE4-vs-PDE5 distinctions the seed set was built to show, so
  there is nothing here that should be collapsed. What is genuinely missing is
  a way to *mark* them, so the visual mass of one experiment reads as one
  experiment without claiming the proteins are one thing. The hull machinery
  can now draw exactly that; what it would need is a grouping key that says
  "one assay" rather than "one receptor", and a visibly different style, since
  reusing the assembly hull would assert the merge it is trying to avoid.
- **Mechanism fan-out is not collapsed anywhere.** `fanoutRef` groups on the
  assay id, so it catches an experiment attributed to many subunits but not a
  *curated mechanism* filed against a protein family. Dipyridamole's single
  "3',5'-cyclic phosphodiesterase inhibitor" record fans out to 22 PDE
  accessions and pentoxifylline's to 13, and each arrives as a separate solid
  edge carrying `is_primary_mechanism`. The panel will say PDE8A went from one
  opinion to two when the second is one curator's family-level assertion. It
  is the same failure as assay fan-out, one level up, and nothing detects it.
- **Similarity is shared-target overlap, nothing more.** It does not know that
  ADORA1 and ADORA2A are the same receptor family, so two molecules hitting
  different members of one family score zero against each other. Nor does it
  weigh affinity: a molecule that binds a shared target at 7 nM and one that
  binds it at 200 µM count alike. Both are deliberate for now — the fix for
  the first is target family data this database doesn't hold, and the second
  would reintroduce potency into a ranking invariant 7 keeps it out of.
- **The calcium group is counted as one receptor by default, and that is a
  judgement rather than a fact.** Subunits of one assembly now count once (see
  the assembly grouping above), and the residual question is where the line
  sits. ChEMBL types the 26-member "Voltage-gated calcium channel" as a
  `PROTEIN COMPLEX GROUP` — "a poorly defined protein complex, where subunit
  composition is unclear" — and it lumps L-, N-, P/Q-, R- and T-type channels,
  which are genuinely different channels. Its default here is a hull, so all 26
  nodes stay on the canvas and mibefradil's individually-measured
  CACNA1G/1H/1I edges are all still distinct; but the *ranking* counts the
  channel once, which is most of why 30 of the 238 pairs change rather than the
  4 that a strict `PROTEIN COMPLEX`-only rule would move. The argument for it
  is that tacrine's evidence there is a single 26-way screen that cannot
  distinguish subtypes, so reading seven distinct shared targets out of it is
  manufactured similarity. The argument against is that mibefradil's evidence
  *can* distinguish them, and is being averaged in with tacrine's. One control
  away in either direction, which is the honest place to leave it, but it is a
  default that decides something.

  Two figures previously recorded here were wrong and are worth not requoting.
  "18 of 238 change" does not reproduce under any membership rule tried. And
  the tier assignments quoted from the first sketch of this work were off:
  5-HT3 is a `PROTEIN COMPLEX GROUP`, not a `PROTEIN COMPLEX`, and the NMDA
  receptor is reached as *both* — two precise `PROTEIN COMPLEX` dimers
  (GRIN1/GRIN2A, GRIN1/GRIN2B) sitting strictly inside the 7-member
  `PROTEIN COMPLEX GROUP`. A node can only be in one grouping, so
  `resolve_groups` keeps the largest assembly and carries the precise
  complexes along on `absorbed`, where the assembly's panel lists them. That
  demotes NMDA from the tier whose default is "collapse" to the tier whose
  default is "hull" — which is why the headline 8 → 2 correction depends on
  hull mode de-duplicating the count, and not only on collapse.
- **The filter bar still has one *filter* in it.** It has grown a grouping
  block, but grouping changes how things are drawn and counted, not whether
  they are in the picture — brain expression is still the only thing that
  removes anything. There is still no "hide single-source leads",
  no affinity threshold, and no way to drop the 81 single-edge targets — which
  is the one that would do most for the periphery, and the one the third
  cohort made pressing. The machinery is now in place for all of them:
  `setFilter` / `nodeVisible` / `edgeVisible` is a general predicate and every
  view already reads it, so a second row is a predicate and a label rather
  than another pass over the viewer.
- **Hover explanations are hover-only.** They open on keyboard focus too, but
  there is nothing for touch, where there is no hover state at all.
- **Brain expression is thin.** Hand-curated for the ADORA family;
  otherwise derived from UniProt tissue-specificity text, which many entries
  simply don't have.
- **BindingDB's ~3% uncurated remainder** is of unverified independence
  (see the log).
- **DGIdb's annotation reference is still a single claim per edge**, unlike
  ChEMBL's, so an edge DGIdb corroborates from several publications shows one.
  DGIdb's API returns the others; nothing reads them yet.

## Published snapshot

The **legacy** seed viewer is published separately and was not touched by any
of this. A self-contained copy of it (graph data and library inlined) is
published at
https://claude.ai/code/artifact/f9ba9e8b-b1d3-47df-8305-ba6ee64db59d.
Point-in-time, not live — re-export and republish to the same URL after a
pipeline run. Last republished 2026-09-06, from the 28-molecule / 207-target
rebuild of 2026-09-03: the two outstanding rebuilds (14 molecules on
2026-08-31, 28 on 2026-09-03) are now both out, so the published page and the
database agree again. Republishing stays a deliberate outward-facing step
rather than a side effect of a pipeline run.

The size question that was open here is answered: the inlined page is **3.19
MB** against the artifact host's 16 MB limit, of which `graph.data.js` is 2.33
MB and the vendored library 0.69 MB. Data has room to roughly quadruple before
the limit is the binding constraint, but it is worth re-measuring rather than
assuming at the cohort that would double the graph again.

Built by inlining
`vendor/vis-network.min.js` and `graph.data.js` into `viz/index.html` and
stripping the `<!DOCTYPE>`/`<html>`/`<head>`/`<body>` scaffolding, which the
artifact host supplies itself; there is no script for this yet. The 2026-09-06
republish asserted each of those landmarks before cutting, so a moved `<body>`
or a second `<script src>` fails the build rather than silently shipping a
half-inlined page.
