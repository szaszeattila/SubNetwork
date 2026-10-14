#!/usr/bin/env python3
"""Backfill the adverse effects drug labels list into db/cohort1.db, from OnSIDES.

This is the data behind docs/SIMILARITY-LITERATURE.md's step 3: the first
answer key that shares no input with the similarity score. ChEMBL, GtoPdb and
every class key read targets or a curator's word about a mechanism; a label's
adverse-reactions section reads what happened to patients. Two drugs whose
labels list the same unusual nervous-system effects may act alike in the brain
whatever ChEMBL has measured. Nothing here reaches the page or the score.

OnSIDES (Tanaka et al. 2025, doi:10.1016/j.medj.2025.100642; data CC BY 4.0) is
a model's reading of US, UK, EU and Japanese labels into MedDRA terms. Release
v3.1.1 is pinned by sha256 and read straight from its zip. Three facts about it
shape this script:

- **A label belongs to an ingredient only when it has exactly one.** A
  combination product's effects are its partner's as much as its own, so a
  label whose products reach two RxNorm ingredients is not read.
- **The route to a molecule is the FDA backfill's**, by identifier alone:
  InChIKey -> FDA UNII -> RxNorm ingredient, from the same cached answers
  (scripts/resolve_cohort_fda_classes.py's `resolve`, offline once that has
  run). OnSIDES is keyed by the same RxNorm ingredient ids. A molecule that
  reaches no ingredient, or two, has no label effects.
- **OnSIDES carries no MedDRA hierarchy** (MedDRA's is licensed), so it cannot
  say which terms are nervous-system or psychiatric. ADReCS (Cai et al. 2015,
  doi:10.1093/nar/gku1066) publishes MedDRA's SOC -> HLGT -> HLT -> PT tree
  with the MedDRA codes, and v3.3 is pinned the same way. It is read locally as
  a lookup and nothing of it leaves this database; the site states no open
  licence. A Wikidata route (MedDRA ID -> MeSH -> tree C10/F03) was measured
  first and reached 95 nervous-system terms of the 4,800 the catalogue's labels
  use, missing Depression, Hallucination and every LLT (DATA-QUALITY-LOG,
  2026-10-14).

How each OnSIDES term is placed (`label_effect_terms.placement`):

  pt           a preferred term ADReCS has, by its code. Its SOCs are every
               SOC it is filed under (MedDRA is multi-axial).
  llt_one      a lowest-level term whose exact name is a synonym of exactly
               one ADReCS PT: it is counted as that PT, so a US label's
               "Paresthesia" and a UK label's "Paraesthesia" are one effect.
  llt_several  an LLT whose name is a synonym of several PTs ("Convulsion").
               It stays its own effect, never resolved to one of them; its
               SOCs are those every candidate PT shares, which is what can be
               said of it whichever PT is meant.
  unplaced     neither. Kept as its own effect, with no SOC.

A name match is used only for the LLT -> PT step, inside MedDRA's own
vocabulary, whose LLT names are unique by MedDRA's design; it is never used to
reach a molecule (invariant 15) and is refused where it reaches more than one
PT.

What it writes, and nothing else (a rebuild wipes it; rerun after one):
`label_effect_molecules` (each molecule's ingredient and how many of its
single-ingredient labels there are, by country), `label_effects` (each effect
and on how many of those labels it appears), `label_effect_terms` (how each
OnSIDES term was placed) and one build_manifest key. Which effects make a
profile - how many labels, which SOCs - is the answer key's decision, in
analysis/similarity_harness/label_key.json, not this script's.

    python3 scripts/resolve_cohort_label_effects.py            # write
    python3 scripts/resolve_cohort_label_effects.py --dry-run  # report, write nothing
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
import xml.etree.ElementTree as ET
import zipfile

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common
import resolve_cohort_fda_classes as fda
import resolve_cohort_mesh_structure as mesh_struct

TABLES = ("label_effect_molecules", "label_effects", "label_effect_terms")
CACHE = common.DB / "cache"

ONSIDES_VERSION = "v3.1.1"
ONSIDES_URL = ("https://github.com/tatonetti-lab/onsides/releases/download/"
               f"{ONSIDES_VERSION}/onsides-{ONSIDES_VERSION}.zip")
ONSIDES_FILE = CACHE / "onsides" / f"onsides-{ONSIDES_VERSION}.zip"
ONSIDES_SHA256 = "7739c73336786c92e73ca383af92d3f2814caf5e94206e08475b86d5a5ec22b9"

ADRECS_VERSION = "v3.3"
ADRECS_URL = f"http://www.bio-add.org/ADReCS/download/{ADRECS_VERSION}/ADR_ontology_{ADRECS_VERSION}.xlsx"
ADRECS_FILE = CACHE / "adrecs" / f"ADR_ontology_{ADRECS_VERSION}.xlsx"
ADRECS_SHA256 = "142bd797d8e101bf4d3f01ea50b6afbfdc55f84a06420092d75c565fbca68215"

USER_AGENT = fda.USER_AGENT


class PinError(Exception):
    """A pinned file whose checksum is not the one this script was written for."""


def ensure_pinned(path, url, sha, refresh=False):
    """The pinned file, downloaded once. A file that is not byte-for-byte the
    pinned release is refused, never read: a different release is a different
    answer key, and has to be adopted by changing the pin."""
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {url} ...")
        with requests.get(url, stream=True, timeout=120,
                          headers={"User-Agent": USER_AGENT}) as resp:
            resp.raise_for_status()
            tmp = path.with_suffix(path.suffix + ".part")
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(1 << 20):
                    fh.write(chunk)
            tmp.replace(path)
    got = common.sha256(path)
    if got != sha:
        raise PinError(f"{path} has sha256 {got}, not the pinned {sha}.")
    return path


# --------------------------------------------------------------- ADReCS

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_xlsx_rows(path):
    """The first sheet of an .xlsx as a list of {column letter: text}, read
    with the standard library (an .xlsx is zipped XML)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
        sheet = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))[0]
        rows = []
        for r in ET.fromstring(z.read(sheet)).iter(f"{_NS}row"):
            out = {}
            for c in r.findall(f"{_NS}c"):
                v = c.find(f"{_NS}v")
                if v is None:
                    t = c.find(f"{_NS}is/{_NS}t")
                    val = t.text if t is not None else None
                else:
                    val = shared[int(v.text)] if c.get("t") == "s" else v.text
                out[re.match(r"[A-Z]+", c.get("r")).group(0)] = val
            rows.append(out)
    return rows


def load_hierarchy(path):
    """ADReCS's ontology sheet as three lookups.

    Its first column is a dotted position ('17' a SOC, '17.01.02.003' a PT),
    the third the term, the fourth '|'-joined synonyms, the fifth the MedDRA
    code. Returns {"soc": {soc code: name}, "pt": {pt code: {"name", "socs"}},
    "synonym": {lower-cased name: set of pt codes}}.
    """
    rows = read_xlsx_rows(path)
    header = rows[0]
    if (header.get("A"), header.get("C"), header.get("E")) != ("ADRECS_ID", "ADR_TERM", "MEDDRA_CODE"):
        raise PinError(f"{path} does not have the ADReCS ontology's columns: {header}")
    soc_code, soc, pt, synonym = {}, {}, {}, collections.defaultdict(set)
    for r in rows[1:]:
        pos, code = (r.get("A") or "").strip(), (r.get("E") or "").strip()
        if not pos or not code:
            continue
        if "." not in pos:
            soc_code[pos] = code
            soc[code] = r.get("C")
    for r in rows[1:]:
        pos, code = (r.get("A") or "").strip(), (r.get("E") or "").strip()
        if pos.count(".") != 3 or not code:
            continue
        rec = pt.setdefault(code, {"name": r.get("C"), "socs": set()})
        rec["socs"].add(soc_code[pos.split(".")[0]])
        for s in [r.get("C") or ""] + (r.get("D") or "").split("|"):
            s = s.strip()
            if s and s != "Not Available":
                synonym[s.lower()].add(code)
    return {"soc": soc, "pt": pt, "synonym": dict(synonym)}


def place_term(meddra_id, name, term_type, hierarchy):
    """(effect, placement, socs) for one OnSIDES term; see the module docstring."""
    pt = hierarchy["pt"]
    if term_type == "PT" and meddra_id in pt:
        return meddra_id, "pt", set(pt[meddra_id]["socs"])
    if term_type == "LLT":
        found = hierarchy["synonym"].get(name.strip().lower(), set())
        if len(found) == 1:
            (code,) = found
            return code, "llt_one", set(pt[code]["socs"])
        if found:
            return meddra_id, "llt_several", set.intersection(*(pt[c]["socs"] for c in found))
    return meddra_id, "unplaced", set()


# --------------------------------------------------------------- OnSIDES

def _csv(z, name):
    with z.open(f"csv/{name}.csv") as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))


def read_onsides(path, ingredients):
    """What OnSIDES says about these RxNorm ingredients.

    Returns (labels, effects, terms, counts):
      labels  {ingredient: Counter(country -> single-ingredient labels)}
      effects {ingredient: {meddra_id: {label_id: set(sections)}}}
      terms   {meddra_id: (name, term_type)} for every term in `effects`
    A label is read only when every product it covers reaches the same one
    ingredient. Columns are read by name: v3.1.1's ingredient-to-product file
    has them in the opposite order to its schema (fixed in v3.2.1's DDL).
    """
    wanted = set(ingredients)
    counts = collections.Counter()
    with zipfile.ZipFile(path) as z:
        source = {r["label_id"]: r["source"] for r in _csv(z, "product_label")}
        ings_of_product = collections.defaultdict(set)
        for r in _csv(z, "vocab_rxnorm_ingredient_to_product"):
            ings_of_product[r["product_id"]].add(r["ingredient_id"])
        ings_of_label = collections.defaultdict(set)
        for r in _csv(z, "product_to_rxnorm"):
            ings_of_label[r["label_id"]] |= ings_of_product.get(r["rxnorm_product_id"], set())
        ingredient_of_label = {}
        for label, ings in ings_of_label.items():
            if len(ings) != 1:
                counts["labels_combination"] += 1
                continue
            (ing,) = ings
            if ing in wanted:
                ingredient_of_label[label] = ing
        labels = collections.defaultdict(collections.Counter)
        for label, ing in ingredient_of_label.items():
            labels[ing][source[label]] += 1
        counts["labels_read"] = len(ingredient_of_label)

        effects = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(set)))
        for r in _csv(z, "product_adverse_effect"):
            ing = ingredient_of_label.get(r["product_label_id"])
            if ing is None or not r["effect_meddra_id"]:
                continue
            effects[ing][r["effect_meddra_id"]][r["product_label_id"]].add(r["label_section"])
            counts["effect_rows_read"] += 1
        used = {m for per in effects.values() for m in per}
        terms = {r["meddra_id"]: (r["meddra_name"], r["meddra_term_type"])
                 for r in _csv(z, "vocab_meddra_adverse_effect") if r["meddra_id"] in used}
    return labels, effects, terms, counts


# --------------------------------------------------------------- resolve

def resolve(ingredient_of, labels, effects, terms, hierarchy):
    """The three tables' rows.

    `ingredient_of` is {parent_molregno: rxcui}. Effects are counted per label:
    a label listing both an LLT and the PT it is counted as lists that effect
    once. Two parents reaching one ingredient (haloperidol and its decanoate,
    which RxNorm files as one drug) each get its rows; the answer key decides
    what to make of a shared label.
    """
    placed = {m: place_term(m, name, tt, hierarchy) for m, (name, tt) in terms.items()}
    mol_rows, effect_rows = [], []
    per_ingredient = {}
    for ing in sorted(set(ingredient_of.values())):
        by_effect = collections.defaultdict(lambda: collections.defaultdict(set))
        for m, by_label in effects.get(ing, {}).items():
            effect = placed[m][0]
            for label, sections in by_label.items():
                by_effect[effect][label] |= sections
        per_ingredient[ing] = by_effect
    for parent, ing in sorted(ingredient_of.items()):
        n = sum(labels.get(ing, {}).values())
        if not n:
            continue
        by_source = "|".join(f"{s}:{c}" for s, c in sorted(labels[ing].items()))
        mol_rows.append((parent, ing, n, by_source))
        for effect, by_label in sorted(per_ingredient[ing].items()):
            sections = "|".join(sorted(set().union(*by_label.values())))
            effect_rows.append((parent, effect, len(by_label), sections))
    term_rows = []
    for m, (name, tt) in sorted(terms.items()):
        effect, placement, socs = placed[m]
        term_rows.append((m, tt, name, effect, placement, "|".join(sorted(socs)) or None))
    return mol_rows, effect_rows, term_rows


# --------------------------------------------------------------- write

def ensure_tables(conn):
    schema = (common.DB / "schema_cohort.sql").read_text()
    for table in TABLES:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone():
            continue
        m = re.search(r"CREATE TABLE IF NOT EXISTS " + table + r" \(.*?\n\);", schema, re.S)
        if not m:
            raise common.PolicyError(f"{table} is missing from schema_cohort.sql")
        conn.execute(m.group(0))


def write(conn, mol_rows, effect_rows, term_rows):
    """Replace the three tables; returns how many rows changed."""
    ensure_tables(conn)
    changed = 0
    for table, rows in zip(TABLES, (mol_rows, effect_rows, term_rows)):
        before = {tuple(r) for r in conn.execute(f"SELECT * FROM {table}")}
        conn.execute(f"DELETE FROM {table}")
        if rows:
            conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        after = {tuple(r) for r in conn.execute(f"SELECT * FROM {table}")}
        changed += len(before ^ after)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    onsides = ensure_pinned(ONSIDES_FILE, ONSIDES_URL, ONSIDES_SHA256)
    adrecs = ensure_pinned(ADRECS_FILE, ADRECS_URL, ADRECS_SHA256)
    hierarchy = load_hierarchy(adrecs)

    # The FDA backfill's route to an ingredient, from its cache. Run that
    # backfill first; a lookup it never made is made here and cached for it.
    unii_zip = mesh_struct.ensure_unii_file()
    unii_by_key, _ = mesh_struct.load_unii(unii_zip)
    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        molecules = mesh_struct.structures_for(conn, chembl)
    finally:
        conn.close()
        chembl.close()
    rx = fda.RxNav()
    try:
        _, _, _, detail = fda.resolve(molecules, unii_by_key, rx)
    finally:
        rx.save()
    ingredient_of = detail["ingredient"]
    print(f"  {len(ingredient_of)} molecules reach one RxNorm ingredient; reading OnSIDES ...")

    labels, effects, terms, counts = read_onsides(onsides, set(ingredient_of.values()))
    mol_rows, effect_rows, term_rows = resolve(ingredient_of, labels, effects, terms, hierarchy)
    by_country = collections.Counter()
    for r in mol_rows:
        for part in r[3].split("|"):
            country, n = part.split(":")
            by_country[country] += int(n)
    shared = collections.Counter(ingredient_of.values())
    summary = {
        "run_date": datetime.date.today().isoformat(),
        "onsides": ONSIDES_VERSION, "onsides_sha256": ONSIDES_SHA256,
        "adrecs": ADRECS_VERSION, "adrecs_sha256": ADRECS_SHA256,
        "rxnav_version": rx.cache["meta"].get("version"),
        "unii_archive_sha256": common.sha256(unii_zip),
        "chembl_release": common.CHEMBL_RELEASE,
        "socs": dict(sorted(hierarchy["soc"].items())),
        "molecules_with_ingredient": len(ingredient_of),
        "molecules_with_labels": len(mol_rows),
        "ingredients_reached_by_several_molecules": sum(1 for n in shared.values() if n > 1),
        "labels_by_country": dict(sorted(by_country.items())),
        "effect_rows": len(effect_rows), "terms": len(term_rows),
        "terms_by_placement": dict(sorted(collections.Counter(r[4] for r in term_rows).items())),
        "counts": dict(sorted(counts.items())),
    }
    conn = sqlite3.connect(args.db, isolation_level=None, timeout=300)
    try:
        conn.execute("BEGIN IMMEDIATE")
        summary["rows_changed"] = write(conn, mol_rows, effect_rows, term_rows)
        conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                     ("label_effects", json.dumps(summary, sort_keys=True)))
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()

    print(f"{len(mol_rows)} of {len(ingredient_of)} molecules have a single-ingredient label "
          f"({summary['labels_by_country']}); {len(effect_rows)} effect rows over "
          f"{len(term_rows)} OnSIDES terms; {summary['rows_changed']} rows changed"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in summary["terms_by_placement"].items():
        print(f"  {n:5d}  terms placed {k}")
    print(f"  {summary['ingredients_reached_by_several_molecules']} ingredients are reached by "
          "more than one molecule (a drug and its ester or salt, as RxNorm files them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
