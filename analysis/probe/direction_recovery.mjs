// What D15 catches now that a curated direction is read at the protein rather
// than at the ChEMBL target record it happens to be filed against.
//
// **This measured a prototype and the prototype was adopted.** The viewer does
// this in `pooledDirection`, so the two columns below now agree and the honest
// reading of a 0 in "pairs blind today that pooling demotes" is that the page
// already does it, not that there was nothing to find. What the script still
// earns its place by is the one way it differs from what shipped: it pools on
// the **gene symbol** and the viewer pools on the **accession**, so the gap
// between the two "could compare" lines is exactly what the symbol key buys -
// 56 more comparable pairs and not one further demotion, which is why the
// viewer matches on the identifier and leaves the name alone (invariant 6).
//
// The case that prompted it: morphine's nearest neighbour is naltrexone, its
// own antagonist. ChEMBL curates both directions -- morphine AGONIST at
// CHEMBL233 (human mu-opioid, SINGLE PROTEIN), naltrexone ANTAGONIST at
// CHEMBL2095181 (human opioid receptors mu/kappa/delta, PROTEIN FAMILY). The
// two never land on one target record, `directionAt` returns null, and the pair
// is scored as though nothing were known about direction. CLAUDE.md already
// records this shape for adenosine and istradefylline and calls 499 "a floor,
// not a census". This measures the floor's distance from the census.
//
// The rule prototyped: a curated action is attributed to every protein the
// target it is filed against covers -- a SINGLE PROTEIN contributes its own
// gene symbol, a FAMILY or COMPLEX GROUP contributes all of its components'.
// Species is dropped, because OPRK1 and Oprk1 are one receptor measured twice.
// Two molecules are then compared at each protein they share.
//
// This is deliberately NOT the D06 merge. Nothing here changes what a shared
// target is, what it weighs, or what the canvas draws. It changes only which
// two actions get compared, and it is the same argument the viewer already
// makes for reading direction at subsumed rows: the row carrying the direction
// is often not the row carrying the score.
//
// Read-only. Adopts nothing itself; what it measured is adopted in the viewer.

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

// The viewer's own opposition table, read through the accessor it exposes for
// exactly this reason rather than copied here.
const OPPOSED = new Set();
for (const [a, b] of viewer.opposedActions()) {
  OPPOSED.add(a + "|" + b);
  OPPOSED.add(b + "|" + a);
}

const symbolsOf = (t) => (t && t.components ? t.components : [])
  .map((c) => String(c.gene_symbol || "").toUpperCase()).filter(Boolean);

/** molecule id -> (gene symbol -> Set of curated actions), pooled as above. */
function curatedByProtein(rows, moleculeId) {
  const out = new Map();
  for (const row of rows) {
    for (const s of row.shared) {
      for (const c of (moleculeId === row.molecule.id ? s.theirs : s.mine)) {
        if (!c.action_type) continue;
        for (const sym of symbolsOf(s.target)) {
          if (!out.has(sym)) out.set(sym, new Set());
          out.get(sym).add(c.action_type);
        }
      }
    }
  }
  return out;
}

// Build the pooled index once, from every claim the filters admit, by walking
// each labelled molecule's own list. `targetsOf` is the viewer's index of a
// molecule's claims and is what the score itself reads.
const pooled = new Map();   // molecule id -> Map(symbol -> Set(action))
function indexMolecule(id) {
  if (pooled.has(id)) return pooled.get(id);
  const m = new Map();
  for (const [tid, claims] of viewer.targetsOf(id)) {
    const t = viewer.lookupTarget(tid);
    const syms = symbolsOf(t);
    for (const c of claims) {
      if (!c.action_type) continue;
      for (const sym of syms) {
        if (!m.has(sym)) m.set(sym, new Set());
        m.get(sym).add(c.action_type);
      }
    }
  }
  pooled.set(id, m);
  return m;
}

/** Does the pooled view make this pair entirely opposed? */
function pooledDirection(aId, bId, sharedSymbols) {
  const A = indexMolecule(aId), B = indexMolecule(bId);
  let comparable = 0, opposed = 0;
  for (const sym of sharedSymbols) {
    const as = A.get(sym), bs = B.get(sym);
    if (!as || !bs) continue;
    comparable++;
    let isOpp = false, same = false;
    for (const x of as) for (const y of bs) {
      if (x === y) same = true;
      else if (OPPOSED.has(x + "|" + y)) isOpp = true;
    }
    if (isOpp && !same) opposed++;
  }
  return { comparable, opposed, allOpposed: comparable > 0 && opposed === comparable };
}

let pairs = 0, nowComparable = 0, nowOpposedPairs = 0;
let wasBlind = 0, recovered = 0, alreadyDemoted = 0;
const newlyDemoted = [];

const labelled = new Set(key.labelled);
for (const id of labelled) {
  const rows = viewer.sharedTargets(id);
  for (const row of rows) {
    if (row.molecule.id < id) continue;
    pairs++;
    const syms = new Set();
    for (const s of row.shared) for (const sym of symbolsOf(s.target)) syms.add(sym);
    const p = pooledDirection(id, row.molecule.id, syms);
    if (p.comparable) nowComparable++;
    if (p.opposed) nowOpposedPairs++;
    if (row.all_opposed) alreadyDemoted++;
    if (!row.n_comparable) {
      wasBlind++;
      if (p.allOpposed) {
        recovered++;
        // Collected in full and capped only at printing: capping here would
        // report whichever 25 came first in iteration order, which is exactly
        // how morphine/naltrexone -- the pair that prompted this -- fell out of
        // the first run's output while being counted in its total.
        newlyDemoted.push({ a: nameOf.get(id), b: row.molecule.name,
          score: row.score, shared: row.n_shared, comparable: p.comparable });
      }
    }
  }
}

const pct = (a, b) => (b ? (100 * a / b).toFixed(1) + "%" : "n/a");
console.log("Direction, read at the protein rather than at the target record");
console.log("=".repeat(68));
console.log(`pairs examined                                ${pairs}`);
console.log(`pairs D15 compares as shipped (accession key) ${pairs - wasBlind}  (${pct(pairs - wasBlind, pairs)})`);
console.log(`pairs it could compare on a gene-symbol key   ${nowComparable}  (${pct(nowComparable, pairs)})`);
console.log(`pairs demoted as shipped                      ${alreadyDemoted}`);
console.log(`pairs the symbol key would demote further     ${recovered}`);
console.log("");
console.log("Newly demoted pairs, highest scoring first:");
newlyDemoted.sort((a, b) => b.score - a.score);
for (const e of newlyDemoted.slice(0, 20)) {
  console.log(`  ${e.score.toFixed(3)}  ${e.a} / ${e.b}` +
    `   (${e.shared} shared, opposed at ${e.comparable} protein${e.comparable > 1 ? "s" : ""})`);
}
