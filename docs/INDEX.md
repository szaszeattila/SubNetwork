# The documents, and which of them are true now

The markdown documents here are not equal: some record a policy that is in
force, some measure alternatives that were never adopted, and some describe a
pipeline that no longer produces the page. Nothing said that anywhere, so this
index says it.

**[../CLAUDE.md](../CLAUDE.md) is the authority.** Its `## Status` section is
generated from the active database by `scripts/cohort_report.py --write-status`,
and a test fails when it drifts. **Where a document below disagrees with it
about a number, Status is right and the document is a record of when it was
written.** No figure in any of these files is regenerated.

CLAUDE.md was split on 2026-09-27, when it had reached 3,375 lines: the viewer's
design reasoning moved to [VIEWER.md](VIEWER.md) and the legacy pipeline to
[LEGACY-PIPELINE.md](LEGACY-PIPELINE.md), both verbatim, and CLAUDE.md keeps a
compact rule list pointing at the first. Anything CLAUDE.md used to say is in
one of the two.

## Start here

| If you want | Read |
| --- | --- |
| what the project is and every rule it follows | [../CLAUDE.md](../CLAUDE.md) |
| why the viewer does something, before you change it | [VIEWER.md](VIEWER.md) |
| the membership policy actually in force | [COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) |
| what that policy produced, measured | [COHORT-1-IMPLEMENTATION.md](COHORT-1-IMPLEMENTATION.md) |
| what cohort 2 is, and what it has added so far | [COHORT-2.md](COHORT-2.md) |
| why a data rule exists before you change it | [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) |
| how good the similarity ranking is | [SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md) |
| what to do next | [NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md), then COHORT-2.md's **Open** |
| how to deploy the viewer (Cloudflare, staging first) | [PUBLISHING.md](PUBLISHING.md), *The Cloudflare copy* |
| what may be pushed to GitHub, and how the repository goes public | [PUBLISHING.md](PUBLISHING.md), *The GitHub repository* |
| to build it all from a fresh clone, starting with ChEMBL 37 | [REPRODUCING.md](REPRODUCING.md) |

## All of them

**In force — these describe rules the pipeline and the page obey.**

| document | what it answers | numbers |
| --- | --- | --- |
| [COHORT-1-DECISIONS.md](COHORT-1-DECISIONS.md) | the adopted selection and evidence policy, decision by decision (D01–D16) | policy, not counts |
| [COHORT-1-IMPLEMENTATION.md](COHORT-1-IMPLEMENTATION.md) | what the adopted policy built, with the two analysis defects it corrects, the limitations and the rollback commands | measured at build time; **Status supersedes** |
| [COHORT-2.md](COHORT-2.md) | cohort 2's decisions: GtoPdb's action as a direction (D17), its primary targets as curated support (D18), partial agonism as half an opposite (D19), one protein as one target across species (D20), and what is open | measured 2026-09-27 against the active build |
| [VIEWER.md](VIEWER.md) | why the page draws, scores and words things as it does — the reasoning behind CLAUDE.md's viewer rules | measured when each rule was made; **Status supersedes** |
| [DATA-QUALITY-LOG.md](DATA-QUALITY-LOG.md) | why every invariant exists — what went wrong, how it was found, what was measured | historical incidents, each dated |

**Procedure — how to do a recurring job.**

| document | what it answers | numbers |
| --- | --- | --- |
| [PUBLISHING.md](PUBLISHING.md) | how to deploy the viewer to Cloudflare: staging with `--preview`, production, the deploy record, the headers and who may open it; this GitHub repository: begun 2026-10-10 as one audited snapshot of a private working copy, never its history; only `main` pushed, and the hooks that refuse a personal path, address or session link; how it goes public (still private); and, as history, the claude.ai artifact deleted 2026-10-10 (its procedure, refusals and versions 1–28) | Access coverage checked 2026-10-10; refusal counts from 18 session transcripts, as of version 22 |
| [REPRODUCING.md](REPRODUCING.md) | how to go from a fresh clone to a page that opens: where to download ChEMBL 37 and its checksum, `CHEMBL_SQLITE_PATH`, the build and backfill order, and which backfills read live sources and will not reproduce exactly (GtoPdb refuses any release but 2026.3) | checked against EBI's server 2026-10-10 |
| [CHEMBL-ERROR-REPORT-ALFUZOSIN.md](CHEMBL-ERROR-REPORT-ALFUZOSIN.md) | the drafted report to ChEMBL that alfuzosin is filed as an alpha-1 agonist, its evidence, and what to undo when ChEMBL fixes it | checked 2026-10-10; **not yet sent** |

**Measurement — these grade something and adopt nothing.**

| document | what it answers | numbers |
| --- | --- | --- |
| [SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) | how the ranking is graded against ATC level-4 classes, what the constant sweep found, and what was adopted on the strength of it | current, but see trap 4 — it quotes two grades on two question sets |
| [SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md) | where the ranking is right and wrong against 50 known drug relationships, and why — including that the ATC N key is its hardest slice | measured 2026-09-17 against the active build |

**Proposals — nothing in these is adopted, and listing one is not adopting it.**

| document | what it proposes | status |
| --- | --- | --- |
| [NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) | what to do next, ranked against the mission's three clauses | proposals; §1a is D15 and §1b is D17, the rest open |
| [MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md) | three ways to expand beyond the caffeine seed, dataset priorities, inclusion criteria | brainstorming; predates cohort 1 and describes the 28-molecule seed as current |
| [COHORT-FOLLOWUP.md](COHORT-FOLLOWUP.md) | unit recovery, the organism-format review, and an alternative selection policy | **recommendations, not adopted production rules** — its own words, and its first heading reads "Decisions supported by the measurements", which means *supported*, not *taken* |
| [COHORT-BOUNDARY-REVIEW.md](COHORT-BOUNDARY-REVIEW.md) | that the scope boundary has a soft edge, and a curated neuropharmacology route | proposals; no membership policy was changed |
| [HOSTING-REVIEW.md](HOSTING-REVIEW.md) | what it would take to host the viewer as a public website: security, the evidence shards, licensing, and the gaps to close first | a review of 2026-10-09, with a status table: the disclaimer, credits, caching, headers, a CSP and shareable links are done; phones and link-preview tags are open, and a second pass of 2026-10-10 lists what the first missed; after the user's annotations, licence links, a data date, how to cite, load failure, staging, the deploy record and one hosted copy are done, and privacy, error reports, browsers, keyboard access and monitoring are open |
| [HOSTING-REVIEW-ANSWERS.md](HOSTING-REVIEW-ANSWERS.md) | the user's annotations on the hosting review: what each action became, answers to its questions (medical-disclaimer examples, the ODbL, privacy and analytics, the GDPR outside the EU, CYP2D6, two headers), and what making the GitHub repository public would take; and a second round: rewrite the history or publish a fresh copy (fresh copy recommended), which files to make public, and what CITATION.cff, CONTRIBUTING, SECURITY.md and issue templates are; and a third round recording what the user decided on them and what was built | sources fetched 2026-10-10; not legal advice |

**Historical — true when written, and describing something that has moved on.**

| document | what it answers | why it is kept |
| --- | --- | --- |
| [LEGACY-PIPELINE.md](LEGACY-PIPELINE.md) | the six-source seed pipeline: its schema, how to run it, how its three seed cohorts were chosen, its backlog and its published snapshot | it is the rollback path, not to be modified; its selection reasoning is the best material here on growing a graph without manufacturing similarity |
| [CLAUDE-MD-SPLIT-PROPOSAL.md](CLAUDE-MD-SPLIT-PROPOSAL.md) | whether to split CLAUDE.md, three options and a recommendation | **done 2026-09-27** at the user's request, options A and B, with B's summary kept in CLAUDE.md as its own warning asked |
| [COHORT-REPORT.md](COHORT-REPORT.md) | what a clinical-only selection rule would have admitted: 2,245 molecules and 138,509 claims | it measured options and **adopted none**; its totals describe policies that were not chosen. Read it for what the alternatives would have cost, never for current figures |
| [archive/cohort-report-2026-09-12/](archive/cohort-report-2026-09-12/README.md) | a frozen copy of that report with its annotations | a snapshot; its internal links no longer resolve, which is expected of an archive |

**Prompts** — [prompts/](prompts/) holds the two task briefs that produced the
cohort report and the cohort-1 implementation. They are provenance, not
instructions to follow now. Their working-directory paths were made
repository-relative on 2026-10-10, before the public copy; nothing else in
them was changed.

## The traps

Four things a newcomer reads wrongly, three of them as current when they are
not and one as a contradiction when it is not.

1. **[COHORT-REPORT.md](COHORT-REPORT.md)'s 2,245 molecules is not the
   catalogue.** The catalogue is in Status and is smaller, because the policy
   that was adopted is not the one that number measures. CLAUDE.md says this in
   its opening and it is worth repeating here.
2. **[MOLECULE-EXPANSION-BRAINSTORM.md](MOLECULE-EXPANSION-BRAINSTORM.md)
   describes the 28-molecule seed list as the running pipeline.** That was true
   on 2026-09-06 and has not been true since cohort 1 was built. Its *reasoning*
   about datasets and admission routes is still live and is what
   [NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) builds on.
3. **"Cohort 2" meant two things.** Cohort 1's documents use it for a deferred
   future catalogue built from PDSP, BindingDB and DGIdb (D12). What was
   actually started on 2026-09-27 under that name is GtoPdb, mechanism first
   and molecules later; [COHORT-2.md](COHORT-2.md) is the record, and PDSP,
   BindingDB and DGIdb are still deferred.
4. **The similarity grade appears as 42.4% and as a lower figure in Status, and
   both are right.** [SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md) §9 reports
   42.4% top-1 on the **217 molecules answerable under the old defaults**, held
   fixed so that a change buying coverage cannot flatter the ordering. Status
   reports the grade over every molecule scoreable now. The first is the honest
   before-and-after of one change; the second is the state of the whole
   catalogue. Neither is stale, and they must not be compared to each other.
   [SIMILARITY-DIAGNOSIS.md](SIMILARITY-DIAGNOSIS.md) §1 adds a third framing —
   44.5% once the answer key is not restricted to ATC N — which is a fact about
   the key rather than about the ranking.

## The analysis directories

Read-only packages that produce numbers quoted above. None of them writes to a
database or to the viewer.

| directory | what it does |
| --- | --- |
| [../analysis/cohort1/](../analysis/cohort1/README.md) | the analysis behind COHORT-REPORT.md, and `followup/` behind COHORT-FOLLOWUP.md |
| [../analysis/similarity_harness/](../analysis/similarity_harness/README.md) | grades the ranking against ATC classes; sweeps the six constants |
| [../analysis/probe/](../analysis/probe/README.md) | asks the ranking about 50 known drug relationships and says what went wrong |
