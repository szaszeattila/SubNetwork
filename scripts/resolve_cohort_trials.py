#!/usr/bin/env python3
"""Backfill trial_status in db/cohort1.db from the ClinicalTrials.gov registry.

molecule_indications.trial_ids already carries the NCT ids ChEMBL's curators
cite for a disease's phase - one column, '|'-joined, ~12,845 distinct ids
across the whole database. That says how far a trial *got when ChEMBL last
looked*; it says nothing about what became of it since. A Phase 3 label next
to a trial that was terminated for a safety signal two years ago reads as
still-running, because nothing on the page distinguishes the two. This script
fills the other half: for every cited NCT id, the registry's own current
overall status, why it stopped if it did, whether it posted results, and when
that record was last touched.

This is a standalone backfill of one derived fact, modelled directly on
scripts/resolve_cohort_wikipedia.py and not reimplemented from scratch,
because the rule that makes both of these safe is the same rule
(CLAUDE.md invariant 15, the identifier-only half of invariant 6): resolve by
an identifier this database already holds and never by a name or a search.
An NCT id is already exact - there is no ambiguity to guard against the way
there is for a molecule or a protein name - but the registry does sometimes
return a study under a *different* nctId than the one requested (an old id
merged or redirected to a current one). That case is reported and dropped
rather than guessed at, for the same reason a Wikidata item resolving to two
articles is dropped: this script does not know which requested id the
substitute answers for, and a wrong link under a confident label is worse
than a missing one.

It never opens ChEMBL and never changes any table but trial_status. It does
not touch molecule_indications.trial_ids - that column is what tells this
script which ids to look up, not something it writes back to.

Because trial_status was added to db/schema_cohort.sql after some databases
were already built, this script also issues its own
`CREATE TABLE IF NOT EXISTS trial_status (...)` (exactly matching the schema
file) before it does anything else, so it works against an existing
db/cohort1.db without requiring a rebuild. The same problem repeats one level
down: `phases` and `primary_outcomes` were added to that table after the
first backfill had already run and written rows without them, so the table
itself needs a migration, not just its creation. `_ensure_columns` runs
`ALTER TABLE trial_status ADD COLUMN ...` for any of the three newer columns
(`phases`, `primary_outcomes`, `schema_version`) missing from an existing
table - a no-op on a table that already has them, and the thing that lets a
row written by the first shape of this script gain them without a rebuild.

A trial's own phase and primary-outcome statistics are a different question
from the disease-indication phase this database already stores
(molecule_indications.max_phase_for_ind, which is ChEMBL's own read of a
disease's status): that column says how far *ChEMBL's curators* judged one
indication to have progressed, from whatever mix of trials and labels they
were working from. `trial_status.phases` and `.primary_outcomes` are the
registry's own record of one specific trial - what phase *it* ran, and
whether its primary endpoint showed a difference - which can, and does,
disagree with ChEMBL's summary without either being wrong.

`schema_version` is what makes a partial database self-describing rather than
ambiguous: a row can legitimately have `phases IS NULL` (the registry has no
phase for it - many device or behavioral studies do not) and
`primary_outcomes IS NULL` (no results section at all) *after* a full fetch,
so neither column can be used to infer "not yet fetched under the new code".
`schema_version = 2` is written on every row this version of the script
inserts, regardless of whether phases or primary_outcomes actually came back
NULL; a row with `schema_version IS NULL` or `1` was written before these
columns existed and is missing real data, not empty data. See
`resolve_trials` for how a default run re-fetches those old rows alongside
brand-new ids.

`start_date` and `completion_date` came third, for the same reason and by the
same mechanism (`schema_version = 3`): a phase 2 trial that completed in 2005
under a disease that never reached Approved says something a still-running one
does not, and the page could not tell them apart. Both are the registry's own
dates verbatim ("2005-06" or "2005-06-15"), each beside the type CT.gov gives
it - ACTUAL, ESTIMATED, or NULL. NULL is common and is not "unknown": the
registry began typing these dates only in 2017, and an older record's dates are
the ones it reported, not a plan. ESTIMATED is the case that matters. An
ongoing trial's end is a plan, and so is the end date on a trial whose status
is UNKNOWN - in a sample of 200 cited ids, 20 of the 34 estimated completion
dates belonged to trials nobody had updated, most of them planned for a year
long past - and a reader who is shown that year without the word "planned"
reads a trial that ended. The completion date is the whole study's, not the
primary completion date: it is when the trial stopped running, which is the
question the page asks of it. A study with neither date (6 of the 200 had no
completion date) keeps NULLs, and schema_version 3 says they were asked for.

API: GET https://clinicaltrials.gov/api/v2/studies, filter.ids=<comma-joined
NCT ids>, fields=NCTId,OverallStatus,WhyStopped,HasResults,LastUpdatePostDate,
StartDate,StartDateType,CompletionDate,CompletionDateType,
Phase,OutcomeMeasureType,OutcomeMeasureTitle,OutcomeAnalysisPValue,
OutcomeAnalysisNonInferiorityType, pageSize=1000, following nextPageToken ->
pageToken when present. Matched purely on
protocolSection.identificationModule.nctId - never on a title or a condition
search. The dates come back as protocolSection.statusModule.startDateStruct
and .completionDateStruct, each {"date", "type"}; the type is sent only when
StartDateType/CompletionDateType are asked for by name. Phase comes back as protocolSection.designModule.phases (a list, e.g.
["PHASE2", "PHASE3"], joined here with '|'). The outcome fields only come back
at all when a study has posted results, nested at
resultsSection.outcomeMeasuresModule.outcomeMeasures[] - a sibling of
protocolSection, not inside it - each
carrying `type` ("PRIMARY", "SECONDARY", ...), `title`, and an `analyses` list
- present only when a statistical analysis was recorded - of
{"pValue", "nonInferiorityType"}; verified against the live endpoint, and the
shape this script stores keeps only the PRIMARY-typed outcomes, in the
registry's own order, renaming those two analysis fields to "p" and "design".

Ids in one chunk are 200 (CTGOV_CHUNK below) - empirically checked against
this endpoint at the URL that chunk size produces (~2.6 KB for 200
densely-packed ids) and at the larger response the results-section fields
add (~120 KB for 200 ids' worth of outcome data, still under half a second);
comfortably under any URL length limit and fast. pageSize=1000 is far above
that, so pagination is exercised in practice only if the endpoint ever
changes shape, and is implemented so a chunk larger than one page still
cannot silently truncate.

Usage:
    python3 scripts/resolve_cohort_trials.py             # resolve, write
    python3 scripts/resolve_cohort_trials.py --dry-run   # query, report only
    python3 scripts/resolve_cohort_trials.py --refresh   # re-check stored ids too
    python3 scripts/resolve_cohort_trials.py --limit 50  # smoke test

Idempotent and restartable: with no flags it only queries ids that either
have no row yet or whose row predates schema_version 2, so an interrupted
run - or an upgrade from the first shape of this script - can simply be
rerun. Nothing already stored under the current schema is re-fetched or
disturbed. A chunk that fails after retries leaves every id it was carrying
untouched (not "not found" - genuinely unresolved, and retried on the next
run); an id the registry legitimately does not return is "not found" and is
also left unstored, which means it too is retried on the next run rather than
being written as a negative result - CT.gov's coverage can catch up, an
import lag can resolve, and there is no column here for "confirmed absent"
the way `expressed_in_brain` has one (invariant 10 does not apply to a fact
this simple, but the caution does). --refresh re-fetches and upserts every
cited id, including ones already stored at the current schema version, which
is the only way a stored status changes to reflect a trial that has since
completed, stopped, or posted results.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sqlite3
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common

CTGOV_API = "https://clinicaltrials.gov/api/v2/studies"

# ClinicalTrials.gov does not require a registered User-Agent the way
# Wikidata's SPARQL endpoint does, but a descriptive one costs nothing and
# matches the courtesy the Wikidata backfill already extends.
CTGOV_USER_AGENT = (
    "SubNetwork/1.0 (cohort-1 drug-target interaction map; "
    "https://github.com/; contact via repository)"
)

CTGOV_FIELDS = ("NCTId,OverallStatus,WhyStopped,HasResults,LastUpdatePostDate,"
                 "StartDate,StartDateType,CompletionDate,CompletionDateType,"
                 "Phase,OutcomeMeasureType,OutcomeMeasureTitle,"
                 "OutcomeAnalysisPValue,OutcomeAnalysisNonInferiorityType")

# The schema version this build of the script writes. See the module
# docstring: NULL/1 marks a row from before phases/primary_outcomes existed,
# 2 one from before the start and completion dates, and a default run
# re-fetches those rows rather than trusting their NULLs.
SCHEMA_VERSION = 3

REQUEST_TIMEOUT = 60
REQUEST_RETRIES = 6
MAX_RETRY_DELAY = 30  # backoff caps at 3, 6, 12, 24, 30, 30s

# Politeness floor between requests to the same endpoint.
MIN_REQUEST_INTERVAL = 0.3
_last_request_at = 0.0

# See the module docstring: 200 ids keeps the request URL around 2.5 KB and
# well inside one API page (pageSize=1000), measured against this endpoint
# rather than assumed.
CTGOV_CHUNK = 200

# Kept byte-identical (column-for-column; whitespace need not match) to the
# CREATE TABLE in db/schema_cohort.sql, so this script can create trial_status
# on an already-built db/cohort1.db that predates the table, and a build that
# already has it is untouched (IF NOT EXISTS). See tests/test_cohort_trials.py
# for the check that holds these two in sync.
TRIAL_STATUS_DDL = """
CREATE TABLE IF NOT EXISTS trial_status (
    nct_id            TEXT PRIMARY KEY,
    overall_status    TEXT,
    why_stopped       TEXT,
    has_results       INTEGER,
    last_update       TEXT,
    phases            TEXT,
    primary_outcomes  TEXT,
    start_date        TEXT,
    start_date_type   TEXT,
    completion_date   TEXT,
    completion_date_type TEXT,
    schema_version    INTEGER,
    fetched_at        TEXT NOT NULL
)
"""

# Columns added after the first shape of this table shipped. Applied with
# ALTER TABLE ... ADD COLUMN to a table TRIAL_STATUS_DDL's IF NOT EXISTS left
# alone because it already existed - the migration CREATE TABLE cannot reach.
# Order doesn't matter to SQLite; kept in the same order as the DDL above for
# a reader comparing the two.
TRIAL_STATUS_MIGRATION_COLUMNS = [
    ("phases", "TEXT"),
    ("primary_outcomes", "TEXT"),
    ("start_date", "TEXT"),
    ("start_date_type", "TEXT"),
    ("completion_date", "TEXT"),
    ("completion_date_type", "TEXT"),
    ("schema_version", "INTEGER"),
]


class CtgovError(RuntimeError):
    """A ClinicalTrials.gov request failed after retries. Always fatal to the
    chunk that raised it - never swallowed into "no trials found"."""


def _throttle():
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _ctgov_get(params):
    """One retried HTTP GET against the CT.gov v2 studies endpoint. Raises
    CtgovError if every attempt fails - the caller must not treat that the
    same as a query that succeeded and returned no studies."""
    last_err = None
    for attempt in range(REQUEST_RETRIES):
        try:
            _throttle()
            resp = requests.get(
                CTGOV_API,
                params=params,
                headers={"User-Agent": CTGOV_USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as err:
            last_err = err
            status = getattr(getattr(err, "response", None), "status_code", None)
            # A 4xx (other than 429) is a malformed request, not a hiccup -
            # retrying it won't help and every chunk uses the same shape.
            if status is not None and 400 <= status < 500 and status != 429:
                raise CtgovError(f"CT.gov rejected the request: {err}") from err
            if attempt < REQUEST_RETRIES - 1:
                delay = min(3 * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"    CT.gov request failed ({type(err).__name__}), "
                      f"retrying in {delay}s...")
                time.sleep(delay)
    raise CtgovError(
        f"CT.gov request failed after {REQUEST_RETRIES} attempts: {last_err}"
    ) from last_err


def _fetch_chunk_studies(ids):
    """Fetch every study CT.gov returns for these NCT ids, following
    nextPageToken until it stops appearing. Raises CtgovError on failure -
    the whole chunk fails together, never partially applied."""
    studies = []
    page_token = None
    while True:
        params = {
            "filter.ids": ",".join(ids),
            "fields": CTGOV_FIELDS,
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _ctgov_get(params)
        studies.extend(data.get("studies", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return studies


def _extract_phases(proto):
    """proto = the study's protocolSection. Phases come back as a list
    (design can run more than one, e.g. a combined Phase 2/3), joined with
    '|' to match the shape trial_ids is already stored in. None - not "" -
    when the registry has no phase for this study at all, which is common
    for device and behavioral trials and is not the same fact as "not yet
    fetched" (schema_version carries that one)."""
    phases = (proto.get("designModule") or {}).get("phases")
    return "|".join(phases) if phases else None


def _extract_primary_outcomes(study):
    """study = one raw study dict. Returns a JSON string, or None when the
    study carries no resultsSection at all - which the registry omits
    entirely for a trial with no posted results, rather than sending an
    empty one, so its absence here is a fact about the study and not a
    parsing failure. When a resultsSection *is* present, every PRIMARY-typed
    outcome measure is kept, in the registry's own order, with its title and
    its statistical analyses (renamed pValue -> "p", nonInferiorityType ->
    "design" to keep the stored JSON terse); an outcome with no analyses
    recorded is still kept, as "analyses": [] rather than dropped, because
    "no statistical analysis was posted for this endpoint" is itself
    something the panel can say. Secondary and other-typed outcomes are not
    stored here at all - this column answers "did the thing the trial was
    actually powered to detect show a difference", not the whole results
    section."""
    if "resultsSection" not in study or study["resultsSection"] is None:
        return None
    outcome_measures = (
        (study["resultsSection"].get("outcomeMeasuresModule") or {})
        .get("outcomeMeasures") or []
    )
    primaries = []
    for outcome in outcome_measures:
        if outcome.get("type") != "PRIMARY":
            continue
        analyses = [
            {"p": a.get("pValue"), "design": a.get("nonInferiorityType")}
            for a in (outcome.get("analyses") or [])
        ]
        primaries.append({"title": outcome.get("title"), "analyses": analyses})
    return json.dumps(primaries)


def _parse_study(study):
    """One raw study dict -> a trial_status row, or None if it carries no
    nctId at all (defensive - every study the API returns has one)."""
    proto = study.get("protocolSection") or {}
    ident = proto.get("identificationModule") or {}
    status = proto.get("statusModule") or {}
    nct_id = ident.get("nctId")
    if not nct_id:
        return None
    last_update_struct = status.get("lastUpdatePostDateStruct") or {}
    start = status.get("startDateStruct") or {}
    completion = status.get("completionDateStruct") or {}
    has_results = study.get("hasResults")
    return {
        "nct_id": nct_id,
        "overall_status": status.get("overallStatus"),
        "why_stopped": status.get("whyStopped"),
        "has_results": None if has_results is None else (1 if has_results else 0),
        "last_update": last_update_struct.get("date"),
        "phases": _extract_phases(proto),
        "primary_outcomes": _extract_primary_outcomes(study),
        # Verbatim, with the type beside each: see the module docstring for
        # why an ESTIMATED date must never reach the page unmarked.
        "start_date": start.get("date"),
        "start_date_type": start.get("type"),
        "completion_date": completion.get("date"),
        "completion_date_type": completion.get("type"),
    }


def fetch_chunk(ids):
    """Query one chunk of NCT ids. Returns (matched, aliased): `matched` maps
    a *requested* nct_id to its parsed row; `aliased` is the set of nctIds
    CT.gov returned that were not among `ids` - a redirect or a merge, kept
    separate rather than guessed onto whichever requested id might have
    caused it (see the module docstring)."""
    requested = set(ids)
    matched = {}
    aliased = set()
    for raw in _fetch_chunk_studies(ids):
        row = _parse_study(raw)
        if row is None:
            continue
        if row["nct_id"] in requested:
            matched[row["nct_id"]] = row
        else:
            aliased.add(row["nct_id"])
    return matched, aliased


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ensure_table(conn):
    """Create trial_status if it does not exist yet (an already-built
    db/cohort1.db from before this table existed at all), then add any
    column a table that already exists is still missing (an already-built
    db/cohort1.db from the first shape of this script, before phases,
    primary_outcomes and schema_version existed). Both are idempotent and
    safe to call on every run."""
    conn.execute(TRIAL_STATUS_DDL)
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(trial_status)")}
    for name, coltype in TRIAL_STATUS_MIGRATION_COLUMNS:
        if name not in existing_columns:
            conn.execute(f"ALTER TABLE trial_status ADD COLUMN {name} {coltype}")


def all_cited_trial_ids(conn):
    """Every distinct NCT id cited anywhere in molecule_indications.trial_ids.
    Parsed in Python because the column is a '|'-joined blob, not a normal
    key - the same shape ChEMBL's indication_refs was stored in."""
    ids = set()
    for (blob,) in conn.execute(
            "SELECT trial_ids FROM molecule_indications WHERE trial_ids IS NOT NULL"):
        ids.update(blob.split("|"))
    ids.discard("")
    return ids


def resolve_trials(conn, dry_run=False, refresh=False, limit=None,
                    chunk_size=CTGOV_CHUNK, fetched_at=None):
    """Fill trial_status on an already-open connection to db/cohort1.db (or a
    database shaped like it). Never opens ChEMBL, never touches any table but
    trial_status, and commits nothing itself - the caller controls the
    transaction (main() below commits once at the end; a dry run never writes
    a row, by construction below, though it does create the table if
    missing - see the module docstring for why that is not a data write)."""
    fetched_at = fetched_at or _now_iso()
    _ensure_table(conn)

    cited = all_cited_trial_ids(conn)
    total = len(cited)
    candidates = sorted(cited)
    if not refresh:
        # "Already resolved" means resolved *under the current schema* - a
        # row written before phases/primary_outcomes existed (schema_version
        # NULL or < 2) is missing real data, not empty data, and stays a
        # candidate until it is re-fetched. See the module docstring.
        already = {row[0] for row in conn.execute(
            "SELECT nct_id FROM trial_status WHERE schema_version >= ?",
            (SCHEMA_VERSION,))}
        candidates = [i for i in candidates if i not in already]
    if limit:
        candidates = candidates[:int(limit)]

    resolved = not_found = aliased_total = failed = 0
    aliased_seen = set()
    for start in range(0, len(candidates), chunk_size):
        chunk_ids = candidates[start:start + chunk_size]
        try:
            matched, aliased = fetch_chunk(chunk_ids)
        except CtgovError as err:
            print(f"    CT.gov lookup failed for {len(chunk_ids)} id(s): {err}")
            failed += len(chunk_ids)
            continue
        for nct_id in chunk_ids:
            row = matched.get(nct_id)
            if row is None:
                not_found += 1
                continue
            resolved += 1
            if not dry_run:
                conn.execute(
                    "INSERT OR REPLACE INTO trial_status"
                    "(nct_id, overall_status, why_stopped, has_results,"
                    " last_update, phases, primary_outcomes, start_date,"
                    " start_date_type, completion_date, completion_date_type,"
                    " schema_version, fetched_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row["nct_id"], row["overall_status"], row["why_stopped"],
                     row["has_results"], row["last_update"], row["phases"],
                     row["primary_outcomes"], row["start_date"],
                     row["start_date_type"], row["completion_date"],
                     row["completion_date_type"], SCHEMA_VERSION, fetched_at))
        new_aliases = aliased - aliased_seen
        if new_aliases:
            aliased_total += len(new_aliases)
            aliased_seen |= new_aliases
            for a in sorted(new_aliases)[:5]:
                print(f"    CT.gov returned {a}, which was not requested in this "
                      "chunk - a redirect or merge, dropped rather than guessed onto"
                      " a requested id")

    print(f"  trials: {resolved}/{len(candidates)} queried resolved"
          f" ({total} distinct ids cited, {len(candidates)} queried)"
          + (f", {aliased_total} aliased/redirected (dropped)" if aliased_total else "")
          + (f", {failed} failed" if failed else "")
          + f", {not_found} not found")
    return {
        "total": total, "queried": len(candidates), "resolved": resolved,
        "not_found": not_found, "aliased": aliased_total, "failed": failed,
    }


def print_summary(summary):
    print("\nSummary")
    print("-------")
    print(f"trials: {summary['resolved']} resolved, {summary['not_found']} not found, "
          f"{summary['aliased']} aliased/redirected (dropped), "
          f"{summary['failed']} failed "
          f"(of {summary['queried']} queried, {summary['total']} distinct ids cited)")
    if summary["failed"]:
        print(f"\n{summary['failed']} id(s) failed after retries - rerun to retry "
              "them (unresolved ids are simply absent, not written as a negative "
              "result).")
    return summary["failed"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="query and report, write nothing")
    parser.add_argument("--refresh", action="store_true",
                        help="re-fetch ids that already have a stored status")
    parser.add_argument("--limit", type=int, default=None,
                        help="only consider the first N cited ids (for testing)")
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB,
                        help="path to the cohort database (default: db/cohort1.db)")
    args = parser.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    conn = sqlite3.connect(args.db)
    try:
        summary = resolve_trials(conn, dry_run=args.dry_run, refresh=args.refresh,
                                 limit=args.limit)
        if args.dry_run:
            conn.rollback()
            print("\n(dry run - nothing written)")
        else:
            conn.commit()
    finally:
        conn.close()

    failures = print_summary(summary)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
