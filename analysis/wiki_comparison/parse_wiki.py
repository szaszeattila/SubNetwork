#!/usr/bin/env python3
"""Turn a saved copy of scientificsean.wiki's /compounds/table page into
wiki_compounds.csv: one row per compound tile, with the section and class the
wiki files it under.

Neither the page nor the list is kept in the repository: the list, which
copies the wiki's arrangement, is written to placing.REFERENCE
(db/cache/sciwiki/, gitignored), and so is a saved page worth keeping. Run:

    curl -sL https://www.scientificsean.wiki/compounds/table -o table.html
    python3 analysis/wiki_comparison/parse_wiki.py table.html
"""
import csv
import html
import pathlib
import re
import sys

from placing import REFERENCE


def parse(text: str) -> list[dict]:
    # A section is an <h2> carrying its own count; a class is a tagged label
    # heading a "bay" of tiles inside it. Each tile links /compounds/<slug>.
    sections = [(m.start(), html.unescape(re.sub(r"<span.*", "", m.group(1))).strip())
                for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", text, re.S)]
    classes = [(m.start(), html.unescape(m.group(1)).strip())
               for m in re.finditer(r'<span class="pt-cls-tag">[^<]*</span><span[^>]*>([^<]*)</span>', text)]
    rows = []
    for m in re.finditer(r'<a href="/compounds/([^"#?]+)" data-pt-tile="[^"]*"[^>]*>.*?'
                         r'<span class="pt-name[^"]*">([^<]*)</span>', text):
        def before(marks):
            return max((x for x in marks if x[0] < m.start()), default=(0, ""))[1]
        rows.append({"slug": m.group(1), "name": html.unescape(m.group(2)).strip(),
                     "section": before(sections), "wiki_class": before(classes)})
    return rows


def main() -> int:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    rows = parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    if len({r["slug"] for r in rows}) != len(rows):
        sys.exit("duplicate slugs: the page layout has changed")
    with open(REFERENCE / "wiki_compounds.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["slug", "name", "section", "wiki_class"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} compounds in {len({r['section'] for r in rows})} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
