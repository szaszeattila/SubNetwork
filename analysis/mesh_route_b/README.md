# MeSH actions without PubChem

Read-only. **Adopts nothing**, and writes to neither database nor the viewer.
It measures whether the MeSH pharmacological actions that
`scripts/resolve_cohort_pharm_actions.py` reaches through PubChem (route A)
could be read from MeSH itself, through the molecule's FDA UNII (route B), and
what each variant of route B gains and loses against route A. The findings and
the recommendation are in
[docs/MESH-ACTIONS-ROUTE-B.md](../../docs/MESH-ACTIONS-ROUTE-B.md).

```bash
python3 analysis/mesh_route_b/compare.py db/cohort1.db
```

The database must be one whose PubChem backfill completed, since route A is
read from its `mesh_pa` rows. Everything else comes from the pinned files
under `db/cache/` (the MeSH 2026 descriptor and supplementary files, FDA's
UNII records) and from ChEMBL, read-only. It makes no network request.
