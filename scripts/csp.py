#!/usr/bin/env python3
"""Print the Content-Security-Policy the hosted viewer is served with.

The page is one HTML file with one inline <script>, so the policy allows
scripts from its own origin (the vendored library, the two data files and the
evidence shards) and that one inline script by its sha256, which changes with
every edit to the page - so it is computed here, at deploy time, from the file
being deployed, rather than written down anywhere. Styles need
'unsafe-inline' whatever the script does: the page's markup carries style=""
attributes it builds as strings. Nothing is fetched, framed or posted.

    python3 scripts/csp.py viz/index.html
"""

import base64
import hashlib
import re
import sys

# The page's own <!-- comments --> mention "<script>" in prose, so they are
# taken out before looking; a bare <script> tag is the inline one, and one
# carrying src= is a file the 'self' source already covers.
COMMENT = re.compile(r"<!--.*?-->", re.S)
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
# An inline handler (onclick="...") is not covered by a script hash, so the
# page must not have one; it has none, and inline_script_hash refuses a page
# that grows one rather than deploying a page that silently does nothing.
INLINE_HANDLER = re.compile(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", re.S)


def inline_script_hash(html: str) -> str:
    """The CSP source for the page's one inline script; raises unless one."""
    markup = COMMENT.sub("", html)
    scripts = INLINE_SCRIPT.findall(markup)
    if len(scripts) != 1:
        raise ValueError(f"expected one inline <script>, found {len(scripts)}")
    if INLINE_HANDLER.search(INLINE_SCRIPT.sub("", markup)):
        raise ValueError("an inline event handler would be blocked by the CSP")
    digest = hashlib.sha256(scripts[0].encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def policy(html: str) -> str:
    return "; ".join([
        "default-src 'none'",
        "script-src 'self' " + inline_script_hash(html),
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ])


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    # newline="" keeps the bytes as they are on disk: the browser hashes the
    # script exactly as served, carriage returns and all.
    with open(args[0], encoding="utf-8", newline="") as f:
        html = f.read()
    try:
        print(policy(html))
    except ValueError as err:
        print(f"csp: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
