/**
 * The plausible range behind a hit rate.
 *
 * A track record of "11 of 24" is a point estimate a reader will take as
 * settled fact. It is not: 24 picks is a sample, and the honest thing to draw
 * is the range the true rate could sit in. One helper, used by every sport's
 * headline, so the arithmetic is written once and cannot drift between five
 * pages.
 */
import { describe, expect, it } from "vitest";
import { wilsonInterval } from "./wilson";

describe("wilsonInterval", () => {
  it("matches the known value: 25 of 52 is about 35% to 61%", () => {
    const range = wilsonInterval(25, 52);
    expect(range).not.toBeNull();
    const [lo, hi] = range!;
    expect(Math.round(lo * 100)).toBe(35);
    expect(Math.round(hi * 100)).toBe(61);
  });

  it("returns null with nothing graded, never 0%", () => {
    // "0 of 0" is not a rate. A caller that forgot to check `n` would draw a bar
    // pinned at 0%, which reads as a model that has never been right.
    expect(wilsonInterval(0, 0)).toBeNull();
  });

  it("brackets a perfect record at the top of the range", () => {
    const [lo, hi] = wilsonInterval(5, 5)!;
    expect(hi).toBe(1);
    expect(lo).toBeGreaterThan(0.4);
  });

  it("brackets a winless record at the bottom of the range", () => {
    const [lo, hi] = wilsonInterval(0, 5)!;
    expect(lo).toBe(0);
    expect(hi).toBeLessThan(0.6);
  });

  it("never leaves [0, 1]", () => {
    for (const [c, n] of [
      [0, 1],
      [1, 1],
      [1, 100],
      [99, 100],
      [50, 50],
    ] as const) {
      const [lo, hi] = wilsonInterval(c, n)!;
      expect(lo).toBeGreaterThanOrEqual(0);
      expect(hi).toBeLessThanOrEqual(1);
      expect(lo).toBeLessThanOrEqual(hi);
    }
  });
});
