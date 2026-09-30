# What we did today (27–28 September 2026) — a plain-language guide

**Who this is for:** anyone who wants to know what changed in the Predictor player models
today and why, without reading code. If you are an engineer picking up the work, read
[the handoff](handoff/2026-09-28-player-model-remediation-handoff.md) instead — it is
denser and more useful. If you want the full decision record with every number, read
[the ledger](ledgers/2026-09-28-player-model-accuracy-remediation.md).

---

## The short version

Someone pointed out that the **total yards** number in the college-football player panel
was badly wrong. Chasing that turned out to be the thread that unravelled a much bigger
problem: across all four of our sports apps, our tests were checking that numbers *came
out* — never that they were *right*. So wrong numbers could sit in production, fully
green, indefinitely.

We found and fixed a lot of them. We also **retracted two claims we had made earlier in
the same session**, because measuring them properly showed they were wrong.

Nine pull requests merged. One is still finishing its automated checks.

---

## How a wrong number gets shipped: the same mistake, four times

This is the most important thing to understand, because it is not a bug — it is a habit.

A test says *"this function returns a number"*, and the number comes out, so the test
passes. But nobody ever asked *"is it the **right** number?"* That gap let all of the
following through, each caught only by accident:

**1. We added up the wrong things.** To check our player yardage matched the team's
official yardage, the check joined on *(season, week, team)*. But a team can play twice
in a week, and the college season declares **every bowl game as "week 1"**. So in one
case we compared a single game's total against several games' players added together, and
produced a claimed "1,620 yards" for a game that had 443.

**2. A "make sure the data is there" check that could never fail.** We wanted to be sure
both halves of a total were actually present before trusting it. But the spreadsheet
library treats a column of all-missing values as zero, so the check always saw two real
numbers and never complained. The result: a *partial* total that looked *complete*. That
is worse than a missing one, because a missing one shows up in a count and a partial one
does not.

**3. A function that had never actually run on real data.** Our tests all built their own
tiny fake spreadsheets. The real spreadsheet column was named differently. So the function
was wrong in a way no test could see — and it took 42,190 real rows before it complained.

**4. A quality check that was mathematically incapable of passing.** Three of our four
apps had a "lint" step that ran a tool which was never installed. So the check was red on
every single push, permanently. Once we installed the tool, it immediately found four real
bugs — including three where code said a type was `"Path"` without ever importing `Path`.

**The pattern is the point.** In every case the code did what it was told. The failure was
always in what nobody asked.

---

## What we changed, in plain terms

### College football (CFB)

- **The yardage check now compares the right games.** Matching on a unique game ID instead
  of a week. Before: 58 of 272 games matched exactly. After: 161. The typical error went
  from **336 yards** to **0**.
- **We recovered a third of the data we were throwing away.** The check demanded a "week"
  it never used, and the process that supplied weeks discarded any game missing from the
  schedule — which silently threw out every game against a smaller (FCS) opponent. Real
  games, real box scores, gone because of a scheduling filter. We now reconcile **356
  games instead of 272**, at the same quality.
- **We built the missing piece.** There was a function to download team box scores that
  nothing called. It now runs: **351 API calls, 42,190 team-game records across 22
  seasons.**
- **A missing number was being recorded as a prediction.** If a game had a betting spread
  but no probability attached, the system recorded that we'd predicted a side — and
  counted it in the track record. It was inventing a call the model never made, in both
  directions. This was the same bug in both football apps.

### NFL football

- **A real quarterbacks' passing yardage was being replaced by a fixed number.** A bug I
  introduced earlier the same session meant a player with one game got a blank record,
  which got filled with zeros, which is the input the model was never trained on. The
  model then returned its "average" answer: **62.592 passing yards, to 430 of 880 real
  players** — 49% of them. Fixed, and the regression I caused is documented rather than
  quietly removed.
- **A schedule detail was read from the wrong year.** Because the lookup took the first
  match found, and the app loads eight years of history oldest-first, a 2026 game could be
  told a team was playing a divisional game because they did in **2019**. I introduced
  this one too, by replacing a hardcoded zero with a lookup that then had to be right.
- **The app has a "test gate" now.** It had none that could pass.

### Premier League (PL)

- **New research: how strong is the team you're playing?** Our player model knew a
  player's own form and nothing about their opponent. We added opponent defensive
  strength, verified that the version used in training and the version used when
  predicting a live match agree *exactly*, and it **passed our promotion bar on all four
  test folds**.
- **We tightened the bar for promoting a model, in code.** Previously a change could win
  on a *single* lucky week and be declared an improvement. Now it must win on most folds
  *and* beat the measured noise. The noise figure has no default — a default would let
  you set the bar after seeing the result, which is the exact mistake being guarded
  against.
- **The most important research finding was a negative one.** We measured how much
  apparent improvement is just luck. Answer: **the difference between two models on one
  week is about the same size as the noise.** So most of what had looked like model
  progress in earlier work was noise being read as signal. That is why we now require
  multiple folds.
- **A "NaT" bug that peeked at the future.** A fixture with a missing date was quietly
  pulling in matches that hadn't happened yet.

### Sports Predictor (the shared app)

- **The number the user complained about is gone.** It was being calculated by adding up
  individual players, which produces a figure that isn't any real quantity — 800–1,400
  yards against a real team's ~300–450. We **split it into its parts and labelled each
  one** rather than deleting it, so nothing real was thrown away.
- **This app had no automated testing at all.** Its only workflow deployed code. A broken
  build could be merged with nobody noticing.

---

## Two things we got wrong, and said so

We think these matter more than the fixes, so they are written into our records rather
than corrected in place.

**We published a tolerance we had measured on one week of one season.** We wrote "95% of
games reconcile within 10 yards, worst case 35". Measured across all 22 seasons, it is
**92.4%** and the worst case is **337 yards**. One week is not a sample of twenty-two
seasons.

Worse, we then explained *why* the gap existed — and that explanation was also wrong. We
blamed a data quirk. When we checked the raw downloaded data row by row, we found our own
code was at fault: the source reports "0 total yards" for 48 real games, and we were
accepting that zero as a real measurement. So the most alarming number in our own
correction — "the worst case is 550 yards" — was an artefact of our own bug. With it
fixed, the real worst case is 337.

**We described a mechanism we had never checked.** We wrote, confidently, that a particular
module was responsible for an empty data file. It wasn't — that module isn't even used on
that code path. A different module was doing it. The *symptom* was real and verified. The
explanation was a guess written down as a finding.

Both came out of the same review round that found the bugs. That round also produced the
sharpest lesson of the day: **of the four false claims we made, three were one search
away from being caught, and none was.**

---

## What we did about the testing gap

The fix is a rule, not a feeling: **for every new test, break the code on purpose and
confirm the test fails.** If it still passes, the test is decoration.

This caught things intuition would not. In one case a test we had just written **passed
while the fix it was written for did nothing** — one of the two halves simply had no
test. In another, a test passed even after we deleted the entire behaviour it claimed to
protect, because it had been written against a fake spreadsheet that didn't resemble
reality.

We also found we had made the same operational mistake three times over: adding a timeout
to a job that *warms a cache*. A cold run took longer than the timeout, so it was killed,
so it never saved the cache, so the next run was also cold. The timeout we'd added to
prevent a hang had made the gate permanently red.

---

## Where things stand

| | Status |
|---|---|
| NFL Predictor | merged, 245 tests passing |
| CFB Predictor | merged, 272 tests passing |
| Sports Predictor | merged, 189 tests passing |
| PL Predictor | 489 tests passing locally; automated checks still running |
| Documentation | plan, design, ledger and handoff in review |

**We also checked the work against other agents' changes**, since several landed while we
were working. We re-ran every test suite against the current main branch in three apps —
all green — and simulated merging their open pull requests to confirm nothing of ours
breaks. Their branches are cut from an older main, which is worth mentioning to whoever
merges them.

---

## What still needs a decision (not more work)

1. **NFL: games are being recorded after kickoff.** The app scales down to zero when idle,
   so the next save can land *after* the game started — meaning the pre-game prediction it
   needs was never captured. This is the reason player-prop accuracy reads zero, and
   **fixing the missing data file would not help**; this is the real blocker. It costs
   money to keep the app awake, so it's a call for you.
2. **CFB: production starts with an empty cache.** Our 351-call download filled a local
   cache that isn't deployed. Production still starts cold.
3. **PL: the test gate depends on three outside services.** If one is down, the gate goes
   red for reasons unrelated to the change.

---

## The one-line version

A wrong number in a player panel turned out to be the visible end of a habit — tests that
checked numbers *existed* rather than numbers were *right* — and today we fixed nine
specific instances of it across four apps, retracted two of our own claims that didn't
survive proper measurement, and wrote down a rule that would have caught most of them.
