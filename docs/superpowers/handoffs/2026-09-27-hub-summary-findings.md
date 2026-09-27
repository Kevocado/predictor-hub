# Handoff: what the `/hub/summary` investigation found (predictor-hub#16, now closed)

**From:** the session that built and then closed `predictor-hub#16`.
**For:** whoever implements `docs/superpowers/plans/2026-09-27-hub-picks-page.md`.
**Why:** the branch `hub-pick-first` is kept but its endpoint is **not** part of the hub picks page. Four findings below are not in the spec, and two of them change the plan.

I built an endpoint that fans out to all five sports server-side, to test whether the data the cards need is available and honest. It is — and that turned up things the spec assumes differently. **The endpoint itself is not recommended for the page** (see §1); the measurements are.

---

## 1. The one data path: five Caddy blocks, or one explainer endpoint

The plan's T1 adds five `handle_path` proxy blocks so the browser reads the five APIs same-origin. That works and I would not argue against it.

But the **explainer service already holds all five** `SPORT_API_*` base URLs, already fetches `/facts/{id}`, and already computes the confidence band. A `GET /hub/summary` there is one proxy block instead of five, no CORS anywhere, and the fan-out happens server-side where one sport failing can be isolated per card. The `hub-pick-first` branch is that endpoint, if you want it.

**Why I am not recommending it anyway, and why it is closed:**

- **It contradicts your `generated_at` freshness rule, in the direction that matters.** `hub.py::_one` takes `ids[0]` from `/facts/upcoming`, which appends ids as it walks the games list and **never sorts** — so it is not guaranteed to be the soonest fixture. Its only previous consumer (pre-generation, since deleted) did not need an order, so nobody noticed. The snapshots happen to be chronological today. Every `facts.py` *does* carry `starts_at`, so the ordering is recoverable without touching the endpoints.
- **Per-sport selection is the design.** The spec's F1-top-3, PL-best-edge and coin-flip rules are per sport. A uniform `{pick, band, record}` per card cannot express them, so the endpoint's own reason for existing evaporates.
- **`SERVED_SPORTS` is `("pl", "nfl", "cfb")` and the endpoint deliberately ignores it** — a pick is not an explanation. That is a defensible reading, but it is also a second meaning of "which sports does this service speak for", and a future session reading `SERVED_SPORTS` will not know the hub is exempt.

**Take the ordering lesson, drop the endpoint.** Add an explicit sort to the plan's fetch path rather than relying on list order.

## 2. `/facts/{id}` is a uniform contract across all five — worth more than the five API-specific reads

I read each repo's `facts.py` on `main` rather than assuming, and the emitted bundle is **identical in shape for NFL, CFB, PL, NBA and F1**:

```
sport, id, title, starts_at, status, pick_timing, pick, markets,
drivers, context, players, record, result
```

Every sport answers *who* (`pick.label`), *how sure* (`pick.prob`) and *has it been right* (`record`) from this one endpoint. If a teaser row wants a confidence word rather than a percentage, the **band is computed, never read from the payload**: `contract.band_for(prob, market_shape(facts))`, per spec §13a. It is worth re-using rather than re-deriving — and the payload must never be allowed to assert one.

The plan's per-sport sources (`predictions`, `fixtures_by_gameweek`, `weeks[].games`, `GET /games/week`) are each a *different* shape and each needs its own selection rule. `/facts` would be one shape for all five. That is a real simplification the plan has not considered, though it is not sufficient on its own, because the per-sport *selection* is what you actually asked for.

## 3. The record contract, including the honest empty

`record` is `{label, hits, settled}` and the **whole block is `None` when `settled <= 0`**. Two consequences:

- **`0/0` must never be rendered.** It reads as "wrong every time", which is a claim about a record that does not exist. NBA's committed snapshot has `track_record: []`, so its `_record()` returns `None` — the empty case is **the real case**, not a contrived one.
- **`hits: None` is not zero.** NFL emits that when it knows the rate but not the count.
- **The labels differ per sport and should be passed through, not normalised:** NFL and CFB say *"Picks made before kickoff"*, PL says *"before kick-off"*, NBA says *"before tip-off"*. One rule, three spellings. A visitor who sees two spellings for one rule has learned two rules; the hub repeating each sport's own label is the fix.

## 4. NBA's `/facts` is not a snapshot read, and that is the interesting part

The spec's table says NBA must call `GET /games/week` because the snapshot holds
results only. That is right — and worth stating what the alternative already is.

`NBA_Predictor`'s `facts.py` exists, and its own docstring says: *"NBA has no
public snapshot of predictions: every number comes from the same SQLite store the
site itself reads, and `tracking/timing.py` is the single authority on whether a
pick was made before tip-off."* It emits the same bundle as the other four, with
the same honesty rules — *"a pick for a game that has started comes only from the
newest row made before tip-off, never from a later backfill row"*, *"no
prediction at all means `pick` is null and `pick_timing` is `none`*.

So for NBA the `/facts` path is **not** a snapshot read that happens to be
missing predictions. It is a live, pre-kickoff-authoritative read. If a teaser
wants NBA's pick with its timing, `/facts/{id}` is the one source that already
enforces the rule; `GET /games/week` is a schedule read that does not. The cost
is that it needs an id, which `GET /games/week` supplies.

## 5. Confirms your T2, and adds that it is not only NFL and F1

Your `NaN` finding is right and I reproduced the consequence independently: a bare `NaN` in the snapshot is a **dead endpoint**, not an ugly number, because the installed starlette renders with `allow_nan=False`.

One correction to the plan's scope. I grepped the record builders and market builders in all five, not two, and **`PL_Predictor` also emits `null` deliberately** (`_none_if_nan(row.get(f"{side}_implied"))`) — so PL is already defending itself at the edge of its own output. NFL and F1 are the two that write bare `NaN`. Your T2 scope is right; the reason PL is safe is that someone already fixed it there, which is worth knowing so it is not "fixed" twice.

**A fourth, larger problem T2 does not cover, which I hit in the same code path:** the live data is stale in a way that would make a "current today" hub wrong. Measured on the committed snapshots against 2026-09-27:

| Sport | Next fixture in the committed snapshot | Gap |
|---|---|---|
| NFL | 15 games, **today** 17:00 UTC | current |
| CFB | 2026-10-02, 59 games | a week out |
| PL | 2026-10-10, 330 fixtures | two weeks out |
| NBA | 369 future games, but `track_record: []` | no record at all |
| F1 | 8 races left, next is round 21 (2026-11-22) | **two months out** |

So a hub built to show "what's on today" would show CFB and PL fixtures a week to two weeks stale **the moment it ships**, and F1's would be a race in November. The commit message on the snapshots (`"Refresh public snapshot [automated]"`) shows the cron *is* running and the committed snapshot is not current — these are whatever the cron last pushed, and it is behind.

**This does not block the picks page**, but it does mean the page cannot claim "today" until the refreshes catch up, and the `generated_at` line the spec already requires is what keeps that honest. Do not let the teasers imply recency the data does not have.

---

## What I would not repeat

- A mutation script of mine reported a guard as passing three times because it was replacing a string inside a **docstring** rather than code. Three identical "passes" is the signature of a broken harness. It now refuses ambiguous anchors and names the line it changed. If several mutation results come back green in a row, suspect the harness.
- I asserted a test's premise from a half-remembered threshold table and got the direction backwards. Write the expected value *and* its reason before the test runs, not after.
