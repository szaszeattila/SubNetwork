# Hosting the viewer as a public website: a review

Reviewed 2026-10-09 against commit `3a4a31d` and the active build of
2026-09-27; status updated later the same day and on 2026-10-10, the second
time after the user's annotations, which are answered in
[HOSTING-REVIEW-ANSWERS.md](HOSTING-REVIEW-ANSWERS.md). A review, not a
decision: what has been acted on is marked below, and the rest is not
adopted.

The viewer can go on a public server with small changes. It is fully static,
makes no third-party requests and escapes every data string it renders. The
work left is public-facing: a medical disclaimer, data licensing and credits,
phone support, shareable links and cache-busting. A real server also lets you
ship the 71.7 MB of evidence shards the claude.ai artifact never could.

## Where it stands

A private copy runs on Cloudflare Workers static assets behind Cloudflare
Access, evidence shards included, deployed by `scripts/deploy_cloudflare.sh`
([PUBLISHING.md](PUBLISHING.md), *The Cloudflare copy*). It is not public:
Access admits only members of the Cloudflare account.

| Item | State |
| --- | --- |
| Medical disclaimer | **Done.** A permanent strip under the page and an About panel. |
| Data credits and licences | **Done.** About names all six sources and their terms; `NOTICE` ships as `NOTICE.txt`; GtoPdb is in its own file. |
| Phones | **Open.** Needs a decision: responsive, or stated desktop-only. |
| Versioned data files | **Mostly done.** `Cache-Control: no-cache` on every file; the two startup files are paired by stamp. Shards are not checked against the build. |
| Shareable links | **Done.** The selection and the sender's filters are the URL fragment, `#m=CHEMBL113&tier=supported`. |
| First impression | **Partly done.** About explains the page and the title is "SubNetwork"; no meta description, Open Graph tags or intro yet. |
| Security headers | **Done**, including a `script-src` CSP by the inline script's hash. |
| Local path in the payload | **Done.** The export leaves `chembl_path` out of `meta`. |
| Gaps found by the second pass | **Partly done.** Done: licence links, a visible data date, how to cite, the load and failure states, a staging copy, the deploy record, one hosted copy, the interactions line and the two optional headers. Open: privacy, a contact route, other browsers, keyboard access, monitoring, indexing and a favicon, the 43 unexamined claims. The address is `subnetwork.dev`. See *What the first pass missed*. |

Before admitting anyone beyond the account, the remaining choice is phones,
and the link-preview tags are the remaining work from the first pass. Of the
second pass's four items to close before going public, two are done and two
remain: what the host sees, and a way to report an error. The claude.ai
artifact was deleted on 2026-10-10, so Cloudflare is the one hosted copy.

## Security

The page is in good shape: no injection path was found, and there are no
third-party requests at all.

**Verified safe**

- `esc()` escapes all five of `& < > " '`, so it is safe in text and quoted
  attributes.
- `safeUrl()` allows only http and https, and every external link carries
  `rel="noopener"`.
- Search highlighting (`highlightMatch`) escapes every piece it emits.
- `tests/cohort_viewer.test.mjs` tests escaping and rejects `data:` URLs.
- Only four `innerHTML` sinks exist, and every data value reaching them is
  escaped. This was sampled, not read at all 73 markup-building sites. *Since
  then a fifth: About's source list (`aboutSourcesHTML`), whose one data value,
  GtoPdb's release, is escaped.*
- Nothing read from the URL, `postMessage` or `localStorage` reaches a sink;
  the URL supplies only two debug flags (`nocache`, `fps`).
- There are no inline event handlers, and vis-network's HTML hover tooltip is
  off.
- No CDN, web fonts or analytics: no cookies, so no cookie banner if server
  logging is minimal.

**Hardening to add when hosting**

- [x] HTTPS, plus `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin` and
  `frame-ancestors 'none'`. *Done: Cloudflare serves HTTPS, and the deploy
  script's `_headers` sets the three headers, plus `X-Frame-Options: DENY`.*
- [x] A Content-Security-Policy. The app is one inline script, so it needs a
  sha256 hash of that script (recomputed by the deploy script on every edit)
  or `'unsafe-inline'`; styles need `'unsafe-inline'` either way. Moving the
  script to `app.js` would allow `script-src 'self'` but breaks the one-file
  design and the vm test harness. *Done 2026-10-10, by hash:
  `scripts/csp.py` computes the policy from the page being deployed —
  `default-src 'none'`, `script-src 'self'` plus the inline script's sha256,
  `style-src 'self' 'unsafe-inline'`, `img-src 'self'`, and `base-uri`,
  `form-action` and `frame-ancestors` all `'none'` — and refuses a page with a
  second inline script or an inline event handler, which a hash cannot cover.
  Checked in headless Chrome over HTTP with the policy served as a header: no
  violation while opening links, drawing, loading an evidence shard and
  following a pasted link; and with a wrong hash the page was blocked and the
  hash Chrome asked for was the one the script computed.*
- [x] Read-only web files: evidence shards execute as scripts, so whoever can
  write `evidence/` or `graph.data.js` controls the page. *Holds on
  Workers: the files are only written by a deploy.*
- [x] Drop the local path `/mnt/data/chembl/...` that `graph.data.js` carries
  in `meta.chembl_path`. *Done: the export leaves it out (it stays in the
  database's `build_manifest`), and a test holds it.*

## Evidence shards

On your own server the 1,177 shards (71.7 MB raw, about 10 MB gzipped, largest
2.2 MB) just work, with no code change. The page loads each one as a plain
`<script>` from `evidence/<id>.js`, which any static host serves.

The claude.ai artifact caps a version at 255 files and 64 MB, which is why they
were never published there. Hosting them restores the individual measurement
rows inside a claim's Measurements disclosure, curated claims' references, and
the retained-observations lists. [PUBLISHING.md](PUBLISHING.md)'s section "Why
the evidence shards are not published" now applies only to the artifact.

## Payload and compression

Server-side compression is required: it cuts a first visit from about 7 MB to
about 1.5 MB. Cloudflare compresses on its own.

| File | Raw | gzip -9 |
| --- | --- | --- |
| `graph.data.js` | 5.87 MB | 1.22 MB |
| `vendor/vis-network.min.js` (9.1.9) | 0.69 MB | 0.16 MB |
| `index.html` | 0.39 MB | 0.12 MB |
| `evidence/` (1,177 files, on demand) | 71.7 MB | about 10 MB |

These are the review's measurements. Since then GtoPdb's part moved to its own
`gtopdb.data.js` (0.13 MB), leaving `graph.data.js` at 5.71 MB. Brotli was not
measured. Load time on phones is unknown: parsing and laying out about 2,600
nodes was only ever timed in desktop Chrome (216 ms to parse and index).

## Before going public

Six gaps, most important first. The first two are the ones that matter for a
public audience.

- [x] **Add a medical disclaimer on the page.** "Exploratory and educational,
  not medical advice" was in `NOTICE` but nowhere a visitor saw it. "Approved
  for…", trial statuses and **Closest target profiles** read easily as "this
  drug can replace that one". *Done: a permanent one-line strip runs along the
  bottom of the page, outside every panel, and an **About** panel in the top
  bar says what the page is, that it is not medical advice, what "similar"
  does and does not mean (CLAUDE.md's Goal wording), that approval and trial
  statuses are as recorded at build time, and the known limitations listed
  under* Content caveats *below.*
- [x] **Complete data credits and licences.**
  - The page credited GtoPdb (CC BY-SA 4.0) but only named ChEMBL 37, without
    its CC BY-SA 3.0 licence. *Done in `d3b7f1b`.*
  - NLM/MeSH, ClinicalTrials.gov, UniProt and Wikidata were not credited on the
    page. *Done: About credits all six sources with their terms, and `NOTICE`
    now also names ClinicalTrials.gov and the PubChem and FDA UNII routes to
    MeSH. About is the one place the page credits them: the catalogue line in
    Display options keeps its counts and points there. As that line did,
    About credits GtoPdb only when `gtopdb.data.js` was merged, at the release
    the file carries.*
  - Serving `graph.data.js` and `evidence/` redistributes a derived database;
    share-alike needs a stated licence and credits beside the files. *Done:
    each data file states its licence in its header, and the deploy script
    ships `NOTICE` as `NOTICE.txt` beside them, instead of a separate
    `LICENSE-DATA`.*
  - Open question: GtoPdb's database is ODbL while its contents are
    CC BY-SA 4.0, and the export mixed it with ChEMBL. *Answered without
    asking GtoPdb, in `e81bb5e`: everything GtoPdb contributes is exported to
    its own `gtopdb.data.js` under its own terms, and the page combines the two
    files only when it draws. Not legal advice.*
- [ ] **Decide on phones.** There is no `<meta name="viewport">` and no
  `@media` rules, so phones get the desktop page shrunk down, and help text
  opens on hover (it does take keyboard focus). Make it responsive or state
  that it is desktop-only.
- [x] **Version the data files.** Fixed names mean a returning browser can pair
  a new `index.html` with an old `graph.data.js`, or new data with old shards.
  *Mostly done: the deploy sends `Cache-Control: no-cache` for every file, so
  a browser revalidates each one (an unchanged file should answer 304) and cannot
  keep last deploy's data under this deploy's page. The page also merges
  `gtopdb.data.js` only when its stamp matches `graph.data.js`. Not done:
  shards carry no build stamp, so a shard from another build would not be
  noticed; with `no-cache` that would take a deploy interrupted between files.
  Build-stamped names remain the fix if it ever matters.*
- [x] **Add shareable links.** Nothing about the selection is kept in the URL,
  so nobody can link to caffeine. A hash such as `#m=CHEMBL113` is probably the
  most valuable public feature; it would be the first URL input that does
  anything, so use it only as a lookup key. *Done 2026-10-10: every
  selection kind has a fragment (molecules by ChEMBL id), followed by every
  filter the sender moved off its default, read on load and on
  `hashchange` and written with `replaceState`; one naming nothing opens what
  the page would open without it. The rules are in
  [VIEWER.md](VIEWER.md), "The address names what is selected".*
- [ ] **Fix the first impression.** "SubNetwork — Cohort 1" means nothing to a
  visitor. Add a meta description, link-preview (Open Graph) tags and a short
  introduction beyond the empty-panel text. *Partly done: About now explains
  the page, and the title is "SubNetwork" (2026-10-10); the meta tags and
  introduction are unchanged.*

## Deployment and hosting

Ship the page's own paths and nothing else: `viz/index.html`, `viz/vendor/`,
`viz/graph.data.js`, `viz/gtopdb.data.js` (added after the review) and
`viz/evidence/`, plus `NOTICE.txt`. Leave out `viz/backups/` (105 MB) and
`viz/legacy/` unless you want the old viewer live too.

The data cannot be rebuilt from the repo: `graph.data.js` and `evidence/` are
gitignored, and building them needs the local ChEMBL bulk release plus the
network backfills. Nothing runs the test suites automatically either (no CI). A
deploy script should:

1. run both suites and `scripts/cohort_report.py --check-status`; *done*
2. compress and copy the paths; *done (Cloudflare compresses)*
3. compute the CSP hash of the inline script; *done (`scripts/csp.py`)*
4. record which build and commit went live. *Done as the deployment message:
   the commit, and whether `index.html` differed from it.*

No backend is needed, and it is worth keeping it that way. The host comparison
below is from general knowledge, not checked against current documentation.

| Host | Custom headers (CSP, caching) | Compression | Deploying gitignored data |
| --- | --- | --- | --- |
| Cloudflare Pages | Yes, `_headers` file | gzip and brotli | CLI upload of a built folder |
| Netlify | Yes, `_headers` file | gzip and brotli | CLI upload of a built folder |
| GitHub Pages | No; CSP only via `<meta>` | gzip | A GitHub Action, since the data is not in git |
| Own server (nginx) | Yes, full control | Whatever you configure | rsync |

Recommendation: Cloudflare Pages or Netlify, for the headers file and brotli.
*Taken: Cloudflare, as Workers static assets, the successor to Pages.*

## Content caveats to state publicly

These are under "Not done" in CLAUDE.md. They are acceptable for an
exploratory site as long as the About page says so, and it now does:

- The six scoring constants are unvalidated.
- Affinity is not weighed: 7 nM and 200 µM score alike.
- There is no brain-expression signal; the brain focus comes from molecule
  selection only.
- One known ChEMBL curation error is on the page: alfuzosin filed as an
  alpha-1 agonist. (Since 2026-10-10 the direction is withheld and the panel
  says so; About still names it.)
- The similarity grade (38.7% top-1 against ATC classes) makes the ranking a
  place to start looking, not a verdict. About words it as "well under half the
  time" rather than quoting the figure, which is generated and would go stale
  in static text.

## What the first pass missed

A second pass on 2026-10-10, at commit `25e0ea7` and the build of the same
day, asked what a public audience would meet that the review above does not
cover. Phones are left out on purpose; they are a separate piece of work. Like
the rest of this document, these are findings, not decisions. They are ranked
within each group, and the first group is the one to close before the
Access policy comes off.

### Before going public

- [x] **Link the licences and license the derived files.** About and `NOTICE`
  name CC BY-SA 3.0, CC BY-SA 4.0, ODbL 1.0 and CC BY 4.0 but link none of
  them. Each of these licences asks for a link or URI to its text, and the
  CC licences also ask you to say that the material was changed. About says
  the data files "stay under their terms". Share-alike asks for a stronger
  statement: you license your adaptation under the same licence, so
  `graph.data.js` and `evidence/` are CC BY-SA 3.0 *from you*, and
  `gtopdb.data.js` is under ODbL and CC BY-SA 4.0. The ODbL also wants its
  produced-work notice ("contains information from … made available under the
  ODbL") to carry a link. Both NLM sources have terms of their own: the usual
  acknowledgement names the NLM, says it does not endorse the product, and
  gives the date the data was retrieved. About says this for MeSH and not for
  ClinicalTrials.gov. Check the wording against each source's current terms;
  none of this is legal advice. *Done 2026-10-10. About links every licence
  and states the adaptation's licence. Every data file says the same in its
  header, the evidence shards included: changes were made, licensed by
  SubNetwork under CC BY-SA 3.0, and GtoPdb's file under the ODbL 1.0 with
  the produced-work notice. Both NLM sources carry the acknowledgement, the
  non-endorsement, the MeSH version and the trial-fetch date. The wording was
  checked against the sources' pages, but ClinicalTrials.gov's own terms page
  did not render, so NLM's general terms stand in for it.*
- [x] **Put a date on the page.** About says approval and trial statuses are
  "as … recorded … when this page was built" but gives no date anywhere.
  `meta.built_at` is in `graph.data.js` and is never read. `trial_status.fetched_at`
  is stored for every row (all 13,021 rows read 2026-10-10 now) and is not
  exported. One line such as "Built 2026-10-10 from ChEMBL 37; trial statuses
  fetched 2026-10-10" makes the caveat mean something, and NLM's terms ask
  for it too. *Done: the disclaimer reads "Data built 2026-10-10", and About
  gives the build day, the trial-fetch days and the GtoPdb, MeSH and UniProt
  versions. The export carries `trials_fetched`.*
- [ ] **Say what the host sees.** The page sets no cookies and makes no
  third-party requests, and the selection lives in the URL fragment, which
  never reaches the server. But opening a molecule's evidence requests
  `evidence/<id>.js`, so the host's request logs record *which drug a visitor
  looked at*, beside their IP address. On a drug-information page that is
  health-adjacent. A short privacy note in About should say this, name
  Cloudflare as the host and state its log retention, and promise that no
  analytics are added. If you live in the EU, the GDPR applies to the
  operator even of a non-commercial site, and some countries also require an
  operator-identification page. Check yours.
- [ ] **Give visitors a way to report an error.** About says "No other [error]
  has been found, which is not the same as there being none", and then
  offers no way to report one. A public audience is the cheapest error
  finder this project will ever have. The repository is **private**, so there
  is no issue tracker to link to, and "The code is MIT-licensed" points at
  code no visitor can reach. Either publish the repository and link its
  issues, or give a contact address and reword the code line. "How to cite"
  and a version (the build date above) belong next to it. *"How to cite" is
  done: the page by data version and address, and the papers ChEMBL and
  GtoPdb ask for. The contact route waits on whether the repository goes
  public ([HOSTING-REVIEW-ANSWERS.md](HOSTING-REVIEW-ANSWERS.md)).*

### Robustness on desktop

- [x] **Failure is silent and loading is unannounced.** If `graph.data.js` is
  missing, blocked or throws, the page draws an empty canvas, and Display
  options reads "Catalogue: 0 molecules". `const DATA = … ? COHORT_DATA :
  { molecules: [] … }` falls back without a word, and there is no
  `window.onerror`. While the 1.2 MB of compressed data downloads, the sidebar
  already says "the whole network is drawn at rest", over a blank canvas.
  There is no `<noscript>` either. A loading line and an error message would
  each take a few lines. Evidence shards already do this properly: a missing
  one says "a missing file, not an absence of evidence". *Done:*
  - *A line over the canvas says the page is loading, then laying out, and
    clears on the first settled layout.*
  - *A missing `graph.data.js`, a missing vis-network or an uncaught error
    each states its failure, over the canvas and in the panel.*
  - *A `<noscript>` message covers a browser without JavaScript.*
  - *A GtoPdb file from another export is named in About as left out.*
  - *Checked in headless Chrome with the data present and removed.*
- [ ] **Only Chrome has ever run it.** Nobody has opened the page in desktop
  Firefox or Safari; a code comment says "Safari has to be measured by
  whoever is holding the Mac". The edge renderer monkey-patches vis-network
  9.1.9's private `_drawEdges`, and the dash and hairline fast paths were
  tuned to Chrome's GPU backend. No risky JS or CSS feature was found, so
  this is a one-hour check, not a port. Timing the physics settle on a modest
  laptop belongs in the same hour.
- [ ] **Keyboard and screen-reader access stop at the search box.** Search
  works from the keyboard (arrows and Enter), and Escape closes About. But:
  - the panel rows a visitor navigates by are `<div data-select>` with no
    `tabindex`, so a keyboard user reaches a molecule and then cannot follow
    it to its targets;
  - the search input has no label, only a placeholder;
  - nothing is `aria-live`;
  - no panel moves focus when it opens;
  - the only focus style is on the help marks;
  - nothing honours `prefers-reduced-motion`, which matters for the physics
    animation and the smooth scrolling.

  The canvas cannot be made accessible, but the sidebar already carries the
  same information as HTML. Making its rows reachable, with `tabindex="0"`,
  Enter, and a `:focus-visible` outline, is most of the value. The legend
  names every colour, and Preliminary lines are dashed, so colour is not the
  only signal except under the "Curated mechanism" line colouring.

### Operating it in public

- [x] **Every deploy goes straight to the public.** Today Access gives the
  only reader a private copy. Once it is public, `deploy_cloudflare.sh` has no
  preview step: keep a second, Access-protected Worker (or `wrangler versions
  upload` with a preview URL) for checking, and write down `wrangler rollback`
  as the undo. Not verified: whether Access currently covers the workers.dev
  *preview* URLs as well as the main one. That is worth checking now, because
  the private copy depends on it. *Done 2026-10-10:*
  - *Access covers the main URL and every preview hostname. Three version
    URLs, the `staging` alias and an unused alias name all answered 302 to
    the login.*
  - *`deploy_cloudflare.sh --preview` uploads to the staging alias without
    deploying.*
  - *Every upload checks each URL it printed against the Access login.*
  - *`wrangler rollback` is written down in [PUBLISHING.md](PUBLISHING.md).*
- [x] **The deploy record names the code but not the data.** Item 4 under
  *Deployment and hosting* is half done. The message is the commit plus
  "index.html modified". It does not say which build went live (`built_at`),
  and it will deploy a page that differs from every commit. The data is
  gitignored and the live bundle exists only on this disk. A public deploy
  should refuse a modified `index.html`, put `built_at` in the message, and
  keep a copy of what it uploaded. *Done, all three. A production deploy also
  refuses a modified `NOTICE`, vendor library or CSP script. Copies go to
  `deploys/`.*
- [ ] **Nobody will know when it breaks.** With no telemetry by design, a
  broken public page tells no one. A scheduled external check is enough: it
  fetches `index.html` and `graph.data.js` and compares the stamp with
  `gtopdb.data.js`.
- [x] **Two public copies will drift.** The claude.ai artifact (no shards,
  republished by hand) and the Cloudflare site will both be shareable, with
  the same fragment links. Pick one as canonical, and have the other say so
  and link to it. *Done by removal: the artifact was deleted on 2026-10-10 at
  the user's request.*
- [ ] **Decide the address before the first link is shared.** Shared links
  are the page's best feature. Once one is out, moving the site breaks it. A
  `workers.dev` subdomain shows the account name. A custom domain would also
  need its own HSTS: every `.dev` domain is HSTS-preloaded, but a `.org` is
  not. Decide at the same time whether search engines should index a soft
  launch (`robots.txt` / `noindex`), and add the favicon the first pass's
  link-preview item does not mention. *Address done 2026-10-10: the page is
  public at `subnetwork.dev`, registered through Cloudflare, attached by the
  production deploy, and HSTS-preloaded as every `.dev` is; production's `workers.dev`
  address is off and the preview URLs stay behind Access. Indexing and the favicon are open.*

### Content a public reader will misread

- [ ] **Known unexamined data goes public with it.** ChEMBL flags 176 of the
  activities here "Potential transcription error". 156 of them are counted,
  inside 43 Supported claims, and nobody has looked at them (CLAUDE.md, *Not
  done*). The two open MeSH findings will also show. Either look at the 43
  claims before launch or add them to About's known limitations; About
  currently says only that alfuzosin is known.
- [x] **A shared enzyme is not an interaction check.** Metabolic enzymes and
  transporters are drawn as targets like any receptor (naloxone and
  naltrexone share CYP2D6). A member of the public may read a shared CYP
  as "these interact" or, worse, read its absence as "these do not". The
  page says nothing about drug–drug interactions. One line in About and
  the disclaimer would close this: "This page does not cover interactions
  between drugs." *Done: in the disclaimer strip, and in About with the
  CYP2D6 example.*

### Minor

- `graph.data.js` ships `meta.deferred_sources` listing **GtoPdb as deferred**,
  next to the `gtopdb.data.js` that holds it. The page never shows it, but
  anyone reading the payload will. It comes from the evidence policy's
  `source_scope`, written before D17. *Fixed: the GtoPdb backfill takes
  GtoPdb off the list and marks it assessed in `source_coverage`, which the
  payload also carries.*
- The inline script is a classic script, so every top-level function
  (`select`, `getFilters`, …) is callable from the console, and `?fps` and
  `?nocache` still work. This is harmless and needs no change; it is noted
  so that nobody mistakes it for an exposure later.
- `viz/backups/` holds old payloads that still carry `chembl_path`. The deploy
  script ships named paths only, which keeps them out. Keep it that way, and
  never deploy `viz/` whole.
- Optional headers not set: `Permissions-Policy` and
  `Cross-Origin-Opener-Policy`. *Set since 2026-10-10.*

## What was checked

At the review:

- Pipeline suite: 437 tests pass. Viewer and harness suites: 599 pass.
  `--check-status` reports the Status block current.
- A delegated security sweep of `viz/index.html`, with its main claims
  re-checked by hand. It got two details wrong, corrected above: the bundled
  vis-network is 9.1.9, and the `localStorage` reads are already wrapped in
  try/catch.
- Sizes and compression measured locally with `gzip -9`.
- Not done: opening the page in a browser over HTTP, testing any CSP, timing it
  on a phone, and reading every one of the 73 markup-building sites.

At the status update:

- Pipeline suite: 440 tests pass. Node suites: 607 pass. `--check-status`
  reports the Status block current, and `deploy_cloudflare.sh --dry-run`
  stages 1,183 files.
- The re-exported payload contains no `/mnt/data` or home-directory path, in
  `graph.data.js`, `gtopdb.data.js` or any shard.
- The page was rendered in headless Chrome at 1440×900 from `file://`, with
  About closed and open.
- Not checked: the response headers as served, since Cloudflare Access answers
  every request before the Worker does.

At the second pass:

- A delegated read-only sweep of `viz/index.html` for loading and failure
  states, head metadata, accessibility, browser features, external hosts and
  personal data. Its main claims were re-checked by hand: the silent
  `COHORT_DATA` fallback, the one `onerror` (the shard loader's), and the
  absence of `<noscript>`, `og:` tags, a favicon and any `aria-label`.
- About's text, `NOTICE`, `scripts/deploy_cloudflare.sh`, the payload's
  `meta` keys, `build_manifest` and `trial_status.fetched_at` were read
  directly. The repository's visibility was read with `gh`: private.
- No tracked file carries the Cloudflare address or an email address.
- Not checked: any source's licence or terms text, which this pass quotes
  from general knowledge; Firefox and Safari; Access's coverage of preview
  URLs.
