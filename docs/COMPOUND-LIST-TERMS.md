# What public compound lists allow, and which others exist

2026-10-14. **A review; adopts nothing, and is not legal advice.** It answers
three of the user's questions after D23 entered 221 molecules because the
sci-wiki lists them ([COHORT-2.md](COHORT-2.md)): what risk the repository runs
by keeping the wiki's full list published in `analysis/wiki_comparison/`;
whether citing the wiki as a source of compounds is a "competing dataset"; and
what the other lists' terms allow, beside lists
[NOOTROPIC-WIKI-COMPARISON.md](NOOTROPIC-WIKI-COMPARISON.md) did not compare.

Terms were read on 2026-10-14. The sci-wiki's, TripSit's and PiHKAL·info's
were read directly for this document; the rest were read by three research
passes whose quotes are given as they reported them, and every page that could
not be reached says so below rather than being guessed. Terms change; reread
one before relying on it.

The use this document judges every source against is D23's: **a molecule is
entered with the list's name for it and a link to the list's own page for it,
and the list is credited** — nothing the list says about the compound is
copied, and every claim on the page comes from ChEMBL, GtoPdb or MeSH.

## The sci-wiki

**Its terms** (scientificsean.wiki/about/legal, governed by California law):
"Reading, linking to a page, and quoting a short passage with attribution are
all fine" (§18); "Republishing entries, copying the reference in bulk, and
using it as training data are not" (§18); "Do not copy the reference in bulk"
and "Copying entries at scale to train a model or to build a competing dataset
is not permitted" (§13); and "Using them in a way that suggests an endorsement
or an association that does not exist is not permitted" (§18). It claims "the
arrangement of the reference as a whole". Its `robots.txt` refuses AI crawlers
(ClaudeBot, GPTBot and others) the whole site and allows other agents
everything but `/admin`, `/api` and `/members`.

**D23's use is inside them, and is not a competing dataset.** The clause
forbids copying *entries* at scale. An entry here takes a name, which is a
fact, and a link, which the terms allow; none of the wiki's content is copied;
the 221 are a reviewed tenth of 2,184, each written down as a ChEMBL id; the
credit says SubNetwork is not affiliated; and the page sends its reader to the
wiki rather than standing in for it. What would move it toward the clause:

- copying the wiki's sections or classes into the policy, database or page —
  the arrangement it claims (D23 copies neither);
- admitting the whole list, or any part of it, without review;
- re-reading the wiki on a schedule to follow it, rather than one reviewed
  listing.

**The published list is the exposed part.** `wiki_compounds.csv`,
`comparison.csv`, `comparison_d21.csv` and `sections/*.csv` carry every one of
the 2,184 compounds with the wiki's own section and class: a complete copy of
its arrangement, committed before the terms were read. They were taken from one
fetch of the `/compounds/table` index page, which `robots.txt` allows; no entry
was fetched. As of this writing they are on the published branch
`worktree-wiki-comparison` and not on `main`.

- **Copyright is thin.** Under US law compound names are facts; a taxonomy
  can hold thin protection for its selection and arrangement, and a wholesale
  copy is where it applies. The EU database right very likely does not reach
  a US company's database. Statutory damages need a registration that is
  unlikely to exist, so money is near nothing.
- **The terms are the stronger claim.** Terms on a page nobody clicks through
  are often unenforceable in the US, but that weakens once they have actually
  been read, as they now have.
- **The realistic outcome is a takedown, not a suit.** A DMCA notice to GitHub
  disables what it names, and a notice can name the repository; that would
  take the project's public repository down over files the viewer does not
  need.

**Recommended, and the user's call:** before the branch reaches `main`, remove
`wiki_compounds.csv` and `sections/`, and the `section` and `wiki_class`
columns of both comparison files, leaving the scripts, which regenerate the
list from a fresh fetch, and the counts in the comparison document. The README
would then say of the wiki's list what it already says of the six others:
"they are other sites' content". The commits already pushed stay reachable by
hash and cannot be withdrawn; GitHub support can purge cached views if the wiki
ever asks. Asking the wiki's owner whether the list may stay would settle it.

## The lists already compared

The six lists NOOTROPIC-WIKI-COMPARISON.md compared, and the four it did not
retrieve. None was committed; only counts were. For D23's use every one of them
is at least as permissive as the sci-wiki, except Erowid's.

| source | terms | name + link + credit as a reason for entry | the full list published here | retrieval |
| --- | --- | --- | --- | --- |
| Wikidata | structured data public domain (CC0) | yes | yes | yes |
| Wikipedia | text CC BY-SA 4.0; a list of article titles is facts | yes; the link is accepted attribution | names yes; copied text under CC BY-SA | the API, with an identifying user agent |
| PsychonautWiki | CC BY-SA 4.0, except *Disregard Everything I Say* articles (CC BY-NC-SA 4.0) and experience reports (their authors') | yes | names yes; its categories bring share-alike | article pages allowed by `robots.txt`; the GraphQL API's terms not found |
| TripSit | "free-of-charge … for non-commercial purposes"; link back, with "a note citing TripSit as the source … on every page which uses/displays the information"; its GitHub repository has no licence | yes — what it asks for | no: nothing licenses it | its API, which it recommends |
| Nootropics Expert | no terms page found; "© 2026 - Nootropics Expert" | low risk | no | `robots.txt` crawl delay of 5 s |
| Examine.com | not read: rate-limited (429) | unknown | no | unknown |
| Erowid | written permission needed to scrape or to publish its data, per its `robots.txt` notice; its copyright page returned 403 | a plain link only | no | no, without permission |
| DrugBank | the vocabulary file CC0; the full database CC BY-NC 4.0 | the vocabulary only | the vocabulary only | academic downloads paused |
| r/Nootropics wiki | Reddit's user agreement: reuse only through the API terms; not read directly (blocked), from secondhand quotes | avoid | no | API only |
| Longecity | no list or wiki found; forum posts | — | — | — |

**TripSit's non-commercial condition fits SubNetwork as it is**: a free site
with no advertising or payment. It would need revisiting if that changed.

**Share-alike most likely does not reach SubNetwork's data.** A name used as
the reason a molecule is entered copies nothing of the list, so it is not an
adaptation of it; share-alike would attach only to what was copied — a
category, a description — and only to that. This reasoning is untested for
compilations. ChEMBL's own CC BY-SA 3.0 already governs the data either way.

## Lists not yet compared

**Worth weighing, best first.**

1. **MeSH *Nootropic Agents* (D018697).** Already in the database through the
   `mesh_pa` backfill: 19 catalogue entries carry it, 14 in the cohort and 5
   entered from the wiki (the 2026-10-14 build). It is the one nootropic list
   that is already identifier-keyed under this project's rules, and MeSH is
   already pinned. How many MeSH records outside the catalogue carry it is
   unmeasured.
2. **Wikipedia's list articles and categories.** *List of designer drugs*
   (about 600 or more, estimated from a truncated read: new psychoactive
   substances, nitazenes, modafinil analogues and racetams, growth-hormone
   peptides), *List of psychoactive drugs*, *Category:Racetams* (28 pages) and
   *Category:AMPA receptor positive allosteric modulators* (27). CC BY-SA 4.0.
   The lists carry no identifiers, but each article's Wikidata item carries
   its ChEMBL id and InChIKey — the route the Wikipedia backfill already uses.
   The best open complement found.
3. **The EU Early Warning System** (EUDA, formerly the EMCDDA): more than 1,000
   new psychoactive substances notified by 2024. Official, and a strong reason
   for entry; its legal notice was not reached (403). EU institutions default
   to CC BY 4.0 "unless otherwise indicated", which needs checking for EUDA.
   Most of these substances are not in ChEMBL.
4. **The WHO ECDD repository**: more than 450 substances reviewed for
   international control since 1950, as PDFs. Authoritative, but a list of
   what is scheduled, not of what is nootropic; WHO's terms were not read.
5. **NCATS Inxight Drugs / GSRS**: 167,121 substances, identifier-keyed, its
   facts described by NCATS as public domain. It is the FDA's registry of
   everything, which this project already reaches through FDA UNII, not a
   selection — an identity source, not a reason for entry.

**Restricted: a link at most.**

| list | why |
| --- | --- |
| PiHKAL·info (Isomer Design) | CC BY-NC-SA 4.0 (read directly); its `robots.txt` refuses AI crawlers |
| ADDF Cognitive Vitality | access "solely … for Your personal and non-commercial use"; no derivative works |
| HighResNPS | "only intended for a closed user group and not open to the general public" |
| KEGG DRUG | "Non-academic use of KEGG requires a commercial license" |
| DrugsData (Erowid Center) | "not to publish results or analysis of our data without written permission" |
| SWGDRUG library | "All rights Reserved" |
| Cayman Spectral Library, UNODC Early Warning Advisory | behind a login |

**Not found.** No open list with identifiers covers semax, selank, the
Khavinson peptides or the drugs approved only in Russia; the Russian State
Register (GRLS) has no bulk export, and no peptide database checked lists them.
No list found is as broad as the sci-wiki, which stays the widest of them.

## Not read

The terms of Examine.com, Reddit, EUDA, WHO (ECDD and INN), the Broad
Repurposing Hub, Cayman, UNODC and Drugs-Forum; PsychonautWiki's GraphQL API;
and `robots.txt` for Wikipedia, Wikidata, TripSit and DrugBank. Each is a
reading to do before that source is used.
