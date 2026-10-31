#!/usr/bin/env python3
"""Name -> InChIKey through PubChem, for the wiki names compare.py could not
place by ChEMBL name or FDA UNII. Writes pubchem_cache.json after every name,
so a run can be stopped and resumed.

This is a lookup **by name**, which invariant 15 forbids for anything that
enters the database. It is allowed here only because nothing here does: the
result is a read-only comparison, and every PubChem match is labelled low
confidence in comparison.csv. Eight PubChem matches were wrong on review
(REJECTED in placing.py).

PubChem throttles hard: after a burst it answers 429 to every request for
well over ten minutes. This goes at under one request a second and stops after
five consecutive 429s rather than retrying into the block.

    python3 analysis/wiki_comparison/compare.py      # writes need_pubchem.json
    python3 analysis/wiki_comparison/pubchem_lookup.py
    python3 analysis/wiki_comparison/compare.py      # reads the cache
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / "pubchem_cache.json"
URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/property/InChIKey/JSON"


def main() -> int:
    names = json.loads((HERE / "need_pubchem.json").read_text())
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [n for n in names if n not in cache]
    print(f"{len(todo)} names to look up")
    strikes = 0
    for i, name in enumerate(todo):
        while True:
            try:
                with urllib.request.urlopen(URL.format(urllib.parse.quote(name, safe="")), timeout=10) as r:
                    props = json.load(r)["PropertyTable"]["Properties"]
                cache[name] = sorted({p["InChIKey"] for p in props if "InChIKey" in p})
                strikes = 0
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 404):      # PubChem knows no such name
                    cache[name] = []
                    strikes = 0
                    break
                strikes += 1
                print(f"HTTP {e.code} on {name!r}, strike {strikes}", flush=True)
                if strikes >= 5:
                    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
                    sys.exit("throttled by PubChem; stopping. Rerun later to resume.")
                time.sleep(60)
            except OSError as e:
                print(f"network error on {name!r}: {e}; left for a later run", flush=True)
                break
        CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
        if i % 50 == 0:
            print(f"{i}/{len(todo)}", flush=True)
        time.sleep(1.2)
    print(f"done: {sum(1 for n in names if cache.get(n))} of {len(names)} names resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
