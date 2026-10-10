"""Tests for the local ChEMBL bulk-release backend.

Two layers, for two different failure modes.

The unit tests build a miniature ChEMBL schema in memory and run the real
queries against it. They run anywhere, with no 29GB download, and they lock
in the filters and the API-shaped output that load_molecule() depends on --
the things that would silently produce a *plausible but wrong* network if
they drifted (a target_organism join that quietly matched assay_organism, a
missing accession key, an assay_type filter that stopped filtering).

The integration tests only run when a real release is present. They assert
the two backends agree on a live molecule, which is the property the whole
port rests on and which no fixture can prove.

Run with: python3 -m unittest discover -s tests
"""

import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import build_db  # noqa: E402
import chembl_local  # noqa: E402


# Just the columns the backend actually reads. Deliberately not the real
# ChEMBL DDL: a fixture that had to track 72 tables would rot, and the point
# is to exercise the joins, not to re-declare EBI's schema.
FIXTURE_SCHEMA = """
CREATE TABLE molecule_dictionary (molregno INTEGER PRIMARY KEY, chembl_id TEXT, pref_name TEXT);
CREATE TABLE target_dictionary (tid INTEGER PRIMARY KEY, chembl_id TEXT, pref_name TEXT,
                                organism TEXT, target_type TEXT, tax_id INTEGER);
CREATE TABLE target_components (targcomp_id INTEGER PRIMARY KEY, tid INTEGER,
                                component_id INTEGER, homologue INTEGER);
CREATE TABLE component_sequences (component_id INTEGER PRIMARY KEY, accession TEXT,
                                  description TEXT, component_type TEXT, organism TEXT);
CREATE TABLE component_synonyms (compsyn_id INTEGER PRIMARY KEY, component_id INTEGER,
                                 component_synonym TEXT, syn_type TEXT);
CREATE TABLE bioassay_ontology (bao_id TEXT PRIMARY KEY, label TEXT);
CREATE TABLE docs (doc_id INTEGER PRIMARY KEY, chembl_id TEXT, title TEXT, journal TEXT,
                   year INTEGER, doi TEXT, pubmed_id INTEGER, volume TEXT, issue TEXT,
                   first_page TEXT, last_page TEXT, doc_type TEXT, authors TEXT, abstract TEXT);
CREATE TABLE assays (assay_id INTEGER PRIMARY KEY, chembl_id TEXT, doc_id INTEGER,
                     description TEXT, assay_type TEXT, assay_organism TEXT, tid INTEGER,
                     bao_format TEXT);
CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, assay_id INTEGER, doc_id INTEGER,
                         molregno INTEGER, standard_type TEXT, standard_relation TEXT,
                         standard_value NUMERIC, standard_units TEXT,
                         data_validity_comment TEXT, activity_comment TEXT,
                         pchembl_value NUMERIC);
CREATE TABLE drug_mechanism (mec_id INTEGER PRIMARY KEY, molregno INTEGER, tid INTEGER,
                             action_type TEXT, mechanism_of_action TEXT,
                             mechanism_comment TEXT, selectivity_comment TEXT,
                             direct_interaction INTEGER, molecular_mechanism INTEGER,
                             disease_efficacy INTEGER);
CREATE TABLE mechanism_refs (mecref_id INTEGER PRIMARY KEY, mec_id INTEGER, ref_type TEXT,
                             ref_id TEXT, ref_url TEXT);
"""


def build_fixture(path):
    """A deliberately awkward miniature ChEMBL.

    Two targets that differ *only* in organism, an assay whose assay_organism
    disagrees with its target's organism, one B and one F assay, a censored
    value, a non-nM value, and a target component with no accession -- i.e.
    one instance of each thing that has to be handled correctly."""
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE_SCHEMA)
    conn.executescript("""
    INSERT INTO molecule_dictionary VALUES (1, 'CHEMBL_TESTMOL', 'testmol');
    INSERT INTO molecule_dictionary VALUES (2, 'CHEMBL_OTHERMOL', 'othermol');

    -- Same protein, two species. Only the human one may ever be returned.
    INSERT INTO target_dictionary VALUES (10, 'CHEMBL_HUMAN', 'Test receptor',
                                          'Homo sapiens', 'SINGLE PROTEIN', 9606);
    INSERT INTO target_dictionary VALUES (11, 'CHEMBL_RAT', 'Test receptor',
                                          'Rattus norvegicus', 'SINGLE PROTEIN', 10116);

    INSERT INTO target_components VALUES (1, 10, 100, 0);
    INSERT INTO target_components VALUES (2, 10, 101, 0);   -- 2nd component, no accession
    INSERT INTO target_components VALUES (3, 11, 102, 0);
    INSERT INTO component_sequences VALUES (100, 'P00001', 'Test receptor',
                                            'PROTEIN', 'Homo sapiens');
    INSERT INTO component_sequences VALUES (101, NULL, 'Unsequenced subunit',
                                            'PROTEIN', 'Homo sapiens');
    INSERT INTO component_sequences VALUES (102, 'P00002', 'Test receptor',
                                            'PROTEIN', 'Rattus norvegicus');
    INSERT INTO component_synonyms VALUES (500, 100, 'Test receptor alpha', 'OTHER');
    INSERT INTO component_synonyms VALUES (501, 100, 'TSTR1', 'GENE_SYMBOL');
    INSERT INTO component_synonyms VALUES (502, 102, 'Tstr1', 'GENE_SYMBOL');

    INSERT INTO bioassay_ontology VALUES ('BAO_0000019', 'cell-based format');
    INSERT INTO bioassay_ontology VALUES ('BAO_0000218', 'organism-based format');
    INSERT INTO bioassay_ontology VALUES ('BAO_0000357', 'single protein format');

    INSERT INTO docs VALUES (1000, 'CHEMBL_DOC1', 'A paper about testmol', 'J Test Chem',
                             2011, '10.1000/test', 12345678, '1', '2', '3', '4',
                             'PUBLICATION', 'A Author', NULL);

    -- assay_organism is rat while the TARGET is human: a join on the wrong
    -- column would drop this row, which is exactly the bug being guarded.
    INSERT INTO assays VALUES (1, 'CHEMBL_ASSAY_B', 1000, 'Binding to human receptor',
                               'B', 'Rattus norvegicus', 10, 'BAO_0000357');
    INSERT INTO assays VALUES (2, 'CHEMBL_ASSAY_F', 1000, 'cAMP accumulation',
                               'F', 'Homo sapiens', 10, 'BAO_0000019');
    INSERT INTO assays VALUES (3, 'CHEMBL_ASSAY_RAT', 1000, 'Binding to rat receptor',
                               'B', 'Rattus norvegicus', 11, 'BAO_0000357');
    INSERT INTO assays VALUES (4, 'CHEMBL_ASSAY_ORG', 1000, 'Urine output in dosed rat',
                               'F', 'Homo sapiens', 10, 'BAO_0000218');

    INSERT INTO activities VALUES (1, 1, 1000, 1, 'Ki',   '=', 50.0,   'nM', NULL, NULL, 7.3);
    INSERT INTO activities VALUES (2, 1, 1000, 1, 'Ki',   '>', 30000.0,'nM', NULL,
                                   'largest value for relation >', NULL);
    INSERT INTO activities VALUES (3, 1, 1000, 1, 'IC50', '=', 0.5,    'uM', NULL, NULL, NULL);
    INSERT INTO activities VALUES (4, 2, 1000, 1, 'EC50', '=', 120.0,  'nM', NULL, NULL, NULL);
    INSERT INTO activities VALUES (5, 4, 1000, 1, 'EC50', '=', 900.0,  'nM', NULL, NULL, NULL);
    INSERT INTO activities VALUES (6, 3, 1000, 1, 'Ki',   '=', 22.0,   'nM', NULL, NULL, NULL);
    INSERT INTO activities VALUES (7, 2, 1000, 1, 'Potency','=', 5.0,  'nM', NULL, NULL, NULL);
    INSERT INTO activities VALUES (8, 1, 1000, 2, 'Ki',   '=', 11.0,   'nM', NULL, NULL, NULL);

    INSERT INTO drug_mechanism VALUES (1, 1, 10, 'ANTAGONIST', 'Test receptor antagonist',
                                       NULL, NULL, 1, 1, 1);
    INSERT INTO drug_mechanism VALUES (2, 1, NULL, 'INHIBITOR', 'Phenotypic, no target',
                                       NULL, NULL, 0, 0, 1);
    -- Inserted in an order that (ref_type, ref_id) string sorting must undo.
    INSERT INTO mechanism_refs VALUES (1, 1, 'PubMed', '3588607', 'http://x/3588607');
    INSERT INTO mechanism_refs VALUES (2, 1, 'PubMed', '12954362', 'http://x/12954362');
    INSERT INTO mechanism_refs VALUES (3, 1, 'Wikipedia', 'Test', 'http://w/Test');
    """)
    conn.commit()
    conn.close()


class LocalBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._dir = tempfile.TemporaryDirectory()
        cls.path = pathlib.Path(cls._dir.name) / "chembl_99.db"
        build_fixture(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def setUp(self):
        self.db = chembl_local.LocalChEMBL(self.path)
        self.addCleanup(self.db.close)

    # -- filters ---------------------------------------------------------

    def test_binding_activities_filter_on_target_organism_not_assay_organism(self):
        # Activity 1 is a human target assayed in a rat prep. Joining
        # assays.assay_organism instead of target_dictionary.organism would
        # lose it, and losing real measurements is the failure this port
        # most needs to not have.
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "Ki")
        self.assertIn("CHEMBL_ASSAY_B", [a["assay_chembl_id"] for a in acts])
        self.assertTrue(all(a["target_organism"] == "Homo sapiens" for a in acts))

    def test_binding_activities_exclude_non_human_targets(self):
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "Ki")
        self.assertNotIn("CHEMBL_RAT", [a["target_chembl_id"] for a in acts])

    def test_binding_activities_exclude_functional_assays(self):
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "EC50")
        self.assertEqual(acts, [])

    def test_binding_activities_are_scoped_to_the_requested_molecule(self):
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "Ki")
        self.assertNotIn(11.0, [a["standard_value"] for a in acts])

    def test_censored_and_non_nm_values_are_returned_for_the_caller_to_reject(self):
        # The backend deliberately does NOT apply the relation/units filters:
        # they live in load_molecule so both backends drop the same rows for
        # the same documented reason, and so the counts in the log stay
        # attributable to one place.
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "Ki")
        self.assertIn(">", [a["standard_relation"] for a in acts])
        acts = self.db.binding_activities("CHEMBL_TESTMOL", "IC50")
        self.assertEqual([a["standard_units"] for a in acts], ["uM"])

    def test_functional_activities_restrict_to_the_listed_standard_types(self):
        acts = self.db.functional_activities(
            "CHEMBL_TESTMOL", build_db.FUNCTIONAL_STANDARD_TYPES)
        self.assertNotIn("Potency", [a["standard_type"] for a in acts])

    def test_functional_activities_carry_bao_label_for_the_organism_filter(self):
        acts = self.db.functional_activities(
            "CHEMBL_TESTMOL", build_db.FUNCTIONAL_STANDARD_TYPES)
        labels = {a["assay_chembl_id"]: a["bao_label"] for a in acts}
        self.assertEqual(labels["CHEMBL_ASSAY_ORG"], "organism-based format")
        self.assertEqual(labels["CHEMBL_ASSAY_F"], "cell-based format")

    # -- API-shape equivalence -------------------------------------------

    def test_activity_records_carry_every_field_load_molecule_reads(self):
        act = self.db.binding_activities("CHEMBL_TESTMOL", "Ki")[0]
        for field in ("standard_value", "standard_units", "standard_relation",
                      "standard_type", "target_chembl_id", "assay_chembl_id",
                      "assay_description", "data_validity_comment", "bao_label",
                      "document_chembl_id", "document_journal", "document_year"):
            self.assertIn(field, act)

    def test_target_components_always_carry_an_accession_key(self):
        # load_molecule indexes component["accession"] directly, so a missing
        # key is a KeyError mid-build, not a skipped target.
        target = self.db.target("CHEMBL_HUMAN")
        self.assertEqual(len(target["target_components"]), 2)
        self.assertEqual([c["accession"] for c in target["target_components"]],
                         ["P00001", None])

    def test_target_synonyms_use_the_rest_apis_key_name(self):
        target = self.db.target("CHEMBL_HUMAN")
        component = target["target_components"][0]
        gene = next(s["component_synonym"]
                    for s in component["target_component_synonyms"]
                    if s["syn_type"] == "GENE_SYMBOL")
        self.assertEqual(gene, "TSTR1")

    def test_unknown_target_yields_an_empty_component_list_not_a_crash(self):
        self.assertEqual(self.db.target("CHEMBL_NOPE")["target_components"], [])

    def test_target_lookups_are_cached(self):
        first = self.db.target("CHEMBL_HUMAN")
        self.assertIs(self.db.target("CHEMBL_HUMAN"), first)

    def test_unknown_document_is_empty_rather_than_raising(self):
        self.assertEqual(self.db.document("CHEMBL_NOPE"), {})

    def test_document_carries_the_fields_the_citation_builder_reads(self):
        doc = self.db.document("CHEMBL_DOC1")
        self.assertEqual(doc["pubmed_id"], 12345678)
        self.assertEqual(doc["doi"], "10.1000/test")
        self.assertEqual(doc["title"], "A paper about testmol")

    # -- mechanisms ------------------------------------------------------

    def test_mechanism_refs_sort_the_way_the_rest_api_returns_them(self):
        # chembl_mechanism_citation() takes min() by ref_type alone, so all
        # PubMed refs tie and iteration order picks the cited paper. The API
        # sorts (ref_type, ref_id) as strings, which puts "12954362" before
        # "3588607"; ordering by insertion id instead flips it.
        mech = next(m for m in self.db.mechanisms("CHEMBL_TESTMOL")
                    if m["target_chembl_id"] == "CHEMBL_HUMAN")
        self.assertEqual([r["ref_id"] for r in mech["mechanism_refs"]],
                         ["12954362", "3588607", "Test"])
        self.assertEqual(build_db.chembl_mechanism_citation(mech),
                         ("http://x/12954362", "PubMed 12954362"))

    def test_untargeted_mechanism_is_returned_with_a_null_target(self):
        # The API returns these; dropping them here would make the two
        # backends disagree about what ChEMBL says.
        mechs = self.db.mechanisms("CHEMBL_TESTMOL")
        self.assertEqual(len(mechs), 2)
        self.assertIn(None, [m["target_chembl_id"] for m in mechs])

    # -- handle ----------------------------------------------------------

    def test_release_label_comes_from_the_filename(self):
        self.assertEqual(self.db.release, "chembl_99")

    def test_handle_is_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.db.conn.execute("DELETE FROM activities")


class BackendDispatchTest(unittest.TestCase):
    """build_db must route through whichever backend is installed, and must
    go back to the API when the backend is cleared -- a leaked backend would
    make a later 'api' run silently read the local dump instead."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._dir = tempfile.TemporaryDirectory()
        cls.path = pathlib.Path(cls._dir.name) / "chembl_99.db"
        build_fixture(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def setUp(self):
        self.db = chembl_local.LocalChEMBL(self.path)
        build_db.set_chembl_backend(self.db)
        build_db._target_cache.clear()
        build_db._document_cache.clear()
        self.addCleanup(build_db._document_cache.clear)
        self.addCleanup(build_db._target_cache.clear)
        self.addCleanup(build_db.set_chembl_backend, None)
        self.addCleanup(self.db.close)

    def test_fetch_functions_use_the_local_backend_without_network(self):
        def explode(*args, **kwargs):
            raise AssertionError("went to the network with a local backend installed")
        original = build_db.get_json
        build_db.get_json = explode
        self.addCleanup(setattr, build_db, "get_json", original)

        self.assertTrue(build_db.fetch_chembl_binding_activities("CHEMBL_TESTMOL", "Ki"))
        self.assertTrue(build_db.fetch_chembl_mechanisms("CHEMBL_TESTMOL"))
        self.assertTrue(build_db.cached_chembl_target("CHEMBL_HUMAN")["target_components"])
        self.assertEqual(build_db.fetch_chembl_document("CHEMBL_DOC1")["pubmed_id"], 12345678)

    def test_functional_fetch_drops_organism_based_assays(self):
        acts = build_db.fetch_chembl_functional_activities("CHEMBL_TESTMOL")
        self.assertEqual([a["assay_chembl_id"] for a in acts], ["CHEMBL_ASSAY_F"])

    def test_clearing_the_backend_restores_the_api_path(self):
        build_db.set_chembl_backend(None)
        calls = []
        original = build_db.get_json
        self.addCleanup(setattr, build_db, "get_json", original)
        build_db.get_json = lambda url, **kw: calls.append(url) or {"mechanisms": []}
        build_db.fetch_chembl_mechanisms("CHEMBL_TESTMOL")
        self.assertEqual(len(calls), 1)

    def test_backend_label_names_the_release(self):
        self.assertIn("chembl_99", build_db.chembl_backend_label())
        build_db.set_chembl_backend(None)
        self.assertEqual(build_db.chembl_backend_label(), "ChEMBL REST API")


REAL_DB = chembl_local.find_database()


@unittest.skipIf(REAL_DB is None,
                 "no local ChEMBL release found (see scripts/chembl_local.py)")
class RealReleaseTest(unittest.TestCase):
    """Runs only where a real release is installed.

    These are the assertions a fixture can't make: that the queries return
    the numbers the live API returns. The counts are caffeine's, cross-checked
    against the API-built database that preceded this port."""

    @classmethod
    def setUpClass(cls):
        cls.db = chembl_local.LocalChEMBL(REAL_DB)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_caffeine_adora_ki_counts_match_the_api_built_database(self):
        acts = [a for a in self.db.binding_activities("CHEMBL113", "Ki")
                if a["standard_relation"] == "=" and a["standard_units"] == "nM"]
        counts = {}
        for act in acts:
            counts[act["target_chembl_id"]] = counts.get(act["target_chembl_id"], 0) + 1
        self.assertEqual(counts["CHEMBL251"], 18)   # ADORA2A
        self.assertEqual(counts["CHEMBL255"], 17)   # ADORA2B
        self.assertEqual(counts["CHEMBL226"], 13)   # ADORA1
        self.assertEqual(counts["CHEMBL256"], 8)    # ADORA3

    def test_the_target_lookup_that_aborted_two_api_rebuilds(self):
        for chembl_id, accession in (("CHEMBL226", "P30542"),
                                     ("CHEMBL2484", "Q04844"),
                                     ("CHEMBL291", "Q08493")):
            target = self.db.target(chembl_id)
            self.assertEqual(target["target_components"][0]["accession"], accession)

    def test_release_looks_like_a_chembl_release(self):
        self.assertRegex(self.db.release, r"^chembl_\d+$")

    def test_counts_are_non_empty(self):
        self.assertGreater(self.db.counts()["activities"], 1_000_000)


if __name__ == "__main__":
    unittest.main()
