# Data-quality log

Chronological record of what went wrong in this project's data and what was
done about it. Split out of `CLAUDE.md` on 2026-08-25, which had grown to 27KB
of narrative that was being loaded into context on every session; `CLAUDE.md`
now carries the goal, the invariants and how to run things, and this file
carries the history behind them.

Read this before changing how any value gets into the database. Most entries
exist because a plausible-looking number turned out not to mean what the
schema said it meant, and the reasoning is easier to preserve than to
rediscover.

---

## The recurring lesson

Every serious problem found so far has been of one shape: **a value that is
technically present in a source, but does not mean what this schema assumes it
means.** Not missing data, not API errors — data that parses cleanly, stores
cleanly, and is wrong.

- `">30000"` is not a potency of 30,000 nM. It's "nothing detected up to
  30,000 nM".
- BindingDB reporting the same Kd as ChEMBL is not two measurements. It's one
  measurement, republished.
- The first 100 records ChEMBL returns are not the 100 most relevant. They're
  the first 100 by internal id.
- A UniProt full-text hit ranked first is not the protein you named.

The defence in each case was the same: check what the source itself says about
its own value (`standard_relation`, `data_validity_comment`, "Curated by",
`page_meta.total_count`, the recommended name) rather than reading the number
alone.

---

## Sources, and what each is actually good for

| Source | Role | Caveat |
|---|---|---|
| **PubChem** | compound identity, SMILES, CAS numbers (legacy pipeline only since 2026-10-13) | CAS numbers are the only join key into PDSP; links compounds to MeSH by name; blocks an address that keeps asking while throttled |
| **FDA UNII records** | a substance's identity by structure, and its CAS number, which is how a molecule reaches its own MeSH record | registers stereo-defined forms and racemates as such, where ChEMBL often draws no stereochemistry; no InChIKey for most biologics |
| **Wikidata** | an item joining a ChEMBL ID to a Wikipedia article and to a MeSH ID | community-edited; used only by exact identifier, and agreed with FDA's route on 729 of 735 molecules where both answer |
| **ChEMBL** | primary: curated mechanisms + Ki/Kd/IC50 binding assays, functional assays | needs pagination; needs `standard_relation` checking; has real curation errors |
| **UniProt** | protein identity, function, tissue specificity; its reviewed human proteome is what D20 aligns non-human records against | `protein_name:` search is relevance-ranked, not exact; the "stream" download is always the current release, so the copy is pinned |
| **DGIdb** | cross-validation that an edge exists | no measurements of its own |
| **BindingDB** | target *discovery* | ~97% of what it returns here is republished ChEMBL/PDSP; REST endpoint unreliable |
| **PDSP Ki DB** | independent Ki measurements, strong for CNS | bulk CSV only, no query API, no per-row citation link |
| **GtoPdb** | curated action (agonist, antagonist, …) on the receptor, channel and enzyme families this project is about | a ligand's Type can be carried onto secondary targets it was only screened at (vilazodone); anonymous bulk access announced to end |
| **FDA pharmacologic classes (NLM RxNav)** | FDA's Established Pharmacologic Class, mechanism of action and physiologic effect, as an answer key for the similarity ranking; never shown, never evidence | US-labelled drugs only (627 of 2,452 entries have an EPC); RxNorm files a salt apart from its ingredient, and some ChEMBL forms as ingredients of their own (aminophylline); unpinned, so its version is recorded |

---

## 2026-10-13 — FDA's classes, and theophylline lost to its own salt

**What was added.** `scripts/resolve_cohort_fda_classes.py` writes FDA's
Established Pharmacologic Class, mechanism of action and physiologic effect
into `molecule_classes` as `fda_epc`, `fda_moa` and `fda_pe`, as a third
answer key for the similarity ranking
([SIMILARITY-LITERATURE.md](SIMILARITY-LITERATURE.md), step 2). The route is
identifiers only: InChIKey to FDA UNII (the same file the MeSH backfills
read), UNII to RxNorm, a salt's precise ingredient to its ingredient, and
the ingredient's classes from RxClass, kept only where FDA's labels (FDASPL)
or FDA's reference terminology (MED-RT) assert them for the ingredient
itself. The classes stay in the database; the page does not show them.

**What went wrong first.** The first rule read every identifier a molecule
has, the parent's and every folded form's, and required them to reach one
ingredient between them. That dropped 22 molecules as ambiguous, theophylline
among them: ChEMBL folds aminophylline onto theophylline, and RxNorm files
aminophylline as an ingredient of its own (RxCUI 689 against 10438). Neither
source is wrong. A form ChEMBL folds for chemistry can be a product RxNorm
keeps apart, and that says nothing about which drug the parent is.

**The rule now.** The parent's own structure decides. A form is read only
where the parent's UNIIs reach no ingredient, and the forms must then agree.
That leaves 2 dropped, each ambiguous in itself: CHEMBL367149, whose one UNII
RxNorm maps to two ingredients, and CHEMBL1161681, whose parent carries two
UNIIs that reach two. 930 molecules reach one ingredient (911 by the parent,
19 through a form), 627 have an EPC, 787 a MoA and 733 a PE.

**What is not known.** 909 molecules have a UNII that RxNorm does not know
(1,489 of the 2,879 UNIIs asked); most are presumably substances never
marketed in the US, which is the key's stated limit, but nobody has looked.
FDA's MoA mixes how a drug acts with how it is handled: sertraline is a
*Cytochrome P450 2D6 Inhibitor* as well as a *Serotonin Uptake Inhibitor*.
The backfill stores both; the answer key ignores the pharmacokinetic ones
(`analysis/similarity_harness/fda_keys.json`).

## 2026-10-13 — PBF-509 had an article, and Wikidata could not say so

**What happened.** The user found PBF-509 with no Wikipedia link although
English Wikipedia has an article on it, *Taminadenant*. The article sits on
Wikidata item Q133844245, which carries a label and nothing else: no ChEMBL ID,
no InChIKey, no statement of any kind. No Wikidata item carries
CHEMBL3694769 or PBF-509's InChIKey at all, so the identifier route had
nothing to find. The article's own drugbox, though, declares `ChEMBL =
3694769` and the exact InChIKey.

**How many more.** Of the 804 molecules without a link, 103 have an article
whose drugbox links their own ChEMBL ID, and they were missing for a reason
more general than one empty item: **Wikidata and ChEMBL disagree about which
structure is the drug.** ChEMBL's parent for varenicline, vinblastine,
clindamycin and atropine is drawn with stereochemistry that the item holding
the article does not carry, so both identifiers land on an item with no
article. Warfarin's and methamphetamine's articles sit on a "racemic mixture"
item with no identifiers. Candesartan cilexetil's, olmesartan medoxomil's and
dabigatran etexilate's articles are the parent drug's, whose item names the
active acid. Albuterol, metamizole, chlorprothixene, buprenorphine, glutamic
acid and methionine were all in this group.

**The route taken.** Wikipedia's external-link index (`list=exturlusage`)
lists every article linking a ChEMBL compound page, about 10,500 links in 21
requests. That is a lookup by identifier in the reverse direction, not a title
search. An article is accepted for a molecule only where Wikidata found no
article at all (an ambiguous Wikidata answer stays a refusal), and only when:

- a `{{Infobox drug}}`, `{{Drugbox}}` or `{{Chembox}}` on it names the
  molecule's **own parent** ChEMBL ID in its ChEMBL parameter. A ChEMBL link
  in a reference or a list of compounds is not a claim about the article.
- any InChIKey that infobox declares shares the molecule's **skeleton**, the
  first block. The skeleton rather than the whole key, because the stereo
  disagreements above are why the route exists. A side with no key (a
  biologic) matches on the ChEMBL ID alone, as the Wikidata route does.
- it is the only such article.

Measured against the 1,347 molecules Wikidata had already linked whose ChEMBL
ID an article's infobox also carries, the infobox route names the same article
for 1,339. Of the 8 where it differs, the key check catches the worst:
*Nitrous oxide (medication)*'s drugbox carries **oxygen's** ChEMBL ID
(CHEMBL1234886), and its InChIKey is nitrous oxide's. It is one of 15
infoboxes, on already-linked molecules, whose InChIKey contradicts the ChEMBL
ID beside it. Wikipedia's infobox identifiers are hand-entered, and the
InChIKey is the check on them.

**Never through a salt form's ID.** 23 more molecules are reached only
through one of their forms' ChEMBL IDs, and most of those would be right:
mesna, ipratropium bromide, methylene blue, sodium thiopental, carbachol,
fluciclovine (18F). Two would not be. ChEMBL files a deuterated drug as a
form of its parent, so ethyl linoleate would link *Deulinoleate ethyl* and
tebitorexant *Tebideutorexant*, each a different drug developed for being
deuterated. An isotope sits in the InChIKey's second block, outside the
skeleton, so the key check cannot tell them apart, and the cohort database
holds no structure for a form to check against. The Wikidata route has
always read the parent's ID alone, for the same reason.

**Result.** 98 molecules linked: the 103 less 3 whose infobox structure
differs (ribose (pyranose), rocuronium, bryostatin 1, each an infobox drawing
a salt or a relative under the parent's ID) and 2 with two qualifying
articles (inositol, vasopressin). PBF-509 links *Taminadenant*.

**Targets: the protein's article before the gene's.** Albumin and FGF1 were
also unlinked although both have articles. Their protein item and gene item
each carry a *different* English article (*Human serum albumin* on the
protein, *Serum albumin* on ALB), and the query read the two as one set and
refused it as ambiguous. Both are reached by identifier, and a target here is
keyed by its UniProt accession, which is the protein item's. The protein's own
article is therefore taken first, and the gene's only where the protein has
none. That is a fixed precedence between two answers, not a choice between
them; two articles on one side are still a refusal.

It holds only where the protein item names exactly one gene. The first run
without that condition linked Heat shock 70 kDa protein 1A to *HSPA1B*:
HSPA1A and HSPA1B are one sequence, Wikidata files each protein under both
genes, and the HSPA1A protein item carries the HSPA1B article. With two genes
the protein is not one-to-one with either, so the disagreement stays a
refusal; lactoperoxidase, whose article is right, is refused with it. 14
targets were linked: the D3 dopamine receptor, tyrosine hydroxylase, albumin
and FGF1 among them. Six stay ambiguous, the α7 nicotinic receptor among them:
Wikidata files it under CHRNA7 and under the CHRFAM7A fusion gene, each with
its own article. Under invariant 15, the remedy for one like that is a
hand-written Wikidata item, and none was written.

The first form of the target query computed the route with a `BIND` inside
each branch of its `UNION`. That stopped the endpoint's optimiser: a chunk of
15 accessions took 65 s and was refused with a 504, against 0.2 s without it.
The route is now computed in the projection, after the join.

**Left as they are, and why:**

- **Human enzymes whose article is the enzyme class** (fatty acid synthase,
  glycerol kinase, β-glucuronidase). Neither the protein item nor the gene
  item has an article; English Wikipedia writes about the EC class, which can
  cover several human isozymes. That is the family-for-member link D06
  refuses.
- **Non-human records.** About 1,200 rat, mouse, bovine and other
  single-protein records have no article of their own; Wikipedia writes about
  the human protein. 567 of them belong to a protein whose human record is
  linked and shown in the same panel. 68 proteins are here *only* as
  non-human records with a D20 human match, and their nodes show no
  Wikipedia link anywhere. Giving such a record its human orthologue's
  article would move a fact between records, which D20 has so far refused
  for claims; it is the user's call, not a backfill's.
- **Wikidata's empty item.** Q133844245 could be given CHEMBL3694769 and the
  InChIKey upstream, which would fix it for everyone reading Wikidata. That
  is an edit to a public database and was not made.

## 2026-10-13 — MeSH actions read from MeSH, and PubChem left behind

**What happened.** D21 nearly doubled the catalogue, and the backfill that
reads MeSH pharmacological actions through PubChem could not finish. PubChem
answered about 400 requests and then refused this machine, twice, at a pace
(~180 a minute) that had run 2,400 requests without trouble in September. Its
throttling header then read every meter Green and still answered "too many
requests per second or blacklisted": the address was on a temporary block. The
script's own five quick retries, a probe loop asking every minute for two hours,
and each restart the moment a probe got through kept it there. After a night,
68 requests got through before the next block.

**The lessons about a rate-limited source,** kept because the next one will
behave the same way:

- Read the source's own signal (`X-Throttling-Control` here) rather than
  inferring the limit from failures.
- On a block, stop. Retrying into it, or polling to see whether it has lifted,
  are the requests that keep it in place.
- Resume hours later, with one probe.

**What changed instead.** The question became whether the actions need PubChem
at all. PubChem's route also links a compound to MeSH **by name**, the source of
the tafamidis/"FX006" error (2026-09-26), which a judge had to catch. NLM's own
MeSH files carry each record's `PharmacologicalActionList`, and a molecule's own
record can be reached by identifier, the route the structure classes already
take. `resolve_cohort_pharm_actions.py` now places each molecule on one MeSH
record, each step tried only where the one before placed nothing:

1. **UNII.** The InChIKey reaches the FDA UNII registered with exactly that
   structure, and the UNII reaches the MeSH record carrying it.
2. **CAS.** Where the UNIIs reach no record, the CAS numbers FDA lists for
   them are tried, because older MeSH records carry a CAS number where newer
   ones carry the UNII (GABA, budesonide). As a fallback only: used alongside
   the UNII, a CAS number a second record shares refused eplerenone and
   lacosamide.
3. **A mixture of stereoisomers.** Where ChEMBL draws no stereochemistry and
   FDA has no flat structure to match, the FDA substance registered as a
   mixture of that skeleton's stereoisomers (a racemate, written as two
   InChIKeys sharing the first block) is used. This places methylphenidate,
   nebivolol and pentazocine. A molecule drawn *with* stereochemistry never
   reaches this step.
4. **Wikidata.** Where no FDA step places the molecule on exactly one record,
   the MeSH ID on the Wikidata item carrying its ChEMBL ID is used. This
   reaches antibodies, proteins and peptides (exenatide, teriparatide), which
   FDA files without a structure.

Two records at any step is a refusal (invariant 6).

**What was measured before it was adopted**, on the 1,335-entry build whose
PubChem backfill had completed (`analysis/mesh_route_b/`,
[MESH-ACTIONS-ROUTE-B.md](MESH-ACTIONS-ROUTE-B.md)):

- **Coverage.** 848 molecules carry actions against PubChem's 787. 760 are
  identical, 7 differ, 20 are PubChem's alone and 81 the new route's alone.
- **None of the 11 links the judge set aside reappears,** because no step makes
  a name-based link.
- **Tarenflurbil loses flurbiprofen's COX actions,** one of the two open MeSH
  findings. PubChem had carried them across from the racemate's record.
- **Every molecule the stereo-mixture step placed that PubChem also covers
  agrees with PubChem** (7 of 7). So does every one the Wikidata step placed
  (12 of 12).
- **Wikidata and the UNII route name the same record for 729 of 735
  molecules.** The 6 others are a molecule filed as a narrower concept of
  another record (armodafinil within *Modafinil*), and the UNII route's answer
  stands there.

**What was measured and refused.** Matching on the InChIKey's first block, the
skeleton with stereochemistry ignored, reaches 30 more molecules, but:

- it put lucerastat on miglustat's record, a different molecule differing only
  in stereochemistry;
- it gave esmethadone methadone's opioid actions, though esmethadone was
  developed for its low opioid activity.

That is the error shape invariant 6 exists to stop. The stereo-mixture rule is
the narrow version that keeps the gains without the errors.

**What it costs.** 20 molecules PubChem reached are now without actions:

- 9 carry a UNII no MeSH record holds (semagacestat, relugolix);
- 4 are flat structures whose stereoisomer mixtures reach no single record
  (doxepin, menthol);
- 4 are in neither FDA's file nor Wikidata (liraglutide, ziconotide);
- 2 are drawn with a different defined stereochemistry by ChEMBL and FDA
  (benfotiamine, dextrose);
- 1 has a record with no action (samidorphan).

And the harness's second judge moved, since its answer key is built
from these actions: the same 1,335-entry ranking grades 47.4% top-1 and MRR
0.6060 against PubChem's key, and 50.4% and 0.6335 against the new one. Those
are two keys, not a better ranking.

---

## 2026-10-11 — "Several publications" for a claim one paper measured

Found by a reader at caffeine and human ADORA1, in the broader basis (ChEMBL's
*homologous* assignment, relationship type `H`: filed against the human record,
but ChEMBL could not confirm the protein measured was the human one). The claim
has four rows from three studies: a 2000 paper's Ki = 29 µM, a 2023 paper's
AC50 > 30 µM, and two DrugMatrix rows with no value. The panel said
*Preliminary · Several publications, no two in one endpoint class*, and the
reader asked, fairly, why three sources were not Supported.

The tier was right: one exact value from one paper. The reason was wrong. It
was chosen from every study with **any** row, so the bound-only 2023 paper
counted as a second publication, while replication itself was always counted
over exact values only. The patent and deposit branches had the same fault,
counting rows rather than studies with an exact value, and a claim whose exact
values came from both a patent and a deposit fell through to "one
publication".

**What changed** (evidence policy 1.1.0 to 1.1.1). A Preliminary reason now
names only the studies that hold an exact value, with a new
`patents_and_deposits_only` for the fall-through case. The other studies are
still listed with the claim and still counted in `n_publications`. The tier
condition now matches the policy's own definition: an identifiable study
(publication, patent or deposit) with an exact value. The old code accepted any
study key at all, so ketoprofen's broader functional claim at SLC22A7 was
Preliminary on one document with no PubMed id, DOI or patent, beside a paper
that reported only a bound. It is now Limited, *No identifiable study*.

Measured on the rebuild: the same 80,491 non-GtoPdb claims, 420 reasons
changed (334 "several publications" to "one publication"; 83 "one
publication" to deposits, patents, or both; 2 "several publications" to
deposits or patents only), and that one tier. No Supported claim moved, so no
score did.

---

## 2026-10-10 — alfuzosin's agonist is withheld, and how many more there might be

The 2026-09-27 entry below left ChEMBL's alpha-1 `AGONIST` for alfuzosin in
place and let GtoPdb's antagonist sit beside it. That fixed the half that was
reported: tamsulosin and prazosin stopped being alfuzosin's opposites. It left
the other half reversed. A molecule carrying AGONIST and ANTAGONIST at one
protein matches *anything* there, so alfuzosin was never opposed to
phenylephrine, midodrine or any other alpha-1 agonist; its family line was
coloured as an agonist and listed under the Agonist filter, and the panel read
"Adrenergic receptor alpha-1 agonist". A viewer test now holds both states
(`cohort_viewer_gtopdb.test.mjs`).

**Where the error comes from.** It is one row, `drug_mechanism` mec_id 1161,
filed against the hydrochloride (CHEMBL1723) at the alpha-1 *family*
(CHEMBL2094251). Its one reference is the DailyMed label, whose section 12.1
reads *"Alfuzosin is a selective antagonist of post-synaptic
alpha1-adrenoreceptors."* - the record contradicts its own source. Records
1158-1170 are one run through the alpha-1 family, agonists (phenylephrine,
methoxamine, metaraminol, midodrine) and blockers (carvedilol, doxazosin,
prazosin, tamsulosin, terazosin) interleaved; every blocker but alfuzosin is
`ANTAGONIST`. A slip in data entry, in other words, and the live web service
still served it on 2026-10-10.

**What changed.** A new list beside `CHEMBL_ASSAY_LINK_EXCLUSIONS`:
`CHEMBL_MECHANISM_ACTION_EXCLUSIONS` in `config/cohort1_evidence.json`
(evidence policy 1.0.0 to 1.1.0), applied by
`evidence.withhold_excluded_actions`. The action is *withheld*, never
rewritten: the record stays, its claim keeps curated support - nobody disputes
that alfuzosin acts at alpha-1 - and ChEMBL's word is kept verbatim in
`curated_mechanisms.excluded_action_type` with the reason in
`action_exclusion`. The claim's `mechanism_of_action` goes with it, since that
sentence names the same direction, and `claims.action_exclusion` carries one
line the panel shows under a "direction withheld" pill. Writing ANTAGONIST in
its place was rejected: that would be this project authoring a ChEMBL record,
and GtoPdb already supplies the antagonist at alpha-1A, 1B and 1D. Each entry
names the action it expects; if ChEMBL corrects the row, or changes it to
anything else, the build stops and so does a test reading the bulk file, so a
withheld right answer cannot go unnoticed. The error report to ChEMBL is
drafted and has not been sent.

Measured on the rebuilt payload: phenylephrine, an alpha-1 agonist given to
raise blood pressure, was alfuzosin's **3rd** nearest neighbour of 421 and is
now 236th, opposed at all three receptors; midodrine falls from 119th to
370th, and prazosin rises from 4th to 2nd behind tamsulosin. Nothing else
moves: the catalogue's counts are identical, and the harness grade is
unchanged under both judges (ATC top-1 38.7%, MRR 0.5119; MeSH 47.4%, 0.6060).

**How many more.** Searched three ways, none of which is an audit:

- *ChEMBL against GtoPdb* at a shared protein: about 50 pairs disagree, nearly
  all in vocabulary (AGONIST/PARTIAL AGONIST, ANTAGONIST/INVERSE AGONIST,
  OPENER/ACTIVATOR) or in genuine pharmacology (nalmefene at kappa). Alfuzosin
  is the only plain agonist/antagonist contradiction on an undisputed drug.
- *ChEMBL against itself*: across all of ChEMBL 37, 17 parent-target pairs
  carry different actions on different forms, 2 in the catalogue (fingolimod
  AGONIST / BINDING AGENT, varenicline AGONIST / PARTIAL AGONIST), neither an
  opposite; and one parent opposed between a protein and a family containing
  it (dilevalol, not a member).
- *ChEMBL's own flags*: of the 803,096 activity rows scanned, 176 carry
  "Potential transcription error" and 9 "Potential author error". 156 of the
  176 are exact and counted, in 64 claims, 43 of them Supported in the direct
  human basis. Whether any of those 43 owes its tier to the flagged row has
  not been looked at.

None of the three can find an error of alfuzosin's shape - a single row with
nothing beside it to disagree - unless a second curator happens to cover the
pair. One in 1,486 curated mechanisms is the floor, not the rate; the way to
an estimate is a random sample of mechanisms read against the references they
cite.

---

## 2026-10-09 — a structure class's Wikipedia article, and why Xanthines had none

The user found the *Xanthines* class panel had no Wikipedia link and asked for
one wherever it is appropriate. Structure classes had never been linked, and
the obvious route does not reach this one: Wikidata does record MeSH
descriptor D014970 (P486), on item Q49922434, but that item has **no English
article**. English Wikipedia writes about the class inside the article on its
parent compound — *Xanthine* has the derivatives — and Wikidata keeps the
class and the compound as two items and says outright (P1889) that they are
different. Over the 726 structure classes in the build: 415 reach exactly one
article through their own item, 310 reach an item with none, and one
descriptor (D001127, Arginine Vasopressin) sits on two items with two articles
and is dropped (invariant 15).

Tried for the 310, and what each gave:

- **"named after" (P138)** — reaches exactly one class (Purines → purine).
- **"subclass of" (P279)** — the wrong direction: Xanthines is a subclass of
  "purine alkaloid", which has no article either, and walking up would link a
  class to something broader than it.
- **MeSH's own record** — the descriptor holds one concept, "Xanthines", and
  names no parent compound; the supplementary records mapped to it are many
  compounds, and choosing one would be choosing by name.
- **The category's main article** — taken. The item names its main category
  (P910, *Category:Xanthines*), and English Wikipedia's editors declare that
  category's main article with `{{Cat main|Xanthine}}`. That is a link
  followed, not a title searched for, so it keeps to invariant 15. It reaches
  104 categories and yields 80 articles: Piperidines → *Piperidine*,
  Phenothiazines → *Phenothiazine*, Dibenzazepines → *Dibenzazepine*,
  Benzylamines → *Benzylamine § Pharmacology and derivatives*. All 80 were read
  by hand when this was written. The loosest is Pancreatic Hormones →
  *Pancreatic islets*, where the declared "Pancreatic hormone" is Wikipedia's
  own redirect; it has no member filed directly, and the page names the
  article it opens, so the link says what it is.

The rule refuses a category with no such template (23), one whose template
names no article (1) and so defaults to the category's own title, one naming
several or carrying two templates, and an article that is missing or a
disambiguation page. `{{Cat more}}` and `{{See also}}` point further afield
and are not read. It is used only where the class's own item has no article.

The same route was measured on the MeSH **pharmacological actions** and not
adopted: of 164 action classes with an article-less item, 14 have a category,
and its main article is a topic rather than the class (Alkylating Agents →
*Alkylation*, Teratogens → *Teratology*). USAN stems have no identifier at all.

Stored in a table of its own, `class_wikipedia`, with the item, the route and
the category, rather than as a column on `class_labels`: the MeSH backfills
delete and rewrite their `class_labels` rows on every run and would wipe it.
Because the class rows must exist first, `resolve_cohort_wikipedia.py` now
runs after the MeSH backfills. The class panel links the article by its title
("Wikipedia: Xanthine"), since on the category route it is usually the parent
compound's article rather than one about the class.

## 2026-09-27 — what "Outside typical range" means, and where its edges are

Theophylline's one measurement at PI3Kalpha (CHEMBL4005, activity 14553316) is
an IC50 of 300,000 nM from a review, *Small molecules targeting
phosphoinositide 3-kinases*, and carries ChEMBL's `data_validity_comment`
"Outside typical range". The viewer printed that phrase as a bare warning pill
and the user asked what it meant.

ChEMBL's own `data_validity_lookup` table defines it as *"Values for this
activity type are unusually large/small, so may not be accurate"*: an automatic
range check, not an error found in the paper. ChEMBL publishes no bounds. In
this build, of the 6,134 observations carrying it, every exact nM Ki, Kd, IC50
and EC50 flagged is weaker than 100 µM or stronger than 0.01 nM, with 4 EC50
exceptions (73–468 nM); 14 unflagged rows sit above 100 µM. So the edges are
ChEMBL's usual range but not a rule, and the page says "unusually weak or
strong" and then states which edge a given row is past, never the range
itself as ChEMBL's. 1,646 of the 6,134 are counted. Nothing changed in the
data: the flag is kept and never drops a row, which is also why a weak value
like caffeine's ADORA3 Ki of 100 µM stays in (invariant 8).

The pill now opens an explanation for each of ChEMBL's seven phrases
(`VALIDITY_COMMENTS` in `viz/index.html`), and "Manually validated" (a curator
confirming the value) is no longer drawn as a warning.

## 2026-09-27 — one receptor, four species, twelve "shared targets"

The user opened naloxone and naltrexone's pair panel and found the same
receptor heading repeated, and asked whether a target shared across species
counts as much as two different targets. It counted as much. The pair's
"12 shared targets" were mu, kappa and delta in up to four species (human, rat,
mouse, guinea pig) and CYP2D6. Rarity is per record, and fewer molecules are
measured on a rat receptor, so the non-human records weighed *more*: the human
ones carried 18% of the score. ChEMBL names a protein alike in every species,
so the panel could not show which was which; the headings now name the species.

The fix needed to know which records are one protein, and every identifier
route failed: ChEMBL has no orthology, NCBI's list misses the guinea-pig mu
receptor (no GeneID in UniProt), OrthoDB groups mu with kappa, and OMA lacks the
rat and guinea-pig records. A gene symbol would have been right here and is
still refused (invariant 6), for the reason that invariant exists. So it was
matched by sequence ([COHORT-2.md](COHORT-2.md), D20), and three data facts shaped the
rules, each now a case in the script's docstring:

- **ChEMBL holds fragments.** The guinea-pig mu receptor, P97266, is 98
  residues. Measured over the longer sequence it was 24% identical to human
  OPRM1 and refused. Identity is now read over the record's own length, with a
  stricter bar (90%) for a fragment.
- **ChEMBL holds one protein under several accessions.** Guinea pig has mu as
  that fragment and as full-length Q8CGM4, and rat has the noradrenaline
  transporter three times (Q63380, Q9WTR4, F1LNR9; 91–99.7% identical to
  each other). Treating each as a rival refused both proteins. A species protein
  ≥90% identical to the record is now the same protein filed twice. A real
  rodent gene cluster (Cyp2d3 against Cyp2d26, 78%) sits well below that bar.
- **A fragment of one receptor looks like its siblings.** Over its 98
  residues the mu fragment is 82% identical to human kappa, which blocked
  guinea-pig kappa's match. A species protein is now a rival only if its own
  best human match is the same protein.

524 of 578 mammalian records matched. The 15 matches whose gene symbols differ
were read one by one and are right (GPM2 is the old name of CHRM2, and Agtr1a
and Agtr1b are both AGTR1). The 54 refusals leave their records counted as
before, so the rule can undercount a merge and never invent one.

---

## 2026-09-27 — where a direction can come from, and what each source's word is worth

Cohort 2 opened by adding GtoPdb's curated action as a direction on pairs the
catalogue already draws ([COHORT-2.md](COHORT-2.md), D17). Choosing it meant
measuring the three candidates first, and two of the findings are about data
already in the database.

**ChEMBL's curated mechanism for alfuzosin is wrong.** `drug_mechanism` files
it as an alpha-1 `AGONIST` ("Adrenergic receptor alpha-1 agonist"). Alfuzosin
is an alpha-1 blocker; MeSH files it under *Adrenergic alpha-1 Receptor
Antagonists* and GtoPdb as an antagonist at alpha-1A, 1B and 1D. Under D15 the
error quartered alfuzosin against tamsulosin, prazosin and every other
alpha-1 blocker it shares receptors with. It is not excluded - the record is
ChEMBL's and says what it says - but GtoPdb's antagonist now sits beside it,
and a molecule whose two curators disagree is not opposed to anything, which
releases those pairs. Worth reporting to ChEMBL; nothing has been sent.

**ChEMBL's per-activity `action_type` describes the assay, not the drug.**
ChEMBL 37 fills `activities.action_type` on 5,453 of this catalogue's
observations, and it would direct 1,800 more pairs without leaving ChEMBL.
It was not used. Every triptan is labelled `ANTAGONIST` at 5-HT1B/1D, on Ki
assays "assessed as inhibition constant"; diazepam is an `INHIBITOR` at
GABA-A because it displaced [3H]flunitrazepam; cabergoline is an `INHIBITOR`
at D2. Where it overlaps ChEMBL's curated mechanism it agrees on direction
197 times in 215 on binding assays and 64 in 67 on functional ones, which
sounds good until the misses are read: they are systematic, on exactly the
receptor classes this project is about, and they would demote agonists
against their own classmates. The column is the word a curator chose for one
experiment's readout.

**GtoPdb's action is better, and not perfect.** Where GtoPdb and ChEMBL both
direct a pair, they agree 286 times in 289 at GtoPdb's primary targets and 96
in 100 elsewhere. The disagreements are mostly genuine pharmacology (nalmefene
and samidorphan at kappa, partial agonism read two ways), but one error shape
was found: GtoPdb files vilazodone as an `Agonist` at D2, D3 and H1, citing
the discovery paper's binding screen (PMID 15341484) - a ligand's Type carried
onto targets it was only measured at. It is rare where it can be checked, it
is kept, and the page names GtoPdb as the source of every such direction.

**MeSH pharmacological actions cannot direct a pair,** because they are filed
against the molecule and say nothing about which target. About 113 of the 303
actions in the catalogue name a target class ("Phosphodiesterase Inhibitors",
"Serotonin 5-HT1 Receptor Agonists"). They are the right referee for the two
errors above - they contradict both - and the wrong source for a direction,
which would need a hand-written map from each action to protein families.

---

## 2026-09-26 — the two MeSH class sources, and what PubChem's name links got wrong

Moved here verbatim from `CLAUDE.md`'s data model on 2026-09-27, when that
file was compacted; the data model there keeps the rule, and this keeps the
cases and counts that justify it. Counts are as of the 2026-09-26 build.

A third source, `mesh_pa`, holds the **MeSH pharmacological actions** NLM's
indexers record for each drug ("Antidepressive Agents, Tricyclic",
"Phosphodiesterase Inhibitors"). It is written only by
`scripts/resolve_cohort_pharm_actions.py`, a network backfill like the Wikipedia
and trial ones: a rebuild wipes it and it is rerun after. The route is an
identifier at each step. InChIKey goes to the PubChem compound(s); PubChem gives
the MeSH action *concept* ids it lists for the compound; NLM's own descriptor
file for a pinned year (`desc2026.gz`, cached in `db/cache/`, its sha256 in
`build_manifest`) gives each concept's descriptor and tree positions.
`class_labels.parents` carries the hierarchy inside the action branch (D27),
from depth 4 down, so a drug filed as a tricyclic is also under "Antidepressive
Agents". The one link that is not ours to check is PubChem's own
compound-to-MeSH match, which PubChem makes from names and registry numbers.
Where an InChIKey matches several compounds, their actions are taken only if
every compound listing any lists the same set; none disagreed in this run.

That match is by name, and it was found to be wrong in a way that shows. A brand
name or code that means two things joins both records, and the compound gets
the other record's actions. Tafamidis carried triamcinolone's steroid actions
through "FX006": FoldRx called a tafamidis study Fx-006, and Flexion used FX006
for triamcinolone. DMSO carried fluocinonide's through "Topsym", a fluocinonide
solution in DMSO. So each action is now traced to the MeSH records PubChem links
the compound to (its "MeSH Entry Terms"). Each record is judged by identifier
(`Judge`). A record is set aside only on **positive evidence** that it is
something else. That means one of three things. A UNII on it has a structure
ChEMBL files under a different parent. Or it is a product with no UNII mapped to
exactly one heading, and that heading is a different substance. Or it is a
combination containing another drug. An action is dropped only when every record
supplying it was set aside. The first version of the rule compared InChIKeys
directly and set aside six molecules' own substances. Dexketoprofen's record
carries its salt's key, and glucose's its hydrate's. Hydroxypropyl-β-cyclodextrin
is a polymer that FDA and ChEMBL draw differently. So identifiers disagreeing
about *form* is not evidence, and a record that cannot be compared is kept. The
rule sets aside **11 links on 6 molecules**, each listed with its record and
reason under `mesh_pharm_actions` in `build_manifest`. They are DMSO, benzocaine
(ambroxol's *Expectorants* via "Flavamed"), progesterone (dacuronium's
*Neuromuscular Nondepolarizing Agents* via "Gestormone"), tafamidis, and two
combination products' actions on phenylbutazone and norethindrone. Tafamidis is
left with no action, because its own record has none.
**787 of 1,335 entries** carry an action: 1,697 links over 303 actions, 356
classes with their ancestors. Of the rest, 212 have no InChIKey (proteins,
antibodies, mixtures), 22 have no PubChem compound, and 314 have a compound
MeSH gives no action. Each writer to these tables replaces only its own sources,
so rerunning the stem backfill cannot wipe the actions, or the reverse.

A fourth source, `mesh_struct`, holds the **MeSH chemical-structure classes**:
where MeSH files a substance by what it is built like, caffeine under
*Xanthines*, brexpiprazole under *Thiophenes* and *Quinolones*. It is written
only by `scripts/resolve_cohort_mesh_structure.py`, and a rebuild wipes it like
the other backfills. It does **not** go through PubChem, and that was measured
rather than assumed. PubChem's list of a compound's MeSH records is matched on
names and registry numbers on its side. For the cohort it included brand names,
drug combinations and wrong compounds: methylprednisolone was listed with
exifone, a benzophenone, and benzocaine with ambroxol. So the route is
identifiers only. The InChIKey goes to FDA's UNII, by exact standard InChIKey
in FDA's own records file (`UNII_Data.zip`, cached in `db/cache/fda/`), and FDA
registers a UNII from the structure. The UNII goes to the one MeSH descriptor or
supplementary record carrying it as a registry number (`desc2026` and
`supp2026`, pinned). A molecule whose UNIIs reach two records is dropped
(invariant 6). A salt or hydrate form's InChIKey is tried only when the parent's
reaches nothing, because MeSH often files a drug under its salt. A descriptor is
in the tree itself, so it is filed under the headings directly above it; a
supplementary record is filed under the headings MeSH maps it to. Only the
structural branches count (D01–D05, D09, D10, D12, D13), from depth 2 down; the
others (hormones, enzymes, biological factors, preparations, actions) file a
substance by function. A drug whose own heading is a class for another entry is
a member of it too: MeSH files ketorolac under *Indomethacin* and pentoxifylline
under *Theobromine*. `carriers` records the chain, e.g.
`CHEMBL113|UNII:3G6A5W338E|MeSH:D002110`. Where both routes give one record they
agree on 277 of 278 molecules.
**967 of 1,335 entries** carry a structure class: 1,397 links over 526 classes,
726 with their ancestors. 586 come through a descriptor, 381 through a
supplementary record, and 23 through a salt or hydrate form. Of the rest, 212
have no InChIKey, 67 have no UNII, 87 have a UNII no MeSH record carries, one is
ambiguous (thiamine) and one sits only in a functional branch.

---

## 2026-09-04 — six things a reader found in the viewer, and one of them was a lie about a receptor

**All six found by looking at the graph, not by a test.** Five were presentation;
one was the panel making a false statement, and it is the reason this entry
exists.

### The false one: an assembly row that opened onto a single protein

Clicking **verapamil** showed a row reading "Voltage-gated calcium channel" that
expanded to **CACNA1C and nothing else**. Verapamil has four calcium-channel
edges — CACNA1C, CACNA1D, CACNA1F, CACNA1S — and the other three were in a
*second* row of the same name further down the panel, under a different
heading. A reader who opened the first row was told a 26-subunit channel
amounts to one protein here; a reader who noticed both rows was told there are
two calcium channels.

**Cause.** `edgeListHTML` split the edge list into the three evidence tiers
first and grouped by assembly *inside each tier*. That is fine while an
assembly's subunit edges are all equally evidenced and wrong the moment they
are not: CACNA1C is corroborated (2 measurements) and the other three are
single-measurement leads, so the assembly was cut in half along the tier
boundary and each half honestly reported the subunits it happened to hold. The
grouping code was never wrong about which targets are one receptor — it was
being asked the question twice, on two disjoint subsets.

**Measured across the current database:** 4 of the 23 molecule-and-assembly
rows were split this way — verapamil and quinidine at the calcium channel,
clozapine at 5-HT3, mibefradil at the calcium channel. After the fix, 0 of 23.

**Fix.** Grouping now happens once, before the tiers see the list
(`displayUnits`), and a grouped row is placed by its **best-evidenced member**
(`unitTier`). That is not a new rule: the canvas already draws a collapsed edge
solid when *any* subunit edge is corroborated (`groupEdgeCorroborated`), so the
panel and the picture now answer "how well evidenced is this receptor" the same
way, which is what invariant 13 asks of any two things that look comparable.

The promotion is stated rather than assumed. A row that spans tiers prints what
it holds — "4 subunits of 26 measured here · 1 corroborated edge, 3 leads" —
because three leads sitting inside a heading that says "Corroborated" is the
right place for them and exactly the kind of thing that must not be silent. The
"of 26" is the other half: a row naming a whole channel and showing four
proteins should say it is showing four.

### The hull that enclosed things it had never heard of

A hull is a convex hull over a force layout, and the physics knows nothing
about assemblies. This was recorded as known-and-not-fixed since the grouping
work: an unrelated target could land inside the enclosure and be visually
claimed by it, mitigated only by keeping the fill faint. Mitigation is not the
property being claimed. The enclosure says "these proteins are one receptor",
and a node that is not a member has no way to argue back.

Fixed in two halves, because one of them is a cause and the other is a
guarantee:

- **Glue springs** (`glueEdges`) — invisible, physics-only edges holding an
  assembly's subunits together, so the layout actually puts one receptor in one
  place instead of leaving a large loose hull with room inside it. 39 springs
  over the 5 assemblies and their 44 subunits. A star per assembly, not a
  clique: the 26-member calcium channel as a clique would be 325 springs and
  would overwhelm every other force on the canvas. This is the fix `CLAUDE.md`
  described and deferred as "worth trying once someone has looked at the
  hulls"; someone has now looked at them.
- **`hullExclusions`** — the guarantee. Any node that is not a member and lands
  in or against the outline is carved out of the drawn region (even-odd fill,
  outline stroked around the gap), so it is visibly not enclosed.

Nodes are deliberately **not moved** to achieve this. `network.moveNode`
restarts vis's simulation, so pushing intruders out fights the physics that
placed them and oscillates; and it would make the layout a function of the
grouping mode, so switching one assembly to "hull" would rearrange the whole
graph. The picture stays the force layout; only what the enclosure *claims* is
corrected.

### Four presentation faults

- **The legend named protein assemblies twice** — the collapsed hexagon under
  "Node shape" and the enclosure under "Enclosure — protein assemblies", which
  read as two unrelated things when they are one feature drawn two ways. One
  block now, with both swatches under it.
- **A selection opened below the controls.** Clicking a molecule put its name
  under a screenful of brain-filter and protein-assembly prose. The controls
  are chrome for the picture, not part of what was selected, so they fold to
  one line that names their current state (`viewOptionsSummary`) and the panel
  starts where the eye already is. What a control is *doing* does not fold:
  `filterBannersHTML` renders outside the disclosure, because the whole
  argument for allowing a filter that removes things is that it states its cost,
  and a cost behind a disclosure is not being stated.
- **The grouping notes and the legend notes moved to hover**, which is where
  the rest of this panel's vocabulary already lives. Same words, still counted
  from the loaded data rather than hardcoded.
- The legend's help boxes open **upward** (`.legend-cat .help-text`), because
  the legend is pinned to the bottom-left corner and the panel's downward box
  would open off the bottom of the window — the same failure that made the tier
  explanations unreachable in August.

**Held to by test.** `tests/viewer.test.mjs` gained 25 tests: the containment
rule on synthetic geometry (a member is never carved out of its own receptor; a
non-member inside is; one just outside still gets clearance; a degenerate
outline carves nothing), the glue springs' shape and when they pull, the
verapamil case end to end, and the legend's one-assemblies-heading and
hover-not-inline properties read out of the markup.

---

## 2026-09-03 — choosing the third fourteen, and what "reach" turned out to mean

The seed set went from 14 molecules to 28. The brief was the same shape as
last time — new molecules must interact with targets already in the network —
but the *reason* had changed. The second cohort's own entry in this log ends
by stating its cost: 90 of the 141 targets were new, most of them the new
molecules' off-targets, and 93 of 141 sat at a single edge. Densifying the
core had not bounded the periphery. So this round was scored on paying that
down: corroborate targets that already exist and have exactly one opinion on
them, while dragging in as few new nodes as possible.

Two things had to change about how candidates were ranked, and both only
became visible by running the old ranking first.

**Ranking on accessions rewards fan-out.** The second-cohort sweep counted, per
candidate, how many of the network's UniProt accessions it reached. Re-run
against the 141 targets, that ranking's top of the list was SULOCTIDIL (36),
TERODILINE (29), PHLOROGLUCINOL (27), GABAPENTIN, ATAGABALIN, IMAGABALIN and
PREGABALIN (26 each). Every one of them scores that way for the same reason:
a single curated mechanism record filed against the voltage-gated calcium
channel *complex*, which maps to 26 subunits — CACNA1A through CACNA1S,
CACNA2D1-4, CACNB1-4, CACNG1-8. Those 26 accessions are in this database at
all only because tacrine's `CHEMBL4613617` fan-out put them there, and the
viewer already collapses that group into one row precisely because it is one
experiment. Seeding gabapentin would have added 26 edges carrying one
assertion, and scored as the best available pick while doing it.

The fix is to count distinct *single-protein* ChEMBL targets: a target that
maps to at most two components. A family or complex target counts once, which
is what it is. Under that rule gabapentin drops out entirely and the ranking
fills with molecules that were actually measured against individual proteins.

This is the second-cohort entry's "a high hit-count is often family
membership, not reach" lesson, except that it had grown teeth. At 51 targets
it cost a ranking position. At 141 — after a fan-out had deposited 26 subunits
into the target set — it had become the dominant signal in the sweep.

**Scoring candidates one at a time double-counts on both sides.** The aminergic
block is the largest group of orphans, and the drugs that cover it are
antipsychotics and tricyclics that overwhelmingly cover *the same* orphans:
haloperidol, chlorpromazine, clozapine, thioridazine and fluphenazine all
reach DRD1/2/3, HRH2, SIGMAR1 and the monoamine transporters. Ranked
individually they look like five wins. They are close to one. The same
symmetry works in the candidate's favour on the cost side: each of those drugs
drags in 30-45 new targets on its own, but the second one's off-targets are
mostly the first one's, so its marginal cost is far lower than its own number.

So selection was run as a greedy set-cover: at each step, score every remaining
candidate by the orphans it adds to those already covered, minus 0.35 per new
target it adds to those already dragged in, and take the best. That number is
a judgement — it says one new unexplained node costs about a third of what one
newly-corroborated node is worth — but any explicit constant is better than
the implicit zero the per-candidate ranking used.

**What the sweep predicted, and what the rebuild did.** Scored against
`chembl_37` alone, the chosen set covered 34 of the 93 single-edge targets and
added 38 new ones. The rebuild covered **50** and added **66**. Both numbers
moved the same way and for the same reason: the sweep can only see ChEMBL,
and five of the six sources are queried live at build time. PDSP in
particular contributes whole receptor panels for these molecules — the
aminergic screen behind haloperidol, clozapine, amitriptyline and, less
obviously, dipyridamole — which is why coverage beat the estimate, and why
the new-target count overshot it by the same mechanism. A ChEMBL-only sweep
is a lower bound on reach and a lower bound on sprawl, not an estimate of
either; it ranks candidates correctly against each other and should not be
read as a forecast.

**Where the greedy was overruled, and why.** Run unrestricted it returns
SOPHORAFLAVANONE G, CORYNANRHEIDINE, ELPETRIGINE, SUVECALTAMIDE and MINAPRINE
— research compounds with good numbers and no recognition value whatsoever in
a graph whose stated purpose is exploratory and educational. The pool was
restricted to `max_phase = 4` (approved drugs) and the final set chosen by
hand from what the scoring surfaced, then re-scored as a set to check the
arithmetic still held. Two picks are deliberately not what the score would
choose: galantamine adds no new targets and covers no orphans at all, and
memantine covers none either.

**What was picked.** Four for the aminergic block — haloperidol (the anchor:
343 qualifying rows, curated D2/5-HT2A, 11 orphans in one molecule),
clozapine (the atypical against haloperidol's typical: same two curated
targets, opposite balance across them), amitriptyline (curated SERT/NET, and
the only bridge found between the aminergic and sodium-channel blocks) and
loperamide (curated mu-opioid agonist — the only route to OPRD1/OPRK1/OPRM1,
plus SIGMAR1, TMEM97 and the hERG liability it is notorious for). Two for the
NMDA receptor — dextromethorphan (curated GRIN2A antagonist and sigma-1
agonist, reaching six orphans while adding *no* new targets, the best ratio in
the sweep) and memantine. Lamotrigine for the sodium channels. Dipyridamole
and vardenafil for the PDE isoforms. Dronabinol for the cannabinoid receptor.
Phenelzine for MAO-A. Quinidine for the CYP2D6/SCN5A/KCNH2 trio. Galantamine
for the cholinesterases. Mibefradil for the T-type calcium channels.

**Two picks are worth their own note.**

*Dipyridamole reverses a decision this log recorded.* The second-cohort entry
excludes it explicitly: all 11 of its hits were a subset of pentoxifylline's
13 PDE targets, so it would have added a fourth opinion on a family already
covered and reached nothing new. That reasoning was correct then and is not
now, because the target set it would join has changed. Sildenafil brought
PDE6A-H, PDE7A, PDE8A, PDE10A and PDE11A into the database as its own
off-targets, one edge each, and dipyridamole's curated mechanism covers them.
Its equilibrative nucleoside transporter (SLC29A1) mechanism matters more: it
raises adenosine by blocking reuptake where every xanthine here blocks the
receptor, which is a second route to the same physiology and exactly the kind
of thing "which molecules act alike" should be able to show is *not* the same
mechanism. An exclusion recorded against a snapshot of the graph is not a
permanent one, and re-running the old sweep unchanged would have kept
honouring a reason that had expired.

*Dipyridamole's PDE corroboration is one assertion, not 22.* Its curated
mechanism is filed against the phosphodiesterase family target, which fans out
to 22 accessions. Those edges are real and enter under invariant 8, but the
panel will show PDE8A as having gone from one opinion to two when the second
is a family-level annotation. This is the same shape as pentoxifylline's
already-seeded 13 and gets the same treatment, but it is a known overstatement
and belongs here rather than in a footnote: mechanism fan-out is not collapsed
anywhere, in the panel or on the canvas, and only assay fan-out is.

**The parent-molecule filter manufactures a phantom duplicate.** The sweep
offered CHEMBL190, "THEOPHYLLINE ANHYDROUS", as a candidate, scoring on
exactly the targets the seeded theophylline already covers — ALPL, PIK3CA,
TMIGD3 and the ADORA family. It looked like the anhydrous/monohydrate pair the
salt filter would miss, since `molecule_hierarchy` links salts and the two
differ by a water: `ZFXYFBGIUFBOJW-UHFFFAOYSA-N` against the seeded
`INQSMEFCAIHTJG-UHFFFAOYSA-N`.

It is not that. CHEMBL190 is the *parent*, and the seeded CHEMBL1355736 is one
of its six children — alongside oxtriphylline, aminophylline, ambuphylline and
theophylline olamine, three of which the last cohort excluded by hand. The
second-cohort entry's remedy for those exclusions was to roll candidates up to
their parent molecule, and that rollup is what put CHEMBL190 on the list: it
attributes the union of every child's data to the parent, including the
seeded molecule's own. The candidate was theophylline, wearing its parent's
name.

Queried directly, CHEMBL190 has no curated mechanism and no qualifying binding
row of its own at any target in this database. Every one of theophylline's ten
curated mechanisms and all 82 of its qualifying binding rows sit on the
monohydrate child that is actually seeded. So the database is not missing
theophylline data, and — worth stating because it is the opposite of the rule
the last entry implies — "seed the parent" would have been the wrong call
here: the parent is an empty record and the data lives on the child.

The rollup is still right for suppressing salts. But it cannot also be used to
score candidates, because a parent's score is its children's data summed, and
one of those children may already be in the graph. Any future sweep needs to
drop candidates whose child set intersects the seed list, which is a check
neither sweep has made.

---

## 2026-09-03 — ADRA1A resolved to the alpha-1D receptor

Found by the third-cohort rebuild, which died on molecule 22 of 28 with
`sqlite3.IntegrityError: UNIQUE constraint failed: targets.uniprot_accession`.

**What happened.** `resolve_uniprot_accession(gene_symbol=...)` asked UniProt
for `gene_exact:ADRA1A AND organism_id:9606 AND reviewed:true` with `size=1`
and returned `results[0]`. That query returns *two* reviewed human entries, and
UniProt ranks them:

    P25100  ADRA1D  Alpha-1D adrenergic receptor      <- returned
    P35348  ADRA1A  Alpha-1A adrenergic receptor

`gene_exact:` matches UniProt's gene **synonyms** as well as its primary gene
name. The receptor originally cloned and published as "alpha-1a" was
reclassified as alpha-1D, and the superseded name survives as a synonym on
P25100 — so the entry for a *different* protein matches the query, and ranks
above the gene actually asked for. Every alpha-1A measurement PDSP reports
would have been filed against the alpha-1D receptor.

**Why the function had a guard against exactly this and it did not fire.** The
same function's `protein_name` branch is the subject of a long docstring
explaining that UniProt's search is relevance-ranked rather than exact, that
taking `result[0]` had already stored LTBR for "Tumor necrosis factor", and
that the fix is to fetch several candidates and accept only one that matches
exactly — invariant 6, "refuse to guess a gene". The `gene_symbol` branch sits
four lines above that docstring and did none of it. The reasoning had been
written down and applied to one of the function's two arguments.

**Why it surfaced now and not before.** The branch is only reached when a
target arrives with no accession attached, which in practice means PDSP or
DGIdb — ChEMBL supplies the accession directly. ADRA1A had never before
entered this database by that route: it was already present from ChEMBL data,
so `target_info["ADRA1A"]["accession"]` was populated and the resolver was
never called for it. Dipyridamole is the first seeded molecule to carry an
alpha-1A number in the PDSP panel and nothing else, and the resolver ran.

**The constraint is what caught it, and only by luck.** The build crashed
because ADRA1D was already in the graph holding P25100, so writing P25100 a
second time violated the UNIQUE constraint on `targets.uniprot_accession`. Had
the seed set not happened to contain a molecule that reaches ADRA1D, there
would have been no error at all: a target row labelled `ADRA1A` would have been
created carrying the alpha-1D protein's accession, name and function summary,
and every alpha-1A measurement would have been attached to it. It would have
rendered as a normal orange diamond, linked out to the wrong Wikipedia article
and the wrong UniProt record, and nothing in the viewer or the tests would have
indicated a problem. An audit of the 14-molecule database found 0 of 141
targets carrying a gene symbol that is not the primary gene name of its stored
accession, so nothing shipped wrong — but that is a fact about which molecules
were seeded, not about the code.

**Fixed.** The gene branch now fetches up to 10 candidates with
`gene_primary`, keeps only those whose own primary gene name equals the symbol
asked for, and returns an accession only when exactly one does — refusing an
ambiguous answer the same way the protein-name branch refuses a merely-related
one. Four unit tests cover it, one of them the literal ADRA1A/ADRA1D ordering
UniProt returns.

`upsert_target` also now checks for the collision itself and raises naming both
genes and the accession, rather than letting sqlite report "UNIQUE constraint
failed" with no indication of which two targets disagreed or why. The
constraint stays exactly as load-bearing as it was; it just says what it
caught.

**Worth keeping in mind.** The general shape — an identifier that is correct
for one record and a superseded alias on another — is the same failure the
Wikipedia resolution entry describes (invariant 15), and the same one the
protein-name search had. It has now appeared three times in this pipeline
through three different lookups. Any query that resolves a name to a record
here should be assumed relevance-ranked and synonym-matching until proven
otherwise, and should verify the answer on the field it asked about.

---

## 2026-08-31 — choosing the second seven

The seed set went from 7 molecules to 14. The brief was specific: the new
molecules had to interact with targets *already in the network*, so the graph
gets denser rather than merely larger. That is a selection problem, and the
honest way to do it is to ask the data rather than to list drugs from memory.

**How the candidates were found.** The first seven produced 51 targets. Every
one of those 51 was mapped to its ChEMBL target ids through
`component_sequences` → `target_components` → `target_dictionary` (restricted
to *Homo sapiens*), and two sweeps were run over the `chembl_37` release:

- every molecule with a curated `drug_mechanism` record against one of the 51;
- every molecule with a qualifying binding measurement against one of the 51 —
  `standard_relation = '='`, type in (Ki, Kd, IC50), units nM, value ≤ 300 µM,
  `assay_type = 'B'`, `confidence_score ≥ 7`. Those filters are the pipeline's
  own rules (invariants 1 and 8) applied at selection time, so a candidate's
  score predicts what it will actually contribute rather than what a looser
  count would promise.

**Three things the sweep showed that a from-memory list would have missed.**

*Salts are separate molecules in ChEMBL, with their own mechanism records.*
The curated-mechanism ranking put AMINOPHYLLINE, OXTRIPHYLLINE and
THEOPHYLLINE SODIUM GLYCINATE in the top five, each with 10 hits among the 51,
and CAFFEINE CITRATE just below with 4. All four reduce to a molecule already
seeded. Adding any of them would have drawn the same edges a second time under
a different name and inflated the apparent corroboration of the ADORA and PDE
clusters — the graph would have looked better supported while containing no
new evidence. They were excluded by hand; the sweep query now filters to
parent molecules via `molecule_hierarchy` where it can, but the general point
is that a high hit-count is not by itself a reason to seed something.

*A high hit-count is often family membership, not reach.* Below the top few,
the ranking fills with molecules scoring exactly 4 — and they are the same 4
every time: either CACNA1C/1D/1F/1S or PDE4A/B/C/D. ChEMBL records some
mechanisms against a protein-family target, which maps to four accessions at
once, so every dihydropyridine and every PDE4 inhibitor ties. Ranking on the
raw number would have picked four interchangeable calcium blockers. What
matters is how many *distinct* families a candidate touches.

*Curated mechanism and measured binding disagree, and both are needed.*
Sildenafil has no curated mechanism against any of the 51 in this release, and
would have been invisible to the mechanism sweep — but it has 81 qualifying
binding rows across 10 of them, including ADORA1 and ADORA2A, which is the
only route from the PDE cluster back to the adenosine receptors. Conversely
rivastigmine's dual ACHE/BCHE mechanism is curated, which under invariant 8
means those edges enter regardless of affinity. Neither sweep alone would have
produced this set.

**What was picked, and why each one.** Pentoxifylline (mechanism at 13 of the
51; a fourth methylxanthine, so the xanthine and PDE clusters join through one
node instead of sitting adjacent), sildenafil (binding at 10, the PDE↔ADORA
route), verapamil (CACNA1C, KCNH2 and ABCB1 — three families that each hung
off a single edge), rivastigmine (curated dual ACHE/BCHE, plus FAAH),
tacrine (340 qualifying rows across ACHE, BCHE, APP and KCNH2 — the most
heavily measured candidate found), selegiline (MAOB, the same
selective-single-target role istradefylline plays at ADORA2A), and cannabidiol
(CNR1, HRH3 and ADRA2C — three brain-expressed targets that were each at one
edge).

**Deliberately not picked: dipyridamole**, despite ranking second overall with
11 hits. Every one of its 11 is a subset of pentoxifylline's 13, so it would
have added corroboration to PDE edges the network already has from rolipram
and cilostazol, and reached nothing new. With a fixed budget of seven, reach
into thin parts of the graph was worth more than a fourth opinion on the PDE
family. Roflumilast and ibudilast were dropped for the same reason.

**Result.** 7 → 14 molecules, 51 → 141 targets, 84 → 244 interactions. All 51
original targets survived the rebuild, and every new molecule connects to
them: pentoxifylline 8 shared targets, sildenafil 15, verapamil 11, tacrine
12, cannabidiol 6, rivastigmine 3, selegiline 2. ACHE went from 2 edges to 6,
KCNH2 and ADRA2C from 1 to 4, BCHE and CYP1A2 from 1 to 3, MAOB from 2 to 3.

**The cost, stated plainly.** 90 of the 141 targets are new, and most of them
are the new molecules' own off-targets, reached by one edge each. Tacrine
alone brought 34, cannabidiol 28, verapamil 21. The brief was to densify
around the existing targets and that happened, but the periphery grew faster
than the core did, and with no filter UI in the viewer (see CLAUDE.md, "Not
done") there is currently no way to hide it. Seeding for shared targets does
not bound what else a molecule drags in — only a display filter would.

**One viewer change fell out of this.** Cannabidiol's CNR1 edge is the first
`NEGATIVE ALLOSTERIC MODULATOR` in the database, and `actionColor` fell back
to `#b98be0` for unknown action types — the exact colour already assigned to
`FUNCTIONAL`. Two different mechanisms would have rendered identically with
nothing in the legend to separate them, which is invariant 13 in its visual
form. Allosteric modulators now have their own colour and the fallback has a
third, listed as "Other mechanism".

---

## 2026-08-30 — five measurements, one paper, five different experiments

Noticed while reading the panel, not by a failing check: rolipram/PDE4D's
functional value is the median of five IC50s that all cite the same paper
(PMID 16263279). The obvious suspicion was a pagination or dedup bug
depositing one measurement five times.

It wasn't. The five are five *different assays* — different ChEMBL assay ids,
different biology:

| Assay | IC50 | What was measured |
|---|---|---|
| CHEMBL854101 | 41 nM | LTE4 release, human whole blood |
| CHEMBL862504 | 3,000 nM | PAF-mediated eosinophil chemotaxis |
| CHEMBL862502 | 6,500 nM | LTB4-mediated eosinophil chemotaxis |
| CHEMBL862505 | 13,000 nM | eotaxin-mediated eosinophil chemotaxis |
| CHEMBL862503 | 17,000 nM | C5a-mediated eosinophil chemotaxis |

Every invariant held. All five are `assay_type=F`, human, `relationship_type=D`,
`confidence_score=9` (direct single-protein assignment to PDE4D), and
`standard_relation="="`. The pipeline did exactly what it should. **ChEMBL's
unit of record is the assay, not the paper**, and one panel-style pharmacology
paper legitimately deposits a whole row of them. Rolipram appears in this
particular paper only because it is the field's reference PDE4 inhibitor: the
paper is about a different compound and uses rolipram as the benchmark. That
is also why it accumulates 19 binding measurements across 19 unrelated
medicinal-chemistry papers.

So this is the recurring lesson again, one level up. Nothing here is a value
that means something other than it says. It is a *count* that means something
other than it says: n=5 reads as five looks at one quantity, and it is one look
each at five quantities. Pooling them gives 6,500 nM, which is not rolipram's
potency at anything — it is the middle of a list of unlike things. Compare the
PDE4D binding median of 190 nM and the PDE4B functional value of 625 nM.

Two things made it invisible rather than merely subtle:

1. **The panel dropped the paper count exactly when it mattered.** The summary
   line only rendered "from N papers" when N > 1, so an edge whose every
   measurement came from one study displayed a bare "5 measurements" — the most
   reassuring possible rendering of the least corroborated case. Now
   unconditional: "5 measurements from 1 paper".
2. **The assay description was fetched and thrown away.** `chembl_local.py`
   has always selected `a.description`, and `build_db.py` printed it to the
   console during a load, but `add_measurement` never carried it and no column
   held it. Now `measurements.assay_description`, rendered under each row, so
   the five lines above explain themselves.

Checked whether this edge is representative: it is not. It is the **only** edge
in the database with three or more counted measurements all from a single
paper. That is not a reason to leave it alone — it is the case that shows what
n does not measure.

Migrated by `ALTER TABLE` plus a backfill joined to the `chembl_37` bulk
release on assay id, rather than `--rebuild`. 374 of 378 measurements are
ChEMBL and all 374 backfilled; the 4 BindingDB rows have no equivalent field
and stay NULL. A rebuild was deliberately avoided: it re-queries five live
sources, and the 2026-08-28 entry below records what that cost last time
(five edges lost to a BindingDB availability blip). Edge, source-link, target
and measurement counts are byte-identical across the migration, and
`n_measurements` still equals the counted rows per role.

**What to take from this:** a per-measurement fact belongs on the measurement
(invariant 14), and "what was actually measured" is one of those facts. Also:
when a summary line can omit a qualifier, check what it looks like in the case
where the qualifier is most damning.

---

## 2026-08-29 — Wikipedia links, resolved by identifier

Not a data-quality failure — a decision recorded before it becomes one.

The viewer now links each molecule and target to its English Wikipedia
article. The obvious implementation is a title search on the name this
database already holds, and it is wrong here: `ATM`, `APP`, `TNF` and `NOTUM`
are English words or abbreviations with unrelated articles, and a search API
returns a confident answer for every one of them. A wrong link on a panel whose
job is to explain what a protein *is* misinforms more directly than no link.

So every lookup is an exact match on an identifier already in the database,
through Wikidata:

- **Molecules** — InChIKey (P235), PubChem CID (P662) or ChEMBL ID (P592). All
  three are tried, because they disagree about *coverage*, not about answers:
  Wikidata's theophylline item carries a different ChEMBL ID from this DB's,
  and P592 alone misses it. Where more than one matched, they agreed — checked
  for all seven seed molecules.
- **Targets** — UniProt accession (P352), then "encoded by" (P702) to the gene
  item. Both hops are needed and neither is redundant: English Wikipedia's
  article hangs off the protein item for ACHE and off the gene item for
  ADORA1, with no rule saying which.

An item resolving to more than one English article is skipped, not picked
from. Result: 7/7 molecules and 48/51 targets. PDE3A, PDE3B and TMIGD3 have no
English article linked from their Wikidata item, and are left NULL — the honest
answer, and the viewer simply omits the link.

Two operational notes. The endpoint 504s on a 51-accession `VALUES` block and
answers 15 at a time in about a second, so lookups are chunked. And
`apply_articles` only ever writes, never clears: `sparql_articles` returns
partial results when the endpoint fails, so a Wikidata outage during a rerun
would otherwise strip every link in the database.

---

## 2026-08-29 — the citation nobody chose

**Found by the same reader, on the fix for the previous entry.** With the
measurement list in place, the caffeine→ACHE edge still read strangely: the
paper listed under *Databases* was also one of the two papers listed under
*Binding affinity*, with nothing saying how the two differed.

They didn't differ. There was no distinction to find.

`interaction_sources` has one row per (source, role). `reduce_measurements`
built its per-source dict with `{row[1]: row[2:] for row in rows}` — plain dict
assignment, so **last write wins**. Rows arrive in ChEMBL `activity_id` order,
which meant the "source's citation" was whichever measurement ChEMBL happened
to deposit last. Reversing the loop would have produced a different citation
with exactly equal justification. Nobody chose it, and nothing recorded that it
was a sample.

Scope, across 133 source links:

| | links | what the citation was |
|---|---|---|
| ChEMBL binding, no curated mechanism | 44 | a sampled measurement paper |
| ChEMBL functional | 36 | a sampled measurement paper |
| BindingDB binding | 4 | a sampled measurement paper |
| ChEMBL binding, curated mechanism | 20 | the drug-level MOA reference — real |
| DGIdb annotation | 29 | DGIdb's own claim reference — real |

So 84 of 133 were arbitrary, and they were arbitrary in the most misleading
possible way: presented beside the measurement list, under its own heading, a
duplicate paper reads as an *independent* reference corroborating the edge. It
was a copy of a row already on the same panel.

The same defect had a second instance nobody had noticed. `data_validity_note`
— ChEMBL's "Outside typical range" flag — is also per-measurement, and was also
stored per (source, role): 13 links carried a flag where the underlying
measurements carried 20, and which 13 depended on iteration order. A quality
flag that silently drops 7 of 20 is worse than none.

**Fixed** by making the rule structural rather than remembered:

- `reduce_measurements` returns per-source entries with the external ref only.
  The citation and the flag are not sampled, because they are no longer there
  to sample.
- `interaction_sources.data_validity_note` is dropped. Flags live on
  `measurements`, beside the value they apply to — all 20 of them.
- A citation may still be stored on a source link, but only with a
  `citation_kind` saying which non-measurement claim it supports: `mechanism`
  (ChEMBL's drug-level MOA reference) or `annotation` (a source asserting the
  edge exists without measuring it). `link_source` raises on a citation with no
  kind, so the sampling path cannot return by accident.
- The viewer lists one row per *database*, not per (source, role) — the old
  list showed three rows under a heading reading "Databases (2)" — and names
  what each contributed, counted from `measurements` rather than asserted. The
  two surviving citation kinds are labelled and carry a line saying what they
  are and are not.
- The measurement list is open by default. While it was collapsed, the sampled
  citation was the only one visible on the panel, which is most of why it
  looked authoritative.

Rebuild after the change: 84 edges, 133 source links, 51 targets and all 378
measurements byte-identical to the previous build. Only the citations moved —
49 links keep one (20 mechanism, 29 annotation), 84 now carry none, and 0
duplicate a measurement of their own edge.

**The lesson, which is not the same as the previous entry's.** That one was
about labelling two quantities so they invite comparison. This one is about
*storage shape*: a table with one row per source cannot hold a per-measurement
fact without silently picking one. It will always compile, always look
populated, and always be arbitrary. If a fact varies per measurement, the
one-row-per-source table is not somewhere to put it — not even "for now".

---

## 2026-08-28 — "n=13" beside "Sources (3)", and the 230 citations nobody could reach

**Found by a reader, not by a test.** Clicking the caffeine→ADORA1 edge showed
a binding affinity with n=4 and a functional value with n=2, and then a Sources
list with two entries. The obvious reading — that n counts sources — is wrong,
and nothing in the panel said otherwise. (The n=4 was the stale published
artifact; the current database has 13. The mismatch is identical either way.)

**What the two numbers actually count.**

- `n_measurements` counts **individual assay measurements** pooled into the
  median. Caffeine/ADORA1's Ki is the log-space median of 13 separate
  determinations, drawn from **12 different papers** published between 2000 and
  2021.
- The Sources list counted **(source, role) pairs** in `interaction_sources`,
  whose primary key is `(interaction_id, source_id, role)`. All 13 ChEMBL
  binding measurements collapsed into one row. One of the remaining entries was
  DGIdb in the `annotation` role, which asserts the edge exists and contributes
  no measurement at all — so it could never corroborate n even in principle.

**The part that was worse than confusing.** The single surviving ChEMBL row
kept one citation. On this edge that citation is not even one of the 12 papers:
because it is a curated primary mechanism, `load_molecule` deliberately
overwrites the assay citation with ChEMBL's drug-level mechanism-of-action
reference (a review). Correct for the *Mechanism* line; wrong sitting directly
under *Binding affinity*, where it read as evidence for the number above it.
The `external_ref` beside it was whichever assay happened to be pooled last.

Across the database: **35 of 84 edges have n > 1**, and roughly **230 of the
~290 citations** behind pooled values had no representation in the viewer.

**Why labelling alone wasn't enough.** Renaming the heading would have
explained the gap without closing it. `n_measurements` is this project's
central trust signal — invariant 7, the thing that decides whether an edge
draws solid or dashed — and a trust signal whose evidence cannot be inspected
is a weak one. It was, in effect, an assertion.

**What changed.** New `measurements` table: one row per individual measurement,
with its own value, assay id, paper and validity flag, plus a `counted` flag.
Deliberately not deduplicated and with no UNIQUE constraint — two identical
values from two different assays are two measurements (caffeine/ADORA1 has
exactly this: 44,900 nM from both CHEMBL3096082 and CHEMBL3096091). The
enforced invariant is:

```
COUNT(*) FROM measurements WHERE counted = 1 AND role = ?  ==  n_measurements
```

asserted per edge per role in the test suite, and verified across the whole
database after the rebuild: **0 mismatches** on both roles, 378 rows, 374
counted, 142 distinct papers.

Each measurement keeps *its own* citation, taken from the unreduced rows before
the mechanism-citation override runs — so the review still appears under
Mechanism, and the 12 primary studies now appear under Binding affinity.

BindingDB rows excluded from n (4 of them) are **stored, flagged uncounted, and
shown with the reason**, rather than omitted. Silently dropping them would have
traded one invisible fact for another.

**Viewer.** Values now read "Ki = 44,900 nM — median of 13 measurements" with an
expandable list beneath: every measurement, sorted by value so the spread is
visible, each with its assay id and paper. The provenance heading is now
**Databases**, counts distinct databases rather than (source, role) pairs, and
carries a one-line hint saying it is not the measurement count. The word
"sources" is deliberately avoided in the measurement list — "12 papers", not
"12 sources" — since "source" means database everywhere else in that panel.

**The general lesson, which is new to this log.** Every prior entry is about a
value that was *stored* wrong. This one was stored correctly and *presented*
wrong: two honest numbers, adjacent, counting different things, with no label
saying so. A reader who trusted the panel would have concluded the database was
internally inconsistent. Worth stating as its own invariant (13), because no
data-integrity check would ever have caught it — only someone reading the page.

## 2026-08-28 — ChEMBL moved offline, onto the bulk release

**Why.** Two rebuilds aborted in one week on EBI's side: read timeouts on
2026-08-25 and HTTP 500s on `target/CHEMBL291` on 2026-08-26 (both logged
below). Neither was a bug here, and neither was fixable here. A full rebuild
took ~45 minutes, essentially all of it network wait, which made every data
question expensive to ask and made the database's contents partly a function
of which sources happened to be up that afternoon.

ChEMBL publishes the whole database as a bulk SQLite release. `chembl_37`
(released 2026-05-29, prepared 2026-05-01) is 5.4GB compressed, 29GB
extracted, and now lives at `/mnt/data/chembl/`. SHA-256 verified against
EBI's `checksums.txt`, `PRAGMA quick_check` clean, and all six table counts
match the published release notes exactly (24,527,044 activities; 1,970,438
assays; 18,552 targets; 101,100 documents; 2,921,148 compounds; 7,561
mechanisms).

**What changed.** `scripts/chembl_local.py` answers the same five questions
`build_db.py` asked the REST API — binding activities, functional activities,
target, mechanisms, document — from that file. The five `fetch_chembl_*`
functions dispatch to it when a backend is installed and fall back to HTTP
when one is not. `--chembl-source {auto,local,api}` selects; `auto` is the
default and prefers local.

Only ChEMBL moved. UniProt, PubChem, DGIdb, BindingDB and PDSP still go over
the network — a handful of requests per molecule, and never the failure point.
So a rebuild still needs a connection; it just no longer needs *ChEMBL* to be
up, which is where both aborts came from.

**The constraint that made this safe.** Every function returns the same dict
shape the REST endpoint does, so `load_molecule` cannot tell the backends
apart. That is not tidiness — it is what makes an API-vs-local diff a
regression test rather than a shape mismatch. Rebuilt against `chembl_37` and
diffed all three tables against the API-built database from 2026-08-26:

| | API | local | identical |
|---|---|---|---|
| interaction edges | 84 | 84 | 84 |
| source links | 133 | 133 | 133 |
| targets | 51 | 51 | 51 |

`viz/graph.data.js` came out byte-identical to the committed copy. Runtime:
**45 minutes → 76 seconds**, of which ~4s is CPU and the rest is the five
remaining network sources.

**The one real disagreement, and what it exposed.** The first diff had four
rows differing — theophylline's four ADORA edges cited PubMed 3588607 where
the API cited 12954362. Same mechanism, same assay, different paper.

The cause is a latent ambiguity in `chembl_mechanism_citation`, not in either
backend: it picks a reference with `min()` keyed on `ref_type` priority alone,
so every PubMed reference on a mechanism ties and *iteration order silently
decides which paper gets cited*. The REST API returns `mechanism_refs` sorted
by `(ref_type, ref_id)` as **strings**, which puts `"12954362"` before
`"3588607"`; ordering by `mecref_id` — the obvious choice — reverses them.
Verified against the live API for CHEMBL113, CHEMBL799 and CHEMBL1355736, and
`chembl_local` now sorts to match.

Worth stating plainly: this was never wrong in a scientific sense. All four
are real references for a real curated mechanism. But it is the same shape as
the recurring lesson at the top of this file — a value that parses cleanly,
stores cleanly, and is not the value the other path produces. A 133-row diff
found it in seconds; no amount of reading either implementation would have.

**Provenance.** `sources.source_release` (new column) records which snapshot
backed a build — `chembl_37` for a local run, NULL for a live one, where
`accessed_date` is the only version information that exists. `base_url` stays
the public API even on a local build: it is what a reader should follow.
`get_or_create_source` now updates `accessed_date` and `source_release` on
rerun instead of leaving them at their first-insert values, which had made
`accessed_date` quietly meaningless on an incrementally-updated database.

**Tradeoffs accepted.** The release is a snapshot: corrections EBI makes
between releases (roughly every 4–6 months) will not appear until the next one
is downloaded, and `--chembl-source api` exists for checking a specific record
against live data. 29GB of disk. And a rebuild is now fast enough that the
temptation is to treat rebuilding as free — it is not, for the five sources
still queried live.

## 2026-08-25 — ChEMBL fetches were reading only the first page

**The bug.** `fetch_chembl_binding_activities` and
`fetch_chembl_functional_activities` passed a hardcoded `limit=100` and never
followed `page_meta.next`. ChEMBL's default ordering is by internal activity
id — unrelated to affinity, recency or relevance — so the pipeline was pooling
an arbitrary prefix of each result set and treating it as the whole.

**Measured impact**, against the live API before the fix:

| query | records available | usable in first 100 | usable in full set |
|---|---|---|---|
| caffeine Ki (`assay_type=B`) | 156 | 18 | 61 |
| donepezil IC50 | 332 | 96 | 280 |
| rolipram IC50 | 244 | 76 | 190 |

("Usable" = `standard_relation="="`, units nM.)

This corrupted `n_measurements`, which is this project's core
corroborated-vs-lead signal and is rendered directly in the viewer.
Caffeine/ADORA3 was stored as `Ki=13,300 nM, n=1` and displayed as *"Single-source
lead — not yet corroborated"* when ChEMBL alone held 8 usable Ki measurements
for that pair. Caffeine/ADORA1 was stored at `n=4` against 13 available.

It also dropped whole targets. Six of donepezil's fifteen ChEMBL IC50 targets
fell outside the first 100 records, all under the auto-discovery cutoff and so
all eligible for the database: PDE5A (11 nM), CHRNE (32 nM), FAAH (5,250 nM),
MARK4 (5,300 nM), PDE4D (36,000 nM), APP (87,410 nM). Four of those
(PDE5A, FAAH, MARK4, APP) were nonetheless *in* the database — as
BindingDB-only, single-measurement leads. They were uncorroborated only
because ChEMBL's own record for each sat on page two.

**Fix.** `get_json_paginated` follows `page_meta.next` at `limit=1000`, bounded
by `CHEMBL_MAX_PAGES` against a malformed `page_meta`.

**Consequence to watch for.** Pagination re-admits records that the truncation
had been accidentally hiding — including bad ones. See the CHRNE entry below.

## 2026-08-25 — ChEMBL outage during the re-baseline

The rebuild following the pagination fix aborted twice partway through, both
times on ChEMBL. Diagnosed as an upstream outage, not a change in this
pipeline: a static known-good lookup (`target/CHEMBL226`) returned 500 or timed
out on six consecutive attempts, and `/status.json` itself failed roughly one
request in three. Same shape as the 7.5-hour outage a week earlier.

Two changes came out of it, neither data-affecting:

- **Page size 1000 → 250.** A full-size ChEMBL activity page takes ~4s to
  serve against ~1s for 250 or 500, which made every request four times as
  exposed to a slow response. More, smaller requests are faster in aggregate.
- **Retries made patient**: 6 attempts, exponential backoff capped at 30s, 60s
  read timeout. Plus a fast path — a 4xx other than 429 is a definitive answer
  (PubChem returns 404 for a compound with no CAS numbers) and is no longer
  retried, which was costing ~20s per lookup.

A hard failure on a primary fetch still aborts the run rather than writing a
partial molecule, which is the correct behaviour: this project's whole problem
is under-counted measurements, so a silently short fetch is worse than no
fetch. `reset_molecule` makes an interrupted run cost nothing but time.

## 2026-08-25 — the AChE/CHRNE mislink also exists on the ChEMBL path

The donepezil hit filed under "Acetylcholine receptor subunit epsilon" whose
assay description reads *"Inhibition of human AChE by Ellman's method"* — already
excluded on the BindingDB side (monomerid 8960) — turns out to come the same
way from ChEMBL directly: assay `CHEMBL5133661` linked to target `CHEMBL2484`,
which ChEMBL itself resolves to CHRNE (Q04844). That confirms the error
originates **above** BindingDB rather than in its republication.

`BINDINGDB_TARGET_LINK_EXCLUSIONS` is keyed by `(monomerid, target_name)`, so
it could never have caught the ChEMBL-sourced copy. A matching
`CHEMBL_ASSAY_LINK_EXCLUSIONS` entry was added in the same change as
pagination — without it, fixing pagination would have re-admitted a known-bad
record.

All four of donepezil's activities against `CHEMBL2484` are AChE assays by
description; the other three report unitless `% Inhibition` and are dropped by
the nM units filter regardless, so the IC50 record is the only one that could
reach the database.

**Generalisation worth keeping:** an exclusion keyed to how *one* source
identifies a record does not protect the other paths the same upstream record
travels. Both known mislinkings now have a regression test asserting they stay
excluded on every path.

## 2026-08-25 — reruns could not remove data

`upsert_interaction` used `COALESCE(excluded.x, x)` on every column, and
nothing ever deleted a row. Two consequences:

1. **A correction that removes a measurement couldn't propagate.** When the
   `standard_relation="="` filter invalidated ~16 stored binding values, a
   rerun on an existing database would have kept every one of them: the new
   run produces NULL, and `COALESCE` keeps the old number.
2. **An edge that changed `action_type` would duplicate.** `action_type` is
   part of `interactions`' UNIQUE key, so a gene stored as `BINDER` that later
   gained a curated ChEMBL mechanism would be INSERTed as a second
   `ANTAGONIST` row while the stale `BINDER` row lived on — parallel duplicate
   edges in the graph.

Neither had bitten yet only because the database had been rebuilt by hand
(`rm db/subnetwork.db`), which was undocumented and easy to forget.

**Fix.** `reset_molecule` drops a molecule's edges and source links before
reloading it, so each run reflects what the sources report *now*; the upsert
assigns plainly rather than coalescing; `prune_orphan_targets` clears targets
left unreferenced at the end of a run; and `--rebuild` discards the whole
database for a clean re-baseline. `check_schema` refuses to run against a
database predating the current columns instead of failing later with "no such
column".

## 2026-08-25 — one row per source discarded functional provenance

`interaction_sources` was keyed `(interaction_id, source_id)`, but ChEMBL
routinely backs the same edge twice — once with a binding assay, once with a
functional one — and those are different records with different citations. The
write loop merged both dicts (`{**functional_sources, **contributing_sources}`),
so binding silently won and the functional assay ID was discarded on all 16
edges carrying both.

**Fix.** A `role` column (`binding` / `functional` / `annotation`) joins the
primary key. The viewer labels each citation with its role, so it's clear which
number a given link is actually behind. The curated-mechanism citation now also
falls back to the functional row, which previously meant a curated gene whose
only ChEMBL data was functional lost its drug-level citation entirely.

## 2026-08-25 — correction to an earlier entry in this log

An earlier entry claimed that after the `resolve_uniprot_accession` fix, the
generic BindingDB target string `"cGMP-specific 3',5'-cyclic phosphodiesterase"`
"correctly resolves to nothing", with PDE5A entering only via a more specific
string. **That is wrong.** That string *is* UniProt's own recommended full name
for O76074, so the exact-match check accepts it — and the database shows it:
target `PDE5A / "cGMP-specific 3',5'-cyclic phosphodiesterase" / O76074`.

The outcome is correct (PDE5A is the right gene, and the old code's guess of
PDE9A was not), but the stated mechanism was not. Recorded rather than quietly
edited: in a project whose value rests on provenance, a wrong explanation of
why a value is trustworthy is its own kind of bad data.

The TNF and APP halves of that fix did hold — TNF resolves to P01375, not
LTBR.

## 2026-08-18 — censored values stored as measurements

`standard_relation` distinguishes a measured value (`"="`) from a censored
bound (`">"`, meaning no activity detected up to the highest concentration
tested). The pipeline ignored it.

Surfaced while expanding ChEMBL fetching to let functional assays discover new
targets: that first attempt added 140 FUNCTIONAL edges, of which **118 (84%)**
shared two suspiciously round values (30,000 nM / 10,000 nM) almost entirely
from one secondary-pharmacology safety panel (PMID 37468498) that screens many
drugs against ~30 receptors at fixed concentrations. Caffeine's own stored
ADRA1A record read `relation=">"`, `value=30000`, with ChEMBL's
`activity_comment` spelling it out: *"largest value for measurements with
relation sign '>'"*.

Checking backwards showed this was not new: **16 of 65 (25%)** of the
database's existing ChEMBL-sourced binding values had the same problem, present
since the first commit, across caffeine / theophylline / theobromine /
istradefylline / rolipram.

**Fix.** Both processing loops require `standard_relation == "="`. FUNCTIONAL
edges dropped 140 → 20; all 20 pre-existing curated primary mechanisms survived
unchanged, confirming the filter removed only censored data. The same check
already existed for BindingDB (`raw.startswith(">")`) and PDSP
(`ki Note == ">"`); ChEMBL was the gap.

## 2026-08-18 — BindingDB was inflating the corroboration count

Following a new BindingDB compound link for caffeine/SIRT3 led to a page
reading "Curated by ChEMBL" and citing PubMed 38261767 — the exact record
already stored from this pipeline's own direct ChEMBL fetch. One measurement
(Kd=690 nM), counted twice, because it appears in two databases both queried
here.

Tallying every target row across all 9 BindingDB compound pages this database
pools from: **307/338 (91%) "Curated by ChEMBL", 20/338 (6%) "Curated by PDSP
Ki Database"** — 97% of what BindingDB's compound search returns for these
molecules is republished from a source already queried directly.

**Fix.** `reduce_measurements` excludes BindingDB rows from the pooled median
and `n_measurements` whenever a non-BindingDB row exists for that affinity
type. BindingDB remains a listed source (for its citation link) and remains
how several targets — SIRT3, NOTUM, KCNH2 — entered the database at all.
Confirmed: caffeine/SIRT3 dropped 2 → 1; theophylline/ADORA1 stayed at 13 from
genuinely independent ChEMBL/PDSP measurements. ~35 interactions had an
inflated count before the fix.

**Unresolved.** Whether BindingDB's remaining ~3% (no curator tag detected)
contains genuinely independent measurements is unconfirmed. Scraping
BindingDB's HTML per hit to check was considered and rejected as
disproportionate.

## 2026-08-18 — UniProt protein-name search returned the wrong gene

`resolve_uniprot_accession(protein_name=...)` took `results[0]` from
`protein_name:"..."`, which is relevance-ranked full-text search, not
exact-match. Two wrong genes were being stored:

- **"Tumor necrosis factor"** (a rolipram hit) ranked LTBR *"Tumor necrosis
  factor receptor superfamily member 3"* above the literal exact match, TNF
  (P01375). The underlying assay was *"Inhibition of LPS-induced TNF-alpha
  production in human MNC suspension"* — a cellular cytokine-release assay,
  nothing to do with LTBR.
- **"Amyloid-beta precursor protein"** (a donepezil hit) didn't return APP
  (P05067) in the top 3 at all, surfacing APPBP2/APBB1/APBB2 instead. The
  underlying assay was an amyloid-beta self-aggregation inhibition assay.

**Fix.** Fetch several candidates; accept only one whose own UniProt
recommended name matches the query exactly (case/whitespace-insensitive);
return None otherwise. **A wrong gene is worse than a missing one.**

## 2026-08-18 — ChEMBL curation error: PLAP filed as PLAA

Assay `CHEMBL1074487` (theophylline vs `CHEMBL6114`) is text-described as
*"Inhibition of PLAP"* (placental alkaline phosphatase, gene ALPP) but linked
to a target ChEMBL itself names *"Phospholipase A-2-activating protein"* (gene
PLAA) — unrelated. Confirmed isolated by checking its two sibling assays in the
same series (`CHEMBL1074488` → ALPL, `CHEMBL1074489` → ALPI), both correctly
linked.

Excluded via `CHEMBL_ASSAY_LINK_EXCLUSIONS` rather than silently trusted. Worth
re-checking if fixed upstream — and worth treating as the reminder that the
primary, most-trusted source needs spot-checking too, not just the
supplementary ones.

## 2026-08-18 — the ADORA-only filter was dropping curated data

ChEMBL's binding-activity fetch was hardcoded to accept only `ADORA*` genes,
silently discarding curated mechanism data — theophylline's real ChEMBL "PDE4
inhibitor" records never made it in. Removing the filter also surfaced its
curated PDE3A/PDE3B records, which ChEMBL only has IC50 data for (300,000 nM),
previously dropped because the pipeline fetched Ki only.

Widening to Ki + Kd + IC50 restricted to `assay_type=B` was verified not to gut
existing coverage first: 96/100 of theophylline's Ki activities were already
`assay_type=B`.

## 2026-08-18 — citations added

A value with no way to check where it came from isn't worth much more than the
value itself. `interaction_sources` gained `citation_url`, `citation_text` and
`data_validity_note`:

- **ChEMBL** — `document_chembl_id` resolved once per unique document (cached
  across the run) for a PubMed ID or DOI, preferring PubMed → DOI → ChEMBL's own
  document report card. Curated *mechanism* edges cite the drug-level reference
  from `mechanism_refs` (FDA label, PubMed) rather than whichever raw assay
  happened to be pooled last into the median.
- **DGIdb** — `interactionClaims[].publications[]` for a real PMID; falls back
  to naming the curating databases.
- **BindingDB** — `getTargetByCompound` exposes no reference field at all, so
  edges were initially left uncited. Later linked to BindingDB's real, stable
  compound page (`MolStructure.jsp?monomerid=<id>`, distinct from the flaky
  REST endpoint), confirmed against monomerid 10849 → caffeine.
- **PDSP** — the bulk CSV's free-text `Reference` column (e.g. "HOYER, 1988");
  no link exists, it's a flat file.

`link_source` was changed from `INSERT OR IGNORE` to an upsert at the same
time, which would otherwise have left the new citation columns permanently NULL
on every pre-existing interaction.

## 2026-08-17 — the affinity cutoff was too tight (theobromine)

Theobromine loaded with **zero interactions** despite being seeded to sit
alongside caffeine and theophylline. ChEMBL has no curated *mechanism* record
for it (never developed as a drug, so never got a curator's write-up), and none
of its raw binding measurements (105,000–250,000 nM at ADORA1/2A/2B/3 + PDE4)
cleared the then-30,000 nM `MAX_SUPPLEMENTARY_AFFINITY_NM` auto-discovery
cutoff, which only bypasses for genes with a curated mechanism.

Traced the raw data to a real, focused literature review (Faudone/Arifi/Merk,
*The Medicinal Chemistry of Caffeine*, J Med Chem 2021, PMID 34019396) rather
than an HTS artifact, so the cutoff was raised to 300,000 nM — just above that
paper's weakest value, and an order of magnitude already trusted elsewhere in
the database (theophylline's curated PDE3A/3B IC50s are 300,000 nM). Three of
those five values carry ChEMBL's own `data_validity_comment="Outside typical
range"`; not excluded for it, but surfaced.

The cutoff is a **noise filter for auto-discovery only**, not a claim about
biological relevance — caffeine's own curated ADORA3 mechanism is Ki=100 µM,
far above it. Genes with a curated mechanism bypass it entirely.

## 2026-08-17/18 — ChEMBL REST API outage

ChEMBL's entire REST API returned HTTP 500 / hung for roughly 7.5 hours
(2026-08-17 evening into 2026-08-18 morning). Confirmed a full outage, not a
bad query: a static known-good lookup (`molecule/CHEMBL113.json`) and the API's
own `/status.json` health check both failed identically throughout.

`build_db.py` was left polling for recovery. No partial writes occurred — each
molecule only commits at the end of its own load. ChEMBL IDs for the five
molecules added that day were cross-referenced via PubChem's `/synonyms`
endpoint instead of ChEMBL's `molecule/search`.

## Ongoing — BindingDB's compound-search endpoint

`getTargetByCompound` returns HTTP 200 with `Content-Length: 0` for every real
compound query (caffeine, aspirin, ibuprofen, any similarity cutoff), straight
from their origin server — not a proxy swallowing it. BindingDB's own
documented example call returns valid JSON only for its trivial zero-hit
compound.

Independently corroborated by Harvard's Zitnik Lab ToolUniverse project, whose
`bindingdb_tool.py` notes: *"BindingDB's singular-form REST endpoints
(`getLigandsByUniprot`, `getLigandsByPDB`, `getTargetByCompound`) hang
indefinitely as of 2026."* Their workaround — switch to the plural
`getLigandsByUniprots` / `getLigandsByPDBs` — doesn't apply:
`getTargetByCompound` has no documented plural sibling.

Handled non-fatally per molecule rather than aborting the run, since BindingDB
is nobody's primary source here.

Separately: BindingDB's compound search matches on the literal input SMILES
encoding rather than a canonicalized structure, so it may miss ligand records
for a compound with multiple differently-encoded entries. Accepted, for the
same reason.

## Design decisions worth not relitigating

**Functional potency is never blended into `binding_value`.** Receptor reserve
and signal amplification can shift a functional EC50 relative to a binding
affinity; they are not the same physical quantity, so they get separate columns
and separate medians.

**In-vivo data structurally cannot be mapped here.** ChEMBL's whole-organism
assays report a phenotypic outcome (e.g. urine output in a dosed rat) without
attributing it to a molecular target — `target_pref_name` for those rows is
literally the species name, not a gene. Excluded via
`bao_label != "organism-based format"`. Note this leaves a real dimension
unaddressed: whether a compound reaches a target at achievable concentrations
in a living organism (BBB penetration, plasma levels) is distinct from both
binding and functional values. The closest proxy in the schema is
`expressed_in_brain`, which answers "is the target present in the tissue" and
not "does the compound reach it".

**Functional data never auto-discovers a target on its own** unless no
binding-type data exists at all for that gene — same reasoning as the
affinity-cutoff/curated-mechanism split.

**`action_type` uses explicit sentinels, never NULL.** It's part of
`interactions`' UNIQUE key, and SQLite never treats NULL as equal to itself
there, so a NULL would break upsert idempotency. `BINDER` = raw affinity with no
curated mechanism; `FUNCTIONAL` = functional activity with no binding
measurement at all.

**A cell-free assay can still be `assay_type=F`.** Theophylline's PDE3A/4A/4D
functional values come from cell-free TR-FRET/scintillation inhibition assays
that ChEMBL classifies as functional despite "cell-free" in the description —
an assay-type/format labelling quirk, not an error to correct.

---

## 2026-09-13 — Cohort 1: what changed about how a value gets in

The clinical cohort was implemented against the policy in
[COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md); the measured results are in
[COHORT-1-IMPLEMENTATION.md](COHORT-1-IMPLEMENTATION.md). Everything above this
line still describes the six-source seed pipeline, which is unchanged and still
builds `db/subnetwork.db`. This entry records only what is different about
admitting a value in the cohort pipeline, and why.

### Two defects found in the analysis this pipeline was derived from

The production code reuses the validated logic in `analysis/cohort1/`. Two of
its rules did not survive being read again, and both would have been silently
wrong in exactly the shape the recurring lesson above describes: data that
parses cleanly and does not mean what the rule assumed.

**The organism-format gate ran only on functional assays.** The analysis
excluded whole-organism readouts with
`assay_type == "F" and bao_label == "organism-based format"`. ChEMBL 37 also
holds **1,632 organism-format assays typed `B`**, carrying **34,791 activity
rows**, and those went through the gate untouched and were treated as binding
evidence. Checked directly against the release:

```sql
SELECT a.assay_type, COUNT(*) FROM assays a
  JOIN bioassay_ontology bao ON bao.bao_id = a.bao_format
 WHERE bao.label = 'organism-based format' GROUP BY 1;
-- F 451666 | A 189827 | T 49384 | B 1632 | U 425 | P 9
```

A whole-organism readout is not a binding measurement whatever ChEMBL types the
assay, so the production gate runs on every assay type. In this catalogue that
is 13,144 functional rows and **40 binding rows** the analysis rule would have
admitted. The gate is applied *after* the scope gates so the figure stays
comparable with the report's 21,999.

**The direct-assignment test skipped two of its own conditions.** The report's
`specificity()` reads:

```python
if (target_type == "SINGLE PROTEIN" and human and conf == 9 and rel == "D"):
    return "human_direct_single_protein" if variant_id is None else ...
if target_type in ("PROTEIN COMPLEX", "PROTEIN COMPLEX GROUP") and human and conf == 7:
    return "human_direct_complex"                      # no D, no variant test
if human and (target_type == "PROTEIN FAMILY" or conf == 5):
    return "human_family_or_multiple"                  # no D, no variant test
```

The `relationship_type = 'D'` and `variant_id IS NULL` requirements are applied
only to the single-protein branch. Measured against the release, the complex
branch would have accepted **109** human confidence-7 `PROTEIN COMPLEX` assays
that carry a variant, and the family branch **11** variant-carrying
`PROTEIN FAMILY` assays, as direct no-variant human evidence. A variant result
is not a wild-type direct-binding assertion, and that is the whole reason the
test exists on the first branch.

The same `conf == 5` clause also admits target types that are not proteins in
the sense the policy means: **9,740** `PROTEIN-PROTEIN INTERACTION` assays,
**1,129** `SELECTIVITY GROUP` and **2,827** confidence-5 `PROTEIN COMPLEX GROUP`.
D06 names four target identities and none of those is among them.

Production applies the full target-type/confidence/relationship/variant
combination to all three classes, and restricts claimable targets to the four
adopted identities. Everything else is retained as an observation with its
reason and produces no edge.

**A third, smaller one:** the report's `study_key()` tested for a PubMed id
before it tested `doc_type`, so a PATENT document carrying a PubMed id came
back labelled a deposited dataset. Production classifies `doc_type` first.

### The report's own prose was wrong about Neuralgia

`COHORT-REPORT.md` argues that the peripheral-nerve exclusion is safe because
Neuralgia (`D009437`) keeps an in-core placement at `C10.597.617.470`. The
saved classification the report itself produced says otherwise: its C10
placement is `C10.668.829.600`, inside the excluded branch, and `in_core_scope`
is 0. The boundary review caught this and is correct.

It matters because it is the difference between a scope that delivers what was
asked for and one that looks like it does. Adding the Pain tree recovers
Neuralgia, postherpetic neuralgia and pudendal neuralgia — but **not**
trigeminal neuralgia, facial neuralgia or fibromyalgia, none of which carries a
Pain-tree placement at all. The adopted scope therefore carries an explicit
inclusion set that overrides the boundary exclusions, and a test asserts all six
descriptors named in D02 land in scope. The set is an audited starting point,
not a claim that the complete neuropathic scope is mapped.

### Rules that changed, and what each replaced

**Trust is counted in distinct studies, not measurements.** Twenty rows from one
paper are one study, and a bulk deposit is one study however many rows it
carries — the Sanger GDSC deposit alone is 19,041 measurements and one study.
The measurement count survives as an accounting fact that must reconcile to the
rows stored against it, which a build check asserts across the whole database.

**Replication is counted inside one endpoint class.** Two papers that measured
different things are not a replication of either. This is invariant 3 ("never
mix affinity types in one median") applied to the trust rule rather than to the
number.

**Potency stopped gating import.** The 300 µM cutoff decided what reached the
database, and a display control cannot undo an import cutoff. Every eligible
measurement is stored and the filter operates over complete data. The reason
the cutoff existed is unchanged: caffeine's curated ADORA3 mechanism at
Ki = 100 µM is still in the catalogue at every threshold.

**Bounds are retained with their relations and counted.** `>`, `<`, `>=`, `<=`,
`>>` and `~` are six different statements, none of them a value. 51,036 of them
are kept, shown, and excluded from every median, threshold pass and replication
count. A bounds-only claim never becomes a default Supported edge, and none of
them is labelled "no activity".

**Mass conversions are computed and marked conditional.** The conversion uses
the **measured** record's own molecular weight, never the parent freebase — a
salt and its parent give different answers. Even the right source weight does
not establish whether the publication expressed mass as salt, freebase, hydrate
or formulation, so all 1,727 results stay out of tiers, medians and threshold
passes until that is verified. A build check asserts that none of them is
counted. Missing or ambiguous identity produces an explicit unresolved result
rather than a guess, and small-molecule mass rules are never applied to
biologics or unresolved structures.

**Deferred sources are "not assessed", not "no evidence".** PDSP, BindingDB,
DGIdb, GtoPdb, HPA, the Chemical Probes Portal and the BBB datasets are not
read by this build, and `source_coverage` records that as its own status. Their
previously collected records remain in the legacy database with full
provenance. Some seed edges that existed before are gone or weaker under
uniform ChEMBL-only treatment; that is the adopted policy, not data loss.

**A target is a ChEMBL target record, not a gene.** The legacy `targets` table
keyed on a unique gene symbol and UniProt accession, which cannot represent a
protein family or complex group at all. A family claim stays a family claim:
expanding the 477 curated family and complex claims to their components would
have produced 3,146 claims, inventing 2,669 "supported" statements about
individual proteins that nothing measured. Components are stored as context so
a complex can name what it contains, and are never read as claims about those
proteins.

**An unassigned observation never becomes a protein edge.** Confidence ≤ 3,
relationship types N/S/M/U, and target types outside the four adopted
identities all produce a retained observation with its reason and no claim, in
every basis and every filter state. 1,144 cell lines, 80 organisms and 41
tissues appear in the release as assay targets for these molecules; none of
them is a target here.
