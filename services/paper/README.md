# services/paper — the paper-trading ledger

**Paper only.** No order placement, no credentials, no network. Everything here
reads public files the sibling site repos commit and writes two files of its own.
`tests/test_gate.py` asserts the absence of order and credential code in CI,
because a ledger that could place a real order could not honestly be run against
real data.

## What it is for

Record every bet the models *would* have made, at the price that was actually
available at the time, settle it from the real result, and report whether any
**segment** — sport × market × confidence bucket — has an edge over the market
after fees. A segment may only be called "has an edge" on evidence, never on a
flag.

## Running it

```bash
# The site checkouts live as siblings of the hub. SITES_ROOT overrides discovery.
export SITES_ROOT=/path/to/the/dir/holding/NFL_Predictor

python3 scripts/paper_log.py       # append newly qualifying candidates
python3 scripts/paper_settle.py    # settle open rows from Kalshi's result
python3 scripts/paper_report.py    # print the segment table, write report.json

cd services/paper && PYTHONPATH=. python3 -m pytest -q
```

`paper_log.py` and `paper_settle.py` take `--dry-run`. Nothing writes on a dry run.

## The three rules everything else serves

1. **Append-only.** `data/paper/ledger.jsonl` is only ever opened for append. A
   candidate is written once, at the first observation that qualifies; settlement
   is a separate record referencing the same id; a later price is a
   `price_update`. No record is ever rewritten, because every rewrite is a chance
   to improve a row using information that did not exist when the bet was logged.
   See `paper/ledger.py`.

2. **No hindsight.** Four guards, each with a test in `test_no_hindsight.py`: the
   row's own `snapshot_ts` is the `logged_at` (never the wall clock); the price
   must be strictly before kickoff, read from `occurrence` and not `close_time`
   (Kalshi keeps these markets open for days afterwards); the logged price comes
   from that same row and no other; and the model's `generated_at` must be at or
   before the price's `snapshot_ts`, or the row is a **shadow** — logged,
   countable, never staked.

3. **Buyable prices only.** YES is logged at `yes_ask`, NO at `no_ask`. NFL's own
   `kalshi_lines.implied_probability` returns the bid/ask *midpoint*, and a
   midpoint is not a price anybody pays. A dead quote (0 or 1 cent) or a crossed
   book means there was no price to log.

Fees are a **verbatim copy** of `shared/kalshi_fees.py` from `algo-trade-hub-prod`
(commit `12432be`), with its mutation-grade pin tests. Do not reimplement them: it
rounds the total order fee up once, after applying the contract count, and a
per-contract-rounded copy would disagree with every number that repo has already
published.

## Where the numbers come from

| | source |
|---|---|
| price, timestamp, result | `data/lines/*.jsonl.gz` in `NFL_Predictor` / `NBA_Predictor` — self-settling, no box-score join |
| model probability | `data/public_snapshot.json` in the same repos |
| allow-list and gate | `data/paper/segments.json` |

## Current state, and why

**The ledger is empty and no segment qualifies.** That is the correct output, not a
placeholder. The two halves of the input do not currently meet:

| | per-game probability published? | Kalshi game price collected? | candidates |
|---|---|---|---|
| NFL | yes (`public_snapshot.json`, per-game) | **no** — the collector fetches four player-prop series and no `KXNFLGAME` | none |
| NBA | **no** — only aggregate `manifest.metrics` | yes (`KXNBAGAME`, `KXNBASPREAD`, `KXNBATOTAL`) | none |
| CFB | — | no collector exists at all | none |

Against the real committed data the logger reads ~19,500 rows and reports every
skip reason by count, so the gap is visible rather than silent. Injecting a
per-game probability for the real NBA games and nothing else produces 19 correctly
sized candidates, which is how the pipeline was verified.

Player props (WR/TE receptions, QB passing TDs) are a separate change in the NFL
repo, not a hub one, and what is missing there is a calibrated probability per
rung rather than a model at all: the site's committed `public_snapshot.json`
already carries a `receptions_p_over` for 269 of week 6's 415 player rows and a
`passing_td_over_prob` for 46, and its `market-lines` endpoint already attaches a
`model_p` to the receptions and passing-TD rungs it can match, but that number
is the probability at the model's own line (`receptions_line_source` is
`model_line`) copied onto every rung of the ladder, which is the same defect
`paper/log.py::p_over_line` calls out for totals, and the rows behind it carry
no `generated_at` (the endpoint falls back to the request time), no model
version and no game, so nothing today can price a rung at that rung's own line
or prove the probability predates the price it would be paired with. For
`nfl:receptions` and `nfl:passing_tds` to become loggable candidates, the NFL
repo would have to publish, in the committed snapshot this ledger already reads,
one row per counted prop carrying the game the prop belongs to, a player id
the ledger can match to a rung (the Kalshi player token, `NETHENDERSON32` in
`KXNFLREC-26OCT22NECHI-NETHENDERSON32-4`, since the two sides spell the
player's name differently), the rung's own line, the probability that the
player reaches that line as a number in [0,1] and not a projection of the
stat, the timestamp the probability was made, and the model version, so
results can be grouped by model. Receptions prices are already collected (the
21 October `data/lines` file holds 2,524 `KXNFLREC` rows), but `KXNFLPASSTDS`
is not in the collector's series list, so QB passing TDs have no collected
price either; until both halves land, both segments stay blocked and can only
ever be shadows.

`segments.json` is the place to change the pre-stated 4-point edge threshold, and
`tests/test_gate.py` fails if the 300-bet floor is ever lowered. A gate that can
be lowered by an edit is not a gate.
