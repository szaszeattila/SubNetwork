# SubNetwork

An explorable map of what molecules developed for neurological and psychiatric
conditions act on. Click caffeine, see its receptors, and see which other
molecules act on them. Each line is a claim from a public database: which
protein the molecule acts on, how it acts there (agonist, antagonist,
inhibitor, …), and how much published evidence stands behind it.

**Exploratory and educational. Not medical, dosing or safety guidance.** Two
molecules that share targets here are not interchangeable drugs, and the page
says nothing about taking drugs together.

## What it is built from

- **ChEMBL 37** (EMBL-EBI): the molecules, their targets, the measurements and
  the curated mechanisms, and how far each molecule got in clinical
  development.
- **The IUPHAR/BPS Guide to Pharmacology** (release 2026.3): a second curator's
  account of how each molecule acts at its main targets.
- **MeSH, UniProt, ClinicalTrials.gov and Wikidata**: drug classes, protein
  identities across species, trial status, and Wikipedia links.

The catalogue holds about 1,300 molecules and 2,600 targets. The exact figures,
generated from the build, are in **Status** in [CLAUDE.md](CLAUDE.md).

"Similar" here means sharing targets, weighted by evidence, discounted by how
common the target is, and divided by how much each molecule does. That is a
much weaker claim than "these drugs act alike", and the page says so.

## Running it

The page is `viz/index.html`: one self-contained file that opens straight from
disk, with no server and no build step. The data it loads is generated and is
not in the repository. To build it, you need the ChEMBL 37 release (a 5.8 GB
download) and about 30 minutes; [docs/REPRODUCING.md](docs/REPRODUCING.md)
goes step by step.

The tests need no data and run offline in seconds:

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests
node --test "tests/*.test.mjs"     # Node 21 or later
```

## Where things are

- [CLAUDE.md](CLAUDE.md) is the project's rulebook: the goal, the data model,
  the invariants, and every rule the viewer follows, each with the mistake it
  prevents. It is written for the AI assistant (Claude) the project is
  developed with, and is the most complete statement of how the project works.
- [docs/INDEX.md](docs/INDEX.md) lists every document and says which are in
  force, which are proposals and which are history.
- `scripts/` holds the pipeline, `viz/` the page, `tests/` both suites, and
  `analysis/` read-only measurements, such as how well the similarity ranking
  matches the WHO's drug classes.

## Contributing, security and citing

Error reports and pull requests are welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md). Please report a security problem privately,
as [SECURITY.md](SECURITY.md) describes. To cite the project, use GitHub's
**Cite this repository** button ([CITATION.cff](CITATION.cff)), and cite ChEMBL
and the Guide to Pharmacology too.

## Licence

The code is under the MIT License ([LICENSE](LICENSE)) and the documentation
under CC BY 4.0. The data stays under its sources' terms: ChEMBL's under
CC BY-SA 3.0, and the Guide to Pharmacology's under the ODbL with its contents
under CC BY-SA 4.0, which is why the two are exported to separate files.
[NOTICE](NOTICE) has the details.
