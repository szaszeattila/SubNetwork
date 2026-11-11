#!/usr/bin/env node
// Solve the page's opening picture once, ahead of time, and write where every
// node settled to viz/layout.data.js, which the page then draws as given
// instead of laying the network out in each reader's browser (2026-11-10, the
// user's call; docs/VIEWER.md, *The opening layout is solved ahead of time*).
//
// The solve is the page's own: viz/index.html is opened in headless Chrome
// over a local server that withholds any existing layout.data.js, the page
// lays itself out exactly as it does for a reader, and the settled positions
// are read back over the DevTools protocol. Nothing here re-implements the
// layout, so the file cannot drift from what the page would have drawn.
//
//   node scripts/build_layout.mjs             # solve and write (~30 s)
//   node scripts/build_layout.mjs --check     # exit 1 unless the file matches
//                                             # the data and the page on disk
//   node scripts/build_layout.mjs --if-stale  # solve only when --check fails
//
// The file records sha256 of graph.data.js, gtopdb.data.js and the page's one
// inline script, the three things the layout is computed from; --check
// compares them. The page itself checks only the export stamp and the filter
// signature, since it cannot hash what it loads. Needs Chrome or Chromium
// ($CHROME, else the first of the usual names on PATH) and Node 22.
import { createServer } from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const VIZ = join(ROOT, "viz");
const OUT = join(VIZ, "layout.data.js");
const FORMAT = "cohort1-layout/1";
const TIMEOUT_MS = 15 * 60 * 1000;

function sha256(buf) { return createHash("sha256").update(buf).digest("hex"); }

// The page's one inline script: the layout code, the physics settings and the
// filter defaults all live there, and the page's text and styles do not move a
// node, so editing About does not make the layout stale.
function inlineScript() {
  // Comments first, as scripts/csp.py does: the page's opening comment
  // mentions a <script> tag in prose.
  const html = readFileSync(join(VIZ, "index.html"), "utf8").replace(/<!--[\s\S]*?-->/g, "");
  const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  if (inline.length !== 1) throw new Error("expected one inline <script> in viz/index.html");
  return inline[0][1];
}

function currentInputs() {
  for (const f of ["graph.data.js", "gtopdb.data.js"]) {
    if (!existsSync(join(VIZ, f))) throw new Error("viz/" + f + " missing; run the export first");
  }
  return {
    graph_data: sha256(readFileSync(join(VIZ, "graph.data.js"))),
    gtopdb_data: sha256(readFileSync(join(VIZ, "gtopdb.data.js"))),
    page_script: sha256(inlineScript()),
  };
}

function readLayout() {
  if (!existsSync(OUT)) return null;
  const m = /^const COHORT_LAYOUT = (.*);$/m.exec(readFileSync(OUT, "utf8"));
  return m ? JSON.parse(m[1]) : null;
}

// Why the file on disk does not match, or null when it does.
function staleness() {
  const layout = readLayout();
  if (!layout) return "viz/layout.data.js is missing";
  if (layout.format !== FORMAT) return "viz/layout.data.js is format " + layout.format;
  const now = currentInputs();
  const changed = Object.keys(now).filter((k) => (layout.inputs || {})[k] !== now[k]);
  return changed.length ? "changed since the layout was solved: " + changed.join(", ") : null;
}

function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    const r = spawnSync("which", [name], { encoding: "utf8" });
    if (r.status === 0 && r.stdout.trim()) return r.stdout.trim();
  }
  throw new Error("no Chrome or Chromium found; set $CHROME");
}

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8" };

// viz/ as the hosted copy serves it, except that layout.data.js is withheld
// while solving, so the page lays itself out from nothing.
function serve(withholdLayout) {
  const server = createServer((req, res) => {
    const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = normalize(join(VIZ, path === "/" ? "index.html" : path));
    if (!file.startsWith(VIZ + sep) || (withholdLayout && file === OUT) || !existsSync(file)) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(readFileSync(file));
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "subnetwork-layout-"));
  const chrome = spawn(findChrome(), [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--remote-debugging-port=0", "--user-data-dir=" + profile, "--window-size=1600,1000",
    "about:blank",
  ], { stdio: "ignore" });
  const portFile = join(profile, "DevToolsActivePort");
  for (let i = 0; i < 200 && !existsSync(portFile); i++) await sleep(100);
  if (!existsSync(portFile)) throw new Error("Chrome did not start");
  const port = readFileSync(portFile, "utf8").split("\n")[0].trim();
  const targets = await (await fetch("http://127.0.0.1:" + port + "/json/list")).json();
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let next = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, fail } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) fail(new Error(msg.error.message)); else ok(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const id = ++next;
    pending.set(id, { ok, fail });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  };
  // Chrome is still writing its profile as it exits, so the profile goes once
  // it has gone; a cleanup failure never hides the error that led here.
  const exited = new Promise((ok) => chrome.once("exit", ok));
  const close = async () => {
    try { ws.close(); } catch {}
    chrome.kill();
    await Promise.race([exited, sleep(5000)]);
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 5 }); } catch {}
  };
  return { send, evaluate, close };
}

// The page is ready when it has drawn, settled and finished gliding; it says
// so by clearing its load line, as it does for a reader.
const READY = `(() => {
  const s = document.getElementById("load-status");
  if (s && s.classList.contains("failed")) return { failed: s.textContent };
  if (typeof network === "undefined" || !network || drawnSignature === null) return { wait: "loading" };
  if (s && s.textContent) return { wait: s.textContent };
  if (transition) return { wait: "gliding" };
  return { ready: true };
})()`;

async function openPage(browser, url) {
  const started = Date.now();
  await browser.send("Page.navigate", { url });
  let last = "";
  for (;;) {
    if (Date.now() - started > TIMEOUT_MS) throw new Error("the page did not settle in time");
    await sleep(500);
    let state;
    try { state = await browser.evaluate(READY); } catch { continue; }
    if (state.failed) throw new Error("the page reported: " + state.failed);
    if (state.ready) return Date.now() - started;
    if (state.wait !== last) { last = state.wait; process.stdout.write("  " + last + "\n"); }
  }
}

async function build() {
  const inputs = currentInputs();
  const browser = await launch();
  let server = await serve(true);
  try {
    const url = "http://127.0.0.1:" + server.address().port + "/index.html";
    console.log("solving the opening picture in headless Chrome…");
    const ms = await openPage(browser, url);
    const solved = await browser.evaluate(`JSON.stringify({
      generated: DATA.generated, signature: drawnSignature,
      opening: graphSignature() === drawnSignature &&
        Object.keys(filterDefaults()).every(function (k) {
          return JSON.stringify(filters[k]) === JSON.stringify(filterDefaults()[k]);
        }),
      positions: nodePositions(), drawn: visNodes.length })`).then(JSON.parse);
    if (!solved.opening) throw new Error("the page did not open on its default picture");
    const keys = Object.keys(solved.positions).sort();
    const positions = {};
    for (const k of keys) {
      const p = solved.positions[k];
      positions[k] = [Math.round(p.x * 10) / 10, Math.round(p.y * 10) / 10];
    }
    console.log("solved in " + (ms / 1000).toFixed(1) + " s: " + keys.length + " positions");

    const layout = { format: FORMAT, generated: solved.generated, signature: solved.signature,
                     solved_at: new Date().toISOString().slice(0, 19), inputs, positions };
    const text =
      "// Generated by scripts/build_layout.mjs - do not edit.\n" +
      "// SubNetwork: where each node of the page's opening picture is drawn, solved\n" +
      "// ahead of time from graph.data.js and gtopdb.data.js by the page's own layout.\n" +
      "// It holds none of their records - node keys and canvas coordinates only - and\n" +
      "// the page uses it only with the export it was solved from (generated).\n" +
      "const COHORT_LAYOUT = " + JSON.stringify(layout) + ";\n";
    writeFileSync(OUT + ".tmp", text);
    renameSync(OUT + ".tmp", OUT);
    console.log("wrote viz/layout.data.js (" + (text.length / 1024).toFixed(0) + " KB)");

    // Open it again with the file served, and confirm the page drew from it
    // rather than solving: an unused layout would ship as a silent no-op.
    server.close();
    server = await serve(false);
    const again = await openPage(browser, "http://127.0.0.1:" + server.address().port + "/index.html");
    const used = await browser.evaluate(
      "!!LAYOUT && LAYOUT.signature === drawnSignature && prebuiltLayout(drawnSignature, " +
      "visNodes.get().map(function (n) { return { id: n.id }; }))");
    if (!used) throw new Error("the page did not use the layout it was given");
    console.log("the page opens from it in " + (again / 1000).toFixed(1) + " s");
  } finally {
    server.close();
    await browser.close();
  }
}

const mode = process.argv[2] || "";
try {
  if (mode === "--check") {
    const why = staleness();
    if (why) { console.error(why); process.exit(1); }
    console.log("viz/layout.data.js matches the data and the page");
  } else if (mode === "--if-stale") {
    const why = staleness();
    if (why) { console.log(why); await build(); } else console.log("viz/layout.data.js is current");
  } else if (mode === "") {
    await build();
  } else {
    console.error("usage: node scripts/build_layout.mjs [--check | --if-stale]");
    process.exit(2);
  }
} catch (e) {
  console.error(e.message);
  process.exit(1);
}
