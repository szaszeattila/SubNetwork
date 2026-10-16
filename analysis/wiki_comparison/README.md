# The nootropics wiki, placed against the catalogue

Read-only. **Adopts nothing**, changes no membership, and writes to neither
database nor the viewer. The findings are in
[docs/NOOTROPIC-WIKI-COMPARISON.md](../../docs/NOOTROPIC-WIKI-COMPARISON.md).
D23 and D24 ([docs/COHORT-2.md](../../docs/COHORT-2.md)) later entered three
sections' placements into the catalogue. Nothing here feeds the build: each placement
was reviewed and written into `config/cohort1_selection.json` as a ChEMBL id.

It takes every compound the [scientificsean.wiki](https://www.scientificsean.wiki/)
class table lists (2,184 on 2026-10-11), finds each in ChEMBL 37 where it can,
and says whether it is in `db/cohort1.db` and, if not, what ChEMBL holds for it.

**The wiki's own list is not in the repository.** Its terms refuse copying the
reference in bulk ([docs/COMPOUND-LIST-TERMS.md](../../docs/COMPOUND-LIST-TERMS.md)),
and the list with its sections and classes is its arrangement. Since
2026-10-15 it is kept in `db/cache/sciwiki/` (`placing.REFERENCE`, gitignored)
with the section files and the full comparison files, and the scripts read and
write them there; `comparison.csv` and `comparison_d21.csv` here are written
beside them by `compare.py` without the `section` and `wiki_class` columns.
The other sites' lists are kept the same way, in `db/cache/lists/`.

| file | what it is |
| --- | --- |
| `parse_wiki.py` | a saved copy of `/compounds/table` → `db/cache/sciwiki/wiki_compounds.csv`: slug, name, and the wiki's own section and class, carried along for reading and used for nothing |
| `placing.py` | how a name or InChIKey is placed at a ChEMBL parent, its tiers and confidence, and `REJECTED` |
| `compare.py` | places each wiki name and writes `comparison.csv`; prints the summary table |
| `admission_rules.py` | how many of the wiki's ChEMBL placements each looser admission rule would let in, beside how much it would grow the catalogue |
| `brain_targets.py` | the same for routes defined by a brain-target set: ChEMBL mechanisms, GtoPdb interactions, PDSP Ki values and ChEMBL measurements, and the wiki compounds outside ChEMBL that GtoPdb or PDSP reach |
| `fetch_lists.py` | retrieves Wikipedia's nootropic, psychoactive and designer-drug categories, with each article's InChIKey through its Wikidata item, and Wikidata's nootropic and psychoactive roles (2026-10-15) |
| `prepare_lists.py` | turns raw downloads of the other public lists into name files, and records how each was retrieved |
| `compare_lists.py` | sets those lists beside the wiki and the catalogue, and says which catalogue entries the wiki brought in (D23, D24) each list has; `SAME_AS_WIKI` is its reviewed equivalences |
| `pubchem_lookup.py` | name → InChIKey through PubChem for the names nothing else placed; resumable |
| `pubchem_cache.json` | what PubChem answered, `[]` for a name it does not know |
| `need_pubchem.json` | names still not looked up (generated) |
| `comparison.csv` | the public copy, without section and class: one row per wiki compound: match tier and confidence, ChEMBL parents, catalogue entry and status, and for the rest ChEMBL's max phase, ATC level 1, curated mechanisms, publication targets and whether GtoPdb lists it |
| `sections.py` | splits the full `comparison.csv` into `db/cache/sciwiki/sections/`, one file per wiki section, each compound labelled with the column of the *What it found* table it is counted under, and whether it is a member under D21 |
| `comparison_d21.csv` | the same against the `phase1-admission` build (D21, selection policy 3.0.0, 2,452 entries) |
| `ctgov_route.py` | the wiki compounds outside the catalogue asked of ClinicalTrials.gov directly, by name: is any registered trial for an in-scope condition at Phase 1 or later |
| `ctgov_cache.json` | what the registry answered: per name, the matching studies' NCT id, phases and condition MeSH ids |

```bash
curl -sL https://www.scientificsean.wiki/compounds/table -o db/cache/sciwiki/raw/compounds_table.html
python3 analysis/wiki_comparison/parse_wiki.py db/cache/sciwiki/raw/compounds_table.html
python3 analysis/wiki_comparison/compare.py          # writes need_pubchem.json
python3 analysis/wiki_comparison/pubchem_lookup.py   # slow, and PubChem throttles
python3 analysis/wiki_comparison/compare.py
python3 analysis/wiki_comparison/sections.py          # offline, after both comparison files
python3 analysis/wiki_comparison/admission_rules.py   # ~2 min: scans every ChEMBL activity
python3 analysis/wiki_comparison/brain_targets.py     # ~3 min; --brain-set catalogue for the wider set

# the other lists: the 2026-10-11 downloads as prepare_lists.py's docstring
# says, into db/cache/lists/raw; Wikipedia and Wikidata refreshed beside them
L=db/cache/lists
python3 analysis/wiki_comparison/fetch_lists.py $L/raw/2026-10-15
python3 analysis/wiki_comparison/prepare_lists.py $L/raw $L/raw/2026-10-15 $L/names/2026-10-15
python3 analysis/wiki_comparison/compare_lists.py $L/names/2026-10-15
```

The other lists, and `lists_overlap.csv` and `listed_on_lists.csv` that
compare_lists.py writes beside them, stay out of the repository: they are
other sites' content.

`--data-root` names the checkout that holds `db/cohort1.db` and `db/cache/`
(both gitignored), for running from a worktree with no build of its own.
`--csv` names the comparison file, so a second build can be placed without
overwriting the first; `--pdsp` the PDSP CSV when the data root has none.
Against the D21 build, from this worktree:

```bash
W=analysis/wiki_comparison
S=db/cache/sciwiki
python3 $W/compare.py --data-root ../phase1-admission --csv $S/comparison_d21.csv
python3 $W/admission_rules.py --data-root ../phase1-admission --csv $S/comparison_d21.csv
python3 $W/brain_targets.py --data-root ../phase1-admission --csv $S/comparison_d21.csv \
    --pdsp ../../../db/pdsp_ki_database.csv
python3 $W/ctgov_route.py --csv $S/comparison_d21.csv --mesh ../../../db/cache/mesh/desc2026.gz  # ~1 h cold
```
ChEMBL is read from `$CHEMBL_SQLITE_PATH` as everywhere else.

**Matching by name is what invariant 15 refuses for the database, and it is
allowed here only because nothing here reaches the database.** Every row says
how it was placed, so a reader can discount the weak ones: an exact ChEMBL
preferred name or an FDA UNII InChIKey is `high`; an exact ChEMBL synonym is
`medium` (`low` at four characters or fewer — AMT is a thymidine there);
anything squashed, stereo-loose (`_connectivity`) or from PubChem is `low`.
Eleven matches were wrong on review and are listed with their reason in
`REJECTED` in `placing.py`: eight PubChem names, two short synonyms and one
squashed name. Peptides and extracts were where PubChem went most wrong.
