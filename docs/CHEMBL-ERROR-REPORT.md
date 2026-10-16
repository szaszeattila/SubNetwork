# ChEMBL error report

The data errors this project has found in ChEMBL, collected into **one email
to be sent later** (the user's call, 2026-10-16): each error found is added
here as a numbered item in the email and an evidence section below, rather than
reported on its own. **Nothing has been sent.**

| # | Error | Found | What the build does meanwhile |
| --- | --- | --- | --- |
| 1 | Alfuzosin's alpha-1 mechanism filed as AGONIST (mec_id 1161) | 2026-10-10 | withholds the action |
| 2 | Myristicin's record (CHEMBL481044) named ELEMICIN; elemicin's record (CHEMBL458690) unnamed | 2026-10-16 | nothing; the page shows ChEMBL's name |

## Status

- **Not sent.** Send it from your own address, then record the date here and
  in [COHORT-2.md](COHORT-2.md) open item 6.
- **Still wrong upstream.** Alfuzosin's mec_id 1161 was `AGONIST` in ChEMBL's
  live web service on 2026-10-10:
  `https://www.ebi.ac.uk/chembl/api/data/mechanism.json?molecule_chembl_id=CHEMBL1723`.
  CHEMBL481044 was named `ELEMICIN` there on 2026-10-16:
  `https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL481044.json`.
  Recheck both before sending.
- **Where to send it.** chembl-help@ebi.ac.uk is ChEMBL's channel for data
  errors ([getting help](https://chembl.gitbook.io/chembl-interface-documentation/web-services/getting-help)).
  Data-only issues can also go to the GitHub repository
  `chembl/chembl_data_issues`, which gives a public link to cite in
  [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md); there, one issue per error is
  probably easier for them to close.
- **When a fix could arrive.** ChEMBL has released every 7 to 10 months: 33 in
  May 2023, 34 in March 2024, 35 in December 2024, 36 in July 2025, 37 in May
  2026 ([release table](https://link.springer.com/article/10.1186/s13321-025-00963-z)).
  ChEMBL 38 is likely around early 2027; a report sent late may miss it.
- **Adding an error:** a numbered item in the email, a row in the table above,
  an evidence section below with every line checked and dated, and the
  DATA-QUALITY-LOG entry it came from.

## The email

**To:** chembl-help@ebi.ac.uk
**Subject:** Two data errors in ChEMBL 37: alfuzosin mechanism (mec_id 1161) and the myristicin/elemicin names (CHEMBL481044, CHEMBL458690)

```text
Dear ChEMBL team,

I'd like to report two data errors we found while building a drug-target
network from the ChEMBL 37 release. Both are present in ChEMBL 37 and in the
live web service as of the dates below.

1. Alfuzosin's alpha-1 mechanism is filed as AGONIST (checked 2026-10-10)

Record
- mec_id: 1161
- Molecule: ALFUZOSIN HYDROCHLORIDE, CHEMBL1723 (parent CHEMBL709)
- Target: Adrenergic receptor alpha-1, CHEMBL2094251 (PROTEIN FAMILY)
- action_type: AGONIST
- mechanism_of_action: "Adrenergic receptor alpha-1 agonist"
- Reference: DailyMed, setid=f075a897-7bef-4799-b7e2-7e051c461443#nlm34090-1

Why it looks wrong
a. The record's own reference says the opposite. Section 12.1 (Mechanism of
   Action) of that DailyMed label reads: "Alfuzosin is a selective antagonist
   of post-synaptic alpha1-adrenoreceptors."
b. The neighbouring alpha-1 family records from the same batch (mec_id
   1158-1170) file every other alpha-1 blocker as ANTAGONIST - prazosin
   (1168), doxazosin (1162), terazosin (1170), tamsulosin (1169), carvedilol
   (1160) - and only the agonists (phenylephrine, midodrine, methoxamine,
   metaraminol) as AGONIST. Alfuzosin appears to have picked up a
   neighbouring row's value.
c. Other curated sources agree it is an antagonist: the IUPHAR/BPS Guide to
   Pharmacology lists alfuzosin as an antagonist at alpha-1A, 1B and 1D, and
   MeSH files it under Adrenergic alpha-1 Receptor Antagonists.

Suggested correction
action_type ANTAGONIST; mechanism_of_action "Adrenergic receptor alpha-1
antagonist".

2. Myristicin's record is named ELEMICIN (checked 2026-10-16)

Records
- CHEMBL481044, pref_name ELEMICIN, drawn as C=CCc1cc(OC)c2c(c1)OCO2,
  InChIKey BNWJOHGLIBDBOB-UHFFFAOYSA-N - which is myristicin
  (4-methoxy-6-allyl-1,3-benzodioxole; PubChem CID 4276, "Myristicin").
- CHEMBL458690, no pref_name, drawn as C=CCc1cc(OC)c(OC)c(OC)c1, InChIKey
  BPLQKQKXWHCZSS-UHFFFAOYSA-N - which is elemicin
  (3,4,5-trimethoxyallylbenzene; PubChem CID 10248, "Elemicin").

Why it looks wrong
a. The structure at CHEMBL481044 has a methylenedioxy ring and one methoxy
   group; elemicin has three methoxy groups and no ring.
b. Nine of the ten documents that name the compound at CHEMBL481044 call it
   "Myristicin" (CHEMBL1159215, CHEMBL1641401, CHEMBL1764997, CHEMBL2163249,
   CHEMBL3865813, CHEMBL4020792, CHEMBL4334515, CHEMBL5244224,
   CHEMBL5316354). The one that calls it "Elemicin" is
   CHEMBL1144120 (J Nat Prod 1999, antifungal phenylpropanoids), which looks
   like the source of the name.
c. In that same document, "5'-metoxy eugenol" is registered at CHEMBL458690,
   the elemicin structure, while the 2019 and 2023 documents with records at
   CHEMBL458690 (CHEMBL4334515, CHEMBL5365402) name it "Elemicin". The 1999
   document's two records may have been registered one structure off; we
   have not checked the paper itself.

Suggested correction
pref_name MYRISTICIN for CHEMBL481044 and ELEMICIN for CHEMBL458690, and a
check of the compound records in document CHEMBL1144120.

Thank you for maintaining ChEMBL.

Kind regards,
Attila Szabo
```

## 1. Alfuzosin's mechanism

ChEMBL files alfuzosin as an alpha-1 **agonist**; it is an antagonist, and the
record's own cited label says so.

### The evidence

Every line here was checked on 2026-10-10.

| What | Where it was read | What it says |
| --- | --- | --- |
| The record | ChEMBL 37 bulk SQLite, `drug_mechanism` mec_id 1161 | `AGONIST`, "Adrenergic receptor alpha-1 agonist", at CHEMBL2094251 (PROTEIN FAMILY), filed against the hydrochloride CHEMBL1723; its one reference is the DailyMed label |
| The cited label | [DailyMed, setid f075a897-…](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=f075a897-7bef-4799-b7e2-7e051c461443), section 12.1 | "Alfuzosin is a selective antagonist of post-synaptic alpha1-adrenoreceptors." |
| The batch | `drug_mechanism` mec_id 1158-1170 | one run through the alpha-1 family; agonists (phenylephrine 1159 and 1167, methoxamine 1163, metaraminol 1164, midodrine 1166) and blockers (trimipramine 1158, carvedilol 1160 and 1165, doxazosin 1162, prazosin 1168, tamsulosin 1169, terazosin 1170) interleaved; every blocker but alfuzosin is `ANTAGONIST` |
| GtoPdb 2026.3 | `gtopdb_interactions` in `db/cohort1.db` | Antagonist at ADRA1A, ADRA1B and ADRA1D, each a primary target |
| MeSH | the `mesh_pa` classes | Adrenergic alpha-1 Receptor Antagonists |
| ChEMBL's live API | the URL under **Status** | still `AGONIST` |

How unusual it is: of about 50 pairs where ChEMBL's curated action and
GtoPdb's disagree at a primary target, nearly all are wording (agonist against
partial agonist) or genuine pharmacology (nalmefene at kappa). Alfuzosin is the
only plain agonist-against-antagonist contradiction on a drug whose action is
not in dispute ([DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), 2026-10-10).

### What this project does meanwhile

The build withholds the action rather than rewriting it.
`CHEMBL_MECHANISM_ACTION_EXCLUSIONS` in `config/cohort1_evidence.json`
(evidence policy 1.1.0) names mec_id 1161 and the `AGONIST` it expects.
`evidence.withhold_excluded_actions` keeps the record and its curated support,
stores ChEMBL's word in `curated_mechanisms.excluded_action_type`, and the
panel shows a "direction withheld" line in its place. GtoPdb's antagonist is
then alfuzosin's only direction. Phenylephrine fell from alfuzosin's 3rd
closest match to 236th, and prazosin rose from 4th to 2nd.

### When ChEMBL fixes it

The build will stop on the first ChEMBL release that changes the row, and so
will `tests/test_cohort_build.py` while the bulk file is present: the entry
names the action it expects, and a corrected record no longer says it. Then:

1. Confirm the new record reads `ANTAGONIST`.
2. Delete the mec_id 1161 entry from `CHEMBL_MECHANISM_ACTION_EXCLUSIONS` and
   bump the evidence policy version.
3. Rebuild, and note the fix and its release in
   [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) and
   [COHORT-2.md](COHORT-2.md).

## 2. Myristicin named ELEMICIN

Found by D27's review, when PsychonautWiki's *Myristicin* placed through FDA's
UNII InChIKey at a record ChEMBL names ELEMICIN
([DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), 2026-10-16).

### The evidence

Every line here was checked on 2026-10-16.

| What | Where it was read | What it says |
| --- | --- | --- |
| The misnamed record | ChEMBL 37 bulk SQLite, `molecule_dictionary` and `compound_structures`, CHEMBL481044 (molregno 481934) | pref_name `ELEMICIN`; `C=CCc1cc(OC)c2c(c1)OCO2`, InChIKey BNWJOHGLIBDBOB-UHFFFAOYSA-N; no synonyms; 47 activities |
| What that structure is | PubChem, by InChIKey | CID 4276, "Myristicin", 4-methoxy-6-prop-2-enyl-1,3-benzodioxole; FDA's UNII 04PD6CT78W, MYRISTICIN, carries the same key |
| Elemicin's own record | ChEMBL 37, CHEMBL458690 | no pref_name; `C=CCc1cc(OC)c(OC)c(OC)c1`, InChIKey BPLQKQKXWHCZSS-UHFFFAOYSA-N, which is PubChem CID 10248, "Elemicin" |
| What the papers call CHEMBL481044 | `compound_records` | "Myristicin" in nine documents from 1995 to 2023; "Elemicin" only in CHEMBL1144120 (J Nat Prod 1999); a PubChem BioAssay set names it by SID only |
| What the papers call CHEMBL458690 | `compound_records` | "Elemicin" in CHEMBL4334515 (2019) and CHEMBL5365402 (2023); "5'-metoxy eugenol" in CHEMBL1144120 (1999) |
| ChEMBL's live API | the URL under **Status** | still `ELEMICIN` at CHEMBL481044 |

### What this project does meanwhile

Nothing is withheld: the structure, which is right, is the identity, and the
claims at CHEMBL481044 are measurements of myristicin. The entry is in the
catalogue because PsychonautWiki lists myristicin (D27), and its panel shows
ChEMBL's name, ELEMICIN, with "PsychonautWiki, as Myristicin" beneath it. The
policy entry's `review` note records the error. Overriding a ChEMBL name has no
mechanism here, and one error does not justify building one.

### When ChEMBL fixes it

Nothing stops the build; a rebuild picks up the new name. Then remove the
`review` note's mention of the error from `open_listings.py`'s `REVIEW` and the
policy, and note the fix and its release in
[DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md).
