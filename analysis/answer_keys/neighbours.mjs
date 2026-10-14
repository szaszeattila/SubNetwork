// What the label key says, before it judges anything: each named molecule's
// nearest label neighbours and the effects behind them. Read-only.
//
//   node analysis/answer_keys/neighbours.mjs SERTRALINE HALOPERIDOL
//   node analysis/answer_keys/neighbours.mjs --key onsides-all MORPHINE
//
// It reads the key and never the ranking, so it can be run while a key is
// being checked and before it grades anything (docs/SIMILARITY-LITERATURE.md
// §4.1, a key fixed before use).

import { loadPayload, loadKey, KEYS } from "../similarity_harness/harness.mjs";

const argv = process.argv.slice(2);
const keyAt = argv.indexOf("--key");
const keyName = keyAt >= 0 ? argv[keyAt + 1] : "onsides";
const wanted = argv.filter((a, i) => !a.startsWith("--") && !(keyAt >= 0 && i === keyAt + 1));

const data = loadPayload();
const key = await loadKey(keyName, data);
const byName = new Map([...key.names].map(([id, n]) => [String(n).toUpperCase(), id]));

console.log(`${KEYS[keyName].title}${key.version ? ` (v${key.version})` : ""}`);
console.log(`${key.labelled.length} molecules asked; ` +
  `${new Set([...key.labelled].map((id) => key.ingredientOf.get(id))).size} distinct ingredients`);
for (const name of wanted) {
  const id = byName.get(name.toUpperCase());
  if (id === undefined || !key.profiles.has(id)) {
    console.log(`\n${name}: not in the key`);
    continue;
  }
  const peers = key.peersOf(id);
  console.log(`\n${name} (${key.profiles.get(id).size} effects in scope)`);
  console.log("  classmates: " + [...peers].map((p) => key.names.get(p)).join(", "));
  const half = data.molecules.map((r) => r[data.fields.molecules.indexOf("id")])
    .filter((m) => key.gain(id, peers, m) === 0.5);
  console.log("  half credit: " + half.map((p) => key.names.get(p)).join(", "));
}
