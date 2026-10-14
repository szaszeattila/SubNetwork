// A molecule entered because a public list names it (D23) cites that list on
// its own panel and in About, and nowhere claims the listing is evidence.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadViewer, buildData, molecule } from "./cohort_harness.mjs";

function data({ admission = "listed_only", name = "Noopept", slug = "noopept" } = {}) {
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
      molecule({ id: 2, chembl_id: "CHEMBL4303687", name, in_cohort: 0,
                 route_atc_n: 0, admission_reason: admission,
                 exclusion_reason: "no ATC N code in family and no indication " +
                                   "inside the adopted scope",
                 listings: [{ source: "sciwiki", name, slug }] }),
    ],
  });
}

describe("a listed molecule (D23)", () => {
  test("its panel says which list entered it, linked to the compound's page", () => {
    const v = loadViewer(data());
    const html = v.showMolecule(v.lookupMolecule(2));
    assert.match(html, /Entered from/);
    assert.match(html, /href="https:\/\/www\.scientificsean\.wiki\/compounds\/noopept"[^>]*>Noopept<\/a>/);
    assert.match(html, /href="https:\/\/www\.scientificsean\.wiki\/"[^>]*>the sci-wiki<\/a>/);
  });

  test("the hover says a listing is not evidence and not an affiliation", () => {
    const v = loadViewer(data());
    const html = v.showMolecule(v.lookupMolecule(2));
    assert.match(html, /does not count toward similarity/);
    assert.match(html, /not affiliated/);
  });

  test("an entry no list names has no listing row", () => {
    const v = loadViewer(data());
    assert.doesNotMatch(v.showMolecule(v.lookupMolecule(1)), /Entered from|Also listed by/);
  });

  test("a listed molecule the clinical routes admit says 'also listed', not 'entered'", () => {
    const v = loadViewer(data({ admission: "route_indication" }));
    const html = v.showMolecule(v.lookupMolecule(2));
    assert.match(html, /Also listed by/);
    assert.doesNotMatch(html, /Entered from/);
  });

  test("the list's name and slug are escaped and encoded", () => {
    const v = loadViewer(data({ name: "<b>x</b>", slug: "a b/c" }));
    const html = v.showMolecule(v.lookupMolecule(2));
    assert.doesNotMatch(html, /<b>x<\/b>/);
    assert.match(html, /compounds\/a%20b%2Fc"/);
  });
});

describe("About credits the sci-wiki", () => {
  test("only when an entry was entered from it, with the count", () => {
    const h = loadViewer(data()).aboutSourcesHTML();
    assert.match(h, /The sci-wiki<\/a> \(Scientific Sean LLC\): 1 molecule is in the catalogue because its cognition and psychiatric compound lists name it,/);
    assert.match(h, /not affiliated with or endorsed by it/);
    assert.doesNotMatch(loadViewer(buildData({ molecules: [molecule({ id: 1 })] }))
      .aboutSourcesHTML(), /sci-wiki/);
  });

  test("not for a listed molecule the clinical routes admitted anyway", () => {
    const h = loadViewer(data({ admission: "both_routes" })).aboutSourcesHTML();
    assert.doesNotMatch(h, /sci-wiki/);
  });
});
