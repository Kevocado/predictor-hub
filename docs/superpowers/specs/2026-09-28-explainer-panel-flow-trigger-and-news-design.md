# The explainer panel: an instant flow, a triggered AI summary, and team news

**Date:** 2026-09-28
**Status:** **implemented and live** on all four sites; awaiting Kevin's review of the
*design* only. Corrected 2026-09-29, when this said "awaiting Kevin's review" with no
hint that the work had shipped — a reader could not tell an unimplemented proposal from
one that is running in production. See "Status, measured" below for what shipped and
what has not.
**Supersedes:** nothing. **Reverses:** the F1 refusal in
`docs/superpowers/specs/2026-09-25-phase3-4-datahub-explainer-design.md` §3 and the
ruling at ledger Task 37, on the reasoning given in §7 below.

## Status, measured 2026-09-29

The table further down records the state on 2026-09-28 and is left as written,
because it is the evidence for why the spec exists. This section is the current
state, and every row was checked rather than recalled.

| site | panel mounted on `main` | route to the service | served by the service |
|---|---|---|---|
| PL | `FixtureModal.tsx` | own FastAPI proxy | yes |
| F1 | `SessionTimelinePanel.tsx` | own FastAPI proxy (`F1_Predictor#16` pending) | yes |
| NBA | `GameDetailModal.tsx` (`NBA_Predictor#14`, merged) | own FastAPI proxy (`NBA_Predictor#9`, merged) | yes |
| NFL + CFB | via Sports' `GameDetailModal.tsx` | Caddy `handle_path /api/explain/*` | yes |

Checked by: `git grep FixtureExplainer origin/main` in each repo, excluding the
vendored `predictor-ui/` tree — the file that matters is the one a SITE mounts,
not the one the package ships. And by calling `/api/explain/<sport>/<id>` on each
of the four hosts: all four answer `502 The summary service is not available.`
for an unknown id, which is the fixed message the proxies return. A 502 proves
the route exists and reached the service; a 404 would have meant no route.

**F1's proxy is the one still open** — `F1_Predictor#16` is unmerged, so the F1
row above describes `main` plus that PR. The service already serves `f1`
(`SERVED_SPORTS`); the route from F1's site was the missing half.

**What this spec did not deliver, and still has not:**

- **Reasoning is now explicitly off** on every request, and a truncated answer is
  counted as its own `cut_off` failure kind rather than as a bad response
  (`predictor-hub#36`, deployed). Neither was in this spec; both came from the
  first live summaries.
- **Prose naming a market the facts do not quote is now rejected**
  (`predictor-hub#37`, open). The first live NBA summary claimed "the market
  line of BOS by 1.9" for a game with no book quote at all, and every
  number-level rule passed it because the number was real.
- F1 remains a **reduced** panel by design — no line, so no spread or total
  factors. That half of the original refusal still stands.

## The problem, measured

**An empty panel is a dependency failure, not a missing feature.** On `origin/main`
on 2026-09-28:

| site | fetches `/api/explain` | route to the service | panel mounted |
|---|---|---|---|
| PL | yes | its own FastAPI `api/explain.py` | yes, in `FixtureModal` |
| NFL + CFB | yes | Caddy `handle_path /api/explain/*` → `rewrite * /explain{uri}` | yes, in `GameDetailModal` |
| NBA | **no** | **no proxy on `main`** (NBA_Predictor#9, open) | vendored, unwired |
| F1 | no | — | none; the service refuses `f1` |

So three of the four sites have the whole path in code, and the panel is still
empty for a reader. Whatever is failing is on the far side of that path — most
likely the explainer container was never deployed to the VPS, or
`EXPLAINER_UPSTREAM` is unset. **A design that depends on that service being up
inherits that failure**, which is the argument for §2.

**Standardisation is currently false.** PL and Sports each carry their own
`panelFacts` / `FixtureSummaryPanel`, so the two panels have already diverged and
will keep diverging. "Standardised across the four sites" is not achievable while
each site owns a copy.

**No reader is told about team news.** The service already fetches dated ESPN
headlines for all five sports (`news.py`) and passes them to the model. Three
things stop that becoming the context Kevin wants:

1. **The team matching misses.** `_news_terms` (`service.py:46`) splits the
   fixture title on ` at ` / ` v ` / ` vs ` / ` @ `, so `"MIA at BOS"` yields
   `["MIA", "BOS"]`. ESPN's headlines say *"Chicago Bears"*. PL is worse:
   `MUN` and `ARS` against *"Manchester United"* and *"Arsenal"*.
2. **News is deliberately excluded from the cache key** (`service.py:156`):
   *"News feeds the first write-up but isn't in the key: a fresh headline alone
   must not cost another generation."* So a summary written Tuesday saying a
   quarterback is starting is still served on Wednesday, after a midweek injury.
3. **The prompt never asks for news to be explained.** It permits `NEWS` and
   forbids inventing injuries, but does not ask the model to lead with a lineup
   change or to say what it changes for the prediction.

## Decisions

| # | Decision |
|---|---|
| 1 | The default panel state is a **flow description built client-side from facts the site already has**. No network call. |
| 2 | The AI summary is **triggered by a button**, not on modal open. |
| 3 | The flow is **state-appropriate**: pre-game, in-play and finished each say something different. |
| 4 | **F1 is un-refused** and gets a reduced panel, triggered only. |
| 5 | One shared implementation in `predictor-ui`, vendored to all five sites. |
| 6 | **Team news for NFL and PL.** The cache key carries the newest matched headline's date, so newer news regenerates a summary once. |

### Why the AI is behind a button and the flow is not

Measured on the merged branch, 200 renders of a three-market bundle:

| path | latency |
|---|---|
| template render | **median 0.0 ms, p95 0.0 ms, max 0.0 ms** |
| AI generation | up to `TIMEOUT_SECONDS` (25 s) on the service, 15 s at the site proxies |

A button in front of a 0 ms operation just hides content behind a click, so the
flow renders inline. A button in front of a 25 s operation is the correct
affordance, and it also means **nothing is spent until a reader asks** — which
matters against the 1000/day budget, where most opens are repeat views of the
same fixture.

## Previously-designed v2 work, folded in here

The v2 redesign (§11 of `2026-09-27-explainer-v2-design.md`) left three findings
"independent of the redesign" that "should not wait for it", plus two phase-4
tasks. Checked against `origin/main` on 2026-09-28:

| item | state | where it goes |
|---|---|---|
| NFL/CFB shipping two probabilities for one pick in one bundle | **done** — the moneyline is sourced from `pick_source` | — |
| the validator comparing numbers by absolute value, so a flipped spread sign passes | **done** — `validate.py` collects a `flippable` set and checks `_sign_ok`; `test_validate_signs.py:61` asserts a flipped sign is caught | — |
| **the Sports Caddy block being the only proxy of four that forwards an upstream body** | **open** — `Sports_Predictor#6`, unreviewed | reviewed and merged as a **prerequisite** (§Sequencing) |
| **remove the v1 `LegacyExplanation` shape** | **open** — still in `ExplainerPanel.tsx`, documented as *"the shape v1 returned. Still accepted, and removed in v2 phase 4"* | **PR B**, with the shared component |
| `sport_api_f1` cleanup (old task T10) | **obsolete** | T10 said remove it as dead once F1 was refused. Decision 4 un-refuses F1, so it is **required** again. T10 is dropped, not done, and the ledger's Task 37 ruling ("not dead weight") applies |

The v1 shape is the last piece of the redesign rather than an optional extra: it
exists so `main` stays green *between* phases, and every site is now on v2, so the
shim outlived the reason for it. Carrying it means a v1 body can still render —
and a v1 body is exactly the shape that carries the claims the honesty rules now
forbid. Removing it also makes `response_model` honest, since the annotation would
otherwise admit a shape nothing produces.

## Architecture

One shared component in `predictor-ui`, copied into each site by `sync-ui.mjs`
and held honest by the `predictor-ui.sync.test.ts` every site already has.

```
FixtureExplainer            the panel, two states
├── FixtureFlow             instant, local, pure function of the facts
└── SummaryButton           requests the AI prose; swaps it in on arrival
```

- **`panelFacts` moves into `predictor-ui`** as one shared adapter. PL's and
  Sports' local copies are deleted. This is what makes decision 5 true rather
  than aspirational, and it is the change that stops the two existing panels
  drifting further apart.
- Per-sport shape comes from the existing `market_shape` (`two_way` /
  `three_way`), plus one descriptor for F1. Differences are declared once.

### Data flow

```
modal opens ──▶ site renders FixtureFlow from facts it already loaded
                    (zero requests, nothing to wait for, nothing to fail)
button pressed ─▶ GET /api/explain/{sport}/{id}
                    ─▶ site route (PL/NBA/F1 FastAPI · NFL/CFB Caddy)
                    ─▶ explainer ─▶ AI prose, or the template
                    ─▶ swaps in; the flow stays underneath until it lands
```

### The two states

| state | shown when | cost |
|---|---|---|
| `flow` | default, always | none — rendered locally |
| `summary` | after the button resolves | one generation, once per fixture per news-day |
| `unavailable` | the button's request failed | none — the flow is still there, the button offers a retry |

**There is no state in which the panel is empty.** That is the whole point, and
it is what the current design gets wrong.

## What `FixtureFlow` says

State-appropriate, and **honest under the same three rules the template now
obeys** (landed in predictor-hub#17): never a figure withheld without being
said, never a "line" that is not the market's, never a claim the numbers do not
support.

- **Pre-game** — who plays, when, the model's pick, and the market's line beside
  the model's number *when a market line exists*. With no line (PL's three-way
  result, NBA before a quote is tracked, F1), it says the pick and stops.
- **In-play** — the score and the state of the game, and how it stands against
  that line *when there is one to stand against*.
- **Finished** — the result, and whether the model's pick was right.

No direction marker, no "the market disagrees" clause, no derived percentage.
Those were the defects predictor-hub#17 removed from the service's template, and
they must not be reintroduced on the client for the sake of symmetry.

## Team news (NFL and PL)

### Matching

Replace the title-split with a real resolver: take the full team name from the
facts where the sport supplies one, and otherwise map the abbreviation through a
per-sport alias table (`BOS → Chicago Bears`, `MUN → Manchester United`). An alias
miss is not a failure — it yields no news, and the flow is unchanged.

Only NFL and PL are in scope, as asked. The mechanism is per-sport, so CFB, NBA
and F1 opt in by adding entries rather than by a second code path.

### Freshness

**The cache key carries the date of the newest matched headline** — and nothing
when no headline matched, so a fixture with no news costs nothing extra.

| situation | today | after |
|---|---|---|
| summary written Tue, injury Wed | Tue's prose served | key changed → rewritten once |
| summary written today, no new news | today's prose | reused, no cost |
| no news matched for these teams | reused | reused, no cost |

The cost is bounded at **one extra write per fixture per day, and only when
there is genuinely newer news for those two teams.** That is the price of the
midweek case, and it is the price Kevin chose.

The panel shows the date of the news a summary was written from, so a reader can
judge it. The footer already carries an age; this adds the news date beside it.

### Prompt

Add one instruction: when `NEWS` carries injury or lineup news for either team,
lead with it, say what it changes for the prediction, and **date it**; when it
carries none, say nothing about team news at all. The existing rule against
inventing injuries stays and is the reason this is safe — the model can only
report a headline it was given.

## F1

Un-refuse `f1` in `SERVED_SPORTS` and give it a reduced panel: win probability,
podium, points and dnf, with **no market-line tiles and no split-bar market
row** — F1's facts have no lines, and the ledger's own reason for refusing it
("a `KeyNumberTile` and a `ProbabilityBar` would have nothing honest to draw")
still holds for those elements. It is triggered only, never on modal open.

**This reverses a recorded decision and the reversal is recorded, not
overwritten.** The original reasoning was that *"a win probability is the
explanation"*. That remains true of the win probability; what it did not
contemplate is the race story around it — the grid, the qualifying result, a
driver who gained or lost positions — which is the part worth a panel and is
what F1's `drivers` already carry.

## Error handling

| failure | behaviour |
|---|---|
| explainer container down | flow renders; button offers a retry. Never an empty panel. |
| explainer slow | button spins for its 15 s budget, then retry. The flow is untouched. |
| proxy returns 502 | same; the fixed message is not shown to a reader |
| 2xx that is not the expected shape | treated as unavailable |
| no news for a fixture | no news date shown, no extra cost, flow unchanged |

## Testing

- **Component** — per sport shape and per game state, the sentences are the ones
  specified and name no line that is not there; F1 draws no market-line tile; the
  button is absent once a summary exists. `news_date` is read as an **optional**
  field and left out of the footer when absent, so the component in PR B is
  shippable before PR C makes the service send it — the two are additive, and the
  panel never waits on the field.
- **No-empty-panel** — a test per site that renders the modal with the explainer
  unreachable and asserts the flow is on screen. This is the regression that
  produced the current symptom, so it is the one that must exist.
- **News** — the resolver is tested against the abbreviation/full-name pairs that
  actually appear; the freshness rule is tested by a fixture whose news date
  moves and asserting exactly one regeneration.
- **Service** — unchanged except un-refusing `f1` and the key change, each with a
  test that bites.
- Every new guard gets a mutation run, and the vendored-copy check every site
  already has continues to run.

## Sequencing

| # | Repo | PR | Contents |
|---|---|---|---|
| 0 | Sports_Predictor | — | **Prerequisite:** review and merge the open `caddy-no-echo` PR (#6). The last of the four proxies that still forwards an upstream body. Nothing here depends on it, but it should not ship after this. |
| 1 | predictor-hub | A | Un-refuse `f1`; extend the template path for it |
| 2 | predictor-hub | B | `FixtureExplainer`, `FixtureFlow`, `SummaryButton`, shared `panelFacts`, **and remove the v1 `LegacyExplanation` shape** |
| 3 | predictor-hub | C | News resolver, freshness key, prompt instruction |
| 4 | NBA_Predictor | D | Merge #9, then mount the panel |
| 5 | PL_Predictor | E | Re-vendor, delete the local copy, mount |
| 6 | Sports_Predictor | F | Re-vendor, delete the local copy, mount (covers NFL + CFB) |
| 7 | F1_Predictor | G | Re-vendor, mount the reduced panel |
| 8 | — | — | Deploy, then check a Bears game with a real injury headline |

D depends on NBA_Predictor#9. Every site PR re-vendors, so **B must merge before
E, F and G** — they carry a copy of the component it defines.

## Risks

- **The thin-NBA-panel risk is unchanged and is data, not code.** NBA's
  `game_market_predictions` has 0 rows, so 142 of 142 NBA bundles carry no
  `market_line` and both the spread and total factors are omitted. The README
  tells the deployer to run a `sqlite3` count rather than file a bug. This spec
  does not change it; the flow description makes the thin panel *legible* rather
  than fixing it.
- **Alias tables rot.** Team renames and abbreviations change. A miss is a
  silent no-news result, which is the safe direction, but a test that pins the
  resolver against the *sports' own* current abbreviations catches the common
  case.
- **The freshness rule spends more.** Bounded as described, but the daily cap is
  the thing to watch in the first week of traffic.
- **Standardising deletes working code.** PL's and Sports' panels currently work.
  The change replaces them with a shared component that must reproduce their
  behaviour, and their local tests are the specification for that.

## Not in scope

- The landing page and the hub's picks page (another session).
- CFB team news — the mechanism is there, the entries are not.
- Any change to how the model prompt grades or validates; this adds one
  instruction and keeps the existing prohibition on inventing injuries.
