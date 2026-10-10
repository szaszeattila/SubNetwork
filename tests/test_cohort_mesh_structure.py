"""Offline tests for scripts/resolve_cohort_mesh_structure.py.

These lock in the parts of the MeSH structure-class backfill that need no
network: the FDA UNII records parser (`load_unii`), the MeSH descriptor and
supplementary-record parser restricted to a `wanted_uniis` set (`load_mesh`),
the structural-branch hierarchy walk (`parents_of` / `own_classes` /
`label_rows`), the resolution rules in `resolve` (parent-before-form, the
ambiguity rule, the "filed under its own heading" rule), and that `backfill`
only ever touches its own 'mesh_struct' rows of molecule_classes / class_labels
(scripts/cohort/classes.py's SOURCES contract - each writer owns its own
sources).

No network access: this script's only network seams are the file downloaders
(`_download`, `ensure_supp_file`, `ensure_unii_file`) and `structures_for`,
which reads the local ChEMBL release through `common.chembl()`. None of those
are exercised here - every fixture is a tiny hand-built XML or TSV file on
disk, and `resolve`/`backfill` are called directly with those parsed
structures. This test never opens db/cohort1.db; every sqlite fixture here is
an in-memory database built from db/schema_cohort.sql.

Run with: python3 -m unittest discover -s tests
"""

import gzip
import itertools
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_mesh_structure as rms  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

_molregno = itertools.count(1)


# ------------------------------------------------------------------- MeSH
#
# A small fixture inside the structural branches (D01-D05, D09, D10, D12,
# D13), built to model the docstring's own example - caffeine's "Xanthines"
# filed under both Alkaloids (D03.132) and Purinones (D03.633.100.759.758) -
# plus every other rule this module states:
#
#   D002098  Alkaloids                D03.132                       depth 2 (MIN_DEPTH)
#   D011744  Purinones                D03.633.100.759.758           depth 5
#   D014283  Xanthines                D03.132.436                   depth 3   } filed
#                                      D03.633.100.759.758.400       depth 6   } twice
#   D002110  Caffeine                 D03.132.436.077                depth 4  (+ a D27
#                                                                     tree, which must
#                                                                     be ignored)
#   D700001  Theobromine              D03.132.436.100                depth 4
#   D700002  Pentoxifylline           D03.132.436.100.055            depth 5  (direct
#                                                                     class: Theobromine)
#   D760001  TopClass (fixture)       D03.132.500                    depth 3
#   D760002  MidClass2 (fixture)      D03.132.500.200                depth 4
#   D760003  LeafMolecule (fixture)   D03.132.500.200.010            depth 5  (direct
#                                                                     class: MidClass2;
#                                                                     TopClass is only
#                                                                     an ancestor of it)
#   D800001  LonelyDrug (fixture)     D03.132.436.900                depth 4  (a class
#                                                                     nobody else uses)
#   D900001  NoClassChemical (fixture) D01                           depth 1  (no dot:
#                                                                     reaches no parent)
#   D999003  Organic Chemicals (fixture root) D03                    depth 1  (must never
#                                                                     surface as a parent)
#   D999026  Some Pharmaceutical Prep (fixture) D26.100               (D26 is not a
#                                                                     structural branch)
#   D600001  Some Hormonal Thing (fixture) D06.472                   (D06 is not a
#                                                                     structural branch)
#   D750001/2/3  FormTest* (fixture) D03.132.436.15{0,1} / .160      depth 4  (three
#                                                                     interchangeable
#                                                                     leaves under
#                                                                     Xanthines, used
#                                                                     only to test which
#                                                                     structure/form's
#                                                                     UNII gets tried)
#
# Registry numbers (FDA UNIIs) are attached to the descriptors that stand for
# a *molecule's own record*, never to a class descriptor a molecule is merely
# filed under (except Alkaloids/Purinones, which carry UNII-A/UNII-B purely to
# give the ambiguity test two distinct, real records to land on).
#
# A supplementary-record fixture models a MeSH heading reached only through
# "Heading Mapped To", never through the tree itself:
#
#   C999001  SaltForm (fixture)     UNII-SALT       -> *D014283 (Xanthines, kept,
#                                                       leading "*" stripped),
#                                                      D999026 (dropped: not
#                                                       structural), D999003
#                                                       (dropped: depth 1)
#   C999002  UnwantedSalt (fixture) UNII-UNWANTED   -> D014283 (irrelevant: the
#                                                       whole record is dropped
#                                                       because its only UNII is
#                                                       not in `wanted_uniis`)

_DESCRIPTORS = [
    # (UI, name, tree numbers, registry numbers)
    ("D002098", "Alkaloids (fixture)", ["D03.132"], ["UNII-A"]),
    ("D011744", "Purinones (fixture)", ["D03.633.100.759.758"], ["UNII-B"]),
    ("D014283", "Xanthines (fixture)",
     ["D03.132.436", "D03.633.100.759.758.400"], []),
    ("D002110", "Caffeine (fixture)",
     ["D03.132.436.077", "D27.505.696.577.780"], ["UNII-CAFF"]),
    ("D700001", "Theobromine (fixture)", ["D03.132.436.100"], ["UNII-THEO"]),
    ("D700002", "Pentoxifylline (fixture)", ["D03.132.436.100.055"], ["UNII-PENTOX"]),
    ("D760001", "TopClass (fixture)", ["D03.132.500"], ["UNII-TOPCLASS"]),
    ("D760002", "MidClass2 (fixture)", ["D03.132.500.200"], []),
    ("D760003", "LeafMolecule (fixture)", ["D03.132.500.200.010"], ["UNII-LEAF"]),
    ("D800001", "LonelyDrug (fixture)", ["D03.132.436.900"], ["UNII-LONELY"]),
    ("D900001", "NoClassChemical (fixture)", ["D01"], ["UNII-NOCLASS"]),
    ("D999003", "Organic Chemicals (fixture root)", ["D03"], []),
    ("D999026", "Some Pharmaceutical Prep (fixture)", ["D26.100"], []),
    ("D600001", "Some Hormonal Thing (fixture)", ["D06.472"], []),
    ("D750001", "FormTestDrug (fixture)", ["D03.132.436.150"], ["UNII-FORMTEST-PARENT"]),
    ("D750002", "FormTestDrugFormUnused (fixture)", ["D03.132.436.151"],
     ["UNII-FORMTEST-FORM-UNUSED"]),
    ("D750003", "FormTestDrugForm2 (fixture)", ["D03.132.436.160"], ["UNII-FORMTEST-FORM2"]),
]

_SUPPLEMENTARY = [
    # (UI, name, registry numbers, mapped headings - "*" marks a major heading)
    ("C999001", "SaltForm (fixture)", ["UNII-SALT"], ["*D014283", "D999026", "D999003"]),
    ("C999002", "UnwantedSalt (fixture)", ["UNII-UNWANTED"], ["D014283"]),
]

# Every UNII any fixture record carries, except UNII-UNWANTED - which is
# deliberately left out of `wanted_uniis` everywhere below, so that its own
# supplementary record (C999002) and its registry number both prove the "not
# wanted is ignored" rule rather than needing a second, separate parse.
WANTED = frozenset({
    "UNII-A", "UNII-B", "UNII-CAFF", "UNII-THEO", "UNII-PENTOX", "UNII-TOPCLASS",
    "UNII-LEAF", "UNII-LONELY", "UNII-NOCLASS", "UNII-SALT",
    "UNII-FORMTEST-PARENT", "UNII-FORMTEST-FORM-UNUSED", "UNII-FORMTEST-FORM2",
})


def _desc_xml_bytes(descriptors=_DESCRIPTORS):
    parts = ["<DescriptorRecordSet>"]
    for ui, name, trees, registries in descriptors:
        tree_xml = "".join(f"<TreeNumber>{t}</TreeNumber>" for t in trees)
        reg_xml = "".join(f"<RegistryNumber>{r}</RegistryNumber>" for r in registries)
        parts.append(
            "<DescriptorRecord>"
            f"<DescriptorUI>{ui}</DescriptorUI>"
            f"<DescriptorName><String>{name}</String></DescriptorName>"
            f"<TreeNumberList>{tree_xml}</TreeNumberList>"
            f"<ConceptList><Concept><RegistryNumberList>{reg_xml}"
            "</RegistryNumberList></Concept></ConceptList>"
            "</DescriptorRecord>")
    parts.append("</DescriptorRecordSet>")
    return "".join(parts).encode("utf-8")


def _supp_xml_bytes(records=_SUPPLEMENTARY):
    parts = ["<SupplementalRecordSet>"]
    for ui, name, registries, mapped in records:
        reg_xml = "".join(f"<RegistryNumber>{r}</RegistryNumber>" for r in registries)
        mapped_xml = "".join(
            "<HeadingMappedTo><DescriptorReferredTo>"
            f"<DescriptorUI>{m}</DescriptorUI>"
            "</DescriptorReferredTo></HeadingMappedTo>" for m in mapped)
        parts.append(
            "<SupplementalRecord>"
            f"<SupplementalRecordUI>{ui}</SupplementalRecordUI>"
            f"<SupplementalRecordName><String>{name}</String></SupplementalRecordName>"
            f"<ConceptList><Concept><RegistryNumberList>{reg_xml}"
            "</RegistryNumberList></Concept></ConceptList>"
            f"<HeadingMappedToList>{mapped_xml}</HeadingMappedToList>"
            "</SupplementalRecord>")
    parts.append("</SupplementalRecordSet>")
    return "".join(parts).encode("utf-8")


def _write(tmpdir, name, data):
    path = pathlib.Path(tmpdir) / name
    path.write_bytes(data)
    return path


def _mesh(wanted=WANTED, descriptors=_DESCRIPTORS, supp=_SUPPLEMENTARY):
    """Parse the fixture through the real load_mesh, so every other test
    exercises the same code path LoadMeshTest checks directly."""
    with tempfile.TemporaryDirectory() as d:
        desc_path = _write(d, "desc-fixture.xml", _desc_xml_bytes(descriptors))
        supp_path = _write(d, "supp-fixture.xml", _supp_xml_bytes(supp))
        return rms.load_mesh(desc_path, supp_path, wanted)


# ---------------------------------------------------------------- load_unii

_UNII_ROWS = [
    ("UNII", "DISPLAY_NAME", "INCHIKEY"),
    ("UNII-CAFF", "CAFFEINE", "RYYVLZVUVIJVGH-UHFFFAOYSA-N"),
    ("UNII-THEO", "THEOBROMINE", "YAPQBXQYLJRXSA-UHFFFAOYSA-N"),
    ("UNII-DUP1", "SOME SALT", "ZZZZZZKEY-UHFFFAOYSA-N"),
    ("UNII-DUP2", "SOME SALT HYDRATE", "ZZZZZZKEY-UHFFFAOYSA-N"),
    ("UNII-NOKEY", "NO STRUCTURE RECORDED", ""),
]


def _unii_text(rows=_UNII_ROWS):
    return "\n".join("\t".join(r) for r in rows) + "\n"


class LoadUniiTest(unittest.TestCase):
    def test_reads_a_bare_records_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "UNII_Records_26Sep2026.txt", _unii_text().encode("utf-8"))
            mapping, member = rms.load_unii(path)

        self.assertEqual(mapping, {
            "RYYVLZVUVIJVGH-UHFFFAOYSA-N": ["UNII-CAFF"],
            "YAPQBXQYLJRXSA-UHFFFAOYSA-N": ["UNII-THEO"],
            "ZZZZZZKEY-UHFFFAOYSA-N": ["UNII-DUP1", "UNII-DUP2"],
        })
        self.assertEqual(member, "UNII_Records_26Sep2026.txt")

    def test_skips_rows_with_no_inchikey(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "records.txt", _unii_text().encode("utf-8"))
            mapping, _ = rms.load_unii(path)
        self.assertNotIn("", mapping)
        for uniis in mapping.values():
            self.assertNotIn("UNII-NOKEY", uniis)

    def test_reads_the_one_records_file_inside_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            zpath = pathlib.Path(d) / "UNII_Data.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("UNII_Records_26Sep2026.txt", _unii_text())
                zf.writestr("some_other_file.txt", "irrelevant")
            mapping, member = rms.load_unii(zpath)

        self.assertEqual(mapping["RYYVLZVUVIJVGH-UHFFFAOYSA-N"], ["UNII-CAFF"])
        self.assertEqual(member, "UNII_Records_26Sep2026.txt")

    def test_a_zip_with_more_than_one_candidate_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            zpath = pathlib.Path(d) / "UNII_Data.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("UNII_Records_26Sep2026.txt", _unii_text())
                zf.writestr("UNII_Records_Old.txt", _unii_text())
            with self.assertRaises(SystemExit):
                rms.load_unii(zpath)


# ---------------------------------------------------------------- load_mesh

class LoadMeshTest(unittest.TestCase):
    def test_reads_gzipped_and_plain_fixtures_identically(self):
        desc_xml = _desc_xml_bytes()
        supp_xml = _supp_xml_bytes()
        with tempfile.TemporaryDirectory() as d:
            desc_plain = _write(d, "desc.xml", desc_xml)
            desc_gz = _write(d, "desc.gz", gzip.compress(desc_xml))
            supp_plain = _write(d, "supp.xml", supp_xml)
            supp_gz = _write(d, "supp.gz", gzip.compress(supp_xml))
            mesh_plain = rms.load_mesh(desc_plain, supp_plain, WANTED)
            mesh_gz = rms.load_mesh(desc_gz, supp_gz, WANTED)

        self.assertEqual(mesh_plain, mesh_gz)
        self.assertEqual(mesh_plain["desc"]["D014283"],
                          ("Xanthines (fixture)",
                           ["D03.132.436", "D03.633.100.759.758.400"]))
        self.assertEqual(mesh_plain["tree"]["D03.132.436"], "D014283")

    def test_by_unii_is_restricted_to_wanted_uniis(self):
        mesh = _mesh()
        self.assertEqual(mesh["by_unii"]["UNII-CAFF"], ["D002110"])
        # UNII-UNWANTED is a real registry number in the fixture (on C999002)
        # but was never asked for, and must not appear at all.
        self.assertNotIn("UNII-UNWANTED", mesh["by_unii"])

    def test_supplementary_record_kept_only_when_it_carries_a_wanted_unii(self):
        mesh = _mesh()
        self.assertIn("C999001", mesh["supp"])          # UNII-SALT is wanted
        self.assertNotIn("C999002", mesh["supp"])        # UNII-UNWANTED is not

    def test_supplementary_headings_lose_their_leading_star(self):
        mesh = _mesh()
        name, mapped = mesh["supp"]["C999001"]
        self.assertEqual(name, "SaltForm (fixture)")
        self.assertEqual(mapped, ["D014283", "D999026", "D999003"])
        self.assertTrue(all(not m.startswith("*") for m in mapped))


# -------------------------------------------------------------- hierarchy

class ParentsOfTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_a_descriptor_filed_twice_returns_both_parents(self):
        self.assertEqual(set(rms.parents_of(self.mesh, "D014283")),
                          {"D002098", "D011744"})

    def test_never_returns_a_depth_one_branch_root(self):
        # Alkaloids sits at MIN_DEPTH (2); walking up from it lands on "D03",
        # depth 1 - which a real fixture record (Organic Chemicals) occupies,
        # so this is not merely an absent lookup but an active exclusion.
        self.assertIn("D999003", self.mesh["tree"].values())
        self.assertEqual(rms.parents_of(self.mesh, "D002098"), [])

    def test_ignores_tree_numbers_in_a_non_structural_branch(self):
        self.assertEqual(rms.structure_trees(self.mesh, "D600001"), [])
        self.assertEqual(rms.parents_of(self.mesh, "D600001"), [])
        # Caffeine's D27 tree must not contribute a parent or otherwise be
        # seen; only its D03 tree may.
        self.assertEqual(rms.structure_trees(self.mesh, "D002110"),
                          ["D03.132.436.077"])

    def test_a_bare_branch_tree_number_has_no_parent(self):
        # No dot at all: "D01" cannot be walked up from.
        self.assertEqual(rms.parents_of(self.mesh, "D900001"), [])


class OwnClassesTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_a_descriptor_is_classed_by_its_parents(self):
        self.assertEqual(rms.own_classes(self.mesh, "D002110"), ["D014283"])
        self.assertEqual(rms.own_classes(self.mesh, "D700002"), ["D700001"])

    def test_a_supplementary_record_is_classed_by_its_structural_mapped_headings(self):
        # Xanthines is kept; the D26 (pharmaceutical prep) and depth-1 (D03
        # root) mapped headings are both dropped.
        self.assertEqual(rms.own_classes(self.mesh, "C999001"), ["D014283"])

    def test_a_descriptor_with_no_structural_parent_has_no_classes(self):
        self.assertEqual(rms.own_classes(self.mesh, "D900001"), [])


class LabelRowsTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_every_ancestor_is_included_with_its_min_depth_and_joined_parents(self):
        rows = rms.label_rows(self.mesh, ["D014283"])
        by_ui = {r[1]: r for r in rows}

        self.assertEqual(set(by_ui), {"D014283", "D002098", "D011744"})
        self.assertEqual(by_ui["D014283"],
                          (rms.SOURCE, "D014283", 3, "Xanthines (fixture)",
                           "D002098|D011744"))
        self.assertEqual(by_ui["D002098"],
                          (rms.SOURCE, "D002098", 2, "Alkaloids (fixture)", None))
        self.assertEqual(by_ui["D011744"],
                          (rms.SOURCE, "D011744", 5, "Purinones (fixture)", None))


# ------------------------------------------------------------------ resolve

class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_no_inchikey_is_counted_and_skipped(self):
        rows, labels, counts, records = rms.resolve(
            [(1, [("C1", None)]), (2, [("C2", "")])], self.mesh, {})
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_inchikey"], 2)

    def test_inchikey_with_no_unii_is_counted(self):
        rows, labels, counts, records = rms.resolve(
            [(1, [("C1", "KEY_NO_UNII")])], self.mesh, {})
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_unii"], 1)

    def test_unii_in_no_mesh_record_is_counted(self):
        unii_by_key = {"GHOSTKEY": ["UNII-GHOST"]}
        rows, labels, counts, records = rms.resolve(
            [(1, [("C1", "GHOSTKEY")])], self.mesh, unii_by_key)
        self.assertEqual(rows, [])
        self.assertEqual(counts["unii_not_in_mesh"], 1)

    def test_carriers_string_is_exactly_ids_unii_and_mesh_record(self):
        unii_by_key = {"KEYX": ["UNII-CAFF"]}
        rows, labels, counts, records = rms.resolve(
            [(1, [("CHEMBL_CAFF", "KEYX")])], self.mesh, unii_by_key)
        self.assertEqual(rows, [(1, rms.SOURCE, "D014283", "",
                                  "Xanthines (fixture)",
                                  "CHEMBL_CAFF|UNII:UNII-CAFF|MeSH:D002110")])
        self.assertEqual(counts["resolved"], 1)
        self.assertEqual(records[1], "D002110")

    def test_a_form_is_not_tried_when_the_parent_resolves(self):
        unii_by_key = {"PARENT_OK": ["UNII-CAFF"], "FORM_UNUSED": ["UNII-THEO"]}
        rows, labels, counts, records = rms.resolve(
            [(1, [("PARENT_CID", "PARENT_OK"), ("FORM_CID", "FORM_UNUSED")])],
            self.mesh, unii_by_key)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "D014283")            # Caffeine's class
        self.assertIn("MeSH:D002110", rows[0][5])           # Caffeine's own record
        self.assertNotIn("FORM_CID", rows[0][5])
        self.assertNotIn("UNII-THEO", rows[0][5])
        self.assertNotIn("resolved_through_a_form", counts)

    def test_a_form_is_tried_when_the_parent_reaches_nothing(self):
        unii_by_key = {"FORM_OK": ["UNII-THEO"]}          # PARENT_FAIL has no entry
        rows, labels, counts, records = rms.resolve(
            [(1, [("PARENT_CID", "PARENT_FAIL"), ("FORM_CID", "FORM_OK")])],
            self.mesh, unii_by_key)
        self.assertEqual(len(rows), 1)
        self.assertIn("FORM_CID|UNII:UNII-THEO|MeSH:D700001", rows[0][5])
        self.assertNotIn("PARENT_CID", rows[0][5])
        self.assertEqual(counts["resolved_through_a_form"], 1)

    def test_uniis_reaching_two_different_records_are_ambiguous(self):
        unii_by_key = {"AMBKEY": ["UNII-A", "UNII-B"]}
        rows, labels, counts, records = rms.resolve(
            [(1, [("C1", "AMBKEY")])], self.mesh, unii_by_key)
        self.assertEqual(rows, [])
        self.assertEqual(counts["ambiguous_several_records"], 1)
        self.assertNotIn("resolved", counts)
        self.assertNotIn(1, records)

    def test_a_record_with_no_structural_class_is_counted(self):
        unii_by_key = {"NOCLASSKEY": ["UNII-NOCLASS"]}
        rows, labels, counts, records = rms.resolve(
            [(1, [("C1", "NOCLASSKEY")])], self.mesh, unii_by_key)
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_structure_class"], 1)


class ResolveFiledUnderOwnHeadingTest(unittest.TestCase):
    """The bigger, catalogue-shaped scenario: Theobromine is a class directly
    for Pentoxifylline, and TopClass is a class only as an ancestor of
    MidClass2 (LeafMolecule's own, direct class) - two different routes into
    `in_use`, both of which must file the molecule under its own heading.
    LonelyDrug's own record is a class nobody uses, directly or as an
    ancestor, and must not be filed under itself."""

    def setUp(self):
        self.mesh = _mesh()
        self.unii_by_key = {
            "KEY-CAFF": ["UNII-CAFF"],
            "KEY-THEO": ["UNII-THEO"],
            "KEY-PENTOX": ["UNII-PENTOX"],
            "KEY-LEAF": ["UNII-LEAF"],
            "KEY-TOPCLASS": ["UNII-TOPCLASS"],
            "KEY-LONELY": ["UNII-LONELY"],
        }
        self.molecules = [
            (1, [("CHEMBL_CAFF", "KEY-CAFF")]),
            (2, [("CHEMBL_THEO", "KEY-THEO")]),
            (3, [("CHEMBL_PENTOX", "KEY-PENTOX")]),
            (4, [("CHEMBL_LEAF", "KEY-LEAF")]),
            (5, [("CHEMBL_TOPCLASS", "KEY-TOPCLASS")]),
            (6, [("CHEMBL_LONELY", "KEY-LONELY")]),
        ]
        self.rows, self.labels, self.counts, self.records = rms.resolve(
            self.molecules, self.mesh, self.unii_by_key)

    def _classes_of(self, parent):
        return sorted(r[2] for r in self.rows if r[0] == parent)

    def test_theobromine_is_filed_under_its_own_heading_directly(self):
        # Pentoxifylline's own class is Theobromine itself.
        self.assertEqual(self._classes_of(3), ["D700001"])
        self.assertEqual(self._classes_of(2), ["D014283", "D700001"])

    def test_topclass_is_filed_under_its_own_heading_only_as_an_ancestor(self):
        # LeafMolecule's direct class is MidClass2, never TopClass; TopClass
        # only reaches `in_use` through MidClass2's ancestor chain.
        self.assertEqual(self._classes_of(4), ["D760002"])
        self.assertEqual(self._classes_of(5), ["D002098", "D760001"])

    def test_lonelydrug_is_not_filed_under_its_own_heading(self):
        # Nobody's classes or ancestors reach D800001.
        self.assertEqual(self._classes_of(6), ["D014283"])

    def test_caffeine_is_not_filed_under_its_own_heading(self):
        self.assertEqual(self._classes_of(1), ["D014283"])

    def test_filed_under_own_heading_is_counted_exactly_twice(self):
        self.assertEqual(self.counts["filed_under_own_heading"], 2)


# ----------------------------------------------------------------- backfill

def fake_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def add_molecule(conn, chembl_id, inchikey=None):
    parent = next(_molregno)
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, inchikey, in_cohort,"
        " is_seed, route_atc_n, route_indication, admission_reason)"
        " VALUES (?,?,?,0,0,0,0,'seed_only')",
        (parent, chembl_id, inchikey))
    return parent


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()
        self.conn = fake_db()
        self.caffeine = add_molecule(self.conn, "CHEMBL113", inchikey="KEY-CAFF")
        self.no_key = add_molecule(self.conn, "CHEMBL_OTHER", inchikey=None)

        # Pre-existing rows from other writers, in both tables, which must
        # survive a mesh_struct backfill untouched.
        self.conn.execute(
            "INSERT INTO molecule_classes(parent_molregno, source, code, subgroup,"
            " label, carriers) VALUES (?, 'usan', '-ine', '', 'some usan class',"
            " 'CHEMBLX')", (self.caffeine,))
        self.conn.execute(
            "INSERT INTO class_labels(source, code, level, label, parents)"
            " VALUES ('usan', '-ine', NULL, 'some usan class', NULL)")
        self.conn.execute(
            "INSERT INTO molecule_classes(parent_molregno, source, code, subgroup,"
            " label, carriers) VALUES (?, 'mesh_pa', 'D000001', '', 'Some MeSH PA',"
            " 'CID:1')", (self.caffeine,))
        self.conn.execute(
            "INSERT INTO class_labels(source, code, level, label, parents)"
            " VALUES ('mesh_pa', 'D000001', 4, 'Some MeSH PA', NULL)")

    def _molecules_and_unii(self):
        molecules = [(self.caffeine, [("CHEMBL113", "KEY-CAFF")]),
                     (self.no_key, [("CHEMBL_OTHER", None)])]
        unii_by_key = {"KEY-CAFF": ["UNII-CAFF"]}
        return molecules, unii_by_key

    def test_writes_only_mesh_struct_rows_and_leaves_other_sources_alone(self):
        molecules, unii_by_key = self._molecules_and_unii()
        summary = rms.backfill(self.conn, self.mesh, molecules, unii_by_key,
                                {"mesh_desc_sha256": "deadbeef"})

        mesh_rows = self.conn.execute(
            "SELECT parent_molregno, source, code, subgroup, label, carriers"
            " FROM molecule_classes WHERE source = 'mesh_struct'").fetchall()
        self.assertEqual(mesh_rows, [(self.caffeine, "mesh_struct", "D014283", "",
                                       "Xanthines (fixture)",
                                       "CHEMBL113|UNII:UNII-CAFF|MeSH:D002110")])

        mesh_labels = {r[1]: r for r in self.conn.execute(
            "SELECT source, code, level, label, parents FROM class_labels"
            " WHERE source = 'mesh_struct'")}
        self.assertEqual(set(mesh_labels), {"D014283", "D002098", "D011744"})

        usan_rows = self.conn.execute(
            "SELECT parent_molregno, source, code, subgroup, label, carriers"
            " FROM molecule_classes WHERE source = 'usan'").fetchall()
        self.assertEqual(usan_rows, [(self.caffeine, "usan", "-ine", "",
                                       "some usan class", "CHEMBLX")])
        pa_rows = self.conn.execute(
            "SELECT parent_molregno, source, code, subgroup, label, carriers"
            " FROM molecule_classes WHERE source = 'mesh_pa'").fetchall()
        self.assertEqual(pa_rows, [(self.caffeine, "mesh_pa", "D000001", "",
                                     "Some MeSH PA", "CID:1")])
        usan_labels = self.conn.execute(
            "SELECT source, code, level, label, parents FROM class_labels"
            " WHERE source = 'usan'").fetchall()
        self.assertEqual(usan_labels, [("usan", "-ine", None, "some usan class", None)])
        pa_labels = self.conn.execute(
            "SELECT source, code, level, label, parents FROM class_labels"
            " WHERE source = 'mesh_pa'").fetchall()
        self.assertEqual(pa_labels, [("mesh_pa", "D000001", 4, "Some MeSH PA", None)])

        manifest = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'mesh_structure_classes'"
        ).fetchone()[0])
        self.assertEqual(manifest["mesh_desc_sha256"], "deadbeef")
        self.assertEqual(manifest["counts"]["resolved"], 1)
        self.assertEqual(manifest["counts"]["no_inchikey"], 1)
        self.assertEqual(summary["rows_changed"], 1)

    def test_a_second_identical_run_reports_no_rows_changed(self):
        molecules, unii_by_key = self._molecules_and_unii()
        rms.backfill(self.conn, self.mesh, molecules, unii_by_key, {"run": "a"})
        summary = rms.backfill(self.conn, self.mesh, molecules, unii_by_key, {"run": "b"})
        self.assertEqual(summary["rows_changed"], 0)
        manifest = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'mesh_structure_classes'"
        ).fetchone()[0])
        # the manifest still reflects the second run's own inputs, even though
        # no molecule_classes/class_labels row actually changed
        self.assertEqual(manifest["run"], "b")

    def test_writes_the_mesh_structure_classes_manifest_key_only(self):
        molecules, unii_by_key = self._molecules_and_unii()
        rms.backfill(self.conn, self.mesh, molecules, unii_by_key, {})
        keys = {r[0] for r in self.conn.execute("SELECT key FROM build_manifest")}
        self.assertEqual(keys, {"mesh_structure_classes"})


if __name__ == "__main__":
    unittest.main()
