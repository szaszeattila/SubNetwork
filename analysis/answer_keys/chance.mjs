// What each answer key's grade would be if the ranking were a shuffle, and
// how the label key's grade moves with the size of a molecule's profile.
// Read-only, like the harness.
//
//   node analysis/answer_keys/chance.mjs
//   node analysis/answer_keys/chance.mjs onsides epc
//
// The grade's denominator is the questions with a classmate somewhere in the
// list, so a key whose classmates are many, or whose lists are short, is
// easier to score under. The chance figure is the same lists in random order:
// for a list of L molecules holding K classmates, top-1 is K / L and the
// expected reciprocal rank of the first classmate is
// sum over r of C(L - r, K - 1) / C(L, K) / r. A key's grade means something
// only as its distance from that.

import { loadPayload, loadViewer, loadKey, KEYS, grade, pct } from "../similarity_harness/harness.mjs";

function chance(viewer, key) {
  let n = 0, top1 = 0, mrr = 0;
  for (const id of key.labelled) {
    const peers = key.peersOf(id);
    const ids = viewer.sharedTargets(id).map((r) => r.molecule.id);
    const L = ids.length, K = ids.filter((m) => peers.has(m)).length;
    if (!K) continue;
    n++;
    top1 += K / L;
    // P(first classmate at r) = C(L-r, K-1) / C(L, K), as a running product.
    let p = K / L, s = p;
    for (let r = 2; r <= L - K + 1; r++) {
      p *= (L - r - K + 2) / (L - r + 1);
      s += p / r;
    }
    mrr += s;
  }
  return { n, top1: top1 / n, mrr: mrr / n };
}

const names = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const data = loadPayload();
const viewer = loadViewer(data);
console.log("Each key's grade beside the same lists shuffled");
console.log("=".repeat(66));
console.log("key".padEnd(14) + "scoreable   top-1  chance     MRR  chance");
for (const name of names.length ? names : Object.keys(KEYS)) {
  const key = await loadKey(name, data);
  const g = grade(viewer, key), c = chance(viewer, key);
  console.log(name.padEnd(14) + String(g.scoreable).padStart(9) +
    pct(g.top1).padStart(8) + pct(c.top1).padStart(8) +
    g.mrr.toFixed(4).padStart(8) + c.mrr.toFixed(4).padStart(8));
}

for (const name of ["onsides", "onsides-all"]) {
  if (names.length && !names.includes(name)) continue;
  const key = await loadKey(name, data);
  const sizes = key.labelled.map((id) => key.profiles.get(id).size).sort((a, b) => a - b);
  const cuts = [sizes[Math.floor(sizes.length / 3)], sizes[Math.floor((2 * sizes.length) / 3)]];
  console.log("");
  console.log(`${name}: by effects in a question's profile (tertiles at ${cuts.join(" and ")})`);
  for (const [lo, hi] of [[0, cuts[0]], [cuts[0], cuts[1]], [cuts[1], Infinity]]) {
    const sub = { ...key, labelled: key.labelled.filter((id) => {
      const s = key.profiles.get(id).size;
      return s >= lo && s < hi;
    }) };
    const g = grade(viewer, sub), c = chance(viewer, sub);
    console.log(`  ${String(lo).padStart(3)}-${hi === Infinity ? "   " : String(hi - 1).padEnd(3)}` +
      `  scoreable ${String(g.scoreable).padStart(3)}  top-1 ${pct(g.top1).padStart(6)} ` +
      `(chance ${pct(c.top1)})  MRR ${g.mrr.toFixed(4)} (chance ${c.mrr.toFixed(4)})` +
      `  filtered top-1 ${pct(g.filtered.top1)}`);
  }
}
