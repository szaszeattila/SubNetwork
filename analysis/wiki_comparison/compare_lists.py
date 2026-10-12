#!/usr/bin/env python3
"""Set other public compound lists beside the wiki's and the catalogue.

Each list is a file in LIST_DIR, written by prepare_lists.py:
<list>.names.txt, one compound per line with alternative names after " | ", and
optionally <list>.inchikeys.tsv, "name<TAB>InChIKey" for the lists that carry
structures (Wikidata). Every entry is placed with placing.Placer — an InChIKey
when the list gives one, else the name tiers, without PubChem — and two
entries are the same compound when they reach a common ChEMBL parent or, when
neither is placed, when their names are equal with punctuation dropped.

Read-only. Writes LIST_DIR/lists_overlap.csv (one row per list entry, kept
out of the repository with the lists) and prints one summary row per list.

    python3 analysis/wiki_comparison/compare_lists.py LIST_DIR [--data-root DIR]
"""
import argparse
import collections
import csv
import pathlib
import sys

from placing import HERE, ROOT, Placer, squash
from prepare_lists import alternatives


# Another list's name for something the wiki lists under a different one, found
# by reading every "not on the wiki" entry of the nootropic lists. Each is a
# reviewed equivalence, not a fuzzy match: list name -> wiki name.
SAME_AS_WIKI = {
    "Centrophenoxine": "Meclofenoxate",          # the INN
    "Kava Kava": "Kava",
    "Catuaba Bark": "Catuaba",
    "Cacao": "Cacao Powder",
    "Coconut & MCT Oil": "MCT Oil",
    "CoQ10 & Ubiquinol": "CoQ10",
    "L- Carnosine": "Carnosine",
    "Rosemary": "Rosemary Extract",
    "Valerian": "Valerian Root",
    "CBD Oil": "CBD",
    "Black Seed Oil": "Nigella Sativa",
    "Pine Bark Extract": "Pycnogenol",           # a standardised pine bark extract
    "N-Acetyl L-Cysteine": "NAC",
    "N-Acetylcysteine": "NAC",
    "Vitamin B12 (Cobalamin)": "Cyanocobalamin",  # the wiki lists two B12 forms
    "DMAA": "1,3-DMAA",
    "9-Methyl-β-carboline": "9-Me-BC",
    "Dimethylethanolamine": "DMAE",
    "Tropoflavin": "7,8-DHF",                    # 7,8-dihydroxyflavone; eutropoflavin is another compound
    "ergoloid mesylate": "Hydergine",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("list_dir", type=pathlib.Path)
    ap.add_argument("--data-root", type=pathlib.Path, default=ROOT)
    args = ap.parse_args()
    pl = Placer(args.data_root)

    wiki = list(csv.DictReader(open(HERE / "comparison.csv", encoding="utf-8")))
    wiki_parents = {c for r in wiki for c in r["chembl_parents"].split("|") if c}
    # "N-Acetyl L-Tyrosine (NALT)" also answers to either half.
    wiki_names = {squash(a) for r in wiki for a in alternatives(r["name"]).split(" | ")}

    rows, summary, covered_anywhere = [], [], set()
    for f in sorted(args.list_dir.glob("*.names.txt")):
        lst = f.name[: -len(".names.txt")]
        keys = collections.defaultdict(list)
        kf = args.list_dir / f"{lst}.inchikeys.tsv"
        if kf.exists():
            for line in kf.read_text(encoding="utf-8").splitlines():
                name, _, key = line.partition("\t")
                if key.strip():
                    keys[name.strip()].append(key.strip())
        lines = list(dict.fromkeys(n.strip() for n in f.read_text(encoding="utf-8").splitlines() if n.strip()))
        seen_ids, c = set(), collections.Counter()
        for line in lines:
            alts = [a.strip() for a in line.split(" | ") if a.strip()]
            name = alts[0]
            # The first alternative that places wins; an entry nothing places
            # keeps its first name for the name comparison.
            for alt in alts:
                got, tier, _note, conf = pl.place(alt, keys.get(alt, ()), use_pubchem=False)
                if got:
                    break
            ids = pl.ids(got)
            # Two names on one list reaching one parent are one compound.
            ident = frozenset(ids) if ids else frozenset({"name:" + squash(name)})
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            if name in SAME_AS_WIKI:
                alts.append(SAME_AS_WIKI[name])
            in_wiki = bool(set(ids) & wiki_parents) or any(squash(a) in wiki_names for a in alts)
            in_cat = [i for i in ids if i in pl.catalogue]
            c["entries"] += 1
            c["placed"] += bool(ids)
            c["in_wiki"] += in_wiki
            c["in_catalogue"] += bool(in_cat)
            c["neither"] += not in_wiki and not in_cat
            rows.append({"list": lst, "name": name, "alternatives": " | ".join(alts),
                         "match_tier": tier, "confidence": conf,
                         "chembl_parents": "|".join(ids), "in_wiki": int(in_wiki),
                         "in_catalogue": "|".join(in_cat)})
        list_parents = {i for r in rows if r["list"] == lst for i in r["chembl_parents"].split("|") if i}
        list_names = {squash(SAME_AS_WIKI.get(r["name"], r["name"])) for r in rows if r["list"] == lst}
        list_names |= {squash(a) for r in rows if r["list"] == lst for a in r["alternatives"].split(" | ")}
        hit = {r["slug"] for r in wiki if (set(r["chembl_parents"].split("|")) & list_parents)
               or any(squash(a) in list_names for a in alternatives(r["name"]).split(" | "))}
        c["wiki_covered"] = len(hit)
        covered_anywhere |= hit
        summary.append((lst, c))

    # Beside the lists, not in the repository: it reproduces their names.
    with open(args.list_dir / "lists_overlap.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("| list | compounds | placed in ChEMBL | also on the wiki | in the catalogue | on neither | wiki entries it has |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for lst, c in summary:
        pct = lambda n: f"{n} ({100 * n / c['entries']:.0f}%)" if c["entries"] else "0"
        print(f"| {lst} | {c['entries']} | {pct(c['placed'])} | {pct(c['in_wiki'])} | {pct(c['in_catalogue'])} "
              f"| {pct(c['neither'])} | {c['wiki_covered']} of {len(wiki)} |")
    by_section = collections.Counter(r["section"] for r in wiki if r["slug"] not in covered_anywhere)
    print(f"\nwiki entries on at least one other list: {len(covered_anywhere)} of {len(wiki)}; "
          f"on none, by section: {dict(by_section.most_common())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
