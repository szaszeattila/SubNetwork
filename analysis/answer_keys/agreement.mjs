// How often two answer keys agree with each other, before either judges the
// ranking. Read-only, like the harness it borrows its keys from.
//
//   node analysis/answer_keys/agreement.mjs
//   node analysis/answer_keys/agreement.mjs atc-repaired mesh
//
// docs/SIMILARITY-LITERATURE.md §5 asks for this in step 1: two judges that
// disagree about most pairs cannot both be measuring "acts alike", and the
// share of one key's classmate pairs the other accepts is the most any ranking
// could score under both at once.
//
// For each pair of keys the universe is the molecules both of them judge -
// a molecule one key has no class for says nothing about the other - and a
// classmate pair is two of those molecules sharing a class in that key.

import { loadPayload, loadKey, KEYS, pct } from "../similarity_harness/harness.mjs";

const names = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const chosen = names.length ? names : Object.keys(KEYS);

function classmatePairs(key, universe) {
  const pairs = new Set();
  for (const id of universe) {
    for (const other of key.peersOf(id)) {
      if (other > id && universe.has(other)) pairs.add(`${id}:${other}`);
    }
  }
  return pairs;
}

const data = loadPayload();
const keys = [];
for (const name of chosen) keys.push(await loadKey(name, data));
const ids = data.molecules.map((r) => r[data.fields.molecules.indexOf("id")]);

console.log("Agreement between answer keys, over the molecules both judge");
console.log("=".repeat(70));
console.log("A, B".padEnd(26) + "both judge  A pairs  B pairs  shared  B accepts A  A accepts B");
for (let i = 0; i < keys.length; i++) {
  for (let j = i + 1; j < keys.length; j++) {
    const a = keys[i], b = keys[j];
    const universe = new Set(ids.filter((id) => a.judged(id) && b.judged(id)));
    const pa = classmatePairs(a, universe), pb = classmatePairs(b, universe);
    let shared = 0;
    for (const p of pa) if (pb.has(p)) shared++;
    console.log(
      `${a.name}, ${b.name}`.padEnd(26) +
      String(universe.size).padStart(10) + String(pa.size).padStart(9) +
      String(pb.size).padStart(9) + String(shared).padStart(8) +
      (pa.size ? pct(shared / pa.size) : "-").padStart(13) +
      (pb.size ? pct(shared / pb.size) : "-").padStart(13));
  }
}
console.log("");
console.log("'B accepts A' is the share of A's classmate pairs that B also calls");
console.log("classmates. Low in both directions means the two keys are asking");
console.log("different questions, and a constant that pleases one may not please");
console.log("the other for reasons that have nothing to do with the ranking.");
