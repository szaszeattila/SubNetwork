#!/usr/bin/env python3
"""Turn raw downloads of other public compound lists into the name files
compare_lists.py reads: <list>.names.txt, one compound per line with
alternative names after " | ", and <list>.inchikeys.tsv where the list gives
structures.

The lists are other sites' content, under CC BY-SA, CC0 or unstated terms, so
neither the downloads nor the name files are kept in this repository; this
script and the retrieval below are, and the counts are in
docs/NOOTROPIC-WIKI-COMPARISON.md. Retrieved 2026-10-11 into RAW:

  psychonautwiki.json   POST https://api.psychonautwiki.org/ with
                        {"query":"{ substances(limit: 5000) { name class { chemical psychoactive } } }"}
  psychonautwiki_cat_nootropic.json
                        https://psychonautwiki.org/w/api.php?action=query&list=categorymembers&cmtitle=Category:Nootropic&cmlimit=500&format=json
  tripsit.json          https://tripbot.tripsit.me/api/tripsit/getAllDrugs
  wikipedia_cat_nootropics.json
                        https://en.wikipedia.org/w/api.php?action=query&list=categorymembers&cmtitle=Category:Nootropics&cmlimit=500&format=json
  wikidata_nootropic.csv
                        SPARQL at query.wikidata.org: items whose P2868 (subject has
                        role), P366 (has use), P31 or P279 reaches Q742487 (nootropic),
                        with P235 (InChIKey); columns item,itemLabel,ik,via
  nootropicsexpert_list.html
                        https://nootropicsexpert.com/nootropics-list/ (Crawl-delay 5)

Examine.com (bot checkpoint), Erowid (scraping needs written permission),
DrugBank (licence) and the r/Nootropics wiki (403) were not retrieved.

    python3 analysis/wiki_comparison/prepare_lists.py RAW OUT
"""
import csv
import html
import json
import pathlib
import re
import sys

# Wikipedia's category holds articles about the idea as well as compounds.
WIKIPEDIA_NOT_COMPOUNDS = {
    "Nootropic", "Neuroenhancement", "Performance-enhancing substance", "Eugeroic",
    "Smart drink", "Kavalactone", "Lecithin", "Prospekta",
}


def alternatives(name: str) -> str:
    """'Vitamin B3 (Niacin)' -> 'Vitamin B3 (Niacin) | Niacin | Vitamin B3'."""
    m = re.fullmatch(r"(.+?)\s*\(([^)]+)\)", name)
    if not m:
        return name
    outer, inner = m.group(1).strip(), m.group(2).strip()
    if inner.lower() in ("drug", "compound", "medication", "supplement"):
        return f"{name} | {outer}"
    return f"{name} | {inner} | {outer}"


def write(out: pathlib.Path, lst: str, names, keys=()):
    (out / f"{lst}.names.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    if keys:
        (out / f"{lst}.inchikeys.tsv").write_text("\n".join(f"{n}\t{k}" for n, k in keys) + "\n", encoding="utf-8")
    print(f"{lst}: {len(names)}")


def main() -> int:
    raw, out = map(pathlib.Path, sys.argv[1:3])
    out.mkdir(parents=True, exist_ok=True)

    subs = json.loads((raw / "psychonautwiki.json").read_text())["data"]["substances"]
    write(out, "psychonautwiki_all", [s["name"] for s in subs])
    cat = json.loads((raw / "psychonautwiki_cat_nootropic.json").read_text())["query"]["categorymembers"]
    write(out, "psychonautwiki_nootropic", [m["title"] for m in cat if m["ns"] == 0 and m["title"] != "Nootropic"])

    trip = json.loads((raw / "tripsit.json").read_text())["data"][0]
    line = lambda d: " | ".join(dict.fromkeys([d.get("pretty_name") or d["name"], d["name"], *(d.get("aliases") or [])]))
    write(out, "tripsit_all", [line(d) for d in trip.values()])
    write(out, "tripsit_nootropic", [line(d) for d in trip.values() if "nootropic" in (d.get("categories") or [])])

    wp = json.loads((raw / "wikipedia_cat_nootropics.json").read_text())["query"]["categorymembers"]
    titles = [m["title"] for m in wp if m["ns"] == 0]
    keep = [t for t in titles if t not in WIKIPEDIA_NOT_COMPOUNDS and not t.startswith("List of")]
    write(out, "wikipedia_nootropics", [alternatives(t) for t in keep])

    # Only "subject has role" and "has use": the P31/P279 routes reach coffee
    # brands and drinks, because coffee carries the role.
    rows = [r for r in csv.DictReader(open(raw / "wikidata_nootropic.csv", encoding="utf-8"))
            if r["via"].startswith(("P2868", "P366")) and not re.fullmatch(r"Q\d+", r["itemLabel"])]
    labels = list(dict.fromkeys(r["itemLabel"] for r in rows))
    write(out, "wikidata_nootropic", labels, [(r["itemLabel"], r["ik"]) for r in rows if r["ik"]])

    page = (raw / "nootropicsexpert_list.html").read_text(encoding="utf-8", errors="replace")
    body = page[page.find("What is this List of Nootropics About?"):]
    heads = [html.unescape(re.sub(r"<[^>]+>", "", h)).strip() for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S)]
    # The list ends at the newsletter heading; after it come the comments,
    # whose commenter names are headings too.
    end = next((i for i, h in enumerate(heads) if re.search(r"newsletter", h, re.I)), len(heads))
    heads = [h for h in heads[1:end] if h and not re.search(r"head first|list of nootropics", h, re.I)]
    write(out, "nootropicsexpert", [alternatives(h) for h in heads])
    return 0


if __name__ == "__main__":
    sys.exit(main())
