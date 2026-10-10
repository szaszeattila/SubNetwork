"""Write the follow-up narrative and the main report's revised policy section."""
import collections
import csv
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
OUT=HERE/"out"


def read(name):
    with (OUT/name).open() as f:
        return list(csv.DictReader(f))


def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |", "|"+"|".join("---" for _ in headers)+"|"]+
                     ["| "+" | ".join(f"{x:,}" if isinstance(x,int) else str(x) for x in r)+" |" for r in rows])


def main():
    summary=json.loads((OUT/"summary.json").read_text())
    assert all(summary["checks"].values()),"Do not publish unvalidated results"
    policies=read("policy_comparison.csv")
    get=lambda pid,cat,basis="human_with_families",scenario="baseline":next(r for r in policies if r["policy"]==pid+"__"+cat and r["evidence_basis"]==basis and r["scenario"]==scenario)
    names={"P0_all_clinical":"Whole clinical catalogue","P1_indication_phase3":"CNS Approved/Phase 3 only",
           "P2_atc_plus_approved":"ATC N + CNS Approved","P3_atc_plus_phase3":"ATC N + CNS Approved/Phase 3",
           "P4_atc_plus_phase2":"ATC N + CNS Approved/Phase 2/3"}
    membership_table=table(["Selection","All types","Small molecules","Seeds in small-molecule set"],
        [[label,int(get(pid,"all_types")["catalogue_molecules"]),int(get(pid,"small_molecules")["catalogue_molecules"]),
          int(get(pid,"small_molecules")["seeds_retained"])] for pid,label in names.items()])
    graph_table=table(["Small-molecule selection","Supported molecules","Supported pairs","Targets with support","Usable molecules","No qualifying edge"],
        [[label,*[int(get(pid,"small_molecules")[k]) for k in ["molecules_with_supported","supported_pairs","supported_targets","molecules_with_supported_or_preliminary","molecules_without_qualifying_edges"]]] for pid,label in names.items()])
    basis_names={"human_single":"Human single proteins","human_single_and_complex":"+ precise protein complexes","human_with_families":"+ families and complex groups"}
    basis_table=table(["Evidence basis for the same 995 candidates","Supported claims","Supported molecules","Usable molecules"],
        [[label,*[int(get("P3_atc_plus_phase3","small_molecules",basis)[k]) for k in ["supported_claims","molecules_with_supported","molecules_with_supported_or_preliminary"]]] for basis,label in basis_names.items()])
    recovery=read("unit_recovery_summary.csv")
    recovery_table=table(["Recovery scenario","Assignment basis","Added measurements","New Preliminary claims","New Supported claims"],
        [["Concentration conversions" if r["scenario"]=="concentration_only" else "Including conditional mass conversions",
          "All assignments" if r["basis"]=="all_assignments" else "Direct human single protein",
          int(r["added_measurements"]),int(r["newly_preliminary"]),int(r["newly_supported"])] for r in recovery])
    chosen=get("P3_atc_plus_phase3","small_molecules")
    low=get("P4_atc_plus_phase2","small_molecules")
    wider_delta={k:int(low[k])-int(chosen[k]) for k in ["catalogue_molecules","molecules_with_supported","supported_targets"]}
    unit_thresholds=read("unit_threshold_changes.csv")
    threshold_rows=[]
    for scenario in ["concentration_only","including_conditional_mass"]:
        for basis in ["all_assignments","human_single"]:
            for threshold in [1,10,100,300]:
                rows=[r for r in unit_thresholds if r["scenario"]==scenario and r["basis"]==basis and int(r["threshold_uM"])==threshold]
                threshold_rows.append([scenario,basis,threshold,sum(r["old_pass"]=="0" and r["new_pass"]=="1" for r in rows),sum(r["old_pass"]=="1" and r["new_pass"]=="0" for r in rows)])
    org=read("organism_reviewed.csv")
    diag=read("organism_unsafe_pooling_diagnostic.csv")
    org_counts=collections.Counter(r["context_class"] for r in org)
    diagnostic_prelim=sum(r["old_tier"]=="limited_or_unresolved" and r["unsafe_pooled_tier"]=="preliminary" for r in diag)
    diagnostic_supported=sum(r["old_tier"]!="supported" and r["unsafe_pooled_tier"]=="supported" for r in diag)
    policy_section=f'''## 6. Follow-up findings and proposed import policy

**No policy is adopted or implemented by this report.** The September 12
follow-up answers the Zotero questions and measures concrete choices using
the original candidate and evidence exports. Full methods, conversion audit,
all 28 seeds under every policy, and limitations are in
[COHORT-FOLLOWUP.md](COHORT-FOLLOWUP.md) and
[`analysis/cohort1/followup/`](../analysis/cohort1/followup/README.md).

### 1. Count both admission routes explicitly

The earlier recommendation quoted **997** while also recommending retention
of both routes. That is the indication-only Approved/Phase-3 count. Keeping
whole ATC N alongside it gives **1,206** candidates, or **995 small molecules**.
An ATC-only candidate remains eligible even when its CNS phase is missing;
this does not label it CNS-approved.

{membership_table}

These use S0 core indications. All 28 seeds are tested without grandfathering.
The small-molecule definition follows the parent's source type literally.
Both theophylline records, including parent `CHEMBL190`, are typed `Protein`
in ChEMBL 37. That source anomaly costs theophylline under a literal
small-molecule filter even before considering its Phase-1 CNS indication.
It needs an explicit identity correction, not a silent exception.

### 2. Separate catalogue membership from drawable evidence

The following uses the **original baseline evidence**, keeping supported
human single proteins, precise complexes, families and complex groups at
their native ChEMBL target level. Experimental support is recalculated only
from direct human assignments within each accepted type; mutants and
homologous assignments do not contribute. Curated support retains its own
route and is not experimental replication.

"Usable" means at least one Supported or Preliminary claim. A pair is a
molecule-target pair, which may have several role-specific claims. Targets
are ChEMBL target records, not counts of expanded component proteins.

{graph_table}

For the same 995 candidates, target granularity changes what can be shown:

{basis_table}

My proposed starting catalogue is **ATC N plus CNS Approved/Phase 3, small
molecules first**. Keep all 995 catalogue entries. Its broad human-specific
evidence view reaches **{int(chosen['molecules_with_supported']):,} molecules with Supported evidence**
and **{int(chosen['molecules_with_supported_or_preliminary']):,} with Supported or Preliminary evidence**;
the other **{int(chosen['molecules_without_qualifying_edges']):,} remain visible as coverage gaps** for this basis.
Those are not necessarily gaps in all ChEMBL evidence.

Families and complexes need their own target nodes or rows. Their evidence
must not be distributed to subunits or counted as several independent shared
targets. Show Supported claims initially, offer Preliminary and other-species
evidence as explicit layers, and keep curated versus multi-study support
visible. Clinical membership does not certify a CNS mechanism for every edge.

This candidate set carries **{int(chosen['withdrawn_flagged'])} family withdrawal flags** and
**{int(chosen['identity_none'])} records without a structure**. Preserve those annotations;
"clinical catalogue" does not mean currently available or uniformly resolved.

### 3. Treat the Phase-2 expansion as a real tradeoff

Moving from Approved/Phase 3 to Approved/Phase 2/3 while keeping ATC N adds
**{wider_delta['catalogue_molecules']:,} small molecules**, **{wider_delta['molecules_with_supported']:,} molecules with Supported
evidence**, and **{wider_delta['supported_targets']:,} targets with support** under the broad human-specific
basis above. It also retains rolipram and pentoxifylline, which the Phase-3
choice loses. The original claim that this necessarily adds thinner evidence
was not established by its stage counts and is withdrawn. The choice is
between a tighter clinical-stage scope and substantially wider target coverage.

### 4. Preserve excluded evidence before broadening numerical rules

The unit audit compares explicit concentration conversions with a conditional
scenario that also uses the measured compound record's full molecular weight.
The scenarios are alternatives; their counts must not be added together.

{recovery_table}

The direct-human upgrade from explicit concentration conversion is
**phenelzine-MAO-A binding**; imipramine-BRD4 binding gains a Preliminary claim.
The latter's converted values are 647 and 1,020 micromolar, demonstrating why
an exact value and evidence tier do not imply useful potency or exposure.
Conversion does not independently validate upstream units or target species.

The 2,334 mass-concentration proposals remain conditional until the original
material basis is checked. Another 350 non-nM rows remain unrecovered.
No existing coverage-gap molecule gains its first assessed claim through
either conversion scenario. In the proposed 995-molecule catalogue, explicit
concentration recovery adds one Supported claim without adding another
molecule with qualifying evidence.

All **21,999 organism-format exclusions** are now available in a context
inventory. All **36 protein-assigned records**, spanning 22 assays, have been
reviewed from their descriptions. **31** have positive exact nM values, but
their contexts include occupancy, downstream physiology, cell assays with
conflicting format metadata, and microorganism screens. Keeping this context
causes **zero changes to the baseline biochemical tiers**. Blindly pooling
the 31 values would produce {diagnostic_prelim} new Preliminary and
{diagnostic_supported} new Supported claims under the old counting rule; that is a diagnostic
of the risk, not a recommended evidence upgrade.

### 5. Keep scope extensions separate from evidence claims

Core plus CNS oncology plus general pain gives **2,523 molecules (+278)**,
not the earlier 2,445 figure, which counted core plus pain alone. The widest
variant is 2,611 (+366). Neither delta is a count of useful new graph edges:
evidence for molecules added outside the original 2,245 was not assessed.
The corrected scope counts alone do not justify adopting either extension.

A clinical-only catalogue still misses theobromine and other nonclinical
ligands. A future curated-ligand route remains a separate candidate analysis,
with explicit eligibility and identity rules; its coverage is not measured
or assumed here. Loperamide and mibefradil should be judged by those explicit
routes or a documented scope choice, not simply because they are old seeds.

### 6. Build the viewer around selected neighbourhoods

The table measures candidates, claims, pairs and targets; it does not benchmark
rendering performance. A graph need not draw every catalogue item at once.
Searchable membership, target-level identity, selectable neighbourhoods and
clear evidence filters should precede a production import. The original
2,245-by-4,885 product was not an observed edge count and did not establish
that a particular graph implementation was impossible to render.

'''
    doc=PROJECT/"docs/COHORT-REPORT.md"
    text=doc.read_text()
    a=re.search(r"(?m)^## 6\.",text).start()
    b=re.search(r"(?m)^## 7\. Validation",text).start()
    doc.write_text(text[:a]+policy_section+"---\n\n"+text[b:])
    followup=f'''# Clinical cohort follow-up: evidence recovery and import choices

Revised 2026-09-12. Read-only analysis of ChEMBL 37 and the original cohort
exports. No production database, graph export, seed list or viewer changed.
All numerical tables are generated from `analysis/cohort1/followup/out/`.

## Decisions supported by the measurements

Use **995 small-molecule candidates** as a concrete starting proposal if the
desired rule is whole ATC N plus Approved/Phase-3 CNS indications. That
proposal retains 22 of the original 28 seeds. Under direct human evidence
plus curated human targets at their native single-protein, complex or family
level, **666 molecules have a Supported claim, 738 have a Supported or
Preliminary claim, and 257 have neither**. Keep the catalogue distinct from
the displayed neighbourhood; the figures are not a rendering benchmark.

The unit question yields a small, tractable first improvement: 30 explicit
concentration conversions. The much larger mass-concentration opportunity
needs chemical-form checks. The organism question yields a context inventory
and 22 assay reviews; it does not justify mixing in-vivo exposure with
in-vitro potency. These are recommendations, not adopted production rules.

## 1. What was reproduced

The analysis reproduces the existing experimental evidence tiers and the
strict human-single-protein tier subset from their measurement rows, before
adding any proposed conversion. It also recovers the original 2,245-member
scope from the exported MeSH descriptor classification and ChEMBL indication
IDs. All source databases are opened with SQLite `mode=ro`.

Inputs are pinned by SHA-256 in `followup/out/summary.json`; the 30.5 GB
ChEMBL file is pinned by release and byte size as in the original manifest.
No other pharmacology database was assessed and no clinical membership is
decided by evidence availability. Publication counts remain a proxy for
independence, and baseline upstream validity/duplicate flags remain visible.

The original MeSH cache files are absent from this checkout. The follow-up
uses the saved `indication_scope.csv` rather than fetching a changing current
ontology. It therefore reproduces these scope comparisons offline without
claiming to restore the original cache byte-for-byte. Re-fetching MeSH for
the full original pipeline would be a new snapshot and requires comparison.

## 2. Unit recovery

The original table confused retention with numerical use. Every one of the
2,714 `excluded_units` records is already in the baseline measurement audit.
The corrected `evidence_exclusions.csv` now reports that accurately.

{recovery_table}

The second scenario **includes** the first. New Preliminary and new Supported
claims are distinct transitions; a newly Supported claim may have been
Preliminary or Limited before. A claim includes its binding/functional role;
curation of that molecule-target pair never upgrades another role.

### Explicit concentration units: 30 records

The allowlist accepts dimensionally explicit concentration units and an
unambiguous `10^integer` prefix. Examples: 19.2 pmol/L becomes 0.0192 nM;
1.5 in `10^3nM` becomes 1,500 nM. Apostrophe exponent spellings, inverse
concentrations, rates, doses, percentages and missing units are not guessed.

The 30 records affect 29 claims and 16 molecules across all assignments.
Six records concern five claims in the strict human subset. Phenelzine at
MAO-A gains a second publication for binding IC50 and becomes Supported
under the report rule. Imipramine-BRD4 gains one Preliminary binding claim,
from two domains measured in one publication; its 647/1,020 micromolar
values are above all four thresholds considered.

These are conversions of source-reported numbers, not independent correction
of those numbers. For example, some assay descriptions say the target's
origin is unknown despite the direct-human metadata. Preserve that conflict
for review rather than pretending unit conversion resolves it.

### Conditional mass conversion: 2,334 additional records

The mass allowlist covers `ug.mL-1`, `ug ml-1` and `ng/ml`. A proposed
conversion requires a structured Small molecule, a canonical structure,
and positive `full_mwt` on the **measured** ChEMBL record. For micrograms/mL:

`nM = value_in_micrograms_per_mL * 1,000,000 / molecular_weight_g_per_mol`

Using a parent freebase weight for a measured salt can give a different
answer. Even the correct source-record weight does not prove whether the
paper expressed mass as freebase, salt, hydrate or formulation. Hence this
is a conditional sensitivity estimate, with every assumed weight exported
in `unit_audit.csv`; it is not an automatically eligible import list.

Of 2,437 records in these three mass units, 103 fail the identity/weight
conditions. Alongside 247 missing, incompatible or unreviewed unit cases,
that leaves **350** non-nM records unrecovered. The larger conditional
scenario helps mostly evidence outside the strict direct-human subset.

### Threshold consequences

For each affected claim and endpoint, recompute the log-space median with
the proposed values. Both directions are shown: adding an exact measurement
can move a median above a threshold as well as below it. These are changes
in **claim-endpoint combinations**, not unique claims or molecules.

{table(["Scenario","Basis","Threshold (uM)","New passes","Lost passes"],threshold_rows)}

No conversion changes membership or establishes brain exposure. No original
coverage-gap molecule gains its first assessed claim in either scenario.

## 3. Organism-format exclusions

All 21,999 excluded rows are now in `organism_context.csv.gz`, including
published and standard value/unit fields, study references, assay organism,
target organism, confidence and assignment. Of these, 21,937 have organism
targets, 36 have protein/family/complex targets, and 26 have other targets.

The 36 protein-assigned rows span 22 assays. Every assay description was read
and its interpretation recorded in `organism_review.json`; this is a review
of source descriptions, not a full re-extraction of 22 original methods.

{table(["Context identified from the description","Records"],[[k,v] for k,v in sorted(org_counts.items())])}

Four records describe receptor occupancy, separating brain and plasma
concentrations. That is useful exposure/target-engagement context, but is
not the same quantity as a biochemical binding constant. Two describe cell
systems despite the organism-format label. The H1 assay for latrepirdine
explicitly names SK-N-SH cells; the cited publication discusses H1 and
5-HT6 antagonism, but its accessible abstract alone does not verify every
assay method. [Publication record](https://pubmed.ncbi.nlm.nih.gov/19443217/)

The appropriate immediate outcome is **context retention, with zero changes
to the baseline biochemical tiers**. Candidate metadata corrections remain
pending methods-level confirmation. The complete records and reasons are
in `organism_reviewed.csv`.

As a diagnostic, lifting the gate for the 31 protein-assigned positive exact
nM values would affect 27 functional claims, create {diagnostic_prelim} Preliminary
claims and upgrade {diagnostic_supported} to Supported under the old counting rule.
This deliberately unsafe comparison in `organism_unsafe_pooling_diagnostic.csv`
shows why numerical eligibility alone is insufficient: different organism,
exposure, preparation and endpoint contexts must not manufacture replication.

## 4. Concrete catalogue policies

All choices use S0 core indication scope and keep parent normalisation.
The indication phase is `max_phase_for_ind`, not overall molecule phase.
The whole-ATC route has no implied indication-phase requirement.

{membership_table}

Every policy has all-type and literal Small-molecule versions. Theophylline's
parent and hydrate are both typed Protein in this ChEMBL release, so the
small-molecule filter exposes an identity annotation problem. It is not
silently corrected to preserve an old seed. The chosen Phase-3 set also
excludes theophylline on its indication phase. Theobromine, loperamide and
mibefradil fail S0 clinical membership; rolipram and pentoxifylline fail the
Phase-3 cutoff. `policy_seed_membership.csv` shows all 28 under every choice.

## 5. Evidence available under each policy

The following figures use baseline measurements, with human-specific
experimental assignment and supported human curation. Curated action,
binding and functional claims stay separate. Families and complexes retain
their original target identifier and are not expanded into component claims.

{graph_table}

For the proposed 995 candidates, the exact effect of widening target type is:

{basis_table}

The recommended representation keeps all three levels available and labelled.
Adding families/groups to the single-plus-precise-complex basis brings another
109 molecules with Supported evidence in this catalogue. Removing those
claims altogether would lose substantial neuropharmacology; expanding them
to subtype claims would misrepresent their specificity.

The 995 candidates have 63 withdrawal annotations and 12 structure-NONE
identities. Clinical selection does not mean currently approved, available,
brain-penetrant or fully identified. Preserve those distinctions in the UI.

Phase 2 adds {wider_delta['catalogue_molecules']} small molecules, {wider_delta['molecules_with_supported']} supported molecules and
{wider_delta['supported_targets']} supported targets versus the Phase-3 proposal under the same broad
human basis. That is a meaningful coverage tradeoff; the original report's
unqualified assertion of thinner evidence is unsupported and removed.

Explicit concentration recovery adds one Supported claim to the proposed
catalogue (2,049 becomes 2,050), with no new supported/usable molecule.
`policy_comparison.csv` contains both baseline and recovered scenarios for
all target bases and catalogue choices. Conditional mass conversion is not
included in the proposed policy figures.

## 6. Scope arithmetic and interpretation corrections

Core plus oncology plus pain is **2,523 (+278)**; core plus pain alone is
2,445 (+200), and the widest scope is 2,611 (+366). The original recommendation
conflated those alternatives. Evidence for added molecules outside the
baseline candidate set is not assessed by this follow-up.

Other corrections are incorporated into the main report: `Preliminary`,
chemical parents, ATC branches, MeSH descriptors/tree numbers, scope versions,
mapping failures and target assignments are explained at first use. The
retention table now distinguishes missing numerical eligibility from missing
exported records. The four known-bad activity rows are retained in a separate
follow-up audit while remaining excluded from all proposed evidence.

The bounds inventory contains >, <, >=, <= and >> relations, plus 28 approximate
`~` results under the old status name. They do not all mean no activity.
Confidence 4/6/8 is a mixed category; a >=7 filter cannot admit every record
in it. A count of 1,676 human single-protein target records is not a count of
targets with direct human experimental support.

## 7. Reproduction and validation

Run from the repository root:

```bash
python3 analysis/cohort1/followup/analyze.py
python3 -m unittest tests.test_cohort_report tests.test_cohort_followup -v
python3 analysis/cohort1/followup/write_summary.py
```

The original 16 analysis tests and 13 follow-up tests pass. They exercise
unit dimensions, the measured salt weight, non-exact relations, incompatible
endpoints, duplicate studies, dataset provenance, species/variant separation,
target granularity and phase-versus-ATC admission. The data validations in
`followup/out/validation.csv` verify baseline tier reproduction, scope and
exclusion accounting, complete assay review, uniqueness of native target
claims, and unchanged production fingerprints.

Source limits: no new ligand catalogue, literature-wide search, supplementary
database integration, full mass-basis verification, or viewer performance
benchmark is implied by these results. The original annotation pages refer
to the archived edition; the revised PDF has different pagination.
'''
    (PROJECT/"docs/COHORT-FOLLOWUP.md").write_text(followup)
    print("Updated docs/COHORT-REPORT.md section 6 and docs/COHORT-FOLLOWUP.md")


if __name__=="__main__":
    main()
