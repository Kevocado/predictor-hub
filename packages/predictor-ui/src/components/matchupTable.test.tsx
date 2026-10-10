import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MatchupTable } from "./MatchupTable";

const PIVOT = {
  home: "Arsenal",
  away: "Chelsea",
  rows: [
    { key: "goals_scored_per_match", label: "Goals scored per match", homeRank: 3, awayRank: 12, n: 20 },
    { key: "goals_conceded_per_match", label: "Goals conceded per match", homeRank: 2, awayRank: 5, n: 20 },
    { key: "possession_pct", label: "Possession %", homeRank: 2, awayRank: 10, n: 20 },
  ],
};

const PIVOT_HALF_PRESENT = {
  home: "Bills",
  away: "Jets",
  rows: [
    { key: "pass_off_vs_pass_def", label: "Pass off vs pass def", homeRank: 3, awayRank: null, n: 32 },
  ],
};

function getRankBoxes(container: HTMLElement) {
  return container.querySelectorAll('[data-testid="rank-box"]');
}

describe("MatchupTable", () => {
  it("renders home name left and away name right in the header", () => {
    render(<MatchupTable pivot={PIVOT} />);
    expect(screen.getByText("Arsenal")).toBeInTheDocument();
    expect(screen.getByText("Chelsea")).toBeInTheDocument();
    // Home should be in first column, away in third column
    const headerCells = screen.getAllByRole("columnheader");
    expect(headerCells[0]).toHaveTextContent("Arsenal");
    expect(headerCells[2]).toHaveTextContent("Chelsea");
  });

  it("renders three columns per row: home rank, label, away rank", () => {
    render(<MatchupTable pivot={PIVOT} />);
    const rows = screen.getAllByRole("row");
    // header + 3 data rows
    expect(rows).toHaveLength(4);
    // Check first data row
    const firstRow = rows[1];
    const cells = firstRow.querySelectorAll("td");
    expect(cells).toHaveLength(3);
    expect(cells[0]).toHaveTextContent("3"); // home rank
    expect(cells[1]).toHaveTextContent("Goals scored per match"); // label
    expect(cells[2]).toHaveTextContent("12"); // away rank
  });

  it("each rank box shows only the number", () => {
    render(<MatchupTable pivot={PIVOT} />);
    const rankBoxes = getRankBoxes(document.body);
    expect(rankBoxes).toHaveLength(6); // 3 rows * 2 ranks
    rankBoxes.forEach((box) => {
      expect(box.textContent?.trim()).toMatch(/^\d+$/);
    });
  });

  it("aria-label on each rank box includes team, ordinal rank, and total", () => {
    render(<MatchupTable pivot={PIVOT} />);
    const rankBoxes = getRankBoxes(document.body);
    // First box: Arsenal home rank 3
    expect(rankBoxes[0]).toHaveAttribute("aria-label", "Arsenal: 3rd of 20 for Goals scored per match");
    // Second box: Chelsea away rank 12
    expect(rankBoxes[1]).toHaveAttribute("aria-label", "Chelsea: 12th of 20 for Goals scored per match");
  });

  it("tier class per box: good/mid/bad based on rankTier", () => {
    render(<MatchupTable pivot={PIVOT} />);
    const rankBoxes = getRankBoxes(document.body);
    // n=20: third=7, good=1-7, mid=8-14, bad=15-20
    // homeRank 3 -> good, awayRank 12 -> mid
    expect(rankBoxes[0]).toHaveClass("pr-rank-good");
    expect(rankBoxes[1]).toHaveClass("pr-rank-mid");
  });

  it("no bar/progress elements in the DOM", () => {
    render(<MatchupTable pivot={PIVOT} />);
    expect(screen.queryByTestId("rank-fill")).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    // No div with style width that looks like a bar
    const bars = document.querySelectorAll('div[style*="width"]');
    expect(bars).toHaveLength(0);
  });

  it("half-present row shows em dash on missing side", () => {
    render(<MatchupTable pivot={PIVOT_HALF_PRESENT} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(2); // header + 1 data row
    const cells = rows[1].querySelectorAll("td");
    expect(cells[0]).toHaveTextContent("3");
    expect(cells[2]).toHaveTextContent("—"); // em dash for missing away rank
  });

  it("nothing drawable renders nothing", () => {
    const { container } = render(<MatchupTable pivot={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders table with caption for accessibility", () => {
    render(<MatchupTable pivot={PIVOT} />);
    const caption = screen.getByText("Matchup: Arsenal vs Chelsea");
    expect(caption).toBeInTheDocument();
    // caption should be visually hidden
    expect(caption).toHaveClass("sr-only");
  });

  it("middle column (label) wraps to two lines on narrow viewport", () => {
    // This is a CSS concern, but we can verify the structure allows it
    render(<MatchupTable pivot={PIVOT} />);
    const labelCell = screen.getByText("Goals scored per match").closest("td");
    expect(labelCell).toHaveClass("pr-matchup-label");
  });
});