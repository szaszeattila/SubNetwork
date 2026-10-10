"""Stage the public GitHub copy of this repository, and refuse a leaky one.

The public repository is a fresh copy, one snapshot commit per publish, never
this repository's history (docs/HOSTING-REVIEW-ANSWERS.md, second round): the
history carries a personal address and private session links, and rewriting it
would still leave the old commits reachable on GitHub. So the public copy is
the committed tree at HEAD, minus EXCLUDED, and its only audit is of that tree.

    python3 scripts/public_snapshot.py DEST    # export HEAD to DEST and audit it

Exits 1, naming each file and what it matched, when anything in the staged tree
matches FORBIDDEN: inside text, inside gzip members, and inside a PDF's
compressed streams, where a rendered link to a local file hides. A match is
fixed in the private repository and committed, never waved through here.
scripts/publish_github.sh runs this and publishes only a clean tree.
"""

from __future__ import annotations

import gzip
import io
import pathlib
import re
import subprocess
import sys
import tarfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Tracked here, never published. Each names why; a path that no longer exists
# fails the export, so a rename cannot quietly publish what this kept back.
EXCLUDED = {
    "docs/archive/cohort-report-2026-09-12/zotero-annotations.json":
        "the reviewer's own questions, which the live report answers",
    "docs/archive/cohort-report-2026-09-12/COHORT-REPORT.pdf":
        "its links are paths on the machine it was rendered on",
}

# What must not reach the public copy. Each is a pattern that has occurred in
# this repository: a home directory in a path or link, the personal address
# older commits carry, a claude.ai session link, and a job directory.
FORBIDDEN = {
    "home directory": re.compile(rb"/home/[A-Za-z0-9_.-]+/"),
    "personal email": re.compile(rb"[A-Za-z0-9_.+-]+@gmail\.com"),
    "claude.ai session": re.compile(rb"claude\.ai/code/session"),
    "job directory": re.compile(rb"[.]claude/jobs/"),
}
# Each pattern is spelled so that its own source text does not match it, or
# this file would refuse itself.

# Written into every snapshot and never committed here, so a checkout can tell
# which copy it is: the tests that check EXCLUDED against this repository's
# files skip in the public copy, which by design has none of them.
MARKER = ".public-copy"
MARKER_TEXT = ("This is the public copy of SubNetwork, published as snapshots of a\n"
               "private working copy by scripts/publish_github.sh. See CONTRIBUTING.md.\n")

_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)


def export_tree(dest: pathlib.Path, ref: str = "HEAD") -> list[str]:
    """Write the tree at ref into dest (which must be empty), minus EXCLUDED.

    Returns the published paths. Uses git archive, so only committed, tracked
    files can reach the public copy: nothing gitignored, nothing uncommitted.
    """
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise SystemExit(f"{dest} is not empty")
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", ref],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        names = {m.name for m in tar.getmembers() if m.isfile()}
        missing = sorted(set(EXCLUDED) - names)
        if missing:
            raise SystemExit("EXCLUDED names paths not in the tree: " + ", ".join(missing))
        members = [m for m in tar.getmembers() if m.name not in EXCLUDED]
        tar.extractall(dest, members=members, filter="data")
    (dest / MARKER).write_text(MARKER_TEXT)
    return sorted((names - set(EXCLUDED)) | {MARKER})


def _views(path: pathlib.Path, data: bytes):
    """The byte strings a reader of this file could see."""
    yield data
    if path.suffix == ".gz":
        try:
            yield gzip.decompress(data)
        except (OSError, EOFError):
            pass
    if path.suffix == ".pdf":
        for m in _PDF_STREAM.finditer(data):
            try:
                yield zlib.decompress(m.group(1))
            except zlib.error:
                pass


def audit(tree: pathlib.Path) -> list[tuple[str, str]]:
    """Every (relative path, FORBIDDEN label) found in the staged tree."""
    found = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        rel = path.relative_to(tree).as_posix()
        if rel.startswith(".git/"):
            continue
        hits = set()
        for view in _views(path, path.read_bytes()):
            hits.update(label for label, rx in FORBIDDEN.items() if rx.search(view))
        found.extend((rel, label) for label in sorted(hits))
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(f"usage: {pathlib.Path(sys.argv[0]).name} DEST", file=sys.stderr)
        return 2
    dest = pathlib.Path(argv[0])
    paths = export_tree(dest)
    found = audit(dest)
    for rel, label in found:
        print(f"refusing: {rel} contains a {label}", file=sys.stderr)
    if found:
        return 1
    print(f"staged {len(paths)} files in {dest}; {len(EXCLUDED)} kept back; audit clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
