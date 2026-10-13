# MeSH actions without PubChem

Read-only, and writes to neither database nor the viewer. It is the
measurement behind D22: whether the MeSH pharmacological actions that
`scripts/resolve_cohort_pharm_actions.py` used to reach through PubChem (route
A) could be read from each molecule's own MeSH record, and what each variant of
that route gains and loses against route A. The route adopted (B2, then the
stereoisomer-mixture rule R, then Wikidata) is the one the backfill now runs.
The findings are in
[docs/MESH-ACTIONS-ROUTE-B.md](../../docs/MESH-ACTIONS-ROUTE-B.md).

```bash
python3 analysis/mesh_route_b/wikidata_mesh.py db/cohort1.db wikidata_mesh.json
python3 analysis/mesh_route_b/compare.py db/cohort1.db [wikidata_mesh.json]
```

`compare.py` needs a database whose PubChem backfill completed, since route A
is read from its `mesh_pa` rows. After D22 no new build has one, so the
comparison stands as the record of the switch. For that run it was the
1,335-entry build of 2026-10-11. Everything else comes from the pinned files
under `db/cache/` (the MeSH 2026 descriptor and supplementary files, FDA's
UNII records) and from ChEMBL, read-only. `wikidata_mesh.py` is the one
network step. It asks Wikidata which MeSH ID sits on the item carrying each
ChEMBL ID, and writes the answers to the JSON file `compare.py` reads.
