# Task 0 spike: what data actually exists, per sport

> ## ⚠️ Correction — the first version was wrong (`f2a325b` retracted)
>
> It claimed *"Every count below was run against a fresh checkout; no cell is estimated."*
> **That was false.** `data/tracking.db` is **gitignored in 4 of the 5 sports**, so a fresh
> checkout has no such file; those counts came from untracked developer-machine files no reader
> can reproduce. Nothing is silently edited — the retraction is at the top.
>
> - **F1 `2,919` → `3,080`** rows (**1,452** `resolved=1`), re-derived from the committed blob.
> - **"`trust` has no supporting data in any sport" is FALSE.** F1 `trust` **is** supportable.
> - **`DROPPED` for NFL/CFB/NBA/PL is retracted → `UNKNOWN`.** Unmeasured is not zero.
> - **"Hold phases 1-4" is VOID** — it rested on that false claim. **5 of 7 cited SHAs were stale**
>   (re-fetched below). **NBA has 6 tables, not 4.**

Measurement, not design. Spec: `docs/superpowers/specs/2026-10-01-fixture-signals-design.md`. Every
number below is re-derived from a **committed blob** or marked `UNKNOWN`, which means *the
repository cannot answer it* — not that the sport has no data. `origin/main` used (re-fetched):
`predictor-hub` `060e0875`; `NFL_Predictor` `61e34be7`; `CFB_Predictor` `0674c858`;
`NBA_Predictor` `f4d8a34c`; `PL_Predictor` `0e838965`; `F1_Predictor` `6f492739`.

## Why the first version's counts were not reproducible

`git check-ignore -v data/tracking.db` at those SHAs:

```
NFL_Predictor  .gitignore:5:data/tracking.db
CFB_Predictor  .gitignore:7:data/*.db*
NBA_Predictor  .gitignore:10:data/tracking.db
PL_Predictor   .gitignore:8:data/tracking.db
F1_Predictor   exit 1 — tracked, so check-ignore does not report it
```

F1 is the sole exception: `git ls-tree origin/main -- data/tracking.db` → blob `da6217d9`, 749,568
bytes, tables `session_predictions` + `championship_snapshots`. `.gitignore:6` also lists it, but
tracking wins (`--no-index` reports the rule, the default does not). `PL_Predictor`'s own suite
asserts this too: `tests/test_pick_record.py:141`
`test_a_gitignored_tracking_db_is_why_this_is_needed` **fails** if `check-ignore` exits non-zero.

## F1 `trust` buckets — from the committed blob

`git cat-file blob da6217d9`, `WHERE resolved = 1` (1,452 rows), bucketed on `predicted_prob`:

| bucket | n | hit % |
|---|---|---|
| 0.0-0.3 | 1136 | 12.5 |
| 0.3-0.4 | 135 | 36.3 |
| 0.4-0.5 | 40 | 42.5 |
| 0.5-0.6 | 24 | 75.0 |
| 0.6-0.7 | 42 | 73.8 |
| 0.7-1.0 | 75 | 78.7 |

**Five of six buckets clear the spec's `n >= 30` floor** (spec §`trust`; open question 3), and the
hit rate is **monotone**. F1 `trust` is supported by data.

## Sport x signal

| signal | NFL | CFB | NBA | PL | F1 |
|---|---|---|---|---|---|
| `trust` | **BLOCKED on a production count.** Code ships: buckets `_TD_CONFIDENCE_BUCKETS` (`tracking/store.py:1380`, 50-60/60-70/70+), built in `_prop_markets:1445`. Resolved rows **UNKNOWN** | **BLOCKED on a production count.** Code ships: `_td_confidence_buckets` (`tracking/store.py:645`). Resolved rows **UNKNOWN** | **UNKNOWN.** 6 tables in schema (`tracking/store.py:23,33,47,54,63,72`); every row count **UNKNOWN**; no bucket code | **UNKNOWN.** 6 tables (`tracking/store.py:191,237,256,272,284,305`); row counts **UNKNOWN**; no probability *ranges* ship, only scalar `rps`/`brier`/`ignorance`/`n_matches` (`evaluate/calibration.py:47-50`) | **SUPPORTED.** 3,080 rows / 1,452 resolved, monotone buckets above. **No bucket code** — `tracking/store.py` has 0 `bucket` matches, no `confidence_buckets` in any F1 `*.py` |
| `line_gap` | **BLOCKED** — `api/facts.py:509` `markets = [] if (started and stored is None) else ...`, so a started game with no stored pre-kickoff row has no quoted line at all | **UNKNOWN** | n/a | n/a | n/a |
| `post_game` | `game_predictions`, `player_prop_predictions` — **UNKNOWN** | same two tables — **UNKNOWN** | `game_player_outcomes`, `predictions` — **UNKNOWN** | `fixture_player_outcomes`, `predictions` — **UNKNOWN** | `session_predictions` — **3,080 rows / 1,452 resolved**, the only committed store measured |
| odds feed exists? | yes | **UNKNOWN** | **yes** — `odds_timing_snapshots` (`tracking/store.py:54`) | **yes** — `odds_timing_snapshots` (`tracking/store.py:272`) | **UNKNOWN** |
| PL absence statuses `i`/`s`/`u` | n/a | n/a | n/a | **present** — `models/fpl.py:28` `if status in {"i","s","u"}` | n/a |

Notes. NFL/CFB are *blocked on data, not code*. NBA's 6 tables include `game_forecast_snapshots`,
omitted by the first version. PL also tracks `data/tracking_picks.jsonl` (360 records; keys
`event_id`/`market`/`outcome_name`/`predicted_prob`, **no actual-outcome field**) — no outcomes, so
it does **not** rescue `trust`; the omission is deliberate. PL also commits orphaned
`data/tracking 2.db-shm`/`-wal` and `data/tracking 3.db-shm`/`-wal` with **no `.db`**. CFB's local
store was empty when first measured — a property of *this machine*, not of CFB.

## Where the measurement contradicts the approved spec

Three places, all **product decisions for Kevin** — unchanged by this correction:
1. **NBA and PL both have odds feeds; the spec says neither does.** `odds_timing_snapshots` in each
   (`nba_predictor/tracking/store.py:54`, `pl_predictor/tracking/store.py:272`; PL also has a
   no-odds fallback path). Spec §4 asserts both have none.
2. **PL turns "doubtful" into a coefficient, contradicting "flagged, never turned into a number".**
   `models/player_ratings.py:50`, `models/fpl.py:32` and `data/fpl_api.py:428` all compute
   `chance_of_playing_next_round / 100` with a **default of `0.5`** — a doubtful player is not
   flagged but silently given half weight, and a *missing* chance field is indistinguishable from a
   genuine 50%.
3. **NFL `line_gap` cannot be computed for the case it exists to measure.** `facts.py:509` empties
   `markets` for a started game lacking a stored row, so the pre-kickoff-vs-live comparison has
   nothing on one side for exactly the started games that matter.

## Recommendation

**F1 `trust` can proceed now.** The data supports it (monotone, 5/6 buckets over the floor); only
the bucket adapter is missing, and it is the shape CFB already has at `tracking/store.py:645`.

**NFL/CFB `trust` is blocked on a production count, not on code.** Bucket code already ships;
nobody knows how many *resolved* rows sit in the untracked DB. Run this on the deploy host against
production `data/tracking.db` (copy first — the live DB is not read-only-safe); the bounds are the
exact ones `_TD_CONFIDENCE_BUCKETS` defines:

```sql
SELECT CASE WHEN predicted_value < 0.50 THEN '0.0-0.5'
            WHEN predicted_value < 0.60 THEN '0.5-0.6' WHEN predicted_value < 0.70 THEN '0.6-0.7'
            ELSE '0.7-1.0' END AS bucket, COUNT(*) AS n, SUM(actual_value) AS hits
  FROM player_prop_predictions WHERE resolved = 1 AND market = 'anytime_td'
 GROUP BY bucket ORDER BY MIN(predicted_value);
```

Split `0.0-0.5` into finer cuts if that bucket is under-filled; `n` per bucket is the only number
needed. The same query on `game_predictions` (`resolved = 1`, `home_win_prob` bucketed against
`moneyline_hit`) covers the head-to-head side.

**NBA/PL `trust` depth is UNKNOWN**, same reason — plus, for PL, a decision on whether probability
*ranges* are added at all, since only scalar calibration metrics ship today. **Residual:** deploy
hosts are still not discoverable from source (the API base is injected at build time via
`VITE_*_API_BASE_URL`), so nobody can run the query above from a clone — whoever holds the deploy
credentials must. Everything marked `UNKNOWN` stays `UNKNOWN` until then.