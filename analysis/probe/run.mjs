// Ask the page's own ranking about each probe, and when it gets one wrong, say
// what it ranked above the right answer and what the two pairs share.
//
// The aggregate grade answers "how often". This answers "why", which is the
// question that tells you what to change. Read-only; adopts nothing.
//
// Usage:
//   node analysis/probe/run.mjs                 every probe, one line each
//   node analysis/probe/run.mjs --detail 10     the 10 worst, with diagnosis
//   node analysis/probe/run.mjs --only MORPHINE one probe, with diagnosis

import { loadPayload, loadViewer, HarnessError } from "../similarity_harness/harness.mjs";
import { PROBES } from "./probes.mjs";

const args = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = args.indexOf(name);
  return i < 0 ? dflt : args[i + 1];
};
const detailN = Number(flag("--detail", 0));
const only = flag("--only", null);

let data, viewer;
try {
  data = loadPayload();
  viewer = loadViewer(data);
} catch (err) {
  if (err instanceof HarnessError) { console.error(err.message); process.exit(2); }
  throw err;
}

// -- resolving a probe's names to catalogue entries -------------------------
// Exact, case-insensitive, on the entry's own name. Never a substring: "THC"
// matching ethchlorvynol is the failure the viewer's own search notes, and a
// probe that silently resolved to the wrong molecule would report a wrong rank
// as a finding about the ranking.
const F = data.fields.molecules;
const idI = F.indexOf("id"), nameI = F.indexOf("name");
const str = (x) => (typeof x === "number" ? data.strings[x] : x);
const byName = new Map();
for (const row of data.molecules) {
  const n = String(str(row[nameI]) || "").toUpperCase();
  if (!byName.has(n)) byName.set(n, row[idI]);
}
const nameOf = new Map(data.molecules.map((r) => [r[idI], str(r[nameI])]));

const targetName = (t) => {
  if (!t) return "?";
  const syms = (t.components || []).map((c) => c.gene_symbol).filter(Boolean);
  return t.target_type === "SINGLE PROTEIN" && syms.length === 1 ? syms[0] : t.name;
};

const evidenceOf = (claims) => {
  let curated = false, multi = false;
  for (const c of claims) {
    if (c.curated_support) curated = true;
    if (c.multiple_study_support) multi = true;
  }
  if (curated && multi) return { w: 1.0, tag: "curated+replicated" };
  if (multi) return { w: 0.9, tag: "replicated" };
  if (curated) return { w: 0.75, tag: "curated" };
  return { w: 0.5, tag: "preliminary" };
};

/** What one shared-target row contributed, in the score's own terms. */
function contribution(s) {
  const type = s.target ? s.target.target_type : "";
  const w = { "SINGLE PROTEIN": 1.0, "PROTEIN COMPLEX": 1.0,
    "PROTEIN COMPLEX GROUP": 0.5, "PROTEIN FAMILY": 0.5 }[type] || 0.5;
  const mine = evidenceOf(s.mine), theirs = evidenceOf(s.theirs);
  const ev = Math.min(mine.w, theirs.w);
  const prev = s.prevalence === undefined ? null : s.prevalence;
  return {
    name: targetName(s.target), type, w, ev, prev,
    weaker: mine.w <= theirs.w ? mine.tag : theirs.tag,
    subsumed: !!s.subsumed,
    opposed: !!(s.direction && s.direction.opposed),
    product: s.subsumed ? 0 : w * ev * (prev === null ? 1 : prev),
  };
}

function describePair(rows, otherId) {
  const row = rows.find((r) => r.molecule.id === otherId);
  if (!row) return null;
  const parts = row.shared.map(contribution)
    .sort((a, b) => b.product - a.product);
  return { row, parts };
}

function fmtParts(parts, max = 4) {
  return parts.slice(0, max).map((p) => {
    const bits = [`${p.name}`];
    bits.push(p.subsumed ? "subsumed" : p.product.toFixed(3));
    bits.push(p.weaker);
    if (p.prev !== null && !p.subsumed) bits.push(`prev ${p.prev.toFixed(2)}`);
    if (p.w < 1) bits.push(p.type === "PROTEIN FAMILY" ? "family" : "cplx-group");
    if (p.opposed) bits.push("OPPOSED");
    return "      " + bits.join(" · ");
  }).join("\n") + (parts.length > max ? `\n      … and ${parts.length - max} more` : "");
}

// -- run ---------------------------------------------------------------------
const results = [];
for (const probe of PROBES) {
  if (only && probe.q.toUpperCase() !== only.toUpperCase()) continue;
  const qid = byName.get(probe.q.toUpperCase());
  if (qid === undefined) {
    results.push({ probe, missing: "query not in catalogue" });
    continue;
  }
  const want = new Map();
  const absent = [];
  for (const e of probe.expect) {
    const id = byName.get(e.toUpperCase());
    if (id === undefined) absent.push(e); else want.set(id, e);
  }
  if (!want.size) {
    results.push({ probe, missing: `no expected partner in catalogue (${absent.join(", ")})` });
    continue;
  }
  const rows = viewer.sharedTargets(qid);
  let rank = 0, hitId = null;
  for (let i = 0; i < rows.length; i++) {
    if (want.has(rows[i].molecule.id)) { rank = i + 1; hitId = rows[i].molecule.id; break; }
  }
  results.push({
    probe, qid, rows, rank, hitId, absent,
    listed: rows.length,
    top: rows[0] ? rows[0].molecule : null,
    topScore: rows[0] ? rows[0].score : 0,
    want,
  });
}

const kinds = ["mechanism", "opposite", "nonN"];
const verdict = (r) => {
  if (r.missing) return "n/a";
  if (!r.rank) return "ABSENT";
  if (r.probe.kind === "opposite") return r.rank <= 5 ? "BAD" : "ok";
  return r.rank === 1 ? "top-1" : r.rank <= 5 ? "top-5" : r.rank <= 20 ? "top-20" : "BAD";
};

for (const kind of kinds) {
  const group = results.filter((r) => r.probe.kind === kind);
  if (!group.length) continue;
  const header = { mechanism: "Same mechanism — a low rank is right",
    opposite: "Opposites — a HIGH rank is the failure (D15)",
    nonN: "Outside ATC N — the current answer key cannot see these at all" }[kind];
  console.log("\n" + header);
  console.log("=".repeat(70));
  for (const r of group) {
    if (r.missing) {
      console.log(`  ${r.probe.q.padEnd(20)} —      ${r.missing}`);
      continue;
    }
    const rankTxt = r.rank ? `${r.rank}/${r.listed}` : `—/${r.listed}`;
    const hit = r.hitId ? nameOf.get(r.hitId) : "(no expected partner listed)";
    console.log(`  ${r.probe.q.padEnd(20)} ${verdict(r).padEnd(7)} rank ${rankTxt.padEnd(10)}` +
      `${String(hit).slice(0, 18).padEnd(19)} top=${String(r.top && r.top.name).slice(0, 18)}`);
  }
}

// -- counts ------------------------------------------------------------------
const mech = results.filter((r) => r.probe.kind === "mechanism" && !r.missing);
const hits1 = mech.filter((r) => r.rank === 1).length;
const hits5 = mech.filter((r) => r.rank && r.rank <= 5).length;
const bad = mech.filter((r) => !r.rank || r.rank > 20).length;
console.log("\nMechanism probes: " +
  `${mech.length} asked · top-1 ${hits1} · top-5 ${hits5} · beyond rank 20 or absent ${bad}`);
console.log("These counts are a summary of worked examples, not a grade. Nothing");
console.log("here is swept against, for the reason at the top of probes.mjs.");

// -- diagnosis ---------------------------------------------------------------
const toDetail = only
  ? results.filter((r) => !r.missing)
  : results.filter((r) => !r.missing && r.probe.kind === "mechanism")
      .sort((a, b) => (b.rank || 1e9) - (a.rank || 1e9))
      .slice(0, detailN);

for (const r of toDetail) {
  console.log("\n" + "-".repeat(70));
  console.log(`${r.probe.q} — ${r.probe.why}`);
  console.log(`  expected ${r.probe.expect.join(", ")}` +
    (r.absent.length ? `   (not in catalogue: ${r.absent.join(", ")})` : ""));
  console.log(`  ranked ${r.rank ? `${r.rank} of ${r.listed}` : `nowhere in ${r.listed} rows`}`);

  console.log("\n  what the ranking put on top:");
  for (const row of r.rows.slice(0, 3)) {
    const parts = row.shared.map(contribution).sort((a, b) => b.product - a.product);
    console.log(`    ${row.score.toFixed(3)}  ${row.molecule.name}` +
      `  (${row.n_shared} shared)`);
    console.log(fmtParts(parts, 3));
  }

  if (r.hitId) {
    const d = describePair(r.rows, r.hitId);
    console.log(`\n  what it gave the expected partner (${nameOf.get(r.hitId)}):`);
    console.log(`    ${d.row.score.toFixed(3)}  (${d.row.n_shared} shared)`);
    console.log(fmtParts(d.parts, 5));
  } else {
    const names = [...r.want.values()].join(", ");
    console.log(`\n  no expected partner (${names}) appears in the list at all:`);
    console.log("    the two share no eligible claim at any one target -- a coverage");
    console.log("    fact about ChEMBL and this cohort, not a ranking error.");
  }
}
