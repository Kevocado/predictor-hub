# The explainer on all five sports, and live refreshes on game days

**Date:** 2026-09-27
**Status: partially implemented.** Corrected 2026-10-04 — this said only "awaiting
Kevin's review", which a reader could not distinguish from an unimplemented
proposal. Its two asks split, and only one of them shipped. Checked 2026-10-04
against merged PRs and against each site's `refresh-public-snapshot.yml` on
`origin/main`:

| ask | state | evidence |
|---|---|---|
| the explainer reaches **all five** sports | **done** | `docs/superpowers/ledgers/2026-09-25-phase4-match-explainer.md` records the service built and the sport set derived from config; see also [`2026-09-27-explainer-v2-design.md`](2026-09-27-explainer-v2-design.md) |
| the `cron:` lines move **closer together on game days** | **PL only** | PL_Predictor `origin/main` carries `- cron: "*/20 11-21 * * 0,1,3,5,6"` plus a daily catch-all. NFL_Predictor is still `"20 */3 * * *"`, CFB_Predictor `"25 */4 * * *"`, F1_Predictor `"40 */6 * * *"`, NBA_Predictor `'0 */6 * * *'`. No merged PR changed those four. |

So the supersession of explainer-v2 §3 below is in force; the cron half is not,
and the four hourly-or-slower schedules above are the current state.

**Supersedes:** §3 of `docs/superpowers/specs/2026-09-27-explainer-v2-design.md` (the
scope table that removed F1 and NBA), and the `cron:` lines in each sport's
`.github/workflows/refresh-public-snapshot.yml` — **the first, yes; the second only
in PL_Predictor.**

---

## Kevin's two asks, verbatim

- "i hope part of your plan is to finish and push the explainer changes and the ai
  features, also is this explainer going to all predictors with a fixture modal?
  it should"
- "we can keep it a cron but make them closer together on game days or just make it
  to the schedule itself if we have the time data?"

## What the measurement changed

Two of my own earlier positions were wrong, and both are recorded here rather than
quietly reversed.

### NBA was removed for F1's reason without being checked separately

§3 removed **both** F1 and NBA because "the v2 panel is specified for the three
sports whose facts carry the markets it draws". I applied that to both without
testing NBA's facts against it. Measured on `main`:

| Sport | markets in `/facts` | verdict |
|---|---|---|
| PL | `result` (three-way) | serves — correct |
| NFL | `moneyline`, `spread`, `total` | serves — correct |
| CFB | `moneyline`, `spread`, `total` | serves — correct |
| **NBA** | **`moneyline`, `spread`, `total`** | **structurally identical to NFL/CFB** |
| F1 | `win`, `podium`, `points`, `dnf` | no lines, no spread, no total |

NBA's `_markets()` is the same shape as NFL's, key for key: `model`,
`model_margin` + `line`, `model_total`, and `market_line` for the quoted book
line. Every component the v2 panel draws is fed by it. **NBA was refused on a
reason that was true of F1 and false of NBA.**

F1 is a different case and the refusal stands: `win` is a bare probability map per
driver, with no line, no spread and no total. A `KeyNumberTile` and a
`ProbabilityBar` would have nothing honest to draw. That is a panel-design gap, not
a data gap, and §6 of this plan says what closing it would take.

## The refresh cadence, as measured

`scripts/refresh_windows.py` (new, in NFL first, then the other four) derives the
window from each sport's committed snapshot rather than from a guessed range.

| Sport | build time | current cron | dense UTC hours |
|---|---|---|---|
| NFL | 4–7 min | every 3h | 00, 13, 17, 20 |
| CFB | 10–19 min | every 4h | 00–03 (Saturday slate) + evening |
| PL | 4–11 min | **20 min, 5 days, 11:00–21:59** | already fine |
| NBA | ~1 min | every 6h | date-only, no tip-off hour |
| F1 | 3–4 min | every 6h | one race every ~2 weeks |

**What is actually broken**, measured from the committed snapshots. The 17:00Z
slate is **nine** games. The snapshot committed at 17:06:37Z — six minutes after
kickoff — had **0 of 9** scored, which is correct: they were in progress. The next
snapshot, committed at 21:29:38Z, had **9 of 9** with final scores. So the real
latency is **270 minutes** from kickoff to a final score being visible in a
committed snapshot, and on this cadence a game that ends near the end of its
window waits for whatever run comes next. That is the "still a week ahead with
games left on Saturday" complaint in miniature: the week was right, the *result*
was late.

**A correction to this section's own earlier draft.** It previously read: "13 NFL
games kicked off at 17:00Z and their scores in the committed snapshot were still
`None`, five hours later. The snapshot last changed at 17:06Z, six minutes after
kickoff." Every number in that sentence is wrong — it is nine games, not thirteen;
all nine have final scores, in the 21:29:38Z snapshot; and the last change before
that was 17:06:37Z, not the last change overall. It was read from a stale
checkout. The defect underneath it is real and the measurement above is the one
to use; the retracted figures are recorded here rather than quietly replaced,
because a false measurement that has already survived one round of retraction is
worth naming. See ledger Task 40 for the rule this instance of.

**A correction to my own earlier claim.** I said PL's snapshot was "two weeks
stale" and concluded frequency was not the problem. That was wrong: I read a
*fixture date* as staleness. PL's soonest fixture genuinely is 2026-10-10 because
the league has not started, and all five snapshots had committed within 51 minutes
to 8 hours. The frequency argument stands on the NFL scores above, not on that.

**Why the window cannot be truly data-driven.** A GitHub Actions `schedule:` is
evaluated by GitHub's scheduler, which cannot read a repository file. The
achievable form fires often and exits early, which spends a runner start per check
to save nothing — the check is the cheap part. So the window is *derived* by script
and *hand-written* into the workflow, with the derivation committed beside it.

## Decisions

| Decision | Choice |
|---|---|
| Trigger | Cron, kept. Not event-driven — a kickoff is not a hook anything can subscribe to on a static VPS. |
| Cadence | 30 min inside derived windows; the existing coarse cron stays as the backstop. |
| CFB cadence | **2h, not 30 min.** Its build takes up to 19 min and calls three paid APIs; 4h → 30 min is ~8× the quota on the tightest budget. The 2h window still fixes "result unseen for hours" at a third of the cost. Revisit if the keys prove generous. |
| PL | **Unchanged.** It is the proof the pattern works — 337 jobs a week and the tightest data in the family. Its 20 min is below its 11 min build time, which risks queueing; leave it rather than "improve" it. |
| NBA / F1 | Unchanged. NBA's build is 1 minute so 6h is already tight; F1 races are two weeks apart so nothing is gained. |
| Silent failure | Add a failure check to all five. PL's 15:33Z run failed with its neighbours succeeding, and nothing alerted. A tighter cadence makes silent failures *more* likely, not less. |
| NBA panel | **Ship it.** It is market-complete and structurally identical to the two sports already served. |
| F1 panel | **No panel at all, and no AI fixture.** Kevin: "the explainer is intuitive enough". A driver's win probability is its own explanation — a model saying "Norris 71%" needs no prose, and prose over a field of twenty would be noise. So F1 keeps the **refusal**, now for a product reason rather than a data gap. |
| Quota | **PL and NFL get the most.** CFB is 2h for the reason above; PL is already 20-min and stays there; NFL goes to the derived 30-min windows. |

## Tasks

| # | Repo | Work |
|---|---|---|
| T1 | `NFL_Predictor` | `scripts/refresh_windows.py` + 14 tests; derived 30-min windows in the workflow |
| T2 | `CFB_Predictor` | Same script; **2h** windows (see Decisions) |
| T3 | `PL_Predictor` | Same script, for the record. No cron change. |
| T4 | `NBA_Predictor` | Same script. No cron change. |
| T5 | `F1_Predictor` | Same script. No cron change. |
| T6 | all five | A failure check that alerts when a scheduled refresh fails. Not a silent no-op. |
| T7 | `predictor-hub` | **Serve `nba`.** `SERVED_SPORTS` becomes `("pl", "nfl", "cfb", "nba")`; rewrite `test_unserved_sport.py` to refuse `f1` only, and add the tests that prove `nba` now answers. |
| T8 | `NBA_Predictor` | Re-add `api/explain.py` and wire `GameSummaryPanel` — the mirror of what the F1 removal did, for the sport that should not have been removed. |
| T9 | `predictor-hub` | The v1→v2 panel branch deleted; the panel is v2-only. **Last**, so `main` stays green throughout. |
| T10 | `predictor-hub` | `sport_api_f1` becomes dead once nothing reads F1; remove it and the env var, keeping `sport_api_nba`. The refusal list drops to one entry, which is the point — a refusal list nobody can read at a glance is a list that quietly stops being maintained. |

T1–T6 are independent per repo. T7 must precede T8. T9 waits on T7 and T8.

## §6 — why F1 gets no AI fixture, and what would change that

The original concern was data: F1's `win` market is a probability per driver, with
`podium`, `points` and `dnf` alongside, and no line, spread or total to disagree
with. `KeyNumberTile`'s model-vs-line pair would have nothing to show and
`ProbabilityBar`'s two-outcome split does not describe a twenty-driver field.

Kevin's answer to that was that the gap is not worth closing: **"the explainer is
intuitive enough"**, and the AI fixture should exist only for PL, NBA, CFB and
NFL. That is right for a reason worth writing down — a win probability *is* the
explanation. A model that says "Norris 71%" has said the whole thing; adding
"because his recent qualifying pace has been strong" is the model restating its
own input in longer words, which is the failure mode this product exists to avoid.

So F1 keeps the refusal, and it is now a **product decision on the record** rather
than a data gap. The `sport_api_f1` configuration and env var are removed in T10
so the dead half is gone.

What would change this: if F1 ever gains a quoted market (a book price for a
driver to beat), there is a disagreement to explain, and a field list rather than a
match panel becomes worth building. That is a new component, not a configuration
of an existing one.

## Out of scope

- Any change to what the model is asked to write, or to the validator.
- Rebuilding the five sports' market builders.
- Making the refresh event-driven off kickoff. Nothing on a static VPS observes
  kickoff, and the derived cron is what the measurement supports.
- The odds feed. Unchanged and still unwired.
