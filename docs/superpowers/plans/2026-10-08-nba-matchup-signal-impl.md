# NBA matchup signal: implementation plan (hub component, NBA adapter, AI facts)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show "how these two teams play" on the NBA fixture page as a `matchup` signal, and let the AI summary quote it, without adding any number the page does not already show.

**Architecture:** `matchup` is a fifth `Signal` kind drawn by the EXISTING `delta_chip` (its figure is a signed gap in the sport's own units), so the shared component needs a type change and tests, not a new visual. An NBA adapter computes the strongest of three style matchups (pace, offensive rebounding, turnovers) from the two teams' last-10 box scores. The signals endpoint ranks it with the other signals; the facts bundle carries the same text and figures in `context.matchup`, which the explainer's number pool already treats as legal prose.

**Tech Stack:** TypeScript/React/vitest (hub `packages/predictor-ui`), Python 3.13/FastAPI/pytest (NBA).

**Spec:** `docs/superpowers/specs/2026-10-01-fixture-signals-design.md` (amended by Task 1) and `docs/superpowers/plans/2026-10-08-nba-feature-blocks.md`. **Depends on** `2026-10-08-nba-feature-pipeline-impl.md` Task 2 only (the wider box score: fg3a, ftm, ast...). It does NOT depend on the feature blocks being accepted.

**Verified:** built and run: hub `SignalRows` suites 83 passed, `tsc -b` clean (hub `node --test` has the same 2 environment-dependent failures with and without this change); NBA 27+11+5 new tests pass on `ddf3557` plus the feature-pipeline plan's changes.

## Global Constraints

- A figure may reach the page only if the same figure is in the row's own words (the shared component refuses a mismatch). The adapter rounds the gap ONCE to one decimal and uses that number in the words and in `figures.gap`.
- Headline at most 12 words. No roster sums as team figures (spec section 4 correction). No data means no row; a gap too small to matter means no row. One matchup row at most per game.
- A started or finished game carries no matchup (it is information only before tip-off), same rule as the absence signal.
- The adapter failing must never take the game page down: log it and return no signal.
- Vendored UI is changed in the hub and re-synced with `node scripts/sync-ui.mjs` only; never hand-edit the vendored copy. Use a worktree; add files by name; never push to main.
- The AI step may quote only figures that are in the facts. There is no "so what" step yet (it is fixture-signals Phase 4); this plan feeds the EXISTING explainer, nothing more.

---

## Task 1: Hub: add `matchup` to the shared `Signal` kinds, amend the spec

**Files:** Modify `packages/predictor-ui/src/components/SignalRows.tsx`, `docs/superpowers/specs/2026-10-01-fixture-signals-design.md`; create `packages/predictor-ui/src/components/SignalRows.matchup.test.tsx`.

- [ ] **Step 1: Write the failing test**

```tsx
/**
 * `matchup`: a code-computed finding about how the two teams PLAY ("BOS play 4.6 more possessions than MIA"),
 * drawn as a `delta_chip`.
 *
 * It reuses the chip rather than adding a visual because its figure IS a signed gap in the sport's own units, and
 * the chip already refuses the one failure that matters for a gap: a headline that does not state the figure the
 * chip draws. The tests pin that, plus the two properties that make `matchup` different from `trust`: the sample
 * floor does not apply (the figures are the two teams' own recent form, not a hit rate), and extra numbers in the
 * headline (the two raw paces) must not confuse the check on the gap.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  HeadlineFigureMismatchError,
  SignalRows,
  assertFigureIsStated,
  headlineStatesFigure,
  signalIsDrawn,
  type Signal,
} from "./SignalRows";

const matchup = (over: Partial<Signal> = {}): Signal => ({
  kind: "matchup",
  sport: "nba",
  game_id: "401898392",
  headline: {
    text: "BOS play 4.6 more possessions than MIA (101.4 vs 96.8).",
    figures: { gap: 4.6, home: 101.4, away: 96.8 },
  },
  n: 10,
  source: "ESPN box scores, last 10 games each",
  as_of: "2026-10-07",
  strength: 0.92,
  pre_kickoff_only: true,
  visual: "delta_chip",
  ...over,
});

describe("matchup", () => {
  it("is drawn as a delta chip with the gap the headline states", () => {
    expect(signalIsDrawn(matchup())).toBe(true);
    render(<SignalRows signals={[matchup()]} />);
    expect(screen.getByTestId("signal-delta")).toHaveTextContent("+4.6");
    expect(screen.getByTestId("signal-row")).toHaveAttribute("data-kind", "matchup");
  });

  it("refuses a headline that does not state the gap its chip draws", () => {
    const bad = matchup({ headline: { text: "BOS are a fast team.", figures: { gap: 4.6 } } });
    expect(() => assertFigureIsStated(bad)).toThrow(HeadlineFigureMismatchError);
  });

  it("refuses a headline that states the OPPOSITE direction", () => {
    const bad = matchup({ headline: { text: "MIA play −4.6 more possessions than BOS.", figures: { gap: 4.6 } } });
    expect(() => assertFigureIsStated(bad)).toThrow(HeadlineFigureMismatchError);
  });

  it("accepts the gap stated without its sign, and the two raw figures beside it do not interfere", () => {
    const s = matchup();
    expect(headlineStatesFigure(s.headline.text, s, 4.6)).toBe(true);
    const away = matchup({ headline: { text: "MIA play 4.6 fewer possessions than BOS (96.8 vs 101.4).", figures: { gap: -4.6 } } });
    expect(headlineStatesFigure(away.headline.text, away, -4.6)).toBe(true);
  });

  it("is not subject to the rate floor: it states no rate", () => {
    expect(signalIsDrawn(matchup({ n: 3 }))).toBe(true);
    expect(signalIsDrawn(matchup({ n: null }))).toBe(true);
  });
});
```

Run (from `packages/predictor-ui`): `npx tsc -b`
Expected: FAIL (`"matchup"` is not assignable to `SignalKind`).

- [ ] **Step 2: Edit the type and the spec**

```diff
diff --git a/docs/superpowers/specs/2026-10-01-fixture-signals-design.md b/docs/superpowers/specs/2026-10-01-fixture-signals-design.md
index d3c1bf3..ca7e9fd 100644
--- a/docs/superpowers/specs/2026-10-01-fixture-signals-design.md
+++ b/docs/superpowers/specs/2026-10-01-fixture-signals-design.md
@@ -55,5 +55,5 @@ up: "the model supplies words and ordering, never a number the panel renders".)
 ```
 Signal = {
-  kind: "trust" | "absence" | "line_gap" | "post_game",
+  kind: "trust" | "absence" | "line_gap" | "post_game" | "matchup",
   sport, game_id,
   headline: {figures...}      // the numbers the visual draws; the AI may quote only these
@@ -77,4 +77,5 @@ for the wording step. The shared UI renders `Signal[]` with predictor-ui compone
 | **line_gap** | "Model margin 3.1 vs line 2.5: 0.6 pts" with the model's historical record when it disagreed by >= 2 pts (only if n is enough). | NFL/CFB carry a quoted spread/total. PL, NBA and F1 have **no odds feed**: this signal never appears there. **CORRECTED 2026-10-04 — see §11.** | NFL, CFB |
 | **post_game** | "Projected margin 3.1, actual 14. Biggest miss: total (proj 40.6, actual 62)." Whether a flagged absence existed. | stored pre-game pick vs final score and available outcomes | all, finished games only |
+| **matchup** | "BOS play 4.6 more possessions than MIA (101.4 vs 96.8)." The one style matchup whose gap is largest against its own scale (pace, offensive rebounding, turnovers), drawn by the existing `delta_chip` (a signed gap in the sport's own units, so no new visual). Every figure is a team's own computed stat with `n` and `as_of`; never a roster sum. One row at most; none when no gap clears the strength floor or either team has fewer than 8 games. Quoted to the AI as facts, so the validator's number pool is unchanged in kind. | the two teams' last-10 box scores | NBA first; any sport with team box scores |
 
 ### Corrections baked in (found while writing this)
@@ -114,4 +115,5 @@ every state: signal present/absent per sport, finished game, started game). No n
 2. **absence**: builds on the merged injury gates and picks. NBA, NFL, PL.
 3. **post_game**: finished games; replaces the AI's current useless finished-game text.
+   - **matchup** (added 2026-10-08, NBA first): see `docs/superpowers/plans/2026-10-08-nba-matchup-signal-impl.md`. Needs no new visual.
 4. **the "so what" step** and the validator rule; retire the old factor-prose summary.
 5. **Slate brief** (separate spec): across a whole week, the biggest disagreement and the most
diff --git a/packages/predictor-ui/src/components/SignalRows.tsx b/packages/predictor-ui/src/components/SignalRows.tsx
index d8fc2ba..a481b1b 100644
--- a/packages/predictor-ui/src/components/SignalRows.tsx
+++ b/packages/predictor-ui/src/components/SignalRows.tsx
@@ -97,7 +97,9 @@ import { useId, useState } from "react";
 import { kickoff, pct, signed } from "../fmt";
 
-/** Spec §3's `kind`. All four are in the contract from phase 1; see
- *  `UndrawableSignalVisualError` for which of them this package can draw. */
-export type SignalKind = "trust" | "absence" | "line_gap" | "post_game";
+/** Spec §3's `kind`. The first four are in the contract from phase 1; `matchup` (how the two teams' styles meet)
+ *  joined it with the NBA feature work and is drawn by `delta_chip`: it is a signed gap in the sport's own units
+ *  (possessions, points of rebounding share), so it needs no new visual. See `UndrawableSignalVisualError` for
+ *  which visuals this package can draw. */
+export type SignalKind = "trust" | "absence" | "line_gap" | "post_game" | "matchup";
 
 /** Spec §3's `visual`. */
```

- [ ] **Step 3: Run**

Run (from `packages/predictor-ui`): `npx vitest run src/components/SignalRows.matchup.test.tsx src/components/SignalRows.test.tsx src/components/SignalRows.absence.test.tsx && npx tsc -b`
Expected: 83 passed, tsc silent.

- [ ] **Step 4: Commit and PR** `git add packages/predictor-ui/src/components/SignalRows.tsx packages/predictor-ui/src/components/SignalRows.matchup.test.tsx docs/superpowers/specs/2026-10-01-fixture-signals-design.md` (do NOT add `packages/predictor-ui/harness/fixture.js` or `node_modules`; they appear untracked). Run `scripts/coderabbit.sh` WITHOUT a pipe after CodeRabbit has finished, then merge.

## Task 2: Re-sync NBA's vendored UI

- [ ] **Step 1:** After Task 1 merges, from a CLEAN checkout of hub `main`: `node scripts/sync-ui.mjs <NBA worktree>/frontend/src` (if the guard refuses a detached checkout, name the commit with `--from <full sha>`; never `--vendor-anyway`).
- [ ] **Step 2:** In NBA: `cd frontend && npm run build && npx vitest run` (expected: all pass; the type now includes `matchup`). Commit only `frontend/src/predictor-ui/`. PR; the hub "Vendored UI is current" check should stay green.

## Task 3: NBA adapter `signals/matchup.py`

**Files:** Create `src/nba_predictor/signals/matchup.py`, `tests/test_signals_matchup.py`.
**Interfaces:** Consumes `features.team_form.long_with_opponent` and `per_game_stats` (pipeline plan Task 6). Produces `team_form(history, team, as_of, n=10)`, `matchup_from_forms(game_id, home, away, hf, af)`, `matchup_signal(game_id, home, away, history, as_of)` returning the `Signal` dict (kind `matchup`, visual `delta_chip`, `figures: {gap, home, away}`, `n`, `source`, `as_of`, `strength`) or `None`.

- [ ] **Step 1: Failing test**

```python
"""The NBA `matchup` signal. Every figure is a team's own recent form; the headline states the gap the chip draws."""
import pandas as pd
import pytest

from nba_predictor.signals import matchup
from tests.feature_fixtures import make_games


def form(**over):
    base = {"pace": 99.0, "orb_pct": 0.27, "drb_pct": 0.73, "tov_rate": 0.13, "opp_tov_rate": 0.13, "n": 10, "as_of": "2026-10-07"}
    base.update(over)
    return base


def words(text):
    return len(text.split())


def test_a_big_pace_gap_is_the_row_and_the_headline_states_the_gap():
    s = matchup.matchup_from_forms("g1", "BOS", "MIA", form(pace=101.4), form(pace=96.8))
    assert s["kind"] == "matchup" and s["visual"] == "delta_chip" and s["pre_kickoff_only"] is True
    assert s["headline"]["figures"]["gap"] == 4.6
    assert "4.6" in s["headline"]["text"] and "more possessions" in s["headline"]["text"]
    assert words(s["headline"]["text"]) <= 12
    assert s["headline"]["figures"]["home"] == 101.4 and s["headline"]["figures"]["away"] == 96.8


def test_the_gap_is_signed_in_the_home_teams_favour_and_the_words_agree_with_the_sign():
    s = matchup.matchup_from_forms("g1", "BOS", "MIA", form(pace=96.8), form(pace=101.4))
    assert s["headline"]["figures"]["gap"] == -4.6
    assert "4.6 fewer possessions" in s["headline"]["text"]


def test_the_largest_gap_relative_to_its_own_scale_wins():
    # pace gap 2.0 of a 5.0 scale = 0.4; rebounding gap 4.0 pts of a 4.0 scale = 1.0
    s = matchup.matchup_from_forms("g1", "BOS", "MIA", form(pace=100.0, orb_pct=0.31), form(pace=98.0, drb_pct=0.73))
    assert s["headline"]["figures"]["gap"] == pytest.approx(4.0, abs=0.05)
    assert "offensive glass" in s["headline"]["text"]


def test_no_row_when_every_gap_is_too_small_to_matter():
    assert matchup.matchup_from_forms("g1", "BOS", "MIA", form(pace=99.5), form(pace=99.0)) is None


def test_turnover_matchup_states_who_should_turn_it_over_less():
    s = matchup.matchup_from_forms("g1", "BOS", "MIA", form(tov_rate=0.10, opp_tov_rate=0.15), form(tov_rate=0.16, opp_tov_rate=0.10))
    assert "turn it over" in s["headline"]["text"] and s["headline"]["figures"]["gap"] > 0
    assert "less often" in s["headline"]["text"]


def test_strength_is_bounded_and_the_sample_is_the_smaller_of_the_two_teams():
    s = matchup.matchup_from_forms("g1", "BOS", "MIA", form(pace=120.0, n=9), form(pace=90.0, n=12))
    assert 0 < s["strength"] <= 1.0 and s["n"] == 9
    assert s["source"] == "ESPN box scores, last 9 games each"


def _fast_slow_league():
    """The synthetic league with BOS made fast (more shots) and MIA slow, so a pace matchup must exist."""
    games = make_games(n_days=120)
    for side in ("home", "away"):
        for team, factor in (("BOS", 1.25), ("MIA", 0.8)):
            rows = games[f"{side}_team"] == team
            for col in ("fga", "fta", "tov"):
                games.loc[rows, f"{side}_{col}"] = (games.loc[rows, f"{side}_{col}"] * factor).round()
    return games


def test_signal_from_real_shaped_history_meets_the_contract():
    games = _fast_slow_league()
    last = games["game_date"].max()
    out = matchup.matchup_signal("g9", "BOS", "MIA", games, last)
    assert out is not None, "BOS is far faster than MIA: a pace matchup must exist"
    assert set(out) == {"kind", "sport", "game_id", "headline", "n", "source", "as_of", "strength", "pre_kickoff_only", "visual"}
    assert out["n"] >= matchup.MIN_GAMES and out["as_of"] < last
    assert words(out["headline"]["text"]) <= 12
    gap = out["headline"]["figures"]["gap"]
    assert f"{abs(gap):.1f}" in out["headline"]["text"]
    assert gap > 0 and "more possessions" in out["headline"]["text"]


def test_a_team_with_too_few_games_gets_no_row():
    games = make_games(n_days=4)
    assert matchup.matchup_signal("g", "BOS", "MIA", games, games["game_date"].max()) is None


def test_it_only_reads_games_before_the_fixture_date():
    games = _fast_slow_league()
    cut = sorted(games["game_date"].unique())[50]
    a = matchup.matchup_signal("g", "BOS", "MIA", games, cut)
    later = games.copy()
    mask = later["game_date"] >= cut
    later.loc[mask, "home_pts"] = later.loc[mask, "home_pts"] + 40
    b = matchup.matchup_signal("g", "BOS", "MIA", later, cut)
    assert a == b


def test_missing_box_columns_are_an_error_not_a_silent_none():
    games = make_games(n_days=40).drop(columns=["home_fg3a"])
    with pytest.raises(KeyError, match="home_fg3a"):
        matchup.matchup_signal("g", "BOS", "MIA", games, "2099-01-01")


def test_empty_history_says_nothing():
    assert matchup.matchup_signal("g", "BOS", "MIA", pd.DataFrame(), "2099-01-01") is None
```

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_signals_matchup.py`  Expected: FAIL (`nba_predictor.signals.matchup` does not exist).

- [ ] **Step 2: Implement**

```python
"""The NBA `matchup` signal: where the two teams' STYLES meet, computed from their own recent box scores.

One row at most per game: the matchup whose gap is largest relative to its own scale. It is drawn by the shared
`delta_chip`, so the headline MUST state the (one-decimal) gap the chip shows; the adapter rounds the gap once and
uses that same number in the words and in `figures.gap`, which is what the shared component checks.

Rules, from the fixture-signals spec: every figure is a team's own computed stat with a sample size and a date
(never a roster sum); no data -> no row (never filler); a gap too small to matter -> no row.
"""
from __future__ import annotations

import pandas as pd

from nba_predictor.features.team_form import long_with_opponent, per_game_stats

FORM_GAMES = 10
MIN_GAMES = 8
MIN_STRENGTH = 0.5
VISUAL = "delta_chip"

#: A gap of this size (in the stat's own unit) is a full-strength row. Possessions per game; percentage points.
SCALES = {"pace": 5.0, "rebounding": 4.0, "turnovers": 2.5}
_NEEDED = ("pace", "orb_pct", "drb_pct", "tov_rate", "opp_tov_rate")
_BOX = ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "tov", "pts"]


def team_form(history: pd.DataFrame, team: str, as_of: str, n: int = FORM_GAMES) -> dict | None:
    """The team's mean over its last `n` completed games BEFORE `as_of`, or None when it has fewer than MIN_GAMES."""
    if history is None or history.empty:
        return None
    missing = [f"{s}_{f}" for s in ("home", "away") for f in _BOX if f"{s}_{f}" not in history.columns]
    if missing:
        raise KeyError(f"the matchup history lacks box columns {missing}; rebuild the training frame with the wider box score")
    done = history.dropna(subset=["home_pts", "away_pts"])
    done = done[(done["home_team"] == team) | (done["away_team"] == team)]
    done = done[done["game_date"] < as_of]
    if len(done) < MIN_GAMES:
        return None
    stats = per_game_stats(long_with_opponent(done))
    own = stats[stats["team"] == team].sort_values(["game_date", "game_id"]).tail(n)
    if len(own) < MIN_GAMES:
        return None
    return {**{k: float(own[k].mean()) for k in _NEEDED}, "n": int(len(own)), "as_of": str(own["game_date"].max())}


def _candidates(home: str, away: str, hf: dict, af: dict) -> list[tuple[str, float, str, dict]]:
    """(key, signed gap in home's favour, headline, extra figures). The gap is rounded ONCE and reused in the words."""
    out = []
    gap = round(hf["pace"] - af["pace"], 1)
    out.append(("pace", gap,
                f"{home} play {abs(gap):.1f} {'more' if gap > 0 else 'fewer'} possessions than {away} "
                f"({hf['pace']:.1f} vs {af['pace']:.1f}).",
                {"home": round(hf["pace"], 1), "away": round(af["pace"], 1)}))
    gap = round((hf["orb_pct"] - (1.0 - af["drb_pct"])) * 100, 1)
    text = (f"{home} should win the offensive glass by {abs(gap):.1f} pts against {away}."
            if gap > 0 else f"{away} should hold the defensive glass by {abs(gap):.1f} pts against {home}.")
    out.append(("rebounding", gap, text, {"home": round(hf["orb_pct"] * 100, 1), "away": round(af["drb_pct"] * 100, 1)}))
    home_tov = (hf["tov_rate"] + af["opp_tov_rate"]) / 2.0
    away_tov = (af["tov_rate"] + hf["opp_tov_rate"]) / 2.0
    gap = round((away_tov - home_tov) * 100, 1)
    out.append(("turnovers", gap,
                f"{home} should turn it over {abs(gap):.1f} pts {'less' if gap > 0 else 'more'} often than {away}.",
                {"home": round(home_tov * 100, 1), "away": round(away_tov * 100, 1)}))
    return out


def matchup_from_forms(game_id: str, home: str, away: str, hf: dict, af: dict) -> dict | None:
    best = None
    for key, gap, text, extra in _candidates(home, away, hf, af):
        strength = min(1.0, abs(gap) / SCALES[key])
        if gap != 0 and (best is None or strength > best[0]):
            best = (strength, gap, text, extra)
    if best is None or best[0] < MIN_STRENGTH:
        return None
    strength, gap, text, extra = best
    n = min(hf["n"], af["n"])
    return {
        "kind": "matchup",
        "sport": "nba",
        "game_id": str(game_id),
        "headline": {"text": text, "figures": {"gap": gap, **extra}},
        "n": n,
        "source": f"ESPN box scores, last {n} games each",
        "as_of": max(hf["as_of"], af["as_of"]),
        "strength": round(strength, 3),
        "pre_kickoff_only": True,
        "visual": VISUAL,
    }


def matchup_signal(game_id: str, home: str, away: str, history: pd.DataFrame, as_of: str) -> dict | None:
    hf, af = team_form(history, home, as_of), team_form(history, away, as_of)
    if hf is None or af is None:
        return None
    return matchup_from_forms(game_id, home, away, hf, af)
```

- [ ] **Step 3: Run** `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_signals_matchup.py`  Expected: 11 passed.
- [ ] **Step 4: Commit** `git add src/nba_predictor/signals/matchup.py tests/test_signals_matchup.py`

## Task 4: Rank it in the signals endpoint

**Files:** Modify `src/nba_predictor/api/signals.py`, `src/nba_predictor/api/deps.py`; create `tests/test_signals_matchup_endpoint.py`.
**Interfaces:** Produces `deps.get_matchup_history()` (the training cache, re-read only when the file's mtime changes; empty frame when there is no cache yet) and `signals_for_game(..., history=None)`.

- [ ] **Step 1: Failing test**

```python
"""The matchup adapter inside `signals_for_game`: ranked with the others, and its failure never breaks the page."""
import pytest

from nba_predictor.api import signals as signals_module
from nba_predictor.api.signals import signals_for_game
from nba_predictor.signals import matchup

GAME = {"game_id": "401", "home_team": "LAL", "away_team": "BOS", "tipoff": "2099-01-01T00:00:00Z"}
STYLE = {"kind": "matchup", "sport": "nba", "game_id": "401", "headline": {"text": "x 4.6", "figures": {"gap": 4.6}},
         "n": 10, "source": "s", "as_of": "2026-10-07", "strength": 0.9, "pre_kickoff_only": True, "visual": "delta_chip"}


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(signals_module, "get_game", lambda schedule, game_id: GAME if game_id == "401" else None)
    monkeypatch.setattr(signals_module, "picks_by_player_stat", lambda db, game_id, game: {})
    monkeypatch.setattr(signals_module, "load_player_name_map", lambda path: {})
    monkeypatch.setattr(signals_module, "_status", lambda game, now: "scheduled")
    monkeypatch.setattr(signals_module, "_now", lambda: None)


def test_a_matchup_row_is_returned_when_the_adapter_finds_one(wired, monkeypatch):
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: STYLE)
    out = signals_for_game("401", None, [], [], history=object())
    assert [s["kind"] for s in out] == ["matchup"]


def test_the_adapter_receives_the_teams_and_the_fixture_date(wired, monkeypatch):
    seen = {}
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: seen.update(args=a) or None)
    signals_for_game("401", None, [], [], history=object())
    assert seen["args"][:3] == ("401", "LAL", "BOS") and seen["args"][4] == "2099-01-01"


def test_an_adapter_that_raises_is_no_signal_and_not_a_500(wired, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("history unreadable")

    monkeypatch.setattr(matchup, "matchup_signal", boom)
    assert signals_for_game("401", None, [], [], history=object()) == []


def test_without_history_there_is_no_matchup_row_and_nothing_else_changes(wired):
    assert signals_for_game("401", None, [], []) == []


def test_a_started_game_carries_no_matchup(wired, monkeypatch):
    monkeypatch.setattr(signals_module, "_status", lambda game, now: "live")
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: STYLE)
    assert signals_for_game("401", None, [], [], history=object()) == []
```

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_signals_matchup_endpoint.py`  Expected: FAIL (`signals_for_game` takes no `history`).

- [ ] **Step 2: Edit**

```diff
diff --git a/src/nba_predictor/api/signals.py b/src/nba_predictor/api/signals.py
index 6d1ec93..56f7754 100644
--- a/src/nba_predictor/api/signals.py
+++ b/src/nba_predictor/api/signals.py
@@ -45,5 +45,5 @@ from ..config import DATA_DIR
 from ..services.hub_service import load_player_name_map
 from ..services.schedule_repository import get_game
-from ..signals import absence
+from ..signals import absence, matchup
 from ..tracking.player_props import picks_by_player_stat
 
@@ -60,4 +60,5 @@ def signals_for_game(
     schedule: list[dict],
     injuries: list[dict],
+    history=None,
 ) -> list[dict]:
     """Every signal this game can honestly carry, strongest first.
@@ -95,4 +96,17 @@ def signals_for_game(
 
     found = [signal] if signal is not None else []
+
+    # The same rule as the absence adapter above: a signal is an enhancement on a game page, so an adapter that
+    # raises is "no signal", logged, and never allowed to take the page down.
+    if history is not None:
+        try:
+            style = matchup.matchup_signal(
+                game_id, game["home_team"], game["away_team"], history, str(game.get("game_date") or game.get("tipoff") or "9999")[:10],
+            )
+        except Exception:
+            logger.exception("matchup signal unavailable for %s", game_id)
+            style = None
+        if style is not None:
+            found.append(style)
     return sorted(found, key=lambda s: s["strength"], reverse=True)[:MAX_SIGNALS]
 
@@ -104,4 +118,5 @@ def get_signals(
     db_path=Depends(deps.get_db_path),
     injuries: list[dict] = Depends(deps.get_injury_report),
+    history=Depends(deps.get_matchup_history),
 ) -> dict:
     """The signals for one game. `{"signals": []}` is a valid, complete answer.
@@ -111,5 +126,5 @@ def get_signals(
     """
     try:
-        signals = signals_for_game(game_id, db_path, schedule, injuries)
+        signals = signals_for_game(game_id, db_path, schedule, injuries, history)
     except HTTPException:
         raise
```

```diff
diff --git a/src/nba_predictor/api/deps.py b/src/nba_predictor/api/deps.py
index 7554663..cd999c5 100644
--- a/src/nba_predictor/api/deps.py
+++ b/src/nba_predictor/api/deps.py
@@ -74,4 +74,26 @@ def get_training_games_path() -> Path:
 
 
+_MATCHUP_HISTORY: dict = {"mtime": None, "frame": None}
+
+
+def get_matchup_history():
+    """The completed-games frame the matchup signal reads: the training cache, re-read only when the file changes.
+
+    Empty when there is no cache yet (a fresh deploy): the signal then says nothing, and nothing else is affected.
+    """
+    import json
+
+    import pandas as pd
+
+    path = get_training_games_path()
+    try:
+        mtime = path.stat().st_mtime
+    except OSError:
+        return pd.DataFrame()
+    if _MATCHUP_HISTORY["mtime"] != mtime:
+        _MATCHUP_HISTORY.update(mtime=mtime, frame=pd.DataFrame(json.loads(path.read_text())))
+    return _MATCHUP_HISTORY["frame"]
+
+
 def get_today() -> str:
     return date.today().isoformat()
```

- [ ] **Step 3: Run** `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_signals_matchup_endpoint.py tests/test_signals_endpoint.py`  Expected: all pass (existing endpoint tests unchanged).
- [ ] **Step 4: Commit** `git add src/nba_predictor/api/signals.py src/nba_predictor/api/deps.py tests/test_signals_matchup_endpoint.py`

## Task 5: Quote it to the AI summary, as facts

The explainer's validator builds a pool of every number found in the facts JSON; prose may use only those. Putting the matchup text and figures in `context.matchup` therefore makes exactly the figures a reader can see legal, and nothing else.

**Files:** Modify `src/nba_predictor/api/facts.py`; create `tests/test_facts_matchup.py`.
**Interfaces:** Produces `facts._history()`, `facts._matchup_context(game, started)` -> `{text, gap, home, away, n, as_of}` or `None`; `_context(game, schedule, matchup=None)` adds the `matchup` key.

- [ ] **Step 1: Failing test**

```python
"""The style matchup travels to the AI summary as FACTS: the same figures the page shows, nothing newly computed."""
import pandas as pd

from nba_predictor.api import facts as facts_module
from nba_predictor.signals import matchup

GAME = {"game_id": "401", "home_team": "BOS", "away_team": "MIA", "game_date": "2026-10-08", "tipoff": "2026-10-08T23:30:00Z"}
SIGNAL = {
    "kind": "matchup", "sport": "nba", "game_id": "401",
    "headline": {"text": "BOS play 4.6 more possessions than MIA (101.4 vs 96.8).", "figures": {"gap": 4.6, "home": 101.4, "away": 96.8}},
    "n": 10, "source": "ESPN box scores, last 10 games each", "as_of": "2026-10-07", "strength": 0.92,
    "pre_kickoff_only": True, "visual": "delta_chip",
}


def test_the_facts_context_carries_the_matchup_text_and_every_figure_the_page_shows(monkeypatch):
    monkeypatch.setattr(facts_module, "_history", lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: SIGNAL)
    ctx = facts_module._context(GAME, [], facts_module._matchup_context(GAME, started=False))
    assert ctx["matchup"] == {
        "text": SIGNAL["headline"]["text"], "gap": 4.6, "home": 101.4, "away": 96.8, "n": 10, "as_of": "2026-10-07",
    }


def test_a_started_game_has_no_matchup_in_its_facts(monkeypatch):
    monkeypatch.setattr(facts_module, "_history", lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: SIGNAL)
    assert facts_module._matchup_context(GAME, started=True) is None


def test_no_signal_means_no_key_and_an_unchanged_context(monkeypatch):
    monkeypatch.setattr(facts_module, "_history", lambda: pd.DataFrame())
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: None)
    assert "matchup" not in facts_module._context(GAME, [], facts_module._matchup_context(GAME, started=False))


def test_an_unreadable_history_never_breaks_the_facts(monkeypatch):
    def boom():
        raise OSError("training cache unreadable")

    monkeypatch.setattr(facts_module, "_history", boom)
    assert facts_module._matchup_context(GAME, started=False) is None


def test_the_adapter_is_asked_with_the_fixture_date_so_it_reads_only_earlier_games(monkeypatch):
    seen = {}
    monkeypatch.setattr(facts_module, "_history", lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(matchup, "matchup_signal", lambda *a, **k: seen.update(args=a) or None)
    facts_module._matchup_context(GAME, started=False)
    assert seen["args"][:3] == ("401", "BOS", "MIA") and seen["args"][4] == "2026-10-08"
```

Run: `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_facts_matchup.py`  Expected: FAIL (`_matchup_context` not defined).

- [ ] **Step 2: Edit**

```diff
diff --git a/src/nba_predictor/api/facts.py b/src/nba_predictor/api/facts.py
index 12009fb..e4b5f89 100644
--- a/src/nba_predictor/api/facts.py
+++ b/src/nba_predictor/api/facts.py
@@ -29,4 +29,5 @@ from ..api import deps
 from ..services import hub_service
 from ..services.schedule_repository import get_game
+from ..signals import matchup as matchup_signals
 from ..tracking import store
 from ..tracking.timing import latest_pre_tip, made_before_tip, pick_cutoff
@@ -264,8 +265,38 @@ def _players(game_id: str, teams: set[str]) -> list[dict]:
 
 
-def _context(game: dict, schedule: list[dict]) -> dict:
-    """Rest and back-to-back, but only when the schedule already carries
-    them. No new features are computed here."""
+def _history():
+    """The completed-games frame the matchup signal reads (empty when there is no training cache yet)."""
+    return deps.get_matchup_history()
+
+
+def _matchup_context(game: dict, started: bool) -> dict | None:
+    """The one style matchup worth stating, as FACTS the AI may quote: its own computed figures and a sample size.
+
+    Nothing here is new analysis: it is the signal the game page already shows, so the number pool the explainer
+    validates against contains exactly the figures a reader can see. A started game gets none (a matchup is only
+    information before tip-off); an unreadable history gets none, and the summary is simply the one it was.
+    """
+    if started:
+        return None
+    try:
+        tip = _tip_off(game)
+        as_of = tip.date().isoformat() if tip is not None else str(game.get("game_date") or "")[:10]
+        signal = matchup_signals.matchup_signal(
+            str(game.get("game_id")), game["home_team"], game["away_team"], _history(), as_of,
+        )
+    except Exception:
+        logger.exception("matchup facts unavailable for %s", game.get("game_id"))
+        return None
+    if signal is None:
+        return None
+    return {"text": signal["headline"]["text"], **signal["headline"]["figures"], "n": signal["n"], "as_of": signal["as_of"]}
+
+
+def _context(game: dict, schedule: list[dict], matchup: dict | None = None) -> dict:
+    """Rest and back-to-back, but only when the schedule already carries them, plus the style matchup when there
+    is one. No new features are computed here."""
     context: dict[str, Any] = {}
+    if matchup is not None:
+        context["matchup"] = matchup
     home_rest = game.get("home_rest_days")
     away_rest = game.get("away_rest_days")
@@ -385,5 +416,5 @@ def get_facts(game_id: str) -> dict:
         "markets": [] if (started and chosen is None) else _markets(game, prediction),
         "drivers": [],
-        "context": _context(game, schedule),
+        "context": _context(game, schedule, _matchup_context(game, started)),
         "players": _players(str(game_id), {home_team, away_team}),
         "record": _record(),
```

- [ ] **Step 3: Run** `uv run --python 3.13 --extra dev pytest -q -p no:cacheprovider tests/test_facts_matchup.py tests/test_facts.py`  Expected: 28 passed.
- [ ] **Step 4: Commit** `git add src/nba_predictor/api/facts.py tests/test_facts_matchup.py`

## Task 6: Prove the explainer accepts the matchup figures and still rejects invented ones

**Files:** `services/explainer/tests/test_validate_matchup_context.py` (create), in `predictor-hub`.

- [ ] **Step 1: Read how the existing validator tests build their inputs.** Open `services/explainer/tests/test_validate.py` and `test_validate_factors.py`; note how they construct `output` (verdict, factors), `facts_json` and `news_json` for `validate(output, facts_json, news_json)` in `services/explainer/explainer/validate.py`.
- [ ] **Step 2: Write the test (same helpers as those files).** Build a NBA `Facts` whose `context` is `{"matchup": {"text": "BOS play 4.6 more possessions than MIA (101.4 vs 96.8).", "gap": 4.6, "home": 101.4, "away": 96.8, "n": 10, "as_of": "2026-10-07"}}` and assert: (a) factor prose containing `4.6 more possessions` and `101.4` passes the number pool (no number problem returned); (b) prose containing an INVENTED figure such as `7.9 more possessions` is rejected with the existing "number not in the facts" problem; (c) a prose figure equal to `gap` but with the wrong direction word is handled exactly as other directional figures are (follow the existing sign tests). Red-check (b) by temporarily adding 7.9 to the facts; it must then pass.
- [ ] **Step 3: Run** `cd services/explainer && uv run --python 3.11 --extra dev pytest -q tests/test_validate_matchup_context.py` (explainer image is python:3.11). Expected: pass. If (a) FAILS, the explainer does not read `context` numbers: stop and report; do NOT widen the validator without Kevin.
- [ ] **Step 4: Commit and PR in `predictor-hub`; deploy is the reviewer's (explainer image).**

## Task 7: See it on the page (desktop and 390px)

- [ ] **Step 1:** In the NBA worktree with the pipeline plan's data in `data/cache/training/games.json`, start the app (`uv run --python 3.13 uvicorn nba_predictor.api.main:app` or the repo's documented command) and open a game with a clear matchup; confirm: one extra row, the chip shows the signed gap, the headline states the same number, the evidence line shows `n=10` and the date, nothing else on the page changed.
- [ ] **Step 2:** The existing signals harness (`frontend/src/signals-harness.tsx`) renders signal states; add a `matchup` state and capture desktop and 390px screenshots into `docs/screenshots/matchup/`. No new visual was added, so an `/impeccable audit` is only needed if the row's copy or spacing is changed.
- [ ] **Step 3:** Open the AI summary on the same game and confirm any matchup sentence quotes only figures that are on the page.

## Out of scope

The fixture-signals Phase 4 "so what" step and validator rule; matchup signals for other sports; a three-point-defence or free-throw matchup row (add later only with a measured scale); caching `team_form` (the endpoint recomputes from the cached frame per request; measure latency in Task 7 and cache only if needed).

## Self-review

Spec coverage: type + spec amendment (T1), vendored re-sync (T2), adapter with rounding/12-word/figure rules (T3), endpoint ranking and error isolation and started-game rule (T4), AI facts (T5), explainer acceptance and rejection (T6), visual check (T7). Names are consistent across tasks (`matchup_signal`, `get_matchup_history`, `_matchup_context`).
