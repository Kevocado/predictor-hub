# SDD ledger — plan: docs/superpowers/plans/2026-09-25-phase4-match-explainer.md
Ruling: task-start/task-done scripts can't resolve their path (skills installed as superpowers-*) — ledger by hand — cost if wrong: none
Pre-flight: Ruling: free model IDs could not be verified — openrouter.ai is blocked by this container's egress policy — keep the plan defaults (env-overridable EXPLAINER_MODEL / EXPLAINER_FALLBACK_MODEL), treat a 404/400 model error like any failure (fallback model, then template), and put a 'verify model IDs on the VPS' step in the README — cost if wrong: template text until the env var is updated
Pre-flight: shared interfaces — Facts contract (T1) consumed by cache T2 (render→hash), validator T4 (numbers_in), prompts T6, sport /facts T8–11 (must emit the same keys), ExplainerPanel T12 (consumes the service response from T6). Checked the plan text: consistent; ExplainerPanel response shape is fixed in T6.
Task 1: complete (commits b74afd7..3459376, tests: uv run pytest -q → 6 facts+config pass; test_config written after config.py — config is plain settings wiring)
Task 2: complete (cache; tests: uv run pytest -q → 3 cache pass, RED first on import)
Task 3: complete (ledger; tests: uv run pytest -q → 12/12 incl. 200-thread cap test)
Task 4: Ruling: plan's good() fixture is ~85 words, below the 120-word floor the same task sets — rewrote the fixture to 120+ words, kept every plan assertion — cost if wrong: none
Task 4: Ruling: ids and date/time strings are excluded from the number pool (else '00:20' kickoff digits excuse '20%') — stricter than the spec's 'appears in the rendered facts' — cost if wrong: an LLM citing a date retries once, then the template
Task 4: Ruling: numbers compared by absolute value (margin sign depends on perspective); word count is over section texts only; also checks title ≤ 6 words (spec Section 2); facts.numbers_in removed (validate.numbers_in is the one owner)
Task 4: Ruling: template trust line uses words ('about four times in ten'), so its own text never carries a number absent from the facts
Task 4: complete (commit f3724ae, tests: uv run pytest -q → 26 passed)
Task 5: Ruling: failed ESPN fetches are cached for 5 min (plan: 30 min for successes only) so an outage doesn't add a 6 s timeout per game during pre-generation — cost if wrong: news returns 5 min later
Task 5: complete (commit 12ff11d, tests: uv run pytest -q → 33 passed)
Task 6: Ruling: spec's '±0.05 rounding tolerance' applied to fractions let '62%' pass for 0.64 (5-point misstatement) — tolerance is now half a unit of the written token's last digit (3.4→±0.05 as spec; 62%→±0.5pt; 48 matches 47.8) — cost if wrong: a few more retries/templates
Task 6: Ruling: templates stored in an outage/budget cap are re-tried after 3 h (TEMPLATE_RETRY_SECONDS) instead of being cached for the life of the facts — cost if wrong: up to 2 extra calls per id per 3 h while the model keeps failing
Task 6: Ruling: fenced JSON (```json) from free models is unwrapped before parsing; section keys are whitelisted (market/title/text/numbers_used)
Task 6: complete (commit 12793d7, tests: uv run pytest -q → 50 passed)
Task 7: Ruling: uvicorn runs create_app via --factory (no import-time Settings/side effects); pre-generation only starts when enabled AND a key is set (templates need no pre-generation) — cost if wrong: none
Task 7: complete (commit 6da6689, tests: uv run pytest -q → 53 passed; Dockerfile NOT built — no docker in this container; verify on the VPS)
Review (Tasks 1–6): fresh reviewer — 0 Critical, 7 Important, 7 Minor. Fixed all 7 Important + minors (pct/int tolerance, id quoting, numbers_used, both models in key) in 3584d75; tests/test_review_fixes.py RED(13)→GREEN, suite 67/67
Ruling: cache key excludes news (budget: ~100 upcoming ids × 8 runs/day would exceed the cap on headline churn) — cost if wrong: an explanation doesn't pick up a new headline until facts change
Final: minor (deferred): signed tokens compared by absolute value ("BAL +2.5" passes against "BAL -2.5"); numbers written as words are not checked
Note: this ledger was kept in the git-ignored .superpowers/sdd/ workspace and moved here so other executors can read it. Keep appending HERE (tracked), not in .superpowers/.
Next: Task 8 (NFL /facts). Tasks 1–7 and the Tasks 1–6 review fix pass are complete (last commit 3584d75, 67 tests).
