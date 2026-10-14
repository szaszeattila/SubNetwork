# MeSH pharmacological actions without PubChem

**Adopted 2026-10-13, at the user's request ("adopt B2 and complete the open
items").** It was first measured as a proposal and is kept with its
measurements. `scripts/resolve_cohort_pharm_actions.py` now takes this route.
The comparison behind every figure is
[analysis/mesh_route_b/compare.py](../analysis/mesh_route_b/compare.py),
read-only. The incident and the rule are recorded in
[DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md), 2026-10-13.

## Why this was measured

The backfill used to ask PubChem about every molecule: one call from InChIKey
to compound, then two calls per compound for its MeSH data. After D21 nearly
doubled the catalogue, PubChem cut this machine off after about 400 requests,
twice, on 2026-10-12. In September the same script at the same pace (150–170
requests a minute) had made about 2,400 without being blocked. PubChem's
throttling header then read every meter Green and still refused, "too many
requests per second or blacklisted": the address was on a temporary block.
Retrying into the block (the script's own retries, and a probe loop) kept it
there. The cache's file times record each burst:

| burst | requests answered before the block | pace |
|---|---|---|
| 2026-09-26, 16:11–16:27 | ~2,400, never blocked | 150–170/min |
| 2026-10-12, 22:15–22:18 | 407 | ~180/min |
| 2026-10-13, 00:16–00:18 | 399 | ~180/min |
| 2026-10-13, morning | 68, then 42 | 60/min, then 20/min |

That raised a structural question: can the actions be read without asking
PubChem per molecule at all?

## The routes

**Route A (PubChem, until 2026-10-13).** InChIKey → PubChem compound(s) → the
actions PubChem lists for each. PubChem links a compound to MeSH records **by
name**, which is how tafamidis carried triamcinolone's actions through "FX006"
([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md), 2026-09-26). So each action was
judged against the molecule's identity, and 11 links on 6 molecules were set
aside.

**Route B.** The molecule is placed on its own MeSH record by identifier, and
takes that record's `PharmacologicalActionList` from the pinned MeSH files.
Each step is tried only where the one before placed nothing, and two records at
any step is a refusal:

- **B1: the UNII.** The exact InChIKey → FDA UNII → the record carrying it.
  This is the identity route the structure classes already use.
- **B2: then the CAS number.** The CAS numbers FDA lists for those UNIIs, since
  older MeSH records carry a CAS number where newer ones carry the UNII (GABA
  `56-12-2`, budesonide `51333-22-3`). As a fallback only: used *alongside* the
  UNII, a CAS number a second record shares refused five molecules the UNII
  had placed (eplerenone, lacosamide).
- **R: then a mixture of stereoisomers.** Only where ChEMBL draws the molecule
  with no stereochemistry. The FDA substance registered as a mixture of that
  skeleton's stereoisomers is used: FDA writes a racemate as two InChIKeys
  sharing the first block. ChEMBL's "stereo unspecified" and FDA's "a mixture
  of this skeleton's stereoisomers" describe one substance.
- **WD: then Wikidata.** The MeSH ID (P486) on the Wikidata item carrying the
  molecule's ChEMBL ID (P592). This reaches what FDA files without a
  structure: antibodies, proteins, peptides.
- **B3, measured and refused:** after B2, the InChIKey's first block (the
  skeleton, stereochemistry ignored), accepted when it reaches exactly one
  record.

**Adopted: B2, then R, then WD.**

## Measured against route A

On the 1,335-entry build of 2026-10-11, whose PubChem backfill had finished,
route A gives actions to 787 molecules, 1,697 links.

| | molecules with actions | identical to A | A only | B only | both, differing |
|---|---|---|---|---|---|
| B1 | 771 | 735 | 45 | 29 | 7 |
| B2 | 778 | 741 | 39 | 30 | 7 |
| B2 + R | 792 | 748 | 32 | 37 | 7 |
| **B2 + R + WD (adopted)** | **848** | **760** | **20** | **81** | **7** |
| B3 (refused) | 808 | 752 | 27 | 48 | 8 |

The adopted route writes 1,799 links. Run on a copy of that database, the
rewritten backfill reproduces the 848 exactly.

**What the new route gets right that route A did not:**

- **None of the 11 links route A's judge set aside reappears,** because no step
  makes a name-based link.
- **Tarenflurbil keeps only its own record's action,** *Gamma Secretase
  Inhibitors and Modulators*. Route A added flurbiprofen's *Cyclooxygenase
  Inhibitors*, NSAID and analgesic actions, though tarenflurbil is the
  enantiomer made for little COX activity. That was one of CLAUDE.md's two open
  MeSH findings.
- **Amphotericin B** loses *Liposomes*, a formulation rather than an action.
- **81 molecules route A missed:**
  - pentobarbital and bupivacaine, where PubChem answers 404 for the action
    heading on the parent compound;
  - chlordiazepoxide and minocycline, where PubChem returned no compound for
    ChEMBL's InChIKey;
  - tramadol, reboxetine and milnacipran, through R;
  - 44 biologics through WD (adalimumab, natalizumab, glatiramer acetate,
    interferon beta-1a).

**R has no disagreements.** It places 14 molecules. The 7 route A also
covers are identical (methylphenidate, nebivolol, pentazocine, phenazocine,
camphor, formoterol, glycopyrronium). The other 7 are racemic drugs route A
missed.

**WD agrees with the UNII route.** Where both name a record, it is the same one
for 729 of 735 molecules. The 6 others are a molecule filed as a narrower
concept of another record (armodafinil within *Modafinil*, estradiol valerate
within *Estradiol*), and the UNII route's answer stands there. Of the 56
molecules WD places, the 12 route A also covers are identical: exenatide,
teriparatide, lanreotide, oxytocin, vasopressin, vincristine and six others.

**What it costs: 20 molecules route A reached have no actions now.**

| why | count | molecules |
|---|---|---|
| FDA holds the structure's UNII, but no MeSH record carries it or its CAS | 9 | semagacestat, relugolix, zatolmilast, idalopirdine, dexketoprofen, levoketoconazole, buntanetap, reposal, tocotrienol |
| a flat structure whose stereoisomer mixtures reach no record or two | 4 | doxepin, menthol, clopenthixol, mebicar |
| nothing in FDA's file, and no Wikidata item carries the ChEMBL ID | 4 | liraglutide, ziconotide, nabiximols, hydroxypropyl-β-cyclodextrin |
| drawn with a different defined stereochemistry by ChEMBL and FDA | 2 | benfotiamine, dextrose |
| the record lists no action | 1 | samidorphan |

Matching the last group would mean matching a skeleton while ignoring
stereochemistry, which is B3.

**The 7 molecules that differ** are mostly route A carrying a related record's
actions:

- haloperidol decanoate (haloperidol's);
- prednisolone acetate (prednisolone's);
- dexchlorpheniramine;
- brexanolone (*GABA Modulators* and *Neurosteroids*, which its own record
  lacks);
- tarenflurbil, amphotericin B and silybin A, above.

**Why not B3.** The skeleton fallback reaches 30 more molecules, many correctly,
but it is the error shape the identifier rule exists to stop:

- **Lucerastat landed on miglustat's record,** a different molecule differing
  only in stereochemistry.
- **Esmethadone took methadone's opioid actions,** though it was developed for
  its low opioid activity.
- **Arbaclofen, dexmecamylamine, dexketoprofen and levomethadone** each took
  their racemate's record.

R is the narrow version: it applies only to a structure ChEMBL leaves
unspecified, where the racemate is the honest reading. None of those six molecules
can reach it, because ChEMBL draws all of them with stereochemistry.

## The harness's second judge moved

The MeSH answer key is built from these actions, so changing the route changes
the judge. Graded on one build, the same 1,335-entry ranking:

| key | labelled | scoreable | top-1 | top-10 | MRR |
|---|---|---|---|---|---|
| route A | 699 | 588 | 47.4% | 85.5% | 0.6060 |
| new route | 745 | 621 | 50.4% | 86.8% | 0.6335 |

The ranking did not change: its ATC grade is 38.7% and 0.5119 under both.
These are two keys, and a MeSH grade from before 2026-10-13 is not comparable
with one after.

On the D21 build the new key labels 1,028 molecules, about 280 of the 1,117
newcomers. It grades 45.0% and 0.5945, against 50.4% and 0.6335 on the 1,335
build. As with ATC, the fall is newcomers the judge cannot credit. Asked only
about the old catalogue's molecules, with the newcomers skipped in each list,
the D21 ranking grades 50.2% and 0.6341, where it was before them.

## What adopting it changed

- **No PubChem calls.** The cohort pipeline no longer reads PubChem at all. The
  backfill runs in minutes from pinned MeSH and FDA files and one cached pass
  over Wikidata (`db/cache/wikidata/mesh_by_chembl.json`, recorded by sha256 in
  `build_manifest`).
- **The judge is gone,** because no name-made link enters. So are the PubChem
  client and its cache's role. `db/cache/pubchem/` is unused and can be
  deleted locally.
- **D21's catalogue:** 1,194 of 2,452 molecules carry actions:
  - 1,067 by UNII;
  - 13 by CAS;
  - 22 by stereoisomer mixture;
  - 92 by Wikidata.

## The open items, closed

1. **The stereo losses:** R recovers 14 molecules with no disagreement, and WD
   recovers vincristine, oxytocin, methylnaltrexone and tetrabenazine. The 2
   still lost (benfotiamine, dextrose) are drawn with a different *defined*
   stereochemistry by ChEMBL and FDA, which no identifier settles.
2. **Peptides and other biologics:** WD reaches exenatide, teriparatide,
   lanreotide, oxytocin and vasopressin, and 44 biologics route A never could.
   Liraglutide and ziconotide remain: no Wikidata item carries their ChEMBL ID.
3. **PubChem client fixes:** there is no PubChem client left in the cohort
   pipeline to fix. The legacy pipeline still reads PubChem and is not
   modified. The lessons are recorded for the next rate-limited source in
   DATA-QUALITY-LOG, 2026-10-13: read its throttling signal, stop on a block,
   never poll while blocked, and resume hours later with one probe.
