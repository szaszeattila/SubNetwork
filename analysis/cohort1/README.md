# Cohort 1 — clinical catalogue: analysis package

Everything behind [`docs/COHORT-REPORT.md`](../../docs/COHORT-REPORT.md): the
selection and tier rules, the scripts that apply them, the row-level outputs,
and the source manifest.

This is a **read-only report**. It opens ChEMBL 37 and `db/subnetwork.db` with
`mode=ro` and writes only under `analysis/cohort1/`. It does not change the
production schema, the seed list, the database, the graph export or the viewer,
and it does not adopt a selection policy.

The [September 12 annotation follow-up](followup/README.md) clarifies the report,
evaluates recoverable units and organism-format exclusions, and compares five
clinical policies across two molecule categories and three target bases. It
keeps the baseline evidence fixed. The only baseline metadata correction is
`evidence_exclusions.csv`'s retention flag, now matching which rows actually
appear in `measurements.csv.gz`; `step3_evidence.py` emits the corrected flag.

## Reproducing it

```bash
bash analysis/cohort1/scripts/run_all.sh
```

Or one step at a time, from `analysis/cohort1/`:

```bash
python3 scripts/step1_fetch_mesh.py    # network; caches cache/mesh_tree.tsv
python3 scripts/step2_candidates.py    # offline; the catalogue
python3 scripts/step3_evidence.py      # offline; claims and tiers  (~12 s)
python3 scripts/step4_tables.py        # offline; report_tables.json
python3 scripts/step5_validate.py      # offline; validation.csv
```

Unit tests for the analysis logic:

```bash
python3 -m unittest tests.test_cohort_report -v   # from the repository root
```

Requirements: python3 ≥ 3.10, standard library only. Environment overrides:

| Variable | Default | Purpose |
|---|---|---|
| `CHEMBL_SQLITE_PATH` | `/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db` | the pinned ChEMBL release |
| `SUBNETWORK_DB` | `db/subnetwork.db`, falling back to the main checkout when run from a worktree | only for the new-vs-existing target comparison; absent means "not assessed" |

Step 1 is the only networked step, and its output is cached, so steps 2–5 are
offline and deterministic. `cache/` is gitignored.

**Snapshot availability at the September 12 review:** the original MeSH cache
files are absent in this checkout. The saved outputs and manifest remain.
A full `run_all.sh` rerun would fetch a new MeSH snapshot; compare it rather
than treating it as the original September 7 cache. The follow-up reproduces
its scope comparisons offline using the exported `indication_scope.csv`.

## Configuration (versioned, machine-readable)

| File | What it fixes |
|---|---|
| `config/cns_indication_scope.json` | the CNS indication scope: MeSH roots, the descendant rule, every boundary class with its reason **and its counter-argument**, the cumulative variants, and the ATC rule with its flagged subtrees |
| `config/tier_rules.json` | measurement validity, endpoint classes, study identity, the three tiers and their reason codes, target-assignment specificity, conflict rules, threshold rules |
| `MANIFEST.json` | every external source: URL, retrieval date, checksum or size pin, access status, licence, and any recorded failure |

Changing a rule means editing the config and rerunning; no rule is hard-coded
in a script without a corresponding config entry.

## Join keys

Everything joins on two identifiers.

- **`parent_molregno`** — ChEMBL `molecule_hierarchy.parent_molregno`, falling
  back to the molecule's own `molregno`. One catalogue row per parent. Its
  `parent_chembl_id` is the human-readable form.
- **`target_chembl_id`** — ChEMBL `target_dictionary.chembl_id`.

A claim is `(parent_molregno, target_chembl_id, claim_role)`. A measurement
carries `activity_id`, which is unique in ChEMBL. A study is `study_key`
(`pmid:…` / `doi:…` / `patent:…` / `doc:…`).

```
candidates.csv ──parent_molregno──┬── candidate_atc_codes.csv
                                  ├── candidate_indications.csv ──mesh_id── indication_scope.csv
                                  ├── family_members.csv  (member_molregno = every salt/form)
                                  ├── molecule_evidence.csv
                                  ├── coverage_gaps.csv
                                  └── target_pairs.csv.gz ──target_chembl_id── observed_targets.csv
                                            │
   assessed_claims.csv.gz ──(parent_molregno, target_chembl_id, claim_role)──┤
             │                                                               │
             ├── claim_studies.csv.gz      (+ endpoint_class, study_key)
             ├── claim_thresholds.csv.gz   (+ endpoint_class)
             └── measurements.csv.gz       (activity_id; assay_chembl_id, doc_chembl_id, pubmed_id, doi)
```

`seed_membership.csv` and `seed_report.csv` join to `candidates.csv` on
`parent_chembl_id`, and carry the seeded `seed_chembl_id` separately — the two
differ for theophylline.

## Outputs

`.gz` files are ordinary CSVs; `pandas.read_csv` opens them directly, or
`gzip.open(path, "rt")`.

### Catalogue

| File | Rows | One row per | Key columns |
|---|---|---|---|
| `candidates.csv` | 2 245 | catalogue molecule (parent) | `route_atc_n`, `route_cns_indication`, `route_combination`, `atc_level5_codes`, `atc_boundary_flags`, `family_max_phase_label`, `cns_ind_max_phase_label`, `withdrawn_any_family`, `molecule_type`, `structure_type` |
| `candidate_atc_codes.csv` | 605 | (candidate, ATC level-5 code) | `carrier_molregno` — which family member carried the code, `boundary_flag` |
| `candidate_indications.csv` | 8 850 | (candidate, `drugind_id`) | `mesh_id`, `efo_id`, `max_phase_for_ind`, `in_core_scope`, `scope_classes`, `core_tree_numbers` |
| `family_members.csv` | 3 668 | (parent, family member) | `is_parent`, `member_carries_atc_n`, `member_carries_scoped_indication` — the parent/salt audit trail |
| `indication_scope.csv` | 2 869 | MeSH descriptor | `tree_numbers`, `in_core_scope`, `scope_classes`, `drug_indication_rows`, `distinct_parent_molecules` |
| `route_arithmetic.csv` | 13 | rule stage | `atc_n_only`, `cns_indication_only`, `both_routes`, `union`, `arithmetic_holds` |
| `stage_breakdown.csv` | 61 | (subset, phase basis, stage) | `phase_basis` distinguishes molecule-level `family_max_phase` from indication-level `max_phase_for_ind` |

### Evidence

| File | Rows | One row per | Key columns |
|---|---|---|---|
| `assessed_claims.csv.gz` | 138 509 | molecule–target claim | `tier`, `tier_reasons`, `curated_support`, `multiple_study_support`, `tier_human_direct`, `assignment_specificity`, `claim_target_specificity`, `conflict_*`, `example_source_records` |
| `target_pairs.csv.gz` | 126 196 | molecule–target pair | `support_routes` (`curated_only` / `multiple_study_only` / `both` / `neither`) — this is where the two Supported routes intersect |
| `claim_studies.csv.gz` | 106 380 | (claim, endpoint class, study) | `provenance_class`, `counts_toward_multi_study`, `n_measurements_in_study` |
| `claim_thresholds.csv.gz` | 51 881 | (claim, endpoint class) | `median_nM_log_pooled`, `median_pass_{1,10,100,300}uM`, `any_pass_…` |
| `measurements.csv.gz` | 310 719 | ChEMBL `activity_id` | `status` (`included_exact` / `retained_as_bound` / `excluded_*`), `specificity`, `study_key`, `data_validity_comment`, `potential_duplicate`, `assay_description` |
| `molecule_evidence.csv` | 2 245 | catalogue molecule | claim counts per tier, `n_pairs_both_routes`, `any_qualifying_human_target_claim`, `evidence_status` |
| `observed_targets.csv` | 4 885 | target | `n_molecules`, `n_supported`, `n_human_direct`, `target_family_l1/l2`, `target_accessions` |
| `coverage_gaps.csv` | 361 | catalogue molecule with no assessable evidence | `gap_kind`, `detail` |
| `evidence_exclusions.csv` | 9 | exclusion reason | `n_activity_rows`, `retained_in_output` |
| `family_coverage.csv` | 48 | ChEMBL protein-class level 1 | `n_targets_not_in_current_graph` |
| `threshold_sensitivity.csv` | 104 | (threshold, basis, endpoint class) | claims and molecules passing under each aggregation rule |
| `tier_distribution.csv` | 16 | (role, basis, tier) | `basis` separates all assessed evidence from direct-human-only |
| `seed_report.csv` | 28 | existing seed molecule | membership, admission/exclusion reason, evidence status |
| `validation.csv` | 11 | validation check | `result`, `detail` |
| `report_tables.json` | — | — | every number the report quotes, under the key it is quoted by |

### Caveat carried by every evidence file

Coverage is **ChEMBL 37 only**. "No eligible evidence found" means none in
ChEMBL 37 — not none in the literature, and not none across the project's six
production sources. PDSP, BindingDB, DGIdb, GtoPdb, HPA and B3DB were not
assessed here; see the report's coverage-limits section.
