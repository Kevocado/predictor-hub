---
version: 1
slug: "packages-predictor-ui-src-components-boxscore-tsx"
primary_target: "packages/predictor-ui/src/components/BoxScore.tsx"
related_targets: []
---

# BoxScore

Scope: the predicted box score on a fixture/game detail surface (NFL, CFB, NBA).
Mode: Operate — the visitor is scanning a projected roster to decide whether to trust it.
This is an extension of an established surface, so the broadcast-scoreboard world in
`predictor-ui/src/tokens.css` is inherited unchanged. No new visual identity.

## Audience, job, proof

Fans checking picks, on a phone, minutes before kickoff. Their job: read the whole
projected roster for one game without scrolling back and forth, and see at a glance
which players the model actually likes and which are bench filler. Proof: every row
is a real model prediction, the columns are exactly the markets the model predicts,
and a sport with no real depth-chart feed says so on its face instead of implying
one.

## Chosen direction and memorable moment

A projected box score, grouped into position blocks, starters above a hairline and
bench below, each block totalling, each team totalling at the foot — the projected
score readable straight off the two total rows without scrolling back up. The
memorable moment is the **honesty rail**: `isStarter: null` renders a visibly
different "Projected order" treatment with a note, so CFB (no depth-chart feed) can
never be mistaken for NFL (real nflverse depth charts). The component makes the
distinction structural rather than a footnote.

## Constraints

- Columns are exactly the model's markets. No dashed-out FanDuel columns; an
  em-dash means the model has no prediction, and most cells must not be em-dashes.
- Three-state team control (Away / Both / Home), default Both.
- 12 px text floor, 4.5:1 contrast, tabular numerals, no meaning by colour alone.
- At 390 px one team's starters plus its total must be readable without scrolling.
- Presentational only: the caller groups, sorts and chooses columns. The component
  never reorders and never fetches.

## Unresolved

- A5 must read the NBA prop feed before fixing the NBA column list; no assumed
  parity with the NFL set.
- A5 must confirm NBA has real starter data before assuming `isStarter` is non-null.

## Direction contract

THESIS: A box score, not a prop list. The category default for "show me player
predictions" is a filterable sortable table that the reader must decipher; this
refuses that and reads as a lineup sheet, where position is the structure and
volume is the sort.

OWN-WORLD: Broadcast graphics package. Near-black stage, one raised panel colour,
hard 1px rules, squared 2–4px corners, slabs and lower-third bars instead of glassy
cards. One condensed display face in capitals for position labels and team totals,
tabular numerals in every data cell, one hot accent per sport used like a network's
graphics package. Team colours only in chips and bars.

STORY: The visitor arrives wanting to know who plays and what the model expects from
them. They read the team totals first and get a projected score. They scan the
position blocks and their eyes land on the starters first, because the rail puts
them there. Where the feed has no depth chart, the sheet tells them so and they
discount it accordingly — trust is built by the admission, not hidden by it.

FIRST VIEWPORT: Section header on one line: title left, three-state team control
right. Immediately below, the two team total rows at display scale, so the projected
score is the first thing read. Then position blocks, each opening with a sticky
header carrying the position label and its own subtotal. Inside a block, starters in
depth-chart order, a hairline, then bench.

FORM: Extend an existing surface. Inherited composition; no concept roll, no seed key.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
