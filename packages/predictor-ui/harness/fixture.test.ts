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
  outPlayers,
  ranked,
  valueOf,
  assertFixtureConsistency,
  type Category,
} from "./fixture";

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