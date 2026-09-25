export type Status = "next" | "live" | "called" | "missed" | "nopick" | "rebuilt";

// Status always carries words; colour only reinforces them.
const LOOK: Record<Status, { words: string; tone: string }> = {
  next: { words: "Next up", tone: "bg-pr-accent text-pr-accent-ink" },
  live: { words: "Live", tone: "border border-pr-loss text-pr-loss" },
  called: { words: "Called it ✓", tone: "text-pr-win" },
  missed: { words: "Missed ✗", tone: "text-pr-loss" },
  nopick: { words: "No pick yet", tone: "text-pr-text-dim" },
  rebuilt: { words: "Rebuilt after kickoff", tone: "border border-pr-rule text-pr-text-dim" },
};

/** The exact words each status reads as, for accessible names elsewhere. */
export const statusWords = (status: Status) => LOOK[status].words;

export function StatusBadge({ status }: { status: Status }) {
  const { words, tone } = LOOK[status];
  return (
    <span className={`inline-flex items-center rounded-pr px-1.5 py-0.5 font-pr-display text-xs font-semibold uppercase tracking-wide ${tone}`}>
      {words}
    </span>
  );
}
