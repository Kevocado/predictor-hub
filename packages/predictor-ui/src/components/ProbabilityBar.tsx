import { contrast, parseHex } from "../contrast";
import { pct } from "../fmt";

export type Segment = {
  label: string;
  prob: number;
  color?: string;
  /** The facts' `market` key, when this segment IS a market. A factor's `key`
   *  refers to it, which is what makes §13c's highlight a lookup rather than a
   *  second naming scheme. Optional, so the match-card call sites that predate
   *  the panel are unaffected. */
  market?: string;
};

// Which outcome the model picked, as the service derived it from the facts
// (spec §5b; `contract.pick_for`). The panel never works this out for itself:
// a renderer that guessed the pick from segment order or from the widest
// segment is the defect this field exists to remove.
// Not named `Pick`, which would shadow the built-in utility type of that name
// inside every file that imports it. The key on the wire is still `pick`.
export type PickRef = { label: string; side?: string };

/** The only colour that means "this is the pick", so only the pick may spend
 *  it — and a bar with no pick spends none of it. */
const ACCENT = "var(--color-pr-accent)";

// The neutral ramp a segment that is NOT the pick is painted in, most prominent
// first. Never good/bad green/red: a green segment beside a grey one reads as
// "right" and a red one as "wrong", which is a claim about the outcome, and
// this bar is only claiming which side was picked.
// Three steps, not two, because a three-way market (PL home/draw/away) has to
// keep three distinguishable tones once the accent has been given to the pick.
// Two segments painted the same grey is a worse defect than the one this
// replaces: the reader cannot read a 48% home off a 26% draw by tone at all.
// `fill-mute` is the third rung, added to tokens.css for exactly this.
const NEUTRALS = [
  "var(--color-pr-text-dim)",
  "var(--color-pr-text-faint)",
  "var(--color-pr-fill-mute)",
];

// A team colour that nearly matches the panel (Browns brown, Ravens purple)
// would make its share of the bar disappear; those fall back to a neutral
// that reads. 1.6:1 against the panel is the floor.
// Kept equal to --color-pr-panel by tokens.test.ts.
export const PANEL = "#151920";
function fill(color: string | undefined, emphasised: boolean, rank: number): string {
  const hex = color ? parseHex(color) : null;
  return hex && contrast(hex, PANEL) >= 1.6 ? hex : emphasised ? ACCENT : NEUTRALS[rank % NEUTRALS.length];
}

/** Where the pick is, as an index into `segments`; -1 when there is no pick to
 *  find, and -1 for a pick whose label matches nothing here too. That second
 *  case fails closed on purpose: a label the bar cannot find is a site passing
 *  a different vocabulary, and pointing at the nearest segment to it would put
 *  the emphasis on a claim nobody made. */
function pickIndex(segments: Segment[], pick: PickRef | null | undefined): number {
  return pick ? segments.findIndex((s) => s.label === pick.label) : -1;
}

/** One tone per segment, in the order given.
 *
 *  The ramp is walked by the segments that are NOT the pick, so the neutrals
 *  stay three distinct tones on a three-way bar whether the pick is the first
 *  segment, the last, or the draw in the middle. A segment with a legible team
 *  colour is not painted from the ramp at all and does not consume a step, so
 *  the neutrals beside it still start at the most prominent rung.
 *
 *  A bar of five outcomes or more would wrap the ramp and repeat a tone. Nothing
 *  this product serves draws more than three outcomes on one market, and a
 *  repeat is what the old index-based fallback did too — it is not a new
 *  collapse, so it is left rather than guarded.
 */
function tones(segments: Segment[], index: number): string[] {
  let rank = 0;
  return segments.map((s, i) => {
    const emphasised = i === index;
    const tone = fill(s.color, emphasised, rank);
    if (!emphasised) rank += 1;
    return tone;
  });
}

/** Whether the market's own split covers every outcome the model's split has.
 *
 *  Spec §13b. PL's `implied` carries only the two sides, so with a three-way
 *  model split a market row would sit under a draw segment with nothing above
 *  it: two bars covering different outcomes, inviting a comparison that cannot
 *  be made. Omission is the honest answer.
 */
function covers(segments: Segment[], legend: Segment[]): boolean {
  const have = new Set(legend.map((s) => s.label));
  return segments.every((s) => have.has(s.label));
}

/**
 * Segments render in the order given, each labelled in words.
 *
 * The graphic keeps its `role="img"` and its single label, which is the right
 * summary for a reader who is not going to step through it. The per-segment
 * labels are then real buttons carrying the same figures, so a reader who
 * *does* step through it gets them one at a time. That is summary plus detail,
 * and it is why nothing here is `aria-hidden`: a focusable element inside an
 * `aria-hidden` container is reachable by keyboard and invisible to a screen
 * reader, which is worse than either alone.
 */
export function ProbabilityBar({
  segments,
  legend,
  minSegmentPx = 0,
  highlightKey = null,
  pick = null,
  onSegmentFocus,
}: {
  segments: Segment[];
  legend?: Segment[];
  /** A 3% probability still has to render as a sliver rather than vanishing.
   *  §6a: the label goes in the legend rather than shrinking below the 12px
   *  floor, so visibility and the floor are not in tension. */
  minSegmentPx?: number;
  /** The market key a selected factor points at (§13c). */
  highlightKey?: string | null;
  /** The pick, from the answer. The accent follows it and nothing else does:
   *  segment order used to decide, so on a two-way bar with the away side
   *  listed first the model was shown to have picked the home side. Absent
   *  means no pick, and then no segment is accented — a bar that emphasises
   *  something is claiming there is a pick, and with none there is none to
   *  point at. */
  pick?: PickRef | null;
  onSegmentFocus?: (label: string, market?: string) => void;
}) {
  const index = pickIndex(segments, pick);
  const fills = tones(segments, index);
  const named = segments.map((s) => `${s.label} ${pct(s.prob)}`);
  // The accent is a colour, so the emphasis has to be said as well. This is the
  // same rule FactorList states about its triangles: a meaning carried by
  // colour alone is not carried at all for a reader who cannot see it, in
  // greyscale print, or on the wrong background. Only when the pick actually
  // matched a segment — an unmatched label is not a claim about any of them.
  const described = index < 0 ? named : [...named, `the pick is ${segments[index].label}`];
  const showLegend = !!legend && covers(segments, legend);
  const dim = (s: Segment) => (highlightKey && s.market && s.market !== highlightKey ? 0.4 : 1);

  return (
    <div className="flex flex-col gap-1.5">
      <div role="img" aria-label={described.join(", ")}>
        <span aria-hidden="true" className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-pr">
          {segments.map((s, i) => (
            <span
              key={i}
              data-testid="pbar-fill"
              data-min-width={minSegmentPx ? `${minSegmentPx}px` : undefined}
              className="h-full transition-opacity duration-150"
              style={{
                flexGrow: Math.max(s.prob, 0.01),
                minWidth: minSegmentPx ? `${minSegmentPx}px` : undefined,
                backgroundColor: fills[i],
                opacity: dim(s),
              }}
            />
          ))}
        </span>
      </div>

      <div className="flex items-baseline justify-between gap-2">
        {segments.map((s, i) => (
          <button
            key={i}
            type="button"
            data-testid="pbar-label"
            data-seg={s.label}
            data-highlighted={highlightKey && s.market === highlightKey ? "true" : "false"}
            onClick={() => onSegmentFocus?.(s.label, s.market)}
            onFocus={() => onSegmentFocus?.(s.label, s.market)}
            className="min-w-0 rounded-pr text-xs tabular-nums text-pr-text-dim underline-offset-4 transition-opacity duration-150 hover:text-pr-text focus-visible:text-pr-text"
            style={{ opacity: dim(s) }}
          >
            {s.label} {pct(s.prob)}
          </button>
        ))}
      </div>

      {showLegend && (
        <div data-testid="pbar-legend" className="flex flex-col gap-1 border-t border-pr-rule pt-1.5">
          <span className="flex items-center gap-2 text-xs text-pr-text-faint">
            <span className="w-16 shrink-0 uppercase tracking-wide">market</span>
            <span aria-hidden="true" className="flex h-1 w-full gap-0.5 overflow-hidden rounded-pr">
              {legend!.map((s, i) => (
                <span key={i} style={{ flexGrow: Math.max(s.prob, 0.01), backgroundColor: "var(--color-pr-text-faint)" }} />
              ))}
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
