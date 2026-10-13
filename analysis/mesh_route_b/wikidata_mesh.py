"""Wikidata as an identifier bridge ChEMBL ID -> MeSH ID (P486), measured.

Fetches, for every catalogue molecule, the MeSH IDs on the Wikidata item(s)
carrying its ChEMBL ID (P592), and caches the answer as JSON. Read-only on the
database. Run from the repository root:
    python3 analysis/mesh_route_b/wikidata_mesh.py db/cohort1.db wikidata_mesh.json

The answers feed analysis/mesh_route_b/compare.py. The backfill itself keeps
its own cache in a richer shape (with the Wikidata item), under db/cache/.
"""
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, "scripts")
import resolve_cohort_wikipedia as wiki  # noqa: E402

QUERY = """SELECT ?chembl ?mesh WHERE {
  VALUES ?chembl { %s }
  ?item wdt:P592 ?chembl .
  OPTIONAL { ?item wdt:P486 ?mesh . }
}"""

db, out = sys.argv[1], pathlib.Path(sys.argv[2])
cache = json.loads(out.read_text()) if out.exists() else {}
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
ids = [r[0] for r in conn.execute("SELECT chembl_id FROM molecules ORDER BY chembl_id")]
todo = [i for i in ids if i not in cache]
print(f"{len(ids)} molecules, {len(todo)} to ask")
for chunk in (todo[i:i + 50] for i in range(0, len(todo), 50)):
    body = wiki._wikidata_get(QUERY % " ".join(wiki.sparql_literal(c) for c in chunk))
    got = {c: [] for c in chunk}
    for b in body["results"]["bindings"]:
        c = b["chembl"]["value"]
        if "mesh" in b and b["mesh"]["value"] not in got[c]:
            got[c].append(b["mesh"]["value"])
    cache.update(got)
    out.write_text(json.dumps(cache, sort_keys=True))
print("with a MeSH id:", sum(1 for v in cache.values() if v),
      "| with two or more:", sum(1 for v in cache.values() if len(v) > 1))
