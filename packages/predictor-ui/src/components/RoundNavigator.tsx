import { record as fmtRecord } from "../fmt";

type Record = { hits: number; settled: number; rebuilt: number };

type Props = {
  label: string;
  /** "gameweek", "week", "round": used in "Jump to current …" and the record line. */
  unit?: string;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  onJumpToCurrent?: () => void;
  record?: Record;
};

const stepClass =
  "rounded-pr border border-pr-rule bg-pr-panel px-2.5 py-1.5 text-pr-text-dim transition-colors hover:text-pr-text disabled:cursor-not-allowed disabled:opacity-40";

function recordLine(r: Record, unit: string): string | null {
  if (r.settled > 0) return `${fmtRecord(r.hits, r.settled)} picks made before kickoff correct`;
  if (r.rebuilt > 0) return `No pre-kickoff picks this ${unit}`;
  return null;
}

/** Round stepping plus the round's honest pre-kickoff record. */
export function RoundNavigator({ label, unit = "week", canPrev, canNext, onPrev, onNext, onJumpToCurrent, record }: Props) {
  const line = record ? recordLine(record, unit) : null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <button type="button" aria-label="Previous" disabled={!canPrev} onClick={onPrev} className={stepClass}>
          ←
        </button>
        <h2 className="font-pr-display text-2xl font-bold uppercase tracking-wide text-pr-text">{label}</h2>
        <button type="button" aria-label="Next" disabled={!canNext} onClick={onNext} className={stepClass}>
          →
        </button>
        {onJumpToCurrent && (
          <button type="button" onClick={onJumpToCurrent} className="rounded-pr border border-pr-accent px-2.5 py-1.5 text-xs font-semibold text-pr-text transition-colors hover:bg-pr-panel-2">
            Jump to current {unit}
          </button>
        )}
      </div>
      {line && <p className="text-sm text-pr-text-dim">{line}</p>}
    </div>
  );
}
