// Directions a measured claim's row names (D28, 2026-11-11).
//
// What is locked in: where GtoPdb gives an action at a pair, or ChEMBL labels a
// functional assay's result there, the measured claims at that pair name the
// direction and its source instead of reading "no direction". It is display
// only: no tier, no line colour, no mechanism filter and no D15 opposition
// reads a functional-assay label (whether any of them should is open in
// docs/COHORT-2.md, D28).
//
// Run with: node --test tests/cohort_viewer_directions.test.mjs

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadViewer, buildData, buildGtopdb, withGtopdbFile, molecule, target, claim,
         endpoint, observation } from "./cohort_harness.mjs";

const D2 = { accession: "P14416", gene_symbol: "DRD2", description: "Dopamine D2 receptor" };

// Two molecules at one protein, each with a binding claim and a functional one;
// molecule 1's functional result is labelled ANTAGONIST in two studies,
// molecule 2's AGONIST in one.
function labelled() {
  const functional = (over) => claim(Object.assign({
    role: "functional", tier: "preliminary", tier_reason: "one_publication",
    multiple_study_support: 0, supporting_endpoint_class: null,
    endpoints: [endpoint({ endpoint_class: "functional:IC50", supported: 0 })],
  }, over));
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL1", name: "BLOCKER ONE" }),
      molecule({ id: 2, chembl_id: "CHEMBL2", name: "AGONIST TWO" }),
    ],
    targets: [target({ chembl_id: "T_D2", name: "Dopamine D2 receptor", components: [D2] })],
    claims: [
      claim({ id: 1, molecule: 1, target: "T_D2" }),
      functional({ id: 2, molecule: 1, target: "T_D2", assay_actions: [["ANTAGONIST", 2]] }),
      claim({ id: 3, molecule: 2, target: "T_D2" }),
      functional({ id: 4, molecule: 2, target: "T_D2", assay_actions: [["AGONIST", 1]] }),
    ],
  });
}

describe("a measured claim names the pair's direction and its source", () => {
  test("a functional-assay label is named on the binding and the functional row", () => {
    const v = loadViewer(labelled());
    const binding = v.allClaims().find((c) => c.id === 1);
    const functional = v.allClaims().find((c) => c.id === 2);
    for (const c of [binding, functional]) {
      assert.match(v.claimDetail(c),
        /direction<span class="help-text">[^<]+<\/span><\/span>: ANTAGONIST per ChEMBL&#39;s functional-assay label \(2 studies\)/);
    }
    assert.match(v.claimDetail(v.allClaims().find((c) => c.id === 3)), /AGONIST per ChEMBL&#39;s functional-assay label \(1 study\)/);
  });

  test("GtoPdb's action at the pair is named as GtoPdb's", () => {
    const data = withGtopdbFile(labelled(), buildGtopdb({ actions: [
      { molecule: 1, target: "T_D2", action_type: "ANTAGONIST", gtp_type: "Antagonist",
        gtp_action: "Antagonist", primary_target: 0, endogenous: 0, gtp_ligand_id: 1,
        gtp_target_id: 215 },
    ], claims: [], status: {}, release: "2026.3" }));
    const v = loadViewer(data);
    const detail = v.claimDetail(v.allClaims().find((c) => c.id === 1));
    assert.match(detail, /: ANTAGONIST per GtoPdb and ChEMBL&#39;s functional-assay label \(2 studies\)$/);
  });

  test("ChEMBL's own curated direction at the pair is named too, once per action", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1", name: "BLOCKER ONE" })],
      targets: [target({ chembl_id: "T_D2", name: "Dopamine D2 receptor", components: [D2] })],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_D2" }),
        claim({ id: 2, molecule: 1, target: "T_D2", role: "curated", action_type: "ANTAGONIST",
                tier_reason: "curated_support", curated_support: 1, multiple_study_support: 0,
                endpoints: [], supporting_endpoint_class: null }),
        claim({ id: 3, molecule: 1, target: "T_D2", role: "functional",
                assay_actions: [["ANTAGONIST", 1], ["INVERSE AGONIST", 1]] }),
      ],
    }));
    const detail = v.claimDetail(v.allClaims().find((c) => c.id === 1));
    assert.match(detail, /: ANTAGONIST per ChEMBL&#39;s curators and ChEMBL&#39;s functional-assay label \(1 study\); INVERSE AGONIST per ChEMBL&#39;s functional-assay label \(1 study\)$/);
  });

  test("the headings no longer say a measured group has no direction", () => {
    const v = loadViewer(labelled());
    v.setClaimGrouping("mechanism");
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /· measured affinity<\/span>/);
    assert.match(html, /· measured activity<\/span>/);
    assert.doesNotMatch(html, /measured (affinity|activity), no direction/);
  });

  test("a label in a layer the basis filter hides is not named", () => {
    const broader = loadViewer(buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1", name: "X" })],
      targets: [target({ chembl_id: "T_D2", components: [D2] })],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_D2" }),
        claim({ id: 2, molecule: 1, target: "T_D2", role: "functional", basis: "broader",
                assay_actions: [["AGONIST", 1]] }),
      ],
    }));
    broader.setFilter("basis", "human_direct");
    assert.equal(broader.measuredDirections(broader.allClaims()[0]).length, 0);
    broader.setFilter("basis", "all");
    assert.equal(broader.measuredDirections(broader.allClaims()[0]).length, 1);
  });
});

describe("a functional-assay label is shown, never counted", () => {
  test("it moves no tier, no line colour, no mechanism filter and no opposition", () => {
    const plain = loadViewer(labelled());
    const v = loadViewer(labelled());
    for (const c of v.allClaims()) {
      // claimActions is what the colour, the filter and D15 read.
      assert.equal(v.claimActions(c).length, 0);
      assert.equal(c.tier, plain.allClaims().find((p) => p.id === c.id).tier);
    }
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 0);       // ANTAGONIST against AGONIST, never compared
    assert.ok(!row.all_opposed);
  });

  test("a curated claim's row names no extra direction", () => {
    const v = loadViewer(labelled());
    const c = Object.assign({}, v.allClaims()[0], { role: "curated", action_type: "AGONIST" });
    assert.equal(v.measuredDirections(c).length, 0);
  });

  test("a measurement row names its functional-assay label", () => {
    const v = loadViewer(labelled());
    const html = v.observationRowHTML(observation({ assay_type: "F",
      assay_action_type: "ANTAGONIST" }), [{ study_key: "pmid:1", provenance_class: "publication" }]);
    assert.match(html, /ChEMBL&#39;s assay label<span class="help-text">[^<]+<\/span><\/span>: ANTAGONIST/);
    const none = v.observationRowHTML(observation(), [{ study_key: "pmid:1",
      provenance_class: "publication" }]);
    assert.doesNotMatch(none, /assay label/);
  });
});
