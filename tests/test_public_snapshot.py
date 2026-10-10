"""Tests for scripts/public_snapshot.py, which stages the public copy of the
repository and refuses a leaky one.

The audit is the only thing between a private home directory, a personal
address or a session link and a public repository, so it is tested against each
place a leak has hidden: plain text, a gzip member, and a PDF's compressed
stream. The script's own source must pass its own audit, because its patterns
are spelled so they do not match themselves. Every EXCLUDED path must be
tracked, so a rename cannot silently publish what it keeps back, and one
end-to-end test exports HEAD and audits the result.

The sample leaks below are assembled from pieces for the same reason as the
script's patterns: this file is committed and would otherwise fail the audit.

Run with: python3 -m unittest discover -s tests
"""

import gzip
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import public_snapshot  # noqa: E402

HOME_PATH = "/ho" + "me/someone/x"
EMAIL = "a.b@gm" + "ail.com"
SESSION = "https://claude.ai/co" + "de/session_abc"
JOB = "~/.cla" + "ude/jobs/1234/tmp"

# The private repository, where EXCLUDED's files are tracked. The public copy
# is a git checkout too, but one that by design has none of them, and carries
# the marker the export writes.
PRIVATE_REPO = (ROOT / ".git").exists() and not (ROOT / public_snapshot.MARKER).exists()


class AuditCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tree = pathlib.Path(tmp.name)

    def put(self, rel, data):
        path = self.tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path


class Audit(AuditCase):
    def test_clean_text_and_gzip_have_no_findings(self):
        self.put("README.md", "nothing to see here\n")
        self.put("data/x.json.gz", gzip.compress(b'{"a": 1}'))
        self.assertEqual(public_snapshot.audit(self.tree), [])

    def test_each_forbidden_pattern_is_reported_with_its_label(self):
        cases = {
            "home directory": HOME_PATH,
            "personal email": EMAIL,
            "claude.ai session": SESSION,
            "job directory": JOB,
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                tree = self.tree / label.replace(" ", "_").replace(".", "_")
                tree.mkdir()
                (tree / "notes.txt").write_text("see " + text + " for more\n")
                self.assertEqual(public_snapshot.audit(tree), [("notes.txt", label)])

    def test_findings_are_relative_posix_path_and_label_tuples(self):
        self.put("a/b/c.txt", HOME_PATH)
        found = public_snapshot.audit(self.tree)
        self.assertEqual(found, [("a/b/c.txt", "home directory")])
        self.assertIsInstance(found[0], tuple)

    def test_gzip_is_read_decompressed(self):
        raw = gzip.compress(("path " + HOME_PATH + "/\n").encode() * 50)
        self.assertNotIn(b"/ho" + b"me/", raw)
        self.put("logs/out.txt.gz", raw)
        self.assertEqual(public_snapshot.audit(self.tree), [("logs/out.txt.gz", "home directory")])

    def test_pdf_stream_is_read_decompressed(self):
        packed = zlib.compress(("(link) " + HOME_PATH + "/file.html").encode())
        pdf = b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + packed + b"\nendstream\nendobj\n%%EOF\n"
        self.assertNotIn(b"/ho" + b"me/", pdf)
        self.put("docs/report.pdf", pdf)
        self.assertEqual(public_snapshot.audit(self.tree), [("docs/report.pdf", "home directory")])

    def test_git_directory_is_ignored(self):
        self.put(".git/config", HOME_PATH + "/\n")
        self.put("kept.txt", "clean\n")
        self.assertEqual(public_snapshot.audit(self.tree), [])


class SelfAudit(AuditCase):
    def test_the_script_s_own_source_passes_its_own_audit(self):
        src = ROOT / "scripts" / "public_snapshot.py"
        self.put("scripts/public_snapshot.py", src.read_bytes())
        self.assertEqual(public_snapshot.audit(self.tree), [])


@unittest.skipUnless(PRIVATE_REPO, "not the private repository")
class Excluded(unittest.TestCase):
    def test_every_excluded_path_is_tracked(self):
        for rel in public_snapshot.EXCLUDED:
            with self.subTest(path=rel):
                r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)


class Export(AuditCase):
    def test_a_non_empty_destination_is_refused(self):
        self.put("already/here.txt", "x")
        with self.assertRaises(SystemExit) as cm:
            public_snapshot.export_tree(self.tree)
        self.assertIn("not empty", str(cm.exception))

    @unittest.skipUnless(PRIVATE_REPO, "not the private repository")
    def test_head_exports_without_excluded_paths_and_audits_clean(self):
        dest = self.tree / "out"
        paths = public_snapshot.export_tree(dest)
        self.assertTrue(paths)
        self.assertTrue((dest / public_snapshot.MARKER).exists())
        for rel in public_snapshot.EXCLUDED:
            with self.subTest(path=rel):
                self.assertFalse((dest / rel).exists())
                self.assertNotIn(rel, paths)
        self.assertEqual(public_snapshot.audit(dest), [])


if __name__ == "__main__":
    unittest.main()
