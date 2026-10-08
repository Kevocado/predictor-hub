import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankDuel, RankOutOfRangeError, rankFill } from "./RankDuel";

const base = {
  attacker: "Bills", attackerStat: "passing offence", attackerRank: 3,
  defender: "Jets", defenderStat: "pass defence", defenderRank: 28, nTeams: 32,
};

describe("rankFill", () => {
  it("first is full, last is a stub, never empty", () => {
    expect(rankFill(1, 32)).toBe(1);
    expect(rankFill(32, 32)).toBe(1 / 32);
  });
  it.each([[0, 32], [33, 32], [1.5, 32], [3, 1]])("refuses rank %s of %s", (r, n) => {
    expect(() => rankFill(r, n)).toThrow(RankOutOfRangeError);
  });
  it("refuses a league size that is not a whole number of teams", () => {
    expect(() => rankFill(3, 32.5)).toThrow(RankOutOfRangeError);
  });
});

describe("RankDuel", () => {
  it("prints both ranks and league size beside the bars", () => {
    render(<RankDuel {...base} />);
    const duel = screen.getByTestId("rank-duel");
    expect(duel).toHaveTextContent("Bills · passing offence");
    expect(duel).toHaveTextContent("#3 of 32");
    expect(duel).toHaveTextContent("#28 of 32");
  });

  it("draws the strong unit long and the weak one short", () => {
    render(<RankDuel {...base} />);
    const [a, d] = screen.getAllByTestId("rank-fill");
    expect(a).toHaveStyle({ width: "93.8%" });
    expect(d).toHaveStyle({ width: "15.6%" });
  });

  it("refuses an impossible rank instead of drawing it", () => {
    expect(() => render(<RankDuel {...base} defenderRank={40} />)).toThrow(RankOutOfRangeError);
  });

  it("a full bar and a stub are both drawn, so the weakest unit is still visible", () => {
    // The reason the floor is 1/n rather than 0: a zero-width bar is invisible,
    // and last in the league is a fact a reader needs as much as first.
    render(<RankDuel {...base} attackerRank={1} defenderRank={32} />);
    const [a, d] = screen.getAllByTestId("rank-fill");
    expect(a).toHaveStyle({ width: "100%" });
    expect(d).toHaveStyle({ width: "3.1%" });
  });

  it("the bar track is presentational, so a screen reader reads the ranks once", () => {
    render(<RankDuel {...base} />);
    expect(screen.getByTestId("rank-duel").textContent).toContain("#3 of 32");
  });
});