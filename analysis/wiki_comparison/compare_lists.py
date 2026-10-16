#!/usr/bin/env python3
"""Set other public compound lists beside the wiki's and the catalogue.

Each list is a file in LIST_DIR, written by prepare_lists.py:
<list>.names.txt, one compound per line with alternative names after " | ", and
optionally <list>.inchikeys.tsv, "name<TAB>InChIKey" for the lists that carry
structures (Wikidata). Every entry is placed with placing.Placer — an InChIKey
when the list gives one, else the name tiers, without PubChem — and two
entries are the same compound when they reach a common ChEMBL parent or, when
neither is placed, when their names are equal with punctuation dropped.

Since D25 and D26 a catalogue entry may be there because the wiki lists it
(molecule_listings); `sciwiki_listed` names such entries, and
LIST_DIR/listed_on_lists.csv says which lists each of them is on. Since D27 the open
lists are reasons for entry too, so the summary also counts each list's
entries a listing entered and those still in ChEMBL and outside.

Read-only. Writes LIST_DIR/lists_overlap.csv (one row per list entry) and
listed_on_lists.csv, both kept out of the repository with the lists, and
prints one summary row per list, then the listed entries by section.

    python3 analysis/wiki_comparison/compare_lists.py LIST_DIR [--data-root DIR]
"""
import argparse
import collections
import csv
import pathlib
import sys

from placing import REFERENCE, ROOT, Placer, squash
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

    wiki = list(csv.DictReader(open(REFERENCE / "comparison.csv", encoding="utf-8")))
    # The entries the wiki brought in (D25, D26), by ChEMBL parent.
    listed = {cid: {"chembl_id": cid, "name": name, "section": section, "evidence_status": ev}
              for cid, name, section, ev in pl.coh.execute(
                  "SELECT m.chembl_id, l.name, l.section, m.evidence_status FROM molecule_listings l "
                  "JOIN molecules m USING (parent_molregno) WHERE l.source = 'sciwiki'")}
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
            in_listing = [i for i in ids if i in listed]
            # Since D27 an entry may be in the catalogue because this very list
            # (or another open one) names it.
            c["entered_by_a_list"] += any(pl.catalogue[i][0] == "listed_only" for i in in_cat)
            c["outside"] += bool(ids) and not in_cat
            for i in in_listing:
                listed[i][lst] = 1
            c["entries"] += 1
            c["listed"] += bool(in_listing)
            c["placed"] += bool(ids)
            c["in_wiki"] += in_wiki
            c["in_catalogue"] += bool(in_cat)
            c["neither"] += not in_wiki and not in_cat
            rows.append({"list": lst, "name": name, "alternatives": " | ".join(alts),
                         "match_tier": tier, "confidence": conf,
                         "chembl_parents": "|".join(ids), "in_wiki": int(in_wiki),
                         "in_catalogue": "|".join(in_cat), "sciwiki_listed": "|".join(in_listing)})
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
    lists = [lst for lst, _ in summary]
    with open(args.list_dir / "listed_on_lists.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["chembl_id", "name", "section", "evidence_status", *lists], restval=0)
        w.writeheader()
        w.writerows(sorted(listed.values(), key=lambda e: (e["section"], e["name"].casefold())))

    print("| list | compounds | placed in ChEMBL | also on the wiki | in the catalogue | entered from the wiki "
          "| entered from a list | in ChEMBL, outside | on neither | wiki entries it has |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for lst, c in summary:
        pct = lambda n: f"{n} ({100 * n / c['entries']:.0f}%)" if c["entries"] else "0"
        print(f"| {lst} | {c['entries']} | {pct(c['placed'])} | {pct(c['in_wiki'])} | {pct(c['in_catalogue'])} "
              f"| {pct(c['listed'])} | {c['entered_by_a_list']} | {c['outside']} | {pct(c['neither'])} "
              f"| {c['wiki_covered']} of {len(wiki)} |")
    by_section = collections.Counter(r["section"] for r in wiki if r["slug"] not in covered_anywhere)
    print(f"\nwiki entries on at least one other list: {len(covered_anywhere)} of {len(wiki)}; "
          f"on none, by section: {dict(by_section.most_common())}")

    # The entries the wiki brought in, by section: how many each list has.
    sections = sorted({e["section"] for e in listed.values()})
    print("\n| list | " + " | ".join(sections) + " | all |")
    print("|---|" + "---:|" * (len(sections) + 1))
    of = {sec: [e for e in listed.values() if e["section"] == sec] for sec in sections}
    for lst in lists + ["any"]:
        has = (lambda e: any(e.get(x) for x in lists)) if lst == "any" else (lambda e: e.get(lst))
        print(f"| {lst} | " + " | ".join(f"{sum(1 for e in of[sec] if has(e))} of {len(of[sec])}" for sec in sections)
              + f" | {sum(1 for e in listed.values() if has(e))} of {len(listed)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
