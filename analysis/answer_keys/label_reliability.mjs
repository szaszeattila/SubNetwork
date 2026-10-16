// How far the label key agrees with itself: its noise ceiling. Read-only.
//
//   node analysis/answer_keys/label_reliability.mjs
//
// A key with noise in it caps the grade any ranking can reach against it. The
// representational-similarity literature estimates that cap from the data's
// own reliability (Nili et al. 2014): measure the same thing twice and see how
// well one measurement predicts the other. The label key allows exactly that.
// Most ingredients with a profile have labels from more than one regulator, so
// label_halves.py builds each profile twice under the key's own rules, once
// from the US labels and once from the UK, EU and Japanese ones, and this
// script asks:
//
// 1. how many of an ingredient's five nearest label neighbours by one half are
//    among its five by the other half;
// 2. graded the way the harness grades (walk to the first classmate), how well
//    one half's similarity list scores against the other half's neighbours,
//    beside how well the target ranking scores against the same half, on the
//    same questions, over the same candidates.
//
// The second is the ceiling reading: a second regulator's labels are as good a
// predictor of the key as anything that is not the key itself. Read it with
// one caution: the halves differ in how much OnSIDES reads from them (Japanese
// labels yield a dozen times the effects of a US repackager's), so their
// disagreement mixes the key's noise with a difference between regulators.

import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { readFileSync } from "node:fs";
import { ROOT, loadPayload, loadViewer, nearestByProfile, pct } from "../similarity_harness/harness.mjs";

const spec = JSON.parse(readFileSync(join(ROOT, "analysis", "similarity_harness", "onsides_key.json"), "utf8"));
const halves = JSON.parse(execFileSync("python3",
  [join(ROOT, "analysis", "answer_keys", "label_halves.py")], { maxBuffer: 1 << 28 }).toString());

/** Every other unit by IDF-weighted cosine, highest first, the key's formula. */
function similarityLists(profiles) {
  const units = [...profiles.keys()];
  const df = new Map();
  for (const s of profiles.values()) for (const e of s) df.set(e, (df.get(e) || 0) + 1);
  const idf = new Map([...df].map(([e, n]) => [e, Math.log(units.length / n)]));
  const norm = new Map([...profiles].map(([u, s]) =>
    [u, Math.sqrt([...s].reduce((a, e) => a + idf.get(e) ** 2, 0))]));
  const out = new Map();
  for (const [u, s] of profiles) {
    const sims = [];
    for (const [v, t] of profiles) {
      if (v === u) continue;
      let d = 0;
      for (const e of s) if (t.has(e)) d += idf.get(e) ** 2;
      const c = norm.get(u) && norm.get(v) ? d / (norm.get(u) * norm.get(v)) : 0;
      if (c > 0) sims.push([v, c]);
    }
    sims.sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
    out.set(u, sims.map(([v]) => v));
  }
  return out;
}

function walk(list, peers) {
  const i = list.findIndex((x) => peers.has(x));
  return i < 0 ? 0 : i + 1;
}

const data = loadPayload();
const viewer = loadViewer(data);
const F = data.fields.molecules;
const idI = F.indexOf("id");
const inPayload = new Set(data.molecules.map((r) => r[idI]));
const ingOf = new Map();
for (const [m, rx] of Object.entries(halves.molecules)) if (inPayload.has(Number(m))) ingOf.set(Number(m), rx);
const questionOf = new Map();
for (const [m, rx] of ingOf) if (!questionOf.has(rx) || m < questionOf.get(rx)) questionOf.set(rx, m);

console.log("The label key against itself: US labels against UK, EU and Japanese labels");
console.log("=".repeat(78));
for (const scope of Object.keys(spec.scopes)) {
  const P = {};
  for (const h of ["us", "rest"]) {
    P[h] = new Map(Object.entries(halves.profiles[scope][h])
      .filter(([rx, es]) => es.length >= spec.min_effects && questionOf.has(rx))
      .map(([rx, es]) => [rx, new Set(es)]));
  }
  const common = [...P.us.keys()].filter((rx) => P.rest.has(rx)).sort();
  const C = new Set(common);
  for (const h of ["us", "rest"]) for (const rx of [...P[h].keys()]) if (!C.has(rx)) P[h].delete(rx);
  const N = { us: nearestByProfile(P.us, spec.peers, spec.half_credit_to),
              rest: nearestByProfile(P.rest, spec.peers, spec.half_credit_to) };
  const L = { us: similarityLists(P.us), rest: similarityLists(P.rest) };

  // 1. Neighbour overlap.
  let overlap = 0, n1 = 0;
  for (const rx of common) {
    const a = N.us.get(rx).peers, b = N.rest.get(rx).peers;
    if (!a.size || !b.size) continue;
    let k = 0;
    for (const x of a) if (b.has(x)) k++;
    overlap += k / Math.min(a.size, b.size);
    n1++;
  }
  console.log(`\n${scope}: ${common.length} ingredients with ${spec.min_effects}+ effects in both halves`);
  console.log(`  five nearest neighbours shared between the halves: ${pct(overlap / n1)} ` +
    `(chance ${pct(spec.peers / (common.length - 1))})`);

  // 2. Graded like the harness, on questions both the other half and the
  //    target ranking can answer, over the common candidates only.
  for (const [pred, judge] of [["us", "rest"], ["rest", "us"]]) {
    const r = { label: { t1: 0, mrr: 0 }, target: { t1: 0, mrr: 0 }, n: 0 };
    for (const rx of common) {
      const peers = N[judge].get(rx).peers;
      if (!peers.size) continue;
      const seen = new Set([rx]), tlist = [];
      for (const row of viewer.sharedTargets(questionOf.get(rx))) {
        const other = ingOf.get(row.molecule.id);
        if (!other || !C.has(other) || seen.has(other)) continue;
        seen.add(other);
        tlist.push(other);
      }
      const rt = walk(tlist, peers), rl = walk(L[pred].get(rx), peers);
      if (!rt || !rl) continue;
      r.n++;
      if (rl === 1) r.label.t1++;
      if (rt === 1) r.target.t1++;
      r.label.mrr += 1 / rl;
      r.target.mrr += 1 / rt;
    }
    console.log(`  judged by the ${judge === "us" ? "US" : "non-US"} half, ${r.n} questions both can answer:`);
    console.log(`    the ${pred === "us" ? "US" : "non-US"} half's own list   top-1 ${pct(r.label.t1 / r.n).padStart(6)}` +
      `   MRR ${(r.label.mrr / r.n).toFixed(4)}`);
    console.log(`    the target ranking         top-1 ${pct(r.target.t1 / r.n).padStart(6)}` +
      `   MRR ${(r.target.mrr / r.n).toFixed(4)}`);
  }
}
console.log("\nThe first row of each pair is the ceiling reading: the same key read off");
console.log("another regulator's labels. The target ranking is graded over the same");
console.log("candidates (molecules with a profile in both halves), filtered as the harness");
console.log("filters, so the two rows are comparable with each other and not with Status.");
