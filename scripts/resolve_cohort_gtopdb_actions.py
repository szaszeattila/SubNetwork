#!/usr/bin/env python3
"""Backfill GtoPdb into db/cohort1.db: actions as directions, primary targets as claims.

ChEMBL gives a curated direction (agonist, antagonist, inhibitor, ...) on about
1.5% of this catalogue's molecule-target pairs, and D15 can only compare two
molecules where both sides have one. GtoPdb, the IUPHAR/BPS Guide to
Pharmacology, curates ligand->target interactions with a Type and an Action on
the receptor, channel, transporter and enzyme families this project is about.
This script reads that field, and one more: GtoPdb's flag for the target a
ligand's effect comes from. Every row with a mapped action is a direction on
its pair (D17). A *primary-target* row is also curated support (D18): it
becomes one Supported claim in the `gtopdb` role, the same kind of claim a
ChEMBL curated mechanism is, and where ChEMBL had no claim at the pair that is
a new line. It adds no molecule, no target and no affinity, and a non-primary
row at a pair with no claim is stored with has_claim = 0 and goes nowhere.

The route, identifier at every step (invariants 6 and 15):

  1. ligand -> catalogue molecule. GtoPdb's ligand InChIKey, exactly, against
     molecules.inchikey; else GtoPdb's ChEMBL id against molecule_forms, which
     must name exactly one parent. If both routes answer and disagree the
     ligand is dropped as ambiguous rather than resolved.
  2. target -> ChEMBL target record, by UniProt accession. A GtoPdb target
     with one accession matches the one SINGLE PROTEIN record carrying it. One
     with several (a GABA-A subunit combination, a heteromer) matches only a
     PROTEIN COMPLEX whose accessions are exactly that set. It is never fanned
     out onto the subunits' own records: that would attribute one assay to
     every member, which is manufactured similarity ("Ranking on accessions
     rewards fan-out" in docs/DATA-QUALITY-LOG.md).
  3. (Type, Action) -> a ChEMBL action_type word, through ACTION_MAP below, so
     the viewer's existing OPPOSED_ACTIONS table reads GtoPdb's directions
     unchanged. GtoPdb's words are kept verbatim beside it. A combination not
     in the map is stored with no direction and listed in the manifest, so a
     new release cannot slip a new word past a reader.

The release is pinned (GTOPDB_VERSION). GtoPdb serves only its latest release
at a fixed URL, so the version is read off the file's own first line and a
mismatch is fatal; the files are cached under db/cache/gtopdb/<version>/ and
their sha256 recorded in build_manifest. GtoPdb said in September 2026 that
anonymous access will end; the cache is what keeps a rerun possible after that.

Licence: the database is ODbL and its contents CC BY-SA 4.0. The published
viewer credits GtoPdb for every action it shows. Commercial organisations pay
GtoPdb access fees; this project is not one.

A separate backfill, not part of a build: it changes gtopdb_interactions, its
own `gtopdb` rows of claims, every molecule's evidence_status (re-derived from
the claims exactly as the build derives it), one build_manifest key, and
GtoPdb's own entries in source_coverage and the manifest's deferred_sources,
which the build writes as "not assessed". A rebuild wipes all of it; rerun
this after it.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import pathlib
import re
import sqlite3
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common

GTOPDB_VERSION = "2026.3"
BASE_URL = "https://www.guidetopharmacology.org/DATA/"
FILES = ("interactions.csv", "ligands.csv")
CACHE = common.DB / "cache" / "gtopdb" / GTOPDB_VERSION
MANIFEST_KEY = "gtopdb_actions"
LICENCE = "GtoPdb database ODbL; contents CC BY-SA 4.0"
USER_AGENT = "SubNetwork/1.0 (drug-target interaction map; non-commercial)"

# GtoPdb (Type, Action) -> ChEMBL action_type. Written out pair by pair from
# every combination release 2026.3 holds, so that nothing is mapped by a rule
# nobody read. None means the pair names no direction.
#
# Choices worth stating:
# - An Action that names an efficacy outranks the Type: ('Antagonist',
#   'Inverse agonist') is INVERSE AGONIST, ('Antagonist', 'Partial agonist') is
#   PARTIAL AGONIST - GtoPdb uses the Type for the family of the ligand and the
#   Action for what it does here.
# - A Type with no qualifying Action ('Agonist', 'None'; 'Inhibitor',
#   'Binding') still states the direction, and takes it.
# - Allosteric agonists and potentiators map to POSITIVE ALLOSTERIC
#   MODULATOR, allosteric antagonists and inverse agonists to NEGATIVE
#   ALLOSTERIC MODULATOR: the site is kept and the direction is right.
# - Gating inhibitors are BLOCKER, as ChEMBL files channel inhibition, except
#   'Slows inactivation', which prolongs the current and is left undirected.
# - 'Neutral' allosteric ligands (flumazenil), 'Binding', 'Mixed', 'Biphasic',
#   'Unknown', and a bare 'None' Type, name no direction.
ACTION_MAP = {
    ("Activator", "Activation"): "ACTIVATOR",
    ("Activator", "Agonist"): "AGONIST",
    ("Activator", "Binding"): "ACTIVATOR",
    ("Activator", "Full agonist"): "AGONIST",
    ("Activator", "None"): "ACTIVATOR",
    ("Activator", "Partial agonist"): "PARTIAL AGONIST",
    ("Activator", "Positive"): "ACTIVATOR",
    ("Activator", "Potentiation"): "ACTIVATOR",
    ("Agonist", "Activation"): "AGONIST",
    ("Agonist", "Agonist"): "AGONIST",
    ("Agonist", "Biased agonist"): "AGONIST",
    ("Agonist", "Binding"): "AGONIST",
    ("Agonist", "Full agonist"): "AGONIST",
    ("Agonist", "Inverse agonist"): "INVERSE AGONIST",
    ("Agonist", "Irreversible agonist"): "AGONIST",
    ("Agonist", "Mixed"): None,
    ("Agonist", "Negative"): None,
    ("Agonist", "None"): "AGONIST",
    ("Agonist", "Partial agonist"): "PARTIAL AGONIST",
    ("Agonist", "Unknown"): None,
    ("Allosteric modulator", "Activation"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Agonist"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Antagonist"): "NEGATIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Biased agonist"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Binding"): None,
    ("Allosteric modulator", "Biphasic"): None,
    ("Allosteric modulator", "Full agonist"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Inhibition"): "NEGATIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Inverse agonist"): "NEGATIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Mixed"): None,
    ("Allosteric modulator", "Negative"): "NEGATIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Neutral"): None,
    ("Allosteric modulator", "None"): None,
    ("Allosteric modulator", "Partial agonist"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Positive"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Allosteric modulator", "Potentiation"): "POSITIVE ALLOSTERIC MODULATOR",
    ("Antagonist", "Antagonist"): "ANTAGONIST",
    ("Antagonist", "Binding"): "ANTAGONIST",
    ("Antagonist", "Inhibition"): "ANTAGONIST",
    ("Antagonist", "Inverse agonist"): "INVERSE AGONIST",
    ("Antagonist", "Irreversible inhibition"): "ANTAGONIST",
    ("Antagonist", "Mixed"): None,
    ("Antagonist", "Non-competitive"): "ANTAGONIST",
    ("Antagonist", "Partial agonist"): "PARTIAL AGONIST",
    ("Antibody", "Agonist"): "AGONIST",
    ("Antibody", "Antagonist"): "ANTAGONIST",
    ("Antibody", "Binding"): None,
    ("Antibody", "Inhibition"): "INHIBITOR",
    ("Antibody", "None"): None,
    ("Channel blocker", "Antagonist"): "BLOCKER",
    ("Channel blocker", "Binding"): "BLOCKER",
    ("Channel blocker", "Inhibition"): "BLOCKER",
    ("Channel blocker", "None"): "BLOCKER",
    ("Channel blocker", "Pore blocker"): "BLOCKER",
    ("Fusion protein", "Binding"): None,
    ("Fusion protein", "Inhibition"): "INHIBITOR",
    ("Gating inhibitor", "Antagonist"): "BLOCKER",
    ("Gating inhibitor", "Inhibition"): "BLOCKER",
    ("Gating inhibitor", "None"): "BLOCKER",
    ("Gating inhibitor", "Pore blocker"): "BLOCKER",
    ("Gating inhibitor", "Slows inactivation"): None,
    ("Gating inhibitor", "Voltage-dependent inhibition"): "BLOCKER",
    ("Inhibitor", "Antagonist"): "INHIBITOR",
    ("Inhibitor", "Binding"): "INHIBITOR",
    ("Inhibitor", "Competitive"): "INHIBITOR",
    ("Inhibitor", "Feedback inhibition"): "INHIBITOR",
    ("Inhibitor", "Inhibition"): "INHIBITOR",
    ("Inhibitor", "Irreversible inhibition"): "INHIBITOR",
    ("Inhibitor", "Non-competitive"): "INHIBITOR",
    ("Inhibitor", "None"): "INHIBITOR",
    ("Inhibitor", "Unknown"): None,
    ("None", "Binding"): None,
    ("None", "Competitive"): "INHIBITOR",
    ("None", "Inhibition"): "INHIBITOR",
    ("None", "None"): None,
    ("None", "Potentiation"): None,
    ("Subunit-specific", "Inhibition"): "NEGATIVE ALLOSTERIC MODULATOR",
    ("Subunit-specific", "Mixed"): None,
    ("Subunit-specific", "Potentiation"): "POSITIVE ALLOSTERIC MODULATOR",
}

TABLE = "gtopdb_interactions"
# D18: the claims this script writes, and the reason their tier is Supported.
CLAIM_ROLE = "gtopdb"
TIER_REASON = "gtopdb_primary_target"


class GtoPdbError(RuntimeError):
    """A pinned GtoPdb input did not hold. Always fatal."""


# ----------------------------------------------------------------- inputs

def file_version(text: str) -> str | None:
    m = re.match(r'"?# GtoPdb Version: ([0-9.]+)', text)
    return m.group(1) if m else None


def ensure_files(cache=CACHE, version=GTOPDB_VERSION, get=None) -> dict:
    """Return {name: path} for the pinned release, downloading what is missing.

    A downloaded file whose own version line is not the pinned one is refused
    and not cached: the URL always serves the latest release, and a different
    release wearing the pinned name is exactly what the pin prevents.
    """
    get = get or (lambda url: requests.get(url, timeout=120,
                                           headers={"User-Agent": USER_AGENT}))
    out = {}
    for name in FILES:
        path = cache / name
        if not path.exists():
            print(f"  downloading {BASE_URL}{name} ...")
            r = get(BASE_URL + name)
            r.raise_for_status()
            got = file_version(r.text)
            if got != version:
                raise GtoPdbError(
                    f"{name} is GtoPdb {got}, not the pinned {version}. Review "
                    f"ACTION_MAP against the new release before bumping GTOPDB_VERSION, "
                    f"or place the {version} files in {cache} (docs/REPRODUCING.md).")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.text)
        elif file_version(path.read_text()[:200]) != version:
            raise GtoPdbError(f"cached {path} is not GtoPdb {version}")
        out[name] = path
    return out


def read_csv(path) -> list[dict]:
    """GtoPdb's CSVs carry a version line above the header."""
    lines = pathlib.Path(path).read_text().splitlines(keepends=True)
    reader = csv.DictReader(io.StringIO("".join(lines[1:])))
    return list(reader)


def published(path) -> str | None:
    m = re.search(r"published: ([0-9-]+)", pathlib.Path(path).read_text()[:200])
    return m.group(1) if m else None


# --------------------------------------------------------------- matching

def match_ligands(ligands, by_inchikey, by_chembl, counts):
    """GtoPdb ligand id -> (parent_molregno, route), identifiers only."""
    out = {}
    for r in ligands:
        lid = int(r["Ligand ID"])
        a = by_inchikey.get(r.get("InChIKey") or "")
        parents = by_chembl.get(r.get("ChEMBL ID") or "", set())
        b = next(iter(parents)) if len(parents) == 1 else None
        if a is not None and b is not None and a != b:
            counts["ligand_routes_disagree"] += 1
        elif a is not None:
            out[lid] = (a, "inchikey")
        elif b is not None:
            out[lid] = (b, "chembl_id")
        elif len(parents) > 1:
            counts["ligand_chembl_id_ambiguous"] += 1
    return out


def target_index(conn):
    """(frozenset of accessions) -> [target_chembl_id], for the two target
    types a GtoPdb target can be: a single protein or an exact complex."""
    comps = collections.defaultdict(set)
    types = {}
    for t, typ in conn.execute("SELECT chembl_id, target_type FROM targets"):
        types[t] = typ
    for t, acc in conn.execute("SELECT target_chembl_id, accession FROM target_components"
                               " WHERE accession IS NOT NULL"):
        comps[t].add(acc)
    index = collections.defaultdict(list)
    for t, accs in comps.items():
        key = frozenset(accs)
        if len(key) == 1 and types.get(t) == "SINGLE PROTEIN":
            index[key].append(t)
        elif len(key) > 1 and types.get(t) == "PROTEIN COMPLEX":
            index[key].append(t)
    return index


def _join(values):
    vals = sorted({v for v in values if v and v != "None"})
    return "|".join(vals) or None


def resolve(interactions, lig2mol, tindex, claim_pairs, counts, unmapped):
    """Fold GtoPdb interaction rows into gtopdb_interactions rows."""
    groups = collections.OrderedDict()
    for r in interactions:
        lid = int(r["Ligand ID"]) if r["Ligand ID"] else None
        if lid not in lig2mol:
            counts["rows_ligand_not_in_catalogue"] += 1
            continue
        accs = frozenset(a.strip() for a in (r["Target UniProt ID"] or "").split("|")
                         if a.strip() and a.strip() != "None")
        if not accs:
            counts["rows_target_no_accession"] += 1
            continue
        targets = tindex.get(accs, [])
        if not targets:
            counts["rows_target_not_in_catalogue"] += 1
            continue
        if len(targets) > 1:
            counts["rows_target_ambiguous"] += 1
            continue
        parent, route = lig2mol[lid]
        typ, act = r["Type"] or "None", r["Action"] or "None"
        if (typ, act) not in ACTION_MAP:
            unmapped[(typ, act)] += 1
        key = (parent, targets[0], lid, int(r["Target ID"]), typ, act)
        g = groups.setdefault(key, {"route": route, "accs": accs, "rows": []})
        g["rows"].append(r)

    out = []
    for (parent, target, lid, tid, typ, act), g in groups.items():
        rows = g["rows"]
        pmids = []
        for r in rows:
            pmids += [p.strip() for p in (r.get("PubMed ID") or "").split("|")]
        out.append({
            "parent_molregno": parent, "target_chembl_id": target,
            "gtp_ligand_id": lid, "gtp_target_id": tid,
            "gtp_type": typ, "gtp_action": act,
            "action_type": ACTION_MAP.get((typ, act)),
            "ligand_match": g["route"], "accessions": "|".join(sorted(g["accs"])),
            "target_species": _join(r["Target Species"] for r in rows),
            "primary_target": int(any(r["Primary Target"] == "true" for r in rows)),
            "endogenous": int(any(r["Endogenous"] == "true" for r in rows)),
            "selectivity": _join(r["Selectivity"] for r in rows),
            "action_comment": _join(r["Action comment"] for r in rows),
            "receptor_site": _join(r["Receptor Site"] for r in rows),
            "ligand_context": _join(r["Ligand Context"] for r in rows),
            "pubmed_ids": _join(pmids),
            "n_rows": len(rows),
            "has_claim": int((parent, target) in claim_pairs),
        })
    return out


POSITIVE = {"AGONIST", "PARTIAL AGONIST", "ACTIVATOR", "POSITIVE ALLOSTERIC MODULATOR"}
NEGATIVE = {"ANTAGONIST", "INVERSE AGONIST", "INHIBITOR", "BLOCKER",
            "NEGATIVE ALLOSTERIC MODULATOR"}


def phrase(row):
    """GtoPdb's words for one row: "Antagonist", "Agonist (partial agonist)"."""
    typ, act = row["gtp_type"], row["gtp_action"]
    extra = f" ({act.lower()})" if act and act not in ("None", typ) else ""
    return (typ if typ != "None" else "No type") + extra


def write_claims(conn, rows):
    """D18: a GtoPdb *primary-target* interaction is curated support.

    GtoPdb marks, per ligand, the target its effect comes from. That is the
    same kind of statement as a ChEMBL curated mechanism - an expert saying
    "this is how the drug works" - so it is written the way ChEMBL's is: one
    Supported claim per molecule, target and basis, in its own role
    (`gtopdb`) so the two curators never overwrite or impersonate each other.
    It carries no measurement and no affinity. Its other rows, the targets a
    ligand was also measured at, stay directions only: they are mostly
    affinities from the papers ChEMBL already abstracts, which is not
    independent evidence, and they are where GtoPdb's one known error shape
    lives (vilazodone "agonist" at D2, D3 and H1).

    Where the pair had no claim at all, this is a new line - an assertion by a
    curator, which is what a ChEMBL curated claim at an unmeasured target
    already is, not an edge manufactured from a measurement. Returns the
    manifest counts; rewrites has_claim and every molecule's evidence_status,
    because both change when a claim appears.
    """
    tax = dict(conn.execute("SELECT chembl_id, tax_id FROM targets"))
    by_pair = collections.defaultdict(list)
    for r in rows:
        if r["primary_target"]:
            by_pair[(r["parent_molregno"], r["target_chembl_id"])].append(r)
    best = {}
    for p, t, tier in conn.execute("SELECT parent_molregno, target_chembl_id, tier FROM claims"):
        rank = {"supported": 0, "preliminary": 1}.get(tier, 2)
        best[(p, t)] = min(rank, best.get((p, t), 9))
    effect = collections.Counter()
    for (parent, target), rs in sorted(by_pair.items()):
        actions = sorted({r["action_type"] for r in rs if r["action_type"]})
        conflict = int(bool(POSITIVE & set(actions)) and bool(NEGATIVE & set(actions)))
        words = "; ".join(sorted({phrase(r) for r in rs}))
        conn.execute(
            "INSERT INTO claims(parent_molregno, target_chembl_id, claim_role, basis, tier,"
            " tier_reason, curated_support, multiple_study_support, n_rows, action_type,"
            " mechanism_of_action, conflict_action, conflict_detail, assignment_classes)"
            " VALUES (?, ?, ?, ?, 'supported', ?, 1, 0, ?, ?, ?, ?, ?, ?)",
            (parent, target, CLAIM_ROLE,
             "human_direct" if tax.get(target) == 9606 else "broader",
             TIER_REASON, len(rs), " / ".join(actions) or None,
             f"GtoPdb: {words}", conflict,
             f"GtoPdb rows assert opposing directions: {words}" if conflict else None,
             CLAIM_ROLE))
        effect[{0: "already_supported", 1: "preliminary_to_supported",
                2: "limited_to_supported", 9: "new_line"}[best.get((parent, target), 9)]] += 1
    conn.execute(f"UPDATE {TABLE} SET has_claim = EXISTS (SELECT 1 FROM claims c"
                 f" WHERE c.parent_molregno = {TABLE}.parent_molregno"
                 f" AND c.target_chembl_id = {TABLE}.target_chembl_id)")
    # Every status is re-derived from the claims table alone, exactly as the
    # build derives it, so resetting first reproduces a build's answer.
    from cohort import build as build_mod
    conn.execute("UPDATE molecules SET evidence_status = NULL, gap_reason = NULL")
    build_mod._write_evidence_status(conn)
    return {"gtopdb_claims": sum(effect.values()),
            "gtopdb_claim_effect": dict(effect),
            "molecules_with_a_gtopdb_claim": len({p for p, _ in by_pair})}


def ensure_table(conn):
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (TABLE,)).fetchone()
    if have:
        return False
    schema = (common.DB / "schema_cohort.sql").read_text()
    for pattern in (r"CREATE TABLE IF NOT EXISTS " + TABLE + r" \(.*?\n\);",
                    r"CREATE INDEX IF NOT EXISTS idx_gtopdb_pair[^;]*;"):
        m = re.search(pattern, schema, re.S)
        if not m:
            raise common.PolicyError(f"{TABLE} is missing from schema_cohort.sql")
        conn.execute(m.group(0))
    return True


def backfill(conn, interactions, ligands, extra=None):
    ensure_table(conn)
    counts, unmapped = collections.Counter(), collections.Counter()
    by_inchikey = {k: p for p, k in conn.execute(
        "SELECT parent_molregno, inchikey FROM molecules WHERE inchikey IS NOT NULL")}
    by_chembl = collections.defaultdict(set)
    for p, c in conn.execute("SELECT parent_molregno, chembl_id FROM molecule_forms"):
        by_chembl[c].add(p)
    for p, c in conn.execute("SELECT parent_molregno, chembl_id FROM molecules"):
        by_chembl[c].add(p)
    lig2mol = match_ligands(ligands, by_inchikey, by_chembl, counts)
    # This script's own claims go first, so what counts as "the catalogue
    # already has a claim here" is ChEMBL's answer and never an earlier run's.
    conn.execute("DELETE FROM claims WHERE claim_role = ?", (CLAIM_ROLE,))
    claim_pairs = set(conn.execute(
        "SELECT DISTINCT parent_molregno, target_chembl_id FROM claims"))
    rows = resolve(interactions, lig2mol, target_index(conn), claim_pairs, counts, unmapped)

    cols = list(rows[0].keys()) if rows else []
    conn.execute(f"DELETE FROM {TABLE}")
    if rows:
        conn.executemany(f"INSERT INTO {TABLE}({', '.join(cols)}) VALUES"
                         f"({', '.join('?' * len(cols))})",
                         [tuple(r[c] for c in cols) for r in rows])

    curated = {(p, t) for p, t in conn.execute(
        "SELECT parent_molregno, target_chembl_id FROM curated_mechanisms"
        " WHERE action_type IS NOT NULL AND action_type <> ''")}
    directed = {(r["parent_molregno"], r["target_chembl_id"]) for r in rows
                if r["has_claim"] and r["action_type"]}
    summary = {
        "release": GTOPDB_VERSION, "licence": LICENCE,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "ligands_matched": len(lig2mol),
        "molecules_matched": len({m for m, _ in lig2mol.values()}),
        "ligand_routes": dict(collections.Counter(r for _, r in lig2mol.values())),
        "rows": len(rows),
        "rows_at_a_claim": sum(r["has_claim"] for r in rows),
        "pairs_directed": len(directed),
        "pairs_directed_without_chembl_direction": len(directed - curated),
        "molecules_gaining_a_direction": len({p for p, _ in directed - curated}),
        "pairs_without_a_claim": len({(r["parent_molregno"], r["target_chembl_id"])
                                      for r in rows if not r["has_claim"]}),
        "counts": dict(counts),
        # A (Type, Action) the pinned map does not hold: stored undirected.
        "unmapped_type_action": sorted([list(k) + [n] for k, n in unmapped.items()]),
    }
    summary.update(write_claims(conn, rows))
    summary.update(extra or {})
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 (MANIFEST_KEY, json.dumps(summary, sort_keys=True)))
    mark_assessed(conn)
    return summary


def mark_assessed(conn):
    """The build records GtoPdb as deferred, because the build alone does not
    read it (D12). Once this has run it is not: the payload carried GtoPdb as
    "not assessed, deferred to cohort 2" beside the gtopdb.data.js that holds
    it (docs/HOSTING-REVIEW.md, Minor). Only GtoPdb's own entries move."""
    conn.execute(
        "INSERT OR REPLACE INTO source_coverage(source, status, release, note)"
        " VALUES('GtoPdb', 'assessed', ?, ?)",
        (GTOPDB_VERSION, "Backfilled after the build (D17, D18): curated actions on pairs"
                         " ChEMBL already has, and primary-target claims. Exported to"
                         " its own file for its licence."))
    row = conn.execute("SELECT value FROM build_manifest"
                       " WHERE key = 'deferred_sources'").fetchone()
    if row:
        deferred = [s for s in json.loads(row[0]) if s != "GtoPdb"]
        conn.execute("UPDATE build_manifest SET value = ? WHERE key = 'deferred_sources'",
                     (json.dumps(deferred),))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    paths = ensure_files()
    extra = {"published": published(paths["interactions.csv"]),
             "sha256": {n: common.sha256(p) for n, p in paths.items()}}
    interactions = read_csv(paths["interactions.csv"])
    ligands = read_csv(paths["ligands.csv"])
    print(f"  GtoPdb {GTOPDB_VERSION}: {len(interactions)} interactions, {len(ligands)} ligands")

    conn = sqlite3.connect(args.db, isolation_level=None)
    try:
        conn.execute("BEGIN")
        s = backfill(conn, interactions, ligands, extra)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()

    print(f"{s['molecules_matched']} molecules matched; {s['rows']} rows, "
          f"{s['rows_at_a_claim']} at a pair with a claim; {s['pairs_directed']} pairs directed, "
          f"{s['pairs_directed_without_chembl_direction']} of them with no ChEMBL direction, "
          f"on {s['molecules_gaining_a_direction']} molecules"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in sorted(s["counts"].items()):
        print(f"  {n:6d}  {k}")
    for typ, act, n in s["unmapped_type_action"]:
        print(f"  unmapped: {typ} / {act} ({n})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
