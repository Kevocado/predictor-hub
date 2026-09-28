---
version: 1
slug: "index-html"
primary_target: "index.html"
related_targets: []
---

# index.html

Scope: the Predictor hub landing page — the card grid plus the live picks teasers
underneath each card. Mode: Operate (scan the five sports and choose one), with the
page also acting as the product's front door. Extension of an established surface:
the broadcast-scoreboard tokens are hand-inlined from `predictor-ui/src/tokens.css`
and `tests/hub.test.mjs` fails on drift, so the world is inherited unchanged.

## Audience, job, proof

A visitor who arrived from a shared link, on a phone, with no context. Their job:
work out in one screen whether this product is worth opening, and which sport to
open. Proof: every teaser number is a real pre-race model pick, each carries the
time it was made, and a sport with nothing to show says so rather than showing a
spinner or a stale pick.

## Chosen direction and memorable moment

A fixture sheet's torn-off strip. The memorable moment is that the page answers
"what does it actually think right now?" without a click — five cards, five live
picks, each stamped with its own snapshot time, so the whole family is legible in
one screen and the visitor chooses a sport already knowing the model's mind.

## Constraints

- Cards render from static HTML and are never gated on a fetch. Every teaser
  hydrates independently; one failure never touches another card.
- Five states per teaser: loading, content, empty (offseason), error, and content
  carrying an edge. No state may be a spinner that never resolves.
- No `NaN` ever reaches a rendered number. Non-finite floats are `null` at the
  source, because a snapshot containing `NaN` is invalid JSON on disk.
- No pick appears without its timing. `generated_at`, and F1's `source`, ship with
  every row.
- Tokens are hand-inlined and drift-tested against `predictor-ui/src/tokens.css`.
  A new token goes into `tokens.css` first.
- 12 px floor, 4.5:1 contrast, tabular numerals, no meaning by colour alone.

## Unresolved

- Edge is a progressive enhancement. Whether `ODDS_API_KEY` gets funded and wired
  across the sports is a separate decision this surface does not wait on.
- T4 (real `driver_name` from the F1 API) is optional; without it the hub and the
  F1 site both show a surname, which is consistent but less informative.

## Direction contract

THESIS: The hub is a picks board, not a directory. The category default for a
multi-product landing page is a hero, a feature grid and a signup; this refuses
that and opens on the product's actual output, because the only proof that a
prediction product is worth anything is a prediction.

OWN-WORLD: Broadcast graphics package, inherited unchanged. Near-black stage, one
raised panel colour, hard 1px rules, 6px radius, Barlow Condensed in capitals for
codes and labels, Barlow for prose, one hot accent per sport set on the card's top
border and carried into its teaser. No glow, no gradient, no emoji — the existing
token-parity and craft-floor tests enforce this.

STORY: The visitor lands and sees five sports and five live opinions. They read
the confidence numbers before they read a single description, because that is the
answer they came for. They notice every number is stamped, which is what makes
them trust the ones they have not checked. They pick a sport from the board rather
than from a pitch.

FIRST VIEWPORT: Header with the wordmark and sport switcher, the h1, the lede, and
the honesty strap. Then the five-card board, each card carrying its teaser
immediately beneath it, so the grid and the picks read as one object. Teasers are
two to three rows, never a table.

FORM: Extend an existing surface. Inherited composition; no concept roll, no seed key.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
