# Task D — a control inside a control

Worktree: `/Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes`
Branch: `explainer-v2-phase3` — commit **`08ecd16`** (base `9bc096e`)

Status: **DONE_WITH_CONCERNS**. The fix is done and verified; the two concerns are
environmental, not code, and both are things the controller has to know about. Neither
is a reason to hold the commit.

---

## 1. The call sites I counted

`ProbabilityBar` render sites in shipped code (`packages/predictor-ui/src/`, excluding
tests) — **two**:

| # | Site | Wrapped in a control? | `onSegmentFocus` | `highlightKey` |
|---|------|----------------------|------------------|----------------|
| 1 | `ExplainerPanel.tsx:233` | no — a `<div>` inside a `<section>` | **yes** (`:242`) | **yes** (`:241`) |
| 2 | `MatchCard.tsx:96` | **yes — the card is a `<button>`** (`:52`) | no | no |

So: one caller wraps a bar, one does not, and the one that wraps is the one that does
**not** pass `onSegmentFocus`. Verified by grep over every `onSegmentFocus=` and
`highlightKey=` in the worktree — both appear only in `ExplainerPanel.tsx` and in test
files. `MatchCard` has no `useState` at all; it is a pure function of its props.

Elsewhere: `harness/main.tsx:177, 184, 190` (three bare bars, none pass
`onSegmentFocus`), `src/index.ts:5` (the re-export that lets Sports and PL add their
own), and 24 direct renders across the pre-existing test files (4 in `card.test.tsx`, 20
in `explainerV2.test.tsx`, counted on `9bc096e`). `AppFrame` is the only component in
the library that emits an `<a>` (`AppFrame.tsx:29`), which is why the assertion has to
handle links and not just buttons.

**What the count says.** Two in-repo call sites is few enough that a prop would have had
exactly one site to remember it on. That is the argument *for* a prop, and it is why I
checked rather than assumed. It loses on the direction of failure, which is the part
the count cannot tell you: `index.ts:5` exports the component, so the real call sites
are in Sports and PL, which are not in this repository and cannot be counted from here.
A flag on an exported component is a thing a consumer must set correctly on a machine
nobody in this PR can run a test on.

## 2. How the bar learns its context

**It is not told. The branch is derived from `onSegmentFocus`, which the component
already receives.** There is no new prop, so there is nothing to forget.

`SegmentFigure` (`ProbabilityBar.tsx:152-195`, with `LABEL_CLASS` at `:120`) renders the
figures as a `<span>` when `onSegmentFocus` is absent and as a `<button>` when it is
present. `LABEL_CLASS` is one constant used by both branches, so the two differ in the
element and its handlers and in **nothing a reader can see** — same layout, same colour,
same 12px, same `hover`/`focus-visible` rules.

The argument that this is the *same fact* and not a proxy for one:

- **The buttons have exactly one job.** §13c's step through the figures, which reports a
  focus to `onSegmentFocus` and gets a `highlightKey` highlight back. Measured before the
  change: the card rendered **2 descendant `<button>`s** inside its own `<button>`, and
  both handlers were `onSegmentFocus?.(…)` with nothing passed. They were focusable,
  announced as buttons, and did nothing. The component was rendering controls that had
  already lost the only thing that made them controls.
- **A card cannot host §13c.** The other half of §13c is a `FactorList` whose rows set
  the highlight, and a card has no factors. So there is no state for a focused segment to
  report into.
- **The failure direction is safe.** A caller that wraps this bar in a button and forgets
  anything gets plain text: valid HTML, no dead focus stop, and it loses only an
  affordance its own surface is already providing. A prop would have to default to
  *interactive* (so the panel keeps its labels without opting in), which fails in the
  opposite direction — into invalid HTML, on the call site that forgot.

Rejected, and why: a `static` / `withinButton` prop defaulting to `false` would need
`ExplainerPanel` to opt *in*, which silently drops §13c from the one surface the spec
cares about, and from the harness, and from every site that renders a bare bar. Also
`element.closest("button")` — not available to a component, and the answer is the same
fact anyway.

## 3. What happens to `onSegmentFocus` / `highlightKey` inside a card

**Nothing, and that is a consequence, stated rather than papered over.**

- `onSegmentFocus` is unreachable from inside a card and always will be (§13c's other
  half is the factor list). A card's bar therefore cannot report a segment focus, and
  the panel's factor-to-figure highlight **cannot happen from inside a card**.
- `highlightKey` is never passed, so `dim()` (`ProbabilityBar.tsx:269`) is a no-op there
  — every segment renders at opacity 1 — and every `data-highlighted` is `"false"`.
  Asserted in `card.test.tsx`, which reads the rendered values rather than the source.
- **The Escape question, answered directly: the card path has no Escape, and it does not
  need one, because the state `Escape` clears does not exist in a card.** There is no
  highlight to get stuck in, so there is nothing to clear. `ExplainerPanel`'s Escape
  (`ExplainerPanel.tsx:150-159`) exists precisely because the panel *can* set a highlight
  and a keyboard reader has no other way out of it. A reader on a card is not left with
  an unclearable highlight; a reader on a card is left with no highlight at all.
- **The condition under which that would change, so it is not mistaken for settled:** if a
  card ever grows a factor list, the highlight becomes reachable and the card would then
  owe an Escape. That is a future change and it should be judged when it is made, not
  pre-empted here.
- I kept `data-highlighted` on the non-interactive labels. It costs nothing and it keeps
  the door open for the case above; it also keeps the pre-existing §13c test honest.

## 4. The assertion: real coverage, and its limits

`src/components/nesting.test.tsx`, 33 tests. `INTERACTIVE` is one selector list; the
walker climbs from each interactive element to its nearest interactive ancestor and
reports `outer > inner`.

**Caught shapes, each built by hand so the claim is checkable without a component that
does the wrong thing on purpose** (11 fault cases, 9 clean cases): `<button>` in
`<button>`, `<a href>` in `<button>`, `<button>` in `<a>`, `role="button"` div in
`<button>`, `div[tabindex]` in `<button>`, `contenteditable` in `<button>`, `<input>` and
`<select>` in `<button>`, `<summary>` in `<button>`, `<input type=checkbox>` in `<a>`, and
a button two levels deep. The clean list is the anti-false-positive half: sibling controls,
a `<button>` holding spans, an `href`-less `<a>` (not focusable, so not a control), and
`role="img"` / `role="status"` / `role="alert"` wrapping a control — the last of which is
this library's own vocabulary.

**The sweep covers every component `src/index.ts` exports**, in the states that carry a
control: `MatchCard` (3), `ProbabilityBar` (5), `AppFrame` with a card inside it,
`RoundNavigator` (2), `ExplainerPanel` (5), `FactorList` (2), `StatTable`, `EmptyState`,
`ErrorState`, `Skeleton`, `BandChip`, `PanelHeading`, `KeyNumberTile` (2), `RecordStrip`,
`StatTile`, `StatusBadge`, `TeamChip`. The zero-control components are listed on purpose,
so editing one of their files is still covered rather than silently absent.

**Anti-vacuity.** Every case asserts the exact number of interactive elements it renders
(measured with a throwaway probe, not estimated — my first guesses were wrong and the
guard caught me). Without it, a component that stopped rendering its control would make
the case pass for a new and wrong reason. I also put the nesting assertion *first* in each
case after noticing the count check was masking it: a real nesting failure now reports
`button > button` rather than "expected 3 to be 1".

**What it does NOT cover — read this before assuming more than it does:**

1. **It covers the states in `CASES` and nothing else.** Add a prop to a component, render
   a state nobody listed, and that state is unchecked. It is a floor, not a proof.
2. **It is a DOM assertion.** It says nothing about reachability, naming, or description.
   `aria-hidden` on a focusable element, an unlabelled control, and a control with no
   handler all pass here. Only the last one is caught, and only because a control with no
   handler is a separate question — see mutation 1 for what the DOM check *does* catch.
3. **It does not look at a consuming site's own markup**, only at what this library
   renders. A `<button>` inside a link in Sports' page is not this test's business.
4. **It does not cover the server-rendered path.** See the parser fact below — a browser
   parsing SSR markup *repairs* the nesting into siblings, so the defect is only ever
   visible in a client-built tree, which is also why it is a hydration error and not a
   styling one.
5. **It does not check tab order, focus visibility, or whether the surviving control is
   reachable in a sensible sequence.**

**The measured fact that shaped the design.** The HTML parser repairs a nested button.
`host.innerHTML = "<button><span><button>x</button></span></button>"` yields
`<button><span></span></button><button>x</button>` — two siblings, and
`querySelectorAll("button button")` finds **0**. So an assertion written against parsed
markup would pass on a page that has the defect. React builds with `createElement`, which
no parser touches, which is why it can emit one at all and why its warning says "This
will cause a hydration error". The walk exists for that reason as much as for the report
it produces, and it is pinned by a test so the reasoning is not lost.

## 5. The React warning, before and after

**Before** (`npx vitest run`, 180 passed, exit 0 — the defect was *not* a test failure):

```
stderr | src/components/card.test.tsx > the match card's bar > accents the segment the card's pick names, not the first one
In HTML, <button> cannot be a descendant of <button>.
This will cause a hydration error.
  <MatchCard left={{code:"TOT", ...}} ...>
>   <button type="button" onClick={function onOpen} className="pr-notch flex w-full flex-col rounded-pr ...">
      <span data-testid="pick-section" ...>
        <ProbabilityBar segments={[...]} pick={{label:"AVL"}}>
>             <button type="button" data-testid="pbar-label" data-seg="TOT"
                     onClick={function onClick} onFocus={function onFocus} ...>

<button> cannot contain a nested <button>.
See this log for the ancestor stack trace.
```

`grep -c "cannot contain a nested" → 1`

**After** (`npx vitest run`, 218 passed, exit 0):

```
grep -c "cannot contain a nested\|validateDOMNesting\|In HTML," → 0
```

No `stderr` block from any test file. The warning is gone, and mutations 1 and 3 below
bring it straight back — so it is the fix closing it, not the warning having been
suppressed.

## 6. Commands, exactly as run, with the numbers I measured

```
cd /Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes/packages/predictor-ui
npx vitest run        # Test Files 10 passed (10) | Tests 218 passed (218) | exit 0   (was 180)
npx tsc --noEmit      # exit 0
cd ../../services/explainer && .venv/bin/python -m pytest -q
                      # 235 passed, 1 warning in 1.01s
cd ../.. && node --test tests/*.mjs
                      # tests 21 | pass 21 | fail 0
```

Baselines measured on this branch before I started: 180 vitest, `tsc` exit 0, 235 pytest,
21 node `--test`. All four hold; vitest is 218 (180 + 38).

### Two things about those commands that the controller should know

**1. `pytest` from the repo root does not give 235 — it gives 44 failed, 191 passed.**
The brief says to run it from the root, and from the root:

```
services/explainer/.venv/bin/python -m pytest -q
→ 44 failed, 191 passed, 1 warning in 0.84s
→ async def functions are not natively supported.
  You need to install a suitable plugin for your async framework...
```

Every failure is the same line, and none is a code failure.
`asyncio_mode = "auto"` and `testpaths = ["tests"]` live in
`services/explainer/pyproject.toml` under `[tool.pytest.ini_options]`. Run from the repo
root, pytest's rootdir is the repo root, that file is not read, `asyncio_mode` falls back
to `strict`, and 44 `async def` tests error out. Run from `services/explainer`, the config
is found and it is **235 passed**. So the 235 baseline is real, but it is a
directory-relative measurement, and a "235" quoted without the directory is a number that
cannot be reproduced by the command as written. Worth pinning in the ledger so the next
controller does not read `191 passed` as a regression — I checked before believing it.

**2. The controller reset this worktree under me, mid-task, and it cost three edits.**
At **17:23:34** — between my source edits and my next test run — a `git reset` landed in
this worktree and reverted `ProbabilityBar.tsx`, `MatchCard.tsx` and
`explainerV2.test.tsx` to `9bc096e`. Evidence, in the reflog:

```
9bc096e HEAD@{2026-09-27 17:23:34 -0500}: reset: moving to 9bc096e
207e20d HEAD@{2026-09-27 17:23:05 -0500}: cherry-pick: docs: handoff — NBA's /facts is authoritative…
3d3b573 HEAD@{2026-09-27 17:23:05 -0500}: cherry-pick: docs: handoff — what the /hub/summary investigation found…
9bc096e HEAD@{2026-09-27 17:22:37 -0500}: checkout: moving from mergecheck to explainer-v2-phase3
```

My first test run passed because the fix was live; the next one failed for a reason that
had nothing to do with my code, and the cause was a reset I did not make. I caught it by
`git status` disagreeing with my own edits and read the reflog rather than re-applying
until green — which is the only reason I can report a SHA. I re-applied, backed the
files up outside the worktree, and committed within a minute. **A subagent and a
controller in one worktree at the same time is a live hazard, and this one is real.**
I flag it rather than absorb it: the reset was almost certainly deliberate (you were
mid-investigation on `mergecheck`), but it silently destroys uncommitted work, and the
next instance may not be as recoverable.

## 7. Mutations

All three applied to the committed state, run, then reverted with `git checkout --`.
**After all three, `git diff --quiet HEAD -- packages/predictor-ui/` → tree byte-identical
to `08ecd16`.**

### Mutation 1 — re-introduce a `<button>` inside the card's bar

Remove the conditional, so the labels are buttons again whatever the caller passes.

```diff
-  if (!onFocus) {
-    return (
-      <span
-        data-testid="pbar-label"
-        …
-      </span>
-    );
+  if (!onFocus && false) {
+    return null;
   }
```

```
Tests  8 failed | 210 passed (218)
  × the card's bar inside the card's own button > holds no control of its own …
  × no component in this library nests one control inside another > MatchCard with a bar
  × … > MatchCard, no pick, with a bar
  × … > ProbabilityBar on its own
  × … > ProbabilityBar with a market row
  × … > ProbabilityBar expandable
  × … > AppFrame with tabs, links and a card
  × ProbabilityBar > makes the segment labels operable only for a caller that can be told about it
```

```
AssertionError: MatchCard with a bar: expected [ Array(2) ] to deeply equal []
AssertionError: MatchCard, no pick, with a bar: expected [ 'button > button' ] to deeply equal []
```

React's own warning reappears in the same run, which is the direct evidence that the
warning's disappearance was this fix and not something else.

### Mutation 2 — the standalone panel's bar renders plain text too, so §13c loses its affordance

```diff
-  if (!onFocus) {
+  if (!onFocus || onFocus) {
     return (
       <span
```

```
Tests  7 failed | 211 passed (218)
  × ProbabilityBar > is operable by keyboard alone, which is what catches a div with onClick
  × ProbabilityBar > shows a 3% segment its label on focus, and keeps it a sliver
  × ProbabilityBar > makes the segment labels operable only for a caller that can be told about it
  × … > ProbabilityBar with a listener: its labels are controls again
  × … > ProbabilityBar, three-way with a listener
  × … > ExplainerPanel, v2, resting
  × … > ExplainerPanel, expandable market row
```

```
AssertionError: expected 'SPAN' to be 'BUTTON'   (×2)
```

**Worth noting which test did *not* fail, because it is a real limit on what §13c's test
coverage says.** `ExplainerPanel`'s *"links a factor to the figure it names, and clears on
Escape"* **passes** under this mutation. It clicks a factor and asserts the segment's
`data-highlighted` is `"true"` — and it still is, because I kept the attribute on the
non-interactive label. So that test covers the **factor → figure** direction and says
nothing about the **figure → factor** direction, which is the direction the buttons exist
for. The tests that catch mutation 2 are the operability ones. If §13c's second direction
is meant to be load-bearing, that is the test to strengthen, and I have flagged it rather
than quietly widened the existing one.

### Mutation 3 — the card's bar interactive again, the card still a `<button>`

Done at the **call site** rather than in the component, which is the more realistic way
this comes back: someone wires the handler without touching `ProbabilityBar` at all.

```diff
-          {bar && <ProbabilityBar segments={bar} pick={pick ? { label: pick.label } : null} />}
+          {bar && <ProbabilityBar segments={bar} pick={pick ? { label: pick.label } : null} onSegmentFocus={() => {}} />}
```

```
Tests  4 failed | 214 passed (218)
  × the card's bar inside the card's own button > holds no control of its own …
  × … > MatchCard with a bar
  × … > MatchCard, no pick, with a bar
  × … > AppFrame with tabs, links and a card
```

```
AssertionError: MatchCard, no pick, with a bar: expected [ 'button > button' ] to deeply equal []
```

This is the mutation the comment I added at `MatchCard.tsx:87-95` exists for.

## 8. Things I want on the record, and one I got wrong first

**I do not disagree with the decided shape.** It is the right call, and the reasoning
survives contact with the code: the segment buttons inside a card are a duplicate
affordance for a detail the card's own click already provides, and a card cannot host
§13c anyway. If I had to argue for anything, it is only that "duplicate affordance"
understates it — inside a card they were not a duplicate but *dead*, and the honest
description is "controls with no listener". That makes the fix stronger, not different.

**The harness loses three sets of non-functional controls, and this is a concern for the
screenshot task, not a defect.** `harness/main.tsx:177, 184, 190` pass no
`onSegmentFocus`, so those three bare bars now render their labels as text. They were
already dead — nothing to report to. The **panel** states (cases 1, 2, 5, 6) go through
`ExplainerPanel`, which does wire the listener, so the interactive bar is still in the
screenshots. `LABEL_CLASS` is unchanged, so there is **no visual delta** in a screenshot
and no screenshot needs re-shooting for this. No prop was added or removed, so the harness
compiles exactly as before. The one real loss is fidelity of the demo: cases 3 and 4
demonstrate the bar without its affordance. If the screenshot task wants them faithful,
rendering those cases through `ExplainerPanel` would do it — that is a change for that
task, and I did not make it here.

**`nesting.test.tsx` is type-checked, and the harness is not.** `tsconfig.json` includes
`["src", "vitest.config.ts", "test-setup.ts"]`, so my new file is under `tsc` and the
harness is not. That is still Task C's concern 2, unchanged and still one devDependency
away.

**The one I got wrong first, recorded because the ledger keeps asking for it.** My first
pass at the control counts in the sweep was estimated rather than measured, and the
non-vacuity guard failed 7 of my own cases. I had assumed a bare `ProbabilityBar` still
rendered two buttons. It renders **zero** — which is not a bug, it is the point of the
change, and it is now pinned as `controls: 0` in the sweep. The guard did its job on me
before it ever had to do it on someone else, which is the argument for having written it.

## 9. What I did not touch

- `services/explainer` — not one line. Both pytest numbers above are before/after the same
  untouched tree.
- `MatchCard`'s click behaviour, styling, or any visual. `git show 08ecd16 --
  MatchCard.tsx` is **comment-only**: 9 added lines, all of them a JSX comment, zero
  changed lines. Verified, not assumed.
- The `onSegmentFocus`/`highlightKey` wiring on the panel, the market row, and
  `expandable`. Task C's work is untouched and still off by default.

---

# Task E — the test that covered nothing, and the harness no compiler read

Worktree: `/Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes`
Branch: `explainer-v2-phase3` — commits **`319be8b`** (item 1) + **`2001c93`** (item 2), base `b6ed7a3`

Status: **DONE_WITH_CONCERNS**. Both items are done, both mutations are caught, and no
baseline regressed. Three things need the controller's attention and none of them is
code I could fix without inventing behaviour: **§13c's third direction does not exist**,
**the type error in the hand-off was fixed one commit before my base**, and **this repo
has no CI on push or PR**, so the new typecheck is run by a person.

`HEAD` was checked before I started (`b6ed7a3`), before each commit, and after each
mutation. No reset landed on this worktree while I was in it. `services/explainer`:
`git diff --name-only b6ed7a3 HEAD -- services/` returns **0 files**.

## 10. Item 1 — what the test actually covered, and the direction that is not built

### The defect, stated more precisely than the hand-off states it

The hand-off's framing was "a test that asserts an interaction but not its result
proves the handler is wired, not that the interaction does anything". That is the right
pattern, and it is the third instance this session. But it is **not quite this test's
shape**, and saying so matters, because the fix differs.

`"links a factor to the figure it names, and clears on Escape"` already asserted
**results**, not a handler call: `data-highlighted="true"` on the tile and on the
segment, then `"false"` after Escape. So it was never a wiring-only test. What it
actually covered was **one direction of §13c's first affordance** — factor → tile and
factor → figure — and its blind spot was different from the one described:

**The panel's `onSegmentFocus` was never exercised at all.** The test clicked a
*factor* row, and a factor row is a `<button>` by §13c's own rule, independently tested
at `explainerV2.test.tsx:441`. The figures were only ever *read* by the test, never
*driven*. So the panel could have stopped passing `onSegmentFocus` entirely — the bar
would have rendered its labels as inert text and the panel would have said nothing —
and no panel test would have noticed. `ProbabilityBar`'s own tests cannot catch it
either, because they pass `onSegmentFocus` in themselves; they test the component's
branch, not the panel's choice of branch.

That is why mutation 2 (labels become `<span>`) left it green, and it is the thing the
strengthened test has to close.

### §13c's second direction is NOT implemented. Measured, not read off the source.

Spec §13c item 1 (`docs/superpowers/specs/2026-09-27-explainer-v2-design.md:620`)
says: *"Selecting or hovering a why row highlights the tile and the bar segment whose
market `key` it names… **Both directions highlight**, and clearing the highlight
restores the resting state."*

**"Both directions" does not mean figure → factor.** It means: from a factor, the tile
*and* the segment both light. I checked that reading against the plan doc
(`2026-09-27-explainer-v2.md:65`, `:785-786`), which is the same: the linkage is one
lookup from `key` to tile/segment, and `FactorList` is never given a highlight back.
So the second direction of that *sentence* is implemented, and my test covers it.

**The figure → factor direction — a reader stepping through the bar's figures and the
corresponding factor lighting up — is a separate affordance, and it does not exist.**
Task D's hand-off calls this "§13c's second direction"; the spec's own numbering calls
it §13c's *first item*, second direction. Both are the same thing, and the brief's
instruction to check it was the right thing to check.

I measured it with a throwaway probe (since deleted) that dumped the DOM after focusing
the `BAL` figure, which names the `spread` market:

```
PROBE after click, segment labels: [ 'KC=false', 'BAL=true' ]
PROBE after click, tiles:          [ 'tile-moneyline=false', 'tile-spread=true' ]
PROBE after click, factor rows: [
  'factor-moneyline=false aria-pressed=false',
  'factor-spread=false    aria-pressed=false'
]
```

The figure lights itself and lights its tile. **Neither factor row changes.** The cause
is structural, not a missed condition: `ExplainerPanel` owns `highlighted` and passes it
to `KeyNumberTile` (`:228`) and `ProbabilityBar` (`:241`), and `FactorList` **has no
prop that could receive it** — its props are `factors`, `onSelect`, `expanded`,
`onToggle`, `expandable`. The only `data-highlighted` on a factor row
(`FactorList.tsx:127`) is bound to `open`, which is *expansion*, not highlight; the row
also carries `aria-pressed={open}`, so expansion and highlighting are not even the same
signal in that component.

So: **the report is that §13c item 1's "both directions" is satisfied, and the
figure → factor link Task D was looking for is not in the spec's words at all, is not
built, and is not claimed anywhere in the code's comments.** I did not write a test
asserting it, per the brief. I did not write a test asserting it is *absent* either —
see below.

### What I did instead, and why the todo is a todo

`explainerV2.test.tsx`, in the `ExplainerPanel` block:

1. **The existing factor → figure/tile test gained its negatives.** It asserted the
   lit tile and the lit segment; it never asserted the *unlit* one. A panel that lit
   every tile and every segment satisfied it. It now also asserts `tile-moneyline` and
   `[data-seg="KC"]` are `"false"`, both before and after Escape.
2. **A second test drives the figures** — `"links a figure to the market it names, the
   other way round, and clears on Escape"` — and asserts the result: the figure naming
   `spread` lights `tile-spread` and itself; the one naming `moneyline` does not; Escape
   clears both. This is the test that closes the blind spot above.
3. **`it.todo` for figure → factor**, with the measurement in the comment.

The crossed fixture is the load-bearing part of (2) and (1): `SEGMENTS` maps
`{label:"BAL", market:"spread"}` and `{label:"KC", market:"moneyline"}`, so pairing a
figure to a tile **by label** or **by position** lights the wrong element and fails.
Without that, "the tile lights" proves only that some tile lit.

Two details I got wrong on the way and corrected, because both would have shipped:

- **I drove it with a raw `figure.focus()` first, and it introduced a new `act()`
  warning into the suite** — `focus()` is outside `act`, and the bar's `onFocus` calls
  `setHighlighted`, so React warned. The baseline had **zero** `stderr` blocks and I was
  not going to add one. Switched to `await user.click(figure)`, which `userEvent`
  wraps. `grep -c "not wrapped in act"` → **0**.
- **`user.click` turned out to be the better test anyway, for a reason I did not
  design for**: `userEvent` focuses what it clicks and will not focus a `<span>`, so
  `expect(figure).toHaveFocus()` fails on a figure that stopped being a control —
  an independent second catch. I verified the result assertion catches it *alone* (see
  mutation A2 below), so the test does not rest on the tag name.

**On the `it.todo`:** I did not write `expect(factorRow).toHaveAttribute(
"data-highlighted", "false")`. That test would pass today, and it would **fail the day
somebody implements the feature** — it would pin the gap shut and turn the correct fix
into a red suite. A `todo` states the spec's claim, shows up in the test count, cannot
pass while the claim is unmade, and cannot block anyone who makes it. If the controller
prefers the gap to be invisible in the suite entirely, deleting that one line is the
whole change.

### Item 1 mutations

**Mutation A1 — the panel's `onSegmentFocus` does nothing.** The brief's required one.

```diff
--- a/packages/predictor-ui/src/components/ExplainerPanel.tsx
+++ b/packages/predictor-ui/src/components/ExplainerPanel.tsx
-              onSegmentFocus={(_, market) => market && setHighlighted(market)}
+              onSegmentFocus={() => {}}
```

```
Tests  1 failed | 218 passed | 1 todo (220)
  × ExplainerPanel > links a figure to the market it names, the other way round, and clears on Escape
```
```
Error: expect(element).toHaveAttribute("data-highlighted", "true")
Expected the element to have attribute:  data-highlighted="true"
Received:                               data-highlighted="false"
 ❯ src/components/explainerV2.test.tsx:593
```

Exactly one test fails and it is the new one. It fails on the **tile staying dark** —
the result, not the shape.

**Mutation A2 — Task D's mutation 2, the panel's figures become plain text.** The named
defect of this item, run to confirm it is now closed.

```diff
--- a/packages/predictor-ui/src/components/ProbabilityBar.tsx
+++ b/packages/predictor-ui/src/components/ProbabilityBar.tsx
-  if (!onFocus) {
+  if (!onFocus || onFocus) {
```

```
Tests  8 failed | 211 passed | 1 todo (220)
  × no component in this library nests one control inside another > ProbabilityBar with a listener: its labels are controls again
  × no component in this library nests one control inside another > ProbabilityBar, three-way with a listener
  × no component in this library nests one control inside another > ExplainerPanel, v2, resting
  × no component in this library nests one control inside another > ExplainerPanel, expandable market row
  × ProbabilityBar > shows a 3% segment its label on focus, and keeps it a sliver
  × ProbabilityBar > makes the segment labels operable only for a caller that can be told about it
  × ProbabilityBar > is operable by keyboard alone, which is what catches a div with onClick
  × ExplainerPanel > links a figure to the market it names, the other way round, and clears on Escape
```

Task D measured **7 failed** for this mutation; it is 8 now, and the extra one is the
new panel test. It failed first on `expect(figure).toHaveFocus()` at line 589. To check
that this is not resting on the focus assertion, I re-ran the same mutation with **only**
that one line neutralised:

```
  × ExplainerPanel > links a figure to the market it names, the other way round, and clears on Escape
Error: expect(element).toHaveAttribute("data-highlighted", "true")
Expected the element to have attribute:  data-highlighted="true"
Received:                               data-highlighted="false"
```

So the interaction-not-doing-anything is caught on its own. Both mutations reverted with
`git checkout --`; `git diff --stat` after reverting showed **only**
`explainerV2.test.tsx`, and the suite returned to 219 passed.

## 11. Item 2 — the type error in the hand-off was already fixed

### The premise is stale, and the git trail says exactly when

**There is no type error at `harness/main.tsx:201`. There is no type error anywhere in
the harness.** I did not take that from the absence of output — I confirmed `tsc` is
reading the file first:

```
$ npx tsc --noEmit --listFiles | grep -c "predictor-ui/src"
17
$ npx tsc --noEmit --listFiles | grep "harness/main.tsx"
harness/main.tsx
```

`harness/main.tsx` is in the program, and behind it all 17 library `src` files. `tsc`
read the file and found nothing. (A check that returns nothing is not a check that
returns "no" — fourth time this session, and the reason I checked rather than believed.)

The error was real, and it was fixed **one commit before my base**:

| commit | `harness/main.tsx` | the `.factors` access |
|---|---|---|
| `3662248` (Task B) | `const NFL_VERDICT: Explanation = {` — the **union** | line **201**: `<FactorList factors={NFL_VERDICT.factors} … />` |
| `9bc096e` (Task C) | `const NFL_VERDICT: Common & Verdict = {` — the **v2 arm** | line 233, same expression |

At `3662248` the union had no `.factors` on the `LegacyExplanation` arm, so line 201
raised precisely `Property 'factors' does not exist on type 'Explanation'`. Task C fixed
it by annotating the fixtures `Common & Verdict` — and left a comment above
`NFL_VERDICT` (now `main.tsx:20-25`) explaining **exactly this**: *"On the union
`.factors` does not exist, so the fixture could not hand its own factors to the
standalone FactorList in state 9."* The import changed from `Explanation` to
`Common, Verdict` in the same commit. Line 201 today is a `<div>`.

So Task C fixed the type error as a side effect of the label work and did not report it,
and the hand-off carried the line number forward. **The devDependency gap was real and
is the thing that needed doing; the type error was already gone.**

### What I did

1. **`harness/package.json`** — `@types/react: ^19.2.17` (the exact range the library
   declares, resolving to the same **19.3.0** it already has installed) and
   `@types/react-dom: ^19.3.0`. The second could not be "matched" because the library
   declares **none** — its `src` imports only `react`, so it has no reason to;
   `@types/react-dom@19.3.0` is the React 19 counterpart of the `@types/react` that
   resolves today. `npm install` → `added 3 packages`. Verified installed:
   `@types/react 19.3.0`, `@types/react-dom 19.3.0`.
2. **`harness/tsconfig.json`** — new. The library's options minus the three test-time
   `types`, `noEmit` in the config as well as the script (so a bare `tsc -p .` in an
   editor cannot write `.js` next to the sources), `include: ["main.tsx",
   "vite.config.ts"]`. The library's own `include` is untouched, so `npx tsc --noEmit` in
   `packages/predictor-ui` is undisturbed — measured, exit 0 before, during and after.
   One non-obvious line, commented in the file: `types: ["react"]` is required, because
   `main.tsx:145` names `React.ReactNode` as a **type** without importing React, which
   resolves through the UMD global namespace. Drop it and the harness stops compiling for
   a reason unrelated to the harness.
3. **`typecheck` script** in the harness, and the README updated with the command, why
   the tsconfig is its own, and the measurement below.
4. **Not the library's manifest.** `predictor-ui/package.json` is byte-identical — the
   README's warning about the six silently-broken test files is the reason, and I did
   not go near it.

### Why the check earns its place: measured, with the defect reintroduced

```
$ npm run typecheck ; echo $?      →  2
$ npm run build     ; echo $?      →  0
$ cd .. && npx tsc --noEmit ; echo $?  →  0
```

**`vite build` cannot see a type error here** — it transpiles through esbuild, which
strips types without reading them, so a broken harness still builds a working `dist/`
that screenshots perfectly. The library's `tsc` cannot see it either, because the
harness is outside its `include`. Only the new script catches it. That is the whole
argument for this commit, and it is three exit codes rather than a claim.

### Item 2 mutation

The brief's mutation is "revert the `main.tsx:201` fix → the harness typecheck must
fail". **There is no such fix of mine to revert**, so I substituted the *original*
defect, which is a stronger test: I put the pre-Task-C annotation back, verbatim.

```diff
--- a/packages/predictor-ui/harness/main.tsx
+++ b/packages/predictor-ui/harness/main.tsx
-import type { Common, MarketTile, PickRef, Segment, Verdict } from "../src/index";
+import type { Common, Explanation, MarketTile, PickRef, Segment, Verdict } from "../src/index";
-const NFL_VERDICT: Common & Verdict = {
+const NFL_VERDICT: Common & Explanation = {
```

```
main.tsx(233,44): error TS2339: Property 'factors' does not exist on type 'Common & Explanation'.
  Property 'factors' does not exist on type 'Common & LegacyExplanation'.

MUTATED typecheck exit: 2
MUTATED build exit:     0
MUTATED library tsc:    0
```

That is the hand-off's error, reproduced character for character, at line **233** rather
than 201 (Task C's five-line comment above `NFL_VERDICT` moved it down). Restored with
`cp` from a backup taken outside the tree; `git diff --quiet -- harness/main.tsx` → clean,
`git status --porcelain` does not list it, and `npm run typecheck` → exit 0.

### Swept the rest of the harness — two findings, neither fixed

Both type-checkable harness files are in the program, so `tsc` exit 0 covers them.

1. **`vite.config.ts:6`'s `as any` is no longer needed.** With the `@types` present,
   `tailwindcss()` type-checks on its own — I removed the cast and `npx tsc --noEmit`
   exited **0**. So the harness carries an `any` that is currently suppressing a check
   that would pass, and nobody can tell that from reading it. **Not changed**: it is not
   an error, it is a refactor of a line I was not asked to touch, and one word of a cast
   is a reviewer's decision. It is reported here instead.
2. **The inline no-pick fixture (`main.tsx:202-213`) is the one fixture not annotated
   `Common & Verdict`**, so the file's stated convention is not applied to it. It
   type-checks only because it sits in a **contextually typed** position (`data={…}`),
   where `direction: "neutral"` infers its literal type from `Explanation` rather than
   widening to `string`. That is load-bearing and invisible: hoist that literal to a
   module-level `const` with no annotation and it fails to compile. Arguably good — it
   fails loudly — but the file's own comment claims the *annotation* is what makes a
   non-v2 fixture fail to compile, and this fixture has no such guarantee. **Not
   changed**, same reason as above.

### The finding the brief's step 3 cannot deliver

**This repo has no CI on push or PR.** `.github/workflows/` contains exactly one file,
`azure-static-web-apps-brave-moss-064ee9b0f.yml`, and its own header says it: *"Everything
runs on the VPS now: this Azure deploy no longer fires on push or PR. Run it by hand from
the Actions tab only if Azure is ever needed."* `on: workflow_dispatch: {}`.

So "caught by CI rather than by a screenshot" is not currently achievable, and I did not
fabricate a workflow to make the sentence true — an Azure deploy config is the wrong
place to bolt a typecheck onto, and turning that workflow into a push/PR trigger would
redeploy sites nobody asked to redeploy. What I could do is make the check exist, be
correct, and be one command, and say plainly in the harness README that **a person runs
it**. What is actually needed is one CI job that runs, on push and PR:

```
packages/predictor-ui:  npx vitest run && npx tsc --noEmit
packages/predictor-ui/harness:  npm ci && npm run typecheck && npm run build
services/explainer:      .venv/bin/python -m pytest -q
repo root:              node --test tests/*.mjs
```

That is a controller/Kevin call, and it is worth more than both commits in this report:
until it exists, every one of these four numbers is a number somebody remembered to
measure.

## 12. Commands, exactly as run, with the numbers I measured

Baselines, before I touched anything, on `b6ed7a3`:

```
cd packages/predictor-ui && npx vitest run
  → Test Files 10 passed (10) | Tests 218 passed (218)          exit 0
```

After both commits:

```
cd /Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes/packages/predictor-ui
npx vitest run
  → Test Files 10 passed (10) | Tests 219 passed | 1 todo (220)  exit 0
      (218 baseline + 1 new test. The 1 todo is item 1's figure -> factor, unbuilt.)
      grep -c "not wrapped in act"  → 0     (baseline was also 0; I did not add a warning)
npx tsc --noEmit
  → exit 0

cd harness
npm run typecheck
  → exit 0
npm run build
  → ✓ 34 modules transformed.  ✓ built in 164ms  exit 0
      dist/index.html 0.54 kB, dist/narrow.html 0.49 kB,
      dist/assets/states-B68YWAlj.js 240.49 kB, states-B32uGMBh.css 19.57 kB

cd ../../services/explainer && .venv/bin/python -m pytest -q
  → 235 passed, 1 warning in 1.28s

cd /Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes
node --test tests/*.mjs
  → tests 21 | pass 21 | fail 0
```

**218 did not regress — it is 219, plus 1 todo that is a claim nobody has built yet.**
235, 21 and both `tsc` runs are unchanged. I did not re-shoot the screenshots.

`pytest` run from `services/explainer` as instructed, and I did not once run it from the
repo root, so I never saw the 191 and did not have to reason about whether it was a
regression.

## 13. What I did not touch

- **No production code for item 1.** `git diff --name-only b6ed7a3 HEAD` is five files:
  `explainerV2.test.tsx`, and for item 2 `harness/{package.json, package-lock.json,
  tsconfig.json, README.md}`. **No `.tsx` component changed.**
- `services/explainer` — 0 files.
- The screenshots. Not re-shot, per the brief; the controller needs the clean tree.
- `harness/main.tsx` and `harness/vite.config.ts` — both back to byte-identical with
  `b6ed7a3` after the mutations.
- The unmade affordance itself. Wiring `highlighted` into `FactorList` is production
  code, it is a new prop on an exported component, and item 1 said test-only. It is
  reported, not built.

## 14. Carried forward

- **figure → factor does not exist.** Not a broken test, not a regression: a spec-shaped
  affordance with no implementation and no code comment claiming it. If it is wanted,
  it is a `highlighted` prop on `FactorList` (its `data-highlighted` is currently bound to
  *expansion*, and it also sets `aria-pressed={open}`, so highlight and expand are two
  different signals sharing one attribute — that needs deciding before the prop lands).
- **`@types/react-dom` was pickable only because Task C exported `Common` and `Verdict`.**
  Not a loose end, but it is the second time that export saved a type error, which is
  evidence the export was the right call.
- **No push/PR CI.** Four numbers, all hand-measured. This is now the largest unguarded
  thing in the repo, and it is larger than anything in either of my two items.
- `prompt_version` is still `v2`; the no-pick fix is inert for cached rows until Kevin
  bumps it. Unchanged, still his call.
- Task C concern 1 is still the top risk in the PR: a site may pass the *model's* probs
  as `legend`. Unchanged by this work.
