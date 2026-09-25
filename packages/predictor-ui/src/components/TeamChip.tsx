import { inkFor } from "../contrast";

// Team identity without logos: the team colour with its code set in ink
// that stays readable on that colour.
export function TeamChip({ code, name, color }: { code: string; name?: string; color?: string }) {
  const style = color ? { backgroundColor: color, color: inkFor(color) } : undefined;
  return (
    <span
      aria-label={name}
      style={style}
      className={`inline-flex min-w-[3ch] ring-1 ring-inset ring-pr-rule items-center justify-center rounded-pr px-1.5 py-0.5 font-pr-display text-sm font-bold uppercase tracking-wide ${
        color ? "" : "bg-pr-panel-2 text-pr-text"
      }`}
    >
      {code}
    </span>
  );
}
