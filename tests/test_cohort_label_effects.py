"""Offline tests for scripts/resolve_cohort_label_effects.py.

The ADReCS ontology (.xlsx) and the OnSIDES release (.zip) are built in the
test from a handful of rows, in temp files; the database is an in-memory copy of
db/schema_cohort.sql. The network, db/cohort1.db, ChEMBL and db/cache/ are never
touched.

Run with: python3 -m unittest discover -s tests
"""

import csv
import io
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from xml.sax.saxutils import escape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_label_effects as le  # noqa: E402
from cohort import common  # noqa: E402

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql"
SCHEMA = SCHEMA_PATH.read_text()

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
HEADER = ["ADRECS_ID", "ADR_ID", "ADR_TERM", "ADR_SYNONYMS", "MEDDRA_CODE"]

SOC_NERVOUS, SOC_PSYCH, SOC_GI = "10029205", "10037175", "10017947"

# (position, adr_id, term, synonyms, meddra code)
ADRECS_ROWS = [
    ("17", "S17", "Nervous system disorders", "Not Available", SOC_NERVOUS),
    ("19", "S19", "Psychiatric disorders", "Not Available", SOC_PSYCH),
    ("07", "S07", "Gastrointestinal disorders", "Not Available", SOC_GI),
    ("17.01", "G1", "Headaches", "Not Available", "20000001"),         # HLGT, one dot
    ("17.01.01", "H1", "Headaches NEC", "Not Available", "30000001"),  # HLT, two dots
    # PTs (three dots)
    ("17.01.01.001", "P1", "Headache", "Cephalalgia | Head pain", "1001"),
    ("17.02.01.001", "P2", "Seizure", "Fit | Convulsion", "1002"),
    ("17.02.01.002", "P3", "Epilepsy", "Convulsion", "1003"),          # 'Convulsion' again, same SOC
    ("07.01.01.001", "P4", "Nausea", "Queasiness | Dizzy feeling", "1004"),  # GI only
    ("17.03.01.001", "P5", "Dizziness", "Dizzy feeling", "1005"),      # CNS; shares an LLT with Nausea
    ("19.01.01.001", "P6", "Insomnia", "Not Available", "1006"),       # multi-axial: psych...
    ("17.04.01.001", "P6", "Insomnia", "Not Available", "1006"),       # ...and nervous
]


def write_xlsx(path, rows, header=HEADER):
    """A minimal .xlsx: one sheet, inline strings, no sharedStrings.xml."""
    def cell(col, r, text):
        return f'<c r="{col}{r}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
    body = []
    for i, row in enumerate([header] + [list(r) for r in rows], start=1):
        cells = "".join(cell("ABCDE"[j], i, v) for j, v in enumerate(row))
        body.append(f'<row r="{i}">{cells}</row>')
    sheet = (f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}">'
             f'<sheetData>{"".join(body)}</sheetData></worksheet>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


# Ingredients 100 and 200 are wanted; 300 is not. Products p1,p2 are 100; p3 is
# 200; p4 is 300; a combination label covers p5 (200) and p6 (100).
PRODUCT_LABEL = [("L1", "US", "x", "1", "u"), ("L2", "UK", "x", "2", "u"),
                 ("L3", "US", "x", "3", "u"), ("L4", "US", "x", "4", "u"),
                 ("L5", "JP", "x", "5", "u")]
# v3.1.1's real column order: product first, opposite to the schema's.
ING_TO_PRODUCT = [("p1", "100"), ("p2", "100"), ("p3", "200"), ("p4", "300"),
                  ("p5", "200"), ("p6", "100")]
PRODUCT_TO_RXNORM = [("L1", "p1"), ("L2", "p2"), ("L3", "p3"), ("L4", "p4"),
                     ("L5", "p5"), ("L5", "p6")]
ADVERSE = [
    # L1 lists the LLT 'Cephalalgia' and the PT 'Headache' it is placed as.
    ("L1", "e1", "AR", "1001", "m", "0", "0"),
    ("L1", "e2", "AR", "9001", "m", "0", "0"),
    ("L2", "e3", "WP", "1001", "m", "0", "0"),
    ("L2", "e4", "AR", "9002", "m", "0", "0"),   # 'Convulsion', several PTs
    ("L3", "e5", "AR", "1005", "m", "0", "0"),
    ("L3", "e6", "AR", "5555", "m", "0", "0"),   # a code ADReCS lacks
    ("L3", "e7", "AR", "", "m", "0", "0"),       # no MedDRA id: skipped
    ("L4", "e8", "AR", "1001", "m", "0", "0"),   # ingredient 300: not wanted
    ("L5", "e9", "AR", "1001", "m", "0", "0"),   # a combination label
]
VOCAB = [("1001", "Headache", "PT"), ("9001", "Cephalalgia", "LLT"),
         ("9002", "Convulsion", "LLT"), ("1005", "Dizziness", "PT"),
         ("5555", "Mystery", "PT"), ("9999", "Never used", "PT")]


def write_onsides(path):
    files = {
        "product_label": csv_text(["label_id", "source", "source_product_name",
                                   "source_product_id", "source_label_url"], PRODUCT_LABEL),
        "vocab_rxnorm_ingredient_to_product": csv_text(["product_id", "ingredient_id"], ING_TO_PRODUCT),
        "product_to_rxnorm": csv_text(["label_id", "rxnorm_product_id"], PRODUCT_TO_RXNORM),
        "product_adverse_effect": csv_text(
            ["product_label_id", "effect_id", "label_section", "effect_meddra_id",
             "match_method", "pred0", "pred1"], ADVERSE),
        "vocab_meddra_adverse_effect": csv_text(["meddra_id", "meddra_name", "meddra_term_type"], VOCAB),
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(f"csv/{name}.csv", text)


def new_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    # The schema turns foreign keys on; label_effects rows need their parent.
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, inchikey, in_cohort,"
        " is_seed, route_atc_n, route_indication, admission_reason)"
        " VALUES (10, 'CHEMBL10', 'KEY', 0, 0, 0, 0, 'seed_only')")
    return conn


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.xlsx = self.dir / "adrecs.xlsx"
        write_xlsx(self.xlsx, ADRECS_ROWS)
        self.zip = self.dir / "onsides.zip"
        write_onsides(self.zip)
        self.h = le.load_hierarchy(self.xlsx)


class LoadHierarchyTests(Base):
    def test_soc_codes_map_to_names(self):
        """The SOC filter of the answer key is keyed by MedDRA code, so the
        position ('17') must be translated to the code and the name kept."""
        self.assertEqual(self.h["soc"], {SOC_NERVOUS: "Nervous system disorders",
                                         SOC_PSYCH: "Psychiatric disorders",
                                         SOC_GI: "Gastrointestinal disorders"})

    def test_only_three_dot_rows_are_pts(self):
        """HLGT and HLT rows (one and two dots) must not be mistaken for PTs."""
        self.assertEqual(set(self.h["pt"]), {"1001", "1002", "1003", "1004", "1005", "1006"})

    def test_multiaxial_pt_has_every_soc(self):
        """MedDRA is multi-axial; a PT filed under two SOCs must carry both,
        or a psychiatric-and-nervous effect is lost to one filter."""
        self.assertEqual(self.h["pt"]["1006"]["socs"], {SOC_NERVOUS, SOC_PSYCH})
        self.assertEqual(self.h["pt"]["1001"]["socs"], {SOC_NERVOUS})

    def test_synonyms_are_lowercase_and_include_the_pt_name(self):
        """LLT lookup is by exact lower-cased name; 'Not Available' is no name."""
        syn = self.h["synonym"]
        self.assertEqual(syn["cephalalgia"], {"1001"})
        self.assertEqual(syn["head pain"], {"1001"})
        self.assertEqual(syn["headache"], {"1001"})
        self.assertEqual(syn["convulsion"], {"1002", "1003"})
        self.assertNotIn("not available", syn)
        self.assertTrue(all(k == k.lower() for k in syn))

    def test_wrong_header_raises_pinerror(self):
        """A different workbook must be refused, not read as garbage."""
        bad = self.dir / "bad.xlsx"
        write_xlsx(bad, ADRECS_ROWS, header=["A", "B", "C", "D", "E"])
        with self.assertRaises(le.PinError):
            le.load_hierarchy(bad)


class PlaceTermTests(Base):
    def test_known_pt(self):
        """A PT ADReCS has is its own effect with all its SOCs."""
        self.assertEqual(le.place_term("1006", "Insomnia", "PT", self.h),
                         ("1006", "pt", {SOC_NERVOUS, SOC_PSYCH}))

    def test_pt_code_adrecs_lacks_is_unplaced(self):
        """No guessing by name for a PT: an unknown code stays unplaced."""
        self.assertEqual(le.place_term("5555", "Headache", "PT", self.h),
                         ("5555", "unplaced", set()))

    def test_llt_naming_one_pt_is_counted_as_it(self):
        """'Paresthesia' vs 'Paraesthesia' must be one effect."""
        self.assertEqual(le.place_term("9001", "Cephalalgia", "LLT", self.h),
                         ("1001", "llt_one", {SOC_NERVOUS}))

    def test_llt_name_match_ignores_case_and_padding(self):
        self.assertEqual(le.place_term("9001", "  CEPHALALGIA ", "LLT", self.h)[1], "llt_one")

    def test_llt_naming_several_pts_keeps_own_code_and_shared_socs(self):
        """Never resolved to one candidate; SOCs are what holds for any."""
        self.assertEqual(le.place_term("9002", "Convulsion", "LLT", self.h),
                         ("9002", "llt_several", {SOC_NERVOUS}))

    def test_llt_with_gi_only_candidate_has_no_shared_soc(self):
        """'Dizzy feeling' may be Nausea (GI) or Dizziness (CNS): claiming
        nervous-system would be wrong for one reading, so SOCs are empty."""
        self.assertEqual(le.place_term("9003", "Dizzy feeling", "LLT", self.h),
                         ("9003", "llt_several", set()))

    def test_unknown_llt_is_unplaced(self):
        self.assertEqual(le.place_term("9004", "No such term", "LLT", self.h),
                         ("9004", "unplaced", set()))


class ReadOnsidesTests(Base):
    def test_combination_labels_skipped_and_counted(self):
        """A combination's effects are its partner's too, so L5 (ingredients
        100 and 200) is not read for either, and is counted."""
        labels, effects, terms, counts = le.read_onsides(self.zip, {"100", "200"})
        self.assertEqual(counts["labels_combination"], 1)
        self.assertNotIn("L5", effects["100"]["1001"])
        self.assertNotIn("L5", effects["200"].get("1001", {}))

    def test_labels_counted_per_country(self):
        labels, _, _, counts = le.read_onsides(self.zip, {"100", "200"})
        self.assertEqual(dict(labels["100"]), {"US": 1, "UK": 1})
        self.assertEqual(dict(labels["200"]), {"US": 1})
        self.assertEqual(counts["labels_read"], 3)

    def test_effect_label_section_structure(self):
        _, effects, _, counts = le.read_onsides(self.zip, {"100", "200"})
        self.assertEqual(effects["100"]["1001"], {"L1": {"AR"}, "L2": {"WP"}})
        self.assertEqual(effects["100"]["9001"], {"L1": {"AR"}})
        self.assertEqual(effects["200"]["1005"], {"L3": {"AR"}})
        self.assertNotIn("", effects["200"])  # an empty MedDRA id is no effect
        self.assertEqual(counts["effect_rows_read"], 6)

    def test_only_wanted_ingredients_are_read(self):
        """The release is large; ingredients the catalogue does not reach
        must not be loaded or counted (L4 is ingredient 300)."""
        labels, effects, terms, counts = le.read_onsides(self.zip, {"100"})
        self.assertEqual(set(labels), {"100"})
        self.assertEqual(set(effects), {"100"})
        self.assertEqual(counts["labels_read"], 2)
        self.assertEqual(set(terms), {"1001", "9001", "9002"})

    def test_columns_read_by_name_despite_swapped_order(self):
        """v3.1.1's ingredient-to-product file has product_id first; reading
        by position would map products to the wrong side."""
        _, _, terms, _ = le.read_onsides(self.zip, {"100", "200"})
        self.assertEqual(terms["9002"], ("Convulsion", "LLT"))
        labels, _, _, _ = le.read_onsides(self.zip, {"100"})
        self.assertEqual(sum(labels["100"].values()), 2)


class ResolveTests(Base):
    def run_resolve(self, ingredient_of):
        labels, effects, terms, _ = le.read_onsides(self.zip, set(ingredient_of.values()))
        return le.resolve(ingredient_of, labels, effects, terms, self.h)

    def test_llt_and_its_pt_count_once_per_label(self):
        """L1 lists Cephalalgia (-> Headache) and Headache: one effect on one
        label, else a label's wording would double its weight."""
        mol, eff, _ = self.run_resolve({10: "100"})
        headache = [r for r in eff if r[1] == "1001"]
        self.assertEqual(len(headache), 1)
        # L1 (both terms) and L2 (the PT): two labels, not three.
        self.assertEqual(headache[0], (10, "1001", 2, "AR|WP"))

    def test_n_labels_is_labels_listing_the_effect_and_sections_sorted(self):
        _, eff, _ = self.run_resolve({10: "100"})
        by_effect = {r[1]: r for r in eff}
        self.assertEqual(by_effect["9002"], (10, "9002", 1, "AR"))
        self.assertEqual(by_effect["1001"][3], "AR|WP")

    def test_molecule_row(self):
        mol, _, _ = self.run_resolve({10: "100"})
        self.assertEqual(mol, [(10, "100", 2, "UK:1|US:1")])

    def test_two_parents_one_ingredient_get_identical_rows(self):
        """RxNorm files a drug and its ester as one ingredient; both parents
        carry the same rows and the answer key decides what that means."""
        mol, eff, _ = self.run_resolve({10: "100", 11: "100"})
        strip = lambda rows: [r[1:] for r in rows]
        self.assertEqual(strip([r for r in mol if r[0] == 10]), strip([r for r in mol if r[0] == 11]))
        self.assertEqual(strip([r for r in eff if r[0] == 10]), strip([r for r in eff if r[0] == 11]))
        self.assertTrue([r for r in eff if r[0] == 11])

    def test_parent_without_labels_gets_no_molecule_row(self):
        """No labels means nothing known, not 'no adverse effects'."""
        mol, eff, _ = self.run_resolve({10: "100", 13: "400"})
        self.assertEqual([r[0] for r in mol], [10])
        self.assertFalse([r for r in eff if r[0] == 13])

    def test_term_rows_carry_placement_and_socs(self):
        _, _, terms = self.run_resolve({10: "100", 12: "200"})
        by = {r[0]: r for r in terms}
        self.assertEqual(by["1001"], ("1001", "PT", "Headache", "1001", "pt", SOC_NERVOUS))
        self.assertEqual(by["9001"], ("9001", "LLT", "Cephalalgia", "1001", "llt_one", SOC_NERVOUS))
        self.assertEqual(by["9002"][4:], ("llt_several", SOC_NERVOUS))
        self.assertEqual(by["5555"], ("5555", "PT", "Mystery", "5555", "unplaced", None))
        self.assertNotIn("9999", by)

    def test_socs_are_joined_sorted(self):
        """Multi-SOC placements are '|'-joined in sorted order."""
        terms = {"1006": ("Insomnia", "PT")}
        _, _, rows = le.resolve({}, {}, {}, terms, self.h)
        self.assertEqual(rows[0][5], "|".join(sorted([SOC_NERVOUS, SOC_PSYCH])))


class WriteTests(unittest.TestCase):
    MOL = [(10, "100", 2, "UK:1|US:1")]
    EFF = [(10, "1001", 2, "AR|WP")]
    TERM = [("1001", "PT", "Headache", "1001", "pt", SOC_NERVOUS)]

    def test_rows_land(self):
        conn = new_db()
        le.write(conn, self.MOL, self.EFF, self.TERM)
        self.assertEqual(conn.execute("SELECT * FROM label_effect_molecules").fetchall(), self.MOL)
        self.assertEqual(conn.execute("SELECT * FROM label_effects").fetchall(), self.EFF)
        self.assertEqual(conn.execute("SELECT * FROM label_effect_terms").fetchall(), self.TERM)

    def test_second_identical_write_changes_nothing(self):
        """Idempotence is how a rerun proves it reproduced the last run."""
        conn = new_db()
        self.assertEqual(le.write(conn, self.MOL, self.EFF, self.TERM), 3)
        self.assertEqual(le.write(conn, self.MOL, self.EFF, self.TERM), 0)

    def test_stale_rows_are_replaced(self):
        conn = new_db()
        le.write(conn, self.MOL, self.EFF, self.TERM)
        self.assertEqual(le.write(conn, [], [], []), 3)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM label_effects").fetchone()[0], 0)

    def _schema_without_tables(self):
        text = SCHEMA
        for table in le.TABLES:
            text = re.sub(r"CREATE TABLE IF NOT EXISTS " + table + r" \(.*?\n\);", "", text, flags=re.S)
        return text

    def test_ensure_tables_creates_missing_tables(self):
        """A database built before these tables existed must still be
        backfilled, without a rebuild."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(self._schema_without_tables())
        names = lambda: {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(names() & set(le.TABLES))
        le.ensure_tables(conn)  # reads the real schema via common.DB
        self.assertTrue(set(le.TABLES) <= names())

    def test_ensure_tables_raises_when_schema_lacks_them(self):
        """A schema that cannot create the tables is a policy error, not a
        silent no-op followed by an obscure INSERT failure."""
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "schema_cohort.sql").write_text(self._schema_without_tables())
            conn = sqlite3.connect(":memory:")
            conn.executescript(self._schema_without_tables())
            with mock.patch.object(common, "DB", pathlib.Path(d)):
                with self.assertRaises(common.PolicyError):
                    le.ensure_tables(conn)


class EnsurePinnedTests(unittest.TestCase):
    def test_wrong_checksum_refused_without_network(self):
        """A file that is not the pinned release is refused and never
        re-downloaded over: changing the pin is the only way to adopt another."""
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "pinned.bin"
            path.write_bytes(b"not the release")
            with mock.patch("requests.get",
                            side_effect=AssertionError("network must not be called")) as get:
                with self.assertRaises(le.PinError):
                    le.ensure_pinned(path, "http://example.invalid/x", "0" * 64)
            get.assert_not_called()
            self.assertEqual(path.read_bytes(), b"not the release")

    def test_matching_checksum_returns_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "pinned.bin"
            path.write_bytes(b"release")
            sha = common.sha256(path)
            with mock.patch("requests.get", side_effect=AssertionError("network")):
                self.assertEqual(le.ensure_pinned(path, "http://example.invalid/x", sha), path)


if __name__ == "__main__":
    unittest.main()
