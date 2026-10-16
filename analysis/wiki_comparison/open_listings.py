#!/usr/bin/env python3
"""Write the open lists' entries into the selection policy (D27).

Every compound Wikipedia, Wikidata, TripSit or PsychonautWiki carries that
compare_lists.py placed at a ChEMBL parent outside the clinical catalogue is
listed under that list, by the ChEMBL id, with the list's name for it and the
key its page is linked by. A compound the sci-wiki brought in (D25, D26) that
one of the four also carries is cited by the four instead, and its sci-wiki
entry is dropped; the sci-wiki stays the source only where no open list names
the compound.

Identity is D25's rule. A placement by an InChIKey the list itself gives (from
the article's Wikidata item), by an FDA UNII InChIKey, or by an exact ChEMBL
preferred name is read over and kept. Anything else - a synonym, a squashed
name, a skeleton-only match, or a name reaching two parents - is in REVIEW,
decided by hand against ChEMBL's structure, and an entry REVIEW does not name
stops the script.

Reads LIST_DIR/lists_overlap.csv (compare_lists.py, run against the D26
build), the raw downloads for page keys, and the active database for which
parents the clinical routes and the seeds already hold. Prints a summary;
with --write, rewrites the four listings blocks and the sci-wiki block's
molecules in config/cohort1_selection.json.

    python3 analysis/wiki_comparison/open_listings.py LIST_DIR RAW [RAW ...] [--write]
"""
import argparse
import collections
import csv
import json
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
POLICY = ROOT / "config" / "cohort1_selection.json"

# compare_lists.py's lists, by the policy key they are listed under, in the
# order a section is named; the nootropic sub-lists of TripSit and
# PsychonautWiki are subsets of their whole lists and add nothing.
SOURCES = {
    "wikipedia": [("wikipedia_nootropics", "Category:Nootropics"),
                  ("wikipedia_psychoactive", "Category:Psychedelic drugs and other psychoactive categories"),
                  ("wikipedia_designer", "Category:Designer drugs")],
    "wikidata": [("wikidata_nootropic", "role: nootropic"),
                 ("wikidata_psychoactive", "role: psychoactive")],
    "tripsit": [("tripsit_all", None)],
    "psychonautwiki": [("psychonautwiki_all", None)],
}
IDENTIFIER_TIERS = {"inchikey", "unii_inchikey", "chembl_name"}

_IDENTITY = ("Each entry names a ChEMBL id, written down by analysis/wiki_comparison/open_listings.py; "
             "the build reads the id and never the name (invariant 15). placed_by records how the "
             "list's entry was placed: inchikey (the InChIKey on the entry's Wikidata item, given by "
             "the list), unii_inchikey, chembl_name, or a weaker tier that the script's REVIEW table "
             "decided by hand against ChEMBL's structure; review says why such an entry was kept or "
             "corrected, and considered_and_not_listed why one was refused.")
_ONLY_OUTSIDE = ("Only parents outside the clinical routes and the seeds are named: the listing is a "
                 "reason for entry, and a member the routes admit already has one.")
_LABEL = ("Like a seed (D05), a listed molecule is never in the clinical cohort: in_cohort stays the "
          "two routes and admission_reason reads listed_only. A listing is not evidence of anything "
          "and never enters the similarity score.")
# Each source's policy block, set where the policy lacks it. Its terms were
# read on the date given; docs/COMPOUND-LIST-TERMS.md has the reading.
SOURCE_META = {
    "wikipedia": {
        "source": "English Wikipedia (Wikimedia Foundation)",
        "home": "https://en.wikipedia.org/",
        "page": "https://en.wikipedia.org/wiki/{slug}",
        "licence": "CC BY-SA 4.0",
        "retrieved": "2026-10-15",
        "decision": "docs/COHORT-2.md D27",
        "rule": "A ChEMBL parent named below enters the catalogue whatever the clinical routes say, because an English Wikipedia article on it is filed in Category:Nootropics; in Category:Psychedelic drugs or a category below it, Category:Entactogens, Dissociative drugs, Deliriants or Cathinones; or in Category:Designer drugs or its subcategories, as analysis/wiki_comparison/fetch_lists.py read them on 2026-10-15. " + _ONLY_OUTSIDE,
        "membership_labelling": _LABEL,
        "identity": _IDENTITY,
        "terms": "Article text is CC BY-SA 4.0. What is kept is the article's title, a fact, and the title its page is linked by (slug); no article text is copied. Each entry links its article, and About names Wikipedia and its licence. section names the category an article was read from, which is a fact about where an editor filed it.",
    },
    "wikidata": {
        "source": "Wikidata (Wikimedia Foundation)",
        "home": "https://www.wikidata.org/",
        "page": "https://www.wikidata.org/wiki/{slug}",
        "licence": "CC0 1.0",
        "retrieved": "2026-10-15",
        "decision": "docs/COHORT-2.md D27",
        "rule": "A ChEMBL parent named below enters the catalogue whatever the clinical routes say, because its Wikidata item's subject has role (P2868) or has use (P366) is nootropic, or a psychoactive role (psychedelic drug, hallucinogen, empathogen-entactogen, dissociative, stimulant), as analysis/wiki_comparison/fetch_lists.py read them on 2026-10-15. " + _ONLY_OUTSIDE,
        "membership_labelling": _LABEL,
        "identity": _IDENTITY,
        "terms": "Structured data is CC0 1.0 and needs no attribution; it is credited anyway. What is kept is the item's English label and its Q-id (slug), which the entry links.",
    },
    "tripsit": {
        "source": "TripSit factsheets (tripsit.me)",
        "home": "https://tripsit.me/factsheets/",
        "page": "https://tripsit.me/factsheets/{slug}",
        "licence": "free of charge for non-commercial use, with a link back and a note citing TripSit",
        "retrieved": "2026-10-11",
        "decision": "docs/COHORT-2.md D27",
        "rule": "A ChEMBL parent named below enters the catalogue whatever the clinical routes say, because TripSit's factsheets (its getAllDrugs API, read 2026-10-11) carry it. " + _ONLY_OUTSIDE,
        "membership_labelling": _LABEL,
        "identity": _IDENTITY,
        "terms": "wiki.tripsit.me/wiki/Factsheets, read 2026-10-15: \"Use of the data from factsheets, whether copied directly or obtained through the API is free-of-charge for non-commercial purposes. We only require that your application links back to either this page, the Factsheets homepage, or the specific factsheet page of the drug concerned. This should be accompanied with a note citing TripSit as the source for the particular piece(s) of information on every page which uses/displays the information.\" SubNetwork is free and carries no advertising. What is kept is TripSit's display name and the key its factsheet is linked by (slug); the panel showing an entry links that factsheet and names TripSit as the source of the listing, and About credits TripSit. None of a factsheet's doses, effects or categories is copied.",
    },
    "psychonautwiki": {
        "source": "PsychonautWiki",
        "home": "https://psychonautwiki.org/",
        "page": "https://psychonautwiki.org/wiki/{slug}",
        "licence": "CC BY 4.0 (semantic data); articles CC BY-SA 4.0",
        "retrieved": "2026-10-11",
        "decision": "docs/COHORT-2.md D27",
        "rule": "A ChEMBL parent named below enters the catalogue whatever the clinical routes say, because PsychonautWiki's substance index (its API, read 2026-10-11) carries it. " + _ONLY_OUTSIDE,
        "membership_labelling": _LABEL,
        "identity": _IDENTITY,
        "terms": "psychonautwiki.org/wiki/Copyrights, read 2026-10-15: content is CC BY-SA 4.0, and semantic data, which the substance index is, CC BY 4.0, usable \"for any purpose, when properly attributed\". What is kept is the substance's name and the page title it is linked by (slug); each entry links its page, and About gives PsychonautWiki's name, link and licence. No article text, dose or class is copied.",
    },
}


def render_listings(listings: dict) -> str:
    """The policy's listings block, one entry per line as the file keeps it."""
    out = ['  "listings": {']
    for i, (src, block) in enumerate(listings.items()):
        out.append(f'    {json.dumps(src)}: {{')
        items = list(block.items())
        for j, (k, v) in enumerate(items):
            comma = "," if j < len(items) - 1 else ""
            if isinstance(v, list):
                out.append(f'      {json.dumps(k)}: [')
                out.extend(f'        {json.dumps(e, ensure_ascii=False)}{"," if n < len(v) - 1 else ""}'
                           for n, e in enumerate(v))
                out.append(f'      ]{comma}')
            else:
                out.append(f'      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}{comma}')
        out.append("    }" + ("," if i < len(listings) - 1 else ""))
    out.append("  }")
    return "\n".join(out)

# Each non-identifier placement, compared with what ChEMBL draws at the id,
# on D25's and D26's precedents: a name that gives no stereochemistry is
# refused where ChEMBL holds only single stereoisomers of it (5-MAPB, MDPV in
# D26), kept where ChEMBL's only record is drawn flat (nooglutyl in D25), and a
# name reaching several parents is placed only where another open list's
# InChIKey places the same compound.
# (list, name) -> ("keep", note) | ("correct", chembl_id, note) | ("refuse", note)
_RACEMATE = "a racemate by its name and the list's flat InChIKey; ChEMBL holds it only as single enantiomers"
_STEREO = "the list's InChIKey is a stereoisomer ChEMBL does not draw; the skeleton reaches other stereoisomers only"
_SEVERAL = "reaches several ChEMBL stereoisomers, and no open list's InChIKey says which"
_ONLY_FLAT = "matched by skeleton at ChEMBL's only record of it, drawn with no stereochemistry"
_BELLADONNA = "ChEMBL's structureless BELLADONNA record, as D26 placed the sci-wiki's Atropa belladonna"
_PCP = "ChEMBL's PHENCYCLIDINE, where Wikipedia's and Wikidata's InChIKeys place it too"
_MDA = "the four-letter synonym of TENAMFETAMINE (MDA), as D26 placed the sci-wiki's MDA"
_ANIL = "ChEMBL synonym of isoaminile, an antitussive; 2C-B-AN is a 2C-B prodrug (brolphetaminil)"
REVIEW: dict = {
    ("psychonautwiki_all", "Atropa belladonna"): ("keep", _BELLADONNA),
    ("wikipedia_psychoactive", "Atropa bella-donna"): ("keep", _BELLADONNA),
    ("psychonautwiki_all", "MDA"): ("keep", _MDA),
    ("tripsit_all", "MDA"): ("keep", _MDA),
    ("psychonautwiki_all", "PCP"): ("keep", _PCP),
    ("tripsit_all", "PCP"): ("keep", _PCP),
    ("tripsit_all", "4-Chlorodiazepam"): ("keep", "ChEMBL's RO-54864 is 4'-chlorodiazepam (Ro5-4864)"),
    ("tripsit_all", "Amfecloral"): ("keep", "ChEMBL's AMPHECLORAL, the same compound under its other spelling"),
    ("tripsit_all", "Desmethylflunitrazepam"): ("keep", "ChEMBL draws N-desmethylflunitrazepam (fonazepam) at the id"),
    ("tripsit_all", "MK-801"): ("keep", "ChEMBL's DIZOCILPINE, drawn as the (+)-enantiomer MK-801 names"),
    ("tripsit_all", "Methedrone"): ("keep", "ChEMBL's METHOXYPHEDRINE is 4-methoxymethcathinone"),
    ("tripsit_all", "PV-10"): ("keep", "ChEMBL draws alpha-pyrrolidinononanophenone at the id, which PV-10 names"),
    ("wikidata_nootropic", "Traneurocin"): ("keep", "ChEMBL's own synonym of cyclo(prolylglycyl); Wikidata's item gives no structure"),
    ("wikipedia_psychoactive", "Dimethylcathinone"): ("keep", "ChEMBL's METAMFEPRAMONE is N,N-dimethylcathinone"),
    ("wikidata_nootropic", "nooglutil"): ("keep", _ONLY_FLAT + ", as D25 placed the sci-wiki's nooglutyl"),
    ("wikipedia_nootropics", "Nooglutyl"): ("keep", _ONLY_FLAT + ", as D25 placed the sci-wiki's nooglutyl"),
    ("wikipedia_designer", "Trendione"): ("keep", _ONLY_FLAT),
    ("wikipedia_designer", "AC-262,536"): ("keep", "ChEMBL's only record, drawn as the one bridged-ring isomer the compound is; the list's key leaves the ring stereo undrawn"),
    ("wikidata_psychoactive", "picrotoxin"): ("correct", "CHEMBL1908342", "picrotoxin is a picrotoxinin-picrotin mixture ChEMBL draws eight ways; CHEMBL1908342 is the record ChEMBL names PICROTOXIN"),
    ("tripsit_all", "3,4-CTMP"): ("correct", "CHEMBL1179011", "the name reaches five stereoisomers; Wikipedia's 3,4-Dichloromethylphenidate places the compound here by its InChIKey"),
    ("tripsit_all", "4-Fluoromethylphenidate"): ("correct", "CHEMBL1253289", "the name reaches two stereoisomers; Wikipedia's article places the compound here by its InChIKey"),
    ("tripsit_all", "U-47700"): ("correct", "CHEMBL277572", "the name reaches two enantiomers; Wikipedia's article places the compound here by its InChIKey"),
    ("psychonautwiki_all", "U-47700"): ("correct", "CHEMBL277572", "the name reaches two enantiomers; Wikipedia's article places the compound here by its InChIKey"),
    ("psychonautwiki_all", "Dichloropane"): ("refuse", _SEVERAL + ", as D25 found"),
    ("wikipedia_designer", "Dichloropane"): ("refuse", _STEREO),
    ("tripsit_all", "RTI-111"): ("refuse", "RTI-111 is dichloropane; " + _SEVERAL),
    ("psychonautwiki_all", "Methylnaphthidate"): ("refuse", _SEVERAL + ", as D25 found"),
    ("tripsit_all", "2C-B-AN"): ("refuse", _ANIL),
    ("wikipedia_designer", "2C-B-AN"): ("refuse", _ANIL),
    ("wikipedia_psychoactive", "2C-B-AN"): ("refuse", _ANIL),
    ("tripsit_all", "Aleph"): ("refuse", "the squashed name reached dinitolmide, a coccidiostat; Aleph is 4-methylthio-2,5-dimethoxyamphetamine"),
    ("tripsit_all", "αMT"): ("refuse", "ChEMBL synonym of 3-amino-3-deoxythymidine; αMT is alpha-methyltryptamine"),
    ("wikipedia_psychoactive", "G-4 (drug)"): ("refuse", "ChEMBL synonym of dichlorophen, an antimicrobial; G-4 is a DOx homologue, and the article's InChIKey is not in ChEMBL"),
    ("wikidata_psychoactive", "Beta-D"): ("refuse", "a deuterated mescaline; the skeleton match reaches mescaline itself"),
    ("wikipedia_psychoactive", "4-D (psychedelic)"): ("refuse", "a deuterated mescaline; the skeleton match reaches mescaline itself"),
    ("tripsit_all", "6-MAPB"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "6-MAPB"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "6-MAPB"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "5-MAPB"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikipedia_psychoactive", "5-MAPB"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikidata_psychoactive", "methylenedioxypyrovalerone"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikipedia_designer", "Methylenedioxypyrovalerone"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikipedia_psychoactive", "Methylenedioxypyrovalerone"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikidata_psychoactive", "Ariadne"): ("refuse", _RACEMATE + ", as D26 found"),
    ("wikipedia_psychoactive", "Ariadne (drug)"): ("refuse", _RACEMATE + ", as D26 found"),
    ("tripsit_all", "MT-45"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "MT-45"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "4-Fluorophenibut"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "4-Methylaminorex"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "Dimethylamphetamine"): ("refuse", _RACEMATE),
    ("wikidata_psychoactive", "N,N-dimethylamphetamine"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "Propylamphetamine"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "MPMI (drug)"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "MPMI (drug)"): ("refuse", _RACEMATE),
    ("wikipedia_designer", "N-Hydroxy-DOM"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "N-Hydroxy-DOM"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "2C-B-3PIP"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "3,5-Dimethoxyamphetamine"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "4-HO-αMT"): ("refuse", _RACEMATE),
    ("wikipedia_psychoactive", "8A-PDHQ"): ("refuse", _SEVERAL),
    ("wikipedia_psychoactive", "AL-38022A"): ("refuse", "the list's flat InChIKey; ChEMBL holds one enantiomer, and which the name means is not settled here"),
    ("wikipedia_psychoactive", "DragonFLY"): ("refuse", _RACEMATE),
    ("wikidata_nootropic", "S-17092"): ("refuse", _STEREO),
    ("wikipedia_nootropics", "S-17092"): ("refuse", _STEREO),
    ("wikipedia_designer", "Bolandione"): ("refuse", _STEREO),
    ("wikipedia_designer", "CP 47,497"): ("refuse", _STEREO),
    ("wikipedia_designer", "Fentanyl tropane"): ("refuse", _STEREO),
    ("wikipedia_designer", "LSZ"): ("refuse", _STEREO + ", as D26 found"),
    ("wikipedia_psychoactive", "LSZ"): ("refuse", _STEREO + ", as D26 found"),
    ("wikipedia_psychoactive", "CAR-226,086"): ("refuse", _STEREO),
    ("wikipedia_psychoactive", "CS-27349"): ("refuse", _STEREO),
    ("wikipedia_psychoactive", "Tropine benzilate"): ("refuse", _STEREO),
    # From the read-over of identifier placements.
    ("psychonautwiki_all", "Myristicin"): ("keep", "FDA's UNII for myristicin places it at a record ChEMBL draws as myristicin and names ELEMICIN, a naming error in ChEMBL 37; the structure is the identity"),
    ("wikipedia_psychoactive", "Deupsilocin"): ("refuse", "ChEMBL files deupsilocin, a deuterated drug, as a form of psilocin; the article is about the deuterated drug, and psilocin is listed under its own name"),
}


def page_keys(raws):
    """(list, name) -> (slug, display name), from the raw downloads."""
    def find(name):
        return next((r / name for r in reversed(raws) if (r / name).exists()), None)

    keys = {}
    for lst in ("wikipedia_nootropics", "wikipedia_psychoactive", "wikipedia_designer"):
        for r in json.loads(find(f"{lst}.json").read_text()):
            keys[(lst, r["title"])] = (r["title"].replace(" ", "_"), r["title"])
    for lst in ("wikidata_nootropic", "wikidata_psychoactive"):
        for r in json.loads(find(f"{lst}.json").read_text()):
            keys[(lst, r["title"])] = (r["qid"], r["title"])
    for d in json.loads(find("tripsit.json").read_text())["data"][0].values():
        keys[("tripsit_all", d.get("pretty_name") or d["name"])] = (d["name"], d.get("pretty_name") or d["name"])
    for s in json.loads(find("psychonautwiki.json").read_text())["data"]["substances"]:
        keys[("psychonautwiki_all", s["name"])] = (s["name"].replace(" ", "_"), s["name"])
    return keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("list_dir", type=pathlib.Path)
    ap.add_argument("raw", type=pathlib.Path, nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{ROOT / 'db' / 'cohort1.db'}?mode=ro", uri=True)
    # Held by a clinical route or as a seed: these have a reason already.
    held = {r[0] for r in db.execute(
        "SELECT chembl_id FROM molecules WHERE admission_reason != 'listed_only'")}
    keys = page_keys(args.raw)
    rows = list(csv.DictReader(open(args.list_dir / "lists_overlap.csv", encoding="utf-8")))
    section_of = {lst: (src, sec) for src, lsts in SOURCES.items() for lst, sec in lsts}

    entries = collections.defaultdict(dict)   # source -> chembl_id -> entry
    refused = collections.defaultdict(list)
    unreviewed = []
    for r in rows:
        if r["list"] not in section_of:
            continue
        ids = [i for i in r["chembl_parents"].split("|") if i]
        if not ids or any(i in held for i in ids):
            continue
        src, sec = section_of[r["list"]]
        slug, name = keys[(r["list"], r["name"])]
        tier = r["match_tier"]
        note = None
        # The read-over of identifier placements can decide one too.
        if tier not in IDENTIFIER_TIERS or len(ids) > 1 or (r["list"], r["name"]) in REVIEW:
            verdict = REVIEW.get((r["list"], r["name"]))
            if verdict is None:
                unreviewed.append((r["list"], r["name"], tier, "|".join(ids)))
                continue
            if verdict[0] == "refuse":
                refused[src].append({"name": name, "slug": slug, "chembl_ids": ids, "reason": verdict[1]})
                continue
            if verdict[0] == "correct":
                ids, note = [verdict[1]], verdict[2]
                if ids[0] in held:
                    continue
            else:
                note = verdict[1]
        cid = ids[0]
        e = entries[src].get(cid)
        if e is None:
            e = entries[src][cid] = {"chembl_id": cid, "name": name, "slug": slug,
                                     "section": sec, "placed_by": tier}
            if note:
                e["review"] = note
        elif sec and sec not in (e["section"] or ""):
            # One article in two categories is one listing.
            e["section"] = f"{e['section']}; {sec}"

    if unreviewed:
        print(f"{len(unreviewed)} placements need review:")
        for u in sorted(unreviewed):
            print("  ", *u, sep="\t")
        return 1

    text = POLICY.read_text(encoding="utf-8")
    pol = json.loads(text)
    sciwiki = pol["listings"]["sciwiki"]["molecules"]
    opened = {cid for src in entries for cid in entries[src]}
    kept = [e for e in sciwiki if e["chembl_id"] not in opened]
    for src in SOURCES:
        print(f"{src}: {len(entries[src])} entries, {len(refused[src])} refused")
    print(f"distinct parents: {len(opened)}; sci-wiki entries cited by an open list instead: "
          f"{len(sciwiki) - len(kept)}; sci-wiki entries kept: {len(kept)}")
    if not args.write:
        return 0
    pol["listings"]["sciwiki"]["molecules"] = kept
    for src in SOURCES:
        block = pol["listings"].setdefault(src, dict(SOURCE_META[src]))
        block["molecules"] = sorted(entries[src].values(), key=lambda e: e["name"].casefold())
        block["considered_and_not_listed"] = sorted(refused[src], key=lambda e: e["name"].casefold())
    # Only the listings block is rewritten; the rest of the file keeps its layout.
    start = text.index('\n  "listings": {') + 1
    end = text.index('\n  "', start + 1)
    text = text[:start] + render_listings(pol["listings"]) + ",\n" + text[end:]
    assert json.loads(text)["listings"] == pol["listings"]
    POLICY.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
