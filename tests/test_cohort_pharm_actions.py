"""Offline tests for scripts/resolve_cohort_pharm_actions.py.

These lock in the parts of the MeSH pharmacological-action backfill that need
no network and no pinned file: parsing a MeSH descriptor file, placing a
molecule on exactly one MeSH record by identifier (FDA UNII, CAS, a stereoisomer
mixture, then Wikidata - invariant 15) with a refusal, never a pick, wherever
more than one record is reached (invariant 6), and that the backfill only ever
touches its own 'mesh_pa' rows of molecule_classes / class_labels
(scripts/cohort/classes.py's SOURCES contract - each writer owns its own
sources).

Every input is a small in-memory fixture: `records` shaped like load_records,
an `Fda` like load_fda, a `mesh` like load_mesh. Wikidata is reached only
through an injected `get`. This test never opens db/cohort1.db; every sqlite
fixture here is an in-memory database built from db/schema_cohort.sql.

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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_pharm_actions as rcpa  # noqa: E402
from cohort import classes as classes_mod  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

_molregno = itertools.count(1)


# ------------------------------------------------------------------- MeSH
#
# A tiny fixture that mirrors the real D27 (pharmacological action) branch
# far enough to exercise depth, a descriptor filed in two places, and the
# D27 boundary itself:
#
#   D002491 Central Nervous System Agents  D27.505.954.427             depth 4 (MIN_DEPTH)
#   D011619 Psychotropic Drugs              D27.505.954.427.700         depth 5
#   D000928 Antidepressive Agents            D27.505.954.427.700.122     depth 6
#   D000929 Antidepressive Agents, Tricyclic  D27.505.954.427.700.122.055 depth 7
#   D999999 Therapeutic Uses                D27.505.954                 depth 3 - generic,
#                                            must never surface as a parent or a label
#   D999001 (fixture) filed twice: once under Antidepressive Agents, once
#           directly under Psychotropic Drugs
#   D500001 (fixture) a chemical in the D03 branch only - never a
#           pharmacological action, and its tree number must be ignored
#
# Concept ids are MeSH concept ids (M0001382-shaped).

_DESCRIPTORS = [
    ("D999999", "Therapeutic Uses", ["D27.505.954"], ["M0999999"]),
    ("D002491", "Central Nervous System Agents", ["D27.505.954.427"], ["M0002491"]),
    ("D011619", "Psychotropic Drugs", ["D27.505.954.427.700"], ["M0011619"]),
    ("D000928", "Antidepressive Agents", ["D27.505.954.427.700.122"], ["M0000928"]),
    ("D000929", "Antidepressive Agents, Tricyclic",
     ["D27.505.954.427.700.122.055"], ["M0000929"]),
    ("D999001", "Serotonin Uptake-Adjacent Agents (fixture)",
     ["D27.505.954.427.700.122.100", "D27.505.954.427.700.099"], ["M0999001"]),
    ("D500001", "Some Chemical (fixture)", ["D03.383.129"], ["M0500001"]),
]


def _mesh_xml_bytes():
    parts = ["<DescriptorRecordSet>"]
    for ui, name, trees, concepts in _DESCRIPTORS:
        tree_xml = "".join(f"<TreeNumber>{t}</TreeNumber>" for t in trees)
        concept_xml = "".join(f"<Concept><ConceptUI>{c}</ConceptUI></Concept>" for c in concepts)
        parts.append(
            "<DescriptorRecord>"
            f"<DescriptorUI>{ui}</DescriptorUI>"
            f"<DescriptorName><String>{name}</String></DescriptorName>"
            f"<TreeNumberList>{tree_xml}</TreeNumberList>"
            f"<ConceptList>{concept_xml}</ConceptList>"
            "</DescriptorRecord>")
    parts.append("</DescriptorRecordSet>")
    return "".join(parts).encode("utf-8")


def _mesh():
    """Parse the fixture through the real load_mesh, so every other test
    exercises the same code path LoadMeshTest checks directly."""
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / "desc-fixture.xml"
        path.write_bytes(_mesh_xml_bytes())
        return rcpa.load_mesh(path)


class LoadMeshTest(unittest.TestCase):
    def test_reads_gzipped_and_plain_fixtures_identically(self):
        xml = _mesh_xml_bytes()
        with tempfile.TemporaryDirectory() as d:
            plain = pathlib.Path(d) / "desc.xml"
            packed = pathlib.Path(d) / "desc.gz"
            plain.write_bytes(xml)
            packed.write_bytes(gzip.compress(xml))
            mesh_plain = rcpa.load_mesh(plain)
            mesh_gz = rcpa.load_mesh(packed)

        self.assertEqual(mesh_plain, mesh_gz)
        # concept -> descriptor
        self.assertEqual(mesh_plain["concept"]["M0000929"], "D000929")
        self.assertEqual(mesh_plain["concept"]["M0002491"], "D002491")
        # descriptor -> (name, tree numbers)
        self.assertEqual(mesh_plain["desc"]["D000929"],
                          ("Antidepressive Agents, Tricyclic",
                           ["D27.505.954.427.700.122.055"]))
        self.assertEqual(mesh_plain["desc"]["D999001"][1],
                          ["D27.505.954.427.700.122.100", "D27.505.954.427.700.099"])
        # tree number -> descriptor
        self.assertEqual(mesh_plain["tree"]["D27.505.954.427.700.122.055"], "D000929")
        self.assertEqual(mesh_plain["tree"]["D27.505.954.427"], "D002491")


class ParentsOfTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_walks_one_level_up_inside_d27(self):
        self.assertEqual(rcpa.parents_of(self.mesh, "D000929"), ["D000928"])
        self.assertEqual(rcpa.parents_of(self.mesh, "D000928"), ["D011619"])
        self.assertEqual(rcpa.parents_of(self.mesh, "D011619"), ["D002491"])

    def test_stops_at_min_depth_and_never_returns_therapeutic_uses(self):
        # D002491 sits at MIN_DEPTH (4); walking up from it lands on the
        # depth-3 "Therapeutic Uses" branch, which must never be returned.
        self.assertEqual(rcpa.parents_of(self.mesh, "D002491"), [])

    def test_a_descriptor_filed_in_two_places_returns_both_parents(self):
        self.assertEqual(set(rcpa.parents_of(self.mesh, "D999001")),
                          {"D000928", "D011619"})

    def test_ignores_non_d27_tree_numbers(self):
        self.assertEqual(rcpa.parents_of(self.mesh, "D500001"), [])


class LabelRowsTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    def test_tricyclic_action_returns_itself_and_every_ancestor_to_min_depth(self):
        rows = rcpa.label_rows(self.mesh, ["D000929"])
        by_ui = {r[1]: r for r in rows}

        self.assertEqual(set(by_ui), {"D000929", "D000928", "D011619", "D002491"})
        self.assertEqual(by_ui["D000929"],
                          ("mesh_pa", "D000929", 7,
                           "Antidepressive Agents, Tricyclic", "D000928"))
        self.assertEqual(by_ui["D000928"],
                          ("mesh_pa", "D000928", 6, "Antidepressive Agents", "D011619"))
        self.assertEqual(by_ui["D011619"],
                          ("mesh_pa", "D011619", 5, "Psychotropic Drugs", "D002491"))
        # top of the hierarchy: no parent at all - not even the depth-3 branch
        self.assertEqual(by_ui["D002491"],
                          ("mesh_pa", "D002491", 4,
                           "Central Nervous System Agents", None))


# ------------------------------------------------------------ record loading

class LoadRecordsTest(unittest.TestCase):
    """load_records() reads both the descriptor and supplemental files into
    one identity index: concept -> record, each record's own actions,
    registry numbers, mapped headings, and the descriptors directly above it
    from the tree numbers of *both* files combined."""

    DESC_XML = """<DescriptorRecordSet>
<DescriptorRecord>
<DescriptorUI>D_A</DescriptorUI>
<DescriptorName><String>A Name</String></DescriptorName>
<TreeNumberList><TreeNumber>T1.100</TreeNumber></TreeNumberList>
<ConceptList>
<Concept><ConceptUI>C_A1</ConceptUI>
<RegistryNumberList><RegistryNumber>12345-67-8</RegistryNumber><RegistryNumber>0</RegistryNumber></RegistryNumberList>
</Concept>
<Concept><ConceptUI>C_A2</ConceptUI></Concept>
</ConceptList>
</DescriptorRecord>
<DescriptorRecord>
<DescriptorUI>D_B</DescriptorUI>
<DescriptorName><String>B Name</String></DescriptorName>
<TreeNumberList><TreeNumber>T1</TreeNumber></TreeNumberList>
<ConceptList><Concept><ConceptUI>C_B1</ConceptUI></Concept></ConceptList>
</DescriptorRecord>
</DescriptorRecordSet>"""

    SUPP_XML = """<SupplementalRecordSet>
<SupplementalRecord>
<SupplementalRecordUI>S_C</SupplementalRecordUI>
<SupplementalRecordName><String>C Name</String></SupplementalRecordName>
<ConceptList>
<Concept><ConceptUI>C_C1</ConceptUI>
<RegistryNumberList><RegistryNumber>999-99-9</RegistryNumber></RegistryNumberList>
</Concept>
</ConceptList>
<PharmacologicalActionList>
<PharmacologicalAction><DescriptorReferredTo><DescriptorUI>D_A</DescriptorUI></DescriptorReferredTo></PharmacologicalAction>
</PharmacologicalActionList>
<HeadingMappedToList>
<HeadingMappedTo><DescriptorReferredTo><DescriptorUI>*D_A</DescriptorUI></DescriptorReferredTo></HeadingMappedTo>
<HeadingMappedTo><DescriptorReferredTo><DescriptorUI>D_B</DescriptorUI></DescriptorReferredTo></HeadingMappedTo>
</HeadingMappedToList>
</SupplementalRecord>
</SupplementalRecordSet>"""

    def _load(self, pack):
        with tempfile.TemporaryDirectory() as d:
            ext = ".gz" if pack else ".xml"
            desc = pathlib.Path(d) / f"desc{ext}"
            supp = pathlib.Path(d) / f"supp{ext}"
            if pack:
                desc.write_bytes(gzip.compress(self.DESC_XML.encode()))
                supp.write_bytes(gzip.compress(self.SUPP_XML.encode()))
            else:
                desc.write_bytes(self.DESC_XML.encode())
                supp.write_bytes(self.SUPP_XML.encode())
            return rcpa.load_records(desc, supp)

    def test_plain_and_gzipped_fixtures_read_identically(self):
        plain = self._load(pack=False)
        gz = self._load(pack=True)
        self.assertEqual(plain, gz)

        self.assertEqual(plain["concept"], {
            "C_A1": "D_A", "C_A2": "D_A", "C_B1": "D_B", "C_C1": "S_C"})
        self.assertEqual(plain["pa"], {"S_C": frozenset({"D_A"})})
        # the "0" registry number is not a real registry number and is
        # dropped, the same rule the real UNII/CAS data needs.
        self.assertEqual(plain["rn"], {"D_A": ["12345-67-8"], "S_C": ["999-99-9"]})
        # the leading "*" HeadingMappedTo marks a preferred mapping in the
        # real MeSH files and carries no meaning here, so it is stripped.
        self.assertEqual(plain["mapped"], {"S_C": ["D_A", "D_B"]})
        # D_A's tree parent (D_B) is resolved from tree numbers across both
        # files; the supplemental record S_C carries no tree number at all
        # and so has no entry here.
        self.assertEqual(plain["parents"], {"D_A": ["D_B"], "D_B": []})
        self.assertNotIn("S_C", plain["parents"])


# ------------------------------------------------------------ fixtures

def _records(concept=None, pa=None, rn=None, mapped=None, parents=None):
    return {"concept": concept or {}, "pa": pa or {}, "rn": rn or {},
            "mapped": mapped or {}, "parents": parents or {}}


def _fda(unii_by_key=None, cas_of=None, mixtures=None):
    return rcpa.Fda(unii_by_key or {}, cas_of or {}, mixtures or {})


# Real InChIKey shape: 14-character skeleton block, '-', 10-character second
# block, '-', one protonation character. SKELETON_A flat has no stereo layer.
FLAT_KEY = "ABCDEFGHIJKLMN-UHFFFAOYSA-N"
STEREO_KEY = "ABCDEFGHIJKLMN-QWERTYUIOP-N"
SKELETON = "ABCDEFGHIJKLMN"


class RecordsByNumberTest(unittest.TestCase):
    def test_inverts_registry_numbers_to_the_records_carrying_them(self):
        records = _records(rn={"R1": ["U1", "56-12-2"], "R2": ["U1"]})
        by_number = rcpa.records_by_number(records)
        self.assertEqual(by_number["U1"], {"R1", "R2"})
        self.assertEqual(by_number["56-12-2"], {"R1"})
        self.assertNotIn("U9", by_number)


# ------------------------------------------------------------------ load_fda

class LoadFdaTest(unittest.TestCase):
    HEADER = "UNII\tPT\tRN\tINCHIKEY\n"

    def _load(self, rows):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "UNII_Records.txt"
            path.write_text(self.HEADER + "".join("\t".join(r) + "\n" for r in rows),
                            encoding="utf-8")
            return rcpa.load_fda(path)

    def test_an_exact_key_maps_to_its_unii_and_a_unii_to_its_cas(self):
        fda = self._load([("UNII1", "drug", "56-12-2", "KEYAAAAAAAAAAA-QWERTYUIOP-N")])
        self.assertEqual(fda.unii_by_key["KEYAAAAAAAAAAA-QWERTYUIOP-N"], {"UNII1"})
        self.assertEqual(fda.cas_of["UNII1"], {"56-12-2"})

    def test_two_uniis_registered_with_one_structure_both_kept(self):
        fda = self._load([("U1", "a", "", "K1AAAAAAAAAAAA-QWERTYUIOP-N"),
                          ("U2", "b", "", "K1AAAAAAAAAAAA-QWERTYUIOP-N")])
        self.assertEqual(fda.unii_by_key["K1AAAAAAAAAAAA-QWERTYUIOP-N"], {"U1", "U2"})

    def test_a_cas_is_recorded_even_for_a_substance_with_no_inchikey(self):
        fda = self._load([("U1", "antibody", "1234-56-7", "")])
        self.assertEqual(fda.cas_of["U1"], {"1234-56-7"})
        self.assertEqual(fda.unii_by_key, {})

    def test_joined_keys_sharing_a_first_block_are_a_mixture_under_that_block(self):
        a = f"{SKELETON}-AAAAAAAAAA-N"
        b = f"{SKELETON}-BBBBBBBBBB-N"
        fda = self._load([("UMIX", "racemate", "", f"{a};{b}")])
        self.assertEqual(fda.mixtures, {SKELETON: {"UMIX"}})
        # the joined field is also kept as the exact key FDA wrote
        self.assertEqual(fda.unii_by_key[f"{a};{b}"], {"UMIX"})

    def test_joined_keys_with_different_first_blocks_are_not_a_mixture(self):
        # A combination product: two different skeletons, not stereoisomers
        # of one, so it must never stand in for either.
        fda = self._load([("UCOMBO", "combo", "",
                           "AAAAAAAAAAAAAA-QWERTYUIOP-N;BBBBBBBBBBBBBB-QWERTYUIOP-N")])
        self.assertEqual(fda.mixtures, {})

    def test_rows_with_no_unii_are_ignored(self):
        fda = self._load([("", "nameless", "9-9-9", "KEYAAAAAAAAAAA-QWERTYUIOP-N")])
        self.assertEqual(fda.unii_by_key, {})
        self.assertEqual(fda.cas_of, {})
        self.assertEqual(fda.mixtures, {})


# --------------------------------------------------------------------- place

class PlaceTest(unittest.TestCase):
    """place(keys, chembl_id, by_number, fda, wikidata, known) -> (record,
    step, carriers). Each fallback is tried only where the one before placed
    nothing, and more than one record is a refusal."""

    KNOWN = {"R1", "R2", "R3"}

    def _place(self, keys, rn=None, fda=None, wikidata=(), known=None):
        by_number = rcpa.records_by_number(_records(rn=rn))
        return rcpa.place(keys, "CHEMBL1", by_number, fda or _fda(), list(wikidata),
                          self.KNOWN if known is None else known)

    # -- UNII

    def test_a_unii_reaching_one_record_places_it_with_the_unii_step(self):
        rec, step, carriers = self._place(
            ["K1"], rn={"R1": ["U1"]}, fda=_fda(unii_by_key={"K1": {"U1"}}))
        self.assertEqual((rec, step), ("R1", "unii"))
        self.assertTrue(carriers.endswith("MeSH:R1"))
        self.assertIn("UNII:U1", carriers)

    def test_the_parent_key_alone_settles_it_a_forms_unii_is_not_consulted(self):
        fda = _fda(unii_by_key={"PARENT": {"U1"}, "FORM": {"U2"}})
        rec, step, _ = self._place(["PARENT", "FORM"],
                                   rn={"R1": ["U1"], "R2": ["U2"]}, fda=fda)
        self.assertEqual((rec, step), ("R1", "unii"))

    def test_a_forms_key_is_used_when_the_parents_reaches_nothing(self):
        fda = _fda(unii_by_key={"PARENT": {"U0"}, "FORM": {"U2"}})
        rec, step, carriers = self._place(["PARENT", "FORM"],
                                          rn={"R2": ["U2"]}, fda=fda)
        self.assertEqual((rec, step), ("R2", "unii"))
        self.assertIn("UNII:U2", carriers)

    def test_two_records_reached_is_a_refusal_never_a_pick(self):
        fda = _fda(unii_by_key={"K1": {"U1", "U2"}})
        rec, step, carriers = self._place(["K1"], rn={"R1": ["U1"], "R2": ["U2"]}, fda=fda)
        self.assertIsNone(rec)
        self.assertEqual(step, "several_records")
        self.assertEqual(carriers, "")

    def test_no_record_reached_and_nothing_else_is_no_record(self):
        rec, step, _ = self._place(["K1"], fda=_fda(unii_by_key={"K1": {"U1"}}))
        self.assertEqual((rec, step), (None, "no_record"))

    # -- CAS

    def test_cas_places_when_the_uniis_reach_no_record(self):
        # GABA: the MeSH record carries the CAS number, not the UNII.
        fda = _fda(unii_by_key={"K1": {"U1"}}, cas_of={"U1": {"56-12-2"}})
        rec, step, carriers = self._place(["K1"], rn={"R1": ["56-12-2"]}, fda=fda)
        self.assertEqual((rec, step), ("R1", "cas"))
        self.assertIn("UNII:U1|CAS:56-12-2", carriers)
        self.assertTrue(carriers.endswith("MeSH:R1"))

    def test_cas_is_not_tried_when_the_unii_reached_a_record(self):
        # Eplerenone/lacosamide: the UNII places R1, and a second record R2
        # also carries a CAS of that UNII. Using the CAS beside the UNII
        # would refuse a molecule the UNII had settled.
        fda = _fda(unii_by_key={"K1": {"U1"}}, cas_of={"U1": {"111-11-1"}})
        rec, step, _ = self._place(["K1"],
                                   rn={"R1": ["U1"], "R2": ["111-11-1"]}, fda=fda)
        self.assertEqual((rec, step), ("R1", "unii"))

    def test_a_cas_reaching_two_records_is_refused(self):
        fda = _fda(unii_by_key={"K1": {"U1"}}, cas_of={"U1": {"111-11-1"}})
        rec, step, _ = self._place(["K1"],
                                   rn={"R1": ["111-11-1"], "R2": ["111-11-1"]}, fda=fda)
        self.assertEqual((rec, step), (None, "several_records"))

    # -- stereoisomer mixture

    def test_a_flat_key_with_no_exact_match_is_placed_through_a_mixture(self):
        # Methylphenidate: ChEMBL draws it flat, FDA registers the racemate.
        fda = _fda(mixtures={SKELETON: {"UMIX"}})
        rec, step, carriers = self._place([FLAT_KEY], rn={"R1": ["UMIX"]}, fda=fda)
        self.assertEqual((rec, step), ("R1", "stereo_mixture"))
        self.assertIn("UNII:UMIX", carriers)

    def test_a_key_with_stereo_never_uses_the_mixture_step(self):
        # Esmethadone must not land on methadone's record just because the
        # skeletons match.
        fda = _fda(mixtures={SKELETON: {"UMIX"}})
        rec, step, _ = self._place([STEREO_KEY], rn={"R1": ["UMIX"]}, fda=fda)
        self.assertEqual((rec, step), (None, "no_record"))

    def test_an_exact_match_beats_the_mixture_for_a_flat_key(self):
        fda = _fda(unii_by_key={FLAT_KEY: {"U1"}}, mixtures={SKELETON: {"UMIX"}})
        rec, step, _ = self._place([FLAT_KEY], rn={"R1": ["U1"], "R2": ["UMIX"]}, fda=fda)
        self.assertEqual((rec, step), ("R1", "unii"))

    def test_a_mixture_reaching_two_records_is_refused(self):
        fda = _fda(mixtures={SKELETON: {"UMIX1", "UMIX2"}})
        rec, step, _ = self._place([FLAT_KEY],
                                   rn={"R1": ["UMIX1"], "R2": ["UMIX2"]}, fda=fda)
        self.assertEqual((rec, step), (None, "several_records"))

    # -- Wikidata

    def test_wikidata_places_when_the_fda_steps_place_nothing(self):
        rec, step, carriers = self._place(["K1"], wikidata=[["Q42", "R3"]])
        self.assertEqual((rec, step), ("R3", "wikidata"))
        self.assertIn("Wikidata:Q42", carriers)
        self.assertTrue(carriers.endswith("MeSH:R3"))

    def test_an_fda_placement_wins_over_a_different_wikidata_record(self):
        # armodafinil within Modafinil: where both name a record, FDA's stands.
        fda = _fda(unii_by_key={"K1": {"U1"}})
        rec, step, carriers = self._place(["K1"], rn={"R1": ["U1"]}, fda=fda,
                                          wikidata=[["Q42", "R3"]])
        self.assertEqual((rec, step), ("R1", "unii"))
        self.assertNotIn("Wikidata", carriers)

    def test_wikidata_naming_two_mesh_ids_is_refused(self):
        rec, step, _ = self._place([], wikidata=[["Q1", "R1"], ["Q2", "R2"]])
        self.assertEqual((rec, step), (None, "wikidata_several_records"))

    def test_two_items_naming_the_same_mesh_id_place_with_both_carried(self):
        rec, step, carriers = self._place([], wikidata=[["Q2", "R1"], ["Q1", "R1"]])
        self.assertEqual((rec, step), ("R1", "wikidata"))
        self.assertEqual(carriers, "Wikidata:Q1|Wikidata:Q2|MeSH:R1")

    def test_a_wikidata_mesh_id_unknown_to_the_pinned_files_is_ignored(self):
        rec, step, _ = self._place(["K1"], wikidata=[["Q42", "D_NOT_THIS_YEAR"]])
        self.assertEqual((rec, step), (None, "no_record"))

    def test_wikidata_item_without_a_mesh_id_places_nothing(self):
        rec, step, _ = self._place(["K1"], wikidata=[["Q42", None]])
        self.assertEqual((rec, step), (None, "no_record"))

    def test_fda_reaching_two_records_and_no_usable_wikidata_is_several_records(self):
        fda = _fda(unii_by_key={"K1": {"U1", "U2"}})
        rec, step, _ = self._place(["K1"], rn={"R1": ["U1"], "R2": ["U2"]}, fda=fda,
                                   wikidata=[["Q42", "D_NOT_THIS_YEAR"]])
        self.assertEqual((rec, step), (None, "several_records"))

    def test_wikidata_can_settle_what_fda_left_ambiguous(self):
        fda = _fda(unii_by_key={"K1": {"U1", "U2"}})
        rec, step, _ = self._place(["K1"], rn={"R1": ["U1"], "R2": ["U2"]}, fda=fda,
                                   wikidata=[["Q42", "R3"]])
        self.assertEqual((rec, step), ("R3", "wikidata"))

    def test_no_keys_and_no_wikidata_item_is_named_as_such(self):
        rec, step, carriers = self._place([])
        self.assertEqual((rec, step, carriers), (None, "no_inchikey_no_wikidata_item", ""))


# ------------------------------------------------------------------- resolve

class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()
        self.fda = _fda(unii_by_key={"K1": {"U1"}, "K2": {"U2"}, "K3": {"U3"}})
        self.records = _records(
            concept={"M_R1": "R1"},
            pa={"R1": frozenset({"D000929", "D000928"})},
            rn={"R1": ["U1"], "R2": ["U2"], "R3": ["U3"]})

    def _resolve(self, molecules, records=None, wikidata=None):
        return rcpa.resolve(molecules, self.mesh, records or self.records,
                            self.fda, wikidata or {})

    def test_rows_carry_the_records_own_actions_and_the_carriers(self):
        rows, labels, counts = self._resolve([(1, "CHEMBL1", ["K1"])])
        self.assertEqual(rows, [
            (1, "mesh_pa", "D000928", "", "Antidepressive Agents", "UNII:U1|MeSH:R1"),
            (1, "mesh_pa", "D000929", "", "Antidepressive Agents, Tricyclic",
             "UNII:U1|MeSH:R1"),
        ])
        self.assertEqual(counts["resolved"], 1)
        self.assertEqual(counts["resolved_by_unii"], 1)

    def test_labels_include_the_actions_and_their_d27_parents(self):
        _, labels, _ = self._resolve([(1, "CHEMBL1", ["K1"])])
        self.assertEqual({l[1] for l in labels},
                         {"D000929", "D000928", "D011619", "D002491"})

    def test_a_record_with_no_actions_is_counted_and_writes_nothing(self):
        rows, labels, counts = self._resolve([(1, "CHEMBL2", ["K2"])])
        self.assertEqual((rows, labels), ([], []))
        self.assertEqual(counts["record_lists_no_action"], 1)
        self.assertNotIn("resolved", counts)

    def test_an_action_absent_from_the_mesh_year_is_dropped_and_counted(self):
        records = _records(pa={"R1": frozenset({"D000929", "D_GONE"})},
                           rn={"R1": ["U1"]})
        rows, _, counts = self._resolve([(1, "CHEMBL1", ["K1"])], records=records)
        self.assertEqual([r[2] for r in rows], ["D000929"])
        self.assertEqual(counts["action_not_in_mesh_year"], 1)
        self.assertEqual(counts["resolved"], 1)

    def test_a_record_whose_every_action_is_absent_counts_as_no_action(self):
        records = _records(pa={"R1": frozenset({"D_GONE"})}, rn={"R1": ["U1"]})
        rows, _, counts = self._resolve([(1, "CHEMBL1", ["K1"])], records=records)
        self.assertEqual(rows, [])
        self.assertEqual(counts["action_not_in_mesh_year"], 1)
        self.assertEqual(counts["record_lists_no_action"], 1)

    def test_a_refused_placement_is_counted_by_its_step_and_writes_nothing(self):
        rows, _, counts = self._resolve([(1, "CHEMBL9", ["NOSUCHKEY"]), (2, "CHEMBL8", [])])
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_record"], 1)
        self.assertEqual(counts["no_inchikey_no_wikidata_item"], 1)

    def test_a_wikidata_placement_is_counted_under_its_own_step(self):
        # R1 is also a concept's descriptor, so it is known to the files.
        rows, _, counts = self._resolve(
            [(1, "CHEMBL5", [])], wikidata={"CHEMBL5": [["Q7", "R1"]]})
        self.assertEqual(counts["resolved_by_wikidata"], 1)
        self.assertEqual({r[5] for r in rows}, {"Wikidata:Q7|MeSH:R1"})

    def test_rows_are_sorted(self):
        rows, _, _ = self._resolve([(2, "CHEMBL1", ["K1"]), (1, "CHEMBL1", ["K1"])])
        self.assertEqual(rows, sorted(rows))


# ------------------------------------------------------------ fetch_wikidata

def _binding(chembl, item, mesh=None):
    b = {"chembl": {"value": chembl},
         "item": {"value": f"http://www.wikidata.org/entity/{item}"}}
    if mesh:
        b["mesh"] = {"value": mesh}
    return b


class FetchWikidataTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cache = pathlib.Path(self._tmp.name) / "sub" / "mesh_by_chembl.json"
        self.calls = []

    def _get(self, bindings):
        def get(query):
            self.calls.append(query)
            return {"results": {"bindings": bindings}}
        return get

    def test_parses_bindings_records_empty_for_an_unknown_id_and_writes_the_cache(self):
        get = self._get([_binding("CHEMBL1", "Q1", "D000001"),
                         _binding("CHEMBL1", "Q2"),
                         _binding("CHEMBL1", "Q1", "D000001")])  # duplicate row
        out = rcpa.fetch_wikidata(["CHEMBL1", "CHEMBL2"], cache_path=self.cache, get=get)
        self.assertEqual(out, {"CHEMBL1": [["Q1", "D000001"], ["Q2", None]],
                               "CHEMBL2": []})
        self.assertEqual(len(self.calls), 1)
        self.assertIn("CHEMBL1", self.calls[0])
        self.assertEqual(json.loads(self.cache.read_text()), out)

    def test_a_second_call_with_everything_cached_does_not_ask(self):
        get = self._get([_binding("CHEMBL1", "Q1", "D000001")])
        rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache, get=get)
        again = rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache, get=get)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(again, {"CHEMBL1": [["Q1", "D000001"]]})

    def test_only_ids_missing_from_the_cache_are_asked_about(self):
        rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache,
                            get=self._get([_binding("CHEMBL1", "Q1")]))
        self.calls.clear()
        out = rcpa.fetch_wikidata(["CHEMBL1", "CHEMBL3"], cache_path=self.cache,
                                  get=self._get([_binding("CHEMBL3", "Q3", "D000003")]))
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn("CHEMBL1", self.calls[0])
        self.assertEqual(out["CHEMBL3"], [["Q3", "D000003"]])
        self.assertEqual(out["CHEMBL1"], [["Q1", None]])

    def test_refresh_asks_again_despite_the_cache(self):
        get = self._get([_binding("CHEMBL1", "Q1", "D000001")])
        rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache, get=get)
        rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache, get=get, refresh=True)
        self.assertEqual(len(self.calls), 2)

    def test_a_failed_request_raises_rather_than_reading_as_no_item(self):
        def get(query):
            raise RuntimeError("wikidata down")
        with self.assertRaises(RuntimeError):
            rcpa.fetch_wikidata(["CHEMBL1"], cache_path=self.cache, get=get)
        self.assertFalse(self.cache.exists())


# ------------------------------------------------------------- molecule_keys

class MoleculeKeysTest(unittest.TestCase):
    def test_parent_key_first_then_forms_deduplicated_skipping_missing(self):
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL_P", inchikey="PKEY")
        bare = add_molecule(conn, "CHEMBL_Q", inchikey=None)
        # parent's own form row, two salts (one sharing the parent's key, one
        # with no structure in ChEMBL), and a bare molecule with a single form
        conn.executemany(
            "INSERT INTO molecule_forms(parent_molregno, molregno, is_parent)"
            " VALUES (?, ?, ?)",
            [(parent, 100, 1), (parent, 101, 0), (parent, 102, 0), (parent, 103, 0),
             (bare, 200, 1)])

        chembl = sqlite3.connect(":memory:")
        chembl.execute("CREATE TABLE compound_structures"
                       " (molregno INTEGER, standard_inchi_key TEXT)")
        chembl.executemany("INSERT INTO compound_structures VALUES (?, ?)", [
            (100, "PKEY"), (101, "SALTKEY"), (102, "PKEY"), (103, None)])
        # molregno 200 has no structure row at all

        out = {cid: (p, keys) for p, cid, keys in rcpa.molecule_keys(conn, chembl)}
        self.assertEqual(out["CHEMBL_P"], (parent, ["PKEY", "SALTKEY"]))
        self.assertEqual(out["CHEMBL_Q"], (bare, []))


# --------------------------------------------------------------- backfill
#
# class_labels shipped without its `parents` column at first (it was added
# for this backfill - see cohort/classes.py's ensure_tables), so the fixture
# here builds that older shape by hand, the same way
# tests/test_cohort_trials.py cuts a table's CREATE statement out of the
# real schema and swaps in an older shape to test the migration path.

OLD_CLASS_LABELS_SQL = """
CREATE TABLE IF NOT EXISTS class_labels (
    source  TEXT NOT NULL,
    code    TEXT NOT NULL,
    level   INTEGER,
    label   TEXT,
    PRIMARY KEY (source, code)
);
"""


def _cut_table_block(schema, table_name):
    """(before, after): schema text with the named CREATE TABLE statement
    sliced out."""
    lines = schema.splitlines()
    start = next(i for i, l in enumerate(lines)
                 if f"CREATE TABLE IF NOT EXISTS {table_name} " in l)
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == ");")
    return "\n".join(lines[:start]), "\n".join(lines[end + 1:])


def fake_db():
    """An in-memory cohort database with class_labels in its pre-`parents`
    shape - the shape ensure_tables() has to migrate away from - and every
    other table (including molecule_classes) as the real schema has it."""
    before, after = _cut_table_block(SCHEMA, "class_labels")
    conn = sqlite3.connect(":memory:")
    conn.executescript(before + "\n" + OLD_CLASS_LABELS_SQL + "\n" + after)
    conn.execute("PRAGMA foreign_keys = OFF")
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
        self.tricyclic = add_molecule(self.conn, "CHEMBL1", inchikey="KEY1")
        self.no_key = add_molecule(self.conn, "CHEMBL2", inchikey=None)
        self.molecules = [(self.tricyclic, "CHEMBL1", ["KEY1"]),
                          (self.no_key, "CHEMBL2", [])]
        self.records = _records(pa={"R1": frozenset({"D000929"})}, rn={"R1": ["U1"]})
        self.fda = _fda(unii_by_key={"KEY1": {"U1"}})

        # A pre-existing usan row, in class_labels' older (pre-`parents`)
        # shape - written by a different backfill before this one ever ran,
        # and which must survive untouched.
        self.conn.execute(
            "INSERT INTO molecule_classes(parent_molregno, source, code,"
            " subgroup, label, carriers) VALUES (?, 'usan', '-pramine', '',"
            " 'antidepressants (imipramine type)', 'CHEMBL1')", (self.tricyclic,))
        self.conn.execute(
            "INSERT INTO class_labels(source, code, level, label)"
            " VALUES ('usan', '-pramine', NULL, 'antidepressants (imipramine type)')")

    def _backfill(self, extra=None):
        return rcpa.backfill(self.conn, self.molecules, self.mesh, self.records,
                             self.fda, {}, extra)

    def test_adds_parents_column_writes_mesh_pa_rows_and_leaves_usan_alone(self):
        summary = self._backfill({"mesh_sha256": "deadbeef" * 8})

        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(class_labels)")}
        self.assertIn("parents", cols)

        usan_classes = self.conn.execute(
            "SELECT parent_molregno, source, code, subgroup, label, carriers"
            " FROM molecule_classes WHERE source = 'usan'").fetchall()
        self.assertEqual(usan_classes, [(self.tricyclic, "usan", "-pramine", "",
                                          "antidepressants (imipramine type)", "CHEMBL1")])
        usan_labels = self.conn.execute(
            "SELECT source, code, level, label, parents FROM class_labels"
            " WHERE source = 'usan'").fetchall()
        self.assertEqual(usan_labels, [("usan", "-pramine", None,
                                         "antidepressants (imipramine type)", None)])

        mesh_rows = self.conn.execute(
            "SELECT parent_molregno, source, code, subgroup, label, carriers"
            " FROM molecule_classes WHERE source = 'mesh_pa'").fetchall()
        self.assertEqual(mesh_rows, [(self.tricyclic, "mesh_pa", "D000929", "",
                                       "Antidepressive Agents, Tricyclic",
                                       "UNII:U1|MeSH:R1")])

        mesh_labels = {r[1]: r for r in self.conn.execute(
            "SELECT source, code, level, label, parents FROM class_labels"
            " WHERE source = 'mesh_pa'")}
        self.assertEqual(set(mesh_labels), {"D000929", "D000928", "D011619", "D002491"})
        self.assertEqual(mesh_labels["D000929"][4], "D000928")
        self.assertIsNone(mesh_labels["D002491"][4])

        manifest = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'mesh_pharm_actions'"
        ).fetchone()[0])
        self.assertEqual(manifest["mesh_sha256"], "deadbeef" * 8)
        self.assertEqual(manifest["counts"]["resolved"], 1)
        self.assertEqual(manifest["counts"]["no_inchikey_no_wikidata_item"], 1)
        self.assertEqual(summary["rows_changed"], 1)
        self.assertEqual(summary["molecules"], 2)
        self.assertEqual(summary["rows"], 1)

    def test_a_second_identical_run_reports_no_rows_changed(self):
        self._backfill({"mesh_sha256": "sha-a"})
        summary = self._backfill({"mesh_sha256": "sha-b"})
        self.assertEqual(summary["rows_changed"], 0)
        manifest = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'mesh_pharm_actions'"
        ).fetchone()[0])
        # the manifest itself still reflects the second run's own sha, even
        # though no molecule_classes/class_labels row actually changed
        self.assertEqual(manifest["mesh_sha256"], "sha-b")

    def test_a_later_atc_usan_write_does_not_touch_mesh_pa_rows(self):
        self._backfill()
        before = set(self.conn.execute(
            "SELECT * FROM molecule_classes WHERE source = 'mesh_pa'"))
        before_labels = set(self.conn.execute(
            "SELECT * FROM class_labels WHERE source = 'mesh_pa'"))

        classes_mod.write(self.conn, [], [], sources=("atc", "usan"))

        after = set(self.conn.execute(
            "SELECT * FROM molecule_classes WHERE source = 'mesh_pa'"))
        after_labels = set(self.conn.execute(
            "SELECT * FROM class_labels WHERE source = 'mesh_pa'"))
        self.assertEqual(before, after)
        self.assertEqual(before_labels, after_labels)
        # and the usan row IS gone - confirming the mesh_pa rows above
        # survived because write() only touches its own sources, not
        # because this call deleted nothing at all.
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM molecule_classes WHERE source = 'usan'"
        ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
