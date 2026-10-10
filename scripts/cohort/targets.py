"""Target identities, at the level ChEMBL asserts them (decision D06).

Four target types are claimable here: SINGLE PROTEIN, PROTEIN COMPLEX,
PROTEIN COMPLEX GROUP and PROTEIN FAMILY. Each keeps its own identity. A
family claim is never expanded into claims about its members, a complex is
never split into its subunits, and two target records that happen to share
components stay two records.

Components are loaded as *context* - so a complex can name what it contains -
and never as claims. Nothing here matches on a gene symbol or a name.
"""

from __future__ import annotations

import collections

from . import common

CLAIMABLE = ("SINGLE PROTEIN", "PROTEIN COMPLEX", "PROTEIN COMPLEX GROUP", "PROTEIN FAMILY")


def load(conn) -> dict[int, dict]:
    """tid -> target record, for every target in the release.

    The whole dictionary is ~15k rows and is needed by tid during the activity
    scan, so it is loaded once rather than queried per row.
    """
    targets = {}
    for row in conn.execute("""
        SELECT td.tid, td.chembl_id, td.pref_name, td.target_type,
               td.organism, td.tax_id
          FROM target_dictionary td
    """):
        targets[row["tid"]] = {
            "tid": row["tid"],
            "chembl_id": row["chembl_id"],
            "pref_name": row["pref_name"],
            "target_type": row["target_type"],
            "organism": row["organism"],
            "tax_id": row["tax_id"],
            "claimable": row["target_type"] in CLAIMABLE,
            "components": [],
        }
    for row in conn.execute("""
        SELECT tc.tid, cs.accession, cs.description, cs.component_type
          FROM target_components tc
          JOIN component_sequences cs ON cs.component_id = tc.component_id
         ORDER BY tc.tid, cs.accession
    """):
        t = targets.get(row["tid"])
        if t is not None and row["accession"]:
            t["components"].append({
                "accession": row["accession"],
                "description": row["description"],
                "component_type": row["component_type"],
            })
    for t in targets.values():
        t["n_components"] = len(t["components"])
    common.log(f"  targets: {len(targets)} records, "
               f"{sum(1 for t in targets.values() if t['claimable'])} claimable")
    return targets


def gene_symbols(conn, accessions: set[str]) -> dict[str, str]:
    """Accession -> gene symbol, for display only.

    Read from ChEMBL's own component synonyms on an exact accession join. This
    is a label on a component, never a way to match or merge targets
    (CLAUDE.md invariants 6 and 15).
    """
    out: dict[str, str] = {}
    if not accessions:
        return out
    for chunk in common.chunked(sorted(accessions)):
        q = ("SELECT cs.accession, cy.component_synonym "
             "FROM component_sequences cs "
             "JOIN component_synonyms cy ON cy.component_id = cs.component_id "
             f"WHERE cs.accession IN ({','.join('?' * len(chunk))}) "
             "  AND cy.syn_type = 'GENE_SYMBOL' "
             "ORDER BY cs.accession, cy.component_synonym")
        for row in conn.execute(q, chunk):
            out.setdefault(row["accession"], row["component_synonym"])
    return out


def protein_classes(conn, accessions: set[str]) -> dict[str, str]:
    """Accession -> ChEMBL's protein classification at levels 1 and 2.

    Each class a component is filed under is written as "level 1 > level 2"
    (e.g. "Ion channel > Ligand-gated ion channel"), and a component filed
    under several is '|'-joined, sorted. Deeper levels are left out: the one
    thing this is read for is whether a complex is made of ion-channel
    subunits, which the viewer lays out as one unit.

    A drawing hint and nothing else. It is never a matching or merging key,
    never evidence and never a route for moving a claim - and it is never read
    as *which* targets belong together, which ChEMBL's classification tree
    gets wrong (CLAUDE.md: it files CACNB2, which co-assembles with CACNA1C,
    under "Auxiliary transport protein"). Membership is still the accession.
    """
    out: dict[str, str] = {}
    if not accessions:
        return out
    tree = {r["protein_class_id"]: (r["parent_id"], r["class_level"], r["pref_name"])
            for r in conn.execute("SELECT protein_class_id, parent_id, class_level,"
                                  " pref_name FROM protein_classification")}

    def path(cid):
        chain, seen = [], set()
        while cid is not None and cid in tree and cid not in seen:
            seen.add(cid)
            parent, level, name = tree[cid]
            if level in (1, 2) and name:
                chain.append((level, name))
            cid = parent
        return " > ".join(name for _, name in sorted(chain))

    per = collections.defaultdict(set)
    for chunk in common.chunked(sorted(accessions)):
        q = ("SELECT cs.accession, cc.protein_class_id "
             "FROM component_sequences cs "
             "JOIN component_class cc ON cc.component_id = cs.component_id "
             f"WHERE cs.accession IN ({','.join('?' * len(chunk))})")
        for row in conn.execute(q, chunk):
            p = path(row["protein_class_id"])
            if p:
                per[row["accession"]].add(p)
    return {acc: "|".join(sorted(paths)) for acc, paths in per.items()}
