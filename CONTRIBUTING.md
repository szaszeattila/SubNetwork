# Contributing

Contributions are welcome: error reports most of all, and pull requests too.

## Reporting an error in the data

Open an issue. Name the molecule and the target (a ChEMBL id is best, such as
`CHEMBL113` for caffeine), say what the page shows and what you think is
right, and give the source that says so: a paper, a drug label, or another
curated database. A page link that opens the molecule (the address bar carries
it) saves a step.

Many errors are upstream, in ChEMBL or the Guide to Pharmacology, and are best
fixed there. This project does not rewrite a source's record. Where one is
known to be wrong, it is withheld with the reason shown on the page, and the
source is told. Alfuzosin's alpha-1 action is the example: see
[docs/CHEMBL-ERROR-REPORT-ALFUZOSIN.md](docs/CHEMBL-ERROR-REPORT-ALFUZOSIN.md).

## Changing the code

1. Read the part of [CLAUDE.md](CLAUDE.md) your change touches. It is the
   project's rulebook: the invariants and the viewer rules each record a
   mistake that was made once. It is written for the AI assistant the project
   is developed with, and is also the most complete statement of the rules.
   [docs/INDEX.md](docs/INDEX.md) says which document explains which rule.
2. Before changing how any value gets into the database, read
   [docs/DATA-QUALITY-LOG.md](docs/DATA-QUALITY-LOG.md). Before changing what
   the page draws, scores or says, read [docs/VIEWER.md](docs/VIEWER.md).
3. Run both suites. They run offline in seconds, and need nothing beyond
   `requirements.txt` and Node 21 or later:

   ```bash
   python3 -m unittest discover -s tests
   node --test "tests/*.test.mjs"
   ```

   A change that moves the similarity ranking should also say what
   `node analysis/similarity_harness/evaluate.mjs` reports before and after.
   That needs a build: see [docs/REPRODUCING.md](docs/REPRODUCING.md).
4. Keep the page one self-contained file with no build step: one inline
   `<script>`, no inline event handlers, and everything from the data escaped.

Leave the legacy pipeline (`scripts/build_db.py` and the files listed beside it
in CLAUDE.md) alone; it is kept unchanged as a rollback path. Documents go in
`docs/` as markdown and are listed in `docs/INDEX.md`.

## How changes arrive here

This repository is where the project is developed. A pull request is reviewed
and merged here, and keeps its own commits and its author. Only `main` is
published; work in progress is not pushed as branches, so open a pull request
against `main`.

## Licence

By contributing, you agree that your contribution is licensed as the part of
the project it touches is: code under the MIT License, documentation under
CC BY 4.0 (see [NOTICE](NOTICE)).
