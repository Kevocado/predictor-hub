# Review Prompt — Player-Model Accuracy Remediation (2026-09-27)

> Copy everything below the line into a new Claude Code / OpenCode session.
> It is written to be self-contained: the reviewer needs no prior context from
> this session, and should not have to ask what was meant.

---

## Your task

You are reviewing a cross-repository ML remediation in a sports-prediction
monorepo. Four sibling repos, each a FastAPI + React app with its own model
pipeline, all maintained in one working directory:

```
/Users/sigey/Documents/Projects.nosync/
├── CFB_Predictor/     college football  (port of NFL_Predictor)
├── NFL_Predictor/     american football (the original)
├── PL_Predictor/      premier league    (the most mature)
├── Sports_Predictor/  the React dashboard that consumes all of them
└── predictor-hub/     static index page + cross-repo docs
```

All four have GitHub remotes under `github.com/Kevocado/*`. Changes are meant to
land as PRs.

**What we were asked to do:** the owner reported that "the total yards
predictions for the american football predictors are pretty off", and asked for a
comprehensive review of every player model across all three sports, with
attention to new and interaction features.

**What we found:** the reported symptom is the visible tip of a four-layer
problem, and it is much worse than "pretty off".

---

## Read these first, in order

1. `/Users/sigey/Documents/Projects.nosync/.superpowers/audit-2026-09-27-total-yards.md`
   — the raw live-endpoint forensics. Every number in the spec traces here.
2. `predictor-hub/docs/superpowers/specs/2026-09-27-player-model-accuracy-design.md`
   — the design and what was implemented.
3. `predictor-hub/docs/superpowers/plans/2026-09-27-player-model-accuracy-remediation.md`
   — 10 tasks, most not started.
4. `PL_Predictor/tests/test_player_goals_serving_defects.py` — the 7 new
   regression tests.
5. `git -C PL_Predictor diff` for `models/player_goals.py`, `models/manifest.py`,
   `api/routes.py`, `tests/test_manifest_market_overrides.py`.

---

## The core finding

The dashboard labels a number "Team Yardage Predictions". That number is the sum
of every active player's position-specific yardage projection across the entire
roster. Measured live on the current deployment:

| | CFB wk5 | NFL wk3 | Reality |
|---|---|---|---|
| teams with a figure | 118 | 32 | — |
| median | **841** | **1110** | 300–450 (CFB) / 330–400 (NFL) |
| max | 1343 | 1452 | — |
| in the realistic band | **0** | **0** | 100% should be |

Two independent errors compound:

- **Over-counting.** Philadelphia's 1452 adds four quarterbacks' passing
  projections (217 + 199 + 185 + 63). PHI has one starter.
- **Under-counting the real thing.** `POSITION_MARKETS` gives QB no
  `rushing_yards`, RB no `receiving_yards`, WR/TE no `rushing_yards`. Verified:
  0/112 NFL QBs have `rushing_yards`; 0/204 RBs have `receiving_yards`. Every
  omitted bucket is a rushing/receiving figure, so a total built this way cannot
  represent net yardage even in principle.

The decisive insight from the data-availability research: **the share constraint
is an exact identity, not an approximation.** `Σ_p(rushing + receiving)` equals
the team's `totalYards` in 355/356 CFB team-games (median error 0.00) and 511/512
NFL team-games (mean diff −0.0098 yds). So the architecture is settled —
**project the team total, then allocate by share** — and a roster sum that misses
by 2.6× is a category error, not a noisy estimate.

Verified sources, with cost:

| Sport | Source | Rows | Cost |
|---|---|---|---|
| CFB | `cfbd.GamesApi.get_game_team_stats(year, week)` → `totalYards` | ~19,000 FBS team-games 2004–2025 | 1 call per season-week, ~330 one-time |
| NFL | `nflverse-data` release `stats_team/week/{y}.parquet`, 138 cols, zero nulls | 14,531 team-games 1999–2025 | ~0.2 MB/season, no API key. **No `nfl_data_py` import function wraps it** |
| PL | Understat `rosters` block: per-player `time`, `xG`, `xA`, `key_passes` | already being fetched | **zero extra HTTP** (`understat_shots.py` reads only `data["shots"]` and discards `rosters`) |

Blocked: FBRef (possession, passing, pass attempts) is behind a Cloudflare
challenge — 403 to plain *and* TLS-impersonating clients. Do not build on it.

---

## What was implemented (all in `PL_Predictor`, TDD)

Diff is +156/−20 across 4 source files plus 1 new test file. Full suite: **346
passed, 0 failed**.

### 1. `was_home` was silently dropped at serving time

`predict_goal_contribution` took no `is_home`. `was_home` **is** in
`BASE_FEATURES` (`evaluate/goal_contribution_research.py:33`) and **is** fitted,
but neither `player_form.blended_current_form` nor `current_start_features`
emits that key, so the comprehension's `or 0.0` default scored **every home
player with `was_home = 0.0`**. The fitted home-advantage coefficient
contributed a constant offset rather than an effect. The served model was not
the model that had been validated.

Fixed by adding an explicit `is_home` parameter and special-casing the key,
mirroring the pattern `predict_player` already used for its position-rate models
(`player_goals.py:283`).

### 2. `max()` is not a sound probability combiner

```python
pred["anytime_goal_contribution_prob"] = max(
    direct_contribution, pred["anytime_goal_prob"], pred["anytime_assist_prob"])
```

- It mixes an *event* with two of its own *components*, so the inequality
  `G+A ≥ max(goal, assist)` is guaranteed by code, not by modelling.
- `max(a, b) = (a+b)/2 + |a-b|/2` — the upward bias is **half the inter-model
  disagreement**. It therefore shrinks least toward the base rate exactly for
  the players both models are least sure about. That is regression-to-the-mean
  failure in reverse.
- It has no fitted parameter, so nothing about it was ever validated.

Replaced with `blend_contribution(direct, union, weight)` — a convex mixture
whose weight is grid-searched by `_fit_blend_weight` on the held-out
calibration season, minimising Brier. The Poisson union is Platt-calibrated on
the same slice so neither side of the mixture is privileged. A mixture can land
below either component, which is information about which model to trust where.

Behaviour with the direct model unavailable is unchanged: `blend_contribution(None,
union, None)` returns the union, exactly as before.

### 3. `shots_scale` was dead code

`predict_player` reads a `context` object to scale shot estimates, but
`rank_team_players` had no `context` parameter and `_rank_fixture_players` never
passed one. So `shots_scale == 1.0` on **every live call** and
`expected_shots` / `expected_shots_on_target` were never scaled by the team's own
shot volume. This is the direct cause of an observed
`anytime_shot_on_target_prob = 0.9781` on a defender — the missing divisor was
the only thing damping it.

Fixed by threading `context=models.get("context")` from `routes.py`.

### 4. Reverted the decayed O/U 2.5 override

`MARKET_MODEL_OVERRIDES = {"over_2_5": "covariate_poisson"}` → `{}`.

The evidence had not merely decayed, it had **reversed**. On the live
2026-09-14 manifest, O/U 2.5:

| model | log loss | Brier | rank |
|---|---|---|---|
| bivariate_poisson | **0.683763** | **0.245133** | 1st |
| dixon_coles | 0.684296 | 0.245331 | 2nd |
| ml_scoreline | 0.689441 | 0.248157 | 3rd |
| covariate_poisson ← was serving | 0.689638 | 0.248153 | **4th** |

Every O/U 2.5 prediction was coming from the worst of four candidates — worse
than `ml_scoreline` by 0.000197, the reverse of the study's own ordering, and
behind bivariate_poisson by 0.00588 (~20× the original study's margin, opposite
direction). The original comment said to revisit on a stronger or more
consistent result; one appeared. The per-market override **mechanism** is kept
and still tested; a new test pins the empty default.

---

## Review these, in priority order

### A. The three player-model fixes

- Is `blend_contribution` + `_fit_blend_weight` statistically sound? Is a 21-point
  grid coarse enough? Should the pooling be in **logit space** rather than
  probability space?
- **Precedence:** when `rates` already contains a `was_home` key, my
  implementation lets the `is_home` argument win. Is that right? Argue it from
  the training frame's provenance, not convenience.
- Could threading `context` change any field *other* than `expected_shots` /
  `expected_shots_on_target`? Prove it doesn't.
- Are the 7 regression tests actually load-bearing, or do any of them pass
  vacuously?

### B. The O/U 2.5 revert

I reasoned from `models/manifest.json`. Independently verify the reversal is
real and that `{}` is the right response, versus re-tuning `covariate_poisson`
(now that it is no longer carrying a market). Note EXP-2026-14 already found
`ml_scoreline` beats all three alternatives on *every* market metric over 5
folds — check whether that makes the override question moot, or whether O/U 2.5
is genuinely different.

### C. The evaluation gap — this is the most important thing

**No walk-forward evaluation was run for the blend change.** It is unit-tested
and logically sound, but untested against the metric that matters.

Worse: the direct G+A classifier is currently **dark in production** — 0 of 160
live rows come from it, because `_get_ready_goal_contribution_model()` returns
`None` until the 24h warm-up completes. It becomes live the moment the cache
warms. And in the project's own ledger it has never itself been walk-forward
scored — only the qualitative conclusion that it "beat the Poisson-union
baseline" is recorded, with no per-fold numbers.

Propose the exact experiment: which folds, which metrics, what promotion bar,
and whether the old `max()` should be included as a scored baseline arm.

### D. Sanity-check the research claims the spec rests on

Do not trust them. Re-derive, in particular:

- That `Σ_p(rushing + receiving) == team totalYards` is an exact identity.
- That nflverse has **no** `player_stats` file for 2025 or 2026 (this drives the
  entire NFL plan; if it is wrong, several tasks are unnecessary).
- The O/U 2.5 metric table.

---

## Conventions you must respect

`PL_Predictor` is the most disciplined of the three. Its rules are in
`docs/AI_CONTINUITY.md` and must be followed:

- **Two-gate promotion rule.** A candidate goes live only if it improves the
  walk-forward mean **and** holds on the single most recent season. The ledger
  records three separate tunings that improved the mean and regressed 2025-26,
  which it correctly reads as evidence that 2025-26 is non-stationary. Its own
  words: *"an average win driven by older folds while the most recent one
  regresses is treated as a walk-forward-specific artifact, not a real gain."*
- **Never delete a failed experiment.** *"Negative evidence prevents repeated
  work."* Roughly 22 are logged with per-fold numbers.
- Docstrings that record *why*, including the bugs that were fixed and the
  reasoning behind deviations. Long prose is the house style, not a defect.
- `PYTHONPATH=src` is required; `pip install -e` silently no-ops on this machine.
- The full suite takes ~7 minutes (346 tests). Use `-p no:randomly`.

`NFL_Predictor` and `CFB_Predictor` are a near-verbatim port pair with far less
process — no CI runs tests or a Python linter in **any** of the three repos.

---

## Findings that were RETRACTED — do not chase these

**"CFB conference labels are corrupted and poison the `conference_game` model
feature."** This was a **false positive** and is retracted. Verified against the
live CFBD API (`/teams?year=2026&classification=fbs`, 138 FBS teams): Big Ten 18,
ACC 17, SEC 16, Big 12 16, Sun Belt 14, American 14, Mid-American 13, Mountain
West 10, C-USA 10, Pac-12 8, FBS Independents 2 — correct for 2026 after the
realignment. USC/UCLA/Washington/Oregon really are Big Ten; Stanford/California
really are ACC; the Pac-12 really did rebuild around Oregon State, Washington
State, Boise State, SDSU, Fresno State, Utah State, Colorado State and Texas
State. The original "ground truth" was a stale pre-realignment map. The odd
conference *names* in the raw payload (`Michigan`, `Wisconsin`, `Ohio`,
`Minnesota`, `So. Cal.`) are genuine DIII conferences (MIAA, WIAC, OAC, UMAC,
SCAC), visible only because `classification=fbs` is filtered client-side.
**No fix needed.**

**"NFL's roster-fallback feature row uses the wrong non-`_roll` keys."** Does not
exist in NFL. Both local HEAD and `origin/main` build the fallback as
`pd.Series({col: 0.0 for col in PLAYER_FEATURE_COLUMNS})`, correctly. That bug
is **CFB-only** (`CFB_Predictor/src/cfb_predictor/api/routes.py:501`).

**"PL has no player-minutes / player-xG-xA / fantasy-points model."** All three
are false — each exists and serves live numbers. The genuine gaps are a
**clean-sheet model** and **opponent-scaled keeper saves**.

---

## Unfinished, and known-so

- The yardage backfills (NFL, CFB) and the NFL serving fixes are **specified, not
  implemented** (plan tasks 2–6).
- All six PL feature experiments are **specified, not run** (task 8). Each needs
  its own two-gate evaluation; batching them is exactly what EXP-2026-03/11/17/21
  show going wrong.
- **Task 9 is deliberately left to the owner** and should stay that way: PL's
  published metric is `min()` of four candidates on the *same* 380-fixture
  `val_df` it is reported on (`manifest.py:272` vs `:369`; the two RPS values
  agree to 14 significant figures), compounded by 7 tuned hyperparameters and a
  persistent `optuna_study.db` with `load_if_exists=True`. Changing what that
  number *means* is a product decision about the dashboard headline and README.
- **Task 1** is a choice for the owner: delete the "Total Yards" panel, or
  relabel it "Roster Yardage Projection (not a team total)" with a player count.
  It is a real projection, just of the wrong quantity.

---

## Environment gotchas that will bite you

- **Every repo's local `main` is behind `origin/main`** — PL by 54, NFL by 37,
  Sports_Predictor by 25, CFB by 33. Branch off `origin/main`. Do **not** `git
  pull` the local `main` in `NFL_Predictor`: it drags in automated snapshot
  commits that regenerate the (equally broken) `public_snapshot.json`.
- **Uncommitted work exists and is not ours to clobber:**
  `CFB_Predictor/.github/workflows/deploy-azure-cfb.yml`,
  `PL_Predictor/.github/workflows/deploy-azure.yml`,
  `Sports_Predictor/{.github/workflows/deploy-azure.yml,src/api/client.ts}`, and
  4 dirty `PL_Predictor/models/*_xgb.json` binaries from a retrain (tracked —
  exclude them from any PR or `manifest.json` ships out of sync).
- `PL_Predictor` has **five registered git worktrees**, two of which live under
  `/Users/sigey/Documents/Projects/` (not `Projects.nosync/`) and two of which
  edit the same `player_goals.py` / `manifest.py` we just changed — they will
  conflict on merge.
- `PL_Predictor/.github\nF1_Predictor` is a real **directory**, not a symlink,
  whose name contains a literal backslash-n, holding a 5-deep chain of empty
  dirs. Untracked, unignored, invisible to `ls`/`find`/`git status`. Fix with
  `rm -rf '.github\nF1_Predictor'` (quote it).
- The current deployment is the **VPS**, not Azure:
  `https://sports.40-160-91-131.sslip.io/?sport=cfb`, API proxied at `/cfb/api/*`
  and `/nfl/api/*`. The repo's `Sports_Predictor/Caddyfile` is stale and does not
  describe this. The `*-predictor.proudbay-f56b8dfa.eastus2.azurecontainerapps.io`
  hosts are an **older build**. The VPS build has already fixed the phantom-row
  bug (101 → 0) but no structural cause.
- `PL_Predictor`'s `docs/AI_CONTINUITY.md` is **stale relative to the code** — the
  manifest was retrained 2026-09-14 and September's Sportsbook-API switch, the
  parlay spec, and the player-shots market are entirely undocumented. Check
  `models/manifest.json`, not the doc. `EXP-2026-05` is used twice.
- CFBD's real cap is ~2,200 calls (observed via the `X-CallLimit-Remaining`
  header), roughly 2× the 1,000/month asserted in
  `CFB_Predictor/src/cfb_predictor/config.py`. The ~330-call backfill is
  one-time and must never be scheduled.
- `docs/superpowers/specs/2026-09-10-parlay-builder-design.md` directly
  contradicts `AI_CONTINUITY.md:21` and the README ("never create a parlay
  recommendation"). Flag to the owner before either lands.

---

## What a good review looks like

Useful: finding a real regression, showing a fix is wrong or incomplete,
identifying a leak or a train/serve skew I missed, questioning whether a metric
is being read correctly, or telling us plainly that a fix is correct but
premature because its evaluation is missing.

Not useful: restating the spec back to us, or re-litigating a retracted finding.
