#!/usr/bin/env bash
# Reproduce the cohort-1 clinical-catalogue report end to end.
#
#   bash analysis/cohort1/scripts/run_all.sh
#
# Step 1 is the only step that touches the network. Steps 2-5 are offline and
# deterministic: rerunning them against the same cache and the same ChEMBL
# release reproduces every output byte for byte.
#
# Requires python3 (>= 3.10, standard library only) and the ChEMBL 37 bulk
# release. Override its location with CHEMBL_SQLITE_PATH; override the project
# database used for the new-vs-existing target comparison with SUBNETWORK_DB.
# Both databases are opened read-only.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== step 1: cache MeSH tree numbers (the only networked step) =="
python3 scripts/step1_fetch_mesh.py

echo "== step 2: build the clinical catalogue =="
python3 scripts/step2_candidates.py

echo "== step 3: assess ChEMBL 37 target evidence =="
python3 scripts/step3_evidence.py

echo "== step 4: roll up the report tables =="
python3 scripts/step4_tables.py

echo "== step 5: validate =="
python3 scripts/step5_validate.py

echo
echo "Outputs:  analysis/cohort1/out/"
echo "Manifest: analysis/cohort1/MANIFEST.json"
echo "Report:   docs/COHORT-REPORT.md"
