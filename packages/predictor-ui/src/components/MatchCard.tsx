import type { ReactNode } from "react";
import { pct } from "../fmt";
import { ProbabilityBar, type Segment } from "./ProbabilityBar";
import { StatusBadge, statusWords, type Status } from "./StatusBadge";
import { TeamChip } from "./TeamChip";

export type Side = { code: string; name?: string; color?: string; badge?: ReactNode };

type Props = {
  left: Side;
  right: Side;
  /** Kickoff time before the game, the score after it. */
  centre: string;
  status: Status;
  pick?: { label: string; prob: number };
  /** Top-left line, usually the kickoff date. */
  when?: string;
  /** Sport-specific line under the pick: a spread, a total, a venue. */
  meta?: string;
  bar?: Segment[];
  /** "v" for football (home first), "at" for US sports (away first). */
  separator?: "v" | "at";
  onOpen: () => void;
};

function Team({ side }: { side: Side }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
      {side.badge ?? <TeamChip code={side.code} name={side.name} color={side.color} />}
      <span className="w-full truncate text-sm font-semibold text-pr-text">{side.name ?? side.code}</span>
    </div>
  );
}

/** The family match card: one pick, one status, a labelled bar. */
export function MatchCard({ left, right, centre, status, pick, when, meta, bar, separator = "v", onOpen }: Props) {
  const pickLine = pick ? `Pick: ${pick.label} · ${pct(pick.prob)}` : undefined;
  const name = [
    `${left.name ?? left.code} ${separator} ${right.name ?? right.code}, ${centre}.`,
    pickLine ? `${pickLine}.` : undefined,
    statusWords(status),
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={name}
      className="pr-notch flex w-full flex-col gap-3 rounded-pr border border-pr-rule bg-pr-panel p-4 text-left transition-colors hover:border-pr-accent"
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wide text-pr-text-dim">{when}</span>
        <StatusBadge status={status} />
      </div>
      <div className="flex w-full items-center gap-2">
        <Team side={left} />
        <span className="shrink-0 rounded-pr bg-pr-panel-2 px-2.5 py-1 font-pr-display text-xl font-semibold tracking-wide text-pr-text">
          {centre}
        </span>
        <Team side={right} />
      </div>
      {(pickLine || bar || meta) && (
        <div data-testid="pick-section" className="flex w-full flex-col gap-2 border-t border-pr-rule pt-2.5">
          {pickLine && <span className="text-sm font-semibold text-pr-text">{pickLine}</span>}
          {bar && <ProbabilityBar segments={bar} />}
          {meta && <span className="text-xs text-pr-text-dim">{meta}</span>}
        </div>
      )}
    </button>
  );
}
