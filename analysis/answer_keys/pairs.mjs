// The pre-registered pairwise key: docs/SIMILARITY-LITERATURE.md, step 4.
//
//   node analysis/answer_keys/pairs.mjs            # grade the ranking
//   node analysis/answer_keys/pairs.mjs --check    # validate the key, grade nothing
//   node analysis/answer_keys/pairs.mjs --list 20  # and list the worst pairs of each kind
//   node analysis/answer_keys/pairs.mjs --json     # the shape scripts/cohort/status.py reads
//
// pairs.json is a few hundred drug pairs written by hand, each citing its
// sources: positives (the same mechanism at the same target), known-unlike
// negatives (the same indication by different mechanisms) and opposites (one
// target, opposite directions). SIMILARITY-HARNESS §3 refuses a hand-written
// key because it can be bent to say anything. The answer to that is in how
// this one was made, not in this file: it was written by people who had not
// seen the ranking's lists, each pair cites a source a reader can check, and
// the key and the rules below were committed and pushed before it graded
// anything, so the history shows which came first.
//
// It is held out. KEYS in the harness does not carry it, so sweep.mjs cannot
// be pointed at it, and no constant is ever chosen by it. It is read once per
// change, as a check on what a change did, never as the thing a change aims at.
//
// The rules are in pairs.json beside the pairs, fixed with them:
//
// - each pair is read in both directions, b in a's list and a in b's;
// - a positive is a hit when the partner ranks within `top_k`; a partner not
//   in the list at all shares no target and is unreachable, counted apart as
//   the harness counts coverage, never as a miss;
// - a negative or an opposite is clean when the partner ranks below `top_k`
//   or is absent;
// - ordering: for each list asked about at least one reachable positive and
//   at least one negative or opposite, the share of (positive, other) pairs
//   in which the positive ranks higher, an absent one ranking below
//   everything and a tie counting half (the AUC of that list), averaged over
//   lists;
// - three readings, all reported: every pair, without the pairs the probe set
//   had already asked about (`seen`), and without the pairs whose sourcing or
//   claim was judged weaker (`doubt`).

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, HarnessError, loadPayload, loadViewer, pct } from "../similarity_harness/harness.mjs";

export const PAIRS = join(ROOT, "analysis", "answer_keys", "pairs.json");
export const KINDS = ["positive", "negative", "opposite"];

/** Problems with the key itself, as a list of strings; empty when sound. */
export function validate(spec, catalogue) {
  const out = [];
  for (const k of ["version", "frozen", "rules", "sources", "pairs"]) {
    if (!(k in spec)) out.push(`pairs.json has no ${k}`);
  }
  if (out.length) return out;
  const seen = new Set();
  spec.pairs.forEach((p, i) => {
    const at = `pair ${i + 1} (${p.a_name} / ${p.b_name})`;
    if (!KINDS.includes(p.kind)) out.push(`${at}: kind ${p.kind}`);
    if (p.a === p.b) out.push(`${at}: a molecule paired with itself`);
    for (const [id, name] of [[p.a, p.a_name], [p.b, p.b_name]]) {
      if (!catalogue.has(id)) out.push(`${at}: ${id} is not in the catalogue`);
      else if (catalogue.get(id).toUpperCase() !== String(name).toUpperCase()) {
        out.push(`${at}: ${id} is ${catalogue.get(id)}, not ${name}`);
      }
    }
    const k = [p.a, p.b].sort().join(":");
    if (seen.has(k)) out.push(`${at}: listed twice`);
    seen.add(k);
    if (!p.relation) out.push(`${at}: no relation stated`);
    if (!Array.isArray(p.cites) || !p.cites.length) out.push(`${at}: cites nothing`);
    for (const c of p.cites || []) {
      if (!spec.sources[c.source]) out.push(`${at}: cites ${c.source}, which is not a source`);
      if (!c.says) out.push(`${at}: a citation of ${c.source} says nothing`);
    }
  });
  for (const [id, s] of Object.entries(spec.sources)) {
    if (s.kind === "doi" && !s.doi) out.push(`source ${id}: no DOI`);
    else if (s.kind === "label" && !s.setid) out.push(`source ${id}: no setid`);
    else if (s.kind !== "doi" && s.kind !== "label") out.push(`source ${id}: kind ${s.kind}`);
  }
  return out;
}

/**
 * Grade a ranking against the pairs. `rankIn(query, other)` is the 1-based
 * rank of `other` in `query`'s list, or 0 when it is not there; `keep(pair)`
 * selects which pairs count (all by default).
 */
export function gradePairs(spec, rankIn, keep = () => true) {
  const k = spec.rules.top_k;
  const tally = Object.fromEntries(KINDS.map((x) => [x, { asked: 0, reachable: 0, good: 0, ranks: [] }]));
  const byQuery = new Map();      // query -> { pos: [rank], other: [rank or Infinity] }
  const rows = [];
  for (const p of spec.pairs) {
    if (!keep(p)) continue;
    for (const [q, m] of [[p.a, p.b], [p.b, p.a]]) {
      const rank = rankIn(q, m);
      const t = tally[p.kind];
      t.asked++;
      if (rank) { t.reachable++; t.ranks.push(rank); }
      const good = p.kind === "positive" ? rank > 0 && rank <= k : !rank || rank > k;
      if (good && (p.kind !== "positive" || rank)) t.good++;
      rows.push({ pair: p, query: q, other: m, rank, good });
      if (!byQuery.has(q)) byQuery.set(q, { pos: [], other: [] });
      if (p.kind === "positive") { if (rank) byQuery.get(q).pos.push(rank); }
      else byQuery.get(q).other.push(rank || Infinity);
    }
  }
  let aucSum = 0, aucLists = 0;
  for (const { pos, other } of byQuery.values()) {
    if (!pos.length || !other.length) continue;
    let s = 0;
    for (const a of pos) for (const b of other) s += a < b ? 1 : a === b ? 0.5 : 0;
    aucSum += s / (pos.length * other.length);
    aucLists++;
  }
  const median = (xs) => {
    if (!xs.length) return null;
    const v = [...xs].sort((a, b) => a - b), h = v.length >> 1;
    return v.length % 2 ? v[h] : (v[h - 1] + v[h]) / 2;
  };
  const summary = {};
  for (const kind of KINDS) {
    const t = tally[kind];
    summary[kind] = {
      asked: t.asked, reachable: t.reachable, median_rank: median(t.ranks),
      // A positive's rate is over the reachable; a negative's or an
      // opposite's over all asked, since absence is the right answer.
      rate: kind === "positive" ? (t.reachable ? t.good / t.reachable : null)
                                : (t.asked ? t.good / t.asked : null),
    };
  }
  summary.ordering = { lists: aucLists, auc: aucLists ? aucSum / aucLists : null };
  return { summary, rows };
}

function report(title, s, k) {
  console.log(title);
  const p = s.positive, n = s.negative, o = s.opposite;
  console.log(`  positives  ${String(p.asked).padStart(4)} asked, ${p.reachable} reachable: ` +
    `${p.rate == null ? "-" : pct(p.rate)} within top ${k}, median rank ${p.median_rank ?? "-"}`);
  console.log(`  negatives  ${String(n.asked).padStart(4)} asked: ${n.rate == null ? "-" : pct(n.rate)} ` +
    `clean (below ${k} or absent), ${n.reachable} in the list, median rank ${n.median_rank ?? "-"}`);
  console.log(`  opposites  ${String(o.asked).padStart(4)} asked: ${o.rate == null ? "-" : pct(o.rate)} ` +
    `clean, ${o.reachable} in the list, median rank ${o.median_rank ?? "-"}`);
  console.log(`  ordering   ${s.ordering.lists} lists: a positive above a negative or ` +
    `opposite ${s.ordering.auc == null ? "-" : pct(s.ordering.auc)} of the time`);
}

async function main() {
  const argv = process.argv.slice(2);
  const spec = JSON.parse(readFileSync(PAIRS, "utf8"));
  const data = loadPayload();
  const F = data.fields.molecules;
  const idI = F.indexOf("id"), cI = F.indexOf("chembl_id"), nI = F.indexOf("name");
  const str = (x) => (typeof x === "number" ? data.strings[x] : x);
  const byChembl = new Map(data.molecules.map((r) => [str(r[cI]), r[idI]]));
  const catalogue = new Map(data.molecules.map((r) => [str(r[cI]), str(r[nI])]));
  const problems = validate(spec, catalogue);
  if (problems.length) {
    throw new HarnessError("pairs.json does not validate:\n  " + problems.join("\n  "));
  }
  const counts = Object.fromEntries(KINDS.map((x) => [x, spec.pairs.filter((p) => p.kind === x).length]));
  if (!argv.includes("--json")) console.log(`Pre-registered pairwise key v${spec.version}, frozen ${spec.frozen}: ` +
    `${spec.pairs.length} pairs (${KINDS.map((x) => `${counts[x]} ${x}`).join(", ")}), ` +
    `${Object.keys(spec.sources).length} sources`);
  if (argv.includes("--check")) {
    console.log("valid; nothing graded.");
    return;
  }

  const viewer = loadViewer(data);
  const lists = new Map();
  const rankIn = (q, m) => {
    const qi = byChembl.get(q), mi = byChembl.get(m);
    if (!lists.has(qi)) lists.set(qi, viewer.sharedTargets(qi).map((r) => r.molecule.id));
    return lists.get(qi).indexOf(mi) + 1;
  };
  const k = spec.rules.top_k;
  const all = gradePairs(spec, rankIn);
  if (argv.includes("--json")) {
    // The shape scripts/cohort/status.py reads; rates are fractions.
    process.stdout.write(JSON.stringify({
      version: spec.version, pairs: spec.pairs.length, counts, top_k: k, ...all.summary,
    }) + "\n");
    return;
  }
  console.log("=".repeat(72));
  report("Every pair, both directions", all.summary, k);
  console.log("");
  report("Without the pairs the probe set had already put to the ranking",
    gradePairs(spec, rankIn, (p) => !p.seen).summary, k);
  console.log("");
  report("Without the pairs marked doubt", gradePairs(spec, rankIn, (p) => !p.doubt).summary, k);

  const listAt = argv.indexOf("--list");
  if (listAt >= 0) {
    const n = Number(argv[listAt + 1]) || 15;
    for (const kind of KINDS) {
      const bad = all.rows.filter((r) => r.pair.kind === kind && !r.good && (kind !== "positive" || r.rank))
        .sort((a, b) => (kind === "positive" ? b.rank - a.rank : a.rank - b.rank));
      console.log(`\n${kind}s graded wrong (${bad.length})`);
      for (const r of bad.slice(0, n)) {
        console.log(`  ${String(r.rank).padStart(4)}  ${catalogue.get(r.query)} -> ${catalogue.get(r.other)}` +
          `  (${r.pair.relation})`);
      }
    }
  }
  console.log("");
  console.log("Held out: no constant is chosen by this key. The pairs were written");
  console.log("by hand, with sources, before the ranking was asked about them;");
  console.log("a positive whose partner shares no target is coverage, not a miss.");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    if (err instanceof HarnessError) {
      console.error("pairwise key: " + err.message);
      process.exit(2);
    }
    throw err;
  });
}
