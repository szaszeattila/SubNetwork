"""Tests for the generated ``## Status`` block in CLAUDE.md.

The point of this file is the first test in it. Every other figure in that
section is computed by the pipeline and was always exact; the ones a human
transcribed drifted, and by 2026-09-17 four of them were wrong at once. A
proofread fixes that for one commit. A test fixes it for good, which is why
staleness here is a failure rather than something review has to notice.

The rest are unit tests over the pure parts: that a rewrite touches nothing
outside the markers, that a missing input raises instead of writing a zero,
and that the two sentences with a branch in them say the right thing on both
sides of it.

Run with: python3 -m unittest discover -s tests
"""

import pathlib
import shutil
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from cohort import common, status  # noqa: E402


def _fake_figures(**overrides):
    """A complete figure set, so a render test exercises one branch at a time."""
    fig = {
        "built_at": "2026-09-16T22:24:27", "built_date": "2026-09-16",
        "chembl_release": "chembl_37",
        "selection_policy": "cohort1-selection", "selection_version": "2.0.0",
        "evidence_policy": "cohort1-evidence", "evidence_version": "1.0.0",
        "molecules": 1331, "targets": 2577, "claims": 80459,
        "observations": 210157,
        "in_cohort": 1326, "outside_cohort": 5,
        "route_atc_n": 171, "route_indication": 782, "route_both": 373,
        "seeds": 28, "seeds_admitted": 23, "seed_only": 5, "listed_only": 0,
        "supported_claims": 2411, "supported_curated": 1045,
        "supported_replicated": 1366, "supported_both": 0,
        "supported_pairs": 1962,
        "has_supported": 845, "has_preliminary": 151, "broader_only": 38,
        "limited_only": 37, "no_evidence": 260,
        "studies": 14548, "counted": 41682, "bounds": 51036,
        "conditional": 1727, "organism_format": 13184,
        "documented_exclusion": 3, "scanned": 803018,
        "checks_total": 15, "checks_passed": 15,
        "wiki_molecules": 1051, "single_component": 2265, "wiki_targets": 1280,
        "multi_component": 310, "no_component": 2,
        "multi_single_protein": 1, "multi_single_protein_accessions": 3,
        "wiki_multi": 280, "multi_no_article": 30, "multi_unreviewed": 0,
        "payload_bytes": 4390047, "gtopdb_bytes": 129332, "drugcentral_bytes": 31000, "shard_bytes": 71652390, "shard_count": 1176,
        "python_tests": 219, "viewer_cohort_tests": 182,
        "viewer_legacy_tests": 222, "viewer_tests": 404,
        "harness_tests": 7, "node_tests": 411,
        "sim_labelled": 395, "sim_classes": 64, "sim_scoreable": 217,
        "sim_unanswerable": 178, "sim_top1": 0.359447, "sim_mrr": 0.498516,
    }
    fig.update(overrides)
    return fig


class StatusBlockIsCurrentTest(unittest.TestCase):
    """The one that stops the drift coming back."""

    def test_claude_md_status_block_matches_the_active_build(self):
        if not common.COHORT_DB.exists():
            self.skipTest(
                f"no cohort database at {common.COHORT_DB}; "
                f"build one to check the status block")
        if not status.GRAPH_DATA.exists():
            self.skipTest(
                f"no export at {status.GRAPH_DATA}; "
                f"run scripts/export_cohort.py to check the status block")
        if shutil.which("node") is None:
            self.skipTest("node is not on PATH, so the viewer suites cannot be counted")

        text = status.DOC.read_text(encoding="utf-8")
        self.assertEqual(
            status.current_block(text),
            status.rendered(),
            "CLAUDE.md's ## Status block is stale. Refresh it with\n"
            "    python3 scripts/cohort_report.py --write-status\n"
            "and commit the result. Nothing outside the markers is touched.",
        )


class ReplaceBlockTest(unittest.TestCase):
    """A rewrite owns the block and nothing else."""

    DOC = (
        "# Title\n\nprose before\n\n"
        + status.BEGIN % "cohort-status" + "\n"
        + "old body\n"
        + status.END % "cohort-status" + "\n\nprose after\n"
    )

    def test_everything_outside_the_markers_is_byte_identical(self):
        out = status.replace_block(self.DOC, "new body")
        self.assertIn("prose before", out)
        self.assertIn("prose after", out)
        self.assertEqual(out.split(status.BEGIN % "cohort-status")[0],
                         self.DOC.split(status.BEGIN % "cohort-status")[0])
        self.assertEqual(out.split(status.END % "cohort-status")[1],
                         self.DOC.split(status.END % "cohort-status")[1])

    def test_the_body_is_replaced(self):
        out = status.replace_block(self.DOC, "new body")
        self.assertEqual(status.current_block(out), "new body")
        self.assertNotIn("old body", out)

    def test_an_empty_block_can_be_filled(self):
        # How the markers first enter the document: two adjacent lines.
        empty = (status.BEGIN % "cohort-status" + "\n"
                 + status.END % "cohort-status" + "\n")
        self.assertEqual(status.current_block(empty), "")
        self.assertEqual(
            status.current_block(status.replace_block(empty, "filled")), "filled")

    def test_rewriting_is_idempotent(self):
        once = status.replace_block(self.DOC, "new body")
        self.assertEqual(status.replace_block(once, "new body"), once)

    def test_a_document_with_no_markers_raises(self):
        with self.assertRaises(status.StatusError):
            status.current_block("# Title\n\nno markers here\n")


class MissingInputTest(unittest.TestCase):
    """Never write a zero for something that could not be measured."""

    def test_a_missing_database_raises_rather_than_reporting_nothing(self):
        with self.assertRaises(status.StatusError) as caught:
            status.db_figures(common.ROOT / "db" / "does-not-exist.db")
        self.assertIn("no cohort database", str(caught.exception))


class RenderTest(unittest.TestCase):
    """The sentences that change shape with the data."""

    def test_no_claim_carrying_both_is_written_only_while_it_is_true(self):
        text = status.render_status(_fake_figures(supported_both=0))
        self.assertIn("with no claim carrying both", text)

    def test_a_claim_carrying_both_routes_is_reported_instead_of_denied(self):
        text = status.render_status(
            _fake_figures(supported_both=7, supported_claims=2418))
        self.assertNotIn("with no claim carrying both", text)
        self.assertIn("7 by both", text)

    def test_the_odd_single_protein_states_its_own_accession_count(self):
        # The figure that was wrong in the hand-written prose: it said two.
        text = status.render_status(
            _fake_figures(multi_single_protein=1,
                          multi_single_protein_accessions=3))
        self.assertIn("SINGLE PROTEIN carrying 3 accessions", text)

    def test_a_build_with_no_odd_single_protein_says_nothing_about_one(self):
        text = status.render_status(_fake_figures(multi_single_protein=0))
        self.assertNotIn("SINGLE PROTEIN carrying", text)

    def test_multi_component_links_are_counted_and_unreviewed_ones_named(self):
        text = " ".join(status.render_status(_fake_figures()).split())
        self.assertIn("So do **280 of the 310 multi-component targets**", text)
        self.assertIn("30 were reviewed and have no article of their own.", text)
        self.assertNotIn("not yet reviewed", text)
        text = " ".join(status.render_status(
            _fake_figures(multi_unreviewed=4)).split())
        self.assertIn("and 4 are not yet reviewed and stay unlinked.", text)

    def test_lent_human_articles_are_counted_only_where_the_column_was_written(self):
        text = " ".join(status.render_status(_fake_figures(wiki_human_lent=653)).split())
        self.assertIn("A further 653 non-human records with no article of their own", text)
        self.assertNotIn("A further", status.render_status(_fake_figures()))

    def test_targets_with_no_accession_are_mentioned_only_when_there_are_some(self):
        self.assertIn("no accession at all",
                      status.render_status(_fake_figures(no_component=2)))
        self.assertNotIn("no accession at all",
                         status.render_status(_fake_figures(no_component=0)))

    def test_headline_counts_carry_thousands_separators(self):
        text = status.render_status(_fake_figures())
        self.assertIn("**1,331 catalogue entries · 2,577 targets · "
                      "80,459 claims · 210,157 observations**", text)

    def test_every_paragraph_wraps_inside_the_documents_width(self):
        # The headline is one bold run and is deliberately not broken -- the
        # hand-written version overran too. Everything else wraps, so a
        # refresh never shows up as a reflow of the whole block.
        for line in status.render_status(_fake_figures()).splitlines():
            if line.startswith("**") and line.endswith("observations**"):
                continue
            self.assertLessEqual(
                len(line), status.WRAP,
                f"generated line is wider than the document wraps: {line!r}")

    def test_the_headline_counts_stay_on_one_line(self):
        headline = [ln for ln in status.render_status(_fake_figures()).splitlines()
                    if ln.startswith("**1,331 catalogue")]
        self.assertEqual(len(headline), 1)


class MegabytesTest(unittest.TestCase):
    """1 MB is 1e6 bytes here, which is what the hand-written figures used."""

    def test_the_payload_reproduces_the_figure_the_prose_had(self):
        self.assertEqual(status._mb(4390047), "4.39 MB")

    def test_a_large_size_drops_to_one_decimal(self):
        self.assertEqual(status._mb(71652390), "71.7 MB")


class ValidationGateTest(unittest.TestCase):
    """A failed build does not get a status block written about it."""

    def test_a_build_with_a_failing_check_refuses_to_be_described(self):
        import sqlite3
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "cohort1.db"
            db = sqlite3.connect(path)
            db.executescript(
                "CREATE TABLE build_manifest (key TEXT, value TEXT);"
                "INSERT INTO build_manifest VALUES ('built_at','2026-09-16T00:00:00'),"
                " ('chembl_release','chembl_37'),"
                " ('selection_policy','{\"policy_id\":\"s\",\"version\":\"1\"}'),"
                " ('evidence_policy','{\"policy_id\":\"e\",\"version\":\"1\"}');"
                "CREATE TABLE molecules (in_cohort INT, is_seed INT,"
                " admission_reason TEXT, evidence_status TEXT, wikipedia_url TEXT);"
                "CREATE TABLE targets (chembl_id TEXT, n_components INT,"
                " target_type TEXT, wikipedia_url TEXT);"
                "CREATE TABLE claims (basis TEXT, tier TEXT, curated_support INT,"
                " multiple_study_support INT, parent_molregno INT,"
                " target_chembl_id TEXT);"
                "CREATE TABLE observations (study_key TEXT, counted INT,"
                " value_status TEXT);"
                "CREATE TABLE exclusion_summary (reason TEXT, n_rows INT);"
                "CREATE TABLE validation (check_name TEXT, result TEXT);"
                "INSERT INTO validation VALUES ('a','PASS'),('b','FAIL');"
            )
            db.commit()
            db.close()

            with self.assertRaises(status.StatusError) as caught:
                status.db_figures(path)
            self.assertIn("build checks did not pass", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
