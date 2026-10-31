// What a public visitor is told about the page itself, rather than about the
// data: that it is loading, that it failed and why, which build they are
// looking at, under which licences, and how to cite it. Each of these was a
// gap the hosting review's second pass found (docs/HOSTING-REVIEW.md).
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import { loadViewer, makeSandbox, viewerSource, viewerHtml, buildData, buildGtopdb, withGtopdbFile,
         molecule } from "./cohort_harness.mjs";

// The page as it runs when graph.data.js never arrived: no COHORT_DATA at all,
// which loadViewer cannot express (it defaults to an empty catalogue).
function loadWithoutCatalogue() {
  const ctx = makeSandbox(buildData({}));
  delete ctx.COHORT_DATA;
  vm.runInContext(viewerSource(), ctx, { filename: "viz/index.html" });
  return ctx;
}

function dated({ gtopdb = false } = {}) {
  const data = buildData({
    molecules: [molecule({ id: 1, chembl_id: "CHEMBL113", name: "CAFFEINE" })],
    meta: {
      built_at: "2026-10-10T11:01:28",
      mesh_pharm_actions: JSON.stringify({ mesh_release: "desc2026" }),
      target_orthologues: JSON.stringify({ reference_release: "2026_03" }),
    },
  });
  data.generated = "2026-10-10T11:04:55";
  data.trials_fetched = ["2026-10-09T23:59:00+00:00", "2026-10-10T18:01:40+00:00"];
  if (gtopdb) withGtopdbFile(data, buildGtopdb({ generated: data.generated }));
  return data;
}

describe("loading and failing", () => {
  test("a missing catalogue says so, over the canvas and in the panel", () => {
    const v = loadWithoutCatalogue();
    const status = v.document.getElementById("load-status");
    assert.match(status.textContent, /graph\.data\.js is missing, blocked or broken/);
    assert.match(status.textContent, /not an empty catalogue/);
    assert.equal(status.hidden, false);
    assert.equal(status.className, "failed");
    assert.match(v.document.getElementById("detail-empty").textContent, /did not load/);
  });

  test("with the data there, the line says it is laying out, and clears on the first settle", () => {
    const v = loadViewer(dated());
    v.setLoadStatus("Laying out the network…");
    assert.equal(v.loadProblem(), null);
    v.settleGraph();
    assert.equal(v.document.getElementById("load-status").hidden, true);
  });

  test("a failure is never papered over by progress", () => {
    const v = loadViewer(dated());
    v.onPageError({ message: "boom <b>" });
    const status = v.document.getElementById("load-status");
    v.setLoadStatus("Laying out the network…");
    v.setLoadStatus("");
    assert.match(status.textContent, /Something on this page failed \(boom <b>\)/);
    assert.equal(status.hidden, false);
  });

  test("an uncaught error is listened for", () => {
    const v = loadViewer(dated(), { hash: "" });
    assert.ok(v.__windowListeners.some((l) => l.name === "error"));
  });
});

// A filter change takes seconds at the open defaults, all of it on the main
// thread, so the page says it is working before it starts: the status goes up,
// the rebuild waits a frame and a tick so the browser can paint it, and it
// comes down when the layout settles.
describe("a filter change says it is working", () => {
  const filterClick = (group, value) => ({
    target: {
      closest(sel) {
        if (sel !== "[data-filter]") return null;
        const attrs = { "data-filter": group, "data-value": value };
        return { getAttribute(name) { return name in attrs ? attrs[name] : null; } };
      },
    },
  });
  const runQueued = (v) => {
    while (v.__frames.length) v.__frames.shift()();
    for (const t of v.__timers.splice(0)) if (!t.cleared && t.ms === 0) t.fn();
  };

  // The busy line sits in the counts box at the top left, never on the
  // centred #load-status: the open Display options popover covers that.
  const counts = (v) => v.document.getElementById("graph-counts");

  test("the busy line goes up before the rebuild, and down once the layout settles", () => {
    const v = loadViewer(dated());
    v.settleGraph();
    const net = v.__networks[0];
    const solves = (net.stabilizeCalls || []).length;
    v.onFilterClick(filterClick("tier", "supported"));
    assert.equal(v.getBusy(), "Applying the filters…");
    assert.match(counts(v).innerHTML, /<div class="busy">Applying the filters…<\/div>$/);
    assert.equal(v.document.getElementById("load-status").hidden, true);
    // Nothing rebuilt yet: the filter is set, the re-solve has not started.
    assert.equal(v.getFilters().tier, "supported");
    assert.equal((net.stabilizeCalls || []).length, solves);
    runQueued(v);
    assert.equal((net.stabilizeCalls || []).length, solves + 1);
    assert.equal(v.getBusy(), "Laying out the network…");
    net.finishStabilizing({});
    assert.equal(v.getBusy(), "");
    assert.doesNotMatch(counts(v).innerHTML, /busy/);
  });

  test("clicks while one is queued fold into it", () => {
    const v = loadViewer(dated());
    v.settleGraph();
    const frames = v.__frames.length;
    v.onFilterClick(filterClick("tier", "supported"));
    v.onFilterClick(filterClick("basis", "human_direct"));
    assert.equal(v.__frames.length, frames + 1);
    // A layout finishing meanwhile leaves the queued change's line up.
    v.settleGraph();
    assert.equal(v.getBusy(), "Applying the filters…");
  });

  test("a change that moves nothing on the canvas clears as soon as it is drawn", () => {
    const v = loadViewer(dated());
    v.settleGraph();
    v.onFilterClick(filterClick("lineColor", "evidence"));
    runQueued(v);
    assert.equal(v.getBusy(), "");
  });
});

describe("the data's date", () => {
  test("the disclaimer carries the build day, and About the trial fetch days too", () => {
    const v = loadViewer(dated());
    assert.equal(v.dataDateLine(),
                 "Data built 2026-10-10 from ChEMBL 37; trial statuses fetched 2026-10-09 to 2026-10-10.");
    assert.equal(v.document.getElementById("data-date").textContent, " Data built 2026-10-10.");
    assert.match(v.document.getElementById("about-version").textContent,
                 /^Data built 2026-10-10 .* Also MeSH 2026, UniProt 2026_03\. Everything/);
  });

  test("an export without dates says it has none rather than inventing one", () => {
    const v = loadViewer(buildData({}));
    assert.equal(v.dataDateLine(), "");
    assert.match(v.aboutVersionText(), /not recorded/);
  });

  test("the NLM sources carry acknowledgement, non-endorsement, version and date", () => {
    const h = loadViewer(dated()).aboutSourcesHTML();
    assert.match(h, /MeSH<\/a> 2026, courtesy of the U\.S\. National Library of Medicine/);
    assert.match(h, /ClinicalTrials\.gov<\/a>, courtesy of the U\.S\. National Library of Medicine: trial status and site countries, fetched 2026-10-09 to 2026-10-10\. The NLM does not endorse/);
  });

  test("every licence named in About is a link to its text", () => {
    const h = loadViewer(dated({ gtopdb: true })).aboutSourcesHTML();
    for (const name of ["CC BY-SA 3.0", "CC BY-SA 4.0", "CC BY 4.0", "CC0 1.0", "ODbL 1.0"]) {
      assert.match(h, new RegExp('<a href="https://[^"]+"[^>]*>' + name.replace(/\./g, "\\.") + "</a>"), name);
    }
  });

  test("a GtoPdb file from another export is named as left out, not silently dropped", () => {
    const data = dated();
    withGtopdbFile(data, buildGtopdb({ generated: "2020-01-01T00:00:00" }));
    assert.match(loadViewer(data).aboutSourcesHTML(), /from a different export[^<]*left out/);
  });
});

describe("what the page is not", () => {
  test("the disclaimer and About both say interactions are not covered", () => {
    const html = viewerHtml();
    const strip = /<div id="disclaimer">([\s\S]*?)<\/div>/.exec(html)[1];
    const about = /<div id="about-body">([\s\S]*?)<h4>What "similar"/.exec(html)[1];
    for (const text of [strip, about]) {
      assert.match(text.replace(/\s+/g, " "), /does not cover interactions between drugs/);
    }
    assert.match(about, /CYP2D6/);
  });
});

describe("where to report an error", () => {
  // The public repository is where errors go (CONTRIBUTING.md): said in the
  // permanent strip, since About is closed by default, and in About with what
  // a useful report names. This repository's own address (docs/PUBLISHING.md).
  test("the disclaimer and About both link the repository's issues", () => {
    const html = viewerHtml();
    const strip = /<div id="disclaimer">([\s\S]*?)<\/div>/.exec(html)[1];
    const about = /<h4>Report an error<\/h4>\s*<p>([\s\S]*?)<\/p>/.exec(html)[1];
    const issues = /<a href="https:\/\/github\.com\/szaszeattila\/SubNetwork\/issues" target="_blank" rel="noopener">/;
    assert.match(strip, issues);
    assert.match(about, issues);
    assert.match(about.replace(/\s+/g, " "), /naming the molecule, the target and the source/);
  });
});

describe("how to cite", () => {
  test("cites the page by its data version and names the sources' own papers", () => {
    const h = loadViewer(dated({ gtopdb: true })).aboutCiteHTML();
    assert.match(h, /SubNetwork: a map of drug–target interactions, data version 2026-10-10\. Built from ChEMBL 37 and the IUPHAR\/BPS Guide to Pharmacology 2026\.3\./);
    assert.match(h, /doi:10\.1093\/nar\/gkad1004/);
    assert.match(h, /doi:10\.1093\/nar\/gkaf1067/);
  });

  test("a local file is never cited by its path on someone's disk", () => {
    const h = loadViewer(dated()).aboutCiteHTML();
    assert.doesNotMatch(h, /file:/);
    assert.doesNotMatch(h, /gkaf1067/);          // no GtoPdb file, no GtoPdb paper
  });

  test("a hosted page is cited by its address, without the selection", () => {
    const v = loadViewer(dated(), { hash: "#m=CHEMBL113" });
    v.window.location.href = "https://example.org/subnetwork/#m=CHEMBL113";
    assert.match(v.aboutCiteHTML(), /https:\/\/example\.org\/subnetwork\/\. Accessed/);
  });
});
