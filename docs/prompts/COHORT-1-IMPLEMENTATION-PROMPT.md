# Opus 5 — implement the first clinical cohort

Implement the adopted clinical cohort in this SubNetwork repository, including
the database, importer, export, viewer, tests and documentation. Carry the work
through to a working local application with the expanded catalogue. The user
has finished choosing the policy; do not stop after a plan or reopen settled
choices. Use your judgment for implementation details and explain consequential
decisions as you work. Ask only if an actual unresolved blocker prevents work.

Work in the repository root. This is an implementation
task, not another read-only cohort report. Preserve unrelated working-tree
changes, including untracked analysis and documentation. Inspect repository
instructions and current state before editing. Do not deploy or publish.

## Read first and resolve precedence

Read these documents and the relevant source/configuration files they link:

1. `docs/COHORT-1-DECISIONS.md` — the adopted policy, finalized September 13.
   Its dated adopted-rule blocks take precedence over its historical questions.
2. `CLAUDE.md` and `docs/DATA-QUALITY-LOG.md` — existing behavior, invariants,
   known upstream errors, and viewer/identity failures that must not recur.
3. `docs/COHORT-REPORT.md`, `docs/COHORT-FOLLOWUP.md`, and
   `docs/COHORT-BOUNDARY-REVIEW.md` — measurements, corrections and limitations.
4. `analysis/cohort1/README.md`, `analysis/cohort1/config/`, the original
   scripts/outputs/manifest, `analysis/cohort1/followup/README.md` and its
   rules/audits/outputs, and `analysis/cohort1/boundaries/`.
5. `docs/MOLECULE-EXPANSION-BRAINSTORM.md` for the longer-term cohort design.
6. `db/schema.sql`, `scripts/build_db.py`, `scripts/chembl_local.py`,
   `scripts/export_graph.py`, `viz/index.html`, and the existing tests.

The brainstorm, report-generation prompt and archived report are historical
context, not additional requirements to adopt. The boundary review corrects
the report's Neuralgia explanation but does not authorize every expansion it
recommends. Where analysis code, prose and saved records differ, investigate
the source records, implement the adopted policy, and document the resolution.
Do not silently copy an analysis bug into production.

The user explicitly adopted changes to current production behavior: study-based
support replaces measurement-count corroboration; target claims retain their
native granularity; clinical selection supplements the seeds; active
pharmacology becomes ChEMBL-only; and potency becomes an optional display
filter. Reconcile and update affected `CLAUDE.md` invariants and tests. Preserve
unaffected invariants, including exact identity matching, source provenance,
role/endpoint separation, explicit known-bad exclusions and escaped viewer text.

## Product outcome

The user wants to explore substances that may have related effects by examining
their shared targets and evidence. Include all qualifying molecule types;
do not infer an oral-only restriction or a small-molecule filter. The comparison
remains shared-target evidence, not a newly invented predictor of subjective
effects, dose equivalence or interchangeability. Keep that distinction clear
in ordinary product language without adding intrusive warning flows.

The application opens on the **caffeine neighbourhood**. Users can search the
full catalogue, select other neighbourhoods, inspect evidence, and change
evidence/assignment/potency filters. A large catalogue does not require drawing
every molecule and target simultaneously. Preserve the existing useful
interaction patterns and offline viewer experience where practicable.

## 1. Pin inputs and compute the adopted membership

Use ChEMBL 37 at
`/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db`, opened read-only.
Use the saved `analysis/cohort1/out/indication_scope.csv` as the starting MeSH
classification, with versioned scope changes. The original raw MeSH cache is
missing: do not run a fresh ontology fetch and call it the same snapshot.
If an additional descriptor mapping is necessary, record its source, date and
relationship to the pinned inputs explicitly. Keep the cohort build reproducible.

A chemical parent enters cohort 1 if **either**:

- It or one of its source family members carries an ATC level-5 code under
  whole ATC N. This route has no CNS-indication phase requirement.
- It or a family member has an indication at Approved or Phase 3 within the
  adopted indication scope. Use `drug_indication.max_phase_for_ind`, not the
  maximum molecule phase across unrelated diseases. Missing/unknown/earlier
  indication phases cannot satisfy this route.

The indication scope is **S0 core plus the general Pain tree, explicitly
including neuropathic pain and fibromyalgia**. Keep whole ATC N, including
the local-anaesthetic and general-analgesic branches with their annotations.
Do not add blanket oncology, peripheral-nerve or muscle/NMJ admission routes.
A separate qualifying core/pain indication can still admit a substance.

Audit the exact descriptor coverage. The saved scope excludes Fibromyalgia
`D005356`, Neuralgia `D009437`, Postherpetic Neuralgia `D051474`, Trigeminal
Neuralgia `D014277`, Facial Neuralgia `D005156`, and Pudendal Neuralgia
`D060545`. General Pain alone does not recover all these descriptors. Use
stable identifiers and a documented explicit inclusion set/descendant rule
that fulfills the user's neuropathic-pain requirement; these examples are
starting fixtures, not a claim that the complete set has already been mapped.
Explicit pain inclusions take precedence over the old boundary exclusions,
but do not waive the clinical phase requirement.

Accept the actual breadth of the saved Pain tree, including its angina
descendants, with visible admission reasons. Do not silently narrow it to
centrally acting analgesics. Loperamide's saved Pain phase is 0.5, so adding
pain does not itself make it a Phase-3 cohort member.

Include **all molecule types** and retain withdrawal annotations and unresolved
structures. An absent structure does not justify inventing one or losing an
otherwise traceable catalogue identity. Normalize only through explicit source
parent relationships; retain source forms, synonyms and contributing IDs.
Preserve distinct stereoisomers, prodrugs, metabolites and mixtures where the
source distinguishes them. Flag suspicious identity/category records for
review instead of silently rewriting them or merging by name.

Keep all **28 existing seed substances** in the active catalogue, normalized
without duplicate nodes, and label seed membership separately from clinical
membership. Theophylline's seed ID `CHEMBL1355736` maps to `CHEMBL190`; preserve
both identities and aliases in provenance. Its source Protein type is an
annotation, not an exclusion under the selected all-types rule. Reassess every
seed against the new clinical policy. Seeds outside cohort 1 remain examples
for designing cohort 2, not automatically admitted members of an undefined
cohort 2. The old seed expansion batches are not these new systematic cohorts.

Recompute membership, clinical-route overlap, seed outcomes and evidence for
the complete union. The earlier 995/1,206 proposals and their support/gap counts
do **not** describe this policy. Existing evidence exports do not cover every
newly admitted pain/fibromyalgia candidate or every out-of-cohort seed.

## 2. Restrict active pharmacology to ChEMBL

Use **ChEMBL 37 only** for active mechanism/measurement evidence, uniformly
across seeds and new candidates. Defer PDSP, BindingDB and DGIdb entirely from
this active build and from its support counts/ranking. Do not let an old seed
retain stronger active evidence merely because supplementary records already
exist in the old database. Preserve historical data and source provenance in
backups/audits. Some old edges will legitimately disappear or change tier.

Defer GtoPdb, HPA, Chemical Probes Portal, BBB datasets and cohort-2/3 selection.
Identity/context/link enrichment is separate from pharmacology evidence: reuse
valid existing metadata and exact-identifier enrichment where helpful, but
make optional network enrichment resumable and avoid having its failure erase
a catalogue entry or prevent a valid pinned evidence build. Never fall back
silently to a live ChEMBL release. Mark deferred sources **not assessed**,
not as negative evidence findings.

## 3. Represent target claims without overstating specificity

Retain ChEMBL single-protein, precise-complex, protein-family and complex-group
target identities. Do not require every target to fit the old unique gene
symbol/UniProt schema. Store component relationships as context, not inferred
binding claims. Do not distribute family/complex evidence over subtypes or
subunits. Visual grouping must not merge distinct source claims or inflate
shared-target counts; inspect the old `resolve_groups` assumptions accordingly.

Default experimental eligibility follows the follow-up's broad human basis:
human taxon 9606, direct relationship D, no variant, and the appropriate
target-type/assignment combination: single protein confidence 9, precise
complex or complex group confidence 7, family confidence 5. Do not substitute
a generic confidence >=7 test. Keep supported human curated mechanisms at the
target/action level actually asserted, distinct from experimental assignment.
Preserve variant and indirect-mechanism information; it must not become a
wild-type direct-binding assertion through a lossy aggregation.

Offer a separate filter for nonhuman, homologous, variant and otherwise
non-direct/ambiguous assignments, with honest labels and distinguishable
support bases. Include catalogue members whose only eligible evidence is in
that layer. Never manufacture a named-protein edge for an unassigned or
non-molecular observation. Do not pool species, variants or assignment classes
to manufacture replication for a more specific claim. Brain expression and
BBB status are not universal membership or evidence gates; missing remains
unknown. Nonhuman biochemical assays are distinct from organism-format
observations, which are excluded below.

## 4. Adopt the accepted evidence policy

Store and assess claims at parent–target–role granularity, preserving individual
curated actions and source records. Binding, functional and curated claims
remain separate. Within experimental roles, retain endpoint classes such as
Ki, Kd, binding IC50, functional IC50, EC50, AC50 and Kb separately.

- **Supported through curation:** a traceable qualifying ChEMBL mechanism at
  its asserted target/action level, using the report's reference/comment
  provenance rules. A known indirect or unresolved assertion does not become
  direct binding. Curated support never upgrades an experimental claim.
- **Supported through multiple studies:** at least two distinguishable
  publication-class studies with eligible exact measurements within the same
  claim and endpoint class, after assignment/species/variant filtering.
- **Preliminary:** at least one identifiable eligible study without qualifying
  Supported evidence. A patent or deposited dataset may support this tier but
  cannot manufacture multiple-publication support.
- **Limited/unresolved:** retained observations with an explicit reason for
  failing those rules, not an invented default interaction edge.

Resolve publication identity through PMID/DOI with the existing provenance
rules; collapse duplicate representations of the same study. Twenty rows from
one paper remain one study. A dataset DOI is not automatically a publication.
Display measurements, studies and databases as separate quantities. Preserve
per-measurement citations, assay descriptions and quality/duplicate flags.

Retain the report's flag/conflict policy: visible annotations, documented
known-bad exclusions on every applicable ingestion path, no automatic blanket
drop merely for an upstream flag, and no implication that conflicting findings
agree. Preserve conflicting curated directions instead of choosing one by
row order. Multiple publications are a proxy for independence, not proof of
independent laboratories or experiments.

Numeric summaries remain log-space medians within endpoint classes. Counted
measurement rows must reconcile to each displayed summary; study support is a
separate calculation. Do not discard provenance while reducing to display
values. Keep endpoint-specific support visible when a role-level tier is
derived from one qualifying endpoint, so it cannot falsely certify another.

## 5. Conversions and excluded observations

Adopt the audited explicit concentration conversions in the follow-up rules,
preserving original values/units and conversion provenance. Retain exact
relations, positive values and compatible endpoint requirements.

Compute mass-to-molar conversions where identity and molecular weight permit.
Use the **measured material's** source record, never automatically the parent
freebase weight. Retain the weight, source form, original units, formula,
assumptions, result and verification status. Unverified material-basis results
remain **conditional**, excluded from tiers and numeric potency summaries
until their material basis is verified. A source molecular weight alone does
not prove whether a paper expressed mass as salt, freebase or formulation.
Do not guess missing/ambiguous weights or apply small-molecule mass rules
blindly to mixtures/biologics. Conditional calculations with explicit unresolved
reasons satisfy this first release; a literature-wide verification project is
not required. Check existing audit scenarios before recomputing them.

Show bounds and approximations in evidence details with original relations:
`>`, `<`, `>=`, `<=`, `>>`, and `~` are not interchangeable and not exact values.
Exclude them from exact medians, exact-value threshold passes and the adopted
replication rule. A bounds-only record does not become a default Supported edge.
Make these details accessible for a catalogue entry without requiring a
drawable edge. Do not label all bounds as “no activity.”

Exclude organism-format observations from active evidence, viewer context,
graph and ranking, including the broader-assignment layer. Keep historical
organism audits intact; do not import the follow-up's diagnostic unsafe-pooling
scenario. Preserve auditable exclusion reasons for all omitted records.

## 6. Viewer, similarity and potency controls

Default to the caffeine neighbourhood, human-basis Supported claims and **no
potency cutoff**. Distinguish curated versus multiple-study support. Provide
independent controls for Preliminary evidence, broader assignment/species
evidence, and potency. The broader layer must make eligible non-direct-only
members discoverable, with guidance when a separate tier filter also hides them.

Potency is a **display filter**, not a catalogue admission or import cutoff.
Offer 1/10/100/300 micromolar presets and a clear disabled state. Use within-
endpoint log-space medians and label the endpoint. Preserve curated weak or
unquantified mechanisms as curated claims; do not pretend missing potency
passes a numeric threshold. Show this treatment clearly. Reconcile the old
300-micromolar experimental auto-discovery gate so it does not irreversibly
discard evidence before the display filter can operate.

Default similarity counts Supported shared targets at their actual identity.
Prevent multiple role/action rows at one target from multiplying the number
of shared targets. Family/complex-group overlap is distinguishable from exact
single-protein overlap, and is not equivalent to a subtype hit. Choose and
document sensible detailed scoring/weighting; graph, panels and ranking must
use consistent eligible evidence. Optional layers must never silently raise
the default direct-human score. Make active filters and their effects visible.

Keep **every admitted candidate and retained seed searchable**, including
entries with no drawable evidence. Show admission route, clinical annotation,
molecule type, withdrawal/identity flags, source coverage and meaningful gap
reasons. Distinguish “no qualifying evidence found in ChEMBL 37,” “target or
evidence unresolved,” and “evidence hidden by current filters.” Expose retained
observations without requiring a graph edge. Never manufacture an edge to
avoid an empty state, or describe a source gap as no known pharmacology.

Preserve exact-identifier external links, safe escaping of all source text,
useful seed aliases, and molecule/target/evidence navigation. Prefer a light
catalogue/index and selected neighbourhood rendering over loading/rendering
all evidence at once if the measured size warrants it. Keep the offline
`viz/index.html` workflow where feasible; document and justify any necessary
delivery change rather than adding a server or framework by default.

## 7. Build safely and finish the implementation

Start with a short implementation plan after reading the sources. Then execute
it. Design a versioned production selection/evidence configuration and a data
model that supports these claims; simply appending candidates to
`SEED_MOLECULES` is insufficient. Do not repurpose frozen report outputs as
mutable production storage. Keep analysis reproduction and production builds
distinct, reusing validated logic where appropriate.

Build a new database/export in staging. Preserve the existing generated
database/export with a manifest and a practical rollback path. Keep ChEMBL
read-only. Make the build deterministic, restartable/idempotent, and explicit
about pinned sources, missing optional metadata, and failures. A rerun must
remove stale derived claims as appropriate, not only append new ones.

Produce a build comparison with actual counts and material changes, run the
checks below, and activate the validated local artifacts with backups in place.
The user has authorized this implementation through this prompt; no separate
confirmation is required for routine schema/code changes, staged builds or
reversible local activation. Preserve unrelated edits. Do not publish, deploy,
push, or implement future cohorts as part of this task.

Update `CLAUDE.md`, build/run documentation, schema comments and the data-quality
log to describe the new behavior and intentional changes. Leave historical
report totals identified as historical; write new selected-policy results to
a separate implementation summary with source/policy versions. Do not report
stale historical artifact-fingerprint checks as current preservation failures
without distinguishing an intentional rebuild.

## 8. Validation and deliverables

Run the relevant existing suites (`python3 -m unittest discover -s tests` and
the documented Node viewer tests), adapting obsolete expectations only where
the adopted policy intentionally changes behavior. Add meaningful regression
coverage for the changed semantics, including:

- ATC-only eligibility versus indication-specific phase; all categories;
  explicit neuropathic/fibromyalgia inclusions and precedence; boundary
  exclusions that still apply; no phase waiver for Pain.
- Parent/form deduplication, theophylline's mapping, preservation of all seed
  substances, and separate seed/clinical membership reasons.
- One paper with many measurements; repeated PMID/DOI records; datasets and
  patents; separate endpoints/roles/species/variants; curated versus measured
  support; quality flags and contradictory actions.
- Native families/complexes retained without subtype expansion or inflated
  similarity. No unassigned observation converted into a protein edge.
- Audited concentration conversion; measured salt versus parent mass basis;
  conditional mass values excluded from tiers/potency; invalid/unresolved
  conversions; bounds/approximations preserved; organism-format records absent
  from every active layer.
- ChEMBL-only active evidence, including former seeds; deferred-source status
  distinct from no evidence; source failures never converted to negatives.
- Caffeine initial selection; Supported/default and optional-filter behavior;
  searchable zero-edge entries; observation inspection without an edge;
  consistent graph/panel/ranking values and safe rendering of source text.

Validate the complete build's referential integrity, source-record uniqueness,
admission-route arithmetic, parent identities, per-summary measurement counts,
per-claim study counts and exclusion accounting. Report actual catalogue,
claim, pair and target totals, tier/assignment breakdowns, gaps, conversions,
and seed outcomes. Distinguish unique molecules from claims and source target
records from component proteins.

Exercise the actual viewer at the chosen catalogue size, not only its unit
harness. Check caffeine, a dense neighbourhood, a family/complex claim, an
entry with only broader-assignment evidence, and an entry with no drawable
evidence. Measure startup, search, neighbourhood selection/filter responsiveness
and artifact size; address material regressions. Record the environment and
observations without presenting unrun checks as passes. If browser tooling is
unavailable, state that limitation and provide the strongest executable checks.

Finish with the working local application and a concise handoff explaining:
what changed, how to build/open it, the measured cohort and seed outcomes,
validation/performance results, any genuine limitations, and rollback commands
or paths. Link the selected-policy implementation summary. Do not stop at
membership generation, a schema proposal, or a report while the old viewer
still represents the old evidence rules.
