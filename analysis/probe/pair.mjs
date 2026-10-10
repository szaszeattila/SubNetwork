// One pair, everything the score and D15 saw in it.
//   node analysis/probe/pair.mjs MORPHINE NALTREXONE
import { loadPayload, loadViewer } from "../similarity_harness/harness.mjs";

const [aName, bName] = process.argv.slice(2);
const data = loadPayload();
const viewer = loadViewer(data);
const F = data.fields.molecules;
const idI = F.indexOf("id"), nameI = F.indexOf("name");
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const byName = new Map();
for (const row of data.molecules) {
  byName.set(String(str(row[nameI]) || "").toUpperCase(), row[idI]);
}
const a = byName.get(String(aName).toUpperCase());
const b = byName.get(String(bName).toUpperCase());
if (a === undefined || b === undefined) {
  console.error("not in catalogue:", a === undefined ? aName : bName);
  process.exit(2);
}
const rows = viewer.sharedTargets(a);
const rank = rows.findIndex((r) => r.molecule.id === b) + 1;
const row = rows[rank - 1];
if (!row) { console.log(`${bName} is nowhere in ${aName}'s list`); process.exit(0); }

console.log(`${aName} -> ${bName}: rank ${rank} of ${rows.length}, score ${row.score.toFixed(4)}`);
console.log(`shared ${row.n_shared}  exact ${row.n_exact}  broad ${row.n_broad}  ` +
  `subsumed ${row.n_subsumed}  comparable ${row.n_comparable}  opposed ${row.n_opposed}  ` +
  `all_opposed ${row.all_opposed}`);
console.log("");
const tn = (t) => {
  const syms = (t.components || []).map((c) => c.gene_symbol).filter(Boolean);
  return t.target_type === "SINGLE PROTEIN" && syms.length === 1 ? syms[0] : t.name;
};
const acts = (cs) => {
  const out = [...new Set(cs.map((c) => c.action_type).filter(Boolean))];
  return out.length ? out.join("/") : "-";
};
for (const s of row.shared) {
  console.log(
    `  ${tn(s.target).padEnd(38).slice(0, 38)} ${String(s.target.target_type).padEnd(21)} ` +
    `${String(s.target.organism || "").slice(0, 18).padEnd(19)} ` +
    `A:${acts(s.mine).padEnd(12)} B:${acts(s.theirs).padEnd(12)} ` +
    `${s.subsumed ? "subsumed " : ""}${s.direction ? (s.direction.opposed ? "OPPOSED" : "comparable") : "no direction"}`);
}
