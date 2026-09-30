# NFL current-season players — which players the hub lists

**Status:** decision taken while Kevin is away, reversible. Recorded here because
item 8 of the reviewer's standing list asked for the decision to be written into a
spec rather than left in someone's head.

**Parent spec:** `2026-09-30-fixture-insight-design.md` §C (NFL row) and §D (NFL
availability). This document does not change that spec; it settles one question it
left open — who is eligible to appear in an NFL player row at all.

Measured at `NFL_Predictor` `origin/main` **b2ec1b7** (fetched 2026-09-30),
with every line read via `git show origin/main:<file>`.

## The measured behaviour

- `src/nfl_predictor/api/routes.py:844` — `GET /hub/players?season=<int>`,
  defaulting to `config.CURRENT_SEASON`.
- `routes.py:853` — `_get_hub_players_live(season)` builds the response from
  `player_season_mod.load_hub_weekly(season)` and
  `player_season_mod.player_season(weekly, season)`.
- `src/nfl_predictor/data/player_season.py:37-38` — `player_season()` keeps
  `weekly[weekly["season"] == season]` and
  `weekly[weekly["position"].isin(POSITIONS)]`, where `POSITIONS = ["QB", "RB",
  "WR", "TE"]` (`player_season.py:10`).

**Consequence, stated exactly:** a player appears in the hub if and only if he has
at least one weekly row in the requested season at a modelled position. A
current-season rookie who has not yet taken a snap, a player who has only appeared
at a non-modelled position, and anyone on a current-season roster who does not
appear in the weekly feed, are **absent from the response entirely**. The site
cannot show them, cannot project them, and cannot say "no data yet" about them,
because there is no row to attach a message to.

## The decision

**1. The hub keeps listing only players with current-season data.** A projection
for a player with no week of his own current-season data would rest on nothing but
a position and a team — that is an invented number, and this product's rule is
that a surface may not state a figure the data does not carry. Better an absent
player than a confident wrong one.

**2. `POSITIONS` stays `QB, RB, WR, TE`.** Kickers, offensive line and defensive
line remain excluded, which is the same rule the predicted box score already
states in its own words ("the box score only covers QB, RB, WR and TE") — Sports
PR #20. A position with no projection has no row.

**3. The missing piece is disclosure, not membership.** "No data yet" is a fact we
can carry: `src/nfl_predictor/data/depth_charts.py:115` (`resolve_chart`) returns
the most recent published chart at or before a given week, so the current-season
roster is available in-repo. Surfacing roster-only players as **names with no
projection and an explicit "no data yet"** is the honest version of inclusion, and
it is deferred to its own PR rather than folded into a picks phase.

**4. When it does land, it must never be ranked.** A roster-only player carries no
model number, so per §D of the parent spec and the rule fixed in predictor-hub#50
(an out player leaves the ranking entirely), such a player may appear in a
"no data yet" list and nowhere else: no bar, no tile, no rank position, no callout.

## Alternatives considered

- **Union the depth chart into `/hub/players` now.** Rejected: it would put
  players in a response that feeds projections, and every consumer of that
  response would need the "no number" case handled before it could ship. That is
  a bigger change than the disclosure it enables, and it risks a row that has no
  figure in it.
- **Backfill a prior season's rows for missing players.** Rejected: it would let a
  2025 figure pass as a 2026 one. The season filter exists precisely to stop that.

## Reverse by

Delete sections 1-2 and add a roster union to `player_season()`; the guard against
inventing numbers is section 3's "no data yet" state, not the membership filter.