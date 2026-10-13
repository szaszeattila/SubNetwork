// Tests for D20: one protein recorded once per species. ChEMBL files a
// SINGLE PROTEIN target once per organism it was assayed in, so a receptor
// studied in human and rat is two target records of one protein. A backfill
// (scripts/resolve_cohort_orthologues.py, not part of this test) matches each
// non-human SINGLE PROTEIN record to the human protein it is, by sequence,
// and exports that accession on the target as `human_orthologue`. This file
// characterises what the viewer (viz/index.html) does with that field:
// `proteinOf`/`proteinKey` fold matched records into one shared target,
// weighted by species_factor = n^0.5; prevalence stays per record; direction
// and subsumption are read at the protein rather than at the record; and the
// pair panel says so. See docs/COHORT-2.md, D20, and viz/index.html around
// `proteinOfAccession`/`proteinKey`/`SPECIES_EXPONENT`.
//
// Following the pattern in tests/cohort_viewer.test.mjs (see especially
// "an opposite is not a likeness" and "the pair panel shows the arithmetic
// behind the score"): small hand-built catalogues, read through the vm
// harness in tests/cohort_harness.mjs, nothing mocked beyond that.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadViewer, buildData, buildShard, molecule, target, claim, plain } from "./cohort_harness.mjs";

// The shape at the centre of D20: a mu-opioid-type receptor with a human
// record (TH, accession P1) and a rat record (TR, accession P2), the rat one
// carrying `human_orthologue: "P1"` when a match was found. Both molecules
// are curated/measured at both records, so the un-orthologued run reproduces
// the "12 shared targets that were three receptors in four species" problem
// D20 exists to fix.
function orthologueCatalogue({ withOrthologue = true, claims = null } = {}) {
  const human = { accession: "P1", gene_symbol: "OPRM1", description: "Mu-type opioid receptor" };
  const rat = { accession: "P2", gene_symbol: "Oprm1", description: "Mu-type opioid receptor" };
  return buildData({
    molecules: [
      molecule({ id: 1, name: "ALPHA" }),
      molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
    ],
    targets: [
      target({ chembl_id: "TH", name: "Mu-type opioid receptor", components: [human] }),
      target(Object.assign(
        { chembl_id: "TR", name: "Mu-type opioid receptor", organism: "Rattus norvegicus",
          tax_id: 10116, components: [rat] },
        withOrthologue ? { human_orthologue: "P1" } : {})),
    ],
    claims: claims || [
      claim({ id: 1, molecule: 1, target: "TH" }),
      claim({ id: 2, molecule: 1, target: "TR" }),
      claim({ id: 3, molecule: 2, target: "TH" }),
      claim({ id: 4, molecule: 2, target: "TR" }),
    ],
  });
}

// Two genuinely different human proteins, set up so every per-record factor
// (kind weight, evidence, prevalence) matches orthologueCatalogue()'s exactly:
// same two molecules, each target shared by both, same claim defaults. Only
// the identity of what is shared differs - one protein twice a species
// (above) versus two proteins once each (here).
function twoProteinCatalogue() {
  const px = { accession: "PX", gene_symbol: "GENEX", description: "Protein X" };
  const py = { accession: "PY", gene_symbol: "GENEY", description: "Protein Y" };
  return buildData({
    molecules: [
      molecule({ id: 1, name: "ALPHA" }),
      molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
    ],
    targets: [
      target({ chembl_id: "TX", name: "Protein X", components: [px] }),
      target({ chembl_id: "TY", name: "Protein Y", components: [py] }),
    ],
    claims: [
      claim({ id: 1, molecule: 1, target: "TX" }),
      claim({ id: 2, molecule: 1, target: "TY" }),
      claim({ id: 3, molecule: 2, target: "TX" }),
      claim({ id: 4, molecule: 2, target: "TY" }),
    ],
  });
}

describe("D20: one protein in several species folds into one shared target", () => {
  // The canvas's count is in nodes, and a protein is one node: two records of
  // one protein are one target there, and the tooltip names the records.
  test("the canvas counts a protein once, and names its records apart", () => {
    const folded = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    assert.match(folded.graphCountsHTML(), /<b>1<\/b> of 1 targets$/);
    assert.match(folded.graphCountsTitle(), /2 ChEMBL target records are 1 targets here/);
    const apart = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    assert.match(apart.graphCountsHTML(), /<b>2<\/b> of 2 targets$/);
  });

  test("a matched orthologue folds the rat record into the human one, at √2", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_shared, 1);
    assert.equal(row.n_same_protein, 1);
    assert.equal(row.n_exact, 1);

    const counted = row.shared.filter((s) => s.contribution > 0);
    assert.equal(counted.length, 1, "only the kept record scores");
    const kept = counted[0];
    assert.equal(kept.species, 2);
    assert.ok(Math.abs(kept.species_factor - Math.SQRT2) < 1e-9,
      `species_factor should be sqrt(2), got ${kept.species_factor}`);

    const folded = row.shared.find((s) => s.same_protein_as);
    assert.ok(folded, "the other species' record is kept on the pair, not dropped");
    assert.equal(folded.contribution, 0);
    assert.equal(folded.same_protein_as.chembl_id, kept.target.chembl_id);

    // raw_score is the single-record contribution (kind x evidence x
    // prevalence, read off the kept row before the species multiplier) times
    // species_factor - not the sum of both records' contributions, which
    // would be the old, unfolded behaviour.
    const singleRecordContribution = kept.kind_weight * kept.evidence * kept.prevalence;
    assert.ok(Math.abs(row.raw_score - singleRecordContribution * kept.species_factor) < 1e-9);
    assert.ok(
      Math.abs(row.raw_score - singleRecordContribution * 2) > 1e-6,
      "not double-counted as if both records scored in full");
  });

  test("without a matched orthologue, the old behaviour: two shared targets", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_shared, 2);
    assert.equal(row.n_same_protein, 0);
    assert.ok(row.shared.every((s) => !s.same_protein_as));
    assert.equal(row.shared.filter((s) => s.contribution > 0).length, 2);
  });

  test("two different proteins outscore one protein shared in two species", () => {
    // The ordering the rule exists for: two proteins is a broader overlap than
    // one protein doubly recorded, so it must score higher even though the
    // species-repeat case gets a boost of its own. Built so every per-record
    // factor (kind, evidence, prevalence) is identical between the two
    // catalogues - same two molecules, same claim defaults, same df (2 of 2
    // molecules at every target) - so the only variable is what SPECIES_EXPONENT
    // and n_shared actually differ on: sqrt(2) =~ 1.414 of one thing versus
    // 2 of two things.
    const speciesRow = loadViewer(orthologueCatalogue({ withOrthologue: true }))
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    const twoProteinRow = loadViewer(twoProteinCatalogue())
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(twoProteinRow.n_shared, 2);
    assert.equal(speciesRow.n_shared, 1);
    assert.ok(twoProteinRow.raw_score > speciesRow.raw_score,
      `expected two distinct proteins (${twoProteinRow.raw_score}) to outscore ` +
      `one protein in two species (${speciesRow.raw_score})`);
  });

  test("degree counts proteins, not records: two species is one thing a molecule does", () => {
    // Read off prevalenceIndex through n_mine_targets/n_their_targets, the
    // divisor's inputs (score /= sqrt(mineDeg * theirDeg)). A molecule with
    // claims at TH and TR reaches one protein, not two records.
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_mine_targets, 1);
    assert.equal(row.n_their_targets, 1);
  });
});

describe("D20: direction and subsumption are read at the protein, across species", () => {
  test("an agonist at the rat record opposes an antagonist at the matched human one", () => {
    const human = { accession: "P1", gene_symbol: "OPRM1", description: "Mu-type opioid receptor" };
    const rat = { accession: "P2", gene_symbol: "Oprm1", description: "Mu-type opioid receptor" };
    const v = loadViewer(buildData({
      molecules: [
        molecule({ id: 1, name: "ALPHA" }),
        molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
      ],
      targets: [
        target({ chembl_id: "TH", name: "Mu-type opioid receptor", components: [human] }),
        target({ chembl_id: "TR", name: "Mu-type opioid receptor", organism: "Rattus norvegicus",
                 tax_id: 10116, components: [rat], human_orthologue: "P1" }),
      ],
      claims: [
        // Both molecules need a claim at both records for TH/TR to both be
        // "shared", which is what makes their proteins comparable at all.
        claim({ id: 1, molecule: 1, target: "TH" }),
        claim({ id: 2, molecule: 1, target: "TR", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0, action_type: "AGONIST",
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 3, molecule: 2, target: "TH", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0, action_type: "ANTAGONIST",
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 4, molecule: 2, target: "TR" }),
      ],
    }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 1,
      "one protein, curated on both sides, however far apart the two records are");
    assert.equal(row.n_opposed, 1);
    assert.equal(row.all_opposed, true);
  });

  test("the same claims with no orthologue match are not comparable at all", () => {
    // Same shape, but TR carries no human_orthologue: the rat accession is
    // its own protein by the fallback rule, so ALPHA's AGONIST at P2 and
    // BETA's ANTAGONIST at P1 never meet.
    const human = { accession: "P1", gene_symbol: "OPRM1", description: "Mu-type opioid receptor" };
    const rat = { accession: "P2", gene_symbol: "Oprm1", description: "Mu-type opioid receptor" };
    const v = loadViewer(buildData({
      molecules: [
        molecule({ id: 1, name: "ALPHA" }),
        molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
      ],
      targets: [
        target({ chembl_id: "TH", name: "Mu-type opioid receptor", components: [human] }),
        target({ chembl_id: "TR", name: "Mu-type opioid receptor", organism: "Rattus norvegicus",
                 tax_id: 10116, components: [rat] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "TH" }),
        claim({ id: 2, molecule: 1, target: "TR", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0, action_type: "AGONIST",
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 3, molecule: 2, target: "TH", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0, action_type: "ANTAGONIST",
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 4, molecule: 2, target: "TR" }),
      ],
    }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 0);
    assert.equal(row.n_opposed, 0);
    assert.equal(row.all_opposed, false);
  });

  test("a family listing a non-human accession is subsumed by the matched human record", () => {
    // FAM's own components are [P2 (rat), P3 (human)]. The pair shares that
    // protein individually as TH (human, P1) and TY (human, P3). Without D20,
    // proteinOf(P2) is just P2, which nothing in `covered` contains, so FAM
    // would NOT be subsumed - it would read as a second, broader overlap of a
    // protein the pair already shares under a different accession.
    const human1 = { accession: "P1", gene_symbol: "OPRM1", description: "Mu-type opioid receptor" };
    const rat1 = { accession: "P2", gene_symbol: "Oprm1", description: "Mu-type opioid receptor" };
    const human2 = { accession: "P3", gene_symbol: "OPRK1", description: "Kappa-type opioid receptor" };
    const v = loadViewer(buildData({
      molecules: [
        molecule({ id: 1, name: "ALPHA" }),
        molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
      ],
      targets: [
        target({ chembl_id: "TH", name: "Mu-type opioid receptor", components: [human1] }),
        target({ chembl_id: "TR", name: "Mu-type opioid receptor", organism: "Rattus norvegicus",
                 tax_id: 10116, components: [rat1], human_orthologue: "P1" }),
        target({ chembl_id: "TY", name: "Kappa-type opioid receptor", components: [human2] }),
        target({ chembl_id: "FAM", name: "Opioid receptor", target_type: "PROTEIN FAMILY",
                 n_components: 2, components: [rat1, human2] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "TH" }),
        claim({ id: 2, molecule: 2, target: "TH" }),
        claim({ id: 3, molecule: 1, target: "TY" }),
        claim({ id: 4, molecule: 2, target: "TY" }),
        claim({ id: 5, molecule: 1, target: "FAM", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0,
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 6, molecule: 2, target: "FAM", role: "curated", tier_reason: "curated_support",
                curated_support: 1, multiple_study_support: 0,
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
      ],
    }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const fam = row.shared.find((s) => s.target.chembl_id === "FAM");
    assert.ok(fam, "the family claim is on the pair");
    assert.equal(fam.subsumed, true,
      "TR's accession maps to the same protein as TH, so FAM's non-human " +
      "listing does not escape subsumption");
  });
});

describe("D20: a PROTEIN COMPLEX is never folded by species", () => {
  test("proteinKey returns the complex's own chembl_id, never a protein key", () => {
    const v = loadViewer();
    const complex = target({
      chembl_id: "CPLX1", target_type: "PROTEIN COMPLEX",
      components: [{ accession: "P1", gene_symbol: "G1", description: "one subunit" }],
    });
    assert.equal(v.proteinKey(complex), "CPLX1");
  });

  test("even a human_orthologue on the record (were one ever exported) changes nothing", () => {
    const v = loadViewer();
    const complex = target({
      chembl_id: "CPLX1", target_type: "PROTEIN COMPLEX", human_orthologue: "P9",
      components: [{ accession: "P1", gene_symbol: "G1", description: "one subunit" }],
    });
    assert.equal(v.proteinKey(complex), "CPLX1");
  });

  test("a single-component SINGLE PROTEIN target still keys by protein", () => {
    const v = loadViewer();
    const single = target({
      chembl_id: "T1", target_type: "SINGLE PROTEIN",
      components: [{ accession: "P1", gene_symbol: "G1", description: "protein" }],
    });
    assert.equal(v.proteinKey(single), "protein:P1");
  });
});

describe("D20: the pair panel names the fold and shows the Species column", () => {
  test("the pair-level note, the folded block, the counted block and ×1.41", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));

    // The one-line summary before the reader meets two "Mu-type opioid
    // receptor" blocks and counts two targets.
    assert.ok(h.includes(
      "1 more record is the same protein in another species, listed with it " +
      "and counted once."),
      "expected the pair-level fold note");

    // The folded block points back at the counted one.
    assert.ok(h.includes(
      "the same protein as Mu-type opioid receptor (human) above, in another " +
      "species, so it is counted there, once"),
      "expected the folded block's own note");

    // The counted block states how many species and the multiplier.
    assert.ok(h.includes("recorded in 2 species"), "expected the species count");
    assert.ok(h.includes("here, counted once, at the human record, where it is strongest, ×1.41"),
      "expected the species factor and the record that counts");

    // The score table carries a Species column, with the same ×1.41.
    assert.match(h, /<th><span class="help" tabindex="0">Species<span class="help-text">/);
    const table = h.slice(h.indexOf("score-table"), h.indexOf("</table>"));
    assert.ok(table.includes("×1.41"), "expected the Species column's factor");
  });

  test("without a match, no fold language and no Species multiplier appear", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.ok(!h.includes("the same protein in another species"));
    assert.ok(!h.includes("counted once, ×"));
  });

  test("sorting keeps a folded row directly after its counted row", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const keptIndex = row.shared.findIndex((s) => s.species > 1 && !s.same_protein_as);
    const foldedIndex = row.shared.findIndex((s) => !!s.same_protein_as);
    assert.ok(keptIndex >= 0 && foldedIndex >= 0, "both rows are present");
    assert.equal(foldedIndex, keptIndex + 1,
      "the same protein's other species' record sits right after the one that counts");
  });
});

// 2026-09-28, at the user's request: caffeine and theophylline's Why this score
// named ADORA1 at the cow record alone, though the pair meets at four species'
// ADORA1, and the blocks below were one per record with nothing but a full
// name to match against the symbol in the table.
describe("D20: a protein in several species is one block, one row, one link", () => {
  test("one header for the protein, each species' record folded under it", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.ok(h.includes('<details class="section" id="blk-pair_p_P1"'),
      "the group is one section, anchored by the protein");
    assert.ok(h.includes(
      'data-fold="pair_p_P1">OPRM1 · Mu-type opioid receptor · 2 species: human, rat</summary>'),
      "the header names the human symbol and every species under it");
    // Both records sit inside the group, as folded subsections of their own.
    const group = h.slice(h.indexOf('id="blk-pair_p_P1"'));
    assert.ok(group.includes('<details class="subsection"><summary class="subsection-toggle" ' +
      'data-fold="pair_t_TH">OPRM1 · Mu-type opioid receptor (human) ' +
      '<span class="muted">· the one counted</span></summary>'));
    assert.ok(group.includes('<details class="subsection"><summary class="subsection-toggle" ' +
      'data-fold="pair_t_TR">Oprm1 · Mu-type opioid receptor (rat)</summary>'));
    assert.ok(!h.includes('id="blk-pair_t_TH"') && !h.includes('id="blk-pair_t_TR"'),
      "neither record is a top-level block of its own any more");
    // Each record keeps its own claims: two per record, four in all.
    assert.equal((group.match(/class="claim-row/g) || []).length,
                 (h.match(/class="claim-row/g) || []).length);
  });

  test("the score row says how many species rather than one record's", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    const table = h.slice(h.indexOf("score-table"), h.indexOf("</table>"));
    assert.ok(table.includes('<a href="#" data-jump="pair_p_P1">OPRM1</a> ' +
      '<span class="muted" title="human, rat">2 species</span>'));
  });

  test("the symbol is the human protein's even when a rat record counts", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    assert.equal(v.proteinSymbol(v.lookupTarget("TR")), "OPRM1");
    assert.equal(v.targetLabel(v.lookupTarget("TR")), "Oprm1", "the record keeps its own label");
  });

  test("without a match, each record is its own block and row, named by its species", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.ok(h.includes('id="blk-pair_t_TH"') && h.includes('id="blk-pair_t_TR"'));
    assert.ok(!h.includes("pair_p_"));
    const table = h.slice(h.indexOf("score-table"), h.indexOf("</table>"));
    assert.ok(table.includes('>Oprm1</a> <span class="muted">rat</span>'));
  });

  test("a jump opens the block, remembers it open, and scrolls to it", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const el = v.document.getElementById("blk-pair_p_P1");
    let scrolled = null;
    el.open = false;
    el.scrollIntoView = (opts) => { scrolled = opts; };
    assert.equal(v.jumpToBlock("pair_p_P1"), true);
    assert.equal(el.open, true);
    assert.equal(v.sectionOpen("pair_p_P1", false), true);
    assert.equal(scrolled.block, "start");
  });
});

// A protein recorded in several species is drawn as one node, and its panels
// are the protein's, with one section per species' record (2026-10-10, at the
// user's request: two nodes that share a name read as two different things).
// Each record keeps its own claims; nothing here is added across species.
describe("D20 on the canvas: one protein in several species is one node", () => {
  test("one node keyed by the human record, one line per molecule, both records' claims", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const g = v.catalogueGraph();
    const targets = plain(g.nodes).filter((n) => n.kind === "target");
    assert.deepEqual(targets.map((n) => n.key), ["tTH"]);
    assert.deepEqual(targets[0].records.map((t) => t.chembl_id), ["TH", "TR"]);
    assert.equal(v.nodeLabel(g.byKey.get("tTH")), "OPRM1");
    assert.deepEqual(plain(g.edges).map((e) => e.from + ">" + e.to + ":" +
                                         e.claims.map((c) => c.id).join(",")),
                     ["m1>tTH:1,2", "m2>tTH:3,4"]);
  });

  test("without a match the two records are two nodes, as before", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    const keys = plain(v.catalogueGraph().nodes).filter((n) => n.kind === "target")
      .map((n) => n.key).sort();
    assert.deepEqual(keys, ["tTH", "tTR"]);
  });

  test("a lone non-human record is its own node, under its own key", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "TR", name: "Mu-type opioid receptor",
                         organism: "Rattus norvegicus", human_orthologue: "P1",
                         components: [{ accession: "P2", gene_symbol: "Oprm1" }] })],
      claims: [claim({ id: 1, molecule: 1, target: "TR" })],
    }));
    const g = v.catalogueGraph();
    assert.ok(g.byKey.has("tTR"));
    // Named by the human protein it was matched to, which the catalogue lacks.
    assert.equal(v.nodeLabel(g.byKey.get("tTR")), "OPRM1");
  });

  test("selecting either record, or a line opened at either, lights the one node", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const viaRat = v.highlightFor("target", "TR");
    assert.equal(viaRat.nodes.get("tTH"), 0);
    assert.equal(viaRat.nodes.get("m1"), 1);
    const edge = v.highlightFor("edge", 1, "TR");
    assert.equal(edge.nodes.get("tTH"), 0);
    assert.equal(edge.nodes.get("m1"), 0);
  });

  test("a pair meeting at the protein in two species lights it as shared", () => {
    const v = loadViewer(orthologueCatalogue({ claims: [
      claim({ id: 1, molecule: 1, target: "TH" }),
      claim({ id: 2, molecule: 2, target: "TR" }),
    ] }));
    const h = v.highlightFor("pair", 1, 2);
    assert.equal(h.nodes.get("tTH"), 1);
    assert.equal(h.edges.size, 2);
  });

  test("a click on the node opens the protein, and on a line opens its strongest record", () => {
    const v = loadViewer(orthologueCatalogue({ claims: [
      claim({ id: 1, molecule: 1, target: "TH", tier: "preliminary", multiple_study_support: 0 }),
      claim({ id: 2, molecule: 1, target: "TR" }),
    ] }));
    v.onGraphClick({ nodes: ["tTH"], edges: [] });
    assert.equal(v.getSelection().kind + ":" + v.getSelection().id, "target:TH");
    const e = plain(v.catalogueGraph().edges)[0];
    v.onGraphClick({ nodes: [], edges: [e.id] });
    assert.equal(v.getSelection().kind + ":" + v.getSelection().extra, "edge:TR",
                 "the rat record carries the Supported claim");
  });

  test("search lists the protein once, at the record that matched", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const byName = v.searchCatalogue("mu-type").targets;
    assert.equal(byName.length, 1);
    assert.equal(byName[0].target.chembl_id, "TH");
    const byId = plain(v.searchCatalogue("TR").targets.map((r) => r.target.chembl_id));
    assert.deepEqual(byId, ["TR"]);
    assert.match(v.searchResultsHTML(v.searchCatalogue("mu-type")), /2 species: human, rat/);
  });
});

describe("D20 in the panels: the protein's panel has a section per species", () => {
  test("the target panel names no species and opens with the record it was opened at", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const h = v.showTarget(v.lookupTarget("TR"));
    assert.ok(h.startsWith("<h3>OPRM1 · Mu-type opioid receptor</h3>"), h.slice(0, 80));
    assert.ok(h.includes("<td>rat, human</td>"));
    const rat = h.indexOf('data-fold="target_species_Rattus_norvegicus"');
    const human = h.indexOf('data-fold="target_species_Homo_sapiens"');
    assert.ok(rat > 0 && human > rat, "the rat record first");
    // Molecules once however many species' records each is at; claims apart.
    assert.match(h, />2 molecules<.*· 4 claims/s);
    // Each section's rows open the line at that section's record.
    const ratSection = h.slice(rat, human);
    assert.ok(ratSection.includes('data-select="edge" data-id="1" data-other="TR"'));
    assert.ok(!ratSection.includes('data-other="TH"'));
  });

  test("the interaction panel puts the clicked species first and keeps the rest", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("TH"), null);
    assert.ok(h.startsWith("<h3>ALPHA → OPRM1 · Mu-type opioid receptor</h3>"), h.slice(0, 80));
    assert.ok(h.includes("2 claims drawn as this line and counted as <b>one</b> shared target"));
    const human = h.indexOf('data-fold="edge_claims"');
    const rat = h.indexOf('data-fold="edge_claims_Rattus_norvegicus"');
    assert.ok(human > 0 && rat > human, "the record it was opened at first");
    assert.match(h.slice(human, rat), /Human \(1\)/);
    assert.match(h.slice(rat), /Rat \(1\)/);
    // Opened at the rat record, the rat claims lead.
    const r = v.showEdge(v.lookupMolecule(1), v.lookupTarget("TR"), null);
    const lead = r.indexOf('data-fold="edge_claims"');
    const next = r.indexOf('data-fold="edge_claims_Homo_sapiens"');
    assert.ok(lead > 0 && next > lead);
    assert.match(r.slice(lead, next), /Rat \(1\)/);
  });

  test("a retained claim in the evidence shard is counted in its own record's section", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: true }));
    v.registerEvidence(buildShard({
      molecule: 1,
      claims: [claim({ id: 99, molecule: 1, target: "TR", tier: "limited_or_unresolved",
                       tier_reason: "censored_only", multiple_study_support: 0,
                       n_measurements: 0, supporting_endpoint_class: null, endpoints: [] })],
    }));
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("TH"), v.evidenceFor(1));
    assert.ok(h.includes("2 claims drawn as this line and counted as <b>one</b> shared target · " +
                         "1 retained, backing no line"));
    const rat = h.slice(h.indexOf('data-fold="edge_claims_Rattus_norvegicus"'));
    assert.match(rat, /Rat \(2\) <span class="muted">· 1 drawn · 1 retained<\/span>/);
  });

  test("where the molecule meets the protein in one species, one Claims section as before", () => {
    const v = loadViewer(orthologueCatalogue({ withOrthologue: false }));
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("TH"), null);
    assert.ok(h.includes('data-fold="edge_claims"'));
    assert.ok(!h.includes('data-fold="edge_claims_'));
    assert.ok(h.startsWith("<h3>ALPHA → OPRM1 · Mu-type opioid receptor</h3>"));
  });
});
