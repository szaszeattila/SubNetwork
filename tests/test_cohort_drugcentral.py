"""D24: which regulators approved a molecule, from DrugCentral's dump.

Offline: the dump's two tables are given as the COPY text pg_restore prints,
so neither PostgreSQL nor the 1.4 GB file is needed.

Run with: python3 -m unittest discover -s tests
"""
import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_drugcentral as dc  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

DUMP = """--
-- PostgreSQL database dump
--
COPY public.approval (id, struct_id, approval, type, applicant, orphan) FROM stdin;
1\t10\t1998-03-01\tEMA\tA PHARMA\tf
2\t10\t2004-07-01\tPMDA\tA K.K.\t\\N
3\t10\t\\N\tYEAR INTRODUCED\t\\N\t\\N
4\t20\t1970-01-01\tFDA\tB INC\\tTAB\tt
5\t30\t1990-01-01\tFDA\tC\tf
6\t40\t1991-01-01\tFDA\tD\tf
7\t41\t1992-01-01\tFDA\tE\tf
\\.

COPY public.dbversion (version, dtime) FROM stdin;
56\t2026-09-02 00:00:00
\\.

COPY public.identifier (id, identifier, id_type, struct_id, parent_match) FROM stdin;
1\tCHEMBL1\tChEMBL_ID\t10\t\\N
2\tCHEMBL2_SALT\tChEMBL_ID\t20\t\\N
3\tC0000001\tUMLSCUI\t20\t\\N
4\tCHEMBL3\tChEMBL_ID\t30\t\\N
5\tCHEMBL4\tChEMBL_ID\t30\t\\N
6\tCHEMBL5\tChEMBL_ID\t40\t\\N
7\tCHEMBL5\tChEMBL_ID\t41\t\\N
\\.
"""


def cohort_db():
    from cohort import build
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    status, gap = build.evidence_status_of([])
    for p, cid in ((1, "CHEMBL1"), (2, "CHEMBL2"), (3, "CHEMBL3"), (4, "CHEMBL4"),
                   (5, "CHEMBL5")):
        conn.execute("INSERT INTO molecules(parent_molregno, chembl_id, in_cohort, is_seed,"
                     " route_atc_n, route_indication, admission_reason, evidence_status,"
                     " gap_reason) VALUES (?,?,1,0,1,0,'route_atc_n',?,?)",
                     (p, cid, status, gap))
    conn.execute("INSERT INTO molecule_forms(parent_molregno, molregno, chembl_id, is_parent)"
                 " VALUES (2, 22, 'CHEMBL2_SALT', 0)")
    return conn


class ParseTest(unittest.TestCase):
    def test_copy_blocks_are_read_with_nulls_and_escapes(self):
        t = dc.parse_copy(DUMP)
        self.assertEqual(set(t), {"approval", "dbversion", "identifier"})
        self.assertEqual(len(t["approval"]), 7)
        self.assertIsNone(t["approval"][1]["orphan"])
        self.assertEqual(t["approval"][3]["applicant"], "B INC\tTAB")
        self.assertEqual(t["dbversion"][0]["version"], "56")


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.conn = cohort_db()
        self.summary = dc.backfill(self.conn, dc.parse_copy(DUMP))

    def rows(self):
        return self.conn.execute("SELECT parent_molregno, agency, year, orphan"
                                 " FROM molecule_approvals ORDER BY 1, 2").fetchall()

    def test_matched_by_chembl_id_through_a_form_and_year_introduced_left_out(self):
        self.assertEqual(self.rows(), [(1, "EMA", 1998, 0), (1, "PMDA", 2004, None),
                                       (2, "FDA", 1970, 1)])
        self.assertEqual(self.summary["left_out"], {"YEAR INTRODUCED": 1})

    def test_a_structure_reaching_two_entries_is_refused(self):
        # struct 30 files CHEMBL3 and CHEMBL4, two catalogue entries
        self.assertEqual(self.summary["structures_reaching_two_entries"], 1)
        self.assertEqual(self.summary["entries_refused_for_a_shared_structure"], 2)
        self.assertNotIn(3, {r[0] for r in self.rows()})

    def test_an_entry_reached_by_two_structures_is_refused(self):
        # CHEMBL5 is filed on structs 40 and 41: two substances to DrugCentral
        self.assertEqual(self.summary["entries_reached_by_two_structures"], 1)
        self.assertNotIn(5, {r[0] for r in self.rows()})

    def test_rerunning_replaces_rather_than_adds(self):
        dc.backfill(self.conn, dc.parse_copy(DUMP))
        self.assertEqual(len(self.rows()), 3)

    def test_the_manifest_names_the_pinned_dump_and_its_version(self):
        m = json.loads(self.conn.execute("SELECT value FROM build_manifest"
                                         " WHERE key = 'drugcentral_approvals'").fetchone()[0])
        self.assertEqual((m["sha256"], m["version"], m["licence"]),
                         (dc.DUMP_SHA256, "56", "CC BY-SA 4.0"))


class ExportTest(unittest.TestCase):
    """DrugCentral's part leaves the export in its own file, for its licence."""

    def test_it_travels_in_drugcentral_data_js_and_never_in_graph_data_js(self):
        from cohort import export as export_mod
        conn = cohort_db()
        dc.backfill(conn, dc.parse_copy(DUMP))
        conn.commit()
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            disk = sqlite3.connect(str(d / "cohort.db"))
            conn.backup(disk)
            disk.close()
            export_mod.export(db_path=d / "cohort.db", out_dir=d / "viz", backup=False)
            graph = (d / "viz" / "graph.data.js").read_text()
            text = (d / "viz" / "drugcentral.data.js").read_text()
        payload = json.loads(re.search(r"const COHORT_DRUGCENTRAL = (.*);\n$", text, re.S).group(1))
        self.assertEqual(payload["approvals"], {"1": [["EMA", 1998], ["PMDA", 2004]],
                                                "2": [["FDA", 1970]]})
        self.assertEqual(payload["release"], "v56, 2026-09-02")
        self.assertIn("CC BY-SA 4.0", text.splitlines()[1] + text.splitlines()[2])
        # graph.data.js carries the build manifest's counts, never an approval
        self.assertNotIn('["PMDA",2004]', graph)
        self.assertNotIn('"approvals":{', graph)


if __name__ == "__main__":
    unittest.main()
