import { contrast } from "../contrast";
import { pct } from "../fmt";

export type Segment = { label: string; prob: number; color?: string };

// Default fills when a segment has no team colour: three-way reads
// home / draw / away as accent / neutral / dim, never good/bad green/red.
const FALLBACK = ["var(--color-pr-accent)", "var(--color-pr-rule)", "var(--color-pr-text-faint)"];

// A team colour that nearly matches the panel (Browns brown, Ravens purple)
// would make its share of the bar disappear; those fall back to a neutral
// that reads. 1.6:1 against the panel is the floor.
const PANEL = "#151920";
const visible = (color: string | undefined, i: number) =>
  color && contrast(color, PANEL) >= 1.6 ? color : FALLBACK[i % FALLBACK.length];

/** Segments render in the order given, each labelled in words. */
export function ProbabilityBar({ segments }: { segments: Segment[] }) {
  const described = segments.map((s) => `${s.label} ${pct(s.prob)}`);
  return (
    <div role="img" aria-label={described.join(", ")} className="flex flex-col gap-1.5">
      <div aria-hidden="true" className="flex h-2 w-full gap-0.5 overflow-hidden rounded-pr">
        {segments.map((s, i) => (
          <div key={s.label} data-testid="pbar-fill" style={{ flexGrow: Math.max(s.prob, 0.01), backgroundColor: visible(s.color, i === 0 ? 0 : 2) }} />
        ))}
      </div>
      <div aria-hidden="true" className="flex justify-between gap-2 text-xs text-pr-text-dim">
        {described.map((text) => (
          <span key={text} data-testid="pbar-label">
            {text}
          </span>
        ))}
      </div>
    </div>
  );
}
