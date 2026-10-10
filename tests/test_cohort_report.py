"""Unit tests for the cohort-1 report's substantive analysis logic.

These exercise the pure functions in analysis/cohort1/scripts/step2_candidates.py
and step3_evidence.py: MeSH descendant/exclusion logic, target-assignment
specificity, study identity/provenance, and log-space pooling. Everything here
runs offline against the real config files (cns_indication_scope.json,
tier_rules.json) - no ChEMBL database, no network. main() is never called.

Run with: python3 -m unittest discover -s tests
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / "analysis" / "cohort1" / "scripts"))

import common  # noqa: E402
import step2_candidates as step2  # noqa: E402
import step3_evidence as step3  # noqa: E402


SCOPE = common.load_config("cns_indication_scope.json")


class InClassTest(unittest.TestCase):
    """Tree-number membership: full dot-delimited prefix only, self included."""

    def test_tree_number_is_a_descendant_of_itself(self):
        self.assertEqual(step2.in_class({"C10"}, ["C10"]), {"C10"})

    def test_child_tree_number_matches_on_dotted_prefix(self):
        self.assertEqual(step2.in_class({"C10.551"}, ["C10"]), {"C10.551"})

    def test_bare_string_prefix_without_a_period_does_not_match(self):
        # "C100" and "C10X" both start with the characters "C10" but are not
        # inside the C10 class: the rule requires the prefix to be followed
        # by a literal period, not just any character.
        self.assertEqual(step2.in_class({"C100"}, ["C10"]), set())
        self.assertEqual(step2.in_class({"C10X"}, ["C10"]), set())


class ClassifyScopeTest(unittest.TestCase):
    """classify_scope against the real cns_indication_scope.json config."""

    def test_oncology_only_descriptor_is_excluded_but_labelled(self):
        tree = {"D_ONCO": {"C10.551.500"}}
        classified = step2.classify_scope(SCOPE, tree)
        info = classified["D_ONCO"]
        self.assertFalse(info["core"])
        self.assertIn("cns_oncology", info["classes"])

    def test_myasthenia_gravis_case_stays_core_via_remaining_placement(self):
        # A descriptor placed under BOTH an in-core autoimmune tree
        # (C10.114.703) and an excluded neuromuscular-junction tree
        # (C10.668.758) must stay in core: exclusion only fires when EVERY
        # in-scope placement is excluded, and one placement survives here.
        tree = {"D_MG": {"C10.114.703", "C10.668.758"}}
        classified = step2.classify_scope(SCOPE, tree)
        info = classified["D_MG"]
        self.assertTrue(info["core"])
        self.assertIn("muscle_and_neuromuscular_junction", info["classes"])

    def test_pain_descriptor_placement_is_not_core(self):
        # The real MeSH placement of the Pain descriptor: none of its tree
        # numbers sit under C10 or F03, so it never enters core scope, and it
        # carries the general_pain class as an additive-only option.
        tree = {"D_PAIN": {"C23.888.592.612", "F02.830.816.444", "G11.561.790.444"}}
        classified = step2.classify_scope(SCOPE, tree)
        info = classified["D_PAIN"]
        self.assertFalse(info["core"])
        self.assertIn("general_pain", info["classes"])


class VariantMembersTest(unittest.TestCase):
    """Cumulative scope variants build on top of the always-included core."""

    def test_oncology_descriptor_enters_only_at_its_own_variant_and_widest(self):
        classified = {
            "D_CORE": {"core": True, "classes": ["core"]},
            "D_ONCO": {"core": False, "classes": ["cns_oncology"]},
        }
        variants = step2.variant_members(SCOPE, classified)
        self.assertNotIn("D_ONCO", variants["S0_core"])
        self.assertIn("D_ONCO", variants["S1_core_plus_oncology"])
        self.assertIn("D_CORE", variants["S5_widest"])
        self.assertIn("D_ONCO", variants["S5_widest"])


class SpecificityTest(unittest.TestCase):
    """Target-assignment specificity per config/tier_rules.json."""

    def test_human_direct_single_protein_and_its_mutant_variant(self):
        self.assertEqual(
            step3.specificity("SINGLE PROTEIN", 9606, 9, "D", None),
            "human_direct_single_protein")
        self.assertEqual(
            step3.specificity("SINGLE PROTEIN", 9606, 9, "D", "VAR1"),
            "human_direct_single_protein_mutant")

    def test_confidence_below_nine_never_yields_a_human_direct_verdict(self):
        # Never use >= 7 as a proxy: confidence 8 (homologous single protein)
        # must not be mistaken for confidence 9 (direct single protein).
        self.assertEqual(
            step3.specificity("SINGLE PROTEIN", 9606, 8, "D", None),
            "homologous_or_unknown_species")
        # Confidence 7 with a SINGLE PROTEIN target type is likewise not a
        # human-direct verdict of any kind.
        seven = step3.specificity("SINGLE PROTEIN", 9606, 7, "D", None)
        self.assertNotEqual(seven, "human_direct_single_protein")
        self.assertFalse(str(seven).startswith("human_direct"))

    def test_human_direct_complex_and_family_or_multiple(self):
        self.assertEqual(
            step3.specificity("PROTEIN COMPLEX", 9606, 7, "D", None),
            "human_direct_complex")
        self.assertEqual(
            step3.specificity("PROTEIN FAMILY", 9606, 5, "D", None),
            "human_family_or_multiple")

    def test_nonhuman_single_protein(self):
        self.assertEqual(
            step3.specificity("SINGLE PROTEIN", 10116, 9, "D", None),
            "nonhuman")


class StudyKeyTest(unittest.TestCase):
    """Study identity precedence and provenance classification."""

    def test_precedence_pmid_over_doi_over_patent_over_doc_id(self):
        key, prov = step3.study_key(123, "10.1/x", "P1", "CHEMBL999", "PUBLICATION")
        self.assertEqual((key, prov), ("pmid:123", "publication"))

        key, prov = step3.study_key(None, "10.1/x", "P1", "CHEMBL999", "PUBLICATION")
        self.assertEqual((key, prov), ("doi:10.1/x", "publication"))

        key, prov = step3.study_key(None, None, "P1", "CHEMBL999", "PUBLICATION")
        self.assertEqual((key, prov), ("patent:P1", "patent"))

        key, prov = step3.study_key(None, None, None, "CHEMBL999", "PUBLICATION")
        self.assertEqual(key, "doc:CHEMBL999")

    def test_dataset_doi_is_deposited_not_publication(self):
        # A bulk deposit carrying a DOI must not be counted as a publication -
        # otherwise one dataset could manufacture multi-study support.
        key, prov = step3.study_key(None, "10.5/data", None, "CHEMBL1", "DATASET")
        self.assertEqual(key, "doi:10.5/data")
        self.assertEqual(prov, "deposited_dataset")

    def test_no_identifiers_at_all_is_unresolved(self):
        key, prov = step3.study_key(None, None, None, None, "PUBLICATION")
        self.assertIsNone(key)
        self.assertEqual(prov, "unresolved")


class LogMedianTest(unittest.TestCase):
    """Pooling happens in log space, never arithmetically."""

    def test_two_values_pool_to_the_geometric_midpoint(self):
        # Arithmetic mean would be 50.5 - nearly a log unit off.
        self.assertAlmostEqual(step3.log_median([1.0, 100.0]), 10.0)

    def test_three_values_pool_to_the_log_space_median(self):
        self.assertAlmostEqual(step3.log_median([1.0, 10.0, 1000.0]), 10.0)


if __name__ == "__main__":
    unittest.main()
