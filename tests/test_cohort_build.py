"""Tests for the cohort-1 selection and evidence semantics.

These are not here for coverage. Each one locks in a decision from
docs/COHORT-1-DECISIONS.md that would be silently wrong if changed, or a
failure that has already happened once - in the analysis package this
production pipeline was derived from, in the report's prose, or in ChEMBL
itself.

They run offline against a small in-memory database shaped like ChEMBL, so the
whole file is fast and needs neither the 30 GB release nor a built cohort.
"""

import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from cohort import (classes as classes_mod, common, evidence, labels as labels_mod,
                    scope as scope_mod, selection, targets as targets_mod)


# ---------------------------------------------------------------------------
# A miniature ChEMBL
# ---------------------------------------------------------------------------

CHEMBL_DDL = """
CREATE TABLE molecule_dictionary (
    molregno INTEGER PRIMARY KEY, chembl_id TEXT, pref_name TEXT,
    molecule_type TEXT, structure_type TEXT, max_phase REAL, first_approval INTEGER,
    withdrawn_flag INTEGER DEFAULT 0, therapeutic_flag INTEGER, natural_product INTEGER,
    prodrug INTEGER, polymer_flag INTEGER, inorganic_flag INTEGER,
    black_box_warning INTEGER, chirality INTEGER, chemical_probe INTEGER,
    orphan INTEGER, usan_stem TEXT, usan_substem TEXT, usan_stem_definition TEXT);
CREATE TABLE molecule_hierarchy (molregno INTEGER, parent_molregno INTEGER);
CREATE TABLE molecule_synonyms (molregno INTEGER, synonyms TEXT, syn_type TEXT);
CREATE TABLE atc_classification (
    level5 TEXT PRIMARY KEY, level4 TEXT, level3 TEXT, level2 TEXT, level1 TEXT,
    who_name TEXT, level1_description TEXT, level2_description TEXT,
    level3_description TEXT, level4_description TEXT);
CREATE TABLE molecule_atc_classification (molregno INTEGER, level5 TEXT);
CREATE TABLE usan_stems (stem TEXT, subgroup TEXT, annotation TEXT);
CREATE TABLE drug_indication (
    drugind_id INTEGER PRIMARY KEY, record_id INTEGER, molregno INTEGER,
    max_phase_for_ind REAL, mesh_id TEXT, mesh_heading TEXT, efo_id TEXT, efo_term TEXT);
CREATE TABLE indication_refs (
    indref_id INTEGER PRIMARY KEY, drugind_id INTEGER, ref_type TEXT, ref_id TEXT,
    ref_url TEXT);
CREATE TABLE target_dictionary (
    tid INTEGER PRIMARY KEY, chembl_id TEXT, pref_name TEXT, target_type TEXT,
    organism TEXT, tax_id INTEGER);
CREATE TABLE target_components (tid INTEGER, component_id INTEGER);
CREATE TABLE component_sequences (
    component_id INTEGER PRIMARY KEY, accession TEXT, description TEXT,
    component_type TEXT);
CREATE TABLE component_class (
    component_id INTEGER, protein_class_id INTEGER, comp_class_id INTEGER);
CREATE TABLE protein_classification (
    protein_class_id INTEGER PRIMARY KEY, parent_id INTEGER, pref_name TEXT,
    class_level INTEGER);
CREATE TABLE component_synonyms (
    component_id INTEGER, component_synonym TEXT, syn_type TEXT);
CREATE TABLE assays (
    assay_id INTEGER PRIMARY KEY, chembl_id TEXT, description TEXT, assay_type TEXT,
    confidence_score INTEGER, relationship_type TEXT, variant_id INTEGER, tid INTEGER,
    bao_format TEXT);
CREATE TABLE bioassay_ontology (bao_id TEXT PRIMARY KEY, label TEXT);
CREATE TABLE docs (
    doc_id INTEGER PRIMARY KEY, chembl_id TEXT, pubmed_id INTEGER, doi TEXT,
    patent_id TEXT, doc_type TEXT, year INTEGER, journal TEXT, title TEXT);
CREATE TABLE activities (
    activity_id INTEGER PRIMARY KEY, molregno INTEGER, assay_id INTEGER, doc_id INTEGER,
    standard_type TEXT, standard_relation TEXT, standard_value REAL,
    standard_units TEXT, data_validity_comment TEXT, potential_duplicate INTEGER,
    activity_comment TEXT);
CREATE TABLE drug_mechanism (
    mec_id INTEGER PRIMARY KEY, molregno INTEGER, tid INTEGER, action_type TEXT,
    mechanism_of_action TEXT, direct_interaction INTEGER, molecular_mechanism INTEGER,
    mechanism_comment TEXT, selectivity_comment TEXT, variant_id INTEGER,
    record_id INTEGER);
CREATE TABLE mechanism_refs (
    mecref_id INTEGER PRIMARY KEY, mec_id INTEGER, ref_type TEXT, ref_id TEXT,
    ref_url TEXT);
CREATE TABLE action_type (action_type TEXT PRIMARY KEY, parent_type TEXT);
CREATE TABLE compound_properties (molregno INTEGER PRIMARY KEY, full_mwt REAL,
    full_molformula TEXT);
CREATE TABLE compound_structures (molregno INTEGER PRIMARY KEY, canonical_smiles TEXT,
    standard_inchi_key TEXT);
"""


def fake_chembl():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CHEMBL_DDL)
    return conn


def add_molecule(conn, molregno, chembl_id, name, mtype="Small molecule",
                 parent=None, structure_type="MOL", max_phase=4.0, withdrawn=0):
    conn.execute(
        "INSERT INTO molecule_dictionary(molregno, chembl_id, pref_name, molecule_type,"
        " structure_type, max_phase, withdrawn_flag) VALUES(?,?,?,?,?,?,?)",
        (molregno, chembl_id, name, mtype, structure_type, max_phase, withdrawn))
    conn.execute("INSERT INTO molecule_hierarchy(molregno, parent_molregno) VALUES(?,?)",
                 (molregno, parent if parent is not None else molregno))


def add_atc(conn, molregno, level5, level1="N", level3=None):
    conn.execute(
        "INSERT OR IGNORE INTO atc_classification(level5, level4, level3, level2, level1,"
        " who_name, level3_description) VALUES(?,?,?,?,?,?,?)",
        (level5, level5[:5], level3 or level5[:4], level5[:3], level1, "who", "desc"))
    conn.execute("INSERT INTO molecule_atc_classification(molregno, level5) VALUES(?,?)",
                 (molregno, level5))


def add_indication(conn, drugind_id, molregno, mesh_id, phase, heading="x"):
    conn.execute(
        "INSERT INTO drug_indication(drugind_id, record_id, molregno, max_phase_for_ind,"
        " mesh_id, mesh_heading) VALUES(?,?,?,?,?,?)",
        (drugind_id, drugind_id, molregno, phase, mesh_id, heading))


def add_indication_refs(conn, drugind_id, ref_type, ref_id, indref_id=None):
    conn.execute(
        "INSERT INTO indication_refs(indref_id, drugind_id, ref_type, ref_id, ref_url)"
        " VALUES(?,?,?,?,?)",
        (indref_id if indref_id is not None else drugind_id * 100,
         drugind_id, ref_type, ref_id, "https://example.invalid/" + ref_id))


def empty_label_status():
    """config/cohort1_label_status.json for a release with no label-backed record."""
    return {"chembl_release": common.CHEMBL_RELEASE, "checked": {}, "records": {}}


def label_record(verdict, molregno, mesh_id, set_ids, trials=(), trial_phase=None):
    """One record as scripts/check_dailymed_labels.py writes it."""
    rec = {"verdict": verdict, "molregno": molregno, "mesh_id": mesh_id,
           "labels": [{"set_id": s, "title": "T", "labeler": "L",
                       "categories": ["UNAPPROVED DRUG OTHER"],
                       "marketed_from": "01/01/2011", "marketed_until": "12/31/2017"}
                      for s in set_ids],
           "trials": [{"nct": t, "phases": None} for t in trials]}
    if verdict == "unapproved":
        rec["trial_phase"] = trial_phase
    return rec


def descriptor(mesh_id, label, trees, in_core, reasons, boundary=()):
    return scope_mod.Descriptor(
        mesh_id=mesh_id, label=label, tree_numbers=tuple(trees), in_core=in_core,
        core_trees=tuple(t for t in trees if t.startswith("C10") or t.startswith("F03")),
        boundary_classes=tuple(boundary), in_scope=bool(reasons),
        scope_reasons=tuple(reasons))


def policy():
    return common.load_policy("cohort1_selection.json")


# ---------------------------------------------------------------------------
# Scope: the adopted indication boundary
# ---------------------------------------------------------------------------

class ScopeTest(unittest.TestCase):
    """The scope is rebuilt from the pinned classification, not refetched."""

    @classmethod
    def setUpClass(cls):
        cls.pol = policy()
        cls.desc = scope_mod.load(cls.pol)

    def test_recomputed_core_matches_the_pinned_column(self):
        # scope_mod.load raises if the recomputation disagrees with the saved
        # in_core_scope column, so reaching here at all is the assertion. The
        # count is checked too: 974 core descriptors is what the report
        # measured, and a silent change to the base scope would move it.
        self.assertEqual(sum(1 for d in self.desc.values() if d.in_core), 974)

    def test_every_descriptor_d02_names_is_in_scope(self):
        self.assertEqual(scope_mod.fixtures_check(self.desc, self.pol), [])

    def test_pain_tree_alone_does_not_deliver_the_requirement(self):
        # This is the audit finding. Neuralgia and postherpetic neuralgia do
        # arrive through the Pain tree, but trigeminal neuralgia, facial
        # neuralgia and fibromyalgia carry no Pain-tree placement at all, so an
        # implementation that added only S4 would quietly drop three of the six
        # descriptors D02 names.
        for mesh_id in ("D009437", "D051474", "D060545"):
            self.assertIn("general_pain", self.desc[mesh_id].scope_reasons, mesh_id)
        for mesh_id in ("D014277", "D005156", "D005356"):
            self.assertNotIn("general_pain", self.desc[mesh_id].scope_reasons, mesh_id)
            self.assertTrue(self.desc[mesh_id].in_scope, mesh_id)

    def test_explicit_inclusions_override_the_boundary_exclusions(self):
        fibro = self.desc["D005356"]
        self.assertFalse(fibro.in_core)
        self.assertIn("muscle_and_neuromuscular_junction", fibro.boundary_classes)
        self.assertEqual(fibro.scope_reasons, ("explicit_fibromyalgia",))

        trigeminal = self.desc["D014277"]
        self.assertIn("peripheral_nervous_system", trigeminal.boundary_classes)
        self.assertIn("explicit_neuropathic", trigeminal.scope_reasons)

    def test_cns_conditions_filed_outside_c10_and_f03_are_admitted_by_id(self):
        # D16: MeSH files Anxiety and Depression as emotions (F01), Smoking
        # Cessation as a behaviour (F01) and Anesthesia as a procedure (E03).
        # Each is admitted by its own id with its own reason, and the branches
        # around them are not opened.
        for mesh_id in ("D001007", "D003863", "D016540", "D000758"):
            d = self.desc[mesh_id]
            self.assertFalse(d.in_core, mesh_id)
            self.assertEqual(d.scope_reasons, ("explicit_cns_heading",), mesh_id)
        self.assertFalse(self.desc["D000374"].in_scope, "the rest of F01 is not opened")  # Aggression

    def test_the_report_prose_about_neuralgia_is_not_reproduced(self):
        # The report said Neuralgia keeps an in-core C10 placement at
        # C10.597.617.470. The saved row says otherwise, and the boundary
        # review's correction is the accurate one. If this ever passes by
        # in_core the scope has drifted back to the prose.
        neuralgia = self.desc["D009437"]
        self.assertFalse(neuralgia.in_core)
        self.assertIn("C10.668.829.600", neuralgia.tree_numbers)
        self.assertNotIn("C10.597.617.470", neuralgia.tree_numbers)

    def test_boundary_exclusions_that_still_apply(self):
        # No blanket oncology, peripheral-nerve or muscle route was adopted.
        for mesh_id in ("D016543",      # Central Nervous System Neoplasms
                        "D010523",      # Peripheral Nervous System Diseases
                        "D020388"):     # Muscular Dystrophy, Duchenne
            self.assertFalse(self.desc[mesh_id].in_scope, mesh_id)

    def test_the_pain_tree_is_accepted_at_its_measured_breadth(self):
        # The boundary review measured that the saved Pain tree reaches angina.
        # D02 accepts that breadth with visible labels rather than inventing a
        # narrower exception, so this is deliberate, not an oversight.
        angina = self.desc["D000787"]
        self.assertTrue(angina.in_scope)
        self.assertEqual(angina.scope_reasons, ("general_pain",))

    def test_an_unclassified_descriptor_is_a_failure_not_an_exclusion(self):
        with self.assertRaises(common.PolicyError):
            scope_mod.assert_covers(self.desc, {"D000000_not_a_real_descriptor"})


# ---------------------------------------------------------------------------
# Selection: admission routes, identity, seeds
# ---------------------------------------------------------------------------

class SelectionTest(unittest.TestCase):

    def setUp(self):
        self.pol = json.loads(json.dumps(policy()))
        self.conn = fake_chembl()
        # A tiny scope: one core descriptor, one pain descriptor, one excluded.
        self.desc = {
            "D_CORE": descriptor("D_CORE", "Epilepsy", ["C10.228"], True, ["core"]),
            "D_PAIN": descriptor("D_PAIN", "Pain", ["C23.888.592.612"], False,
                                 ["general_pain"], ["general_pain"]),
            "D_FIBRO": descriptor("D_FIBRO", "Fibromyalgia", ["C10.668.491.425"], False,
                                  ["explicit_fibromyalgia"],
                                  ["muscle_and_neuromuscular_junction"]),
            "D_OUT": descriptor("D_OUT", "Asthma", ["C08.127"], False, []),
        }
        # Seeds are irrelevant to most of these tests; keep one that exists.
        add_molecule(self.conn, 900, "CHEMBL113", "CAFFEINE")
        self.pol["seeds"]["molecules"] = [["caffeine", "CHEMBL113"]]

    def run_selection(self, label_cfg=None):
        return selection.run(self.conn, self.pol, self.desc,
                             labels_mod.LabelStatus(self.conn,
                                                    cfg=label_cfg or empty_label_status()))

    def test_atc_n_admits_with_no_indication_at_all(self):
        add_molecule(self.conn, 1, "CHEMBL_A", "ATC ONLY")
        add_atc(self.conn, 1, "N05AA01")
        m = self.run_selection()["members"][1]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.admission_reason, "route_atc_n")
        self.assertEqual(m.qualifying_indications, ())

    def test_the_indication_route_needs_phase_one_on_that_indication(self):
        # D21 lowered the floor from Phase 3 to Phase 1. Early Phase 1 (0.5)
        # is below it.
        add_molecule(self.conn, 2, "CHEMBL_B", "EARLY PHASE 1 ONLY", max_phase=4.0)
        add_indication(self.conn, 10, 2, "D_CORE", 0.5)
        members = self.run_selection()["members"]
        self.assertNotIn(2, members)   # not a seed, not admitted

        add_molecule(self.conn, 3, "CHEMBL_C", "PHASE 1", max_phase=1.0)
        add_indication(self.conn, 11, 3, "D_CORE", 1.0)
        m = self.run_selection()["members"][3]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.admission_reason, "route_indication")

    def test_the_floor_is_read_from_the_policy(self):
        self.assertEqual(policy()["admission_routes"]["indication"]["min_phase"], 1)

    def test_an_indication_carries_the_trials_its_phase_is_read_off(self):
        # ChEMBL files one ClinicalTrials reference per drug_indication whose
        # ref_id is a comma-joined list of NCT ids. They are split, de-duplicated
        # and sorted, and only the identifiers are kept - the ref_url is a
        # clinicaltrials.gov search over the same ids, and this page builds a
        # link from an identifier rather than storing somebody else's query.
        add_molecule(self.conn, 40, "CHEMBL_T", "TRIALLED")
        add_indication(self.conn, 50, 40, "D_CORE", 3.0)
        add_indication_refs(self.conn, 50, "ClinicalTrials",
                            "NCT00000002,NCT00000001,NCT00000002")
        add_indication_refs(self.conn, 50, "DailyMed", "a-set-id", indref_id=5001)
        m = self.run_selection()["members"][40]
        self.assertEqual(m.qualifying_indications[0]["trial_ids"],
                         ("NCT00000001", "NCT00000002"))

    def test_an_indication_with_no_registered_trial_keeps_its_phase(self):
        # A missing registration is not a missing indication, and never a
        # statement that no trial was run.
        add_molecule(self.conn, 41, "CHEMBL_U", "UNREGISTERED")
        add_indication(self.conn, 51, 41, "D_CORE", 4.0)
        m = self.run_selection()["members"][41]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.qualifying_indications[0]["trial_ids"], ())

    def test_the_out_of_scope_diseases_are_counted_but_not_stored(self):
        # The viewer's indication list holds only what the adopted scope covers,
        # so it needs to know how much of the molecule's record that is. The
        # count spans every therapeutic area; the rows do not.
        add_molecule(self.conn, 42, "CHEMBL_V", "BROAD")
        add_indication(self.conn, 52, 42, "D_CORE", 4.0)
        add_indication(self.conn, 53, 42, "D_OUT", 4.0)
        add_indication(self.conn, 54, 42, "D_OUT", 3.0)   # same disease twice
        m = self.run_selection()["members"][42]
        self.assertEqual(len(m.qualifying_indications), 1)
        self.assertEqual(m.n_indications_chembl, 2)       # distinct diseases

    def test_approvals_outside_the_scope_are_named_across_the_family(self):
        # The viewer lists only in-scope diseases, so an approved drug whose
        # approvals all fall outside them needs to say what they were for -
        # bromazepam is approved for Anxiety and listed only at phase 3. Only
        # phase 4 counts, a disease filed twice is one name, a salt's approval
        # is the parent's, and an in-scope approval is already on the list.
        add_molecule(self.conn, 43, "CHEMBL_W", "ELSEWHERE")
        add_molecule(self.conn, 44, "CHEMBL_W_SALT", "ELSEWHERE HCL", parent=43)
        add_indication(self.conn, 55, 43, "D_CORE", 4.0, heading="Epilepsy")
        add_indication(self.conn, 56, 43, "D_OUT", 4.0, heading="Asthma")
        add_indication(self.conn, 57, 44, "D_OUT", 4.0, heading="Asthma")
        add_indication(self.conn, 58, 44, "D_OUT2", 4.0, heading="acne")
        add_indication(self.conn, 59, 43, "D_OUT3", 3.0, heading="Gout")
        self.desc["D_OUT2"] = descriptor("D_OUT2", "Acne", ["C17.1"], False, [])
        self.desc["D_OUT3"] = descriptor("D_OUT3", "Gout", ["C05.1"], False, [])
        m = self.run_selection()["members"][43]
        self.assertEqual(m.approved_elsewhere, ("acne", "Asthma"))

    # ---- D23: what stands behind Approved -----------------------------------

    def _isometheptene(self, trials=(), trial_phase=None, extra_refs=()):
        # Approved for migraine on US labels alone, every one of them sold as
        # UNAPPROVED DRUG OTHER: FDA never approved it.
        add_molecule(self.conn, 70, "CHEMBL_ISO", "ISOMETHEPTENE", max_phase=4.0)
        add_indication(self.conn, 80, 70, "D_CORE", 4.0, heading="Migraine")
        add_indication_refs(self.conn, 80, "DailyMed", "set-a", indref_id=8001)
        add_indication_refs(self.conn, 80, "DailyMed", "set-b", indref_id=8002)
        if trials:
            add_indication_refs(self.conn, 80, "ClinicalTrials", ",".join(trials),
                                indref_id=8003)
        for i, (t, r) in enumerate(extra_refs):
            add_indication_refs(self.conn, 80, t, r, indref_id=8010 + i)
        cfg = empty_label_status()
        cfg["records"]["80"] = label_record("unapproved", 70, "D_CORE", ["set-a", "set-b"],
                                            trials, trial_phase)
        return cfg

    def test_an_approval_resting_only_on_unapproved_labels_admits_nothing(self):
        sel = self.run_selection(self._isometheptene())
        self.assertNotIn(70, sel["members"])

    def test_an_unapproved_label_is_stated_as_one_and_takes_back_the_molecules_approval(self):
        # A seed stays in the catalogue, so its record can be read.
        self.pol["seeds"]["molecules"].append(["isometheptene", "CHEMBL_ISO"])
        m = self.run_selection(self._isometheptene())["members"][70]
        e = m.near_miss_indications[0]
        self.assertIsNone(e["max_phase_for_ind"])
        self.assertEqual(e["phase_label"], labels_mod.MARKETED_UNAPPROVED)
        self.assertEqual(e["approval_basis"], "unapproved")
        self.assertEqual(e["chembl_max_phase"], 4.0)
        self.assertEqual([lab["set_id"] for lab in e["unapproved_labels"]], ["set-a", "set-b"])
        self.assertEqual(m.max_phase, 4.0)                  # ChEMBL's, kept
        self.assertEqual(m.approval_status, "unapproved_marketing")
        self.assertIsNone(m.max_phase_checked)

    def test_an_unapproved_record_takes_the_phase_of_the_trials_it_cites(self):
        m = self.run_selection(self._isometheptene(["NCT01"], 2.0))["members"][70]
        e = m.qualifying_indications[0]
        self.assertEqual((e["max_phase_for_ind"], e["phase_label"]), (2.0, "Phase 2"))
        self.assertEqual(m.approval_status, "unapproved_marketing")
        self.assertEqual(m.max_phase_checked, 2.0)

    def test_an_atc_class_beside_unapproved_labels_is_not_contradicted(self):
        cfg = self._isometheptene(extra_refs=[("ATC", "N02CX")])
        m = self.run_selection(cfg)["members"][70]
        e = m.qualifying_indications[0]
        self.assertEqual((e["phase_label"], e["approval_basis"]), ("Approved", "atc"))
        self.assertIsNone(m.approval_status)

    def test_a_label_with_an_application_is_an_approval(self):
        add_molecule(self.conn, 71, "CHEMBL_RX", "APPROVED")
        add_indication(self.conn, 81, 71, "D_CORE", 4.0)
        add_indication_refs(self.conn, 81, "DailyMed", "set-c", indref_id=8101)
        cfg = empty_label_status()
        cfg["checked"]["label"] = [81]
        e = self.run_selection(cfg)["members"][71].qualifying_indications[0]
        self.assertEqual((e["max_phase_for_ind"], e["phase_label"], e["approval_basis"]),
                         (4.0, "Approved", "label"))
        self.assertIsNone(e["unapproved_labels"] or None)

    def test_a_phase_4_trial_alone_stands_as_an_approval_and_says_so(self):
        # A post-marketing trial usually studies the approved use: read as no
        # approval, it put desipramine's major depression and lidocaine's
        # neuralgia below Approved. It stands, and its basis names it.
        add_molecule(self.conn, 72, "CHEMBL_P4", "TRIALLED AFTER APPROVAL")
        add_indication(self.conn, 82, 72, "D_CORE", 4.0)
        add_indication_refs(self.conn, 82, "ClinicalTrials", "NCT02", indref_id=8201)
        m = self.run_selection()["members"][72]
        e = m.qualifying_indications[0]
        self.assertEqual((e["max_phase_for_ind"], e["phase_label"], e["approval_basis"]),
                         (4.0, "Approved", "trial"))
        self.assertIsNone(m.approval_status)

    def test_a_phase_4_trial_beside_unapproved_labels_is_a_trial(self):
        # The labels say there is no approval behind them, so the trial is read
        # as what it is, and the molecule keeps ChEMBL's approval somewhere.
        m = self.run_selection(self._isometheptene(["NCT03"], 4.0))["members"][70]
        e = m.qualifying_indications[0]
        self.assertEqual((e["max_phase_for_ind"], e["phase_label"], e["approval_basis"]),
                         (4.0, labels_mod.PHASE4_TRIAL, "unapproved"))
        self.assertIsNone(m.approval_status)

    def test_an_unapproved_label_is_not_an_approval_elsewhere(self):
        cfg = self._isometheptene()
        add_atc(self.conn, 70, "N02CX01")                    # stays a member by ATC
        add_indication(self.conn, 83, 70, "D_OUT", 4.0, heading="Asthma")
        add_indication_refs(self.conn, 83, "DailyMed", "set-d", indref_id=8301)
        cfg["records"]["83"] = label_record("unapproved", 70, "D_OUT", ["set-d"])
        m = self.run_selection(cfg)["members"][70]
        self.assertEqual(m.approved_elsewhere, ())

    def test_an_unchecked_label_backed_record_stops_the_build(self):
        # A new release, or a policy file from another: never read as approved.
        cfg = self._isometheptene()
        del cfg["records"]["80"]
        with self.assertRaises(common.PolicyError):
            self.run_selection(cfg)

    def test_a_record_citing_different_labels_stops_the_build(self):
        cfg = self._isometheptene()
        cfg["records"]["80"]["labels"].pop()
        with self.assertRaises(common.PolicyError):
            self.run_selection(cfg)

    def test_a_checked_record_that_is_no_longer_label_backed_stops_the_build(self):
        cfg = self._isometheptene(extra_refs=[("FDA", "label.pdf")])
        with self.assertRaises(common.PolicyError):
            self.run_selection(cfg)

    def test_the_molecule_level_max_phase_is_not_the_admission_test(self):
        # An Approved drug whose only in-scope indication sits at Early Phase 1
        # does not qualify through the indication route: the threshold is on
        # the indication, not on the highest phase across unrelated diseases.
        add_molecule(self.conn, 4, "CHEMBL_D", "APPROVED ELSEWHERE", max_phase=4.0)
        add_indication(self.conn, 12, 4, "D_CORE", 0.5)
        self.assertNotIn(4, self.run_selection()["members"])

    def test_missing_and_unknown_indication_phases_cannot_qualify(self):
        for i, phase in enumerate([None, -1.0, 0.5]):
            molregno = 20 + i
            add_molecule(self.conn, molregno, "CHEMBL_P%d" % i, "P%d" % i)
            add_indication(self.conn, 30 + i, molregno, "D_CORE", phase)
        members = self.run_selection()["members"]
        for i in range(3):
            self.assertNotIn(20 + i, members)

    def test_a_missing_phase_does_not_disqualify_an_atc_n_match(self):
        add_molecule(self.conn, 5, "CHEMBL_E", "ATC PLUS WEAK INDICATION")
        add_atc(self.conn, 5, "N02AA01")
        add_indication(self.conn, 13, 5, "D_CORE", None)
        m = self.run_selection()["members"][5]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.admission_reason, "route_atc_n")

    def test_pain_does_not_waive_the_phase_requirement(self):
        # Loperamide's saved Pain phase is 0.5. Adding the Pain tree admits the
        # descriptor, not the molecule.
        add_molecule(self.conn, 6, "CHEMBL841", "LOPERAMIDE")
        add_indication(self.conn, 14, 6, "D_PAIN", 0.5)
        self.assertNotIn(6, self.run_selection()["members"])

    def test_a_pain_indication_at_phase_one_does_admit(self):
        add_molecule(self.conn, 7, "CHEMBL_F", "PAIN PHASE 1")
        add_indication(self.conn, 15, 7, "D_PAIN", 1.0)
        m = self.run_selection()["members"][7]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.scope_reasons, ("general_pain",))

    def test_an_explicit_fibromyalgia_indication_admits_with_its_own_reason(self):
        add_molecule(self.conn, 8, "CHEMBL_G", "FIBRO DRUG")
        add_indication(self.conn, 16, 8, "D_FIBRO", 4.0)
        m = self.run_selection()["members"][8]
        self.assertTrue(m.in_cohort)
        self.assertEqual(m.scope_reasons, ("explicit_fibromyalgia",))

    def test_an_out_of_scope_indication_admits_nothing(self):
        add_molecule(self.conn, 9, "CHEMBL_H", "ASTHMA DRUG")
        add_indication(self.conn, 17, 9, "D_OUT", 4.0)
        self.assertNotIn(9, self.run_selection()["members"])

    def test_every_molecule_category_qualifies(self):
        # D03: no molecule-type filter. A protein, an antibody and an
        # unresolved structure all enter on the same routes as a small molecule.
        for i, (mtype, structure) in enumerate([
                ("Protein", "SEQ"), ("Antibody", "SEQ"), ("Unknown", "NONE"),
                ("Oligonucleotide", "SEQ")]):
            molregno = 40 + i
            add_molecule(self.conn, molregno, "CHEMBL_T%d" % i, "T%d" % i,
                         mtype=mtype, structure_type=structure)
            add_atc(self.conn, molregno, "N07X%02d" % i)
        members = self.run_selection()["members"]
        for i in range(4):
            self.assertTrue(members[40 + i].in_cohort)
        self.assertIn("structure_unresolved", members[42].identity_flags)

    def test_withdrawal_and_unresolved_structure_are_retained_and_flagged(self):
        add_molecule(self.conn, 50, "CHEMBL_W", "WITHDRAWN", structure_type="NONE",
                     withdrawn=1)
        add_atc(self.conn, 50, "N06AA99")
        m = self.run_selection()["members"][50]
        self.assertTrue(m.in_cohort)
        self.assertIn("withdrawn_in_family", m.identity_flags)
        self.assertIn("structure_unresolved", m.identity_flags)

    def test_forms_fold_onto_one_parent_row(self):
        add_molecule(self.conn, 60, "CHEMBL_PARENT", "BASE")
        add_molecule(self.conn, 61, "CHEMBL_SALT", "BASE HCL", parent=60)
        add_molecule(self.conn, 62, "CHEMBL_HYDRATE", "BASE HYDRATE", parent=60)
        add_atc(self.conn, 61, "N03AX99")     # the ATC code is on the salt
        members = self.run_selection()["members"]
        self.assertIn(60, members)
        self.assertNotIn(61, members)
        self.assertNotIn(62, members)
        parent = members[60]
        self.assertTrue(parent.route_atc_n)       # reached through the family
        self.assertEqual(len(parent.family), 3)
        carriers = [f["chembl_id"] for f in parent.family if f["carries_atc_n"]]
        self.assertEqual(carriers, ["CHEMBL_SALT"])

    def test_theophylline_is_one_row_at_its_parent_keeping_both_identities(self):
        add_molecule(self.conn, 70, "CHEMBL190", "THEOPHYLLINE ANHYDROUS",
                     mtype="Protein")
        add_molecule(self.conn, 71, "CHEMBL1355736", "THEOPHYLLINE MONOHYDRATE",
                     mtype="Protein", parent=70)
        add_indication(self.conn, 18, 71, "D_PAIN", 3.0)
        self.pol["seeds"]["molecules"] = [["caffeine", "CHEMBL113"],
                                          ["theophylline", "CHEMBL1355736"]]
        members = self.run_selection()["members"]
        self.assertIn(70, members)
        self.assertNotIn(71, members)
        theo = members[70]
        self.assertEqual(theo.parent_chembl_id, "CHEMBL190")
        self.assertEqual(theo.seed_name, "theophylline")
        aliases = {f["chembl_id"]: f["seed_alias"] for f in theo.family}
        self.assertEqual(aliases["CHEMBL1355736"], "theophylline")
        # The Protein typing is an annotation, not an exclusion (D03).
        self.assertIn("molecule_type_anomaly_theophylline", theo.identity_flags)
        self.assertTrue(theo.in_cohort)

    def test_a_seed_outside_the_cohort_is_retained_with_a_reason(self):
        add_molecule(self.conn, 80, "CHEMBL1114", "THEOBROMINE")
        self.pol["seeds"]["molecules"] = [["theobromine", "CHEMBL1114"]]
        m = self.run_selection()["members"][80]
        self.assertTrue(m.is_seed)
        self.assertFalse(m.in_cohort)
        self.assertEqual(m.admission_reason, "seed_only")
        self.assertIn("no ATC N code", m.exclusion_reason)

    def test_a_near_miss_indication_is_kept_so_the_reason_can_be_shown(self):
        add_molecule(self.conn, 81, "CHEMBL841", "LOPERAMIDE")
        add_indication(self.conn, 19, 81, "D_PAIN", 0.5)
        self.pol["seeds"]["molecules"] = [["loperamide", "CHEMBL841"]]
        m = self.run_selection()["members"][81]
        self.assertFalse(m.in_cohort)
        self.assertEqual(len(m.near_miss_indications), 1)
        self.assertIn("Early Phase 1", m.exclusion_reason)

    def test_seed_membership_is_recorded_separately_from_clinical_membership(self):
        add_molecule(self.conn, 90, "CHEMBL_SEEDY", "SEED AND MEMBER")
        add_atc(self.conn, 90, "N01AX99")
        self.pol["seeds"]["molecules"] = [["seedy", "CHEMBL_SEEDY"]]
        m = self.run_selection()["members"][90]
        self.assertTrue(m.is_seed)
        self.assertTrue(m.in_cohort)
        # Two independent facts, not one: the seed flag never stands in for an
        # admission route, and the route was earned.
        self.assertEqual(m.admission_reason, "route_atc_n")

    def test_admission_route_arithmetic_holds(self):
        add_molecule(self.conn, 100, "CHEMBL_X1", "BOTH")
        add_atc(self.conn, 100, "N05BA99")
        add_indication(self.conn, 20, 100, "D_CORE", 4.0)
        add_molecule(self.conn, 101, "CHEMBL_X2", "ATC")
        add_atc(self.conn, 101, "N05BA98")
        add_molecule(self.conn, 102, "CHEMBL_X3", "IND")
        add_indication(self.conn, 21, 102, "D_CORE", 4.0)
        a = self.run_selection()["arithmetic"]
        self.assertTrue(a["arithmetic_holds"])
        self.assertEqual(a["both_routes"], 1)
        self.assertEqual(a["atc_n_only"], 1)
        self.assertEqual(a["indication_only"], 1)

    def test_the_flagged_atc_branches_are_annotated_not_removed(self):
        add_molecule(self.conn, 110, "CHEMBL_LOCAL", "LIDOCAINE")
        add_atc(self.conn, 110, "N01BB02", level3="N01B")
        m = self.run_selection()["members"][110]
        self.assertTrue(m.in_cohort)
        self.assertIn("peripheral_site_of_action", m.atc_flags)


# ---------------------------------------------------------------------------
# Evidence: units, assignment, studies, tiers
# ---------------------------------------------------------------------------

def assessor():
    return evidence.Assessor(common.load_policy("cohort1_evidence.json"))


SMALL = {"chembl_id": "CHEMBL_M", "molecule_type": "Small molecule",
         "full_mwt": 200.0, "has_structure": 1}


class UnitTest(unittest.TestCase):

    def setUp(self):
        self.a = assessor()

    def test_native_nanomolar_is_exact(self):
        nm, status, conv = self.a.normalise("=", 5.0, "nM", SMALL)
        self.assertEqual((nm, status), (5.0, "exact"))
        self.assertEqual(conv["kind"], "native")

    def test_audited_concentration_units_convert_and_count(self):
        for units, value, expected in [("uM", 1.5, 1500.0), ("mM", 2.0, 2e6),
                                       ("M", 1e-6, 1000.0), ("pM", 1000.0, 1.0),
                                       ("pmol/L", 19.2, 0.0192)]:
            nm, status, conv = self.a.normalise("=", value, units, SMALL)
            self.assertEqual(status, "exact", units)
            self.assertAlmostEqual(nm, expected, places=6, msg=units)
            self.assertEqual(conv["kind"], "concentration")
            self.assertEqual(conv["verified"], 1)

    def test_explicit_power_of_ten_prefix_is_accepted(self):
        nm, status, _ = self.a.normalise("=", 1.5, "10^3nM", SMALL)
        self.assertEqual((nm, status), (1500.0, "exact"))

    def test_apostrophe_exponent_notation_is_never_guessed(self):
        nm, status, conv = self.a.normalise("=", 1.5, "10'-6M", SMALL)
        self.assertIsNone(nm)
        self.assertEqual(status, "unresolved")
        self.assertIn("not dimensionally resolvable", conv["note"])

    def test_mass_conversion_uses_the_measured_record_not_the_parent(self):
        measured = {"chembl_id": "CHEMBL_SALT", "molecule_type": "Small molecule",
                    "full_mwt": 400.0, "has_structure": 1}
        nm, status, conv = self.a.normalise("=", 1.0, "ug.mL-1", measured)
        self.assertEqual(status, "conditional")
        self.assertAlmostEqual(nm, 1.0 * 1e6 / 400.0)
        self.assertEqual(conv["mwt"], 400.0)
        self.assertEqual(conv["form"], "CHEMBL_SALT")
        self.assertIn("not the\nparent freebase".replace("\n", " "), conv["basis"])
        self.assertEqual(conv["verified"], 0)

    def test_a_conditional_value_is_not_exact(self):
        _, status, _ = self.a.normalise("=", 1.0, "ng/ml", SMALL)
        self.assertEqual(status, "conditional")

    def test_mass_rules_are_not_applied_to_a_biologic_or_a_missing_weight(self):
        protein = {"chembl_id": "CHEMBL_P", "molecule_type": "Protein",
                   "full_mwt": 50000.0, "has_structure": 1}
        _, status, conv = self.a.normalise("=", 1.0, "ug.mL-1", protein)
        self.assertEqual(status, "unresolved")
        self.assertIn("small-molecule mass", conv["note"])

        noweight = {"chembl_id": "CHEMBL_N", "molecule_type": "Small molecule",
                    "full_mwt": None, "has_structure": 1}
        _, status, conv = self.a.normalise("=", 1.0, "ug.mL-1", noweight)
        self.assertEqual(status, "unresolved")
        self.assertIn("molecular weight", conv["note"])

    def test_every_bound_relation_is_preserved_and_kept_out_of_exact_values(self):
        for rel in (">", "<", ">=", "<=", ">>", "~"):
            nm, status, conv = self.a.normalise(rel, 100.0, "nM", SMALL)
            self.assertEqual(status, "bound", rel)
            self.assertEqual(nm, 100.0)
            self.assertIn(rel, conv["note"])

    def test_a_bound_in_another_unit_is_not_converted(self):
        # Conversion requires an exact relation: rescaling a censored bound
        # does not turn it into a measurement.
        nm, status, _ = self.a.normalise(">", 5.0, "uM", SMALL)
        self.assertEqual(status, "bound")
        self.assertIsNone(nm)

    def test_a_null_value_is_unresolved_not_zero(self):
        nm, status, _ = self.a.normalise("=", None, "nM", SMALL)
        self.assertIsNone(nm)
        self.assertEqual(status, "unresolved")


class AssignmentTest(unittest.TestCase):

    def setUp(self):
        self.a = assessor()

    def target(self, ttype="SINGLE PROTEIN", tax=9606):
        return {"target_type": ttype, "tax_id": tax, "organism": "Homo sapiens",
                "chembl_id": "CHEMBL_T", "claimable": ttype in targets_mod.CLAIMABLE}

    def test_the_three_direct_human_combinations(self):
        cases = [("SINGLE PROTEIN", 9, "human_single_protein"),
                 ("PROTEIN COMPLEX", 7, "human_complex"),
                 ("PROTEIN COMPLEX GROUP", 7, "human_complex"),
                 ("PROTEIN FAMILY", 5, "human_family")]
        for ttype, conf, expected in cases:
            basis, cls, _ = self.a.assignment(self.target(ttype), conf, "D", None)
            self.assertEqual((basis, cls), ("human_direct", expected), ttype)

    def test_a_generic_confidence_seven_test_is_not_used(self):
        # 9, 7 and 8 are three different assignment categories, not a ranking.
        # A single protein at 7, or a complex at 9, is not the combination the
        # policy names, and a homologous 8 is never direct.
        basis, cls, _ = self.a.assignment(self.target("SINGLE PROTEIN"), 7, "D", None)
        self.assertEqual(basis, "broader")
        self.assertEqual(cls, "ambiguous_assignment")
        basis, _, _ = self.a.assignment(self.target("SINGLE PROTEIN"), 8, "D", None)
        self.assertEqual(basis, "broader")

    def test_the_direct_and_no_variant_requirements_apply_to_complexes_too(self):
        # The analysis this was derived from applied relationship_type = 'D'
        # and variant_id IS NULL only to the single-protein branch, so 109
        # variant-carrying human complex assays would have counted as direct
        # no-variant evidence.
        basis, cls, _ = self.a.assignment(self.target("PROTEIN COMPLEX"), 7, "D", 42)
        self.assertEqual((basis, cls), ("broader", "human_variant"))
        basis, cls, _ = self.a.assignment(self.target("PROTEIN COMPLEX"), 7, "H", None)
        self.assertEqual((basis, cls), ("broader", "homologous"))

    def test_the_same_applies_to_families(self):
        basis, cls, _ = self.a.assignment(self.target("PROTEIN FAMILY"), 5, "D", 7)
        self.assertEqual((basis, cls), ("broader", "human_variant"))

    def test_a_nonhuman_target_is_broader_not_absent(self):
        basis, cls, _ = self.a.assignment(self.target(tax=10090), 9, "D", None)
        self.assertEqual((basis, cls), ("broader", "nonhuman"))

    def test_unassigned_and_non_molecular_observations_back_no_claim(self):
        for ttype in ("ORGANISM", "CELL-LINE", "PROTEIN-PROTEIN INTERACTION",
                      "SELECTIVITY GROUP", "NO TARGET ASSIGNED"):
            basis, cls, _ = self.a.assignment(self.target(ttype), 9, "D", None)
            self.assertIsNone(basis, ttype)
            self.assertEqual(cls, "unassigned_or_non_molecular")

        for conf in (0, 1, 2, 3):
            basis, _, _ = self.a.assignment(self.target(), conf, "D", None)
            self.assertIsNone(basis, conf)
        for rel in ("N", "S", "M", "U"):
            basis, _, _ = self.a.assignment(self.target(), 9, rel, None)
            self.assertIsNone(basis, rel)

    def test_a_missing_target_record_backs_no_claim(self):
        basis, cls, _ = self.a.assignment(None, 9, "D", None)
        self.assertIsNone(basis)
        self.assertEqual(cls, "unassigned_or_non_molecular")


class StudyIdentityTest(unittest.TestCase):

    def setUp(self):
        self.a = assessor()

    def test_a_publication_resolves_by_pmid_then_doi(self):
        self.assertEqual(self.a.study(111, None, None, "CHEMBL_D", "PUBLICATION"),
                         ("pmid:111", "publication"))
        self.assertEqual(self.a.study(None, "10.1/x", None, "CHEMBL_D", "PUBLICATION"),
                         ("doi:10.1/x", "publication"))

    def test_a_patent_carrying_a_pmid_stays_a_patent(self):
        # The analysis classified on the identifier first, so a PATENT document
        # with a pubmed_id came back labelled a deposited dataset.
        self.assertEqual(self.a.study(111, None, "US123", "CHEMBL_D", "PATENT"),
                         ("patent:US123", "patent"))

    def test_a_bulk_deposit_is_one_study_however_many_rows(self):
        key, cls = self.a.study(None, None, None, "CHEMBL1201862", "DATASET")
        self.assertEqual((key, cls), ("doc:CHEMBL1201862", "deposited_dataset"))

    def test_an_unidentifiable_document_is_unresolved(self):
        self.assertEqual(self.a.study(None, None, None, None, None), (None, "unresolved"))


def obs(**over):
    row = {"activity_id": over.pop("activity_id", 1), "parent_molregno": 1,
           "target_chembl_id": "CHEMBL_T", "role": "binding",
           "endpoint_class": "binding:Ki", "value_status": "exact", "value_nm": 10.0,
           "study_key": "pmid:1", "provenance_class": "publication",
           "basis": "human_direct", "assignment_class": "human_single_protein",
           "pubmed_id": 1, "doi": None, "patent_id": None, "doc_chembl_id": None,
           "doc_year": 2020, "doc_journal": "J", "doc_title": "T", "counted": 0}
    row.update(over)
    return row


class ClaimAggregationTest(unittest.TestCase):

    def setUp(self):
        self.pol = common.load_policy("cohort1_evidence.json")

    def aggregate(self, rows, curated=()):
        return evidence.aggregate_claims(rows, list(curated), self.pol)

    def key(self, role="binding", basis="human_direct"):
        return (1, "CHEMBL_T", role, basis)

    def test_twenty_rows_from_one_paper_are_one_study(self):
        rows = [obs(activity_id=i, study_key="pmid:7", pubmed_id=7) for i in range(20)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["n_measurements"], 20)
        self.assertEqual(claim["n_studies"], 1)
        self.assertEqual(claim["tier"], "preliminary")
        self.assertEqual(claim["tier_reason"], "one_publication")

    def test_two_publications_in_one_endpoint_class_are_supported(self):
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "supported")
        self.assertEqual(claim["tier_reason"], "multiple_study_support")
        self.assertEqual(claim["supporting_endpoint_class"], "binding:Ki")

    def test_publications_split_across_endpoint_classes_are_not_replication(self):
        # Two papers, but one measured Ki and the other IC50. Replication is
        # counted inside one endpoint class only, so this is Preliminary and
        # says which case it is.
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1,
                    endpoint_class="binding:Ki"),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2,
                    endpoint_class="binding:IC50")]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "preliminary")
        self.assertEqual(claim["tier_reason"],
                         "multiple_publications_split_across_endpoint_classes")

    def test_a_paper_reporting_only_a_bound_is_not_a_second_publication(self):
        # Caffeine at human ADORA1, homologous assignment: one paper's Ki, a
        # second paper's AC50 > 30 uM and a DrugMatrix row with no value. One
        # paper holds an exact value, so the reason says one publication, not
        # several split across endpoint classes.
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2,
                    endpoint_class="binding:AC50", value_status="bound", value_nm=None),
                obs(activity_id=3, study_key="doc:D", provenance_class="deposited_dataset",
                    pubmed_id=None, value_status="unresolved", value_nm=None)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "preliminary")
        self.assertEqual(claim["tier_reason"], "one_publication")
        self.assertEqual(claim["n_publications"], 2)   # both papers are still listed

    def test_reason_names_where_the_exact_values_come_from(self):
        # A paper with only a bound does not make deposited values "one publication".
        rows = [obs(activity_id=1, study_key="doc:D", provenance_class="deposited_dataset",
                    pubmed_id=None),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2,
                    value_status="bound", value_nm=None)]
        self.assertEqual(self.aggregate(rows)[self.key()]["tier_reason"],
                         "deposited_datasets_only")

        rows = [obs(activity_id=1, study_key="doc:D", provenance_class="deposited_dataset",
                    pubmed_id=None),
                obs(activity_id=2, study_key="patent:A", provenance_class="patent",
                    pubmed_id=None, patent_id="A")]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "preliminary")
        self.assertEqual(claim["tier_reason"], "patents_and_deposits_only")

    def test_an_untraceable_document_alone_is_not_preliminary(self):
        # The policy's Preliminary needs an identifiable study with an exact
        # value; a document with no PubMed id, DOI or patent is not one, even
        # beside a paper that reported only a bound.
        rows = [obs(activity_id=1, study_key="doc:X", provenance_class="unresolved",
                    pubmed_id=None),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2,
                    value_status="bound", value_nm=None)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "limited_or_unresolved")
        self.assertEqual(claim["tier_reason"], "unresolved_study_provenance")

    def test_patents_and_deposits_never_create_multiple_study_support(self):
        rows = [obs(activity_id=1, study_key="patent:A", provenance_class="patent",
                    pubmed_id=None, patent_id="A"),
                obs(activity_id=2, study_key="patent:B", provenance_class="patent",
                    pubmed_id=None, patent_id="B")]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "preliminary")
        self.assertEqual(claim["tier_reason"], "patents_only")
        self.assertEqual(claim["multiple_study_support"], 0)

        rows = [obs(activity_id=i, study_key="doc:D%d" % i,
                    provenance_class="deposited_dataset", pubmed_id=None)
                for i in (1, 2)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier_reason"], "deposited_datasets_only")

    def test_bounds_alone_never_reach_a_tier(self):
        rows = [obs(activity_id=i, value_status="bound", value_nm=None,
                    study_key="pmid:%d" % i, pubmed_id=i) for i in (1, 2)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "limited_or_unresolved")
        self.assertEqual(claim["tier_reason"], "censored_only")
        self.assertEqual(claim["n_bounds"], 2)
        self.assertEqual(claim["n_measurements"], 0)

    def test_conditional_conversions_alone_never_reach_a_tier(self):
        rows = [obs(activity_id=i, value_status="conditional", value_nm=500.0,
                    study_key="pmid:%d" % i, pubmed_id=i) for i in (1, 2)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "limited_or_unresolved")
        self.assertEqual(claim["tier_reason"], "conditional_conversion_only")
        self.assertEqual(claim["n_conditional"], 2)
        # And they are not in the median either.
        self.assertEqual(claim["endpoints"]["binding:Ki"]["n_measurements"], 0)

    def test_only_exact_rows_are_marked_counted(self):
        rows = [obs(activity_id=1),
                obs(activity_id=2, value_status="bound", value_nm=None),
                obs(activity_id=3, value_status="conditional", value_nm=7.0),
                obs(activity_id=4, value_status="unresolved", value_nm=None)]
        self.aggregate(rows)
        self.assertEqual([r["counted"] for r in rows], [1, 0, 0, 0])

    def test_the_median_reconciles_to_the_rows_counted_into_it(self):
        rows = [obs(activity_id=i, value_nm=v, study_key="pmid:%d" % i, pubmed_id=i)
                for i, v in enumerate([1.0, 10.0, 100.0], start=1)]
        claim = self.aggregate(rows)[self.key()]
        e = claim["endpoints"]["binding:Ki"]
        self.assertEqual(e["n_measurements"], 3)
        self.assertAlmostEqual(e["median_nm"], 10.0)       # log-space median
        self.assertEqual(e["n_measurements"],
                         sum(1 for r in rows if r["counted"] == 1))

    def test_binding_and_functional_are_separate_claims(self):
        rows = [obs(activity_id=1, role="binding", endpoint_class="binding:Ki"),
                obs(activity_id=2, role="functional", endpoint_class="functional:EC50")]
        claims = self.aggregate(rows)
        self.assertIn(self.key("binding"), claims)
        self.assertIn(self.key("functional"), claims)

    def test_the_two_bases_never_pool(self):
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2, basis="broader",
                    assignment_class="nonhuman")]
        claims = self.aggregate(rows)
        direct = claims[self.key(basis="human_direct")]
        broader = claims[self.key(basis="broader")]
        # One publication each: pooling them would have manufactured replication
        # for a claim neither basis supports on its own.
        self.assertEqual(direct["tier"], "preliminary")
        self.assertEqual(broader["tier"], "preliminary")

    def test_a_hundredfold_disagreement_is_flagged_without_changing_the_tier(self):
        rows = [obs(activity_id=1, value_nm=0.01, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, value_nm=1000.0, study_key="pmid:2", pubmed_id=2)]
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["tier"], "supported")
        self.assertEqual(claim["conflict_dispersion"], 1)
        self.assertIn("fold", claim["conflict_detail"])

    def test_upstream_flags_do_not_drop_a_row(self):
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2)]
        rows[0]["data_validity_comment"] = "Outside typical range"
        rows[1]["potential_duplicate"] = 1
        claim = self.aggregate(rows)[self.key()]
        self.assertEqual(claim["n_measurements"], 2)
        self.assertEqual(claim["tier"], "supported")


def mech(**over):
    row = {"mec_id": 1, "parent_molregno": 1, "measured_molregno": 1,
           "target_chembl_id": "CHEMBL_T", "source_target_chembl_id": "CHEMBL_T",
           "target_type": "SINGLE PROTEIN", "target_tax_id": 9606,
           "action_type": "ANTAGONIST", "action_parent_type": "NEGATIVE MODULATOR",
           "mechanism_of_action": "Receptor antagonist", "direct_interaction": 1,
           "molecular_mechanism": 1, "mechanism_comment": None,
           "selectivity_comment": None, "variant_id": None, "n_refs": 1,
           "refs": [{"ref_type": "PubMed", "ref_id": "1", "ref_url": "u"}],
           "tier": "supported", "tier_reason": "curated_support"}
    row.update(over)
    return row


class CuratedTest(unittest.TestCase):

    def setUp(self):
        self.pol = common.load_policy("cohort1_evidence.json")

    def test_curated_support_does_not_upgrade_a_measured_claim(self):
        rows = [obs(activity_id=1)]
        claims = evidence.aggregate_claims(rows, [mech()], self.pol)
        binding = claims[(1, "CHEMBL_T", "binding", "human_direct")]
        curated = claims[(1, "CHEMBL_T", "curated", "human_direct")]
        self.assertEqual(binding["tier"], "preliminary")
        self.assertEqual(binding["curated_support"], 0)
        self.assertEqual(curated["tier"], "supported")
        self.assertEqual(curated["curated_support"], 1)

    def test_experimental_support_does_not_establish_an_action(self):
        rows = [obs(activity_id=1, study_key="pmid:1", pubmed_id=1),
                obs(activity_id=2, study_key="pmid:2", pubmed_id=2)]
        claims = evidence.aggregate_claims(rows, [], self.pol)
        binding = claims[(1, "CHEMBL_T", "binding", "human_direct")]
        self.assertEqual(binding["tier"], "supported")
        self.assertIsNone(binding["action_type"])
        self.assertNotIn((1, "CHEMBL_T", "curated", "human_direct"), claims)

    def test_opposing_curated_directions_are_both_kept_and_flagged(self):
        claims = evidence.aggregate_claims([], [
            mech(mec_id=1, action_type="AGONIST", action_parent_type="POSITIVE MODULATOR"),
            mech(mec_id=2, action_type="ANTAGONIST",
                 action_parent_type="NEGATIVE MODULATOR")], self.pol)
        curated = claims[(1, "CHEMBL_T", "curated", "human_direct")]
        self.assertEqual(curated["conflict_action"], 1)
        self.assertIn("AGONIST", curated["action_type"])
        self.assertIn("ANTAGONIST", curated["action_type"])
        # A conflict never raises a tier, and never reads as agreement.
        self.assertEqual(curated["tier"], "supported")
        self.assertIn("opposing", curated["conflict_detail"])

    def test_a_variant_specific_mechanism_goes_to_the_broader_layer(self):
        claims = evidence.aggregate_claims([], [mech(variant_id=9)], self.pol)
        self.assertIn((1, "CHEMBL_T", "curated", "broader"), claims)
        self.assertNotIn((1, "CHEMBL_T", "curated", "human_direct"), claims)

    def test_a_family_mechanism_stays_at_the_family(self):
        claims = evidence.aggregate_claims(
            [], [mech(target_chembl_id="CHEMBL_FAMILY", target_type="PROTEIN FAMILY")],
            self.pol)
        self.assertEqual(list(claims), [(1, "CHEMBL_FAMILY", "curated", "human_direct")])

    def test_curated_basis_is_none_when_there_is_no_claimable_target(self):
        self.assertIsNone(evidence.curated_basis(mech(target_chembl_id=None)))


class MechanismActionExclusionTest(unittest.TestCase):
    """CHEMBL_MECHANISM_ACTION_EXCLUSIONS: a direction withheld, never rewritten."""

    EXCLUSIONS = {1161: {"mec_id": 1161, "action_type": "AGONIST",
                         "reason": "its cited label says antagonist"}}

    def setUp(self):
        self.pol = common.load_policy("cohort1_evidence.json")

    def alfuzosin(self, **over):
        row = dict(mec_id=1161, action_type="AGONIST",
                   action_parent_type="POSITIVE MODULATOR",
                   mechanism_of_action="Adrenergic receptor alpha-1 agonist",
                   target_chembl_id="CHEMBL_FAMILY", source_target_chembl_id="CHEMBL_FAMILY",
                   target_type="PROTEIN FAMILY")
        row.update(over)
        return mech(**row)

    def test_the_action_is_withheld_and_kept_verbatim_beside_the_reason(self):
        mechs = evidence.withhold_excluded_actions([self.alfuzosin(), mech(mec_id=2)],
                                                   self.EXCLUSIONS)
        self.assertIsNone(mechs[0]["action_type"])
        self.assertIsNone(mechs[0]["action_parent_type"])
        self.assertEqual(mechs[0]["excluded_action_type"], "AGONIST")
        self.assertEqual(mechs[0]["action_exclusion"], "its cited label says antagonist")
        # ChEMBL's sentence stays on the record; nothing is written in its place.
        self.assertEqual(mechs[0]["mechanism_of_action"], "Adrenergic receptor alpha-1 agonist")
        # The tier is the curator's claim that it acts there, which is not disputed.
        self.assertEqual(mechs[0]["tier"], "supported")
        self.assertEqual(mechs[1]["action_type"], "ANTAGONIST")
        self.assertNotIn("excluded_action_type", mechs[1])

    def test_a_record_chembl_has_changed_stops_the_build(self):
        with self.assertRaisesRegex(ValueError, "now reads 'ANTAGONIST'"):
            evidence.withhold_excluded_actions(
                [self.alfuzosin(action_type="ANTAGONIST")], self.EXCLUSIONS)

    def test_an_entry_matching_nothing_stops_the_build(self):
        with self.assertRaisesRegex(ValueError, "matched no curated mechanism"):
            evidence.withhold_excluded_actions([mech(mec_id=2)], self.EXCLUSIONS)

    def test_the_claim_keeps_curated_support_and_says_why_it_has_no_direction(self):
        mechs = evidence.withhold_excluded_actions([self.alfuzosin()], self.EXCLUSIONS)
        claims = evidence.aggregate_claims([], mechs, self.pol)
        claim = claims[(1, "CHEMBL_FAMILY", "curated", "human_direct")]
        self.assertEqual(claim["tier"], "supported")
        self.assertEqual(claim["curated_support"], 1)
        self.assertIsNone(claim["action_type"])
        # The sentence names the withheld direction, so it goes with it.
        self.assertIsNone(claim["mechanism_of_action"])
        self.assertIn("AGONIST", claim["action_exclusion"])
        self.assertIn("Adrenergic receptor alpha-1 agonist", claim["action_exclusion"])
        self.assertIn("its cited label says antagonist", claim["action_exclusion"])
        self.assertEqual(claim["conflict_action"], 0)

    def test_an_unexcluded_claim_carries_no_exclusion(self):
        claims = evidence.aggregate_claims([], [mech()], self.pol)
        self.assertIsNone(claims[(1, "CHEMBL_T", "curated", "human_direct")]["action_exclusion"])

    def test_every_policy_entry_names_an_action_and_a_reason(self):
        entries = evidence.Assessor(self.pol).mechanism_action_exclusions
        self.assertIn(1161, entries)
        for e in entries.values():
            self.assertTrue(e["action_type"])
            self.assertTrue(e["reason"].strip())

    def test_every_policy_entry_still_matches_the_pinned_release(self):
        # The build makes the same check; this one runs without building, so a
        # ChEMBL release that corrects the record is noticed by the suite too.
        if not common.CHEMBL_DB.exists():
            self.skipTest("ChEMBL 37 bulk release not present")
        conn = sqlite3.connect(f"file:{common.CHEMBL_DB}?mode=ro", uri=True)
        try:
            for mec_id, e in evidence.Assessor(self.pol).mechanism_action_exclusions.items():
                row = conn.execute("SELECT action_type FROM drug_mechanism WHERE mec_id = ?",
                                   (mec_id,)).fetchone()
                self.assertEqual(row, (e["action_type"],), mec_id)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# The activity scan: gates, exclusions and accounting
# ---------------------------------------------------------------------------

class ScanTest(unittest.TestCase):

    def setUp(self):
        self.conn = fake_chembl()
        self.conn.executescript(
            "CREATE TEMP TABLE cohort_members(molregno INTEGER PRIMARY KEY);"
            "INSERT INTO cohort_members VALUES(1);")
        add_molecule(self.conn, 1, "CHEMBL_M", "M")
        self.conn.execute(
            "INSERT INTO target_dictionary(tid, chembl_id, pref_name, target_type,"
            " organism, tax_id) VALUES(1,'CHEMBL_T','T','SINGLE PROTEIN','Homo sapiens',9606)")
        self.conn.execute(
            "INSERT INTO bioassay_ontology(bao_id, label) VALUES"
            " ('BAO_ORG','organism-based format'),('BAO_SP','single protein format')")
        self.conn.execute(
            "INSERT INTO docs(doc_id, chembl_id, pubmed_id, doc_type) "
            "VALUES(1,'CHEMBL_DOC',5,'PUBLICATION')")
        self.a = assessor()
        self.targets = targets_mod.load(self.conn)
        self.measured = evidence.measured_records(self.conn, {1})

    def assay(self, assay_id, chembl_id, assay_type="B", bao="BAO_SP", conf=9,
              rel="D", tid=1):
        self.conn.execute(
            "INSERT INTO assays(assay_id, chembl_id, description, assay_type,"
            " confidence_score, relationship_type, variant_id, tid, bao_format)"
            " VALUES(?,?,?,?,?,?,NULL,?,?)",
            (assay_id, chembl_id, "desc", assay_type, conf, rel, tid, bao))

    def activity(self, activity_id, assay_id, stype="Ki", rel="=", value=10.0,
                 units="nM"):
        self.conn.execute(
            "INSERT INTO activities(activity_id, molregno, assay_id, doc_id,"
            " standard_type, standard_relation, standard_value, standard_units)"
            " VALUES(?,1,?,1,?,?,?,?)",
            (activity_id, assay_id, stype, rel, value, units))

    def scan(self):
        kept = []
        counts, known_bad = evidence.scan_activities(
            self.conn, self.a, {1: 1}, self.targets, self.measured, kept.append)
        return kept, counts, known_bad

    def test_organism_format_rows_are_excluded_in_every_assay_type(self):
        # The analysis applied this gate only to assay_type 'F'. chembl_37 also
        # carries organism-format assays typed 'B', which that gate let through
        # as binding evidence.
        self.assay(1, "CHEMBL_A1", assay_type="F", bao="BAO_ORG")
        self.assay(2, "CHEMBL_A2", assay_type="B", bao="BAO_ORG")
        self.assay(3, "CHEMBL_A3", assay_type="B", bao="BAO_SP")
        for i, a in enumerate([1, 2, 3], start=1):
            self.activity(i, a)
        kept, counts, _ = self.scan()
        self.assertEqual(counts["organism_based_format"], 2)
        self.assertEqual(counts["organism_based_format_B"], 1)
        self.assertEqual(counts["organism_based_format_F"], 1)
        self.assertEqual([r["assay_chembl_id"] for r in kept], ["CHEMBL_A3"])

    def test_known_bad_records_are_excluded_and_individually_retained(self):
        self.assay(1, "CHEMBL5133661")
        self.activity(1, 1)
        kept, counts, known_bad = self.scan()
        self.assertEqual(kept, [])
        self.assertEqual(counts["documented_exclusion"], 1)
        self.assertEqual(len(known_bad), 1)
        self.assertEqual(known_bad[0]["reason"], "documented_exclusion")

    def test_an_unassigned_observation_is_kept_but_backs_no_claim(self):
        self.conn.execute(
            "INSERT INTO target_dictionary(tid, chembl_id, pref_name, target_type,"
            " organism, tax_id) VALUES(2,'CHEMBL_ORG','Rat','ORGANISM','Rattus',10116)")
        self.targets = targets_mod.load(self.conn)
        self.assay(1, "CHEMBL_A1", tid=2)
        self.activity(1, 1)
        kept, counts, _ = self.scan()
        self.assertEqual(len(kept), 1)
        self.assertIsNone(kept[0]["basis"])
        self.assertIsNone(kept[0]["target_chembl_id"] and kept[0]["basis"])
        self.assertEqual(counts["no_claimable_assignment"], 1)
        self.assertIn("not one of the four claimable", kept[0]["exclusion_reason"])

    def test_the_scan_accounts_for_every_row_it_read(self):
        self.assay(1, "CHEMBL_A1")
        self.assay(2, "CHEMBL_A2", assay_type="A")            # not B or F
        self.assay(3, "CHEMBL_A3", assay_type="F", bao="BAO_ORG")
        self.activity(1, 1)
        self.activity(2, 2)
        self.activity(3, 3)
        self.activity(4, 1, stype="Solubility")               # out-of-scope endpoint
        _, counts, _ = self.scan()
        accounted = (counts["assay_type_not_B_or_F"] + counts["standard_type_out_of_scope"]
                     + counts["organism_based_format"] + counts["documented_exclusion"]
                     + counts["kept_exact"] + counts["kept_bound"]
                     + counts["kept_conditional"] + counts["kept_unresolved"])
        self.assertEqual(counts["scanned"], 4)
        self.assertEqual(accounted, 4)


class TargetIdentityTest(unittest.TestCase):

    def test_only_the_four_adopted_identities_are_claimable(self):
        conn = fake_chembl()
        rows = [(1, "CHEMBL_SP", "SINGLE PROTEIN"), (2, "CHEMBL_PC", "PROTEIN COMPLEX"),
                (3, "CHEMBL_CG", "PROTEIN COMPLEX GROUP"), (4, "CHEMBL_PF", "PROTEIN FAMILY"),
                (5, "CHEMBL_PPI", "PROTEIN-PROTEIN INTERACTION"),
                (6, "CHEMBL_SG", "SELECTIVITY GROUP"), (7, "CHEMBL_CL", "CELL-LINE")]
        for tid, cid, ttype in rows:
            conn.execute("INSERT INTO target_dictionary(tid, chembl_id, pref_name,"
                         " target_type, organism, tax_id) VALUES(?,?,?,?,?,9606)",
                         (tid, cid, cid, ttype, "Homo sapiens"))
        index = targets_mod.load(conn)
        self.assertEqual(sorted(t["chembl_id"] for t in index.values() if t["claimable"]),
                         ["CHEMBL_CG", "CHEMBL_PC", "CHEMBL_PF", "CHEMBL_SP"])

    def test_components_are_loaded_as_context(self):
        conn = fake_chembl()
        conn.execute("INSERT INTO target_dictionary(tid, chembl_id, pref_name,"
                     " target_type, organism, tax_id)"
                     " VALUES(1,'CHEMBL_PC','Complex','PROTEIN COMPLEX','Homo sapiens',9606)")
        for cid, acc in [(1, "P1"), (2, "P2")]:
            conn.execute("INSERT INTO component_sequences(component_id, accession,"
                         " description, component_type) VALUES(?,?,?,'PROTEIN')",
                         (cid, acc, "sub " + acc))
            conn.execute("INSERT INTO target_components(tid, component_id) VALUES(1,?)",
                         (cid,))
        index = targets_mod.load(conn)
        t = index[1]
        self.assertEqual(t["n_components"], 2)
        self.assertEqual([c["accession"] for c in t["components"]], ["P1", "P2"])

    def test_protein_class_is_read_at_levels_one_and_two(self):
        # What the viewer reads to decide which complexes are ion-channel
        # assemblies. Level 3 and below are left off, and a component filed
        # under two classes carries both.
        conn = fake_chembl()
        for row in [(1, None, "Protein class", 0), (2, 1, "Ion channel", 1),
                    (3, 2, "Ligand-gated ion channel", 2), (4, 3, "GABA-A receptor", 3),
                    (5, 1, "Auxiliary transport protein", 1),
                    (6, 5, "Calcium channel auxiliary subunit beta family", 2)]:
            conn.execute("INSERT INTO protein_classification(protein_class_id,"
                         " parent_id, pref_name, class_level) VALUES(?,?,?,?)", row)
        for cid, acc in [(1, "P1"), (2, "P2"), (3, "P3")]:
            conn.execute("INSERT INTO component_sequences(component_id, accession,"
                         " description, component_type) VALUES(?,?,?,'PROTEIN')",
                         (cid, acc, acc))
        conn.executemany("INSERT INTO component_class(component_id, protein_class_id)"
                         " VALUES(?,?)", [(1, 4), (2, 6), (2, 3)])
        out = targets_mod.protein_classes(conn, {"P1", "P2", "P3"})
        self.assertEqual(out["P1"], "Ion channel > Ligand-gated ion channel")
        self.assertEqual(out["P2"], "Auxiliary transport protein > Calcium channel "
                                    "auxiliary subunit beta family|Ion channel > "
                                    "Ligand-gated ion channel")
        self.assertNotIn("P3", out, "an unclassified component carries nothing")

    def test_the_protein_class_backfill_migrates_and_is_idempotent(self):
        # db/cohort1.db predates the column, and a rebuild would wipe the two
        # network backfills; the script adds it and fills it from the release.
        import resolve_cohort_protein_class as backfill_mod
        chembl = fake_chembl()
        chembl.executemany("INSERT INTO protein_classification(protein_class_id,"
                           " parent_id, pref_name, class_level) VALUES(?,?,?,?)",
                           [(1, None, "Protein class", 0), (2, 1, "Ion channel", 1),
                            (3, 2, "Ligand-gated ion channel", 2)])
        chembl.execute("INSERT INTO component_sequences(component_id, accession,"
                       " description, component_type) VALUES(1,'P1','x','PROTEIN')")
        chembl.execute("INSERT INTO component_class(component_id, protein_class_id)"
                       " VALUES(1,3)")
        cohort = sqlite3.connect(":memory:")
        cohort.execute("CREATE TABLE target_components (target_chembl_id TEXT,"
                       " accession TEXT, description TEXT, gene_symbol TEXT)")
        cohort.executemany("INSERT INTO target_components VALUES(?,?,?,?)",
                           [("T1", "P1", None, "A"), ("T2", "P1", None, "A"),
                            ("T2", "P9", None, "Z")])
        first = backfill_mod.backfill(cohort, chembl)
        self.assertTrue(first["column_added"])
        self.assertEqual(first["rows_changed"], 2)
        self.assertEqual(dict(cohort.execute(
            "SELECT target_chembl_id || accession, protein_class FROM target_components")),
            {"T1P1": "Ion channel > Ligand-gated ion channel",
             "T2P1": "Ion channel > Ligand-gated ion channel", "T2P9": None})
        again = backfill_mod.backfill(cohort, chembl)
        self.assertFalse(again["column_added"])
        self.assertEqual(again["rows_changed"], 0)

    def test_the_approved_elsewhere_backfill_matches_the_build_and_is_idempotent(self):
        # db/cohort1.db predates the column, and a rebuild would wipe the
        # network backfills. Scope comes from the database's own
        # indication_scope and families from molecule_forms.
        import resolve_cohort_approved_elsewhere as backfill_mod
        chembl = fake_chembl()
        add_indication(chembl, 1, 10, "D_IN", 4.0, heading="Epilepsy")
        add_indication(chembl, 2, 11, "D_OUT", 4.0, heading="Anxiety")
        add_indication(chembl, 3, 10, "D_OUT2", 3.0, heading="Gout")
        cohort = sqlite3.connect(":memory:")
        cohort.execute("CREATE TABLE molecules (parent_molregno INTEGER)")
        cohort.execute("CREATE TABLE molecule_forms (parent_molregno INTEGER, molregno INTEGER)")
        cohort.execute("CREATE TABLE indication_scope (mesh_id TEXT, in_scope INTEGER)")
        cohort.executemany("INSERT INTO molecules VALUES(?)", [(10,), (20,)])
        cohort.executemany("INSERT INTO molecule_forms VALUES(?,?)", [(10, 10), (10, 11)])
        cohort.executemany("INSERT INTO indication_scope VALUES(?,?)",
                           [("D_IN", 1), ("D_OUT", 0), ("D_OUT2", 0)])
        status = labels_mod.LabelStatus(chembl, cfg=empty_label_status())
        first = backfill_mod.backfill(cohort, chembl, status)
        self.assertTrue(first["column_added"])
        self.assertEqual(dict(cohort.execute(
            "SELECT parent_molregno, approved_elsewhere FROM molecules")),
            {10: "Anxiety", 20: None})
        again = backfill_mod.backfill(cohort, chembl, status)
        self.assertFalse(again["column_added"])
        self.assertEqual(again["rows_changed"], 0)

    def test_a_family_claim_is_not_expanded_into_its_members(self):
        # The failure this guards against: 477 curated family and complex
        # claims would have become 3,146 by expansion, inventing 2,669
        # "supported" claims about individual proteins that nothing measured.
        pol = common.load_policy("cohort1_evidence.json")
        claims = evidence.aggregate_claims(
            [obs(target_chembl_id="CHEMBL_FAMILY")],
            [mech(target_chembl_id="CHEMBL_FAMILY", target_type="PROTEIN FAMILY")], pol)
        self.assertEqual({k[1] for k in claims}, {"CHEMBL_FAMILY"})


# ---------------------------------------------------------------------------
# Drug classes: ATC codes and USAN/INN name stems
# ---------------------------------------------------------------------------

class ClassesTest(unittest.TestCase):

    def test_stem_pairs_splits_and_pairs_stems_with_their_substems(self):
        # A single stem, no substem: ChEMBL's commonest row shape.
        self.assertEqual(list(classes_mod.stem_pairs("-pramine", None)),
                         [("-pramine", "")])
        # Several stems, each with its own parenthesised subgroup, matched
        # positionally by "; ".
        self.assertEqual(
            list(classes_mod.stem_pairs("-mab; -mab",
                                        "-mab (-umab); -mab (-zumab)")),
            [("-mab", "-umab"), ("-mab", "-zumab")])
        # ChEMBL's "no stem" placeholder is a bare "-" and is not a class.
        self.assertEqual(list(classes_mod.stem_pairs("-", None)), [])
        # The stem and substem lists disagree in length (one substem for two
        # stems): the pairing is refused rather than risking a mismatch, and
        # the substems are dropped, not zipped onto the wrong stem.
        self.assertEqual(
            list(classes_mod.stem_pairs("-a; -b", "-a (-x)")),
            [("-a", ""), ("-b", "")])

    def test_collect_gathers_atc_from_any_anatomical_group_and_folds_salts(self):
        # aspirin's B01AC06 is not an N code, and the admission route's own
        # molecule_atc only keeps N; this table is broader on purpose.
        conn = fake_chembl()
        add_molecule(conn, 200, "CHEMBL200", "aspirin parent")
        add_molecule(conn, 201, "CHEMBL050", "aspirin salt", parent=200)
        conn.execute(
            "INSERT INTO atc_classification(level5, level4, level3, level2, level1,"
            " who_name, level1_description, level2_description, level3_description,"
            " level4_description) VALUES"
            " ('B01AC06','B01AC','B01A','B01','B','acetylsalicylic acid',"
            "  'BLOOD AND BLOOD FORMING ORGANS','ANTITHROMBOTIC AGENTS',"
            "  'PLATELET AGGREGATION INHIBITORS EXCL. HEPARIN',"
            "  'Platelet aggregation inhibitors excl. heparin')")
        conn.execute("INSERT INTO molecule_atc_classification(molregno, level5)"
                     " VALUES(200,'B01AC06')")
        conn.execute("INSERT INTO molecule_atc_classification(molregno, level5)"
                     " VALUES(201,'B01AC06')")

        form_to_parent = {200: 200, 201: 200}
        rows, label_rows = classes_mod.collect(conn, form_to_parent)

        self.assertEqual(rows, [
            (200, "atc", "B01AC06", "", "acetylsalicylic acid", "CHEMBL050|CHEMBL200"),
        ])
        self.assertEqual(sorted(r for r in label_rows if r[0] == "atc"), [
            ("atc", "B", 1, "BLOOD AND BLOOD FORMING ORGANS"),
            ("atc", "B01", 2, "ANTITHROMBOTIC AGENTS"),
            ("atc", "B01A", 3, "PLATELET AGGREGATION INHIBITORS EXCL. HEPARIN"),
            ("atc", "B01AC", 4, "Platelet aggregation inhibitors excl. heparin"),
        ])

    def test_collect_resolves_usan_stem_labels_and_subgroup_fallback(self):
        conn = fake_chembl()
        # A subgroup written "-oxetine (-tioxetine)": the parenthesised part
        # is the usan_stems subgroup, and the bare stem carries its own,
        # separate annotation.
        add_molecule(conn, 300, "CHEMBL300", "oxetine-class drug")
        conn.execute("UPDATE molecule_dictionary SET usan_stem = '-oxetine',"
                     " usan_substem = '-oxetine (-tioxetine)',"
                     " usan_stem_definition = 'unused when usan_stems answers'"
                     " WHERE molregno = 300")
        # A single-stem row whose stem usan_stems has never heard of: the
        # row's own definition is the only place a label can come from.
        add_molecule(conn, 301, "CHEMBL301", "orphan-stem drug")
        conn.execute("UPDATE molecule_dictionary SET usan_stem = '-zzznone',"
                     " usan_stem_definition = 'fallback def for zzznone'"
                     " WHERE molregno = 301")
        # A two-stem row where one stem is unknown to usan_stems: with more
        # than one stem on the row, an unknown one must not borrow the row's
        # definition, because it could belong to either stem.
        add_molecule(conn, 302, "CHEMBL302", "two-stem drug")
        conn.execute("UPDATE molecule_dictionary SET usan_stem = '-pramine; -zzzmissing',"
                     " usan_stem_definition = 'antidepressants (imipramine type); n/a'"
                     " WHERE molregno = 302")
        conn.executemany(
            "INSERT INTO usan_stems(stem, subgroup, annotation) VALUES(?,?,?)", [
                ("-oxetine", "-tioxetine", "antidepressants, tioxetine type"),
                ("-oxetine", "", "antidepressants (oxetine-type, general)"),
                ("-pramine", "", "antidepressants (imipramine type)"),
            ])

        form_to_parent = {300: 300, 301: 301, 302: 302}
        rows, label_rows = classes_mod.collect(conn, form_to_parent)

        usan_rows = {(p, c, g): lbl for p, s, c, g, lbl, carriers in rows if s == "usan"}
        self.assertEqual(usan_rows[(300, "-oxetine", "-tioxetine")],
                         "antidepressants, tioxetine type")
        self.assertEqual(usan_rows[(301, "-zzznone", "")],
                         "fallback def for zzznone")
        self.assertEqual(usan_rows[(302, "-pramine", "")],
                         "antidepressants (imipramine type)")
        self.assertIsNone(usan_rows[(302, "-zzzmissing", "")],
                          "a two-stem row's unmatched stem must not borrow the "
                          "row's definition")

        usan_labels = {c: lbl for s, c, lv, lbl in label_rows if s == "usan"}
        self.assertEqual(usan_labels["-oxetine"], "antidepressants (oxetine-type, general)")
        self.assertEqual(usan_labels["-pramine"], "antidepressants (imipramine type)")
        self.assertIsNone(usan_labels["-zzznone"],
                          "no usan_stems row at all for this stem's own annotation")
        self.assertIsNone(usan_labels["-zzzmissing"])


class ClassesBackfillTest(unittest.TestCase):
    """scripts/resolve_cohort_classes.py, on the pattern of the protein-class
    backfill above: it arrived after db/cohort1.db was built, so it must be
    able to create the two tables it needs rather than assume they exist.
    """

    def _cohort_with_one_molecule(self, conn):
        conn.execute("CREATE TABLE molecules (parent_molregno INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE molecule_forms (parent_molregno INTEGER, molregno INTEGER)")
        conn.execute("INSERT INTO molecules(parent_molregno) VALUES(400)")
        conn.execute("INSERT INTO molecule_forms(parent_molregno, molregno) VALUES(400, 400)")

    def _fake_chembl_with_one_class(self):
        chembl = fake_chembl()
        add_molecule(chembl, 400, "CHEMBL400", "some drug")
        add_atc(chembl, 400, "N06AA02", level1="N")
        return chembl

    def test_backfill_creates_tables_fills_them_and_is_idempotent(self):
        import resolve_cohort_classes as backfill_mod

        cohort = sqlite3.connect(":memory:")
        self._cohort_with_one_molecule(cohort)
        chembl = self._fake_chembl_with_one_class()

        first = backfill_mod.backfill(cohort, chembl)
        self.assertEqual(set(first["tables_created"]), {"molecule_classes", "class_labels"})
        self.assertEqual(first["rows"], 1)
        self.assertGreater(first["rows_changed"], 0)
        before = sorted(cohort.execute("SELECT * FROM molecule_classes"))
        self.assertEqual(before, [(400, "atc", "N06AA02", "", "who", "CHEMBL400")])

        again = backfill_mod.backfill(cohort, chembl)
        self.assertEqual(again["tables_created"], [])
        self.assertEqual(again["rows_changed"], 0)
        after = sorted(cohort.execute("SELECT * FROM molecule_classes"))
        self.assertEqual(after, before)

    def test_a_rolled_back_backfill_leaves_no_tables_behind(self):
        import resolve_cohort_classes as backfill_mod

        chembl = self._fake_chembl_with_one_class()
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        path = tmp.name
        try:
            setup = sqlite3.connect(path)
            self._cohort_with_one_molecule(setup)
            setup.commit()
            setup.close()

            # The same explicit-transaction dance resolve_cohort_classes.main()
            # uses for --dry-run: Python's sqlite3 commits a bare CREATE TABLE
            # on its own under the default isolation level, so a dry run has
            # to take manual control of the transaction to be undoable at all.
            conn = sqlite3.connect(path, isolation_level=None)
            conn.execute("BEGIN")
            backfill_mod.backfill(conn, chembl)
            conn.execute("ROLLBACK")
            conn.close()

            check = sqlite3.connect(path)
            tables = {r[0] for r in
                     check.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            check.close()
            self.assertNotIn("molecule_classes", tables)
            self.assertNotIn("class_labels", tables)
        finally:
            pathlib.Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Source scope
# ---------------------------------------------------------------------------

class SourceScopeTest(unittest.TestCase):

    def setUp(self):
        self.pol = common.load_policy("cohort1_evidence.json")

    def test_chembl_is_the_only_active_pharmacology_source(self):
        self.assertEqual(self.pol["source_scope"]["active_pharmacology"], ["chembl_37"])

    def test_deferred_sources_are_not_assessed_rather_than_negative(self):
        deferred = self.pol["source_scope"]["deferred"]
        self.assertEqual(deferred["status"], "not_assessed")
        for src in ("PDSP", "BindingDB", "DGIdb", "GtoPdb", "HPA"):
            self.assertIn(src, deferred["sources"])

    def test_the_potency_cutoff_no_longer_gates_import(self):
        # Invariant 8's 300 uM auto-discovery cutoff decided what reached the
        # database. A display filter cannot undo an import cutoff, so it moved.
        potency = self.pol["potency_filter"]
        self.assertEqual(potency["role"], "display_filter_only")
        self.assertIsNone(potency["default"])
        self.assertEqual(potency["presets_uM"], [1, 10, 100, 300])
        self.assertIn("Not used by this build",
                      potency["legacy_reconciliation"]["resolution"])

    def test_a_missing_pinned_release_fails_rather_than_falling_back(self):
        original = common.CHEMBL_DB
        try:
            common.CHEMBL_DB = pathlib.Path("/nonexistent/chembl.db")
            with self.assertRaises(common.PolicyError):
                common.chembl()
        finally:
            common.CHEMBL_DB = original


class ReasonVocabularyTest(unittest.TestCase):
    """Every tier_reason the build can write has a name on the page.

    The viewer grouped its retained-observations panel by the raw token -
    "invalid_units_only (1)" as a heading - which names a rule to a reader who
    already knows it and to nobody else. It now carries a label and an
    explanation per reason, and the failure mode of that map is silence: a new
    reason falls back to the token and the heading goes back to what it was,
    with nothing saying so. This holds the map to the source that writes them.
    """

    def _reasons_written_by_the_build(self):
        src = (pathlib.Path(__file__).resolve().parent.parent
               / "scripts" / "cohort" / "evidence.py").read_text(encoding="utf-8")
        # `tier, reason = "supported", "curated_support"` binds two names on one
        # line, so the tier vocabulary comes back with the reasons and is
        # dropped by name rather than by a cleverer pattern.
        tiers = {"supported", "preliminary", "limited_or_unresolved"}
        found = set(re.findall(r'reason = "([a-z_]+)"', src)) - tiers
        found |= set(re.findall(r'reason = \("([a-z_]+)"', src))
        found |= set(re.findall(r'tier, reason = "[a-z_]+", "([a-z_]+)"', src))
        found |= set(re.findall(r'\n\s+if len\(all_pub_studies\) >= 2 else "([a-z_]+)"', src))
        return found - tiers

    def test_every_reason_the_build_writes_is_named_by_the_viewer(self):
        reasons = self._reasons_written_by_the_build()
        # A regex that stopped matching would pass this vacuously, which is the
        # way a guard like this usually dies.
        self.assertGreaterEqual(len(reasons), 12, sorted(reasons))
        self.assertIn("invalid_units_only", reasons)
        self.assertIn("curated_support", reasons)

        page = (pathlib.Path(__file__).resolve().parent.parent
                / "viz" / "index.html").read_text(encoding="utf-8")
        block = re.search(r"const TIER_REASONS = \{(.*?)\n\};", page, re.S)
        self.assertIsNotNone(block, "TIER_REASONS is gone from viz/index.html")
        named = set(re.findall(r"^  ([a-z_]+): \{", block.group(1), re.M))
        self.assertEqual(reasons - named, set(),
                         "tier reasons the viewer cannot name: "
                         + ", ".join(sorted(reasons - named)))


if __name__ == "__main__":
    unittest.main()
