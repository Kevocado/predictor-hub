// The one owner of numbers on screen. Models and APIs keep full precision;
// rounding, signs, team names and time zones happen here, once, so every
// Predictor site reads the same.

const MINUS = "−";
const DASH = "—";

const bad = (x: number) => typeof x !== "number" || Number.isNaN(x);

/** Whole percent. A live probability never reads 0% or 100%. */
export function pct(p: number): string {
  if (bad(p)) return DASH;
  if (p <= 0.005) return "<1%";
  if (p >= 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** One decimal under 10% (where the difference matters), whole above. */
export function pctFine(p: number): string {
  if (bad(p)) return DASH;
  if (p < 0.001) return "<0.1%";
  if (p < 0.1) return `${(p * 100).toFixed(1)}%`;
  return pct(p);
}

/** One decimal: a projection of 16.514 carries no more meaning than 16.5. */
export function stat(x: number): string {
  return bad(x) ? DASH : x.toFixed(1);
}

/** Always signed, with a true minus sign. */
export function signed(x: number): string {
  if (bad(x)) return DASH;
  if (x > 0) return `+${x.toFixed(1)}`;
  if (x < 0) return `${MINUS}${Math.abs(x).toFixed(1)}`;
  return "0.0";
}

/** W3 / L1 instead of 3 / -1. */
export function streak(n: number): string {
  if (bad(n) || n === 0) return DASH;
  return `${n > 0 ? "W" : "L"}${Math.abs(n)}`;
}

/** Hits over settled picks; nothing settled reads as a dash, never 0/0. */
export function record(hits: number, settled: number): string {
  return settled > 0 ? `${hits}/${settled}` : DASH;
}

/** "MIA by 4.8" for the favoured team; under half a point is a toss-up. */
export function margin(team: string, x: number): string {
  if (bad(x) || Math.abs(x) < 0.5) return "Toss-up";
  return `${team} by ${Math.abs(x).toFixed(1)}`;
}

/** A betting line written with its team: "KC −3.5", "KC +3", "KC PK". */
export function spread(team: string, line: number): string {
  if (bad(line)) return DASH;
  if (line === 0) return `${team} PK`;
  const n = Number.isInteger(line) ? String(Math.abs(line)) : Math.abs(line).toFixed(1);
  return `${team} ${line < 0 ? MINUS : "+"}${n}`;
}

/** "Sat 3 Oct · 7:30 PM CDT": always shows the zone the time is in. */
export function kickoff(iso: string, timeZone?: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    })
      .formatToParts(d)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.weekday} ${parts.day} ${parts.month} · ${parts.hour}:${parts.minute} ${parts.dayPeriod} ${parts.timeZoneName}`;
}

/** "v20260918120240" or an ISO timestamp → "Sep 18 model". */
export function modelDate(id: string): string {
  const compact = /^v?(\d{4})(\d{2})(\d{2})/.exec(id);
  const d = compact ? new Date(Date.UTC(+compact[1], +compact[2] - 1, +compact[3])) : new Date(id);
  if (Number.isNaN(d.getTime())) return "Model";
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} model`;
}
