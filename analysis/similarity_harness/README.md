# The similarity harness

Grades `viz/index.html`'s own similarity ranking against an answer key nobody
here wrote. Read-only: it changes no file and adopts no constant. The headline
key reads only the payload; the repaired ATC key also opens `db/cohort1.db`
read-only, and refuses one built at a different time from the payload.

```bash
node analysis/similarity_harness/evaluate.mjs            # the grade
node analysis/similarity_harness/evaluate.mjs --json     # what ## Status reads
node analysis/similarity_harness/evaluate.mjs --key mesh          # MeSH actions
node analysis/similarity_harness/evaluate.mjs --key atc-repaired  # every ATC level
node analysis/similarity_harness/sweep.mjs               # every constant
node analysis/similarity_harness/sweep.mjs evidence_curated --movers
```

Both need `viz/graph.data.js` and `viz/gtopdb.data.js`, which are generated and
gitignored. Without them they report a missing payload and exit 2, rather than
grading nothing and printing a number.

| file | what it is |
| --- | --- |
| `harness.mjs` | answer keys, grading, and the constant patching. The reasoning lives at the top of it. |
| `atc_repaired.json` | the repaired ATC key's exclusion list, versioned, every entry with its reason |
| `evaluate.mjs` | the grade, the worst-ranked molecules, and the per-class breakdown |
| `sweep.mjs` | one constant at a time over a grid, with `--movers` |

The method, why the answer key is generated rather than written, and what the
first sweep found are in [../../docs/SIMILARITY-HARNESS.md](../../docs/SIMILARITY-HARNESS.md).

Three things about it are load-bearing and easy to undo by accident:

- **It calls `sharedTargets` in the page**, through the same vm sandbox the
  viewer tests use. Reimplementing the score here would mean grading a copy.
- **The answer key is ATC level 4**, read from `molecules.atc_level5`. The
  `X` classes are dropped: `N06AX` is "other antidepressants", a group defined
  by *not* sharing a mechanism, so grading against it awards a point for a
  wrong answer.
- **A new key or reading reports beside the headline, never in its place.**
  Every key prints the headline walk, the same walk *filtered* to molecules
  the key can judge, and nDCG@10; `--key atc` stays the figure in Status, so
  that it is comparable across builds. A change to `atc_repaired.json` is a
  change of instrument: bump its version and say why in
  docs/SIMILARITY-HARNESS.md, never in the same change as a constant it judges.
- **Molecules with no reachable class peer are counted apart**, never as
  failures. Several constants change what is eligible, so folding coverage into
  the denominator would let a constant raise the grade without improving one
  ranking.

The grade is a proxy. ATC groups mostly by chemical structure, partly by
mechanism, and ChEMBL curates mechanism most thoroughly for well-known drugs,
so it flatters any weighting term that rewards curation — which is exactly the kind of term the open
proposals would add. Quote it with that caveat attached.
