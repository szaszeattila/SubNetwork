# MeSH pharmacological actions without PubChem

**A proposal with its measurement, 2026-10-13. Nothing is adopted.** The
backfill still reads PubChem. The script behind every figure here is
[analysis/mesh_route_b/compare.py](../analysis/mesh_route_b/compare.py),
read-only and offline.

## Why this was measured

`scripts/resolve_cohort_pharm_actions.py` asks PubChem about every molecule:
one call from InChIKey to compound, then two calls per compound for its MeSH
data. After D21 nearly doubled the catalogue, PubChem cut this machine off
after about 400 requests, twice, on 2026-10-12. In September the same script
at the same pace (150–170 requests a minute) had made about 2,400 without
being blocked. PubChem's throttling header then read every meter Green and
still refused, "too many requests per second or blacklisted": the address was
on a temporary block. Retrying into the block (the script's own retries, and a
probe loop) kept it there. The cache's file times record each burst:

| burst | requests answered before the block | pace |
|---|---|---|
| 2026-09-26, 16:11–16:27 | ~2,400, never blocked | 150–170/min |
| 2026-10-12, 22:15–22:18 | 407 | ~180/min |
| 2026-10-13, 00:16–00:18 | 399 | ~180/min |
| 2026-10-13, morning | 68, then 42 | 60/min, then 20/min |

That raised a structural question: can the actions be read without asking
PubChem per molecule at all?

## The two routes

**Route A (today).** InChIKey → PubChem compound(s) → the actions PubChem
lists for each. PubChem links a compound to MeSH records **by name**, which is
how tafamidis carried triamcinolone's actions through "FX006"
([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md), 2026-09-26). So each action is judged
against the molecule's identity, and 11 links on 6 molecules are set aside.

**Route B.** InChIKey → FDA UNII → the one MeSH record carrying that UNII →
that record's own `PharmacologicalActionList`, read from the pinned MeSH files.
This is the identity route the structure classes already use
(`resolve_cohort_mesh_structure.py`, and `own_record` in the PubChem backfill),
so every step is an identifier (invariant 15) and nothing touches the network.
The D27 hierarchy above each action is unchanged.

Three variants were measured:

- **B1:** the UNII alone.
- **B2:** B1, and where the UNIIs reach no MeSH record, the CAS numbers FDA
  lists for them. Older MeSH records carry a CAS number where newer ones carry
  the UNII (GABA `56-12-2`, budesonide `51333-22-3`). Used *alongside* the
  UNII, a CAS number that a second record also carries refused five molecules
  the UNII had placed (eplerenone, lacosamide), so it is a fallback only.
- **B3:** B2, and where that still finds nothing, the InChIKey's first block
  (the skeleton, stereochemistry ignored), accepted only when it reaches
  exactly one record.

## Against route A, on the catalogue where route A is complete

The 1,335-entry build of 2026-10-11, whose PubChem backfill finished. Route A
gives actions to 787 molecules, 1,697 links.

| | molecules with actions | identical to A | A only | B only | both, differing |
|---|---|---|---|---|---|
| B1 | 771 | 735 | 45 | 29 | 7 |
| **B2** | **778** | **741** | **39** | **30** | **7** |
| B3 | 808 | 752 | 27 | 48 | 8 |

Route B carries **none** of the 11 links route A's judge sets aside.

**What route B gets right that route A does not:**

- **Tarenflurbil.** Route A gives it flurbiprofen's *Cyclooxygenase
  Inhibitors* and NSAID actions, though it is the enantiomer made for little
  COX activity. That is one of CLAUDE.md's two open MeSH findings. Route B
  gives it none.
- **Amphotericin B.** Route A lists *Liposomes*, a formulation rather than an
  action. Route B drops it.
- **30 molecules route A misses entirely,** among them pentobarbital,
  bupivacaine, chlordiazepoxide, minocycline, tranexamic acid and abacavir.
  - For pentobarbital and bupivacaine, PubChem answers 404 for the action
    heading on the parent compound. Route B reaches their records through a
    UNII.
  - For chlordiazepoxide and minocycline, PubChem returned no compound for
    ChEMBL's InChIKey.

**What route B loses (B2's 39):**

- **25:** none of the molecule's InChIKeys is in FDA's file.
  - Mostly stereochemistry: ChEMBL draws methylphenidate, nebivolol,
    pentazocine and tetrabenazine without stereo, and FDA registers
    stereo-defined forms.
  - Also peptides FDA files with no InChIKey: oxytocin, exenatide,
    vasopressin, teriparatide.
- **13:** the UNII reaches no MeSH record, or two.
- **1:** the record lists no action (samidorphan).

Methylphenidate is the best-known drug among them.

**The 7 differing molecules** are mostly route A carrying a related record's
actions: haloperidol decanoate (haloperidol's), prednisolone acetate
(prednisolone's), dexchlorpheniramine, brexanolone (*GABA Modulators* and
*Neurosteroids*, which its own record lacks), plus tarenflurbil, amphotericin
B and silybin A above.

**Why not B3.** The skeleton fallback reaches 30 more molecules, many
correctly (buprenorphine, tramadol, nebivolol, vincristine), but it is the
error shape the identifier rule exists to stop:

- **Lucerastat landed on miglustat's record**, a different molecule that
  differs only in stereochemistry.
- **Esmethadone took methadone's opioid actions,** though it was developed
  for its low opioid activity. That is the tarenflurbil error made new.
- **Arbaclofen, dexmecamylamine, dexketoprofen and levomethadone** each took
  their racemate's record.

**On the expanded catalogue (D21, 2,452 entries),** B2 gives actions to 1,080.
Route A's figure there is unknown until the PubChem backfill completes.

## What adopting B2 would mean

- **No PubChem calls for this backfill.** It runs offline, in minutes rather
  than hours, from files already pinned in `build_manifest`, and reproduces
  exactly.
- **The judge becomes unnecessary,** because no name-made link enters. The
  6 molecules and 11 links it guards against cannot arise.
- **Coverage is about the same overall:** 778 against 787, 741 identical. It
  swaps 39 molecules route A reaches (methylphenidate among them) for 30 it
  does not (pentobarbital, chlordiazepoxide among them).
- **The harness's second judge moves.** The MeSH answer key is built from
  these actions, so grades taken under route A and route B are not comparable.
  Both should be taken on one build at the switch.
- **It changes how a value enters the database,** so it is the user's call
  and gets a DATA-QUALITY-LOG entry.

## Open

1. **The stereo losses.** A rule that matches ChEMBL's flat structure to an
   FDA substance registered as a racemate (both enantiomers of one skeleton)
   might recover methylphenidate without B3's errors. It is not measured.
2. **Peptides** need an identifier other than an InChIKey (UNII by sequence,
   or ChEMBL's own cross-references). Not measured.
3. **PubChem client fixes stand whether or not B2 is adopted,** for as long
   as this backfill reads PubChem and for any future source that does (the
   legacy pipeline also reads PubChem, and is not modified):
   - read `X-Throttling-Control`;
   - stop rather than retry on 429 or 503;
   - cap requests per run;
   - never poll while blocked.
