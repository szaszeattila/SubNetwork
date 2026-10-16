// What the grades reward: how hard the pairwise key's questions are, how much
// the largest classes weigh, and how far a few molecules dominate the lists.
// Read-only.
//
//   node analysis/answer_keys/difficulty.mjs
//
// Three checks the literature on reference standards asks for:
//
// 1. A negative control is informative only if the method could plausibly
//    fail it (Hauben et al. 2016 on OMOP's negatives; Coloma et al. 2013 keep
//    only drugs a method can see). A known-unlike pair that shares no target
//    is absent from both lists and "clean" by construction. This counts how
//    much of each negative and opposite rate is that, and how many positives
//    are already classmates under the class keys, which they would duplicate.
// 2. A per-question mean lets a large class decide the grade. This sets each
//    class key's MRR averaged over questions beside the same averaged over
//    classes, each question in its first class with a classmate.
// 3. Hubness (Radovanovic et al. 2010): how often each molecule appears in
//    other molecules' top 10, and how skewed that is.

import { readFileSync } from "node:fs";
import { loadPayload, loadViewer, loadKey, grade, pct } from "../similarity_harness/harness.mjs";
import { PAIRS } from "./pairs.mjs";

const data = loadPayload();
const viewer = loadViewer(data);
const F = data.fields.molecules;
const idI = F.indexOf("id"), cI = F.indexOf("chembl_id"), nI = F.indexOf("name");
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const byChembl = new Map(data.molecules.map((r) => [str(r[cI]), r[idI]]));
const nameOf = new Map(data.molecules.map((r) => [r[idI], str(r[nI])]));
const lists = new Map();
const listOf = (id) => {
  if (!lists.has(id)) lists.set(id, viewer.sharedTargets(id).map((r) => r.molecule.id));
  return lists.get(id);
};

// 1. The pairwise key.
const spec = JSON.parse(readFileSync(PAIRS, "utf8"));
const K = spec.rules.top_k;
const classKeys = { "atc-repaired": await loadKey("atc-repaired", data), epc: await loadKey("epc", data),
                    mesh: await loadKey("mesh", data) };
console.log("What the grades reward");
console.log("=".repeat(74));
console.log(`1. The pairwise key v${spec.version}, both directions of each pair`);
for (const kind of ["negative", "opposite"]) {
  let asked = 0, absent = 0, reachClean = 0, reach = 0;
  for (const p of spec.pairs.filter((x) => x.kind === kind)) {
    for (const [q, m] of [[p.a, p.b], [p.b, p.a]]) {
      asked++;
      const r = listOf(byChembl.get(q)).indexOf(byChembl.get(m)) + 1;
      if (!r) { absent++; continue; }
      reach++;
      if (r > K) reachClean++;
    }
  }
  console.log(`  ${kind}s: ${asked} asked; ${absent} (${pct(absent / asked)}) share no target and are clean by ` +
    `construction; of the ${reach} that could fail, ${pct(reachClean / reach)} rank below ${K}`);
}
const pos = spec.pairs.filter((x) => x.kind === "positive");
for (const [name, key] of Object.entries(classKeys)) {
  const n = pos.filter((p) => key.peersOf(byChembl.get(p.a)).has(byChembl.get(p.b))).length;
  console.log(`  positives already ${name} classmates: ${n} of ${pos.length} (${pct(n / pos.length)})`);
}
const anyClass = pos.filter((p) => Object.values(classKeys).some((key) =>
  key.peersOf(byChembl.get(p.a)).has(byChembl.get(p.b)))).length;
console.log(`  positives a classmate under at least one of them: ${anyClass} of ${pos.length}`);

// 2. Questions against classes.
console.log("");
console.log("2. MRR over questions and over classes (each question in its first class)");
for (const name of ["atc", "atc-repaired", "mesh", "epc", "pe"]) {
  const key = name in classKeys ? classKeys[name] : await loadKey(name, data);
  const g = grade(viewer, key);
  const by = new Map();
  for (const [id, r] of g.ranks) {
    const c = [...key.classesOf.get(id)].filter((x) => key.members.has(x)).sort()[0];
    if (!by.has(c)) by.set(c, []);
    by.get(c).push(1 / r.rank);
  }
  const sizes = [...by.values()].map((v) => v.length).sort((a, b) => b - a);
  const top5 = sizes.slice(0, 5).reduce((a, b) => a + b, 0);
  const macro = [...by.values()].reduce((a, v) => a + v.reduce((x, y) => x + y, 0) / v.length, 0) / by.size;
  console.log(`  ${name.padEnd(13)} ${String(g.scoreable).padStart(4)} questions in ${String(by.size).padStart(3)} classes; ` +
    `largest five hold ${pct(top5 / g.scoreable).padStart(6)}; MRR ${g.mrr.toFixed(4)} by question, ` +
    `${macro.toFixed(4)} by class`);
}

// 3. Hubness.
console.log("");
console.log("3. How often each molecule is in another's top 10");
const occ = new Map();
let withList = 0;
for (const r of data.molecules) {
  const top = listOf(r[idI]).slice(0, 10);
  if (top.length) withList++;
  for (const m of top) occ.set(m, (occ.get(m) || 0) + 1);
}
const counts = data.molecules.map((r) => occ.get(r[idI]) || 0);
const n = counts.length, mu = counts.reduce((a, b) => a + b, 0) / n;
const sd = Math.sqrt(counts.reduce((a, c) => a + (c - mu) ** 2, 0) / n);
const skew = counts.reduce((a, c) => a + ((c - mu) / sd) ** 3, 0) / n;
const sorted = [...counts].sort((a, b) => b - a);
const top1pc = sorted.slice(0, Math.ceil(n / 100)).reduce((a, b) => a + b, 0) / counts.reduce((a, b) => a + b, 0);
console.log(`  ${withList} molecules have a list; mean appearances ${mu.toFixed(1)}, skewness ${skew.toFixed(2)}, ` +
  `never in a top 10: ${counts.filter((c) => !c).length}`);
console.log(`  the top 1% of molecules fill ${pct(top1pc)} of all top-10 places`);
const hubs = [...occ].sort((a, b) => b[1] - a[1]).slice(0, 10);
console.log("  most frequent: " + hubs.map(([m, c]) => `${nameOf.get(m)} ${c}`).join(", "));
