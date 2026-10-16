#!/usr/bin/env python3
"""Read the FDA marketing category of every DailyMed label ChEMBL calls an approval.

ChEMBL files a disease as Approved (`drug_indication.max_phase_for_ind = 4`)
when a US label names it, and cites the label by its DailyMed set id. A label
is not an approval. FDA lets a product be sold, and its label be published in
DailyMed, without approving it: the label's own "Marketing Category" says so,
as UNAPPROVED DRUG OTHER, and carries FDA's notice that "this drug has not
been found by FDA to be safe and effective". Isometheptene was Approved for
migraine here on five such labels and nothing else; FDA never approved it
(docs/DATA-QUALITY-LOG.md, 2026-10-15; docs/COHORT-2.md, D23).

Two steps, run in order, then rebuild.

`fetch` reads every DailyMed label behind a phase-4 drug_indication record in
the whole ChEMBL release that cites no FDA or EMA document - the records whose
approval rests on a label, whichever molecule they belong to, so a change of
selection policy never meets an unchecked one. For each label it keeps what
the label says about how its products are marketed: category, application
number or monograph citation, and dates. Identifiers only (invariant 15): the
set id is the one ChEMBL cites, the page is fetched by it, and nothing is
matched on a name. DailyMed's structured API serves only current labels and
answers 404 for an archived one (all five of isometheptene's), so the label
page is read, which serves both; it is kept gzipped under db/cache/dailymed/,
so a parser change never refetches.

`write` classifies each record from its labels (`verdict`), reads from
ClinicalTrials.gov the registry phase of any trial an unapproved record also
cites, and writes config/cohort1_label_status.json. The build reads that file
and nothing on the network (scripts/cohort/labels.py): what DailyMed says
enters the catalogue only through a committed file whose diff names every
disease that changed - the shape of a documented exclusion (invariant 9),
generated rather than typed because there are hundreds. `--dry-run` prints
the counts and writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import gzip
import html
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from cohort import common, labels as labels_mod  # noqa: E402

CACHE = ROOT / "db" / "cache" / "dailymed"
HTML_DIR = CACHE / "html"
LABELS = CACHE / "labels.json"

LABEL_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={}"
USER_AGENT = (
    "SubNetwork/1.0 (cohort-1 drug-target interaction map; "
    "https://github.com/; contact via repository)"
)
WORKERS = 4
SET_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


# ---------------------------------------------------------------- parsing

_HEADER = re.compile(r"<th\b[^>]*>\s*Marketing Category\s*</th>.*?</tr>", re.S | re.I)
_ROW = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", fragment))).strip()


def parse_label(page: str) -> dict:
    """What a DailyMed label page says about how its products are marketed.

    Every product on a label has a "Marketing Information" table whose header
    row is Marketing Category / Application Number or Monograph Citation /
    Marketing Start Date / Marketing End Date; a kit repeats it per part. The
    rows are returned in page order, de-duplicated. A label that states no
    category - some current ones carry no marketing section at all, in the
    page or in the SPL itself - returns none, and is never read as
    unapproved. `found` is False on DailyMed's search page, which is what
    the address serves for a set id it does not hold.
    """
    m = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    title = _text(m.group(1)) if m else ""
    title = re.sub(r"^DailyMed\s*-?\s*", "", title) or None
    m = re.search(r"Labeler\s*-\s*</span>(.*?)</td>", page, re.S | re.I)
    labeler = re.sub(r"\s*\(\d+\)\s*$", "", _text(m.group(1))) if m else None
    rows, seen = [], set()
    # Read from each header row to the end of its own table. Matching whole
    # tables instead would start at an enclosing layout table and swallow the
    # first marketing table inside it.
    for header in _HEADER.finditer(page):
        end = page.lower().find("</table>", header.end())
        for tr in _ROW.findall(page[header.end():end if end >= 0 else None]):
            cells = [_text(c) for c in _CELL.findall(tr)]
            if len(cells) != 4:
                continue
            row = (cells[0].upper(), cells[1] or None, cells[2] or None, cells[3] or None)
            if row not in seen:
                seen.add(row)
                rows.append(dict(zip(("category", "application", "start", "end"), row)))
    return {"found": title is not None, "title": title, "labeler": labeler,
            "marketing": rows}


# ---------------------------------------------------------------- fetch

def _load_labels() -> dict:
    return json.loads(LABELS.read_text()) if LABELS.exists() else {}


def _save_labels(labels: dict) -> None:
    tmp = LABELS.with_suffix(".tmp")
    tmp.write_text(json.dumps(labels, indent=0, sort_keys=True))
    os.replace(tmp, LABELS)


def _get(session: requests.Session, set_id: str) -> tuple[int, str]:
    delay = 2.0
    for attempt in range(4):
        try:
            r = session.get(LABEL_URL.format(set_id), timeout=60)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            return r.status_code, r.text
        except requests.exceptions.RequestException:
            if attempt == 3:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def fetch(set_ids: list[str], refresh: bool = False) -> dict:
    """Fetch, cache and parse each label; a cached page is parsed again, never refetched."""
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    labels = _load_labels()
    todo = [s for s in set_ids if refresh or s not in labels]
    print(f"{len(set_ids)} set ids cited, {len(set_ids) - len(todo)} parsed already, "
          f"{len(todo)} to read")
    local = threading.local()

    def one(set_id: str) -> tuple[str, dict]:
        path = HTML_DIR / f"{set_id}.html.gz"
        if path.exists() and not refresh:
            status, page = 200, gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
            fetched = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        else:
            if not hasattr(local, "s"):
                local.s = requests.Session()
                local.s.headers["User-Agent"] = USER_AGENT
            status, page = _get(local.s, set_id)
            if status == 200:
                path.write_bytes(gzip.compress(page.encode("utf-8")))
            fetched = dt.datetime.now(dt.timezone.utc)
        rec = parse_label(page) if status == 200 else {
            "found": False, "title": None, "labeler": None, "marketing": []}
        rec["http_status"] = status
        rec["fetched_at"] = fetched.strftime("%Y-%m-%dT%H:%M:%SZ")
        return set_id, rec

    done = 0
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for set_id, rec in pool.map(one, todo):
            labels[set_id] = rec
            done += 1
            if done % 250 == 0:
                _save_labels(labels)
                print(f"  {done}/{len(todo)}", flush=True)
    _save_labels(labels)
    return labels


def reparse() -> dict:
    """Parse every cached page again, after a parser change."""
    labels = _load_labels()
    for set_id, rec in labels.items():
        path = HTML_DIR / f"{set_id}.html.gz"
        if path.exists():
            new = parse_label(gzip.decompress(path.read_bytes()).decode("utf-8", "replace"))
            rec.update(new)
    _save_labels(labels)
    return labels


# ---------------------------------------------------------------- classify

def verdict(set_ids: list[str], labels: dict) -> str:
    """One record's verdict from its labels (see scripts/cohort/labels.py).

    `label`: a label holds an application (NDA, ANDA, BLA, an authorised
    generic). `monograph`: none does, and one is sold under an FDA OTC
    monograph. `unapproved`: every label was read, and each states only
    categories that are not an approval. `unresolved`: anything else - a
    label not found, one stating no category, or a category this script does
    not know - so ChEMBL's Approved stands for want of a reading, never on a
    guess either way.
    """
    cats = []
    unreadable = False
    for s in set_ids:
        rec = labels.get(s)
        if not rec or not rec.get("found") or not rec["marketing"]:
            unreadable = True
            continue
        cats.extend(m["category"] for m in rec["marketing"])
    kinds = {labels_mod.category_kind(c) for c in cats}
    if "application" in kinds:
        return "label"
    if "monograph" in kinds:
        return "monograph"
    if unreadable or None in kinds or not kinds:
        return "unresolved"
    return "unapproved"


def _label_detail(set_id: str, labels: dict) -> dict:
    rec = labels.get(set_id) or {}
    rows = rec.get("marketing") or []
    starts = [r["start"] for r in rows if r["start"]]
    ends = [r["end"] for r in rows if r["end"]]
    return {
        "set_id": set_id,
        "title": rec.get("title"),
        "labeler": rec.get("labeler"),
        "categories": sorted({r["category"] for r in rows}),
        # the earliest start and, only where every product has ended, the
        # latest end: a label still on sale has no end
        "marketed_from": min(starts, key=_date_key) if starts else None,
        "marketed_until": (max(ends, key=_date_key)
                           if ends and len(ends) == len(rows) else None),
    }


def _date_key(mmddyyyy: str):
    m, d, y = (mmddyyyy.split("/") + ["", "", ""])[:3]
    return (y, m, d)


REGISTRY_PHASE = {"EARLY_PHASE1": 0.5, "PHASE1": 1.0, "PHASE2": 2.0,
                  "PHASE3": 3.0, "PHASE4": 4.0}


def trial_phases(ncts: list[str]) -> dict[str, str | None]:
    """The registry's own phases for each NCT id, '|'-joined, by identifier."""
    import resolve_cohort_trials as ct
    out: dict[str, str | None] = {}
    for i in range(0, len(ncts), 200):
        for study in ct._fetch_chunk_studies(ncts[i:i + 200]):
            proto = study.get("protocolSection") or {}
            nct = (proto.get("identificationModule") or {}).get("nctId")
            if nct:
                out[nct] = ct._extract_phases(proto)
    return out


def write(dry_run: bool = False) -> int:
    conn = common.chembl()
    records = labels_mod.label_backed_records(conn)
    conn.close()
    labels = _load_labels()
    by_verdict: dict[str, list[int]] = collections.defaultdict(list)
    for rid, rec in sorted(records.items()):
        by_verdict[verdict(rec["dailymed"], labels)].append(rid)

    detail = {}
    for v in ("unapproved", "unresolved"):
        for rid in by_verdict[v]:
            rec = records[rid]
            detail[str(rid)] = {
                "verdict": v,
                "molregno": rec["molregno"],
                "mesh_id": rec["mesh_id"],
                "labels": [_label_detail(s, labels) for s in rec["dailymed"]],
                "trials": rec["trials"],
            }

    ncts = sorted({t for d in detail.values() if d["verdict"] == "unapproved"
                   for t in d["trials"]})
    phases = trial_phases(ncts) if ncts and not dry_run else {}
    missing = [t for t in ncts if t not in phases]
    for d in detail.values():
        if d["verdict"] != "unapproved":
            continue
        d["trials"] = [{"nct": t, "phases": phases.get(t)} for t in d["trials"]]
        ps = [REGISTRY_PHASE[p] for t in d["trials"] if t["phases"]
              for p in t["phases"].split("|") if p in REGISTRY_PHASE]
        d["trial_phase"] = max(ps) if ps else None

    counts = {v: len(ids) for v, ids in sorted(by_verdict.items())}
    print(f"{len(records)} phase-4 records rest on DailyMed labels with no FDA or EMA "
          f"document: {counts}")
    unknown = collections.Counter(
        m["category"] for rec in labels.values() for m in rec.get("marketing") or []
        if labels_mod.category_kind(m["category"]) is None)
    if unknown:
        print(f"categories not classified (their records stay unresolved): {dict(unknown)}")
    if missing and not dry_run:
        print(f"{len(missing)} cited NCT ids the registry did not return: {missing[:10]}")
    if dry_run:
        return 0

    fetched = [labels[s]["fetched_at"] for r in records.values() for s in r["dailymed"]
               if s in labels]
    out = {
        "policy_id": "cohort1-label-status",
        "version": "1.0.0",
        "decision": "D23 (docs/COHORT-2.md)",
        "chembl_release": common.CHEMBL_RELEASE,
        "generated_by": "scripts/check_dailymed_labels.py",
        "labels_read": {"from": "DailyMed label pages, by the set id ChEMBL cites",
                        "first": min(fetched) if fetched else None,
                        "last": max(fetched) if fetched else None},
        "summary": counts,
        "checked": {v: by_verdict[v] for v in ("label", "monograph")},
        "records": detail,
    }
    labels_mod.STATUS_FILE.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {labels_mod.STATUS_FILE.relative_to(ROOT)}")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch and parse every cited label")
    f.add_argument("--refresh", action="store_true", help="refetch cached labels")
    sub.add_parser("reparse", help="parse the cached pages again")
    w = sub.add_parser("write", help="classify and write the config file")
    w.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        conn = common.chembl()
        records = labels_mod.label_backed_records(conn)
        conn.close()
        cited = {s for r in records.values() for s in r["dailymed"]}
        bad = sorted(s for s in cited if not SET_ID.match(s))
        if bad:
            print(f"{len(bad)} DailyMed refs are not set ids and are not fetched: {bad[:5]}")
        fetch(sorted(s for s in cited if SET_ID.match(s)), refresh=args.refresh)
    elif args.cmd == "reparse":
        reparse()
    else:
        return write(args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
