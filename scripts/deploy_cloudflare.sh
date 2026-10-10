#!/usr/bin/env bash
# Deploy the cohort viewer to Cloudflare Workers static assets (the successor
# to Cloudflare Pages), evidence shards included, as the Worker named below.
# Who may open it is set by Cloudflare Access in the dashboard, not here.
#
# Ships five paths and nothing else (docs/HOSTING-REVIEW.md): index.html,
# vendor/, graph.data.js, gtopdb.data.js and evidence/, plus a _headers file
# and NOTICE as NOTICE.txt, the data's licences served beside the data.
# The two .data.js files come from one export and go together. The data is
# gitignored, so this uploads what is on disk now, after both suites and the
# Status check pass. Needs `wrangler login` once.
#
#   scripts/deploy_cloudflare.sh            # checks, stage, deploy to production
#   scripts/deploy_cloudflare.sh --preview  # checks, stage, upload to the staging
#                                           # preview URL; production untouched
#   scripts/deploy_cloudflare.sh --dry-run  # checks and stage only
#
# --preview is the private copy to work on (docs/PUBLISHING.md, The Cloudflare
# copy): a version uploaded but not deployed, at the stable alias URL
# staging-<worker>.<account>.workers.dev, behind Access like every preview URL.
# A production deploy refuses a page, NOTICE or CSP script that differs from
# the commit it names; a preview is for work in progress and says so instead.
# Every upload names the data build in its message, keeps a copy of exactly
# what it uploaded under deploys/ (gitignored), and checks that each URL wrangler
# reports answers with the Access login rather than the page.
set -euo pipefail

WORKER=subnetwork
PREVIEW_ALIAS=staging
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

MODE=deploy
case "${1:-}" in
  "") ;;
  --dry-run) MODE=dry-run ;;
  --preview) MODE=preview ;;
  *) echo "usage: $0 [--dry-run | --preview]" >&2; exit 2 ;;
esac

# The files that decide what the page is, besides the gitignored data.
SHIPPED_SOURCES="viz/index.html viz/vendor NOTICE scripts/csp.py"
DIRTY=$(git status --porcelain -- $SHIPPED_SOURCES)
if [ -n "$DIRTY" ] && [ "$MODE" = deploy ]; then
  echo "refusing to deploy to production: these differ from commit $(git rev-parse --short HEAD):" >&2
  echo "$DIRTY" >&2
  echo "commit them, or use --preview to check work in progress" >&2
  exit 1
fi

python3 -m unittest discover -s tests >/dev/null 2>&1 \
  || { echo "pipeline suite failed" >&2; exit 1; }
node --test "tests/*.test.mjs" >/dev/null 2>&1 \
  || { echo "viewer suite failed" >&2; exit 1; }
python3 scripts/cohort_report.py --check-status

[ -s viz/graph.data.js ] && [ -s viz/gtopdb.data.js ] && [ -d viz/evidence ] \
  || { echo "viz/graph.data.js, viz/gtopdb.data.js or viz/evidence/ missing; run the export" >&2; exit 1; }

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
SITE="$STAGE/assets"
mkdir "$SITE"
cp viz/index.html viz/graph.data.js viz/gtopdb.data.js "$SITE"/
cp -r viz/vendor viz/evidence "$SITE"/
cp NOTICE "$SITE/NOTICE.txt"

cat > "$STAGE/wrangler.jsonc" <<JSON
{
  "name": "$WORKER",
  "compatibility_date": "2026-10-01",
  "assets": { "directory": "./assets" }
}
JSON

# The CSP allows the page's own files and its one inline script by sha256,
# which changes with every edit, so it is computed from the page being staged
# (scripts/csp.py). A page whose hash this missed would not run at all.
# Permissions-Policy switches off browser features the page never uses, for it
# and anything it embeds; Cross-Origin-Opener-Policy cuts the link to windows
# of other sites that open it. Neither changes what the page does.
# no-cache is "revalidate every time", not "never cache": the file names are
# fixed, so a browser holding last deploy's graph.data.js must not pair it
# with this deploy's index.html or shards; unchanged files still answer 304.
CSP=$(python3 scripts/csp.py "$SITE/index.html")
cat > "$SITE/_headers" <<HEADERS
/*
  Cache-Control: no-cache
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  Cross-Origin-Opener-Policy: same-origin
  Content-Security-Policy: $CSP
HEADERS

# Workers Free: 20,000 asset files per version, 25 MiB per file.
FILES=$(find "$SITE" -type f | wc -l)
LARGEST=$(find "$SITE" -type f -printf '%s\n' | sort -n | tail -1)
echo "staged $FILES files, $(du -sh "$SITE" | cut -f1), largest $LARGEST bytes"
[ "$FILES" -le 20000 ] && [ "$LARGEST" -le 26214400 ] \
  || { echo "over the Workers Free limits" >&2; exit 1; }

# Which build is going live: the data is gitignored, so the commit alone
# does not say. Both stamps are in the first bytes of graph.data.js.
stamp() { head -c 4096 viz/graph.data.js | grep -o "\"$1\":\"[^\"]*\"" | head -1 | cut -d'"' -f4; }
BUILT=$(stamp built_at)
EXPORTED=$(stamp generated)
COMMIT=$(git rev-parse --short HEAD)
MESSAGE="commit $COMMIT${DIRTY:+ + uncommitted changes}, data built ${BUILT:-unknown}, exported ${EXPORTED:-unknown}"
echo "$MESSAGE"

if [ "$MODE" = dry-run ]; then
  cat "$SITE/_headers"
  echo "dry run: not deployed"
  exit 0
fi

# Exactly what was uploaded, since the data exists nowhere else once a rebuild
# replaces it: about 11 MB compressed per upload. Prune by hand.
mkdir -p deploys
ARCHIVE="deploys/$(date -u +%Y%m%dT%H%M%SZ)-$MODE-$COMMIT.tar.gz"
tar -czf "$ARCHIVE" -C "$SITE" .
echo "kept a copy of the upload as $ARCHIVE"

LOG="$STAGE/wrangler.log"
if [ "$MODE" = preview ]; then
  (cd "$STAGE" && wrangler versions upload --preview-alias "$PREVIEW_ALIAS" \
     --message "$MESSAGE") 2>&1 | tee "$LOG"
else
  (cd "$STAGE" && wrangler deploy --message "$MESSAGE") 2>&1 | tee "$LOG"
fi

# Private means the login page, not the site. A preview URL that serves the
# page is an exposure, so it fails the run; the production URL is reported,
# since it is meant to be public one day.
STATUS=0
for url in $(grep -o 'https://[a-z0-9.-]*\.workers\.dev' "$LOG" | sort -u); do
  ANSWER=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "$url/" || true)
  case "$ANSWER" in
    302\ https://*.cloudflareaccess.com/*) echo "behind Access: $url" ;;
    *) if [ "$MODE" = preview ]; then
         echo "NOT behind Access: $url answered ${ANSWER%% *}" >&2; STATUS=1
       else
         echo "answers without Access: $url (${ANSWER%% *})"
       fi ;;
  esac
done
exit $STATUS
