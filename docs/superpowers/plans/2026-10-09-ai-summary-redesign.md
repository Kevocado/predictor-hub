# AI summary redesign: Edge / Risk / Price, built on matchup duels

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the match summary on all four served sports (NFL, CFB, PL, NBA) more intuitive and more targeted: a verdict, then what favours the pick (Edge), what could undo it (Risk), and where the model sits against a quoted price (Price). Edge and Risk come from code-computed offence-versus-defence "duels" (and the sport's equivalents) stated in league ranks a fan can read.

**Architecture:** Nothing about the model's output shape changes. A factor already has `key`, `direction` (`up`/`down`/`neutral`), `headline`, `text`; the redesign (1) adds a new KEY vocabulary, `matchup:<id>`, that points at a code-computed duel in `facts.context.matchups`, (2) derives a `slot` from direction (up = Edge, down = Risk, neutral on a quoted market = Price), and (3) makes the deterministic template path (the default today) produce the same slots, so the redesign works with the LLM off. Code picks which duels matter by strength; the model, when live, only words them. The frontend plan renders the slots.

**Tech Stack:** Python 3.11 (each sport repo), the hub `services/explainer` (pydantic facts, `contract.py`, `template.py`, `prompts.py`, `validate.py`). No new dependencies.

**Spec:** `docs/superpowers/plans/2026-10-02-fixture-signals-phases-1-4.md` (signals contract; its Phase 4 "so what" step does not exist yet and this plan is its replacement for matchups), `services/explainer/explainer/contract.py` (factor contract), `2026-10-08-nba-matchup-signal-impl.md` (the NBA `matchup` signal this extends).

**Verified vs drafted:** Tasks 1 and 2 were built and run (NFL: duel module 7 tests, adapter 3 tests, passing alongside the model-plan changes). Tasks 3-10 are DRAFTED: real code and tests, not executed; run them and expect small adjustments. Task 0 is a read-only inventory that gates every sport adapter.

## Global Constraints

- Code computes the insight; the model chooses and words it. The model never supplies a number: every figure on screen comes from `facts`, and the validator's number pool stays "every number in the facts JSON".
- No betting advice words (existing prompt rule 2). Price slot appears only when a QUOTED line exists in facts. NBA has no Price slot: NBA stays independent of betting lines.
- A signal whose data is absent is dropped, never approximated. A duel closer than `min_gap` ranks is not produced. Fewer rows beats a weak row.
- A duel is labelled Edge/Risk only if it passes the residual-lift test (Task 10); otherwise it is shown as neutral context.
- Pre-kickoff only: duels use games strictly before the game; a started or finished game gets no Edge/Risk rows (the existing `markets: [] if started` behaviour stands).
- Never `git add -A`; add by name. Never push to main. Use worktrees. Tests never touch the network. Python 3.11 for NFL/CFB/PL/explainer, 3.13 for NBA.

## The design in one screen

```
VERDICT   Bills by about 4. Leaning.                        (verdict sentence, band from the model's own probability)

EDGE      Passing: Bills' #3 pass offence vs Jets' #28 pass defence.      [rank duel]
          Quarterback: Allen has started 112 games; Jets start a rookie.
RISK      Wind of 22 mph cuts the passing game both ways.                   [conditions chip]
          Jets' #4 run defence meets Bills' #19 run offence.                [rank duel]
PRICE     Model has Bills -4.0; the market quotes -6.5.                     (only when a quoted line exists)
```

Rules: at most 2 Edge, 2 Risk, 1 Price rows. Rows are ordered by duel strength, not by the model. A slot with nothing to say is omitted, never padded.

## Signal catalog (what each sport can say)

"Status" is what the code already has today. Everything marked INVENTORY must pass Task 0 before an adapter is written; if the data is not there the row is deleted from this table, not approximated.

| Sport | Signal id | Compares | Data | Status |
|---|---|---|---|---|
| NFL | `pass_off_vs_pass_def:{home,away}` | pass offence EPA/play vs opponent pass defence EPA allowed, as league ranks | play-by-play (`team_game_efficiency`) | built (Task 2) |
| NFL | `rush_off_vs_rush_def:{home,away}` | rush offence vs rush defence | same | built (Task 2) |
| NFL | `sack_rate_vs_pass_rush` | offence's sack+hit rate allowed vs defence's sack+hit rate forced | pbp `sack`, `qb_hit` | available in nflverse; not yet in PBP_AGG_COLUMNS |
| NFL | `explosive_vs_explosive_allowed` | 20+ yard play rate for vs against | pbp `yards_gained` | available in nflverse; not yet in PBP_AGG_COLUMNS |
| NFL | `red_zone_td_vs_red_zone_d` | TD rate inside the 20 for vs against | pbp `yardline_100` | available in nflverse; not yet in PBP_AGG_COLUMNS |
| NFL | `third_down_off_vs_def` | 3rd-down conversion rate for vs against | pbp `down`, `first_down` | available in nflverse; not yet in PBP_AGG_COLUMNS |
| NFL | `qb_situation` | starter experience, backup/new-QB flag, QB EPA/dropback rank | Task 5 of the model plan (`qb_games`, depth chart) | built in model plan |
| NFL | `conditions` | wind, cold, dome or rain, and how pass-heavy each side is | schedule `roof/temp/wind`; Open-Meteo forecast | built in model plan (Task 7) |
| NFL | `rest_and_travel` | short week, bye, miles/time zones travelled | schedule + stadium coords | partly built (rest) |
| NFL | `key_absences` | position-group-weighted starters Out | injuries + depth chart | built (absence signal) |
| CFB | `ppa_pass/rush_off_vs_def` | PPA per play, pass and rush, as ranks | CFBD advanced stats (model plan Task 11) | built (CFB#35) |
| CFB | `turnover_luck` | turnover margin vs what fumble-recovery luck predicts | game stats | INVENTORY |
| CFB | `qb_situation`, `conditions`, `rest_and_travel`, `key_absences` | as NFL | CFBD + Open-Meteo | INVENTORY |
| PL | `attack_vs_defence` | xG created vs conceded, as ranks | Understat xG per match | built (xG available) |
| PL | `set_pieces` | set-piece goals for vs against | match events if stored | INVENTORY |
| PL | `home_away_split` | team's home/away points per game vs league | results | built from results |
| PL | `congestion` | days since last match, midweek European fixtures | fixtures | INVENTORY |
| PL | `stakes` | title/European/relegation stakes by table position late in the season | standings | built from standings |
| PL | `btts_profile` | both teams' scoring and clean-sheet rates | results | built from results |
| NBA | `four_factors_duel` | offence vs defence on eFG%, TOV%, ORB%, FT rate, as ranks | box scores | built (four_factors.py) |
| NBA | `style matchups` | pace, offensive rebounding, turnovers, 3-point rate, free-throw rate | the NBA plan's `matchup` signal | designed and merged (NBA plan) |

Deleted from the catalog (Task 0 inventory, absent data):
- CFB `havoc_vs_havoc_allowed` — CFBD advanced stats do not include havoc rate
- CFB `line_play` — CFBD advanced stats do not include line-play splits
- CFB `explosiveness` — CFBD advanced stats do not include explosiveness
- CFB `talent_gap` — requires a separate CFBD `/teams/talent` call; not in the current pull
| NBA | `four_factors_duel` | offence vs defence on eFG%, TOV%, ORB%, FT rate, as ranks | box scores | extends NBA plan (Task 9) |
| NBA | `rest_load`, `availability` | back-to-back, minutes-weighted absences | NBA plan blocks | designed in NBA plan |

---

## Task 0: Data inventory per sport (read-only, gates Tasks 7-9)

**Files:** Create `docs/superpowers/plans/2026-10-09-signal-data-inventory.md` in predictor-hub (the output).

- [x] **Step 1:** In each of CFB_Predictor and PL_Predictor, list what the per-match / per-game data actually contains (column names, seasons covered, nulls). Method: read the loaders under `src/*/data/` and the snapshot builder; for NFL confirm pbp columns `sack`, `qb_hit`, `yards_gained`, `yardline_100`, `down`, `first_down` exist in the nflverse parquet already loaded by `load_pbp_agg`.
- [x] **Step 2:** For every row marked INVENTORY above write one line: `available (column names, coverage)` or `absent`. Absent rows are deleted from the catalog.
- [x] **Step 3:** Open a docs PR with the inventory. No code changes.

## Task 1 (verified): the duel primitive

One module, copied into each sport repo (they share no Python package; keep the file identical and say so in a header comment). It turns a stat for each team into league ranks, and produces a duel only when the rank gap is at least `min_gap` places. Strength is the percentile of the gap among past duels of that kind.

**Files:** Create `src/nfl_predictor/signals/__init__.py` (empty), `src/nfl_predictor/signals/duel.py`; Test `tests/test_duel.py`. Repeat for `cfb_predictor`, `pl_predictor`, `nba_predictor` (NBA: Python 3.13).

**Interfaces:**
- Produces: `Duel` (frozen dataclass: `id, attacker, defender, stat, foil, attacker_rank, defender_rank, n_teams, toward, strength`), `ranks(values: dict[str, float], higher_is_better=True) -> dict[str, int]`, `edge_strength(gap, history, n_teams=None) -> float` (percentile of |gap| among past gaps; with NO history it scales the gap by league size instead of returning 0, so duels still order by gap size and never tie in declaration order), `make_duel(duel_id, stat, foil, *, home, away, attacker_side, attack_ranks, defence_ranks, history_gaps, min_gap=8) -> Duel | None`.

- [ ] **Step 1: Write the tests.**

```python
import numpy as np
from nfl_predictor.signals.duel import edge_strength, make_duel, ranks


def test_ranks_best_is_one_and_ties_share():
    r = ranks({"A": 3.0, "B": 2.0, "C": 2.0, "D": 1.0})
    assert r == {"A": 1, "B": 2, "C": 2, "D": 4}


def test_lower_is_better_flips_order():
    assert ranks({"A": 3.0, "B": 1.0}, higher_is_better=False) == {"B": 1, "A": 2}


def test_strength_is_a_percentile_of_past_gaps():
    hist = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert edge_strength(5, hist) == 0.5 and edge_strength(-10, hist) == 1.0


def test_without_history_strength_scales_with_the_gap_so_duels_still_order():
    none = np.array([])
    assert edge_strength(3, none) == 0.0 and edge_strength(3, none, n_teams=32) < edge_strength(25, none, n_teams=32) <= 1.0
    assert edge_strength(31, none, n_teams=32) == 1.0


def _ranks(n=32):
    return {f"T{i}": i for i in range(1, n + 1)}


def test_good_attack_into_bad_defence_favours_the_attacker():
    d = make_duel("pass_off_vs_pass_def", "passing offence", "pass defence", home="T3", away="T28", attacker_side="home",
                  attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[5, 10, 20])
    # T3 attack rank 3 vs T28 defence rank 28: gap 25, favours home
    assert d is not None and (d.attacker_rank, d.defender_rank, d.toward) == (3, 28, "home")


def test_bad_attack_into_good_defence_favours_the_defender():
    d = make_duel("rush_off_vs_rush_def", "rushing offence", "rush defence", home="T30", away="T2", attacker_side="home",
                  attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[5, 10, 20])
    assert d is not None and d.toward == "away"


def test_close_duel_is_not_produced():
    assert make_duel("x", "a", "b", home="T10", away="T12", attacker_side="home",
                     attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[5]) is None


def test_unranked_team_gives_no_duel():
    assert make_duel("x", "a", "b", home="T1", away="ZZZ", attacker_side="home",
                     attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[5]) is None


def test_a_duel_built_without_history_carries_a_gap_based_strength():
    big = make_duel("a", "x", "y", home="T3", away="T28", attacker_side="home", attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[])
    small = make_duel("a", "x", "y", home="T10", away="T20", attacker_side="home", attack_ranks=_ranks(), defence_ranks=_ranks(), history_gaps=[])
    assert big.strength > small.strength > 0
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_duel.py` Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""Matchup duels: one team's strength against the other's weakness, in ranks a fan can read.

A duel compares an ATTACK stat of one side with the DEFENCE stat of the other. Ranks are 1 = best of `n_teams`. The
duel's strength is how unusual the rank gap is against every past duel of the same kind, so a 25-place gap in a stat
that is usually noisy does not outrank a 25-place gap in a stable one.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Duel:
    id: str            # stable key, e.g. "pass_off_vs_pass_def"
    attacker: str      # team whose strength is used
    defender: str      # team whose weakness is tested
    stat: str          # human noun, e.g. "passing offence"
    foil: str          # human noun for the other side, e.g. "pass defence"
    attacker_rank: int
    defender_rank: int
    n_teams: int
    toward: str        # "home" | "away": which side the duel favours
    strength: float    # 0..1, percentile of |gap| among past duels of this kind


def ranks(values: dict[str, float], higher_is_better: bool = True) -> dict[str, int]:
    """1 = best. Ties share the better rank so a tie never invents an ordering."""
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    out, last_v, last_r = {}, None, 0
    for i, (team, v) in enumerate(ordered, start=1):
        last_r = last_r if v == last_v else i
        last_v = v
        out[team] = last_r
    return out


def edge_strength(gap: float, history: np.ndarray, n_teams: int | None = None) -> float:
    """Percentile of |gap| among past |gaps|. With no history the gap is scaled by the league size instead, so duels
    still order by how big the gap is rather than all tying at zero and keeping declaration order."""
    history = np.abs(np.asarray(history, float))
    if history.size == 0:
        return min(1.0, abs(gap) / (n_teams - 1)) if n_teams and n_teams > 1 else 0.0
    return float((history <= abs(gap)).mean())


def make_duel(duel_id: str, stat: str, foil: str, *, home: str, away: str, attacker_side: str,
              attack_ranks: dict[str, int], defence_ranks: dict[str, int], history_gaps, min_gap: int = 8) -> Duel | None:
    """The duel of `attacker_side`'s attack against the other side's defence, or None when it is too close to call.

    A rank gap under `min_gap` places says nothing, so the duel is not produced rather than produced weak.
    """
    attacker = home if attacker_side == "home" else away
    defender = away if attacker_side == "home" else home
    a, d = attack_ranks.get(attacker), defence_ranks.get(defender)
    if a is None or d is None:
        return None
    gap = d - a  # positive: the defence ranks WORSE than the attack ranks, so the attack has the edge
    if abs(gap) < min_gap:
        return None
    toward = attacker_side if gap > 0 else ("away" if attacker_side == "home" else "home")
    return Duel(duel_id, attacker, defender, stat, foil, a, d, len(attack_ranks), toward,
                edge_strength(gap, history_gaps, len(attack_ranks)))
```

- [ ] **Step 4: Run.** Expected: 7 passed.

- [ ] **Step 5: Commit.** `git add src/nfl_predictor/signals/__init__.py src/nfl_predictor/signals/duel.py tests/test_duel.py && git commit -m "feat: matchup duel primitive (ranks, strength)"`

## Task 2 (verified): NFL offence-versus-defence duels

Four duels per game (pass and rush, each in both directions), from each team's last 8 games OF THE SAME SEASON strictly before the game, at least 3 games of data per team (so weeks 1-3 produce no duels: nothing to say beats ranking last year's roster). Output is the facts-bundle form with `toward_pick` computed in code.

**Files:** Create `src/nfl_predictor/signals/matchups.py`; Test `tests/test_matchups.py` (uses `tests/epa_fixtures.py` from the model plan Task 4, so land that first).

**Interfaces:**
- Consumes: `team_game_efficiency` output (columns `game_id, team, epa_off_pass, epa_off_rush, epa_def_pass, epa_def_rush, ...`), `duel.make_duel`.
- Produces: `matchups_for_game(home, away, games_df, efficiency, as_of, season, history_gaps=None, min_gap=8) -> list[Duel]` (strongest first); `to_context(duels, pick_side, limit=4) -> list[dict]` with keys `id, attacker, defender, stat, foil, attacker_rank, defender_rank, n_teams, toward_pick`.

- [ ] **Step 1: Write the tests.**

```python
import numpy as np
import pandas as pd
from epa_fixtures import make_games, make_pbp
from nfl_predictor.data.pbp_agg import team_game_efficiency
from nfl_predictor.signals.matchups import matchups_for_game, to_context


def _setup():
    games = make_games()
    return games, team_game_efficiency(make_pbp(games))


def test_uses_only_games_before_as_of():
    games, eff = _setup()
    last = games.iloc[-1]
    a = matchups_for_game(last["home_team"], last["away_team"], games, eff, last["gameday"], int(last["season"]), min_gap=2)
    tampered = eff.copy()
    after = tampered["game_id"].isin(games[games["gameday"] >= last["gameday"]]["game_id"])
    tampered.loc[after, ["epa_off_pass", "epa_def_pass", "epa_off_rush", "epa_def_rush"]] = 99.0
    b = matchups_for_game(last["home_team"], last["away_team"], games, tampered, last["gameday"], int(last["season"]), min_gap=2)
    assert a and [(d.id, d.attacker_rank, d.defender_rank) for d in a] == [(d.id, d.attacker_rank, d.defender_rank) for d in b]


def test_unknown_team_yields_no_duels():
    games, eff = _setup()
    assert matchups_for_game("NOPE", "T1", games, eff, pd.Timestamp("2026-01-01"), 2025) == []


def test_context_marks_direction_relative_to_the_pick():
    games, eff = _setup()
    last = games.iloc[-1]
    duels = matchups_for_game(last["home_team"], last["away_team"], games, eff, last["gameday"], int(last["season"]), min_gap=1)
    assert duels
    ctx = to_context(duels, pick_side="home")
    assert all(isinstance(r["toward_pick"], bool) for r in ctx)
    assert all(r["toward_pick"] is None for r in to_context(duels, pick_side=None))


def test_only_the_given_season_is_used():
    games, eff = _setup()
    first_week_of_last_season = games[games["season"] == 2025].iloc[0]
    # Week 1 of 2025: prior seasons exist but must not be ranked as if they were this season's form.
    assert matchups_for_game(first_week_of_last_season["home_team"], first_week_of_last_season["away_team"], games, eff,
                             first_week_of_last_season["gameday"], 2025, min_gap=1) == []
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""NFL offence-versus-defence duels for one game, from play-by-play efficiency known BEFORE the game.

Each duel is one side's attack (EPA/play, pass or rush) against the other side's matching defence, expressed as league
ranks. Only games of `season` strictly before `as_of`, and each team's last `WINDOW` of them, are used: early in a season
there are fewer than `MIN_GAMES` and the answer is no duels, which is better than ranking last year's roster.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .duel import Duel, make_duel, ranks

WINDOW = 8
MIN_GAMES = 3
#: (duel id, attack column, defence column, attack noun, defence noun). Defence columns are EPA ALLOWED: lower is better.
DUELS = [
    ("pass_off_vs_pass_def", "epa_off_pass", "epa_def_pass", "passing offence", "pass defence"),
    ("rush_off_vs_rush_def", "epa_off_rush", "epa_def_rush", "rushing offence", "run defence"),
]


def _recent_means(efficiency: pd.DataFrame, games_df: pd.DataFrame, as_of: pd.Timestamp, season: int) -> pd.DataFrame:
    meta = games_df.set_index("game_id")[["gameday", "season"]]
    eff = efficiency.assign(gameday=pd.to_datetime(efficiency["game_id"].map(meta["gameday"])),
                            season=efficiency["game_id"].map(meta["season"]))
    eff = eff[(eff["gameday"] < as_of) & (eff["season"] == season)].sort_values("gameday")
    last = eff.groupby("team").tail(WINDOW)
    counts = last.groupby("team").size()
    means = last.groupby("team").mean(numeric_only=True)
    return means[counts.reindex(means.index) >= MIN_GAMES]


def matchups_for_game(home: str, away: str, games_df: pd.DataFrame, efficiency: pd.DataFrame, as_of, season: int,
                      history_gaps: dict[str, np.ndarray] | None = None, min_gap: int = 8) -> list[Duel]:
    """Up to four duels (two kinds x two directions), strongest first. Empty when either team lacks data."""
    means = _recent_means(efficiency, games_df, pd.Timestamp(as_of), season)
    if home not in means.index or away not in means.index:
        return []
    history_gaps = history_gaps or {}
    out: list[Duel] = []
    for duel_id, atk, dfn, atk_noun, dfn_noun in DUELS:
        attack = ranks(means[atk].to_dict(), higher_is_better=True)
        defence = ranks(means[dfn].to_dict(), higher_is_better=False)
        for side in ("home", "away"):
            d = make_duel(f"{duel_id}:{side}", atk_noun, dfn_noun, home=home, away=away, attacker_side=side,
                          attack_ranks=attack, defence_ranks=defence, history_gaps=history_gaps.get(duel_id, []), min_gap=min_gap)
            if d is not None:
                out.append(d)
    return sorted(out, key=lambda d: -d.strength)


def to_context(duels: list[Duel], pick_side: str | None, limit: int = 4) -> list[dict]:
    """The facts-bundle form. `toward_pick` is true/false/None (None when there is no pick), never inferred by the model."""
    rows = []
    for d in duels[:limit]:
        rows.append({
            "id": d.id, "attacker": d.attacker, "defender": d.defender, "stat": d.stat, "foil": d.foil,
            "attacker_rank": d.attacker_rank, "defender_rank": d.defender_rank, "n_teams": d.n_teams,
            "toward_pick": None if pick_side is None else d.toward == pick_side,
        })
    return rows
```

- [ ] **Step 4: Run, then the full suite.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider` Expected: pass.

- [ ] **Step 5: Commit.** `git add src/nfl_predictor/signals/matchups.py tests/test_matchups.py && git commit -m "feat(nfl): offence-versus-defence duels from play-by-play"`

## Task 3 (NFL, DRAFTED): put duels in the facts bundle

**Why:** the explainer reads only `facts`. `context.matchups` is where duels travel; the explainer's number pool then includes the ranks automatically.

**Files:** Modify `src/nfl_predictor/api/facts.py` (the function that builds the `context` dict — find it by `grep -n "context" src/nfl_predictor/api/facts.py`), `src/nfl_predictor/api/routes.py` (pass `efficiency` and the games frame in). Test `tests/test_facts.py`.

- [ ] **Step 1: Failing test** (add to `tests/test_facts.py`; reuse the file's existing game/prediction doubles):

```python
def test_facts_carry_matchups_for_an_upcoming_game(monkeypatch):
    from nfl_predictor.api import facts as facts_mod
    duel_rows = [{"id": "pass_off_vs_pass_def:home", "attacker": "BUF", "defender": "NYJ", "stat": "passing offence",
                  "foil": "pass defence", "attacker_rank": 3, "defender_rank": 28, "n_teams": 32, "toward_pick": True}]
    monkeypatch.setattr(facts_mod, "_matchup_rows", lambda *a, **k: duel_rows)
    bundle = facts_mod.build_facts(**_upcoming_args())  # use the file's existing helper for a minimal upcoming game
    assert bundle["context"]["matchups"] == duel_rows


def test_started_game_has_no_matchups(monkeypatch):
    from nfl_predictor.api import facts as facts_mod
    monkeypatch.setattr(facts_mod, "_matchup_rows", lambda *a, **k: [{"id": "x"}])
    bundle = facts_mod.build_facts(**_started_args())
    assert "matchups" not in bundle["context"]
```

- [ ] **Step 2: Run to verify failure.** Expected: AttributeError `_matchup_rows`.
- [ ] **Step 3: Implement.** Add to `facts.py`:

```python
def _matchup_rows(home, away, games_df, efficiency, as_of, season, pick_side):
    from ..signals.matchups import load_history_gaps, matchups_for_game, to_context
    if efficiency is None or len(efficiency) == 0:
        return []
    duels = matchups_for_game(home, away, games_df, efficiency, as_of, season, history_gaps=load_history_gaps())
    return to_context(duels, pick_side)
```

and in the context builder, for an UPCOMING game only: `matchups = _matchup_rows(...)`; `if matchups: context["matchups"] = matchups`. `pick_side` is `"home"`/`"away"` from the pick, `None` when there is no pick; `season` is the game's season. Add `load_history_gaps()` to `signals/matchups.py`: it reads `data/duel_gaps.json` (`{duel_type: [past rank gaps]}`, written by the Task 10 tool from the walk-forward games) and returns `{}` when the file is absent, in which case `edge_strength` falls back to gap-scaled strength (Task 1). Test both: with the file, strength is a percentile; without it, a 25-place gap outranks a 10-place gap.
- [ ] **Step 4: Run the full suite.** Expected: pass.
- [ ] **Step 5: Commit** by name: `feat(nfl): matchup duels in the facts bundle`.

## Task 4 (hub, DRAFTED): `matchup:<id>` keys and slots in the factor contract

**Files:** Modify `services/explainer/explainer/contract.py`; Test `services/explainer/tests/test_factor_keys.py` (extend).

- [ ] **Step 1: Failing tests.**

```python
from explainer.contract import resolve_factors, slot_for

FACTS = {"markets": [{"market": "spread"}], "context": {"matchups": [{"id": "pass_off_vs_pass_def:home"}]}}


def test_a_matchup_key_that_the_facts_carry_is_kept():
    v = {"factors": [{"key": "matchup:pass_off_vs_pass_def:home", "direction": "up", "headline": "h", "text": "t"}]}
    assert [f["key"] for f in resolve_factors(v, FACTS)] == ["matchup:pass_off_vs_pass_def:home"]


def test_a_matchup_key_the_facts_do_not_carry_is_dropped():
    v = {"factors": [{"key": "matchup:invented", "direction": "up", "headline": "h", "text": "t"}]}
    assert resolve_factors(v, FACTS) == []


def _facts(toward):
    return {"markets": [{"market": "spread"}], "context": {"matchups": [{"id": "x", "toward_pick": toward}]}}


def test_slots_follow_direction_and_market():
    assert slot_for("up", "matchup:x", _facts(True)) == "edge"
    assert slot_for("down", "matchup:x", _facts(False)) == "risk"
    assert slot_for("neutral", "spread", FACTS) == "price"
    assert slot_for("neutral", "record", FACTS) == "context"


def test_the_model_cannot_promote_a_matchup_the_code_did_not_direct():
    # code says null (failed the lift gate) or the other side: whatever direction the model wrote, the row is context
    assert slot_for("up", "matchup:x", _facts(None)) == "context"
    assert slot_for("down", "matchup:x", _facts(None)) == "context"
    assert slot_for("up", "matchup:x", _facts(False)) == "context"
    assert slot_for("down", "matchup:x", _facts(True)) == "context"


def test_resolved_factors_carry_their_slot():
    v = {"factors": [{"key": "spread", "direction": "neutral", "headline": "h", "text": "t"}]}
    assert resolve_factors(v, FACTS)[0]["slot"] == "price"
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError `slot_for`.
- [ ] **Step 3: Implement.** In `contract.py`:

```python
def matchup_rows(facts) -> dict:
    rows = (as_dict(facts).get("context") or {}).get("matchups") or []
    return {f"matchup:{r['id']}": r for r in rows if isinstance(r, dict) and r.get("id")}


def slot_for(direction: str, key: str, facts) -> str:
    """edge = argues for the pick, risk = argues against, price = a statement about a quoted market, else context.

    A matchup row is directed by CODE (`toward_pick`), not by the model: it is Edge only when the code says it favours
    the pick and the model said "up", Risk only when the code says it favours the other side and the model said "down".
    Anything else (including a duel type that failed the lift gate, `toward_pick: None`) is context.
    """
    row = matchup_rows(facts).get(key)
    if row is not None:
        toward = row.get("toward_pick")
        if direction == "up" and toward is True:
            return "edge"
        if direction == "down" and toward is False:
            return "risk"
        return "context"
    if direction == "up":
        return "edge"
    if direction == "down":
        return "risk"
    return "price" if key in market_keys(facts) else "context"
```

and change `resolve_factors`:

```python
    allowed = market_keys(facts) | set(matchup_rows(facts)) | set(PSEUDO_MARKETS)
    return [{**f, "slot": slot_for(f.get("direction"), f.get("key"), facts)}
            for f in verdict.get("factors") or [] if f.get("key") in allowed]
```

- [ ] **Step 4: Run the explainer suite** (`cd services/explainer && uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider`). Expected: pass; fix any test that compares factor dicts exactly by adding `slot`.
- [ ] **Step 5: Commit.** `git add services/explainer/explainer/contract.py services/explainer/tests/test_factor_keys.py && git commit -m "feat(explainer): matchup factor keys and edge/risk/price slots"`

## Task 5 (hub, DRAFTED): the template path produces Edge and Risk

**Why:** the template path is what readers get today. Edge = the strongest duel toward the pick, Risk = the strongest duel against it. Text states only numbers that are in facts.

**Files:** Modify `services/explainer/explainer/template.py` (inside `explain_from_template`, before padding); Test `services/explainer/tests/test_template_matchups.py`.

- [ ] **Step 1: Failing test.**

```python
from explainer.template import explain_from_template

DUEL = lambda i, toward: {"id": i, "attacker": "Bills", "defender": "Jets", "stat": "passing offence", "foil": "pass defence",
                          "attacker_rank": 3, "defender_rank": 28, "n_teams": 32, "toward_pick": toward}


def _facts(matchups):
    return {"sport": "nfl", "id": "g1", "title": "Bills at Jets", "starts_at": "2026-10-11T17:00:00Z", "status": "upcoming",
            "pick_timing": "pre_kickoff", "pick": {"side": "home", "team": "Bills", "prob": 0.64},
            "markets": [{"market": "moneyline", "home_prob": 0.64}], "context": {"matchups": matchups}}


def test_edge_and_risk_rows_come_from_the_duels_toward_and_against_the_pick():
    out = explain_from_template(_facts([DUEL("a", True), DUEL("b", False)]))
    slots = [(f["slot"], f["key"]) for f in out["factors"] if f["key"].startswith("matchup:")]
    assert ("edge", "matchup:a") in slots and ("risk", "matchup:b") in slots


def test_the_row_text_states_the_ranks_from_facts():
    out = explain_from_template(_facts([DUEL("a", True)]))
    row = next(f for f in out["factors"] if f["key"] == "matchup:a")
    assert "3" in row["headline"] and "28" in row["headline"]


def test_a_duel_the_code_did_not_direct_is_a_neutral_context_row():
    out = explain_from_template(_facts([DUEL("n", None)]))
    row = next(f for f in out["factors"] if f["key"] == "matchup:n")
    assert row["direction"] == "neutral" and row["slot"] == "context"


def test_every_factor_carries_a_slot():
    out = explain_from_template(_facts([DUEL("a", True), DUEL("b", False), DUEL("n", None)]))
    assert out["factors"] and all(f.get("slot") for f in out["factors"])


def test_no_duels_means_no_matchup_rows_and_no_padding_about_them():
    out = explain_from_template(_facts([]))
    assert not [f for f in out["factors"] if f["key"].startswith("matchup:")]
```

- [ ] **Step 2: Run to verify failure.** Expected: no matchup rows.
- [ ] **Step 3: Implement.** Add a helper and call it where `explain_from_template` assembles `factors` (read the function first; keep the existing 2-4 factor cap by letting matchup rows take the first Edge and Risk positions and moving the remaining rows down):

```python
def _matchup_factors(facts: dict) -> list[dict]:
    rows = [r for r in ((facts.get("context") or {}).get("matchups") or []) if isinstance(r, dict)]
    out = []
    for toward, direction in ((True, "up"), (False, "down")):
        row = next((r for r in rows if r.get("toward_pick") is toward), None)  # rows arrive strongest first
        if row is None:
            continue
        verb = "meets" if toward else "runs into"
        headline = (f"{row['attacker']}'s #{row['attacker_rank']} {row['stat']} {verb} "
                    f"{row['defender']}'s #{row['defender_rank']} {row['foil']}")
        text = (f"{row['attacker']} rank {row['attacker_rank']} of {row['n_teams']} in {row['stat']}; "
                f"{row['defender']} rank {row['defender_rank']} of {row['n_teams']} in {row['foil']}.")
        out.append(_fact(f"matchup:{row['id']}", direction, headline, text))
    neutral = next((r for r in rows if r.get("toward_pick") is None), None)  # failed the lift gate, or a profile row
    if neutral is not None and len(out) < 2:
        out.append(_fact(f"matchup:{neutral['id']}", "neutral",
                         f"{neutral['attacker']}'s #{neutral['attacker_rank']} {neutral['stat']} and {neutral['defender']}'s #{neutral['defender_rank']} {neutral['foil']}",
                         f"{neutral['attacker']} rank {neutral['attacker_rank']} of {neutral['n_teams']} in {neutral['stat']}; "
                         f"{neutral['defender']} rank {neutral['defender_rank']} of {neutral['n_teams']} in {neutral['foil']}."))
    return out
```

Then, at the END of `explain_from_template`, after the factor list is final (including padding), stamp every factor: `for f in factors: f["slot"] = slot_for(f["direction"], f["key"], facts)` (import `slot_for` from `.contract`). `_fact` itself returns only `key, direction, headline, text`; the slot is added once, at the end, so the template and model paths agree.

For the Risk row the sentence must read from the pick's point of view: a duel with `toward_pick: False` means the OTHER side holds the edge, so its headline is the same words and the `down` direction supplies the meaning. Do not add "advantage"/"mismatch" adjectives; the ranks carry it.
- [ ] **Step 4: Run the explainer suite**, including `validate` tests (the template output must pass `validate` with the ranks in the number pool). Expected: pass.
- [ ] **Step 5: Commit.** `feat(explainer): template path emits Edge and Risk from matchup duels`.

## Task 6 (hub, DRAFTED): prompt and validator for the model path

**Files:** Modify `services/explainer/explainer/prompts.py`, `services/explainer/explainer/validate.py`; Test `services/explainer/tests/test_prompt_instructions.py` (extend), `services/explainer/tests/test_validate.py`.

- [ ] **Step 1: Failing test.**

```python
from explainer.prompts import SYSTEM


def test_prompt_teaches_matchup_keys_and_slots():
    assert "matchup:" in SYSTEM
    assert "context.matchups" in SYSTEM
    assert "Edge" in SYSTEM and "Risk" in SYSTEM


def test_prompt_still_forbids_figures_in_panel_text():
    assert "Write NO figures" in SYSTEM
```

- [ ] **Step 2: Run to verify failure.** Expected: assertion on `matchup:`.
- [ ] **Step 3: Implement.** In `SYSTEM`, after the list of market keys, add:

```
- "matchup:<id>" for any duel listed in context.matchups, using the id exactly as given. Choose at most two "up" factors (Edge: arguing for the pick) and at most two "down" factors (Risk: arguing against it) from the duels whose toward_pick is true and false respectively; prefer the duels listed first, they are strongest. Name the two units in your words ("their passing offence against that pass defence"); do not write the ranks, the panel draws them. If context.matchups is empty or missing, use market and context keys as before.
```

and raise the factor cap sentence from "2 to 4" to "2 to 5". Also raise `MAX_FACTORS` in `explainer/validate.py` from 4 to 5 (find it with `grep -n MAX_FACTORS explainer/validate.py`) and update every test that asserts the four-factor limit, adding one that a five-factor body validates and a six-factor body is rejected. The per-factor length rules are unchanged.
- [ ] **Step 4: Run the explainer suite.** Expected: pass. Then run `tools/measure_llm_trigger_fps.py` if a key is configured in a safe environment; do not print the key.
- [ ] **Step 5: Commit.** `feat(explainer): prompt teaches matchup keys, Edge and Risk`.

## Task 7 (CFB, DRAFTED): CFB duels

**Depends on:** model plan Task 11 (CFBD advanced stats committed) and Task 0.

- [ ] **Step 1:** Copy Task 1's `duel.py` and its tests into `cfb_predictor/signals/`.
- [ ] **Step 2:** `cfb_predictor/signals/matchups.py`: same shape as NFL Task 2 over the CFB `to_team_game_frame` output. Duels, in order: `pass_off_vs_pass_def`, `rush_off_vs_rush_def` (PPA), then those Task 0 marked available: `havoc` (defence havoc rate vs offence havoc allowed), `explosiveness`, `line_play`. The one CFB-specific addition: `talent_gap`, a single duel from the recruiting-talent rank of each team (attacker/defender are just the two teams; `stat="recruiting talent"`, `foil="recruiting talent"`).
- [ ] **Step 3:** Tests mirror `test_matchups.py`: causality (tamper with post-game rows, ranks unchanged), unknown team → `[]`, `toward_pick` relative to the pick.
- [ ] **Step 4:** Wire `context.matchups` into `cfb_predictor/api/facts.py` exactly as Task 3.
- [ ] **Step 5:** Full suite, commit by name.

## Task 8 (PL, DRAFTED): PL duels

**Depends on:** Task 0's decision on xG vs shots.

- [ ] **Step 1:** Copy `duel.py` and tests into `pl_predictor/signals/`.
- [ ] **Step 2:** `attack_vs_defence`: team attack (xG or shots on target created per match, last 8) against the opponent's defence (conceded, same measure), ranked among the 20 clubs. Use `min_gap=5` (20 teams, not 32). Output through the same `to_context`.
- [ ] **Step 3:** From results only (no new data): `home_away_split` (points per game at home for the home side vs away for the away side, as a rank duel across the league), `btts_profile` (a neutral context row, direction `neutral`, keyed `matchup:btts_profile`, stating each side's both-teams-scored rate from facts), `stakes` (only after matchday 30; table-position based, neutral).
- [ ] **Step 4:** Tests as Task 7; PL slots follow the same direction rule. The PL three-way result market means `toward_pick` is computed against the pick's team; for a predicted draw `pick_side` is `None` and all rows are neutral context, which the slot logic already handles (`toward_pick: None` → no Edge/Risk).
- [ ] **Step 5:** Full suite, commit by name.

## Task 9 (NBA, DRAFTED): NBA four-factors duels and the existing style signal

NBA already has the `matchup` signal (pace, rebounding, turnover, 3-point and free-throw style gaps) in its own `delta_chip` form. Add rank duels for the four factors so NBA reads like the other sports.

- [ ] **Step 1:** Copy `duel.py` and tests into `nba_predictor/signals/` (Python 3.13).
- [ ] **Step 2:** `four_factors_duel`: for each of eFG%, TOV%, ORB%, FT rate, rank every team's offence and defence (opponent value) over the last 15 games before the game; produce the strongest two duels with `min_gap=8` of 30 teams.
- [ ] **Step 3:** `context.matchups` gets these rows; the older `matchup` signal keeps its separate path (`Signal[]` endpoint). Do not show both for the same fact: if a four-factors duel and a style `matchup` signal cover the same stat (for example offensive rebounding), keep the duel and drop the signal row in the endpoint ranking. Test that.
- [ ] **Step 4:** NBA has no Price slot: in `explainer/template.py` the Price row requires a quoted line, which NBA facts never carry, so nothing changes; add a test asserting an NBA bundle never yields `slot == "price"`.
- [ ] **Step 5:** Full suite (3.13), commit by name.

## Task 10 (all sports, DRAFTED): residual-lift test, the honesty gate for Edge and Risk

**Why:** a duel can be true and still explain nothing the model has not already priced. Before a duel type is allowed to claim Edge or Risk, check that, across history, games where it favoured a side ended better for that side than the model expected.

**Files:** Create `tools/duel_lift.py` in each sport repo; Test `tests/test_duel_lift.py`.

**Interfaces:** `lift(rows) -> dict` where `rows` is a DataFrame with `toward` (+1 home, -1 away), `actual_margin`, `model_margin` (home minus away); returns `{"n", "mean_lift", "ci": (lo, hi), "passes"}`; passes when `n >= 200` and `lo > 0`.

- [ ] **Step 1: Failing test.**

```python
import numpy as np
import pandas as pd
from tools.duel_lift import lift


def _rows(effect, n=600, seed=0):
    rng = np.random.default_rng(seed)
    toward = rng.choice([-1, 1], n)
    model = rng.normal(0, 6, n)
    actual = model + effect * toward + rng.normal(0, 10, n)
    return pd.DataFrame({"toward": toward, "actual_margin": actual, "model_margin": model})


def test_a_real_effect_passes():
    assert lift(_rows(2.0))["passes"]


def test_no_effect_does_not_pass():
    assert not lift(_rows(0.0))["passes"]


def test_too_few_rows_never_pass():
    assert not lift(_rows(5.0, n=50))["passes"]
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.
- [ ] **Step 3: Implement.**

```python
"""Does a duel type tell us something the model's margin did not? Lift = (actual - model) signed toward the duel's side."""
from __future__ import annotations

import numpy as np

MIN_N = 200


def lift(rows, n_boot: int = 2000, seed: int = 0) -> dict:
    x = (rows["toward"] * (rows["actual_margin"] - rows["model_margin"])).to_numpy(float)
    n = len(x)
    if n == 0:
        return {"n": 0, "mean_lift": 0.0, "ci": (0.0, 0.0), "passes": False}
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, n), replace=True).mean(axis=1)
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    return {"n": n, "mean_lift": float(x.mean()), "ci": (lo, hi), "passes": bool(n >= MIN_N and lo > 0)}
```

- [ ] **Step 4:** A `__main__` per sport builds `rows` for each duel id over the walk-forward held-out games (duel at the time of the game; model margin from the out-of-fold prediction) and writes `data/duel_lift.json` (`{"pass_off_vs_pass_def": {...}, ...}`). Commit that file.
- [ ] **Step 5: Use it.** `to_context` consults `data/duel_lift.json`: a duel type whose entry is missing or `passes: false` is emitted with `"toward_pick": null` (shown as neutral context, never Edge or Risk). Test: a failing type yields `toward_pick is None`.
- [ ] **Step 6:** Full suite; commit by name. Report the table (duel type, n, mean lift, CI, passes) in the PR. Expect some types to fail; that is the point.

## Rollout

1. Land Tasks 1-6 for NFL (the first sport); screenshots from the frontend plan complete the loop.
2. Tasks 7-9 per sport after Task 0 and the CFBD pull. Each sport is its own PR.
3. Task 10 gates what may be called Edge/Risk per sport; until it has run, all matchup rows are neutral context (`toward_pick: null`).
4. Deploy order: sport API (adds `context.matchups`, harmless to the old explainer) then the explainer (reads it) then the frontend (renders slots). An old frontend ignores `slot` and still renders the factor list.

## Self-review

Coverage: more offence-versus-defence ideas for NFL/CFB/PL/NBA (catalog), intuitive form (ranks, Edge/Risk/Price), targeted (strength-ranked, at most 2+2+1, omitted when empty), AI is only a wording layer (Tasks 4-6), template path first (Task 5), honesty gate (Task 10), NBA independence (Task 9). Placeholders: Tasks 3-10 are drafted code with the unverified parts named; Task 0 exists precisely so no signal is written against data that is not there. Names used consistently: `Duel`, `make_duel`, `matchups_for_game`, `to_context`, `matchup_rows`, `slot_for`, `lift`.
