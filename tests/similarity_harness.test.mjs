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
  payloadExists, loadPayload, loadViewer, labelledSet, grade, byClass,
  patchConstant, viewerSource, CONSTANTS, skippingListed,
} from "../analysis/similarity_harness/harness.mjs";

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
//
// Since D25 (2026-10-16) the floor grades with every listed_only entry left
// out of each ranked list (`skippingListed`). D25 entered 545 molecules from
// four public lists, none of which can carry an ATC N code, and as graded the
// ranking fell to 0.4343 / 30.3% while skipping them it rose to 0.4646 / 33.5%
// -- the D24 build graded 0.4601 / 32.7% the same way. A floor lowered for every
// list admitted would wear away to nothing; one that skips them still sees
// what they do to every target's prevalence.
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
  const g = grade(skippingListed(viewer), key);
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
