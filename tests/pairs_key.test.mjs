// The pre-registered pairwise key (analysis/answer_keys/pairs.mjs).
//
// What is held here is the instrument and the key's shape, never the grade:
// the key is held out, so no test pins what it says about the ranking. Every
// grading test runs against a stub ranking written below.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gradePairs, validate, PAIRS, KINDS } from "../analysis/answer_keys/pairs.mjs";
import { KEYS, loadKey, HarnessError, payloadExists, loadPayload } from
  "../analysis/similarity_harness/harness.mjs";

const spec = (pairs, extra = {}) => ({
  version: "t", frozen: "t", rules: { top_k: 2 },
  sources: { s: { kind: "doi", doi: "10.1/x" } }, pairs, ...extra,
});
const pair = (a, b, kind, more = {}) =>
  ({ a, a_name: a, b, b_name: b, kind, relation: "r", cites: [{ source: "s", says: "x" }], ...more });

test("a positive is a hit within top_k, and an absent partner is coverage, not a miss", () => {
  const ranks = { "A:B": 1, "B:A": 3, "A:C": 0, "C:A": 0 };
  const g = gradePairs(spec([pair("A", "B", "positive"), pair("A", "C", "positive")]),
    (q, m) => ranks[`${q}:${m}`]);
  const p = g.summary.positive;
  assert.equal(p.asked, 4);
  assert.equal(p.reachable, 2);
  assert.equal(p.rate, 0.5, "one of two reachable directions within top 2");
});

test("a negative or an opposite is clean below top_k or absent, and its rate is over all asked", () => {
  const ranks = { "A:N": 1, "N:A": 0, "A:O": 5, "O:A": 2 };
  const g = gradePairs(spec([pair("A", "N", "negative"), pair("A", "O", "opposite")]),
    (q, m) => ranks[`${q}:${m}`]);
  assert.equal(g.summary.negative.rate, 0.5);
  assert.equal(g.summary.opposite.rate, 0.5);
});

test("ordering: a positive above every negative is 1, an absent negative ranks last, a tie is half", () => {
  const pairs = [pair("Q", "P", "positive"), pair("Q", "N", "negative"), pair("Q", "M", "opposite")];
  const ranks = { "Q:P": 3, "Q:N": 0, "Q:M": 3, "P:Q": 0, "N:Q": 0, "M:Q": 0 };
  const g = gradePairs(spec(pairs), (q, m) => ranks[`${q}:${m}`]);
  // One list (Q's) has a reachable positive: P above absent N (1), tied with M (0.5).
  assert.equal(g.summary.ordering.lists, 1);
  assert.equal(g.summary.ordering.auc, 0.75);
});

test("a reading leaves pairs out by the filter it is given", () => {
  const pairs = [pair("A", "B", "positive"), pair("A", "C", "positive", { doubt: "why" })];
  const g = gradePairs(spec(pairs), () => 1, (p) => !p.doubt);
  assert.equal(g.summary.positive.asked, 2, "both directions of the one undoubted pair");
});

test("validation catches what would make a pair ungradeable or unsourced", () => {
  const cat = new Map([["A", "A"], ["B", "B"], ["C", "C"]]);
  assert.deepEqual(validate(spec([pair("A", "B", "positive")]), cat), []);
  const bad = validate(spec([
    pair("A", "B", "similar"),
    pair("B", "A", "negative"),
    pair("A", "Z", "positive"),
    { ...pair("A", "C", "opposite"), cites: [{ source: "nope", says: "x" }] },
    { ...pair("B", "C", "positive"), b_name: "D" },
  ]), cat);
  for (const want of ["kind similar", "listed twice", "Z is not in the catalogue",
                      "nope, which is not a source", "C is C, not D"]) {
    assert.ok(bad.some((x) => x.includes(want)), `no problem reported for: ${want}`);
  }
});

test("the key is held out: no sweep or --key can load it", async () => {
  assert.ok(!("pairs" in KEYS));
  await assert.rejects(() => loadKey("pairs", {}), HarnessError);
});

test("the committed key states its rules, provenance and a source for every pair", () => {
  const key = JSON.parse(readFileSync(PAIRS, "utf8"));
  assert.ok(key.version && key.frozen && key.rules.top_k && key.provenance);
  for (const kind of KINDS) {
    assert.ok(key.pairs.filter((p) => p.kind === kind).length >= 30, `too few ${kind} pairs`);
  }
  for (const s of Object.values(key.sources)) {
    assert.ok(s.kind === "doi" || s.kind === "label", "a source is a DOI or a label");
  }
  for (const p of key.pairs) {
    assert.equal(typeof p.seen, "boolean");
    assert.ok(p.cites.length && p.cites.every((c) => key.sources[c.source] && c.says));
  }
});

test("the committed key names only molecules the payload holds, by the payload's names",
  { skip: payloadExists() ? false : "viz/graph.data.js is not built" }, () => {
    const data = loadPayload();
    const F = data.fields.molecules;
    const str = (x) => (typeof x === "number" ? data.strings[x] : x);
    const cat = new Map(data.molecules.map((r) =>
      [str(r[F.indexOf("chembl_id")]), str(r[F.indexOf("name")])]));
    assert.deepEqual(validate(JSON.parse(readFileSync(PAIRS, "utf8")), cat), []);
  });
