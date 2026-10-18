// Tests for the cohort-1 viewer's decision-making logic (viz/index.html).
//
// The Python suite covers which claims get into the database. This one covers
// what the page then claims about them - which is where this project's actual
// deliverable lives, because the graph is the product rather than a readout of
// the database.
//
// Each test locks in a decision from docs/COHORT-1-DECISIONS.md, or a failure
// that has already happened once.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  loadViewer, buildData, buildShard, molecule, target, claim, endpoint,
  observation, study, viewerHtml, viewerSource, plain,
} from "./cohort_harness.mjs";

// A small catalogue: caffeine with a supported claim, a preliminary claim, a
// broader-layer-only neighbour, and an entry with nothing drawable at all.
function catalogue() {
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE", is_seed: 1,
                 seed_name: "caffeine", admission_reason: "both_routes",
                 route_indication: 1, scope_reasons: "core|general_pain",
                 n_claims_supported: 1, n_claims_preliminary: 1,
                 synonyms: ["guaranine"] }),
      molecule({ id: 2, chembl_id: "CHEMBL190", name: "THEOPHYLLINE ANHYDROUS",
                 synonyms: ["CHEMBL1355736", "theophylline"] }),
      molecule({ id: 3, chembl_id: "CHEMBL_BR", name: "BROADER ONLY",
                 evidence_status: "has_supported_broader_only",
                 n_claims_supported: 1, n_claims_preliminary: 0 }),
      molecule({ id: 4, chembl_id: "CHEMBL_GAP", name: "NO EVIDENCE",
                 evidence_status: "no_eligible_evidence", n_claims_supported: 0,
                 n_claims_preliminary: 0, n_claims_limited: 0, n_observations: 0,
                 gap_reason: "No qualifying evidence found in ChEMBL 37" }),
      molecule({ id: 5, chembl_id: "CHEMBL841", name: "LOPERAMIDE", in_cohort: 0,
                 is_seed: 1, seed_name: "loperamide", route_atc_n: 0,
                 admission_reason: "seed_only", n_claims_supported: 0,
                 evidence_status: "no_eligible_evidence",
                 exclusion_reason: "no ATC N code in family; best scoped indication " +
                                   "is Pain at Early Phase 1" }),
    ],
    targets: [
      target({ chembl_id: "CHEMBLT1", name: "Adenosine receptor A1" }),
      target({ chembl_id: "CHEMBLT2", name: "Adenosine receptor", n_components: 4,
               target_type: "PROTEIN FAMILY" }),
      target({ chembl_id: "CHEMBLT3", name: "Acetylcholinesterase" }),
    ],
    claims: [
      claim({ id: 1, molecule: 1, target: "CHEMBLT1", n_measurements: 12,
              n_publications: 11,
              endpoints: [endpoint({ endpoint_class: "binding:Ki", median_nm: 44900,
                                     n_measurements: 12, n_publications: 11,
                                     supported: 1 }),
                          endpoint({ endpoint_class: "binding:IC50", median_nm: 10700,
                                     n_measurements: 1, n_publications: 1,
                                     supported: 0 })] }),
      claim({ id: 2, molecule: 1, target: "CHEMBLT2", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: "ANTAGONIST",
              mechanism_of_action: "Adenosine receptor antagonist",
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
      claim({ id: 3, molecule: 1, target: "CHEMBLT3", tier: "preliminary",
              tier_reason: "one_publication", multiple_study_support: 0,
              n_measurements: 1, n_studies: 1, n_publications: 1,
              supporting_endpoint_class: null,
              endpoints: [endpoint({ n_measurements: 1, n_publications: 1,
                                     supported: 0, median_nm: 500 })] }),
      claim({ id: 4, molecule: 2, target: "CHEMBLT1", n_measurements: 8,
              n_publications: 6 }),
      claim({ id: 5, molecule: 2, target: "CHEMBLT2", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: "ANTAGONIST",
              n_measurements: 0, n_studies: 0, supporting_endpoint_class: null,
              endpoints: [] }),
      claim({ id: 6, molecule: 3, target: "CHEMBLT1", basis: "broader",
              assignment_classes: "nonhuman" }),
    ],
    indications: { 1: [["D010146", "Pain", "Phase 3", "general_pain", 1]] },
  });
}

describe("the page opens on the caffeine neighbourhood", () => {
  test("caffeine is the initial selection", () => {
    const v = loadViewer(catalogue());
    const opening = v.openingMolecule();
    assert.equal(opening.chembl_id, "CHEMBL113");
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.getSelection().id, 1);
  });

  test("it falls back to the best-evidenced entry rather than an empty canvas", () => {
    const data = buildData({
      molecules: [molecule({ id: 7, chembl_id: "CHEMBL_X", name: "X",
                             n_claims_supported: 3 }),
                  molecule({ id: 8, chembl_id: "CHEMBL_Y", name: "Y",
                             n_claims_supported: 9 })],
    });
    const v = loadViewer(data);
    assert.equal(v.openingMolecule().chembl_id, "CHEMBL_Y");
  });

  test("the defaults are Supported and Preliminary, both assignment layers, and no potency cutoff", () => {
    const v = loadViewer(catalogue());
    assert.deepEqual(plain({
      tier: v.getFilters().tier, basis: v.getFilters().basis,
      potency: v.getFilters().potency,
    }), { tier: "supported_preliminary", basis: "all", potency: null });
  });
});

describe("the three filters are independent and each answers for itself", () => {
  test("Supported-only hides Preliminary and nothing else", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    assert.deepEqual(plain(v.visibleClaimsFor(1).map((c) => c.id)), [1, 2]);
    v.setFilter("tier", "supported_preliminary");
    assert.deepEqual(plain(v.visibleClaimsFor(1).map((c) => c.id)), [1, 2, 3]);
  });

  test("the broader layer is off by default and never mixes into direct human", () => {
    const v = loadViewer(catalogue());
    v.setFilter("basis", "human_direct");
    assert.equal(v.visibleClaimsFor(3).length, 0);
    v.setFilter("basis", "all");
    assert.equal(v.visibleClaimsFor(3).length, 1);
    assert.equal(v.visibleClaimsFor(3)[0].basis, "broader");
  });

  test("an entry whose only evidence is broader is discoverable, with guidance", () => {
    const v = loadViewer(catalogue());
    v.setFilter("basis", "human_direct");
    const mol = v.lookupMolecule(3);
    const gap = v.gapStatement(mol);
    assert.equal(gap.kind, "hidden_by_filters");
    const banners = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banners, /broader claim is hidden/);
    assert.match(banners, /Include broader assignment/);
  });

  test("potency is a display filter with the adopted presets", () => {
    const v = loadViewer(catalogue());
    // claim 1's best median is 10.7 uM, so 100 uM keeps it and 1 uM does not.
    v.setFilter("potency", 100);
    assert.ok(v.visibleClaimsFor(1).some((x) => x.id === 1));
    v.setFilter("potency", 1);
    assert.ok(!v.visibleClaimsFor(1).some((x) => x.id === 1));
    v.setFilter("potency", null);
    assert.ok(v.visibleClaimsFor(1).some((x) => x.id === 1));
  });

  test("a curated claim with no value is hidden for want of one, not as a failure", () => {
    const v = loadViewer(catalogue());
    const curated = v.allClaims().find((c) => c.id === 2);
    assert.equal(v.bestPotency(curated), null);
    v.setFilter("potency", 300);
    assert.equal(v.potencyAllowed(curated), false);
    assert.equal(v.hiddenReason(curated), "potency_no_value");
    const banner = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banner, /hides \d+ weaker claim/);
    assert.match(banner, /for want of a comparable value/);
  });

  test("potency never removes an entry from the catalogue or from search", () => {
    const v = loadViewer(catalogue());
    v.setFilter("potency", 1);
    assert.equal(v.searchCatalogue("caffeine").molecules.length, 1);
    assert.equal(v.allMolecules().length, 5);
  });
});

describe("a tier earned at one endpoint cannot certify another", () => {
  test("the row shows the endpoint that earned Supported, not the strongest one", () => {
    // The failure this guards: a claim replicated at Ki and measured once at
    // IC50 printed "Supported - multiple studies" beside "1 measurement in 1
    // publication", because the row showed whichever endpoint had the lowest
    // median.
    const v = loadViewer(catalogue());
    const c = v.allClaims().find((x) => x.id === 1);
    assert.equal(v.supportingEndpoint(c).endpoint_class, "binding:Ki");
    assert.equal(v.bestPotency(c).endpoint_class, "binding:IC50");
    const html = v.claimRowHTML(c);
    assert.match(html, /binding:Ki median[^<]*12 measurements in 11 publications/);
    assert.match(html, /strongest value[^<]*at binding:IC50/);
  });
});

describe("similarity counts a target once, at its own identity", () => {
  test("two claims at one target are one shared target", () => {
    const data = buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "CHEMBL2",
                                                  name: "BETA" })],
      targets: [target({ chembl_id: "CHEMBLT1" })],
      claims: [
        claim({ id: 1, molecule: 1, target: "CHEMBLT1", role: "binding" }),
        claim({ id: 2, molecule: 1, target: "CHEMBLT1", role: "functional" }),
        claim({ id: 3, molecule: 2, target: "CHEMBLT1", role: "binding" }),
        claim({ id: 4, molecule: 2, target: "CHEMBLT1", role: "curated",
                curated_support: 1, multiple_study_support: 0,
                supporting_endpoint_class: null, endpoints: [] }),
      ],
    });
    const v = loadViewer(data);
    const rows = v.sharedTargets(1);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].n_shared, 1);
  });

  test("a family overlap is distinguishable from an exact protein overlap", () => {
    const v = loadViewer(catalogue());
    const rows = v.sharedTargets(1);
    const theo = rows.find((r) => r.molecule.id === 2);
    assert.equal(theo.n_shared, 2);
    assert.equal(theo.n_exact, 1);   // the single protein
    assert.equal(theo.n_broad, 1);   // the protein family
  });

  test("a family hit is weighted below an exact protein hit", () => {
    const single = buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [target({ chembl_id: "T", target_type: "SINGLE PROTEIN" })],
      claims: [claim({ id: 1, molecule: 1, target: "T" }),
               claim({ id: 2, molecule: 2, target: "T" })],
    });
    const family = buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [target({ chembl_id: "T", target_type: "PROTEIN FAMILY" })],
      claims: [claim({ id: 1, molecule: 1, target: "T" }),
               claim({ id: 2, molecule: 2, target: "T" })],
    });
    const a = loadViewer(single).sharedTargets(1)[0].score;
    const b = loadViewer(family).sharedTargets(1)[0].score;
    assert.ok(b < a, `family score ${b} should be below exact score ${a}`);
  });

  test("an optional layer cannot raise the default direct-human score", () => {
    const v = loadViewer(catalogue());
    const before = v.sharedTargets(1).find((r) => r.molecule.id === 2).score;
    v.setFilter("basis", "all");
    v.setFilter("tier", "supported_preliminary");
    const rows = v.sharedTargets(1);
    const after = rows.find((r) => r.molecule.id === 2).score;
    assert.equal(after, before);
  });
});

describe("every entry stays searchable, including the ones with no edge", () => {
  test("an entry with no drawable evidence is found and says why", () => {
    const v = loadViewer(catalogue());
    const hits = v.searchCatalogue("no evidence").molecules;
    assert.equal(hits.length, 1);
    assert.equal(hits[0].molecule.chembl_id, "CHEMBL_GAP");
    const gap = v.gapStatement(hits[0].molecule);
    assert.equal(gap.kind, "no_eligible_evidence");
    assert.match(gap.text, /ChEMBL 37/);
    assert.match(gap.text, /not an absence of pharmacology/);
  });

  test("a retained seed outside the cohort is found and shown like any other entry", () => {
    // The catalogue will grow past ATC N and the qualifying indications, so a
    // seed the selection rule left out is no longer marked as the odd one out
    // (2026-09-27, at the user's request) - not in its panel, not in search.
    const v = loadViewer(catalogue());
    const results = v.searchCatalogue("loperamide");
    assert.equal(results.molecules.length, 1);
    const html = v.showMolecule(results.molecules[0].molecule);
    assert.ok(!/seed, outside cohort 1/.test(html));
    assert.ok(!/example for designing cohort 2/.test(html));
    assert.ok(!/Not admitted because/.test(html));
    assert.ok(!/seed, outside cohort 1/.test(v.searchResultsHTML(results)));
  });

  test("a seed found by the id it was seeded under resolves to its parent row", () => {
    // Theophylline was seeded as CHEMBL1355736 and lives here as CHEMBL190.
    const v = loadViewer(catalogue());
    const hits = v.searchCatalogue("CHEMBL1355736").molecules;
    assert.equal(hits.length, 1);
    assert.equal(hits[0].molecule.chembl_id, "CHEMBL190");
    assert.equal(hits[0].via, "CHEMBL1355736");
  });

  test("a target is found by its gene symbol and its accession", () => {
    const data = buildData({
      targets: [target({ chembl_id: "T1", name: "Adenosine receptor A1",
                         components: [{ accession: "P30542", gene_symbol: "ADORA1",
                                        description: "A1 receptor" }] })],
    });
    const v = loadViewer(data);
    assert.equal(v.searchCatalogue("ADORA1").targets.length, 1);
    assert.equal(v.searchCatalogue("P30542").targets[0].via, "P30542");
  });

  test("the four gap statements are different statements", () => {
    const v = loadViewer(catalogue());
    v.setFilter("basis", "human_direct");
    assert.equal(v.gapStatement(v.lookupMolecule(4)).kind, "no_eligible_evidence");
    assert.equal(v.gapStatement(v.lookupMolecule(3)).kind, "hidden_by_filters");
    assert.equal(v.gapStatement(v.lookupMolecule(1)), null);
    const limited = v.lookupMolecule(5);
    limited.n_claims_limited = 4;
    assert.equal(v.gapStatement(limited).kind, "unresolved");
  });
});

// A click the way the page really delivers one: the handlers read
// event.target.closest, so a fake target answers for the element it is
// standing in for and null for everything else.
function clickOn(el, ...selectors) {
  return {
    target: {
      closest(sel) { return selectors.includes(sel) ? (el || {}) : null; },
    },
    preventDefault() {},
  };
}

function row(attrs) {
  return { getAttribute(name) { return name in attrs ? attrs[name] : null; } };
}

describe("a popover comes down when the reader is finished with it", () => {
  function opened() {
    const v = loadViewer(catalogue());
    v.setSearchQuery("caffeine");
    v.renderSearch();
    const box = v.document.getElementById("search-results");
    assert.equal(box.hidden, false);
    assert.match(box.innerHTML, /CAFFEINE/);
    return { v, box };
  }

  test("clicking a result closes the list it was chosen from", () => {
    const { v, box } = opened();
    v.onAppClick(clickOn(row({ "data-select": "molecule", "data-id": "2" }),
                         "[data-select]"));
    assert.equal(v.getSelection().id, 2);
    assert.equal(box.hidden, true);
    // Emptied on the refresh the selection triggers, not inside the click.
    assert.equal(box.innerHTML, "");
  });

  // The arrow keys walk the rows the list drew, in the order it drew them, and
  // Enter opens the one they are on - or the first, if they have not moved.
  function keyed(query) {
    const v = loadViewer(catalogue());
    v.setSearchQuery(query);
    v.renderSearch();
    const box = v.document.getElementById("search-results");
    const ids = [...box.innerHTML.matchAll(/data-nav="\d+" data-select="(\w+)" data-id="([^"]+)"/g)]
      .map((m) => m[1] + ":" + m[2]);
    return { v, box, ids };
  }
  const key = (k) => { let prevented = false; return { key: k, preventDefault() { prevented = true; }, get prevented() { return prevented; } }; };

  test("the arrow keys move through the results and hold at either end", () => {
    const { v, box, ids } = keyed("ne");
    assert.ok(ids.length >= 2, "the fixture has to match more than one row");
    assert.equal(v.getSearchActive(), -1);
    const down = key("ArrowDown");
    assert.equal(v.onSearchKeydown(down), true);
    assert.equal(down.prevented, true, "the caret does not jump to the end of the text");
    assert.equal(v.getSearchActive(), 0);
    assert.match(box.innerHTML, /class="row-item active" data-nav="0"/);
    for (let i = 0; i < ids.length + 3; i++) v.onSearchKeydown(key("ArrowDown"));
    assert.equal(v.getSearchActive(), ids.length - 1, "holds at the bottom");
    for (let i = 0; i < ids.length + 3; i++) v.onSearchKeydown(key("ArrowUp"));
    assert.equal(v.getSearchActive(), 0, "holds at the top");
    // Typing starts the walk again from the top.
    v.setSearchQuery("nes");
    assert.equal(v.getSearchActive(), -1);
  });

  test("Enter opens the row the arrows are on, and closes the list", () => {
    const { v, box, ids } = keyed("ne");
    v.onSearchKeydown(key("ArrowDown"));
    v.onSearchKeydown(key("ArrowDown"));
    assert.equal(v.onSearchKeydown(key("Enter")), true);
    const [kind, id] = ids[1].split(":");
    assert.equal(v.getSelection().kind, kind);
    assert.equal(String(v.getSelection().id), id);
    assert.equal(v.isSearchOpen(), false);
    assert.equal(box.innerHTML, "");
  });

  test("Enter with the arrows unmoved opens the first result", () => {
    const { v, ids } = keyed("theophylline");
    v.onSearchKeydown(key("Enter"));
    assert.equal(v.getSelection().kind + ":" + v.getSelection().id, ids[0]);
  });

  test("an arrow key brings a dismissed list back up", () => {
    const { v, box } = keyed("ne");
    v.onDocumentKeydown({ key: "Escape" });
    assert.equal(v.isSearchOpen(), false);
    v.onSearchKeydown(key("ArrowDown"));
    assert.equal(v.isSearchOpen(), true);
    assert.equal(box.hidden, false);
    // Enter on a closed list does nothing rather than opening something unseen.
    v.onDocumentKeydown({ key: "Escape" });
    assert.equal(v.onSearchKeydown(key("Enter")), false);
  });

  test("a click on the graph closes the list, a click in the box does not", () => {
    const { v, box } = opened();
    v.onDocumentClick(clickOn(null, "#graph"));
    assert.equal(v.isSearchOpen(), false);
    assert.equal(box.hidden, true);

    v.setSearchQuery("caffeine");
    v.renderSearch();
    v.onDocumentClick(clickOn({}, "#search-wrap"));
    assert.equal(v.isSearchOpen(), true);
    assert.equal(box.hidden, false);
  });

  test("a dismissed list stays down through a refresh from somewhere else", () => {
    const { v, box } = opened();
    v.onDocumentClick(clickOn(null, "#graph"));
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    assert.equal(box.hidden, true);
    assert.equal(box.innerHTML, "");
    // The query is kept rather than thrown away: clicking back into the box
    // offers the same answers again.
    assert.equal(v.getSearchQuery(), "caffeine");
    v.openSearch();
    v.renderSearch();
    assert.match(box.innerHTML, /CAFFEINE/);
  });

  test("a click outside the display options closes them, one inside does not", () => {
    const v = loadViewer(catalogue());
    const details = v.document.getElementById("view-options");
    details.open = true;
    v.onDocumentClick(clickOn({}, "#view-options"));
    assert.equal(details.open, true);
    v.onDocumentClick(clickOn(null, "#graph"));
    assert.equal(details.open, false);
  });

  test("Escape closes both", () => {
    const { v, box } = opened();
    const details = v.document.getElementById("view-options");
    details.open = true;
    v.onDocumentKeydown({ key: "a" });
    assert.equal(v.isSearchOpen(), true);
    assert.equal(details.open, true);
    v.onDocumentKeydown({ key: "Escape" });
    assert.equal(v.isSearchOpen(), false);
    assert.equal(details.open, false);
    assert.equal(box.innerHTML, "");
  });

  test("About closes like the display options: outside click or Escape", () => {
    const v = loadViewer(catalogue());
    const about = v.document.getElementById("about");
    about.open = true;
    v.onDocumentClick(clickOn({}, "#about"));
    assert.equal(about.open, true);
    v.onDocumentClick(clickOn(null, "#graph"));
    assert.equal(about.open, false);
    about.open = true;
    // Escape dismisses About first and does not also clear the selection.
    const before = v.getSelection();
    assert.equal(v.onDocumentKeydown({ key: "Escape" }), true);
    assert.equal(about.open, false);
    assert.equal(v.getSelection(), before);
  });

  // Capture, not bubble. onFilterClick re-renders the control that was clicked,
  // so a handler running on the way back up would find that button detached,
  // read it as "outside #view-options", and close the popover on every filter
  // change - which is the bug this phase choice exists to prevent.
  test("dismissal is bound on the document, in the capture phase", () => {
    const v = loadViewer(catalogue());
    const names = v.__documentListeners.map((l) => l.name + ":" + l.capture);
    assert.ok(names.includes("click:true"), names.join(", "));
    assert.ok(names.includes("keydown:true"), names.join(", "));
  });

  test("a filter click inside the popover leaves it open", () => {
    const v = loadViewer(catalogue());
    const details = v.document.getElementById("view-options");
    details.open = true;
    const click = clickOn(row({ "data-filter": "tier", "data-value": "supported_preliminary" }),
                          "[data-filter]", "#view-options");
    v.onDocumentClick(click);
    v.onFilterClick(click);
    assert.equal(details.open, true);
    assert.equal(v.getFilters().tier, "supported_preliminary");
  });
});

describe("the whole network is drawn, and a selection lights part of it", () => {
  test("the canvas holds every eligible entry, not just the selection's", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    const g = v.catalogueGraph();
    const keys = g.nodes.map((n) => n.key).sort();
    // Caffeine and theophylline and the two targets they are Supported at.
    // The broader-layer entry and the one with no evidence are not drawn, and
    // acetylcholinesterase is reached only by a Preliminary claim.
    assert.deepEqual(plain(keys), ["m1", "m2", "tCHEMBLT1", "tCHEMBLT2"]);
    assert.equal(g.edges.length, 4);
    // Theophylline is on the canvas without being selected or adjacent to the
    // selection - which is the whole change: the network is the picture.
    v.setSelection("molecule", 1);
    assert.ok(v.catalogueGraph().byKey.has("m2"));
  });

  test("two claims at one target are still one edge", () => {
    const v = loadViewer(catalogue());
    const g = v.catalogueGraph();
    const pairs = g.edges.map((e) => e.from + "|" + e.to);
    assert.equal(new Set(pairs).size, pairs.length);
  });

  test("a selection lights its targets and the molecules on them", () => {
    const v = loadViewer(catalogue());
    const h = v.highlightFor("molecule", 1);
    assert.equal(h.nodes.get("m1"), 0);
    assert.equal(h.nodes.get("tCHEMBLT1"), 1);
    assert.equal(h.nodes.get("tCHEMBLT2"), 1);
    // The second hop: theophylline, on caffeine's targets, held between the
    // neighbourhood and the rest rather than dimmed out with it.
    assert.equal(h.nodes.get("m2"), 2);
  });

  test("nothing is removed from the canvas to light something on it", () => {
    const v = loadViewer(catalogue());
    const drawn = v.catalogueGraph().nodes.length;
    v.setSelection("molecule", 1);
    const lit = v.highlightOpacity();
    assert.equal(lit.nodes.size, drawn);
    assert.equal(lit.highlighted, true);
    // Every node still has an opacity, and the unlit ones are dim rather than
    // gone - a picture you can find your way back out of.
    assert.ok([...lit.nodes.values()].every((o) => o > 0));
  });

  test("a target's neighbourhood has no second hop", () => {
    const v = loadViewer(catalogue());
    const h = v.highlightFor("target", "CHEMBLT1");
    // Every other target of every molecule that binds it is most of the
    // catalogue, which is not a neighbourhood but a reset.
    assert.ok([...h.nodes.values()].every((hop) => hop <= 1));
  });

  test("a pair lights the overlap and nothing else", () => {
    const v = loadViewer(catalogue());
    const h = v.highlightFor("pair", 1, 2);
    const lit = [...h.nodes.keys()].filter((k) => k.charAt(0) === "t").sort();
    assert.deepEqual(plain(lit), ["tCHEMBLT1", "tCHEMBLT2"]);
    // Acetylcholinesterase is caffeine's alone and is not in the pair.
    assert.ok(!h.nodes.has("tCHEMBLT3"));
    assert.ok([...h.nodes.values()].every((hop) => hop <= 1));
  });

  test("a selection with nothing drawable lights nothing rather than emptying it", () => {
    const v = loadViewer(catalogue());
    // Entry 4 has no eligible evidence at all. It stays searchable and its gap
    // statement says so; the canvas simply has nothing of it to light.
    assert.equal(v.highlightFor("molecule", 4), null);
    v.setSelection("molecule", 4);
    const o = v.highlightOpacity();
    assert.equal(o.highlighted, false);
    assert.equal(o.nodes.size, v.catalogueGraph().nodes.length);
  });

  test("a lit node keeps its label at every zoom", () => {
    const v = loadViewer(catalogue());
    // Zoomed out, an unlit node is unlabelled - a thousand labels at the zoom
    // where a thousand nodes fit is a smear over the graph.
    assert.equal(v.labelSize(undefined, false), 0);
    assert.ok(v.labelSize(undefined, true) > 0);
    // But whatever the selection lit stays named, at any zoom. Hiding the
    // label on the thing the reader just clicked is the one way this could be
    // worse than drawing all of them.
    assert.ok(v.labelSize(0, false) > 0);
    assert.ok(v.labelSize(1, false) > 0);
    assert.ok(v.labelSize(2, false) > 0);
  });


  test("a dimmed node's label dims with it", () => {
    const v = loadViewer(catalogue());
    // vis applies a node's opacity to its shape and not to its label, so this
    // has to be written separately or the highlight leaves every name on the
    // canvas at full brightness - which on 1,373 nodes is most of the ink.
    assert.notEqual(v.labelColor(undefined), v.labelColor(0));
    assert.notEqual(v.labelColor(2), v.labelColor(0));
    assert.equal(v.labelColor(1), v.labelColor(0));
  });

  test("the filters decide the picture and the selection does not", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    const before = v.catalogueGraph();
    v.setSelection("target", "CHEMBLT1");
    // Same object: a selection must not cost a pass over the catalogue, and a
    // rebuilt canvas is a moved layout under a reader who only clicked.
    assert.equal(v.catalogueGraph(), before);
    v.setFilter("tier", "supported_preliminary");
    const after = v.catalogueGraph();
    assert.notEqual(after, before);
    assert.ok(after.nodes.length > before.nodes.length);
  });

  test("the graph, the panel and the ranking read the same rule", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    const drawn = new Set(v.catalogueGraph().edges
      .filter((e) => e.from === "m1").map((e) => e.to.slice(1)));
    const panel = new Set(v.visibleClaimsFor(1).map((c) => c.target));
    assert.deepEqual(plain([...drawn].sort()), plain([...panel].sort()));
    v.setFilter("tier", "supported_preliminary");
    const drawn2 = new Set(v.catalogueGraph().edges
      .filter((e) => e.from === "m1").map((e) => e.to.slice(1)));
    const panel2 = new Set(v.visibleClaimsFor(1).map((c) => c.target));
    assert.deepEqual(plain([...drawn2].sort()), plain([...panel2].sort()));
    assert.ok(drawn2.size > drawn.size);
  });
});

describe("the canvas is labelled in the vocabulary the field uses", () => {
  test("a single protein is labelled by its gene symbol", () => {
    const v = loadViewer(catalogue());
    const t = v.lookupTarget("CHEMBLT1");
    t.components = [{ accession: "P30542", gene_symbol: "ADORA1" }];
    // "Adenosine receptor A1" is 21 characters and the panel still says it;
    // the canvas says ADORA1, which is the same protein and the name the
    // literature uses for it.
    assert.equal(v.targetLabel(t), "ADORA1");
    assert.equal(t.name, "Adenosine receptor A1");
  });

  test("a family or complex keeps its own name", () => {
    const v = loadViewer(catalogue());
    const fam = v.lookupTarget("CHEMBLT2");
    fam.components = [{ accession: "P30542", gene_symbol: "ADORA1" },
                      { accession: "P29274", gene_symbol: "ADORA2A" }];
    // Picking one member's symbol for a family would assert exactly the merge
    // D06 refuses: a family claim is a claim about the set.
    assert.equal(v.targetLabel(fam), "Adenosine receptor");
    fam.components = [{ accession: "P30542", gene_symbol: "ADORA1" }];
    assert.equal(v.targetLabel(fam), "Adenosine receptor",
                 "a one-member family is still a family");
  });

  test("a name too long to draw is cut, and only on the canvas", () => {
    const v = loadViewer(catalogue());
    const long = "Dual specificity calcium/calmodulin-dependent phosphodiesterase 1C";
    const t = { name: long, target_type: "PROTEIN COMPLEX", components: [] };
    assert.ok(v.targetLabel(t).length < long.length);
    assert.ok(v.targetLabel(t).endsWith("…"));
    // The untouched name is what every panel reads.
    assert.equal(t.name, long);
  });
});

describe("the canvas control thins the picture without thinning the catalogue", () => {
  test("it is off by default", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.getFilters().periphery, "show");
    assert.equal(v.catalogueGraph().pruned, null);
  });

  test("a target with one molecule at it comes off the canvas", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported_preliminary");
    const before = v.catalogueGraph();
    // Acetylcholinesterase is caffeine's alone - one molecule, one edge.
    assert.ok(before.byKey.has("tCHEMBLT3"));
    v.setFilter("periphery", "hide");
    const after = v.catalogueGraph();
    assert.ok(!after.byKey.has("tCHEMBLT3"));
    assert.equal(after.pruned.targets, 1);
    // The two adenosine targets have both molecules at them and stay.
    assert.ok(after.byKey.has("tCHEMBLT1"));
    assert.ok(after.byKey.has("tCHEMBLT2"));
  });

  test("it changes what is drawn and nothing about what exists", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported_preliminary");
    const claims = v.visibleClaimsFor(1).map((c) => c.id);
    const ranked = v.sharedTargets(1).map((r) => r.molecule.id);
    const found = v.searchCatalogue("acetylcholinesterase").targets.length;
    v.setFilter("periphery", "hide");
    // The one line this page keeps: "is it in the picture" and "is it drawn"
    // are two questions, and only the claim filters answer the first.
    assert.deepEqual(plain(v.visibleClaimsFor(1).map((c) => c.id)), plain(claims));
    assert.deepEqual(plain(v.sharedTargets(1).map((r) => r.molecule.id)), plain(ranked));
    assert.equal(v.searchCatalogue("acetylcholinesterase").targets.length, found);
    assert.ok(v.gapStatement(v.lookupMolecule(1)) === null);
  });

  // The count on the canvas: what the claim filters keep, out of the whole
  // catalogue, and - only with the canvas control on - what of that is drawn.
  test("the canvas counts what the filters keep against the whole catalogue", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    // Caffeine and theophylline, at the two targets they are Supported at.
    assert.equal(v.graphCountsHTML(),
                 "Filters keep <b>2</b> of 5 molecules and <b>2</b> of 3 targets");
    v.setFilter("tier", "supported_preliminary");
    assert.match(v.graphCountsHTML(), /<b>2<\/b> of 5 molecules and <b>3<\/b> of 3 targets$/);
  });

  test("the canvas control adds what is drawn, and moves no kept count", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported_preliminary");
    const kept = v.graphCountsHTML();
    v.setFilter("periphery", "hide");
    const h = v.graphCountsHTML();
    assert.ok(h.startsWith(kept + "<br>"), h);
    // Acetylcholinesterase, caffeine's alone, is kept and not drawn.
    assert.match(h, /Drawn: <b>3<\/b> molecules and <b>2<\/b> targets, single-molecule targets hidden/);
  });

  test("it says what it took, including the molecules it emptied", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported_preliminary");
    v.setFilter("periphery", "hide");
    const banner = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banner, /Canvas thinned/);
    assert.match(banner, /All stay in the panels, the similarity ranking and search/);
  });
});

describe("an edge on the canvas opens the pair behind it", () => {
  test("clicking an edge selects the molecule-target pair", () => {
    const v = loadViewer(catalogue());
    const e = v.catalogueGraph().byPair.get("m1|tCHEMBLT1");
    assert.ok(e);
    v.onGraphClick({ nodes: [], edges: [e.id] });
    assert.equal(v.getSelection().kind, "edge");
    assert.equal(v.getSelection().id, 1);
    assert.equal(v.getSelection().extra, "CHEMBLT1");
  });

  test("a node wins when vis reports both", () => {
    const v = loadViewer(catalogue());
    const e = v.catalogueGraph().byPair.get("m1|tCHEMBLT1");
    v.onGraphClick({ nodes: ["tCHEMBLT1"], edges: [e.id] });
    assert.equal(v.getSelection().kind, "target");
  });

  // Every drawn node at a 10x10 box round where `at` puts it (the rest piled
  // out of the way), and every line between them, as vis's body holds them.
  function placeBody(v, at, scale) {
    const g = v.catalogueGraph();
    const nodes = {}, edges = {};
    for (const n of g.nodes) {
      const p = at[n.key] || { x: 5000, y: 5000 };
      nodes[n.key] = { x: p.x, y: p.y, options: {},
                       shape: { left: p.x - 5, top: p.y - 5, width: 10, height: 10 } };
    }
    for (const e of g.edges.concat(g.links)) {
      edges[e.id] = { connected: true, from: nodes[e.from], to: nodes[e.to] };
    }
    const net = v.__networks[0];
    net.body = { nodes: nodes, edges: edges };
    net.scale = scale;
  }
  const click = (x, y, vis) =>
    Object.assign({ nodes: [], edges: [], pointer: { canvas: { x: x, y: y } } }, vis || {});

  test("a click beside a lit line opens it, not the dimmed node vis found under it", () => {
    const v = loadViewer(catalogue());
    v.select("target", "CHEMBLT3");
    // Caffeine's one lit line runs along y = 0; theophylline, dimmed, sits on it.
    placeBody(v, { m1: { x: 0, y: 0 }, tCHEMBLT3: { x: 200, y: 0 },
                   m2: { x: 100, y: 4 }, tCHEMBLT1: { x: 100, y: 300 } }, 1);
    v.onGraphClick(click(100, 3, { nodes: ["m2"] }));
    assert.deepEqual(plain(v.getSelection()),
                     plain({ kind: "edge", id: 1, extra: "CHEMBLT3" }));
  });

  test("the lit line's reach is in screen pixels, whatever the zoom", () => {
    const at = { m1: { x: 0, y: 0 }, tCHEMBLT3: { x: 2000, y: 0 }, m2: { x: 1000, y: 60 } };
    // 60 canvas units is 6 pixels at zoom 0.1, where vis's own 10 is one.
    const far = loadViewer(catalogue());
    far.select("target", "CHEMBLT3");
    placeBody(far, at, 0.1);
    far.onGraphClick(click(1000, 60, { nodes: ["m2"] }));
    assert.equal(far.getSelection().kind, "edge");
    // And 60 pixels at zoom 1, which is not beside the line at all.
    const near = loadViewer(catalogue());
    near.select("target", "CHEMBLT3");
    placeBody(near, at, 1);
    near.onGraphClick(click(1000, 60, { nodes: ["m2"] }));
    assert.deepEqual(plain(near.getSelection()), plain({ kind: "molecule", id: 2, extra: null }));
  });

  test("a lit node under the pointer still wins over its own lines", () => {
    const v = loadViewer(catalogue());
    v.select("target", "CHEMBLT3");
    placeBody(v, { m1: { x: 0, y: 0 }, tCHEMBLT3: { x: 200, y: 0 } }, 1);
    v.onGraphClick(click(198, 1));
    assert.deepEqual(plain(v.getSelection()),
                     plain({ kind: "target", id: "CHEMBLT3", extra: null }));
  });

  test("the selection's own lines come before the second hop's", () => {
    const v = loadViewer(catalogue());
    v.select("molecule", 1);
    // Theophylline's echo line to A1 is nearer the pointer than caffeine's own.
    placeBody(v, { m1: { x: 0, y: 0 }, tCHEMBLT3: { x: 200, y: 0 },
                   tCHEMBLT1: { x: 0, y: 10 }, m2: { x: 200, y: 10 } }, 1);
    const echo = v.catalogueGraph().byPair.get("m2|tCHEMBLT1");
    // 6 from caffeine's line, 4 from theophylline's, which vis would take.
    v.onGraphClick(click(100, 6, { edges: [echo.id] }));
    assert.deepEqual(plain(v.getSelection()),
                     plain({ kind: "edge", id: 1, extra: "CHEMBLT3" }));
  });

  test("with nothing lit near the pointer, vis's own answer stands", () => {
    const v = loadViewer(catalogue());
    v.select("target", "CHEMBLT3");
    placeBody(v, { m1: { x: 0, y: 0 }, tCHEMBLT3: { x: 200, y: 0 }, m2: { x: 100, y: 100 } }, 1);
    v.onGraphClick(click(100, 100, { nodes: ["m2"] }));
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.getSelection().id, 2);
  });

  test("the panel reads every claim on the pair and adds none of them", () => {
    const v = loadViewer(catalogue());
    const mol = v.lookupMolecule(1), t = v.lookupTarget("CHEMBLT1");
    const h = v.showEdge(mol, t, null);
    assert.match(h, /CAFFEINE/);
    assert.match(h, /Adenosine receptor A1/);
    // 389 of 1,962 edges carry more than one claim, so opening one of them
    // would be sampling. Each is a block here, whole, in the one panel.
    assert.match(h, /counted as <b>one<\/b> shared target/);
    assert.match(h, /class="claim-block"/);
    assert.match(h, /Measurements \(exact\)/);
    assert.match(h, /Endpoint classes/);
  });

  test("a claim is read here and in no panel of its own", () => {
    // Reading one pair used to be a walk through several panels - the line, a
    // claim, back out, the next claim - and the retained observations were not
    // on that walk at all.
    const src = viewerSource();
    assert.ok(!/function showClaim\b/.test(src), "showClaim is still here");
    assert.ok(!/data-select="claim"/.test(src), "a row still opens a claim panel");
  });

  test("two claims on one pair are two blocks in one panel", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "T" })],
      claims: [claim({ id: 1, molecule: 1, target: "T", role: "binding" }),
               claim({ id: 2, molecule: 1, target: "T", role: "functional" })],
    }));
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T"), null);
    assert.equal((h.match(/class="claim-block"/g) || []).length, 2);
    assert.match(h, /2 claims drawn as this line/);
    assert.match(h, /counted as <b>one<\/b> shared target/);
  });

  test("the claims fold, and sit under the kind of interaction they assert", () => {
    // 2026-09-25, at the user's request: a subtitle per curated action, then
    // measured binding, then measured functional - and the section folds.
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "T" })],
      claims: [claim({ id: 1, molecule: 1, target: "T", role: "functional" }),
               claim({ id: 2, molecule: 1, target: "T", role: "binding" }),
               claim({ id: 3, molecule: 1, target: "T", role: "curated",
                       tier_reason: "curated_support", curated_support: 1,
                       multiple_study_support: 0, action_type: "ANTAGONIST",
                       n_measurements: 0, n_studies: 0, supporting_endpoint_class: null,
                       endpoints: [] })],
    }));
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T"), null);
    // The section starts folded like every other, its count on the heading.
    assert.match(h, /<details class="section"><summary class="section-toggle" data-fold="edge_claims">/);
    const at = (k) => h.indexOf('data-fold="edge_group_' + k + '"');
    assert.ok(at("action_ANTAGONIST") > 0);
    assert.ok(at("action_ANTAGONIST") < at("role_binding"));
    assert.ok(at("role_binding") < at("role_functional"));
    assert.match(h, /tabindex="0">Antagonist<[^]*?\(1\) <span class="muted">· curated by ChEMBL/);
    assert.match(h, /measured affinity, no direction/);
    // The same three claims, once each, and nothing added.
    assert.equal((h.match(/class="claim-block"/g) || []).length, 3);
    assert.match(h, /3 claims drawn as this line/);
    // A group folded by the reader stays folded on the next render.
    v.setSectionOpen("edge_group_role_binding", false);
    const again = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T"), null);
    assert.match(again, /<details class="subsection"><summary class="subsection-toggle" data-fold="edge_group_role_binding">/);
    v.setSectionOpen("edge_group_role_binding", true);
  });

  test("a block under a mechanism heading does not name the mechanism again", () => {
    const v = loadViewer(catalogue());
    const c = v.allClaims().find((x) => x.id === 3);   // a Preliminary binding claim
    assert.match(v.claimDetail(c), /^binding · /);
    assert.ok(!/^binding · /.test(v.claimDetail(c, true)));
    assert.match(v.claimDetail(c, true), /^binding:Ki median/);
    const cur = v.allClaims().find((x) => x.id === 2);  // curated ANTAGONIST
    assert.match(v.claimDetail(cur), /ANTAGONIST/);
    assert.ok(!/ANTAGONIST/.test(v.claimDetail(cur, true)));
  });

  test("a row that is a fact does not offer itself as a door", () => {
    // The panel lists every measurement inline now. A hundred rows that light
    // up under the cursor and do nothing when clicked is an affordance the
    // page cannot honour.
    const v = loadViewer(catalogue());
    const h = v.observationRowHTML(observation(), []);
    assert.match(h, /class="row-item static"/);
    assert.match(viewerHtml(), /\.row-item\.static \{ cursor: default; \}/);
  });

  test("it lights that edge and its two ends and nothing else", () => {
    const v = loadViewer(catalogue());
    const h = v.highlightFor("edge", 1, "CHEMBLT1");
    assert.deepEqual(plain([...h.nodes.keys()].sort()), ["m1", "tCHEMBLT1"]);
    assert.equal(h.edges.size, 1);
  });

  test("an edge the filters have taken away says so rather than going blank", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    // Caffeine's acetylcholinesterase claim is Preliminary and hidden by default.
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT3"), null);
    assert.match(h, /No line under the current filters/);
    assert.match(h, /which hide every claim between these two/);
    // And it is still shown, because it exists: the filter says what it took.
    assert.match(h, /Hidden by the current filters/);
  });
});

describe("the legend is on the page and says what the canvas draws", () => {
  test("it is a sibling of the canvas, not a child of it", () => {
    const html = viewerHtml();
    // vis-network empties its container when it builds the canvas, so a legend
    // inside #graph is rendered once and then silently deleted on the first
    // draw. That is exactly how it went missing, and it survives a read of the
    // code: renderLegend runs, and the markup it wrote is gone.
    assert.match(html, /<div id="graph"><\/div>/);
    assert.ok(html.indexOf('id="legend"') > html.indexOf('id="graph"'));
    assert.match(html, /#graph-wrap\s*\{[^}]*position:\s*relative/);
  });

  test("every colour the canvas can draw is in it", () => {
    const v = loadViewer(catalogue());
    const html = v.legendRows().map((b) => b[1].map((r) => r[0]).join("")).join("");
    // Read out of the styling code rather than restated, so the legend and the
    // canvas cannot drift: a swatch in a colour the canvas no longer uses
    // explains a distinction the reader cannot see.
    const edge = (tier, curated) =>
      v.edgeStyle({ claims: [{ tier, curated_support: curated ? 1 : 0 }] }).color.color;
    for (const c of [edge("supported", true), edge("supported", false),
                     edge("preliminary", false)]) {
      assert.ok(html.includes(c), "no legend row draws " + c);
    }
    const mol = (n) => v.nodeStyle({ kind: "molecule", ref: { n_claims_supported: n } });
    assert.ok(html.includes(mol(1).color.border));
    assert.ok(html.includes(mol(0).color.border));
    assert.ok(html.includes(v.nodeStyle(
      { kind: "target", ref: { target_type: "PROTEIN FAMILY" } }).color.border));
  });

  test("it does not spend three rows explaining that dim means unselected", () => {
    // The legend is pinned over the graph it explains, and every row it holds
    // is graph it is covering. Bright-means-selected is the one thing on this
    // page nobody has to be told, so it is the first row to go.
    const v = loadViewer(catalogue());
    assert.equal(v.legendRows().find((b) => /opacity/i.test(b[0])), undefined);
    // Still three steps on the canvas, still written from one place: the rows
    // went, the behaviour did not.
    assert.ok(v.edgeOpacity(1) > v.edgeOpacity(2));
    assert.ok(v.edgeOpacity(2) > v.edgeOpacity(undefined));
  });

  test("colouring by mechanism swaps the colour block for the actions on screen", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    v.setFilter("lineColor", "evidence");
    const blockTitles = () => v.legendRows().map((b) => b[0]);
    assert.ok(blockTitles().some((t) => t.startsWith("Line colour · evidence")));

    v.setFilter("lineColor", "mechanism");
    const titles = blockTitles();
    assert.ok(titles.some((t) => t.startsWith("Line colour · mechanism")));
    assert.ok(!titles.some((t) => t.startsWith("Line colour · evidence")));
    // The dashes still carry the evidence in this mode, so the legend has to
    // say so somewhere: the colour block no longer can.
    const ev = v.legendRows().find((b) => b[0] === "Evidence")[1].map((r) => r[1]);
    assert.ok(ev.includes("Supported") && ev.includes("Preliminary (1 study)"));

    const rows = v.legendRows().find((b) => b[0].startsWith("Line colour"))[1];
    const labels = rows.map((r) => r[1]);
    assert.deepEqual(plain(labels), ["antagonist (2)", "no curated mechanism (2)"]);
  });

  test("every colour the canvas draws in mechanism mode has a legend row", () => {
    // The legend is read off the canvas rather than off the palette, which is
    // what makes this hold when a new action arrives in the data - the failure
    // the legacy page had twice, where a mechanism drew in a colour nothing
    // named.
    const v = loadViewer(catalogue());
    v.setFilter("lineColor", "mechanism");
    const html = v.legendRows().map((b) => b[1].map((r) => r[0]).join("")).join("");
    for (const e of v.catalogueGraph().edges) {
      assert.ok(html.includes(v.edgeColor(e).color),
                "no legend row draws " + v.edgeColor(e).color);
    }
  });
});

describe("evidence loads on demand and reconciles to what it claims", () => {
  function shard() {
    return buildShard({
      molecule: 1,
      studies: [study({ study_key: "pmid:1", pubmed_id: 1 }),
                study({ study_key: "pmid:2", pubmed_id: 2, title: "Second paper" })],
      observations: [
        observation({ activity_id: 1, claim_id: 1, study: 0 }),
        observation({ activity_id: 2, claim_id: 1, study: 1, value_nm: 200 }),
        observation({ activity_id: 3, claim_id: 1, value_status: "bound",
                      standard_relation: ">", value_nm: null, counted: 0, study: 0 }),
      ],
      claims: [claim({ id: 99, molecule: 1, target: "CHEMBLT1",
                       tier: "limited_or_unresolved", tier_reason: "censored_only",
                       multiple_study_support: 0, n_measurements: 0, n_bounds: 3,
                       supporting_endpoint_class: null, endpoints: [] })],
    });
  }

  test("a shard registers and is cached", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.evidenceFor(1), null);
    v.registerEvidence(shard());
    assert.equal(v.evidenceFor(1).observations.length, 3);
  });

  test("rows counted into the median equal what the summary says", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(shard());
    const ev = v.evidenceFor(1);
    const rows = ev.byClaim.get(1);
    assert.equal(rows.filter((o) => o.counted).length, 2);
    assert.equal(v.allClaims().find((c) => c.id === 1).endpoints[0].n_measurements, 12);
    // The fixture's summary and its rows disagree on purpose nowhere else;
    // this asserts the accessor, and the build-time check in
    // scripts/cohort/validate.py asserts the equality across the real data.
    assert.equal(rows.filter((o) => o.value_status === "bound").length, 1);
  });

  test("a bound is shown with its relation and never as an exact value", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(shard());
    const ev = v.evidenceFor(1);
    const bound = ev.byClaim.get(1).find((o) => o.value_status === "bound");
    const html = v.observationRowHTML(bound, ev.studies);
    assert.match(html, /&gt; 100 nM/);
    assert.ok(!/counted<\/span>/.test(html.replace("not counted", "")));
    assert.match(html, /no effect seen up to this concentration/);
  });

  test("a conditional mass conversion is labelled as conditional", () => {
    const v = loadViewer(catalogue());
    const o = observation({ value_status: "conditional", value_nm: 2500, counted: 0,
                            conversion_kind: "mass",
                            conversion_note: "1 ug.mL-1 -> 2500 nM using MW 400" });
    const html = v.observationRowHTML(o, []);
    assert.match(html, /conditional/);
    assert.match(html, /wrong salt form/);
  });

  test("retained observations are inspectable without a graph edge", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(shard());
    const html = v.showRetained(v.lookupMolecule(1), v.evidenceFor(1));
    assert.match(html, /censored_only/);
    assert.match(html, /None is drawn/);
    assert.match(html, /retained claims<\/h3>/);
    // And the retained claim is not in the drawable set.
    assert.ok(!v.allClaims().some((c) => c.id === 99 && c.tier !== "limited_or_unresolved"));
  });

  test("a missing shard is a missing file, not an absence of evidence", () => {
    const v = loadViewer(catalogue());
    const html = v.claimEvidenceHTML(v.allClaims()[0], null, true);
    assert.match(html, /did not load/);
    assert.match(html, /not missing evidence/);
  });

  test("a shard still in flight says so instead", () => {
    // Not yet and not there are different statements about a molecule's
    // evidence, and only one of them is about the data.
    const v = loadViewer(catalogue());
    assert.match(v.claimEvidenceHTML(v.allClaims()[0], null, false), /Loading/);
  });
});

// A retained claim was an island. It is filed away from the catalogue, under a
// rule it failed, spelled as the rule's own token - and the panel it opened
// counted the other claims on its pair by subtracting itself from the drawn
// edge's claim list, which is one minus one when the claim is not on that edge.
//
// TOZADENANT is the case it was reported on: one functional row at Adenosine
// receptor A2b with no relation and no value, filed under "invalid_units_only",
// beside three exact Ki measurements at the same protein that nothing on the
// panel mentioned. The fixture's shard is that shape - retained claim 99 at
// CHEMBLT1, where claim 1 is Supported over 12 measurements.
describe("a retained claim says what else the pair holds", () => {
  function pairShard() {
    return buildShard({
      molecule: 1,
      studies: [study({ study_key: "pmid:1", pubmed_id: 1 })],
      observations: [
        observation({ activity_id: 5, claim_id: 99, role: "functional",
                      endpoint_class: "functional:Ki", standard_relation: null,
                      standard_value: null, standard_units: null, value_nm: null,
                      value_status: "unresolved", counted: 0, assay_type: "F",
                      study: 0 }),
      ],
      claims: [claim({ id: 99, molecule: 1, target: "CHEMBLT1", role: "functional",
                       tier: "limited_or_unresolved", tier_reason: "invalid_units_only",
                       multiple_study_support: 0, n_measurements: 0, n_rows: 1,
                       n_unresolved: 1, n_studies: 1, n_publications: 1,
                       supporting_endpoint_class: null, endpoints: [] })],
    });
  }

  function retainedClaim(v) {
    return v.evidenceFor(1).claims.find((c) => c.id === 99);
  }

  test("the heading names the rule rather than spelling its token", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const html = v.showRetained(v.lookupMolecule(1), v.evidenceFor(1));
    assert.match(html, /No resolvable value/);
    // The token is still there, inside the explanation, because it is what the
    // database stores and the thing to grep for - and not beside the label,
    // which would be one fact wearing two headings.
    assert.match(html, /Recorded as invalid_units_only/);
    assert.ok(!/>invalid_units_only \(1\)/.test(html));
  });

  test("every reason the build can write has a name on the page", () => {
    const v = loadViewer(catalogue());
    // The same list scripts/cohort/evidence.py assigns; tests/test_cohort_build.py
    // holds the two together against the source rather than against this copy.
    for (const r of ["curated_support", "multiple_study_support",
                     "multiple_publications_split_across_endpoint_classes",
                     "one_publication", "deposited_datasets_only", "patents_only",
                     "patents_and_deposits_only",
                     "unresolved_study_provenance", "conditional_conversion_only",
                     "censored_only", "invalid_units_only",
                     "curated_no_target_assigned", "curated_target_not_claimable",
                     "curated_indirect", "curated_untraceable"]) {
      assert.match(v.reasonHelp(r), /class="help-text"/, r + " has no explanation");
      assert.notEqual(v.reasonLabel(r), r, r + " is not named");
    }
  });

  test("a reason this page has never seen falls back to the build's token", () => {
    // Silence would be indistinguishable from a reason that was never given
    // one, which is the failure helpLabel had with the edge panel's "Claims".
    const v = loadViewer(catalogue());
    assert.equal(v.reasonLabel("some_new_rule"), "some_new_rule");
    assert.equal(v.reasonHelp("some_new_rule"), "some_new_rule");
  });

  test("the row in the retained list counts the pair's other claims", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const html = v.showRetained(v.lookupMolecule(1), v.evidenceFor(1));
    assert.match(html, /1 other claim between these two/);
    assert.match(html, /counted as one shared target/);
  });

  test("the pair panel reads the retained claim beside the drawn one", () => {
    // The Supported claim at this protein is 12 measurements over 11
    // publications; the retained one is a single functional row with no
    // resolvable value. Arriving on either of them used to show that one and
    // nothing about the other.
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const html = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT1"),
                            v.evidenceFor(1));
    assert.equal((html.match(/class="claim-block"/g) || []).length, 2);
    assert.match(html, /1 claim drawn as this line/);
    assert.match(html, /1 retained, backing no line/);
    assert.match(html, /Retained: meets neither the Supported/);
    assert.match(html, /Supported · multiple studies/);
    assert.match(html, /No resolvable value/);
    // They are listed, never added: the pair is one shared target (invariant 13).
    assert.match(html, /counted as <b>one<\/b> shared target/);
  });

  test("the retained ones are absent from the panel until the shard lands", () => {
    // They live in the molecule's shard rather than in the startup catalogue,
    // which is exactly why they back nothing - so an entry the catalogue says
    // has some reports the count as still coming rather than printing one it
    // cannot yet stand behind.
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, n_claims_limited: 1 })],
      targets: [target({ chembl_id: "T" })],
      claims: [claim({ id: 1, molecule: 1, target: "T" })],
    }));
    const html = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T"), null);
    assert.equal((html.match(/class="claim-block"/g) || []).length, 1);
    assert.match(html, /retained claims still loading/);

    // And an entry the catalogue says has none does not wait for them.
    const none = loadViewer(catalogue());
    assert.ok(!/still loading/.test(
      none.showEdge(none.lookupMolecule(1), none.lookupTarget("CHEMBLT1"), null)));
  });

  test("the row in the molecule-wide retained list opens the pair", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const html = v.showRetained(v.lookupMolecule(1), v.evidenceFor(1));
    assert.match(html, /data-select="edge" data-id="1" data-other="CHEMBLT1"/);
  });

  test("a pair with no retained claim says nothing about retained ones", () => {
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const html = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT3"),
                            v.evidenceFor(1));
    assert.ok(!/backing no line/.test(html));
    assert.ok(!/still loading/.test(html));
  });

  test("a claim with no usable value says what it is made of", () => {
    // "functional \u00b7 SINGLE PROTEIN" was the whole row, and the count of
    // rows behind it was a click away in the panel.
    const v = loadViewer(catalogue());
    v.registerEvidence(pairShard());
    const row = v.claimRowHTML(retainedClaim(v));
    assert.match(row, /1 row with no resolvable value/);
    assert.ok(!/no resolvable value, no exact value/.test(row));
  });
});

describe("a shard that arrives late belongs to the claim that asked for it", () => {
  // loadEvidence injects a <script> tag, so a shard is genuinely asynchronous
  // and a reader can select a second claim before the first one's rows land.
  // The guard that was here read the live selection object on both sides of
  // the comparison and so was true by construction; a shard for molecule A
  // painted its measurements into the panel of whatever claim was open by the
  // time it arrived.
  function shardFor(moleculeId, claimId) {
    return buildShard({
      molecule: moleculeId,
      studies: [study({ study_key: "pmid:" + claimId, pubmed_id: claimId })],
      observations: [observation({ activity_id: claimId * 10, claim_id: claimId,
                                   molecule: moleculeId, study: 0 })],
    });
  }

  test("a shard for a pair the reader has left does not paint over the new one", () => {
    const v = loadViewer(catalogue());
    // Caffeine and theophylline both have a claim at CHEMBLT1, so the two
    // selections differ only in the molecule - which is why the guard has to
    // read both ends of the pair and not only one.
    v.select("edge", 1, "CHEMBLT1");
    v.select("edge", 2, "CHEMBLT1");
    const detail = v.document.getElementById("detail");
    detail.innerHTML = "SENTINEL";

    v.registerEvidence(shardFor(1, 1));
    assert.equal(detail.innerHTML, "SENTINEL",
                 "caffeine's shard redrew theophylline's pair panel");

    v.registerEvidence(shardFor(2, 4));
    assert.notEqual(detail.innerHTML, "SENTINEL",
                    "the selected pair's own shard still redraws it");
  });

  test("a retained entry's shard only redraws the panel while it is selected", () => {
    const v = loadViewer(catalogue());
    v.select("retained", 1);
    v.select("molecule", 2);
    const detail = v.document.getElementById("detail");
    detail.innerHTML = "SENTINEL";
    v.registerEvidence(shardFor(1, 1));
    assert.equal(detail.innerHTML, "SENTINEL");
  });
});

describe("the target panel counts molecules, not claims", () => {
  // Invariant 13: the heading said "Molecules" and printed the number of
  // claims, while the same molecule appeared twice in the list under it.
  function twoClaimsAtOneTarget() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
                  molecule({ id: 2, chembl_id: "CHEMBL2", name: "OTHER" })],
      targets: [target({ chembl_id: "CHEMBLT1", name: "Adenosine receptor A1" })],
      claims: [
        claim({ id: 1, molecule: 1, target: "CHEMBLT1", n_publications: 11 }),
        claim({ id: 2, molecule: 1, target: "CHEMBLT1", role: "curated",
                tier_reason: "curated_support", curated_support: 1,
                multiple_study_support: 0, action_type: "ANTAGONIST",
                n_measurements: 0, n_studies: 0, n_publications: 0,
                supporting_endpoint_class: null, endpoints: [] }),
        claim({ id: 3, molecule: 2, target: "CHEMBLT1", n_publications: 2 }),
      ],
    });
  }

  test("one molecule with two claims here is one molecule", () => {
    const v = loadViewer(twoClaimsAtOneTarget());
    const html = v.showTarget(v.lookupTarget("CHEMBLT1"));
    assert.match(html, /class="small target-molecules">[^\n]*?2 molecules<[\s\S]*?· 3 claims/);
    // And a section holding one molecule twice says so beside its claim count:
    // both rows are still there, because a curated mechanism and a measured
    // binding claim are two kinds of evidence rather than two strengths of one.
    assert.match(html, /data-fold="target_claims_supported">[\s\S]*? \(3\) <span class="muted">· 2 molecules<\/span><\/summary>/);
    // Both rows stay, and both open the pair that holds them - which is now
    // the one panel where either claim is read.
    assert.equal((html.match(/data-select="edge"/g) || []).length, 3);
  });

  test("molecules are ordered by kind of evidence, then potency, and none is cut off", () => {
    // Curated-only used to sort last (a curated mechanism has 0 publications)
    // and the list stopped at 60, which hid 22 of the 41 curated DRD2 drugs.
    const mols = [], claims = [];
    const add = (id, name, over) => {
      mols.push(molecule({ id, chembl_id: "C" + id, name }));
      claims.push(claim(Object.assign({ id, molecule: id, target: "T" }, over)));
    };
    const curated = { role: "curated", tier_reason: "curated_support", curated_support: 1,
                      multiple_study_support: 0, n_publications: 0, n_measurements: 0,
                      endpoints: [] };
    add(1, "PRELIM", { tier: "preliminary", multiple_study_support: 0, n_publications: 1,
                       endpoints: [endpoint({ median_nm: 1 })] });
    add(2, "WEAK REPLICATED", { n_publications: 20, endpoints: [endpoint({ median_nm: 5000 })] });
    add(3, "STRONG REPLICATED", { n_publications: 2, endpoints: [endpoint({ median_nm: 3 })] });
    add(4, "CURATED ONLY", curated);
    add(5, "BROADER", { basis: "broader", endpoints: [endpoint({ median_nm: 0.1 })] });
    // A molecule with both kinds leads.
    add(6, "BOTH", curated);
    claims.push(claim({ id: 7, molecule: 6, target: "T", endpoints: [endpoint({ median_nm: 900 })] }));
    for (let i = 0; i < 65; i++) add(100 + i, "FILLER " + i, { tier: "preliminary",
      multiple_study_support: 0, n_publications: 1, endpoints: [endpoint({ median_nm: 10 + i })] });
    const v = loadViewer(buildData({ molecules: mols, targets: [target({ chembl_id: "T" })], claims }));
    v.setFilter("tier", "supported_preliminary");
    v.setFilter("basis", "all");
    const html = v.showTarget(v.lookupTarget("T"));
    // Split by tier now, and the order holds inside each section.
    const section = (key) => {
      const start = html.indexOf('data-fold="target_claims_' + key + '"');
      const end = html.indexOf("</details>", start);
      return [...new Set([...html.slice(start, end).matchAll(/data-select="edge" data-id="(\d+)"/g)]
        .map((m) => v.lookupMolecule(Number(m[1])).name))];
    };
    const supported = section("supported");
    assert.deepEqual(plain(supported),
      ["BOTH", "CURATED ONLY", "STRONG REPLICATED", "WEAK REPLICATED", "BROADER"],
      "broader-layer only comes after direct human");
    const preliminary = section("preliminary");
    assert.equal(preliminary[0], "PRELIM");
    assert.equal(supported.length + preliminary.length, 71, "every molecule is listed");
    assert.doesNotMatch(html, /more not listed/);
  });

  test("a target's claims group by curated mechanism under the molecule panel's toggle", () => {
    // The same "Group claims by" state as the molecule panel (2026-09-26): one
    // section per curated action, then what was measured, with no row
    // repeating the action its heading names.
    const v = loadViewer(twoClaimsAtOneTarget());
    v.setClaimGrouping("mechanism");
    try {
      const html = v.showTarget(v.lookupTarget("CHEMBLT1"));
      assert.match(html, /data-claim-group="mechanism" aria-pressed="true"/);
      assert.match(html, /data-fold="target_claims_mech_ANTAGONIST">[\s\S]*?Antagonist<[\s\S]*? \(1\)/);
      assert.match(html, /data-fold="target_claims_measured_binding">[\s\S]*?Binding<[\s\S]*? \(2\)/);
      assert.ok(html.indexOf("target_claims_mech_ANTAGONIST") <
                html.indexOf("target_claims_measured_binding"));
      assert.ok(!/target_claims_supported/.test(html));
      const antagonist = html.slice(html.indexOf("target_claims_mech_ANTAGONIST"),
                                    html.indexOf("target_claims_measured_binding"));
      assert.ok(!/ANTAGONIST<\/div>|· ANTAGONIST/.test(antagonist), "the row repeats its heading");
    } finally {
      v.setClaimGrouping("tier");
    }
  });

  test("a target panel folds its sections apart from a molecule panel's", () => {
    const v = loadViewer(twoClaimsAtOneTarget());
    v.setSectionOpen("claims_supported", true);
    const html = v.showTarget(v.lookupTarget("CHEMBLT1"));
    assert.match(html, /<details class="section"><summary class="section-toggle" data-fold="target_claims_supported">/);
  });

  test("a molecule's claims are listed together", () => {
    const v = loadViewer(twoClaimsAtOneTarget());
    const html = v.showTarget(v.lookupTarget("CHEMBLT1"));
    const ids = [...html.matchAll(/data-select="edge" data-id="(\d+)"/g)]
      .map((m) => Number(m[1]));
    // A repeated name reads as one molecule with two claims rather than as two
    // entries, so its rows are adjacent.
    assert.deepEqual(plain(ids), [1, 1, 2]);
  });

  test("the count says nothing extra when every molecule has one claim", () => {
    const v = loadViewer(catalogue());
    v.setFilter("basis", "human_direct");
    const html = v.showTarget(v.lookupTarget("CHEMBLT1"));
    assert.match(html, /class="small target-molecules">[^\n]*?2 molecules<span class="help-text">[^<]*<\/span><\/span><\/div>/);
    assert.ok(!/· 2 claims/.test(html));
    assert.ok(!/<\/span> \(\d+\) <span class="muted">· \d+ molecules?<\/span><\/summary>/.test(html));
  });
});

describe("source text is escaped wherever it reaches innerHTML", () => {
  const nasty = '<img src=x onerror="alert(1)">';

  test("esc neutralises markup", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.esc(nasty),
      "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  });

  test("a hostile target name cannot reach the panel as markup", () => {
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "T1", name: nasty })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" })],
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1)) + v.showTarget(v.lookupTarget("T1"));
    assert.ok(!html.includes("<img"));
    assert.match(html, /&lt;img/);
  });

  test("a hostile assay description and paper title are escaped", () => {
    const v = loadViewer(catalogue());
    const html = v.observationRowHTML(
      observation({ assay_description: nasty }),
      [study({ title: nasty })]);
    assert.ok(!html.includes("<img"));
  });

  test("search highlighting escapes each slice rather than the whole string", () => {
    const v = loadViewer(catalogue());
    const out = v.highlightMatch("a&b caffeine", "caffeine");
    assert.match(out, /a&amp;b/);
    assert.match(out, /<mark>caffeine<\/mark>/);
  });

  test("only http and https links are built", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.safeUrl("javascript:alert(1)"), null);
    assert.equal(v.safeUrl("data:text/html,<script>"), null);
    assert.ok(v.safeUrl("https://example.org/x"));
    assert.match(v.link("javascript:alert(1)", "x"), /^<span class="v">x<\/span>$/);
  });

  test("external links are built from identifiers, never from a name", () => {
    const v = loadViewer(catalogue());
    const links = v.externalLinks("molecule", v.lookupMolecule(1)).join(" ");
    assert.match(links, /compound_report_card\/CHEMBL113/);
    const t = v.lookupTarget("CHEMBLT1");
    assert.match(v.externalLinks("target", t).join(" "), /target_report_card\/CHEMBLT1/);
  });
});

describe("the panel says what it is counting", () => {
  test("measurements, studies and databases are never one number", () => {
    const v = loadViewer(catalogue());
    const html = v.claimBlockHTML(v.allClaims().find((c) => c.id === 1), null);
    assert.match(html, /Measurements \(exact\)/);
    assert.match(html, /across all endpoint classes/);
    assert.match(html, /publication-class/);
  });

  test("the endpoint class that earned the tier is the one marked", () => {
    // Caffeine's ADORA1 claim is Supported at Ki across 11 publications and
    // also carries a single IC50 at a lower value. The mark goes on the class
    // that earned the tier, not on the strongest number.
    const v = loadViewer(catalogue());
    const html = v.claimBlockHTML(v.allClaims().find((c) => c.id === 1), null);
    assert.match(html, /binding:Ki<\/b> <span class="pill supported">supported here/);
    assert.ok(!/binding:IC50<\/b> <span class="pill supported">/.test(html));
    // And the stronger value is still shown, named as the endpoint it is.
    assert.match(html, /strongest value[\s\S]*binding:IC50/);
  });

  test("a Supported pill is not repeated as a reason underneath itself", () => {
    // "Supported · multiple studies" over "Replicated across publications" is
    // one fact wearing two labels (invariant 13). The tiers whose pill names
    // only the tier are the ones that still need the rule spelled out.
    const v = loadViewer(catalogue());
    const supported = v.claimBlockHTML(v.allClaims().find((c) => c.id === 1), null);
    assert.ok(!/Why this tier/.test(supported));
    const preliminary = v.claimBlockHTML(v.allClaims().find((c) => c.id === 3), null);
    assert.match(preliminary, /Why this tier/);
    assert.match(preliminary, /One publication/);
  });

  test("the panel does not say why an entry is in the catalogue", () => {
    // It was one line under the identity table naming the admission route and
    // the seed status (2026-09-26); it is gone (2026-09-27, at the user's
    // request), because the rule that admitted an entry is about this project
    // rather than about the drug.
    const v = loadViewer(catalogue());
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.ok(!/class="membership/.test(html));
    assert.ok(!/In the catalogue by/.test(html));
    assert.ok(!/ATC N and a qualifying indication/.test(html));
    assert.ok(!/seed molecule/.test(html));
  });

  test("the indications are their own section, below the pharmacology", () => {
    // What a drug is used for and how far it has got is a fact about the drug,
    // useful to a reader who does not care why the entry is in the catalogue.
    const v = loadViewer(catalogue());
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /data-fold="indications">.*Indications/);
    // Pharmacology first: the section sits below the claims and the ranking.
    assert.ok(html.indexOf('data-fold="claims_supported"') <
              html.indexOf('data-fold="indications"'));
    assert.ok(html.indexOf('data-fold="similar"') <
              html.indexOf('data-fold="indications"'));
  });

  test("the retained claims close the molecule panel, under their own name", () => {
    // They back no line, and sat between the drawn claims and the ranking as a
    // detour (2026-09-25, at the user's request). Last, after the indications.
    const data = catalogue();
    const v = loadViewer(data);
    const mol = v.lookupMolecule(1);
    mol.n_claims_limited = 2;
    const html = v.showMolecule(mol);
    // Headed as the claims they are, not as observations (2026-09-25).
    assert.ok(!/Retained observations/.test(html));
    const retained = html.indexOf("Retained claims");
    assert.ok(retained > 0);
    assert.ok(html.indexOf('data-fold="indications"') < retained);
    assert.ok(html.indexOf('data-fold="similar"') < retained);
  });

  test("the retained claims start folded, like the other long sections", () => {
    const v = loadViewer(catalogue());
    const mol = v.lookupMolecule(1);
    mol.n_claims_limited = 2;
    const html = v.showMolecule(mol);
    assert.match(html, /<details class="section"><summary class="section-toggle" data-fold="retained_link">/);
  });

  test("a claim row names the species of its target", () => {
    const v = loadViewer(catalogue());
    const claim = v.allClaims().find((c) => c.id === 1);
    const t = v.lookupTarget(claim.target);
    assert.ok(t.organism, "the fixture target carries an organism");
    const row = v.claimRowHTML(claim);
    assert.ok(row.includes(" · " + t.organism + "</div>"), row);
  });

  test("claims can be grouped by curated mechanism instead of by tier", () => {
    // One group per exact ChEMBL action, and the measured claims - which carry
    // no direction however well replicated - after them, grouped by role.
    // It is panel state and not a filter: the same claims, the same rows.
    const v = loadViewer(catalogue());
    const mol = v.lookupMolecule(1);
    const byTier = v.showMolecule(mol);
    assert.match(byTier, /data-claim-group="tier" aria-pressed="true"/);
    assert.match(byTier, /data-fold="claims_supported"/);
    assert.ok(!/claims_mech_/.test(byTier));

    assert.equal(v.setClaimGrouping("mechanism"), "mechanism");
    const byMech = v.showMolecule(mol);
    assert.match(byMech, /data-claim-group="mechanism" aria-pressed="true"/);
    assert.ok(!/data-fold="claims_supported"/.test(byMech));
    const antagonist = byMech.indexOf('data-fold="claims_mech_ANTAGONIST"');
    const none = byMech.indexOf('data-fold="claims_measured_binding"');
    assert.ok(antagonist > 0 && none > antagonist, "the measured claims come last");
    const heading = (at) => byMech.slice(at, byMech.indexOf("</summary>", at));
    assert.match(heading(antagonist), /tabindex="0">Antagonist<[\s\S]* \(1\)$/);
    assert.match(heading(none),
      /tabindex="0">Binding<[\s\S]* \(2\) <span class="muted">· measured affinity, no direction<\/span>$/);
    assert.ok(!/No curated mechanism/.test(byMech));
    // Under the Antagonist heading the row does not say ANTAGONIST again.
    const antBody = byMech.slice(antagonist, none);
    assert.ok(!/ANTAGONIST/.test(antBody.slice(antBody.indexOf("</summary>"))));
    // Every claim row is still there, once.
    const rows = (html) => (html.match(/class="row-item" data-select="edge"/g) || []).length;
    assert.equal(rows(byMech), rows(byTier));
    for (const key of ["claim_grouping", "claim_mechanism", "claim_binding",
                       "claim_functional", "claim_curated_none"]) {
      assert.match(v.helpLabel("x", key), /help-text/, key);
    }
    v.setClaimGrouping("tier");
  });

  test("a measured claim is grouped by role, never under 'no curated mechanism'", () => {
    // 2026-09-25, at the user's request. Armodafinil has a curated INHIBITOR
    // claim at human DAT and a measured Ki claim at the same target; one group
    // headed "No curated mechanism" read as a statement about the pair and
    // contradicted the group above it. The measured claims are now Binding and
    // Functional, as on the edge panel, and a curated claim with no action has
    // a group of its own rather than being filed as a measurement.
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "DAT" }), target({ chembl_id: "NET" })],
      claims: [
        claim({ id: 1, molecule: 1, target: "DAT", role: "curated",
                tier_reason: "curated_support", curated_support: 1,
                multiple_study_support: 0, action_type: "INHIBITOR",
                n_measurements: 0, n_studies: 0, supporting_endpoint_class: null,
                endpoints: [] }),
        claim({ id: 2, molecule: 1, target: "DAT", role: "binding" }),
        claim({ id: 3, molecule: 1, target: "NET", role: "functional" }),
        claim({ id: 4, molecule: 1, target: "NET", role: "curated",
                tier_reason: "curated_support", curated_support: 1,
                multiple_study_support: 0, action_type: null,
                n_measurements: 0, n_studies: 0, supporting_endpoint_class: null,
                endpoints: [] }),
      ],
    }));
    v.setClaimGrouping("mechanism");
    const h = v.showMolecule(v.lookupMolecule(1));
    v.setClaimGrouping("tier");
    const at = (k) => h.indexOf('data-fold="' + k + '"');
    assert.ok(at("claims_mech_INHIBITOR") > 0);
    assert.ok(at("claims_mech_INHIBITOR") < at("claims_curated_none"));
    assert.ok(at("claims_curated_none") < at("claims_measured_binding"));
    assert.ok(at("claims_measured_binding") < at("claims_measured_functional"));
    assert.match(h, /tabindex="0">Curated<[^]*?\(1\) <span class="muted">· no direction recorded/);
    assert.match(h, /tabindex="0">Functional<[^]*?\(1\) <span class="muted">· measured activity, no direction/);
    assert.ok(!/No curated mechanism/.test(h));
    // Each group holds one row, and the binding row does not repeat its role.
    const body = h.slice(at("claims_measured_binding"), at("claims_measured_functional"));
    assert.equal((body.match(/class="row-item" data-select="edge"/g) || []).length, 1);
    assert.match(body, /<div class="small muted">binding:Ki median/);
    assert.ok(!/<div class="small muted">binding ·/.test(body));
  });

  test("an indication links the trials its phase is an annotation of", () => {
    // "Phase 3" on its own is this page asserting a development stage with no
    // way to check it. The link is built from the NCT identifier, never a
    // search by name (invariant 15), and folds above one because a disease can
    // carry 200 registrations.
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [
        ["D1", "Alone", "Phase 3", "core", 1, "NCT00000001"],
        ["D2", "Several", "Phase 3", "core", 1, "NCT00000002|NCT00000003"],
        ["D3", "Unregistered", "Approved", "core", 1, null],
      ] },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /href="https:\/\/clinicaltrials\.gov\/study\/NCT00000001"/);
    assert.match(html, /<summary>2 trials: 2 status not fetched<\/summary>/);
    assert.ok(!/1 trial:/.test(html), "a single trial is linked, not folded");
    // Why a condition has no link is in the section's hover rather than a
    // count in the note, and the row itself is never marked as untrialled.
    assert.match(html, /No trial link usually means a drug label/);
  });

  test("a trial says whether it is ongoing, completed or stopped early", () => {
    // ClinicalTrials.gov's status, from resolve_cohort_trials.py. The folded
    // summary carries the tally so how the trials went is readable without
    // opening it, and a stopped trial carries the sponsor's own reason.
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [
        ["D1", "Alone", "Phase 2", "core", 0, "NCT00000001"],
        ["D2", "Several", "Phase 3", "core", 1,
         "NCT00000002|NCT00000003|NCT00000004|NCT00000005"],
      ] },
      trial_status: {
        NCT00000001: ["TERMINATED", "Lack of efficacy <b>"],
        NCT00000002: ["COMPLETED"],
        NCT00000003: ["RECRUITING"],
        NCT00000004: ["WITHDRAWN", "Sponsor decision"],
      },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /NCT00000001<\/a> <span class="trial-status stopped">stopped early<\/span>/);
    assert.match(html, /Lack of efficacy &lt;b&gt;/, "the registry's text is escaped");
    assert.match(html, /<summary>4 trials: 1 ongoing, 1 completed, 1 stopped early, 1 status not fetched<\/summary>/);
    assert.match(html, /withdrawn before enrolling/);
    // Completed is never presented as success.
    assert.match(html, /completed means finished, not successful/);
  });

  test("each trial says its own phase and what it reported on its main goal", () => {
    // The phase on a disease row is the furthest any trial reached, and the
    // list under it mixes in phase 1 and 2 studies, so every trial says its
    // own. A main-goal result is shown only as the sponsor reported it.
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [["D1", "Epilepsy", "Phase 3", "core", 1,
        "NCT00000001|NCT00000002|NCT00000003|NCT00000004"]] },
      trial_status: {
        NCT00000001: ["COMPLETED", null, "PHASE2", null],
        NCT00000002: ["COMPLETED", null, "PHASE2|PHASE3",
                      [["Seizure <rate>", ["<0.0001"]]]],
        NCT00000003: ["TERMINATED", "Futility", "PHASE3", [["Relapse", []]]],
        NCT00000004: ["RECRUITING"],
      },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<summary>4 trials, 2 at phase 3\+: /);
    assert.match(html, /NCT00000002<\/a> <span class="muted">phase 2\/3<\/span>/);
    assert.match(html, /Seizure &lt;rate&gt;: p &lt; 0.0001/);
    assert.match(html, /NCT00000001<\/a> <span class="muted">phase 2<\/span>[^]*?no results posted/);
    assert.match(html, /results posted<\/a>, no test of the main goal</);
    // Highest phase first; an unfetched trial sorts last and claims nothing.
    const order = [...new Set([...html.matchAll(/study\/(NCT\d+)/g)].map((m) => m[1]))];
    assert.deepEqual(plain(order), ["NCT00000002", "NCT00000003", "NCT00000001", "NCT00000004"]);
    assert.ok(!/NCT00000004<\/a>[^<]*<span class="muted">phase/.test(html));
  });

  test("each trial says when it ran, and a date the registry only plans says so", () => {
    // A phase 2 completed in 2005 under a disease still short of Approved is
    // a different fact from one still recruiting. An estimated end is said to
    // be planned: on a trial whose status is UNKNOWN it is usually long past,
    // and printed bare it would read as the year the trial ended.
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [["D1", "Epilepsy", "Phase 3", "core", 0,
        "NCT00000001|NCT00000002|NCT00000003|NCT00000004|NCT00000005|NCT00000006"]] },
      trial_status: {
        NCT00000001: ["COMPLETED", null, "PHASE2", null, 2001, 2005],
        NCT00000002: ["UNKNOWN", null, "PHASE3", null, 2009, 2012, 2],
        NCT00000003: ["NOT_YET_RECRUITING", null, "PHASE2", null, 2027, 2029, 3],
        NCT00000004: ["COMPLETED", null, "PHASE1", null, 2005, 2005],
        NCT00000005: ["COMPLETED", null, null, null, null, 1999],
        NCT00000006: ["RECRUITING"],
      },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /NCT00000001<\/a> <span class="muted">phase 2, 2001–2005<\/span>/);
    assert.match(html, /NCT00000002<\/a> <span class="muted">phase 3, started 2009, planned to end 2012<\/span>/);
    assert.match(html, /NCT00000003<\/a> <span class="muted">phase 2, planned 2027–2029<\/span>/);
    assert.match(html, /NCT00000004<\/a> <span class="muted">phase 1, 2005<\/span>/);
    assert.match(html, /NCT00000005<\/a> <span class="muted">ended 1999<\/span>/);
    // A row fetched before the dates were asked for claims no year.
    assert.match(html, /NCT00000006<\/a> <span class="trial-status/);
    // The folded summary spans only what happened: 1999 to 2009, not to the
    // planned 2012 or 2029.
    assert.match(html, /<summary>6 trials, 1999–2009, 1 at phase 3\+: /);
    // Within a phase the latest first, by end year (planned or not); undated last.
    const order = [...new Set([...html.matchAll(/study\/(NCT\d+)/g)].map((m) => m[1]))];
    assert.deepEqual(plain(order), ["NCT00000002", "NCT00000003", "NCT00000001",
                                    "NCT00000004", "NCT00000005", "NCT00000006"]);
  });

  test("a long main goal is cut short, with one p-value and the rest counted", () => {
    const long = "Change From Baseline in the Positive and Negative Syndrome Scale Total Score at Week 6";
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [["D1", "Schizophrenia", "Phase 3", "core", 1, "NCT00000001"]] },
      trial_status: {
        NCT00000001: ["COMPLETED", null, "PHASE3",
                      [[long, ["0.004", "0.3", "<0.001"]], ["Second goal", ["0.02"]]]],
      },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /title="Change From Baseline[^"]*Week 6"/, "the full title is the hover");
    assert.match(html, /Negative Syndrome…<\/span>: p = 0.004 <span class="muted">\(\+2 more\)<\/span>/);
    assert.match(html, /\+1 more goal/);
    assert.doesNotMatch(html, /Second goal/);
  });

  test("one disease is one row, at the furthest phase any record reached", () => {
    // ChEMBL files a drug_indication per form of the molecule and the forms
    // fold onto one parent, so caffeine carries Pain twice - Approved against
    // CHEMBL113 and Phase 2 against a salt. 682 of the 5,939 diseases here are
    // assembled from more than one record and 115 of those straddle the
    // qualifying line. Listing them separately would show one indication as
    // two, and the trials behind them are pooled rather than split.
    const data = buildData({
      molecules: [molecule({ id: 1 })],
      indications: { 1: [
        ["D1", "Pain", "Approved", "core", 1, "NCT00000001"],
        ["D1", "Pain", "Phase 2", "core", 0, "NCT00000002"],
      ] },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<\/span> \(1\)</, "two records read as two diseases");
    assert.ok(!/Phase 2/.test(html), "the lower phase is shown as a second row");
    assert.match(html, /2 ChEMBL records, furthest phase shown/);
    assert.match(html, /<summary>2 trials: /);
  });

  test("the panel says how far the molecule itself has got", () => {
    // 296 of the 1,331 entries stop at phase 3 - trialled that far and approved
    // for nothing, which is a different thing from an approved drug being
    // trialled for something new, and the two used to read identically.
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, max_phase: 3, first_approval: null })],
    }));
    assert.match(v.showMolecule(v.lookupMolecule(1)),
                 /reached phase 3, not approved for any disease/);
    const v2 = loadViewer(buildData({
      molecules: [molecule({ id: 2, max_phase: 4, first_approval: 1948 })],
    }));
    assert.match(v2.showMolecule(v2.lookupMolecule(2)), /approved, first in 1948/);
  });

  test("a phase ChEMBL files no disease under says it cites nothing for it", () => {
    // Cyclazodone is phase 2 in ChEMBL 37 with no drug_indication row, and its
    // only source is the INN list: "reached phase 2" asserted a trial nothing
    // cites (2026-10-17).
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, max_phase: 2, n_indications_chembl: 0 })],
    }));
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /ChEMBL records phase 2 but cites no trial or disease for it/);
    assert.ok(!/reached phase 2/.test(html));
    // A molecule with diseases, none of them listed here, keeps "reached".
    const v2 = loadViewer(buildData({
      molecules: [molecule({ id: 2, max_phase: 3, n_indications_chembl: 4 })],
    }));
    assert.match(v2.showMolecule(v2.lookupMolecule(2)),
                 /reached phase 3, not approved for any disease/);
    // An approval with no condition keeps its own line (2026-09-27).
    const v3 = loadViewer(buildData({
      molecules: [molecule({ id: 3, max_phase: 4, n_indications_chembl: 0 })],
    }));
    assert.match(v3.showMolecule(v3.lookupMolecule(3)),
                 /ChEMBL names no condition it is approved for/);
  });

  test("the claim and similarity sections fold, and fold with their counts on them", () => {
    // The heading becomes the summary rather than sitting above one, so a
    // folded section is the h2 the panel already had with a triangle on it -
    // and it keeps the count, because a section that hid how many rows it held
    // would be hiding rather than folding.
    const v = loadViewer(catalogue());
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<summary class="section-toggle" data-fold="claims_supported">/);
    assert.match(html, /<summary class="section-toggle" data-fold="similar">/);
    const heading = html.slice(html.indexOf('data-fold="claims_supported"'));
    assert.match(heading.slice(0, heading.indexOf("</summary>")), /\(2\)/);
    // Both start folded, so a panel opens as a list of headings with counts
    // rather than several screens of rows the reader has not asked for.
    assert.match(html, /<details class="section"><summary class="section-toggle" data-fold="claims_supported">/);
    assert.match(html, /<details class="section"><summary class="section-toggle" data-fold="similar">/);
  });

  test("the similarity list draws every row its heading counts", () => {
    // It used to draw the first 25 under a heading counting the whole list.
    // 304 of the 1,331 entries have more than 25 neighbours - haloperidol has
    // 180 under the default filters and pimozide 670 with all of them open -
    // so that was a count and a list disagreeing on a quarter of the
    // catalogue, in the section that answers this page's own question.
    const mols = [], claims = [];
    for (let i = 1; i <= 30; i++) {
      mols.push(molecule({ id: i, chembl_id: "CHEMBL" + i, name: "MOL " + i }));
      claims.push(claim({ id: i, molecule: i, target: "CHEMBLT1" }));
    }
    const v = loadViewer(buildData({
      molecules: mols, targets: [target({ chembl_id: "CHEMBLT1" })], claims,
    }));
    const html = v.showMolecule(v.lookupMolecule(1));
    const heading = html.slice(html.indexOf('data-fold="similar"'));
    assert.match(heading.slice(0, heading.indexOf("</summary>")), /\(29\)/);
    assert.equal((html.match(/data-select="pair"/g) || []).length, 29);
  });

  test("a folded section is still folded after the panel is rebuilt", () => {
    // Every filter change re-renders the panel, so a fold kept only in the DOM
    // would spring open on the next click of a control - which reads as the
    // fold not having worked.
    const v = loadViewer(catalogue());
    v.setSectionOpen("similar", false);
    v.setSectionOpen("claims_supported", true);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<details class="section"><summary class="section-toggle" data-fold="similar">/);
    assert.match(html, /<details class="section" open><summary class="section-toggle" data-fold="claims_supported">/);
    v.setSectionOpen("similar", true);
    v.setSectionOpen("claims_supported", false);
  });

  test("a click on a section heading records where the fold landed", () => {
    // The browser toggles the <details> as the click's default action, so the
    // element still holds its pre-click state when the handler reads it.
    const v = loadViewer(catalogue());
    const details = { open: true };
    const summary = { parentNode: details, getAttribute: () => "similar" };
    v.onAppClick({ target: { closest: (sel) => (sel === "summary[data-fold]" ? summary : null) } });
    assert.equal(v.sectionOpen("similar", true), false);
    details.open = false;
    v.onAppClick({ target: { closest: (sel) => (sel === "summary[data-fold]" ? summary : null) } });
    assert.equal(v.sectionOpen("similar", true), true);
  });

  test("an indication says its disease and phase and not the policy token it fell under", () => {
    // core / general_pain / neuropathic name the part of the adopted selection
    // scope a disease landed in. That is a fact about the rule rather than
    // about the drug, it repeated on every row, and it is gone from the panel.
    const v = loadViewer(catalogue());
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /Pain/);
    assert.match(html, /Phase 3/);
    assert.ok(!/general_pain/.test(html), "the scope token is still printed");
    assert.ok(!/Indication scope/.test(html));
  });

  test("every indication is listed, the near misses among them", () => {
    // The list used to print six and then "8 more" - a count with no way to
    // reach what it counted - and to drop the ones that did not qualify. Both
    // were about membership: a phase-2 indication is a fact about the drug, and
    // it is exactly what "in trials, not approved for this" looks like. The
    // section folds instead, which is how every long list here is made bearable.
    const rows = [];
    for (let i = 1; i <= 14; i++) {
      rows.push(["D" + i, "Disease " + i, "Phase 3", "core", 1, null]);
    }
    rows.push(["D99", "Below the line", "Phase 2", "core", 0, null]);
    const data = buildData({
      molecules: [molecule({ id: 1, route_indication: 1, n_indications_chembl: 20 })],
      indications: { 1: rows },
    });
    const v = loadViewer(data);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<\/span> \(15\)</);
    for (let i = 1; i <= 14; i++) assert.match(html, new RegExp(">Disease " + i + "</a>"));
    assert.match(html, /Below the line/, "a near miss is dropped rather than shown");
    assert.ok(!/more indications/.test(html), "the list is still capped");
    // What share of the record is shown, said once.
    assert.match(html, /Neurological and pain conditions only: 15 of ChEMBL's 20\./);
  });

  test("a target panel lists its components and says on hover they are not claims", () => {
    // The "Context only ..." note under the heading is gone (2026-09-26, at the
    // user's request); the one sentence that matters is the heading's hover.
    const data = buildData({
      targets: [target({ chembl_id: "T1", target_type: "PROTEIN COMPLEX",
                         n_components: 2,
                         components: [{ accession: "P1", gene_symbol: "G1" },
                                      { accession: "P2", gene_symbol: "G2" }] })],
    });
    const v = loadViewer(data);
    const html = v.showTarget(v.lookupTarget("T1"));
    assert.ok(!/Context only/.test(html));
    assert.match(html, /never passed on to them/);
    assert.match(html, />G1 </);
  });

  test("an explanation opens on hover or on keyboard focus, never on a click", () => {
    // .help carries tabindex="0" so the keyboard can reach it, and a click
    // focuses it too - so under :focus the box opened on the click and stayed
    // open over whatever was beneath it until something else was clicked. The
    // headings that fold a section made it plain, because there clicking the
    // label is also how the control is worked.
    const css = viewerHtml();
    assert.match(css, /\.help:hover \.help-text, \.help:focus-visible \.help-text \{ display: block; \}/);
    assert.ok(!/\.help:focus \.help-text/.test(css), "an explanation still opens on :focus");
  });

  test("an explanation closes when the pointer leaves the label for the box", () => {
    // .help-text is a child of .help, so without this the pointer resting on
    // the open box still counted as hovering the label, and the box stayed
    // open over the panel it covered.
    const css = viewerHtml();
    assert.match(css, /\.help-text \{[^}]*pointer-events: none;/);
  });

  test("every heading that opens an explanation sits in a positioned element", () => {
    // .help-text is absolutely positioned against its nearest positioned
    // ancestor; a heading that is not one anchors the box to the viewport and
    // opens it below the fold, which reads as the explanation being missing.
    const css = viewerHtml();
    assert.match(css, /h2,\s*\.ctl h4,\s*\.row-item \{ position: relative; \}/);
  });
});

describe("banners state the cost of every control that hides something", () => {
  test("a cost and an inclusion are not the same statement", () => {
    // Both open defaults push a banner, because a reader looking at Preliminary
    // claims and nonhuman assignments has to be told so. Neither is a *cost* -
    // nothing is hidden at rest - and the folded summary counts costs. Before
    // this distinction existed the resting page read "Display options - 2
    // stating a cost" while hiding nothing at all, which is two quantities
    // under one label.
    const v = loadViewer(catalogue());
    const atRest = v.filterBanners();
    assert.ok(atRest.length, "the open defaults still say what they are showing");
    assert.equal(atRest.filter((b) => b.kind === "cost").length, 0,
      "nothing is hidden at the defaults, so nothing is a cost");
    assert.equal(v.viewOptionsSummary(), "Display options");

    // Narrow one control and exactly that one reports a cost.
    v.setFilter("tier", "supported");
    const narrowed = v.filterBanners();
    const costs = narrowed.filter((b) => b.kind === "cost");
    assert.equal(costs.length, 1);
    assert.equal(costs[0].control, "tier");
    assert.equal(v.viewOptionsSummary(), "Display options · 1 hiding");
  });

  test("the tier banner counts what it hid", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    assert.match(v.filterBanners().map((b) => b.text).join(" "), /1 Preliminary claim is hidden/);
  });

  test("the broader layer says it is included and how it is counted", () => {
    // The banner used to read "Broader assignment layer is on", which was right
    // while the layer was something a reader switched on. It is the default
    // now, so the wording says what is being shown rather than what was done to
    // the control - and still says the thing that must not be lost, which is
    // that the two layers are counted apart.
    const v = loadViewer(catalogue());
    v.setFilter("basis", "all");
    const banner = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banner, /Including the <b>broader assignment<\/b> layer/);
    assert.match(banner, /never pooled with direct human results/);
  });

  test("the button counts what is hidden and its tooltip names every setting", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    // The button says only how many controls are hiding something - the
    // settings list squeezed the search box in a narrow window - and the list
    // is its tooltip. Two here: the tier control hiding a Preliminary claim,
    // and the basis control hiding the broader layer.
    assert.equal(v.viewOptionsSummary(), "Display options · 2 hiding");
    assert.equal(v.viewOptionsSettings(),
      "Supported only · direct human · " +
      "no potency cutoff · every mechanism · every target drawn · " +
      "protein groups linked · lines coloured by mechanism");
    v.renderControls();
    assert.equal(v.document.getElementById("view-options-summary").textContent,
      "Display options · 2 hiding");
    // Nothing hidden, nothing claimed: a page with no cost says so by saying
    // nothing, rather than printing a zero.
    const quiet = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "T" })],
      claims: [claim({ id: 1, molecule: 1, target: "T" })],
    }));
    quiet.setFilter("tier", "supported");
    quiet.setFilter("basis", "human_direct");
    assert.equal(quiet.viewOptionsSummary(), "Display options");
    v.setFilter("potency", 10);
    v.setFilter("basis", "all");
    assert.match(v.viewOptionsSettings(), /including broader assignment · potency ≤ 10 µM/);
    // Folding the controls away must never hide a changed one, and the canvas
    // control is a setting like the other three.
    v.setFilter("periphery", "hide");
    assert.match(v.viewOptionsSettings(), /single-molecule targets hidden/);
    v.toggleMechanism("ANTAGONIST");
    v.setFilter("lineColor", "evidence");
    assert.match(v.viewOptionsSettings(), /lines coloured by evidence/);
    v.setFilter("lineColor", "mechanism");
    assert.match(v.viewOptionsSettings(), /antagonist only/);
    assert.match(v.viewOptionsSettings(), /lines coloured by mechanism/);
  });
});

// Two molecules, two different curated actions, one measured claim with none.
// Small enough that every count below can be read off it.
function mechanismCatalogue() {
  return buildData({
    molecules: [molecule({ id: 1, name: "ANTA" }), molecule({ id: 2, name: "AGO" }),
                molecule({ id: 3, name: "MEASURED" })],
    targets: [target({ chembl_id: "T1", name: "Target one" })],
    claims: [
      claim({ id: 1, molecule: 1, target: "T1", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: "ANTAGONIST",
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
      claim({ id: 2, molecule: 2, target: "T1", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: "AGONIST",
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
      claim({ id: 3, molecule: 3, target: "T1" }),
    ],
  });
}

describe("the curated mechanism is a first-class thing to filter on", () => {
  test("choosing an action leaves only the claims annotated with it", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    assert.equal(v.catalogueGraph().edges.length, 4);
    v.toggleMechanism("ANTAGONIST");
    const claims = v.catalogueGraph().edges.flatMap((e) => e.claims);
    assert.equal(claims.length, 2);
    for (const c of claims) assert.equal(c.action_type, "ANTAGONIST");
  });

  test("several actions can be on at once, and they compose", () => {
    // The question a reader has is usually about a group of related
    // directions, and those are separate actions in ChEMBL on purpose. One at
    // a time would push them toward the direction families this control
    // refuses to define for them.
    const v = loadViewer(mechanismCatalogue());
    assert.equal(v.catalogueGraph().edges.length, 3);
    v.toggleMechanism("ANTAGONIST");
    assert.equal(v.catalogueGraph().edges.length, 1);
    v.toggleMechanism("AGONIST");
    const actions = v.catalogueGraph().edges.flatMap((e) => e.claims)
      .map((c) => c.action_type).sort();
    assert.deepEqual(plain(actions), ["AGONIST", "ANTAGONIST"]);
    // And picking one back off leaves the other in place.
    v.toggleMechanism("ANTAGONIST");
    assert.deepEqual(plain(v.getFilters().mechanism), ["AGONIST"]);
    assert.equal(v.mechanismSummary(), "agonist only");
  });

  test("the two whole-annotation answers are tokens like any other", () => {
    const v = loadViewer(mechanismCatalogue());
    v.toggleMechanism("curated");
    assert.equal(v.catalogueGraph().edges.length, 2);
    v.toggleMechanism("uncurated");
    assert.equal(v.catalogueGraph().edges.length, 3);
    assert.equal(v.mechanismSummary(),
                 "any curated mechanism or no curated mechanism only");
  });

  test("taking every action back off is every claim, not an empty canvas", () => {
    const v = loadViewer(catalogue());
    const all = v.catalogueGraph().edges.length;
    v.toggleMechanism("ANTAGONIST");
    assert.notEqual(v.catalogueGraph().edges.length, all);
    v.toggleMechanism("ANTAGONIST");
    assert.equal(v.catalogueGraph().edges.length, all);
    assert.equal(v.mechanismSummary(), "every mechanism");
  });

  test("it is an eligibility filter, so every view moves with it", () => {
    // The panel lists, the similarity ranking and the canvas read one rule.
    // A mechanism control that changed only the picture would be a second
    // answer to what is on screen.
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    assert.equal(v.sharedTargets(1).length, 1);
    assert.equal(v.visibleClaimsFor(1).length, 2);
    v.toggleMechanism("AGONIST");
    assert.equal(v.visibleClaimsFor(1).length, 0);
    assert.equal(v.sharedTargets(1).length, 0);
    assert.equal(v.catalogueGraph().edges.length, 0);
  });

  test("an unannotated claim is hidden as unannotated, not as a different action", () => {
    // The two absences are different statements and the reason code keeps them
    // apart: ChEMBL having curated another direction is a claim about the
    // molecule, and ChEMBL having curated nothing is not.
    const v = loadViewer(mechanismCatalogue());
    v.toggleMechanism("ANTAGONIST");
    const byId = (id) => v.allClaims().find((c) => c.id === id);
    assert.equal(v.hiddenReason(byId(3)), "mechanism_none");
    assert.equal(v.hiddenReason(byId(1)), null);
    assert.equal(v.hiddenReason(byId(2)), "mechanism");
  });

  test("the banner counts the two costs separately and says what silence means", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    v.toggleMechanism("ANTAGONIST");
    const banner = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banner, /<b>antagonist<\/b> only/);
    assert.match(banner, /2 claims with no curated action at all/);
    assert.match(banner, /not that the molecule does not act this way/);
    // Two tokens are named, not summed into one word.
    v.toggleMechanism("AGONIST");
    assert.match(v.filterBanners().map((b) => b.text).join(" "), /antagonist or agonist/);
  });

  test("the control offers the actions this build holds, with what each would draw", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    const counts = v.actionCounts();
    assert.deepEqual(plain(counts.rows), [{ action: "ANTAGONIST", n: 2 }]);
    assert.equal(counts.curated, 2);
    assert.equal(counts.uncurated, 2);
    const html = v.filtersHTML();
    assert.match(html, /data-filter="mechanism" data-value="ANTAGONIST"[^>]*>antagonist \(2\)</);
    // Counted under the other three controls, so the number beside an action
    // is what picking it would actually put on screen.
    v.setFilter("tier", "supported_preliminary");
    assert.equal(v.actionCounts().uncurated, 3);
  });

  test("an action the other controls have emptied stays on the control", () => {
    // Otherwise it disappears from the popover while still filtering, which is
    // the one way this could narrow the catalogue with nothing saying so.
    const v = loadViewer(catalogue());
    v.toggleMechanism("ANTAGONIST");
    v.setFilter("potency", 1);
    assert.equal(v.actionCounts().rows.length, 0);
    assert.match(v.filtersHTML(),
                 /data-value="ANTAGONIST"[^>]*aria-pressed="true"[^>]*>antagonist \(0\)</);
  });

  test("reset puts both mechanism controls back", () => {
    const v = loadViewer(catalogue());
    v.toggleMechanism("ANTAGONIST");
    v.setFilter("lineColor", "mechanism");
    v.setFilter("lineColor", "evidence");
    v.resetFilters();
    assert.deepEqual(plain(v.getFilters().mechanism), []);
    // Mechanism is the default colouring (2026-09-24), so reset returns to it.
    assert.equal(v.getFilters().lineColor, "mechanism");
  });
});

describe("line colour answers one question at a time", () => {
  test("switching it changes no claim's eligibility and no node's place", () => {
    const v = loadViewer(catalogue());
    const before = v.graphSignature();
    const edges = v.catalogueGraph().edges.length;
    v.setFilter("lineColor", "mechanism");
    // Same signature means the canvas is not rebuilt and the layout is not
    // re-solved: a repaint must not move the picture under the reader.
    assert.equal(v.graphSignature(), before);
    assert.equal(v.catalogueGraph().edges.length, edges);
  });

  test("the colour follows the curated action, and the dashes still follow the tier", () => {
    const v = loadViewer(catalogue());
    const g = v.catalogueGraph();
    const antagonist = g.edges.find((e) => v.edgeActions(e).length);
    const unannotated = g.edges.find((e) => !v.edgeActions(e).length);
    v.setFilter("lineColor", "mechanism");
    assert.equal(v.edgeColor(antagonist).color, v.actionColor("ANTAGONIST"));
    assert.equal(v.edgeColor(unannotated).color, v.actionColor(null));
    assert.notEqual(v.actionColor("ANTAGONIST"), v.actionColor(null));
    // The evidence did not stop being drawn: it moved to the channel that was
    // already carrying it.
    assert.equal(v.edgeStyle(antagonist).dashes, false);
  });

  test("an action with no colour of its own does not borrow another's", () => {
    // The legacy page did this twice - a new action_type fell through to some
    // named mechanism's colour and the legend said nothing.
    const v = loadViewer(catalogue());
    const fallback = v.actionColor("SOMETHING ENTIRELY NEW");
    for (const known of ["ANTAGONIST", "AGONIST", "INHIBITOR", "BLOCKER",
                         "POSITIVE ALLOSTERIC MODULATOR",
                         "NEGATIVE ALLOSTERIC MODULATOR"]) {
      assert.notEqual(v.actionColor(known), fallback);
    }
    assert.notEqual(fallback, v.actionColor(null));
  });

  test("the banner says how much of the canvas the colour cannot speak for", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.setFilter("basis", "human_direct");
    v.setFilter("lineColor", "mechanism");
    const banner = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(banner, /2 of 4 drawn edges have one/);
    assert.match(banner, /none curated, not no effect/);
  });
});

describe("a selection is drawn bold, not repainted", () => {
  // vis replaces a selected edge's colour with color.highlight and a selected
  // node's fill with color.highlight.background. Left at the defaults that took
  // the evidence colour off every line into the thing just clicked, and turned
  // a selected target from orange to pale blue - the canvas stopping saying
  // what it says at the one moment a reader is looking hardest.
  test("a selected edge keeps its own colour, in both line-colour modes", () => {
    const v = loadViewer(catalogue());
    for (const mode of ["evidence", "mechanism"]) {
      v.setFilter("lineColor", mode);
      for (const e of v.catalogueGraph().edges) {
        const c = v.edgeStyle(e).color;
        assert.equal(c.highlight, c.color, mode + " edge " + e.id);
      }
    }
  });

  test("the highlight colour survives the update a selection writes", () => {
    const v = loadViewer(catalogue());
    v.select("molecule", 1);
    const drawn = v.__networks[0].data.edges.rows;
    assert.ok(drawn.length);
    for (const row of drawn) {
      assert.equal(row.color.highlight, row.color.color, "edge " + row.id);
    }
  });

  test("the dashes still carry the evidence on a selected edge", () => {
    const v = loadViewer(catalogue());
    // A dashed edge is a Preliminary one, so the tier control has to be open
    // for there to be one on the canvas at all.
    v.setFilter("tier", "supported_preliminary");
    // In mechanism colouring an unannotated line is one colour whatever its
    // tier, so the colour half of this only exists in evidence colouring.
    v.setFilter("lineColor", "evidence");
    const g = v.catalogueGraph();
    const preliminary = g.edges.find((e) => v.edgeStyle(e).dashes);
    const supported = g.edges.find((e) => !v.edgeStyle(e).dashes);
    assert.ok(preliminary && supported, "need one edge of each kind");
    // vis never touches dashes on selection, so the only way to lose them was
    // to stop drawing a distinguishable colour - which is the other half.
    assert.notEqual(v.edgeStyle(preliminary).color.highlight,
                    v.edgeStyle(supported).color.highlight);
  });

  test("selection is spent on width, and the width is stated rather than vis's", () => {
    const v = loadViewer(catalogue());
    const w = v.graphOptions(true).edges.selectionWidth;
    assert.equal(typeof w, "number");
    assert.ok(w > 0, "a selected line has to read as bolder than an unselected one");
    assert.equal(v.graphOptions(false).edges.selectionWidth, w);
  });

  test("a selected node keeps its fill and its evidence rim", () => {
    const v = loadViewer(catalogue());
    const styles = [
      v.nodeStyle({ kind: "molecule", ref: { n_claims_supported: 1 } }),
      v.nodeStyle({ kind: "molecule", ref: { n_claims_supported: 0 } }),
      v.nodeStyle({ kind: "target", ref: { target_type: "SINGLE PROTEIN" } }),
      v.nodeStyle({ kind: "target", ref: { target_type: "PROTEIN FAMILY" } }),
    ];
    for (const st of styles) {
      assert.equal(st.color.highlight.background, st.color.background);
      assert.equal(st.color.highlight.border, "#ffffff");
      // vis drops a selected node to borderWidthSelected, which defaults to 2 -
      // thinner than the 3px rim that says an entry has a Supported claim.
      assert.ok(st.borderWidthSelected >= st.borderWidth,
                "selecting a node must not thin the rim that carries evidence");
    }
  });
});

describe("a filter change solves the layout and then glides to it", () => {
  test("the re-solve is asked for explicitly, because a data change is not one", () => {
    // This is the whole bug. Changing the DataSets does not call stabilize();
    // vis answers a data change with startSimulation(), which animates the
    // graph on screen until every velocity falls under tolerance - many
    // seconds at 1,373 nodes - and never emits stabilizationIterationsDone, so
    // nothing was there to stop it.
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.refresh();
    const net = v.drawnCanvas().network;
    net.stabilizeCalls = [];
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    assert.deepEqual(plain(net.stabilizeCalls),
                     [v.graphOptions(false).physics.stabilization.iterations]);
  });

  test("the solve runs to completion, and only then does anything move", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.refresh();
    const net = v.drawnCanvas().network;
    const before = v.__frames.length;
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    // Nothing is animated while the solve is running: vis blocks redrawing for
    // the whole of a stabilization, so the glide cannot start until it reports
    // back.
    assert.equal(v.__frames.length, before);

    const solved = {};
    for (const n of v.drawnCanvas().nodes.rows) solved[n.id] = { x: 500, y: 600 };
    net.finishStabilizing(solved);
    assert.equal(net.options.physics, false, "physics is off before the glide");
    assert.ok(v.__frames.length > before, "the glide was not started");

    // It starts from where the reader was looking, not from the solved layout.
    const moved = v.drawnCanvas().nodes.rows.filter((n) => n.x === 100 && n.y === 200);
    assert.ok(moved.length > 0, "nodes were not put back before the first paint");
  });

  test("the glide is bounded and ends exactly on the solved positions", async () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.refresh();
    const net = v.drawnCanvas().network;
    const carried = new Set(v.drawnCanvas().nodes.rows.map((n) => n.id));
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    const solved = {};
    for (const n of v.drawnCanvas().nodes.rows) solved[n.id] = { x: 500, y: 600 };
    net.finishStabilizing(solved);

    const row = (id) => v.drawnCanvas().nodes.rows.find((n) => n.id === id);
    const one = [...carried][0];
    // A frame straight away is part of the way there and not all of it: the
    // glide is a transition rather than a second jump.
    v.__frames.pop()();
    assert.ok(row(one).x >= 100 && row(one).x < 500, "mid-glide at " + row(one).x);

    // Past the duration, every carried node is exactly where the finished solve
    // put it. The glide never leaves the layout somewhere the solver did not
    // choose - which is the whole difference from cutting a solve off.
    await new Promise((r) => setTimeout(r, 650));
    while (v.__frames.length) v.__frames.pop()();
    for (const id of carried) {
      assert.equal(row(id).x, 500, id + " did not arrive");
      assert.equal(row(id).y, 600, id + " did not arrive");
    }
  });

  test("a node that is new to the canvas is not glided from nowhere", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.refresh();
    const net = v.drawnCanvas().network;
    const before = new Set(v.drawnCanvas().nodes.rows.map((n) => n.id));
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    const added = v.drawnCanvas().nodes.rows.filter((n) => !before.has(n.id));
    assert.ok(added.length > 0, "the wider filter should add a node");
    const solved = {};
    for (const n of v.drawnCanvas().nodes.rows) solved[n.id] = { x: 500, y: 600 };
    net.finishStabilizing(solved);
    for (const n of v.drawnCanvas().nodes.rows) {
      if (before.has(n.id)) continue;
      // Left where the solve put it. There is no honest place to start it from.
      assert.notEqual(n.x, 100);
    }
  });

  test("the surviving nodes are handed to the solver where they already were", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    v.refresh();
    const before = new Set(v.drawnCanvas().nodes.rows.map((n) => n.id));
    assert.ok(before.size > 0);
    v.setFilter("tier", "supported_preliminary");
    v.refresh();
    const rows = v.drawnCanvas().nodes.rows;
    assert.ok(rows.length > before.size, "the wider filter should add a node");
    for (const n of rows) {
      if (before.has(n.id)) {
        // The stub reports every node it already holds at (100, 200). A
        // re-solve that carried nothing over would leave these undefined and
        // vis would scatter the whole picture afresh on a one-click change.
        assert.equal(n.x, 100, n.id + " lost its position");
        assert.equal(n.y, 200, n.id + " lost its position");
      } else {
        assert.equal(n.x, undefined, "a node that is new has nowhere to be put back");
      }
    }
  });

  test("a one-second backstop still exists, for a solve that never reports back", () => {
    // Not the mechanism any more - stabilize() completing is - but vis returns
    // early from stabilize() when it has no physics nodes at all, and a page
    // waiting on an event that is not coming would leave physics on.
    const v = loadViewer(catalogue());
    const before = v.__timers.length;
    v.setFilter("periphery", "hide");
    v.refresh();
    const armed = v.__timers.slice(before);
    assert.equal(armed.length, 1);
    assert.equal(armed[0].ms, 1000);
    armed[0].fn();
    assert.equal(v.drawnCanvas().network.options.physics, false);
  });

  test("the first layout gets the full solve and the fit; a re-solve does not", () => {
    const v = loadViewer(catalogue());
    assert.deepEqual(plain(v.graphOptions(true).physics.stabilization),
                     { iterations: 320, updateInterval: 50, fit: true });
    const resolve = v.graphOptions(false).physics.stabilization;
    // A budget rather than a plan: the solver stops the moment it converges,
    // which a re-solve starting from the previous positions usually does well
    // short of this.
    assert.ok(resolve.iterations >= 60);
    // Refitting on a filter change zooms the picture out from under a reader
    // who changed one control, which is the same cost the layout move has.
    assert.equal(resolve.fit, false);
  });
});

describe("a common name finds the molecule it is a name for", () => {
  // The case this was built for. ChEMBL 37 spells THC only inside
  // ".delta.1-thc" and "Delta-9-thc", so "thc" is a substring hit on three
  // molecules at once - including ethchlorvynol, which contains the letters and
  // is not a cannabinoid - and the old ranking broke that tie alphabetically.
  function cannabis() {
    return buildData({
      molecules: [
        molecule({ id: 1, chembl_id: "CHEMBL465", name: "DRONABINOL",
                   aliases: ["THC", "Delta-9-THC", "Marinol"],
                   synonyms: [".delta.1-thc", "Tetrahydrocannabinol"] }),
        molecule({ id: 2, chembl_id: "CHEMBL_DEX", name: "DEXANABINOL",
                   synonyms: ["11-oh-thc"] }),
        molecule({ id: 3, chembl_id: "CHEMBL_ETH", name: "ETHCHLORVYNOL" }),
      ],
    });
  }

  test("a reviewed common name outranks a substring of somebody else's name", () => {
    const v = loadViewer(cannabis());
    const hits = v.searchCatalogue("thc").molecules;
    assert.equal(hits[0].molecule.name, "DRONABINOL");
    assert.equal(hits[0].via, "THC");
    assert.equal(hits[0].field, "alias");
    // The others are still found. Ranking is the fix here, not exclusion.
    assert.deepEqual(plain(hits.map((h) => h.molecule.name)),
                     ["DRONABINOL", "ETHCHLORVYNOL", "DEXANABINOL"]);
  });

  test("how well it matched comes before which field it matched in", () => {
    // The opposite weighting from the legacy page, and on purpose: there the
    // choice was between a gene symbol and an accession, and here a molecule
    // carries ChEMBL's whole synonym list, where a substring of a brand name of
    // a combination product is the commonest kind of hit there is.
    const v = loadViewer(cannabis());
    const exactAlias = v.searchCatalogue("marinol").molecules[0];
    assert.equal(exactAlias.molecule.name, "DRONABINOL");
    assert.equal(exactAlias.rank, 0);
    // An entry's own name still wins a tie at equal match quality.
    const both = v.searchCatalogue("dronabinol").molecules[0];
    assert.equal(both.field, "name");
  });

  test("the row says what kind of name it matched, not just that it matched", () => {
    const v = loadViewer(cannabis());
    const html = v.searchResultsHTML(v.searchCatalogue("thc"));
    assert.match(html, /common name <mark>THC<\/mark>/);
    const alsoCalled = v.searchResultsHTML(v.searchCatalogue("11-oh"));
    assert.match(alsoCalled, /also called/);
    // A hit on the entry's own name is already highlighted in the heading, so
    // the page does not repeat it back.
    const byName = v.searchResultsHTML(v.searchCatalogue("dronabinol"));
    assert.ok(!/common name|also called/.test(byName));
  });

  test("a target's gene symbol outranks its accession at the same match quality", () => {
    const data = buildData({
      targets: [
        target({ chembl_id: "T1", name: "Adenosine receptor A1",
                 components: [{ accession: "P30542", gene_symbol: "ADORA1" }] }),
        target({ chembl_id: "T2", name: "Other",
                 components: [{ accession: "ADORA1X", gene_symbol: "OTHER" }] }),
      ],
    });
    const v = loadViewer(data);
    const hits = v.searchCatalogue("adora1").targets;
    assert.equal(hits[0].target.chembl_id, "T1");
    assert.equal(hits[0].field, "gene");
    // And an exact accession is still an exact hit.
    assert.equal(v.searchCatalogue("p30542").targets[0].target.chembl_id, "T1");
  });

  test("a gene symbol opens the protein, not the family that contains it", () => {
    // A gene symbol is a single protein's name and also one line of a family's
    // membership list, so both match it exactly and the tie has to be broken by
    // something. Breaking it on the name alone put "Adenosine receptor" above
    // "Adenosine receptor A1" - the family standing in front of the subtype,
    // which is the merge D06 exists to refuse.
    const data = buildData({
      targets: [
        target({ chembl_id: "FAM", name: "Adenosine receptor",
                 target_type: "PROTEIN FAMILY", n_components: 4,
                 components: [{ accession: "P30542", gene_symbol: "ADORA1" },
                              { accession: "P29274", gene_symbol: "ADORA2A" }] }),
        target({ chembl_id: "ONE", name: "Adenosine receptor A1", n_components: 1,
                 components: [{ accession: "P30542", gene_symbol: "ADORA1" }] }),
      ],
    });
    const v = loadViewer(data);
    assert.deepEqual(plain(v.searchCatalogue("adora1").targets.map((h) => h.target.chembl_id)),
                     ["ONE", "FAM"]);
  });

  test("the reviewed names are exported, not invented in the page", () => {
    // Search-only and keyed by ChEMBL id in scripts/cohort/export.py, so adding
    // a name is a re-export rather than a rebuild - and so it can never rename
    // a node or reach source matching or evidence.
    const v = loadViewer(cannabis());
    assert.deepEqual(plain(v.lookupMolecule(1).aliases),
                     ["THC", "Delta-9-THC", "Marinol"]);
    assert.equal(v.lookupMolecule(1).name, "DRONABINOL");
  });
});

describe("every heading that offers an explanation has one", () => {
  test("no helpLabel call names a key the help map does not hold", () => {
    // helpLabel falls back to plain text for an unknown key, so a heading that
    // was meant to explain itself simply stops doing it - silently, and
    // indistinguishably from a heading that was never given one. "Claims" on
    // the edge panel had been in that state since it was written.
    const v = loadViewer(catalogue());
    const keys = new Set();
    const re = /helpLabel\([^,]+,\s*"([A-Za-z_]+)"\)/g;
    let m;
    while ((m = re.exec(viewerSource())) !== null) keys.add(m[1]);
    assert.ok(keys.size >= 20, "found only " + keys.size + " helpLabel keys");
    for (const key of keys) {
      assert.match(v.helpLabel("x", key), /class="help-text"/,
                   'no explanation behind "' + key + '"');
    }
  });

  test("a claim block explains the vocabulary it is written in", () => {
    const v = loadViewer(catalogue());
    const measured = v.claimBlockHTML(v.allClaims().find((c) => c.id === 1), null);
    for (const heading of ["Measurements \\(exact\\)", "Endpoint classes",
                           "Measurements"]) {
      assert.match(measured, new RegExp('class="help"[^>]*>' + heading));
    }
    const curated = v.claimBlockHTML(v.allClaims().find((c) => c.id === 2), null);
    for (const heading of ["Mechanism", "References"]) {
      assert.match(curated, new RegExp('class="help"[^>]*>' + heading));
    }
  });

  test("one curated assertion is one set of references, however it was filed", () => {
    // ChEMBL files the same mechanism once per form of the molecule, and the
    // forms fold onto one parent here: caffeine's adenosine-receptor
    // antagonism is curated against the parent and against a salt, with
    // identical references both times. 163 of the 1,083 curated claims are
    // assembled from more than one record, and 435 of the 2,751 reference rows
    // behind them repeat one already listed on the same claim. Showing those
    // twice reads as two citations for one assertion, which is invariant 14.
    const v = loadViewer(catalogue());
    v.registerEvidence(buildShard({
      molecule: 1,
      curated: [
        { claim_id: 2, mec_id: 1213, action_type: "ANTAGONIST",
          mechanism_of_action: "Adenosine receptor antagonist", n_refs: 2,
          mechanism_comment: "Curator's note",
          refs: [{ ref_type: "PubMed", ref_id: "15095008",
                   ref_url: "https://pubmed.ncbi.nlm.nih.gov/15095008/" },
                 { ref_type: "Wikipedia", ref_id: "Adenosine_receptor",
                   ref_url: "https://en.wikipedia.org/wiki/Adenosine_receptor" }] },
        { claim_id: 2, mec_id: 1214, action_type: "ANTAGONIST",
          mechanism_of_action: "Adenosine receptor antagonist", n_refs: 2,
          mechanism_comment: "Curator's note",
          refs: [{ ref_type: "PubMed", ref_id: "15095008",
                   ref_url: "https://pubmed.ncbi.nlm.nih.gov/15095008/" },
                 { ref_type: "Wikipedia", ref_id: "Adenosine_receptor",
                   ref_url: "https://en.wikipedia.org/wiki/Adenosine_receptor" }] },
      ],
    }));
    const ev = v.evidenceFor(1);
    const found = v.curatedRefs(v.allClaims().find((c) => c.id === 2), ev);
    assert.equal(found.records, 2);
    assert.equal(found.refs.length, 2);
    assert.deepEqual(plain(found.notes), ["Curator's note"]);

    const html = v.claimBlockHTML(v.allClaims().find((c) => c.id === 2), ev);
    assert.equal((html.match(/15095008/g) || []).length, 2, "one link, one href");
    // And the folding is stated rather than only being visible as its absence.
    assert.match(html, /once per form of the molecule \(2 records\)/);
    assert.match(html, /each reference listed once/);
    assert.match(html, /References[\s\S]*\(2\)/);
  });

  test("a curated claim is not given a table of zeroes", () => {
    // It is built from ChEMBL's drug_mechanism table and from no measurement at
    // all - none of the 210,157 observations here is attached to one - so
    // "0 measurements, 0 studies" is the wrong question answered rather than a
    // finding about the molecule.
    const v = loadViewer(catalogue());
    const curated = v.claimBlockHTML(v.allClaims().find((c) => c.id === 2), null);
    assert.ok(!/Measurements \(exact\)/.test(curated));
    assert.ok(!/Distinct studies/.test(curated));
    const measured = v.claimBlockHTML(v.allClaims().find((c) => c.id === 1), null);
    assert.match(measured, /Measurements \(exact\)/);
  });

  test("a curated claim is offered its references, never measurements", () => {
    // None of the 210,157 observations in this build is attached to a curated
    // claim, so a "Measurements" disclosure on one opens on an absence that is
    // the panel's category error and reads as the data's.
    const v = loadViewer(catalogue());
    const curated = v.claimBlockHTML(v.allClaims().find((c) => c.id === 2), null);
    assert.ok(!/>Measurements</.test(curated));
    assert.match(curated, /class="help"[^>]*>References/);
  });

  test("the edge panel explains what a line stands for", () => {
    const v = loadViewer(catalogue());
    const html = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT2"));
    assert.match(html, /class="help"[^>]*>Claims/);
    assert.match(html, /listed side by side, never added together/);
  });
});

describe("the export format and the viewer agree", () => {
  test("a short row is read as trailing nulls, not as shifted columns", () => {
    const v = loadViewer(catalogue());
    const m = v.lookupMolecule(2);
    assert.equal(m.name, "THEOPHYLLINE ANHYDROUS");
    assert.equal(m.wikipedia_url, null);
    assert.equal(m.gap_reason, null);
  });

  test("interned columns come back as strings and plain ones as numbers", () => {
    const v = loadViewer(catalogue());
    const c = v.allClaims().find((x) => x.id === 1);
    assert.equal(typeof c.tier, "string");
    assert.equal(typeof c.n_measurements, "number");
    assert.equal(typeof c.endpoints[0].endpoint_class, "string");
  });

  test("the page degrades rather than throwing on an empty catalogue", () => {
    const v = loadViewer(buildData({}));
    assert.deepEqual(plain(v.allMolecules()), []);
    assert.equal(v.openingMolecule(), null);
    assert.deepEqual(plain(v.searchCatalogue("anything").molecules), []);
  });
});

// A catalogue shaped like the one the reader ran into: a molecule with a
// curated claim at a protein family and measured claims at the same proteins,
// which is three rows about two proteins and read as three findings.
// `theirs` is the second molecule's curated direction at the family. Left at
// ANTAGONIST this is caffeine and theophylline; set to AGONIST it is caffeine
// and adenosine, which is the same four receptors approached from the other
// end. `mine` set to null is ChEMBL having curated only one side.
function familyCatalogue({ mine = "ANTAGONIST", theirs = "ANTAGONIST" } = {}) {
  const comps = [
    { accession: "P30542", gene_symbol: "ADORA1", description: "Adenosine receptor A1" },
    { accession: "P29274", gene_symbol: "ADORA2A", description: "Adenosine receptor A2a" },
  ];
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
      molecule({ id: 2, chembl_id: "CHEMBL190", name: "THEOPHYLLINE" }),
    ],
    targets: [
      target({ chembl_id: "T_A1", name: "Adenosine receptor A1", n_components: 1,
               components: [comps[0]] }),
      target({ chembl_id: "T_A2A", name: "Adenosine receptor A2a", n_components: 1,
               components: [comps[1]] }),
      target({ chembl_id: "T_FAM", name: "Adenosine receptor", target_type: "PROTEIN FAMILY",
               n_components: 2, components: comps }),
    ],
    claims: [
      claim({ id: 1, molecule: 1, target: "T_A1" }),
      claim({ id: 2, molecule: 1, target: "T_A2A" }),
      claim({ id: 3, molecule: 1, target: "T_FAM", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: mine,
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
      claim({ id: 4, molecule: 2, target: "T_A1" }),
      claim({ id: 5, molecule: 2, target: "T_A2A" }),
      claim({ id: 6, molecule: 2, target: "T_FAM", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: theirs,
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
    ],
  });
}

describe("a family and its own proteins say how they relate", () => {
  test("the family row names the proteins of its own listed beside it", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showMolecule(v.lookupMolecule(1));
    // Still two claims and never one: D06 refuses the merge, and what the page
    // owes the reader is the line naming them rather than the collapse.
    assert.match(h, /Also listed on their own: ADORA1, ADORA2A</);
  });

  test("each of those proteins names the family it is inside", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showMolecule(v.lookupMolecule(1));
    assert.match(h, /Also inside the Adenosine receptor claim here/);
  });

  test("a protein with no wider target in view says nothing extra", () => {
    const v = loadViewer(catalogue());
    const h = v.showMolecule(v.lookupMolecule(1));
    assert.doesNotMatch(h, /Also inside/);
  });

  test("the edge panel lists the family's proteins and opens each line", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T_FAM"));
    assert.match(h, /The proteins in it/);
    assert.match(h, /2 also have a line of/);
    assert.match(h, /data-select="edge" data-id="1" data-other="T_A1"/);
  });

  test("a protein's edge panel points back up at the family", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("T_A1"));
    assert.match(h, /Wider targets it sits in/);
    assert.match(h, /data-select="edge" data-id="1" data-other="T_FAM"/);
  });

  test("a target panel links a component to the target it is here", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showTarget(v.lookupTarget("T_FAM"));
    assert.match(h, /data-select="target" data-id="T_A1"/);
    const own = v.showTarget(v.lookupTarget("T_A1"));
    assert.match(own, /Wider targets it sits in/);
    assert.match(own, /data-select="target" data-id="T_FAM"/);
  });

  test("an accession held by two targets resolves to neither", () => {
    // Invariant 6 applied to this index: two species' records of one protein
    // are two targets, and picking one asserts an identity ChEMBL does not. A
    // silent answer beats a confident wrong one.
    const data = buildData({
      targets: [
        target({ chembl_id: "T_H", name: "Receptor (human)",
                 components: [{ accession: "P1", gene_symbol: "R", description: "R" }] }),
        target({ chembl_id: "T_R", name: "Receptor (rat)", organism: "Rattus norvegicus",
                 components: [{ accession: "P1", gene_symbol: "R", description: "R" }] }),
      ],
    });
    const v = loadViewer(data);
    assert.equal(v.proteinTarget("P1"), null);
  });
});

describe("a family overlap is not a second share of its own proteins", () => {
  test("a family whose proteins are all shared individually counts once", () => {
    const v = loadViewer(familyCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_targets, 3);
    assert.equal(row.n_shared, 2);
    assert.equal(row.n_exact, 2);
    assert.equal(row.n_broad, 0);
    assert.equal(row.n_subsumed, 1);
  });

  test("the subsumed claim is kept, flagged and still listed", () => {
    const v = loadViewer(familyCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const fam = row.shared.find((s) => s.target.chembl_id === "T_FAM");
    assert.ok(fam, "the family claim is still on the pair");
    assert.equal(fam.subsumed, true);
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.match(h, /1 family claim repeats proteins already shared here/);
    assert.match(h, /all shared above, so not counted again/);
  });

  test("the compression is stated on the ranked row rather than silent", () => {
    const v = loadViewer(familyCatalogue());
    const h = v.showMolecule(v.lookupMolecule(1));
    assert.match(h, /\+1 family repeat<span class="help-text">/);
  });

  test("a family covering a protein shared nowhere else still counts", () => {
    const data = buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "T_A1", components: [
          { accession: "P30542", gene_symbol: "ADORA1", description: "A1" }] }),
        target({ chembl_id: "T_WIDE", target_type: "PROTEIN FAMILY", n_components: 2,
                 components: [
                   { accession: "P30542", gene_symbol: "ADORA1", description: "A1" },
                   { accession: "Q99250", gene_symbol: "SCN2A", description: "S2" }] }),
      ],
      claims: [claim({ id: 1, molecule: 1, target: "T_A1" }),
               claim({ id: 2, molecule: 1, target: "T_WIDE" }),
               claim({ id: 3, molecule: 2, target: "T_A1" }),
               claim({ id: 4, molecule: 2, target: "T_WIDE" })],
    });
    const v = loadViewer(data);
    const row = v.sharedTargets(1)[0];
    assert.equal(row.n_subsumed, 0);
    assert.equal(row.n_shared, 2);
    assert.equal(row.n_broad, 1);
  });

  test("a complex is never subsumed by its own subunits", () => {
    // It is one physical assembly rather than a set of proteins, which is why
    // it already weighs what a single protein weighs.
    const data = buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "T_S", components: [
          { accession: "P1", gene_symbol: "G1", description: "d" }] }),
        target({ chembl_id: "T_C", target_type: "PROTEIN COMPLEX", n_components: 2,
                 components: [
                   { accession: "P1", gene_symbol: "G1", description: "d" },
                   { accession: "P2", gene_symbol: "G2", description: "d" }] }),
        target({ chembl_id: "T_S2", components: [
          { accession: "P2", gene_symbol: "G2", description: "d" }] }),
      ],
      claims: [claim({ id: 1, molecule: 1, target: "T_S" }),
               claim({ id: 2, molecule: 1, target: "T_S2" }),
               claim({ id: 3, molecule: 1, target: "T_C" }),
               claim({ id: 4, molecule: 2, target: "T_S" }),
               claim({ id: 5, molecule: 2, target: "T_S2" }),
               claim({ id: 6, molecule: 2, target: "T_C" })],
    });
    const v = loadViewer(data);
    const row = v.sharedTargets(1)[0];
    assert.equal(row.n_subsumed, 0);
    assert.equal(row.n_shared, 3);
  });
});

describe("no panel is a dead end", () => {
  test("the pair panel opens either end and links both out", () => {
    const v = loadViewer(catalogue());
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT1"), null);
    assert.match(h, /data-select="molecule" data-id="1"/);
    assert.match(h, /data-select="target" data-id="CHEMBLT1"/);
    assert.match(h, /compound_report_card\/CHEMBL113/);
    assert.match(h, /target_report_card\/CHEMBLT1/);
  });

  test("a pair the filters hid still offers both its ends", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    const h = v.showEdge(v.lookupMolecule(1), v.lookupTarget("CHEMBLT3"), null);
    assert.match(h, /No line under the current filters/);
    assert.match(h, /data-select="molecule" data-id="1"/);
    assert.match(h, /data-select="target" data-id="CHEMBLT3"/);
  });

  test("the retained-observations panel goes back to its molecule", () => {
    const v = loadViewer(catalogue());
    const h = v.showRetained(v.lookupMolecule(1), null);
    assert.match(h, /data-select="molecule" data-id="1"/);
  });
});

describe("a cost is stated inside the control that causes it", () => {
  test("the strip across the window is gone", () => {
    // It was five lines of prose at the defaults, sitting between the top bar
    // and the graph - the picture's own space, spent explaining the picture.
    const html = viewerHtml();
    assert.doesNotMatch(html, /id="banners"/);
    assert.doesNotMatch(html, /class="banner"/);
  });

  test("each cost is rendered under the buttons that caused it", () => {
    const v = loadViewer(catalogue());
    v.setFilter("periphery", "hide");
    v.setFilter("potency", 10);
    const h = v.filtersHTML();
    for (const b of v.filterBanners()) {
      const i = h.indexOf('data-filter="' + b.control + '"');
      assert.ok(i >= 0, "no control named " + b.control);
      const cost = h.indexOf(b.text);
      assert.ok(cost > i, b.control + "'s cost should follow its buttons");
    }
  });

  test("every cost names a control the page actually draws", () => {
    // A banner keyed to a control that does not exist would render nowhere,
    // which is the silent version of not stating the cost at all.
    const v = loadViewer(catalogue());
    v.setFilter("potency", 1);
    v.setFilter("basis", "all");
    v.setFilter("lineColor", "mechanism");
    v.setFilter("periphery", "hide");
    v.toggleMechanism("ANTAGONIST");
    const h = v.filtersHTML();
    const banners = v.filterBanners();
    assert.ok(banners.length >= 4);
    for (const b of banners) {
      assert.match(h, new RegExp('data-filter="' + b.control + '"'));
      assert.ok(h.includes(b.text), b.control + "'s cost is missing from the control");
    }
  });

  test("the counting is unchanged - the same numbers, in a different place", () => {
    const v = loadViewer(catalogue());
    v.setFilter("tier", "supported");
    const text = v.filterBanners().map((b) => b.text).join(" ");
    assert.match(text, /1 Preliminary claim is hidden/);
    assert.match(v.filtersHTML(), /1 Preliminary claim is hidden/);
  });
});

describe("a row does not say the same thing twice", () => {
  test("a curated row leads with the direction, not with the word on its pill", () => {
    // "Supported · curated" on the pill and "curated" underneath it is one
    // fact wearing two labels (invariant 13). The pill says how well evidenced
    // the claim is and by which route; the row says what ChEMBL curated.
    const v = loadViewer(catalogue());
    const curated = v.allClaims().find((c) => c.role === "curated");
    const detail = v.claimDetail(curated);
    assert.equal(detail.startsWith("ANTAGONIST"), true);
    assert.doesNotMatch(detail, /curated/);
    assert.match(v.tierPill(curated), /Supported · curated/);
  });

  test("a measured row still says which kind of claim it is", () => {
    // "binding" beside "Supported · multiple studies" is two different facts,
    // so nothing is dropped there.
    const v = loadViewer(catalogue());
    const measured = v.allClaims().find((c) => c.id === 1);
    assert.match(v.claimDetail(measured), /^binding · /);
  });

  test("a curated claim that did not reach Supported still names its role", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [target({ chembl_id: "T" })],
      claims: [claim({ id: 1, molecule: 1, target: "T", role: "curated",
                       tier: "preliminary", curated_support: 0,
                       multiple_study_support: 0, action_type: null,
                       supporting_endpoint_class: null, endpoints: [] })],
    }));
    const c = v.allClaims()[0];
    assert.match(v.claimDetail(c), /curated/);
    assert.match(v.tierPill(c), /Preliminary/);
  });

  test("the target panel and the molecule panel describe a claim alike", () => {
    const v = loadViewer(catalogue());
    const curated = v.allClaims().find((c) => c.role === "curated");
    const target = v.showTarget(v.lookupTarget("CHEMBLT2"));
    const molecule = v.showMolecule(v.lookupMolecule(1));
    const detail = v.claimDetail(curated);
    assert.ok(target.includes(detail), "the target panel uses the shared line");
    assert.ok(molecule.includes(detail), "the molecule panel uses the same one");
    // And the row under the pill no longer repeats it.
    assert.doesNotMatch(target, /Supported · curated<\/span><div class="small muted">curated</);
  });
});

// The caffeine/adenosine shape, which is the real one: two molecules with the
// same receptors between them, curated in opposite directions at the family
// that covers those receptors and nowhere else.
function opposedCatalogue(theirs = "AGONIST") {
  return familyCatalogue({ theirs });
}

describe("an opposite is not a likeness", () => {
  // The counts below are in **proteins**, not in shared target records, and
  // that is the whole of what reading direction at the protein changed here.
  // The pair's one curated row each is at the two-member Adenosine receptor
  // family, so the comparison is made at ADORA1 and at ADORA2A: two proteins,
  // one record. The verdict is unchanged either way, which is the point - the
  // unit moved and what the score claims did not.
  test("two molecules curated in opposite directions are marked and demoted", () => {
    const v = loadViewer(opposedCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 2);
    assert.equal(row.n_opposed, 2);
    assert.equal(row.all_opposed, true);
  });

  test("a claim naming two actions is read as both, not as one unknown word", () => {
    // The build joins a pair's several curated actions with " / " (varenicline
    // AGONIST / PARTIAL AGONIST). Read whole, that matched no opposite, and
    // this agonist against an antagonist was compared as nothing at all.
    const v = loadViewer(opposedCatalogue("AGONIST / PARTIAL AGONIST"));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 2);
    assert.equal(row.n_opposed, 2, "the full opposite outranks the half one");
  });

  test("the same pair curated the same way is neither", () => {
    const v = loadViewer(familyCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 2);
    assert.equal(row.n_opposed, 0);
    assert.equal(row.all_opposed, false);
  });

  test("the demotion is a quarter, and it is the only difference", () => {
    const same = loadViewer(familyCatalogue())
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    const opposite = loadViewer(opposedCatalogue())
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    // Same shared targets, same evidence, same subsumption - only direction.
    assert.equal(opposite.n_shared, same.n_shared);
    assert.equal(opposite.n_subsumed, same.n_subsumed);
    assert.ok(same.score > 0);
    assert.ok(Math.abs(opposite.score - same.score * 0.25) < 1e-9,
      `expected ${same.score * 0.25}, got ${opposite.score}`);
  });

  test("direction is read at a subsumed family, which is where it lives", () => {
    // The load-bearing one. Caffeine and adenosine share four receptors, none
    // of which carries a curated direction; the only row that knows they point
    // opposite ways is the family claim, and that is exactly the row the
    // subsumption rule zeroes. A direction factor applied per scored row would
    // find nothing here.
    const v = loadViewer(opposedCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const fam = row.shared.find((s) => s.target.chembl_id === "T_FAM");
    assert.equal(fam.subsumed, true, "the family is still subsumed");
    assert.equal(fam.direction.opposed, true, "and its direction is still read");
    assert.equal(row.all_opposed, true);
  });

  test("a different action that is not an opposite changes nothing", () => {
    // Agonist against partial agonist is a matter of degree, and positive
    // allosteric modulator against positive modulator is ChEMBL saying one
    // thing twice. 1,215 of the 1,723 disagreeing overlaps in this build are
    // of that kind; reading them as opposition would demote pairs that agree.
    for (const action of ["PARTIAL AGONIST", "POSITIVE ALLOSTERIC MODULATOR",
                          "INHIBITOR", "RELEASING AGENT"]) {
      const v = loadViewer(opposedCatalogue(action));
      const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
      assert.equal(row.n_opposed, 0, `${action} is not the opposite of ANTAGONIST`);
      assert.equal(row.all_opposed, false);
    }
  });

  test("agreement never raises a score", () => {
    // The factor only goes down. Rewarding a curated match would demote every
    // pair ChEMBL has not got round to curating, which is most of them.
    const bare = loadViewer(familyCatalogue({ mine: null, theirs: null }))
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    const agreed = loadViewer(familyCatalogue())
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(agreed.score, bare.score);
  });

  test("ChEMBL's silence on one side is not a disagreement", () => {
    const row = loadViewer(familyCatalogue({ mine: null, theirs: "AGONIST" }))
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 0, "the question cannot be asked");
    assert.equal(row.n_opposed, 0);
    assert.equal(row.all_opposed, false);
  });

  test("a pair that opposes at one target and agrees at another is not demoted", () => {
    const comps = [
      { accession: "P30542", gene_symbol: "ADORA1", description: "Adenosine receptor A1" },
      { accession: "P29274", gene_symbol: "ADORA2A", description: "Adenosine receptor A2a" },
    ];
    const curated = (over) => claim(Object.assign({
      role: "curated", tier_reason: "curated_support", curated_support: 1,
      multiple_study_support: 0, n_measurements: 0, n_studies: 0,
      n_publications: 0, supporting_endpoint_class: null, endpoints: [],
    }, over));
    const data = buildData({
      molecules: [molecule({ id: 1, name: "A" }),
                  molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "T_1", name: "One", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "T_2", name: "Two", n_components: 1, components: [comps[1]] }),
      ],
      claims: [
        curated({ id: 1, molecule: 1, target: "T_1", action_type: "AGONIST" }),
        curated({ id: 2, molecule: 2, target: "T_1", action_type: "ANTAGONIST" }),
        curated({ id: 3, molecule: 1, target: "T_2", action_type: "INHIBITOR" }),
        curated({ id: 4, molecule: 2, target: "T_2", action_type: "INHIBITOR" }),
      ],
    });
    const v = loadViewer(data);
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 2);
    assert.equal(row.n_opposed, 1);
    assert.equal(row.all_opposed, false, "it is not an entirely-opposed pair");
    // Two single proteins, both curated-only on both sides, so each contributes
    // 1.0 (single protein) x 0.75 (curated only) x its prevalence weight. Both
    // molecules are at both targets, so n = 2 and df = 2 at each:
    // log(1 + 2/2) / log(1 + 2) = log 2 / log 3 = 0.63093. Two of them makes
    // 0.94640, and the pair is normalised by sqrt(deg x deg) = sqrt(2 x 2) = 2.
    const undemoted = 2 * 1.0 * 0.75 * (Math.log(2) / Math.log(3)) / 2;
    // Opposed at one of two comparable proteins, so the demotion is half the
    // distance to the quarter: 1 - 0.75 x (1/2) = 0.625. This is the half of
    // the rule that is *not* all-or-nothing, and the reason it is not: under
    // the old rule this pair scored exactly as though nothing were known about
    // direction, which put half-opposed and not-opposed at the same number.
    const expected = undemoted * (1 - 0.75 * (1 / 2));
    assert.ok(Math.abs(row.score - expected) < 1e-9, `got ${row.score}`);
    assert.ok(row.score > undemoted * 0.25, "and it is not quartered either");
    assert.ok(row.score < undemoted, "but it did go down");
    // And the one that opposes still says so on its own row.
    assert.match(v.showPair(v.lookupMolecule(1), v.lookupMolecule(2)),
      /Opposite curated directions here/);
    // The sentence states the cost rather than only the fact.
    assert.match(v.oppositionNote(row), /score is reduced by 38%/);
  });

  test("the demotion scales with how much of the comparison opposes", () => {
    // Three settings of one fixture, so the shape of the rule is held rather
    // than three separate numbers: none opposed keeps the score, all opposed
    // quarters it, and one of two lands exactly half way between on the factor.
    const comps = [
      { accession: "A1", gene_symbol: "G1", description: "One" },
      { accession: "A2", gene_symbol: "G2", description: "Two" },
    ];
    const curated = (over) => claim(Object.assign({
      role: "curated", tier_reason: "curated_support", curated_support: 1,
      multiple_study_support: 0, n_measurements: 0, n_studies: 0,
      n_publications: 0, supporting_endpoint_class: null, endpoints: [],
    }, over));
    const build = (second) => loadViewer(buildData({
      molecules: [molecule({ id: 1, name: "A" }),
                  molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "T_1", name: "One", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "T_2", name: "Two", n_components: 1, components: [comps[1]] }),
      ],
      claims: [
        curated({ id: 1, molecule: 1, target: "T_1", action_type: "AGONIST" }),
        curated({ id: 2, molecule: 2, target: "T_1", action_type: "ANTAGONIST" }),
        curated({ id: 3, molecule: 1, target: "T_2", action_type: "AGONIST" }),
        curated({ id: 4, molecule: 2, target: "T_2", action_type: second }),
      ],
    })).sharedTargets(1).find((r) => r.molecule.id === 2);

    // T_1 opposes in both variants; T_2 only in the second.
    const partly = build("AGONIST");
    const entirely = build("ANTAGONIST");
    assert.equal(partly.n_comparable, 2);
    assert.equal(partly.n_opposed, 1);
    assert.equal(partly.all_opposed, false);
    assert.equal(entirely.n_opposed, 2);
    assert.equal(entirely.all_opposed, true);
    // One of two against two of two: the factors are 0.625 and 0.25, so the
    // partly-opposed pair scores 2.5x the entirely-opposed one.
    assert.ok(Math.abs(partly.score / entirely.score - 0.625 / 0.25) < 1e-9,
      `got ${partly.score / entirely.score}`);
  });

  test("the ranked row and the pair panel say it, from one sentence", () => {
    const v = loadViewer(opposedCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const note = v.oppositionNote(row);
    assert.ok(note, "there is a sentence");
    assert.match(note, /opposite directions/);
    assert.match(note, /quartered/);
    const list = v.showMolecule(v.lookupMolecule(1));
    const pair = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    // The ranked row carries it as a tag, explained on hover; the pair panel
    // carries the sentence.
    assert.ok(list.includes(v.oppositionTag(row)), "the ranked row carries it");
    assert.match(v.oppositionTag(row), /opposite actions, score ×¼/);
    assert.ok(pair.includes(note), "and the pair panel says it in full");
    // The block itself names the two directions and whose is whose.
    assert.match(pair, /Opposite curated directions here/);
    assert.match(pair, /CAFFEINE ANTAGONIST/);
    assert.match(pair, /THEOPHYLLINE AGONIST/);
  });

  test("nothing is dropped: the opposed claim is still listed", () => {
    const v = loadViewer(opposedCatalogue());
    const pair = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.match(pair, /Adenosine receptor/);
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.shared.length, 3, "all three shared targets are still on the pair");
  });

  test("a pair with no opposition says nothing about direction", () => {
    const v = loadViewer(familyCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(v.oppositionNote(row), "",
      "silence, rather than reporting no opposition found on every row");
    assert.doesNotMatch(v.showPair(v.lookupMolecule(1), v.lookupMolecule(2)),
      /opposite directions/);
  });

  test("every action named as an opposite is one ChEMBL can actually write", () => {
    // The map is a claim about pharmacology, not about this snapshot, but an
    // entry naming an action that does not exist would be silently dead.
    const v = loadViewer(familyCatalogue());
    for (const pair of v.opposedActions()) {
      assert.equal(pair.length, 2);
      for (const action of pair) {
        assert.equal(action, action.toUpperCase(),
          "ChEMBL's actions are upper case and matched exactly");
      }
    }
    // And the relation is symmetric however it is asked.
    const one = v.directionAt([{ action_type: "AGONIST" }], [{ action_type: "ANTAGONIST" }]);
    const other = v.directionAt([{ action_type: "ANTAGONIST" }], [{ action_type: "AGONIST" }]);
    assert.equal(one.opposed, true);
    assert.equal(other.opposed, true);
  });

  test("the efficacy axis is treated alike, whichever word ChEMBL used", () => {
    // PARTIAL AGONIST against INVERSE AGONIST was on the list and came off it.
    // Not because the pharmacology is wrong -- a partial agonist and an inverse
    // agonist really do sit either side of neutral efficacy -- but because
    // ChEMBL carries four INVERSE AGONIST claims in the whole catalogue against
    // 260 ANTAGONIST, so the entry encoded a curator's word rather than a
    // difference. Against aripiprazole it demoted haloperidol and not
    // chlorpromazine, risperidone or fluphenazine, which are the same
    // relationship spelled the commoner way.
    //
    // The rule this holds is consistency: PARTIAL AGONIST vs ANTAGONIST is a
    // matter of degree and not opposed, so PARTIAL AGONIST vs INVERSE AGONIST --
    // the same axis one notch further -- must not be opposed either. Re-adding
    // one without the other is the state this test exists to prevent.
    const v = loadViewer(familyCatalogue());
    for (const other of ["ANTAGONIST", "INVERSE AGONIST"]) {
      const d = v.directionAt([{ action_type: "PARTIAL AGONIST" }],
                              [{ action_type: other }]);
      assert.equal(d.opposed, false,
        `PARTIAL AGONIST against ${other} is a matter of degree, not a reversal`);
    }
    // A full agonist against either is still a reversal, which is what keeps
    // this a statement about partial agonism rather than about inverse agonism.
    for (const other of ["ANTAGONIST", "INVERSE AGONIST"]) {
      const d = v.directionAt([{ action_type: "AGONIST" }], [{ action_type: other }]);
      assert.equal(d.opposed, true, `AGONIST against ${other} is still opposed`);
    }
  });

  test("a molecule contradicting itself is not counted as opposing the other", () => {
    // Two curated directions of its own at one target is ChEMBL disagreeing
    // with itself; a pairing that matches outranks one that opposes.
    const v = loadViewer(familyCatalogue());
    const d = v.directionAt(
      [{ action_type: "AGONIST" }, { action_type: "ANTAGONIST" }],
      [{ action_type: "ANTAGONIST" }]);
    assert.equal(d.same, true);
    assert.equal(d.opposed, false);
  });
});

// The morphine/naltrexone shape: one receptor, two directions, filed on two
// different ChEMBL target records so that nothing on the pair ever compared
// them. Morphine is curated AGONIST at human mu-opioid and naltrexone
// ANTAGONIST at the human mu/kappa/delta family, and morphine's nearest
// neighbour of 380 was the drug given to reverse it.
function splitDirectionCatalogue({ mine = "AGONIST", theirs = "ANTAGONIST" } = {}) {
  const mu = { accession: "P35372", gene_symbol: "OPRM1",
               description: "Mu-type opioid receptor" };
  const kappa = { accession: "P41145", gene_symbol: "OPRK1",
                  description: "Kappa-type opioid receptor" };
  return buildData({
    molecules: [
      molecule({ id: 1, chembl_id: "CHEMBL70", name: "MORPHINE" }),
      molecule({ id: 2, chembl_id: "CHEMBL1200657", name: "NALTREXONE" }),
    ],
    targets: [
      target({ chembl_id: "T_MU", name: "Mu opioid receptor",
               n_components: 1, components: [mu] }),
      target({ chembl_id: "T_FAM", name: "Opioid receptors; mu/kappa/delta",
               target_type: "PROTEIN FAMILY", n_components: 2,
               components: [mu, kappa] }),
    ],
    claims: [
      // Both are measured at the protein, which is the record they share.
      claim({ id: 1, molecule: 1, target: "T_MU" }),
      claim({ id: 2, molecule: 2, target: "T_MU" }),
      // Morphine's direction is at the protein...
      claim({ id: 3, molecule: 1, target: "T_MU", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: mine,
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
      // ...and naltrexone's at the family, which only it has a claim at.
      claim({ id: 4, molecule: 2, target: "T_FAM", role: "curated",
              tier_reason: "curated_support", curated_support: 1,
              multiple_study_support: 0, action_type: theirs,
              n_measurements: 0, n_studies: 0, n_publications: 0,
              supporting_endpoint_class: null, endpoints: [] }),
    ],
  });
}

describe("direction is read at the protein, not at the target record", () => {
  test("two directions filed a record apart are compared and demote the pair", () => {
    const v = loadViewer(splitDirectionCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    // No shared record carries both directions, so the one-record rule sees
    // nothing at all here.
    const mu = row.shared.find((s) => s.target.chembl_id === "T_MU");
    assert.equal(mu.direction, null, "the shared record cannot answer it");
    // The protein can.
    assert.equal(row.n_comparable, 1);
    assert.equal(row.n_opposed, 1);
    assert.equal(row.all_opposed, true);
    assert.equal(row.opposed_proteins.length, 1);
    assert.equal(row.opposed_proteins[0].accession, "P35372");
    assert.deepEqual(row.opposed_proteins[0].mine, ["AGONIST"]);
    assert.deepEqual(row.opposed_proteins[0].theirs, ["ANTAGONIST"]);
  });

  test("nothing about what is shared, weighed or subsumed moves with it", () => {
    // The whole licence for this rule is that it is not the D06 merge: it
    // changes which two actions are compared and nothing else. So the same
    // catalogue with the directions stripped must agree about every structural
    // number, and differ only by the quarter.
    const v = loadViewer(splitDirectionCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const plain = loadViewer(splitDirectionCatalogue({ mine: null, theirs: null }))
      .sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_shared, plain.n_shared);
    assert.equal(row.n_exact, plain.n_exact);
    assert.equal(row.n_broad, plain.n_broad);
    assert.equal(row.n_subsumed, plain.n_subsumed);
    assert.equal(row.shared.length, plain.shared.length);
    assert.ok(plain.score > 0);
    assert.ok(Math.abs(row.score - plain.score * 0.25) < 1e-9,
      `expected ${plain.score * 0.25}, got ${row.score}`);
  });

  test("the pair panel names an opposition no single block can show", () => {
    const v = loadViewer(splitDirectionCatalogue());
    const pair = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    // A page that announces a demotion and shows nothing explaining it is the
    // shape this project keeps trying not to have.
    assert.match(pair, /quartered/);
    assert.match(pair, /Curated on two different records/);
    assert.match(pair, /OPRM1/);
    assert.match(pair, /MORPHINE AGONIST \(ChEMBL\) at Mu opioid receptor \(human\)/);
    assert.match(pair, /NALTREXONE ANTAGONIST \(ChEMBL\) at Opioid receptors; mu\/kappa\/delta \(human\)/);
  });

  test("and does not repeat one a block already states", () => {
    // Caffeine and adenosine carry both directions on one shared family row,
    // which the block prints beside the claims themselves. Saying it again
    // above would be one fact under two headings (invariant 13).
    const v = loadViewer(opposedCatalogue());
    const pair = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.match(pair, /Opposite curated directions here/);
    assert.doesNotMatch(pair, /different records/);
  });

  test("the counts are in proteins, and the sentence says so", () => {
    // n_comparable is no longer a count of shared target records, and the row
    // it is printed on carries the shared-target count a few characters away.
    const v = loadViewer(opposedCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_shared, 2, "two shared proteins, the family subsumed");
    assert.equal(row.n_comparable, 2, "and the family covers both of them");
    assert.match(v.oppositionNote(row), /shared proteins/);
    assert.doesNotMatch(v.oppositionNote(row), /shared targets/);
  });

  test("the key is the accession, never the gene symbol", () => {
    // Invariant 6. The prototype pooled on the symbol so that OPRK1 and Oprk1
    // would meet; measured against the real build the two keys recover the
    // same 535 entirely-opposed pairs, so the symbol buys nothing and a name
    // is not worth trading an identifier for. Here two records carry one
    // symbol on two accessions, and they must not be treated as one protein.
    const human = { accession: "P35372", gene_symbol: "OPRM1",
                    description: "Mu-type opioid receptor" };
    const rat = { accession: "P33535", gene_symbol: "OPRM1",
                  description: "Mu-type opioid receptor" };
    const curated = (over) => claim(Object.assign({
      role: "curated", tier_reason: "curated_support", curated_support: 1,
      multiple_study_support: 0, n_measurements: 0, n_studies: 0,
      n_publications: 0, supporting_endpoint_class: null, endpoints: [],
    }, over));
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, name: "A" }),
                  molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "T_BOTH", name: "Mu opioid receptor, both records",
                 target_type: "PROTEIN FAMILY", n_components: 2,
                 components: [human, rat] }),
        target({ chembl_id: "T_H", name: "Mu opioid receptor (human)",
                 n_components: 1, components: [human] }),
        target({ chembl_id: "T_R", name: "Mu opioid receptor (rat)",
                 n_components: 1, components: [rat] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_BOTH" }),
        claim({ id: 2, molecule: 2, target: "T_BOTH" }),
        curated({ id: 3, molecule: 1, target: "T_H", action_type: "AGONIST" }),
        curated({ id: 4, molecule: 2, target: "T_R", action_type: "ANTAGONIST" }),
      ],
    }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.equal(row.n_comparable, 0,
      "two accessions are two proteins however they are spelled");
    assert.equal(row.all_opposed, false);
  });

  test("a pair that agrees elsewhere is released rather than quartered", () => {
    // The two pairs the real build *un*-demotes, and they are as much the
    // argument as the 290 it adds: trimipramine and tolazoline are both
    // ANTAGONIST at three adrenoceptors and opposed at one, which the
    // one-record view could not see, so a pair agreeing three times out of
    // four was being quartered.
    const p1 = { accession: "A1", gene_symbol: "ADRA1A", description: "One" };
    const p2 = { accession: "A2", gene_symbol: "ADRA2A", description: "Two" };
    const curated = (over) => claim(Object.assign({
      role: "curated", tier_reason: "curated_support", curated_support: 1,
      multiple_study_support: 0, n_measurements: 0, n_studies: 0,
      n_publications: 0, supporting_endpoint_class: null, endpoints: [],
    }, over));
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, name: "TRIMIPRAMINE" }),
                  molecule({ id: 2, chembl_id: "C2", name: "TOLAZOLINE" })],
      targets: [
        target({ chembl_id: "T_1", name: "One", n_components: 1, components: [p1] }),
        target({ chembl_id: "T_2", name: "Two", n_components: 1, components: [p2] }),
        target({ chembl_id: "T_FAM", name: "Adrenoceptors",
                 target_type: "PROTEIN FAMILY", n_components: 2,
                 components: [p1, p2] }),
      ],
      claims: [
        // Both are measured at both proteins, so both records are shared.
        claim({ id: 1, molecule: 1, target: "T_1" }),
        claim({ id: 2, molecule: 2, target: "T_1" }),
        claim({ id: 3, molecule: 1, target: "T_2" }),
        claim({ id: 4, molecule: 2, target: "T_2" }),
        // One record carries both directions and they oppose: the whole of
        // what the one-record rule can see, and it quartered the pair on it.
        curated({ id: 5, molecule: 1, target: "T_2", action_type: "ANTAGONIST" }),
        curated({ id: 6, molecule: 2, target: "T_2", action_type: "AGONIST" }),
        // And the agreement it could not see: A's family claim covers both
        // proteins, and B is curated the same way at the other one.
        curated({ id: 7, molecule: 1, target: "T_FAM", action_type: "ANTAGONIST" }),
        curated({ id: 8, molecule: 2, target: "T_1", action_type: "ANTAGONIST" }),
      ],
    }));
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    const two = row.shared.find((s) => s.target.chembl_id === "T_2");
    assert.equal(two.direction.opposed, true, "the one record still opposes");
    assert.equal(row.n_comparable, 2, "but there are two proteins to ask about");
    assert.equal(row.n_opposed, 1);
    assert.equal(row.all_opposed, false, "so the pair keeps its score");
  });
});

// ---------------------------------------------------------------------------

describe("the canvas draws the edges that are on it, and no others", () => {
  // vis culls nodes to the viewport on every frame and never culls edges, so
  // zoomed in on one molecule the page was drawing all 12,835 lines to show the
  // dozen in the window - a flat ~17 ms of every frame, which is what made the
  // drag and the zoom slow. edgeInRect is what answers "is this line on
  // screen", and it has to be exact in one direction and cheap in the other: a
  // line wrongly kept costs a stroke, a line wrongly dropped is a wrong
  // picture.
  const RECT = { left: -100, top: -50, right: 100, bottom: 50 };
  const seg = (ax, ay, bx, by) => ({ from: { x: ax, y: ay }, to: { x: bx, y: by } });

  // Written a second, independent way: the segment against the four sides,
  // rather than against four half-planes. Liang-Barsky agreeing with itself
  // would prove nothing.
  function intersects(e, r) {
    const a = e.from, b = e.to;
    const inside = (p) => p.x >= r.left && p.x <= r.right && p.y >= r.top && p.y <= r.bottom;
    if (inside(a) || inside(b)) return true;
    const cross = (x1, y1, x2, y2, x3, y3, x4, y4) => {
      const d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3);
      if (d === 0) return false;
      const t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d;
      const u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d;
      return t >= 0 && t <= 1 && u >= 0 && u <= 1;
    };
    return cross(a.x, a.y, b.x, b.y, r.left, r.top, r.right, r.top)
        || cross(a.x, a.y, b.x, b.y, r.right, r.top, r.right, r.bottom)
        || cross(a.x, a.y, b.x, b.y, r.right, r.bottom, r.left, r.bottom)
        || cross(a.x, a.y, b.x, b.y, r.left, r.bottom, r.left, r.top);
  }

  test("a line with an end in the window is drawn", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.edgeInRect(seg(0, 0, 9000, 9000), RECT), true);
    assert.equal(v.edgeInRect(seg(-9000, -9000, 0, 0), RECT), true);
  });

  test("a line crossing the window with both ends outside it is drawn", () => {
    // The case a bounding-box test also gets right, and the case that matters:
    // this layout is hubs and spokes, so a great many long lines pass through.
    const v = loadViewer(catalogue());
    assert.equal(v.edgeInRect(seg(-9000, 0, 9000, 0), RECT), true);
    assert.equal(v.edgeInRect(seg(0, -9000, 0, 9000), RECT), true);
    assert.equal(v.edgeInRect(seg(-9000, -9000, 9000, 9000), RECT), true);
  });

  test("a line whose box covers the window but whose line misses it is dropped", () => {
    // This is the whole reason the test is a clip and not a box overlap. The
    // box rule was written first and kept 9,876 of 12,835 edges at zoom 2.0,
    // where the clip keeps 60 - because a long edge's box is large and any box
    // containing the window passes.
    const v = loadViewer(catalogue());
    const corner = seg(-9000, -8000, 9000, 10000);
    assert.equal(intersects(corner, RECT), false, "the reference agrees it misses");
    assert.equal(v.edgeInRect(corner, RECT), false);
  });

  test("a line wholly outside the window is dropped", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.edgeInRect(seg(200, 200, 900, 900), RECT), false);
    assert.equal(v.edgeInRect(seg(-900, 0, -200, 0), RECT), false, "left");
    assert.equal(v.edgeInRect(seg(0, -900, 0, -200), RECT), false, "above");
  });

  test("a self-loop is kept exactly when its node is in the window", () => {
    // from === to is a zero-length segment, which the clip reads as the point.
    const v = loadViewer(catalogue());
    const at = (x, y) => { const n = { x: x, y: y }; return { from: n, to: n }; };
    assert.equal(v.edgeInRect(at(0, 0), RECT), true);
    assert.equal(v.edgeInRect(at(500, 500), RECT), false);
  });

  test("an edge missing an end is kept rather than guessed at", () => {
    // vis skips an unconnected edge itself. Keeping it costs one iteration;
    // dropping it would be this code deciding something it cannot see.
    const v = loadViewer(catalogue());
    assert.equal(v.edgeInRect({ from: null, to: { x: 0, y: 0 } }, RECT), true);
    assert.equal(v.edgeInRect({}, RECT), true);
  });

  test("the clip agrees with an independent reference over random segments", () => {
    // The property that matters, asserted rather than sampled by hand, over
    // spans far longer than the window - which is what this layout is full of
    // and what the box rule got wrong.
    const v = loadViewer(catalogue());
    let seed = 20260921;
    const rnd = () => { seed = (seed * 1103515245 + 12345) % 0x7fffffff; return seed / 0x7fffffff; };
    let checked = 0, kept = 0;
    for (let i = 0; i < 20000; i++) {
      const span = [40, 300, 4000, 90000][i % 4];
      const c = () => rnd() * 2 * span - span;
      const e = seg(c(), c(), c(), c());
      const got = v.edgeInRect(e, RECT);
      assert.equal(got, intersects(e, RECT),
        "clip and reference disagree on " + JSON.stringify(e));
      checked++;
      if (got) kept++;
    }
    assert.equal(checked, 20000);
    assert.ok(kept > 0 && kept < checked, "the sample exercises both answers");
  });

  test("the window is the canvas, margined, and not the graph", () => {
    const v = loadViewer(catalogue());
    const net = {
      canvas: { frame: { canvas: { clientWidth: 1000, clientHeight: 600 } } },
      DOMtoCanvas: (p) => ({ x: p.x * 2, y: p.y * 2 }),
    };
    const r = v.canvasViewRect(net);
    // The margin is applied in DOM pixels, before the mapping, so it is a
    // fixed number of screen pixels off the edge at every zoom rather than a
    // fixed number of canvas units.
    assert.ok(r.left < 0 && r.top < 0, "it reaches past the near corner");
    assert.ok(r.right > 2000 && r.bottom > 1200, "and past the far one");
  });

  test("a network it does not recognise is left alone", () => {
    // A drawing optimisation that reaches into vis's internals must fail by
    // doing nothing, not by drawing the wrong picture. Every name below is one
    // the wrapper reaches for.
    const v = loadViewer(catalogue());
    const ok = () => ({
      renderer: { _drawEdges() {}, _drawArrows() {}, dragging: false, zooming: false },
      body: { edgeIndices: [], edges: {}, emitter: { on() {} } },
      on() {},
    });
    assert.equal(v.installEdgeCulling(ok()), true, "the shape it does know");
    assert.equal(v.installEdgeCulling(null), false);
    assert.equal(v.installEdgeCulling({}), false);
    for (const missing of ["renderer", "body"]) {
      const n = ok(); delete n[missing];
      assert.equal(v.installEdgeCulling(n), false, "no " + missing);
    }
    for (const missing of ["_drawEdges", "_drawArrows"]) {
      const n = ok(); delete n.renderer[missing];
      assert.equal(v.installEdgeCulling(n), false, "no renderer." + missing);
    }
    const noIndices = ok(); noIndices.body.edgeIndices = undefined;
    assert.equal(v.installEdgeCulling(noIndices), false, "no edgeIndices");
    const noEmitter = ok(); noEmitter.body.emitter = {};
    assert.equal(v.installEdgeCulling(noEmitter), false, "no emitter.on");
  });

  // A vis stand-in: enough of the shape for the wrapper to install onto, and
  // it records what list it was handed.
  function fakeNetwork(edges, indices) {
    const body = { edgeIndices: indices, edges: edges,
                   emitter: { on(k, f) { this[k] = f; }, emit(k) { this.emitted.push(k); },
                              emitted: [] } };
    const net = {
      renderer: {
        dragging: false, zooming: false,
        walked: null,
        _drawEdges() { this.walked = body.edgeIndices.slice(); },
        _drawArrows() {},
      },
      body: body,
      canvas: { frame: { canvas: { clientWidth: 100, clientHeight: 100 } } },
      DOMtoCanvas: (p) => ({ x: p.x, y: p.y }),
      handlers: {},
      on(name, fn) { this.handlers[name] = fn; },
    };
    return net;
  }

  test("culling narrows the list vis walks and puts it back", () => {
    // The wrapper swaps what vis iterates rather than reimplementing how vis
    // draws, which is the point: body.edgeIndices must be exactly as it was by
    // the time anything else reads it.
    const v = loadViewer(catalogue());
    const at = (x, y) => ({ x: x, y: y });
    const net = fakeNetwork({
      near: { from: at(0, 0), to: at(10, 10) },
      far: { from: at(9000, 9000), to: at(9100, 9100) },
    }, ["near", "far"]);
    assert.equal(v.installEdgeCulling(net), true);
    net.renderer._drawEdges({ lineCap: "" });
    // plain(), because the list the wrapper hands vis is built inside the vm
    // sandbox and so carries that realm's Array prototype.
    assert.deepEqual(plain(net.renderer.walked), ["near"],
      "only the edge in the window is walked");
    assert.deepEqual(plain(net.body.edgeIndices), ["near", "far"],
      "and the real list is back before anything else reads it");
  });

  // Enough of a 2d context to record what was asked of it. `drawEdges` writes
  // only these, which is most of the point of it.
  function fakeCtx() {
    const ctx = {
      lineCap: "butt", strokeStyle: null, lineWidth: -1,
      dash: null, ops: [], strokes: 0,
      setLineDash(d) { ctx.dash = d.slice(); ctx.ops.push(["dash", d.join(",")]); },
      beginPath() { ctx.ops.push(["begin"]); },
      moveTo(x, y) { ctx.ops.push(["move", x, y]); },
      lineTo(x, y) { ctx.ops.push(["line", x, y]); },
      stroke() { ctx.strokes++;
        ctx.ops.push(["stroke", ctx.strokeStyle, ctx.lineWidth, ctx.dash && ctx.dash.join(",")]); },
    };
    return ctx;
  }

  // A canvas of `n` edges, `lit` of them at the opacity a selection writes on
  // the lines it lights directly.
  function crowdedNetwork(n, lit) {
    const at = (x, y) => ({ x: x, y: y });
    const edges = {}, indices = [];
    for (let i = 0; i < n; i++) {
      indices.push("e" + i);
      edges["e" + i] = { from: at(0, 0), to: at(1, 1),
                         options: { color: { opacity: i < lit ? 0.9 : 0.06 } } };
    }
    return fakeNetwork(edges, indices);
  }

  test("a gesture gives up nothing at all", () => {
    // Two rules stood here before and both were wrong, in the same way at
    // different sizes. The first dropped every line for the frames the reader
    // was moving the canvas - vis's own hideEdgesOnDrag bargain - so the lines
    // from a selected molecule to its targets vanished during a zoom or a drag,
    // which is the single thing a reader is most likely to be moving the canvas
    // to see. The second kept those and dropped only the dim haze of everything
    // else, but the haze is most of the ink, so the picture still changed when
    // a gesture began and changed back when it ended: glitching rather than
    // simplifying. The edge pass got cheap enough that neither is needed.
    const v = loadViewer(catalogue());
    const net = crowdedNetwork(4000, 43);
    assert.equal(v.installEdgeCulling(net), true);
    const frame = () => {
      net.body.emitter.initRedraw();
      net.renderer.walked = null;
      net.renderer._drawEdges(fakeCtx());
      return net.renderer.walked && net.renderer.walked.length;
    };
    assert.equal(frame(), 4000, "at rest");
    net.renderer.dragging = true;
    assert.equal(frame(), 4000, "mid-drag, the same lines");
    net.renderer.dragging = false;
    net.renderer.zooming = true;
    assert.equal(frame(), 4000, "and mid-zoom");
    net.renderer.zooming = false;
    assert.equal(frame(), 4000, "and after");
  });


  test("the line cap is stated, so a frame does not depend on what is on screen", () => {
    // vis's dashed-line draw sets ctx.lineCap = "round" outside its own
    // save/restore, so the cap leaks to every edge drawn after the first
    // dashed one. That made a line's ends a function of how many dashed edges
    // preceded it, which culling changes - and it showed up as 960
    // sub-perceptual pixels between a culled frame and an unculled one.
    const v = loadViewer(catalogue());
    const net = fakeNetwork({}, []);
    assert.equal(v.installEdgeCulling(net), true);
    const ctx = { lineCap: "butt" };
    net.renderer._drawEdges(ctx);
    assert.equal(ctx.lineCap, "round");
  });

  test("the page installs it on the network it builds", () => {
    const src = viewerSource();
    assert.match(src, /installEdgeCulling\(network\)/,
      "the cull is wired into renderGraph, not merely defined");
  });
});

// ---------------------------------------------------------------------------
describe("a repaint does not rebuild what it is not changing", () => {
  // vis keeps two copies of every node and edge - the DataSet row the page
  // wrote, and the object it draws - and it answers any write to the DataSet by
  // rebuilding its data model for the whole graph. That costs the same whether
  // one edge changed or all 12,835, because the work is proportional to the
  // graph: updating a single edge measures 37 ms on this build. applyHighlight
  // made two of those writes on every selection, and a selection changes no
  // structure at all, so a click cost 187 ms - and syncLabels calls the same
  // function when a zoom crosses the label threshold, which put the stall in
  // the middle of a gesture too.
  //
  // The fakes below model the one thing about vis that makes this delicate, and
  // they model it because getting it wrong shipped: a Node's label settings
  // live in a labelModule with its *own copy* of the font, and only setOptions
  // syncs the two. Written straight onto node.options, every label on the
  // canvas went on drawing at whatever the last DataSet write left it at - all
  // 3,097 at full brightness instead of the ~309 a selection lights, which is a
  // wall of unreadable text with no visible highlight in it. A fake that merged
  // into one object would have passed that build, which is exactly what the
  // first version of these tests did.
  function fakeNode() {
    const node = {
      options: { opacity: 1, font: { size: 12, color: "#ffffff" } },
      x: 0, y: 0,
      // vis's own split: the label module is a copy, refreshed by setOptions
      // and by nothing else.
      labelModule: { fontOptions: { size: 12, color: "#ffffff" } },
      setOptions(o) {
        if (o.opacity !== undefined) node.options.opacity = o.opacity;
        if (o.font) {
          Object.assign(node.options.font, o.font);
          Object.assign(node.labelModule.fontOptions, o.font);
        }
      },
    };
    return node;
  }
  function fakeEdge() {
    const edge = {
      options: { color: { color: "#000000", highlight: "#000000", opacity: 1 } },
      setOptions(o) { if (o.color) Object.assign(edge.options.color, o.color); },
    };
    // An edge resolves its colour through edgeType, which in this build shares
    // the options object rather than copying it. That sharing is what makes the
    // cheap path legitimate, and paintStyles checks for it at runtime.
    edge.edgeType = { options: edge.options };
    return edge;
  }
  function fakeBody(nodeIds, edgeIds) {
    const nodes = {}, edges = {};
    for (const id of nodeIds) nodes[id] = fakeNode();
    for (const id of edgeIds) edges[id] = fakeEdge();
    return { nodes: nodes, edges: edges,
             emitter: { emitted: [], emit(k) { this.emitted.push(k); } } };
  }

  test("a label follows the highlight, and not the last DataSet write", () => {
    // The assertion the shipped bug failed. options.font agreeing proves
    // nothing; the label module is what paints.
    const v = loadViewer(catalogue());
    const body = fakeBody(["m1", "m2"], ["e1"]);
    const ok = v.paintStyles({ body: body },
      [{ id: "m1", opacity: 0.12, font: { size: 0, color: "#464e5c" } },
       { id: "m2", opacity: 1, font: { size: 12, color: "#e6e8ec" } }],
      [{ id: "e1", color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.9 } }]);
    assert.equal(ok, true);
    assert.equal(body.nodes.m1.labelModule.fontOptions.size, 0,
      "a dimmed node's label is hidden where the highlight says so");
    assert.equal(body.nodes.m1.labelModule.fontOptions.color, "#464e5c");
    assert.equal(body.nodes.m2.labelModule.fontOptions.size, 12);
    assert.equal(body.nodes.m2.labelModule.fontOptions.color, "#e6e8ec",
      "and a lit one stays named and bright");
    assert.equal(body.nodes.m1.options.opacity, 0.12, "the shape dims too");
    assert.equal(body.nodes.m2.options.opacity, 1);
    assert.equal(body.edges.e1.options.color.color, "#4da3ff");
    assert.equal(body.edges.e1.options.color.opacity, 0.9);
    assert.deepEqual(plain(body.emitter.emitted), ["_requestRedraw"],
      "the DataSet write used to ask for the frame; nothing else will");
  });

  test("it goes through each node's own setOptions", () => {
    // Stated directly, because it is the difference between working and the
    // wall of text: nothing may write node.options.font without syncing the
    // label module, and setOptions is the only thing that does.
    const v = loadViewer(catalogue());
    const body = fakeBody(["m1"], []);
    const calls = [];
    const inner = body.nodes.m1.setOptions;
    body.nodes.m1.setOptions = function (o) { calls.push(o); return inner(o); };
    v.paintStyles({ body: body },
      [{ id: "m1", opacity: 0.55, font: { size: 12, color: "#8d96a5" } }], []);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].opacity, 0.55);
    assert.equal(calls[0].font.size, 12);
    assert.equal(calls[0].font.color, "#8d96a5");
  });

  test("one node's label is not every node's label", () => {
    // If vis shared a font between two nodes, a per-node write would dim the
    // whole canvas at once. It copies per node, and this says so about the
    // shape the fast path relies on.
    const v = loadViewer(catalogue());
    const body = fakeBody(["m1", "m2"], []);
    assert.notEqual(body.nodes.m1.options.font, body.nodes.m2.options.font);
    v.paintStyles({ body: body },
      [{ id: "m1", opacity: 0.12, font: { size: 0, color: "#464e5c" } }], []);
    assert.equal(body.nodes.m2.labelModule.fontOptions.size, 12,
      "the other node is untouched");
    assert.equal(body.nodes.m2.labelModule.fontOptions.color, "#ffffff");
    assert.equal(body.nodes.m2.options.opacity, 1);
  });

  test("an edge whose type keeps its own options is written the slow way", () => {
    // The cheap edge path is an assumption about vis - that a colour is
    // resolved from options.color on every draw - and the node bug is what a
    // wrong assumption about vis costs. So it is checked at runtime, and an
    // edge that fails the check still gets painted, through setOptions.
    const v = loadViewer(catalogue());
    const body = fakeBody([], ["e1"]);
    const edge = body.edges.e1;
    edge.edgeType = { options: { color: { color: "#000000" } } };  // a copy, not a share
    const calls = [];
    const inner = edge.setOptions;
    edge.setOptions = function (o) { calls.push(o); return inner(o); };
    const ok = v.paintStyles({ body: body }, [],
      [{ id: "e1", color: { color: "#abcdef", highlight: "#abcdef", opacity: 0.4 } }]);
    assert.equal(ok, true);
    assert.equal(calls.length, 1, "it falls back rather than writing through");
    assert.equal(body.edges.e1.options.color.color, "#abcdef");
  });

  test("an edge whose type shares its options is written straight on", () => {
    const v = loadViewer(catalogue());
    const body = fakeBody([], ["e1"]);
    const calls = [];
    const inner = body.edges.e1.setOptions;
    body.edges.e1.setOptions = function (o) { calls.push(o); return inner(o); };
    v.paintStyles({ body: body }, [],
      [{ id: "e1", color: { color: "#abcdef", highlight: "#abcdef", opacity: 0.4 } }]);
    assert.equal(calls.length, 0, "no setOptions needed");
    assert.equal(body.edges.e1.options.color.color, "#abcdef");
    assert.equal(body.edges.e1.options.color.opacity, 0.4);
  });

  test("a vis it does not recognise is not half-painted", () => {
    // All or nothing: a canvas painted halfway is worse than one painted
    // slowly, so the shape is probed before a single write lands and the caller
    // falls back to the DataSet on a false.
    const v = loadViewer(catalogue());
    const nodes = [{ id: "m1", opacity: 0.5, font: { size: 3, color: "#111111" } }];
    const edges = [{ id: "e1", color: { color: "#222222", highlight: "#222222", opacity: 0.5 } }];

    assert.equal(v.paintStyles(null, nodes, edges), false, "no network");
    assert.equal(v.paintStyles({}, nodes, edges), false, "no body");
    assert.equal(
      v.paintStyles({ body: { nodes: {}, edges: {}, emitter: {} } }, nodes, edges),
      false, "no emitter.emit");

    const noSet = fakeBody(["m1"], ["e1"]);
    delete noSet.nodes.m1.setOptions;
    assert.equal(v.paintStyles({ body: noSet }, nodes, edges), false,
      "a node it cannot set options on");
    assert.equal(noSet.edges.e1.options.color.color, "#000000",
      "and nothing was written before it gave up");

    const noEdgeSet = fakeBody(["m1"], ["e1"]);
    delete noEdgeSet.edges.e1.setOptions;
    delete noEdgeSet.edges.e1.edgeType;
    assert.equal(v.paintStyles({ body: noEdgeSet }, nodes, edges), false,
      "an edge it cannot set options on");
    assert.equal(noEdgeSet.nodes.m1.options.opacity, 1,
      "and the nodes were not written either");
  });

  test("a node or edge that is gone is skipped rather than thrown over", () => {
    const v = loadViewer(catalogue());
    const body = fakeBody(["m1"], ["e1"]);
    const ok = v.paintStyles({ body: body },
      [{ id: "m1", opacity: 0.3, font: { size: 1, color: "#123456" } },
       { id: "gone", opacity: 1, font: { size: 12, color: "#ffffff" } }],
      [{ id: "e1", color: { color: "#abcdef", highlight: "#abcdef", opacity: 0.4 } },
       { id: "gone", color: { color: "#000000", highlight: "#000000", opacity: 1 } }]);
    assert.equal(ok, true);
    assert.equal(body.nodes.m1.labelModule.fontOptions.size, 1);
    assert.equal(body.edges.e1.options.color.color, "#abcdef");
  });

  test("the glide writes positions the same way, and not through moveNode", () => {
    // moveNode restarts vis's simulation, which is the thing the whole settle
    // arrangement exists to avoid. Physics is off by the time a glide runs, so
    // the position is simply the position, and x/y are plain properties with no
    // second copy anywhere - which is the difference from the font.
    const v = loadViewer(catalogue());
    const body = fakeBody(["m1", "m2"], []);
    assert.equal(v.paintPositions({ body: body }, [{ id: "m1", x: 5, y: -7 }]), true);
    assert.equal(body.nodes.m1.x, 5);
    assert.equal(body.nodes.m1.y, -7);
    assert.equal(body.nodes.m2.x, 0, "the node that is not moving does not move");
    assert.deepEqual(plain(body.emitter.emitted), ["_requestRedraw"]);
  });

  test("positions fall back rather than guess at an unfamiliar node", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.paintPositions(null, [{ id: "m1", x: 1, y: 2 }]), false);
    const body = fakeBody(["m1"], []);
    delete body.nodes.m1.x;
    assert.equal(v.paintPositions({ body: body }, [{ id: "m1", x: 1, y: 2 }]), false,
      "a node with no coordinate of its own");
  });

  test("both callers keep the DataSet path as their fallback", () => {
    // The payload is built once and used by whichever path runs, so the slow
    // one is exactly what the page did before and the fast one has nothing of
    // its own to get wrong.
    const src = viewerSource();
    assert.match(src, /if \(!paintStyles\(network, nodes, edges\)\) \{\s*\n\s*visNodes\.update\(nodes\);\s*\n\s*visEdges\.update\(edges\);/,
      "applyHighlight falls back to the DataSet");
    assert.match(src, /if \(!paintPositions\(network, start\)\) visNodes\.update\(start\);/,
      "the glide's first frame falls back");
    assert.match(src, /if \(!paintPositions\(network, step\)\) visNodes\.update\(step\);/,
      "and every frame after it");
  });

  test("nothing writes a node's font without going through setOptions", () => {
    // The shipped bug as a grep, because it is the kind of thing a later edit
    // reintroduces by writing the obvious line.
    const src = viewerSource();
    assert.doesNotMatch(src, /\.options\.font\.(size|color)\s*=/,
      "a direct font write leaves the label module holding the old value");
  });
});

// ---------------------------------------------------------------------------

describe("the edge pass draws what vis draws, without what vis charges for it", () => {
  // vis's own pass builds a fresh rgba() string per edge, assigns it to
  // strokeStyle - making the canvas parse a colour - and for a dashed edge does
  // a full ctx.save()/setLineDash/draw/setLineDash/restore. On this canvas
  // 11,752 of 12,835 edges are dashed, so that is 11,752 canvas state saves for
  // a picture with eight distinct line styles in it. Taking that out is what
  // made a frame affordable with nothing dropped: 26.8 ms to 14.9 ms at the
  // fitted view, and the edge pass itself about 19.5 ms to 7.5 ms.
  function ctxStub() {
    const ctx = {
      lineCap: "butt", strokeStyle: null, lineWidth: -1, dash: null,
      strokes: [], segments: 0, dashCalls: 0, styleWrites: 0, widthWrites: 0,
      setLineDash(d) { ctx.dashCalls++; ctx.dash = d.slice(); },
      beginPath() {}, moveTo(x, y) { ctx._m = [x, y]; ctx.segments++; },
      lineTo(x, y) { ctx._l = [x, y]; },
      stroke() {
        ctx.strokes.push({ style: ctx.strokeStyle, width: ctx.lineWidth,
                           dash: ctx.dash ? ctx.dash.join(",") : null,
                           from: ctx._m, to: ctx._l, cap: ctx.lineCap });
      },
    };
    // Count how often the expensive properties are actually written.
    let style = null, width = -1;
    Object.defineProperty(ctx, "strokeStyle", {
      get() { return style; },
      set(v) { ctx.styleWrites++; style = v; },
    });
    Object.defineProperty(ctx, "lineWidth", {
      get() { return width; },
      set(v) { ctx.widthWrites++; width = v; },
    });
    return ctx;
  }

  const node = (x, y) => ({ x: x, y: y });
  function edge(over) {
    return Object.assign({
      connected: true, selected: false, hover: false, chooser: true,
      from: node(0, 0), to: node(10, 10),
      draw() { this.drawnByVis = (this.drawnByVis || 0) + 1; },
      options: {
        color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.9, inherit: false },
        width: 2, dashes: false, selectionWidth: 2,
        shadow: { enabled: false }, background: { enabled: false },
        arrows: { to: false, from: false, middle: false },
      },
    }, over);
  }
  function net(edges, scale = 1) {
    const map = {}, ids = [];
    edges.forEach((e, i) => { map["e" + i] = e; ids.push("e" + i); });
    return { net: { body: { edges: map, view: { scale: scale } } }, ids: ids };
  }

  test("a colour becomes rgba once, however many edges share it", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.rgbaOf("#4da3ff", 0.9), "rgba(77,163,255,0.9)");
    assert.equal(v.rgbaOf("#000000", 0.06), "rgba(0,0,0,0.06)");
    assert.equal(v.rgbaOf("#fff", 1), "rgba(255,255,255,1)", "short form too");
  });

  test("a colour it cannot read hands the frame back rather than guessing", () => {
    // Every colour this page defines is hex. Anything else is something new,
    // and the right answer to something new on this path is vis.
    const v = loadViewer(catalogue());
    assert.equal(v.rgbaOf("rgb(1,2,3)", 1), null);
    assert.equal(v.rgbaOf("red", 1), null);
    assert.equal(v.rgbaOf("#12345", 1), null);
    assert.equal(v.rgbaOf(null, 1), null);
    const { net: n, ids } = net([edge({ options: Object.assign(edge().options,
      { color: { color: "red", highlight: "red", opacity: 1, inherit: false } }) })]);
    assert.equal(v.drawEdges(n, ctxStub(), ids), false);
  });

  test("one stroke per style, not per edge, so the overlap composites once", () => {
    // The load-bearing decision, and the reverse of what stood here before.
    // Alpha accumulates - n translucent lines over one pixel leave 1-(1-a)^n -
    // so at the old 0.06 a mere twenty overlaps reached 0.71 and the crowded
    // middle of the graph went solid, with the molecules and targets lost
    // underneath it. Lowering the opacity cannot fix that on its own: a hundred
    // overlaps still reach 0.78 at 0.015. Drawing each style once is what makes
    // a thousand crossing lines as faint as one.
    const v = loadViewer(catalogue());
    const { net: n, ids } = net([edge(), edge(), edge()]);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes.length, 1, "three edges of one style, one stroke");
  });

  test("every edge is still drawn, in its own style", () => {
    // Nothing is dropped, sampled or merged: what changed is how the overlap
    // composites, not which lines exist.
    const v = loadViewer(catalogue());
    const tinted = (hex, op) => edge({ options: Object.assign(edge().options,
      { color: { color: hex, highlight: hex, opacity: op, inherit: false } }) });
    const { net: n, ids } = net([tinted("#4da3ff", 0.06), tinted("#4da3ff", 0.06),
                                 tinted("#59c47a", 0.9), tinted("#4da3ff", 0.1)]);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes.length, 3, "three distinct styles");
    assert.equal(ctx.segments, 4, "but all four lines");
    const styles = ctx.strokes.map((x) => x.style).sort();
    assert.deepEqual(plain(styles), ["rgba(77,163,255,0.06)", "rgba(77,163,255,0.1)",
                                     "rgba(89,196,122,0.9)"]);
  });

  test("a colour is converted once however many edges share it", () => {
    const v = loadViewer(catalogue());
    const dim = () => edge({ options: Object.assign(edge().options,
      { color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.015, inherit: false } }) });
    const { net: n, ids } = net([dim(), dim(), dim(), dim()]);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.styleWrites, 1, "four identical edges, one colour write");
    assert.equal(ctx.widthWrites, 1);
    assert.equal(ctx.segments, 4);
  });

  test("a line is never thinner than vis draws it", () => {
    // Edge.getFormattingValues ends with width = max(width, 0.3 / scale), a
    // floor of 0.3 device pixels. At the fitted view, scale 0.11, a width-1
    // line is drawn at 2.7 - and missing that made the first version of this
    // thinner than the real thing on every single line, which is what 78,683
    // differing pixels looked like before it was found.
    const v = loadViewer(catalogue());
    const thin = edge({ options: Object.assign(edge().options, { width: 1 }) });
    const { net: n, ids } = net([thin], 0.1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    // vis's own arithmetic, written the same way rather than rounded: it
    // computes 0.3 / scale and so does this, floating-point tail and all.
    assert.equal(ctx.strokes[0].width, 0.3 / 0.1);

    const { net: n2, ids: ids2 } = net([edge({ options:
      Object.assign(edge().options, { width: 2 }) })], 1);
    const ctx2 = ctxStub();
    v.drawEdges(n2, ctx2, ids2);
    assert.equal(ctx2.strokes[0].width, 2, "above the floor, its own width");
  });

  test("a selected line is widened and takes its highlight colour", () => {
    // The fixture gives the two colours different values on purpose. On this
    // page edgeColorSpec sets highlight to the edge's own colour - deliberately,
    // so a selection says "this one" in weight rather than by repainting the
    // channel that carries the evidence - which means a fixture that shares
    // them asserts nothing about which one is read. It did, and a control that
    // broke the highlight lookup passed.
    const v = loadViewer(catalogue());
    const sel = edge({ selected: true });
    sel.options.color = { color: "#111111", highlight: "#222222",
                          opacity: 0.9, inherit: false };
    const { net: n, ids } = net([sel], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes[0].width, 4, "width 2 plus selectionWidth 2");
    assert.equal(ctx.strokes[0].style, "rgba(34,34,34,0.9)", "the highlight colour");

    const plain = edge();
    plain.options.color = { color: "#111111", highlight: "#222222",
                            opacity: 0.9, inherit: false };
    const { net: n2, ids: ids2 } = net([plain], 1);
    const ctx2 = ctxStub();
    v.drawEdges(n2, ctx2, ids2);
    assert.equal(ctx2.strokes[0].style, "rgba(17,17,17,0.9)",
      "and an unselected one takes its own");
  });

  test("the faintest style is drawn first, so the lit lines land on top", () => {
    // Drawing a style at a time reorders the canvas: where two lines of
    // different colours cross, which one is on top is decided here rather than
    // by the order vis happens to hold the edges in. An order decided by
    // accident is the part of that worth fixing, and by opacity is the one
    // ordering this page can defend - what the selection lit is what the
    // reader is looking at.
    const v = loadViewer(catalogue());
    const at = (op) => edge({ options: Object.assign(edge().options,
      { color: { color: "#4da3ff", highlight: "#4da3ff", opacity: op, inherit: false } }) });
    // Fed in the wrong order on purpose.
    const { net: n, ids } = net([at(0.9), at(0.06), at(0.1)], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    const opacities = ctx.strokes.map((x) => Number(x.style.split(",")[3].replace(")", "")));
    assert.deepEqual(plain(opacities), [0.06, 0.1, 0.9],
      "faintest first, the lit line last");
  });

  test("dashed and solid are different styles and stroke separately", () => {
    const v = loadViewer(catalogue());
    const dashed = () => edge({ options: Object.assign(edge().options, { dashes: true }) });
    const { net: n, ids } = net([dashed(), dashed(), edge()], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes.length, 2, "one dashed stroke, one solid");
    const dashes = ctx.strokes.map((x) => x.dash).sort();
    assert.deepEqual(plain(dashes), ["", "5,5"]);
    assert.equal(ctx.segments, 3, "all three lines");
  });

  test("the cap is round, which is what this canvas has always drawn", () => {
    const v = loadViewer(catalogue());
    const { net: n, ids } = net([edge()], 1);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    assert.equal(ctx.strokes[0].cap, "round");
  });

  test("an unconnected edge is skipped, the way vis skips it", () => {
    const v = loadViewer(catalogue());
    const { net: n, ids } = net([edge({ connected: false }), edge()], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes.length, 1);
  });

  test("a self-loop and a hovered edge go back to vis", () => {
    // A self-loop is a circle rather than a line, and hover is a third style
    // this does not write. Neither happens on this canvas; both are handed
    // back rather than assumed away.
    const v = loadViewer(catalogue());
    const shared = node(3, 4);
    const loop = edge({ from: shared, to: shared });
    const hovered = edge({ hover: true });
    const { net: n, ids } = net([loop, hovered], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    assert.equal(ctx.strokes.length, 0, "neither was drawn here");
    assert.equal(loop.drawnByVis, 1);
    assert.equal(hovered.drawnByVis, 1);
  });

  test("anything it does not implement sends the whole frame back to vis", () => {
    // Checked once against the first edge, not per edge: all of these are
    // global on this canvas, and a frame drawn half one way and half the other
    // is the failure mode with no upside.
    const v = loadViewer(catalogue());
    const variants = {
      "an inherited colour": (o) => { o.color.inherit = "from"; },
      "a shadow": (o) => { o.shadow.enabled = true; },
      "a background": (o) => { o.background.enabled = true; },
      "an arrow": (o) => { o.arrows.to = true; },
      "an arrow object": (o) => { o.arrows.to = { enabled: true }; },
    };
    for (const [name, wreck] of Object.entries(variants)) {
      const e = edge();
      wreck(e.options);
      const { net: n, ids } = net([e, edge()], 1);
      const ctx = ctxStub();
      assert.equal(v.drawEdges(n, ctx, ids), false, name);
      assert.equal(ctx.strokes.length, 0, name + ": and nothing was drawn first");
    }
    const chooser = edge({ chooser: function () {} });
    const { net: n2, ids: ids2 } = net([chooser], 1);
    assert.equal(v.drawEdges(n2, ctxStub(), ids2), false, "a chooser function");
  });

  test("a dash is drawn only where it can be seen", () => {
    // Chrome's GPU backend cannot dash on the GPU: it cuts every dashed line
    // into its dashes on the CPU. With 11,752 of 12,835 edges dashed that was
    // 83 ms a frame fitted and 50 at 1x, against 17 for the same lines solid.
    // Most of those dashes cannot be seen - too small below a few pixels a
    // period, too faint in the 0.015 haze - so those are drawn solid.
    const v = loadViewer(catalogue());
    assert.equal(v.dashIsVisible(1, 0.9), true, "a lit line at 1x: 10 px period");
    assert.equal(v.dashIsVisible(0.4, 0.9), true, "4 px period is the threshold");
    assert.equal(v.dashIsVisible(0.3, 0.9), false, "3 px: a pattern nobody resolves");
    assert.equal(v.dashIsVisible(0.12, 0.9), false, "the fitted view: 1.2 px");
    assert.equal(v.dashIsVisible(2, 0.015), false, "the haze: four shades of modulation");
    assert.equal(v.dashIsVisible(2, v.edgeOpacity(2)), false,
      "the second hop is background: brexpiprazole lights 3,192 of those lines");
    assert.equal(v.dashIsVisible(2, 0.22), false, "and so is the resting opacity");
  });

  test("a dash drawn solid keeps the coverage the pattern had", () => {
    // Round caps lengthen each 5-unit dash by the line's width, so a pattern
    // covers more than half its length. The solid line is drawn at that
    // fraction of the alpha, which is what the dashes averaged to.
    const v = loadViewer(catalogue());
    assert.equal(v.dashCoverage(1), 0.6);
    assert.equal(v.dashCoverage(2), 0.7);
    assert.equal(v.dashCoverage(9), 1, "never more than the solid line");
  });

  test("a faint dashed line is stroked solid at its averaged alpha", () => {
    const v = loadViewer(catalogue());
    const faint = edge({ options: Object.assign(edge().options, { dashes: true, width: 1,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.015, inherit: false } }) });
    const lit = edge({ options: Object.assign(edge().options, { dashes: true, width: 1,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.9, inherit: false } }) });
    const { net: n, ids } = net([faint, lit], 1);
    const ctx = ctxStub();
    assert.equal(v.drawEdges(n, ctx, ids), true);
    const byAlpha = new Map(ctx.strokes.map((x) =>
      [Number(x.style.split(",")[3].replace(")", "")), x]));
    // Solid at the pattern's coverage, and a hairline at that same alpha.
    const haze = byAlpha.get(0.015 * 0.6);
    assert.ok(haze, "found at " + [...byAlpha.keys()].join(", "));
    assert.equal(haze.dash, "", "the haze line, solid");
    assert.equal(haze.width, 0.9, "and a hairline");
    assert.equal(byAlpha.get(0.9).dash, "5,5", "the selection's line, still dashed");
  });

  test("a line too faint to read its width is a hairline at its own brightness", () => {
    // Chrome paints a line under a pixel wide on a fast path and anything
    // wider by outlining it. In software raster, eleven thousand 1.5-4 px haze
    // lines on screen in the middle zooms cost 100-200 ms a frame; as
    // hairlines, 33. A width nobody can see is not worth that. Brightness, not
    // ink, is what is kept: keeping ink made each line's core four times
    // brighter than the line it replaced.
    const v = loadViewer(catalogue());
    assert.equal(v.lineIsFaint(0.015), true, "the haze");
    assert.equal(v.lineIsFaint(v.edgeOpacity(2)), true,
                 "the second hop is drawn as background, however bright");
    assert.ok(v.edgeOpacity(2) >= 0.3,
              "and is bright enough to follow from a target to its molecules");
    assert.equal(v.lineIsFaint(0.22), true, "the resting opacity is background too");
    assert.equal(v.lineIsFaint(0.9), false, "the selection keeps its width");
    const faint = edge({ options: Object.assign(edge().options, { width: 2,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.015, inherit: false } }) });
    const lit = edge({ options: Object.assign(edge().options, { width: 2,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.9, inherit: false } }) });
    const { net: n, ids } = net([faint, lit], 2);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    const [thin, thick] = ctx.strokes;   // faintest first
    assert.equal(thin.width, 0.9 / 2, "0.9 device px at scale 2");
    assert.equal(thin.style, "rgba(77,163,255,0.015)", "at the alpha it had");
    assert.equal(thick.width, 2, "a visible line keeps its width");
  });

  test("a faint line already under the hairline is left as it is", () => {
    const v = loadViewer(catalogue());
    const faint = edge({ options: Object.assign(edge().options, { width: 1,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.015, inherit: false } }) });
    const { net: n, ids } = net([faint], 0.12);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    assert.equal(ctx.strokes[0].width, 0.3 / 0.12, "vis's own 0.3 px floor");
    assert.equal(ctx.strokes[0].style, "rgba(77,163,255,0.015)");
  });

  test("on a Retina screen the hairline is counted in device pixels", () => {
    // Every measurement behind the hairline was taken at DPR 1, where CSS and
    // device pixels are the same. At DPR 2 a "0.9 px" line was 1.8 device
    // pixels, off Skia's fast path: the faint bucket alone cost 427 ms of
    // painting a frame at 0.6x on a MacBook-sized window, and Safari on a Mac
    // was reported laggy at exactly that zoom.
    const v = loadViewer(catalogue());
    const at = (opacity) => edge({ options: Object.assign(edge().options, { width: 2,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: opacity, inherit: false } }) });
    const draw = (opacity, pr) => {
      const { net: n, ids } = net([at(opacity)], 1);
      if (pr) n.canvas = { pixelRatio: pr };
      const ctx = ctxStub();
      v.drawEdges(n, ctx, ids);
      const s = ctx.strokes[0];
      return { width: s.width, alpha: Number(s.style.split(",")[3].replace(")", "")) };
    };
    const haze = draw(0.015, 2);
    assert.equal(haze.width, 0.45, "0.9 device pixels at DPR 2");
    assert.equal(haze.alpha, 0.015, "the haze keeps its brightness, not its ink");
    // The second hop is the faint line a reader follows. The CSS-pixel rule
    // drew it 1.8 device pixels wide at 0.35; it keeps that ink.
    const echo = draw(v.edgeOpacity(2), 2);
    assert.equal(echo.width, 0.45);
    assert.ok(Math.abs(echo.alpha - v.edgeOpacity(2) * 2) < 1e-9,
      "alpha raised by the width it lost: " + echo.alpha);
    // And at DPR 1 nothing is different from what was measured there.
    assert.deepEqual(draw(v.edgeOpacity(2), 1), { width: 0.9, alpha: v.edgeOpacity(2) });
    assert.deepEqual(draw(v.edgeOpacity(2)), { width: 0.9, alpha: v.edgeOpacity(2) },
      "a canvas that does not say is DPR 1");
    assert.equal(draw(0.9, 2).width, 2, "a lit line keeps its width");
  });

  test("zoomed out, even the selection's dashes are drawn solid", () => {
    const v = loadViewer(catalogue());
    const lit = edge({ options: Object.assign(edge().options, { dashes: true, width: 1,
      color: { color: "#4da3ff", highlight: "#4da3ff", opacity: 0.9, inherit: false } }) });
    const { net: n, ids } = net([lit], 0.12);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    assert.equal(ctx.strokes[0].dash, "", "a 1.2 px period is not a pattern");
  });

  // A network with a window, so the edge pass can clip to it: 100 x 100 DOM
  // pixels mapped 1:1 onto canvas units.
  function windowed(edges, scale = 1) {
    const w = net(edges, scale);
    w.net.canvas = { frame: { canvas: { clientWidth: 100, clientHeight: 100 } } };
    w.net.DOMtoCanvas = (p) => ({ x: p.x, y: p.y });
    return w;
  }

  test("a line is stroked only where it crosses the window", () => {
    // Every line crossing the window used to be stroked end to end; with a
    // dashed one Chrome lays out every dash of it before clipping, and this
    // layout is hubs and spokes, so a kept line is typically thousands of
    // units long with a few dozen visible.
    const v = loadViewer(catalogue());
    const long = edge({ from: { x: -5000, y: 50 }, to: { x: 5000, y: 50 } });
    const { net: n, ids } = windowed([long]);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    const [x0] = ctx.strokes[0].from, [x1] = ctx.strokes[0].to;
    assert.ok(x0 >= -61 && x0 < 0, "starts just off the left of the window: " + x0);
    assert.ok(x1 > 100 && x1 <= 100 + 61, "ends just off the right: " + x1);
  });

  test("a clipped dashed line keeps its pattern where vis would have put it", () => {
    // The canvas starts each sub-path's pattern afresh, so a cut start is moved
    // back to the last whole period; otherwise the dashes on screen would
    // shift as the view moved, and read as the lines crawling.
    const v = loadViewer(catalogue());
    const long = edge({ from: { x: -5003, y: 50 }, to: { x: 5000, y: 50 },
      options: Object.assign(edge().options, { dashes: true, width: 1 }) });
    const { net: n, ids } = windowed([long]);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    assert.equal(ctx.strokes[0].dash, "5,5");
    const start = ctx.strokes[0].from[0];
    const along = start - (-5003);
    assert.ok(Math.abs(along / 10 - Math.round(along / 10)) < 1e-9,
      "starts a whole number of periods from the line's own start: " + along);
    assert.ok(start < 0, "and still before the window");
  });

  test("a line wholly in the window is drawn from its own end points", () => {
    // Not recomputed as from + d * t, which is not always bit-for-bit the same.
    const v = loadViewer(catalogue());
    const inside = edge({ from: { x: 10.1, y: 20.3 }, to: { x: 70.7, y: 80.9 } });
    const { net: n, ids } = windowed([inside]);
    const ctx = ctxStub();
    v.drawEdges(n, ctx, ids);
    assert.deepEqual(plain(ctx.strokes[0].from), [10.1, 20.3]);
    assert.deepEqual(plain(ctx.strokes[0].to), [70.7, 80.9]);
  });

  test("a network it cannot read is declined", () => {
    const v = loadViewer(catalogue());
    const { net: n, ids } = net([edge()], 1);
    assert.equal(v.drawEdges(null, ctxStub(), ids), false);
    assert.equal(v.drawEdges({}, ctxStub(), ids), false);
    assert.equal(v.drawEdges(n, null, ids), false, "no context");
    assert.equal(v.drawEdges({ body: { edges: {}, view: { scale: 0 } } },
      ctxStub(), []), false, "a scale of zero");
  });
});

describe("a condition can be searched for and opened", () => {
  // The indications turned the other way round: start from a disease and see
  // the molecules recorded for it and what they act on.
  function withConditions() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1", name: "ALPHA" }),
                  molecule({ id: 2, chembl_id: "CHEMBL2", name: "BETA" }),
                  molecule({ id: 3, chembl_id: "CHEMBL3", name: "GAMMA" })],
      targets: [target({ chembl_id: "T1", name: "Receptor one" }),
                target({ chembl_id: "T2", name: "Receptor two" }),
                target({ chembl_id: "T3", name: "Receptor three" })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" }),
               claim({ id: 2, molecule: 1, target: "T2" }),
               claim({ id: 3, molecule: 2, target: "T1" }),
               claim({ id: 4, molecule: 3, target: "T3" })],
      indications: {
        1: [["D1", "Epilepsy", "Approved", "core", 1, null]],
        2: [["D1", "Epilepsy", "Phase 2", "core", 0, "NCT00000001"],
            ["D1", "Epilepsy", "Phase 3", "core", 1, null]],
        3: [["D2", "Migraine <Disorders>", "Approved", "core", 1, null]],
      },
    });
  }

  test("search finds a condition by name and says how many molecules it has", () => {
    const v = loadViewer(withConditions());
    const r = v.searchCatalogue("epil");
    assert.equal(r.conditions.length, 1);
    assert.equal(r.conditions[0].condition.rows.length, 2, "one row per molecule");
    const html = v.searchResultsHTML(r);
    assert.match(html, /data-select="condition" data-id="D1"/);
    assert.match(html, /2 molecules · 1 approved for it/);
  });

  test("its panel lists the molecules by phase and the targets they share", () => {
    const v = loadViewer(withConditions());
    const html = v.showCondition(v.lookupCondition("D1"));
    assert.match(html, /Approved for it \(1\)/);
    assert.match(html, /Phase 3 \(1\)/, "a molecule sits at its furthest phase");
    assert.ok(!/Phase 2 \(/.test(html));
    assert.match(html, /data-select="target" data-id="T1">Receptor one[^]*?2 of these 2 molecules · 2 in the whole catalogue/);
    assert.ok(!/data-id="T2"/.test(html), "a target only one of them hits is not shared");
    assert.match(html, /not what it acts on/);
    assert.match(v.showCondition(v.lookupCondition("D2")), /Migraine &lt;Disorders&gt;/);
  });

  test("it lights its molecules and their targets, and nothing else", () => {
    const v = loadViewer(withConditions());
    const h = v.highlightFor("condition", "D1");
    assert.equal(h.nodes.get("m1"), 0);
    assert.equal(h.nodes.get("m2"), 0);
    assert.equal(h.nodes.get("tT1"), 1);
    assert.equal(h.nodes.get("m3"), undefined);
    assert.equal(v.highlightFor("condition", "NOPE"), null);
  });

  test("a disease on a molecule's panel opens the condition", () => {
    const v = loadViewer(withConditions());
    assert.match(v.showMolecule(v.lookupMolecule(1)),
                 /<a href="#" data-select="condition" data-id="D1">Epilepsy<\/a>/);
    const el = { getAttribute: (k) => ({ "data-select": "condition", "data-id": "D1" })[k] };
    v.onAppClick({ target: { closest: (sel) => (sel === "[data-select]" ? el : null) },
                   preventDefault() {} });
    assert.equal(v.getSelection().kind, "condition");
    assert.match(v.panelHTML(), /<h3>Epilepsy<\/h3>/);
  });
});

describe("a name stem can be searched for and opened", () => {
  // USAN/INN name stems, in ChEMBL's words: "-pramine" should find
  // quinupramine's family, and a stem should open its molecules. A class is how
  // a drug is filed and never evidence about a target. ATC classes were shown
  // for a day and taken back off (2026-09-26); an export that still carries
  // them must not put them back on the page.
  function withClasses() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1", name: "QUINUPRAMINE",
                             atc_level5: "N06AA23" }),
                  molecule({ id: 2, chembl_id: "CHEMBL2", name: "IMIPRAMINE" }),
                  molecule({ id: 3, chembl_id: "CHEMBL3", name: "DIAZEPAM" }),
                  molecule({ id: 4, chembl_id: "CHEMBL4", name: "FLUOXETINE" })],
      targets: [target({ chembl_id: "T1", name: "Serotonin transporter" }),
                target({ chembl_id: "T2", name: "GABA-A receptor" })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" }),
               claim({ id: 2, molecule: 2, target: "T1" }),
               claim({ id: 3, molecule: 3, target: "T2" })],
      classes: {
        labels: {
          atc: { N06A: [3, "ANTIDEPRESSANTS"],
                 N06AA: [4, "Non-selective monoamine reuptake inhibitors"] },
          usan: { "-pramine": [null, "antidepressants (imipramine type)"],
                  "-azepam": [null, null], "-oxetine": [null, "antidepressants (fluoxetine type)"] },
        },
        molecules: {
          1: [["atc", "N06AA23", null, "quinupramine"],
              ["usan", "-pramine", null, "antidepressants (imipramine type)"]],
          2: [["usan", "-pramine", null, "antidepressants (imipramine type)"]],
          3: [["usan", "-azepam", null, "antianxiety agents (diazepam type)"]],
          4: [["usan", "-oxetine", "-tioxetine",
               "antidepressants (fluoxetine type): thioether derivatives"]],
        },
      },
    });
  }

  test("ATC rows in the data are not indexed, searched or shown", () => {
    const v = loadViewer(withClasses());
    assert.equal(v.lookupClass("atc:N06A"), null);
    assert.equal(v.lookupClass("atc:N06AA"), null);
    assert.equal(v.searchCatalogue("antidepressants").classes
      .filter((c) => c.cls.source === "atc").length, 0);
    assert.equal(v.searchCatalogue("N06AA23").molecules.length, 0,
                 "an ATC code is not a search key any more");
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /<td>N06AA23<\/td>/, "the ATC row is the bare code again");
    assert.ok(!/data-id="atc:/.test(html));
  });

  test("a stem with no annotation of its own is named by its members", () => {
    const v = loadViewer(withClasses());
    assert.equal(v.className(v.lookupClass("usan:-azepam")),
                 "antianxiety agents (diazepam type)");
  });

  test("search finds a stem by what it stands for, and without its dash", () => {
    const v = loadViewer(withClasses());
    const keys = v.searchCatalogue("antidepress").classes.map((c) => c.cls.key);
    assert.ok(keys.includes("usan:-pramine") && keys.includes("usan:-oxetine"));
    assert.equal(v.searchCatalogue("pramine").classes[0].cls.key, "usan:-pramine");
    const html = v.searchResultsHTML(v.searchCatalogue("pramine"));
    assert.match(html, /data-select="class" data-id="usan:-pramine"/);
    assert.match(html, /name stem -<mark>pramine<\/mark> · 2 molecules/);
  });

  test("a molecule's panel names its stem and the stem opens", () => {
    const v = loadViewer(withClasses());
    assert.match(v.showMolecule(v.lookupMolecule(1)),
      /data-select="class" data-id="usan:-pramine">-pramine<\/a> <span class="muted">antidepressants \(imipramine type\)/);
  });

  test("its panel lists the molecules, their sub-stems and the shared targets", () => {
    const v = loadViewer(withClasses());
    const html = v.showClass(v.lookupClass("usan:-pramine"));
    assert.match(html, /<h3>antidepressants \(imipramine type\)<\/h3>/);
    assert.match(html, /Molecules[^]*?\(2\)/);
    assert.match(html, /data-select="target" data-id="T1">Serotonin transporter[^]*?2 of these 2 molecules/);
    assert.match(html, /says nothing about their targets/);
    assert.match(v.showClass(v.lookupClass("usan:-oxetine")),
                 /FLUOXETINE<div class="small muted">-tioxetine: antidepressants \(fluoxetine type\): thioether derivatives/);
  });

  test("it lights its molecules and their targets, and nothing else", () => {
    const v = loadViewer(withClasses());
    const h = v.highlightFor("class", "usan:-pramine");
    assert.equal(h.nodes.get("m1"), 0);
    assert.equal(h.nodes.get("m2"), 0);
    assert.equal(h.nodes.get("tT1"), 1);
    assert.equal(h.nodes.get("m3"), undefined);
    assert.equal(v.highlightFor("class", "usan:-nope"), null);
  });

  test("a class opened from a panel is selected, named and can be gone back from", () => {
    const v = loadViewer(withClasses());
    v.select("molecule", 1);
    const el = { getAttribute: (k) => ({ "data-select": "class", "data-id": "usan:-pramine" })[k] };
    v.onAppClick({ target: { closest: (sel) => (sel === "[data-select]" ? el : null) },
                   preventDefault() {} });
    assert.equal(v.getSelection().kind, "class");
    assert.equal(v.selectionName(v.getSelection()), "antidepressants (imipramine type)");
    assert.match(v.panelHTML(), /USAN\/INN name stem <b>-pramine<\/b>/);
    assert.ok(v.goBack());
    assert.equal(v.getSelection().kind, "molecule");
  });
});

describe("a MeSH pharmacological action can be searched for and opened", () => {
  // What NLM's indexers record a drug as doing, read from its MeSH record. An
  // action also holds the molecules filed under the narrower actions below it,
  // so "Antidepressive Agents" gathers the tricyclics and the SSRIs.
  function withActions() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL11", name: "IMIPRAMINE" }),
                  molecule({ id: 2, chembl_id: "CHEMBL629", name: "AMITRIPTYLINE" }),
                  molecule({ id: 3, chembl_id: "CHEMBL41", name: "FLUOXETINE" }),
                  molecule({ id: 4, chembl_id: "CHEMBL42", name: "CLOZAPINE" })],
      targets: [target({ chembl_id: "T1", name: "Serotonin transporter" }),
                target({ chembl_id: "T2", name: "Dopamine D2 receptor" })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" }),
               claim({ id: 2, molecule: 2, target: "T1" }),
               claim({ id: 3, molecule: 3, target: "T1" }),
               claim({ id: 4, molecule: 4, target: "T2" })],
      classes: {
        labels: {
          mesh_pa: {
            D002491: [4, "Central Nervous System Agents"],
            D011619: [5, "Psychotropic Drugs", ["D002491"]],
            D000928: [6, "Antidepressive Agents", ["D011619"]],
            D000929: [7, "Antidepressive Agents, Tricyclic", ["D000928"]],
            D017367: [6, "Serotonin Uptake Inhibitors", ["D011619", "D000928"]],
            D014150: [6, "Antipsychotic Agents", ["D011619"]],
          },
        },
        molecules: {
          1: [["mesh_pa", "D000929", null, "Antidepressive Agents, Tricyclic"]],
          2: [["mesh_pa", "D000929", null, "Antidepressive Agents, Tricyclic"]],
          3: [["mesh_pa", "D017367", null, "Serotonin Uptake Inhibitors"]],
          4: [["mesh_pa", "D014150", null, "Antipsychotic Agents"]],
        },
      },
    });
  }

  test("an action's panel does not add a sentence about NLM's indexers", () => {
    // Removed 2026-09-27, at the user's request: the MeSH link and the word
    // "pharmacological action" already say where the class comes from.
    const html = loadViewer(withActions()).showClass(
      loadViewer(withActions()).lookupClass("mesh_pa:D000929"));
    assert.match(html, /pharmacological action/);
    assert.ok(!/indexers/.test(html));
  });

  test("an action holds its own molecules and those of the actions below it, once", () => {
    const v = loadViewer(withActions());
    assert.equal(v.lookupClass("mesh_pa:D000929").members.size, 2);
    assert.equal(v.lookupClass("mesh_pa:D000928").members.size, 3, "tricyclics and the SSRI");
    assert.equal(v.lookupClass("mesh_pa:D011619").members.size, 4,
                 "reached by two paths, counted once");
    assert.ok(v.lookupClass("mesh_pa:D000928").children.has("mesh_pa:D000929"));
    assert.ok(!v.lookupClass("mesh_pa:D000928").members.has(4), "clozapine is not an antidepressant");
  });

  test("an action is listed before a name stem, whatever the match", () => {
    const data = withActions();
    const v = loadViewer(data);
    // A stem whose annotation starts with the query would otherwise win on
    // match rank alone.
    assert.equal(v.searchCatalogue("antidepress").classes[0].cls.source, "mesh_pa");
  });

  test("search finds an action by name, not by its descriptor id", () => {
    const v = loadViewer(withActions());
    assert.equal(v.searchCatalogue("tricyclic").classes[0].cls.key, "mesh_pa:D000929");
    assert.equal(v.searchCatalogue("D000929").classes.length, 0);
    assert.match(v.searchResultsHTML(v.searchCatalogue("tricyclic")),
                 /MeSH action · in Antidepressive Agents · 2 molecules/);
  });

  test("a molecule's panel names its actions and each opens", () => {
    const v = loadViewer(withActions());
    assert.match(v.showMolecule(v.lookupMolecule(1)),
      /Action \(MeSH\)[^]*?data-select="class" data-id="mesh_pa:D000929">Antidepressive Agents, Tricyclic<\/a>/);
  });

  test("its panel links MeSH, names what it sits inside, and what brought each molecule in", () => {
    const v = loadViewer(withActions());
    const html = v.showClass(v.lookupClass("mesh_pa:D000928"));
    assert.match(html, /meshb\.nlm\.nih\.gov\/record\/ui\?ui=D000928/);
    assert.match(html, /Inside <a href="#" data-select="class" data-id="mesh_pa:D011619">Psychotropic Drugs/);
    assert.match(html, /Narrower actions[^]*?data-id="mesh_pa:D000929"/);
    assert.match(html, /FLUOXETINE<div class="small muted">Serotonin Uptake Inhibitors · /);
    assert.match(html, /data-select="target" data-id="T1">Serotonin transporter[^]*?3 of these 3 molecules/);
    const own = v.showClass(v.lookupClass("mesh_pa:D000929"));
    assert.match(own, /IMIPRAMINE<div class="small muted">1 visible claim/,
                 "no reason is printed where the molecule is filed here directly");
  });

  test("it lights its molecules and their targets", () => {
    const v = loadViewer(withActions());
    const h = v.highlightFor("class", "mesh_pa:D000928");
    assert.equal(h.nodes.get("m3"), 0);
    assert.equal(h.nodes.get("tT1"), 1);
    assert.equal(h.nodes.get("m4"), undefined);
  });
});

describe("a MeSH structure class can be searched for and opened", () => {
  // What MeSH files a molecule as being built like, backfilled through FDA's
  // UNII. Caffeine is a xanthine, and Xanthines sits under two parents.
  // Theobromine is a xanthine whose own heading MeSH also files pentoxifylline
  // under, so it is a class too and theobromine is a member of it; the panel
  // says so rather than listing theobromine as a kind of itself.
  function withStructures() {
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
                  molecule({ id: 2, chembl_id: "CHEMBL1114", name: "THEOBROMINE" }),
                  molecule({ id: 3, chembl_id: "CHEMBL628", name: "PENTOXIFYLLINE" }),
                  molecule({ id: 4, chembl_id: "CHEMBL42", name: "CLOZAPINE" })],
      targets: [target({ chembl_id: "T1", name: "Adenosine receptor A1" }),
                target({ chembl_id: "T2", name: "Dopamine D2 receptor" })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" }),
               claim({ id: 2, molecule: 2, target: "T1" }),
               claim({ id: 3, molecule: 3, target: "T1" }),
               claim({ id: 4, molecule: 4, target: "T2" })],
      classes: {
        labels: {
          mesh_struct: {
            D000470: [2, "Alkaloids"],
            D011687: [4, "Purines"],
            D011688: [5, "Purinones", ["D011687"]],
            D014970: [3, "Xanthines", ["D000470", "D011688"]],
            D013805: [4, "Theobromine", ["D014970"]],
            D003984: [4, "Dibenzazepines"],
          },
          mesh_pa: { D058905: [5, "Purinergic P1 Receptor Antagonists"] },
        },
        molecules: {
          1: [["mesh_struct", "D014970", null, "Xanthines"],
              ["mesh_pa", "D058905", null, "Purinergic P1 Receptor Antagonists"]],
          2: [["mesh_struct", "D013805", null, "Theobromine"],
              ["mesh_struct", "D014970", null, "Xanthines"]],
          3: [["mesh_struct", "D013805", null, "Theobromine"]],
          4: [["mesh_struct", "D003984", null, "Dibenzazepines"]],
        },
        mesh_record: { 1: "D002110", 2: "D013805", 3: "D010431", 4: "D003024" },
      },
    });
  }

  test("a class holds its own molecules and those below it, once", () => {
    const v = loadViewer(withStructures());
    assert.equal(v.lookupClass("mesh_struct:D014970").members.size, 3,
                 "caffeine, theobromine, and pentoxifylline by way of Theobromine");
    assert.equal(v.lookupClass("mesh_struct:D011687").members.size, 3,
                 "reached through Purinones");
    assert.equal(v.lookupClass("mesh_struct:D000470").members.size, 3,
                 "and through Alkaloids, each counted once");
    assert.ok(v.lookupClass("mesh_struct:D014970").children.has("mesh_struct:D013805"));
    assert.ok(!v.lookupClass("mesh_struct:D014970").members.has(4));
  });

  test("search finds it by name, after an action and before a name stem", () => {
    const v = loadViewer(withStructures());
    assert.equal(v.searchCatalogue("xanthine").classes[0].cls.key, "mesh_struct:D014970");
    assert.equal(v.searchCatalogue("D014970").classes.length, 0,
                 "a descriptor id is no search key");
    assert.match(v.searchResultsHTML(v.searchCatalogue("xanthine")), /MeSH structure/);
    const order = v.searchCatalogue("purin").classes.map((c) => c.cls.source).join(",");
    assert.equal(order, "mesh_pa,mesh_struct,mesh_struct", "the action first, whatever the match");
  });

  test("a molecule's panel names its structure classes, never its own heading, and links its record", () => {
    const v = loadViewer(withStructures());
    const caffeine = v.showMolecule(v.lookupMolecule(1));
    assert.match(caffeine,
      /Structure \(MeSH\)[^]*?data-select="class" data-id="mesh_struct:D014970">Xanthines<\/a>/);
    assert.match(caffeine, /meshb\.nlm\.nih\.gov\/record\/ui\?ui=D002110/);
    const theobromine = v.showMolecule(v.lookupMolecule(2));
    const row = theobromine.match(/Structure \(MeSH\)[^]*?<\/tr>/)[0];
    assert.match(row, /mesh_struct:D014970/);
    assert.doesNotMatch(row, /data-id="mesh_struct:D013805"/, "not a kind of itself");
  });

  test("its panel links MeSH, names both parents, and what brought each molecule in", () => {
    const v = loadViewer(withStructures());
    const html = v.showClass(v.lookupClass("mesh_struct:D014970"));
    assert.match(html, /meshb\.nlm\.nih\.gov\/record\/ui\?ui=D014970/);
    assert.match(html, /chemical structure class/);
    assert.match(html, /Inside [^]*?mesh_struct:D000470[^]*?mesh_struct:D011688/);
    assert.match(html, /Narrower classes[^]*?data-id="mesh_struct:D013805"/);
    assert.match(html, /PENTOXIFYLLINE<div class="small muted">Theobromine · /);
    assert.match(html, /THEOBROMINE<div class="small muted">1 visible claim/,
                 "filed here directly; its own heading is not its route in");
    const own = v.showClass(v.lookupClass("mesh_struct:D013805"));
    assert.match(own, /THEOBROMINE<div class="small muted">its own heading · /);
    assert.match(own, /PENTOXIFYLLINE<div class="small muted">1 visible claim/);
  });

  test("its panel links the Wikipedia article an identifier reached, named by its title", () => {
    const data = withStructures();
    data.classes.wikipedia = { mesh_struct: {
      D014970: "https://en.wikipedia.org/wiki/Xanthine",
      D011687: "https://en.wikipedia.org/wiki/Benzylamine#Pharmacology_and_derivatives",
    } };
    const v = loadViewer(data);
    assert.match(v.showClass(v.lookupClass("mesh_struct:D014970")),
      /chemical structure class · <a href="https:\/\/en\.wikipedia\.org\/wiki\/Xanthine"[^>]*>Wikipedia: Xanthine<\/a>/);
    assert.match(v.showClass(v.lookupClass("mesh_struct:D011687")),
      />Wikipedia: Benzylamine § Pharmacology and derivatives<\/a>/,
      "a section is named as one");
    assert.doesNotMatch(v.showClass(v.lookupClass("mesh_struct:D003984")), /Wikipedia/,
      "a class no identifier reached has no link, rather than a guessed one");
    assert.doesNotMatch(loadViewer(withStructures()).showClass(
      loadViewer(withStructures()).lookupClass("mesh_struct:D014970")), /Wikipedia/,
      "a payload exported before the backfill shows none");
  });

  test("it lights its molecules and their targets, and an action is a separate class", () => {
    const v = loadViewer(withStructures());
    const h = v.highlightFor("class", "mesh_struct:D014970");
    assert.equal(h.nodes.get("m3"), 0);
    assert.equal(h.nodes.get("tT1"), 1);
    assert.equal(h.nodes.get("m4"), undefined);
    assert.equal(v.lookupClass("mesh_pa:D058905").members.size, 1,
                 "structure and action are never merged");
  });
});

describe("a gesture moves a picture of the scene rather than redrawing it", () => {
  // Safari on a Mac paints this canvas on the CPU at Retina resolution, and a
  // pan or a zoom used to repaint every line, node and name on every step. The
  // scene is now drawn once into a bitmap larger than the window, and a step of
  // a view gesture draws that bitmap under the new transform. At rest the page
  // draws exactly as it did. These hold the arithmetic, the fallbacks, and the
  // invalidation that keeps the bitmap from ever showing a stale scene.
  const cache = (over) => Object.assign({ valid: true, scale: 1, tx: 0, ty: 0,
    mx: 50, my: 40, w: 200, h: 160, cw: 100, ch: 80 }, over);
  const view = (scale, x = 0, y = 0) => ({ scale: scale, translation: { x: x, y: y } });

  test("the bitmap lands where the scene it holds now is", () => {
    const v = loadViewer(catalogue());
    const r = v.sceneCacheRect(cache(), view(1));
    assert.deepEqual(plain(r), { k: 1, ox: 0, oy: 0, left: -50, top: -40, right: 150, bottom: 120 });
    // A world point at c0 = W*s0 + t0 is at (c0 - t0)*k + t1 now: panned by
    // 30, the whole bitmap moves 30; zoomed 2x about the origin, it doubles.
    assert.equal(v.sceneCacheRect(cache(), view(1, 30, -10)).left, -20);
    assert.equal(v.sceneCacheRect(cache(), view(2)).right, 300);
    assert.equal(v.sceneCacheRect(cache({ tx: 10 }), view(2, 20)).ox, 0,
      "the translation it was drawn under is scaled out first");
  });

  test("a pan is a copy at whole device pixels, and anything else is drawn scaled", () => {
    // At a ratio of 1.5 a pointer moves the view by 2/3 of a device pixel, and
    // a bitmap drawn at a fractional offset is resampled through every pixel
    // of the window on every step: 10-13 ms a step in Firefox on Linux.
    const v = loadViewer(catalogue());
    const c = cache({ pr: 1.5 });
    const panned = v.sceneCacheRect(c, view(1, 10.333, -0.25));
    assert.deepEqual(plain(v.sceneCacheBlit(c, panned, 1.5)),
                     { x: Math.round((10.333 - 50) * 1.5), y: Math.round((-0.25 - 40) * 1.5) });
    assert.ok(Number.isInteger(v.sceneCacheBlit(c, panned, 1.5).x));
    assert.equal(v.sceneCacheBlit(c, v.sceneCacheRect(c, view(1.2)), 1.5), null, "zoomed");
    assert.equal(v.sceneCacheBlit(c, panned, 2), null, "drawn at less than the canvas's resolution");
  });

  test("it stands in for a frame only while it covers the window and still looks like it", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.sceneCacheUsable(cache(), view(1), 100, 80), true);
    assert.equal(v.sceneCacheUsable(cache(), view(1, 49, 39), 100, 80), true, "inside the margin");
    assert.equal(v.sceneCacheUsable(cache(), view(1, 51), 100, 80), false, "panned off its edge");
    assert.equal(v.sceneCacheUsable(cache(), view(1, -51), 100, 80), false, "the other edge");
    assert.equal(v.sceneCacheUsable(cache(), view(1.4), 100, 80), true, "magnified a little");
    assert.equal(v.sceneCacheUsable(cache(), view(1.6), 100, 80), false, "magnified past sharp");
    assert.equal(v.sceneCacheUsable(cache(), view(0.55), 100, 80), false, "shrunk past the scene");
    assert.equal(v.sceneCacheUsable(cache({ valid: false }), view(1), 100, 80), false, "stale");
    assert.equal(v.sceneCacheUsable(cache(), view(1), 120, 80), false, "a resized window");
    assert.equal(v.sceneCacheUsable(null, view(1), 100, 80), false);
  });

  // Enough of vis for the wrapper: a renderer whose _redraw records the
  // context and window it was handed, and a canvas element whose client size
  // lives on its prototype, as a real element's does.
  function fakeVis(v) {
    const screen = { drawn: [], at: [], clearRect() {}, save() {}, restore() {}, translate() {},
                     scale() {}, setTransform() {},
                     drawImage(img, x, y) { this.drawn.push(img); this.at.push([x, y]); } };
    const bitmaps = [];
    v.document.createElement = () => {
      const b = { width: 0, height: 0, ctx: { bitmap: true } };
      b.getContext = () => b.ctx;
      bitmaps.push(b);
      return b;
    };
    const el = Object.create({ clientWidth: 100, clientHeight: 80 });
    el.width = 200; el.height = 160;
    const emitter = { handlers: {}, on(k, f) { (this.handlers[k] = this.handlers[k] || []).push(f); } };
    const canvas = { pixelRatio: 2, frame: { canvas: el },
                     getContext() { return screen; }, setTransform() {} };
    const net = {
      canvas: canvas,
      body: { view: view(1), emitter: emitter },
      physics: { physicsEnabled: false },
      interactionHandler: { drag: { selection: [] } },
      on() {},
    };
    const renderer = {
      canvas: canvas, allowRedraw: true, dragging: false, zooming: false,
      redrawRequested: true, calls: [],
      _redraw() {
        this.calls.push({ ctx: canvas.getContext(), pr: canvas.pixelRatio,
                          w: el.clientWidth, h: el.clientHeight,
                          tx: net.body.view.translation.x, ty: net.body.view.translation.y });
      },
    };
    net.renderer = renderer;
    return { net, renderer, canvas, el, screen, bitmaps, emitter };
  }

  test("a vis it does not recognise is left to draw as it always has", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.installSceneCache(null), false);
    assert.equal(v.installSceneCache({}), false);
    for (const wreck of [(f) => { delete f.renderer._redraw; },
                         (f) => { delete f.canvas.setTransform; },
                         (f) => { delete f.net.body.view; },
                         (f) => { f.net.body.emitter = {}; }]) {
      const f = fakeVis(v);
      wreck(f);
      const before = f.renderer._redraw;
      assert.equal(v.installSceneCache(f.net), false);
      assert.equal(f.renderer._redraw, before, "and nothing was wrapped");
    }
  });

  test("a pan draws the scene once and then moves the picture", () => {
    const v = loadViewer(catalogue());
    const f = fakeVis(v);
    assert.equal(v.installSceneCache(f.net), true);
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 1, "at rest vis draws the frame");
    assert.equal(f.renderer.calls[0].ctx, f.screen, "onto the screen");

    f.renderer.dragging = true;
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 2, "the first step draws the scene...");
    const build = f.renderer.calls[1];
    assert.ok(build.ctx.bitmap, "...into the bitmap");
    assert.deepEqual([build.w, build.h], [300, 240], "over the window and its margin");
    assert.deepEqual([build.tx, build.ty], [100, 80], "shifted so the margin is drawn too");
    assert.equal(build.pr, 2, "at the canvas's own resolution");
    assert.deepEqual([f.bitmaps[0].width, f.bitmaps[0].height], [600, 480]);
    // Everything swapped for the build is put back.
    assert.equal(f.el.clientWidth, 100);
    assert.equal(f.el.clientHeight, 80);
    assert.equal(f.canvas.getContext(), f.screen);
    assert.equal(f.canvas.pixelRatio, 2);
    assert.deepEqual(plain(f.net.body.view.translation), { x: 0, y: 0 });
    assert.equal(f.screen.drawn.length, 1, "and the step shows the bitmap");

    f.net.body.view.translation.x = 20;
    f.renderer.redrawRequested = true;
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 2, "later steps do not draw the scene");
    assert.equal(f.screen.drawn.length, 2, "they move the picture");
    assert.deepEqual(f.screen.at[1], [-160, -160],
      "copied whole, in device pixels: the margin back and the pan forward, at 2x");
    assert.equal(f.renderer.redrawRequested, false,
      "and clear vis's request flag, or vis would never ask for another frame");
  });

  test("a zoom rebuilds with only the margin its direction needs", () => {
    // Zoomed in, the margin is most of what a rebuild costs - 128 ms against
    // 50 at 2.5x in Firefox on Linux - and a zoom crosses a rebuild every four
    // or five wheel clicks.
    const v = loadViewer(catalogue());
    assert.equal(v.sceneCacheZoomMargin(1, 1.6), 0, "magnified about a point in the window, it still covers it");
    assert.ok(Math.abs(v.sceneCacheZoomMargin(1, 0.9) - 1 / 3) < 1e-9, "down to 0.6x about the middle");
    assert.equal(v.sceneCacheZoomMargin(undefined, 1), null);

    const f = fakeVis(v);
    v.installSceneCache(f.net);
    f.renderer.dragging = true;
    f.renderer._redraw();                       // a pan's bitmap, at 1x
    f.renderer.dragging = false;
    f.renderer.zooming = true;
    f.net.body.view.scale = 1.6;                // past sharp: rebuilt
    f.renderer._redraw();
    const zin = f.renderer.calls[f.renderer.calls.length - 1];
    assert.deepEqual([zin.w, zin.h], [100, 80], "zooming in, no margin");
    v.sceneChanged();
    f.net.body.view.scale = 1.2;
    f.renderer._redraw();
    const zout = f.renderer.calls[f.renderer.calls.length - 1];
    assert.deepEqual([zout.w, zout.h], [166, 133],
      "zooming out, a third of the window in whole device pixels each side");
    f.renderer.zooming = false;
    f.renderer.dragging = true;
    v.sceneChanged();
    f.renderer._redraw();
    const pan = f.renderer.calls[f.renderer.calls.length - 1];
    assert.deepEqual([pan.w, pan.h], [300, 240], "and a pan gets the whole margin");
  });

  test("anything that changes the scene throws the bitmap away", () => {
    const v = loadViewer(catalogue());
    const f = fakeVis(v);
    v.installSceneCache(f.net);
    f.renderer.dragging = true;
    f.renderer._redraw();
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 1);
    v.sceneChanged();
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 2, "a paint mid-gesture redraws the scene");
    for (const ev of ["_dataChanged", "_dataUpdated"]) {
      f.emitter.handlers[ev].forEach((h) => h());
      f.renderer._redraw();
    }
    assert.equal(f.renderer.calls.length, 4, "and so does a DataSet write");

    // The crisp frame vis draws when a gesture ends changes nothing...
    f.renderer.dragging = false;
    f.renderer._redraw();
    f.renderer.dragging = true;
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 5, "...so the next gesture reuses the bitmap");
    // ...but any other resting frame might be vis changing something itself,
    // such as a click selecting a node.
    f.renderer.dragging = false;
    f.renderer._redraw();
    f.renderer._redraw();
    f.renderer.dragging = true;
    f.renderer._redraw();
    assert.equal(f.renderer.calls.length, 8, "so it expires the bitmap");
  });

  test("dragging a node, a selection box or a running layout is drawn by vis", () => {
    const v = loadViewer(catalogue());
    for (const [name, set] of [
      ["a node being dragged", (f) => { f.net.interactionHandler.drag.selection = [{}]; }],
      ["a selection box", (f) => { f.net.body.selectionBox = { show: true }; }],
      ["physics on", (f) => { f.net.physics.physicsEnabled = true; }],
    ]) {
      const f = fakeVis(v);
      v.installSceneCache(f.net);
      set(f);
      f.renderer.dragging = true;
      f.renderer._redraw();
      f.renderer._redraw();
      assert.equal(f.renderer.calls.length, 2, name + ": every frame drawn");
      assert.ok(f.renderer.calls.every((c) => c.ctx === f.screen), name + ": on screen");
    }
  });

  test("every path on the page that repaints the scene says so", () => {
    // The paint paths write onto vis's objects and ask for a redraw directly,
    // bypassing the DataSet events the wrapper also listens to. A new one that
    // forgets to call sceneChanged would leave a stale picture on screen for
    // the length of a gesture.
    const lines = viewerSource().split("\n");
    const asks = [];
    lines.forEach((l, i) => { if (/emit\("_requestRedraw"\)/.test(l)) asks.push(i); });
    assert.ok(asks.length >= 2, "found " + asks.length);
    for (const i of asks) {
      assert.match(lines[i - 1], /sceneChanged\(\);/, "line " + (i + 1) + ": " + lines[i].trim());
    }
  });
});

// A family, complex group or complex is a target of its own and so are its
// proteins, and on the canvas they were five unrelated lines. The membership
// lines say how they relate - and must say
// nothing else: no count, no hop, no score may see them.
describe("a group is joined to its own proteins on the canvas", () => {
  // A molecule at the family and one member, and a second reaching the other
  // member and not the family - istradefylline at A2A, the case a lit line
  // must not claim.
  function selectiveCatalogue() {
    const comps = [
      { accession: "P30542", gene_symbol: "ADORA1", description: "Adenosine receptor A1" },
      { accession: "P29274", gene_symbol: "ADORA2A", description: "Adenosine receptor A2a" },
    ];
    return buildData({
      molecules: [
        molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
        molecule({ id: 3, chembl_id: "CHEMBL_IST", name: "ISTRADEFYLLINE" }),
      ],
      targets: [
        target({ chembl_id: "T_A1", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "T_A2A", n_components: 1, components: [comps[1]] }),
        target({ chembl_id: "T_FAM", name: "Adenosine receptor",
                 target_type: "PROTEIN FAMILY", n_components: 2, components: comps }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "T_A1" }),
        claim({ id: 2, molecule: 1, target: "T_FAM" }),
        claim({ id: 3, molecule: 3, target: "T_A2A" }),
      ],
    });
  }

  test("a family is joined to each of its proteins that is drawn", () => {
    const v = loadViewer(familyCatalogue());
    const links = plain(v.catalogueGraph().links).map((k) => k.from + ">" + k.to).sort();
    assert.deepEqual(links, ["tT_FAM>tT_A1", "tT_FAM>tT_A2A"]);
  });

  test("the lines are not edges: counts, hops and the ranking cannot see them", () => {
    const linked = loadViewer(familyCatalogue());
    const separate = loadViewer(familyCatalogue());
    separate.setFilter("groups", "separate");
    assert.equal(plain(separate.catalogueGraph().links).length, 0);
    assert.deepEqual(plain(linked.catalogueGraph().edges).map((e) => e.id),
                     plain(separate.catalogueGraph().edges).map((e) => e.id));
    const ids = new Set(plain(linked.catalogueGraph().links).map((k) => k.id));
    for (const e of plain(linked.catalogueGraph().edges)) assert.ok(!ids.has(e.id));
    const h = linked.highlightFor("molecule", 1);
    for (const id of h.edges.keys()) assert.ok(!ids.has(id), "hop over " + id);
    assert.deepEqual(plain(linked.sharedTargets(1)), plain(separate.sharedTargets(1)));
    assert.deepEqual(plain(linked.mechanismLegendRows()), plain(separate.mechanismLegendRows()));
  });

  test("the setting re-solves the layout, since the lines are springs", () => {
    const v = loadViewer(familyCatalogue());
    const before = v.graphSignature();
    v.setFilter("groups", "separate");
    assert.notEqual(v.graphSignature(), before);
  });

  test("no line to a protein that is not drawn", () => {
    const d = selectiveCatalogue();
    const v = loadViewer(d);
    v.setFilter("periphery", "hide");
    // Each target has one molecule, so hiding the periphery takes all three
    // off - and their lines with them.
    assert.equal(plain(v.catalogueGraph().links).length, 0);
  });

  test("two single-protein records of one accession are one node, which the group joins", () => {
    // They are one protein, so one node (2026-10-10), and joining the group to
    // that node picks neither record over the other.
    const comps = [
      { accession: "P1", gene_symbol: "A" }, { accession: "P2", gene_symbol: "B" },
    ];
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [
        target({ chembl_id: "HUMAN", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "OTHER", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "FAM", target_type: "PROTEIN FAMILY", n_components: 2,
                 components: comps }),
      ],
      claims: [claim({ id: 1, molecule: 1, target: "HUMAN" }),
               claim({ id: 2, molecule: 1, target: "OTHER" }),
               claim({ id: 3, molecule: 1, target: "FAM" })],
    }));
    const g = v.catalogueGraph();
    assert.deepEqual(plain(g.nodes).filter((n) => n.kind === "target").map((n) => n.key).sort(),
                     ["tFAM", "tHUMAN"]);
    assert.deepEqual(plain(g.links).map((k) => k.from + ">" + k.to), ["tFAM>tHUMAN"]);
  });

  test("an accession held by records drawn as two nodes joins neither", () => {
    // A single protein and a one-component record of another type are not
    // folded together, so naming one of them would be the guess invariant 6
    // refuses.
    const comps = [
      { accession: "P1", gene_symbol: "A" }, { accession: "P2", gene_symbol: "B" },
    ];
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 })],
      targets: [
        target({ chembl_id: "HUMAN", n_components: 1, components: [comps[0]] }),
        target({ chembl_id: "OTHER", target_type: "PROTEIN COMPLEX", n_components: 1,
                 components: [comps[0]] }),
        target({ chembl_id: "FAM", target_type: "PROTEIN FAMILY", n_components: 2,
                 components: comps }),
      ],
      claims: [claim({ id: 1, molecule: 1, target: "HUMAN" }),
               claim({ id: 2, molecule: 1, target: "OTHER" }),
               claim({ id: 3, molecule: 1, target: "FAM" })],
    }));
    assert.deepEqual(plain(v.catalogueGraph().links), []);
  });

  test("a selection lights the lines between two of its own targets, and dims the rest", () => {
    const v = loadViewer(selectiveCatalogue());
    v.setSelection("molecule", 1);
    const o = v.highlightOpacity();
    const byTo = new Map(plain(v.catalogueGraph().links).map((k) => [k.to, k.id]));
    assert.equal(o.links.get(byTo.get("tT_A1")), v.KEPT_LINK_OPACITY ?? 0.6);
    // Caffeine reaches the family and A1, not A2A: that line is not its own.
    assert.ok(o.links.get(byTo.get("tT_A2A")) < 0.1);
    // A target selection lights molecules, never a second target, so no line.
    v.setSelection("target", "T_FAM");
    const t = v.highlightOpacity();
    for (const x of t.links.values()) assert.ok(x < 0.1);
  });

  test("the canvas gets the lines styled as structure, and a click on one opens the group", () => {
    const v = loadViewer(selectiveCatalogue());
    v.select("molecule", 1);
    const net = v.__networks[0];
    const rows = net.data.edges.rows.filter((r) => String(r.id).startsWith("k"));
    assert.equal(rows.length, 2);
    for (const r of rows) {
      assert.equal(r.color.color, "#ffd9a8");
      assert.equal(r.dashes, false, "a dash means Preliminary");
      assert.equal(r.width, 1, "width means Supported");
      assert.equal(r.selectionWidth, 0);
    }
    net.handlers.click({ nodes: [], edges: [rows[0].id] });
    assert.equal(v.getSelection().kind, "target");
    assert.equal(v.getSelection().id, "T_FAM");
  });

  test("the legend names the lines as structure only while they are drawn", () => {
    const v = loadViewer(familyCatalogue());
    assert.ok(plain(v.legendRows()).some((b) => b[0] === "Protein groups"));
    v.setFilter("groups", "separate");
    assert.ok(!plain(v.legendRows()).some((b) => b[0] === "Protein groups"));
  });
});

// Ion-channel assemblies are laid out as one unit: the subunits of a GABA-A or
// NMDA receptor never work apart, so they are packed with their complexes into
// one disc, while each keeps its own node and its own lines. Only ion channels
// - ChEMBL's PROTEIN COMPLEX also covers kinase pairs and receptor heteromers
// whose parts do work alone - and only placement: nothing counted may move.
describe("an ion-channel assembly is laid out as one unit", () => {
  const LGIC = "Ion channel > Ligand-gated ion channel";
  const AUX = "Auxiliary transport protein > Calcium channel auxiliary subunit beta family";
  const comp = (acc, sym, cls) => ({ accession: acc, gene_symbol: sym, protein_class: cls });
  const A1 = comp("PA1", "GABRA1", LGIC), B2 = comp("PB2", "GABRB2", LGIC),
        B3 = comp("PB3", "GABRB3", LGIC), G2 = comp("PG2", "GABRG2", LGIC),
        JAK1 = comp("PJ1", "JAK1", "Enzyme > Kinase"), JAK3 = comp("PJ3", "JAK3", "Enzyme > Kinase");
  function unitCatalogue() {
    return buildData({
      molecules: [molecule({ id: 1, name: "DIAZEPAM" }), molecule({ id: 2, name: "ZOLPIDEM" }),
                  molecule({ id: 3, name: "TOFACITINIB" })],
      targets: [
        target({ chembl_id: "S_A1", n_components: 1, components: [A1] }),
        target({ chembl_id: "S_B3", n_components: 1, components: [B3] }),
        target({ chembl_id: "S_J1", n_components: 1, components: [JAK1] }),
        target({ chembl_id: "S_J3", n_components: 1, components: [JAK3] }),
        target({ chembl_id: "C_122", name: "GABA-A a1b2g2", target_type: "PROTEIN COMPLEX",
                 n_components: 3, components: [A1, B2, G2] }),
        target({ chembl_id: "C_132", name: "GABA-A a1b3g2", target_type: "PROTEIN COMPLEX",
                 n_components: 3, components: [A1, B3, G2] }),
        target({ chembl_id: "G_GABA", name: "GABA-A receptor", target_type: "PROTEIN COMPLEX GROUP",
                 n_components: 4, components: [A1, B2, B3, G2] }),
        target({ chembl_id: "F_GABA", name: "GABA-A alpha family", target_type: "PROTEIN FAMILY",
                 n_components: 1 + 1, components: [A1, comp("PA5", "GABRA5", LGIC)] }),
        target({ chembl_id: "C_JAK", name: "JAK1/JAK3", target_type: "PROTEIN COMPLEX",
                 n_components: 2, components: [JAK1, JAK3] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "C_122" }),
        claim({ id: 2, molecule: 1, target: "C_132" }),
        claim({ id: 3, molecule: 1, target: "G_GABA" }),
        claim({ id: 4, molecule: 1, target: "S_A1" }),
        claim({ id: 5, molecule: 1, target: "S_B3" }),
        claim({ id: 6, molecule: 2, target: "S_A1" }),
        claim({ id: 7, molecule: 2, target: "F_GABA" }),
        claim({ id: 8, molecule: 3, target: "C_JAK" }),
        claim({ id: 9, molecule: 3, target: "S_J1" }),
        claim({ id: 10, molecule: 3, target: "S_J3" }),
      ],
    });
  }

  test("protein_class travels as a component's fourth field, and is null without it", () => {
    const v = loadViewer(unitCatalogue());
    assert.equal(v.lookupTarget("S_A1").components[0].protein_class, LGIC);
    const bare = loadViewer(catalogue());
    assert.equal(bare.lookupTarget("CHEMBLT1").components.length, 0);
    const old = loadViewer(buildData({ targets: [target({ chembl_id: "X", components: [
      { accession: "P", gene_symbol: "G" }] })] }));
    assert.equal(old.lookupTarget("X").components[0].protein_class, null);
  });

  test("only a complex of ion-channel subunits is a channel assembly", () => {
    const v = loadViewer(unitCatalogue());
    assert.equal(v.channelAssembly(v.lookupTarget("C_122")), true);
    assert.equal(v.channelAssembly(v.lookupTarget("G_GABA")), true, "complex groups too");
    assert.equal(v.channelAssembly(v.lookupTarget("C_JAK")), false, "kinases work alone");
    assert.equal(v.channelAssembly(v.lookupTarget("F_GABA")), false, "a family is paralogues");
    assert.equal(v.channelAssembly(v.lookupTarget("S_A1")), false);
    const t = (comps) => ({ target_type: "PROTEIN COMPLEX", components: comps });
    assert.equal(v.channelAssembly(t([A1, comp("X", "CACNB1", AUX)])), true,
                 "a channel's auxiliary subunit belongs with it");
    assert.equal(v.channelAssembly(t([comp("X", "a", AUX), comp("Y", "b", AUX)])), false,
                 "auxiliaries alone are not a channel");
    assert.equal(v.channelAssembly(t([A1, comp("X", "ITGA5", null)])), false,
                 "an unclassified component is not assumed to be a channel's");
  });

  test("assemblies sharing a subunit are one unit, packed groups first and subunits last", () => {
    const v = loadViewer(unitCatalogue());
    const units = plain(v.catalogueGraph().units);
    assert.equal(units.length, 1, "the JAK complex is not a unit");
    assert.deepEqual(units[0].nodes, ["tG_GABA", "tC_122", "tC_132", "tS_A1", "tS_B3"]);
    assert.equal(units[0].key, "u:tG_GABA");
  });

  test("lines inside a unit give way to the disc; a family's line into it stays", () => {
    const v = loadViewer(unitCatalogue());
    const links = plain(v.catalogueGraph().links).map((k) => k.from + ">" + k.to).sort();
    assert.deepEqual(links, ["tC_JAK>tS_J1", "tC_JAK>tS_J3", "tF_GABA>tS_A1"]);
  });

  test("nothing counted changes: the same edges, hops and ranking with units or without", () => {
    const linked = loadViewer(unitCatalogue());
    const separate = loadViewer(unitCatalogue());
    separate.setFilter("groups", "separate");
    assert.equal(plain(separate.catalogueGraph().units).length, 0);
    assert.deepEqual(plain(linked.catalogueGraph().edges).map((e) => e.id + e.from + e.to),
                     plain(separate.catalogueGraph().edges).map((e) => e.id + e.from + e.to));
    for (const id of [1, 2, 3]) {
      assert.deepEqual(plain(linked.sharedTargets(id)), plain(separate.sharedTargets(id)));
      assert.deepEqual(plain([...linked.highlightFor("molecule", id).nodes]),
                       plain([...separate.highlightFor("molecule", id).nodes]));
    }
  });

  test("the physics sees a unit as one body, pulled once per neighbour", () => {
    const v = loadViewer(unitCatalogue());
    const g = v.catalogueGraph();
    const plan = v.physicsPlan(g);
    assert.deepEqual(plain(plan.anchors).map((a) => [a.id, a.hidden, a.physics]),
                     [["u:tG_GABA", true, true]]);
    assert.ok(plan.anchors[0].mass > 1 && plan.anchors[0].size > 16);
    assert.deepEqual([...plan.frozenNodes].sort(),
                     ["tC_122", "tC_132", "tG_GABA", "tS_A1", "tS_B3"]);
    // Diazepam reaches five of the unit's nodes and pulls on it once; zolpidem
    // once, and its family once through the family's line into the unit.
    const pairs = plain(plan.proxies).map((p) => [p.from, p.to].sort().join("|")).sort();
    assert.deepEqual(pairs, ["m1|u:tG_GABA", "m2|u:tG_GABA", "tF_GABA|u:tG_GABA"]);
    assert.ok(plan.proxies.every((p) => p.hidden && p.physics));
    // Every real line touching the unit is drawn and carries no spring.
    const touching = plain(g.edges.concat(g.links)).filter((e) =>
      plan.frozenNodes.has(e.from) || plan.frozenNodes.has(e.to)).map((e) => e.id).sort();
    assert.deepEqual([...plan.frozenEdges].sort(), touching);
  });

  test("the packing holds the unit's nodes, and only them, clear of other discs", () => {
    const v = loadViewer(unitCatalogue());
    const g = v.catalogueGraph();
    const pos = { "u:tG_GABA": { x: 0, y: 0 }, m1: { x: 5, y: 5 }, m2: { x: 400, y: 0 },
                  tF_GABA: { x: -3, y: 2 } };
    const rows = plain(v.unitPlacement(g, pos));
    const at = Object.fromEntries(rows.map((r) => [r.id, r]));
    const unit = g.units[0];
    let r = 0;
    for (const k of unit.nodes) r = Math.max(r, Math.hypot(at[k].x, at[k].y));
    assert.deepEqual([at.tG_GABA.x, at.tG_GABA.y], [0, 0], "first node at the centre");
    // Two nodes that were sitting where the disc now is are moved out past it.
    for (const k of ["m1", "tF_GABA"]) {
      assert.ok(at[k], k + " moved");
      assert.ok(Math.hypot(at[k].x, at[k].y) >= r, k + " is outside the disc");
    }
    assert.equal(at.m2, undefined, "a node already clear is left where it is");
  });

  test("two overlapping discs are moved apart, the smaller one moving", () => {
    const v = loadViewer(buildData({}));
    const u = (key, n) => ({ key: key, nodes: Array.from({ length: n }, (_, i) => key + i) });
    const g = { units: [u("u:big", 9), u("u:small", 3)], nodes: [] };
    const rows = plain(v.unitPlacement(g, { "u:big": { x: 0, y: 0 }, "u:small": { x: 10, y: 0 } }));
    const at = Object.fromEntries(rows.map((r) => [r.id, r]));
    assert.deepEqual([at["u:big"].x, at["u:big"].y], [0, 0]);
    assert.ok(at["u:small"].x > 100, "moved clear along the line between them");
  });

  test("vis's overlap avoidance stays off: it set the crowded middle in rows and columns", () => {
    const v = loadViewer(buildData({}));
    for (const initial of [true, false]) {
      assert.equal(v.graphOptions(initial).physics.barnesHut.avoidOverlap, 0);
    }
  });

  test("crowded nodes are spaced along the line between them; a node with room is not moved", () => {
    const v = loadViewer(buildData({}));
    const pts = [{ key: "a", x: 0, y: 0 }, { key: "b", x: 10, y: 0 },
                 { key: "c", x: 100, y: 100 }, { key: "d", x: 100, y: 100 },
                 { key: "e", x: 900, y: 900 }];
    const at = Object.fromEntries(plain(v.spreadNodes(pts.map((p) => Object.assign({}, p)), []))
      .map((p) => [p.key, p]));
    const gap = (p, q) => Math.hypot(at[p].x - at[q].x, at[p].y - at[q].y);
    assert.ok(gap("a", "b") >= 31, "a and b spaced");
    assert.ok(Math.abs(at.a.y) < 1e-9 && Math.abs(at.b.y) < 1e-9, "along their own line, not across it");
    assert.ok(gap("c", "d") >= 31, "two on one spot are parted");
    // ...at an angle of their own, never along an axis, which is the grid this replaced.
    const dx = Math.abs(at.c.x - at.d.x), dy = Math.abs(at.c.y - at.d.y);
    assert.ok(dx > 1 && dy > 1, "parted off-axis");
    assert.ok(!at.e.moved);
    assert.deepEqual([at.e.x, at.e.y], [900, 900]);
  });

  test("a canvas with no units is spaced all the same", () => {
    const v = loadViewer(buildData({}));
    const g = { units: [], nodes: [{ key: "m1" }, { key: "m2" }, { key: "m3" }] };
    const rows = plain(v.unitPlacement(g, { m1: { x: 0, y: 0 }, m2: { x: 0, y: 4 },
                                            m3: { x: 400, y: 0 } }));
    assert.deepEqual(rows.map((r) => r.id).sort(), ["m1", "m2"]);
    const [p, q] = rows;
    assert.ok(Math.hypot(p.x - q.x, p.y - q.y) >= 31);
  });

  test("vis is handed small frozen nodes, a hidden anchor, hidden springs and a disc painter", () => {
    const v = loadViewer(unitCatalogue());
    v.select("molecule", 1);
    const net = v.__networks[0];
    const nodes = Object.fromEntries(net.data.nodes.rows.map((r) => [r.id, r]));
    assert.equal(nodes.tS_A1.physics, false);
    assert.ok(nodes.tS_A1.size < nodes.tS_J1.size, "a unit's nodes are the smaller ones");
    assert.equal(nodes["u:tG_GABA"].hidden, true);
    const proxies = net.data.edges.rows.filter((r) => String(r.id).startsWith("p"));
    assert.equal(proxies.length, 3);
    assert.ok(proxies.every((r) => r.hidden));
    for (const h of ["beforeDrawing", "dragStart", "dragging", "dragEnd"]) {
      assert.equal(typeof net.handlers[h], "function", h);
    }
  });

  test("dragging any node of a unit moves the whole unit by the pointer's travel", () => {
    const v = loadViewer(unitCatalogue());
    v.select("molecule", 1);
    const net = v.__networks[0];
    const body = { nodes: {}, emitter: { emit() {} } };
    const unit = v.catalogueGraph().units[0];
    unit.nodes.concat([unit.key]).forEach((k, i) => { body.nodes[k] = { x: i * 10, y: 0 }; });
    net.body = body;
    net.positions = Object.fromEntries(Object.entries(body.nodes).map(([k, n]) => [k, { x: n.x, y: n.y }]));
    net.handlers.dragStart({ nodes: ["tS_A1"], pointer: { canvas: { x: 30, y: 0 } } });
    net.handlers.dragging({ nodes: ["tS_A1"], pointer: { canvas: { x: 80, y: 40 } } });
    for (const k of unit.nodes.concat([unit.key])) {
      if (k === "tS_A1") continue;
      const i = unit.nodes.concat([unit.key]).indexOf(k);
      assert.deepEqual([body.nodes[k].x, body.nodes[k].y], [i * 10 + 50, 40], k);
    }
    net.handlers.dragEnd({});
    net.handlers.dragStart({ nodes: ["tS_J1"], pointer: { canvas: { x: 0, y: 0 } } });
    net.handlers.dragging({ nodes: ["tS_J1"], pointer: { canvas: { x: 99, y: 99 } } });
    assert.equal(body.nodes["u:tG_GABA"].y, 40, "a node outside every unit drags alone");
  });

  test("the disc is painted round the anchor, out to the furthest node", () => {
    const v = loadViewer(unitCatalogue());
    v.select("molecule", 1);
    const net = v.__networks[0];
    const unit = v.catalogueGraph().units[0];
    net.body = { view: { scale: 1 }, nodes: { [unit.key]: { x: 0, y: 0 } } };
    unit.nodes.forEach((k, i) => { net.body.nodes[k] = { x: i * 10, y: 0 }; });
    const calls = [];
    const ctx = new Proxy({}, { get: (t, k) => (k in t ? t[k] : (...a) => calls.push([k, a])),
                                set: (t, k, val) => { t[k] = val; return true; } });
    net.handlers.beforeDrawing(ctx);
    const arcs = calls.filter((c) => c[0] === "arc");
    assert.equal(arcs.length, 1);
    assert.deepEqual(arcs[0][1].slice(0, 3), [0, 0, (unit.nodes.length - 1) * 10 + 16]);
  });

  test("the legend names the disc while protein groups are linked", () => {
    const v = loadViewer(unitCatalogue());
    const block = plain(v.legendRows()).find((b) => b[0] === "Protein groups");
    assert.ok(block[1].some((r) => r[1] === "ion channel"));
  });

  test("selecting a complex lights its own subunits, and nothing else of theirs", () => {
    const v = loadViewer(unitCatalogue());
    const h = v.highlightFor("target", "C_132");
    // alpha1 and beta3 are drawn; gamma2 has no node of its own here.
    assert.equal(h.nodes.get("tS_A1"), 1);
    assert.equal(h.nodes.get("tS_B3"), 1);
    // Zolpidem acts at alpha1 and not at the complex, so it stays dark: the
    // subunits are lit, not treated as the selection's targets.
    assert.equal(h.nodes.get("m2"), undefined);
    assert.equal(h.nodes.get("m1"), 1, "the complex's own molecule is lit as ever");
    // A family is paralogues rather than parts, and lights no members.
    const f = v.highlightFor("target", "F_GABA");
    assert.equal(f.nodes.get("tS_A1"), undefined);
  });
});

describe("the legend is small and folds away", () => {
  test("it folds to one button, and the fold is remembered", () => {
    const v = loadViewer(catalogue());
    assert.match(v.legendHTML(), /Legend ▾/);
    v.setLegendOpen(false);
    assert.equal(v.legendHTML().replace(/<[^>]+>/g, ""), "Legend ▸");
    v.setLegendOpen(true);
    assert.match(v.legendHTML(), /<h5>What it is<\/h5>/);
    // Wired through the delegated click handler, like every row on the page.
    assert.match(viewerSource(), /closest\("\[data-legend-toggle\]"\)/);
  });

  test("a long block is set in two columns, a short one in one", () => {
    const v = loadViewer(catalogue());
    const html = v.legendHTML();
    assert.match(html, /<h5>What it is<\/h5><div class="legend-rows">/);
    const long = v.legendRows().some((b) => b[1].length > 6);
    assert.equal(/legend-rows two/.test(html), long);
  });

  test("in evidence colouring the lines are named once, by the colour block", () => {
    const v = loadViewer(catalogue());
    v.setFilter("lineColor", "evidence");
    const ev = v.legendRows().find((b) => b[0] === "Evidence")[1].map((r) => r[1]);
    assert.deepEqual(plain(ev), ["has a Supported claim", "none Supported"]);
  });
});

describe("the legend explains each mechanism on hover", () => {
  // Three lines: a coloured action, an action with no colour of its own, and
  // a measured claim with none.
  function mechanisms() {
    const curated = (id, mol, tgt, action) => claim({
      id: id, molecule: mol, target: tgt, role: "curated", tier_reason: "curated_support",
      curated_support: 1, multiple_study_support: 0, action_type: action,
      n_measurements: 0, n_studies: 0, n_publications: 0,
      supporting_endpoint_class: null, endpoints: [] });
    return buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
                  molecule({ id: 2, chembl_id: "CHEMBL2", name: "OTHER" })],
      targets: [target({ chembl_id: "T1", name: "Adenosine receptor A1" }),
                target({ chembl_id: "T2", name: "Some enzyme" })],
      claims: [curated(1, 1, "T1", "ANTAGONIST"),
               curated(2, 2, "T2", "HYDROLYTIC ENZYME"),
               claim({ id: 3, molecule: 2, target: "T1" })],
    });
  }
  const mechanismRows = (v) =>
    v.legendRows().find((b) => b[0].startsWith("Line colour · mechanism"))[1];

  test("every action with a colour of its own has an explanation", () => {
    // Read off the palette's own source, so a colour added later without an
    // explanation fails here.
    const palette = viewerSource().match(/const ACTION_COLORS = \{([^}]*)\}/)[1];
    const actions = [...palette.matchAll(/^\s*"?([A-Z][A-Z ]+?)"?:/gm)].map((m) => m[1]);
    assert.equal(actions.length, 13);
    const v = loadViewer(catalogue());
    for (const action of actions) {
      assert.ok(v.actionHelp(action).length > 20, "no explanation for " + action);
    }
    assert.equal(v.actionHelp("SOMETHING ENTIRELY NEW"), "");
  });

  test("each mechanism row carries one, and so do the rows with no single action", () => {
    const v = loadViewer(mechanisms());
    v.setFilter("lineColor", "mechanism");
    const rows = plain(mechanismRows(v));
    assert.deepEqual(rows.map((r) => r[1]),
      ["antagonist (1)", "other curated action (1)", "no curated mechanism (1)"]);
    assert.equal(rows[0][2], v.actionHelp("ANTAGONIST"));
    assert.match(rows[1][2], /no colour of its own here: hydrolytic enzyme \(1\)\./,
                 "the catch-all names what it holds");
    assert.match(rows[2][2], /Not a sign of no effect/);
  });

  test("a claim naming two actions is both of them, never an 'other' action", () => {
    // Varenicline's shape: one curated claim, AGONIST / PARTIAL AGONIST.
    const data = buildData({
      molecules: [molecule({ id: 1, chembl_id: "CHEMBL1076903", name: "VARENICLINE" })],
      targets: [target({ chembl_id: "T1", name: "Neuronal acetylcholine receptor" })],
      claims: [claim({ id: 1, molecule: 1, target: "T1", role: "curated",
                       tier_reason: "curated_support", curated_support: 1,
                       multiple_study_support: 0, action_type: "AGONIST / PARTIAL AGONIST",
                       n_measurements: 0, n_studies: 0, n_publications: 0,
                       supporting_endpoint_class: null, endpoints: [] })],
    });
    const v = loadViewer(data);
    const c = v.allClaims()[0];
    assert.deepEqual(plain(v.claimActions(c)), ["AGONIST", "PARTIAL AGONIST"]);
    v.setFilter("lineColor", "mechanism");
    assert.deepEqual(plain(mechanismRows(v)).map((r) => r[1]), ["several curated actions (1)"]);
    v.toggleMechanism("PARTIAL AGONIST");
    assert.ok(v.claimVisible(c), "the filter finds it by either action");
    // The panel still states it as the curator filed it, once.
    assert.match(v.claimDetail(c), /AGONIST \/ PARTIAL AGONIST/);
  });

  test("the explanation travels escaped, on the row's text and not on its swatch", () => {
    const v = loadViewer(mechanisms());
    v.setFilter("lineColor", "mechanism");
    const html = v.legendHTML();
    assert.match(html, /<span class="legend-help" tabindex="0" data-legend-help="Occupies[^"]*">antagonist \(1\)<\/span>/);
    assert.match(html, /body&#39;s own messenger|body&#x27;s own messenger/,
                 "an apostrophe in the text is escaped inside the attribute");
    // The rows that explain nothing - the node shapes - are plain text.
    assert.match(html, /<\/span>molecule<\/div>/);
  });

  test("the box sits beside the legend, not inside its scrolling", () => {
    assert.match(viewerHtml(), /<div id="legend"><\/div>\s*<div id="legend-tip" role="tooltip" hidden><\/div>/);
    const src = viewerSource();
    assert.match(src, /tip\.textContent = row\.getAttribute\("data-legend-help"\)/,
                 "its text is never read as markup");
    for (const type of ["mouseover", "mouseout", "focusin", "focusout"]) {
      assert.match(src, new RegExp('"' + type + '"'));
    }
  });
});

describe("every panel heading folds, the panel folds, and nothing can be selected", () => {
  test("no panel writes a heading that cannot be folded", () => {
    // Every section heading on every panel is a <summary>, so a reader can fold
    // any of them; a bare <h2> is a heading that cannot be.
    assert.doesNotMatch(viewerSource(), /"<h2>"/);
    const v = loadViewer(catalogue());
    for (const id of [1, 4]) {
      v.select("molecule", id);
      const html = v.panelHTML();
      assert.doesNotMatch(html, /<h2[\s>]/);
      assert.match(html, /class="section-toggle"/);
    }
    // The coverage line on an entry with nothing drawable is one of them, and
    // it starts folded like every other section.
    v.select("molecule", 4);
    assert.match(v.panelHTML(), /<details class="section"><summary class="section-toggle" data-fold="coverage">/);
    // No section on any panel starts open.
    assert.doesNotMatch(viewerSource(), /foldedSection\([^;]*, true[,)]/);
  });

  test("Clear selection leaves nothing lit and nothing dimmed", () => {
    const v = loadViewer(catalogue());
    const clear = v.document.getElementById("clear-btn");
    v.select("molecule", 1);
    assert.equal(clear.disabled, false);
    assert.equal(v.clearSelection(), true);
    assert.equal(v.getSelection().kind, null);
    assert.equal(v.panelHTML(), "");
    assert.equal(v.document.getElementById("detail-empty").hidden, false);
    assert.equal(clear.disabled, true);
    const o = v.highlightOpacity();
    assert.equal(o.highlighted, false);
    for (const x of o.nodes.values()) assert.equal(x, 1);
    // Nothing to clear is a no-op that says so.
    assert.equal(v.clearSelection(), false);
  });

  test("Back returns to the previous selection, and the page opening is not a step", () => {
    const v = loadViewer(catalogue());
    const back = v.document.getElementById("back-btn");
    // Opens on caffeine with nothing behind it.
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.selectionHistoryLength(), 0);
    assert.equal(back.disabled, true);
    assert.equal(v.goBack(), false);

    v.select("target", "CHEMBLT1");
    assert.equal(back.disabled, false);
    assert.match(back.title, /Back to CAFFEINE/);
    // Re-selecting what is already selected is not a second step.
    v.select("target", "CHEMBLT1");
    assert.equal(v.selectionHistoryLength(), 1);
    v.select("molecule", 2);
    // A misclick cleared: Back restores what was cleared.
    v.clearSelection();
    assert.match(back.title, /THEOPHYLLINE/);

    assert.equal(v.goBack(), true);
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.getSelection().id, 2);
    assert.equal(v.goBack(), true);
    assert.equal(v.getSelection().kind, "target");
    assert.equal(v.getSelection().id, "CHEMBLT1");
    assert.equal(v.goBack(), true);
    assert.equal(v.getSelection().id, 1);
    // Going back records nothing, so it walks back rather than toggling.
    assert.equal(back.disabled, true);
    assert.equal(v.goBack(), false);
  });

  test("Back restores a pair or an edge with both of its ends", () => {
    const v = loadViewer(catalogue());
    v.select("pair", 1, 2);
    v.select("edge", 1, "CHEMBLT1");
    v.select(null, null);
    assert.match(v.document.getElementById("back-btn").title, /CAFFEINE → Adenosine receptor A1/);
    v.goBack();
    assert.deepEqual([v.getSelection().kind, v.getSelection().id, v.getSelection().extra], ["edge", 1, "CHEMBLT1"]);
    v.goBack();
    assert.deepEqual([v.getSelection().kind, v.getSelection().id, v.getSelection().extra], ["pair", 1, 2]);
  });

  test("Escape clears the selection only when there is nothing else to close", () => {
    const v = loadViewer(catalogue());
    v.select("molecule", 1);
    // From inside the search box it means "leave the box", not "forget".
    assert.equal(v.onDocumentKeydown({ key: "Escape", target: { tagName: "INPUT" } }), false);
    assert.equal(v.getSelection().kind, "molecule");
    // An open popover is closed first, and the selection survives that press.
    const details = v.document.getElementById("view-options");
    details.open = true;
    assert.equal(v.onDocumentKeydown({ key: "Escape" }), true);
    assert.equal(details.open, false);
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.onDocumentKeydown({ key: "Escape" }), true);
    assert.equal(v.getSelection().kind, null);
  });

  test("the panel folds away, and its toggle names what is selected", () => {
    const v = loadViewer(catalogue());
    const side = v.document.getElementById("sidebar");
    const toggle = v.document.getElementById("sidebar-toggle");
    v.select("molecule", 1);
    v.setSidebarOpen(false);
    v.renderSidebarState(true);
    assert.equal(v.isSidebarOpen(), false);
    assert.equal(side.hidden, true);
    assert.match(toggle.textContent, /Panel · CAFFEINE/);
    // A selection made while it is folded keeps it folded and is named.
    v.select("molecule", 2);
    assert.equal(side.hidden, true);
    assert.match(toggle.textContent, /THEOPHYLLINE ANHYDROUS/);
    v.setSidebarOpen(true);
    v.renderSidebarState(true);
    assert.equal(side.hidden, false);
    assert.match(toggle.textContent, /Hide panel/);
    // Resizing the container is told to vis rather than left to its poll.
    assert.match(viewerSource(), /network\.setSize\(\);\s*sceneChanged\(\);/);
  });
});

describe("a ranked row says why it is where it is", () => {
  // ALPHA acts at T1-T3. BETA's only target is T1; GAMMA shares T1 and T2 and
  // reaches two more of its own; DELTA shares all three and nothing else.
  function profileCatalogue() {
    const t = (id, sym, over = {}) => target(Object.assign({
      chembl_id: id, name: "Protein " + sym,
      components: [{ accession: "P_" + id, gene_symbol: sym, description: sym }],
    }, over));
    let n = 0;
    const c = (molecule, tgt, over = {}) => claim(Object.assign({ id: ++n, molecule, target: tgt }, over));
    return buildData({
      molecules: [
        molecule({ id: 1, name: "ALPHA" }),
        molecule({ id: 2, chembl_id: "C2", name: "BETA" }),
        molecule({ id: 3, chembl_id: "C3", name: "GAMMA" }),
        molecule({ id: 4, chembl_id: "C4", name: "DELTA" }),
      ],
      targets: [t("T1", "GENEA"), t("T2", "GENEB"), t("T3", "GENEC"),
                t("T4", "GENED"), t("T5", "GENEE")],
      claims: [
        c(1, "T1"), c(1, "T2"), c(1, "T3"),
        c(2, "T1"),
        c(3, "T1"), c(3, "T2", { tier: "preliminary", multiple_study_support: 0 }),
        c(3, "T4"), c(3, "T5"),
        c(4, "T1"), c(4, "T2"), c(4, "T3"),
      ],
    });
  }

  test("the score is the sum of the contributions, scaled by two pair-wide factors", () => {
    const v = loadViewer(profileCatalogue());
    for (const row of v.sharedTargets(1)) {
      const sum = row.shared.reduce((t, s) => t + s.contribution, 0);
      assert.ok(Math.abs(sum - row.raw_score) < 1e-12);
      const expect = row.raw_score * row.direction_factor /
                     Math.sqrt(row.n_mine_targets * row.n_their_targets);
      assert.ok(Math.abs(expect - row.score) < 1e-12, row.molecule.name);
      for (let i = 1; i < row.shared.length; i++) {
        assert.ok(row.shared[i - 1].contribution >= row.shared[i].contribution,
          "shared targets are in contribution order");
      }
    }
  });

  test("the row states the overlap against both profiles", () => {
    const v = loadViewer(profileCatalogue());
    const a = v.lookupMolecule(1);
    const rows = v.sharedTargets(1);
    const line = (id) => v.similarityRowSummary(rows.find((r) => r.molecule.id === id), a);
    assert.match(line(2), /^its only target · 1 of ALPHA's 3 · /);
    assert.match(line(3), /^2 of its 4 targets · 2 of ALPHA's 3 · /);
    assert.match(line(4), /^all 3 of its targets · 3 of ALPHA's 3 · /);
    // And the raw score is no longer printed on the row: it is the bar's hover.
    assert.doesNotMatch(line(4), /score \d/);
  });

  test("it names the targets carrying half the score, or says it is spread", () => {
    const v = loadViewer(profileCatalogue());
    const rows = v.sharedTargets(1);
    // GAMMA's T1 is replicated and its T2 Preliminary, so T1 carries most.
    const gamma = rows.find((r) => r.molecule.id === 3);
    assert.equal(v.driverPhrase(gamma), "mostly GENEA");
    // BETA shares one target, which is the whole of its score.
    assert.equal(v.driverPhrase(rows.find((r) => r.molecule.id === 2)), "via GENEA");
    // DELTA's three are equal, so no one or two of them is "mostly".
    const delta = rows.find((r) => r.molecule.id === 4);
    assert.match(v.driverPhrase(delta), /^mostly GENE[ABC], GENE[ABC]$/);
  });

  test("three equal targets short of half read as spread out, not as mostly", () => {
    // Seven equal targets: three of them are 43% of the score.
    const tg = [], cl = [];
    for (let i = 1; i <= 7; i++) {
      tg.push(target({ chembl_id: "T" + i, name: "P" + i,
        components: [{ accession: "A" + i, gene_symbol: "G" + i }] }));
      cl.push(claim({ id: i, molecule: 1, target: "T" + i }));
      cl.push(claim({ id: 10 + i, molecule: 2, target: "T" + i }));
    }
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: tg, claims: cl,
    }));
    const row = v.sharedTargets(1)[0];
    assert.match(v.driverPhrase(row), /^spread out, led by G\d, G\d, G\d$/);
  });

  test("two species' records of one symbol say whose each is", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [
        target({ chembl_id: "TH", components: [{ accession: "P1", gene_symbol: "OPRM1" }] }),
        target({ chembl_id: "TG", organism: "Cavia porcellus", tax_id: 10141,
                 components: [{ accession: "P2", gene_symbol: "OPRM1" }] }),
        target({ chembl_id: "T3", components: [{ accession: "P3", gene_symbol: "X" }] }),
        target({ chembl_id: "T4", components: [{ accession: "P4", gene_symbol: "Y" }] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "TH" }), claim({ id: 2, molecule: 1, target: "TG" }),
        claim({ id: 3, molecule: 1, target: "T3", tier: "preliminary", multiple_study_support: 0 }),
        claim({ id: 4, molecule: 1, target: "T4", tier: "preliminary", multiple_study_support: 0 }),
        claim({ id: 5, molecule: 2, target: "TH" }), claim({ id: 6, molecule: 2, target: "TG" }),
        claim({ id: 7, molecule: 2, target: "T3", tier: "preliminary", multiple_study_support: 0 }),
        claim({ id: 8, molecule: 2, target: "T4", tier: "preliminary", multiple_study_support: 0 }),
      ],
    }));
    const phrase = v.driverPhrase(v.sharedTargets(1)[0]);
    assert.match(phrase, /OPRM1 \(human\)/);
    assert.match(phrase, /OPRM1 \(guinea pig\)/);
  });

  test("the section is titled for what it ranks, with a bar scaled to the top row", () => {
    const v = loadViewer(profileCatalogue());
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /Closest target profiles/);
    assert.doesNotMatch(html, /Shares targets with/);
    const top = v.sharedTargets(1)[0];
    assert.ok(html.includes('title="score ' + top.score.toFixed(3) + ', 100% of the top match"'));
    assert.match(html, /<span style="width:100%"><\/span>/);
  });
});

describe("the pair panel shows the arithmetic behind the score", () => {
  test("each target's share, the divisor, and the rank", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1, name: "ALPHA" }), molecule({ id: 2, chembl_id: "C2", name: "BETA" })],
      targets: [
        target({ chembl_id: "T1", components: [{ accession: "P1", gene_symbol: "GENEA" }] }),
        target({ chembl_id: "T2", organism: "Rattus norvegicus", tax_id: 10116,
                 components: [{ accession: "P2", gene_symbol: "Geneb" }] }),
      ],
      claims: [
        claim({ id: 1, molecule: 1, target: "T1" }),
        claim({ id: 2, molecule: 1, target: "T2", tier: "preliminary", multiple_study_support: 0 }),
        claim({ id: 3, molecule: 2, target: "T1" }),
        claim({ id: 4, molecule: 2, target: "T2" }),
      ],
    }));
    const row = v.sharedTargets(1)[0];
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.match(h, /data-fold="why_score"/);
    assert.match(h, /#1 of 1 for ALPHA/);
    // GENEA (0.9 evidence) before Geneb (0.5), and the shares add to 100.
    const a = row.shared[0].contribution / row.raw_score;
    assert.equal(row.shared[0].target.chembl_id, "T1");
    const table = h.slice(h.indexOf("score-table"), h.indexOf("</table>"));
    assert.ok(table.indexOf("GENEA") < table.indexOf("Geneb"));
    assert.ok(table.includes(Math.round(100 * a) + "%"));
    assert.ok(table.includes(Math.round(100 * (1 - a)) + "%"));
    assert.match(table, /Geneb<\/a> <span class="muted">rat<\/span>/,
      "a non-human record names its species");
    assert.ok(h.includes("Sum " + row.raw_score.toFixed(3) + " ÷ √(2 × 2) for how much each does = " +
                                row.score.toFixed(3) + "."));
    // The blocks below follow the same order.
    assert.ok(h.indexOf('data-fold="pair_t_T1"') < h.indexOf('data-fold="pair_t_T2"'));
    // ChEMBL names a protein alike in every species, so each block heading
    // says whose it is - human too, since a bare heading beside "(rat)" read
    // as a species not recorded rather than as human. It leads with the gene
    // symbol the score table names it by, so the two can be matched up.
    assert.ok(h.includes('data-fold="pair_t_T2">Geneb · Target one (rat)</summary>'));
    assert.ok(h.includes('data-fold="pair_t_T1">GENEA · Target one (human)</summary>'));
    assert.match(table, /GENEA<\/a> <span class="muted">human<\/span>/,
      "a human record names its species too");
    // Each name in the table jumps to its block further down the panel.
    assert.ok(table.includes('<a href="#" data-jump="pair_t_T1">GENEA</a>'));
    assert.ok(h.includes('<details class="section" id="blk-pair_t_T1"'));
    // A protein's own panel is headed by the protein, with no species in the
    // name (2026-10-10, at the user's request); the species is a row of its own.
    const tp = v.showTarget(v.lookupTarget("T2"));
    assert.match(tp, /<h3>Geneb · Target one<\/h3>/);
    assert.match(tp, /Rattus norvegicus/);
  });

  test("a species with no common name here keeps its binomial", () => {
    const v = loadViewer();
    assert.equal(v.targetTitle(target({ organism: "Danio rerio" })), "Target one (Danio rerio)");
    assert.equal(v.targetTitle(target({ organism: null })), "Target one (organism not recorded)");
  });

  test("a ChEMBL validity flag says what it means, and which edge the value is past", () => {
    // Theophylline's PI3Kalpha IC50 of 300 µM carries "Outside typical range",
    // which was printed bare and read as a verdict with no reason.
    const v = loadViewer();
    const obs = (value_nm, comment) => ({ value_status: "exact", value_nm,
                                          data_validity_comment: comment });
    const weak = v.validityPill(obs(300000, "Outside typical range"));
    assert.match(weak, /<span class="pill warn">Outside typical range<\/span><span class="help-text">/);
    assert.match(weak, /unusually weak or strong/);
    assert.match(weak, /This one is weaker than 100 µM\./);
    assert.match(v.validityPill(obs(0.001, "Outside typical range")),
                 /This one is stronger than 0\.01 nM\./);
    // Inside both edges, or a bound, it says nothing it cannot back.
    assert.doesNotMatch(v.validityPill(obs(468, "Outside typical range")), /This one/);
    assert.doesNotMatch(v.validityPill({ value_status: "bound", value_nm: null,
      data_validity_comment: "Outside typical range" }), /This one/);
    // A curator's check that the value is right is not a warning.
    assert.match(v.validityPill(obs(10, "Manually validated")),
                 /<span class="pill">Manually validated<\/span>/);
    // A phrase not in the map keeps ChEMBL's words and still opens something.
    const odd = v.validityPill(obs(10, "Some <new> flag"));
    assert.match(odd, /Some &lt;new&gt; flag<\/span><span class="help-text">A quality note/);
    // The observation row uses it.
    const row = v.observationRowHTML(Object.assign(obs(300000, "Outside typical range"),
      { standard_type: "IC50", assay_chembl_id: "CHEMBL3223603", counted: 1, study: null }), []);
    assert.ok(row.includes(weak));
  });

  test("an opposed pair's factor is part of the sum", () => {
    const v = loadViewer(opposedCatalogue());
    const row = v.sharedTargets(1).find((r) => r.molecule.id === 2);
    assert.ok(row.direction_factor < 1);
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.ok(h.includes(" × " + row.direction_factor.toFixed(3) + " for opposite actions"));
  });

  test("past eight targets the rest fold under their count and share", () => {
    const tg = [], cl = [];
    for (let i = 1; i <= 11; i++) {
      tg.push(target({ chembl_id: "T" + i, name: "P" + i,
        components: [{ accession: "A" + i, gene_symbol: "G" + i }] }));
      cl.push(claim({ id: i, molecule: 1, target: "T" + i }));
      cl.push(claim({ id: 20 + i, molecule: 2, target: "T" + i }));
    }
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: tg, claims: cl,
    }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    assert.match(h, /data-fold="why_score_rest">3 more targets · 27% of the score/);
    assert.equal((h.match(/<tr><td><a [^>]*>G\d+/g) || []).length, 11, "every target is still listed");
  });
});

describe("an approved molecule says what it is approved for when the list cannot", () => {
  // The Indications section holds only the neurological and pain conditions,
  // so bromazepam read "approved" over three phase-3 diseases: its approval is
  // for Anxiety, outside that scope (2026-09-27, at the user's request).
  function approved(over, indications) {
    return loadViewer(buildData({
      molecules: [molecule(Object.assign({ id: 1, name: "BROMAZEPAM", max_phase: 4 }, over))],
      indications: { 1: indications },
    }));
  }
  const phase3 = [["D003704", "Dementia", "Phase 3", "core", 1]];

  test("an approval outside the listed conditions is named", () => {
    const v = approved({ approved_elsewhere: "Anxiety" }, phase3);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /approved<div class="small muted">for Anxiety \(not listed here\)<\/div>/);
  });

  test("past three names the rest are counted, and every name is on hover", () => {
    const v = approved({ approved_elsewhere: "A|B|C|D|E" }, phase3);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /title="A, B, C, D, E">for A, B, C and 2 more \(not listed here\)/);
  });

  test("an approval ChEMBL files under no condition says so", () => {
    const v = approved({}, phase3);
    assert.match(v.showMolecule(v.lookupMolecule(1)),
                 /ChEMBL names no condition it is approved for/);
  });

  test("nothing is added where a listed condition is itself approved", () => {
    const v = approved({ approved_elsewhere: "Anxiety" },
                       [["D1", "Epilepsy", "Approved", "core", 1]]);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.ok(!/not listed here/.test(html));
    assert.ok(!/records no condition/.test(html));
  });

  test("a molecule that is not approved is untouched", () => {
    const v = approved({ max_phase: 3, approved_elsewhere: null }, phase3);
    const html = v.showMolecule(v.lookupMolecule(1));
    assert.match(html, /reached phase 3, not approved for any disease/);
    assert.ok(!/not listed here|records no condition/.test(html));
  });
});

describe("an Approved resting only on unapproved US labels is not one (D23)", () => {
  // Isometheptene was Approved for migraine on five DailyMed labels, every one
  // marketed as UNAPPROVED DRUG OTHER; FDA never approved it.
  const LABELS = [
    ["0844-set", "Nodolor Capsules", "Macoven Pharmaceuticals", "UNAPPROVED DRUG OTHER",
     "06/28/2011", "12/20/2017"],
    ["7752-set", "Isometheptene Mucate/Dichloralphenazone/Acetaminophen Capsules",
     "ECI <Pharmaceuticals>", "UNAPPROVED DRUG OTHER", "02/15/2011", "03/31/2018"],
  ];
  function viewer(over, rows) {
    return loadViewer(buildData({
      molecules: [molecule(Object.assign({ id: 1, name: "ISOMETHEPTENE", max_phase: 4 }, over))],
      indications: { 1: rows },
    }));
  }

  test("the disease reads Marketed unapproved and names and links the labels", () => {
    const v = viewer({}, [["D1", "Migraine Disorders", "Marketed unapproved", "core", 0,
                           null, "unapproved", LABELS]]);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, /Migraine Disorders<\/a> <span class="muted">Marketed unapproved<\/span>/);
    assert.match(h, /ChEMBL's Approved rests on 2 US labels FDA lists as unapproved, sold 2011–2018/);
    assert.match(h, /href="https:\/\/dailymed\.nlm\.nih\.gov\/dailymed\/drugInfo\.cfm\?setid=0844-set"[^>]*>Nodolor Capsules<\/a>/);
    assert.match(h, /\(ECI &lt;Pharmaceuticals&gt;\)/, "a labeler is escaped (invariant 11)");
  });

  test("a label still on sale is said so, not given an end", () => {
    const open = [["s", "T", "L", "UNAPPROVED DRUG OTHER", "01/01/1973", null]];
    const v = viewer({}, [["D1", "Myasthenia Gravis", "Marketed unapproved", "core", 0,
                           null, "unapproved", open]]);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)), /on one US label .*, sold since 1973:/);
  });

  test("a disease another record approves carries no label note", () => {
    const v = viewer({}, [["D1", "Pain", "Approved", "core", 1, null, "regulator"],
                          ["D1", "Pain", "Marketed unapproved", "core", 0, null,
                           "unapproved", LABELS]]);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, /title="ChEMBL&#39;s source: an FDA or EMA approval document">Approved/);
    assert.ok(!/FDA lists as unapproved/.test(h));
  });

  test("an unapproved record's cited trial sets its phase, and it still says why", () => {
    const v = viewer({}, [["D1", "Chronic Pain", "Phase 2", "core", 1, "NCT01",
                           "unapproved", LABELS]]);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, /<span class="muted">Phase 2<\/span>/);
    assert.match(h, /FDA lists as unapproved/);
  });

  test("Phase 4 trial sorts between Approved and Phase 3, Marketed unapproved below every phase", () => {
    const v = viewer({}, [["D1", "A", "Early Phase 1", "core", 0],
                          ["D2", "B", "Marketed unapproved", "core", 0, null, "unapproved", LABELS],
                          ["D3", "C", "Phase 3", "core", 1],
                          ["D4", "D", "Phase 4 trial", "core", 1, null, "unapproved", LABELS]]);
    assert.deepEqual(v.indicationsByDisease(1).map((i) => i.phase_label),
                     ["Phase 4 trial", "Phase 3", "Early Phase 1", "Marketed unapproved"]);
  });

  test("an approval read off a trial or an ATC class says so on hover", () => {
    const v = viewer({}, [["D1", "Narcolepsy", "Approved", "core", 1, "NCT9", "trial"],
                          ["D2", "Pain", "Approved", "core", 1, null, "atc"]]);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, /ChEMBL&#39;s source: a trial the registry calls Phase 4 \(post-marketing\)/);
    assert.match(h, /ChEMBL&#39;s source: the WHO ATC class the drug is filed in; no regulator&#39;s record is cited/);
  });

  test("a molecule whose only approval was such labels is not called approved", () => {
    const v = viewer({ approval_status: "unapproved_marketing", max_phase_checked: 2 },
                     [["D1", "Migraine Disorders", "Phase 2", "core", 1, "NCT1", "unapproved",
                       LABELS]]);
    const h = v.showMolecule(v.lookupMolecule(1));
    assert.match(h, /sold in the US without FDA approval, ChEMBL&#39;s only grounds for Approved; trials reached phase 2/);
    assert.ok(!/names no condition it is approved for|not listed here/.test(h));
  });
});

describe("the columns of Why this score explain themselves", () => {
  test("each header carries a hover explanation, anchored to the table", () => {
    const v = loadViewer(buildData({
      molecules: [molecule({ id: 1 }), molecule({ id: 2, chembl_id: "C2", name: "B" })],
      targets: [target({ chembl_id: "T1", components: [{ accession: "P1", gene_symbol: "G1" }] })],
      claims: [claim({ id: 1, molecule: 1, target: "T1" }),
               claim({ id: 2, molecule: 2, target: "T1" })],
    }));
    const h = v.showPair(v.lookupMolecule(1), v.lookupMolecule(2));
    for (const col of ["Target", "Kind", "Evidence", "Rarity", "Share"]) {
      assert.match(h, new RegExp('<th><span class="help" tabindex="0">' + col +
                                 '<span class="help-text">'), col);
    }
    assert.match(h, /1 when almost no molecule acts on this target/);
    assert.match(h, /<div class="score-wrap"><table class="score-table">/);
    assert.match(viewerHtml(), /\.score-wrap \{ position: relative; \}/);
  });
});

// The page is hosted publicly (docs/HOSTING-REVIEW.md), so what NOTICE says
// has to be on the page a visitor sees, not only in the repository.
describe("disclaimer and credits", () => {
  const html = viewerHtml();
  const start = html.indexOf('<details id="about">');
  const about = start < 0 ? "" : html.slice(start, html.indexOf("</details>", start));

  test("a permanent disclaimer sits outside every panel and popover", () => {
    const m = html.match(/<div id="disclaimer">([\s\S]*?)<\/div>/);
    assert.ok(m, "no #disclaimer");
    assert.match(m[1], /not medical, dosing or safety advice/);
    assert.match(m[1], /not interchangeable/);
    // A sibling of #main inside #app: not hidden with the sidebar or a popover.
    assert.ok(html.indexOf('<div id="disclaimer">') > html.indexOf('<div id="main">'));
  });

  test("About credits every source the payload is built from, with its terms", () => {
    assert.ok(about.length > 0, "no About panel");
    assert.match(about, /<ul id="about-sources"><\/ul>/);
    const sources = loadViewer(catalogue()).aboutSourcesHTML();
    // GtoPdb, credited only when its file is there, is held in
    // cohort_viewer_gtopdb.test.mjs; catalogue() has no GtoPdb file.
    for (const [source, terms] of [
      ["ChEMBL", /CC BY-SA 3\.0/], ["MeSH", /does not endorse/],
      ["ClinicalTrials\\.gov", /trial status/], ["UniProt", /CC BY 4\.0/],
      ["Wikidata", /CC0 1\.0/],
    ]) {
      assert.match(sources, new RegExp(source), source);
      assert.match(sources, terms, source);
    }
    assert.match(about, /Not medical advice/);
    assert.match(about, /not substitutes/);
    // Invariant 11's link rule holds for every external link About carries.
    const links = sources.match(/<a [^>]*>/g);
    assert.ok(links.length >= 6);
    for (const a of links) assert.match(a, /href="https:\/\/[^"]+" target="_blank" rel="noopener"/);
  });
});
