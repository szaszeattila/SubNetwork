// Whether an answer key can tell two settings of the score apart at all.
// Read-only, like the harness.
//
//   node analysis/answer_keys/power.mjs
//   node analysis/answer_keys/power.mjs --b 2000      # fewer resamples, faster
//
// SIMILARITY-HARNESS §15 sorts the scoring constants by the sign of an MRR
// change under five judges, and the changes are small: +0.0042, -0.0044,
// +0.0003. A sign is a finding only if the change is larger than the key's own
// sampling noise, and nothing measured that. This does, for the six settings
// in that table, the way information retrieval compares two systems over one
// set of questions (Smucker, Allan & Carterette 2007): per question, the
// reciprocal rank before and after; then
//
// - a paired bootstrap over questions, for a 95% interval on the MRR change;
// - for the class keys, the same bootstrap resampling whole classes, since a
//   constant moves a class's members together and a question-level bootstrap
//   treats them as independent (each question is put in its first class with
//   a classmate; the label key has no classes and gets the question level
//   only);
// - a sign-flip randomisation test of the mean change, and Holm's correction
//   across every cell, since 42 tests at 5% would find two by chance;
// - how many questions moved each way, which the aggregate hides.
//
// Nothing here is adopted and no constant is changed. It reports how large a
// change each key can see.

import { loadPayload, loadViewer, loadKey, grade, patchConstant } from "../similarity_harness/harness.mjs";

const argv = process.argv.slice(2);
const bAt = argv.indexOf("--b");
const B = bAt >= 0 ? Number(argv[bAt + 1]) : 10000;

const KEY_NAMES = ["atc", "atc-repaired", "mesh", "epc", "pe", "onsides", "onsides-all"];
const SETTINGS = [
  ["opposed_pair_factor", 1.0, "D15 off (OPPOSED_PAIR_FACTOR 1.0)"],
  ["evidence_curated", 1.0, "curated-only 0.75 -> 1.0"],
  ["evidence_multi", 0.75, "replicated-only 0.9 -> 0.75"],
  ["target_weight_broad", 1.0, "family weight 0.5 -> 1.0"],
  ["evidence_preliminary", 0.25, "Preliminary 0.5 -> 0.25"],
  ["species_exponent", 0.75, "SPECIES_EXPONENT 0.5 -> 0.75"],
];

// A seeded generator, so two runs print the same intervals.
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const quantile = (sorted, q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(q * sorted.length)))];

/** 95% interval of the mean of `groups` (arrays of deltas), resampling groups. */
function bootstrap(groups, rand) {
  const n = groups.length;
  const sums = groups.map((g) => g.reduce((a, b) => a + b, 0));
  const sizes = groups.map((g) => g.length);
  const out = new Float64Array(B);
  for (let b = 0; b < B; b++) {
    let s = 0, c = 0;
    for (let i = 0; i < n; i++) {
      const j = Math.floor(rand() * n);
      s += sums[j]; c += sizes[j];
    }
    out[b] = s / c;
  }
  const sorted = Array.from(out).sort((a, b) => a - b);
  return [quantile(sorted, 0.025), quantile(sorted, 0.975)];
}

/** Two-sided sign-flip randomisation p-value for the mean of paired deltas. */
function signFlip(deltas, rand) {
  const obs = Math.abs(mean(deltas));
  if (obs === 0) return 1;
  let hit = 0;
  for (let b = 0; b < B; b++) {
    let s = 0;
    for (const d of deltas) s += rand() < 0.5 ? d : -d;
    if (Math.abs(s / deltas.length) >= obs - 1e-15) hit++;
  }
  return (hit + 1) / (B + 1);
}

/** Each question's first class that has a classmate, or null for the label key. */
function clusterOf(key, id) {
  const cs = [...(key.classesOf.get(id) || [])].filter((c) => key.members.has(c)).sort();
  return cs.length ? cs[0] : null;
}

const rr = (g) => new Map([...g.ranks].map(([id, r]) => [id, 1 / r.rank]));

async function main() {
  const data = loadPayload();
  const keys = {};
  for (const k of KEY_NAMES) keys[k] = await loadKey(k, data);
  const base = loadViewer(data);
  const baseRR = {};
  for (const k of KEY_NAMES) baseRR[k] = rr(grade(base, keys[k]));

  console.log(`Can each key see the sweep's changes? Paired over questions, B = ${B}`);
  console.log("=".repeat(100));
  console.log("Baseline MRR with a 95% bootstrap interval over questions:");
  const rand0 = mulberry32(1);
  for (const k of KEY_NAMES) {
    const v = [...baseRR[k].values()];
    const [lo, hi] = bootstrap(v.map((x) => [x]), rand0);
    console.log(`  ${k.padEnd(13)} n ${String(v.length).padStart(4)}   MRR ${mean(v).toFixed(4)}` +
      `   [${lo.toFixed(4)}, ${hi.toFixed(4)}]   half-width ${((hi - lo) / 2).toFixed(4)}`);
  }

  const cells = [];
  for (const [name, value, label] of SETTINGS) {
    const viewer = loadViewer(data, patchConstant(name, value));
    for (const k of KEY_NAMES) {
      const after = rr(grade(viewer, keys[k]));
      const ids = [...baseRR[k].keys()];
      if (ids.length !== after.size || ids.some((id) => !after.has(id))) {
        throw new Error(`${label} under ${k}: the scoreable set moved; the deltas would not be paired`);
      }
      const deltas = ids.map((id) => after.get(id) - baseRR[k].get(id));
      const rand = mulberry32(7);
      const ci = bootstrap(deltas.map((d) => [d]), rand);
      let ciClass = null;
      if (keys[k].members.size) {
        const by = new Map();
        ids.forEach((id, i) => {
          const c = clusterOf(keys[k], id) ?? `self:${id}`;
          if (!by.has(c)) by.set(c, []);
          by.get(c).push(deltas[i]);
        });
        ciClass = bootstrap([...by.values()], rand);
      }
      cells.push({
        label, key: k, n: deltas.length, delta: mean(deltas), ci, ciClass,
        sd: Math.sqrt(deltas.reduce((a, d) => a + (d - mean(deltas)) ** 2, 0) / (deltas.length - 1)),
        up: deltas.filter((d) => d > 0).length, down: deltas.filter((d) => d < 0).length,
        p: signFlip(deltas, rand),
      });
    }
  }

  // Holm: sort by p, compare the i-th smallest with alpha / (m - i), stop at
  // the first that fails.
  const m = cells.length;
  const order = [...cells].sort((a, b) => a.p - b.p);
  let stillRejecting = true;
  order.forEach((c, i) => {
    stillRejecting = stillRejecting && c.p <= 0.05 / (m - i);
    c.holm = stillRejecting;
  });

  for (const [, , label] of SETTINGS) {
    console.log("");
    console.log(label);
    console.log("-".repeat(100));
    console.log("  key              n    dMRR   95% (questions)      95% (classes)      better worse      p  Holm");
    for (const c of cells.filter((x) => x.label === label)) {
      const f = (x) => (x >= 0 ? "+" : "") + x.toFixed(4);
      const iv = (r) => (r ? `[${f(r[0])}, ${f(r[1])}]` : "-").padEnd(19);
      console.log(`  ${c.key.padEnd(13)} ${String(c.n).padStart(4)}  ${f(c.delta)}  ${iv(c.ci)} ${iv(c.ciClass)}` +
        `${String(c.up).padStart(6)} ${String(c.down).padStart(5)}  ${c.p.toFixed(4)}  ${c.holm ? "yes" : "no"}`);
    }
  }

  // The smallest paired change each key could detect at 5% with 80% power,
  // from the spread of per-question changes under the five small settings
  // (D15 off moves more questions further, so it is left out). With the
  // normal approximation this is (1.96 + 0.84) * sd / sqrt(n); and the
  // questions needed to detect a change of 0.004 are 7.84 * (sd / 0.004)^2
  // (Sakai's topic-set-size design).
  console.log("");
  console.log("Smallest change each key can detect (5%, 80% power), from the per-question");
  console.log("spread under the five settings other than D15:");
  for (const k of KEY_NAMES) {
    const sds = cells.filter((c) => c.key === k && !c.label.startsWith("D15")).map((c) => c.sd).sort((a, b) => a - b);
    const sd = sds[Math.floor(sds.length / 2)];
    const n = cells.find((c) => c.key === k).n;
    console.log(`  ${k.padEnd(13)} median sd ${sd.toFixed(4)}   detectable ${(2.8 * sd / Math.sqrt(n)).toFixed(4)}` +
      `   questions needed for 0.004: ${Math.round(7.84 * (sd / 0.004) ** 2)}`);
  }

  console.log("");
  const sig = cells.filter((c) => c.holm);
  console.log(`${sig.length} of ${m} cells survive Holm's correction at 5%.`);
  const excl = cells.filter((c) => c.ci[0] > 0 || c.ci[1] < 0);
  console.log(`${excl.length} of ${m} have a question-level interval that excludes zero;`);
  console.log(`${cells.filter((c) => c.ciClass && (c.ciClass[0] > 0 || c.ciClass[1] < 0)).length} of ` +
    `${cells.filter((c) => c.ciClass).length} class-key cells still do when whole classes are resampled.`);
}

main();
