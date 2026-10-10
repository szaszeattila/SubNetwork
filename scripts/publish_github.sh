#!/usr/bin/env bash
# Publish the public GitHub copy: one snapshot commit of the committed tree,
# never this repository's history (docs/PUBLISHING.md, The public GitHub copy).
# scripts/public_snapshot.py stages the tree and refuses one that carries a
# home path, a personal address or a session link.
#
#   scripts/publish_github.sh --dry-run    # checks, stage, audit, commit; keeps
#                                          # the staged repository to inspect
#   scripts/publish_github.sh --private    # first publish only: create it
#                                          # private, to look at on GitHub first
#   scripts/publish_github.sh              # create it public, or add a snapshot
#   scripts/publish_github.sh --carried    # add a snapshot when the copy has a
#                                          # commit of its own (a merged pull
#                                          # request) already carried back here
#   scripts/publish_github.sh --go-public  # make a private copy public; nothing
#                                          # is pushed
#
# A new repository gets its description and topics; a public one also gets
# private vulnerability reporting (SECURITY.md), which GitHub offers only on
# public repositories. An existing repository is pushed to only if it carries
# the snapshot marker (.public-copy), which this repository never does, so a
# snapshot can never land on top of the full history. Needs `gh auth login`.
set -euo pipefail

PUBLIC_REPO=${PUBLIC_REPO:-szaszeattila/SubNetwork}
BRANCH=main
DESCRIPTION="An explorable map of drug-target interactions from ChEMBL and the Guide to Pharmacology: what molecules developed for the brain act on, and how well each claim is evidenced."
TOPICS="cheminformatics pharmacology chembl drug-target-interactions network-visualization"
MARKER=.public-copy
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

MODE=publish
case "${1:-}" in
  "") ;;
  --dry-run) MODE=dry-run ;;
  --private) MODE=private ;;
  --carried) MODE=carried ;;
  --go-public) MODE=go-public ;;
  *) echo "usage: $0 [--dry-run | --private | --carried | --go-public]" >&2; exit 2 ;;
esac

# Every remote of this repository is the private one. One naming the public
# copy would let an ordinary `git push` send it the whole history.
if git remote -v | grep -qi "github\.com[:/]$PUBLIC_REPO\(\.git\)\? "; then
  echo "refusing: a remote of this repository points at $PUBLIC_REPO:" >&2
  git remote -v >&2
  echo "point it at the private repository (git remote set-url)" >&2
  exit 1
fi

# GitHub answers a renamed repository's old name with the renamed one, so a
# name that comes back different is a redirect, and free to create.
VIEW=$(gh repo view "$PUBLIC_REPO" --json nameWithOwner,visibility \
       --jq '.nameWithOwner + " " + .visibility' 2>/dev/null || echo "- NONE")
VISIBILITY=${VIEW##* }
if [ "$(echo "${VIEW% *}" | tr A-Z a-z)" != "$(echo "$PUBLIC_REPO" | tr A-Z a-z)" ]; then
  [ "$VISIBILITY" = NONE ] || echo "$PUBLIC_REPO redirects to ${VIEW% *}; creating it ends the redirect"
  VISIBILITY=NONE
fi
if [ "$VISIBILITY" != NONE ] \
   && ! gh api "repos/$PUBLIC_REPO/contents/$MARKER?ref=$BRANCH" >/dev/null 2>&1; then
  echo "refusing: $PUBLIC_REPO exists and is not a snapshot copy (no $MARKER on $BRANCH)." >&2
  echo "Is it the private repository under its old name? Set PUBLIC_REPO." >&2
  exit 1
fi

if [ "$MODE" = go-public ]; then
  [ "$VISIBILITY" = PRIVATE ] || { echo "$PUBLIC_REPO is $VISIBILITY, not a private copy" >&2; exit 1; }
  gh repo edit "$PUBLIC_REPO" --visibility public --accept-visibility-change-consequences
  gh api -X PUT "repos/$PUBLIC_REPO/private-vulnerability-reporting" >/dev/null
  echo "https://github.com/$PUBLIC_REPO is public"
  exit 0
fi
if [ "$MODE" = private ] && [ "$VISIBILITY" != NONE ]; then
  echo "refusing: --private creates the copy, and $PUBLIC_REPO already exists ($VISIBILITY)" >&2
  exit 1
fi

# The snapshot is HEAD, so uncommitted work would be silently left out of it.
DIRTY=$(git status --porcelain --untracked-files=no)
if [ -n "$DIRTY" ]; then
  echo "refusing: tracked files differ from commit $(git rev-parse --short HEAD):" >&2
  echo "$DIRTY" >&2
  exit 1
fi

# The snapshot commit's author is the configured identity, so it must be the
# GitHub no-reply address, never a personal one.
EMAIL=$(git config user.email)
case "$EMAIL" in
  *@users.noreply.github.com) ;;
  *) echo "refusing: commit email $EMAIL is not a GitHub no-reply address" >&2; exit 1 ;;
esac

python3 -m unittest discover -s tests >/dev/null 2>&1 \
  || { echo "pipeline suite failed" >&2; exit 1; }
node --test "tests/*.test.mjs" >/dev/null 2>&1 \
  || { echo "viewer suite failed" >&2; exit 1; }

STAGE=$(mktemp -d)
[ "$MODE" = dry-run ] || trap 'rm -rf "$STAGE"' EXIT
REPO="$STAGE/repo"

if [ "$VISIBILITY" != NONE ]; then
  gh repo clone "$PUBLIC_REPO" "$REPO" -- -q --depth 1 --branch "$BRANCH"
  # A commit there that this script did not make is a contribution. Overlaying
  # the next snapshot would revert it, so it is carried back here first.
  if ! git -C "$REPO" log -1 --format=%B | grep -q '^Snapshot-Of: ' && [ "$MODE" != carried ]; then
    echo "refusing: $PUBLIC_REPO's $BRANCH has a commit this script did not make:" >&2
    git -C "$REPO" log -1 --format='  %h %an: %s' >&2
    echo "carry it into this repository, commit, and rerun with --carried" >&2
    exit 1
  fi
  find "$REPO" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  python3 scripts/public_snapshot.py "$STAGE/tree"
  cp -a "$STAGE/tree/." "$REPO/"
else
  python3 scripts/public_snapshot.py "$REPO"
  git -C "$REPO" init -q -b "$BRANCH"
fi

COMMIT=$(git rev-parse --short HEAD)
git -C "$REPO" add -A
if git -C "$REPO" diff --cached --quiet; then
  echo "nothing changed since the last snapshot"; exit 0
fi
# A contribution carried back here is committed with its author as a
# Co-authored-by trailer (CONTRIBUTING.md), and the snapshot that publishes it
# repeats every such trailer since the last snapshot, so GitHub credits them.
# The assistant's own trailer is not a contributor's and is left out.
TRAILERS=""
LAST=$( [ -d "$REPO/.git" ] && git -C "$REPO" log -1 --format=%B 2>/dev/null \
        | sed -n 's/^Snapshot-Of: //p' | head -1 || true)
if [ -n "$LAST" ] && git cat-file -e "$LAST^{commit}" 2>/dev/null; then
  TRAILERS=$(git log --format='%(trailers:key=Co-authored-by,valueonly)' "$LAST..HEAD" \
             | grep -iv 'anthropic\.com' | sed '/^$/d' | sort -u | sed 's/^/Co-authored-by: /')
fi
git -C "$REPO" -c user.name="$(git config user.name)" -c user.email="$EMAIL" \
  commit -q -m "Snapshot $(date -u +%Y-%m-%d)" -m "Snapshot-Of: $COMMIT${TRAILERS:+
$TRAILERS}"
git -C "$REPO" log -1 --stat --format='%h %an <%ae>%n%s' | tail -3

if [ "$MODE" = dry-run ]; then
  echo "dry run: not pushed; the staged repository is $REPO"
  exit 0
fi

if [ "$VISIBILITY" != NONE ]; then
  git -C "$REPO" push -q origin "$BRANCH"
else
  VIS=--public; [ "$MODE" = private ] && VIS=--private
  gh repo create "$PUBLIC_REPO" "$VIS" --description "$DESCRIPTION" \
    --source "$REPO" --remote origin --push
  for topic in $TOPICS; do gh repo edit "$PUBLIC_REPO" --add-topic "$topic" >/dev/null; done
  [ "$MODE" = private ] \
    || gh api -X PUT "repos/$PUBLIC_REPO/private-vulnerability-reporting" >/dev/null
fi
echo "published $COMMIT to https://github.com/$PUBLIC_REPO ($(gh repo view "$PUBLIC_REPO" --json visibility --jq .visibility))"
