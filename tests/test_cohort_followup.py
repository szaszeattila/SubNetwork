"""Failure cases for the report-only recovery and policy comparison."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "analysis/cohort1/followup/analyze.py"
SPEC = importlib.util.spec_from_file_location("cohort_followup", PATH)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class UnitRecoveryTest(unittest.TestCase):
    def test_picomoIar_and_scaled_concentration(self):
        self.assertAlmostEqual(review.convert_unit(19.2, "pmol/L")[1], 0.0192)
        self.assertEqual(review.convert_unit(1.5, "10^3nM")[1], 1500)
        self.assertAlmostEqual(review.convert_unit(2, "10^-4microM")[1], 0.2)

    def test_mass_uses_measured_full_weight_and_stays_conditional(self):
        identity = dict(molecule_type="Small molecule",structure_type="MOL",canonical_smiles="C.Cl",full_mwt=200,mw_freebase=100)
        kind,value,_ = review.convert_unit(1,"ug.mL-1",identity=identity)
        self.assertEqual(kind,"conditional_mass")
        self.assertAlmostEqual(value,5000)

    def test_mass_identity_is_required(self):
        self.assertIsNone(review.convert_unit(1,"ug.mL-1",identity={"full_mwt":200})[1])

    def test_bounds_are_not_exact_values(self):
        for rel in [">","<","~",">="]:
            self.assertIsNone(review.convert_unit(1,"uM",rel)[1])

    def test_missing_different_dimensions_and_unreviewed_notation(self):
        for unit in ["","/s","mg kg-1","mol","M-1","%","10'3pM"]:
            self.assertIsNone(review.convert_unit(1,unit)[1],unit)

    def test_nonpositive_and_nonfinite(self):
        for value in [0,-1,float("inf"),float("nan"),None]:
            self.assertIsNone(review.convert_unit(value,"uM")[1])


class EvidenceTest(unittest.TestCase):
    def row(self,study="pmid:1",endpoint="binding:Ki",source="publication"):
        return dict(study_key=study,endpoint_class=endpoint,provenance_class=source)

    def test_many_rows_one_paper_stay_preliminary(self):
        self.assertEqual(review.assess([self.row()]*20),"preliminary")

    def test_different_endpoints_do_not_manufacture_replication(self):
        self.assertEqual(review.assess([self.row(),self.row("pmid:2","binding:Kd")]),"preliminary")
        self.assertEqual(review.assess([self.row(),self.row("pmid:2")]),"supported")

    def test_deposits_do_not_manufacture_replication(self):
        self.assertEqual(review.assess([self.row("doi:1",source="deposited_dataset"),self.row("doi:2",source="deposited_dataset")]),"preliminary")

    def test_species_variant_and_homology_remain_separate(self):
        r=dict(target_tax_id="9606",relationship_type="D",variant_id="",target_type="SINGLE PROTEIN",confidence_score="9")
        self.assertTrue(review.assignment_matches(r,"human_single"))
        for field,value in [("target_tax_id","10116"),("relationship_type","H"),("variant_id","12"),("confidence_score","8")]:
            self.assertFalse(review.assignment_matches(dict(r,**{field:value}),"human_single"))

    def test_complex_and_family_have_explicit_bases(self):
        r=dict(target_tax_id="9606",relationship_type="D",variant_id="",target_type="PROTEIN COMPLEX",confidence_score="7")
        self.assertFalse(review.assignment_matches(r,"human_single"))
        self.assertTrue(review.assignment_matches(r,"human_single_and_complex"))
        r.update(target_type="PROTEIN FAMILY",confidence_score="5")
        self.assertFalse(review.assignment_matches(r,"human_single_and_complex"))
        self.assertTrue(review.assignment_matches(r,"human_with_families"))


class PolicyTest(unittest.TestCase):
    def test_atc_route_survives_missing_indication_and_evidence(self):
        c=dict(molecule_type="Small molecule",cns_ind_max_phase="",route_cns_indication="0",route_atc_n="1")
        p=dict(keep_atc=True,min_cns_phase=3)
        self.assertTrue(review.membership(c,p,"small_molecules"))
        self.assertFalse(review.membership(c,dict(p,keep_atc=False),"small_molecules"))

    def test_cns_phase_is_not_overall_phase(self):
        c=dict(molecule_type="Small molecule",cns_ind_max_phase="2",family_max_phase="4",route_cns_indication="1",route_atc_n="0")
        self.assertFalse(review.membership(c,dict(keep_atc=True,min_cns_phase=3),"small_molecules"))
        self.assertTrue(review.membership(c,dict(keep_atc=True,min_cns_phase=2),"small_molecules"))


if __name__ == "__main__":
    unittest.main()
