// Loads viz/index.html's inline <script> into a sandbox so the cohort viewer's
// functions can be tested without a browser.
//
// Same arrangement as the legacy harness it replaces, and for the same reason:
// the page is a single self-contained file that opens off file:// with no
// build step, so the tests read it rather than importing it. Every viewer
// function is a top-level declaration, and every piece of mutable state is
// reached through a function, so both land on the sandbox global.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const INDEX = join(ROOT, "viz", "index.html");

// Anchored to line starts: the comment at the top of index.html contains the
// literal text "<script src=...>", and an unanchored match would start there.
const SCRIPT_RE = /^<script>$\r?\n([\s\S]*?)\r?\n^<\/script>$/m;

export function viewerSource() {
  const html = readFileSync(INDEX, "utf8");
  const m = html.match(SCRIPT_RE);
  if (!m) {
    throw new Error(
      "Could not find the inline <script> block in viz/index.html. If the " +
      "viewer was restructured, update SCRIPT_RE in tests/cohort_harness.mjs.");
  }
  return m[1];
}

export function viewerHtml() {
  return readFileSync(INDEX, "utf8");
}

function stubElement() {
  return {
    style: {}, innerHTML: "", textContent: "", hidden: false, value: "",
    addEventListener() {}, appendChild() {}, setAttribute() {},
    getAttribute() { return null; }, closest() { return null; },
  };
}

// Exported for the similarity harness in analysis/similarity_harness/, which
// sweeps the scoring constants. Two of the three are top-level `const`s, and a
// top-level `const` lives in the script's lexical scope rather than on the
// sandbox global, so it cannot be reached or rebound from outside: the only way
// to vary it is to patch the source text before running it. That needs a
// sandbox around a source string this module did not read, which is what
// loadViewer cannot offer and this can.
//
// The page loads two data files, graph.data.js and gtopdb.data.js (GtoPdb's
// part, kept apart for its licence). A catalogue object carries the second
// under this key, so every caller that hands one catalogue to the viewer hands
// it both, and one without it is a page whose GtoPdb file did not load.
export const GTOPDB_FILE = Symbol("gtopdb.data.js");
// DrugCentral's file (D24), carried the same way.
export const DRUGCENTRAL_FILE = Symbol("drugcentral.data.js");

export function makeSandbox(data, options = {}) {
  const elements = new Map();
  const created = [];
  // Recorded, not run. The two popovers in the top bar are dismissed from
  // document-level handlers, and a test needs to read that they were bound,
  // in which phase, and to fire them itself.
  const documentListeners = [];
  // The viewer holds its network and its DataSets in `let` bindings, which a
  // vm script does not put on the global, so a test cannot reach what a
  // selection actually wrote onto the canvas. Every constructed network is
  // recorded here instead, with its DataSets hanging off it.
  const networks = [];
  const ctx = {
    COHORT_DATA: data,
    ...(data && data[GTOPDB_FILE] ? { COHORT_GTOPDB: data[GTOPDB_FILE] } : {}),
    ...(data && data[DRUGCENTRAL_FILE] ? { COHORT_DRUGCENTRAL: data[DRUGCENTRAL_FILE] } : {}),
    console,
    URL,
    performance: { now: () => 0 },
    Math, JSON, Number, String, Array, Object, Map, Set, Boolean, Date, RegExp, Error,
    vis: {
      // Enough of a DataSet to record what the viewer writes: the canvas is
      // now drawn once per filter setting and only *updated* on a selection,
      // so a stub that ignores update() would hide the whole highlight.
      DataSet: class {
        constructor(rows) { this.rows = (rows || []).slice(); }
        add(rows) { this.rows = this.rows.concat(rows); }
        clear() { this.rows = []; }
        update(rows) {
          for (const r of [].concat(rows)) {
            const i = this.rows.findIndex((x) => x.id === r.id);
            if (i < 0) this.rows.push(r);
            else this.rows[i] = Object.assign({}, this.rows[i], r);
          }
        }
        get(id) { return this.rows.find((x) => x.id === id) || null; }
      },
      Network: class {
        constructor(container, data, options) {
          networks.push(this);
          this.handlers = {};
          this.options = options || {};
          this.selection = { nodes: [], edges: [] };
          this.scale = 1;
          this.data = data;
        }
        // Every node the canvas already holds, at a position the caller can
        // recognise: a re-solve carries the old positions over, and a stub
        // that returned nothing would let that silently stop happening.
        getPositions() {
          if (this.positions) return this.positions;
          const out = {};
          for (const n of (this.data && this.data.nodes ? this.data.nodes.rows : [])) {
            out[n.id] = { x: 100, y: 200 };
          }
          return out;
        }
        on(name, fn) { this.handlers[name] = fn; }
        once(name, fn) { this.handlers[name] = fn; }
        off(name) { delete this.handlers[name]; }
        setOptions(o) { Object.assign(this.options, o); }
        // Recorded, not run. vis blocks redrawing for the whole of a real
        // stabilization and reports back through an event; the test fires that
        // event itself so the solve and the glide can be read a step at a time.
        stabilize(iterations) {
          this.stabilizeCalls = (this.stabilizeCalls || []).concat(iterations);
        }
        // Whatever the node data says, which is how a real network answers once
        // physics is off and positions are being written through the DataSet.
        finishStabilizing(positions) {
          this.positions = positions;
          if (this.handlers.stabilizationIterationsDone) {
            this.handlers.stabilizationIterationsDone();
          }
        }
        setSelection(s) { this.selection = s; }
        getScale() { return this.scale; }
        fit() {}
      },
    },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, stubElement());
        return elements.get(id);
      },
      createElement(tag) {
        const el = stubElement();
        el.tag = tag;
        created.push(el);
        return el;
      },
      head: { appendChild() {} },
      addEventListener(name, fn, capture) {
        documentListeners.push({ name: name, fn: fn, capture: !!capture });
      },
    },
    window: { location: { href: "file:///viz/index.html" }, addEventListener() {} },
  };
  // Opt-in, so every existing caller keeps the bare window above. A test of the
  // shareable links has to open the page at a fragment, read what the page
  // writes back with replaceState, and fire hashchange itself, so the window
  // gets a hash, a history that updates the location the way a browser does,
  // and listeners that are recorded rather than dropped.
  if (options.hash !== undefined) {
    const replaceStates = [];
    const windowListeners = [];
    const loc = { href: "file:///viz/index.html" + options.hash, hash: options.hash };
    ctx.window = {
      location: loc,
      history: {
        replaceState(state, title, url) {
          replaceStates.push({ state: state, title: title, url: url });
          loc.href = String(url);
          const i = loc.href.indexOf("#");
          loc.hash = i < 0 ? "" : loc.href.slice(i);
        },
      },
      addEventListener(name, fn) { windowListeners.push({ name: name, fn: fn }); },
    };
    ctx.__replaceStates = replaceStates;
    ctx.__windowListeners = windowListeners;
  }
  // Recorded rather than run. The viewer caps a filter re-solve on the clock,
  // and a test needs to read that the cap was armed and at what delay without
  // waiting a second for it - or leaving a live timer behind in a realm the
  // test has finished with.
  const timers = [];
  ctx.setTimeout = function (fn, ms) { timers.push({ fn: fn, ms: ms }); return timers.length; };
  ctx.clearTimeout = function (id) {
    if (id >= 1 && timers[id - 1]) timers[id - 1].cleared = true;
  };
  ctx.__timers = timers;
  // Frames are queued rather than run, for the same reason as the timers: the
  // glide after a re-solve is a decision about where nodes end up, and a test
  // should be able to step it without a clock or a renderer.
  const frames = [];
  ctx.requestAnimationFrame = function (fn) { frames.push(fn); return frames.length; };
  ctx.__frames = frames;
  ctx.globalThis = ctx;
  ctx.__elements = elements;
  ctx.__created = created;
  ctx.__documentListeners = documentListeners;
  ctx.__networks = networks;
  return vm.createContext(ctx);
}

// A fresh realm per call, because the viewer builds its indexes once from
// COHORT_DATA at load - a different catalogue means a different page.
export function loadViewer(data = emptyData(), options = {}) {
  const ctx = makeSandbox(data, options);
  vm.runInContext(viewerSource(), ctx, { filename: "viz/index.html" });
  return ctx;
}

export function emptyData() {
  return buildData({});
}

// ---------------------------------------------------------------------------
// Fixture builders. The field lists mirror scripts/cohort/export.py exactly;
// a test that passes here with a different order would be testing nothing.
// ---------------------------------------------------------------------------

export const MOLECULE_FIELDS = [
  "id", "chembl_id", "name", "molecule_type", "in_cohort", "is_seed",
  "route_atc_n", "route_indication", "admission_reason", "evidence_status",
  "scope_reasons", "n_claims_supported", "n_claims_preliminary", "n_claims_limited",
  "n_observations", "structure_type", "max_phase", "first_approval",
  "molecular_formula", "molecular_weight", "atc_level5", "atc_flags",
  "identity_flags", "seed_name", "gap_reason", "exclusion_reason", "smiles",
  "inchikey", "wikipedia_url", "n_indications_chembl", "synonyms", "aliases",
  "approved_elsewhere", "approval_status", "max_phase_checked",
  "trial_sites", "trial_countries", "withdrawals",
];

export const TARGET_FIELDS = [
  "chembl_id", "name", "target_type", "organism", "tax_id", "n_components",
  "wikipedia_url", "components", "human_orthologue",
];

export const CLAIM_FIELDS = [
  "id", "molecule", "target", "role", "basis", "tier", "tier_reason",
  "curated_support", "multiple_study_support", "n_measurements", "n_studies",
  "n_publications", "endpoints", "n_rows", "n_bounds", "n_conditional",
  "n_unresolved", "n_patents", "n_datasets", "assignment_classes",
  "supporting_endpoint_class", "action_type", "direct_interaction",
  "conflict_action", "conflict_dispersion", "mechanism_of_action", "conflict_detail",
  "action_exclusion",
];

export const ENDPOINT_FIELDS = [
  "endpoint_class", "n_measurements", "median_nm", "n_studies", "n_publications",
  "supported", "n_rows", "min_nm", "max_nm", "log_spread",
];

export const OBSERVATION_FIELDS = [
  "activity_id", "claim_id", "molecule", "target", "role", "endpoint_class",
  "standard_type", "standard_relation", "standard_value", "standard_units",
  "value_nm", "value_status", "counted", "study", "assay_chembl_id",
  "assay_description", "basis", "assignment_class", "confidence_score",
  "relationship_type", "conversion_kind", "conversion_note",
  "material_basis_verified", "measured_full_mwt", "measured_form",
  "data_validity_comment", "potential_duplicate", "activity_comment",
  "assignment_reason", "exclusion_reason", "measured_chembl_id", "variant_id",
  "assay_type",
];

export const STUDY_FIELDS = [
  "study_key", "provenance_class", "pubmed_id", "year", "journal", "title",
  "doi", "patent_id", "doc_chembl_id",
];

// The same interning table the exporter uses, so fixtures encode the way real
// rows do.
const INTERNED = new Set([
  "molecule_type", "structure_type", "admission_reason", "scope_reasons",
  "atc_flags", "identity_flags", "evidence_status", "gap_reason", "target_type",
  "organism", "role", "basis", "tier", "tier_reason", "supporting_endpoint_class",
  "action_type", "assignment_classes", "endpoint_class", "standard_type",
  "standard_relation", "standard_units", "value_status", "conversion_kind",
  "assignment_class", "assignment_reason", "relationship_type", "assay_type",
  "data_validity_comment", "provenance_class", "journal", "exclusion_reason",
  "measured_form", "name", "mechanism_of_action", "assay_description",
  "conversion_note", "activity_comment", "phase_label", "mesh_heading",
  "seed_name", "note", "description", "gene_symbol", "mechanism_comment",
  "selectivity_comment", "gtp_type", "gtp_action", "selectivity",
  "trial_sites", "trial_countries",
]);

class Interner {
  constructor() { this.values = []; this.index = new Map(); }
  intern(v) {
    if (v === null || v === undefined) return null;
    const s = String(v);
    if (!this.index.has(s)) { this.index.set(s, this.values.length); this.values.push(s); }
    return this.index.get(s);
  }
}

function encodeRow(record, fields, strings) {
  const out = fields.map((f) => {
    const v = record[f] === undefined ? null : record[f];
    return (v !== null && INTERNED.has(f)) ? strings.intern(v) : v;
  });
  while (out.length && out[out.length - 1] === null) out.pop();
  return out;
}

export function molecule(over = {}) {
  return Object.assign({
    id: 1, chembl_id: "CHEMBL1", name: "ALPHA", molecule_type: "Small molecule",
    in_cohort: 1, is_seed: 0, route_atc_n: 1, route_indication: 0,
    admission_reason: "route_atc_n", evidence_status: "has_supported",
    scope_reasons: "core", n_claims_supported: 1, n_claims_preliminary: 0,
    n_claims_limited: 0, n_observations: 1, synonyms: [], aliases: [],
  }, over);
}

export function target(over = {}) {
  return Object.assign({
    chembl_id: "CHEMBLT1", name: "Target one", target_type: "SINGLE PROTEIN",
    organism: "Homo sapiens", tax_id: 9606, n_components: 1, components: [],
  }, over);
}

export function endpoint(over = {}) {
  return Object.assign({
    endpoint_class: "binding:Ki", n_measurements: 2, median_nm: 100, n_studies: 2,
    n_publications: 2, supported: 1, n_rows: 2, min_nm: 50, max_nm: 200, log_spread: 0.6,
  }, over);
}

export function claim(over = {}) {
  return Object.assign({
    id: 1, molecule: 1, target: "CHEMBLT1", role: "binding", basis: "human_direct",
    tier: "supported", tier_reason: "multiple_study_support", curated_support: 0,
    multiple_study_support: 1, n_measurements: 2, n_studies: 2, n_publications: 2,
    n_rows: 2, n_bounds: 0, n_conditional: 0, n_unresolved: 0, n_patents: 0,
    n_datasets: 0, assignment_classes: "human_single_protein",
    supporting_endpoint_class: "binding:Ki", endpoints: [endpoint()],
  }, over);
}

export function observation(over = {}) {
  return Object.assign({
    activity_id: 1, claim_id: 1, molecule: 1, target: "CHEMBLT1", role: "binding",
    endpoint_class: "binding:Ki", standard_type: "Ki", standard_relation: "=",
    standard_value: 100, standard_units: "nM", value_nm: 100, value_status: "exact",
    counted: 1, study: 0, assay_chembl_id: "CHEMBL_A1",
    assay_description: "Binding affinity", basis: "human_direct",
    assignment_class: "human_single_protein", assay_type: "B",
  }, over);
}

export function study(over = {}) {
  return Object.assign({
    study_key: "pmid:1", provenance_class: "publication", pubmed_id: 1, year: 2020,
    journal: "J Test", title: "A study",
  }, over);
}

export function buildData({ molecules = [], targets = [], claims = [],
                            indications = {}, trial_status = {}, classes = null,
                            meta = {} } = {}) {
  const strings = new Interner();
  const encodedMolecules = molecules.map((m) => {
    const copy = Object.assign({}, m);
    copy.synonyms = (m.synonyms || []).map((s) => strings.intern(s));
    copy.aliases = (m.aliases || []).map((s) => strings.intern(s));
    // D24: withdrawals as [countries, year, classes] with the two strings
    // interned, as the exporter writes them; left off when absent.
    copy.withdrawals = m.withdrawals
      ? m.withdrawals.map((w) => [strings.intern(w[0]), w[1] || null,
                                  w[2] ? strings.intern(w[2]) : null])
      : null;
    return encodeRow(copy, MOLECULE_FIELDS, strings);
  });
  const encodedTargets = targets.map((t) => {
    const copy = Object.assign({}, t);
    // protein_class travels as an optional fourth field, as the exporter
    // writes it: absent on a database that predates it.
    copy.components = (t.components || []).map((c) => {
      const row = [c.accession, strings.intern(c.gene_symbol), strings.intern(c.description)];
      if (c.protein_class) row.push(strings.intern(c.protein_class));
      return row;
    });
    return encodeRow(copy, TARGET_FIELDS, strings);
  });
  const encodedClaims = claims.map((c) => {
    const copy = Object.assign({}, c);
    copy.endpoints = (c.endpoints || []).map((e) => encodeRow(e, ENDPOINT_FIELDS, strings));
    return encodeRow(copy, CLAIM_FIELDS, strings);
  });
  // Indications are interned the way the exporter writes them: [mesh_id,
  // heading, phase_label, scope_reasons, qualifies], with the middle three as
  // dictionary indices. A fixture that skipped this would be testing a format
  // the exporter never produces.
  const encodedIndications = {};
  // D23's two optional places follow: the approval basis (interned), and the
  // unapproved labels as [set id, title, labeler, categories, from, until]
  // with the three strings interned; both left off when absent, as exported.
  const opt = (v) => (v === undefined || v === null ? null : strings.intern(v));
  for (const [key, rows] of Object.entries(indications)) {
    encodedIndications[key] = rows.map((r) => {
      const row = [r[0], strings.intern(r[1]), strings.intern(r[2]), strings.intern(r[3]),
                   r[4], opt(r[5]), opt(r[6]),
                   r[7] ? r[7].map((l) => [l[0], opt(l[1]), opt(l[2]), opt(l[3]),
                                           l[4] || null, l[5] || null]) : null,
                   // D24: the ATC classes ('|'-joined) and an unread label's reason
                   opt(r[8]), opt(r[9])];
      while (row.length > 5 && row[row.length - 1] === null) row.pop();
      return row;
    });
  }
  // Trial status as the exporter writes it: nct -> [status, why_stopped?] for
  // a row fetched before phases were recorded, or [status, why_stopped,
  // phases, outcomes, start year?, end year?, planned?, countries?] after,
  // where outcomes is null (no results posted) or [[title, [p, ...]], ...].
  // Strings interned, p-values verbatim, years and the planned flags passed
  // through; countries ('|'-joined, or null for a record listing no site)
  // interned at index 7.
  const encodedTrials = {};
  for (const [nct, r] of Object.entries(trial_status)) {
    if (r.length > 2) {
      encodedTrials[nct] = [strings.intern(r[0]), r[1] ? strings.intern(r[1]) : null,
        r[2] ? strings.intern(r[2]) : null,
        r[3] === null ? null : r[3].map((o) => [strings.intern(o[0]), o[1]]),
        ...r.slice(4, 7)];
      if (r.length > 7) {
        while (encodedTrials[nct].length < 7) encodedTrials[nct].push(null);
        encodedTrials[nct].push(r[7] ? strings.intern(r[7]) : null);
      }
    } else {
      encodedTrials[nct] = r[1] ? [strings.intern(r[0]), strings.intern(r[1])]
                                : [strings.intern(r[0])];
    }
  }
  // Classes as the exporter writes them: labels as source -> code -> [level,
  // label, parents?], and per molecule [source, code, subgroup?, label?], labels
  // interned. Left out entirely when a test passes none, as an export from
  // before the classes existed would.
  let encodedClasses;
  if (classes) {
    encodedClasses = { fields: ["source", "code", "subgroup", "label"], labels: {}, molecules: {} };
    for (const [source, codes] of Object.entries(classes.labels || {})) {
      encodedClasses.labels[source] = {};
      for (const [code, [level, label, parents]] of Object.entries(codes)) {
        const row = [level, label == null ? null : strings.intern(label)];
        if (parents && parents.length) row.push(parents);
        encodedClasses.labels[source][code] = row;
      }
    }
    for (const [id, rows] of Object.entries(classes.molecules || {})) {
      encodedClasses.molecules[id] = rows.map((r) => {
        const row = [r[0], r[1], r[2] || null, r[3] == null ? null : strings.intern(r[3])];
        while (row.length && row[row.length - 1] === null) row.pop();
        return row;
      });
    }
    // Each structure-classed molecule's own MeSH record, which the exporter
    // reads off the carriers.
    if (classes.mesh_record) encodedClasses.mesh_record = { ...classes.mesh_record };
  }
  return {
    format: "cohort1/2",
    evidence_dir: "evidence",
    meta,
    ...(encodedClasses ? { classes: encodedClasses } : {}),
    fields: { molecules: MOLECULE_FIELDS, targets: TARGET_FIELDS,
              claims: CLAIM_FIELDS, endpoints: ENDPOINT_FIELDS },
    counts: { molecules: encodedMolecules.length, targets: encodedTargets.length,
              claims_drawable: encodedClaims.length },
    molecules: encodedMolecules,
    targets: encodedTargets,
    claims: encodedClaims,
    indications: encodedIndications,
    trial_status: encodedTrials,
    exclusions: [],
    source_coverage: [],
    validation: [],
    strings: strings.values,
  };
}

export const GTOPDB_FIELDS = [
  "molecule", "target", "action_type", "gtp_type", "gtp_action", "primary_target",
  "endogenous", "gtp_ligand_id", "gtp_target_id", "selectivity", "pubmed_ids",
];

// gtopdb.data.js the way scripts/cohort/export.py writes it, with its own
// strings: GtoPdb's actions, its `gtopdb`-role claims, and molecule id ->
// [evidence_status, gap_reason] where those claims change ChEMBL's status.
// `generated` must equal the catalogue's for the page to merge it; buildData
// sets none, so by default neither does this.
export function buildGtopdb({ actions = [], claims = [], status = {}, release = "2026.3",
                              generated = undefined } = {}) {
  const strings = new Interner();
  return {
    format: "cohort1-gtopdb/1",
    ...(generated === undefined ? {} : { generated }),
    release,
    fields: { actions: GTOPDB_FIELDS, claims: CLAIM_FIELDS },
    actions: actions.map((a) => encodeRow(a, GTOPDB_FIELDS, strings)),
    claims: claims.map((c) => encodeRow(Object.assign({}, c, { endpoints: [] }), CLAIM_FIELDS, strings)),
    status,
    strings: strings.values,
  };
}

// A catalogue carrying its GtoPdb file, as the page loads the two together.
export function withGtopdbFile(data, gtopdb) {
  data[GTOPDB_FILE] = gtopdb;
  return data;
}

// A catalogue carrying drugcentral.data.js (D24): molecule id -> [[agency,
// year], ...]. `generated` must equal the catalogue's for the page to merge it.
export function withDrugcentralFile(data, approvals, { release = "v56, 2026-09-02",
                                                       generated = data.generated } = {}) {
  data[DRUGCENTRAL_FILE] = { format: "cohort1-drugcentral/1", generated, release, approvals };
  return data;
}

// Build one evidence shard the way scripts/cohort/export.py writes it, so a
// test can hand it to registerEvidence exactly as a loaded script would.
export function buildShard({ molecule: mol = 1, observations = [], studies = [],
                             claims = [], claim_studies = [], curated = [] } = {}) {
  const strings = new Interner();
  return {
    molecule: mol,
    fields: {
      observations: OBSERVATION_FIELDS, studies: STUDY_FIELDS,
      claim_studies: ["claim_id", "endpoint_class", "study", "n_measurements", "n_rows"],
      curated: ["claim_id", "mec_id", "action_type", "mechanism_of_action",
                "direct_interaction", "n_refs", "tier", "tier_reason", "refs",
                "mechanism_comment", "selectivity_comment"],
      claims: CLAIM_FIELDS, endpoints: ENDPOINT_FIELDS,
    },
    observations: observations.map((o) => encodeRow(o, OBSERVATION_FIELDS, strings)),
    studies: studies.map((s) => encodeRow(s, STUDY_FIELDS, strings)),
    claim_studies: claim_studies.map((c) => encodeRow(
      c, ["claim_id", "endpoint_class", "study", "n_measurements", "n_rows"], strings)),
    claims: claims.map((c) => {
      const copy = Object.assign({}, c);
      copy.endpoints = (c.endpoints || []).map((e) => encodeRow(e, ENDPOINT_FIELDS, strings));
      return encodeRow(copy, CLAIM_FIELDS, strings);
    }),
    curated: curated.map((c) => encodeRow(
      c, ["claim_id", "mec_id", "action_type", "mechanism_of_action",
          "direct_interaction", "n_refs", "tier", "tier_reason", "refs",
          "mechanism_comment", "selectivity_comment"], strings)),
    strings: strings.values,
  };
}

export function plain(value) {
  return structuredClone(value);
}
