/**
 * The harness is a review instrument: if two mocks can disagree about the
 * same fixture, the reviewer has to catch it by eye. These tests pin the
 * guards that make that impossible — and, more importantly, prove each
 * guard THROWS. A guard that only ever passes is decoration.
 *
 * Each test below reproduces a bug a reviewer or a re-shoot actually found.
 */
import { describe, expect, it } from "vitest";
import {
  LISTS,
  PLAYERS,
  CATEGORY_KIND,
  BUCKET,
  SIGNALS,
  LONG_HEADLINE_SIGNAL,
  BELOW_FLOOR_SIGNAL,
  FIX,
  trustRate,
  outPlayers,
  ranked,
  valueOf,
  assertFixtureConsistency,
  type Category,
} from "./fixture";
import { SPEC_MIN_N, clipHeadline } from "../src";

const boxRows = () =>
  ["wilson", "robinson"].map((k) => ({
    key: k,
    values: [valueOf(PLAYERS[k], "Rush yds")],
  }));

const pickRows = () =>
  LISTS.flatMap(({ category }) =>
    ranked(category).map((p) => ({ category, playerKey: p.key, value: valueOf(p, category) })),
  );

describe("one fixture, one number", () => {
  it("accepts the mocks as authored", () => {
    expect(() => assertFixtureConsistency(pickRows(), boxRows())).not.toThrow();
  });

  it("throws when a box score row disagrees with the picks about the same player", () => {
    // Review finding 3: Robinson was 96 in the picks mock, 84 in the box score.
    expect(() =>
      assertFixtureConsistency(pickRows(), [{ key: "robinson", values: [84] }]),
    ).toThrow(/one fixture, one number/);
  });

  it("throws when a row restates a figure the object does not carry", () => {
    expect(() =>
      assertFixtureConsistency(
        [{ category: "Rush yds", playerKey: "robinson", value: 95 }],
        [],
      ),
    ).toThrow(/shows 95, object says 96/);
  });
});

describe("a row must be the KIND its category claims", () => {
  it("throws when a yardage figure is read as a probability", () => {
    // Caught by re-shooting: with one number per player, Robinson's 96 rush
    // yards rendered as his anytime-TD probability — "9600%".
    expect(() =>
      assertFixtureConsistency(
        [{ category: "Anytime TD", playerKey: "robinson", value: 96 }],
        [],
      ),
    ).toThrow(/read as a probability/);
  });

  it("every authored row is within its category's range", () => {
    for (const { category, playerKey, value } of pickRows()) {
      const kind = CATEGORY_KIND[category];
      if (kind === "probability") {
        expect(value, `${playerKey} ${category}`).toBeGreaterThanOrEqual(0);
        expect(value, `${playerKey} ${category}`).toBeLessThanOrEqual(1);
      } else {
        expect(value, `${playerKey} ${category}`).toBeGreaterThan(0);
      }
    }
  });
});

describe("an out player leaves the ranking", () => {
  it("the fixture has an out player, and no list ranks them", () => {
    expect(outPlayers().map((p) => p.key)).toEqual(["jacobs"]);
    for (const { category } of LISTS) {
      expect(ranked(category).map((p) => p.key)).not.toContain("jacobs");
    }
  });

  it("throws if an out player is ranked with a number", () => {
    // Review finding 2: Jacobs was the #2 rush pick with a bold tile.
    expect(() =>
      assertFixtureConsistency(
        [...pickRows(), { category: "Rush yds", playerKey: "jacobs", value: 78 }],
        [],
      ),
    ).toThrow(/is OUT but still appears/);
  });

  it("throws if the box score projects an out player", () => {
    expect(() =>
      assertFixtureConsistency(pickRows(), [{ key: "jacobs", values: [78] }]),
    ).toThrow(/is out, so the box score must not project him/);
  });
});

describe("one category per list", () => {
  it("throws when a player's row sits under another category's heading", () => {
    // Review finding 4: an Adebayo rebounds row inside "NBA points — top 3".
    expect(() =>
      assertFixtureConsistency(
        [...pickRows(), { category: "Points" as Category, playerKey: "adebayo", value: 10.2 }],
        [],
      ),
    ).toThrow(/one category per list/);
    expect(LISTS.find((l) => l.category === "Points")!.keys).not.toContain("adebayo");
  });

  it("every category's rows come from its own key list", () => {
    for (const { category, keys } of LISTS) {
      for (const p of ranked(category)) expect(keys).toContain(p.key);
    }
  });
});

/* ---------------------------------------------------------------------------
 * The signal mocks, held to the same rule as the player mocks: one fixture, one
 * number, and the figures a signal shows are the fixture's own.
 *
 * These are 4 of the harness's tests, and the count matters — `fixture.test.ts`
 * is the guard whose size is quoted when it is extended, so it is pinned here by
 * the count it had (12) plus these four.
 * --------------------------------------------------------------------------- */

describe("a signal's figures come from the one fixture", () => {
  it("states the model's gap as the fixture's own arithmetic, magnitude not signed", () => {
    // The tile above says `model GB -6.1` against `line GB -4.5`. The gap is
    // 1.6 either way round; `FIX.edge` is -1.6 because the home frame signs it,
    // and the chip signs its own copy with `fmt.signed`. Asserted on both so a
    // change to either getter is a failure rather than a screenshot nobody reads.
    //
    // `toBeCloseTo`, not `toBe`: -6.1 - -4.5 is -1.5999999999999996 in binary
    // floating point, and `FIX.edge` is exactly that difference rounded to one
    // decimal. Pinning the raw subtraction to a literal would be a false claim
    // about what floats do.
    expect(FIX.modelMargin - FIX.spreadLine).toBeCloseTo(-1.6, 10);
    expect(FIX.edge).toBe(-1.6);
    expect(FIX.edgePts).toBe(1.6);
    const gap = SIGNALS.find((s) => s.kind === "line_gap")!;
    expect(gap.headline.figures.gap).toBe(FIX.edgePts);
    expect(gap.headline.figures.model_margin).toBe(FIX.modelMargin);
    expect(gap.headline.figures.line).toBe(FIX.spreadLine);
  });

  it("selects the bucket from FIX's own probability, never a second number", () => {
    // CodeRabbit review comment 4171773474. The first draft typed `model_prob:
    // 0.66` beside a tile that says 72% — both plausible, and the mock claiming
    // the model sits in the 60s while the tile above it said 70%. That is exactly
    // the drift this file exists to end, found in a file written to prevent it.
    expect(BUCKET.model_prob).toBe(FIX.homeWinProb);
    // And the label is DERIVED from that, not typed beside it.
    const low = Math.floor(FIX.homeWinProb * 10);
    expect(BUCKET.label).toBe(`${(low / 10).toFixed(1)}-${((low + 1) / 10).toFixed(1)}`);
    const trust = SIGNALS.find((s) => s.kind === "trust")!;
    expect(trust.source).toContain(BUCKET.label);
    // The headline's own probability is the tile's, so the two agree on the page.
    expect(trust.headline.text).toContain(`${Math.round(FIX.homeWinProb * 100)}%`);
  });

  it("states the trust rate as its own bucket's hits over n, computed once", () => {
    expect(trustRate).toBe(BUCKET.hits / BUCKET.n);
    const trust = SIGNALS.find((s) => s.kind === "trust")!;
    // A rate, so the [0,1] guard is a real assertion here and not a tautology.
    expect(trust.headline.figures.rate).toBeGreaterThan(0);
    expect(trust.headline.figures.rate).toBeLessThanOrEqual(1);
    expect(trust.headline.figures.rate).toBe(trustRate);
    expect(trust.n).toBe(BUCKET.n);
    // And that bucket clears the floor, so the populated mock actually renders.
    expect(BUCKET.n).toBeGreaterThanOrEqual(SPEC_MIN_N);
  });

  it("every figure a visual DRAWS is stated in its headline's own words", () => {
    // The honesty property, at the fixture level: the harness mock must not be
    // the thing that teaches a reader to expect a figure the words do not carry.
    //
    // Scoped to the DRAWN figure, deliberately. `figures` is an open record
    // (spec §3 writes `{figures...}`), so a signal also carries figures nothing
    // draws — `model_margin` and `line` here, `model_prob` in the trust row —
    // and they are the evidence behind the sentence rather than claims on it.
    // Requiring all of them in a 12-word headline would be the same rule as
    // "no sentence may have evidence", and would push the adapters to drop the
    // provenance a future "so what" step needs.
    const DRAWN: Record<string, string> = { reliability_bar: "rate", delta_chip: "gap" };
    for (const signal of SIGNALS) {
      const name = DRAWN[signal.visual];
      const value = signal.headline.figures[name];
      expect(value, `${signal.kind}: nothing to draw`).toBeTypeOf("number");
      const word = signal.visual === "reliability_bar" ? `${Math.round(value * 100)}%` : `${value}`;
      expect(signal.headline.text, `${signal.kind}: figures.${name} is not in the headline`).toContain(word);
    }
  });

  it("the below-floor and long-headline states are states of THIS row, not new ones", () => {
    // Both keep the populated row's figures, so a screenshot of either cannot
    // show a number the other states do not.
    expect(BELOW_FLOOR_SIGNAL.n).toBeLessThan(SPEC_MIN_N);
    expect(BELOW_FLOOR_SIGNAL.game_id).toBe(SIGNALS[0].game_id);
    expect(clipHeadline(BELOW_FLOOR_SIGNAL.headline.text).clipped).toBe(false);
    // The long one keeps the SAME rate and is over the cap.
    expect(LONG_HEADLINE_SIGNAL.headline.figures.rate).toBe(SIGNALS[0].headline.figures.rate);
    expect(clipHeadline(LONG_HEADLINE_SIGNAL.headline.text).clipped).toBe(true);
  });
});

describe("the ranking is computed, not hand-written", () => {
  it("sorts each list by that category's own number", () => {
    // Robinson is 0.38 as a TD candidate and 96 as a rusher: the two lists
    // must not share a sort key.
    expect(ranked("Anytime TD").map((p) => p.key)).toEqual(["robinson", "love"]);
    expect(ranked("Rush yds").map((p) => p.key)).toEqual(["robinson", "wilson"]);
    expect(valueOf(PLAYERS.robinson, "Anytime TD")).toBeLessThan(
      valueOf(PLAYERS.robinson, "Rush yds"),
    );
  });

  it("every ranked player has a figure for that category", () => {
    for (const { category } of LISTS) {
      for (const p of ranked(category)) {
        expect(p.values[category], `${p.name} ${category}`).toBeTypeOf("number");
      }
    }
  });
});