# Making the viewer work on phones

A plan, written 2026-10-18 against `viz/index.html` at commit `03a4c81`.
**Nothing in it is adopted.** It answers the open item in
[HOSTING-REVIEW.md](HOSTING-REVIEW.md) — *Decide on phones: make it responsive
or state that it is desktop-only* — by laying out what responsive would take,
in the order it should be done. Line numbers below are that commit's.

## Where the page stands

A phone today gets the desktop page shrunk to fit:

- **No `<meta name="viewport">` and not one `@media` rule** in the page, so a
  phone browser lays it out at a desktop width (about 980 px) and scales the
  result down.
- **Every explanation opens on hover.** 63 `helpLabel` call sites, the
  legend's `ACTION_HELP` rows, and seven kinds of `title=` tooltip built into
  the panels that carry content: an Approved's source, the full trial-sites
  list, a trial outcome's full title, a list of names cut short, the
  similarity bar's exact score, the species behind a protein, and a
  withdrawal's events. A touch screen has no hover, and `.help` opens on
  `:focus-visible` ([index.html:262](../viz/index.html#L262)), which a tap
  does not trigger. Several viewer rules promise that a fact is "on hover";
  on a phone those facts are unreachable.
- **Fixed desktop widths:** the panel is `flex: 0 0 420px; max-width: 42vw`
  ([:70](../viz/index.html#L70)), Display options 360 px
  ([:136](../viz/index.html#L136)), About 440 px
  ([:86](../viz/index.html#L86)), a help box 300 px
  ([:246](../viz/index.html#L246)).
- **The graph is tuned for a mouse:** a line is caught within
  `PICK_EDGE_PX = 8` screen pixels ([:8810](../viz/index.html#L8810)), and
  `dragNodes: true` ([:8352](../viz/index.html#L8352)) means a finger that
  starts a pan on a node drags the node instead.
- **Load cost is unmeasured on a phone.** `graph.data.js` is 8.9 MB (1.8 MB
  gzipped), and vis lays out about 2,600 nodes; the only timing ever taken was
  desktop Chrome (216 ms to parse and index, against a 4 MB payload).

Some of the work is already done: the panel folds away and resizes the graph
when it does (`renderSidebarState`, [:9228](../viz/index.html#L9228)), the
legend collapses, and Display options and About are `<details>` drop-downs.

## The steps

### 0. Measure on a real phone first

Deploy to staging (`scripts/deploy_cloudflare.sh --preview`) and load it on a
mid-range Android phone and an iPhone, with remote debugging attached. Record:
time to first draw, time until the layout settles, peak memory, and whether
the tab survives. If it takes tens of seconds or the tab is killed, that
changes the plan more than any layout work does — the remedy would be
something like shipping precomputed node positions, which touches the export
rather than the page.

### 1. Decide what a phone is for

**Recommended: panel first.** On a narrow screen you search, then read the
molecule's targets, shared-target rows and closest target profiles; the graph
is a second view one tap away, not squeezed beside the panel. A 375 px canvas
holding thousands of nodes is hard to read, while the panels carry what the
page says in words. The alternative — the graph first with the panel as a
bottom sheet over it — keeps the picture primary, which is what the project's
goal names as the deliverable, at the cost of a small canvas with a sheet over
part of it.

### 2. The baseline

- Add `<meta name="viewport" content="width=device-width, initial-scale=1">`.
  It is markup, not script, so the CSP's script hash is unaffected.
- Size `#app` with `100dvh` rather than `height: 100%`, so the iOS address bar
  does not push the disclaimer off the bottom; pad with
  `env(safe-area-inset-*)` for the notch.

### 3. Reflow below about 760 px

One `@media (max-width: 760px)` block:

- **Top bar** — search takes its own full-width row; Display options, About,
  Back, Clear and Reset go into one compact row or a menu.
- **Panel** — leaves the side and becomes a full-screen view (or a bottom
  sheet, per step 1), driven by the existing toggle and
  `renderSidebarState`, which already calls `network.setSize()`.
- **Display options and About** — full-width sheets with their own scrolling,
  their heights in `dvh`.
- **Legend** — starts collapsed; `#legend-tip` opens to the legend's right
  (`showLegendTip`, [:9286](../viz/index.html#L9286)), where a phone has no
  room, so it opens above or below instead.
- **Count box** — `#graph-counts` may take 55% of the width
  ([:126](../viz/index.html#L126)); smaller, or folded to one line.
- **Disclaimer** — stays permanent and outside every panel, as the viewer
  rule requires; only its size changes.
- **Search results** — capped at `60vh` ([:50](../viz/index.html#L50)), which
  the on-screen keyboard partly covers; size them from `visualViewport`.
- **Wide tables** — the pair panel's score columns go in a horizontally
  scrolling container, or stack.

### 4. Every hover explanation reachable by tap

The largest piece, and the one that matters most for what the page says.

- `.help` opens on a tap and closes on a tap elsewhere; the box is clamped to
  the viewport instead of opening a fixed 300 px from the label's left edge.
- The seven content-bearing `title=` tooltips move onto the same mechanism,
  and so does the count box's; a `title` on a button that only names what it
  does can stay.
- The legend's `ACTION_HELP` rows open their box on a tap.
- **Must not reintroduce the desktop bug** that moved `.help` from `:focus` to
  `:focus-visible`: a box opened by a click and left open over the panel.
  Tap-to-open belongs to coarse pointers only, or closes reliably.

### 5. The graph by touch

vis handles pinch and pan itself; what needs changing is this page's own
handling.

- `pickLit` takes `PICK_EDGE_PX` at 8; on a touch event (`pointerType`
  `touch`) it should be about 20 px.
- `dragNodes` off for touch, so a pan is a pan.
- At device pixel ratio 3, check the gesture-scene cache's bitmap against iOS
  Safari's canvas-area limit, and the device-pixel thresholds in
  `lineIsFaint` ([:7490](../viz/index.html#L7490)) and `dashIsVisible`
  ([:7401](../viz/index.html#L7401)).
- Check that labels are still readable at phone sizes.

### 6. Tap targets

Under `@media (pointer: coarse)`, buttons, panel rows, filter chips and the
legend toggle grow to about 44 px; a button is under 30 px tall now.

### 7. The back gesture — a decision

On a phone the back gesture is how people close a sheet. The **Links** rule
writes the address with `replaceState` only and never adds browser history
([:9582](../viz/index.html#L9582)). Either the rule takes an exception for an
open sheet or panel, pushing one history entry that Back pops, or the back
gesture leaves the page while a sheet is open.

### 8. Tests and documents

- **Node tests:** the viewport meta is present; a tap opens and closes
  `.help`; every content-bearing `title` is reachable without hover;
  `pickLit` uses the touch tolerance on a touch event.
- **Layout:** the `vm` harness sees no layout, so either screenshots at 375,
  414 and 768 px from Playwright's device emulation (a dev-only tool, not
  part of the page) or a written checklist on real iOS Safari and Android
  Chrome — or both.
- **Documents:** a phones section in [VIEWER.md](VIEWER.md); the viewer rules
  in [../CLAUDE.md](../CLAUDE.md) reworded from "on hover" to "on hover or
  tap"; the item closed in [HOSTING-REVIEW.md](HOSTING-REVIEW.md) and in the
  Not-done list.

## Order

Step 0, then the two decisions (1 and 7); then 2–4 together as the first
version worth shipping — usable, panel first; then 5 and 6; step 8 goes with
each part rather than at the end. Every part is checked on staging from a
phone before production.
