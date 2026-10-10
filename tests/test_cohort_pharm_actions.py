"""Offline tests for scripts/resolve_cohort_pharm_actions.py.

These lock in the parts of the MeSH pharmacological-action backfill that need
no network: parsing a MeSH descriptor file (invariant 15's identifier chain
from a PubChem concept id to a MeSH descriptor and its ancestors), the
ambiguity rule that drops a molecule rather than guessing between two
PubChem compounds that disagree (invariant 6), and that the backfill only
ever touches its own 'mesh_pa' rows of molecule_classes / class_labels
(scripts/cohort/classes.py's SOURCES contract - each writer owns its own
sources).

No network access: `_cached_get` - the one seam that ever calls
`requests.get` - is stubbed out in every test that reaches it, the same way
tests/test_cohort_trials.py stubs `_ctgov_get`. This test never opens
db/cohort1.db; every sqlite fixture here is an in-memory database built from
db/schema_cohort.sql.

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
from unittest import mock

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
# Concept ids are the MeSH concept ids fetch_actions would read off a
# PubChem PUG-View reference (M0001382-shaped).

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


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.mesh = _mesh()

    @staticmethod
    def _fetchers(cids_by_key=None, actions_by_cid=None):
        cids_by_key = cids_by_key or {}
        actions_by_cid = actions_by_cid or {}
        return ((lambda key: cids_by_key.get(key, [])),
                (lambda cid: actions_by_cid.get(cid, [])))

    def test_one_compound_with_actions_resolves(self):
        cids_for, actions_for = self._fetchers(
            {"KEY1": [111]},
            {111: [("M0000929", "Antidepressive Agents, Tricyclic")]})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [(1, "mesh_pa", "D000929", "",
                                  "Antidepressive Agents, Tricyclic", "CID:111")])
        self.assertEqual(counts["resolved"], 1)
        self.assertNotIn("resolved_over_several_compounds", counts)

    def test_no_inchikey_is_counted_and_skipped(self):
        cids_for, actions_for = self._fetchers()
        rows, labels, counts, _ = rcpa.resolve(
            [(1, None), (2, "")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_inchikey"], 2)

    def test_no_pubchem_compound_is_counted(self):
        cids_for, actions_for = self._fetchers({"KEY1": []})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_pubchem_compound"], 1)

    def test_compound_with_no_actions_is_counted(self):
        cids_for, actions_for = self._fetchers({"KEY1": [111]}, {111: []})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [])
        self.assertEqual(counts["no_actions"], 1)

    def test_two_compounds_agreeing_are_resolved_with_both_carriers(self):
        acts = [("M0000929", "Antidepressive Agents, Tricyclic")]
        cids_for, actions_for = self._fetchers(
            {"KEY1": [222, 111]}, {111: acts, 222: acts})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [(1, "mesh_pa", "D000929", "",
                                  "Antidepressive Agents, Tricyclic", "CID:111|CID:222")])
        self.assertEqual(counts["resolved"], 1)
        self.assertEqual(counts["resolved_over_several_compounds"], 1)

    def test_two_compounds_disagreeing_are_dropped_as_ambiguous(self):
        cids_for, actions_for = self._fetchers(
            {"KEY1": [111, 222]},
            {111: [("M0000929", "Antidepressive Agents, Tricyclic")],
             222: [("M0000928", "Antidepressive Agents")]})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [])
        self.assertEqual(counts["ambiguous_compounds_disagree"], 1)
        self.assertNotIn("resolved", counts)

    def test_resolved_from_the_one_compound_that_lists_an_action(self):
        cids_for, actions_for = self._fetchers(
            {"KEY1": [111, 222]},
            {111: [], 222: [("M0000929", "Antidepressive Agents, Tricyclic")]})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        # only the compound that actually lists an action carries the row -
        # the silent one is not counted as a carrier.
        self.assertEqual(rows, [(1, "mesh_pa", "D000929", "",
                                  "Antidepressive Agents, Tricyclic", "CID:222")])
        self.assertEqual(counts["resolved"], 1)
        # The molecule matched two compounds but only one listed anything, so
        # that is one source rather than an agreement between two.
        self.assertNotIn("resolved_over_several_compounds", counts)

    def test_concept_not_in_mesh_year_is_counted_and_dropped(self):
        cids_for, actions_for = self._fetchers(
            {"KEY1": [111]}, {111: [("M9999999", "Not In This MeSH Year")]})
        rows, labels, counts, _ = rcpa.resolve([(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [])
        self.assertEqual(counts["concept_not_in_mesh_year"], 1)


class FetchActionsTest(unittest.TestCase):
    def test_parses_mesh_references_ignores_other_sources_and_dedupes(self):
        body = json.dumps({"Record": {
            "RecordType": "CID", "RecordNumber": 5311454,
            "Reference": [
                {"ReferenceNumber": 1, "SourceName": "Medical Subject Headings (MeSH)",
                 "SourceID": "M0001382", "Name": "Anticonvulsants"},
                # a duplicate of the reference above - must not be repeated
                {"ReferenceNumber": 2, "SourceName": "Medical Subject Headings (MeSH)",
                 "SourceID": "M0001382", "Name": "Anticonvulsants"},
                # a different source entirely - must be ignored
                {"ReferenceNumber": 3, "SourceName": "ChemIDplus",
                 "SourceID": "XYZ", "Name": "Something else"},
                {"ReferenceNumber": 4, "SourceName": "Medical Subject Headings (MeSH)",
                 "SourceID": "M0002210", "Name": "Central Nervous System Depressants"},
            ],
        }})
        with mock.patch.object(rcpa, "_cached_get",
                                lambda url, key, refresh=False: (200, body)):
            actions = rcpa.fetch_actions(5311454)
        self.assertEqual(actions, [
            ("M0001382", "Anticonvulsants"),
            ("M0002210", "Central Nervous System Depressants"),
        ])

    def test_404_is_no_actions(self):
        with mock.patch.object(rcpa, "_cached_get",
                                lambda url, key, refresh=False: (404, "")):
            self.assertEqual(rcpa.fetch_actions(1), [])


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

    @staticmethod
    def _fetchers():
        cids = {"KEY1": [111]}
        actions = {111: [("M0000929", "Antidepressive Agents, Tricyclic")]}
        return (lambda key: cids.get(key, [])), (lambda cid: actions.get(cid, []))

    def test_adds_parents_column_writes_mesh_pa_rows_and_leaves_usan_alone(self):
        cids_for, actions_for = self._fetchers()
        summary = rcpa.backfill(self.conn, self.mesh, "deadbeef" * 8, cids_for, actions_for)

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
                                       "Antidepressive Agents, Tricyclic", "CID:111")])

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
        self.assertEqual(manifest["counts"]["no_inchikey"], 1)
        self.assertEqual(summary["rows_changed"], 1)

    def test_a_second_identical_run_reports_no_rows_changed(self):
        cids_for, actions_for = self._fetchers()
        rcpa.backfill(self.conn, self.mesh, "sha-a", cids_for, actions_for)
        summary = rcpa.backfill(self.conn, self.mesh, "sha-b", cids_for, actions_for)
        self.assertEqual(summary["rows_changed"], 0)
        manifest = json.loads(self.conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'mesh_pharm_actions'"
        ).fetchone()[0])
        # the manifest itself still reflects the second run's own sha, even
        # though no molecule_classes/class_labels row actually changed
        self.assertEqual(manifest["mesh_sha256"], "sha-b")

    def test_a_later_atc_usan_write_does_not_touch_mesh_pa_rows(self):
        cids_for, actions_for = self._fetchers()
        rcpa.backfill(self.conn, self.mesh, "sha-a", cids_for, actions_for)
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


# -------------------------------------------------------- record identity
#
# PubChem links a compound to MeSH records by name, and a brand name or code
# that means two things joins both - the module docstring's own examples:
# DMSO reaching fluocinonide's actions through the brand "Topsym", tafamidis
# through "FX006" (a triamcinolone product), and LY-411575's chemical name
# mapping to two unrelated MeSH headings that are parts of it rather than an
# identity. Judge sets a record aside only on POSITIVE evidence that it is a
# different substance (invariant 6): a record nothing can compare is kept.

def _identity(blocks=(), uniis=(), own=None):
    return rcpa.Identity(frozenset(blocks), frozenset(uniis), own)


def _records(concept=None, pa=None, rn=None, mapped=None, parents=None):
    return {"concept": concept or {}, "pa": pa or {}, "rn": rn or {},
            "mapped": mapped or {}, "parents": parents or {}}


class JudgeIdentityOfTest(unittest.TestCase):
    """identity_of(record, ident): same | different | unknown, read from a
    record's own UNIIs alone."""

    def test_a_keyed_unii_naming_a_different_chembl_parent_is_different(self):
        # DMSO linked to fluocinonide's "Topsym" record: the record's UNII
        # has a structure, and ChEMBL knows that exact structure filed under
        # a different parent than DMSO.
        records = _records(rn={"TOPSYM": ["UNII_FLUO"]})
        unii_key = {"UNII_FLUO": "FLUOCINONIDE_KEY"}
        blocks_by_key = {"FLUOCINONIDE_KEY": frozenset({"FLUOBLOCK"})}
        judge = rcpa.Judge(records, unii_key,
                            lambda k: blocks_by_key.get(k, frozenset()))
        ident = _identity(blocks={"DMSOBLOCK"})
        self.assertEqual(judge.identity_of("TOPSYM", ident), "different")

    def test_a_differing_key_whose_parent_blocks_contain_the_molecule_is_same(self):
        # dexketoprofen trometamol: the salt's own InChIKey block differs
        # from dexketoprofen's, but ChEMBL files that exact salt structure
        # under dexketoprofen's own parent/active-moiety block.
        records = _records(rn={"TROMETAMOL_SALT": ["UNII_SALT"]})
        unii_key = {"UNII_SALT": "SALT_KEY"}
        blocks_by_key = {"SALT_KEY": frozenset({"DEXKETOBLOCK"})}
        judge = rcpa.Judge(records, unii_key,
                            lambda k: blocks_by_key.get(k, frozenset()))
        ident = _identity(blocks={"DEXKETOBLOCK"})
        self.assertEqual(judge.identity_of("TROMETAMOL_SALT", ident), "same")

    def test_a_unii_already_on_the_identity_is_same_regardless_of_structure(self):
        records = _records(rn={"SOME_RECORD": ["UNII_SELF"]})
        unii_key = {"UNII_SELF": ""}  # FDA gives it no structure either
        judge = rcpa.Judge(records, unii_key, lambda k: frozenset())
        ident = _identity(uniis={"UNII_SELF"})
        self.assertEqual(judge.identity_of("SOME_RECORD", ident), "same")

    def test_a_no_structure_unii_is_unknown_even_beside_a_differing_one(self):
        # nabiximols / norgestimate / "Glucose": one keyed UNII with a real,
        # differing structure, and one FDA gives no structure at all (a
        # mixture or unspecified form). The no-structure UNII alone is
        # enough to keep the record uncomparable, whatever the other says.
        records = _records(rn={"REC": ["UNII_DIFF", "UNII_NOSTRUCT"]})
        unii_key = {"UNII_DIFF": "OTHER_KEY", "UNII_NOSTRUCT": ""}
        blocks_by_key = {"OTHER_KEY": frozenset({"OTHERBLOCK"})}
        judge = rcpa.Judge(records, unii_key,
                            lambda k: blocks_by_key.get(k, frozenset()))
        ident = _identity(blocks={"MYBLOCK"})
        self.assertEqual(judge.identity_of("REC", ident), "unknown")

    def test_a_keyed_unii_chembl_does_not_hold_is_unknown_not_different(self):
        # hydroxypropyl-beta-cyclodextrin polymer: FDA gives it a structure,
        # but ChEMBL holds nothing under that InChIKey at all - a record
        # nothing can compare is kept rather than guessed at.
        records = _records(rn={"CYCLO": ["UNII_CYCLO"]})
        unii_key = {"UNII_CYCLO": "CYCLO_KEY"}
        judge = rcpa.Judge(records, unii_key, lambda k: frozenset())
        ident = _identity(blocks={"MYBLOCK"})
        self.assertEqual(judge.identity_of("CYCLO", ident), "unknown")

    def test_no_keyed_unii_at_all_is_unknown(self):
        judge = rcpa.Judge(_records(rn={"REC": []}), {}, lambda k: frozenset())
        self.assertEqual(judge.identity_of("REC", _identity()), "unknown")


class JudgeVerdictTest(unittest.TestCase):
    """verdict(record, ident): own | filed_under | same_structure |
    unidentified keep a record; different_substance |
    combination_with_another_drug set it aside."""

    def test_the_molecules_own_record_is_own(self):
        judge = rcpa.Judge(_records(), {}, lambda k: frozenset())
        ident = _identity(own="D_X")
        self.assertEqual(judge.verdict("D_X", ident), "own")

    def test_a_heading_the_own_record_is_mapped_to_is_filed_under(self):
        # prednisolone acetate (the molecule's own SCR) is mapped to the
        # heading Prednisolone; judging that heading against the molecule
        # is MeSH itself saying which record the molecule is filed under.
        records = _records(mapped={"D_PRED_ACETATE": ["D_PREDNISOLONE"]})
        judge = rcpa.Judge(records, {}, lambda k: frozenset())
        ident = _identity(own="D_PRED_ACETATE")
        self.assertEqual(judge.verdict("D_PREDNISOLONE", ident), "filed_under")

    def test_a_tree_parent_of_the_own_record_is_filed_under(self):
        records = _records(parents={"D_SILYBIN": ["D_SILYMARIN"]})
        judge = rcpa.Judge(records, {}, lambda k: frozenset())
        ident = _identity(own="D_SILYBIN")
        self.assertEqual(judge.verdict("D_SILYMARIN", ident), "filed_under")

    def test_a_no_unii_scr_mapped_to_one_differing_heading_is_different_substance(self):
        # FX006: tafamidis linked, through the code name, to a no-UNII SCR
        # mapped to exactly one heading, Triamcinolone Acetonide - a product
        # name resolving to one different structure.
        records = _records(
            rn={"D_TRIAM": ["UNII_TRIAM"]},
            mapped={"FX006": ["D_TRIAM"]})
        unii_key = {"UNII_TRIAM": "TRIAM_KEY"}
        blocks_by_key = {"TRIAM_KEY": frozenset({"TRIAMBLOCK"})}
        judge = rcpa.Judge(records, unii_key,
                            lambda k: blocks_by_key.get(k, frozenset()))
        ident = _identity(blocks={"TAFABLOCK"}, own="TAFAMIDIS_OWN")
        self.assertEqual(judge.verdict("FX006", ident), "different_substance")

    def test_a_no_unii_scr_mapped_to_two_disagreeing_headings_is_unidentified(self):
        # LY-411575's chemical name maps to Alanine and Azepines - parts of
        # the molecule's name, not a single identity, so it is left
        # unresolved rather than read as a match or a mismatch.
        records = _records(mapped={"LY411575": ["D_ALANINE", "D_AZEPINES"]})
        judge = rcpa.Judge(records, {}, lambda k: frozenset())
        ident = _identity(blocks={"LYBLOCK"}, own="LY_OWN")
        self.assertEqual(judge.verdict("LY411575", ident), "unidentified")

    def test_a_combination_with_a_heading_that_has_its_own_actions_is_set_aside(self):
        # "Ambene": phenylbutazone (the molecule) plus aminopyrine, which
        # MeSH gives its own pharmacological actions - so the combination
        # record speaks for a second drug, not only for this one.
        records = _records(
            mapped={"AMBENE": [rcpa.DRUG_COMBINATIONS, "PHENYLBUTAZONE", "AMINOPYRINE"]},
            pa={"AMINOPYRINE": frozenset({"D_SOME_ACTION"})})
        judge = rcpa.Judge(records, {}, lambda k: frozenset())
        ident = _identity(own="PHENYLBUTAZONE")
        self.assertEqual(judge.verdict("AMBENE", ident),
                          "combination_with_another_drug")
        self.assertIn("combination_with_another_drug", rcpa.SET_ASIDE)

    def test_a_combination_with_an_actionless_excipient_is_kept(self):
        # brexanolone's infusion product is brexanolone plus a cyclodextrin,
        # which MeSH gives no action at all - nothing else in it is a drug.
        records = _records(
            mapped={"BREX_INF": [rcpa.DRUG_COMBINATIONS, "BREXANOLONE", "CYCLODEXTRIN"]})
        judge = rcpa.Judge(records, {}, lambda k: frozenset())
        ident = _identity(own="BREXANOLONE")
        self.assertNotIn(judge.verdict("BREX_INF", ident), rcpa.SET_ASIDE)


class FilterActionsTest(unittest.TestCase):
    """filter_actions() keeps an action unless every linked record that
    supplies it was set aside, and names what it set aside as (action
    descriptor, record, verdict)."""

    def setUp(self):
        self.mesh = {"concept": {
            "PA_A": "D_ACT_A", "PA_B": "D_ACT_B", "PA_C": "D_ACT_C",
            "PA_D": "D_ACT_D", "PA_E": "D_ACT_E",
        }}
        records = _records(
            concept={"C_R1": "R1", "C_R2": "R2", "C_R3": "R3"},
            pa={"R1": frozenset({"D_ACT_A", "D_ACT_C"}),
                "R2": frozenset({"D_ACT_B", "D_ACT_C", "D_ACT_D"}),
                "R3": frozenset({"D_ACT_D"}),
                "SOME_OTHER_DRUG": frozenset({"D_ACT_X"})},
            rn={"R2": ["UNII_R2"]},
            mapped={"R3": [rcpa.DRUG_COMBINATIONS, "R1", "SOME_OTHER_DRUG"]})
        unii_key = {"UNII_R2": "R2_KEY"}
        blocks_by_key = {"R2_KEY": frozenset({"OTHERBLOCK"})}
        self.judge = rcpa.Judge(records, unii_key,
                                lambda k: blocks_by_key.get(k, frozenset()))
        self.ident = _identity(blocks={"MYBLOCK"}, own="R1")
        self.concepts = ["C_R1", "C_R2", "C_R3"]

    def test_verdicts_behind_the_fixture(self):
        # R1 is the molecule's own record; R2 names a different structure
        # through its keyed UNII; R3 is a combination with another drug.
        self.assertEqual(self.judge.verdict("R1", self.ident), "own")
        self.assertEqual(self.judge.verdict("R2", self.ident), "different_substance")
        self.assertEqual(self.judge.verdict("R3", self.ident),
                          "combination_with_another_drug")

    def test_an_action_no_linked_record_supplies_is_kept(self):
        acts = [("PA_E", "Action E")]
        kept, aside = rcpa.filter_actions(
            acts, self.concepts, self.ident, self.mesh, self.judge)
        self.assertEqual(kept, acts)
        self.assertEqual(aside, [])

    def test_an_action_only_a_set_aside_record_supplies_is_dropped(self):
        acts = [("PA_B", "Action B")]  # only R2 (set aside) supplies D_ACT_B
        kept, aside = rcpa.filter_actions(
            acts, self.concepts, self.ident, self.mesh, self.judge)
        self.assertEqual(kept, [])
        self.assertEqual(aside, [("D_ACT_B", "R2", "different_substance")])

    def test_an_action_from_one_set_aside_and_one_kept_record_is_kept(self):
        acts = [("PA_C", "Action C")]  # R1 (own, kept) and R2 (set aside)
        kept, aside = rcpa.filter_actions(
            acts, self.concepts, self.ident, self.mesh, self.judge)
        self.assertEqual(kept, acts)
        self.assertEqual(aside, [])

    def test_an_action_from_two_set_aside_records_is_dropped_and_both_named(self):
        acts = [("PA_D", "Action D")]  # R2 and R3, both set aside
        kept, aside = rcpa.filter_actions(
            acts, self.concepts, self.ident, self.mesh, self.judge)
        self.assertEqual(kept, [])
        self.assertEqual(sorted(aside), sorted([
            ("D_ACT_D", "R2", "different_substance"),
            ("D_ACT_D", "R3", "combination_with_another_drug"),
        ]))


class ResolveWithRecordFilteringTest(unittest.TestCase):
    """resolve()'s optional records_for/idents/judge parameters route every
    compound's actions through filter_actions before the ambiguity check,
    and report what was set aside."""

    def setUp(self):
        self.mesh = _mesh()

    def test_a_set_aside_action_is_excluded_and_counted(self):
        acts = [("M0000929", "Antidepressive Agents, Tricyclic"),
                ("M0000928", "Antidepressive Agents")]
        cids_for = lambda key: {"KEY1": [111]}.get(key, [])
        actions_for = lambda cid: acts if cid == 111 else []
        records_for = lambda cid: ["C_OWN", "C_OTHER"] if cid == 111 else []

        records = _records(
            concept={"C_OWN": "R_OWN", "C_OTHER": "R_OTHER"},
            pa={"R_OWN": frozenset({"D000928"}), "R_OTHER": frozenset({"D000929"})},
            rn={"R_OTHER": ["UNII_OTHER"]})
        unii_key = {"UNII_OTHER": "OTHER_KEY"}
        blocks_by_key = {"OTHER_KEY": frozenset({"OTHERBLOCK"})}
        judge = rcpa.Judge(records, unii_key,
                            lambda k: blocks_by_key.get(k, frozenset()))
        idents = {1: _identity(blocks={"SELFBLOCK"}, own="R_OWN")}

        rows, labels, counts, aside = rcpa.resolve(
            [(1, "KEY1")], self.mesh, cids_for, actions_for,
            records_for=records_for, idents=idents, judge=judge)

        # The tricyclic action came only from R_OTHER, set aside as a
        # different substance; only the own record's action survives.
        self.assertEqual([r[2] for r in rows], ["D000928"])
        self.assertEqual(counts["resolved"], 1)
        self.assertEqual(counts["links_set_aside"], 1)
        self.assertEqual(counts["molecules_with_a_link_set_aside"], 1)
        self.assertEqual(aside, [(1, "D000929", "R_OTHER", "different_substance")])

    def test_records_for_none_leaves_resolve_unfiltered(self):
        # Existing behaviour (ResolveTest above) is unchanged when the new
        # parameters are simply not supplied.
        cids_for, actions_for = ResolveTest._fetchers(
            {"KEY1": [111]},
            {111: [("M0000929", "Antidepressive Agents, Tricyclic")]})
        rows, labels, counts, aside = rcpa.resolve(
            [(1, "KEY1")], self.mesh, cids_for, actions_for)
        self.assertEqual(rows, [(1, "mesh_pa", "D000929", "",
                                  "Antidepressive Agents, Tricyclic", "CID:111")])
        self.assertEqual(aside, [])
        self.assertNotIn("links_set_aside", counts)


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


class OwnRecordTest(unittest.TestCase):
    """own_record(): the parent's own structure decides it whenever it
    resolves to exactly one record; the forms are read only once the parent
    reaches nothing, and two records is refused rather than guessed at
    (invariant 6)."""

    def test_the_parent_key_alone_settles_it_forms_are_never_consulted(self):
        unii_by_key = {"PARENT_KEY": {"U1"}, "FORM_KEY": {"U2"}}
        by_unii = {"U1": {"REC1"}, "U2": {"REC2"}}
        self.assertEqual(
            rcpa.own_record(["PARENT_KEY", "FORM_KEY"], unii_by_key, by_unii), "REC1")

    def test_forms_are_read_only_once_the_parent_reaches_nothing(self):
        unii_by_key = {"FORM_KEY": {"U2"}}  # no entry for PARENT_KEY at all
        by_unii = {"U2": {"REC2"}}
        self.assertEqual(
            rcpa.own_record(["PARENT_KEY", "FORM_KEY"], unii_by_key, by_unii), "REC2")

    def test_two_records_refuses_rather_than_guesses(self):
        unii_by_key = {"PARENT_KEY": {"U1", "U2"}}
        by_unii = {"U1": {"REC1"}, "U2": {"REC2"}}
        self.assertIsNone(rcpa.own_record(["PARENT_KEY"], unii_by_key, by_unii))

    def test_nothing_found_at_all_is_none(self):
        self.assertIsNone(rcpa.own_record(["PARENT_KEY"], {}, {}))


class ChemblParentBlocksTest(unittest.TestCase):
    """chembl_parent_blocks(): InChIKey -> the first blocks of the parent and
    active moiety ChEMBL files that exact structure under, cached per key."""

    def setUp(self):
        self.chembl = sqlite3.connect(":memory:")
        self.chembl.executescript("""
            CREATE TABLE compound_structures (
                molregno INTEGER, standard_inchi_key TEXT);
            CREATE TABLE molecule_hierarchy (
                molregno INTEGER, parent_molregno INTEGER, active_molregno INTEGER);
        """)
        self.chembl.executemany(
            "INSERT INTO compound_structures VALUES (?, ?)", [
                (1, "QUERYKEY"), (2, "QUERYKEY"),  # two deposits, one structure
                (10, "PARENTFULLKEYXXXX"), (20, "ACTIVEFULLKEYYYYY"),
            ])
        self.chembl.executemany(
            "INSERT INTO molecule_hierarchy VALUES (?, ?, ?)", [
                (1, 10, 20), (2, 10, None),
            ])

    def test_returns_the_first_blocks_of_parent_and_active_moiety(self):
        lookup = rcpa.chembl_parent_blocks(self.chembl)
        self.assertEqual(lookup("QUERYKEY"),
                          frozenset({"PARENTFULLKEYXXXX"[:14], "ACTIVEFULLKEYYYYY"[:14]}))

    def test_a_key_chembl_does_not_hold_is_empty(self):
        lookup = rcpa.chembl_parent_blocks(self.chembl)
        self.assertEqual(lookup("NOTHING_LIKE_THIS"), frozenset())

    def test_the_result_is_cached_after_the_first_lookup(self):
        lookup = rcpa.chembl_parent_blocks(self.chembl)
        first = lookup("QUERYKEY")
        self.chembl.execute("DELETE FROM compound_structures")
        # a fresh lookup would find nothing now; the cached one still does.
        self.assertEqual(lookup("QUERYKEY"), first)


class IdentitiesTest(unittest.TestCase):
    """identities(): every InChIKey block of a molecule, its forms and the
    active moiety ChEMBL names for each, and the one MeSH record its own
    UNII reaches."""

    def test_blocks_uniis_and_own_across_a_parent_form_and_active_moiety(self):
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL_P", inchikey="PKEY")
        # one non-parent form, filed in ChEMBL under molregno 100
        conn.execute(
            "INSERT INTO molecule_forms(parent_molregno, molregno, is_parent)"
            " VALUES (?, 100, 0)", (parent,))

        chembl = sqlite3.connect(":memory:")
        chembl.executescript("""
            CREATE TABLE molecule_hierarchy (molregno INTEGER, active_molregno INTEGER);
            CREATE TABLE compound_structures (molregno INTEGER, standard_inchi_key TEXT);
        """)
        chembl.execute("INSERT INTO molecule_hierarchy VALUES (100, 200)")  # salt -> moiety
        chembl.executemany("INSERT INTO compound_structures VALUES (?, ?)", [
            (100, "SKEY"), (200, "AKEY")])

        records = _records(rn={"REC_OWN": ["UNII_P"]})
        unii_by_key = {"PKEY": {"UNII_P"}}  # FDA's own UNII for the parent's structure

        idents = rcpa.identities(conn, chembl, unii_by_key, records)

        self.assertEqual(
            idents[parent],
            rcpa.Identity(frozenset({"PKEY", "SKEY", "AKEY"}),
                          frozenset({"UNII_P"}), "REC_OWN"))


if __name__ == "__main__":
    unittest.main()
