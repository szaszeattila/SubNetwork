// How much of the label key is shared indication. Read-only.
//
//   node analysis/answer_keys/confounding.mjs
//
// A label lists what happened to patients taking the drug, and those patients
// had the disease the drug is for, so two drugs for one disease list its
// symptoms whatever their mechanism: memantine is donepezil's label neighbour.
// The literature names this confounding by indication and leaves it
// unmeasured for side-effect similarity (Kuhn et al. 2013 do not address it;
// Tatonetti et al. 2012 correct for it in FAERS). If the label key's agreement
// with the ranking were mostly shared indication, the "independent" judge
// would be a use key like ATC's, by another road.
//
// Two measurements:
//
// 1. how often a molecule and its label neighbour share an approved
//    indication (ChEMBL drug_indication, phase 4, by MeSH id, every form
//    folded onto its parent), beside random pairs and beside the classmate
//    pairs of the class keys;
// 2. the label key rebuilt with every candidate that shares an approved
//    indication with the question set aside, so its five neighbours must come
//    from drugs for other diseases; the ranking is graded against it on the
//    same questions as against the key as built, each beside a shuffle.
//
// Indications are compared by exact MeSH id, so "Depressive Disorder" and
// "Depressive Disorder, Major" are different diseases here. That undercounts
// sharing, and the rebuilt key in (2) still lets some same-use pairs through.

import { DatabaseSync } from "node:sqlite";
import { loadPayload, loadViewer, loadKey, grade, pct } from "../similarity_harness/harness.mjs";

const CHEMBL = process.env.CHEMBL_SQLITE_PATH ||
  "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db";

function approvedIndications() {
  const db = new DatabaseSync(CHEMBL, { readOnly: true });
  const out = new Map();
  try {
    for (const r of db.prepare(
      `SELECT COALESCE(h.parent_molregno, d.molregno) AS parent, d.mesh_id
       FROM drug_indication d LEFT JOIN molecule_hierarchy h ON h.molregno = d.molregno
       WHERE d.max_phase_for_ind = 4 AND d.mesh_id IS NOT NULL`).all()) {
      if (!out.has(r.parent)) out.set(r.parent, new Set());
      out.get(r.parent).add(r.mesh_id);
    }
  } finally {
    db.close();
  }
  return out;
}

const share = (a, b) => { for (const x of a) if (b.has(x)) return true; return false; };

/** Every other labelled molecule by IDF-weighted cosine, the key's formula. */
function cosineLists(key) {
  const ids = key.labelled;
  const prof = key.profiles;
  const ingredients = new Set(ids.map((id) => key.ingredientOf.get(id)));
  const df = new Map();
  const counted = new Set();
  for (const id of ids) {
    const ing = key.ingredientOf.get(id);
    if (counted.has(ing)) continue;
    counted.add(ing);
    for (const e of prof.get(id)) df.set(e, (df.get(e) || 0) + 1);
  }
  const idf = new Map([...df].map(([e, n]) => [e, Math.log(ingredients.size / n)]));
  const norm = new Map(ids.map((id) => [id, Math.sqrt([...prof.get(id)].reduce((a, e) => a + idf.get(e) ** 2, 0))]));
  const out = new Map();
  for (const q of ids) {
    const sims = [];
    for (const m of ids) {
      if (key.ingredientOf.get(m) === key.ingredientOf.get(q)) continue;
      let d = 0;
      for (const e of prof.get(q)) if (prof.get(m).has(e)) d += idf.get(e) ** 2;
      if (d > 0) sims.push([m, d / (norm.get(q) * norm.get(m))]);
    }
    sims.sort((a, b) => b[1] - a[1] || a[0] - b[0]);
    out.set(q, sims);
  }
  return out;
}

/** The first `k` distinct ingredients of a list, ties at the k-th included. */
function topIngredients(key, sims, k) {
  const out = new Set(), ings = new Set();
  let last = null;
  for (const [m, s] of sims) {
    const ing = key.ingredientOf.get(m);
    if (ings.size >= k && s !== last) break;
    ings.add(ing);
    out.add(m);
    last = s;
  }
  // Every molecule of a chosen ingredient is a classmate, as in the key.
  for (const [m] of sims) if (ings.has(key.ingredientOf.get(m))) out.add(m);
  return out;
}

function chanceTop1(viewer, key) {
  let n = 0, s = 0;
  for (const id of key.labelled) {
    const peers = key.peersOf(id);
    const ids = viewer.sharedTargets(id).map((r) => r.molecule.id);
    const K = ids.filter((m) => peers.has(m)).length;
    if (!K) continue;
    n++;
    s += K / ids.length;
  }
  return s / n;
}

const data = loadPayload();
const viewer = loadViewer(data);
const ind = approvedIndications();
const label = await loadKey("onsides", data);
const k = 5;

// 1. How often each kind of pair shares an approved indication.
console.log("How much of the label key is shared indication");
console.log("=".repeat(74));
console.log("Pairs in which both molecules have an approved indication, and the share");
console.log("of them that share one (exact MeSH id):");
const rate = (pairs) => {
  const p = pairs.filter(([a, b]) => ind.has(a) && ind.has(b));
  return [p.length, p.filter(([a, b]) => share(ind.get(a), ind.get(b))).length / p.length];
};
const pairsOf = (key) => key.labelled.flatMap((q) => [...key.peersOf(q)].map((m) => [q, m]));
const rows = [["label neighbours (nervous system)", pairsOf(label)]];
for (const name of ["onsides-all", "atc-repaired", "epc"]) rows.push([`${name} classmates`, pairsOf(await loadKey(name, data))]);
rows.push(["the ranking's first answer", label.labelled
  .map((q) => [q, (viewer.sharedTargets(q)[0] || {}).molecule]).filter(([, m]) => m).map(([q, m]) => [q, m.id])]);
const rnd = [];
let seed = 3;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
for (let i = 0; i < 20000; i++) {
  const a = label.labelled[Math.floor(rand() * label.labelled.length)];
  const b = label.labelled[Math.floor(rand() * label.labelled.length)];
  if (label.ingredientOf.get(a) !== label.ingredientOf.get(b)) rnd.push([a, b]);
}
rows.push(["random pairs of labelled molecules", rnd]);
for (const [title, pairs] of rows) {
  const [n, r] = rate(pairs);
  console.log(`  ${title.padEnd(38)} ${String(n).padStart(6)} pairs   ${pct(r).padStart(6)}`);
}

// 2. The key rebuilt without indication-sharing candidates.
const lists = cosineLists(label);
let agree = 0, agreeN = 0;
for (const q of label.labelled) {
  const mine = topIngredients(label, lists.get(q), k), theirs = label.peersOf(q);
  agreeN++;
  if ([...theirs].every((m) => mine.has(m)) && [...mine].every((m) => theirs.has(m))) agree++;
}
console.log("");
console.log(`Sanity: the recomputed neighbours equal the key's for ${agree} of ${agreeN} questions`);
console.log("(IDF here runs over the labelled molecules' ingredients, the key's over every");
console.log("profiled ingredient, so a few ties fall differently).");

const asked = label.labelled.filter((q) => ind.has(q));
const disjoint = new Map();
for (const q of asked) {
  const sims = lists.get(q).filter(([m]) => !(ind.has(m) && share(ind.get(q), ind.get(m))));
  disjoint.set(q, topIngredients(label, sims, k));
}
const variant = {
  ...label, name: "onsides-indication-disjoint", labelled: asked,
  peersOf: (q) => disjoint.get(q) || new Set(),
  // A candidate sharing the question's indication is set aside, not judged.
  judged: (m, q) => label.judged(m, q) && !(q !== undefined && ind.has(m) && ind.has(q) && share(ind.get(q), ind.get(m))),
};
const sameQ = { ...label, labelled: asked };
console.log("");
console.log(`Graded on the ${asked.length} label-key questions with an approved indication:`);
console.log("  key                                   scoreable  top-1  shuffled  MRR     filtered top-1");
for (const [title, key] of [["label key as built", sameQ], ["neighbours from other diseases only", variant]]) {
  const g = grade(viewer, key);
  console.log(`  ${title.padEnd(38)} ${String(g.scoreable).padStart(6)}  ${pct(g.top1).padStart(6)}  ` +
    `${pct(chanceTop1(viewer, key)).padStart(6)}   ${g.mrr.toFixed(4)}  ${pct(g.filtered.top1).padStart(6)}`);
}
console.log("");
console.log("If the second row stays well above its shuffle, the ranking agrees with the");
console.log("label key beyond what shared indication explains.");
