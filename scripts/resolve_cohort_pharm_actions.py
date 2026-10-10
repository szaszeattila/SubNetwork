#!/usr/bin/env python3
"""Backfill MeSH pharmacological actions into db/cohort1.db, via PubChem.

A pharmacological action is what NLM's MeSH indexers record a drug as doing:
"Antidepressive Agents, Tricyclic", "Phosphodiesterase Inhibitors",
"Antipsychotic Agents". It is the one class source here that answers the
question the page asks - which molecules act alike - rather than what a drug is
used for (ATC, taken back off the page) or what it is built like (a structural
taxonomy). It is still a curated label and not evidence: it never becomes a
claim, never reaches the similarity score, and says nothing about a target.

The route, identifier at every step (invariant 15):

  1. molecules.inchikey -> PubChem compound id(s), by exact InChIKey.
  2. CID -> the MeSH pharmacological actions PubChem lists for it, each as a
     MeSH *concept* id (M0001382), from PUG-View's "MeSH Pharmacological
     Classification" heading.
  3. concept id -> MeSH descriptor (D000927) and its tree numbers, from NLM's
     own descriptor file for a pinned year (desc<MESH_YEAR>.gz, cached under
     db/cache/mesh/ and recorded by sha256 in build_manifest).
  4. tree numbers -> the actions above it, inside the pharmacological-action
     branch (D27), so "Antidepressive Agents, Tricyclic" also files a drug
     under "Antidepressive Agents".

Step 2 rests on PubChem's link between a compound and a MeSH record, which
PubChem makes from names and registry numbers on its side. This script never
searches by a name itself, but that link is not an identifier join it can
check, and it is stated as such wherever the result is described.

An InChIKey can match more than one PubChem compound (usually duplicate
deposits of one structure). The actions are then taken only if every matched
compound that lists any lists the same set; where they disagree the molecule is
dropped as ambiguous rather than resolved to a guess (invariant 6). A concept id
the pinned MeSH year does not hold is dropped and counted.

PubChem joins a compound to MeSH records by name, and a brand name or code that
means two things joins both: tafamidis is linked to Flexion's triamcinolone
product through "FX006", DMSO to fluocinonide through "Topsym", a fluocinonide
solution in DMSO. PubChem's action list then carries the other record's actions.
So each action is also traced to the MeSH records PubChem links the compound to
(its "MeSH Entry Terms"), and each record is judged against the molecule's
identity (Judge, below): a record whose registry numbers, or whose mapped
headings' registry numbers, name a different structure, or a combination that
holds another drug, is set aside. An action is dropped only when every record
that supplies it was set aside; a record nothing identifies is not second-guessed.
The dropped links are listed, with the record and the reason, in the
build_manifest summary.

The identity is read by identifier only: the molecule's InChIKeys (its own, its
forms', and the active moiety ChEMBL names for each) against the InChIKey FDA
registers for each UNII a MeSH record carries, compared on the first InChIKey
block so an enantiomer or a racemate is the same substance. The molecule's own
MeSH record is the one its UNII reaches, the route
scripts/resolve_cohort_mesh_structure.py documents.

A separate backfill, not part of a build: it reads ChEMBL read-only (for forms
and active moieties) and changes only the mesh_pa rows of molecule_classes and
class_labels, and one build_manifest key. A rebuild wipes those rows, as it wipes the Wikipedia and trial backfills;
rerun this after it. Every PubChem response is cached under db/cache/pubchem/,
so a rerun is offline unless --refresh is given.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import gzip
import hashlib
import json
import pathlib
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET

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
PUBCHEM_CACHE = CACHE / "pubchem"

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest"
PA_HEADING = "MeSH Pharmacological Classification"

# The pharmacological-action branch of MeSH, and how deep an action has to sit
# to be a class worth offering. Depths 1-3 are "Chemical Actions and Uses",
# "Pharmacologic Actions" and its three halves ("Molecular Mechanisms of
# Pharmacological Action", "Physiological Effects of Drugs", "Therapeutic
# Uses"), which hold nearly every drug and say nothing about any of them.
PA_BRANCH = "D27"
MIN_DEPTH = 4

USER_AGENT = "SubNetwork/1.0 (cohort-1 drug-target interaction map)"
MIN_REQUEST_INTERVAL = 0.25     # PubChem asks for no more than 5 a second
REQUEST_RETRIES = 5
REQUEST_TIMEOUT = 60
_last_request_at = 0.0


class PubChemError(RuntimeError):
    """A PubChem request failed after retries - never read as "no actions"."""


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


# --------------------------------------------------------------- PubChem

def _throttle():
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _cached_get(url, cache_key, refresh=False):
    """One GET, cached on disk by key. Returns (status, text); 404 is an answer."""
    PUBCHEM_CACHE.mkdir(parents=True, exist_ok=True)
    path = PUBCHEM_CACHE / (hashlib.sha256(cache_key.encode()).hexdigest() + ".json")
    if path.exists() and not refresh:
        rec = json.loads(path.read_text())
        return rec["status"], rec["body"]
    last = None
    for attempt in range(REQUEST_RETRIES):
        try:
            _throttle()
            resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                                headers={"User-Agent": USER_AGENT})
            if resp.status_code in (200, 404):
                path.write_text(json.dumps({"key": cache_key, "status": resp.status_code,
                                            "body": resp.text}))
                return resp.status_code, resp.text
            last = f"HTTP {resp.status_code}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.exceptions.RequestException as err:
            last = repr(err)
        time.sleep(min(2 * (2 ** attempt), 30))
    raise PubChemError(f"{cache_key}: {last}")


def fetch_cids(inchikey, refresh=False):
    status, body = _cached_get(f"{PUG}/pug/compound/inchikey/{inchikey}/cids/TXT",
                               "cids:" + inchikey, refresh)
    if status == 404:
        return []
    return [int(x) for x in body.split() if x.strip().isdigit()]


def fetch_actions(cid, refresh=False):
    """[(concept id, name)] PubChem lists for one compound, or [] for none."""
    url = (f"{PUG}/pug_view/data/compound/{cid}/JSON?heading="
           + requests.utils.quote(PA_HEADING))
    status, body = _cached_get(url, f"pa:{cid}", refresh)
    if status == 404:
        return []
    record = json.loads(body).get("Record", {})
    out = []
    for ref in record.get("Reference", []):
        if ref.get("SourceName") == "Medical Subject Headings (MeSH)" and ref.get("SourceID"):
            pair = (ref["SourceID"], ref.get("Name"))
            if pair not in out:
                out.append(pair)
    return out


def fetch_records(cid, refresh=False):
    """The MeSH concept ids PubChem links to one compound ("MeSH Entry Terms"),
    or [] for none. Each belongs to one MeSH record."""
    url = (f"{PUG}/pug_view/data/compound/{cid}/JSON?heading="
           + requests.utils.quote(TERMS_HEADING))
    status, body = _cached_get(url, f"mesh_terms:{cid}", refresh)
    if status == 404:
        return []
    out = []
    for ref in json.loads(body).get("Record", {}).get("Reference", []):
        if (ref.get("SourceName") == "Medical Subject Headings (MeSH)"
                and ref.get("SourceID") and ref["SourceID"] not in out):
            out.append(ref["SourceID"])
    return out


# -------------------------------------------------------- record identity

TERMS_HEADING = "MeSH Entry Terms"
DRUG_COMBINATIONS = "D004338"

# The verdicts that set a record aside. Every other verdict keeps it.
SET_ASIDE = frozenset({"different_substance", "combination_with_another_drug"})

Identity = collections.namedtuple("Identity", "blocks uniis own")
NO_IDENTITY = Identity(frozenset(), frozenset(), None)


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


class Judge:
    """Whether a MeSH record PubChem links to a compound is that compound.

    A record is set aside only on positive evidence that it is something else,
    because identifiers disagree about form far more often than about
    substance: a salt, a hydrate, an anomer and a polymer are each drawn
    differently by FDA and by ChEMBL. So a record's UNII counts against a
    molecule only where ChEMBL knows that structure as a *different* parent
    molecule, and a record that cannot be compared is kept.

    records: load_records(). unii_key: every FDA UNII -> the InChIKey FDA
    registers for it, "" where FDA gives it no structure. parent_blocks: an
    InChIKey -> the first InChIKey blocks of the parent and active moiety
    ChEMBL files that exact structure under, or an empty set where ChEMBL does
    not hold it. Only first blocks (the skeleton) are compared, so an
    enantiomer and its racemate count as one substance.
    """

    def __init__(self, records, unii_key, parent_blocks):
        self.r = records
        self.unii_key = unii_key
        self.parent_blocks = parent_blocks

    def record_of(self, concept):
        return self.r["concept"].get(concept)

    def actions(self, record):
        return self.r["pa"].get(record, frozenset())

    def uniis(self, record):
        return [u for u in self.r["rn"].get(record, ()) if u in self.unii_key]

    def identity_of(self, record, ident):
        """same | different | unknown, from the record's own UNIIs alone."""
        uniis = self.uniis(record)
        if not uniis:
            return "unknown"
        if any(u in ident.uniis for u in uniis):
            return "same"
        if any(not self.unii_key[u] for u in uniis):
            # A UNII FDA gives no structure (a mixture, an unspecified form)
            # may be this very molecule; nothing here can say it is not.
            return "unknown"
        other = False
        for u in uniis:
            key = self.unii_key[u]
            known = self.parent_blocks(key)
            if key[:14] in ident.blocks or known & ident.blocks:
                return "same"
            other = other or bool(known)
        return "different" if other else "unknown"

    def verdict(self, record, ident):
        """own | filed_under | same_structure | unidentified, which keep it,
        or different_substance | combination_with_another_drug, which set it
        aside."""
        if ident.own and record == ident.own:
            return "own"
        if ident.own and (record in self.r["mapped"].get(ident.own, ())
                          or record in self.r["parents"].get(ident.own, ())):
            # MeSH itself files the molecule's own record under this one:
            # prednisolone acetate under Prednisolone, Silybin under Silymarin.
            return "filed_under"
        mine = self.identity_of(record, ident)
        if mine != "unknown" or self.uniis(record):
            return {"same": "same_structure", "different": "different_substance"}.get(
                mine, "unidentified")
        # Nothing on the record says what it is, so read the headings MeSH
        # maps it to.
        mapped = self.r["mapped"].get(record, [])
        heads = [h for h in mapped if h != DRUG_COMBINATIONS]
        same = [h for h in heads
                if h == ident.own or self.identity_of(h, ident) == "same"]
        if DRUG_COMBINATIONS in mapped:
            # A combination speaks for this molecule only when nothing else in
            # it is a drug: brexanolone's infusion product is brexanolone and a
            # cyclodextrin, which MeSH gives no action; "Ambene" is
            # phenylbutazone with aminopyrine, dexamethasone and vitamins.
            if same and any(h not in same and self.actions(h) for h in heads):
                return "combination_with_another_drug"
        elif len(heads) == 1 and not same and self.identity_of(heads[0], ident) == "different":
            # One mapped heading says what a product is: FX006 is an
            # extended-release Triamcinolone Acetonide. A chemical-name record
            # maps to several structural headings instead (LY-411575 to
            # Alanine and Azepines), which are parts of it, not its identity.
            return "different_substance"
        return "same_structure" if same else "unidentified"


def filter_actions(acts, concepts, ident, mesh, judge):
    """Keep the actions of one compound that some kept record supplies.

    acts: [(action concept, name)] PubChem lists; concepts: the MeSH concept
    ids it links the compound to. Returns (kept, set aside), the second as
    [(action descriptor, record, verdict)]. An action no linked record
    supplies is kept: there is nothing to judge it by.
    """
    records = []
    for c in concepts:
        r = judge.record_of(c)
        if r and r not in records:
            records.append(r)
    verdicts = {r: judge.verdict(r, ident) for r in records}
    kept, aside = [], []
    for concept, name in acts:
        ui = mesh["concept"].get(concept)
        suppliers = [r for r in records if ui and ui in judge.actions(r)]
        if not suppliers or any(verdicts[r] not in SET_ASIDE for r in suppliers):
            kept.append((concept, name))
        else:
            aside.extend((ui, r, verdicts[r]) for r in suppliers)
    return kept, aside


def own_record(structures, unii_by_key, by_unii):
    """The one MeSH record a molecule's UNII reaches: the parent's structure
    first, its forms only where the parent reaches nothing. None when there is
    none or more than one."""
    found = set()
    for i, key in enumerate(structures):
        if i == 1 and found:
            break
        for u in unii_by_key.get(key, ()):
            found.update(by_unii.get(u, ()))
    return next(iter(found)) if len(found) == 1 else None


def chembl_parent_blocks(chembl):
    """InChIKey -> the first blocks of the parent and active moiety ChEMBL
    files that exact structure under; an empty set where it holds none."""
    cache = {}

    def lookup(key):
        if key not in cache:
            found = set()
            for p, a in chembl.execute(
                    "SELECT h.parent_molregno, h.active_molregno FROM compound_structures cs"
                    " JOIN molecule_hierarchy h ON h.molregno = cs.molregno"
                    " WHERE cs.standard_inchi_key = ?", (key,)):
                for m in {p, a} - {None}:
                    row = chembl.execute("SELECT standard_inchi_key FROM compound_structures"
                                         " WHERE molregno = ?", (m,)).fetchone()
                    if row and row[0]:
                        found.add(row[0][:14])
            cache[key] = frozenset(found)
        return cache[key]
    return lookup


def identities(conn, chembl, unii_by_key, records):
    """{parent_molregno: Identity}: every InChIKey block of the molecule, its
    forms and the active moiety ChEMBL names for each, and its own record."""
    forms = collections.defaultdict(list)
    for p, m, is_parent in conn.execute(
            "SELECT parent_molregno, molregno, is_parent FROM molecule_forms"
            " ORDER BY parent_molregno, is_parent DESC, molregno"):
        forms[p].append(m)
    regnos = sorted({m for v in forms.values() for m in v})
    active, key = {}, {}
    for chunk in common.chunked(regnos):
        marks = ",".join("?" * len(chunk))
        for m, a in chembl.execute("SELECT molregno, active_molregno FROM molecule_hierarchy"
                                   f" WHERE molregno IN ({marks})", chunk):
            if a is not None:
                active[m] = a
    wanted = sorted(set(regnos) | set(active.values()))
    for chunk in common.chunked(wanted):
        marks = ",".join("?" * len(chunk))
        for m, k in chembl.execute("SELECT molregno, standard_inchi_key FROM compound_structures"
                                   f" WHERE molregno IN ({marks})", chunk):
            key[m] = k
    by_unii = collections.defaultdict(set)
    for rec, rns in records["rn"].items():
        for u in rns:
            by_unii[u].add(rec)
    out = {}
    for p, parent_key in conn.execute("SELECT parent_molregno, inchikey FROM molecules"):
        keys = [parent_key] + [key.get(m) for m in forms[p]]
        keys = [k for k in dict.fromkeys(keys) if k]
        moieties = [key.get(active.get(m)) for m in forms[p]]
        blocks = frozenset(k[:14] for k in keys + [k for k in moieties if k])
        uniis = frozenset(u for k in keys for u in unii_by_key.get(k, ()))
        out[p] = Identity(blocks, uniis, own_record(keys, unii_by_key, by_unii))
    return out


# --------------------------------------------------------------- resolve

def resolve(molecules, mesh, cids_for, actions_for, records_for=None,
            idents=None, judge=None):
    """Decide each molecule's actions. Pure given its fetchers, so the rules
    can be tested without the network.

    molecules: [(parent_molregno, inchikey)]. With records_for, idents and
    judge, each compound's actions are first filtered by filter_actions.
    Returns (rows, labels, counts, set aside), the last as sorted
    (parent, action, record, verdict) tuples.
    """
    counts = collections.Counter()
    rows, used, aside = [], set(), set()
    for parent, key in molecules:
        if not key:
            counts["no_inchikey"] += 1
            continue
        cids = cids_for(key)
        if not cids:
            counts["no_pubchem_compound"] += 1
            continue
        by_cid = {}
        for cid in cids:
            acts = actions_for(cid)
            if records_for is not None and acts:
                acts, dropped = filter_actions(acts, records_for(cid),
                                               (idents or {}).get(parent, NO_IDENTITY),
                                               mesh, judge)
                aside.update((parent,) + d for d in dropped)
            by_cid[cid] = frozenset(acts)
        listed = {cid: acts for cid, acts in by_cid.items() if acts}
        if not listed:
            counts["no_actions"] += 1
            continue
        if len(set(listed.values())) > 1:
            counts["ambiguous_compounds_disagree"] += 1
            continue
        acts = next(iter(listed.values()))
        carriers = "|".join(f"CID:{c}" for c in sorted(listed))
        found = []
        for concept, name in sorted(acts):
            ui = mesh["concept"].get(concept)
            if not ui:
                counts["concept_not_in_mesh_year"] += 1
                continue
            if ui not in found:
                found.append(ui)
        if not found:
            counts["no_actions"] += 1
            continue
        counts["resolved"] += 1
        # Only where several compounds each listed the same actions: one
        # listing and the rest silent is a single source, not an agreement.
        if len(listed) > 1:
            counts["resolved_over_several_compounds"] += 1
        for ui in found:
            rows.append((parent, SOURCE, ui, "", mesh["desc"][ui][0], carriers))
            used.add(ui)
    rows.sort()
    aside = sorted(aside)
    # A link is set aside once however many compounds or records carried it.
    links = {(p, a) for p, a, _, _ in aside}
    kept_links = {(r[0], r[2]) for r in rows}
    counts["links_set_aside"] = len(links - kept_links)
    counts["molecules_with_a_link_set_aside"] = len({p for p, _ in links - kept_links})
    if not counts["links_set_aside"]:
        del counts["links_set_aside"], counts["molecules_with_a_link_set_aside"]
    return rows, label_rows(mesh, used), counts, aside


def backfill(conn, mesh, mesh_sha, cids_for, actions_for, limit=None,
             records_for=None, idents=None, judge=None, extra=None):
    classes_mod.ensure_tables(conn)
    molecules = conn.execute("SELECT parent_molregno, inchikey FROM molecules"
                             " ORDER BY parent_molregno").fetchall()
    if limit:
        molecules = molecules[:limit]
    rows, labels, counts, aside = resolve(molecules, mesh, cids_for, actions_for,
                                          records_for, idents, judge)
    before = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    classes_mod.write(conn, rows, labels, sources=(SOURCE,))
    after = {tuple(r) for r in conn.execute(
        "SELECT * FROM molecule_classes WHERE source = ?", (SOURCE,))}
    summary = {
        "mesh_release": f"desc{MESH_YEAR}", "mesh_sha256": mesh_sha,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "molecules": len(molecules), "rows": len(rows), "labels": len(labels),
        "actions_used": len({r[2] for r in rows}), "rows_changed": len(before ^ after),
        "counts": dict(counts),
        # What was set aside and why, so the filter can be audited without
        # rerunning it: [parent_molregno, action, record, verdict].
        "set_aside": [list(a) for a in aside],
    }
    summary.update(extra or {})
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 ("mesh_pharm_actions", json.dumps(summary, sort_keys=True)))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch from PubChem instead of reading the cache")
    parser.add_argument("--limit", type=int, default=None, help="first N molecules only")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    path = ensure_mesh_file()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"  reading {path.name} ...")
    mesh = load_mesh(path)
    print(f"    {len(mesh['desc'])} descriptors, {len(mesh['concept'])} concepts")

    done = [0]

    def actions_for(cid):
        return fetch_actions(cid, args.refresh)

    def cids_for(key):
        done[0] += 1
        if done[0] % 100 == 0:
            print(f"    {done[0]} molecules looked up")
        return fetch_cids(key, args.refresh)

    def records_for(cid):
        return fetch_records(cid, args.refresh)

    # Imported here rather than at the top: that script imports this one.
    import resolve_cohort_mesh_structure as structure
    supp = structure.ensure_supp_file()
    unii_zip = structure.ensure_unii_file()
    print(f"  reading {supp.name} and {unii_zip.name} ...")
    records = load_records(path, supp)
    unii_by_key, unii_member = structure.load_unii(unii_zip)
    unii_key = structure.load_unii_structures(unii_zip)
    extra = {"mesh_supp_sha256": common.sha256(supp), "unii_records": unii_member,
             "unii_archive_sha256": common.sha256(unii_zip),
             "chembl_release": common.CHEMBL_RELEASE}

    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        judge = Judge(records, unii_key, chembl_parent_blocks(chembl))
        idents = identities(conn, chembl, unii_by_key, records)
        conn.execute("BEGIN")
        s = backfill(conn, mesh, sha, cids_for, actions_for, args.limit,
                     records_for, idents, judge, extra)
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
    if s["set_aside"]:
        print("  set aside (molecule, action, from record, why):")
        for parent, action, record, why in s["set_aside"]:
            print(f"    {parent}  {mesh['desc'].get(action, (action,))[0]}  <- {record}  {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
