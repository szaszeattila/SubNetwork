"""Shared helpers for the cohort-1 clinical-catalogue report.

Every script in this directory opens ChEMBL and the project database
**read-only** and writes only under ``analysis/cohort1/``. Nothing here
touches the production schema, seed list, graph export or viewer.

Paths, the source manifest, and the deterministic CSV writer live here so
each step can be rerun on its own and produce byte-identical output.
"""

import csv
import datetime
import gzip
import hashlib
import json
import os
import pathlib
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = ROOT.parent.parent
CONFIG = ROOT / "config"
CACHE = ROOT / "cache"
OUT = ROOT / "out"
MANIFEST_PATH = ROOT / "MANIFEST.json"

CHEMBL_DB = pathlib.Path(
    os.environ.get(
        "CHEMBL_SQLITE_PATH",
        "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db",
    )
)
CHEMBL_RELEASE = "chembl_37"
def _find_project_db() -> pathlib.Path:
    """Locate the built project database.

    ``db/subnetwork.db`` is gitignored, so it exists only where a build was
    run. When this analysis runs from a git worktree under
    ``<repo>/.claude/worktrees/<name>/`` the file lives in the main checkout,
    three levels up. It is only ever opened read-only.
    """
    env = os.environ.get("SUBNETWORK_DB")
    if env:
        return pathlib.Path(env)
    here = PROJECT / "db" / "subnetwork.db"
    if here.exists():
        return here
    parts = PROJECT.parts
    if len(parts) >= 3 and parts[-3:-1] == (".claude", "worktrees"):
        main = pathlib.Path(*parts[:-3]) / "db" / "subnetwork.db"
        if main.exists():
            return main
    return here


PROJECT_DB = _find_project_db()

# The 28 molecules the running pipeline seeds, in seed order. Mirrored here
# (rather than imported from scripts/build_db.py) so this analysis never
# imports production code that could reach the network on import.
SEED_MOLECULES = [
    ("caffeine", "CHEMBL113"),
    ("theophylline", "CHEMBL1355736"),
    ("theobromine", "CHEMBL1114"),
    ("istradefylline", "CHEMBL431770"),
    ("rolipram", "CHEMBL63"),
    ("cilostazol", "CHEMBL799"),
    ("donepezil", "CHEMBL502"),
    ("pentoxifylline", "CHEMBL628"),
    ("sildenafil", "CHEMBL192"),
    ("verapamil", "CHEMBL6966"),
    ("rivastigmine", "CHEMBL636"),
    ("tacrine", "CHEMBL95"),
    ("selegiline", "CHEMBL972"),
    ("cannabidiol", "CHEMBL190461"),
    ("haloperidol", "CHEMBL54"),
    ("clozapine", "CHEMBL42"),
    ("amitriptyline", "CHEMBL629"),
    ("loperamide", "CHEMBL841"),
    ("dextromethorphan", "CHEMBL52440"),
    ("memantine", "CHEMBL807"),
    ("lamotrigine", "CHEMBL741"),
    ("dipyridamole", "CHEMBL932"),
    ("vardenafil", "CHEMBL1520"),
    ("dronabinol", "CHEMBL465"),
    ("phenelzine", "CHEMBL1089"),
    ("quinidine", "CHEMBL1294"),
    ("galantamine", "CHEMBL659"),
    ("mibefradil", "CHEMBL45816"),
]


def chembl() -> sqlite3.Connection:
    """Open the pinned ChEMBL bulk release read-only."""
    if not CHEMBL_DB.exists():
        raise SystemExit(f"ChEMBL release not found at {CHEMBL_DB}")
    # ``mode=ro`` is the read-only guarantee: SQLite refuses every write to the
    # release file itself. ``query_only`` is deliberately NOT set, because it
    # also blocks the in-memory TEMP tables these steps use to hold the
    # candidate molregno set; temp tables never touch the release.
    conn = sqlite3.connect(f"file:{CHEMBL_DB}?mode=ro", uri=True)
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.row_factory = sqlite3.Row
    return conn


def project_db() -> sqlite3.Connection | None:
    """Open the project's built database read-only, or None if absent."""
    if not PROJECT_DB.exists():
        return None
    conn = sqlite3.connect(f"file:{PROJECT_DB}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def load_config(name: str) -> dict:
    with open(CONFIG / name) as fh:
        return json.load(fh)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(name: str, fieldnames: list[str], rows, *,
              compress: bool = False) -> pathlib.Path:
    """Write a report table deterministically (LF endings, fixed column order).

    ``compress`` gzips the table and appends ``.gz``. Used for the four
    row-level tables, which run to tens of megabytes uncompressed; they stay
    complete and machine-readable, they just do not enter git at full size.
    Read one with ``gzip.open(path, "rt")`` or ``pandas.read_csv(path)``.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (name + ".gz" if compress else name)
    opener = (lambda: gzip.open(path, "wt", newline="\n", encoding="utf-8")) if compress \
        else (lambda: open(path, "w", newline="\n", encoding="utf-8"))
    with opener() as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        n = 0
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
            n += 1
    print(f"  wrote {path.relative_to(PROJECT)}  ({n} rows)")
    return path


def read_csv(name: str) -> list[dict]:
    """Read a table written by write_csv, transparently handling the .gz form."""
    path = OUT / name
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    gz = OUT / (name + ".gz")
    if gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    raise FileNotFoundError(f"{path} (and {gz.name}) not found")


def write_json(name: str, payload) -> pathlib.Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    print(f"  wrote {path.relative_to(PROJECT)}")
    return path


# --------------------------------------------------------------------------
# Source manifest
# --------------------------------------------------------------------------

def record_source(key: str, **fields) -> None:
    """Add or replace one entry in MANIFEST.json.

    Every external input the report reads gets an entry: URL, retrieval date,
    checksum, access status and licence. Failed fetches are recorded too, with
    ``access_status`` set to the failure, so an absent source stays visible in
    the report instead of silently becoming a negative finding.
    """
    manifest = {}
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as fh:
            manifest = json.load(fh)
    manifest.setdefault("sources", {})
    fields.setdefault("retrieved", datetime.date.today().isoformat())
    manifest["sources"][key] = fields
    manifest["updated"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


def http_get(url: str, params: dict | None = None, *, tries: int = 4,
             timeout: int = 120, accept: str | None = None,
             post: bool = False) -> bytes:
    """HTTP GET (or form-encoded POST) with bounded retries and backoff.

    A 4xx other than 408/429 is a permanent answer, so it is raised at once
    rather than retried. Callers record the failure in the manifest rather
    than treating it as an empty result.
    """
    body = None
    headers = {
        "User-Agent": "SubNetwork-cohort1-report/1.0 (research; contact via repository)",
    }
    if accept:
        headers["Accept"] = accept
    if post:
        body = urllib.parse.urlencode(params or {}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif params:
        url = url + "?" + urllib.parse.urlencode(params)

    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                raise RuntimeError(
                    f"{'POST' if post else 'GET'} {url[:100]}: "
                    f"HTTP {exc.code} {exc.reason}") from exc
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{'POST' if post else 'GET'} failed after {tries} tries: "
                       f"{url[:100]}: {last}")


def log(msg: str) -> None:
    print(msg, flush=True)
