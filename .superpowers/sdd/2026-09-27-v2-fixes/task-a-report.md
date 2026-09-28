# Task A — the Python contract and the template

Worktree: `/Users/sigey/Documents/Projects.nosync/predictor-hub-worktrees/v2p3-fixes`
Branch: `explainer-v2-phase3` (PR #13)
Scope: `services/explainer` only. `packages/predictor-ui` is **byte-for-byte untouched**
(`git status --short packages/` is empty), because Tasks B and C own it.

**The path in the brief was wrong.** It said `Documents/Projects/nosync/predictor-hub-worktrees/v2p3-fixes`.
There is no `Projects/nosync`; the real one is `Documents/Projects.nosync/...` (a dot, not a
slash). The ledger's own header (`progress.md:3`) has the correct path, so there is no
ambiguity about which tree this is. `Documents/Projects/nosync/` also exists and contains a
near-empty decoy (`predictor-hub-worktrees/v2p3/packages/predictor-ui/src/components/FactorList.tsx`,
8 KB, no `.git`, no `services/`). I did not touch it. Worth knowing that it is there.

---

## 1. The shape I chose for the pick, and why

```python
# contract.py
def pick_for(facts) -> dict | None:      # {"label": "BAL"}  /  {"label": "Arsenal", "side": "home"}  /  None
```

and in `service._answer`, the key is **omitted** when there is no pick:

```jsonc
// with a pick
{ ..., "verdict": "BAL is the pick.", "band": "strong", "factors": [...],
  "pick": { "label": "BAL" }, "pick_timing": "pre_kickoff" }

// no pick — note what is NOT there
{ ..., "verdict": "There is no pick for this one yet.", "band": "leaning", "factors": [...],
  "pick_timing": "pre_kickoff" }
```

(That is real output, printed from `_answer`'s own construction — see §6.)

**Why this shape, in the order I decided it:**

- **It sits next to `pick_prob`, as a sibling of `band_for`, and is called from `_answer`
  beside the band.** The band is computed in exactly one place so the model path and the
  template path cannot disagree about it. The pick is the same kind of value for the same
  reason, so it is built the same way: one function, one call site, no second copy in
  TypeScript.
- **`label` is the join key, and it is the label the facts already carry.** §5c of the spec
  says the panel draws from `pick {label, prob}` (NFL) and `pick {side, label, prob}` (PL),
  and the bar segments in the harness are labelled with those same strings (`"KC"`,
  `"BAL"`, `"Arsenal"`, `"Draw"`, `"Chelsea"`). So a renderer can match `pick.label` against
  `segment.label` with no translation table. Kevin's item 1 is "`pick.label` / `side`", and
  both are there.
- **`side` rides along only when the facts carry one.** PL has it (`home`/`away` against a
  draw); NFL has no such field. Inventing one for NFL would be a value nothing supports, so
  the key is simply absent. That makes the type `{label: string; side?: string}`.
- **No `prob`.** §5a-bis is explicit that the panel draws every figure from the facts, and a
  second copy of a probability in the *explanation* is a second thing that can disagree with
  the bar. The response already depends on `prob` — the band is computed from it — but a
  band is a word and cannot contradict a segment's width; a `prob` here could. Not included.
- **No `market`.** Deliberate. The segments the panel passes in already carry their own
  `market` key (`Segment.market`), so a renderer matching by label can find the segment and
  read its market from it. Inventing a pick→market mapping in Python would be a second
  vocabulary to keep in step with `template._outcome_key` and `contract.market_shape`, and
  both of those already exist for their own jobs. If Task B turns out to need it, the
  honest place is a `_outcome_key`-style function, not a field smuggled into the pick.
- **`None` means no pick, and the key is omitted rather than set to `null`.** The renderer
  acts on the absence. `null` and `{"label": ""}` are both answers to a question nobody
  asked, and both would still be an object for a renderer to test.
- **The gate is "usable label AND usable probability"** — deliberately the *same* test as
  `pick_prob` and as `template.py`'s verdict string. This is the load-bearing decision. A
  bundle with `pick: {"label": "BAL"}` and no probability produces the verdict "There is no
  pick for this one yet."; if `pick_for` only required a label, the response would carry a
  `pick` beside a sentence denying one, and the panel would point a bar at it. Three
  separate "is there a pick" tests is three things to keep in step, so there is one
  function, and the template calls it too (`has_pick = pick_for(facts) is not None`).

**On `as_dict`.** The brief flagged that the accessor has to work on both shapes. It does,
by going through `as_dict` rather than `facts.get` — which is that function's whole stated
job. `test_the_pick_reads_a_model_dump_and_a_dict_alike` passes a real `Facts` instance, its
`model_dump()`, and a plain dict, and gets the same answer from all three.

---

## 2. Every factor in `explain_from_template`, with the direction under a pick and no pick

This table is **measured**, not intended: it is the output of running
`explain_from_template` over nine bundles and reading the directions back. `—` means the row
is not emitted at all for that bundle.

| factor (`template.py`) | gate | with a pick | no pick | why |
|---|---|---|---|---|
| `How it finished` :110 | `status == final` and a score | `up` | `neutral` | Only a pick it grades. With a pick and `pick_won`, the sentence is "The pick was right/wrong: BAL", which is a point for the pick. With no pick the row reports the score and nothing else, so it is not for anything. |
| `Rebuilt after the start` :115 | `pick_timing == "rebuilt"` | `down` | `neutral` | A rebuilt pick is a reason not to lean on it, so `down` is a real "against". Unchanged, as instructed. With no pick there is nothing rebuilt to be cautious about. |
| `The pick` :121 | `label and prob is not None` | `up` | not emitted | Unchanged, as instructed. It is the one row whose gate *is* `has_pick`. |
| `The line` :130 | needs a `label` | `down` | `neutral` (when the gate is met) | A point against the pick, as instructed. Note the gate: it tests `label`, **not** `prob`, so for `{"label": "BAL"}` with no probability the row is still emitted — and used to read "against it" beside a verdict saying there is no pick. Now `neutral`. This is the asymmetry I had to decide about; see §3. |
| `The total` :139 | market + `model_total` + a line | `neutral` | `neutral` | Statement about the game. Defended in §3. |
| `Both to score` :146 | `btts` + `yes_prob` | `neutral` | `neutral` | Statement about the game. Defended in §3. |
| `Its record so far` :164 | `record` + hits/settled | `neutral` | `neutral` | Statement about **other** picks. Nobody listed this one, but it was emitted unconditionally and was `"up"`, so with no pick it read "for the pick" exactly like the total. Defended in §3. |
| `Not much to go on` :178 (padding) | fewer than 2 rows | `down` | `neutral` | "The facts for this one are still filling in" is thin evidence, which *is* a point against a pick that exists. Verified reachable with a pick (one market-keyed row, no record) — not a dead branch. |
| `Where this stands` :184 (padding) | fewer than 2 rows | `neutral` | `neutral` | "So there is little to weigh up here: {title}" is not an argument for anything. It was `"up"` only because the row needed *a* direction. Defended in §3. |

`minimal()` (:204, :206) — the last resort, which runs when even the template failed, so it is
the purest no-pick case there is: `Not ready` and `Try again` were `down` and `up`. Both are
now `neutral`. A reader whose explanation failed outright was being told the service had a
case against the pick and a case for it.

Measured, for the record:

```
pick, one market row -> [('moneyline', 'The pick', 'up'), ('context', 'Not much to go on', 'down')]
no pick, same markets -> [('context', 'Not much to go on', 'neutral'), ('context', 'Where this stands', 'neutral')]
```

---

## 3. The judgements, and whether I agree with the brief

### I agree with the ruling that the total and btts are neutral *regardless* of whether there is a pick

The brief asked me to think about this and defend it. The argument that convinced me: these
rows never name a side. "It projects 2.7 goals against a line of 2.5" and "It puts 61% on both
teams scoring" are complete sentences with no pick in them. The pick is on the `result`
market. A reader who sees **FOR THE PICK** beside them cannot check what that means, because
nothing in the row says which way it leans — and if the pick ever *were* the total market,
the row still would not say over or under. So "for the pick" is not a weaker claim there, it
is an unsupportable one, and the honest reading does not change when a pick appears. The
same argument disposes of the record row, which counts *other* picks and so is not evidence
for this one under any circumstances.

The general rule I applied, which I think is cleaner than "with a pick / without a pick":
**emit `up` or `down` only where the row is genuinely a claim about the pick.** That is the
brief's own words for the template ("emit an explicit up/down only where it actually knows
the direction"), applied past the five rows it listed. A consequence worth flagging, because
it changes the *with-pick* rendering of two rows nobody flagged:

- `Its record so far`: `up` → `neutral`. I believe `"up"` was wrong here, not merely
  imprecise: it let a season's 41/68 stand in for a match.
- `Where this stands`: `up` → `neutral`. Also wrong: "there is little to weigh up here" is
  the opposite of support, and it was `up` only because the row needed a direction.

Both are Task B's *rendering* to finish, but the value Task B will read is now honest. If
the controller disagrees and wants those two left at `up` for the with-pick case, it is a
two-line revert and no test in the new set depends on it except
`test_a_row_about_the_game_is_neutral_even_when_there_is_a_pick`, which pins the full table
deliberately.

### One place I did **not** take the brief's framing, because the source disagrees

**The coercion at `contract.py:129` is not what produced the no-pick defect, and I can show
it.** `_clean` → `clean_verdict` → `_factors` is called from exactly one place,
`service.py:204`, and only on a body that has already been through `validate()`:

```python
problems = validate(out, facts_json, news_json)
if not problems:
    return _clean(out), "llm", model     # service.py:203-204
```

and `validate.py:207` refuses any factor whose `direction not in DIRECTIONS`. So on the
model path the coercion's `else` branch is **unreachable** — a model that omitted
`direction` or wrote `"sideways"` was rejected by the validator and the service fell back to
the template, and it is the *template's own hardcoded `"up"` literals* at `:115`, `:121` (and
`:136`, and `:153`) that put "for the pick" on screen with no pick.

So the ledger's finding B is a real hazard — a fail-open default that would bite any future
caller of `clean_verdict` that is not the validated model path, and a second copy of the rule
— but describing it as "the mechanism that produces the no-pick defect" is not quite right,
and a reviewer looking for a fix *only* there would have left the defect in place. Both are
now fixed, and I pinned the coercion in its own right
(`test_an_unknown_direction_becomes_neutral_rather_than_being_dropped`,
`test_a_missing_direction_becomes_neutral_too`) rather than relying on a downstream test,
because the coercion's own function is where the rule lives.

I flag this rather than argue with it: the ruling ("absent or unrecognised → NEUTRAL, not
`up`") is right and I implemented it exactly. Only the diagnosis of *which line was live*
needed correcting, and the mutation output in §5 shows the coercion is now genuinely covered.

### The asymmetry I deliberately did not "fix" (a residual defect, unchanged)

`template.py:107` gates the grading sentence on `label` alone while everything else in the
file that decides "is there a pick" uses `label and prob is not None`. For a bundle with
`pick: {"label": "BAL"}` and no probability, the template therefore says **"The pick was
right: BAL"** in the "How it finished" row while the verdict says "There is no pick for this
one yet." That contradiction exists today, before my change, and my change does not make it
worse or better — I fixed the *direction* of that row and left the *sentence* alone, because
tightening the gate is a third change nobody asked for and would alter which rows appear.

It is reachable only with a malformed bundle: spec §5c says the real NFL and PL facts both
carry `prob` on the pick, verified against live bundles. I would fix it by gating that
sentence on `has_pick` rather than `label`, and I would rather it were a deliberate decision
than a silent one. Flagged, not done.

---

## 4. `DIRECTIONS`, the validator, the `"sideways"` test, and the prompt

- **`contract.py`**: `NEUTRAL = "neutral"` added as a named constant, and
  `DIRECTIONS = ("up", "down", NEUTRAL)`. `NEUTRAL` rather than another bare literal so the
  coercion, the template and the docs have one name and one string.
- **The coercion** (`_factors`): `else "up"` → `else NEUTRAL`, with the reasoning in a
  comment at the line.
- **The validator needed no change at all.** `validate.py:207` is
  `if f.get("direction") not in DIRECTIONS`, and `DIRECTIONS` grew, so `"neutral"` is now
  accepted and `"sideways"` is still refused. The error message interpolates `DIRECTIONS`,
  so it now reads `must be one of ('up', 'down', 'neutral')`. That is the whole behaviour
  change, and it is the right place for it — one vocabulary, referenced, not restated.
- **`prompts.py` WAS changed, and this was not optional.** The prompt is the model's copy of
  the contract and it stated the two-state union twice (`:20` and the JSON sketch at `:29`).
  Leaving it would have made the third value unreachable on the model path — the model would
  never be told it may say `neutral`, so a no-pick answer would still be forced to pick
  `"up"` or `"down"`, and the widened validator would have accepted the lie. The prompt now
  describes `neutral`, says what it is for (the total, both teams to score, the record), and
  says that with no pick every factor is `neutral`.
- **The two-state test that had to be amended** — there were **three** places pinning it, not
  the one the brief named:
  1. `test_validate_factors.py:85 test_a_direction_must_be_up_or_down` → renamed
     `test_a_direction_must_be_one_of_the_three`. It now asserts all three are accepted
     **and keeps its `"sideways"` case failing**, and a new
     `test_nothing_outside_the_three_is_accepted` sweeps `"sideways"`, `"UP"`, `"Up"`, `""`,
     `None`, `1`, `True`, `"up "`, `"up/down"`. So a third value did not become "anything
     goes": the check is membership, not a length or prefix test.
  2. `test_contract.py:52` asserted `DIRECTIONS == ("up", "down")` in
     `test_the_vocabularies_are_closed` — same class of pin, not mentioned in the brief.
  3. `test_contract.py:75 test_an_unknown_direction_becomes_up_rather_than_being_dropped`
     pinned the *coercion itself* to `"up"`. Renamed
     `..._becomes_neutral_rather_than_being_dropped` and re-pointed at the new contract. It
     keeps the original point too: a factor is still not dropped for a bad direction, because
     `validate()` is what refuses the whole answer.
  Plus `test_template_v2.py:52`, which asserted `f["direction"] in ("up", "down")` — now
  `in DIRECTIONS`, imported, so the vocabulary cannot be copied into a second place.
- **TypeScript: I widened nothing, on purpose.** `FactorList.tsx:24`'s
  `direction: "up" | "down"` is load-bearing for
  `const WORDS: Record<Factor["direction"], string>`. Widening the union **forces** a
  `neutral` key in `WORDS`, and `WORDS` is what the reader sees. Choosing that word is
  renderer behaviour and it is exactly what the brief reserved for Task B ("no triangle, no
  win/loss colour on a neutral factor" is a rendering decision). Nothing in TypeScript passes
  a `"neutral"` today, so `tsc` does **not** need the widening — verified, `tsc --noEmit`
  exits 0 with `packages/` untouched. Task B should widen the union and the words together,
  in one visible step. Also note `const up = factor.direction === "down"` at `:75`: with a
  neutral value that expression renders a **down** triangle in the loss colour, so Task B
  cannot widen the type and leave the rest alone — it will fail its own tests, which is the
  correct pressure, but worth knowing before it starts.

---

## 5. Verification — exact commands, real numbers

Baseline measured by me before touching anything, on this branch:

```
$ uv run --extra dev python -m pytest -q          # from services/explainer
167 passed, 1 warning in 1.11s

$ npx vitest run                                  # from packages/predictor-ui
Test Files  9 passed (9)
     Tests  148 passed (148)

$ npx tsc --noEmit                                # from packages/predictor-ui
tsc exit: 0
```

The project's own runner is `uv run --extra dev python -m pytest` from
`services/explainer` (there is no Makefile; `pyproject.toml` sets `testpaths = ["tests"]` and
`asyncio_mode = "auto"`, and the plan doc uses the same invocation). It creates `.venv` on
first run.

After the change:

```
$ uv run --extra dev python -m pytest -q
222 passed, 1 warning in 0.94s

$ npx vitest run
Test Files  9 passed (9)
     Tests  148 passed (148)
   vitest exit: 0

$ npx tsc --noEmit
tsc exit: 0

$ git status --short packages/
(no output)
```

**167 → 222 Python, 148 vitest unchanged, `tsc` 0, `packages/` untouched.** 55 new tests, 3
amended, 0 removed.

### The real template path, per the brief

`tests/test_template_v2.py` now calls `explain_from_template` with facts that have **no pick**
(`WITHOUT_PICK = {**PL_FULL, "pick": None}`, and final / rebuilt / label-without-probability
/ bare variants) and asserts on what comes back:

- `test_with_no_pick_nothing_is_for_or_against_one` — asserts over **every** row, not the one
  in the screenshot: `wrong = {h: d for h, d in _directions(out).items() if d != NEUTRAL}`.
- `test_no_pick_bundle_emits_nothing_directional` — the same rule across five no-pick bundles.
- `test_the_game_rows_are_still_there_without_a_pick` — the fix is the direction, **not**
  hiding the row: the total and both-teams-to-score rows are still emitted, with their real
  figures. Dropping them to dodge a word would be the dishonest fix.
- `test_the_rows_about_the_pick_still_carry_their_direction` — the other half, so neutral
  cannot become a way of losing the panel's argument.
- `test_a_finished_game_with_no_pick_is_neutral_not_up`,
  `test_a_label_without_a_probability_gives_neutral_where_it_names_a_side`,
  `test_minimal_claims_nothing_about_a_pick`.

No harness fixture was added (that is the harness's own defect, and a fixture that agrees
with the template is the point of the change). And on the harness contradiction Kevin
described — *"Its numbers favour KC over BAL"* against a bar of KC 38% / BAL 62%:

> **The template can produce a correct version of that sentence, and Task C should derive it
> rather than hand-write it.** It is a one-liner from the facts and the bar's own segments:
> name the side with the higher probability and say the gap. I deliberately did not add it,
> because a sentence about the model's split is a rendering concern and Task C owns the
> wording (`O2.5 56%` → `Over 2.5 · 56%` is the same kind of call). But the honest source
> for it is now in the response: with the pick derived and carried, "favour" has a referent
> — `pick.label` is BAL, and BAL holds 62% of the bar. The fixture contradicts itself
> because it was written without knowing where the pick was; that is the defect, and this
> change is the thing that makes the correct sentence derivable rather than guessable.

### Mutations — each one reverted, each one caught

**1. Restore the coercion to `"up"`** (`contract.py`, the `else` branch)

```
FAILED tests/test_contract.py::test_an_unknown_direction_becomes_neutral_rather_than_being_dropped
FAILED tests/test_contract.py::test_a_missing_direction_becomes_neutral_too
2 failed, 220 passed, 1 warning in 0.96s
```

**2. Template emits `"up"` again for the total and btts rows** (unconditional, as before)

```
FAILED tests/test_template_v2.py::test_with_no_pick_nothing_is_for_or_against_one
FAILED tests/test_template_v2.py::test_no_pick_bundle_emits_nothing_directional[no-pick]
FAILED tests/test_template_v2.py::test_no_pick_bundle_emits_nothing_directional[no-pick-final]
FAILED tests/test_template_v2.py::test_no_pick_bundle_emits_nothing_directional[no-pick-rebuilt]
FAILED tests/test_template_v2.py::test_a_row_about_the_game_is_neutral_even_when_there_is_a_pick
5 failed, 217 passed, 1 warning in 0.95s
```

**3. Pick present-but-empty when there is no pick** (`out["pick"] = pick_for(facts) or {"label": ""}`)

```
FAILED tests/test_service.py::test_no_pick_means_no_pick_key_at_all[None]
FAILED tests/test_service.py::test_no_pick_means_no_pick_key_at_all[pick1]
FAILED tests/test_service.py::test_no_pick_means_no_pick_key_at_all[pick2]
FAILED tests/test_service.py::test_no_pick_means_no_pick_key_at_all[pick3]
FAILED tests/test_service.py::test_the_template_path_carries_no_pick_either
5 failed, 217 passed, 1 warning in 0.95s
```

**4. Validator accepts anything stringy** (`not in DIRECTIONS` → `not isinstance(str)`)

```
FAILED tests/test_validate_factors.py::test_a_direction_must_be_one_of_the_three
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[sideways]
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[UP]
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[Up]
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[]
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[up ]
FAILED tests/test_validate_factors.py::test_nothing_outside_the_three_is_accepted[up/down]
7 failed, 215 passed, 1 warning in 0.98s
```

After each revert the suite returned to `222 passed`. The seven failures before I wrote
anything were exactly the three tests that pin the two-state union (7 = 1 + 1 + 5 parametrised
cases) and nothing else — the amendment set was not a guess.

---

## 6. Things in the tree that a reviewer should know about

1. **`services/explainer/contract.py` is a byte-identical, unimported duplicate of
   `services/explainer/explainer/contract.py`.** Added in the same commit (`98b8990`), never
   imported by anything (`grep` finds no importer), and **not shipped** — the Dockerfile
   copies only `explainer/`. It therefore still contains the old `DIRECTIONS = ("up", "down")`
   and the old `else "up"`, and it is now a stale second copy of the rule this change is
   about. It cannot cause a defect today. I did not touch it: deleting or rewriting it is a
   refactor of code I was not asked to change, and one commit was the instruction. My
   recommendation is to delete it, but that is the controller's call.

2. **`prompt_version` is still `"v2"`, and it probably should not be.** This is the one
   follow-up I think matters. The cached `body` holds the factors, so a row written **before**
   this deploy still carries `"up"` on its total/btts/record rows — and, for a no-pick
   bundle, still renders "FOR THE PICK". A cached template row survives
   `TEMPLATE_RETRY_SECONDS` (3 h); a cached **llm** row survives until the facts change, i.e.
   potentially the whole match. So without a bump, the no-pick fix does not reach readers
   whose answer is already cached, and no code change can reach them: `_answer` must not
   rewrite a cached body's prose, and a renderer cannot tell which rows are about the game.
   The bump is the mechanism that exists for exactly this (it is why v1→v2 happened).
   I did not do it because it is a deploy-and-budget decision, not a contract change: it
   invalidates every cached row, and each uncached first open then costs a model call
   against the 900/day cap. On-demand volume is "roughly one request per fixture a human
   actually opens", so a bump is probably well inside the cap — but that is the controller's
   number to reason about, and it belongs with the Task 4 deploy. **`config.py:33`,
   `prompt_version: str = "v2"`.**

3. **`test_template_v2.py`'s `NO_PICK` fixture is a misnomer** and I left the name alone:
   `{"label": "BAL", "prob": 0.0}` — 0.0 is a *usable* probability, so there **is** a pick
   there and the pick-relative rows stay directional. It is a band fixture. I extended its
   comment to say so, because a reader looking for the no-pick case would otherwise stop
   there and believe the coverage was already there. It was not: the suite had **no**
   genuinely no-pick bundle through the real template path at all, which is exactly why
   Kevin had to find this in a screenshot.

4. **Docs I updated, and why.** `services/explainer/README.md` ("What it returns" is the
   response contract; it now shows `pick` and the three directions) and spec §5a/§5b
   (`docs/superpowers/specs/2026-09-27-explainer-v2-design.md`), which otherwise still state
   a two-state union and omit the pick — and this project's own `contract.py` docstring
   argues that two copies of a rule drift the first time one is edited. I did **not** add a
   §13 amendment (the ledger reserves §13 for the controller's rulings, and Task B writes
   item 5's there) and did **not** touch
   `docs/superpowers/plans/2026-09-27-explainer-v2.md`, which is the immutable record of the
   previous phase and still says `DIRECTIONS == ("up", "down")` as a description of what that
   commit did. If the controller would rather the spec edit waited for the Task B/C text, it
   is one file and easily dropped.

5. **No `uv.lock` or `pyproject.toml` change**, no new dependency, and nothing in
   `packages/`. The runner created `services/explainer/.venv`, which that directory's own
   `.gitignore` already covers.

---

## 7. Concerns, in the order I would act on them

1. **Bump `prompt_version` to `"v3"` in the deploy that ships this**, or the no-pick fix
   will not reach cached answers (§6.2). Biggest one.
2. **Task B cannot widen `Factor["direction"]` on its own.** `WORDS` gains a key and
   `factor.direction === "up"` currently means "not down" — a neutral row would draw a down
   triangle in the loss colour (§4).
3. **The `label`-without-`probability` grading sentence** still contradicts the verdict
   (§3). Pre-existing, malformed-bundle-only, not made worse, and not fixed.
4. **`Its record so far` and `Where this stands` changed direction in the with-pick case
   too** (§3), not only in the no-pick case. I think both were wrong; overrule if the
   controller disagrees.
5. **The decoy tree at `Documents/Projects/nosync/…/v2p3/`** (§0) — a near-empty
   `FactorList.tsx` with no repo around it. Not touched, but it will mislead anyone who
   greps for `predictor-ui` before reading the ledger's path.
