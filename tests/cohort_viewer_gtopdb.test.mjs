// GtoPdb's curated actions in the viewer (scripts/resolve_cohort_gtopdb_actions.py).
//
// What is locked in: a GtoPdb action is a direction and nothing else. It is
// read where the pair has a claim the filters show and nowhere else, it lands
// in the same per-protein set ChEMBL's curated actions do - so one molecule's
// two curators disagreeing is treated as ChEMBL disagreeing with itself - and
// every sentence about an opposition names which curator it came from. All of
// it arrives in gtopdb.data.js, its own file for its own licence, built here
// the way scripts/cohort/export.py writes it (buildGtopdb): declared fields,
// positional rows, the file's own interned strings.
//
// Run with: node --test tests/cohort_viewer_gtopdb.test.mjs

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadViewer, buildData, buildGtopdb, withGtopdbFile, molecule, target, claim }
  from "./cohort_harness.mjs";

function withGtopdb(data, actions, { release = "2026.3", claims = [], status = {},
                                     generated = undefined } = {}) {
  return withGtopdbFile(data, buildGtopdb({ actions, claims, status, release, generated }));
}

const MU = { accession: "P35372", gene_symbol: "OPRM1", description: "Mu-type opioid receptor" };
const KAPPA = { accession: "P41145", gene_symbol: "OPRK1", description: "Kappa-type opioid receptor" };

function curated(over) {
  return claim(Object.assign({
    role: "curated", tier_reason: "curated_support", curated_support: 1,
    multiple_study_support: 0, n_measurements: 0, n_studies: 0, n_publications: 0,
    supporting_endpoint_class: null, endpoints: [],
  }, over));
}

// Two molecules measured at one protein, with no ChEMBL direction on either.
function measuredOnly() {
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL70", name: "MORPHINE" }),
      molecule({ id: 2, chembl_id: "CHEMBL1200657", name: "NALTREXONE" }),
    ],
    targets: [target({ chembl_id: "T_MU", name: "Mu opioid receptor", components: [MU] })],
    claims: [
      claim({ id: 1, molecule: 1, target: "T_MU" }),
      claim({ id: 2, molecule: 2, target: "T_MU" }),
    ],
  });
}

const gtp = (over) => Object.assign({
  primary_target: 1, endogenous: 0, gtp_target_id: 319, pubmed_ids: "9686407",
}, over);

describe("GtoPdb directions", () => {
  test("give a direction where ChEMBL gives none, and an opposite pair is quartered", () => {
    const plain = loadViewer(measuredOnly()).sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(plain.n_comparable, 0);
    const v = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 1, target: "T_MU", action_type: "AGONIST", gtp_type: "Agonist",
            gtp_action: "Full agonist", gtp_ligand_id: 1627 }),
      gtp({ molecule: 2, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist",
            gtp_action: "Antagonist", gtp_ligand_id: 1639 }),
    ]));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 1);
    assert.equal(row.all_opposed, true);
    assert.ok(Math.abs(row.score - plain.score * 0.25) < 1e-9);
    assert.equal(row.direction_curators, "GtoPdb");
    // The sentence names the curator that actually supplied the directions.
    assert.match(v.oppositionNote(row), /^GtoPdb curates these two in opposite directions/);
    const pair = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    // The curator beside the action, the species on the target.
    assert.match(pair, /MORPHINE AGONIST \(GtoPdb\) at Mu opioid receptor \(human\)/);
    assert.match(pair, /Where the opposite direction comes from/);
    assert.doesNotMatch(pair, /curated on two different records/);
  });

  test("never change the structure of the score, only the direction factor", () => {
    const base = loadViewer(measuredOnly()).sharedTargets(1).find((r) => r.molecule.id === 2);
    const row = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 1, target: "T_MU", action_type: "AGONIST", gtp_type: "Agonist", gtp_action: "Agonist" }),
    ])).sharedTargets(1).find((r) => r.molecule.id === 2);
    // One side only: nothing is comparable, so nothing moves.
    assert.equal(row.n_comparable, 0);
    assert.equal(row.score, base.score);
    assert.equal(row.n_shared, base.n_shared);
  });

  test("are ignored at a pair the molecule has no visible claim at", () => {
    // Naltrexone is only drawn at the family. GtoPdb's row for it at the mu
    // protein has no claim of naltrexone's to stand on and must not make the
    // two comparable there.
    const data = buildData({
      molecules: [
        molecule({ id: 1, chembl_id: "CHEMBL70", name: "MORPHINE" }),
        molecule({ id: 2, chembl_id: "CHEMBL1200657", name: "NALTREXONE" }),
      ],
      targets: [
        target({ chembl_id: "T_MU", name: "Mu opioid receptor", components: [MU] }),
        target({ chembl_id: "T_FAM", name: "Opioid receptors", target_type: "PROTEIN FAMILY",
                 n_components: 2, components: [MU, KAPPA] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_MU" }),
        claim({ id: 2, molecule: 1, target: "T_FAM" }),
        claim({ id: 3, molecule: 2, target: "T_FAM" }),
      ],
    });
    const v = loadViewer(withGtopdb(data, [
      gtp({ molecule: 1, target: "T_MU", action_type: "AGONIST", gtp_type: "Agonist", gtp_action: "Agonist" }),
      gtp({ molecule: 2, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ]));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 0);
    assert.equal(row.n_opposed, 0);
  });

  test("a molecule's two curators disagreeing is not an opposition", () => {
    // ChEMBL files alfuzosin as an alpha-1 AGONIST; GtoPdb as an ANTAGONIST.
    // Against an antagonist, the pairing that matches outranks the one that
    // opposes, exactly as when ChEMBL disagrees with itself.
    const A1A = { accession: "P35348", gene_symbol: "ADRA1A", description: "Alpha-1A adrenergic receptor" };
    const data = buildData({
      molecules: [
        molecule({ id: 1, chembl_id: "CHEMBL709", name: "ALFUZOSIN" }),
        molecule({ id: 2, chembl_id: "CHEMBL580", name: "TAMSULOSIN" }),
      ],
      targets: [target({ chembl_id: "T_A1A", name: "Alpha-1A adrenergic receptor", components: [A1A] })],
      claims: [
        curated({ id: 1, molecule: 1, target: "T_A1A", action_type: "AGONIST" }),
        curated({ id: 2, molecule: 2, target: "T_A1A", action_type: "ANTAGONIST" }),
      ],
    });
    const before = loadViewer(data).sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(before.all_opposed, true);
    const after = loadViewer(withGtopdb(buildData({
      molecules: [
        molecule({ id: 1, chembl_id: "CHEMBL709", name: "ALFUZOSIN" }),
        molecule({ id: 2, chembl_id: "CHEMBL580", name: "TAMSULOSIN" }),
      ],
      targets: [target({ chembl_id: "T_A1A", name: "Alpha-1A adrenergic receptor", components: [A1A] })],
      claims: [
        curated({ id: 1, molecule: 1, target: "T_A1A", action_type: "AGONIST" }),
        curated({ id: 2, molecule: 2, target: "T_A1A", action_type: "ANTAGONIST" }),
      ],
    }), [
      gtp({ molecule: 1, target: "T_A1A", action_type: "ANTAGONIST", gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ])).sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(after.n_comparable, 1);
    assert.equal(after.n_opposed, 0);
  });

  test("the edge panel shows GtoPdb's own words, escaped, with the ligand link", () => {
    const v = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 2, target: "T_MU", action_type: "INVERSE AGONIST", gtp_type: "Antagonist",
            gtp_action: "Inverse <agonist>", gtp_ligand_id: 1639 }),
    ]));
    const h = v.showEdge(v.lookupMolecule(2), v.lookupTarget("T_MU"), null);
    assert.match(h, /GtoPdb action/);
    assert.match(h, /Antagonist \(inverse &lt;agonist&gt;\)/);
    assert.match(h, /primary target/);
    assert.match(h, /ligandId=1639/);
    // Nothing for the molecule GtoPdb says nothing about.
    const none = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T_MU"), null);
    assert.doesNotMatch(none, /GtoPdb action/);
  });

  test("a GtoPdb pair with no direction is shown as such and compares nothing", () => {
    const v = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 1, target: "T_MU", action_type: null, gtp_type: "Allosteric modulator", gtp_action: "Neutral" }),
      gtp({ molecule: 2, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ]));
    assert.equal(v.sharedTargets(1).find((r) => r.molecule.id === 2).n_comparable, 0);
    assert.match(v.showEdge(v.lookupMolecule(1), v.lookupTarget("T_MU"), null),
                 /Allosteric modulator \(neutral\) — no direction/);
  });

  test("the mechanism filter passes a measured claim on its pair's GtoPdb action", () => {
    const v = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 2, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ]));
    v.toggleMechanism("ANTAGONIST");
    const c1 = v.allClaims().find((c) => c.id === 1), c2 = v.allClaims().find((c) => c.id === 2);
    assert.equal(v.claimVisible(c2), true);   // naltrexone, directed by GtoPdb
    assert.equal(v.claimVisible(c1), false);  // morphine, directed by nobody
    const counts = v.actionCounts();
    assert.equal(counts.rows.find((r) => r.action === "ANTAGONIST").n, 1);
    assert.equal(counts.uncurated, 1);
    v.toggleMechanism("ANTAGONIST");
    v.toggleMechanism("uncurated");
    assert.equal(v.claimVisible(c1), true);
    assert.equal(v.claimVisible(c2), false);
  });

  test("the line colour reads GtoPdb where ChEMBL is silent, and never relabels ChEMBL", () => {
    const data = buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL70", name: "MORPHINE" })],
      targets: [target({ chembl_id: "T_MU", name: "Mu opioid receptor", components: [MU] }),
                target({ chembl_id: "T_K", name: "Kappa opioid receptor", components: [KAPPA] })],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_MU" }),
        curated({ id: 2, molecule: 1, target: "T_MU", action_type: "AGONIST" }),
        claim({ id: 3, molecule: 1, target: "T_K" }),
      ],
    });
    const v = loadViewer(withGtopdb(data, [
      gtp({ molecule: 1, target: "T_MU", action_type: "PARTIAL AGONIST", gtp_type: "Agonist", gtp_action: "Partial agonist" }),
      gtp({ molecule: 1, target: "T_K", action_type: "PARTIAL AGONIST", gtp_type: "Agonist", gtp_action: "Partial agonist" }),
    ]));
    // The curated claim keeps ChEMBL's word; the measured one beside it takes GtoPdb's.
    assert.deepEqual([...v.claimActions(v.allClaims().find((c) => c.id === 2))], ["AGONIST"]);
    assert.deepEqual([...v.claimActions(v.allClaims().find((c) => c.id === 1))], ["PARTIAL AGONIST"]);
    const edges = v.catalogueGraph().edges;
    const mu = edges.find((e) => e.claims.some((c) => c.target === "T_MU"));
    const kappa = edges.find((e) => e.claims.some((c) => c.target === "T_K"));
    // Two curators, two words: the line says so.
    assert.deepEqual([...v.edgeActions(mu)].sort(), ["AGONIST", "PARTIAL AGONIST"]);
    assert.equal(v.edgeColor(mu).color, "#e8e8f0");  // MIXED_ACTION_COLOR
    assert.deepEqual([...v.edgeActions(kappa)], ["PARTIAL AGONIST"]);
    assert.equal(v.edgeColor(kappa).color, v.actionColor("PARTIAL AGONIST"));
  });

  test("a partial agonist against an antagonist is half an opposite (D19)", () => {
    const plain = loadViewer(measuredOnly()).sharedTargets(1).find((r) => r.molecule.id === 2);
    const v = loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 1, target: "T_MU", action_type: "PARTIAL AGONIST", gtp_type: "Agonist", gtp_action: "Partial agonist" }),
      gtp({ molecule: 2, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ]));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 1);
    assert.equal(row.n_opposed, 0);
    assert.equal(row.n_half, 1);
    assert.equal(row.all_opposed, false);
    // 1 - 0.75 * 0.5
    assert.ok(Math.abs(row.score - plain.score * 0.625) < 1e-9);
    assert.match(v.oppositionNote(row), /partial agonist against an antagonist or inverse agonist at 1 \(counted as half an opposite\)/);
    assert.match(v.oppositionNote(row), /reduced by 38%/);
    assert.match(v.showPair(v.lookupMolecule(1), v.lookupMolecule(2)), /counted as half/);
  });

  test("inverse agonist gets the same half rule, and a partial agonist never opposes a full one", () => {
    const pairOf = (a, b) => loadViewer(withGtopdb(measuredOnly(), [
      gtp({ molecule: 1, target: "T_MU", action_type: a, gtp_type: "Agonist", gtp_action: "Agonist" }),
      gtp({ molecule: 2, target: "T_MU", action_type: b, gtp_type: "Antagonist", gtp_action: "Antagonist" }),
    ])).sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(pairOf("PARTIAL AGONIST", "INVERSE AGONIST").n_half, 1);
    const same = pairOf("PARTIAL AGONIST", "AGONIST");
    assert.equal(same.n_half, 0);
    assert.equal(same.n_opposed, 0);
    // A full opposite is still a full one.
    assert.equal(pairOf("AGONIST", "ANTAGONIST").n_opposed, 1);
  });

  test("a GtoPdb primary-target claim is curated support, named as GtoPdb's (D18)", () => {
    const data = buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1200657", name: "NALTREXONE" })],
      targets: [target({ chembl_id: "T_MU", name: "Mu opioid receptor", components: [MU] })],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_MU", tier: "preliminary", tier_reason: "one_publication",
                multiple_study_support: 0 }),
      ],
    });
    const v = loadViewer(withGtopdb(data, [
      gtp({ molecule: 1, target: "T_MU", action_type: "ANTAGONIST", gtp_type: "Antagonist",
            gtp_action: "Antagonist", gtp_ligand_id: 1639, pubmed_ids: "9686407|24973897" }),
    ], { claims: [
      curated({ id: 2, molecule: 1, target: "T_MU", role: "gtopdb", tier_reason: "gtopdb_primary_target",
                action_type: "ANTAGONIST", mechanism_of_action: "GtoPdb: Antagonist" }),
    ] }));
    const c = v.allClaims().find((x) => x.id === 2);
    assert.equal(v.isCuratedRole(c), true);
    assert.equal(v.curatorOf(c), "GtoPdb");
    const block = v.claimBlockHTML(c, null, null, true, false);
    assert.match(block, /pubmed\.ncbi\.nlm\.nih\.gov\/9686407/);
    assert.match(block, /pubmed\.ncbi\.nlm\.nih\.gov\/24973897/);
    assert.doesNotMatch(block, /Measurements \(exact\)/);  // never measured, never "0 measurements"
    const groups = v.edgeClaimGroups([{ claim: c, note: null }]);
    assert.equal(groups[0].sub, "curated by GtoPdb");
    assert.equal(groups[0].key, "action_ANTAGONIST_gtopdb");
    const edge = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T_MU"), null);
    assert.match(edge, /curated by GtoPdb/);
    assert.match(edge, /Supported · curated/);
    // The tier reason is named, not spelled, wherever a reason is shown.
    assert.equal(v.reasonLabel("gtopdb_primary_target"), "GtoPdb primary target");
  });

  // ChEMBL mechanism 1161 files alfuzosin AGONIST at the alpha-1 family against
  // its own cited label; the build withholds it (CHEMBL_MECHANISM_ACTION_EXCLUSIONS).
  // Kept, ChEMBL's AGONIST matched phenylephrine's and the pair was never
  // opposed; withheld, GtoPdb's antagonist is the only direction and it is.
  test("a direction withheld as a ChEMBL error is said, and GtoPdb's then stands", () => {
    const A1A = { accession: "P35348", gene_symbol: "ADRA1A", description: "Alpha-1A adrenergic receptor" };
    const A1B = { accession: "P35368", gene_symbol: "ADRA1B", description: "Alpha-1B adrenergic receptor" };
    const WHY = "ChEMBL files this as AGONIST (\"Adrenergic receptor alpha-1 agonist\", " +
                "mechanism 1161), withheld as a known error: its cited label says antagonist";
    function alpha1(alfuzosinFamily) {
      const data = buildData({
        molecules: [
          molecule({ id: 1, chembl_id: "CHEMBL709", name: "ALFUZOSIN" }),
          molecule({ id: 2, chembl_id: "CHEMBL1215", name: "PHENYLEPHRINE" }),
        ],
        targets: [
          target({ chembl_id: "T_A1", name: "Adrenergic receptor alpha-1", target_type: "PROTEIN FAMILY",
                   components: [A1A, A1B] }),
          target({ chembl_id: "T_A1A", name: "Alpha-1A adrenergic receptor", components: [A1A] }),
        ],
        claims: [
          curated(Object.assign({ id: 1, molecule: 1, target: "T_A1" }, alfuzosinFamily)),
          curated({ id: 2, molecule: 2, target: "T_A1", action_type: "AGONIST",
                    mechanism_of_action: "Adrenergic receptor alpha-1 agonist" }),
        ],
      });
      return loadViewer(withGtopdb(data, [
        gtp({ molecule: 1, target: "T_A1A", action_type: "ANTAGONIST", gtp_type: "Antagonist",
              gtp_action: "Antagonist", gtp_ligand_id: 486 }),
      ], { claims: [
        curated({ id: 3, molecule: 1, target: "T_A1A", role: "gtopdb", tier_reason: "gtopdb_primary_target",
                  action_type: "ANTAGONIST", mechanism_of_action: "GtoPdb: Antagonist" }),
      ] }));
    }
    const row = (v) => v.sharedTargets(1).find((r) => r.molecule.id === 2);

    const kept = alpha1({ action_type: "AGONIST", mechanism_of_action: "Adrenergic receptor alpha-1 agonist" });
    assert.equal(row(kept).n_opposed, 0);

    const v = alpha1({ action_type: null, mechanism_of_action: null, action_exclusion: WHY });
    assert.equal(row(v).n_comparable, 1);
    assert.equal(row(v).n_opposed, 1);
    const c = v.allClaims().find((x) => x.id === 1);
    assert.equal(v.claimActions(c).length, 0);           // no agonist colour, no Agonist filter
    assert.match(v.claimDetail(c), /direction withheld \(a known ChEMBL error\)/);
    assert.doesNotMatch(v.claimDetail(c), /no direction recorded/);
    const block = v.claimBlockHTML(c, null, null, true, false);
    assert.match(block, /<span class="pill warn">direction withheld<\/span>/);
    assert.match(block, /its cited label says antagonist/);
    assert.match(block, /Supported · curated/);           // the claim keeps its support
  });

  test("About credits GtoPdb and both its licences only when its file is there", () => {
    assert.match(loadViewer(withGtopdb(measuredOnly(), [])).aboutSourcesHTML(),
                 /Guide to Pharmacology<\/a> 2026\.3: [^<]*<a href="https:\/\/opendatacommons\.org\/licenses\/odbl\/1-0\/"[^>]*>ODbL 1\.0<\/a>, contents <a href="https:\/\/creativecommons\.org\/licenses\/by-sa\/4\.0\/"[^>]*>CC BY-SA 4\.0<\/a>/);
    assert.doesNotMatch(loadViewer(measuredOnly()).aboutSourcesHTML(), /Guide to Pharmacology/);
  });

  test("About names ChEMBL's licence, with or without GtoPdb", () => {
    for (const data of [measuredOnly(), withGtopdb(measuredOnly(), [])]) {
      assert.match(loadViewer(data).aboutSourcesHTML(),
                   /ebi\.ac\.uk\/chembl\/[^>]*>ChEMBL<\/a> 37 \(EMBL-EBI\)[^<]*<a href="https:\/\/creativecommons\.org\/licenses\/by-sa\/3\.0\/"[^>]*>CC BY-SA 3\.0<\/a>/);
    }
  });

  test("the catalogue line keeps its counts and leaves the credits to About", () => {
    const h = loadViewer(withGtopdb(measuredOnly(), [])).filtersHTML();
    assert.match(h, /Catalogue: \d+ molecules, \d+ ChEMBL target records, \d+ drawable claims\./);
    assert.match(h, /Sources and licences are under About/);
    assert.doesNotMatch(h, /CC BY-SA|ODbL|Guide to Pharmacology/);
  });
});

describe("gtopdb.data.js, GtoPdb's own file", () => {
  // graph.data.js states every status and count from ChEMBL's claims alone;
  // the GtoPdb file carries its claims and the statuses they change.
  function chemblPreliminary() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1200657", name: "NALTREXONE",
                             evidence_status: "has_preliminary",
                             gap_reason: "No Supported claim; Preliminary evidence only",
                             n_claims_supported: 0, n_claims_preliminary: 1 })],
      targets: [target({ chembl_id: "T_MU", name: "Mu opioid receptor", components: [MU] }),
                target({ chembl_id: "T_KAPPA", name: "Kappa opioid receptor", components: [KAPPA] })],
      claims: [claim({ id: 1, molecule: 1, target: "T_MU", tier: "preliminary",
                       tier_reason: "one_publication", multiple_study_support: 0 }),
               claim({ id: 3, molecule: 1, target: "T_KAPPA", tier: "preliminary",
                       tier_reason: "one_publication", multiple_study_support: 0 })],
    });
  }
  const gtopdbClaim = curated({ id: 2, molecule: 1, target: "T_MU", role: "gtopdb",
                                tier_reason: "gtopdb_primary_target", action_type: "ANTAGONIST" });

  test("merges its claims in id order, and counts and states them as the build would", () => {
    const v = loadViewer(withGtopdb(chemblPreliminary(), [], {
      claims: [gtopdbClaim], status: { 1: ["has_supported"] } }));
    assert.deepEqual(v.allClaims().map((c) => c.id), [1, 2, 3]);
    const m = v.lookupMolecule(1);
    assert.equal(m.evidence_status, "has_supported");
    assert.equal(m.gap_reason, null);
    assert.equal(m.n_claims_supported, 1);
    assert.equal(m.n_claims_preliminary, 1);
    assert.equal(v.catalogueCounts().claims_drawable, 3);
  });

  test("is merged only into the catalogue it was exported with", () => {
    const data = chemblPreliminary();
    data.generated = "2026-10-09T12:00:00";
    const stale = loadViewer(withGtopdb(data, [], {
      claims: [gtopdbClaim], status: { 1: ["has_supported"] }, generated: "2026-09-27T21:00:00" }));
    assert.deepEqual(stale.allClaims().map((c) => c.id), [1, 3]);
    assert.equal(stale.lookupMolecule(1).evidence_status, "has_preliminary");
    const paired = chemblPreliminary();
    paired.generated = "2026-10-09T12:00:00";
    const v = loadViewer(withGtopdb(paired, [], {
      claims: [gtopdbClaim], status: { 1: ["has_supported"] }, generated: "2026-10-09T12:00:00" }));
    assert.deepEqual(v.allClaims().map((c) => c.id), [1, 2, 3]);
  });

  test("absent, leaves the ChEMBL-only page whole", () => {
    const v = loadViewer(chemblPreliminary());
    assert.deepEqual(v.allClaims().map((c) => c.id), [1, 3]);
    const m = v.lookupMolecule(1);
    assert.equal(m.evidence_status, "has_preliminary");
    assert.equal(m.n_claims_supported, 0);
    assert.equal(v.catalogueCounts().claims_drawable, 2);
    assert.equal(v.gtopdbAt(1, "T_MU").length, 0);
  });
});
