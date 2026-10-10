// Three structural things the probe set turned up, counted across the whole
// catalogue rather than argued from the examples that found them.
//
//   1. Orthologue double-counting. OPRK1 and Oprk1 are the human and rat
//      records of one receptor. D06 keeps them as two target identities on
//      purpose, and the viewer's own `singleProteinByAccession` already returns
//      null when two targets hold one accession "two species' records of the
//      same protein". But `sharedTargets` scores them as two shared targets, so
//      a pair measured in both species is credited twice for one receptor --
//      the same double-count the family subsumption rule exists to stop, one
//      axis over.
//
//   2. Screening-only pairs. Phenobarbital and pentobarbital share exactly one
//      target: KCNH2, the hERG safety channel. The pair is scored, so it counts
//      as a ranking failure -- but no barbiturate in this catalogue has a
//      GABA-A claim at all, so there was never anything to rank on. That is a
//      third category the grade does not have: not "ranked badly", not
//      "unanswerable", but "answerable only through a screening panel".
//
//   3. Where D15 cannot see. Morphine's nearest neighbour is naltrexone, its
//      own antagonist. D15 did not fire because these particular claims carry
//      no curated direction -- the opposition is real and ChEMBL simply has not
//      annotated it on the rows the pair shares.
//
// Read-only. Counts things; adopts nothing.

import { loadPayload, loadViewer, labelledSet, HarnessError } from "../similarity_harness/harness.mjs";

let data, viewer;
try {
  data = loadPayload();
  viewer = loadViewer(data);
} catch (err) {
  if (err instanceof HarnessError) { console.error(err.message); process.exit(2); }
  throw err;
}

const F = data.fields.molecules;
const idI = F.indexOf("id"), nameI = F.indexOf("name");
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const nameOf = new Map(data.molecules.map((r) => [r[idI], str(r[nameI])]));
const key = labelledSet(data);

const symbolsOf = (t) => {
  if (!t) return [];
  return (t.components || []).map((c) => String(c.gene_symbol || "").toUpperCase())
    .filter(Boolean);
};
// One protein, one symbol -- the only case where "the same protein in another
// species" is unambiguous. A complex or family shares symbols with its own
// members by construction and is not what this is counting.
const soleSymbol = (t) => {
  if (!t || t.target_type !== "SINGLE PROTEIN") return null;
  const s = symbolsOf(t);
  return s.length === 1 ? s[0] : null;
};

let pairs = 0, pairsWithOrtho = 0, orthoRows = 0, scoredRows = 0;
let screeningOnly = 0, screeningOnlyLabelled = 0;
let opposedPairs = 0, blindOpposed = 0;
const examples = [];

// The prevalence a target has to exceed to count as "everything is screened
// here". prevalenceWeight is log(1+n/df)/log(1+n), so a low weight is a common
// target; 0.35 lands around a target on a tenth of the visible catalogue.
const SCREEN = 0.35;

const labelled = new Set(key.labelled);
for (const id of labelled) {
  const rows = viewer.sharedTargets(id);
  for (const row of rows) {
    // Each unordered pair once.
    if (row.molecule.id < id) continue;
    pairs++;
    const bySym = new Map();
    let scored = 0, screening = 0, maxPrev = 0;
    for (const s of row.shared) {
      if (s.subsumed) continue;
      scored++;
      const sym = soleSymbol(s.target);
      if (sym) {
        if (!bySym.has(sym)) bySym.set(sym, []);
        bySym.get(sym).push(s);
      }
      const p = s.prevalence === undefined ? 1 : s.prevalence;
      if (p > maxPrev) maxPrev = p;
      if (p < SCREEN) screening++;
    }
    scoredRows += scored;
    let dup = 0;
    for (const [, list] of bySym) if (list.length > 1) dup += list.length - 1;
    if (dup) {
      pairsWithOrtho++;
      orthoRows += dup;
      if (examples.length < 8 && dup >= 3) {
        examples.push(`${nameOf.get(id)} / ${row.molecule.name}: ${row.n_shared} shared, ` +
          `${dup} of them a second species record of a receptor already counted`);
      }
    }
    if (scored && screening === scored) {
      screeningOnly++;
      if (labelled.has(row.molecule.id)) screeningOnlyLabelled++;
    }
    if (row.n_opposed) opposedPairs++;
    // A pair where ChEMBL gives a direction nowhere, yet both molecules DO have
    // curated directions elsewhere in the catalogue -- D15's blind spot.
    if (!row.n_comparable && row.n_shared) blindOpposed++;
  }
}

const pct = (a, b) => (b ? (100 * a / b).toFixed(1) + "%" : "n/a");

console.log("Across every ranked pair involving an ATC-labelled molecule");
console.log("=".repeat(66));
console.log(`pairs examined                      ${pairs}`);
console.log(`scored shared-target rows           ${scoredRows}`);
console.log("");
console.log("1. Orthologue double-counting");
console.log(`   pairs counting one receptor twice or more   ${pairsWithOrtho}  (${pct(pairsWithOrtho, pairs)})`);
console.log(`   duplicated rows                             ${orthoRows}  (${pct(orthoRows, scoredRows)} of scored rows)`);
for (const e of examples) console.log("     " + e);
console.log("");
console.log("2. Pairs scored only through screening-prevalent targets");
console.log(`   every shared target below prevalence ${SCREEN}   ${screeningOnly}  (${pct(screeningOnly, pairs)})`);
console.log(`   of those, both molecules ATC-labelled        ${screeningOnlyLabelled}`);
console.log("   These are graded as ranking failures today. They are closer to");
console.log("   unanswerable: the pair shares a safety panel and nothing else.");
console.log("");
console.log("3. Direction");
console.log(`   pairs with at least one opposed target       ${opposedPairs}`);
console.log(`   pairs sharing targets with NO curated direction on either side  ${blindOpposed}  (${pct(blindOpposed, pairs)})`);
console.log("   D15 can only demote what ChEMBL annotated; morphine/naltrexone");
console.log("   is in the second group, which is why it ranks first.");
