# Task 0 spike: what data actually exists, per sport

Measurement, not design. Spec: `docs/superpowers/specs/2026-10-01-fixture-signals-design.md`.
Every count below was run against a fresh checkout; **no cell is estimated or extrapolated.**
A cell reading `DROPPED` or `UNMEASURED` is an honest gap, not a placeholder to fill in later.

`origin/main` used: `predictor-hub` `060e0875`; `NFL_Predictor` `56c3d84d`; `CFB_Predictor` `69ef7e2a`;
`NBA_Predictor` `f4d8a34c`; `PL_Predictor` `5b054cc7`; `F1_Predictor` `06cc8bd8`; `Sports_Predictor` `18b27226`.

## Sport x signal

| signal | NFL | CFB | NBA | PL | F1 |
|---|---|---|---|---|---|
| `trust` (n>=30) | **DROPPED** — 0 resolved rows in `data/tracking.db` | **DROPPED** — `data/tracking.db` has **no tables at all** | **DROPPED** — 0 rows in all 4 tables (`predictions`, `game_market_predictions`, `player_prediction_snapshots`, `odds_timing_snapshots`) | **DROPPED** — 0 rows in `predictions` and `fixture_market_predictions`; and no probability *ranges* exist, only scalar RPS/Brier + `n_matches` | **DROPPED** — no bucket code at all; only `session_predictions` (2,919 rows) and no probability buckets |
| `line_gap` | **BLOCKED** — `src/nfl_predictor/api/facts.py:509` `markets = [] if (started and stored is None) else ...`, so a started game with no stored pre-kickoff row has no quoted line at all | **UNMEASURED** | n/a | n/a | n/a |
| `post_game` (actual outcome) | `game_predictions` (0 rows locally) | no tables locally | `game_player_outcomes`, `predictions` (both 0 rows) | `fixture_player_outcomes`, `predictions` (both 0 rows) | `session_predictions` — **2,919 rows**, the only non-empty store measured |
| odds feed exists? | yes | UNMEASURED | **yes** — `odds_timing_snapshots` table | **yes** — `odds_timing_snapshots` table | UNMEASURED |
| PL absence statuses `i`/`s`/`u` | n/a | n/a | n/a | **present** — `models/fpl.py:28` `if status in {"i","s","u"}`, and `data/fpl_api.py:424` `UNAVAILABLE_STATUSES` | n/a |

## Where the measurement contradicts the approved spec

Seven places. **Four are product decisions, so phases 1-4 are not safe to build on the spec as
written** — they are listed for Kevin rather than guessed at.

1. **`trust` has no supporting data in any sport.** Not one sport has the resolved history the
   signal needs at `n >= 30`. This is the phase-1 centrepiece, so phases 1-4 as planned cannot ship.
2. **NBA has an odds feed.** `odds_timing_snapshots` exists. Spec §4 asserts it has none.
3. **PL has an odds feed**, plus a no-odds fallback path. Spec §4 asserts it has none.
4. **PL turns "doubtful" into a coefficient, contradicting "flagged, never turned into a number".**
   `player_ratings.py:50` and `models/fpl.py:32` and `data/fpl_api.py:428` all compute
   `chance_of_playing_next_round / 100` with a **default of `0.5`**. A doubtful player is therefore
   not flagged but silently given half weight, and a *missing* chance field is indistinguishable
   from a genuine 50%.
5. **NFL `line_gap` cannot be computed for the case it exists to measure.** `facts.py:509` empties
   `markets` for a started game lacking a stored row, so the pre-kickoff-vs-live comparison has
   nothing on one side for exactly the started games that matter.
6. **Local tracking stores are almost entirely empty** (only F1 has rows), so row counts from a
   developer machine cannot answer calibration questions. The `trust` depth must be measured against
   production, not these files — and the deployment hosts are not discoverable from source, since
   the API base is injected at build time via `VITE_*_API_BASE_URL`.
7. Two local `origin/main` refs were stale when measured (`predictor-hub`, `CFB_Predictor`); every
   number above was re-measured from the SHAs listed at the top.

## Recommendation

Hold phases 1-4. Resolve 4 and 5 as product decisions first, and decide how `trust` is supposed to
get data at all — with 0 resolved rows everywhere, the phase-1 work would ship a component with
nothing to render.
