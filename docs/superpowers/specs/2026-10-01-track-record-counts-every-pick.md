# The track record counts every recorded pick

**Status:** decided by Kevin on 2026-10-01 (in chat). Supersedes the "only a pick made before the
start counts" rule everywhere it appears (PRODUCT.md, the reviewer handoff, specs B8 / §F of the
fixture-insight design, PL#28/#29, NFL#23, Sports#13). Implementation is not started.

## The decision, in Kevin's words

> "i dont really care about picks made after kickoff because im always re running the models ...
> with every model change it will stop tracking ... make it that whats recorded remains recorded and
> then just use every prediction we make for the track record stuff."

## What was true before, measured (so the change is exact)

- A recorded prediction was **already immutable**: `INSERT OR IGNORE` on (event/game, market, outcome)
  in PL's `tracking/store.py` (and the NFL/CFB/NBA equivalents). A model change never erased one.
- What a rerun did was produce a prediction with `snapshotted_at` AFTER kickoff, which was labelled
  "rebuilt", excluded from the headline, and shown only in a second "all picks" figure (B8).
- So the real effect of the old rule was that a re-run model's picks on already-played games never
  counted, and the headline stayed empty until a pick was captured before a game started
  (PL's headline is empty today for exactly that reason).

## The new rule

1. **Recorded stays recorded.** The record is append-only. Nothing is overwritten, deleted or
   re-scored with a newer model. (Unchanged in mechanism; now stated as the rule.)
2. **One counted pick per (game, market): the EARLIEST recorded one.** A later rerun of the model on
   the same game is kept as history but neither replaces the counted pick nor counts a second time
   (otherwise re-running until it is right would be free). If the earliest recorded pick for a game was
   made after kickoff (a backfill), that is its counted pick.
   *Reversible:* count the latest recorded pick instead; one place in each repo's `get_track_record`.
3. **The headline counts every counted pick**, whenever it was made. The figure beside it is the
   subset **made before kickoff**, with its own n. B8's two figures swap roles: headline = all,
   secondary = pre-kickoff only.
4. **Honesty moves from exclusion to disclosure.** Every pick row carries `made_before_kickoff`
   (derived from its own `snapshotted_at` vs `commence_time`, compared as UTC instants, never from a
   flag) and its timestamp, and the per-pick list shows it. A pick made after kickoff is never
   presented as one made before.

## What does NOT change

- The AI explainer and the instant block still must not describe a post-kickoff number as a pre-game
  prediction: for a started game they use the stored (earliest recorded) pick, and the badge still
  says when it was made. Only the words "not counted" go.
- Nothing computed after the start may be labelled "made before kickoff".
- Never overwrite a recorded pick. Never backfill a `made_before_kickoff = true` that the timestamps
  do not prove.

## Implementation list (one PR per repo, test-first, `npm run build` clean for frontends)

| where | change |
|---|---|
| PL_Predictor | `get_track_record`: headline over all counted picks (earliest per game+market); `pre_kickoff` sub-record beside it. `pick_record.py` / `tracking_picks.jsonl`: record ALL picks with `made_before_kickoff`, not only pre-kickoff ones. Frontend track-record panel + copy. |
| NFL_Predictor, CFB_Predictor | B8 `all_picks` becomes the headline; the existing pre-kickoff figures become the secondary. API field names kept where possible so sites do not break; document any rename. |
| NBA_Predictor, F1_Predictor | same swap in their track-record endpoints and panels (F1: sessions, not kickoffs). |
| Sports_Predictor (frontend) | track-record page + week cards: headline all, "made before kickoff" secondary; list-card tally. |
| predictor-hub / predictor-ui | `StatusBadge`, `InstantBlock`, `FixtureExplainer` copy: "Rebuilt after kickoff … not counted" becomes "Made after kickoff" with no "not counted"; hub teasers' record rows; tests that assert the old strings. |
| docs | PRODUCT.md, the reviewer handoff (both already updated in the PR that adds this file), the ledger. |

## Risks stated plainly (Kevin has decided; recorded so the choice is informed, not re-litigated)

- Counting picks made after the game inflates the headline relative to a pure pre-game record: a model
  fitted on data that includes the result can look better than it would have on the night. The
  `made_before_kickoff` secondary figure is the honest read of live performance and stays visible.
- Because the earliest recorded pick counts, the headline is only as honest as WHEN the first pick
  was recorded. Capturing picks before kickoff (the CI snapshot job, PL#29) stays valuable: it is what
  makes the secondary figure non-empty.
