# Fixture insight design (spec, 2026-09-30)

SPEC ONLY — nothing here is implemented. It becomes work only when the
reviewer approves this file. One design system for all five surfaces
(PL, NFL, CFB, F1, NBA); per-sport differences are listed, not forked.

## 1. Goal

The AI summary currently restates what the fixture detail already shows.
After this plan, the fixture detail and the AI summary do not overlap:

- the **facts block** is instant and does all the "what" (badge, tiles,
  bar, verdict, record) on every site, with no button and no request;
- the **AI part** is for what needs interpreting — 2–3 scannable callouts,
  something that pops, not paragraphs;
- **player picks** come from each sport's own player model, with their
  probability/projection and their track record where one exists;
- **player news** (out/doubtful/returning) changes or flags the picks.

Mode is Operate: fans on phones, seconds to understand. Bettors comparing
with odds get edge framing, never wagering advice.

Non-goals: no new model training, no odds feeds, no calibration research,
no redesign of anything that is not listed in §4.

## 2. Measured starting point (corrected)

The reviewer's live findings stand, with three corrections from code:

1. NBA has **no explainer at all** — no button, no panel, no `/facts`
   second source. Its tiles are instant because there is nothing else.
   "Like NBA does now" is true of the tiles; NBA still needs the verdict
   line, the timing machinery, and the whole AI side, which is new work.
2. NBA's player list is a **single mixed list**, not a team split. The
   claim "NBA and PL split by team" is half wrong: PL splits (two-column),
   NBA does not. §5 corrects this.
3. The 68-vs-72 shape is structural: site tiles come from today's model
   response (`GameSummary`/`FixtureDetail`), AI prose numbers come from
   the explainer's `/facts` (frozen pre-kickoff card on started fixtures).

## 3. Design

### A. Instant facts block, no button, every site

Composition, in order: timing badge → verdict line → key-number tiles →
split bar → record strip. All from the site bundle via `panelFacts`
(zero requests), rendered by the existing components. Per sport:

| sport | instant block | what's new vs today |
|---|---|---|
| NFL/CFB | rebuilt/pre-kickoff/nopick badge + verdict + 3 tiles + 2-way bar + record | everything currently behind the button moves out of it |
| PL | same + 3-way bar + market row when implied covers | same move; record/players extras get passed for the first time |
| F1 | session/unverified badge + pick + win prob + record; no tiles, no market bar (unchanged reduced rule) | badge + record become instant; table and ExplainRibbon untouched |
| NBA | verdict + tiles + bar + record; no badge until NBA tracks pre-tip picks | verdict line + record are new; tiles stay where they are |

One source of truth per number: every rendered figure comes from the
site bundle. The AI insight (part B) is **forbidden from stating any
figure the block already renders** — enforced by the validator (§B).
The 68-vs-72 contradiction is fixed at its root: there is no second
number on the page to contradict the first.

De-duplication (what is deleted, per surface):

| surface | removed | kept |
|---|---|---|
| FixtureFlow prose (PL/NFL/CFB) | `Win probabilities: …`, `The model picks …`, `The market's line is …`, pick-timing sentence | in-play/finished score + result sentences (unique info); F1 tier/state line |
| Sports "Match Markets" | per-market prob rows repeating tiles | nothing (the graded edge view lives in the insight callouts) |
| PL "Match result & goals" MarketBars | prob-vs-implied rows repeating tiles/bar | heatmap, head-to-head, predicted margin/shots rows |
| NBA markets table | — (kept: bookmaker odds + edge + graded result are additive, not repeats) | whole table |
| PostMatchReview / verdict badges | — (kept: they judge the stored pre-kickoff card, which the block does not) | all |

### B. AI insight: callouts, not paragraphs

Shape: 2–3 callout rows. Each row = a small visual (delta chip, edge
bar, W–L record) + one line ≤ 12 words + expandable evidence line
(source + n). The model supplies words and ordering only — the v2
principle, unchanged. Nothing already on the page; nothing without a
fact behind it; no invented injuries.

Validator non-overlap rule (new, enforced): a factor is rejected when
every figure it states already appears in the rendered facts block,
**unless** it adds a comparison (model vs line), a trend (last-N with
n), or a cause (news-backed). A bare restated figure is a validation
failure and the service falls back to the template — which, for insight,
renders the block alone with no callouts rather than invented prose.

Interpretation menu per sport (only where the facts carry it):

- matchup edge vs the market (spread/total panels, PL result + goals);
- where the model disagrees with the line, with the gap in points;
- last-N from the stored pre-kickoff record, always with n;
- availability swing (only with a dated news item, §D);
- rest/travel/weather angle (only if the facts carry it — otherwise the
  row must not exist).

### C. Best player picks, per sport, honestly labelled

Name: "Model's top calls". Never "lock", "guaranteed", "best bet"
(validator banned-word list grows accordingly). Ranked by the model's
own number. Every row carries provenance:

| sport | row = market + model number | record shown |
|---|---|---|
| PL | anytime goal/assist/G+A prob (Platt-calibrated direct arm); shots/SOT expectations | scorer hit-rate + Brier where ledger exists; shots rows say "no graded record yet" |
| NFL | anytime-TD prob (uncalibrated) + yardage projections | TD bucket hit-rate (50–60/60–70/70%+) as calibration context; yardage MAE as ± context |
| CFB | same as NFL minus targets (structurally absent) | same ledgers; every row flagged "no availability check" (no injury/depth feed) |
| NBA | points/rebounds/assists/threes projections | "no graded record yet" until the aggregate endpoint lands (phase 3 prerequisite); no probabilities shown because the model outputs none |
| F1 | p_win/podium/points/DNF + quali markets per driver | per-market Brier/hit-rate/avgProb; no H2H or fastest-lap (the model cannot price them); no driver-news column (session state only) |

What "confident" means is stated per row: a probability for PL
scorers/NFL TD, a bucket rate for uncalibrated arms, a projection ±
MAE for yardage/NBA. No odds feed exists anywhere, so no row ever
claims an edge vs a price.

### D. Player news

Reuse of the Sep-28 mechanism (alias table → cache key carries newest
matched date → prompt leads with injury, date it, else say nothing),
extended with player entries and pick-relevance:

| sport | source | status |
|---|---|---|
| PL | FPL status/news (gates predictions today) + ESPN confirmed XI in the lineup window | surface what already gates; dated, attributed |
| NFL | official injury reports + depth-chart flags (gate props today) | surface what already gates; dated by week |
| NBA | official injury report + ESPN (exist, unwired to props) | wire in: a listed player demotes/flags the pick |
| CFB | none exists | picks carry the no-check flag; building a feed is out of scope |
| F1 | session state only | no news surface; weather stays a session input |

Rules: a player who is out is never recommended — the pick moves or is
flagged, never silently kept. Doubtful demotes. No news → the block
says nothing at all (no "no news" row).

### E. Box-score team split (preceding small PR)

Reviewer's preference stands: ship this first, as its own PR. Scope:

- Sports: the planned Away/Both/Home filter (default Both), grouped by
  team then position, team totals once — exactly plan-a A4, reaffirmed,
  not rewritten.
- NBA: adopt team grouping (it has none today) reusing BoxScore groups;
  no filter until the grouping proves out.
- PL: already split; no change. F1: N/A.

### F. Honesty (unchanged, binding on all phases)

Only a pick made before the start counts; rebuilt picks are shown,
labelled, never counted; after kickoff only the stored pre-kickoff
record is used, and the surface says so. Insight callouts and player
picks on a started game use stored pre-kickoff data only — a trend with
n from the stored record, never today's rebuilt numbers. The
player-accuracy spec's prohibitions bind: no team-total tile from
roster sums, no number the system cannot compute (§5.1–5.2 there).

### G. Trigger, budget, cost

The insight stays on demand (button): one generation per fixture per
news-day, same cache key / cap / refusal rules as today. The template
path renders the same layout from facts alone (one renderer). Per-open
cost is one model call; the instantaneous block costs nothing. Player
news adds a second freshness trigger bounded exactly like team news
(one extra write per fixture per day, only on genuinely newer news).

### H. Phases (in this order)

0. Box-score split small PR (§E).
1. Instant block + de-duplication (§A) — biggest win, no model cost.
   One PR per repo per phase; a parity test per sport asserting the
   block renders from the bundle with the network blocked.
2. Player picks (§C; NBA aggregation endpoint first).
3. Player news (§D).
4. Insight rewrite (§B + validator rule).

Parity test per sport per phase: same assertions, five repos — the
block from the bundle offline; picks with provenance; news flag
behavior; callout non-overlap against the real template.

## 4. Amendments to existing specs

| spec | clause | amend / extend |
|---|---|---|
| explainer-v2 | §6 panel items 1–5, §7a/7b mocks, §8 template path | AMEND (instant block restructure + dedup) |
| explainer-v2 | §4 on-demand trigger, skeleton, button gating | AMEND (instant scope, no button for facts) |
| explainer-v2 | §5a/5b contract, §13d/f budget+deploy | EXTEND (callouts render the same contract; same cap/key) |
| explainer-v2 | §6 mini-list, §11/§12 keep-vs-drop, §13e no-band | AMEND mini-list → full picks (§C); EXTEND record/band rules |
| explainer-v2 | §5c `players[]` shape | EXTEND (ranking layer on the same shape) |
| Sep-28 flow/trigger/news | flow-sentence rules, button-gated summary, F1 "triggered only" | AMEND (richer instant flow; callouts replace prose-swap) |
| Sep-28 flow/trigger/news | alias→key-date→prompt news mechanism, bounded cost | EXTEND (player entries + pick-relevance) |
| plan-a box-score/track-record | A4 team filter + dedup rule | REAFFIRM for Sports (phase 0); EXTEND grouping to NBA |
| plan-a box-score/track-record | B8 two-record honesty, weekly rows | untouched, still binding |
| player-model-accuracy | §5.1–5.2 prohibitions, Layer 3b counting | untouched, binding constraints on §C/§F |

## 5. Decisions (Kevin away — taken here, all reversible)

| # | decision | alternative considered | reverse by |
|---|---|---|---|
| 1 | AI never states a rendered figure (validator-enforced) instead of reconciling two pipelines | unify /facts and site bundles on one number at serving time | relax the validator rule to allow equal figures |
| 2 | Pre-kickoff gets a quiet timing chip ("Made before kickoff") | no chip for the normal state | delete the chip; badge set stays rebuilt/unverified/nopick |
| 3 | NBA markets table stays whole (odds+edge+grading are additive) | strip it as duplication | remove in phase 1 |
| 4 | Uncalibrated arms show bucket hit-rate / ±MAE instead of hiding | hide everything uncalibrated | drop the context column |
| 5 | CFB ships picks flagged "no availability check" rather than waiting for a feed | hold CFB picks until a feed exists | remove CFB rows |
| 6 | NBA player picks wait for the aggregate endpoint + a prob layer | show raw projections as "picks" now | ship projections-only rows |
| 7 | Box-score split ships as preceding small PR, NBA grouping included | fold into phase 1 | merge into phase 1 PRs |
| 8 | F1 insight stays per-race (table + ribbon unchanged), no fixture panel | build F1 a fixture-style panel | extend phase 1 to F1 panel |
| 9 | Finished flow keeps score/result sentences; pre-game flow prose is deleted | keep flow as the no-AI fallback | restore sentences in phase 1 |
| 10 | Player-news freshness reuses the one-write-per-day bound | separate cap for player news | new cap rule in phase 3 |

## 6. Mocks

`packages/predictor-ui/harness/insight.html` (+ `insight-narrow.html`
for 390px), rendered from the real components for the instant block and
explicitly-marked proposal markup for the new pieces. Shots in
`harness/shots/insight/` (desktop + `-390`):

1. `nfl-rebuilt` — rebuilt instant block. 2. `nfl-pre` — pre-kickoff +
   quiet chip. 3. `pl-pre` — three-way + market row. 4. `f1-unknown` —
   reduced block + session badge. 5. `nba-now` — tiles + verdict +
   record. 6. `no-pick` — numbers without a claim. 7. `news` —
   present (attributed flag, pick moved) vs absent (nothing renders).
8. `callouts` — two proposal rows with delta visuals.
9. `picks` — proposal table with provenance per row.
10. `boxfilter` — proposal Away/Both/Home over the real BoxScore.

Reproduce: `cd packages/predictor-ui/harness && npm install &&
npm run typecheck && npm run build && npm run preview`
(shot with a desktop viewport and the 390px iframe page).
