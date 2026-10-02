/**
 * The model's own top calls, ranked per category.
 *
 * Three rules are enforced HERE rather than left to every caller, because each
 * one has already been broken at least once by a caller that was being careful:
 *
 *  1. **A row's visual must match what its number IS.** `kind: "probability"`
 *     draws a share bar and `kind: "projection"` draws a key number with a ±.
 *     Passing a yardage figure as a probability once rendered "9600%", so the
 *     two kinds have disjoint ranges and a value outside its own is refused by
 *     name rather than drawn.
 *  2. **An out player leaves the ranking entirely.** A row marked `out` is
 *     refused. There is no greyed-out row and no "flagged in place" state to
 *     opt into — the caller passes them in `out`, where they are shown once,
 *     below the lists, with the source and the date.
 *  3. **Three rows per category, and three is a ceiling.** Fewer when fewer
 *     exist. Nothing is padded to fill the list.
 *
 * Provenance is the caller's own words, verbatim. This component composes no
 * confidence language at all: a probability, a bucket context and a ± are all
 * it renders, so there is no sentence here that could claim an edge, a price
 * or a guarantee — no odds feed exists in any of these repos.
 *
 * And a fourth rule, which is not a guard against a careless caller but a
 * decision about what a row says:
 *
 *  4. **A row's `detail` renders only when it says something the category
 *     heading above it does not already say.** See `detailAddsToHeading` for
 *     why, for the two readings of "always" that were rejected, and for what
 *     this costs. The short form: a heading is the list's label, a row's
 *     `detail` is the row's own, and a label that adds no word is stutter
 *     rather than information.
 */
import { pct, stat } from "../fmt";
import { StatusBadge } from "./StatusBadge";

/** A player out for this fixture, shown once below the lists and never ranked. */
export type OutPlayer = {
  name: string;
  team?: string;
  /** Where the out claim came from, in words. Never an id. */
  source: string;
  /** When it was known, in words. Never an epoch. */
  dated: string;
};

export type PickRow = {
  /** Stable per player+category; the tile's identity and the React key. */
  key: string;
  name: string;
  team?: string;
  /** The category, in words: "Anytime TD", "Rush yds".
   *
   *  A row's own label, and rendered only when it adds a word the category
   *  heading does not already carry — `detailAddsToHeading`, below. NFL's QB
   *  passing-TD rows are what make this field load-bearing rather than
   *  decorative: the call is `"Over 2.5"` and the probability is `value`, so
   *  without the detail the row is a bare "64%" and a reader has no line to
   *  act on.
   */
  detail: string;
  /** The model's own number for this category. Never derived here. */
  value: number;
  /** "probability" draws a share bar; "projection" draws a key number + ±. */
  kind: "probability" | "projection";
  /** Only for `kind: "projection"`: the error margin, rendered as "± N".
   *  Absent means there is no error estimate yet, which is said in words
   *  rather than drawn as "± 0" — a zero margin would be a claim. */
  margin?: number;
  /** What the rendered `detail` IS, in the caller's own words. Defaults to
   *  `DEFAULT_DETAIL_LABEL`.
   *
   *  The qualifier is in the *visible* text, not in a `title` or a hidden
   *  accessible label, and that is the whole point of it. A detail like
   *  "Over 2.5" is the shape of a sportsbook price, and nothing on the page
   *  distinguishes one from the other: there is no odds feed in any of these
   *  repos, so a reader who assumes a price is reading a line the model chose.
   *  A `title` cannot carry that on the device this is mostly read on — it
   *  never appears on touch, and it is not reliably announced from a
   *  non-focusable span — so the provenance has to be words on the page.
   *
   *  "model call" is the default because it is the one noun this component
   *  can vouch for whatever the caller passed: the caller's words describe
   *  what the MODEL is picking, and `value` is documented above as the
   *  model's own number. A caller that knows its detail is a line says so
   *  (Sports_Predictor's NFL adapter passes `"model line"`, which is the
   *  plan's wording) — which is also why this is per row and not a prop on
   *  `PicksListProps`: a list can hold two kinds of row.
   */
  detailLabel?: string;
  /** Accepted for compatibility and NOT rendered. Kevin, 2026-10-01: the best calls are
   *  the player and the prediction, nothing else (no record, Brier, calibration or error
   *  prose per row). Callers may stop passing it. */
  provenance?: string;
  /** True when this player is out. If true the row must NOT be passed — see
   *  `out`. The field exists so the mistake can be caught by name instead of
   *  rendering a forbidden ranking. */
  out?: boolean;
};

export interface PicksListProps {
  title?: string;
  categories: { category: string; rows: PickRow[] }[];
  out?: OutPlayer[];
}

/** At most this many rows per category. A cap, never a quota. */
export const MAX_ROWS_PER_CATEGORY = 3;

/** The qualifier that says where a rendered `detail` came from. Exported so a
 *  site names this constant rather than retyping the string. */
export const DEFAULT_DETAIL_LABEL = "model call";

/**
 * Does this row's `detail` say anything its category heading does not already
 * say?
 *
 * **THE RULE.** A row renders its `detail` when at least one word of the
 * detail is absent from the heading above it. Equality is not the test, and it
 * cannot be: the harness already builds headings like
 * `"Rush yds — projections, not probabilities"`, and `"Rush yds" !==` that
 * string, so an equality test would print the detail three times on every
 * projection card in the family and call the output a fix. Containment is the
 * test, word by word, lowercased, with runs of punctuation split and the dot
 * inside a number kept (`2.5` is one token, not two).
 *
 * **WHY, and the two readings of "always" that were rejected.**
 *
 * The failure to avoid is a bare percentage: NFL's QB passing-TD category is
 * specified to read `Over 2.5 · 64%`, and without the detail the page shows
 * "A. Rodgers · 64%", which is not actionable — a probability with no line.
 * The cost to avoid is a heading repeated on every row under it, in five
 * sports' worth of existing data, where `detail` is very often the category
 * restated ("Pass yds", "Rush yds").
 *
 *  * **(a) Always.** Loses nothing — and that is the problem. Every existing
 *    card prints its heading three more times, and a repeated word cannot be
 *    read as emphasis or as a mistake, so the reader stops trusting the
 *    hierarchy: on a card where a word IS new, it looks identical to the noise
 *    around it. It also spends the row's only spare text slot on information
 *    already on screen.
 *  * **(c) Always, de-emphasised.** Keeps the duplication and de-emphasises
 *    the only actionable thing on the row. Under this rule the detail is
 *    rendered precisely when it is NEW, so it is the row's most useful text,
 *    and greying it says the opposite of what the rule just decided. A
 *    consistent answer ("a detail that adds nothing is dropped") beats an
 *    inconsistent one ("a detail that adds nothing is drawn quietly") because
 *    the reader learns it once.
 *  * **(b) Only when it adds a word — chosen.** A reader of any existing
 *    category sees exactly today's row, so nothing is taken away from the four
 *    sports that are live; a reader of the new category gains the line.
 *
 * **WHAT IS GIVEN UP.** A detail made entirely of words the heading already
 * uses is dropped, so a caller cannot disambiguate two rows in one list by a
 * word the heading already carries — `detail: "passing"` under
 * `"QB passing TDs"` renders nothing. Accepted: the heading is what the reader
 * navigates by, and the row's own `value` already separates two rows under one
 * heading. A caller who needs the distinction puts the distinguishing word in
 * the heading or in `detail`, where this rule lets it through.
 *
 * A row whose detail DOES add a word under a heading that does not mention its
 * category is the caller's own inconsistency, and saying it out loud is better
 * than dropping it — the same reason a bad `kind` is refused by name rather
 * than quietly corrected.
 */
export function detailAddsToHeading(detail: string, category: string): boolean {
  const detailWords = detail.toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
  if (detailWords.length === 0) return false;
  const headingWords = new Set(category.toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean));
  return detailWords.some((word) => !headingWords.has(word));
}

/** A row marked `out` was passed as a ranked row: "removed, not flagged" is a
 *  rule about what reaches the page, and this is the last place that can say no. */
export class OutPlayerInRankingError extends Error {
  constructor(name: string) {
    super(
      `PicksList: "${name}" is marked out and was passed as a ranked row. An out player ` +
        `leaves the ranking entirely — pass them in \`out\` instead, where they appear once ` +
        `below the lists with their source and date.`,
    );
    this.name = "OutPlayerInRankingError";
  }
}

/** A row's `value` is outside the range its `kind` can honestly draw. */
export class RowKindMismatchError extends Error {
  constructor(player: string, detail: string, kind: "probability" | "projection", value: number) {
    super(
      kind === "probability"
        ? `PicksList: "${player}" is a ${detail} probability row, so its value must be in [0,1] — got ${value}. ` +
            `A yardage figure read as a share is the defect this guard exists for.`
        : `PicksList: "${player}" is a ${detail} projection row, so its value must be finite and not negative — got ${value}.`,
    );
    this.name = "RowKindMismatchError";
  }
}

/**
 * Refuse a row whose number cannot honestly draw the visual its `kind` asks for.
 *
 * Runs before anything renders, so a caller that made the mistake gets a named
 * error naming the player and the category instead of a bar reading 9600%.
 */
function checkRow(row: PickRow): void {
  if (row.out) throw new OutPlayerInRankingError(row.name);
  if (!Number.isFinite(row.value)) {
    throw new RowKindMismatchError(row.name, row.detail, row.kind, row.value);
  }
  if (row.kind === "probability") {
    if (row.value < 0 || row.value > 1) throw new RowKindMismatchError(row.name, row.detail, row.kind, row.value);
  } else {
    // A projection is a count or a distance: finite and not negative. It MAY be a
    // fraction (0.8 steals, 0.6 touchdowns). The row's `kind` is explicit, so a
    // magnitude test is not how a mislabelled row is caught here; refusing [0,1]
    // threw during render for legitimate rows and took the whole list down.
    if (row.value < 0) throw new RowKindMismatchError(row.name, row.detail, row.kind, row.value);
  }
}

/** The figure a row shows. A probability is a percentage; a projection is a plain
 *  number with no % anywhere, because a count read as a share is the "9600%" defect. */
function figure(row: PickRow): string {
  return row.kind === "probability" ? pct(row.value) : stat(row.value);
}

/** A thin bar for a probability only. Floored so a small probability stays visible. */
function Bar({ value }: { value: number }) {
  const width = Math.max(value * 100, 3);
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-pr-rule" aria-hidden="true">
      <div data-testid="picks-bar" className="h-full rounded-full bg-pr-accent" style={{ width: `${width}%` }} />
    </div>
  );
}

export function PicksList({ title = "Model's top calls", categories, out }: PicksListProps) {
  // Every row is checked before any of them renders, so one bad row cannot
  // leave a half-drawn list on the page.
  for (const { rows } of categories) for (const row of rows) checkRow(row);

  if (categories.length === 0 && !out?.length) return null;

  return (
    <div data-testid="picks-list" className="flex flex-col gap-4">
      <p
        data-testid="picks-title"
        className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-faint"
      >
        {title}
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        {categories.map(({ category, rows }) => {
          // The ceiling. `slice` rather than a filter, so an out player could not be
          // swapped in to backfill a dropped row; `checkRow` has already refused one.
          const shown = rows.slice(0, MAX_ROWS_PER_CATEGORY);
          return (
            <section
              key={category}
              data-testid="picks-category"
              className="flex flex-col gap-2 rounded-pr border border-pr-rule bg-pr-surface/40 p-3"
            >
              <h3
                data-testid="picks-category-heading"
                className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-dim"
              >
                {category}
              </h3>
              {shown.length === 0 ? (
                // The existing empty-state vocabulary, never a zero: a figure nobody
                // produced must not be drawn as one.
                <StatusBadge status="nopick" />
              ) : (
                shown.map((row, i) => (
                  <div
                    key={row.key}
                    data-testid="picks-row"
                    data-kind={row.kind}
                    data-category={category}
                    className="flex flex-col gap-1.5 border-t border-pr-rule pt-2 first:border-t-0 first:pt-0"
                  >
                    <div className="flex items-baseline gap-2">
                      <span data-testid="picks-rank" className="w-4 shrink-0 font-pr-display text-xs font-semibold text-pr-text-faint tabular-nums">
                        {i + 1}
                      </span>
                      <p className="min-w-0 flex-1 truncate text-sm font-medium leading-snug text-pr-text">
                        {row.name}
                        {row.team && <span className="font-normal text-pr-text-dim"> · {row.team}</span>}
                      </p>
                      <span
                        data-testid="picks-value"
                        className={`font-pr-display text-xl font-semibold leading-none tabular-nums ${i === 0 ? "text-pr-accent" : "text-pr-text"}`}
                      >
                        {figure(row)}
                      </span>
                    </div>
                    {/* Rule 4, and the whole of it: `detailAddsToHeading` is the
                        only thing that decides this, so a detail that adds no word
                        to the heading renders nothing at all rather than a quieter
                        copy of the heading. Indented past the rank gutter so it
                        reads as part of the player's row and not as a fourth
                        column. The label is visible text, not a `title` — see
                        `detailLabel`. */}
                    {detailAddsToHeading(row.detail, category) && (
                      <p data-testid="picks-detail" className="pl-6 text-xs leading-snug text-pr-text-dim">
                        {row.detail}
                        <span className="text-pr-text-faint"> · {row.detailLabel ?? DEFAULT_DETAIL_LABEL}</span>
                      </p>
                    )}
                    {row.kind === "probability" && <Bar value={row.value} />}
                  </div>
                ))
              )}
            </section>
          );
        })}
      </div>

      {/* §D: an out player is shown ONCE, here, and nowhere in a ranking — no
          bar, no tile, no rank position, attributed and dated. */}
      {!!out?.length && (
        <div data-testid="picks-out" className="flex flex-col gap-1 border-t border-pr-rule pt-2">
          {out.map((p) => (
            <p key={`${p.name}-${p.dated}`} className="text-xs leading-snug text-pr-text-faint">
              Out: {p.name}
              {p.team && ` · ${p.team}`} — not ranked. {p.source} · {p.dated}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/** The percentage a probability row shows, for a caller that wants the same
 *  rounding the bar uses. Exported so a site cannot re-derive it differently. */
export { pct as picksPct };