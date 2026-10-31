// Tests for the shareable links in viz/index.html: the selection as a URL
// fragment, read on load and on hashchange, written with replaceState.
//
// The fragment is the one thing read from the URL that does anything, so
// several of these are about what it must NOT do: name nothing, throw, or reach
// the page as markup.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  loadViewer, buildData, molecule, target, claim, plain,
} from "./cohort_harness.mjs";

// Internal ids are deliberately not the numbers in the ChEMBL ids, so a link
// built from the wrong one fails.
function catalogue(extraClaims = []) {
  return buildData({
    molecules: [
      molecule({ id: 7, chembl_id: "CHEMBL113", name: "CAFFEINE" }),
      molecule({ id: 8, chembl_id: "CHEMBL190", name: "THEOPHYLLINE" }),
      molecule({ id: 9, chembl_id: "CHEMBL555", name: "GAMMA" }),
    ],
    targets: [target({ chembl_id: "CHEMBL251", name: "Receptor one" }),
              target({ chembl_id: "CHEMBL252", name: "Receptor two" })],
    claims: [claim({ id: 1, molecule: 7, target: "CHEMBL251" }),
             claim({ id: 2, molecule: 8, target: "CHEMBL251" }),
             claim({ id: 3, molecule: 9, target: "CHEMBL252" })].concat(extraClaims),
    indications: {
      7: [["D003866", "Epilepsy", "Approved", "core", 1, null]],
      8: [["D003866", "Epilepsy", "Phase 3", "core", 1, null]],
    },
    classes: {
      labels: { mesh_pa: { D018377: [null, "Adenosine antagonists"] } },
      molecules: {
        7: [["mesh_pa", "D018377", null, "Adenosine antagonists"]],
        8: [["mesh_pa", "D018377", null, "Adenosine antagonists"]],
      },
    },
  });
}

const SELECTIONS = {
  molecule: { sel: { kind: "molecule", id: 8, extra: null }, link: "m=CHEMBL190" },
  target: { sel: { kind: "target", id: "CHEMBL251", extra: null }, link: "t=CHEMBL251" },
  edge: { sel: { kind: "edge", id: 7, extra: "CHEMBL251" }, link: "m=CHEMBL113&t=CHEMBL251" },
  pair: { sel: { kind: "pair", id: 7, extra: 8 }, link: "m=CHEMBL113&with=CHEMBL190" },
  retained: { sel: { kind: "retained", id: 7, extra: null }, link: "retained=CHEMBL113" },
  condition: { sel: { kind: "condition", id: "D003866", extra: null },
               link: "condition=D003866" },
  class: { sel: { kind: "class", id: "mesh_pa:D018377", extra: null },
           link: "class=mesh_pa:D018377" },
};

describe("a selection round-trips through its link", () => {
  for (const [kind, { sel, link }] of Object.entries(SELECTIONS)) {
    test(`${kind}: written in the documented format and read back equal`, () => {
      const v = loadViewer(catalogue());
      const text = v.selectionLink(sel);
      assert.equal(text, link);
      assert.deepEqual(plain(v.selectionFromLink(text)), sel);
      assert.deepEqual(plain(v.selectionFromLink("#" + text)), sel, "a leading # is accepted");
    });
  }

  test("a molecule is named by ChEMBL id, never the internal number", () => {
    const v = loadViewer(catalogue());
    for (const k of ["molecule", "edge", "pair", "retained"]) {
      const text = v.selectionLink(SELECTIONS[k].sel);
      assert.match(text, /CHEMBL\d+/);
      assert.ok(!/(^|[=&])[789]($|&)/.test(text), `${k}: ${text}`);
    }
  });

  test("the colon in a class key is left unescaped", () => {
    const v = loadViewer(catalogue());
    const text = v.selectionLink(SELECTIONS.class.sel);
    assert.ok(text.includes(":"));
    assert.ok(!/%3a/i.test(text));
  });

  test("nothing selected, or something unknown, has no link", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.selectionLink({ kind: null, id: null, extra: null }), "");
    assert.equal(v.selectionLink({ kind: "molecule", id: 999, extra: null }), "");
    assert.equal(v.selectionLink({ kind: "edge", id: 7, extra: "NOPE" }), "");
  });
});

describe("a link is only a lookup key", () => {
  const bad = [
    ["unknown molecule", "#m=CHEMBL999999"],
    ["unknown target", "#t=NOPE"],
    ["unknown condition", "#condition=D999999"],
    ["unknown class", "#class=mesh_pa:D999999"],
    ["unknown retained molecule", "#retained=CHEMBL999999"],
    ["unknown molecule with a valid target", "#m=CHEMBL999999&t=CHEMBL251"],
    ["unknown partner", "#m=CHEMBL113&with=CHEMBL999999"],
    ["a pair of a molecule with itself", "#m=CHEMBL113&with=CHEMBL113"],
    ["a malformed percent escape", "#m=%E0%A4%A"],
    ["an empty hash", ""],
    ["a bare #", "#"],
    ["markup", "#m=<img src=x onerror=alert(1)>"],
    ["markup as a class", "#class=<script>alert(1)</script>"],
    ["the internal number", "#m=7"],
  ];
  for (const [name, hash] of bad) {
    test(`${name} names nothing`, () => {
      const v = loadViewer(catalogue());
      assert.equal(v.selectionFromLink(hash), null);
    });
  }

  test("undefined and null name nothing", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.selectionFromLink(undefined), null);
    assert.equal(v.selectionFromLink(null), null);
  });
});

describe("opening the page at a link", () => {
  test("selects the molecule the link names, not the default opening", () => {
    const v = loadViewer(catalogue(), { hash: "#m=CHEMBL190" });
    const s = v.getSelection();
    assert.equal(s.kind, "molecule");
    assert.equal(s.id, 8);
    assert.equal(v.selectionHistoryLength(), 0);
  });

  test("opens other kinds too", () => {
    const v = loadViewer(catalogue(), { hash: "#m=CHEMBL113&with=CHEMBL190" });
    assert.deepEqual(plain(v.getSelection()), { kind: "pair", id: 7, extra: 8 });
  });

  test("a link naming nothing falls back to the default opening", () => {
    const plainOpen = loadViewer(catalogue());
    const v = loadViewer(catalogue(), { hash: "#m=CHEMBL999999" });
    assert.equal(v.getSelection().kind, "molecule");
    assert.equal(v.getSelection().id, plainOpen.getSelection().id);
    assert.equal(v.getSelection().id, 7, "caffeine");
    assert.equal(v.selectionHistoryLength(), 0);
  });

  test("with no hash the default opening has no Back history", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    assert.equal(v.getSelection().id, 7);
    assert.equal(v.selectionHistoryLength(), 0);
  });
});

describe("writing the link", () => {
  const last = (v) => v.__replaceStates[v.__replaceStates.length - 1];

  test("a selection writes its fragment", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    v.select("molecule", 8);
    assert.ok(last(v).url.endsWith("#m=CHEMBL190"), last(v).url);
    v.select("edge", 7, "CHEMBL251");
    assert.ok(last(v).url.endsWith("#m=CHEMBL113&t=CHEMBL251"), last(v).url);
    assert.equal(v.window.location.hash, "#m=CHEMBL113&t=CHEMBL251");
  });

  test("the page's own opening is written into the address", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    assert.ok(last(v).url.endsWith("#m=CHEMBL113"));
  });

  test("clearing the selection writes a URL with no #", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    v.select("molecule", 8);
    assert.equal(v.clearSelection(), true);
    assert.ok(!last(v).url.includes("#"), last(v).url);
  });

  test("re-selecting the same thing does not write again", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    v.select("molecule", 8);
    const n = v.__replaceStates.length;
    v.select("molecule", 8);
    assert.equal(v.__replaceStates.length, n);
  });

  test("opening at a link that already matches writes nothing", () => {
    const v = loadViewer(catalogue(), { hash: "#m=CHEMBL190" });
    assert.equal(v.__replaceStates.length, 0);
  });

  test("writing a link adds no Back step of its own", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    v.select("molecule", 8);
    assert.equal(v.selectionHistoryLength(), 1, "only the one select() step");
  });
});

describe("hashchange", () => {
  function fire(v) {
    const ls = v.__windowListeners.filter((l) => l.name === "hashchange");
    assert.equal(ls.length, 1, "exactly one hashchange listener");
    ls[0].fn();
  }

  test("a valid link selects it and records one Back step", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    assert.equal(v.selectionHistoryLength(), 0);
    v.window.location.hash = "#m=CHEMBL113&with=CHEMBL190";
    fire(v);
    assert.deepEqual(plain(v.getSelection()), { kind: "pair", id: 7, extra: 8 });
    assert.equal(v.selectionHistoryLength(), 1);
  });

  test("a hash naming nothing leaves the selection unchanged", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    const before = plain(v.getSelection());
    v.window.location.hash = "#m=CHEMBL999999";
    fire(v);
    assert.deepEqual(plain(v.getSelection()), before);
    assert.equal(v.selectionHistoryLength(), 0);
    v.window.location.hash = "";
    fire(v);
    assert.deepEqual(plain(v.getSelection()), before);
  });

  // The address is never left naming something other than what is open.
  test("a hash naming nothing is put back to what is open", () => {
    const v = loadViewer(catalogue(), { hash: "#m=CHEMBL190" });
    v.window.location.hash = "#m=CHEMBL999999";
    v.window.location.href = "file:///viz/index.html#m=CHEMBL999999";
    fire(v);
    assert.equal(v.window.location.hash, "#m=CHEMBL190");
    assert.equal(v.selectionHistoryLength(), 0);
  });
});

describe("a host without history", () => {
  test("selection works and nothing throws", () => {
    const v = loadViewer(catalogue());
    assert.equal(v.window.history, undefined);
    assert.doesNotThrow(() => {
      v.select("molecule", 8);
      v.select("pair", 7, 8);
      v.clearSelection();
    });
    assert.equal(v.writeSelectionLink(), false);
    assert.equal(v.getSelection().kind, null);
  });

  test("a host whose replaceState throws leaves selection working", () => {
    const v = loadViewer(catalogue(), { hash: "" });
    v.window.history.replaceState = () => { throw new Error("sandboxed"); };
    assert.doesNotThrow(() => v.select("molecule", 8));
    assert.equal(v.getSelection().id, 8);
  });
});

// The sender's filters travel with the link (2026-10-10): a link is a claim
// about what the sender saw, and the same molecule under other filters is a
// different picture. Only filters moved off their defaults are written.
function curatedCatalogue() {
  return catalogue([
    claim({ id: 4, molecule: 7, target: "CHEMBL252", role: "curated", curated_support: 1,
            multiple_study_support: 0, action_type: "PARTIAL AGONIST" }),
    claim({ id: 5, molecule: 8, target: "CHEMBL252", role: "curated", curated_support: 1,
            multiple_study_support: 0, action_type: "ANTAGONIST" })]);
}

describe("a link carries the sender's filters", () => {
  const last = (v) => v.__replaceStates[v.__replaceStates.length - 1];

  test("filterDefaults is what the page opens with, and what Reset returns to", () => {
    const v = loadViewer(curatedCatalogue());
    assert.deepEqual(plain(v.getFilters()), plain(v.filterDefaults()));
    v.setFilter("tier", "supported");
    v.toggleMechanism("ANTAGONIST");
    v.resetFilters();
    assert.deepEqual(plain(v.getFilters()), plain(v.filterDefaults()));
  });

  test("default filters add nothing to a link", () => {
    const v = loadViewer(curatedCatalogue());
    assert.equal(v.filterLink(), "");
  });

  test("every moved filter is written in the documented order and read back", () => {
    const v = loadViewer(curatedCatalogue());
    v.applyFilters({ tier: "supported", basis: "human_direct", potency: 10,
                     mechanism: ["PARTIAL AGONIST", "curated"], trials: "elsewhere",
                     periphery: "hide", groups: "separate", lineColor: "evidence" });
    const text = v.filterLink();
    assert.equal(text, "tier=supported&basis=human_direct&potency=10" +
      "&mech=PARTIAL%20AGONIST,curated&trials=elsewhere&canvas=hide&groups=separate" +
      "&color=evidence");
    assert.deepEqual(plain(v.filtersFromLink("#m=CHEMBL113&" + text)), plain(v.getFilters()));
  });

  test("a value no control offers is left at its default", () => {
    const v = loadViewer(curatedCatalogue());
    const f = plain(v.filtersFromLink(
      "#tier=everything&basis=<b>&potency=5&trials=mars&canvas=1&groups=&color=red" +
      "&mech=NOT%20AN%20ACTION,%3Cscript%3E,ANTAGONIST,ANTAGONIST"));
    assert.deepEqual(f, Object.assign(plain(v.filterDefaults()), { mechanism: ["ANTAGONIST"] }));
  });

  test("a malformed escape leaves every filter at its default", () => {
    const v = loadViewer(curatedCatalogue());
    assert.deepEqual(plain(v.filtersFromLink("#tier=supported&mech=%E0%A4%A")),
                     plain(v.filterDefaults()));
  });

  test("opening at a link applies its filters before the first drawing", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "#m=CHEMBL190&tier=supported&color=evidence" });
    assert.equal(v.getFilters().tier, "supported");
    assert.equal(v.getFilters().lineColor, "evidence");
    assert.equal(v.getSelection().id, 8);
    assert.equal(v.__replaceStates.length, 0, "the address already names this");
  });

  test("a link whose selection names nothing still carries its filters", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "#m=CHEMBL999999&tier=supported" });
    assert.equal(v.getSelection().id, 7, "the default opening");
    assert.equal(v.getFilters().tier, "supported");
    assert.equal(v.window.location.hash, "#m=CHEMBL113&tier=supported");
  });

  test("moving a filter rewrites the address", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "" });
    v.setFilter("potency", 100);
    v.refresh();
    assert.ok(last(v).url.endsWith("#m=CHEMBL113&potency=100"), last(v).url);
    v.setFilter("potency", null);
    v.refresh();
    assert.ok(last(v).url.endsWith("#m=CHEMBL113"), last(v).url);
  });

  test("with nothing selected a link is its filters alone", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "" });
    v.setFilter("basis", "human_direct");
    v.clearSelection();
    assert.equal(v.window.location.hash, "#basis=human_direct");
  });
});

describe("hashchange with filters", () => {
  function fire(v) {
    v.__windowListeners.filter((l) => l.name === "hashchange")[0].fn();
  }

  test("a pasted link replaces the reader's filters with the sender's", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "" });
    v.setFilter("groups", "separate");
    v.window.location.hash = "#m=CHEMBL190&tier=supported";
    fire(v);
    assert.equal(v.getSelection().id, 8);
    assert.equal(v.getFilters().tier, "supported");
    assert.equal(v.getFilters().groups, "linked", "a filter the link leaves out is at its default");
    assert.equal(v.selectionHistoryLength(), 1);
  });

  test("a link of filters alone keeps what is open", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "#m=CHEMBL190" });
    v.window.location.hash = "#canvas=hide";
    fire(v);
    assert.equal(v.getSelection().id, 8);
    assert.equal(v.getFilters().periphery, "hide");
    assert.equal(v.window.location.hash, "#m=CHEMBL190&canvas=hide");
    assert.equal(v.selectionHistoryLength(), 0);
  });

  test("a link naming nothing moves no filter", () => {
    const v = loadViewer(curatedCatalogue(), { hash: "#m=CHEMBL190&tier=supported" });
    for (const hash of ["#m=CHEMBL999999&tier=supported_preliminary", "#foo=bar", ""]) {
      v.window.location.hash = hash;
      fire(v);
      assert.equal(v.getFilters().tier, "supported", hash);
      assert.equal(v.getSelection().id, 8, hash);
      assert.equal(v.window.location.hash, "#m=CHEMBL190&tier=supported", hash);
    }
  });
});
