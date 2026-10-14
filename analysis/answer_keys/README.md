# The answer-key audit

Read-only. Asks what the ATC answer key in
[../similarity_harness/](../similarity_harness/README.md) calls a top-1 miss,
and whether each one is a miss. It calls the page's own `sharedTargets` through
the harness, changes no file and adopts nothing. The findings, and what they
mean for choosing better keys, are in
[../../docs/SIMILARITY-LITERATURE.md](../../docs/SIMILARITY-LITERATURE.md),
Part 3.

```bash
node analysis/answer_keys/audit.mjs            # the summary
node analysis/answer_keys/audit.mjs --misses   # every top-1 miss, classified
node analysis/answer_keys/audit.mjs --classes  # every class, with its name
```

It needs `viz/graph.data.js` and `viz/gtopdb.data.js`, which are generated and
gitignored, and exits 2 without them. It opens `db/cohort1.db` read-only for
the ATC class names alone, since the payload no longer carries them, and prints
codes without names when there is no database.

Each miss goes in the first bucket that holds: the top answer shares the
query's ATC level 3 (**sibling**), shares a MeSH action (**mesh**), carries no
N code with a classmate (**unlabelled**, which the key cannot judge), or none of
these (**other**). The **filtered** grade walks the same list past only the
molecules the key can judge. It is the filtered setting of link-prediction
evaluation, and it changes no ranking.

Its filtered grade counts a molecule as judged only when it carries an N code
with a classmate. The harness's own filtered reading (`grade(...).filtered`,
docs/SIMILARITY-HARNESS.md §13) counts any molecule the key places, a class of
one included, so the two figures differ; the harness's is the one Status
quotes.

```bash
node analysis/answer_keys/agreement.mjs                  # every pair of keys
node analysis/answer_keys/agreement.mjs atc epc          # just these two
```

`agreement.mjs` asks how far the answer keys agree with each other before
either judges the ranking: over the molecules both keys judge, the share of
one key's classmate pairs the other also calls classmates. Its keys come from
the harness's `KEYS`, so the repaired ATC and FDA keys need `db/cohort1.db`.
