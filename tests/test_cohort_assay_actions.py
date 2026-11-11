"""ChEMBL's per-activity action word, backfilled and exported (D28).

What is locked in: the backfill copies activities.action_type and its parent
verbatim onto the observation, for every assay type, adding the columns where
the database predates them, idempotently. The export ships the word only from a
functional assay with an exact value whose parent names a direction, counted in
distinct studies per claim - a binding assay's word (every triptan ANTAGONIST
on a Ki) never reaches the page.
"""

import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_assay_actions as backfill_mod  # noqa: E402
from cohort import export  # noqa: E402


def fake_chembl():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, action_type TEXT);
        CREATE TABLE action_type (action_type TEXT PRIMARY KEY, parent_type TEXT);
        INSERT INTO action_type VALUES ('ANTAGONIST', 'NEGATIVE MODULATOR'),
                                       ('AGONIST', 'POSITIVE MODULATOR'),
                                       ('BINDING AGENT', 'OTHER');
        INSERT INTO activities VALUES (1, 'ANTAGONIST'), (2, 'AGONIST'), (3, NULL),
                                      (4, 'BINDING AGENT');
    """)
    return conn


def old_cohort():
    """An observations table from before the columns existed."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("CREATE TABLE observations (activity_id INTEGER PRIMARY KEY, assay_type TEXT)")
    conn.executemany("INSERT INTO observations VALUES (?, ?)",
                     [(1, "B"), (2, "F"), (3, "F"), (4, "B")])
    return conn


class Backfill(unittest.TestCase):
    def test_copies_the_word_and_its_parent_verbatim_for_every_assay_type(self):
        conn = old_cohort()
        summary = backfill_mod.backfill(conn, fake_chembl())
        self.assertEqual(summary["columns_added"], list(backfill_mod.COLUMNS))
        rows = dict((r[0], (r[1], r[2])) for r in conn.execute(
            "SELECT activity_id, assay_action_type, assay_action_parent_type FROM observations"))
        self.assertEqual(rows, {1: ("ANTAGONIST", "NEGATIVE MODULATOR"),
                                2: ("AGONIST", "POSITIVE MODULATOR"),
                                3: (None, None),
                                4: ("BINDING AGENT", "OTHER")})

    def test_a_second_run_changes_nothing(self):
        conn = old_cohort()
        backfill_mod.backfill(conn, fake_chembl())
        again = backfill_mod.backfill(conn, fake_chembl())
        self.assertEqual(again["columns_added"], [])
        self.assertEqual(again["rows_changed"], 0)


def cohort_for_export(rows):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE observations (activity_id INTEGER PRIMARY KEY, claim_id INTEGER,"
                 " assay_type TEXT, value_status TEXT, assay_action_type TEXT,"
                 " assay_action_parent_type TEXT, study_key TEXT)")
    conn.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?)", rows)
    return conn


NEG, POS, OTHER = "NEGATIVE MODULATOR", "POSITIVE MODULATOR", "OTHER"


class Export(unittest.TestCase):
    def test_only_an_exact_functional_direction_travels_counted_in_studies(self):
        db = cohort_for_export([
            (1, 10, "F", "exact", "ANTAGONIST", NEG, "pmid:1"),
            (2, 10, "F", "exact", "ANTAGONIST", NEG, "pmid:1"),   # same study
            (3, 10, "F", "exact", "ANTAGONIST", NEG, "pmid:2"),
            (4, 10, "F", "exact", "AGONIST", POS, None),          # no study: counted alone
            (5, 10, "F", "bound", "AGONIST", POS, "pmid:3"),      # no effect seen: not a direction
            (6, 10, "B", "exact", "ANTAGONIST", NEG, "pmid:4"),   # a binding readout
            (7, 10, "F", "exact", "BINDING AGENT", OTHER, "pmid:5"),
            (8, 11, "B", "exact", "INHIBITOR", NEG, "pmid:6"),
        ])
        self.assertEqual(export._assay_actions(db),
                         {10: [["ANTAGONIST", 2], ["AGONIST", 1]]})

    def test_a_database_without_the_columns_ships_none(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE observations (activity_id INTEGER, claim_id INTEGER)")
        self.assertEqual(export._assay_actions(db), {})

    def test_an_observation_row_carries_the_word_only_where_it_is_shown(self):
        shown = {"assay_type": "F", "value_status": "exact",
                 "assay_action_type": "AGONIST", "assay_action_parent_type": POS}
        self.assertEqual(export._shown_assay_action(shown), "AGONIST")
        self.assertIsNone(export._shown_assay_action(dict(shown, assay_type="B")))
        self.assertIsNone(export._shown_assay_action(dict(shown, value_status="bound")))
        self.assertIsNone(export._shown_assay_action(
            dict(shown, assay_action_parent_type=OTHER)))


if __name__ == "__main__":
    unittest.main()
