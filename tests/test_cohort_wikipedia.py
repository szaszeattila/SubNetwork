"""Offline tests for scripts/resolve_cohort_wikipedia.py.

These lock in the rule the whole script exists to enforce (CLAUDE.md
invariant 15: resolve external links by identifier, never by name) and the
operational guarantees the task asked for: an ambiguous Wikidata match is
dropped rather than guessed, a multi-component target is never queried at
all, a failed lookup is distinguished from "no article exists", and a rerun
never disturbs an already-resolved row.

No network access: `_wikidata_get` - the one seam that ever calls
`requests.get` - is stubbed out in every test. The stub inspects the
rendered SPARQL text for a quoted identifier literal, which doubles as the
"name is never a matching key" check: a query that embedded a molecule's
name rather than its ChEMBL ID/InChIKey would simply never match the stub's
data.

Run with: python3 -m unittest discover -s tests
"""

import itertools
import re
import pathlib
import sqlite3
import sys
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


def stub(article_map=None, fail_keys=(), log=None):
    """A fake `_wikidata_get`. `article_map` maps a literal that must appear
    in the rendered query (quoted, as sparql_literal would render it) to the
    set of article URLs to return for whichever `?key` row matched it.
    `fail_keys` are literals that raise WikidataError instead - simulating an
    endpoint failure distinct from a query that legitimately found nothing."""
    article_map = article_map or {}

    def _get(query):
        if log is not None:
            log.append(query)
        for needle in fail_keys:
            if f'"{needle}"' in query:
                raise rcw.WikidataError("stubbed failure")
        bindings = []
        for needle, articles in article_map.items():
            if f'"{needle}"' in query:
                for article in articles:
                    bindings.append({"key": {"value": needle},
                                      "article": {"value": article}})
        return {"results": {"bindings": bindings}}

    return _get


class MoleculeResolutionTest(unittest.TestCase):
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


class TargetResolutionTest(unittest.TestCase):
    def test_single_component_target_is_resolved(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_T1", ["P00533"])
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL_T1": {"https://en.wikipedia.org/wiki/EGFR"}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_T1'").fetchone()[0],
            "https://en.wikipedia.org/wiki/EGFR")

    def test_multi_component_target_is_never_queried(self):
        conn = fake_db()
        add_target(conn, "CHEMBL_COMPLEX", ["P1", "P2"], target_type="PROTEIN COMPLEX")
        log = []
        with mock.patch.object(rcw, "_wikidata_get",
                                stub({"CHEMBL_COMPLEX": {"https://en.wikipedia.org/wiki/Wrong"}}, log=log)):
            summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["multi_component"], 1)
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(log, [])
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_COMPLEX'").fetchone()[0])

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
                "CHEMBL_T2": {"https://en.wikipedia.org/wiki/A",
                              "https://en.wikipedia.org/wiki/B"}})):
            summary = rcw.resolve_targets(conn)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertIsNone(
            conn.execute("SELECT wikipedia_url FROM targets WHERE chembl_id = 'CHEMBL_T2'").fetchone()[0])


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


class FullResolveTest(unittest.TestCase):
    def test_resolve_covers_both_tables_and_never_touches_other_columns(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL113", inchikey="RYYVLZVUVIJVGH-UHFFFAOYSA-N",
                     pref_name="Caffeine")
        add_target(conn, "CHEMBL226", ["P30542"])
        with mock.patch.object(rcw, "_wikidata_get", stub({
                "CHEMBL113": {"https://en.wikipedia.org/wiki/Caffeine"},
                "CHEMBL226": {"https://en.wikipedia.org/wiki/ADORA1"}})):
            summary = rcw.resolve(conn)
        self.assertEqual(summary["molecules"]["resolved"], 1)
        self.assertEqual(summary["targets"]["resolved"], 1)
        # pref_name is untouched - this backfill writes exactly one column.
        self.assertEqual(
            conn.execute("SELECT pref_name FROM molecules WHERE chembl_id = 'CHEMBL113'").fetchone()[0],
            "Caffeine")


if __name__ == "__main__":
    unittest.main()
