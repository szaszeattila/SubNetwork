# D23's three gaps, measured, and what would close each

D23 ([COHORT-2.md](COHORT-2.md)) took back an Approved that rests only on US
labels FDA lists as marketed without approval. It named three things it did
not check: 35 label-backed records it could not read, an Approved read off a
WHO ATC class alone (293 in-scope records), and one read off a Phase 4 trial
alone (115). The user asked for those to be interrogated and for a solution to
each. This is that: what each gap actually is, measured against the active
build (2026-10-15, selection policy 3.1.0) and the committed
`config/cohort1_label_status.json`, and a proposal for each.

The short version: the first gap is mostly a parser defect, the third is
mostly a wrong assumption about what ChEMBL cites, and only the second needs a
source this project does not yet read.

## What was adopted (D24, 2026-10-16)

The user annotated this document and the result is decision D24 in
[COHORT-2.md](COHORT-2.md), which has the numbers as built. In brief:

| proposal | the user's word | outcome |
|---|---|---|
| gap 1, rules 1-4 | "adopt these 4 proposals" | built: `found` by set id, RxNav, fda.gov as FDA, the approval-year guard |
| gap 3, rules 1-2 | "adopt 1 and 2 only, not 3" | built: registry phase for trial-only records, the hover corrected |
| gap 3, rule 3 | not adopted | the trial's condition and country are not checked |
| gap 2, rule 1 | "if it was withdrawn worldwide, it should say so" | built: "Approved, withdrawn worldwide (1984)"; elsewhere "Approved; withdrawn in France, 1990" |
| gap 2, rule 2 | "install postgreSQL and RDKit and implement this" | built: `scripts/resolve_cohort_drugcentral.py`; 139 of 228 ATC-only diseases now name a regulator, 8 of the 80 no-US-trace molecules |
| gap 2, rule 3 | "measure this" | measured: 49 of 230 confirmed on-label, a floor; not adopted |
| gap 2, rule 4 | "implement this as well" | recorded in D24 as rejected sources, read as adopting the rejections: each fails invariant 15 or names no approval |
| gap 2, rule 5 | "sure but lets put finding regulators … as a possible action item in the future" | built: the wording; the action item is COHORT-2's **Open** 10 |

Two of the measurements below changed when built: RxNav holds 134 labels
DailyMed no longer serves, not one, because the count here was only of the 35
unresolved records; and gap 3's rule moves two in-scope diseases, not three,
as the table below says it would, since lithium's depression stays Approved on
the Lithane label.

## Records and diseases

The three counts are `drug_indication` records. The page folds every record of
one disease onto one row and names every basis on the hover, so what a reader
sees is the disease. Of the **1,101 in-scope diseases reading Approved**:

| what the best record rests on | diseases |
|---|---|
| a regulator document, an approved US label or an OTC monograph | 856 |
| a WHO ATC class (with or without a trial) | 230 |
| a cited trial alone | 5 |
| an unreadable label alone | 10 |

The 115 trial records shrink to 5 diseases because 110 sit under a disease
another record already approves. The 293 ATC records are 230 diseases on 205
molecules.

## Gap 1 — the 35 unresolved label records

### What they are

D23's note says "most cite a set id DailyMed no longer serves". That is not
what the cache shows. Re-reading the 35 records' labels from
`db/cache/dailymed/`:

| cause | records |
|---|---|
| the label page was served and parsed, but its `<title>` is empty | 25 |
| a pre-2009 label with no marketing table, in the page or the SPL XML | 8 |
| a set id DailyMed no longer serves | 1 |
| not a set id: an fda.gov biologics page in ChEMBL's DailyMed slot | 1 |

**The 25 are a defect in `parse_label`.** It sets `found` from the page title,
and 618 labels in the release are real label pages with an empty `<title>`.
Their marketing tables parse correctly (ANDA, NDA, monograph), but `verdict`
treats a label that is not `found` as unreadable. DailyMed's answer for a set
id it does not hold is its search page, titled "DailyMed", which never names
the set id; every one of the 618 names its set id several times. The defect
only ever made a record *unresolved*, never wrongly *unapproved*, because
`unapproved` needs every label read.

Re-run with `found` meaning "the page names the set id it was asked for", the
35 become:

| verdict | records | in scope |
|---|---|---|
| label | 22 | 10 (carisoprodol, buprenorphine, propoxyphene, aspirin, codeine, methamphetamine, clorazepate ×3, maprotiline) |
| monograph | 1 | 0 |
| unapproved | 2 | 1: **benzocaine, Anesthesia**: all five cited labels are UNAPPROVED DRUG OTHER |
| unresolved | 10 | 3 |

Benzocaine stays in the catalogue: its Toothache and Premature Ejaculation
records rest on OTC monographs, and it is ATC N as well. Its Anesthesia row
would read Marketed unapproved.

### Proposals

1. **Fix `found`** in `scripts/check_dailymed_labels.py`: a page is the label
   when it names the requested set id. Then `reparse` and `write` (the pages
   are cached, so nothing is refetched), pin the new sha256 and rebuild. Add a
   test with an empty-title page beside one of DailyMed's search page. This is
   a bug fix and needs no decision. It is also a DATA-QUALITY-LOG entry.
2. **A set id DailyMed no longer serves: ask NLM's RxNav by the same set id.**
   `rxnav.nlm.nih.gov/REST/ndcproperties.json?id=<set id>&ndcstatus=ALL`
   returns a `MARKETING_CATEGORY` where RxNorm still holds the label's NDCs.
   It answered NDA (ACTIVE) for buprenorphine's `b25457a9-…`, the one such
   label here (in scope, Acute Pain). The lookup is by identifier, it is free,
   and it would be cached and committed through the same file.
3. **An fda.gov URL in the DailyMed slot is an FDA document**, so its basis is
   `regulator`. There is one in the release: Aucatzyl (obecabtagene
   autoleucel), a BLA. Its URL is kept as the record's reference.
4. **A label older than FDA's marketing table** (6 labels, 8 records:
   Viadur, Moxatag ×2, Hospira's cimetidine, ISMO, Baxter's propranolol ×2,
   Lithane) states its category nowhere this project can read it. I checked
   the DailyMed page, the SPL XML, RxNav (label type only) and openFDA's NDC
   directory (not found). Every one of the 8 is a molecule with an FDA
   approval year (`molecules.first_approval`, from FDA's own records via
   ChEMBL). **Proposed rule:** an unreadable label keeps ChEMBL's Approved
   only where FDA records an approval year for the molecule. Otherwise it falls
   like any other record without support. The hover says the label predates
   FDA's marketing category. No record changes under that rule today; it
   keeps a future one from standing on nothing. *The user's call.*

With 1–3 adopted, in-scope unresolved records go from 15 to 2: isosorbide
mononitrate for angina (ISMO) and lithium carbonate for Depressive Disorder
(Lithane). Both are kept under rule 4.

## Gap 3 — the 115 "Phase 4 trial alone" records

### What they are

D23 assumed that a phase-4 record citing only ClinicalTrials.gov cites a
Phase 4 trial. The page says so on hover ("a Phase 4 (post-marketing)
trial"), and the decision to keep these Approved rested on it ("a
post-marketing trial usually studies the approved use"). **The registry
disagrees for 108 of the 115.** Using the registry phases already stored in
`trial_status`:

| furthest registry phase among a record's cited trials | records |
|---|---|
| Phase 4 | 7 |
| Phase 3 | 86 |
| Phase 2 | 14 |
| Phase 1 | 8 |

So ChEMBL's 4 on those 108 is not the trial's. Nothing ChEMBL cites says the
drug is approved for that disease. That is exactly the shape D23 already
handles for an unapproved label: no approval cited, so take the furthest phase
of the trials cited.

At disease level the rule separates the five trial-only diseases cleanly:

| disease | cited trials, registry phase | under the rule |
|---|---|---|
| desipramine, Major Depressive Disorder | NCT00166114 Phase 4 (US), conditions include D003865 | Approved |
| lidocaine, Neuralgia | NCT00851513 Phase 4 (France), NCT02862769 Phase 4 (Canada) | Approved |
| lidocaine, Muscle Cramp | NCT01155167 Phase 2/3 | Phase 3 |
| folic acid, Depressive Disorder | NCT00480207 Phase 2/3 (Israel) | Phase 3 |
| lithium carbonate, Depressive Disorder | six trials, Early Phase 1 to Phase 3, none Phase 4 | Phase 3 |

The two kept are the two approved uses D23's first attempt wrongly demoted:
desipramine's depression and Lidoderm's neuralgia. Of the three that fall, as
far as I know none is a US-approved use. Folic acid's depression trial tests it
beside DHA and B12. Lithium is approved for bipolar disorder, and its row stays
Approved anyway through the Lithane label (gap 1, rule 4). No molecule changes
membership, since each falls to a phase above D21's Phase 1 floor.

### Proposals

1. **A record whose only support is cited trials is Approved only where one
   of them is Phase 4 in the registry; otherwise it takes their furthest
   registry phase.** This is D23's own rule for unapproved labels, extended.
   The build reads no network, so the registry phases have to come through the
   committed file, as D23 already does for unapproved records' trials:
   `check_dailymed_labels.py write` (or a sibling script, since these are not
   labels) records them for every trial-only record. 108 records and 3 in-scope
   diseases change.
2. **Correct the hover.** `trial` would then mean a Phase 4 trial is cited,
   which is true. A record that falls says its trials' phase, as an unapproved
   one already does.
3. **Optional, stricter: the Phase 4 trial must be about that disease.**
   Check that the trial's condition MeSH IDs
   (`derivedSection.conditionBrowseModule.meshes`) contain the record's MeSH
   ID or a descendant, by identifier. Both kept diseases pass. Name the
   trial's site countries on the hover from `trial_status.countries`, since a
   Phase 4 trial is post-marketing *where it ran*: "Approved, per a Phase 4
   trial in France".

## Gap 2 — the 293 "ATC class alone" records

### What they are

A WHO ATC code is a classification by use. It is not a regulator, and the
disease is ChEMBL's reading of the class (N05BA, anxiolytics, gives
"Anxiety"). An ATC code normally means the substance was marketed somewhere,
which is why D23 let it stand. The 230 diseases split:

| | diseases | molecules |
|---|---|---|
| the molecule has an FDA approval year, or another in-scope disease checked approved | 142 | — |
| neither: no US trace at all | 88 | 80 |

The 88 are mostly drugs authorised nationally in Europe or Japan
(bromazepam, sulpiride, dosulepin, clotiazepam, piribedil, loxoprofen), and
some long withdrawn. **ChEMBL itself records withdrawals** (`drug_warning`,
`warning_type = 'Withdrawn'`, with countries and years). That source is
already in the release and is read by no one here:

- 47 of the 230 ATC-only diseases belong to a molecule withdrawn somewhere:
  19 of the 142, and 28 of the 88.
- Across all 1,101 Approved diseases, 83 diseases on 54 molecules are
  withdrawn somewhere. Five molecules are withdrawn worldwide: glafenine,
  zimeldine, nomifensine, remoxipride and thioridazine.

There are two different questions here. Was the drug approved by anyone, and
where? And does that approval still stand?

### Proposals

1. **Say where an approval was withdrawn, from ChEMBL's `drug_warning`, on
   every Approved disease of a withdrawn molecule**, whatever its basis:
   "Approved; withdrawn in France, 1990". Offline, no new source, nothing moves
   membership. *The user's call:* whether a molecule withdrawn **worldwide**
   should still read Approved at all, or read "Approved, withdrawn worldwide
   (1984)".
2. **Name a regulator where an identifier-keyed source can.** DrugCentral
   (drugcentral.org; CC BY-SA 4.0; dump dated 2026-09-25) has a molecule-level
   `approval` table with FDA, EMA and PMDA approvals, per its own example SQL.
   Its identifier table is said to carry ChEMBL IDs and UNIIs. That would turn
   an `atc` basis into "EMA, 1998" or "PMDA, 2004" at the molecule level.
   **Not yet measured:** the dump needs PostgreSQL with the RDKit extension,
   and this machine has no PostgreSQL. The first step is to restore it and
   count how many of the 80 no-US-trace molecules it reaches. My expectation is
   few, because most of them are national European authorisations, which
   neither the EMA nor DrugCentral lists. Licence to check before export, as
   GtoPdb's was.
   *Measured 2026-10-16 (D24):* restored into PostgreSQL 18.6 with the RDKit
   cartridge; DrugCentral publishes the dump under CC BY-SA 4.0. It reaches 8
   of the 80 (7 FDA, 1 PMDA), and 139 of the 228 ATC-only diseases as built.
   The expectation held.
3. **Disease level, for the 142 whose molecule is approved somewhere:**
   DrugCentral's indications reportedly separate on-label from off-label use,
   but are keyed by SNOMED CT and UMLS CUI, not MeSH. The identifier bridge
   would be Wikidata items carrying both P2892 (UMLS CUI) and P486 (MeSH).
   Coverage is unmeasured. Same first step as 2.
   *Measured 2026-10-16 (D24):* indications are keyed by UMLS CUI and
   relationship (`indication`, `off-label use`, `contraindication`). Through
   Wikidata's 1:1 CUI-to-MeSH pairs (25,938), 49 of the 230 ATC-only diseases
   are confirmed on-label: 21 at the same MeSH heading, 14 at a narrower one
   (Lennox-Gastaut syndrome for Epilepsy), 14 only at a broader one (Pain for
   Arthralgia, a weak confirmation). 4 are off-label only, 79 have a matched
   structure whose bridged indications do not match, 91 have indications the
   bridge cannot map, and 7 reach no single structure. A floor, since the
   bridge is the limit; every match inspected was correct. With many-to-one
   bridge entries allowed, 64 are on-label.
4. **Rejected, with reasons:**
   - **NLM MED-RT `may_treat`** (RxClass): its disease IDs are MeSH, but it
     mixes labelled and off-label uses without saying which, so it is not an
     approval source.
   - **EMA's medicines spreadsheet:** substances by name only (and an ATC
     code), therapeutic area as MeSH heading *text*, and centrally authorised
     products only. Invariant 15 rules out the names, and the old national
     authorisations are not in it.
   - **openFDA labels:** indications as free text.
   - **Health Canada's DPD and PMDA:** no identifier-keyed list found.
5. **What stays unchecked: national authorisations outside the US.** No public,
   identifier-keyed source found for them. The hover already names the ATC
   class as the source. Proposed wording: "classified by WHO ATC as a
   <class>; no regulator's record is cited", rather than reading as any
   regulator's.

## Order, and what each needs

| | change | needs | moves |
|---|---|---|---|
| 1 | gap 1.1, the `found` fix | nothing; bug fix | 25 records, 11 in scope; benzocaine's Anesthesia becomes Marketed unapproved |
| 2 | gap 3.1–3.2, trial-only by registry phase | the user's yes (a policy change, D23 extended) | 108 records; 3 in-scope diseases fall to Phase 3 |
| 3 | gap 1.2–1.4: RxNav, the fda.gov URL, the residual rule | the user's yes on 1.4 | 2 records now, and a guard after |
| 4 | gap 2.1, withdrawals | the user's call on wording, and on worldwide | display only |
| 5 | gap 3.3, trial condition and country | optional | wording; possibly a few records |
| 6 | gap 2.2–2.3, DrugCentral | PostgreSQL + RDKit to measure first | unknown until measured |

Items 1–3 are one rewrite of the committed status file and one rebuild. Each
changes the file through a reviewed diff, the way D23 does.
