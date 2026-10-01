# Fixture signals: computed insight, instant, with an AI "so what"

**Status:** design approved by Kevin on 2026-10-01 (brainstormed in chat; all four signals chosen,
signals instant, AI adds the interpretation). No code yet. Next: an implementation plan
(`superpowers:writing-plans`), then phases below, one PR per repo per phase.

## 1. The problem, measured

What the AI says today, one fixture per sport, next to what the page already shows
(live, 2026-10-01):

| sport | AI text | already on the page |
|---|---|---|
| NFL | "Model gives Pittsburgh 59%, Cleveland 41%"; "projects a total of 40.6, slightly above the 38.5 line" | tile 59%, bar, tiles line/total |
| CFB | "52 picks before kickoff, 70 settled correctly" | the record strip |
| NBA, F1 | template: "MIA is the pick at 53%" | everything |
| PL | "~7 in 10 … won four of last five" | the bar, the form dots |

**Root cause: the AI sees only the model's own outputs, so everything it can say is a paraphrase.** The
rule that every number must come from those facts forbids it from adding anything. Prompt tuning
cannot fix this; new information has to enter the system. (NBA/F1 mostly fall back to the template.)

## 2. The principle

**Code computes the insight; the AI only chooses and words it.** (The explainer-v2 principle, one level
up: "the model supplies words and ordering, never a number the panel renders".)

- A **signals layer**, one adapter per sport, inside each sport's API (they own the data), produces typed
  findings with their figures, sample size and source.
- A fixed rule (not the model) ranks them by `strength` and keeps the top 2-3.
- Signals are **instant**: computed from stored data, no model call, rendered with the facts block.
- The AI button adds **one short "so what"** that ties the shown signals together. The validator
  rejects any figure not present in the signal payloads (extends the existing market-word / number rules).
- A signal exists only if it adds something the page does not already show. No data, no row. No empty
  states, no "unknown" rows, no filler.

## 3. The signal contract

```
Signal = {
  kind: "trust" | "absence" | "line_gap" | "post_game",
  sport, game_id,
  headline: {figures...}      // the numbers the visual draws; the AI may quote only these
  n: int | null,              // sample size where it is a rate
  source: str, as_of: iso,    // attributable and dated
  strength: 0..1,             // how much the reader should care; set by the adapter, tested
  pre_kickoff_only: bool,     // false only for post_game
  visual: "delta_chip" | "reliability_bar" | "absence_strip" | "projected_vs_actual"
}
```

Served by each sport API on a signals endpoint (shape decided in the plan), also included in `/facts`
for the wording step. The shared UI renders `Signal[]` with predictor-ui components.

## 4. The four signals

| signal | what it says | data (verify in the plan's spike) | sports |
|---|---|---|---|
| **trust** | "When this model says ~59% on a home favourite it has been right X% of the time (n games)." | the stored track record's pick-probability buckets / each site's calibration data. Renders only at n >= 30; below that the row says nothing, never a rate from a handful of games. | all |
| **absence** | "Out: J. Jacobs, our #2 rush projection (78 yds), ESPN injury report, Wed." Day-To-Day is **flagged, never turned into a number.** | NBA `/players/out` + Day-To-Day (merged), NFL gate (merged), PL FPL status. F1/CFB: no feed, no row. | NBA, NFL, PL |
| **line_gap** | "Model margin 3.1 vs line 2.5: 0.6 pts" with the model's historical record when it disagreed by >= 2 pts (only if n is enough). | NFL/CFB carry a quoted spread/total. PL, NBA and F1 have **no odds feed**: this signal never appears there. | NFL, CFB |
| **post_game** | "Projected margin 3.1, actual 14. Biggest miss: total (proj 40.6, actual 62)." Whether a flagged absence existed. | stored pre-game pick vs final score and available outcomes | all, finished games only |

### Corrections baked in (found while writing this)

- **No roster sums as team figures.** The absence signal states the *player's* own projection and rank;
  it never says "team rushing drops from 164 to 86". `player-model-accuracy` §5.1-5.2 forbids
  team totals built from roster sums (the model projects one market per position). My first example in the
  brainstorm did exactly that and was wrong.
- **Doubtful is a flag, not a coefficient.** NBA has no calibrated number to pair with Day-To-Day.
- **Started games** use the stored (earliest recorded) pick for every figure; no signal restates today's
  rerun as the pre-game call. `post_game` is the only signal about the result and only for finished games.
- **Nothing is invented to fill a slot.** If a sport has one honest signal, it shows one.

## 5. The AI step

- Input: the selected `Signal[]` plus the existing facts. Output: `{ so_what: str (<= 20 words) }`, no
  band, no figures of its own.
- Validator: every figure in `so_what` must appear in a signal payload; the existing banned-word,
  market-word and timing rules apply unchanged; zero overlap with the facts block (a restated figure
  fails and the template wording is used).
- Template path (model off / budget out / rejected): the same signals render with their own fixed
  one-line wording. The page is identical except for the "so what" line, and the footer says which wrote it.
- Cost: one call per open as today; the signals add none.

## 6. How it looks

Compact **callout rows** under the facts block (never paragraphs): a delta chip for `line_gap`, a
reliability bar for `trust`, an absence strip for `absence`, a projected-vs-actual marker for
`post_game`. Each row has one line (<= 12 words) and a collapsed evidence line (source, n, date).
Design with the impeccable skill and render real components in the predictor-ui harness (desktop + 390px,
every state: signal present/absent per sport, finished game, started game). No new tokens or faces.

## 7. Phases (one PR per repo per phase, test-first, `npm run build` clean, red proofs)

1. **trust + line_gap**: the data already exists. Shared `Signal` contract + `SignalRows` component in
   predictor-ui; adapters in NFL, CFB (line_gap + trust), PL, NBA, F1 (trust). Instant rendering.
2. **absence**: builds on the merged injury gates and picks. NBA, NFL, PL.
3. **post_game**: finished games; replaces the AI's current useless finished-game text.
4. **the "so what" step** and the validator rule; retire the old factor-prose summary.
5. **Slate brief** (separate spec): across a whole week, the biggest disagreement and the most
   injury-affected game; no per-fixture page does that comparison.

## 8. Amends

| spec | clause | change |
|---|---|---|
| explainer-v2 | §5a contract (`factors`), §6 factor rows, §8 template path | factors replaced by `Signal[]` + `so_what` |
| fixture-insight-design | §B callouts and its validator non-overlap rule | the callouts become the four signals; the non-overlap rule moves to the signal payloads |
| Sep-28 flow/trigger/news | news mechanism | unchanged; news feeds `absence` where a source exists |
| fixture-insight-design | §D player news | `absence` is its fixture-level surface |

## 9. Decisions (reversible)

| # | decision | alternative | reverse by |
|---|---|---|---|
| 1 | signals instant, AI adds the "so what" (Kevin) | everything behind the button | gate the rows on the button |
| 2 | adapters live in each sport API | compute in the explainer service | move the module; contract unchanged |
| 3 | trust needs n >= 30 | lower or higher floor | one constant per sport |
| 4 | ranked by adapter `strength`, top 3 | model chooses | the AI step may reorder only |
| 5 | slate brief is a separate spec | include now | add phase |

## 10. Open items for the plan's first spike (measure, do not assume)

- Does each sport's stored track record have the pick-probability buckets `trust` needs, at what n?
- What shape is the quoted line on NFL/CFB for pre-game and for started games (stored vs live)?
- Where does a finished game's actual outcome data live per sport for `post_game`?
- PL: which FPL statuses map to out vs doubtful (PL#38 already removes i/s/u).
