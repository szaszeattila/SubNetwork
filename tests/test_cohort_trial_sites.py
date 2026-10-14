"""Where a molecule's in-scope trials ran, as the export computes it for the
page's trial-sites filter (scripts/cohort/export.py, trial_sites)."""

import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from cohort import export  # noqa: E402


class TrialSitesTest(unittest.TestCase):
    def test_us_only(self):
        self.assertEqual(export.trial_sites([("PHASE2", "United States")]), ("us", None))

    def test_outside_the_us_names_the_countries_sorted(self):
        self.assertEqual(export.trial_sites([("PHASE3", "Russia"), ("PHASE1", "China|Russia")]),
                         ("elsewhere", "China|Russia"))

    def test_both_sides_in_one_trial_or_two(self):
        self.assertEqual(export.trial_sites([("PHASE3", "Germany|United States")]),
                         ("both", "Germany"))
        self.assertEqual(export.trial_sites([("PHASE2", "United States"), ("PHASE1", "Iran")]),
                         ("both", "Iran"))

    def test_a_combined_phase_counts_from_its_parts(self):
        self.assertEqual(export.trial_sites([("PHASE1|PHASE2", "Japan")]), ("elsewhere", "Japan"))

    def test_early_phase_1_and_not_applicable_never_count(self):
        # The floor D21 sets: Early Phase 1 cannot qualify an indication, and a
        # trial with no phase is not one at Phase 1.
        self.assertEqual(export.trial_sites([("EARLY_PHASE1", "Russia")]), (None, None))
        self.assertEqual(export.trial_sites([("NA", "Russia"), (None, "Russia")]), (None, None))

    def test_a_non_counting_trial_cannot_add_a_side(self):
        self.assertEqual(export.trial_sites([("PHASE3", "United States"),
                                             ("EARLY_PHASE1", "Russia")]), ("us", None))

    def test_trials_with_no_listed_site_are_unstated_not_absent(self):
        self.assertEqual(export.trial_sites([("PHASE2", None)]), ("unstated", None))
        # ...and a site anywhere outranks a record that lists none.
        self.assertEqual(export.trial_sites([("PHASE2", None), ("PHASE1", "Russia")]),
                         ("elsewhere", "Russia"))

    def test_no_trials(self):
        self.assertEqual(export.trial_sites([]), (None, None))


class TrialSitesByMoleculeTest(unittest.TestCase):
    def db(self, countries_column=True, version=4):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE molecule_indications (parent_molregno INTEGER, trial_ids TEXT)")
        cols = "nct_id TEXT, phases TEXT, schema_version INTEGER" + (
            ", countries TEXT" if countries_column else "")
        conn.execute(f"CREATE TABLE trial_status ({cols})")
        conn.executemany("INSERT INTO molecule_indications VALUES (?, ?)",
                         [(1, "NCT1|NCT2"), (1, "NCT2"), (2, "NCT3"), (3, None)])
        rows = [("NCT1", "PHASE3", version, "United States"),
                ("NCT2", "PHASE2", version, "Russia"),
                ("NCT3", "PHASE1", version, None)]
        if countries_column:
            conn.executemany("INSERT INTO trial_status VALUES (?, ?, ?, ?)", rows)
        else:
            conn.executemany("INSERT INTO trial_status VALUES (?, ?, ?)",
                             [r[:3] for r in rows])
        return conn

    def test_reads_every_cited_trial_once_per_molecule(self):
        got = export._trial_sites_by_molecule(self.db())
        self.assertEqual(got, {1: ("both", "Russia"), 2: ("unstated", None)})

    def test_a_build_without_countries_says_nothing_rather_than_unstated(self):
        self.assertEqual(export._trial_sites_by_molecule(self.db(countries_column=False)), {})

    def test_a_row_fetched_before_countries_existed_is_not_read_as_no_site(self):
        self.assertEqual(export._trial_sites_by_molecule(self.db(version=3)), {})


if __name__ == "__main__":
    unittest.main()
