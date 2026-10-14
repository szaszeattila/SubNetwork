#!/usr/bin/env python3
"""Backfill FDA's pharmacologic classes into db/cohort1.db, via FDA UNII and RxNav.

FDA files a drug's labelling under three kinds of class: its **Established
Pharmacologic Class** (EPC, "Serotonin Reuptake Inhibitor"), its **mechanism of
action** (MoA, "Cytochrome P450 2D6 Inhibitors") and its **physiologic effect**
(PE, "Increased Central Nervous System Serotonin Activity"). NLM's RxClass
serves them, keyed by RxNorm ingredient. They are kept as three sources,
`fda_epc`, `fda_moa` and `fda_pe`, for the same reason the MeSH actions and
structures are two: they answer different questions, and a consumer picks.
A class here is a label for search, display and grading, never evidence about
a target, and never part of the similarity score. Nothing is filtered by
interest: CYP-inhibitor MoAs are stored like any other, because which classes
make a useful answer key is the key's decision and not the backfill's.

The route, an identifier at every step (invariant 15):

  1. molecules.inchikey -> FDA UNII, by exact standard InChIKey in FDA's own
     UNII records file (the same cached archive as
     scripts/resolve_cohort_mesh_structure.py, read with its `load_unii`). The
     InChIKeys are the parent's and those of every form the build folded onto
     it, read exactly as that script reads them.
  2. UNII -> RxCUI, RxNav's `rxcui.json?idtype=UNII_CODE`.
  3. RxCUI -> ingredient. RxNorm files a salt as a precise ingredient (PIN,
     "sertraline hydrochloride") apart from its ingredient (IN, "sertraline").
     An IN is kept; a PIN is followed to its IN and accepted only when that is
     exactly one; any other term type (a brand, a clinical drug) is not used.
  4. A molecule resolves only if every identifier it has reaches **exactly
     one** ingredient. Zero is unresolved; two or more is dropped as ambiguous
     and listed, never resolved to either (invariant 6: a wrong drug is worse
     than a missing one).
  5. ingredient -> classes, RxClass `class/byRxcui.json`. Only rows asserted
     for the ingredient itself (the answer also carries its salts' rows), by a
     `has_epc`, `has_moa` or `has_pe` relation, from `FDASPL` (the labels) or
     `MEDRT` (FDA's reference terminology). DAILYMED repeats FDASPL and is
     ignored; so is every other relation (`ci_moa`, `may_treat`, ...) and every
     other class system (ATC, MeSH, VA). One class asserted by both sources is
     one row whose carriers name both.

It never searches by name. A molecule with no UNII, or a UNII RxNorm does not
know, simply has no FDA class.

Each row's carriers read `UNII:<unii>|...|RxCUI:<ingredient>|FDASPL+MEDRT`:
the UNIIs that reached the ingredient, the ingredient, and the sources that
asserted the class. The classes stay in the database; the page does not show
them (scripts/cohort/export.py's SURFACED_CLASS_SOURCES is unchanged).

A separate backfill, not part of a build: it reads ChEMBL read-only, asks RxNav
(not pinned: its version and the run date go into build_manifest, with the
sha256 of the UNII archive and of every answer cache), and changes only the
three fda_* sources of molecule_classes and class_labels and one build_manifest
key. A rebuild wipes those rows; rerun this after it. Answers are cached as
JSON under db/cache/rxnav/, so a rerun is offline unless --refresh is given. A
failed lookup is counted and never cached as an empty answer.

    python3 scripts/resolve_cohort_fda_classes.py            # ask RxNav, write
    python3 scripts/resolve_cohort_fda_classes.py --dry-run  # report, write nothing
    python3 scripts/resolve_cohort_fda_classes.py --refresh  # ignore the cache
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sqlite3
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import classes as classes_mod
from cohort import common
import resolve_cohort_mesh_structure as mesh_struct
import resolve_cohort_pharm_actions as pharm

SOURCES = ("fda_epc", "fda_moa", "fda_pe")
SOURCE_OF_RELA = {"has_epc": "fda_epc", "has_moa": "fda_moa", "has_pe": "fda_pe"}
CLASS_SOURCES = frozenset({"FDASPL", "MEDRT"})

BASE = "https://rxnav.nlm.nih.gov/REST"
CACHE_DIR = pharm.CACHE / "rxnav"
USER_AGENT = pharm.USER_AGENT
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 4
MIN_INTERVAL = 0.1            # seconds between requests: at most ~10 a second
CACHE_NAMES = ("unii_rxcui", "tty", "to_ingredient", "classes", "meta")

_last_request = [0.0]


class RxNavError(Exception):
    """A lookup that failed, as opposed to one that answered "nothing"."""


def http_get(url, params=None):
    """One throttled, retried GET returning parsed JSON. Raises RxNavError when
    every attempt fails; a 4xx other than 429 is not retried."""
    last = None
    for attempt in range(REQUEST_RETRIES):
        wait = MIN_INTERVAL - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT,
                                headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as err:
            last = err
            status = getattr(getattr(err, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                break
            if attempt < REQUEST_RETRIES - 1:
                time.sleep(2 * (2 ** attempt))
    raise RxNavError(f"{url} {params}: {last}")


class RxNav:
    """The RxNav lookups this script makes, each cached to its own JSON file
    under ``cache_dir``. ``get(url, params)`` is injectable for the tests."""

    def __init__(self, cache_dir=None, refresh=False, get=None):
        self.dir = pathlib.Path(cache_dir or CACHE_DIR)
        self.get = get or http_get
        self.asked = collections.Counter()      # requests actually made, by cache
        self.failed = []
        self.cache = {}
        for name in CACHE_NAMES:
            path = self.path(name)
            self.cache[name] = ({} if refresh or not path.exists()
                                else json.loads(path.read_text()))

    def path(self, name):
        return self.dir / f"{name}.json"

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, data in self.cache.items():
            if data:
                self.path(name).write_text(json.dumps(data, sort_keys=True, indent=0))

    def files(self):
        return {n: self.path(n) for n in CACHE_NAMES if self.path(n).exists()}

    def _ask(self, name, key, url, params, extract):
        """The cached answer for key, else ask. Raises RxNavError on a failure,
        and caches nothing then."""
        if key in self.cache[name]:
            return self.cache[name][key]
        try:
            value = extract(self.get(url, params))
        except RxNavError:
            self.failed.append((name, key))
            raise
        except (KeyError, TypeError, AttributeError) as err:
            self.failed.append((name, key))
            raise RxNavError(f"{url} {params}: unexpected answer ({err!r})") from err
        self.asked[name] += 1
        self.cache[name][key] = value
        return value

    def rxcuis_of_unii(self, unii):
        return self._ask("unii_rxcui", unii, f"{BASE}/rxcui.json",
                         {"idtype": "UNII_CODE", "id": unii},
                         lambda b: sorted(set(b.get("idGroup", {}).get("rxnormId") or [])))

    def tty(self, rxcui):
        return self._ask("tty", rxcui, f"{BASE}/rxcui/{rxcui}/properties.json", None,
                         lambda b: (b.get("properties") or {}).get("tty"))

    def ingredients_of(self, rxcui):
        def extract(b):
            groups = (b.get("relatedGroup") or {}).get("conceptGroup") or []
            return sorted({p["rxcui"] for g in groups if g.get("tty") == "IN"
                           for p in g.get("conceptProperties") or []})
        return self._ask("to_ingredient", rxcui, f"{BASE}/rxcui/{rxcui}/related.json",
                         {"tty": "IN"}, extract)

    def ingredient(self, rxcui):
        """The one ingredient RxCUI an RxCUI stands for, or None."""
        tty = self.tty(rxcui)
        if tty == "IN":
            return rxcui
        if tty == "PIN":
            ins = self.ingredients_of(rxcui)
            return ins[0] if len(ins) == 1 else None
        return None

    def classes(self, ingredient):
        """[[source, classId, className, relaSource], ...] kept for one IN."""
        def extract(b):
            out = set()
            for r in (b.get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo") or []:
                if r["minConcept"]["rxcui"] != ingredient:
                    continue
                source = SOURCE_OF_RELA.get(r.get("rela"))
                if source is None or r.get("relaSource") not in CLASS_SOURCES:
                    continue
                item = r["rxclassMinConceptItem"]
                out.add((source, item["classId"], item["className"], r["relaSource"]))
            return [list(x) for x in sorted(out)]
        return self._ask("classes", ingredient, f"{BASE}/rxclass/class/byRxcui.json",
                         {"rxcui": ingredient}, extract)

    def version(self, refresh=False):
        """RxNav's version, asked once and kept with the date it was asked."""
        meta = self.cache["meta"]
        if "version" not in meta or refresh:
            try:
                body = self.get(f"{BASE}/version.json", None)
            except RxNavError:
                self.failed.append(("meta", "version"))
                raise
            meta["version"] = {"version": body.get("version"),
                               "apiVersion": body.get("apiVersion"),
                               "asked": datetime.date.today().isoformat()}
        return meta["version"]


# --------------------------------------------------------------- resolve

def resolve(molecules, unii_by_key, rx):
    """Decide each molecule's FDA classes. molecules is mesh_struct's
    [(parent_molregno, [(chembl_id, inchikey), ...])], parent first.

    The parent's own structure decides: its UNIIs must reach exactly one
    ingredient. The forms folded onto it are read only where the parent's
    reach none, and must then agree on exactly one between them. A form that
    RxNorm files as an ingredient of its own is a different product, not a
    doubt about the parent: aminophylline is folded onto theophylline in
    ChEMBL and is its own ingredient in RxNorm, and reading both together
    dropped theophylline as ambiguous.

    Returns (rows, label_rows, counts, detail); detail has "ambiguous"
    {parent: {ingredient: [uniis]}}, "failed" [parent], "ingredient"
    {parent: rxcui} and "kinds" {parent: set of fda_* sources it has a row in}.
    """
    counts = collections.Counter()
    ambiguous, failed, ingredient_of, kinds_of = {}, [], {}, {}
    merged = {}                     # (parent, source, code) -> [name, uniis, rxcui, relaSources]

    def uniis_of(structures):
        return sorted({u for _, k in structures if k for u in unii_by_key.get(k, ())})

    def reach(uniis):
        reached = collections.defaultdict(set)
        for unii in uniis:
            for rxcui in rx.rxcuis_of_unii(unii):
                ing = rx.ingredient(rxcui)
                if ing:
                    reached[ing].add(unii)
        return reached

    for parent, structures in molecules:
        own, forms = uniis_of(structures[:1]), uniis_of(structures[1:])
        if not own and not forms:
            counts["no_unii"] += 1
            continue
        counts["has_unii"] += 1
        try:
            reached, route = reach(own), "by_parent"
            if not reached:
                reached, route = reach([u for u in forms if u not in own]), "by_form"
            if not reached:
                counts["no_ingredient"] += 1
                continue
            if len(reached) > 1:
                counts["ambiguous_several_ingredients"] += 1
                ambiguous[parent] = {i: sorted(u) for i, u in sorted(reached.items())}
                continue
            counts[route] += 1           # of the molecules that resolve
            ing, via = next(iter(reached.items()))
            # A form that reaches the same ingredient is named among the
            # carriers; one that reaches another is not, and changes nothing.
            if own and forms:
                via = set(via) | reach([u for u in forms if u not in own]).get(ing, set())
            found = rx.classes(ing)
        except RxNavError:
            counts["lookup_failed"] += 1
            failed.append(parent)
            continue
        counts["one_ingredient"] += 1
        ingredient_of[parent] = ing
        kinds = set()
        for source, code, name, rela_source in found:
            rec = merged.setdefault((parent, source, code), [name, sorted(via), ing, set()])
            rec[3].add(rela_source)
            kinds.add(source)
        kinds_of[parent] = kinds
        for s in sorted(kinds):
            counts[f"with_{s}"] += 1
        if not kinds:
            counts["no_fda_class"] += 1

    rows, labels = [], {}
    for (parent, source, code), (name, uniis, ing, srcs) in sorted(merged.items()):
        carriers = "|".join([f"UNII:{u}" for u in uniis] + [f"RxCUI:{ing}", "+".join(sorted(srcs))])
        rows.append((parent, source, code, "", name, carriers))
        labels.setdefault((source, code), name)
    label_rows = [(s, c, None, n, None) for (s, c), n in sorted(labels.items())]
    detail = {"ambiguous": ambiguous, "failed": failed, "ingredient": ingredient_of,
              "kinds": kinds_of}
    return rows, label_rows, counts, detail


def backfill(conn, molecules, unii_by_key, rx, manifest, resolved=None):
    """Write the result. ``resolved`` is resolve()'s answer when the caller has
    already computed it (main does, so the database is not held open across the
    network); otherwise it is computed here."""
    classes_mod.ensure_tables(conn)
    try:
        rows, labels, counts, detail = resolved or resolve(molecules, unii_by_key, rx)
    finally:
        rx.save()
    marks = ",".join("?" * len(SOURCES))
    before = {tuple(r) for r in conn.execute(
        f"SELECT * FROM molecule_classes WHERE source IN ({marks})", SOURCES)}
    classes_mod.write(conn, rows, labels, sources=SOURCES)
    after = {tuple(r) for r in conn.execute(
        f"SELECT * FROM molecule_classes WHERE source IN ({marks})", SOURCES)}
    names = {p: c for p, c in conn.execute("SELECT parent_molregno, chembl_id FROM molecules")}
    summary = dict(manifest)
    summary.update({
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rxnav_version": rx.cache["meta"].get("version"),
        "rxnav_cache_sha256": {n: common.sha256(p) for n, p in rx.files().items()},
        "rxnav_requests": dict(rx.asked),
        "molecules": len(molecules), "rows": len(rows), "labels": len(labels),
        "rows_by_source": dict(collections.Counter(r[1] for r in rows)),
        "classes_by_source": dict(collections.Counter(s for s, _ in {(r[1], r[2]) for r in rows})),
        "rows_changed": len(before ^ after), "counts": dict(counts),
        "dropped_ambiguous": {names.get(p, str(p)): v for p, v in sorted(detail["ambiguous"].items())},
        "lookups_failed": sorted(names.get(p, str(p)) for p in detail["failed"]),
    })
    conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                 ("fda_pharmacologic_classes", json.dumps(summary, sort_keys=True)))
    return summary, rows, detail, names


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="report, write nothing to the database (the HTTP cache may fill)")
    parser.add_argument("--refresh", action="store_true",
                        help="ask RxNav again instead of reading the cache")
    parser.add_argument("--refresh-unii", action="store_true",
                        help="re-download FDA's UNII archive instead of reading the cached copy")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    unii_zip = mesh_struct.ensure_unii_file(refresh=args.refresh_unii)
    print(f"  reading {unii_zip.name} ...")
    unii_by_key, unii_member = mesh_struct.load_unii(unii_zip)

    rx = RxNav(refresh=args.refresh)
    try:
        rx.version(refresh=args.refresh)
    except RxNavError as err:
        raise SystemExit(f"cannot reach RxNav: {err}")
    # Read what is needed and let go of the database before any network call:
    # the lookups take minutes, and a held connection blocks other backfills.
    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        molecules = mesh_struct.structures_for(conn, chembl)
    finally:
        conn.close()
        chembl.close()
    print(f"  asking RxNav about {len(molecules)} molecules (cached answers are reused) ...")
    manifest = {"run_date": datetime.date.today().isoformat(),
                "unii_records": unii_member,
                "unii_archive_sha256": common.sha256(unii_zip),
                "chembl_release": common.CHEMBL_RELEASE,
                "relas": sorted(SOURCE_OF_RELA), "rela_sources": sorted(CLASS_SOURCES)}
    try:
        resolved = resolve(molecules, unii_by_key, rx)
    finally:
        rx.save()
    # Reopened only to write, in one short transaction.
    conn = sqlite3.connect(args.db, isolation_level=None, timeout=300)
    try:
        conn.execute("BEGIN IMMEDIATE")
        s, rows, detail, names = backfill(conn, molecules, unii_by_key, rx, manifest, resolved)
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()

    c = s["counts"]
    print(f"{len(detail['ingredient'])} of {s['molecules']} molecules reach one RxNorm "
          f"ingredient; {s['rows']} rows {s['rows_by_source']}, {s['labels']} classes; "
          f"{s['rows_changed']} rows changed"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in sorted(c.items()):
        print(f"  {n:5d}  {k}")
    if detail["ambiguous"]:
        print(f"dropped as ambiguous ({len(detail['ambiguous'])}):")
        for p, v in sorted(detail["ambiguous"].items()):
            print(f"  {names.get(p, p)}: " + "; ".join(
                f"RxCUI {i} via {','.join(u)}" for i, u in v.items()))
    if detail["failed"]:
        print(f"{len(detail['failed'])} molecules had a failed lookup (not cached, not "
              f"written): " + ", ".join(names.get(p, str(p)) for p in detail["failed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
