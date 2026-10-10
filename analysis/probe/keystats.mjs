// What the ATC answer key is actually made of, before asking whether it is a
// good judge. Read-only; adopts nothing.
import { loadPayload, labelledSet } from "../similarity_harness/harness.mjs";

const data = loadPayload();
const key = labelledSet(data);

const byL1 = new Map();
for (const [code, set] of key.members) {
  const l1 = code[0];
  if (!byL1.has(l1)) byL1.set(l1, { classes: 0, mols: new Set() });
  byL1.get(l1).classes++;
  for (const m of set) byL1.get(l1).mols.add(m);
}
console.log("ATC level-1 spread of the answer key:");
for (const [l1, v] of [...byL1].sort((a, b) => b[1].mols.size - a[1].mols.size)) {
  console.log(`  ${l1}  classes ${String(v.classes).padStart(3)}  molecules ${v.mols.size}`);
}
console.log("total labelled", key.labelled.length, "classes", key.members.size);

const sizes = [...key.members.values()].map((s) => s.size).sort((a, b) => a - b);
console.log("class sizes: min", sizes[0],
  "median", sizes[Math.floor(sizes.length / 2)], "max", sizes[sizes.length - 1]);
console.log("classes of exactly 2:", sizes.filter((s) => s === 2).length);
