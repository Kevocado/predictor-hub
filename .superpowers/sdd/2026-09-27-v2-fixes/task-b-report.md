# Task B — the renderer (TypeScript)

Worktree: `/Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes`
Branch: `explainer-v2-phase3` (PR #13)
Commit: **`3662248`** — *fix(predictor-ui): the accent is the pick, and a neutral factor claims nothing*
Scope: `packages/predictor-ui` + the spec. **`services/explainer` is untouched** —
`git diff 1fb1bdf..HEAD --name-only | grep services` → nothing.

**Status: DONE_WITH_CONCERNS.** The three items are done and proved by mutation.
The concerns in §7 are not defects in this change; two of them are things this
task found that nobody has claimed yet, and one of those is a type error that has
been sitting in the harness.

---

## 1. Every change, file:line

### `src/components/ProbabilityBar.tsx` — the emphasis now follows the pick

| line | change |
|---|---|
| `:21` | `export type PickRef = { label: string; side?: string }` — the wire `pick` from `contract.pick_for`. Not named `Pick`: that shadows the built-in utility type in every file that imports it. |
| `:25` | `const ACCENT` — the one colour that means "this is the pick", extracted from the old `FALLBACK_2[0]` so the claim about it is one line. |
| `:27-40` | `FALLBACK_2` / `FALLBACK_3` deleted; `NEUTRALS` is the three-step neutral ramp, most prominent first. |
| `:47-50` | `fill(color, emphasised, rank)` — the same 1.6:1 team-colour rule, unchanged and evaluated **first**, so a legible team colour still wins. Only when it does not: accent if this is the pick, else the ramp. |
| `:52-59` | `pickIndex` — `segments.findIndex(s => s.label === pick.label)`, `-1` for no pick **and** for a pick whose label matches nothing. |
| `:61-78` | `tones` — one tone per segment; the ramp is walked by the segments that are **not** the pick. |
| `:112`, `:129` | new `pick?: PickRef \| null` prop, default `null`. Optional, so the pre-panel call sites compile and render unchanged. |
| `:140` | the bar's accessible name gains `, the pick is BAL` **only** when the pick matched a segment. |
| `:157` | `backgroundColor: fills[i]` replaces `fill(s.color, i, segments.length)`. |

### `src/components/ExplainerPanel.tsx`

| line | change |
|---|---|
| `:8`, `:15` | `Verdict` gains `pick?: PickRef`. The v1 branch is untouched: the bar only renders under `v2`, and `:229` passes `data.pick` only then. |
| `:179-190` | the comment above the band chip, and `{v2 && !rebuilt && <BandChip …/>}` — **item 5**, the whole decision in one line. |
| `:229` | `pick={v2 ? data.pick : null}` — the answer's pick, handed down. The panel never works one out. |

### `src/components/FactorList.tsx` — a neutral row claims nothing

| line | change |
|---|---|
| `:30` | `direction: "up" \| "down" \| "neutral"`, with §5a quoted. |
| `:49-60` | `MARK: Record<Factor["direction"], "up" \| "down" \| null>` — the mark keyed by the whole union. `neutral: null`. |
| `:61-69` | `TONE: Record<…>` — `up` → `text-pr-win`, `down` → `text-pr-loss`, `neutral` → `text-pr-text-faint`. |
| `:83` | `WORDS.neutral = "context"`. |
| `:113`, `:118-122` | `const mark = MARK[factor.direction]` replaces `const up = factor.direction === "up"`; the gutter span is always 14px wide so a neutral row's words still line up, and it holds no mark. |

The button and the expansion are **not** touched: same element, same handlers,
same `aria-expanded` — a neutral row is a row.

### `src/components/MatchCard.tsx:87`

`pick={pick ? { label: pick.label } : null}` on the card's bar. One line, and
without it the family card would have quietly *lost* the emphasis it used to
have — for the right reason (order-based emphasis was wrong) and with nothing put
in its place. See §3.

### `src/tokens.css:21-30` and `index.html:32`

`--color-pr-fill-mute: #5e6775` — one new rung, and `index.html` because
`tests/hub.test.mjs:28` fails on any drift between the file and the inlined
tokens. Reasoning in §2.

### `src/index.ts:5` — `type PickRef` exported.

### Spec — `docs/superpowers/specs/2026-09-27-explainer-v2-design.md`

- `:240-250` — §6 item 3 (split bar): the accent marks the pick and nothing else;
  joined by `pick.label`; **no pick, no accented segment**; an unmatched pick
  accents nothing; non-pick segments walk a three-step neutral ramp.
- `:251-258` — §6 item 4 (why boxes): a `neutral` factor draws no arrow, wears
  neither win nor loss colour, is labelled "context", and is still selectable and
  expandable.
- `:663-693` — **§13e, the item 5 ruling with its reasoning**: a rebuilt pick
  shows no band; the band is a claim about how much to trust a number a model
  produced after it had seen the score, and the panel is telling the reader two
  lines below not to count or grade it; it is withheld rather than softened; it
  fails closed; and the band stays computed and in the response so the value is
  still available, because the band is not *wrong*, it is unsayable *here*.

### Tests

- `src/components/explainerV2.test.tsx` — three new describes: **the pick is the
  accented segment** (`:162`, 8 tests), **a factor with no direction** (`:304`, 4
  tests), **a rebuilt pick's band** (`:459`, 2 tests), plus two panel-level tests
  (`:434`, `:442`). Fixtures `NFL_BAR`, `PL_BAR`, `fills()`, `ACCENT`, `NEUTRALS`
  at `:57-79`.
- `src/components/card.test.tsx:90-118` — **the match card's bar**, 3 tests.
- `src/components/card.test.tsx:77-88` — a comment added to the existing
  "fallback fills" test; **no expectation changed**. See §4.
- `src/tokens.test.ts:51-62`, `:63-75` — the ramp is three deep, ordered, and
  above the 1.6:1 fill floor; the new token is held to the fill bar, not the text
  bar, and at `:72` is asserted *not* to be named `text-*`.

22 new tests. 148 → **170**.

---

## 2. The three-way palette, and what I rejected

This is the decision I spent the most time on, so here is the whole reasoning.

**The constraint.** Requirement 2 (no pick → nothing emphasised) and requirement 4
(a three-way bar keeps three distinguishable tones) collide, because
`FALLBACK_3 = [accent, faint, dim]` spends the accent on distinctness. Once the
accent means "this is the pick" and there is no pick, a three-way bar needs
**three distinct tones, none of them the accent**.

**What I chose.** The pick gets the accent; the segments that are not the pick
walk a three-step **neutral ramp**: `--color-pr-text-dim` (9.3:1 on the panel),
`--color-pr-text-faint` (6.2:1), `--color-pr-fill-mute` (3.1:1, new). The ramp is
walked by the non-pick segments *in the order they appear*, so the draw gets its
own tone whatever the pick is:

```
pick = Arsenal → [accent, faint, mute]     pick = Draw    → [dim, accent, faint]
pick = Chelsea → [dim, faint, accent]     no pick        → [dim, faint, mute]
```

Three distinct tones in every case, and the two segments that are not the pick
never share a grey.

**The third rung did not exist, and that is the interesting part.** The candidates
in the current palette, measured against the panel (`#151920`) with the repo's own
`contrast()`:

| candidate | on panel | verdict |
|---|---|---|
| `--color-pr-text` `#f3f5f8` | 16.1:1 | **Rejected.** It is 3.4× brighter than every sport accent (NFL blue is 0.28 luminance, this is 0.91) and 3× brighter than the label printed under the segment that names it. A near-white segment between two greys reads as the marked one — the *same* defect as "the first one is", wearing a different hat. |
| `--color-pr-rule` `#2b333f` | 1.4:1 | **Rejected: below the 1.6:1 fill floor**, which the comment at `ProbabilityBar.tsx:42-45` states as deliberate. I did not move the floor. |
| `--color-pr-panel-2` `#1d232c` | 1.1:1 | **Rejected:** effectively invisible on the panel. |
| `--color-pr-win` / `loss` / `lean` | — | **Rejected outright.** The old comment already banned good/bad green/red, and a green segment beside grey would say "right", which is a claim about the outcome. |
| a new rung, `--color-pr-fill-mute` `#5e6775` | 3.1:1 | **Chosen.** |

So this is **one new token**, and the argument that it is not "a new palette" is
that it is a third rung on a neutral scale that already had three usable rungs
(`text-dim`, `text-faint`, and the accent the bar was borrowing). The bar's palette
is not new; it is purified — the distinctness job and the emphasis job were sharing
one colour, and now they do not. §6a says "no new palette, no new typefaces": this
is one grey, no new hue, and nothing about type. **If you would rather have zero new
tokens, the fallback is to use `--color-pr-text` for the third rung and accept the
bright-segment reading; I do not recommend it, and the tokens test in
`tokens.test.ts:51` is what will stop the ramp from being quietly reordered later.**

Two things about the new token I made explicit in tests rather than in prose:

- It is named for what it paints (`fill-`), not `text-`, because it sits below the
  4.5:1 text bar and a token named `text-mute` would get used as a text colour.
  `tokens.test.ts:72` asserts `css` never grows `--color-pr-text-mute`.
- It is pinned to the same ≥3:1 band the spec already sets for a sport accent on
  the panel, and asserted `< 4.5` so it can never be mistaken for a text tone.

**What I rejected for the mechanism.** Emphasis by *opacity* (paint every segment
the same and dim the non-picks) would have worked alongside team colours, but the
`opacity` channel is already `dim()` for §13c's market highlight, the two would
multiply, and an opacity-only emphasis is invisible to assistive tech. A 1px accent
ring on the pick's segment would keep both team colours and add an emphasis, but a
1px mark on a 10px-tall bar is not an emphasis a reader sees. Both rejected in
favour of one mechanism with one rule.

**The honest limit, pinned rather than hidden.** When **both** segments carry a
legible team colour, neither gets the accent: a team's colour is a fact about the
team, and overpainting it to mean "the pick" puts a second claim on top of the
first. The pick is named in the bar's accessible name instead
(`ProbabilityBar.tsx:140`), which is the same rule `FactorList.tsx:9-15` states
about its triangles. `card.test.tsx:93-102` and
`explainerV2.test.tsx:199-225` assert both halves of this, so nobody later "fixes"
it by overpainting a team colour.

---

## 3. Two changes beyond the literal brief, and why

**1. The pick is in the bar's accessible name.** The accent is a colour, and this
repo treats colour-only meaning as a defect (FactorList rule 1, §6c). A reader who
cannot see which segment is tinted, or is in greyscale print, was being told the
split and not the pick. `ProbabilityBar.tsx:140` appends `, the pick is BAL`, and
only when the pick actually matched a segment — the two pre-panel call sites that
pass no pick see a byte-identical name, which is why the existing name assertions
(`card.test.tsx:11`, `explainerV2.test.tsx:85`, `:92`) still pass untouched.

**2. `MatchCard` passes its pick down** (`MatchCard.tsx:87`). Not asked for, and I
would rather flag it than leave it: the card's bar is the same component, so the
same defect was live there — and my change would have made that bar *lose* its
(incorrect) emphasis without gaining the correct one. With a pick it now follows
the pick; with a card whose pick label is not one of the bar's segments
("Aston Villa win" against segments "TOT"/"AVL") it accents nothing, which
`card.test.tsx:110-118` pins. Three tests, one line of source.

---

## 4. Existing tests I changed, and which were wrong

**I changed no existing expectation.** Every one of the 148 pre-existing tests still
passes, and two of them were load-bearing on the old palette. What I did instead was
add a comment saying what changed underneath them:

- `card.test.tsx:78-88` "gives home, draw and away three different fills when no
  team colours are known" — its **values** changed (accent/faint/dim → three
  neutrals) and its **assertion did not** (three distinct tones). The test was not
  wrong: it asserted distinctness, which is still exactly right. What was wrong was
  the palette it was reading, and the comment now says so, including *why* the
  accent is no longer in it.
- `card.test.tsx:59-66` "swaps a team colour that would vanish on the panel" — the
  1.6:1 rule is untouched and it passes. Nothing added; it is the test that would
  have caught a regression in §2's first branch.
- `explainerV2.test.tsx:85`, `:92`, `card.test.tsx:11` — the bar's accessible name,
  unchanged when there is no pick.
- No test asserted the band chip on a rebuilt pick, so item 5 broke nothing
  (`explainer.test.tsx:165-220` is all v1 fixtures, and `v2` is false for those).

The only expectation I wrote *after* seeing my own output and then had to justify is
`tokens.test.ts:69` (`fill-mute ≥ 3:1`): my first hex `#5b6472` measured 2.946:1
and the test failed. I moved the hex rather than the bar, because the 3:1 figure is
the spec's own number for a colour that must be visible on the panel.

---

## 5. The neutral wording: `context`

`WORDS.neutral = "context"` (`FactorList.tsx:83`). It renders as
`ITS RECORD SO FAR · CONTEXT` beside the headline, one word, in the same slot as
"for the pick" and "against it".

**Why this one.** A neutral row is a *statement*, not an argument, so the word has
to be a category rather than a direction — which is exactly what the brief asked
for. "Context" is true of every row the contract now emits as neutral: the total
("It projects 2.7 goals against a line of 2.5"), both teams to score, the record
("41 of 68 have landed"), and the padding rows ("So there is little to weigh up
here"). It never names a pick, so it is safe in the no-pick state — the whole point
of item 2. And it is one word, so the three labels sit together as a set rather
than one of them being a sentence.

**What I rejected, and why:**

- **`neutral`** — the wire value, and the obvious choice. Rejected: in this
  product's own copy "neutral" is a verdict on an outcome (the band vocabulary is
  leaning/moderate/strong, the statuses are Called it / Missed / Leans), so a row
  about the projected total labelled NEUTRAL would read as "no edge here" — which
  is a claim about the pick, in a panel that has just been told there is no pick.
  It also would have made the reader learn a second vocabulary for a word the API
  already uses for a third thing.
- **`not for or against`** — accurate, and it is the phrase Kevin quoted. Rejected
  because it re-names the pick in exactly the state where there is none, and
  because it is a clause in a slot that holds one word. The honest version of
  this label is the *absence* of a claim, and a word is a poor way to be absent.
- **`either way` / `neither way`** — claims the row cancels itself out. The total
  does not; it is a number the reader may want. A label that over-claims is the
  failure mode this panel is built against.
- **`no lean`** — borrows the band vocabulary (and the `--color-pr-lean` token),
  and reads as a claim about the pick's strength.
- **`for reference`** — already the panel's wording for "shown but not counted"
  (`ExplainerPanel.tsx:197`). Reusing it would blur two different warnings into
  one word: *this is background* and *do not act on this* are not the same message,
  and the second is the more urgent.

The reasoning is in the source at `FactorList.tsx:73-82`, not only here, so it
survives the next reader.

**The trap, and why the fix is the comparison and not the type.** `MARK` and `TONE`
are `Record<Factor["direction"], …>` over the **whole** union, so there is no
branch to fall into: a fourth direction is a compile error, not a rendered verdict.
Mutation 3 in §8 restores the old `const up = factor.direction === "up"` and two
tests fail. That is the shape I would defend in review.

---

## 6. The harness, and what I would not do

`packages/predictor-ui/harness/main.tsx`:

- `:58` `PL_PICK: PickRef` and `pick:` on both pick-bearing fixtures, so states 1,
  2, 3, 4 and 5 all show the accent on the right segment — state 1 is Kevin's case,
  the pick on the **second** segment.
- `:100-118` (the function at `:114`) `favours(segments)` — the sentence is now computed from the same
  array the bar draws, so it cannot contradict it again. It reads "Its numbers
  favour BAL over KC" beside KC 38% / BAL 62%, and would follow the numbers if
  they changed.
- `:168-182` the no-pick state: no `pick` key at all, both rows `neutral` (as the
  service now emits for a no-pick bundle), headline "What the numbers say" — the
  old headline was "The model likes the favourite", which was a second claim on top
  of the sentence, about a panel with no pick.
- `:20-42` (the row at `:36-37`) a third, `neutral` row in the with-pick NFL state (the record), because
  the service emits neutral rows *whether or not* there is a pick, and without one
  the screenshots would not show the neutral state at all.

**What I did not do, plainly.** "Derive it from the template" is not available from
here, and I want to be exact about why rather than hand-write a better sentence.
`grep -rn favour services/explainer/explainer/` returns **nothing**: the Python
template has never emitted a "favour" row. With no pick it emits `Not much to go
on` / `Where this stands`; with a pick it emits `The pick` / `The line` / etc. So
there is no template sentence to derive *from* and no template call I could make —
`explain_from_template` is a Python function and the harness is a browser bundle.
What I have done is remove the possibility of contradiction *inside the harness*
(derived from the same constant the bar draws) rather than claim a derivation that
does not exist. If the panel is ever to say this for real, the sentence belongs in
`template.py` beside the other prose, with a test that it agrees with the bar — and
that is Task A's file, so it is the controller's call, not mine.

---

## 7. Concerns

1. **Nested `<button>` in `MatchCard`, pre-existing and now visible.** My three
   card tests are the first to render a `MatchCard` **with** a bar, and React logs
   *"<button> cannot contain a nested <button>"*. The structure is
   `MatchCard.tsx:52` (the card is a `<button>`) → `ProbabilityBar`'s per-segment
   label buttons. Invalid HTML, and a screen reader flattens the inner ones, so
   §13c's "reachable and operable by keyboard alone" is compromised inside a card.
   It is not caused by my change (I added a prop), and the fix is a design call —
   either the card stops being a `<button>` wrapper, or the bar's labels become
   non-interactive inside one — so I did not make it. **It should be someone's task.**
2. **The harness is not type-checked, and does not type-check.** `tsconfig.json`'s
   `include` is `["src", "vitest.config.ts", "test-setup.ts"]` — no `harness`. Adding
   it today produces three errors, one of which is a real latent bug in the file I
   edited: `harness/main.tsx:201` — `Property 'factors' does not exist on type
   'Explanation'` (the fixture is annotated as the v1|v2 union, so the v2-only
   members are unreachable). The other two are missing dev deps at the package root
   (`@types/react-dom`, `@vitejs/plugin-react`, `@tailwindcss/vite`), so closing the
   gap needs a dependency decision, not a one-line `include`. **The screenshot
   evidence for this whole panel is a file no type-checker reads** — which is the
   same shape as Task A concern 7 and the same shape as every wrong claim in this
   session. I avoided adding a *second* instance of that error (I hoisted
   `PL_PICK` to a constant rather than reading `PL_VERDICT.pick` off the union) but
   I did not fix the existing one, because I cannot prove a fix compiles.
3. **Task A concern 7 stands, and I could not fix it under the brief.**
   `services/explainer/tests/test_template_v2.py`'s `NO_PICK` fixture sets
   `prob: 0.0`, which is a usable probability, so it **has** a pick and its name
   asserts the opposite. My own no-pick fixtures are named for what they are
   (`NFL_BAR` with no `pick` prop, `NEUTRAL_FACTORS`, `noPick` in the panel tests,
   harness state 6 which omits the `pick` key entirely). It needs renaming in the
   final wiring task.
4. **`prompt_version` is still `v2` (Task A concern 2) and is still the biggest
   thing in this PR.** Nothing in this commit reaches a cached row: a body cached
   before the deploy still carries `"up"` on its total/btts/record rows, and my
   renderer cannot tell which rows are about the game. A cached **llm** row survives
   until the facts change. The no-pick fix ships inert for exactly the readers
   whose answer is already cached unless `config.py:33` is bumped in the deploy.
5. **The new token is a cross-repo change in waiting.** `scripts/sync-ui.mjs` copies
   whole files, so no change is needed there, but each site's vendored
   `predictor-ui/tokens.css` (and any generated CSS) picks it up on the next sync.
   Task 4's wiring must not skip it, and the sites' own contrast gates are
   unaffected because no site references the token yet.
6. **A correction to the ledger, in the ledger's favour.** It says (line 9) that
   `packages/predictor-ui/node_modules` is **not** gitignored on this branch and
   that `git add -A` must never be used here. It is ignored:
   `packages/predictor-ui/.gitignore:1` is `node_modules/`, that file is tracked
   (`git ls-files packages/predictor-ui/.gitignore` prints it), and
   `git check-ignore -v packages/predictor-ui/node_modules` attributes the ignore
   to it. The pattern is unanchored, so `harness/node_modules` is covered too, and
   `git status --short` after `npm ci` shows no `node_modules` entry. I staged
   explicit paths anyway and would still recommend it — but the warning is about
   the wrong file, and the *right* warning is that `node_modules` is ignored
   **now** and nothing in CI enforces that, so a future `rm .gitignore` would put
   200MB of dependencies into the next `git add -A`.

---

## 8. Verification — the exact commands and the numbers I measured

Baselines, measured by me on this branch before I touched anything:

```
$ cd packages/predictor-ui && npx vitest run
 Test Files  9 passed (9)
      Tests  148 passed (148)

$ npx tsc --noEmit
tsc exit: 0

$ services/explainer/.venv/bin/python -m pytest -q services/explainer
235 passed, 1 warning in 1.22s

$ node --test tests/*.mjs
ℹ tests 21
ℹ pass 21
ℹ fail 0
```

(Durations vary run to run, so only the counts are load-bearing here.)

After the change, on the committed tree:

```
$ cd packages/predictor-ui && npx vitest run
 ✓ src/teamColors.test.ts (33 tests) 85ms
 ✓ src/tokens.test.ts (12 tests) 6ms
 ✓ src/fmt.test.ts (21 tests) 53ms
 ✓ src/components/atoms.test.tsx (15 tests) 125ms
 ✓ src/components/frame.test.tsx (7 tests) 176ms
 ✓ src/components/table.test.tsx (3 tests) 248ms
 ✓ src/components/card.test.tsx (20 tests) 213ms
 ✓ src/components/explainer.test.tsx (21 tests) 201ms
 ✓ src/components/explainerV2.test.tsx (38 tests) 381ms
 Test Files  9 passed (9)
      Tests  170 passed (170)

$ npx tsc --noEmit
tsc exit: 0

$ cd <repo root> && services/explainer/.venv/bin/python -m pytest -q services/explainer
235 passed, 1 warning in 1.08s

$ node --test tests/*.mjs
ℹ tests 21
ℹ pass 21
ℹ fail 0
```

**148 → 170 vitest, `tsc` 0, 235 explainer pytest (no regression), 21 root node
tests (no regression).** 22 tests added, 0 amended, 0 removed.

The harness is covered by none of those, so I checked it parses:

```
$ node_modules/.bin/esbuild harness/main.tsx --outfile=/tmp/harness-check.js --format=esm
  /tmp/harness-check.js  9.7kb
⚡ Done in 3ms
esbuild exit: 0
```

(It cannot be type-checked or built here — `harness/node_modules` is not installed
and the harness is outside the tsconfig `include`. See §7.2.)

### Mutations — each reverted, each caught, output below

**1. Revert `fill()`'s emphasis to segment order** (`tones()` → accent on index 0):

```diff
 function tones(segments: Segment[], index: number): string[] {
-  let rank = 0;
-  return segments.map((s, i) => {
-    const emphasised = i === index;
-    const tone = fill(s.color, emphasised, rank);
-    if (!emphasised) rank += 1;
-    return tone;
-  });
+  // MUTATION: the old rule. The accent goes to the first segment, whatever the pick.
+  return segments.map((s, i) => (i === 0 ? ACCENT : NEUTRALS[(i - 1) % NEUTRALS.length]));
 }
```
```
 FAIL  src/components/card.test.tsx > the match card's bar > accents the segment the card's pick names, not the first one
 FAIL  src/components/explainerV2.test.tsx > the pick is the accented segment > accents the pick's segment, and the pick here is the second one
   AssertionError: expected [ 'var(--color-pr-accent)', …(1) ] to deeply equal [ 'var(--color-pr-text-dim)', …(1) ]
   - Expected
   + Received
     Array [
   -   "var(--color-pr-text-dim)",
       "var(--color-pr-accent)",
   +   "var(--color-pr-text-dim)",
     ]
 Test Files  2 failed | 7 passed (9)
      Tests  13 failed | 157 passed (170)
```

**2. Force an emphasised segment when there is no pick** (`pickIndex` → `0`):

```diff
 function pickIndex(segments: Segment[], pick: PickRef | null | undefined): number {
-  return pick ? segments.findIndex((s) => s.label === pick.label) : -1;
+  // MUTATION: with no pick, fall back to emphasising the first segment.
+  return pick ? segments.findIndex((s) => s.label === pick.label) : 0;
 }
```
```
 FAIL  src/components/explainerV2.test.tsx > the pick is the accented segment > accents nothing at all when there is no pick
   AssertionError: expected [ 'var(--color-pr-accent)', …(1) ] to not include 'var(--color-pr-accent'
     ❯ src/components/explainerV2.test.tsx:188:34
 Test Files  2 failed | 7 passed (9)
      Tests  8 failed | 162 passed (170)
```

**3. The trap — restore `const up = factor.direction === "up"`** and the old
unconditional triangle:

```diff
-        const mark = MARK[factor.direction];
+        // MUTATION: the old rule. `up` means "not down", so a neutral row reads
+        // as a down triangle in the loss colour.
+        const up = factor.direction === "up";
+        const mark: "up" | "down" | null = up ? "up" : "down";
-              <span className={`mt-0.5 w-[14px] shrink-0 ${TONE[factor.direction]}`}>
-                {mark && TRIANGLE(mark === "up")}
-              </span>
+              <span className={up ? "mt-0.5 text-pr-win" : "mt-0.5 text-pr-loss"}>{TRIANGLE(up)}</span>
```
```
 FAIL  src/components/explainerV2.test.tsx > a factor with no direction > draws no mark at all, and wears neither the win nor the loss colour
   AssertionError: expected …(2) to have a length of +0 but got 2
     ❯ src/components/explainerV2.test.tsx:315:63
 FAIL  src/components/explainerV2.test.tsx > ExplainerPanel > accents nothing on a panel whose answer carries no pick
 Test Files  1 failed | 8 passed (9)
      Tests  2 failed | 168 passed (170)
```

**4. Render the band on a rebuilt pick:**

```diff
-        {v2 && !rebuilt && <BandChip band={data.band} />}
+        {v2 && <BandChip band={data.band} />}
```
```
 FAIL  src/components/explainerV2.test.tsx > a rebuilt pick's band > withholds it on a rebuilt pick, while the status line still says rebuilt
   AssertionError: expected <span …(2)></span> to be null
   - Expected: null
   + Received:
   + <span class="…" data-testid="band-chip">Strong</span>
 Test Files  1 failed | 8 passed (9)
      Tests  1 failed | 169 passed (170)
```

**After each revert**, `git diff` was empty and the suite returned to 170. The
final state, checked after the fourth revert:

```
$ git status --short
?? .superpowers/sdd/2026-09-27-v2-fixes/progress.md      # the ledger, untracked, not mine to commit
$ git diff
(empty)
$ git log --oneline -1
3662248 fix(predictor-ui): the accent is the pick, and a neutral factor claims nothing
```

The tree is byte-identical to `3662248`. No mutation is left in place.

---

## 9. Where I disagree, or would argue

**With the item 5 ruling: I agree, and I think it is the stronger call than a
softer word for a reason the ruling does not use.** Withholding is right; what I
would add is that a weaker band is not a smaller version of the same lie. "MODERATE"
beside "not counted" is still a confidence the reader has to weigh against the
warning, so it does not remove the contradiction — it only makes it quieter. That is
why §13e says "withheld rather than softened" and why the test asserts
`not.toMatch(/strong/i)` on the whole panel rather than just the chip's absence.

**With the controller's split of the work: one small correction, in the
controller's favour.** The brief said the renderer is the right place for the
withholding and not to move it into Python without asking. I did not move it, and I
agree — but I want to record that I looked for the reason and there is a second one
beyond "it keeps the value available". A `band_for` conditional on `pick_timing`
would make the *contract* depend on when the pick was made, and §13a's thresholds
are about how much to trust a number; a number's trustworthiness is a property of
the number, and the panel's inability to act on it is a property of the panel. One
function, one job.

**One thing I would push back on in Task C, since it is coming next:** the harness's
`note=` strings on `Case` are also hand-written prose about what a screenshot shows,
and they are the same drift risk as the sentence I just fixed. They are not
contradicted by a figure next to them today, so I left them, but if a note ever
says a number it should be derived the same way.

**Nothing in this task needed a ruling overturned.** Task A's concern 2
(`prompt_version`) is the one I would act on before anything else in this PR, and
it is not mine to bump.
