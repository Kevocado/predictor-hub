# NBA feature pipeline: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add defence/pace, schedule load, a causal power rating, opponent adjustment, player-minutes availability and style-matchup features to the NBA models behind a block framework that scores each block against the previous best on identical held-out games, and fix the three defects found on the way (7 constant-zero features, unscaled linear models, silent box-score cache staleness).

**Architecture:** Features are grouped into BLOCKS (`power`, `schedule`, `form`, `adjusted`, `availability`, `matchup`). `features/build.py` composes the selected blocks; `DEFAULT_BLOCKS = ()` keeps production unchanged until a block clears the evaluation bar. A model's manifest records the blocks and columns it was fitted on, and serving rebuilds exactly those. A shared scaled linear builder is used by both the candidate race and the served models. `tools/feature_block_eval.py` scores a block set with paired-bootstrap intervals and the calibration gap, and refuses to compare if the held-out games differ.

**Tech Stack:** Python 3.13 (uv), pandas, numpy, scikit-learn, FastAPI, pytest. ESPN public endpoints for data. No new dependencies.

**Spec:** `docs/superpowers/plans/2026-10-08-nba-feature-blocks.md` (the approved design; Kevin approved blocks 1-3, the player-box fetch and style matchups on 2026-10-08). The matchup SIGNAL (hub component, NBA adapter, AI facts) is a separate plan: `2026-10-08-nba-matchup-signal-impl.md`.

**Verified:** every module, test and edit below was built and run against NBA_Predictor `main` at `ddf3557`; with all tasks applied the full suite is **937 passed, 23 skipped** (main alone: about 870).

## Global Constraints

- NBA stays an INDEPENDENT model: no betting lines as a feature, benchmark or dependency.
- Python 3.13 for NBA: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider`. Run the FULL suite before reporting anything.
- Tests never touch the network. ESPN data comes from fixtures (`tests/fixtures/espn_summary_sample.json`) or injected fakes.
- Every feature for game g uses only games strictly before g's date. The one stated exception is the availability block, which reads who actually played IN g (the training stand-in for the reported-Out list at tip-off); it never reads a later game. Both properties are tested.
- Train/serve parity: a model is only ever scored on the columns it was fitted on, rebuilt the way it was fitted. A missing fitted column is an error, never a silent zero.
- Recorded picks are immutable; nothing here rewrites any stored prediction.
- Never `git add -A` (it has swept untracked directories into commits); add files by name. Never push to main; branch and PR. Use a git worktree, never switch branches in a shared clone.
- A block ships (joins `DEFAULT_BLOCKS`) only if its paired-bootstrap 95% intervals exclude zero on the metrics it claims AND the 5-bucket calibration gap does not widen, scored on the IDENTICAL held-out games (Task 14).
- Read the existing code each task touches before editing; the diffs below were made against `ddf3557` and may need small adjustments if main has moved. If a diff does not apply, make the same edit by hand and re-run the task's tests.

## File structure

New: `src/nba_predictor/features/{power_rating,schedule_load,team_form,opp_adjust,availability,matchup}.py`, `src/nba_predictor/models/linear.py`, `tools/feature_block_eval.py`, `tests/feature_fixtures.py`, `tests/fixtures/espn_summary_sample.json`, and one `tests/test_*.py` per module (listed per task).
Modified: `data/espn.py` (box fields, cache freshness, starter flag), `pipeline/ingest.py` (BOX_FIELDS, player fetch, serving), `pipeline/backfill.py` (player box, atomic write), `pipeline/retrain.py` (blocks in, manifest columns out), `features/build.py` (block composition, legacy columns), `models/candidate_race.py` and `models/game_outcome.py` (shared scaled linear builder), and five existing test files whose fixtures or assertions encoded the old behaviour.

## PR plan

PR-F1: Tasks 1-3 (fixtures, box widening, scaled linear). PR-F2: Tasks 4-10 (the six block modules and the player fetch; all inert). PR-F3: Tasks 11-13 (composition, retrain/serving wiring, evaluation tool). Then Task 14 (data run and one evaluation PR per block). Each PR: full suite green, red-checks pasted, CodeRabbit gate, no deploy.

---

## Task 1: Shared synthetic-league fixtures

**Files:** Create `tests/feature_fixtures.py`.

**Interfaces:** Produces `make_games(n_days, seed, start)` (completed games with every box field, a sparse schedule so rest days vary), `perturb_from(games, cut_date)` (scrambles results and boxes from a date on), `with_upcoming(games, n)` (last n games become upcoming: no result, no box), `make_player_games(games, seed, miss_prob)` (eight players per team per game, each regular misses with probability `miss_prob`), `perturb_players_from(player_games, cut_date)`.

- [ ] **Step 1: Create the file**

```python
"""Synthetic league for feature tests: deterministic, offline, with every box field."""
import numpy as np
import pandas as pd

TEAMS = ["BOS", "MIA", "LAL", "GSW", "DEN", "CHI"]
BOX_FIELDS = ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov", "ast", "stl", "blk", "pf"]


def _team_box(rng: np.random.Generator, skill: float) -> dict:
    fga = int(rng.normal(88, 4))
    fg_pct = float(np.clip(0.46 + 0.02 * skill + rng.normal(0, 0.03), 0.35, 0.58))
    fgm = int(round(fga * fg_pct))
    fg3a = int(np.clip(rng.normal(35, 4), 20, 50))
    fg3m = int(min(fgm, round(fg3a * np.clip(0.36 + rng.normal(0, 0.04), 0.2, 0.5))))
    fta = int(np.clip(rng.normal(22, 4), 8, 40))
    ftm = int(round(fta * np.clip(0.78 + rng.normal(0, 0.05), 0.5, 0.95)))
    return {
        "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta,
        "oreb": int(np.clip(rng.normal(10, 2), 3, 20)), "dreb": int(np.clip(rng.normal(33, 3), 20, 45)),
        "tov": int(np.clip(rng.normal(13, 3), 4, 25)), "ast": int(np.clip(rng.normal(25, 4), 12, 40)),
        "stl": int(np.clip(rng.normal(7, 2), 1, 15)), "blk": int(np.clip(rng.normal(5, 2), 0, 12)),
        "pf": int(np.clip(rng.normal(19, 3), 8, 30)),
        "pts": 2 * (fgm - fg3m) + 3 * fg3m + ftm,
    }


def make_games(n_days: int = 120, seed: int = 7, start: str = "2025-10-22") -> pd.DataFrame:
    """Every day three games among six teams, all completed, home/away columns like the real frame."""
    rng = np.random.default_rng(seed)
    skill = {t: float(rng.normal(0, 1)) for t in TEAMS}
    rows, gid = [], 0
    for d in range(n_days):
        day = (pd.Timestamp(start) + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        order = list(rng.permutation(TEAMS))
        for i in range(0, 2 * int(rng.choice([1, 2, 3], p=[0.3, 0.4, 0.3])), 2):
            home, away = order[i], order[i + 1]
            hb, ab = _team_box(rng, skill[home] + 0.3), _team_box(rng, skill[away])
            row = {"game_id": f"g{gid:05d}", "game_date": day, "home_team": home, "away_team": away}
            for k, v in hb.items():
                row[f"home_{k}"] = v
            for k, v in ab.items():
                row[f"away_{k}"] = v
            row["home_win"] = int(hb["pts"] > ab["pts"] or (hb["pts"] == ab["pts"] and rng.random() < 0.5))
            rows.append(row)
            gid += 1
    return pd.DataFrame(rows)


def perturb_from(games: pd.DataFrame, cut_date: str, seed: int = 99) -> pd.DataFrame:
    """Scramble results and box scores of every game ON OR AFTER cut_date; earlier games are untouched."""
    rng = np.random.default_rng(seed)
    out = games.copy()
    mask = out["game_date"] >= cut_date
    for side in ("home", "away"):
        for field in BOX_FIELDS + ["pts"]:
            col = f"{side}_{field}"
            if col in out.columns:
                out.loc[mask, col] = (out.loc[mask, col] * rng.uniform(0.6, 1.4, mask.sum())).round()
    out.loc[mask, "home_win"] = rng.integers(0, 2, mask.sum())
    return out


def with_upcoming(games: pd.DataFrame, n_upcoming: int = 3) -> pd.DataFrame:
    """The last n games turned into UPCOMING games: no result, no box score (what serving sees)."""
    out = games.copy()
    idx = out.index[-n_upcoming:]
    for side in ("home", "away"):
        for field in BOX_FIELDS + ["pts"]:
            col = f"{side}_{field}"
            if col in out.columns:
                out.loc[idx, col] = np.nan
    out.loc[idx, "home_win"] = np.nan
    return out


ROSTER = [  # (player slot, minutes, starter, points, rebounds, assists)
    ("p1", 35, True, 26, 7, 6), ("p2", 32, True, 19, 5, 5), ("p3", 30, True, 14, 6, 3), ("p4", 28, True, 11, 4, 2),
    ("p5", 26, True, 9, 7, 1), ("p6", 21, False, 8, 3, 2), ("p7", 17, False, 6, 2, 1), ("p8", 12, False, 3, 2, 1),
]


def make_player_games(games: pd.DataFrame, seed: int = 11, miss_prob: float = 0.12) -> pd.DataFrame:
    """Eight players per team per game. Each regular misses a game with probability `miss_prob`."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, g in games.iterrows():
        for team in (g["home_team"], g["away_team"]):
            for slot, minutes, starter, pts, reb, ast in ROSTER:
                if slot != "p8" and rng.random() < miss_prob:
                    continue
                rows.append({"game_id": g["game_id"], "game_date": g["game_date"], "team": team, "player_id": f"{team}_{slot}",
                             "minutes": float(minutes + rng.integers(-3, 4)), "starter": starter,
                             "points": float(pts + rng.integers(-3, 4)), "rebounds": float(reb), "assists": float(ast)})
    return pd.DataFrame(rows)


def perturb_players_from(player_games: pd.DataFrame, cut_date: str, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = player_games.copy()
    mask = out["game_date"] >= cut_date
    out.loc[mask, "minutes"] = (out.loc[mask, "minutes"] * rng.uniform(0.2, 1.8, mask.sum())).round()
    return out[~(mask & (rng.random(len(out)) < 0.4))]
```

- [ ] **Step 2: Smoke it**

Run: `uv run --python 3.13 python -c "from tests.feature_fixtures import make_games, make_player_games; g=make_games(60); print(len(g), len(make_player_games(g)))"`
Expected: two positive integers; no error

- [ ] **Step 3: Commit** `git add tests/feature_fixtures.py && git commit -m "test: a synthetic league for feature tests"`

## Task 2: Widen the box score, and refuse stale cached box scores

**Why:** the model parses fg3a and ftm but drops them; ESPN also gives assists, steals, blocks and fouls. `enrich_with_boxscores` skips any game whose cached box lacks a required field, so widening `BOX_FIELDS` without refreshing the cache would silently drop games from training. Verified against a real ESPN summary (`assists`, `steals`, `blocks`, `fouls`; player `starter`, `didNotPlay`, label `MIN`).

**Files:** Modify `src/nba_predictor/data/espn.py`, `src/nba_predictor/pipeline/ingest.py`; create `tests/fixtures/espn_summary_sample.json`, `tests/test_espn_box_fields.py`; modify `tests/test_backfill.py`, `tests/test_retrain_freshness.py`, `tests/test_pipeline_ingest.py`, `tests/test_features_build.py` (fixtures).

**Interfaces:** Produces `espn.BOXSCORE_REQUIRED_FIELDS` (13 names), `ingest.BOX_FIELDS = list(espn.BOXSCORE_REQUIRED_FIELDS)`, player rows with `starter: bool`.

- [ ] **Step 1: Save a trimmed real ESPN summary as the fixture**

```bash
mkdir -p tests/fixtures
curl -s "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401898388" -o /tmp/espn_sample.json
python3 - <<'PY'
import json
d = json.load(open("/tmp/espn_sample.json"))
box = d["boxscore"]
trim = {"boxscore": {"teams": box["teams"], "players": []}}
for tb in box["players"]:
    grp = tb["statistics"][0]
    trim["boxscore"]["players"].append({"team": tb["team"], "statistics": [{"labels": grp["labels"], "athletes": grp["athletes"][:2]}]})
json.dump(trim, open("tests/fixtures/espn_summary_sample.json", "w"), indent=1)
PY
```
(If that event id is ever unavailable use any completed NBA event id; the test asserts the MEM/ATL numbers below, so keep event 401898388 if you can.)

- [ ] **Step 2: Write the failing test**

```python
import json
from pathlib import Path

import pytest

from nba_predictor.data import espn
from nba_predictor.pipeline import ingest

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "espn_summary_sample.json").read_text())


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(espn, "ESPN_CACHE_DIR", tmp_path)
    calls = []

    def fake_fetch(url, params=None):
        calls.append(params)
        return FIXTURE

    monkeypatch.setattr(espn, "_fetch_json", fake_fetch)
    return calls


def test_team_box_keeps_assists_steals_blocks_fouls_and_three_point_attempts(cache):
    box = espn.get_boxscore("401898388")
    for team in box.values():
        for field in ingest.BOX_FIELDS:
            assert field in team, field
    assert box["MEM"]["fg3a"] == 43 and box["MEM"]["fg3m"] == 18
    assert box["MEM"]["ast"] == 32 and box["MEM"]["stl"] == 13 and box["MEM"]["blk"] == 3 and box["MEM"]["pf"] == 26
    assert box["MEM"]["ftm"] == 28 and box["MEM"]["fta"] == 37


def test_a_cached_box_score_missing_the_new_fields_is_refetched_not_reused(cache, tmp_path):
    espn._save_cache("boxscore", "401898388", {"MEM": {"fgm": 1, "fga": 2, "fg3m": 0, "tov": 1, "oreb": 1, "dreb": 1, "fta": 1}})
    box = espn.get_boxscore("401898388")
    assert len(cache) == 1, "the stale cache entry must trigger a fresh fetch"
    assert "ast" in box["MEM"]


def test_a_fresh_cache_is_reused_without_a_request(cache):
    espn.get_boxscore("401898388")
    espn.get_boxscore("401898388")
    assert len(cache) == 1


def test_enrich_never_silently_drops_a_game_whose_cache_was_stale(cache):
    espn._save_cache("boxscore", "401898388", {"MEM": {"fgm": 1}, "ATL": {"fgm": 1}})
    games = [{"game_id": "401898388", "game_date": "2026-10-05", "home_team": "MEM", "away_team": "ATL",
              "completed": True, "home_pts": 132, "away_pts": 123}]
    enriched = ingest.enrich_with_boxscores(games)
    assert enriched[0]["home_ast"] == 32 and enriched[0]["away_fg3a"] is not None
    frame = ingest.to_training_frame(enriched)
    assert len(frame) == 1 and "home_ast" in frame.columns


def test_player_rows_carry_starter_and_skip_players_who_did_not_play(cache):
    rows = espn.get_player_boxscore("401898388")
    assert rows and all("starter" in r for r in rows)
    assert any(r["starter"] for r in rows)
    assert all(r["minutes"] > 0 for r in rows)
    assert len(rows) == 4, "the fixture keeps two athletes per team"


def test_a_cached_player_box_without_starter_is_refetched(cache):
    espn._save_cache("player_boxscore", "401898388", {"rows": [{"player_id": "1", "team": "MEM", "minutes": 20.0}]})
    rows = espn.get_player_boxscore("401898388")
    assert len(cache) == 1 and all("starter" in r for r in rows)
```

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_espn_box_fields.py`
Expected: FAIL (`espn.BOXSCORE_REQUIRED_FIELDS` / `starter` not defined)

- [ ] **Step 3: Edit `data/espn.py`**

```diff
diff --git a/src/nba_predictor/data/espn.py b/src/nba_predictor/data/espn.py
index ac0bfe3..20c53c2 100644
--- a/src/nba_predictor/data/espn.py
+++ b/src/nba_predictor/data/espn.py
@@ -182,6 +182,19 @@ _STAT_KEYS = {
     "defensiveRebounds": ("dreb", None),
     "turnovers": ("tov", None),
+    "assists": ("ast", None),
+    "steals": ("stl", None),
+    "blocks": ("blk", None),
+    "fouls": ("pf", None),
 }
 
+#: Every team box field a training row needs. A cached box score missing any of these is STALE: it was
+#: fetched before the field was parsed, and using it would silently drop the game from training.
+BOXSCORE_REQUIRED_FIELDS = ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov", "ast", "stl", "blk", "pf")
+
+
+def _boxscore_is_fresh(cached: dict | None) -> bool:
+    teams = [t for t in (cached or {}).values() if isinstance(t, dict)]
+    return bool(teams) and all(all(f in t for f in BOXSCORE_REQUIRED_FIELDS) for t in teams)
+
 
 def _parse_team_box(team_block: dict) -> dict:
@@ -213,5 +226,5 @@ def get_boxscore(event_id: str) -> dict:
     """
     cached = _load_cache("boxscore", event_id)
-    if cached is not None:
+    if cached is not None and _boxscore_is_fresh(cached):
         return cached
 
@@ -245,5 +258,5 @@ def get_player_boxscore(event_id: str) -> list[dict]:
     """
     cached = _load_cache("player_boxscore", event_id)
-    if cached is not None:
+    if cached is not None and all("starter" in r for r in cached["rows"]):
         return cached["rows"]
 
@@ -267,4 +280,5 @@ def get_player_boxscore(event_id: str) -> list[dict]:
                         "team": abbr,
                         "position": (athlete.get("position") or {}).get("abbreviation", ""),
+                        "starter": bool(entry.get("starter")),
                         "minutes": _to_float(stats.get("MIN")),
                         "points": _to_float(stats.get("PTS")),
```

- [ ] **Step 4: Edit `pipeline/ingest.py` (BOX_FIELDS only)**

```diff
diff --git a/src/nba_predictor/pipeline/ingest.py b/src/nba_predictor/pipeline/ingest.py
index 0df3469..d2b4193 100644
--- a/src/nba_predictor/pipeline/ingest.py
+++ b/src/nba_predictor/pipeline/ingest.py
@@ -25,5 +28,5 @@ from nba_predictor.pipeline.retrain import run_retrain_pipeline
 from nba_predictor.tracking import store
 
-BOX_FIELDS = ["fgm", "fga", "fg3m", "tov", "oreb", "dreb", "fta"]
+BOX_FIELDS = list(espn.BOXSCORE_REQUIRED_FIELDS)
```

- [ ] **Step 5: Run the new tests**

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_espn_box_fields.py`
Expected: 6 passed

- [ ] **Step 6: Widen the existing 7-field fixtures with this one-off script, then review `git diff tests/`**

Save the script below as `/tmp/widen_box_fixtures.py`. Existing tests build 7-field boxes; they now fail (11 in `test_backfill.py`, 6 in `test_pipeline_ingest.py`, 1 in `test_retrain_freshness.py`). Save and run:

```python
"""One-off: widen the 7-field box-score fixtures in existing tests to the full BOX_FIELDS set."""
import re
import sys

NEW = {"fg3a": 30, "ftm": 15, "ast": 22, "stl": 7, "blk": 4, "pf": 19}


def widen_flat(text: str) -> str:
    def repl(m):
        side, value, tail = m.group(1), m.group(2), m.group(3)
        extra = ", ".join(f'"{side}_{k}": {("None" if value == "None" else v)}' for k, v in NEW.items())
        return f'"{side}_fta": {value}, {extra}{tail}'
    return re.sub(r'"(home|away)_fta": (\d+|None)(,?)', repl, text)


def widen_nested(text: str) -> str:
    def repl(m):
        extra = ", ".join(f'"{k}": {v}' for k, v in NEW.items())
        return f'"fta": {m.group(1)}, {extra}}}'
    return re.sub(r'"fta": (\d+)\}', repl, text)


def widen_loop(text: str) -> str:
    def repl(m):
        indent, var = m.group(1), m.group(2)
        extra = "".join(f'{indent}{var}[f"{{side}}_{k}"] = {v}\n' for k, v in NEW.items())
        return m.group(0) + extra
    return re.sub(r'^( *)(g)\[f"\{side\}_fta"\] = \d+\n', repl, text, flags=re.M)


for path in sys.argv[1:]:
    src = open(path).read()
    out = widen_loop(widen_nested(widen_flat(src)))
    if out != src:
        open(path, "w").write(out)
        print("widened", path)
```

```bash
python3 /tmp/widen_box_fixtures.py tests/test_backfill.py tests/test_retrain_freshness.py tests/test_pipeline_ingest.py tests/test_features_build.py
```

- [ ] **Step 7: Replace the three tests that asserted the old zero-fill (they encode the defect)**

In `tests/test_features_build.py` replace `test_build_training_frame_fills_missing_optional_columns_with_zero` and delete `test_build_training_frame_respects_precomputed_optional_columns`; in `tests/test_missing_value_feature_provenance.py` delete `test_missing_value_is_filled_with_a_constant_zero_not_from_the_stub` and `test_a_real_measured_missing_value_is_indistinguishable_from_the_default`. The replacements are asserted in Task 11 (they need the new `FEATURE_COLUMNS`); for now only widen fixtures and expect these three to still fail until Task 11.

- [ ] **Step 8: Full suite except those three**

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider --deselect tests/test_features_build.py::test_build_training_frame_fills_missing_optional_columns_with_zero --deselect tests/test_missing_value_feature_provenance.py`
Expected: all other tests pass

- [ ] **Step 9: Commit** `git add src/nba_predictor/data/espn.py src/nba_predictor/pipeline/ingest.py tests/fixtures tests/test_espn_box_fields.py tests/test_backfill.py tests/test_retrain_freshness.py tests/test_pipeline_ingest.py tests/test_features_build.py`

## Task 3: One scaled linear model, shared by evaluation and serving

**Why:** `candidate_race.py` (evaluation) and `game_outcome.py` (serving) each fit `LogisticRegression`/`Ridge` on RAW columns with an L2 penalty. With Elo near 1500, miles in the thousands and rates near 0.5, the penalty shrinks small-unit features hardest, so which block "wins" would depend on units, and lbfgs warns about convergence. Standardising inside the model removes that. Both paths must use the same builder or evaluation stops describing what is served.

**Files:** Create `src/nba_predictor/models/linear.py`, `tests/test_linear_scaling.py`; modify `models/candidate_race.py`, `models/game_outcome.py`.

**Interfaces:** Produces `make_logistic(c=1.0, random_state=42)` and `make_ridge(alpha=1.0, random_state=42)`, both `Pipeline(StandardScaler, estimator)`.

- [ ] **Step 1: Failing test**

```python
import numpy as np
import pandas as pd

from nba_predictor.models import game_outcome
from nba_predictor.models.candidate_race import make_logistic_classifier_factory, make_ridge_regressor_factory


def _frame(n=400, seed=5):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"rate": rng.normal(0.5, 0.05, n), "elo": rng.normal(1500, 80, n), "miles": rng.normal(2000, 900, n)})
    z = 8 * (X["rate"] - 0.5) + 0.01 * (X["elo"] - 1500) - 0.0004 * (X["miles"] - 2000)
    X["home_win"] = (z + rng.normal(0, 0.8, n) > 0).astype(int)
    X["margin"] = 12 * z + rng.normal(0, 5, n)
    return X


def test_win_predictions_do_not_depend_on_the_units_of_a_feature():
    df = _frame()
    cols = ["rate", "elo", "miles"]
    a = make_logistic_classifier_factory(cols)(df)(df)
    rescaled = df.assign(miles=df["miles"] / 1000.0, elo=df["elo"] * 10)
    b = make_logistic_classifier_factory(cols)(rescaled)(rescaled)
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_margin_predictions_do_not_depend_on_the_units_of_a_feature():
    df = _frame()
    cols = ["rate", "elo", "miles"]
    a = make_ridge_regressor_factory(cols, "margin")(df)(df)
    rescaled = df.assign(miles=df["miles"] / 1000.0, elo=df["elo"] * 10)
    b = make_ridge_regressor_factory(cols, "margin")(rescaled)(rescaled)
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_the_race_and_the_served_model_are_the_same_model():
    df = _frame()
    cols = ["rate", "elo", "miles"]
    raced = make_logistic_classifier_factory(cols)(df)(df)
    served = game_outcome.predict_win_probability(game_outcome.train_win_probability_model(df[cols], df["home_win"], candidate="logistic"), df[cols])
    np.testing.assert_allclose(raced, served, atol=1e-9)
    raced_m = make_ridge_regressor_factory(cols, "margin")(df)(df)
    served_m = game_outcome.train_margin_model(df[cols], df["margin"], candidate="ridge").predict(df[cols])
    np.testing.assert_allclose(raced_m, served_m, atol=1e-9)
```

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_linear_scaling.py`
Expected: FAIL: the unit-invariance tests fail on the raw models (and `make_logistic` does not exist)

- [ ] **Step 2: Create the shared builder**

```python
"""The ONE definition of the linear win and margin/total models, used by evaluation AND serving.

Features arrive in very different units (a rate near 0.5, an Elo near 1500, travel in thousands of miles). An L2
penalty on raw columns shrinks the small-unit features hardest and lets the large-unit ones dominate, so which
block "wins" would depend on its units. Standardising inside the model removes that: predictions are invariant
to rescaling any feature, and the penalty means the same thing for every column.
"""
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

LOGISTIC_C = 1.0
RIDGE_ALPHA = 1.0
RANDOM_STATE = 42


def make_logistic(*, c: float = LOGISTIC_C, random_state: int = RANDOM_STATE) -> Pipeline:
    return make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=1000, random_state=random_state))


def make_ridge(*, alpha: float = RIDGE_ALPHA, random_state: int = RANDOM_STATE) -> Pipeline:
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha, random_state=random_state))
```

- [ ] **Step 3: Use it in both paths**

```diff
diff --git a/src/nba_predictor/models/candidate_race.py b/src/nba_predictor/models/candidate_race.py
index c3a6cd9..8811830 100644
--- a/src/nba_predictor/models/candidate_race.py
+++ b/src/nba_predictor/models/candidate_race.py
@@ -62,5 +62,5 @@ def make_logistic_classifier_factory(feature_cols: list[str]) -> Callable:
 
     def factory(train_df: pd.DataFrame):
-        from sklearn.linear_model import LogisticRegression
+        from nba_predictor.models.linear import make_logistic
 
         _seed()
@@ -73,5 +73,5 @@ def make_logistic_classifier_factory(feature_cols: list[str]) -> Callable:
 
         _seed()
-        model = LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)
+        model = make_logistic(random_state=RANDOM_STATE)
         model.fit(train_df[feature_cols], y)
         return lambda X: model.predict_proba(X[feature_cols])[:, 1]
@@ -82,8 +82,8 @@ def make_logistic_classifier_factory(feature_cols: list[str]) -> Callable:
 def make_ridge_regressor_factory(feature_cols: list[str], target_col: str) -> Callable:
     def factory(train_df: pd.DataFrame):
-        from sklearn.linear_model import Ridge
+        from nba_predictor.models.linear import make_ridge
 
         _seed()
-        model = Ridge(alpha=1.0, random_state=RANDOM_STATE)
+        model = make_ridge(random_state=RANDOM_STATE)
         model.fit(train_df[feature_cols], train_df[target_col])
         return lambda X: model.predict(X[feature_cols])
```

```diff
diff --git a/src/nba_predictor/models/game_outcome.py b/src/nba_predictor/models/game_outcome.py
index 6b886c8..cb83637 100644
--- a/src/nba_predictor/models/game_outcome.py
+++ b/src/nba_predictor/models/game_outcome.py
@@ -38,7 +38,7 @@ def train_win_probability_model(X: pd.DataFrame, y: pd.Series, candidate: str =
     _check_candidate(candidate)
     if candidate == "logistic":
-        from sklearn.linear_model import LogisticRegression
+        from nba_predictor.models.linear import make_logistic
 
-        model = LogisticRegression(max_iter=1000, random_state=42)
+        model = make_logistic()
     else:
         import xgboost as xgb
@@ -56,7 +56,7 @@ def train_margin_model(X: pd.DataFrame, y: pd.Series, candidate: str = "xgboost"
     _check_candidate(candidate)
     if candidate == "ridge":
-        from sklearn.linear_model import Ridge
+        from nba_predictor.models.linear import make_ridge
 
-        model = Ridge(alpha=1.0, random_state=42)
+        model = make_ridge()
     else:
         import xgboost as xgb
```

- [ ] **Step 4: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_linear_scaling.py tests/test_candidate_race.py tests/test_models_game_outcome.py tests/test_pipeline_retrain.py`
Expected: 24 passed

- [ ] **Step 5: Re-baseline.** Scaling changes the baseline model. Once Task 13 exists, score `--baseline ''` before and after this change with `tools/feature_block_eval.py` style scoring and record the effect in the evaluation doc; do not claim Phase A numbers for the new baseline.

- [ ] **Step 6: Commit** `git add src/nba_predictor/models/linear.py src/nba_predictor/models/candidate_race.py src/nba_predictor/models/game_outcome.py tests/test_linear_scaling.py`

## Task 4: Block `power`: causal margin-of-victory Elo

**Files:** Create `src/nba_predictor/features/power_rating.py`, `tests/test_features_power_rating.py`.
**Interfaces:** Produces `pregame_power_ratings(games, k=20.0, home_adv=65.0, carry=0.75) -> DataFrame[home_power_rating, away_power_rating]` indexed like `games`; `season_of(date)`. `carry` is a starting value; the season carry-over PR (hand-off item 2) fits the real weight in walk-forward and replaces `DEFAULT_CARRY`.

- [ ] **Step 1: Failing test**
```python
import numpy as np
import pandas as pd
import pytest

from tests.feature_fixtures import make_games, perturb_from, with_upcoming
from nba_predictor.features.power_rating import (
    BASE_RATING, DEFAULT_CARRY, pregame_power_ratings, season_of,
)


def _game(gid, date, home, away, hp, ap):
    return {"game_id": gid, "game_date": date, "home_team": home, "away_team": away, "home_pts": hp, "away_pts": ap}


def test_first_game_is_rated_at_the_base():
    r = pregame_power_ratings(pd.DataFrame([_game("a", "2025-10-22", "BOS", "MIA", 110, 100)]))
    assert r.loc[0, "home_power_rating"] == BASE_RATING and r.loc[0, "away_power_rating"] == BASE_RATING


def test_a_home_win_raises_home_and_lowers_away_by_the_same_amount():
    g = pd.DataFrame([_game("a", "2025-10-22", "BOS", "MIA", 120, 100), _game("b", "2025-10-24", "BOS", "MIA", 100, 100 - 1)])
    r = pregame_power_ratings(g)
    up = r.loc[1, "home_power_rating"] - BASE_RATING
    down = BASE_RATING - r.loc[1, "away_power_rating"]
    assert up > 0 and up == pytest.approx(down)


def test_an_upset_moves_ratings_more_than_an_expected_win():
    base = [_game(f"w{i}", f"2025-10-{10 + i:02d}", "BOS", "MIA", 115, 100) for i in range(6)]
    expected = pd.DataFrame(base + [_game("x", "2025-10-30", "BOS", "MIA", 115, 100), _game("y", "2025-11-01", "BOS", "MIA", 100, 99)])
    upset = pd.DataFrame(base + [_game("x", "2025-10-30", "BOS", "MIA", 100, 115), _game("y", "2025-11-01", "BOS", "MIA", 100, 99)])
    gain_expected = pregame_power_ratings(expected).loc[7, "home_power_rating"] - pregame_power_ratings(expected).loc[6, "home_power_rating"]
    swing_upset = pregame_power_ratings(upset).loc[7, "home_power_rating"] - pregame_power_ratings(upset).loc[6, "home_power_rating"]
    assert abs(swing_upset) > abs(gain_expected)


def test_season_boundary_pulls_ratings_toward_the_base():
    games = pd.DataFrame([_game(f"a{i}", f"2025-10-{10 + i:02d}", "BOS", "MIA", 120, 95) for i in range(8)]
                         + [_game("z", "2026-10-22", "BOS", "MIA", 100, 99)])
    r = pregame_power_ratings(games, carry=0.5)
    last = pregame_power_ratings(games.iloc[:8], carry=0.5).iloc[-1]["home_power_rating"]
    before_boundary = r.loc[7, "home_power_rating"]
    assert season_of("2025-10-10") != season_of("2026-10-22")
    assert abs(r.loc[8, "home_power_rating"] - BASE_RATING) < abs(before_boundary - BASE_RATING)
    assert last == pytest.approx(before_boundary)


def test_upcoming_games_are_rated_but_never_update():
    g = with_upcoming(make_games(n_days=40), n_upcoming=3)
    r = pregame_power_ratings(g)
    assert r["home_power_rating"].notna().all()
    # the upcoming rows must equal what a frame WITHOUT them would have produced for the last completed game's ratings
    done = g.dropna(subset=["home_pts"])
    r_done = pregame_power_ratings(done)
    assert r.loc[done.index, "home_power_rating"].equals(r_done["home_power_rating"])


def test_causal_future_games_do_not_change_earlier_ratings():
    games = make_games(n_days=60)
    cut = sorted(games["game_date"].unique())[30]
    a = pregame_power_ratings(games)
    b = pregame_power_ratings(perturb_from(games, cut))
    earlier = games["game_date"] <= cut
    pd.testing.assert_frame_equal(a[earlier], b[earlier])
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_power_rating.py`
Expected: FAIL: ModuleNotFoundError nba_predictor.features.power_rating
- [ ] **Step 2: Implement**
```python
"""Causal margin-of-victory Elo: the rating each team carried INTO every game."""
from __future__ import annotations

import pandas as pd

BASE_RATING = 1500.0
DEFAULT_K = 20.0
DEFAULT_HOME_ADV = 65.0
#: Share of last season's distance from 1500 kept at a season boundary. 0.75 is a starting
#: value; the season carry-over step fits the real weight in walk-forward and replaces it.
DEFAULT_CARRY = 0.75


def season_of(game_date: str) -> int:
    """NBA season id = the calendar year it starts in (seasons open late September/October)."""
    year, month = int(game_date[:4]), int(game_date[5:7])
    return year if month >= 9 else year - 1


def _mov_multiplier(margin: float, winner_elo_diff: float) -> float:
    return ((abs(margin) + 3.0) ** 0.8) / (7.5 + 0.006 * winner_elo_diff)


def pregame_power_ratings(
    games: pd.DataFrame,
    k: float = DEFAULT_K,
    home_adv: float = DEFAULT_HOME_ADV,
    carry: float = DEFAULT_CARRY,
) -> pd.DataFrame:
    """`home_power_rating` / `away_power_rating` for every row of `games`, indexed like `games`.

    Ratings are read BEFORE the game and updated AFTER it, in date order. A row with no result
    (an upcoming game) is rated but never updates anything, so serving and training agree.
    """
    ordered = games.sort_values(["game_date", "game_id"])
    ratings: dict[str, float] = {}
    season = None
    home_out: dict = {}
    away_out: dict = {}
    for idx, row in ordered.iterrows():
        this_season = season_of(row["game_date"])
        if season is not None and this_season != season:
            for team in ratings:
                ratings[team] = BASE_RATING + carry * (ratings[team] - BASE_RATING)
        season = this_season
        home, away = row["home_team"], row["away_team"]
        rating_home = ratings.get(home, BASE_RATING)
        rating_away = ratings.get(away, BASE_RATING)
        home_out[idx], away_out[idx] = rating_home, rating_away
        if pd.isna(row.get("home_pts")) or pd.isna(row.get("away_pts")):
            continue
        diff = rating_home + home_adv - rating_away
        expected_home = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        margin = float(row["home_pts"] - row["away_pts"])
        home_won = margin > 0
        winner_diff = diff if home_won else -diff
        delta = k * _mov_multiplier(margin, winner_diff) * ((1.0 if home_won else 0.0) - expected_home)
        ratings[home] = rating_home + delta
        ratings[away] = rating_away - delta
    return pd.DataFrame(
        {"home_power_rating": pd.Series(home_out), "away_power_rating": pd.Series(away_out)}
    ).reindex(games.index)
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_power_rating.py`
Expected: 6 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/power_rating.py tests/test_features_power_rating.py`

## Task 5: Block `schedule`: travel, time-zone and congestion load

Reuses the existing, previously unwired helpers in `features/rest_travel.py` (`rolling_travel_miles`, `timezone_change_count`, `fatigue_index`, `congestion_flags`, `compute_rest_days`).

**Files:** Create `src/nba_predictor/features/schedule_load.py`, `tests/test_features_schedule_load.py`.
**Interfaces:** Produces `add_schedule_load(games)` adding `home_/away_` `travel_miles_7d, tz_changes_7d, fatigue_index, three_in_four, games_last_7`; `SCHEDULE_COLUMNS`.

- [ ] **Step 1: Failing test**
```python
import pandas as pd
import pytest

from tests.feature_fixtures import make_games
from nba_predictor.features.rest_travel import fatigue_index, haversine_miles
from nba_predictor.features.schedule_load import SCHEDULE_COLUMNS, add_schedule_load


def _g(gid, date, home, away):
    return {"game_id": gid, "game_date": date, "home_team": home, "away_team": away}


def test_travel_miles_follow_the_arenas_the_team_actually_visited():
    games = pd.DataFrame([_g("a", "2025-10-20", "BOS", "MIA"), _g("b", "2025-10-22", "LAL", "BOS")])
    out = add_schedule_load(games)
    boston_to_la = haversine_miles(42.3662, -71.0621, 34.0430, -118.2673)
    assert out.loc[1, "away_travel_miles_7d"] == pytest.approx(boston_to_la, rel=0.01)
    assert out.loc[1, "away_tz_changes_7d"] == 1
    assert out.loc[1, "home_travel_miles_7d"] == 0.0


def test_fatigue_uses_the_existing_formula_with_real_rest_days():
    games = pd.DataFrame([_g("a", "2025-10-20", "BOS", "MIA"), _g("b", "2025-10-22", "LAL", "BOS")])
    out = add_schedule_load(games)
    expected = fatigue_index(out.loc[1, "away_travel_miles_7d"], 1, 1)  # one rest day between the 20th and the 22nd
    assert out.loc[1, "away_fatigue_index"] == pytest.approx(expected)


def test_the_window_is_seven_days_back_inclusive_and_no_further():
    games = pd.DataFrame([
        _g("a", "2025-10-14", "BOS", "MIA"),   # 8 days before the 22nd: outside
        _g("b", "2025-10-15", "BOS", "CHI"),   # 7 days before: inside
        _g("c", "2025-10-22", "LAL", "BOS"),
    ])
    out = add_schedule_load(games)
    assert out.loc[2, "away_games_last_7"] == 1


def test_three_in_four_flag():
    games = pd.DataFrame([_g("a", "2025-10-20", "BOS", "MIA"), _g("b", "2025-10-21", "BOS", "CHI"), _g("c", "2025-10-23", "BOS", "DEN")])
    out = add_schedule_load(games)
    assert bool(out.loc[2, "home_three_in_four"]) is True and bool(out.loc[0, "home_three_in_four"]) is False


def test_columns_exist_for_both_sides_and_nothing_is_constant():
    out = add_schedule_load(make_games(n_days=60))
    for side in ("home", "away"):
        for col in SCHEDULE_COLUMNS:
            assert f"{side}_{col}" in out.columns
    assert out["home_travel_miles_7d"].nunique() > 1 and out["away_fatigue_index"].nunique() > 1


def test_later_games_never_change_earlier_rows():
    games = make_games(n_days=60)
    full = add_schedule_load(games)
    head = add_schedule_load(games.iloc[:90])
    cols = [f"{s}_{c}" for s in ("home", "away") for c in SCHEDULE_COLUMNS]
    pd.testing.assert_frame_equal(full.iloc[:90][cols].reset_index(drop=True), head[cols].reset_index(drop=True))
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_schedule_load.py`
Expected: FAIL: ModuleNotFoundError
- [ ] **Step 2: Implement**
```python
"""Travel, time-zone and congestion load per team per game, from the schedule alone."""
from __future__ import annotations

from datetime import date

import pandas as pd

from nba_predictor.features.rest_travel import (
    compute_rest_days, congestion_flags, fatigue_index, rolling_travel_miles, timezone_change_count,
)

WINDOW_DAYS = 7
SCHEDULE_COLUMNS = [
    "travel_miles_7d", "tz_changes_7d", "fatigue_index", "three_in_four", "games_last_7",
]


def _team_rows(games: pd.DataFrame) -> pd.DataFrame:
    home = games[["game_id", "game_date", "home_team"]].rename(columns={"home_team": "team"}).assign(location=games["home_team"])
    away = games[["game_id", "game_date", "away_team", "home_team"]].rename(
        columns={"away_team": "team", "home_team": "location"}
    )[["game_id", "game_date", "team", "location"]]
    both = pd.concat([home[["game_id", "game_date", "team", "location"]], away], ignore_index=True)
    return both.sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)


def add_schedule_load(games: pd.DataFrame) -> pd.DataFrame:
    """Add `home_*` and `away_*` columns named in SCHEDULE_COLUMNS. Only EARLIER dates are read."""
    rows = _team_rows(games)
    load: dict[tuple[str, str], dict] = {}
    for team, grp in rows.groupby("team", sort=False):
        dates = grp["game_date"].tolist()
        locs = grp["location"].tolist()
        gids = grp["game_id"].tolist()
        for i, (d, loc, gid) in enumerate(zip(dates, locs, gids)):
            today = date.fromisoformat(d)
            prior = [
                (pd_, pl) for pd_, pl in zip(dates[:i], locs[:i])
                if pd_ < d and 1 <= (today - date.fromisoformat(pd_)).days <= WINDOW_DAYS
            ]
            seq = [pl for _, pl in prior] + [loc]
            earlier = [x for x in dates[:i] if x < d]
            rest = compute_rest_days(d, earlier[-1] if earlier else None)
            miles = rolling_travel_miles(seq)
            tz = timezone_change_count(seq)
            flags = congestion_flags(earlier, d)
            load[(gid, team)] = {
                "travel_miles_7d": miles, "tz_changes_7d": tz,
                "fatigue_index": fatigue_index(miles, tz, rest),
                "three_in_four": bool(flags["three_in_four"]), "games_last_7": len(prior),
            }
    out = games.copy()
    for side in ("home", "away"):
        for col in SCHEDULE_COLUMNS:
            out[f"{side}_{col}"] = [load[(g, t)][col] for g, t in zip(out["game_id"], out[f"{side}_team"])]
    return out
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_schedule_load.py`
Expected: 6 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/schedule_load.py tests/test_features_schedule_load.py`

## Task 6: Block `form`: defence, pace and opponent-allowed stats

Possessions = FGA + 0.44 FTA - OREB + TOV. Rolling windows 5/10/20 and an EWMA (half-life 8 games), all `shift(1)`-lagged; the default block uses `r10` and `ewm`; the ablation (Task 14) decides which stay.

**Files:** Create `src/nba_predictor/features/team_form.py`, `tests/test_features_team_form.py`.
**Interfaces:** Produces `long_with_opponent(games)`, `per_game_stats(long)`, `add_rolling(stats, windows, halflife)`, `form_columns(suffixes)`, `attach_form`, `add_team_form(games, suffixes)`, `FORM_STATS`.

- [ ] **Step 1: Failing test**
```python
import numpy as np
import pandas as pd
import pytest

from tests.feature_fixtures import make_games, perturb_from, with_upcoming
from nba_predictor.features.team_form import (
    FORM_STATS, add_team_form, form_columns, long_with_opponent, per_game_stats,
)


def _one_game(**over):
    base = {"game_id": "g1", "game_date": "2025-10-22", "home_team": "BOS", "away_team": "MIA"}
    for side, pts in (("home", 110), ("away", 100)):
        base.update({f"{side}_fgm": 40, f"{side}_fga": 90, f"{side}_fg3m": 12, f"{side}_fg3a": 36, f"{side}_ftm": 16,
                     f"{side}_fta": 20, f"{side}_oreb": 10, f"{side}_dreb": 33, f"{side}_tov": 12, f"{side}_pts": pts})
    base.update(over)
    return pd.DataFrame([base])


def test_possessions_formula():
    s = per_game_stats(long_with_opponent(_one_game()))
    assert s.loc[0, "poss"] == pytest.approx(90 + 0.44 * 20 - 10 + 12)  # 100.8


def test_ortg_drtg_and_net_are_per_100_possessions():
    s = per_game_stats(long_with_opponent(_one_game())).set_index("team")
    assert s.loc["BOS", "ortg"] == pytest.approx(100 * 110 / 100.8)
    assert s.loc["BOS", "drtg"] == pytest.approx(100 * 100 / 100.8)
    assert s.loc["BOS", "net"] == pytest.approx(s.loc["BOS", "ortg"] - s.loc["BOS", "drtg"])
    assert s.loc["BOS", "net"] == pytest.approx(-s.loc["MIA", "net"])


def test_what_a_team_allows_is_what_its_opponent_did():
    s = per_game_stats(long_with_opponent(make_games(n_days=3))).set_index(["game_id", "team"])
    g = make_games(n_days=3).iloc[0]
    assert s.loc[(g["game_id"], g["home_team"]), "opp_efg"] == pytest.approx(s.loc[(g["game_id"], g["away_team"]), "efg"])
    assert s.loc[(g["game_id"], g["home_team"]), "opp_fg3_pct"] == pytest.approx(g["away_fg3m"] / g["away_fg3a"])


def test_rolling_is_lagged_so_a_game_never_sees_itself():
    games = make_games(n_days=30)
    out = add_team_form(games)
    stats = per_game_stats(long_with_opponent(games))
    team = "BOS"
    own = stats[stats["team"] == team].sort_values("game_date")
    second = own.iloc[1]
    row = out[(out["game_id"] == second["game_id"])].iloc[0]
    side = "home" if row["home_team"] == team else "away"
    assert row[f"{side}_net_r10"] == pytest.approx(own.iloc[0]["net"])
    first = own.iloc[0]
    row0 = out[out["game_id"] == first["game_id"]].iloc[0]
    assert np.isnan(row0[f"{'home' if row0['home_team'] == team else 'away'}_net_r10"])


def test_every_stat_has_every_requested_column_and_none_is_constant():
    out = add_team_form(make_games(n_days=80))
    for side in ("home", "away"):
        for c in form_columns():
            assert f"{side}_{c}" in out.columns
    for c in form_columns():
        assert out[f"home_{c}"].nunique() > 1, c


def test_causal_later_games_do_not_change_earlier_form():
    games = make_games(n_days=60)
    cut = sorted(games["game_date"].unique())[30]
    a = add_team_form(games)
    b = add_team_form(perturb_from(games, cut))
    earlier = games["game_date"] <= cut
    cols = [f"{s}_{c}" for s in ("home", "away") for c in form_columns()]
    pd.testing.assert_frame_equal(a[earlier][cols].reset_index(drop=True), b[earlier][cols].reset_index(drop=True))


def test_upcoming_rows_get_form_from_history_only():
    games = with_upcoming(make_games(n_days=40), 3)
    out = add_team_form(games)
    tail = out.iloc[-3:]
    assert tail[f"home_net_r10"].notna().all() and tail[f"away_pace_ewm"].notna().all()
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_team_form.py`
Expected: FAIL: ModuleNotFoundError
- [ ] **Step 2: Implement**
```python
"""Per-team rolling form incl. DEFENCE, pace and opponent-allowed stats (all causal: shift(1))."""
from __future__ import annotations

import pandas as pd

BOX = ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov", "pts"]

#: Per-game stats that become rolling features.
FORM_STATS = [
    "ortg", "drtg", "net", "pace",
    "efg", "tov_rate", "orb_pct", "ft_rate", "drb_pct", "fg3a_rate",
    "opp_efg", "opp_tov_rate", "opp_ft_rate", "opp_fg3a_rate", "opp_fg3_pct",
]
WINDOWS = (5, 10, 20)
EWM_HALFLIFE = 8
#: What a block-2 model uses by default; the ablation decides what stays.
DEFAULT_FORM_SUFFIXES = ("r10", "ewm")


def long_with_opponent(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game, with the opponent's box beside it as `opp_*`."""
    rows = []
    for side, other in (("home", "away"), ("away", "home")):
        part = pd.DataFrame({
            "game_id": games["game_id"], "game_date": games["game_date"],
            "team": games[f"{side}_team"], "opp": games[f"{other}_team"], "is_home": side == "home",
        })
        for f in BOX:
            part[f] = games[f"{side}_{f}"].to_numpy()
            part[f"opp_{f}"] = games[f"{other}_{f}"].to_numpy()
        rows.append(part)
    return pd.concat(rows, ignore_index=True).sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)


def _safe(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den).where(den != 0)


def per_game_stats(long: pd.DataFrame) -> pd.DataFrame:
    """Single-game values (not yet lagged). Possessions = FGA + 0.44*FTA - OREB + TOV."""
    d = long.copy()
    poss = d["fga"] + 0.44 * d["fta"] - d["oreb"] + d["tov"]
    opp_poss = d["opp_fga"] + 0.44 * d["opp_fta"] - d["opp_oreb"] + d["opp_tov"]
    d["poss"], d["opp_poss"] = poss, opp_poss
    d["pace"] = (poss + opp_poss) / 2.0
    d["ortg"] = 100.0 * _safe(d["pts"], poss)
    d["drtg"] = 100.0 * _safe(d["opp_pts"], opp_poss)
    d["net"] = d["ortg"] - d["drtg"]
    d["efg"] = _safe(d["fgm"] + 0.5 * d["fg3m"], d["fga"])
    d["tov_rate"] = _safe(d["tov"], d["fga"] + 0.44 * d["fta"] + d["tov"])
    d["orb_pct"] = _safe(d["oreb"], d["oreb"] + d["opp_dreb"])
    d["drb_pct"] = _safe(d["dreb"], d["dreb"] + d["opp_oreb"])
    d["ft_rate"] = _safe(d["fta"], d["fga"])
    d["fg3a_rate"] = _safe(d["fg3a"], d["fga"])
    d["opp_efg"] = _safe(d["opp_fgm"] + 0.5 * d["opp_fg3m"], d["opp_fga"])
    d["opp_tov_rate"] = _safe(d["opp_tov"], d["opp_fga"] + 0.44 * d["opp_fta"] + d["opp_tov"])
    d["opp_ft_rate"] = _safe(d["opp_fta"], d["opp_fga"])
    d["opp_fg3a_rate"] = _safe(d["opp_fg3a"], d["opp_fga"])
    d["opp_fg3_pct"] = _safe(d["opp_fg3m"], d["opp_fg3a"])
    return d


def add_rolling(stats: pd.DataFrame, windows: tuple[int, ...] = WINDOWS, halflife: float = EWM_HALFLIFE) -> pd.DataFrame:
    """`{stat}_r{w}` = mean of the team's previous w games; `{stat}_ewm` = EWMA of all previous games."""
    d = stats.sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)
    grouped = d.groupby("team", sort=False)
    new = {}
    for stat in FORM_STATS:
        lagged = grouped[stat].shift(1)
        by_team = lagged.groupby(d["team"], sort=False)
        for w in windows:
            new[f"{stat}_r{w}"] = by_team.transform(lambda s, w=w: s.rolling(w, min_periods=1).mean())
        new[f"{stat}_ewm"] = by_team.transform(lambda s: s.ewm(halflife=halflife, min_periods=1).mean())
    return pd.concat([d, pd.DataFrame(new)], axis=1)


def form_columns(suffixes: tuple[str, ...] = DEFAULT_FORM_SUFFIXES) -> list[str]:
    return [f"{stat}_{suffix}" for stat in FORM_STATS for suffix in suffixes]


def attach_form(games: pd.DataFrame, rolled: pd.DataFrame, suffixes: tuple[str, ...] = DEFAULT_FORM_SUFFIXES) -> pd.DataFrame:
    """Merge each side's rolled form onto `games` as `home_<col>` / `away_<col>`."""
    cols = form_columns(suffixes)
    keyed = rolled.set_index(["game_id", "team"])[cols]
    out = games.copy()
    for side in ("home", "away"):
        idx = pd.MultiIndex.from_arrays([out["game_id"], out[f"{side}_team"]])
        values = keyed.reindex(idx)
        for c in cols:
            out[f"{side}_{c}"] = values[c].to_numpy()
    return out


def add_team_form(games: pd.DataFrame, suffixes: tuple[str, ...] = DEFAULT_FORM_SUFFIXES) -> pd.DataFrame:
    return attach_form(games, add_rolling(per_game_stats(long_with_opponent(games))), suffixes)
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_team_form.py`
Expected: 7 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/team_form.py tests/test_features_team_form.py`

## Task 7: Block `adjusted`: opponent-adjusted offence and defence

A recency-weighted ridge solve per date over completed games strictly before that date: points scored ~ own offence + opponent defence + home + intercept. `adj_net = adj_off - adj_def`; NaN until 30 games exist.

**Files:** Create `src/nba_predictor/features/opp_adjust.py`, `tests/test_features_opp_adjust.py`.
**Interfaces:** Produces `adjusted_ratings_by_date(games, lam=10.0, lookback_days=365, halflife_days=90.0, min_games=30)` returning `{home,away}_adj_{off,def,net}` indexed like `games`.

- [ ] **Step 1: Failing test**
```python
import numpy as np
import pandas as pd
import pytest

from tests.feature_fixtures import TEAMS, make_games, perturb_from
from nba_predictor.features.opp_adjust import adjusted_ratings_by_date


def _league(n_days=140, seed=3):
    """Points really are offence + opponent defence + noise, so the solve has a known answer."""
    rng = np.random.default_rng(seed)
    off = {t: float(v) for t, v in zip(TEAMS, [6, 3, 0, -2, -4, -3])}
    dfn = {t: float(v) for t, v in zip(TEAMS, [-5, -2, 0, 1, 3, 3])}   # negative = concedes less = better defence
    rows = []
    for d in range(n_days):
        day = (pd.Timestamp("2025-10-22") + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        order = list(rng.permutation(TEAMS))
        for i in range(0, 6, 2):
            h, a = order[i], order[i + 1]
            rows.append({"game_id": f"g{len(rows):05d}", "game_date": day, "home_team": h, "away_team": a,
                         "home_pts": 110 + off[h] + dfn[a] + 2 + rng.normal(0, 3),
                         "away_pts": 110 + off[a] + dfn[h] + rng.normal(0, 3)})
    return pd.DataFrame(rows), off, dfn


def test_ratings_recover_the_known_strengths():
    games, off, dfn = _league()
    r = adjusted_ratings_by_date(games)
    last_day = games["game_date"].max()
    last = games[games["game_date"] == last_day].iloc[0]
    est_off = {last["home_team"]: r.loc[last.name, "home_adj_off"], last["away_team"]: r.loc[last.name, "away_adj_off"]}
    for team, value in est_off.items():
        centred = off[team] - np.mean(list(off.values()))
        assert value == pytest.approx(centred, abs=2.5)
    # the best offence outranks the worst
    best, worst = max(off, key=off.get), min(off, key=off.get)
    day_rows = games[games["game_date"] == last_day]
    ratings_by_team = {}
    for idx, row in day_rows.iterrows():
        ratings_by_team[row["home_team"]] = r.loc[idx, "home_adj_off"]
        ratings_by_team[row["away_team"]] = r.loc[idx, "away_adj_off"]
    ordered = sorted(ratings_by_team, key=ratings_by_team.get)
    assert off[ordered[-1]] >= off[ordered[0]]


def test_nan_until_enough_games_exist():
    games, _, _ = _league(n_days=40)
    r = adjusted_ratings_by_date(games)
    assert r.loc[games.index[0], "home_adj_net"] != r.loc[games.index[0], "home_adj_net"]  # NaN
    assert r["home_adj_net"].notna().sum() > 0


def test_net_is_offence_minus_defence():
    games, _, _ = _league(n_days=60)
    r = adjusted_ratings_by_date(games).dropna()
    np.testing.assert_allclose(r["home_adj_net"], r["home_adj_off"] - r["home_adj_def"])


def test_causal_future_games_never_change_earlier_ratings():
    games, _, _ = _league(n_days=70)
    cut = sorted(games["game_date"].unique())[50]
    a = adjusted_ratings_by_date(games)
    pert = games.copy()
    mask = pert["game_date"] >= cut
    pert.loc[mask, "home_pts"] = pert.loc[mask, "home_pts"] + 30
    b = adjusted_ratings_by_date(pert)
    earlier = games["game_date"] <= cut
    pd.testing.assert_frame_equal(a[earlier], b[earlier])
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_opp_adjust.py`
Expected: FAIL: ModuleNotFoundError
- [ ] **Step 2: Implement**
```python
"""Opponent-adjusted offence/defence ratings: a recency-weighted ridge solve, per date, on EARLIER games only."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_GAMES = 30


def _design(games: pd.DataFrame, team_index: dict[str, int]):
    """Two observations per game: points a team scored ~ its offence + the opponent's defence + home + intercept."""
    n = len(team_index)
    home_idx = games["home_team"].map(team_index).to_numpy()
    away_idx = games["away_team"].map(team_index).to_numpy()
    m = len(games)
    X = np.zeros((2 * m, 2 * n + 2))
    X[np.arange(m), home_idx] = 1.0                 # home offence
    X[np.arange(m), n + away_idx] = 1.0             # away defence (higher = concedes more)
    X[np.arange(m), 2 * n] = 1.0                    # home flag
    X[np.arange(m), 2 * n + 1] = 1.0                # intercept
    X[m + np.arange(m), away_idx] = 1.0             # away offence
    X[m + np.arange(m), n + home_idx] = 1.0         # home defence
    X[m + np.arange(m), 2 * n + 1] = 1.0
    y = np.concatenate([games["home_pts"].to_numpy(float), games["away_pts"].to_numpy(float)])
    return X, y


def adjusted_ratings_by_date(
    games: pd.DataFrame, lam: float = 10.0, lookback_days: int = 365, halflife_days: float = 90.0, min_games: int = MIN_GAMES,
) -> pd.DataFrame:
    """`{home,away}_adj_off`, `{home,away}_adj_def`, `{home,away}_adj_net` for every row (NaN until `min_games`).

    `adj_off` = points above an average offence; `adj_def` = points above average CONCEDED (lower is better),
    so `adj_net = adj_off - adj_def`. Each date's ratings are fit on completed games strictly before that date.
    """
    teams = sorted(set(games["home_team"]) | set(games["away_team"]))
    team_index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    done = games.dropna(subset=["home_pts", "away_pts"]).copy()
    done["_ord"] = pd.to_datetime(done["game_date"]).map(pd.Timestamp.toordinal)
    penalty = np.ones(2 * n + 2)
    penalty[2 * n:] = 0.0                            # never shrink the home flag or the intercept
    cols = ["home_adj_off", "home_adj_def", "home_adj_net", "away_adj_off", "away_adj_def", "away_adj_net"]
    out = {c: np.full(len(games), np.nan) for c in cols}
    home_team = games["home_team"].to_numpy()
    away_team = games["away_team"].to_numpy()
    dates = games["game_date"].to_numpy()
    for day in sorted(games["game_date"].unique()):
        o = pd.Timestamp(day).toordinal()
        window = done[(done["_ord"] < o) & (done["_ord"] >= o - lookback_days)]
        if len(window) < min_games:
            continue
        X, y = _design(window, team_index)
        age = np.concatenate([o - window["_ord"].to_numpy(), o - window["_ord"].to_numpy()]).astype(float)
        w = 0.5 ** (age / halflife_days)
        A = X.T @ (X * w[:, None]) + lam * np.diag(penalty)
        beta = np.linalg.solve(A, X.T @ (w * y))
        ratings = {t: (float(beta[i]), float(beta[n + i])) for t, i in team_index.items()}
        for pos in np.flatnonzero(dates == day):
            for side, teams_arr in (("home", home_team), ("away", away_team)):
                off, dfn = ratings[teams_arr[pos]]
                out[f"{side}_adj_off"][pos], out[f"{side}_adj_def"][pos] = off, dfn
                out[f"{side}_adj_net"][pos] = off - dfn
    return pd.DataFrame(out, index=games.index)
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_opp_adjust.py`
Expected: 4 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/opp_adjust.py tests/test_features_opp_adjust.py`

## Task 8: Block `matchup`: style-matchup features

Reads the already-lagged `r10` form (so Task 6 must run first) plus trailing league averages.

**Files:** Create `src/nba_predictor/features/matchup.py`, `tests/test_features_matchup.py`.
**Interfaces:** Produces `add_matchup(games, suffix="r10")` adding `MATCHUP_COLUMNS` (`pace_expected, pace_gap, home/away_three_edge, home/away_orb_edge, home/away_ft_edge, home/away_tov_edge, league_ppg_30d`).

- [ ] **Step 1: Failing test**
```python
import numpy as np
import pandas as pd
import pytest

from tests.feature_fixtures import make_games, perturb_from
from nba_predictor.features.matchup import MATCHUP_COLUMNS, add_matchup, league_trailing
from nba_predictor.features.team_form import add_team_form


def _with_form(n_days=80, seed=7):
    return add_team_form(make_games(n_days=n_days, seed=seed), suffixes=("r10",))


def test_every_matchup_column_is_produced_and_not_constant():
    out = add_matchup(_with_form()).dropna(subset=["home_pace_r10", "away_pace_r10"])
    for c in MATCHUP_COLUMNS:
        assert c in out.columns
        assert out[c].dropna().nunique() > 1, c


def test_expected_possessions_sits_between_the_two_paces():
    out = add_matchup(_with_form()).dropna(subset=["pace_expected"])
    lo = out[["home_pace_r10", "away_pace_r10"]].min(axis=1)
    hi = out[["home_pace_r10", "away_pace_r10"]].max(axis=1)
    assert ((out["pace_expected"] >= lo - 1e-9) & (out["pace_expected"] <= hi + 1e-9)).all()


def test_hand_checked_edges():
    games = _with_form(n_days=40).iloc[[25]].copy()
    games["game_date"] = "2025-12-01"
    for col, val in {"home_orb_pct_r10": 0.30, "away_drb_pct_r10": 0.72, "home_ft_rate_r10": 0.26, "away_opp_ft_rate_r10": 0.22,
                     "home_pace_r10": 101.0, "away_pace_r10": 97.0, "home_tov_rate_r10": 0.12, "away_opp_tov_rate_r10": 0.14,
                     "away_tov_rate_r10": 0.13, "home_opp_tov_rate_r10": 0.11}.items():
        games[col] = val
    full = pd.concat([_with_form(n_days=40), games.assign(game_id="x")], ignore_index=True)
    row = add_matchup(full).iloc[-1]
    assert row["home_orb_edge"] == pytest.approx(0.30 - (1 - 0.72))
    assert row["home_ft_edge"] == pytest.approx(0.26 - 0.22)
    assert row["pace_gap"] == pytest.approx(4.0)
    home_tov, away_tov = (0.12 + 0.14) / 2, (0.13 + 0.11) / 2
    assert row["home_tov_edge"] == pytest.approx(away_tov - home_tov)


def test_swapping_home_and_away_flips_the_edges():
    out = add_matchup(_with_form(n_days=60)).dropna(subset=["home_orb_edge"])
    assert np.allclose(out["pace_gap"], out["home_pace_r10"] - out["away_pace_r10"])
    assert np.allclose(out["home_tov_edge"], -out["away_tov_edge"])


def test_league_averages_only_look_backwards():
    games = make_games(n_days=60)
    cut = sorted(games["game_date"].unique())[40]
    a = league_trailing(games)
    b = league_trailing(perturb_from(games, cut))
    earlier = [d for d in a.index if d <= cut]
    pd.testing.assert_frame_equal(a.loc[earlier], b.loc[earlier])
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_matchup.py`
Expected: FAIL: ModuleNotFoundError
- [ ] **Step 2: Implement**
```python
"""Style matchups: how one team's strengths meet the other's weaknesses. Reads only already-lagged team form."""
from __future__ import annotations

import pandas as pd

LEAGUE_WINDOW_DAYS = 30
MATCHUP_COLUMNS = [
    "pace_expected", "pace_gap",
    "home_three_edge", "away_three_edge",
    "home_orb_edge", "away_orb_edge",
    "home_ft_edge", "away_ft_edge",
    "home_tov_edge", "away_tov_edge",
    "league_ppg_30d",
]


def league_trailing(games: pd.DataFrame, window_days: int = LEAGUE_WINDOW_DAYS) -> pd.DataFrame:
    """League averages over the `window_days` BEFORE each date: points per team-game, pace and 3P%."""
    done = games.dropna(subset=["home_pts", "away_pts"])
    daily = pd.DataFrame({
        "date": pd.to_datetime(done["game_date"]),
        "pts": (done["home_pts"] + done["away_pts"]) / 2.0,
        "fg3m": (done["home_fg3m"] + done["away_fg3m"]),
        "fg3a": (done["home_fg3a"] + done["away_fg3a"]),
    })
    out = {}
    days = sorted(games["game_date"].unique())
    for d in days:
        o = pd.Timestamp(d)
        w = daily[(daily["date"] < o) & (daily["date"] >= o - pd.Timedelta(days=window_days))]
        out[d] = {
            "ppg": float(w["pts"].mean()) if len(w) else float("nan"),
            "fg3_pct": float(w["fg3m"].sum() / w["fg3a"].sum()) if len(w) and w["fg3a"].sum() else float("nan"),
        }
    return pd.DataFrame(out).T


def add_matchup(games: pd.DataFrame, suffix: str = "r10") -> pd.DataFrame:
    """Needs `home_/away_` team-form columns (see team_form) and the box fields for the league averages."""
    league = league_trailing(games)
    g = games.copy()
    ppg = g["game_date"].map(league["ppg"])
    fg3 = g["game_date"].map(league["fg3_pct"])
    h = lambda c: g[f"home_{c}_{suffix}"]  # noqa: E731
    a = lambda c: g[f"away_{c}_{suffix}"]  # noqa: E731
    league_pace = (h("pace") + a("pace")) / 2.0
    # Expected possessions: each side's pace, scaled by the league level the two paces average to.
    g["pace_expected"] = h("pace") * a("pace") / league_pace
    g["pace_gap"] = h("pace") - a("pace")
    g["home_three_edge"] = h("fg3a_rate") * (a("opp_fg3_pct") - fg3)
    g["away_three_edge"] = a("fg3a_rate") * (h("opp_fg3_pct") - fg3)
    g["home_orb_edge"] = h("orb_pct") - (1.0 - a("drb_pct"))
    g["away_orb_edge"] = a("orb_pct") - (1.0 - h("drb_pct"))
    g["home_ft_edge"] = h("ft_rate") - a("opp_ft_rate")
    g["away_ft_edge"] = a("ft_rate") - h("opp_ft_rate")
    # Turnovers: expected rate = average of what the team commits and what the opponent forces.
    home_tov = (h("tov_rate") + a("opp_tov_rate")) / 2.0
    away_tov = (a("tov_rate") + h("opp_tov_rate")) / 2.0
    g["home_tov_edge"] = away_tov - home_tov
    g["away_tov_edge"] = home_tov - away_tov
    g["league_ppg_30d"] = ppg
    return g
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_matchup.py`
Expected: 5 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/matchup.py tests/test_features_matchup.py`

## Task 9: The player-box fetch and an atomic training-file write

**Why:** availability needs who played, for every game. `espn.get_player_boxscore` already caches per event and skips players who did not play (it now also returns `starter`). The backfill gains `--with-players`. The training-file write becomes atomic: a crash mid-write used to leave a corrupt file that the next run read as empty and overwrote with fewer rows. An existing test pins that `backfill.py` never imports `espn` directly (all network goes through functions injected from `ingest`), so the default fetcher lives in `ingest.fetch_player_box`.

**Files:** Modify `pipeline/backfill.py`, `pipeline/ingest.py`; create `tests/test_backfill_players.py`.
**Interfaces:** Produces `ingest.fetch_player_box(game_id)`, `backfill.fetch_player_rows(games, fetch_players, log)`, `backfill.write_player_games(frame, path)`, `backfill._write_json_atomic(path, payload)`, `PLAYER_COLUMNS`; `backfill_seasons(..., with_players, players_path, fetch_players)`; CLI `--with-players`.

- [ ] **Step 1: Failing test**
```python
"""Player box scores for availability: fetched per finished game, merged, written atomically. No network."""
import json
import os

import pytest

from nba_predictor.pipeline import backfill
from tests.test_backfill import _game


def _players(game_id):
    return [
        {"player_id": "1", "team": "BOS", "minutes": 34.0, "starter": True, "points": 22.0, "rebounds": 6.0, "assists": 5.0},
        {"player_id": "2", "team": "LAL", "minutes": 28.0, "starter": False, "points": 10.0, "rebounds": 3.0, "assists": 2.0},
        {"player_id": "3", "team": "BOS", "minutes": 0.0, "starter": False, "points": 0.0, "rebounds": 0.0, "assists": 0.0},
    ]


def test_rows_are_per_player_who_played_in_finished_games_with_a_team_box():
    games = [_game("a", "2025-10-22"), _game("b", "2025-10-23", completed=False), _game("c", "2025-10-24", with_box=False)]
    frame, failed = backfill.fetch_player_rows(games, fetch_players=_players, log=lambda *_: None)
    assert failed == []
    assert set(frame["game_id"]) == {"a"}                      # unfinished and box-less games are skipped
    assert list(frame.columns) == backfill.PLAYER_COLUMNS
    assert len(frame) == 2 and set(frame["player_id"]) == {"1", "2"}   # the 0-minute entry is dropped
    assert bool(frame.loc[frame["player_id"] == "1", "starter"].iloc[0]) is True


def test_one_game_failing_is_named_and_the_rest_are_kept():
    def flaky(game_id):
        if game_id == "b":
            raise ConnectionError("dns")
        return _players(game_id)

    games = [_game("a", "2025-10-22"), _game("b", "2025-10-23"), _game("c", "2025-10-24")]
    frame, failed = backfill.fetch_player_rows(games, fetch_players=flaky, log=lambda *_: None)
    assert failed == ["b"] and set(frame["game_id"]) == {"a", "c"}


def test_the_player_cache_is_merged_and_deduplicated_across_runs(tmp_path):
    path = tmp_path / "player_games.json"
    first, _ = backfill.fetch_player_rows([_game("a", "2025-10-22")], fetch_players=_players, log=lambda *_: None)
    assert backfill.write_player_games(first, path) == 2
    second, _ = backfill.fetch_player_rows([_game("a", "2025-10-22"), _game("b", "2025-10-23")], fetch_players=_players, log=lambda *_: None)
    assert backfill.write_player_games(second, path) == 4       # a's two rows are not duplicated
    assert len(json.loads(path.read_text())) == 4


def test_a_crash_while_writing_leaves_the_old_file_intact(tmp_path, monkeypatch):
    path = tmp_path / "games.json"
    path.write_text(json.dumps([{"game_id": "keep-me"}]))

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        backfill._write_json_atomic(path, [{"game_id": "new"}])
    assert json.loads(path.read_text()) == [{"game_id": "keep-me"}]
    assert [p.name for p in tmp_path.iterdir()] == ["games.json"], "no temp file may be left behind"


def test_backfill_seasons_can_write_the_player_cache(tmp_path):
    games = [_game("a", "2025-10-22")]
    summary = backfill.backfill_seasons(
        [2025], training_path=tmp_path / "games.json", fetch=lambda s, e: games, enrich=lambda g: g, log=lambda *_: None,
        with_players=True, players_path=tmp_path / "player_games.json", fetch_players=_players,
    )
    assert summary["n_player_rows"] == 2 and summary["failed_player_games"] == []
    assert (tmp_path / "player_games.json").exists()


def test_the_cli_exits_non_zero_when_a_game_has_no_player_box(tmp_path, monkeypatch, capsys):
    games = [_game("a", "2025-10-22")]
    real = backfill.backfill_seasons

    def fake_backfill(seasons, **kw):
        return real(seasons, training_path=tmp_path / "games.json", fetch=lambda s, e: games, enrich=lambda g: g, log=lambda *_: None,
                    with_players=True, players_path=tmp_path / "p.json", fetch_players=lambda gid: (_ for _ in ()).throw(ConnectionError("x")))

    monkeypatch.setattr(backfill, "backfill_seasons", fake_backfill)
    assert backfill.main(["--seasons", "1", "--with-players"]) == 1
    assert "INCOMPLETE" in capsys.readouterr().err
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_backfill_players.py`
Expected: FAIL: `backfill.fetch_player_rows` not defined
- [ ] **Step 2: Edit `pipeline/ingest.py` (add `fetch_player_box`)**
```diff
diff --git a/src/nba_predictor/pipeline/ingest.py b/src/nba_predictor/pipeline/ingest.py
index 0df3469..d2b4193 100644
--- a/src/nba_predictor/pipeline/ingest.py
+++ b/src/nba_predictor/pipeline/ingest.py
@@ -284,4 +287,9 @@ def fetch_schedule_range(start_date: str, end_date: str) -> list[dict]:
 
 
+def fetch_player_box(game_id: str) -> list[dict]:
+    """Player rows (minutes, starter, points, rebounds, assists) for one finished game, via ESPN."""
+    return espn.get_player_boxscore(game_id)
+
+
 def enrich_with_boxscores(games: list[dict]) -> list[dict]:
     """Adds flat home_*/away_* box-score fields to completed games with a full box score."""
```
- [ ] **Step 3: Edit `pipeline/backfill.py`**
```diff
diff --git a/src/nba_predictor/pipeline/backfill.py b/src/nba_predictor/pipeline/backfill.py
index 3158b2c..f448fda 100644
--- a/src/nba_predictor/pipeline/backfill.py
+++ b/src/nba_predictor/pipeline/backfill.py
@@ -27,5 +27,7 @@ import argparse
 import json
 import logging
+import os
 import sys
+import tempfile
 from datetime import date, timedelta
 from pathlib import Path
@@ -36,4 +38,5 @@ from nba_predictor import config
 from nba_predictor.pipeline.ingest import (
     enrich_with_boxscores,
+    fetch_player_box,
     fetch_schedule_range,
     to_training_frame,
@@ -101,4 +104,7 @@ def backfill_seasons(
     log=print,
     today: date | None = None,
+    with_players: bool = False,
+    players_path: Path | None = None,
+    fetch_players=None,
 ) -> dict:
     """Warm the cache for `seasons`, then write the combined training cache.
@@ -174,9 +180,20 @@ def backfill_seasons(
     payload = merged.to_dict(orient="records")
 
-    training_path.write_text(json.dumps(payload))
+    _write_json_atomic(training_path, payload)
     log(f"Wrote {len(payload)} training rows to {training_path} "
         f"({len(training_df)} new this run, {len(previous)} carried over)")
 
+    player_summary: dict = {}
+    if with_players:
+        players_path = players_path or (config.DATA_DIR / "cache" / "training" / "player_games.json")
+        player_rows, failed_player_games = fetch_player_rows(games, fetch_players=fetch_players, log=log)
+        player_summary = {
+            "n_player_rows": write_player_games(player_rows, players_path),
+            "players_path": str(players_path),
+            "failed_player_games": failed_player_games,
+        }
+
     return {
+        **player_summary,
         "seasons": per_season,
         "n_training_rows": len(payload),
@@ -192,4 +209,64 @@ def backfill_seasons(
 
 
+PLAYER_COLUMNS = ["game_id", "game_date", "team", "player_id", "minutes", "starter", "points", "rebounds", "assists"]
+
+
+def _write_json_atomic(path: Path, payload) -> None:
+    """Write beside the target, then rename over it. A crash mid-write leaves the OLD file intact and no
+    half-written one: a corrupt cache reads as empty and the next run would overwrite it with fewer rows."""
+    path.parent.mkdir(parents=True, exist_ok=True)
+    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
+    try:
+        with os.fdopen(fd, "w") as handle:
+            json.dump(payload, handle)
+        os.replace(tmp, path)
+    except BaseException:
+        try:
+            os.unlink(tmp)
+        except OSError:
+            pass
+        raise
+
+
+def fetch_player_rows(games: list[dict], *, fetch_players=None, log=print) -> tuple[pd.DataFrame, list[str]]:
+    """One row per player who PLAYED in each finished game that has a team box score.
+
+    `fetch_players(game_id) -> list[dict]` is injected (default `ingest.fetch_player_box`, cached per event and
+    rate-limited). A game that fails is reported, not fatal: the rest are kept and a re-run resumes.
+    """
+    fetch_players = fetch_players or fetch_player_box
+    rows: list[dict] = []
+    failed: list[str] = []
+    for game in games:
+        if not game.get("completed") or "home_fgm" not in game:
+            continue
+        try:
+            players = fetch_players(game["game_id"])
+        except Exception as exc:  # noqa: BLE001 - one game's failure is named, not fatal
+            logger.error("player box for %s failed: %s: %s", game["game_id"], type(exc).__name__, exc)
+            failed.append(game["game_id"])
+            continue
+        for p in players:
+            if not p.get("minutes"):
+                continue
+            rows.append({
+                "game_id": game["game_id"], "game_date": game["game_date"], "team": p["team"],
+                "player_id": str(p["player_id"]), "minutes": float(p["minutes"]), "starter": bool(p.get("starter")),
+                "points": float(p.get("points") or 0), "rebounds": float(p.get("rebounds") or 0),
+                "assists": float(p.get("assists") or 0),
+            })
+    log(f"  player rows: {len(rows)} from {len(games)} games ({len(failed)} failed)")
+    return pd.DataFrame(rows, columns=PLAYER_COLUMNS), failed
+
+
+def write_player_games(new: pd.DataFrame, path: Path) -> int:
+    """Merge into the player cache (dedupe on game+player, newest wins) and write atomically."""
+    previous = _load_existing(path)
+    merged = pd.concat([previous, new], ignore_index=True) if len(previous) else new
+    merged = merged.drop_duplicates(subset=["game_id", "player_id"], keep="last").sort_values(["game_date", "game_id", "player_id"])
+    _write_json_atomic(path, merged.to_dict(orient="records"))
+    return len(merged)
+
+
 def _load_existing(training_path: Path) -> pd.DataFrame:
     """Whatever is already in the training cache, as a frame. Empty when absent
@@ -213,4 +290,8 @@ def main(argv: list[str] | None = None) -> int:
         help="where to write the training cache (default data/cache/training/games.json)",
     )
+    parser.add_argument(
+        "--with-players", action="store_true",
+        help="also fetch each finished game's player box score (minutes, starters) into player_games.json",
+    )
     args = parser.parse_args(argv)
 
@@ -222,9 +303,15 @@ def main(argv: list[str] | None = None) -> int:
     seasons = prior_seasons(args.seasons)
     print(f"Backfilling seasons: {seasons}")
-    summary = backfill_seasons(seasons, training_path=args.training_path)
+    summary = backfill_seasons(seasons, training_path=args.training_path, with_players=args.with_players)
     print(json.dumps(summary, indent=2))
 
     # A partial backfill is not a successful one. Exiting 0 on a run that lost a
     # season is how a caller concludes the fetch is done when it is not.
+    if summary.get("failed_player_games"):
+        print(
+            f"INCOMPLETE: {len(summary['failed_player_games'])} games have no player box score. Re-run to resume.",
+            file=sys.stderr,
+        )
+        return 1
     if summary["failed_seasons"]:
         print(
```
- [ ] **Step 4: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_backfill_players.py tests/test_backfill.py`
Expected: 28 passed
- [ ] **Step 5: Commit** `git add src/nba_predictor/pipeline/backfill.py src/nba_predictor/pipeline/ingest.py tests/test_backfill_players.py`

## Task 10: Block `availability`: who is missing, from player minutes

A "regular" has at least 5 appearances in the team's previous 20 games within 45 days and averaged at least 15 minutes. Features per team-game: `minutes_lost` (share of the 240 team minutes), `star_presence` (share of the top 3 by production who played), `starters_missing`, `rotation_continuity`. Training reads who actually played; serving reads the VERIFIED reported-Out list (`known_absent_from_feed`, which reuses `game_context._verified_out_player_ids`: only rows the feed itself emits, only status Out; this is the rule from the fabricated-injury incident). A team with no rotation in the window (offseason, first games) gets neutral values, not NaN, so early-season games are not dropped.

**Skew, stated not hidden:** training uses actual DNPs (including rest and coach decisions); serving only has reported Outs. Task 12 stores the reported-Out list with each served prediction so the agreement can be measured; report it when enough games exist.

**Files:** Create `src/nba_predictor/features/availability.py`, `tests/test_features_availability.py`.
**Interfaces:** Produces `team_availability(games, player_games, known_absent=None)`, `attach_availability(games, availability)`, `known_absent_from_feed(upcoming, injuries)`, `AVAILABILITY_COLUMNS`.

- [ ] **Step 1: Failing test**
```python
import pandas as pd
import pytest

from nba_predictor.features.availability import (
    AVAILABILITY_COLUMNS, TEAM_MINUTES, attach_availability, team_availability,
)


def _games(n=8, team="BOS", opp="MIA", start="2025-10-20"):
    rows = []
    for i in range(n):
        day = (pd.Timestamp(start) + pd.Timedelta(days=2 * i)).strftime("%Y-%m-%d")
        rows.append({"game_id": f"g{i}", "game_date": day, "home_team": team, "away_team": opp})
    return pd.DataFrame(rows)


ROSTER = {  # id: (minutes, starter, points, rebounds, assists)
    "star": (36, True, 28, 8, 6), "second": (32, True, 20, 5, 5), "third": (30, True, 14, 6, 3),
    "four": (28, True, 10, 4, 2), "five": (26, True, 8, 7, 1), "six": (20, False, 8, 3, 2), "seven": (16, False, 5, 2, 1),
}


def _box(games, missing_in=None, team="BOS"):
    """Everyone plays every game, except the players named per game id in `missing_in`."""
    missing_in = missing_in or {}
    rows = []
    for _, g in games.iterrows():
        for pid, (m, st, pts, reb, ast) in ROSTER.items():
            if pid in missing_in.get(g["game_id"], ()):
                continue
            rows.append({"game_id": g["game_id"], "game_date": g["game_date"], "team": team, "player_id": pid,
                         "minutes": m, "starter": st, "points": pts, "rebounds": reb, "assists": ast})
    return pd.DataFrame(rows)


def _row(av, gid, team="BOS"):
    return av[(av["game_id"] == gid) & (av["team"] == team)].iloc[0]


def test_nobody_missing_means_a_full_rotation():
    games = _games()
    r = _row(team_availability(games, _box(games)), "g7")
    assert r["minutes_lost"] == 0 and r["star_presence"] == 1.0 and r["starters_missing"] == 0 and r["rotation_continuity"] == 1.0


def test_a_missing_star_is_counted_in_minutes_presence_and_starters():
    games = _games()
    box = _box(games, missing_in={"g7": ("star",)})
    r = _row(team_availability(games, box), "g7")
    assert r["minutes_lost"] == pytest.approx(36 / TEAM_MINUTES)
    assert r["star_presence"] == pytest.approx(2 / 3)
    assert r["starters_missing"] == 1
    assert r["rotation_continuity"] < 1.0


def test_a_missing_bench_player_is_not_a_missing_starter():
    games = _games()
    r = _row(team_availability(games, _box(games, missing_in={"g7": ("six",)})), "g7")
    assert r["starters_missing"] == 0 and r["minutes_lost"] == pytest.approx(20 / TEAM_MINUTES)


def test_a_player_who_was_never_a_regular_does_not_count_as_absent():
    games = _games()
    box = _box(games)
    extra = pd.DataFrame([{"game_id": "g0", "game_date": games.loc[0, "game_date"], "team": "BOS", "player_id": "cameo",
                           "minutes": 20, "starter": False, "points": 6, "rebounds": 2, "assists": 1}])
    r = _row(team_availability(games, pd.concat([box, extra], ignore_index=True)), "g7")
    assert r["minutes_lost"] == 0


def test_upcoming_game_uses_the_reported_out_list():
    games = _games(n=9)
    box = _box(games.iloc[:8])                      # g8 has no box: it is upcoming
    av = team_availability(games, box, known_absent={("g8", "BOS"): {"star"}})
    r = _row(av, "g8")
    assert r["minutes_lost"] == pytest.approx(36 / TEAM_MINUTES)
    av_none = team_availability(games, box)
    assert _row(av_none, "g8")["minutes_lost"] == 0


def test_an_offseason_gap_leaves_no_rotation_to_miss():
    games = pd.concat([_games(n=8), _games(n=1, start="2026-10-22").assign(game_id="late")], ignore_index=True)
    box = _box(games.iloc[:8])                      # the season-opener 'late' has no box and no history within 45 days
    assert _row(team_availability(games, box, known_absent={("late", "BOS"): {"star"}}), "late")["minutes_lost"] == 0


def test_the_first_games_of_a_team_have_neutral_values_not_nan():
    games = _games()
    av = team_availability(games, _box(games))
    first = _row(av, "g0")
    assert first[AVAILABILITY_COLUMNS].notna().all()


def test_later_games_never_change_earlier_rows():
    games = _games(n=12)
    box = _box(games)
    full = team_availability(games, box)
    head = team_availability(games.iloc[:9], box[box["game_id"].isin(games.iloc[:9]["game_id"])])
    cols = ["game_id", "team"] + AVAILABILITY_COLUMNS
    pd.testing.assert_frame_equal(full[full["game_id"].isin(games.iloc[:9]["game_id"])][cols].reset_index(drop=True), head[cols].reset_index(drop=True))


def test_attach_adds_home_and_away_columns():
    games = _games()
    out = attach_availability(games, team_availability(games, _box(games)))
    for side in ("home", "away"):
        for c in AVAILABILITY_COLUMNS:
            assert f"{side}_{c}" in out.columns
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_availability.py`
Expected: FAIL: ModuleNotFoundError
- [ ] **Step 2: Implement**
```python
"""Who is missing, from player minutes. Training uses who actually played; serving uses the reported-Out list."""
from __future__ import annotations

from datetime import date

import pandas as pd

LOOKBACK_DAYS = 45          # rotation is read from this many days before the game (offseason -> no rotation)
TRAILING_GAMES = 20         # ...and at most this many of the team's previous games
MIN_APPEARANCES = 5
MIN_AVG_MINUTES = 15.0
TEAM_MINUTES = 240.0
AVAILABILITY_COLUMNS = ["minutes_lost", "star_presence", "starters_missing", "rotation_continuity"]


def _production(rows: pd.DataFrame) -> pd.Series:
    return rows["points"] + 1.2 * rows["rebounds"] + 1.5 * rows["assists"]


def team_availability(
    games: pd.DataFrame, player_games: pd.DataFrame, known_absent: dict[tuple[str, str], set[str]] | None = None,
) -> pd.DataFrame:
    """One row per (game_id, team) with AVAILABILITY_COLUMNS.

    `player_games`: game_id, game_date, team, player_id, minutes, starter, points, rebounds, assists
    (a player appears only in games he played). A "regular" is a player with >= MIN_APPEARANCES in the
    team's previous TRAILING_GAMES games within LOOKBACK_DAYS who averaged >= MIN_AVG_MINUTES.

    Completed games (the box exists): absent = regulars with no row in that game. Games without a box
    (upcoming): absent = `known_absent[(game_id, team)]` intersected with the regulars.
    """
    known_absent = known_absent or {}
    pg = player_games.copy()
    pg = pg[pg["minutes"] > 0]
    boxed = set(pg["game_id"])
    team_games = []
    for side in ("home", "away"):
        team_games.append(games[["game_id", "game_date", f"{side}_team"]].rename(columns={f"{side}_team": "team"}))
    tg = pd.concat(team_games, ignore_index=True).sort_values(["team", "game_date", "game_id"])
    by_game_team = {k: g for k, g in pg.groupby(["game_id", "team"])}
    rows = []
    for team, grp in tg.groupby("team", sort=False):
        ids, dates = grp["game_id"].tolist(), grp["game_date"].tolist()
        for i, (gid, d) in enumerate(zip(ids, dates)):
            today = date.fromisoformat(d)
            prior = [
                ids[j] for j in range(i - 1, max(-1, i - 1 - TRAILING_GAMES), -1)
                if dates[j] < d and (today - date.fromisoformat(dates[j])).days <= LOOKBACK_DAYS
            ]
            frames = [by_game_team[(p, team)] for p in prior if (p, team) in by_game_team]
            result = {"game_id": gid, "team": team, "minutes_lost": 0.0, "star_presence": 1.0,
                      "starters_missing": 0.0, "rotation_continuity": 1.0}
            if frames:
                hist = pd.concat(frames)
                stats = hist.groupby("player_id").agg(
                    apps=("minutes", "size"), avg_min=("minutes", "mean"), starts=("starter", "mean"),
                )
                stats["prod"] = _production(hist).groupby(hist["player_id"]).mean()
                regulars = stats[(stats["apps"] >= MIN_APPEARANCES) & (stats["avg_min"] >= MIN_AVG_MINUTES)]
                if len(regulars):
                    if gid in boxed:
                        played = set(by_game_team[(gid, team)]["player_id"]) if (gid, team) in by_game_team else set()
                        absent = [p for p in regulars.index if p not in played]
                    else:
                        reported = known_absent.get((gid, team), set())
                        absent = [p for p in regulars.index if p in reported]
                    lost = float(regulars.loc[absent, "avg_min"].sum()) if absent else 0.0
                    top3 = regulars.sort_values("prod", ascending=False).head(3).index
                    result["minutes_lost"] = lost / TEAM_MINUTES
                    result["star_presence"] = float(sum(1 for p in top3 if p not in absent)) / len(top3)
                    result["starters_missing"] = float(sum(1 for p in absent if regulars.loc[p, "starts"] >= 0.5))
                    total = float(regulars["avg_min"].sum())
                    result["rotation_continuity"] = (total - lost) / total if total else 1.0
            rows.append(result)
    return pd.DataFrame(rows)


def attach_availability(games: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    keyed = availability.set_index(["game_id", "team"])[AVAILABILITY_COLUMNS]
    out = games.copy()
    for side in ("home", "away"):
        idx = pd.MultiIndex.from_arrays([out["game_id"], out[f"{side}_team"]])
        values = keyed.reindex(idx)
        for c in AVAILABILITY_COLUMNS:
            out[f"{side}_{c}"] = values[c].to_numpy()
    return out


def known_absent_from_feed(upcoming: pd.DataFrame, injuries: list[dict]) -> dict[tuple[str, str], set[str]]:
    """{(game_id, team): {player_id}} of players the VERIFIED ESPN feed marks Out for each upcoming game.

    Reuses `game_context._verified_out_player_ids`: only rows the feed itself emits count, and only status Out
    (Day-To-Day is a flag, never a number). A row of unknown provenance is ignored, which is the rule that
    came out of the fabricated-injury incident.
    """
    from nba_predictor.features.game_context import _verified_out_player_ids

    out_by_team = _verified_out_player_ids(injuries)
    known: dict[tuple[str, str], set[str]] = {}
    for _, game in upcoming.iterrows():
        for team in (game["home_team"], game["away_team"]):
            ids = out_by_team.get(team)
            if ids:
                known[(game["game_id"], team)] = {str(i) for i in ids}
    return known
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_features_availability.py`
Expected: 9 passed
- [ ] **Step 4: Commit** `git add src/nba_predictor/features/availability.py tests/test_features_availability.py`

## Task 11: Compose the blocks in `build_feature_frame`, and remove the dead columns

**What changes:** `FEATURE_COLUMNS` is now the 17 informative columns (the 7 constant-zero ones are gone); `feature_columns(blocks)` composes the base columns with the selected blocks; `build_feature_frame(games, *, blocks, player_games, known_absent)` fails loudly when a block's inputs are missing (never fills zeros); `LEGACY_FEATURE_COLUMNS` / `align_to_fitted` let serving reproduce the 24 columns a pre-change model was fitted on (those seven zeros may be re-created as 0.0, nothing else may). `DEFAULT_BLOCKS = ()`.

**Files:** Modify `src/nba_predictor/features/build.py`, `tests/test_features_build.py`, `tests/test_missing_value_feature_provenance.py`; create `tests/test_feature_blocks_integration.py`.

- [ ] **Step 1: Failing guards (no constant column, causality, parity)**
```python
"""The three guards every feature block must keep green: no constant columns, causality, train/serve parity."""
import pandas as pd

from nba_predictor.features.build import (
    BLOCK_COLUMNS, DEFAULT_BLOCKS, build_feature_frame, feature_columns,
)
from tests.feature_fixtures import (
    make_games, make_player_games, perturb_from, perturb_players_from, with_upcoming,
)

ALL = tuple(BLOCK_COLUMNS)


def _build(games, blocks=ALL, player_games=None, **kw):
    if player_games is None and "availability" in blocks:
        player_games = make_player_games(games)
    return build_feature_frame(games, blocks=blocks, player_games=player_games, **kw)


def test_no_default_feature_column_is_constant():
    frame, cols = _build(make_games(n_days=160), blocks=DEFAULT_BLOCKS)
    constant = [c for c in cols if frame[c].astype(float).nunique() <= 1]
    assert constant == [], f"constant columns carry no information: {constant}"


def test_no_column_of_any_block_is_constant():
    frame, cols = _build(make_games(n_days=160))
    constant = [c for c in cols if frame[c].astype(float).nunique() <= 1]
    assert constant == [], f"constant columns carry no information: {constant}"


def test_non_availability_blocks_never_use_the_game_itself_or_anything_later():
    """Through the cut date INCLUSIVE: a game ON the cut date may not see its own result or box score."""
    games = make_games(n_days=140)
    cut = sorted(games["game_date"].unique())[90]
    blocks = tuple(b for b in ALL if b != "availability")
    a, cols = _build(games, blocks=blocks)
    b, _ = _build(perturb_from(games, cut), blocks=blocks)
    earlier = a[a["game_date"] <= cut].set_index("game_id")[cols]
    after = b.set_index("game_id").reindex(earlier.index)[cols]
    pd.testing.assert_frame_equal(earlier, after)


def test_availability_uses_prior_games_plus_the_game_s_own_participation_and_nothing_later():
    """Availability for game g is 'who is missing from g' (the training stand-in for the reported-Out list at tip-off),
    so it legitimately reads g's own player rows. It must never read a LATER game: perturb from the cut and compare
    only games strictly before it."""
    games = make_games(n_days=140)
    pg = make_player_games(games)
    cut = sorted(games["game_date"].unique())[90]
    a, cols = _build(games, player_games=pg)
    b, _ = _build(perturb_from(games, cut), player_games=perturb_players_from(pg, cut))
    earlier = a[a["game_date"] < cut].set_index("game_id")[cols]
    after = b.set_index("game_id").reindex(earlier.index)[cols]
    pd.testing.assert_frame_equal(earlier, after)


def test_the_served_row_equals_the_row_training_builds_for_the_same_game():
    games = make_games(n_days=140)
    pg = make_player_games(games)
    target = games.iloc[-1]
    gid = target["game_id"]
    trained, cols = _build(games, player_games=pg)
    served_input = with_upcoming(games, 1)                 # the last game: no result, no box score
    pg_served = pg[pg["game_id"] != gid]
    reported_out = {
        (gid, team): set(pg[pg["team"] == team]["player_id"]) - set(pg[(pg["game_id"] == gid) & (pg["team"] == team)]["player_id"])
        for team in (target["home_team"], target["away_team"])
    }
    served, served_cols = _build(served_input, player_games=pg_served, known_absent=reported_out)
    assert served_cols == cols
    t = trained[trained["game_id"] == gid].iloc[0][cols].astype(float)
    s = served[served["game_id"] == gid].iloc[0][cols].astype(float)
    pd.testing.assert_series_equal(t, s, check_names=False)


def test_every_fitted_column_is_present_and_non_null_when_serving():
    games = make_games(n_days=140)
    served, cols = _build(with_upcoming(games, 1), player_games=make_player_games(games).pipe(lambda d: d[d["game_id"] != games.iloc[-1]["game_id"]]))
    row = served[served["game_id"] == games.iloc[-1]["game_id"]]
    assert len(row) == 1 and row[cols].notna().all(axis=None)


def test_the_availability_block_refuses_to_default_to_zeros():
    import pytest
    with pytest.raises(ValueError, match="player_games"):
        build_feature_frame(make_games(n_days=60), blocks=("availability",))


def test_a_block_that_needs_box_columns_fails_loudly_when_they_are_missing():
    import pytest
    games = make_games(n_days=60).drop(columns=["home_fg3a"])
    with pytest.raises(KeyError, match="home_fg3a"):
        build_feature_frame(games, blocks=("form",))


def test_unknown_block_is_an_error():
    import pytest
    with pytest.raises(ValueError, match="unknown feature blocks"):
        feature_columns(("nonsense",))
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_feature_blocks_integration.py`
Expected: FAIL: `BLOCK_COLUMNS` / `blocks=` not defined
- [ ] **Step 2: Edit `features/build.py`**
```diff
diff --git a/src/nba_predictor/features/build.py b/src/nba_predictor/features/build.py
index f7ec8a1..38ad1e9 100644
--- a/src/nba_predictor/features/build.py
+++ b/src/nba_predictor/features/build.py
@@ -1,24 +1,94 @@
 import pandas as pd
 
+from nba_predictor.features.availability import AVAILABILITY_COLUMNS, attach_availability, team_availability
 from nba_predictor.features.context import current_streak, game_flags, is_high_altitude
 from nba_predictor.features.four_factors import add_rolling_four_factors
+from nba_predictor.features.matchup import MATCHUP_COLUMNS, add_matchup
+from nba_predictor.features.opp_adjust import adjusted_ratings_by_date
+from nba_predictor.features.power_rating import pregame_power_ratings
 from nba_predictor.features.rest_travel import compute_rest_days, is_back_to_back
+from nba_predictor.features.schedule_load import SCHEDULE_COLUMNS, add_schedule_load
+from nba_predictor.features.team_form import add_team_form, form_columns
 
-FEATURE_COLUMNS = [
+#: The 17 features that carry information today (the old list also held 7 columns that were all zeros).
+BASE_COLUMNS = [
     "home_efg_pct_roll", "home_tov_rate_roll", "home_orb_pct_roll", "home_ft_rate_roll",
     "away_efg_pct_roll", "away_tov_rate_roll", "away_orb_pct_roll", "away_ft_rate_roll",
-    "home_power_rating", "away_power_rating", "power_rating_diff",
     "home_rest_days", "away_rest_days", "home_back_to_back", "away_back_to_back",
-    "home_fatigue_index", "away_fatigue_index",
-    "home_missing_value", "away_missing_value",
     "home_streak", "away_streak",
     "is_high_altitude", "conference_game", "division_game",
 ]
 
-_OPTIONAL_COLUMNS_DEFAULT_ZERO = [
-    "home_power_rating", "away_power_rating",
+
+def _both(columns: list[str]) -> list[str]:
+    return [f"{side}_{c}" for c in columns for side in ("home", "away")]
+
+
+#: Feature BLOCKS, each scored as a unit against the previous best (see the plan's protocol).
+BLOCK_COLUMNS: dict[str, list[str]] = {
+    "power": ["home_power_rating", "away_power_rating", "power_rating_diff"],
+    "schedule": _both(SCHEDULE_COLUMNS),
+    "form": _both(form_columns()),
+    "adjusted": _both(["adj_off", "adj_def", "adj_net"]),
+    "availability": _both(AVAILABILITY_COLUMNS),
+    "matchup": list(MATCHUP_COLUMNS),
+}
+
+#: A block joins this tuple only in the PR that shows it clears the bar (bootstrap intervals + calibration).
+DEFAULT_BLOCKS: tuple[str, ...] = ()
+
+
+def feature_columns(blocks: tuple[str, ...] = DEFAULT_BLOCKS) -> list[str]:
+    unknown = [b for b in blocks if b not in BLOCK_COLUMNS]
+    if unknown:
+        raise ValueError(f"unknown feature blocks: {unknown}; known: {sorted(BLOCK_COLUMNS)}")
+    cols = list(BASE_COLUMNS)
+    for block in blocks:
+        cols += BLOCK_COLUMNS[block]
+    return cols
+
+
+#: Kept as the name the rest of the code imports: the columns of the default feature set.
+FEATURE_COLUMNS = feature_columns(DEFAULT_BLOCKS)
+
+#: The 24 columns the models fitted BEFORE this change were trained on, in the order they were fitted. Models
+#: already committed carry no `feature_cols` in their manifest, so serving reproduces this exact list for them.
+LEGACY_FEATURE_COLUMNS = [
+    "home_efg_pct_roll", "home_tov_rate_roll", "home_orb_pct_roll", "home_ft_rate_roll",
+    "away_efg_pct_roll", "away_tov_rate_roll", "away_orb_pct_roll", "away_ft_rate_roll",
+    "home_power_rating", "away_power_rating", "power_rating_diff",
+    "home_rest_days", "away_rest_days", "home_back_to_back", "away_back_to_back",
     "home_fatigue_index", "away_fatigue_index",
     "home_missing_value", "away_missing_value",
+    "home_streak", "away_streak",
+    "is_high_altitude", "conference_game", "division_game",
 ]
+#: Those models were fitted with these seven columns equal to 0.0 on every row. Only they may be re-created as 0.0.
+LEGACY_ZERO_COLUMNS = (
+    "home_power_rating", "away_power_rating", "power_rating_diff",
+    "home_fatigue_index", "away_fatigue_index", "home_missing_value", "away_missing_value",
+)
+
+
+def align_to_fitted(frame: pd.DataFrame, fitted: list[str]) -> tuple[pd.DataFrame, list[str]]:
+    """The columns a model was FITTED on, in fitted order. A legacy constant-zero placeholder is re-created as 0.0
+    (that is what the model saw); any other missing column is an error, never a silent zero."""
+    out = frame.copy()
+    missing = [c for c in fitted if c not in out.columns]
+    unknown = [c for c in missing if c not in LEGACY_ZERO_COLUMNS]
+    if unknown:
+        raise KeyError(f"the model was fitted on columns the served frame does not have: {unknown}")
+    for c in missing:
+        out[c] = 0.0
+    return out, list(fitted)
+
+
+#: Box-score columns each block needs on the games frame. Missing ones fail loudly, never fill with zeros.
+_REQUIRED_BOX = {
+    "power": ["home_pts", "away_pts"],
+    "adjusted": ["home_pts", "away_pts"],
+    "form": [f"{s}_{f}" for s in ("home", "away") for f in ("fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov", "pts")],
+    "matchup": [f"{s}_{f}" for s in ("home", "away") for f in ("fg3m", "fg3a", "pts")],
+}
 
 
@@ -41,11 +111,43 @@ def _long_format_box_scores(games: pd.DataFrame) -> pd.DataFrame:
 
 
-def build_feature_frame(games: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
+def _require(games: pd.DataFrame, blocks: tuple[str, ...]) -> None:
+    for block in blocks:
+        missing = [c for c in _REQUIRED_BOX.get(block, []) if c not in games.columns]
+        if missing:
+            raise KeyError(f"feature block {block!r} needs columns the games frame lacks: {missing}")
+
+
+def build_feature_frame(
+    games: pd.DataFrame,
+    *,
+    blocks: tuple[str, ...] = DEFAULT_BLOCKS,
+    player_games: pd.DataFrame | None = None,
+    known_absent: dict[tuple[str, str], set[str]] | None = None,
+) -> tuple[pd.DataFrame, list[str]]:
+    """Training and serving build features through THIS function over the same frame, so a feature that
+    exists in one exists in the other. `known_absent` carries the verified reported-Out list for UPCOMING games."""
+    columns = feature_columns(blocks)
+    _require(games, blocks)
+    if "availability" in blocks and player_games is None:
+        raise ValueError("the availability block needs player_games; refusing to default it to zeros")
     games = games.copy()
 
-    for col in _OPTIONAL_COLUMNS_DEFAULT_ZERO:
-        if col not in games.columns:
-            games[col] = 0.0
-    games["power_rating_diff"] = games["home_power_rating"] - games["away_power_rating"]
+    def _fresh(frame: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
+        """Join `new` columns onto `frame`, replacing any same-named column already there."""
+        return frame.drop(columns=[c for c in new.columns if c in frame.columns]).join(new)
+
+    if "power" in blocks:
+        games = _fresh(games, pregame_power_ratings(games))
+        games["power_rating_diff"] = games["home_power_rating"] - games["away_power_rating"]
+    if "schedule" in blocks:
+        games = add_schedule_load(games)
+    if "form" in blocks or "matchup" in blocks:
+        games = add_team_form(games)
+    if "matchup" in blocks:
+        games = add_matchup(games)
+    if "adjusted" in blocks:
+        games = _fresh(games, adjusted_ratings_by_date(games))
+    if "availability" in blocks:
+        games = attach_availability(games, team_availability(games, player_games, known_absent))
 
     long_form = add_rolling_four_factors(_long_format_box_scores(games))
@@ -99,8 +201,8 @@ def build_feature_frame(games: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
     games["division_game"] = flags["division_game"]
 
-    games = games.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)
-    return games, FEATURE_COLUMNS
+    games = games.dropna(subset=columns).reset_index(drop=True)
+    return games, columns
 
 
-def build_training_frame(games: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
-    return build_feature_frame(games)
+def build_training_frame(games: pd.DataFrame, **kwargs) -> tuple[pd.DataFrame, list[str]]:
+    return build_feature_frame(games, **kwargs)
```
- [ ] **Step 3: Replace the three old tests (the ones that asserted the defect)**
```diff
diff --git a/tests/test_features_build.py b/tests/test_features_build.py
index 10fec66..548641e 100644
--- a/tests/test_features_build.py
+++ b/tests/test_features_build.py
@@ -18,7 +18,7 @@ def _sample_games() -> pd.DataFrame:
                 "away_pts": 105 + i,
                 "home_fgm": 40, "home_fga": 88, "home_fg3m": 12, "home_tov": 11,
-                "home_oreb": 9, "home_dreb": 32, "home_fta": 20,
+                "home_oreb": 9, "home_dreb": 32, "home_fta": 20, "home_fg3a": 30, "home_ftm": 15, "home_ast": 22, "home_stl": 7, "home_blk": 4, "home_pf": 19,
                 "away_fgm": 38, "away_fga": 90, "away_fg3m": 10, "away_tov": 13,
-                "away_oreb": 10, "away_dreb": 30, "away_fta": 18,
+                "away_oreb": 10, "away_dreb": 30, "away_fta": 18, "away_fg3a": 30, "away_ftm": 15, "away_ast": 22, "away_stl": 7, "away_blk": 4, "away_pf": 19,
                 "home_win": 1,
             }
@@ -48,23 +48,14 @@ def test_build_training_frame_drops_rows_with_no_rolling_history():
 
 
-def test_build_training_frame_fills_missing_optional_columns_with_zero():
-    from nba_predictor.features.build import build_training_frame
-
-    games = _sample_games()
-    result_df, _ = build_training_frame(games)
-
-    assert (result_df["home_power_rating"] == 0.0).all()
-    assert (result_df["home_fatigue_index"] == 0.0).all()
-    assert (result_df["home_missing_value"] == 0.0).all()
+def test_default_features_contain_no_constant_zero_placeholders():
+    """The old default list carried seven columns that were zero on every training row."""
+    from nba_predictor.features.build import FEATURE_COLUMNS
 
+    dead = {
+        "home_power_rating", "away_power_rating", "power_rating_diff",
+        "home_fatigue_index", "away_fatigue_index", "home_missing_value", "away_missing_value",
+    }
+    assert dead.isdisjoint(FEATURE_COLUMNS)
 
-def test_build_training_frame_respects_precomputed_optional_columns():
-    from nba_predictor.features.build import build_training_frame
-
-    games = _sample_games()
-    games["home_power_rating"] = 1550.0
-    result_df, _ = build_training_frame(games)
-
-    assert (result_df["home_power_rating"] == 1550.0).all()
 
 
@@ -78,7 +69,7 @@ def test_build_feature_frame_computes_rolling_features_for_upcoming_game():
             "home_win": None,
             "home_fgm": None, "home_fga": None, "home_fg3m": None, "home_tov": None,
-            "home_oreb": None, "home_dreb": None, "home_fta": None,
+            "home_oreb": None, "home_dreb": None, "home_fta": None, "home_fg3a": None, "home_ftm": None, "home_ast": None, "home_stl": None, "home_blk": None, "home_pf": None,
             "away_fgm": None, "away_fga": None, "away_fg3m": None, "away_tov": None,
-            "away_oreb": None, "away_dreb": None, "away_fta": None,
+            "away_oreb": None, "away_dreb": None, "away_fta": None, "away_fg3a": None, "away_ftm": None, "away_ast": None, "away_stl": None, "away_blk": None, "away_pf": None,
         }
     ])
@@ -102,7 +93,7 @@ def test_build_feature_frame_does_not_record_a_result_for_upcoming_games():
             "home_win": None,
             "home_fgm": None, "home_fga": None, "home_fg3m": None, "home_tov": None,
-            "home_oreb": None, "home_dreb": None, "home_fta": None,
+            "home_oreb": None, "home_dreb": None, "home_fta": None, "home_fg3a": None, "home_ftm": None, "home_ast": None, "home_stl": None, "home_blk": None, "home_pf": None,
             "away_fgm": None, "away_fga": None, "away_fg3m": None, "away_tov": None,
-            "away_oreb": None, "away_dreb": None, "away_fta": None,
+            "away_oreb": None, "away_dreb": None, "away_fta": None, "away_fg3a": None, "away_ftm": None, "away_ast": None, "away_stl": None, "away_blk": None, "away_pf": None,
         },
         {
@@ -110,7 +101,7 @@ def test_build_feature_frame_does_not_record_a_result_for_upcoming_games():
             "home_win": None,
             "home_fgm": None, "home_fga": None, "home_fg3m": None, "home_tov": None,
-            "home_oreb": None, "home_dreb": None, "home_fta": None,
+            "home_oreb": None, "home_dreb": None, "home_fta": None, "home_fg3a": None, "home_ftm": None, "home_ast": None, "home_stl": None, "home_blk": None, "home_pf": None,
             "away_fgm": None, "away_fga": None, "away_fg3m": None, "away_tov": None,
-            "away_oreb": None, "away_dreb": None, "away_fta": None,
+            "away_oreb": None, "away_dreb": None, "away_fta": None, "away_fg3a": None, "away_ftm": None, "away_ast": None, "away_stl": None, "away_blk": None, "away_pf": None,
         },
     ])
```
```diff
diff --git a/tests/test_missing_value_feature_provenance.py b/tests/test_missing_value_feature_provenance.py
index f765e5f..9e5248a 100644
--- a/tests/test_missing_value_feature_provenance.py
+++ b/tests/test_missing_value_feature_provenance.py
@@ -174,28 +174,4 @@ def _two_games():
 
 
-def test_missing_value_is_filled_with_a_constant_zero_not_from_the_stub():
-    from nba_predictor.features.build import build_feature_frame
-
-    result, feature_cols = build_feature_frame(_two_games())
-
-    assert "home_missing_value" in feature_cols
-    assert (result["home_missing_value"] == 0.0).all()
-    assert (result["away_missing_value"] == 0.0).all()
-
-
-def test_a_real_measured_missing_value_is_indistinguishable_from_the_default():
-    # The recorded defect. A column a real source filled with 0.0 and the
-    # default 0.0 produce the same frame, so nothing downstream can tell
-    # "nobody is missing a player" from "we never looked".
-    from nba_predictor.features.build import build_feature_frame
-
-    defaulted = build_feature_frame(_two_games())[0]
-    measured_zero = build_feature_frame(
-        _two_games().assign(home_missing_value=0.0, away_missing_value=0.0)
-    )[0]
-
-    assert defaulted["home_missing_value"].equals(measured_zero["home_missing_value"])
-    assert defaulted["away_missing_value"].equals(measured_zero["away_missing_value"])
-
 
 def test_the_manifest_does_not_claim_a_missing_value_metric():
@@ -217,2 +193,10 @@ def test_the_player_models_have_no_injury_feature_at_all(model_name):
         "points_roll", "rebounds_roll", "assists_roll", "fg3m_roll", "minutes_roll",
     ]
+
+
+def test_the_default_feature_set_has_no_missing_value_placeholder_columns():
+    """The constant-zero `*_missing_value` columns are gone from the default feature set. Availability now comes from
+    observed player minutes (features/availability.py), and the block refuses to run without that data."""
+    from nba_predictor.features.build import FEATURE_COLUMNS
+
+    assert not [c for c in FEATURE_COLUMNS if c.endswith("_missing_value")]
```
- [ ] **Step 4: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_feature_blocks_integration.py tests/test_features_*.py tests/test_missing_value_feature_provenance.py`
Expected: all pass

Note the causality test is two tests on purpose: every block except availability is causal THROUGH the cut date (a game on that date may not see its own result or box); availability reads the game's own participation by design, so it is checked strictly before the cut.
- [ ] **Step 5: Commit** `git add src/nba_predictor/features/build.py tests/test_feature_blocks_integration.py tests/test_features_build.py tests/test_missing_value_feature_provenance.py`

## Task 12: Retrain records what it fitted; serving rebuilds exactly that

**What changes:** `run_retrain_pipeline(..., blocks, player_games)` passes the blocks through and writes `training.feature_blocks` and `training.feature_cols` to the manifest. Serving (`score_upcoming_games`, `score_and_store_predictions`) rebuilds with the manifest's blocks, selects the manifest's columns in the manifest's order, treats a manifest WITHOUT `feature_cols` as the legacy 24 columns (so the models already committed keep serving until the next retrain), and for an availability model REFUSES to score without the player cache and the verified injury report. `score_upcoming_games` takes `injuries=`. The builder is resolved at call time, not bound as a default argument (a default captures the original function and ignores a test patch).

**Files:** Modify `pipeline/retrain.py`, `pipeline/ingest.py`, `tests/test_api_coherence.py`; create `tests/test_serving_feature_parity.py`.

- [ ] **Step 1: Failing test**
```python
"""A model is only ever scored on the columns it was FITTED on, rebuilt the way it was fitted."""
import json

import numpy as np
import pandas as pd
import pytest

from nba_predictor.features.availability import known_absent_from_feed
from nba_predictor.features.build import LEGACY_FEATURE_COLUMNS, LEGACY_ZERO_COLUMNS, align_to_fitted, build_feature_frame
from nba_predictor.pipeline import ingest
from nba_predictor.pipeline.retrain import run_retrain_pipeline
from tests.feature_fixtures import make_games, with_upcoming


def test_a_legacy_model_gets_its_seven_zero_placeholders_back_in_fitted_order():
    frame, cols = build_feature_frame(make_games(n_days=60))
    out, fitted = align_to_fitted(frame, LEGACY_FEATURE_COLUMNS)
    assert fitted == LEGACY_FEATURE_COLUMNS and len(fitted) == 24
    for c in LEGACY_ZERO_COLUMNS:
        assert (out[c] == 0.0).all()
    assert list(out[fitted].columns) == LEGACY_FEATURE_COLUMNS


def test_any_other_missing_fitted_column_is_a_loud_error_never_a_zero():
    frame, _ = build_feature_frame(make_games(n_days=60))
    with pytest.raises(KeyError, match="home_net_r10"):
        align_to_fitted(frame, ["home_efg_pct_roll", "home_net_r10"])


def test_the_manifest_records_the_blocks_and_columns_the_model_was_fitted_on(tmp_path):
    games = make_games(n_days=200)
    manifest = run_retrain_pipeline(games, tmp_path / "m", "v-t", "2026-11-01T00:00:00", blocks=("power", "schedule"))
    training = manifest["training"]
    assert training["feature_blocks"] == ["power", "schedule"]
    assert "home_power_rating" in training["feature_cols"] and "home_fatigue_index" in training["feature_cols"]
    assert json.loads((tmp_path / "m" / "manifest.json").read_text())["training"]["feature_cols"] == training["feature_cols"]


def test_serving_scores_with_the_blocks_the_model_was_trained_with(tmp_path):
    games = make_games(n_days=200)
    models_dir = tmp_path / "m"
    run_retrain_pipeline(games, models_dir, "v-t", "2026-11-01T00:00:00", blocks=("power", "schedule", "form"))
    manifest = json.loads((models_dir / "manifest.json").read_text())
    served_in = with_upcoming(games, 2)
    served_in["home_win"] = served_in["home_win"]
    frame, cols = ingest._serving_frame(served_in, manifest)
    assert cols == manifest["training"]["feature_cols"]
    up = frame[frame["home_win"].isna()]
    assert len(up) == 2 and up[cols].notna().all(axis=None)


def test_serving_a_model_that_uses_availability_refuses_to_default(tmp_path, monkeypatch):
    games = make_games(n_days=120)
    manifest = {"training": {"feature_blocks": ["availability"], "feature_cols": ["home_minutes_lost"]}}
    from nba_predictor import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="player_games.json"):
        ingest._serving_frame(games, manifest, injuries=[])
    (tmp_path / "cache" / "training").mkdir(parents=True)
    (tmp_path / "cache" / "training" / "player_games.json").write_text("[]")
    with pytest.raises(ValueError, match="verified injury report"):
        ingest._serving_frame(games, manifest, injuries=None)


def test_known_absent_uses_only_the_verified_feed_and_only_status_out():
    upcoming = pd.DataFrame([{"game_id": "g1", "home_team": "BOS", "away_team": "MIA"}])
    feed = [
        {"team": "BOS", "player_id": "11", "player_name": "A", "status": "Out", "dated": "Oct 7"},
        {"team": "BOS", "player_id": "12", "player_name": "B", "status": "Day-To-Day", "dated": "Oct 7"},
        {"team": "MIA", "player_id": "21", "player_name": "C", "status": "Out", "dated": "Oct 7", "source": "rumour"},
    ]
    assert known_absent_from_feed(upcoming, feed) == {("g1", "BOS"): {"11"}}
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_serving_feature_parity.py`
Expected: FAIL: `blocks=` / `_serving_frame` not defined
- [ ] **Step 2: Edit `pipeline/retrain.py`**
```diff
diff --git a/src/nba_predictor/pipeline/retrain.py b/src/nba_predictor/pipeline/retrain.py
index 830d4af..02175bb 100644
--- a/src/nba_predictor/pipeline/retrain.py
+++ b/src/nba_predictor/pipeline/retrain.py
@@ -7,5 +7,5 @@ import numpy as np
 import pandas as pd
 
-from nba_predictor.features.build import build_training_frame
+from nba_predictor.features.build import DEFAULT_BLOCKS, build_training_frame
 from nba_predictor.models.candidate_race import run_candidate_race
 from nba_predictor.models.evaluate.walk_forward import chronological_split
@@ -79,5 +79,13 @@ def _nba_season_start_year(game_date: str) -> int:
 
 
-def run_retrain_pipeline(games: pd.DataFrame, models_dir: Path, model_version: str, trained_at: str) -> dict:
+def run_retrain_pipeline(
+    games: pd.DataFrame,
+    models_dir: Path,
+    model_version: str,
+    trained_at: str,
+    *,
+    blocks: tuple[str, ...] = DEFAULT_BLOCKS,
+    player_games: pd.DataFrame | None = None,
+) -> dict:
     models_dir.mkdir(parents=True, exist_ok=True)
 
@@ -89,6 +97,8 @@ def run_retrain_pipeline(games: pd.DataFrame, models_dir: Path, model_version: s
     )
 
-    train_df, feature_cols = build_training_frame(train_games)
-    holdout_df, _ = build_training_frame(pd.concat([train_games, holdout_games], ignore_index=True))
+    train_df, feature_cols = build_training_frame(train_games, blocks=blocks, player_games=player_games)
+    holdout_df, _ = build_training_frame(
+        pd.concat([train_games, holdout_games], ignore_index=True), blocks=blocks, player_games=player_games,
+    )
     holdout_df = holdout_df[holdout_df["game_id"].isin(holdout_games["game_id"])]
 
@@ -226,4 +236,7 @@ def run_retrain_pipeline(games: pd.DataFrame, models_dir: Path, model_version: s
             "n_holdout_games": int(len(holdout_games)),
             "n_current_season_games": n_current_season_games,
+            # What serving must rebuild: a model is only ever scored on the columns it was fitted on.
+            "feature_blocks": list(blocks),
+            "feature_cols": list(feature_cols),
             "win_candidate": win_candidate,
             "margin_candidate": margin_candidate,
```
- [ ] **Step 3: Edit `pipeline/ingest.py` (serving)**
```diff
diff --git a/src/nba_predictor/pipeline/ingest.py b/src/nba_predictor/pipeline/ingest.py
index 0df3469..d2b4193 100644
--- a/src/nba_predictor/pipeline/ingest.py
+++ b/src/nba_predictor/pipeline/ingest.py
@@ -14,5 +14,8 @@ from nba_predictor import config
 from nba_predictor.data import espn
 from nba_predictor.data.team_reference import get_team
-from nba_predictor.features.build import build_feature_frame, build_training_frame
+from nba_predictor.features.availability import known_absent_from_feed
+from nba_predictor.features.build import (
+    LEGACY_FEATURE_COLUMNS, align_to_fitted, build_feature_frame, build_training_frame,
+)
 from nba_predictor.features.player_stats import build_player_feature_frame
 from nba_predictor.features.context import current_streak
@@ -370,5 +378,36 @@ def to_scoring_frame(games: list[dict]) -> pd.DataFrame:
 
 
-def score_upcoming_games(games: list[dict], models_dir: Path, db_path: Path, model_version: str) -> int:
+def _serving_frame(
+    games_df: pd.DataFrame, manifest: dict, *, injuries: list[dict] | None = None, builder=None,
+) -> tuple[pd.DataFrame, list[str]]:
+    """Features for serving, rebuilt the way the model was FITTED: its blocks, its columns, in its order.
+
+    A manifest from before this change has no `feature_cols`: those models were fitted on LEGACY_FEATURE_COLUMNS.
+    The availability block needs the player cache and (for upcoming games) the verified Out list; both are required,
+    so a model that uses availability is never scored on defaults.
+    """
+    # Resolved at call time, not bound as a default: a default would capture the original function and ignore a patch.
+    builder = builder or build_feature_frame
+    training = manifest.get("training", {})
+    blocks = tuple(training.get("feature_blocks", ()))
+    fitted = list(training.get("feature_cols") or LEGACY_FEATURE_COLUMNS)
+    player_games = None
+    known_absent = None
+    if "availability" in blocks:
+        players_path = config.DATA_DIR / "cache" / "training" / "player_games.json"
+        if not players_path.exists():
+            raise FileNotFoundError(f"the model uses availability but {players_path} is missing; refusing to score on defaults")
+        player_games = pd.DataFrame(json.loads(players_path.read_text()))
+        if injuries is None:
+            raise ValueError("the model uses availability: pass the verified injury report (injuries=...), never default to none")
+        upcoming = games_df[games_df["home_win"].isna()]
+        known_absent = known_absent_from_feed(upcoming, injuries)
+    frame, _ = builder(games_df, blocks=blocks, player_games=player_games, known_absent=known_absent)
+    return align_to_fitted(frame, fitted)
+
+
+def score_upcoming_games(
+    games: list[dict], models_dir: Path, db_path: Path, model_version: str, injuries: list[dict] | None = None,
+) -> int:
     """Scores every not-yet-completed game using real prior-game rolling
     features (via to_scoring_frame + build_feature_frame) and stores the
@@ -383,7 +422,5 @@ def score_upcoming_games(games: list[dict], models_dir: Path, db_path: Path, mod
     silently falling back."""
     scoring_df = to_scoring_frame(games)
-    frame, feature_cols = build_feature_frame(scoring_df)
-    upcoming_frame = frame[frame["home_win"].isna()].reset_index(drop=True)
-    if len(upcoming_frame) == 0:
+    if not scoring_df["home_win"].isna().any():
         return 0
 
@@ -408,4 +445,9 @@ def score_upcoming_games(games: list[dict], models_dir: Path, db_path: Path, mod
         raise ValueError(f"manifest missing positive finite margin_sigma; cannot serve win-from-margin. Got: {margin_sigma!r}")
 
+    frame, feature_cols = _serving_frame(scoring_df, manifest, injuries=injuries)
+    upcoming_frame = frame[frame["home_win"].isna()].reset_index(drop=True)
+    if len(upcoming_frame) == 0:
+        return 0
+
     margins = margin_model.predict(upcoming_frame[feature_cols])
     totals = total_model.predict(upcoming_frame[feature_cols])
@@ -853,5 +895,5 @@ def score_and_store_predictions(games_df: pd.DataFrame, models_dir: Path, db_pat
         raise ValueError(f"manifest missing positive finite margin_sigma; cannot serve win-from-margin. Got: {margin_sigma!r}")
 
-    frame, feature_cols = build_training_frame(games_df)
+    frame, feature_cols = _serving_frame(games_df, manifest, builder=build_training_frame)
     if len(frame) == 0:
         return 0
```
- [ ] **Step 4: Update the existing coherence test's manifest to carry `feature_cols` like a real manifest**
```diff
diff --git a/tests/test_api_coherence.py b/tests/test_api_coherence.py
index b7c0217..25a36d5 100644
--- a/tests/test_api_coherence.py
+++ b/tests/test_api_coherence.py
@@ -87,4 +87,6 @@ def test_score_upcoming_games_uses_win_from_margin(tmp_path):
     models_dir.mkdir()
     (models_dir / "manifest.json").write_text(json.dumps({
+        # A real manifest names the columns the model was fitted on; this test's mocked builder returns f1, f2.
+        "training": {"feature_blocks": [], "feature_cols": ["f1", "f2"]},
         "metrics": {"margin": {"residual_sigma": 15.87}}
     }))
```
- [ ] **Step 5: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_serving_feature_parity.py tests/test_api_coherence.py tests/test_pipeline_ingest.py tests/test_pipeline_retrain.py tests/test_retrain_freshness.py`
Expected: all pass
- [ ] **Step 6: Record the reported-Out list with each served prediction** (for measuring the availability skew later). Add a table `injury_snapshots(game_id TEXT, team TEXT, player_id TEXT, created_at TEXT)` in `tracking/store.py` (additive, `CREATE TABLE IF NOT EXISTS`) and write one row per reported-Out player per upcoming game inside `score_upcoming_games` when `injuries` is supplied. Test: a scored game with a reported Out writes exactly that row and a re-score does not duplicate it. This is plumbing only; it does not change any stored prediction.
- [ ] **Step 7: Commit** `git add src/nba_predictor/pipeline/retrain.py src/nba_predictor/pipeline/ingest.py src/nba_predictor/tracking/store.py tests/test_serving_feature_parity.py tests/test_api_coherence.py`

## Task 13: The block evaluation tool

Scores a block set against a baseline on the identical held-out games with the repo's own `paired_bootstrap` and `calibration_gap`. Features are built over the WHOLE multi-season frame once per block set; the held-out window is `split_start..split_end` (default Phase A's `2025-10-02..2026-10-04`); history joins TRAINING only. `compare` REFUSES (raises) if the held-out games differ.

**Files:** Create `tools/feature_block_eval.py`, `tests/test_feature_block_eval.py`.
**Interfaces:** Produces `score_blocks(all_games, blocks, player_games, split_start, split_end, windows, fixed_total_baseline)`, `compare(baseline, candidate, n_resamples, seed)` -> `{table, gap_baseline, gap_candidate, gap_widened, not_improved, clears_the_bar, n_held_out}`, `render(label, result)`, CLI `python tools/feature_block_eval.py --baseline power --candidate power,schedule`.

- [ ] **Step 1: Failing test**
```python
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import feature_block_eval as fbe  # noqa: E402

from tests.feature_fixtures import make_games  # noqa: E402


def _all_games():
    return make_games(n_days=420, seed=3)


def _split(games):
    days = sorted(games["game_date"].unique())
    return days[200], days[-1]


def test_identical_blocks_are_not_an_improvement_and_hold_out_the_same_games():
    games = _all_games()
    start, end = _split(games)
    a = fbe.score_blocks(games, (), split_start=start, split_end=end)
    b = fbe.score_blocks(games, (), split_start=start, split_end=end)
    out = fbe.compare(a, b, n_resamples=200)
    assert out["n_held_out"] > 100
    assert out["not_improved"] and out["clears_the_bar"] is False
    assert all(abs(v["difference"]) < 1e-12 for v in out["table"].values())


def test_a_candidate_block_is_scored_on_the_same_games_as_the_baseline():
    games = _all_games()
    start, end = _split(games)
    base = fbe.score_blocks(games, (), split_start=start, split_end=end)
    cand = fbe.score_blocks(games, ("power", "schedule"), split_start=start, split_end=end)
    out = fbe.compare(base, cand, n_resamples=200)
    assert set(out["table"]) == set(fbe.METRICS)
    assert cand["n_features"] > base["n_features"]
    assert "VERDICT" in fbe.render("power+schedule vs none", out)


def test_comparing_different_held_out_games_is_refused():
    games = _all_games()
    start, end = _split(games)
    a = fbe.score_blocks(games, (), split_start=start, split_end=end)
    b = fbe.score_blocks(games, (), split_start=start, split_end=sorted(games["game_date"].unique())[-30])
    with pytest.raises(ValueError, match="held-out games differ"):
        fbe.compare(a, b, n_resamples=50)
```
Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_feature_block_eval.py`
Expected: FAIL: no module `feature_block_eval`
- [ ] **Step 2: Implement**
```python
"""Score a set of feature BLOCKS against the previous best on the IDENTICAL held-out games.

A block ships only if (1) its paired-bootstrap 95% interval excludes zero on every metric it claims, and
(2) the 5-bucket calibration gap does not widen. This module does the scoring; `main` runs it on the real
training cache. Features are built over the WHOLE multi-season frame once per block set, so season-opening
games carry their history; the held-out games are the `split_start..split_end` window, identical by assertion.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nba_predictor.features.build import build_training_frame  # noqa: E402
from nba_predictor.models.artifact_gate import calibration_gap  # noqa: E402
from nba_predictor.models.candidate_race import default_candidates  # noqa: E402
from nba_predictor.models.evaluate.paired_bootstrap import paired_bootstrap  # noqa: E402
from nba_predictor.models.evaluate.walk_forward_eval import walk_forward_metrics, walk_forward_regression  # noqa: E402

PHASE_A_START = "2025-10-02"
PHASE_A_END = "2026-10-04"
N_BUCKETS = 5
N_RESAMPLES = 2000
SEED = 20261007

#: metric label -> (which target, metric name understood by paired_bootstrap)
METRICS = {
    "win log_loss": ("win", "log_loss"),
    "win brier": ("win", "brier"),
    "win auc": ("win", "auc"),
    "margin mae": ("margin", "mae"),
    "total mae": ("total", "mae"),
}


def score_blocks(
    all_games: pd.DataFrame,
    blocks: tuple[str, ...],
    *,
    player_games: pd.DataFrame | None = None,
    split_start: str = PHASE_A_START,
    split_end: str = PHASE_A_END,
    windows: int = 4,
    fixed_total_baseline: float | None = None,
) -> dict:
    """Walk-forward scores for one block set. History (before `split_start`) joins TRAINING only."""
    frame, cols = build_training_frame(all_games, blocks=blocks, player_games=player_games)
    frame = frame.assign(home_margin=frame["home_pts"] - frame["away_pts"], home_total=frame["home_pts"] + frame["away_pts"])
    current = frame[(frame["game_date"] >= split_start) & (frame["game_date"] <= split_end)]
    history = frame[frame["game_date"] < split_start]
    cands = default_candidates(cols)
    win = walk_forward_metrics(current, model_factory=lambda tr: cands["logistic"]["win"](tr), windows=windows, history_df=history)
    margin = walk_forward_regression(
        current, model_factory=lambda tr: cands["ridge"]["margin"](tr), target="home_margin", windows=windows, history_df=history,
    )
    total = walk_forward_regression(
        current, model_factory=lambda tr: cands["ridge"]["total"](tr), target="home_total", windows=windows,
        fixed_baseline=fixed_total_baseline, history_df=history,
    )
    return {"blocks": tuple(blocks), "n_features": len(cols), "win": win, "margin": margin, "total": total}


def _pooled(result: dict, target: str) -> dict:
    return result[target]["pooled"]


def compare(baseline: dict, candidate: dict, *, n_resamples: int = N_RESAMPLES, seed: int = SEED) -> dict:
    """Paired bootstrap + calibration on the identical held-out games. Refuses if the held-out games differ."""
    for target in ("win", "margin", "total"):
        by, cy = np.asarray(_pooled(baseline, target)["y"]), np.asarray(_pooled(candidate, target)["y"])
        if by.shape != cy.shape or not np.array_equal(by, cy):
            raise ValueError(
                f"the {target} held-out games differ between baseline ({by.shape[0]}) and candidate ({cy.shape[0]}): "
                "a comparison on different games is not a comparison"
            )
    table = {}
    for label, (target, metric) in METRICS.items():
        b, c = _pooled(baseline, target), _pooled(candidate, target)
        table[label] = paired_bootstrap(
            np.asarray(b["y"]), np.asarray(b["preds"]), np.asarray(c["preds"]), metric, n_resamples=n_resamples, seed=seed,
        )
    win_y = np.asarray(_pooled(baseline, "win")["y"])
    gap_base = calibration_gap(win_y, np.asarray(_pooled(baseline, "win")["preds"]), n_buckets=N_BUCKETS)
    gap_cand = calibration_gap(win_y, np.asarray(_pooled(candidate, "win")["preds"]), n_buckets=N_BUCKETS)
    short = [name for name, out in table.items() if not out["improved"]]
    return {
        "table": table, "gap_baseline": gap_base, "gap_candidate": gap_cand,
        "gap_widened": gap_cand > gap_base, "not_improved": short,
        "clears_the_bar": not short and gap_cand <= gap_base,
        "n_held_out": int(win_y.shape[0]),
    }


def render(label: str, result: dict) -> str:
    lines = [f"=== {label}: {result['n_held_out']} identical held-out games", f"{'metric':<14}{'baseline':>10}{'candidate':>11}{'diff':>10}{'95% interval':>24}  verdict"]
    for name, out in result["table"].items():
        lines.append(
            f"{name:<14}{out['baseline']:>10.4f}{out['candidate']:>11.4f}{out['difference']:>+10.4f}"
            f"{'[%+.4f, %+.4f]' % (out['ci_low'], out['ci_high']):>24}  {'IMPROVED' if out['improved'] else 'not distinguishable'}"
        )
    lines.append(
        f"calibration gap {result['gap_baseline']:.4f} -> {result['gap_candidate']:.4f} "
        f"({'WIDENED' if result['gap_widened'] else 'not widened'})"
    )
    lines.append("VERDICT: " + ("CLEARS the bar" if result["clears_the_bar"] else "NOT cleared: " + (", ".join(result["not_improved"]) or "calibration widened")))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", default="", help="comma-separated block names already in the model ('' = none)")
    ap.add_argument("--candidate", required=True, help="comma-separated block names to score against the baseline")
    ap.add_argument("--training", type=Path, default=Path("data/cache/training/games.json"))
    ap.add_argument("--players", type=Path, default=Path("data/cache/training/player_games.json"))
    args = ap.parse_args(argv)
    games = pd.DataFrame(json.loads(args.training.read_text()))
    blocks_b = tuple(b for b in args.baseline.split(",") if b)
    blocks_c = tuple(b for b in args.candidate.split(",") if b)
    players = pd.DataFrame(json.loads(args.players.read_text())) if (args.players.exists() and "availability" in blocks_b + blocks_c) else None
    base = score_blocks(games, blocks_b, player_games=players)
    cand = score_blocks(games, blocks_c, player_games=players)
    print(render(f"{'+'.join(blocks_c) or 'none'} vs {'+'.join(blocks_b) or 'none'}", compare(base, cand)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
- [ ] **Step 3: Run** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_feature_block_eval.py`
Expected: 3 passed
- [ ] **Step 4: Full suite** Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider`
Expected: 937 passed, 23 skipped (or main's count plus this plan's new tests)
- [ ] **Step 5: Commit** `git add tools/feature_block_eval.py tests/test_feature_block_eval.py`

## Task 14: Fetch the data, then evaluate each block (one PR per block)

This is the measurement the whole plan exists for. Nothing here is code to write; it is a procedure with decision rules.

- [ ] **Step 1: Refresh the training cache with the wider box score.** Old cached box scores lack the new fields and are now refetched (Task 2). In a worktree: `uv run --python 3.13 -m nba_predictor.pipeline.backfill --seasons 3 --with-players`. It is resumable (re-run if a season or game fails; exit code 1 means incomplete) and rate-limited (about 6,000 team-box and about 4,000 player-box requests). Report games per season, the missing-data rate for each new field and `n_player_rows`. Do NOT commit the raw ESPN cache files (a later PR commits a compact training frame and player table).
- [ ] **Step 2: Baseline.** `python tools/feature_block_eval.py --baseline '' --candidate ''` must reproduce itself with zero differences and the same `n_held_out` as before (758 on the Phase A window when the frame includes the playoff games).
- [ ] **Step 3: One block at a time, in this order:** `power`, then `schedule`, then `form`, then `adjusted`, then `availability` (needs `player_games.json`), then `matchup`. For block B with the already-accepted set A: `--baseline A --candidate A,B`. Paste each rendered table into `docs/nba-feature-blocks-evaluation-2026-10.md`.
- [ ] **Step 4: Decision rule (no exceptions).** A block joins `DEFAULT_BLOCKS` only if its table says `CLEARS the bar` (every claimed metric's 95% interval excludes zero in the better direction AND the calibration gap did not widen). A block that fails stays out and the doc says which metric failed. Within a block run the ablation (drop each sub-group, e.g. only `r10` vs `r10,ewm`, only `adj_net`) and keep only sub-groups that earn their place. Do not test many single features against the same held-out games.
- [ ] **Step 3b: Check calibration after any accepted block** with the existing 5-bucket reliability table; the standing calibration PR (fit inside the walk-forward) is the remedy for a widened gap, not a reason to ship a block that widens it.
- [ ] **Step 5: One PR per accepted block:** a one-line change adding it to `DEFAULT_BLOCKS`, the evaluation table in the doc, and a retrain through the candidate race on the multi-season frame. Report the real manifest numbers (holdout named). Do not deploy; the reviewer deploys, because merging code does not replace the live model files.
- [ ] **Step 6: Availability only:** after enough upcoming games have been scored with Task 12's snapshot, report the agreement between reported-Out and actual absence.

## Self-review (against the spec)

Spec coverage: Block 1 power/schedule (Tasks 4-5, dead columns removed Task 11); Block 2 defence/pace/adjusted (Tasks 2, 6, 7); Block 3 player-box fetch and availability (Tasks 9-10, skew Task 12); Block 5 style-matchup FEATURES (Task 8; the signal and AI summary are the other plan); protocol (causality, parity, no-constant guards Task 11; bootstrap + calibration Task 13; decision rule Task 14); scaled linear models (Task 3, a defect found while writing this); legacy-model serving compatibility (Tasks 11-12). Types are the ones defined above and each later task consumes only what an earlier task produces.
