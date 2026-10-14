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
// ATC level 4 is the WHO's own grouping, it is already in
// `molecules.atc_level5`, and it was written by people who had never heard of
// this project. It is not a grouping by how drugs work: WHO defines levels 3
// and 4 as "chemical, pharmacological or therapeutic" subgroups, and 42 of the
// key's 64 classes are chemical-structure groups (docs/SIMILARITY-LITERATURE.md
// §3.5). `atcRepairedKey` below reads it with that said.
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
 * -- and level 4 is the first five characters. WHO calls level 4 a "chemical,
 * pharmacological or therapeutic" subgroup, and in this key it is mostly the
 * first: N05AA and N05AC split the phenothiazines by side chain. This is the
 * headline key and stays as it is, so that its figure is comparable across
 * builds; `atcRepairedKey` is the one read with that defect answered.
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
    name: "atc", classesOf, members, labelled, names,
    // A molecule the key places somewhere, a class of one included: it has an
    // opinion of that molecule, which is that it is not the query's classmate.
    judged: (id) => classesOf.has(id),
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
    name: "mesh", classesOf, members, labelled, names, labelOf,
    judged: (id) => classesOf.has(id),
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

// ------------------------------------------------ keys read from the database

export const DATABASE = join(ROOT, "db", "cohort1.db");
export const ATC_REPAIRED = join(ROOT, "analysis", "similarity_harness", "atc_repaired.json");

/**
 * Class rows from db/cohort1.db, for keys the payload does not carry.
 *
 * Every ATC code left the payload when ATC came off the page (2026-09-26), and
 * the FDA classes were never on it, so these keys read the database, read-only.
 * The database must be the build the payload was exported from: a key from one
 * build grading a ranking from another would be a grade of neither, so a
 * mismatched `built_at` is refused rather than reported.
 *
 * Returns { byMolecule: Map(parent_molregno -> [{source, code, label}]),
 *           labels: Map("source:code" -> label) }.
 */
async function openDatabase(data, path) {
  if (!existsSync(path)) {
    throw new HarnessError(`${path} is not there; this key is read from the database.`);
  }
  const { DatabaseSync } = await import("node:sqlite");
  const db = new DatabaseSync(path, { readOnly: true });
  const built = db.prepare("SELECT value FROM build_manifest WHERE key = 'built_at'").get();
  const want = data.meta && data.meta.built_at;
  if (!built || !want || built.value !== want) {
    db.close();
    throw new HarnessError(
      `db/cohort1.db was built at ${built && built.value} but viz/graph.data.js ` +
      `was exported from the build of ${want}. Re-export, or grade the pair ` +
      "that belongs together.");
  }
  return db;
}

export async function readDbClasses(data, sources, path = DATABASE) {
  const db = await openDatabase(data, path);
  try {
    const marks = sources.map(() => "?").join(",");
    const byMolecule = new Map();
    for (const r of db.prepare(
      `SELECT parent_molregno, source, code, label FROM molecule_classes
       WHERE source IN (${marks}) ORDER BY parent_molregno, source, code`).all(...sources)) {
      if (!byMolecule.has(r.parent_molregno)) byMolecule.set(r.parent_molregno, []);
      byMolecule.get(r.parent_molregno).push({ source: r.source, code: r.code, label: r.label });
    }
    const labels = new Map();
    for (const r of db.prepare(
      `SELECT source, code, label FROM class_labels WHERE source IN (${marks})`).all(...sources)) {
      labels.set(`${r.source}:${r.code}`, r.label);
    }
    return { byMolecule, labels };
  } finally {
    db.close();
  }
}

/**
 * The repaired ATC key: docs/SIMILARITY-LITERATURE.md, step 1.
 *
 * Three changes from `labelledSet`, each answering a defect that section 3.6
 * lists, and none touching the ranking:
 *
 * - **Peers from every ATC level.** The questions are still the molecules with
 *   an N code, but a peer is anyone sharing a level-4 class at any anatomical
 *   level. The headline key reads `molecules.atc_level5`, which holds only N
 *   codes because it is the admission route's record, so a classmate filed
 *   under S01FA (scopolamine and atropine) was invisible to it.
 * - **A documented exclusion list** (atc_repaired.json) beside the X rule:
 *   residual classes filed under another letter, classes grouped by use, and
 *   classes that are not pharmacological. Each entry carries its reason.
 * - **Graded credit.** `gain` is 1 for a shared level-4 class and 0.5 for a
 *   shared level-3 group only, so a sibling-class answer (thioridazine for
 *   chlorpromazine, N05AC against N05AA) is worth something in nDCG without
 *   changing what top-1 or MRR count.
 *
 * `judged` is any molecule the key places at level 4 or level 3: one it places
 * only under an excluded class, or under none, is a molecule it has no opinion
 * of, and the filtered walk steps past it.
 */
export async function atcRepairedKey(data, { path = DATABASE, config = ATC_REPAIRED } = {}) {
  const spec = JSON.parse(readFileSync(config, "utf8"));
  const ex4 = new Set(Object.keys(spec.excluded_level4 || {}));
  const ex3 = new Set(Object.keys(spec.excluded_level3 || {}));
  const { byMolecule, labels } = await readDbClasses(data, ["atc"], path);

  const F = data.fields.molecules;
  const idI = F.indexOf("id"), nameI = F.indexOf("name");
  const names = new Map(data.molecules.map((r) => [r[idI], str(data, r[nameI])]));

  const classesOf = new Map(), members = new Map(), groupsOf = new Map(), hasN = new Set();
  for (const [id, rows] of byMolecule) {
    if (!names.has(id)) continue;          // only what the payload can rank
    for (const { code } of rows) {
      if (code.length < 5) continue;
      const l4 = code.slice(0, 5), l3 = code.slice(0, 4);
      if (ex4.has(l4)) continue;
      // Level 3 credit survives a level-4 X (mirtazapine, N06AX, is still an
      // antidepressant) but not a level-3 X or a listed level-3 group.
      if (l3[3] !== "X" && !ex3.has(l3)) {
        if (!groupsOf.has(id)) groupsOf.set(id, new Set());
        groupsOf.get(id).add(l3);
      }
      if (l4[4] === "X") continue;
      if (!classesOf.has(id)) classesOf.set(id, new Set());
      classesOf.get(id).add(l4);
      if (!members.has(l4)) members.set(l4, new Set());
      members.get(l4).add(id);
      if (l4[0] === "N") hasN.add(id);
    }
  }
  for (const [code, set] of [...members]) if (set.size < 2) members.delete(code);

  // A question asks about one of its N classes; a peer may come through any
  // class the two share, N or not.
  const labelled = [...hasN]
    .filter((id) => [...classesOf.get(id)].some((c) => c[0] === "N" && members.has(c)))
    .sort((a, b) => a - b);
  if (!labelled.length) {
    throw new HarnessError("the repaired ATC key is empty: is molecule_classes backfilled? " +
      "Run scripts/resolve_cohort_classes.py.");
  }
  const peersOf = (id) => {
    const out = new Set();
    for (const code of classesOf.get(id) || []) {
      if (!members.has(code)) continue;
      for (const other of members.get(code)) if (other !== id) out.add(other);
    }
    return out;
  };
  const shareGroup = (a, b) => {
    const x = groupsOf.get(a), y = groupsOf.get(b);
    if (!x || !y) return false;
    for (const g of x) if (y.has(g)) return true;
    return false;
  };
  return {
    name: "atc-repaired", version: spec.version,
    classesOf, members, labelled, names,
    labelOf: (code) => labels.get(`atc:${code}`) || code,
    judged: (id) => classesOf.has(id) || groupsOf.has(id),
    peersOf,
    gain(query, peers, other) {
      if (peers.has(other)) return 1;
      return shareGroup(query, other) ? 0.5 : 0;
    },
  };
}

export const FDA_KEYS = join(ROOT, "analysis", "similarity_harness", "fda_keys.json");

/**
 * FDA's classes as answer keys: docs/SIMILARITY-LITERATURE.md, step 2.
 *
 * A separate curator from WHO and from ChEMBL - FDA's Established Pharmacologic
 * Class, mechanism of action and physiologic effect, indexed from the US label
 * and reached by identifier alone (scripts/resolve_cohort_fda_classes.py). It
 * is not independent of the score's inputs: EPC and MoA restate mechanism, as
 * ChEMBL's curated mechanisms do. PE is an effect axis and the nearest thing
 * here to "acts alike" rather than "binds alike".
 *
 * `epc`: a classmate shares an EPC (gain 1); a molecule sharing only a MoA
 * earns 0.5, except through the MoA classes fda_keys.json lists as
 * pharmacokinetic or empty. `pe`: a classmate shares a PE, no graded credit.
 * Questions are every molecule with a classmate, as in the MeSH key, since FDA
 * classes are not limited to the nervous system. Only US-labelled drugs have
 * any, so coverage is reported as the harness always reports it, apart.
 */
export async function fdaKey(data, which, { path = DATABASE, config = FDA_KEYS } = {}) {
  const spec = JSON.parse(readFileSync(config, "utf8"));
  const patterns = Object.keys(spec.moa_no_credit_patterns || {});
  const named = new Set(Object.keys(spec.moa_no_credit_names || {}));
  const source = which === "pe" ? "fda_pe" : "fda_epc";
  const { byMolecule, labels } = await readDbClasses(data, [source, "fda_moa"], path);

  const F = data.fields.molecules;
  const idI = F.indexOf("id"), nameI = F.indexOf("name");
  const names = new Map(data.molecules.map((r) => [r[idI], str(data, r[nameI])]));
  const classesOf = new Map(), members = new Map(), moaOf = new Map();
  for (const [id, rows] of byMolecule) {
    if (!names.has(id)) continue;
    for (const { source: s, code, label } of rows) {
      if (s === source) {
        if (!classesOf.has(id)) classesOf.set(id, new Set());
        classesOf.get(id).add(code);
        if (!members.has(code)) members.set(code, new Set());
        members.get(code).add(id);
      } else if (which !== "pe" && !named.has(label) && !patterns.some((p) => label.includes(p))) {
        if (!moaOf.has(id)) moaOf.set(id, new Set());
        moaOf.get(id).add(code);
      }
    }
  }
  for (const [code, set] of [...members]) if (set.size < 2) members.delete(code);
  const labelled = [...classesOf.keys()]
    .filter((id) => [...classesOf.get(id)].some((c) => members.has(c)))
    .sort((a, b) => a - b);
  if (!labelled.length) {
    throw new HarnessError(`the ${which} key is empty: run scripts/resolve_cohort_fda_classes.py.`);
  }
  const peersOf = (id) => {
    const out = new Set();
    for (const code of classesOf.get(id) || []) {
      if (!members.has(code)) continue;
      for (const other of members.get(code)) if (other !== id) out.add(other);
    }
    return out;
  };
  const shareMoa = (a, b) => {
    const x = moaOf.get(a), y = moaOf.get(b);
    if (!x || !y) return false;
    for (const c of x) if (y.has(c)) return true;
    return false;
  };
  return {
    name: which, version: spec.version,
    classesOf, members, labelled, names,
    labelOf: (code) => labels.get(`${source}:${code}`) || code,
    judged: (id) => classesOf.has(id) || moaOf.has(id),
    peersOf,
    ...(which === "pe" ? {} : {
      gain(query, peers, other) {
        if (peers.has(other)) return 1;
        return shareMoa(query, other) ? 0.5 : 0;
      },
    }),
  };
}

export const ONSIDES_KEY = join(ROOT, "analysis", "similarity_harness", "onsides_key.json");

/**
 * Read one molecule's label profile, in a scope, from label_effects rows.
 * Exported for the tests: `rows` is [{parent_molregno, effect, n_labels}],
 * `labels` Map(parent -> its single-ingredient label count), `socsOf`
 * Map(effect -> Set of SOC codes), `scope` a Set of SOC codes or null for all.
 * An effect counts when `minLabels` labels list it, or every label a molecule
 * with fewer has.
 */
export function labelProfiles(rows, labels, socsOf, scope, minLabels) {
  const out = new Map();
  for (const r of rows) {
    const total = labels.get(r.parent_molregno);
    if (!total || r.n_labels < Math.min(minLabels, total)) continue;
    if (scope) {
      const socs = socsOf.get(r.effect);
      if (!socs || ![...socs].some((s) => scope.has(s))) continue;
    }
    if (!out.has(r.parent_molregno)) out.set(r.parent_molregno, new Set());
    out.get(r.parent_molregno).add(r.effect);
  }
  return out;
}

/**
 * Each profile's nearest neighbours by the cosine of IDF-weighted binary
 * profiles. `profiles` is Map(unit -> Set of effects); returns Map(unit ->
 * { peers: Set, half: Set }), the `peers` nearest with ties at the last
 * included, then up to `halfTo`, also with ties, each above zero.
 */
export function nearestByProfile(profiles, peers, halfTo) {
  const units = [...profiles.keys()];
  const df = new Map();
  for (const set of profiles.values()) for (const e of set) df.set(e, (df.get(e) || 0) + 1);
  const idf = new Map([...df].map(([e, n]) => [e, Math.log(units.length / n)]));
  const norm = new Map();
  for (const [u, set] of profiles) {
    let s = 0;
    for (const e of set) s += idf.get(e) ** 2;
    norm.set(u, Math.sqrt(s));
  }
  // An inverted index: only units sharing an effect can score above zero.
  const holders = new Map();
  for (const [u, set] of profiles) {
    for (const e of set) {
      if (!idf.get(e)) continue;
      if (!holders.has(e)) holders.set(e, []);
      holders.get(e).push(u);
    }
  }
  const cut = (sorted, k) => {
    if (sorted.length <= k) return sorted.length;
    let n = k;
    while (n < sorted.length && sorted[n][1] === sorted[k - 1][1]) n++;
    return n;
  };
  const out = new Map();
  for (const [u, set] of profiles) {
    const dot = new Map();
    for (const e of set) {
      const w = idf.get(e);
      if (!w) continue;
      for (const v of holders.get(e)) if (v !== u) dot.set(v, (dot.get(v) || 0) + w * w);
    }
    const nu = norm.get(u);
    const sims = [...dot]
      .map(([v, d]) => [v, nu && norm.get(v) ? d / (nu * norm.get(v)) : 0])
      .filter(([, s]) => s > 0)
      .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1));
    const p = cut(sims, peers);
    const h = Math.max(p, cut(sims, halfTo));
    out.set(u, { peers: new Set(sims.slice(0, p).map(([v]) => v)),
                 half: new Set(sims.slice(p, h).map(([v]) => v)) });
  }
  return out;
}

/**
 * Adverse effects on the label as an answer key: docs/SIMILARITY-LITERATURE.md,
 * step 3, and the first key that shares no input with the score.
 *
 * A molecule's profile is the set of effects at least two of its
 * single-ingredient labels list, or its only label (OnSIDES, through
 * scripts/resolve_cohort_label_effects.py), in the nervous-system and
 * psychiatric SOCs for `onsides` and in every SOC for `onsides-all`. Its
 * classmates are the molecules of the five nearest ingredients by IDF-weighted
 * cosine; the next five earn half in nDCG. Every value is in onsides_key.json,
 * fixed before the key first graded the ranking.
 *
 * Profiles are compared per RxNorm ingredient, not per molecule: haloperidol
 * and haloperidol decanoate reach one ingredient and share its labels, so
 * neither is the other's neighbour, and `judged(m, query)` steps past one in
 * the other's list. There are no classes, so `members` is empty and the
 * per-class table has nothing to show.
 *
 * Read it with the bias stated (SIMILARITY-LITERATURE §4.2): labels repeat
 * class boilerplate, which the IDF weight answers only in part, and a drug's
 * effects are confounded by what it is for.
 */
export async function onsidesKey(data, which = "onsides", { path = DATABASE, config = ONSIDES_KEY } = {}) {
  const spec = JSON.parse(readFileSync(config, "utf8"));
  const scopeSpec = spec.scopes[which];
  if (!scopeSpec) throw new HarnessError(`onsides_key.json has no scope ${which}`);
  const scope = scopeSpec.socs ? new Set(Object.keys(scopeSpec.socs)) : null;

  const db = await openDatabase(data, path);
  let molecules, rows, terms;
  try {
    const have = db.prepare(
      "SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name = 'label_effects'").get();
    if (!have.n) {
      throw new HarnessError("db/cohort1.db has no label_effects table: run " +
        "scripts/resolve_cohort_label_effects.py.");
    }
    molecules = db.prepare("SELECT parent_molregno, rxcui, n_labels FROM label_effect_molecules").all();
    rows = db.prepare("SELECT parent_molregno, effect, n_labels FROM label_effects").all();
    terms = db.prepare("SELECT DISTINCT effect, socs FROM label_effect_terms").all();
  } finally {
    db.close();
  }

  const F = data.fields.molecules;
  const idI = F.indexOf("id"), nameI = F.indexOf("name");
  const names = new Map(data.molecules.map((r) => [r[idI], str(data, r[nameI])]));

  // Per ingredient: its label count, and the molecules the payload can rank.
  const ingredientOf = new Map(), labels = new Map(), moleculesOf = new Map();
  for (const m of molecules) {
    if (!names.has(m.parent_molregno)) continue;
    ingredientOf.set(m.parent_molregno, m.rxcui);
    labels.set(m.rxcui, m.n_labels);
    if (!moleculesOf.has(m.rxcui)) moleculesOf.set(m.rxcui, []);
    moleculesOf.get(m.rxcui).push(m.parent_molregno);
  }
  const socsOf = new Map();
  for (const t of terms) {
    if (!socsOf.has(t.effect)) socsOf.set(t.effect, new Set());
    for (const s of (t.socs || "").split("|")) if (s) socsOf.get(t.effect).add(s);
  }
  // Rows are per molecule and identical across one ingredient's molecules, so
  // one molecule's rows stand for the ingredient.
  const firstOf = new Map([...moleculesOf].map(([ing, ms]) => [ing, Math.min(...ms)]));
  const ingRows = rows
    .filter((r) => ingredientOf.has(r.parent_molregno) &&
                   firstOf.get(ingredientOf.get(r.parent_molregno)) === r.parent_molregno)
    .map((r) => ({ ...r, parent_molregno: ingredientOf.get(r.parent_molregno) }));
  const profiles = labelProfiles(ingRows, labels, socsOf, scope, spec.min_labels);
  for (const [ing, set] of [...profiles]) if (set.size < spec.min_effects) profiles.delete(ing);
  if (!profiles.size) {
    throw new HarnessError(`the ${which} key is empty: run scripts/resolve_cohort_label_effects.py.`);
  }
  const nearest = nearestByProfile(profiles, spec.peers, spec.half_credit_to);

  const expand = (ings) => {
    const out = new Set();
    for (const ing of ings) for (const m of moleculesOf.get(ing)) out.add(m);
    return out;
  };
  const peersOf = (id) => {
    const n = nearest.get(ingredientOf.get(id));
    return n ? expand(n.peers) : new Set();
  };
  const halfOf = (id) => {
    const n = nearest.get(ingredientOf.get(id));
    return n ? expand(n.half) : new Set();
  };
  const labelled = [...ingredientOf.keys()]
    .filter((id) => profiles.has(ingredientOf.get(id)) && peersOf(id).size)
    .sort((a, b) => a - b);
  return {
    name: which, version: spec.version,
    classesOf: new Map(), members: new Map(), labelled, names,
    profiles: new Map(labelled.map((id) => [id, profiles.get(ingredientOf.get(id))])),
    ingredientOf,
    judged: (m, query) => profiles.has(ingredientOf.get(m)) &&
      (query === undefined || ingredientOf.get(m) !== ingredientOf.get(query)),
    peersOf,
    gain(query, peers, other) {
      if (peers.has(other)) return 1;
      return halfOf(query).has(other) ? 0.5 : 0;
    },
  };
}

/**
 * Every answer key by the name `--key` takes. The headline is `atc`, and it
 * stays the headline: a new key reports beside it, never in its place
 * (docs/SIMILARITY-LITERATURE.md §4.3).
 */
export const KEYS = {
  atc: { title: "ATC level-4 classes", load: (data) => labelledSet(data) },
  mesh: { title: "MeSH pharmacological actions", load: (data) => meshActionSet(data) },
  "atc-repaired": { title: "the repaired ATC key", load: (data) => atcRepairedKey(data) },
  epc: { title: "FDA Established Pharmacologic Classes", load: (data) => fdaKey(data, "epc") },
  pe: { title: "FDA physiologic effects", load: (data) => fdaKey(data, "pe") },
  onsides: { title: "nervous-system and psychiatric effects on the label (OnSIDES)",
    load: (data) => onsidesKey(data, "onsides") },
  "onsides-all": { title: "every effect on the label (OnSIDES)",
    load: (data) => onsidesKey(data, "onsides-all") },
};

export async function loadKey(name, data) {
  if (!KEYS[name]) {
    throw new HarnessError(`unknown --key ${name}; use ${Object.keys(KEYS).join(", ")}.`);
  }
  return await KEYS[name].load(data);
}

// ------------------------------------------------------------------- the grade

/**
 * Walk each labelled molecule's ranking to its first same-class peer.
 *
 * `unanswerable` is the count of molecules with no peer anywhere in the list,
 * and it is kept out of every rate rather than scored as a failure. See the
 * third decision at the top of this file: it is the one that stops a sweep
 * rewarding coverage and calling it ranking.
 *
 * Two readings sit beside the headline rates, over the same scoreable
 * molecules, and neither changes them (docs/SIMILARITY-LITERATURE.md, step 1):
 *
 * - `filtered`: the same walk past only the molecules the key can judge
 *   (`key.judged`). A molecule the key has no class for - seltorexant, which
 *   has no ATC code, above suvorexant's classmates - is neither right nor
 *   wrong, so it may not stand between a query and its classmate. This is the
 *   "filtered" setting of link-prediction evaluation (Bordes et al. 2013).
 * - `ndcg`: nDCG@10 (Jarvelin & Kekalainen 2002), with `key.gain` where a key
 *   grades its answers (1 for a classmate, 0.5 for a sibling class) and 1 or 0
 *   where it does not. The ideal ordering is built from the molecules the list
 *   holds, not from every classmate in the catalogue, so a classmate ChEMBL
 *   gives nothing to rank costs coverage, never ordering - the same line
 *   `unanswerable` draws.
 */
export const NDCG_K = 10;

function dcg(gains, k) {
  let s = 0;
  for (let i = 0; i < Math.min(k, gains.length); i++) s += gains[i] / Math.log2(i + 2);
  return s;
}

export function ndcgAt(gains, k) {
  const ideal = dcg([...gains].sort((a, b) => b - a), k);
  return ideal > 0 ? dcg(gains, k) / ideal : 0;
}

export function grade(viewer, key) {
  let scoreable = 0, top1 = 0, top5 = 0, top10 = 0, mrr = 0, unanswerable = 0;
  const f = { top1: 0, top5: 0, top10: 0, mrr: 0 };
  let ndcg = 0, ndcgF = 0;
  const ranks = new Map();
  const judged = key.judged || (() => true);
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

    const ids = rows.map((r) => r.molecule.id);
    // A key may judge a molecule differently per question: the label key
    // has no opinion of haloperidol decanoate in haloperidol's list.
    const kept = ids.filter((m) => judged(m, id));
    // A classmate is judged by construction (it is in one of the key's
    // classes), so the filtered list always still holds one.
    const fRank = kept.findIndex((m) => peers.has(m)) + 1;
    if (!fRank) throw new HarnessError(`${key.name}: a classmate of ${id} is not judged`);
    if (fRank === 1) f.top1++;
    if (fRank <= 5) f.top5++;
    if (fRank <= 10) f.top10++;
    f.mrr += 1 / fRank;
    const gain = key.gain ? (m) => key.gain(id, peers, m) : (m) => (peers.has(m) ? 1 : 0);
    ndcg += ndcgAt(ids.map(gain), NDCG_K);
    ndcgF += ndcgAt(kept.map(gain), NDCG_K);
  }
  return {
    scoreable, unanswerable, ranks,
    top1: top1 / scoreable, top5: top5 / scoreable, top10: top10 / scoreable,
    mrr: mrr / scoreable,
    ndcg: ndcg / scoreable,
    filtered: {
      top1: f.top1 / scoreable, top5: f.top5 / scoreable, top10: f.top10 / scoreable,
      mrr: f.mrr / scoreable, ndcg: ndcgF / scoreable,
    },
  };
}

/** Per-class top-1, which is the diagnostic the aggregate hides. */
export function byClass(viewer, key, minMembers = 5) {
  const out = [];
  // In the repaired ATC key a class can hold molecules that are only ever
  // peers (a non-N member of S01HA); only the questions are counted.
  const asked = new Set(key.labelled);
  for (const [code, set] of key.members) {
    if (set.size < minMembers) continue;
    let scoreable = 0, hits = 0;
    for (const id of set) {
      if (!asked.has(id)) continue;
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
