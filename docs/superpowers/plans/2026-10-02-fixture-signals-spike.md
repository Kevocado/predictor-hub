# Task 0 spike: what data actually exists, per sport

> ## ⚠️ Correction — the first version was wrong (`f2a325b` retracted)
>
> It claimed *"Every count below was run against a fresh checkout; no cell is estimated."*
> **That was false.** `data/tracking.db` is **gitignored in 4 of the 5 sports**, so a fresh
> checkout has no such file; those counts came from untracked developer-machine files no reader
> can reproduce. Nothing is silently edited — the retraction is at the top.
>
> - **F1 `2,919` → `3,080`** rows (**1,452** `resolved=1`), re-derived from the committed blob.
>   *(Superseded by a further refresh, not retracted — see the dated-measurement note below. As of
>   blob `e22d8a43` on 2026-10-03 it is **3,172 rows / 1,584 `resolved=1`**.)*
> - **"the hit rate is **monotone**" was wrong on its own figures.** `0.5-0.6` (75.0%, n=24) sits
>   above `0.6-0.7` (73.8%, n=42). Monotone only over the bands that clear `n >= 30`, and only just.
> - **"`trust` has no supporting data in any sport" is FALSE.** F1 `trust` **is** supportable.
> - **`DROPPED` for NFL/CFB/NBA/PL is retracted → `UNKNOWN`.** Unmeasured is not zero.
> - **"Hold phases 1-4" is VOID** — it rested on that false claim. **5 of 7 cited SHAs were stale**
>   (re-fetched below). **NBA has 6 tables, not 4.**

Measurement, not design. Spec: `docs/superpowers/specs/2026-10-01-fixture-signals-design.md`. Every
number below is re-derived from a **committed blob** or marked `UNKNOWN`, which means *the
repository cannot answer it* — not that the sport has no data. `origin/main` used (re-fetched):
`predictor-hub` `060e0875`; `NFL_Predictor` `61e34be7`; `CFB_Predictor` `0674c858`;
`NBA_Predictor` `f4d8a34c`; `PL_Predictor` `0e838965`; `F1_Predictor` `6f492739`.

> ## ⚠️ Every F1 figure below is a DATED OBSERVATION, not a standing fact
>
> **F1's `data/tracking.db` is refreshed automatically.** A workflow ("Refresh public snapshot +
> track record [automated]") re-ingests it and commits the result, so its row totals and bucket
> counts move on their own — without anyone editing this document, and often within a day. A
> reader who treats an F1 number here as current will be wrong, and cannot tell from the prose
> which figure is fresh.
>
> **So every F1 figure below carries the blob SHA it was measured from and the date.** Both
> measurements are recorded, because the older one is not superseded — it is traceable, and that
> traceability is what lets you re-measure:
>
> | measurement | F1 `origin/main` | `data/tracking.db` blob | measured | total rows | `resolved=1` |
> |---|---|---|---|---|---|
> | first correction | `6f492739` | `da6217d9` | 2026-10-02 | 3,080 | 1,452 |
> | re-measurement | `61ac4c65` | `e22d8a43` | 2026-10-03 | 3,172 | **1,584** |
>
> **Re-measure before use.** No clone and no credentials are needed — F1 is the one sport whose
> store is committed at all:
>
> ```sh
> cd F1_Predictor
> BLOB=$(git rev-parse origin/main:data/tracking.db)   # record this SHA with your figures
> git cat-file blob "$BLOB" > /tmp/tracking.db         # read the BLOB, not the working tree
>
> # total rows, and resolved rows — the two figures in the measurement table:
> sqlite3 /tmp/tracking.db "SELECT COUNT(*) FROM session_predictions;"
> sqlite3 /tmp/tracking.db "SELECT COUNT(*) FROM session_predictions WHERE resolved=1;"
>
> # the bucket table, on the bounds signals/trust.py's BUCKET_BOUNDS defines.
> # same bucketing as store.get_probability_buckets, so this reproduces its bands:
> sqlite3 -header -column /tmp/tracking.db "
> SELECT CASE WHEN predicted_prob < 0.3 THEN '0.0-0.3' WHEN predicted_prob < 0.4 THEN '0.3-0.4'
>             WHEN predicted_prob < 0.5 THEN '0.4-0.5' WHEN predicted_prob < 0.6 THEN '0.5-0.6'
>             WHEN predicted_prob < 0.7 THEN '0.6-0.7' ELSE '0.7-1.0' END AS bucket,
>        COUNT(*) AS n,
>        SUM(actual_outcome) AS hits,
>        ROUND(100.0 * SUM(actual_outcome) / COUNT(*), 1) AS hit_pct
>   FROM session_predictions WHERE resolved = 1
>  GROUP BY bucket ORDER BY MIN(predicted_prob);"
> ```
>
> Verified against blob `da6217d9`: 1,452 resolved, and the six bands below reproduce exactly. Add
> the band total to the resolved count as a check — every resolved row must land in exactly one
> band, so they sum to the same number.
>
> The other four sports' stores are untracked (below), so they cannot be re-measured this way:
> their `UNKNOWN`s are permanent rather than stale.

## Why the first version's counts were not reproducible

`git check-ignore -v data/tracking.db` at those SHAs:

```
NFL_Predictor  .gitignore:5:data/tracking.db
CFB_Predictor  .gitignore:7:data/*.db*
NBA_Predictor  .gitignore:10:data/tracking.db
PL_Predictor   .gitignore:8:data/tracking.db
F1_Predictor   exit 1 — tracked, so check-ignore does not report it
```

F1 is the sole exception: at `6f492739`, `git ls-tree origin/main -- data/tracking.db` → blob
`da6217d9`, 749,568 bytes, tables `session_predictions` + `championship_snapshots`. **The blob moves
— at `61ac4c65` it is `e22d8a43`, 778,240 bytes** (same two tables); the permanent fact is that it
is tracked, not the SHA. `.gitignore:6` also lists it, but
tracking wins (`--no-index` reports the rule, the default does not). `PL_Predictor`'s own suite
asserts this too: `tests/test_pick_record.py:141`
`test_a_gitignored_tracking_db_is_why_this_is_needed` **fails** if `check-ignore` exits non-zero.

## F1 `trust` buckets — from the committed blob

Bucketed on `predicted_prob` over `WHERE resolved = 1`, two measurements of the same committed
store. **Neither is current; each is what it was on its date.** Read the `n >= 30` column from
whichever measurement you are reasoning about — the floor verdict is stable across both, the rates
are not.

### Measured 2026-10-02 — blob `da6217d9` at F1 `origin/main` `6f492739` (1,452 `resolved=1`)

| bucket | n | hit % | clears `n >= 30` |
|---|---|---|---|
| 0.0-0.3 | 1136 | 12.5 | yes |
| 0.3-0.4 | 135 | 36.3 | yes |
| 0.4-0.5 | 40 | 42.5 | yes |
| 0.5-0.6 | 24 | 75.0 | **no** |
| 0.6-0.7 | 42 | 73.8 | yes |
| 0.7-1.0 | 75 | 78.7 | yes |

On these figures **five of six buckets clear the spec's `n >= 30` floor** (spec §`trust`; open
question 3). The five are monotone — 12.5 < 36.3 < 42.5 < 73.8 < 78.7 — but the **full** six-bucket
curve is **not**: the below-floor `0.5-0.6` band realises 75.0%, *above* `0.6-0.7`'s 73.8%. So the
original "the hit rate is **monotone**" claim was overstated even on its own figures; it holds only
over the bands the floor renders. F1 `trust` is supported by data.

### Measured 2026-10-03 — blob `e22d8a43` at F1 `origin/main` `61ac4c65` (1,584 `resolved=1`)

| bucket | n | hit % | clears `n >= 30` |
|---|---|---|---|
| 0.0-0.3 | 1235 | 12.2 | yes |
| 0.3-0.4 | 148 | 35.1 | yes |
| 0.4-0.5 | 44 | 38.6 | yes |
| 0.5-0.6 | 27 | 77.8 | **no** |
| 0.6-0.7 | 45 | 75.6 | yes |
| 0.7-1.0 | 85 | 81.2 | yes |

Every band grew, and not uniformly: `0.4-0.5` gained 4 picks, `0.5-0.6` gained 3.

**The conclusion still holds, but the shape of the evidence changed and must not be described as
before.** Precisely:

- **Still 5 of 6 over the floor.** The only band under it is `0.5-0.6` (n=27), so the floor is
  still withholding exactly the band too thin to publish.
- **The full six-band curve is NOT monotone.** There is one inversion: `0.5-0.6` realises **77.8%**
  on 27 picks, *above* `0.6-0.7`'s **75.6%** on 45 — a higher stated probability realised a lower
  rate. "Monotone" was true of the 2026-10-02 figures and is **false** of these.
- **Over the five bands that clear the floor, and so actually render, the curve is monotone
  non-decreasing**: 12.2 < 35.1 < 38.6 < 75.6 < 81.2. The one inversion sits entirely inside the
  band the floor withholds.
- **Enough to ship, on this evidence.** A dip confined to a band too thin to render cannot put a
  wrong ordering on the page, and the signal's premise — a higher stated probability has meant a
  higher realised rate — holds across everything a reader can see. That is weaker evidence than
  "monotone", it is evidence about 1,584 picks at one blob on one day, and the dip is small
  (2.2 points on 27 picks), so a single further refresh could move it either way. Re-measure rather
  than rely on it.

## Sport x signal

| signal | NFL | CFB | NBA | PL | F1 |
|---|---|---|---|---|---|
| `trust` | **BLOCKED on a production count.** Code ships: buckets `_TD_CONFIDENCE_BUCKETS` (`tracking/store.py:1380`, 50-60/60-70/70+), built in `_prop_markets:1445`. Resolved rows **UNKNOWN** | **BLOCKED on a production count.** Code ships: `_td_confidence_buckets` (`tracking/store.py:645`). Resolved rows **UNKNOWN** | **UNKNOWN.** 6 tables in schema (`tracking/store.py:23,33,47,54,63,72`); every row count **UNKNOWN**; no bucket code | **UNKNOWN.** 6 tables (`tracking/store.py:191,237,256,272,284,305`); row counts **UNKNOWN**; no probability *ranges* ship, only scalar `rps`/`brier`/`ignorance`/`n_matches` (`evaluate/calibration.py:47-50`) | **SUPPORTED.** Buckets above — 2026-10-02 (`da6217d9`, 1,452 resolved, monotone) and 2026-10-03 (`e22d8a43`, 1,584 resolved, one inversion, below the floor). **Bucket code now SHIPS**: this cell originally read "No bucket code — `tracking/store.py` has 0 `bucket` matches", which **PR #34** (`61ac4c65`) made false — `tracking/store.py` now has `get_probability_buckets` and `signals/trust.py` owns the bounds and the floor |
| `line_gap` | **BLOCKED** — `api/facts.py:509` `markets = [] if (started and stored is None) else ...`, so a started game with no stored pre-kickoff row has no quoted line at all | **UNKNOWN** | n/a | n/a | n/a |
| `post_game` | `game_predictions`, `player_prop_predictions` — **UNKNOWN** | same two tables — **UNKNOWN** | `game_player_outcomes`, `predictions` — **UNKNOWN** | `fixture_player_outcomes`, `predictions` — **UNKNOWN** | `session_predictions` — the only committed store measured, so the only one re-measurable: **3,080 rows / 1,452 resolved** at blob `da6217d9` (2026-10-02), **3,172 / 1,584** at `e22d8a43` (2026-10-03) |
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

**F1 `trust` can proceed now.** The data supports it (5/6 buckets over the floor; monotone across
the bands that render, with the one inversion below the floor). Only the bucket adapter was missing, and **PR #34** has since shipped it —
`signals/trust.py` owns the bounds and the floor over `store.get_probability_buckets`, so this
recommendation is now spent rather than open. The one qualifier: the curve is monotone **over the
rendered bands only**, with one inversion below the floor (2026-10-03, blob `e22d8a43`).

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