# Review fixes — `explainer-v2-phase3`

Worktree: `/Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes`
Branch: `explainer-v2-phase3` · base `main` · `origin/main` at `20c448b`
Date: 2026-09-27

**Nothing pushed, nothing merged, nothing deployed.** Six commits on top of the
merge of `origin/main`, listed at the end with SHAs.

| | before | after |
|---|---|---|
| `services/explainer` pytest | 235 passed | 235 passed |
| `predictor-ui` vitest | 228 passed, 1 todo | **237 passed, 0 todo** |
| `npx tsc --noEmit` | exit 0 | exit 0 |
| root `node --test` | 21 pass | 21 pass |

The baseline was measured on this branch *after* merging `origin/main` and before
any edit, and it matched the numbers I was given to beat.

---

## The merge

`git merge origin/main` — a merge commit, not a rebase, no force.

```
56b76f2 Merge remote-tracking branch 'origin/main' into explainer-v2-phase3
```

Clean, `ort` strategy, three files: `tokens.css` (the #15 scrollbar/caret theme),
`browserSurfaces.test.ts` (+219), and one screenshot. No conflict markers, nothing
of mine had to be adjusted, and all four suites are green on top of it. #15's own
9 tests are in the 237.

---

## Important 1 — a key with no figure behind it dimmed everything and lit nothing

**The review is right, and it is worse than "every control on a no-pick panel": on
a no-pick panel `record` and `context` are the two keys that can *never* resolve,
so the panel's only always-present controls all produce it.**

I measured it before changing anything, on a body shaped like `template.py`'s
output (no `pick`; factors `total`, `record`, `context`; a `total` tile and a
two-segment bar present, so the panel was not empty and *something* was linkable):

```
BEFORE fills opacity: ["1","1"]
BEFORE tiles highlighted: [ false ]
BEFORE segs highlighted: [ 'false', 'false' ]
BEFORE row data-highlighted: false
BEFORE aria-pressed: false

  AFTER  fills opacity: ["0.4","0.4"]
  AFTER  tiles highlighted: [ false ]
  AFTER  segs highlighted: [ 'false', 'false' ]
  AFTER  row data-highlighted: false
  AFTER  aria-pressed: false
```

The fills go to `0.4`, no segment and no tile lights, and the row the reader
pressed gives no sign of anything. One correction to the review's framing, in its
favour's favour: `total` and `btts` *are* linkable when the site passes a tile for
them, so the accurate statement is "`record` and `context` are unlinkable by
construction, and they are exactly the keys `template.py:164`, `:178` and `:184`
always emit on a no-pick bundle." The fixture I used carries a `total` tile
precisely so the test cannot pass by there being nothing linkable on the panel.

### The fix, in three parts

**1. Forward a key only if something can link to it.** `ExplainerPanel`:

```ts
const linkable = (key: string) =>
  tiles.some((t) => t.market === key) || !!segments?.some((s) => s.market === key);
const selectFactor = (key: string) =>
  setHighlighted((was) => (linkable(key) ? (was === key ? null : key) : null));
```

An unlinkable key **clears** the highlight rather than setting one. That is a
deliberate choice over the other two available readings, and it is what keeps the
row from being the thing `SegmentFigure`'s own comment is about — "a focus stop
that lies". Every row now means one sentence: *light the figure this row is about,
or clear the light if there is none to light.* A row with no figure under its key
turns a light off, which is a state change the reader can see and undo. The
alternative — rendering an unresolvable row as plain text so it is not a control —
was rejected: a reader cannot tell which of their rows have figures, and spec §6
item 4 says a *why* row is "still a row like any other: selectable, and
expandable". Both readings are written down at the branch.

**2. Pass the highlight into `FactorList`.** New optional prop `highlighted`.
`data-highlighted` and `aria-pressed` on a row now track *that* rather than
`expanded`. Expansion keeps its own `aria-expanded` control, so nothing is lost,
and a button's pressed state now says what pressing it did.

**3. Tests.** Three, one per wrong implementation, and the middle one exists
because "do nothing" is only safe if it is not nothing:

| test | pins |
|---|---|
| `dims nothing at all when the factor names a market this panel has no figure for` | `record` click → `dims` stay `["1","1"]`, nothing lit |
| `presses the row the reader selected, and de-emphasises only what it did not light` | `spread` click → `["0.4","1"]`, row pressed, sibling not |
| `takes the light back down when the next row names nothing, so no row is a dead control` | `spread` then `record` → the light goes out |

### Mutation evidence

Four mutations, each reverted. The first two were the pre-fix code exactly.

**(a) Forward the key unconditionally** — the review's reported defect, verbatim:

```
× ExplainerPanel > dims nothing at all when the factor names a market this panel has no figure for
  → expected [ '0.4', '0.4' ] to deeply equal [ '1', '1' ]
```

Exactly the measured `["1","1"] → ["0.4","0.4"]`.

**(b) Ignore an unlinkable key instead of clearing it** — the plausible wrong fix:

```
× ExplainerPanel > takes the light back down when the next row names nothing, so no row is a dead control
  → expect(element).toHaveAttribute("data-highlighted", "false")
  Expected: data-highlighted="false"   Received: data-highlighted="true"
```

This is the one that would have shipped a dead control on every no-pick panel.

**(c) Do not pass the highlight to `FactorList`** (`highlighted={null}`):

```
× ExplainerPanel > presses the row the reader selected, and de-emphasises only what it did not light
  → expect(element).toHaveAttribute("data-highlighted", "true")
  Expected: data-highlighted="true"    Received: data-highlighted="false"
```

**(d) Light the row by index instead of by key** (`i === 0`):

```
× ExplainerPanel > lights the factor whose key names the focused figure  → data-highlighted="true", got "false"
× ExplainerPanel > presses the row the reader selected, ...              → data-highlighted="true", got "false"
```

### One thing I did not expect, and had to handle

Passing `highlighted` into `FactorList` **completed §13c's third direction**. The
suite carried this:

```ts
it.todo("lights the factor whose key names the focused figure (spec §13c, direction two)");
```

whose comment said the direction "is not built" and that `FactorList` "has no prop
that could receive it". Both were true when written and stopped being true with
this change. A todo is the one line in a file somebody trusts without checking, so
it is now a real test, driven from a *figure* and matched by *market key*. That is
why the todo count went 1 → 0, and the test count went up by one more than the
three above.

---

## Important 2 — the band chip invented "Moderate" from an absent field

**The review is right, and its framing is the strongest argument for the fix: the
band was the only uncertainty in the file that failed open, and the failing-closed
footer is forty lines away in the same component's sibling.**

The fix is the review's:

```tsx
const word = band == null ? undefined : WORDS[band];
if (!word) return null;
```

The prop is widened to `Band | null | undefined` rather than kept as `Band`,
because the type is a promise about the service and the renderer is handed whatever
the service sent. `WORDS[band]` is `undefined` for a value outside the union, so
one guard covers the renamed value as well as the absent one — and both are tested.

### Mutation evidence

**(a) Restore the default** (`?? WORDS.moderate`) — the review's reported defect:

```
× a body the band cannot be read from > shows no confidence word at all when the body carries no band
  → expected <span …(2)></span> to be null
  Received: <span … data-testid="band-chip"> Moderate </span>
× a body the band cannot be read from > shows none for a band word this build has never heard of either
  → expected <span …(2)></span> to be null
```

**(b) Show nothing ever** (the "just return null" over-correction) is caught by the
pre-existing `pre_kickoff` test, which asserts the chip reads "Strong". So the guard
is pinned from both sides: absent → nothing, present → the word.

The first test also asserts `not.toMatch(/leaning|moderate|strong/i)` over the
whole document, so the fix cannot be "render the chip with no text", and that the
verdict line still renders — failing closed on the claim, not on the panel.

---

## 3. `<button><ProbabilityBar onSegmentFocus={…} /></button>` in `CASES`

**I disagree with one factual claim in the review, and the disagreement is the
finding. "It passes today" is not true — it fails, twice, and the reason it fails
is a real hole in the PR's own reasoning.**

The case was added exactly as written and run before anything was changed:

```
× no component in this library nests one control inside another
  > a button wrapping a bar that has a listener
  → expected [ Array(2) ] to deeply equal []
  + "button > button"
  + "button > button"
```

with React's own warning behind it, and the tree showing `<SegmentFigure …>` having
rendered a `<button>`.

`SegmentFigure`'s comment claimed the unsafe answer was "unreachable by accident",
because the branch is derived from `onSegmentFocus` rather than from a prop:

> *a caller that wraps this bar in a button and forgets a flag gets plain text*

That is true of a caller that passes **no listener**. It was never true of a caller
that passes one, because **a component cannot see its own ancestors** — and the
combination (inside a control *and* somebody listening) is exactly the one nothing
in this library renders today, which is why it survived. `MatchCard` is safe from
it only because a card has no `FactorList` and so never has a listener.

So I did both halves:

- **Narrowed the claim** in the comment to what it is true of, and said plainly that
  "unreachable by accident" was too wide.
- **Added `insideControl`** (default `false`, so no existing call site changes),
  which makes every label text and suppresses the market row's disclosure — the
  disclosure cannot exist inside a control, so the figures stay *open* rather than
  hidden behind a button the caller may not render. Nothing is withheld.
- **Added the case to `CASES`** with the annotation, `controls: 1` — one, not three.
  It fails on the arithmetic before anyone reads the fault list.
- **Added a companion test** asserting the *un*annotated shape is a fault, with the
  real component: `["button > button", "button > button"]`. Deliberately **not** in
  `CASES`, which asserts "no faults" — a case reporting a rule is not a case
  obeying it, and putting it there means either a permanently red suite or an
  exception the next person reads as permission. That test also asserts React says
  the same thing, and swallows the log — a suite that prints a nesting warning on
  every run teaches everyone to ignore nesting warnings, which is how the first one
  of these sat in the tree through three tasks.

**What I did not do:** put `insideControl` on `ExplainerPanel`. The panel is a
labelled `<section>` landmark and renders four kinds of control of its own;
suppressing them would gut §13c, and a caller who nests a landmark inside a button
has a defect this library cannot defend against. The nesting test's own docstring
already carries that limit ("It does not look at a consuming site's own markup"),
and I have not widened the claim.

---

## 4. The `prompt_version` deploy precondition, in the spec

New **§13f**, immediately after the §13e ruling, plus a cross-reference from §5b
(whose `prompt_version` sentence was about a *shape* change and left the *writer*
case implied). Full text:

> ### 13f. Deploy precondition: the `prompt_version` bump ships WITH the renderer
>
> **Adds to** §5b rather than overriding anything, and sits here because it is the
> requirement a person meets immediately before they deploy. The rest of §13 changes
> what the code should do; this one changes what the deploy must do, and a code
> review cannot enforce it, which is exactly why it is written down where the deploy
> is planned.
>
> **A deploy that changes how a response is *written* must move `prompt_version` in
> the same deploy. A PR that changes it is not optional housekeeping, and it is not
> the deploy's problem to remember.**
>
> §5b said the version is bumped so v1 prose cannot be read by a v2 renderer. That
> was about a *shape* change. This is the other case, and the cache makes it just
> as real: **the cache key covers `prompt_version`** (`cache.py:23`, and
> `service.py:158` builds it from `s.prompt_version`), and a row is served verbatim
> on a hit — `_answer` spreads `row["body"]` and re-derives only `band`, `pick` and
> `pick_timing`. So a body written before the deploy keeps being served, verbatim,
> for as long as its facts render to the same JSON.
>
> **The consequence, named.** Every change this design makes to the *generated
> body* — and that is where all of §5a's rules live, since `verdict` and `factors`
> come out of the cache while only `band` and `pick` are re-derived per read — is
> **inert in production** until the version moves. Specifically, without the bump:
>
> - A pre-deploy row for a **no-pick** bundle still carries `direction: "up"` on
>   every factor, because `contract.py:129` coerces an unrecognised direction to
>   `"up"` and `template.py` had no `_toward`. The new renderer then draws an up
>   triangle in the win colour and says "FOR THE PICK" beside a match with no pick
>   — the exact defect §5a's `neutral` and the no-pick wording rules remove. The
>   fixes are correct and never run.
> - An **`llm`** row is not retried at all: `_usable` only gives a retry window to a
>   template written while the model was unavailable, so it survives until its
>   **facts change**, and the key includes `facts_json`.
> - **The cache is not empty and a no-op deploy is not visible from outside.** §4
>   keeps the cache (a second open of a fixture is free), so every fixture a reader
>   has already opened holds a row, and those rows are written by the pre-deploy
>   writer. The panel then renders them without a regeneration, which means the
>   defect is not "some fixtures are stale" — it is "the fixtures readers have
>   already looked at are the stale ones", and the ones a reader opens next are the
>   ones that get fixed.
>
> **What the deploy has to do.** Move `prompt_version` off `"v2"` — any new string
> will do, and `"v3"` is the obvious one — in the same change that deploys a new
> writer. It costs one generation per cached row, which is the point: it is the
> price of the prose changing.
>
> **Why the bump is not in the renderer PR.** It spends the model budget, and
> budget is a deploy decision, not a reviewer's: a PR that bumps the version to
> prove its own renderer works spends real generations on rows nobody has asked for
> yet. So the requirement lives here, next to §13e, and the person who deploys
> meets it before they deploy rather than after a reader does.

Every claim in it is verified, not assumed. `config.py:33` is `"v2"`, and the
`v1 → v2` bump is **already on `main`** (`98b8990`, an ancestor of `origin/main`),
so `"v2"` rows exist in production already — this is not a version that has never
shipped. `origin/main`'s `contract.py:129` does coerce an unrecognised `direction`
to `"up"`, and `origin/main`'s `template.py` has no `_toward`. `service.py:158`
builds the key from `s.prompt_version`; `service.py:107-130` re-derives only
`band`, `pick` and `pick_timing` on a hit; `service.py:132-140` is where `_usable`
gives its retry window.

`config.py` is **not** touched. The bump spends the model budget and is a deploy
decision.

---

## 5. The narrow-surface fallback — left as a prop, and the ruling is written down

**I do not think a CSS-only solution is clean here, so the prop stays. The
reasoning is now at the prop, so the next person does not re-open it without
measuring first.**

The hazard is real: `expandable` is opt-in, so a site that forgets it gets a row
that collides at 260px. It is also the one place this component is not derived
from a signal it already receives — which is exactly the critique. Three CSS
answers, each measured against the spec:

- **`clamp()` — out on §6a.** The spec says the market row "does not get a smaller
  size to make a row fit, it drops the row", and the 12px floor is a *test* in both
  consuming repos (`craft-floor.test.ts` in Sports_Predictor, `hub.test.mjs` in the
  Hub). So `clamp()` is not a style preference without teeth; it is a floor those
  suites assert.
- **A container query that hides the figures — out on §13c.** It fixes the
  collision, but CSS cannot add the control that brings them back, so on a narrow
  surface it withholds data with no way to reach it. The disclosure has to be a
  real element; that is the whole reason the fallback is a `<button aria-expanded>`
  and not a `hidden` attribute.
- **A container query that reflows instead (`flex-wrap`, or the cells stacking) —
  out on §6 item 3.** Nothing is hidden, so nothing is withheld, and the floor
  holds. But it breaks the one thing the row exists for: §6 item 3 requires each
  figure to sit "in the column of the figure it is being compared with", and a
  wrapped row puts two outcomes on one line and one on the next. At 260px with
  three outcomes there is no layout that keeps three 12px figures in three columns.
  Something has to give, and §13c item 4 already chose what.

What is left is a prop to remember, whose default is the *safe* one: off means the
figures are shown. The failure mode of forgetting is a collision at 260px — a
layout defect a screenshot catches — and not withheld text, a dead control, or a
claim. §13c item 4's own wording ("opt-in and open by default") is unchanged; I
have not touched the spec on this point, only the code comment that carries the
argument.

---

## 6. The harness check is parsed now, and the regex was worse than a lint

**The review is right, and the specific mechanism it named is worse than it sounds:
the comment-strip deletes *code*, so it can delete the violation it was looking
for.**

The old check was `readFileSync(...)` plus two `replace`s plus two regexes. I
measured the failure it cannot see, on the real harness, in memory:

```
raw file really contains the violation : true
  ... on line 99 of 242
stripped file still contains it        : false
OLD check reports a violation          : false
lines raw / after the strip            : 242 / 178
```

One ordinary string above the offending tile, holding an unpaired `/*` — a note
about how the market row is drawn, written as prose. The strip pairs it with the
next `*/` anywhere in the file and removes **8,120 characters and 64 lines**,
including `label: "btts"`. The assertion then passes over a file that has the
defect, silently, and the suite is green. The paired case (`/* … */` wholly inside
one string) is harmless; the unpaired one is not, and nothing in the file or the
test distinguishes them.

`harness/main.tsx` is now parsed with `typescript`, already a devDependency of
this package. `ts.createSourceFile` with `ScriptKind.TSX`, and the question becomes
"what string does this `label` property hold" rather than "does this text look like
it would". It also reads things the regex saw only by accident of layout: **JSX
text** and **no-substitution template literals**, both of which reach a reader. The
key check is now equality against a collected list, so the diagnostic names the
offending value, and the non-vacuity half (`"Both teams score"`, `"Over 2.5 · 56%"`
are present) is asserted against that same list.

**Mutation evidence.** `label: "Both teams score"` → `label: "btts"` in the harness:

```
× no raw key, and no bare O, reaches a reader > never hands a market key to a tile's label or to its sub line
  → a tile label or sub line holds the raw key "btts":
    expected [ 'BAL', 'Moneyline', 'Spread', …(26) ] to not include 'btts'
```

Harness restored afterwards; `git diff` on it is empty.

**What this still does not cover, stated rather than glossed:** it covers the
harness, not a site. The review's point that "it covers nothing about any real
site, which is where a key would actually reach a reader" is still true after the
parse — parsing a fixture cannot reach another repo. The durable home for the
site-level form of the rule is the consuming site's own fixture test, beside
`craft-floor.test.ts`, and that is a phase-4 wiring task. I did not move the check
to oxlint; the review offered that as an alternative, and the parse keeps it in the
suite where it can assert both halves (no key, and the words that replaced it).

---

## 7. `RecordStrip` with `hits: null, settled > 0` — a decision, and it is the dash

**I took the second option: the dash stays, and the reason is now written at the
branch with a test that makes it a decision rather than a fall-out.**

The trade-off is real and I am not going to pretend otherwise — this throws away a
68 the caller did hand over, and `—/68` would show it. What decided it:

- **`hits` and `settled` are two fields of one `record` object**, not two
  independent facts. `facts.py:29` types it as one `dict | None`; every fixture in
  the service's own tests carries both; and `template.py:159` refuses to write a
  record row at all unless both are present. So `hits: null` does not mean "a record
  missing its numerator" — it means an object this component cannot read, and
  quoting its denominator while withholding its numerator asserts that one of the
  two is sound when the only thing known is that the object is not.
- **It is the same mistake as drawing the bar 0% wide**, which the component
  already refuses to do.
- **There is an accessibility cost.** `—/68` announces as "em dash slash
  sixty-eight" — precisely the run of glyphs the bar's own `"41 of 68"` accessible
  name exists to avoid, in a file whose docstring is entirely about that.

**What would change the ruling**, written down: the service emitting a partial
record deliberately, or the facts guaranteeing `settled` independently of `hits`.
Neither is true today, so there is no partial here to be honest *about*.

### Mutation evidence

Showing the partial instead (`${hits === null ? "—" : hits}/${settled}`):

```
× RecordStrip > shows a dash for a record it cannot read, and never quotes half of one
  → Unable to find an element with the text: —
  <span aria-label="null of 68" role="img" …>
```

Note the mutation also produced `aria-label="null of 68"` — the string `null` read
as a number. The test asserts the dash, that no `68` appears, and that no bar is
drawn.

---

## Commits

`56b76f2` is the merge of `origin/main`; the rest are mine, in order.

| SHA | |
|---|---|
| `56b76f24808c85ab64dc9ec71ebac72ac4fa7c89` | Merge `origin/main` into `explainer-v2-phase3` |
| `49eec8692ab564e9d6ded04c579650b401ce359b` | fix(predictor-ui): a key with no figure behind it must dim nothing, and the band must not be invented |
| `934c5f59049eaaa5e4f1930a6bde7608162a5e1d` | test(predictor-ui): parse the harness, decide the partial record, and rule on the narrow fallback |
| `cbaabbc52eb2c1ae654d5e2fc2e37822a0f9aa81` | docs(spec): the `prompt_version` bump is a deploy precondition, and it ships with the writer |
| `0d2c4ef54c3648acc47cbf3624213ef843baea05` | test(predictor-ui): the figure → factor half of §13c is built, so the todo is a test |
| `6da91b4eb2373d22bd1df9660bad12ac0db1a04b` | docs(predictor-ui): drop a stray doc comment I pasted onto the wrong prop |

Every commit message ends with exactly
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Explicit paths staged
only; `git status` shows three untracked files that were already there
(`progress.md`, `task-4-wiring-report.md`, `task-c-report.md`) and that I have
deliberately not added.

**Not done, as instructed:** no push, no merge, no deploy. `config.py:33` is
untouched at `"v2"` — §13f names what the deploy must do and the bump stays a
deploy decision.

---

## Verification — exact output

### `packages/predictor-ui` — `npx vitest run`

```
 RUN  v2.1.9 /Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes/packages/predictor-ui

 ✓ src/browserSurfaces.test.ts (9 tests) 11ms
 ✓ src/fmt.test.ts (21 tests) 29ms
 ✓ src/tokens.test.ts (12 tests) 8ms
 ✓ src/components/atoms.test.tsx (15 tests) 142ms
 ✓ src/components/frame.test.tsx (7 tests) 212ms
 ✓ src/components/card.test.tsx (24 tests) 258ms
 ✓ src/components/explainer.test.tsx (21 tests) 176ms
 ✓ src/components/nesting.test.tsx (35 tests) 159ms
 ✓ src/teamColors.test.ts (33 tests) 10ms
 ✓ src/components/table.test.tsx (3 tests) 102ms
 ✓ src/components/explainerV2.test.tsx (57 tests) 378ms

 Test Files  11 passed (11)
      Tests  237 passed (237)
   Start at  21:21:26
   Duration  2.26s (transform 667ms, setup 1.08s, collect 3.22s, tests 1.48s, environment 6.78s, prepare 878ms)
```

No `todo` in the run: the last one became a real assertion.

### `packages/predictor-ui` — `npx tsc --noEmit`

```
exit=0
```

### `services/explainer` — `.venv/bin/python -m pytest -q`

Run from `services/explainer`, where `asyncio_mode = "auto"` lives.

```
235 passed, 1 warning in 1.03s
```

(The one warning is the pre-existing `StarletteDeprecationWarning` from
`fastapi/testclient.py` about `httpx`/`httpx2`. It is present on `main` too.)

### root — `node --test tests/*.mjs`

```
ℹ tests 21
ℹ suites 0
ℹ pass 21
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 546.07425
```

---

## Where I think the review was right, wrong, and thin

- **Important 1: right**, and the mechanism is worse than stated — the keys that
  can *never* resolve (`record`, `context`) are the ones the no-pick panel always
  shows. One nuance in the review's favour's disfavour: `total` and `btts` *do*
  link when the site passes a tile, so "every factor is one of
  `record`/`context`/`total`/`btts`" is right about the key set and the *always
  broken* subset is `record`/`context`.
- **Important 2: right**, and the strongest version of the argument is the one in
  the prompt — the band is the only uncertainty in that component that fails open,
  and the footer that refuses to is forty lines away.
- **3: the finding is right, the prediction is wrong.** "It passes today" is false;
  it produces two `button > button` faults. That is not a quibble — it is the
  discovery, and it means `SegmentFigure`'s "unreachable by accident" claim was too
  wide. I narrowed the claim and added the prop the guarantee actually needed.
- **4: right, and understated in one direction** — the `v1 → v2` bump is already
  on `main`, so production already holds `v2` rows. The inert-ness is not
  hypothetical.
- **5: the hazard is real and the CSS-only fix is not clean.** `clamp()` is ruled
  out by a floor two repos test for; a container query either withholds the figures
  or breaks the column alignment the row exists for. Prop left, ruling written.
- **6: right, and the failure mode is worse than a lint** — the strip deletes
  8,120 characters of real source in the case I measured, and the check then passes
  over a file that has the defect. It still does not cover a real site; that is a
  phase-4 task, stated rather than papered over.
- **7: "honest, but thin" is a fair description, and the fix is the comment.** I
  did not show `—/68`, and the reason is not "the dash is nicer" — it is that
  `settled` and `hits` are two fields of one object, so quoting one while
  withholding the other claims the object is partly sound. The cost of that call is
  written down, along with what would reverse it.
