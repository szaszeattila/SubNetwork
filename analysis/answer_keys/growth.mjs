// What entering molecules the keys cannot label does to the keys. Read-only.
//
//   node analysis/answer_keys/growth.mjs
//
// D25-D27 entered 841 molecules because a public list names them
// (admission_reason "listed_only"). This separates what they did to each key
// into the questions they add and the competitors they put in every list, by
// reading the same build twice: as built, and with the listed entries taken
// out of each list (`skippingListed`, as the floor test grades). It reports:
//
// 1. how many of each key's questions are listed entries;
// 2. the pairwise key's three rates both ways, and how long the lists are;
// 3. hubness (how often a molecule is in another's top 10) both ways, and
//    whose lists the most frequent molecules appear in.
//
// docs/ANSWER-KEYS-REVIEW.md §6 reads the output. Nothing is adopted.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, loadPayload, loadViewer, loadKey, grade, pct, skippingListed }
  from "../similarity_harness/harness.mjs";

const data = loadPayload();
const F = data.fields.molecules;
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const idI = F.indexOf("id"), cI = F.indexOf("chembl_id"), nI = F.indexOf("name");
const aI = F.indexOf("admission_reason");
const listed = new Set(data.molecules.filter((r) => str(r[aI]) === "listed_only").map((r) => r[idI]));
const nameOf = new Map(data.molecules.map((r) => [r[idI], str(r[nI])]));
const byChembl = new Map(data.molecules.map((r) => [str(r[cI]), r[idI]]));
const built = loadViewer(data);
const skip = skippingListed(loadViewer(data));
const median = (xs) => {
  const s = [...xs].sort((x, y) => x - y);
  return s.length ? (s[(s.length - 1) >> 1] + s[s.length >> 1]) / 2 : null;
};

console.log("What the listed entries do to the keys");
console.log("=".repeat(74));
console.log(`${listed.size} of ${data.molecules.length} entries are listed (D25-D27).`);

console.log("");
console.log("1. Questions: how many each key asks, and how many of them are listed entries");
for (const k of ["atc", "atc-repaired", "mesh", "epc", "pe", "onsides", "onsides-all"]) {
  const key = await loadKey(k, data);
  const g = grade(built, key), gs = grade(skip, key);
  const mrr = (gr) => [...gr.ranks.values()].reduce((a, r) => a + 1 / r.rank, 0) / gr.ranks.size;
  const sc = [...g.ranks.keys()].filter((id) => listed.has(id)).length;
  // The old questions alone, with the listed entries out of their lists: the
  // same ranking among the same molecules as before they were entered.
  const old = [...gs.ranks].filter(([id]) => !listed.has(id));
  const oldMrr = old.reduce((a, [, r]) => a + 1 / r.rank, 0) / old.length;
  console.log(`  ${k.padEnd(13)} labelled ${String(key.labelled.length).padStart(4)} ` +
    `(${String(key.labelled.filter((id) => listed.has(id)).length).padStart(3)} listed); ` +
    `scoreable ${String(g.ranks.size).padStart(4)} (${String(sc).padStart(3)} listed), MRR ${mrr(g).toFixed(4)}; ` +
    `listed skipped: scoreable ${String(gs.ranks.size).padStart(4)}, MRR ${mrr(gs).toFixed(4)}; ` +
    `questions not listed, listed skipped: ${old.length}, MRR ${oldMrr.toFixed(4)}`);
}

console.log("");
console.log("2. The pairwise key, both directions of each pair");
const spec = JSON.parse(readFileSync(join(ROOT, "analysis", "answer_keys", "pairs.json"), "utf8"));
const K = spec.rules.top_k;
for (const [label, v] of [["as built", built], ["listed skipped", skip]]) {
  const res = { positive: [0, 0], negative: [0, 0], opposite: [0, 0] };
  for (const p of spec.pairs) {
    for (const [a, b] of [[p.a, p.b], [p.b, p.a]]) {
      const r = v.sharedTargets(byChembl.get(a)).findIndex((x) => x.molecule.id === byChembl.get(b)) + 1;
      const s = res[p.kind];
      s[0]++;
      if (p.kind === "positive" ? (r > 0 && r <= K) : (r === 0 || r > K)) s[1]++;
    }
  }
  console.log(`  ${label.padEnd(15)} positives within top ${K} ${pct(res.positive[1] / res.positive[0])}; ` +
    `negatives clean ${pct(res.negative[1] / res.negative[0])}; opposites clean ${pct(res.opposite[1] / res.opposite[0])}`);
}
for (const [label, v] of [["as built", built], ["listed skipped", skip]]) {
  const lens = data.molecules.map((r) => r[idI]).filter((id) => !listed.has(id))
    .map((id) => v.sharedTargets(id).length).filter((n) => n);
  console.log(`  list length, entries not listed, ${label}: median ${median(lens)}, ` +
    `mean ${(lens.reduce((a, b) => a + b, 0) / lens.length).toFixed(0)}`);
}

console.log("");
console.log("3. How often each molecule is in another's top 10 (* = listed)");
for (const [label, v, keep] of [["as built", built, () => true], ["listed skipped", skip, (id) => !listed.has(id)]]) {
  const ids = data.molecules.map((r) => r[idI]).filter(keep);
  const occ = new Map();
  for (const id of ids) {
    for (const x of v.sharedTargets(id).slice(0, 10)) occ.set(x.molecule.id, (occ.get(x.molecule.id) || 0) + 1);
  }
  const c = ids.map((id) => occ.get(id) || 0), n = c.length;
  const mu = c.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(c.reduce((a, x) => a + (x - mu) ** 2, 0) / n);
  const skew = c.reduce((a, x) => a + ((x - mu) / sd) ** 3, 0) / n;
  const tot = c.reduce((a, b) => a + b, 0);
  const top1 = [...c].sort((a, b) => b - a).slice(0, Math.ceil(n / 100)).reduce((a, b) => a + b, 0) / tot;
  const hubs = [...occ].sort((a, b) => b[1] - a[1]).slice(0, 10);
  console.log(`  ${label.padEnd(15)} skewness ${skew.toFixed(2)}; the top 1% fill ${pct(top1)} of top-10 places; ` +
    `most frequent ${hubs[0][1]}`);
  console.log("    " + hubs.map(([id, x]) => `${nameOf.get(id)}${listed.has(id) ? "*" : ""} ${x}`).join(", "));
}
const inListed = new Map(), inRest = new Map();
for (const r of data.molecules) {
  const m = listed.has(r[idI]) ? inListed : inRest;
  for (const x of built.sharedTargets(r[idI]).slice(0, 10)) m.set(x.molecule.id, (m.get(x.molecule.id) || 0) + 1);
}
const share = (m) => [...m].filter(([id]) => listed.has(id)).reduce((a, [, x]) => a + x, 0) /
  [...m.values()].reduce((a, b) => a + b, 0);
console.log(`  listed entries hold ${pct(share(inListed))} of the top-10 places in listed entries' lists, ` +
  `${pct(share(inRest))} in everyone else's`);
