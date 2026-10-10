"""Unit tests for build_db.py's pure data-handling logic.

Everything here runs offline. The point isn't coverage for its own sake - it's
that this project's value rests on a handful of small decisions about which
numbers are real and how many independent measurements back them, and every one
of those decisions was previously verified only by hand, once, against live
APIs. These lock in the ones that have already been gotten wrong at least once.

Run with: python3 -m unittest discover -s tests
"""

import contextlib
import io
import pathlib
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import build_db  # noqa: E402


class PooledAffinityTest(unittest.TestCase):
    """Affinities are log-normal; pooling must not average them arithmetically."""

    def test_odd_sample_is_the_middle_value(self):
        self.assertEqual(build_db.pooled_affinity([10, 100, 1000]), 100)

    def test_even_sample_uses_the_geometric_midpoint(self):
        # Arithmetic would give 505, which is nearly a log unit off.
        self.assertAlmostEqual(build_db.pooled_affinity([10, 1000]), 100.0)

    def test_single_value(self):
        self.assertEqual(build_db.pooled_affinity([49000]), 49000)

    def test_unordered_input(self):
        self.assertEqual(build_db.pooled_affinity([1000, 10, 100]), 100)

    def test_non_positive_value_does_not_crash(self):
        self.assertEqual(build_db.pooled_affinity([0, 10]), 5)


def row(value, source, ref="ref", url=None, text=None, note=None, description=None):
    return (value, source, ref, url, text, note, description)


class ReduceMeasurementsTest(unittest.TestCase):

    def test_prefers_ki_over_kd_over_ic50(self):
        entries = {
            "IC50": [row(1, "ChEMBL")],
            "Kd": [row(2, "ChEMBL")],
            "Ki": [row(3, "ChEMBL")],
        }
        self.assertEqual(build_db.reduce_measurements(entries)[0], "Ki")
        del entries["Ki"]
        self.assertEqual(build_db.reduce_measurements(entries)[0], "Kd")
        del entries["Kd"]
        self.assertEqual(build_db.reduce_measurements(entries)[0], "IC50")

    def test_never_mixes_types_into_one_median(self):
        entries = {"Ki": [row(10, "ChEMBL"), row(20, "PDSP")], "IC50": [row(9999, "ChEMBL")]}
        measurement_type, value, n, _, _ = build_db.reduce_measurements(entries)
        self.assertEqual((measurement_type, n), ("Ki", 2))
        self.assertNotIn(9999, (value,))

    def test_bindingdb_excluded_from_count_when_another_source_exists(self):
        # BindingDB republishes ChEMBL/PDSP records (~97% of what it returns
        # for these molecules), so counting it inflates n_measurements - the
        # signal the viewer renders as corroborated-vs-lead.
        entries = {"Kd": [row(690, "ChEMBL"), row(690, "BindingDB")]}
        _, value, n, sources, detail = build_db.reduce_measurements(entries)
        self.assertEqual(n, 1)
        self.assertEqual(value, 690)
        # Still listed as a source, for its citation link.
        self.assertIn("BindingDB", sources)
        # ...and still recorded as a measurement, flagged uncounted, so the
        # viewer can show it and say why it did not count rather than
        # silently omitting it.
        self.assertEqual([(d["source"], d["counted"]) for d in detail],
                         [("ChEMBL", True), ("BindingDB", False)])

    def test_bindingdb_counted_when_it_is_the_only_source(self):
        entries = {"Ki": [row(500, "BindingDB")]}
        _, value, n, sources, _ = build_db.reduce_measurements(entries)
        self.assertEqual((value, n), (500, 1))
        self.assertEqual(set(sources), {"BindingDB"})

    def test_empty_returns_none(self):
        self.assertIsNone(build_db.reduce_measurements({}))
        self.assertIsNone(build_db.reduce_measurements({"Ki": []}))

    def test_source_entries_carry_no_sampled_citation(self):
        # The dict holds one entry per source, so a citation put here is
        # whichever row happened to be assigned last - a paper nobody chose,
        # rendered beside the measurement list as if it were a separate
        # reference corroborating the edge. Per-measurement citations live
        # in the fifth element (and the `measurements` table); this dict
        # keeps only the external ref.
        entries = {"Ki": [row(10, "ChEMBL", ref="A", url="http://a", text="Paper A"),
                          row(20, "ChEMBL", ref="B", url="http://b", text="Paper B")]}
        _, _, _, sources, detail = build_db.reduce_measurements(entries)
        self.assertEqual(sources, {"ChEMBL": ("B", None, None, None)})
        self.assertEqual([(d["external_ref"], d["citation_url"]) for d in detail],
                         [("A", "http://a"), ("B", "http://b")])

    def test_functional_preference_order_is_honoured(self):
        entries = {"EC50": [row(5, "ChEMBL")], "Kb": [row(7, "ChEMBL")]}
        measurement_type, _, _, _, _ = build_db.reduce_measurements(
            entries, preference=build_db.FUNCTIONAL_STANDARD_TYPES
        )
        self.assertEqual(measurement_type, "EC50")


class PaginationTest(unittest.TestCase):
    """The bug this project shipped for months: reading only the first page."""

    def setUp(self):
        self._real_get_json = build_db.get_json
        self.calls = []

    def tearDown(self):
        build_db.get_json = self._real_get_json

    def _serve(self, total):
        records = [{"i": i} for i in range(total)]

        def fake_get_json(url, params=None, **kwargs):
            offset = params.get("offset", 0)
            limit = params.get("limit")
            self.calls.append(offset)
            page = records[offset:offset + limit]
            nxt = f"?offset={offset + limit}" if offset + limit < total else None
            return {"activities": page, "page_meta": {"total_count": total, "next": nxt}}

        build_db.get_json = fake_get_json

    def test_follows_every_page(self):
        # Derived from the configured page size rather than hardcoded, so
        # tuning CHEMBL_PAGE_SIZE doesn't turn into a spurious test failure.
        page = build_db.CHEMBL_PAGE_SIZE
        total = page * 2 + 7
        self._serve(total)
        got = build_db.get_json_paginated("u", {}, "activities")
        self.assertEqual(len(got), total)
        self.assertEqual(self.calls, [0, page, page * 2])

    def test_single_page_makes_one_request(self):
        self._serve(12)
        self.assertEqual(len(build_db.get_json_paginated("u", {}, "activities")), 12)
        self.assertEqual(self.calls, [0])

    def test_empty_result(self):
        self._serve(0)
        self.assertEqual(build_db.get_json_paginated("u", {}, "activities"), [])

    def test_stops_at_max_pages_instead_of_looping_forever(self):
        def never_ending(url, params=None, **kwargs):
            return {"activities": [{"i": 1}], "page_meta": {"total_count": 10**9, "next": "?more"}}

        build_db.get_json = never_ending
        got = build_db.get_json_paginated("u", {}, "activities")
        self.assertEqual(len(got), build_db.CHEMBL_MAX_PAGES)



class ListEndpointsPaginateTest(unittest.TestCase):
    """Invariant 2 is categorical: *every* ChEMBL list fetch follows page_meta.

    fetch_chembl_mechanisms shipped for months reading only page one. Nothing
    was ever wrong in the database, because no molecule in ChEMBL 37 has more
    than 15 curated mechanisms against a REST default limit of 20 - the breach
    was real but unreachable. That headroom is a property of the corpus, not of
    the code, so it is not something a reader should have to re-derive to know
    the fetcher is safe. Checking each list fetcher by name keeps the rule
    cheap to verify and catches the next one added.
    """

    # (label, zero-arg call, the collection key its endpoint returns)
    FETCHERS = [
        ("mechanism",
         lambda: build_db.fetch_chembl_mechanisms("CHEMBL113"),
         "mechanisms"),
        ("binding activity",
         lambda: build_db.fetch_chembl_binding_activities("CHEMBL113", "Ki"),
         "activities"),
        ("functional activity",
         lambda: build_db.fetch_chembl_functional_activities("CHEMBL113"),
         "activities"),
    ]

    def setUp(self):
        self._real_get_json = build_db.get_json
        self._real_local = build_db._local_chembl
        # Force the REST path; the local backend reads whole tables by SQL and
        # never paginates, which is the asymmetry that hid this in the first
        # place (invariant 12 - the two backends must agree).
        build_db._local_chembl = None

    def tearDown(self):
        build_db.get_json = self._real_get_json
        build_db._local_chembl = self._real_local

    def _serve(self, collection_key, total):
        records = [{"i": i} for i in range(total)]
        calls = []

        def fake_get_json(url, params=None, **kwargs):
            params = params or {}
            calls.append(dict(params))
            offset = params.get("offset", 0)
            limit = params.get("limit")
            if limit is None:
                raise AssertionError(f"{url} fetched with no limit - not paginated")
            nxt = f"?offset={offset + limit}" if offset + limit < total else None
            return {collection_key: records[offset:offset + limit],
                    "page_meta": {"total_count": total, "next": nxt}}

        build_db.get_json = fake_get_json
        return calls

    def test_every_list_fetcher_follows_pagination(self):
        page = build_db.CHEMBL_PAGE_SIZE
        total = page + 3          # one record past the first page
        for label, call, key in self.FETCHERS:
            with self.subTest(endpoint=label):
                calls = self._serve(key, total)
                got = call()
                self.assertEqual(len(got), total)
                self.assertEqual([c.get("offset") for c in calls], [0, page])
                self.assertTrue(all(c.get("limit") == page for c in calls))


class UniProtResolutionTest(unittest.TestCase):
    """protein_name search is relevance-ranked, not exact-match: accepting the
    top hit silently stored LTBR for "Tumor necrosis factor"."""

    def setUp(self):
        self._real_get_json = build_db.get_json

    def tearDown(self):
        build_db.get_json = self._real_get_json

    def _serve(self, names):
        def fake_get_json(url, params=None, **kwargs):
            return {"results": [
                {"primaryAccession": acc,
                 "proteinDescription": {"recommendedName": {"fullName": {"value": name}}}}
                for acc, name in names
            ]}
        build_db.get_json = fake_get_json

    def test_rejects_a_merely_related_top_hit(self):
        self._serve([
            ("P36941", "Tumor necrosis factor receptor superfamily member 3"),
            ("P01375", "Tumor necrosis factor"),
        ])
        self.assertEqual(
            build_db.resolve_uniprot_accession(protein_name="Tumor necrosis factor"),
            "P01375",
        )

    def test_returns_none_rather_than_guessing(self):
        self._serve([("Q9UKV8", "Protein argonaute-2"), ("Q13541", "Something else")])
        self.assertIsNone(
            build_db.resolve_uniprot_accession(protein_name="cGMP-specific phosphodiesterase")
        )

    def test_match_ignores_case_and_whitespace(self):
        self._serve([("O76074", "cGMP-specific  3',5'-cyclic   phosphodiesterase")])
        self.assertEqual(
            build_db.resolve_uniprot_accession(
                protein_name="CGMP-SPECIFIC 3',5'-CYCLIC PHOSPHODIESTERASE"),
            "O76074",
        )

    def _serve_genes(self, entries):
        """entries: [(accession, [gene names, primary first]), ...] in the
        order UniProt returns them."""
        def fake_get_json(url, params=None, **kwargs):
            return {"results": [
                {"primaryAccession": acc,
                 "genes": [{"geneName": {"value": g}} for g in genes]}
                for acc, genes in entries
            ]}
        build_db.get_json = fake_get_json

    def test_gene_search_rejects_a_synonym_ranked_first(self):
        """gene_exact: matches synonyms too, and ranks by relevance. UniProt
        really does return ADRA1D first for ADRA1A - the receptor cloned as
        "alpha-1a" was reclassified, and the old name is a synonym on that
        entry. Taking result[0] filed alpha-1A measurements under alpha-1D."""
        self._serve_genes([
            ("P25100", ["ADRA1D"]),
            ("P35348", ["ADRA1A"]),
        ])
        self.assertEqual(
            build_db.resolve_uniprot_accession(gene_symbol="ADRA1A"), "P35348")

    def test_gene_search_returns_none_when_only_a_synonym_matches(self):
        self._serve_genes([("P25100", ["ADRA1D"])])
        self.assertIsNone(build_db.resolve_uniprot_accession(gene_symbol="ADRA1A"))

    def test_gene_search_refuses_an_ambiguous_answer(self):
        self._serve_genes([("P00001", ["DUP"]), ("P00002", ["DUP"])])
        self.assertIsNone(build_db.resolve_uniprot_accession(gene_symbol="DUP"))

    def test_gene_search_ignores_case(self):
        self._serve_genes([("P31645", ["SLC6A4"])])
        self.assertEqual(
            build_db.resolve_uniprot_accession(gene_symbol="slc6a4"), "P31645")


class BrainExpressionTest(unittest.TestCase):

    def entry(self, accession, tissue):
        return {"primaryAccession": accession,
                "comments": [{"commentType": "TISSUE SPECIFICITY",
                              "texts": [{"value": tissue}]}]}

    def test_curated_note_wins(self):
        flag, note = build_db.brain_expression("ADORA1", self.entry("P30542", "Found in liver"))
        self.assertEqual(flag, 1)
        self.assertIn("caffeine", note)

    def test_uniprot_tissue_comment_sets_the_flag_with_a_verbatim_note(self):
        flag, note = build_db.brain_expression(
            "PDE4B", self.entry("Q07343", "Expressed in brain, heart, lung and skeletal muscle"))
        self.assertEqual(flag, 1)
        self.assertIn("Q07343", note)
        self.assertIn("Expressed in brain", note)

    def test_unknown_stays_null_never_zero(self):
        flag, note = build_db.brain_expression(
            "SIRT3", self.entry("Q9NTG7", "Widely expressed"))
        self.assertIsNone(flag)
        self.assertIsNone(note)

    def test_no_tissue_comment_at_all(self):
        self.assertEqual(build_db.brain_expression("XYZ1", {"comments": []}), (None, None))
        self.assertEqual(build_db.brain_expression("XYZ1", None), (None, None))

    def test_adrenal_cortex_is_not_brain(self):
        flag, _ = build_db.brain_expression(
            "CYP11B1", self.entry("P15538", "Expressed in the adrenal cortex"))
        self.assertIsNone(flag)


class ExclusionMapTest(unittest.TestCase):
    """Both known upstream mislinkings stay excluded, on both paths."""

    def test_chembl_plap_plaa_mislink(self):
        self.assertIn(("CHEMBL1074487", "CHEMBL6114"), build_db.CHEMBL_ASSAY_LINK_EXCLUSIONS)

    def test_ache_filed_under_chrne_is_excluded_on_both_sides(self):
        # Same upstream record reaches this pipeline twice: directly from
        # ChEMBL, and republished by BindingDB. Excluding only one leaves the
        # other open - which is exactly what paginating the ChEMBL fetch
        # would otherwise have re-admitted.
        self.assertIn(("CHEMBL5133661", "CHEMBL2484"), build_db.CHEMBL_ASSAY_LINK_EXCLUSIONS)
        self.assertIn(("8960", "Acetylcholine receptor subunit epsilon"),
                      build_db.BINDINGDB_TARGET_LINK_EXCLUSIONS)


class WikipediaLinkTest(unittest.TestCase):
    """Links are resolved through Wikidata by exact identifier match, never by
    title search - "ATM", "APP" and "TNF" are all English words, and a search
    API would answer confidently and wrongly."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(build_db.SCHEMA_PATH.read_text())
        self.conn.execute(
            "INSERT INTO targets (gene_symbol, uniprot_accession)"
            " VALUES ('ADORA1', 'P30542'), ('ACHE', 'P22303'), ('PDE3A', 'Q14432')")

    def tearDown(self):
        self.conn.close()

    def test_sparql_literal_escapes(self):
        self.assertEqual(build_db.sparql_literal("P30542"), '"P30542"')
        self.assertEqual(build_db.sparql_literal(2519), '"2519"')
        self.assertEqual(build_db.sparql_literal('a"b'), '"a\\"b"')
        self.assertEqual(build_db.sparql_literal("a\\b"), '"a\\\\b"')

    def test_only_unambiguous_matches_are_written(self):
        # One article: written. Two: skipped, because picking one would be a
        # guess. None: skipped, and NULL is the honest answer.
        found = {
            "ADORA1": {"https://en.wikipedia.org/wiki/Adenosine_A1_receptor"},
            "ACHE": {"https://en.wikipedia.org/wiki/Acetylcholinesterase",
                      "https://en.wikipedia.org/wiki/Cholinesterase"},
        }
        build_db.apply_articles(self.conn, "targets", "gene_symbol", found,
                                ["ADORA1", "ACHE", "PDE3A"])
        rows = dict(self.conn.execute(
            "SELECT gene_symbol, wikipedia_url FROM targets"))
        self.assertEqual(rows["ADORA1"],
                         "https://en.wikipedia.org/wiki/Adenosine_A1_receptor")
        self.assertIsNone(rows["ACHE"])
        self.assertIsNone(rows["PDE3A"])

    def test_an_unresolved_pass_does_not_blank_an_existing_link(self):
        # sparql_articles returns partial results when the endpoint fails, so
        # apply_articles must only ever write, never clear - otherwise one
        # Wikidata outage silently strips every link in the database.
        self.conn.execute(
            "UPDATE targets SET wikipedia_url = 'https://en.wikipedia.org/wiki/X'"
            " WHERE gene_symbol = 'ADORA1'")
        build_db.apply_articles(self.conn, "targets", "gene_symbol", {}, ["ADORA1"])
        self.assertEqual(self.conn.execute(
            "SELECT wikipedia_url FROM targets WHERE gene_symbol='ADORA1'"
        ).fetchone()[0], "https://en.wikipedia.org/wiki/X")

    def test_lookup_is_chunked(self):
        # A single 51-accession VALUES block 504s on the live endpoint.
        calls = []
        original = build_db.get_json
        build_db.get_json = lambda url, **kw: (
            calls.append(kw["params"]["query"]) or {"results": {"bindings": []}})
        self.addCleanup(setattr, build_db, "get_json", original)
        build_db.sparql_articles("%s", [f'("G{i}" "A{i}")' for i in range(51)])
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0].count("("), build_db.WIKIDATA_CHUNK)


class ComplexWikidataItemsShapeTest(unittest.TestCase):
    """The ChEMBL-id-to-Wikidata-item identities in COMPLEX_WIKIDATA_ITEMS
    are hand-written (see the comment above the map: no derivation from a
    member's UniProt accession lands on the right concept, only on
    confidently-wrong or over-broad ones), so nothing here checks them
    against Wikidata itself. This only guards the one thing a typo could
    silently break - the shape of the keys and values - so a bad entry
    fails a test instead of failing a build's Wikidata query."""

    def test_keys_are_chembl_ids(self):
        for key in build_db.COMPLEX_WIKIDATA_ITEMS:
            self.assertIsInstance(key, str)
            self.assertRegex(key, r"^CHEMBL[0-9]+$")

    def test_non_none_values_are_wikidata_item_ids(self):
        # None is a real, deliberate value here (see CHEMBL2221347) - the
        # record that an assembly was looked at and found to have no
        # English article of its own, not that it was missed.
        for value in build_db.COMPLEX_WIKIDATA_ITEMS.values():
            if value is not None:
                self.assertRegex(value, r"^Q[0-9]+$")


class ComplexWikipediaLinkTest(unittest.TestCase):
    """target_complexes.wikipedia_url comes from the hand-curated
    COMPLEX_WIKIDATA_ITEMS map, not from an identifier ChEMBL supplies -
    only the article lookup itself goes through Wikidata, via the same
    apply_articles/sparql_articles machinery molecules and targets use."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(build_db.SCHEMA_PATH.read_text())
        self.conn.execute(
            "INSERT INTO target_complexes (chembl_id, name, target_type, n_components)"
            " VALUES "
            "('CHEMBL5303741', 'GABA-A a1/a2/b2/g2', 'PROTEIN COMPLEX', 4),"
            "('CHEMBL2221347', 'IKs channel', 'PROTEIN COMPLEX', 2),"
            "('CHEMBL9999999', 'Unmapped complex', 'PROTEIN COMPLEX', 2)"
        )
        self.original_sparql_articles = build_db.sparql_articles
        self.addCleanup(setattr, build_db, "sparql_articles",
                        self.original_sparql_articles)
        self.addCleanup(self.conn.close)

    def test_only_the_mapped_non_none_complex_is_queried(self):
        # CHEMBL2221347 maps to None (deliberately: no English article for
        # the IKs channel itself) and CHEMBL9999999 has no entry in the map
        # at all - neither should generate a Wikidata query.
        queried_values = []

        def fake_sparql_articles(query_template, values):
            self.assertEqual(query_template, build_db.WIKIDATA_ITEM_QUERY)
            queried_values.extend(values)
            return {}

        build_db.sparql_articles = fake_sparql_articles
        build_db.resolve_complex_wikipedia_urls(self.conn)

        self.assertEqual(len(queried_values), 1)
        self.assertIn('"CHEMBL5303741"', queried_values[0])
        # The item is a bare prefixed IRI, not a quoted string literal.
        self.assertIn("wd:Q60147", queried_values[0])
        self.assertNotIn('"Q60147"', queried_values[0])

    def test_resolved_article_is_written_and_unmapped_stay_null(self):
        build_db.sparql_articles = lambda qt, values: {
            "CHEMBL5303741": {"https://en.wikipedia.org/wiki/GABAA_receptor"}}
        build_db.resolve_complex_wikipedia_urls(self.conn)
        rows = dict(self.conn.execute(
            "SELECT chembl_id, wikipedia_url FROM target_complexes"))
        self.assertEqual(rows["CHEMBL5303741"],
                         "https://en.wikipedia.org/wiki/GABAA_receptor")
        # A deliberate None mapping and a wholly unmapped complex end up with
        # the same NULL, for two different and both-honest reasons.
        self.assertIsNone(rows["CHEMBL2221347"])
        self.assertIsNone(rows["CHEMBL9999999"])

    def test_entirely_unmapped_complex_is_reported_by_name(self):
        # A newly-appearing assembly with no entry at all must be visible,
        # not silently unlinked.
        build_db.sparql_articles = lambda qt, values: {}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            build_db.resolve_complex_wikipedia_urls(self.conn)
        self.assertIn("CHEMBL9999999", out.getvalue())


class AddColumnIfMissingTest(unittest.TestCase):
    """The one migration this pipeline performs on an existing database
    without --rebuild - deliberately narrow, for the one column that
    provably adds no rows and changes no measurement (see the docstring on
    add_column_if_missing)."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        self.addCleanup(self.conn.close)

    def test_adds_a_missing_column(self):
        build_db.add_column_if_missing(self.conn, "t", "wikipedia_url", "TEXT")
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(t)")}
        self.assertIn("wikipedia_url", columns)

    def test_is_a_no_op_when_the_column_already_exists(self):
        build_db.add_column_if_missing(self.conn, "t", "wikipedia_url", "TEXT")
        # A second ALTER TABLE ADD COLUMN of the same name raises in SQLite -
        # this must not, since it runs on every build and every
        # --complexes-only invocation, not just the first one after the
        # column was introduced.
        build_db.add_column_if_missing(self.conn, "t", "wikipedia_url", "TEXT")


class SchemaTest(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(build_db.SCHEMA_PATH.read_text())

    def tearDown(self):
        self.conn.close()

    def test_one_source_can_back_an_edge_in_two_roles(self):
        # The regression that dropped ChEMBL's functional assay id on every
        # edge that also had ChEMBL binding data.
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADORA1')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (1, 'ChEMBL')")
        self.conn.execute(
            "INSERT INTO interactions (id, molecule_id, target_id, action_type)"
            " VALUES (1, 1, 1, 'ANTAGONIST')")
        build_db.link_source(self.conn, 1, 1, "CHEMBL_B", role="binding")
        build_db.link_source(self.conn, 1, 1, "CHEMBL_F", role="functional")
        refs = [r[0] for r in self.conn.execute(
            "SELECT external_ref FROM interaction_sources ORDER BY role")]
        self.assertEqual(refs, ["CHEMBL_B", "CHEMBL_F"])

    def test_link_source_upserts_rather_than_duplicating(self):
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADORA1')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (1, 'ChEMBL')")
        self.conn.execute(
            "INSERT INTO interactions (id, molecule_id, target_id, action_type)"
            " VALUES (1, 1, 1, 'ANTAGONIST')")
        build_db.link_source(self.conn, 1, 1, "A", citation_url=None, role="binding")
        build_db.link_source(self.conn, 1, 1, "A", citation_url="http://x",
                             citation_kind="mechanism", role="binding")
        rows = list(self.conn.execute(
            "SELECT external_ref, citation_url, citation_kind FROM interaction_sources"))
        self.assertEqual(rows, [("A", "http://x", "mechanism")])

    def test_link_source_refuses_an_unlabelled_citation(self):
        # An unlabelled citation here reads, in the viewer's database list,
        # as an independent reference for the edge. For 84 of 133 links it
        # was a sampled copy of one of the edge's own measurements. Storing
        # one now requires saying which of the two non-measurement kinds it
        # is, so the sampling path cannot come back by accident.
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADORA1')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (1, 'ChEMBL')")
        self.conn.execute(
            "INSERT INTO interactions (id, molecule_id, target_id, action_type)"
            " VALUES (1, 1, 1, 'ANTAGONIST')")
        with self.assertRaises(ValueError):
            build_db.link_source(self.conn, 1, 1, "A", citation_url="http://x",
                                 role="binding")
        with self.assertRaises(ValueError):
            build_db.link_source(self.conn, 1, 1, "A", citation_text="A paper",
                                 role="binding")
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM interaction_sources").fetchone()[0], 0)

    def test_upsert_interaction_clears_a_value_the_sources_no_longer_support(self):
        # COALESCE here would pin a retracted measurement in place forever.
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADRA1A')")
        build_db.upsert_interaction(self.conn, 1, 1, "BINDER", "moa", 0,
                                    30000.0, "Ki", "nM", 1)
        build_db.upsert_interaction(self.conn, 1, 1, "BINDER", "moa", 0,
                                    None, None, None, None)
        value, n = self.conn.execute(
            "SELECT binding_value, n_measurements FROM interactions").fetchone()
        self.assertIsNone(value)
        self.assertIsNone(n)

    def test_reset_molecule_removes_edges_and_their_source_links(self):
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADORA1')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (1, 'ChEMBL')")
        self.conn.execute(
            "INSERT INTO interactions (id, molecule_id, target_id, action_type)"
            " VALUES (1, 1, 1, 'BINDER')")
        build_db.link_source(self.conn, 1, 1, "A", role="binding")
        build_db.reset_molecule(self.conn, 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM interactions").fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM interaction_sources").fetchone()[0], 0)

    def _seed_edge(self):
        self.conn.execute("INSERT INTO molecules (id, name) VALUES (1, 'Caffeine')")
        self.conn.execute("INSERT INTO targets (id, gene_symbol) VALUES (1, 'ADORA1')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (1, 'ChEMBL')")
        self.conn.execute("INSERT INTO sources (id, name) VALUES (2, 'BindingDB')")
        self.conn.execute(
            "INSERT INTO interactions (id, molecule_id, target_id, action_type)"
            " VALUES (1, 1, 1, 'ANTAGONIST')")
        return {"ChEMBL": 1, "BindingDB": 2}

    def test_measurements_keep_every_row_the_source_dict_collapses(self):
        # The defect this table exists for: interaction_sources holds one row
        # per (source, role), so thirteen ChEMBL binding measurements left a
        # single citation and n_measurements was an unverifiable assertion.
        source_ids = self._seed_edge()
        entries = {"Ki": [
            (10700.0, "ChEMBL", "CHEMBL4259136", "http://p/1", "Paper one", None, None),
            (44900.0, "ChEMBL", "CHEMBL2156697", "http://p/2", "Paper two", None, None),
            (49000.0, "ChEMBL", "CHEMBL947105", "http://p/3", "Paper three", None, None),
        ]}
        _, _, n, sources, detail = build_db.reduce_measurements(entries)
        build_db.record_measurements(self.conn, 1, source_ids, "binding", "Ki", detail)
        self.assertEqual(len(sources), 1)          # what the old panel showed
        rows = list(self.conn.execute(
            "SELECT external_ref, citation_text FROM measurements ORDER BY value"))
        self.assertEqual(len(rows), n)             # what it shows now
        self.assertEqual([r[1] for r in rows],
                         ["Paper one", "Paper two", "Paper three"])

    def test_counted_rows_equal_n_measurements(self):
        # The invariant the whole table rests on: what the viewer lists as
        # counted must be exactly what n_measurements claims.
        source_ids = self._seed_edge()
        entries = {"Kd": [
            (690.0, "ChEMBL", "CHEMBL1", "http://p/1", "Paper", None, None),
            (690.0, "BindingDB", "10849", "http://b/1", "BDBM10849", None, None),
        ]}
        _, _, n, _, detail = build_db.reduce_measurements(entries)
        build_db.record_measurements(self.conn, 1, source_ids, "binding", "Kd", detail)
        counted = self.conn.execute(
            "SELECT COUNT(*) FROM measurements WHERE counted = 1").fetchone()[0]
        self.assertEqual(counted, n)
        # ...and the excluded row is still stored, so the viewer can show it
        # and say why rather than silently dropping it.
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM measurements").fetchone()[0], 2)

    def test_identical_measurements_are_not_deduplicated(self):
        # Two assays reporting the same number are two measurements. A UNIQUE
        # constraint here would silently deflate n_measurements.
        source_ids = self._seed_edge()
        entries = {"Ki": [
            (44900.0, "ChEMBL", "CHEMBL3096082", "http://p/1", "Paper", None, None),
            (44900.0, "ChEMBL", "CHEMBL3096091", "http://p/1", "Paper", None, None),
        ]}
        _, _, n, _, detail = build_db.reduce_measurements(entries)
        build_db.record_measurements(self.conn, 1, source_ids, "binding", "Ki", detail)
        self.assertEqual(n, 2)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM measurements").fetchone()[0], 2)

    def test_reset_molecule_removes_measurements(self):
        # Without this, a rerun would append a second copy of every
        # measurement (there is no key to upsert on) and n would drift.
        source_ids = self._seed_edge()
        build_db.record_measurements(self.conn, 1, source_ids, "binding", "Ki", [
            {"value": 1.0, "source": "ChEMBL", "external_ref": "A",
             "citation_url": None, "citation_text": None,
             "data_validity_note": None, "assay_description": None,
             "counted": True},
        ])
        build_db.reset_molecule(self.conn, 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM measurements").fetchone()[0], 0)

    def test_check_schema_rejects_a_database_predating_the_role_column(self):
        old = sqlite3.connect(":memory:")
        old.execute("CREATE TABLE interaction_sources (interaction_id INT, source_id INT)")
        with self.assertRaises(SystemExit) as ctx:
            build_db.check_schema(old)
        self.assertIn("--rebuild", str(ctx.exception))
        old.close()


class CitationTest(unittest.TestCase):

    def test_mechanism_citation_prefers_pubmed_over_fda(self):
        mech = {"mechanism_refs": [
            {"ref_type": "FDA", "ref_id": "1", "ref_url": "http://fda"},
            {"ref_type": "PubMed", "ref_id": "2", "ref_url": "http://pubmed"},
        ]}
        url, text = build_db.chembl_mechanism_citation(mech)
        self.assertEqual(url, "http://pubmed")
        self.assertIn("PubMed", text)

    def test_mechanism_citation_with_no_refs(self):
        self.assertEqual(build_db.chembl_mechanism_citation({}), (None, None))

    def test_bindingdb_citation_links_the_compound_page(self):
        url, text = build_db.bindingdb_citation("10849")
        self.assertIn("monomerid=10849", url)
        self.assertEqual(text, "BindingDB BDBM10849")

    def test_bindingdb_citation_handles_a_missing_id(self):
        self.assertEqual(build_db.bindingdb_citation(None), (None, None))
        self.assertEqual(build_db.bindingdb_citation("None"), (None, None))

    def test_dgidb_falls_back_to_naming_the_curating_databases(self):
        interaction = {"interactionClaims": [
            {"source": {"sourceDbName": "TTD"}, "publications": []},
            {"source": {"sourceDbName": "ChEMBL"}, "publications": []},
        ]}
        url, text = build_db.dgidb_citation(interaction)
        self.assertIsNone(url)
        self.assertEqual(text, "ChEMBL, TTD")

    def test_dgidb_prefers_a_real_publication(self):
        interaction = {"interactionClaims": [
            {"source": {"sourceDbName": "TTD"},
             "publications": [{"pmid": 12345, "citation": "A paper"}]},
        ]}
        url, text = build_db.dgidb_citation(interaction)
        self.assertEqual(url, "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertEqual(text, "A paper")


if __name__ == "__main__":
    unittest.main()
