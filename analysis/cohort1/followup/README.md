# Clinical-cohort annotation follow-up

Read-only evaluation of the 11 Zotero questions, excluded evidence and concrete
clinical import choices. The narrative is in
[COHORT-FOLLOWUP.md](../../../docs/COHORT-FOLLOWUP.md); the main report incorporates
the definitions, corrections and policy comparison. No policy is implemented.

## Reproduce

From the repository root, using Python 3.10 or later:

```bash
python3 analysis/cohort1/followup/analyze.py
python3 -m unittest tests.test_cohort_report tests.test_cohort_followup -v
python3 analysis/cohort1/followup/write_summary.py
```

The analysis uses only the Python standard library, ChEMBL 37 opened with
`mode=ro`, and the original exports in `analysis/cohort1/out/`. It writes only
`followup/out/`. The narrative builder updates `docs/COHORT-FOLLOWUP.md` and
section 6 of `docs/COHORT-REPORT.md`; rerun it after the analysis.

PDF rendering requires `reportlab`, `markdown-it-py`, Noto Sans/Serif and
DejaVu Sans Mono fonts. The task used the Codex bundled Python runtime with
ReportLab 4.x and markdown-it-py 4.2.0:

```bash
python3 analysis/cohort1/followup/build_pdf.py
```

The renderer supports `--input` and `--output` for a review draft. It preserves
all table columns, splitting the wide seed table into two readable tables
sharing the Seed column. External web links remain clickable. Relative
project references remain readable text. Inspect rendered pages after edits.

## Rules and provenance

- `rules.json` versions the unit allowlists, chemical-form assumptions,
  membership policies and three human target-assignment bases.
- `organism_review.json` records a manual review of all 22 assay descriptions
  behind the 36 protein-assigned organism-format records. It does not claim
  independent verification of every original experimental method.
- `out/summary.json` pins the analysis inputs by SHA-256, and ChEMBL by release
  and byte size. It records relation counts and the data validations.
- `protected-before.json` fingerprints the seven production artifacts as they
  stood before this task. A later intentional production rebuild will cause
  the preservation check to fail against this historical fingerprint; that
  must be distinguished from an unintended write by this analysis.
- The original raw MeSH cache is absent in this checkout. The saved descriptor
  classification is the follow-up's ontology input. No current MeSH fetch
  was substituted. This reproduces the scope comparisons, not the missing
  cache bytes or every step of the original retrieval process.

Experimental support is evaluated per `(parent_molregno, target_chembl_id,
role)`, with replication counted within one `endpoint_class`. Source study
keys retain the original report's DOI/PMID/deposit handling. Source flags
remain visible; different publications still do not prove independence.

No family or complex is expanded into components. Experimental evidence is
filtered by species, direct assignment and absence of a variant *before*
its tier is computed. Supported curated human mechanisms are accepted at
their original target level and remain separate role-specific claims.

## Outputs

All `.gz` files are ordinary gzip-compressed CSVs. Keys are source-native
ChEMBL identifiers and the baseline chemical-parent identifier.

| File | Grain and use |
|---|---|
| `unit_audit.csv` | All 2,714 excluded-unit measurements, original values/units, proposed conversion, reason, measured-form identity and molecular weight |
| `unit_summary.csv` | Unit/recovery-class/reason counts |
| `unit_claim_changes.csv` | Affected claim under each conversion scenario and assignment basis, before/after tier and exact-measurement count |
| `unit_recovery_summary.csv` | Four scenario/basis summaries; the mass scenario includes the concentration-only scenario |
| `unit_threshold_changes.csv` | Before/after log median and threshold pass per affected claim/endpoint/threshold; not unique claim counts |
| `organism_context.csv.gz` | All 21,999 omitted organism-format records with assay, target, published value, standard value and study provenance |
| `organism_protein_assigned.csv` | The 36 protein/family/complex-assigned records |
| `organism_reviewed.csv` | Those 36 records with the description review and contextual-retention recommendation |
| `organism_review_summary.csv` | Context-class counts |
| `organism_summary.csv` | Target-type and assignment counts across all 21,999 |
| `organism_unsafe_pooling_diagnostic.csv` | Consequences of naively pooling the 31 protein-assigned exact nM values; explicitly not proposed tier changes |
| `known_bad_excluded_records.csv` | Four known-bad original activity rows, retained for audit and excluded from all proposed evidence |
| `policy_membership.csv` | Every admitted candidate under five policies and two molecule-category choices |
| `policy_seed_membership.csv` | All 28 seeds under each of the ten membership choices, with admission/exclusion reasons |
| `policy_comparison.csv` | 60 combinations: ten membership choices, three target bases and baseline/concentration-recovered evidence |
| `evidence_by_basis.csv.gz` | Eligible claim and tier under each target basis and conversion scenario; join to policy membership on parent ID |
| `scope_comparison.csv` | Core, oncology, pain, combined oncology/pain and widest unions; evidence for added molecules is not assessed |
| `validation.csv` | Eight data checks, including exact baseline tier reproduction and unchanged production fingerprints |
| `pdf_validation.json` | Delivered report and Markdown hashes, 21-page visual check, text-boundary checks, and preservation of the original PDF |

## Deliberate limits

Mass conversion is conditional on the publication's material basis. No
mass-derived value is proposed for automatic import. Organism observations
are retained as context, without mixing exposure, occupancy or physiology
into an in-vitro potency median. Potentially mislabelled cell assays remain
review candidates. No outside-baseline cohort, supplementary pharmacology
source, BBB dataset, clinical approval verification or graph-performance
benchmark is included.

The original report and Zotero annotation export are preserved in
[`docs/archive/cohort-report-2026-09-12/`](../../../docs/archive/cohort-report-2026-09-12/README.md).
