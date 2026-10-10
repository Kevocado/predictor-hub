# Matchup section and tactical AI read — implementation plan

> For agentic workers: use superpowers:subagent-driven-development; one fresh subagent per task, review between. Spec: `docs/superpowers/specs/2026-10-10-matchup-summary-design.md`.

**Global rules:** branch + PR per task, never push to main; TDD with real data types (pandas rows, not dicts); offline tests only; read every check line before merge, CodeRabbit gate `scripts/coderabbit.sh` exit 0 unpiped; after any deploy curl the live endpoint; explainer tests on py3.11 (`uv run --python 3.11 --extra dev pytest`).

## Task 1 — Hub: UI + explainer (blocks 2–7)
Files: `packages/predictor-ui/src/components/{MatchupBrief,RankDuel}.tsx` (+tests, harness case), `services/explainer/explainer/{prompts,validate,template,service,config}.py` (+tests).
- [ ] Matchup section rendered above the AI panel; panel shows verdict + read only (no Edge/Risk/Price groups).
- [ ] Prompt: matchups + player context are the input; market numbers background only; output = verdict + `read` (2–3 sentences). Bump `prompt_version` to v9.
- [ ] Validator: reject a read that contains the pick probability, spread, total, rest or moneyline figures; keep the number-pool rule. Fallback = template read.
- [ ] Template read: deterministic 2–3 sentences from matchup rows (+ NFL top rusher/passer names), neutral wording.
- [ ] Remove the neutral-backfill of rows into the factor list (superseded by the section).
- Verify: vitest + tsc, explainer suite, harness screenshot.

## Task 2 — NBA (after Task 1 contract merged)
- [ ] Reproduce and fix "one team's predictions missing" in the fixture detail (live curl first, regression test with real shapes).
- [ ] Facts: off/def rating, pace, reb/g, 3P%, FG% duels from existing four-factors/box-score data.

## Task 3 — NFL
- [ ] Add predicted top rusher/passer names to facts context for the explainer only; props block unchanged.

## Task 4 — PL
- [ ] Derive attack/defence strength from form + Elo + xG; rank among 20; emit duels.

## Task 5 — CFB
- [ ] FBS-only rank duels from CFBD advanced data; weekly pull within budget; snapshot-carried like NFL.

## Task 6 — F1
- [ ] Driver/constructor read facts (recent form, quali pace, track history) in the same section.

## Task 7 — Rollout (one at a time, prune between)
- [ ] Re-sync predictor-ui to each site, merge, `deploy-site.sh`, redeploy explainer from hub main, curl each live host, confirm Matchup section and a read with no restated figures.

Tasks 2–6 are independent once Task 1's contract is merged and can run in parallel.
