# Production measurements: trust buckets and odds feeds (2026-10-04)

Measured on the VPS against the deployed containers' own `tracking.db` and odds
caches, read-only. This exists because the open question was never "is the data
there" — it was "is it there *in production*", which the gitignored stores could
not answer from a checkout and which a fresh clone gets wrong by default.

Read-only throughout: `sqlite3.connect("file:…?mode=ro")` and `ls`/`find` on the
cache directories. No credential value was read or printed — only whether a
variable was set and how long it was.

## 1. How this was measured, and two ways the first answer was wrong

The spike (`2026-10-02-fixture-signals-spike.md`) recorded the per-sport trust
counts as `UNKNOWN` because `tracking.db` is gitignored in NFL/CFB/NBA/PL. The
stores exist in the deployed containers, so the counts are obtainable — and two
bugs would have produced a confident, wrong table if this had been left:

1. **A 0-byte decoy shadowed the real store.** Every container has
   `data/cache/tracking.db` at **0 bytes** alongside the real
   `data/tracking.db`. Globbing for `tracking.db` and taking the first match
   yields empty tables in NFL and CFB, which reads exactly like "no data". The
   real stores are 553KB (NFL) and 1.5MB (CFB).
2. **`resolved` is not an outcome.** NFL's and CFB's `game_predictions` carry
   `resolved`, `moneyline_hit`, `ats_hit` and `total_hit`. `resolved` is a
   *graded* flag. Bucketing `home_win_prob` against `resolved` returns
   `hit = 1.000` in **every** bucket, which is not calibration — it is the
   grading flag read as a result. NFL's per-bucket rates came out backwards
   under the same mistake (86% realised in a 0.2–0.3 bucket). The outcome
   columns are `moneyline_hit` / `ats_hit` / `total_hit`.

Both were caught by the numbers refusing to look like themselves. Worth writing
down, because both produce a clean table rather than an error.

## 2. `trust` — graded pairs per sport and market

Only rows carrying **both** a probability and a decided outcome count. The floor
is the spec's `n >= 30`.

| sport / market | graded pairs | bands over the floor | shippable |
|---|---|---|---|
| **CFB moneyline** | **390** | **6 of 10** | **yes** |
| F1 (7 markets pooled) | 1,452 | 7 of 10 | already shipped |
| CFB ATS | 59 | 0 | no |
| CFB total | 59 | 0 | no |
| NFL moneyline / ATS / total | 49 | 0 | no — too few |
| NFL player props | **0 gradable** | — | no — see §4 |
| CFB player props | **0 gradable** | — | no — see §4 |
| NBA any market | 119,860 joinable | — | no — wrong shape, §5 |
| PL anything | 0 | — | no store at all |

### CFB moneyline, the one market that qualifies

```
0.4–0.5  n=35  hit 0.486      0.7–0.8  n=66  hit 0.833
0.5–0.6  n=34  hit 0.529      0.8–0.9  n=80  hit 0.887
0.6–0.7  n=49  hit 0.714      0.9–1.0  n=86  hit 0.953
```

Monotone, six bands clear the floor, and under-confident through the middle
(states 0.65, realises 0.714) — the safe direction. On CFB's existing
four-bucket layout (`store.get_calibration`, `CALIBRATION_N_BUCKETS = 4`, chosen
for parity with NFL and the hub's edge gate) the same 390 rows put three of four
bands over the floor, so **the adapter can reuse `get_calibration` rather than
port F1's `get_probability_buckets`.**

### F1, the shipped one, for comparison

```
0.0–0.1 n=690 0.057   0.4–0.5 n=40 0.425   0.7–0.8 n=48 0.812
0.1–0.2 n=294 0.228   0.5–0.6 n=24 0.750*  0.8–0.9 n=22 0.773*
0.2–0.3 n=152 0.237   0.6–0.7 n=42 0.738   0.9–1.0 n=5  0.600*
0.3–0.4 n=135 0.363                          (* under the floor)
```

## 3. Kevin's decisions this measurement settled

| # | decision | recorded |
|---|---|---|
| 1 | trust ships only where a market is proven | CFB moneyline and F1. NFL, CFB ATS/total, all props, NBA and PL stay dark — a floor low enough to show NFL's 49 rows would publish rates off 12–20 observations |
| 2 | NFL should be accurate too | nothing to switch on: NFL has 49 graded game rows and 0 gradable prop rows. Recording continues; the badge appears when a band clears 30 |
| 3 | record the book line on prop predictions | required, and already the reason props are ungradable — §4. **NFL already has it** (see §6), so the work is CFB/NBA/PL |
| 4 | doubtful stays a flag, not a number | agreed; matches phase 2's own test, "doubtful flagged not computed" |

## 4. Player props are ungradable as recorded — and the reason is not the one expected

`player_prop_predictions` holds 3,088 rows in NFL (738 resolved) and 9,619 in
CFB. Neither can yield a single hit:

- **NFL: 42 of 3,088 rows have a `line`**, and 42 have a `side` (33 under, 9
  over). With no line, over/under is undecidable. 738 resolved rows are worth
  zero for calibration.
- **CFB has no `line`, no `side` and no `call_prob` at all.**

The correction to the obvious reading: this is **not** because the line is never
fetched. NFL's `line` column holds **the model's own projection line**, kept
deliberately distinct from the book (`store.py`, and the in-flight forward-test
work adds `line_at_snapshot` / `odds_at_snapshot` / `closing_line` beside it).
So a line *is* recorded — just not the one a bet is graded against.

## 5. NBA has the volume and not the shape

`player_prediction_snapshots` (132,788) joins `game_player_outcomes` (122,452) on
(game, player, stat) with **zero** ambiguity — 119,860 joinable pairs, 99.9% of
predictions carry a `player_id`. But the table stores `predicted_value` (a
projected 1.2 points), **no probability and no line**. Calibration needs a binary
event and a probability; a projection has neither. Trust for NBA is a modelling
change, not a wiring change.

**PL has no tracking database at all** — only `optuna_study.db`.

## 6. Odds feeds: the claim was wrong, and only CFB is actually wired

Full table and the reasoning are in `2026-10-01-fixture-signals-design.md` §11.
The short form: four repos ship an odds client; only CFB's `cache/sportsbook/`
is populated (written same-day). NFL and NBA hold `SPORTSBOOK_API_KEY` yet have
**no `sportsbook/` directory at all**, so their refresh never calls the path that
works — a wiring gap, not a missing key. PL has the largest stack in the fleet
(`sportsbook_api.py`, `value_bets`, `odds_benchmark`, a background refresh loop)
and **no odds credential set in production at all**, which matches Kevin's report
that PL was showing odds and no longer is.

## 7. What `line_gap` is actually blocked on

`line_gap` appears in **no** repository's `src/` — it is Phase 1 work not yet
started. The blocker is circular and worth stating precisely:
`nfl/api/facts.py:509` builds

```python
markets = [] if (started and stored is None) else _markets(...)
```

so a started game with no stored pick emits **no** markets — and that is exactly
the case `line_gap` exists to explain. The signal needs a line `facts.py`
deliberately declines to produce. Either `facts.py` emits the stored line for
started games, or `line_gap` is scoped to pre-kickoff only and is nearly empty.
NFL's `origin/props-quantile` does **not** touch `facts.py`, so it does not
resolve this.