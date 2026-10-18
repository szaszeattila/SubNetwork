"""Offline tests for scripts/resolve_cohort_wikipedia.py.

These lock in the rule the whole script exists to enforce (CLAUDE.md
invariant 15: resolve external links by identifier, never by name) and the
operational guarantees the task asked for: an ambiguous Wikidata match is
dropped rather than guessed, a multi-component target is queried only through
its reviewed Wikidata item, a failed lookup is distinguished from "no article
exists", and a rerun never disturbs an already-resolved row.

No network access: `_wikidata_get` - the one seam that ever calls
`requests.get` - is stubbed out in every test. The stub inspects the
rendered SPARQL text for a quoted identifier literal, which doubles as the
"name is never a matching key" check: a query that embedded a molecule's
name rather than its ChEMBL ID/InChIKey would simply never match the stub's
data.

Run with: python3 -m unittest discover -s tests
"""

import itertools
import json
import re
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_wikipedia as rcw  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

_molregno = itertools.count(1)


def fake_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def add_molecule(conn, chembl_id, inchikey=None, wikipedia_url=None, pref_name=None):
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, pref_name, in_cohort,"
        " is_seed, route_atc_n, route_indication, admission_reason, inchikey,"
        " wikipedia_url) VALUES (?,?,?,0,0,0,0,'seed_only',?,?)",
        (next(_molregno), chembl_id, pref_name, inchikey, wikipedia_url))


def add_target(conn, chembl_id, accessions, wikipedia_url=None,
                target_type="SINGLE PROTEIN"):
    conn.execute(
        "INSERT INTO targets(chembl_id, pref_name, target_type, n_components,"
        " wikipedia_url) VALUES (?,?,?,?,?)",
        (chembl_id, chembl_id, target_type, len(accessions), wikipedia_url))
    for accession in accessions:
        conn.execute(
            "INSERT INTO target_components(target_chembl_id, accession) VALUES (?,?)",
            (chembl_id, accession))


def stub(article_map=None, fail_keys=(), log=None, genes=None):
    """A fake `_wikidata_get`. `article_map` maps a literal that must appear
    in the rendered query (quoted, as sparql_literal would render it) to the
    set of article URLs to return for whichever `?key` row matched it, or to
    {via: set of URLs} where the query binds ?via (the target query's
    "protein" or "gene"). `genes` maps a target key to how many genes its
    protein item names, for the gene-count query (1 where not given).
    `fail_keys` are literals that raise WikidataError instead - simulating an
    endpoint failure distinct from a query that legitimately found nothing."""
    article_map, genes = article_map or {}, genes or {}

    def _get(query):
        if log is not None:
            log.append(query)
        for needle in fail_keys:
            if f'"{needle}"' in query:
                raise rcw.WikidataError("stubbed failure")
        if "COUNT(DISTINCT ?gene)" in query:
            return {"results": {"bindings": [
                {"key": {"value": k}, "genes": {"value": str(genes.get(k, 1))}}
                for k in re.findall(r'\("([^"]+)" "[^"]+"\)', query)]}}
        bindings = []
        for needle, articles in article_map.items():
            if f'"{needle}"' in query:
                by_via = articles if isinstance(articles, dict) else {None: articles}
                for via, urls in by_via.items():
                    for article in urls:
                        b = {"key": {"value": needle}, "article": {"value": article}}
                        if via:
                            b["via"] = {"value": via}
                        bindings.append(b)
        return {"results": {"bindings": bindings}}

    return _get


def drugbox_stub(links=None, pages=None, log=None, fail=False):
    """A fake `_wikipedia_get` for the infobox route: `links` maps a ChEMBL
    compound URL to the article titles carrying it, as the external-link index
    lists them, and `pages` maps a title to its wikitext."""
    links, pages = links or {}, pages or {}

    def _get(params):
        if log is not None:
            log.append(params)
        if fail:
            raise rcw.WikidataError("stubbed failure")
        if params.get("list") == "exturlusage":
            rows = [{"title": t, "url": url} for url, titles in links.items()
                    if params["euprotocol"] == "https"
                    and url.startswith(params["euquery"]) for t in titles]
            return {"query": {"exturlusage": rows}}
        return {"query": {"pages": [
            {"title": t, "revisions": [{"slots": {"main": {"content": pages[t]}}}]}
            if t in pages else {"title": t, "missing": True}
            for t in params["titles"].split("|")]}}
    return _get


def drugbox(chembl=None, inchikey=None, template="Infobox drug"):
    lines = [f"{{{{{template}", "| image = x.png"]
    if chembl:
        lines.append(f"| ChEMBL = {chembl}")
    if inchikey:
        lines.append(f"| StdInChIKey = {inchikey}")
    return "\n".join(lines) + "\n}}\n'''Drug''' is a drug.{{cite journal | title = T}}"


def chembl_url(chembl_id):
    return "www.ebi.ac.uk/chembl/explore/compound/" + chembl_id.replace("CHEMBL", "ChEMBL")


class MoleculeResolutionTest(unittest.TestCase):
    def setUp(self):
        # A molecule Wikidata finds no article for goes on to the infobox
        # route; here it finds none there either.
        self.enterContext(mock.patch.object(rcw, "_wikipedia_get", drugbox_stub()))

    def test_unambiguous_match_is_written(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL113", inchikey="RYYVLZVUVIJVGH-UHFFFAOYSA-N")
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL113": {"https://en.wikipedia.org/wiki/Caffeine"}})):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL113'").fetchone()[0],
            "https://en.wikipedia.org/wiki/Caffeine")

    def test_ambiguous_match_is_written_as_null(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL999", inchikey="SOMEKEY")
        with mock.patch.object(rcw, "_wikidata_get", stub({
                "CHEMBL999": {"https://en.wikipedia.org/wiki/A",
                              "https://en.wikipedia.org/wiki/B"}})):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL999'").fetchone()[0])

    def test_name_is_never_used_as_a_matching_key(self):
        # An article keyed only on the molecule's pref_name must never match:
        # the query embeds chembl_id and inchikey literals, not the name.
        conn = fake_db()
        add_molecule(conn, "CHEMBL1", inchikey="NOMATCHKEY", pref_name="Caffeine")
        log = []
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"Caffeine": {"https://en.wikipedia.org/wiki/Caffeine"}}, log=log)):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(summary["no_article"], 1)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL1'").fetchone()[0])
        # And the rendered query really did carry the identifiers, not the name.
        self.assertTrue(any('"CHEMBL1"' in q for q in log))
        self.assertTrue(any('"NOMATCHKEY"' in q for q in log))
        self.assertFalse(any("Caffeine" in q for q in log))

    def test_failed_lookup_is_distinguished_from_no_article(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL2", inchikey="KEY2")
        with mock.patch.object(rcw, "_wikidata_get", stub(fail_keys={"CHEMBL2"})):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["no_article"], 0)
        self.assertEqual(summary["resolved"], 0)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL2'").fetchone()[0])

    def test_dry_run_writes_nothing(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL3", inchikey="KEY3")
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL3": {"https://en.wikipedia.org/wiki/X"}})):
            summary = rcw.resolve_molecules(conn, dry_run=True)
        self.assertEqual(summary["resolved"], 1)  # it did find a match...
        self.assertIsNone(  # ...but nothing was written
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL3'").fetchone()[0])

    def test_rerun_does_not_disturb_an_already_resolved_row(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL4", inchikey="KEY4")
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL4": {"https://en.wikipedia.org/wiki/First"}})):
            rcw.resolve_molecules(conn)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL4'").fetchone()[0],
            "https://en.wikipedia.org/wiki/First")

        # Second run, no --refresh: the item's article "changes" upstream,
        # but the row is no longer a candidate, so it must not move.
        log = []
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL4": {"https://en.wikipedia.org/wiki/Second"}}, log=log)):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(log, [])
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL4'").fetchone()[0],
            "https://en.wikipedia.org/wiki/First")

    def test_refresh_re_queries_an_already_resolved_row(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL5", inchikey="KEY5",
                     wikipedia_url="https://en.wikipedia.org/wiki/Old")
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL5": {"https://en.wikipedia.org/wiki/New"}})):
            summary = rcw.resolve_molecules(conn, refresh=True)
        self.assertEqual(summary["queried"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = 'CHEMBL5'").fetchone()[0],
            "https://en.wikipedia.org/wiki/New")


PBF509_KEY = "ATFXVNUWQOXRRU-UHFFFAOYSA-N"
TAMINADENANT = "https://en.wikipedia.org/wiki/Taminadenant"


class InfoboxRouteTest(unittest.TestCase):
    """PBF-509's article, Taminadenant, sits on a Wikidata item with no
    statements; its drugbox names CHEMBL3694769 and the InChIKey."""

    def resolve(self, conn, links, pages, wikidata=None, log=None, **kw):
        with mock.patch.object(rcw, "_wikidata_get", stub(wikidata)), \
             mock.patch.object(rcw, "_wikipedia_get", drugbox_stub(links, pages, log)):
            return rcw.resolve_molecules(conn, **kw)

    def url(self, conn, chembl_id):
        return conn.execute("SELECT wikipedia_url FROM molecules WHERE chembl_id = ?",
                            (chembl_id,)).fetchone()[0]

    def test_pbf509_reaches_taminadenant_through_its_drugbox(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL3694769", inchikey=PBF509_KEY, pref_name="PBF-509")
        summary = self.resolve(conn, {chembl_url("CHEMBL3694769"): ["Taminadenant"]},
                               {"Taminadenant": drugbox("3694769", PBF509_KEY)})
        self.assertEqual((summary["resolved"], summary["by_infobox"]), (1, 1))
        self.assertEqual(self.url(conn, "CHEMBL3694769"), TAMINADENANT)

    def test_a_stereo_disagreement_keeps_the_skeleton(self):
        # Varenicline: ChEMBL's parent is drawn with stereo, the article flat.
        conn = fake_db()
        add_molecule(conn, "CHEMBL1076903", inchikey="JQSHBVHOMNKWFT-DTORHVGOSA-N")
        self.resolve(conn, {chembl_url("CHEMBL1076903"): ["Varenicline"]},
                     {"Varenicline": drugbox("1076903", "JQSHBVHOMNKWFT-UHFFFAOYSA-N")})
        self.assertEqual(self.url(conn, "CHEMBL1076903"),
                         "https://en.wikipedia.org/wiki/Varenicline")

    def test_an_infobox_whose_structure_differs_is_refused(self):
        # "Nitrous oxide (medication)" carries oxygen's ChEMBL ID.
        conn = fake_db()
        add_molecule(conn, "CHEMBL1234886", inchikey="MYMOFIZGZYHOMD-UHFFFAOYSA-N")
        summary = self.resolve(
            conn, {chembl_url("CHEMBL1234886"): ["Nitrous oxide (medication)"]},
            {"Nitrous oxide (medication)": drugbox("1234886", "GQPLMRYTRLFLPF-UHFFFAOYSA-N")})
        self.assertEqual((summary["resolved"], summary["refused"]), (0, 1))
        self.assertIsNone(self.url(conn, "CHEMBL1234886"))

    def test_a_link_outside_an_infobox_is_not_a_claim_about_the_article(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL3694769", inchikey=PBF509_KEY)
        text = (drugbox("1", None) + "\n* [https://www.ebi.ac.uk/chembl/explore/"
                "compound/ChEMBL3694769 PBF-509]")
        summary = self.resolve(conn, {chembl_url("CHEMBL3694769"): ["Adenosine A2A receptor"]},
                               {"Adenosine A2A receptor": text})
        self.assertEqual((summary["resolved"], summary["refused"]), (0, 1))

    def test_a_prefix_of_the_id_is_not_the_id(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL369476", inchikey=PBF509_KEY)
        summary = self.resolve(conn, {chembl_url("CHEMBL3694769"): ["Taminadenant"]},
                               {"Taminadenant": drugbox("3694769", PBF509_KEY)})
        self.assertEqual(summary["resolved"], 0)

    def test_two_articles_are_ambiguous(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL373742", inchikey="KBZOIRJILGZLEJ-LGYYRGKSSA-N")
        box = drugbox("CHEMBL373742", "KBZOIRJILGZLEJ-LGYYRGKSSA-N")
        summary = self.resolve(
            conn, {chembl_url("CHEMBL373742"): ["Vasopressin", "Vasopressin (medication)"]},
            {"Vasopressin": box, "Vasopressin (medication)": box})
        self.assertEqual((summary["resolved"], summary["ambiguous"]), (0, 1))

    def test_a_molecule_without_a_key_matches_on_the_id_and_a_chembox_counts(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL1201438")
        box = ("{{Chembox\n| Section1 = {{Chembox Identifiers\n| ChEMBL = 1201438\n"
               "| ChEMBL_Ref = {{ebicite|x}}\n}}\n}}")
        self.resolve(conn, {chembl_url("CHEMBL1201438"): ["Interleukin 2"]},
                     {"Interleukin 2": box})
        self.assertEqual(self.url(conn, "CHEMBL1201438"),
                         "https://en.wikipedia.org/wiki/Interleukin_2")

    def test_wikidata_answers_first_and_is_never_overruled(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL1", inchikey="AAAAAAAAAAAAAA-UHFFFAOYSA-N")
        add_molecule(conn, "CHEMBL2", inchikey="BBBBBBBBBBBBBB-UHFFFAOYSA-N")
        log = []
        summary = self.resolve(
            conn, {chembl_url("CHEMBL1"): ["Other"], chembl_url("CHEMBL2"): ["Other"]},
            {"Other": drugbox("1") + drugbox("2")},
            wikidata={"CHEMBL1": {"https://en.wikipedia.org/wiki/One"},
                      "CHEMBL2": {"https://en.wikipedia.org/wiki/A",
                                  "https://en.wikipedia.org/wiki/B"}}, log=log)
        self.assertEqual(self.url(conn, "CHEMBL1"), "https://en.wikipedia.org/wiki/One")
        # An ambiguous Wikidata answer stays a refusal, not a cue to look elsewhere.
        self.assertIsNone(self.url(conn, "CHEMBL2"))
        self.assertEqual(summary["ambiguous"], 1)
        self.assertEqual(log, [])

    def test_a_salt_forms_id_is_never_read(self):
        # Ethyl linoleate's forms include deulinoleate ethyl, a different drug.
        conn = fake_db()
        add_molecule(conn, "CHEMBL2106238", inchikey="FMMOOAYVCKXGMF-MURFETPASA-N")
        conn.execute("INSERT INTO molecule_forms(parent_molregno, molregno, chembl_id,"
                     " is_parent) SELECT parent_molregno, 999, 'CHEMBL5095415', 0"
                     " FROM molecules WHERE chembl_id = 'CHEMBL2106238'")
        summary = self.resolve(
            conn, {chembl_url("CHEMBL5095415"): ["Deulinoleate ethyl"]},
            {"Deulinoleate ethyl": drugbox("5095415", "FMMOOAYVCKXGMF-MURFETPASA-N")})
        self.assertEqual(summary["resolved"], 0)

    def test_a_wikipedia_failure_is_a_failure_not_no_article(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL3694769", inchikey=PBF509_KEY)
        with mock.patch.object(rcw, "_wikidata_get", stub()), \
             mock.patch.object(rcw, "_wikipedia_get", drugbox_stub(fail=True)):
            summary = rcw.resolve_molecules(conn)
        self.assertEqual((summary["failed"], summary["no_article"]), (1, 0))

    def test_the_index_is_read_by_identifier_prefix_never_by_title(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL3694769", inchikey=PBF509_KEY, pref_name="PBF-509")
        log = []
        self.resolve(conn, {chembl_url("CHEMBL3694769"): ["Taminadenant"]},
                     {"Taminadenant": drugbox("3694769", PBF509_KEY)}, log=log)
        searches = [p for p in log if p.get("list")]
        self.assertTrue(searches)
        self.assertTrue(all(p["list"] == "exturlusage"
                            and p["euquery"] in rcw.CHEMBL_LINK_PREFIXES for p in searches))
        self.assertFalse(any("PBF" in str(p) for p in log))


class TargetResolutionTest(unittest.TestCase):
    def test_single_component_target_is_resolved(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_T1", ["P00533"])
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL_T1": {"protein": {"https://en.wikipedia.org/wiki/EGFR"}}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_T1'").fetchone()[0],
            "https://en.wikipedia.org/wiki/EGFR")

    def test_an_unreviewed_multi_component_target_is_never_queried(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_COMPLEX", ["P1", "P2"], target_type="PROTEIN COMPLEX")
        log = []
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL_COMPLEX": {"https://en.wikipedia.org/wiki/Wrong"}}, log=log)):
            summary = rcw.resolve_targets(conn, items={})
        self.assertEqual(summary["multi_component"], 1)
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(summary["by_item"]["unreviewed"], 1)
        self.assertEqual(log, [])
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_COMPLEX'").fetchone()[0])

    def test_a_family_is_linked_through_its_reviewed_item_never_its_members(self):
        # Walking out from PTGS1 and PTGS2 reaches "Haem peroxidase
        # superfamily"; the family's own item is Cyclooxygenase's.
        conn = fake_db()
        add_target(conn, "CHEMBL2094253", ["P23219", "P35354"], target_type="PROTEIN FAMILY")
        log = []
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL2094253": {
                "https://en.wikipedia.org/wiki/Cyclooxygenase"}}, log=log)):
            summary = rcw.resolve_targets(conn, items={"CHEMBL2094253": "Q410251"})
        self.assertEqual(summary["by_item"]["resolved"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL2094253'").fetchone()[0],
            "https://en.wikipedia.org/wiki/Cyclooxygenase")
        self.assertEqual(len(log), 1)
        self.assertIn("wd:Q410251", log[0])
        self.assertNotIn("P23219", log[0])
        self.assertNotIn("P35354", log[0])

    def test_a_target_reviewed_with_no_article_is_never_queried(self):
        conn = fake_db()
        add_target(conn, "CHEMBL2221347", ["P51787", "P15382"], target_type="PROTEIN COMPLEX")
        log = []
        with mock.patch.object(rcw, "_wikidata_get", stub(log=log)):
            summary = rcw.resolve_targets(conn, items={"CHEMBL2221347": None})
        self.assertEqual(summary["by_item"]["refused"], 1)
        self.assertEqual(summary["by_item"]["unreviewed"], 0)
        self.assertEqual(log, [])

    def test_a_reviewed_item_with_two_articles_is_ambiguous(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_FAMILY", ["P1", "P2"], target_type="PROTEIN FAMILY")
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL_FAMILY": {
                "https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/B"}})):
            summary = rcw.resolve_targets(conn, items={"CHEMBL_FAMILY": "Q1"})
        self.assertEqual(summary["by_item"]["ambiguous"], 1)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_FAMILY'").fetchone()[0])

    def test_a_failed_item_lookup_is_a_failure_and_writes_nothing(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_FAMILY", ["P1", "P2"], target_type="PROTEIN FAMILY",
                   wikipedia_url="https://en.wikipedia.org/wiki/Kept")
        with mock.patch.object(rcw, "_wikidata_get", stub(fail_keys=("CHEMBL_FAMILY",))):
            summary = rcw.resolve_targets(conn, refresh=True, items={"CHEMBL_FAMILY": "Q1"})
        self.assertEqual(summary["by_item"]["failed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_FAMILY'").fetchone()[0],
            "https://en.wikipedia.org/wiki/Kept")

    def test_a_single_component_target_never_takes_the_item_route(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_T1", ["P00533"])
        log = []
        with mock.patch.object(rcw, "_wikidata_get", stub(log=log)):
            summary = rcw.resolve_targets(conn, items={"CHEMBL_T1": "Q1"})
        self.assertEqual(summary["by_item"]["queried"], 0)
        self.assertTrue(all("wd:Q1" not in q for q in log))

    def test_target_type_label_is_not_trusted_over_the_actual_component_count(self):
        # ChEMBL itself files some SINGLE PROTEIN targets with zero or several
        # accessions (see the module docstring in resolve_cohort_wikipedia.py).
        # Eligibility must follow target_components, not target_type.
        conn = fake_db()
        add_target(conn, "CHEMBL_ODD", ["P1", "P2"], target_type="SINGLE PROTEIN")
        summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["multi_component"], 1)
        self.assertEqual(summary["queried"], 0)

    def test_no_accession_target_is_skipped_and_counted_separately(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_NOACC", [], target_type="SINGLE PROTEIN")
        summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["no_accession"], 1)
        self.assertEqual(summary["multi_component"], 0)
        self.assertEqual(summary["queried"], 0)

    def test_ambiguous_target_match_is_written_as_null(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_T2", ["P2"])
        with mock.patch.object(rcw, "_wikidata_get", stub({
                "CHEMBL_T2": {"protein": {"https://en.wikipedia.org/wiki/A",
                                          "https://en.wikipedia.org/wiki/B"}}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_T2'").fetchone()[0])

    def test_the_proteins_own_article_comes_before_its_genes(self):
        # Albumin: "Human serum albumin" on the protein, "Serum albumin" on ALB.
        conn = fake_db()
        add_target(conn, "CHEMBL3253", ["P02768"])
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL3253": {
                "protein": {"https://en.wikipedia.org/wiki/Human_serum_albumin"},
                "gene": {"https://en.wikipedia.org/wiki/Serum_albumin"}}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual((summary["resolved"], summary["ambiguous"]), (1, 0))
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL3253'").fetchone()[0],
            "https://en.wikipedia.org/wiki/Human_serum_albumin")

    def test_a_protein_two_genes_encode_keeps_the_disagreement_a_refusal(self):
        # The HSPA1A protein item carries the article "HSPA1B", and Wikidata
        # files it under both genes.
        conn = fake_db()
        add_target(conn, "CHEMBL5460", ["P0DMV8"])
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL5460": {
                "protein": {"https://en.wikipedia.org/wiki/HSPA1B"},
                "gene": {"https://en.wikipedia.org/wiki/HSPA1A"}}},
                genes={"CHEMBL5460": 2})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual((summary["resolved"], summary["ambiguous"]), (0, 1))

    def test_a_failed_gene_count_is_a_failure(self):
        conn = fake_db()
        add_target(conn, "CHEMBL3253", ["P02768"])
        get = stub({"CHEMBL3253": {
            "protein": {"https://en.wikipedia.org/wiki/Human_serum_albumin"},
            "gene": {"https://en.wikipedia.org/wiki/Serum_albumin"}}})

        def failing_count(query):
            if "COUNT(DISTINCT ?gene)" in query:
                raise rcw.WikidataError("stubbed failure")
            return get(query)
        with mock.patch.object(rcw, "_wikidata_get", failing_count):
            summary = rcw.resolve_targets(conn)
        self.assertEqual((summary["resolved"], summary["failed"]), (0, 1))

    def test_the_genes_article_stands_where_the_protein_has_none(self):
        conn = fake_db()
        add_target(conn, "CHEMBL226", ["P30542"])
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL226": {
                "gene": {"https://en.wikipedia.org/wiki/ADORA1"}}})):
            rcw.resolve_targets(conn)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL226'").fetchone()[0],
            "https://en.wikipedia.org/wiki/ADORA1")

    def test_two_gene_articles_are_still_ambiguous(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_T3", ["P3"])
        with mock.patch.object(rcw, "_wikidata_get", stub({"CHEMBL_T3": {
                "gene": {"https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/B"}}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual((summary["resolved"], summary["ambiguous"]), (0, 1))


def add_class(conn, code, label, source="mesh_struct"):
    conn.execute("INSERT INTO class_labels(source, code, level, label) VALUES (?,?,3,?)",
                 (source, code, label))


def class_stub(rows, log=None):
    """A fake `_wikidata_get` for the class query. `rows` maps a descriptor UI
    to a list of (item, article, category) bindings, any of the last two
    None - one binding per row SPARQL would return."""
    def _get(query):
        if log is not None:
            log.append(query)
        bindings = []
        for code, found in rows.items():
            if f'"{code}"' not in query:
                continue
            key = next(k for k in re.findall(r'\("([^"]+)" "' + code + r'"\)', query))
            for item, article, category in found:
                b = {"key": {"value": key},
                     "item": {"value": "http://www.wikidata.org/entity/" + item}}
                if article:
                    b["article"] = {"value": article}
                if category:
                    b["category"] = {"value": category}
                bindings.append(b)
        return {"results": {"bindings": bindings}}
    return _get


def wiki_stub(categories=None, pages=None, redirects=None, disambiguation=(),
              fail=False):
    """A fake `_wikipedia_get`: `categories` maps a category title to its
    wikitext, `pages` is the set of article titles that exist, `redirects`
    maps a title to (target, fragment)."""
    categories, pages, redirects = categories or {}, set(pages or ()), redirects or {}

    def _get(params):
        if fail:
            raise rcw.WikidataError("stubbed failure")
        titles = params["titles"].split("|")
        if params.get("prop") == "revisions":
            return {"query": {"pages": [
                {"title": t, "revisions": [{"slots": {"main": {"content": categories[t]}}}]}
                if t in categories else {"title": t, "missing": True} for t in titles]}}
        norm = [{"from": t, "to": t[0].upper() + t[1:]} for t in titles if t[0].islower()]
        names = [t[0].upper() + t[1:] for t in titles]
        redir = [{"from": t, "to": redirects[t][0], "tofragment": redirects[t][1]}
                 for t in names if t in redirects]
        out = []
        for t in names:
            t = redirects.get(t, (t,))[0]
            if t in pages:
                p = {"title": t}
                if t in disambiguation:
                    p["pageprops"] = {"disambiguation": ""}
                out.append(p)
            else:
                out.append({"title": t, "missing": True})
        return {"query": {"normalized": norm, "redirects": redir, "pages": out}}
    return _get


def class_links(conn):
    return {r[0]: r[1:] for r in conn.execute(
        "SELECT code, route, wikidata_item, category, wikipedia_url FROM class_wikipedia")}


class ClassResolutionTest(unittest.TestCase):
    def resolve(self, conn, wikidata, wikipedia=None, **kw):
        with mock.patch.object(rcw, "_wikidata_get", wikidata), \
             mock.patch.object(rcw, "_wikipedia_get", wikipedia or wiki_stub()):
            return rcw.resolve_classes(conn, **kw)

    def test_a_class_with_its_own_article_is_linked_by_its_item(self):
        conn = fake_db()
        add_class(conn, "D001569", "Benzodiazepines")
        summary = self.resolve(conn, class_stub({"D001569": [
            ("Q83871", "https://en.wikipedia.org/wiki/Benzodiazepine", "Category:Benzodiazepines")]}))
        self.assertEqual(summary["by_item"], 1)
        self.assertEqual(class_links(conn), {"D001569": (
            "item", "Q83871", None, "https://en.wikipedia.org/wiki/Benzodiazepine")})

    def test_xanthines_reaches_xanthine_through_its_category(self):
        # The item carrying D014970 has no English article; the category
        # Wikidata names for it declares Xanthine as its main article.
        conn = fake_db()
        add_class(conn, "D014970", "Xanthines")
        summary = self.resolve(
            conn,
            class_stub({"D014970": [("Q49922434", None, "Category:Xanthines")]}),
            wiki_stub(categories={"Category:Xanthines":
                                  "{{Commons category|Xanthines}}\n{{Cat main|Xanthine}}\n"},
                      pages={"Xanthine"}))
        self.assertEqual(summary["by_category"], 1)
        self.assertEqual(class_links(conn), {"D014970": (
            "category", "Q49922434", "Category:Xanthines",
            "https://en.wikipedia.org/wiki/Xanthine")})

    def test_a_redirect_is_followed_and_a_section_kept(self):
        conn = fake_db()
        add_class(conn, "D001596", "Benzylamines")
        add_class(conn, "D010187", "Pancreatic Hormones")
        self.resolve(
            conn,
            class_stub({"D001596": [("Q1", None, "Category:Benzylamines")],
                        "D010187": [("Q2", None, "Category:Pancreatic hormones")]}),
            wiki_stub(categories={
                "Category:Benzylamines": "{{Cat main|Benzylamine#Pharmacology and derivatives}}",
                "Category:Pancreatic hormones": "{{Category main|pancreatic hormone}}"},
                pages={"Benzylamine", "Pancreatic islets"},
                redirects={"Pancreatic hormone": ("Pancreatic islets", "")}))
        links = class_links(conn)
        self.assertEqual(links["D001596"][3],
                         "https://en.wikipedia.org/wiki/Benzylamine#Pharmacology_and_derivatives")
        self.assertEqual(links["D010187"][3], "https://en.wikipedia.org/wiki/Pancreatic_islets")

    def test_a_category_that_names_no_single_article_is_refused(self):
        conn = fake_db()
        texts = {"Category:A": "nothing here",
                 "Category:B": "{{Cat main}}",
                 "Category:C": "{{Cat main|One|Two}}",
                 "Category:D": "{{Cat main|One}}\n{{Main|Two}}",
                 "Category:E": "{{Cat main|Ambiguous}}",
                 "Category:F": "{{Cat main|Missing}}",
                 "Category:G": "{{Cat more|Elsewhere}}"}
        rows = {}
        for i, letter in enumerate("ABCDEFG"):
            add_class(conn, f"D00000{i}", letter)
            rows[f"D00000{i}"] = [(f"Q{i}", None, f"Category:{letter}")]
        summary = self.resolve(conn, class_stub(rows),
                               wiki_stub(categories=texts, pages={"One", "Two", "Ambiguous",
                                                                  "Elsewhere"},
                                         disambiguation={"Ambiguous"}))
        self.assertEqual(class_links(conn), {})
        self.assertEqual(summary["refused"], 7)

    def test_two_items_or_two_categories_are_ambiguous(self):
        conn = fake_db()
        add_class(conn, "D001127", "Arginine Vasopressin")
        add_class(conn, "D000002", "Two categories")
        summary = self.resolve(conn, class_stub({
            "D001127": [("Q183011", "https://en.wikipedia.org/wiki/Vasopressin", None),
                        ("Q21124841", "https://en.wikipedia.org/wiki/Vasopressin_(medication)", None)],
            "D000002": [("Q5", None, "Category:One"), ("Q5", None, "Category:Two")]}),
            wiki_stub(categories={"Category:One": "{{Cat main|One}}",
                                  "Category:Two": "{{Cat main|Two}}"}, pages={"One", "Two"}))
        self.assertEqual(class_links(conn), {})
        self.assertEqual(summary["ambiguous"], 2)

    def test_only_structure_classes_are_queried_and_by_descriptor_alone(self):
        conn = fake_db()
        add_class(conn, "D014970", "Xanthines")
        add_class(conn, "D000929", "Antidepressive Agents", source="mesh_pa")
        add_class(conn, "-pramine", "imipramine type", source="usan")
        log = []
        self.resolve(conn, class_stub({}, log=log))
        query = " ".join(log)
        self.assertIn('"D014970"', query)
        self.assertNotIn("D000929", query)
        self.assertNotIn("Xanthines", query, "a label is never a matching key")

    def test_a_failed_lookup_writes_nothing_and_leaves_existing_rows(self):
        conn = fake_db()
        add_class(conn, "D014970", "Xanthines")
        conn.execute("INSERT INTO class_wikipedia VALUES ('mesh_struct', 'D014970', 'Q1',"
                     " 'item', NULL, 'https://en.wikipedia.org/wiki/Xanthine')")
        summary = self.resolve(
            conn, class_stub({"D014970": [("Q49922434", None, "Category:Xanthines")]}),
            wiki_stub(fail=True), refresh=True)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(class_links(conn)["D014970"][0], "item")

    def test_dry_run_writes_nothing_and_a_rerun_skips_linked_classes(self):
        conn = fake_db()
        add_class(conn, "D001569", "Benzodiazepines")
        found = class_stub({"D001569": [
            ("Q83871", "https://en.wikipedia.org/wiki/Benzodiazepine", None)]})
        self.resolve(conn, found, dry_run=True)
        self.assertEqual(class_links(conn), {})
        self.resolve(conn, found)
        log = []
        summary = self.resolve(conn, class_stub({}, log=log))
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(log, [])

    def test_the_table_is_made_in_a_database_built_before_it(self):
        conn = fake_db()
        conn.execute("DROP TABLE class_wikipedia")
        add_class(conn, "D001569", "Benzodiazepines")
        self.resolve(conn, class_stub({"D001569": [
            ("Q83871", "https://en.wikipedia.org/wiki/Benzodiazepine", None)]}))
        self.assertEqual(len(class_links(conn)), 1)

    def test_main_article_reads_one_template_naming_one_article(self):
        self.assertEqual(rcw.main_article("{{Cat main|Xanthine}}"), ("Xanthine", None))
        self.assertEqual(rcw.main_article("{{catmain| indole }}"), ("indole", None))
        self.assertEqual(rcw.main_article("{{Category main article|Purine|l1=purines}}"),
                         ("Purine", None))
        self.assertEqual(rcw.main_article("{{Cat main}}"), (None, "names no article"))
        self.assertEqual(rcw.main_article(None), (None, "no main article"))


class TargetItemMapTest(unittest.TestCase):
    """config/cohort1_target_wikidata.json is hand-reviewed, so nothing here
    checks an item against Wikidata. These hold its shape, and its agreement
    with the seven legacy assemblies reviewed the same way before it."""

    def test_the_committed_map_loads(self):
        items = rcw.load_target_items()
        self.assertGreater(len(items), 400)
        self.assertEqual(items["CHEMBL2094253"], "Q410251")  # Cyclooxygenase

    def test_it_agrees_with_the_legacy_assembly_map(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import build_db
        items = rcw.load_target_items()
        for chembl_id, item in build_db.COMPLEX_WIKIDATA_ITEMS.items():
            self.assertEqual(items[chembl_id], item, chembl_id)

    def write_map(self, targets):
        tmp = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())) / "map.json"
        tmp.write_text(json.dumps({"targets": targets}))
        return tmp

    def test_a_null_item_needs_a_reason(self):
        path = self.write_map({"CHEMBL1": {"name": "x", "item": None}})
        with self.assertRaises(SystemExit):
            rcw.load_target_items(path)

    def test_an_item_must_be_a_wikidata_item_id(self):
        for bad in ("Cyclooxygenase", "q410251", "Q410251 "):
            path = self.write_map({"CHEMBL1": {"name": "x", "item": bad}})
            with self.assertRaises(SystemExit):
                rcw.load_target_items(path)

    def test_a_key_must_be_a_chembl_id(self):
        path = self.write_map({"Cyclooxygenase": {"name": "x", "item": "Q410251"}})
        with self.assertRaises(SystemExit):
            rcw.load_target_items(path)


class FullResolveTest(unittest.TestCase):
    def test_resolve_covers_both_tables_and_never_touches_other_columns(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL113", inchikey="RYYVLZVUVIJVGH-UHFFFAOYSA-N",
                     pref_name="Caffeine")
        add_target(conn, "CHEMBL226", ["P30542"])
        with mock.patch.object(rcw, "_wikidata_get", stub({
                "CHEMBL113": {"https://en.wikipedia.org/wiki/Caffeine"},
                "CHEMBL226": {"gene": {"https://en.wikipedia.org/wiki/ADORA1"}}})):
            summary = rcw.resolve(conn)
        self.assertEqual(summary["molecules"]["resolved"], 1)
        self.assertEqual(summary["targets"]["resolved"], 1)
        # pref_name is untouched - this backfill writes exactly one column.
        self.assertEqual(
            conn.execute("SELECT pref_name FROM molecules WHERE chembl_id = 'CHEMBL113'").fetchone()[0],
            "Caffeine")


if __name__ == "__main__":
    unittest.main()
