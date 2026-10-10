"""Offline tests for scripts/resolve_cohort_gtopdb_actions.py.

These lock in the parts of the GtoPdb action backfill that need no network:
the pinned-release check on both a download and a cached file (a mismatch is
always fatal and nothing bad is cached), the identifier-only matching rules
for both ligand and target (invariants 6 and 15 - a disagreement or an
ambiguity drops the row rather than guessing, and a multi-subunit target
matches only the one PROTEIN COMPLEX record with exactly that accession set,
never fanned out onto the subunits' own SINGLE PROTEIN records - "Ranking on
accessions rewards fan-out" in docs/DATA-QUALITY-LOG.md), the ACTION_MAP
lookup and its manifest accounting for an unmapped (Type, Action), has_claim,
the fold that collapses several GtoPdb rows onto one (parent, target, type,
action), and that a rerun replaces rows rather than duplicating them and
never touches any table but its own.

No network access: `ensure_files` takes `get` as a parameter, and every test
that reaches it passes a stub rather than `requests.get`. This test never
opens db/cohort1.db; every sqlite fixture here is an in-memory database built
from db/schema_cohort.sql.

Run with: python3 -m unittest discover -s tests
"""

import collections
import itertools
import json
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_gtopdb_actions as gca  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

_molregno = itertools.count(1)


# --------------------------------------------------------------- fixtures

def fake_db():
    """An in-memory cohort database at the real schema's current shape -
    gtopdb_interactions and its index already exist here, so backfill's own
    ensure_table() is a no-op on this fixture, exactly as it is against a
    real build."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
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


def add_molecule_form(conn, parent, molregno, chembl_id, is_parent=0):
    conn.execute(
        "INSERT INTO molecule_forms(parent_molregno, molregno, chembl_id, is_parent)"
        " VALUES (?,?,?,?)", (parent, molregno, chembl_id, is_parent))


def add_target(conn, chembl_id, target_type, accessions, tax_id=None):
    conn.execute("INSERT INTO targets(chembl_id, target_type, tax_id) VALUES (?,?,?)",
                 (chembl_id, target_type, tax_id))
    for acc in accessions:
        conn.execute(
            "INSERT INTO target_components(target_chembl_id, accession) VALUES (?,?)",
            (chembl_id, acc))


def add_claim(conn, parent, target_chembl_id, claim_role="binding", basis="human_direct",
              tier="supported"):
    conn.execute(
        "INSERT INTO claims(parent_molregno, target_chembl_id, claim_role, basis,"
        " tier, tier_reason) VALUES (?,?,?,?,?,'x')",
        (parent, target_chembl_id, claim_role, basis, tier))


GTOPDB_CLAIM_COLS = ("parent_molregno", "target_chembl_id", "claim_role", "basis", "tier",
                     "tier_reason", "curated_support", "action_type", "mechanism_of_action",
                     "conflict_action", "conflict_detail")


def gtopdb_claims(conn):
    """The `gtopdb`-role claims write_claims() produced, as plain dicts, ordered
    by pair so a multi-row assertion is not at the mercy of insertion order."""
    rows = conn.execute(
        f"SELECT {', '.join(GTOPDB_CLAIM_COLS)} FROM claims WHERE claim_role = 'gtopdb'"
        " ORDER BY parent_molregno, target_chembl_id").fetchall()
    return [dict(zip(GTOPDB_CLAIM_COLS, r)) for r in rows]


def add_curated_mechanism(conn, parent, target_chembl_id, action_type):
    conn.execute(
        "INSERT INTO curated_mechanisms(parent_molregno, target_chembl_id,"
        " action_type, tier, tier_reason) VALUES (?,?,?,'supported','x')",
        (parent, target_chembl_id, action_type))


def ligand_row(lig_id, inchikey="", chembl_id=""):
    return {"Ligand ID": str(lig_id), "InChIKey": inchikey, "ChEMBL ID": chembl_id}


def interaction_row(lig_id, target_id, accessions, **overrides):
    row = {
        "Ligand ID": str(lig_id),
        "Target ID": str(target_id),
        "Target UniProt ID": accessions,
        "Target Species": "Human",
        "Type": "Agonist",
        "Action": "Agonist",
        "Action comment": "",
        "Selectivity": "",
        "Endogenous": "false",
        "Primary Target": "false",
        "Receptor Site": "",
        "Ligand Context": "",
        "PubMed ID": "",
    }
    row.update(overrides)
    return row


VERSION_LINE = '"# GtoPdb Version: 2026.3 - published: 2026-09-16"'


class _Resp:
    """A stand-in for requests.Response: only .text and .raise_for_status()
    are ever used by ensure_files."""

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


# ----------------------------------------------------------------- inputs

class FileVersionPublishedTest(unittest.TestCase):
    def test_file_version_parses_the_pinned_release_off_the_first_line(self):
        self.assertEqual(gca.file_version(VERSION_LINE), "2026.3")

    def test_file_version_is_none_when_the_line_does_not_match(self):
        self.assertIsNone(gca.file_version("Ligand ID,InChIKey\n"))

    def test_published_reads_the_date_off_the_first_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "interactions.csv"
            path.write_text(VERSION_LINE + "\nLigand ID\n1\n")
            self.assertEqual(gca.published(path), "2026-09-16")


class EnsureFilesTest(unittest.TestCase):
    VERSION = "2026.3"
    GOOD = VERSION_LINE + "\nLigand ID\n1\n"
    BAD = '"# GtoPdb Version: 2025.1 - published: 2025-01-01"\nLigand ID\n1\n'

    def test_a_download_with_the_wrong_version_raises_and_caches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d)
            calls = []

            def get(url):
                calls.append(url)
                return _Resp(self.BAD)

            with self.assertRaises(gca.GtoPdbError):
                gca.ensure_files(cache=cache, version=self.VERSION, get=get)
            # stopped at the first file (FILES order) and wrote nothing at all
            self.assertEqual(len(calls), 1)
            self.assertEqual(list(cache.iterdir()), [])

    def test_a_download_with_the_pinned_version_is_cached(self):
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d)

            def get(url):
                return _Resp(self.GOOD)

            paths = gca.ensure_files(cache=cache, version=self.VERSION, get=get)
            self.assertEqual(set(paths), {"interactions.csv", "ligands.csv"})
            for name, path in paths.items():
                self.assertTrue(path.exists(), name)
                self.assertEqual(path.read_text(), self.GOOD)

    def test_a_cached_file_with_the_wrong_version_raises_without_downloading(self):
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d)
            (cache / "interactions.csv").write_text(self.BAD)

            def get(url):
                raise AssertionError("must not download when a cached file already exists")

            with self.assertRaises(gca.GtoPdbError):
                gca.ensure_files(cache=cache, version=self.VERSION, get=get)


class ReadCsvTest(unittest.TestCase):
    def test_skips_the_version_line_and_parses_the_header(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "ligands.csv"
            path.write_text(
                VERSION_LINE + "\n"
                "Ligand ID,InChIKey,ChEMBL ID\n"
                "1,KEYAAAAAAAAAA,CHEMBL1\n"
                "2,KEYBBBBBBBBBB,CHEMBL2\n")
            rows = gca.read_csv(path)
        self.assertEqual(rows, [
            {"Ligand ID": "1", "InChIKey": "KEYAAAAAAAAAA", "ChEMBL ID": "CHEMBL1"},
            {"Ligand ID": "2", "InChIKey": "KEYBBBBBBBBBB", "ChEMBL ID": "CHEMBL2"},
        ])


# --------------------------------------------------------------- matching

class MatchLigandsTest(unittest.TestCase):
    def test_inchikey_route(self):
        ligands = [ligand_row(1, inchikey="KEY1")]
        counts = collections.Counter()
        out = gca.match_ligands(ligands, {"KEY1": 100}, {}, counts)
        self.assertEqual(out, {1: (100, "inchikey")})
        self.assertEqual(counts, {})

    def test_chembl_id_only_route_via_a_molecule_forms_style_mapping(self):
        ligands = [ligand_row(2, chembl_id="CHEMBL9")]
        counts = collections.Counter()
        out = gca.match_ligands(ligands, {}, {"CHEMBL9": {200}}, counts)
        self.assertEqual(out, {2: (200, "chembl_id")})

    def test_both_routes_disagreeing_is_dropped_and_counted(self):
        ligands = [ligand_row(3, inchikey="KEY3", chembl_id="CHEMBL3")]
        counts = collections.Counter()
        out = gca.match_ligands(ligands, {"KEY3": 300}, {"CHEMBL3": {301}}, counts)
        self.assertEqual(out, {})
        self.assertEqual(counts["ligand_routes_disagree"], 1)

    def test_a_chembl_id_mapping_to_two_parents_is_ambiguous_and_dropped(self):
        ligands = [ligand_row(4, chembl_id="CHEMBL4")]
        counts = collections.Counter()
        out = gca.match_ligands(ligands, {}, {"CHEMBL4": {400, 401}}, counts)
        self.assertEqual(out, {})
        self.assertEqual(counts["ligand_chembl_id_ambiguous"], 1)


class TargetMatchingTest(unittest.TestCase):
    """Target matching, exercised through backfill() on a real in-memory db -
    the route from a GtoPdb row's accession set to a target row."""

    def setUp(self):
        self.conn = fake_db()

    def test_a_single_accession_row_matches_the_single_protein_record(self):
        conn = self.conn
        parent = add_molecule(conn, "CHEMBL1", inchikey="KEY1")
        add_target(conn, "CHEMBL_T1", "SINGLE PROTEIN", ["P00001"])
        summary = gca.backfill(
            conn,
            [interaction_row(1, 10, "P00001")],
            [ligand_row(1, inchikey="KEY1")])
        rows = conn.execute(
            "SELECT parent_molregno, target_chembl_id FROM gtopdb_interactions").fetchall()
        self.assertEqual(rows, [(parent, "CHEMBL_T1")])
        self.assertEqual(summary["counts"], {})

    def test_a_two_accession_row_matches_the_exact_protein_complex(self):
        conn = self.conn
        parent = add_molecule(conn, "CHEMBL2", inchikey="KEY2")
        add_target(conn, "CHEMBL_COMPLEX", "PROTEIN COMPLEX", ["P00002", "P00003"])
        gca.backfill(
            conn,
            [interaction_row(2, 20, "P00002|P00003")],
            [ligand_row(2, inchikey="KEY2")])
        rows = conn.execute(
            "SELECT parent_molregno, target_chembl_id, accessions"
            " FROM gtopdb_interactions").fetchall()
        self.assertEqual(rows, [(parent, "CHEMBL_COMPLEX", "P00002|P00003")])

    def test_a_two_accession_row_does_not_fan_out_onto_the_single_protein_subunits(self):
        conn = self.conn
        add_molecule(conn, "CHEMBL3", inchikey="KEY3")
        # only the two subunits' own SINGLE PROTEIN records exist - no
        # PROTEIN COMPLEX record carries exactly {P00004, P00005}.
        add_target(conn, "CHEMBL_SUB1", "SINGLE PROTEIN", ["P00004"])
        add_target(conn, "CHEMBL_SUB2", "SINGLE PROTEIN", ["P00005"])
        summary = gca.backfill(
            conn,
            [interaction_row(3, 30, "P00004|P00005")],
            [ligand_row(3, inchikey="KEY3")])
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM gtopdb_interactions").fetchone()[0], 0)
        self.assertEqual(summary["counts"]["rows_target_not_in_catalogue"], 1)

    def test_an_accession_carried_only_by_a_protein_family_is_not_matched(self):
        conn = self.conn
        add_molecule(conn, "CHEMBL4", inchikey="KEY4")
        add_target(conn, "CHEMBL_FAM", "PROTEIN FAMILY", ["P00006"])
        summary = gca.backfill(
            conn,
            [interaction_row(4, 40, "P00006")],
            [ligand_row(4, inchikey="KEY4")])
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM gtopdb_interactions").fetchone()[0], 0)
        self.assertEqual(summary["counts"]["rows_target_not_in_catalogue"], 1)


# ----------------------------------------------------------------- ACTION_MAP

class ActionMapTest(unittest.TestCase):
    def test_an_action_naming_an_efficacy_outranks_the_type(self):
        self.assertEqual(
            gca.ACTION_MAP[("Antagonist", "Inverse agonist")], "INVERSE AGONIST")

    def test_a_neutral_allosteric_ligand_names_no_direction(self):
        self.assertIsNone(gca.ACTION_MAP[("Allosteric modulator", "Neutral")])

    def test_an_unmapped_pair_is_stored_undirected_and_listed_in_the_manifest(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL5", inchikey="KEY5")
        add_target(conn, "CHEMBL_T5", "SINGLE PROTEIN", ["P00007"])
        summary = gca.backfill(
            conn,
            [interaction_row(5, 50, "P00007", Type="Mystery Type", Action="Mystery Action")],
            [ligand_row(5, inchikey="KEY5")])
        row = conn.execute("SELECT action_type FROM gtopdb_interactions").fetchone()
        self.assertIsNone(row[0])
        self.assertEqual(summary["unmapped_type_action"],
                          [["Mystery Type", "Mystery Action", 1]])


# ------------------------------------------------------------------ has_claim

class HasClaimTest(unittest.TestCase):
    def test_has_claim_is_1_only_at_a_pair_the_claims_table_holds(self):
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL6", inchikey="KEY6")
        p2 = add_molecule(conn, "CHEMBL7", inchikey="KEY7")
        add_target(conn, "CHEMBL_T6", "SINGLE PROTEIN", ["P00008"])
        add_claim(conn, p1, "CHEMBL_T6")
        gca.backfill(
            conn,
            [interaction_row(6, 60, "P00008"), interaction_row(7, 61, "P00008")],
            [ligand_row(6, inchikey="KEY6"), ligand_row(7, inchikey="KEY7")])
        rows = dict(conn.execute(
            "SELECT parent_molregno, has_claim FROM gtopdb_interactions"))
        self.assertEqual(rows, {p1: 1, p2: 0})


# -------------------------------------------------------------------- folding

class FoldingTest(unittest.TestCase):
    def test_two_rows_for_the_same_pair_type_action_fold_into_one(self):
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL8", inchikey="KEY8")
        add_target(conn, "CHEMBL_T8", "SINGLE PROTEIN", ["P00009"])
        gca.backfill(
            conn,
            [interaction_row(8, 80, "P00009", **{"Primary Target": "false",
                                                   "PubMed ID": "111|222"}),
             interaction_row(8, 80, "P00009", **{"Primary Target": "true",
                                                  "PubMed ID": "222|333"})],
            [ligand_row(8, inchikey="KEY8")])
        row = conn.execute(
            "SELECT n_rows, primary_target, pubmed_ids FROM gtopdb_interactions").fetchone()
        self.assertEqual(row, (2, 1, "111|222|333"))


# ------------------------------------------------------------- rerun/manifest

class RerunAndManifestTest(unittest.TestCase):
    def test_rerunning_replaces_rows_without_duplicating_them(self):
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL9", inchikey="KEY9")
        add_target(conn, "CHEMBL_T9", "SINGLE PROTEIN", ["P00010"])
        add_claim(conn, parent, "CHEMBL_T9")
        interactions = [interaction_row(9, 90, "P00010")]
        ligands = [ligand_row(9, inchikey="KEY9")]

        gca.backfill(conn, interactions, ligands)
        gca.backfill(conn, interactions, ligands)

        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM gtopdb_interactions").fetchone()[0], 1)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM build_manifest"
                         " WHERE key = 'gtopdb_actions'").fetchone()[0], 1)

        manifest = json.loads(conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'gtopdb_actions'").fetchone()[0])
        self.assertEqual(manifest["pairs_directed"], 1)
        self.assertEqual(manifest["pairs_directed_without_chembl_direction"], 1)

    def test_gtopdb_is_no_longer_listed_as_deferred_once_backfilled(self):
        # The build writes every deferred source as not assessed; the payload
        # then called GtoPdb deferred beside the file holding its data.
        conn = fake_db()
        conn.execute("INSERT INTO build_manifest VALUES('deferred_sources', ?)",
                     (json.dumps(["PDSP", "GtoPdb", "HPA"]),))
        conn.execute("INSERT INTO source_coverage VALUES('GtoPdb', 'not_assessed', NULL, 'x')")
        conn.execute("INSERT INTO source_coverage VALUES('PDSP', 'not_assessed', NULL, 'x')")
        gca.backfill(conn, [], [])
        deferred = json.loads(conn.execute(
            "SELECT value FROM build_manifest WHERE key = 'deferred_sources'").fetchone()[0])
        self.assertEqual(deferred, ["PDSP", "HPA"])
        self.assertEqual(
            dict(conn.execute("SELECT source, status FROM source_coverage")),
            {"GtoPdb": "assessed", "PDSP": "not_assessed"})
        self.assertEqual(conn.execute("SELECT release FROM source_coverage"
                                      " WHERE source = 'GtoPdb'").fetchone()[0],
                         gca.GTOPDB_VERSION)

    def test_pairs_directed_without_chembl_direction_excludes_curated_pairs(self):
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL10", inchikey="KEY10")
        add_target(conn, "CHEMBL_T10", "SINGLE PROTEIN", ["P00011"])
        add_claim(conn, parent, "CHEMBL_T10")
        add_curated_mechanism(conn, parent, "CHEMBL_T10", action_type="AGONIST")

        summary = gca.backfill(
            conn,
            [interaction_row(10, 100, "P00011")],
            [ligand_row(10, inchikey="KEY10")])

        self.assertEqual(summary["pairs_directed"], 1)
        self.assertEqual(summary["pairs_directed_without_chembl_direction"], 0)


# -------------------------------------------------------------- side effects

class NoSideEffectsTest(unittest.TestCase):
    def test_backfill_leaves_non_gtopdb_claims_targets_and_curated_mechanisms_untouched(self):
        """D18 has the backfill write its own `gtopdb` claims, but it must
        still touch nothing else: no other claim row, no target, no curated
        mechanism, and on molecules only evidence_status/gap_reason move."""
        conn = fake_db()
        parent = add_molecule(conn, "CHEMBL11", inchikey="KEY11")
        add_target(conn, "CHEMBL_T11", "SINGLE PROTEIN", ["P00012"], tax_id=9606)
        add_claim(conn, parent, "CHEMBL_T11")
        add_curated_mechanism(conn, parent, "CHEMBL_T11", action_type="AGONIST")

        before_claims = conn.execute(
            "SELECT * FROM claims WHERE claim_role <> 'gtopdb'").fetchall()
        before_targets = conn.execute("SELECT * FROM targets").fetchall()
        before_curated = conn.execute("SELECT * FROM curated_mechanisms").fetchall()
        molecule_cols = [d[0] for d in conn.execute("SELECT * FROM molecules").description]
        other_cols = [c for c in molecule_cols if c not in ("evidence_status", "gap_reason")]
        before_molecules = conn.execute(
            f"SELECT {', '.join(other_cols)} FROM molecules"
            " ORDER BY parent_molregno").fetchall()

        # A primary row here, so this exercises the case where the backfill
        # *does* write a gtopdb claim - the side-effect guarantee still has to
        # hold around that write, not just when nothing changes.
        gca.backfill(
            conn,
            [interaction_row(11, 110, "P00012", **{"Primary Target": "true"})],
            [ligand_row(11, inchikey="KEY11")])

        self.assertEqual(
            conn.execute("SELECT * FROM claims WHERE claim_role <> 'gtopdb'").fetchall(),
            before_claims)
        self.assertEqual(conn.execute("SELECT * FROM targets").fetchall(), before_targets)
        self.assertEqual(
            conn.execute("SELECT * FROM curated_mechanisms").fetchall(), before_curated)
        self.assertEqual(
            conn.execute(
                f"SELECT {', '.join(other_cols)} FROM molecules"
                " ORDER BY parent_molregno").fetchall(),
            before_molecules)


# --------------------------------------------------------------- write_claims

class WriteClaimsTest(unittest.TestCase):
    """D18: primary-target GtoPdb rows become `gtopdb`-role Supported claims."""

    def test_primary_rows_create_one_claim_per_pair_non_primary_pairs_create_none(self):
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL20", inchikey="KEY20")
        add_molecule(conn, "CHEMBL21", inchikey="KEY21")
        add_target(conn, "CHEMBL_T20", "SINGLE PROTEIN", ["P00020"], tax_id=9606)
        add_target(conn, "CHEMBL_T21", "SINGLE PROTEIN", ["P00021"], tax_id=9606)

        gca.backfill(
            conn,
            [interaction_row(20, 200, "P00020", **{"Primary Target": "true"}),
             interaction_row(21, 210, "P00021", **{"Primary Target": "false"})],
            [ligand_row(20, inchikey="KEY20"), ligand_row(21, inchikey="KEY21")])

        claims = gtopdb_claims(conn)
        self.assertEqual(len(claims), 1)
        c = claims[0]
        self.assertEqual(c["parent_molregno"], p1)
        self.assertEqual(c["target_chembl_id"], "CHEMBL_T20")
        self.assertEqual(c["claim_role"], "gtopdb")
        self.assertEqual(c["tier"], "supported")
        self.assertEqual(c["tier_reason"], "gtopdb_primary_target")
        self.assertEqual(c["curated_support"], 1)
        self.assertEqual(c["basis"], "human_direct")
        self.assertEqual(c["action_type"], "AGONIST")
        self.assertIn("GtoPdb:", c["mechanism_of_action"])
        self.assertEqual(c["conflict_action"], 0)

    def test_basis_follows_target_tax_id(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL22", inchikey="KEY22")
        add_molecule(conn, "CHEMBL23", inchikey="KEY23")
        add_target(conn, "CHEMBL_T22", "SINGLE PROTEIN", ["P00022"], tax_id=9606)
        add_target(conn, "CHEMBL_T23", "SINGLE PROTEIN", ["P00023"], tax_id=10116)

        gca.backfill(
            conn,
            [interaction_row(22, 220, "P00022", **{"Primary Target": "true"}),
             interaction_row(23, 230, "P00023", **{"Primary Target": "true"})],
            [ligand_row(22, inchikey="KEY22"), ligand_row(23, inchikey="KEY23")])

        basis = {c["target_chembl_id"]: c["basis"] for c in gtopdb_claims(conn)}
        self.assertEqual(basis, {"CHEMBL_T22": "human_direct", "CHEMBL_T23": "broader"})

    def test_new_line_at_a_pair_with_no_claim_and_has_claim_recomputed(self):
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL24", inchikey="KEY24")
        p2 = add_molecule(conn, "CHEMBL25", inchikey="KEY25")
        add_target(conn, "CHEMBL_T24", "SINGLE PROTEIN", ["P00024"], tax_id=9606)
        add_target(conn, "CHEMBL_T25", "SINGLE PROTEIN", ["P00025"], tax_id=9606)

        summary = gca.backfill(
            conn,
            [interaction_row(24, 240, "P00024", **{"Primary Target": "true"}),
             interaction_row(25, 250, "P00025", **{"Primary Target": "false"})],
            [ligand_row(24, inchikey="KEY24"), ligand_row(25, inchikey="KEY25")])

        self.assertEqual(summary["gtopdb_claim_effect"], {"new_line": 1})
        has_claim = dict(conn.execute(
            "SELECT parent_molregno, has_claim FROM gtopdb_interactions"))
        self.assertEqual(has_claim, {p1: 1, p2: 0})

    def test_primary_row_with_no_mapped_direction_still_makes_a_supported_claim(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL26", inchikey="KEY26")
        add_target(conn, "CHEMBL_T26", "SINGLE PROTEIN", ["P00026"], tax_id=9606)

        gca.backfill(
            conn,
            [interaction_row(26, 260, "P00026", **{"Primary Target": "true",
                                                     "Type": "Allosteric modulator",
                                                     "Action": "Neutral"})],
            [ligand_row(26, inchikey="KEY26")])

        claims = gtopdb_claims(conn)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["tier"], "supported")
        self.assertIsNone(claims[0]["action_type"])

    def test_opposing_primary_rows_at_one_pair_set_conflict_action(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL27", inchikey="KEY27")
        add_target(conn, "CHEMBL_T27", "SINGLE PROTEIN", ["P00027"], tax_id=9606)

        gca.backfill(
            conn,
            [interaction_row(27, 270, "P00027", **{"Primary Target": "true",
                                                     "Type": "Agonist", "Action": "Agonist"}),
             interaction_row(27, 270, "P00027", **{"Primary Target": "true",
                                                     "Type": "Antagonist",
                                                     "Action": "Antagonist"})],
            [ligand_row(27, inchikey="KEY27")])

        claims = gtopdb_claims(conn)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["conflict_action"], 1)
        self.assertEqual(claims[0]["action_type"], "AGONIST / ANTAGONIST")

    def test_preliminary_only_molecule_becomes_has_supported(self):
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL28", inchikey="KEY28")
        add_target(conn, "CHEMBL_T28", "SINGLE PROTEIN", ["P00028"], tax_id=9606)
        add_claim(conn, p1, "CHEMBL_T28", tier="preliminary")

        summary = gca.backfill(
            conn,
            [interaction_row(28, 280, "P00028", **{"Primary Target": "true"})],
            [ligand_row(28, inchikey="KEY28")])

        self.assertEqual(summary["gtopdb_claim_effect"], {"preliminary_to_supported": 1})
        status, reason = conn.execute(
            "SELECT evidence_status, gap_reason FROM molecules"
            " WHERE parent_molregno = ?", (p1,)).fetchone()
        self.assertEqual(status, "has_supported")
        self.assertIsNone(reason)

    def test_evidence_status_rederivation_matches_build_write_evidence_status(self):
        """The re-derivation the backfill runs must be exactly what
        build._write_evidence_status gives on the same claims - not a
        parallel copy of its logic that could drift from it."""
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL29", inchikey="KEY29")
        add_target(conn, "CHEMBL_T29", "SINGLE PROTEIN", ["P00029"], tax_id=9606)
        add_claim(conn, p1, "CHEMBL_T29", tier="preliminary")

        gca.backfill(
            conn,
            [interaction_row(29, 290, "P00029", **{"Primary Target": "true"})],
            [ligand_row(29, inchikey="KEY29")])
        after_backfill = conn.execute(
            "SELECT evidence_status, gap_reason FROM molecules"
            " WHERE parent_molregno = ?", (p1,)).fetchone()

        from cohort import build as build_mod
        conn.execute("UPDATE molecules SET evidence_status = NULL, gap_reason = NULL")
        build_mod._write_evidence_status(conn)
        after_direct = conn.execute(
            "SELECT evidence_status, gap_reason FROM molecules"
            " WHERE parent_molregno = ?", (p1,)).fetchone()

        self.assertEqual(after_backfill, ("has_supported", None))
        self.assertEqual(after_backfill, after_direct)

    def test_rerunning_backfill_twice_does_not_duplicate_or_double_count(self):
        conn = fake_db()
        p1 = add_molecule(conn, "CHEMBL30", inchikey="KEY30")
        add_target(conn, "CHEMBL_T30", "SINGLE PROTEIN", ["P00030"], tax_id=9606)
        interactions = [interaction_row(30, 300, "P00030", **{"Primary Target": "true"})]
        ligands = [ligand_row(30, inchikey="KEY30")]

        first = gca.backfill(conn, interactions, ligands)
        second = gca.backfill(conn, interactions, ligands)

        # Rerunning must not treat the first run's own gtopdb claim as a
        # ChEMBL claim: the pair is still a "new line" the second time.
        self.assertEqual(first["gtopdb_claim_effect"], {"new_line": 1})
        self.assertEqual(second["gtopdb_claim_effect"], {"new_line": 1})
        self.assertEqual(
            conn.execute(
                "SELECT COUNT(*) FROM claims WHERE claim_role = 'gtopdb'").fetchone()[0],
            1)
        has_claim = dict(conn.execute(
            "SELECT parent_molregno, has_claim FROM gtopdb_interactions"))
        self.assertEqual(has_claim, {p1: 1})


# --------------------------------------------------------------- export split

def _payload(path, name):
    text = path.read_text()
    m = re.match(r"^(?:// .*\n)+const " + name + r" = (.*);\n$", text, re.S)
    return json.loads(m.group(1)), text


class ExportSplitTest(unittest.TestCase):
    """Everything GtoPdb contributes leaves the export in gtopdb.data.js, under
    its own licence, and graph.data.js states statuses and counts from ChEMBL's
    claims alone - so the ChEMBL file holds nothing of GtoPdb's and, alone, is
    the ChEMBL-only page."""

    def _export(self, conn):
        from cohort import export as export_mod
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            disk = sqlite3.connect(str(d / "cohort.db"))
            conn.commit()  # backup() retries for ever against an open write
            conn.backup(disk)
            disk.close()
            export_mod.export(db_path=d / "cohort.db", out_dir=d / "viz", backup=False)
            return (_payload(d / "viz" / "graph.data.js", "COHORT_DATA"),
                    _payload(d / "viz" / "gtopdb.data.js", "COHORT_GTOPDB"))

    def _db(self):
        conn = fake_db()
        a = add_molecule(conn, "CHEMBL30", inchikey="KEY30")
        b = add_molecule(conn, "CHEMBL31", inchikey="KEY31")
        add_target(conn, "CHEMBL_T30", "SINGLE PROTEIN", ["P00030"], tax_id=9606)
        add_claim(conn, a, "CHEMBL_T30", tier="preliminary")
        add_claim(conn, b, "CHEMBL_T30", tier="supported")
        gca.backfill(
            conn,
            [interaction_row(30, 300, "P00030", **{"Primary Target": "true"}),
             interaction_row(31, 300, "P00030", Type="Antagonist", Action="Antagonist")],
            [ligand_row(30, inchikey="KEY30"), ligand_row(31, inchikey="KEY31")])
        return conn, a, b

    def test_gtopdb_claims_actions_and_status_changes_travel_in_their_own_file(self):
        conn, a, b = self._db()
        (graph, graph_text), (gtp, gtp_text) = self._export(conn)

        strings = graph["strings"]
        roles = {strings[c[graph["fields"]["claims"].index("role")]] for c in graph["claims"]}
        self.assertEqual(roles, {"binding"})
        self.assertNotIn("gtopdb", strings)
        self.assertNotIn("gtopdb", graph)
        mol = {m[0]: dict(zip(graph["fields"]["molecules"], m)) for m in graph["molecules"]}
        self.assertEqual(strings[mol[a]["evidence_status"]], "has_preliminary")
        self.assertEqual(mol[a]["n_claims_supported"], 0)
        self.assertEqual(strings[mol[b]["evidence_status"]], "has_supported")

        g_strings = gtp["strings"]
        self.assertEqual(len(gtp["claims"]), 1)
        claim = dict(zip(gtp["fields"]["claims"], gtp["claims"][0]))
        self.assertEqual(g_strings[claim["role"]], "gtopdb")
        self.assertEqual(claim["molecule"], a)
        self.assertEqual(len(gtp["actions"]), 2)
        self.assertEqual(gtp["status"], {str(a): ["has_supported", None]})
        self.assertIn("ODbL", gtp["licence"])
        self.assertIn("ODbL", gtp_text.split("const ")[0])
        self.assertIn("no GtoPdb data", graph["licence"])
        self.assertEqual(graph["counts"]["claims_drawable"], 2)
        # The page pairs the two files by this stamp.
        self.assertEqual(gtp["generated"], graph["generated"])

    def test_the_local_chembl_path_stays_out_of_the_served_meta(self):
        conn, _, _ = self._db()
        conn.execute("INSERT INTO build_manifest (key, value) VALUES"
                     " ('chembl_path', '/mnt/data/chembl/chembl.db'),"
                     " ('chembl_release', 'chembl_37')")
        (graph, graph_text), _ = self._export(conn)
        self.assertNotIn("chembl_path", graph["meta"])
        self.assertNotIn("/mnt/data", graph_text)
        self.assertEqual(graph["meta"]["chembl_release"], "chembl_37")

    def test_every_data_file_states_its_licence_as_an_adaptation_with_links(self):
        # Share-alike: the adaptation is licensed by whoever made it, under the
        # same licence, saying it was changed and linking the text - in the
        # file itself, shards included (docs/HOSTING-REVIEW.md, second pass).
        from cohort import export as export_mod
        conn, a, _ = self._db()
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            disk = sqlite3.connect(str(d / "cohort.db"))
            conn.commit()
            conn.backup(disk)
            disk.close()
            export_mod.export(db_path=d / "cohort.db", out_dir=d / "viz", backup=False)
            export_mod._dump_shard(d / "viz" / "evidence", a, {"molecule": a})
            heads = {p.name: p.read_text().split("const ")[0].split("registerEvidence(")[0]
                     for p in [d / "viz" / "graph.data.js", d / "viz" / "gtopdb.data.js",
                               d / "viz" / "evidence" / f"{a}.js"]}
        self.assertEqual(len(heads), 3)
        for name, head in heads.items():
            if name == "gtopdb.data.js":
                self.assertIn("made available here under the", head)
                self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", head)
                self.assertIn("https://creativecommons.org/licenses/by-sa/4.0/", head)
            else:
                self.assertIn("changes were made", head, name)
                self.assertIn("licensed under CC BY-SA 3.0, "
                              "https://creativecommons.org/licenses/by-sa/3.0/", head, name)

    def test_the_trial_fetch_dates_travel_so_the_page_can_state_them(self):
        conn, _, _ = self._db()
        (graph, _), _ = self._export(conn)
        self.assertIsNone(graph["trials_fetched"])          # never fetched: says so
        conn.executemany("INSERT INTO trial_status(nct_id, overall_status, fetched_at)"
                         " VALUES (?, 'COMPLETED', ?)",
                         [("NCT1", "2026-10-09T23:00:00+00:00"),
                          ("NCT2", "2026-10-10T18:01:40+00:00")])
        (graph, _), _ = self._export(conn)
        self.assertEqual(graph["trials_fetched"],
                         ["2026-10-09T23:00:00+00:00", "2026-10-10T18:01:40+00:00"])

    def test_a_stored_status_the_shared_rule_would_not_give_stops_the_export(self):
        from cohort import common
        conn, a, _ = self._db()
        conn.execute("UPDATE molecules SET evidence_status = 'has_preliminary'"
                     " WHERE parent_molregno = ?", (a,))
        with self.assertRaises(common.PolicyError):
            self._export(conn)


if __name__ == "__main__":
    unittest.main()
