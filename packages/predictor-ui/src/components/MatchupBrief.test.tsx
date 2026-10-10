import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MatchupBrief, groupBySlot } from "./MatchupBrief";

const duel = {
  id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets",
  stat: "passing offence", foil: "pass defence",
  attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true,
};
const factors = [
  {
    key: "matchup:pass_off_vs_pass_def:home", direction: "up" as const, slot: "edge" as const,
    headline: "Bills' #3 passing offence meets Jets' #28 pass defence", text: "t",
  },
  {
    key: "spread", direction: "neutral" as const, slot: "price" as const,
    headline: "Model -4.0 against a quoted -6.5", text: "t",
  },
];

describe("groupBySlot", () => {
  it("keeps order within a slot and drops nothing", () => {
    const g = groupBySlot([...factors, { ...factors[0], key: "matchup:b" }]);
    expect(g.edge.map((f) => f.key)).toEqual(["matchup:pass_off_vs_pass_def:home", "matchup:b"]);
    expect(g.price).toHaveLength(1);
  });

  it("a factor with no slot is context, because that is where an absent one draws", () => {
    const { slot: _dropped, ...legacy } = factors[0];
    expect(groupBySlot([legacy]).context).toHaveLength(1);
  });
});

describe("MatchupBrief", () => {
  it("labels the groups and draws the duel for a matchup row", () => {
    render(<MatchupBrief factors={factors} matchups={[duel]} />);
    expect(screen.getByRole("heading", { name: "Edge" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Price" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Risk" })).toBeNull();   // an empty slot is omitted, not padded
    expect(within(screen.getByTestId("rank-duel")).getByText("#28", { exact: false })).toBeInTheDocument();
  });

  it("refuses a duel whose ranks the headline does not state", () => {
    const bad = [{ ...factors[0], headline: "Bills have the edge in the air" }];
    expect(() => render(<MatchupBrief factors={bad} matchups={[duel]} />)).toThrow(/headline/i);
  });

  it("a number that is not written as a rank does not count as stating it", () => {
    const bad = [{ ...factors[0], headline: "Bills scored 3 points; Jets allowed 28 points" }];
    expect(() => render(<MatchupBrief factors={bad} matchups={[duel]} />)).toThrow(/headline/i);
  });

  it("a matchup factor with no matching row in matchups is not drawn as a duel", () => {
    render(<MatchupBrief factors={factors} matchups={[]} />);
    expect(screen.queryByTestId("rank-duel")).toBeNull();
    expect(screen.getByText(/#3 passing offence/)).toBeInTheDocument();   // the words still render
  });

  it("the risk group is drawn when the code directs a duel the other way", () => {
    const against = {
      ...duel, id: "rush_off_vs_rush_def:home", stat: "rushing offence", foil: "run defence",
      attacker_rank: 19, defender_rank: 4, toward_pick: false,
    };
    render(
      <MatchupBrief
        factors={[factors[0], { ...factors[0], key: `matchup:${against.id}`, slot: "risk", headline: "Bills' #19 rushing offence runs into Jets' #4 run defence" }]}
        matchups={[duel, against]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Risk" })).toBeInTheDocument();
    expect(screen.getAllByTestId("rank-duel")).toHaveLength(2);
  });

  it("context rows keep rendering through FactorList, with their direction words", () => {
    render(
      <MatchupBrief
        factors={[...factors, { key: "record", direction: "neutral", slot: "context", headline: "Its record so far", text: "41 of 68 landed." }]}
        matchups={[duel]}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("context")).toBeInTheDocument();
    expect(screen.getByTestId("factor-record")).toBeInTheDocument();
  });

  it("a row lights the figure it names, and pressing it again clears the light", async () => {
    const onSelect = vi.fn();
    render(<MatchupBrief factors={factors} matchups={[duel]} onSelect={onSelect} highlighted={null} />);
    const row = screen.getByTestId("factor-spread");
    expect(row).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(row);
    expect(onSelect).toHaveBeenCalledWith("spread");
    // A matchup row has no figure to light, so the panel's guard clears instead —
    // the row is still a real control, and pressing it is still something.
    await userEvent.click(screen.getByTestId("factor-matchup:pass_off_vs_pass_def:home"));
    expect(onSelect).toHaveBeenLastCalledWith("matchup:pass_off_vs_pass_def:home");
  });

  it("a pressed row is the one the panel says is lit", () => {
    render(<MatchupBrief factors={factors} matchups={[duel]} onSelect={() => {}} highlighted="spread" />);
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("factor-spread")).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("factor-matchup:pass_off_vs_pass_def:home"))
      .toHaveAttribute("aria-pressed", "false");
  });

  it("every duel row is checked, not only the first", () => {
    // `assertStates` runs per row inside `Row`; a version that checked once, on the
    // first matchup factor, would pass every other test in this file.
    const second = { ...duel, id: "b", attacker_rank: 19, defender_rank: 4 };
    const good = { ...factors[0], headline: "Bills' #3 passing offence meets Jets' #28 pass defence" };
    const bad = { ...factors[0], key: "matchup:b", headline: "Their running game against that run defence" };
    expect(() => render(<MatchupBrief factors={[good, bad]} matchups={[duel, second]} />))
      .toThrow(/matchup:b/);
  });
});

describe("MatchupBrief: undirected duels", () => {
  const neutral = { ...duel, toward_pick: null };
  const neutralFactor = {
    key: "matchup:pass_off_vs_pass_def:home", direction: "neutral" as const, slot: "context" as const,
    headline: "Bills' #3 passing offence and Jets' #28 pass defence", text: "t",
  };

  it("draws a duel the code did not direct under a plain Matchup heading, with the rank bars and no Edge/Risk", () => {
    render(<MatchupBrief factors={[neutralFactor]} matchups={[{ ...neutral, id: "pass_off_vs_pass_def:home" }]} />);
    expect(screen.getByRole("heading", { name: "Matchup" })).toBeInTheDocument();
    expect(screen.getByTestId("rank-duel")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Edge" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Risk" })).toBeNull();
  });

  it("a context row that is not a known duel stays in the ordinary context list", () => {
    render(<MatchupBrief factors={[{ key: "record", direction: "neutral", slot: "context", headline: "Record", text: "t" }]} matchups={[]} />);
    expect(screen.queryByRole("heading", { name: "Matchup" })).toBeNull();
    expect(screen.queryByTestId("rank-duel")).toBeNull();
  });

  it("still refuses a neutral duel whose headline does not state the ranks it draws", () => {
    const bad = { ...neutralFactor, headline: "Bills have an edge in the air" };
    expect(() => render(<MatchupBrief factors={[bad]} matchups={[{ ...neutral, id: "pass_off_vs_pass_def:home" }]} />)).toThrow(/headline/i);
  });
});

