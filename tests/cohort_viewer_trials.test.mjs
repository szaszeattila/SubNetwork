// The trial-sites filter: which molecules' claims are in the picture, by where
// their Phase 1 or later in-scope trials had sites (2026-10-13, the user's
// "us only vs us + foreign vs foreign only"). The sites are computed by the
// export (scripts/cohort/export.py, trial_sites) and tested there; this holds
// what the page does with them.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadViewer, buildData, molecule, target, claim } from "./cohort_harness.mjs";

// One molecule per site class, each with one Supported claim at its own target.
function sited() {
  const mols = [
    [1, "CHEMBL_BOTH", "both", "Russia"],
    [2, "CHEMBL_US", "us", null],
    [3, "CHEMBL_ABROAD", "elsewhere", "Iran|Russia"],
    [4, "CHEMBL_UNSTATED", "unstated", null],
    [5, "CHEMBL_NONE", null, null],
  ];
  return buildData({
    molecules: mols.map(([id, cid, s, c]) => molecule({
      id, chembl_id: cid, name: cid, trial_sites: s, trial_countries: c })),
    targets: mols.map(([id]) => target({ chembl_id: "CHEMBLT" + id, name: "T" + id })),
    claims: mols.map(([id]) => claim({ id, molecule: id, target: "CHEMBLT" + id })),
  });
}

function shown(v) {
  return [...new Set(v.allClaims().filter((c) => v.claimVisible(c)).map((c) => c.molecule))]
    .sort();
}

describe("the trial-sites filter decides which molecules are in the picture", () => {
  test("at its default it moves nothing", () => {
    const v = loadViewer(sited());
    assert.equal(v.getFilters().trials, "any");
    assert.deepEqual(shown(v), [1, 2, 3, 4, 5]);
  });

  test("US sites keeps a molecule with any US-site trial", () => {
    const v = loadViewer(sited());
    v.setFilter("trials", "us");
    assert.deepEqual(shown(v), [1, 2]);
  });

  test("outside the US keeps a molecule with any non-US-site trial, US ones too", () => {
    // Which trials count, not which molecules were never trialled in the US:
    // a drug trialled in both has Phase 1 or later evidence from abroad.
    const v = loadViewer(sited());
    v.setFilter("trials", "elsewhere");
    assert.deepEqual(shown(v), [1, 3]);
  });

  test("anywhere keeps a trial with no listed site, and only drops no trial at all", () => {
    const v = loadViewer(sited());
    v.setFilter("trials", "anywhere");
    assert.deepEqual(shown(v), [1, 2, 3, 4]);
  });

  test("it is an eligibility rule, so it names itself as the reason and moves the layout", () => {
    const v = loadViewer(sited());
    const before = v.graphSignature();
    v.setFilter("trials", "us");
    assert.notEqual(v.graphSignature(), before);
    const hidden = v.allClaims().find((c) => c.molecule === 3);
    assert.equal(v.hiddenReason(hidden), "trials");
  });

  test("its banner is a cost, counted in molecules and split by why", () => {
    const v = loadViewer(sited());
    v.setFilter("trials", "us");
    const b = v.filterBanners().filter((x) => x.control === "trials");
    assert.equal(b.length, 1);
    assert.equal(b[0].kind, "cost");
    assert.match(b[0].text, /: 2 of 5\./);
    assert.match(b[0].text, /1 molecule with no such trial ChEMBL cites is hidden/);
    assert.match(b[0].text, /2 molecules whose trials list no US site/);
  });

  test("the control counts each setting and is offered only where sites are known", () => {
    const v = loadViewer(sited());
    const html = v.filtersHTML();
    assert.match(html, /Every molecule \(5\)/);
    assert.match(html, /US sites \(2\)/);
    assert.match(html, /Anywhere \(4\)/);
    assert.match(html, /Outside the US \(2\)/);
    assert.match(v.viewOptionsSettings(), /every molecule/);

    const bare = loadViewer(buildData({
      molecules: [molecule({ id: 1 })], targets: [target()], claims: [claim()] }));
    assert.doesNotMatch(bare.filtersHTML(), /Trial sites/);
    assert.doesNotMatch(bare.viewOptionsSettings(), /molecule/);
    // ...but a filter narrowed by a link can always be put back.
    bare.setFilter("trials", "us");
    assert.match(bare.filtersHTML(), /Trial sites/);
  });

  test("the indications note says where the trials ran and names the countries", () => {
    const v = loadViewer(sited());
    assert.equal(v.trialSitesSentence(v.lookupMolecule(3)),
      "Its Phase 1 or later trials had sites outside the US only: Iran, Russia.");
    assert.equal(v.trialSitesSentence(v.lookupMolecule(1)),
      "Its Phase 1 or later trials had sites in the US and elsewhere: Russia.");
    assert.equal(v.trialSitesSentence(v.lookupMolecule(2)),
      "Its Phase 1 or later trials had sites in the US only.");
    assert.equal(v.trialSitesSentence(v.lookupMolecule(5)), "");
  });

  test("a country name is escaped before it reaches the page (invariant 11)", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, trial_sites: "elsewhere", trial_countries: "<b>X</b>" })],
      targets: [target()], claims: [claim()] }));
    assert.doesNotMatch(v.trialSitesSentence(v.lookupMolecule(1)), /<b>/);
  });
});

describe("each trial names where it had sites, beside its id", () => {
  // 2026-10-15: trimipramine's indications said its trials ran in Germany,
  // and not which trial did.
  function page(trials) {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [["D1", "Depression", "Phase 3", "core", 1,
                          Object.keys(trials).join("|")]] },
      trial_status: trials,
    }));
    return v.showMolecule(v.lookupMolecule(1));
  }

  test("one country is named beside the id", () => {
    const html = page({ NCT02374567: ["COMPLETED", null, "PHASE3", null, 2015, 2017, null, "Germany"] });
    assert.match(html, /NCT02374567<\/a> <span class="trial-sites">\(Germany\)<\/span> <span class="muted">phase 3, 2015–2017<\/span>/);
  });

  test("the US comes first, past three the rest are counted and the list is the hover", () => {
    const html = page({ NCT00000001: ["COMPLETED", null, "PHASE3", null, null, null, null,
      "Canada|France|Germany|Poland|United States"] });
    assert.match(html, /title="5 countries: United States, Canada, France, Germany, Poland">\(United States, Canada, France \+2 more\)</);
  });

  test("a record listing no site says so; one fetched before sites says nothing", () => {
    const html = page({
      NCT00000001: ["COMPLETED", null, "PHASE2", null, 2001, 2005, null, null],
      NCT00000002: ["COMPLETED", null, "PHASE2", null, 2001, 2005],
    });
    assert.match(html, /NCT00000001<\/a> <span class="muted">\(no sites listed\)<\/span>/);
    assert.match(html, /NCT00000002<\/a> <span class="muted">phase 2, 2001–2005<\/span>/);
  });

  test("a country name is escaped (invariant 11)", () => {
    const html = page({ NCT00000001: ["COMPLETED", null, "PHASE2", null, null, null, null, "<b>"] });
    assert.match(html, /\(&lt;b&gt;\)/);
  });
});
