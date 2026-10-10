// Tests for the viewer's decision-making logic (viz/index.html).
//
// The Python suite covers which numbers get into the database. This one covers
// what the page then claims about them, which is where the project's actual
// deliverable lives: the graph is the product, not a readout of the DB, so the
// code that decides what counts as corroboration, what collapses into one
// assay row, and which molecules are ranked as similar is load-bearing in
// exactly the way build_db.py is.
//
// Same standard as tests/test_build_db.py: these are not here for coverage,
// they lock in decisions that have already been gotten wrong at least once, or
// that would be silently wrong if changed.
//
// Run with: node --test tests/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  loadViewer, edge, measurement, molecule, target, group, plain,
} from "./legacy_viewer_harness.mjs";

// A graph with the target nodes compareEvidence needs for its label tiebreak.
const TARGETS = {
  nodes: [
    molecule("mol_a", "Caffeine"),
    target("tgt_x", "ADORA1", { expressed_in_brain: 1 }),
    target("tgt_y", "ADORA2A", { expressed_in_brain: 1 }),
    target("tgt_z", "PDE4A"),
  ],
  edges: [],
};

describe("escaping and link safety (invariant 11)", () => {
  const v = loadViewer(TARGETS);

  test("esc neutralises every character that can break out of markup", () => {
    assert.equal(v.esc(`<script>&"'`), "&lt;script&gt;&amp;&quot;&#39;");
  });

  test("esc renders null and undefined as empty, not as the word 'null'", () => {
    assert.equal(v.esc(null), "");
    assert.equal(v.esc(undefined), "");
  });

  test("safeUrl accepts http and https", () => {
    assert.equal(v.safeUrl("https://pubmed.ncbi.nlm.nih.gov/123/"),
                 "https://pubmed.ncbi.nlm.nih.gov/123/");
    assert.ok(v.safeUrl("http://example.test/a"));
  });

  test("safeUrl rejects script-bearing schemes", () => {
    // Upstream free text reaching an href is the case this exists for: PDSP's
    // Reference column and ChEMBL paper titles are not sanitised at source.
    assert.equal(v.safeUrl("javascript:alert(1)"), null);
    assert.equal(v.safeUrl("data:text/html,<script>alert(1)</script>"), null);
    assert.equal(v.safeUrl("vbscript:msgbox(1)"), null);
  });

  test("safeUrl rejects unparseable input rather than throwing", () => {
    assert.equal(v.safeUrl("http://[not a url"), null);
    assert.equal(v.safeUrl(""), null);
    assert.equal(v.safeUrl(null), null);
  });

  test("link degrades a rejected URL to plain text and still escapes the label", () => {
    const html = v.link("javascript:alert(1)", `Butini S <b>2008</b>`);
    assert.ok(!html.includes("<a "), "must not emit an anchor for a bad scheme");
    assert.ok(html.includes("&lt;b&gt;"), "label must still be escaped");
  });

  test("link escapes the href it does emit", () => {
    const html = v.link(`https://x.test/a"onmouseover="evil()`, "paper");
    assert.ok(!/href="[^"]*"[^>]*onmouseover/.test(html),
              "a quote in the URL must not open a new attribute");
  });
});

describe("isCorroborated", () => {
  const v = loadViewer(TARGETS);

  test("more than one measurement is corroboration", () => {
    assert.equal(v.isCorroborated(edge({ n_measurements: 2 })), true);
    assert.equal(v.isCorroborated(edge({ n_measurements: 1 })), false);
  });

  test("a curated mechanism is corroboration regardless of n", () => {
    assert.equal(
      v.isCorroborated(edge({ is_primary_mechanism: 1, n_measurements: null })),
      true);
  });

  test("a functional-only edge reads its own count, not the binding NULL", () => {
    // The documented regression: functional-only edges leave n_measurements
    // NULL, and reading only that column labelled every one of them a
    // single-source lead no matter how many measurements backed it.
    assert.equal(
      v.isCorroborated(edge({ n_measurements: null, functional_n_measurements: 4 })),
      true);
  });

  test("a single measurement in each role is still not corroboration", () => {
    assert.equal(
      v.isCorroborated(edge({ n_measurements: 1, functional_n_measurements: 1 })),
      false);
  });
});

describe("evidenceTier", () => {
  const v = loadViewer(TARGETS);

  test("curated 0, corroborated 1, single-source lead 2", () => {
    assert.equal(v.evidenceTier(edge({ is_primary_mechanism: 1 })), 0);
    assert.equal(v.evidenceTier(edge({ n_measurements: 6 })), 1);
    assert.equal(v.evidenceTier(edge({ n_measurements: 1 })), 2);
  });

  test("tier cannot disagree with the graph's solid-vs-dashed styling", () => {
    // Both read the same predicate; this fails the moment one is reimplemented
    // beside the other instead of on top of it.
    for (const e of [
      edge({ is_primary_mechanism: 1, n_measurements: null }),
      edge({ n_measurements: 9 }),
      edge({ n_measurements: 1 }),
      edge({ n_measurements: null, functional_n_measurements: 3 }),
      edge({ n_measurements: null, functional_n_measurements: null }),
    ]) {
      assert.equal(v.evidenceTier(e) <= 1, v.isCorroborated(e));
    }
  });
});

describe("paperCount", () => {
  const v = loadViewer(TARGETS);

  test("counts distinct papers, not measurements", () => {
    // Ten assays from one study are one opinion.
    const e = edge({ measurements: [
      measurement({ citation_url: "https://x.test/1" }),
      measurement({ citation_url: "https://x.test/1" }),
      measurement({ citation_url: "https://x.test/2" }),
    ]});
    assert.equal(v.paperCount(e), 2);
  });

  test("ignores measurements excluded from the count", () => {
    const e = edge({ measurements: [
      measurement({ citation_url: "https://x.test/1" }),
      measurement({ counted: 0, citation_url: "https://x.test/2" }),
    ]});
    assert.equal(v.paperCount(e), 1);
  });

  test("an edge with no measurements is zero papers, not an error", () => {
    assert.equal(v.paperCount(edge()), 0);
    assert.equal(v.paperCount(edge({ measurements: null })), 0);
  });

  test("counts a paper cited by text when it has no URL", () => {
    // PDSP measurements structurally never carry a citation_url (0/5 in the
    // current build, against ChEMBL's 729/729), and PDSP is the one source
    // here whose corroboration is independent. Filtering on citation_url
    // discarded it from the primary ranking key and rendered "0 papers"
    // beside "1 measurement" on the two edges it backs.
    const e = edge({ measurements: [
      measurement({ name: "PDSP", citation_url: null,
                    citation_text: "Butini S et al., 2008" }),
    ]});
    assert.equal(v.paperCount(e), 1);
  });

  test("a URL and a free-text reference to one study stay two papers", () => {
    // Invariant 15 applied to references: merging them means matching a
    // citation by its name, which would claim cross-database corroboration
    // that might be two different studies. citationKey's identity, shared
    // with the paper index, is what keeps this consistent across the viewer.
    const e = edge({ measurements: [
      measurement({ name: "ChEMBL", citation_url: "https://x.test/1",
                    citation_text: "Butini S et al., 2008" }),
      measurement({ name: "PDSP", citation_url: null,
                    citation_text: "Butini S et al., 2008" }),
    ]});
    assert.equal(v.paperCount(e), 2);
  });

  test("an uncited counted row falls back to its assay, never to zero", () => {
    // Not a paper, but one distinct piece of evidence: counting it as zero
    // would print "1 measurement from 0 papers".
    const e = edge({ measurements: [
      measurement({ citation_url: null, citation_text: null,
                    external_ref: "CHEMBL111" }),
    ]});
    assert.equal(v.paperCount(e), 1);
  });

  test("the ranking key and the panel's summary count the same papers", () => {
    // These are two renderings of one claim about one set of rows. Read off
    // two different field lists they disagreed - the two-panels-disagree
    // failure invariant 13 exists to prevent - so both go through paperKeys.
    const rows = [
      measurement({ name: "ChEMBL", citation_url: "https://x.test/1" }),
      measurement({ name: "ChEMBL", citation_url: "https://x.test/1" }),
      measurement({ name: "PDSP", citation_url: null,
                    citation_text: "Butini S et al., 2008" }),
      measurement({ name: "BindingDB", counted: 0,
                    citation_url: "https://x.test/9" }),
    ];
    const e = edge({ measurements: rows });
    assert.equal(v.paperCount(e), 2);
    assert.equal(v.paperKeys(rows).size, v.paperCount(e));
    assert.match(v.measurementListHTML(rows), /from 2 papers/);
  });
});

describe("measurementCount and databaseCount", () => {
  const v = loadViewer(TARGETS);

  test("takes the larger role, never the sum (invariant 4)", () => {
    // Binding and functional are different physical quantities; adding them
    // would coin a number that appears nowhere else on the page.
    assert.equal(
      v.measurementCount(edge({ n_measurements: 3, functional_n_measurements: 5 })),
      5);
  });

  test("counts databases, not source rows", () => {
    // An edge backed by ChEMBL alone in two roles read as "Sources (2)" and
    // looked like corroboration it wasn't.
    const e = edge({ sources: [
      { name: "ChEMBL", role: "binding" },
      { name: "ChEMBL", role: "functional" },
      { name: "PDSP", role: "binding" },
    ]});
    assert.equal(v.databaseCount(e), 2);
    assert.equal(v.databaseGroups(e).length, 2);
  });
});

describe("compareEvidence - ranking (invariant 7)", () => {
  const v = loadViewer(TARGETS);
  const sorted = (edges) =>
    [...edges].sort((a, b) => v.compareEvidence(a, b, "to")).map(e => e.id);

  test("tier dominates every other key", () => {
    const curated = edge({ id: "curated", to: "tgt_z", is_primary_mechanism: 1,
                           n_measurements: null });
    const heavy = edge({ id: "heavy", to: "tgt_x", n_measurements: 50,
      measurements: Array.from({ length: 20 }, (_, i) =>
        measurement({ citation_url: `https://x.test/${i}` })) });
    assert.deepEqual(sorted([heavy, curated]), ["curated", "heavy"]);
  });

  test("papers outrank raw measurement count", () => {
    const manyAssaysOnePaper = edge({ id: "one-paper", to: "tgt_x",
      n_measurements: 30,
      measurements: [measurement({ citation_url: "https://x.test/1" })] });
    const fewerAssaysThreePapers = edge({ id: "three-papers", to: "tgt_y",
      n_measurements: 3,
      measurements: [1, 2, 3].map(i =>
        measurement({ citation_url: `https://x.test/${i}` })) });
    assert.deepEqual(sorted([manyAssaysOnePaper, fewerAssaysThreePapers]),
                     ["three-papers", "one-paper"]);
  });

  test("affinity never enters the ordering", () => {
    // The tacrine case named in the source comment: a single unreplicated
    // sub-nanomolar IC50 must not outrank the many-paper ACHE result.
    const ache = edge({ id: "ACHE", to: "tgt_x", n_measurements: 14,
      binding_value: 10000,
      measurements: Array.from({ length: 14 }, (_, i) =>
        measurement({ citation_url: `https://x.test/${i}` })) });
    const app = edge({ id: "APP", to: "tgt_y", n_measurements: 2,
      binding_value: 0.5,
      measurements: [measurement({ citation_url: "https://x.test/only" })] });
    assert.deepEqual(sorted([app, ache]), ["ACHE", "APP"]);
  });

  test("two edges alike in evidence are ordered by label, not by affinity", () => {
    const strong = edge({ id: "strong", to: "tgt_y", binding_value: 0.1 });  // ADORA2A
    const weak = edge({ id: "weak", to: "tgt_x", binding_value: 90000 });    // ADORA1
    assert.deepEqual(sorted([strong, weak]), ["weak", "strong"]);
  });

  test("the comparator is a consistent ordering, not just a boolean", () => {
    const a = edge({ id: "a", to: "tgt_x", n_measurements: 5 });
    const b = edge({ id: "b", to: "tgt_y", n_measurements: 5 });
    assert.equal(Math.sign(v.compareEvidence(a, b, "to")),
                 -Math.sign(v.compareEvidence(b, a, "to")));
    assert.equal(v.compareEvidence(a, a, "to"), 0);
  });
});

describe("fanoutRef - the assay fan-out guard", () => {
  const v = loadViewer(TARGETS);

  test("one distinct assay behind the edge returns that assay", () => {
    const e = edge({ measurements: [
      measurement({ external_ref: "CHEMBL636450" }),
      measurement({ external_ref: "CHEMBL636450" }),
    ]});
    assert.equal(v.fanoutRef(e), "CHEMBL636450");
  });

  test("two distinct assays is not a fan-out", () => {
    const e = edge({ measurements: [
      measurement({ external_ref: "A1" }),
      measurement({ external_ref: "A2" }),
    ]});
    assert.equal(v.fanoutRef(e), null);
  });

  test("no assay reference at all is not a fan-out", () => {
    assert.equal(v.fanoutRef(edge()), null);
    assert.equal(v.fanoutRef(edge({ measurements: [measurement()] })), null);
  });

  test("uncounted measurements do not create or break a fan-out", () => {
    const e = edge({ measurements: [
      measurement({ external_ref: "A1" }),
      measurement({ counted: 0, external_ref: "A2" }),
    ]});
    assert.equal(v.fanoutRef(e), "A1");
  });
});

describe("groupFanouts", () => {
  const v = loadViewer(TARGETS);
  const withRef = (id, to, ref) => edge({
    id, to, measurements: [measurement({ external_ref: ref })],
  });

  test("edges sharing one assay collapse into a single group", () => {
    const groups = v.groupFanouts([
      withRef("e1", "tgt_x", "A1"),
      withRef("e2", "tgt_y", "A1"),
      withRef("e3", "tgt_z", "A2"),
    ]);
    assert.equal(groups.length, 2);
    assert.equal(groups[0].ref, "A1");
    assert.deepEqual(plain(groups[0].edges.map(e => e.id)), ["e1", "e2"]);
    assert.equal(groups[1].ref, null, "a lone assay is not a fan-out group");
    assert.deepEqual(plain(groups[1].edges.map(e => e.id)), ["e3"]);
  });

  test("a group is emitted once, at the position of its first member", () => {
    const groups = v.groupFanouts([
      withRef("first", "tgt_x", "A1"),
      withRef("middle", "tgt_z", "A2"),
      withRef("last", "tgt_y", "A1"),
    ]);
    assert.deepEqual(plain(groups.map(g => g.edges.map(e => e.id))),
                     [["first", "last"], ["middle"]]);
  });

  test("edges with no assay reference pass through ungrouped", () => {
    const groups = v.groupFanouts([edge({ id: "e1" }), edge({ id: "e2" })]);
    assert.deepEqual(plain(groups.map(g => g.ref)), [null, null]);
    assert.equal(groups.length, 2);
  });

  test("the rendered group states that it is one finding, not n", () => {
    const groups = v.groupFanouts([
      withRef("e1", "tgt_x", "CHEMBL636450"),
      withRef("e2", "tgt_y", "CHEMBL636450"),
    ]);
    const html = v.fanGroupHTML(groups[0], "to");
    assert.ok(html.includes("2 targets, one assay"));
    assert.ok(html.includes("not 2 independent findings"));
    assert.ok(html.includes("ADORA1, ADORA2A"));
  });
});

describe("edgeListHTML - tier grouping", () => {
  const v = loadViewer(TARGETS);

  test("an empty tier is omitted rather than shown as (0)", () => {
    // Theophylline is curated edges and single-source leads with nothing in
    // between; an empty middle group reads as a missing section, not a zero.
    const html = v.edgeListHTML([
      edge({ id: "c", to: "tgt_x", is_primary_mechanism: 1 }),
      edge({ id: "s", to: "tgt_y", n_measurements: 1 }),
    ], "to");
    assert.ok(html.includes("Curated mechanism (1)"));
    assert.ok(html.includes("Single-source leads (1)"));
    assert.ok(!html.includes("Corroborated ("),
              "the empty middle tier must not render");
  });

  test("every edge lands in exactly one tier", () => {
    const edges = [
      edge({ id: "a", to: "tgt_x", is_primary_mechanism: 1 }),
      edge({ id: "b", to: "tgt_y", n_measurements: 4 }),
      edge({ id: "c", to: "tgt_z", n_measurements: 1 }),
    ];
    const html = v.edgeListHTML(edges, "to");
    for (const e of edges) {
      const hits = html.split(`data-edge-id="${e.id}"`).length - 1;
      assert.equal(hits, 1, `${e.id} should appear once, appeared ${hits}x`);
    }
  });
});

describe("sharedTargets - the similarity engine", () => {
  const nodes = [
    molecule("mol_a", "Caffeine"),
    molecule("mol_b", "Theophylline"),
    molecule("mol_c", "Rolipram"),
    target("tgt_1", "ADORA1", { expressed_in_brain: 1 }),
    target("tgt_2", "ADORA2A", { expressed_in_brain: 1 }),
    target("tgt_3", "PDE4A"),
  ];
  const link = (id, from, to, over = {}) => edge({ id, from, to, ...over });

  test("counts the targets two molecules have in common", () => {
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1"), link("a2", "mol_a", "tgt_2"),
      link("a3", "mol_a", "tgt_3"),
      link("b1", "mol_b", "tgt_1"), link("b2", "mol_b", "tgt_2"),
      link("c3", "mol_c", "tgt_3"),
    ]});
    const rows = v.sharedTargets({ id: "mol_a" });
    assert.deepEqual(plain(rows.map(r => [r.molId, r.shared, r.brain])),
                     [["mol_b", 2, 2], ["mol_c", 1, 0]]);
  });

  test("the molecule itself is never one of its own matches", () => {
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1"), link("b1", "mol_b", "tgt_1"),
    ]});
    assert.deepEqual(plain(v.sharedTargets({ id: "mol_a" }).map(r => r.molId)), ["mol_b"]);
  });

  test("a pair corroborated on neither side is ranked last, NOT dropped", () => {
    // The panel ranks; it does not filter. Turning this into a filter would
    // blank the panel for exactly the molecules with the least evidence -
    // theobromine's rows all read "0 corroborated on both sides" and it must
    // still open on caffeine and theophylline.
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1", { n_measurements: 1 }),
      link("b1", "mol_b", "tgt_1", { n_measurements: 1 }),
    ]});
    const rows = v.sharedTargets({ id: "mol_a" });
    assert.equal(rows.length, 1);
    assert.deepEqual([rows[0].molId, rows[0].shared, rows[0].solid],
                     ["mol_b", 1, 0]);
  });

  test("solid counts only pairs corroborated on both sides", () => {
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1", { n_measurements: 8 }),
      link("b1", "mol_b", "tgt_1", { n_measurements: 8 }),
      link("a2", "mol_a", "tgt_2", { n_measurements: 8 }),
      link("b2", "mol_b", "tgt_2", { n_measurements: 1 }),
    ]});
    const [row] = v.sharedTargets({ id: "mol_a" });
    assert.equal(row.shared, 2);
    assert.equal(row.solid, 1, "the one-sided pair must not count as solid");
  });

  test("one assay hitting a complex is one overlap, not several", () => {
    // The failure this whole grouping exists for: an assay attributed to every
    // member of a protein complex would otherwise manufacture similarity.
    const fan = (id, from, to, ref) => edge({
      id, from, to, measurements: [measurement({ external_ref: ref })],
    });
    const v = loadViewer({ nodes, edges: [
      fan("a1", "mol_a", "tgt_1", "ASSAY_A"),
      fan("a2", "mol_a", "tgt_2", "ASSAY_A"),
      fan("b1", "mol_b", "tgt_1", "ASSAY_B"),
      fan("b2", "mol_b", "tgt_2", "ASSAY_B"),
    ]});
    const [row] = v.sharedTargets({ id: "mol_a" });
    assert.equal(row.shared, 1,
      "two targets from one assay on each side is a single shared finding");
  });

  test("distinct assays on the same targets stay distinct", () => {
    const fan = (id, from, to, ref) => edge({
      id, from, to, measurements: [measurement({ external_ref: ref })],
    });
    const v = loadViewer({ nodes, edges: [
      fan("a1", "mol_a", "tgt_1", "ASSAY_1"),
      fan("a2", "mol_a", "tgt_2", "ASSAY_2"),
      fan("b1", "mol_b", "tgt_1", "ASSAY_3"),
      fan("b2", "mol_b", "tgt_2", "ASSAY_4"),
    ]});
    assert.equal(v.sharedTargets({ id: "mol_a" })[0].shared, 2);
  });

  test("ranks by corroborated pairs, then brain-expressed, then raw overlap", () => {
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1", { n_measurements: 8 }),
      link("a2", "mol_a", "tgt_2", { n_measurements: 8 }),
      link("a3", "mol_a", "tgt_3", { n_measurements: 8 }),
      // Rolipram: three shared targets but none corroborated on its side.
      link("c1", "mol_c", "tgt_1", { n_measurements: 1 }),
      link("c2", "mol_c", "tgt_2", { n_measurements: 1 }),
      link("c3", "mol_c", "tgt_3", { n_measurements: 1 }),
      // Theophylline: one shared target, corroborated on both sides.
      link("b1", "mol_b", "tgt_1", { n_measurements: 8 }),
    ]});
    const rows = v.sharedTargets({ id: "mol_a" });
    assert.deepEqual(plain(rows.map(r => r.molId)), ["mol_b", "mol_c"]);
    assert.deepEqual([rows[0].solid, rows[0].shared], [1, 1]);
    assert.deepEqual([rows[1].solid, rows[1].shared], [0, 3]);
  });

  test("a molecule sharing nothing produces no row", () => {
    const v = loadViewer({ nodes, edges: [
      link("a1", "mol_a", "tgt_1"), link("c3", "mol_c", "tgt_3"),
    ]});
    assert.deepEqual(plain(v.sharedTargets({ id: "mol_a" })), []);
  });
});

describe("small formatters", () => {
  const v = loadViewer(TARGETS);

  test("plural agrees with its count", () => {
    assert.equal(v.plural(1, "measurement"), "1 measurement");
    assert.equal(v.plural(0, "measurement"), "0 measurements");
    assert.equal(v.plural(13, "shared target"), "13 shared targets");
  });

  test("a missing value renders no value line at all", () => {
    assert.equal(v.valueLineHTML("Binding: ", "Ki", null, "nM", 3), "");
  });

  test("a value line escapes the fields it interpolates", () => {
    const html = v.valueLineHTML("Binding: ", `<b>Ki`, 100, `nM"`, 2);
    assert.ok(!html.includes("<b>"), "type must be escaped");
    assert.ok(html.includes("2 measurements"));
  });
});


// ---------------------------------------------------------------------------
// The legend is a claim about what the canvas draws, and it drifted: it showed
// the brain-expressed target with a white rim, which is the *selected*-node
// border colour, while an unselected target is drawn in dark orange. On screen
// that read as "no border at all", and the note under it explained a
// distinction the reader could not see. These tests read both the legend markup
// and the node-styling code out of viz/index.html and hold them to each other.
// ---------------------------------------------------------------------------
describe("the legend agrees with what the canvas draws", () => {
  const html = readFileSync(new URL("../viz/legacy/index.html", import.meta.url), "utf8");
  const legend = html.slice(html.indexOf('<div id="legend">'),
                            html.indexOf('<div id="sidebar">'));
  assert.ok(legend.includes("Brain-expressed target"), "legend block not found");

  const targetBorder = html.match(/border: isMolecule \? "(#[0-9a-f]{6})" : "(#[0-9a-f]{6})"/i);
  const widths = html.match(
    /borderWidth: !isMolecule && n\.expressed_in_brain === 1 \? (\d+) : (\d+)/);

  test("every target swatch uses the border colour unselected nodes are drawn in", () => {
    assert.ok(targetBorder, "could not find the node border colours in the viewer");
    const [, moleculeBorder, drawn] = targetBorder;
    legend.split("\n")
      .filter(line => line.includes("background:#ffb04d"))
      .forEach(line => {
        assert.ok(line.includes(`solid ${drawn}`),
          `a target swatch does not use the drawn border colour ${drawn}: ${line}`);
      });
    assert.ok(legend.includes(`solid ${moleculeBorder}`),
      "the molecule swatch does not use the drawn molecule border colour");
  });

  test("the legend never shows the highlight colour as if it were the resting one", () => {
    // #f2f4f8 was the old swatch rim; the graph only ever draws white (#ffffff)
    // on the *selected* node, so no resting-state swatch may use either.
    assert.ok(!/#f2f4f8/i.test(legend));
    assert.ok(!/solid #ffffff/i.test(legend));
  });

  test("the brain-expressed swatch is as much thicker as the node is", () => {
    assert.ok(widths, "could not find the brain-expression border widths");
    const [, thick, thin] = widths;
    const brainRow = legend.split("\n").find(l => l.includes("Brain-expressed target"));
    const plainRow = legend.split("\n")
      .find(l => l.includes("background:#ffb04d") && !l.includes("Brain-expressed"));
    assert.ok(brainRow.includes(`${thick}px solid`),
      `brain-expressed swatch should be ${thick}px, matching the node`);
    assert.ok(plainRow.includes(`${thin}px solid`),
      `plain target swatch should be ${thin}px, matching the node`);
  });

  test("each block of legend rows says which visual channel it encodes", () => {
    const headings = legend.match(/class="legend-cat"/g) || [];
    assert.ok(headings.length >= 4,
      "shape, rim, line colour and line style each need a heading");
    assert.ok(!/style="height:6px;"/.test(legend),
      "blank spacers were how the blocks used to be separated; headings replace them");
  });

  // A new action_type in the data is silent: actionColor falls back, the edge
  // draws in the fallback colour, and nothing says so. It has happened twice -
  // NEGATIVE ALLOSTERIC MODULATOR fell through to FUNCTIONAL's exact colour,
  // and INVERSE AGONIST (haloperidol's curated D2-family mechanism) fell
  // through to a grey one shade off BINDER's, which means the opposite thing:
  // no curated mechanism at all. These two tests hold the colour map and the
  // legend to each other so the third time fails here instead of on screen.
  const colorMap = html.slice(html.indexOf("const ACTION_COLORS = {"),
                              html.indexOf("function actionColor("));
  const mapped = [...colorMap.matchAll(/"(#[0-9a-f]{6})"/gi)].map(m => m[1].toLowerCase());
  const fallback = html.match(/return ACTION_COLORS\[actionType\] \|\| "(#[0-9a-f]{6})"/i);
  const legendLineColors = [...legend.matchAll(/border-color:(#[0-9a-f]{6});/gi)]
    .map(m => m[1].toLowerCase());

  test("every colour an edge can be drawn in has a legend row", () => {
    assert.ok(mapped.length > 0, "could not read ACTION_COLORS");
    assert.ok(fallback, "could not read the actionColor fallback");
    for (const c of new Set(mapped)) {
      assert.ok(legendLineColors.includes(c),
        `${c} is an action colour with no legend row - a mechanism draws on ` +
        `the canvas that the legend does not name`);
    }
    assert.ok(legendLineColors.includes(fallback[1].toLowerCase()),
      "the fallback colour has no legend row");
  });

  test("the fallback colour is not one of the mapped ones", () => {
    assert.ok(!mapped.includes(fallback[1].toLowerCase()),
      `the fallback ${fallback[1]} is also a named mechanism's colour, so an ` +
      `unrecognised action_type is indistinguishable from that mechanism`);
  });

  test("protein assemblies get one heading, not two", () => {
    // The hexagon was filed under "Node shape" and the enclosure under
    // "Enclosure - protein assemblies", which named the same feature twice in
    // a legend of five headings and read as two unrelated things.
    const headings = [...legend.matchAll(/class="legend-cat"[^>]*>([\s\S]*?)<\/div>/g)]
      .map(m => m[1].replace(/<[\s\S]*?>/g, " "));
    const naming = headings.filter(h => /assembl/i.test(h));
    assert.equal(naming.length, 1,
      `protein assemblies are named by ${naming.length} legend headings`);
  });

  test("the legend's explanations are on hover, not printed under the rows", () => {
    // Five lines of prose per block made the legend tall enough to cover the
    // graph it explains. Same words, same .help markup the panel uses.
    assert.ok(!legend.includes("legend-note"),
      "an inline explanation block is back in the legend");
    const helps = (legend.match(/class="help"/g) || []).length;
    assert.ok(helps >= 2,
      "the assembly and brain-rim blocks each need a reachable explanation");
    assert.equal(helps, (legend.match(/class="help-text"/g) || []).length,
      "a .help with no .help-text is a dotted underline that opens nothing");
  });

  test("a legend explanation opens upwards, away from the bottom of the window", () => {
    // #legend is pinned to the bottom-left corner, so the panel's downward
    // .help-text would open off the bottom of the screen - which is exactly how
    // the tier explanations became unreachable.
    assert.match(html, /\.legend-cat \.help-text \{[^}]*bottom:\s*100%/,
      "the legend's help box must open above its heading");
  });
});

// ---------------------------------------------------------------------------
// Every heading in the panel is a piece of vocabulary this project uses in a
// specific, easily-confused way, so each one carries a hover explanation. The
// tier headings *had* one and it was unreachable: .help-text is absolutely
// positioned, and .tier > summary was not a positioned ancestor, so the box
// anchored to the viewport and opened below the fold. An explanation nobody can
// open is the same as no explanation, which is how this got reported as missing.
// ---------------------------------------------------------------------------
describe("panel headings carry a reachable explanation", () => {
  const v = loadViewer(TARGETS);

  const anchored = sel => new RegExp(
    `${sel}\\s*\\{[^}]*position:\\s*relative`);
  const css = readFileSync(new URL("../viz/legacy/index.html", import.meta.url), "utf8");

  test("a hover explanation is anchored to its own heading, not the viewport", () => {
    [".tier > summary", ".fangroup > summary", ".section-toggle > summary",
     ".panel-section h2", ".field .k", ".result-group h3",
     ".filter-row", ".cxgroup > summary", ".grouping-head",
     ".grouping-tier", ".legend-cat", "#view-options > summary"].forEach(sel => {
      assert.match(css, anchored(sel.replace(/[.>*+?^${}()|[\]\\]/g, "\\$&")),
        `${sel} must be position: relative or its .help-text opens off-screen`);
    });
  });

  test("every evidence tier heading has an explanation to show", () => {
    ["Curated mechanism", "Corroborated", "Single-source leads"].forEach(label => {
      assert.ok(v.helpLabel(label).includes('class="help-text"'),
        `the "${label}" heading has no explanation`);
    });
  });

  test("every helpLabel key the grouping feature uses resolves to real help text", () => {
    // Same failure mode as the tier headings above, transplanted onto the
    // assembly feature: a key that helpLabel doesn't recognise renders as
    // plain escaped text with no .help-text span at all, silently dropping
    // the explanation rather than erroring.
    ["Protein assemblies", "Show every subunit individually",
     "One receptor, many subunits", "Part of an assembly", "ChEMBL type",
     "Subunits", "Complexes inside this", "How this is drawn"].forEach(key => {
      assert.ok(v.helpLabel(key, key).includes('class="help-text"'),
        `the "${key}" heading has no explanation`);
    });
  });

  test("edgeListHTML attaches the explanation to the heading it counts", () => {
    const html = v.edgeListHTML([
      edge({ id: "e1", to: "tgt_x", is_primary_mechanism: 1 }),
      edge({ id: "e2", to: "tgt_y" }),
    ], "to");
    assert.match(html, /Curated mechanism \(1\)<\/span><span class="help-text">/);
    assert.match(html, /Single-source leads \(1\)<\/span><span class="help-text">/);
  });

  test("the fan-out row explains why many targets are one finding", () => {
    const fan = (id, to) => edge({
      id, to, measurements: [measurement({ external_ref: "CHEMBL4613617" })],
    });
    const groups = v.groupFanouts([fan("e1", "tgt_x"), fan("e2", "tgt_y")]);
    const html = v.fanGroupHTML(groups[0], "to");
    assert.match(html, /2 targets, one assay<\/span><span class="help-text">/);
    assert.ok(html.includes("One experiment, not this many findings"));
  });

  test("the fan-out summary escapes its value once, not twice", () => {
    // The value moved inside helpLabel(), which escapes; pre-escaping it there
    // too would render "&amp;lt;" to the reader.
    const fan = (id, to) => edge({
      id, to, binding_value: 17000, binding_type: "IC50<b>", binding_units: "nM",
      measurements: [measurement({ external_ref: "A1" })],
    });
    const groups = v.groupFanouts([fan("e1", "tgt_x"), fan("e2", "tgt_y")]);
    const html = v.fanGroupHTML(groups[0], "to");
    assert.ok(html.includes("IC50&lt;b&gt; 17,000 nM"));
    assert.ok(!html.includes("&amp;lt;"), "value was escaped twice");
  });
});

// ---------------------------------------------------------------------------
// "Shares targets with" is the section closest to the question the graph exists
// to answer, so it stays open by default - but it sits below a target list that
// runs to 46 rows, and a reader should be able to fold it away.
// ---------------------------------------------------------------------------
describe("sharedTargetsHTML - a section the reader can fold away", () => {
  const graph = {
    nodes: [
      molecule("mol_a", "Caffeine"),
      molecule("mol_b", "Theophylline"),
      target("tgt_x", "ADORA1", { expressed_in_brain: 1 }),
    ],
    edges: [
      edge({ id: "e1", from: "mol_a", to: "tgt_x" }),
      edge({ id: "e2", from: "mol_b", to: "tgt_x" }),
    ],
  };
  const v = loadViewer(graph);
  const html = v.sharedTargetsHTML(graph.nodes[0]);

  test("renders as a disclosure, open by default", () => {
    assert.ok(html.includes('<details class="section-toggle" open>'));
  });

  test("the disclosure wraps the rows and is closed exactly once", () => {
    assert.equal((html.match(/<details/g) || []).length, 1);
    assert.equal((html.match(/<\/details>/g) || []).length, 1);
    assert.ok(html.indexOf("Theophylline") > html.indexOf("<details"));
    assert.ok(html.indexOf("Theophylline") < html.indexOf("</details>"));
  });

  test("the heading keeps its count and its explanation", () => {
    assert.match(html, /Shares targets with \(1\)<\/span><span class="help-text">/);
  });

  test("a molecule that shares nothing renders no section to collapse", () => {
    const lone = loadViewer({ nodes: graph.nodes, edges: [graph.edges[0]] });
    assert.equal(lone.sharedTargetsHTML(graph.nodes[0]), "");
  });
});

// ---------------------------------------------------------------------------
// Search
//
// The panel could previously only be reached by clicking, which meant a
// molecule the reader already knew the name of had to be found by eye in a
// 155-node graph. What is locked in below is not that search works but what it
// is allowed to claim: which field a hit came from (so an exact match on an
// accession cannot outrank a partial match on the gene symbol it belongs to),
// that a capped list says how much it capped, and that a query is escaped on
// the way back onto the page.
// ---------------------------------------------------------------------------

const SEARCH_GRAPH = {
  nodes: [
    molecule("mol_1", "Caffeine", {
      iupac_name: "1,3,7-trimethylpurine-2,6-dione",
      molecular_formula: "C8H10N4O2",
      chembl_id: "CHEMBL113",
      pubchem_cid: 2519,
    }),
    molecule("mol_2", "Theophylline", { chembl_id: "CHEMBL190" }),
    target("tgt_1", "ADORA1", {
      protein_name: "Adenosine receptor A1",
      uniprot_accession: "P30542",
      expressed_in_brain: 1,
    }),
    target("tgt_2", "PDE4A", {
      protein_name: "cAMP-specific 3',5'-cyclic phosphodiesterase 4A",
      uniprot_accession: "P27815",
    }),
  ],
  edges: [
    edge({
      id: "int_1", from: "mol_1", to: "tgt_1", action_type: "ANTAGONIST",
      is_primary_mechanism: 1,
      mechanism_of_action: "Adenosine A1 receptor antagonist",
      n_measurements: 3,
      measurements: [
        measurement({ value: 10000, citation_url: "https://pubmed.ncbi.nlm.nih.gov/111/", citation_text: "Fredholm 2001" }),
        measurement({ value: 12000, citation_url: "https://pubmed.ncbi.nlm.nih.gov/111/", citation_text: "Fredholm 2001" }),
        measurement({ value: 14000, citation_url: "https://pubmed.ncbi.nlm.nih.gov/222/", citation_text: "Daly 1999" }),
        measurement({
          counted: 0, name: "BindingDB", value: 11000,
          citation_url: "https://www.bindingdb.org/rwd/bind/chemsearch/marvin/MolStructure.jsp?monomerid=10849",
          citation_text: "BindingDB BDBM10849",
        }),
      ],
      sources: [
        { name: "ChEMBL", role: "binding" },
        { name: "ChEMBL", role: "annotation", citation_kind: "mechanism",
          citation_url: "https://pubmed.ncbi.nlm.nih.gov/111/", citation_text: "PubMed 111" },
        { name: "DGIdb", role: "annotation", citation_kind: "annotation",
          citation_url: null, citation_text: "PharmGKB, TTD" },
      ],
    }),
    edge({
      id: "int_2", from: "mol_2", to: "tgt_1", action_type: "ANTAGONIST",
      n_measurements: 1,
      measurements: [
        measurement({ value: 8000, citation_url: "https://pubmed.ncbi.nlm.nih.gov/222/", citation_text: "Daly 1999" }),
      ],
    }),
    edge({
      id: "int_3", from: "mol_2", to: "tgt_2", action_type: "INHIBITOR",
      n_measurements: null, functional_n_measurements: 2,
      measurements: [
        measurement({ role: "functional", affinity_type: "IC50", value: 90,
                      citation_url: "https://pubmed.ncbi.nlm.nih.gov/222/", citation_text: "Daly 1999" }),
        measurement({ role: "functional", affinity_type: "IC50", value: 110,
                      citation_url: "https://pubmed.ncbi.nlm.nih.gov/333/", citation_text: "Beavo 1988" }),
      ],
    }),
  ],
};

const PUBMED_111 = "u:https://pubmed.ncbi.nlm.nih.gov/111/";
const PUBMED_222 = "u:https://pubmed.ncbi.nlm.nih.gov/222/";
const BINDINGDB_KEY =
  "u:https://www.bindingdb.org/rwd/bind/chemsearch/marvin/MolStructure.jsp?monomerid=10849";

describe("matchRank - where in a field the query landed", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("exact, prefix, word-start and mid-word are four different answers", () => {
    assert.equal(v.matchRank("ADORA1", "adora1"), 0);
    assert.equal(v.matchRank("ADORA1", "adora"), 1);
    // The edge label puts the gene after an arrow, so the hit starts a word.
    assert.equal(v.matchRank("Caffeine → ADORA1", "adora"), 2);
    assert.equal(v.matchRank("XADORA1", "adora"), 3);
    assert.equal(v.matchRank("ADORA1", "pde"), null);
  });

  test("a missing field is not a match rather than a crash", () => {
    assert.equal(v.matchRank(null, "x"), null);
    assert.equal(v.matchRank("ADORA1", ""), null);
  });
});

describe("recordRank - which field the hit came from decides the rank", () => {
  const v = loadViewer(SEARCH_GRAPH);
  const one = ["x"];

  test("any match in the name outranks every match in a later field", () => {
    // The case this exists for: searching an accession finds ADORA1, but a
    // partial match on a gene symbol is still the better answer to "adora"
    // than an exact match on some other protein's accession.
    const nameSubstring = v.recordRank(["XADORA1", null, "P30542"], "adora", one);
    const accessionExact = v.recordRank(["ADORA1", null, "P30542"], "p30542", one);
    assert.ok(nameSubstring < accessionExact,
      "a substring of the name must beat an exact hit on a third-position field");
  });

  test("words scattered across fields match, and rank below every whole-string hit", () => {
    const scattered = v.recordRank(
      ["Caffeine → ADORA1", "ANTAGONIST", null], "caffeine antagonist",
      ["caffeine", "antagonist"]);
    const whole = v.recordRank(["Caffeine → ADORA1", "ANTAGONIST", null], "antagonist", ["antagonist"]);
    assert.ok(scattered > whole,
      "a scattered match is the weakest kind and must sort last");
  });

  test("every term must be present, and one term never falls back to scattering", () => {
    assert.equal(
      v.recordRank(["Caffeine → ADORA1", "ANTAGONIST"], "caffeine inhibitor",
                   ["caffeine", "inhibitor"]),
      null, "'inhibitor' is in neither field - the record must not match");
    assert.equal(v.recordRank(["Caffeine"], "zzz", ["zzz"]), null);
  });
});

describe("highlightMatch escapes around the marker (invariant 11)", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("the matched run is marked and the rest is still escaped", () => {
    const html = v.highlightMatch("Effects of <b>caffeine</b> & theophylline", "caffeine");
    assert.ok(html.includes("<mark>caffeine</mark>"), "the hit must be marked");
    assert.ok(!html.includes("<b>"), "upstream markup must not survive");
    assert.ok(html.includes("&lt;b&gt;") && html.includes("&amp;"),
      "the text either side of the hit must still be escaped");
  });

  test("a query containing markup characters is escaped, not doubly escaped", () => {
    // Escaping the whole string first would move every offset (& -> &amp;) and
    // the marker would land in the wrong place; escaping after inserting the
    // tags would escape the tags. Both are why this slices before escaping.
    const html = v.highlightMatch("Smith & Jones 1999", "& jones");
    assert.ok(html.includes("<mark>&amp; Jones</mark>"),
      `matched run should be escaped exactly once, got: ${html}`);
    assert.ok(!html.includes("&amp;amp;"), "must not double-escape");
  });

  test("no match yields escaped text and no marker at all", () => {
    const html = v.highlightMatch("<i>title</i>", "zzz");
    assert.equal(html, "&lt;i&gt;title&lt;/i&gt;");
  });
});

describe("common molecule names", () => {
  const graph = {
    nodes: [
      molecule("mol_thc", "Dronabinol", {
        aliases: ["Marinol", "THC", "Delta-9-THC", "Tetrahydrocannabinol"],
      }),
      molecule("mol_cbd", "Cannabidiol", { aliases: ["CBD", "Epidiolex"] }),
      target("tgt_cnr1", "CNR1", { expressed_in_brain: 1 }),
    ],
    edges: [edge({ id: "int_thc", from: "mol_thc", to: "tgt_cnr1" })],
  };
  const v = loadViewer(graph);

  test("common names find the canonical molecule once, regardless of case", () => {
    for (const query of ["thc", "  ThC  ", "tetrahydrocannabinol", "marin", "Dronabinol"]) {
      assert.deepEqual(plain(v.searchGraph(query).molecules.map(r => r.node.label)), ["Dronabinol"]);
    }
    assert.equal(v.searchGraph("CBD").molecules[0].node.label, "Cannabidiol");
    assert.equal(v.searchGraph("delta-8").total, 0);
  });

  test("results explain the best alias match and select the original node", () => {
    const html = v.searchResultsHTML(v.searchGraph("thc"));
    assert.match(html, /data-node-id="mol_thc"/);
    assert.match(html, /Dronabinol/);
    assert.match(html, /Also known as THC/);
  });

  test("aliases work in combined molecule-target searches and highlights", () => {
    const results = v.searchGraph("THC CNR1");
    assert.deepEqual(plain(results.edges.map(r => r.edge.id)), ["int_thc"]);
    const { keepNodes, keepEdges } = v.searchHighlight(v.searchGraph("THC"));
    assert.ok(keepNodes.has("mol_thc"));
    assert.ok(keepEdges.has("int_thc"));
  });

  test("alias priority is independent of alias order and beats systematic names", () => {
    const w = loadViewer({ nodes: [
      molecule("mol_alias", "Dronabinol", { aliases: ["Marinol", "Syndros", "THC"] }),
      molecule("mol_systematic", "Other", { iupac_name: "THC" }),
      molecule("mol_name", "THC"),
    ], edges: [] });
    assert.deepEqual(plain(w.searchGraph("THC").molecules.map(r => r.node.id)),
      ["mol_name", "mol_alias", "mol_systematic"]);
  });

  test("alias text is escaped in search results", () => {
    const w = loadViewer({ nodes: [molecule("mol_x", "Example", {
      aliases: ['<img src=x onerror=1>'],
    })], edges: [] });
    const html = w.searchResultsHTML(w.searchGraph("<img"));
    assert.ok(!html.includes("<img"));
    assert.match(html, /Also known as &lt;img/);
  });
});

describe("searchGraph", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("a query shorter than two characters returns nothing to render", () => {
    // Every SMILES and half the gene symbols contain any single letter; one
    // character is not a query, it is the whole graph.
    assert.equal(v.searchGraph("c"), null);
    assert.equal(v.searchGraph("  "), null);
  });

  test("molecules match on name, systematic name, formula and database id", () => {
    const names = q => plain(v.searchGraph(q).molecules.map(r => r.node.label));
    assert.deepEqual(names("caff"), ["Caffeine"]);
    assert.deepEqual(names("trimethylpurine"), ["Caffeine"]);
    assert.deepEqual(names("C8H10N4O2"), ["Caffeine"]);
    assert.deepEqual(names("CHEMBL113"), ["Caffeine"]);
    assert.deepEqual(names("2519"), ["Caffeine"]);
  });

  test("targets match on gene symbol, protein name and UniProt accession", () => {
    const names = q => plain(v.searchGraph(q).targets.map(r => r.node.label));
    assert.deepEqual(names("adora"), ["ADORA1"]);
    assert.deepEqual(names("phosphodiesterase"), ["PDE4A"]);
    assert.deepEqual(names("P30542"), ["ADORA1"]);
  });

  test("an interaction is findable by either end, by mechanism, or by action type", () => {
    const ids = q => plain(v.searchGraph(q).edges.map(r => r.edge.id));
    assert.deepEqual(ids("antagonist").sort(), ["int_1", "int_2"]);
    assert.deepEqual(ids("Adenosine A1 receptor antagonist"), ["int_1"]);
    // Two words that never appear adjacent in any one field: this is how
    // someone asks for one specific edge, and it has to reach exactly it.
    assert.deepEqual(ids("caffeine adora1"), ["int_1"]);
  });

  test("a paper is findable by its PubMed ID, not only by its title", () => {
    // The likeliest way someone arrives holding a specific paper: they have
    // the PMID or the DOI, not the exact title string. Both live in the URL,
    // which is indexed as a field of its own for this reason.
    const byPmid = plain(v.searchGraph("111").papers.map(r => r.citation.text));
    assert.deepEqual(byPmid, ["Fredholm 2001"]);
  });

  test("a nonexistent term matches nothing rather than everything", () => {
    const res = v.searchGraph("zzzz");
    assert.equal(res.total, 0);
  });
});

describe("the citation index - one paper, however it arrived", () => {
  const v = loadViewer(SEARCH_GRAPH);
  const found = v.citations();

  test("the same paper as a measurement citation and as a mechanism reference is one entry", () => {
    // ChEMBL cites PubMed 111 twice over: once per activity record behind the
    // value, and once on the mechanism link, where its display text is the
    // bare "PubMed 111". Keyed on the URL they are one paper; keyed on the
    // text they would be two, and the reader would be shown the same study
    // as two separate contributors.
    assert.ok(found.has(PUBMED_111));
    const c = found.get(PUBMED_111);
    assert.equal(c.measurements.length, 2);
    assert.equal(c.refs.length, 1);
  });

  test("a citation with no link is keyed on its text and still findable", () => {
    // DGIdb names the curating databases when a claim carries no publication.
    assert.ok(found.has("t:PharmGKB, TTD"));
    assert.equal(found.get("t:PharmGKB, TTD").url, null);
  });

  test("a source link carrying neither a URL nor text creates no citation", () => {
    // 257 of the 342 source links carry no citation at all; each is a pointer
    // to a database, not a reference, and an entry per one would be 257 blank
    // rows in the search index.
    const empty = loadViewer({
      nodes: [molecule("mol_a", "A"), target("tgt_x", "X")],
      edges: [edge({ sources: [{ name: "ChEMBL", role: "binding" }] })],
    });
    assert.equal(empty.citations().size, 0);
  });

  test("measurements and references are counted apart, never summed", () => {
    // Invariant 13. "3 things" would put a Ki determination and a database's
    // note that the edge exists into one number.
    const s = plain(v.citationSummary(v.citations().get(PUBMED_111)));
    assert.deepEqual(s, { edges: 1, measurements: 2, counted: 2, refs: 1 });
    const text = v.citationSummaryText(v.citations().get(PUBMED_111));
    assert.match(text, /2 measurements/);
    assert.match(text, /1 reference/);
    assert.ok(!/3 /.test(text), `the two kinds must not be added: ${text}`);
  });

  test("rows a source republishes are counted, and flagged as not counted", () => {
    const s = plain(v.citationSummary(v.citations().get(BINDINGDB_KEY)));
    assert.equal(s.measurements, 1);
    assert.equal(s.counted, 0);
    assert.match(v.citationSummaryText(v.citations().get(BINDINGDB_KEY)),
                 /1 measurement \(1 not counted\)/);
  });
});

describe("citationNote - not every citation here is a study", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("an ordinary publication gets no note", () => {
    assert.equal(v.citationNote({ url: "https://pubmed.ncbi.nlm.nih.gov/111/", text: "x" }), null);
    assert.equal(v.citationNote({ url: "https://doi.org/10.1000/x", text: "x" }), null);
  });

  test("a BindingDB compound record says it is not a publication", () => {
    // It is indexed rather than hidden - someone who searches "BindingDB"
    // should find it - so the panel is where it has to say what it is.
    const note = v.citationNote(v.citations().get(BINDINGDB_KEY));
    assert.match(note, /not a publication/);
  });

  test("a reference with no link says so rather than passing for a paper", () => {
    assert.match(v.citationNote({ url: null, text: "PharmGKB, TTD" }), /No link recorded/);
  });

  test("an FDA label is named as a label", () => {
    assert.match(v.citationNote({ url: "https://www.accessdata.fda.gov/x", text: "FDA 1234" }),
                 /not a study/);
  });
});

describe("what a citation contributed to one edge", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("a paper's weight is stated against the edge's own total, not on its own", () => {
    // "2 measurements" says nothing about how much of the median is this
    // paper's. "2 of 3" is the number a reader chasing a claim needs.
    const html = v.citationPanelHTML(v.citations().get(PUBMED_111));
    assert.match(html, /2 of 3 binding measurements pooled into this edge/);
  });

  test("binding and functional are separate lines (invariant 4)", () => {
    const html = v.citationPanelHTML(v.citations().get(PUBMED_222));
    assert.match(html, /1 of 3 binding measurements/);
    assert.match(html, /1 of 2 functional measurements/);
  });

  test("an uncounted row says it reached no value, rather than reading as 0 of n", () => {
    const html = v.citationPanelHTML(v.citations().get(BINDINGDB_KEY));
    assert.match(html, /none counted toward the value on this edge/);
    assert.ok(!/0 of /.test(html), "'0 of 3 measurements pooled' is not a sentence");
  });

  test("measurements and references get their own headings on the panel", () => {
    const html = v.citationPanelHTML(v.citations().get(PUBMED_111));
    assert.match(html, /Measurements contributed \(2\)/);
    assert.match(html, /Cited as a reference \(1\)/);
    assert.match(html, /contributes no measurement/);
  });

  test("a citation's edges are ranked by evidence, like every other edge list", () => {
    // Same rule as a molecule's target list: curated first, then corroborated,
    // then leads. Daly 1999 backs one of each.
    const html = v.citationPanelHTML(v.citations().get(PUBMED_222));
    const order = [...html.matchAll(/data-edge-id="(int_\d)"/g)].map(m => m[1]);
    assert.deepEqual(order, ["int_1", "int_3", "int_2"]);
  });
});

describe("search results say how much they are not showing", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("a group heading counts every match, not the rows drawn", () => {
    // A capped list that prints its cap as the count is a list claiming the
    // answer is smaller than it is.
    const many = {
      nodes: [
        molecule("mol_1", "Caffeine"),
        ...Array.from({ length: 12 }, (_, i) => target(`tgt_${i}`, `PDE${i}A`)),
      ],
      edges: [],
    };
    const w = loadViewer(many);
    const html = w.searchResultsHTML(w.searchGraph("PDE"));
    assert.match(html, /Targets \(12\)/);
    assert.equal((html.match(/class="result-item"/g) || []).length, 8);
    assert.match(html, /4 more not shown/);
  });

  test("an empty result escapes the query it echoes back", () => {
    const html = v.searchResultsHTML(v.searchGraph('<img src=x onerror=1>'));
    assert.ok(!html.includes("<img"), "the query must not be re-emitted as markup");
    assert.match(html, /&lt;img/);
  });

  test("every result row names what it opens", () => {
    const html = v.searchResultsHTML(v.searchGraph("adora"));
    assert.match(html, /data-node-id="tgt_1"/);
    assert.match(html, /data-edge-id="int_1"/);
    const papers = v.searchResultsHTML(v.searchGraph("Fredholm"));
    assert.match(papers, /data-citation-key="u:https/);
  });
});

describe("what a search lights up on the graph", () => {
  const v = loadViewer(SEARCH_GRAPH);

  test("an edge between two matched nodes is kept, though it is not itself a hit", () => {
    // Without this, searching "adora" dims the very lines that make ADORA1 a
    // hub, and the result reads as a scatter of unconnected dots.
    const { keepNodes, keepEdges } = v.searchHighlight(v.searchGraph("theophylline"));
    assert.ok(keepNodes.has("mol_2"));
    assert.ok(keepEdges.has("int_2") && keepEdges.has("int_3"),
      "the matched molecule's edges are matched too, via the edge label");
  });

  test("a paper lights every edge it touches, and their endpoints", () => {
    const { keepNodes, keepEdges } = v.searchHighlight(v.searchGraph("Daly"));
    assert.deepEqual([...keepEdges].sort(), ["int_1", "int_2", "int_3"]);
    assert.deepEqual([...keepNodes].sort(), ["mol_1", "mol_2", "tgt_1", "tgt_2"]);
  });

  test("a match on one node alone keeps that node and nothing else", () => {
    const { keepNodes, keepEdges } = v.searchHighlight(v.searchGraph("P30542"));
    assert.deepEqual([...keepNodes], ["tgt_1"]);
    assert.equal(keepEdges.size, 0);
  });

  test("keeping no edges dims them, rather than reading as 'keep them all'", () => {
    // The condition is one decision about the whole picture, not one per
    // channel. Read per-channel, an empty edge set means "every edge bright" -
    // which is harmless for a selection, whose node always keeps its own
    // edges, and lit every line in the graph for a search that matched a
    // target by its accession.
    const o = v.highlightOpacity(new Set(["tgt_1"]), new Set(), new Set(), new Set());
    assert.equal(o.nodes.get("tgt_1"), 1);
    assert.equal(o.nodes.get("mol_1"), 0.12);
    assert.equal(o.edges.get("int_1"), 0.06, "no edge was kept, so none is bright");
  });

  test("keeping nothing at all is the unfiltered graph", () => {
    const o = v.highlightOpacity(new Set(), new Set(), new Set(), new Set());
    assert.equal(o.nodes.get("mol_1"), 1);
    assert.equal(o.edges.get("int_1"), 0.9);
  });

  test("a selection's second hop sits between the neighbourhood and the rest", () => {
    // Selecting caffeine keeps its own edges, and echoes theophylline in at
    // an intermediate opacity because it is on the same target - the whole
    // point of the graph, and what used to be dimmed to nothing.
    const o = v.highlightOpacity(
      new Set(["mol_1", "tgt_1"]), new Set(["int_1"]),
      new Set(["mol_2"]), new Set(["int_2"]));
    assert.equal(o.nodes.get("mol_1"), 1);
    assert.equal(o.nodes.get("mol_2"), 0.55);
    assert.equal(o.nodes.get("tgt_2"), 0.12);
    assert.equal(o.edges.get("int_1"), 0.9);
    assert.equal(o.edges.get("int_2"), 0.3);
    assert.equal(o.edges.get("int_3"), 0.06);
  });
});

// ---------------------------------------------------------------------------
// The brain filter.
//
// This is the only control on the page that removes things rather than marking
// them, and it removes them on a field that cannot support a negative:
// expressed_in_brain is 1 or NULL and never 0 (invariant 10). So the tests
// here are not about the checkbox working - they are about the filter telling
// the truth while it is on, and about the canvas, the panel lists, the
// similarity ranking and the search all hiding the same set. Four views that
// can disagree about what is on screen is how a picture goes wrong while every
// number in it stays correct.
// ---------------------------------------------------------------------------
describe("the brain filter hides unverified targets, and says so", () => {
  // ACHE stands in for the real problem: a target every reader knows is in the
  // brain, that UniProt gives no tissue comment for. Galantamine acts on
  // nothing else, so filtering removes the molecule outright.
  const nodes = [
    molecule("mol_a", "Caffeine"),
    molecule("mol_g", "Galantamine"),
    target("tgt_1", "ADORA1", { expressed_in_brain: 1 }),
    target("tgt_2", "ADORA2A", { expressed_in_brain: 1 }),
    target("tgt_ache", "ACHE"),
  ];
  const edges = [
    edge({ id: "a1", from: "mol_a", to: "tgt_1" }),
    edge({ id: "a2", from: "mol_a", to: "tgt_2" }),
    edge({ id: "aA", from: "mol_a", to: "tgt_ache" }),
    edge({ id: "gA", from: "mol_g", to: "tgt_ache" }),
  ];
  const loaded = () => loadViewer({ nodes, edges });
  const on = () => { const v = loaded(); v.setFilter("brainOnly", true); return v; };

  test("off by default, and off means nothing is hidden", () => {
    const v = loaded();
    assert.equal(v.filterOn("brainOnly"), false);
    assert.ok(nodes.every(n => v.nodeVisible(n)));
    assert.ok(edges.every(e => v.edgeVisible(e)));
  });

  test("on, a target survives only on a positive tissue comment", () => {
    const v = on();
    assert.equal(v.nodeVisible(nodes[2]), true, "ADORA1 is confirmed");
    assert.equal(v.nodeVisible(nodes[4]), false, "ACHE is unverified");
  });

  test("an edge goes exactly when its target goes", () => {
    const v = on();
    assert.deepEqual(edges.filter(e => v.edgeVisible(e)).map(e => e.id),
                     ["a1", "a2"]);
  });

  test("no edge is ever left on screen with a hidden end", () => {
    // The failure this rules out is an edge drawn to nothing: vis keeps
    // painting a line whose node is hidden, so the picture grows stubs.
    const v = on();
    edges.filter(e => v.edgeVisible(e)).forEach(e => {
      assert.ok(v.nodeVisible(v.nodeById(e.from)) && v.nodeVisible(v.nodeById(e.to)),
        `${e.id} is drawn but one of its ends is not`);
    });
  });

  test("a molecule goes only when the filter took everything it acts on", () => {
    const v = on();
    assert.equal(v.nodeVisible(nodes[0]), true, "caffeine keeps two targets");
    assert.equal(v.nodeVisible(nodes[1]), false, "galantamine has only ACHE");
  });

  test("the panel heading counts what is shown against what exists", () => {
    const v = loaded();
    const mine = edges.filter(e => e.from === "mol_a");
    assert.equal(v.rowCountLabel(mine, "to"), "3");
    v.setFilter("brainOnly", true);
    assert.equal(v.rowCountLabel(mine, "to"), "2 of 3",
      "a heading that reported only the shortened count would hide the filter");
  });

  test("the edge list says how many rows the filter took", () => {
    const v = on();
    const html = v.edgeListHTML(edges.filter(e => e.from === "mol_a"), "to");
    assert.match(html, /1 row hidden by/);
    assert.match(html, /unverified, not absent/,
      "the note must not let 'hidden' read as 'not in the brain'");
    assert.ok(!html.includes("ACHE"), "the hidden row is gone from the list");
  });

  test("similarity is recomputed on what is visible, not on the whole graph", () => {
    // Caffeine and galantamine share only ACHE. With the filter on they share
    // nothing, and the row has to disappear - a similarity claim resting
    // entirely on a target the reader has hidden is the ranking disagreeing
    // with the picture.
    const v = loaded();
    assert.deepEqual(plain(v.sharedTargets({ id: "mol_a" }).map(r => r.molId)),
                     ["mol_g"]);
    v.setFilter("brainOnly", true);
    assert.deepEqual(plain(v.sharedTargets({ id: "mol_a" })), []);
  });

  test("search does not offer a result that is not on the graph", () => {
    const v = loaded();
    assert.equal(v.searchGraph("ACHE").targets.length, 1);
    v.setFilter("brainOnly", true);
    assert.equal(v.searchGraph("ACHE").targets.length, 0,
      "clicking it would scroll the canvas to a hidden node");
    assert.equal(v.searchGraph("Galantamine").molecules.length, 0);
  });

  test("the control states its cost, counted from the data", () => {
    const v = loaded();
    const s = plain(v.brainFilterStats());
    assert.equal(s.keptTargets, 2);
    assert.equal(s.droppedTargets, 1);
    assert.deepEqual(s.notable, ["ACHE"]);
    assert.deepEqual(s.orphaned, ["Galantamine"],
      "a molecule the filter would delete outright has to be named");
  });

  test("the note calls what it hides unverified, never absent", () => {
    // The one sentence this whole feature depends on. expressed_in_brain is 1
    // or NULL and never 0, so "hidden" is a gap in UniProt and not a finding,
    // and a filter that let the reader read it the other way would be turning
    // a missing tissue comment into a claim this database cannot make.
    const v = loaded();
    const html = v.filtersHTML();
    assert.match(html, /unverified/);
    assert.match(html, /not known to be absent/);
    assert.match(html, /Galantamine/);
    assert.ok(v.helpLabel("Confirmed brain-expressed targets only")
      .includes('class="help-text"'), "the filter label needs an explanation");
  });

  test("the banner is on screen for as long as the filter is", () => {
    // Rendered by filterBannersHTML, outside the collapsible control block, so
    // that folding the controls away cannot fold away what they are doing. The
    // whole argument for allowing a filter that removes things is that it says
    // its cost, and a cost the reader has to open a disclosure to see is not
    // being said.
    const v = loaded();
    assert.ok(!v.filterBannersHTML().includes("filter-active"));
    v.setFilter("brainOnly", true);
    assert.match(v.filterBannersHTML(), /class="filter-active"/);
    assert.match(v.filterBannersHTML(), /2 of 3 targets/);
    assert.match(v.filterBannersHTML(), /1 of 2 molecules/);
    assert.ok(!v.filtersHTML().includes("filter-active"),
      "the banner must not also be inside the block that collapses");
  });

  test("the collapsed control line names every setting it is hiding", () => {
    // The controls fold to one line so a selection is not pushed below a
    // screenful of prose. Folding them must not hide a setting that has been
    // changed: a reader who turned the filter on and closed the block can still
    // read that they did.
    const v = loaded();
    assert.match(v.viewOptionsSummary(), /all targets/);
    v.setFilter("brainOnly", true);
    assert.match(v.viewOptionsSummary(), /brain filter on/);
  });

  test("the checkbox reflects the state it is in", () => {
    const v = loaded();
    assert.ok(!v.filtersHTML().includes("checked"));
    v.setFilter("brainOnly", true);
    assert.match(v.filtersHTML(), /id="filter-brain" checked/);
  });

  test("a target panel opened on a hidden target still lists its molecules", () => {
    // Reached from a link or a stale selection rather than the canvas. The
    // filter shortens the overview; it does not blank a thing the reader has
    // explicitly opened, because the molecules binding ACHE are still on the
    // graph and still the answer to what was asked.
    const v = on();
    const rows = v.visibleRows(edges.filter(e => e.to === "tgt_ache"), "from");
    assert.deepEqual(rows.map(e => e.id), ["aA"],
      "caffeine survives the filter, so its row stays; galantamine's goes");
  });
});

// ---------------------------------------------------------------------------
// Protein assembly grouping.
//
// GRAPH_DATA grew a third top-level key, `groups`, carrying ChEMBL's own
// typing of which targets are subunits of one physical receptor or channel.
// Every test below is either locking in the correction that typing makes
// possible (a shared receptor counted once, not once per subunit) or holding
// the four things that read `groupMode` - the canvas, the panel lists, the
// ranking and the highlighter - to agreeing with each other, the same
// standard invariant 10 already holds the brain filter to.
// ---------------------------------------------------------------------------

describe("loadViewer's own default has no groups key at all", () => {
  // The harness's default graph, `{ nodes: [], edges: [] }` (viewer_harness.mjs),
  // predates this feature and was never updated to carry a `groups` key. That
  // is deliberate - every other describe block in this file that doesn't care
  // about grouping calls loadViewer(TARGETS), a graph with the same gap - so
  // this is the one test standing between that default and every grouping
  // function silently throwing on `undefined.length` the moment a test forgot
  // to pass `groups: []` explicitly.
  const v = loadViewer();

  test("every grouping function tolerates a graph with no assemblies at all", () => {
    assert.deepEqual(plain(v.allGroups()), []);
    assert.deepEqual(plain(v.allGroupEdges()), []);
    assert.equal(v.groupingHTML(), "");
    assert.equal(v.groupById("grp_missing"), null);
    assert.equal(v.groupOfTarget("tgt_missing"), null);
    assert.equal(v.groupMode(null), "separate");
    assert.doesNotThrow(() => v.sharedTargets({ id: "mol_missing" }));
    assert.doesNotThrow(() => v.edgeListHTML([], "to"));
    assert.doesNotThrow(() => v.renderRows([], "to"));
    assert.doesNotThrow(() => v.highlightOpacity(new Set(), new Set(), new Set(), new Set()));
  });
});

describe("sharedTargets - grouping corrects the shared-target count", () => {
  // The defect this whole feature exists to fix. Two molecules that both
  // reach a seven-subunit receptor look, in the raw rows, like they share
  // seven or four targets depending on how each one's assays happened to be
  // run - which is not a fact about the two drugs, it is a fact about how
  // ChEMBL's assays were designed. fanoutRef already caught the case where
  // *one* molecule's own fan-out inflates its own edge count; it does nothing
  // for the case here, where each molecule reaches the assembly by a
  // different route.
  const nodes = [
    molecule("mol_a", "Dextromethorphan-like"),
    molecule("mol_b", "Memantine-like"),
    target("tgt_1", "GRIN1"), target("tgt_2", "GRIN2A"),
    target("tgt_3", "GRIN2B"), target("tgt_4", "GRIN2C"),
  ];
  const groups = [group("grp_nmda", "Glutamate [NMDA] receptor",
    { tier: "complex", target_type: "PROTEIN COMPLEX GROUP",
      members: ["tgt_1", "tgt_2", "tgt_3", "tgt_4"] })];
  // Molecule A: one assay, attributed to all four subunits - a single
  // seven-subunit-style screen collapsed here to four for brevity.
  const fanEdges = ["tgt_1", "tgt_2", "tgt_3", "tgt_4"].map((tid, i) =>
    edge({ id: `a${i}`, from: "mol_a", to: tid,
      measurements: [measurement({ external_ref: "FANOUT_ASSAY" })] }));
  // Molecule B: three of those same subunits, each its own assay - no
  // external_ref in common with any other of B's edges, so fanoutRef alone
  // sees three unrelated single-assay edges and nothing to merge.
  const individualEdges = ["tgt_1", "tgt_2", "tgt_3"].map((tid, i) =>
    edge({ id: `b${i}`, from: "mol_b", to: tid,
      measurements: [measurement({ external_ref: `SEPARATE_${i}` })] }));
  const edges = fanEdges.concat(individualEdges);

  for (const mode of ["collapse", "hull"]) {
    test(`grouped (${mode}): one receptor is one shared target, not three`, () => {
      const v = loadViewer({ nodes, edges, groups });
      v.setGrouping("complex", mode);
      const [row] = v.sharedTargets({ id: "mol_a" });
      assert.equal(row.shared, 1,
        "both molecules reach one assembly; the fan-out on A's side and the " +
        "three separate assays on B's side must collapse to one fact");
      assert.equal(row.proteins, 3,
        "the protein count behind the merge must still say how many subunits it is");
    });
  }

  test('tier "separate": the old, un-de-duplicated behaviour returns', () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex", "separate");
    const [row] = v.sharedTargets({ id: "mol_a" });
    assert.equal(row.shared, 3,
      "with the assembly not recognised as one thing, each of B's three " +
      "subunit measurements is its own overlap - the very miscount this " +
      "feature corrects");
  });

  test("setUngrouped(true) reproduces the same uncorrected count", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setUngrouped(true);
    const [row] = v.sharedTargets({ id: "mol_a" });
    assert.equal(row.shared, 3);
  });

  describe("the assay-level de-duplication is a separate mechanism, and setUngrouped turns it off too", () => {
    // Not the assembly case above - these targets belong to no group at all,
    // so this isolates fanoutRef's own fan-out guard (already covered
    // elsewhere in this file) against the ungrouped escape hatch specifically.
    const plainNodes = [
      molecule("mol_p", "P"), molecule("mol_q", "Q"),
      target("tgt_x", "X"), target("tgt_y", "Y"), target("tgt_z", "Z"),
    ];
    const fan = (id, from, to) => edge({
      id, from, to, measurements: [measurement({ external_ref: "ONE_ASSAY" })],
    });
    const plainEdges = ["tgt_x", "tgt_y", "tgt_z"].flatMap(tid => [
      fan(`p_${tid}`, "mol_p", tid), fan(`q_${tid}`, "mol_q", tid),
    ]);

    test("grouping on (the default): one assay behind three targets is one overlap", () => {
      const v = loadViewer({ nodes: plainNodes, edges: plainEdges });
      assert.equal(v.sharedTargets({ id: "mol_p" })[0].shared, 1);
    });

    test("setUngrouped(true): the same one assay now counts three times over", () => {
      const v = loadViewer({ nodes: plainNodes, edges: plainEdges });
      v.setUngrouped(true);
      assert.equal(v.sharedTargets({ id: "mol_p" })[0].shared, 3);
    });
  });
});

describe("canvas vs. picture - a collapsed subunit leaves the canvas, not the picture", () => {
  // Collapsing is a drawing decision, not a visibility one (see the comment
  // above nodeOnCanvas in the source). A subunit merged into its assembly's
  // node must still be nodeVisible - still counted by sharedTargets, still
  // listed in the panel - while nodeOnCanvas alone goes false, because that
  // is the one predicate the canvas actually reads.
  const nodes = [
    molecule("mol_a", "A"), target("tgt_1", "T1"), target("tgt_2", "T2"),
  ];
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2"] })];
  const e1 = edge({ id: "e1", from: "mol_a", to: "tgt_1" });
  const edges = [e1, edge({ id: "e2", from: "mol_a", to: "tgt_2" })];

  test("collapse: off the canvas, still in the picture", () => {
    const v = loadViewer({ nodes, edges, groups }); // complex tier defaults to collapse
    const g = v.groupById("grp_1");
    const t1 = v.nodeById("tgt_1");
    assert.equal(v.nodeOnCanvas(t1), false);
    assert.equal(v.nodeVisible(t1), true);
    assert.equal(v.groupNodeOnCanvas(g), true);
    assert.equal(v.collapsedGroupOf(t1), g);
    assert.equal(v.visibleRows([e1], "to").length, 1,
      "the panel's own visibility rule (endVisible) reads nodeVisible, not " +
      "nodeOnCanvas, so the row must still be listed");
  });

  test("hull: on the canvas, and not collapsed", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex", "hull");
    const g = v.groupById("grp_1");
    const t1 = v.nodeById("tgt_1");
    assert.equal(v.nodeOnCanvas(t1), true);
    assert.equal(v.groupNodeOnCanvas(g), false);
    assert.equal(v.collapsedGroupOf(t1), null);
  });

  test("separate: on the canvas, and not collapsed", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex", "separate");
    const g = v.groupById("grp_1");
    const t1 = v.nodeById("tgt_1");
    assert.equal(v.nodeOnCanvas(t1), true);
    assert.equal(v.groupNodeOnCanvas(g), false);
    assert.equal(v.collapsedGroupOf(t1), null);
  });
});

describe("the brain filter and grouping compose", () => {
  // Two controls that each remove things from the picture, layered: the
  // filter decides which subunits survive, and only then does grouping decide
  // whether what survives is drawn as one node. An assembly with at least one
  // confirmed member is still worth drawing; one with none is not, and must
  // not appear as an empty hexagon standing for nothing on screen.
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2"] })];
  const edges = [
    edge({ id: "e1", from: "mol_a", to: "tgt_1" }),
    edge({ id: "e2", from: "mol_a", to: "tgt_2" }),
  ];

  test("visibleMembers keeps only the brain-confirmed subunits", () => {
    const nodes = [
      molecule("mol_a", "A"),
      target("tgt_1", "T1", { expressed_in_brain: 1 }),
      target("tgt_2", "T2"), // unverified
    ];
    const v = loadViewer({ nodes, edges, groups });
    v.setFilter("brainOnly", true);
    assert.deepEqual(v.visibleMembers(v.groupById("grp_1")).map(n => n.id), ["tgt_1"]);
  });

  test("a collapsed group with at least one confirmed member stays on the canvas", () => {
    const nodes = [
      molecule("mol_a", "A"),
      target("tgt_1", "T1", { expressed_in_brain: 1 }),
      target("tgt_2", "T2"),
    ];
    const v = loadViewer({ nodes, edges, groups });
    v.setFilter("brainOnly", true);
    assert.equal(v.groupNodeOnCanvas(v.groupById("grp_1")), true);
  });

  test("a collapsed group whose members are all unverified is not drawn at all", () => {
    const nodes = [
      molecule("mol_a", "A"),
      target("tgt_1", "T1"),
      target("tgt_2", "T2"),
    ];
    const v = loadViewer({ nodes, edges, groups });
    v.setFilter("brainOnly", true);
    assert.equal(v.groupNodeOnCanvas(v.groupById("grp_1")), false,
      "a hexagon standing for zero visible subunits would be a node drawn for nothing");
  });
});

describe("renderRows - one row per assembly, not one per subunit", () => {
  // Both de-duplications from sharedTargets have to reappear here: the panel
  // a reader actually looks at has to agree with the ranking it explains, or
  // the two disagree about what counts as one thing (invariant 13's failure
  // mode, applied to grouping instead of citation counts).
  const nodes = [
    molecule("mol_a", "A"),
    target("tgt_1", "T1"), target("tgt_2", "T2"), target("tgt_3", "T3"),
  ];
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2"] })];
  // Ranking order under the caller's control: curated first, a corroborated
  // loose edge second, the assembly's other subunit last - so the group's
  // best-ranked member (e1) is not adjacent to its other member (e2).
  const e1 = edge({ id: "e1", from: "mol_a", to: "tgt_1", is_primary_mechanism: 1 });
  const eLoose = edge({ id: "eLoose", from: "mol_a", to: "tgt_3", n_measurements: 5 });
  const e2 = edge({ id: "e2", from: "mol_a", to: "tgt_2", n_measurements: 1 });
  const edges = [e1, eLoose, e2];

  test("a grouped assembly collapses to one cxgroup row carrying its subunit rows", () => {
    const v = loadViewer({ nodes, edges, groups });
    const html = v.renderRows(edges, "to");
    assert.equal((html.match(/class="cxgroup"/g) || []).length, 1,
      "one hexagon, one row - not one row per subunit");
    assert.ok(html.includes('data-edge-id="e1"') && html.includes('data-edge-id="e2"'),
      "the individual subunit edges must still be listed inside the group's row");
  });

  test("the group's row sits at the position of its best-ranked member", () => {
    const v = loadViewer({ nodes, edges, groups });
    const html = v.renderRows(edges, "to");
    // e1 (curated, tgt_1) is the group's best-ranked member and comes first in
    // the input; the group must be emitted there, ahead of eLoose, and must
    // not be emitted again at e2's later position.
    const groupPos = html.indexOf('class="cxgroup"');
    const loosePos = html.indexOf('data-edge-id="eLoose"');
    assert.ok(groupPos >= 0 && groupPos < loosePos,
      "the group must appear before the loose edge, matching e1's rank");
  });

  test('tier "separate": no cxgroup row at all', () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex", "separate");
    assert.ok(!v.renderRows(edges, "to").includes("cxgroup"));
  });

  test("setUngrouped(true): no cxgroup row at all", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setUngrouped(true);
    assert.ok(!v.renderRows(edges, "to").includes("cxgroup"));
  });

  test('renderRows(edges, "from") - a target\'s molecule list - never groups', () => {
    // Existing behaviour that must survive: only the targets-of-a-molecule
    // direction collapses subunits into their assembly. A target's own list
    // of molecules has no assembly to fold into and must list every edge.
    const v = loadViewer({ nodes, edges, groups });
    const html = v.renderRows(edges, "from");
    assert.ok(!html.includes("cxgroup"));
    edges.forEach(e => assert.ok(html.includes(`data-edge-id="${e.id}"`)));
  });
});

// ---------------------------------------------------------------------------
// One receptor is one row, whatever the evidence tiers do.
//
// Reported from the graph: clicking verapamil showed a "Voltage-gated calcium
// channel" row that expanded to CACNA1C alone. Its other three calcium edges
// were in a second row of the same name, in a different tier - the list was
// grouped by assembly *inside* each tier, so an assembly whose subunit edges
// were not all equally evidenced was split, and each half honestly reported
// the subunits it happened to hold. Four of the 23 assembly rows in the
// current database were split this way. Grouping now happens before the tiers
// see the list, and a grouped row is placed by its best-evidenced member -
// the same rule the canvas already uses to decide a collapsed edge is solid.
// ---------------------------------------------------------------------------
describe("an assembly is one row even when its subunits differ in evidence", () => {
  const nodes = [
    molecule("mol_a", "Verapamil"),
    target("t_c", "CACNA1C"), target("t_d", "CACNA1D"),
    target("t_f", "CACNA1F"), target("t_s", "CACNA1S"),
    target("t_other", "KCNH2"),
  ];
  const groups = [group("grp_cav", "Voltage-gated calcium channel", {
    tier: "complex_group", members: ["t_c", "t_d", "t_f", "t_s"],
  })];
  // Verapamil's actual shape: CACNA1C corroborated, the other three single
  // measurements, which put them in two different tiers.
  const edges = [
    edge({ id: "e_c", from: "mol_a", to: "t_c", n_measurements: 2 }),
    edge({ id: "e_d", from: "mol_a", to: "t_d", n_measurements: 1 }),
    edge({ id: "e_f", from: "mol_a", to: "t_f", n_measurements: 1 }),
    edge({ id: "e_s", from: "mol_a", to: "t_s", n_measurements: 1 }),
    edge({ id: "e_k", from: "mol_a", to: "t_other", n_measurements: 9 }),
  ];

  test("one assembly row, not one per tier", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML(edges, "to");
    assert.equal((html.match(/class="cxgroup"/g) || []).length, 1,
      "the calcium channel appeared twice - once per evidence tier");
  });

  test("the row expands to every subunit edge, not just the tier's share", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML(edges, "to");
    ["e_c", "e_d", "e_f", "e_s"].forEach(id =>
      assert.ok(html.includes(`data-edge-id="${id}"`),
        `${id} is missing - this is the bug: the row opened to CACNA1C alone`));
  });

  test("it sits in the tier of its best-evidenced subunit", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML(edges, "to");
    const corroborated = html.indexOf("Corroborated (");
    const leads = html.indexOf("Single-source leads");
    const row = html.indexOf('class="cxgroup"');
    assert.ok(corroborated >= 0 && row > corroborated,
      "an assembly with a corroborated subunit belongs in the corroborated tier");
    assert.ok(leads === -1 || row < leads);
  });

  test("the promotion is stated in the row rather than being silent", () => {
    // Three of the four edges inside a "Corroborated" row are single-source
    // leads. That is the right place for the row and the wrong thing to leave
    // unsaid, so the row counts what it holds.
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML(edges, "to");
    assert.match(html, /1 corroborated edge, 3 leads/);
  });

  test("the row says how much of the receptor it accounts for", () => {
    // "Voltage-gated calcium channel" opening onto one protein is a row naming
    // a 26-subunit channel and showing one of them. Say which.
    const v = loadViewer({ nodes, edges: [edges[0]], groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML([edges[0]], "to");
    assert.match(html, /1 subunit of 4 measured here/);
  });

  test("the tier heading still counts edges, not rows", () => {
    // A grouped row stands for several edges; a heading reading "(1)" over a
    // row holding four would be the two-quantities-one-label failure again.
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const html = v.edgeListHTML(edges, "to");
    assert.match(html, /Corroborated \(5\)/);
  });

  test("a single-tier assembly says nothing about a spread it does not have", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.setGrouping("complex_group", "hull");
    const same = [
      edge({ id: "s1", from: "mol_a", to: "t_c", n_measurements: 2 }),
      edge({ id: "s2", from: "mol_a", to: "t_d", n_measurements: 3 }),
    ];
    const html = v.edgeListHTML(same, "to");
    assert.ok(!/corroborated edge.*lead/.test(html),
      "the heading above already says the tier; repeating it in the row is noise");
  });
});

describe("per-assembly override beats the tier default", () => {
  const nodes = [molecule("mol_a", "A"), target("tgt_1", "T1"), target("tgt_2", "T2")];
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2"] })];

  test("an override changes what groupMode reports, independent of the tier setting", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    const g = v.groupById("grp_1");
    assert.equal(v.groupMode(g), "collapse", "complex defaults to collapse");
    v.setGroupOverride("grp_1", "separate");
    assert.equal(v.groupMode(g), "separate");
  });

  test("setGroupOverride(id, null) clears the override back to the tier default", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    const g = v.groupById("grp_1");
    v.setGroupOverride("grp_1", "hull");
    assert.equal(v.groupMode(g), "hull");
    v.setGroupOverride("grp_1", null);
    assert.equal(v.groupMode(g), "collapse",
      "clearing the override must fall through to groupingDefault('complex'), not stay stuck");
    assert.equal(v.groupingDefault("complex"), "collapse");
  });

  test("changing the tier default does not require touching an unrelated override", () => {
    // A reader who merges the NMDA receptor by itself must not also merge
    // every other complex_group on the page.
    const other = group("grp_2", "Other assembly", { tier: "complex_group", members: ["tgt_1"] });
    const v = loadViewer({ nodes, edges: [], groups: [...groups, other] });
    v.setGroupOverride("grp_1", "separate");
    assert.equal(v.groupMode(v.groupById("grp_1")), "separate");
    assert.equal(v.groupMode(v.groupById("grp_2")), "hull", "complex_group's own default, untouched");
  });

  test("clicking Collapse selects the newly collapsed assembly on the canvas", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    v.setGrouping("complex", "hull");

    v.applyGroupModeChoice("grp_1", "collapse");

    assert.equal(v.groupMode(v.groupById("grp_1")), "collapse");
    assert.deepEqual(plain(v.networkSelections.at(-1)), ["grp_1"],
      "the synthetic assembly node should receive vis-network's selected rim");
    assert.match(v.document.getElementById("detail").innerHTML, /Assembly/,
      "the assembly itself should also become the sidebar selection");
  });
});

describe("groupEdges - one collapsed edge stands for several real ones", () => {
  const nodes = [
    molecule("mol_a", "A"),
    target("tgt_1", "T1"), target("tgt_2", "T2"), target("tgt_3", "T3"),
  ];
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2", "tgt_3"] })];

  test("exactly one groupEdges entry exists per (molecule, assembly) pair, carrying every underlying edge", () => {
    const edges = [
      edge({ id: "e1", from: "mol_a", to: "tgt_1" }),
      edge({ id: "e2", from: "mol_a", to: "tgt_2" }),
      edge({ id: "e3", from: "mol_a", to: "tgt_3" }),
    ];
    const v = loadViewer({ nodes, edges, groups });
    const matches = v.allGroupEdges().filter(ge => ge.from === "mol_a" && ge.group.id === "grp_1");
    assert.equal(matches.length, 1);
    assert.deepEqual(plain(matches[0].edges.map(e => e.id)).sort(), ["e1", "e2", "e3"]);
  });

  test("groupEdgeCorroborated is true when any one underlying edge is corroborated", () => {
    const v = loadViewer({
      nodes, groups,
      edges: [
        edge({ id: "e1", from: "mol_a", to: "tgt_1", n_measurements: 1 }), // lead
        edge({ id: "e2", from: "mol_a", to: "tgt_2", n_measurements: 5 }), // corroborated
      ],
    });
    const ge = v.allGroupEdges().find(x => x.from === "mol_a");
    assert.equal(v.groupEdgeCorroborated(ge), true);
  });

  test("groupEdgeCorroborated is false when none of the underlying edges is", () => {
    const v = loadViewer({
      nodes, groups,
      edges: [
        edge({ id: "e1", from: "mol_a", to: "tgt_1", n_measurements: 1 }),
        edge({ id: "e2", from: "mol_a", to: "tgt_2", n_measurements: 1 }),
      ],
    });
    const ge = v.allGroupEdges().find(x => x.from === "mol_a");
    assert.equal(v.groupEdgeCorroborated(ge), false);
  });

  test("groupEdgeAction prefers a curated edge's action_type over the most frequent one", () => {
    const v = loadViewer({
      nodes, groups,
      edges: [
        edge({ id: "e1", from: "mol_a", to: "tgt_1", action_type: "ANTAGONIST",
               is_primary_mechanism: 1, n_measurements: null }),
        edge({ id: "e2", from: "mol_a", to: "tgt_2", action_type: "INHIBITOR" }),
        edge({ id: "e3", from: "mol_a", to: "tgt_3", action_type: "INHIBITOR" }),
      ],
    });
    const ge = v.allGroupEdges().find(x => x.from === "mol_a");
    assert.equal(v.groupEdgeAction(ge), "ANTAGONIST",
      "INHIBITOR is the more frequent action_type, but the curated mechanism must win");
  });

  test("groupEdgeAction falls back to the most frequent action_type with no curated edge", () => {
    const v = loadViewer({
      nodes, groups,
      edges: [
        edge({ id: "e1", from: "mol_a", to: "tgt_1", action_type: "INHIBITOR" }),
        edge({ id: "e2", from: "mol_a", to: "tgt_2", action_type: "INHIBITOR" }),
        edge({ id: "e3", from: "mol_a", to: "tgt_3", action_type: "ANTAGONIST" }),
      ],
    });
    const ge = v.allGroupEdges().find(x => x.from === "mol_a");
    assert.equal(v.groupEdgeAction(ge), "INHIBITOR");
  });

  test("groupEdgeOnCanvas is true only in collapse mode", () => {
    const edges = [
      edge({ id: "e1", from: "mol_a", to: "tgt_1" }),
      edge({ id: "e2", from: "mol_a", to: "tgt_2" }),
    ];
    const v = loadViewer({ nodes, edges, groups });
    const ge = v.allGroupEdges().find(x => x.from === "mol_a");
    assert.equal(v.groupEdgeOnCanvas(ge), true, "complex defaults to collapse");
    v.setGrouping("complex", "hull");
    assert.equal(v.groupEdgeOnCanvas(ge), false);
    v.setGrouping("complex", "separate");
    assert.equal(v.groupEdgeOnCanvas(ge), false);
  });
});

describe("highlightOpacity carries collapsed assemblies along with their members", () => {
  const nodes = [molecule("mol_a", "A"), target("tgt_1", "T1"), target("tgt_2", "T2")];
  const groups = [group("grp_1", "Assembly", { members: ["tgt_1", "tgt_2"] })];
  const edges = [edge({ id: "e1", from: "mol_a", to: "tgt_1" })];

  test("a collapsed assembly is at full opacity when any of its members is kept", () => {
    const v = loadViewer({ nodes, edges, groups });
    const o = v.highlightOpacity(new Set(["tgt_1"]), new Set(), new Set(), new Set());
    assert.equal(o.nodes.get("grp_1"), 1);
  });

  test("group ids are present in the returned nodes map at all, even unfiltered", () => {
    const v = loadViewer({ nodes, edges, groups });
    const o = v.highlightOpacity(new Set(), new Set(), new Set(), new Set());
    assert.ok(o.nodes.has("grp_1"));
    assert.equal(o.nodes.get("grp_1"), 1, "nothing kept means nothing dimmed, groups included");
  });

  test("returns {nodes: Map, edges: Map}", () => {
    // Not `instanceof Map`: the sandbox is a separate vm realm, so its Map
    // constructor is not this realm's Map, the same reason plain() exists.
    const v = loadViewer({ nodes, edges, groups });
    const o = v.highlightOpacity(new Set(), new Set(), new Set(), new Set());
    const isMap = x => Object.prototype.toString.call(x) === "[object Map]";
    assert.ok(isMap(o.nodes));
    assert.ok(isMap(o.edges));
  });
});

// ---------------------------------------------------------------------------
// Escaping, invariant 11, applied to assembly names. These are upstream
// ChEMBL pref_names, exactly as free-text as everything else invariant 11
// already covers, and reach innerHTML the same three ways: the assembly's own
// panel, the collapsed row in a molecule's edge list, and the grouping
// control that names the largest one. This page is published as a shared
// artifact, so an unescaped name is a stored-XSS payload sitting in the seed
// data, not just a cosmetic bug.
// ---------------------------------------------------------------------------
describe("escaping reaches assembly names too (invariant 11)", () => {
  const HOSTILE_NAME = `NMDA <script>alert(1)</script> & Co`;
  const nodes = [molecule("mol_a", "A"), target("tgt_1", "T1"), target("tgt_2", "T2")];
  const groups = [group("grp_1", HOSTILE_NAME, { members: ["tgt_1", "tgt_2"] })];
  const edges = [edge({ id: "e1", from: "mol_a", to: "tgt_1" }),
                 edge({ id: "e2", from: "mol_a", to: "tgt_2" })];

  test("showGroup escapes a hostile assembly name", () => {
    const v = loadViewer({ nodes, edges, groups });
    v.selectGroup("grp_1");
    const html = v.document.getElementById("detail").innerHTML;
    assert.ok(!html.includes("<script>alert"), "the raw tag must not survive into innerHTML");
    assert.ok(html.includes("&lt;script&gt;"));
    assert.ok(html.includes("&amp; Co"));
  });

  test("renderRows escapes a hostile assembly name in the collapsed row", () => {
    const v = loadViewer({ nodes, edges, groups });
    const html = v.renderRows(edges, "to");
    assert.ok(!html.includes("<script>alert"));
    assert.ok(html.includes("&lt;script&gt;"));
    assert.ok(html.includes("&amp;"));
  });

  test("groupingHTML escapes a hostile assembly name", () => {
    const v = loadViewer({ nodes, edges, groups });
    const html = v.groupingHTML();
    assert.ok(!html.includes("<script>alert"));
    assert.ok(html.includes("&lt;script&gt;"));
    assert.ok(html.includes("&amp;"));
  });
});

// ---------------------------------------------------------------------------
// Hull geometry, headless. No renderer runs here - the project's standing
// rule is that logic is driven headless and the canvas is reserved for
// pixels - so these hold convexHull and hullOutline to being usable polygons
// on ordinary input and on the two degenerate cases (two subunits; several in
// a line) that would otherwise draw as a stroke around nothing at all.
// ---------------------------------------------------------------------------
describe("convexHull and hullOutline", () => {
  const v = loadViewer();

  test("convexHull encloses a normal spread and drops the interior point", () => {
    const pts = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 },
                 { x: 5, y: 5 }]; // centre point, must not appear in the hull
    const hull = v.convexHull(pts);
    assert.equal(hull.length, 4);
    assert.ok(!hull.some(p => p.x === 5 && p.y === 5),
      "an interior point is not part of the enclosing hull");
  });

  test("hullOutline gives two subunits a usable rectangle, not a zero-area line", () => {
    const outline = v.hullOutline([{ x: 0, y: 0 }, { x: 10, y: 0 }]);
    const xs = outline.map(p => p.x), ys = outline.map(p => p.y);
    assert.ok(outline.length >= 3);
    assert.ok(Math.max(...xs) - Math.min(...xs) > 0, "must have non-zero width");
    assert.ok(Math.max(...ys) - Math.min(...ys) > 0,
      "two horizontally-placed nodes give zero-height points; the floor must add height");
  });

  test("hullOutline gives several collinear subunits a usable rectangle, not a zero-width line", () => {
    const vertical = [{ x: 5, y: 0 }, { x: 5, y: 10 }, { x: 5, y: 20 }, { x: 5, y: 30 }];
    const outline = v.hullOutline(vertical);
    const xs = outline.map(p => p.x), ys = outline.map(p => p.y);
    assert.ok(outline.length >= 3);
    assert.ok(Math.max(...xs) - Math.min(...xs) > 0,
      "four vertically-stacked nodes give zero-width points; the floor must add width");
    assert.ok(Math.max(...ys) - Math.min(...ys) > 0);
    assert.ok(new Set(outline.map(p => `${p.x},${p.y}`)).size >= 3,
      "must be at least 3 distinct points to be a drawable polygon");
  });
});

// ---------------------------------------------------------------------------
// A hull encloses only its own members.
//
// The enclosure is a claim - "these proteins are one receptor" - and vis's
// physics knows nothing about assemblies, so nothing stopped the layout from
// putting an unrelated target inside one and having the picture make that claim
// about it. Two things now stop it: glue springs, which pull an assembly's
// subunits into a tight cluster so there is little room inside to land in, and
// hullExclusions, which is the guarantee - anything that is not a member and is
// in or against the outline is carved out of the drawn region.
// ---------------------------------------------------------------------------
describe("a hull encloses only its own members", () => {
  const v = loadViewer();
  // A square of members, big enough that a node can sit well inside it.
  const square = [{ x: 0, y: 0 }, { x: 200, y: 0 },
                  { x: 200, y: 200 }, { x: 0, y: 200 }];
  const at = (id, x, y, r) => ({ id, x, y, r: r == null ? 30 : r });

  test("pointInPolygon separates inside from outside", () => {
    assert.ok(v.pointInPolygon({ x: 100, y: 100 }, square));
    assert.ok(!v.pointInPolygon({ x: 400, y: 100 }, square));
  });

  test("distanceToPolygon measures to the nearest edge, whichever side it is on", () => {
    assert.equal(Math.round(v.distanceToPolygon({ x: 100, y: 240 }, square)), 40);
    assert.equal(Math.round(v.distanceToPolygon({ x: 100, y: 160 }, square)), 40);
  });

  test("a non-member sitting inside the outline is excluded from it", () => {
    const excluded = v.hullExclusions(square, ["m1", "m2"], [
      at("m1", 10, 10), at("m2", 190, 190), at("stranger", 100, 100),
    ]);
    assert.deepEqual(excluded.map(n => n.id), ["stranger"]);
  });

  test("a member is never excluded, however deep inside it sits", () => {
    const excluded = v.hullExclusions(square, ["m1", "inner"], [
      at("m1", 10, 10), at("inner", 100, 100),
    ]);
    assert.deepEqual(excluded.map(n => n.id), [],
      "carving a subunit out of its own receptor's enclosure would be worse " +
      "than the problem being fixed");
  });

  test("a non-member just outside is still given clearance, so the outline never touches it", () => {
    // Its centre is out, but the enclosure would be drawn through it. An
    // outline running across a node reads as the node being on the boundary of
    // the assembly, which is a claim about it either way.
    const excluded = v.hullExclusions(square, ["m1"], [
      at("m1", 10, 10), at("grazing", 100, 215, 30),
    ]);
    assert.deepEqual(excluded.map(n => n.id), ["grazing"]);
  });

  test("a non-member well clear of the outline is left alone", () => {
    const excluded = v.hullExclusions(square, ["m1"], [
      at("m1", 10, 10), at("far", 100, 400, 30),
    ]);
    assert.deepEqual(excluded.map(n => n.id), []);
  });

  test("a degenerate outline excludes nothing rather than everything", () => {
    // hullOutline never returns fewer than 3 points, but a hull with no area
    // is not a claim about anything and must not start carving the graph up.
    assert.equal(v.hullExclusions([], ["m1"], [at("x", 0, 0)]).length, 0);
    assert.equal(v.hullExclusions([{ x: 0, y: 0 }, { x: 1, y: 1 }], ["m1"],
      [at("x", 0, 0)]).length, 0);
  });
});

describe("glue springs hold an assembly's subunits together", () => {
  const nodes = [
    molecule("mol_a", "A"),
    target("tgt_1", "T1"), target("tgt_2", "T2"), target("tgt_3", "T3"),
  ];
  const groups = [group("grp_1", "Assembly",
    { tier: "complex_group", members: ["tgt_1", "tgt_2", "tgt_3"] })];

  test("one spring per subunit beyond the first - a star, not a clique", () => {
    // 26 calcium subunits as a clique would be 325 springs and would overwhelm
    // every other force on the canvas.
    const v = loadViewer({ nodes, edges: [], groups });
    assert.equal(v.allGlueEdges().length, 2);
    assert.deepEqual(v.allGlueEdges().map(g => `${g.from}->${g.to}`).join(" "),
      "tgt_1->tgt_2 tgt_1->tgt_3");
  });

  test("they pull only while the assembly is being drawn as one thing", () => {
    // "Separate" is the reader withdrawing the claim that these belong
    // together; a spring still holding them in one place would go on making it.
    const v = loadViewer({ nodes, edges: [], groups });
    assert.ok(v.glueActive(v.allGlueEdges()[0]), "complex_group defaults to hull");
    v.setGrouping("complex_group", "separate");
    assert.ok(!v.glueActive(v.allGlueEdges()[0]));
    v.setGrouping("complex_group", "collapse");
    assert.ok(!v.glueActive(v.allGlueEdges()[0]),
      "collapsed subunits are off the canvas; there is nothing to hold together");
  });

  test("a glue spring is not an edge anything can open", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    v.allGlueEdges().forEach(g => {
      assert.ok(v.isGlueEdge(g.id));
      assert.equal(v.nodeById(g.id), undefined);
    });
    assert.ok(!v.isGlueEdge("int_1"));
  });
});

describe("groupingHTML - the grouping control states its own cost", () => {
  const nodes = [
    molecule("mol_a", "A"),
    target("tgt_1", "T1"), target("tgt_2", "T2"),
    target("tgt_3", "T3"), target("tgt_4", "T4"), target("tgt_5", "T5"),
  ];
  const groups = [
    group("grp_small", "Small assembly", { members: ["tgt_1", "tgt_2"] }),
    group("grp_big", "Big assembly",
      { tier: "complex_group", members: ["tgt_3", "tgt_4", "tgt_5"] }),
  ];

  test("names the largest assembly and its subunit count", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    const html = v.groupingHTML();
    assert.match(html, /Largest here: Big assembly/);
    assert.match(html, /3 subunits/);
  });

  test("the tier's reasoning is on hover, not printed under the buttons", () => {
    // It was two paragraphs above every panel, read once and scrolled past
    // forever. The words are unchanged and still counted from the data; only
    // where they sit changed.
    const v = loadViewer({ nodes, edges: [], groups });
    const html = v.groupingHTML();
    assert.ok(!html.includes("filter-note"),
      "an inline note block is back in the grouping control");
    assert.equal((html.match(/class="help"/g) || []).length,
                 (html.match(/class="help-text"/g) || []).length);
    assert.match(html, /Largest here[\s\S]*?<\/span>/);
    const tierName = html.indexOf("Protein complexes");
    assert.ok(html.slice(tierName).startsWith("Protein complexes</span><span class=\"help-text\">"),
      "a tier label must carry its own explanation, not the block's");
  });

  test("the per-assembly control explains its scope on the heading", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    const html = v.groupModeControlHTML(v.groupById("grp_big"));
    assert.ok(!html.includes("filter-note"));
    assert.match(html, /How this is drawn<\/span><span class="help-text">/);
    assert.match(html, /Applies to this assembly only/);
  });

  test("returns an empty string when there are no groups", () => {
    const v = loadViewer({ nodes: [molecule("mol_a", "A")], edges: [] });
    assert.equal(v.groupingHTML(), "");
  });

  test("setUngrouped(true) says grouping is off and how many targets are counted separately", () => {
    // In the banner rather than in the control block, for the same reason the
    // brain filter's is: the block collapses and what it has done to the graph
    // must not collapse with it.
    const v = loadViewer({ nodes, edges: [], groups });
    v.setUngrouped(true);
    const html = v.filterBannersHTML();
    assert.match(html, /Grouping off/);
    assert.match(html, /5 of 5 targets/);
    assert.match(html, /2 assemblies/);
  });

  test("the collapsed control line names the mode each tier is in", () => {
    const v = loadViewer({ nodes, edges: [], groups });
    assert.match(v.viewOptionsSummary(), /protein complexes collapse/);
    assert.match(v.viewOptionsSummary(), /protein complex groups hull/);
    v.setGrouping("complex", "separate");
    assert.match(v.viewOptionsSummary(), /protein complexes separate/);
    v.setUngrouped(true);
    assert.match(v.viewOptionsSummary(), /assemblies ungrouped/);
  });

  test("a per-assembly override is named in the collapsed line, not silently kept", () => {
    // An override the reader cannot see is the failure the tier buttons already
    // guard against by clearing overrides when a default changes.
    const v = loadViewer({ nodes, edges: [], groups });
    v.setGroupOverride("grp_big", "collapse");
    assert.match(v.viewOptionsSummary(), /1 override/);
  });
});

// ---------------------------------------------------------------------------
// The pair view.
//
// A "Shares targets with" row used to open the other molecule, which answers a
// different question - it swapped one 46-row target list for another and left
// the overlap to be found by eye. What is locked in here is not that clicking
// works, but that the pair panel shows *the row's own units*: the same
// de-duplications that produced the number on the row, so a row saying "2
// shared targets (8 proteins, grouped)" and the list it opens can never
// disagree about which two things they are.
// ---------------------------------------------------------------------------

const PAIR_GRAPH = {
  nodes: [
    molecule("mol_a", "Caffeine"),
    molecule("mol_b", "Theophylline"),
    molecule("mol_c", "Donepezil"),
    target("tgt_x", "ADORA1", {
      expressed_in_brain: 1, protein_name: "Adenosine receptor A1",
    }),
    target("tgt_y", "ADORA2A", { expressed_in_brain: 1 }),
    target("tgt_z", "ACHE"),
  ],
  edges: [
    // ADORA1: both sides corroborated, and brain-expressed.
    edge({ id: "a_x", from: "mol_a", to: "tgt_x", n_measurements: 4 }),
    edge({ id: "b_x", from: "mol_b", to: "tgt_x", n_measurements: 3 }),
    // ADORA2A: shared, but a lead on caffeine's side.
    edge({ id: "a_y", from: "mol_a", to: "tgt_y", n_measurements: 1 }),
    edge({ id: "b_y", from: "mol_b", to: "tgt_y", n_measurements: 5 }),
    // Not shared with theophylline at all.
    edge({ id: "a_z", from: "mol_a", to: "tgt_z", n_measurements: 2 }),
    edge({ id: "c_z", from: "mol_c", to: "tgt_z", n_measurements: 2 }),
  ],
};

describe("sharedTargets keeps the units its counts are made of", () => {
  const v = loadViewer(PAIR_GRAPH);
  const row = v.sharedTargets(v.nodeById("mol_a")).find(r => r.molId === "mol_b");

  test("there is one unit per counted thing, not one per hit", () => {
    assert.equal(row.shared, 2);
    assert.equal(row.units.length, row.shared,
      "shared is the number of units, so the panel can list exactly what was counted");
  });

  test("each unit carries both molecules' edges at that target", () => {
    const byTarget = new Map(row.units.map(u => [u.hits[0].tid, u.hits[0]]));
    assert.equal(byTarget.get("tgt_x").a.id, "a_x");
    assert.equal(byTarget.get("tgt_x").b.id, "b_x");
    assert.equal(byTarget.get("tgt_y").a.id, "a_y");
    assert.equal(byTarget.get("tgt_y").b.id, "b_y");
  });

  test("the brain and corroborated counts still agree with the units", () => {
    // Both were Sets of keys before and are counts of units now; the numbers
    // must not have moved, because they are the ranking.
    assert.equal(row.brain, 2);
    assert.equal(row.solid, 1, "ADORA2A is a lead on caffeine's side");
  });

  test("a target only one of them acts on is not a unit", () => {
    assert.ok(!row.units.some(u => u.hits.some(h => h.tid === "tgt_z")));
  });
});

describe("a shared-target row opens the pair, not the other molecule", () => {
  const v = loadViewer(PAIR_GRAPH);
  const html = v.sharedTargetsHTML(v.nodeById("mol_a"));

  test("the row names both ends, so the click is unambiguous", () => {
    assert.match(html, /data-pair="mol_a\|mol_b"/);
  });

  test("it no longer opens the other molecule's own panel", () => {
    assert.ok(!html.includes('data-node-id="mol_b"'),
      "a row that opened the other molecule answered a different question");
  });
});

describe("pairFor - what the panel is allowed to describe", () => {
  const v = loadViewer(PAIR_GRAPH);

  test("resolves a real pair to the row that ranked it", () => {
    const pair = v.pairFor("mol_a", "mol_b");
    assert.equal(pair.a.label, "Caffeine");
    assert.equal(pair.b.label, "Theophylline");
    assert.equal(pair.row.shared, 2);
  });

  test("two molecules that share nothing are not a pair", () => {
    assert.equal(v.pairFor("mol_b", "mol_c"), null);
  });

  test("a target is not half of a pair", () => {
    assert.equal(v.pairFor("mol_a", "tgt_x"), null);
    assert.equal(v.pairFor("nope", "mol_b"), null);
  });

  test("the brain filter can dissolve a pair, and the panel must notice", () => {
    // Donepezil and caffeine share only ACHE, which has no tissue comment.
    const f = loadViewer(PAIR_GRAPH);
    assert.ok(f.pairFor("mol_a", "mol_c"));
    f.setFilter("brainOnly", true);
    assert.equal(f.pairFor("mol_a", "mol_c"), null,
      "the overlap is gone, so refreshSelection must fall back rather than "
      + "describe an overlap that is no longer on the canvas");
  });
});

describe("showPair - both sides of every shared target, side by side", () => {
  const v = loadViewer(PAIR_GRAPH);
  v.showPair(v.pairFor("mol_a", "mol_b"));
  const html = v.document.getElementById("detail").innerHTML;

  test("the title names both molecules", () => {
    assert.match(html, /Caffeine &amp; Theophylline/);
  });

  test("the overlap line repeats the row's own three numbers", () => {
    assert.ok(html.includes("2 shared targets"));
    assert.ok(html.includes("1 corroborated on both sides"));
    assert.ok(html.includes("2 brain-expressed"));
  });

  test("every shared target carries both molecules' edges", () => {
    ["a_x", "b_x", "a_y", "b_y"].forEach(id =>
      assert.ok(html.includes(`data-edge-id="${id}"`), `${id} is missing`));
  });

  test("an edge to a target they do not share is not in it", () => {
    assert.ok(!html.includes('data-edge-id="a_z"'));
  });

  test("the rows name the molecule, not the target the block is already about", () => {
    // edgeListItemHTML(e, "from"): under an ADORA1 heading, two rows reading
    // "ADORA1" would say nothing about which molecule each belongs to.
    assert.ok(html.includes("Caffeine — inhibitor"));
    assert.ok(html.includes("Theophylline — inhibitor"));
  });

  test("both molecules can still be opened on their own", () => {
    assert.match(html, /data-node-id="mol_a"/);
    assert.match(html, /data-node-id="mol_b"/);
  });

  test("it says the rest of the graph is dimmed and not filtered out", () => {
    assert.ok(/dimmed, not removed/.test(html),
      "only the brain filter removes; a selection that looked like a filter "
      + "would be a second answer to what is on screen");
  });

  test("the best-evidenced overlap leads", () => {
    assert.ok(html.indexOf("ADORA1") < html.indexOf("ADORA2A"),
      "ADORA1 is corroborated on both sides and ADORA2A is not");
  });

  test("its headings all have an explanation to open", () => {
    ["Overlap", "What they share", "Open on its own"].forEach(key =>
      assert.ok(v.helpLabel(key, key).includes('class="help-text"'),
        `the "${key}" heading has no explanation`));
  });
});

describe("pairHighlight - the two molecules and their overlap, nothing else", () => {
  const v = loadViewer(PAIR_GRAPH);
  const { keepNodes, keepEdges } = v.pairHighlight(v.pairFor("mol_a", "mol_b"));

  test("keeps both molecules and every shared target", () => {
    assert.deepEqual([...keepNodes].sort(), ["mol_a", "mol_b", "tgt_x", "tgt_y"]);
  });

  test("keeps both edges at each shared target and no others", () => {
    assert.deepEqual([...keepEdges].sort(), ["a_x", "a_y", "b_x", "b_y"]);
  });

  test("there is no second hop", () => {
    // A molecule's own selection echoes the molecules on its targets, which is
    // how the graph shows who else is there. A pair has already answered that
    // question, and echoing would put back the graph it was asked to isolate.
    const o = v.highlightOpacity(keepNodes, keepEdges, new Set(), new Set());
    assert.equal(o.nodes.get("mol_c"), 0.12);
    assert.equal(o.nodes.get("tgt_z"), 0.12);
    assert.equal(o.edges.get("a_z"), 0.06);
  });
});

// One assembly is one shared thing, however many subunits and however many
// separate experiments - the same rule the shared-target count uses. The panel
// has to say so on the block, because a block holding four proteins that
// contributed 1 to "shared targets" is exactly the compression that must not
// be silent.
describe("the pair panel groups an assembly the way the count did", () => {
  const ASSEMBLY = {
    nodes: [
      molecule("mol_a", "Dextromethorphan"),
      molecule("mol_b", "Memantine"),
      target("tgt_1", "GRIN1"),
      target("tgt_2", "GRIN2A"),
      target("tgt_3", "GRIN2B"),
    ],
    edges: [
      edge({ id: "a1", from: "mol_a", to: "tgt_1", n_measurements: 2 }),
      edge({ id: "a2", from: "mol_a", to: "tgt_2", n_measurements: 2 }),
      edge({ id: "a3", from: "mol_a", to: "tgt_3", n_measurements: 2 }),
      edge({ id: "b1", from: "mol_b", to: "tgt_1", n_measurements: 2 }),
      edge({ id: "b2", from: "mol_b", to: "tgt_2", n_measurements: 2 }),
      edge({ id: "b3", from: "mol_b", to: "tgt_3", n_measurements: 2 }),
    ],
    groups: [group("grp_nmda", "Glutamate [NMDA] receptor",
      { members: ["tgt_1", "tgt_2", "tgt_3"] })],
  };
  const v = loadViewer(ASSEMBLY);
  const pair = v.pairFor("mol_a", "mol_b");
  v.showPair(pair);
  const html = v.document.getElementById("detail").innerHTML;

  test("three shared subunits are one shared target", () => {
    assert.equal(pair.row.shared, 1);
    assert.equal(pair.row.proteins, 3);
  });

  test("the panel says what it compressed rather than leaving it at 1", () => {
    assert.ok(html.includes("1 shared target"));
    assert.ok(html.includes("3 proteins"), "the compression must not be silent");
    assert.ok(html.includes("one assembly, counted once"));
  });

  test("one block names the assembly and opens it", () => {
    assert.match(html, /data-group-id="grp_nmda"/);
    assert.ok(html.includes("Glutamate [NMDA] receptor"));
  });

  test("every subunit's edges are still inside that one block", () => {
    ["a1", "a2", "a3", "b1", "b2", "b3"].forEach(id =>
      assert.ok(html.includes(`data-edge-id="${id}"`), `${id} is missing`));
    ["tgt_1", "tgt_2", "tgt_3"].forEach(id =>
      assert.ok(html.includes(`class="pair-protein" data-node-id="${id}"`),
        `${id} is not named inside the block`));
  });

  test("turning grouping off counts the subunits separately again", () => {
    const u = loadViewer(ASSEMBLY);
    u.setUngrouped(true);
    assert.equal(u.pairFor("mol_a", "mol_b").row.shared, 3);
  });

  test("an assembly name reaches innerHTML escaped (invariant 11)", () => {
    const evil = {
      ...ASSEMBLY,
      groups: [group("grp_x", "<img src=x onerror=alert(1)>",
        { members: ["tgt_1", "tgt_2", "tgt_3"] })],
    };
    const e = loadViewer(evil);
    e.showPair(e.pairFor("mol_a", "mol_b"));
    const out = e.document.getElementById("detail").innerHTML;
    assert.ok(!out.includes("<img src=x"));
    assert.ok(out.includes("&lt;img src=x"));
  });
});

// ---------------------------------------------------------------------------
// Where the chrome lives.
//
// The title, the search box and the display options used to stack on top of
// the sidebar, so clicking a molecule put its name a screenful below the click
// that opened it. They belong to the picture rather than to the selection, so
// they moved into a bar over the graph and the sidebar holds one thing. These
// assertions are about the wiring that move could silently break, not about
// how it looks: a control that has moved out of #sidebar is a control whose
// clicks the sidebar's delegated handler no longer sees.
// ---------------------------------------------------------------------------
describe("the sidebar holds the selection and nothing else", () => {
  const html = readFileSync(new URL("../viz/legacy/index.html", import.meta.url), "utf8");
  const sidebar = html.slice(html.indexOf('<div id="sidebar">'),
                             html.indexOf('<script src="graph.data.js">'));

  test("the search box, the controls and the title are not in it", () => {
    ['id="search"', 'id="view-options"', 'id="search-results"',
     'id="filters"', "<h1>"].forEach(marker =>
      assert.ok(!sidebar.includes(marker),
        `${marker} is still inside #sidebar`));
  });

  test("what is in it is the selection", () => {
    assert.ok(sidebar.includes('id="detail-empty"'));
    assert.ok(sidebar.includes('id="detail"'));
  });

  test("the row handler is bound above the sidebar, not to it", () => {
    // The search results render outside #sidebar now. Bound to #sidebar, every
    // result row would be dead on click.
    assert.match(html,
      /document\.getElementById\("app"\)\.addEventListener\("click"/,
      "the delegated row handler must cover the chrome as well as the panel");
    assert.ok(!html.includes('document.getElementById("sidebar").addEventListener'));
  });

  test("the handler knows about every attribute a row can carry", () => {
    const selector = html.slice(html.indexOf('const item = ev.target.closest('));
    ["data-group-mode", "data-group-id", "data-node-id", "data-edge-id",
     "data-citation-key", "data-pair"].forEach(attr =>
      assert.ok(selector.slice(0, 400).includes(attr), `${attr} is not delegated`));
  });

  test("the filter's banner is outside the disclosure it reports on", () => {
    // The argument for allowing a control that removes things is that it
    // states its cost, and a cost behind a fold is not being stated - so
    // moving the controls must not take the banner into them.
    const bar = html.slice(html.indexOf('<header id="topbar">'),
                           html.indexOf("</header>"));
    assert.ok(bar.includes('id="view-options"'));
    assert.ok(!bar.includes('id="filters-active"'),
      "the banner must not live inside the bar that folds away");
    assert.ok(html.includes('<div id="filters-active"></div>'));
  });
});


// ---------------------------------------------------------------------------
// An assembly's Wikipedia link.
//
// Unlike a molecule's or a target's, this one is not derivable: no walk from a
// member's UniProt accession reaches the right Wikidata concept (it reaches
// "Cys-loop receptor" for 5-HT3 and "Ionotropic glutamate receptor" for NMDA),
// so build_db.py hand-writes the ChEMBL-id-to-Wikidata-item identity and
// resolves the article from that. What matters on this side is that a missing
// article renders as nothing rather than as a broken or invented link.
// ---------------------------------------------------------------------------
describe("an assembly links out to Wikipedia when it has an article", () => {
  const base = {
    nodes: [
      molecule("mol_a", "Memantine"),
      target("tgt_1", "GRIN1"),
      target("tgt_2", "GRIN2A"),
    ],
    edges: [edge({ id: "e1", from: "mol_a", to: "tgt_1" })],
  };
  const withUrl = loadViewer({
    ...base,
    groups: [group("grp_nmda", "Glutamate [NMDA] receptor", {
      members: ["tgt_1", "tgt_2"],
      wikipedia_url: "https://en.wikipedia.org/wiki/NMDA_receptor",
    })],
  });
  withUrl.showGroup(withUrl.groupById("grp_nmda"));
  const html = withUrl.document.getElementById("detail").innerHTML;

  test("the link is there, and it leads", () => {
    assert.ok(html.includes('href="https://en.wikipedia.org/wiki/NMDA_receptor"'));
    assert.ok(html.indexOf("Wikipedia") < html.indexOf("GRP_NMDA"),
      "Wikipedia comes before the ChEMBL record, as on every other panel");
  });

  test("an assembly with no article shows only the ChEMBL record", () => {
    const without = loadViewer({
      ...base,
      groups: [group("grp_iks", "Voltage-gated potassium channel, IKs",
        { members: ["tgt_1", "tgt_2"] })],
    });
    without.showGroup(without.groupById("grp_iks"));
    const out = without.document.getElementById("detail").innerHTML;
    // Not the bare word - the "Links" explanation mentions Wikipedia by name -
    // but a link to one.
    assert.ok(!/href="[^"]*wikipedia/.test(out),
      "no article is a curated answer, not a link to nowhere");
    assert.ok(out.includes("GRP_IKS"));
  });

  test("an absorbed complex naming the same article does not repeat it", () => {
    // All three NMDA records - the 7-member group and the two precise dimers
    // resolve_groups folds into it - name one receptor and take one item, so
    // three identical links would read as three different articles.
    const nested = loadViewer({
      ...base,
      groups: [group("grp_nmda", "Glutamate [NMDA] receptor", {
        members: ["tgt_1", "tgt_2"],
        wikipedia_url: "https://en.wikipedia.org/wiki/NMDA_receptor",
        absorbed: [{
          chembl_id: "CHEMBL1907604", name: "GRIN1/GRIN2A",
          target_type: "PROTEIN COMPLEX", members: ["tgt_1", "tgt_2"],
          wikipedia_url: "https://en.wikipedia.org/wiki/NMDA_receptor",
        }],
      })],
    });
    nested.showGroup(nested.groupById("grp_nmda"));
    const out = nested.document.getElementById("detail").innerHTML;
    assert.equal((out.match(/>Wikipedia</g) || []).length, 1);
  });

  test("a javascript: url on an assembly is refused like any other (invariant 11)", () => {
    const evil = loadViewer({
      ...base,
      groups: [group("grp_x", "Evil", {
        members: ["tgt_1", "tgt_2"],
        wikipedia_url: "javascript:alert(1)",
      })],
    });
    evil.showGroup(evil.groupById("grp_x"));
    const out = evil.document.getElementById("detail").innerHTML;
    assert.ok(!out.includes("javascript:"));
  });
});
