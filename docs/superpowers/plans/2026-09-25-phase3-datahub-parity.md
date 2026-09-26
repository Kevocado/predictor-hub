# Phase 3: NFL/CFB Data Hub parity with PL (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task.
> Also required:
> - superpowers:test-driven-development for every task;
> - superpowers:verification-before-completion before any "done";
> - superpowers:requesting-code-review at the end.
>
> For UI work, run `/impeccable` (typeset, clarify, layout and adapt; read `reference/craft-floor.md`), then `impeccable detect --json` on the changed files and one desktop (1440) and phone (390) screenshot round.
>
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** the NFL and CFB Data Hub answers "how good is this team or player?" as well as PL's does, using advanced stats (EPA, success rate, usage), form, streaks, recent games and position leaderboards.

**Architecture:**
- Each backend computes per-season team and player tables from data it already fetches: nflverse play-by-play and weekly stats for NFL; CFBD advanced season stats and player PPA for CFB.
- Each backend serves them at `/hub/teams` and `/hub/players`, and bakes them into the public snapshot, so public mode never computes live.
- The Sports site renders them with the family components, in PL's TeamHub/PlayerHub pattern.

**Tech stack:**
- **Backends:** Python 3.11, FastAPI, pandas, `nfl_data_py`, `cfbd`, pytest (run with `uv run pytest -q`).
- **Site:** React 19, Vite 8, Tailwind 4, the vendored `predictor-ui`, and Vitest (`npx vitest run`, `npx tsc -b`).

**Spec:** [../specs/2026-09-25-phase3-4-datahub-explainer-design.md](../specs/2026-09-25-phase3-4-datahub-explainer-design.md), sub-project A.

**Repos and branch:** `Kevocado/NFL_Predictor`, `Kevocado/CFB_Predictor` and `Kevocado/Sports_Predictor`. Work on the branch `claude/sports-predictors-frontend-plan-qpab3v` in each repo, which already exists and has open PRs. Push to that branch and never to `main`. Add to each repo's PR #1 body.

## Global constraints

- **Public mode:** it never triggers live data work on a request. It serves `snapshot["hub_teams"]` and `snapshot["hub_players"]`, and falls back to a live compute only when the key is missing, the same as the existing `/standings` pattern.
- **Network in tests:** tests never touch the network. Build DataFrames by hand, with the columns listed in each task.
- **CFBD quota:** at most one advanced-stats call and one player-PPA call per season per day, cached on disk under `config.CACHE_DIR / "cfbd_advanced"`.
- **Numbers on screen:**
  - EPA: 2 decimals, signed, with a true minus (U+2212);
  - rates and shares: whole %;
  - missing values: "—", never 0.
- **Type:** no text under 12 px, and no new fonts.
- **Colour:** status colour always comes with words (the trend reads "Improving form ↑").
- **Copy:** plain English. "EPA per play" gets a one-line tooltip: "Expected points added per play: how much each play changed the expected score. Above 0 is better than average."

## Review focus

1. **Week 1:** a team with 0 games gets a row with dashes and form "new". It is never divided by zero.
2. **Players who switch teams mid-season:** they are shown under the team of their latest week.
3. **CFB with the CFBD key unset or quota exhausted:** the hub still renders (without EPA columns) and says so ("Advanced stats unavailable right now").
4. **Sorting by a column with missing values:** missing values sort last in both directions.
5. **At 390 px:** tables scroll inside their own box, and the page never scrolls sideways.

Each has a test in the task that owns it.

---

### Task 1: NFL team efficiency table (backend)

**Files:**
- Create: `NFL_Predictor/src/nfl_predictor/data/team_efficiency.py`
- Test: `NFL_Predictor/tests/test_team_efficiency.py`

**Interfaces:**
- Produces: `team_efficiency(pbp: pd.DataFrame, games: pd.DataFrame, season: int) -> list[dict]`. Each dict has exactly these keys:
  - `team`
  - `games`
  - `wins`, `losses`, `ties`
  - `points_for_pg`, `points_against_pg`
  - `off_epa_play`, `def_epa_play`
  - `off_success_rate`, `def_success_rate`
  - `yards_per_play`
  - `pass_rate`
  - `turnover_margin`
  - `streak` (int: +3 is W3, −2 is L2)
  - `form` (list of `"W"`/`"L"`/`"T"`, oldest first, up to 5)
  - `form_trend` (`"up"`, `"down"`, `"steady"` or `"new"`)
  - `recent_games` (a list of `{gameday, opponent, is_home, team_score, opponent_score, result}`, newest first, up to 5)
- Produces: `load_pbp(season: int) -> pd.DataFrame`, which wraps `nfl_data_py.import_pbp_data([season], columns=PBP_COLUMNS)` with a per-season parquet cache under `config.CACHE_DIR / "pbp"`.
- `PBP_COLUMNS = ["game_id","posteam","defteam","epa","success","yards_gained","pass","rush","play_type","interception","fumble_lost","week","season_type"]`.
- Only regular and post-season plays where `play_type` is in `{"pass","run"}` count.

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd
from nfl_predictor.data.team_efficiency import team_efficiency

def _pbp():
    rows = []
    # KC offense: 4 plays, EPA 0.5,0.5,-0.2,0.2 → 0.25/play, success 3/4
    for epa in (0.5, 0.5, -0.2, 0.2):
        rows.append(dict(game_id="g1", posteam="KC", defteam="BAL", epa=epa, success=int(epa > 0),
                         yards_gained=5, **{"pass": 1, "rush": 0}, play_type="pass",
                         interception=0, fumble_lost=0, week=1, season_type="REG"))
    # BAL offense: 2 plays, EPA -0.4, 0.0 → -0.2/play
    for epa in (-0.4, 0.0):
        rows.append(dict(game_id="g1", posteam="BAL", defteam="KC", epa=epa, success=int(epa > 0),
                         yards_gained=2, **{"pass": 0, "rush": 1}, play_type="run",
                         interception=1 if epa < 0 else 0, fumble_lost=0, week=1, season_type="REG"))
    return pd.DataFrame(rows)

def _games():
    return pd.DataFrame([dict(game_id="g1", season=2026, week=1, gameday="2026-09-10",
                              home_team="KC", away_team="BAL", home_score=27, away_score=20)])

def test_offense_and_defense_epa_per_play():
    rows = {r["team"]: r for r in team_efficiency(_pbp(), _games(), 2026)}
    assert rows["KC"]["off_epa_play"] == 0.25
    assert rows["KC"]["def_epa_play"] == -0.2
    assert rows["KC"]["off_success_rate"] == 0.75
    assert rows["BAL"]["turnover_margin"] == -1 and rows["KC"]["turnover_margin"] == 1

def test_record_form_streak_and_recent_games():
    kc = next(r for r in team_efficiency(_pbp(), _games(), 2026) if r["team"] == "KC")
    assert (kc["wins"], kc["losses"], kc["games"]) == (1, 0, 1)
    assert kc["streak"] == 1 and kc["form"] == ["W"] and kc["form_trend"] == "new"
    assert kc["recent_games"][0] == {"gameday": "2026-09-10", "opponent": "BAL", "is_home": True,
                                     "team_score": 27, "opponent_score": 20, "result": "W"}
    assert kc["points_for_pg"] == 27.0

def test_team_with_no_games_gets_dashes_not_zero_division():
    games = pd.concat([_games(), pd.DataFrame([dict(game_id="g2", season=2026, week=2, gameday="2026-09-17",
                        home_team="NYJ", away_team="MIA", home_score=None, away_score=None)])])
    nyj = next(r for r in team_efficiency(_pbp(), games, 2026) if r["team"] == "NYJ")
    assert nyj["games"] == 0 and nyj["off_epa_play"] is None and nyj["points_for_pg"] is None
    assert nyj["form_trend"] == "new"

def test_form_trend_up_when_last_three_beat_season_average_by_more_than_three():
    games = pd.DataFrame([
        dict(game_id=f"g{i}", season=2026, week=i, gameday=f"2026-09-{10+i:02d}", home_team="KC",
             away_team="BAL", home_score=s, away_score=10) for i, s in enumerate([10, 10, 10, 30, 30, 30], start=1)
    ])
    kc = next(r for r in team_efficiency(pd.DataFrame(columns=_pbp().columns), games, 2026) if r["team"] == "KC")
    assert kc["form_trend"] == "up" and kc["streak"] == 3
```

- [ ] **Step 2: Run the tests and confirm they fail.** Run `uv run pytest -q tests/test_team_efficiency.py`. Expected: `ModuleNotFoundError: nfl_predictor.data.team_efficiency`.

- [ ] **Step 3: Implement.**

```python
"""Per-team season efficiency from nflverse play-by-play (the NFL's
equivalent of PL's xG), plus record, form and recent games from the
schedule. Missing values are None, never 0: the site shows a dash."""
from __future__ import annotations

import pandas as pd

from ..config import CACHE_DIR

PBP_COLUMNS = ["game_id", "posteam", "defteam", "epa", "success", "yards_gained", "pass", "rush",
               "play_type", "interception", "fumble_lost", "week", "season_type"]


def load_pbp(season: int) -> pd.DataFrame:
    path = CACHE_DIR / "pbp" / f"pbp_{season}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    import nfl_data_py as nfl

    df = nfl.import_pbp_data([season], columns=PBP_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None or pd.isna(x) else round(float(x), nd)


def _results(team: str, played: pd.DataFrame) -> list[dict]:
    out = []
    for _, g in played.sort_values("gameday").iterrows():
        home = g["home_team"] == team
        ts, os_ = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
        out.append({"gameday": str(g["gameday"])[:10], "opponent": g["away_team"] if home else g["home_team"],
                    "is_home": bool(home), "team_score": int(ts), "opponent_score": int(os_),
                    "result": "W" if ts > os_ else "L" if ts < os_ else "T"})
    return out


def _streak(results: list[dict]) -> int:
    if not results:
        return 0
    last = results[-1]["result"]
    n = 0
    for r in reversed(results):
        if r["result"] != last:
            break
        n += 1
    return n if last == "W" else -n if last == "L" else 0


def _trend(results: list[dict]) -> str:
    if len(results) < 3:
        return "new"
    nets = [r["team_score"] - r["opponent_score"] for r in results]
    diff = sum(nets[-3:]) / 3 - sum(nets) / len(nets)
    return "up" if diff > 3 else "down" if diff < -3 else "steady"


def team_efficiency(pbp: pd.DataFrame, games: pd.DataFrame, season: int) -> list[dict]:
    plays = pbp[pbp["play_type"].isin(["pass", "run"])] if not pbp.empty else pbp
    season_games = games[games["season"] == season]
    teams = sorted(set(season_games["home_team"]) | set(season_games["away_team"]))
    played = season_games[season_games["home_score"].notna() & season_games["away_score"].notna()]
    rows = []
    for team in teams:
        mine = played[(played["home_team"] == team) | (played["away_team"] == team)]
        results = _results(team, mine)
        n = len(results)
        off = plays[plays["posteam"] == team] if not plays.empty else plays
        dfn = plays[plays["defteam"] == team] if not plays.empty else plays
        give = int(off["interception"].sum() + off["fumble_lost"].sum()) if len(off) else 0
        take = int(dfn["interception"].sum() + dfn["fumble_lost"].sum()) if len(dfn) else 0
        rows.append({
            "team": team, "games": n,
            "wins": sum(r["result"] == "W" for r in results),
            "losses": sum(r["result"] == "L" for r in results),
            "ties": sum(r["result"] == "T" for r in results),
            "points_for_pg": _r(sum(r["team_score"] for r in results) / n, 1) if n else None,
            "points_against_pg": _r(sum(r["opponent_score"] for r in results) / n, 1) if n else None,
            "off_epa_play": _r(off["epa"].mean()) if len(off) else None,
            "def_epa_play": _r(dfn["epa"].mean()) if len(dfn) else None,
            "off_success_rate": _r(off["success"].mean()) if len(off) else None,
            "def_success_rate": _r(dfn["success"].mean()) if len(dfn) else None,
            "yards_per_play": _r(off["yards_gained"].mean(), 2) if len(off) else None,
            "pass_rate": _r(off["pass"].mean()) if len(off) else None,
            "turnover_margin": (take - give) if (len(off) or len(dfn)) else None,
            "streak": _streak(results),
            "form": [r["result"] for r in results[-5:]],
            "form_trend": _trend(results),
            "recent_games": list(reversed(results[-5:])),
        })
    return rows
```

- [ ] **Step 4: Run the tests and confirm they pass.** Run `uv run pytest -q tests/test_team_efficiency.py`. Expected: 4 passed. Then run `uv run pytest -q`: everything passes.
- [ ] **Step 5: Commit** with `git commit -m "feat: NFL team efficiency (EPA, success rate, form) for the Data Hub"`.

### Task 2: NFL player season table (backend)

**Files:**
- Create: `NFL_Predictor/src/nfl_predictor/data/player_season.py`
- Test: `NFL_Predictor/tests/test_player_season.py`

**Interfaces:**
- Consumes: the weekly player DataFrame from `player_stats.fetch_weekly_player_stats([season])`. Its columns include:
  - identity: `player_id`, `player_display_name`, `position`, `recent_team`, `season`, `week`;
  - passing: `completions`, `attempts`, `passing_yards`, `passing_tds`, `interceptions`, `passing_epa`;
  - rushing: `carries`, `rushing_yards`, `rushing_tds`, `rushing_epa`;
  - receiving: `receptions`, `targets`, `receiving_yards`, `receiving_tds`, `receiving_epa`;
  - usage and fantasy: `target_share`, `air_yards_share`, `fantasy_points_ppr`.
- Produces: `player_season(weekly: pd.DataFrame, season: int) -> dict` with keys:
  - `players`: a list with one dict per player. Each has `player_id`, `name`, `team` (the latest week's team), `position`, `games` and all the summed stats above, plus these averages (None when absent):
    - `epa_total` (the sum of the three EPA columns, treating NaN as 0 only when at least one is present);
    - `target_share`;
    - `air_yards_share`;
    - `fantasy_ppr_pg`.
  - `leaderboards`: `{"QB": [...top 5 by epa_total], "RB": [...], "WR": [...], "TE": [...]}`.
- Positions kept: QB, RB, WR and TE.

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd
from nfl_predictor.data.player_season import player_season

def _w(pid, name, pos, team, week, **stats):
    base = dict(player_id=pid, player_display_name=name, position=pos, recent_team=team, season=2026, week=week,
                completions=0, attempts=0, passing_yards=0, passing_tds=0, interceptions=0, passing_epa=None,
                carries=0, rushing_yards=0, rushing_tds=0, rushing_epa=None, receptions=0, targets=0,
                receiving_yards=0, receiving_tds=0, receiving_epa=None, target_share=None, air_yards_share=None,
                fantasy_points_ppr=0.0)
    base.update(stats)
    return base

def test_sums_stats_uses_latest_team_and_ranks_leaderboards():
    weekly = pd.DataFrame([
        _w("q1", "Pat QB", "QB", "KC", 1, passing_yards=300, passing_tds=3, passing_epa=10.0, fantasy_points_ppr=25),
        _w("q1", "Pat QB", "QB", "KC", 2, passing_yards=200, passing_tds=1, passing_epa=-2.0, fantasy_points_ppr=15),
        _w("w1", "Tyreek WR", "WR", "MIA", 1, receiving_yards=100, targets=10, receiving_epa=5.0, target_share=0.3),
        _w("w1", "Tyreek WR", "WR", "BUF", 2, receiving_yards=50, targets=6, receiving_epa=1.0, target_share=0.2),
        _w("k1", "Kicker", "K", "KC", 1),
    ])
    out = player_season(weekly, 2026)
    by_id = {p["player_id"]: p for p in out["players"]}
    assert "k1" not in by_id
    assert by_id["q1"]["passing_yards"] == 500 and by_id["q1"]["games"] == 2 and by_id["q1"]["epa_total"] == 8.0
    assert by_id["q1"]["fantasy_ppr_pg"] == 20.0
    assert by_id["w1"]["team"] == "BUF" and by_id["w1"]["target_share"] == 0.25
    assert out["leaderboards"]["QB"][0]["player_id"] == "q1"

def test_player_without_any_epa_gets_none_not_zero():
    out = player_season(pd.DataFrame([_w("r1", "Back", "RB", "NYJ", 1, carries=10, rushing_yards=40)]), 2026)
    assert out["players"][0]["epa_total"] is None
```

- [ ] **Step 2: Run the tests and confirm they fail.** Run `uv run pytest -q tests/test_player_season.py`. Expected: a module-not-found error.

- [ ] **Step 3: Implement.**

```python
"""Per-player season table and position leaderboards from nflverse weekly
stats. EPA is the headline efficiency number; missing values stay None."""
from __future__ import annotations

import pandas as pd

POSITIONS = ["QB", "RB", "WR", "TE"]
SUM_COLS = ["completions", "attempts", "passing_yards", "passing_tds", "interceptions", "carries",
            "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds"]
EPA_COLS = ["passing_epa", "rushing_epa", "receiving_epa"]


def _mean(s: pd.Series) -> float | None:
    s = s.dropna()
    return None if s.empty else round(float(s.mean()), 3)


def player_season(weekly: pd.DataFrame, season: int) -> dict:
    df = weekly[(weekly["season"] == season) & weekly["position"].isin(POSITIONS)].sort_values("week")
    players = []
    for pid, g in df.groupby("player_id"):
        last = g.iloc[-1]
        epa_present = g[EPA_COLS].notna().any().any()
        row = {"player_id": pid, "name": last["player_display_name"], "team": last["recent_team"],
               "position": last["position"], "games": int(g["week"].nunique())}
        row.update({c: int(g[c].fillna(0).sum()) for c in SUM_COLS})
        row["epa_total"] = round(float(g[EPA_COLS].fillna(0).to_numpy().sum()), 2) if epa_present else None
        row["target_share"] = _mean(g["target_share"])
        row["air_yards_share"] = _mean(g["air_yards_share"])
        row["fantasy_ppr_pg"] = round(float(g["fantasy_points_ppr"].fillna(0).sum()) / row["games"], 1)
        players.append(row)
    boards = {}
    for pos in POSITIONS:
        ranked = [p for p in players if p["position"] == pos and p["epa_total"] is not None]
        boards[pos] = sorted(ranked, key=lambda p: p["epa_total"], reverse=True)[:5]
    return {"players": players, "leaderboards": boards}
```

- [ ] **Step 4: Run the tests and confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit** with `git commit -m "feat: NFL player season stats and position leaderboards"`.

### Task 3: NFL `/hub/teams` and `/hub/players` endpoints, and the snapshot

**Files:**
- Modify: `NFL_Predictor/src/nfl_predictor/api/routes.py` (add after `get_power_rankings`)
- Modify: `NFL_Predictor/src/nfl_predictor/public_snapshot.py` (in `build_snapshot`, the returned dict)
- Test: `NFL_Predictor/tests/test_hub_routes.py`

**Interfaces:**
- Consumes: Task 1's `team_efficiency` and `load_pbp`; Task 2's `player_season`; the existing `_load_game_history`, `player_stats.fetch_weekly_player_stats` and `_public_snapshot`.
- Produces:
  - `GET /hub/teams?season=` returns `{"season": int, "teams": list[dict]}`;
  - `GET /hub/players?season=` returns `{"season": int, "players": [...], "leaderboards": {...}}`;
  - snapshot keys `hub_teams` and `hub_players`, in the same shapes.

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient
from nfl_predictor.api import routes
from nfl_predictor.api.main import app

def test_public_mode_serves_hub_from_snapshot_without_live_work(monkeypatch):
    snap = {"season": 2026, "hub_teams": {"season": 2026, "teams": [{"team": "KC"}]},
            "hub_players": {"season": 2026, "players": [], "leaderboards": {}}}
    monkeypatch.setattr(routes, "PUBLIC_MODE", True)
    monkeypatch.setattr(routes, "_public_snapshot", lambda: snap)
    monkeypatch.setattr(routes, "_get_hub_teams_live", lambda season: (_ for _ in ()).throw(AssertionError("live")))
    c = TestClient(app)
    assert c.get("/api/hub/teams?season=2026").json()["teams"] == [{"team": "KC"}]
    assert c.get("/api/hub/players?season=2026").json()["leaderboards"] == {}

def test_live_path_combines_pbp_and_schedule(monkeypatch):
    import pandas as pd
    monkeypatch.setattr(routes, "PUBLIC_MODE", False)
    monkeypatch.setattr(routes, "_load_game_history", lambda s: pd.DataFrame([dict(game_id="g1", season=2026, week=1,
        gameday="2026-09-10", home_team="KC", away_team="BAL", home_score=27, away_score=20)]))
    monkeypatch.setattr(routes.team_efficiency_mod, "load_pbp", lambda s: pd.DataFrame(columns=routes.team_efficiency_mod.PBP_COLUMNS))
    body = TestClient(app).get("/api/hub/teams?season=2026").json()
    assert {t["team"] for t in body["teams"]} == {"KC", "BAL"}
```

Check the prefix first: `main.py` mounts the router at `/api`. If it is mounted at the root, drop `/api` from the URLs.

- [ ] **Step 2: Run the tests and confirm they fail.** Run `uv run pytest -q tests/test_hub_routes.py`.

- [ ] **Step 3: Implement.** In `routes.py`, import:

```python
from ..data import team_efficiency as team_efficiency_mod
from ..data.player_season import player_season
```

Then add:

```python
@router.get("/hub/teams")
def get_hub_teams(season: int = CURRENT_SEASON):
    if PUBLIC_MODE:
        snap = _public_snapshot()
        if snap.get("season") == season and "hub_teams" in snap:
            return snap["hub_teams"]
    return _get_hub_teams_live(season)


def _get_hub_teams_live(season: int) -> dict:
    games = _load_game_history(season)
    pbp = team_efficiency_mod.load_pbp(season)
    return {"season": season, "teams": team_efficiency_mod.team_efficiency(pbp, games, season)}


@router.get("/hub/players")
def get_hub_players(season: int = CURRENT_SEASON):
    if PUBLIC_MODE:
        snap = _public_snapshot()
        if snap.get("season") == season and "hub_players" in snap:
            return snap["hub_players"]
    weekly = player_stats.fetch_weekly_player_stats([season])
    return {"season": season, **player_season(weekly, season)}
```

In `public_snapshot.build_snapshot`, beside `power_rankings`, do the following. Each call gets its own try/except, following the existing pattern:
- compute `hub_teams = routes._get_hub_teams_live(season)`, falling back to `previous.get("hub_teams", {})` on failure;
- compute `hub_players = routes.get_hub_players(season)` with PUBLIC_MODE off, the same way;
- add both keys to the returned dict.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit and push** with `git commit -m "feat: NFL Data Hub endpoints, baked into the public snapshot" && git push`.

### Task 4: CFB team and player hub (backend)

**Files:**
- Create: `CFB_Predictor/src/cfb_predictor/data/advanced_stats.py`
- Modify: `CFB_Predictor/src/cfb_predictor/api/routes.py` and `CFB_Predictor/src/cfb_predictor/public_snapshot.py`
- Test: `CFB_Predictor/tests/test_advanced_stats.py`

**Interfaces:**
- **`fetch_advanced(season) -> list[dict]`** calls `cfbd.StatsApi(api_client).get_advanced_season_stats(year=season, exclude_garbage_time=True)` using the existing `_cfbd_configuration()` from `data/games.py`.
  - It returns plain dicts with `team`, `off_ppa`, `def_ppa`, `off_success_rate`, `def_success_rate`, `off_explosiveness` and `def_explosiveness`, mapped from `offense.ppa`, `defense.ppa`, `offense.success_rate`, `defense.success_rate`, `offense.explosiveness` and `defense.explosiveness`.
  - Results are cached at `CACHE_DIR/"cfbd_advanced"/f"{season}.json"`, stamped with `fetched_at`, and refetched only when older than 24 h.
- **`fetch_player_ppa(season) -> list[dict]`** calls `get_player_season_ppa(year=season)` (on `cfbd.MetricsApi`) with the same cache rule. It returns `{player_id, name, team, position, ppa_total}` (from `total_ppa.all`).
- **`team_hub(advanced, games, season) -> list[dict]`** has the same keys as NFL Task 1. The EPA fields are filled from PPA: `off_epa_play` = `off_ppa`, `def_epa_play` = `def_ppa`, and likewise for the success rates. `yards_per_play`, `pass_rate` and `turnover_margin` are None. Record, form, streak, trend and recent games are computed exactly as NFL does. Copy `_results`, `_streak` and `_trend` into this module, because each repo is self-contained.
- **Unavailability:** when `CFBD_API_KEY` is unset or the call raises, `fetch_advanced` returns `[]` and the hub response carries `"advanced_available": false`.

- [ ] **Step 1: Write the failing tests** (the CFBD client is mocked, with no network).

```python
import pandas as pd
from cfb_predictor.data import advanced_stats as adv

def test_team_hub_maps_ppa_to_epa_fields_and_keeps_form():
    advanced = [dict(team="Georgia", off_ppa=0.31, def_ppa=-0.12, off_success_rate=0.48, def_success_rate=0.36,
                     off_explosiveness=1.2, def_explosiveness=1.1)]
    games = pd.DataFrame([dict(game_id=1, season=2026, week=1, gameday="2026-08-30", home_team="Georgia",
                               away_team="Clemson", home_score=34, away_score=3)])
    uga = next(r for r in adv.team_hub(advanced, games, 2026) if r["team"] == "Georgia")
    assert uga["off_epa_play"] == 0.31 and uga["def_epa_play"] == -0.12 and uga["turnover_margin"] is None
    assert uga["form"] == ["W"] and uga["streak"] == 1

def test_missing_key_means_no_advanced_and_no_call(monkeypatch, tmp_path):
    monkeypatch.setattr(adv, "CFBD_API_KEY", None)
    monkeypatch.setattr(adv, "CACHE_DIR", tmp_path)
    assert adv.fetch_advanced(2026) == []

def test_cache_is_reused_within_a_day(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(adv, "CFBD_API_KEY", "k")
    monkeypatch.setattr(adv, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(adv, "_call_advanced", lambda season: calls.append(season) or [dict(team="Georgia", off_ppa=0.3,
        def_ppa=-0.1, off_success_rate=0.5, def_success_rate=0.4, off_explosiveness=1.0, def_explosiveness=1.0)])
    adv.fetch_advanced(2026); adv.fetch_advanced(2026)
    assert calls == [2026]
```

- [ ] **Step 2: Run the tests and confirm they fail.**

- [ ] **Step 3: Implement.**
  - **`advanced_stats.py`:** `_call_advanced(season)` does the CFBD call and mapping above. `fetch_advanced` wraps it with the key check and the 24 h JSON cache. `fetch_player_ppa` follows the same pattern. `team_hub` works as described.
  - **Routes:** add `/hub/teams` and `/hub/players` to `routes.py` in the same shape as NFL Task 3.
    - `/hub/teams` returns `{"season", "teams", "advanced_available": bool(advanced)}`.
    - `/hub/players` builds the player table from the site's existing weekly player stats, keeping the positions CFB carries (QB, RB, WR, TE). It sets `epa_total` from `fetch_player_ppa` by player name and team; unmatched players get None.
  - **Snapshot:** add `hub_teams` and `hub_players` to the CFB snapshot, each with the same try/except fallback as NFL.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit and push** with `git commit -m "feat: CFB Data Hub from CFBD advanced stats (cached, quota-safe)" && git push`.

### Task 5: `StatTable` in `predictor-ui` (the shared package)

**Files:**
- Create: `predictor-hub/packages/predictor-ui/src/components/StatTable.tsx`
- Test: `predictor-hub/packages/predictor-ui/src/components/table.test.tsx`
- Modify: `predictor-hub/packages/predictor-ui/src/index.ts` (export it)
- Then resync into `Sports_Predictor` (`node ../predictor-hub/scripts/sync-ui.mjs src`)

**Interfaces:**

```ts
export type Column<T> = {
  key: string;
  label: string;
  value: (row: T) => number | string | null; // null = missing: renders "—", sorts last both ways
  render?: (row: T) => ReactNode;           // defaults to the value, formatted
  numeric?: boolean;
  tooltip?: string;                          // rendered as the header's title and an sr-only description
};
export function StatTable<T>(props: {
  rows: T[]; columns: Column<T>[]; rowKey: (row: T) => string;
  initialSort?: { key: string; dir: "asc" | "desc" };
  caption: string;                            // visually hidden table caption
  expand?: (row: T) => ReactNode;             // optional detail row, toggled by a button in the first cell
}): JSX.Element
```

- [ ] **Step 1: Write the failing tests**

```tsx
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { StatTable, type Column } from "./StatTable";

type R = { team: string; epa: number | null };
const rows: R[] = [{ team: "KC", epa: 0.12 }, { team: "BAL", epa: null }, { team: "MIA", epa: -0.05 }];
const cols: Column<R>[] = [
  { key: "team", label: "Team", value: (r) => r.team },
  { key: "epa", label: "Off EPA/play", value: (r) => r.epa, numeric: true, tooltip: "Expected points added per play" },
];

describe("StatTable", () => {
  it("sorts by a header, missing values last in both directions, and says the sort", () => {
    render(<StatTable rows={rows} columns={cols} rowKey={(r) => r.team} caption="Teams" />);
    const sortBtn = screen.getByRole("button", { name: /Off EPA\/play/ });
    fireEvent.click(sortBtn);
    const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
    expect(names()).toEqual(["KC", "MIA", "BAL"]);
    expect(screen.getByRole("columnheader", { name: /Off EPA\/play/ })).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(sortBtn);
    expect(names()).toEqual(["MIA", "KC", "BAL"]);
    expect(screen.getAllByText("—").length).toBe(1);
  });
  it("expands a row's detail with a labelled toggle", () => {
    render(<StatTable rows={rows} columns={cols} rowKey={(r) => r.team} caption="Teams" expand={(r) => <p>Detail {r.team}</p>} />);
    fireEvent.click(screen.getByRole("button", { name: "Show KC details" }));
    expect(screen.getByText("Detail KC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide KC details" })).toHaveAttribute("aria-expanded", "true");
  });
});
```

- [ ] **Step 2: Run the tests and confirm they fail.** Run `cd predictor-hub/packages/predictor-ui && npx vitest run src/components/table.test.tsx`.
- [ ] **Step 3: Implement `StatTable`.**
  - The table sits in `<div className="overflow-x-auto">`. Tables never scroll the page.
  - Headers are `<th aria-sort>` containing a `<button>`. The default sort direction is desc for numeric columns, asc otherwise.
  - Missing values go last in both directions.
  - Numeric cells get `text-right tabular-nums`.
  - Text is 12 px minimum, using the family `pr-*` tokens.
  - The first cell holds the expand toggle, labelled "Show {first-column value} details" or "Hide … details".
  - Add `export { StatTable, type Column } from "./components/StatTable";` to `index.ts`.
- [ ] **Step 4: Run the tests and confirm they pass.** Run `npx vitest run && npx tsc --noEmit -p .`. Then resync into Sports and run its tests, as the next task needs it.
- [ ] **Step 5: Commit** in both repos:
  - predictor-hub: `feat(predictor-ui): StatTable (sortable, missing-last, expandable)`
  - Sports: `chore: resync predictor-ui (StatTable)`

### Task 6: Sports site Teams and Players pages on the new hub data

**Files:**
- Modify: `Sports_Predictor/src/types.ts` (add `HubTeam`, `HubTeamsResponse`, `HubPlayer` and `HubPlayersResponse`, mirroring Tasks 1–4 exactly)
- Modify: `Sports_Predictor/src/api/client.ts` (add `hubTeams(season)` and `hubPlayers(season)` to both the NFL and CFB `SportApi`)
- Replace: `Sports_Predictor/src/pages/TeamHubPage.tsx`, and `PlayersPage.tsx` as the Players tab
- Modify: `Sports_Predictor/src/pages/HubPage.tsx` (tab labels become Teams, Players, Standings and Track record)
- Tests: `TeamHubPage.test.tsx`, `PlayersPage.test.tsx` (update them) and `lib/hubFormat.test.ts` (new)

**Interfaces:**
- Consumes: `StatTable` and `Column` (Task 5); `signed`, `pct` and `streak` from `predictor-ui`.
- Produces:
  - `lib/hubFormat.ts` exports `epa(x: number | null): string`. It returns 2 decimals via a true minus, or "—".
  - It also exports `share(x: number | null): string`, which returns a whole % or "—".

- [ ] **Step 1: Write the failing tests.**
  - **`hubFormat.test.ts`:** `epa(-0.123)` is `"−0.12"`; `epa(0.1)` is `"+0.10"`; `epa(null)` is `"—"`; `share(0.253)` is `"25%"`.
  - **`TeamHubPage.test.tsx`** mocks `api.hubTeams` with two teams, one with `games: 0`, and checks:
    - the headers are "Team", "Record", "Off EPA/play", "Def EPA/play", "Success rate", "Pts for/g", "Pts against/g", "Turnovers ±" and "Form";
    - the 0-game team shows dashes and "New this season";
    - expanding a team lists its recent games ("W 27–20 v BAL");
    - with `advanced_available: false` the page reads "Advanced stats unavailable right now" and hides the EPA columns.
  - **`PlayersPage.test.tsx`** mocks `api.hubPlayers` and `api.playerProps` and checks:
    - the "QB" filter shows only QBs, with columns "Pass yds", "Pass TD", "INT" and "EPA";
    - the "WR" filter shows "Targets", "Target share", "Rec yds", "Rec TD" and "EPA";
    - the leaderboard lists the top 5 by EPA;
    - "Projected this week" shows the prop value when one exists, and "—" otherwise;
    - search narrows by name.
- [ ] **Step 2: Run the tests and confirm they fail.** Run `npx vitest run`.
- [ ] **Step 3: Implement.**
  - Build both pages on `StatTable`.
  - The form cell uses the existing `FormStrip` plus a trend word.
  - Show the EPA tooltip on the header.
  - Keep the Phase 1 and 2 states: `Skeleton`, `ErrorState` with Try again, `EmptyState`.
- [ ] **Step 4: Verify.**
  - Run `npx vitest run && npx tsc -b && npx oxlint src`.
  - Run `impeccable detect --json src/pages`.
  - Build, preview against the local NFL and CFB APIs, and take screenshots of the Teams and Players pages at 1440 and 390. There must be no page-level horizontal scroll.
- [ ] **Step 5: Commit and push** with `git commit -m "feat: Data Hub Teams and Players at PL depth (EPA, form, leaderboards)"`. Add a section to each repo's PR #1 body.

## Self-review

- **Spec coverage:**
  - NFL teams: Task 1. NFL players: Task 2. Endpoints and snapshot: Task 3.
  - CFB, including quota and unavailability: Task 4.
  - Shared table: Task 5. UI: Task 6.
  - NBA gaps are out of scope, as the spec says.
- **Review focus:** each line has a test.
  - Week 1 (0 games): Task 1 test 3 and Task 6.
  - Players who switch teams: Task 2 test 1.
  - CFB unavailable: Tasks 4 and 6.
  - Missing values sort last: Task 5.
  - 390 px: the Task 6 screenshots.
