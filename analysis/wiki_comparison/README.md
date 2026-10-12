# The nootropics wiki, placed against the catalogue

Read-only. **Adopts nothing**, changes no membership, and writes to neither
database nor the viewer. The findings are in
[docs/NOOTROPIC-WIKI-COMPARISON.md](../../docs/NOOTROPIC-WIKI-COMPARISON.md).

It takes every compound the [scientificsean.wiki](https://www.scientificsean.wiki/)
class table lists (2,184 on 2026-10-11), finds each in ChEMBL 37 where it can,
and says whether it is in `db/cohort1.db` and, if not, what ChEMBL holds for it.

| file | what it is |
| --- | --- |
| `parse_wiki.py` | a saved copy of `/compounds/table` → `wiki_compounds.csv`. The page itself is not kept |
| `wiki_compounds.csv` | slug, name, and the wiki's own section and class. The wiki's labels are carried along for reading and used for nothing |
| `placing.py` | how a name or InChIKey is placed at a ChEMBL parent, its tiers and confidence, and `REJECTED` |
| `compare.py` | places each wiki name and writes `comparison.csv`; prints the summary table |
| `prepare_lists.py` | turns raw downloads of six other public lists into name files, and records how each was retrieved |
| `compare_lists.py` | sets those lists beside the wiki and the catalogue; `SAME_AS_WIKI` is its reviewed equivalences |
| `pubchem_lookup.py` | name → InChIKey through PubChem for the names nothing else placed; resumable |
| `pubchem_cache.json` | what PubChem answered, `[]` for a name it does not know |
| `need_pubchem.json` | names still not looked up (generated) |
| `comparison.csv` | one row per wiki compound: match tier and confidence, ChEMBL parents, catalogue entry and status, and for the rest ChEMBL's max phase, ATC level 1, curated mechanisms, publication targets and whether GtoPdb lists it |

```bash
curl -sL https://www.scientificsean.wiki/compounds/table -o "$TMPDIR/table.html"
python3 analysis/wiki_comparison/parse_wiki.py "$TMPDIR/table.html"
python3 analysis/wiki_comparison/compare.py          # writes need_pubchem.json
python3 analysis/wiki_comparison/pubchem_lookup.py   # slow, and PubChem throttles
python3 analysis/wiki_comparison/compare.py

# the other lists: download them as prepare_lists.py's docstring says, into RAW
python3 analysis/wiki_comparison/prepare_lists.py RAW LISTS
python3 analysis/wiki_comparison/compare_lists.py LISTS
```

The other lists, and `lists_overlap.csv` that compare_lists.py writes beside
them, stay out of the repository: they are other sites' content.

`--data-root` names the checkout that holds `db/cohort1.db` and `db/cache/`
(both gitignored), for running from a worktree with no build of its own.
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
