# Plan: fixture signals, phases 1-4

Spec: `docs/superpowers/specs/2026-10-01-fixture-signals-design.md` (approved by Kevin 2026-10-01).
One PR per repo per phase, test-first, `npm run build` clean, red proofs, CodeRabbit gate, no deploys.
Use the impeccable skill for the mocks (desktop + 390px, every state); no new tokens or faces.

## Task 0 — the spike (measure, do not assume). Output: a short table in the first hub PR.
For each sport (NFL, CFB, NBA, PL, F1) answer, with the file path and a real row count:
1. Do stored picks have probability buckets deep enough for `trust` at n >= 30? Which probability range has n >= 30?
2. NFL/CFB: shape of the quoted line, pre-game stored vs live for started games; where `line_gap` reads it.
3. Where does a finished game's actual outcome live per sport (for `post_game`)?
4. PL: FPL statuses i/s/u -> out vs flag (PL#38 already removes i/s/u).
5. Where the explainer's facts/validator live (`predictor-hub` explainer service) and how `/facts` is assembled.
Any signal with no data in a sport is dropped for that sport. Do not invent.

## Phase 1 — shared contract + trust + line_gap
- hub `packages/predictor-ui`: `Signal` type (spec §3), `SignalRows` component (delta chip, reliability bar),
  one-line headline (<= 12 words), collapsed evidence line (source, n, as_of). Component tests: renders each
  visual; renders nothing for an empty list; never renders a rate with n < floor; the figures drawn equal
  `headline` figures.
- adapters (one module per sport API, e.g. `signals/trust.py`, `signals/line_gap.py`): `trust` for all sports,
  `line_gap` for NFL/CFB only. Constants per sport: `TRUST_MIN_N = 30`. `strength` is computed and unit-tested
  (monotonic in disagreement size / reliability gap). Endpoint `GET /signals/{game_id}` returning the top 3 by
  `strength`; also embedded in `/facts`.
- `scripts/sync-ui.mjs` each site; render `SignalRows` under the facts block in each modal.
- Tests per adapter: n below floor -> no signal; strength ordering; earliest recorded pick is used for started
  games; no signal restates a rerun as the pre-game call.

## Phase 2 — absence (NBA, NFL, PL)
Build on the merged injury gates (NBA `/players/out` + Day-To-Day, NFL gate, PL FPL). Row text states the
player's own projection and rank ("Out: J. Jacobs, our #2 rush projection (78 yds)"). Never a team total built
from roster sums. Day-To-Day is a flag, never a number. F1/CFB: no row. Tests: out player appears with own
projection; doubtful flagged not computed; no team-sum figure anywhere; stale injury data (TTL) yields no row.

## Phase 3 — post_game (finished games, all sports)
Stored pre-game pick vs final: "Projected margin 3.1, actual 14. Biggest miss: total (proj 40.6, actual 62)",
and whether a flagged absence existed. Uses the earliest recorded pick. Replaces the AI's current finished-game
text. Visual `projected_vs_actual`. Tests: finished only; uses the stored pick, not today's rerun; handles
missing actuals by showing no row.

## Phase 4 — the "so what" step and validator
Explainer: input is the selected `Signal[]` + facts; output `{ so_what: str (<= 20 words) }`, no band, no figures of
its own. Validator: every figure in `so_what` must appear in a signal payload; existing banned-word / market-word /
timing rules unchanged; zero overlap with the facts block (a restated figure fails -> template wording). Template
path renders the signals with fixed one-line wording and the footer says which wrote it. Retire the factor-prose
summary only after the new path is verified on all five served sports. Tests run on Python 3.11 (image is
python:3.11-slim) and never touch the network; red-check the validator by removing the figure rule.

## Out of scope
Phase 5 (slate brief) needs its own spec. Do not start it.

## Done when
Phases 1-4 merged through the gate; summary on hub#69 lists repos needing a deploy, and anything the spike
dropped for a sport and why.
