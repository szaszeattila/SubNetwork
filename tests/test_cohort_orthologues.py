"""Offline tests for scripts/resolve_cohort_orthologues.py.

These lock in the reciprocal-best-match rules (D20) that decide whether a
non-human mammalian ChEMBL SINGLE PROTEIN record is a human protein, without
ever touching the network or an aligner: `leads` and `decide` are pure
functions of pre-computed identities, tested against the exact numbers in the
script's own docstring (rat Oprk1/Oprk2, rat Scn3a vs SCN3A/SCN2A, human
DHFR/DHFR2, the guinea-pig mu fragment P97266, the rat Cyp2d cluster). `resolve`
is tested against a hand-built cache shaped exactly like the on-disk one
(`_seq_key`/`_rev_key`), so no alignment ever runs there either.

`load_fasta`, `clean` and `candidates` are tested against real files and a
real (if tiny) database. One test each exercises the real `Aligner` (parasail)
on short synthetic sequences, skipped if parasail is not importable, to check
`forward_hits` and `reverse_hits` actually call it the way the pure functions
above assume.

A last block checks the one line scripts/cohort/export.py adds for this
backfill (D20): `human_orthologue` appears on a target when
target_orthologues has a match for it, and is silently absent - not null,
absent - when the table does not exist at all, which is every database built
before this backfill was ever run.

This test never opens db/cohort1.db; every sqlite fixture here is either an
in-memory or a tiny on-disk database built from db/schema_cohort.sql (export()
requires a real file to open read-only).

Run with: python3 -m unittest discover -s tests
"""

import gzip
import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_orthologues as orth  # noqa: E402
from cohort import common, export as export_mod  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

try:
    import parasail  # noqa: F401
    HAVE_PARASAIL = True
except ImportError:
    HAVE_PARASAIL = False


# --------------------------------------------------------------- fixtures

def fake_cohort_db():
    """An in-memory cohort database at the real schema's current shape."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def add_target(conn, chembl_id, target_type, accessions, tax_id=None):
    conn.execute("INSERT INTO targets(chembl_id, target_type, tax_id) VALUES (?,?,?)",
                 (chembl_id, target_type, tax_id))
    for acc in accessions:
        conn.execute(
            "INSERT INTO target_components(target_chembl_id, accession) VALUES (?,?)",
            (chembl_id, acc))


def fake_chembl_organisms(rows):
    """rows: [(tax_id, l2)]. Only the column candidates() reads."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE organism_class (tax_id INTEGER, l1 TEXT, l2 TEXT, l3 TEXT)")
    conn.executemany("INSERT INTO organism_class(tax_id, l2) VALUES (?, ?)", rows)
    return conn


def write_fasta(path, entries):
    """entries: [(accession, header_suffix, sequence)]. Writes a plain or
    gzipped UniProt-style FASTA depending on path's suffix, sequence wrapped
    across two lines to exercise multi-line parsing."""
    lines = []
    for acc, suffix, seq in entries:
        lines.append(f">sp|{acc}|{suffix}")
        mid = len(seq) // 2 or len(seq)
        if mid and mid < len(seq):
            lines.append(seq[:mid])
            lines.append(seq[mid:])
        else:
            lines.append(seq)
    text = "\n".join(lines) + "\n"
    if str(path).endswith(".gz"):
        with gzip.open(path, "wt") as fh:
            fh.write(text)
    else:
        path.write_text(text)


# ------------------------------------------------------------------ leads

class LeadsTest(unittest.TestCase):
    def test_true_on_an_absolute_lead(self):
        # rat Oprk1: 94% identical to human OPRK1, 59% to the nearest paralogue.
        self.assertTrue(orth.leads(0.94, 0.59))

    def test_true_by_the_difference_ratio_for_a_conserved_family(self):
        # rat Scn3a: 97.2% SCN3A, 87.8% SCN2A - 9.4 points but four times the
        # remaining differences (12.2 vs 2.8).
        self.assertTrue(orth.leads(0.972, 0.878))

    def test_false_for_the_dhfr_retrogene_pair(self):
        # rat Dhfr: 87% to human DHFR, 84% to the retrogene DHFR2 - neither
        # test passes, and the match is refused rather than guessed.
        self.assertFalse(orth.leads(0.87, 0.84))

    def test_false_when_other_is_at_least_best(self):
        self.assertFalse(orth.leads(0.80, 0.80))
        self.assertFalse(orth.leads(0.80, 0.85))


# ------------------------------------------------------------------ decide

class DecideTest(unittest.TestCase):
    def test_matched_names_the_best_hit_and_the_runner_up(self):
        forward = [("H1", 0.94, 1.0), ("H2", 0.59, 0.95)]
        reverse = [("R1", 0.94, False), ("R2", 0.60, False)]
        best_human_of = {"R2": "H2"}
        row = orth.decide("R1", forward, reverse, best_human_of)
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["human_accession"], "H1")
        self.assertEqual(row["runner_up"], "H2")

    def test_a_fragment_with_a_clear_lead_is_matched(self):
        # the guinea-pig mu fragment P97266: 98 residues, 98% identical to
        # human OPRM1 and clearly ahead of the nearest paralogue it resembles.
        forward = [("OPRM1", 0.98, 0.24), ("OPRK1", 0.82, 0.24)]
        reverse = [("R_FRAG", 0.98, False)]
        row = orth.decide("R_FRAG", forward, reverse, {})
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["human_accession"], "OPRM1")

    def test_the_same_fragment_at_lower_identity_is_refused(self):
        forward = [("OPRM1", 0.82, 0.24)]
        row = orth.decide("R_FRAG", forward, None, {})
        self.assertEqual(row["status"], "fragment_below_identity")
        self.assertIsNone(row["human_accession"])

    def test_full_length_below_identity_is_refused(self):
        forward = [("H1", 0.65, 0.95)]
        row = orth.decide("R1", forward, None, {})
        self.assertEqual(row["status"], "below_identity")

    def test_empty_forward_is_no_human_hit(self):
        row = orth.decide("R1", [], None, {})
        self.assertEqual(row["status"], "no_human_hit")
        self.assertIsNone(row["human_accession"])
        self.assertIsNone(row["best_accession"])

    def test_no_lead_over_runner_up(self):
        forward = [("H1", 0.75, 0.9), ("H2", 0.70, 0.9)]
        row = orth.decide("R1", forward, [("R1", 0.75, False)], {})
        self.assertEqual(row["status"], "no_lead_over_runner_up")

    def test_record_absent_from_reverse_is_not_reciprocal(self):
        forward = [("H1", 0.94, 1.0)]
        row = orth.decide("R1", forward, [("OTHER", 0.90, False)], {})
        self.assertEqual(row["status"], "not_reciprocal")

    def test_reverse_none_is_also_not_reciprocal(self):
        forward = [("H1", 0.94, 1.0)]
        row = orth.decide("R1", forward, None, {})
        self.assertEqual(row["status"], "not_reciprocal")

    def test_a_rival_with_higher_identity_is_not_reciprocal(self):
        forward = [("H1", 0.95, 1.0)]
        reverse = [("R1", 0.90, False), ("RIVAL", 0.93, False)]
        best_human_of = {"RIVAL": "H1"}
        row = orth.decide("R1", forward, reverse, best_human_of)
        self.assertEqual(row["status"], "not_reciprocal")

    def test_a_rival_within_the_lead_blocks_with_no_lead_in_species(self):
        # the rat Cyp2d cluster: every gene reaches CYP2D6 and none leads it.
        forward = [("H1", 0.95, 1.0)]
        reverse = [("R1", 0.90, False), ("RIVAL", 0.85, False)]
        best_human_of = {"RIVAL": "H1"}
        row = orth.decide("R1", forward, reverse, best_human_of)
        self.assertEqual(row["status"], "no_lead_in_species")

    def test_a_rival_whose_own_best_human_is_different_does_not_block(self):
        # the mu fragment is 82% identical to human kappa, but the fragment's
        # own best match is mu, not kappa - it is not a rival at all.
        forward = [("H_MU", 0.95, 1.0)]
        reverse = [("R_MU", 0.90, False), ("R_FRAG_KAPPA", 0.85, False)]
        best_human_of = {"R_FRAG_KAPPA": "H_KAPPA"}
        row = orth.decide("R_MU", forward, reverse, best_human_of)
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["human_accession"], "H_MU")

    def test_a_species_protein_flagged_same_does_not_block(self):
        # guinea pig has mu as a fragment (P97266) and full-length (Q8CGM4);
        # the full-length record is the same protein filed again, not a rival.
        forward = [("H_MU", 0.95, 1.0)]
        reverse = [("R_FRAG", 0.90, False), ("R_FULL", 0.99, True)]
        best_human_of = {"R_FULL": "H_MU"}
        row = orth.decide("R_FRAG", forward, reverse, best_human_of)
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["human_accession"], "H_MU")


# --------------------------------------------------------------- one_to_one

class OneToOneTest(unittest.TestCase):
    def test_two_records_reaching_one_protein_and_not_same_are_both_refused(self):
        rows = {
            "T1": {"target_chembl_id": "T1", "accession": "A1", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
            "T2": {"target_chembl_id": "T2", "accession": "A2", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
        }
        orth.one_to_one(rows, same_protein=lambda tax_id, a, b: False)
        self.assertIsNone(rows["T1"]["human_accession"])
        self.assertIsNone(rows["T2"]["human_accession"])
        self.assertEqual(rows["T1"]["status"], "several_records_one_protein")
        self.assertEqual(rows["T2"]["status"], "several_records_one_protein")

    def test_two_records_reaching_one_protein_that_are_the_same_protein_stay_matched(self):
        rows = {
            "T1": {"target_chembl_id": "T1", "accession": "A1", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
            "T2": {"target_chembl_id": "T2", "accession": "A2", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
        }
        orth.one_to_one(rows, same_protein=lambda tax_id, a, b: True)
        self.assertEqual(rows["T1"]["human_accession"], "H1")
        self.assertEqual(rows["T2"]["human_accession"], "H1")
        self.assertEqual(rows["T1"]["status"], "matched")
        self.assertEqual(rows["T2"]["status"], "matched")

    def test_the_same_human_accession_in_two_different_species_is_not_a_conflict(self):
        rows = {
            "T1": {"target_chembl_id": "T1", "accession": "A1", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
            "T2": {"target_chembl_id": "T2", "accession": "A2", "tax_id": 10090,
                   "human_accession": "H1", "status": "matched"},
        }
        # same_protein must not even need to distinguish these - different
        # tax_ids never share a `reach` bucket.
        orth.one_to_one(rows, same_protein=lambda tax_id, a, b: False)
        self.assertEqual(rows["T1"]["human_accession"], "H1")
        self.assertEqual(rows["T2"]["human_accession"], "H1")

    def test_the_same_accession_filed_as_two_targets_is_not_a_conflict(self):
        rows = {
            "T1": {"target_chembl_id": "T1", "accession": "A1", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
            "T2": {"target_chembl_id": "T2", "accession": "A1", "tax_id": 10116,
                   "human_accession": "H1", "status": "matched"},
        }

        def boom(tax_id, a, b):
            raise AssertionError("same_protein must not be called: `others` is empty")

        orth.one_to_one(rows, same_protein=boom)
        self.assertEqual(rows["T1"]["human_accession"], "H1")
        self.assertEqual(rows["T2"]["human_accession"], "H1")


# -------------------------------------------------------------- load_fasta

class LoadFastaTest(unittest.TestCase):
    ENTRIES = [
        ("P35372", "OPRM_HUMAN Mu-type opioid receptor OS=Homo sapiens OX=9606 GN=OPRM1 PE=1 SV=2",
         "MDSSTGPGNTSDCSDPLAQASCSPAP"),
        ("P41145", "OPRK_HUMAN Kappa-type opioid receptor OS=Homo sapiens OX=9606 PE=1 SV=1",
         "MESPIQIFRGEPGPTCAPSACLPPNS"),
    ]

    def test_plain_fasta_reads_accession_sequence_and_gene(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "proteome.fasta"
            write_fasta(path, self.ENTRIES)
            out = orth.load_fasta(path)
        self.assertEqual(out["P35372"], ("MDSSTGPGNTSDCSDPLAQASCSPAP", "OPRM1"))
        # no GN= field at all -> gene is None, never guessed.
        self.assertEqual(out["P41145"], ("MESPIQIFRGEPGPTCAPSACLPPNS", None))

    def test_gzipped_fasta_reads_the_same(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "proteome.fasta.gz"
            write_fasta(path, self.ENTRIES)
            out = orth.load_fasta(path)
        self.assertEqual(out["P35372"], ("MDSSTGPGNTSDCSDPLAQASCSPAP", "OPRM1"))
        self.assertEqual(out["P41145"], ("MESPIQIFRGEPGPTCAPSACLPPNS", None))


# ------------------------------------------------------------------- clean

class CleanTest(unittest.TestCase):
    def test_u_o_j_become_x(self):
        self.assertEqual(orth.clean("ARNU"), "ARNX")
        self.assertEqual(orth.clean("ARNO"), "ARNX")
        self.assertEqual(orth.clean("ARNJ"), "ARNX")

    def test_lowercase_is_uppercased(self):
        self.assertEqual(orth.clean("arndcq"), "ARNDCQ")

    def test_lowercase_disallowed_letters_are_also_cleaned(self):
        self.assertEqual(orth.clean("uoj"), "XXX")


# --------------------------------------------------------------- candidates

class CandidatesTest(unittest.TestCase):
    def test_only_nonhuman_mammalian_single_component_single_proteins_qualify(self):
        conn = fake_cohort_db()
        # a human single protein - excluded by tax_id alone.
        add_target(conn, "CHEMBL_HUMAN", "SINGLE PROTEIN", ["P00001"], tax_id=9606)
        # a rat single protein, single component - the one that should qualify.
        add_target(conn, "CHEMBL_RAT", "SINGLE PROTEIN", ["P00002"], tax_id=10116)
        # a bird single protein - not Mammalia.
        add_target(conn, "CHEMBL_BIRD", "SINGLE PROTEIN", ["P00003"], tax_id=9031)
        # a rat PROTEIN COMPLEX - not a SINGLE PROTEIN, however few accessions.
        add_target(conn, "CHEMBL_COMPLEX", "PROTEIN COMPLEX", ["P00004", "P00005"],
                   tax_id=10116)
        # a rat SINGLE PROTEIN with two components - excluded as multi-component.
        add_target(conn, "CHEMBL_MULTI", "SINGLE PROTEIN", ["P00006", "P00007"],
                   tax_id=10116)

        chembl = fake_chembl_organisms([(10116, "Mammalia"), (9031, "Aves")])
        cands = orth.candidates(conn, chembl)

        self.assertEqual(cands, {"CHEMBL_RAT": ("P00002", 10116)})


# --------------------------------------------------------- write/ensure_table

class WriteAndEnsureTableTest(unittest.TestCase):
    def _row(self, tid="T1", accession="R1", tax_id=10116, human_accession="H1",
             status="matched"):
        return {"target_chembl_id": tid, "accession": accession, "tax_id": tax_id,
                "human_accession": human_accession, "best_accession": human_accession,
                "identity": 0.95, "runner_up": None, "runner_up_identity": None,
                "coverage": 1.0, "status": status}

    def test_ensure_table_creates_it_from_the_real_schema_file(self):
        conn = sqlite3.connect(":memory:")
        self.assertIsNone(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='target_orthologues'"
        ).fetchone())
        created = orth.ensure_table(conn)
        self.assertTrue(created)
        self.assertIsNotNone(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='target_orthologues'"
        ).fetchone())
        # a second call is a no-op, not a re-create.
        self.assertFalse(orth.ensure_table(conn))

    def test_write_reports_rows_changed_then_zero_then_nonzero_on_a_real_change(self):
        conn = sqlite3.connect(":memory:")
        rows = {"T1": self._row()}

        first = orth.write(conn, rows)
        self.assertEqual(first, 1)

        second = orth.write(conn, rows)
        self.assertEqual(second, 0)

        rows["T1"]["status"] = "no_lead_in_species"
        rows["T1"]["human_accession"] = None
        third = orth.write(conn, rows)
        self.assertGreater(third, 0)


# ------------------------------------------------------------------- resolve

class ResolveTest(unittest.TestCase):
    def test_a_candidate_with_no_sequence_is_no_sequence(self):
        cands = {"T1": ("R1", 10116)}
        species = {}  # no sequence recorded for R1 at all
        cache = {"forward": {}, "reverse": {}}
        rows = orth.resolve(cands, species, cache, same_protein=lambda t, a, b: False)
        self.assertEqual(rows["T1"]["status"], "no_sequence")
        self.assertIsNone(rows["T1"]["human_accession"])

    def test_a_normal_candidate_is_matched_from_the_cache_alone(self):
        seq = "MKVLATILGGSPQR"
        species = {10116: {"R1": seq}}
        cands = {"T1": ("R1", 10116)}
        fwd_key = orth._seq_key(seq)
        rev_key = orth._rev_key(("H1", 10116, "R1"))
        cache = {
            "forward": {fwd_key: [("H1", 0.95, 1.0)]},
            "reverse": {rev_key: [("R1", 0.95, False)]},
        }
        rows = orth.resolve(cands, species, cache, same_protein=lambda t, a, b: False)
        self.assertEqual(rows["T1"]["status"], "matched")
        self.assertEqual(rows["T1"]["human_accession"], "H1")


# ------------------------------------------------------------- real Aligner

@unittest.skipUnless(HAVE_PARASAIL, "parasail is not importable in this environment")
class AlignerTest(unittest.TestCase):
    def test_forward_hits_ranks_an_identical_sequence_first(self):
        aligner = orth.Aligner()
        query = "MKVLATILGGSPQRKLADFGHIVWNYCE"
        library = [
            ("SAME", query),
            ("DIFFERENT", "AAAAAAAAAAAAAAAAAAAAAAAAAAAA"),
        ]
        by_acc = dict(library)
        hits = orth.forward_hits(aligner, query, library, by_acc)
        self.assertEqual(hits[0][0], "SAME")
        self.assertAlmostEqual(hits[0][1], 1.0)

    def test_reverse_hits_scores_a_fragment_of_a_library_protein_at_full_identity(self):
        aligner = orth.Aligner()
        fragment = "MKVLATILGGSPQR"
        human_seq = fragment + "KLADFGHIVWNYCEQRSTPLMKV"
        library = [("FRAG", fragment)]
        by_acc = {"FRAG": fragment}
        hits = orth.reverse_hits(aligner, human_seq, "FRAG", library, by_acc)
        acc, ident, same = hits[0]
        self.assertEqual(acc, "FRAG")
        # identity is over the shorter (fragment) sequence, so a substring of
        # the library protein scores 1.0 rather than its length ratio.
        self.assertAlmostEqual(ident, 1.0)


# ------------------------------------------------------------ export field

def strip_table(schema_text, table):
    pattern = re.compile(r"CREATE TABLE IF NOT EXISTS " + re.escape(table) + r" \(.*?\n\);",
                         re.S)
    stripped, n = pattern.subn("", schema_text)
    assert n == 1, f"expected exactly one {table} table in the schema"
    return stripped


class ExportHumanOrthologueFieldTest(unittest.TestCase):
    """scripts/cohort/export.py adds `human_orthologue`, last in TARGET_FIELDS,
    read from target_orthologues only when that table exists (D20). Neither
    tests/test_cohort_build.py (fake-ChEMBL fixtures, no cohort database at
    all - its own docstring says so) nor tests/test_cohort_report.py
    (analysis/cohort1 pure functions) builds a cohort database and runs the
    export, so this is done here instead, against a tiny on-disk database
    (export() opens its db_path read-only, so :memory: will not do)."""

    def _write_db(self, path, schema_text, with_orthologue_row):
        conn = sqlite3.connect(str(path))
        conn.executescript(schema_text)
        conn.execute(
            "INSERT INTO targets(chembl_id, target_type, tax_id) VALUES (?,?,?)",
            ("CHEMBL_RAT", "SINGLE PROTEIN", 10116))
        conn.execute(
            "INSERT INTO target_components(target_chembl_id, accession) VALUES (?,?)",
            ("CHEMBL_RAT", "P00002"))
        if with_orthologue_row:
            conn.execute(
                "INSERT INTO target_orthologues(target_chembl_id, accession, tax_id,"
                " human_accession, best_accession, identity, runner_up,"
                " runner_up_identity, coverage, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("CHEMBL_RAT", "P00002", 10116, "P00001", "P00001", 0.95, None,
                 None, 1.0, "matched"))
        conn.commit()
        conn.close()

    def _exported_target(self, db_path):
        with tempfile.TemporaryDirectory() as out_d:
            export_mod.export(db_path=db_path, out_dir=pathlib.Path(out_d), backup=False)
            text = (pathlib.Path(out_d) / "graph.data.js").read_text()
        m = re.match(r"^// .*\nconst COHORT_DATA = (.*);\n$", text, re.S)
        payload = json.loads(m.group(1))
        fields = payload["fields"]["targets"]
        # find the CHEMBL_RAT row by its position of the chembl_id field
        # rather than relying on row order.
        chembl_id_idx = fields.index("chembl_id")
        row = next(t for t in payload["targets"] if t[chembl_id_idx] == "CHEMBL_RAT")
        return dict(zip(fields, row))

    def test_human_orthologue_appears_when_the_table_has_a_match(self):
        with tempfile.TemporaryDirectory() as d:
            db_path = pathlib.Path(d) / "cohort.db"
            self._write_db(db_path, SCHEMA, with_orthologue_row=True)
            target = self._exported_target(db_path)
        self.assertEqual(target.get("human_orthologue"), "P00001")

    def test_human_orthologue_is_absent_without_the_table_at_all(self):
        schema_no_orth = strip_table(SCHEMA, "target_orthologues")
        with tempfile.TemporaryDirectory() as d:
            db_path = pathlib.Path(d) / "cohort.db"
            self._write_db(db_path, schema_no_orth, with_orthologue_row=False)
            target = self._exported_target(db_path)
        # the trailing-null trim drops a field that never had a value, so it
        # is missing from the row entirely - not present and null.
        self.assertNotIn("human_orthologue", target)


if __name__ == "__main__":
    unittest.main()
