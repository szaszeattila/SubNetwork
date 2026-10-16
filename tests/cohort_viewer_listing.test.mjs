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
    assert.match(h, /The sci-wiki<\/a> \(Scientific Sean LLC\): 1 molecule is in the catalogue because its cognition, psychiatric and psychedelics compound lists name it and none of the open lists above does,/);
    assert.match(h, /not affiliated with or endorsed by any of these lists/);
    assert.doesNotMatch(loadViewer(buildData({ molecules: [molecule({ id: 1 })] }))
      .aboutSourcesHTML(), /sci-wiki|not affiliated/);
  });

  test("not for a listed molecule the clinical routes admitted anyway", () => {
    const h = loadViewer(data({ admission: "both_routes" })).aboutSourcesHTML();
    assert.doesNotMatch(h, /sci-wiki/);
  });
});

// D25: Wikipedia, Wikidata, TripSit and PsychonautWiki, each cited as its
// terms ask, and the open lists named before the sci-wiki.
function openData() {
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
      molecule({ id: 2, chembl_id: "CHEMBL127202", name: "2C-G", in_cohort: 0,
                 route_atc_n: 0, admission_reason: "listed_only",
                 listings: [
                   { source: "tripsit", name: "2C-G", slug: "2c-g" },
                   { source: "wikipedia", name: "2C-G", slug: "2C-G" },
                   { source: "psychonautwiki", name: "2C-G", slug: "2C-G" },
                 ] }),
      molecule({ id: 3, chembl_id: "CHEMBL3", name: "X", in_cohort: 0,
                 route_atc_n: 0, admission_reason: "listed_only",
                 listings: [{ source: "wikidata", name: "x", slug: "Q42" }] }),
    ],
  });
}

describe("a molecule an open list entered (D25)", () => {
  test("its panel links each list's own page, the open lists in a fixed order", () => {
    const v = loadViewer(openData());
    const html = v.showMolecule(v.lookupMolecule(2));
    assert.match(html, /href="https:\/\/en\.wikipedia\.org\/wiki\/2C-G"/);
    assert.match(html, /href="https:\/\/psychonautwiki\.org\/wiki\/2C-G"/);
    assert.match(html, /href="https:\/\/tripsit\.me\/factsheets\/2c-g"/);
    const at = (s) => html.indexOf(s);
    assert.ok(at(">Wikipedia<") < at(">PsychonautWiki<"));
    assert.ok(at(">PsychonautWiki<") < at(">TripSit<"));
    const w = v.showMolecule(v.lookupMolecule(3));
    assert.match(w, /href="https:\/\/www\.wikidata\.org\/wiki\/Q42"/);
  });

  test("TripSit is named as the source on the panel showing its listing", () => {
    const v = loadViewer(openData());
    assert.match(v.showMolecule(v.lookupMolecule(2)),
                 /Entered from.*>TripSit<\/a>, as <a [^>]*>2C-G<\/a>/s);
  });

  test("About credits each list with its count and licence or terms", () => {
    const h = loadViewer(openData()).aboutSourcesHTML();
    assert.match(h, />Wikipedia<\/a>: 1 molecule is in the catalogue because an English Wikipedia article on it/);
    assert.match(h, /Article text <a [^>]*creativecommons\.org\/licenses\/by-sa\/4\.0/);
    assert.match(h, />Wikidata<\/a>: 1 molecule is in the catalogue because its item gives it/);
    assert.match(h, />PsychonautWiki<\/a>: 1 molecule .*creativecommons\.org\/licenses\/by\/4\.0/);
    assert.match(h, />TripSit's factsheets<\/a>: 1 molecule .*non-commercial use as <a href="https:\/\/wiki\.tripsit\.me\/wiki\/Factsheets"/);
    assert.doesNotMatch(h, /sci-wiki/);
  });
});
