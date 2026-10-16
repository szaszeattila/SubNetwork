#!/usr/bin/env python3
"""Retrieve the Wikipedia categories and Wikidata roles compare_lists.py sets
beside the wiki, into RAW, for prepare_lists.py to turn into name files.

Added 2026-10-15, when D24 listed the wiki's psychedelics section: the
nootropic category and role alone say nothing about a psychedelic. Each list
is written as RAW/<list>.json, [{"title", "qid", "inchikeys"}], where a
Wikipedia article carries its Wikidata item's InChIKeys (P235), so that
compare_lists.py places it by structure before it tries the name.

  wikipedia_nootropics    the pages of Category:Nootropics, no subcategories
                          (the 2026-10-11 rule, refreshed)
  wikipedia_psychoactive  the pages of Category:Psychedelic drugs and every
                          subcategory below it, with Category:Entactogens,
                          Dissociative drugs, Deliriants and Cathinones
  wikipedia_designer      Category:Designer drugs and its subcategories
  wikidata_nootropic      items whose P2868 (subject has role) or P366 (has use)
                          is nootropic (Q742487); the 2026-10-11 rule, refreshed
  wikidata_psychoactive   the same for psychedelic drug (Q2314176), hallucinogen
                          (Q194270), empathogen-entactogen (Q903338),
                          dissociative (Q900394, Q50429828) and stimulant (Q211036)

Read-only towards everything here; the lists are other sites' content and stay
out of the repository with RAW.

    python3 analysis/wiki_comparison/fetch_lists.py RAW
"""
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

UA = "SubNetwork/1.0 (https://subnetwork.dev; drug-target interaction map; analysis/wiki_comparison)"
WP = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"

CATEGORY_LISTS = {
    "wikipedia_nootropics": [("Nootropics", False)],
    "wikipedia_psychoactive": [("Psychedelic drugs", True), ("Entactogens", True), ("Dissociative drugs", True),
                               ("Deliriants", True), ("Cathinones", True)],
    "wikipedia_designer": [("Designer drugs", True)],
}
ROLE_LISTS = {
    "wikidata_nootropic": ["Q742487"],
    "wikidata_psychoactive": ["Q2314176", "Q194270", "Q903338", "Q900394", "Q50429828", "Q211036"],
}


def get(url: str, **params) -> dict:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def members(cat: str, kind: str) -> list[str]:
    out, cont = [], {}
    while True:
        d = get(WP, action="query", list="categorymembers", cmtitle="Category:" + cat, cmtype=kind,
                cmlimit=500, format="json", **cont)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            return out
        cont = {"cmcontinue": d["continue"]["cmcontinue"]}


def pages_under(roots) -> list[str]:
    pages, seen = [], set()
    todo = [(c, deep) for c, deep in roots]
    while todo:
        cat, deep = todo.pop()
        if cat in seen:
            continue
        seen.add(cat)
        pages += members(cat, "page")
        if deep:
            todo += [(s.removeprefix("Category:"), True) for s in members(cat, "subcat")]
    return list(dict.fromkeys(pages))


def items_of(titles: list[str]) -> dict[str, str]:
    qid = {}
    for i in range(0, len(titles), 50):
        d = get(WP, action="query", prop="pageprops", ppprop="wikibase_item", redirects=1,
                titles="|".join(titles[i:i + 50]), format="json")
        back = {r["to"]: r["from"] for r in d["query"].get("redirects", [])}
        back.update({n["to"]: n["from"] for n in d["query"].get("normalized", [])})
        for p in d["query"]["pages"].values():
            q = p.get("pageprops", {}).get("wikibase_item")
            if q:
                qid[back.get(p["title"], p["title"])] = q
    return qid


def inchikeys(qids) -> dict[str, list[str]]:
    keys = {}
    qids = sorted(set(qids))
    for i in range(0, len(qids), 200):
        q = ("SELECT ?item ?ik WHERE { VALUES ?item { " + " ".join("wd:" + x for x in qids[i:i + 200])
             + " } ?item wdt:P235 ?ik }")
        for b in get(SPARQL, query=q, format="json")["results"]["bindings"]:
            keys.setdefault(b["item"]["value"].rsplit("/", 1)[1], []).append(b["ik"]["value"])
    return keys


def role_items(roles) -> list[dict]:
    q = ("SELECT DISTINCT ?item ?itemLabel ?ik WHERE { VALUES ?role { " + " ".join("wd:" + r for r in roles)
         + " } ?item wdt:P2868|wdt:P366 ?role . OPTIONAL { ?item wdt:P235 ?ik }"
         + ' SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }')
    by = {}
    for b in get(SPARQL, query=q, format="json")["results"]["bindings"]:
        q_ = b["item"]["value"].rsplit("/", 1)[1]
        e = by.setdefault(q_, {"title": b["itemLabel"]["value"], "qid": q_, "inchikeys": []})
        if "ik" in b and b["ik"]["value"] not in e["inchikeys"]:
            e["inchikeys"].append(b["ik"]["value"])
    # An item with no English label comes back labelled with its own id.
    return [e for e in by.values() if e["title"] != e["qid"]]


def main() -> int:
    raw = pathlib.Path(sys.argv[1])
    raw.mkdir(parents=True, exist_ok=True)
    for lst, roots in CATEGORY_LISTS.items():
        titles = [t for t in pages_under(roots) if not t.startswith("List of")]
        qid = items_of(titles)
        keys = inchikeys(qid.values())
        rows = [{"title": t, "qid": qid.get(t), "inchikeys": keys.get(qid.get(t), [])} for t in titles]
        (raw / f"{lst}.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False))
        print(f"{lst}: {len(rows)} pages, {sum(bool(r['inchikeys']) for r in rows)} with an InChIKey")
    for lst, roles in ROLE_LISTS.items():
        rows = role_items(roles)
        (raw / f"{lst}.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False))
        print(f"{lst}: {len(rows)} items, {sum(bool(r['inchikeys']) for r in rows)} with an InChIKey")
    return 0


if __name__ == "__main__":
    sys.exit(main())
