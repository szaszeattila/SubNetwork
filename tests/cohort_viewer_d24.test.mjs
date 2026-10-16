// D24 (docs/COHORT-2.md): what the page says about an Approved once D23's
// three gaps were closed - a trial-only approval that rests on no Phase 4
// trial, an approval read off a WHO ATC class, an unread label, and a drug
// ChEMBL records withdrawn.
import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  loadViewer, buildData, molecule, withDrugcentralFile,
} from "./cohort_harness.mjs";

function viewer(over, rows, approvals) {
  const data = buildData({
    molecules: [molecule(Object.assign({ id: 1, name: "DRUG", max_phase: 4 }, over))],
    indications: { 1: rows },
  });
  return loadViewer(approvals ? withDrugcentralFile(data, approvals) : data);
}

const N05BA = "N05BA (anxiolytics: benzodiazepine derivatives)";

describe("an ATC-backed Approved names the class, not a regulator (D24)", () => {
  test("with no regulator on record it says none is cited", () => {
    const v = viewer({}, [["D1", "Anxiety", "Approved", "core", 1, null, "atc", null, N05BA]]);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)),
                 /title="ChEMBL&#39;s source: classified by WHO ATC in N05BA \(anxiolytics: benzodiazepine derivatives\); no regulator&#39;s record is cited">Approved/);
  });

  test("DrugCentral's regulators are named, as a fact about the drug", () => {
    const v = viewer({}, [["D1", "Anxiety", "Approved", "core", 1, null, "atc", null, N05BA]],
                     { 1: [["EMA", 1998], ["PMDA", 2004]] });
    assert.match(v.indicationsHTML(v.lookupMolecule(1)),
                 /DrugCentral records the drug approved by EMA \(1998\), PMDA \(2004\), not necessarily for this disease/);
  });

  test("a DrugCentral file from another export is not merged, and About says so", () => {
    const data = buildData({
      molecules: [molecule({ id: 1, name: "DRUG", max_phase: 4 })],
      indications: { 1: [["D1", "Anxiety", "Approved", "core", 1, null, "atc", null, N05BA]] },
    });
    data.generated = "2026-10-16T10:00:00";
    const v = loadViewer(withDrugcentralFile(data, { 1: [["EMA", 1998]] },
                                             { generated: "2026-01-01T00:00:00" }));
    assert.match(v.indicationsHTML(v.lookupMolecule(1)), /no regulator&#39;s record is cited/);
    assert.match(v.aboutSourcesHTML(), /drugcentral\.data\.js\) is from a different export/);
  });

  test("About credits DrugCentral, at its release, only when its file was merged", () => {
    const merged = viewer({}, [], { 1: [["FDA", 1970]] });
    assert.match(merged.aboutSourcesHTML(), />DrugCentral<\/a> v56, 2026-09-02: .*CC BY-SA 4\.0/);
    assert.doesNotMatch(viewer({}, []).aboutSourcesHTML(), /DrugCentral/);
  });
});

describe("a trial-only Approved stands only on a Phase 4 trial (D24)", () => {
  test("one that rests on no Phase 4 trial reads its trials' phase and says why", () => {
    const v = viewer({}, [["D1", "Muscle Cramp", "Phase 3", "core", 1, "NCT01155167",
                           "trial_phase"]]);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, /Muscle Cramp<\/a> <span class="muted">Phase 3<\/span>/);
    assert.match(h, /ChEMBL lists this as approved, on trials alone, none of which the registry records as Phase 4\./);
  });

  test("a genuine Phase 3 carries no such note", () => {
    const v = viewer({}, [["D1", "Pain", "Phase 3", "core", 1, "NCT1"]]);
    assert.doesNotMatch(v.indicationsHTML(v.lookupMolecule(1)), /on trials alone/);
  });

  test("Approval unconfirmed sorts with Marketed unapproved, below every phase", () => {
    const v = viewer({}, [["D1", "A", "Approval unconfirmed", "core", 0, null, "unconfirmed"],
                          ["D2", "B", "Early Phase 1", "core", 0]]);
    assert.deepEqual(v.indicationsByDisease(1).map((i) => i.phase_label),
                     ["Early Phase 1", "Approval unconfirmed"]);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)),
                 /on a US label that could not be read, and FDA records no approval of the drug/);
  });

  test("a molecule every approval of which fell is not called approved", () => {
    const v = viewer({ approval_status: "no_approval_cited", max_phase_checked: 3 },
                     [["D1", "Pain", "Phase 3", "core", 1, "NCT1", "trial_phase"]]);
    assert.match(v.showMolecule(v.lookupMolecule(1)),
                 /ChEMBL records it as approved, but nothing it cites is an approval; its trials reached phase 3/);
  });
});

describe("an unread label says why, beside FDA's approval year (D24)", () => {
  test("a label older than FDA's marketing categories", () => {
    const v = viewer({ first_approval: 1970 },
                     [["D1", "Depressive Disorder", "Approved", "core", 1, null, "unresolved",
                       null, null, "no marketing table"]]);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)),
                 /ChEMBL&#39;s source: a US drug label older than FDA&#39;s marketing categories, which states none; FDA records the drug approved in 1970/);
  });
});

describe("a withdrawal ChEMBL records is said beside Approved (D24)", () => {
  const rows = [["D1", "Depressive Disorder", "Approved", "core", 1, null, "regulator"],
                ["D2", "Pain", "Phase 2", "core", 1]];

  test("withdrawn worldwide reads as one, with the year", () => {
    const v = viewer({ withdrawals: [["Sweden", 1982, null],
                                     ["Worldwide", 1983, "neurotoxicity"]] }, rows);
    const h = v.indicationsHTML(v.lookupMolecule(1));
    assert.match(h, />Approved, withdrawn worldwide \(1983\)<\/span>/);
    assert.match(h, /ChEMBL records it withdrawn: Sweden, 1982; worldwide, 1983 \(neurotoxicity\)/);
    assert.match(h, /<span class="muted">Phase 2<\/span>/, "only an Approved row says it");
    assert.match(v.showMolecule(v.lookupMolecule(1)), /approved, withdrawn worldwide \(1983\)/);
  });

  test("withdrawn in some markets names them", () => {
    const v = viewer({ withdrawals: [["France", 1990, "hepatotoxicity"]] }, rows);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)),
                 />Approved; withdrawn in France, 1990<\/span>/);
  });

  test("several markets join their names, and more than two events are counted", () => {
    const two = viewer({ withdrawals: [["United States; United Kingdom; Italy", 1970, null],
                                       ["Spain", 1993, null]] }, rows);
    assert.match(two.indicationsHTML(two.lookupMolecule(1)),
                 /Approved; withdrawn in United States, United Kingdom and Italy, 1970; in Spain, 1993/);
    const three = viewer({ withdrawals: [["France", 1977, null], ["Spain", 1985, null],
                                         ["Germany", 1999, null]] }, rows);
    assert.match(three.indicationsHTML(three.lookupMolecule(1)),
                 /Approved; withdrawn in 3 markets, 1977–1999/);
  });

  test("a country name is escaped (invariant 11)", () => {
    const v = viewer({ withdrawals: [["<Ruritania>", 2000, null]] }, rows);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)), /withdrawn in &lt;Ruritania&gt;, 2000/);
  });

  test("a molecule ChEMBL records no withdrawal of reads plain Approved", () => {
    const v = viewer({}, rows);
    assert.match(v.indicationsHTML(v.lookupMolecule(1)), />Approved<\/span>/);
  });
});
