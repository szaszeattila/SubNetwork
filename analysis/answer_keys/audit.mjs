// What the ATC answer key calls a miss, and whether it is one.
//
// Read-only, like the harness it borrows from: it calls the page's own
// `sharedTargets` through `loadViewer`, reads `viz/graph.data.js` and
// `viz/gtopdb.data.js`, and opens `db/cohort1.db` read-only for nothing but the
// ATC class names, which the payload no longer carries. It adopts nothing.
// The numbers it prints are the ones docs/SIMILARITY-LITERATURE.md quotes.
//
//   node analysis/answer_keys/audit.mjs            # the summary
//   node analysis/answer_keys/audit.mjs --misses   # every top-1 miss, classified
//   node analysis/answer_keys/audit.mjs --classes  # every class, with its name
//
// A top-1 miss is put in the first of these that holds, in this order:
//
//   sibling   the top answer shares the query's ATC level 3 (N05A, N06A): a
//             level-4 split the key draws inside one drug group, often by
//             chemical structure (N05AA aliphatic vs N05AC piperidine
//             phenothiazines), so the ranking named a pharmacological relative
//             and the key called it wrong
//   mesh      the top answer shares a MeSH pharmacological action with the
//             query (depth 5 or deeper, as `meshActionSet` reads them): a second
//             judge from outside ChEMBL calls it right
//   unlabelled the top answer carries no N code with a classmate, so the ATC
//             key has no opinion of it at all - not evidence either way
//   other     none of those: the miss the key and MeSH agree on

import {
  loadPayload, loadViewer, labelledSet, meshActionSet, payloadExists, ROOT, pct,
} from "../similarity_harness/harness.mjs";
import { existsSync } from "node:fs";
import { join } from "node:path";

if (!payloadExists()) {
  console.error("viz/graph.data.js is not there; run python3 scripts/export_cohort.py first.");
  process.exit(2);
}

const args = new Set(process.argv.slice(2));
const data = loadPayload();
const viewer = loadViewer(data);
const atc = labelledSet(data);
const mesh = meshActionSet(data);

// ATC names, if the database is to hand. Without it the codes still print.
const atcName = new Map();
const dbPath = join(ROOT, "db", "cohort1.db");
if (existsSync(dbPath)) {
  const { DatabaseSync } = await import("node:sqlite");
  const db = new DatabaseSync(dbPath, { readOnly: true });
  for (const r of db.prepare(
    "SELECT code, label FROM class_labels WHERE source = 'atc'").all()) {
    atcName.set(r.code, r.label);
  }
  db.close();
}
const nameOf = (code) => atcName.get(code) || "";

const level3 = (id) => new Set([...(atc.classesOf.get(id) || [])].map((c) => c.slice(0, 4)));
const shareMesh = (a, b) => {
  const x = mesh.classesOf.get(a), y = mesh.classesOf.get(b);
  if (!x || !y) return false;
  for (const c of x) if (y.has(c) && mesh.members.has(c)) return true;
  return false;
};
const hasClassmateCode = (id) =>
  [...(atc.classesOf.get(id) || [])].some((c) => atc.members.has(c));

// A shared row is curated on a side when any claim there carries curated
// support - a ChEMBL mechanism or a GtoPdb primary target.
const curatedBothSides = (s) =>
  s.mine.some((c) => c.curated_support) && s.theirs.some((c) => c.curated_support);

// The filtered grade: the same walk down the same list, but past only the
// molecules the key can judge - those carrying an N code with a classmate. It
// is the "filtered" setting of link-prediction evaluation: a candidate the key
// has no opinion about is neither right nor wrong, so it is not allowed to
// stand between a query and its classmate. It never changes the ranking.
let fScore = 0, fTop1 = 0, fMrr = 0;

const counts = { scoreable: 0, unanswerable: 0, hit: 0, sibling: 0, mesh: 0, unlabelled: 0, other: 0 };
let hitsLedByCurated = 0;
const misses = [];
const perClass = new Map();

for (const id of atc.labelled) {
  const peers = atc.peersOf(id);
  if (!peers.size) continue;
  const rows = viewer.sharedTargets(id);
  const rank = rows.findIndex((r) => peers.has(r.molecule.id)) + 1;
  for (const code of atc.classesOf.get(id)) {
    if (!atc.members.has(code)) continue;
    if (!perClass.has(code)) perClass.set(code, { members: atc.members.get(code).size, scoreable: 0, hit: 0 });
  }
  if (!rank) { counts.unanswerable++; continue; }
  counts.scoreable++;
  const judged = rows.filter((r) => hasClassmateCode(r.molecule.id));
  const fRank = judged.findIndex((r) => peers.has(r.molecule.id)) + 1;
  fScore++; fMrr += 1 / fRank; if (fRank === 1) fTop1++;
  for (const code of atc.classesOf.get(id)) {
    const pc = perClass.get(code);
    if (!pc) continue;
    pc.scoreable++;
    if (rank === 1) pc.hit++;
  }
  if (rank === 1) {
    counts.hit++;
    // Is the target doing most of the work on the winning pair one that both
    // molecules have a curated mechanism at? That is the circularity: the key
    // and the score reading the same curation.
    const lead = rows[0].shared.find((s) => s.contribution > 0);
    if (lead && curatedBothSides(lead)) hitsLedByCurated++;
    continue;
  }
  const top = rows[0].molecule;
  let kind;
  const mine3 = level3(id);
  if ([...level3(top.id)].some((c) => mine3.has(c))) kind = "sibling";
  else if (shareMesh(id, top.id)) kind = "mesh";
  else if (!hasClassmateCode(top.id)) kind = "unlabelled";
  else kind = "other";
  counts[kind]++;
  misses.push({ name: atc.names.get(id), rank, top: top.name, kind,
                codes: [...atc.classesOf.get(id)].join("|"),
                topCodes: [...(atc.classesOf.get(top.id) || [])].join("|") || "-" });
}

const misses1 = counts.scoreable - counts.hit;
console.log("What the ATC key calls a top-1 miss");
console.log("=".repeat(62));
console.log(`answer key   ${atc.labelled.length} molecules in ${atc.members.size} classes`);
console.log(`scoreable    ${counts.scoreable}   unanswerable ${counts.unanswerable}`);
console.log(`top-1 hits   ${counts.hit} (${pct(counts.hit / counts.scoreable)})`);
console.log(`  led by a target both sides have a curated mechanism at: ${hitsLedByCurated} of ${counts.hit} (${pct(hitsLedByCurated / counts.hit)})`);
console.log(`top-1 misses ${misses1}`);
for (const k of ["sibling", "mesh", "unlabelled", "other"]) {
  console.log(`  ${k.padEnd(11)} ${String(counts[k]).padStart(4)}  (${pct(counts[k] / misses1)})`);
}
const lenient = counts.hit + counts.sibling + counts.mesh;
console.log(`top-1 if a sibling or MeSH-agreed answer counted: ${pct(lenient / counts.scoreable)}`);
console.log(`filtered (ranked among judged molecules only): top-1 ${pct(fTop1 / fScore)}  MRR ${(fMrr / fScore).toFixed(4)}`);

if (args.has("--misses")) {
  console.log("\nEvery top-1 miss");
  console.log("-".repeat(62));
  misses.sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name));
  for (const m of misses) {
    console.log(`  ${m.kind.padEnd(10)} ${m.name.padEnd(28)} ${m.codes.padEnd(12)} rank ${String(m.rank).padStart(3)}  top ${m.top} (${m.topCodes})`);
  }
}

if (args.has("--classes")) {
  console.log("\nEvery class in the key");
  console.log("-".repeat(62));
  for (const [code, pc] of [...perClass].sort((a, b) => a[0].localeCompare(b[0]))) {
    const t1 = pc.scoreable ? pct(pc.hit / pc.scoreable) : "-";
    console.log(`  ${code}  ${String(pc.members).padStart(3)} members  ${String(pc.scoreable).padStart(3)} scoreable  top-1 ${t1.padStart(6)}  ${nameOf(code)}`);
  }
}
