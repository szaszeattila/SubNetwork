#!/usr/bin/env python3
"""Backfill MeSH pharmacological actions into db/cohort1.db, read from MeSH.

A pharmacological action is what NLM's MeSH indexers record a drug as doing:
"Antidepressive Agents, Tricyclic", "Phosphodiesterase Inhibitors",
"Antipsychotic Agents". It is the one class source here that answers the
question the page asks - which molecules act alike - rather than what a drug is
used for (ATC, taken back off the page) or what it is built like (a structural
taxonomy). It is still a curated label and not evidence: it never becomes a
claim, never reaches the similarity score, and says nothing about a target.

Each molecule is placed on ONE MeSH record, and takes that record's own
PharmacologicalActionList from NLM's files for a pinned year (desc<YEAR>.gz,
supp<YEAR>.gz). The record is found by identifier at every step (invariant 15),
each step tried only where the one before placed nothing:

  1. UNII. The molecule's standard InChIKey -> the FDA UNII registered with
     exactly that structure (FDA's UNII records) -> the MeSH record carrying
     that UNII as a registry number. The parent's InChIKey first, its forms'
     (the salts and hydrates the build folded onto it) only where the parent
     reaches nothing, because MeSH often files a drug under its salt. This is
     the route scripts/resolve_cohort_mesh_structure.py takes.
  2. CAS. Older MeSH records carry a CAS number where newer ones carry the
     UNII (GABA 56-12-2), so where the UNIIs reach no record, the CAS numbers
     FDA lists for them are tried. Only then: used alongside the UNII, a CAS
     number a second record also carries refused molecules the UNII had placed
     (eplerenone, lacosamide).
  3. A mixture of stereoisomers. Where ChEMBL draws the molecule with no
     stereochemistry (an InChIKey whose second block is UHFFFAOYSA) and FDA has
     no record of that flat structure, an FDA substance registered as a mixture
     of that skeleton's stereoisomers (its InChIKey field joins two or more keys
     sharing the first block - a racemate) is the same substance: "stereo
     unspecified" and "a mixture of this skeleton's stereoisomers" describe one
     thing. Methylphenidate, nebivolol and pentazocine are placed this way. A
     molecule ChEMBL draws WITH stereochemistry never reaches this step, which
     is what keeps esmethadone off methadone's record and lucerastat off
     miglustat's: matching a skeleton while ignoring its stereochemistry was
     measured and put both there.
  4. Wikidata. Where no FDA route places the molecule on exactly one record,
     the MeSH ID (P486) on the Wikidata item carrying its ChEMBL ID (P592).
     This reaches what FDA files without a structure - antibodies, proteins,
     peptides (exenatide, teriparatide) - and nothing is matched by a name.
     Where both name a record they agreed on 729 of 735 molecules; the six
     disagreements are a molecule filed as a narrower concept of another
     record (armodafinil within Modafinil), and step 1's answer stands there.

At every step more than one record is a refusal, never a pick (invariant 6),
and is counted. Each action is then filed under the actions above it, inside
the pharmacological-action branch (D27), so "Antidepressive Agents, Tricyclic"
also files a drug under "Antidepressive Agents".

Until 2026-10-13 this went through PubChem, which links a compound to MeSH
records by name: tafamidis carried triamcinolone's steroid actions through
"FX006", and a judge had to set aside links PubChem made. No step here makes a
name-based link, so there is nothing to set aside. The route was measured
against PubChem's before it replaced it (docs/MESH-ACTIONS-ROUTE-B.md,
analysis/mesh_route_b/).

A separate backfill, not part of a build: it reads ChEMBL read-only (for the
forms' InChIKeys) and changes only the mesh_pa rows of molecule_classes and
class_labels, and one build_manifest key. A rebuild wipes those rows, as it
wipes the Wikipedia and trial backfills; rerun this after it. The MeSH and FDA
files are pinned under db/cache/ and recorded by sha256. The Wikidata answers
are cached under db/cache/wikidata/, so a rerun is offline unless --refresh is
given or a molecule is new.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import gzip
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import classes as classes_mod
from cohort import common

SOURCE = "mesh_pa"

MESH_YEAR = 2026
MESH_URL = ("https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/"
            f"desc{MESH_YEAR}.gz")
CACHE = common.DB / "cache"
MESH_FILE = CACHE / "mesh" / f"desc{MESH_YEAR}.gz"
WIKIDATA_CACHE = CACHE / "wikidata" / "mesh_by_chembl.json"

# The pharmacological-action branch of MeSH, and how deep an action has to sit
# to be a class worth offering. Depths 1-3 are "Chemical Actions and Uses",
# "Pharmacologic Actions" and its three halves ("Molecular Mechanisms of
# Pharmacological Action", "Physiological Effects of Drugs", "Therapeutic
# Uses"), which hold nearly every drug and say nothing about any of them.
PA_BRANCH = "D27"
MIN_DEPTH = 4

# An InChIKey's second block when the structure has no stereo (or isotope)
# layer at all.
FLAT = "UHFFFAOYSA"

USER_AGENT = "SubNetwork/1.0 (cohort-1 drug-target interaction map)"
REQUEST_TIMEOUT = 60

# How many ChEMBL IDs one Wikidata query asks about.
WIKIDATA_CHUNK = 50
WIKIDATA_QUERY = """SELECT ?chembl ?item ?mesh WHERE {
  VALUES ?chembl { %s }
  ?item wdt:P592 ?chembl .
  OPTIONAL { ?item wdt:P486 ?mesh . }
}"""


# ------------------------------------------------------------------ MeSH

def ensure_mesh_file(path=MESH_FILE, url=MESH_URL) -> pathlib.Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {url} ...")
        tmp = path.with_suffix(".part")
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT,
                          headers={"User-Agent": USER_AGENT}) as resp:
            resp.raise_for_status()
            # The raw stream, not iter_content: the server marks the file with a
            # gzip Content-Encoding and requests would otherwise unpack it,
            # storing 300 MB of XML under a .gz name.
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.raw.read(1 << 20, decode_content=False)
                    if not chunk:
                        break
                    fh.write(chunk)
        tmp.rename(path)
    return path


def load_mesh(path) -> dict:
    """Parse a MeSH descriptor file into the three lookups this script needs.

    concept -> descriptor UI, descriptor UI -> (name, tree numbers), and tree
    number -> descriptor UI. Streamed, because the file is 300 MB unpacked.
    """
    concept_to_desc, descs, tree_to_desc = {}, {}, {}
    with open(path, "rb") as probe:
        packed = probe.read(2) == b"\x1f\x8b"
    with (gzip.open if packed else open)(path, "rb") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "DescriptorRecord":
                continue
            ui = el.findtext("DescriptorUI")
            name = el.findtext("DescriptorName/String")
            trees = [t.text for t in el.findall("TreeNumberList/TreeNumber") if t.text]
            descs[ui] = (name, trees)
            for t in trees:
                tree_to_desc[t] = ui
            for c in el.findall("ConceptList/Concept/ConceptUI"):
                if c.text:
                    concept_to_desc[c.text] = ui
            el.clear()
    return {"concept": concept_to_desc, "desc": descs, "tree": tree_to_desc}


def pa_trees(mesh, ui):
    return [t for t in mesh["desc"].get(ui, (None, []))[1]
            if t == PA_BRANCH or t.startswith(PA_BRANCH + ".")]


def depth(tree):
    return tree.count(".") + 1


def parents_of(mesh, ui):
    """The descriptors directly above one, inside the action branch and at or
    below MIN_DEPTH. A descriptor sitting in two places has a parent for each."""
    out = []
    for t in pa_trees(mesh, ui):
        if "." not in t:
            continue
        up = t.rsplit(".", 1)[0]
        if depth(up) < MIN_DEPTH:
            continue
        p = mesh["tree"].get(up)
        if p and p not in out:
            out.append(p)
    return out


def label_rows(mesh, uis):
    """class_labels rows for these actions and every action above them."""
    seen, todo = {}, list(uis)
    while todo:
        ui = todo.pop()
        if ui in seen:
            continue
        name, _ = mesh["desc"].get(ui, (None, []))
        trees = pa_trees(mesh, ui)
        parents = parents_of(mesh, ui)
        seen[ui] = (SOURCE, ui, min((depth(t) for t in trees), default=None), name,
                    "|".join(parents) or None)
        todo.extend(parents)
    return sorted(seen.values())


def load_records(desc_path, supp_path):
    """Every MeSH record's identity, from both files: concept -> record, and
    per record its pharmacological actions, registry numbers, mapped headings
    (supplementary records) and the descriptors directly above it."""
    out = {"concept": {}, "pa": {}, "rn": {}, "mapped": {}, "parents": {}}
    tree = {}
    for path, tag, ui_tag in ((desc_path, "DescriptorRecord", "DescriptorUI"),
                              (supp_path, "SupplementalRecord", "SupplementalRecordUI")):
        with open(path, "rb") as probe:
            packed = probe.read(2) == b"\x1f\x8b"
        with (gzip.open if packed else open)(path, "rb") as fh:
            for _, el in ET.iterparse(fh, events=("end",)):
                if el.tag != tag:
                    continue
                ui = el.findtext(ui_tag)
                for c in el.findall("ConceptList/Concept/ConceptUI"):
                    if c.text:
                        out["concept"][c.text] = ui
                pa = frozenset(d.text for d in el.findall(
                    "PharmacologicalActionList/PharmacologicalAction/DescriptorReferredTo/DescriptorUI")
                    if d.text)
                if pa:
                    out["pa"][ui] = pa
                rn = [r.text for r in el.findall(
                    "ConceptList/Concept/RegistryNumberList/RegistryNumber")
                    if r.text and r.text != "0"]
                if rn:
                    out["rn"][ui] = rn
                mapped = [d.text.lstrip("*") for d in el.findall(
                    "HeadingMappedToList/HeadingMappedTo/DescriptorReferredTo/DescriptorUI")
                    if d.text]
                if mapped:
                    out["mapped"][ui] = mapped
                trees = [t.text for t in el.findall("TreeNumberList/TreeNumber") if t.text]
                if trees:
                    out["parents"][ui] = trees
                    for t in trees:
                        tree[t] = ui
                el.clear()
    for ui, trees in list(out["parents"].items()):
        ups = []
        for t in trees:
            p = tree.get(t.rsplit(".", 1)[0]) if "." in t else None
            if p and p not in ups:
                ups.append(p)
        out["parents"][ui] = ups
    return out


def records_by_number(records) -> dict:
    """A registry number (UNII or CAS) -> the MeSH records carrying it."""
    out = collections.defaultdict(set)
    for rec, numbers in records["rn"].items():
        for n in numbers:
            out[n].add(rec)
    return out


# ------------------------------------------------------------------- FDA

Fda = collections.namedtuple("Fda", "unii_by_key cas_of mixtures")


def load_fda(path) -> Fda:
    """FDA's UNII records, as the three lookups the placement reads.

    unii_by_key: a standard InChIKey -> the UNIIs registered with exactly that
    structure. cas_of: a UNII -> the CAS numbers FDA lists for it. mixtures: an
    InChIKey first block -> the UNIIs registered as a mixture of that
    skeleton's stereoisomers, which FDA writes as two or more InChIKeys joined
    by ';', every one sharing the first block. Accepts the archive or a bare
    records file, so the tests can hand it a fixture.
    """
    csv.field_size_limit(1 << 30)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.startswith("UNII_Records")]
            if len(names) != 1:
                raise SystemExit(f"{path}: expected one UNII_Records file, found {names}")
            text = zf.read(names[0]).decode("utf-8")
    else:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    unii_by_key = collections.defaultdict(set)
    cas_of = collections.defaultdict(set)
    mixtures = collections.defaultdict(set)
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        unii, key, cas = r.get("UNII"), r.get("INCHIKEY") or "", (r.get("RN") or "").strip()
        if not unii:
            continue
        if cas:
            cas_of[unii].add(cas)
        if not key:
            continue
        unii_by_key[key].add(unii)
        parts = [k.strip() for k in key.split(";") if k.strip()]
        if len(parts) >= 2 and len({k[:14] for k in parts}) == 1:
            mixtures[parts[0][:14]].add(unii)
    return Fda(dict(unii_by_key), dict(cas_of), dict(mixtures))


# -------------------------------------------------------------- Wikidata

def fetch_wikidata(chembl_ids, cache_path=WIKIDATA_CACHE, refresh=False, get=None):
    """ChEMBL ID -> [[item, MeSH ID or None], ...] for the Wikidata items
    carrying it (P592), cached as JSON. A ChEMBL ID no item carries is cached
    as []. A failed request raises rather than reading as "no item": the
    Wikidata step would otherwise place fewer molecules without saying so.

    get: the SPARQL GET, injectable for the tests; the Wikipedia backfill's
    retried, throttled one by default.
    """
    if get is None:
        import resolve_cohort_wikipedia as wiki
        get = wiki._wikidata_get
    from resolve_cohort_wikipedia import sparql_literal
    cache = {}
    if cache_path.exists() and not refresh:
        cache = json.loads(cache_path.read_text())
    todo = [c for c in chembl_ids if c not in cache]
    for i in range(0, len(todo), WIKIDATA_CHUNK):
        chunk = todo[i:i + WIKIDATA_CHUNK]
        body = get(WIKIDATA_QUERY % " ".join(sparql_literal(c) for c in chunk))
        got = {c: [] for c in chunk}
        for b in body["results"]["bindings"]:
            pair = [b["item"]["value"].rsplit("/", 1)[-1],
                    b["mesh"]["value"] if "mesh" in b else None]
            if pair not in got[b["chembl"]["value"]]:
                got[b["chembl"]["value"]].append(pair)
        cache.update(got)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, sort_keys=True, indent=0))
    return {c: cache.get(c, []) for c in chembl_ids}


# --------------------------------------------------------------- placing

def _reach(uniis, by_number, fda, cas):
    """The MeSH records these UNIIs reach - through the UNII itself, or with
    cas, through the CAS numbers FDA lists for them."""
    found, via = set(), []
    for u in sorted(uniis):
        hits = set(by_number.get(u, ()))
        label = f"UNII:{u}"
        if cas:
            hits = set()
            for c in sorted(fda.cas_of.get(u, ())):
                if by_number.get(c):
                    hits |= by_number[c]
                    label = f"UNII:{u}|CAS:{c}"
        if hits:
            found |= hits
            via.append(label)
    return found, via


def _by_keys(keys, by_number, fda, cas):
    """own_record's order: the parent's key first, the forms' only if the
    parent reaches nothing."""
    found, via = set(), []
    for i, key in enumerate(keys):
        if i == 1 and found:
            break
        f, v = _reach(fda.unii_by_key.get(key, ()), by_number, fda, cas)
        found |= f
        via += v
    return found, via


def place(keys, chembl_id, by_number, fda, wikidata, known):
    """Place one molecule on one MeSH record.

    keys: the parent's InChIKey, then its forms'. wikidata: [[item, MeSH ID]]
    for its ChEMBL ID. known: every record UI in the pinned files. Returns
    (record or None, step, carriers), where step names the route that placed
    it or why nothing did.
    """
    found, via = _by_keys(keys, by_number, fda, cas=False)
    step = "unii"
    if not found:
        found, via = _by_keys(keys, by_number, fda, cas=True)
        step = "cas"
    if not found:
        for key in keys:
            if key[15:25] != FLAT:
                continue
            uniis = fda.mixtures.get(key[:14], ())
            found, via = _reach(uniis, by_number, fda, cas=False)
            if not found:
                found, via = _reach(uniis, by_number, fda, cas=True)
            if found:
                step = "stereo_mixture"
                break
    if len(found) == 1:
        rec = next(iter(found))
        return rec, step, "|".join(via + [f"MeSH:{rec}"])
    fda_refused = len(found) > 1

    mesh_ids = {m for _, m in wikidata if m in known}
    if len(mesh_ids) == 1:
        rec = next(iter(mesh_ids))
        items = sorted({i for i, m in wikidata if m == rec})
        return rec, "wikidata", "|".join([f"Wikidata:{i}" for i in items] + [f"MeSH:{rec}"])
    if len(mesh_ids) > 1:
        return None, "wikidata_several_records", ""
    if fda_refused:
        return None, "several_records", ""
    if not keys and not wikidata:
        return None, "no_inchikey_no_wikidata_item", ""
    return None, "no_record", ""


def resolve(molecules, mesh, records, fda, wikidata):
    """Decide each molecule's actions. Pure given its inputs, so the rules can
    be tested without files or network.

    molecules: [(parent_molregno, chembl_id, [InChIKeys: parent's, then forms'])].
    wikidata: chembl_id -> [[item, MeSH ID]]. Returns (rows, labels, counts).
    """
    by_number = records_by_number(records)
    known = set(records["concept"].values()) | set(mesh["desc"])
    counts = collections.Counter()
    rows, used = [], set()
    for parent, chembl_id, keys in molecules:
        rec, step, carriers = place(keys, chembl_id, by_number, fda,
                                    wikidata.get(chembl_id, []), known)
        if rec is None:
            counts[step] += 1
            continue
        actions = sorted(a for a in records["pa"].get(rec, ()) if a in mesh["desc"])
        dropped = len(records["pa"].get(rec, ())) - len(actions)
        if dropped:
            counts["action_not_in_mesh_year"] += dropped
        if not actions:
            counts["record_lists_no_action"] += 1
            continue
        counts["resolved"] += 1
        counts[f"resolved_by_{step}"] += 1
        for ui in actions:
            rows.append((parent, SOURCE, ui, "", mesh["desc"][ui][0], carriers))
            used.add(ui)
    rows.sort()
    return rows, label_rows(mesh, used), counts


def molecule_keys(conn, chembl):
    """[(parent_molregno, chembl_id, [InChIKeys])]: the parent's key, then each
    folded form's, as ChEMBL holds them, de-duplicated in that order."""
    forms = collections.defaultdict(list)
    for p, m in conn.execute("SELECT parent_molregno, molregno FROM molecule_forms"
                             " ORDER BY parent_molregno, is_parent DESC, molregno"):
        forms[p].append(m)
    key_of = {}
    regnos = sorted({m for v in forms.values() for m in v})
    for chunk in common.chunked(regnos):
        marks = ",".join("?" * len(chunk))
        key_of.update(chembl.execute("SELECT molregno, standard_inchi_key FROM compound_structures"
                                     f" WHERE molregno IN ({marks})", chunk).fetchall())
    out = []
    for p, chembl_id, key in conn.execute("SELECT parent_molregno, chembl_id, inchikey"
                                          " FROM molecules ORDER BY parent_molregno"):
        keys = [k for k in dict.fromkeys([key] + [key_of.get(m) for m in forms[p]]) if k]
        out.append((p, chembl_id, keys))
    return out


def backfill(conn, molecules, mesh, records, fda, wikidata, extra=None):
    classes_mod.ensure_tables(conn)
    rows, labels, counts = resolve(molecules, mesh, records, fda, wikidata)
    before = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    classes_mod.write(conn, rows, labels, sources=(SOURCE,))
    after = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    summary = {
        "route": "MeSH record by UNII, CAS, stereoisomer mixture, then Wikidata",
        "mesh_release": f"desc{MESH_YEAR}",
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "molecules": len(molecules), "rows": len(rows), "labels": len(labels),
        "actions_used": len({r[2] for r in rows}), "rows_changed": len(before ^ after),
        "counts": dict(counts),
    }
    summary.update(extra or {})
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 ("mesh_pharm_actions", json.dumps(summary, sort_keys=True)))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--refresh", action="store_true",
                        help="re-ask Wikidata instead of reading its cached answers")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    # Imported here rather than at the top: that script imports this one.
    import resolve_cohort_mesh_structure as structure
    desc = ensure_mesh_file()
    supp = structure.ensure_supp_file()
    unii_zip = structure.ensure_unii_file()
    print(f"  reading {desc.name}, {supp.name} and {unii_zip.name} ...")
    mesh = load_mesh(desc)
    records = load_records(desc, supp)
    fda = load_fda(unii_zip)

    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        molecules = molecule_keys(conn, chembl)
        print(f"  asking Wikidata about {len(molecules)} ChEMBL IDs (cached) ...")
        wikidata = fetch_wikidata([c for _, c, _ in molecules], refresh=args.refresh)
        extra = {"mesh_sha256": common.sha256(desc), "mesh_supp_sha256": common.sha256(supp),
                 "unii_archive_sha256": common.sha256(unii_zip),
                 "wikidata_cache_sha256": common.sha256(WIKIDATA_CACHE),
                 "chembl_release": common.CHEMBL_RELEASE}
        conn.execute("BEGIN")
        s = backfill(conn, molecules, mesh, records, fda, wikidata, extra)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
        chembl.close()

    c = s["counts"]
    print(f"{c.get('resolved', 0)} of {s['molecules']} molecules carry a MeSH "
          f"pharmacological action; {s['rows']} rows over {s['actions_used']} actions, "
          f"{s['labels']} class labels with their parents; {s['rows_changed']} rows changed"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in sorted(c.items()):
        print(f"  {n:5d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
