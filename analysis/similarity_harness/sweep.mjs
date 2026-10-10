// Sweep the scoring constants, one at a time, and report what each is worth.
//
//   node analysis/similarity_harness/sweep.mjs
//   node analysis/similarity_harness/sweep.mjs evidence_curated
//   node analysis/similarity_harness/sweep.mjs evidence_curated --movers
//   node analysis/similarity_harness/sweep.mjs --key mesh    # MeSH actions as the judge
//
// One at a time is deliberate. A joint optimisation over six constants against
// a 217-molecule proxy would fit the proxy, and the answer would be six numbers
// nobody could defend for any reason except that the search found them -- which
// is the position this harness exists to get out of, reached from the other
// side.
//
// `--movers` is the part that carries the argument. An aggregate hides whether
// a gain is broad or is three molecules moving a long way, and a change that
// helps 42 and hurts 24 is a different proposition from one that helps 42 and
// hurts nobody, however the means compare.

import { loadPayload, loadViewer, labelledSet, meshActionSet, grade, patchConstant,
         CONSTANTS, pct, HarnessError } from "./harness.mjs";

const argv = process.argv.slice(2);
const showMovers = argv.includes("--movers");
const keyAt = argv.indexOf("--key");
const keyName = keyAt >= 0 ? argv[keyAt + 1] : "atc";
const only = argv.filter((a, i) => !a.startsWith("--") && !(keyAt >= 0 && i === keyAt + 1));

function main() {
  const data = loadPayload();
  if (keyName !== "atc" && keyName !== "mesh") {
    throw new HarnessError(`unknown --key ${keyName}; use atc or mesh.`);
  }
  const key = keyName === "mesh" ? meshActionSet(data) : labelledSet(data);

  const base = grade(loadViewer(data), key);
  console.log("Sweeping against the current build, judged by " +
              (keyName === "mesh" ? "MeSH pharmacological actions" : "ATC level-4 classes"));
  console.log("=".repeat(72));
  console.log(`baseline   scoreable ${base.scoreable}   top-1 ${pct(base.top1)}   ` +
              `top-5 ${pct(base.top5)}   MRR ${base.mrr.toFixed(4)}`);
  console.log("");

  const names = only.length ? only : Object.keys(CONSTANTS);
  for (const name of names) {
    const spec = CONSTANTS[name];
    if (!spec) throw new HarnessError(`no such constant: ${name}`);
    console.log(spec.label + `  (currently ${spec.current})`);
    console.log("-".repeat(72));

    let flat = true;
    for (const value of spec.grid) {
      const g = grade(loadViewer(data, patchConstant(name, value)), key);
      const d = g.mrr - base.mrr;
      const mark = value === spec.current ? " <- current" : "";
      // Scoreable is printed only when it moves. It should not: these weights
      // reorder a list rather than decide what is on it. If one of them ever
      // changes the count, the grade is no longer comparing like with like and
      // saying so is more useful than the rate it would otherwise print.
      const cov = g.scoreable === base.scoreable ? "" : `   [scoreable ${g.scoreable}!]`;
      console.log(`  ${String(value).padEnd(6)} top-1 ${pct(g.top1).padStart(6)}   ` +
                  `top-5 ${pct(g.top5).padStart(6)}   MRR ${g.mrr.toFixed(4)}   ` +
                  `${d >= 0 ? "+" : ""}${d.toFixed(4)}${mark}${cov}`);
      if (Math.abs(d) > 0.002) flat = false;

      if (showMovers && value !== spec.current) {
        let up = 0, down = 0;
        const moved = [];
        for (const [id, before] of base.ranks) {
          const after = g.ranks.get(id);
          if (!after || after.rank === before.rank) continue;
          if (after.rank < before.rank) up++; else down++;
          moved.push({ name: key.names.get(id), from: before.rank, to: after.rank });
        }
        moved.sort((a, b) => (a.to - a.from) - (b.to - b.from));
        console.log(`         improved ${up}, worsened ${down}, unchanged ` +
                    `${base.ranks.size - up - down}`);
        for (const m of moved.slice(0, 4)) {
          console.log(`           ${m.name}: ${m.from} -> ${m.to}`);
        }
        if (moved.length > 8) console.log("           ...");
        for (const m of moved.slice(-4)) {
          console.log(`           ${m.name}: ${m.from} -> ${m.to}`);
        }
      }
    }
    if (flat) {
      console.log("  (flat: no value on this grid moves MRR by more than 0.002,");
      console.log("   so the ranking cannot tell these settings apart)");
    }
    console.log("");
  }

  console.log("A gain here is a gain against a proxy that is partly defined by");
  console.log("mechanism. Before adopting one, check it against the molecules it");
  console.log("moved, and read the caveat at the foot of evaluate.mjs.");
}

try {
  main();
} catch (err) {
  if (err instanceof HarnessError) {
    console.error("similarity harness: " + err.message);
    process.exit(2);
  }
  throw err;
}
