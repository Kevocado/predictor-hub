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
