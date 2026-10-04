# Fixture insight design (spec, 2026-09-30)

**Status: partially implemented.** Corrected 2026-10-04 — this said "SPEC ONLY —
nothing here is implemented" after §H phases 0–2 had shipped on every surface.
Checked 2026-10-04 against merged PRs (`gh pr list --state merged`, all seven repos):

| §H phase | state | merged PRs |
|---|---|---|
| 0 — box-score team split (§E) | shipped | Sports_Predictor #20 |
| 1 — instant block + de-duplication (§A) | shipped, all five surfaces | hub #52, Sports #22, NBA #17, PL #35, F1 #22 |
| 2 — player's top calls (§C) | shipped, then simplified | hub #63, #72, #69; Sports #24, #25; NBA #22, #25; PL #38, #40; F1 #26 then **withdrawn** by F1 #28 |
| 3 — player news (§D) | partial | NBA #23 (Day-To-Day), NFL #24 (injury gate). No merged PR found for CFB, PL or F1 news rows. |
| 4 — insight rewrite (§B + validator rule) | not started | no merged PR found |

F1's phase-2 rows shipped in #26 and were removed again in #28, so F1 has no
"Model's top calls" block; the spec's §C row for F1 no longer describes the site.

**Superseded in part** by
[`2026-10-01-fixture-signals-design.md`](2026-10-01-fixture-signals-design.md),
which re-specs the signals layer (`trust` / `line_gap` / absence / `post_game` /
AI "so what") against measured data. Its phases 1–4 are separate work with their
own status line; §H phase 4 above and that spec's phase 4 are not the same task.

One design system for all five surfaces
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

Measured at (origin/main SHAs, fetched 2026-09-30): predictor-hub
9054c6a, PL_Predictor 03040e3, F1_Predictor 07305b0, NBA_Predictor
22b6857, Sports_Predictor 8bdb307, NFL_Predictor 6beeb98,
CFB_Predictor c6bb22a. Every claim below names the file it was read
from; the first draft of this section cited stale checkouts for NBA
and was corrected on review — that is why the SHAs are recorded.

The reviewer's live findings stand, with three corrections from code:

1. NBA **has an explainer**: NBA#14 (ec338c0, merged 09-29) mounts
   `FixtureExplainer` with the AI button in `GameDetailModal.tsx:304`,
   passing `extras={{ tiles, segments }}` only. What NBA truly lacks is
   the verdict line, the timing badge (it already computes
   `pick_timing: rebuilt` for its flow bundle at `GameDetailModal:177`
   and words it in `PregamePick`, but renders no StatusBadge), and the
   record/players extras. "Like NBA does now" holds for instant tiles
   only.
2. NBA's player box score **is team-split** (`PlayerBoxScore.tsx:89:
   "split down the middle by team", via `splitByTeam`). Its gap is the
   Away/Both/Home filter, which does not exist there either. §5
   corrects this: phase 0 is Sports only.
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
| NBA | verdict + record added to the existing instant tiles; timing badge once NBA promotes its flow `pick_timing` to the panel | tiles stay; PregamePick prose is replaced by the badge, not repeated beside it |

The instant block must look complete before the AI button is pressed:
badge → verdict → tiles → bar → record, then the button with a promise
line beneath it naming what the AI adds — "AI read: model vs line,
trends, who's out" — so the block reads as the finished facts, not as
a panel waiting to load. The promise line is static site copy, not a
model output, and it never mentions a figure.

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

> **Amendment, Kevin 2026-10-01 — supersedes "every row carries provenance" in this section.**
> The best calls are a pop-out of the player and the prediction, nothing else: three ranked rows per
> category, the player and team, one figure (a percentage with a thin bar for a probability, a plain
> number for a projection). No per-row record, Brier, calibration, "uncalibrated", MAE or "no error
> estimate" prose. The honesty rules that remain are enforced in code, not in row text: an out player
> is never ranked, a projection is never drawn as a percentage, at most three rows per category.
> What the old provenance said is not lost: the `trust` signal (fixture-signals-design) is where a
> reader learns how much a number can be relied on.

Name: "Model's top calls". Never "lock", "guaranteed", "best bet"
(validator banned-word list grows accordingly). Ranked by the model's
own number within lists of **exactly three rows** per category — three
when three are available, fewer when fewer are (never padded, never a
fourth), so "top-3" in the mocks means a cap and not a quota (PL goals
| shots; NFL/CFB
TD | passing | rushing | receiving yards; NBA points | rebounds |
assists | threes). Every row carries a visual, built from the real
components: probability rows get a share bar, projection rows get a key
number with its ± margin. Every row carries provenance:

| sport | row = market + model number | record shown |
|---|---|---|
| PL | anytime goal/assist/G+A prob (Platt-calibrated direct arm); shots/SOT expectations | scorer hit-rate + Brier where ledger exists; shots rows say "no graded record yet" |
| NFL | anytime-TD prob (uncalibrated) + yardage projections | TD bucket hit-rate (50–60/60–70/70%+) as calibration context; yardage MAE as ± context |
| CFB | same as NFL minus targets (structurally absent) | same ledgers; every row flagged "no availability check" (no injury/depth feed) |
| NBA | points/rebounds/assists/threes projections, labelled "projection, not a probability" with ± in-sample MAE; one category per list, never mixed | shipped in phase 2 as projections (decision 6 reversed), gated on the §D availability wiring in the same phase; the aggregate endpoint + probability layer is a later upgrade, not a gate |
| F1 | p_win/podium/points/DNF + quali markets per driver | per-market Brier/hit-rate/avgProb; no H2H or fastest-lap (the model cannot price them); no driver-news column (session state only) |

What "confident" means is stated per row: a probability for PL
scorers/NFL TD, a bucket rate for uncalibrated arms, a projection ±
MAE for yardage/NBA. No odds feed exists anywhere, so no row ever
claims an edge vs a price. **PREMISE CORRECTED 2026-10-04:** four repos do
ship an odds client, and only CFB's cache is populated in production — see
`2026-10-01-fixture-signals-design.md` §11. The RULE stands unchanged: no row
may claim an edge vs a price, because that prohibition is about deriving an edge
from a probability, not about a feed being absent.

### D. Player news

Reuse of the Sep-28 mechanism (alias table → cache key carries newest
matched date → prompt leads with injury, date it, else say nothing),
extended with player entries and pick-relevance:

| sport | source | status |
|---|---|---|
| PL | FPL status/news (gates predictions today) + ESPN confirmed XI in the lineup window | surface what already gates; dated, attributed |
| NFL | official injury reports + depth-chart flags (gate props today) | surface what already gates; dated by week |
| NBA | official injury report + ESPN (exist, unwired to props) | wire in **in phase 2, in the same phase as NBA picks** — a listed player is removed from the ranking, never kept |
| CFB | none exists | picks carry the no-check flag; building a feed is out of scope |
| F1 | session state only | no news surface; weather stays a session input |

Rules: a player who is out is never recommended. **Removed wins over
flagged** — the earlier wording here ("the pick moves or is flagged")
contradicted the rule added with #50, and "moves" is the weaker word:
an out player leaves the ranking entirely and appears once below the
lists as an attributed line, never inside a list with a flag on him.
Doubtful **demotes** (he may stay ranked, lower). No news → the block
says nothing at all (no "no news" row).

**An out player is removed from the ranking, not merely marked in it.**
He does not appear in any top-3 list, with any bar, tile or bold number;
he appears once, below the lists, as an attributed line ("Out: J.
Jacobs · official injury report · GB · week 6"). A list that keeps an
out player — even labelled — contradicts this spec's own rule, so the
ranking is computed over available players only. Every sport's picks
PR includes the test for this: seed an out player, assert he is absent
from the list and present exactly once in the out line. NBA may not
ship picks in phase 2 without this gate already in the same phase; if
the gate cannot land there, NBA picks move to phase 3 whole.

### E. Box-score team split (preceding small PR)

Reviewer's preference stands: ship this first, as its own PR
(Sports PR #20, in review). Scope:

- Sports: the planned Away/Both/Home filter (default Both), grouped by
  team then position, team totals once — exactly plan-a A4, reaffirmed,
  not rewritten.
- NBA: already team-split; no work here.
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

0. Box-score split small PR (§E) — Sports only (PR #20, **merged** 2026-09-30).
1. Instant block + de-duplication (§A) — biggest win, no model cost.
   The block must look complete before the AI button is pressed, and
   the button carries a static promise line naming what the AI adds
   ("AI read: model vs line, trends, who's out") so the facts never
   read as a panel waiting to load.
   One PR per repo per phase; a parity test per sport asserting the
   block renders from the bundle with the network blocked.
2. Player picks (§C) — including NBA as projections ± MAE, **with
   the §D availability gate wired in the same phase**. One category per
   list. Out players leave the ranking (see §D).
3. Player news (§D) — remaining sports.
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
| plan-a box-score/track-record | A4 team filter + dedup rule | REAFFIRM for Sports (phase 0, PR #20 in review); NBA already split, filter not required |
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
| 6 | NBA player picks ship in phase 2 as projections ± MAE, labelled "projection, not a probability" (reversed on review — Kevin wants them now), **but not without the §D availability gate in the same phase** | wait for the aggregate endpoint + prob layer | hold NBA rows until the prob layer lands |
| 7 | Box-score split ships as a preceding Sports-only small PR (PR #20); NBA needs no grouping work | fold into phase 1, or add an NBA filter too | merge into phase 1 PRs |
| 8 | F1 insight stays per-race (table + ribbon unchanged), no fixture panel | build F1 a fixture-style panel | extend phase 1 to F1 panel |
| 9 | Finished flow keeps score/result sentences; pre-game flow prose is deleted | keep flow as the no-AI fallback | restore sentences in phase 1 |
| 10 | Player-news freshness reuses the one-write-per-day bound | separate cap for player news | new cap rule in phase 3 |

## 6. Mocks

`packages/predictor-ui/harness/insight.html` (+ `insight-narrow.html`
for 390px), rendered from the real components for the instant block and
explicitly-marked proposal markup for the new pieces. Shots in
`harness/shots/insight/` (desktop + `-390`):

1. `nfl-rebuilt` — rebuilt instant block. 2. `prebutton` — complete
   pre-button state: instant block + the real SummaryButton + the static
   promise line ("AI read: model vs line, trends, who's out").
3. `pl-pre` — three-way + market row. 4. `f1-unknown` —
   reduced block + session badge. 5. `nba-now` — tiles + verdict +
   record. 6. `no-pick` — numbers without a claim. 7. `news` —
   present (attributed flag, pick moved) vs absent (nothing renders).
8. `callouts` — two proposal rows with delta visuals, every figure
   derived from the one `FIX` object in `insight.tsx` (model −6.1 vs
   line −4.5, gap 1.6).
9. `picks` — proposal top-3 per category with visuals from the real
   components (share bars for probabilities, key numbers with ±
   margins for projections), provenance per row.
10. `boxfilter` — proposal Away/Both/Home over the real BoxScore.

One fixture, enforced by code, not by care: every figure in every mock
is read from `packages/predictor-ui/harness/fixture.ts`, keyed BY
CATEGORY (a player has a TD probability and a yardage projection; they
are different numbers, and mixing them is how the mock once printed
Robinson's 96 rush yards as a "9600%" TD probability — caught by
re-shooting the page, not by reading the code).
`assertFixtureConsistency()` runs when the mock loads and throws,
naming every problem: a row whose figure differs from the object, a
row of the wrong kind for its category, an out player who is ranked,
a row under a heading that does not list him, and the same player
carrying two numbers in two mocks. `harness/fixture.test.ts` (12 tests)
proves each guard actually throws, using the exact bugs the review
found — 84-vs-96, Jacobs ranked, a rebounds row under "NBA points".

Reproduce: `cd packages/predictor-ui/harness && npm install &&
npm run typecheck && npm run build && npm run preview`
(shot with a desktop viewport and the 390px iframe page).
