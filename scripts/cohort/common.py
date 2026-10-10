"""Paths, pinned inputs, config loading and small shared helpers.

Nothing in this module reaches the network. The ChEMBL release is opened
read-only and never written to, and the policy configs are hashed into the
build manifest so a database can always say which rules produced it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import sqlite3
import statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config"
DB = ROOT / "db"
STAGING = DB / "staging"
BACKUPS = DB / "backups"
VIZ = ROOT / "viz"
VIZ_BACKUPS = VIZ / "backups"

# The active cohort database. Deliberately NOT db/subnetwork.db: that file is
# the legacy six-source build, and leaving it alone is most of the rollback
# path (see docs/COHORT-1-IMPLEMENTATION.md).
COHORT_DB = DB / "cohort1.db"
STAGING_DB = STAGING / "cohort1.db"

CHEMBL_RELEASE = "chembl_37"
CHEMBL_DB = pathlib.Path(
    os.environ.get(
        "CHEMBL_SQLITE_PATH",
        "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db",
    )
)

# The pinned MeSH descriptor classification (decision D14). This is a saved
# output of the September 2026 report, not a fresh ontology fetch: the raw
# mesh_tree.tsv cache is gone, and refetching MeSH now would be a different
# snapshot wearing the same name.
MESH_SCOPE_CSV = ROOT / "analysis" / "cohort1" / "out" / "indication_scope.csv"


class PolicyError(RuntimeError):
    """A pinned input or policy invariant did not hold. Always fatal."""


def chembl() -> sqlite3.Connection:
    """Open the pinned ChEMBL bulk release read-only.

    ``mode=ro`` is the guarantee that this build cannot write to the release.
    ``query_only`` is deliberately not set: the selection step holds its
    candidate molregnos in a TEMP table, which never touches the release file.
    """
    if not CHEMBL_DB.exists():
        raise PolicyError(
            f"pinned ChEMBL release not found at {CHEMBL_DB}. This build never "
            f"falls back to a live release or another snapshot. Download "
            f"{CHEMBL_RELEASE}_sqlite.tar.gz and set CHEMBL_SQLITE_PATH to the "
            f"extracted {CHEMBL_RELEASE}.db (docs/REPRODUCING.md)."
        )
    conn = sqlite3.connect(f"file:{CHEMBL_DB}?mode=ro", uri=True)
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.row_factory = sqlite3.Row
    return conn


def load_policy(name: str) -> dict:
    path = CONFIG / name
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def policy_fingerprint(name: str) -> dict:
    policy = load_policy(name)
    return {
        "file": f"config/{name}",
        "policy_id": policy.get("policy_id"),
        "version": policy.get("version"),
        "sha256": sha256(CONFIG / name),
    }


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_median(values) -> float:
    """Median in log10 space. Affinities are log-normal (CLAUDE.md invariant 3)."""
    return 10 ** statistics.median([math.log10(v) for v in values])


def log_spread(values) -> float:
    """log10(max/min) - the dispersion measure the conflict rule uses."""
    lo, hi = min(values), max(values)
    return math.log10(hi / lo) if lo > 0 else 0.0


PHASE_LABEL = {
    4.0: "Approved",
    3.0: "Phase 3",
    2.0: "Phase 2",
    1.0: "Phase 1",
    0.5: "Early Phase 1",
    -1.0: "Unknown (ChEMBL -1)",
}


def phase_label(value) -> str:
    """Label a clinical phase without folding Missing and Unknown into zero."""
    if value is None:
        return "Missing (no phase recorded)"
    return PHASE_LABEL.get(float(value), f"Other ({value})")


def log(msg: str) -> None:
    print(msg, flush=True)


def chunked(items, size: int = 900):
    """SQLite's parameter limit makes every IN (...) query a chunked one."""
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]
