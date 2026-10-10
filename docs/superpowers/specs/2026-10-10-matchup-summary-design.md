# Matchup section and tactical AI read — design

Approved by Kevin in chat on 2026-10-10.

## Problem
The AI summary restates what the fixture detail already shows (win probability, spread, total, rest) as Edge/Risk/Price bullets, while the useful content — how the two teams' units meet — sits as thin "context" lines at the bottom.

## Decisions
1. **Matchup section (data, no AI)** in the fixture detail, above the AI panel, using `RankDuel`. Shown for every game that has the data; absent (no placeholder) otherwise.
2. **AI panel = verdict + a 2–3 sentence tactical read.** It is about the matchup and player context only. It must not restate pick probability, spread, total, rest or moneyline. Edge/Risk/Price groups are removed from the panel.
3. **NFL player props stay displayed exactly as today.** The AI read may *mention* the predicted top rusher/passer as context; the props block is unchanged.
4. **Duels stay neutral** (no "advantage"/"favours") until the lift-gate data run proves a duel type predicts. The read describes the matchup without picking a side from it.
5. **Validation unchanged in spirit:** every number in the read must exist in the facts; a read that restates a market figure is rejected and the deterministic template read is served.

## Per-sport facts (all in `context.matchups`, same row shape as today)
- **NFL:** existing rank duels + predicted top rusher/passer names (already in player props) as context facts.
- **NBA:** offence/defence rating, pace, rebounds/game, 3P%, FG% as ranked duels (four-factors duels already exist). **Known bug to fix first:** NBA fixture detail is missing one team's predictions — reproduce on live, find root cause, fix before building on it.
- **PL:** attack/defence strength derived from the live form + Elo table, plus xG for/against; ranked among 20 teams.
- **CFB:** FBS-only rank duels from CFBD efficiency data (budget-aware weekly pull).
- **F1:** own version in the same section: driver/constructor recent form, qualifying pace, track history. No offence/defence framing.

## Non-goals
Directing duels (needs `duel_lift` data run); new models; DFS.

## Success criteria
Live fixture detail on each sport shows the Matchup section for upcoming games with data; the AI read contains no restated market figure (validator test); NBA shows both teams' predictions; suites green; each sport verified by curl on the live host after deploy.
