// Grade the current similarity ranking. Read-only; changes nothing.
//
//   node analysis/similarity_harness/evaluate.mjs
//   node analysis/similarity_harness/evaluate.mjs --json
//   node analysis/similarity_harness/evaluate.mjs --misses 20
//   node analysis/similarity_harness/evaluate.mjs --key mesh   # MeSH actions as the judge
//   node analysis/similarity_harness/evaluate.mjs --skip-listed  # listed entries out of each list
//
// The per-class table below the headline is the part worth reading. A class at
// 0% is either a ranking failure or a label that was never a fair question, and
// the aggregate cannot tell you which -- only the name of the class can.

import { loadPayload, loadViewer, labelledSet, meshActionSet, grade, byClass, pct,
  HarnessError, skippingListed } from "./harness.mjs";

const argv = process.argv.slice(2);
const asJson = argv.includes("--json");
const missArg = argv.indexOf("--misses");
const missLimit = missArg >= 0 ? Number(argv[missArg + 1]) : 12;
const keyArg = argv.indexOf("--key");
const keyName = keyArg >= 0 ? argv[keyArg + 1] : "atc";

function main() {
  const data = loadPayload();
  if (keyName !== "atc" && keyName !== "mesh") {
    throw new HarnessError(`unknown --key ${keyName}; use atc or mesh.`);
  }
  const key = keyName === "mesh" ? meshActionSet(data) : labelledSet(data);
  const viewer = argv.includes("--skip-listed") ? skippingListed(loadViewer(data)) : loadViewer(data);
  const started = Date.now();
  const g = grade(viewer, key);
  const elapsed = Date.now() - started;

  if (asJson) {
    // The shape scripts/cohort/status.py reads. Rates are fractions, not
    // percentages, so the caller decides how to round them.
    process.stdout.write(JSON.stringify({
      labelled: key.labelled.length, classes: key.members.size,
      scoreable: g.scoreable, unanswerable: g.unanswerable,
      top1: g.top1, top5: g.top5, top10: g.top10, mrr: g.mrr,
    }) + "\n");
    return;
  }

  console.log(keyName === "mesh"
    ? "Similarity ranking, graded against MeSH pharmacological actions"
    : "Similarity ranking, graded against ATC level-4 classes");
  console.log("=".repeat(62));
  console.log(`answer key   ${key.labelled.length} molecules in ${key.members.size} classes`);
  console.log(`scoreable    ${g.scoreable}`);
  console.log(`unanswerable ${g.unanswerable}  (no same-class peer anywhere in the list;`);
  console.log(`                  a fact about ChEMBL's coverage, not about the ranking)`);
  console.log("");
  console.log(`top-1        ${pct(g.top1)}`);
  console.log(`top-5        ${pct(g.top5)}`);
  console.log(`top-10       ${pct(g.top10)}`);
  console.log(`MRR          ${g.mrr.toFixed(4)}`);
  console.log(`graded in    ${elapsed} ms`);

  const misses = [...g.ranks.entries()]
    .filter(([, r]) => r.rank > 10)
    .sort((a, b) => b[1].rank - a[1].rank);
  console.log("");
  console.log(`Worst ranked (${misses.length} beyond rank 10)`);
  console.log("-".repeat(62));
  for (const [id, r] of misses.slice(0, missLimit)) {
    const peers = [...key.peersOf(id)].map((p) => key.names.get(p)).slice(0, 3);
    console.log(`  ${String(key.names.get(id)).padEnd(20)} rank ${String(r.rank).padStart(3)}/${String(r.listed).padEnd(4)} ` +
                `top=${String(r.top).slice(0, 18).padEnd(18)} peers=${peers.join(", ")}`);
  }

  console.log("");
  console.log("Per class (5 or more members)");
  console.log("-".repeat(62));
  for (const row of byClass(viewer, key)) {
    const label = key.labelOf ? " " + key.labelOf(row.code).slice(0, 34).padEnd(34) : "";
    console.log(`  ${row.code}${label}  members ${String(row.members).padStart(2)}  ` +
                `scoreable ${String(row.scoreable).padStart(2)}  top-1 ${pct(row.top1)}`);
  }

  console.log("");
  if (keyName === "mesh") {
    console.log("Read with the bias stated: MeSH actions come from the literature,");
    console.log("not from ChEMBL, and are linked through PubChem. Many are");
    console.log("mechanisms (\"Serotonin Uptake Inhibitors\"), so they reward the");
    console.log("same thing the ranking measures; others are uses (\"Analgesics\").");
    console.log("A second proxy, not ground truth.");
  } else {
    console.log("Read with the bias stated: ATC classes are partly defined by");
    console.log("mechanism, and ChEMBL curates mechanism most thoroughly for");
    console.log("well-known drugs, so this metric flatters any weighting term");
    console.log("that rewards curation. It is a proxy, not ground truth.");
  }
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
