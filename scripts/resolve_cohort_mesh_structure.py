#!/usr/bin/env python3
"""Backfill MeSH chemical-structure classes into db/cohort1.db, via FDA UNII.

A structure class is where MeSH files a chemical by what it is built like:
caffeine under "Xanthines", diazepam under "Benzodiazepinones", brexpiprazole
under "Thiophenes" and "Quinolones". It answers a different question from the
pharmacological actions (scripts/resolve_cohort_pharm_actions.py), which say
what a drug *does*, and the two are kept as two sources for that reason:
clozapine really is a dibenzazepine beside imipramine, and really is not a
tricyclic antidepressant. A structure class is a label for search and display,
never evidence about a target, and never part of the similarity score.

The route, an identifier at every step (invariant 15):

  1. molecules.inchikey -> FDA UNII, by exact standard InChIKey in FDA's own
     UNII records file (UNII_Records_*.txt from precision.fda.gov). FDA
     registers a UNII from the substance's structure, so this is a structure
     match and not a name match. Only where the parent's InChIKey reaches no
     MeSH record are the InChIKeys of its other forms tried (the salts and
     hydrates the build folded onto it, read from the pinned ChEMBL release),
     because MeSH often files a drug under its salt: lisinopril's heading
     carries lisinopril dihydrate's UNII.
  2. UNII -> the one MeSH record carrying it as a concept's registry number,
     from NLM's descriptor and supplementary-record files for a pinned year
     (desc<YEAR>.gz, supp<YEAR>.gz). A molecule whose UNIIs reach two different
     records is dropped as ambiguous rather than resolved to either
     (invariant 6).
  3. record -> its structure classes. A descriptor sits in the tree itself
     (Caffeine is at D03.132.960.175), so it is filed under the descriptors
     directly above each of its positions (Xanthines). A supplementary record
     is not in the tree; MeSH maps it to headings ("Heading Mapped To"), and
     those are its classes.
  4. classes -> the classes above them, inside the structural branches and at
     or below MIN_DEPTH, so a xanthine is also a purinone and a purine.

It deliberately does not go through PubChem, which the pharmacological actions
did until 2026-10-13; they now take this route too, with a CAS, stereoisomer-
mixture and Wikidata step after it (scripts/resolve_cohort_pharm_actions.py).
PubChem lists a compound's MeSH records by name and registry matching on
its side, and for a sample of this catalogue that list included brand names,
drug combinations and outright wrong compounds (methylprednisolone listed with
exifone, a benzophenone). Where both routes give one answer they agree on 277
of 278 molecules on the record; the one difference is silybin A, which PubChem
matches to the herbal mixture Silymarin itself and the UNII to Silybin, the
heading beneath it.

A drug whose own descriptor is itself a class for another catalogue entry
(MeSH files Ketorolac under Indomethacin, and Pentoxifylline under Theobromine)
is also filed in it, so the class "Indomethacin" lists indomethacin as well as
ketorolac. Each row's carriers name the chain it came by: the ChEMBL form
whose InChIKey matched, the UNII and the molecule's own MeSH record.

A separate backfill, not part of a build: it reads ChEMBL read-only, touches
the network only to fetch the three reference files once (all cached under
db/cache/ and recorded by sha256 in build_manifest), and changes only the
mesh_struct rows of molecule_classes and class_labels and one build_manifest
key. A rebuild wipes those rows, as it wipes the other class backfills; rerun
this after it.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import gzip
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
import resolve_cohort_pharm_actions as pharm

SOURCE = "mesh_struct"

MESH_YEAR = pharm.MESH_YEAR
DESC_FILE = pharm.MESH_FILE
SUPP_URL = ("https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/"
            f"supp{MESH_YEAR}.gz")
SUPP_FILE = pharm.CACHE / "mesh" / f"supp{MESH_YEAR}.gz"

# FDA's UNII archive. "latest" moves, so the copy is kept once fetched and is
# what the backfill reads until --refresh-unii replaces it; the records file
# inside names its own date, and that name and the archive's sha256 go into
# build_manifest.
UNII_URL = "https://precision.fda.gov/uniisearch/archive/latest/UNII_Data.zip"
UNII_FILE = pharm.CACHE / "fda" / "UNII_Data.zip"
# The download answers 403 to a request without a browser-like agent.
UNII_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SubNetwork/1.0"

# The branches of MeSH's Chemicals and Drugs category that file a substance by
# what it is built like. The others file it by what it is for or where it comes
# from - D06 hormones and hormone antagonists, D08 enzymes and coenzymes, D20
# complex mixtures, D23 biological factors, D25 materials, D26 pharmaceutical
# preparations, D27 actions and uses - and a drug's place there is a claim about
# its function, which the pharmacological actions already carry.
STRUCTURE_BRANCHES = frozenset({"D01", "D02", "D03", "D04", "D05",
                                "D09", "D10", "D12", "D13"})
# Depth 1 is the branch itself ("Heterocyclic Compounds", "Organic Chemicals"),
# which holds most of the catalogue and says nothing about any of it.
MIN_DEPTH = 2


# ------------------------------------------------------------------ files

def _download(url, path, user_agent=pharm.USER_AGENT):
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url} ...")
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=pharm.REQUEST_TIMEOUT,
                      headers={"User-Agent": user_agent}) as resp:
        resp.raise_for_status()
        # The raw stream, for the same reason as ensure_mesh_file: the MeSH
        # server marks its .gz files with a gzip Content-Encoding.
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.raw.read(1 << 20, decode_content=False)
                if not chunk:
                    break
                fh.write(chunk)
    tmp.rename(path)
    return path


def ensure_supp_file(path=SUPP_FILE, url=SUPP_URL):
    return path if path.exists() else _download(url, path)


def ensure_unii_file(path=UNII_FILE, url=UNII_URL, refresh=False):
    if refresh or not path.exists():
        _download(url, path, UNII_USER_AGENT)
    return path


def load_unii(path):
    """Standard InChIKey -> sorted UNIIs FDA registers with that structure.

    Returns (mapping, name of the records file inside the archive). Accepts
    the archive or a bare records file, so the tests can hand it a fixture.
    """
    csv.field_size_limit(1 << 30)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.startswith("UNII_Records")]
            if len(names) != 1:
                raise SystemExit(f"{path}: expected one UNII_Records file, found {names}")
            text = zf.read(names[0]).decode("utf-8")
            member = names[0]
    else:
        text = pathlib.Path(path).read_text(encoding="utf-8")
        member = pathlib.Path(path).name
    by_key = collections.defaultdict(set)
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        if r.get("INCHIKEY") and r.get("UNII"):
            by_key[r["INCHIKEY"]].add(r["UNII"])
    return {k: sorted(v) for k, v in by_key.items()}, member


def load_unii_structures(path):
    """Every UNII in FDA's records -> the standard InChIKey FDA registers for
    it, or "" where it registers none (a mixture, a protein, an unspecified
    form). Read by scripts/resolve_cohort_pharm_actions.py."""
    csv.field_size_limit(1 << 30)
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.startswith("UNII_Records")]
        if len(names) != 1:
            raise SystemExit(f"{path}: expected one UNII_Records file, found {names}")
        text = zf.read(names[0]).decode("utf-8")
    return {r["UNII"]: r.get("INCHIKEY") or ""
            for r in csv.DictReader(io.StringIO(text), delimiter="\t") if r.get("UNII")}


def _open(path):
    with open(path, "rb") as probe:
        packed = probe.read(2) == b"\x1f\x8b"
    return (gzip.open if packed else open)(path, "rb")


def load_mesh(desc_path, supp_path, wanted_uniis):
    """Read both MeSH files into what this script needs.

    Every descriptor's name and tree numbers (the hierarchy), the tree-number
    index, and - for the UNIIs in ``wanted_uniis`` only, since the
    supplementary file holds 300,000 records - which records carry each one as
    a concept's registry number, and each such supplementary record's name and
    mapped headings.
    """
    mesh = {"desc": {}, "tree": {}, "supp": {}, "by_unii": collections.defaultdict(set)}

    def registry(el, ui):
        for r in el.findall("ConceptList/Concept/RegistryNumberList/RegistryNumber"):
            if r.text in wanted_uniis:
                mesh["by_unii"][r.text].add(ui)

    with _open(desc_path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "DescriptorRecord":
                continue
            ui = el.findtext("DescriptorUI")
            trees = [t.text for t in el.findall("TreeNumberList/TreeNumber") if t.text]
            mesh["desc"][ui] = (el.findtext("DescriptorName/String"), trees)
            for t in trees:
                mesh["tree"][t] = ui
            registry(el, ui)
            el.clear()
    with _open(supp_path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != "SupplementalRecord":
                continue
            ui = el.findtext("SupplementalRecordUI")
            before = sum(len(v) for v in mesh["by_unii"].values())
            registry(el, ui)
            if sum(len(v) for v in mesh["by_unii"].values()) != before:
                # A leading "*" marks a heading MeSH calls major; both kinds
                # are where the record is filed.
                mapped = [d.text.lstrip("*") for d in el.findall(
                    "HeadingMappedToList/HeadingMappedTo/DescriptorReferredTo/DescriptorUI")
                    if d.text]
                mesh["supp"][ui] = (el.findtext("SupplementalRecordName/String"), mapped)
            el.clear()
    mesh["by_unii"] = {k: sorted(v) for k, v in mesh["by_unii"].items()}
    return mesh


# ------------------------------------------------------------- hierarchy

def depth(tree):
    return tree.count(".") + 1


def structure_trees(mesh, ui):
    """A descriptor's tree positions inside the structural branches."""
    return [t for t in mesh["desc"].get(ui, (None, []))[1]
            if t.split(".", 1)[0] in STRUCTURE_BRANCHES]


def is_class(mesh, ui):
    """True for a descriptor that may name a class here: filed somewhere in a
    structural branch at MIN_DEPTH or deeper."""
    return any(depth(t) >= MIN_DEPTH for t in structure_trees(mesh, ui))


def parents_of(mesh, ui):
    """The descriptors directly above one, inside the structural branches and
    at or below MIN_DEPTH. A descriptor filed in two places has a parent for
    each: Xanthines sits under Alkaloids and under Purinones."""
    out = []
    for t in structure_trees(mesh, ui):
        if "." not in t:
            continue
        up = t.rsplit(".", 1)[0]
        if depth(up) < MIN_DEPTH:
            continue
        p = mesh["tree"].get(up)
        if p and p not in out:
            out.append(p)
    return out


def ancestors(mesh, ui):
    seen, todo = set(), parents_of(mesh, ui)
    while todo:
        p = todo.pop()
        if p not in seen:
            seen.add(p)
            todo.extend(parents_of(mesh, p))
    return seen


def own_classes(mesh, record):
    """Where MeSH files one record, as class descriptors: the descriptors above
    a descriptor's own positions, or a supplementary record's mapped headings."""
    if record in mesh["desc"]:
        found = parents_of(mesh, record)
    else:
        found = [h for h in mesh["supp"].get(record, (None, []))[1] if is_class(mesh, h)]
    return sorted(set(found))


def label_rows(mesh, uis):
    """class_labels rows for these classes and every class above them."""
    seen, todo = {}, list(uis)
    while todo:
        ui = todo.pop()
        if ui in seen:
            continue
        name = mesh["desc"][ui][0]
        parents = parents_of(mesh, ui)
        level = min((depth(t) for t in structure_trees(mesh, ui)), default=None)
        seen[ui] = (SOURCE, ui, level, name, "|".join(parents) or None)
        todo.extend(parents)
    return sorted(seen.values())


def record_name(mesh, record):
    return (mesh["desc"].get(record) or mesh["supp"].get(record) or (None,))[0]


# --------------------------------------------------------------- resolve

def resolve(molecules, mesh, unii_by_key):
    """Decide each molecule's structure classes. Pure, so the rules can be
    tested without any file.

    molecules: [(parent_molregno, [(chembl_id, inchikey), ...])], the parent's
    own structure first and then its other forms. Returns (rows, labels,
    counts, records), where records maps a resolved molecule to its own MeSH
    record.
    """
    counts = collections.Counter()
    resolved = {}                      # parent -> (record, carriers, classes)
    for parent, structures in molecules:
        structures = [(cid, key) for cid, key in structures if key]
        if not structures:
            counts["no_inchikey"] += 1
            continue
        found, via, any_unii = set(), [], False
        # The parent first; its forms only where the parent reaches nothing.
        for i, (chembl_id, key) in enumerate(structures):
            if i == 1 and found:
                break
            for unii in unii_by_key.get(key, ()):
                any_unii = True
                recs = mesh["by_unii"].get(unii, ())
                if recs:
                    found.update(recs)
                    via.append((chembl_id, unii))
        if not found:
            counts["unii_not_in_mesh" if any_unii else "no_unii"] += 1
            continue
        if len(found) > 1:
            counts["ambiguous_several_records"] += 1
            continue
        record = next(iter(found))
        if via[0][0] != structures[0][0]:
            counts["resolved_through_a_form"] += 1
        classes = own_classes(mesh, record)
        if not classes:
            counts["no_structure_class"] += 1
            continue
        chembl_ids = sorted({c for c, _ in via})
        uniis = sorted({u for _, u in via})
        carriers = "|".join(chembl_ids + [f"UNII:{u}" for u in uniis] + [f"MeSH:{record}"])
        resolved[parent] = (record, carriers, classes)
        counts["resolved"] += 1
        counts["via_descriptor" if record in mesh["desc"] else "via_supplementary_record"] += 1

    # A molecule's own descriptor is a class for it too, wherever it is a
    # class for some other entry here.
    in_use = set()
    for record, _, classes in resolved.values():
        for c in classes:
            in_use.add(c)
            in_use |= ancestors(mesh, c)
    rows, used = [], set()
    for parent, (record, carriers, classes) in resolved.items():
        mine = list(classes)
        if record in in_use and record not in mine and is_class(mesh, record):
            mine.append(record)
            counts["filed_under_own_heading"] += 1
        for ui in mine:
            rows.append((parent, SOURCE, ui, "", mesh["desc"][ui][0], carriers))
            used.add(ui)
    rows.sort()
    records = {p: r for p, (r, _, _) in resolved.items()}
    return rows, label_rows(mesh, used), counts, records


def structures_for(conn, chembl):
    """[(parent_molregno, [(chembl_id, inchikey), ...])], parent first.

    The parent's key is the one the catalogue stores; each other form's is
    read from the pinned ChEMBL release by molregno.
    """
    forms = collections.defaultdict(list)
    for p, m, cid in conn.execute("SELECT parent_molregno, molregno, chembl_id"
                                  " FROM molecule_forms WHERE is_parent = 0"
                                  " ORDER BY parent_molregno, molregno"):
        forms[p].append((m, cid))
    keys = {}
    wanted = sorted({m for v in forms.values() for m, _ in v})
    for chunk in common.chunked(wanted):
        marks = ",".join("?" * len(chunk))
        for m, k in chembl.execute("SELECT molregno, standard_inchi_key FROM compound_structures"
                                   f" WHERE molregno IN ({marks})", chunk):
            keys[m] = k
    out = []
    for p, cid, key in conn.execute("SELECT parent_molregno, chembl_id, inchikey"
                                    " FROM molecules ORDER BY parent_molregno"):
        out.append((p, [(cid, key)] + [(fc, keys.get(m)) for m, fc in forms[p]]))
    return out


def backfill(conn, mesh, molecules, unii_by_key, manifest):
    classes_mod.ensure_tables(conn)
    rows, labels, counts, records = resolve(molecules, mesh, unii_by_key)
    before = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    classes_mod.write(conn, rows, labels, sources=(SOURCE,))
    after = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    summary = dict(manifest)
    summary.update({
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "molecules": len(molecules), "rows": len(rows), "labels": len(labels),
        "classes_used": len({r[2] for r in rows}), "rows_changed": len(before ^ after),
        "structure_branches": sorted(STRUCTURE_BRANCHES), "min_depth": MIN_DEPTH,
        "counts": dict(counts),
    })
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 ("mesh_structure_classes", json.dumps(summary, sort_keys=True)))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--refresh-unii", action="store_true",
                        help="re-download FDA's UNII archive instead of reading the cached copy")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    desc = pharm.ensure_mesh_file()
    supp = ensure_supp_file()
    unii_zip = ensure_unii_file(refresh=args.refresh_unii)
    print(f"  reading {unii_zip.name} ...")
    unii_by_key, unii_member = load_unii(unii_zip)

    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        molecules = structures_for(conn, chembl)
        wanted = {u for _, structs in molecules for _, k in structs if k
                  for u in unii_by_key.get(k, ())}
        print(f"  reading {desc.name} and {supp.name} ...")
        mesh = load_mesh(desc, supp, wanted)
        manifest = {
            "mesh_release": f"desc{MESH_YEAR}+supp{MESH_YEAR}",
            "mesh_desc_sha256": common.sha256(desc),
            "mesh_supp_sha256": common.sha256(supp),
            "unii_records": unii_member,
            "unii_archive_sha256": common.sha256(unii_zip),
            "chembl_release": common.CHEMBL_RELEASE,
        }
        conn.execute("BEGIN")
        s = backfill(conn, mesh, molecules, unii_by_key, manifest)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
        chembl.close()

    c = s["counts"]
    print(f"{c.get('resolved', 0)} of {s['molecules']} molecules carry a MeSH structure "
          f"class; {s['rows']} rows over {s['classes_used']} classes, {s['labels']} class "
          f"labels with their parents; {s['rows_changed']} rows changed"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in sorted(c.items()):
        print(f"  {n:5d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
