import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProbabilityBar } from "./ProbabilityBar";
import { MatchCard } from "./MatchCard";

describe("ProbabilityBar", () => {
  it("labels every segment in the given order, in words and for assistive tech", () => {
    render(<ProbabilityBar segments={[{ label: "Home", prob: 0.36 }, { label: "Draw", prob: 0.26 }, { label: "Away", prob: 0.38 }]} />);
    const bar = screen.getByRole("img");
    expect(bar).toHaveAccessibleName("Home 36%, Draw 26%, Away 38%");
    const labels = screen.getAllByTestId("pbar-label").map((n) => n.textContent);
    expect(labels).toEqual(["Home 36%", "Draw 26%", "Away 38%"]);
  });
  it("keeps a two-way bar in the header's order (away first for US sports)", () => {
    render(<ProbabilityBar segments={[{ label: "KC", prob: 0.38, color: "#E31837" }, { label: "BAL", prob: 0.62, color: "#241773" }]} />);
    expect(screen.getAllByTestId("pbar-label").map((n) => n.textContent)).toEqual(["KC 38%", "BAL 62%"]);
  });
});

const base = {
  left: { code: "TOT", name: "Tottenham" },
  right: { code: "AVL", name: "Aston Villa" },
  centre: "2–3",
  status: "called" as const,
  onOpen: () => {},
};

describe("MatchCard", () => {
  it("states one pick with its confidence", () => {
    render(<MatchCard {...base} pick={{ label: "Aston Villa win", prob: 0.38 }} />);
    expect(screen.getByText("Pick: Aston Villa win · 38%")).toBeInTheDocument();
    expect(screen.getByText("Called it ✓")).toBeInTheDocument();
  });
  it("says 'No pick yet' without a pick, and shows exactly one status", () => {
    render(<MatchCard {...base} status="nopick" />);
    expect(screen.getAllByText(/Next up|Live|Called it|Missed|No pick yet|Rebuilt after kickoff/)).toHaveLength(1);
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
  });
  it("is a real button: Enter and Space both open it, and its name summarises the pick", async () => {
    const onOpen = vi.fn();
    render(<MatchCard {...base} pick={{ label: "Aston Villa win", prob: 0.38 }} onOpen={onOpen} />);
    const card = screen.getByRole("button");
    expect(card).toHaveAccessibleName("Tottenham v Aston Villa, 2–3. Pick: Aston Villa win · 38%. Called it ✓");
    card.focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
  it("shows sport meta such as a spread line", () => {
    render(<MatchCard {...base} status="next" meta="KC −3.5 · Total 46.5" />);
    expect(screen.getByText("KC −3.5 · Total 46.5")).toBeInTheDocument();
  });
});
