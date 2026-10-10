# ChEMBL error report: alfuzosin's mechanism

ChEMBL files alfuzosin as an alpha-1 **agonist**; it is an antagonist, and the
record's own cited label says so. The report to ChEMBL below was drafted on
2026-10-10 and **has not been sent**. Until ChEMBL corrects the record, the
build withholds that one action (see **What this project does meanwhile**).

## Status

- **Not sent.** Send it from your own address, then record the date here and
  in [COHORT-2.md](COHORT-2.md) open item 6.
- **Still wrong upstream on 2026-10-10.** ChEMBL's live web service (ChEMBL 37,
  released 2026-05-01) returned mec_id 1161 as `AGONIST`:
  `https://www.ebi.ac.uk/chembl/api/data/mechanism.json?molecule_chembl_id=CHEMBL1723`.
- **Where to send it.** chembl-help@ebi.ac.uk is ChEMBL's channel for data
  errors ([getting help](https://chembl.gitbook.io/chembl-interface-documentation/web-services/getting-help)).
  Data-only issues can also go to the GitHub repository
  `chembl/chembl_data_issues`, which gives a public link to cite in
  [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md).
- **When a fix could arrive.** ChEMBL has released every 7 to 10 months: 33 in
  May 2023, 34 in March 2024, 35 in December 2024, 36 in July 2025, 37 in May
  2026 ([release table](https://link.springer.com/article/10.1186/s13321-025-00963-z)).
  ChEMBL 38 is likely around early 2027, and a report sent now may miss it.

## The email

**To:** chembl-help@ebi.ac.uk
**Subject:** Data error: alfuzosin mechanism filed as alpha-1 AGONIST (mec_id 1161) - should be ANTAGONIST

```text
Dear ChEMBL team,

I'd like to report what looks like a data-entry error in drug_mechanism,
present in ChEMBL 37 and in the live web service today.

Record
- mec_id: 1161
- Molecule: ALFUZOSIN HYDROCHLORIDE, CHEMBL1723 (parent CHEMBL709)
- Target: Adrenergic receptor alpha-1, CHEMBL2094251 (PROTEIN FAMILY)
- action_type: AGONIST
- mechanism_of_action: "Adrenergic receptor alpha-1 agonist"
- Reference: DailyMed, setid=f075a897-7bef-4799-b7e2-7e051c461443#nlm34090-1

Why it looks wrong
1. The record's own reference says the opposite. Section 12.1 (Mechanism of
   Action) of that DailyMed label reads: "Alfuzosin is a selective antagonist
   of post-synaptic alpha1-adrenoreceptors."
2. The neighbouring alpha-1 family records from the same batch (mec_id
   1158-1170) file every other alpha-1 blocker as ANTAGONIST - prazosin
   (1168), doxazosin (1162), terazosin (1170), tamsulosin (1169), carvedilol
   (1160) - and only the agonists (phenylephrine, midodrine, methoxamine,
   metaraminol) as AGONIST. Alfuzosin appears to have picked up a
   neighbouring row's value.
3. Other curated sources agree it is an antagonist: the IUPHAR/BPS Guide to
   Pharmacology lists alfuzosin as an antagonist at alpha-1A, 1B and 1D, and
   MeSH files it under Adrenergic alpha-1 Receptor Antagonists.

Suggested correction
action_type ANTAGONIST; mechanism_of_action "Adrenergic receptor alpha-1
antagonist".

We found this while building a drug-target network from the ChEMBL 37
release, where the error made alfuzosin read as pharmacologically opposite
to the other alpha-1 blockers. Thank you for maintaining ChEMBL.

Kind regards,
Attila Szabo
```

## The evidence

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

## What this project does meanwhile

The build withholds the action rather than rewriting it.
`CHEMBL_MECHANISM_ACTION_EXCLUSIONS` in `config/cohort1_evidence.json`
(evidence policy 1.1.0) names mec_id 1161 and the `AGONIST` it expects.
`evidence.withhold_excluded_actions` keeps the record and its curated support,
stores ChEMBL's word in `curated_mechanisms.excluded_action_type`, and the
panel shows a "direction withheld" line in its place. GtoPdb's antagonist is
then alfuzosin's only direction. Phenylephrine fell from alfuzosin's 3rd
closest match to 236th, and prazosin rose from 4th to 2nd.

## When ChEMBL fixes it

The build will stop on the first ChEMBL release that changes the row, and so
will `tests/test_cohort_build.py` while the bulk file is present: the entry
names the action it expects, and a corrected record no longer says it. Then:

1. Confirm the new record reads `ANTAGONIST`.
2. Delete the mec_id 1161 entry from `CHEMBL_MECHANISM_ACTION_EXCLUSIONS` and
   bump the evidence policy version.
3. Rebuild, and note the fix and its release in
   [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) and
   [COHORT-2.md](COHORT-2.md).
