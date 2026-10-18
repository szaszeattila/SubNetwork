# Reproducing the catalogue from a fresh clone

Everything the page opens is generated, and none of it is in git. A fresh
clone has the code, the two policies in `config/`, the pinned MeSH scope
classification, and `config/cohort1_label_status.json`, what DailyMed said
about the labels behind ChEMBL's approvals (D23), committed so the build never
has to ask. It does not have the ChEMBL release, the database, the
backfills' caches or the exported payload. This document is the path from
the clone to a page that opens. It was written on 2026-10-10. The download
location and checksum were checked against EBI's server that day.

## What you need

- **Python 3.10 or later**, with `pip install -r requirements.txt`.
  `requests` is needed by the network backfills. `parasail` is needed only by
  the orthologue backfill. The PDF renderer's two packages are needed by no
  step here.
- **Node 21 or later**, for the viewer tests and the similarity harness.
  `node --test "tests/*.test.mjs"` relies on Node expanding the glob itself,
  and Node 21 is the first version that does. No npm packages are needed:
  the page vendors vis-network.
- **About 36 GB of free disk** for the ChEMBL download (5.8 GB) and the
  extracted database (30.5 GB). You can delete the archive after checking it.
- **Network access** for the backfills, and nothing else. The build itself
  reads only local files.
- **PostgreSQL's `pg_restore`**, for the DrugCentral backfill only, which
  reads two plain tables out of DrugCentral's dump with it; no server and no
  RDKit are needed. Any recent PostgreSQL client will do (the dump is
  PostgreSQL 16's custom format; 18.6 reads it). Without root, a conda env
  from conda-forge is enough: `conda create -p <dir> -c conda-forge
  postgresql`, then put `<dir>/bin` on `PATH` or set `PG_RESTORE`. To query
  the whole dump, it restores into PostgreSQL with the `rdkit` extension
  (conda-forge's `rdkit-postgresql`).

## 1. Download ChEMBL 37

The build reads ChEMBL 37's SQLite release and the files in `config/`, and it
never falls back to another release. Use the release's own directory. Do not use
`latest/`, which will point at a newer release.

```bash
cd /somewhere/with/space
curl -O https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/chembl_37_sqlite.tar.gz
curl -O https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/checksums.txt
grep chembl_37_sqlite.tar.gz checksums.txt | sha256sum -c -
tar -xzf chembl_37_sqlite.tar.gz
```

The archive's sha256 is
`33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281`.
It is 5,764,252,857 bytes. The extracted file is
`chembl_37/chembl_37_sqlite/chembl_37.db`, 30,480,314,368 bytes, which is the
size this project's analysis manifests record.

The code looks for that file at
`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db` (that is where it
lives on the machine it was built on). Anywhere else, point the environment
variable at it:

```bash
export CHEMBL_SQLITE_PATH=/somewhere/with/space/chembl_37/chembl_37_sqlite/chembl_37.db
```

The same path also appears in `config/cohort1_selection.json` under
`pinned_inputs`. There it is a record only: no code reads it, and editing it
would change the policy file's recorded hash without changing the build.
ChEMBL is always opened read-only.

## 2. Build, backfill, export

Run these from the repository root, in this order. A rebuild wipes every
backfill, so each one is rerun after it.

```bash
python3 scripts/build_cohort.py                      # ~20 s, ChEMBL only
python3 scripts/resolve_cohort_trials.py             # ClinicalTrials.gov, ~20 s
python3 scripts/resolve_cohort_protein_class.py      # offline
python3 scripts/resolve_cohort_approved_elsewhere.py # offline
python3 scripts/resolve_cohort_classes.py            # offline
python3 scripts/resolve_cohort_pharm_actions.py      # MeSH, FDA UNII, Wikidata, a few minutes
python3 scripts/resolve_cohort_mesh_structure.py     # MeSH, FDA UNII, ~35 s
python3 scripts/resolve_cohort_gtopdb_actions.py     # GtoPdb 2026.3.1, see below
python3 scripts/resolve_cohort_orthologues.py        # UniProt, ~2 min cold, needs parasail
python3 scripts/resolve_cohort_wikipedia.py          # Wikidata and Wikipedia; after the orthologues
python3 scripts/resolve_cohort_drugcentral.py        # DrugCentral dump, needs pg_restore, see below
python3 scripts/export_cohort.py                     # ~6 s, writes viz/
```

Then open `viz/index.html` in a browser. No server is needed.

The build checks itself (15 validation checks) and replaces nothing unless
all of them pass. Each backfill downloads what it needs into `db/cache/` the
first time it runs, and reuses it after that. Each takes `--dry-run`.

## 3. Check it

```bash
python3 -m unittest discover -s tests
node --test "tests/*.test.mjs"
python3 scripts/cohort_report.py --check-status
node analysis/similarity_harness/evaluate.mjs
```

`--check-status` compares your build with the **Status** block in
`CLAUDE.md`, which was generated from the published build. The build step
reads only ChEMBL 37 and versioned files, so its counts (entries, targets,
claims, observations, tiers) should match exactly. Figures that come from a
backfill may differ, for the reasons below, and `--check-status` fails on any
figure that differs, so read what it prints rather than its exit code. Some
tests skip rather than fail
without a build or without ChEMBL: the ones that read the ChEMBL file, the
Status check and the harness floor.

## What will not reproduce exactly

The build is pinned. Most backfills read a live service or a "latest" file,
so a rerun months later reads a newer one. Each records the sha256 of what it
downloaded in `build_manifest`, so two builds can be compared. None refuses a
newer file, except GtoPdb.

| Backfill | What it reads | Why it can differ |
| --- | --- | --- |
| trials | ClinicalTrials.gov API | trial statuses change |
| pharm actions | MeSH `desc2026` and `supp2026`, FDA UNII, Wikidata | Wikidata items change, and its answers are cached in `db/cache/wikidata/`; UNII is served only as "latest" |
| mesh structure | MeSH `desc2026` and `supp2026`, FDA UNII | as above |
| wikipedia | Wikidata, Wikipedia | articles and items change |
| orthologues | UniProt's reviewed human proteome | streamed from the current release, not 2026_03 |
| **gtopdb** | `guidetopharmacology.org/DATA/` | **refuses any release but 2026.3.1**, see below |
| **drugcentral** | `Drugcentral_2026-09-25.pgdump` (1.4 GB) | **refuses any file but that one**, by sha256 `5afea88f…32dc`; download it from `unmtid-dbs.net/download/` into `db/cache/drugcentral/` |

**GtoPdb is the one that can stop you.** It serves only its latest release, at
a fixed address. The backfill reads the version off each file's first line,
and refuses anything other than 2026.3.1, because its `ACTION_MAP` was reviewed
against that release. Once GtoPdb publishes a newer release, a fresh clone
cannot download 2026.3.1 from that address. To get past this you have two
choices:

- obtain `interactions.csv` and `ligands.csv` from release 2026.3.1 and place
  them in `db/cache/gtopdb/2026.3.1/`. Their download page showed no archive of
  past releases on 2026-10-10, so this means asking GtoPdb, or someone who
  has the cache; or
- review `ACTION_MAP` against the new release and bump `GTOPDB_VERSION`. That
  is a change to the project, not a reproduction.

The files are cached exactly as GtoPdb serves them, so a copy from anyone can
be checked against the sha256 the manifest records. For 2026.3.1 (published
2026-10-12) these are `c1b81895…1ffa1` for `interactions.csv` and
`bc858e6a…7a2` for `ligands.csv`; the full values are in the `gtopdb_actions`
key of `build_manifest`.

GtoPdb said in September 2026 that anonymous downloads will end. If that
happens, the backfill will need whatever access GtoPdb then requires.

## What is not covered

The legacy seed pipeline (`scripts/build_db.py`) reads six live sources and
is not reproducible in this sense; see
[LEGACY-PIPELINE.md](LEGACY-PIPELINE.md). The read-only analyses under
`analysis/` have their own READMEs, and read ChEMBL from the same file through
the same `CHEMBL_SQLITE_PATH`, except `analysis/probe/`, whose two dump scripts
name the default path directly.
