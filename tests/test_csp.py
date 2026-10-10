"""Tests for scripts/csp.py, the Content-Security-Policy the hosted viewer is
served with.

The policy names the page's one inline script by its sha256. A hash that
missed would not degrade the page, it would stop it: the browser refuses to
run the script, and the reader gets an empty frame. So the first test is
against the real page, and the rest pin down the two things the hash cannot
cover - a second inline script, and an inline event handler.

Run with: python3 -m unittest discover -s tests
"""

import base64
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import csp  # noqa: E402


def sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


class TheRealPage(unittest.TestCase):
    def test_policy_hashes_the_page_s_one_inline_script(self):
        with open(ROOT / "viz" / "index.html", encoding="utf-8", newline="") as f:
            html = f.read()
        body = html.split("\n<script>", 1)[1].rsplit("</script>", 1)[0]
        policy = csp.policy(html)
        directives = dict(d.split(" ", 1) for d in policy.split("; "))
        self.assertEqual(directives["script-src"], "'self' " + sha(body))
        self.assertIn("default-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)


class Refusals(unittest.TestCase):
    def test_a_script_mentioned_in_a_comment_is_not_the_inline_one(self):
        html = "<!-- a plain <script> rather than fetch --><script src=a.js></script><script>go()</script>"
        self.assertEqual(csp.inline_script_hash(html), sha("go()"))

    def test_hashes_the_bytes_exactly_carriage_returns_included(self):
        self.assertEqual(csp.inline_script_hash("<script>a();\r\nb();</script>"), sha("a();\r\nb();"))

    def test_two_inline_scripts_are_refused(self):
        with self.assertRaisesRegex(ValueError, "found 2"):
            csp.inline_script_hash("<script>a()</script><script>b()</script>")

    def test_no_inline_script_is_refused(self):
        with self.assertRaisesRegex(ValueError, "found 0"):
            csp.inline_script_hash("<script src=a.js></script>")

    def test_an_inline_event_handler_is_refused(self):
        with self.assertRaisesRegex(ValueError, "event handler"):
            csp.inline_script_hash('<button onclick="go()">x</button><script>go()</script>')

    def test_handler_like_text_inside_the_script_is_not_a_handler(self):
        html = '<script>el.innerHTML = \'<b onclick="x">\';</script>'
        self.assertTrue(csp.inline_script_hash(html).startswith("'sha256-"))

    def test_cli_exits_nonzero_on_a_refused_page(self):
        import contextlib, io, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write("<p>no script</p>")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(csp.main([f.name]), 1)
        pathlib.Path(f.name).unlink()
        self.assertIn("found 0", err.getvalue())


if __name__ == "__main__":
    unittest.main()
