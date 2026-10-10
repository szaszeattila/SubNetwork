// Grade the same ranking against three answer keys, to ask what the grade is a
// fact about: the ranking, or the key.
//
//   N-only      what the harness grades today -- molecules.atc_level5, which
//               the build fills only for level1 = 'N'
//   all-ATC     every ATC level ChEMBL has for the same molecules
//   non-N-only  the classes the current key cannot see at all
//
// Nothing here changes the ranking. The same `sharedTargets` answers all three.
// Read-only; adopts nothing.

import { loadPayload, loadViewer, grade, pct, HarnessError } from "../similarity_harness/harness.mjs";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ATC_FULL = join(HERE, "atc_full.json");
if (!existsSync(ATC_FULL)) {
  console.error(`${ATC_FULL} is not there. Run:  python3 analysis/probe/dump_atc.py`);
  process.exit(2);
}

let data, viewer;
try {
  data = loadPayload();
  viewer = loadViewer(data);
} catch (err) {
  if (err instanceof HarnessError) { console.error(err.message); process.exit(2); }
  throw err;
}

const full = JSON.parse(readFileSync(ATC_FULL, "utf8"));
const F = data.fields.molecules;
const idI = F.indexOf("id"), nameI = F.indexOf("name"), chemI = F.indexOf("chembl_id");
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const nameOf = new Map(data.molecules.map((r) => [r[idI], str(r[nameI])]));

/**
 * The harness's own key shape, built over a chosen slice of ATC.
 *
 * The two rules that make the existing key fair are kept exactly: a fourth-
 * level `X` is "other", a group defined by NOT sharing a mechanism, and a class
 * of one cannot be got right or wrong.
 */
function keyOver(keep) {
  const classesOf = new Map(), members = new Map();
  for (const row of data.molecules) {
    const chembl = str(row[chemI]);
    const codes = full[chembl];
    if (!codes) continue;
    const id = row[idI];
    for (const code of codes) {
      const l4 = String(code).slice(0, 5);
      if (l4.length !== 5 || l4[4] === "X") continue;
      if (!keep(l4)) continue;
      if (!classesOf.has(id)) classesOf.set(id, new Set());
      classesOf.get(id).add(l4);
      if (!members.has(l4)) members.set(l4, new Set());
      members.get(l4).add(id);
    }
  }
  for (const [code, set] of [...members]) if (set.size < 2) members.delete(code);
  const labelled = [...classesOf.keys()]
    .filter((id) => [...classesOf.get(id)].some((c) => members.has(c)))
    .sort((a, b) => a - b);
  return {
    classesOf, members, labelled, names: nameOf,
    peersOf(id) {
      const out = new Set();
      for (const code of classesOf.get(id) || []) {
        if (!members.has(code)) continue;
        for (const other of members.get(code)) if (other !== id) out.add(other);
      }
      return out;
    },
  };
}

const keys = [
  ["ATC N only (what is graded today)", (c) => c[0] === "N"],
  ["every ATC level", () => true],
  ["non-N classes only", (c) => c[0] !== "N"],
];

console.log("The same ranking, graded against three answer keys");
console.log("=".repeat(78));
console.log("key".padEnd(36) + "mols  cls  scoreable  unans   top-1   top-5    MRR");
console.log("-".repeat(78));
const held = [];
for (const [label, keep] of keys) {
  const key = keyOver(keep);
  const g = grade(viewer, key);
  held.push([label, key, g]);
  console.log(
    label.padEnd(36) +
    String(key.labelled.length).padStart(4) +
    String(key.members.size).padStart(5) +
    String(g.scoreable).padStart(11) +
    String(g.unanswerable).padStart(7) +
    pct(g.top1).padStart(8) + pct(g.top5).padStart(8) +
    g.mrr.toFixed(4).padStart(8));
}

console.log("");
console.log("Per class, non-N, 4 or more members, worst first");
console.log("-".repeat(78));
const [, allKey] = held[1];
const rows = [];
for (const [code, set] of allKey.members) {
  if (code[0] === "N" || set.size < 4) continue;
  let scoreable = 0, hits = 0;
  for (const id of set) {
    const peers = allKey.peersOf(id);
    const list = viewer.sharedTargets(id);
    if (!list.some((r) => peers.has(r.molecule.id))) continue;
    scoreable++;
    if (list.length && peers.has(list[0].molecule.id)) hits++;
  }
  if (scoreable) rows.push({ code, members: set.size, scoreable, top1: hits / scoreable,
    names: [...set].map((i) => nameOf.get(i)) });
}
rows.sort((a, b) => a.top1 - b.top1 || a.code.localeCompare(b.code));
for (const r of rows) {
  console.log(`  ${r.code}  members ${String(r.members).padStart(2)}  ` +
    `scoreable ${String(r.scoreable).padStart(2)}  top-1 ${pct(r.top1).padStart(6)}   ` +
    r.names.slice(0, 4).join(", ").slice(0, 52));
}
