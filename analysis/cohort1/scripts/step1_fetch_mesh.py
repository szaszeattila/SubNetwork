"""Step 1 - cache the MeSH tree numbers the CNS indication scope is defined on.

ChEMBL's ``drug_indication`` names a disease by MeSH descriptor id
(``mesh_id``, e.g. ``D010146``). A descriptor id alone says nothing about
where the disease sits in MeSH, so a scope defined as "nervous-system and
psychiatric disease" needs the descriptor-to-tree-number map. That map is
fetched once from the NLM MeSH SPARQL endpoint and cached, so every later
step runs offline and deterministically against the same snapshot.

Two sets are fetched:

* every descriptor carrying a tree number under a configured root
  (``C10``, ``F03``, ... - the scope's universe), and
* every descriptor id that actually appears in ``drug_indication``,
  looked up by exact identifier.

The second set is what membership is decided on. Looking descriptors up by
id, never by heading text, keeps this inside the project's rule that
external records are resolved by identifier and never by name
(CLAUDE.md invariant 15). Descriptor ids that the endpoint returns no tree
number for are written out as unresolved rather than dropped.

Output: ``cache/mesh_tree.tsv`` (descriptor_id, tree_number, label) and
``cache/mesh_unresolved.tsv``. Both are recorded in ``MANIFEST.json``.
"""

import collections
import json
import sys

import common

ENDPOINT = "https://id.nlm.nih.gov/mesh/sparql"
GRAPH = "http://id.nlm.nih.gov/mesh"
PAGE = 1000          # endpoint's maximum result page
BATCH = 150          # descriptor ids per VALUES lookup

PREFIXES = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>
"""


def sparql(query: str, post: bool = False) -> list[dict]:
    raw = common.http_get(ENDPOINT, {
        "query": PREFIXES + query,
        "format": "JSON",
        "inference": "false",
    }, accept="application/sparql-results+json", post=post)
    return json.loads(raw)["results"]["bindings"]


def descriptor_id(uri: str) -> str:
    return uri.rsplit("/", 1)[1]


def fetch_root(root: str) -> list[tuple[str, str, str]]:
    """Every (descriptor, tree number, label) at or below one tree root."""
    rows, offset = [], 0
    while True:
        bindings = sparql(f"""
SELECT ?d ?tn ?label
FROM <{GRAPH}>
WHERE {{
  ?d meshv:treeNumber ?t .
  ?t rdfs:label ?tn .
  ?d rdfs:label ?label .
  FILTER(langMatches(LANG(?label), "en"))
  FILTER(STR(?tn) = "{root}" || STRSTARTS(STR(?tn), "{root}."))
}}
ORDER BY ?tn ?d
LIMIT {PAGE} OFFSET {offset}
""")
        rows += [(descriptor_id(b["d"]["value"]), b["tn"]["value"], b["label"]["value"])
                 for b in bindings]
        if len(bindings) < PAGE:
            return rows
        offset += PAGE


def fetch_ids(ids: list[str]) -> list[tuple[str, str, str]]:
    """Tree numbers for an explicit list of descriptor ids, batched."""
    rows = []
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        values = " ".join(f"<http://id.nlm.nih.gov/mesh/{d}>" for d in chunk)
        bindings = sparql(f"""
SELECT ?d ?tn ?label
FROM <{GRAPH}>
WHERE {{
  VALUES ?d {{ {values} }}
  ?d meshv:treeNumber ?t .
  ?t rdfs:label ?tn .
  ?d rdfs:label ?label .
  FILTER(langMatches(LANG(?label), "en"))
}}
""", post=True)
        rows += [(descriptor_id(b["d"]["value"]), b["tn"]["value"], b["label"]["value"])
                 for b in bindings]
        common.log(f"    ids {i + len(chunk)}/{len(ids)} -> {len(rows)} tree numbers")
    return rows


def main() -> int:
    scope = common.load_config("cns_indication_scope.json")
    roots = sorted({r["tree"] for r in scope["roots_fetched"]})

    conn = common.chembl()
    used = [r[0] for r in conn.execute(
        "SELECT DISTINCT mesh_id FROM drug_indication "
        "WHERE mesh_id IS NOT NULL AND mesh_id <> '' ORDER BY mesh_id")]
    conn.close()
    common.log(f"  {len(used)} distinct mesh_id values in drug_indication")

    rows = set()
    failures = []
    for root in roots:
        try:
            got = fetch_root(root)
            rows.update(got)
            common.log(f"  root {root}: {len(got)} tree numbers")
        except RuntimeError as exc:
            failures.append({"kind": "root", "value": root, "error": str(exc)})
            common.log(f"  root {root}: FAILED {exc}")

    try:
        rows.update(fetch_ids(used))
    except RuntimeError as exc:
        failures.append({"kind": "ids", "value": "drug_indication mesh_ids", "error": str(exc)})
        common.log(f"  id lookup FAILED {exc}")

    common.CACHE.mkdir(parents=True, exist_ok=True)
    tree_path = common.CACHE / "mesh_tree.tsv"
    with open(tree_path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write("descriptor_id\ttree_number\tlabel\n")
        for d, tn, label in sorted(rows):
            fh.write(f"{d}\t{tn}\t{label}\n")

    resolved = {d for d, _, _ in rows}
    unresolved = [d for d in used if d not in resolved]
    unres_path = common.CACHE / "mesh_unresolved.tsv"
    with open(unres_path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write("descriptor_id\theading_in_chembl\n")
        conn = common.chembl()
        for d in unresolved:
            head = conn.execute(
                "SELECT mesh_heading FROM drug_indication WHERE mesh_id = ? LIMIT 1",
                (d,)).fetchone()
            fh.write(f"{d}\t{head[0] if head else ''}\n")
        conn.close()

    per = collections.Counter(d for d, _, _ in rows)
    common.log(f"  {len(rows)} descriptor/tree-number pairs, {len(per)} descriptors, "
               f"{len(unresolved)} of {len(used)} drug_indication ids unresolved")

    common.record_source("mesh", **{
        "name": "MeSH (Medical Subject Headings) tree numbers",
        "publisher": "U.S. National Library of Medicine",
        "url": ENDPOINT,
        "graph": GRAPH,
        "query": "descriptor treeNumber, current-year graph, inference=false",
        "access_status": "ok" if not failures else "partial",
        "failures": failures,
        "license": "Public domain (NLM MeSH is in the public domain; "
                   "see https://www.nlm.nih.gov/databases/download/terms_and_conditions.html)",
        "files": {
            "cache/mesh_tree.tsv": {"sha256": common.sha256(tree_path),
                                    "rows": len(rows)},
            "cache/mesh_unresolved.tsv": {"sha256": common.sha256(unres_path),
                                          "rows": len(unresolved)},
        },
    })
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
