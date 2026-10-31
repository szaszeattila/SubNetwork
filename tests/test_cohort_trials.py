"""Offline tests for scripts/resolve_cohort_trials.py.

These lock in the rule the script exists to enforce (CLAUDE.md invariant 15,
applied to a registry id instead of a name: an id CT.gov does not confirm is
never guessed onto a row) and the operational guarantees the task asked for:
chunking, pagination, a not-found id distinguished from a failed chunk, a
redirected/aliased id reported and dropped rather than stored under the
wrong key, idempotence, --refresh, --dry-run, and that nothing outside
trial_status is ever touched.

No network access: `_ctgov_get` - the one seam that ever calls
`requests.get` - is stubbed out in every test, the same way
tests/test_cohort_wikipedia.py stubs `_wikidata_get`.

Run with: python3 -m unittest discover -s tests
"""

import itertools
import json
import pathlib
import sqlite3
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import resolve_cohort_trials as rct  # noqa: E402

SCHEMA = (pathlib.Path(__file__).resolve().parent.parent / "db" / "schema_cohort.sql").read_text()

_molregno = itertools.count(1)
_drugind = itertools.count(1)


# The very first shape trial_status shipped in, before phases,
# primary_outcomes and schema_version existed - used to test the migration
# path, which is the thing that lets an already-built db/cohort1.db gain
# these columns without a rebuild.
OLD_TRIAL_STATUS_SQL = """
CREATE TABLE trial_status (
    nct_id          TEXT PRIMARY KEY,
    overall_status  TEXT,
    why_stopped     TEXT,
    has_results     INTEGER,
    last_update     TEXT,
    fetched_at      TEXT NOT NULL
);
"""


def _cut_trial_status_block(schema):
    """(before, after): the schema text with the CREATE TABLE trial_status
    statement (whichever shape SCHEMA currently carries) sliced out, plus the
    text on either side of it - so a test can swap in a different shape or
    drop it entirely."""
    lines = schema.splitlines()
    start = next(i for i, l in enumerate(lines) if "CREATE TABLE IF NOT EXISTS trial_status" in l)
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == ");")
    return "\n".join(lines[:start]), "\n".join(lines[end + 1:])


def fake_db(trial_status="current"):
    """trial_status: "current" (the real, up-to-date table - the normal
    case), "missing" (simulate a db/cohort1.db built before trial_status
    existed at all - the CREATE TABLE IF NOT EXISTS case), or "old"
    (simulate one built under the first shape of this script, before
    phases/primary_outcomes/schema_version existed - the ALTER TABLE case)."""
    conn = sqlite3.connect(":memory:")
    if trial_status == "current":
        schema = SCHEMA
    else:
        before, after = _cut_trial_status_block(SCHEMA)
        schema = before + ("\n" + OLD_TRIAL_STATUS_SQL if trial_status == "old" else "") + after
    conn.executescript(schema)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def add_molecule(conn, chembl_id):
    conn.execute(
        "INSERT INTO molecules(parent_molregno, chembl_id, in_cohort,"
        " is_seed, route_atc_n, route_indication, admission_reason)"
        " VALUES (?,?,0,0,0,0,'seed_only')",
        (next(_molregno), chembl_id))
    return conn.execute("SELECT parent_molregno FROM molecules WHERE chembl_id = ?",
                         (chembl_id,)).fetchone()[0]


def add_indication(conn, parent_molregno, trial_ids):
    conn.execute(
        "INSERT INTO molecule_indications(parent_molregno, drugind_id, mesh_id,"
        " qualifies, trial_ids) VALUES (?,?,?,0,?)",
        (parent_molregno, next(_drugind), "D000001", trial_ids))


_NO_RESULTS_SECTION = object()


def study(nct_id, status=None, why_stopped=None, has_results=False, last_update=None,
          phases=None, outcomes=_NO_RESULTS_SECTION, start=None, completion=None,
          locations=None):
    """`phases` is a list of CT.gov phase strings, or None for a study with no
    phase at all. `outcomes` is a list of raw outcomeMeasure dicts (each with
    its own "type", "title" and optional "analyses"); the sentinel default
    means the study carries no resultsSection key whatsoever - a real API
    response never sends an empty one - and an explicit [] means a
    resultsSection with no outcome measures in it, which is a different
    (rarer) fact this script must still tell apart from "no results".
    `start` and `completion` are the registry's date structs as sent -
    {"date": ...} or {"date": ..., "type": ...} - or None for a study that
    carries no such struct at all. `locations` is the list of raw location
    dicts ({"country": ...}), or None for a record with no locations module."""
    record = {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "statusModule": {
                "overallStatus": status,
                **({"whyStopped": why_stopped} if why_stopped is not None else {}),
                "lastUpdatePostDateStruct": {"date": last_update},
                **({"startDateStruct": start} if start is not None else {}),
                **({"completionDateStruct": completion} if completion is not None else {}),
            },
        },
        "hasResults": has_results,
    }
    if phases is not None:
        record["protocolSection"]["designModule"] = {"phases": phases}
    if locations is not None:
        record["protocolSection"]["contactsLocationsModule"] = {"locations": locations}
    if outcomes is not _NO_RESULTS_SECTION:
        record["resultsSection"] = {"outcomeMeasuresModule": {"outcomeMeasures": outcomes}}
    return record


def stub(studies_by_chunk=None, fail_on=(), log=None):
    """A fake `_ctgov_get`. `studies_by_chunk` maps a requested nct_id to the
    raw study dict to return for it (matched by presence of that id in
    `filter.ids`, once per call). `fail_on` is a set of nct_ids whose chunk
    should raise CtgovError."""
    studies_by_chunk = studies_by_chunk or {}
    calls = []

    def _get(params):
        if log is not None:
            log.append(params)
        calls.append(params)
        requested = params["filter.ids"].split(",")
        for bad in fail_on:
            if bad in requested:
                raise rct.CtgovError("stubbed failure")
        seen = set()
        studies = []
        for nct_id in requested:
            if nct_id in studies_by_chunk and nct_id not in seen:
                studies.append(studies_by_chunk[nct_id])
                seen.add(nct_id)
        return {"studies": studies}

    return _get, calls


class ChunkFetchTest(unittest.TestCase):
    def test_matched_and_aliased_are_split(self):
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
                # CT.gov answers a request for NCT002 under its current id NCT999 -
                # a redirect/merge, which must not land on NCT002.
                "NCT002": study("NCT999", status="TERMINATED", why_stopped="futility"),
        })[0]):
            matched, aliased = rct.fetch_chunk(["NCT001", "NCT002"])
        self.assertEqual(set(matched), {"NCT001"})
        self.assertEqual(aliased, {"NCT999"})

    def test_pagination_follows_next_page_token(self):
        log = []

        def _get(params):
            log.append(params)
            if "pageToken" not in params:
                return {"studies": [study("NCT001", status="COMPLETED")],
                         "nextPageToken": "page2"}
            self.assertEqual(params["pageToken"], "page2")
            return {"studies": [study("NCT002", status="RECRUITING")]}

        with mock.patch.object(rct, "_ctgov_get", _get):
            matched, aliased = rct.fetch_chunk(["NCT001", "NCT002"])
        self.assertEqual(set(matched), {"NCT001", "NCT002"})
        self.assertEqual(len(log), 2)


def outcome_measure(title, type_="PRIMARY", analyses=None):
    """One raw outcomeMeasure entry, as CT.gov's resultsSection sends it.
    `analyses` is a list of raw {"pValue", "nonInferiorityType"} dicts; the
    default omits the "analyses" key entirely, matching how the live
    endpoint answers an outcome with no statistical analysis posted."""
    entry = {"type": type_, "title": title}
    if analyses is not None:
        entry["analyses"] = analyses
    return entry


class ParseStudyTest(unittest.TestCase):
    def test_all_fields(self):
        row = rct._parse_study(study("NCT001", status="TERMINATED",
                                      why_stopped="slow accrual", has_results=True,
                                      last_update="2024-01-23"))
        self.assertEqual(row, {
            "nct_id": "NCT001", "overall_status": "TERMINATED",
            "why_stopped": "slow accrual", "has_results": 1,
            "last_update": "2024-01-23", "phases": None, "primary_outcomes": None,
            "start_date": None, "start_date_type": None,
            "completion_date": None, "completion_date_type": None, "countries": None,
        })

    def test_countries_are_the_distinct_site_countries_sorted(self):
        row = rct._parse_study(study("NCT001", locations=[
            {"country": "Russia"}, {"country": "United States"},
            {"country": "Russia"}, {"city": "no country given"}]))
        self.assertEqual(row["countries"], "Russia|United States")

    def test_a_record_with_no_sites_keeps_countries_null_not_empty(self):
        # No location is a gap in the record, not a trial that ran nowhere.
        self.assertIsNone(rct._parse_study(study("NCT001", locations=[]))["countries"])
        self.assertIsNone(rct._parse_study(study("NCT001"))["countries"])

    def test_the_site_countries_are_asked_for(self):
        self.assertIn("LocationCountry", rct.CTGOV_FIELDS.split(","))

    def test_dates_are_kept_verbatim_beside_their_type(self):
        row = rct._parse_study(study(
            "NCT001", status="UNKNOWN",
            start={"date": "2009-03", "type": "ACTUAL"},
            completion={"date": "2012-12-31", "type": "ESTIMATED"}))
        self.assertEqual((row["start_date"], row["start_date_type"]), ("2009-03", "ACTUAL"))
        self.assertEqual((row["completion_date"], row["completion_date_type"]),
                         ("2012-12-31", "ESTIMATED"))

    def test_an_untyped_date_keeps_a_null_type_rather_than_a_guessed_one(self):
        # The registry typed no dates before 2017; an older record's date is
        # what it reported, and "ACTUAL" would be this script's word, not its.
        row = rct._parse_study(study("NCT001", status="COMPLETED",
                                      start={"date": "1998-01"},
                                      completion={"date": "2001-06"}))
        self.assertEqual(row["completion_date"], "2001-06")
        self.assertIsNone(row["start_date_type"])
        self.assertIsNone(row["completion_date_type"])

    def test_the_date_types_are_asked_for_by_name(self):
        # CT.gov sends a date struct's "type" only when the field list names
        # it - asking for CompletionDate alone returns a bare date.
        fields = rct.CTGOV_FIELDS.split(",")
        for f in ("StartDate", "StartDateType", "CompletionDate", "CompletionDateType"):
            self.assertIn(f, fields)

    def test_no_why_stopped_is_none(self):
        row = rct._parse_study(study("NCT002", status="COMPLETED", has_results=False))
        self.assertIsNone(row["why_stopped"])
        self.assertEqual(row["has_results"], 0)

    def test_missing_nct_id_returns_none(self):
        self.assertIsNone(rct._parse_study({"protocolSection": {}}))


class PhaseParsingTest(unittest.TestCase):
    def test_single_phase(self):
        self.assertEqual(rct._extract_phases({"designModule": {"phases": ["PHASE2"]}}),
                          "PHASE2")

    def test_multiple_phases_are_pipe_joined_in_registry_order(self):
        self.assertEqual(
            rct._extract_phases({"designModule": {"phases": ["PHASE2", "PHASE3"]}}),
            "PHASE2|PHASE3")

    def test_na_and_early_phase1_pass_through_verbatim(self):
        self.assertEqual(rct._extract_phases({"designModule": {"phases": ["NA"]}}), "NA")
        self.assertEqual(
            rct._extract_phases({"designModule": {"phases": ["EARLY_PHASE1"]}}),
            "EARLY_PHASE1")

    def test_no_design_module_is_none(self):
        self.assertIsNone(rct._extract_phases({}))

    def test_empty_phases_list_is_none(self):
        self.assertIsNone(rct._extract_phases({"designModule": {"phases": []}}))

    def test_via_parse_study(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED",
                                      phases=["PHASE1", "PHASE2"]))
        self.assertEqual(row["phases"], "PHASE1|PHASE2")


class PrimaryOutcomesParsingTest(unittest.TestCase):
    def test_no_results_section_is_none(self):
        row = rct._parse_study(study("NCT001", status="RECRUITING", has_results=False))
        self.assertIsNone(row["primary_outcomes"])

    def test_results_section_with_no_outcomes_is_empty_json_array(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True,
                                      outcomes=[]))
        self.assertEqual(row["primary_outcomes"], "[]")

    def test_only_primary_typed_outcomes_are_kept(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True, outcomes=[
            outcome_measure("Primary endpoint", type_="PRIMARY"),
            outcome_measure("Secondary endpoint", type_="SECONDARY"),
            outcome_measure("Other-specified endpoint", type_="OTHER_PRE_SPECIFIED"),
        ]))
        parsed = json.loads(row["primary_outcomes"])
        self.assertEqual([o["title"] for o in parsed], ["Primary endpoint"])

    def test_registry_order_is_preserved(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True, outcomes=[
            outcome_measure("Second primary", type_="PRIMARY"),
            outcome_measure("First primary", type_="PRIMARY"),
        ]))
        parsed = json.loads(row["primary_outcomes"])
        self.assertEqual([o["title"] for o in parsed], ["Second primary", "First primary"])

    def test_outcome_with_no_analyses_key_is_kept_with_empty_analyses_list(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True, outcomes=[
            outcome_measure("Primary endpoint", analyses=None),
        ]))
        parsed = json.loads(row["primary_outcomes"])
        self.assertEqual(parsed, [{"title": "Primary endpoint", "analyses": []}])

    def test_analyses_are_renamed_p_and_design_verbatim(self):
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True, outcomes=[
            outcome_measure("Primary endpoint", analyses=[
                {"pValue": "0.041", "nonInferiorityType": "SUPERIORITY_OR_OTHER"},
                {"pValue": "<0.001", "nonInferiorityType": "SUPERIORITY_OR_OTHER"},
            ]),
        ]))
        parsed = json.loads(row["primary_outcomes"])
        self.assertEqual(parsed, [{
            "title": "Primary endpoint",
            "analyses": [
                {"p": "0.041", "design": "SUPERIORITY_OR_OTHER"},
                {"p": "<0.001", "design": "SUPERIORITY_OR_OTHER"},
            ],
        }])

    def test_json_shape_matches_the_documented_contract(self):
        # The exact shape from the module docstring / schema comment:
        # [{"title": ..., "analyses": [{"p": ..., "design": ...}]}]
        row = rct._parse_study(study("NCT001", status="COMPLETED", has_results=True, outcomes=[
            outcome_measure("Percent change in trunk fat", analyses=[
                {"pValue": "0.004", "nonInferiorityType": None},
            ]),
        ]))
        parsed = json.loads(row["primary_outcomes"])
        self.assertIsInstance(parsed, list)
        self.assertEqual(set(parsed[0]), {"title", "analyses"})
        self.assertEqual(set(parsed[0]["analyses"][0]), {"p", "design"})
        self.assertEqual(parsed[0]["analyses"][0]["design"], None)


class ResolveTrialsTest(unittest.TestCase):
    def test_unresolved_ids_are_written(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001|NCT002")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED", last_update="2020-01-01"),
                "NCT002": study("NCT002", status="TERMINATED", why_stopped="safety",
                                 last_update="2021-06-01"),
        })[0]):
            summary = rct.resolve_trials(conn, fetched_at="2026-09-23T00:00:00+00:00")
        self.assertEqual(summary["resolved"], 2)
        self.assertEqual(summary["total"], 2)
        rows = dict(conn.execute("SELECT nct_id, overall_status FROM trial_status"))
        self.assertEqual(rows, {"NCT001": "COMPLETED", "NCT002": "TERMINATED"})
        why = conn.execute(
            "SELECT why_stopped FROM trial_status WHERE nct_id = 'NCT002'").fetchone()[0]
        self.assertEqual(why, "safety")
        fetched_at = conn.execute(
            "SELECT fetched_at FROM trial_status WHERE nct_id = 'NCT001'").fetchone()[0]
        self.assertEqual(fetched_at, "2026-09-23T00:00:00+00:00")

    def test_distinct_ids_deduplicated_across_rows(self):
        # Two indications (maybe two molecules) citing the same trial must
        # only be queried and counted once.
        conn = fake_db()
        m1 = add_molecule(conn, "CHEMBL1")
        m2 = add_molecule(conn, "CHEMBL2")
        add_indication(conn, m1, "NCT001|NCT002")
        add_indication(conn, m2, "NCT002")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
                "NCT002": study("NCT002", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["queried"], 2)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM trial_status").fetchone()[0], 2)

    def test_not_found_id_is_not_written(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT404")
        with mock.patch.object(rct, "_ctgov_get", stub({})[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["not_found"], 1)
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM trial_status").fetchone()[0], 0)

    def test_aliased_id_is_reported_and_dropped(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT002")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT002": study("NCT999", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["aliased"], 1)
        # Neither the requested nor the returned id is stored - guessing the
        # mapping is exactly what invariant 15 forbids.
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM trial_status").fetchone()[0], 0)
        # The id that was actually requested got no exact match either, so it
        # is *also* counted not found - it stays unresolved and retryable
        # next run, same as any other id the registry didn't confirm.
        self.assertEqual(summary["not_found"], 1)

    def test_failed_chunk_leaves_existing_rows_untouched(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001|NCT002")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
                "NCT002": study("NCT002", status="COMPLETED"),
        }, fail_on={"NCT002"})[0]):
            summary = rct.resolve_trials(conn, chunk_size=200)
        # Both ids share one chunk here, so the whole chunk fails together.
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM trial_status").fetchone()[0], 0)

    def test_failed_chunk_does_not_disturb_other_successful_chunks(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001|NCT002")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
                "NCT002": study("NCT002", status="COMPLETED"),
        }, fail_on={"NCT002"})[0]):
            summary = rct.resolve_trials(conn, chunk_size=1)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(
            conn.execute("SELECT nct_id FROM trial_status").fetchone()[0], "NCT001")

    def test_dry_run_writes_nothing(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn, dry_run=True)
        self.assertEqual(summary["resolved"], 1)  # it did find it...
        self.assertEqual(  # ...but nothing was written
            conn.execute("SELECT COUNT(*) FROM trial_status").fetchone()[0], 0)

    def test_rerun_does_not_requery_an_already_stored_id(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="RECRUITING"),
        })[0]):
            rct.resolve_trials(conn)
        self.assertEqual(
            conn.execute("SELECT overall_status FROM trial_status WHERE nct_id = 'NCT001'")
                .fetchone()[0], "RECRUITING")

        log = []
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        }, log=log)[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(log, [])
        self.assertEqual(
            conn.execute("SELECT overall_status FROM trial_status WHERE nct_id = 'NCT001'")
                .fetchone()[0], "RECRUITING")

    def test_refresh_requeries_and_overwrites_a_stored_id(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="RECRUITING"),
        })[0]):
            rct.resolve_trials(conn)
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED", has_results=True),
        })[0]):
            summary = rct.resolve_trials(conn, refresh=True)
        self.assertEqual(summary["queried"], 1)
        row = conn.execute(
            "SELECT overall_status, has_results FROM trial_status WHERE nct_id = 'NCT001'"
        ).fetchone()
        self.assertEqual(row, ("COMPLETED", 1))

    def test_limit_caps_the_candidate_set(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001|NCT002|NCT003")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
                "NCT002": study("NCT002", status="COMPLETED"),
                "NCT003": study("NCT003", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn, limit=1)
        self.assertEqual(summary["queried"], 1)
        self.assertEqual(summary["total"], 3)

    def test_chunking_splits_many_ids_into_several_requests(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        ids = [f"NCT{i:06d}" for i in range(5)]
        add_indication(conn, m, "|".join(ids))
        by_id = {i: study(i, status="COMPLETED") for i in ids}
        log = []
        with mock.patch.object(rct, "_ctgov_get", stub(by_id, log=log)[0]):
            summary = rct.resolve_trials(conn, chunk_size=2)
        self.assertEqual(summary["resolved"], 5)
        self.assertEqual(len(log), 3)  # ceil(5/2)
        for call in log:
            self.assertLessEqual(len(call["filter.ids"].split(",")), 2)

    def test_only_trial_status_is_written(self):
        conn = fake_db()
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        before = conn.execute("SELECT pref_name FROM molecules WHERE chembl_id='CHEMBL1'").fetchone()
        before_trial_ids = conn.execute(
            "SELECT trial_ids FROM molecule_indications WHERE parent_molregno=?", (m,)).fetchone()
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        })[0]):
            rct.resolve_trials(conn)
        after = conn.execute("SELECT pref_name FROM molecules WHERE chembl_id='CHEMBL1'").fetchone()
        after_trial_ids = conn.execute(
            "SELECT trial_ids FROM molecule_indications WHERE parent_molregno=?", (m,)).fetchone()
        self.assertEqual(before, after)
        self.assertEqual(before_trial_ids, after_trial_ids)

    def test_no_cited_trials_is_a_no_op(self):
        conn = fake_db()
        add_molecule(conn, "CHEMBL1")  # no indications at all
        summary = rct.resolve_trials(conn)
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["queried"], 0)


class CreatesTableOnAnOlderDatabaseTest(unittest.TestCase):
    def test_ensure_table_works_on_a_db_that_predates_trial_status(self):
        conn = fake_db(trial_status="missing")
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='trial_status'"
        ).fetchone()[0], 0)
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(
            conn.execute("SELECT overall_status FROM trial_status WHERE nct_id='NCT001'")
                .fetchone()[0], "COMPLETED")

    def test_ensure_table_is_idempotent_on_a_db_that_already_has_it(self):
        conn = fake_db(trial_status="current")
        rct._ensure_table(conn)  # must not raise
        rct._ensure_table(conn)

    def test_ensure_table_adds_missing_columns_to_an_old_shaped_table(self):
        conn = fake_db(trial_status="old")
        columns_before = {row[1] for row in conn.execute("PRAGMA table_info(trial_status)")}
        self.assertNotIn("phases", columns_before)
        self.assertNotIn("primary_outcomes", columns_before)
        self.assertNotIn("schema_version", columns_before)

        rct._ensure_table(conn)

        columns_after = {row[1] for row in conn.execute("PRAGMA table_info(trial_status)")}
        self.assertIn("phases", columns_after)
        self.assertIn("primary_outcomes", columns_after)
        self.assertIn("schema_version", columns_after)
        # ALTER TABLE ADD COLUMN must not disturb the original columns' data.
        conn.execute("INSERT INTO trial_status(nct_id, overall_status, fetched_at)"
                     " VALUES ('NCT001', 'COMPLETED', '2026-01-01T00:00:00+00:00')")
        row = conn.execute(
            "SELECT overall_status, phases, primary_outcomes, schema_version"
            " FROM trial_status WHERE nct_id = 'NCT001'").fetchone()
        self.assertEqual(row, ("COMPLETED", None, None, None))

    def test_ensure_table_migration_is_idempotent(self):
        conn = fake_db(trial_status="old")
        rct._ensure_table(conn)
        rct._ensure_table(conn)  # must not raise (ALTER TABLE ADD COLUMN twice)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(trial_status)")}
        self.assertIn("schema_version", columns)


class OldRowsAreRefetchedTest(unittest.TestCase):
    """The whole point of schema_version: a plain run (no --refresh) must
    treat a row written by the first shape of this script as unresolved,
    because its phases/primary_outcomes are missing data, not empty data."""

    def test_a_row_with_no_schema_version_is_requeried_and_gains_the_new_columns(self):
        conn = fake_db(trial_status="old")
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        conn.execute(
            "INSERT INTO trial_status(nct_id, overall_status, fetched_at)"
            " VALUES ('NCT001', 'RECRUITING', '2026-01-01T00:00:00+00:00')")

        log = []
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED", phases=["PHASE2"],
                                 has_results=True, outcomes=[
                                     outcome_measure("Primary endpoint",
                                                      analyses=[{"pValue": "0.01",
                                                                 "nonInferiorityType": None}]),
                                 ]),
        }, log=log)[0]):
            summary = rct.resolve_trials(conn)

        self.assertEqual(summary["queried"], 1)  # it WAS re-queried, not skipped
        self.assertEqual(len(log), 1)
        row = conn.execute(
            "SELECT overall_status, phases, primary_outcomes, schema_version"
            " FROM trial_status WHERE nct_id = 'NCT001'").fetchone()
        self.assertEqual(row[0], "COMPLETED")
        self.assertEqual(row[1], "PHASE2")
        self.assertEqual(json.loads(row[2]), [
            {"title": "Primary endpoint", "analyses": [{"p": "0.01", "design": None}]}])
        self.assertEqual(row[3], rct.SCHEMA_VERSION)

    def test_a_row_with_schema_version_1_is_also_requeried(self):
        conn = fake_db(trial_status="old")
        rct._ensure_table(conn)  # migrate the table so schema_version exists to set
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        conn.execute(
            "INSERT INTO trial_status(nct_id, overall_status, schema_version, fetched_at)"
            " VALUES ('NCT001', 'RECRUITING', 1, '2026-01-01T00:00:00+00:00')")

        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        })[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["queried"], 1)
        self.assertEqual(
            conn.execute("SELECT schema_version FROM trial_status WHERE nct_id='NCT001'")
                .fetchone()[0], rct.SCHEMA_VERSION)

    def test_a_row_with_schema_version_2_is_requeried_and_gains_its_dates(self):
        # A row from before the dates were fetched has NULL dates because
        # nobody asked, not because the registry has none.
        conn = fake_db(trial_status="current")
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        conn.execute(
            "INSERT INTO trial_status(nct_id, overall_status, phases, schema_version,"
            " fetched_at) VALUES ('NCT001', 'COMPLETED', 'PHASE2', 2,"
            " '2026-01-01T00:00:00+00:00')")

        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED", phases=["PHASE2"],
                                 start={"date": "2003-02"},
                                 completion={"date": "2005-11", "type": "ACTUAL"}),
        })[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["queried"], 1)
        row = conn.execute(
            "SELECT start_date, completion_date, completion_date_type, schema_version"
            " FROM trial_status WHERE nct_id = 'NCT001'").fetchone()
        self.assertEqual(tuple(row), ("2003-02", "2005-11", "ACTUAL", rct.SCHEMA_VERSION))

    def test_a_row_already_at_the_current_schema_version_is_not_requeried(self):
        conn = fake_db(trial_status="current")
        m = add_molecule(conn, "CHEMBL1")
        add_indication(conn, m, "NCT001")
        conn.execute(
            "INSERT INTO trial_status(nct_id, overall_status, schema_version, fetched_at)"
            " VALUES ('NCT001', 'RECRUITING', ?, '2026-01-01T00:00:00+00:00')",
            (rct.SCHEMA_VERSION,))

        log = []
        with mock.patch.object(rct, "_ctgov_get", stub({
                "NCT001": study("NCT001", status="COMPLETED"),
        }, log=log)[0]):
            summary = rct.resolve_trials(conn)
        self.assertEqual(summary["queried"], 0)
        self.assertEqual(log, [])
        self.assertEqual(
            conn.execute("SELECT overall_status FROM trial_status WHERE nct_id='NCT001'")
                .fetchone()[0], "RECRUITING")  # untouched


class ExportedYearsTest(unittest.TestCase):
    """What the page is sent: years, and which of them are only planned."""

    @staticmethod
    def years(start=None, start_type=None, end=None, end_type=None):
        from cohort import export
        return export._trial_years({"start_date": start, "start_date_type": start_type,
                                    "completion_date": end,
                                    "completion_date_type": end_type})

    def test_reported_dates_travel_as_years_with_no_flag(self):
        self.assertEqual(self.years("2001-03", "ACTUAL", "2005-06-15", None), [2001, 2005])

    def test_an_estimated_date_is_flagged_planned(self):
        from cohort import export
        self.assertEqual(self.years("2009-03", None, "2012-12", "ESTIMATED"),
                         [2009, 2012, export.TRIAL_END_PLANNED])
        self.assertEqual(self.years("2027-01", "ESTIMATED", "2029-01", "ESTIMATED"),
                         [2027, 2029, export.TRIAL_START_PLANNED | export.TRIAL_END_PLANNED])

    def test_missing_dates_are_dropped_from_the_tail(self):
        self.assertEqual(self.years(), [])
        self.assertEqual(self.years("1998-01"), [1998])
        self.assertEqual(self.years(None, None, "1999-02", None), [None, 1999])


if __name__ == "__main__":
    unittest.main()
