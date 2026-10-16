// The similarity harness: grade viz/index.html's own ranking against an answer
// key that nobody here wrote.
//
// The six constants behind `sharedTargets` were each chosen by argument and
// measured against nothing, which is finding 2 of the 2026-09-17 review. This
// is the instrument that ends that: it does not derive a constant from
// anything, it lets two candidate values be compared, which is the difference
// between an argument and a measurement.
//
// Three decisions carry the whole thing, and each one is a way of not cheating.
//
// *The page's own code is what gets graded.* `sharedTargets` is called through
// the same vm sandbox the viewer tests use, never reimplemented here. A
// reimplementation starts identical and drifts, and then the harness reports on
// a copy while the page ships something else.
//
// *The answer key is generated, not written.* Hand-listing the classes -- the
// four cholinesterase inhibitors, haloperidol and clozapine, the
// methylxanthines -- would fix six hand-picked numbers by hand-picking the
// thing that judges them, and the grade could then be made to say anything.
// ATC level 4 is the WHO's own grouping of drugs by how they work, it is
// already in `molecules.atc_level5`, and it was written by people who had never
// heard of this project.
//
// *Coverage is counted apart from ordering.* A molecule whose class peers are
// nowhere in its list is not a molecule the ranking got wrong; it is one ChEMBL
// gives nothing to rank. Several of the constants change what is eligible at
// all, so folding those into the denominator would let a constant improve the
// grade by making more questions answerable, and the sweep would tune toward
// coverage without ever saying so.
//
// What the grade is *not* is ground truth. ATC groups partly by mechanism and
// ChEMBL curates mechanism most thoroughly for well-known drugs, so this metric
// structurally flatters any term that rewards curation. That bias is reported
// beside every number rather than left to be discovered.

import { makeSandbox, withGtopdbFile } from "../../tests/cohort_harness.mjs";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const GRAPH_DATA = join(ROOT, "viz", "graph.data.js");
const INDEX = join(ROOT, "viz", "index.html");

// Anchored at line starts for the same reason tests/cohort_harness.mjs anchors
// it: the comment at the top of index.html contains the literal text
// "<script src=...>".
const SCRIPT_RE = /^<script>$\r?\n([\s\S]*?)\r?\n^<\/script>$/m;

export class HarnessError extends Error {}

export function payloadExists() {
  return existsSync(GRAPH_DATA);
}

/**
 * The real exported catalogue, as the page would receive it: graph.data.js
 * with gtopdb.data.js beside it, which carries GtoPdb's directions and claims
 * under its own licence. Both are required - a grade without the second would
 * be a grade of a different ranking, not of a missing file.
 */
export function loadPayload(path = GRAPH_DATA) {
  const gtopdbPath = join(dirname(path), "gtopdb.data.js");
  for (const p of [path, gtopdbPath]) {
    if (!existsSync(p)) {
      throw new HarnessError(
        `${p} is not there. It is generated and gitignored; run ` +
        "`python3 scripts/export_cohort.py` first.");
    }
  }
  const ctx = vm.createContext({});
  vm.runInContext(readFileSync(path, "utf8") + ";globalThis.__d=COHORT_DATA;", ctx);
  if (!ctx.__d || !Array.isArray(ctx.__d.molecules)) {
    throw new HarnessError(`${path} did not define a COHORT_DATA catalogue.`);
  }
  vm.runInContext(readFileSync(gtopdbPath, "utf8") + ";globalThis.__g=COHORT_GTOPDB;", ctx);
  if (!ctx.__g || !Array.isArray(ctx.__g.claims)) {
    throw new HarnessError(`${gtopdbPath} did not define a COHORT_GTOPDB file.`);
  }
  return withGtopdbFile(ctx.__d, ctx.__g);
}

export function viewerSource() {
  const m = readFileSync(INDEX, "utf8").match(SCRIPT_RE);
  if (!m) {
    throw new HarnessError(
      "Could not find the inline <script> block in viz/index.html. If the " +
      "viewer was restructured, update SCRIPT_RE in analysis/similarity_" +
      "harness/harness.mjs -- and in tests/cohort_harness.mjs, which has its " +
      "own copy.");
  }
  return m[1];
}

/**
 * The viewer, in a fresh realm, optionally over patched source.
 *
 * A fresh realm per call is not an optimisation to remove: the page builds its
 * indexes once from COHORT_DATA at load, and a re-run of a patched source in a
 * used realm would redeclare its `const`s and throw.
 */
export function loadViewer(data, patch = (s) => s) {
  const source = patch(viewerSource());
  const ctx = makeSandbox(data);
  vm.runInContext(source, ctx, { filename: "viz/index.html" });
  if (typeof ctx.sharedTargets !== "function") {
    throw new HarnessError("the viewer loaded but exposes no sharedTargets().");
  }
  return ctx;
}

// -------------------------------------------------------------- the answer key

/**
 * Patch one of the scoring constants in the viewer's source text.
 *
 * Each patch asserts it changed something. A regex that silently stops matching
 * would report the baseline under every label in a sweep -- a table of numbers
 * that all agree because nothing was ever varied, which is worse than an error.
 */
export function patchConstant(name, value) {
  const edits = {
    // Both halves of the broad-target weight move together: they are the two
    // identities the page treats as "a claim about a set" (D06).
    target_weight_broad: [
      /"PROTEIN COMPLEX GROUP": [0-9.]+, "PROTEIN FAMILY": [0-9.]+,/,
      (v) => `"PROTEIN COMPLEX GROUP": ${v}, "PROTEIN FAMILY": ${v},`,
    ],
    opposed_pair_factor: [
      /const OPPOSED_PAIR_FACTOR = [0-9.]+;/,
      (v) => `const OPPOSED_PAIR_FACTOR = ${v};`,
    ],
    evidence_curated_multi: [
      /if \(curated && multi\) return [0-9.]+;/,
      (v) => `if (curated && multi) return ${v};`,
    ],
    evidence_multi: [
      /\n  if \(multi\) return [0-9.]+;/,
      (v) => `\n  if (multi) return ${v};`,
    ],
    evidence_curated: [
      /\n  if \(curated\) return [0-9.]+;/,
      (v) => `\n  if (curated) return ${v};`,
    ],
    evidence_preliminary: [
      /\n  return [0-9.]+;   \/\/ Preliminary/,
      (v) => `\n  return ${v};   // Preliminary`,
    ],
    species_exponent: [
      /const SPECIES_EXPONENT = [0-9.]+;/,
      (v) => `const SPECIES_EXPONENT = ${v};`,
    ],
  };
  const edit = edits[name];
  if (!edit) throw new HarnessError(`no such constant: ${name}`);
  const [re, write] = edit;
  return function (source) {
    // The test is whether the pattern *matched*, not whether the text changed.
    // Patching a constant to the value it already holds is a legitimate no-op,
    // and it is the first row of every grid -- reading an unchanged string as a
    // failed patch would make the baseline the one case that cannot be run.
    if (!re.test(source)) {
      throw new HarnessError(
        `the patch for ${name} matched nothing in viz/index.html. The ` +
        "constant was probably renamed or reformatted; fix the pattern in " +
        "patchConstant() rather than letting a sweep report the baseline " +
        "under every label.");
    }
    return source.replace(re, write(value));
  };
}

export const CONSTANTS = {
  target_weight_broad: { current: 0.5, grid: [0, 0.25, 0.5, 0.75, 1.0],
    label: "TARGET_WEIGHT, family / complex group" },
  opposed_pair_factor: { current: 0.25, grid: [0, 0.25, 0.5, 0.75, 1.0],
    label: "OPPOSED_PAIR_FACTOR (1.0 disables D15)" },
  evidence_curated_multi: { current: 1.0, grid: [0.75, 0.9, 1.0],
    label: "evidenceWeight, curated and replicated" },
  evidence_multi: { current: 0.9, grid: [0.5, 0.75, 0.9, 1.0],
    label: "evidenceWeight, replicated only" },
  evidence_curated: { current: 0.75, grid: [0.5, 0.75, 0.9, 0.95, 1.0],
    label: "evidenceWeight, curated only" },
  evidence_preliminary: { current: 0.5, grid: [0.25, 0.5, 0.75],
    label: "evidenceWeight, neither (Preliminary)" },
  // D20: 0 counts a protein strictly once across species, 1 lets every
  // species' record add as much as a different protein would.
  species_exponent: { current: 0.5, grid: [0, 0.25, 0.5, 0.75, 1.0],
    label: "SPECIES_EXPONENT, one protein in n species (D20)" },
};

// -------------------------------------------------------------- the answer key

const str = (data, x) => (typeof x === "number" ? data.strings[x] : x);

/**
 * ATC level-4 classes, as the answer key.
 *
 * An ATC code is a nested address -- N06AA09 is nervous system / psychoanaleptic
 * / antidepressant / non-selective monoamine reuptake inhibitor / amitriptyline
 * -- and level 4, the first five characters, is where the WHO groups drugs by
 * how they work.
 *
 * The `X` classes are dropped, and that is not tidying. A fourth-level `X`
 * means "other": N06AX is literally "other antidepressants", and at 29 members
 * the largest class there is. It is a group *defined by not sharing a
 * mechanism* -- mirtazapine and bupropion are both in it -- so a ranking that
 * called two of its members similar would be wrong, and grading against it
 * would award a point for that. Dropping them takes the set from 514 molecules
 * to 395.
 */
export function labelledSet(data) {
  const F = data.fields.molecules;
  const idI = F.indexOf("id"), nameI = F.indexOf("name"), atcI = F.indexOf("atc_level5");
  if (atcI < 0) throw new HarnessError("the payload carries no atc_level5 field.");

  const classesOf = new Map();   // molecule id -> Set of level-4 codes
  const members = new Map();     // level-4 code -> Set of molecule ids
  for (const row of data.molecules) {
    const txt = str(data, row[atcI]);
    if (!txt) continue;
    const id = row[idI];
    // A molecule can be filed under several codes; ChEMBL joins them with "|".
    for (const code of String(txt).split("|")) {
      const l4 = code.trim().slice(0, 5);
      if (l4.length !== 5) continue;
      if (l4[4] === "X") continue;
      if (!classesOf.has(id)) classesOf.set(id, new Set());
      classesOf.get(id).add(l4);
      if (!members.has(l4)) members.set(l4, new Set());
      members.get(l4).add(id);
    }
  }
  // A class of one cannot be got right or wrong, so it is not a question.
  for (const [code, set] of [...members]) if (set.size < 2) members.delete(code);

  const labelled = [...classesOf.keys()]
    .filter((id) => [...classesOf.get(id)].some((c) => members.has(c)))
    .sort((a, b) => a - b);     // deterministic order, so a diff of two runs is a diff
  const names = new Map(data.molecules.map((r) => [r[idI], str(data, r[nameI])]));

  if (!labelled.length) {
    throw new HarnessError(
      "no molecule in this payload carries an ATC code with a classmate, so " +
      "there is nothing to grade.");
  }
  return {
    classesOf, members, labelled, names,
    peersOf(id) {
      const out = new Set();
      for (const code of classesOf.get(id) || []) {
        if (!members.has(code)) continue;
        for (const other of members.get(code)) if (other !== id) out.add(other);
      }
      return out;
    },
  };
}

/**
 * MeSH pharmacological actions, as a second and independent answer key.
 *
 * ATC is the only judge this harness had, and SIMILARITY-HARNESS.md names the
 * gap: a key partly defined by mechanism and built from the same world as
 * ChEMBL's curation flatters whatever rewards curation. A MeSH action is what
 * NLM's indexers record a drug as doing, from the literature and not from
 * ChEMBL, backfilled by scripts/resolve_cohort_pharm_actions.py and shipped in
 * the payload's `classes` block.
 *
 * Two molecules are classmates when they share an action they are *directly*
 * indexed with - not one inherited from the hierarchy, which would make every
 * antidepressant a classmate of every antipsychotic through "Psychotropic
 * Drugs". Actions shallower than `minDepth` in the MeSH tree are dropped, for
 * the reason the ATC key drops its `X` classes: "Central Nervous System Agents"
 * or "Enzyme Inhibitors" is a heading, not a shared mechanism, and a ranking
 * that called two of its members alike would be awarded a point it had not
 * earned.
 */
export function meshActionSet(data, { minDepth = 5 } = {}) {
  const F = data.fields.molecules;
  const idI = F.indexOf("id"), nameI = F.indexOf("name");
  const cls = data.classes || {};
  const labels = (cls.labels || {}).mesh_pa || {};
  const classesOf = new Map(), members = new Map();
  for (const [id, rows] of Object.entries(cls.molecules || {})) {
    for (const r of rows) {
      if (r[0] !== "mesh_pa") continue;
      const lab = labels[r[1]];
      if (!lab || lab[0] == null || lab[0] < minDepth) continue;
      const mid = Number(id);
      if (!classesOf.has(mid)) classesOf.set(mid, new Set());
      classesOf.get(mid).add(r[1]);
      if (!members.has(r[1])) members.set(r[1], new Set());
      members.get(r[1]).add(mid);
    }
  }
  for (const [code, set] of [...members]) if (set.size < 2) members.delete(code);
  const labelled = [...classesOf.keys()]
    .filter((id) => [...classesOf.get(id)].some((c) => members.has(c)))
    .sort((a, b) => a - b);
  const names = new Map(data.molecules.map((r) => [r[idI], str(data, r[nameI])]));
  if (!labelled.length) {
    throw new HarnessError(
      "no molecule in this payload carries a MeSH action with a classmate. Run " +
      "scripts/resolve_cohort_pharm_actions.py and re-export.");
  }
  const labelOf = (code) => str(data, (labels[code] || [])[1]) || code;
  return {
    classesOf, members, labelled, names, labelOf,
    peersOf(id) {
      const out = new Set();
      for (const code of classesOf.get(id) || []) {
        if (!members.has(code)) continue;
        for (const other of members.get(code)) if (other !== id) out.add(other);
      }
      return out;
    },
  };
}

// ------------------------------------------------------------------- the grade

/**
 * Walk each labelled molecule's ranking to its first same-class peer.
 *
 * `unanswerable` is the count of molecules with no peer anywhere in the list,
 * and it is kept out of every rate rather than scored as a failure. See the
 * third decision at the top of this file: it is the one that stops a sweep
 * rewarding coverage and calling it ranking.
 */
export function grade(viewer, key) {
  let scoreable = 0, top1 = 0, top5 = 0, top10 = 0, mrr = 0, unanswerable = 0;
  const ranks = new Map();
  for (const id of key.labelled) {
    const peers = key.peersOf(id);
    if (!peers.size) continue;
    const rows = viewer.sharedTargets(id);
    let rank = 0;
    for (let i = 0; i < rows.length; i++) {
      if (peers.has(rows[i].molecule.id)) { rank = i + 1; break; }
    }
    if (!rank) { unanswerable++; continue; }
    scoreable++;
    ranks.set(id, { rank, listed: rows.length, top: rows[0] && rows[0].molecule.name });
    if (rank === 1) top1++;
    if (rank <= 5) top5++;
    if (rank <= 10) top10++;
    mrr += 1 / rank;
  }
  return {
    scoreable, unanswerable, ranks,
    top1: top1 / scoreable, top5: top5 / scoreable, top10: top10 / scoreable,
    mrr: mrr / scoreable,
  };
}

/**
 * The viewer with every listed_only entry (D23-D25) left out of each ranked
 * list. Such an entry can never carry an ATC N code -- one would have admitted
 * it -- so ranked above a class-mate it is a miss the judge cannot tell from a
 * ranking error. It still weighs on every target's prevalence, which is how it
 * can still move the grade. docs/SIMILARITY-HARNESS.md section 13.
 */
export function skippingListed(viewer) {
  const listed = (row) => row.molecule.admission_reason === "listed_only";
  const shared = (id) => viewer.sharedTargets(id).filter((r) => !listed(r));
  return new Proxy(viewer, {
    get: (target, prop) => (prop === "sharedTargets" ? shared : target[prop]),
  });
}

/** Per-class top-1, which is the diagnostic the aggregate hides. */
export function byClass(viewer, key, minMembers = 5) {
  const out = [];
  for (const [code, set] of key.members) {
    if (set.size < minMembers) continue;
    let scoreable = 0, hits = 0;
    for (const id of set) {
      const peers = key.peersOf(id);
      const rows = viewer.sharedTargets(id);
      if (!rows.some((r) => peers.has(r.molecule.id))) continue;
      scoreable++;
      if (rows.length && peers.has(rows[0].molecule.id)) hits++;
    }
    if (scoreable) out.push({ code, members: set.size, scoreable, top1: hits / scoreable });
  }
  out.sort((a, b) => a.top1 - b.top1 || a.code.localeCompare(b.code));
  return out;
}

export const pct = (x) => (x * 100).toFixed(1) + "%";
