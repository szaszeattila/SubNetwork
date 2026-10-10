"""Tests for scripts/privacy_check.py, which keeps a home path, a personal
address and a session link out of this public repository, and every branch but
main on this machine.

The check is the only thing between those and GitHub, so it is tested against
each place a leak has hidden: plain text, a gzip member, a PDF's compressed
stream, a commit's identity, and a commit a later one fixed. The script's own
source must pass its own check, because its patterns are spelled so they do not
match themselves, and this repository's tracked tree must pass it too.

The sample leaks below are assembled from pieces for the same reason as the
script's patterns: this file is committed and would otherwise fail the check.

Run with: python3 -m unittest discover -s tests
"""

import gzip
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import privacy_check  # noqa: E402

HOME_PATH = "/ho" + "me/someone/x"
EMAIL = "a.b@gm" + "ail.com"
SESSION = "https://claude.ai/co" + "de/session_abc"
JOB = "~/.cla" + "ude/jobs/1234/tmp"

# A scratch repository must not read the user's git configuration (a global
# hooksPath would run these very hooks) and needs an identity of its own.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@users.noreply.github.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@users.noreply.github.com",
}


class Scan(unittest.TestCase):
    def test_clean_text_and_gzip_have_no_findings(self):
        self.assertEqual(privacy_check.scan("README.md", b"nothing to see here\n"), [])
        self.assertEqual(privacy_check.scan("x.json.gz", gzip.compress(b'{"a": 1}')), [])

    def test_each_forbidden_pattern_is_reported_with_its_label(self):
        cases = {
            "home directory": HOME_PATH,
            "personal email": EMAIL,
            "claude.ai session": SESSION,
            "job directory": JOB,
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                data = ("see " + text + " for more\n").encode()
                self.assertEqual(privacy_check.scan("notes.txt", data), [label])

    def test_gzip_is_read_decompressed(self):
        raw = gzip.compress(("path " + HOME_PATH + "/\n").encode() * 50)
        self.assertNotIn(b"/ho" + b"me/", raw)
        self.assertEqual(privacy_check.scan("logs/out.txt.gz", raw), ["home directory"])

    def test_pdf_stream_is_read_decompressed(self):
        packed = zlib.compress(("(link) " + HOME_PATH + "/file.html").encode())
        pdf = (b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + packed
               + b"\nendstream\nendobj\n%%EOF\n")
        self.assertNotIn(b"/ho" + b"me/", pdf)
        self.assertEqual(privacy_check.scan("docs/report.pdf", pdf), ["home directory"])

    def test_the_script_s_own_source_passes_its_own_check(self):
        src = ROOT / "scripts" / "privacy_check.py"
        self.assertEqual(privacy_check.scan(src.name, src.read_bytes()), [])


@unittest.skipUnless((ROOT / ".git").exists(), "not a git checkout")
class ThisRepository(unittest.TestCase):
    def test_every_tracked_file_at_head_is_clean(self):
        self.assertEqual(privacy_check.tree(ROOT), [])


class GitCase(unittest.TestCase):
    """A scratch repository, with a bare one standing in for GitHub."""

    def setUp(self):
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        self.remote = pathlib.Path(tmp.name) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        self.git("remote", "add", "origin", str(self.remote))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, rel, text, message="change"):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.git("add", rel)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def push_lines(self, local, remote_ref="refs/heads/main", remote_sha=privacy_check.ZERO):
        return [f"refs/heads/x {self.git('rev-parse', local)} {remote_ref} {remote_sha}"]


class Staged(GitCase):
    def test_a_clean_staged_file_passes(self):
        (self.repo / "a.txt").write_text("fine\n")
        self.git("add", "a.txt")
        self.assertEqual(privacy_check.staged(self.repo), [])

    def test_a_leak_in_a_staged_file_is_refused(self):
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "a.md").write_text("see " + HOME_PATH + "\n")
        self.git("add", "docs/a.md")
        self.assertEqual(privacy_check.staged(self.repo), [("docs/a.md", "home directory")])

    def test_only_the_staged_version_counts(self):
        (self.repo / "a.txt").write_text("fine\n")
        self.git("add", "a.txt")
        (self.repo / "a.txt").write_text(EMAIL + "\n")
        self.assertEqual(privacy_check.staged(self.repo), [])

    def test_a_personal_commit_identity_is_refused(self):
        (self.repo / "a.txt").write_text("fine\n")
        self.git("add", "a.txt")
        with mock.patch.dict(os.environ, {"GIT_AUTHOR_EMAIL": EMAIL}):
            self.assertEqual(privacy_check.staged(self.repo),
                             [("author identity", "personal email")])


class PrePush(GitCase):
    def test_a_clean_push_of_main_passes(self):
        self.commit("a.txt", "fine\n")
        self.assertEqual(privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD")), [])

    def test_any_other_branch_is_refused_unscanned(self):
        self.commit("a.txt", "fine\n")
        found = privacy_check.pre_push(self.repo, "origin",
                                       self.push_lines("HEAD", "refs/heads/wip"))
        self.assertEqual([where for where, _ in found], ["refs/heads/wip"])

    def test_a_tag_may_be_pushed(self):
        self.commit("a.txt", "fine\n")
        found = privacy_check.pre_push(self.repo, "origin",
                                       self.push_lines("HEAD", "refs/tags/v1.0"))
        self.assertEqual(found, [])

    def test_deleting_a_remote_branch_publishes_nothing(self):
        lines = [f"(delete) {privacy_check.ZERO} refs/heads/wip {'1' * 40}"]
        self.assertEqual(privacy_check.pre_push(self.repo, "origin", lines), [])

    def test_a_leak_fixed_by_a_later_commit_is_still_refused(self):
        self.commit("a.txt", "fine\n")
        leaked = self.commit("a.txt", "see " + SESSION + "\n")
        self.commit("a.txt", "fine again\n")
        found = privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD"))
        self.assertEqual(found, [(f"commit {leaked[:7]}: a.txt", "claude.ai session")])

    def test_a_leak_in_a_commit_message_is_refused(self):
        sha = self.commit("a.txt", "fine\n", message="from " + JOB)
        found = privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD"))
        self.assertEqual(found, [(f"commit {sha[:7]} (message or author)", "job directory")])

    def test_a_personal_author_is_refused(self):
        with mock.patch.dict(os.environ, {"GIT_AUTHOR_EMAIL": EMAIL}):
            sha = self.commit("a.txt", "fine\n")
        found = privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD"))
        self.assertEqual(found, [(f"commit {sha[:7]} (message or author)", "personal email")])

    def test_commits_already_on_the_remote_are_not_rescanned(self):
        self.commit("a.txt", "see " + HOME_PATH + "\n")
        subprocess.run(["git", "-C", str(self.repo), "push", "-q", "--no-verify",
                        "origin", "main"], check=True)
        self.commit("b.txt", "fine\n")
        self.assertEqual(privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD")), [])

    def test_a_leak_merged_in_from_a_branch_is_refused(self):
        self.commit("a.txt", "fine\n")
        self.git("checkout", "-q", "-b", "side")
        leaked = self.commit("b.txt", EMAIL + "\n")
        self.git("checkout", "-q", "main")
        self.commit("c.txt", "fine\n")
        self.git("merge", "-q", "--no-edit", "side")
        found = privacy_check.pre_push(self.repo, "origin", self.push_lines("HEAD"))
        self.assertIn((f"commit {leaked[:7]}: b.txt", "personal email"), found)


if __name__ == "__main__":
    unittest.main()
