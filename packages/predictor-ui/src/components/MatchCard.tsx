import type { ReactNode } from "react";
import { pct } from "../fmt";
import { ProbabilityBar, type Segment } from "./ProbabilityBar";
import { StatusBadge, type Status } from "./StatusBadge";
import { TeamChip } from "./TeamChip";

export type Side = { code: string; name?: string; color?: string; badge?: ReactNode };

type Props = {
  left: Side;
  right: Side;
  /** Kickoff time before the game, the score after it. */
  centre: string;
  /** Omit for an upcoming game that is not next up: no badge. */
  status?: Status;
  pick?: { label: string; prob: number };
  /** Top-left line, usually the kickoff date. */
  when?: string;
  /** Sport-specific line under the pick: a spread, a total, a venue. */
  meta?: string;
  bar?: Segment[];
  onOpen: () => void;
};

// The card is named by its own visible text (WCAG 2.5.3 Label in Name), so
// screen readers hear everything sighted visitors see. Buttons may only hold
// phrasing content, so the layout is built from spans.
const Sep = () => <span className="sr-only">, </span>;

function Team({ side }: { side: Side }) {
  return (
    <span className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
      <span aria-hidden="true">{side.badge ?? <TeamChip code={side.code} color={side.color} />}</span>
      <span className="block w-full truncate text-sm font-semibold text-pr-text">{side.name ?? side.code}</span>
    </span>
  );
}

/** The family match card: one pick, one status, a labelled bar. */
export function MatchCard({ left, right, centre, status, pick, when, meta, bar, onOpen }: Props) {
  // A missing pick is always said out loud; the status badge only covers it
  // when the badge itself reads "No pick yet".
  const pickLine = pick ? `Pick: ${pick.label} · ${pct(pick.prob)}` : status === "nopick" ? undefined : "No pick yet";

  return (
    <button
      type="button"
      onClick={onOpen}
      className="pr-notch flex w-full flex-col gap-3 rounded-pr border border-pr-rule bg-pr-panel p-4 text-left transition-colors hover:border-pr-accent"
    >
      <span className="flex w-full items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wide text-pr-text-dim">{when}</span>
        {status && (
          <>
            <Sep />
            <StatusBadge status={status} />
          </>
        )}
      </span>
      <Sep />
      <span className="flex w-full items-center gap-2">
        <Team side={left} />
        <Sep />
        <span className="shrink-0 rounded-pr bg-pr-panel-2 px-2.5 py-1 font-pr-display text-xl font-semibold tracking-wide text-pr-text">
          {centre}
        </span>
        <Sep />
        <Team side={right} />
      </span>
      {(pickLine || bar || meta) && (
        <span data-testid="pick-section" className="flex w-full flex-col gap-2 border-t border-pr-rule pt-2.5">
          <Sep />
          {pickLine && <span className={`text-sm font-semibold ${pick ? "text-pr-text" : "text-pr-text-dim"}`}>{pickLine}</span>}
          {bar && <ProbabilityBar segments={bar} />}
          {meta && (
            <>
              <Sep />
              <span className="text-xs text-pr-text-dim">{meta}</span>
            </>
          )}
        </span>
      )}
    </button>
  );
}
