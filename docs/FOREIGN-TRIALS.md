# Trials outside the United States

2026-10-13. **A proposal on the `worktree-foreign-trials` branch; adopts
nothing.** No membership policy was changed. Figures are from this branch's
build (selection policy 3.0.0, D21, 2,452 entries) and a fresh trial backfill;
where they disagree with [../CLAUDE.md](../CLAUDE.md)'s Status, Status is right.

The user's annotation on the wiki comparison, at *National approvals are the
real gap for the Russian drugs*:

> I think this is an interesting lead. if we can get foreign trial data into
> the graph and admit molecules based on at least equivalent phase 1 in other
> countries, and that could be a filter in the display options (us only vs us
> + foreign vs foreign only). attempt this in a new worktree.

It has two halves, and they came out differently. **Where a member's trials
ran** can be read by identifier and is now on the page as a filter. **Admitting
molecules from registries other than ClinicalTrials.gov** has no open source to
read, and is written up below with what blocks it.

## ClinicalTrials.gov is not a US registry

The first thing the data says is that the premise half-holds already.
ChEMBL's indication phases come from ClinicalTrials.gov, and ClinicalTrials.gov
registers trials run anywhere: a trial with every site in Russia is an NCT id
like any other. So D21's floor already admits on Phase 1 trials abroad,
wherever ChEMBL's curators made the trial an indication. **471 of the 2,452
entries have Phase 1 or later in-scope trials that list sites outside the US
only**, and 412 of those are in by the indication route alone. Emoxypine, a
Russian drug, is a member on Phase 3 stroke trials sited in Russia, Kazakhstan
and Uzbekistan; tianeptine's are in Brazil and Poland.

What ChEMBL does not have is trials registered *only* in another country's
registry, and national approvals that rest on no registered trial. Those are
the part the Russian drugs need, and the part no open source reaches.

## What was built: where each member's trials ran

**Data.** `scripts/resolve_cohort_trials.py` already fetches every NCT id
ChEMBL cites, by identifier. It now also stores `trial_status.countries`
(`schema_version` 4): the distinct countries the registry lists a site in,
NULL where the record lists none. Nothing is matched on a name.

**The rule** (`trial_sites` in `scripts/cohort/export.py`). For each molecule,
read every trial cited for any of its in-scope indications. A trial counts
only where the registry's own phase for it is Phase 1 or later — D21's floor,
read off the trial, because an indication's phase can come from a US Phase 3
while its trial abroad was Early Phase 1. Early Phase 1 and "not applicable"
never count. The molecule is then:

| `trial_sites` | meaning | entries |
| --- | --- | ---: |
| `us` | every counted trial with a listed site has one in the US, and none abroad | 498 |
| `both` | sites in the US and elsewhere | 1,030 |
| `elsewhere` | sites outside the US only | 471 |
| `unstated` | counted trials, none listing a site | 88 |
| null | no Phase 1+ in-scope trial ChEMBL cites | 365 |

The 365 are 160 members by both routes, 72 by ATC N alone, 130 by an
indication with no Phase 1+ registered trial behind it (a label, an approval,
a trial the registry phases lower or no longer returns), and 3 seeds. Aniracetam, oxiracetam, pramiracetam, phenibut and mebicar are among
them: members, with no trial anywhere to place.

Of the 14,829 cited trials the registry returned, 8,285 have a US site, 5,102
sites outside the US only, and 1,442 list no site. Among the 471
outside-only members the commonest countries are Germany (113), the United
Kingdom (89), France (72), Spain (53), China (51) and Canada (48); Russia is in
25 of them, and in 281 members' trials altogether.

**The page.** A *Trial sites* control in Display options, with four settings:
**Every molecule** (the default, which moves nothing), **US sites** (`us` or
`both`), **Anywhere** (any counted trial, sited or not) and **Outside the US**
(`elsewhere` or `both`). "Outside the US" is read as *which trials count*, not
*which molecules were never trialled in the US*: a drug trialled in both has
Phase 1 evidence from abroad and stays. Each setting shows how many molecules
it keeps; its banner counts what it hides and splits the hidden by why (no
trial at all, or trials only on the other side); the indications section says
where the molecule's trials ran and names up to six countries; and a link
carries it as `&trials=elsewhere`. The control is offered only where the
payload carries sites, so a build without the backfill does not offer three
settings that empty the canvas. Since 2026-10-15 each trial under a disease
also names its own countries beside its NCT id ("NCT02374567 (Germany)"), so
the section's summary sentence can be traced to the trial behind it
([VIEWER.md](VIEWER.md)).

**It is an eligibility filter, and the viewer's rule changes with it.**
`claimVisible` used to be decided by four claim filters. This makes five, and
the fifth is about the molecule rather than the claim: under "US sites" a
molecule trialled only abroad is out of the panels, the ranking and the second
hop as well as the canvas, because a picture of "what US trials support" in
which it still ranked as a neighbour would be two pictures at once. The
alternative, a drawing rule like *Hide single-molecule targets*, was rejected
for that reason. CLAUDE.md's rule and [VIEWER.md](VIEWER.md) are updated on
this branch.

## What admitting from other registries would take

Measured from the registries' own pages on 2026-10-13. None was downloaded.

| source | bulk access | terms | intervention / condition / phase | Russian trials |
| --- | --- | --- | --- | --- |
| WHO ICTRP (18 primary registries: ChiCTR, CTRI, jRCT, IRCT, DRKS, EU-CTR, CTIS, ISRCTN, ANZCTR, …) | full CSV/XML, by request form; the crawling service is down | no open licence; reuse "for marketing, promotional or commercial purposes" is forbidden; credit WHO | free text / free text / a field, often empty | none: Russia has no primary registry |
| EU CTR (EudraCT) | none: 20 records per text export | credit the register; EMA permits reuse with acknowledgement | not verified | as sites of EU trials |
| CTIS | no documented API | — | — | — |
| jRCT | automated download prohibited | — | — | — |
| Russia, GRLS clinical-trial permits | none; moved to grls.minzdrav.gov.ru with no export | none published | permit and purpose, no phase | the source itself |

So **no registry outside ClinicalTrials.gov is both bulk-readable and under
terms an open CC BY-SA repository can rely on.** ICTRP comes nearest and is
the only route to the Chinese, Indian, Japanese and Iranian registries. Its
non-commercial clause is not compatible with republishing derived facts under
CC BY-SA without asking WHO.

**And its interventions are free text, so admitting from it means matching
drug names.** `selection.py` says *nothing is matched on a name*, and
invariant 15 forbids it for anything entering the database. The wiki
comparison already tried the nearest version, ClinicalTrials.gov read directly
by intervention name ([NOOTROPIC-WIKI-COMPARISON.md](https://github.com/szaszeattila/SubNetwork/blob/worktree-wiki-comparison/docs/NOOTROPIC-WIKI-COMPARISON.md),
*Clinical records*). The trials it found passed the scope by their condition
and mostly trialled drugs that are not for a brain disorder: statins in
stroke, kinase inhibitors in glioma, anti-androgens in Kennedy's disease, and
compounds listed beside the drug under test. ChEMBL's curation is what turns a
trial into an indication, and a registry read by name reads around it.

**What it would reach for the Russian drugs**, by ClinicalTrials.gov, the one
source with structured countries:

| drug | in ChEMBL's trials? | |
| --- | --- | --- |
| emoxypine (Mexidol) | yes | already a member, `elsewhere` |
| fabomotizole (Afobazole) | yes | already a member; its cited trials list no site (`unstated`); a Phase 4 Russian trial ChEMBL does not cite exists |
| phenylpiracetam (Phenotropil) | no | one Phase 1 trial by name (NCT07852130); ChEMBL records no indication |
| cerebrolysin | no | 40 trials by name, but a peptide hydrolysate with no ChEMBL parent |
| semax, selank, bromantane, noopept, bemethyl, cortexin | no | no registered trial in any fetchable registry |

The six in the last row are national approvals with no trial record anywhere
this project can read, which is the GRLS gap again.

## Decisions this needs

1. **Whether to adopt the filter.** It is built and tested on this branch,
   rests on identifiers only, changes no membership, and widens `claimVisible`
   from four filters to five. Merging it is the user's call.
2. **Whether to ask WHO** about ICTRP's terms for an open project. Without a
   yes, nothing from ICTRP can be published here.
3. **Whether trial interventions may be matched by name** for a new admission
   route, against invariant 15 and `selection.py`'s rule. This is the precondition
   for any registry beyond ClinicalTrials.gov, and for ClinicalTrials.gov trials
   ChEMBL has not curated. If yes, the wiki comparison's ClinicalTrials.gov
   measurement says the route needs a reviewed list rather than a rule.
4. **The Russian approvals stay unreachable** until GRLS publishes an export
   or the project accepts a hand-curated, cited list of national approvals
   under its own provenance — a policy question, not a source.

## Reproducing

```bash
python3 scripts/build_cohort.py               # D21, selection policy 3.0.0
python3 scripts/resolve_cohort_trials.py      # refetches every row below schema 4
# ... the other backfills, as CLAUDE.md lists them
python3 scripts/export_cohort.py              # writes trial_sites / trial_countries
```

The rule's tests are `tests/test_cohort_trial_sites.py`, the backfill's
`tests/test_cohort_trials.py`, and the page's `tests/cohort_viewer_trials.test.mjs`.
