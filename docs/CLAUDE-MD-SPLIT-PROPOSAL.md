# Proposal: splitting CLAUDE.md

**Status: done, 2026-09-27, at the user's request** ("it seems Claude md is
becoming really big now"), when the file had reached 3,375 lines and 224 KB.
Options A and B were both taken: the legacy pipeline is in
[LEGACY-PIPELINE.md](LEGACY-PIPELINE.md) and the viewer's reasoning in
[VIEWER.md](VIEWER.md), both moved verbatim. Option B's own warning was
followed rather than overridden: CLAUDE.md keeps each viewer rule with its
one-line reason and the example that makes it non-arbitrary, and points at the
full paragraph. What follows is the proposal as written on 2026-09-17,
alongside the change that made the `## Status` figures generated.

The question is whether `CLAUDE.md` should stay one file. It loads into context
every session, and it has grown to a size where that is a real cost. The
argument against splitting it is stronger than it looks, so it is stated first.

## What the file is now, measured

From `wc -lwc CLAUDE.md`, and from a walk of its `##`/`###` headings:

| | |
| --- | --- |
| lines | 1,967 |
| words | 20,701 |
| bytes | 128,370 |

**Token counts below are estimates, not measurements.** No tokenizer is
installed here. At 4 bytes/token the file is ~32,100 tokens; at 1.3
tokens/word, ~26,900. Every figure below is the bytes/4 estimate, and the real
number is likely 15-20% lower. Treat them as proportions, which is what the
decision turns on, rather than as a budget.

| Section | Lines | Bytes | ~tokens |
| --- | ---: | ---: | ---: |
| `## Two pipelines` | 19 | 960 | 240 |
| `## Goal` | 45 | 2,473 | 618 |
| `## Running it` | 103 | 6,161 | 1,540 |
| `## Layout` | 39 | 2,363 | 590 |
| `### The cohort database` | 65 | 4,094 | 1,023 |
| `### The legacy database` | 78 | 5,278 | 1,319 |
| `## Sources` | 27 | 1,661 | 415 |
| `## Invariants` | 85 | 5,878 | 1,469 |
| `## Status` | 80 | 4,840 | 1,210 |
| `### The viewer` | 651 | 44,564 | **11,141** |
| `### Not done — the cohort pipeline` | 101 | 6,257 | 1,564 |
| `### The legacy seed database — history` | 501 | 33,013 | **8,253** |
| `### Not done — the legacy seed pipeline` | 97 | 6,661 | 1,665 |
| `### Published snapshot` | 42 | 2,520 | 630 |

Two sections are 61% of the file between them: `### The viewer` and the legacy
history. Everything a session needs to *act correctly* — the goal, the
commands, the layout, the cohort data model, the invariants, the status and the
current backlog — is about 8,700 tokens, a little over a quarter.

## The argument against splitting

The invariants in this repository have survived because the reasoning that
produced them sits next to them and is read by accident. Invariant 6 is not
"match exactly"; it is "match exactly, *because* `gene_exact:ADRA1A` ranks
ADRA1D first, because the receptor cloned as alpha-1a was reclassified". An
agent that has read the second clause does not relitigate the rule at 2am. An
agent that has read a one-line summary does.

That is not a hypothetical. The failures this document records — the sampled
citation, the two confidently-wrong Wikipedia derivations, the action colour
that fell through to `BINDER`'s grey — are all cases where a rule looked
arbitrary until someone read why it existed. Moving the why into a second file
means it is loaded when someone goes looking, and going looking is exactly what
does not happen under time pressure.

So the trade is not "tokens against prose". It is **tokens against the
probability that a rule gets broken again**, and the history of this repository
says that probability is not small.

## Option A — move the legacy pipeline out (recommended)

Move to `docs/LEGACY-PIPELINE.md`:

- `### The legacy database (db/schema.sql)` (~1,319)
- `### The legacy seed database — history` (~8,253)
- `### Not done — the legacy seed pipeline` (~1,665)

Leave behind, in `## Two pipelines`, the three facts a session actually needs:
the legacy pipeline exists, it is the rollback path, and **do not modify it**.
Plus a link.

**Saving: ~11,200 tokens, about 35% of the file.**

Why this one is safe, where a viewer split is not: none of that text governs
work on the current pipeline. It explains a pipeline that nothing reads, whose
code is not to be touched, and whose rules have *already* been promoted into
`## Invariants` — which stays. The reasoning-next-to-the-rule argument above
protects the invariants; it does not protect 500 lines of seed-cohort selection
narrative that no current task can act on.

The cost is real but bounded: the second and third seed cohorts' selection
reasoning is genuinely good material on how to expand a graph without
manufacturing similarity, and the cohort pipeline will face that question
again. It should be linked from `### Not done — the cohort pipeline`, not just
from `## Two pipelines`.

## Option B — A, plus split the viewer's reasoning

Additionally move the *why* of `### The viewer` to `docs/VIEWER-DECISIONS.md`,
leaving a summary of what the viewer currently does.

**Saving: perhaps ~19,000 tokens total, about 60%.**

**Not recommended.** This is the section the argument against splitting is
about. It is 651 lines and most of them are load-bearing in the specific way
that matters: the `stabilize()` bug that is invisible in the viewer's own code,
why the selection must not repaint an edge's colour, why `singleProteinByAccession`
returns null on a duplicated accession, why direction is read at every shared
target including the subsumed ones. Every one of those reads as an arbitrary
implementation detail without its paragraph, and every one of them would be
"simplified" away by a confident agent that had not read it.

If it is ever done, the split should be by *age* rather than by kind — the
viewer decisions that are settled and have not been touched in months move; the
ones describing behaviour still being changed stay — and that is a judgement
call needing a person, not a rule.

## Option C — split nothing, index instead

Keep the file whole and add a table of contents with the section byte sizes, so
a session can see what it is about to read. Saving: none, minus the index.

Worth mentioning only because it is the honest baseline: the file being long is
not itself the defect. The defect that was just fixed was numbers going stale,
and that is fixed by generation rather than by length.

## Recommendation

**Option A, and not now.** The legacy split is low-risk and pays 35%. But the
same commit that generated the `## Status` block just moved the current backlog
next to the current work, and the file has not been read at its new shape yet.
Doing both at once means neither gets evaluated.

The thing to watch is whether `### The viewer` keeps growing. At 651 lines it is
already half again the size of everything actionable in the file put together,
and it grows with every viewer change, because this project's convention —
correctly — is to write down why. That convention has no upper bound, and Option
B is the bill for it eventually coming due.

**This is the user's call.** The reasoning prose being present is plausibly why
the invariants have survived, and nobody should trade that for context budget on
an agent's initiative.
