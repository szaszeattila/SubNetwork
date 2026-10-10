#!/usr/bin/env python3
"""Backfill Wikipedia links for molecules, targets and structure classes in db/cohort1.db.

The cohort pipeline (build_cohort.py) reads ChEMBL 37 and nothing else, so
these two columns exist in db/schema_cohort.sql but are never filled - every
row is NULL. This is a standalone backfill of that one derived fact, not a
rebuild: it never touches a molecule, target, claim or observation row, and
it never opens the ChEMBL release.

Ported from scripts/build_db.py's resolve_wikipedia_urls (see that file,
~line 1700, and docs/DATA-QUALITY-LOG.md's 2026-08-29 entry) rather than
reimplemented, because the rule that makes this safe was decided there and
should not be re-derived: every lookup is an exact match on an identifier
this database already holds, through Wikidata, and an item that resolves to
more than one English article is skipped rather than guessed at (CLAUDE.md
invariant 15, applying invariant 6 - "refuse to guess" - to links instead of
genes). A title search on `pref_name` would be shorter to write and wrong:
"ATM", "APP" and "TNF" are English words, and this database now also holds
protein *families* and *complexes* whose names are even more likely to
collide with something unrelated.

Molecules match on InChIKey (P235) and ChEMBL ID (P592) - both tried,
because they disagree about coverage: 1,121 of 1,331 molecules here carry an
InChIKey and all 1,331 carry a ChEMBL ID, and (per the legacy build) a
Wikidata item's own ChEMBL ID can name a different form of the same parent
than the one this database stores. There is no PubChem CID column in the
cohort schema (db/schema_cohort.sql), unlike the legacy one, so P662 is not
tried here.

Targets match on UniProt accession (P352), then Wikidata's "encoded by"
(P702) hop to the gene item - both are needed, because English Wikipedia's
article sits on the protein item for some targets and the gene item for
others, with no rule saying which.

Multi-component targets (target_components has more than one row for a
target - 310 of 2,577 in the build this was written against, not quite the
"309" the docs quote because three targets ChEMBL itself files under SINGLE
PROTEIN turn out to carry zero or several accessions; see the test suite)
are deliberately left NULL. build_db.py tried twice to derive a link for its
seven legacy protein assemblies from their members' accessions - walking
P527/P361 outward, then requiring unanimity across every member - and both
attempts produced confident wrong answers (5-HT3 to "Cys-loop receptor",
the 7-member NMDA group to "Ionotropic glutamate receptor") rather than no
answer, which is worse than the NULL this script leaves. Its fallback for
those seven was a hand-written ChEMBL-id-to-Wikidata-item map
(COMPLEX_WIKIDATA_ITEMS); that map covers seven specific legacy assemblies
and does not generalise to the 310 here, so it is deliberately not ported.
Building a review process for 310 hand-picked identities is future work, not
a backfill.

MeSH structure classes match on their descriptor UI (P486) and, where that
item has no English article, on the main article its English category
declares - see the comment above resolve_classes. They need the class
backfills to have run first, so this script runs after
resolve_cohort_mesh_structure.py.

Usage:
    python3 scripts/resolve_cohort_wikipedia.py             # resolve, write
    python3 scripts/resolve_cohort_wikipedia.py --dry-run   # query, report only
    python3 scripts/resolve_cohort_wikipedia.py --refresh   # re-check resolved rows too
    python3 scripts/resolve_cohort_wikipedia.py --limit 50  # smoke test

Idempotent and restartable: with no flags it only queries rows that are
still NULL, so an interrupted run can simply be rerun. It never clears a
previously-resolved link on its own - a chunk that fails, an item that has
since become ambiguous, or a target with no article now all leave the
existing value untouched, matching apply_articles in build_db.py. The only
way a resolved link changes is --refresh finding a *different* unambiguous
article for it.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sqlite3
import sys
import time
import urllib.parse

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Wikidata asks for a descriptive User-Agent on its SPARQL endpoint and
# throttles requests that arrive without one (same requirement build_db.py
# documents for the legacy pipeline).
WIKIDATA_USER_AGENT = (
    "SubNetwork/1.0 (cohort-1 drug-target interaction map; "
    "https://github.com/; contact via repository)"
)

REQUEST_TIMEOUT = 60
REQUEST_RETRIES = 6
MAX_RETRY_DELAY = 30  # backoff caps at 3, 6, 12, 24, 30, 30s

# Politeness floor between requests to the same endpoint.
MIN_REQUEST_INTERVAL = 0.2
_last_request_at = 0.0

# The endpoint 504s on a large VALUES block and answers ~15 rows at a time in
# about a second - empirically established in build_db.py against the same
# endpoint. Kept identical here rather than re-measured.
WIKIDATA_CHUNK = 15

WIKIDATA_MOLECULE_QUERY = """
SELECT ?key ?article WHERE {
  VALUES (?key ?prop ?value) { %s }
  ?item ?prop ?value .
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
}"""

WIKIDATA_TARGET_QUERY = """
SELECT ?key ?article WHERE {
  VALUES (?key ?accession) { %s }
  ?protein wdt:P352 ?accession .
  { ?article schema:about ?protein }
  UNION
  { ?protein wdt:P702 ?gene . ?article schema:about ?gene }
  ?article schema:isPartOf <https://en.wikipedia.org/> .
}"""


class WikidataError(RuntimeError):
    """A SPARQL request failed after retries. Always fatal to the chunk that
    raised it - never swallowed into "no article exists"."""


def _throttle():
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _wikidata_get(query):
    """One retried HTTP GET against the Wikidata SPARQL endpoint. Raises
    WikidataError if every attempt fails - the caller must not treat that the
    same as a query that succeeded and returned no rows."""
    last_err = None
    for attempt in range(REQUEST_RETRIES):
        try:
            _throttle()
            resp = requests.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            last_err = err
            status = getattr(getattr(err, "response", None), "status_code", None)
            # A 4xx (other than 429) is a malformed query, not a hiccup -
            # retrying it won't help and every chunk uses the same template.
            if status is not None and 400 <= status < 500 and status != 429:
                raise WikidataError(f"Wikidata rejected the query: {err}") from err
            if attempt < REQUEST_RETRIES - 1:
                delay = min(3 * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"    Wikidata request failed ({type(err).__name__}), "
                      f"retrying in {delay}s...")
                time.sleep(delay)
    raise WikidataError(
        f"Wikidata request failed after {REQUEST_RETRIES} attempts: {last_err}"
    ) from last_err


def sparql_literal(value):
    """A SPARQL string literal. Every value passed here is an identifier this
    database already validated, but quoting is not the place to rely on
    that."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _chunk(rows, size):
    """rows: list of (key, rendered-VALUES-tuple). Yields (keys-in-chunk,
    values-in-chunk) so a failed chunk's keys can be attributed precisely."""
    for start in range(0, len(rows), size):
        batch = rows[start:start + size]
        yield {k for k, _ in batch}, [v for _, v in batch]


def sparql_articles(query_template, rows):
    """Run one SPARQL query per chunk of `rows` and return (found,
    failed_keys). `found` maps key -> set of article URLs. `failed_keys` is
    every key touched by a chunk that failed and never resolved via another
    chunk - the same key can appear in two chunks (a molecule tried on both
    InChIKey and ChEMBL ID), so failure is only real once nothing on that
    key succeeded anywhere."""
    found: dict[str, set] = {}
    failed_keys: set = set()
    chunks = list(_chunk(rows, WIKIDATA_CHUNK))
    for keys_in_chunk, values in chunks:
        query = query_template % " ".join(values)
        try:
            data = _wikidata_get(query)
        except WikidataError as err:
            print(f"    Wikidata lookup failed for {len(keys_in_chunk)} "
                  f"key(s): {err}")
            failed_keys.update(keys_in_chunk)
            continue
        for binding in data["results"]["bindings"]:
            found.setdefault(binding["key"]["value"], set()).add(
                binding["article"]["value"])
    failed_keys -= set(found)
    return found, failed_keys


def apply_results(conn, table, key_column, keys, found, failed, dry_run):
    """Write resolved URLs, skipping anything ambiguous. Never writes NULL:
    a key with no result (network failure or no article) leaves whatever was
    already stored untouched, exactly as build_db.py's apply_articles does -
    losing a Wikidata request should not blank an existing link."""
    resolved = ambiguous = no_article = 0
    for key in keys:
        if key in failed:
            continue
        articles = found.get(key)
        if not articles:
            no_article += 1
            continue
        if len(articles) > 1:
            ambiguous += 1
            print(f"    {key}: {len(articles)} English articles on Wikidata, "
                  "skipping rather than picking one")
            continue
        resolved += 1
        if not dry_run:
            conn.execute(
                f"UPDATE {table} SET wikipedia_url = ? WHERE {key_column} = ?",
                (next(iter(articles)), key),
            )
    return resolved, ambiguous, no_article


def resolve_molecules(conn, dry_run=False, refresh=False, limit=None):
    where = "" if refresh else "WHERE wikipedia_url IS NULL"
    sql = f"SELECT chembl_id, inchikey FROM molecules {where} ORDER BY chembl_id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    candidates = list(conn.execute(sql))
    total = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]

    rows = []
    for chembl_id, inchikey in candidates:
        if inchikey:
            rows.append((chembl_id,
                         f"({sparql_literal(chembl_id)} wdt:P235 {sparql_literal(inchikey)})"))
        rows.append((chembl_id,
                     f"({sparql_literal(chembl_id)} wdt:P592 {sparql_literal(chembl_id)})"))

    found, failed = sparql_articles(WIKIDATA_MOLECULE_QUERY, rows)
    keys = [c[0] for c in candidates]
    resolved, ambiguous, no_article = apply_results(
        conn, "molecules", "chembl_id", keys, found, failed, dry_run)
    print(f"  molecules: {resolved}/{len(keys)} queried linked to Wikipedia"
          f" ({total} total, {len(keys)} queried)"
          + (f", {ambiguous} skipped as ambiguous" if ambiguous else "")
          + (f", {len(failed)} failed" if failed else "")
          + f", {no_article} with no article")
    return {
        "total": total, "queried": len(keys), "resolved": resolved,
        "ambiguous": ambiguous, "no_article": no_article, "failed": len(failed),
    }


def resolve_targets(conn, dry_run=False, refresh=False, limit=None):
    total = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]

    # Eligible: exactly one target_components row, regardless of what
    # targets.target_type claims (see the module docstring - three SINGLE
    # PROTEIN targets in the build this was written against actually carry
    # zero or several accessions, so the type label is not trusted here).
    eligible_ids = {row[0] for row in conn.execute(
        "SELECT target_chembl_id FROM target_components"
        " GROUP BY target_chembl_id HAVING COUNT(*) = 1")}
    accession_by_target = dict(conn.execute(
        "SELECT target_chembl_id, MIN(accession) FROM target_components"
        " GROUP BY target_chembl_id"))
    no_accession = conn.execute(
        "SELECT COUNT(*) FROM targets t WHERE NOT EXISTS ("
        "SELECT 1 FROM target_components tc WHERE tc.target_chembl_id = t.chembl_id)"
    ).fetchone()[0]
    multi_component = total - len(eligible_ids) - no_accession

    where = "chembl_id IN ({})".format(",".join("?" * len(eligible_ids))) if eligible_ids else "0"
    params = list(eligible_ids)
    if not refresh:
        where += " AND wikipedia_url IS NULL"
    sql = f"SELECT chembl_id FROM targets WHERE {where} ORDER BY chembl_id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    candidates = [row[0] for row in conn.execute(sql, params)] if eligible_ids else []

    rows = [(chembl_id,
             f"({sparql_literal(chembl_id)} {sparql_literal(accession_by_target[chembl_id])})")
            for chembl_id in candidates]

    found, failed = sparql_articles(WIKIDATA_TARGET_QUERY, rows)
    resolved, ambiguous, no_article = apply_results(
        conn, "targets", "chembl_id", candidates, found, failed, dry_run)
    print(f"  targets: {resolved}/{len(candidates)} queried linked to Wikipedia"
          f" ({total} total, {len(eligible_ids)} single-component eligible,"
          f" {multi_component} multi-component skipped,"
          f" {no_accession} with no accession skipped, {len(candidates)} queried)"
          + (f", {ambiguous} skipped as ambiguous" if ambiguous else "")
          + (f", {len(failed)} failed" if failed else "")
          + f", {no_article} with no article")
    return {
        "total": total, "eligible": len(eligible_ids),
        "multi_component": multi_component, "no_accession": no_accession,
        "queried": len(candidates), "resolved": resolved, "ambiguous": ambiguous,
        "no_article": no_article, "failed": len(failed),
    }


def _wikipedia_get(params):
    """One retried GET against English Wikipedia's API, under the same rules
    as _wikidata_get: a failure raises, and is never read as "no article"."""
    last_err = None
    for attempt in range(REQUEST_RETRIES):
        try:
            _throttle()
            resp = requests.get(
                WIKIPEDIA_API,
                params=dict(params, format="json", formatversion=2),
                headers={"User-Agent": WIKIDATA_USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            last_err = err
            status = getattr(getattr(err, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise WikidataError(f"Wikipedia rejected the request: {err}") from err
            if attempt < REQUEST_RETRIES - 1:
                delay = min(3 * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"    Wikipedia request failed ({type(err).__name__}), "
                      f"retrying in {delay}s...")
                time.sleep(delay)
    raise WikidataError(
        f"Wikipedia request failed after {REQUEST_RETRIES} attempts: {last_err}"
    ) from last_err


# --------------------------------------------------------------- classes
#
# A MeSH structure class ("Xanthines", D014970) is matched on its descriptor
# UI, which Wikidata records as P486 - an identifier this database already
# holds, so invariant 15 is kept. 415 of the 726 classes in the build this was
# written against reach exactly one English article that way. Another 310
# reach an item with no English article of its own, Xanthines among them:
# English Wikipedia writes about the class in the article on its parent
# compound ("Xanthine" has the derivatives) and Wikidata keeps the class and
# the compound as two items, and says outright they are different.
#
# No identifier joins those two items - not P279 (Xanthines is a subclass of
# "purine alkaloid", which has no article either), not P138 (it reaches one
# class), and MeSH's own record names no parent compound. What does join them
# is a link English Wikipedia's editors wrote: the category Wikidata names as
# the item's main category (P910) declares its main article with {{Cat main}}
# - Category:Xanthines names Xanthine, Category:Phenothiazines names
# Phenothiazine. That is a link followed, not a title searched for, and it is
# read only where the item has no article of its own. It is refused unless the
# category carries exactly one such template naming exactly one article, and
# the article exists and is not a disambiguation page.
#
# Only structure classes. The same route was measured on the 164 MeSH
# pharmacological actions with no article: 14 have a category, and its main
# article is a topic rather than the class (Alkylating Agents -> "Alkylation",
# Teratogens -> "Teratology"). USAN stems have no identifier at all.

CLASS_SOURCES = ("mesh_struct",)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE = "https://en.wikipedia.org/wiki/"

# The Wikipedia API answers up to 50 titles per query. The class query is a
# plain lookup on one property, and answered 100 descriptors at a time without
# trouble when this was written; 60 leaves room.
WIKIPEDIA_CHUNK = 50
WIKIDATA_CLASS_CHUNK = 60

WIKIDATA_CLASS_QUERY = """
SELECT ?key ?item ?article ?category WHERE {
  VALUES (?key ?mesh) { %s }
  ?item wdt:P486 ?mesh .
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }
  OPTIONAL { ?item wdt:P910 ?cat .
             ?catpage schema:about ?cat ; schema:isPartOf <https://en.wikipedia.org/> ;
                      schema:name ?category . }
}"""

# {{Cat main}} and the names English Wikipedia redirects to it, and {{Main}},
# which categories also use for the same statement. {{Cat more}} and
# {{See also}} point somewhere further, not at the article on the class.
MAIN_ARTICLE_TEMPLATE = re.compile(
    r"\{\{\s*(?:cat(?:egory)?[ _]?main(?:[ _]article)?|main(?:[ _]article)?)\s*"
    r"((?:\|[^{}]*)?)\}\}", re.I)


def main_article(wikitext):
    """The one article a category's wikitext declares as its main article, or
    (None, reason). A template naming several, two templates, or one naming
    none (which defaults to the category's own title - a name, not a link) is
    refused rather than resolved."""
    found = MAIN_ARTICLE_TEMPLATE.findall(wikitext or "")
    if not found:
        return None, "no main article"
    if len(found) > 1:
        return None, "several main-article templates"
    names = [a.strip() for a in found[0].split("|")[1:]]
    names = [a for a in names if a and "=" not in a]
    if len(names) != 1:
        return None, "names no article" if not names else "names several articles"
    return names[0], None


def article_url(title, fragment=""):
    """The article URL for a Wikipedia title, as Wikidata's sitelinks write
    them: spaces as underscores, everything else percent-encoded."""
    def enc(s):
        return urllib.parse.quote(s.replace(" ", "_"), safe="()',!*:/-._~")
    url = WIKIPEDIA_ARTICLE + enc(title)
    return url + "#" + enc(fragment) if fragment else url


def _category_texts(titles):
    """title -> wikitext for each English category page that exists."""
    out = {}
    titles = sorted(titles)
    for start in range(0, len(titles), WIKIPEDIA_CHUNK):
        data = _wikipedia_get({
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "titles": "|".join(titles[start:start + WIKIPEDIA_CHUNK])})
        query = data.get("query", {})
        back = {n["to"]: n["from"] for n in query.get("normalized", [])}
        for page in query.get("pages", []):
            if page.get("missing") or not page.get("revisions"):
                continue
            title = back.get(page["title"], page["title"])
            out[title] = page["revisions"][0]["slots"]["main"]["content"]
    return out


def _articles(titles):
    """title -> (resolved title, fragment) for each title naming an existing,
    non-disambiguation article, following redirects (a redirect to a section
    keeps its section)."""
    out = {}
    titles = sorted(titles)
    for start in range(0, len(titles), WIKIPEDIA_CHUNK):
        data = _wikipedia_get({
            "action": "query", "redirects": 1, "prop": "pageprops",
            "ppprop": "disambiguation",
            "titles": "|".join(titles[start:start + WIKIPEDIA_CHUNK])})
        query = data.get("query", {})
        norm = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redir = {r["from"]: (r["to"], r.get("tofragment", ""))
                 for r in query.get("redirects", [])}
        pages = {p["title"]: p for p in query.get("pages", [])}
        for asked in titles[start:start + WIKIPEDIA_CHUNK]:
            title, fragment = norm.get(asked, asked), ""
            if title in redir:
                title, fragment = redir[title]
            page = pages.get(title)
            if (not page or page.get("missing") or page.get("invalid")
                    or "disambiguation" in page.get("pageprops", {})):
                continue
            out[asked] = (title, fragment)
    return out


def resolve_classes(conn, dry_run=False, refresh=False, limit=None):
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "class_labels" not in have:
        print("  classes: no class_labels table - run the class backfills first")
        return {"total": 0, "queried": 0, "resolved": 0, "by_item": 0, "by_category": 0,
                "ambiguous": 0, "refused": 0, "no_article": 0, "failed": 0}
    if "class_wikipedia" not in have and not dry_run:
        ensure_class_table(conn)
    marks = ",".join("?" * len(CLASS_SOURCES))
    total = conn.execute(f"SELECT COUNT(*) FROM class_labels WHERE source IN ({marks})",
                         CLASS_SOURCES).fetchone()[0]
    sql = f"SELECT source, code FROM class_labels l WHERE source IN ({marks})"
    if not refresh and "class_wikipedia" in have:
        sql += (" AND NOT EXISTS (SELECT 1 FROM class_wikipedia w"
                " WHERE w.source = l.source AND w.code = l.code)")
    sql += " ORDER BY source, code"
    if limit:
        sql += f" LIMIT {int(limit)}"
    candidates = list(conn.execute(sql, CLASS_SOURCES))
    key_of = {f"{s}:{c}": (s, c) for s, c in candidates}

    # A descriptor UI is the whole key: every source here is MeSH.
    rows = [(k, f"({sparql_literal(k)} {sparql_literal(c)})") for k, (s, c) in key_of.items()]
    items, articles, categories, failed = {}, {}, {}, set()
    for keys_in_chunk, values in _chunk(rows, WIKIDATA_CLASS_CHUNK):
        try:
            data = _wikidata_get(WIKIDATA_CLASS_QUERY % " ".join(values))
        except WikidataError as err:
            print(f"    Wikidata lookup failed for {len(keys_in_chunk)} class(es): {err}")
            failed.update(keys_in_chunk)
            continue
        for b in data["results"]["bindings"]:
            k = b["key"]["value"]
            items.setdefault(k, set()).add(b["item"]["value"].rsplit("/", 1)[-1])
            if "article" in b:
                articles.setdefault(k, set()).add(b["article"]["value"])
            if "category" in b:
                categories.setdefault(k, set()).add(b["category"]["value"])

    # The category route, for an item with no article of its own.
    via_category = {}
    for k in key_of:
        if k in failed or len(items.get(k, ())) != 1 or articles.get(k):
            continue
        if len(categories.get(k, ())) == 1:
            via_category[k] = next(iter(categories[k]))
    named, refused = {}, collections.Counter()
    try:
        texts = _category_texts(set(via_category.values()))
        for k, cat in via_category.items():
            title, why = main_article(texts.get(cat))
            if title:
                named[k] = title
            else:
                refused[why] += 1
        page_of = _articles({t.split("#", 1)[0].strip() for t in named.values()})
    except WikidataError as err:
        print(f"    Wikipedia lookup failed for {len(via_category)} class(es): {err}")
        failed.update(via_category)
        named, page_of = {}, {}

    resolved, ambiguous, no_article = [], 0, 0
    for k, (source, code) in key_of.items():
        if k in failed:
            continue
        found = items.get(k, set())
        if len(found) > 1:
            ambiguous += 1
            print(f"    {code}: {len(found)} Wikidata items carry this descriptor, "
                  "skipping rather than picking one")
            continue
        if not found:
            no_article += 1
            continue
        item = next(iter(found))
        own = articles.get(k, set())
        if len(own) > 1 or (not own and len(categories.get(k, ())) > 1):
            ambiguous += 1
            continue
        if len(own) == 1:
            resolved.append((source, code, item, "item", None, next(iter(own))))
        elif k in named:
            title, _, fragment = named[k].partition("#")
            page = page_of.get(title.strip())
            if not page:
                refused["main article missing or a disambiguation page"] += 1
                continue
            resolved.append((source, code, item, "category", via_category[k],
                             article_url(page[0], fragment.strip() or page[1])))
        elif k not in via_category:
            no_article += 1

    if not dry_run:
        conn.executemany(
            "INSERT OR REPLACE INTO class_wikipedia(source, code, wikidata_item, route,"
            " category, wikipedia_url) VALUES (?,?,?,?,?,?)", resolved)
    by_item = sum(1 for r in resolved if r[3] == "item")
    n_refused = sum(refused.values())
    print(f"  classes: {len(resolved)}/{len(key_of)} queried linked to Wikipedia"
          f" ({by_item} by their own item, {len(resolved) - by_item} by their"
          f" category's main article; {total} structure classes)"
          + (f", {ambiguous} skipped as ambiguous" if ambiguous else "")
          + (f", {n_refused} category routes refused ({dict(refused)})" if n_refused else "")
          + (f", {len(failed)} failed" if failed else "")
          + f", {no_article} with no article")
    return {"total": total, "queried": len(key_of), "resolved": len(resolved),
            "by_item": by_item, "by_category": len(resolved) - by_item,
            "ambiguous": ambiguous, "refused": n_refused,
            "no_article": no_article, "failed": len(failed)}


def ensure_class_table(conn):
    """Create class_wikipedia in a database built before it, from the
    statement in db/schema_cohort.sql, so the two cannot differ in shape."""
    schema = (common.DB / "schema_cohort.sql").read_text()
    m = re.search(r"CREATE TABLE IF NOT EXISTS class_wikipedia \(.*?\n\);", schema, re.S)
    if not m:
        raise SystemExit("class_wikipedia is missing from db/schema_cohort.sql")
    conn.execute(m.group(0))


def resolve(conn, dry_run=False, refresh=False, limit=None):
    """Fill molecules.wikipedia_url, targets.wikipedia_url and class_wikipedia
    on an already-open connection to db/cohort1.db (or a database shaped like
    it). Never opens the ChEMBL release, never touches any other table, and
    commits nothing itself - the caller controls the transaction (main() below
    commits once at the end; a dry run never writes at all, by construction of
    apply_results and resolve_classes)."""
    print("Resolving Wikipedia links via Wikidata...")
    summary = {
        "molecules": resolve_molecules(conn, dry_run, refresh, limit),
        "targets": resolve_targets(conn, dry_run, refresh, limit),
        "classes": resolve_classes(conn, dry_run, refresh, limit),
    }
    return summary


def print_summary(summary):
    m, t = summary["molecules"], summary["targets"]
    print("\nSummary")
    print("-------")
    print(f"molecules: {m['resolved']} resolved, {m['no_article']} no article, "
          f"{m['ambiguous']} ambiguous (dropped), {m['failed']} failed "
          f"(of {m['queried']} queried, {m['total']} total)")
    print(f"targets:   {t['resolved']} resolved, {t['no_article']} no article, "
          f"{t['ambiguous']} ambiguous (dropped), {t['failed']} failed, "
          f"{t['multi_component']} skipped as multi-component, "
          f"{t['no_accession']} skipped with no accession "
          f"(of {t['queried']} queried, {t['eligible']} eligible, {t['total']} total)")
    c = summary["classes"]
    print(f"classes:   {c['resolved']} resolved ({c['by_item']} by their own item, "
          f"{c['by_category']} by their category's main article), "
          f"{c['no_article']} no article, {c['ambiguous']} ambiguous (dropped), "
          f"{c['refused']} category routes refused, {c['failed']} failed "
          f"(of {c['queried']} queried, {c['total']} structure classes)")
    failures = m["failed"] + t["failed"] + c["failed"]
    if failures:
        print(f"\n{failures} key(s) failed after retries - rerun to retry them "
              "(unresolved rows are unchanged, not cleared).")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="query and report, write nothing")
    parser.add_argument("--refresh", action="store_true",
                        help="re-resolve rows that already have a wikipedia_url")
    parser.add_argument("--limit", type=int, default=None,
                        help="only consider the first N molecules and N targets"
                             " (for testing)")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB,
                        help="path to the cohort database (default: db/cohort1.db)")
    args = parser.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    conn = sqlite3.connect(args.db)
    try:
        summary = resolve(conn, dry_run=args.dry_run, refresh=args.refresh,
                          limit=args.limit)
        if args.dry_run:
            conn.rollback()
            print("\n(dry run - nothing written)")
        else:
            conn.commit()
    finally:
        conn.close()

    failures = print_summary(summary)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
