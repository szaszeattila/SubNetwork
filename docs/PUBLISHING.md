# Publishing the cohort viewer

**The viewer is hosted on Cloudflare only.** Its claude.ai artifact was
deleted on 2026-10-10 at the user's request, after version 28, so that two
shareable copies with the same links could not drift apart
([HOSTING-REVIEW.md](HOSTING-REVIEW.md), *Two public copies will drift*). The
procedure is **The Cloudflare copy**, at the end of this file. Everything
between here and there is the artifact's record: how it was republished, the
refusals that procedure met, its version history, and why it never carried
the evidence shards. Kept as history, not as a procedure. The artifact's link
no longer works, and publishing the page again would create a new artifact at
a new address.

The code's GitHub repository, what may be pushed to it and how it goes public,
is **The GitHub repository**, at the very end.

## The artifact (deleted 2026-10-10)

How to republish `viz/index.html` to its claude.ai artifact without the
refusals that most republishes have hit first. Written 2026-09-26 from the
transcripts of every earlier publish of this artifact, and followed for
version 22, which went through on the first call.

The artifact was https://claude.ai/artifact/RDfcNKHA4zEZPNjmgZdvJf. It held
five files: `index.html` (the page), `graph.data.js`, `gtopdb.data.js`,
`NOTICE.txt` and `vendor/vis-network.min.js`. The evidence shards are not
published and cannot be (see **Why the evidence shards are not published**
below).

**The two data files always go together.** GtoPdb's part of the export travels
in its own file, because its database is ODbL and its contents CC BY-SA 4.0
while ChEMBL is CC BY-SA 3.0, and no published compatibility joins the ODbL to
CC BY-SA (`scripts/cohort/export.py` has the reasoning). The page merges the
two only when both carry the same export stamp, so a `graph.data.js` sent
without the `gtopdb.data.js` from the same export leaves GtoPdb out. About says
the hosted copy serves the data's terms as `NOTICE.txt`; `NOTICE` is published
under that name (`{"from": ".../NOTICE", "contentType": "text/plain"}`) and
re-sent whenever it changes. All three went up together for the first time in
version 28.

### The procedure

Every step is needed. The server refuses a republish from any session that has
not *viewed* the version currently live, and viewing has a strict meaning.

1. **Check the page is ready.** `node --test "tests/*.test.mjs"` and
   `python3 -m unittest discover -s tests` pass, and `python3
   scripts/cohort_report.py --check-status` exits 0. If a test count changed,
   run `--write-status` first.

2. **Read the live version.** `Artifact` with `action: "read"` and the URL. It
   saves the full live HTML to a file under the session's `tool-results/`
   directory and says how many lines it has. The result says it plainly:
   *"this version counts as viewed only once you have Read every line of that
   file"*. The read action alone does **not** count.

3. **Read every line of that saved file with the Read tool**, start to end.
   It is about 6,900 lines and 330 KB, which is over the Read tool's size limit,
   so read it in chunks of about 1,200 lines (`offset` 1, 1201, 2401, …) until
   the last line. The last line has no trailing newline, so `wc -l` reports
   one fewer than the count the read result gives. Read through the number the
   *result* gives. Do not edit the file.

4. **Check nothing was published from elsewhere.** The saved file is the page
   wrapped in one line of host scaffolding at the top and two at the bottom.
   Strip those and diff against the committed page:

   ```bash
   F=<the saved file>
   N=$(wc -l < "$F")
   sed -n "2,$((N - 1))p" "$F" > /tmp/live.html   # drop the host's wrapper lines
   git show HEAD:viz/index.html | diff - /tmp/live.html
   ```

   Keep `/tmp/live.html` inside the job's own tmp directory when running as a
   background job. No difference means the live page is the last committed one,
   and your working copy can be published over it. Any other difference is a
   publish from somewhere else. Merge it before going on, or it is lost.

5. **Publish by absolute path**, page only unless the data changed:

   ```json
   {"action": "publish",
    "url": "https://claude.ai/artifact/RDfcNKHA4zEZPNjmgZdvJf",
    "file_path": "/…/SubNetwork/.claude/worktrees/<worktree>/viz/index.html"}
   ```

   Leave out `files` when `graph.data.js` and the vendor library have not
   changed. Files left out are kept as they are. To check, compare
   `stat -c %s viz/graph.data.js` with the size last recorded under
   **Version history** below.
   Pass no `icon` on a republish, and never pass `force`.

6. **Record it.** Add the version to **Version history** below: the number,
   the date, what changed, and whether `graph.data.js` was re-sent (with its
   size). Update the one-line **Published snapshot** in `../CLAUDE.md` to
   name the new version. Then commit.

### When `graph.data.js` did change

It is 5.7 MB and a supporting file, so it has its own viewed check. Before
publishing it, `Artifact` `read` with `url` and `path: "graph.data.js"` (and
`path: "gtopdb.data.js"` once that is published, and
`path: "vendor/vis-network.min.js"` if the library changed too). Then publish
with a `files` map using absolute source paths. The two data files come from
one export and always go together:

```json
{"action": "publish",
 "url": "https://claude.ai/artifact/RDfcNKHA4zEZPNjmgZdvJf",
 "file_path": "/…/viz/index.html",
 "files": {"graph.data.js": "/…/viz/graph.data.js",
           "gtopdb.data.js": "/…/viz/gtopdb.data.js"}}
```

The published paths, the keys, must stay `graph.data.js` and
`gtopdb.data.js`, which are the paths the page asks for. Never
`viz/graph.data.js`.

### The refusals, and what each one means

These are the three that have actually happened, with how often, counted over
18 earlier session transcripts.

**"You hadn't viewed the live version of this artifact, so the publish was
refused."** This happened 9 times. It means step 3 was skipped: the session
called `read` and then went straight to publishing. The fix is to Read every
line of the saved file the refusal names, then publish again.

**"Publish refused — nothing was merged or published: this is the identical
content already refused against the newer version…, resent unchanged."** This
happened 7 times, every one straight after the first refusal. It means the same
publish call was resent without doing anything about the first refusal. The
server treats that as a blind retry. What worked every time was a fresh `read`
of the URL, the full Read of the file it saves, and then one publish. The two
sessions that did the full Read after the first refusal never saw this one.

**"This publish touches files whose published content is not what you last
saw… 'graph.data.js'"** This happened once. The publish carried a `files`
entry for a supporting file that had not been read in that session. Either
leave the file out (it is kept) or `read` it with `path` first. That session
also used relative source paths, and every other successful publish used
absolute ones.

None of these was ever a permanent failure. Versions 1–22 all landed. Each one
is the server asking for proof that a newer version is not about to be
overwritten. Steps 2–4 give that proof and also check it yourself.

### What not to do

- Do not publish without `url`. That creates a second, separate artifact
  rather than a new version of this one.
- Do not pass `force: true`. It discards whatever is live, which is the loss
  the viewed check exists to prevent.
- Do not inline the data or the library into the page. That was how the legacy
  viewer was published, and it is no longer needed. The host takes supporting
  files, so the published copy and the local one are the same bytes.
- Do not try to publish `viz/evidence/`. It is over both the file-count and
  size limits (see **Why the evidence shards are not published** below).

### Version history

Newest first. Moved here from `CLAUDE.md` on 2026-09-27. First published
2026-09-21 from the `db/cohort1.db` build of 2026-09-16.

Version 28 (2026-10-10), from commit `6a7de33`, the first since version 27 and
so carrying everything between them: GtoPdb's part of the payload in its own
`gtopdb.data.js` (129,385 bytes) and the data's terms as `NOTICE.txt`, both
published for the first time; the permanent disclaimer and the About panel;
the selection and filters in a shareable URL fragment; one node per protein
across species, with a panel section per record; the lit-first click; "cohort
1" off the heading; and alfuzosin's alpha-1 AGONIST withheld as a known ChEMBL
error (`CHEMBL_MECHANISM_ACTION_EXCLUSIONS`, evidence policy 1.1.0), with the
panel saying so. `graph.data.js` was re-sent (5,740,367 bytes, from a rebuild
of the same day), and all three data files were checked sha256-identical to
the local export after publishing. The live page was read in full first and
was identical to commit `acfc8da`, the version 27 republish. It went through
on the first call.
Version 27 (2026-10-04), from commit `acfc8da`: one protein counted once
across species, matched by sequence (D20), with a protein's species records
grouped under one heading in the pair panel and the score names linking to
their blocks; each clinical trial's years, with a planned date worded as
planned and a phase's latest trial first; species named on non-human target
headings; ChEMBL's validity flags explained; four hover texts trimmed; the
gesture bitmap's pan copied at whole device pixels; and every panel section
starting folded. `graph.data.js` was re-sent (5,871,165 bytes, now carrying
`human_orthologue`) and checked sha256-identical to the local export after
publishing. The live page was read in full first and was identical to commit
`81a7943`, the version 26 republish. It went through on the first call.
Version 26 (2026-09-27), the first with cohort 2 on it, from commit `81a7943`:
GtoPdb's curated actions read as directions beside ChEMBL's (D17), the
mechanism filter and line colour reading them, GtoPdb primary-target rows as
Supported claims in the `gtopdb` role (D18), and a partial agonist against an
antagonist or inverse agonist counted as half an opposite (D19). GtoPdb is
credited on the page (CC BY-SA 4.0). `graph.data.js` was re-sent (5,734,065
bytes) and checked sha256-identical to the local export after publishing. The
live page was read in full first and was identical to commit `79f2cce`, the
version 25 republish. It went through on the first call.
Version 25 (2026-09-27), from the rebuild under selection policy 2.1.0 (D16: Anxiety, Depression, Smoking
Cessation and Anesthesia in scope). It also carries the approval line naming
what an approved drug is approved for, the removal of the membership line and
the seed flags, the hover explanations on **Why this score**, and the MeSH
structure classes, which version 24 did not have. `graph.data.js` was re-sent
(5,573,896 bytes). The live page was read in full first and was identical to
commit `37082ec`, and the live `graph.data.js` was checked sha256-identical to
the local export after publishing. It went through on the first call.
Version 24 (2026-09-26) had
the **MeSH pharmacological actions** searchable and openable as classes, and
the ATC classes taken back off the page; `graph.data.js` was re-sent
(5,397,311 bytes).
Version 23 had **searchable drug classes** (every ATC code and USAN name stem,
and a class panel) and the "Action or measurement" rename; `graph.data.js` was
re-sent (5,416,944 bytes). Version 22 had the **‹ Back** button; only the page changed. Version 21 had
the similarity list renamed **Closest target profiles**, each row stating its
overlap against both profiles and the targets carrying its score, and the pair
panel's **Why this score** breakdown; only the page changed. Version 20 had
a target's claims grouped by tier or curated mechanism under the molecule
panel's toggle, the species on every claim row, the membership fold flattened to
one line and the retained claims folded; only the page changed, and
`graph.data.js` was checked the same size as the published copy and was not
re-sent. Version 19 had
the molecule panel's measured claims grouped under Binding and Functional rather
than "No curated mechanism" when grouping by mechanism; only the page changed,
and `graph.data.js` was checked the same size as the published copy and was not
re-sent. Version 18 made every panel heading foldable, the panel itself
foldable, and added Clear selection. Version 17 grouped an edge's claims under their mechanism and
named retained observations as retained claims. Version 16 made the molecule panel's
claims groupable by curated mechanism and moved the retained observations to
the bottom. Version 15 had a
complex lighting its subunits and the smaller, foldable legend. Version 14
added the ion-channel units and also republished `graph.data.js`, which now
carries each component's protein class. Version 13 took the selection's bands
back off, version 12 had added them with the protein-group membership lines,
and version 11 added keyboard search, the evidence-ordered target Molecules
list and the shortened panel prose. The library file published with version 9
is kept as it was.

### Why the evidence shards were not published

**It is not inlined**, and the inlining this section used to describe is no
longer the way to do it. The artifact host takes supporting files, so the page
is published exactly as it sits on disk — `viz/index.html` with
`graph.data.js` and `vendor/vis-network.min.js` beside it at the same relative
paths the page already asks for. The published copy and the local one are the
same bytes, which is worth more than the single file was: there is no cutting
step to get wrong, and no half-inlined page to ship. The limits it is measured
against are per text file 16 MB, per version 64 MB and 255 files; this is three
files and 5.3 MB.

**What is missing is the individual measurement rows**, and the reason is the
same one this section has always given. The 71.7 MB of per-molecule shards is
1,176 files against a 255-file limit and 71.7 MB against a 64 MB one, so it
fails both, and neither is close enough to trim: the rows are already a columnar
`fields`-plus-array format, and no single field is more than 12% of the bulk.
Gzipped they are 9.9 MB and would fit easily, but nothing decompresses them —
the page loads a shard as a plain `<script>` tag precisely so that it works off
`file://` with no server, and fetch-plus-`DecompressionStream` is a second load
path that only the published copy would ever run. That is the open question,
and it is a real piece of work rather than a setting.

Shipping *some* of the shards was considered and rejected: a page where some
molecules have their rows and others do not, with no rule saying which, is worse
than one where none do.

What the published page therefore loses is narrower than "the evidence", and
was checked rather than assumed. The molecule panel, the pair panel, every claim
block, the tiers and the routes, the medians and the endpoint classes, the
counts of measurements and studies, the similarity ranking, search, the
indications and the trial links all come from `graph.data.js` and are intact.
What needs a shard is the list of individual rows inside a claim's
**Measurements** disclosure, the curated claim's references, and the
retained-observations list. Those report themselves as a missing file, which is
what the page already says and is still true — "that is a missing file, not an
absence of evidence".

## The Cloudflare copy

Since 2026-10-10 the viewer runs on Cloudflare Workers static assets, the
successor to Cloudflare Pages (wrangler now routes its `pages` commands to
Workers), **with** the evidence shards. It is the one hosted copy. Its
addresses are in the Cloudflare dashboard, not in this repository.

### Deploying

Run the script once `wrangler login` has been run on the machine:

```bash
scripts/deploy_cloudflare.sh --dry-run   # checks and stage; prints the headers and the message
scripts/deploy_cloudflare.sh --preview   # upload to the private staging alias; production untouched
scripts/deploy_cloudflare.sh             # deploy to production
```

Every mode runs both suites and `--check-status` first. It then stages
`index.html`, `graph.data.js`, `gtopdb.data.js`, `vendor/`, `evidence/`,
`NOTICE` as `NOTICE.txt` (the data's licences, beside the data) and a
`_headers` file. Only changed files are uploaded.

- **Work on the staging copy first.** `--preview` uploads a version without
  deploying it, at the stable alias `staging-subnetwork.<account>.workers.dev`.
  The upload is allowed to carry uncommitted changes, and its message says so.
  It is the private copy to work on once production is public. Each
  `--preview` moves the alias to the newest upload.
- **Production names what it serves.** A production deploy refuses to run
  when `viz/index.html`, `viz/vendor/`, `NOTICE` or `scripts/csp.py` differs
  from the commit. Every message names the commit and the data's `built_at`
  and `generated` stamps (the data is gitignored, so the commit alone does not
  say which build went live). `wrangler versions list --name subnetwork`
  shows them.
- **What was uploaded is kept.** Each upload is archived under `deploys/`
  (gitignored, about 11 MB). Once a rebuild replaces the data, that archive is
  the only copy of what went live. Prune it by hand.
- **Access is checked after every upload.** The script requests each URL
  wrangler printed. For a preview, any URL that serves the page instead of
  redirecting to the `cloudflareaccess.com` login fails the run. For
  production it only reports the answer, since production is meant to be
  public one day.
- **Undo:** `wrangler rollback --name subnetwork` makes the previous version
  the deployment again, or pass a version id from `wrangler versions list`.

### Headers

`_headers` carries the Content-Security-Policy that `scripts/csp.py` computes
from the staged page. Its `script-src` names the inline script by sha256, so
the page is only ever served with the policy of its own bytes, and a page
edited by hand on the server would not run.

The file also sets:

- `Cache-Control: no-cache` on every file, because the names are fixed and a
  browser must not pair one deploy's page with another's data;
- `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`;
- since 2026-10-10, `Permissions-Policy` (camera, microphone, geolocation,
  payment and USB off) and `Cross-Origin-Opener-Policy: same-origin`.

### Who may open it

Who may open it is set in the dashboard, not by the script. Cloudflare Access
covers the production URL and every preview hostname of the Worker. That was
checked on 2026-10-10: the main URL, three version preview URLs, the
`staging` alias and an unused alias name all answered `302` to the Access
login. The policy admits only members of the Cloudflare account. To admit
others, add an **Emails** rule to that policy. An email *domain* rule for a
public mail provider would admit everyone who uses that provider.

When production goes public, take Access off the production (workers.dev)
route only. Then confirm that a preview URL still answers `302`. Cloudflare's
documentation says Access can cover production, previews or both, but it
does not promise that removing one leaves the other in place. The
`--preview` check will catch an exposed preview on the next upload. Checking
by hand right away catches it sooner.

## The GitHub repository

This repository is `szaszeattila/SubNetwork`, and it is where the work is
done. It began on 2026-10-10 as one snapshot commit of a private working copy,
`szaszeattila/SubNetwork-private`, which is archived read-only on GitHub. That
copy keeps the history from before the snapshot, which is never pushed here:
it carries a personal address and private session links, and rewriting it
would still leave the old commits reachable on GitHub by their hashes
([HOSTING-REVIEW-ANSWERS.md](HOSTING-REVIEW-ANSWERS.md), second round). It
also keeps the two files the snapshot left out, the archived report's Zotero
annotation export and its PDF, whose links are paths on the machine the PDF
was rendered on.

The first plan was to keep working privately and publish a snapshot of the
private copy each time (`scripts/publish_github.sh`, since removed). The user
dropped it the same day, before the repository went public, because each
contribution would have had to be carried back by hand and would have
reappeared under a snapshot commit instead of its own.

### Pushing

**Unfinished work stays on this machine** (the user's decision, 2026-10-10).
Work happens on local branches and worktrees. Only `main` is pushed, and only
finished work is merged into it. Nothing pushed can be taken back: a deleted
branch's commits stay reachable by their hashes, and a fork keeps its own copy.
A local branch is also not backed up anywhere, so a worktree's branch is
merged or kept before the worktree is removed.

Two hooks hold this, once a clone has run:

```bash
git config core.hooksPath .githooks
```

- **pre-commit** searches what is staged, and the author and committer
  identities, for a home-directory path, a gmail address, a claude.ai session
  link or a job directory (`scripts/privacy_check.py`).
- **pre-push** refuses any branch but `main` (tags are allowed), and searches
  every commit the push would publish: its files, its message and its
  identities. It checks every commit, not just the tip, because a leak fixed
  by a later commit is still public in the earlier one.

Both read text, gzip members and a PDF's compressed streams. A match is
fixed and committed, never waved through. `--no-verify` skips the hooks and is
not for that. `python3 scripts/privacy_check.py --tree` searches every tracked
file at HEAD, and a test runs it.

Commit as the GitHub no-reply address (`git config user.email
<id>+<user>@users.noreply.github.com`). The hooks refuse a gmail identity,
but not any other address.

### Going public

The repository is still **private**, so the README, the *Cite this
repository* button and the topics can be looked at on GitHub before anyone
else sees them. Its description and its five topics (`cheminformatics`,
`pharmacology`, `chembl`, `drug-target-interactions`,
`network-visualization`) are already set. To make it public:

```bash
gh repo edit szaszeattila/SubNetwork --visibility public --accept-visibility-change-consequences
gh api -X PUT repos/szaszeattila/SubNetwork/private-vulnerability-reporting
```

The second command turns on private vulnerability reporting for
[SECURITY.md](../SECURITY.md), which GitHub offers only on public
repositories. Then deploy the page to production, so that its GitHub links
lead somewhere. The page's error-report links (the disclaimer strip and
About), `CITATION.cff` and the test holding those links
(`tests/cohort_viewer_public.test.mjs`) all name this address, so a rename
changes all of them.

### Contributions

A pull request is reviewed and merged here like any other change, and keeps
its own commits and author ([CONTRIBUTING.md](../CONTRIBUTING.md)).
