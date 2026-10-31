"""What the export makes of a listed molecule (D25).

The list's name labels an entry only where ChEMBL gives the parent no preferred
name, is searchable either way, and travels with the slug the page builds the
citation link from. A listing from a source the page cannot credit stops the
export rather than reaching the page uncredited.
"""

import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from cohort import build, common, export  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()


def fake_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def add_molecule(conn, parent, chembl_id, pref_name, admission="listed_only"):
    status, gap = build.evidence_status_of([])
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, pref_name, in_cohort, is_seed,"
        " route_atc_n, route_indication, admission_reason, evidence_status, gap_reason)"
        " VALUES (?,?,?,0,0,0,0,?,?,?)", (parent, chembl_id, pref_name, admission, status, gap))


def add_listing(conn, parent, name, slug, source="sciwiki"):
    conn.execute(
        "INSERT INTO molecule_listings(parent_molregno, source, chembl_id, name, slug)"
        " VALUES (?,?,?,?,?)", (parent, source, f"CHEMBL{parent}", name, slug))


def run_export(conn):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        disk = sqlite3.connect(str(d / "cohort.db"))
        conn.commit()
        conn.backup(disk)
        disk.close()
        export.export(db_path=d / "cohort.db", out_dir=d / "viz", backup=False)
        text = (d / "viz" / "graph.data.js").read_text()
    payload = json.loads(re.match(r"^(?:// .*\n)+const COHORT_DATA = (.*);\n$", text,
                                  re.S).group(1))
    strings, fields = payload["strings"], payload["fields"]["molecules"]
    out = {}
    for row in payload["molecules"]:
        m = dict(zip(fields, row))
        out[m["id"]] = m
    return out, strings


class ListingExportTest(unittest.TestCase):

    def setUp(self):
        self.conn = fake_db()
        add_molecule(self.conn, 1, "CHEMBL4303687", None)
        add_listing(self.conn, 1, "Noopept", "noopept")
        add_molecule(self.conn, 2, "CHEMBL167150", "TRICHLORFON")
        add_listing(self.conn, 2, "Metrifonate", "metrifonate")
        add_molecule(self.conn, 3, "CHEMBL113", "CAFFEINE", admission="route_atc_n")

    def test_the_list_s_name_labels_an_entry_chembl_leaves_unnamed(self):
        mols, strings = run_export(self.conn)
        self.assertEqual(strings[mols[1]["name"]], "Noopept")
        self.assertEqual(strings[mols[2]["name"]], "TRICHLORFON")

    def test_the_list_s_name_is_searchable_where_it_is_not_the_label(self):
        mols, strings = run_export(self.conn)
        self.assertIn("Metrifonate", [strings[i] for i in mols[2]["synonyms"]])

    def test_the_listing_travels_as_source_name_and_slug(self):
        mols, strings = run_export(self.conn)
        self.assertEqual([[strings[i] for i in l] for l in mols[1]["listings"]],
                         [["sciwiki", "Noopept", "noopept"]])
        self.assertIsNone(mols[3].get("listings"))

    def test_a_substance_index_name_labels_before_a_wikipedia_title_or_a_wikidata_label(self):
        # D27: Wikidata's label can be a salt's; a Wikipedia title carries a
        # disambiguator a label does not need.
        add_molecule(self.conn, 4, "CHEMBL4", None)
        add_listing(self.conn, 4, "cocaine hydrochloride", "Q1", source="wikidata")
        add_listing(self.conn, 4, "Aleph (psychedelic)", "Aleph_(psychedelic)", source="wikipedia")
        add_molecule(self.conn, 5, "CHEMBL5", None)
        add_listing(self.conn, 5, "Aleph (psychedelic)", "Aleph_(psychedelic)", source="wikipedia")
        add_listing(self.conn, 5, "ALEPH", "aleph", source="tripsit")
        mols, strings = run_export(self.conn)
        self.assertEqual(strings[mols[4]["name"]], "Aleph")
        self.assertEqual(strings[mols[5]["name"]], "ALEPH")

    def test_a_source_the_page_cannot_credit_stops_the_export(self):
        add_listing(self.conn, 3, "Caffeine", "caffeine", source="elsewhere")
        with self.assertRaises(common.PolicyError):
            run_export(self.conn)


if __name__ == "__main__":
    unittest.main()
