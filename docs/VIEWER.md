# The cohort viewer — design reasoning

Moved out of `CLAUDE.md` verbatim on 2026-09-27 (option B of
[CLAUDE-MD-SPLIT-PROPOSAL.md](CLAUDE-MD-SPLIT-PROPOSAL.md)), when this section
alone had reached 1,672 lines. `CLAUDE.md` keeps a compact list of the rules
below, each with its one-line reason; **this file is the reasoning, and it is
the thing to read before changing any behaviour a rule there describes.**
Every rule here exists because the obvious alternative was tried, measured
or shipped, and made the picture misleading.

## The viewer

The page opens on **caffeine** (decision D13) and draws **the whole eligible
network**, with the selection lighting a neighbourhood inside it: caffeine, its
43 eligible targets, and the 265 other molecules on those targets, over the rest
of the network held dim rather than removed. Under the defaults that canvas is
1,035 molecules, 1,663 targets and 11,599 edges; narrowed to Supported claims
and direct-human assignments it is 849 / 543 / 2,077. Those are counted since
a protein became one node in every species (2026-10-10, *One protein, one
node*, below); before it the default canvas was 2,063 target records and 12,835
edges, the figure most measurements on this page were taken against. Search, the filters, the
similarity ranking and the gap statements all read the whole catalogue, so
membership never depends on what is drawn.

**The tier and basis defaults are open, and that was measured rather than
argued.** Held at Supported and direct-human, the median catalogue entry reached
exactly one target — which is not enough to rank anything on. 84% of similarity
lists had a tied top score, the largest tie ran to 58 molecules, and the sort
fell through to comparing names, so nine of the twelve commonest "most similar"
answers began with the letter A. Opening both takes the median entry to five
targets and the tied-top share to 20%. The catch, and the reason this could not
have been done on its own: opening them while the score was still an
unnormalised sum over flat-weighted targets made the ranking *worse*, because
the added claims are weaker and more promiscuous and nothing could tell them
apart. The prevalence discount and the normalisation are what make the extra
evidence pay. All three landed together for that reason, and the numbers are in
[docs/SIMILARITY-HARNESS.md](SIMILARITY-HARNESS.md).

The two filters do not come apart, either, and that is the thing to know before
reverting half of this. Holding the scoring fixed, **opening only one of them is
worse than opening neither** — Preliminary alone grades 33.2% and the broader
layer alone 35.5%, against 38.2% for both held strict and 42.4% for both open.
There is no conservative middle setting here; the apparent compromise is the
worst of the four.

It used to draw one neighbourhood at a time and rebuild the canvas on every
click. That answered "what does caffeine act on" and lost the question this
graph exists for — where that neighbourhood sits among the others. Nothing held
still between two selections, and there was no way to see that two molecules
are near each other without opening them as a pair first. **The filters decide
what is on the canvas and the selection decides only what is lit**, which are
two questions that used to be answered by the same rebuild.

The cost is that the resting picture is dense, and it is paid six ways.

*A selection writes opacity and never rebuilds*, so the layout does not move
under a reader who only clicked. *Physics is switched off* once the layout has
settled, because at 12,835 edges every drag would otherwise re-solve the graph.

That paragraph used to end "— 1 ms over 1,373 nodes", and both halves of that
were wrong by the time anyone measured them. The canvas is **3,097 nodes** at
the default filters — 1,034 molecules and 2,063 targets, which the same section
states correctly a few lines above — and a selection cost **187 ms**, not 1.
What the sentence was describing is real and still true: a selection changes no
structure, so nothing is rebuilt. What it had not noticed is that vis rebuilds
anyway, on being told. See **what a frame costs** below, which is where the
figures now live, measured rather than recalled.

*A filter change solves the layout to completion and then glides to it.* The bug
underneath this is worth keeping, because nothing about it is visible in the
viewer's own code: **changing the DataSets does not call vis's `stabilize()`**.
vis answers a data change with `startSimulation()`, which animates the whole
graph on screen frame by frame until every velocity falls under tolerance — many
seconds at 3,097 nodes — and it never emits `stabilizationIterationsDone`, so the
handler that switches physics off was waiting for an event that was not coming.
A filter change was the one path on this page where the simulation ran free.

So a re-solve now asks for one: `network.stabilize(n)`. vis blocks redrawing for
the whole of a stabilization and paints once at the end, so the solve runs to
completion **unseen** rather than being watched or cut off half way, and the
batch loop exits the moment the layout converges — usually well short of the
budget, because every surviving node is handed to the solver at the position it
already had. Physics goes off when it reports back, so the `startSimulation()`
call at the end of vis's own `_finalizeStabilization` has nothing to animate.

What the reader sees is a transition the page owns: each node glides from where
it was to where the finished solve put it, over **600 ms**, on a cosine ease so
it starts and ends still. A node the change added has nowhere honest to travel
from and is simply left where the solve put it; a node that moved less than two
pixels is not worth a frame. The movement still says the picture changed, and
now it is movement toward an answer rather than the search for one — the layout
is never left somewhere the solver did not choose, which is what cutting a solve
off on a timer did. The one-second timer survives as a **backstop only**: vis
returns early from `stabilize()` when it has no physics nodes, and a page
waiting on that would leave physics on. The first layout still gets the full
320-iteration solve and the fit, having nothing to start from; a re-solve does
not refit, for the same reason it keeps the positions.

*Labels are hidden when zoomed out*, except on whatever the selection has lit,
which stays named at every zoom: hiding the label on the thing just clicked is
the one way this could be worse than drawing all of them. vis applies a node's
opacity to its shape and **not** to its label, so the label is dimmed
separately, by colour — without that the highlight leaves every name at full
brightness, which on 3,097 nodes is most of the ink.

*The canvas is labelled in the vocabulary the field uses.* ChEMBL's protein
names run to 91 characters and would be 79,075 characters of ink across the
default canvas; a single protein is labelled by its **gene symbol** — ADORA1,
not "Adenosine receptor A1" — which covers 1,782 of the 2,063 targets drawn and
takes the total to 27,948, 65% less. A complex, complex group or family has
several components and no single symbol, and picking one would assert exactly
the merge D06 refuses, so those keep their own name, shortened at 26 characters
(194 of 3,097 labels). `target_components.gene_symbol` stays a label and never a
matching key, which is invariant 6. The full name is never cut in the panel.

*A control of its own thins the canvas*, and it is the only thing on this page
that takes something off the picture without taking it out of the catalogue.
810 of the 1,663 targets on the default canvas have exactly one molecule at
them — the off-target fringe, one edge each, and most of what makes the picture
hard to read at rest. **Hide single-molecule targets** leaves 853 targets, 992
molecules and 10,789 edges, and its banner states the whole cost including the
43 molecules left with nothing to draw. (Counted per protein node since
2026-10-10; per record it was 1,036 of 2,063.) It is off by default, and it is a
*drawing* rule rather than an eligibility rule: `claimVisible` answers "is this
in the picture" and only the eligibility filters may change that answer, while
this one answers "is this drawn". The panel's lists, the similarity ranking,
the gap statements and search all still read the whole catalogue, so nothing
becomes unfindable by being undrawn — caffeine's 59 visible claims and 265
shared-target rows are identical with it on and off.

**Trial sites is the one eligibility filter about the molecule rather than the
claim** (2026-10-13, a proposal on the `worktree-foreign-trials` branch,
[FOREIGN-TRIALS.md](FOREIGN-TRIALS.md)). It keeps the molecules whose Phase 1+
in-scope trials, as ChEMBL cites them, list a site in the US, anywhere, or
outside the US, and drops every claim of the rest. It is in `claimVisible`
rather than a drawing rule because the question it answers — "what does the
picture look like on trials outside the US alone?" — is not answered by a
canvas that still ranks the dropped molecules as neighbours. Its default moves
nothing; it is offered only where the payload carries sites; and its banner
counts the hidden in molecules, split into those with no trial ChEMBL cites
(an ATC N member, a label) and those whose trials are on the other side, which
are two different facts. On D21's build the four settings keep 2,452, 1,528,
2,087 and 1,501 molecules.

**What a frame costs, and the two things that were paying for nothing.** The
page was slow to zoom and slow to drag, and the reason was not the size of the
picture. The table below is the *JavaScript* side of a frame — the time to issue
the canvas calls — measured in Chrome over this build at 1180×867 through the
browser's own input pipeline. It is real and it is not the whole frame; **the
painting is measured separately, below, and was the larger half**:

| | before | now |
|---|---|---|
| issuing a frame while wheel-zooming, fitted | 25.8 ms | **12.5 ms** |
| issuing a frame while dragging, fitted | 20.8 ms | **9.9 ms** |
| a selection | 185.7 ms | **20.5 ms** |
| a frame of the glide after a filter change | 52.4 ms | **0.04 ms** |

And the frames a reader actually sees, presented on the GPU during a
continuous pan with caffeine selected — an RX 6600 through ANGLE/OpenGL, the
path a desktop Chrome paints with, at 1600×1000 and again at 2560×1440:

| zoom | before the dash rule | now |
|---|---|---|
| fitted (0.12) | 83 ms | **16.7 ms** (60 fps) |
| 0.5 | 67–83 ms | **16.7 ms** |
| 1 | 33–50 ms | **16.7 ms** |
| 2 and deeper | 16.7 ms | **16.7 ms** |

**Every timer on this page had been measuring the wrong half of the frame.**
`performance.now()` around `_redraw` brackets the JavaScript that issues canvas
calls. Chrome does not paint there: it records the calls and rasterises at the
next flush, so the painting sat outside every measurement in this file, and
“zoomed in is the cheap case” was true of the calls and false of the frame. It
was reported as “zoomed in it's basically unusable” while every recorded number
said otherwise. Two instruments see it: a one-pixel `getImageData` after the
redraw, which forces the flush (and is only honest in software raster — on a GPU
canvas it forces a readback and distorts what it measures), and presented frame
intervals during a real pan with the GPU on, which is what the table above uses.
Headless Chrome is launched with `--disable-gpu` by default and paints in
software, where the costs are different enough to point the wrong way:
batching looked expensive there and is the cheaper option on the GPU.

Neither cause was in the picture, and both were vis doing work in proportion to
the graph rather than to the change.

*vis culls nodes to the viewport on every frame and never culls edges.* Its
`_drawNodes` tests each node's bounding box against the visible rect;
`_drawEdges` and `_drawArrows` walk `body.edgeIndices` end to end. So the edge
cost was flat at every zoom — 17 ms of a frame whether all 12,835 lines were on
screen or a dozen were — and zoomed in on one molecule the page was drawing the
whole network to show a corner of it. `edgeInRect` is the missing half of vis's
own rule, and an edge outside the window is not part of the picture: not drawing
it changes no pixel, which is asserted rather than argued — 13 views across four
positions and three zooms paint byte-identical canvases culled and unculled.

It is **not** a filter and must never be described as one. `claimVisible` still
answers what is in the picture and only the eligibility filters may change that
answer; the canvas control still answers what is drawn; this answers neither. It
answers what is on screen, which is a question about the window and not about
the data, and the panel lists, the ranking, the gap statements and search cannot
see it at all.

It is a **clip and not a bounding-box overlap**, which was the first attempt
and bought almost nothing: this layout is hubs and spokes, so a great many edges
are long, a long edge's box is large, and any box containing the window passes.
The box rule kept 9,876 of 12,835 edges at zoom 2.0 where the clip keeps 60.

**Fitted out, a gesture gives up nothing**, and the two rules that did give
something up are kept here because they were the same mistake at two sizes.

There, every line genuinely is on screen and the cull can save nothing by
definition, so the first attempt dropped every line for the frames the reader
was moving the canvas — vis's own `hideEdgesOnDrag` bargain. That made the lines
from a selected molecule to its targets vanish for the duration of a zoom or a
drag, which is the single thing a reader is most likely to be moving the canvas
in order to see. The second kept exactly those — 43 edges for caffeine, 240 at
the very worst in the catalogue — and dropped only the dim haze of everything
else. Better, and still wrong: the haze is most of the ink, so the picture
changed the moment a gesture began and changed back when it ended, which reads
as the page glitching rather than as a considered simplification. Both rules
were answering “what should be sacrificed”, and the question was wrong.

**The edge pass was about three times more expensive than the drawing it did.**
Per edge vis builds a fresh `rgba(...)` *string* from the hex colour and the
opacity, assigns it to `ctx.strokeStyle` — which makes the canvas parse a colour
— sets the width, and for a dashed edge does a full `ctx.save()`,
`setLineDash`, draw, `setLineDash([0])`, `ctx.restore()`. On this canvas 11,752
of the 12,835 edges are dashed, so that is 11,752 canvas state saves and
restores and 12,835 colour strings built and parsed, for a picture with **eight
distinct line styles in it**.

`drawEdges` draws the same lines with that taken out: the `rgba()` string
memoised per colour-and-opacity, and the whole canvas drawn as **one path per
style** — nine of them over 12,835 lines — rather than one stroke, one colour
parse and one state change per line. A frame at the fitted view goes from
26.8 ms to about 11 ms and the edge pass from roughly 19.5 ms to 3, which is
what makes the whole canvas affordable while moving. Nothing is dropped at any
zoom, with or without a selection, and a frame drawn mid-gesture is identical to
one drawn at rest across nine views — which is the property the reader actually
asked for, and the one the tests assert.

**The haze had to stop accumulating, and that is why batching is not just an
optimisation.** The dim, echo and resting edge opacities were 0.06, 0.3 and
0.55, and at those values the lines buried the thing they connect: 12,835 of
them over 3,097 nodes is four lines per node, they cross everywhere, and an
unselected node is drawn at 0.12. Reported as “it is hard to see any molecule or
target with the haze”, which is the picture failing at the one job the Goal
states. Lowering the three numbers — now **0.015, 0.35 and 0.22** (the second hop was 0.1 until it proved too faint to follow, below) — is half the
answer and could not have been all of it, for a reason that is not obvious:
alpha accumulates, so n lines crossing one pixel leave 1-(1-a)^n. At the old
0.06 a mere twenty overlaps reached 0.71 and the crowded middle went solid
whatever the individual line was set to; even at 0.015 a hundred overlaps still
reach 0.78. The number fixes the sparse parts of the canvas and does nothing for
the crowded middle, which is exactly where the nodes were being lost. Drawing
each style once composites the overlap **once**, so a region with a thousand
lines through it is as faint as a region with one, and what is left on top of it
is the nodes.

What is **not** given up: every edge is still drawn, in its own colour, at its
own width, dashed or not. Nothing is dropped, sampled or merged. The single
thing the picture no longer says is *how many* lines cross a given pixel, which
it was only ever saying by going opaque — which is the failure being fixed.

This paragraph used to say the change was large — “29.8% of pixels differ, by
a mean of 48/255” — and that figure was wrong by about twenty times. It was
read off the graph canvas itself, which is **transparent**: a line at 0.8%
alpha is stored premultiplied as roughly `(2,1,0,2)`, reads back un-premultiplied
as bright orange-red, and was counted at that colour when on screen it is
nearly invisible over the background. The same artefact is why screenshots of
this canvas taken with `toDataURL` show a red mesh that no reader ever sees.
**Composited over the page's own background, `rgb(15,17,21)`, batching moves
the picture by a mean of 1.4–2.7 shades out of 255**, and more than 8 shades on
at most about 1% of pixels. Any pixel comparison of this canvas has to
composite first — in arithmetic, because drawing the canvas onto a second
canvas measured as non-deterministic here where the canvas itself is not — and
has to show a same-frame control of zero before its numbers mean anything.

An earlier version of this stroked each edge separately and was **byte-identical
to vis**, which is a property worth naming because it was deliberately given up
rather than lost. What replaces it as the guarantee is narrower and still
checkable: every line is drawn, and the buckets are stroked **faintest first**.
Drawing a style at a time reorders the canvas — where two lines of different
colours cross, which is on top is now decided here rather than by the order vis
happens to hold the edges in — and an order decided by accident is the part of
that worth fixing. By opacity is the one ordering this page can defend: what the
selection lit is what the reader is looking at, so it goes on top of the haze
rather than under it.

The one piece of vis arithmetic that had to be copied rather than skipped is
worth keeping, because it was found by comparison and not by reading. `Edge.getFormattingValues` ends with
`width = Math.max(width, 0.3 / scale)` — a floor of 0.3 *device* pixels, so at
the fitted view a width-1 line is drawn at 2.7 and a width-2 line at 2.7 as
well. Missing it made the prototype thinner than the real thing on every single
line: **78,683 differing pixels**, found by the comparison rather than by
reading. `drawEdges` also declines rather than guesses — an inherited colour, a
shadow, a background, an arrow, a hover, a self-loop, a colour that is not hex,
a `chooser` function — and hands the frame back to vis whole, because a canvas
drawn half one way and half the other is the failure mode with no upside.

*And vis keeps two copies of everything.* There is the row the page put in the
DataSet and the object it draws, and vis answers any write to the DataSet by
rebuilding its data model for the whole graph — which costs the same whether one
edge changed or all 12,835. Updating a **single** edge measures 37 ms here.
`applyHighlight` made two of those writes on every selection, and a selection
changes no structure at all: the same nodes and edges, in the same places,
painted differently. That was the 187 ms, and it is not only a click cost —
`syncLabels` calls the same function when a zoom crosses the label threshold, so
the stall was landing in the middle of a gesture too. The glide after a filter
change was the same mistake once per animation frame.

So a highlight and a glide are painted onto the objects vis draws, and the
DataSet is left to the things that really do change it: `renderGraph`'s
clear-and-add, which is the only place structure moves. A node is painted
through its own **`setOptions`**, which is exactly what the DataSet path ends in
— vis's handlers walk the changed rows and call it — so this is that path minus
the graph-wide rebuild rather than a second way of styling a node. An edge's
colour is written straight onto its options, which is 1 ms against 68 for
12,835 of them, and that is an assumption about vis rather than its API, so it
is **checked at runtime**: the cheap path is taken only where `edgeType.options`
*is* `edge.options` rather than a copy of it, and an edge that fails the check
goes through `setOptions` instead. Both are fast paths and neither is the only
one: given a vis whose object model is not the shape they expect they paint
nothing and say so, and the caller writes the same payload to the DataSet
exactly as before. Ten selections across two zooms paint the same pixels as the
DataSet path.

**Writing onto `node.options` instead of calling `setOptions` does not work, and
was shipped once.** It is worth the space, because it looked right, it was
fast, and the test written beside it passed. A vis `Node` keeps its label
settings in a `labelModule` holding its **own copy** of the font —
`labelModule.fontOptions` is not `options.font` — and only `setOptions` syncs
them. Written the direct way, every label went on drawing at whatever the last
DataSet write left it at, which is the global resting font from page load: all
**3,097** labels at size 12 in the bright kept colour, where a selection lights
**309**. The canvas became a wall of unreadable white text with no visible
highlight in it — which is the exact channel the paragraph on dimming labels by
colour exists to protect, defeated from the other end.

The test that missed it is the more useful lesson. It reset the canvas between
the two paths *through the DataSet*, which is the path that works, so both sides
were measured from a synced starting point; and it called
`setSelection({kind, id})` when the signature is `setSelection(kind, id, extra)`,
so all four of its "different selections" were the same no-selection state. A
comparison that cannot fail is not evidence. The one that replaced it drives the
page through `select()`, the way the click handler does, and was run against the
broken build first to watch it report 0 of 10 before it was allowed to report 10
of 10. The unit tests around it model vis's split — a fake node whose label
module only follows `setOptions` — and four of them fail when the direct write
is put back, one of which is simply a grep for `.options.font.size =`.

One thing that was already wrong and is now fixed rather than inherited: vis's
dashed-line draw sets `ctx.lineCap = "round"` **before** its own `save()` and
restores everything except that, so the cap leaked and every edge drawn after
the first dashed one in a frame inherited it. A line's ends were a function of
how many dashed edges preceded it, which used not to matter because the answer
was always "all of them". Culling changes the count, and the pixel comparison
caught it — 960 sub-perceptual pixels across two of thirteen views. The cap is
stated at the top of the edge pass now, which costs nothing and takes the frame
off the list of things that depend on the viewport.

*And vis's arrow pass draws nothing, twice a frame.* No edge on this canvas
carries an arrow, and `_drawArrows` is a second full walk of the edge list that
asks three questions of each one and paints nothing: **1.9 ms of every frame**
at the fitted view, more than the cull saves there. It is skipped when the edges
say they have no arrows, checked the same way everything else on this path is
checked — once against the first edge, with the whole pass handed back to vis
the moment one disagrees.

**And the dashes were most of the painting.** Measured on the GPU, solid lines
hold 60 fps at every zoom, line width makes no difference at all, and dashed
lines cost the fitted view 83 ms a frame and a 1× view 50. Chrome's GPU backend
cannot dash on the GPU: it cuts each dashed line into its dashes on the CPU and
uploads the pieces, and 11,752 of the 12,835 edges are dashed. Most of those
dashes cannot be seen — below about four device pixels a period a dash is not
visible as one (fitted, a 5-unit dash is 0.6 px), and in the 0.015 haze the
pattern is a modulation of four shades — so `dashIsVisible` sends those to the
GPU as solid lines at the alpha the pattern averages to (`dashCoverage`:
round caps lengthen each dash by the line's width). What stays dashed is exactly
what a reader uses: the selection's own lines, which say Preliminary by being
dashed, and the second hop once the zoom makes its pattern big enough to read.
Composited over the background the rule moves the picture by a mean of 1.5–4.3
shades, and at 2× the worst single pixel is 3 shades.

A dashed line that does stay dashed is **cut to the window before it is stroked**,
because Chrome lays out every dash of a line before clipping any of it and a kept
line here is typically thousands of units long with a few dozen visible. The cut
start is moved back to the last whole dash period, since the canvas restarts the
pattern at every sub-path and a start that moved with the view would make the
dashes crawl. In software raster this measured as no gain at all and was nearly
removed on that evidence; on the GPU it is the difference between 83 and 67 ms
at 0.5× with nothing selected. The instrument decides which way a change points.

**The band where the names appear was slow for a third reason, and the pan
test above could not see it.** Reported as “when you zoom in far enough to see
all the names it is laggy to drag; zoomed out and all the way in are not” —
after the table above said 60 fps at every zoom. The table was right about what
it measured and had measured the wrong thing twice over. Its pan moved the view
with `moveTo`, which does not fire the zoom event `syncLabels` listens to, so
the names never came on in any frame it timed; and it ran on the GPU. With the
names switched on and a real 250 Hz mouse drag through Chrome's input pipeline,
the GPU still holds 60 fps everywhere, at 2560×1440 and at 2× DPR. In
**software** raster it reproduces the report exactly — fast at both ends, and
150 ms a frame at 0.6×, 67 at 1× — and hiding every name changes nothing.

The cost there is line **width**. Skia paints a line under a pixel wide on a
dedicated fast path and anything wider by outlining and filling it; zoomed out
every line is under a pixel, zoomed all the way in only a few dozen are on
screen, and in between eleven thousand 1.5–4 px lines are. The width of a line
at 0.015 opacity cannot be read, so `lineIsFaint` draws it as a 0.9-pixel
hairline **at its own alpha** — the same threshold that already decides whether
its dashes are worth drawing. Keeping its ink instead (alpha raised by the ratio
of the widths) was measured and rejected: it packs the ink into a core four
times brighter than the line it replaces, more than 8 shades of change on
8–15% of pixels at 1.5–2×, where keeping the alpha changes a mean of
1.5–2.7 shades and more than 8 on almost none. A real software drag at
2560×1440 goes from 150 to 33 ms a frame at 0.6× and from 67 to 17 at 1×; the
GPU is unchanged. 0.6× in software is the slowest frame left, at 30 fps.

Whether a given reader's Chrome paints this canvas in software is not known
from here. The one Chrome profile on this machine has hardware acceleration on,
and headless Chrome on the same machine paints on the GPU only with
`--enable-gpu --use-gl=angle --use-angle=gl`; `chrome://gpu`, under Canvas,
is the place to check. The measurement harness for both lives in the job's
scratch directory and is not in the repository.

**And the cost grew with the selection, because the second hop was drawn in
detail.** Reported as “with BREXPIPRAZOLE selected the lag is worse, there seem
to be more of those very faint lines in the background” — in **Firefox**, which
paints this canvas in software during the draw call, so a redraw's JavaScript
time is its whole cost and the in-page timer finally measures the right thing.
Caffeine lights 466 second-hop lines; brexpiprazole lights 3,192, of which 2,654
dashed, and the antipsychotics run to 5,750 (chlorpromazine). At 0.1 those were
above the old 0.05 threshold, so each kept its dashes and its width. One redraw
with brexpiprazole selected was 37–39 ms at 0.6–1× and 61 at 2× that way, and
31/31/25 with the second hop drawn as background, within 1–2 ms of drawing
every line on the canvas as a plain hairline and level with caffeine.
`EDGE_DETAIL_MIN_OPACITY` was raised to 0.15, so the second hop is background too.

That left the second hop at 0.1 and too faint to follow — reported as "it is
hard to see what molecules are connected to the targets that a molecule that is
selected interacts with … that is kind of the point of the graph". What cost
frames was width and dashes, never alpha: every line is batched into one stroke
per style, so a brighter style string is the same strokes on the same fast
path. The second hop is now **0.35** and the threshold **0.5**, so it is still an
undashed hairline, only visible. The resting 0.22 falls under the threshold too,
which is the state **Clear selection** puts the page in.
What is given up is that, zoomed in, a second-hop line no longer shows Supported
by its width or Preliminary by its dashes; Firefox's own screenshots of
brexpiprazole before and after are indistinguishable by eye, the panel still
states that evidence, and the selection's own lines keep both.

Firefox needed its own harness: headless Firefox driven over WebDriver BiDi
(`--remote-debugging-port`, `input.performActions` for a real pointer drag,
`browsingContext.captureScreenshot` for pictures composited the way the screen
shows them). What is left there is a floor of roughly 20–30 ms a redraw at mid
zoom whatever is selected — about 15–20 of it the eleven thousand background
hairlines, the rest nodes and names. Drawing the background from a cached
image while the view is only being dragged is the next thing that would move
it, and is not done.

Absolute timings in this section drift by a factor of up to two between page
loads — each load solves a different layout, and the machine carries other work
— so every comparison quoted is between variants inside one page load.

**Nothing selected is reachable now, and its frame cost has not been
re-measured.** This paragraph used to say that state was slow at mid zoom —
15–30 fps at 0.5–2× — because every line rested at 0.22 with its dashes drawn,
and that the page could not get there. Both have changed: the threshold has since
risen to 0.5, so a resting line is an undashed hairline like the background of a
selection, and **Clear selection** (or Escape) now puts the page there on
purpose (2026-09-25, at the user's request). What the resting canvas costs
a frame today is unmeasured; if it is slow, this is where it will show.

What is **not** fixed is the floor, and it is now the largest thing left on the
JavaScript side.
Fitted out, vis's node pass is **6–7 ms** of the frame on its own and no culling
can help, because every one of the 3,097 nodes is on screen; the lit selection's
~309 labels are only about 1.4 ms of that. The rest is the same waste the edges
had — two `ctx.save()`/`restore()` pairs per node in `performFill` and
`performStroke`, and three `rgba()` strings built per node in
`getFormattingValues`, which is 6,194 canvas state saves and 9,291 colour
conversions a frame.

Removing the save/restore pairs was measured at **4.4 ms** and is *not* done.
It changes the rendering by up to **64/255 in a channel** on about a hundred
pixels, in a way that is too small to see and that no reading of vis has
explained — and shipping a change to vis's internals that is not understood is
exactly what put the wall of unreadable labels on this page once already. The
measurement is recorded here so the next attempt starts from it rather than
rediscovering it; what it needs is an explanation of those hundred pixels, not
another benchmark.

**Every figure above was measured at a device pixel ratio of 1, and a Mac is
2.** Reported from Safari on a MacBook as lag with caffeine selected, “zoomed
in about halfway so all the text shows up” — the band this section had already
fixed twice. Safari was not available to measure (this machine is Linux, and
WebKitGTK paints with Skia rather than the CoreGraphics Safari uses), so the
nearest thing was measured instead: headless Chrome in software raster at a
MacBook-sized window and DPR 2. It reproduces the report, and the cause was in
this page rather than in Safari.

`lineIsFaint` draws a faint line as a “0.9-pixel hairline”, and the 0.9 was in
CSS pixels. At DPR 2 that is 1.2–1.8 **device** pixels, off Skia's fast path,
which is the whole of what the rule was for: with caffeine selected at 0.6×
the faint bucket alone — 9,062 lines in one stroke — cost **427 ms** of
painting, where every node and name on the canvas cost under 10. The hairline
is now counted in device pixels, reading the ratio off vis's canvas. Thinning
by the ratio halves the ink of the second hop too, the one faint line a
reader follows, so lines at 0.1 opacity or brighter get that ink back as
alpha. That factor is 1 at DPR 1, so nothing changes on a DPR-1 screen.
Composited, the picture moves by a mean of 0.5–0.8 shades, and side by side
the two are indistinguishable by eye; the haze is a little finer on Retina.

*And a gesture no longer redraws the scene at all.* Everything above makes one
frame cheaper; a pan still drew a whole frame per step to move it a few pixels.
`installSceneCache` wraps vis's `_redraw`. While the view alone is moving (not
a node, not a selection box, not physics), the scene is drawn once into a
bitmap a screen larger than the window on every side, and each step draws
that bitmap under the new transform. At rest nothing changes: vis asks for a
redraw of its own when a gesture ends, and it is drawn the ordinary way. The
bitmap is built at the canvas's own resolution: at 1.79 device pixels per CSS
pixel instead of 2, the resampling alone moved the picture by a mean of 6
shades, which reads as text going soft whenever a drag starts. So the margin
shrinks (1 → 0.25 screens) to fit the 16M-pixel cap (iOS's hard limit)
before resolution is allowed to drop. It is built ahead once the view has been
still for 400 ms, so the first step of a pan does not pay for it.

What it rests on is invalidation, and that is checked rather than argued.
`sceneChanged()` is called by both paint paths, vis's DataSet events call it,
and any resting redraw that is not the end of a gesture calls it too, which
covers whatever vis changes on its own (a click selecting a node). Composited
over the background, a gesture frame matches an ordinary frame at the same
view to a mean of **0.02–0.05 shades** after a pan, after a new selection, and
across the label threshold mid-zoom. With invalidation disabled, a stale
selection differs by **15.6**, so the check can fail. A zoom still magnifies
the bitmap, so a pinch is briefly soft until the redraw at its end (a mean of
8 shades at 1.25×), and it is rebuilt past 1.5×.

A real mouse pan, caffeine selected, 1092×854 canvas at DPR 2, software raster,
presented frame intervals:

| | 0.6× | 1× | 2× |
|---|---|---|---|
| before | 300–800 ms | 170–680 ms | ~650 ms |
| device-pixel hairline | 50 ms | 67 ms | 50 ms |
| and the gesture bitmap | **16.7 ms** | **16.7 ms** | **16.7 ms** |

The worst single frame of a pan is 17 ms. A wheel zoom holds 16.7 ms at the
median and p90, with one frame of about 170 ms wherever it crosses the label
threshold or magnifies past 1.5×, because there the scene itself changes. A
resting frame at 0.6× went from 790 ms of JavaScript and painting to 55.

The software-raster drag figures above deserve a warning before anyone re-runs
them. That harness pressed at the centre of the canvas after centring it on
caffeine, which grabs caffeine: **they were a node being dragged, not a pan.**
Both redraw the whole scene, so they are not wrong about what a frame costs.
But a node drag bypasses the gesture bitmap on purpose, so that harness cannot
see this change. The one that replaced it presses on empty canvas and checks
that vis reports a pan.

**Firefox on Linux, thioridazine selected, 2026-10-02: two costs the bitmap
still had.** Reported as "a bit of lag when I drag … zoomed in enough where I
can see all the text and lines". Measured in headless Firefox over WebDriver
BiDi (a real pointer pan on empty canvas, 1180×864 canvas, each redraw timed
with a one-pixel `getImageData` after it, which is honest here because Firefox
paints this canvas on the CPU during the call):

- *A step was a resample at a fractional pixel ratio.* The bitmap was drawn
  under a CSS-pixel transform; at a ratio of 1.5 its device width is rarely
  the destination's exactly, and its offset is rarely whole, so every step
  filtered every pixel of the window: **11.6 ms median, p90 20.6** at 0.6×,
  against 2 at a ratio of 1. A pan is now a copy at whole device pixels
  (`sceneCacheBlit`), with the margin counted in device pixels so that a pan
  of whole device pixels needs no rounding at all: **4.1 ms, p90 7.5**. The
  margin is rounded down, because one sized to the 16M cap and rounded up was
  over it, and there the resolution fell to 1.4999 and the copy was a resample
  again. Against an ordinary frame at the same view, after a pan of whole
  device pixels, a step differs by a mean of **0.02–0.11 shades** at ratios 1,
  1.25, 1.5 and 2.
- *A drag of more than half a window ran off the bitmap* and paid for a
  rebuild in the middle of the gesture: **37–58 ms**, once per half window,
  at 0.6–1×. The margin is now a whole window where the cap allows (at a
  ratio of 1; a Retina window was already held under half by the cap), and
  the same 0.7-window drag never runs off it. The bigger bitmap costs
  **34–61 ms** to draw against 32–49, at 0.4–1×, paid while the view is still.

*And a zoom rebuilt the bitmap with a pan's margin.* Reported next as "zooming
in or out is laggy when all the text is visible". A zoom has to rebuild: every
1.5× in (magnified past sharp) and 0.6× out, which a wheel crosses every four
or five clicks, and with the whole-window margin a rebuild zoomed in cost
**64–122 ms** — the margin is most of it, 128 ms against 50 at 2.5× with a
quarter window. But a zoom needs far less: magnified about a point inside the
window the bitmap still covers it, so zooming in needs no margin, and zooming
out needs a third of the window to last down to 0.6×. Rebuilt with just that
(`sceneCacheZoomMargin`), a 30-click wheel zoom in from 0.5× has its rebuilds
at **28–60 ms**, and out from 1.8× at 32–72. Such a bitmap is marked
`partial`, so the build made once the view is still replaces it with the whole
margin before the next pan. Each step between rebuilds is ~10 ms.

What is left is a rebuild costing about what the crisp frame at that zoom
costs, since the text is drawn at a new size. Two ways of having fewer were
measured and not taken: letting the bitmap be magnified to 2× before rebuilding
nearly doubles how far it strays from the crisp frame (a mean of 11 → 19
shades), and rebuilding at 1.5× the canvas's resolution while zooming in halves
the rebuilds but makes each dearer (61–75 ms), for a total stall of 207 ms
against 268 over the same zoom and a worse worst one.

A resting frame there is 28–33 ms at every zoom from 0.4 to 1, two thirds of
it the ~11,000 background hairlines that cross the middle of the layout;
that is the floor the first Firefox harness found (above), and a pan no
longer pays it.

**Safari itself has not been measured.** `?fps` puts a readout in the corner
giving the median and p90 frame interval of the last gesture, and `?nocache`
turns the bitmap off, so the two can be compared on the Mac itself. Both are
URL flags and change nothing without them.

**Clicking a molecule–target edge opens everything the two of them have
between them, in one panel.** A claim has no panel of its own any more. Each
one is a block inside the pair's panel carrying its tier and route, the rule it
was tiered under where its pill has not already given it, ChEMBL's mechanism
sentence, its counts, its endpoint classes and its individual rows — so reading
a pair is one click rather than a walk through four panels and back. 2,364 of
the 12,835 edges carry more than one claim, so that walk was the usual case; and the
retained observations were not on it at all, being reachable only from the
molecule.

**A click goes to the lit part of the picture first** (2026-10-10, reported
against preladenant). vis picks a node under the pointer, lit or dimmed, and
otherwise the nearest line within ten *canvas* units: any line, the 0.015 haze
as readily as the selection's own, and one or two screen pixels at the zoom
where the canvas fits. Measured in Chrome at that zoom, 0 of 12 points 4 px off
preladenant's lines picked the line aimed at; vis opened a background line or
a dimmed molecule instead. `pickLit` asks the selection and what it touches
first, then the second hop, catching a line within `PICK_EDGE_PX` (8) screen
pixels at every zoom; a lit node under the pointer still wins over a line of
its own step, because the lines end on it. Only when nothing lit is near does
the click go to vis, which with nothing selected is always. After the change 7
of the 12 opened the line aimed at and the other 5 the nearer of two
preladenant lines fanning out from the molecule a few pixels apart, which is
the right answer to where the pointer actually was.

Three groups sit in that panel, ordered, each labelled and none of them summed:
the claims the filters draw as this line, the claims they are holding back, and
the retained ones, which meet neither rule and are part of no line. Sharing a
panel is not being merged — a curated mechanism beside a measured binding claim
is still two kinds of evidence and not two strengths of one (D06), and the pair
is still **one** shared target however many claims sit on it. A pair the filters
have emptied says so and still shows what it is hiding, rather than going blank.

**The claims are grouped under the kind of interaction they assert** (2026-09-25,
at the user's request). The Claims section folds — open by default at first,
because on this panel it is the answer to the click, folded since 2026-10-02
like every section — and inside it each curated action is a
subtitle of its own (Antagonist, Inhibitor, … · curated by ChEMBL), then
**Binding** and **Functional**, each saying "measured, no direction" in its
heading because that is what a reader scanning for a direction needs to know
about a measurement. Within a group the drawn claims come first, then the hidden
ones, then the retained ones, each still carrying its note. The three statuses are
counted apart on the summary row above, so regrouping moves no count. A block does
not repeat the role or action its heading already names (`claimDetail(claim,
headed)`), and each subtitle folds and is remembered like any other section.

Every row anywhere that used to open a claim — the molecule panel's, the target
panel's, the two-molecule pair's, the retained list's — opens the pair that
holds it. Rows that are facts rather than doors say so: a measurement no longer
lights up under the cursor and does nothing when clicked.

**Each claim's rows start folded.** They used to start open when the pair's
own rows numbered thirty or fewer. That was replaced on 2026-09-23 with folded
always, at the user's request: the block already says what the claim is and
how much stands behind it, and the rows are for the reader checking it. The
disclosure states its count, so nothing folded is folded silently.
Acetazolamide at CA2 is 5 blocks and 592 rows, and builds in 0.8 ms.

**A curated claim is offered its references, never measurements.** None of the
210,157 observations in this build is attached to one — a curated claim comes
from ChEMBL's `drug_mechanism` table and from no measurement at all — so the
panel used to hand it a "Measurements" disclosure that opened on "No individual
rows recorded", which reads as an absence in the data rather than as the wrong
question, and a counts table of zeroes beside it. Both are gone. What stands
behind it is ChEMBL's own references, which all 1,485 curated mechanisms here
carry and which this page had never shown anywhere: the papers, patents, FDA
labels and product pages its curators worked from, with their prose where they
left any (453 of the 1,485).

Those are de-duplicated, and that is load-bearing. ChEMBL files the same
mechanism once per form of the molecule, and the forms fold onto one parent
here — caffeine's adenosine-receptor antagonism is curated twice, against the
parent and against a salt, with identical references both times. 163 of the
1,083 curated claims are assembled from more than one record, and **435 of the
2,751 reference rows behind them repeat one already listed on the same claim**.
Listing those twice would show one assertion as two citations, which is the
failure invariant 14 exists to stop, so a reference is listed once and the
number of records behind it is stated rather than being visible only as
duplication.

**A family says which of its proteins are drawn beside it, and each of them
says which family it is inside.** Caffeine has a curated claim at the 4-member
*Adenosine receptor* family and measured claims at ADORA1, ADORA2A, ADORA2B and
ADORA3 — five rows about four proteins, drawn as five lines, with nothing on the
page connecting them. It read as five findings, and it was reported as a bug.
It is not one: a curated family antagonism and four measured affinities are
different assertions, and redistributing the family claim onto its members is
exactly the merge D06 refuses. What was missing was the sentence. The family row
now names the proteins of its own that are listed with it, each of those names
the family, the edge panel lists the family's proteins with a row that opens
each line the molecule actually has at one, and a protein's panel names the
wider targets ChEMBL records it inside. 85 molecules carry one of those
statements, over 97 family rows and 248 protein rows. `singleProteinByAccession`
is how a protein is recognised, and it answers **null** where two targets hold
one accession — two species' records of the same protein, where picking one is
invariant 6's failure.

**And the canvas now says it too** (2026-09-24, at the user's request). A thin
peach line — the family hexagon's own rim colour, which no claim is drawn in —
joins each family, complex group or complex to every one of its own proteins
drawn beside it: **548 lines, joining 221 groups to 374 proteins** at the
default filters. With a molecule selected, a line lights only when both of its
ends are the selection's own targets.

The legacy page's collapse / hull / separate control does not carry over, and
the reason is in the data rather than in taste. It solved *fan-out* — one assay
filed against 26 subunits — across five assemblies that could be made
disjoint. Here a complex is already one node, and **105 of the proteins drawn
sit inside two or more drawn groups** (248 pairs of groups partially overlap,
mostly GABA-A subtype complexes sharing subunits inside a 16-member complex
group), so a node would have to be in two hulls or two collapsed nodes at once.
The legacy rule, keep the largest, would fold α1β2γ2 and α5β3γ2 into one blob.
Collapsing a family would also join istradefylline to the same node as caffeine,
which is D06's merge drawn rather than stored.

The lines are **not edges**, and nothing that reads `edges` sees them: they sit
on `catalogueGraph().links`, and no count, banner, hop, similarity score, panel
list or line-colour legend reads that list. The second hop never travels along
one — otherwise selecting caffeine would light every PDE through the PDE family.
They are springs as well as ink (`GROUP_LINK_LENGTH`, shorter than a claim's),
which is why the control is in the graph signature.

**An ion-channel assembly is laid out as one unit** (2026-09-25, at the user's
request). A GABA-A, nicotinic, NMDA, AMPA, kainate, 5-HT3, glycine, Cav or KCNQ
receptor's subunits never work apart, and the canvas drew GABRA1 at one end and
the α1β2γ2 receptor at the other. Each such assembly — its complex and complex-
group records and their drawn subunits, joined wherever they share a subunit —
is now packed into one disc in the target colour, as smaller nodes, with every
molecule's line still landing on the exact record its claim is at. **24 units
over 140 nodes** at the default filters; the human GABA-A disc is 27 nodes,
seven subunits and twenty receptor records. Lines between two nodes of one unit
are not drawn (the disc says it); a family's line into one is.

*Which* complexes is the user's decision, and it is ion channels only. ChEMBL's
PROTEIN COMPLEX also covers the JAK kinase pairs, the mu-opioid/α2A
heteromer, RXR/PPARγ and factor VII/tissue factor, whose parts work alone —
one unit there would fuse OPRM1 into a blob with ADRA2A. So `channelAssembly`
reads `protein_class`: every component an ion channel or an ion channel's
auxiliary subunit, at least one the channel itself. That is 87 of the 152
complex records drawn. One rat L-type record is missed because ChEMBL leaves
its Cacnb1 unclassified, and the rule does not guess. The classification says
what kind of complex a record is and never which records belong together — the
accession still does that — which is how it stays clear of the warning above
about ChEMBL's classification tree.

The physics never sees a unit's nodes. vis has no rigid bodies, and a spring
strong enough to hold 27 nodes together would decide the rest of the layout, so
each unit is one hidden anchor, sized and weighted for its disc, and every line
touching the unit is felt as one hidden spring from its other end to the anchor
(one per neighbour, the way the ranking counts one shared target). The real
lines are drawn and carry no spring. When the solve settles, `unitPlacement`
packs each unit on a sunflower spiral round its anchor — complex groups in the
middle, subunits on the rim where the lines arrive — then **guarantees** the
disc holds only its own nodes: discs are separated largest first, and any other
node inside one is moved to just past its rim. Sizing the anchors alone left 148
unrelated nodes inside discs and 2 discs overlapping; the pass leaves 0 and 0,
measured in Chrome across two fresh layouts and after two filter changes. Every
move is glided by the transition that follows. Dragging any node of a unit
moves the whole unit by the pointer's travel — read from the pointer, because
vis emits `dragging` before it moves the node and a node read there is one step
behind. `getPositions()` without arguments leaves hidden nodes out, which is why
`nodePositions` asks for the anchors by name; without that nothing was packed.

Nothing counted changes: the same edges, hops, panels and similarity scores
with units on or off (top-1 38.2%, MRR 0.5105 either way).

**Selecting a complex lights its own subunits** (2026-09-25, at the user's
request), wherever they are drawn, so what a receptor is made of can be read off
the canvas without opening its Components list. They are lit and not treated as
the selection's targets: their own molecules and lines stay dark. Complexes and
complex groups only; a family's members are separate proteins, not its parts. "Protein groups:
draw separately" turns units and lines off together.

**A band round the selection's groups was shipped and taken off again**
(version 12, removed 2026-09-25 at the user's request: "adding too much to an
already quite busy view"). It is worth knowing it was tried in two shapes. A
convex hull round diazepam's GABA-A groups took in half the canvas, because each
subunit is pulled toward its own dozens of molecules; a band along the lit lines
fixed that but was long wherever the lines were.

**A family overlap that repeats proteins already shared is counted once.**
Caffeine and theophylline share ADORA1, A2A, A2B and A3 and both have the
curated family claim over those same four proteins, so the pair read **6 shared
targets** for five proteins plus a claim about four of them — the picture and
the number disagreeing, one level up from the legacy page's protein assemblies.
A family or complex-group overlap whose every protein the pair already shares
individually now adds nothing to the score and is not a second shared target;
caffeine/theophylline is 18 shared at 0.246. Only a *complete* repeat is subsumed —
lidocaine's sodium-channel family covers ten proteins where two are shared, and
the other eight are something the pair shares nowhere else, so it keeps its half
weight. A `PROTEIN COMPLEX` is never subsumed: it is one physical assembly
rather than a set, which is why it already weighs what a single protein weighs.
Nothing is dropped — the claim stays on the pair, listed last, saying what it
is. 98 of the 19,362 ranked rows change, and 10 of 769 molecules get a different
top neighbour.

**An opposite is not a likeness** (decision D15). Caffeine and adenosine share
ADORA1, A2A, A2B and A3, and adenosine sat *second* in caffeine's ranking at
3.60 — behind theophylline's 4.50 and ahead of everything else — while ChEMBL
curates caffeine an ANTAGONIST and adenosine an AGONIST at the family covering
exactly those four receptors. The score said near-twin about a pair of
opposites, which on a page for finding molecules that act alike is the one
error that states the reverse of the truth rather than ranking noisily.

What it is *not* is a direction taxonomy. `OPPOSED_ACTIONS` lists the ChEMBL
actions that are each other's opposite and `directionAt` gives three answers —
opposite, not opposite, and **null** where either side has no curated direction,
which is 6,239 of the 12,964 overlaps. Folding the 23 actions into agonist-like
and antagonist-like families is the merge the mechanism control refuses (D06),
and the measurement says why it would be wrong here too: 1,723 overlaps carry
two *different* curated actions and only **508 are opposites**. The rest are the
same direction said twice (320 positive allosteric modulator against positive
modulator), a matter of degree (306 involving a partial agonist), or the same
net effect by another route (193 inhibitor against releasing agent, which at a
transporter both raise what is outside the cell). Reading "different" as
"disagrees" would demote three pairs that agree for every one that does not.

The factor **only ever goes down**: a pair whose every known direction is
opposite scores at a quarter, and agreement is never a bonus. Rewarding a
curated match would demote every pair ChEMBL has not got round to curating,
turning its silence into a negative result — what the mechanism banner's two
separate costs already exist to prevent. `OPPOSED_PAIR_FACTOR` is 0.25 rather
than 0 because the two molecules do share the target and that is a fact; what it
must not read as is "these two act alike", which is the only claim the score
makes. Nothing is dropped anywhere.

**The demotion is proportional, over the proteins the pair can be compared at.**
A pair opposed at one of two comparable proteins is multiplied by 0.625 —
half the distance to the quarter — and its row says so. It used to keep its
score untouched, which put half-opposed and not-opposed at the identical number
and made the one signal this rule carries an all-or-nothing cliff. An
entirely-opposed pair is unchanged at a quarter, so this reaches only the pairs
the old rule declined to touch: 42 of them here, 84 ranked rows, and **4 of 988
molecules get a different top neighbour**. Nalbuphine drops the pure antagonist
samidorphan for butorphanol, its own mixed agonist–antagonist class, and
nalmefene drops the partial agonist buprenorphine for samidorphan. The grade
goes from top-1 37.8% / MRR 0.5083 to **38.2% / 0.5105**.

The cost it appeared to carry turned out to be an entry on `OPPOSED_ACTIONS`
rather than the factor, and chasing it removed one. Haloperidol and aripiprazole
dropped from rank 4 to 29 because ChEMBL curates haloperidol an INVERSE AGONIST
at the D2-like family and aripiprazole a PARTIAL AGONIST at D2 — and that entry
is gone, so they are back at rank 4. See **the efficacy axis** below.

**The denominator is `comparable` and never `n_shared`**, which is the
load-bearing half of that decision. A shared target where ChEMBL curates no
direction is an *unknown*, not an agreement, so dividing by everything shared
would let silence dilute a demotion: clozapine and apomorphine share 34 targets
and are comparable at one, and a shared-denominator rule would score them as
near-identical on the strength of 33 proteins nobody has said anything about.
That converts "ChEMBL has not got round to this" into a defence, which is the
mirror image of the failure the paragraph above refuses — and it grades below
the rule it would replace (MRR 0.5065 against 0.5083).

The worry that prompted the question — that demoting on one comparable protein
out of 34 shared is too thin — was measured against the answer key rather than
argued. Of the 876 entirely-opposed pairs, **exactly one** is a same-ATC-class
pair, and of the 167 demoted on a single comparable protein while sharing ten or
more targets, **none** are. The one exception is betahistine and cinnarizine, an
H1 agonist against an H1 antagonist: same clinical class, opposite mechanism,
and the key being a proxy rather than this rule misfiring. The thin comparisons
land on the protein that carries the mechanism, and the shared targets around
them are the screening history the prevalence discount exists for.

Direction is read at **every** shared target, the subsumed ones included, and
that is the whole of why it works. The only row that knows caffeine and
adenosine point opposite ways is the family claim — precisely the row the
subsumption rule above zeroes — and the four protein rows carrying that pair's
entire 3.60 carry no curated direction at all. A factor applied per scored row
would have found nothing on the one pair that most needed it.

**And it is read at the protein, not at the target record it is filed against.**
The paragraph above used to end by naming its own limit — adenosine and
istradefylline are real opposites and were not demoted, because one's curated
direction is at the family and the other's at the single protein, so they never
met at one row. That was recorded as "a floor, not a census", and the census is
what `pooledDirection` now takes. A curated action is attributed to every
protein the target it is filed against covers — a SINGLE PROTEIN contributes its
own accession, a family or complex group all of its components' — and two
molecules are compared at each protein their shared targets cover. Istradefylline
is now demoted, and so is the case that prompted it: **morphine's nearest
neighbour of 380 was naltrexone**, the drug given to reverse it, over twelve
shared rows on which `directionAt` returned null every time. Morphine is curated
AGONIST at human mu-opioid and naltrexone ANTAGONIST at the human mu/kappa/delta
family — one row apart, never compared, and the family row carrying naltrexone's
half is *subsumed*, so it contributed 0 to the score while being the only row
that knew. Morphine now ranks naltrexone 17th and opens on buprenorphine.

This is **not** the D06 merge and must not be described as one. Nothing in it
changes what a shared target is, what it weighs, which rows are subsumed, or
what the canvas draws; no claim is moved from a set onto its members. It changes
exactly one thing: which two actions get compared. That is the same argument the
paragraph above already makes for reading direction at subsumed rows — the row
carrying the direction is usually not the row carrying the score.

It matches on the **accession** and never on a gene symbol, and that was
measured rather than assumed. The prototype in
`analysis/probe/direction_recovery.mjs` pooled on the symbol so that OPRK1 and
Oprk1 would meet; against this build the two keys recover **the same 535
entirely-opposed pairs**, the symbol reaching 56 more comparable pairs and
demoting not one of them further. An identifier that costs nothing measurable is
not worth trading for a name (invariant 6), so the orthologue duplicates stay a
separate problem. The script is kept, and now reports that gap rather than a
prototype's gain.

**The pair panel names the oppositions no block on it can show.** Reading
direction at the protein means the two halves are usually on two different
records, and often only one of them — or neither — is a row the pair shares, so
every block in morphine's panel would print two claims with no sentence relating
them under a line announcing the score had been quartered. A page that asserts a
demotion and shows nothing explaining it is the shape this project keeps trying
not to have. Each such protein is named above the blocks with both directions
and the record each is curated at; proteins with the same two directions from
the same two records are one line naming all of them, so the adenosine-receptor
case does not print the identical sentence four times. A protein whose
opposition *is* readable from one shared block — caffeine and adenosine, both
directions on the one family row — is left to that block, because saying it
again above is one fact under two headings (invariant 13). The counts in the
sentence are in **proteins** and say so, for the same reason: the row it is
printed on carries the shared-*target* count a few characters earlier.

Measured across the catalogue at the default filters: rows with a comparable
direction go from 12,328 to 15,416 of 227,298, and **490 demoted pairs become
876** of 113,649 — 389 gained and **3 released**. The three are as much the
argument as the 389: trimipramine and tolazoline are both ANTAGONIST at three
adrenoceptors and opposed at one, which the one-record view could not see, so a
pair that agrees three times out of four was being quartered. **7 of 988
molecules get a different top neighbour**, and they read correctly without being
told to: morphine and oxycodone drop naltrexone for buprenorphine, buprenorphine
drops naloxone for oxymorphone, nalbuphine drops aticaprant for samidorphan, and
remoxipride drops the D2 *agonist* pramipexole for tiapride. The ATC grade moves
from top-1 37.5% / MRR 0.5035 to **37.8% / 0.5083** — small, and not the reason
to do it: an opposite ranked as a likeness is the one error this page cannot
afford whatever a proxy says about it.

**The efficacy axis is treated alike, whichever word ChEMBL used.** Efficacy is
a signed continuum — full agonist, partial agonist, zero for a neutral
antagonist, negative for an inverse agonist — so a partial agonist and an
inverse agonist really do sit either side of neutral, and that pair was on
`OPPOSED_ACTIONS` for exactly that reason. It came off, and the pharmacology is
on the losing side of the argument, which is why it is written down.

ChEMBL does not use the label systematically. The whole catalogue carries **four
INVERSE AGONIST claims** — haloperidol and its own decanoate at the D2-like
dopamine receptor, pitolisant at H3, pimavanserin at 5-HT2A — against **260
ANTAGONIST** and 25 PARTIAL AGONIST. At DRD2, 41 molecules are curated
ANTAGONIST and 2 INVERSE AGONIST; at HTR2A it is 41 against 1. Most
antipsychotics have inverse agonist activity at D2 and ChEMBL says so for one of
them. So the entry encoded a curator's word rather than a difference: against
aripiprazole, a D2 partial agonist, it demoted haloperidol to rank 29 while
chlorpromazine sat at 13, risperidone at 3 and fluphenazine at 40 — four D2
blockers in one relationship to one partial agonist, one of them penalised for
vocabulary.

The parallel case was already decided the other way, and that is what settles
it. PARTIAL AGONIST against ANTAGONIST is a matter of degree and deliberately
not opposed, which is **242 pairs** here; PARTIAL AGONIST against INVERSE
AGONIST is the same axis one notch further and was **10 pairs, every one of them
haloperidol's or its decanoate's**. Treating the axis alike is the only
consistent position available, and doing it the other way means demoting those
242 — which the 508-of-1,723 measurement above argues against. The grade is
identical either way (top-1 38.2%, MRR 0.5105), so nothing was traded for it.

It is a judgement about ChEMBL's curation and not about receptors, so it is
worth revisiting under a source that curates efficacy systematically — which is
what GtoPdb is proposed for in
[docs/NEXT-STEPS-PROPOSAL.md](NEXT-STEPS-PROPOSAL.md) §1b. Pimavanserin is
marketed as a 5-HT2A inverse agonist, and if a 5-HT2A partial agonist ever
enters this catalogue the opposition would be real.

**A row says a thing once.** The tier pill says how well evidenced a claim is
*and by which route* — "Supported · curated" is ChEMBL having curated the
mechanism, "Supported · multiple studies" is replication. The line under it said
the claim's role, which for a curated claim is the same word again: the target
panel drew a green "Supported · curated" with "curated" underneath it, which is
one fact wearing two labels and reads as two (invariant 13). A row whose pill
has already said "curated" now leads with what the pill cannot say — the
direction ChEMBL curated, which at the *Adenosine receptor* family is ANTAGONIST
for caffeine and theophylline and AGONIST for adenosine. A measured row is
untouched: "binding" beside "Supported · multiple studies" is two different
facts. A curated claim that did not reach Supported still names its role, because
there the pill says "Preliminary" and nothing else has said what kind of claim it
is. `claimDetail` is that line, written once, so the molecule panel and the
target panel cannot describe one claim in two vocabularies.

**No panel is a dead end.** The claim panel named a molecule and a target in its
heading as plain text, with no links out and nothing to open, so the question a
measurement most provokes — what is this protein, what else acts on it — had no
answer in the panel that raised it. Every panel about a molecule *and* a target
now ends with both of them as rows and links both out, a pair the filters hid
offers its ends rather than only its absence, and the retained-observations
panel goes back to the molecule it came from. The other half of that problem is
gone rather than fixed: there is no claim panel any more, so a claim cannot be
opened away from its siblings in the first place.

**A rule is named, not spelled.** The retained-observations panel grouped its
rows by the build's own `tier_reason` token and used it as the heading —
*invalid_units_only (1)*, which explains the rule to a reader who already knows
it and to nobody else. All 14 reasons the build can write now carry a label and
an explanation: that one is **No resolvable value**, covering the three ways
ChEMBL reaches it — no exact `=` relation, no value at all, or units that do not
convert to a concentration — with the rows kept because the experiment happened
and counted into nothing because there is no number to count. The token is named
*inside* the explanation rather than printed beside the label, since one fact
wearing two headings is invariant 13, and it stays visible because it is what the
database stores and the thing to grep for. "Why this tier" on a claim block
reads the same map, and prints nothing where the tier pill has already given
the rule — "Supported · multiple studies" over "Replicated across publications"
is one fact under two labels. A reason this page has never seen falls back to the token
rather than to silence — the failure `helpLabel` had with the edge panel's
"Claims" — and a test scans `scripts/cohort/evidence.py` for every reason it
assigns and holds the map to that list.

**The pair is the unit, and the arithmetic that missed it is worth keeping.**
TOZADENANT has one functional row at ADORA2B with no relation and no value, and
three exact Ki measurements at that same protein. The retained list showed the
first, said "1 row", and gave no sign the second existed; the panel it opened
offered no way through, because it counted the pair's other claims as
`edge.claims.length - 1` — one minus one, when the claim being looked at is not
on that edge. A retained claim never is: it lives in the molecule's evidence
shard rather than in the catalogue, *because* it backs no line, so subtracting
it from a list it was never in is the arithmetic of a claim that exists in two
places and is counted in one. Reading a claim in a panel of its own is what made
that possible, and the fix in the end was to stop: every claim is read inside
the panel about its pair, where nothing has to be counted around it. What
survives from the first attempt is the row in the molecule-wide retained list,
which still names the claims drawn beside it before opening the pair, and
`claimDetail` saying what a claim with no comparable value is made of — "1 row
with no resolvable value", "3 bounds, no exact value" — rather than only its
role and its target type.

**Seven controls, each independent and each stating its own cost — inside the
control that causes it.** The whole argument for a control that removes things
is still that it says what it removed, and every number below is still counted
from the loaded data. What changed is where it is printed. The costs used to be
a strip across the window, on the reasoning that a cost behind a disclosure is
not being stated; at the defaults that strip was two paragraphs of prose and
with a couple of filters on it was five, taking the top of the graph to explain
the graph. It also put each statement nowhere near the buttons it was about. Each
one now sits under its own control, where a reader is already deciding whether
to remove something, and the button carries only the *number* of controls
with a cost ("Display options · 1 hiding") so that there is one is visible
without opening anything. The full list of settings is the button's hover
tooltip; it used to be printed on the button itself, and in a narrow window it
squeezed the search box to a sliver (removed 2026-09-24, at the user's request).

**A cost and an inclusion are counted apart**, which the open tier and basis
defaults made necessary. Both of those push a banner at rest — a reader looking
at Preliminary claims and at nonhuman assignments has to be told so — but
neither is a cost, because nothing is hidden. Counted together, the resting page
read "2 stating a cost" while hiding nothing at all, which is two quantities
under one label (invariant 13). A banner now carries a `kind`, the summary
counts only the `cost` ones, and what is being *included* is already in the
summary's own settings list in words. Four controls decide which claims are
eligible; three decide only what is drawn, and say which they are:

- **Evidence tier** — Supported and Preliminary by default, narrowable to
  Supported alone. Curated and multiple-study support are drawn and labelled
  differently; they are two different claims, not two strengths of one, and a
  Preliminary claim — exactly one identifiable study — carries its own pill on
  every row. The default is open because the strict one left the median entry
  with a single target and the ranking with nothing to rank on; the banner
  states which setting is in force either way, so an included Preliminary claim
  is never mistaken for a settled one.
- **Assignment basis** — both layers by default, narrowable to direct human
  alone. The broader layer holds nonhuman, homologous, variant and ambiguous
  assignments, labelled as such on every row. The layers are scored separately
  and never pooled, so including the broader one cannot raise a direct-human
  score. Narrowed, the banner names the 38 entries whose *only* evidence is in
  that layer and says which control reveals them.
- **Potency** — no cutoff by default, with 1/10/100/300 µM presets. It is a
  display filter and removes nothing from the catalogue or from search. A
  curated claim, a bounds-only claim and a conditional conversion have no
  comparable value, and the banner reports them as hidden *for want of one*
  rather than as having failed.
- **Curated mechanism** — every claim by default, or **any number** of exact
  ChEMBL actions at once. It is ChEMBL's curated direction, and the only
  directional statement in this database: a measured affinity says how tightly a
  molecule binds a target and never which way it acts on it. 1,083 of the 12,835
  default edges carry one, across **24 distinct actions**, and the control offers
  all 24 at ChEMBL's own granularity rather than folded into direction families
  — a positive allosteric modulator is not an agonist and an inhibitor is not an
  antagonist, and grouping them would assert exactly the merges D06 refuses at
  the targets. They **compose** rather than replacing one another, which is the
  other half of that argument: the question a reader actually has is usually
  about a group of related directions, and a control that offered one at a time
  would push them toward the families it declines to define. Antagonist, inverse
  agonist and negative allosteric modulator together are 193 molecules, 71
  targets and 269 edges; agonist with partial agonist is 195 / 86 / 231.
  Unpicking every action is every claim again, not an empty canvas. Each toggle
  carries what it would draw, counted under the other three eligibility
  controls: inhibitor 347, antagonist 260, agonist 206, blocker 63, positive
  allosteric modulator 45. It is an eligibility filter, so the canvas, the panel
  lists, the similarity ranking and the gap statements move together — antagonist
  alone is 186 molecules, 71 targets and 260 edges, and takes caffeine's 265
  shared-target rows to 1. A picked action the other controls have emptied stays
  on the control, showing "(0)", rather than disappearing while still filtering.
  Its banner counts **two costs apart**: claims annotated with a different
  action, and claims annotated with none at all. Those are different statements,
  and reporting them as one number would turn ChEMBL's silence into a negative
  result.
- **Canvas** — every target drawn by default, or single-molecule targets
  hidden. One of the two controls here that change what is *drawn* rather than
  which claims are eligible, and the only one that can take something off the
  picture without taking it out of the catalogue. Its cost is above.
- **Line colour** — the curated mechanism by default (since 2026-09-24, at the
  user's request), or what backs the claim. The second drawing-only control: the same edges are on the canvas either way
  and it moves nothing in or out, which is why it is deliberately not in the
  graph signature — a repaint must not cost a rebuild or move the layout. The
  dashes carry the evidence in **both** modes, so nothing the colour stops
  saying goes unsaid. The palette is the legacy page's, extended: where that map
  shares a colour between INHIBITOR and BLOCKER, or between the positive and
  negative allosteric modulators, this one does not, because those are different
  assertions and one of those pairs is a pair of opposites. 13 actions have a
  colour, the other 11 draw as *other curated action*, and the 11,752 edges with
  no annotation draw in a recessive colour of their own that is named on the legend
  as **no curated mechanism** — ChEMBL not having curated one, never a finding
  about the molecule. The banner says how much of the canvas the colour cannot
  speak for; that banner is an inclusion and not a cost, since the colour
  hides nothing, so the resting summary still reports no cost. The legend's colour block is read **off the canvas rather than off
  the palette** in this mode: one row per colour actually drawn, with a count,
  so a new `action_type` arriving in the data cannot draw in a colour nothing
  names — which is the failure the legacy page had twice.
- **Protein groups** — linked by default, or drawn separately. The third
  drawing-only control: it adds or removes the membership lines and the
  ion-channel units described above, and changes no claim, count or score.
  Unlike line colour it *is* in the graph signature, because the lines are
  springs. It states no cost, because it hides nothing.

**A selection is drawn bold, and repaints nothing that was already saying
something.** vis writes a selected edge's colour from `color.highlight` and a
selected node's fill from `color.highlight.background`, and at the defaults both
are its own: every line into the clicked molecule turned white, and a clicked
target stopped being orange. That takes the two channels this canvas works
hardest — the line colour, which says what backs the claim or which direction
ChEMBL curated, and the node fill, which says molecule or target — off the
picture at the exact moment a reader is looking at them, and in a colour the
legend names nowhere. It is the failure the legacy page had twice with action
colours, arriving through the selection rather than through the data. So an
edge's highlight colour is its own colour and a node's highlight fill is its own
fill, `selectionWidth` is stated at 2 so a selected line reads bold rather than
repainted (Supported 2→4, Preliminary 1→3), and `borderWidthSelected` is held at
or above the node's own rim so selecting a molecule cannot thin the 3px rim that
says it has a Supported claim. The dashes vis never touched go on carrying the
evidence throughout.

**Both popovers in the top bar can be dismissed without being used.** The search
results and the display options had no way out but to pick something: clicking a
result left the list sitting over the molecule it had just selected, and the
graph — the obvious place to click to mean "not this" — was behind both of them.
A click that lands outside either one closes it, Escape closes both, and picking
a result closes the list. The search text is kept rather than thrown away, so
clicking back into the box offers the same answers again; `searchOpen` is
separate state from the query precisely because every `refresh()` re-renders the
results from the query, and a dismissed popover that a filter change puts back
is not dismissed. The handler is bound on `document` in the **capture** phase,
which is load-bearing: `onFilterClick` re-renders the control it was called on,
so a handler running on the way back up would find that button detached from the
DOM, read it as a click outside `#view-options`, and close the popover on every
filter change. `closeSearch` hides rather than empties for the mirror-image
reason — emptying inside the click would detach the row before the handler that
reads its `data-select` ever saw it. **About**, the third, closes the same way
(`closeDetails`), and Escape dismisses it before it would clear the selection.

**The canvas counts what the filters keep, against the whole catalogue**
(2026-10-13, at the user's request). A box at the top left of the canvas reads
*Filters keep 1,834 of 2,452 molecules and 2,454 of 2,758 targets* at the
defaults (built 2026-10-12), and with *Hide single-molecule targets* on adds a
second line, *Drawn: 1,767 molecules and 1,487 targets*. Two rules shape it:

- **"Kept" is the claim filters' answer and "drawn" the canvas control's**, read
  in `catalogueGraph` before and after the periphery is pruned, so turning the
  canvas control on never moves the first line — the same line between "in the
  picture" and "drawn" that the periphery section above holds.
- **Targets are counted in canvas nodes, both totals and kept.** A protein in
  four species is one node (D20), so the catalogue's 3,359 ChEMBL target records
  are 2,758 targets here (`catalogueTotals`). Counting records beside a canvas
  of proteins would have given a "kept" figure no reader could check against
  the picture. The Display options line, which already said "3,359 targets",
  now says "ChEMBL target records", and the box's tooltip names both figures:
  two numbers both labelled "targets" are what invariant 13 forbids. At
  Supported and direct human only the box reads 1,497 molecules, which is the
  Status block's "1,497 entries have a Supported claim" by another route.

**A filter change says it is working before it starts.** At the open defaults
a filter change rewrites ~4,300 nodes and ~19,000 edges into vis and re-solves
them, all on the main thread: 8.4–8.9 s in headless Chrome, of which the page's
own recompute (claims, controls, panel) is about 120 ms in the vm harness. Run straight from the
click, none of it left the browser a frame, so not even the pressed button
showed until it was over. `refreshAfterFilters` now repaints the controls and
puts *Applying the filters…* with a spinner in the counts box, and runs the
rebuild from a timeout queued inside a `requestAnimationFrame` callback: the
browser paints straight after those callbacks, so that frame is on screen
before the work starts and stays there while the main thread is held. A
re-solve then says *Laying out the network… 50%* from vis's
`stabilizationProgress`, wherever the browser gets a frame between batches, and
the line clears in `settleGraph`, or straight after the rebuild where nothing
was re-solved (line colour). Clicks while one is queued fold into it, and a
layout settling meanwhile leaves the queued change's line up. Reset goes the
same way.

The line is in the counts box rather than in `#load-status`, which was the
first place it went: that is centred on the canvas, and Display options — open
whenever a filter is clicked — sits over the middle of the canvas at z-index 50
against its 30. The first screenshot of the change showed nothing.

**The solver's batch size was tried and left alone.** The browser paints only
between vis's batches (`updateInterval`, 100 ticks for a re-solve, about 4 s
each in headless Chrome), so 10 looked like the way to a live progress line,
and it made the re-solve 4.6× faster — because the solve stopped after 40 ticks
instead of 200. With the `SETTLE_MS` backstop pushed out to a minute, the same
10-tick batches ran all 200 ticks and the progress line counted up in 5% steps;
at 100 the solve ran all 200 in each of three runs with the backstop as it is.
So the backstop, which exists for a solve that never reports back, cut short
one that was reporting, and the batch size stays at 100. Left open: whether it
also cuts a 100-tick re-solve short on a machine where a batch finishes inside
a second — unmeasured. Re-arming it on each `stabilizationProgress` would keep
it a backstop and allow short batches; that changes how far every re-solve
runs, and was not done here. (Settled positions could not be compared: two
identical runs with `Math.random` seeded alike differed by a mean of 1,873
canvas units, so a position difference is not evidence of anything here.)

**The page says what it is not, permanently, and credits its sources in one
place** (2026-10-09, at the user's request, before hosting it on a server;
[HOSTING-REVIEW.md](HOSTING-REVIEW.md)). "Exploratory and educational, not
medical advice" was in `NOTICE` and nowhere a visitor saw it, while the panels
say "Approved for…", give trial statuses, and rank **Closest target profiles** —
which a visitor reads as "this drug can replace that one", the claim the Goal
section of `CLAUDE.md` takes most care not to make. So a one-line strip runs
along the bottom of `#app`, a sibling of `#main` rather than inside a panel or
popover, where folding the sidebar or a section cannot hide it; and **About**,
beside Display options, says what the page is, what "similar" does and does not
mean, that approval and trial statuses are as recorded at build time, and the
known limitations. Its limitation on the grade says "well under half the time"
rather than quoting 38.7%, because a figure in static markup is the kind that
goes stale ([the Status rule](../CLAUDE.md)).

The sources and their licences were a sentence at the foot of Display options,
naming ChEMBL and GtoPdb only. They are now About's alone — six sources, each
with its terms — and the catalogue line keeps its counts and points there,
because the same credit in two places is two things to keep in step. The list
is built by `aboutSourcesHTML` rather than written into the markup for one
reason: GtoPdb is credited only when `gtopdb.data.js` was merged, at the release
that file carries. A page without the file, or with one from another export, is
the ChEMBL-only page, and a credit hard-coded beside it would attribute data the
page is not showing.

**A shard that arrives late belongs to the selection that asked for it.**
`loadEvidence` injects a `<script>` tag, so a reader can select a second thing
before the first one's measurements land. The guard against that read
`getSelection()` on both sides of its own comparison — and since `getSelection`
returns the one live selection object, which `setSelection` mutates in place, it
was true by construction. A shard for molecule A painted its rows into whichever
panel was open when it arrived. Two claims on one molecule hid it, because both
callbacks fire from a single `registerEvidence` in push order and the newer
selection's wins; it showed across two molecules, which is the case slow enough
to click through. The selection is now read into primitives before the shard is
asked for, and the callback checks those — **three** of them for a pair, because
a pair is identified by both of its ends and caffeine and theophylline can be
open at the same protein one after the other. The pair panel is then rendered
again rather than patched, since every block on it reads the shard: for its
rows, and for whether it exists at all.

**The target panel counts molecules, not claims.** Its heading read
"Molecules (N)" with N the number of *claims* at that target, while the same
molecule appeared twice in the list below it — invariant 13, two quantities
labelled so they invite comparison. A molecule with both a curated mechanism and
a measured binding claim at one target is one molecule, which is the same thing
the edge panel already says about the 389 edges carrying more than one claim.
The heading counts distinct molecules, the claim count is stated beside it when
the two differ, and a molecule's claims are listed together so a repeated name
reads as one molecule with two claims rather than as two entries. Both rows stay
separately clickable: they are two kinds of evidence, not two strengths of one.

**The list is ordered by kind of evidence, then potency, and is never cut off**
(2026-09-24). It used to be ordered by the most publications behind any one
claim and stopped at 60 molecules. A curated mechanism counts 0 publications,
because it rests on references rather than measurement studies, so curated-only
drugs sank to the bottom and were cut: **22 of the 41 drugs ChEMBL curates at
DRD2** were unreachable, paliperidone, lurasidone and cabergoline among them, and
130 across 18 targets. Now direct human comes before the broader layer, and within
each a molecule with both a curated mechanism and replicated measurements leads,
then curated only, then replicated only, then Preliminary, strongest median first
within each. Curated-only is above replicated-only *here* because this list answers
"what acts at this target" and a curated mechanism says the target is how the drug
works; it is an ordering of kinds and not a ranking of strength, and the similarity
score weights it the other way (0.75 against 0.9).

**A target's claims are grouped the way a molecule's are** (2026-09-26, at the
user's request). The single Molecules heading is gone: a line under the identity
table counts the molecules (and the claims, where those differ), and below it
the molecule panel's own "Group claims by" toggle splits the list into Supported
/ Preliminary, or into one section per curated action and then Binding and
Functional. It is the same state as the molecule panel's, so switching it on one
switches it on both, and both panels group through one function (`claimGroups`),
so a claim cannot be filed two ways. Inside a section the order above holds and
a molecule's claims stay together; a section that holds a molecule twice says
how many molecules it is beside its claim count. The sections fold under their
own keys (`target_claims_…`), so folding Supported on a target does not fold it
on a molecule. DRD2 reads Antagonist (31), Partial agonist (5), Agonist (2),
Modulator (2), Inhibitor (1), then Binding (181) and Functional (26); hERG has no
curated section at all, which is the point of it.

**The panels' prose was cut to a line where a line would do** (2026-09-24, at the
user's request). A ranked neighbour's row says its compressions and demotions as
tags ("+2 family repeats", "opposite actions, score ×¼") with the sentence on
hover and in the pair panel, rather than spelling each one out on hundreds of
rows. The prevalence, family, wider-target, retained and banner notes are one
clause each, and a trial shows one main goal, its title cut at 60 characters
with the rest on hover, and its first p-value with the others counted.

**The legend is small, and folds to one button** (2026-09-25, at the user's
request: the graph's visible area was too small). 11px text, labels cut to a few
words ("ion channel" needs no gloss), the mechanism colours in two columns, and
"Node rim" and "Line style" merged into one **Evidence** block, because they say
the same kind of thing at two scales: a line is solid when *that* claim is
Supported, a molecule's rim is bright when *any* of its claims is, counted over
the whole catalogue and not moved by the filters. It went from about 614px tall
to 377, and folded it is 70×24; the fold is remembered in the browser where it
can be.

The legend **no longer spends three rows explaining the opacity**. It is pinned
over the graph it explains and every row it holds is graph it is covering;
bright-means-selected is the one thing on this page nobody has to be told. The
three steps and the single place that writes them are unchanged, and a test
holds that ordering rather than the rows.

**Each mechanism row explains itself on hover** (2026-10-09, at the user's
request). The text is ChEMBL's own definition from its `action_type` table in
plain words — GtoPdb's actions are mapped onto the same words, so one gloss
serves both curators — with an example this catalogue curates (caffeine at
adenosine receptors, ezogabine at KCNQ channels), so the reader can click the
drug and find the line. "Other curated action" names the actions it holds on
the current canvas, and "no curated mechanism" says it is not a sign of no
effect, the same caution the banner gives. The box sits **beside** the legend,
on `#graph-wrap`, rather than as a `.help` box inside it: the legend scrolls,
and a box inside it is clipped by that scrolling. A test reads the palette's
keys from the source and fails for a colour added without an explanation.

**A structure class links its Wikipedia article by the article's title**
("Wikipedia: Xanthine"), not as a bare "Wikipedia": on the category route the
article is usually the parent compound's, and the link should say so. A class
no identifier reached has no link rather than a guessed one
([DATA-QUALITY-LOG](DATA-QUALITY-LOG.md), 2026-10-09).

**Every heading that offers an explanation has one.** `helpLabel` falls back to
plain text for a key the `HELP` map does not hold, so a heading meant to explain
itself simply stops doing it — silently, and indistinguishably from one that was
never given an explanation at all. "Claims" on the edge panel had been in that
state since it was written. A test now scans the page for every `helpLabel` call
and asserts the map answers each of its keys, and the map has grown from 10
entries to 35: a claim block's own vocabulary (role, why this tier, curated
action, counts, endpoint classes, measurements, references, unresolved rows,
conflict), the two new controls, and every field on the molecule and target
panels that names something a reader would have to already know — category,
formula, ATC, ATC annotation, flags, seed, exclusion reason, organism,
components. (36 until `indication scope` went with the row it explained, below.) The distinction the `role` entry carries is the
load-bearing one: a curated claim is the only kind here that states a direction,
because an affinity is how tightly and never how.

The entries that named a thing without defining it were rewritten. **Assignment
basis** is the clearest case: it used to open "the direct human basis is target
taxon 9606, a direct assignment and no variant", which explains the rule to
somebody who already knows what an assignment is and nobody else. It now starts
where the reader is — assignment is the step where a measured number gets
attached to a protein, because the experiment was run in an assay and somebody
decided which target that assay was measuring — and only then says which
assignments the default keeps. **Evidence tier**, **similarity** and
**admission** were rewritten the same way, each opening on what the thing is
rather than on the rule that implements it.

**They are one or two sentences each, and that is the rule now** (2026-09-23).
The user found them "way too long", worst of all the similarity one, which ran
to eleven sentences. A hover box that covers the panel is the wrong place for a
rule's justification. Each entry now says what the thing is, in words a reader
who has never opened ChEMBL can follow, and the reasoning lives here and in the
docs. The tier-reason explanations (`TIER_REASONS`) were cut the same way.

**A common name finds the molecule it is a name for.** Search matches ChEMBL's
whole synonym list — 1,314 of the 1,331 entries carry one, up to 146 names each
— and that list is better than the seed set suggested: Tylenol, Xanax, Viagra,
Ambien, Marinol and Epidiolex already found their molecule. What it does not
carry is the short form a person actually types. ChEMBL 37 spells THC only
inside `.delta.1-thc` and `Delta-9-thc`, so "thc" was a substring hit on three
molecules at once — one of them *ethchlorvynol*, which contains the letters and
is not a cannabinoid — and the tie was broken alphabetically, putting dexanabinol
first and dronabinol second.

Two things fix it. A **reviewed alias map** in `scripts/cohort/export.py`, keyed
by ChEMBL ID, carried over from the legacy exporter's and extended only where
ChEMBL's own synonyms do not already answer: THC, CBD, ASA and L-DOPA appear
nowhere searchable otherwise. Combination products are excluded on purpose —
Adderall is a mixed-salts formulation and not a name for amphetamine. It is
search-only: it renames no node and reaches neither source matching nor
evidence, and adding a name is a re-export rather than a rebuild.

And the **ranking now puts how well a hit matched before which field it landed
in**, which is the opposite weighting from the legacy page and deliberately so.
There the choice was between a gene symbol and an accession, and a partial
symbol match was worth more than an exact hit on another protein's accession.
Here an entry carries a hundred-odd names including the brand names of
combination products, so a substring buried in one of them is the commonest kind
of hit there is, and an exact reviewed common name has to beat it. Field
position is still the tie-break, in order of what a match there is worth: the
entry's own name, then a reviewed common name, then its ChEMBL id, then the raw
synonyms. A result row now says *which kind* of name it matched — "common name
THC" against "also called .delta.1-thc" — and says nothing at all when the hit
was the entry's own name, which the heading already highlights. For targets the
tie-break is the component count, so `ADORA1` opens **Adenosine receptor A1** and
not the four-member *Adenosine receptor* family that also lists that gene: the
family standing in front of the subtype is the merge D06 exists to refuse.

**Why an entry is in the catalogue is no longer on the panel** (2026-09-27, at
the user's request). It was one line under the identity table — *In the
catalogue by ATC N and a qualifying indication · seed molecule* — and, for the
five seeds the clinical rule leaves out (rolipram, pentoxifylline, loperamide,
mibefradil, theobromine), a warning pill and their exclusion reason. The
catalogue is going to grow past ATC N and the qualifying indications, so the
rule that admitted an entry is a fact about this project rather than about the
drug, and a seed outside the cohort is no longer marked as the odd one out,
there or in a search result. Nothing in the database changed: `in_cohort`,
`is_seed`, `admission_reason` and `exclusion_reason` are still stored and still
exported, and the five seeds are still in the catalogue.

The same day three smaller things changed. **Retained claims** starts folded,
like the other long sections. A claim row on the molecule and pair panels names
its target's **species** after the target type, since the broader-layer pill
says only that an assignment is not direct human, not which animal it is. And
the target panel's **Components** lost its "Context only…" note; the one
sentence in it that mattered — a claim at the target is never passed on to its
proteins — is the heading's hover.

**The indications have since left it, and are a section of their own.**
They were inside it because they are what the indication route reads — but what
a drug is used for and how far it has got are facts about the *drug*, useful to
somebody who does not care why the entry is in the catalogue at all, and
"in phase 3 for Parkinson's and not approved for it" is not a statement about a
selection rule. **Indications** is the last section of the molecule panel,
folded and remembered like the claim lists: below the pharmacology, because an
indication is still never evidence about a target, and above nothing, because
it is no longer a line inside somebody else's argument. Its note is two
sentences at most (2026-09-24, at the user's request): how much of the drug's
record is listed, and that a phase is the furthest any trial reached and
"completed" means finished, not worked. It no longer counts the conditions that
admitted the entry — the membership fold names the route — and why a condition
may have no trial link is in the section's hover.

Three things inside it changed with the move.

*Every disease is listed, the near misses among them.* The panel printed six
and then the words "8 more" — a count with no way to reach what it counted —
and showed only the ones that qualified. Both were about membership. A phase-2
indication is a fact about the drug and is exactly what "tried for this, not
approved for it" looks like, so all of them are listed now, highest phase
first, and folding the section is what makes a long one bearable. 82 is the
most any entry here carries.

*One disease is one row.* ChEMBL files a `drug_indication` per *form* of the
molecule and the forms fold onto one parent here, so caffeine carried Pain
twice — Approved against `CHEMBL113` and Phase 2 against `CHEMBL1200569` — which
is one disease and not two. **682 of the 5,939 diseases in this catalogue are
assembled from more than one record, 227 of those records disagree about the
phase, and 115 put the same disease on both sides of the qualifying line.** A
disease is one row at the furthest phase any record reached, the trials behind
all of them are pooled, and the number of records is stated rather than being
visible only as a repeated name — the same rule, and the same reason, as the
de-duplication of a curated claim's references.

*The list says how much of the drug's record it is showing.* `molecule_indications`
holds only the diseases inside the adopted scope, so a section headed
"Indications" would read as the whole label while being a neuro-and-pain slice
of it: fenretinide shows 4 of its 27 diseases, sodium chloride 82 of 418, and
**959 of the 1,331 entries have a disease that is not listed here.** The build
now records `molecules.n_indications_chembl`, the distinct diseases ChEMBL has
for the family across *every* therapeutic area, purely so that sentence can be
counted rather than hedged.

And an indication says its disease and the phase it reached and nothing else.
The scope token beside it — `core`, `general_pain`, `neuropathic` — names which
part of the adopted policy the disease fell in, which is a fact about the rule
rather than about the drug, and it was repeated on every row and summarised in a
row of its own above them. Both are gone, and the `scope` help entry with them.
The column is still in the database and still in the export; nothing here decides
what the build records. The one other place the machinery showed through was a
search result, which named the route as the build's own token — *both_routes*,
*route_atc_n* — in the one place a reader is looking for a molecule rather than
for why it is here; a row now carries its id, its category and its claim count,
and says "seed, outside cohort 1" only where that is true.

**A trial says where it stands, and what it reported, and nothing more**
(2026-09-23). `scripts/resolve_cohort_trials.py` backfills `trial_status` from
ClinicalTrials.gov by NCT id: the registry status, the sponsor's stated reason
for stopping, the trial's **own** phase, and the p-values it posted for its
**primary** outcomes. 12,815 of the 12,845 cited ids resolve. Each disease row
tallies its trials (ongoing / completed / stopped early), and each trial
states its phase, its status and any main-goal p-value, verbatim.

What this deliberately does not do is say whether a drug *failed* for a disease,
needs another trial, is under review or was not filed. The user asked for
exactly that, and it was measured and declined: no identifier-keyed source
holds it. In a sample of 100 completed trials behind "Phase 3, not approved"
rows, 55 posted no results, 27 posted results with no test of the main goal,
and 18 reported a p-value. **44 of the 100 were not phase 3 themselves**, which
is why each trial now states its own phase: a row's phase is the furthest any
trial reached, and the list under it is mostly earlier studies. Regulatory
states live in press releases and filings, and reading them would mean writing
claims from prose, which invariant 15 refuses everywhere else. "Completed" is
never drawn green and the section says it means finished, not worked. Only
outcomes with a p-value are exported: the untested ones' titles were 610 KB of
the startup file and the page shows none of them.

**A trial says when it ran, and a date that is only a plan says so**
(2026-09-28, at the user's request). A phase 2 that completed in 2005 under a
disease that never reached Approved says something a phase 2 still recruiting
does not, and the two lines read alike. The backfill now stores the registry's
start and completion dates verbatim with the type CT.gov gives each
(`schema_version` 3), and each trial line carries its years beside its phase:
"phase 2, 2001–2005". The completion date is the whole study's, not the
primary completion: the question is when the trial stopped running.

The type is the part that matters. Of 13,021 resolved trials, 1,889 give their
end as ESTIMATED, and 908 of those are trials whose status is UNKNOWN — not
updated in two years — with 890 of the 908 planned for a year already past.
Printed bare, that year reads as the year the trial ended. So an estimated date
is always worded as planned ("started 2009, planned to end 2012"; "planned
2027–2029"), and an untyped one is shown as reported, because the registry
typed no dates before 2017 and an older record's date is what it reported, not
a guess (336 of 9,513 completed trials). A trial with no date shows none (265
completed trials have no completion date; a few carry only a primary
completion, which is not read). Only the years are exported — 131 KB on the
startup file — and the full dates stay in the database.

Two uses of the years followed the same day. Within a phase the list runs
latest first, by end year (or start, where there is no end), planned or not —
an ongoing trial is the most recent there is, and in registration order the
newest phase 2 sat among studies twenty years older. And a folded list's
summary carries the span its trials actually ran ("9 trials, 2008–2015, 6 at
phase 3 or later: 9 completed", bitopertin), so whether a disease row is
history or current reads without opening it. That span counts only dates the
registry reports as having happened: a planned end, often long past on a
trial nobody updated, would stretch it to a year nothing reached.

**A trial names the countries it had sites in, beside its id** (2026-10-15, at
the user's request, on the `worktree-foreign-trials` branch). Trimipramine's
indications said its Phase 1+ trials ran outside the US only, in Germany, and
not which trial that was; the line now reads "NCT02374567 (Germany) phase 3,
2015–2017". The countries are the registry's own `trial_status.countries`
(`schema_version` 4), exported per trial at a fixed index after the years. Of
14,829 trials, 10,831 list one country and some up to 47, so three are named,
the US first because it is the line the trial-sites filter draws, the rest
counted ("+5 more") with the whole list as the hover. The 1,442 records that
list no site say "(no sites listed)" — a gap in the record, not "nowhere" — and
a row fetched before sites were asked for says nothing. It costs 0.31 MB of
the startup file, nearly all of it the 1,999 distinct joined lists;
interning each country instead would save about 30 KB, not worth a second
format.

ChEMBL's "Approved" is **not** US-only, which was said wrongly once in
conversation: of the 1,376 approved indication records here, 122 rest on an EMA
reference alone and 276 on ATC alone.

**A condition can be searched for, and opens the molecules recorded for it.**
The user's second use for this page is to start from a disease and find
molecules that may be relevant to it. Search has a Conditions group matching
MeSH headings, and every disease on a molecule panel is a link to the same
place. The condition panel lists its molecules by the furthest phase each
reached for it, folded like everything else, and a **Targets they share** list:
targets two or more of them act on, each with the catalogue-wide count beside
it, because hERG will sit near the top of any such list for reasons that have
nothing to do with the disease. The canvas lights the molecules and their
targets, with no second hop. Epilepsy is 96 molecules; the panel builds in
3 ms. What it does **not** yet do is rank molecules *not* recorded for the
condition by how much they resemble the ones that are, which is the obvious
next step and the one closest to the similarity goal.

**A name stem can be searched for, and opens its molecules** (2026-09-26, at
the user's request). Search has a **Classes** group matching USAN/INN name stems
by what they stand for and by the stem itself, with or without its dash.
"antidepressant" finds the `-oxetine`, `-pramine`, `-triptyline` and `-faxine`
stems, and "pramine" finds `-pramine`. The molecule panel has a **Name stem**
row linking each stem. A class panel lists every molecule filed under the stem,
with its sub-stem, and the condition panel's **Targets they share**. The canvas
lights the class the way it lights a condition. 747 of the 1,331 entries carry a
stem.

**ATC classes were surfaced the same way for one version and taken back off**
(version 23, reverted the same day at the user's request). The reason is in the
data, not in the presentation: ATC files a drug by what it is *used for*.
Caffeine's "Xanthine derivatives" (N06BC) is the stimulant xanthines, caffeine
and propentofylline. Theophylline is under *Xanthines* (R03DA) with the asthma
drugs, theobromine is in both of those and a diuretic class (C03BD), and
pentoxifylline is a vasodilator *Purine derivative* (C04AD). The same chemical
family is split four ways, and the page's question is which molecules are alike.
The molecule panel's ATC row is the bare admission-route code again.

**A MeSH pharmacological action can be searched for and opened** (2026-09-26,
at the user's request). ChEBI, ClassyFire and MeSH were compared the same day.
ClassyFire is the best *structural* taxonomy (it puts all the xanthines
together, and quinupramine with imipramine), and ChEBI misfiles quinupramine as a
dibenzooxazepine although it holds no oxygen. MeSH's pharmacological actions are
the one source that says what a drug *does*. They were adopted, and MeSH's own
structure tree was adopted later the same day (below). Search lists them first in its Classes group, ahead of
name stems whatever the match, so "tricyclic" opens *Antidepressive Agents,
Tricyclic* (17 molecules) before USAN's structural "-pine: tricyclic compounds".
The molecule panel has an **Action (MeSH)** row. An action's panel links MeSH,
names the actions it sits inside and the narrower ones inside it, and lists
every molecule filed under it or under anything below it, naming the narrower
action that brought each in. It used to add a sentence on what NLM's indexers
record, which was dropped (2026-09-27, at the user's request): the MeSH link and
"pharmacological action" already say where the class comes from. Caffeine and
theophylline share *Phosphodiesterase
Inhibitors* and *Purinergic P1 Receptor Antagonists*; clozapine is under
*Antipsychotic Agents* and nowhere near the tricyclics. Quinupramine carries no
action at all, because MeSH has none for it. No identifier-keyed source says it
is a tricyclic antidepressant.

**A MeSH structure class can be searched for and opened** (2026-09-26, at the
user's request: "that caffeine is a xanthine derivative"). It is a class source
of its own, beside the actions and never merged with them, because the two
disagree usefully: clozapine is a dibenzazepine next to imipramine and is not a
tricyclic antidepressant. Quinupramine, which has no action, lands in
*Dibenzazepines* with imipramine, clozapine and carbamazepine. The molecule
panel has a **Structure (MeSH)** row naming the classes directly above the
molecule, with a link to its own MeSH record. A drug's own heading is left off
its own row, where it would read as the drug being a kind of itself. A structure
class's panel links MeSH, names the classes it sits inside (Xanthines is inside
*Alkaloids* and *Purinones*) and the narrower ones inside it, and lists every
molecule under it or below it with the narrower class that brought it in. A
member filed under its own heading says "its own heading", and that heading is
never given as its route into a wider class. Search lists structure classes after
the actions and before the name stems, so "xanthine" opens *Xanthines*
(7 molecules). The startup payload grows by 109 KB.

**A phase is an annotation of trials, and the trials are linked.** "Phase 3" on
its own is this page asserting a development stage and offering no way to check
it — the same shape as the legacy page's `n=13` beside a single citation, which
is what `measurements` exists to answer. ChEMBL's `indication_refs` carries the
ClinicalTrials.gov registrations its curators read the phase off, and the build
now stores them on `molecule_indications.trial_ids`. Coverage is best exactly
where the question is sharpest: **2,078 of the 2,093 phase-3 diseases here carry
at least one**, against 563 of the 1,078 approved ones, because what ChEMBL
cites for an approved indication is usually the product label rather than a
trial. That asymmetry is stated in the section rather than left to be inferred
from a missing link, which would read as no trial having been run. 12,845
distinct studies are reachable this way; one disease carries 258 of them, so a
row links a single study inline and folds above one, with the count on the
disclosure.

Only the identifiers are stored. ChEMBL's own `ref_url` is a clinicaltrials.gov
*search* over the same NCT ids, and the link here is built from the identifier
at display time — invariant 15, and the reason it is one is that an NCT id
resolves to exactly one registry record while a search is somebody else's query
frozen into the database.

**The panel says how far the molecule itself has got, before any of the
diseases.** `molecules.max_phase` has been in the export all along and was drawn
nowhere. It answers "is this approved or still in trials" without opening
anything, which is the question a reader asks first and which the disease list
could only answer one disease at a time. **296 of the 1,331 entries stop at
phase 3** — trialled that far and approved for nothing — and that is a different
thing from an approved drug being trialled for something new, which is the
commoner shape here and which reads as *approved* with the new disease at its
own phase below. The two used to be indistinguishable. The row says which in
words rather than printing ChEMBL's number, and an unrecognised value names
itself rather than going silent. It is not the admission test and its help entry
says so: the indication route reads the phase of the *qualifying indication*,
which is why an Approved drug whose only in-scope disease sits at Phase 1 is not
admitted through it.

**And "approved" says what for, where the list below cannot** (2026-09-27, at
the user's request). Bromazepam read *approved* over three phase-3 diseases,
because its approval is for Anxiety and the Indications section lists only the
neurological and pain conditions. **327 of the 900 approved entries** were in
that state. For 241 of them ChEMBL files an approval under a condition outside
the scope, and the row now names it: *for Anxiety, a condition not listed
here*, with the first three names printed and every name on hover. The other 86,
mostly barbiturates, are approved in ChEMBL with no approved indication filed
at all, and the row says *ChEMBL records no condition it is approved for*
instead of implying one. Nothing is added where a listed condition is itself
approved.

**And a phase with nothing behind it says so** (2026-10-17, at the user's
request). Cyclazodone read *reached phase 2, not approved for any disease* over
an empty Indications section. ChEMBL 37 gives it `max_phase` 2 with no
`drug_indication` row, no mechanism and no activity, and its only source record
is the WHO INN list; ClinicalTrials.gov registers no study under either of its
INNs and PubMed holds no human study. That is ChEMBL's pattern rather than one
record: 2,752 parents in the release are phase 2 with no indication and the INN
list as their only drug source, and about 1,900 more add USAN. Here 163 entries
carry a phase below 4 and no disease at all, and every one ChEMBL itself puts at
phase 2 or 3 has an INN or USAN. The row now reads *ChEMBL records phase 2 but
cites no trial or disease for it*: it keeps ChEMBL's number, because a name
being recommended is some sign of development, and stops saying the molecule
reached a phase nothing here shows. A molecule whose diseases all sit outside
the scope keeps *reached*, since ChEMBL does file a phase under a disease for
it, and an Approved with no condition keeps the line above.

Bromazepam itself no longer needs the line. The finding behind it was that
MeSH files **Anxiety** under Behavior (F01) and not Mental Disorders (F03),
and ChEMBL uses that heading for 182 indication records. So Anxiety,
Depression, Smoking Cessation and Anesthesia were added to the scope by id
(decision D16, selection policy 2.1.0, 2026-09-27, at the user's request). That
admitted 4 new members and put Anxiety on 156 entries' lists. After it, 317 of
the 900 approved entries still have no listed approval: 231 name a condition
outside the scope and 86 name none. Drugs that act in the brain but are filed
under a symptom (NK3 antagonists for hot flashes, central anorectics,
antiemetics) are left for the expansion beyond ATC N; D16 says why.

**The panel's two long sections fold, and stay folded.** Caffeine's claim list
is 11 rows and its shared-target list 34, and a reader who is comparing two
molecules reads one of those and scrolls past the other. Supported claims,
Preliminary claims and the similarity list (now **Closest target profiles**) are
disclosures now, and so are the
target panel's Components, Wider targets and Molecules. **All of them start
folded** (since 2026-09-23, at the user's request), so a panel opens as a list of
headings with counts rather than several screens of rows. The heading itself is
the summary:
`.section-toggle` styles it as the `h2` it replaces, so this is a triangle on
the heading the page already had rather than a second kind of heading. Each
keeps its count while folded, for the same reason every other fold here states
what it holds.

Where that state lives is the load-bearing half. Every filter change re-renders
the whole panel, so a fold kept only in the DOM springs open again on the next
click of a control — which reads as the fold not having worked, on a page where
the controls and the panel are the two things a reader is using at once.
`sectionFolds` records it per section and `onAppClick` writes it on the way
through; the element still holds its pre-click state there, because the browser
toggles the `<details>` as the click's default action, so what gets recorded is
its opposite. It is keyed by section rather than by molecule, deliberately: the
reason to fold one away is that this reader is not reading it, and that outlasts
one selection. The membership fold above is remembered the same way.

**Every heading on every panel folds** (2026-09-25, at the user's request). The
seven that were still a bare `<h2>` — the molecule panel's Coverage and Retained
claims, the retained panel's reason groups, the edge panel's "The proteins in
it", "Wider targets it sits in" and "Either end", and each shared-target block
in the pair panel — are `foldedSection`s like the rest. They started **open**,
unlike the long lists, because each is either one sentence or the answer to the
click; a pair block is keyed by its target, so folding hERG away in one pair
folds it in the next. A test holds the source to having no `"<h2>"` left.

**Every section now starts folded, on every panel** (2026-10-02, at the user's
request): the pair panel's shared targets and Why this score, the edge panel's
Claims and its action groups, Coverage, Either end, Species, the components and
wider-target lists, and a class's members. `foldedSection` no longer takes an
open-by-default flag at all, and a test holds the source to passing none. The
headings carry their counts, so a folded panel is a table of contents rather
than an empty one, and anything the reader opens stays open across selections
as before. A jump from Why this score still opens the block it names.

**The panel itself folds, and nothing can be selected** (2026-09-25, at the
user's request). "Hide panel ›" on the graph's top-right corner gives the graph
the whole width and tells vis to resize at once rather than on its one-second
poll; folded, the same corner reads "‹ Panel · CAFFEINE", so a selection made
with the panel away is never silent. The choice is remembered in the browser
like the legend's. **Clear selection** in the top bar, or Escape once no popover
is left to close (and never from inside the search box), selects nothing: every
node at full opacity, every line at the resting 0.22, nothing lit and nothing
dimmed, and the panel says so. The layout does not move, since a selection only
ever changes what is lit. A click on empty canvas still keeps the selection —
the same click dismisses the two popovers, and losing a selection to it would be
the worse surprise. Reset still returns to caffeine (D13).

**Back undoes a selection** (2026-09-26, at the user's request, for misclicks).
"‹ Back" in the top bar returns to whatever was selected before, and its hover
names it. Every path that changes the selection goes through `select()`, which
records the previous one, so a canvas click, a panel row, a search result,
Clear selection and Reset are all steps Back can undo. Nothing selected is a
state like any other, so Back after an accidental Clear brings the selection
back. Going back records nothing, so repeated presses walk further back rather
than toggling between two states. Re-selecting what is already selected records
nothing, and the page opening on caffeine is not a step, so Back starts
disabled. It is panel state only. It moves no filter, and going back to
something the filters have since hidden opens it the way search does. The
history holds the last 100 selections and is not kept across page loads.

**The address names what is selected, and under which filters, so it can be sent** (2026-10-10, at the
user's request, before opening the page to the public;
[HOSTING-REVIEW.md](HOSTING-REVIEW.md)). Nobody could link to caffeine. The
selection is now the URL's fragment — `#m=CHEMBL113`, `#t=CHEMBL251`,
`#m=CHEMBL113&t=CHEMBL226` for an edge, `#m=CHEMBL113&with=CHEMBL190` for a
pair, and `retained=`, `condition=` (MeSH id) and `class=` (the class key) —
and the comment above `selectionLink` is the reference. Four choices in it:

- **A molecule is named by its ChEMBL id**, never the page's molecule number,
  which is the export's row order and moves with a rebuild; a link from last
  month's build still opens the same drug.
- **It is a lookup key and nothing else.** It is the first thing read from the
  URL that does anything (the other two are debug flags), so each value is
  looked up in a map built from the payload; one naming nothing opens what the
  page opens without a link, and the address is put back to name that. No part
  of the fragment is written into the page.
- **It carries the sender's filters too** (changed the same day, at the
  user's request; the first version held the selection alone). A link is a
  claim about what the sender saw, and the same caffeine under someone else's
  filters is a different picture with different neighbours. Only a filter
  moved off its default is written — `&tier=supported`, `&potency=10`,
  `&mech=ANTAGONIST,PARTIAL%20AGONIST`, `&canvas=hide`, `&groups=separate`,
  `&color=evidence` — so a link to the page as it opens is still
  `#m=CHEMBL113`, and a filter a link leaves out is at its default, whatever
  the reader had. Each value must be one its control offers (a mechanism, one
  some claim in the catalogue carries), and one that is not is left at its
  default. A link whose selection names nothing still carries its filters; a
  pasted link of filters alone keeps what is open; Back restores the
  selection, never the filters, as it always has. The cost is the one the
  first version avoided: if a default changes, an old link that left a filter
  out opens under the new default.
- **It is written with `replaceState`, never by setting `location.hash`.** A
  browser history entry per click would put a second Back beside the page's
  own, and the two would disagree about where back is; `replaceState` also
  fires no `hashchange`, so writing the link never reads it back. A link pasted
  into an open page *is* read, through `select()`, so Back returns from it. The
  page opening at a link is not a step, so Back still starts disabled. Where
  the host refuses `replaceState` (a sandboxed frame, such as the claude.ai
  artifact) the address is simply left alone.

**A molecule's claims can be grouped by curated mechanism instead of by tier**
(2026-09-25, at the user's request). A "Group claims by" toggle above the lists
switches between Supported / Preliminary and one section per exact ChEMBL action
(Antagonist, Inhibitor, …), commonest first, then the measured claims under
**Binding** and **Functional**, each saying "measured, no direction" in its
heading as the edge panel's do. Those are most of every molecule's claims,
because only a curated claim carries a direction: a measured affinity is never
filed under "antagonist" however well replicated. It is panel state and not a
filter, so it moves no claim, changes no count and is not in the graph
signature. The tier pill stays on every row.

The button reads **Action or measurement** (renamed 2026-09-26, at the user's
request). It used to read "Curated mechanism", which described only the first
of its sections and implied every claim would be filed under one: a molecule
with no curated claim gets nothing but Binding and Functional in that mode, and
a Ki is not a mechanism. The stored value is still `mechanism`, so a remembered
grouping and its fold keys carry over.

The measured claims used to be one group headed **No curated mechanism**, and
that heading read as a statement about the *pair* when it was one about the
*claim*: armodafinil's measured Ki at human DAT sat under it two groups below
ChEMBL's curated INHIBITOR claim at the same target (split 2026-09-25, at the
user's request). The two are separate claims because they are separate kinds of
evidence (D06); what was wrong was only the name. Armodafinil also has a
Supported binding claim at *rat* DAT, where ChEMBL genuinely curates nothing,
and carrying the human direction across to it would be a cross-species inference
this page does not make. A curated claim with no action gets a **Curated · no
direction recorded** group of its own rather than being filed with the
measurements; there are none in this build.
The same day the **retained claims** moved from between the claims and the
ranking to the very bottom of the panel, below the indications, and were
renamed. The heading used to read "Retained observations" while counting
*claims* (tier `limited_or_unresolved`, each built from one or more observation
rows), which is one thing named by another's word and was what prompted the
question of what the difference is. The panel it opens, its hover text and the
edge panel's loading note all say claims now; "observation" is kept for the
individual rows.

**The similarity list draws every row it counts.** It drew the first 25 under a
heading counting the whole list, and 304 of the 1,331 entries have more than 25
neighbours — haloperidol has 180 under the default filters and pimozide 670 with
all of them open — so a count and a list disagreed on nearly a quarter of the
catalogue, in the section that answers this page's own question. That is
invariant 13, and the fix is not a note about the cap: every row is drawn.
Pimozide's 670 rows build in 7.0 ms and haloperidol's 180 in 1.4 ms — both
measured before the tier and basis defaults opened, which is visible in the row
counts themselves: haloperidol has 639 neighbours under the current defaults,
not 180. Re-measured in the vm harness rather than the browser those figures
were taken in, and so quoted only against each other: pimozide is 11.4 ms before
reading direction at the protein and 13.5 ms after, and haloperidol 12.3 and
12.2. Folding the
section is what makes a long list bearable — a reader who does not want it
closes it, rather than being handed a quarter of it and told the total.

**The list is called Closest target profiles, and each row says why it is where
it is** (2026-09-26, at the user's request). It was headed "Shares targets
with", which names the input and not the ranking: the order is set by evidence,
rarity, opposite directions and above all the normalisation, and the count of
shared targets does not decide it. Caffeine's list puts tozadenant (5 shared)
above nimodipine (6), because tozadenant's five are all it does and nimodipine's
six are a quarter of its 25, and menthol (3) above pentoxifylline (4) the same
way. The row showed the count and a bare score, so that order read as
arbitrary. "Closest" and not "most similar" or "acts most like", because shared
targets are a weaker claim than acting alike (Goal).

What makes the explanation exact rather than a gloss is that the score is a
**sum over shared targets**, scaled by two factors that are the same for every
target on the pair (the D15 direction factor and the √(degree × degree)
normalisation). So a target's share of the sum is exactly its share of the
score. `sharedTargets` now keeps each target's `contribution` with its three
factors, and the pair's `raw_score`, `direction_factor` and both degrees, and it
leaves `shared` in contribution order.

- **The row** reads *all 5 of its targets · 5 of CAFFEINE's 43 · mostly ADORA2B,
  ADORA2A*: the normalisation in words, then the fewest targets (at most three)
  carrying half the score. Where three do not reach half it says *spread out,
  led by …* rather than claim "mostly" of a third. Where two drivers share a
  symbol, two species' records of one protein, each names its organism
  ("OPRM1 (Cavia porcellus), OPRM1 (Homo sapiens)"), because "mostly OPRM1,
  OPRM1" reads as a mistake. The numerator is `n_shared`, the count stated
  everywhere else. The denominators are target records and so include a family
  repeat, which the "+N family repeat" tag on the same line already accounts
  for. The raw score left the row: it had no unit a reader could use. It is now
  a bar scaled to the top row, with the number on hover, and the section's own
  hover says what the bar is (2026-09-27, when it was asked about).
- **The pair panel** opens with **Why this score**: one row per counted target,
  showing kind (×1 / ×½), evidence, rarity and share of the score, largest
  first, with the species on every record since ADORA1 and Adora1 are
  otherwise told apart only by letter case. Human records were left unmarked at
  first, and every target heading followed the same rule; beside "(rat)" a bare
  heading read as a species not recorded rather than as human, so since
  2026-09-27 every record names its own, human included. The first eight rows are shown and
  the rest fold under their count and share. Then comes the arithmetic, *Sum
  1.737 ÷ √(43 × 25) for how much each does = 0.053*, with the direction factor
  inserted where there is one. The heading line gains the rank (*#8 of 265 for
  CAFFEINE*), and the target blocks below follow the same contribution order,
  so the target doing the work is the first one read. Each column heading
  explains itself on hover (2026-09-27, at the user's request, starting from
  "what is meant by rarity"). The box is anchored to the table (`.score-wrap`)
  rather than to its narrow column, so the right-hand columns do not open off
  the side of the panel.
- **A protein in several species is one block, one score row and one link**
  (2026-09-28, at the user's request). Caffeine and theophylline's table read
  *ADORA1 cow*: D20 counts a protein at whichever species' record scores
  highest, and there it was the cow's, so the row read as though the pair
  met only at cow ADORA1 when it meets at four species' records. Below it
  sat eleven adenosine-receptor blocks for three proteins, each headed by
  ChEMBL's full name, while the table named them by gene symbol — so a
  symbol could not be matched to its block. Now a species-folded row reads
  *ADORA1 · 4 species* (listed on hover), under the human protein's symbol
  (`proteinSymbol`), since that is the protein the rat's *Adora1* was
  matched to. Every name in the table links to its block
  (`data-jump` → `jumpToBlock`), which opens it without re-rendering.
  Every block heading leads with its gene symbol, and a protein's species
  are one section headed *ADORA1 · Adenosine receptor A1 · 4 species: cow,
  guinea pig, rat, human*. Each record is a folded subsection inside it
  that keeps its own claims, GtoPdb action and rarity. The heading groups
  the records; it does not merge them, just as `proteinKey` groups without
  moving a claim. The molecule → target panel gains a **Species** section
  on the same principle: every record of that protein the molecule has a
  claim at, with this one first and each of the others opening its own
  panel. The drawn, hidden and retained counts are listed separately,
  never summed. It appears only where there is more than one record.
  *Superseded on the edge panel by the next item:* the records are now
  sections of the panel itself rather than rows that open other panels.

**One protein, one node** (2026-10-10, at the user's request: "it's confusing
now that proteins that share a name are two different units on the graph").
The score had counted a protein once across species since D20, and the pair
panel had grouped its records under one heading, but the canvas still drew one
diamond per ChEMBL record — 2,063 target nodes for 1,663 proteins, with 246
proteins drawn two to four times under the same symbol. A reader clicking one
ADORA2A saw a third of the molecules at the receptor and nothing saying the
other two diamonds were the same protein.

- **The canvas.** `catalogueGraph` keys a target node by `targetNodeKey`: the
  protein's first record in `proteinRecords` order (the human record, else the
  lowest ChEMBL id). The key is that record's id, so a node keeps its place
  across filter changes whichever species' claims are on, a protein recorded
  once is keyed exactly as before, and the node carries `records`, the ones
  with a drawn claim. One edge per molecule–protein pair, carrying every
  species' claims, as one edge already carried every role's. The label is
  `proteinSymbol`, the human protein's. Grouping is `proteinKey` and nothing
  else: a complex or a family is still one record and one node per species
  (D20's open item 8), and an unmatched record is still its own protein.
- **The membership lines** reach the protein's node through
  `proteinNodeTarget`, so the rat GABA-A group and the human one both join the
  one GABRA1 node. That merges channel units that shared no node before: 24
  units (largest 27 nodes) became 14 (largest 35). Two records of one
  accession, which `proteinTarget` refuses, are one node here, so naming the
  node is no longer a guess; an accession held by records drawn as two nodes
  still joins neither.
- **The target panel** is headed by the protein — symbol and name, no species
  — with a *Species* row, and one section per record: the one it was opened at
  first, then the protein's own order. Each section carries that record's
  ChEMBL and UniProt links and its claims under the usual tier or action
  grouping. The line above the sections counts molecules once and claims
  apart; a section counts only its own. Wider targets name their species,
  since the rat and the human *Adenosine receptor* family are two records with
  one name.
- **The edge panel** is the molecule and the protein, and it opens at a record:
  a claim row in the molecule panel opens its own record, so preladenant's
  human A2A binding claim opens with *Claims · Human* first and *Claims · Rat*
  below; a click on the line opens at the record carrying its strongest drawn
  claim (`edgeLeadRecord`), human on a tie. The summary row counts drawn,
  hidden and retained across the records, still apart; each section names its
  own counts where they are not all drawn, and its own GtoPdb action. The
  opened record keeps the one-record panel's fold keys, so a reader who keeps
  *Claims* open finds the claims they clicked open. A shareable link names the
  record (`#m=…&t=CHEMBL251`), so it opens at the same species.
- **Search** lists a protein once, at the record that matched best — a rat
  record's ChEMBL id opens the protein at the rat claims — and says how many
  species it was recorded in.

Nothing counted changes: the score, the ranking and the pair panel read
`proteinKey` as before (top-1 38.7%, MRR 0.5119). What moves is the picture:
caffeine lights 32 protein nodes where it lit 43 records, and its second hop
reaches every molecule at those proteins in any species — 270 where it was 265.

**A "mostly common targets" tag was built and taken out before shipping.** It
was meant to mark a rank resting on screening targets like hERG. Read off the
prevalence discount (most of the score from targets below 0.5), it fired on
**211,248 of 227,298** ranked rows and on the top neighbour of 407 of 988
molecules. That is not a loose threshold. Prevalence cannot tell a screening
panel from a mechanism: human OPRM1 is worth 0.28 and hERG 0.24, because both
are measured for hundreds of molecules. Telling them apart is the
curated-mechanism conditioning listed below as open and not yet argued for, so
it was not smuggled in as a display rule. The drivers line names hERG as hERG
when it is what carries a rank, which was the tag's purpose.

Nothing counted changes: the same rows, scores and order (top-1 38.2%, MRR
0.5105).

**An explanation opens on hover or on a keyboard tab, and no longer on a
click.** `.help` carries `tabindex="0"` so the keyboard can reach it, and the
rule read `.help:hover .help-text, .help:focus .help-text` — but a click focuses
the label too, so the box opened on the click and then stayed open, over
whatever was beneath it, until something else was clicked. Every heading on this
page that explains itself behaved that way; the headings that fold a section
made it obvious, because there clicking the label is also how the control gets
worked. `:focus-visible` is exactly the distinction between a reader who tabbed
to a label and one who clicked it, and it is what `viz/legacy/index.html`
already used — the cohort page lost it in the rewrite rather than never having
had it.

**Every admitted candidate and every retained seed stays searchable**, including
the 260 with no drawable evidence. Four gap statements are kept distinct and
never merged: no qualifying evidence in ChEMBL 37, target or evidence
unresolved, hidden by the current filters, and source not assessed. Retained
observations are inspectable without a graph edge, and no edge is ever
manufactured to avoid an empty state.

A claim block marks the endpoint class that **earned** its tier, not the one
with the strongest number. That distinction is load-bearing and was got wrong
once here: caffeine's ADORA1 claim is Supported at `binding:Ki` across 11
publications and also has a single `binding:IC50` at a lower value, and showing
the lower one printed "Supported · multiple studies" beside "1 measurement in 1
publication". The stronger value is still shown, named as the different
endpoint it is.

Per-measurement rows live in per-molecule shards under `viz/evidence/` and are
injected as script tags on first use — classic script loads from `file://` are
permitted, which was checked in Chrome before the format was chosen, because
the whole offline workflow depends on it. A missing shard reports itself as a
missing file, never as an absence of evidence.

