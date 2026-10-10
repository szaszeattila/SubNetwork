# Answers to the annotations on the hosting review

The user annotated a PDF of [HOSTING-REVIEW.md](HOSTING-REVIEW.md) in Zotero on
2026-10-10. Its actions were carried out in commit `7608765` and the two
commits after it. The claude.ai artifact was deleted the same day. All of it
is on the private staging copy; production still serves the build before it
until `scripts/deploy_cloudflare.sh` is run. Its questions are answered here.
Sources were fetched on 2026-10-10, except where marked unverified. None of
this is legal advice.

## Done

- **Licence links and licensing of the derived files.** About links every
  licence. About and each data file's header license the adaptation:
  `graph.data.js` and the shards under CC BY-SA 3.0, `gtopdb.data.js` under the
  ODbL 1.0 with its contents under CC BY-SA 4.0. Both say that changes were
  made. The ODbL produced-work notice is in the header.
- **A date on the page.** The disclaimer reads "Data built 2026-10-10". About
  gives the build date, the trial-fetch dates, and the GtoPdb, MeSH and
  UniProt versions. The export now carries `trials_fetched`.
- **How to cite.** About cites the page by its data version and address, plus
  the papers each source asks for. ChEMBL: Zdrazil et al., NAR 2024,
  doi:10.1093/nar/gkad1004. GtoPdb: Harding et al., NAR 2026,
  doi:10.1093/nar/gkaf1067.
- **Loading indicator and error message.** A line over the canvas says the
  page is loading, then laying out, and clears when the layout settles. A
  missing `graph.data.js`, a missing vis-network or an uncaught error each
  gets a stated failure. The page also has a `<noscript>` message.
- **A private copy to work on.** `deploy_cloudflare.sh --preview` uploads to a
  `staging` alias URL without touching production. Checked: Access answers on
  the main URL, on every version preview URL tried, and on any
  `*-subnetwork` hostname, the staging alias included. The script re-checks
  this after every upload.
- **Deploy record.** The deploy message names the commit and the data's build
  and export stamps. A production deploy refuses an uncommitted page, `NOTICE`
  or CSP script. Each upload is kept under `deploys/`.
- **Two public copies.** The claude.ai artifact was deleted. Cloudflare is the
  one hosted copy.
- **`deferred_sources`.** The GtoPdb backfill now takes GtoPdb off the list
  and marks it assessed in `source_coverage`.

## Questions

**Examples of sites with a medical disclaimer.**

- [Wikipedia: Medical disclaimer](https://en.wikipedia.org/wiki/Wikipedia:Medical_disclaimer)
  ("Wikipedia does not give medical advice") is the closest model: a
  volunteer-built reference with a dedicated page.
- The [NHS website terms](https://www.nhs.uk/our-policies/terms-and-conditions/),
  section 4, puts it in its terms and conditions.
- [NLM's web policies](https://www.nlm.nih.gov/web_policies.html) (MedlinePlus
  redirects there) use a dedicated policy page.
- [WebMD](https://www.webmd.com/about-webmd-policies/default.htm) puts a line
  in its site footer, which is closest to this page's permanent strip.
- GtoPdb's own disclaimer page has no medical disclaimer.

**What is ODbL, and why ask GtoPdb?** The Open Database License (Open Data
Commons) is a share-alike licence for databases as a whole. GtoPdb licenses its
database under the ODbL and the individual entries under CC BY-SA 4.0. The
question was never "how do they label it". It was whether ODbL data may be
merged into a file licensed under ChEMBL's CC BY-SA 3.0, and no published
compatibility says it may. That was settled without asking GtoPdb: its data
ships in its own file under its own terms. No question to GtoPdb is
outstanding.

**Is a privacy note needed, and would analytics be a problem?** The page sets
no cookies and makes no third-party requests. Opening a molecule's evidence
does fetch `evidence/<id>.js`, though, so a host log can tie an IP address to
a drug. A short note is cheap and honest, but it is not required by any rule
we found for a US operator.

Aggregate counts would be low-risk: searches per molecule per country, with
no IP addresses and no identifiers stored. Cloudflare Web Analytics is
cookieless and does not fingerprint. Two places add risk:

- **Anything per visitor.** Under the GDPR an IP address is personal data
  (CJEU *Breyer*, C-582/14). A drug looked up by an identifiable person can be
  health data, since the CJEU (C-21/23) treated pharmacy orders that way.
- **Very small counts.** A rare molecule seen from a small country could
  identify someone.

If analytics are added, About must stop promising that there are none.

**I don't live in the EU; does the GDPR apply?** Mostly no. Under Art. 3(2) it
reaches a non-EU operator only if the site offers services to people in the EU
or monitors their behaviour there. The EDPB says mere accessibility from the
EU is not enough, and that monitoring means tracking or profiling, such as
cookies or fingerprinting. A free English-language site with no tracking does
neither. Per-visitor analytics could count as monitoring. The UK GDPR follows
the same rule. (The machine's time zone and Access's country flag both say US.
US law has no general privacy statute that applies to a site this size.)

**What do the CYP2D6 lines mean?** CYP2D6 is not a drug. It is a liver enzyme
that breaks many drugs down. ChEMBL records measurements of drugs inhibiting
it, so it is drawn as a target like a receptor. Two molecules sharing it means
both were measured at that enzyme. It does not mean they act alike, and it
says nothing reliable about whether they interact when taken together.
Interaction checking needs dose and exposure data this page does not have.
The page now says so in the disclaimer strip, and About gives the CYP2D6
example.

**What are Permissions-Policy and Cross-Origin-Opener-Policy?**

- **`Permissions-Policy`** switches browser features off for the page and
  anything it embeds. For example, `camera=(), microphone=(), geolocation=()`
  means no script on the page can ever ask for those.
- **`Cross-Origin-Opener-Policy: same-origin`** cuts the link between this
  page and windows of other sites that open it or that it opens, so a
  malicious opener cannot script it.

The page needs neither feature and its outbound links use `noopener`, so both
headers are hardening with nothing to break. Both are now set in the deploy
script's `_headers`.

## Making the GitHub repository public

From a read-only audit. The commit-metadata figures come from the audit and
were not re-checked here.

**Must fix**

- Commit metadata carries a personal gmail address on 126 commits, some under
  other author names.
- About 230 commit messages link private claude.ai sessions.
- Removing either means rewriting history (`git filter-repo` with a mailmap
  and a message filter) and force-pushing every branch and the tag.
  Publishing a fresh, single-commit copy of the repository is the simpler
  route.
- Home-directory paths appear in `docs/prompts/*.md` and in links inside the
  archived report PDF.

**Should fix**

- There is no root `README.md`; `CLAUDE.md` is written for an assistant.
- Reproduction assumes `/mnt/data/chembl/` and gitignored data, and nothing
  tells an outsider to download ChEMBL 37. *Done: [REPRODUCING.md](REPRODUCING.md).*
- `docs/CHEMBL-ERROR-REPORT-ALFUZOSIN.md` is an unsent draft.
- Decide whether `CLAUDE.md`, `docs/prompts/` and the archived Zotero notes
  should be public.
- `requirements.txt` misses `markdown_it` and `reportlab`. *Done.*

**Nice to have:** `CITATION.cff`, `CONTRIBUTING`, `SECURITY.md`, issue
templates, and a GitHub description and topics.

**Clean:** no secrets or keys anywhere in history, no Cloudflare address, no
file over 10.1 MB, and vendored code with its licence header intact.

## Second round: annotations on this document

The user annotated a PDF of this document on 2026-10-10, six notes on the
section above. Three asked for a fix and three asked a question.

### Done

- **Reproduction from a fresh clone.** [REPRODUCING.md](REPRODUCING.md) now
  covers it:
  - It gives the ChEMBL 37 download from the release's own directory, never
    `latest/`. It gives the archive's sha256 from EBI's `checksums.txt`,
    checked against the server on 2026-10-10.
  - It says that `CHEMBL_SQLITE_PATH` points the build at the file.
  - It gives the build, backfill and export order, and what each step needs
    from the network.
  - It says which backfills read a live source and so will not reproduce
    exactly.
  - It warns that `config/cohort1_selection.json`'s ChEMBL path is a record
    that no code reads.

  The build's error for a missing ChEMBL file now names the variable and that
  document. The survey found one real trap, now documented: GtoPdb serves only
  its latest release, and the backfill refuses anything but 2026.3. Once
  GtoPdb ships its next release, a fresh clone cannot fetch the pinned files,
  and GtoPdb's download page showed no archive of past releases. The error now
  says where to put the pinned files. `CLAUDE.md` and [INDEX.md](INDEX.md)
  link the new document.
- **`requirements.txt`** lists `markdown-it-py>=4.0` and `reportlab>=4.0`.
  A comment says only `analysis/cohort1/followup/build_pdf.py` uses them and
  that it also needs the system Noto and DejaVu fonts.

### Not done

- **The alfuzosin report is still unsent.** On 2026-10-10 ChEMBL's live API
  still returned mec_id 1161 as `AGONIST`, so the report is still accurate.
  Sending it from the user's Gmail was attempted and refused by the session's
  permission rules. Leaving it as a Gmail draft was refused too. Both are
  actions the user has to allow or take. The text is in
  [CHEMBL-ERROR-REPORT-ALFUZOSIN.md](CHEMBL-ERROR-REPORT-ALFUZOSIN.md), ready to
  paste. Once it is sent, record the date there and in
  [COHORT-2.md](COHORT-2.md).

### Rewrite the history, or publish a fresh copy?

What is in the history, checked on 2026-10-10:

- The gmail address is on 126 commits, under two author names other than the
  current one.
- 230 commit messages carry a link to a private claude.ai session.
- Both stopped some time ago. The last session link is from 2026-09-28 and
  the last gmail commit from 2026-10-04. Commits are now made under GitHub's
  noreply address, so the problem is historical and is not still growing.

**Route 1: rewrite the history** with `git filter-repo`, a mailmap and a
message filter.

- *For:* the public repository keeps the real history: blame, bisect, and
  dated commits showing how each rule arrived. There is one repository, not
  two.
- *Against:* every commit hash changes. Ten hashes cited in
  [HOSTING-REVIEW.md](HOSTING-REVIEW.md), [PUBLISHING.md](PUBLISHING.md) and
  this file stop resolving unless they are edited too.
- *Against:* every branch, the `legacy-seed-graph` tag and every open worktree
  has to be force-pushed or recreated.
- *Against:* only what you tell `filter-repo` to remove is removed. The
  home-directory paths in old versions of the archived PDF stay unless they
  are filtered as well.
- *Against, the important one:* force-pushing over this same GitHub repository
  does not make the old commits disappear. GitHub's guide to
  [removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
  says they stay reachable by their hash in cached views and through pull
  requests until GitHub Support removes them. Flipping that repository public
  afterwards could still expose them. If you rewrite, push the result to a
  **new** repository.

**Route 2: publish a fresh copy**, one commit in a new public repository.

- *For:* the only thing to audit is the current tree.
- *For:* the private repository keeps its full history untouched, with nothing
  to force-push and no worktree disturbed.
- *For:* you choose file by file what goes public (see the next question)
  without deleting anything from the private record.
- *Against:* the public history starts at day one, and the cited hashes point
  at nothing public.
- *Against:* there are two repositories. Each later publish is a new snapshot
  commit, from a small script that copies the tree, and a contribution made to
  the public copy has to be carried back by hand.

**Recommendation: route 2.** The project's reasoning already lives in `docs/`,
dated, rather than in commit messages. So the public loses the least by
losing the history. The private repository loses nothing at all. Publish one
snapshot per data build, with the build date as the commit message. Route 1
is only worth it if you want outsiders to bisect, and then only into a new
repository.

### Should `CLAUDE.md`, `docs/prompts/` and the Zotero notes be public?

- **`CLAUDE.md`: yes.** It is the most exact statement of the rules and
  invariants anywhere in the project, and it holds nothing private. The
  Cloudflare address was kept out of it on purpose. It is also honest about
  how the project is made. For a scientific resource, that openness is worth
  more than the slight oddity of a file addressed to an assistant. It should
  not be the front door, though: a short `README.md` for people should come
  first and link to it.
- **`docs/prompts/`: yes, after the home-directory paths are made
  repository-relative.** They are provenance. They record what scope and
  constraints each piece of work was given, such as "evidence availability
  must not determine membership", and an auditor of the method would want
  that. The decision documents carry the substance either way, so dropping
  them would cost little. But nothing in them needs hiding.
- **The archived Zotero notes (`docs/archive/cohort-report-2026-09-12/`):
  I would leave them out of the public copy.** They are your own questions
  ("what is MeSH and what is a versioned scope?"), and they are the least
  useful thing here to an outsider. The current
  [COHORT-REPORT.md](COHORT-REPORT.md) already answers them, and the archived
  PDF is also where the home-directory links are. Nothing in them is
  sensitive; it is a matter of taste, not risk. Route 2 makes this easy: keep
  them privately and simply do not copy them.

### What are `CITATION.cff`, `CONTRIBUTING`, `SECURITY.md`, issue templates, description and topics?

They are conventions GitHub recognises, and none is required.

- **`CITATION.cff`** is a small YAML file at the root saying how to cite the
  repository: title, authors, version, date, and optionally the papers it
  rests on. GitHub turns it into a "Cite this repository" button with APA and
  BibTeX, and Zenodo reads it if you ever archive a release for a DOI.
  About already says how to cite the page. This would make that
  machine-readable. *Worth it: cheap.*
- **`CONTRIBUTING.md`** tells outsiders how to propose a change. Here that
  means: run both suites, read DATA-QUALITY-LOG before changing how a value
  gets in, and a data claim needs its source. GitHub links it when someone
  opens an issue or pull request. If you do not want contributions, it is
  where you say so ("issues welcome, pull requests not accepted"). *Worth one
  paragraph either way.*
- **`SECURITY.md`** says how to report a vulnerability privately rather than
  in a public issue. GitHub shows it under the Security tab, and you can turn
  on private vulnerability reporting beside it. The page is static, and its
  real exposure is text from the data reaching the page (invariant 11). So
  this is one paragraph and an address. *Worth it once public.*
- **Issue templates** are forms under `.github/ISSUE_TEMPLATE/` that fill in
  the fields of a new issue. The useful one here is "Report a data error",
  asking for the molecule, the target, what is wrong and the source that says
  so. That closes the hosting review's open item *a way to report an error*.
  *The most useful of the four.*
- **Description and topics** are not files. They are the one-line summary and
  the tags (`cheminformatics`, `pharmacology`, `chembl`,
  `drug-target-interactions`, `network-visualization`) set in the repository's
  settings, so that it can be found by search. *Two minutes, at publish time.*

## Third round: the decisions, and what was built

The user annotated the second round on 2026-10-10 and decided each question.

- **Route 2, a fresh copy.** `scripts/publish_github.sh` publishes one
  snapshot commit of HEAD to a new public repository. It never publishes this
  repository's history, and this repository stays private. Before anything
  leaves, `scripts/public_snapshot.py` audits the staged tree. The procedure
  is in [PUBLISHING.md](PUBLISHING.md), *The public GitHub copy*. **It has not
  been run.** Its default target, `szaszeattila/SubNetwork`, is still this
  private repository's name. The script refuses a private target, so the name
  has to be settled first.
- **Which files go public: as suggested.**
  - `CLAUDE.md` is public. A new root `README.md` stands in front of it and
    says what it is.
  - The prompts' home-directory paths are now repository-relative.
  - The archived Zotero export, and the archived PDF whose links are local
    paths, are kept back from the public copy. The archive's README says so.
  - The names the history carries were taken out of the second round above.
- **`CITATION.cff`** cites the project, and lists ChEMBL's and GtoPdb's papers
  as references.
- **`CONTRIBUTING.md`** says contributions are welcome. It covers what a
  useful error report names, the documents to read before changing data or
  the page, and both suites. It says how a pull request reaches the snapshots:
  it is carried back by hand, and the snapshot names its author as a
  co-author. It also covers the licence of contributions.
- **`SECURITY.md`** asks for private reports through GitHub's vulnerability
  reporting, which the first publish turns on. It lists what is in scope for
  a static page.
- **No issue templates yet.** Instead, the page links the repository's
  issues. The disclaimer strip says "report an error on GitHub", and About has
  a *Report an error* paragraph that says what to name. The links go to the
  default target, so they lead somewhere only once the public copy exists.
  Templates can come later, if reports of one kind repeat.
- **Description and topics** are set by the first publish:
  `cheminformatics`, `pharmacology`, `chembl`, `drug-target-interactions` and
  `network-visualization`.
