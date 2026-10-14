"""Offline tests for scripts/resolve_cohort_fda_classes.py.

Every RxNav request goes through the injectable ``get`` of `RxNav`, so these
use a fake that answers from small dicts shaped like RxNav's JSON and counts
what it was asked. The database is a temp file or in-memory copy of
db/schema_cohort.sql; db/cohort1.db, ChEMBL and the network are never touched
(main() is run with the file/ChEMBL seams patched).

Run with: python3 -m unittest discover -s tests
"""

import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_fda_classes as fda  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

BASE = fda.BASE


def row(rxcui, tty, rela, source, class_id, name, kind):
    return {"minConcept": {"rxcui": rxcui, "name": "x", "tty": tty},
            "rxclassMinConceptItem": {"classId": class_id, "className": name, "classType": kind},
            "rela": rela, "relaSource": source}


SERT_ROWS = [
    # The ingredient's own rows: kept.
    row("36437", "IN", "has_epc", "FDASPL", "N0000175696", "Serotonin Reuptake Inhibitor", "EPC"),
    row("36437", "IN", "has_epc", "DAILYMED", "N0000175696", "Serotonin Reuptake Inhibitor", "EPC"),
    row("36437", "IN", "has_moa", "FDASPL", "N0000000109", "Serotonin Uptake Inhibitors", "MOA"),
    row("36437", "IN", "has_moa", "MEDRT", "N0000000109", "Serotonin Uptake Inhibitors", "MOA"),
    row("36437", "IN", "has_moa", "DAILYMED", "N0000000109", "Serotonin Uptake Inhibitors", "MOA"),
    row("36437", "IN", "has_moa", "FDASPL", "N0000182137", "Cytochrome P450 2D6 Inhibitors", "MOA"),
    row("36437", "IN", "has_pe", "MEDRT", "N0000009198", "Increased CNS Serotonin Activity", "PE"),
    # DAILYMED alone duplicates FDASPL elsewhere; here it is the only source.
    row("36437", "IN", "has_epc", "DAILYMED", "N0000999999", "Only Via DailyMed", "EPC"),
    # Other relations and other class systems.
    row("36437", "IN", "ci_moa", "FDASPL", "N0000111111", "Contraindicated MoA", "MOA"),
    row("36437", "IN", "may_treat", "MEDRT", "D003866", "Depression", "DISEASE"),
    row("36437", "IN", "has_epc", "ATC", "N06AB", "Selective serotonin reuptake inhibitors", "ATC"),
    # The salt's rows (a PIN minConcept): not the ingredient's.
    row("155137", "PIN", "has_moa", "MEDRT", "N0000222222", "Salt Only Class", "MOA"),
]


class FakeRxNav:
    """Answers RxNav's endpoints from dicts; ``fail`` is a set of substrings of
    a URL+params string whose request raises RxNavError."""

    def __init__(self):
        self.unii = {"U_SERT": ["36437"],
                     "U_SERT_HCL": ["155137"],          # PIN
                     "U_A": ["1001"], "U_B": ["1002"],  # two different INs
                     "U_BRAND": ["5555"],               # a brand (BN)
                     "U_BAD": ["7777"]}
        self.tty = {"36437": "IN", "155137": "PIN", "1001": "IN", "1002": "IN",
                    "5555": "BN", "7777": "PIN", "8888": "IN"}
        self.related = {"155137": ["36437"], "7777": ["1001", "1002"]}
        self.classes = {"36437": SERT_ROWS,
                        "1001": [row("1001", "IN", "has_epc", "FDASPL", "N1", "Class A", "EPC")],
                        "1002": []}
        self.fail = set()
        self.calls = []

    def __call__(self, url, params=None):
        key = f"{url} {params}"
        self.calls.append(key)
        if any(f in key for f in self.fail):
            raise fda.RxNavError("boom")
        if url.endswith("/version.json"):
            return {"version": "01-Jan-2030", "apiVersion": "3.1.0"}
        if url.endswith("/rxcui.json"):
            ids = self.unii.get(params["id"])
            return {"idGroup": {"rxnormId": ids} if ids else {}}
        if url.endswith("/properties.json"):
            rxcui = url.split("/")[-2]
            return {"properties": {"rxcui": rxcui, "tty": self.tty[rxcui]}} if rxcui in self.tty else {}
        if url.endswith("/related.json"):
            rxcui = url.split("/")[-2]
            ins = self.related.get(rxcui, [])
            groups = [{"tty": "IN", "conceptProperties": [{"rxcui": i, "tty": "IN"} for i in ins]}] if ins else [{"tty": "IN"}]
            return {"relatedGroup": {"rxcui": None, "conceptGroup": groups}}
        if url.endswith("/byRxcui.json"):
            rows = self.classes.get(params["rxcui"])
            return {"rxclassDrugInfoList": {"rxclassDrugInfo": rows}} if rows else {}
        raise AssertionError(key)


def new_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def add_molecule(conn, parent, chembl_id, inchikey):
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, inchikey, in_cohort,"
        " is_seed, route_atc_n, route_indication, admission_reason)"
        " VALUES (?,?,?,0,0,0,0,'seed_only')", (parent, chembl_id, inchikey))


# Molecules: 1 sertraline (a base key and a salt key, both reach the one IN),
# 2 reaches its IN only through a PIN, 3 a parent whose two UNIIs reach two INs (ambiguous),
# 4 no UNII, 5 UNII RxNorm does not know, 6 UNII is a brand, 7 PIN with two INs,
# 8 an IN with no FDA class at all.
MOLECULES = [
    (1, [("CHEMBL_SERT", "K_SERT"), ("CHEMBL_SERT_HCL", "K_SERT_HCL")]),
    (2, [("CHEMBL_PINONLY", "K_SERT_HCL_ONLY")]),
    (3, [("CHEMBL_AMB", "K_A"), ("CHEMBL_AMB_FORM", "K_B")]),
    (4, [("CHEMBL_NOKEY", None)]),
    (5, [("CHEMBL_UNKNOWN", "K_UNKNOWN")]),
    (6, [("CHEMBL_BRAND", "K_BRAND")]),
    (7, [("CHEMBL_BAD", "K_BAD")]),
    (8, [("CHEMBL_EMPTY", "K_EMPTY")]),
]
UNII_BY_KEY = {"K_SERT": ["U_SERT"], "K_SERT_HCL": ["U_SERT_HCL"],
               "K_SERT_HCL_ONLY": ["U_SERT_HCL"],
               "K_A": ["U_A", "U_B"], "K_B": ["U_B"], "K_UNKNOWN": ["U_NOBODY"],
               "K_BRAND": ["U_BRAND"], "K_BAD": ["U_BAD"], "K_EMPTY": ["U_EMPTY"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name) / "rxnav"
        self.fake = FakeRxNav()
        # U_EMPTY -> an IN that RxClass has nothing for.
        self.fake.unii["U_EMPTY"] = ["8888"]

    def rx(self, **kw):
        return fda.RxNav(cache_dir=self.dir, get=self.fake, **kw)


class ResolveTest(Base):
    def setUp(self):
        super().setUp()
        self.rows, self.labels, self.counts, self.detail = fda.resolve(
            MOLECULES, UNII_BY_KEY, self.rx())

    def mine(self, parent):
        return {(r[1], r[2]): r for r in self.rows if r[0] == parent}

    def test_full_chain_for_one_molecule(self):
        got = self.mine(1)
        self.assertEqual(set(got), {("fda_epc", "N0000175696"),
                                    ("fda_moa", "N0000000109"), ("fda_moa", "N0000182137"),
                                    ("fda_pe", "N0000009198")})
        epc = got[("fda_epc", "N0000175696")]
        self.assertEqual(epc[3], "")
        self.assertEqual(epc[4], "Serotonin Reuptake Inhibitor")
        # Both forms' UNIIs reached the one ingredient.
        self.assertEqual(epc[5], "UNII:U_SERT|UNII:U_SERT_HCL|RxCUI:36437|FDASPL")

    def test_pin_is_normalised_to_its_ingredient(self):
        got = self.mine(2)[("fda_epc", "N0000175696")]
        self.assertEqual(got[5], "UNII:U_SERT_HCL|RxCUI:36437|FDASPL")
        self.assertEqual(self.detail["ingredient"][2], "36437")

    def test_row_filter(self):
        codes = {r[2] for r in self.rows if r[0] == 1}
        self.assertNotIn("N0000111111", codes)        # ci_moa
        self.assertNotIn("D003866", codes)            # may_treat
        self.assertNotIn("N06AB", codes)              # ATC
        self.assertNotIn("N0000222222", codes)        # a PIN minConcept row
        # A class only DAILYMED asserts has no source here at all.
        self.assertNotIn("N0000999999", codes)

    def test_sources_merged_into_one_row(self):
        moa = self.mine(1)[("fda_moa", "N0000000109")]
        self.assertTrue(moa[5].endswith("|RxCUI:36437|FDASPL+MEDRT"))
        self.assertEqual(len([r for r in self.rows if r[0] == 1 and r[2] == "N0000000109"]), 1)
        self.assertTrue(self.mine(1)[("fda_pe", "N0000009198")][5].endswith("|MEDRT"))

    def test_ambiguous_dropped_and_listed(self):
        self.assertEqual(self.mine(3), {})
        self.assertEqual(self.detail["ambiguous"][3], {"1001": ["U_A"], "1002": ["U_B"]})
        # A PIN reaching two INs is not used, so that molecule is unresolved.
        self.assertEqual(self.mine(7), {})
        self.assertNotIn(7, self.detail["ambiguous"])
        self.assertEqual(self.counts["ambiguous_several_ingredients"], 1)

    def test_unresolved_cases(self):
        for parent in (4, 5, 6):
            self.assertEqual(self.mine(parent), {})
        self.assertEqual(self.counts["no_unii"], 1)
        self.assertEqual(self.counts["no_ingredient"], 3)   # unknown UNII, a brand, a PIN with two INs
        self.assertEqual(self.counts["has_unii"], 7)

    def test_ingredient_without_classes(self):
        self.assertEqual(self.mine(8), {})
        self.assertEqual(self.detail["ingredient"][8], "8888")
        self.assertEqual(self.counts["no_fda_class"], 1)

    def test_labels_cover_every_code_once(self):
        keys = [(r[1], r[2]) for r in self.rows]
        self.assertEqual(sorted(set(keys)), sorted((l[0], l[1]) for l in self.labels))
        for label in self.labels:
            self.assertIsNone(label[2])
            self.assertIsNone(label[4])

    def test_counts(self):
        self.assertEqual(self.counts["one_ingredient"], 3)
        self.assertEqual(self.counts["with_fda_epc"], 2)
        self.assertEqual(self.counts["with_fda_moa"], 2)
        self.assertEqual(self.counts["with_fda_pe"], 2)


class CacheTest(Base):
    def test_second_run_is_offline(self):
        rx = self.rx()
        fda.resolve(MOLECULES, UNII_BY_KEY, rx)
        rx.save()
        n = len(self.fake.calls)
        self.assertGreater(n, 0)
        rx2 = self.rx()
        fda.resolve(MOLECULES, UNII_BY_KEY, rx2)
        self.assertEqual(len(self.fake.calls), n)
        self.assertEqual(sum(rx2.asked.values()), 0)

    def test_refresh_asks_again(self):
        rx = self.rx()
        fda.resolve(MOLECULES, UNII_BY_KEY, rx)
        rx.save()
        n = len(self.fake.calls)
        fda.resolve(MOLECULES, UNII_BY_KEY, self.rx(refresh=True))
        self.assertEqual(len(self.fake.calls), 2 * n)

    def test_the_parent_decides_and_a_form_only_fills_in(self):
        # Theophylline's case: ChEMBL folds aminophylline onto it, and RxNorm
        # files aminophylline as an ingredient of its own. The parent's UNII
        # reaches one ingredient, so the form's other ingredient is not a doubt.
        mols = [(10, [("CHEMBL_THEO", "K_THEO"), ("CHEMBL_AMINO", "K_AMINO")]),
                (11, [("CHEMBL_NOPARENT", "K_NONE"), ("CHEMBL_FORM", "K_THEO")]),
                (12, [("CHEMBL_TWOFORMS", "K_NONE"), ("F1", "K_THEO"), ("F2", "K_AMINO")])]
        keys = {"K_THEO": ["U_A"], "K_AMINO": ["U_B"], "K_NONE": ["U_NOBODY"]}
        rows, _, counts, detail = fda.resolve(mols, keys, self.rx())
        self.assertEqual(detail["ingredient"][10], "1001")
        self.assertEqual([r[5] for r in rows if r[0] == 10], ["UNII:U_A|RxCUI:1001|FDASPL"])
        # No parent answer: a form fills in, but forms that disagree are refused.
        self.assertEqual(detail["ingredient"][11], "1001")
        self.assertEqual(detail["ambiguous"][12], {"1001": ["U_A"], "1002": ["U_B"]})
        self.assertEqual((counts["by_parent"], counts["by_form"]), (1, 1))  # 12 is dropped, not counted

    def test_failed_lookup_is_counted_and_not_cached(self):
        self.fake.fail = {"U_SERT_HCL"}
        rx = self.rx()
        rows, _, counts, detail = fda.resolve(MOLECULES, UNII_BY_KEY, rx)
        rx.save()
        # Molecules 1 and 2 both need U_SERT_HCL.
        self.assertEqual(counts["lookup_failed"], 2)
        self.assertEqual(sorted(detail["failed"]), [1, 2])
        self.assertNotIn(1, detail["ingredient"])
        self.assertEqual([r for r in rows if r[0] in (1, 2)], [])
        self.assertNotIn("U_SERT_HCL", json.loads((self.dir / "unii_rxcui.json").read_text()))
        # Healed on the next run, and only the failed lookup is asked again.
        self.fake.fail = set()
        self.fake.calls.clear()
        rows, _, counts, _ = fda.resolve(MOLECULES, UNII_BY_KEY, self.rx())
        self.assertEqual(counts["lookup_failed"], 0)
        self.assertTrue(any(r[0] == 1 for r in rows))
        self.assertFalse(any("U_A" in c for c in self.fake.calls))

    def test_malformed_answer_is_a_failure(self):
        rx = fda.RxNav(cache_dir=self.dir, get=lambda url, params=None: {"rxclassDrugInfoList": {
            "rxclassDrugInfo": [{"minConcept": {}}]}})
        with self.assertRaises(fda.RxNavError):
            rx.classes("36437")
        self.assertEqual(rx.cache["classes"], {})


class BackfillTest(Base):
    def setUp(self):
        super().setUp()
        self.conn = new_db()
        self.addCleanup(self.conn.close)
        for parent, structs in MOLECULES:
            add_molecule(self.conn, parent, structs[0][0], structs[0][1])
        self.conn.execute(
            "INSERT INTO molecule_classes(parent_molregno, source, code, subgroup, label, carriers)"
            " VALUES (1, 'mesh_pa', 'D000001', '', 'Some PA', 'CID:1')")
        self.conn.execute(
            "INSERT INTO class_labels(source, code, level, label, parents)"
            " VALUES ('mesh_pa', 'D000001', 4, 'Some PA', NULL)")
        # A stale row of this backfill's own, which the rerun must remove.
        self.conn.execute(
            "INSERT INTO molecule_classes(parent_molregno, source, code, subgroup, label, carriers)"
            " VALUES (3, 'fda_epc', 'NSTALE', '', 'Stale', 'x')")
        self.conn.execute(
            "INSERT INTO class_labels(source, code, level, label, parents)"
            " VALUES ('fda_epc', 'NSTALE', NULL, 'Stale', NULL)")

    def run_backfill(self, manifest=None):
        return fda.backfill(self.conn, MOLECULES, UNII_BY_KEY, self.rx(), manifest or {})

    def snapshot(self, sources):
        marks = ",".join("?" * len(sources))
        return (sorted(self.conn.execute(
                    f"SELECT * FROM molecule_classes WHERE source IN ({marks})", sources)),
                sorted(self.conn.execute(
                    f"SELECT * FROM class_labels WHERE source IN ({marks})", sources)))

    def test_writes_only_its_own_sources(self):
        summary, *_ = self.run_backfill()
        sources = {r[0] for r in self.conn.execute("SELECT DISTINCT source FROM molecule_classes")}
        self.assertEqual(sources, {"mesh_pa", "fda_epc", "fda_moa", "fda_pe"})
        self.assertEqual(self.snapshot(("mesh_pa",)),
                         ([(1, "mesh_pa", "D000001", "", "Some PA", "CID:1")],
                          [("mesh_pa", "D000001", 4, "Some PA", None)]))
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM molecule_classes WHERE code = 'NSTALE'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM class_labels WHERE code = 'NSTALE'").fetchone()[0], 0)
        self.assertEqual(summary["rows_changed"], summary["rows"] + 1)
        self.assertEqual(summary["rows_by_source"], {"fda_epc": 2, "fda_moa": 4, "fda_pe": 2})

    def test_idempotent(self):
        self.run_backfill()
        first = self.snapshot(fda.SOURCES)
        summary, *_ = self.run_backfill()
        self.assertEqual(summary["rows_changed"], 0)
        self.assertEqual(self.snapshot(fda.SOURCES), first)

    def test_manifest(self):
        summary, *_ = self.run_backfill({"unii_archive_sha256": "abc"})
        stored = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'fda_pharmacologic_classes'").fetchone()[0])
        self.assertEqual(stored["unii_archive_sha256"], "abc")
        self.assertEqual(stored["dropped_ambiguous"],
                         {"CHEMBL_AMB": {"1001": ["U_A"], "1002": ["U_B"]}})
        self.assertEqual(stored["counts"]["no_unii"], 1)
        self.assertEqual(set(stored["rxnav_cache_sha256"]),
                         {"unii_rxcui", "tty", "to_ingredient", "classes"})
        self.assertEqual(stored["rows"], summary["rows"])


class MainTest(Base):
    """main() against a temp database, with the file and ChEMBL seams patched."""

    def run_main(self, *args):
        db = pathlib.Path(self.tmp.name) / "cohort.db"
        if not db.exists():
            conn = sqlite3.connect(db)
            conn.executescript(SCHEMA)
            for parent, structs in MOLECULES:
                add_molecule(conn, parent, structs[0][0], structs[0][1])
            conn.commit()
            conn.close()
        self.db = db
        unii = pathlib.Path(self.tmp.name) / "unii.zip"
        with mock.patch.object(fda.mesh_struct, "ensure_unii_file", return_value=unii), \
             mock.patch.object(fda.mesh_struct, "load_unii",
                               return_value=(UNII_BY_KEY, "UNII_Records.txt")), \
             mock.patch.object(fda.mesh_struct, "structures_for", return_value=MOLECULES), \
             mock.patch.object(fda.common, "chembl", return_value=mock.MagicMock()), \
             mock.patch.object(fda.common, "sha256", return_value="sha"), \
             mock.patch.object(fda, "CACHE_DIR", self.dir), \
             mock.patch.object(fda, "http_get", self.fake), \
             mock.patch("builtins.print"):
            return fda.main(["--db", str(db), *args])

    def count(self):
        conn = sqlite3.connect(self.db)
        try:
            return (conn.execute("SELECT COUNT(*) FROM molecule_classes").fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM build_manifest"
                                 " WHERE key = 'fda_pharmacologic_classes'").fetchone()[0])
        finally:
            conn.close()

    def test_dry_run_writes_nothing_then_real_run_writes(self):
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertEqual(self.count(), (0, 0))
        self.assertTrue((self.dir / "classes.json").exists())      # the HTTP cache may fill
        self.run_main()
        rows, manifest = self.count()
        self.assertGreater(rows, 0)
        self.assertEqual(manifest, 1)
        self.fake.calls.clear()
        self.run_main()                                           # offline rerun
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.count(), (rows, 1))


if __name__ == "__main__":
    unittest.main()
