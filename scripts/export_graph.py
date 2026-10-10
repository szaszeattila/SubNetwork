"""Export db/subnetwork.db into viz/legacy/graph.data.js for the network viewer.

Writes a plain `const GRAPH_DATA = {...}` JS file (not JSON fetched via XHR)
so viz/index.html can load it with a <script src> tag and work straight off
`file://` with no local server.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "subnetwork.db"
OUT_PATH = Path(__file__).parent.parent / "viz" / "legacy" / "graph.data.js"

# Search-only names, keyed by identity rather than the displayed label.
# Reviewed against ChEMBL 37 molecule_synonyms for these exact ChEMBL IDs;
# THC/CBD and the delta spellings are readable forms of its delta-9-thc and
# (-)-cbd synonyms. Keep this small: combination products and other isomers
# are not aliases for a molecule. These never affect ingestion or evidence.
MOLECULE_ALIASES = {
    "CHEMBL465": ["THC", "Tetrahydrocannabinol", "Delta-9-THC",
                  "Delta 9 THC", "Δ9-THC", "Delta-9-tetrahydrocannabinol",
                  "Marinol", "Syndros"],
    "CHEMBL190461": ["CBD", "Epidiolex", "Epidyolex"],
    "CHEMBL113": ["Guaranine", "NoDoz", "Vivarin"],
    "CHEMBL431770": ["Nourianz"],
    "CHEMBL799": ["Pletal"],
    "CHEMBL628": ["Oxpentifylline", "Trental"],
    "CHEMBL636": ["Exelon"],
    "CHEMBL972": ["Emsam"],
    "CHEMBL54": ["Haldol"],
    "CHEMBL42": ["Clozaril", "Fazaclo", "Versacloz"],
    "CHEMBL741": ["Lamictal"],
    "CHEMBL932": ["Persantine"],
    "CHEMBL1520": ["Levitra", "Vivanza"],
    "CHEMBL659": ["Galanthamine", "Reminyl"],
}

# target_dictionary.target_type -> the viewer-facing tier name, used both by
# resolve_groups' output and by the viewer to decide how to draw a hull.
TARGET_TYPE_TIERS = {
    "PROTEIN COMPLEX": "complex",
    "PROTEIN COMPLEX GROUP": "complex_group",
}


def resolve_groups(complexes):
    """Resolve ChEMBL's raw complex/complex-group records into the disjoint
    set of hulls the canvas can actually draw.

    complexes: a list of dicts with keys chembl_id, name, target_type,
    n_components, wikipedia_url, members (a list/set of target node ids,
    e.g. "tgt_12").

    A node can only sit inside one hull, but ChEMBL's own complex records
    overlap: CHEMBL2094124 "Glutamate [NMDA] receptor" is a 7-member
    PROTEIN COMPLEX GROUP ("subunit composition is unclear") whose GRIN1/
    GRIN2A and GRIN1/GRIN2B pairs are *also* each asserted, precisely, as
    their own PROTEIN COMPLEX (CHEMBL1907604, CHEMBL1907603). Silently
    dropping the two precise dimers would throw away the one thing ChEMBL is
    actually sure of; silently keeping all three would draw three overlapping
    hulls over four nodes. The rule below is what makes the choice
    deterministic instead of "whichever happened to be inserted last":

    1. Sort candidates by (member count DESC, chembl_id ASC) - the largest,
       most-inclusive assembly is considered first, and ties break on the
       identifier rather than insertion order.
    2. Walk them in that order. A candidate whose member set is a *subset* of
       an already-kept group's is absorbed: it is not drawn as its own hull,
       but is recorded on the keeper's `absorbed` list so the precise
       sub-complex ChEMBL does assert is still carried along rather than
       discarded outright.
    3. Otherwise keep it, but drop any member already claimed by an earlier
       kept group - a partial overlap. None occurs in this database (every
       real overlap here is a clean subset), but the rule has to be total:
       an undefined case would make the output depend on dict/set iteration
       order. If removing claimed members leaves fewer than two, the
       candidate is dropped entirely rather than kept as a false singleton.
    4. Asserted at the end: no target id sits in two kept groups' member
       lists, so the canvas never has to choose which hull to draw a node
       inside.
    """
    ordered = sorted(complexes, key=lambda c: (-len(c["members"]), c["chembl_id"]))
    kept = []
    claimed = set()
    for candidate in ordered:
        members = set(candidate["members"])
        absorbed_into = next(
            (k for k in kept if members <= k["_member_set"]), None
        )
        if absorbed_into is not None:
            absorbed_into["absorbed"].append({
                "chembl_id": candidate["chembl_id"],
                "name": candidate["name"],
                "target_type": candidate["target_type"],
                "wikipedia_url": candidate["wikipedia_url"],
                "members": sorted(members),
            })
            continue

        remaining = members - claimed
        if len(remaining) < 2:
            continue
        kept.append({
            "chembl_id": candidate["chembl_id"],
            "name": candidate["name"],
            "target_type": candidate["target_type"],
            "tier": TARGET_TYPE_TIERS[candidate["target_type"]],
            "n_components": candidate["n_components"],
            "wikipedia_url": candidate["wikipedia_url"],
            "_member_set": remaining,
            "members": sorted(remaining),
            "absorbed": [],
        })
        claimed |= remaining

    seen = set()
    for group in kept:
        for member in group["members"]:
            assert member not in seen, (
                f"{member} claimed by more than one kept group - resolve_groups "
                "must leave every target in at most one hull"
            )
            seen.add(member)

    kept.sort(key=lambda g: (-len(g["members"]), g["chembl_id"]))
    for group in kept:
        del group["_member_set"]
    return kept


def build_graph(con: sqlite3.Connection) -> dict:
    con.row_factory = sqlite3.Row

    nodes = []
    for m in con.execute("SELECT * FROM molecules ORDER BY id"):
        nodes.append(
            {
                "id": f"mol_{m['id']}",
                "type": "molecule",
                "label": m["name"],
                "aliases": MOLECULE_ALIASES.get(m["chembl_id"], []),
                "chembl_id": m["chembl_id"],
                "pubchem_cid": m["pubchem_cid"],
                "iupac_name": m["iupac_name"],
                "molecular_formula": m["molecular_formula"],
                "molecular_weight": m["molecular_weight"],
                "smiles": m["smiles"],
                "wikipedia_url": m["wikipedia_url"],
            }
        )
    for t in con.execute("SELECT * FROM targets ORDER BY id"):
        nodes.append(
            {
                "id": f"tgt_{t['id']}",
                "type": "target",
                "label": t["gene_symbol"],
                "protein_name": t["protein_name"],
                "uniprot_accession": t["uniprot_accession"],
                "organism": t["organism"],
                "expressed_in_brain": t["expressed_in_brain"],
                "expression_note": t["expression_note"],
                "wikipedia_url": t["wikipedia_url"],
            }
        )

    edges = []
    for i in con.execute("SELECT * FROM interactions ORDER BY id"):
        sources = []
        for row in con.execute(
            """
            SELECT sources.name AS name,
                   interaction_sources.external_ref AS external_ref,
                   interaction_sources.citation_url AS citation_url,
                   interaction_sources.citation_text AS citation_text,
                   interaction_sources.citation_kind AS citation_kind,
                   interaction_sources.role AS role
            FROM interaction_sources
            JOIN sources ON sources.id = interaction_sources.source_id
            WHERE interaction_sources.interaction_id = ?
            -- Binding first, then functional, then bare annotations: the
            -- viewer lists them in this order and the measurement a
            -- displayed value came from should lead.
            ORDER BY CASE interaction_sources.role
                         WHEN 'binding' THEN 0
                         WHEN 'functional' THEN 1
                         ELSE 2
                     END,
                     sources.name
            """,
            (i["id"],),
        ):
            sources.append({
                "name": row["name"],
                "external_ref": row["external_ref"],
                "citation_url": row["citation_url"],
                "citation_text": row["citation_text"],
                "citation_kind": row["citation_kind"],
                "role": row["role"],
            })

        # Every individual measurement behind the two pooled values. Ordered
        # binding-first, counted-first, then ascending by value: the reader
        # sees the spread the median came from, with any excluded row last.
        measurements = []
        for row in con.execute(
            """
            SELECT sources.name AS name,
                   measurements.role AS role,
                   measurements.affinity_type AS affinity_type,
                   measurements.value AS value,
                   measurements.units AS units,
                   measurements.counted AS counted,
                   measurements.external_ref AS external_ref,
                   measurements.citation_url AS citation_url,
                   measurements.citation_text AS citation_text,
                   measurements.data_validity_note AS data_validity_note,
                   measurements.assay_description AS assay_description
            FROM measurements
            JOIN sources ON sources.id = measurements.source_id
            WHERE measurements.interaction_id = ?
            ORDER BY CASE measurements.role WHEN 'binding' THEN 0 ELSE 1 END,
                     measurements.counted DESC,
                     measurements.value
            """,
            (i["id"],),
        ):
            measurements.append({
                "name": row["name"],
                "role": row["role"],
                "affinity_type": row["affinity_type"],
                "value": row["value"],
                "units": row["units"],
                "counted": bool(row["counted"]),
                "external_ref": row["external_ref"],
                "citation_url": row["citation_url"],
                "citation_text": row["citation_text"],
                "data_validity_note": row["data_validity_note"],
                "assay_description": row["assay_description"],
            })

        edges.append(
            {
                "id": f"int_{i['id']}",
                "from": f"mol_{i['molecule_id']}",
                "to": f"tgt_{i['target_id']}",
                "action_type": i["action_type"],
                "mechanism_of_action": i["mechanism_of_action"],
                "is_primary_mechanism": bool(i["is_primary_mechanism"]),
                "binding_value": i["binding_value"],
                "binding_type": i["binding_type"],
                "binding_units": i["binding_units"],
                "n_measurements": i["n_measurements"],
                "functional_value": i["functional_value"],
                "functional_type": i["functional_type"],
                "functional_units": i["functional_units"],
                "functional_n_measurements": i["functional_n_measurements"],
                "sources": sources,
                "measurements": measurements,
            }
        )

    # Complex membership: which target nodes ChEMBL asserts sit inside one
    # physical assembly (see target_complexes/target_complex_members in
    # schema.sql, and load_target_complexes in build_db.py for how they're
    # populated). Resolved through resolve_groups so overlapping ChEMBL
    # records - the NMDA dimers nested inside the 7-member NMDA complex
    # group - become the disjoint set of hulls a canvas can actually draw.
    gene_symbol_by_node = {}
    members_by_complex = {}
    for row in con.execute(
        """
        SELECT tcm.complex_chembl_id AS complex_chembl_id,
               t.id AS target_id, t.gene_symbol AS gene_symbol
        FROM target_complex_members tcm
        JOIN targets t ON t.id = tcm.target_id
        """
    ):
        node_id = f"tgt_{row['target_id']}"
        gene_symbol_by_node[node_id] = row["gene_symbol"]
        members_by_complex.setdefault(row["complex_chembl_id"], []).append(node_id)

    complexes = [
        {
            "chembl_id": row["chembl_id"],
            "name": row["name"],
            "target_type": row["target_type"],
            "n_components": row["n_components"],
            "wikipedia_url": row["wikipedia_url"],
            "members": members_by_complex.get(row["chembl_id"], []),
        }
        for row in con.execute(
            "SELECT chembl_id, name, target_type, n_components, wikipedia_url"
            " FROM target_complexes"
        )
    ]

    def by_gene_symbol(node_ids):
        return sorted(node_ids, key=lambda n: gene_symbol_by_node.get(n, n))

    groups = [
        {
            "id": f"grp_{group['chembl_id']}",
            "chembl_id": group["chembl_id"],
            "name": group["name"],
            "target_type": group["target_type"],
            "tier": group["tier"],
            "n_components": group["n_components"],
            "wikipedia_url": group["wikipedia_url"],
            "members": by_gene_symbol(group["members"]),
            "absorbed": [
                {
                    "chembl_id": a["chembl_id"],
                    "name": a["name"],
                    "target_type": a["target_type"],
                    "wikipedia_url": a["wikipedia_url"],
                    "members": by_gene_symbol(a["members"]),
                }
                for a in group["absorbed"]
            ],
        }
        for group in resolve_groups(complexes)
    ]

    return {"nodes": nodes, "edges": edges, "groups": groups}


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        graph = build_graph(con)
    finally:
        con.close()

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text("const GRAPH_DATA = " + json.dumps(graph, indent=2) + ";\n")
    n_measurements = sum(len(e["measurements"]) for e in graph["edges"])
    print(
        f"Wrote {OUT_PATH} ({len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges, {n_measurements} measurements, "
        f"{len(graph['groups'])} complex groups)"
    )


if __name__ == "__main__":
    main()
