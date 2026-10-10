// Loads viz/index.html's inline <script> into a sandbox so its functions can
// be tested directly.
//
// The viewer is deliberately one self-contained file that runs off file:// with
// no server and no build step (see the comment at the top of index.html), so
// there is no module to import. Splitting it into modules to make it testable
// would break the property that makes it shippable. Instead this reads the
// page, pulls out the one inline script, and evaluates it in a vm context with
// GRAPH_DATA injected and the handful of host objects it touches stubbed.
//
// That works because of two facts about the file, both load-bearing:
//   - every function is a top-level `function` declaration, so it lands on the
//     sandbox's global object and is reachable from here;
//   - the data enters through exactly one symbol, GRAPH_DATA (index.html:355).

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const INDEX = join(ROOT, "viz", "legacy", "index.html");

// The bare <script> on a line of its own. Anchored to line starts because the
// HTML comment at the top of index.html contains the literal text "<script>"
// mid-sentence, and a looser pattern matches that comment instead.
const SCRIPT_RE = /^<script>$\r?\n([\s\S]*?)\r?\n^<\/script>$/m;

function viewerSource() {
  const html = readFileSync(INDEX, "utf8");
  const m = html.match(SCRIPT_RE);
  if (!m) {
    throw new Error(
      "Could not find the inline <script> block in viz/index.html. If the " +
      "viewer was restructured, update SCRIPT_RE in tests/viewer_harness.mjs."
    );
  }
  return m[1];
}

// Everything the script touches at evaluation time. Kept as small as it is
// real: if the viewer starts using a new host API at load, it throws here
// rather than being quietly absent.
function makeSandbox(graphData) {
  const noop = () => {};
  const networkSelections = [];
  const element = () => ({
    style: {},
    innerHTML: "",
    addEventListener: noop,
    getAttribute: () => null,
    closest: () => null,
  });
  // Cached by id, unlike a bare `element()`: showGroup and friends write into
  // whatever `document.getElementById("detail")` returned at load time (index.html:1000)
  // and hold onto that reference, so a test that wants to read the HTML a
  // selection rendered has to be handed the same object back, not a fresh one.
  const elementsById = new Map();
  const getElementById = id => {
    if (!elementsById.has(id)) elementsById.set(id, element());
    return elementsById.get(id);
  };

  class DataSet {
    constructor(items) { this.items = items; this.updates = []; }
    update(items) { this.updates.push(items); }
  }
  class Network {
    constructor() { this.handlers = {}; }
    on(name, fn) { this.handlers[name] = fn; }
    unselectAll() {}
    selectNodes(ids) { networkSelections.push([...ids]); }
    fit() {}
  }

  return {
    GRAPH_DATA: graphData,
    vis: { DataSet, Network },
    document: { getElementById },
    window: { location: { href: "https://example.invalid/viz/index.html" } },
    // Not a JS intrinsic - safeUrl() needs it, and a fresh vm context has no
    // web APIs at all.
    URL,
    console,
    networkSelections,
  };
}

/**
 * Evaluate the viewer against a graph and return its sandbox. Every top-level
 * function is a property of the returned object.
 *
 * Re-evaluated per call rather than shared, because rawNodes/rawEdges are
 * `const`s captured at load (index.html:355-356) - so a different graph means
 * a different load, and tests cannot leak state into each other.
 */
export function loadViewer(graphData = { nodes: [], edges: [] }) {
  const ctx = vm.createContext(makeSandbox(graphData));
  vm.runInContext(viewerSource(), ctx, { filename: "viz/index.html" });
  return ctx;
}

// ---------------------------------------------------------------------------
// Fixture builders. Field names mirror export_graph.py's output exactly; the
// viewer reads these keys and nothing else.
// ---------------------------------------------------------------------------

export function measurement(over = {}) {
  return {
    counted: 1,
    role: "binding",
    // `name`, not `source_name`: export_graph.py joins sources.name into the
    // measurement row under that key and the viewer reads `m.name`. The
    // fixture said source_name, so every measurement in these tests rendered
    // its database as the empty string.
    name: "ChEMBL",
    affinity_type: "Ki",
    value: 100,
    units: "nM",
    external_ref: null,
    citation_url: null,
    citation_text: null,
    assay_description: null,
    ...over,
  };
}

export function edge(over = {}) {
  return {
    id: "int_1",
    from: "mol_a",
    to: "tgt_x",
    action_type: "inhibitor",
    is_primary_mechanism: 0,
    n_measurements: 1,
    functional_n_measurements: null,
    binding_value: null,
    binding_type: null,
    binding_units: null,
    measurements: [],
    sources: [{ name: "ChEMBL" }],
    ...over,
  };
}

export function molecule(id, label, over = {}) {
  return { id, label, type: "molecule", ...over };
}

export function target(id, label, over = {}) {
  return { id, label, type: "target", expressed_in_brain: null, ...over };
}

// A protein assembly (export_graph.py's `groups`), field names matching it
// exactly. `n_components` defaults to `members.length` - ChEMBL listing more
// subunits than this database holds an edge to is a real case (see showGroup)
// but not the default a fixture should have to opt out of.
export function group(id, name, over = {}) {
  const members = over.members || [];
  return {
    id,
    chembl_id: id.toUpperCase(),
    name,
    target_type: "PROTEIN COMPLEX",
    tier: "complex",
    n_components: members.length,
    // NULL is the honest default: most assemblies have no English article
    // reachable from any identifier ChEMBL supplies, so the map in
    // build_db.py leaves them blank rather than guessing.
    wikipedia_url: null,
    members,
    absorbed: [],
    ...over,
  };
}

/**
 * Rehydrate a value the sandbox produced into this realm.
 *
 * vm code builds its arrays and objects with its own realm's prototypes, so
 * assert.deepStrictEqual reports a prototype mismatch on values whose contents
 * are identical. Wrap anything that crossed the boundary before comparing it.
 */
export function plain(value) {
  return structuredClone(value);
}
