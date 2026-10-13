"""Refuse a commit or a push that would publish a home path, a personal
address or a session link.

This repository is public, and so is every commit pushed to it. It began on
2026-10-10 as one snapshot of a private working copy, whose history carries
those things and was never pushed here (docs/PUBLISHING.md, *The GitHub
repository*). This keeps them from arriving afresh. The hooks in .githooks/
run it, once a clone has `git config core.hooksPath .githooks`:

    python3 scripts/privacy_check.py --staged           # pre-commit
    python3 scripts/privacy_check.py --pre-push REMOTE  # pre-push; refs on stdin
    python3 scripts/privacy_check.py --tree [REF]       # every tracked file at REF

A file is searched as text, inside gzip members, and inside a PDF's compressed
streams, where a rendered link to a local file hides. A push is searched commit
by commit, files, message and identities alike, because a leak fixed in a later
commit is still public in the earlier one. Any branch may be pushed, a
worktree's included, and each is searched the same way (CLAUDE.md, *Repository
and pushing*). Exits 1 naming each finding. A match is fixed and committed, never
waved through: `--no-verify` skips the hooks, and is not for that.
"""

from __future__ import annotations

import gzip
import pathlib
import re
import subprocess
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# What must not reach the public repository. Each is a pattern that has
# occurred in this project's history: a home directory in a path or link, the
# personal address older commits carry, a claude.ai session link, and a job
# directory.
FORBIDDEN = {
    "home directory": re.compile(rb"/home/[A-Za-z0-9_.-]+/"),
    "personal email": re.compile(rb"[A-Za-z0-9_.+-]+@gmail\.com"),
    "claude.ai session": re.compile(rb"claude\.ai/code/session"),
    "job directory": re.compile(rb"[.]claude/jobs/"),
}
# Each pattern is spelled so that its own source text does not match it, or
# this file would refuse itself.

ZERO = "0" * 40

_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)


def _views(name: str, data: bytes):
    """The byte strings a reader of this file could see."""
    yield data
    if name.endswith(".gz"):
        try:
            yield gzip.decompress(data)
        except (OSError, EOFError):
            pass
    if name.endswith(".pdf"):
        for m in _PDF_STREAM.finditer(data):
            try:
                yield zlib.decompress(m.group(1))
            except zlib.error:
                pass


def scan(name: str, data: bytes) -> list[str]:
    """The FORBIDDEN labels found in a file called name holding data."""
    hits = set()
    for view in _views(name, data):
        hits.update(label for label, rx in FORBIDDEN.items() if rx.search(view))
    return sorted(hits)


def _git(root: pathlib.Path, *args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin,
                          check=True, capture_output=True).stdout


def _blobs(root: pathlib.Path, shas: list[str]) -> dict[str, bytes]:
    """Each blob's contents, read in one `git cat-file --batch`."""
    if not shas:
        return {}
    out = _git(root, "cat-file", "--batch", stdin=("\n".join(shas) + "\n").encode())
    blobs, pos = {}, 0
    for sha in shas:
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        size = int(header[2])
        blobs[sha] = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    return blobs


def _raw_entries(raw: bytes) -> list[tuple[str, str]]:
    """(blob sha, path) for each added or changed file in -z --raw output."""
    fields = raw.split(b"\0")
    entries = []
    for meta, path in zip(fields[0::2], fields[1::2]):
        if not meta.startswith(b":"):
            continue
        new_sha = meta.split()[3].decode()
        if new_sha != ZERO:
            entries.append((new_sha, path.decode()))
    return entries


def _scan_entries(root: pathlib.Path, entries, where: str = "") -> list[tuple[str, str]]:
    names = {}
    for sha, path in entries:
        names.setdefault(sha, path)
    blobs = _blobs(root, list(names))
    return [(where + names[sha], label)
            for sha in names for label in scan(names[sha], blobs[sha])]


def staged(root: pathlib.Path = ROOT) -> list[tuple[str, str]]:
    """Findings in what is about to be committed, and in who is committing it."""
    raw = _git(root, "diff", "--cached", "--raw", "-z", "--no-abbrev", "--no-renames",
               "--diff-filter=ACMRT")
    found = _scan_entries(root, _raw_entries(raw))
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        ident = _git(root, "var", var)
        found += [(var.lower().replace("git_", "").replace("_ident", " identity"), label)
                  for label in scan("", ident)]
    return found


def commits(root: pathlib.Path, shas: list[str]) -> list[tuple[str, str]]:
    """Findings in each commit's files, message and identities."""
    found = []
    for sha in shas:
        short = sha[:7]
        meta = _git(root, "log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", sha)
        found += [(f"commit {short} (message or author)", label) for label in scan("", meta)]
        raw = _git(root, "diff-tree", "-r", "-m", "--root", "--no-commit-id", "--raw", "-z",
                   "--no-abbrev", "--no-renames", "--diff-filter=ACMRT", sha)
        found += _scan_entries(root, _raw_entries(raw), where=f"commit {short}: ")
    return found


def pre_push(root: pathlib.Path, remote: str, lines: list[str]) -> list[tuple[str, str]]:
    """Findings for a push, given git's pre-push stdin lines."""
    found = []
    for line in lines:
        if not line.strip():
            continue
        _lref, lsha, rref, rsha = line.split()
        if lsha == ZERO:
            continue  # deleting a remote ref publishes nothing
        exclude = [f"--remotes={remote}"]
        if rsha != ZERO and subprocess.run(["git", "-C", str(root), "cat-file", "-e", rsha],
                                           capture_output=True).returncode == 0:
            exclude.append(rsha)
        new = _git(root, "rev-list", lsha, "--not", *exclude).decode().split()
        found += commits(root, new)
    return found


def tree(root: pathlib.Path = ROOT, ref: str = "HEAD") -> list[tuple[str, str]]:
    """Findings in every tracked file at ref."""
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", ref)
    entries = []
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, sha = meta.split()
        if kind == b"blob":
            entries.append((sha.decode(), path.decode()))
    return _scan_entries(root, entries)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--staged"] and len(argv) == 1:
        found = staged()
    elif argv[:1] == ["--pre-push"] and len(argv) == 2:
        found = pre_push(ROOT, argv[1], sys.stdin.read().splitlines())
    elif argv[:1] == ["--tree"] and len(argv) <= 2:
        found = tree(ref=argv[1] if len(argv) == 2 else "HEAD")
    else:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    for where, label in found:
        print(f"refusing: {where}: {label}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
