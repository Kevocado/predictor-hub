# Explainer v2 — a visual, on-demand match explainer

**Status:** design only. Nothing here is implemented. The reviewer approves this
before a plan is written (`superpowers:writing-plans`) and before any code moves.

**Supersedes:** §3 and §4 of `2026-09-25-phase3-4-datahub-explainer-design.md`
remain true where this document does not contradict them. The honesty rule,
the pre-kickoff record rule and the footer contract are unchanged and are
restated here because the redesign puts more weight on them, not less.

---

## 1. What changes, and the one idea underneath it

Kevin's brief asks for four things: a narrower scope (PL, NFL, CFB only), an
on-demand trigger, structured visual output, and a template that is just as
good as the model's. The first two are scope. The third and fourth are one
decision, and it is the whole design:

> **The model never supplies a number. The panel renders numbers from the facts
> bundle, and the model supplies only words and ordering.**

Today the model writes prose containing figures, and `validate.py` catches any
figure that is not in the facts. That is a real guard and it stays — but it is
a guard against a failure mode we can simply not have. The facts bundle already
carries every figure, already structured, already correct by the honesty rules
in §2. If the panel reads them directly then:

- a number on screen is correct **by construction**, not by validation;
- the template path renders the *same* layout from the *same* facts, because
  layout is data-driven and does not know or care whether a model was involved
  (Kevin's requirement 4, satisfied structurally rather than by effort);
- and the model is left doing the only thing it is actually good at: saying
  which factors matter and in what order, in plain words.

The model may still write digits. `validate()` still rejects any that are not
in the facts. The difference is that the UI has no path by which a model's digit
could be rendered as a figure, so the guard is a net rather than the wall.

### Why this is the design and not the obvious one

The alternative — ask the model for structured tiles including numbers, then
validate each tile's number — keeps the model in charge of layout and makes
every tile a validation surface. It also makes the template path a second,
hand-built renderer that must be kept visually identical to the first. That is
the failure mode this design exists to remove: two renderers, drifting.

---

## 2. Honesty rules (unchanged, restated because more now depends on them)

1. **After the moment, only the stored pre-kickoff record.** Unchanged. The
   facts bundle already enforces this: a started game gets its figures from the
   stored row, and a field the row lacks is *absent* rather than backfilled.
2. **A rebuilt pick is shown, never counted,** and says so on the panel.
   `pick_timing` travels on the response from the facts, never read out of prose.
3. **The footer fails closed.** "AI" renders only when the response carries
   `source === "llm"` *and* a model *and* a readable timestamp. Anything else
   gets the sentence that claims nothing. Unchanged, and still the one claim in
   the product with no fact behind it.
4. **Every figure on screen came from the facts.** Now true by construction
   (§1) and additionally enforced by `validate()` on any digit the model writes.
5. **No figure implies certainty.** No "lock", "guaranteed", "sure thing",
   "value play", "bet". Unchanged. The bands in §5 are named, not numeric, and
   the model may not attach a number to one.

### 2a. A new check, closing an open Critical

The whole-phase review found that `validate()` does not check a pick's **outcome
verdict**, so prose can call a rebuilt or lost pick "right" and pass. A RED test
for it exists and is parked. Structured output makes this *harder* to get wrong
rather than easier, because the panel will render the outcome from
`result.pick_won` and the model only supplies a phrase — so the fix is to check
the phrase against `pick_won`, and the panel never renders a model-supplied
verdict at all. This must land with v2, not after it.

---

## 3. Scope

| Sport | Panel | Service | Why |
|---|---|---|---|
| Premier League | keep, on fixture detail | serves | in scope |
| NFL | keep, on game detail | serves | in scope |
| CFB | keep, on game detail | serves | in scope |
| F1 | **remove** | **refuses** | out of scope |
| NBA | **remove** | **refuses** | out of scope |

> **Superseded for NBA, 2026-09-27.** The rows below say the service *refuses*
> `f1` and `nba`. That is true of **F1 only**, and it was true of neither when the
> decision was made: NBA was refused on F1's reason without being checked, and its
> `/facts` carries the same `moneyline`/`spread`/`total` the panel draws. NBA now
> serves. F1 is refused as a product decision, not a data gap — a win probability
> *is* the explanation.
>
> The refusal also had a consequence nobody wrote down here: NBA's `line` is the
> **model's own wording**, not the market's line, so serving it required the
> template to know which key holds the quoted price per sport. See
> `services/explainer/explainer/template.py` `MARKET_LINE_KEY`. Every other
> "refuses `f1`/`nba`" line in this document is stale in the same way; they are
> left as the approved record rather than rewritten.

**Wiring, precisely.** NFL and CFB are served by the **Sports_Predictor**
frontend (`sports.<host>/?sport=nfl|cfb`), so their single panel lives in
`Sports_Predictor/src/components/GameDetailModal.tsx`, which already takes an
`explain(sport, id)` prop and a `sport` prop. PL has its own
`PL_Predictor/frontend/src/components/FixtureSummaryPanel.tsx`. Those three
surfaces are the whole change.

**Removed:** `F1_Predictor`'s `SessionSummaryPanel` usage and
`NBA_Predictor`'s `GameSummaryPanel` usage, and both sites' `api/explain.py`
proxies. A dead proxy is worse than no proxy: it is an endpoint that looks
supported and 404s from the wrong layer.

**The service refuses `f1` and `nba`** at the edge of `/explain/{sport}/{id}`,
before any facts fetch and before any budget is touched. Chosen over "return a
template" so a caller cannot mistake a refusal for an answer.

**The `/facts` endpoints stay.** They cost nothing, and item 3 of the current
round refers to F1's `/facts` still being read. Deleting five endpoints is a
separate change with its own justification; it is listed as an open item in §10
rather than smuggled in here.

---

## 4. Trigger: on demand only

The 3-hourly pre-generation loop goes, and with it the service's use of
`/facts/upcoming`. Kept: the cache, so a second open of the same fixture is
free, and the daily cap.

This is a large budget saving on its own. Pre-generating 72 hours across five
sports was the main consumer; on-demand it is roughly "one request per fixture a
human actually opens", so expect well under a tenth of the previous volume.
**Revisit the cap after a week of real numbers** rather than guessing at it now.

**Consequence to design for: the first open is slow.** 2–8 seconds is normal
for a free model. So:

- the panel never gates the detail it sits in (already true, and stays true);
- the skeleton says *"Writing the summary…"* and, after 4 seconds, adds
  *"the numbers below are already here"* — because they are, and the reader
  should know the wait is optional;
- a cancel is not offered: the request is idempotent and the result is cached,
  so abandoning it wastes a cache entry at worst.

---

## 5. The structured contract

### 5a. What the model returns

```jsonc
{
  "verdict": "Baltimore is the pick, but the line is thinner than the number.",  // ≤ 18 words
  "band": "moderate",           // one of: leaning | moderate | strong — NAMED, not numeric
  "factors": [
    { "key": "moneyline", "direction": "up",   "headline": "Model leans Baltimore",
      "text": "The rating gap has held all week and the model has not moved off it." },
    { "key": "spread",    "direction": "down", "headline": "The line asks more than the margin",
      "text": "The market is asking for more than the model thinks the gap is worth." }
  ]
}
```

- `key` **references** a market in the facts (`moneyline`, `spread`, `total`,
  `result`, `total_goals`, `btts`) or the pseudo-markets `record` and `context`.
  It never carries a figure. The service resolves it against the facts; an
  unknown key is **dropped**, not an error (fail closed to fewer factors).
- `band` is a word. It is deliberately not a probability: a band is a judgement
  about the *pick*, and giving it a number would put a figure on screen that no
  fact supports.
- `direction` is **relative to the pick**: `up` is a factor arguing for it,
  `down` a factor arguing against. It is never "the number went up" — the
  numbers do not move.
- `text` is number-free by rule. If the model writes a digit, `validate()` will
  reject it against the facts pool, so the rule is enforced rather than trusted.
- 2–4 factors. Fewer is fine; zero is a validation failure, because a panel with
  no factors is a worse panel than one with two.

### 5a-bis. Derived figures: encoded, never stated

The panel may *encode* a ratio as geometry — a bar's width, a segment's share —
because that is what a bar is. It may never *state* one as a figure.

`record` is `hits: 41, settled: 68`. The facts contain no `60.3`. So the panel
writes **`41 / 68`** and lets the bar carry the proportion; it does not write
"60.3%". The first draft of the mocks in §7 did write it, which is the same
class of error as a model inventing a number, and it is called out here so the
plan does not reintroduce it.

The same applies to a bar's accessible name: it reads "41 of 68", not "60.3%".

### 5b. What the service adds

Unchanged from today: `sport`, `id`, `source`, `model`, `generated_at`,
`prompt_version`, `pick_timing`.

**`prompt_version` is bumped.** The v1 rows hold `headline`/`sections`; a v2
renderer reading one would render nothing. A new version means a new cache key,
so v1 rows are never read. The renderer additionally treats any cached body
without a `verdict` as a **miss**, so a reused version can never serve prose
into a structured panel.

### 5c. The facts the panel draws from (verified against the real bundles)

**NFL** — `pick {label, prob}`; `markets[]` of `moneyline` (`model` map),
`spread` (`model_margin`, `line`, `model_cover_prob`), `total`
(`model_total`, `line`); `players[]` (`name`, `team`, `projection`);
`record {label, hits, settled}`; `context`; `result`.

**PL** — `pick {side, label, prob}`; `markets[]` of `result` (`model` map of
**three** probabilities, plus `implied` and `edge` when odds exist),
`total_goals` (`model_total`, `over_2_5`, `under_2_5`), `btts` (`yes_prob`);
`record`; `context {gameweek}`; `result`.

PL's three-way result market with a bookmaker comparison is the richest thing in
either bundle, and it is what the split bar in §6 is for.

---

## 6. The panel

Five parts, in this order. Layout is driven by the facts, identically for the
model and the template.

1. **Verdict line** — the model's one sentence, or the template's.
2. **Key-number tiles** — one per market the facts carry. Each shows the
   model's figure large, with the market's line beneath it when there is one.
   A tile is *absent* when its market is absent; never a zero, never a dash.
3. **Split bar** — the probability breakdown, `segments` wide. NFL gets two
   segments (the moneyline pair), PL gets three (home/draw/away). With PL's
   `implied` present, a second hairline row underneath shows the market's own
   split, so the reader can see model against market rather than a bare number.
4. **Why boxes** — the factors. Each is a row: a direction arrow, a headline,
   and the model's sentence. The arrow is a **glyph plus a text label**, never
   colour alone.
5. **Footer** — §2 rule 3, unchanged.

Plus, where the facts carry them: the record strip (`hits/settled` as a thin
proportional bar) and NFL's player projections as a three-row mini-list.

### 6a. Typography and colour

Reuse the family tokens already in `predictor-ui` (`--font-pr-display`,
`--font-pr-body`, `--pr-accent`, `--pr-text-dim`, `--pr-rule`). No new palette,
no new typefaces. No emoji as icons, focus-visible rings, `prefers-reduced-motion`
honoured.

**On the 12px floor specifically — a claim this spec made and had to correct
twice.** The hub asserts a 12px minimum in `hub.test.mjs` and holds it. My first
correction said `Sports_Predictor` had 23 occurrences across 9 files; that number
came from reading a dirty checkout rather than `origin/main`, and the real count
is **six, in two files**. `Sports_Predictor` now has `src/craft-floor.test.ts`
enforcing the floor the way the hub does, so the rule is a test in both places
rather than a habit in one. The v2 panel is a new surface in that site and should
follow it.

The wider lesson is in the ledger and worth the space here, because this spec
inherited a claim it had not checked: **a dirty checkout is not a slower version
of the product, it is a different product.** Three of four findings from the
review that prompted this correction were properties of somebody's uncommitted
work. A spec that cites a defect should be able to say which commit it is on.

A 12px floor rules out one tempting move — tiny percentage labels inside the
split bar segments. Where a segment is too narrow for its label, the label goes
in a legend beneath rather than shrinking.

### 6b. Motion

Deliberately almost none.

- The split bar animates its widths once, on first paint, 240ms, ease-out.
- **Direction arrows do not animate.** A count-up or a pulse on a static number
  implies the number is changing. It is not.
- The record strip does not animate in.
- Everything above is disabled under `prefers-reduced-motion: reduce`.

### 6c. Accessibility

- The split bar is `role="img"` with an `aria-label` carrying the same
  numbers in words, so it is not a mystery graphic to a screen reader. The
  record bar's label reads "41 of 68", never a percentage (§5a-bis).
- The direction arrow is `aria-hidden` with the direction in adjacent text.
- Tiles are a `<dl>`, so the label/value pairing is structural.
- Every interactive element (there are none in v2 beyond a retry) is reachable
  and has a visible focus ring.
- 390px: one column, tiles stack, the split bar goes full width. The bar's
  minimum segment width is 2px so a 3% probability still renders as a sliver
  rather than vanishing.

---

## 7. The two mocks

Both mocks show a `41 / 68`-style record and **no percentage beside it**, which
is §5a-bis made visible: the proportion is the bar's width, not a stated figure.
The first draft of these mocks wrote "off 60.3%", which is arithmetic the facts
do not contain — the same class of error as a model inventing a number, and the
reason the rule is written down rather than left to the renderer.

### 7a. NFL — game detail

Facts: `pick {label: "BAL", prob: 0.62}` · moneyline `{KC: 0.38, BAL: 0.62}` ·
spread `model_margin 3.4, line "BAL -2.5", model_cover_prob 0.58` ·
total `model_total 45.2, line 44.5` · record `41/68` ·
players `A. Tucker 71 rec yds`, `M. Jones 68 rec yds`, `T. Holliday 54 rec yds` ·
`pick_timing: pre_kickoff`.

```
┌────────────────────────────────────────────────────────────────────┐
│ IN PLAIN ENGLISH                                                  │
│                                                                    │
│ Baltimore is the pick, but the line is thinner than the number.    │
│                                          ┌──────────────┐           │
│  ┌──────────────┐  ┌──────────────┐       │  MODERATE    │           │
│  │     62%      │  │  BAL −2.5    │       └──────────────┘           │
│  │  win · BAL   │  │  model −3.4  │                                 │
│  └──────────────┘  └──────────────┘                                 │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │     45.2     │  │  41 / 68     │                                 │
│  │  total pts   │  │ before kick  │                                 │
│  │  line 44.5   │  │     off      │                                 │
│  └──────────────┘  └──────────────┘                                 │
│                                                                    │
│  KC  ████████████████████░░░░░░░░░░░░░░░░░░░░░  BAL                │
│      38%                                    62%                    │
│      ─────────── model ───────────                                    │
│                                                                    │
│  WHY IT MATTERS                                                    │
│  ▲ Model leans Baltimore                                           │
│    The rating gap has held all week and the model has not           │
│    moved off it.                                                   │
│  ▼ The line asks more than the margin                               │
│    The market is asking for more than the model thinks the gap      │
│    is worth.                                                       │
│                                                                    │
│  TOP PROJECTIONS                     PICKS MADE BEFORE KICKOFF     │
│  A. Tucker            71 rec yds     ███████████████░░░░░░  41/68  │
│  M. Jones             68 rec yds                                     │
│  T. Holliday          54 rec yds                                     │
│                                                                    │
│  AI summary of the model's numbers · nemotron-3.5-lightning · 2 min │
└────────────────────────────────────────────────────────────────────┘
```

### 7b. PL — fixture detail

Facts: `pick {side: "home_win", label: "Arsenal win", prob: 0.48}` ·
`result.model {home_win: 0.48, draw: 0.26, away_win: 0.26}` ·
`result.implied {Arsenal: 0.44, Chelsea: 0.30}` · `edge {Arsenal: 0.04,
Chelsea: -0.04}` · `total_goals {model_total 2.7, over_2_5 0.56, under_2_5
0.44}` · `btts {yes_prob 0.61}` · `record 38/71` · `context {gameweek: 31}` ·
`pick_timing: pre_kickoff`.

```
┌────────────────────────────────────────────────────────────────────┐
│ IN PLAIN ENGLISH                                                  │
│                                                                    │
│ Arsenal are the pick, and the market roughly agrees.               │
│                                          ┌──────────────┐           │
│  ┌──────────────┐  ┌──────────────┐       │  MODERATE    │           │
│  │     48%      │  │     2.7      │       └──────────────┘           │
│  │ Arsenal win  │  │  total goals │                                 │
│  │  market 44%  │  │  O2.5  56%   │                                 │
│  └──────────────┘  └──────────────┘                                 │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │     61%      │  │  38 / 71     │                                 │
│  │  both score  │  │ before kick- │                                 │
│  └──────────────┘  │     off      │                                 │
│                    └──────────────┘                                 │
│                                                                    │
│  Arsenal ████████████░░░░░░░░░░░▓▓▓▓▓▓░░░░░░░░░  Chelsea            │
│          48%          26% draw        26%                          │
│      ─────────── model ───────────                                    │
│      ─────────── market ──────────                                    │
│                                                                    │
│  WHY IT MATTERS                                                    │
│  ▲ Model and market agree on Arsenal                                │
│    Both put Arsenal at about the same price, so there is no        │
│    disagreement to exploit here.                                    │
│  ▼ Goals look closer than the sides do                              │
│    The sides are near even, but the model expects goals.            │
│                                                                    │
│  GAMEWEEK 31                      PICKS MADE BEFORE KICK-OFF       │
│                                    ███████████░░░░░░░░░░  38/71   │
│                                                                    │
│  AI summary of the model's numbers · laguna-s-2.1 · just now       │
└────────────────────────────────────────────────────────────────────┘
```

The draw is a separate segment in the middle, not folded into "not Chelsea" —
a three-way market rendered as two ways is a lie by layout.

---

## 8. The template path

Same components, same layout, same tiles, same bar. Only the words differ, and
the footer says so. The template builds its structure from the facts alone:

- verdict: composed from the pick's probability band and the market's line.
- factors: one per market present, headline and text composed from the market's
  own fields.

This is cheap **because** the layout is data-driven (§1). It is also the reason
the two paths cannot drift: there is one renderer.

## 9. Testing

TDD throughout, as everywhere.

- **Contract tests, built with the producer's own types.** The recurring bug in
  this codebase is a double shaped like the consumer: PL read a pydantic model
  as a dict, NBA imported a module that did not exist, F1 read field names its
  routes do not emit, and the props test asserted a single-week fetch that later
  became two-week. Every new facts-shaped fixture is built with the real schema
  class, and a real route is driven where one exists.
- **`validate()`** keeps every current rule, gains the outcome-verdict check
  (§2a), and gains: factors are 2–4; `key` resolves against the facts; no digit
  in a headline or `text` that is not in the facts; `band` is one of three
  words.
- **A panel test per state**: loading, error, template, model, rebuilt,
  three-way bar, two-way bar, a market absent, a 3% sliver segment, 390px.
- **A parity test**: the template and model fixtures must produce the same
  *structure* — same tiles, same segments — with only the words differing. That
  is the one that keeps §8 honest.
- **Screen-reader labels** asserted, not eyeballed.
- No test touches the network.

## 10. Scope check: is this one plan?

It is one feature with one contract change, but it is wide: the service's output
contract, the validator, five new UI components, three site wirings, and two
removals. That is too much for one implementation plan to hold honestly, and the
plan should be **written as four sequenced phases** rather than one long list:

1. **Contract and validator** — the new response shape, `prompt_version` bump,
   the outcome-verdict check (§2a), the factor rules. No UI. This is the part
   everything else depends on, and it is independently testable.
2. **The shared components** — tiles, split bar, factor rows, record strip, in
   `predictor-ui`, with the template path built first so parity is structural
   from the first commit.
3. **Wiring in and removal out** — Sports (NFL + CFB) and PL switched over;
   F1 and NBA's panels and proxies deleted. One PR per repo.
4. **Trigger change** — drop the scheduler, on-demand only, and revisit the cap
   once there are real numbers.

Phases 1 and 2 are reviewable on their own. Phase 4 is small and independent,
and could go first if the budget saving is wanted sooner than the redesign.

## 11. Open items, deliberately not in this spec

- Deleting the five `/facts` endpoints once nothing reads them.
- The daily cap's new value, once on-demand volume is real.
- Whether `records` and the player list belong in the panel at all; they are
  here because the facts carry them and they are honest, but they are the most
  droppable parts of §6.
- The remaining whole-phase-review findings, which are independent of the
  redesign and should not wait for it: NFL/CFB shipping two different
  probabilities for the same pick in one bundle; the validator comparing numbers
  by absolute value so a flipped spread sign passes; the Sports Caddy block
  being the only proxy of four that forwards an upstream body.

## 12. Decisions taken without asking, and why

Kevin is away. Each of these is a judgement I made so the round could finish;
each is one line to reverse.

| Decision | Why | Reverse by |
|---|---|---|
| Numbers come from the facts, not the model | Makes honesty structural, and makes template parity free (§1) | — this is the design |
| `band` is a word, not a number | A numeric band is a figure no fact supports | name a probability instead |
| 2–4 factors, zero is a failure | A panel with no factors is worse than one with two | allow zero |
| Refuse `f1`/`nba` with 404, not a template | A refusal must not look like an answer | return a template |
| Keep `/facts` endpoints | Item 3 refers to F1's still being read | delete them |
| No path filter discussion here | Unrelated to the panel | — |
| 240ms bar animation, no arrow motion | Motion on a static number implies it is changing | — |
| NFL's players and both records kept | They are in the facts and they are honest | drop them from §6 |

---

## 13. Amendments

Added after review of this spec and **before** any code moved. Each names the
clause it overrides, because a spec that says "and also" is how a document ends
up with two answers to one question. Where an amendment contradicts §12, §13
wins; §12's row "`band` is a word, not a number" is **replaced** by 13a rather
than merely supplemented.

### 13a. `band` is computed from the facts, never chosen by the model

**Overrides** the `band` bullet in §5a, and replaces the §12 row about `band`.

The model is not asked for a confidence band and is not allowed to supply one. §5a
argued that a *numeric* band would be an unsupported figure; it did not notice
that a *named* band is worse, because a name cannot be checked. Nothing ties
`"strong"` to anything. So the model can call a 52% pick `"strong"` and the
reader sees a confident sentence with no fact behind the confidence — which is the
one failure this whole redesign exists to remove.

The band is therefore a pure function of `pick.prob`, computed by the service,
with thresholds fixed here so they are reviewable rather than emergent.

**Two-way markets** (NFL and CFB moneyline). No-edge is 0.50.

| band | `pick.prob` |
|---|---|
| `strong` | ≥ 0.60 |
| `moderate` | ≥ 0.52 |
| `leaning` | < 0.52 |

**Three-way markets** (PL `result`). A draw is a real outcome, so no-edge is
about 0.333, not 0.50; the two-way thresholds would call a 45% home win `leaning`
and a 40% one `strong`, which is inverted.

| band | `pick.prob` |
|---|---|
| `strong` | ≥ 0.50 |
| `moderate` | ≥ 0.40 |
| `leaning` | < 0.40 |

The market shape is read from the facts, not hard-coded per sport, so a future
sport is classified by its own market rather than by a list someone remembered
to update.

**When `pick.prob` is absent there is no pick to have a confidence about**, so the
band is `leaning`, the weakest word, and §6's verdict line reads the no-pick
sentence. The band never implies a confidence the facts do not contain.

`band` is **removed from the contract** in §5a: the model returns `verdict` and
`factors` only. A model that volunteers a `band` anyway has it **ignored**, and
that is tested rather than asserted — a fixture returns `"strong"` beside a 52%
pick and the rendered band must still read `moderate`. Removing the field from
the contract is not sufficient on its own, because a model that was trained on
the old shape will emit it regardless, and a field that is merely undocumented
is a field that eventually gets read.

**The template calls the same function.** There is exactly one implementation of
the thresholds, in one place, and a test asserts the template's band equals
`band_for(prob, shape)` for a range of probabilities. A second hand-written
threshold table is the failure mode where the two paths quietly diverge, and
divergence between the default and the model is precisely what §8 forbids.

This does not weaken §5a's "the model never supplies a rendered number". It
strengthens it: a *word* is a figure too when it is the only carrier of a
confidence, and now the word is derived from the one number the facts do carry.

### 13b. The PL market row needs implied probabilities for all three outcomes

**Overrides** the second half of §6 item 3 ("With PL's `implied` present, a
second hairline row…").

Checked against the real bundle, PL's `implied` covers **only the two sides** —
home and away. There is no `draw` key. So "with `implied` present" is a
condition that reads as satisfiable and is not: the row would render a three-way
model split over a two-way market split, the draw segment sitting above nothing,
and the reader comparing two bars that do not cover the same outcomes.

The market row renders **only when `implied` covers every outcome the model's
split has** — all three for PL. Otherwise it is omitted entirely. Omission is
the honest answer; a partial row is a comparison that cannot be made.

The same rule governs the tile's market line: it states `implied` **for a side
that is present**, and is omitted when the side it would name has no `implied`.
For a draw pick with no `implied.draw`, the tile carries no market line at all.

**No draw probability is ever derived.** A book's 2.5/3.0/3.5 prices imply a draw
probability by subtraction, and it would be a real number — but it would be a
number *this product computed*, not one the facts carry, which is the line §1
draws. It is also the number most likely to be wrong in a way nobody would
notice: it silently assumes the overround is distributed across all three
outcomes, and different books distribute it differently. If a market comparison
for the draw is wanted, `implied` has to carry it, and that is a `/facts` change
for later.

### 13c. Light, keyboard-accessible interaction

**Overrides** §6c's "Every interactive element (there are none in v2 beyond a
retry)", and adds to §6b.

Kevin asked for something intuitive and interactive. v1 had a retry button. That
is not interaction, it is error handling, and it is not what was asked for. The
panel gains three affordances, all of which connect parts of the same panel to
each other, and all of which are reachable and operable from the keyboard.

1. **A factor references what it is about.** Selecting or hovering a *why* row
   highlights the tile and the bar segment whose market `key` it names. The
   linkage is the `key` from §5a, so it cannot drift from the reference the
   factor already makes in text. Both directions highlight, and clearing the
   highlight restores the resting state.
2. **A bar segment shows its own label on focus or tap.** A segment is
   focusable and labelled by the same figures its `aria-label` already carries,
   so a pointer user and a keyboard user get the same information. A segment
   that is too narrow to show a label in place still shows one on focus, in a
   legend — §6a's 12px floor is why the in-place label was never an option.
3. **A factor's text is expandable on narrow screens.** Under a viewport
   threshold the sentence is clamped to its first line behind a real
   `<button aria-expanded>`, not a CSS-only trick, so it works without
   JavaScript-driven measurement and is announced correctly.

**The constraint that makes this safe: no interaction may reveal a figure that is
not in the facts.** Each affordance shows a label, a highlight, or geometry the
facts already supply. None computes, rounds or interpolates a new number, and
none may be a place where a model's wording surfaces a figure that §5a's
validator would have rejected in prose. A hover tooltip carrying "probably
around 55-60%" is the exact failure this section exists to prevent, and it is
worth naming because it is the obvious thing to reach for when adding
interactivity to a data panel.

Motion is unchanged in kind: the highlights cross-fade over 120ms, and **all of
it is disabled under `prefers-reduced-motion: reduce`**, including the
expansion. A highlight that appears instantly is not a problem; a highlight that
slides is, for a reader who asked for less motion.

Every affordance is tested twice: that it works, and that it is reachable and
operable by keyboard alone. The second is the one that catches a div with an
`onClick`.

### 13d. The trigger and the refusal go first

**Overrides** the sequencing implied by §4 and §10, which read as "trigger last".

The on-demand trigger and the `f1`/`nba` refusal ship as the **first** phase, not
the last. Two reasons, and the second is the one that matters:

1. They are small and independent — a deletion, a lifespan change and a guard.
   Nothing in phases two through four can block them.
2. **Budget is being spent today on exactly what this removes.** The scheduler
   pre-generates 72 hours across five sports, including two the redesign does not
   serve. That spend continues until this phase lands, so leaving it last means
   paying for a design decision to be deferred.

The refusal is in the same phase because it is the same kind of change — a
refusal at the service boundary — and because a `f1` or `nba` request arriving
between phases one and three should be a `404` from the first hour, not from the
day the frontends are edited.

Revised order: **(1) trigger and refusal**, (2) contract and validator,
(3) shared components, (4) wiring in and removal out.
