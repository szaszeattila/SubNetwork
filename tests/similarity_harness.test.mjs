// The similarity harness, held to a floor.
//
// A grade nothing enforces is a grade that gets admired once and then drifts,
// which is the failure the generated ## Status block exists to stop one level
// up. These tests do not assert that the ranking is *good* -- nothing here
// knows that. They assert that it has not quietly got worse, and that the
// instrument itself still works: an answer key that silently empties, or a
// constant patch that silently stops matching, would both report a healthy
// number while measuring nothing.
//
// The real payload is generated and gitignored, so every test that needs it
// skips when it is absent rather than failing. A fresh checkout has no build,
// and a suite that went red there would be reporting on the checkout rather
// than on the code.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  payloadExists, loadPayload, loadViewer, labelledSet, meshActionSet, grade, byClass,
  patchConstant, viewerSource, CONSTANTS, ndcgAt, atcRepairedKey, readDbClasses,
  DATABASE, ATC_REPAIRED, HarnessError, fdaKey, onsidesKey, labelProfiles, nearestByProfile,
  ONSIDES_KEY, KEYS,
} from "../analysis/similarity_harness/harness.mjs";
import { existsSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Measured on the chembl_37 build of 2026-09-16 at 0.4985 / 35.9%, and on the
// D21 build of 2026-10-12 at 0.4607 / 32.7% / top-5 61.3%. The floors sit a
// little under the latest: they are here to catch a regression, not to pin the
// third decimal of a number that moves whenever the catalogue is rebuilt.
//
// D21's fall is the answer key's, not the ranking's. It admitted 1,119
// molecules with no ATC N code, so one ranked above a class-mate is a miss
// however apt (adipiplon above a benzodiazepine, carfentanil above an opioid).
// With those 1,119 skipped in each list the same build grades 0.5121 / 38.7%,
// what it graded before them (docs/COHORT-2.md, D21).
const MRR_FLOOR = 0.44;
const TOP1_FLOOR = 0.31;
const TOP5_FLOOR = 0.58;

const has = payloadExists();
const skip = has ? false : "viz/graph.data.js is not built; run scripts/export_cohort.py";

let cached = null;
function fixture() {
  if (!cached) {
    const data = loadPayload();
    cached = { data, key: labelledSet(data), viewer: loadViewer(data) };
  }
  return cached;
}

test("the answer key is not empty, and holds no one-member classes", { skip }, () => {
  const { key } = fixture();
  assert.ok(key.labelled.length > 100,
    `answer key collapsed to ${key.labelled.length} molecules`);
  assert.ok(key.members.size > 20,
    `answer key collapsed to ${key.members.size} classes`);
  for (const [code, set] of key.members) {
    assert.ok(set.size >= 2, `${code} has ${set.size} member(s) and cannot be a question`);
  }
});

test("no 'other ...' class reaches the answer key", { skip }, () => {
  // An ATC level-4 X is a junk drawer -- N06AX is "other antidepressants",
  // a group defined by NOT sharing a mechanism. Grading against it would award
  // a point for calling mirtazapine and bupropion alike.
  const { key } = fixture();
  for (const code of key.members.keys()) {
    assert.notEqual(code[4], "X", `${code} is an "other ..." class`);
  }
});

test("the ranking clears its floor", { skip }, () => {
  const { viewer, key } = fixture();
  const g = grade(viewer, key);
  assert.ok(g.scoreable > 100, `only ${g.scoreable} molecules were scoreable`);
  assert.ok(g.mrr >= MRR_FLOOR,
    `MRR fell to ${g.mrr.toFixed(4)}, under the ${MRR_FLOOR} floor`);
  assert.ok(g.top1 >= TOP1_FLOOR,
    `top-1 fell to ${(g.top1 * 100).toFixed(1)}%, under ${TOP1_FLOOR * 100}%`);
  assert.ok(g.top5 >= TOP5_FLOOR,
    `top-5 fell to ${(g.top5 * 100).toFixed(1)}%, under ${TOP5_FLOOR * 100}%`);
});

test("coverage is counted apart from ordering", { skip }, () => {
  // The rates must be over the scoreable molecules alone. If unanswerable ones
  // were folded in, a constant that makes more claims eligible would raise the
  // grade without improving a single ranking.
  const { viewer, key } = fixture();
  const g = grade(viewer, key);
  assert.ok(g.unanswerable > 0, "expected some molecules to have no reachable peer");
  assert.equal(g.scoreable + g.unanswerable, key.labelled.length);
  assert.equal(g.ranks.size, g.scoreable);
  for (const [, r] of g.ranks) assert.ok(r.rank >= 1, "a recorded rank was not a rank");
});

test("every sweepable constant still matches the viewer's source", () => {
  // The guard that matters most, and the one test here that needs no build:
  // it reads viz/index.html, which is checked in. A renamed or reformatted
  // constant makes its patch a no-op, and a sweep would then print the
  // baseline under every label -- a table of numbers that agree because
  // nothing was ever varied.
  const source = viewerSource();
  for (const [name, spec] of Object.entries(CONSTANTS)) {
    assert.doesNotThrow(() => patchConstant(name, spec.current)(source),
      `${name} no longer matches anything in viz/index.html`);
    // And the patch must be able to write a different value, not just match.
    const changed = patchConstant(name, spec.current + 0.01)(source);
    assert.notEqual(changed, source, `${name} matched but wrote nothing`);
  }
});

test("patching a constant actually changes the grade", { skip }, () => {
  // End-to-end proof that the sweep path works: disabling the opposed-pair
  // demotion must move the number. If this passes while the sweep prints a
  // flat column, the patch is not reaching the code.
  const { data, key } = fixture();
  const base = grade(loadViewer(data), key);
  const off = grade(loadViewer(data, patchConstant("opposed_pair_factor", 1.0)), key);
  assert.notEqual(off.mrr.toFixed(4), base.mrr.toFixed(4),
    "OPPOSED_PAIR_FACTOR=1.0 graded identically to the default, so the patch " +
    "is probably not reaching sharedTargets");
  assert.ok(off.mrr < base.mrr,
    "disabling the opposed-pair demotion improved the grade, which would " +
    "reverse the measurement D15 rests on");
});

test("the per-class breakdown covers the classes it claims", { skip }, () => {
  const { viewer, key } = fixture();
  const rows = byClass(viewer, key, 5);
  assert.ok(rows.length > 5, "per-class breakdown is empty");
  for (const r of rows) {
    assert.ok(r.members >= 5);
    assert.ok(r.scoreable > 0 && r.scoreable <= r.members);
    assert.ok(r.top1 >= 0 && r.top1 <= 1);
  }
});

// ------------------------------------------------- the readings beside the grade

test("nDCG is computed against the ordering the list could have had", () => {
  // Needs no build. One classmate at rank 1 is perfect; at rank 2 it is
  // 1/log2(3); a sibling ahead of a classmate is better than nothing ahead of
  // it and worse than the classmate first.
  assert.equal(ndcgAt([1, 0, 0], 10), 1);
  assert.equal(ndcgAt([0, 1, 0], 10).toFixed(4), (1 / Math.log2(3)).toFixed(4));
  assert.equal(ndcgAt([0, 0, 0], 10), 0);
  const sib = ndcgAt([0.5, 1, 0], 10), none = ndcgAt([0, 1, 0], 10);
  assert.ok(sib > none && sib < 1, `sibling-first scored ${sib}`);
  // Past k nothing counts: a classmate at 11 of 11 is worth 0 at k = 10.
  assert.equal(ndcgAt([...Array(10).fill(0), 1], 10), 0);
});

test("the filtered walk only ever moves a classmate up", { skip }, () => {
  // Filtering removes molecules the key cannot judge and nothing else, so a
  // classmate can only rise. If any rate fell, the filter removed a classmate.
  const { viewer, key, data } = fixture();
  for (const k of [key, meshActionSet(data)]) {
    const g = grade(viewer, k);
    for (const m of ["top1", "top5", "top10", "mrr"]) {
      assert.ok(g.filtered[m] >= g[m], `${k.name}: filtered ${m} ${g.filtered[m]} < ${g[m]}`);
    }
    for (const v of [g.ndcg, g.filtered.ndcg]) assert.ok(v > 0 && v <= 1, `nDCG ${v}`);
  }
});

const hasDb = has && existsSync(DATABASE);
const skipDb = hasDb ? false : "db/cohort1.db or viz/graph.data.js is not built";

test("every exclusion in the repaired ATC key states its reason and version", () => {
  const spec = JSON.parse(readFileSync(ATC_REPAIRED, "utf8"));
  assert.match(spec.version, /^\d+\.\d+\.\d+$/);
  for (const group of ["excluded_level4", "excluded_level3"]) {
    for (const [code, why] of Object.entries(spec[group])) {
      assert.equal(code.length, group === "excluded_level4" ? 5 : 4, `${code} in ${group}`);
      assert.ok(typeof why === "string" && why.length > 10, `${code} has no reason`);
    }
  }
});

test("the repaired ATC key asks N questions and holds no excluded class", { skip: skipDb }, async () => {
  const { data } = fixture();
  const key = await atcRepairedKey(data);
  const spec = JSON.parse(readFileSync(ATC_REPAIRED, "utf8"));
  for (const code of key.members.keys()) {
    assert.notEqual(code[4], "X", `${code} is an "other ..." class`);
    assert.ok(!(code in spec.excluded_level4), `${code} is excluded but in the key`);
    assert.ok(key.members.get(code).size >= 2);
  }
  for (const id of key.labelled) {
    assert.ok([...key.classesOf.get(id)].some((c) => c[0] === "N" && key.members.has(c)),
      `question ${id} has no N class with a classmate`);
  }
  // Reading every level must reach peers the N-only key cannot see.
  const n = labelledSet(data);
  let wider = 0;
  for (const id of key.labelled) if (key.peersOf(id).size > n.peersOf(id).size) wider++;
  assert.ok(wider > 0, "no question gained a peer from a non-N class");
  // Gains: a classmate 1, a sibling only 0.5, anything else 0.
  for (const id of key.labelled.slice(0, 50)) {
    const peers = key.peersOf(id);
    for (const p of peers) assert.equal(key.gain(id, peers, p), 1);
  }
});

test("a database from another build is refused, not graded", { skip: skipDb }, async () => {
  const { data } = fixture();
  const stale = { ...data, meta: { ...data.meta, built_at: "1999-01-01T00:00:00" } };
  await assert.rejects(() => readDbClasses(stale, ["atc"]), HarnessError);
});

test("the FDA keys hold no class of one", { skip: skipDb }, async () => {
  const { data } = fixture();
  for (const which of ["epc", "pe"]) {
    let key;
    try { key = await fdaKey(data, which); } catch (err) {
      if (err instanceof HarnessError && /is empty/.test(err.message)) return;  // not backfilled
      throw err;
    }
    for (const [code, set] of key.members) assert.ok(set.size >= 2, `${which} ${code}`);
    for (const id of key.labelled) assert.ok(key.peersOf(id).size > 0);
    if (which === "pe") assert.equal(key.gain, undefined, "PE has no graded credit");
  }
});

test("a pharmacokinetic MoA earns no credit in the EPC key; a mechanism earns half", async () => {
  // Needs no build: a four-molecule database written here.
  const { DatabaseSync } = await import("node:sqlite");
  const dir = mkdtempSync(join(tmpdir(), "fdakey-"));
  const path = join(dir, "t.db");
  const db = new DatabaseSync(path);
  db.exec(`CREATE TABLE build_manifest (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE molecule_classes (parent_molregno INTEGER, source TEXT, code TEXT,
      subgroup TEXT, label TEXT, carriers TEXT);
    CREATE TABLE class_labels (source TEXT, code TEXT, level INTEGER, label TEXT, parents TEXT);
    INSERT INTO build_manifest VALUES ('built_at', 'T');`);
  const ins = db.prepare("INSERT INTO molecule_classes VALUES (?, ?, ?, '', ?, '')");
  ins.run(1, "fda_epc", "E1", "Serotonin Reuptake Inhibitor");
  ins.run(2, "fda_epc", "E1", "Serotonin Reuptake Inhibitor");
  ins.run(1, "fda_moa", "M1", "Cytochrome P450 2D6 Inhibitors");
  ins.run(3, "fda_moa", "M1", "Cytochrome P450 2D6 Inhibitors");
  ins.run(1, "fda_moa", "M2", "Serotonin Uptake Inhibitors");
  ins.run(4, "fda_moa", "M2", "Serotonin Uptake Inhibitors");
  db.close();
  const data = { meta: { built_at: "T" }, fields: { molecules: ["id", "name"] },
                 molecules: [[1, "a"], [2, "b"], [3, "c"], [4, "d"]] };
  try {
    const key = await fdaKey(data, "epc", { path });
    const peers = key.peersOf(1);
    assert.deepEqual([...peers], [2]);
    assert.equal(key.gain(1, peers, 2), 1);
    assert.equal(key.gain(1, peers, 3), 0, "credit through a CYP2D6-inhibitor MoA");
    assert.equal(key.gain(1, peers, 4), 0.5);
    assert.ok(!key.judged(3), "a molecule known only by a pharmacokinetic MoA is not judged");
    assert.ok(key.judged(4));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------- the label key

test("a label effect counts on two labels, or on a molecule's only label", () => {
  const labels = new Map([[1, 10], [2, 1]]);
  const socsOf = new Map([["NERV", new Set(["10029205"])], ["GUT", new Set(["10017947"])]]);
  const rows = [
    { parent_molregno: 1, effect: "NERV", n_labels: 2 },
    { parent_molregno: 1, effect: "GUT", n_labels: 9 },
    { parent_molregno: 1, effect: "ONE", n_labels: 1 },     // one odd label of ten
    { parent_molregno: 2, effect: "NERV", n_labels: 1 },    // its only label
  ];
  const all = labelProfiles(rows, labels, socsOf, null, 2);
  assert.deepEqual([...all.get(1)].sort(), ["GUT", "NERV"]);
  assert.deepEqual([...all.get(2)], ["NERV"]);
  const cns = labelProfiles(rows, labels, socsOf, new Set(["10029205", "10037175"]), 2);
  assert.deepEqual([...cns.get(1)], ["NERV"], "a GI effect is out of the nervous-system scope");
});

test("label neighbours: an effect on every profile weighs nothing, and ties at the cut are kept", () => {
  const profiles = new Map([
    ["a", new Set(["all", "x", "y"])],
    ["b", new Set(["all", "x", "y"])],
    ["c", new Set(["all", "x"])],
    ["d", new Set(["all", "y"])],
    ["e", new Set(["all", "z"])],
  ]);
  const n = nearestByProfile(profiles, 1, 3);
  assert.deepEqual([...n.get("a").peers], ["b"]);
  assert.deepEqual([...n.get("a").half].sort(), ["c", "d"], "c and d tie, and both are kept");
  // e shares only the effect every profile has: similarity zero, never a neighbour.
  assert.equal(n.get("e").peers.size, 0);
  assert.ok(![...n.get("a").peers, ...n.get("a").half].includes("e"));
});

test("one ingredient's molecules are never each other's neighbour or judged in each other's list", async () => {
  // Needs no build: a database and a key config written here.
  const { DatabaseSync } = await import("node:sqlite");
  const dir = mkdtempSync(join(tmpdir(), "labelkey-"));
  const path = join(dir, "t.db"), config = join(dir, "k.json");
  const spec = JSON.parse(readFileSync(ONSIDES_KEY, "utf8"));
  writeFileSync(config, JSON.stringify({ ...spec, min_effects: 1, peers: 1, half_credit_to: 2 }));
  const db = new DatabaseSync(path);
  db.exec(`CREATE TABLE build_manifest (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE label_effect_molecules (parent_molregno INTEGER, rxcui TEXT, n_labels INTEGER,
      labels_by_source TEXT);
    CREATE TABLE label_effects (parent_molregno INTEGER, effect TEXT, n_labels INTEGER, sections TEXT);
    CREATE TABLE label_effect_terms (term TEXT, term_type TEXT, name TEXT, effect TEXT,
      placement TEXT, socs TEXT);
    INSERT INTO build_manifest VALUES ('built_at', 'T');`);
  // 1 and 2 are a drug and its ester, one ingredient (A); 3 and 4 are others.
  const mol = db.prepare("INSERT INTO label_effect_molecules VALUES (?, ?, 2, 'US:2')");
  for (const [m, ing] of [[1, "A"], [2, "A"], [3, "B"], [4, "C"]]) mol.run(m, ing);
  const eff = db.prepare("INSERT INTO label_effects VALUES (?, ?, 2, 'AR')");
  // S is on every profile and weighs nothing; 4 shares nothing else.
  const prof = { 1: ["S", "T", "U"], 2: ["S", "T", "U"], 3: ["S", "T", "W"], 4: ["S", "V"] };
  for (const [m, es] of Object.entries(prof)) for (const e of es) eff.run(Number(m), e);
  const term = db.prepare("INSERT INTO label_effect_terms VALUES (?, 'PT', ?, ?, 'pt', '10029205')");
  for (const e of ["S", "T", "U", "V", "W"]) term.run(e, e, e);
  db.close();
  const data = { meta: { built_at: "T" }, fields: { molecules: ["id", "name"] },
                 molecules: [[1, "drug"], [2, "drug ester"], [3, "b"], [4, "c"]] };
  try {
    const key = await onsidesKey(data, "onsides", { path, config });
    assert.deepEqual([...key.peersOf(1)], [3], "the ester is not the drug's label neighbour");
    assert.deepEqual([...key.peersOf(3)].sort(), [1, 2], "an ingredient's molecules are peers together");
    assert.equal(key.judged(2, 1), false, "the ester is not judged in the drug's list");
    assert.equal(key.judged(2, 3), true);
    assert.equal(key.judged(2), true);
    assert.equal(key.gain(1, key.peersOf(1), 4), 0, "no shared effect but the universal one");
    assert.equal(key.members.size, 0, "a neighbour key has no classes");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

const hasLabels = hasDb && (() => {
  try {
    return readFileSync(DATABASE).includes("CREATE TABLE label_effects");
  } catch { return false; }
})();
test("the label keys ask hundreds of questions and never pair a molecule with its own ingredient",
  { skip: hasLabels ? false : "label_effects is not backfilled" }, async () => {
    const { data } = fixture();
    for (const which of ["onsides", "onsides-all"]) {
      const key = await onsidesKey(data, which);
      assert.ok(key.labelled.length > 200, `${which} asks only ${key.labelled.length}`);
      for (const id of key.labelled) {
        for (const p of key.peersOf(id)) {
          assert.notEqual(key.ingredientOf.get(p), key.ingredientOf.get(id), `${which} ${id} ${p}`);
        }
      }
    }
  });

test("the label keys are registered for --key and read their fixed config", () => {
  const spec = JSON.parse(readFileSync(ONSIDES_KEY, "utf8"));
  assert.ok(spec.version && spec.fixed, "a key states its version and when it was fixed");
  for (const k of ["min_labels", "min_effects", "peers", "half_credit_to"]) {
    assert.equal(typeof spec[k], "number", k);
    assert.ok(spec.why[k], `${k} states its reason`);
  }
  assert.ok(KEYS.onsides && KEYS["onsides-all"]);
});
